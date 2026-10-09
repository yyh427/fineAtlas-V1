#!/usr/bin/env python3
"""Independent read-only SQL and public-API acceptance of CUB version scopes.

No migration adapter, builder predicate, or private SDK admission judge is
imported. The complete 200-label ledger and frozen native containment witnesses
are checked, including the unchanged original author targets and identities.
"""
from __future__ import annotations

if not __debug__:
    raise RuntimeError('Independent biological acceptance refuses optimized Python')

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

SCHEMA='FINEATLAS_CUB_ANNOTATION_VERSION_SCOPE_V1'
STAGE='v1.11-cub-author-taxonomic-version-scope'
SOURCE='Caltech-UCSD Birds author metadata; taxonomic-version scope review'
META_KEY='cub_annotation_version_scope_sha256'


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def require(ok,message):
    if not ok:
        raise ValueError(message)


def locate(c,table,locator):
    keys={'entity_relations':('subject_uid','object_uid','relation','source'),
          'edges':('child_uid','parent_uid','relation','source','source_relation','layer')}[table]
    rows=list(c.execute('SELECT * FROM '+table+' WHERE '+' AND '.join(k+'=?' for k in keys),
                        tuple(locator[k] for k in keys)))
    require(len(rows)==1,'Exact frozen source assertion multiplicity differs: '+table)
    return dict(rows[0])


def path_witness_sql(c,result):
    for step in result.get('path',[]):
        edge=step['edge'];relation=edge['relation']
        require(relation in {'IS_A','TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT','DEPICTS_TYPE','SAME_CONCEPT'},
                'Unexpected relation entered biological annotation path')
        if 'subject_uid' in edge:
            row=c.execute('SELECT * FROM entity_relations WHERE id=?',(edge['id'],)).fetchone()
            require(row is not None and row['status']=='ACTIVE' and all(row[k]==edge[k] for k in ('subject_uid','object_uid','relation','source')),
                    'Public typed path differs from actual SQL source claim')
            require(bool(row['evidence_id']) and c.execute('SELECT 1 FROM evidence WHERE evidence_id=?',(row['evidence_id'],)).fetchone() is not None,
                    'Public typed path lacks actual source evidence')
        elif 'child_uid' in edge:
            row=c.execute('SELECT * FROM edges WHERE id=?',(edge['id'],)).fetchone()
            require(row is not None and row['status'] in ('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE') and all(row[k]==edge[k] for k in ('child_uid','parent_uid','relation','source')),
                    'Public taxonomy path differs from actual SQL assertion')
        elif 'left_uid' in edge:
            row=c.execute('SELECT * FROM bridges WHERE id=?',(edge['id'],)).fetchone()
            require(row is not None and row['status']=='ACTIVE' and relation=='SAME_CONCEPT'
                    and all(row[k]==edge[k] for k in ('left_uid','right_uid','relation','source')),
                    'Public identity witness differs from actual bridge')
            left=c.execute('SELECT component_id FROM nodes WHERE uid=?',(row['left_uid'],)).fetchone()[0]
            right=c.execute('SELECT component_id FROM nodes WHERE uid=?',(row['right_uid'],)).fetchone()[0]
            proof=json.loads(row['data'])
            require(left==right and bool(proof.get('evidence_ids')) and all(c.execute('SELECT 1 FROM evidence WHERE evidence_id=?',(e,)).fetchone() is not None for e in proof['evidence_ids']),
                    'Unproven or uncontracted identity bridge entered path')
        else:
            raise ValueError('Unaccounted path witness')


