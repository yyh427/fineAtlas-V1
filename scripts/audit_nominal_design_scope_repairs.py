#!/usr/bin/env python3
"""Verify nominal-scope additions independently with immutable SQL and source bytes."""
from __future__ import annotations

if not __debug__:
    raise RuntimeError('Mandatory nominal source checks cannot run optimized')

import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import sqlite3

INPUT_NAME = 'structure_nominal_design_scope_repairs.json'
SOURCE = 'Reviewed complete nominal design and generic class scope'
KEYS = {'nodes': 'uid', 'node_profiles': 'uid', 'normalization_roles': 'uid',
        'edges': 'id', 'entity_relations': 'id', 'bridges': 'id', 'evidence': 'evidence_id'}
ACTIVE = {'ACTIVE', 'BACKBONE_ACTIVE', 'TYPED_ACTIVE'}


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def assertion_sha(row):
    return sha(json.dumps({k: v for k, v in row.items() if k not in {'id', 'status', 'reason'}}, sort_keys=True))


def row_at(con, table, key):
    if table not in KEYS:
        raise ValueError('Unsafe source witness table')
    row = con.execute('SELECT * FROM ' + table + ' WHERE ' + KEYS[table] + '=?', (key,)).fetchone()
    return dict(row) if row else None


def read_input(inputs, name):
    if not isinstance(name, str) or Path(name).name != name:
        raise ValueError('Source evidence must have a safe portable filename')
    return (inputs / name).read_bytes()


def role(con, node):
    profile = row_at(con, 'node_profiles', node['uid'])
    if profile and profile.get('node_kind'):
        return profile['node_kind']
    return {'model': 'MODEL', 'product_model': 'MODEL', 'aircraft_model': 'MODEL',
            'vehicle_model': 'MODEL', 'series': 'MODEL_FAMILY', 'model_family': 'MODEL_FAMILY',
            'configuration': 'CONFIGURATION', 'instance': 'INSTANCE', 'unknown': 'UNKNOWN',
            'type_or_product_model': 'UNKNOWN', 'biological_variant': 'BIOLOGICAL_VARIANT',
            'dataset_category': 'DATASET_CATEGORY', 'manufacturer': 'ORGANIZATION',
            'attribute': 'ATTRIBUTE'}.get((node.get('rank') or '').lower(), 'CLASS')


def allowed(relation, child_role, parent_role):
    return (relation == 'IS_A' and child_role == parent_role == 'CLASS'
            or relation == 'DESIGN_TYPE_OF' and child_role in {'MODEL', 'MODEL_FAMILY'} and parent_role == 'CLASS'
            or relation == 'NATIVE_DESIGN_PARENT' and child_role in {'MODEL', 'MODEL_FAMILY'}
            and parent_role in {'MODEL', 'MODEL_FAMILY'}
            or relation == 'INSTANCE_OF' and child_role == 'INSTANCE' and parent_role == 'CLASS')


def complete_fields(node):
    data = json.loads(node['data'])
    return {(name, value) for container in (data, data.get('evidence_record', {}))
            for name in ('description', 'wikidata_description', 'definition', 'wikipedia_intro', 'gloss')
            if isinstance((value := container.get(name)), str) and value}


def check_witness(con, witness):
    node = row_at(con, 'nodes', witness['uid'])
    if not node or sha(node['data']) != witness['data_sha256']:
        raise ValueError('Complete retained source object bytes differ')
    path = witness['field_path']
    if not isinstance(path, (str, list)):
        raise ValueError('Explicit source field path required')
    parts = path.split('.') if isinstance(path, str) else path
    value = json.loads(node['data'])
    for part in parts:
        value = value.get(part) if isinstance(value, dict) else None
    if not isinstance(value, str) or not value.strip() or value != witness['statement']:
        raise ValueError('Source witness differs from the complete original field')
    return node


def witnessed_peer(con, own, witness):
    queue, visited = deque([own['uid']]), set()
    while queue:
        uid = queue.popleft()
        if uid == witness['uid']:
            return True
        if uid in visited:
            continue
        visited.add(uid)
        for bridge in con.execute("SELECT * FROM bridges WHERE relation='SAME_CONCEPT' AND status='ACTIVE' AND (left_uid=? OR right_uid=?)", (uid, uid)):
            other = bridge['right_uid'] if bridge['left_uid'] == uid else bridge['left_uid']
            node = row_at(con, 'nodes', other)
            if node and node['visibility'] == 'ACTIVE' and role(con, node) == role(con, own):
                queue.append(other)
    return False


