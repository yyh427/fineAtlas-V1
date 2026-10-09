#!/usr/bin/env python3
"""Promote a fully checked candidate with unchanged semantics; rebuild browse indexes.

Refuses reuse when any graph input, semantic implementation, or original recipe
changes. Never edits the source DB/inputs. Completion is preparation, not final
acceptance: both promoted artifacts still require independent full comparison
and the complete acceptance suite.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(16 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

def read_json(path):
    return json.loads(Path(path).read_text())

def read_metadata(database):
    with sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as c:
        return {key: json.loads(value) for key, value in c.execute('SELECT key,value FROM metadata')}

def files_digest(directory):
    directory = Path(directory)
    return {str(p.relative_to(directory)): digest_file(p) for p in sorted(directory.rglob('*')) if p.is_file()}

def version_only(old, new, expected_version):
    expression = re.compile(rb"(?m)^(__version__[ \t]*=[ \t]*)(['\"])([^'\"\r\n]+)\2([ \t]*)$")
    old_matches, new_matches = list(expression.finditer(old)), list(expression.finditer(new))
    if len(old_matches) != 1 or len(new_matches) != 1:
        raise ValueError('Exactly one literal __version__ assignment required')
    if new_matches[0].group(3).decode() != expected_version.removeprefix('v'):
        raise ValueError('SDK version must exactly match promoted release')
    replacement = lambda m: m.group(1) + m.group(2) + b'VERSION' + m.group(2) + m.group(4)
    if expression.sub(replacement, old) != expression.sub(replacement, new):
        raise ValueError('SDK __init__ changed beyond version literal; full rebuild required')

def validate_reuse(meta, source_code, source_inputs, code, inputs):
    source_code, source_inputs, code, inputs = map(Path, (source_code, source_inputs, code, inputs))
    for flag in ('unified_ready', 'usability_indexes_ready', 'browse_indexes_ready'):
        if meta.get(flag) is not True:
            raise ValueError('Source is not a complete candidate: ' + flag)
    if meta.get('database_revision') != meta.get('browse_index_revision'):
        raise ValueError('Source browse revision mismatch')
    freeze = meta['unified_frozen_build_manifest']
    if meta.get('browse_parent_revision') != canonical_hash(freeze):
        raise ValueError('Frozen manifest does not reproduce source parent revision')
    if meta.get('browse_source_revision') != meta['browse_parent_revision']:
        raise ValueError('Source browse parent/source mismatch')
    if freeze['source_graph_revision'] != meta['unified_source_graph_revision']:
        raise ValueError('Source graph revision does not match frozen manifest')
    if freeze['policy_sha256'] != meta['unified_policy_sha256'] or canonical_hash(meta['unified_policy_definition']) != freeze['policy_sha256']:
        raise ValueError('Source policy fingerprint mismatch')
    old_inputs, new_inputs = files_digest(source_inputs), files_digest(inputs)
    if old_inputs != freeze['inputs'] or set(new_inputs) != set(old_inputs):
        raise ValueError('Frozen input inventory/hash mismatch')
    changed = {name for name in old_inputs if old_inputs[name] != new_inputs[name]}
    if changed != {'review_release.json'}:
        raise ValueError('Only review_release.json may change; full rebuild otherwise')
    old_release, new_release = read_json(source_inputs/'review_release.json'), read_json(inputs/'review_release.json')
    release = new_release['version']
    if not re.fullmatch(r'v1\.10\.\d+', release):
        raise ValueError('Expected stable v1.10.x release, no candidate suffix')
    if old_release['version'] != meta['release'] or old_release | {'version': release} != new_release:
        raise ValueError('Only review_release.version may change')
    old_code = {str(p.relative_to(source_code)): digest_file(p) for p in sorted((source_code/'src/fineatlas').glob('*.py'))}
    new_code = {str(p.relative_to(code)): digest_file(p) for p in sorted((code/'src/fineatlas').glob('*.py'))}
    if old_code != freeze['code'] or set(new_code) != set(old_code):
        raise ValueError('Frozen SDK inventory/hash mismatch')
    if any(new_code[name] != old_code[name] for name in old_code if name != 'src/fineatlas/__init__.py'):
        raise ValueError('Semantic SDK implementation changed; full rebuild required')
    version_only((source_code/'src/fineatlas/__init__.py').read_bytes(), (code/'src/fineatlas/__init__.py').read_bytes(), release)
    for name, sha in freeze['build_scripts'].items():
        if digest_file(source_code/name) != sha or digest_file(code/name) != sha:
            raise ValueError('Original build recipe changed; full rebuild required: ' + name)
    scripts = dict(freeze['build_scripts'])
    scripts['scripts/promote_stable_candidate.py'] = digest_file(code/'scripts/promote_stable_candidate.py')
    promotion = {'schema': 'FINEATLAS_STABLE_GRAPH_REUSE_V1', 'parent_candidate_revision': meta['database_revision'],
                 'parent_frozen_manifest_sha256': canonical_hash(freeze),
                 'parent_release': meta['release'], 'semantic_graph_recomputed': False,
                 'allowed_deltas': ['review_release.version', 'SDK __version__ literal'],
                 'browse_indexes_rebuilt': True}
    new_freeze = {'inputs': new_inputs, 'code': new_code,
                  'source_graph_revision': freeze['source_graph_revision'], 'policy_sha256': freeze['policy_sha256'],
                  'build_scripts': scripts, 'promotion': promotion,
                  'packaging': {'pyproject.toml': digest_file(code/'pyproject.toml')}}
    return {'release': release, 'revision': canonical_hash(new_freeze), 'manifest': new_freeze}

def validate_evidence(meta, source, integrity, comparison, acceptance):
    if not integrity.get('complete') or not integrity.get('all_pass'):
        raise ValueError('Source integrity proof not complete/PASS')
    if not all(comparison.get(k) is True for k in ('complete','pass','artifact_hashes_bound','final_view_statistics_pass')) or comparison.get('exit_code') != 0 or comparison.get('logical_table_count') != 105:
        raise ValueError('Independent full source comparison not complete/PASS')
    if not acceptance.get('all_pass') or not acceptance.get('ended_utc') or not acceptance.get('candidate_unchanged') or not acceptance.get('inputs_unchanged'):
        raise ValueError('Acceptance receipt is not complete and bound')
    required_jobs={'domains','labels','structure','preservation','nonfocus','browse','contracts','cycles','witnesses','cli','same-policy','global-contracts','usability','living-focused','repair-focus','self-reward'}
    if set(acceptance.get('jobs', {})) != required_jobs or any(row.get('exit_code') != 0 or row.get('verdict',{}).get('pass') is not True or not row.get('ended_utc') for row in acceptance['jobs'].values()):
        raise ValueError('Source acceptance jobs not complete/PASS')
    primary = integrity['artifacts']['primary']
    if acceptance['database_sha256'] != primary['sha256'] or acceptance['database_revision'] != primary['database_revision']:
        raise ValueError('Acceptance is not bound to the independently compared primary')
    selected = None
    for name in ('primary', 'reproduction'):
        row = integrity['artifacts'][name]
        pair = comparison[name]
        if pair['database_sha256'] != row['sha256'] or pair['database_revision'] != row['database_revision']:
            raise ValueError('Comparison and integrity artifact bindings differ')
        if row['database_revision'] != acceptance['database_revision'] or not row.get('pass') or row.get('integrity_check') != ['ok'] or not row.get('file_unchanged_during_checks'):
            raise ValueError('Invalid independently checked source artifact')
        if Path(row['database']).resolve() == Path(source).resolve():
            selected = row
    if selected is None or selected['database_revision'] != meta['database_revision']:
        raise ValueError('Source path/revision is not one of checked independent artifacts')
    return selected

def freeze_promoted_metadata(database, result):
    # Deliberately touches only metadata. Source records, roles, identities,
    # policy contracts, four semantic graphs and WordNet usage stay untouched.
    with sqlite3.connect(database) as c:
        for key, value in {'release': result['release'], 'review_version': result['release'], 'database_revision': result['revision'],
                           'unified_frozen_build_manifest': result['manifest'],
                           'browse_parent_revision': result['revision'], 'browse_indexes_ready': False}.items():
            c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', (key,json.dumps(value)))

def validate_paths(source, database, staging):
    if database.exists() or staging.exists():
        raise ValueError('Refusing to overwrite output candidate/staging')
    if len({source.resolve(), database.resolve(), staging.resolve()}) != 3:
        raise ValueError('Source/output/staging must be distinct')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source','source-code','source-inputs','inputs','database','browse-staging','reports','integrity','comparison-completion','acceptance'):
        p.add_argument('--'+name, type=Path, required=True)
    a=p.parse_args()
    for name,value in vars(a).items():setattr(a,name,value.resolve())
    validate_paths(a.source,a.database,a.browse_staging)
    a.reports.mkdir(parents=True,exist_ok=True)
    a.database.parent.mkdir(parents=True,exist_ok=True);a.browse_staging.parent.mkdir(parents=True,exist_ok=True)
    temporary=a.database.parent/'tmp';temporary.mkdir(exist_ok=True)
    env={**os.environ,'PYTHONHASHSEED':'0','PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(temporary),'SQLITE_TMPDIR':str(temporary),'PYTHONPATH':str(ROOT/'src')}
    status={};started=time.monotonic();begin=datetime.datetime.now(datetime.timezone.utc).isoformat()
    def stage(name,function=None,command=None):
        start=time.monotonic();row={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'RUNNING'}
        status[name]=row
        def save(): (a.reports/'promotion_status.json').write_text(json.dumps(status,indent=2)+'\n')
        save();print('START',name,flush=True)
        try:
            if function:row['result']=function()
            else:
                row['command']=command
                with (a.reports/(name+'.log')).open('w') as log:
                    row['exit_code']=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
                if row['exit_code']:raise RuntimeError(name+' failed')
            row['status']='PASS'
        except Exception as error:row['status']='FAIL';row['error']=str(error);raise
        finally:
            row['seconds']=time.monotonic()-start;row['completed_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
        print('PASS',name,row['seconds'],flush=True)
        return row.get('result')
    original_stat=a.source.stat()
    def verify():
        meta=read_metadata(a.source)
        result=validate_reuse(meta,a.source_code,a.source_inputs,ROOT,a.inputs)
        source=validate_evidence(meta,a.source,read_json(a.integrity),read_json(a.comparison_completion),read_json(a.acceptance))
        if a.source.stat().st_size != source['bytes_scanned'] or digest_file(a.source) != source['sha256']:
            raise ValueError('Source byte size/SHA differs from verified artifact')
        return {'freeze':result,'source_sha256':source['sha256'],'source_revision':meta['database_revision']}
    verified=stage('source_verification',function=verify)
    stage('independent_source_copy',command=['cp','--reflink=auto','--sparse=always','--',str(a.source),str(a.database)])
    def copy_check():
        if a.database.samefile(a.source) or digest_file(a.database) != verified['source_sha256']:
            raise ValueError('Copy bytes/inode do not preserve source')
        return {'distinct_inode':True,'sha256':verified['source_sha256']}
    stage('copy_verification',function=copy_check)
    def freeze_check():
        if validate_reuse(read_metadata(a.source),a.source_code,a.source_inputs,ROOT,a.inputs) != verified['freeze']:
            raise ValueError('Promotion code/inputs changed after verification')
        freeze_promoted_metadata(a.database,verified['freeze'])
    stage('freeze_promoted_metadata',function=freeze_check)
    (a.reports/'frozen_metadata.json').write_text(json.dumps(verified['freeze'],indent=2)+'\n')
    py=[sys.executable,'-B']
    stage('browse_staging',command=py+[str(ROOT/'scripts/stage_browse_indexes.py'),'--source',str(a.database),'--output',str(a.browse_staging),'--reports',str(a.reports/'browse-build'),'--release',verified['freeze']['release']])
    stage('embed_browse_indexes',command=py+[str(ROOT/'scripts/apply_browse_indexes.py'),'--database',str(a.database),'--staging',str(a.browse_staging),'--source-revision',verified['freeze']['revision'],'--output',str(a.reports/'browse_application.json')])
    current=a.source.stat()
    if (original_stat.st_ino,original_stat.st_size,original_stat.st_mtime_ns,original_stat.st_ctime_ns)!=(current.st_ino,current.st_size,current.st_mtime_ns,current.st_ctime_ns):
        raise ValueError('Source artifact changed during promotion')
    if validate_reuse(read_metadata(a.source),a.source_code,a.source_inputs,ROOT,a.inputs) != verified['freeze']:
        raise ValueError('Promotion code/inputs changed while building indexes')
    final=read_metadata(a.database)
    if final['release']!=verified['freeze']['release'] or not final.get('browse_indexes_ready') or final['database_revision']!=final['browse_index_revision']:
        raise ValueError('Promoted browse metadata not ready/matching')
    (a.reports/'promotion_complete.json').write_text(json.dumps({'complete':True,'pass':True,'started_utc':begin,'ended_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'seconds':time.monotonic()-started,'source':str(a.source),'database':str(a.database),'source_sha256':verified['source_sha256'],'source_revision':verified['source_revision'],'database_revision':final['database_revision'],'release':final['release'],'source_unchanged':True,'semantic_graph_recomputed':False,'browse_indexes_rebuilt':True,'requires_independent_105_table_schema_comparison':True,'requires_separate_complete_16_job_acceptance':True,'requires_source_record_preservation_proof':True},indent=2)+'\n')

if __name__=='__main__':main()
