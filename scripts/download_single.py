#!/usr/bin/env python3
"""Download and verify the single-database release, with resumable assets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess

from _download import digest, download

ROOT = Path(__file__).resolve().parents[1]


def default_manifest(root: Path = ROOT) -> Path:
    """An absent default must not silently select an old production artifact."""
    for name in ('unified_data.json', 'single_download.json'):
        path = root / name
        if path.is_file():
            metadata = json.loads(path.read_text())
            if metadata.get('default_relation_view') != 'unified' or metadata.get('candidate') is not False:
                raise RuntimeError('The default manifest must describe a formal unified release; use --manifest explicitly for a preserved legacy/candidate release')
            validate_manifest(metadata)
            if metadata.get('sdk_version') != metadata['release'].removeprefix('v'):
                raise RuntimeError('Formal default data and SDK versions differ')
            return path
    raise FileNotFoundError('Missing formal unified release manifest; preserved releases require explicit --manifest')


def validate_manifest(manifest):
    if manifest.get('default_relation_view') == 'unified':
        if not all(manifest.get(k) for k in ('release','database_revision','sdk_version')):
            raise RuntimeError('Unified release manifest lacks exact release/revision/SDK version')
        if set(manifest.get('supported_relation_views',[])) != {'strict','taxonomy','membership','unified'}:
            raise RuntimeError('Unified release manifest lacks the four supported views')
        if not re.fullmatch('[0-9a-f]{64}', manifest['database_revision']):
            raise RuntimeError('Invalid exact unified database revision')


def runtime_sdk(manifest):
    """A download from one release cannot silently install into another SDK."""
    if manifest.get('default_relation_view') != 'unified':
        return None  # Explicit historical downloads retain their original contract.
    import fineatlas
    if not manifest.get('sdk_version') or fineatlas.__version__ != manifest['sdk_version']:
        raise RuntimeError('Installed SDK version differs from the release manifest; install the matching public code first')
    return fineatlas


def write_receipt(root, metadata):
    path = root / 'single_database.json'
    if path.exists() and json.loads(path.read_text()) != metadata:
        raise RuntimeError('Existing installation receipt belongs to a different release; choose a new output directory')
    temporary = path.with_suffix('.json.pending')
    temporary.write_text(json.dumps(metadata, indent=2) + '\n')
    temporary.replace(path)


def install(root: Path, metadata: dict) -> Path:
    validate_manifest(metadata)
    runtime_sdk(metadata)
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    receipt = root / 'single_database.json'
    if receipt.exists() and json.loads(receipt.read_text()) != metadata:
        raise RuntimeError('Existing installation receipt belongs to a different release; choose a new output directory')
    expected = metadata['database']
    if Path(expected['name']).name != expected['name']:
        raise ValueError('Invalid database filename')
    database = root / expected['name']
    if database.is_file():
        if database.stat().st_size == expected['bytes'] and digest(database) == expected['sha256']:
            verify_revision(database,metadata)
            write_receipt(root,metadata)
            print('Single database already verified.', flush=True)
            return database
        raise RuntimeError('Existing database has a different checksum; choose a new output directory')
    if not shutil.which('zstd'):
        raise RuntimeError('Install zstd first (apt install zstd / brew install zstd).')
    downloads = root / 'downloads'
    downloads.mkdir(exist_ok=True)
    assets = []
    for item in metadata['assets']:
        if Path(item['name']).name != item['name']:
            raise ValueError('Invalid asset filename')
        path = downloads / item['name']
        download(metadata['base_url'] + '/' + item['name'], path, item)
        assets.append(path)
    compressed = downloads / 'fineatlas.sqlite.zst'
    with compressed.open('wb') as target:
        for asset in assets:
            with asset.open('rb') as stream:
                shutil.copyfileobj(stream, target, 4 * 1024 * 1024)
    temporary = database.with_name(database.name + '.extracting')
    process = subprocess.Popen(['zstd', '-dc', '--', str(compressed)], stdout=subprocess.PIPE)
    h = hashlib.sha256()
    total = 0
    try:
        with temporary.open('wb') as target:
            for block in iter(lambda: process.stdout.read(4 * 1024 * 1024), b''):
                total += len(block)
                if total > expected['bytes']:
                    raise RuntimeError('Unexpected decompressed size')
                h.update(block)
                target.write(block)
        if process.wait() != 0 or total != expected['bytes'] or h.hexdigest() != expected['sha256']:
            raise RuntimeError('Database checksum/size mismatch')
        verify_revision(temporary,metadata)
        temporary.replace(database)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait()
    compressed.unlink()
    write_receipt(root,metadata)
    print(f'Verified {database}', flush=True)
    return database


def verify_revision(database,manifest):
    """Hash verification does not excuse a stale graph/view/index manifest."""
    if 'database_revision' not in manifest:return
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as c:
        meta={k:json.loads(v) for k,v in c.execute('SELECT key,value FROM metadata')}
    if meta.get('release') != manifest.get('release'):
        raise RuntimeError('Snapshot release differs from the release manifest')
    if meta.get('database_revision')!=manifest['database_revision']:
        raise RuntimeError('Snapshot revision differs from the release manifest')
    expected_view=manifest.get('default_relation_view')
    if expected_view and meta.get('default_relation_view','strict')!=expected_view:
        raise RuntimeError('Snapshot default view differs from the release manifest')
    if expected_view=='unified' and not(meta.get('unified_ready') and meta.get('usability_indexes_ready')
                                     and meta.get('browse_indexes_ready')
                                     and meta.get('browse_index_revision')==meta.get('database_revision')):
        raise RuntimeError('Unified graph or browse caches are incomplete/stale')
    if expected_view=='unified':
        if meta.get('schema') != 'FINEATLAS_SINGLE_DB_V1':
            raise RuntimeError('Unsupported unified database schema')
        if set(meta.get('supported_relation_views',[])) != set(manifest.get('supported_relation_views',[])):
            raise RuntimeError('Snapshot supported views differ from the release manifest')
        sdk = runtime_sdk(manifest)
        source = Path(sdk.__file__).resolve().parent
        code = meta.get('unified_frozen_build_manifest',{}).get('code',{})
        if not code or 'src/fineatlas/__init__.py' not in code:
            raise RuntimeError('Snapshot has no frozen SDK manifest')
        for name, expected in code.items():
            relative = Path(name)
            if relative.parts[:2] != ('src','fineatlas') or len(relative.parts) != 3:
                raise RuntimeError('Unexpected frozen SDK filename')
            path = source / relative.name
            if not path.is_file() or digest(path) != expected:
                raise RuntimeError('Installed SDK file differs from the frozen snapshot: '+name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT)
    parser.add_argument('--manifest', type=Path,
                        help='Explicit release manifest; preserved legacy/candidates never become an implicit default')
    args = parser.parse_args()
    manifest = args.manifest or default_manifest()
    install(args.output_dir, json.loads(manifest.read_text()))


if __name__ == '__main__':
    main()
