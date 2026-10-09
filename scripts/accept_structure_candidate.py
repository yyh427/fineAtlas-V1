#!/usr/bin/env python3
"""Run bound independent structural acceptance, then attach public verification.

Local completion permits packaging a prerelease. Full acceptance additionally
requires an actual matching public-download/installed-SDK proof. A failed job
cannot be dropped from the receipt or converted into a warning.
"""
from __future__ import annotations

if not __debug__:
    raise RuntimeError("Optimized Python is forbidden for mandatory structural checks")

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_structure_candidate import build_fingerprints
from structure_acceptance_contract import (REQUIRED_JOBS, validate_completed_acceptance,
    validate_independent_builds, validate_comparison_inventory, validate_public_evidence, file_sha256)


def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def stamp(path):
    value=path.stat();return [value.st_size,value.st_mtime_ns,value.st_ino]
def read(path):return json.loads(path.read_text())


def run_local(a):
    a.output.mkdir(parents=True,exist_ok=True)
    fingerprints=build_fingerprints(a.inputs)
    builds=validate_independent_builds(a.database,a.reproduction,a.primary_build,a.reproduction_build,fingerprints)
    before={name:stamp(path) for name,path in [('primary',a.database),('reproduction',a.reproduction)]}
    receipt={'schema':'FINEATLAS_STRUCTURE_ACCEPTANCE_V1','complete':False,'all_pass':False,
             'started_utc':utc(),'jobs':{},'fingerprints':fingerprints,'artifact_stamps':before,
             'artifacts':{'primary':str(a.database),'reproduction':str(a.reproduction)},'independent_builds':builds}
    path=a.output/'acceptance_receipt.json';write(path,receipt)
    temp=a.output/'tmp';temp.mkdir(exist_ok=True)
    env={**os.environ,'TMPDIR':str(temp),'SQLITE_TMPDIR':str(temp),
         'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT/'src')}
    env.pop('PYTHONOPTIMIZE',None)
    env['PYTHONPYCACHEPREFIX']=str(temp/('pycache-'+uuid.uuid4().hex))
    def command(script,*args):return [sys.executable,'-B',str(ROOT/'scripts'/script),*map(str,args)]
    jobs={
      'integrity':[command('audit_structure_artifact.py','--database',db,'--inputs',a.inputs,
                         '--output',a.output/(name+'-integrity.json'),'--integrity')
                   for name,db in [('primary',a.database),('reproduction',a.reproduction)]],
      'source-preservation':[command('audit_structure_preservation.py','--baseline',a.baseline,'--candidate',a.database,
                         '--reference',a.reference,'--output',a.output/'source-preservation.json')],
      'logical-reproduction':[command('compare_reproductions.py','--database',a.database,'--reproduction',a.reproduction,
                         '--output',a.output/'logical-comparison.json')],
      'whole-library':[command('audit_structure_library.py','--baseline',a.baseline,'--database',a.database,
                         '--inventory',a.inventory,'--output',a.output/'whole-library')],
      'contracts':[command('audit_contracts.py','--baseline',a.baseline,'--database',a.database,'--output',a.output/'contracts')],
      'cycles':[command('audit_browse_cycles.py','--staging',a.database,'--output',a.output/'cycles.json')],
      'witnesses':[command('audit_browse_witnesses.py','--baseline',a.database,'--staging',a.database,'--output',a.output/'witnesses.json')],
      'public-cli':[command('audit_browse_cli.py','--database',a.database,'--output',a.output/'public-cli')],
      'full-six-matrix':[command('audit_structure_rewards.py','--database',a.database,'--inputs',a.inputs,'--output',a.output/'matrix')],
      'living':[command('audit_living_candidate.py','--database',a.database,'--inputs',a.inputs,'--output',a.output/'living')],
      'source-contracts':[command('audit_source_contract_candidate.py','--database',a.database,'--inputs',a.inputs,'--output',a.output/'source-contracts')],
      'source-freeze':[command('audit_structure_artifact.py','--database',db,'--inputs',a.inputs,
                         '--output',a.output/(name+'-freeze.json'))
                     for name,db in [('primary',a.database),('reproduction',a.reproduction)]],
    }
    def execute(name,commands):
        print('START ACCEPTANCE',name,flush=True);start=time.monotonic()
        result={'started_utc':utc(),'commands':commands,'pass':False,'exit_code':None}
        with (a.output/(name+'.log')).open('w') as log:
            for argv in commands:
                code=subprocess.run(argv,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
                if code:break
        result.update(exit_code=code,**{'pass':code==0},ended_utc=utc(),seconds=time.monotonic()-start)
        print('END ACCEPTANCE',name,code,round(result['seconds'],2),flush=True)
        return result
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures={pool.submit(execute,name,commands):name for name,commands in jobs.items()}
        for future in as_completed(futures):
            name=futures[future]
            try:receipt['jobs'][name]=future.result()
            except Exception as error:receipt['jobs'][name]={'pass':False,'exit_code':-1,'error':str(error),'ended_utc':utc()}
            write(path,receipt)
    if receipt['jobs']['full-six-matrix']['pass']:
        receipt['jobs']['exports']=execute('exports',[command('audit_structure_exports.py','--database',a.database,
                      '--inputs',a.inputs,'--matrix',a.output/'matrix','--output',a.output/'exports')])
    else:
        receipt['jobs']['exports']={'pass':False,'exit_code':-1,'error':'Independent matrix failed','ended_utc':utc()}
    receipt['jobs']['public-install']={'pass':False,'exit_code':None,'status':'PENDING_REAL_PUBLIC_DOWNLOAD'}
    receipt['candidate_unchanged']=before=={name:stamp(db) for name,db in [('primary',a.database),('reproduction',a.reproduction)]}
    after=build_fingerprints(a.inputs)
    receipt['inputs_unchanged']=fingerprints['inputs']==after['inputs']
    receipt['code_unchanged']=fingerprints['code']==after['code'] and fingerprints['packaging']==after['packaging']
    local=all(row.get('pass') and row.get('exit_code')==0 for name,row in receipt['jobs'].items() if name!='public-install')
    receipt['local_all_pass']=bool(local and receipt['candidate_unchanged'] and receipt['inputs_unchanged'] and receipt['code_unchanged'])
    if receipt['local_all_pass']:
        artifacts={name:read(a.output/(name+'-integrity.json')) for name in ('primary','reproduction')}
        comparison=read(a.output/'logical-comparison.json')
        assert all(row['pass'] for row in comparison.values())
        schema=comparison['schema_inventory'];objects=comparison['schema_objects']
        complete={'complete':True,'pass':True,'exit_code':0,'schema_inventory_pass':schema['pass'],
                  'schema_objects_pass':objects['pass'],'final_view_statistics_pass':comparison['view_statistics_without_runtime']['pass'],
                  'all_logical_tables_pass':True,'logical_table_count':schema['table_counts'][0],
                  'artifacts':artifacts,
                  'compared_content_tables':comparison['content_inventory']['compared_content_tables'],
                  'excluded_content_tables':comparison['content_inventory']['excluded_content_tables'],
                  'independent_builds':builds,'comparison_report':str(a.output/'logical-comparison.json'),
                  'comparison_report_sha256':file_sha256(a.output/'logical-comparison.json'),'ended_utc':utc()}
        validate_comparison_inventory(complete)
        write(a.output/'comparison_complete.json',complete)
        receipt['database_sha256']=artifacts['primary']['sha256']
        receipt['database_revision']=artifacts['primary']['database_revision']
        receipt['release']=artifacts['primary']['release']
        matrix=read(a.output/'matrix/summary.json')
        receipt['matrix_expected_counts']={name:{dataset:row['counts'] for dataset,row in mode['datasets'].items()} for name,mode in matrix.items()}
        receipt['local_matrix_report_sha256']=file_sha256(a.output/'matrix/summary.json')
        write(a.output/'local_validation_complete.json',{'pass':True,'complete':True,
            'release':receipt['release'],'database_sha256':receipt['database_sha256'],
            'database_revision':receipt['database_revision'],'public_install_pending':True,'ended_utc':utc()})
    receipt['local_ended_utc']=utc();write(path,receipt)
    if not receipt['local_all_pass']:raise SystemExit('Local structural acceptance failed; inspect complete receipt')


def finalize(a):
    path=a.output/'acceptance_receipt.json';receipt=read(path);public=read(a.public_verification)
    if not receipt.get('local_all_pass'):raise ValueError('Local acceptance has not passed')
    public_sha=validate_public_evidence(public,receipt,a.public_verification)
    if any(stamp(Path(db))!=receipt['artifact_stamps'][name] for name,db in receipt['artifacts'].items()):
        raise ValueError('Accepted primary or reproduction changed')
    if build_fingerprints(a.inputs)!=receipt['fingerprints']:
        raise ValueError('Accepted source code or frozen inputs changed')
    receipt['jobs']['public-install']={'pass':True,'exit_code':0,'ended_utc':public['ended_utc'],
                    'verification_file':str(a.public_verification),'verification_file_sha256':public_sha,
                    'database_revision':public['database_revision'],'release':public['release'],
                    'database_sha256':public['database_sha256']}
    receipt.update(complete=True,all_pass=True,ended_utc=utc())
    validate_completed_acceptance(receipt);write(path,receipt)
    print('FULL STRUCTURAL ACCEPTANCE INCLUDING PUBLIC DOWNLOAD PASS',receipt['release'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    local=sub.add_parser('local')
    for name in ('database','reproduction','baseline','inputs','inventory','reference','output','primary-build','reproduction-build'):local.add_argument('--'+name,type=Path,required=True)
    local.add_argument('--workers',type=int,default=3)
    final=sub.add_parser('finalize')
    for name in ('inputs','output','public-verification'):final.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    for key,value in vars(args).items():
        if isinstance(value,Path):setattr(args,key,value.resolve())
    if args.action=='local':run_local(args)
    else:finalize(args)
