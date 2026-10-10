"""Independent factual four-stage and literal-version checks; no build imports."""

if not __debug__:
    raise RuntimeError('Optimized Python is forbidden for mandatory independent audit gates')

import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3

FORMAL_STAGES=('verified_version_only_semantic_reuse','browse_staging','embed_browse_indexes','final_bound_source_and_cache_checks')
NOMINAL_STAGES=('verify_complete_owned_type_parent_copy','nominal_design_scope_repairs','whole_graph_recomputation','freeze_metadata','browse_staging','embed_browse_indexes')
FOUR_SCHEMA='FINEATLAS_NOMINAL_FORMAL_FOUR_GENERATION_INDEPENDENCE_V1'

def read(path):return json.loads(Path(path).read_text())
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def metadata(path):
    path=Path(path).resolve()
    assert not any(Path(str(path)+suffix).exists()for suffix in('-wal','-shm','-journal'))
    with sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)as con:
        con.execute('PRAGMA query_only=ON')
        return {key:json.loads(value)for key,value in con.execute('SELECT key,value FROM metadata')}

def exact_formal_receipt(path):
    path=Path(path);row=read(path)
    assert row['schema']=='FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1'
    assert all(row.get(key)is True for key in('complete','pass','semantic_reuse_only','requires_independent_acceptance'))
    assert row['build_id']and row['started_utc']and row['ended_utc']
    assert 'required_stages'not in row or tuple(row['required_stages'])==FORMAL_STAGES
    states=read(path.with_name('build_status.json'))
    assert set(states)==set(FORMAL_STAGES)and all(x['status']=='PASS'for x in states.values())
    for name in('build_status','started_fingerprints'):assert digest(path.with_name(name+'.json'))==row[name+'_sha256']
    promotion=read(path.with_name('promotion_metadata.json'));complete=read(path.with_name('promotion_complete.json'))
    verified=states[FORMAL_STAGES[0]]['result'];final=states[FORMAL_STAGES[-1]]['result']
    assert verified['graphs_recomputed']is False and final['source_unchanged']is True and final['revision']==row['revision']
    assert complete['complete']is True and complete['pass']is True and complete['source_unchanged']is True
    assert complete['requires_full_new_acceptance_and_public_download']is True
    assert complete['database_revision']==row['revision']and complete['source_sha256']==verified['source_sha256']==row['source_sha256']
    assert complete['release']==promotion['release']==row['release']
    assert promotion['revision']==row['revision']
    mark=promotion['manifest']['promotion']
    assert mark['parent_candidate_revision']==verified['parent_revision']and mark['semantic_graph_recomputed']is False and mark['browse_indexes_rebuilt']is True
    assert mark['allowed_deltas']==['review_release.version','SDK __version__ literal','packaging version literal']
    return row,promotion,verified

def exact_nominal_receipt(path):
    path=Path(path);row=read(path)
    assert row['schema']=='FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1'and row['complete']is True and row['pass']is True
    assert tuple(row['required_stages'])==NOMINAL_STAGES
    assert digest(path.with_name('build_status.json'))==row['build_status_sha256']
    assert digest(path.with_name('started_fingerprints.json'))==row['started_fingerprints_sha256']
    assert digest(path.with_name('parent_lineage.json'))==row['parent_lineage_sha256']
    states=read(path.with_name('build_status.json'));assert set(states)==set(NOMINAL_STAGES)and all(x['status']=='PASS'for x in states.values())
    freeze=read(path.with_name('frozen_metadata.json'));fingerprints=read(path.with_name('started_fingerprints.json'))
    assert freeze['revision']==row['source_graph_revision']and all(fingerprints[group]==freeze['manifest'][group]for group in('inputs','code','packaging'))
    assert row['cache_bindings']=={'browse_parent_revision':freeze['revision'],'browse_source_revision':freeze['revision'],'browse_index_revision':row['revision']}
    return row,freeze

