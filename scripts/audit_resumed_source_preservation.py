#!/usr/bin/env python3
"""Preserve every raw source field while auditing explicit visibility migrations.

The original strict auditor remains unchanged. This compatibility audit permits
only visibility changes enumerated by frozen deltas whose independent actual
audits pass. It never normalizes raw payloads, source fields or missing rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from structure_delivery_delta_registry import required_deltas, validate_delta_receipt
from structure_acceptance_contract import file_sha256

ROOT = Path(__file__).resolve().parents[1]


def independent_permissions(database, inputs, output):
    """Require complete independent actual audits before allowing any change."""
    con = sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    metadata = {key: json.loads(value) for key, value in con.execute('SELECT * FROM metadata')}
    revision = metadata['database_revision']
    frozen_inputs = metadata['structure_frozen_build_manifest']['inputs']
    actual_inputs = {str(path.relative_to(inputs)): file_sha256(path)
                     for path in sorted(inputs.rglob('*')) if path.is_file()}
    if actual_inputs != frozen_inputs:
        raise ValueError('Source-preservation inputs differ from actual frozen revision')
    con.close()
    permissions, audits = {}, []
    for spec in required_deltas(inputs):
        if spec.name not in {'complete-subject-scope', 'cars-projection-view'}:
            continue
        report = output.parent / (output.stem + '-' + spec.name + '.json')
        subprocess.run([sys.executable, '-B', str(ROOT / 'scripts' / spec.auditor),
                        '--database', str(database), '--inputs', str(inputs),
                        '--output', str(report)], check=True)
        validate_delta_receipt(spec, report, database, inputs, revision)
        manifest = json.loads((inputs / spec.fallback_input).read_text())
        if spec.name == 'cars-projection-view':
            rows = [(row['uid'], row['before_node']['visibility'], row['visibility_after'])
                    for row in manifest['source_projections']]
        else:
            rows = [(row['uid'], row['before_visibility'], 'ACTIVE')
                    for row in manifest.get('source_class_activations', [])]
        for uid, before, after in rows:
            if uid in permissions or before == after:
                raise ValueError('Duplicate or empty visibility migration')
            permissions[uid] = {'before': before, 'after': after, 'delta': spec.name}
        audits.append({'delta': spec.name, 'report': str(report),
                       'sha256': hashlib.sha256(report.read_bytes()).hexdigest()})
    return permissions, audits, revision, frozen_inputs


def digest_rows(con, table, columns, maximum, permissions=None):
    digest, count, changes = hashlib.sha256(), 0, []
    quoted = ','.join('"' + name + '"' for name in columns)
    sql = 'SELECT ' + quoted + ' FROM "' + table + '" WHERE rowid<=? ORDER BY rowid'
    uid_index = columns.index('uid') if table == 'nodes' else None
    visibility_index = columns.index('visibility') if table == 'nodes' else None
    started = time.monotonic()
    for record in con.execute(sql, (maximum,)):
        row = list(record)
        if permissions and table == 'nodes' and row[uid_index] in permissions:
            uid = row[uid_index]
            permit = permissions[uid]
            if row[visibility_index] != permit['after']:
                raise ValueError('Actual visibility differs from audited migration: ' + uid)
            changes.append({'uid': uid, **permit})
            row[visibility_index] = permit['before']
        payload = json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode()
        digest.update(len(payload).to_bytes(8, 'big'))
        digest.update(payload)
        count += 1
        if count % 1000000 == 0:
            print(table, count, round(time.monotonic() - started, 1), flush=True)
    return {'sha256': digest.hexdigest(), 'rows': count,
            'seconds': time.monotonic() - started}, changes


def run(baseline, candidate, inputs, output, reference=None):
    if not __debug__:
        raise RuntimeError('Optimized Python is forbidden for source preservation')
    output.parent.mkdir(parents=True, exist_ok=True)
    permissions, audits, revision, frozen_inputs = independent_permissions(candidate, inputs, output)
    base = sqlite3.connect(baseline.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    con = sqlite3.connect(candidate.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    saved = json.loads(reference.read_text()) if reference else None
    # A declared permission is applicable to the baseline only if its exact old
    # visibility agrees. New nodes outside the original row bound need no waiver.
    applicable = {}
    for uid, permit in permissions.items():
        row = base.execute('SELECT visibility FROM nodes WHERE uid=?', (uid,)).fetchone()
        if row:
            if row[0] != permit['before']:
                raise ValueError('Original visibility differs from frozen migration: ' + uid)
            applicable[uid] = permit
    tables = [row[0] for row in base.execute("SELECT name FROM sqlite_master WHERE type='table' "
        "AND name IN ('nodes','evidence','source_nodes','source_edges','source_bridges','source_entity_relations')")]
    results, changes = {}, []
    result = {'schema': 'FINEATLAS_RESUMED_RAW_SOURCE_PRESERVATION_V1',
              'baseline': str(baseline), 'candidate': str(candidate),
              'database_revision': revision, 'independent_actual_audits': audits,
              'frozen_input_fingerprints': frozen_inputs,
              'allowed_fields': ['nodes.visibility'], 'complete': False, 'tables': results}
    for table in tables:
        columns = [row[1] for row in base.execute('PRAGMA table_info("' + table + '")')
                   if not (table == 'nodes' and row[1] == 'component_id')]
        maximum = base.execute('SELECT max(rowid) FROM "' + table + '"').fetchone()[0]
        frozen = saved.get('tables', {}).get(table) if saved else None
        if frozen and (frozen['columns'] != columns or frozen['max_baseline_rowid'] != maximum):
            raise ValueError('Original reference schema or row bound changed: ' + table)
        left = frozen['baseline'] if frozen else digest_rows(base, table, columns, maximum)[0]
        right, changed = digest_rows(con, table, columns, maximum, applicable)
        changes.extend(changed)
        results[table] = {'columns': columns, 'max_baseline_rowid': maximum,
                         'baseline': left, 'candidate_with_audited_visibility': right,
                         'pass': left['sha256'] == right['sha256'] and left['rows'] == right['rows']}
        result['audited_visibility_changes'] = changes
        result['pass'] = all(row['pass'] for row in results.values())
        output.write_text(json.dumps(result, indent=2) + '\n')
        print('TABLE', table, results[table]['pass'], flush=True)
    if {row['uid'] for row in changes} != set(applicable):
        result.update({'pass': False, 'error': 'Audited migration census differs'})
        output.write_text(json.dumps(result, indent=2) + '\n')
        raise ValueError('Audited visibility census differs from original retained rows')
    base.close()
    con.close()
    if not result['pass']:
        raise ValueError('Original raw source content changed or disappeared')
    result['complete'] = True
    output.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'candidate', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--reference', type=Path)
    args = parser.parse_args()
    run(args.baseline.resolve(), args.candidate.resolve(), args.inputs.resolve(),
        args.output.resolve(), args.reference.resolve() if args.reference else None)
