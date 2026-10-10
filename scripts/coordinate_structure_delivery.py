#!/usr/bin/env python3
"""Reproducible staged local/package/public acceptance; never upload or promote.

All paths are supplied by a reviewable JSON configuration. Each action has an
exclusive lease, retained command log and fingerprint-bound completion receipt.
Public SDK, frozen inputs and data must be fresh unauthenticated network downloads.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from _download import digest, download
from build_structure_candidate import build_fingerprints
from resume_structure_repairs import validate_resumed_parent_independence


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def metadata(path):
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as con:
        return {key: json.loads(value) for key, value in con.execute('SELECT * FROM metadata')}


def is_stable_release(release):
    """Final three-part versions are stable; prerelease/nightly suffixes are not."""
    return bool(re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', release))


@contextmanager
def lease(path):
    """Refuse duplicate execution; failed/dead leases need explicit investigation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump({'pid': os.getpid()}, stream)
    try:
        yield
    finally:
        path.unlink()


def require_fresh(proof):
    if (proof.get('fresh_download') is not True or proof.get('network_request') is not True or
            proof.get('authenticated') is not False or proof.get('initial_cached_bytes') != 0):
        raise ValueError('Fresh unauthenticated network transfer required; preserve prior files and select a new public-run directory')


def safe_extract(archive, output, expected):
    """Extract only declared immutable inputs and license files; verify each hash."""
    output.mkdir(exist_ok=False, parents=True)
    process = subprocess.Popen(['zstd', '-dc', '--', str(archive)], stdout=subprocess.PIPE)
    seen = set()
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|') as stream:
            for member in stream:
                path = Path(member.name)
                if (not member.isfile() or path.is_absolute() or '..' in path.parts or
                        member.name not in expected or member.name in seen):
                    raise ValueError('Unexpected, duplicate or unsafe archive member: ' + member.name)
                seen.add(member.name)
                target = output / path
                target.parent.mkdir(parents=True, exist_ok=True)
                with stream.extractfile(member) as source, target.open('xb') as dest:
                    shutil.copyfileobj(source, dest, 4 * 1024 * 1024)
                if digest(target) != expected[member.name]:
                    raise ValueError('Public frozen input hash mismatch: ' + member.name)
        if process.wait() != 0 or seen != set(expected):
            raise ValueError('Incomplete public frozen input archive')
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait()