def audit_identity_scope(c,inputs):
    """Check frozen exact identity extent delta using actual rows, not adapter code."""
    path=inputs/'structure_biology_identity_scope.json'
    require(path.exists(),'Frozen biological identity extent input missing')
    payload=json.loads(path.read_text())
    require(payload['schema']=='FINEATLAS_BIOLOGY_IDENTITY_SCOPE_V1'
            and payload['stage']=='v1.11-biological-taxonomic-identity-extent',
            'Unknown biological identity extent contract')
    fingerprint=digest(payload)
    stored=c.execute("SELECT value FROM metadata WHERE key='biology_identity_scope_input_sha256'").fetchone()
    require(stored is not None and json.loads(stored[0])==fingerprint,'Actual biological identity extent fingerprint differs')
    groups=payload['reviewed_identity_groups'];repairs=payload['repairs']
    require(len(groups)==payload['reviewed_cub_label_identity_groups']==12
            and len({r['class_id'] for r in groups})==12
            and len(repairs)==payload['proven_identity_scope_repairs'],
            'Incomplete scientific identity extent cohort')
    repair_by={r['before_bridge']['id']:r for r in repairs}
    checked=set();exceptions={};cases=[]
    bridge_columns={r[1] for r in c.execute('PRAGMA table_info(bridges)')}
    for group in groups:
        for before in group['actual_active_bridges']:
            bid=before['id'];require(bid not in checked,'Scientific bridge counted twice');checked.add(bid)
            rows=list(c.execute('SELECT * FROM bridges WHERE left_uid=? AND right_uid=? AND relation=? AND source=?',
                        tuple(before[k] for k in ('left_uid','right_uid','relation','source'))))
            require(len(rows)==1,'Frozen scientific identity source bridge multiplicity changed')
            actual=dict(rows[0]);want={k:before[k] for k in bridge_columns if k!='id'}
            if bid in repair_by:
                want['status']='GRAIN_REJECTED';want['reason']=repair_by[bid]['proof']['basis']
            require({k:v for k,v in actual.items() if k!='id'}==want,'Unintended scientific identity assertion change')
            for ev in before['actual_evidence_records']:
                row=c.execute('SELECT * FROM evidence WHERE evidence_id=?',(ev['evidence_id'],)).fetchone()
                require(row is not None and dict(row)==ev
                        and hashlib.sha256(row['payload'].encode()).hexdigest()==row['payload_sha256'],
                        'Original scientific identity proof was lost or altered')
    require(len(checked)==payload['actual_active_bridges_reviewed']==17,
            'Incomplete original seventeen scientific identity sources')
    for repair in repairs:
        before=repair['before_bridge'];proof=repair['proof'];loc=repair['locator']
        source_hash=hashlib.sha256(json.dumps({k:v for k,v in before.items() if k not in {'id','status','reason'}},sort_keys=True).encode()).hexdigest()
        require(source_hash==loc['content_sha256'] and before['id'] in checked
                and proof['individual_semantic_review'] is True and proof['source_scope_conflict'] is True,
                'Identity rejection lacks exact reviewed original source assertion')
        narrow=proof['modern_narrow_species_record'];other=proof['modern_excluded_species_record']
        require(narrow['Taxon_rank']==other['Taxon_rank']=='species'
                and other['Scientific_name'].split()[1] in narrow['Decision_summary']
                and narrow['Scientific_name']!=other['Scientific_name'],
                'Modern primary scope distinction lacks positive source decision')
        for frozen in proof['retained_nodes']:
            row=c.execute('SELECT uid,label,source,rank,data,description,visibility FROM nodes WHERE uid=?',(frozen['uid'],)).fetchone()
            require(row is not None and dict(row)==frozen,'Scientific entity/source/rank/visibility changed during identity separation')
        witness=proof['native_parent_witness']
        actual=locate(c,'edges',witness)
        require(actual['status']=='ACTIVE' and actual['facet_family']=='TAXONOMIC_LINEAGE'
                and digest({k:v for k,v in actual.items() if k!='id'})==proof['native_parent_witness_sha256'],
                'Original positive native taxonomic inclusion witness lost')
        size=proof['scope_size_proof']
        for field,parent,source,countfield in (
             ('old_native_direct_children',proof['historical_scope_uid'],'ott','old_native_direct_child_count'),
             ('modern_narrow_direct_children','avilist:'+narrow['Scientific_name'].lower(),'avilist','modern_narrow_direct_child_count')):
            rows=[dict(r) for r in c.execute("SELECT e.*,n.label,n.rank FROM edges e JOIN nodes n ON n.uid=e.child_uid WHERE e.parent_uid=? AND e.source=? AND e.status='ACTIVE'",(parent,source))]
            strip=lambda rs:sorted(canonical({k:v for k,v in r.items() if k!='id'}) for r in rs)
            require(len(rows)==size[countfield] and strip(rows)==strip(size[field]),'Frozen true native extent footprint changed')
        require(any(r['child_uid']==proof['native_included_taxon_uid'] for r in size['old_native_direct_children'])
                and not any(r['child_uid']==proof['excluded_modern_taxon_uid'] for r in size['modern_narrow_direct_children']),
                'Positive included old taxon is not separately excluded from modern native extent')
        actual_parts=[];component_ids=set()
        for part in repair['expected_partitions']:
            ids={c.execute('SELECT component_id FROM nodes WHERE uid=?',(u,)).fetchone()[0] for u in part}
            require(len(ids)==1,'Equal-extent retained peer partition was mechanically split')
            comp=next(iter(ids));members={r[0] for r in c.execute('SELECT uid FROM nodes WHERE component_id=?',(comp,))}
            require(members==set(part),'False identity contraction or unapproved new identity merge remains')
            component_ids.add(comp);actual_parts.append(sorted(part))
            for uid in part:exceptions[uid]=set(part)
        require(len(component_ids)==len(actual_parts)
                and set().union(*(set(p) for p in actual_parts))==set(repair['prior_component_members']),
                'Exact scientific scope partition lost original members')
        histories=list(c.execute('SELECT before_json,after_json,evidence FROM usability_changes WHERE stage=? AND object_type=?',
                     (payload['stage'],'scientific_identity_scope_review')))
        matches=[r for r in histories if json.loads(r['before_json'])==before]
        require(len(matches)==1 and json.loads(matches[0]['evidence'])==proof
                and json.loads(matches[0]['after_json'])['status']=='GRAIN_REJECTED',
                'Exact original scientific bridge or complete extent proof history missing')
        cases.append({'original_bridge_id':before['id'],'original_source_content_sha256':source_hash,
                      'partitions':actual_parts,'native_parent_preserved':True,'source_entities_preserved':True,'pass':True})
    return {'input_sha256':fingerprint,'input_file_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'scientific_identity_scope_cases_checked':len(groups),'scientific_identity_bridges_checked':len(checked),
            'scientific_identity_scope_splits_checked':len(cases),'cases':cases,'pass':True},exceptions