def scope_inventory(con, uid, post):
    answer = {}
    for name, table, column in (('edges_incoming', 'edges', 'parent_uid'),
                                ('edges_outgoing', 'edges', 'child_uid'),
                                ('typed_incoming', 'entity_relations', 'object_uid'),
                                ('typed_outgoing', 'entity_relations', 'subject_uid')):
        rows = [dict(r) for r in con.execute('SELECT * FROM ' + table + ' WHERE ' + column + '=? ORDER BY id', (uid,))]
        answer[name] = [r for r in rows if not post or r['source'] != SOURCE]
    answer['identity_bridges'] = [dict(r) for r in con.execute(
        'SELECT * FROM bridges WHERE left_uid=? OR right_uid=? ORDER BY id', (uid, uid))]
    return answer


def admitted(con, node):
    if not node or node['visibility'] != 'ACTIVE' or role(con, node) not in {'CLASS', 'MODEL', 'MODEL_FAMILY', 'INSTANCE'}:
        return False
    profile = row_at(con, 'node_profiles', node['uid'])
    attrs = json.loads(profile.get('attributes') or '{}') if profile else {}
    allowed_views = attrs.get('allowed_views')
    return not isinstance(allowed_views, list) or 'taxonomy' in allowed_views


def raw_parents(con, uid):
    child = row_at(con, 'nodes', uid)
    if not admitted(con, child):
        return []
    result = []
    for raw_peer in con.execute('SELECT * FROM nodes WHERE component_id=? AND visibility=?', (child['component_id'], 'ACTIVE')):
        peer = dict(raw_peer)
        if not admitted(con, peer):
            continue
        for table, left, right in (('edges', 'child_uid', 'parent_uid'),
                                    ('entity_relations', 'subject_uid', 'object_uid')):
            for edge in con.execute('SELECT * FROM ' + table + ' WHERE ' + left + '=?', (peer['uid'],)):
                parent = row_at(con, 'nodes', edge[right])
                valid_status = (table == 'edges' and edge['relation'] == 'IS_A' and edge['status'] in {'ACTIVE', 'BACKBONE_ACTIVE'}
                                or table == 'entity_relations' and edge['relation'] in {'DESIGN_TYPE_OF', 'NATIVE_DESIGN_PARENT', 'INSTANCE_OF'} and edge['status'] == 'ACTIVE')
                if (admitted(con, parent) and valid_status
                        and allowed(edge['relation'], role(con, peer), role(con, parent))
                        and parent['component_id'] != child['component_id']):
                    result.append(parent['uid'])
    return result


def reaches(con, start, destination):
    target = row_at(con, 'nodes', destination)
    queue, seen = deque([start]), set()
    while target and queue:
        node = row_at(con, 'nodes', queue.popleft())
        if not admitted(con, node) or node['component_id'] in seen:
            continue
        if node['component_id'] == target['component_id']:
            return True
        seen.add(node['component_id'])
        queue.extend(raw_parents(con, node['uid']))
    return False


