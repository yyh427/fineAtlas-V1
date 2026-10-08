#!/usr/bin/env python3
"""Reproduce unified domains, source identities, all labels/pairs and retention.

Output files are stage checkpoints. A summary is not an unconditional semantic
certification: unresolved source concepts and annotation grain remain visible.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas import FineAtlas
from fineatlas.semantics import role_expression
from export_text_training import DATASETS

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def domains(tree,out):
    result=[]
    for domain in tree.domains():
        name=domain['domain'];entry=tree.domain(name)
        rules=[json.loads(r[0]) for r in tree.con.execute(
            'SELECT payload FROM unified_domain_rules WHERE domain_id=? ORDER BY native_root_uid',
            (entry['domain_id'],))]
        members=[dict(r) for r in tree.con.execute('''SELECT dc.category,count(*) identities,
            sum(CASE WHEN vp.component_id IS NULL THEN 1 ELSE 0 END) no_root_witness
            FROM domain_components dc LEFT JOIN view_paths vp ON vp.component_id=dc.component_id AND vp.view=dc.view
            WHERE dc.domain_id=? AND dc.view='unified' GROUP BY dc.category''',(entry['domain_id'],))]
        roots=[]
        for rule in rules:
            root=rule['native_root_uid'];path=tree.path_result(root)
            reached=path['status'] in ('ROOT','CONNECTED')
            roots.append({'native_root_uid':root,'wordnet_anchor_uid':rule['wordnet_anchor_uid'],
                          'synset_id':rule['synset_id'],'definition':rule['definition'],
                          'attachment_relation':rule['relation'],'basis':rule['selection_basis'],
                          'status':path['status'],'path':path['path'],'root_reachable':reached})
        browser=tree.browse_children_page(name,20)
        alias_checks=[{'alias':alias,'resolved_domain':(tree.domain(alias) or {}).get('domain')}
                      for alias in domain.get('aliases',[])]
        role_checks=[]
        for role,count in tree.con.execute("SELECT role,count(*) FROM domain_members WHERE domain_id=? AND view='unified' GROUP BY role",(entry['domain_id'],)):
            page=tree.domain_page(name,limit=1,node_kind=role)
            checked={'role':role,'member_source_uids':count,'returned':len(page['items'])}
            if page['items']:
                n=page['items'][0]
                found=tree.search_page(n['label'],domain=name,node_kind=role,exact=True,limit=100)
                checked['search_contains_member_identity']=any(x['component_id']==n['component_id'] for x in found['items'])
                checked['search_truncated']=found['has_more']
                token_search=tree.search_page(n['label'],domain=name,node_kind=role,limit=100)
                checked['token_search_contains_member_identity']=any(x['component_id']==n['component_id'] for x in token_search['items'])
            role_checks.append(checked)
        result.append({'domain':name,'entry_uid':entry['entry_uid'],'roots':roots,
                       'member_census':members,'browser_status':browser['status'],
                       'alias_checks':alias_checks,'role_interface_checks':role_checks,
                       'default_page_count':len(browser['items']),
                       'pass':bool(roots) and all(r['root_reachable'] for r in roots)
                              and all(r['no_root_witness']==0 for r in members)
                              and browser['status'] in ('OK','EMPTY')
                              and all(a['resolved_domain']==name for a in alias_checks)
                              and all(r['returned']==1 and r['search_contains_member_identity'] and r['token_search_contains_member_identity'] for r in role_checks)})
        write(out/'domains.json',result)
        print('DOMAIN',name,result[-1]['pass'],flush=True)
    return {'domains':len(result),'passed':sum(r['pass'] for r in result),
            'all_domain_members_checked_by_frozen_root_witness_join':True}

def labels(database,out):
    per_view={}; examples=[]
    for view in ('strict','taxonomy','unified','membership'):
        rows=[];totals=Counter()
        with FineAtlas(database,relation_view=view) as tree:
            for ds in DATASETS:
                for t in tree.task_labels(ds):
                    uid=t['target_uid'];node=tree.node(uid);identity=tree.identity(uid)
                    path=tree.path_result(uid);state=tree.connection_status(uid)
                    peers=[]
                    for peer in identity.get('members',identity.get('representations',[])):
                        puid=peer.get('uid') if isinstance(peer,dict) else peer
                        if puid and puid!=uid:
                            peers.append({'uid':puid,'status':tree.connection_status(puid),
                                          'path_status':tree.path_result(puid)['status']})
                    row={'dataset':ds,'class_id':t['class_id'],'label':t['label'],'uid':uid,
                         'source':node['source'],'role':node['node_kind'],
                         'identity':identity,'mapping_review':t.get('mapping_review'),
                         'stored_identity_claim_verified':t.get('stored_identity_claim_verified',t['identity_verified']),
                         'identity_verified':t['identity_verified'],
                         'path':path,'state':state,'task_admission':t['task_admission'],
                         'peer_states':peers,'consistent':path['status']==state['path_status']}
                    rows.append(row);totals['labels']+=1;totals['stored_identity_claim_verified']+=row['stored_identity_claim_verified']
                    totals['identity_verified']+=t['identity_verified']
                    totals['root_reachable']+=state['root_reachable'];totals['path_state_consistent']+=row['consistent']
                    totals['hierarchy_admitted']+=t['task_admission']['usable']
                    if totals['labels']%25==0:print('LABEL',view,totals['labels'],flush=True)
            write(out/(view+'_labels.json'),rows)
        per_view[view]=dict(totals);write(out/'label_summary.json',per_view)
    with FineAtlas(database) as tree:
        pair_summaries={ds:tree.export_training(ds,out/'training'/ds) for ds in DATASETS}
        for a,b in [('1','2'),('100','101'),('3','1'),('2','3'),('77','78')]:
            x=tree.target('cub200',a);y=tree.target('cub200',b)
            index=tree.relation_reward_index('cub200')
            examples.append({'class_ids':[a,b],'labels':[x['label'],y['label']],
                             'uids':[x['target_uid'],y['target_uid']],
                             'paths':[tree.path_result(x['target_uid']),tree.path_result(y['target_uid'])],
                             'public_lca':tree.lca(x['target_uid'],y['target_uid']),
                             'public_distance':tree.distance(x['target_uid'],y['target_uid']),
                             'training_pair':index.query(a,b)})
        write(out/'cub_examples.json',examples);write(out/'pair_summary.json',pair_summaries)
    return {'views':per_view,'pairs':pair_summaries}

def structure(tree,out):
    c=tree.con;role=role_expression('n','p')
    result={}
    for table,left,right in [('edges','child_uid','parent_uid'),('entity_relations','subject_uid','object_uid')]:
        result[table+'_dangling_retained_records']=c.execute(f'''SELECT count(*) FROM {table} e
            LEFT JOIN nodes a ON a.uid=e.{left} LEFT JOIN nodes b ON b.uid=e.{right}
            WHERE a.uid IS NULL OR b.uid IS NULL''').fetchone()[0]
        result[table+'_dangling_admitted_records']=c.execute(f'''SELECT count(*) FROM {table} e
            LEFT JOIN nodes a ON a.uid=e.{left} LEFT JOIN nodes b ON b.uid=e.{right}
            WHERE e.status IN ('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE') AND (a.uid IS NULL OR b.uid IS NULL)''').fetchone()[0]
        write(out/'structure.json',result);print('STRUCTURE',table,flush=True)
    result['unrooted_classification_records']=[dict(r) for r in c.execute(f'''SELECT n.source,n.rank,{role} role,count(*) records,min(n.uid) example
        FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid LEFT JOIN view_roots vr ON vr.component_id=n.component_id AND vr.view='unified'
        WHERE n.visibility='ACTIVE' AND vr.component_id IS NULL AND {role} IN ('CLASS','BIOLOGICAL_VARIANT')
        AND (json_type(p.attributes,'$.allowed_views') IS NOT 'array' OR EXISTS(SELECT 1 FROM json_each(p.attributes,'$.allowed_views') j WHERE j.value='taxonomy'))
        GROUP BY 1,2,3 ORDER BY records DESC''')]
    result['unified_cached_statistics']=tree.metadata['usability_view_statistics']['unified']
    result['identity_role_conflicts']=[dict(r) for r in c.execute(f'''SELECT n.component_id,count(DISTINCT {role}) roles,count(*) representations,min(n.uid) example
        FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility='ACTIVE'
        GROUP BY n.component_id HAVING count(DISTINCT {role})>1''')]
    write(out/'structure.json',result);return result

def preservation(tree,baseline,out):
    c=tree.con;c.execute('ATTACH DATABASE ? AS before',(baseline.resolve().as_uri()+'?mode=ro&immutable=1',))
    result={}
    result['original_nodes_missing']=c.execute('SELECT count(*) FROM before.nodes a LEFT JOIN main.nodes b ON b.uid=a.uid WHERE b.uid IS NULL').fetchone()[0]
    result['original_source_payload_changed']=c.execute('SELECT count(*) FROM before.nodes a JOIN main.nodes b ON b.uid=a.uid WHERE a.data IS NOT b.data').fetchone()[0]
    result['original_active_nodes_removed']=c.execute("SELECT count(*) FROM before.nodes a JOIN main.nodes b ON b.uid=a.uid WHERE a.visibility='ACTIVE' AND b.visibility<>'ACTIVE'").fetchone()[0]
    write(out/'preservation.json',result);print('PRESERVATION original UID/payload/visibility',result,flush=True)
    for table,left,right in [('edges','child_uid','parent_uid'),('entity_relations','subject_uid','object_uid')]:
        result[table+'_original_records_missing_or_retargeted']=c.execute(f'''SELECT count(*) FROM before.{table} a LEFT JOIN main.{table} b ON b.id=a.id
            WHERE b.id IS NULL OR a.{left} IS NOT b.{left} OR a.{right} IS NOT b.{right} OR a.relation IS NOT b.relation OR a.data IS NOT b.data''').fetchone()[0]
        result[table+'_old_active_arc_not_preserved_or_identity_resolved']=c.execute(f'''SELECT count(*) FROM before.{table} a JOIN main.{table} b ON b.id=a.id
            JOIN nodes l ON l.uid=b.{left} JOIN nodes r ON r.uid=b.{right}
            WHERE a.status IN ('ACTIVE','TYPED_ACTIVE') AND b.status<>a.status
            AND NOT(b.status='IDENTITY_RESOLVED' AND l.component_id=r.component_id)''').fetchone()[0]
        write(out/'preservation.json',result);print('PRESERVATION',table,flush=True)
    result['all_original_task_labels_retained']=c.execute('''SELECT count(*) FROM before.dataset_targets a LEFT JOIN main.dataset_targets b
        ON a.dataset=b.dataset AND a.class_id=b.class_id WHERE b.class_id IS NULL OR b.label IS NOT a.label''').fetchone()[0]==0
    result['mapping_changes_have_original_target_history']=c.execute('''SELECT count(*) FROM before.dataset_targets a JOIN main.dataset_targets b
        ON a.dataset=b.dataset AND a.class_id=b.class_id LEFT JOIN dataset_target_history h ON h.dataset=a.dataset AND h.class_id=a.class_id
        WHERE a.target_uid<>b.target_uid AND (h.original_target_uid IS NULL OR h.original_target_uid<>a.target_uid)''').fetchone()[0]==0
    corrections=[]
    for old in c.execute("SELECT a.*,b.status current_status,n.data native_data,p.node_kind current_role FROM before.entity_relations a JOIN main.entity_relations b ON b.id=a.id JOIN nodes n ON n.uid=b.subject_uid LEFT JOIN node_profiles p ON p.uid=n.uid WHERE a.status='ACTIVE' AND b.status<>a.status AND b.status<>'IDENTITY_RESOLVED'"):
        native=json.loads(old['native_data'] or '{}')
        witnesses=[json.loads(r[0]) for r in c.execute("SELECT evidence FROM usability_changes WHERE object_type='typed' AND object_id=?",(str(old['id']),))]
        evidence=next((r for r in witnesses if r.get('basis')=='REGULATORY_CLASSIFICATION_RECORD_IS_NOT_A_PRODUCT_DESIGN'),None)
        path=tree.path_result(old['subject_uid'])
        checked=bool(old['relation']=='DESIGN_TYPE_OF' and old['current_status']=='HIERARCHY_SUPERSEDED'
                     and old['current_role']=='CLASS' and native.get('scope','').startswith('Native regulatory classification')
                     and evidence and evidence.get('definition')==native.get('definition')
                     and path['status'] in ('ROOT','CONNECTED'))
        corrections.append({'original_id':old['id'],'uid':old['subject_uid'],'original_relation':old['relation'],
                            'original_parent':old['object_uid'],'source_record_retained':True,
                            'replacement_path':path,'evidence':evidence,'verified_semantic_correction':checked})
    write(out/'corrected_source_relations.json',corrections)
    verified=sum(r['verified_semantic_correction'] for r in corrections)
    result['explicitly_verified_invalid_design_corrections']=verified
    root_corrections=[]
    for old in c.execute("SELECT a.*,b.status current_status FROM before.edges a JOIN main.edges b ON b.id=a.id WHERE a.status IN ('ACTIVE','TYPED_ACTIVE') AND b.status<>a.status AND b.status<>'IDENTITY_RESOLVED'"):
        proof=c.execute("SELECT evidence FROM usability_changes WHERE stage='source_semantic_contract' AND object_type='edge' AND object_id=? ORDER BY id DESC LIMIT 1",(str(old['id']),)).fetchone()
        proof=json.loads(proof[0]) if proof else None
        path=tree.path_result(old['child_uid'])
        checked=bool(proof and proof.get('individual_semantic_review') and proof.get('source_scope_conflict')
                     and old['current_status']=='HIERARCHY_SUPERSEDED' and path['status'] in ('ROOT','CONNECTED')
                     and proof.get('replacement_edge_ids') and all(c.execute("SELECT 1 FROM edges WHERE id=? AND child_uid=? AND status='ACTIVE'",(rid,old['child_uid'])).fetchone() for rid in proof['replacement_edge_ids']))
        root_corrections.append({'original_id':old['id'],'uid':old['child_uid'],'original_parent':old['parent_uid'],
                                 'evidence':proof,'replacement_path':path,'verified_semantic_correction':checked})
    write(out/'corrected_root_relations.json',root_corrections)
    verified_roots=sum(r['verified_semantic_correction'] for r in root_corrections)
    result['explicitly_verified_invalid_root_corrections']=verified_roots
    result['unexpected_active_relation_losses']=result['edges_old_active_arc_not_preserved_or_identity_resolved']+result['entity_relations_old_active_arc_not_preserved_or_identity_resolved']-verified-verified_roots
    result['descendant_identity_preservation_basis']='All original source UIDs, raw source payloads and original source endpoints/relations remain. Original valid arcs are retained or zero-depth identity-resolved. Explicitly documented incorrect FDA design and native root-parent arcs are quarantined with retained valid alternative paths; their old wrong ancestor/domain sets are intentionally not certified as legitimate. Focused wide-branch source UID sets are additionally checked by pagination audits.'
    zero_fields=['original_nodes_missing','original_source_payload_changed','original_active_nodes_removed',
                 'edges_original_records_missing_or_retargeted','entity_relations_original_records_missing_or_retargeted','unexpected_active_relation_losses']
    result['pass']=all(result[k]==0 for k in zero_fields) and result['all_original_task_labels_retained'] and result['mapping_changes_have_original_target_history']
    write(out/'preservation.json',result);return result

def nonfocus(tree,samples,out):
    result=[]
    for sample in json.loads(samples.read_text()):
        uid=sample['uid'];node=tree.node(uid);path=tree.path_result(uid)
        result.append({'uid':uid,'domain':sample['domain'],'source':sample['source'],
                       'original_view':sample['view'],'original_status':sample['status'],
                       'unified_status':path['status'],'preserved':node is not None,
                       'classification_or_navigation_available':path['status'] in ('ROOT','CONNECTED'),
                       'source_record':tree.source_hierarchy(uid,limit=3),
                       'sampling_scope':'Frozen nonbenchmark stratum; source semantics must be inspected separately'})
        if len(result)%100==0:print('NONFOCUS',len(result),flush=True)
    write(out/'nonfocus.json',result)
    summary={'count':len(result),'domains':len({r['domain'] for r in result}),
             'preserved':sum(r['preserved'] for r in result),
             'connected':sum(r['classification_or_navigation_available'] for r in result),
             'regressions':sum(r['original_status'] in ('ROOT','CONNECTED') and not r['classification_or_navigation_available'] for r in result),
             'semantic_all_edges_certified':False}
    write(out/'nonfocus_summary.json',summary);return summary

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--baseline',type=Path);p.add_argument('--samples',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--phase',choices=('domains','labels','structure','preservation','nonfocus'),action='append')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);summary={};start=time.monotonic()
    for phase in a.phase or ['domains','labels','structure','preservation','nonfocus']:
        with FineAtlas(a.database,relation_view='unified') as tree:
            if phase=='domains':result=domains(tree,a.output)
            elif phase=='labels':result=labels(a.database,a.output)
            elif phase=='structure':result=structure(tree,a.output)
            elif phase=='preservation':
                if not a.baseline:raise ValueError('--baseline required')
                result=preservation(tree,a.baseline,a.output)
            else:
                if not a.samples:raise ValueError('--samples required')
                result=nonfocus(tree,a.samples,a.output)
        summary[phase]=result;summary['elapsed_seconds']=time.monotonic()-start
        write(a.output/'summary.json',summary);print('PHASE COMPLETE',phase,flush=True)

if __name__=='__main__':main()
