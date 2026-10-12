"""Full original-class usability and fixed-budget retrieval/pair acceptance.

Original label probes are backend oracle checks, not autonomous model recall.
No model, GPU, image download or training process is used.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import time

from fineatlas import FineAtlas, __version__
from fineatlas.repair_candidate import CORE_COUNTS

DOMAINS = dict(zip(CORE_COUNTS, ('bird', 'aircraft', 'plant', 'animal', 'animal', 'car')))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--database', type=Path, required=True)
    p.add_argument('--baseline-audit', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--phase', choices=('classes', 'queries', 'pairs'), required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    original = json.loads((args.baseline_audit / 'original_annotations.json').read_text())
    old_queries = {(r['dataset'], r['class_id']): r for r in json.loads((args.baseline_audit / 'candidate_v1110rc1_queries.json').read_text())}
    result = {'phase': args.phase, 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'database': str(args.database.resolve()), 'sdk_version': __version__, 'datasets': {}, 'errors': [],
              'scope': 'All six original datasets;755 source classes;backend label probes are not visual recall'}
    rows, queries, relation_rows = [], [], []
    with FineAtlas(args.database, relation_view='unified') as atlas:
        atlas.con.execute('PRAGMA query_only=ON')
        atlas.con.execute('PRAGMA cache_size=-65536')
        result['database_revision'] = atlas._revision
        result['relation_view'] = atlas.relation_view
        for dataset, expected in CORE_COUNTS.items():
            counts = Counter()
            if args.phase == 'pairs':
                for admission, scope in [('legacy', 'world'), ('reviewed_paths', 'world'), ('reviewed_paths', 'source_native')]:
                    statuses = Counter()
                    index = atlas.relation_reward_index(dataset, admission_mode=admission, target_scope=scope)
                    filename = args.output / (dataset + '_' + admission + '_' + scope + '_pairs.csv')
                    with filename.open('w', newline='', encoding='utf-8-sig') as stream:
                        writer = csv.DictWriter(stream, fieldnames=['dataset', 'left', 'right', 'status', 'distance', 'lcas', 'reasons'])
                        writer.writeheader()
                        for pair in index.pairs():
                            statuses[pair['status']] += 1
                            writer.writerow({'dataset': dataset, 'left': pair['left'], 'right': pair['right'],
                                             'status': pair['status'], 'distance': pair['distance'],
                                             'lcas': json.dumps(pair['lcas'], ensure_ascii=False),
                                             'reasons': json.dumps(pair.get('reasons', {}), ensure_ascii=False)})
                    result['datasets'].setdefault(dataset, {})[admission + '/' + scope] = {
                        'labels': len(index.labels), 'pairs': sum(statuses.values()), 'statuses': dict(statuses),
                        'expected_pairs': expected * (expected - 1) // 2,
                        'admission_mode': admission, 'target_scope': scope,
                        'requirement': index.requirement, 'source_scope': index.source_scope,
                        'hierarchy_reward_enabled_for_accuracy_experiment': False}
                    if len(index.labels) != expected or sum(statuses.values()) != expected * (expected - 1) // 2:
                        result['errors'].append({'dataset': dataset, 'mode': admission + '/' + scope, 'error': 'Denominator mismatch'})
                    print(dataset, admission, scope, dict(statuses), flush=True)
                save(args.output / 'pairs_summary.json', result)
                continue
            labels = original['labels'][dataset]
            if len(labels) != expected:
                result['errors'].append({'dataset': dataset, 'error': 'Original label inventory count mismatch'})
            for cid, label in labels.items():
                try:
                    if args.phase == 'classes':
                        native = atlas.native_class(dataset, cid)
                        direct = atlas.target(dataset, cid, target_scope='source_native')
                        resolution = atlas.resolve_native_name(label, dataset=dataset)
                        own_exact = atlas.evaluate_exact(dataset, cid, predicted_uid=native['uid'])
                        label_exact = atlas.evaluate_exact(dataset, cid, predicted_label=label)
                        contract = atlas.candidate_contract(native['uid'], dataset=dataset)
                        relations = atlas.native_relations(dataset, cid)
                        relation_rows.append({'dataset': dataset, 'class_id': cid, **relations})
                        world = native['world_mapping']
                        world_prediction = atlas.evaluate_exact(dataset, cid, predicted_uid=world['uid']) if world['uid'] else None
                        checks = {'stable_namespaced_id': ':' in native['uid'],
                                  'native_usable': native['native_usable'],
                                  'direct_query': bool(direct and direct['target_uid'] == native['uid'] and direct['native_label_admission']['usable']),
                                  'original_name_resolution': resolution['status'] == 'RESOLVED' and resolution['items'][0]['uid'] == native['uid'],
                                  'native_answer_eligibility': contract['native_answer_eligible'],
                                  'uid_exact_evaluation': own_exact['native_exact'],
                                  'name_exact_evaluation': label_exact['native_exact'],
                                  'effective_world_feedback': bool(world['effective_status'] and world['reason']),
                                  'review_not_world_supervision': world['world_identity_verified'] or own_exact['world_exact'] is None,
                                  'confirmed_world_answer_eligibility': not world['world_identity_verified'] or atlas.candidate_contract(world['uid'], dataset=dataset)['world_answer_eligible'],
                                  'confirmed_world_exact_evaluation': not world['world_identity_verified'] or bool(world_prediction and world_prediction['native_exact'] and world_prediction['world_exact']),
                                  'unconfirmed_world_not_native_exact': world['world_identity_verified'] or not world_prediction or not world_prediction['native_exact'],
                                  'relations_and_navigation_explained': relations['status'] == 'AVAILABLE' and bool(relations['source_relations']),
                                  'hierarchy_reward_disabled': own_exact['hierarchy_reward'] is None and not own_exact['hierarchy_reward_enabled']}
                        row = {'dataset': dataset, 'class_id': cid, 'original_label': label,
                               'uid': native['uid'], 'namespace': native['namespace'], 'source_version': native['source_version'],
                               'role': native['role'], 'object_granularity': native['object_granularity'],
                               'world_uid': world['uid'], 'stored_status': world['stored_status'],
                               'effective_world_status': world['effective_status'], 'world_identity_verified': world['world_identity_verified'],
                               'world_reason': world['reason'], 'missing_world_evidence': world['missing_evidence'],
                               'world_evidence_ids': world['evidence_ids'], 'native_evidence_ids': native['evidence_ids'],
                               'navigation_status': relations['navigation']['status'],
                               'source_relation_types': sorted({r['relation'] for r in relations['source_relations']}),
                               'checks': checks, 'passed': all(checks.values())}
                        rows.append(row)
                        counts['classes'] += 1
                        counts['passed'] += row['passed']
                        counts['world_' + world['effective_status']] += 1
                        counts['navigation_' + relations['navigation']['status']] += 1
                        if not row['passed']:
                            result['errors'].append({'dataset': dataset, 'class_id': cid, 'failed_checks': [k for k, v in checks.items() if not v]})
                    else:
                        old = old_queries[(dataset, cid)]
                        record = {'dataset': dataset, 'class_id': cid, 'query': label, 'domain': DOMAINS[dataset], 'budgets': {}}
                        native = atlas.native_class(dataset, cid)
                        for budget in (10, 80):
                            raw = atlas.search(label, budget, DOMAINS[dataset])
                            discovery = atlas.candidate_search(label, budget, DOMAINS[dataset])
                            answers = atlas.candidate_search(label, budget, DOMAINS[dataset], dataset=dataset, purpose='answers')
                            item = {'raw_uids': [r['uid'] for r in raw],
                                    'raw_slots': len(raw), 'raw_unique_components': len({r['component_id'] for r in raw}),
                                    'raw_duplicate_slots': len(raw) - len({r['component_id'] for r in raw}),
                                    'discovery_uids': [r['uid'] for r in discovery['items']],
                                    'discovery_keys': [r['presentation_key'] for r in discovery['items']],
                                    'discovery_slots': len(discovery['items']),
                                    'discovery_duplicate_slots': len(discovery['items']) - len({r['presentation_key'] for r in discovery['items']}),
                                    'answer_uids': [r['uid'] for r in answers['items']],
                                    'answer_slots': len(answers['items']),
                                    'native_target_in_discovery': any(r['uid'] == native['uid'] for r in discovery['items']),
                                    'native_target_in_answers': any(r['uid'] == native['uid'] for r in answers['items']),
                                    'scan_complete': discovery['diagnostics']['scan_complete'],
                                    'diagnostics': discovery['diagnostics'],
                                    'ineligible_answer_slots': sum(not atlas.candidate_contract(r['uid'], dataset=dataset)['answer_eligible'] for r in answers['items'])}
                            record['budgets'][str(budget)] = item
                            for prefix, value in [('raw_slots', item['raw_slots']), ('raw_duplicates', item['raw_duplicate_slots']),
                                                  ('discovery_slots', item['discovery_slots']), ('discovery_duplicates', item['discovery_duplicate_slots']),
                                                  ('answers', item['answer_slots']), ('ineligible_answers', item['ineligible_answer_slots'])]:
                                counts[prefix + '_' + str(budget)] += value
                            counts['empty_raw_' + str(budget)] += int(not raw)
                            counts['empty_discovery_' + str(budget)] += int(not discovery['items'])
                            counts['empty_answers_' + str(budget)] += int(not answers['items'])
                            counts['backend_native_target_in_answers_' + str(budget)] += item['native_target_in_answers']
                            counts['incomplete_scan_' + str(budget)] += int(not item['scan_complete'])
                        record['baseline_rc1'] = {k: old[k] for k in ('returned_10', 'unique_identity_10', 'duplicate_slots_10', 'returned_80', 'unique_identity_80', 'small_uids')}
                        queries.append(record)
                        counts['queries'] += 1
                    if int(cid) % 50 == 0:
                        print(args.phase, dataset, cid, dict(counts), flush=True)
                except Exception as exc:
                    result['errors'].append({'dataset': dataset, 'class_id': cid, 'error': str(exc)})
            result['datasets'][dataset] = dict(counts)
            save(args.output / (args.phase + '_summary.json'), result)
            save(args.output / ('native755_acceptance.json' if args.phase == 'classes' else 'fixed755_queries.json'), rows if args.phase == 'classes' else queries)
            if args.phase == 'classes':
                save(args.output / 'native755_relations_and_paths.json', relation_rows)
            print(args.phase, dataset, dict(counts), flush=True)
        result['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        result['passed'] = not result['errors']
        if args.phase == 'classes':
            result['passed'] = result['passed'] and len(rows) == 755 and all(r['passed'] for r in rows)
            with (args.output / 'native755_acceptance.csv').open('w', newline='', encoding='utf-8-sig') as stream:
                fields = list(rows[0]) if rows else []
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})
        save(args.output / (args.phase + '_summary.json'), result)
        print(json.dumps({'phase': args.phase, 'passed': result['passed'], 'errors': len(result['errors']),
                          'database_revision': result['database_revision']}), flush=True)
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
