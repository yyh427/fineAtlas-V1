#!/usr/bin/env python3
"""Extend a hash-bound, unaccepted source checkpoint and rebuild all views.

The interrupted graph build is never resumed: every derived graph and browse
index is recomputed. Both source checkpoints must independently pass this recipe
and independent acceptance before packaging. Capture receipts before copying.
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
# A private empty cache prevents valid timestamp-based stale .pyc reads.
_import_cache=Path(os.environ.get('TMPDIR',str(ROOT.parent/'tmp')))/('fineatlas-import-'+uuid.uuid4().hex)
_import_cache.mkdir(parents=True,exist_ok=False)
sys.pycache_prefix=str(_import_cache)
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from structure_build_safety import inventory_code, protect_output, require_unoptimized
require_unoptimized()
PREIMPORT_CODE_INVENTORY = inventory_code(ROOT)
from fineatlas.migration import Migration, digest_file
from fineatlas.unified_build import ram_graphs
from build_structure_candidate import (freeze_metadata, build_fingerprints, start_build,
                                      require_stable_build, write_build_complete, final_artifact_binding)
if inventory_code(ROOT) != PREIMPORT_CODE_INVENTORY:
    raise ValueError('Code changed while SDK/build modules were imported')

SOURCE_STAGES = ('verify_independent_copy', 'schema', 'biological_scope',
                 'engineering_scope', 'breed_sources', 'living_catalogue',
                 'navigation_names')
BUILD_STAGES = ('verify_source_checkpoint_copy', 'biological_whole_definition_scope',
                'candidate_evidence_dates', 'whole_subject_source_contracts',
                'whole_graph_recomputation', 'freeze_metadata', 'browse_staging',
                'embed_browse_indexes')


def source_snapshot(database):
    with sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1', uri=True) as c:
        meta = {key: json.loads(value) for key, value in c.execute('SELECT * FROM metadata')}
        schema = list(c.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
                                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"))
    return {'revision': meta['database_revision'], 'release': meta['release'],
            'unified_ready': meta.get('unified_ready'),
            'usability_indexes_ready': meta.get('usability_indexes_ready'),
            'schema_sha256': hashlib.sha256(json.dumps(schema).encode()).hexdigest()}


def capture(database, frozen_inputs, build_status, receipt):
    require_unoptimized()
    for suffix in ('-wal', '-journal', '-shm'):
        if Path(str(database)+suffix).exists():
            raise ValueError('Checkpoint must be closed and have no journal sidecars')
    states = json.loads(build_status.read_text())
    if any(states.get(stage, {}).get('status') != 'PASS' for stage in SOURCE_STAGES):
        raise ValueError('All source replay stages must already have passed')
    snapshot = source_snapshot(database)
    if snapshot['unified_ready'] or snapshot['usability_indexes_ready']:
        raise ValueError('Only an explicitly unaccepted source checkpoint is eligible')
    value = {'schema': 'FINEATLAS_UNACCEPTED_SOURCE_CHECKPOINT_V1',
             'database': str(database), 'database_sha256': digest_file(database),
             'database_bytes': database.stat().st_size, 'snapshot': snapshot,
             'source_code_commit': 'f718b84232c3a20392b382f1bbc71972252dd921',
             'source_stage_status': states,
             'inputs': {str(path.relative_to(frozen_inputs)): digest_file(path)
                        for path in sorted(frozen_inputs.rglob('*')) if path.is_file()},
             'captured_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'accepted': False}
    receipt.parent.mkdir(parents=True, exist_ok=True)
    if receipt.exists():
        protect_output(receipt, frozen_inputs, additional_protected=(database, build_status))
        receipt.write_text(json.dumps(value, indent=2)+'\n')
    else:
        with receipt.open('x') as output:
            output.write(json.dumps(value, indent=2)+'\n')
    print(json.dumps({'receipt': str(receipt), 'sha256': value['database_sha256']}), flush=True)


def build(a):
    fingerprints, context = start_build(a.inputs, a.reports)
    if {key:fingerprints[key] for key in ('code','packaging')} != PREIMPORT_CODE_INVENTORY:
        raise ValueError('Extension code differs from its pre-SDK-import inventory')
    receipt = json.loads(a.receipt.read_text())
    if receipt.get('schema') != 'FINEATLAS_UNACCEPTED_SOURCE_CHECKPOINT_V1' or receipt.get('accepted') is not False:
        raise ValueError('Not a valid unaccepted source checkpoint receipt')
    source = Path(receipt['database']).resolve()
    temp = a.database.parent/'tmp'; temp.mkdir(exist_ok=True)
    os.environ.update(TMPDIR=str(temp), SQLITE_TMPDIR=str(temp))
    env = {**os.environ, 'PYTHONHASHSEED': '0', 'PYTHONDONTWRITEBYTECODE': '1',
           'PYTHONPATH': str(ROOT/'src')}
    env.pop('PYTHONOPTIMIZE', None)
    env['PYTHONPYCACHEPREFIX']=sys.pycache_prefix
    states = {}
    def stage(name, function):
        start = time.monotonic()
        states[name] = {'status': 'RUNNING', 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        status = a.reports/'build_status.json'
        status.write_text(json.dumps(states, indent=2)+'\n')
        print('START', name, flush=True)
        try:
            require_stable_build(a.inputs, fingerprints)
            result = function()
            require_stable_build(a.inputs, fingerprints)
            states[name].update(status='PASS', result=result)
        except Exception as error:
            states[name].update(status='FAIL', error=str(error))
            raise
        finally:
            states[name]['seconds'] = time.monotonic()-start
            status.write_text(json.dumps(states, indent=2)+'\n')
        print('PASS', name, round(states[name]['seconds'], 3), flush=True)
        return result
    def verify():
        protection = protect_output(a.database, a.inputs, a.baseline, (source,))
        if digest_file(a.database) != receipt['database_sha256'] or a.database.stat().st_size != receipt['database_bytes']:
            raise ValueError('Independent checkpoint copy changed')
        if source_snapshot(a.database) != receipt['snapshot']:
            raise ValueError('Source checkpoint schema/metadata changed')
        for name, expected in receipt['inputs'].items():
            if digest_file(a.inputs/name) != expected:
                raise ValueError('Previously replayed input changed: '+name)
        base = json.loads((a.inputs/'baseline.json').read_text())
        if source_snapshot(a.baseline)['revision'] != base['database_revision']:
            raise ValueError('Protected production revision changed')
        if not (a.inputs/'structure_source_contracts.json').is_file() and not (a.inputs/'structure_source_contracts.json.gz').is_file():
            raise ValueError('Required complete source scope input is missing')
        return {'checkpoint_sha256': receipt['database_sha256'],
                'checkpoint_receipt_sha256': digest_file(a.receipt),
                'distinct_inode': True, 'all_original_inputs_unchanged': True, 'protection': protection}
    stage('verify_source_checkpoint_copy', verify)
    m = Migration(a.database, a.inputs, a.reports/'graph-build')
    from fineatlas.structure_biology_scope import apply_structure_biology_scope
    stage('biological_whole_definition_scope', lambda: apply_structure_biology_scope(m))
    from fineatlas.evidence_dates import apply_evidence_dates
    stage('candidate_evidence_dates', lambda: apply_evidence_dates(m))
    # schema() has already passed; avoid a second full-database ANALYZE.
    from fineatlas.structure_source_contracts import apply_source_contracts
    stage('whole_subject_source_contracts', lambda: apply_source_contracts(m))
    stage('whole_graph_recomputation', lambda: ram_graphs(m))
    frozen = stage('freeze_metadata', lambda: freeze_metadata(m, fingerprints))
    (a.reports/'frozen_metadata.json').write_text(json.dumps(frozen, indent=2)+'\n')
    m.c.close()
    release = json.loads((a.inputs/'review_release.json').read_text())['version']
    def command(name, arguments):
        log_path = a.reports/(name+'.log')
        with log_path.open('w') as log:
            subprocess.run([sys.executable, '-B', *arguments], cwd=ROOT, env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        return {'log': str(log_path)}
    stage('browse_staging', lambda: command('browse_staging', [str(ROOT/'scripts/stage_browse_indexes.py'),
          '--source', str(a.database), '--output', str(a.browse_staging),
          '--reports', str(a.reports/'browse-build'), '--release', release]))
    stage('embed_browse_indexes', lambda: command('embed_browse_indexes', [str(ROOT/'scripts/apply_browse_indexes.py'),
          '--database', str(a.database), '--staging', str(a.browse_staging),
          '--source-revision', frozen['revision'], '--output', str(a.reports/'browse_application.json')]))
    require_stable_build(a.inputs, fingerprints)
    binding = final_artifact_binding(a.database, release, frozen['revision'])
    write_build_complete(a.reports, a.database, release, binding['revision'], context, states, BUILD_STAGES,
                         source_graph_revision=frozen['revision'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    capture_p = sub.add_parser('capture')
    for name in ('database', 'frozen-inputs', 'build-status', 'receipt'):
        capture_p.add_argument('--'+name, type=Path, required=True)
    build_p = sub.add_parser('build')
    for name in ('database', 'baseline', 'inputs', 'reports', 'browse-staging', 'receipt'):
        build_p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    for key, value in vars(a).items():
        if isinstance(value, Path):
            setattr(a, key, value.resolve())
    if a.action == 'capture':
        capture(a.database, a.frozen_inputs, a.build_status, a.receipt)
    else:
        build(a)


if __name__ == '__main__':
    main()
