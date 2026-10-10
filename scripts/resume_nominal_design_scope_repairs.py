#!/usr/bin/env python3
"""Append signed nominal scope links to two complete physical-type parents."""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.pycache_prefix = str(Path(os.environ.get('TMPDIR', str(ROOT.parent / 'tmp'))) /
                        ('nominal-scope-import-' + uuid.uuid4().hex))
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))
from structure_build_safety import inventory_code, protect_output, require_unoptimized

require_unoptimized()
PREIMPORT_INVENTORY = inventory_code(ROOT)
from build_structure_candidate import (final_artifact_binding, freeze_metadata,
    require_stable_build, start_build, write_build_complete)
from fineatlas.migration import Migration, digest_file
from fineatlas.unified_build import ram_graphs
from fineatlas.structure_nominal_design_scope_repairs import apply_nominal_design_scope_repairs
from resume_structure_repairs import validate_resumed_parent_independence, verify_parent_byte_copy
from structure_complete_owned_type_delivery_guard import require_complete_type_child_build

if inventory_code(ROOT) != PREIMPORT_INVENTORY:
    raise ValueError('Implementation changed during import')

STAGES = ('verify_complete_owned_type_parent_copy', 'nominal_design_scope_repairs',
          'whole_graph_recomputation', 'freeze_metadata', 'browse_staging', 'embed_browse_indexes')


def read_metadata(database):
    with sqlite3.connect(database.as_uri() + '?mode=ro&immutable=1', uri=True) as con:
        return {key: json.loads(value) for key, value in con.execute('SELECT * FROM metadata')}


