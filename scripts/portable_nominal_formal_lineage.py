"""Four-generation proof for explicit four-stage version-only formal promotions."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import sqlite3
from types import SimpleNamespace

from _download import digest
from portable_nominal_structure_lineage import (
    require_nominal_scope_build, package_lineage_members as package_nominal_members,
    validate_portable_parent_independence as validate_nominal_independence)
from coordinate_structure_delivery import read, metadata
from promote_stable_candidate import version_only, canonical_hash
import re

SCHEMA='FINEATLAS_NOMINAL_FORMAL_FOUR_GENERATION_INDEPENDENCE_V1'
STAGES=('verified_version_only_semantic_reuse','browse_staging','embed_browse_indexes','final_bound_source_and_cache_checks')


def candidate_config(config):
    path=Path(config['nominal_candidate_delivery_config']).resolve()
    value=read(path)
    if not value.get('primary_build')or not value.get('reproduction_build'):
        raise ValueError('Actual complete Source9 candidate configuration required')
    return value


def candidate_accepted(config):
    source=candidate_config(config);path=Path(source['local_output'])/'acceptance_receipt.json'
    value=read(path)
    if not value.get('local_all_pass')or value.get('database_revision')!=require_nominal_scope_build(source['primary_build'])['revision']:
        raise ValueError('Actual completed Source9 candidate acceptance is missing')
    from structure_acceptance_contract import validate_completed_acceptance
    validate_completed_acceptance(value)
    finalized=read(Path(source['delivery_root'])/'nominal_scope_finalized_extension.json')
    extension_path=Path(source['delivery_root'])/'public/checks/nominal_scope_public_extension.json'
    if (finalized.get('schema')!='FINEATLAS_NOMINAL_SCOPE_FINALIZED_EXTENSION_V1'or finalized.get('pass')is not True
            or finalized.get('database_revision')!=value['database_revision']
            or finalized.get('public_extension_sha256')!=digest(extension_path)):
        raise ValueError('Source9 candidate complete public finalization is absent or changed')
    return value


def require_formal_version_only_build(receipt_path):
    path=Path(receipt_path);value=read(path)
    if (value.get('schema')!='FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1'or value.get('complete')is not True
            or value.get('pass')is not True or value.get('semantic_reuse_only')is not True
            or value.get('requires_independent_acceptance')is not True or not value.get('build_id')or not value.get('ended_utc')):
        raise ValueError('Actual four-stage version-only formal build required')
    if 'required_stages'in value and value['required_stages']!=list(STAGES):
        raise ValueError('A semantic candidate recipe cannot impersonate a version-only formal recipe')
    for name in ('started_fingerprints','build_status'):
        if digest(path.with_name(name+'.json'))!=value.get(name+'_sha256'):
            raise ValueError('Actual formal promotion evidence changed: '+name)
    states=read(path.with_name('build_status.json'))
    if set(states)!=set(STAGES)or any(state.get('status')!='PASS'for state in states.values()):
        raise ValueError('Exactly four actual completed formal promotion stages required')
    verified=states[STAGES[0]]['result'];final=states[STAGES[-1]]['result']
    promotion=read(path.with_name('promotion_metadata.json'));complete=read(path.with_name('promotion_complete.json'))
    if (verified.get('graphs_recomputed')is not False or final.get('source_unchanged')is not True
            or final.get('revision')!=value['revision']or complete.get('complete')is not True
            or complete.get('pass')is not True or complete.get('source_unchanged')is not True
            or complete.get('requires_full_new_acceptance_and_public_download')is not True
            or complete.get('database_revision')!=value['revision']or complete.get('source_sha256')!=verified.get('source_sha256')
            or promotion.get('release')!=value['release']or complete.get('release')!=value['release']
            or promotion['manifest']['promotion'].get('parent_candidate_revision')!=verified.get('parent_revision')
            or promotion['manifest']['promotion'].get('semantic_graph_recomputed')is not False
            or promotion['manifest']['promotion'].get('browse_indexes_rebuilt')is not True):
        raise ValueError('Formal version-only source, release, semantic reuse or final cache evidence differs')
    return value


def require_source_binding(config,name,path):
    child=require_formal_version_only_build(path);source=candidate_config(config)
    parent_path=Path(source[name+'_build']);parent=require_nominal_scope_build(parent_path)
    integrity_path=Path(config['formal_'+name+'_candidate_integrity']);integrity=read(integrity_path)
    states=read(Path(path).with_name('build_status.json'));verified=states[STAGES[0]]['result']
    if (any(integrity.get(key)is not True for key in ('pass','complete','integrity_pass','file_unchanged_during_checks','all_frozen_inputs_and_recipes_checked'))
            or integrity.get('integrity_check')!=['ok']or integrity.get('database_revision')!=parent['revision']
            or Path(integrity['database']).resolve()!=Path(parent['database']).resolve()
            or verified.get('parent_revision')!=parent['revision']or verified.get('source_sha256')!=integrity['sha256']):
        raise ValueError('Formal actual source must bind one independently accepted Source9 six-stage artifact')
    source_database=Path(parent['database']).resolve();formal_database=Path(child['database']).resolve()
    for database in (source_database,formal_database):
        if any(Path(str(database)+suffix).exists()for suffix in ('-wal','-shm','-journal')):
            raise ValueError('Formal and source databases must both be closed')
    if source_database.samefile(formal_database)or source_database.stat().st_size!=integrity['bytes']:
        raise ValueError('Actual Source9 source and formal version-only copy must be separate files')
    if source_database.stat().st_mtime>__import__('datetime').datetime.fromisoformat(child['ended_utc']).timestamp():
        raise ValueError('Source9 candidate changed after actual formal source-copy validation')
    source_meta=metadata(source_database);formal_meta=metadata(formal_database)
    source_code=Path(config['nominal_candidate_code_root']);source_inputs=Path(source['inputs'])
    from promote_structure_stable import validate_structure_reuse
    result=validate_structure_reuse(source_meta,source_code,source_inputs,Path(config['formal_code_root']),Path(config['inputs']))
    recorded=read(Path(path).with_name('promotion_metadata.json'))
    if result!=recorded or formal_meta['structure_frozen_build_manifest']!=result['manifest']:
        raise ValueError('Formal source facts, code and inputs are not an exact literal-version-only reuse')
    if (formal_meta['database_revision']!=child['revision']or formal_meta['browse_index_revision']!=child['revision']
            or formal_meta['browse_parent_revision']!=result['revision']
            or source_meta['database_revision']!=parent['revision']):
        raise ValueError('Actual formal or source database/cache metadata differs')
    for key in ('structure_resume_parent','structure_delta_resume_parent','structure_complete_type_resume_parent','structure_nominal_design_resume_parent'):
        if formal_meta.get(key)!=source_meta.get(key):
            raise ValueError('Formal version-only preparation changed an original semantic lineage')
    return child,parent,integrity


def package_lineage_members(config,output,accepted):
    output=Path(output);members={};records=[];inodes=[];source=candidate_config(config)
    for name in ('primary','reproduction'):
        path=Path(config[name+'_build']);child,parent,integrity=require_source_binding(config,name,path)
        if child['revision']!=accepted['database_revision']:raise ValueError('Formal source proof differs from accepted formal artifact')
        source_database=Path(parent['database']);formal_database=Path(child['database'])
        inodes.extend([(source_database.stat().st_dev,source_database.stat().st_ino),(formal_database.stat().st_dev,formal_database.stat().st_ino)])
        files={}
        for filename in ('build_complete.json','build_status.json','started_fingerprints.json','promotion_metadata.json','promotion_complete.json'):
            current=path.with_name(filename);member='builds/'+name+'/'+filename;members[member]=current;files[filename]={'member':member,'sha256':digest(current)}
        integrity_path=Path(config['formal_'+name+'_candidate_integrity']);member='builds/'+name+'/source9_integrity.json';members[member]=integrity_path
        files['source9_integrity.json']={'member':member,'sha256':digest(integrity_path)}
        records.append({'name':name,'files':files,'formal_build_id':child['build_id'],'source9_build_id':parent['build_id'],
            'source9_revision':parent['revision'],'source9_whole_sha256':integrity['sha256'],
            'actual_source_inode':[source_database.stat().st_dev,source_database.stat().st_ino],
            'actual_formal_inode':[formal_database.stat().st_dev,formal_database.stat().st_ino]})
    if len(set(inodes))!=4 or records[0]['formal_build_id']==records[1]['formal_build_id']or records[0]['source9_build_id']==records[1]['source9_build_id']:
        raise ValueError('Two independently promoted formal files and two independent Source9 sources required')
    foundation_output=output/'source9-foundation';foundation_output.mkdir(exist_ok=False)
    nominal_accepted=candidate_accepted(config)
    if records[0]['source9_whole_sha256']!=nominal_accepted['database_sha256']:
        raise ValueError('Formal primary source must bind the actually accepted Source9 candidate full SHA')
    foundation=package_nominal_members(source,foundation_output,nominal_accepted)
    members.update({'source9-foundation/'+name:path for name,path in foundation.items()})
    for name in ('primary','reproduction'):
        members['source9-foundation/builds/'+name+'/frozen_metadata.json']=Path(source[name+'_build']).with_name('frozen_metadata.json')
    for prefix,code_root,inputs_root in (('source9',Path(config['nominal_candidate_code_root']),Path(source['inputs'])),
            ('formal',Path(config['formal_code_root']),Path(config['inputs']))):
        for name,path in (('__init__.py',code_root/'src/fineatlas/__init__.py'),('pyproject.toml',code_root/'pyproject.toml'),('review_release.json',inputs_root/'review_release.json')):
            members['versions/'+prefix+'/'+name]=path
    proof={'schema':SCHEMA,'pass':True,'formal_revision':accepted['database_revision'],'formal_sha256':accepted['database_sha256'],
        'actual_local_four_distinct_inodes_checked':True,'children':records,'source9_accepted':nominal_accepted,
        'source9_foundation_proof_sha256':digest(foundation_output/'build-independence.json'),
        'version_only_promoter_sha256':digest(Path(__file__).with_name('promote_structure_stable.py')),
        'scope':'Four actual formal version-only promotion stages, six-stage nominal Source9 candidates, six-stage Source8 parents, eight-stage c933 ancestors. Public verifies original archived evidence and never claims fresh historical inode checks.'}
    proof_path=output/'formal-four-generation-independence.json';proof_path.write_text(json.dumps(proof,indent=2)+'\n')
    members['builds/formal-four-generation-independence.json']=proof_path
    return members


def validate_portable_parent_independence(support,primary,reproduction,accepted):
    proof=read(support.root/'builds/formal-four-generation-independence.json')
    if (proof.get('schema')!=SCHEMA or proof.get('pass')is not True
            or proof.get('formal_revision')!=accepted['database_revision']or proof.get('formal_sha256')!=accepted['database_sha256']
            or proof.get('actual_local_four_distinct_inodes_checked')is not True
            or proof.get('version_only_promoter_sha256')!=digest(Path(__file__).with_name('promote_structure_stable.py'))):
        raise ValueError('Exact actual four-generation formal proof required')
    records=[];parents=[];fingerprints=[]
    for name,path in zip(('primary','reproduction'),map(Path,(primary,reproduction))):
        if path.resolve()!=support.root/'builds'/name/'build_complete.json':raise ValueError('Formal public proof cannot borrow host receipt paths')
        selected=[row for row in proof['children']if row['name']==name]
        if len(selected)!=1:raise ValueError('Each independent formal promotion needs one original evidence record')
        row=selected[0]
        for filename,item in row['files'].items():
            file=path.parent/filename
            if item['member']!=str(file.relative_to(support.root))or digest(file)!=item['sha256']:
                raise ValueError('Portable formal historical bytes differ')
        child=require_formal_version_only_build(path);integrity=read(path.with_name('source9_integrity.json'))
        parent_path=support.root/'source9-foundation/builds'/name/'build_complete.json';parent=require_nominal_scope_build(parent_path)
        verified=read(path.with_name('build_status.json'))[STAGES[0]]['result']
        parent_frozen=read(parent_path.with_name('started_fingerprints.json'));current_frozen=read(path.with_name('started_fingerprints.json'))
        promotion=read(path.with_name('promotion_metadata.json'))
        if (child['revision']!=accepted['database_revision']or current_frozen!=accepted['fingerprints']
                or parent['build_id']!=row['source9_build_id']or child['build_id']!=row['formal_build_id']
                or parent['revision']!=row['source9_revision']or parent['revision']!=integrity.get('database_revision')
                or integrity.get('sha256')!=row['source9_whole_sha256']or verified['source_sha256']!=integrity['sha256']
                or verified['parent_revision']!=parent['revision']
                or promotion['manifest']['promotion']['parent_candidate_revision']!=parent['revision']):
            raise ValueError('Formal, source9 and accepted original frozen proof do not agree')
        source_freeze=read(parent_path.with_name('frozen_metadata.json'))
        if (promotion['manifest']['promotion'].get('parent_frozen_manifest_sha256')!=canonical_hash(source_freeze['manifest'])
                or any(source_freeze['manifest'][group]!=parent_frozen[group]for group in ('inputs','code','packaging'))):
            raise ValueError('Original Source9 semantic freeze is absent or changed')
        validate_portable_version_literals(support.root,parent_frozen,current_frozen,child['release'])
        differences={group:{key for key in current_frozen[group]if parent_frozen[group].get(key)!=current_frozen[group][key]}for group in ('inputs','code','packaging')}
        if (any(set(current_frozen[group])!=set(parent_frozen[group])for group in differences)
                or differences!={'inputs':{'review_release.json'},'code':{'src/fineatlas/__init__.py'},'packaging':{'pyproject.toml'}}):
            raise ValueError('Formal public freeze contains changes beyond the three allowed version literals')
        records.append(row);parents.append(parent);fingerprints.append(parent_frozen)
    if (records[0]['formal_build_id']==records[1]['formal_build_id']or parents[0]['build_id']==parents[1]['build_id']
            or len({tuple(row[key])for row in records for key in ('actual_source_inode','actual_formal_inode')})!=4
            or parents[0]['revision']!=parents[1]['revision']or fingerprints[0]!=fingerprints[1]):
        raise ValueError('Two exact independently accepted nominal Source9 sources and formal promotions required')
    if records[0]['source9_whole_sha256']!=proof['source9_accepted']['database_sha256']:
        raise ValueError('Formal primary source SHA differs from the accepted Source9 candidate')
    foundation=SimpleNamespace(root=support.root/'source9-foundation')
    if digest(foundation.root/'builds/build-independence.json')!=proof['source9_foundation_proof_sha256']:
        raise ValueError('Original candidate three-generation historical proof changed')
    ancestry=validate_nominal_independence(foundation,foundation.root/'builds/primary/build_complete.json',foundation.root/'builds/reproduction/build_complete.json',proof['source9_accepted'])
    return {'schema':'FINEATLAS_PUBLIC_FORMAL_NOMINAL_FOUR_GENERATION_PROOF_VERIFICATION_V1','pass':True,
        'formal_revision':accepted['database_revision'],'proof_sha256':digest(support.root/'builds/formal-four-generation-independence.json'),
        'historical_source9_three_generation_proof':ancestry,'physical_parent_inodes_rechecked_here':False,'immutable_original_four_generation_bytes_checked':True}


def validate_portable_version_literals(root,source_frozen,formal_frozen,release):
    root=Path(root);expected={'__init__.py':('code','src/fineatlas/__init__.py'),'pyproject.toml':('packaging','pyproject.toml'),'review_release.json':('inputs','review_release.json')}
    for prefix,inventory in (('source9',source_frozen),('formal',formal_frozen)):
        for name,(group,key)in expected.items():
            if digest(root/'versions'/prefix/name)!=inventory[group][key]:
                raise ValueError('Original portable candidate/formal version-only bytes differ from accepted freeze')
    version_only((root/'versions/source9/__init__.py').read_bytes(),(root/'versions/formal/__init__.py').read_bytes(),release)
    old=read(root/'versions/source9/review_release.json');new=read(root/'versions/formal/review_release.json')
    if not re.fullmatch(r'v1\.11\.\d+',release)or old|{'version':release}!=new or new.get('version')!=release:
        raise ValueError('Only the release input version may change for formal preparation')
    old=(root/'versions/source9/pyproject.toml').read_text();new=(root/'versions/formal/pyproject.toml').read_text();pattern=re.compile(r'(?m)^version\s*=\s*"([^"\n]+)"$')
    if len(pattern.findall(old))!=1 or pattern.findall(new)!=[release[1:]]or pattern.sub('version = "VERSION"',old)!=pattern.sub('version = "VERSION"',new):
        raise ValueError('Only the packaging version literal may change')
