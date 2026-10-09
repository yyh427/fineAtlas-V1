#!/usr/bin/env python3
"""Independent dynamic-domain, fixed-source and wide-branch release audit.

Raw SQL, locally declared role/relation contracts, and retained source witnesses
are compared with the public SDK and its caches. Reviewed withdrawals are
reported separately from unknown regressions; sampling is not an all-fact
scientific certification. This script never modifies either input database.
"""
from __future__ import annotations

if not __debug__:
    raise RuntimeError("Optimized Python is forbidden for mandatory structural checks")


import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

if '--installed-sdk' not in sys.argv:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
else:
    import fineatlas
    assert Path(fineatlas.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()) and 'site-packages' in Path(fineatlas.__file__).parts, 'Use the installed SDK'
from fineatlas import FineAtlas

TYPE_ROLES = {'CLASS','BIOLOGICAL_VARIANT'}
NAV_ROLES = TYPE_ROLES|{'MODEL','MODEL_FAMILY','CONFIGURATION'}
TYPED = {'INSTANCE':{'INSTANCE_OF'},'ATTRIBUTE':{'ATTRIBUTE_KIND_OF'},
         'DATASET_CATEGORY':{'DEPICTS_TYPE'},
         'MODEL':{'DESIGN_TYPE_OF','REGULATED_AS','SERIES_MEMBER_OF','NATIVE_DESIGN_PARENT'},
         'MODEL_FAMILY':{'DESIGN_TYPE_OF','NATIVE_DESIGN_PARENT'},
         'CONFIGURATION':{'CONFIGURATION_OF','CONFIGURATION_TYPE_OF','REGULATED_AS'}}
NATIVE_FIELDS = ('uid','label','source','rank','description','data','domain','domains','layer')


