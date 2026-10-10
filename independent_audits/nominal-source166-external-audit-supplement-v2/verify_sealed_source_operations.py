#!/usr/bin/env python3
"""Exercise sealed Source9 observer interfaces against a private SQL fixture.

The exact before rows come from the closed Source8 parent. Synthetic after rows
are not a final database, graph/index audit or source certification.
"""

if not __debug__:
    raise RuntimeError('Optimized Python is forbidden for mandatory independent audit gates')

import argparse
from collections import Counter
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def run(inputs, parent, output):
    inputs, parent = Path(inputs).resolve(), Path(parent).resolve()
    assert not any(Path(str(parent) + s).exists() for s in ('-wal', '-shm', '-journal'))
    script = Path(__file__).parent / 'nominal-design-scope-final-plan-v1/independent_nominal_design_scope_final_interface_audit.py'
    spec = importlib.util.spec_from_file_location('observer', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = sqlite3.connect(parent.as_uri() + '?mode=ro&immutable=1', uri=True)
    original.row_factory = sqlite3.Row
    original.execute('PRAGMA query_only=ON')
    original.execute('PRAGMA cache_size=-32768')
    fixture = sqlite3.connect(':memory:')
    fixture.row_factory = sqlite3.Row
    for table in ('nodes', 'node_profiles', 'normalization_roles', 'edges', 'browse_links', 'view_roots', 'view_paths', 'view_terminal_connections', 'entity_connections'):
        row = original.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name=?', (table,)).fetchone()
        assert row, table
        fixture.execute(row[0])
    fixture.execute('CREATE TABLE evidence(evidence_id TEXT,payload TEXT,payload_sha256 TEXT,source_name TEXT,source_uri TEXT)')
    fixture.execute('CREATE TABLE usability_changes(stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT)')

    def insert(table, row):
        fixture.execute('INSERT INTO ' + table + '(' + ','.join(row) + ') VALUES(' + ','.join('?' for _ in row) + ')', list(row.values()))

    inserted_nodes = set()
    records, errors, counts = [], [], Counter()
    manifest = json.loads((inputs / 'structure_nominal_design_scope_repairs.json').read_text())
    op_path = inputs / manifest['operations_file']
    for line in op_path.open():
        if not line.strip():
            continue
        op = json.loads(line)
        counts[op['op']] += 1
        try:
            needed = {op['uid'], op['parent']} | {row['uid'] for row in op['proof']['source_witnesses']}
            for uid in sorted(needed - inserted_nodes):
                row = original.execute('SELECT *FROM nodes WHERE uid=?', (uid,)).fetchone()
                assert row
                insert('nodes', dict(row))
                inserted_nodes.add(uid)
            if op['op'] == 'link':
                review = module.verify_nominal_source_approval(fixture, inputs, op, 'approved_source_directions')
                abstract = module.verify_nominal_classification_axis(op, review)
                records.append({'uid': op['uid'], 'op': op['op'], 'relation': op['relation'], 'axis': op['classification_axis'], 'abstract_configuration': abstract is not None})
            elif op['op'] == 'correct_role':
                for table, field in (('node_profiles', 'profile'), ('normalization_roles', 'normalization_role')):
                    actual = original.execute('SELECT *FROM ' + table + ' WHERE uid=?', (op['uid'],)).fetchone()
                    assert (dict(actual) if actual else None) == op['before_' + field]
                    insert(table, op['after_' + field])
                proof = op['proof']
                payload = compact(proof)
                eid = 'usability:' + hashlib.sha256(payload.encode()).hexdigest()
                insert('evidence', {'evidence_id': eid, 'payload': payload, 'payload_sha256': hashlib.sha256(payload.encode()).hexdigest(), 'source_name': op['source'], 'source_uri': op['uri']})
                before = {'profile': op['before_profile'], 'normalization_role': op['before_normalization_role']}
                after = {'profile': op['after_profile'], 'normalization_role': op['after_normalization_role']}
                insert('usability_changes', {'stage': 'nominal_design_scope_repairs', 'object_type': 'role_source_adjudication', 'object_id': op['uid'], 'before_json': compact(before), 'after_json': compact(after), 'evidence': payload})
                record = module.verify_nominal_role_transition(fixture, inputs, op)
                records.append({'op': op['op'], **record})
            elif op['op'] == 'review_class_edge':
                before = op['before_assertion']
                actual = original.execute('SELECT *FROM edges WHERE id=?', (before['id'],)).fetchone()
                assert dict(actual) == before
                insert('edges', {**before, 'status': 'SOURCE_SCOPE_REVIEW'})
                insert('usability_changes', {'stage': 'nominal_design_scope_repairs', 'object_type': 'class_scope_review', 'object_id': str(before['id']), 'before_json': compact(before), 'after_json': compact({'status': 'SOURCE_SCOPE_REVIEW'}), 'evidence': compact(op['proof'])})
                records.append({'op': op['op'], **module.verify_nominal_class_withdrawal(fixture, inputs, op)})
            else:
                raise AssertionError('Unrecognized sealed operation kind: ' + op['op'])
        except Exception as error:
            errors.append({'uid': op['uid'], 'op': op['op'], 'relation': op['relation'], 'error': repr(error)})
    parent_revision = json.loads(original.execute('SELECT value FROM metadata WHERE key="database_revision"').fetchone()[0])
    report = {'schema': 'FINEATLAS_SEALED_SOURCE_OPERATION_EXTERNAL_INTERFACE_FIXTURE_V1', 'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'pass': not errors, 'fixture_only': True, 'actual_candidate_acceptance': False, 'source_semantic_certification': False, 'closed_actual_parent': str(parent), 'closed_actual_parent_revision': parent_revision, 'observer_sha256': digest(script), 'fixture_driver_sha256': digest(__file__), 'manifest_sha256': digest(inputs / 'structure_nominal_design_scope_repairs.json'), 'operations_sha256': digest(op_path), 'operations': dict(counts), 'operations_checked': len(records), 'records': records, 'errors': errors, 'scope': 'Actual closed-parent before rows and frozen source-document bytes, exact derived private fixture role/review after rows/history/evidence, all source axes. Empty fixture indexes do not prove actual final indexes; actual Source9 root/path/index/SDK acceptance remains mandatory.'}
    output = Path(output)
    assert not output.exists(), 'Keep prior failure receipts'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    original.close()
    fixture.close()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert __debug__
    result = run(args.inputs, args.parent, args.output)
    print(json.dumps({key: result[key] for key in ('pass', 'operations', 'operations_checked', 'errors')}, ensure_ascii=False))
    raise SystemExit(0 if result['pass'] else 1)
