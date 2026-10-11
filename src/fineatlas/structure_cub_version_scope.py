"""Label-local historical taxonomy scope corrections; no entity mutation.

The main candidate migration installs the shared history tables and rebuilds all
caches after this separate stage. Inputs preserve every previous assertion and
are bound to individual first-party source scope observations.
"""
from collections import Counter
import hashlib
import json

INPUT_NAME = 'cub_annotation_version_scope.json'
SCHEMA = 'FINEATLAS_CUB_ANNOTATION_VERSION_SCOPE_V1'
STAGE = 'v1.11-cub-author-taxonomic-version-scope'
SOURCE = 'Caltech-UCSD Birds author metadata; taxonomic-version scope review'
META_KEY = 'cub_annotation_version_scope_sha256'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_payload(payload):
    if payload.get('schema') != SCHEMA or payload.get('stage') != STAGE:
        raise ValueError('Unsupported CUB temporal annotation-scope input')
    if (payload.get('reviewed_label_count') != 200
            or payload.get('retained_world_entities') is not True
            or payload.get('source_taxonomy_edges_preserved') is not True
            or payload.get('new_scientific_nodes') != 0
            or payload.get('new_identity_bridges') != 0):
        raise ValueError('Temporal review cannot change scientific entity scope')
    cases = payload['mapping_reviews']
    if len(cases) != payload['new_label_scope_reviews']:
        raise ValueError('Incomplete temporal scope-review cohort')
    keys = set()
    for case in cases:
        key = (case['dataset'],case['class_id'])
        if key in keys:
            raise ValueError('Duplicate author-label review')
        keys.add(key)
        proof = case['proof']
        parent = proof['broader_parent_source_definition']
        if (case['dataset'] != 'cub200' or proof.get('decision') != 'UNCONFIRMED_SCOPE'
                or proof.get('world_entity_disposition') != 'PRESERVE'
                or proof.get('world_identity_authorized') is not False
                or proof.get('mapping_is_identity') is not False
                or not proof.get('reason') or not proof.get('review_version')
                or not proof.get('primary_change_evidence')
                or case['replacement_parent_uid'] != proof['broader_native_parent_uid']
                or parent['uid'] != case['replacement_parent_uid']
                or parent['source'] != 'avilist'
                or parent['rank'] not in ('genus','species')
                or parent['visibility'] != 'ACTIVE'
                or digest(parent) != proof['broader_parent_scope_sha256']
                or proof['broader_parent_source_record']['Scientific_name'].lower()
                   != parent['uid'].removeprefix('avilist:')
                or proof['broader_parent_source_record']['Taxon_rank'] != parent['rank']
                or proof['modern_taxonomy_sha256'] != payload['modern_source_snapshot_sha256']):
            raise ValueError('Unconfirmed source mapping must use a documented broader native scope')
        if proof['depiction_semantics'] not in (
                'DOCUMENTED_HISTORICAL_COMPLEX_CONTAINED_IN_NATIVE_GENUS',
                'HISTORICAL_LABEL_CONTAINED_IN_MODERN_LUMPED_SPECIES'):
            raise ValueError('Undocumented historical containment')
        if proof.get('source_scope_entails_parent') is not True:
            raise ValueError('Native historical containment lacks an individual scope review')
        witnesses=proof.get('native_containment_witnesses',[])
        if not witnesses:
            raise ValueError('Native historical complex has no actual parent witnesses')
        for witness in witnesses:
            arc=witness['parent_assertion']
            if (witness['parent_uid'] != parent['uid']
                    or witness['source_uid'] != 'avilist:'+witness['source_record']['Scientific_name'].lower()
                    or arc['child_uid'] != witness['source_uid'] or arc['parent_uid'] != parent['uid']
                    or arc['relation'] != 'IS_A' or arc['source'] != 'avilist'
                    or arc['source_relation'] != 'Taxon_rank'
                    or arc['facet_family'] != 'TAXONOMIC_LINEAGE' or arc['status'] != 'ACTIVE'
                    or digest({k:v for k,v in arc.items() if k!='id'}) != witness['parent_assertion_sha256']):
                raise ValueError('Historical complex must stay within actual native taxonomic parent')
        if not case['withdraw_depiction_claims']:
            raise ValueError('The old narrower depiction claim must be retained as REVIEW')
        for claim in case['withdraw_depiction_claims']:
            r = claim['before_record']
            if (r['relation'] != 'DEPICTS_TYPE' or r['status'] != 'ACTIVE'
                    or r['subject_uid'] != case['before_scope_target']['source_uid']
                    or digest({k:v for k,v in r.items() if k != 'id'}) != claim['before_claim_sha256']):
                raise ValueError('Temporal scope review may only revise its exact prior depiction')


