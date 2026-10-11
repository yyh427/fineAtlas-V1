"""Portable proof for the actual appended build, separate from its ancestors."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from _download import digest
from resume_structure_repairs import validate_resumed_parent_independence
from structure_complete_owned_type_delivery_guard import require_complete_type_child_build, STAGES
from structure_literal_jet_delivery_guard import require_literal_jet_child_build, CHILD_STAGES

NAME = 'complete-type-checkpoint-proof.json'
SCHEMA = 'FINEATLAS_COMPLETE_TYPE_ACTUAL_CHECKPOINT_PROOF_V1'


def json_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def record(path):
    path = Path(path)
    return {'sha256': digest(path), 'text': path.read_text()}


def package_checkpoint_proof(config, output, accepted):
    paths = [Path(config[key]) for key in ('primary_build', 'reproduction_build')]
    independence = validate_resumed_parent_independence(*paths)
    rows = []
    for name, path in zip(('primary', 'reproduction'), paths):
        child = require_complete_type_child_build(path)
        if child['revision'] != accepted['database_revision']:
            raise ValueError('Final child proof must identify the actually accepted revision')
        lineage_path = path.parent / 'parent_lineage.json'
        lineage = json.loads(lineage_path.read_bytes())
        ancestor_path = Path(config['lineage_' + name + '_build'])
        ancestor = require_literal_jet_child_build(ancestor_path)
        integrity_path = Path(config['complete_type_' + name + '_parent_integrity'])
        integrity = json.loads(integrity_path.read_bytes())
        if (digest(ancestor_path) != lineage['parent_receipt_sha256']
                or digest(integrity_path) != lineage['parent_integrity_sha256']
                or ancestor['revision'] != lineage['parent_revision']
                or integrity.get('sha256') != lineage['parent_database_sha256']
                or integrity.get('database_revision') != ancestor['revision']):
            raise ValueError('Actual final child, eight-stage ancestor and complete integrity disagree')
        source = Path(lineage['parent_database']).resolve()
        if source != Path(ancestor['database']).resolve():
            raise ValueError('Final delta was appended to another physical source')
        rows.append({'name': name, 'files': {
            'build_complete.json': record(path),
            'parent_lineage.json': record(lineage_path),
            'started_fingerprints.json': record(path.parent / 'started_fingerprints.json'),
            'build_status.json': record(path.parent / 'build_status.json'),
            'parent_build_complete.json': record(ancestor_path),
            'parent_started_fingerprints.json': record(ancestor_path.parent / 'started_fingerprints.json'),
            'parent_build_status.json': record(ancestor_path.parent / 'build_status.json'),
            'parent_integrity.json': record(integrity_path)}})
    proof = {'schema': SCHEMA, 'pass': True, 'database_revision': accepted['database_revision'],
             'database_sha256': accepted['database_sha256'], 'actual_local_parent_independence': independence,
             'local_physical_source_inodes_checked': True, 'final_required_stages': list(STAGES),
             'children': rows, 'scope': 'Actual six-stage final builds and actual complete eight-stage parents; public verification rechecks immutable historical bytes.'}
    path = Path(output) / NAME
    if path.exists():
        raise ValueError('Do not overwrite an existing actual checkpoint proof')
    path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
    return path


def validate_checkpoint_proof(path, accepted):
    """Check downloaded historical bytes, without claiming local source copies."""
    proof = json.loads(Path(path).read_bytes())
    if (proof.get('schema') != SCHEMA or proof.get('pass') is not True
            or proof.get('database_revision') != accepted['database_revision']
            or proof.get('database_sha256') != accepted['database_sha256']
            or proof.get('local_physical_source_inodes_checked') is not True
            or proof.get('final_required_stages') != list(STAGES)
            or proof.get('actual_local_parent_independence', {}).get('pass') is not True):
        raise ValueError('Actual final independent checkpoint proof is not bound')
    children = proof.get('children', [])
    if len(children) != 2 or {r['name'] for r in children} != {'primary', 'reproduction'}:
        raise ValueError('Two named actual final builds are required')
    expected_files = {'build_complete.json', 'parent_lineage.json', 'started_fingerprints.json',
                      'build_status.json', 'parent_build_complete.json', 'parent_started_fingerprints.json',
                      'parent_build_status.json', 'parent_integrity.json'}
    verified = []
    for name in ('primary', 'reproduction'):
        child = next(r for r in children if r['name'] == name)
        files = child['files']
        if set(files) != expected_files:
            raise ValueError('Actual child or parent source proof is incomplete')
        for row in files.values():
            if hashlib.sha256(row['text'].encode()).hexdigest() != row['sha256']:
                raise ValueError('Historical checkpoint evidence bytes changed')
        values = {name: json.loads(row['text']) for name, row in files.items()}
        complete = values['build_complete.json']
        lineage = values['parent_lineage.json']
        parent = values['parent_build_complete.json']
        integrity = values['parent_integrity.json']
        states = values['build_status.json']
        parent_states = values['parent_build_status.json']
        if (complete.get('complete') is not True or complete.get('pass') is not True
                or complete.get('revision') != accepted['database_revision']
                or complete.get('required_stages') != list(STAGES)
                or set(states) != set(STAGES) or any(s.get('status') != 'PASS' for s in states.values())
                or complete.get('started_fingerprints_sha256') != files['started_fingerprints.json']['sha256']
                or complete.get('build_status_sha256') != files['build_status.json']['sha256']
                or complete.get('parent_lineage_sha256') != files['parent_lineage.json']['sha256']
                or lineage.get('resumed_build_id') != complete.get('build_id')
                or lineage.get('resumed_revision') != complete['revision']
                or lineage.get('parent_build_id') != complete.get('parent_build_id')
                or lineage.get('parent_source_inode') != complete.get('parent_source_inode')
                or lineage.get('parent_build_id') != parent.get('build_id')
                or lineage.get('parent_revision') != parent.get('revision')
                or lineage.get('parent_receipt_sha256') != files['parent_build_complete.json']['sha256']
                or lineage.get('parent_integrity_sha256') != files['parent_integrity.json']['sha256']
                or parent.get('complete') is not True or parent.get('pass') is not True
                or parent.get('required_stages') != list(CHILD_STAGES)
                or set(parent_states) != set(parent['required_stages'])
                or any(s.get('status') != 'PASS' for s in parent_states.values())
                or parent.get('started_fingerprints_sha256') != files['parent_started_fingerprints.json']['sha256']
                or parent.get('build_status_sha256') != files['parent_build_status.json']['sha256']
                or integrity.get('sha256') != lineage.get('parent_database_sha256')
                or integrity.get('database_revision') != parent.get('revision')
                or any(integrity.get(k) is not True for k in ('pass', 'complete', 'integrity_pass',
                    'file_unchanged_during_checks', 'all_frozen_inputs_and_recipes_checked'))
                or integrity.get('integrity_check') != ['ok']):
            raise ValueError('Actual final/parent stages, lineage and integrity disagree')
        inventory = values['started_fingerprints.json']
        if inventory != accepted['fingerprints']:
            raise ValueError('Final actual build inventory differs from the accepted artifact')
        parent_inventory = values['parent_started_fingerprints.json']
        for group in ('inputs', 'code', 'packaging'):
            if any(inventory[group].get(n) != d for n, d in parent_inventory[group].items()):
                raise ValueError('Final build did not preserve its immutable parent implementation and inputs')
        verified.append((complete, lineage))
    one, two = verified
    historical = proof['actual_local_parent_independence']
    if (one[0]['build_id'] == two[0]['build_id']
            or one[1]['parent_build_id'] == two[1]['parent_build_id']
            or one[1]['parent_source_inode'] == two[1]['parent_source_inode']
            or one[1]['parent_revision'] != two[1]['parent_revision']
            or historical.get('resumed_build_ids') != [r[0]['build_id'] for r in verified]
            or historical.get('parent_build_ids') != [r[1]['parent_build_id'] for r in verified]
            or historical.get('parent_revision') != one[1]['parent_revision']
            or historical.get('distinct_source_inodes') is not True):
        raise ValueError('Two genuinely independent final build histories are required')
    return {'pass': True, 'database_revision': accepted['database_revision'],
            'checkpoint_proof_sha256': digest(Path(path)), 'immutable_actual_historical_bytes_checked': True,
            'physical_parent_inodes_rechecked_here': False}
