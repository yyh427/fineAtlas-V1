#!/usr/bin/env python3
"""Independently verify projection source retention and world-view withdrawal.

Uses read-only SQLite and local predicates, never migration/classifier helpers.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3

INPUT_NAME = 'structure_cars_projection_view_repairs.json'
STAGE = 'cars_projection_view_repairs'


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def content(row):
    return {k: v for k, v in dict(row).items() if k not in {'id', 'status', 'reason'}}


def claim_sha(row):
    return sha(json.dumps(content(row), sort_keys=True))


def find_claim(c, original):
    rows = c.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',
                     tuple(original[k] for k in ('subject_uid', 'object_uid', 'relation', 'source'))).fetchall()
    found = [r for r in rows if content(r) == content(original)]
    return found[0] if len(found) == 1 else None


def table_hash(c, table):
    rows = sorted([dict(r) for r in c.execute('SELECT * FROM ' + table)], key=lambda x: json.dumps(x, sort_keys=True))
    return sha(json.dumps(rows, sort_keys=True))


def run(database, inputs, output, preflight=False):
    database = Path(database).resolve(); inputs = Path(inputs).resolve(); output = Path(output)
    manifest_path = inputs / INPUT_NAME
    manifest = json.loads(manifest_path.read_text())
    operation_path = (inputs / manifest['operations_file']).resolve()
    if not operation_path.is_relative_to(inputs) or operation_path.name != 'cars_projection_view_repairs.jsonl':
        raise ValueError('Unsafe projection operation path')
    raw = operation_path.read_bytes(); ops = [json.loads(x) for x in raw.decode().splitlines() if x]
    errors = []
    def bad(kind, **fields): errors.append({'kind': kind, **fields})
    if (manifest.get('schema') != 'FINEATLAS_CARS_PROJECTION_VIEW_REPAIRS_V1' or not ops
            or sha(raw) != manifest['operations_sha256'] or type(manifest['operation_count']) is not int
            or len(ops) != manifest['operation_count'] or dict(Counter(x['relation'] for x in ops)) != manifest['operations']
            or len(manifest['source_projections']) != manifest['source_projection_count']
            or len({x['uid'] for x in manifest['source_projections']}) != manifest['source_projection_count']):
        bad('INCOMPLETE_FROZEN_CENSUS')
    c = sqlite3.connect(database.as_uri() + '?mode=ro&immutable=1', uri=True); c.row_factory = sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    index = {x['uid']: x for x in manifest['source_projections']}
    for uid, entry in index.items():
        row = c.execute('SELECT * FROM nodes WHERE uid=?', (uid,)).fetchone()
        profile = c.execute('SELECT * FROM node_profiles WHERE uid=?', (uid,)).fetchone()
        if not row: bad('MISSING_SOURCE_OBJECT', uid=uid); continue
        original = entry['before_node']; origin = entry['origin']
        if any(dict(row).get(k) != v for k, v in original.items() if k not in {'component_id', 'visibility'}) or sha(row['data']) != entry['native_record_sha256']:
            bad('SOURCE_OBJECT_CONTENT_CHANGED', uid=uid)
        expected_uid = 'v26-car:' + sha('\0'.join((origin['dataset'], origin['class_id'], origin['official_label'])))[:32]
        if (expected_uid != uid or origin['deterministic_constructor_uid'] != uid
                or origin['original_overlay_node']['data'] != row['data']
                or json.loads(row['data']).get('dataset_alias') != origin['official_label']
                or origin['original_overlay_target']['target_uid'] != uid
                or origin['author_source_origin_proven'] is not True
                or origin['author_origin_does_not_close_world_configuration_range'] is not True):
            bad('ORIGINAL_AUTHOR_CONSTRUCTOR_UNBOUND', uid=uid)
        target = c.execute('SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?', (origin['dataset'], origin['class_id'])).fetchone()
        if not target or target['label'] != origin['official_label'] or target['target_uid'] != uid:
            bad('ORIGINAL_AUTHOR_TARGET_CHANGED', uid=uid)
        for field, table in (('before_current_target', 'dataset_targets'), ('before_mapping_check', 'dataset_mapping_checks')):
            if field not in entry: bad('FROZEN_CURRENT_MAPPING_CHECK_MISSING', uid=uid, field=field)
            if field in entry:
                current = c.execute('SELECT * FROM ' + table + ' WHERE dataset=? AND class_id=?', (origin['dataset'], origin['class_id'])).fetchone()
                if (dict(current) if current else None) != entry[field]: bad('MAPPING_OR_CHECK_CHANGED', uid=uid, table=table)
        if preflight:
            if row['visibility'] != 'ACTIVE' or (dict(profile) if profile else None) != entry['before_profile']:
                bad('PREFLIGHT_ROLE_OR_VISIBILITY_CHANGED', uid=uid)
            continue
        attrs = json.loads(profile['attributes']) if profile else {}
        old_attrs = json.loads(entry['before_profile']['attributes']) if entry['before_profile'] else {}
        if (row['visibility'] != 'SOURCE_ONLY' or not profile or profile['node_kind'] != 'UNKNOWN'
                or attrs.get('allowed_views') != [] or attrs.get('source_role') != old_attrs.get('source_role', original['rank'])
                or profile['domain'] != (entry['before_profile']['domain'] if entry['before_profile'] else original['domain'])):
            bad('CANONICAL_REVIEW_OR_DECLARATION_LOST', uid=uid)
        role = c.execute('SELECT * FROM normalization_roles WHERE uid=?', (uid,)).fetchone()
        ev = c.execute('SELECT payload FROM evidence WHERE evidence_id=?', (role['evidence_id'],)).fetchone() if role else None
        proof = json.loads(ev[0]) if ev else {}
        if not role or role['canonical_role'] != 'UNKNOWN' or role['status'] != 'VERIFIED' or proof.get('native_record_sha256') != sha(row['data']) or proof.get('source_origin') != origin:
            bad('REVIEW_ROLE_EVIDENCE_MISSING', uid=uid)
        histories = c.execute("SELECT before_json,after_json FROM usability_changes WHERE stage=? AND object_type='nodes' AND object_id=?", (STAGE, uid)).fetchall()
        if not any(json.loads(h[0]) == original and all(json.loads(h[1]).get(k) == dict(row).get(k) for k in original if k != 'component_id') for h in histories):
            # Independent parent graph rebuilding may alter component IDs before the delta.
            if not any(all(json.loads(h[0]).get(k) == v for k, v in original.items() if k != 'component_id') and all(json.loads(h[1]).get(k) == dict(row).get(k) for k in original if k != 'component_id') for h in histories):
                bad('SOURCE_VISIBILITY_HISTORY_MISSING', uid=uid)
        histories = c.execute("SELECT before_json,after_json FROM usability_changes WHERE stage=? AND object_type='node_profiles' AND object_id=?", (STAGE, uid)).fetchall()
        if not any(json.loads(h[0]) == entry['before_profile'] and json.loads(h[1]) == dict(profile) for h in histories):
            bad('SOURCE_ROLE_HISTORY_MISSING', uid=uid)
        for table in ('browse_nodes', 'view_terminal_connections'):
            # Source-only objects must not be materialized as hierarchy subjects.
            if c.execute('SELECT count(*) FROM ' + table + ' WHERE uid=?', (uid,)).fetchone()[0]:
                bad('SOURCE_ONLY_OBJECT_IN_NAVIGATION_CACHE', uid=uid, table=table)
    review_keys = set(); reference_ids = set()
    for op in ops:
        before = op['before_relation']; uid = op['uid']; proof = op['proof']
        expected_hash = claim_sha(before)
        if (uid not in index or op['op'] != 'review_world_projection_relation' or op['relation'] != 'CONFIGURATION_OF'
                or proof['world_identity_assertion'] is not False or proof['new_parent_task_relation'] is not False
                or proof['source_scope_conflict'] is not False or proof['scope_evidence_gap'] is not True
                or proof['source_origin'] != index[uid]['origin'] or expected_hash != op['locator']['content_sha256']
                or expected_hash != proof['old_relation_content_sha256']):
            bad('INVALID_SOURCE_REVIEW_CONTRACT', uid=uid)
        old = find_claim(c, before)
        if not old or old['status'] != ('ACTIVE' if preflight else 'SOURCE_SCOPE_REVIEW'):
            bad('ORIGINAL_CLAIM_NOT_RETAINED_WITH_REVIEW', uid=uid); continue
        key = (before['subject_uid'], before['object_uid'], before['source'], expected_hash)
        if key in review_keys: bad('DUPLICATE_CLAIM', uid=uid)
        review_keys.add(key)
        parent = c.execute('SELECT data,source FROM nodes WHERE uid=?', (op['parent'],)).fetchone()
        if not parent or sha(parent['data']) != proof['parent_native_record_sha256'] or parent['source'] != proof['parent_source']:
            bad('NATIVE_MODEL_REFERENCE_CHANGED', uid=uid)
        if preflight: continue
        history = c.execute("SELECT before_json,after_json,evidence FROM usability_changes WHERE stage=? AND object_type='entity_relations' AND object_id=?", (STAGE, str(old['id']))).fetchall()
        if not any(content(json.loads(h[0])) == content(before) and json.loads(h[0]).get('status') == 'ACTIVE' and json.loads(h[1]) == dict(old) and json.loads(h[2]).get('basis') == proof['basis'] for h in history):
            bad('ORIGINAL_CLAIM_REVIEW_HISTORY_MISSING', uid=uid)
        source = op['source'] + ' [' + expected_hash + ']'
        refs = c.execute("SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation='SOURCE_MODEL_REFERENCE' AND source=?", (uid, op['parent'], source)).fetchall()
        if len(refs) != 1:
            bad('RETAINED_PRODUCER_REFERENCE_MISSING', uid=uid); continue
        ref = refs[0]; reference_ids.add(ref['id']); retained = json.loads(ref['data'])
        ev = c.execute('SELECT payload,payload_sha256 FROM evidence WHERE evidence_id=?', (ref['evidence_id'],)).fetchone()
        if (ref['status'] != 'SOURCE_DECLARED' or retained.get('original_assertion') != content(before)
                or retained.get('original_locator') != op['locator'] or retained.get('original_status') != 'ACTIVE'
                or retained.get('world_identity_assertion') is not False or retained.get('no_navigation') is not True
                or not ev or json.loads(ev[0]) != retained or sha(ev[0]) != ev[1]):
            bad('REFERENCE_SCOPE_OR_SOURCE_EVIDENCE_CHANGED', uid=uid)
        for table, condition in (('browse_links', "storage='entity_relations' AND record_id=?"), ('view_terminal_connections', 'witness_relation_id=?'), ('view_paths', 'witness_id=?')):
            record_id = -ref['id'] if table == 'view_paths' else ref['id']
            if c.execute('SELECT count(*) FROM ' + table + ' WHERE ' + condition, (record_id,)).fetchone()[0]:
                bad('SOURCE_REFERENCE_IN_NAVIGATION_OR_DISTANCE', uid=uid, table=table)
    if preflight:
        actual_keys = {(r['subject_uid'], r['object_uid'], r['source'], claim_sha(r)) for uid in index for r in c.execute("SELECT * FROM entity_relations WHERE subject_uid=? AND relation='CONFIGURATION_OF' AND status='ACTIVE'", (uid,))}
        if actual_keys != review_keys: bad('UNCLOSED_WORLD_CLAIM_CENSUS_INCOMPLETE')
    for uid in index:
        active = c.execute("SELECT count(*) FROM entity_relations WHERE subject_uid=? AND relation='CONFIGURATION_OF' AND status='ACTIVE'", (uid,)).fetchone()[0]
        if not preflight and active: bad('UNCLOSED_WORLD_INCLUSION_STILL_ACTIVE', uid=uid, count=active)
    for entry in manifest['preserved_nonprojection_configs']:
        node = c.execute('SELECT * FROM nodes WHERE uid=?', (entry['uid'],)).fetchone()
        profile = c.execute('SELECT * FROM node_profiles WHERE uid=?', (entry['uid'],)).fetchone()
        if (not node or any(dict(node).get(k) != v for k, v in entry['before_node'].items() if k != 'component_id')
                or (dict(profile) if profile else None) != entry['before_profile']):
            bad('LEGAL_OEM_OR_EPA_SOURCE_ROLE_CHANGED', uid=entry['uid'])
        if entry['uid'] in index: bad('LEGAL_SOURCE_CONFIGURATION_INCLUDED_IN_WITHDRAWAL', uid=entry['uid'])
        for before in entry['current_configuration_of_claims']:
            current = find_claim(c, before)
            if not current or current['status'] != before['status']:
                bad('LEGAL_OEM_OR_EPA_CLAIM_WITHDRAWN', uid=entry['uid'])
    metadata = {r['key']: json.loads(r['value']) for r in c.execute('SELECT * FROM metadata')}
    if not preflight:
        applied = metadata.get(STAGE, {}); frozen = metadata.get('structure_frozen_build_manifest', {}).get('inputs', {})
        if (applied.get('manifest_sha256') != sha(manifest_path.read_bytes()) or applied.get('operations_sha256') != sha(raw)
                or applied.get('operation_count') != len(ops) or applied.get('reference_count') != len(reference_ids)
                or applied.get('source_projection_count') != len(index)):
            bad('ACTUAL_APPLIED_METADATA_UNBOUND')
        for name, digest in ((INPUT_NAME, sha(manifest_path.read_bytes())), (operation_path.name, sha(raw))):
            if frozen.get(name) != digest: bad('FROZEN_INPUT_NOT_BOUND', name=name)
        for table in ('dataset_targets', 'dataset_mapping_checks'):
            if applied.get('mapping_snapshots_sha256', {}).get(table) != table_hash(c, table): bad('AUTHOR_MAPPING_CHANGED', table=table)
        total = c.execute("SELECT count(*) FROM entity_relations WHERE relation='SOURCE_MODEL_REFERENCE' AND source LIKE 'Reviewed author-derived configuration projection scope [%'").fetchone()[0]
        if total != len(ops): bad('EXTRA_OR_MISSING_SOURCE_REFERENCES', actual=total)
    report = {'schema': 'FINEATLAS_INDEPENDENT_CARS_PROJECTION_VIEW_AUDIT_V1', 'pass': not errors, 'preflight_only': preflight,
              'database': str(database), 'database_revision': metadata.get('database_revision'), 'release': metadata.get('release'),
              'manifest_sha256': sha(manifest_path.read_bytes()), 'operations_sha256': sha(raw), 'operation_count': len(ops),
              'operations': dict(Counter(x['relation'] for x in ops)), 'source_projection_count': len(index),
              'preserved_nonprojection_configurations': len(manifest['preserved_nonprojection_configs']), 'read_only': True, 'errors': errors}
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(report, indent=2) + '\n')
    c.close(); print(json.dumps(report)); return not errors


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database', type=Path, required=True); p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--preflight-only', action='store_true')
    a = p.parse_args(); raise SystemExit(0 if run(a.database, a.inputs, a.output, a.preflight_only) else 1)
