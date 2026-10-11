"""Portable three-generation proof: nominal child, complete-type parent, owned-scope ancestor."""
from __future__ import annotations
import json
import datetime
from pathlib import Path
import sqlite3

from _download import digest
from resume_structure_repairs import validate_resumed_parent_independence
from portable_complete_structure_lineage import require_complete_type_build, package_lineage_members as package_complete_lineage, validate_portable_parent_independence as validate_complete_lineage
from types import SimpleNamespace

SCHEMA='FINEATLAS_PORTABLE_NOMINAL_SCOPE_THREE_GENERATION_BUILD_INDEPENDENCE_V1'
STAGES=('verify_complete_owned_type_parent_copy','nominal_design_scope_repairs','whole_graph_recomputation','freeze_metadata','browse_staging','embed_browse_indexes')


def require_nominal_scope_build(receipt_path):
    path=Path(receipt_path);value=json.loads(path.read_text())
    if (value.get('schema')!='FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1' or value.get('pass')is not True
            or value.get('complete')is not True or not value.get('build_id')or not value.get('ended_utc')
            or value.get('required_stages')!=list(STAGES)):
        raise ValueError('Actual completed six-stage nominal-scope child required')
    for name in ('started_fingerprints','build_status','parent_lineage'):
        if digest(path.parent/(name+'.json'))!=value.get(name+'_sha256'):
            raise ValueError('Nominal-scope child receipt evidence changed: '+name)
    states=json.loads(path.with_name('build_status.json').read_text())
    if set(states)!=set(STAGES)or any(row.get('status')!='PASS'for row in states.values()):
        raise ValueError('Every actual nominal-scope build stage must have passed')
    lineage=json.loads(path.with_name('parent_lineage.json').read_text())
    if (lineage.get('schema')!='FINEATLAS_REPAIR_PARENT_LINEAGE_V1'
            or lineage.get('resumed_build_id')!=value['build_id']or lineage.get('resumed_revision')!=value['revision']
            or lineage.get('parent_build_id')!=value.get('parent_build_id')
            or lineage.get('parent_source_inode')!=value.get('parent_source_inode')):
        raise ValueError('Actual nominal-scope child lineage differs from its completed receipt')
    copy=states[STAGES[0]]['result']
    for key in ('parent_database_sha256','parent_integrity_sha256','parent_receipt_sha256','parent_build_id','parent_revision'):
        if copy.get(key)!=lineage.get(key):raise ValueError('Actual whole-parent-copy evidence changed: '+key)
    return value


def verify_seal(seal,lineage):
    if (any(seal.get(key)is not True for key in ('pass','complete','integrity_pass','file_unchanged_during_checks','all_frozen_inputs_and_recipes_checked'))
            or seal.get('integrity_check')!=['ok']or seal.get('sha256')!=lineage['parent_database_sha256']
            or seal.get('database_revision')!=lineage['parent_revision']
            or Path(seal.get('database','')).resolve()!=Path(lineage['parent_database']).resolve()):
        raise ValueError('Actual complete-type parent whole-file integrity seal differs from child lineage')