def version_literals(source_files,formal_files,source_frozen,formal_frozen,release):
    assert re.fullmatch(r'v1\.11\.\d+',release)
    allow={'inputs':{'review_release.json'},'code':{'src/fineatlas/__init__.py'},'packaging':{'pyproject.toml'}}
    for group,expected in allow.items():
        assert set(source_frozen[group])==set(formal_frozen[group])
        assert {key for key in source_frozen[group]if source_frozen[group][key]!=formal_frozen[group][key]}==expected
    for name,group,key in(('__init__.py','code','src/fineatlas/__init__.py'),('pyproject.toml','packaging','pyproject.toml'),('review_release.json','inputs','review_release.json')):
        assert digest(source_files[name])==source_frozen[group][key]and digest(formal_files[name])==formal_frozen[group][key]
    old=read(source_files['review_release.json']);new=read(formal_files['review_release.json'])
    assert old|{'version':release}==new and new['version']==release
    old_init=Path(source_files['__init__.py']).read_text();new_init=Path(formal_files['__init__.py']).read_text()
    pattern=re.compile(r'(?m)^__version__\s*=\s*([\'"])([^\n\'"]+)\1$')
    assert len(pattern.findall(old_init))==1 and pattern.findall(new_init)==[(pattern.findall(old_init)[0][0],release[1:])]
    assert pattern.sub('__version__ = "VERSION"',old_init)==pattern.sub('__version__ = "VERSION"',new_init)
    old_pkg=Path(source_files['pyproject.toml']).read_text();new_pkg=Path(formal_files['pyproject.toml']).read_text();pattern=re.compile(r'(?m)^version\s*=\s*"([^"\n]+)"$')
    assert len(pattern.findall(old_pkg))==1 and pattern.findall(new_pkg)==[release[1:]]
    assert pattern.sub('version = "VERSION"',old_pkg)==pattern.sub('version = "VERSION"',new_pkg)

