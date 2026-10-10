"""Portable historical proof of the complete-type child and actual owned-scope parent."""
from __future__ import annotations
import json
import datetime
from pathlib import Path
import sqlite3

from _download import digest
from resume_structure_repairs import validate_resumed_parent_independence
from structure_literal_jet_delivery_guard import require_literal_jet_child_build

SCHEMA='FINEATLAS_PORTABLE_COMPLETED_TYPE_BUILD_INDEPENDENCE_V1'
STAGES=('verify_complete_owned_scope_parent_copy','complete_owned_type_repairs','whole_graph_recomputation','freeze_metadata','browse_staging','embed_browse_indexes')


def require_complete_type_build(receipt_path):
    path=Path(receipt_path);value=json.loads(path.read_text())
    if (value.get('schema')!='FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1' or value.get('pass')is not True
            or value.get('complete')is not True or not value.get('build_id')or not value.get('ended_utc')
            or value.get('required_stages')!=list(STAGES)):
        raise ValueError('Actual completed six-stage complete-type child required')
    for name in ('started_fingerprints','build_status','parent_lineage'):
        if digest(path.parent/(name+'.json'))!=value.get(name+'_sha256'):
            raise ValueError('Complete-type child receipt evidence changed: '+name)
    states=json.loads(path.with_name('build_status.json').read_text())
    if set(states)!=set(STAGES)or any(row.get('status')!='PASS'for row in states.values()):
        raise ValueError('Every actual complete-type build stage must have passed')
    lineage=json.loads(path.with_name('parent_lineage.json').read_text())
    if (lineage.get('schema')!='FINEATLAS_REPAIR_PARENT_LINEAGE_V1'
            or lineage.get('resumed_build_id')!=value['build_id']or lineage.get('resumed_revision')!=value['revision']
            or lineage.get('parent_build_id')!=value.get('parent_build_id')
            or lineage.get('parent_source_inode')!=value.get('parent_source_inode')):
        raise ValueError('Actual complete-type child lineage differs from its completed receipt')
    copy=states[STAGES[0]]['result']
    for key in ('parent_database_sha256','parent_integrity_sha256','parent_receipt_sha256','parent_build_id','parent_revision'):
        if copy.get(key)!=lineage.get(key):raise ValueError('Actual whole-parent-copy evidence changed: '+key)
    return value


def verify_seal(seal,lineage):
    if (any(seal.get(key)is not True for key in ('pass','complete','integrity_pass','file_unchanged_during_checks','all_frozen_inputs_and_recipes_checked'))
            or seal.get('integrity_check')!=['ok']or seal.get('sha256')!=lineage['parent_database_sha256']
            or seal.get('database_revision')!=lineage['parent_revision']
            or Path(seal.get('database','')).resolve()!=Path(lineage['parent_database']).resolve()):
        raise ValueError('Actual owned-scope parent whole-file integrity seal differs from child lineage')


def require_source_parent_binding(config,name,child_path,complete):
    lineage=json.loads(Path(child_path).with_name('parent_lineage.json').read_text())
    parent_path=Path(config[name+'_parent_build']);parent=require_literal_jet_child_build(parent_path)
    integrity_path=Path(config['complete_type_'+name+'_parent_integrity']);seal=json.loads(integrity_path.read_text())
    if (digest(parent_path)!=lineage['parent_receipt_sha256']or parent['revision']!=lineage['parent_revision']
            or parent['build_id']!=lineage['parent_build_id']
            or Path(parent['database']).resolve()!=Path(lineage['parent_database']).resolve()
            or digest(integrity_path)!=lineage['parent_integrity_sha256']):
        raise ValueError('The actual completed eight-stage source parent cannot be substituted with an older checkpoint')
    verify_seal(seal,lineage)
    database=Path(parent['database']).resolve()
    if any(Path(str(database)+s).exists()for s in ('-wal','-shm','-journal')):
        raise ValueError('Source parent must be closed')
    actual_stat=database.stat();lineage_path=Path(child_path).with_name('parent_lineage.json')
    if [actual_stat.st_dev,actual_stat.st_ino]!=complete['parent_source_inode']:
        raise ValueError('Actual owned-scope source inode changed after complete child byte-copy verification')
    state=json.loads(Path(child_path).with_name('build_status.json').read_text())[STAGES[0]]
    copy_end=datetime.datetime.fromisoformat(state['started_utc']).timestamp()+state['seconds']
    if actual_stat.st_mtime>copy_end:raise ValueError('Actual owned-scope source changed after verified complete whole-byte copy')
    if database.stat().st_size!=seal['bytes']:
        raise ValueError('Parent byte extent differs from its actual whole-file integrity receipt')
    with sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)as con:
        con.execute('PRAGMA query_only=ON');meta={key:json.loads(value)for key,value in con.execute('SELECT key,value FROM metadata')}
    frozen=json.loads(parent_path.with_name('frozen_metadata.json').read_text())
    fingerprints=json.loads(parent_path.with_name('started_fingerprints.json').read_text())
    if (meta.get('database_revision')!=parent['revision']or meta.get('browse_index_revision')!=parent['revision']
            or meta.get('browse_parent_revision')!=parent['source_graph_revision']or frozen['revision']!=parent['source_graph_revision']
            or meta.get('structure_frozen_build_manifest')!=frozen['manifest']
            or not meta.get('owned_scope_repairs')or meta.get('complete_owned_type_repairs')):
        raise ValueError('Actual c933 owned-scope parent SQL/index/frozen metadata differs from its receipt')
    for section in ('inputs','code','packaging'):
        if frozen['manifest'][section]!=fingerprints[section]:raise ValueError('Source parent executed frozen inventory changed')
    if any(meta.get(key)!=lineage['preserved_'+key]for key in ('structure_resume_parent','structure_delta_resume_parent')):
        raise ValueError('Complete-type child did not preserve actual historical adjudication lineage')
    return parent,seal


