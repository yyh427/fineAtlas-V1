#!/usr/bin/env python3
"""Build a new 1.10 review candidate from its verified frozen source baseline.

Refuses to overwrite a database. No network, publication, or source preparation
occurs here; every source decision is replayed from the supplied frozen inputs.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]

def digest_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(16*1024*1024),b''):h.update(block)
    return h.hexdigest()

def validate_paths(baseline,database,staging):
    if database.exists() or staging.exists():
        raise ValueError('Refusing to overwrite an existing candidate or browse staging')
    if baseline.resolve() in {database.resolve(),staging.resolve()} or database.resolve()==staging.resolve():
        raise ValueError('Source, candidate and staging must be separate files')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline','inputs','database','reports','browse-staging'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    # Subprocesses run from the checked-out code, so freeze caller-relative
    # paths before changing their working directory.
    for name in ('baseline','inputs','database','reports','browse_staging'):
        setattr(a,name,getattr(a,name).resolve())
    validate_paths(a.baseline,a.database,a.browse_staging)
    a.reports.mkdir(parents=True,exist_ok=True);a.database.parent.mkdir(parents=True,exist_ok=True)
    a.browse_staging.parent.mkdir(parents=True,exist_ok=True)
    temporary=a.database.parent/'tmp';temporary.mkdir(exist_ok=True)
    env={**os.environ,'PYTHONHASHSEED':'0','PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(temporary),'SQLITE_TMPDIR':str(temporary),'PYTHONPATH':str(ROOT/'src')}
    status={};started=time.monotonic()
    def stage(name,command=None,function=None):
        t=time.monotonic();row={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'RUNNING'}
        status[name]=row;(a.reports/'rebuild_status.json').write_text(json.dumps(status,indent=2)+'\n')
        print('START',name,flush=True)
        try:
            if function:result=function();row['result']=result
            else:
                row['command']=command
                with (a.reports/(name+'.log')).open('w') as log:
                    result=subprocess.run(command,env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=False)
                row['exit_code']=result.returncode
                if result.returncode:raise RuntimeError(name+' failed; see '+str(a.reports/(name+'.log')))
            row['status']='PASS'
        except Exception as error:
            row['status']='FAIL';row['error']=str(error);raise
        finally:
            row['seconds']=time.monotonic()-t;row['completed_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
            (a.reports/'rebuild_status.json').write_text(json.dumps(status,indent=2)+'\n')
        print('PASS',name,round(row['seconds'],3),flush=True)
    frozen=json.loads((a.inputs/'baseline.json').read_text());release=json.loads((a.inputs/'review_release.json').read_text())['version']
    if not release.startswith('v1.10.'):raise ValueError('This recipe builds only the explicit 1.10 candidate family')
    def verify_baseline():
        if a.baseline.stat().st_size!=frozen['database_bytes']:raise ValueError('Baseline size mismatch')
        with sqlite3.connect(a.baseline.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as c:
            value=json.loads(c.execute("SELECT value FROM metadata WHERE key='database_revision'").fetchone()[0])
        if value!=frozen['database_revision']:raise ValueError('Baseline revision mismatch')
        digest=digest_file(a.baseline)
        if digest!=frozen['database_sha256']:raise ValueError('Baseline SHA-256 mismatch')
        return {'sha256':digest,'bytes':a.baseline.stat().st_size,'revision':value}
    stage('baseline_verification',function=verify_baseline)
    stage('independent_baseline_copy',['cp','--reflink=auto','--sparse=always','--',str(a.baseline),str(a.database)])
    def verify_copy():
        value=digest_file(a.database)
        if value!=frozen['database_sha256']:raise ValueError('Copied baseline SHA-256 mismatch')
        if a.database.samefile(a.baseline):raise ValueError('Candidate is a hardlink to baseline')
        return {'sha256':value,'distinct_inode':True}
    stage('copy_verification',function=verify_copy)
    py=[sys.executable,'-B']
    stage('source_and_graphs',py+[str(ROOT/'scripts/build_unified_candidate.py'),'--baseline',str(a.baseline),'--database',str(a.database),'--inputs',str(a.inputs),'--reports',str(a.reports/'source-and-graphs')])
    metadata=a.reports/'frozen_metadata.json'
    stage('freeze_metadata',py+[str(ROOT/'scripts/finalize_unified_metadata.py'),'--database',str(a.database),'--inputs',str(a.inputs),'--output',str(metadata)])
    revision=json.loads(metadata.read_text())['revision']
    stage('browse_staging',py+[str(ROOT/'scripts/stage_browse_indexes.py'),'--source',str(a.database),'--output',str(a.browse_staging),'--reports',str(a.reports/'browse-build'),'--release',release])
    stage('embed_browse_indexes',py+[str(ROOT/'scripts/apply_browse_indexes.py'),'--database',str(a.database),'--staging',str(a.browse_staging),'--source-revision',revision,'--output',str(a.reports/'browse_application.json')])
    (a.reports/'rebuild_complete.json').write_text(json.dumps({'complete':True,'release':release,'database':str(a.database),'baseline_sha256':frozen['database_sha256'],'seconds':time.monotonic()-started,'requires_separate_full_acceptance':True},indent=2)+'\n')

if __name__=='__main__':main()