def require_source_parent_binding(config,name,child_path,complete):
    lineage=json.loads(Path(child_path).with_name('parent_lineage.json').read_text())
    parent_path=Path(config[name+'_parent_build'])
    if Path(config['nominal_'+name+'_parent_build']).resolve()!=parent_path.resolve():
        raise ValueError('Explicit nominal direct-parent alias differs from its actual completed Source8 parent')
    parent=require_complete_type_build(parent_path)
    integrity_path=Path(config['nominal_'+name+'_parent_integrity']);seal=json.loads(integrity_path.read_text())
    if (digest(parent_path)!=lineage['parent_receipt_sha256']or parent['revision']!=lineage['parent_revision']
            or parent['build_id']!=lineage['parent_build_id']
            or Path(parent['database']).resolve()!=Path(lineage['parent_database']).resolve()
            or digest(integrity_path)!=lineage['parent_integrity_sha256']):
        raise ValueError('The actual completed six-stage complete-type source parent cannot be substituted with an older checkpoint')
    verify_seal(seal,lineage)
    database=Path(parent['database']).resolve()
    if any(Path(str(database)+s).exists()for s in ('-wal','-shm','-journal')):
        raise ValueError('Source parent must be closed')
    actual_stat=database.stat();lineage_path=Path(child_path).with_name('parent_lineage.json')
    if [actual_stat.st_dev,actual_stat.st_ino]!=complete['parent_source_inode']:
        raise ValueError('Actual complete-type source inode changed after complete child byte-copy verification')
    state=json.loads(Path(child_path).with_name('build_status.json').read_text())[STAGES[0]]
    copy_end=datetime.datetime.fromisoformat(state['started_utc']).timestamp()+state['seconds']
    if actual_stat.st_mtime>copy_end:raise ValueError('Actual complete-type source changed after verified complete whole-byte copy')
    if database.stat().st_size!=seal['bytes']:
        raise ValueError('Parent byte extent differs from its actual whole-file integrity receipt')
    with sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)as con:
        con.execute('PRAGMA query_only=ON');meta={key:json.loads(value)for key,value in con.execute('SELECT key,value FROM metadata')}
    frozen=json.loads(parent_path.with_name('frozen_metadata.json').read_text())
    fingerprints=json.loads(parent_path.with_name('started_fingerprints.json').read_text())
    if (meta.get('database_revision')!=parent['revision']or meta.get('browse_index_revision')!=parent['revision']
            or meta.get('browse_parent_revision')!=parent['source_graph_revision']or frozen['revision']!=parent['source_graph_revision']
            or meta.get('structure_frozen_build_manifest')!=frozen['manifest']
            or not meta.get('complete_owned_type_repairs')or meta.get('nominal_design_scope_repairs')):
        raise ValueError('Actual completed Source8 parent SQL/index/frozen metadata differs from its receipt')
    for section in ('inputs','code','packaging'):
        if frozen['manifest'][section]!=fingerprints[section]:raise ValueError('Source parent executed frozen inventory changed')
    if any(meta.get(key)!=lineage['preserved_'+key]for key in ('structure_resume_parent','structure_delta_resume_parent','structure_complete_type_resume_parent')):
        raise ValueError('Nominal-scope child did not preserve actual historical adjudication lineage')
    return parent,seal


