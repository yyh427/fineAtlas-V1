"""Portable exact proof for nominal children, direct Source8 parents and c933 ancestors."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from _download import digest
from portable_nominal_structure_lineage import package_lineage_members, validate_portable_parent_independence

NAME = 'nominal-scope-checkpoint-proof.json'
SCHEMA = 'FINEATLAS_NOMINAL_SCOPE_ACTUAL_CHECKPOINT_PROOF_V1'


def package_checkpoint_proof(config, output, accepted):
    output = Path(output)
    target = output / NAME
    if target.exists():
        raise ValueError('Preserve existing actual nominal checkpoint proof')
    directory = output / 'nominal-checkpoint-historical-bytes'
    directory.mkdir()
    members = package_lineage_members(config, directory, accepted)
    for name, source in members.items():
        destination = directory / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != destination.resolve():
            shutil.copyfile(source, destination)
    portable = SimpleNamespace(root=directory)
    verified = validate_portable_parent_independence(portable,
        directory / 'builds/primary/build_complete.json',
        directory / 'builds/reproduction/build_complete.json', accepted)
    files = {}
    for name in members:
        path = directory / name
        files[name] = {'sha256': digest(path), 'text': path.read_text()}
    proof = {'schema': SCHEMA, 'pass': True, 'database_revision': accepted['database_revision'],
             'database_sha256': accepted['database_sha256'], 'files': files,
             'historical_independent_generations': verified,
             'scope': 'Actual current nominal six-stage children, immediate complete-owned-type six-stage parents, and c933 eight-stage ancestors. Public verification checks archived bytes, not unavailable historical local inodes.'}
    target.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
    return target


def validate_checkpoint_proof(path, accepted):
    path = Path(path)
    proof = json.loads(path.read_bytes())
    if (proof.get('schema') != SCHEMA or proof.get('pass') is not True
            or proof.get('database_revision') != accepted['database_revision']
            or proof.get('database_sha256') != accepted['database_sha256']):
        raise ValueError('Actual nominal checkpoint proof is not bound to the accepted final artifact')
    import tempfile
    with tempfile.TemporaryDirectory(prefix='fineatlas-nominal-checkpoint-') as temporary:
        root = Path(temporary)
        for name, row in proof['files'].items():
            member = Path(name)
            if member.is_absolute() or '..' in member.parts or not member.parts:
                raise ValueError('Unsafe portable historical checkpoint member')
            if hashlib.sha256(row['text'].encode()).hexdigest() != row['sha256']:
                raise ValueError('Actual historical checkpoint bytes changed')
            target = root / member
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(row['text'])
        verified = validate_portable_parent_independence(SimpleNamespace(root=root),
            root / 'builds/primary/build_complete.json', root / 'builds/reproduction/build_complete.json', accepted)
    if verified != proof['historical_independent_generations']:
        raise ValueError('Archived three-generation independence proof differs')
    return {'pass': True, 'database_revision': accepted['database_revision'],
            'checkpoint_proof_sha256': digest(path), 'immutable_actual_historical_bytes_checked': True,
            'physical_parent_inodes_rechecked_here': False}
