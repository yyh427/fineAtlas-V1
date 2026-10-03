#!/usr/bin/env python3
"""Download, verify and extract the complete FineAtlas data release."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def download(url: str, path: Path, expected: dict) -> None:
    if path.is_file() and path.stat().st_size == expected['bytes'] and digest(path) == expected['sha256']:
        print(f'Already verified {path.name}', flush=True)
        return
    temporary = path.with_name(path.name + '.download')
    for attempt in range(6):
        try:
            offset = temporary.stat().st_size if temporary.exists() else 0
            headers = {'User-Agent': 'FineAtlas-V1-download/1.0'}
            if offset:
                headers['Range'] = f'bytes={offset}-'
            with urlopen(Request(url, headers=headers), timeout=120) as response:
                append = offset > 0 and response.status == 206
                if append and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                    raise RuntimeError('Server returned an unexpected resume offset')
                with temporary.open('ab' if append else 'wb') as stream:
                    shutil.copyfileobj(response, stream, 1024 * 1024)
            if temporary.stat().st_size != expected['bytes'] or digest(temporary) != expected['sha256']:
                temporary.unlink(missing_ok=True)
                raise RuntimeError('Downloaded asset checksum/size mismatch')
            temporary.replace(path)
            print(f'Verified {path.name}', flush=True)
            return
        except Exception as exc:
            if attempt == 5:
                raise
            print(f'Retrying {path.name}: {exc}', flush=True)
            time.sleep(min(2 ** attempt, 30))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT)
    parser.add_argument('--download-only', action='store_true')
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not (root / 'bundle.json').exists():
        shutil.copy2(ROOT / 'bundle.json', root / 'bundle.json')
    if (root / 'bundle.json').read_bytes() != (ROOT / 'bundle.json').read_bytes():
        raise RuntimeError('Output directory has a different bundle.json; use a new directory')
    meta = json.loads((ROOT / 'data_download.json').read_text())
    downloads = root / 'downloads'
    downloads.mkdir(exist_ok=True)
    assets = []
    for item in meta['assets']:
        name = item['name']
        if Path(name).name != name:
            raise RuntimeError('Invalid asset name')
        path = downloads / name
        print(f'Downloading {name}', flush=True)
        download(meta['base_url'] + '/' + name, path, item)
        assets.append(path)
    if args.download_only:
        return
    if not shutil.which('zstd'):
        raise RuntimeError('Install zstd first (apt install zstd / brew install zstd). Assets are retained.')
    archive = downloads / 'fineatlas-v1-v33-data.tar.zst'
    with archive.open('wb') as destination:
        for path in assets:
            with path.open('rb') as source:
                shutil.copyfileobj(source, destination, 4 * 1024 * 1024)
    manifest = json.loads((root / 'bundle.json').read_text())
    expected = {item['path']: item for item in manifest['files']}
    extracted = set()
    process = subprocess.Popen(['zstd', '-dc', str(archive)], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|') as tar:
            for member in tar:
                name = member.name.removeprefix('./')
                if member.isdir():
                    continue
                if not member.isfile() or name not in expected or name in extracted:
                    raise RuntimeError(f'Unexpected archive entry: {name}')
                if member.size != expected[name]['bytes']:
                    raise RuntimeError(f'Unexpected archive member size: {name}')
                path = root / name
                if path.is_file() and digest(path) == expected[name]['sha256']:
                    extracted.add(name)
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(path.name + '.extracting')
                source = tar.extractfile(member)
                h = hashlib.sha256()
                with temporary.open('wb') as destination:
                    for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
                        destination.write(block)
                        h.update(block)
                if h.hexdigest() != expected[name]['sha256']:
                    temporary.unlink(missing_ok=True)
                    raise RuntimeError(f'Extracted database checksum mismatch: {name}')
                temporary.replace(path)
                extracted.add(name)
                print(f'Extracted and verified {name}', flush=True)
        if process.wait() != 0 or extracted != set(expected):
            raise RuntimeError('Incomplete data archive')
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait()
    archive.unlink()
    print('Complete graph installed. Downloaded parts remain in downloads/.')


if __name__ == '__main__':
    main()