def check_operation(con, inputs, manifest, op, post, operations=()):
    proof = op['proof']
    if (op['op'] != 'link' or op['source'] != SOURCE or not op['uri'].startswith('https://')
            or proof['kind'] != 'SOURCE_REVIEWED_WHOLE_NOMINAL_DESIGN_SCOPE'
            or proof.get('world_identity_assertion') is not False
            or proof.get('no_identity_merges') is not True
            or proof.get('whole_subject_scope_review') is not True or not proof.get('scope_observation')):
        raise ValueError('Conservative independently reviewed source link required')
    axis = op['classification_axis']
    if (axis != proof['classification_axis']
            or axis not in {'IS_A': {'physical_intension', 'class_intension'}, 'DESIGN_TYPE_OF': {'purpose', 'function', 'physical_intension'},
                             'NATIVE_DESIGN_PARENT': {'design_family'}, 'INSTANCE_OF': {'physical_intension'}}.get(op['relation'], set())):
        raise ValueError('Declared classification axis is incompatible with relation')
    child, parent = [row_at(con, 'nodes', op[k]) for k in ('uid', 'parent')]
    if (not child or not parent or any(n['visibility'] != 'ACTIVE' for n in (child, parent))
            or child['component_id'] == parent['component_id']
            or not allowed(op['relation'], role(con, child), role(con, parent))):
        raise ValueError('Grounded distinct endpoints and compatible actual roles required')
    for node, prefix in ((child, ''), (parent, 'parent_')):
        expected_profile = proof[prefix + 'before_profile']
        expected_normalization = proof[prefix + 'before_normalization_role']
        corrections = [o for o in operations if o['op'] == 'correct_role' and o['uid'] == node['uid']]
        if len(corrections) > 1:
            raise ValueError('Duplicate endpoint role adjudication')
        if corrections:
            correction = corrections[0]
            if (expected_profile != correction['before_profile']
                    or expected_normalization != correction['before_normalization_role']):
                raise ValueError('Nominal link before role differs from exact role-source timepoint')
            check_role_operation(con, inputs, correction, post)
            if post:
                expected_profile = correction['after_profile']
                expected_normalization = correction['after_normalization_role']
        if (node != proof[prefix + 'before_node']
                or row_at(con, 'node_profiles', node['uid']) != expected_profile
                or row_at(con, 'normalization_roles', node['uid']) != expected_normalization
                or sha(node['data']) != proof[prefix + 'native_record_sha256']):
            raise ValueError('Original object, source bytes, identity or role changed beyond exact source adjudication')
    witnesses = proof['source_witnesses']
    for witness in witnesses:
        actual_witness = check_witness(con, witness)
        endpoint = child if actual_witness['component_id'] == child['component_id'] else parent
        if (actual_witness['component_id'] not in {child['component_id'], parent['component_id']}
                or not witnessed_peer(con, endpoint, actual_witness)):
            raise ValueError('Source scope needs a real admitted same-role identity path to its endpoint')
    for node in {n['uid']: n for n in [child, parent, *[row_at(con, 'nodes', w['uid']) for w in witnesses]]}.values():
        declared = {(str(w['field_path']).split('.')[-1], w['statement']) for w in witnesses if w['uid'] == node['uid']}
        if declared != complete_fields(node) or not declared:
            raise ValueError('Whole own and parent retained scope fields must all be reviewed')
    locator = proof['source_review_locator']
    raw = read_input(inputs, locator['file'])
    review = json.loads(raw)
    if (sha(raw) != locator['sha256'] or review != proof['source_scope_review_record']
            or review.get('accepted_source_scope_only') is not True
            or [op['uid'], op['parent'], op['relation']] not in review.get('approved_source_directions', [])
            or any(locator[k] != op[k] for k in ('uid', 'parent', 'relation'))):
        raise ValueError('Independent complete source verdict does not approve this exact direction')
    if not proof['parent_conditions']:
        raise ValueError('Whole parent necessary conditions must be explicit')
    for condition in proof['parent_conditions']:
        if not condition['condition'] or not condition['exact_spans']:
            raise ValueError('Missing whole parent scope condition or source spans')
        for span in condition['exact_spans']:
            witness = witnesses[span['witness_index']]
            if not span['text'] or span['text'] not in witness['statement']:
                raise ValueError('A necessary scope condition cites no exact retained source span')
    composition = proof['composition_scope_review']
    if (composition.get('whole_parent_range_reviewed') is not True
            or composition.get('active_derivation_conflation_absent') is not True
            or not composition.get('scope_observation')):
        raise ValueError('Design derivation and whole nominal family range require explicit review')
    for item in proof['prior_assertions'] + composition['non_admitted_derivations']:
        before = item['before_assertion']
        expected = before
        same_batch_reviews = [o for o in operations if o['op'] == 'review_class_edge'
                              and item['table'] == 'edges' and o['before_assertion']['id'] == before['id']]
        if same_batch_reviews:
            if len(same_batch_reviews) != 1 or same_batch_reviews[0]['before_assertion'] != before:
                raise ValueError('Prior declaration withdrawal differs from its exact full original row')
            check_review_operation(con, inputs, same_batch_reviews[0], post)
            if post:
                expected = {**before, 'status': 'SOURCE_SCOPE_REVIEW'}
        if row_at(con, item['table'], before['id']) != expected or assertion_sha(before) != item['content_sha256']:
            raise ValueError('Original declaration content, status or source history changed')
    for item in composition['non_admitted_derivations']:
        if item['before_assertion']['status'] in ACTIVE:
            raise ValueError('A non-member derivative is still admitted as family membership')
    table, left, right = ('edges', 'child_uid', 'parent_uid') if op['relation'] == 'IS_A' else ('entity_relations', 'subject_uid', 'object_uid')
    rows = [dict(r) for r in con.execute('SELECT * FROM ' + table + ' WHERE ' + left + '=? AND ' + right + '=? AND relation=? AND source=?',
                                      (op['uid'], op['parent'], op['relation'], SOURCE))]
    if not post:
        if rows:
            raise ValueError('New source direction already exists')
    else:
        if len(rows) != 1 or rows[0]['status'] != 'ACTIVE':
            raise ValueError('Exactly one actual active nominal source direction required')
        actual = rows[0]
        data = json.loads(actual['data'])
        eid = 'usability:' + sha(dump(proof))
        evidence = row_at(con, 'evidence', eid)
        if (data.get('admission_basis') != proof or data.get('classification_axis') != axis
                or not evidence or evidence['payload'] != dump(proof)
                or evidence['payload_sha256'] != sha(dump(proof))
                or evidence['source_name'] != SOURCE or evidence['source_uri'] != op['uri']):
            raise ValueError('Actual evidence and whole scope declaration differ')
        if table == 'edges':
            if eid not in json.loads(actual['provenance']).get('evidence_ids', []) or data.get('eligible_for_final_dag') is not True:
                raise ValueError('Ordinary class bridge lost its grounded evidence or DAG admission')
        elif actual['evidence_id'] != eid or data.get('is_class_inclusion') is not False:
            raise ValueError('Typed relation lost evidence or was misrepresented as ordinary class inclusion')
        histories = con.execute('SELECT * FROM usability_changes WHERE stage=? AND object_type=? AND object_id=?',
                                ('nominal_design_scope_repairs', 'nominal_scope_link', op['uid'])).fetchall()
        if sum(json.loads(r['before_json']) == {'prior_assertions': proof['prior_assertions']}
               and json.loads(r['after_json']) == {'table': table, 'added_assertion': actual}
               and json.loads(r['evidence']) == proof for r in histories) != 1:
            raise ValueError('Exact full source change history is missing or duplicated')
        if reaches(con, op['parent'], op['uid']) or not reaches(con, op['uid'], 'wordnet31:00001740-n'):
            raise ValueError('Actual new source direction is cyclic or disconnected from the root')
    return {'uid': op['uid'], 'parent': op['parent'], 'relation': op['relation'],
            'complete_source_sha256': proof['native_record_sha256'], 'classification_axis': axis}


