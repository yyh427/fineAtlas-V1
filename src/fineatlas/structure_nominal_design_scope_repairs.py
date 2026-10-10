"""Append source-reviewed purpose, nominal-family and generic class bridges.

This checkpoint preserves every original source object, identity,
mapping and declaration. Evidenced grain corrections and exact scope reviews
retain complete before snapshots. Design derivation is never promoted to
family membership. Source approval does not certify a fine distance result.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json

from .nominal_design_scope_contracts import dump, node, safe_input, sha, validate_operations

INPUT_NAME = 'structure_nominal_design_scope_repairs.json'
OPERATION_NAME = 'hierarchy_nominal_design_scope_repairs.jsonl'
METADATA_KEY = 'nominal_design_scope_repairs'
SOURCE = 'Reviewed complete nominal design and generic class scope'


def apply_nominal_design_scope_repairs(m):
    if not (m.inputs / INPUT_NAME).exists():
        return {'status': 'not_requested'}
    m.c.execute('SAVEPOINT nominal_scope_append')
    try:
        result = _apply_nominal_design_scope_repairs(m)
        m.c.execute('RELEASE SAVEPOINT nominal_scope_append')
        m.c.commit()
        return result
    except Exception:
        m.c.execute('ROLLBACK TO SAVEPOINT nominal_scope_append')
        m.c.execute('RELEASE SAVEPOINT nominal_scope_append')
        raise


def _apply_nominal_design_scope_repairs(m):
    path = m.inputs / INPUT_NAME
    if not path.exists():
        return {'status': 'not_requested'}
    manifest = json.loads(path.read_bytes())
    if manifest['operations_file'] != OPERATION_NAME:
        raise ValueError('Unexpected nominal design operations input')
    raw = safe_input(m.inputs, OPERATION_NAME).read_bytes()
    operations = [json.loads(line) for line in raw.decode().splitlines() if line]
    if sha(raw) != manifest['operations_sha256']:
        raise ValueError('Frozen nominal design operation bytes changed')
    review_raw = safe_input(m.inputs, manifest['source_review_file']).read_bytes()
    if sha(review_raw) != manifest['source_review_sha256']:
        raise ValueError('Independent exact source operation review bytes changed')
    reviews = {}
    for item in manifest['semantic_review_files']:
        name = item['file']
        data = safe_input(m.inputs, name).read_bytes()
        if name in reviews or sha(data) != item['sha256']:
            raise ValueError('Complete source review inventory is duplicated or changed')
        reviews[name] = {'sha256': sha(data), 'record': json.loads(data)}
    validate_operations(m.c, manifest, operations, json.loads(review_raw), reviews, SOURCE)
    protected = ('nodes', 'node_profiles', 'normalization_roles', 'bridges', 'dataset_targets', 'dataset_mapping_checks')
    def fingerprint(table, excluding=()):
        digest = hashlib.sha256()
        order = 'uid' if table in ('nodes', 'node_profiles', 'normalization_roles') else 'id' if table == 'bridges' else 'dataset,class_id'
        for row in m.c.execute('SELECT * FROM '+table+' ORDER BY '+order):
            if table in ('node_profiles', 'normalization_roles') and row['uid'] in excluding:
                continue
            digest.update((dump(dict(row))+'\n').encode())
        return digest.hexdigest()
    protected_before = {t: fingerprint(t) for t in protected}
    role_ops = {o['uid']: o for o in operations if o['op'] == 'correct_role'}
    role_tables = ('node_profiles', 'normalization_roles')
    role_unaffected_before = {t: fingerprint(t, role_ops) for t in role_tables}
    old_rows = {t: {r['id']: sha(dump(dict(r))) for r in m.c.execute('SELECT * FROM '+t)}
                for t in ('edges', 'entity_relations')}
    for op in operations:
        if op['op'] == 'review_class_edge':
            old_rows['edges'][op['before_assertion']['id']] = sha(dump(dict(op['before_assertion'], status='SOURCE_SCOPE_REVIEW')))
    canonical = set()
    # Apply source-grain decisions before validating the resulting link roles.
    for op in operations:
        if op['op'] != 'correct_role':
            continue
        m.role(op['uid'], op['after_profile']['node_kind'], op['proof'], SOURCE, op['uri'])
        if op['after_profile']['node_kind'] == 'UNKNOWN':
            # The old writer remains immutable; this local exact helper changes
            # current certainty only after the complete source review above.
            row = m.c.execute('SELECT attributes FROM node_profiles WHERE uid=?', (op['uid'],)).fetchone()
            attrs = json.loads(row['attributes']); attrs.update(role_status='REVIEW', allowed_views=[])
            m.c.execute('UPDATE node_profiles SET attributes=? WHERE uid=?', (dump(attrs), op['uid']))
            m.c.execute("UPDATE normalization_roles SET status='REVIEW' WHERE uid=?", (op['uid'],))
        profile = dict(m.c.execute('SELECT * FROM node_profiles WHERE uid=?', (op['uid'],)).fetchone())
        normalization = dict(m.c.execute('SELECT * FROM normalization_roles WHERE uid=?', (op['uid'],)).fetchone())
        if profile != op['after_profile'] or normalization != op['after_normalization_role']:
            raise ValueError('Real role output differs from the frozen complete after state')
        m.change(METADATA_KEY, 'role_source_adjudication', op['uid'],
                 {'profile': op['before_profile'], 'normalization_role': op['before_normalization_role']},
                 {'profile': profile, 'normalization_role': normalization}, op['proof'])
    for op in operations:
        if op['op'] == 'correct_role':
            continue
        proof = op['proof']
        axis = op['classification_axis']
        if op['op'] == 'review_class_edge':
            original = op['before_assertion']
            m.c.execute("UPDATE edges SET status='SOURCE_SCOPE_REVIEW' WHERE id=?", (original['id'],))
            m.change(METADATA_KEY, 'class_scope_review', str(original['id']), original,
                     {'status': 'SOURCE_SCOPE_REVIEW'}, proof)
            continue
        child, parent = node(m.c, op['uid']), node(m.c, op['parent'])
        canonical.add((child['component_id'], parent['component_id'], op['relation']))
        if op['relation'] == 'IS_A':
            eid = m.evidence(SOURCE, op['uri'], proof, 'HIERARCHY_REFINEMENT')
            cursor = m.c.execute('INSERT INTO edges(child_uid,parent_uid,relation,original_relation,facet_family,classification_basis,navigation_role,source,source_relation,confidence,provenance,data,layer,status,reason) VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)',
                                 (op['uid'], op['parent'], 'IS_A', 'IS_A', 'NATIVE_OBJECT_KIND', proof['kind'], 'SOURCE_VALIDATED', SOURCE, 'COMPLETE_GENERIC_SOURCE_SCOPE', dump({'evidence_ids': [eid]}), dump({'eligible_for_final_dag': True, 'admission_basis': proof, 'classification_axis': axis}), 'v1.8-hierarchy-review', 'ACTIVE', 'Independent complete source intension and whole parent range review'))
            table = 'edges'
            added = dict(m.c.execute('SELECT * FROM edges WHERE id=?', (cursor.lastrowid,)).fetchone())
        else:
            m.typed(op['uid'], op['parent'], op['relation'], proof, SOURCE, op['uri'])
            row = m.c.execute('SELECT id,data FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?', (op['uid'], op['parent'], op['relation'], SOURCE)).fetchone()
            value = json.loads(row['data'])
            value['classification_axis'] = axis
            m.c.execute('UPDATE entity_relations SET data=? WHERE id=?', (dump(value), row['id']))
            table = 'entity_relations'
            added = dict(m.c.execute('SELECT * FROM entity_relations WHERE id=?', (row['id'],)).fetchone())
        m.change(METADATA_KEY, 'nominal_scope_link', op['uid'], {'prior_assertions': proof['prior_assertions']}, {'table': table, 'added_assertion': added}, proof)
    if any(fingerprint(t) != protected_before[t] for t in protected if t not in role_tables):
        raise ValueError('Nominal source scope repair changed source identities or mappings')
    for table in role_tables:
        if fingerprint(table, role_ops) != role_unaffected_before[table]:
            raise ValueError('Role tables differ outside exact frozen source adjudications')
        for uid, op in role_ops.items():
            row = m.c.execute('SELECT * FROM '+table+' WHERE uid=?', (uid,)).fetchone()
            if not row or dict(row) != op['after_profile' if table == 'node_profiles' else 'after_normalization_role']:
                raise ValueError('Actual role table differs from frozen complete after state')
    reviewed = {o['before_assertion']['id'] for o in operations if o['op'] == 'review_class_edge'}
    for table, rows in old_rows.items():
        seen, total = 0, 0
        for row in m.c.execute('SELECT * FROM '+table):
            total += 1
            if row['id'] in rows:
                seen += 1
                if sha(dump(dict(row))) != rows[row['id']]:
                    raise ValueError('Nominal source scope repair changed an original hierarchy declaration')
        added = sum(o['op'] == 'link' and (o['relation'] == 'IS_A') == (table == 'edges') for o in operations)
        if seen != len(rows) or total != len(rows)+added:
            raise ValueError('Source declaration census differs outside exact appended assertions')
    counts = dict(Counter(o['relation'] for o in operations))
    axes = dict(Counter(o['classification_axis'] for o in operations))
    m.c.execute('INSERT INTO source_catalogs VALUES(?,?,?,?,?)', ('Hierarchy refinement: '+SOURCE, operations[0]['uri'], 'Source-derived factual scope assertions; complete original source records and attribution retained', sha(raw), dump({'operation_count': len(operations), 'source_review_sha256': manifest['source_review_sha256'], 'no_identity_or_mapping_promotions': True})))
    changes = dict(Counter(o['op'] for o in operations))
    result = {'status': 'PASS', 'source_assertions_added': changes.get('link', 0), 'class_scope_reviews': changes.get('review_class_edge', 0), 'distinct_canonical_directions_asserted': len(canonical), 'operations': counts, 'operation_kinds': changes, 'classification_axes': axes, 'new_nodes': 0, 'role_changes': len(role_ops), 'identity_changes': 0, 'mapping_changes': 0}
    m.meta(METADATA_KEY, {**result, 'manifest_sha256': sha(path.read_bytes()), 'operations_sha256': sha(raw), 'operation_count': len(operations), 'completed_parent_binding': manifest['completed_parent_binding'], 'protected_table_hashes': protected_before, 'protected_table_hashes_after': {t: fingerprint(t) for t in protected}, 'allowed_role_differences': sorted(role_ops), 'reviewed_class_assertion_ids': sorted(reviewed), 'source_declarations_preserved': True, 'fine_distance_recovery_not_inferred': True, 'navigation_disabled_source_grain_uids': sorted(o['uid'] for o in role_ops.values() if o['after_profile']['node_kind']=='UNKNOWN')})
    return result
