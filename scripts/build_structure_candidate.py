#!/usr/bin/env python3
"""Replay frozen 1.11 structural deltas on a verified, independent 1.10.1 copy."""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from fineatlas.migration import Migration, digest_file
from fineatlas.unified_build import ram_graphs


def freeze_metadata(m):
    c = m.c
    meta = {r[0]: json.loads(r[1]) for r in c.execute('SELECT * FROM metadata')}
    if not meta.get('unified_ready') or not meta.get('usability_indexes_ready'):
        raise ValueError('Full graph recomputation must pass before freezing')
    policies = json.loads((m.inputs / 'reviewed_policies.json').read_text())
    old = json.loads((m.inputs / 'legacy_policies.json').read_text())
    if meta['unified_reward_policies'] != old:
        raise ValueError('Legacy policies changed during replay')
    freeze = {'schema': 'FINEATLAS_STRUCTURE_BUILD_V1',
              'inputs': {str(p.relative_to(m.inputs)): digest_file(p) for p in sorted(m.inputs.rglob('*')) if p.is_file()},
              'code': {str(p.relative_to(ROOT)): digest_file(p) for directory in ('src/fineatlas', 'scripts', 'configs')
                       for p in sorted((ROOT / directory).rglob('*')) if p.is_file() and p.suffix in {'.py', '.json'}},
              'packaging': {'pyproject.toml':digest_file(ROOT/'pyproject.toml')},
              'source_graph_revision': meta['database_revision'],
              'legacy_policies': old, 'reviewed_policies': policies}
    revision = hashlib.sha256(json.dumps(freeze, sort_keys=True).encode()).hexdigest()
    for key, value in {'reviewed_reward_policies': policies,
                       'structure_frozen_build_manifest': freeze,
                       'database_revision': revision, 'browse_parent_revision': revision,
                       'browse_indexes_ready': False, 'baseline_release': 'v1.10.1',
                       'structure_baseline_sha256': json.loads((m.inputs/'baseline.json').read_text())['database_sha256'],
                       'structure_evidence_capture_date': '2026-10-09'}.items():
        m.meta(key, value)
    c.commit()
    return {'revision': revision, 'manifest': freeze}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'database', 'inputs', 'reports', 'browse-staging'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    for key, value in vars(a).items():
        setattr(a, key, value.resolve())
    if a.database == a.baseline or a.database.samefile(a.baseline):
        raise ValueError('Candidate must be an independent, pre-copied baseline')
    a.reports.mkdir(parents=True, exist_ok=True)
    temp = a.database.parent/'tmp'; temp.mkdir(exist_ok=True)
    os.environ.update(TMPDIR=str(temp), SQLITE_TMPDIR=str(temp))
    env = {**os.environ, 'PYTHONHASHSEED':'0', 'PYTHONDONTWRITEBYTECODE':'1', 'PYTHONPATH':str(ROOT/'src')}
    states = {}
    def stage(name, function):
        started = time.monotonic()
        states[name] = {'status':'RUNNING', 'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        status_path = a.reports/'build_status.json'
        status_path.write_text(json.dumps(states, indent=2)+'\n')
        print('START', name, flush=True)
        try:
            result = function()
            states[name].update(status='PASS', result=result)
        except Exception as error:
            states[name].update(status='FAIL', error=str(error))
            raise
        finally:
            states[name]['seconds'] = time.monotonic()-started
            status_path.write_text(json.dumps(states, indent=2)+'\n')
        print('PASS', name, round(states[name]['seconds'], 3), flush=True)
        return result
    frozen = json.loads((a.inputs/'baseline.json').read_text())
    release = json.loads((a.inputs/'review_release.json').read_text())['version']
    if release != 'v1.11.0rc1':
        raise ValueError('This recipe builds only the explicit 1.11.0rc1 candidate')
    def verify_copy():
        digest = digest_file(a.database)
        if digest != frozen['database_sha256'] or a.database.stat().st_size != frozen['database_bytes']:
            raise ValueError('Candidate copy differs from protected baseline')
        with sqlite3.connect(a.baseline.as_uri()+'?mode=ro&immutable=1',uri=True) as c:
            revision = json.loads(c.execute("SELECT value FROM metadata WHERE key='database_revision'").fetchone()[0])
        if revision != frozen['database_revision']:
            raise ValueError('Protected baseline revision differs')
        return {'sha256':digest, 'distinct_inode':True, 'baseline_revision':revision}
    stage('verify_independent_copy', verify_copy)
    m = Migration(a.database, a.inputs, a.reports/'graph-build')
    stage('schema', m.schema)
    from fineatlas.structure_biology import apply_structure_biology
    from fineatlas.structure_engineering import apply_structure_engineering
    from fineatlas.structure_breeds import apply_structure_breeds
    from prepare_living_expansion import apply_living_expansion
    from fineatlas.display_aliases import apply_display_domain_aliases
    for name, function in [('biological_scope',apply_structure_biology),('engineering_scope',apply_structure_engineering),
                           ('breed_sources',apply_structure_breeds),('living_catalogue',apply_living_expansion),
                           ('navigation_names',apply_display_domain_aliases)]:
        stage(name, lambda function=function: function(m))
    stage('whole_graph_recomputation', lambda: ram_graphs(m))
    frozen_meta = stage('freeze_metadata', lambda: freeze_metadata(m))
    (a.reports/'frozen_metadata.json').write_text(json.dumps(frozen_meta,indent=2)+'\n')
    m.c.close()
    def command(name, args):
        with (a.reports/(name+'.log')).open('w') as log:
            subprocess.run([sys.executable,'-B',*args],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        return {'log':str(a.reports/(name+'.log'))}
    stage('browse_staging', lambda:command('browse_staging',[str(ROOT/'scripts/stage_browse_indexes.py'),
          '--source',str(a.database),'--output',str(a.browse_staging),'--reports',str(a.reports/'browse-build'),'--release',release]))
    stage('embed_browse_indexes',lambda:command('embed_browse_indexes',[str(ROOT/'scripts/apply_browse_indexes.py'),
          '--database',str(a.database),'--staging',str(a.browse_staging),'--source-revision',frozen_meta['revision'],
          '--output',str(a.reports/'browse_application.json')]))
    (a.reports/'build_complete.json').write_text(json.dumps({'complete':True,'release':release,
            'revision':frozen_meta['revision'],'database':str(a.database),'requires_independent_acceptance':True},indent=2)+'\n')

if __name__ == '__main__':
    main()
