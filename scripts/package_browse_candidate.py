#!/usr/bin/env python3
"""Package a frozen candidate into checked release chunks; never publish automatically."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(8*1024*1024):h.update(block)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--release',default='v1.9.0-night-review');a=p.parse_args()
    with sqlite3.connect(a.database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as c:
        metadata={r[0]:json.loads(r[1]) for r in c.execute('SELECT key,value FROM metadata')}
        if not metadata.get('browse_indexes_ready') or metadata['release']!=a.release:
            raise ValueError('Candidate is not frozen under the requested release')
    a.output.mkdir(parents=True,exist_ok=True)
    compressed=a.output/('fineatlas-'+a.release+'.sqlite.zst')
    subprocess.run(['zstd','-T8','-8','-o',str(compressed),'--',str(a.database)],check=True)
    parts=[]
    with compressed.open('rb') as stream:
        for index in range(100):
            block=stream.read(8*1024*1024)
            if not block:break
            path=a.output/(compressed.name+f'.part-{index:03d}');h=hashlib.sha256();size=0
            with path.open('xb') as part:
                while block:
                    part.write(block);h.update(block);size+=len(block)
                    if size==1024**3:break
                    block=stream.read(min(8*1024*1024,1024**3-size))
            parts.append({'name':path.name,'bytes':size,'sha256':h.hexdigest()})
            print('PART',path.name,size,flush=True)
    process=subprocess.Popen(['zstd','-dc','--',str(compressed)],stdout=subprocess.PIPE)
    h=hashlib.sha256();size=0
    while block:=process.stdout.read(8*1024*1024):h.update(block);size+=len(block)
    if process.wait()!=0:raise RuntimeError('Decompression failed')
    expected=digest(a.database)
    if h.hexdigest()!=expected or size!=a.database.stat().st_size:raise ValueError('Compressed roundtrip differs from candidate')
    manifest={'public_name':'FineAtlas V1','release':a.release,'graph_version':'V1','candidate':True,
              'base_url':f'https://github.com/yyh427/fineAtlas-V1/releases/download/{a.release}',
              'database':{'name':'fineatlas.sqlite','bytes':size,'sha256':expected},'assets':parts,
              'database_build_version':a.release,'database_revision':metadata['database_revision']}
    (a.output/'review_data.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (a.output/'compression_verification.json').write_text(json.dumps({'pass':True,'database_bytes':size,
        'sha256':expected,'compressed_bytes':compressed.stat().st_size,'chunks':len(parts)},indent=2)+'\n')
    print('PACKAGE ROUNDTRIP AND SOURCE HASH VERIFIED',expected,flush=True)


if __name__=='__main__':main()
