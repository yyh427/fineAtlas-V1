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
import uuid
ROOT = Path(__file__).resolve().parents[1]
# A private empty cache prevents valid timestamp-based stale .pyc reads.
_import_cache=Path(os.environ.get('TMPDIR',str(ROOT.parent/'tmp')))/('fineatlas-import-'+uuid.uuid4().hex)
_import_cache.mkdir(parents=True,exist_ok=False)
sys.pycache_prefix=str(_import_cache)
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from structure_build_safety import inventory_code, protect_output, require_unoptimized
require_unoptimized()
PREIMPORT_CODE_INVENTORY = inventory_code(ROOT)
from fineatlas.migration import Migration, digest_file
from fineatlas.unified_build import ram_graphs
if inventory_code(ROOT) != PREIMPORT_CODE_INVENTORY:
    raise ValueError('Code changed while SDK/build modules were imported')

BUILD_STAGES = ('verify_independent_copy', 'schema', 'biological_scope',
                'engineering_scope', 'breed_sources', 'living_catalogue',
                'navigation_names', 'biological_whole_definition_scope',
                'candidate_evidence_dates', 'whole_subject_source_contracts',
                'whole_graph_recomputation', 'freeze_metadata', 'browse_staging',
                'embed_browse_indexes')


def build_fingerprints(inputs):
    return {'inputs': {str(p.relative_to(inputs)): digest_file(p) for p in sorted(inputs.rglob('*')) if p.is_file()},
            **inventory_code(ROOT)}


def require_stable_build(inputs, expected):
    current = build_fingerprints(inputs)
    if {key: current[key] for key in ('code', 'packaging')} != PREIMPORT_CODE_INVENTORY:
        raise ValueError('Current files differ from the inventory captured before SDK import')
    if current != expected:
        raise ValueError('Code or frozen inputs changed during structural construction')