def check_review_operation(con, inputs, op, post):
    proof = op['proof']; before = op['before_assertion']
    if (op['op'] != 'review_class_edge' or op.get('table') != 'edges'
            or op['relation'] != 'IS_A' or op['classification_axis'] not in {'physical_intension', 'class_intension'}
            or before['child_uid'] != op['uid'] or before['parent_uid'] != op['parent']
            or before['relation'] != 'IS_A' or before['status'] != 'ACTIVE'
            or op.get('after_status', 'SOURCE_SCOPE_REVIEW') != 'SOURCE_SCOPE_REVIEW'
            or assertion_sha(before) != op['content_sha256']
            or proof.get('world_identity_assertion') is not False
            or proof.get('no_identity_merges') is not True
            or proof.get('whole_subject_scope_review') is not True):
        raise ValueError('An exact original over-narrow class assertion and whole-scope review required')
    retained = proof['withdrawn_scope_witness']
    if (retained.get('table') != 'edges' or retained.get('before_assertion') != before
            or retained.get('content_sha256') != assertion_sha(before)
            or retained.get('data_sha256') != sha(before['data'])):
        raise ValueError('Withdrawn original source scope bytes differ from the exact retained declaration')
    value = json.loads(before['data'])
    for part in retained['field_path']:
        value = value.get(part) if isinstance(value, dict) else None
    permitted_path = {'RETAINED_COMPLETE_SOURCE_STATEMENT': ['admission_basis', 'source_statement'],
                      'ORIGINAL_INFERENCE_SCOPE_UNPROVEN': ['classification_basis']}.get(retained.get('witness_kind'))
    if (not isinstance(value, str) or not value.strip() or value != retained['statement']
            or permitted_path is None or retained['field_path'] != permitted_path):
        raise ValueError('Withdrawal must preserve the complete original source or explicitly unproven inference text')
    locator = proof['source_review_locator']
    raw = read_input(inputs, locator['file']); review = json.loads(raw)
    if (sha(raw) != locator['sha256'] or review != proof['source_scope_review_record']
            or review.get('accepted_source_scope_only') is not True
            or any(locator[k] != op[k] for k in ('uid', 'parent', 'relation'))):
        raise ValueError('Exact original scope withdrawal is not independently source-approved')
    approvals = review.get('approved_source_reviews', [])
    key = [op['uid'], op['parent'], op['relation']]
    if key not in approvals:
        raise ValueError('Independent complete source verdict does not approve this withdrawal key')
    witnesses = proof['source_witnesses']
    endpoints = [row_at(con, 'nodes', op[k]) for k in ('uid', 'parent')]
    for witness in witnesses:
        actual_witness = check_witness(con, witness)
        if not any(endpoint and endpoint['component_id'] == actual_witness['component_id']
                   and witnessed_peer(con, endpoint, actual_witness) for endpoint in endpoints):
            raise ValueError('Withdrawal source context belongs to an unconnected object')
    for uid in {op['uid'], op['parent'], *[w['uid'] for w in witnesses]}:
        node = row_at(con, 'nodes', uid)
        declared = {(str(w['field_path']).split('.')[-1], w['statement']) for w in witnesses if w['uid'] == uid}
        if not node or not declared or declared != complete_fields(node):
            raise ValueError('Whole withdrawn endpoint or source scope was omitted')
    actual = row_at(con, 'edges', before['id'])
    expected = {**before, 'status': 'SOURCE_SCOPE_REVIEW'} if post else before
    if actual != expected:
        raise ValueError('Reviewed declaration changed beyond its exact status withdrawal')
    if post:
        histories = con.execute('SELECT * FROM usability_changes WHERE stage=? AND object_type=? AND object_id=?',
                                ('nominal_design_scope_repairs', 'class_scope_review', str(before['id']))).fetchall()
        if sum(json.loads(r['before_json']) == before
               and json.loads(r['after_json']) == {'status': 'SOURCE_SCOPE_REVIEW'}
               and json.loads(r['evidence']) == proof for r in histories) != 1:
            raise ValueError('Original source withdrawal lacks its exact complete evidence history')
    return {'uid': op['uid'], 'parent': op['parent'], 'relation': op['relation'],
            'reviewed_original_id': before['id'], 'after_status': 'SOURCE_SCOPE_REVIEW'}