def validate_parent(database, receipt_path, integrity_path, fingerprints):
    receipt = require_complete_type_child_build(receipt_path)
    if Path(receipt['database']).resolve() != database:
        raise ValueError('Completed six-stage receipt identifies another source database')
    inventory = json.loads((receipt_path.parent / 'started_fingerprints.json').read_bytes())
    for group in ('inputs', 'code', 'packaging'):
        for name, digest in inventory[group].items():
            if fingerprints[group].get(name) != digest:
                raise ValueError('Previously executed input or implementation changed: ' + name)
    meta = read_metadata(database)
    frozen = meta.get('structure_frozen_build_manifest', {})
    if any(frozen.get(group) != inventory[group] for group in ('inputs', 'code', 'packaging')):
        raise ValueError('Actual parent is not bound to its completed immutable inventory')
    actual = final_artifact_binding(database, receipt['release'], receipt['source_graph_revision'])
    if actual['revision'] != receipt['revision']:
        raise ValueError('Completed six-stage parent revision changed')
    integrity = json.loads(integrity_path.read_bytes())
    if (any(integrity.get(k) is not True for k in ('pass', 'complete', 'integrity_pass',
            'file_unchanged_during_checks', 'all_frozen_inputs_and_recipes_checked'))
            or integrity.get('integrity_check') != ['ok']
            or Path(integrity.get('database', '')).resolve() != database
            or integrity.get('database_revision') != receipt['revision']
            or integrity.get('bytes') != database.stat().st_size
            or integrity.get('release') != receipt['release']
            or not isinstance(integrity.get('sha256'), str) or len(integrity['sha256']) != 64):
        raise ValueError('Actual complete parent integrity and whole-file hash receipt required')
    if (not meta.get('structure_resume_parent', {}).get('parent_revision')
            or meta.get('structure_delta_resume_parent', {}).get('repair_recipe') != 'resume_literal_jet_repairs.py'
            or meta.get('structure_complete_type_resume_parent', {}).get('repair_recipe') != 'resume_complete_owned_type_repairs.py'):
        raise ValueError('Complete physical-type parent adjudication lineage required')
    return receipt, meta, integrity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'parent-build', 'peer-parent-build', 'parent-integrity',
                 'peer-parent-integrity', 'baseline', 'database', 'inputs', 'reports', 'browse-staging'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    for name, path in vars(args).items():
        setattr(args, name, path.resolve())
    fingerprints, context = start_build(args.inputs, args.reports)
    states = {}
    temporary = args.database.parent / 'tmp'
    temporary.mkdir(exist_ok=True)
    os.environ.update(TMPDIR=str(temporary), SQLITE_TMPDIR=str(temporary))

    def stage(name, function):
        began = time.monotonic()
        states[name] = {'status': 'RUNNING', 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        status = args.reports / 'build_status.json'
        status.write_text(json.dumps(states, indent=2) + '\n')
        print('START', name, flush=True)
        try:
            require_stable_build(args.inputs, fingerprints)
            states[name].update(status='PASS', result=function())
            require_stable_build(args.inputs, fingerprints)
        except Exception as exc:
            states[name].update(status='FAIL', error=str(exc))
            raise
        finally:
            states[name]['seconds'] = time.monotonic() - began
            status.write_text(json.dumps(states, indent=2) + '\n')
        print('PASS', name, flush=True)
        return states[name]['result']

    def verify():
        independence = validate_resumed_parent_independence(args.parent_build, args.peer_parent_build)
        receipt, meta, integrity = validate_parent(args.source, args.parent_build,
                                                   args.parent_integrity, fingerprints)
        peer = json.loads(args.peer_parent_build.read_bytes())
        peer_source = Path(peer['database']).resolve()
        validate_parent(peer_source, args.peer_parent_build, args.peer_parent_integrity, fingerprints)
        for database in (args.source, peer_source, args.database):
            if any(Path(str(database) + suffix).exists() for suffix in ('-wal', '-journal', '-shm')):
                raise ValueError('Complete parents and pre-copied output must have no SQLite sidecars')
        if (receipt['revision'] != peer['revision'] or receipt['build_id'] == peer['build_id']
                or args.source.samefile(peer_source)):
            raise ValueError('Two distinct complete parents at the same semantic revision required')
        protection = protect_output(args.database, args.inputs, args.baseline, (args.source, peer_source))
        source_sha = verify_parent_byte_copy(args.source, args.database, integrity)
        return {'parent_build_id': receipt['build_id'], 'parent_revision': meta['database_revision'],
                'parent_receipt_sha256': digest_file(args.parent_build),
                'peer_parent_receipt_sha256': digest_file(args.peer_parent_build),
                'parent_integrity_sha256': digest_file(args.parent_integrity),
                'peer_parent_integrity_sha256': digest_file(args.peer_parent_integrity),
                'parent_database': str(args.source), 'parent_database_sha256': source_sha,
                'previous_source_stages_replayed': False, 'previous_repair_stages_replayed': False,
                'independent_previous_checkpoint': independence, 'protection': protection,
                'preserved_structure_resume_parent': meta['structure_resume_parent'],
                'preserved_structure_delta_resume_parent': meta['structure_delta_resume_parent'],
                'preserved_structure_complete_type_resume_parent': meta['structure_complete_type_resume_parent']}

    lineage = stage(STAGES[0], verify)
    migration = Migration(args.database, args.inputs, args.reports / 'graph-build')
    original_meta = read_metadata(args.database)
    original_stages = [dict(r) for r in migration.c.execute('SELECT * FROM usability_stages ORDER BY stage')]

    def apply():
        result = apply_nominal_design_scope_repairs(migration)
        if result.get('status') != 'PASS':
            raise ValueError('Approved complete-source type delta was not actually applied')
        current = read_metadata(args.database)
        mutable = {'usability_indexes_ready', 'unified_ready', 'browse_indexes_ready'}
        if (any(current.get(k) != v for k, v in original_meta.items() if k not in mutable)
                or original_stages != [dict(r) for r in migration.c.execute('SELECT * FROM usability_stages ORDER BY stage')]):
            raise ValueError('Append-only type delta modified prior metadata or source stage history')
        return result

    stage(STAGES[1], apply)
    migration.meta('structure_nominal_design_resume_parent', {
        'parent_revision': lineage['parent_revision'], 'repair_recipe': Path(__file__).name,
        'previous_source_stages_replayed': False, 'previous_repair_stages_replayed': False,
        'all_derived_indexes_recomputed': True})
    migration.c.commit()
    stage(STAGES[2], lambda: ram_graphs(migration))
    frozen = stage(STAGES[3], lambda: freeze_metadata(migration, fingerprints))
    (args.reports / 'frozen_metadata.json').write_text(json.dumps(frozen, indent=2) + '\n')
    migration.c.close()
    release = json.loads((args.inputs / 'review_release.json').read_bytes())['version']
    env = {**os.environ, 'PYTHONHASHSEED': '0', 'PYTHONDONTWRITEBYTECODE': '1',
           'PYTHONPATH': str(ROOT / 'src'), 'PYTHONPYCACHEPREFIX': sys.pycache_prefix}
    env.pop('PYTHONOPTIMIZE', None)

    def command(name, values):
        with (args.reports / (name + '.log')).open('w') as log:
            subprocess.run([sys.executable, '-B', *map(str, values)], cwd=ROOT, env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        return {'log': str(args.reports / (name + '.log'))}

    stage(STAGES[4], lambda: command('browse_staging', [ROOT / 'scripts/stage_browse_indexes.py',
        '--source', args.database, '--output', args.browse_staging,
        '--reports', args.reports / 'browse-build', '--release', release]))
    stage(STAGES[5], lambda: command('embed_browse_indexes', [ROOT / 'scripts/apply_browse_indexes.py',
        '--database', args.database, '--staging', args.browse_staging,
        '--source-revision', frozen['revision'], '--output', args.reports / 'browse_application.json']))
    require_stable_build(args.inputs, fingerprints)
    current = read_metadata(args.database)
    for name in ('structure_resume_parent', 'structure_delta_resume_parent', 'structure_complete_type_resume_parent'):
        if current.get(name) != lineage['preserved_' + name]:
            raise ValueError('Original immutable adjudication lineage changed')
    binding = final_artifact_binding(args.database, release, frozen['revision'])
    lineage_path = args.reports / 'parent_lineage.json'
    source_inode = [args.source.stat().st_dev, args.source.stat().st_ino]
    lineage_path.write_text(json.dumps({'schema': 'FINEATLAS_REPAIR_PARENT_LINEAGE_V1', **lineage,
        'resumed_build_id': context['build_id'], 'resumed_revision': binding['revision'],
        'parent_source_inode': source_inode}, indent=2) + '\n')
    context.update(parent_build_id=lineage['parent_build_id'],
                   parent_lineage_sha256=digest_file(lineage_path), parent_source_inode=source_inode)
    write_build_complete(args.reports, args.database, release, binding['revision'], context,
                         states, STAGES, source_graph_revision=frozen['revision'])


if __name__ == '__main__':
    main()
