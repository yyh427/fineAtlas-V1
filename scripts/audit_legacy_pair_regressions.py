#!/usr/bin/env python3
"""Fail closed on unexplained losses under the frozen formal task policy.

This auditor does not import the SDK or the builder's decision functions. It compares
the original formal SDK export with the compatible SDK's formal-data matrix,
then binds every lost pair to external source adjudication and connection checks.
The reports certify complete accounting, not scientific truth of the sources.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import itertools
import json
from pathlib import Path

DATASETS = {'cub200': 200, 'fgvc_aircraft': 100, 'flowers102': 102,
            'pets37': 37, 'stanford_dogs': 120, 'stanford_cars': 196}
SCHEMA = 'FINEATLAS_LEGACY_PAIR_REGRESSION_DISPOSITIONS_V1'
STAGES = {'endpoint_mapping', 'endpoint_identity', 'endpoint_role',
          'endpoint_admission', 'task_boundary', 'ancestor_role',
          'ancestor_cycle', 'ancestor_connectivity', 'lca_resolution'}


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        digest = hashlib.sha256()
        while block := stream.read(1024 * 1024):
            digest.update(block)
        return digest.hexdigest()


def read_pairs(path: Path) -> dict:
    result = {}
    with path.open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            key = (row['dataset'], row.get('left', row.get('left_id')),
                   row.get('right', row.get('right_id')))
            if key in result:
                raise ValueError(f'Duplicate pair: {key}')
            lcas = json.loads(row.get('lca_uids') or row.get('lcas') or '[]')
            uids = [x['uid'] if isinstance(x, dict) else x for x in lcas]
            distance = None if row['distance'] == '' else int(row['distance'])
            if row['status'] != 'APPLICABLE' and distance is not None:
                raise ValueError(f'Invalid distance must remain null: {key}')
            result[key] = {'status': row['status'], 'distance': distance,
                           'lca_uids': sorted(uids)}
    expected = {(ds, str(a), str(b)) for ds, n in DATASETS.items()
                for a, b in itertools.combinations(range(1, n + 1), 2)}
    if set(result) != expected:
        raise ValueError('All 56,917 canonical domain pairs are required')
    return result


def read_labels(directory: Path) -> dict:
    result = {}
    for ds, count in DATASETS.items():
        rows = json.loads((directory / f'legacy-{ds}-labels.json').read_text())
        for row in rows:
            key = (ds, str(row['class_id']))
            if key in result:
                raise ValueError(f'Duplicate label: {key}')
            result[key] = row
        if {cid for dataset, cid in result if dataset == ds} != {
                str(cid) for cid in range(1, count + 1)}:
            raise ValueError(f'Incomplete labels: {ds}')
    return result


def endpoint_stage(reason: str | None) -> str | None:
    if not reason:
        return None
    if reason.startswith(('ANNOTATION_SCOPE_REVIEW', 'LABEL_REVIEW_REQUIRED')):
        return 'endpoint_mapping'
    if reason.startswith(('UNKNOWN_UID', 'IDENTITY_UNCONFIRMED')):
        return 'endpoint_identity'
    if reason.startswith(('IDENTITY_ROLE_CONFLICT', 'ROLE_NOT_APPLICABLE')):
        return 'endpoint_role'
    if reason.startswith('NO_VALID_TASK_BOUNDARY_PATH'):
        return 'task_boundary'
    return 'endpoint_admission'


def path_signature(label: dict) -> list:
    """Ignore revision/row IDs; retain actual source UID and relation witnesses."""
    return [(step['uid'], step['parent_uid'], step.get('edge', {}).get('relation'))
            for step in label.get('path', {}).get('path', [])]


def evidence_files(rows: list, manifest_path: Path) -> None:
    if not isinstance(rows, list) or not rows:
        raise ValueError('External evidence files are required')
    for row in rows:
        path = Path(row['path'])
        if not path.is_absolute():
            path = manifest_path.parent / path
        path = path.resolve(strict=True)
        if path == manifest_path.resolve() or sha256(path) != row.get('sha256'):
            raise ValueError(f'Self-citing or changed evidence: {path}')


def audit(reference: Path, baseline: Path, candidate: Path, policy: Path,
          dispositions: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    original = read_pairs(reference)
    before = read_pairs(baseline / 'legacy-pairs.csv')
    after = read_pairs(candidate / 'legacy-pairs.csv')
    old_labels, new_labels = read_labels(baseline), read_labels(candidate)
    mismatches = [key for key in before if original[key] != before[key]]
    manifest = json.loads(dispositions.read_text())
    summary = json.loads((candidate / 'summary.json').read_text())
    errors = []
    bindings = {'baseline_matrix_sha256': sha256(baseline / 'legacy-pairs.csv'),
                'candidate_matrix_sha256': sha256(candidate / 'legacy-pairs.csv'),
                'policy_sha256': sha256(policy),
                'candidate_revision': summary['legacy']['database_revision']}
    if manifest.get('schema') != SCHEMA:
        errors.append('Wrong disposition schema')
    for key, value in bindings.items():
        if manifest.get(key) != value:
            errors.append(f'Stale or missing binding: {key}')
    if mismatches:
        errors.append(f'Formal SDK compatibility mismatches: {len(mismatches)}')
    classes, counts = {}, {ds: Counter() for ds in DATASETS}
    losses = set()
    changed_paths = {key for key in old_labels
                     if path_signature(old_labels[key]) != path_signature(new_labels[key])}
    for key, old in before.items():
        new = after[key]
        aa, bb = old['status'] == 'APPLICABLE', new['status'] == 'APPLICABLE'
        change = ('lost' if aa and not bb else 'gained' if bb and not aa else
                  'both_valid_changed' if aa and (old != new or
                      (key[0], key[1]) in changed_paths or (key[0], key[2]) in changed_paths) else
                  'both_valid_unchanged' if aa else 'both_invalid')
        counts[key[0]][change] += 1
        classes[key] = change
        if change == 'lost':
            losses.add(key)
    covered, groups, group_ids = {}, [], set()
    for group in manifest.get('groups', []):
        gid = group.get('id')
        group_errors = []
        if not gid or gid in group_ids:
            group_errors.append('Missing or duplicate group ID')
        group_ids.add(gid)
        category = group.get('category')
        disposition = group.get('disposition')
        if category not in range(1, 9):
            group_errors.append('Cause must be one of the eight declared categories')
        if disposition not in {'WITHDRAWAL_JUSTIFIED', 'PENDING_SOURCE_EVIDENCE'}:
            group_errors.append('Unresolved engineering loss cannot pass')
        if category in {2, 3, 4, 5, 6}:
            group_errors.append('Repairable engineering/data omission remains in lost pairs')
        if disposition == 'PENDING_SOURCE_EVIDENCE' and category != 7:
            group_errors.append('Pending source evidence must use category 7')
        if group.get('first_changed_stage') not in STAGES or not group.get('decision_reason'):
            group_errors.append('First changed stage and decision reason required')
        legal = group.get('legal_connection_check', {})
        if legal.get('status') not in {'NO_LEGAL_CONNECTION_LOSS', 'FIXED'}:
            group_errors.append('Legal connections have not been checked or repaired')
        try:
            evidence_files(group.get('evidence'), dispositions)
            evidence_files(legal.get('evidence'), dispositions)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            group_errors.append(str(exc))
        declared = {}
        for label in group.get('labels', []):
            key = (label.get('dataset'), str(label.get('class_id')))
            if key not in old_labels or key in declared:
                group_errors.append(f'Unknown or duplicate evidence label: {key}')
                continue
            declared[key] = label
            for field in ('old_role', 'new_role', 'mapping', 'parent_chain', 'decision_reason'):
                if field not in label or label[field] is None:
                    group_errors.append(f'Missing label evidence {key}: {field}')
            if (label.get('old_uid') != old_labels[key]['checked']['uid'] or
                    label.get('new_uid') != new_labels[key]['checked']['uid']):
                group_errors.append(f'Endpoint UID differs from actual matrix: {key}')
            try:
                evidence_files(label.get('source_evidence'), dispositions)
            except (KeyError, TypeError, ValueError, OSError) as exc:
                group_errors.append(str(exc))
        keys = []
        for raw in group.get('pairs', []):
            key = tuple(str(x) for x in raw)
            keys.append(key)
            if key not in losses or key in covered:
                group_errors.append(f'Non-loss or duplicate pair disposition: {key}')
                continue
            covered[key] = gid
            endpoints = [(key[0], key[1]), (key[0], key[2])]
            rejected = [cid for cid in endpoints if new_labels[cid]['checked']['reason']]
            required = rejected or endpoints
            if not all(cid in declared for cid in required):
                group_errors.append(f'Actual affected endpoint evidence missing: {key}')
            actual_stages = {endpoint_stage(new_labels[cid]['checked']['reason'])
                             for cid in rejected}
            if actual_stages and group.get('first_changed_stage') not in actual_stages:
                group_errors.append(f'First stage differs from actual endpoint rejection: {key}')
            if not rejected:
                expected_stage = {'IDENTITY_LINEAGE_ROLE_CONFLICT': 'ancestor_role',
                                  'CYCLIC_LINEAGE': 'ancestor_cycle',
                                  'NO_COMMON_ANCESTOR': 'ancestor_connectivity',
                                  'COARSE_COMMON_ANCESTOR_ONLY': 'lca_resolution'}.get(after[key]['status'])
                if expected_stage != group.get('first_changed_stage'):
                    group_errors.append(f'First stage differs from actual pair rejection: {key}')
        if not keys:
            group_errors.append('Empty disposition group')
        groups.append({'id': gid, 'category': category, 'disposition': disposition,
                       'pairs': len(keys), 'labels': len(declared),
                       'pass': not group_errors, 'errors': group_errors[:100]})
        errors.extend(f'{gid}: {error}' for error in group_errors)
    missing = losses - covered.keys()
    if missing:
        errors.append(f'Unexplained old-valid/new-invalid pairs: {len(missing)}')
    with (output / 'all-pair-changes.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['dataset', 'left', 'right', 'change', 'before_status',
                         'after_status', 'before_distance', 'after_distance',
                         'before_lca_uids', 'after_lca_uids', 'disposition_group'])
        for key in before:
            a, b = before[key], after[key]
            writer.writerow([*key, classes[key], a['status'], b['status'],
                             a['distance'], b['distance'], json.dumps(a['lca_uids']),
                             json.dumps(b['lca_uids']), covered.get(key)])
    result = {'schema': 'FINEATLAS_LEGACY_PAIR_REGRESSION_AUDIT_V1',
              'pass': not errors, 'complete': True, **bindings,
              'reference_export_sha256': sha256(reference),
              'dispositions_sha256': sha256(dispositions),
              'formal_sdk_compatibility_mismatches': len(mismatches),
              'labels': len(new_labels), 'pairs': len(before),
              'labels_with_changed_source_paths': len(changed_paths),
              'datasets': {ds: dict(value) for ds, value in counts.items()},
              'lost_pairs': len(losses), 'accounted_lost_pairs': len(covered),
              'unexplained_lost_pairs': len(missing), 'groups': groups,
              'errors': errors[:200], 'error_count': len(errors),
              'scope': 'Complete fixed-policy accounting with hashed external adjudication; source truth requires the cited independent review.'}
    (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'baseline', 'candidate', 'policy', 'dispositions', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    report = audit(**vars(args))
    print(json.dumps({key: report[key] for key in ('pass', 'pairs', 'lost_pairs',
                     'unexplained_lost_pairs', 'error_count')}))
    raise SystemExit(0 if report['pass'] else 1)
