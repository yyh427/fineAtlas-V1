#!/usr/bin/env python3
"""Read-only acceptance of frozen 1.10 shared/scope/furniture repairs.

Run against a completed candidate and again against the public installation,
using the same frozen local inputs. Detailed case evidence is a local report;
this bounded audit does not replace whole-graph or installation acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fineatlas import FineAtlas
from fineatlas.hierarchy import locate_source_assertion, source_assertion_sha256
from fineatlas.role_contracts import reviewed_generic_class
import fineatlas


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


class Checks:
    def __init__(self):
        self.items = []

    def add(self, name, passed, **evidence):
        self.items.append({'name': name, 'pass': bool(passed), **evidence})

    def run(self, name, function):
        try:
            evidence = function()
            self.add(name, evidence.pop('pass'), **evidence)
        except Exception as error:
            self.add(name, False, status='ERROR', error_type=type(error).__name__, error=str(error))


def legal_path(tree, uid):
    """Validate every witnessed arc against all legal parent options."""
    path = tree.path_result(uid)
    state = tree.connection_status(uid)
    invalid = []
    for step in path.get('path', []):
        edge = step.get('edge', {})
        child = edge.get('child_uid') or edge.get('subject_uid') or step.get('uid')
        parent = edge.get('parent_uid') or edge.get('object_uid') or step.get('parent_uid')
        if edge.get('relation') == 'SAME_CONCEPT':
            a, b = tree.node(child), tree.node(parent)
            if not a or not b or a['component_id'] != b['component_id']:
                invalid.append(step)
        else:
            options = tree._parents(child) if child else []
            if not any(p == parent and e.get('relation') == edge.get('relation')
                       and e.get('id') == edge.get('id') for p, e in options):
                invalid.append(step)
    parents = [{'parent_uid': parent, 'relation': edge.get('relation'), 'record_id': edge.get('id')}
               for parent, edge in tree._parents(uid)]
    return {'pass': path['status'] in ('CONNECTED', 'ROOT') and state['path_status'] == path['status']
                    and state['root_reachable'] and not invalid,
            'uid': uid, 'path_status': path['status'], 'path_state_agree': state['path_status'] == path['status'],
            'all_legal_direct_parent_options': parents, 'invalid_witness_steps': invalid, 'path': path}


def typed_matches(c, row, source=None):
    rows = c.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=?' +
                     (' AND source=?' if source else ''),
                     (row['uid'], row['parent'], row['relation'], *([source] if source else []))).fetchall()
    matches = [dict(r) for r in rows if r['status'] == 'ACTIVE'
               and json.loads(r['data']).get('admission_basis') == row['proof']]
    return matches


def profile(c, uid):
    row = c.execute('SELECT * FROM node_profiles WHERE uid=?', (uid,)).fetchone()
    return dict(row) if row else {}


def ledger_inventory(c, shared, assertions):
    """One bounded source-ledger scan, avoiding a large scan per operation."""
    ids = {r['uid'] for r in shared if r['op'] == 'role'}
    ids.update(str(row['id']) for row in assertions.values())
    marks = ','.join('?' for _ in ids)
    out = defaultdict(list)
    for row in c.execute("SELECT * FROM usability_changes WHERE stage IN ('roles','hierarchy') "
                         "AND object_type IN ('node','typed','identity') AND object_id IN (" + marks + ')', sorted(ids)):
        out[(row['stage'], row['object_type'], row['object_id'])].append(dict(row))
    return out


def shared_operation(tree, record, assertion, ledgers):
    c = tree.con
    op, uid, proof = record['op'], record['uid'], record['proof']
    decision = sha(json.dumps(record, sort_keys=True, ensure_ascii=False).encode())
    stored = c.execute('SELECT payload FROM hierarchy_decisions WHERE id=?', (decision,)).fetchone()
    decision_ok = bool(stored and json.loads(stored[0]) == record)
    native = c.execute('SELECT data FROM nodes WHERE uid=?', (uid,)).fetchone()
    native_ok = bool(native and (not proof.get('native_record_sha256')
                               or sha(native[0].encode()) == proof['native_record_sha256']))
    details = {'operation': op, 'uid': uid, 'frozen_decision_retained': decision_ok,
               'native_source_payload_hash_retained': native_ok}
    passed = decision_ok and native_ok
    if op == 'role':
        node = tree.node(uid)
        current_profile = profile(c, uid)
        expected_evidence = 'usability:' + sha(canonical(proof).encode())
        ledger = [r for r in ledgers.get(('roles', 'node', uid), [])
                  if json.loads(r['evidence']) == proof
                  and json.loads(r['after_json']).get('node_kind') == record['role']]
        details.update(expected_role=record['role'], actual_role=node['node_kind'] if node else None,
                       exact_role_ledger_records=len(ledger), current_role_evidence=current_profile.get('evidence_id'),
                       expected_role_evidence=expected_evidence)
        passed = passed and bool(node and node['node_kind'] == record['role'] and ledger
                                 and current_profile.get('evidence_id') == expected_evidence)
    elif op == 'link':
        rows = c.execute('SELECT * FROM edges WHERE child_uid=? AND parent_uid=? AND relation=? AND source=?',
                         (uid, record['parent'], record['relation'], record['source'])).fetchall()
        matches = [dict(r) for r in rows if r['status'] == 'ACTIVE' and json.loads(r['data']).get('admission_basis') == proof]
        legal = any(p == record['parent'] and e['relation'] == record['relation'] for p, e in tree._parents(uid))
        parent = c.execute('SELECT data,description FROM nodes WHERE uid=?', (record['parent'],)).fetchone()
        parent_source_ok = bool(parent and sha(parent['data'].encode()) == proof['parent_native_record_sha256']
                                and parent['description'] == proof['parent_definition'])
        details.update(parent_uid=record['parent'], exact_active_source_edges=matches, legal_parent_option=legal,
                       parent_source_and_definition_retained=parent_source_ok)
        passed = passed and bool(matches) and legal and parent_source_ok
    elif op in ('withdraw_typed_source', 'split_identity_source'):
        if not assertion:
            raise ValueError('Frozen source assertion could not be located by full source content')
        kind = 'typed' if op == 'withdraw_typed_source' else 'identity'
        ledger = [r for r in ledgers.get(('hierarchy', kind, str(assertion['id'])), [])
                  if json.loads(r['evidence']) == proof
                  and source_assertion_sha256(json.loads(r['before_json'])) == record['locator']['content_sha256']]
        expected_status = 'HIERARCHY_SUPERSEDED' if kind == 'typed' else 'GRAIN_REJECTED'
        details.update(source_locator=record['locator'], actual_source_record=assertion,
                       expected_status=expected_status, exact_original_source_ledger_records=len(ledger))
        passed = passed and assertion['status'] == expected_status and bool(ledger)
        if kind == 'identity':
            a, b = tree.node(uid), tree.node(record['parent'])
            separated = bool(a and b and a['component_id'] != b['component_id'])
            details.update(left_component=a['component_id'] if a else None,
                           right_component=b['component_id'] if b else None, current_scopes_separate=separated)
            passed = passed and separated and assertion['reason'] == proof['basis']
    else:
        raise ValueError('Unsupported frozen shared operation: ' + op)
    return {'pass': passed, **details}


def cub_repair(tree, repair, stage):
    c = tree.con
    before = repair['before']
    target = tree.target(before['dataset'], before['class_id'])
    history = c.execute('SELECT original_record FROM annotation_scope_target_history WHERE stage=? AND dataset=? AND class_id=?',
                        (stage, before['dataset'], before['class_id'])).fetchone()
    original = c.execute('SELECT original_target_uid FROM dataset_target_history WHERE dataset=? AND class_id=?',
                         (before['dataset'], before['class_id'])).fetchone()
    history_ok = bool(history and json.loads(history[0]) == before and original and original[0] == before['target_uid'])
    expected_uid = repair['resolved_target_uid']
    path = legal_path(tree, expected_uid)
    mapping = target.get('mapping_review', {}) if target else {}
    passed = bool(target and target['label'] == before['label'] and target['target_uid'] == expected_uid
                  and target['identity_verified'] and target['decision_status'] == 'VERIFIED'
                  and mapping.get('status') == 'PRIMARY_SOURCE_CORROBORATED' and history_ok and path['pass'])
    return {'pass': passed, 'class_id': before['class_id'], 'expected_uid': expected_uid,
            'exact_history_retained': history_ok, 'target': target, 'legal_path': path}


def furniture_record(tree, row, domain):
    c = tree.con
    node = tree.node(row['uid'])
    raw = c.execute('SELECT data FROM nodes WHERE uid=?', (row['uid'],)).fetchone()
    native_ok = bool(raw and json.loads(raw[0]) == row['proof'])
    typed = typed_matches(c, row, row['source'])
    member = c.execute("SELECT role FROM domain_members WHERE domain_id=? AND view='unified' AND uid=?",
                       (domain['domain_id'], row['uid'])).fetchone() if domain else None
    parent_member = c.execute("SELECT role FROM domain_members WHERE domain_id=? AND view='unified' AND uid=?",
                              (domain['domain_id'], row['parent'])).fetchone() if domain else None
    parent = tree.node(row['parent'])
    path = legal_path(tree, row['uid'])
    # This verifies the product itself, not merely its parent or a global root path.
    membership_ok = bool(member and member[0] == 'CONFIGURATION' and parent_member and parent_member[0] == 'CLASS')
    passed = bool(node and node['node_kind'] == 'CONFIGURATION' and native_ok and typed and membership_ok
                  and parent and parent['node_kind'] == 'CLASS' and path['pass'])
    return {'pass': passed, 'uid': row['uid'], 'full_native_payload_and_proof_retained': native_ok,
            'actual_role': node['node_kind'] if node else None, 'typed_parent': row['parent'],
            'exact_active_typed_connections': typed, 'actual_furniture_membership': membership_ok,
            'member_role': member[0] if member else None, 'parent_member_role': parent_member[0] if parent_member else None,
            'legal_path': path}


def audit(database, inputs):
    started = time.monotonic()
    checks = Checks()
    shared = [json.loads(line) for line in (inputs / 'shared_role_repairs.jsonl').read_text().splitlines() if line.strip()]
    scope = json.loads((inputs / 'annotation_scope_repairs.json').read_text())
    historical = json.loads((inputs / 'annotation_historical_alias_repairs.json').read_text())
    ott_links = [json.loads(line) for line in (inputs / 'annotation_taxonomic_navigation.jsonl').read_text().splitlines() if line.strip()]
    furniture = [json.loads(line) for line in (inputs / 'abo_furniture_records.jsonl').read_text().splitlines() if line.strip()]
    with FineAtlas(database, relation_view='unified') as tree:
        c, meta = tree.con, tree.metadata
        c.execute('PRAGMA query_only=ON')
        frozen = meta.get('unified_frozen_build_manifest', {})
        expected_release = json.loads((inputs / 'review_release.json').read_text())['version']
        checks.add('candidate_binding', meta.get('schema') == 'FINEATLAS_SINGLE_DB_V1'
                   and meta.get('release') == expected_release and meta.get('default_relation_view') == 'unified'
                   and all(meta.get(k) is True for k in ('unified_ready', 'usability_indexes_ready', 'browse_indexes_ready'))
                   and meta.get('browse_index_revision') == tree._revision,
                   release=meta.get('release'), expected_release=expected_release, database_revision=tree._revision,
                   browse_index_revision=meta.get('browse_index_revision'))
        actual_inputs = {str(p.relative_to(inputs)): sha(p.read_bytes()) for p in sorted(inputs.rglob('*')) if p.is_file()}
        expected_inputs = frozen.get('inputs', {})
        checks.add('all_frozen_local_inputs', bool(expected_inputs) and actual_inputs == expected_inputs,
                   checked_files=len(actual_inputs), expected_files=len(expected_inputs),
                   missing=sorted(set(expected_inputs) - set(actual_inputs)),
                   unexpected=sorted(set(actual_inputs) - set(expected_inputs)),
                   different=[name for name in expected_inputs if actual_inputs.get(name) != expected_inputs[name]])
        package = Path(fineatlas.__file__).resolve().parent
        code = frozen.get('code', {})
        code_mismatch = [name for name, value in code.items()
                         if not (package / Path(name).name).is_file() or sha((package / Path(name).name).read_bytes()) != value]
        checks.add('loaded_frozen_sdk', bool(code) and not code_mismatch, checked_files=len(code), mismatches=code_mismatch)
        checks.add('frozen_focus_inventory', len(shared) == 57 and len(scope['cub_repairs']) == 2
                   and len(historical['repairs']) == 3 and len(scope['crj_nodes']) == 5
                   and len({r['uid'] for r in scope['crj_nodes']}) == 5
                   and len(ott_links) == 1 and len(furniture) == 4 and len({r['uid'] for r in furniture}) == 4,
                   shared_operations=len(shared), shared_by_operation=dict(Counter(r['op'] for r in shared)),
                   cub_primary=len(scope['cub_repairs']), cub_documented=len(historical['repairs']),
                   crj_source_nodes=len(scope['crj_nodes']), ott_links=len(ott_links), furniture_configurations=len(furniture))
        assertions = {}
        for index, record in enumerate(shared):
            if record['op'] in ('withdraw_typed_source', 'split_identity_source'):
                table = 'entity_relations' if record['op'] == 'withdraw_typed_source' else 'bridges'
                try:
                    assertions[index] = dict(locate_source_assertion(c, table, record['locator']))
                except Exception as error:
                    checks.add('shared_source_locator:' + str(index), False, error=str(error), locator=record['locator'])
        ledgers = ledger_inventory(c, shared, assertions)
        for index, record in enumerate(shared):
            checks.run('shared_operation:' + str(index), lambda index=index, record=record:
                       shared_operation(tree, record, assertions.get(index), ledgers))
        generic = [r['uid'] for r in shared if r['op'] == 'role' and r['role'] == 'CLASS']
        checks.add('ten_generic_guards', len(generic) == 10 and len(set(generic)) == 10, source_uids=generic)
        for uid in generic:
            p = profile(c, uid)
            checks.add('generic_guard:' + uid, reviewed_generic_class(p), uid=uid, profile=p)
            checks.run('generic_legal_path:' + uid, lambda uid=uid: legal_path(tree, uid))
        for uid in ('wikidata:Q201097', 'wikidata:Q2835904', 'wikidata:Q1756060', 'wikidata:Q558106'):
            checks.run('basket_thermal_descendant_path:' + uid, lambda uid=uid: legal_path(tree, uid))
        splits = [r for r in shared if r['op'] == 'split_identity_source']
        checks.add('four_scope_splits', len(splits) == 4, source_pairs=[[r['uid'], r['parent']] for r in splits])
        for repair in scope['cub_repairs']:
            checks.run('cub_repair:' + repair['class_id'], lambda repair=repair:
                       cub_repair(tree, repair, 'v1.10-annotation-scope-repair'))
        for repair in historical['repairs']:
            checks.run('cub_repair:' + repair['before']['class_id'], lambda repair=repair:
                       cub_repair(tree, repair, 'v1.10-documented-annotation-alias'))
        repaired_ids = {r['class_id'] for r in scope['cub_repairs']} | {r['before']['class_id'] for r in historical['repairs']}
        remaining = {r['class_id'] for r in scope['cub_unresolved']} - repaired_ids
        actual_remaining = {r[0] for r in c.execute("SELECT class_id FROM dataset_mapping_checks WHERE dataset='cub200' AND status='ANNOTATION_SCOPE_REVIEW'")}
        original_unresolved=set(remaining)
        delta_path=Path(inputs)/'cub_annotation_version_scope.json'
        if delta_path.exists():
            delta=json.loads(delta_path.read_text())
            if delta.get('schema')!='FINEATLAS_CUB_ANNOTATION_VERSION_SCOPE_V1':
                raise ValueError('Unknown mandatory CUB temporal scope contract')
            remaining |= {case['class_id'] for case in delta['mapping_reviews']}
        checks.add('remaining_cub_reviews', len(original_unresolved) == 15 and actual_remaining == remaining,
                   expected_count=len(remaining), original_unresolved_count=len(original_unresolved),
                   actual_count=len(actual_remaining), expected_class_ids=sorted(remaining),
                   actual_class_ids=sorted(actual_remaining))
        for class_id in sorted(remaining):
            target = tree.target('cub200', class_id)
            checks.add('cub_review_preserved:' + class_id, bool(target and not target['identity_verified']
                       and target.get('mapping_review', {}).get('status') == 'ANNOTATION_SCOPE_REVIEW'), target=target)
        for row in scope['crj_nodes']:
            node = tree.node(row['uid'])
            raw = c.execute('SELECT data FROM nodes WHERE uid=?', (row['uid'],)).fetchone()
            checks.add('crj_native_record:' + row['uid'], bool(node and node['label'] == row['label']
                       and node['node_kind'] == row['role'] and raw and json.loads(raw[0]) == row['proof']),
                       uid=row['uid'], expected_role=row['role'], actual_node=node)
        for index, row in enumerate(scope['crj_links']):
            links = typed_matches(c, row, 'FGVC-Aircraft 2013b author-defined native hierarchy')
            checks.add('crj_source_link:' + str(index), bool(links), frozen_link=row, actual_connections=links)
        crj_before = scope['crj_target']['before']
        crj = tree.target('fgvc_aircraft', crj_before['class_id'])
        crj_path = legal_path(tree, scope['crj_target']['resolved_target_uid'])
        crj_history = c.execute("SELECT original_record FROM annotation_scope_target_history WHERE stage='v1.10-annotation-scope-repair' AND dataset='fgvc_aircraft' AND class_id=?", (crj_before['class_id'],)).fetchone()
        checks.add('crj_native_target_world_review', crj_before['class_id'] == '46' and bool(crj)
                   and crj['target_uid'] == scope['crj_target']['resolved_target_uid']
                   and crj['decision_status'] == 'VERIFIED_NATIVE_LABEL' and not crj['identity_verified']
                   and crj.get('mapping_review', {}).get('status') == 'ANNOTATION_SCOPE_REVIEW'
                   and crj.get('provenance', {}).get('unified_scope_repair', {}).get('world_exact_identity_verified') is False
                   and bool(crj_history and json.loads(crj_history[0]) == crj_before) and crj_path['pass'],
                   target=crj, original_history_retained=bool(crj_history and json.loads(crj_history[0]) == crj_before),
                   legal_path=crj_path)
        original = scope['ott_original_edge']
        # Locate by full original source content, not a guessed independent row ID.
        candidates = c.execute('SELECT * FROM edges WHERE child_uid=? AND parent_uid=? AND relation=? AND source=?',
                               (original['child_uid'], original['parent_uid'], original['relation'], original['source'])).fetchall()
        preserved = [dict(r) for r in candidates if {k: r[k] for k in original if k != 'id'} == {k: v for k, v in original.items() if k != 'id'}]
        checks.add('ott_disputed_original_record', len(preserved) == 1 and original['status'] == 'REVIEW',
                   frozen_original=original, exact_retained_records=preserved)
        for row in ott_links:
            matches = [dict(r) for r in c.execute('SELECT * FROM edges WHERE child_uid=? AND parent_uid=? AND relation=? AND source=?',
                       (row['uid'], row['parent'], row['relation'], row['source']))
                       if r['status'] == 'TYPED_ACTIVE' and json.loads(r['data']).get('admission_basis') == row['proof']]
            legal = any(p == row['parent'] and e['relation'] == 'TAXONOMIC_PARENT' for p, e in tree._parents(row['uid']))
            alternate_path = tree.path_result(row['uid'], anchors=[row['parent']])
            checks.add('ott_evidenced_higher_placement', bool(matches) and legal and alternate_path['status'] == 'CONNECTED',
                       accepted_edges=matches, legal_parent_option=legal, higher_placement_path=alternate_path)
            checks.run('ott_root_path', lambda row=row: legal_path(tree, row['uid']))
        domain = tree.domain('furniture')
        checks.add('furniture_canonical_scope', bool(domain and 'wordnet31:03410635-n' in domain['root_uids']), domain=domain)
        for row in furniture:
            checks.run('abo_configuration:' + row['uid'], lambda row=row: furniture_record(tree, row, domain))
        all_pass = bool(checks.items) and all(row['pass'] for row in checks.items)
        return {'schema': 'FINEATLAS_REPAIR_FOCUS_AUDIT_V1', 'all_pass': all_pass,
                'release': meta.get('release'), 'database_revision': tree._revision,
                'database': str(database.resolve()), 'inputs': str(inputs.resolve()),
                'checker_sha256': sha(Path(__file__).read_bytes()), 'checks': checks.items,
                'checks_count': len(checks.items), 'failed_checks': [r['name'] for r in checks.items if not r['pass']],
                'seconds': time.monotonic() - started, 'database_mutated': False,
                'full_graph_scan_started': False, 'living_domain_pagination': 'Use separate prepare_living_domains.py --audit-inputs; this audit does not duplicate it'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(args.database, args.inputs)
    except Exception as error:
        result = {'schema': 'FINEATLAS_REPAIR_FOCUS_AUDIT_V1', 'all_pass': False,
                  'database': str(args.database.resolve()), 'error_type': type(error).__name__, 'error': str(error),
                  'unknown_checks_are_not_passed': True, 'database_mutated': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('all_pass', 'database_revision', 'checks_count', 'failed_checks', 'error') if k in result}), flush=True)
    if not result['all_pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