def write(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def connect(path):
    con=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA query_only=ON');con.execute('PRAGMA temp_store=MEMORY')
    con.execute('PRAGMA cache_size=-262144')
    return con


def role_sql(n='n',p='p'):
    # Deliberately independent of fineatlas.semantics and cached browse_nodes.
    ranks={'ORGANIZATION':['manufacturer','make'],'INSTANCE':['instance'],
           'ATTRIBUTE':['attribute','horticultural_color_class'],
           'MODEL':['model','product_model','aircraft_model','vehicle_model'],
           'MODEL_FAMILY':['model_family','series'],
           'CONFIGURATION':['model_year','configuration','model_year_configuration'],
           'UNKNOWN':['unknown','type_or_product_model'],'DATASET_CATEGORY':['dataset_category'],
           'BIOLOGICAL_VARIANT':['biological_variant']}
    cases=' '.join("WHEN '"+rank+"' THEN '"+role+"'" for role,values in ranks.items() for rank in values)
    fallback=f"CASE WHEN lower({n}.source)='wfo' AND lower({n}.rank)='series' THEN 'CLASS' ELSE CASE lower(coalesce({n}.rank,'')) {cases} ELSE 'CLASS' END END"
    return f'coalesce({p}.node_kind,{fallback})'


def basic(con,uid):
    row=con.execute('SELECT n.*,'+role_sql()+' audit_role,p.attributes FROM nodes n '
                    'LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(uid,)).fetchone()
    return dict(row) if row else None


def admitted(node):
    if not node or node['visibility']!='ACTIVE':return False
    attrs=json.loads(node.get('attributes') or '{}')
    return not isinstance(attrs.get('allowed_views'),list) or 'taxonomy' in attrs['allowed_views']


def path_errors(con,result,uid):
    errors=[]
    if result['status'] not in ('ROOT','CONNECTED'):return errors
    current=result.get('root_uid')
    for i,step in enumerate(result['path']):
        child,parent=step['uid'],step['parent_uid'];edge=step['edge'];relation=edge['relation']
        cn,pn=basic(con,child),basic(con,parent)
        if not cn or not pn:errors.append({'step':i,'reason':'DANGLING_PATH_ENDPOINT'});continue
        if current is not None and parent!=current:errors.append({'step':i,'reason':'DISCONTIGUOUS_SOURCE_UID_PATH'})
        current=child
        if relation=='SAME_CONCEPT':
            row=con.execute("SELECT * FROM bridges WHERE id=?",(edge['id'],)).fetchone()
            if not row or row['status']!='ACTIVE' or row['relation']!='SAME_CONCEPT' or {row['left_uid'],row['right_uid']}!={child,parent} or cn['component_id']!=pn['component_id']:
                errors.append({'step':i,'reason':'UNGROUNDED_IDENTITY_STEP'})
            continue
        storage='entity_relations' if edge.get('terminal_connection') or 'subject_uid' in edge else 'edges'
        row=con.execute('SELECT * FROM '+storage+' WHERE id=?',(edge['id'],)).fetchone()
        cols=('subject_uid','object_uid') if storage=='entity_relations' else ('child_uid','parent_uid')
        if not row or (row[cols[0]],row[cols[1]],row['relation'])!=(child,parent,relation):
            errors.append({'step':i,'reason':'MISSING_NATIVE_PATH_ASSERTION'});continue
        if not admitted(cn) or not admitted(pn):errors.append({'step':i,'reason':'SOURCE_OR_VISIBILITY_NOT_ADMITTED'})
        if storage=='edges':
            legal=((row['status'] in ('ACTIVE','BACKBONE_ACTIVE') and relation=='IS_A') or
                   (row['status']=='TYPED_ACTIVE' and relation in ('TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT')))
            legal &= cn['audit_role'] in TYPE_ROLES and pn['audit_role'] in TYPE_ROLES
        else:
            legal=row['status']=='ACTIVE' and relation in TYPED.get(cn['audit_role'],set()) and pn['audit_role'] in NAV_ROLES
        if not legal:errors.append({'step':i,'reason':'ILLEGAL_UNIFIED_ROLE_OR_RELATION','storage':storage,'record_id':row['id']})
        if not row['source']:errors.append({'step':i,'reason':'MISSING_PATH_SOURCE'})
    if result['path'] and current!=uid:errors.append({'reason':'PATH_DOES_NOT_END_AT_REQUESTED_SOURCE_UID'})
    return errors


def withdrawal_evidence(con,before_path):
    """A retired old witness needs its exact source adjudication ledger entry."""
    reasons=[]
    for step in before_path.get('path',[]):
        edge=step['edge'];relation=edge['relation']
        storage='bridges' if relation=='SAME_CONCEPT' else ('entity_relations' if edge.get('terminal_connection') or 'subject_uid' in edge else 'edges')
        row=con.execute('SELECT * FROM '+storage+' WHERE id=?',(edge['id'],)).fetchone()
        active=('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE') if storage=='edges' else ('ACTIVE',)
        if not row or row['status'] in active:continue
        columns=('left_uid','right_uid') if storage=='bridges' else (('subject_uid','object_uid') if storage=='entity_relations' else ('child_uid','parent_uid'))
        endpoints={step['uid'],step['parent_uid']}
        if {row[columns[0]],row[columns[1]]}!=endpoints or row['relation']!=relation:continue
        ledgers=con.execute('SELECT stage,object_type,object_id,before_json,after_json,evidence '
                            'FROM usability_changes WHERE object_id=? ORDER BY id',(str(edge['id']),))
        for ledger in ledgers:
            prior=json.loads(ledger['before_json']);proof=json.loads(ledger['evidence'])
            if prior.get(columns[0])!=row[columns[0]] or prior.get(columns[1])!=row[columns[1]] or prior.get('relation')!=relation:
                continue
            if not isinstance(proof,dict) or not proof.get('basis'):continue
            reasons.append({'storage':storage,'record_id':row['id'],'new_status':row['status'],
                            'stage':ledger['stage'],'basis':proof['basis'],
                            'disposition_category':proof.get('disposition_category'),
                            'scientific_identity_is_now_confirmed':False})
            break
    return reasons


def role_change_evidence(con,uid,old_role,new_role):
    row=con.execute('SELECT canonical_role,status,evidence_id FROM normalization_roles WHERE uid=?',(uid,)).fetchone()
    if not row or row['canonical_role']!=new_role or row['status']!='VERIFIED':return None
    proof=con.execute('SELECT payload FROM evidence WHERE evidence_id=?',(row['evidence_id'],)).fetchone()
    if not proof:return None
    payload=json.loads(proof[0])
    if not isinstance(payload,dict) or not payload.get('basis'):return None
    return {'uid':uid,'old_role':old_role,'new_role':new_role,'evidence_id':row['evidence_id'],'basis':payload['basis']}


def classify_sample(con,before,after,old_role,new_role,uid):
    old_ok=before['status'] in ('ROOT','CONNECTED');new_ok=after['status'] in ('ROOT','CONNECTED')
    role_proof=role_change_evidence(con,uid,old_role,new_role) if old_role!=new_role else None
    if old_role!=new_role and role_proof is None:return 'UNKNOWN_ROLE_REGRESSION',[]
    if old_ok and not new_ok:
        proofs=withdrawal_evidence(con,before)
        if proofs or role_proof:return 'EXPLAINED_REVIEW_WITHDRAWAL',proofs+([role_proof] if role_proof else [])
        return 'UNKNOWN_REACHABILITY_REGRESSION',[]
    if not old_ok and new_ok:return 'ROOT_PATH_GAIN',[]
    if old_role!=new_role:return 'EVIDENCED_ROLE_CHANGE',[role_proof]
    if before.get('path')!=after.get('path'):return 'VALID_ROUTE_CHANGED',[]
    return 'UNCHANGED',[]


def raw_branch_rows(con):
    """Full independent unified arc census, not cache counts or SDK parents."""
    typed=' OR '.join("(ch.role='"+role+"' AND e.relation IN ("+','.join("'"+r+"'" for r in sorted(rels))+'))'
                      for role,rels in TYPED.items())
    query='''WITH admitted AS MATERIALIZED (
      SELECT n.uid,n.component_id,'''+role_sql()+''' role FROM nodes n
      LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility='ACTIVE'
      AND (p.uid IS NULL OR json_type(p.attributes,'$.allowed_views') IS NOT 'array'
        OR EXISTS(SELECT 1 FROM json_each(p.attributes,'$.allowed_views') v WHERE v.value='taxonomy'))),
    arcs AS (
      SELECT pa.component_id parent_component,ch.component_id child_component,ch.role,e.relation
      FROM edges e JOIN admitted ch ON ch.uid=e.child_uid JOIN admitted pa ON pa.uid=e.parent_uid
      WHERE ch.role IN ('CLASS','BIOLOGICAL_VARIANT') AND pa.role IN ('CLASS','BIOLOGICAL_VARIANT')
      AND ((e.status IN ('ACTIVE','BACKBONE_ACTIVE') AND e.relation='IS_A') OR
        (e.status='TYPED_ACTIVE' AND e.relation IN ('TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT')))
      UNION ALL
      SELECT pa.component_id,ch.component_id,ch.role,e.relation FROM entity_relations e
      JOIN admitted ch ON ch.uid=e.subject_uid JOIN admitted pa ON pa.uid=e.object_uid
      WHERE e.status='ACTIVE' AND pa.role IN ('CLASS','BIOLOGICAL_VARIANT','MODEL','MODEL_FAMILY','CONFIGURATION')
      AND ('''+typed+'''))
    SELECT parent_component,role,relation,count(DISTINCT child_component) concept_count,
      count(*) source_arc_count FROM arcs WHERE parent_component<>child_component
      GROUP BY parent_component,role,relation ORDER BY parent_component,role,relation'''
    return con.execute(query)


def census(con):
    dangling={}
    for table,left,right,status in [('edges','child_uid','parent_uid',"IN ('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE')"),
                                  ('entity_relations','subject_uid','object_uid',"='ACTIVE'"),
                                  ('bridges','left_uid','right_uid',"='ACTIVE'")]:
        dangling[table]=con.execute(f'SELECT count(*) FROM {table} e LEFT JOIN nodes a ON a.uid=e.{left} '
                                   f'LEFT JOIN nodes b ON b.uid=e.{right} WHERE e.status {status} AND (a.uid IS NULL OR b.uid IS NULL)').fetchone()[0]
    conflicts=[dict(r) for r in con.execute('SELECT n.component_id,count(DISTINCT '+role_sql()+') role_count,min(n.uid) representative_uid '
                "FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility='ACTIVE' GROUP BY n.component_id HAVING role_count>1")]
    return {'active_source_dangling':dangling,'active_role_conflicts':conflicts,
            'role_counts':dict(con.execute('SELECT '+role_sql()+',count(*) FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid '
                                          "WHERE n.visibility='ACTIVE' GROUP BY 1"))}


def audit(baseline,database,inventory,output):
    started=time.monotonic();output=Path(output);output.mkdir(parents=True,exist_ok=True)
    frozen=json.loads(Path(inventory).read_text());failures=[];baseline=Path(baseline);database=Path(database)
    before=connect(baseline);after=connect(database)
    phases={}
    def progress(phase,**values):
        phases[phase]=values;write(output/'progress.json',{'phases':phases,'seconds':time.monotonic()-started})
        print(phase,values,flush=True)
    old_census=census(before);progress('baseline_census',conflicts=len(old_census['active_role_conflicts']))
    new_census=census(after);progress('candidate_census',conflicts=len(new_census['active_role_conflicts']))
    for table,count in new_census['active_source_dangling'].items():
        if count:failures.append({'check':'DANGLING_ACTIVE_SOURCE','table':table,'count':count})
    write(output/'source_role_census.json',{'baseline':old_census,'candidate':new_census})
    old_conflicts={r['component_id'] for r in old_census['active_role_conflicts']}
    new_conflicts=[]
    for conflict in new_census['active_role_conflicts']:
        members=[r[0] for r in after.execute('SELECT uid FROM nodes WHERE component_id=?',(conflict['component_id'],))]
        old_components={row[0] for uid in members for row in before.execute('SELECT component_id FROM nodes WHERE uid=?',(uid,))}
        if not (old_components & old_conflicts):new_conflicts.append(conflict)
    if new_conflicts:failures.append({'check':'NEW_IDENTITY_ROLE_CONFLICTS','count':len(new_conflicts),'components':new_conflicts})
    aliases,portals,samples=[],[],[]
    with FineAtlas(baseline,relation_view='unified') as old,FineAtlas(database,relation_view='unified') as tree:
        domains=list(after.execute('SELECT * FROM domain_registry ORDER BY domain_id'))
        old_ids={r['domain_id'] for r in frozen['domains']}
        if not old_ids <= {r['domain_id'] for r in domains}:failures.append({'check':'DOMAIN_ENTRY_LOST'})
        raw_roles=list(after.execute("SELECT domain_id,role,count(*) n FROM domain_members WHERE view='unified' GROUP BY domain_id,role"))
        role_by_domain=defaultdict(list)
        for row in raw_roles:role_by_domain[row['domain_id']].append(row)
        for domain in domains:
            domain_id,name=domain['domain_id'],domain['canonical_name']
            for row in after.execute('SELECT alias FROM domain_aliases WHERE domain_id=? ORDER BY alias',(domain_id,)):
                alias=row[0];resolved=tree.domain(alias)
                ok=bool(resolved and resolved['domain_id']==domain_id)
                aliases.append({'domain':name,'alias':alias,'language':'zh' if re.search(r'[\u3400-\u9fff]',alias) else 'other',
                                'resolved_to_declared_portal':ok})
                if not ok:failures.append({'check':'DOMAIN_ALIAS_NOT_RESOLVED','alias':alias,'domain':name})
                elif [n['uid'] for n in tree.domain_page(alias,1)['items']] != [n['uid'] for n in tree.domain_page(name,1)['items']]:
                    failures.append({'check':'DOMAIN_ALIAS_BROWSE_DIFFERS','alias':alias,'domain':name})
            for role_row in role_by_domain[domain_id]:
                role=role_row['role'];tick=time.monotonic()
                page=tree.domain_page(name,3,node_kind=role)
                expected=[r[0] for r in after.execute("SELECT uid FROM domain_members WHERE domain_id=? AND view='unified' AND role=? ORDER BY uid LIMIT 3",(domain_id,role))]
                actual=[n['uid'] for n in page['items']]
                ok=actual==expected and all(basic(after,n['uid'])['audit_role']==role for n in page['items'])
                next_page=tree.domain_page(name,3,node_kind=role,cursor=page['next_cursor']) if page['has_more'] else None
                if next_page and actual:
                    next_expected=[r[0] for r in after.execute("SELECT uid FROM domain_members WHERE domain_id=? AND view='unified' AND role=? AND uid>? ORDER BY uid LIMIT 3",(domain_id,role,actual[-1]))]
                    ok &= [n['uid'] for n in next_page['items']]==next_expected
                if role=='INSTANCE':ok &= [n['uid'] for n in tree.domain_instances(name,3)['items']]==actual
                portals.append({'domain':name,'role':role,'declared_source_members':role_row['n'],'first_page':actual,
                                'page_and_instance_contract':ok,'seconds':time.monotonic()-tick})
                if not ok:failures.append({'check':'DOMAIN_ROLE_PAGE_DISAGREES_WITH_SQL','domain':name,'role':role})
            progress('portals',completed=len({r['domain'] for r in portals}),domains=len(domains),role_pages=len(portals))
        for number,sample in enumerate(frozen['fixed_nonfocus_samples'],1):
            uid=sample['uid'];bn,an=basic(before,uid),basic(after,uid)
            if not bn or not an:
                failures.append({'check':'FIXED_SOURCE_UID_LOST','uid':uid});continue
            preserved=all(bn.get(k)==an.get(k) for k in NATIVE_FIELDS)
            try:
                bpath=old.path_result(uid);apath=tree.path_result(uid);state=tree.connection_status(uid)
            except (RuntimeError,ValueError,sqlite3.DatabaseError) as exc:
                failures.append({'check':'FIXED_PATH_EXCEPTION','uid':uid,'error':str(exc)})
                samples.append({'uid':uid,'domain_id':sample['domain_id'],'change_classification':'PATH_EXCEPTION','path_errors':[str(exc)]})
                continue
            errors=path_errors(after,apath,uid)
            if state.get('root_reachable')!=(apath['status'] in ('ROOT','CONNECTED')):errors.append({'reason':'PUBLIC_PATH_STATE_INCONSISTENT'})
            classification,evidence=classify_sample(after,bpath,apath,bn['audit_role'],an['audit_role'],uid)
            if not preserved:errors.append({'reason':'NATIVE_SOURCE_CONTENT_CHANGED'})
            if classification.startswith('UNKNOWN_'):errors.append({'reason':classification})
            rows=after.execute("SELECT role FROM domain_members WHERE domain_id=? AND view='unified' AND uid=?",(sample['domain_id'],uid)).fetchall()
            still_member=any(row['role']==an['audit_role'] for row in rows)
            # Membership loss requires an exact adjudicated old path witness,
            # not an arbitrary listing of engineering source namespaces.
            if not still_member and not (classification=='EXPLAINED_REVIEW_WITHDRAWAL' or evidence):
                errors.append({'reason':'UNEXPLAINED_DOMAIN_MEMBERSHIP_LOSS'})
            name_search=None
            if still_member:
                domain=next(r['canonical_name'] for r in domains if r['domain_id']==sample['domain_id'])
                cursor=None;found=False;pages=0
                while pages<20:
                    page=tree.search_page(an['label'],100,domain=domain,node_kind=an['audit_role'],exact=True,cursor=cursor)
                    pages+=1;found |= any(n['uid']==uid for n in page['items'])
                    cursor=page.get('next_cursor')
                    if found or not cursor:break
                name_search={'query':an['label'],'found_original_uid':found,'pages':pages,'limit_reached':bool(cursor and not found)}
                if not found:errors.append({'reason':'SCOPED_NAME_SEARCH_MISSING_OR_QUERY_LIMIT','search':name_search})
            record={'uid':uid,'domain_id':sample['domain_id'],'source':an['source'],'native_payload_preserved':preserved,
                    'before_role':bn['audit_role'],'after_role':an['audit_role'],'before_status':bpath['status'],
                    'after_status':apath['status'],'change_classification':classification,'review_evidence':evidence,
                    'current_domain_member':still_member,'path_errors':errors,
                    'scoped_name_search':name_search,
                    'path_relations':[s['edge']['relation'] for s in apath['path']]}
            samples.append(record)
            if errors:failures.append({'check':'FIXED_NONFOCUS_SAMPLE','uid':uid,'errors':errors})
            if number%100==0:progress('fixed_samples',checked=number,total=len(frozen['fixed_nonfocus_samples']))
        write(output/'fixed_nonfocus_samples.json',samples)
        write(output/'domain_alias_checks.json',aliases);write(output/'domain_role_pages.json',portals)
        cached={(r[0],r[1],r[2]):(r[3],r[4]) for r in after.execute("SELECT parent_component,role,relation,concept_count,source_arc_count FROM browse_link_counts WHERE view='unified'")}
        baseline_counts={(r['parent_component'],r['role'],r['relation']):(r['concept_count'],r['source_arc_count'])
                         for r in frozen['all_branch_role_relation_counts']}
        wide=[];branch_count=0;cache_mismatches=0
        with gzip.open(output/'all_branch_counts.jsonl.gz','wt',encoding='utf-8') as stream:
            for row in raw_branch_rows(after):
                record=dict(row);key=(row['parent_component'],row['role'],row['relation']);counts=(row['concept_count'],row['source_arc_count'])
                branch_count+=1;stream.write(json.dumps(record,ensure_ascii=False)+'\n')
                if cached.pop(key,None)!=counts:
                    cache_mismatches+=1
                    if cache_mismatches<=30:failures.append({'check':'RAW_BRANCH_COUNT_DIFFERS_FROM_CACHE',**record})
                if row['concept_count']<1000:continue
                parent=after.execute("SELECT uid,label,source,rank FROM nodes WHERE component_id=? AND visibility='ACTIVE' ORDER BY uid LIMIT 1",(row['parent_component'],)).fetchone()
                if not parent:failures.append({'check':'WIDE_PARENT_MISSING',**record});continue
                uid=parent['uid'];tick=time.monotonic()
                page=tree.browse_children_page(uid,3,node_kind=row['role'],relation=row['relation'],include_coarse=True)
                api_ok=page['status']=='OK' and len(page['items'])<=3
                if not api_ok:failures.append({'check':'WIDE_BRANCH_PUBLIC_BROWSE_FAILURE','uid':uid,'status':page['status']})
                finer=after.execute("SELECT count(*) FROM browse_preferences WHERE view='unified' AND parent_component=? AND role=? AND relation=?",key).fetchone()[0]
                facets=[dict(r) for r in after.execute("SELECT f.facet,count(DISTINCT f.component_id) concepts,count(DISTINCT f.value) values_count FROM browse_links b JOIN browse_facets f ON f.component_id=b.child_component WHERE b.view='unified' AND b.parent_component=? AND b.role=? AND b.relation=? AND f.facet<>'source' GROUP BY f.facet",key)]
                old_counts=baseline_counts.get(key)
                # Source UID, not representative component ID, binds baseline
                # when engineering identity splits changed a parent partition.
                old_parent=basic(before,uid)
                if old_parent:old_counts=baseline_counts.get((old_parent['component_id'],row['role'],row['relation']),old_counts)
                old_finer=before.execute("SELECT count(*) FROM browse_preferences WHERE view='unified' AND parent_component=? AND role=? AND relation=?",
                                         (old_parent['component_id'],row['role'],row['relation'])).fetchone()[0] if old_parent else 0
                intermediate_count=after.execute("SELECT count(DISTINCT via_component) FROM browse_preferences WHERE view='unified' AND parent_component=? AND role=? AND relation=?",key).fetchone()[0]
                intermediate_examples=[]
                for via in after.execute("SELECT DISTINCT via_component FROM browse_preferences WHERE view='unified' AND parent_component=? AND role=? AND relation=? ORDER BY via_component LIMIT 10",key):
                    representative=after.execute('SELECT n.uid,n.label,n.source,'+role_sql()+" role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.component_id=? AND n.visibility='ACTIVE' ORDER BY n.uid LIMIT 1",(via[0],)).fetchone()
                    if representative:intermediate_examples.append(dict(representative))
                interpretation=('RETAINED_INSTANCE_COLLECTION_WITH_FACET_PAGING' if row['role']=='INSTANCE' else
                                'EXISTING_EVIDENCED_INTERMEDIATE_PATHS_AVAILABLE' if finer else
                                'SOURCE_CATALOGUE_OR_FACET_BROWSING_ONLY' if facets else
                                'NO_ADDITIONAL_VERIFIED_MIDDLE_LAYER; TRUE_WIDE_SCOPE_RETAINED')
                wide.append({**record,'parent':dict(parent),'baseline_counts':old_counts,
                             'existing_preferred_finer_routes':finer,'baseline_preferred_finer_routes':old_finer,
                             'preferred_finer_route_delta':finer-old_finer,
                             'real_intermediate_components':intermediate_count,'intermediate_examples':intermediate_examples,
                             'preferred_route_delta_alone_is_new_knowledge':False,
                             'facets':facets,'interpretation':interpretation,
                             'public_browse_ok':api_ok,'first_page_seconds':time.monotonic()-tick,
                             'organization_or_paging_counts_as_semantic_depth':False})
                if len(wide)%25==0:progress('wide_branches',checked=len(wide),raw_branch_rows=branch_count)
        if cached:failures.append({'check':'CACHE_BRANCHES_NOT_IN_RAW_CENSUS','count':len(cached)})
        write(output/'wide_branches.json',wide)
    before.close();after.close()
    summary={'schema':'FINEATLAS_INDEPENDENT_STRUCTURE_LIBRARY_AUDIT_V1','pass':not failures,
             'baseline':str(baseline),'database':str(database),'inventory_sha256':hashlib.sha256(Path(inventory).read_bytes()).hexdigest(),
             'domain_entries':len(domains),'baseline_domain_entries':frozen['domain_count'],
             'portal_role_pages':len(portals),'domain_aliases_checked':len(aliases),
             'chinese_domain_aliases_checked':sum(r['language']=='zh' for r in aliases),
             'fixed_nonfocus_samples':len(samples),'sample_changes':dict(Counter(r['change_classification'] for r in samples)),
             'all_role_relation_branches_raw_scanned':branch_count,'raw_cache_mismatches':cache_mismatches,
             'wide_role_relation_branches':len(wide),'failure_count':len(failures),'failures':failures,
             'active_role_conflicts_before':len(old_census['active_role_conflicts']),
             'active_role_conflicts_after':len(new_census['active_role_conflicts']),
             'new_identity_role_conflicts':len(new_conflicts),
             'scope':'Full stored structural census, independent role/relation branch counts, dynamic portals and frozen stratified source paths; does not certify all scientific or commercial semantic facts',
             'explained_review_withdrawals_are_not_quality_gains':True,'seconds':time.monotonic()-started}
    write(output/'summary.json',summary)
    print(json.dumps({k:summary[k] for k in ('pass','domain_entries','fixed_nonfocus_samples','all_role_relation_branches_raw_scanned','wide_role_relation_branches','failure_count','seconds')},ensure_ascii=False),flush=True)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline','database','inventory','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--installed-sdk',action='store_true')
    args=parser.parse_args();result=audit(args.baseline,args.database,args.inventory,args.output)
    if not result['pass']:raise SystemExit(1)


if __name__=='__main__':main()
