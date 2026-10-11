"""Recheck portable historical build proof without claiming new physical copies."""
from __future__ import annotations
from pathlib import Path
import json

from _download import digest
from resume_structure_repairs import validate_resumed_parent_independence
from structure_literal_jet_delivery_guard import require_literal_jet_child_build

SCHEMA='FINEATLAS_PORTABLE_COMPLETED_BUILD_INDEPENDENCE_V1'


def package_lineage_members(config,output,accepted):
    primary=Path(config.get('lineage_primary_build',config['primary_build']))
    reproduction=Path(config.get('lineage_reproduction_build',config['reproduction_build']))
    actual=validate_resumed_parent_independence(primary,reproduction)
    members={};rows=[]
    for name,path in(('primary',primary),('reproduction',reproduction)):
        complete=require_literal_jet_child_build(path)
        lineage_path=path.parent/'parent_lineage.json';lineage=json.loads(lineage_path.read_text())
        integrity_path=Path(config[name+'_parent_integrity']);seal=json.loads(integrity_path.read_text())
        if (digest(integrity_path)!=lineage['parent_integrity_sha256']or seal.get('sha256')!=lineage['parent_database_sha256']
                or seal.get('database_revision')!=lineage['parent_revision']
                or Path(seal.get('database','')).resolve()!=Path(lineage['parent_database']).resolve()
                or any(seal.get(key)is not True for key in('pass','complete','integrity_pass',
                    'file_unchanged_during_checks','all_frozen_inputs_and_recipes_checked'))
                or seal.get('integrity_check')!=['ok']):
            raise ValueError('Actual complete parent byte/integrity seal differs from child lineage')
        local={}
        for filename,source in(('build_complete.json',path),('parent_lineage.json',lineage_path),
                              ('started_fingerprints.json',path.parent/'started_fingerprints.json'),
                              ('build_status.json',path.parent/'build_status.json'),('parent_integrity.json',integrity_path)):
            member='builds/'+name+'/'+filename;members[member]=source
            local[filename]={'member':member,'sha256':digest(source)}
        rows.append({'name':name,'files':local})
    proof={'schema':SCHEMA,'pass':True,'candidate_revision':accepted['database_revision'],
        'candidate_sha256':accepted['database_sha256'],'actual_local_physical_parent_audit':actual,
        'current_host_actual_inodes_checked':True,'original_lineage_validator_sha256':digest(Path(__file__).with_name('resume_structure_repairs.py')),
        'children':rows,'scope':'Historical actual complete independent parent builds; clean public verification checks immutable evidence bytes, not new physical parent copies'}
    path=Path(output)/'build-independence.json';path.write_text(json.dumps(proof,indent=2)+'\n')
    members['builds/build-independence.json']=path
    return members


def validate_portable_parent_independence(support,primary,reproduction,accepted):
    value=json.loads((support.root/'builds/build-independence.json').read_text())
    if (value.get('schema')!=SCHEMA or value.get('pass')is not True
            or value.get('candidate_revision')!=accepted['database_revision']
            or value.get('candidate_sha256')!=accepted['database_sha256']
            or value.get('current_host_actual_inodes_checked')is not True
            or value.get('original_lineage_validator_sha256')!=digest(Path(__file__).with_name('resume_structure_repairs.py'))
            or value.get('actual_local_physical_parent_audit',{}).get('pass')is not True):
        raise ValueError('Complete immutable actual historical parent audit required')
    records=[]
    for name,path in(('primary',Path(primary)),('reproduction',Path(reproduction))):
        if path.resolve()!=support.root/'builds'/name/'build_complete.json':
            raise ValueError('Public build proof must come from the fresh portable support')
        rows=[row for row in value['children']if row['name']==name]
        if len(rows)!=1:raise ValueError('Missing or duplicate portable independent child')
        for filename,row in rows[0]['files'].items():
            file=support.root/'builds'/name/filename
            if row['member']!=str(file.relative_to(support.root))or digest(file)!=row['sha256']:
                raise ValueError('Actual historical build proof changed')
        child=require_literal_jet_child_build(path)
        lineage=json.loads(path.with_name('parent_lineage.json').read_text())
        seal=json.loads(path.with_name('parent_integrity.json').read_text())
        if (child.get('parent_lineage_sha256')!=digest(path.with_name('parent_lineage.json'))
                or lineage.get('resumed_build_id')!=child['build_id']or lineage.get('resumed_revision')!=child['revision']
                or lineage.get('parent_build_id')!=child.get('parent_build_id')
                or lineage.get('parent_source_inode')!=child.get('parent_source_inode')
                or seal.get('sha256')!=lineage['parent_database_sha256']
                or digest(path.with_name('parent_integrity.json'))!=lineage['parent_integrity_sha256']
                or seal.get('database_revision')!=lineage['parent_revision']
                or any(seal.get(key)is not True for key in('pass','complete','integrity_pass',
                    'file_unchanged_during_checks','all_frozen_inputs_and_recipes_checked'))
                or seal.get('integrity_check')!=['ok']):
            raise ValueError('Historical independent build and full parent integrity proof disagree')
        records.append((child,lineage))
    one,two=records;actual=value['actual_local_physical_parent_audit']
    if (one[0]['build_id']==two[0]['build_id']or one[1]['parent_build_id']==two[1]['parent_build_id']
            or one[1]['parent_source_inode']==two[1]['parent_source_inode']
            or one[1]['parent_revision']!=two[1]['parent_revision']
            or one[0]['revision']!=two[0]['revision']
            or actual.get('parent_build_ids')!=[r[1]['parent_build_id']for r in records]
            or actual.get('resumed_build_ids')!=[r[0]['build_id']for r in records]
            or actual.get('distinct_source_inodes')is not True or actual.get('parent_revision')!=one[1]['parent_revision']):
        raise ValueError('Distinct independently completed historical parents are required')
    return {'schema':'FINEATLAS_PUBLIC_HISTORICAL_BUILD_PROOF_VERIFICATION_V1','pass':True,
        'historical_actual_parent_audit':actual,'source_proof_sha256':digest(support.root/'builds/build-independence.json'),
        'physical_parent_inodes_rechecked_here':False,'immutable_historical_lineage_bytes_checked':True}
