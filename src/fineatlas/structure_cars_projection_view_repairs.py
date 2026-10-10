"""Review author-derived world projections without erasing their source records.

An annotation's selected model references do not define a whole world
configuration range. Preserve those references separately from typed inclusion.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json

from .hierarchy import locate_source_assertion, source_assertion_content, source_assertion_sha256

INPUT_NAME = 'structure_cars_projection_view_repairs.json'
SCHEMA = 'FINEATLAS_CARS_PROJECTION_VIEW_REPAIRS_V1'
STAGE = 'cars_projection_view_repairs'


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def load_inputs(inputs):
    path = inputs / INPUT_NAME
    manifest = json.loads(path.read_text())
    if manifest.get('schema') != SCHEMA or manifest.get('operations_file') != 'cars_projection_view_repairs.jsonl':
        raise ValueError('Unexpected author projection review input')
    raw = (inputs / manifest['operations_file']).read_bytes()
    ops = [json.loads(line) for line in raw.decode().splitlines() if line]
    if (sha(raw) != manifest.get('operations_sha256') or type(manifest.get('operation_count')) is not int
            or not ops or len(ops) != manifest['operation_count']
            or dict(Counter(x['relation'] for x in ops)) != manifest.get('operations')):
        raise ValueError('Incomplete frozen projection claim census')
    return path, manifest, ops, raw


def node_unchanged(actual, frozen):
    # Components are derived and can be rebuilt independently; source content is not.
    return actual is not None and all(dict(actual).get(k) == v for k, v in frozen.items() if k != 'component_id')


def table_snapshot(c, table):
    return sorted([dict(row) for row in c.execute('SELECT * FROM ' + table)], key=lambda x: json.dumps(x, sort_keys=True))


def validate_cars_projection_view_repairs(c, manifest, operations):
    nodes = manifest['source_projections']
    if (type(manifest.get('source_projection_count')) is not int or len(nodes) != manifest['source_projection_count']
            or len({x['uid'] for x in nodes}) != len(nodes) or not nodes
            or manifest.get('new_nodes') != 0 or manifest.get('mapping_promotions') != 0
            or manifest.get('legacy_whole_world_claims_are_pending_not_proven_false') is not True):
        raise ValueError('Projection review cannot create identities or promote mappings')
    index = {row['uid']: row for row in nodes}
    for entry in nodes:
        uid = entry['uid']; before = c.execute('SELECT * FROM nodes WHERE uid=?', (uid,)).fetchone()
        profile = c.execute('SELECT * FROM node_profiles WHERE uid=?', (uid,)).fetchone()
        if (not node_unchanged(before, entry['before_node']) or before['visibility'] != 'ACTIVE'
                or before['source'] != 'FineAtlas V26 source projection'
                or sha(before['data']) != entry['native_record_sha256']
                or (dict(profile) if profile else None) != entry['before_profile']
                or (profile['node_kind'] if profile else ('CONFIGURATION' if before['rank'] == 'model_year' else None)) != 'CONFIGURATION'):
            raise ValueError('Original projection record or role changed: ' + uid)
        origin = entry['origin']; expected = 'v26-car:' + sha('\0'.join((origin['dataset'], origin['class_id'], origin['official_label'])))[:32]
        native = json.loads(before['data'])
        if (origin.get('dataset') != 'stanford_cars' or origin.get('author_source_origin_proven') is not True
                or origin.get('author_origin_does_not_close_world_configuration_range') is not True
                or expected != uid or origin.get('deterministic_constructor_uid') != uid
                or origin['original_overlay_node']['data'] != before['data']
                or origin['original_overlay_target']['target_uid'] != uid
                or native.get('dataset_alias') != origin['official_label']
                or entry.get('canonical_role_after') != 'UNKNOWN' or entry.get('visibility_after') != 'SOURCE_ONLY'
                or entry.get('allowed_views_after') != [] or not entry.get('reason')):
            raise ValueError('Author origin or scope review is not bound: ' + uid)
        target = c.execute('SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?', (origin['dataset'], origin['class_id'])).fetchone()
        if not target or target['target_uid'] != uid or target['label'] != origin['official_label']:
            raise ValueError('Projection author target changed')
        for field, table in (('before_current_target', 'dataset_targets'), ('before_mapping_check', 'dataset_mapping_checks')):
            if field in entry:
                row = c.execute('SELECT * FROM ' + table + ' WHERE dataset=? AND class_id=?', (origin['dataset'], origin['class_id'])).fetchone()
                if (dict(row) if row else None) != entry[field]:
                    raise ValueError('Frozen author mapping or review changed')
    seen = set(); resolved = []
    for op in operations:
        proof = op['proof']; uid = op['uid']
        if (uid not in index or op.get('op') != 'review_world_projection_relation' or op.get('relation') != 'CONFIGURATION_OF'
                or op.get('after_status') != 'SOURCE_SCOPE_REVIEW' or op.get('new_reference_relation') != 'SOURCE_MODEL_REFERENCE'
                or op.get('new_reference_status') != 'SOURCE_DECLARED' or proof.get('world_identity_assertion') is not False
                or proof.get('new_parent_task_relation') is not False or proof.get('no_identity_merges') is not True
                or proof.get('scope_evidence_gap') is not True or proof.get('source_scope_conflict') is not False
                or proof.get('parent_data_has_closed_whole_model_scope') is not False
                or proof.get('source_origin') != index[uid]['origin'] or not proof.get('review_reason')):
            raise ValueError('Projection review cannot assert a false identity or replacement hierarchy')
        old = locate_source_assertion(c, 'entity_relations', op['locator'])
        if (old['status'] != 'ACTIVE' or op['locator'].get('status') != 'ACTIVE'
                or source_assertion_content(old) != source_assertion_content(op['before_relation'])
                or (old['subject_uid'], old['object_uid'], old['relation']) != (uid, op['parent'], 'CONFIGURATION_OF')
                or source_assertion_sha256(old) != proof['old_relation_content_sha256']
                or sha(index[uid]['before_node']['data']) != proof['native_record_sha256']):
            raise ValueError('Original projection inclusion changed')
        parent = c.execute('SELECT * FROM nodes WHERE uid=?', (op['parent'],)).fetchone()
        if not parent or sha(parent['data']) != proof['parent_native_record_sha256'] or parent['source'] != proof['parent_source']:
            raise ValueError('Retained native model reference changed')
        key = (uid, op['parent'], old['source'], source_assertion_sha256(old))
        if key in seen:
            raise ValueError('Duplicate frozen source claim')
        seen.add(key); resolved.append(dict(old))
    actual = {(r['subject_uid'], r['object_uid'], r['source'], source_assertion_sha256(r)) for uid in index for r in c.execute("SELECT * FROM entity_relations WHERE subject_uid=? AND relation='CONFIGURATION_OF' AND status='ACTIVE'", (uid,))}
    if actual != seen:
        raise ValueError('Not every active unclosed world inclusion is reviewed')
    for item in manifest['preserved_nonprojection_configs']:
        if item['uid'] in index:
            raise ValueError('Legal source configurations cannot be withdrawn as projections')
        for claim in item['current_configuration_of_claims']:
            locator = {k: claim[k] for k in ('subject_uid', 'object_uid', 'relation', 'source')}
            locator['content_sha256'] = source_assertion_sha256(claim)
            current = locate_source_assertion(c, 'entity_relations', locator)
            if current['status'] != claim['status']:
                raise ValueError('Legal manufacturer/EPA inclusion changed')
    return resolved


def apply_cars_projection_view_repairs(m):
    path = m.inputs / INPUT_NAME
    if not path.exists():
        return {'status': 'not_requested'}
    path, manifest, ops, raw = load_inputs(m.inputs)
    if m.c.execute("SELECT 1 FROM metadata WHERE key='cars_projection_view_repairs'").fetchone():
        raise ValueError('Projection review was already applied')
    old_claims = validate_cars_projection_view_repairs(m.c, manifest, ops)
    snapshots = {table: table_snapshot(m.c, table) for table in ('dataset_targets', 'dataset_mapping_checks')}
    node_count = m.c.execute('SELECT count(*) FROM nodes').fetchone()[0]
    m.c.execute('SAVEPOINT cars_projection_review')
    try:
        for entry in manifest['source_projections']:
            uid = entry['uid']; before = dict(m.c.execute('SELECT * FROM nodes WHERE uid=?', (uid,)).fetchone())
            previous = m.c.execute('SELECT * FROM node_profiles WHERE uid=?', (uid,)).fetchone()
            attrs = json.loads(previous['attributes']) if previous else {}
            proof = {'basis': 'AUTHOR_ORIGIN_PROVEN_WORLD_CONFIGURATION_RANGE_PENDING', 'source_role': attrs.get('source_role', before['rank']),
                     'allowed_views': [], 'review_reason': entry['reason'], 'native_record_sha256': sha(before['data']),
                     'source_origin': entry['origin'], 'world_identity_assertion': False, 'disposition_category': 7}
            if previous:
                ev = m.c.execute('SELECT retrieved_utc FROM evidence WHERE evidence_id=?', (previous['evidence_id'],)).fetchone()
                if ev: proof['retrieved_utc'] = ev[0]
            m.role(uid, 'UNKNOWN', proof, 'Reviewed author-derived configuration projection scope', 'urn:fineatlas:source-record:' + uid)
            m.c.execute("UPDATE nodes SET visibility='SOURCE_ONLY' WHERE uid=?", (uid,))
            after = dict(m.c.execute('SELECT * FROM nodes WHERE uid=?', (uid,)).fetchone())
            m.change(STAGE, 'nodes', uid, before, after, proof)
            current = dict(m.c.execute('SELECT * FROM node_profiles WHERE uid=?', (uid,)).fetchone())
            m.change(STAGE, 'node_profiles', uid, dict(previous) if previous else None, current, proof)
        for op, before in zip(ops, old_claims):
            proof = dict(op['proof']); proof['disposition_category'] = 7
            m.c.execute("UPDATE entity_relations SET status='SOURCE_SCOPE_REVIEW' WHERE id=?", (before['id'],))
            after = dict(m.c.execute('SELECT * FROM entity_relations WHERE id=?', (before['id'],)).fetchone())
            m.change(STAGE, 'entity_relations', before['id'], before, after, proof)
            reference = {'basis': 'RETAINED_SOURCE_CONSTRUCTOR_MODEL_REFERENCE_ONLY', 'original_assertion': source_assertion_content(before),
                         'original_status': before['status'], 'original_locator': op['locator'], 'source_record_sha256': op['proof']['native_record_sha256'],
                         'review_reason': op['proof']['review_reason'], 'world_identity_assertion': False, 'no_navigation': True}
            ev = m.c.execute('SELECT retrieved_utc FROM evidence WHERE evidence_id=?', (before['evidence_id'],)).fetchone()
            if ev: reference['retrieved_utc'] = ev[0]
            source = op['source'] + ' [' + source_assertion_sha256(before) + ']'
            eid = m.evidence(source, op['uri'], reference, 'SOURCE_MODEL_REFERENCE', op['proof']['license'])
            m.c.execute('INSERT INTO entity_relations(subject_uid,object_uid,relation,status,source,evidence_id,data) VALUES (?,?,?,?,?,?,?)',
                        (op['uid'], op['parent'], 'SOURCE_MODEL_REFERENCE', 'SOURCE_DECLARED', source, eid, json.dumps(reference, ensure_ascii=False, sort_keys=True, separators=(',', ':'))))
            row = dict(m.c.execute('SELECT * FROM entity_relations WHERE id=last_insert_rowid()').fetchone())
            m.change(STAGE, 'source_model_reference', row['id'], None, row, reference)
        validate_preserved_claims(m.c, manifest)
        if node_count != m.c.execute('SELECT count(*) FROM nodes').fetchone()[0] or any(snapshots[t] != table_snapshot(m.c, t) for t in snapshots):
            raise ValueError('Source review changed entities or author mappings')
        m.meta(STAGE, {'manifest_sha256': sha(path.read_bytes()), 'operations_sha256': sha(raw), 'operation_count': len(ops),
                      'source_projection_count': len(manifest['source_projections']), 'reference_count': len(ops), 'world_mapping_promotions': 0,
                      'mapping_snapshots_sha256': {t: sha(json.dumps(v, sort_keys=True)) for t, v in snapshots.items()}})
        m.meta('usability_indexes_ready', False)
        m.c.execute('RELEASE cars_projection_review')
    except BaseException:
        m.c.execute('ROLLBACK TO cars_projection_review'); m.c.execute('RELEASE cars_projection_review')
        raise
    m.c.commit()
    return {'status': 'PASS', 'reviewed_claims': len(ops), 'source_only_projections': len(manifest['source_projections']), 'retained_source_references': len(ops)}


def validate_preserved_claims(c, manifest):
    for item in manifest['preserved_nonprojection_configs']:
        for claim in item['current_configuration_of_claims']:
            locator = {k: claim[k] for k in ('subject_uid', 'object_uid', 'relation', 'source')}
            locator['content_sha256'] = source_assertion_sha256(claim)
            current = locate_source_assertion(c, 'entity_relations', locator)
            if current['status'] != claim['status']:
                raise ValueError('Legal manufacturer/EPA inclusion changed')
