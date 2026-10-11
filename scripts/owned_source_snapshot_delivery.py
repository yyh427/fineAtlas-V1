"""Retrieve only seventh-delta documents after preserving the verified eight."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.request
from urllib.parse import urlparse

from primary_source_snapshot_delivery import digest, HttpsOfficialRedirect, REGISTRY_SCHEMA, require_fresh_retrieval

NAME='structure_owned_source_snapshots.json'
SCHEMA='FINEATLAS_FRESH_OWNED_SOURCE_RETRIEVAL_V1'


def entries(inputs):
    inputs=Path(inputs);registry=json.loads((inputs/NAME).read_text())
    first=json.loads((inputs/'structure_primary_source_snapshots.json').read_text())['documents']
    if registry.get('schema')!=REGISTRY_SCHEMA:raise ValueError('Invalid independently sealed owned source registry')
    files={doc['filename']:doc for doc in first.values()}
    old={(doc['source_uri'],doc['sha256'])for doc in first.values()}
    extra={}
    for key,doc in registry['documents'].items():
        filename=doc.get('filename','');uri=urlparse(doc.get('source_uri',''))
        if (not filename or Path(filename).name!=filename or '\\'in filename or filename in('.','..')
                or uri.scheme!='https' or not uri.hostname or uri.username or uri.password
                or not re.fullmatch('[a-f0-9]{64}',doc.get('sha256',''))
                or doc.get('hash_basis')!='HTTP_RESPONSE_BODY_BYTES' or not doc.get('mime_type')
                or not doc.get('revision_locator') or not doc.get('redistribution_authorization')):
            raise ValueError('Unsafe owned source registry entry')
        if filename in files and files[filename]!=doc:raise ValueError('New registry conflicts with a preserved official source filename')
        files[filename]=doc
        if (doc['source_uri'],doc['sha256'])not in old:extra[key]=doc
    return extra,first


def require_owned_retrieval(report,inputs,directory,primary_receipt):
    require_fresh_retrieval(primary_receipt,inputs,directory)
    expected,first=entries(inputs);value=json.loads(Path(report).read_text());directory=Path(directory).resolve()
    if (value.get('schema')!=SCHEMA or value.get('pass')is not True or value.get('complete')is not True
            or value.get('fresh_additional_official_https_retrieval')is not True
            or value.get('registry_sha256')!=digest(Path(inputs)/NAME)
            or value.get('preserved_primary_retrieval_sha256')!=digest(primary_receipt)
            or Path(value.get('snapshots_directory','')).resolve()!=directory
            or set(value.get('documents',{}))!=set(expected)or value.get('errors')!=[]):
        raise ValueError('Complete independent fresh seventh-source evidence required')
    for key,entry in expected.items():
        path=directory/entry['filename'];row=value['documents'][key];final=urlparse(row.get('final_uri',''))
        if (path.is_symlink()or not path.is_file()or digest(path)!=entry['sha256']
                or row.get('source_uri')!=entry['source_uri']or row.get('sha256')!=entry['sha256']
                or row.get('filename')!=entry['filename']or row.get('http_status')!=200
                or row.get('retrieved_from_network')is not True or not row.get('retrieved_utc')
                or row.get('mime_type')!=entry['mime_type']or row.get('byte_count')!=path.stat().st_size
                or final.scheme!='https'or final.hostname!=urlparse(entry['source_uri']).hostname):
            raise ValueError('Actual seventh official source bytes or retrieval facts changed')
    return value


def retrieve_owned(inputs,directory,output,primary_receipt):
    inputs,directory,output,primary_receipt=map(Path,(inputs,directory,output,primary_receipt))
    if output.exists():return require_owned_retrieval(output,inputs,directory,primary_receipt)
    require_fresh_retrieval(primary_receipt,inputs,directory)
    extra,first=entries(inputs)
    if output.with_suffix('.failed.json').exists():raise ValueError('Preserve previous owned source retrieval failure')
    if {path.name for path in directory.iterdir()}!={doc['filename']for doc in first.values()}:
        raise ValueError('Cannot reuse unreceipted additional source material')
    value={'schema':SCHEMA,'pass':False,'complete':False,'fresh_additional_official_https_retrieval':True,
        'registry_sha256':digest(inputs/NAME),'preserved_primary_retrieval_sha256':digest(primary_receipt),
        'snapshots_directory':str(directory.resolve()),'documents':{},'errors':[]}
    opener=urllib.request.build_opener(HttpsOfficialRedirect())
    try:
        for key,entry in extra.items():
            path=directory/entry['filename']
            if path.exists():raise ValueError('Additional retrieval must not overwrite an existing source')
            with opener.open(urllib.request.Request(entry['source_uri'],headers={'User-Agent':'FineAtlas-independent-source-verification/1.0'}),timeout=60)as response:
                raw=response.read();row={'source_uri':entry['source_uri'],'final_uri':response.geturl(),
                    'filename':entry['filename'],'http_status':response.status,'mime_type':response.headers.get_content_type(),
                    'sha256':hashlib.sha256(raw).hexdigest(),'byte_count':len(raw),'retrieved_from_network':True,
                    'retrieved_utc':datetime.now(timezone.utc).isoformat()}
            path.write_bytes(raw);value['documents'][key]=row
            if row['sha256']!=entry['sha256']or row['mime_type']!=entry['mime_type']or row['http_status']!=200:
                raise ValueError('Additional official response differs from sealed seventh source')
        value.update({'pass':True,'complete':True});output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(value,indent=2)+'\n')
        return require_owned_retrieval(output,inputs,directory,primary_receipt)
    except Exception as error:
        value.update({'pass':False,'complete':False});value['errors'].append({'type':type(error).__name__,'reason':str(error)})
        output.parent.mkdir(parents=True,exist_ok=True);output.with_suffix('.failed.json').write_text(json.dumps(value,indent=2)+'\n');raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('inputs','snapshots-dir','output','primary-receipt'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if not __debug__:raise RuntimeError('Owned retrieval cannot run optimized')
    retrieve_owned(args.inputs,args.snapshots_dir,args.output,args.primary_receipt)