def start_build(inputs, reports):
    require_unoptimized()
    fingerprints = build_fingerprints(inputs)
    require_stable_build(inputs, fingerprints)
    if (reports/'build_complete.json').exists():
        raise ValueError('Use a fresh report directory; a prior completion receipt already exists')
    reports.mkdir(parents=True, exist_ok=True)
    started = reports/'started_fingerprints.json'
    started.write_text(json.dumps(fingerprints, indent=2)+'\n')
    return fingerprints, {'build_id': str(uuid.uuid4()), 'pid': os.getpid(),
                          'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                          'started_fingerprints_sha256': digest_file(started)}


def final_artifact_binding(database, release, source_graph_revision):
    with sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1', uri=True) as c:
        actual = {key: json.loads(value) for key, value in c.execute('SELECT * FROM metadata')}
    revision = actual.get('database_revision')
    if not isinstance(revision, str) or not revision or actual.get('release') != release:
        raise ValueError('Completion must bind the actual database release and revision')
    ready = {key: actual.get(key) for key in ('unified_ready', 'usability_indexes_ready', 'browse_indexes_ready')}
    if any(value is not True for value in ready.values()):
        raise ValueError('All graph and browse caches must actually be ready')
    cache = {key: actual.get(key) for key in ('browse_parent_revision', 'browse_source_revision', 'browse_index_revision')}
    if not source_graph_revision or cache['browse_parent_revision'] != source_graph_revision or cache['browse_source_revision'] != source_graph_revision or cache['browse_index_revision'] != revision:
        raise ValueError('Final browse revision must bind the actual frozen source graph and index')
    return {'revision': revision, 'source_graph_revision': source_graph_revision,
            'readiness': ready, 'cache_bindings': cache}


def write_build_complete(reports, database, release, revision, context, states, required_stages,
                         source_graph_revision):
    if set(states) != set(required_stages) or any(states[name].get('status') != 'PASS' for name in required_stages):
        raise ValueError('Every required build stage must actually pass before completion')
    status_path = reports/'build_status.json'
    if json.loads(status_path.read_text()) != states:
        raise ValueError('Persisted build stage states differ from the actual run')
    if digest_file(reports/'started_fingerprints.json') != context['started_fingerprints_sha256']:
        raise ValueError('Started fingerprint receipt changed during construction')
    binding = final_artifact_binding(database, release, source_graph_revision)
    if binding['revision'] != revision:
        raise ValueError('Completion must bind the actual database release and revision')
    receipt = {'schema': 'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1', **context,
               'ended_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'complete': True, 'pass': True, 'release': release, **binding,
               'database': str(database.resolve(strict=True)),
               'build_status_sha256': digest_file(status_path), 'required_stages': list(required_stages),
               'requires_independent_acceptance': True}
    with (reports/'build_complete.json').open('x') as output:
        output.write(json.dumps(receipt, indent=2)+'\n')
    return receipt


def freeze_metadata(m, expected_fingerprints=None):
    c = m.c
    meta = {r[0]: json.loads(r[1]) for r in c.execute('SELECT * FROM metadata')}
    if not meta.get('unified_ready') or not meta.get('usability_indexes_ready'):
        raise ValueError('Full graph recomputation must pass before freezing')
    policies = json.loads((m.inputs / 'reviewed_policies.json').read_text())
    resolution_path=m.inputs/'reviewed_resolution_policies.json'
    resolved=json.loads(resolution_path.read_text()) if resolution_path.exists() else policies
    old = json.loads((m.inputs / 'legacy_policies.json').read_text())
    if meta['unified_reward_policies'] != old:
        raise ValueError('Legacy policies changed during replay')
    fingerprints = build_fingerprints(m.inputs)
    if expected_fingerprints is not None and fingerprints != expected_fingerprints:
        raise ValueError('Code or frozen inputs changed during source/graph construction')
    freeze = {'schema': 'FINEATLAS_STRUCTURE_BUILD_V1', **fingerprints,
              'source_graph_revision': meta['database_revision'],
              'legacy_policies': old, 'reviewed_policies': policies,
              'resolution_policies': resolved}
    revision = hashlib.sha256(json.dumps(freeze, sort_keys=True).encode()).hexdigest()
    for key, value in {'reviewed_reward_policies': resolved,
                       'reviewed_reward_policies_v1': policies,
                       'reviewed_resolution_policy_version': 'native-taxonomic-rank-floors-v2' if resolution_path.exists() else 'v1',
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
    fingerprints, context = start_build(a.inputs, a.reports)
    temp = a.database.parent/'tmp'; temp.mkdir(exist_ok=True)
    os.environ.update(TMPDIR=str(temp), SQLITE_TMPDIR=str(temp))
    env = {**os.environ, 'PYTHONHASHSEED':'0', 'PYTHONDONTWRITEBYTECODE':'1', 'PYTHONPATH':str(ROOT/'src')}
    env.pop('PYTHONOPTIMIZE', None)
    env['PYTHONPYCACHEPREFIX']=sys.pycache_prefix
    states = {}
    def stage(name, function):
        started = time.monotonic()
        states[name] = {'status':'RUNNING', 'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        status_path = a.reports/'build_status.json'
        status_path.write_text(json.dumps(states, indent=2)+'\n')
        print('START', name, flush=True)
        try:
            require_stable_build(a.inputs, fingerprints)
            result = function()
            require_stable_build(a.inputs, fingerprints)
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
        protection = protect_output(a.database, a.inputs, a.baseline)
        digest = digest_file(a.database)
        if digest != frozen['database_sha256'] or a.database.stat().st_size != frozen['database_bytes']:
            raise ValueError('Candidate copy differs from protected baseline')
        with sqlite3.connect(a.baseline.as_uri()+'?mode=ro&immutable=1',uri=True) as c:
            revision = json.loads(c.execute("SELECT value FROM metadata WHERE key='database_revision'").fetchone()[0])
        if revision != frozen['database_revision']:
            raise ValueError('Protected baseline revision differs')
        return {'sha256':digest, 'distinct_inode':True, 'baseline_revision':revision, 'protection':protection}
    stage('verify_independent_copy', verify_copy)
    m = Migration(a.database, a.inputs, a.reports/'graph-build')
    stage('schema', m.schema)
    # Replay the already frozen source-stage history exactly; the separately
    # frozen correction below removes these legacy placeholders before release.
    m.legacy_evidence_fallback='2026-10-05'
    from fineatlas.structure_biology import apply_structure_biology
    from fineatlas.structure_engineering import apply_structure_engineering
    from fineatlas.structure_breeds import apply_structure_breeds
    from prepare_living_expansion import apply_living_expansion
    from fineatlas.display_aliases import apply_display_domain_aliases
    for name, function in [('biological_scope',apply_structure_biology),('engineering_scope',apply_structure_engineering),
                           ('breed_sources',apply_structure_breeds),('living_catalogue',apply_living_expansion),
                           ('navigation_names',apply_display_domain_aliases)]:
        stage(name, lambda function=function: function(m))
    m.legacy_evidence_fallback=None
    from fineatlas.structure_biology_scope import apply_structure_biology_scope
    stage('biological_whole_definition_scope',lambda:apply_structure_biology_scope(m))
    from fineatlas.evidence_dates import apply_evidence_dates
    from fineatlas.structure_source_contracts import apply_source_contracts
    stage('candidate_evidence_dates',lambda:apply_evidence_dates(m))
    stage('whole_subject_source_contracts',lambda:apply_source_contracts(m))
    stage('whole_graph_recomputation', lambda: ram_graphs(m))
    frozen_meta = stage('freeze_metadata', lambda: freeze_metadata(m, fingerprints))
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
    require_stable_build(a.inputs, fingerprints)
    binding = final_artifact_binding(a.database, release, frozen_meta['revision'])
    write_build_complete(a.reports, a.database, release, binding['revision'], context, states, BUILD_STAGES,
                         source_graph_revision=frozen_meta['revision'])

if __name__ == '__main__':
    main()