def package_lineage_members(config,output,accepted):
    paths=[Path(config[name+'_build'])for name in ('primary','reproduction')]
    actual=validate_resumed_parent_independence(*paths)
    members={};rows=[]
    for name,path in zip(('primary','reproduction'),paths):
        child=require_nominal_scope_build(path)
        if child['revision']!=accepted['database_revision']:raise ValueError('Runtime proof belongs to a different final child')
        parent,seal=require_source_parent_binding(config,name,path,child)
        parent_path=Path(config[name+'_parent_build']);integrity_path=Path(config['nominal_'+name+'_parent_integrity'])
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
        'children':rows,'scope':'Historical nominal six-stage final children, complete-type six-stage immediate parents, and owned-scope eight-stage ancestors; public verifies immutable evidence bytes and does not claim freshly inspected historical inodes'}
    foundation_config=source8_config(config)
    source8_accepted=source8_accepted_record(config)
    foundation_output=Path(output)/'source8-foundation';foundation_output.mkdir(exist_ok=False)
    foundation_members=package_complete_lineage(foundation_config,foundation_output,source8_accepted)
    members.update({'source8-foundation/'+name:path for name,path in foundation_members.items()})
    proof['source8_foundation']={'accepted':source8_accepted,'proof_sha256':digest(foundation_output/'build-independence.json')}
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
        raise ValueError('Fresh portable exact nominal-scope historical independence proof required')
    records=[]
    for name,path in zip(('primary','reproduction'),map(Path,(primary,reproduction))):
        if path.resolve()!=support.root/'builds'/name/'build_complete.json':raise ValueError('Public build evidence cannot borrow host paths')
        matching=[r for r in proof['children']if r['name']==name]
        if len(matching)!=1:raise ValueError('Missing or duplicated historical child')
        for filename,row in matching[0]['files'].items():
            file=path.parent/filename
            if row['member']!=str(file.relative_to(support.root))or digest(file)!=row['sha256']:raise ValueError('Portable exact historical build material changed')
        child=require_nominal_scope_build(path);lineage=json.loads(path.with_name('parent_lineage.json').read_text());seal=json.loads(path.with_name('parent_integrity.json').read_text())
        source_path=path.parent/'source-parent/build_complete.json';parent=require_complete_type_build(source_path)
        inventory=json.loads(path.with_name('started_fingerprints.json').read_text())
        source_inventory=json.loads(source_path.with_name('started_fingerprints.json').read_text())
        source_freeze=json.loads(source_path.with_name('frozen_metadata.json').read_text())
        if inventory!=accepted.get('fingerprints'):
            raise ValueError('Portable actual final child must bind the accepted complete frozen inventory')
        if (source_freeze.get('revision')!=parent.get('source_graph_revision')
                or any(source_freeze.get('manifest',{}).get(group)!=source_inventory.get(group)
                       for group in ('inputs','code','packaging'))
                or any(not isinstance(inventory.get(group),dict)
                       or not isinstance(source_inventory.get(group),dict)
                       or any(inventory[group].get(key)!=sha for key,sha in source_inventory[group].items())
                       for group in ('inputs','code','packaging'))):
            raise ValueError('Portable final child must preserve every actually frozen source-parent input and implementation')
        if (digest(path.with_name('parent_integrity.json'))!=lineage['parent_integrity_sha256']
                or digest(source_path)!=lineage['parent_receipt_sha256']or parent['revision']!=lineage['parent_revision']
                or parent['build_id']!=lineage['parent_build_id']
                or parent['build_id']!=matching[0]['source_parent_build_id']or parent['revision']!=matching[0]['source_parent_revision']
                or seal['sha256']!=matching[0]['source_parent_whole_sha256']):
            raise ValueError('Historical actual complete-type source parent does not match final child lineage')
        verify_seal(seal,lineage);records.append((child,lineage))
    actual=proof['actual_local_physical_parent_audit'];one,two=records
    if (one[0]['build_id']==two[0]['build_id']or one[1]['parent_build_id']==two[1]['parent_build_id']
            or one[1]['parent_source_inode']==two[1]['parent_source_inode']or one[0]['revision']!=two[0]['revision']
            or one[1]['parent_revision']!=two[1]['parent_revision']or actual.get('distinct_source_inodes')is not True
            or actual.get('parent_build_ids')!=[r[1]['parent_build_id']for r in records]
            or actual.get('resumed_build_ids')!=[r[0]['build_id']for r in records]
            or actual.get('parent_revision')!=one[1]['parent_revision']):
        raise ValueError('Independent actual complete-type source parents required')
    foundation=proof.get('source8_foundation')
    if (not foundation or foundation.get('accepted',{}).get('database_revision')!=records[0][1]['parent_revision']
            or foundation.get('accepted',{}).get('database_sha256')!=records[0][1]['parent_database_sha256']
            or digest(support.root/'source8-foundation/builds/build-independence.json')!=foundation['proof_sha256']):
        raise ValueError('Actual complete-type parent ancestry is missing or changed')
    foundation_support=SimpleNamespace(root=support.root/'source8-foundation')
    ancestry=validate_complete_lineage(foundation_support,foundation_support.root/'builds/primary/build_complete.json',foundation_support.root/'builds/reproduction/build_complete.json',foundation['accepted'])
    for name,(child,lineage)in zip(('primary','reproduction'),records):
        source_path=support.root/'builds'/name/'source-parent/build_complete.json'
        archived=foundation_support.root/'builds'/name/'build_complete.json'
        if digest(source_path)!=digest(archived):raise ValueError('Nominal direct parent differs from verified complete-type ancestry')
    return {'schema':'FINEATLAS_PUBLIC_NOMINAL_SCOPE_THREE_GENERATION_PROOF_VERIFICATION_V1','pass':True,
        'source_proof_sha256':digest(support.root/'builds/build-independence.json'),'historical_actual_parent_audit':actual,
        'physical_parent_inodes_rechecked_here':False,'immutable_historical_lineage_bytes_checked':True,'complete_type_parent_historical_ancestry':ancestry}


def source8_config(config):
    """Bind old complete-type helper locally; never mutate the delivery configuration."""
    result=dict(config)
    for name in ('primary','reproduction'):
        if Path(config['nominal_'+name+'_parent_build']).resolve()!=Path(config[name+'_parent_build']).resolve():
            raise ValueError('Nominal direct-parent build aliases must refer to the same actual Source8 parent')
        result[name+'_build']=config[name+'_parent_build']
        result[name+'_parent_build']=config['lineage_'+name+'_build']
    return result


def source8_accepted_record(config):
    primary=require_complete_type_build(config['primary_parent_build'])
    reproduction=require_complete_type_build(config['reproduction_parent_build'])
    seals=[json.loads(Path(config['nominal_'+name+'_parent_integrity']).read_text())for name in ('primary','reproduction')]
    inventories=[json.loads(Path(config[name+'_parent_build']).with_name('started_fingerprints.json').read_text())for name in ('primary','reproduction')]
    if (primary['revision']!=reproduction['revision']or inventories[0]!=inventories[1]
            or any(seal.get('database_revision')!=parent['revision']or not seal.get('sha256')
                   for seal,parent in zip(seals,(primary,reproduction)))):
        raise ValueError('Two complete-type parents must bind the same revision and frozen inventory, each with its own actual whole-file SHA')
    return {'database_revision':primary['revision'],'database_sha256':seals[0]['sha256'],'fingerprints':inventories[0]}
