#!/usr/bin/env python3
"""Prepare a stable structural artifact from a public-verified candidate.

Reuse requires unchanged source facts, graph semantics and recipes. The SDK
version and release input are the only allowed implementation/input deltas.
Public acceptance and full independent comparison are prerequisites; the
new artifact still needs fresh full acceptance and public-download verification.
"""
from __future__ import annotations

if not __debug__:
    raise RuntimeError("Optimized Python is forbidden for mandatory structural checks")

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
# A private empty cache prevents valid timestamp-based stale .pyc reads.
_import_cache=Path(os.environ.get('TMPDIR',str(ROOT.parent/'tmp')))/('fineatlas-import-'+uuid.uuid4().hex)
_import_cache.mkdir(parents=True,exist_ok=False)
sys.pycache_prefix=str(_import_cache)
sys.path.insert(0, str(ROOT/'scripts'))
from structure_build_safety import require_unoptimized, inventory_code, protect_output
require_unoptimized()
PRE_IMPORT_INVENTORY=inventory_code(ROOT)
from build_structure_candidate import build_fingerprints
from promote_stable_candidate import (canonical_hash, digest_file, files_digest,
                                      read_metadata, version_only)
from structure_acceptance_contract import (validate_completed_acceptance,
    validate_comparison_inventory, validate_public_evidence, file_sha256)


def validate_structure_reuse(meta, source_code, source_inputs, code, inputs):
    for flag in ('unified_ready', 'usability_indexes_ready', 'browse_indexes_ready'):
        if meta.get(flag) is not True:
            raise ValueError('Candidate incomplete: '+flag)
    freeze = meta['structure_frozen_build_manifest']
    if meta['browse_parent_revision'] != canonical_hash(freeze) or meta['database_revision'] != meta['browse_index_revision']:
        raise ValueError('Frozen semantic/browse revision mismatch')
    old_inputs, new_inputs = files_digest(source_inputs), files_digest(inputs)
    if old_inputs != freeze['inputs'] or set(new_inputs) != set(old_inputs):
        raise ValueError('Frozen input inventory/hash mismatch')
    if {k for k in old_inputs if old_inputs[k] != new_inputs[k]} != {'review_release.json'}:
        raise ValueError('Only the release input version may change')
    old_release = json.loads((source_inputs/'review_release.json').read_text())
    new_release = json.loads((inputs/'review_release.json').read_text())
    release = new_release['version']
    if not re.fullmatch(r'v1\.11\.\d+', release) or old_release['version'] != meta['release'] or old_release | {'version': release} != new_release:
        raise ValueError('Only candidate to stable 1.11 release version may change')
    def inventory(base):
        return {str(p.relative_to(base)): digest_file(p) for directory in ('src/fineatlas','scripts','configs')
                for p in sorted((base/directory).rglob('*')) if p.is_file() and p.suffix in {'.py','.json'}}
    old_code, new_code = inventory(source_code), inventory(code)
    if old_code != freeze['code'] or set(new_code) != set(old_code):
        raise ValueError('Frozen complete SDK/recipe/config inventory mismatch')
    if {name for name in new_code if new_code[name] != old_code[name]} != {'src/fineatlas/__init__.py'}:
        raise ValueError('Only the literal SDK version may change; full rebuild otherwise')
    version_only((source_code/'src/fineatlas/__init__.py').read_bytes(),
                 (code/'src/fineatlas/__init__.py').read_bytes(), release)
    if freeze['packaging']['pyproject.toml'] != digest_file(source_code/'pyproject.toml'):
        raise ValueError('Original packaging fingerprint drift')
    old_package = (source_code/'pyproject.toml').read_text()
    new_package = (code/'pyproject.toml').read_text()
    pattern = re.compile(r'(?m)^version\s*=\s*"([^"\n]+)"$')
    if len(pattern.findall(old_package)) != 1 or pattern.findall(new_package) != [release[1:]] or pattern.sub('version = "VERSION"',old_package) != pattern.sub('version = "VERSION"',new_package):
        raise ValueError('Only the packaging version literal may change')
    stable = {**freeze, 'inputs': new_inputs, 'code': new_code,
              'packaging': {'pyproject.toml': digest_file(code/'pyproject.toml')},
              'promotion': {'schema':'FINEATLAS_STRUCTURE_STABLE_REUSE_V1',
                            'parent_candidate_revision': meta['database_revision'],
                            'parent_frozen_manifest_sha256': canonical_hash(freeze),
                            'parent_release': meta['release'], 'semantic_graph_recomputed': False,
                            'allowed_deltas': ['review_release.version','SDK __version__ literal','packaging version literal'],
                            'browse_indexes_rebuilt': True}}
    return {'release':release,'manifest':stable,'revision':canonical_hash(stable)}


