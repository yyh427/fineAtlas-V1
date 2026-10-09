#!/usr/bin/env python3
"""Replay frozen unified inputs into an independent copy of FineAtlas.

Uses Migration and its existing graph/cache schema. Primary input files and
existing candidates are immutable. Source claims, UID mappings and task target
changes are retained in the normal change/evidence ledgers.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.migration import Migration
from fineatlas.hierarchy import apply_refinements
from fineatlas.semantics import role_expression
from fineatlas.unified_build import ram_graphs


def label_key(name):
    # Dataset typography only: full names, no prefixes, suffixes or fuzzy match.
    name=re.sub(r"['’]s\b",'',name.casefold())
    return ''.join(ch for ch in name if ch.isalnum())


def apply_breed_identities(m):
    """Replay independently corroborated identities for the full dog subtree."""
    c=m.c; counts=Counter()
    for r in json.loads((m.inputs/'unified_breed_identities.json').read_text()):
        proof=r['proof']
        for uid,key in ((r['left_uid'],'native_record_sha256'),
                        (r['right_uid'],'wordnet_native_record_sha256')):
            node=c.execute('SELECT data,visibility FROM nodes WHERE uid=?',(uid,)).fetchone()
            if not node or node['visibility']!='ACTIVE' or hashlib.sha256(node['data'].encode()).hexdigest()!=proof[key]:
                raise ValueError('Frozen breed concept source differs: '+uid)
        eid=m.evidence('Verified primary breed concept identifiers',proof['source_uri'],proof,'SOURCE_IDENTIFIER_ALIGNMENT')
        m.align_identity(r['left_uid'],{'uid':r['right_uid'],'basis':proof['basis']},proof,
                         'Verified primary breed concept identifiers',proof['source_uri'])
        identifier=hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()
        c.execute('INSERT OR IGNORE INTO unified_identity_rules VALUES (?,?,?,?,?)',
                  (identifier,r['left_uid'],r['right_uid'],eid,json.dumps(r,ensure_ascii=False)))
        counts['source_identifier_links']+=1
    for table,left,right in [('edges','child_uid','parent_uid'),('entity_relations','subject_uid','object_uid')]:
        for e in c.execute(f"SELECT e.* FROM {table} e JOIN nodes a ON a.uid=e.{left} JOIN nodes b ON b.uid=e.{right} WHERE a.component_id=b.component_id AND e.status IN ('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE')").fetchall():
            c.execute('UPDATE '+table+" SET status='IDENTITY_RESOLVED' WHERE id=?",(e['id'],))
            m.change('unified_identity_zero_depth',table,e['id'],dict(e),{'status':'IDENTITY_RESOLVED'},
                     {'basis':'Verified source concept identity; declaration retained without artificial depth'})
            counts['identity_self_arcs_retained_without_depth']+=1
    c.commit();return dict(counts)


def apply_display_aliases(m):
    path=m.inputs/'unified_display_aliases.jsonl';count=0
    if not path.exists():return {'existing_names_indexed':0}
    for line in path.open():
        r=json.loads(line);n=m.c.execute('SELECT data FROM nodes WHERE uid=?',(r['uid'],)).fetchone()
        if not n or hashlib.sha256(n['data'].encode()).hexdigest()!=r['native_record_sha256']:
            raise ValueError('Retained name source checksum differs')
        m.alias(r['uid'],r['name'],'Existing retained display-name indexing')
        count+=1
        if count%10000==0:m.c.commit();print('DISPLAY ALIASES',count,flush=True)
    m.c.commit();return {'existing_names_indexed':count,'identity_assertions_added':0}


def apply_repair_extensions(m):
    """Replay separately frozen 1.10 repairs before any derived cache is built."""
    results={}
    if (m.inputs/'shared_role_repairs.jsonl').exists():
        from prepare_shared_role_repairs import apply_shared_repairs
        results['shared_roles']=apply_shared_repairs(m)
    if (m.inputs/'annotation_scope_repairs.json').exists():
        from prepare_annotation_scope_repairs import apply_scope_repairs
        results['annotation_scope']=apply_scope_repairs(m)
    if (m.inputs/'annotation_historical_alias_repairs.json').exists():
        from prepare_annotation_scope_repairs import apply_scope_supplement
        results['annotation_historical_aliases']=apply_scope_supplement(m)
    if (m.inputs/'abo_furniture_records.jsonl').exists():
        from prepare_abo_furniture import apply_abo_inputs
        results['furniture_trial']=apply_abo_inputs(m)
    if (m.inputs/'living_domains_manifest.json').exists():
        from prepare_living_domains import apply_living_inputs
        results['living_domains']=apply_living_inputs(m)
    if (m.inputs/'repair_role_links.jsonl').exists():
        results['repaired_role_navigation']=apply_refinements(m,'repair_role_links.jsonl')
    if results:
        from fineatlas.hierarchy import review_version
        m.meta('release',review_version(m.inputs))
        m.meta('browse_indexes_ready',False)
        m.meta('unified_ready',False)
        m.c.commit()
        (m.out/'repair_extensions_summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    return results


def apply(m):
    c=m.c;counts=Counter()
    c.executescript('''
      CREATE TABLE IF NOT EXISTS unified_backbone_nodes(uid TEXT PRIMARY KEY,payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS unified_backbone_edges(original_edge_id INTEGER PRIMARY KEY,payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS unified_domain_rules(domain_id INTEGER,native_root_uid TEXT,wordnet_anchor_uid TEXT,payload TEXT NOT NULL,PRIMARY KEY(domain_id,native_root_uid));
      CREATE TABLE IF NOT EXISTS unified_identity_rules(id TEXT PRIMARY KEY,left_uid TEXT,right_uid TEXT,evidence_id TEXT,payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS dataset_target_history(dataset TEXT,class_id TEXT,original_target_uid TEXT,original_record TEXT,PRIMARY KEY(dataset,class_id));
      CREATE TABLE IF NOT EXISTS dataset_mapping_checks(dataset TEXT,class_id TEXT,status TEXT,reason TEXT,proof TEXT,PRIMARY KEY(dataset,class_id));
    ''')
    for r in json.loads((m.inputs/'unified_backbone_nodes.json').read_text()):
        n=c.execute('SELECT data,description FROM nodes WHERE uid=?',(r['uid'],)).fetchone()
        if not n or hashlib.sha256(n['data'].encode()).hexdigest()!=r['native_record_sha256'] or n['description']!=r['definition']:
            raise ValueError('Selected WordNet definition differs from frozen source')
        c.execute('INSERT OR REPLACE INTO unified_backbone_nodes VALUES (?,?)',(r['uid'],json.dumps(r,ensure_ascii=False)))
    for r in json.loads((m.inputs/'unified_backbone_edges.json').read_text()):
        e=c.execute('SELECT * FROM edges WHERE id=?',(r['id'],)).fetchone()
        if not e or dict(e)!=r:raise ValueError('Original WordNet hypernym differs')
        c.execute('INSERT OR REPLACE INTO unified_backbone_edges VALUES (?,?)',(r['id'],json.dumps(r)))
        if r['status']=='PRUNED_WORDNET':
            fields=[k for k in r if k!='id'];v=dict(r);v.update(layer='v1.10-unified-backbone',status='BACKBONE_ACTIVE',reason='Selected original WordNet 3.1 upper hypernym; unified view only')
            if not c.execute("SELECT 1 FROM edges WHERE child_uid=? AND parent_uid=? AND layer='v1.10-unified-backbone'",(r['child_uid'],r['parent_uid'])).fetchone():
                c.execute('INSERT INTO edges('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',[v[k] for k in fields])
    for r in json.loads((m.inputs/'unified_domain_rules.json').read_text()):
        c.execute('INSERT OR REPLACE INTO unified_domain_rules VALUES (?,?,?,?)',
                  (r['domain_id'],r['native_root_uid'],r['wordnet_anchor_uid'],json.dumps(r,ensure_ascii=False)))
    c.commit();print('APPLY PRIMARY CONCEPT IDENTITIES',flush=True)
    for filename in ('unified_taxon_identities.json','unified_opentree_identities.json'):
        for r in json.loads((m.inputs/filename).read_text()):
            proof=r['proof'];uid=r['left_uid'];target=r['right_uid']
            # All declared identifiers remain separate UIDs, with explicit
            # identity steps costing zero in hierarchy queries.
            eid=m.evidence('Verified primary taxon concept identifiers',proof['source_uri'],proof,'SOURCE_IDENTIFIER_ALIGNMENT')
            m.align_identity(uid,{'uid':target,'basis':proof['basis']},proof,
                             'Verified primary taxon concept identifiers',proof['source_uri'])
            identifier=hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()
            c.execute('INSERT OR IGNORE INTO unified_identity_rules VALUES (?,?,?,?,?)',
                      (identifier,uid,target,eid,json.dumps(r,ensure_ascii=False)))
            counts['source_identifier_links']+=1
        c.commit()
    # A formerly distinct class inclusion may become an identity self-arc.
    # Preserve its original source declaration, but do not count it as depth.
    for table,left,right in [('edges','child_uid','parent_uid'),('entity_relations','subject_uid','object_uid')]:
        sql=f"SELECT e.* FROM {table} e JOIN nodes a ON a.uid=e.{left} JOIN nodes b ON b.uid=e.{right} WHERE a.component_id=b.component_id AND e.status IN ('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE')"
        for e in c.execute(sql).fetchall():
            before=dict(e)
            c.execute('UPDATE '+table+" SET status='IDENTITY_RESOLVED' WHERE id=?",(e['id'],))
            m.change('unified_identity_zero_depth',table,e['id'],before,{'status':'IDENTITY_RESOLVED'},
                     {'basis':'Primary-identifier-confirmed concept identity; original relation retained as a source record'})
            counts['identity_self_arcs_retained_without_depth']+=1
    c.commit()
    if (m.inputs/'unified_breed_identities.json').exists():
        counts.update(apply_breed_identities(m))
    print('APPLY PRIMARY AVIList NAMES AND TASK ALIGNMENT',flush=True)
    fullnames={};species={}
    for r in json.loads((m.inputs/'unified_avilist_native_records.json').read_text()):
        uid=r['uid'];row=r['row']
        n=c.execute('SELECT visibility FROM nodes WHERE uid=?',(uid,)).fetchone()
        if not n or n['visibility']!='ACTIVE':continue
        species[uid]=r
        evidence=m.evidence('AviList v2025b primary species concept','https://doi.org/10.2173/avilist.v2025b',
                            {'source_sha256':r['source_sha256'],'record':row,'license':'CC BY 4.0'},'PRIMARY_NATIVE_TAXON')
        for field in ('English_name_AviList','English_name_Clements_v2025','English_name_BirdLife_v10'):
            name=str(row.get(field,'')).strip()
            if name:
                fullnames.setdefault(label_key(name),set()).add(uid)
                m.alias(uid,name,'AviList v2025b '+field)
        name=str(row.get('English_name_AviList','')).strip()
        if name:
            c.execute('INSERT OR IGNORE INTO node_names VALUES (?,?,?,?,?,?)',
                      (uid,name,'en',1,'AviList v2025b primary English name',evidence))
    rows=c.execute('SELECT * FROM dataset_targets ORDER BY dataset,class_id').fetchall()
    for t in rows:
        original=dict(t)
        c.execute('INSERT OR IGNORE INTO dataset_target_history VALUES (?,?,?,?)',
                  (t['dataset'],t['class_id'],t['target_uid'],json.dumps(original)))
        candidates=fullnames.get(label_key(t['label']),set())
        if len(candidates)!=1:continue
        uid=next(iter(candidates));r=species[uid]
        a=c.execute('SELECT component_id FROM nodes WHERE uid=?',(t['target_uid'],)).fetchone()
        b=c.execute('SELECT component_id FROM nodes WHERE uid=?',(uid,)).fetchone()
        # Preserve the original UID when its exact concept was independently
        # corroborated; otherwise resolve the annotation to the primary scope.
        resolved=t['target_uid'] if a and a[0]==b[0] else uid
        proof={'basis':'UNIQUE_FULL_PRIMARY_CHECKLIST_LABEL_AND_DECLARED_SPECIES_CONCEPT',
               'source_version':'AviList v2025b','source_uri':r['source_uri'],
               'source_sha256':r['source_sha256'],'sequence':r['row']['Sequence'],
               'scientific_name':r['row']['Scientific_name'],'primary_uid':uid,
               'original_target_uid':c.execute('SELECT original_target_uid FROM dataset_target_history WHERE dataset=? AND class_id=?',
                                                (t['dataset'],t['class_id'])).fetchone()[0],
               'resolved_target_uid':resolved,
               'label_normalization':'case, spacing/hyphenation and grammatical possessive only; no lexical prefix guessing',
               'is_cross_source_same_concept_assertion':False}
        eid=m.evidence('Primary checklist annotation alignment',r['source_uri'],proof,'SOURCE_NATIVE_LABEL_ALIGNMENT')
        provenance=json.loads(t['provenance'] or '{}');provenance['unified_primary_alignment']=proof
        ids=json.loads(t['evidence_ids'] or '[]');ids=sorted(set(ids+[eid]))
        c.execute('UPDATE dataset_targets SET target_uid=?,decision_status=?,identity_basis=?,granularity_basis=?,evidence_ids=?,provenance=? WHERE dataset=? AND class_id=?',
                  (resolved,'VERIFIED','Primary full-label species alignment; cross-source equivalence requires independent identifier bridges',
                   'Primary ranked species concept; original record retained in dataset_target_history',json.dumps(ids),json.dumps(provenance),t['dataset'],t['class_id']))
        c.execute('INSERT OR REPLACE INTO dataset_mapping_checks VALUES (?,?,?,?,?)',
                  (t['dataset'],t['class_id'],'PRIMARY_SOURCE_CORROBORATED','Full primary species label and explicit native rank',json.dumps(proof)))
        if resolved!=t['target_uid']:
            m.change('unified_task_alignment','task',t['dataset']+':'+t['class_id'],original,{'target_uid':resolved},proof)
            counts['primary_label_target_corrections']+=1
        counts['primary_label_alignments']+=1
    # Unchanged labels are retained for source/annotation grain review, never
    # deleted from exports to increase a success rate.
    for t in c.execute("SELECT * FROM dataset_targets WHERE dataset='cub200'").fetchall():
        if not c.execute('SELECT 1 FROM dataset_mapping_checks WHERE dataset=? AND class_id=?',(t['dataset'],t['class_id'])).fetchone():
            c.execute('INSERT INTO dataset_mapping_checks VALUES (?,?,?,?,?)',
                      (t['dataset'],t['class_id'],'ANNOTATION_SCOPE_REVIEW','Primary current species label is not an unambiguous full annotation-name match; broader/older/genus scope needs documentary alignment',json.dumps({'original_target_uid':t['target_uid'],'original_label':t['label']})))
    c.commit()
    print('APPLY REAL NATIVE FIELD INTERMEDIATE TYPES',flush=True)
    counts.update(apply_refinements(m,'unified_field_refinements.jsonl'))
    if (m.inputs/'unified_role_links.jsonl').exists():
        counts.update(apply_refinements(m,'unified_role_links.jsonl'))
    for filename in ('unified_classification_projection.jsonl','unified_source_scope.jsonl','unified_navigation_completion.jsonl',
                     'unified_design_scope.jsonl','unified_breed_parents.jsonl','unified_regulatory_roles.jsonl',
                     'unified_taxonomic_scope.jsonl','unified_biological_units.jsonl','unified_root_contracts.jsonl','unified_final_role_links.jsonl'):
        if (m.inputs/filename).exists():counts.update(apply_refinements(m,filename))
    m.meta('unified_attachment_rules',{'domains':c.execute('SELECT count(DISTINCT domain_id) FROM unified_domain_rules').fetchone()[0],
        'rules':c.execute('SELECT count(*) FROM unified_domain_rules').fetchone()[0],
        'wordnet_version':'3.1','selection_table':'unified_backbone_nodes','rules_table':'unified_domain_rules'})
    counts.update(apply_display_aliases(m))
    c.commit();return dict(counts)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--reports',type=Path,required=True)
    p.add_argument('--baseline',type=Path,help='Verified protected baseline at a portable installation path; never mutated')
    p.add_argument('--apply-only',action='store_true')
    p.add_argument('--graphs-only',action='store_true',help='Resume frozen source replay already completed')
    p.add_argument('--cohorts-only',action='store_true',help='Apply newly verified native projection/source-scope cohorts then rebuild')
    p.add_argument('--completion-only',action='store_true',help='Replay complete fallback-role navigation and final verified source deltas then rebuild')
    p.add_argument('--breed-only',action='store_true',help='Replay verified source-wide breed identities then rebuild all view caches')
    p.add_argument('--final-navigation-only',action='store_true',help='Replay frozen regulatory role and corroborated breed-parent navigation, then rebuild')
    p.add_argument('--root-contracts-only',action='store_true',help='Apply individually evidenced incorrect root-parent quarantines then rebuild')
    p.add_argument('--scope-reconciliation-only',action='store_true',help='Replay exact-QID primary role corrections and complete typed role navigation, then rebuild')
    p.add_argument('--repair-extensions-only',action='store_true',help='Resume completed original 1.10 source replay; apply frozen shared/scope/living/furniture deltas and rebuild')
    p.add_argument('--repair-role-navigation-only',action='store_true',help='Apply separately frozen regenerated role navigation without repeating source repair decisions')
    a=p.parse_args()
    baseline=json.loads((a.inputs/'baseline.json').read_text())
    source=a.baseline or Path(baseline['database'])
    if not source.is_file():raise ValueError('Protected baseline is missing; supply --baseline at its verified installation path')
    if a.database.samefile(source):raise ValueError('Cannot modify protected baseline')
    with sqlite3.connect(source.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as c:
        source_meta={k:json.loads(v) for k,v in c.execute('SELECT key,value FROM metadata')}
    if source.stat().st_size!=baseline['database_bytes'] or source_meta.get('database_revision')!=baseline['database_revision']:
        raise ValueError('Protected baseline size/revision differs from the frozen source manifest')
    m=Migration(a.database,a.inputs,a.reports);m.schema()
    if a.repair_role_navigation_only:
        print(json.dumps(apply_refinements(m,'repair_role_links.jsonl'),indent=2),flush=True)
        m.meta('browse_indexes_ready',False);m.c.commit()
    elif a.repair_extensions_only:
        print(json.dumps(apply_repair_extensions(m),ensure_ascii=False,indent=2),flush=True)
    elif a.scope_reconciliation_only:
        print(json.dumps(apply_refinements(m,'unified_root_contracts.jsonl')),flush=True)
        from prepare_unified_role_links import prepare
        prepare(a.database,m.inputs/'unified_final_role_links.jsonl')
        print(json.dumps(apply_refinements(m,'unified_final_role_links.jsonl')),flush=True)
        m.meta('browse_indexes_ready',False);m.c.commit()
    elif a.root_contracts_only:
        print(json.dumps(apply_refinements(m,'unified_root_contracts.jsonl')),flush=True)
        print(json.dumps(apply_display_aliases(m)),flush=True)
        m.meta('browse_indexes_ready',False);m.c.commit()
    elif a.final_navigation_only:
        for filename in ('unified_design_scope.jsonl','unified_breed_parents.jsonl','unified_regulatory_roles.jsonl','unified_taxonomic_scope.jsonl','unified_biological_units.jsonl'):
            print(filename,json.dumps(apply_refinements(m,filename)),flush=True)
        from prepare_unified_role_links import prepare
        prepare(a.database,m.inputs/'unified_final_role_links.jsonl')
        print(json.dumps(apply_refinements(m,'unified_final_role_links.jsonl')),flush=True)
    elif a.breed_only:
        print(json.dumps(apply_breed_identities(m),indent=2),flush=True)
    elif a.completion_only:
        print(json.dumps(apply_refinements(m,'unified_navigation_completion.jsonl'),indent=2),flush=True)
    elif a.cohorts_only:
        counts={filename:apply_refinements(m,filename) for filename in
                ('unified_classification_projection.jsonl','unified_source_scope.jsonl')}
        print(json.dumps(counts,indent=2),flush=True)
    elif not a.graphs_only:
        print(json.dumps(apply(m),indent=2),flush=True)
        print(json.dumps(apply_repair_extensions(m),ensure_ascii=False,indent=2),flush=True)
    if not a.apply_only:
        result=ram_graphs(m)
        (a.reports/'graphs_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    m.c.close()

if __name__=='__main__':main()
