"""Exact source contracts for additive nominal design and class connections.

Independent complete-range review supplies the semantic judgement. This module
binds that judgement to real source fields, roles, old declarations and the
current composition inventory; names and provider relations are never approval.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .hierarchy import source_assertion_sha256, validate_link_roles
from .semantics import role_expression
from .structure_owned_scope_repairs import validate_batch_cycles


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def safe_input(inputs, name):
    if not isinstance(name, str) or Path(name).name != name or name in ('', '.', '..'):
        raise ValueError('Source review must use a safe frozen input filename')
    return inputs / name


def node(c, uid):
    return c.execute('SELECT n.*, '+role_expression('n', 'p')+' role FROM nodes n '
                     'LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?', (uid,)).fetchone()


def field_value(value, path):
    for part in path.split('.') if isinstance(path, str) else path:
        if isinstance(value, list) and part.isdecimal():
            value = value[int(part)]
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise ValueError('Complete owned source field is missing')
    return value


def complete_fields(data):
    """All retained definition fields, without choosing a convenient short one."""
    result = {}
    keys = {'description', 'wikidata_description', 'definition', 'wikipedia_intro', 'gloss'}
    for prefix, record in [('', data), ('evidence_record.', data.get('evidence_record', {}))]:
        if isinstance(record, dict):
            result.update({prefix+k: v for k, v in record.items()
                           if k in keys and isinstance(v, str) and v.strip()})
    return result


def source_report(op, semantic_reviews, approval_field):
    p = op['proof']
    locator = p['source_review_locator']
    review = semantic_reviews.get(locator['file'])
    expected = {'file': locator['file'], 'sha256': review['sha256'] if review else None,
                'uid': op['uid'], 'parent': op['parent'], 'relation': op['relation']}
    if not review or locator != expected:
        raise ValueError('Independent whole-scope source locator changed')
    report = review['record']
    if report != p['source_scope_review_record'] or report.get('accepted_source_scope_only') is not True:
        raise ValueError('Independent complete source review changed')
    if approval_field != 'approved_source_role_corrections':
        if [op['uid'], op['parent'], op['relation']] not in report.get(approval_field, []):
            raise ValueError('Source operation has no independent complete range approval')
    return report


def validate_role(c, op, semantic_reviews):
    p = op['proof']
    actual = endpoint_before(c, op['uid'], p)
    if op['uid'] != op['parent'] or op['relation'] != 'ROLE_ADJUDICATION' or op['classification_axis'] != 'source_grain':
        raise ValueError('Role correction must describe this same source object')
    if op['before_profile'] != p['before_profile'] or op['before_normalization_role'] != p['before_normalization_role']:
        raise ValueError('Role original snapshots disagree')
    target = op['after_profile']['node_kind']
    if actual['role'] not in {'MODEL', 'MODEL_FAMILY'} or target not in {'MODEL', 'MODEL_FAMILY'} or target == actual['role']:
        raise ValueError('This contract only corrects evidenced nominal programme grain')
    if p.get('source_role_scope_kind') != 'WHOLE_NOMINAL_MULTIMODEL_PROGRAMME' or p.get('role_status') != 'VERIFIED':
        raise ValueError('Whole nominal programme scope adjudication is missing')
    report = source_report(op, semantic_reviews, 'approved_source_role_corrections')
    records = report.get('approved_source_role_corrections', [])
    if not any(r['uid'] == op['uid'] and r['before_role'] == actual['role'] and r['source_role_scope_kind'] == target
               and r['before_profile'] == op['before_profile'] and r['before_normalization'] == op['before_normalization_role'] for r in records):
        raise ValueError('Independent source role decision does not match its exact before scope')
    # Compute the unchanged Migration.role encoding independently before writing.
    prior = op['before_profile']
    attrs = json.loads(prior['attributes'])
    eid = 'usability:'+sha(dump(p))
    if p.get('allowed_views') is not None:
        attrs['allowed_views'] = p['allowed_views']
    attrs['source_role'] = p.get('source_role', attrs.get('source_role', actual['rank'] or 'UNSPECIFIED'))
    attrs.update(native_rank=p.get('native_rank', attrs.get('native_rank', actual['rank'])),
                 role_status='VERIFIED', role_evidence_id=eid)
    attrs.pop('canonical_scope_guard', None)
    attrs.pop('canonical_scope_evidence_id', None)
    after = dict(prior, node_kind=target, source_uri=op['uri'], evidence_id=eid, attributes=dump(attrs))
    norm = op['before_normalization_role']
    if norm:
        after_norm = dict(norm, canonical_role=target, evidence_id=eid, source=op['source'])
    else:
        after_norm = {'uid': op['uid'], 'source_role': p.get('source_role') or actual['rank'] or 'UNSPECIFIED',
                      'canonical_role': target, 'status': 'VERIFIED', 'evidence_id': eid,
                      'source': op['source'], 'prior_profile': dump(prior)}
    if after != op['after_profile'] or after_norm != op['after_normalization_role']:
        raise ValueError('Role output differs from real Migration canonical encoding')
    if norm and (p.get('source_role') != norm['source_role'] or norm['status'] != 'VERIFIED'):
        raise ValueError('Original normalization source role and confidence must be retained')
    return actual


def validate_review(c, op, semantic_reviews):
    p = op['proof']
    row = exact_assertion(c, op)
    if op.get('table') != 'edges' or op['relation'] != 'IS_A' or op['classification_axis'] not in {'physical_intension', 'class_intension'} or row['relation'] != 'IS_A' or row['status'] != 'ACTIVE':
        raise ValueError('Class review must precisely retire one active original inclusion')
    if (row['child_uid'], row['parent_uid']) != (op['uid'], op['parent']):
        raise ValueError('Class review endpoints differ from the original assertion')
    source_report(op, semantic_reviews, 'approved_source_reviews')
    w = p['withdrawn_scope_witness']
    if w['table'] != op['table'] or w['before_assertion'] != op['before_assertion'] or w['content_sha256'] != op['content_sha256']:
        raise ValueError('Withdrawn range must bind this complete original assertion')
    if sha(row['data']) != w['data_sha256'] or field_value(json.loads(row['data']), w['field_path']) != w['statement'] or not w['statement']:
        raise ValueError('Original retained assertion range witness changed')
    expected_paths = {'RETAINED_COMPLETE_SOURCE_STATEMENT': ['admission_basis', 'source_statement'],
                      'ORIGINAL_INFERENCE_SCOPE_UNPROVEN': ['classification_basis']}
    if w.get('witness_kind') not in expected_paths or w['field_path'] != expected_paths[w['witness_kind']]:
        raise ValueError('Retained source statements and unproven inference scopes must remain distinct')
    return endpoint_before(c, op['uid'], p), endpoint_before(c, op['parent'], p, 'parent_')


def validate_root_closure(c, operations, role_overrides):
    """Check the planned actual-role graph, including shared source ancestors."""
    root = c.execute("SELECT value FROM metadata WHERE key='root_uid'").fetchone()
    root_node = node(c, json.loads(root[0])) if root else None
    if not root_node or root_node['visibility'] != 'ACTIVE' or root_node['role'] != 'CLASS':
        raise ValueError('The complete parent has no admitted canonical root')
    root_component = root_node['component_id']
    retired = {o['before_assertion']['id'] for o in operations if o['op'] == 'review_class_edge'}
    proposed = {}
    for o in operations:
        if o['op'] == 'link':
            proposed.setdefault(node(c, o['uid'])['component_id'], set()).add(node(c, o['parent'])['component_id'])
    cache = {}
    def admitted(n):
        if not n or n['visibility'] != 'ACTIVE':
            return False
        profile = c.execute('SELECT * FROM node_profiles WHERE uid=?', (n['uid'],)).fetchone()
        # Existing unified SOURCE admission maps to the taxonomy source view.
        attrs = json.loads(profile['attributes']) if profile else {}
        allowed = attrs.get('allowed_views')
        return not isinstance(allowed, list) or 'taxonomy' in allowed
    def parents(component):
        if component in cache:
            return cache[component]
        result = set(proposed.get(component, ()))
        for peer in c.execute('SELECT uid FROM nodes WHERE component_id=?', (component,)).fetchall():
            a = node(c, peer['uid'])
            if not admitted(a):
                continue
            ar = role_overrides.get(a['uid'], a['role'])
            rows = [('edges', r) for r in c.execute("SELECT * FROM edges WHERE child_uid=? AND status IN ('ACTIVE','BACKBONE_ACTIVE') AND relation='IS_A'", (a['uid'],))]
            rows += [('entity_relations', r) for r in c.execute("SELECT * FROM entity_relations WHERE subject_uid=? AND status='ACTIVE' AND relation IN ('DESIGN_TYPE_OF','NATIVE_DESIGN_PARENT')", (a['uid'],))]
            for table, r in rows:
                if table == 'edges' and r['id'] in retired:
                    continue
                b = node(c, r['parent_uid'] if table == 'edges' else r['object_uid'])
                if not admitted(b):
                    continue
                try:
                    validate_link_roles(r['relation'], ar, role_overrides.get(b['uid'], b['role']))
                except ValueError:
                    continue
                if b['component_id'] != component:
                    result.add(b['component_id'])
        cache[component] = result
        return result
    starts = {node(c, o['parent'] if o['op'] == 'link' else o['uid'])['component_id'] for o in operations}
    for start in starts:
        pending, seen = [start], set()
        while pending:
            current = pending.pop()
            if current == root_component:
                break
            if current not in seen:
                seen.add(current)
                pending.extend(parents(current))
        else:
            raise ValueError('Reviewed source object has no legitimate planned root path')


def inventory(c, uid):
    queries = {
        'edges_incoming': ('edges', 'parent_uid'),
        'edges_outgoing': ('edges', 'child_uid'),
        'typed_incoming': ('entity_relations', 'object_uid'),
        'typed_outgoing': ('entity_relations', 'subject_uid'),
    }
    result = {k: [dict(r) for r in c.execute('SELECT * FROM '+t+' WHERE '+f+'=? ORDER BY id', (uid,))]
              for k, (t, f) in queries.items()}
    result['identity_bridges'] = [dict(r) for r in c.execute(
        'SELECT * FROM bridges WHERE left_uid=? OR right_uid=? ORDER BY id', (uid, uid))]
    return result


def exact_assertion(c, item):
    table = item['table']
    if table not in ('edges', 'entity_relations'):
        raise ValueError('Unexpected original source assertion table')
    row = c.execute('SELECT * FROM '+table+' WHERE id=?', (item['before_assertion']['id'],)).fetchone()
    if not row or dict(row) != item['before_assertion'] or source_assertion_sha256(row) != item['content_sha256']:
        raise ValueError('Original source assertion or its status changed')
    return row


def active_source_peer(c, left, right, role):
    if left == right:
        return True
    pending, seen = [left], set()
    while pending:
        current = pending.pop()
        if current == right:
            return True
        if current in seen:
            continue
        seen.add(current)
        for r in c.execute("SELECT * FROM bridges WHERE status='ACTIVE' AND relation='SAME_CONCEPT' AND (left_uid=? OR right_uid=?)", (current, current)):
            other = r['right_uid'] if r['left_uid'] == current else r['left_uid']
            n = node(c, other)
            if n and n['visibility'] == 'ACTIVE' and n['role'] == role:
                pending.append(other)
    return False


def endpoint_before(c, uid, proof, prefix=''):
    actual = c.execute('SELECT * FROM nodes WHERE uid=?', (uid,)).fetchone()
    profile = c.execute('SELECT * FROM node_profiles WHERE uid=?', (uid,)).fetchone()
    normalization = c.execute('SELECT * FROM normalization_roles WHERE uid=?', (uid,)).fetchone()
    if not actual or dict(actual) != proof[prefix+'before_node']:
        raise ValueError('Complete source endpoint changed')
    if (dict(profile) if profile else None) != proof[prefix+'before_profile']:
        raise ValueError('Reviewed endpoint profile changed')
    if (dict(normalization) if normalization else None) != proof[prefix+'before_normalization_role']:
        raise ValueError('Reviewed source role evidence changed')
    return node(c, uid)


def validate_operations(c, manifest, operations, source_review, semantic_reviews, source):
    if manifest.get('schema') != 'FINEATLAS_NOMINAL_DESIGN_SCOPE_REPAIRS_V1':
        raise ValueError('Unknown nominal design scope schema')
    if type(manifest.get('operation_count')) is not int or not operations or len(operations) != manifest['operation_count']:
        raise ValueError('Source operation count must be exact and nonempty')
    keys = [(o['uid'], o['parent'], o['relation']) for o in operations]
    if len(set(keys)) != len(keys):
        raise ValueError('Source operations have duplicate directional assertions')
    if source_review.get('accepted_source_scope_only') is not True or source_review.get('operations_sha256') != manifest['operations_sha256']:
        raise ValueError('Independent exact operation source review is missing')
    if sorted(map(tuple, source_review.get('approved_keys', []))) != sorted(keys):
        raise ValueError('Independent source review does not cover exactly all operations')
    binding = manifest['completed_parent_binding']
    revision = c.execute("SELECT value FROM metadata WHERE key='database_revision'").fetchone()
    frozen = c.execute("SELECT value FROM metadata WHERE key='structure_frozen_build_manifest'").fetchone()
    if not revision or json.loads(revision[0]) != binding['database_revision']:
        raise ValueError('Complete checkpoint revision differs from the reviewed parent')
    # This historical manifest contract intentionally uses ordinary JSON.
    if not frozen or sha(json.dumps(json.loads(frozen[0]), sort_keys=True, ensure_ascii=False)) != binding['frozen_manifest_sha256']:
        raise ValueError('Complete checkpoint frozen manifest differs from its parent binding')
    affected = set()
    role_overrides = {o['uid']: o['after_profile']['node_kind'] for o in operations if o['op'] == 'correct_role'}
    if len(role_overrides) != sum(o['op'] == 'correct_role' for o in operations):
        raise ValueError('A source object cannot have multiple role adjudications')
    for op in operations:
        if op.get('op') not in {'link', 'correct_role', 'review_class_edge'} or op.get('source') != source or not op.get('uri', '').startswith('https://'):
            raise ValueError('Nominal scope operations must be exact and attributed')
        relation = op['relation']
        axis = op['classification_axis']
        expected_axes = {'DESIGN_TYPE_OF': {'purpose', 'function'}, 'NATIVE_DESIGN_PARENT': {'design_family'}, 'IS_A': {'physical_intension'}, 'ROLE_ADJUDICATION': {'source_grain'}}
        if op['op'] == 'review_class_edge':
            expected_axes['IS_A'].add('class_intension')
        if relation not in expected_axes or axis not in expected_axes[relation]:
            raise ValueError('Relation and source classification axis are incompatible')
        p = op['proof']
        if p.get('classification_axis') != axis or p.get('kind') != 'SOURCE_REVIEWED_WHOLE_NOMINAL_DESIGN_SCOPE':
            raise ValueError('Source axis and proof scope disagree')
        if p.get('world_identity_assertion') is not False or p.get('no_identity_merges') is not True or p.get('whole_subject_scope_review') is not True or not p.get('scope_observation') or not p.get('license'):
            raise ValueError('A source direction cannot promote identity or incomplete scope')
        if op['op'] == 'correct_role':
            child = parent = validate_role(c, op, semantic_reviews)
        elif op['op'] == 'review_class_edge':
            child, parent = validate_review(c, op, semantic_reviews)
        else:
            child = endpoint_before(c, op['uid'], p)
            parent = endpoint_before(c, op['parent'], p, 'parent_')
        if child['visibility'] != 'ACTIVE' or parent['visibility'] != 'ACTIVE':
            raise ValueError('Scope endpoints must already be admitted; activation is outside this contract')
        if sha(child['data']) != p['native_record_sha256'] or (op['op'] != 'correct_role' and sha(parent['data']) != p['parent_native_record_sha256']):
            raise ValueError('Whole endpoint source bytes changed')
        if op['op'] == 'link':
            validate_link_roles(relation, role_overrides.get(child['uid'], child['role']), role_overrides.get(parent['uid'], parent['role']))
        if op['op'] == 'link' and child['component_id'] == parent['component_id']:
            raise ValueError('Directional inclusion cannot contract into source identity')
        affected.update(r[0] for cp in (child['component_id'], parent['component_id'])
                        for r in c.execute('SELECT uid FROM nodes WHERE component_id=?', (cp,)))
        if op['op'] == 'link':
            source_report(op, semantic_reviews, 'approved_source_directions')
        witnesses = p['source_witnesses']
        if len(witnesses) < (1 if op['op'] == 'correct_role' else 2):
            raise ValueError('Complete child and parent scope witnesses are both required')
        represented = set()
        declared = {}
        for w in witnesses:
            n = node(c, w['uid'])
            if not n or sha(n['data']) != w['data_sha256'] or field_value(json.loads(n['data']), w['field_path']) != w['statement'] or not w['statement']:
                raise ValueError('Owned full source witness changed')
            expected_role = child['role'] if n['component_id'] == child['component_id'] else parent['role']
            if n['component_id'] not in (child['component_id'], parent['component_id']) or n['role'] != expected_role:
                raise ValueError('Source body belongs to a different object or role')
            own_uid = op['uid'] if n['component_id'] == child['component_id'] else op['parent']
            if not active_source_peer(c, own_uid, w['uid'], expected_role):
                raise ValueError('A source body requires an actual admitted same-role identity path')
            represented.add(n['component_id'])
            declared.setdefault(w['uid'], {})[w['field_path']] = w['statement']
        if represented != {child['component_id'], parent['component_id']}:
            raise ValueError('Both complete endpoint scopes must be witnessed')
        for uid in declared:
            if declared[uid] != complete_fields(json.loads(node(c, uid)['data'])):
                raise ValueError('Every retained whole owned definition field must be reviewed')
        if not {op['uid'], op['parent']} <= set(declared):
            raise ValueError('Both original endpoints need their own complete definition inventory')
        conditions = p['parent_conditions']
        if not conditions:
            raise ValueError('All parent scope conditions need explicit source spans')
        for condition in conditions:
            if not condition.get('condition') or not condition.get('exact_spans'):
                raise ValueError('Parent condition lacks grounded range evidence')
            for span in condition['exact_spans']:
                if type(span.get('witness_index')) is not int or not 0 <= span['witness_index'] < len(witnesses) or not span.get('text') or span['text'] not in witnesses[span['witness_index']]['statement']:
                    raise ValueError('A parent condition was inferred outside its complete source field')
        if not isinstance(p['prior_assertions'], list):
            raise ValueError('Original source declaration history must be explicit')
        for item in p['prior_assertions']:
            exact_assertion(c, item)
        composition = p['composition_scope_review']
        if composition.get('whole_parent_range_reviewed') is not True or composition.get('active_derivation_conflation_absent') is not True or not composition.get('scope_observation'):
            raise ValueError('Range membership and design derivation composition are unreviewed')
        for item in composition['non_admitted_derivations']:
            row = exact_assertion(c, item)
            if row['status'] in ('ACTIVE', 'TYPED_ACTIVE', 'BACKBONE_ACTIVE'):
                raise ValueError('An unproved derivation must not inherit an admitted type')
        if op['op'] == 'link' and c.execute('SELECT 1 FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?', (op['uid'], op['parent'], relation, source)).fetchone():
            raise ValueError('Source stage was already applied')
        if op['op'] == 'link' and relation == 'IS_A' and c.execute('SELECT 1 FROM edges WHERE child_uid=? AND parent_uid=? AND relation=? AND source=?', (op['uid'], op['parent'], relation, source)).fetchone():
            raise ValueError('Source class stage was already applied')
    if set(manifest['scope_inventories']) != affected:
        raise ValueError('Complete affected identity component inventory is incomplete')
    for uid in affected:
        if inventory(c, uid) != manifest['scope_inventories'][uid]:
            raise ValueError('Parent/member/source composition changed after scope review')
    for uid, target in role_overrides.items():
        for b in c.execute("SELECT * FROM bridges WHERE status='ACTIVE' AND relation='SAME_CONCEPT' AND (left_uid=? OR right_uid=?)", (uid, uid)):
            other = b['right_uid'] if b['left_uid'] == uid else b['left_uid']
            if role_overrides.get(other, node(c, other)['role']) != target:
                raise ValueError('Role correction leaves admitted identity peers at incompatible grains')
        for r in c.execute("SELECT * FROM entity_relations WHERE status='ACTIVE' AND (subject_uid=? OR object_uid=?)", (uid, uid)):
            a, b = node(c, r['subject_uid']), node(c, r['object_uid'])
            if not a or not b:
                continue
            try:
                validate_link_roles(r['relation'], a['role'], b['role'])
            except ValueError:
                continue
            # Every previously legitimate typed parent must remain legitimate.
            validate_link_roles(r['relation'], role_overrides.get(a['uid'], a['role']), role_overrides.get(b['uid'], b['role']))
    for op in operations:
        for uid in {op['uid'], op['parent']}:
            profile = c.execute('SELECT * FROM node_profiles WHERE uid=?', (uid,)).fetchone()
            attrs = json.loads(profile['attributes']) if profile else {}
            views = attrs.get('allowed_views')
            if isinstance(views, list) and 'taxonomy' not in views:
                raise ValueError('Reviewed source endpoint is not admitted to the actual unified source view')
    validate_batch_cycles(c, operations, {})
    validate_root_closure(c, operations, role_overrides)
