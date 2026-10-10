#!/usr/bin/env python3
"""Package or freshly retrieve the exact external audit supplement."""

if not __debug__:
    raise RuntimeError('Optimized Python is forbidden for mandatory independent audit gates')

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request
from urllib.parse import urlparse


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    assert not output.exists() and not output.is_relative_to(root)
    manifest_path = root / 'SUPPLEMENT_CODE_MANIFEST.json'
    manifest = json.loads(manifest_path.read_text())
    members = {**manifest['files'], 'SUPPLEMENT_CODE_MANIFEST.json': digest(manifest_path)}
    assert set(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()) == set(members)
    with output.open('wb') as target, gzip.GzipFile(fileobj=target, mode='wb', filename='', mtime=0) as compressed, tarfile.open(fileobj=compressed, mode='w|') as archive:
        for relative, expected in sorted(members.items()):
            path = root / relative
            assert not path.is_symlink() and digest(path) == expected
            data = path.read_bytes()
            info = tarfile.TarInfo(root.name + '/' + relative)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = info.uid = info.gid = 0
            archive.addfile(info, io.BytesIO(data))
    return {'archive': str(output), 'archive_sha256': digest(output), 'archive_bytes': output.stat().st_size, 'manifest_sha256': digest(manifest_path), 'member_sha256': members}


def download(url, expected_sha, expected_bytes, destination, output):
    assert urlparse(url).scheme == 'https'
    destination, output = Path(destination).resolve(), Path(output).resolve()
    assert not destination.exists() and not output.exists()
    destination.mkdir(parents=True)
    archive_path = destination / 'supplement.tar.gz'
    h = hashlib.sha256()
    total = 0
    request = urllib.request.Request(url, headers={'User-Agent': 'FineAtlas-Independent-External-Supplement/1'})
    with urllib.request.urlopen(request, timeout=120) as response, archive_path.open('wb') as target:
        response_url = response.geturl()
        assert urlparse(response_url).scheme == 'https'
        for block in iter(lambda: response.read(1024 * 1024), b''):
            total += len(block)
            assert total <= expected_bytes
            h.update(block)
            target.write(block)
    assert total == expected_bytes and h.hexdigest() == expected_sha
    with tarfile.open(archive_path, 'r:gz') as archive:
        names = set()
        top_levels = set()
        for member in archive.getmembers():
            name = Path(member.name)
            assert not name.is_absolute() and '..' not in name.parts and '\\' not in member.name
            assert member.isfile() and member.name not in names
            names.add(member.name)
            top_levels.add(name.parts[0])
            path = destination / name
            assert path.resolve().is_relative_to(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            content = archive.extractfile(member)
            assert content is not None
            path.write_bytes(content.read())
    assert len(top_levels) == 1
    root = destination / next(iter(top_levels))
    manifest_path = root / 'SUPPLEMENT_CODE_MANIFEST.json'
    manifest = json.loads(manifest_path.read_text())
    assert manifest['schema'] == 'FINEATLAS_INDEPENDENT_EXTERNAL_AUDIT_SUPPLEMENT_CODE_V1'
    members = {**manifest['files'], 'SUPPLEMENT_CODE_MANIFEST.json': digest(manifest_path)}
    assert {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()} == set(members)
    assert all(digest(root / name) == expected for name, expected in members.items())
    proof = {'schema': 'FINEATLAS_EXTERNAL_AUDIT_SUPPLEMENT_DOWNLOAD_PROOF_V1', 'fresh_download': True, 'network_request': True, 'authenticated': False, 'source_url': url, 'response_url': response_url, 'archive': str(archive_path), 'archive_sha256': expected_sha, 'archive_bytes': total, 'archive_stamp': [archive_path.stat().st_size, archive_path.stat().st_mtime_ns, archive_path.stat().st_ino], 'extracted_root': str(root), 'manifest_sha256': digest(manifest_path), 'member_sha256': members}
    output.write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    pack = sub.add_parser('package')
    pack.add_argument('--source', type=Path, required=True)
    pack.add_argument('--output', type=Path, required=True)
    get = sub.add_parser('download')
    get.add_argument('--url', required=True)
    get.add_argument('--sha256', required=True)
    get.add_argument('--bytes', type=int, required=True)
    get.add_argument('--destination', type=Path, required=True)
    get.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert __debug__
    result = package(args.source, args.output) if args.command == 'package' else download(args.url, args.sha256, args.bytes, args.destination, args.output)
    print(json.dumps(result, indent=2))
