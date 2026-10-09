#!/usr/bin/env python3
"""Run pinned, semantic acceptance of a completed repair artifact; never build it.

Reports are fresh unless --resume is explicit. Preservation uses the source
baseline; browser comparison uses the old recommended browse baseline. A pass
certifies these structural/source/interface contracts, not every identity,
legacy source taxonomy, annotation scope, visual metric or external download.
"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from math import comb
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {'cub200':200, 'fgvc_aircraft':100, 'flowers102':102,
            'pets37':37, 'stanford_dogs':120, 'stanford_cars':196}
VIEWS = {'strict', 'taxonomy', 'membership', 'unified'}
PAIR_STATUSES = {'APPLICABLE', 'ENDPOINT_NOT_APPLICABLE',
                 'IDENTITY_LINEAGE_ROLE_CONFLICT', 'CYCLIC_LINEAGE',
                 'NO_COMMON_ANCESTOR', 'COARSE_COMMON_ANCESTOR_ONLY'}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def code_hash():
    files = sorted([*ROOT.joinpath('src').rglob('*.py'), *ROOT.joinpath('scripts').glob('*.py')])
    return hashlib.sha256(json.dumps([(str(x.relative_to(ROOT)), sha(x)) for x in files]).encode()).hexdigest()


def result_hashes(output):
    return {str(x.relative_to(output)): sha(x) for x in output.rglob('*')
            if x.is_file() and x.suffix in ('.json', '.jsonl')}


def load(path):
    with Path(path).open() as stream:
        return json.load(stream)


def write(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def snapshot(path):
    path = Path(path).resolve()
    stat = path.stat()
    require(path.is_file(), 'Database is not a file')
    for suffix in ('-wal', '-journal'):
        sidecar = Path(str(path) + suffix)
        require(not sidecar.exists() or sidecar.stat().st_size == 0,
                'Database has a live/nonempty SQLite sidecar: ' + str(sidecar))
    with sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True) as con:
        metadata = {k: json.loads(v) for k, v in con.execute('SELECT key,value FROM metadata')}
    return {'path': str(path), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'device': stat.st_dev, 'inode': stat.st_ino, 'metadata': metadata}


def readiness(snap, expected_release):
    m = snap['metadata']
    require(m.get('release') == expected_release, 'Unexpected release')
    require(bool(m.get('database_revision')), 'Missing database revision')
    for key in ('unified_ready', 'usability_indexes_ready', 'browse_indexes_ready'):
        require(m.get(key) is True, key + ' must be true')
    require(m.get('default_relation_view') == 'unified', 'Default relation view must be unified')
    require(set(m.get('supported_relation_views', [])) == VIEWS, 'Missing relation view')
    require(m.get('browse_index_revision') == m['database_revision'], 'Stale browse index')
    require(bool(m.get('browse_parent_revision')), 'Missing browse parent revision')


def validate_pair(pair, revision, view, dataset, ids):
    require(pair.get('dataset') == dataset, 'Pair dataset mismatch')
    require(pair.get('database_revision') == revision and pair.get('relation_view') == view,
            'Pair revision/view mismatch')
    left, right = str(pair.get('left')), str(pair.get('right'))
    require(left in ids and right in ids, 'Unknown pair label')
    status = pair.get('status')
    require(status in PAIR_STATUSES, 'Unknown/non-supported pair status')
    if status == 'APPLICABLE':
        distance = pair.get('distance')
        require(pair.get('applicable') is True and type(distance) is int and distance >= 0,
                'Applicable pair has invalid reward/distance')
        require(bool(pair.get('lcas')), 'Applicable pair lacks evidence-backed LCA')
    else:
        require(pair.get('applicable') is False and pair.get('distance') is None,
                'Nonapplicable pair must have false reward mask/null distance')
    if status == 'ENDPOINT_NOT_APPLICABLE':
        reasons = pair.get('reasons')
        require(isinstance(reasons, dict) and reasons and set(reasons) <= {left, right}
                and all(isinstance(x, str) and x for x in reasons.values()), 'Missing endpoint reasons')
    if status == 'IDENTITY_LINEAGE_ROLE_CONFLICT':
        require(bool(pair.get('conflicts')), 'Missing role-conflict reasons')
    require(pair.get('identity_step_cost') == 0, 'Identity step charged as taxonomy distance')
    return tuple(sorted((left, right)))


def validate_pair_files(directory, summaries, revision, view, *, training):
    require(set(summaries) == set(DATASETS), 'Missing dataset export')
    counts = {}
    for dataset, count in DATASETS.items():
        summary = summaries[dataset]
        ids = {str(i) for i in range(1, count + 1)}
        if training:
            folder = directory / 'training' / dataset
            require(load(folder / 'summary.json') == summary, 'Export summary mismatch')
            require(summary.get('labels') == count and summary.get('category_reward_preserved') is True,
                    'Label accuracy contract lost')
            require(summary.get('nonapplicable_distance', 'missing') is None,
                    'Nonapplicable export distance is not null')
            require(summary.get('database_revision') == revision and summary.get('relation_view') == view,
                    'Export summary revision/view mismatch')
            exported = {}
            with (folder / 'labels.jsonl').open() as stream:
                for line in stream:
                    row = json.loads(line)
                    cid = str(row['target']['class_id'])
                    require(cid in ids and cid not in exported, 'Duplicate/unknown exported label')
                    require(row.get('snapshot_revision') == revision and row.get('relation_view') == view,
                            'Label export revision/view mismatch')
                    require(row.get('category_reward_applicable') is True, 'Category reward disabled')
                    mask, reason = row.get('hierarchy_endpoint_applicable'), row.get('hierarchy_endpoint_reason')
                    require((mask is True and reason is None) or
                            (mask is False and isinstance(reason, str) and bool(reason)),
                            'Endpoint mask/reason inconsistent')
                    exported[cid] = row
            require(set(exported) == ids, 'Label export incomplete')
            pairs_file = folder / 'pairs.jsonl'
            statuses = summary.get('pair_statuses')
        else:
            require(summary.get('revision') == revision and summary.get('view') == view,
                    'Same-policy revision/view mismatch')
            pairs_file = directory / (dataset + '_pairs.jsonl')
            statuses = summary.get('statuses')
        observed = Counter()
        unique = set()
        with pairs_file.open() as stream:
            for line in stream:
                pair = json.loads(line)
                key = validate_pair(pair, revision, view, dataset, ids)
                require(key[0] != key[1] and key not in unique, 'Duplicate/self pair in combination export')
                unique.add(key)
                observed[pair['status']] += 1
                if training:
                    blocked = {cid: exported[cid]['hierarchy_endpoint_reason'] for cid in (str(pair['left']), str(pair['right']))
                               if exported[cid]['hierarchy_endpoint_reason'] is not None}
                    if blocked:
                        require(pair['status'] == 'ENDPOINT_NOT_APPLICABLE' and pair.get('reasons') == blocked,
                                'Pair bypasses frozen endpoint reward mask/reasons')
                    else:
                        require(pair['status'] != 'ENDPOINT_NOT_APPLICABLE', 'Pair invents an endpoint exclusion')
        require(len(unique) == comb(count, 2) == summary.get('pairs'), 'Pair export incomplete')
        require(dict(observed) == statuses, 'Pair reason census differs from exported records')
        counts[dataset] = len(unique)
    require(sum(counts.values()) == 56917, 'Six-dataset total pair count changed')
    return counts


def semantic_gate(name, output, revision, expected):
    """Read completed result files, including detailed rows, not only exit status."""
    s = load(output / 'summary.json') if name not in ('contracts', 'cycles', 'witnesses', 'global-contracts', 'living-focused', 'repair-focus') else load(output / ('contract.json' if name == 'global-contracts' else 'result.json'))
    if name == 'domains':
        rows = load(output / 'domains.json')
        r = s['domains']
        require(len(rows) == r['domains'] == r['passed'] == expected['domains'] and len(rows) > 0,
                'Incomplete/failed domain census')
        require(r.get('all_domain_members_checked_by_frozen_root_witness_join') is True,
                'Domain member witness census was not run')
        require(all(x.get('pass') is True and x.get('roots') and
                    all(p.get('root_reachable') is True for p in x['roots']) for x in rows),
                'Domain root/interface failure')
    elif name == 'labels':
        views = s['labels']['views']
        require(set(views) == VIEWS, 'Missing label view')
        for view in VIEWS:
            rows = load(output / (view + '_labels.json'))
            require(len(rows) == views[view].get('labels') == views[view].get('path_state_consistent') == 755,
                    'Missing/inconsistent label paths')
            require(Counter(x['dataset'] for x in rows) == DATASETS, 'Dataset label counts changed')
            require(len({(x['dataset'], str(x['class_id'])) for x in rows}) == 755, 'Duplicate labels')
            require(all(x.get('consistent') is True and x['path']['status'] == x['state']['path_status']
                        and x['state'].get('root_reachable') == (x['path']['status'] in ('ROOT','CONNECTED'))
                        for x in rows), 'Path/state/root truth mismatch')
        require(views['unified'].get('root_reachable') == 755 and
                all(x['state'].get('root_reachable') is True for x in load(output / 'unified_labels.json')),
                'Unified label root reachability incomplete')
        validate_pair_files(output, s['labels']['pairs'], revision, 'unified', training=True)
    elif name == 'structure':
        r = s['structure']
        require(all(r.get(t + '_dangling_' + scope + '_records') == 0
                    for t in ('edges', 'entity_relations') for scope in ('retained','admitted')),
                'Dangling source relation')
        require(r.get('raw_source_unrooted_records_excluded_to_inflate_pass_rate') is False,
                'Legacy source records were hidden to inflate coverage')
        # Unrooted legacy records and unresolved role groups are disclosed, not fabricated as taxonomy.
        require(isinstance(r.get('identity_role_conflicts'), list) and
                isinstance(r.get('unrooted_classification_records'), list), 'Missing unresolved-source disclosure')
    elif name == 'preservation':
        require(s['preservation'].get('pass') is True, 'Exhaustive source/content preservation failed')
    elif name == 'nonfocus':
        r = s['nonfocus']; rows = load(output / 'nonfocus.json')
        require(r.get('count') == r.get('preserved') == len(rows) == expected['samples'] > 0
                and r.get('regressions') == 0, 'Nonfocus retention/path regression')
        require(all(x.get('preserved') is True and
                    not (x['original_status'] in ('ROOT','CONNECTED') and
                         x['unified_status'] not in ('ROOT','CONNECTED')) for x in rows), 'Nonfocus detail regression')
    elif name == 'browse':
        require(s.get('pagination_pass') is True and s.get('all_pages_checked') is True
                and s.get('same_return_scale') is True, 'Browse pagination/scope comparison failed')
        rows = load(output / 'pagination.json')
        rows = list(rows.values()) if isinstance(rows, dict) else rows
        require(len(rows) == 4 and all(x.get('pass') is True for x in rows), 'Missing pagination proof')
    elif name == 'contracts':
        require(s.get('all_pass') is True and s.get('all_indexed_relations', 0) > 0
                and s.get('checks') and all(x == 0 for x in s['checks'].values()), 'Indexed relation/source coverage failure')
        require(s.get('new_semantic_relations') == 0 and s.get('new_semantic_nodes') == 0,
                'Browse index fabricated semantic facts')
    elif name == 'cycles':
        require(set(s) == VIEWS and all(x.get('acyclic') is True and
                x.get('default_preferred_graph_acyclic') is True and
                x.get('cyclic_or_cycle_dependent_vertices') == 0 and
                x.get('processed_vertices') == x.get('incident_identity_vertices') and
                x.get('unique_arcs', 0) > 0 for x in s.values()), 'Missing view/full indexed cycle failure')
    elif name == 'witnesses':
        require(s.get('all_pass') is True and s.get('index_identity_and_source_mismatches') == 0
                and s.get('all_hidden_display_connections_have_surviving_native_routes') is True
                and s.get('source_revision') == expected['browse_parent_revision'], 'Browse native witness/source revision failure')
    elif name == 'cli':
        require(s.get('all_pass') is True and s.get('real_cli_calls') == len(s.get('records', [])) == 14,
                'Real CLI calls incomplete')
        for i, record in enumerate(s['records']):
            require(record.get('exit_code') == 0 and bool(record.get('command')), 'CLI subprocess failure')
            filename = Path(record['output'])
            require(filename.name == str(filename), 'CLI output escapes job directory')
            value = load(output / filename)
            require(value.get('status') not in ('INDEX_REQUIRED','STALE_INDEX','ERROR','UNKNOWN_DOMAIN','QUERY_LIMIT'),
                    'CLI returned unusable result')
            if i == 13:
                require(value.get('status') == 'NOT_FOUND', 'Unknown UID CLI contract failed')
            else:
                require(value.get('status') != 'NOT_FOUND', 'Known fixture was not found')
            require('items' not in value or len(value['items']) <= 3, 'CLI pagination limit ignored')
    elif name == 'same-policy':
        validate_pair_files(output, s, revision, 'unified', training=False)
    elif name == 'self-reward':
        require(s.get('all_pass') is True and s.get('labels') == 755
                and s.get('database_revision') == revision and s.get('relation_view') == 'unified',
                'Live SDK self-query/reward export failed')
    elif name == 'repair-focus':
        require(s.get('all_pass') is True and s.get('database_revision') == revision,
                'Repair-focus result failed or belongs to another candidate revision')
    elif name == 'living-focused':
        scopes = {'kitchen_and_tableware':155, 'lighting':43, 'bags_and_luggage':24, 'toys':51}
        require(s.get('status') == 'PASS' and s.get('issues') == []
                and s.get('database_revision') == revision, 'Living-focused revision/scope failed')
        require(all(s.get(k) == v for k,v in {'current_domains':95, 'protected_original_domains':91,
                    'protected_aliases_checked':588, 'attachment_rules_checked':163}.items()),
                'Living domain/alias/attachment census changed')
        rows = s.get('new_domains', [])
        require(len(rows) == 4 and {x['domain'] for x in rows} == set(scopes), 'Missing living domain')
        require(sum(len(x.get('root_statuses', {})) for x in rows) == 9, 'Missing living roots')
        require(all(x.get('expected_source_wordnet_synsets') == scopes[x['domain']]
                    and x.get('missing_wordnet_scope_uids') == []
                    and x.get('public_complete_pagination_matches_cache') is True
                    and all(v in ('ROOT','CONNECTED') for v in x['root_statuses'].values()) for x in rows),
                'Living WordNet scope/root/pagination failed')
        furniture = s.get('furniture_configurations', [])
        require(len(furniture) == 4 and all(x.get('pass') is True and
                x.get('native_payload_retained') is True and x.get('status') in ('ROOT','CONNECTED')
                for x in furniture), 'Bounded furniture batch not retained/connected')
    elif name == 'global-contracts':
        require(s.get('structural_contract_pass') is True and s.get('checks')
                and all(x == 0 for x in s['checks'].values())
                and all(x.get('changed_or_deleted') == 0 for x in s.get('regressions',{}).values()), 'Global source/role/witness contract failed')
    elif name == 'usability':
        require(s.get('errors') == [] and s.get('six_dataset_labels') == 755
                and s.get('view_task_checks', 0) > 0 and s.get('view_portal_checks', 0) > 0
                and s.get('public_path_samples', 0) > 0, 'Public usability checks missing/failed')
    else:
        raise ValueError('No semantic gate implemented: ' + name)
    return {'pass': True, 'scope': name,
            'identity_and_annotation_review_not_implicitly_verified': True}


def self_reward(database, exports, output):
    sys.path.insert(0, str(ROOT / 'src'))
    from fineatlas import FineAtlas
    checked = 0
    statuses = Counter()
    with FineAtlas(database) as tree:
        for dataset, count in DATASETS.items():
            index = tree.relation_reward_index(dataset)
            labels = {str(x['target']['class_id']): x for x in
                      (json.loads(line) for line in (exports / 'training' / dataset / 'labels.jsonl').open())}
            require(len(labels) == count == len(index.labels), 'SDK/export label census differs')
            for cid, label in labels.items():
                endpoint = index.labels[cid]
                require(label.get('snapshot_revision') == tree._revision
                        and label['target'].get('target_uid') == endpoint['uid']
                        and label['target'].get('label') == endpoint['label']
                        and label['target'].get('identity_verified') == endpoint['identity_verified']
                        and label['hierarchy_endpoint_reason'] == endpoint['reason']
                        and label['hierarchy_endpoint_applicable'] == (endpoint['reason'] is None),
                        'Export endpoint differs from live SDK policy')
                pair = index.query(cid, cid)
                validate_pair(pair, tree._revision, 'unified', dataset, set(labels))
                require(pair['distance'] is None or pair['distance'] == 0, 'Self identity has nonzero distance')
                if endpoint['reason'] is not None:
                    require(pair['status'] == 'ENDPOINT_NOT_APPLICABLE'
                            and pair['reasons'] == {cid: endpoint['reason']}, 'Self query bypassed endpoint review')
                statuses[pair['status']] += 1
                checked += 1
        output.mkdir(parents=True, exist_ok=True)
        write(output / 'summary.json', {'all_pass': True, 'labels': checked,
            'database_revision': tree._revision, 'relation_view': tree.relation_view,
            'statuses': dict(statuses), 'self_queries': checked,
            'scientific_or_visual_reward_calibration': False})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('database','source-baseline','browse-baseline','browse-staging',
                 'primary-records','samples','reports','source-baseline-manifest','exports','living-inputs','production-baseline','repair-focus-inputs'):
        p.add_argument('--' + flag, type=Path)
    p.add_argument('--expected-release')
    p.add_argument('--expected-revision')
    p.add_argument('--workers', type=int, choices=range(1,5), default=1)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--with-contracts', action='store_true')
    p.add_argument('--with-usability', action='store_true')
    p.add_argument('--self-check', action='store_true', help=argparse.SUPPRESS)
    a = p.parse_args()
    if a.self_check:
        require(a.database and a.exports and a.reports, 'Self check paths required')
        self_reward(a.database, a.exports, a.reports)
        return 0
    for key in ('database','source_baseline','browse_baseline','browse_staging','primary_records','samples','reports','expected_release'):
        require(getattr(a, key) is not None, '--' + key.replace('_','-') + ' required')
    for key in ('database','source_baseline','browse_baseline','browse_staging','primary_records','samples','reports'):
        setattr(a, key, getattr(a, key).resolve())
    require(a.database != a.source_baseline and a.database != a.browse_baseline,
            'Candidate cannot be its own historical baseline')
    require(not a.reports.exists() or a.resume, 'Reports directory exists; use a new directory or explicit --resume')
    require(not a.resume or a.reports.is_dir(), '--resume requires an existing report directory')
    require(not a.with_contracts or a.production_baseline is not None,
            '--with-contracts requires --production-baseline (protected production artifact)')
    if a.production_baseline:
        a.production_baseline = a.production_baseline.resolve()
        require(a.production_baseline != a.database, 'Candidate cannot be its own production baseline')
    a.reports.mkdir(parents=True, exist_ok=True)
    lock = a.reports / '.acceptance.lock'
    if lock.exists():
        pid = int(lock.read_text())
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            require(a.resume, 'Stale acceptance lock requires --resume')
            lock.unlink()
        else:
            raise ValueError('Acceptance already running with PID ' + str(pid))
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.write(fd, str(os.getpid()).encode()); os.close(fd)
    receipt_path = a.reports / 'acceptance_receipt.json'
    try:
        start = snapshot(a.database)
        readiness(start, a.expected_release)
        revision = start['metadata']['database_revision']
        if a.expected_revision:
            require(a.expected_revision == revision, 'Unexpected database revision')
        base = snapshot(a.source_baseline)
        old = snapshot(a.browse_baseline)
        staging = snapshot(a.browse_staging)
        production = snapshot(a.production_baseline) if a.production_baseline else None
        sm = staging['metadata']; m = start['metadata']
        require(sm.get('browse_index_revision') == revision and sm.get('database_revision') == revision
                and sm.get('browse_parent_revision') == m['browse_parent_revision'], 'Browse artifact revision mismatch')
        if a.browse_staging != a.database:
            require(sm.get('browse_source_revision') == m['browse_parent_revision']
                    and sm.get('browse_indexes_ready') is True, 'Wrong/incomplete browse staging source')
        if a.source_baseline_manifest:
            manifest = load(a.source_baseline_manifest)
            require(manifest['database_revision'] == base['metadata'].get('database_revision')
                    and manifest['database_bytes'] == base['size'], 'Source baseline manifest mismatch')
        fingerprint = sha(a.database)
        require(snapshot(a.database) == start, 'Candidate changed while hashing')
        with sqlite3.connect(a.database.as_uri() + '?mode=ro&immutable=1', uri=True) as con:
            domains = con.execute('SELECT count(*) FROM domain_registry').fetchone()[0]
        config = {'source_baseline': base, 'browse_baseline': old, 'browse_staging': staging, 'production_baseline': production,
                  'samples_path': str(a.samples), 'samples_sha256': sha(a.samples),
                  'primary_records_path': str(a.primary_records), 'primary_records_sha256': sha(a.primary_records),
                  'with_contracts': a.with_contracts, 'with_usability': a.with_usability,
                  'runner_sha256': sha(__file__), 'code_sha256': code_hash(),
                  'living_inputs': str(a.living_inputs.resolve()) if a.living_inputs else None,
                  'living_inputs_sha256': result_hashes(a.living_inputs.resolve()) if a.living_inputs else None,
                  'repair_focus_inputs': str(a.repair_focus_inputs.resolve()) if a.repair_focus_inputs else None,
                  'repair_focus_inputs_sha256': result_hashes(a.repair_focus_inputs.resolve()) if a.repair_focus_inputs else None}
        expected = {'domains': domains, 'samples': len(load(a.samples)),
                    'browse_parent_revision': m['browse_parent_revision']}
        previous = load(receipt_path) if a.resume and receipt_path.exists() else None
        if a.resume:
            require(previous is not None and previous.get('database_sha256') == fingerprint
                    and previous.get('database_revision') == revision and previous.get('release') == m['release']
                    and previous.get('initial_snapshot') == start and previous.get('configuration') == config,
                    'Resume receipt does not describe the same pinned inputs/artifact/code')
        receipt = {'all_pass': False, 'database_sha256': fingerprint, 'database_revision': revision,
                   'release': m['release'], 'initial_snapshot': start, 'configuration': config,
                   'started_utc': now(), 'jobs': {}, 'result_verdicts': {},
                   'uncovered': ['Independent semantic validation of every legacy source relation/identity',
                                 'Resolution of all annotation scope reviews and visual reward calibration',
                                 'Live public download/reinstallation verification (separate release step)',
                                 'Focused living-domain/ABO semantic checks beyond all-domain census (separate focused acceptance)']}
        if a.living_inputs:
            receipt['uncovered'].pop()
        mutex = threading.Lock()
        environment = dict(os.environ)
        environment['PYTHONPATH'] = str(ROOT / 'src') + os.pathsep + environment.get('PYTHONPATH','')
        specs = []
        def add(name, script, args, file_output=False):
            specs.append((name, script, args, file_output))
        for phase in ('domains','labels','structure','preservation','nonfocus'):
            add(phase, 'audit_unified_candidate.py', ['--database',str(a.database),'--baseline',str(a.source_baseline),
                '--samples',str(a.samples),'--phase',phase])
        add('browse','audit_unified_browsing.py',['--database',str(a.database),'--baseline',str(a.browse_baseline)])
        add('contracts','audit_browse_contracts.py',['--baseline',str(a.database),'--staging',str(a.browse_staging)],True)
        add('cycles','audit_browse_cycles.py',['--staging',str(a.browse_staging)],True)
        add('witnesses','audit_browse_witnesses.py',['--baseline',str(a.database),'--staging',str(a.browse_staging)],True)
        add('cli','audit_browse_cli.py',['--database',str(a.database)])
        add('same-policy','compare_unified_reward_policy.py',['--database',str(a.database),'--view','unified',
            '--primary-records',str(a.primary_records)])
        if a.with_contracts:
            add('global-contracts','audit_contracts.py',['--database',str(a.database),'--baseline',str(a.production_baseline)])
        if a.with_usability:
            add('usability','audit_usability.py',['--database',str(a.database)])
        if a.living_inputs:
            add('living-focused', 'prepare_living_domains.py', ['--database',str(a.database),
                '--audit-inputs',str(a.living_inputs.resolve())], True)
        if a.repair_focus_inputs:
            require(a.repair_focus_inputs.is_dir(), 'Repair-focus inputs directory is missing')
            require((ROOT / 'scripts' / 'audit_repair_focus.py').is_file(),
                    'Repair-focus audit script is missing; no completed audit may be inferred')
            add('repair-focus', 'audit_repair_focus.py', ['--database',str(a.database),
                '--inputs',str(a.repair_focus_inputs.resolve())], True)
        specs.append(('self-reward', Path(__file__).name, [], False))
        receipt['planned_jobs'] = [s[0] for s in specs]
        write(receipt_path, receipt)
        def run(spec):
            name, script, args, file_output = spec
            script_path = ROOT / 'scripts' / script
            script_sha = sha(script_path)
            previous_job = previous.get('jobs',{}).get(name) if previous else None
            if previous_job and previous_job.get('script_sha256') == script_sha and previous_job.get('verdict',{}).get('pass') is True:
                require(previous_job.get('exit_code') == 0 and previous_job.get('database_revision') == revision
                        and previous_job.get('database_sha256') == fingerprint
                        and bool(previous_job.get('started_utc')) and bool(previous_job.get('ended_utc')),
                        'Resume job lacks successful execution provenance')
                output = Path(previous_job['output'])
                require(output.is_relative_to(a.reports), 'Resume output outside reports')
                require(previous_job.get('result_sha256') == result_hashes(output),
                        'Resume result files changed')
                verdict = semantic_gate(name, output, revision, expected)
                return name, {**previous_job, 'resumed_verified_utc': now(), 'verdict': verdict}
            attempt = 1
            while (a.reports / name / ('attempt-' + str(attempt))).exists():
                attempt += 1
            output = a.reports / name / ('attempt-' + str(attempt))
            output.mkdir(parents=True)
            if name == 'self-reward':
                exports = Path(receipt['jobs']['labels']['output'])
                args = ['--self-check','--database',str(a.database),'--exports',str(exports),'--reports',str(output)]
            else:
                args = args + ['--output',str(output / 'result.json' if file_output else output)]
            command = [sys.executable, '-u', str(script_path), *args]
            job = {'command': command, 'cwd': str(ROOT), 'started_utc': now(), 'ended_utc': None,
                   'exit_code': None, 'database_revision': revision, 'database_sha256': fingerprint,
                   'script_sha256': script_sha, 'output': str(output), 'verdict': {'pass': False, 'reason':'not completed'}}
            with mutex:
                receipt['jobs'][name] = job
                write(receipt_path, receipt)
            try:
                require(snapshot(a.database) == start, 'Candidate changed before job')
                with (output / 'process.log').open('w') as stream:
                    job['exit_code'] = subprocess.run(command,cwd=ROOT,env=environment,stdout=stream,stderr=subprocess.STDOUT).returncode
                require(job['exit_code'] == 0, 'Audit subprocess exit=' + str(job['exit_code']))
                require(sha(script_path) == script_sha, 'Audit code changed during job')
                job['verdict'] = semantic_gate(name, output, revision, expected)
            except Exception as error:
                job['verdict'] = {'pass': False, 'reason': str(error)}
            job['ended_utc'] = now()
            job['result_sha256'] = result_hashes(output)
            return name, job
        def record(result):
            name, job = result
            with mutex:
                receipt['jobs'][name] = job
                receipt['result_verdicts'][name] = job['verdict']
                write(receipt_path, receipt)
            print(name, 'PASS' if job['verdict']['pass'] else 'FAIL', flush=True)
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            for future in as_completed([pool.submit(run, s) for s in specs if s[0] != 'self-reward']):
                record(future.result())
        if receipt['jobs'].get('labels',{}).get('verdict',{}).get('pass') is True:
            record(run(specs[-1]))
        else:
            record(('self-reward', {'command': None, 'exit_code': None, 'started_utc': None,
                'ended_utc': now(), 'database_revision': revision, 'verdict': {'pass': False, 'reason':'not run: label export did not pass'}}))
        unchanged = all(snapshot(path) == original for path, original in
                        ((a.database,start),(a.source_baseline,base),(a.browse_baseline,old),(a.browse_staging,staging)))
        if production:
            unchanged = unchanged and snapshot(a.production_baseline) == production
        inputs_unchanged = sha(a.samples) == config['samples_sha256'] and sha(a.primary_records) == config['primary_records_sha256']
        receipt['candidate_unchanged'] = unchanged
        receipt['inputs_unchanged'] = inputs_unchanged
        receipt['final_snapshot'] = snapshot(a.database)
        receipt['ended_utc'] = now()
        receipt['all_pass'] = (unchanged and inputs_unchanged and sha(__file__) == config['runner_sha256']
                               and set(receipt['jobs']) == set(receipt['planned_jobs'])
                               and code_hash() == config['code_sha256']
                               and (not a.living_inputs or result_hashes(a.living_inputs.resolve()) == config['living_inputs_sha256'])
                               and (not a.repair_focus_inputs or result_hashes(a.repair_focus_inputs.resolve()) == config['repair_focus_inputs_sha256'])
                               and all(x['verdict'].get('pass') is True and x.get('exit_code') == 0 for x in receipt['jobs'].values()))
        write(receipt_path, receipt)
        return 0 if receipt['all_pass'] else 1
    finally:
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, sqlite3.Error) as error:
        print('Acceptance refused/failed:', error, file=sys.stderr)
        raise SystemExit(1)
