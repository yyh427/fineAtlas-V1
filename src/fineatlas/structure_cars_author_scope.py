"""Separate publisher Cars annotation identities from uncertain world ranges."""
from __future__ import annotations
from collections import Counter
import hashlib
import json

INPUT_NAME='structure_cars_author_scope.json'
OPERATIONS_NAME='structure_cars_author_scope_operations.jsonl'


def _canonical(x):
    return json.dumps(x,ensure_ascii=False,sort_keys=True)


def _sha(x):
    return hashlib.sha256(x.encode() if isinstance(x,str) else x).hexdigest()


def apply_structure_cars_author_scope(m):
    path=m.inputs/INPUT_NAME
    if not path.exists():return {'status':'not_requested'}
    raw=path.read_bytes();payload=json.loads(raw);fingerprint=_sha(raw);counts=Counter()
    if payload.get('schema')!='FINEATLAS_CARS_AUTHOR_SCOPE_V1' or len(payload['scope_targets'])!=196 or len(payload['world_mapping_reviews'])!=196:
        raise ValueError('Incomplete original 196-class Cars annotation inventory')
    operations=[json.loads(s) for s in (m.inputs/OPERATIONS_NAME).read_text().splitlines() if s]
    if operations!=payload['operations'] or any(x['relation']!='DEPICTS_TYPE' or x['parent']!='wordnet31:03796768-n' for x in operations):
        raise ValueError('Cars author source scope operation drift')
    original_metadata=(m.inputs/'cars_meta.mat').read_bytes()
    if _sha(original_metadata)!=payload['source_metadata']['source_metadata_sha256']:
        raise ValueError('Original Cars metadata checksum differs')
    # Preflight all mappings/raw UIDs, including previously retained reviews.
    for item in payload['world_mapping_reviews']:
        before=item['before'];current=m.c.execute('SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?',(before['dataset'],before['class_id'])).fetchone()
        if not current:raise ValueError('Cars author label missing')
        provenance=json.loads(current['provenance'] or '{}')
        if provenance.get('cars_author_scope_review_sha256')!=fingerprint and _sha(_canonical(dict(current)))!=item['before_sha256']:
            raise ValueError('Cars world mapping changed before independent range review')
        node=m.c.execute('SELECT data FROM nodes WHERE uid=?',(before['target_uid'],)).fetchone()
        if not node or _sha(node[0])!=item['proof']['native_record_sha256']:
            raise ValueError('Retained Cars real/source object payload changed')
    for item in payload['world_mapping_reviews']:
        before=item['before'];current=m.c.execute('SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?',(before['dataset'],before['class_id'])).fetchone()
        provenance=json.loads(current['provenance'] or '{}')
        if provenance.get('cars_author_scope_review_sha256')==fingerprint:continue
        proof={**item['proof'],'input_sha256':fingerprint,'original_record':before,'original_mapping_check':item['before_check']}
        eid=m.evidence('Independent Cars author/world mapping range review',proof['source_uri'],proof,'DATASET_MAPPING_SCOPE_REVIEW')
        provenance['cars_author_scope_review_sha256']=fingerprint
        after={**before,'decision_status':'REVIEW','identity_basis':'Annotation whole-range review; original world target/entity and source facts retained','provenance':_canonical(provenance)}
        m.c.execute('INSERT OR IGNORE INTO dataset_mapping_history VALUES (?,?,?,?,?,?,?,?,?)',(_sha(_canonical(proof)),before['dataset'],before['class_id'],'world','v1.11.0rc1',_canonical(before),_canonical(after),eid,'ANNOTATION_SCOPE_REVIEW'))
        m.c.execute('UPDATE dataset_targets SET decision_status=?,identity_basis=?,provenance=? WHERE dataset=? AND class_id=?',(after['decision_status'],after['identity_basis'],after['provenance'],before['dataset'],before['class_id']))
        m.c.execute('INSERT OR REPLACE INTO dataset_mapping_checks VALUES (?,?,?,?,?)',(before['dataset'],before['class_id'],'ANNOTATION_SCOPE_REVIEW',item['proof']['scope_observation'],_canonical(proof)))
        m.change('cars_author_scope','mapping_scope',before['dataset']+':'+before['class_id'],before,after,proof);counts['world_mapping_scope_reviews']+=1
    for node in payload['nodes']:
        counts['new_source_annotation_categories']+=m.add_node(node['uid'],node['label'],node['role'],node['domain'],node['source'],node['uri'],node['proof'])
        profile=m.c.execute('SELECT attributes FROM node_profiles WHERE uid=?',(node['uid'],)).fetchone()
        attrs=json.loads(profile[0]);attrs.update(identity_scope='SOURCE_NATIVE',world_exact_identity_verified=False,source_native_identity_verified=True,source_native_namespace=payload['namespace'],native_source_version=payload['source_version'],source_native_unit='ANNOTATION_CLASS',semantic_grain='SOURCE_NATIVE_DATASET_ANNOTATION_CATEGORY',is_world_model=False,is_world_configuration=False)
        m.c.execute('UPDATE node_profiles SET attributes=? WHERE uid=?',(_canonical(attrs),node['uid']))
    for target in payload['scope_targets']:
        values=[target[k] for k in ('dataset','class_id','namespace','source_version','source_uid','role','decision_status')]+[_canonical(target['proof']),target['label']]
        prior=m.c.execute('SELECT * FROM dataset_scope_targets WHERE dataset=? AND class_id=? AND namespace=? AND source_version=?',tuple(values[:4])).fetchone()
        if prior and (prior['source_uid']!=target['source_uid'] or prior['proof']!=values[-2]):raise ValueError('Cars native target namespace/version drift')
        m.c.execute('INSERT OR IGNORE INTO dataset_scope_targets VALUES (?,?,?,?,?,?,?,?,?)',values)
        if prior is None:
            eid=m.evidence('stanford_cars_native',payload['nodes'][0]['uri'],target['proof'],'DATASET_SOURCE_NATIVE_SCOPE')
            m.c.execute('INSERT OR IGNORE INTO dataset_mapping_history VALUES (?,?,?,?,?,?,?,?,?)',(_sha(_canonical(target)),target['dataset'],target['class_id'],target['namespace'],target['source_version'],'{}',_canonical(target),eid,'SOURCE_NATIVE_SCOPE_ADDED'))
            counts['source_native_scope_mappings']+=1
    from .hierarchy import apply_refinements
    counts.update(apply_refinements(m,OPERATIONS_NAME))
    reviewed=m.c.execute('SELECT value FROM metadata WHERE key=?',('reviewed_reward_policies',)).fetchone();policies=json.loads(reviewed[0]) if reviewed else {}
    cars=policies.setdefault('stanford_cars',{})
    cars['source_native']={'policy':'annotation','requirement':'hierarchy','source_scope':'stanford_cars_native','task_boundary_roots':['wordnet31:03796768-n'],'coarse_roots':['wordnet31:03796768-n'],'world_identity_verified':False,'namespace':payload['namespace'],'source_version':payload['source_version'],'source_annotation_coarse_only':True}
    m.meta('reviewed_reward_policies',policies);m.meta('cars_author_scope',{'input_sha256':fingerprint,'world_mapping_reviews':196,'source_native_labels':196,'source_native_pairs':19110,'world_identity_promotions':0,'ordinary_classes_added':0,'world_models_added':0,'world_configurations_added':0,'namespace':payload['namespace'],'source_version':payload['source_version'],'native_coarse_only':True})
    m.c.commit();return {'status':'PASS',**dict(counts),'native_coarse_only':True,'world_identity_promotions':0}
