"""SHA-256 checks and resumable downloads for FineAtlas V1."""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import time
from urllib.request import Request, urlopen


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
    if temporary.is_file() and temporary.stat().st_size >= expected['bytes']:
        if temporary.stat().st_size == expected['bytes'] and digest(temporary) == expected['sha256']:
            temporary.replace(path)
            print(f'Recovered verified {path.name}', flush=True)
            return
        temporary.unlink()
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