class Coordinator:
    def __init__(self, config):
        self.config_path = Path(config).resolve()
        self.c = read(config)
        self.root = Path(self.c['delivery_root']).resolve()
        self.inputs = Path(self.c['inputs']).resolve()
        self.meta = metadata(self.c['database'])
        self.fingerprints = build_fingerprints(self.inputs)
        freeze = self.meta['structure_frozen_build_manifest']
        if {key: freeze[key] for key in self.fingerprints} != self.fingerprints:
            raise ValueError('Coordinator code or inputs differ from the completed candidate freeze')
        self.lineage_primary = Path(self.c.get('lineage_primary_build', self.c['primary_build']))
        self.lineage_reproduction = Path(self.c.get('lineage_reproduction_build', self.c['reproduction_build']))
        self.parents = validate_resumed_parent_independence(self.lineage_primary, self.lineage_reproduction)
        expected_ancestor = freeze.get('promotion', {}).get('parent_candidate_revision', self.meta['database_revision'])
        if any(read(path)['revision'] != expected_ancestor for path in (self.lineage_primary, self.lineage_reproduction)):
            raise ValueError('Actual artifacts are not descendants of the independently resumed candidate')
        for key in ('primary_build', 'reproduction_build'):
            if read(self.c[key])['revision'] != self.meta['database_revision']:
                raise ValueError('Coordinator and resumed build snapshots differ')
        self.env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
        self.env.pop('PYTHONOPTIMIZE', None)
        self.env['PYTHONPATH'] = str(ROOT / 'src')

    def cmd(self, script, *values, python=None):
        return [str(python or sys.executable), '-B', str(ROOT / 'scripts' / script), *map(str, values)]

    def data_package_command(self, output):
        values = ['--database', self.c['database'], '--output', output,
                  '--release', self.meta['release']]
        if is_stable_release(self.meta['release']):
            values.append('--stable')
        # The unmodified packager independently checks the exact stable SDK
        # version and rejects a prerelease SDK for stable data packaging.
        return self.cmd('package_browse_candidate.py', *values)

    def execute(self, name, argv, env=None):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / (name + '.log')).open('w') as stream:
            subprocess.run(argv, cwd=ROOT, env=env or self.env,
                           stdout=stream, stderr=subprocess.STDOUT, check=True)

    def accepted(self):
        value = read(self.c['local_output'] + '/acceptance_receipt.json')
        if (value.get('local_all_pass') is not True or value.get('candidate_unchanged') is not True or
                value.get('database_revision') != self.meta['database_revision'] or
                value.get('fingerprints') != self.fingerprints):
            raise ValueError('Actual complete matching local acceptance required')
        for name, key in [('primary', 'database'), ('reproduction', 'reproduction')]:
            stamp = Path(self.c[key]).stat()
            if [stamp.st_size, stamp.st_mtime_ns, stamp.st_ino] != value['artifact_stamps'][name]:
                raise ValueError('Accepted artifact changed before delivery')
        return value

    def local(self):
        complete = self.root / 'local_complete.json'
        if complete.exists():
            previous = read(complete)
            if previous.get('fingerprints') != self.fingerprints or previous.get('revision') != self.meta['database_revision']:
                raise ValueError('Completed delivery action belongs to another snapshot')
            self.accepted()
            return
        output = Path(self.c['local_output'])
        receipt = output / 'acceptance_receipt.json'
        if receipt.exists():
            # A running or failed predecessor is investigated, never restarted.
            self.accepted()
        else:
            self.execute('local-acceptance', self.cmd('accept_structure_candidate.py', 'local',
                '--database', self.c['database'], '--reproduction', self.c['reproduction'],
                '--baseline', self.c['baseline'], '--inputs', self.inputs, '--inventory', self.c['inventory'],
                '--reference', self.c['reference'], '--output', output,
                '--primary-build', self.c['primary_build'], '--reproduction-build', self.c['reproduction_build'], '--workers', '3'))
        for name, database in [('primary', self.c['database']), ('reproduction', self.c['reproduction'])]:
            self.execute(name + '-scope-repairs', self.cmd('audit_structure_regression_repairs.py',
                '--database', database, '--inputs', self.inputs, '--output', self.root / (name + '-scope-repairs.json')))
        self.execute('local-legacy-regressions', self.cmd('audit_legacy_pair_regressions.py',
            '--reference', self.c['legacy_reference'], '--baseline', self.c['legacy_baseline_matrix'],
            '--candidate', output / 'matrix', '--policy', self.inputs / 'legacy_policies.json',
            '--dispositions', self.c['legacy_dispositions'], '--output', self.root / 'local-legacy-regressions'))
        write(self.root / 'local_complete.json', {'pass': True, 'revision': self.meta['database_revision'],
              'parents': self.parents, 'fingerprints': self.fingerprints,
              'evidence': [{'path': str(path), 'sha256': digest(path)} for path in (
                  self.root / 'primary-scope-repairs.json', self.root / 'reproduction-scope-repairs.json',
                  self.root / 'local-legacy-regressions/summary.json')]})

    def package(self):
        accepted = self.accepted()
        local = read(self.root / 'local_complete.json')
        if local['revision'] != self.meta['database_revision']:
            raise ValueError('Extended local checks incomplete')
        if any(digest(Path(row['path'])) != row['sha256'] for row in local['evidence']):
            raise ValueError('Extended local evidence changed')
        out = self.root / 'package'
        out.mkdir(exist_ok=False)
        self.execute('package-data', self.data_package_command(out / 'data'))
        if read(out / 'data/review_data.json')['database']['sha256'] != accepted['database_sha256']:
            raise ValueError('Packaged data differs from the actual accepted artifact')
        self.execute('package-sdk', [sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
                     '--wheel-dir', str(out / 'sdk'), str(ROOT)])
        wheel, = (out / 'sdk').glob('*.whl')
        expected_sdk = {name.removeprefix('src/'): value for name, value in self.fingerprints['code'].items() if name.startswith('src/fineatlas/')}
        with zipfile.ZipFile(wheel) as archive:
            actual = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist() if name.startswith('fineatlas/') and name.endswith('.py')}
        if actual != expected_sdk:
            raise ValueError('Packaged wheel differs from the exact frozen SDK inventory')
        members = {'inputs/' + name: (self.inputs / name, value) for name, value in self.fingerprints['inputs'].items()}
        for name in ('ABO-ATTRIBUTION.txt', 'ABO-LICENSE-CC-BY-4.0.txt', 'DATA_SOURCES.md', 'LICENSE', 'WORDNET_LICENSE.txt'):
            source = Path(self.c['licenses']) / name
            members['licenses/' + name] = (source, digest(source))
        tar = out / 'inputs.tar'
        with tarfile.open(tar, 'w') as archive:
            for name, (path, expected) in sorted(members.items()):
                if digest(path) != expected:
                    raise ValueError('Input or attribution changed while packaging')
                info = archive.gettarinfo(str(path), arcname=name)
                if not info.isfile():
                    raise ValueError('Frozen archive must contain regular files')
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ''
                with path.open('rb') as stream:
                    archive.addfile(info, stream)
        archive_path = out / ('fineatlas-' + self.meta['release'] + '-frozen-inputs.tar.zst')
        self.execute('compress-inputs', ['zstd', '-T4', '-8', '-o', str(archive_path), '--', str(tar)])
        member_hashes = {name: value for name, (_, value) in members.items()}
        safe_extract(archive_path, out / 'independent-input-roundtrip', member_hashes)
        tar.unlink()
        for script in ('prepare_structure_install_expectations.py',):
            self.execute('prepare-install-expectations', self.cmd(script, '--database', self.c['database'],
                '--acceptance', Path(self.c['local_output']) / 'acceptance_receipt.json',
                '--manifest', out / 'data/review_data.json', '--output', out / 'installed_expectations.json'))
        assets = [wheel, archive_path, out / 'data/review_data.json', out / 'installed_expectations.json',
                  *sorted((out / 'data').glob('*.part-*'))]
        release = {'schema': 'FINEATLAS_REVIEWABLE_DELIVERY_PACKAGE_V1', 'release': self.meta['release'],
                   'database_revision': accepted['database_revision'], 'database_sha256': accepted['database_sha256'],
                   'frozen_inputs': member_hashes, 'wheel': wheel.name, 'input_archive': archive_path.name,
                   'assets': [{'path': str(path), 'name': path.name, 'bytes': path.stat().st_size, 'sha256': digest(path)} for path in assets]}
        write(out / 'delivery_assets.json', release)

    def public(self):
        accepted = self.accepted()
        package = read(self.root / 'package/delivery_assets.json')
        if package['database_revision'] != accepted['database_revision']:
            raise ValueError('Package belongs to another candidate')
        public = self.root / 'public'
        public.mkdir(exist_ok=False)
        proofs = {}
        required = {package['wheel'], package['input_archive'], 'review_data.json', 'installed_expectations.json'}
        for asset in package['assets']:
            if asset['name'] in required:
                proof = download(self.c['public_base_url'].rstrip('/') + '/' + asset['name'], public / asset['name'], asset)
                require_fresh(proof)
                proofs[asset['name']] = proof
        write(public / 'public_dependency_downloads.json', proofs)
        manifest = read(public / 'review_data.json')
        if (manifest['database']['sha256'] != accepted['database_sha256'] or
                manifest['database_revision'] != accepted['database_revision'] or
                manifest['base_url'].rstrip('/') != self.c['public_base_url'].rstrip('/')):
            raise ValueError('Public manifest differs from accepted package or public URL')
        safe_extract(public / package['input_archive'], public / 'frozen', package['frozen_inputs'])
        self.execute('create-public-env', [sys.executable, '-m', 'venv', str(public / 'venv')])
        python = public / 'venv/bin/python'
        env = dict(self.env)
        env.pop('PYTHONPATH', None)
        self.execute('install-public-sdk', [str(python), '-m', 'pip', 'install', '--no-deps', str(public / package['wheel'])], env)
        self.execute('download-public-data', self.cmd('download_single.py', '--manifest', public / 'review_data.json',
                     '--output-dir', public / 'data', python=python), env)
        self.execute('actual-public-checks', self.cmd('run_structure_public_checks.py', '--code', ROOT,
            '--python', python, '--database', public / 'data/fineatlas.sqlite', '--inputs', public / 'frozen/inputs',
            '--baseline', self.c['baseline'], '--inventory', self.c['inventory'], '--manifest', public / 'review_data.json',
            '--expected', public / 'installed_expectations.json', '--acceptance', Path(self.c['local_output']) / 'acceptance_receipt.json',
            '--output', public / 'checks', '--primary-build', self.lineage_primary, '--reproduction-build', self.lineage_reproduction,
            '--legacy-reference', self.c['legacy_reference'], '--legacy-baseline-matrix', self.c['legacy_baseline_matrix'],
            '--legacy-dispositions', self.c['legacy_dispositions']), env)

    def finalize(self):
        extension = read(self.root / 'public/checks/resume_public_extension.json')
        accepted = self.accepted()
        if extension.get('pass') is not True or extension['database_revision'] != accepted['database_revision']:
            raise ValueError('Full public repair and regression extension incomplete')
        for row in extension['evidence'].values():
            if digest(Path(row['path'])) != row['sha256']:
                raise ValueError('Public extension evidence changed')
        self.execute('finalize-original-contract', self.cmd('accept_structure_candidate.py', 'finalize',
            '--inputs', self.inputs, '--output', self.c['local_output'],
            '--public-verification', self.root / 'public/checks/public_verification.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('local', 'package', 'public', 'finalize'))
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError('Optimized Python cannot run mandatory checks')
    coordinator = Coordinator(args.config)
    with lease(coordinator.root / (args.action + '.lease.json')):
        getattr(coordinator, args.action)()
