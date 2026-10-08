#!/usr/bin/env python3
"""Freeze current primary Wikidata identifier claims for source-wide candidates.

Candidate discovery is NOT identity proof. Admission happens in a separate
adapter using the AviList/Cornell/BirdLife declared concept identifiers.
Existing source and FineAtlas files are read-only. Completed batches are reused.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import requests


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--ids-file',type=Path,help='Frozen source-wide identifier list for another hierarchy cohort')
    p.add_argument('--reuse-directory',type=Path,help='Reuse already frozen primary entity snapshots, retaining provenance')
    p.add_argument('--include-aliases',action='store_true',help='Freeze complete native aliases for a concept-scope check')
    p.add_argument('--maxlag',type=int,default=5,help='MediaWiki replica-lag tolerance; errors remain recorded and resumable')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(a.database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    qids=set()
    if a.ids_file:
        qids=set(json.loads(a.ids_file.read_text()))
        if not all(re.fullmatch(r'Q[0-9]+',q) for q in qids):raise ValueError('Invalid source identifier list')
    else:
        for left,right in c.execute("SELECT left_uid,right_uid FROM bridges WHERE left_uid GLOB 'avilist:*' OR right_uid GLOB 'avilist:*'"):
            for uid in (left,right):
                if re.fullmatch(r'wikidata:Q[0-9]+',uid):qids.add(uid.split(':')[1])
    c.close()
    ids=sorted(qids,key=lambda x:int(x[1:])); batches=[ids[i:i+50] for i in range(0,len(ids),50)]
    (a.output/'requested_ids.json').write_text(json.dumps(ids)+'\n')
    print('SOURCE-WIDE CANDIDATES',len(ids),'BATCHES',len(batches),flush=True)
    reused={};origins={}
    if a.reuse_directory and not a.include_aliases:
        for path in sorted(a.reuse_directory.glob('batch-*.json')):
            raw=path.read_bytes();origin={'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()}
            for qid,entity in json.loads(raw).get('entities',{}).items():
                if qid in qids:reused[qid]=entity;origins[qid]=origin
    def fetch(pair):
        i,batch=pair;f=a.output/f'batch-{i:04d}.json'
        if f.exists():
            j=json.loads(f.read_text())
            if set(batch)<=j.get('entities',{}).keys():return i,'REUSED',hashlib.sha256(f.read_bytes()).hexdigest()
        pending=[qid for qid in batch if qid not in reused]
        if not pending:
            j={'entities':{qid:reused[qid] for qid in batch},'_fineatlas_reused_from':{qid:origins[qid] for qid in batch}}
            f.write_text(json.dumps(j,ensure_ascii=False)+'\n')
            return i,'REUSED_PRIMARY',hashlib.sha256(f.read_bytes()).hexdigest()
        params={'action':'wbgetentities','ids':'|'.join(pending),'props':'claims|labels|descriptions|info'+('|aliases' if a.include_aliases else ''),
                'languages':'en','format':'json','maxlag':a.maxlag}
        error=None
        for attempt in range(4):
            try:
                r=requests.get('https://www.wikidata.org/w/api.php',params=params,
                  headers={'User-Agent':'FineAtlas-Unified-Audit/1.0 (https://github.com/yyh427/fineAtlas-V1)'},timeout=60)
                r.raise_for_status();j=r.json()
                if 'error' in j or not set(pending)<=j.get('entities',{}).keys():raise ValueError(str(j.get('error','Incomplete response')))
                for qid in batch:
                    if qid in reused:j['entities'][qid]=reused[qid]
                j['_fineatlas_reused_from']={qid:origins[qid] for qid in batch if qid in reused}
                f.write_text(json.dumps(j,ensure_ascii=False)+'\n')
                return i,'FROZEN',hashlib.sha256(f.read_bytes()).hexdigest()
            except Exception as exc:
                error=type(exc).__name__+': '+str(exc);time.sleep(min(2**attempt,8))
        return i,'ERROR',error
    results=[]
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(fetch,x) for x in enumerate(batches)]
        for job in as_completed(jobs):
            result=job.result();results.append(result)
            print(*result[:2],len(results),'/',len(batches),flush=True)
            (a.output/'fetch_checkpoint.json').write_text(json.dumps(sorted(results),indent=2)+'\n')
    (a.output/'manifest.json').write_text(json.dumps({'source':'Wikidata identifier claim snapshots','endpoint':'https://www.wikidata.org/w/api.php',
        'license':'CC0','requested':len(ids),'batches':sorted(results),'finished_unix':time.time(),
        'missing_is_not_identity_disproof':True},indent=2)+'\n')
    if any(r[1]=='ERROR' for r in results):
        raise SystemExit('Incomplete source freeze; retry the same command to reuse successful batches')

if __name__=='__main__':main()