def package_lineage_members(config,output,accepted):
    paths=[Path(config[name+'_build'])for name in ('primary','reproduction')]
    actual=validate_resumed_parent_independence(*paths)
    members={};rows=[]
    for name,path in zip(('primary','reproduction'),paths):
        child=require_complete_type_build(path)
        if child['revision']!=accepted['database_revision']:raise ValueError('Runtime proof belongs to a different final child')
        parent,seal=require_source_parent_binding(config,name,path,child)
        parent_path=Path(config[name+'_parent_build']);integrity_path=Path(config['complete_type_'+name+'_parent_integrity'])
        local={}
        for filename,source in [('build_complete.json',path),('parent_lineage.json',path.with_name('parent_lineage.json')),
                ('started_fingerprints.json',path.with_name('started_fingerprints.json')),('build_status.json',path.with_name('build_status.json')),
                ('parent_integrity.json',integrity_path)]:
            member='builds/'+name+'/'+filename;members[member]=source;local[filename]={'member':member,'sha256':digest(source)}
        for filename in ('build_complete.json','parent_lineage.json','started_fingerprints.json','build_status.json','frozen_metadata.json'):
            source=parent_path.with_name(filename);member='builds/'+name+'/source-parent/'+filename
            members[member]=source;local['source-parent/'+filename]={'member':member,'sha256':digest(source)}
        rows.append({'name':name,'files':local,'source_parent_revision':parent['revision'],'source_parent_build_id':parent['build_id'],'source_parent_whole_sha256':seal['sha256']})
    proof={'schema':SCHEMA,'pass':True,'candidate_revision':accepted['database_revision'],'candidate_sha256':accepted['database_sha256'],
        'actual_local_physical_parent_audit':actual,'current_host_actual_inodes_checked':True,
        'original_lineage_validator_sha256':digest(Path(__file__).with_name('resume_structure_repairs.py')),
        'children':rows,'scope':'Historical actual final six-stage children and independent complete eight-stage owned-scope parents; public verifies immutable evidence bytes and does not claim freshly inspected historical inodes'}
    proof_path=Path(output)/'build-independence.json';proof_path.write_text(json.dumps(proof,indent=2)+'\n')
    members['builds/build-independence.json']=proof_path
    return members


def validate_portable_parent_independence(support,primary,reproduction,accepted):
    proof=json.loads((support.root/'builds/build-independence.json').read_text())
    if (proof.get('schema')!=SCHEMA or proof.get('pass')is not True
            or proof.get('candidate_revision')!=accepted['database_revision']or proof.get('candidate_sha256')!=accepted['database_sha256']
            or proof.get('current_host_actual_inodes_checked')is not True
            or proof.get('original_lineage_validator_sha256')!=digest(Path(__file__).with_name('resume_structure_repairs.py'))
            or proof.get('actual_local_physical_parent_audit',{}).get('pass')is not True):
        raise ValueError('Fresh portable exact complete-type historical independence proof required')
    records=[]
    for name,path in zip(('primary','reproduction'),map(Path,(primary,reproduction))):
        if path.resolve()!=support.root/'builds'/name/'build_complete.json':raise ValueError('Public build evidence cannot borrow host paths')
        matching=[r for r in proof['children']if r['name']==name]
        if len(matching)!=1:raise ValueError('Missing or duplicated historical child')
        for filename,row in matching[0]['files'].items():
            file=path.parent/filename
            if row['member']!=str(file.relative_to(support.root))or digest(file)!=row['sha256']:raise ValueError('Portable exact historical build material changed')
        child=require_complete_type_build(path);lineage=json.loads(path.with_name('parent_lineage.json').read_text());seal=json.loads(path.with_name('parent_integrity.json').read_text())
        source_path=path.parent/'source-parent/build_complete.json';parent=require_literal_jet_child_build(source_path)
        if (digest(path.with_name('parent_integrity.json'))!=lineage['parent_integrity_sha256']
                or digest(source_path)!=lineage['parent_receipt_sha256']or parent['revision']!=lineage['parent_revision']
                or parent['build_id']!=lineage['parent_build_id']
                or parent['build_id']!=matching[0]['source_parent_build_id']or parent['revision']!=matching[0]['source_parent_revision']
                or seal['sha256']!=matching[0]['source_parent_whole_sha256']):
            raise ValueError('Historical actual c933 source parent does not match final child lineage')
        verify_seal(seal,lineage);records.append((child,lineage))
    actual=proof['actual_local_physical_parent_audit'];one,two=records
    if (one[0]['build_id']==two[0]['build_id']or one[1]['parent_build_id']==two[1]['parent_build_id']
            or one[1]['parent_source_inode']==two[1]['parent_source_inode']or one[0]['revision']!=two[0]['revision']
            or one[1]['parent_revision']!=two[1]['parent_revision']or actual.get('distinct_source_inodes')is not True
            or actual.get('parent_build_ids')!=[r[1]['parent_build_id']for r in records]
            or actual.get('resumed_build_ids')!=[r[0]['build_id']for r in records]
            or actual.get('parent_revision')!=one[1]['parent_revision']):
        raise ValueError('Independent actual owned-scope source parents required')
    return {'schema':'FINEATLAS_PUBLIC_COMPLETE_TYPE_HISTORICAL_PROOF_VERIFICATION_V1','pass':True,
        'source_proof_sha256':digest(support.root/'builds/build-independence.json'),'historical_actual_parent_audit':actual,
        'physical_parent_inodes_rechecked_here':False,'immutable_historical_lineage_bytes_checked':True}