def bind_formal_sources(args,meta):
    """Read true four receipts and separate six parents without fabricating any."""
    formal_paths=[Path(args.primary_build),Path(args.reproduction_build)]
    if args.installed_sdk:
        root=Path(args.support_registry).resolve().parent;support=read(args.support_registry)
        assert root==args.database.parent.parent/'regression-support'
        assert support['database_revision']==meta['database_revision']
        for name,value in support['files'].items():
            member=Path(name);assert not member.is_absolute()and'..'not in member.parts and'\\'not in name
            path=root/member;assert not path.is_symlink()and path.resolve().is_relative_to(root)and digest(path)==value
        proof=read(root/'builds/formal-four-generation-independence.json');assert proof['schema']==FOUR_SCHEMA and proof['pass']is True
        assert proof['formal_revision']==meta['database_revision']and proof['actual_local_four_distinct_inodes_checked']is True
        assert proof['source9_accepted']['local_all_pass']is True
        parents=[root/'source9-foundation/builds'/name/'build_complete.json'for name in('primary','reproduction')]
        integrities=[root/'builds'/name/'source9_integrity.json'for name in('primary','reproduction')]
        assert formal_paths==[root/'builds'/name/'build_complete.json'for name in('primary','reproduction')]
        source_files={name:root/'versions/source9'/name for name in('__init__.py','pyproject.toml','review_release.json')}
        formal_files={name:root/'versions/formal'/name for name in source_files}
    else:
        assert args.formal_delivery_config is not None
        config=read(args.formal_delivery_config);source=read(config['nominal_candidate_delivery_config'])
        assert Path(config['formal_code_root']).resolve()==Path(args.code).resolve()
        assert Path(config['inputs']).resolve()==Path(args.inputs).resolve()
        assert formal_paths==[Path(config[name+'_build'])for name in('primary','reproduction')]
        parents=[Path(source[name+'_build'])for name in('primary','reproduction')]
        integrities=[Path(config['formal_'+name+'_candidate_integrity'])for name in('primary','reproduction')]
        source_files={'__init__.py':Path(config['nominal_candidate_code_root'])/'src/fineatlas/__init__.py','pyproject.toml':Path(config['nominal_candidate_code_root'])/'pyproject.toml','review_release.json':Path(source['inputs'])/'review_release.json'}
        formal_files={'__init__.py':Path(args.code)/'src/fineatlas/__init__.py','pyproject.toml':Path(args.code)/'pyproject.toml','review_release.json':Path(args.inputs)/'review_release.json'}
    rows=[];inodes=[]
    for name,path,parent_path,seal_path in zip(('primary','reproduction'),formal_paths,parents,integrities):
        child,promotion,verified=exact_formal_receipt(path);parent,freeze=exact_nominal_receipt(parent_path);seal=read(seal_path)
        assert all(seal.get(key)is True for key in('pass','complete','integrity_pass','file_unchanged_during_checks','all_frozen_inputs_and_recipes_checked'))and seal['integrity_check']==['ok']
        assert child['revision']==meta['database_revision']and seal['database_revision']==parent['revision']==verified['parent_revision']
        assert seal['sha256']==verified['source_sha256']and Path(seal['database']).resolve()==Path(parent['database']).resolve()
        mark=promotion['manifest']['promotion'];assert mark['parent_frozen_manifest_sha256']==canonical(freeze['manifest'])
        current=read(path.with_name('started_fingerprints.json'));assert all(current[group]==promotion['manifest'][group]==meta['structure_frozen_build_manifest'][group]for group in('inputs','code','packaging'))
        assert promotion['manifest']==meta['structure_frozen_build_manifest']and promotion['revision']==child['revision']
        version_literals(source_files,formal_files,freeze['manifest'],promotion['manifest'],child['release'])
        if not args.installed_sdk:
            source_db=Path(parent['database']).resolve();child_db=Path(child['database']).resolve()
            source_meta=metadata(source_db);formal_meta=metadata(child_db)
            assert source_meta['database_revision']==parent['revision']and source_meta['structure_frozen_build_manifest']==freeze['manifest']
            assert formal_meta['database_revision']==child['revision']and formal_meta['structure_frozen_build_manifest']==promotion['manifest']
            assert source_db.stat().st_size==seal['bytes']and source_db.stat().st_mtime<=datetime.datetime.fromisoformat(child['ended_utc']).timestamp()
            for key in('structure_resume_parent','structure_delta_resume_parent','structure_complete_type_resume_parent','structure_nominal_design_resume_parent'):
                assert source_meta[key]==formal_meta[key]
            allowed={'release','review_version','structure_frozen_build_manifest','database_revision'}
            assert {key:value for key,value in source_meta.items()if key not in allowed and not key.startswith('browse_')}=={key:value for key,value in formal_meta.items()if key not in allowed and not key.startswith('browse_')},'Formal promotion changed semantic metadata outside exact version/cache fields'
            inodes.extend((db.stat().st_dev,db.stat().st_ino)for db in(source_db,child_db))
        else:
            records=[record for record in proof['children']if record['name']==name];assert len(records)==1
            record=records[0]
            assert record['formal_build_id']==child['build_id']and record['source9_build_id']==parent['build_id']
            assert record['source9_revision']==parent['revision']and record['source9_whole_sha256']==seal['sha256']
            for filename,item in record['files'].items():
                actual_path=path.with_name(filename)
                assert item['member']==str(actual_path.relative_to(root))and digest(actual_path)==item['sha256']
        rows.append({'name':name,'formal_build_id':child['build_id'],'source9_build_id':parent['build_id'],'formal_revision':child['revision'],'source9_revision':parent['revision'],'formal_receipt_sha256':digest(path),'source9_receipt_sha256':digest(parent_path),'source9_integrity_sha256':digest(seal_path),'source9_whole_sha256':seal['sha256']})
    assert rows[0]['formal_build_id']!=rows[1]['formal_build_id']and rows[0]['source9_build_id']!=rows[1]['source9_build_id']and rows[0]['source9_revision']==rows[1]['source9_revision']
    if not args.installed_sdk:assert len(set(inodes))==4
    parent=read(parents[0]);seal=read(integrities[0])
    return {'schema':'FINEATLAS_EXTERNAL_ACTUAL_FORMAL_FOUR_STAGE_BINDING_V1','pass':True,'actual_formal_stages':list(FORMAL_STAGES),'source_candidate_stages':list(NOMINAL_STAGES),'physical_historical_inodes_rechecked_here':not args.installed_sdk,'records':rows,'source_database':parent['database'],'source_revision':parent['revision'],'source_database_sha256':seal['sha256'],'source_receipt_sha256':digest(parents[0]),'actual_promotion_metadata_path':str(formal_paths[0].with_name('promotion_metadata.json'))}
