#!/usr/bin/env python3
"""Verify every SQLite snapshot against the shipped SHA-256 inventory."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(root: Path) -> None:
    manifest = json.loads((root / 'bundle.json').read_text())
    for item in manifest['files']:
        path = root / item['path']
        if not path.is_file() or path.stat().st_size != item['bytes']:
            raise RuntimeError(f'Missing/incomplete file: {path}')
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                h.update(block)
        if h.hexdigest() != item['sha256']:
            raise RuntimeError(f'Checksum mismatch: {path}')
        print(f'OK {item["path"]}', flush=True)
    print(f'All {len(manifest["files"])} files verified.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[1])
    verify(p.parse_args().data_dir.resolve())