def check_role_operation(con, inputs, op, post):
    proof = op['proof']
    if (op['op'] != 'correct_role' or op['parent'] != op['uid']
            or op['relation'] != 'ROLE_ADJUDICATION' or op['source'] != SOURCE
            or not op['uri'].startswith('https://')
            or proof.get('world_identity_assertion') is not False
            or proof.get('no_identity_merges') is not True
            or proof.get('whole_subject_scope_review') is not True
            or proof.get('kind') != 'SOURCE_REVIEWED_WHOLE_NOMINAL_DESIGN_SCOPE'
            or op.get('classification_axis') != 'source_grain'):
        raise ValueError('Exact conservative whole-source role adjudication required')
    node = row_at(con, 'nodes', op['uid'])
    if (node != proof['before_node'] or sha(node['data']) != proof['native_record_sha256']
            or node['visibility'] != 'ACTIVE'):
        raise ValueError('Original whole role-source object changed')
    locator = proof['source_review_locator']
    raw = read_input(inputs, locator['file']); review = json.loads(raw)
    before = op['before_profile']; old_norm = op['before_normalization_role']
    before_role = before['node_kind'] if before else {
        'model': 'MODEL', 'product_model': 'MODEL', 'aircraft_model': 'MODEL', 'vehicle_model': 'MODEL',
        'series': 'MODEL_FAMILY', 'model_family': 'MODEL_FAMILY', 'configuration': 'CONFIGURATION',
        'instance': 'INSTANCE', 'unknown': 'UNKNOWN', 'type_or_product_model': 'UNKNOWN',
        'biological_variant': 'BIOLOGICAL_VARIANT', 'dataset_category': 'DATASET_CATEGORY',
        'manufacturer': 'ORGANIZATION', 'attribute': 'ATTRIBUTE'}.get((node.get('rank') or '').lower(), 'CLASS')
    approved = [r for r in review.get('approved_source_role_corrections', []) if r['uid'] == op['uid']]
    if (sha(raw) != locator['sha256'] or review != proof['source_scope_review_record']
            or review.get('accepted_source_scope_only') is not True or len(approved) != 1
            or approved[0]['before_role'] != before_role
            or approved[0]['source_role_scope_kind'] != op['after_profile']['node_kind']
            or approved[0]['before_profile'] != op['before_profile']
            or approved[0]['before_normalization'] != op['before_normalization_role']):
        raise ValueError('Whole independent source grain verdict does not approve the role transition')
    witnesses = proof['source_witnesses']
    for witness in witnesses:
        if witness['uid'] != op['uid']:
            raise ValueError('Role evidence must be the complete own source object')
        check_witness(con, witness)
    declared = {(str(w['field_path']).split('.')[-1], w['statement']) for w in witnesses}
    if not declared or declared != complete_fields(node):
        raise ValueError('Complete own role-source context omitted or changed')
    # Preserve source rank, first normalization history and every view limit.
    attrs = json.loads(before['attributes']) if before else {}
    source_role = old_norm['source_role'] if old_norm else node.get('rank') or 'UNSPECIFIED'
    native_rank = attrs.get('native_rank', node.get('rank'))
    target = op['after_profile']['node_kind']
    contracts = {
        'WHOLE_NOMINAL_MULTIMODEL_PROGRAMME': ('MODEL_FAMILY', 'VERIFIED'),
        'OWNED_NAMED_REUSABLE_DESIGN_PROGRAMME': ('MODEL', 'VERIFIED'),
        'OWNED_NAMED_OPERATIONAL_PHYSICAL_INSTANCE': ('INSTANCE', 'VERIFIED'),
        'SOURCE_NOMINAL_OR_INDIVIDUAL_GRAIN_PENDING': ('UNKNOWN', 'REVIEW'),
    }
    declared = contracts.get(proof.get('source_role_scope_kind'))
    if (declared is None or declared != (target, proof.get('role_status'))
            or target == before_role or proof.get('source_role') != source_role
            or proof.get('native_rank') != native_rank):
        raise ValueError('Unreviewed role grain, original source rank or confidence differs')
    if target == 'MODEL_FAMILY' and before_role not in {'MODEL', 'MODEL_FAMILY'}:
        raise ValueError('Nominal family correction requires an existing evidenced design role')
    eid = 'usability:' + sha(dump(proof))
    attrs.update(source_role=source_role, native_rank=native_rank,
                 role_status=declared[1], role_evidence_id=eid)
    attrs.pop('canonical_scope_guard', None); attrs.pop('canonical_scope_evidence_id', None)
    if target == 'UNKNOWN':
        decision = approved[0]
        if (decision.get('after_role_status') != 'REVIEW' or decision.get('allowed_views') != []
                or decision.get('quarantine_role_grain') is not True or proof.get('allowed_views') != []):
            raise ValueError('Pending grain requires explicit independent review-only view quarantine')
        attrs['allowed_views'] = []
    elif proof.get('allowed_views') is not None and proof['allowed_views'] != attrs.get('allowed_views'):
        raise ValueError('Verified grain cannot loosen source view admission')
    if before:
        expected_profile = {**before, 'node_kind': target, 'source_uri': op['uri'],
                            'evidence_id': eid, 'attributes': dump(attrs)}
    else:
        expected_profile = {'uid': op['uid'], 'node_kind': target, 'domain': node.get('domain') or '',
                            'source_uri': op['uri'], 'evidence_id': eid, 'attributes': dump(attrs)}
    if old_norm:
        expected_norm = {**old_norm, 'canonical_role': target, 'evidence_id': eid, 'source': SOURCE}
        if target == 'UNKNOWN':
            expected_norm['status'] = 'REVIEW'
    else:
        expected_norm = {'uid': op['uid'], 'source_role': source_role, 'canonical_role': target,
                         'status': declared[1], 'evidence_id': eid, 'source': SOURCE,
                         'prior_profile': dump(before or {})}
    if op['after_profile'] != expected_profile or op['after_normalization_role'] != expected_norm:
        raise ValueError('Role migration changed unrelated profile, source history or view fields')
    for table, suffix in (('node_profiles', 'profile'), ('normalization_roles', 'normalization_role')):
        if row_at(con, table, op['uid']) != op[('after_' if post else 'before_') + suffix]:
            raise ValueError('Actual role adjudication differs from exact approved transition')
    if post:
        evidence = row_at(con, 'evidence', eid)
        if (not evidence or evidence['payload'] != dump(proof) or evidence['payload_sha256'] != sha(dump(proof))
                or evidence['source_name'] != SOURCE or evidence['source_uri'] != op['uri']):
            raise ValueError('Actual role evidence is not bound to its whole original source')
        histories = con.execute('SELECT * FROM usability_changes WHERE stage=? AND object_type=? AND object_id=?',
                                ('nominal_design_scope_repairs', 'role_source_adjudication', op['uid'])).fetchall()
        prior = {'profile': before, 'normalization_role': old_norm}
        after = {'profile': expected_profile, 'normalization_role': expected_norm}
        if sum(json.loads(r['before_json']) == prior and json.loads(r['after_json']) == after
               and json.loads(r['evidence']) == proof for r in histories) != 1:
            raise ValueError('Exact source-role before and after history missing or duplicated')
    return {'uid': op['uid'], 'parent': op['parent'], 'relation': op['relation'],
            'before_role': before_role, 'after_role': expected_profile['node_kind']}


