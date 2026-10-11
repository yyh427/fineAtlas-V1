#!/usr/bin/env python3
"""Execute only an approved, exact final-child or fresh-public external plan."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from external_audit_supplement_binding import require_supplement
REQUIRED_STAGES=('verify_complete_owned_type_parent_copy','nominal_design_scope_repairs','whole_graph_recomputation','freeze_metadata','browse_staging','embed_browse_indexes')

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def metadata(database):
    database=Path(database).resolve()
    assert not any(Path(str(database)+s).exists()for s in('-wal','-shm','-journal'))
    with sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)as c:
        c.execute('PRAGMA query_only=ON')
        return {key:json.loads(value)for key,value in c.execute('SELECT key,value FROM metadata')}

def authorize(plan,phase):
    assert plan.get('execution_authorized')is True,'Await actual approved final source/code/inputs/SDK/recipe contract'
    assert plan.get('status')=='READY_ACTUAL_NOMINAL_FINAL_CHILD','Intermediate or pending SOURCE review is not final acceptance'
    assert tuple(plan['required_stages'])==REQUIRED_STAGES
    assert plan.get('final_code_commit')and plan.get('final_source_seal_sha256')and plan.get('frozen_inputs_manifest_sha256')
    assert plan.get('actual_final_revision')and isinstance(plan.get('actual_final_fingerprints'),dict)
    assert set(plan['actual_final_fingerprints'])=={'inputs','code','packaging'}
    script=HERE/'independent_nominal_design_scope_final_interface_audit.py'
    assert digest(script)==plan['auditor_sha256'],'External acceptance source changed after approved plan'
    conf=plan['execution'][phase]
    assert conf['installed_sdk']is(phase=='fresh-public')
    assert isinstance(conf['command'],list)and conf['command'][1]=='-B'and conf['command'][2]==str(script)
    assert '--require-final-child'in conf['command']
    assert ('--installed-sdk'in conf['command'])is conf['installed_sdk']
    return conf

def physical_prerequisite(plan,conf):
    children=[Path(p).resolve()for p in conf['build_receipts']]
    records=[json.loads(p.read_text())for p in children]
    assert len(children)==2 and all(r['complete']is True and r['pass']is True for r in records)
    assert records[0]['revision']==records[1]['revision']==plan['actual_final_revision'] and records[0]['build_id']!=records[1]['build_id']
    parent_sources=[];child_sources=[];evidence=[]
    for index,(p,r)in enumerate(zip(children,records)):
        assert tuple(r['required_stages'])==REQUIRED_STAGES,'Completed eight-stage intermediate cannot impersonate finer final child'
        assert digest(p.parent/'build_status.json')==r['build_status_sha256']
        states=json.loads((p.parent/'build_status.json').read_text());assert set(states)==set(REQUIRED_STAGES)and all(s['status']=='PASS'for s in states.values())
        lineage_path=p.parent/'parent_lineage.json';assert digest(lineage_path)==r['parent_lineage_sha256'];lineage=json.loads(lineage_path.read_text())
        parent_path=Path(conf['parent_receipts'][index]).resolve();assert digest(parent_path)==lineage['parent_receipt_sha256'];parent=json.loads(parent_path.read_text())
        integrity_path=Path(conf['parent_integrity_receipts'][index]).resolve();assert digest(integrity_path)==lineage['parent_integrity_sha256'];seal=json.loads(integrity_path.read_text())
        assert all(seal[k]is True for k in('complete','pass','integrity_pass','file_unchanged_during_checks','all_frozen_inputs_and_recipes_checked'))and seal['integrity_check']==['ok']
        source=Path(parent['database']).resolve();database=Path(r['database']).resolve();source_stat=source.stat()
        assert seal['sha256']==lineage['parent_database_sha256']and seal['bytes']==source_stat.st_size
        assert parent['build_id']==lineage['parent_build_id']and parent['revision']==lineage['parent_revision']==seal['database_revision']
        assert Path(lineage['parent_database']).resolve()==source==Path(seal['database']).resolve()
        copy=states[REQUIRED_STAGES[0]]['result']
        for key in('parent_database_sha256','parent_integrity_sha256','parent_receipt_sha256','parent_build_id','parent_revision'):assert copy[key]==lineage[key]
        import datetime
        verified_end=datetime.datetime.fromisoformat(states[REQUIRED_STAGES[0]]['started_utc']).timestamp()+states[REQUIRED_STAGES[0]]['seconds']
        assert source_stat.st_mtime<=verified_end,'Parent modified after actual whole-copy validation'
        for path,receipt,db in((parent_path,parent,source),(p,r,database)):
            meta=metadata(db);freeze=json.loads((path.parent/'frozen_metadata.json').read_text());fingerprints=json.loads((path.parent/'started_fingerprints.json').read_text())
            assert digest(path.parent/'started_fingerprints.json')==receipt['started_fingerprints_sha256']
            assert meta['database_revision']==meta['browse_index_revision']==receipt['revision']
            assert meta['browse_parent_revision']==freeze['revision']==receipt['source_graph_revision']
            assert receipt['cache_bindings']=={'browse_parent_revision':freeze['revision'],'browse_source_revision':freeze['revision'],'browse_index_revision':receipt['revision']}
            assert meta['structure_frozen_build_manifest']==freeze['manifest']
            for section in('code','inputs','packaging'):assert fingerprints[section]==freeze['manifest'][section]
            if path==p:
                assert fingerprints==plan['actual_final_fingerprints'],'Actual final source/input/packaging freeze differs from approved external plan'
        parent_sources.append((source.stat().st_dev,source.stat().st_ino));child_sources.append((database.stat().st_dev,database.stat().st_ino))
        evidence.append({'actual_parent_revision':parent['revision'],'actual_parent_database_sha256':seal['sha256'],'actual_parent_integrity_sha256':digest(integrity_path),'child_revision':r['revision'],'child_receipt_sha256':digest(p),'verified_whole_copy_seconds':states[REQUIRED_STAGES[0]]['seconds'],'actual_parent_frozen_manifest':metadata(source)['structure_frozen_build_manifest'],'physical_parent_inode':parent_sources[-1],'physical_child_inode':child_sources[-1]})
    assert len(set(parent_sources+child_sources))==4,'Independent complete parent and final children must have four distinct physical files'
    assert records[0]['parent_source_inode']!=records[1]['parent_source_inode']
    assert evidence[0]['actual_parent_revision']==evidence[1]['actual_parent_revision']
    return {'pass':True,'phase':'actual-local-final','records':evidence,'basis':'Actual independent parent integrity whole-SHA plus child verified whole-byte copy, distinct build IDs/inodes and independently read complete frozen metadata; no redundant parent fullfile hashing','semantic_build_functions_called':False}

def fresh_public_database_prerequisite(plan,conf,database):
    download=json.loads(Path(conf['public_download_receipt']).read_text());database=Path(database).resolve();stat=database.stat()
    assert download['schema']=='FINEATLAS_PUBLIC_DOWNLOAD_PROOF_V1'
    assert download['fresh_download']is True and download['authenticated']is False
    assert download['asset_proofs']and all(row.get('fresh_download')is True and row.get('network_request')is True for row in download['asset_proofs'])
    assert download['database_revision']==plan['actual_final_revision']
    assert download['database_sha256']==plan['actual_final_database_sha256']
    assert Path(download['database']).resolve()==database and download['database_bytes']==stat.st_size
    assert download['artifact_stamp']==[stat.st_size,stat.st_mtime_ns,stat.st_ino]
    return download

def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--phase',choices=('local','fresh-public'),required=True);a=p.parse_args()
    assert __debug__,'External audit requires unoptimized Python'
    plan=json.loads(a.plan.read_text());supplement_proof=require_supplement(plan,a.phase,HERE);conf=authorize(plan,a.phase)
    command_database=Path(conf['command'][conf['command'].index('--database')+1]);actual=metadata(command_database)
    assert actual['database_revision']==plan['actual_final_revision'],'Execution database differs from approved final revision'
    assert {group:actual['structure_frozen_build_manifest'][group]for group in ('inputs','code','packaging')}==plan['actual_final_fingerprints'],'Execution freeze differs from approved final snapshot'
    output=Path(conf['output']).resolve();output.mkdir(parents=True,exist_ok=True)
    if a.phase=='local':
        proof=physical_prerequisite(plan,conf);proof['plan_sha256']=digest(a.plan)
        (output/'ACTUAL_FINAL_CHILD_PARENT_INDEPENDENCE_AND_SOURCE_FREEZE.json').write_text(json.dumps(proof,indent=2)+'\n')
    else:
        # Public archive proves the historical build; it does not claim freshly inspected historical inodes.
        assert conf.get('public_download_receipt')and conf.get('public_source_retrieval_receipt')and conf.get('runtime_support_registry')
        for key in('public_download_receipt','public_source_retrieval_receipt','runtime_support_registry'):
            assert digest(conf[key])==conf[key+'_sha256'],'Actual fresh public artifact receipt changed'
        fresh_public_database_prerequisite(plan,conf,command_database)
    supplement_output=Path(conf['output']);supplement_output.mkdir(parents=True,exist_ok=True)
    supplement_proof['plan_sha256']=digest(a.plan)
    supplement_proof['runner_sha256']=digest(__file__)
    (supplement_output/'ACTUAL_EXTERNAL_AUDIT_SUPPLEMENT_SOURCE_BINDING.json').write_text(json.dumps(supplement_proof,indent=2)+'\n')
    environment=dict(os.environ);environment.pop('PYTHONOPTIMIZE',None);environment['PYTHONDONTWRITEBYTECODE']='1'
    if conf['installed_sdk']:environment.pop('PYTHONPATH',None)
    else:environment['PYTHONPATH']=str(Path(plan['code_root'])/'src')
    subprocess.run(conf['command'],env=environment,check=True)

if __name__=='__main__':main()
