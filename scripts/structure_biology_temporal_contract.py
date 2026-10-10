"""Exact later whole-scope reviews of the frozen biological identity cohort."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from pathlib import Path

from _download import digest
from structure_owned_scope_delivery_guard import require_owned_scope_receipt

SCHEMA='FINEATLAS_EXACT_LATER_BIOLOGY_IDENTITY_TRANSITIONS_V1'



def require_frozen_taxonomy_source_review(c,inputs,manifest,operations,meta):
    path=Path(inputs)/'structure_temporal_biology_source_review.json'
    if not path.is_file()or digest(path)!=meta['structure_frozen_build_manifest']['inputs'].get(path.name):
        raise ValueError('Independent historical eight-taxon source review must be frozen without changing original84 inputs')
    review=json.loads(path.read_text());lineage=meta.get('structure_complete_type_resume_parent',{})
    if (review.get('schema')!='FINEATLAS_ACTUAL_EIGHT_TAXON_BRIDGE_TEMPORAL_SOURCE_RECEIPTS_V1'or review.get('pass')is not True
            or review.get('actual_parent_diagnostic_only')is not True or review.get('final_finer_candidate_acceptance')is not False
            or review.get('database_revision')!=lineage.get('parent_revision')
            or review.get('source_operations_sha256')!=manifest['operations_sha256']or review.get('operation_count')!=manifest['operation_count']
            or Path(review.get('source_operations_file','')).name!=manifest['operations_file']):
        raise ValueError('Historical independent taxonomy review must bind the actual c933 parent and exact original1194 operations')
    biological=[op for op in operations if op.get('op')=='review_bridge'and op['proof'].get('basis')=='HISTORICAL_TAXON_VERSION_WHOLE_SCOPE_GAP']
    rows=review['records']
    if len(biological)!=len(rows)or len(rows)!=review.get('biological_bridge_count')or len(rows)!=8:
        raise ValueError('All eight individually reviewed biological source bridges required')
    by_id={r['before_bridge']['id']:r for r in rows}
    if len(by_id)!=len(rows)or set(by_id)!={o['before_assertion']['id']for o in biological}:
        raise ValueError('Historical source review cohort differs from exact frozen taxonomy operations')
    for op in biological:
        before=op['before_assertion'];record=by_id[before['id']];after={**before,'status':'SOURCE_SCOPE_REVIEW'}
        if (record['before_bridge']!=before or record['actual_after_bridge']!=after
                or record['versioned_taxon_source_review']!=op['proof']['versioned_taxon_source_review']
                or record['scientifically_false_identity_asserted']is not False):
            raise ValueError('Historical reviewed before/after or whole-version source evidence changed')
        actual=c.execute('SELECT * FROM bridges WHERE id=?',(before['id'],)).fetchone()
        if not actual or dict(actual)!=after:raise ValueError('Final raw reviewed taxonomy assertion differs from preserved exact source')
        current=[dict(h)for h in c.execute('SELECT * FROM usability_changes WHERE stage="owned_scope_repairs"AND object_type="bridge_scope_review"AND object_id=?',(str(before['id']),))]
        if current!=record['actual_history']:raise ValueError('Historical precise taxonomy source review history changed')
        ref=record['nominal_scientific_reference'];actual_ref=c.execute('SELECT * FROM entity_relations WHERE id=?',(ref['id'],)).fetchone()
        if not actual_ref or dict(actual_ref)!=ref:raise ValueError('Historical nonnavigation scientific reference changed')
        if c.execute('SELECT 1 FROM browse_links WHERE storage="entity"AND record_id=?',(ref['id'],)).fetchone():raise ValueError('A retained scientific reference became navigable')
        for uid,node in record['actual_raw_objects'].items():
            actual=dict(c.execute('SELECT * FROM nodes WHERE uid=?',(uid,)).fetchone())
            if {k:v for k,v in actual.items()if k!='component_id'}!={k:v for k,v in node.items()if k!='component_id'}:
                raise ValueError('Historical scientific source object/rank/scope changed')
        for parents in record['preserved_source_parents'].values():
            for table,field in(('edges','edges'),('entity_relations','entity_relations')):
                for original in parents[field]:
                    actual=c.execute('SELECT * FROM '+table+' WHERE id=?',(original['id'],)).fetchone()
                    if not actual or dict(actual)!=original:raise ValueError('Retained native scientific parent assertion changed')
    return {'file':path.name,'sha256':digest(path),'historical_parent_revision':review['database_revision'],'historical_review_is_current_final_acceptance':False,'exact_eight_current_source_claims_and_histories_checked':len(rows)}

def require_temporal_biology_permissions(c,inputs,owned_audit,code_root):
    inputs=Path(inputs);meta={key:json.loads(value)for key,value in c.execute('SELECT key,value FROM metadata')}
    database=Path(c.execute('PRAGMA database_list').fetchone()[2]).resolve()
    receipt=require_owned_scope_receipt(Path(owned_audit),database,inputs,meta['database_revision'],Path(code_root))
    frozen=meta['structure_frozen_build_manifest']['inputs'];manifest_path=inputs/'structure_owned_scope_repairs.json'
    manifest=json.loads(manifest_path.read_text());ops_path=inputs/manifest['operations_file']
    if digest(manifest_path)!=frozen.get(manifest_path.name)or digest(ops_path)!=manifest['operations_sha256']or digest(ops_path)!=frozen.get(ops_path.name):
        raise ValueError('Exact later biological review operations must be frozen')
    payload=json.loads((inputs/'structure_biology_identity_scope.json').read_text())
    original={b['id']:b for g in payload['reviewed_identity_groups']for b in g['actual_active_bridges']}
    operations=[json.loads(line)for line in ops_path.read_text().splitlines()if line]
    historical_review=require_frozen_taxonomy_source_review(c,inputs,manifest,operations,meta)
    selected=[o for o in operations if o.get('op')=='review_bridge'and o['before_assertion']['id']in original]
    if len(selected)!=5 or len({o['before_assertion']['id']for o in selected})!=5:
        raise ValueError('The original seventeen-bridge contract admits exactly its five later frozen whole-scope reviews')
    columns={row[1]for row in c.execute('PRAGMA table_info(bridges)')};permissions={};evidence=[]
    for op in selected:
        before=op['before_assertion'];old={key:original[before['id']][key]for key in columns}
        if before!=old or before['status']!='ACTIVE' or op['after_status']!='SOURCE_SCOPE_REVIEW':
            raise ValueError('Later review differs from the exact original biological source assertion')
        content={k:v for k,v in before.items()if k not in {'id','status','reason'}}
        if hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest()!=op['content_sha256']:
            raise ValueError('Later biological original assertion hash differs')
        proof=op['proof'];review=proof['versioned_taxon_source_review']
        if (proof['basis']!='HISTORICAL_TAXON_VERSION_WHOLE_SCOPE_GAP'or proof['scientifically_false_identity_asserted']is not False
                or proof['source_native_objects_preserved']is not True or proof['world_identity_assertion']is not False
                or review['bridge']!=before or review['independent_scope_assessment']!='PENDING_HISTORICAL_EXTENT_CROSSWALK_NOT_PROVEN_FALSE'
                or not isinstance(review['modern_explicit_split_present'],bool)or not isinstance(review['modern_scope_decision_present'],bool)
                or review['cub_explicit_historical_change_evidence_present']is not True
                or review['historical_concept_version_in_crosswalk']!='ABSENT'):
            raise ValueError('A later identity uncertainty needs its exact reviewed whole-version scope; it cannot imply false taxa')
        actual=dict(c.execute('SELECT * FROM bridges WHERE id=?',(before['id'],)).fetchone())
        if actual!={**before,'status':'SOURCE_SCOPE_REVIEW'}:raise ValueError('Later biological review changed raw claim, reason, producer or evidence')
        histories=c.execute('SELECT before_json,after_json,evidence FROM usability_changes WHERE stage="owned_scope_repairs"AND object_type="bridge_scope_review"AND object_id=?',(str(before['id']),)).fetchall()
        if sum(json.loads(h['before_json'])==before and json.loads(h['after_json'])=={'status':'SOURCE_SCOPE_REVIEW'}and json.loads(h['evidence'])==proof for h in histories)!=1:
            raise ValueError('Exactly one original-to-later scope review history required')
        for ev in proof['evidence_witnesses']:
            row=c.execute('SELECT * FROM evidence WHERE evidence_id=?',(ev['evidence_id'],)).fetchone()
            if not row or dict(row)!=ev or hashlib.sha256(row['payload'].encode()).hexdigest()!=row['payload_sha256']:
                raise ValueError('Original taxon identity evidence was modified')
        for uid,node in proof['source_nodes'].items():
            row=dict(c.execute('SELECT * FROM nodes WHERE uid=?',(uid,)).fetchone())
            if {k:v for k,v in row.items()if k!='component_id'}!={k:v for k,v in node.items()if k!='component_id'}:
                raise ValueError('Original reviewed scientific source object changed')
        for parent_records in proof['prior_source_parents'].values():
            for table,field in(('edges','edges'),('entity_relations','entity_relations')):
                for claim in parent_records[field]:
                    row=c.execute('SELECT * FROM '+table+' WHERE id=?',(claim['id'],)).fetchone()
                    if not row or dict(row)!=claim:raise ValueError('Original positive native source parents changed')
        refs=c.execute('SELECT * FROM entity_relations WHERE subject_uid=?AND object_uid=?AND relation="NOMINAL_SCIENTIFIC_REFERENCE"', (op['uid'],op['parent'])).fetchall()
        matching=[row for row in refs if row['source']==op['source']+': prior-bridge:'+op['content_sha256']and row['status']=='SOURCE_DECLARED'and json.loads(row['data']).get('admission_basis')==proof and json.loads(row['data']).get('allowed_views')==[]and json.loads(row['data']).get('navigation_eligible')is False]
        if len(matching)!=1:raise ValueError('Versioned nominal reference must be retained and excluded from navigation')
        ref=matching[0]
        if c.execute('SELECT 1 FROM browse_links WHERE storage="entity"AND record_id=?',(ref['id'],)).fetchone():raise ValueError('Non-navigation taxon reference leaked into browse graph')
        permissions[before['id']]=actual;evidence.append({'id':before['id'],'source_content_sha256':op['content_sha256'],'actual_preserved_after':actual,'source_scope_uncertainty':True,'original_evidence_preserved':True,'native_source_parents_preserved':True,'non_navigation_reference_id':ref['id']})
    repairs={r['before_bridge']['id']:r for r in payload['repairs']};partitions={};affected=[]
    for group in payload['reviewed_identity_groups']:
        if not any(b['id']in permissions for b in group['actual_active_bridges']):continue
        cohort={p['uid']for p in group['actual_identity_peers']};expected_bridges=[]
        adjacency={uid:set()for uid in cohort}
        for record in group['actual_active_bridges']:
            before={k:record[k]for k in columns};wanted=dict(before)
            if before['id']in repairs:wanted.update(status='GRAIN_REJECTED',reason=repairs[before['id']]['proof']['basis'])
            if before['id']in permissions:wanted=permissions[before['id']]
            actual=dict(c.execute('SELECT * FROM bridges WHERE id=?',(before['id'],)).fetchone())
            if actual!=wanted:raise ValueError('Unspecified assertion changed in the temporal biological identity cohort')
            expected_bridges.append(wanted)
            if wanted['status']=='ACTIVE':adjacency[wanted['left_uid']].add(wanted['right_uid']);adjacency[wanted['right_uid']].add(wanted['left_uid'])
        touching={r['id']for uid in cohort for r in c.execute('SELECT * FROM bridges WHERE (left_uid=?OR right_uid=?)AND status="ACTIVE"',(uid,uid))}
        if touching!={r['id']for r in expected_bridges if r['status']=='ACTIVE'}:raise ValueError('New or unreviewed identity bridge entered a temporal scientific component')
        todo=set(cohort);parts=[]
        while todo:
            queue=[next(iter(todo))];part=set()
            while queue:
                uid=queue.pop()
                if uid in part:continue
                part.add(uid);queue.extend(adjacency[uid]-part)
            todo-=part;parts.append(part)
        for part in parts:
            ids={c.execute('SELECT component_id FROM nodes WHERE uid=?',(uid,)).fetchone()[0]for uid in part}
            if len(ids)!=1:raise ValueError('Equal reviewed scientific peers were unnecessarily split')
            members={r[0]for r in c.execute('SELECT uid FROM nodes WHERE component_id=?',(next(iter(ids)),))}
            if members!=part:raise ValueError('A source-reviewed identity partition lost or merged members')
            for uid in part:partitions[uid]=part
        affected.append({'class_id':group['class_id'],'before_uids':sorted(cohort),'exact_after_partitions':sorted(map(sorted,parts))})
    return permissions,partitions,{'contract':SCHEMA,'owned_manifest_sha256':digest(manifest_path),'owned_operations_sha256':digest(ops_path),
        'owned_actual_audit':{'path':str(Path(owned_audit).resolve()),'sha256':digest(owned_audit)},'database_revision':meta['database_revision'],
        'historical_independent_taxonomy_review':historical_review,'exact_later_scientific_bridge_reviews':evidence,'exact_later_scientific_partitions':affected,'pass':True}


def require_temporal_biology_receipt(report,database,inputs,revision,code_root):
    path=Path(report);value=json.loads(path.read_text());inputs=Path(inputs);code_root=Path(code_root)
    if (value.get('pass')is not True or value.get('public_api_checked')is not True or value.get('candidate_acceptance')is not True
            or value.get('revision')!=revision or Path(value.get('database','')).resolve()!=Path(database).resolve()
            or value.get('temporal_biology_contract')!=SCHEMA or value.get('original_biology_contract_fully_checked')is not True
            or value.get('scientific_identity_bridges_checked')!=17 or value.get('all_200_original_targets_checked')!=200
            or value.get('native_public_paths_checked')!=302 or value.get('later_biological_identity_reviews')!=5):
        raise ValueError('Full actual temporal biological SQL/API acceptance required; diagnostic/preflight cannot qualify')
    for name in ('structure_owned_scope_repairs.json','structure_biology_identity_scope.json','cub_annotation_version_scope.json','all_200_version_scope_ledger.json','structure_temporal_biology_source_review.json'):
        if value.get('temporal_frozen_inputs',{}).get(name)!=digest(inputs/name):raise ValueError('Temporal biological source input changed')
    for name in ('audit_temporal_complete_biology_version_scope.py','structure_biology_temporal_contract.py','audit_structure_biology_version_scope.py'):
        if value.get('temporal_auditor_code',{}).get(name)!=digest(code_root/'scripts'/name):raise ValueError('Temporal biological actual auditor code changed')
    with sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro&immutable=1',uri=True)as con:
        con.row_factory=sqlite3.Row;con.execute('PRAGMA query_only=ON')
        meta={key:json.loads(raw)for key,raw in con.execute('SELECT key,value FROM metadata')}
        if meta['database_revision']!=revision:raise ValueError('Actual temporal biological database revision changed')
        freeze=meta['structure_frozen_build_manifest']
        if any(freeze['inputs'].get(name)!=sha for name,sha in value['temporal_frozen_inputs'].items()):raise ValueError('Temporal source evidence was not frozen in actual database')
        if any(freeze['code'].get('scripts/'+name)!=sha for name,sha in value['temporal_auditor_code'].items()):raise ValueError('Actual temporal biology implementation was not frozen')
        actual=value['temporal_actual_source_audit'];source_path=Path(actual['path'])
        if digest(source_path)!=actual['sha256']:raise ValueError('Actual owned-scope source audit changed')
        _,_,evidence=require_temporal_biology_permissions(con,inputs,source_path,code_root)
        stored=value['scientific_identity_scope_audit']['temporal']
        if evidence!=stored:raise ValueError('Later biological actual source/history/partition evidence changed')
    return value