def preflight(c, payload):
    """Check all source endpoints and prior claims before changing any case."""
    for case in payload['mapping_reviews']:
        key = (case['dataset'],case['class_id'])
        target = c.execute('SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?',key).fetchone()
        check = c.execute('SELECT * FROM dataset_mapping_checks WHERE dataset=? AND class_id=?',key).fetchone()
        before = case['before_scope_target']
        scope = c.execute('SELECT * FROM dataset_scope_targets WHERE dataset=? AND class_id=? AND namespace=? AND source_version=?',
            (*key,before['namespace'],before['source_version'])).fetchone()
        if (not target or digest(dict(target)) != case['before_target_sha256']
                or (dict(check) if check else None) != case['before_check']
                or not scope or digest(dict(scope)) != case['before_scope_sha256']):
            raise ValueError('Frozen author label/target/scope changed before replay')
        parent = c.execute('SELECT uid,label,source,rank,data,description,visibility FROM nodes WHERE uid=?',
                           (case['replacement_parent_uid'],)).fetchone()
        if not parent or digest(dict(parent)) != case['proof']['broader_parent_scope_sha256']:
            raise ValueError('Frozen native taxon scope changed before replay')
        for witness in case['proof']['native_containment_witnesses']:
            expected=witness['parent_assertion']
            arc=c.execute('SELECT * FROM edges WHERE child_uid=? AND parent_uid=? AND relation=? AND source=? AND source_relation=? AND layer=?',
                tuple(expected[k] for k in ('child_uid','parent_uid','relation','source','source_relation','layer'))).fetchone()
            if not arc or digest({k:v for k,v in dict(arc).items() if k!='id'}) != witness['parent_assertion_sha256']:
                raise ValueError('Frozen native containment parent assertion changed before replay')
        for uid in case['source_entity_uids_preserved']:
            row = c.execute('SELECT visibility FROM nodes WHERE uid=?',(uid,)).fetchone()
            if not row or row[0] != 'ACTIVE':
                raise ValueError('Historical review cannot use missing/inactive entity')
        for claim in case['withdraw_depiction_claims']:
            locator=claim['locator']
            actual=c.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',
                tuple(locator[k] for k in ('subject_uid','object_uid','relation','source'))).fetchone()
            if not actual or digest({k:v for k,v in dict(actual).items() if k!='id'}) != claim['before_claim_sha256']:
                raise ValueError('Frozen prior depiction source claim changed before replay')


