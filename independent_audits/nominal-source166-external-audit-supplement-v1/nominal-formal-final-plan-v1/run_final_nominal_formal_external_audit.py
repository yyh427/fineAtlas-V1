#!/usr/bin/env python3
"""Authorize actual four-stage formal artifacts and run the full external audit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from independent_nominal_formal_binding import FORMAL_STAGES, metadata

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from external_audit_supplement_binding import require_supplement
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def authorize(plan,phase):
    assert plan.get('execution_authorized')is True
    assert plan['status']=='READY_ACTUAL_FORMAL_VERSION_ONLY_FOUR_STAGE'
    assert tuple(plan['required_stages'])==FORMAL_STAGES
    for key in('final_code_commit','final_source_seal_sha256','frozen_inputs_manifest_sha256','actual_final_revision','actual_final_database_sha256','semantic_source9_revision'):
        assert plan.get(key)
    assert set(plan['actual_final_fingerprints'])=={'inputs','code','packaging'}
    for name,value in plan['external_implementation_sha256'].items():
        assert Path(name).name==name and digest(HERE/name)==value
    script=HERE/'independent_nominal_formal_final_interface_audit.py'
    assert script.name in plan['external_implementation_sha256']and 'independent_nominal_formal_binding.py'in plan['external_implementation_sha256']
    conf=plan['execution'][phase];command=conf['command']
    assert conf['installed_sdk']is(phase=='fresh-public')
    assert command[1]=='-B'and command[2]==str(script)and '--require-final-child'in command
    assert ('--installed-sdk'in command)is conf['installed_sdk']
    if phase=='local':assert '--formal-delivery-config'in command
    else:assert '--support-registry'in command
    return conf

def fresh_public_prerequisite(plan,conf,database):
    for key in('public_download_receipt','public_source_retrieval_receipt','runtime_support_registry'):
        assert digest(conf[key])==conf[key+'_sha256']
    download=json.loads(Path(conf['public_download_receipt']).read_text());stat=database.stat()
    assert download['schema']=='FINEATLAS_PUBLIC_DOWNLOAD_PROOF_V1'
    assert download['fresh_download']is True and download['authenticated']is False
    assert download['asset_proofs']and all(row.get('fresh_download')is True and row.get('network_request')is True for row in download['asset_proofs'])
    assert download['database_revision']==plan['actual_final_revision']and download['database_sha256']==plan['actual_final_database_sha256']
    assert Path(download['database']).resolve()==database and download['database_bytes']==stat.st_size
    assert download['artifact_stamp']==[stat.st_size,stat.st_mtime_ns,stat.st_ino]

def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--phase',choices=('local','fresh-public'),required=True);a=p.parse_args()
    assert __debug__;plan=json.loads(a.plan.read_text());supplement_proof=require_supplement(plan,a.phase,HERE);conf=authorize(plan,a.phase)
    command=conf['command'];database=Path(command[command.index('--database')+1]).resolve();meta=metadata(database)
    assert meta['database_revision']==plan['actual_final_revision']
    assert {group:meta['structure_frozen_build_manifest'][group]for group in('inputs','code','packaging')}==plan['actual_final_fingerprints']
    assert meta['structure_frozen_build_manifest']['promotion']['parent_candidate_revision']==plan['semantic_source9_revision']
    if a.phase=='fresh-public':fresh_public_prerequisite(plan,conf,database)
    supplement_output=Path(conf['output']);supplement_output.mkdir(parents=True,exist_ok=True)
    supplement_proof['plan_sha256']=digest(a.plan)
    supplement_proof['runner_sha256']=digest(__file__)
    (supplement_output/'ACTUAL_EXTERNAL_AUDIT_SUPPLEMENT_SOURCE_BINDING.json').write_text(json.dumps(supplement_proof,indent=2)+'\n')
    environment=dict(os.environ);environment.pop('PYTHONOPTIMIZE',None);environment['PYTHONDONTWRITEBYTECODE']='1'
    if conf['installed_sdk']:environment.pop('PYTHONPATH',None)
    else:environment['PYTHONPATH']=str(Path(plan['code_root'])/'src')
    subprocess.run(command,env=environment,check=True)

if __name__=='__main__':main()