def run(database,inputs,output,*,installed_sdk=False,sql_only=False):
    start=time.monotonic();output.mkdir(parents=True,exist_ok=True)
    payload_path=inputs/'cub_annotation_version_scope.json'
    ledger_path=inputs/'all_200_version_scope_ledger.json'
    payload=json.loads(payload_path.read_text());ledger=json.loads(ledger_path.read_text())
    require(payload['schema']==SCHEMA and payload['stage']==STAGE,'Unexpected version-scope contract')
    require(len(ledger)==200 and len({r['class_id'] for r in ledger})==200
            and {r['class_id'] for r in ledger}=={str(i) for i in range(1,201)}
            and digest(ledger)==payload['all_200_ledger_sha256'],'Complete independent 200-label ledger hash/cohort')
    fingerprint=digest(payload)
    c=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');c.execute('PRAGMA temp_store=MEMORY')
    stored=c.execute('SELECT value FROM metadata WHERE key=?',(META_KEY,)).fetchone()
    require(stored is not None and json.loads(stored[0])==fingerprint,'Applied delta input fingerprint differs')
    identity_audit,identity_exceptions=audit_identity_scope(c,inputs)
    delta={(r['dataset'],r['class_id']):r for r in payload['mapping_reviews']}
    require(len(delta)==payload['new_label_scope_reviews'],'Duplicate or incomplete review cases')
    allcases=[];peeruids=set()
    for item in ledger:
        key=(item['dataset'],item['class_id'])
        current=c.execute('SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?',key).fetchone()
        require(current is not None and dict(current)==item['prior_target'],'Original world target/label changed: '+':'.join(key))
        check=dict(c.execute('SELECT * FROM dataset_mapping_checks WHERE dataset=? AND class_id=?',key).fetchone())
        if key not in delta:
            require(check==item['prior_mapping_check'],'Unintended review change outside 12 cases')
        for peer in item['world_entity_peer_records']:
            row=c.execute('SELECT uid,label,source,rank,data,visibility FROM nodes WHERE uid=?',(peer['uid'],)).fetchone()
            require(row is not None and dict(row)==peer,'Original world entity raw/rank/visibility changed: '+peer['uid'])
            peeruids.add(peer['uid'])
        targetnode=c.execute('SELECT component_id FROM nodes WHERE uid=?',(item['prior_target']['target_uid'],)).fetchone()
        peers={r[0] for r in c.execute('SELECT uid FROM nodes WHERE component_id=?',(targetnode[0],))}
        priorpeers={r['uid'] for r in item['world_entity_peer_records']}
        wantpeers=identity_exceptions.get(item['prior_target']['target_uid'],priorpeers)
        require(peers==wantpeers,'Unintended identity merge/split during label scope repair')
        if wantpeers!=priorpeers:
            require(priorpeers==set().union(*(p for u,p in identity_exceptions.items() if u in priorpeers)),
                    'Original peer cohort differs from exact identity extent delta')
        require(item['author_2010_appendix_label_checked'] is True
                and item['annual_supplements_checked']==list(range(2010,2026)),
                'Ledger omitted actual full-label/source-year screen')
        allcases.append({'class_id':key[1],'original_target_all_fields_preserved':True,
                         'identity_peers_and_raw_preserved':True,'mapping_status':check['status'],'pass':True})
    cases=[]
    for key,item in delta.items():
        proof=item['proof'];scope_before=item['before_scope_target']
        check=dict(c.execute('SELECT * FROM dataset_mapping_checks WHERE dataset=? AND class_id=?',key).fetchone())
        review=json.loads(check['proof'])
        require(check['status']=='ANNOTATION_SCOPE_REVIEW' and review['decision']=='UNCONFIRMED_SCOPE'
                and review['input_sha256']==fingerprint and review['world_entity_disposition']=='PRESERVE'
                and all(review[k]==proof[k] for k in proof),'Wrong local world mapping review/provenance')
        history=c.execute('SELECT original_record FROM annotation_scope_target_history WHERE stage=? AND dataset=? AND class_id=?',(STAGE,*key)).fetchone()
        require(history is not None and json.loads(history[0])==item['before_target'],'Exact original world target history missing')
        for frozen in item['withdraw_depiction_claims']:
            claim=locate(c,'entity_relations',frozen['locator'])
            require(claim['status']=='REVIEW' and {k:v for k,v in claim.items() if k not in ('id','status')}
                    =={k:v for k,v in frozen['before_record'].items() if k not in ('id','status')},
                    'Old narrow depiction raw/source/evidence was lost or remains ACTIVE')
        for witness in proof['native_containment_witnesses']:
            actual=locate(c,'edges',witness['parent_assertion'])
            require(actual['status']=='ACTIVE' and digest({k:v for k,v in actual.items() if k!='id'})==witness['parent_assertion_sha256']
                    and actual['facet_family']=='TAXONOMIC_LINEAGE' and actual['parent_uid']==item['replacement_parent_uid'],
                    'Original native containment parent assertion changed')
        parent=c.execute('SELECT uid,label,source,rank,data,description,visibility FROM nodes WHERE uid=?',(item['replacement_parent_uid'],)).fetchone()
        require(parent is not None and digest(dict(parent))==proof['broader_parent_scope_sha256'],
                'Broader native parent source definition drift')
        current=dict(c.execute('SELECT * FROM dataset_scope_targets WHERE dataset=? AND class_id=? AND namespace=? AND source_version=?',
                              (*key,scope_before['namespace'],scope_before['source_version'])).fetchone())
        require({k:v for k,v in current.items() if k!='proof'}=={k:v for k,v in scope_before.items() if k!='proof'},
                'Original author UID/label/namespace/version/role changed')
        currentproof=json.loads(current['proof'])
        require(currentproof['scope_review_version']==proof['review_version']
                and currentproof['world_exact_identity_verified'] is False
                and currentproof['broader_native_parent_uid']==item['replacement_parent_uid'],
                'Native review falsely confirms exact world identity or loses version')
        records=list(c.execute('SELECT * FROM dataset_mapping_history WHERE dataset=? AND class_id=? AND decision=?',
                               (*key,'SOURCE_SCOPE_VERSION_REVIEW')))
        require(len(records)==1 and json.loads(records[0]['before_record'])==scope_before
                and json.loads(records[0]['after_record'])==current,'Full original native selector/proof history missing')
        rows=[dict(r) for r in c.execute("SELECT * FROM entity_relations WHERE subject_uid=? AND relation='DEPICTS_TYPE' AND status='ACTIVE'",(scope_before['source_uid'],))]
        require(len(rows)==1 and rows[0]['source']==SOURCE and rows[0]['object_uid']==item['replacement_parent_uid'],
                'Wrong/multiple active narrow/broader author depiction paths')
        claimproof=json.loads(rows[0]['data'])
        require(claimproof['is_class_inclusion'] is False and claimproof['admission_basis']['source_scope_entails_parent'] is True
                and claimproof['admission_basis']['mapping_is_identity'] is False
                and claimproof['admission_basis']['review_version']==proof['review_version'],
                'Versioned depiction became a type/identity assertion')
        require(c.execute('SELECT 1 FROM evidence WHERE evidence_id=?',(rows[0]['evidence_id'],)).fetchone() is not None,
                'Versioned broader depiction lacks source evidence')
        cases.append({'class_id':key[1],'label_scope_status':check['status'],'native_parent_uid':item['replacement_parent_uid'],
                      'actual_relation_id':rows[0]['id'],'original_narrow_claim_preserved_as_review':True,
                      'original_world_entity_preserved':True,'full_scope_history_preserved':True,'pass':True})
    baseline=json.loads((inputs/'structure_biology.json').read_text())
    expected=baseline['native_labels'];require(len(expected)==302,'Original 302 native labels must be retained')
    for item in expected:
        key=(item['dataset'],item['class_id']);want={(r['parent'],r['relation']) for r in item['links']}
        if key in delta:
            want={(delta[key]['replacement_parent_uid'],'DEPICTS_TYPE')}
        actual={(r['object_uid'],r['relation']) for r in c.execute("SELECT * FROM entity_relations WHERE subject_uid=? AND status='ACTIVE'",(item['uid'],))}
        require(actual==want,'Unexpected native relation changes outside reviewed case: '+':'.join(key))
    paths=[];world_rejections=[];revision=None;module=None
    if not sql_only:
        sys.dont_write_bytecode=True
        if not installed_sdk:sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
        import fineatlas
        if installed_sdk:
            require(Path(fineatlas.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
                    and 'site-packages' in Path(fineatlas.__file__).parts,'Actually installed SDK required')
        from fineatlas import FineAtlas
        module=fineatlas.__file__
        with FineAtlas(database,relation_view='unified') as tree:
            for dataset,ns,version in (('flowers102','oxford-flowers102','2008-categories-20261009'),
                                      ('cub200','caltech-cub200-2011','2011-author-metadata-20261009')):
                ix=tree.relation_reward_index(dataset,admission_mode='reviewed_paths',target_scope='source_native',source_namespace=ns,source_version=version)
                for item in expected:
                    if item['dataset']!=dataset:continue
                    result=tree.task_path(dataset,item['class_id'],index=ix)
                    require(result['status']=='CONNECTED','Reviewed native author category lost valid boundary path')
                    path_witness_sql(c,result)
                    if (dataset,item['class_id']) in delta:
                        want=delta[(dataset,item['class_id'])]['replacement_parent_uid']
                        require(any(step['edge'].get('object_uid')==want and step['edge']['relation']=='DEPICTS_TYPE'
                                    and step['edge']['source']==SOURCE for step in result['path']),
                                'Actual chosen path bypassed reviewed broader versioned source scope')
                    paths.append({'dataset':dataset,'class_id':item['class_id'],'result':result,'pass':True})
            world=tree.relation_reward_index('cub200',admission_mode='reviewed_paths')
            for key,item in delta.items():
                target=tree.target(*key);result=tree.task_path(*key,index=world);pair=world.query(key[1],'1')
                require(target['identity_verified'] is False and target['mapping_review']['status']=='ANNOTATION_SCOPE_REVIEW'
                        and result['status']=='ENDPOINT_NOT_APPLICABLE' and pair['distance'] is None,
                        'Unconfirmed historical label was admitted by world exact path/distance')
                world_rejections.append({'class_id':key[1],'target':target,'world_path':result,'pair_with_1':pair,'pass':True})
            for cls in ('155','199'):
                require(tree.target('cub200',cls)['identity_verified'] is True,
                        'Different-source split or unsupported date suspicion caused mechanical review')
            revision=tree._revision
    counts=Counter(r['mapping_status'] for r in allcases)
    require(counts['ANNOTATION_SCOPE_REVIEW']==27,'Expected original15 and additional12 label reviews')
    report={'pass':True,'status':'PASS_SQL_ONLY_FIXTURE' if sql_only else 'PASS_CANDIDATE_SQL_AND_PUBLIC_API',
      'database':str(database.resolve()),'input_sha256':fingerprint,
      'input_file_sha256':hashlib.sha256(payload_path.read_bytes()).hexdigest(),
      'ledger_file_sha256':hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
      'scientific_identity_scope_cases_checked':identity_audit['scientific_identity_scope_cases_checked'],
      'scientific_identity_bridges_checked':identity_audit['scientific_identity_bridges_checked'],
      'scientific_identity_scope_splits_checked':identity_audit['scientific_identity_scope_splits_checked'],
      'identity_scope_input_sha256':identity_audit['input_sha256'],
      'scientific_identity_scope_audit':identity_audit,
      'all_200_original_targets_checked':len(allcases),'all_200_original_identity_peer_uids_checked':len(peeruids),
      'new_label_scope_reviews_checked':len(cases),'mapping_status_counts':dict(counts),
      'native_sql_labels_checked':len(expected),'public_api_checked':not sql_only,
      'native_public_paths_checked':len(paths),'world_exact_guard_rejections_checked':len(world_rejections),
      'sdk_module_file':module,'revision':revision,'installed_sdk_requested':installed_sdk,
      'scope_delta_cases':cases,'all_200_source_cases':allcases,
      'seconds':round(time.monotonic()-start,3)}
    (output/'biology_version_scope_acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (output/'all_302_actual_native_paths.json').write_text(json.dumps(paths,ensure_ascii=False,indent=2)+'\n')
    (output/'all_12_world_exact_rejections.json').write_text(json.dumps(world_rejections,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('scope_delta_cases','all_200_source_cases')},ensure_ascii=False),flush=True)
    c.close();return 0


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--installed-sdk',action='store_true')
    p.add_argument('--sql-only',action='store_true',help='Small fixture only; cannot satisfy public candidate acceptance')
    a=p.parse_args();return run(a.database,a.inputs,a.output,installed_sdk=a.installed_sdk,sql_only=a.sql_only)

if __name__=='__main__':raise SystemExit(main())
