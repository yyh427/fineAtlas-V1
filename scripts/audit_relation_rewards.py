#!/usr/bin/env python3
"""Read-only public-SDK label/ancestor/pair audit; never hashes or rewrites a DB.

Run with PYTHONPATH=src. Ancestors are materialized once per endpoint, not pair.
The derived common-ancestor distance is NOT the generic undirected API distance.
"""
import argparse
import collections
import hashlib
import itertools
import json
from pathlib import Path
import time

from fineatlas import FineAtlas

DATASETS = ('cub200', 'fgvc_aircraft', 'flowers102', 'pets37',
            'stanford_dogs', 'stanford_cars')


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def run(db, output, views, datasets):
    output.mkdir(parents=True, exist_ok=True)
    summary = {'database': str(db.resolve()), 'bytes': db.stat().st_size,
               'views': {}, 'started_unix': time.time(), 'errors': []}
    for view in views:
        started = time.monotonic()
        with FineAtlas(db, relation_view=view) as atlas:
            summary['metadata'] = atlas.metadata
            summary['runtime_revision'] = atlas._revision
            nodes, parents, labels, ancestors = {}, {}, [], {}
            counts, pairs = {}, {}
            for dataset in datasets:
                counts[dataset] = collections.Counter()
                print(json.dumps({'phase':'labels','dataset':dataset,'view':view,'database':str(db)}),flush=True)
                for target in atlas.task_labels(dataset):
                    uid = target['target_uid']
                    node = atlas.node(uid)
                    result, status = atlas.path_result(uid), atlas.connection_status(uid)
                    row = {'dataset': dataset, 'class_id': target['class_id'],
                           'label': target['label'], 'uid': uid,
                           'decision_status': target['decision_status'],
                           'identity_verified': target['identity_verified'],
                           'mapping_verified': target['mapping_verified'],
                           'node': {k: node.get(k) for k in ('label', 'source', 'node_kind',
                                  'native_rank', 'normalized_rank', 'component_id', 'visibility')},
                           'identity': atlas.identity(uid), 'path': result,
                           'connection_status': status, 'task_admission': target['task_admission']}
                    row['path_status_agree'] = (result['status'] == status.get('path_status'))
                    row['reachability_agree'] = ((result['status'] == 'CONNECTED') == status['root_reachable'])
                    counts[dataset]['labels'] += 1
                    for flag in ('identity_verified', 'mapping_verified', 'path_status_agree', 'reachability_agree'):
                        counts[dataset][flag] += bool(row[flag])
                    counts[dataset]['root_reachable'] += status['root_reachable']
                    counts[dataset]['task_usable'] += target['task_admission']['usable']
                    try:
                        closure = atlas.ancestors(uid, limit=10000, include_self=True, max_nodes=10000)
                        if closure.has_more:
                            raise RuntimeError('Truncated public ancestor result')
                        ancestors[uid] = {n['component_id']: n['distance'] for n in closure}
                        for n in closure:
                            comp = n['component_id']
                            nodes[comp] = {k: n.get(k) for k in ('uid', 'label', 'source', 'node_kind', 'native_rank')}
                            if comp not in parents:
                                pp = atlas.neighbors(n['uid'], direction='parents', limit=10000)
                                if pp.has_more:
                                    raise RuntimeError('Truncated public parent result')
                                parents[comp] = {p['component_id'] for p in pp}
                        row['ancestor_count'] = len(ancestors[uid])
                    except Exception as exc:
                        row['ancestor_error'] = type(exc).__name__ + ': ' + str(exc)
                        ancestors[uid] = {}
                    labels.append(row)
                    if counts[dataset]['labels'] % 25 == 0:
                        print(json.dumps({'phase':'label_checkpoint','dataset':dataset,'view':view,
                                          'count':counts[dataset]['labels'],'uid':uid}),flush=True)
            with (output / (view + '-pairs.jsonl')).open('w') as stream:
                for dataset in datasets:
                    pairs[dataset] = collections.Counter()
                    selected = [r for r in labels if r['dataset'] == dataset]
                    for left, right in itertools.combinations(selected, 2):
                        aa, bb = ancestors[left['uid']], ancestors[right['uid']]
                        common = aa.keys() & bb.keys()
                        nonlowest = set().union(*(parents.get(c, set()) & common for c in common)) if common else set()
                        lowest = common - nonlowest
                        informative = [c for c in lowest if nodes[c]['native_rank'] not in
                                       ('domain_root', 'domain_entry', 'portal') and nodes[c]['uid'] != atlas.root_uid]
                        record = {'dataset': dataset, 'left': left['class_id'], 'right': right['class_id'],
                                  'lcas': [nodes[c] for c in sorted(lowest)],
                                  'ancestor_distance': min((aa[c] + bb[c] for c in common), default=None),
                                  'status': 'ANCESTOR_QUERY_ERROR' if not aa or not bb else
                                            'NO_COMMON_ANCESTOR' if not common else
                                            'COARSE_ONLY' if not informative else 'INFORMATIVE_COMMON_ANCESTOR',
                                  'both_root_reachable': left['connection_status']['root_reachable'] and right['connection_status']['root_reachable'],
                                  'both_identity_verified': left['identity_verified'] and right['identity_verified']}
                        stream.write(json.dumps(record, ensure_ascii=False) + '\n')
                        pairs[dataset]['total'] += 1
                        pairs[dataset][record['status']] += 1
                        if record['status'] == 'INFORMATIVE_COMMON_ANCESTOR':
                            pairs[dataset]['root_and_identity_eligible'] += bool(record['both_root_reachable'] and record['both_identity_verified'])
            # Independent calls to the real existing LCA and graph-distance interfaces.
            samples = []
            for left_id, right_id in [('1','2'), ('1','3'), ('100','101'), ('103','110'), ('14','19')]:
                left, right = atlas.target('cub200',left_id), atlas.target('cub200',right_id)
                if not left or not right:
                    continue
                sample = {'left': left_id, 'right': right_id}
                for method in ('lca','distance'):
                    tick = time.monotonic()
                    try:
                        sample[method] = getattr(atlas,method)(left['target_uid'], right['target_uid'], max_nodes=500)
                    except Exception as exc:
                        sample[method] = {'error': type(exc).__name__, 'detail': str(exc)}
                    sample[method + '_seconds'] = time.monotonic() - tick
                samples.append(sample)
            write(output / (view + '-labels.json'), labels)
            write(output / (view + '-public-samples.json'), samples)
            write(output / (view + '-ancestors.json'), {'nodes': nodes, 'parents': {k:sorted(v) for k,v in parents.items()}, 'closures': ancestors})
            summary['views'][view] = {'labels': counts, 'pairs': pairs, 'seconds': time.monotonic()-started}
            write(output / 'summary.json',summary)
            print(json.dumps({'database':str(db), 'view':view, **summary['views'][view]}),flush=True)
    summary['finished_unix'] = time.time()
    summary['sdk_files_sha256'] = {str(f): hashlib.sha256(f.read_bytes()).hexdigest()
                                  for f in Path('src/fineatlas').glob('*.py')}
    write(output / 'summary.json',summary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--views', nargs='+', default=['strict','taxonomy','membership'])
    parser.add_argument('--datasets', nargs='+', default=list(DATASETS))
    args = parser.parse_args()
    run(args.database,args.output,args.views,args.datasets)