def apply_cub_annotation_version_scope(m):
    path=m.inputs/INPUT_NAME
    if not path.exists():
        return {'status':'not_requested'}
    payload=json.loads(path.read_text());validate_payload(payload);fingerprint=digest(payload)
    previous=m.c.execute('SELECT value FROM metadata WHERE key=?',(META_KEY,)).fetchone()
    if previous:
        if json.loads(previous[0]) == fingerprint:
            return {'status':'already_applied','input_sha256':fingerprint}
        raise ValueError('Immutable temporal-scope stage already applied with another input')
    preflight(m.c,payload)
    counts=Counter();m.c.execute('SAVEPOINT cub_version_scope')
    try:
        for case in payload['mapping_reviews']:
            key=(case['dataset'],case['class_id']);before=case['before_target']
            proof={**case['proof'],'input_sha256':fingerprint,
                   'original_world_target_record':before,'original_mapping_check':case['before_check']}
            eid=m.evidence(SOURCE,proof['source_uri'],proof,'LABEL_TAXONOMIC_VERSION_SCOPE_REVIEW')
            m.c.execute('INSERT OR IGNORE INTO dataset_target_history VALUES(?,?,?,?)',
                (*key,before['target_uid'],canonical(before)))
            m.c.execute('INSERT OR IGNORE INTO annotation_scope_target_history VALUES(?,?,?,?)',
                (STAGE,*key,canonical(before)))
            m.c.execute('INSERT OR REPLACE INTO dataset_mapping_checks VALUES(?,?,?,?,?)',
                (*key,'ANNOTATION_SCOPE_REVIEW',proof['reason'],canonical(proof)))
            m.change(STAGE,'label_mapping_review',':'.join(key),case['before_check'],
                     {'status':'ANNOTATION_SCOPE_REVIEW','decision':'UNCONFIRMED_SCOPE'},proof)
            counts['label_only_scope_reviews']+=1
            for claim in case['withdraw_depiction_claims']:
                locator=claim['locator'];r=m.c.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',
                    tuple(locator[k] for k in ('subject_uid','object_uid','relation','source'))).fetchone()
                m.c.execute("UPDATE entity_relations SET status='REVIEW' WHERE id=?",(r['id'],))
                m.change(STAGE,'typed_source_scope_review',r['id'],dict(r),{'status':'REVIEW'},proof)
                counts['prior_depiction_claims_retained_review']+=1
            scope_before=case['before_scope_target'];scope_after=dict(scope_before)
            old_proof=json.loads(scope_before['proof'])
            scope_after['proof']=canonical({**old_proof,
                'scope_resolution':'AUTHOR_HISTORICAL_SCOPE_REVIEWED_BROADER_NATIVE_TAXON',
                'world_mapping_review':'UNCONFIRMED_SCOPE',
                'world_exact_identity_verified':False,
                'scope_review_version':proof['review_version'],
                'broader_native_parent_uid':case['replacement_parent_uid'],
                'taxonomic_version_scope_review':proof,
                'input_sha256':fingerprint})
            history_id='mapping-history:'+digest({'stage':STAGE,'before':scope_before,'after':scope_after})
            m.c.execute('INSERT OR IGNORE INTO dataset_mapping_history VALUES(?,?,?,?,?,?,?,?,?)',
                (history_id,*key,scope_before['namespace'],scope_before['source_version'],
                 canonical(scope_before),canonical(scope_after),eid,'SOURCE_SCOPE_VERSION_REVIEW'))
            m.c.execute('UPDATE dataset_scope_targets SET proof=? WHERE dataset=? AND class_id=? AND namespace=? AND source_version=?',
                (scope_after['proof'],*key,scope_before['namespace'],scope_before['source_version']))
            m.typed(scope_before['source_uid'],case['replacement_parent_uid'],'DEPICTS_TYPE',
                {**proof,'native_label_uid':scope_before['source_uid'],'source_scope_entails_parent':True},
                SOURCE,proof['modern_taxonomy_uri'])
            claim=m.c.execute('SELECT status FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',
                (scope_before['source_uid'],case['replacement_parent_uid'],'DEPICTS_TYPE',SOURCE)).fetchone()
            if not claim or claim[0]!='ACTIVE':
                raise ValueError('Broader historical annotation path not independently active')
            counts['reviewed_broader_native_depiction_claims']+=1
        m.meta(META_KEY,fingerprint);m.meta('cub_annotation_version_scope_summary',dict(counts))
        m.c.execute('RELEASE cub_version_scope');m.c.commit()
    except BaseException:
        m.c.execute('ROLLBACK TO cub_version_scope');m.c.execute('RELEASE cub_version_scope');raise
    return {**dict(counts),'input_sha256':fingerprint,'source_nodes_modified':0,
            'original_targets_modified':0,'identity_bridges_modified':0,'requires_cache_rebuild':True}
