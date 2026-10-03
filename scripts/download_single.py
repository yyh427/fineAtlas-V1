#!/usr/bin/env python3
"""Download and verify the single-database release, with resumable assets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from download_data import digest, download

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
    compressed = downloads / 'fineatlas-v34.sqlite.zst'
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT)
    args = parser.parse_args()
    install(args.output_dir, json.loads((ROOT / 'single_download.json').read_text()))


if __name__ == '__main__':
    main()