def validate_source_evidence(meta, source, acceptance, comparison, public, public_path=None):
    validate_completed_acceptance(acceptance)
    if not comparison.get('complete') or not comparison.get('pass') or comparison.get('exit_code') != 0:
        raise ValueError('Independent full logical comparison incomplete')
    if not comparison.get('schema_inventory_pass') or not comparison.get('schema_objects_pass') or not comparison.get('final_view_statistics_pass') or not comparison.get('all_logical_tables_pass'):
        raise ValueError('Independent complete graph/schema/source comparison failed')
    validate_comparison_inventory(comparison)
    raw_path=Path(comparison.get('comparison_report','')).resolve(strict=True)
    if file_sha256(raw_path)!=comparison.get('comparison_report_sha256'):
        raise ValueError('Actual logical comparison report/hash required')
    raw=json.loads(raw_path.read_text())
    if not raw or any(row.get('pass') is not True for row in raw.values()):
        raise ValueError('Full actual comparison rows must pass')
    content=raw.get('content_inventory',{})
    for key in ('compared_content_tables','excluded_content_tables'):
        if content.get(key)!=comparison.get(key):raise ValueError('Comparison content inventory binding mismatch')
    builds=comparison.get('independent_builds',[])
    if len(builds)!=2 or builds[0].get('build_id')==builds[1].get('build_id'):
        raise ValueError('Two actual independently rebuilt artifacts required')
    for row in builds:
        if file_sha256(Path(row['receipt_path']))!=row.get('receipt_sha256'):
            raise ValueError('Independent build receipt changed')
    if public_path is None:raise ValueError('Actual public verification file is required')
    public_sha=validate_public_evidence(public,acceptance,public_path)
    job=acceptance['jobs']['public-install']
    if Path(job.get('verification_file','')).resolve()!=public_path.resolve() or job.get('verification_file_sha256')!=public_sha:
        raise ValueError('Acceptance public evidence file/hash mismatch')
    if job.get('release')!=meta['release'] or job.get('database_revision')!=meta['database_revision'] or public.get('release')!=meta['release']:
        raise ValueError('Public release/revision mismatch')
    artifacts = comparison.get('artifacts',{})
    matches = [row for row in artifacts.values() if Path(row['database']).resolve() == source]
    if len(matches) != 1:
        raise ValueError('Source is not one of the independently compared artifacts')
    selected = matches[0]
    primary_path=Path(artifacts['primary']['database']);reproduction_path=Path(artifacts['reproduction']['database'])
    if primary_path.samefile(reproduction_path):raise ValueError('Independent artifacts share an inode')
    with sqlite3.connect(source.as_uri()+'?mode=ro&immutable=1',uri=True) as check:
        actual=[r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*' ORDER BY name")]
    if actual!=selected['logical_table_inventory'] or len(actual)!=comparison['logical_table_count']:
        raise ValueError('Actual source table inventory differs from comparison')
    if selected.get('database_revision') != meta['database_revision'] or acceptance['database_revision'] != meta['database_revision']:
        raise ValueError('Source acceptance/comparison revision mismatch')
    if not selected.get('integrity_pass') or not selected.get('file_unchanged_during_checks'):
        raise ValueError('Source integrity/hash proof missing')
    primary = artifacts.get('primary',{})
    if primary.get('sha256') != acceptance['database_sha256']:
        raise ValueError('Acceptance does not bind compared primary')
    return selected


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','source-code','source-inputs','inputs','database','reports',
                 'browse-staging','acceptance','comparison','public-verification'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    for key,value in vars(a).items():
        setattr(a,key,value.resolve())
    if inventory_code(ROOT)!=PRE_IMPORT_INVENTORY:raise ValueError('Promotion code changed after import')
    a.reports.mkdir(parents=True,exist_ok=True)
    fingerprints=build_fingerprints(a.inputs)
    if {k:fingerprints[k] for k in ('code','packaging')}!=PRE_IMPORT_INVENTORY:raise ValueError('Promotion loaded code differs from inventory')
    (a.reports/'started_fingerprints.json').write_text(json.dumps(fingerprints,indent=2)+'\n')
    build_id=str(uuid.uuid4());started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
    states={}
    def record(name, result):
        states[name]={'status':'PASS','result':result}
        (a.reports/'build_status.json').write_text(json.dumps(states,indent=2)+'\n')
    accepted_comparison=json.loads(a.comparison.read_text())
    protect_output(a.database,a.inputs,additional_protected=[a.source,*[Path(row['database']) for row in accepted_comparison.get('artifacts',{}).values()]])
    if a.database.samefile(a.source):
        raise ValueError('Stable artifact must be an independent pre-copied file')
    a.reports.mkdir(parents=True,exist_ok=True)
    temp=a.database.parent/'tmp';temp.mkdir(exist_ok=True)
    os.environ.update(TMPDIR=str(temp),SQLITE_TMPDIR=str(temp))
    start=time.monotonic()
    meta=read_metadata(a.source)
    selected=validate_source_evidence(meta,a.source,json.loads(a.acceptance.read_text()),
              accepted_comparison,json.loads(a.public_verification.read_text()),a.public_verification)
    source_sha=digest_file(a.source)
    if source_sha != selected['sha256'] or a.source.stat().st_size != selected['bytes'] or digest_file(a.database) != source_sha:
        raise ValueError('Full source or independent copy SHA/size mismatch')
    result=validate_structure_reuse(meta,a.source_code,a.source_inputs,ROOT,a.inputs)
    record('verified_version_only_semantic_reuse',{'parent_revision':meta['database_revision'],'source_sha256':source_sha,'graphs_recomputed':False})
    with sqlite3.connect(a.database) as c:
        for key,value in {'release':result['release'],'review_version':result['release'],
                          'structure_frozen_build_manifest':result['manifest'],
                          'database_revision':result['revision'],'browse_parent_revision':result['revision'],
                          'browse_indexes_ready':False}.items():
            c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(key,json.dumps(value,sort_keys=True)))
    (a.reports/'promotion_metadata.json').write_text(json.dumps(result,indent=2)+'\n')
    env={**os.environ,'PYTHONPATH':str(ROOT/'src'),'PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0'}
    env.pop('PYTHONOPTIMIZE',None)
    env['PYTHONPYCACHEPREFIX']=sys.pycache_prefix
    commands=[('browse_staging',[str(ROOT/'scripts/stage_browse_indexes.py'),'--source',str(a.database),
                '--output',str(a.browse_staging),'--reports',str(a.reports/'browse-build'),'--release',result['release']]),
              ('embed_browse_indexes',[str(ROOT/'scripts/apply_browse_indexes.py'),'--database',str(a.database),
                '--staging',str(a.browse_staging),'--source-revision',result['revision'],
                '--output',str(a.reports/'browse_application.json')])]
    for name,command in commands:
        print('START',name,flush=True)
        with (a.reports/(name+'.log')).open('w') as log:
            subprocess.run([sys.executable,'-B',*command],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        record(name,{'log':str(a.reports/(name+'.log'))})
        print('PASS',name,flush=True)
    if inventory_code(ROOT)!=PRE_IMPORT_INVENTORY:raise ValueError('Loaded promotion code changed')
    if validate_structure_reuse(meta,a.source_code,a.source_inputs,ROOT,a.inputs) != result:
        raise ValueError('Code or inputs changed during promotion')
    if digest_file(a.source) != source_sha:
        raise ValueError('Original candidate changed during promotion')
    final=read_metadata(a.database)
    if not final.get('browse_indexes_ready') or final['database_revision'] != final['browse_index_revision']:
        raise ValueError('Stable browse artifact incomplete')
    if build_fingerprints(a.inputs)!=fingerprints:raise ValueError('Code or frozen inputs changed during promotion')
    record('final_bound_source_and_cache_checks',{'source_unchanged':True,'revision':final['database_revision']})
    (a.reports/'build_complete.json').write_text(json.dumps({
       'schema':'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1','complete':True,'pass':True,
       'build_id':build_id,'pid':os.getpid(),'started_utc':started_utc,
       'ended_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'release':result['release'],'revision':final['database_revision'],'database':str(a.database),
       'started_fingerprints_sha256':digest_file(a.reports/'started_fingerprints.json'),
       'build_status_sha256':digest_file(a.reports/'build_status.json'),
       'semantic_reuse_only':True,'requires_independent_acceptance':True},indent=2)+'\n')
    (a.reports/'promotion_complete.json').write_text(json.dumps({'complete':True,'pass':True,
       'release':result['release'],'database':str(a.database),'database_revision':final['database_revision'],
       'source_sha256':source_sha,'source_unchanged':True,'seconds':time.monotonic()-start,
       'requires_full_new_acceptance_and_public_download':True,
       'ended_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2)+'\n')


if __name__=='__main__':main()