def run(database, inputs, output, preflight=False, allow_unsealed_inputs=False):
    database, inputs, output = [Path(p).resolve() for p in (database, inputs, output)]
    if output.exists() or output == database or output.is_relative_to(inputs):
        raise ValueError('Independent audit output must be a new artifact outside preserved inputs')
    raw_manifest = read_input(inputs, INPUT_NAME)
    manifest = json.loads(raw_manifest)
    raw_ops = read_input(inputs, manifest['operations_file'])
    ops = [json.loads(line) for line in raw_ops.decode().splitlines() if line]
    if (manifest['schema'] != 'FINEATLAS_NOMINAL_DESIGN_SCOPE_REPAIRS_V1'
            or manifest['operations_sha256'] != sha(raw_ops)
            or type(manifest['operation_count']) is not int or manifest['operation_count'] != len(ops) or not ops):
        raise ValueError('Exact complete nonempty source operation census required')
    if any(Path(str(database) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('Independent immutable audit requires a closed database without sidecars')
    con = sqlite3.connect(database.as_uri() + '?mode=ro&immutable=1', uri=True)
    con.row_factory = sqlite3.Row
    metadata = {r['key']: json.loads(r['value']) for r in con.execute('SELECT * FROM metadata')}
    errors, checked, seen = [], [], set()
    try:
        for item in manifest['semantic_review_files']:
            if sha(read_input(inputs, item['file'])) != item['sha256']:
                raise ValueError('Portable whole source review inventory bytes differ')
        if not allow_unsealed_inputs:
            review_raw = read_input(inputs, manifest['source_review_file'])
            review = json.loads(review_raw)
            if (sha(review_raw) != manifest['source_review_sha256']
                    or review.get('accepted_source_scope_only') is not True
                    or review.get('operations_sha256') != sha(raw_ops)
                    or sorted(review.get('approved_keys', [])) != sorted([o['uid'], o['parent'], o['relation']] for o in ops)):
                raise ValueError('Exact independent batch source review missing')
            binding = manifest['completed_parent_binding']
            if set(binding) != {'database_revision', 'frozen_manifest_sha256'}:
                raise ValueError('Exact complete parent binding missing')
            if preflight:
                if (binding['database_revision'] != metadata['database_revision']
                        or binding['frozen_manifest_sha256'] != sha(json.dumps(metadata['structure_frozen_build_manifest'], sort_keys=True, ensure_ascii=False))):
                    raise ValueError('Actual completed preflight parent differs')
            else:
                lineage = metadata['structure_nominal_design_resume_parent']
                applied = metadata['nominal_design_scope_repairs']
                if (lineage.get('repair_recipe') != 'resume_nominal_design_scope_repairs.py'
                        or lineage.get('parent_revision') != binding['database_revision']
                        or lineage.get('previous_source_stages_replayed') is not False
                        or lineage.get('previous_repair_stages_replayed') is not False
                        or lineage.get('all_derived_indexes_recomputed') is not True
                        or applied.get('manifest_sha256') != sha(raw_manifest)
                        or applied.get('operations_sha256') != sha(raw_ops)
                        or applied.get('operation_count') != len(ops)
                        or applied.get('completed_parent_binding') != binding
                        or any(applied.get(k) != 0 for k in ('new_nodes', 'identity_changes', 'mapping_changes'))
                        or applied.get('role_changes') != sum(o['op'] == 'correct_role' for o in ops)
                        or applied.get('class_scope_reviews') != sum(o['op'] == 'review_class_edge' for o in ops)
                        or applied.get('source_assertions_added') != sum(o['op'] == 'link' for o in ops)
                        or applied.get('operation_kinds') != dict(Counter(o['op'] for o in ops))
                        or applied.get('allowed_role_differences') != sorted(o['uid'] for o in ops if o['op'] == 'correct_role')
                        or applied.get('reviewed_class_assertion_ids') != sorted(o['before_assertion']['id'] for o in ops if o['op'] == 'review_class_edge')):
                    raise ValueError('Actual applied metadata or parent lineage differs')
                frozen = metadata['structure_frozen_build_manifest']
                for name in [INPUT_NAME, manifest['operations_file'], manifest['source_review_file'], *[r['file'] for r in manifest['semantic_review_files']]]:
                    if frozen['inputs'].get(name) != sha(read_input(inputs, name)):
                        raise ValueError('Actual source review input was not frozen')
                if frozen['code'].get('scripts/audit_nominal_design_scope_repairs.py') != sha(Path(__file__).read_bytes()):
                    raise ValueError('Actual independent auditor bytes were not frozen')
        affected = {o[k] for o in ops for k in ('uid', 'parent')}
        expanded = {r['uid'] for uid in affected for r in con.execute('SELECT uid FROM nodes WHERE component_id=(SELECT component_id FROM nodes WHERE uid=?)', (uid,))}
        if set(manifest['scope_inventories']) != expanded:
            raise ValueError('Full affected identity components were not inventoried')
        for uid in expanded:
            expected_inventory = json.loads(dump(manifest['scope_inventories'][uid]))
            for op in ops:
                if op['op'] == 'review_class_edge':
                    check_review_operation(con, inputs, op, not preflight)
                    for name in ('edges_incoming', 'edges_outgoing'):
                        for before in expected_inventory[name]:
                            if before['id'] == op['before_assertion']['id']:
                                if before != op['before_assertion']:
                                    raise ValueError('Original inventory does not match exact source review before row')
                                if not preflight:
                                    before['status'] = 'SOURCE_SCOPE_REVIEW'
            if scope_inventory(con, uid, not preflight) != expected_inventory:
                raise ValueError('An original affected scope declaration changed beyond exact scope review: ' + uid)
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
        errors.append({'kind': 'FROZEN_PARENT_OR_ORIGINAL_SCOPE_CHANGED', 'reason': str(exc)})
    for op in ops:
        try:
            proof = op['proof']
            if (op['source'] != SOURCE or not op['uri'].startswith('https://')
                    or proof.get('kind') != 'SOURCE_REVIEWED_WHOLE_NOMINAL_DESIGN_SCOPE'
                    or proof.get('classification_axis') != op['classification_axis']
                    or proof.get('world_identity_assertion') is not False
                    or proof.get('no_identity_merges') is not True
                    or proof.get('whole_subject_scope_review') is not True
                    or not proof.get('scope_observation') or not proof.get('license')):
                raise ValueError('Conservative complete source scope, attribution and licensing required')
            key = op['uid'], op['parent'], op['relation']
            if op['op'] == 'review_class_edge':
                key = (*key, op['table'], op['before_assertion']['id'])
            if key in seen:
                raise ValueError('Duplicate source direction')
            seen.add(key)
            if op['op'] == 'correct_role':
                checked.append(check_role_operation(con, inputs, op, not preflight))
            elif op['op'] == 'review_class_edge':
                checked.append(check_review_operation(con, inputs, op, not preflight))
            else:
                checked.append(check_operation(con, inputs, manifest, op, not preflight, ops))
        except (ValueError, KeyError, TypeError, IndexError, OSError, sqlite3.Error) as exc:
            errors.append({'kind': 'ACTUAL_NOMINAL_SCOPE_OR_DIRECTION_DIFFERS', 'uid': op.get('uid'),
                           'parent': op.get('parent'), 'reason': str(exc)})
    if not preflight:
        actual_count = sum(con.execute('SELECT count(*) FROM ' + table + ' WHERE source=?', (SOURCE,)).fetchone()[0]
                           for table in ('edges', 'entity_relations'))
        expected_links = sum(o['op'] == 'link' for o in ops)
        if actual_count != expected_links:
            errors.append({'kind': 'ADDED_SOURCE_CENSUS_DIFFERS', 'actual': actual_count, 'expected': expected_links})
    report = {'schema': 'FINEATLAS_INDEPENDENT_NOMINAL_DESIGN_SCOPE_AUDIT_V1',
              'database': str(database), 'database_revision': metadata.get('database_revision'),
              'manifest_sha256': sha(raw_manifest), 'operations_sha256': sha(raw_ops),
              'operation_count': len(ops), 'operations': dict(Counter(o['relation'] for o in ops)),
              'pass': not errors, 'preflight_only': bool(preflight or allow_unsealed_inputs),
              'unsealed_source_diagnostic': bool(allow_unsealed_inputs),
              'candidate_acceptance': bool(not preflight and not allow_unsealed_inputs and not errors),
              'checked_complete_source': checked, 'errors': errors}
    con.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in {'checked_complete_source', 'errors'}}))
    return not errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--allow-unsealed-inputs', action='store_true')
    args = parser.parse_args()
    raise SystemExit(0 if run(args.database, args.inputs, args.output, args.preflight, args.allow_unsealed_inputs) else 1)
