"""Explicit official HTTP snapshots, with fresh retrieval evidence and no fallback."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request
from urllib.parse import urlparse

REGISTRY_NAME = 'structure_primary_source_snapshots.json'
REGISTRY_SCHEMA = 'FINEATLAS_PORTABLE_PRIMARY_SOURCE_SNAPSHOTS_V1'
RECEIPT_SCHEMA = 'FINEATLAS_FRESH_PRIMARY_SOURCE_RETRIEVAL_V1'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def registry(inputs, manifest_name='structure_primary_aircraft_family_repairs.json'):
    inputs = Path(inputs)
    value = json.loads((inputs / REGISTRY_NAME).read_text())
    manifest = json.loads((inputs / manifest_name).read_text())
    documents = manifest['primary_documents']
    external = {key: doc for key, doc in documents.items()
                if doc.get('source_kind') != 'SOURCE_OWNED_COMPLETE_DESCRIPTION'}
    if value.get('schema') != REGISTRY_SCHEMA or set(value.get('documents', {})) != set(external):
        raise ValueError('Portable registry must exactly cover sealed external documents')
    filenames = set()
    for key, entry in value['documents'].items():
        filename = entry.get('filename', '')
        parsed = urlparse(entry.get('source_uri', ''))
        if (not filename or Path(filename).name != filename or filename in ('.', '..')
                or filename in filenames or '\\' in filename
                or parsed.scheme != 'https' or not parsed.hostname
                or parsed.username or parsed.password
                or entry.get('source_uri') != external[key]['source_uri']
                or entry.get('sha256') != external[key]['sha256']
                or not re.fullmatch('[a-f0-9]{64}', entry.get('sha256', ''))
                or entry.get('hash_basis') != 'HTTP_RESPONSE_BODY_BYTES'
                or not entry.get('mime_type') or not entry.get('revision_locator')
                or not entry.get('redistribution_authorization')):
            raise ValueError('Unsafe or unbound official source registry entry: ' + key)
        filenames.add(filename)
    return value, documents


def require_snapshot_files(inputs, directory, audit=None, manifest_name='structure_primary_aircraft_family_repairs.json'):
    value, documents = registry(inputs, manifest_name)
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError('An actual explicit directory of primary source snapshots is required')
    checked = audit.get('primary_snapshot_actual_hashes', {}) if audit is not None else None
    if audit is not None and (audit.get('primary_source_registry_sha256') != digest(Path(inputs) / REGISTRY_NAME)
            or Path(audit.get('primary_snapshots_dir') or '/MISSING').resolve() != directory
            or set(checked) != set(documents)):
        raise ValueError('Actual primary document evidence must bind registry and explicit directory')
    for key, entry in value['documents'].items():
        path = directory / entry['filename']
        if path.is_symlink() or not path.is_file() or path.resolve().parent != directory or digest(path) != entry['sha256']:
            raise ValueError('Actual explicit primary source snapshot is absent or changed: ' + key)
        if checked is not None:
            row = checked[key]
            if (row.get('pass') is not True or row.get('actual_sha256') != entry['sha256']
                    or row.get('expected_sha256') != entry['sha256']
                    or Path(row.get('path', '')).resolve() != path.resolve()):
                raise ValueError('Independent source audit did not read the explicit snapshot: ' + key)
    if checked is not None:
        for key, doc in documents.items():
            if key in value['documents']:
                continue
            row = checked[key]
            if (row.get('path') != 'source-payload:' + doc['database_source_uid']
                    or row.get('pass') is not True or row.get('actual_sha256') != doc['sha256']
                    or row.get('expected_sha256') != doc['sha256']):
                raise ValueError('Source-owned SQL document evidence is missing: ' + key)
    return value


def require_fresh_retrieval(report, inputs, directory):
    value = require_snapshot_files(inputs, directory)
    receipt = json.loads(Path(report).read_text())
    if (receipt.get('schema') != RECEIPT_SCHEMA or receipt.get('pass') is not True
            or receipt.get('complete') is not True or receipt.get('fresh_official_https_retrieval') is not True
            or receipt.get('registry_sha256') != digest(Path(inputs) / REGISTRY_NAME)
            or Path(receipt.get('snapshots_directory', '')).resolve() != Path(directory).resolve()
            or set(receipt.get('documents', {})) != set(value['documents'])):
        raise ValueError('Complete fresh official primary source retrieval evidence is required')
    for key, entry in value['documents'].items():
        row = receipt['documents'][key]
        final = urlparse(row.get('final_uri', ''))
        requested = urlparse(entry['source_uri'])
        if (row.get('source_uri') != entry['source_uri'] or row.get('filename') != entry['filename']
                or row.get('sha256') != entry['sha256'] or row.get('http_status') != 200
                or row.get('retrieved_from_network') is not True or not row.get('retrieved_utc')
                or final.scheme != 'https' or final.hostname != requested.hostname
                or row.get('mime_type') != entry['mime_type']
                or row.get('byte_count') != (Path(directory) / entry['filename']).stat().st_size):
            raise ValueError('Official fresh retrieval facts are invalid: ' + key)
    return receipt


class HttpsOfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        before, after = urlparse(req.full_url), urlparse(newurl)
        if after.scheme != 'https' or after.hostname != before.hostname:
            raise ValueError('Source redirect left the explicit official HTTPS host')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def retrieve(inputs, directory, output):
    from datetime import datetime, timezone
    inputs, directory, output = Path(inputs), Path(directory), Path(output)
    if output.exists():
        return require_fresh_retrieval(output, inputs, directory)
    # Never reuse unreceipted files, including bytes from a partial prior attempt.
    if directory.exists() or output.with_suffix('.failed.json').exists():
        raise ValueError('Fresh source directory must be new; preserve prior failed retrieval material')
    value, _ = registry(inputs)
    directory.mkdir(parents=True)
    receipt = {'schema': RECEIPT_SCHEMA, 'pass': False, 'complete': False,
               'fresh_official_https_retrieval': True,
               'registry_sha256': digest(inputs / REGISTRY_NAME),
               'snapshots_directory': str(directory.resolve()), 'documents': {}, 'errors': []}
    opener = urllib.request.build_opener(HttpsOfficialRedirect())
    try:
        for key, entry in value['documents'].items():
            request = urllib.request.Request(entry['source_uri'], headers={'User-Agent': 'FineAtlas-independent-source-verification/1.0'})
            with opener.open(request, timeout=60) as response:
                data = response.read()
                mime = response.headers.get_content_type()
                row = {'source_uri': entry['source_uri'], 'final_uri': response.geturl(),
                       'filename': entry['filename'], 'http_status': response.status,
                       'mime_type': mime, 'byte_count': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                       'retrieved_from_network': True, 'retrieved_utc': datetime.now(timezone.utc).isoformat()}
            (directory / entry['filename']).write_bytes(data)
            receipt['documents'][key] = row
            if row['http_status'] != 200 or mime != entry['mime_type'] or row['sha256'] != entry['sha256']:
                raise ValueError('Official retrieved bytes or MIME differ from sealed snapshot: ' + key)
        receipt['pass'] = True; receipt['complete'] = True
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, indent=2) + '\n')
        return require_fresh_retrieval(output, inputs, directory)
    except Exception as error:
        receipt['pass'] = False; receipt['complete'] = False
        receipt['errors'].append({'type': type(error).__name__, 'reason': str(error)})
        output.parent.mkdir(parents=True, exist_ok=True)
        output.with_suffix('.failed.json').write_text(json.dumps(receipt, indent=2) + '\n')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--snapshots-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError('Source retrieval verification cannot run optimized')
    retrieve(args.inputs, args.snapshots_dir, args.output)
