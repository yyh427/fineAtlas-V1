#!/usr/bin/env python3
"""Download and verify the single-database release, with resumable assets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

from _download import digest, download

ROOT = Path(__file__).resolve().parents[1]


def install(root: Path, metadata: dict) -> Path:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    expected = metadata['database']
    if Path(expected['name']).name != expected['name']:
        raise ValueError('Invalid database filename')
    database = root / expected['name']
    if database.is_file():
        if database.stat().st_size == expected['bytes'] and digest(database) == expected['sha256']:
            verify_revision(database,metadata)
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
        temporary.replace(database)
        verify_revision(database,metadata)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait()
    compressed.unlink()
    (root / 'single_database.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(f'Verified {database}', flush=True)
    return database


def verify_revision(database,manifest):
    """Hash verification does not excuse a stale graph/view/index manifest."""
    if 'database_revision' not in manifest:return
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as c:
        meta={k:json.loads(v) for k,v in c.execute('SELECT key,value FROM metadata')}
    if meta.get('database_revision')!=manifest['database_revision']:
        raise RuntimeError('Snapshot revision differs from the release manifest')
    expected_view=manifest.get('default_relation_view')
    if expected_view and meta.get('default_relation_view','strict')!=expected_view:
        raise RuntimeError('Snapshot default view differs from the release manifest')
    if expected_view=='unified' and not(meta.get('unified_ready') and meta.get('usability_indexes_ready')
                                     and meta.get('browse_indexes_ready')
                                     and meta.get('browse_index_revision')==meta.get('database_revision')):
        raise RuntimeError('Unified graph or browse caches are incomplete/stale')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT)
    default_manifest=ROOT/'unified_data.json' if (ROOT/'unified_data.json').exists() else ROOT/'single_download.json'
    parser.add_argument('--manifest', type=Path, default=default_manifest,
                        help='Release manifest, or review_data.json for a separate candidate installation')
    args = parser.parse_args()
    install(args.output_dir, json.loads(args.manifest.read_text()))


if __name__ == '__main__':
    main()
