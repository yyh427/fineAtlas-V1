#!/usr/bin/env python3
"""Independent SQL audit of manufacturer whole-body scope and physical types."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def run(database, inputs, output, preflight=False):
    manifest = json.loads((inputs / 'structure_oem_body_scope_repairs.json').read_text())
    raw = (inputs / manifest['operations_file']).read_bytes()
    ops = [json.loads(line) for line in raw.decode().splitlines() if line]
    errors = []
    if sha(raw) != manifest['operations_sha256'] or len(ops) != manifest['operation_count']:
        errors.append({'kind': 'INPUT_BINDING_CHANGED'})
    c = sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    c.row_factory = sqlite3.Row
    for op in ops:
        proof = op['proof']; uid = op['uid']
        node = c.execute('SELECT * FROM nodes WHERE uid=?', (uid,)).fetchone()
        parent = c.execute('SELECT * FROM nodes WHERE uid=?', (op['parent'],)).fetchone()
        if not node or not parent:
            errors.append({'kind': 'MISSING_ENDPOINT', 'uid': uid}); continue
        native = json.loads(node['data'])
        if sha(node['data']) != proof['native_record_sha256'] or sha(parent['data']) != proof['parent_native_record_sha256']:
            errors.append({'kind': 'ENTIRE_SOURCE_RANGE_CHANGED', 'uid': uid})
        if native.get('scope') != proof['own_complete_scope'] or proof['world_identity_assertion'] is not False:
            errors.append({'kind': 'COMPLETE_SCOPE_OR_IDENTITY_INVALID', 'uid': uid})
        evid = c.execute('SELECT payload FROM evidence WHERE evidence_id=?', (proof['original_scope_evidence_id'],)).fetchone()
        payload = json.loads(evid[0]) if evid else {}
        if not evid or sha(evid[0]) != proof['original_scope_payload_sha256'] or proof['original_scope_evidence_id'] not in native.get('evidence_ids', []):
            errors.append({'kind': 'ORIGINAL_SCOPE_BINDING_CHANGED', 'uid': uid})
        if payload.get('review', {}).get('verdict') != 'PASS' or not payload.get('definition') or any(payload.get('scope', {}).get(k) != v for k, v in native.get('scope', {}).items()):
            errors.append({'kind': 'COMPLETE_DECLARED_RANGE_UNPROVED', 'uid': uid})
        if proof['manufacturer_material_hashes'] != sorted(x['sha256'] for x in payload.get('proofs', [])):
            errors.append({'kind': 'MANUFACTURER_PROOF_NOT_BOUND', 'uid': uid})
        profile = c.execute('SELECT node_kind FROM node_profiles WHERE uid=?', (uid,)).fetchone()
        role = profile[0] if profile and profile[0] else ('CONFIGURATION' if node['rank'] in ('model_year', 'configuration', 'model_year_configuration') else 'MODEL' if node['rank'] in ('model', 'product_model', 'aircraft_model', 'vehicle_model') else 'CLASS')
        expected_role = 'CONFIGURATION' if op['relation'] == 'CONFIGURATION_TYPE_OF' else 'MODEL'
        if role != expected_role or node['visibility'] != 'ACTIVE' or parent['visibility'] != 'ACTIVE':
            errors.append({'kind': 'ROLE_OR_VISIBILITY_CHANGED', 'uid': uid})
        body = native.get('scope', {}).get('body')
        parent_profile = c.execute('SELECT node_kind FROM node_profiles WHERE uid=?', (op['parent'],)).fetchone()
        parent_role = parent_profile[0] if parent_profile and parent_profile[0] else ('CLASS' if parent['rank'] in ('', 'class') else parent['rank'].upper())
        if parent_role != 'CLASS':
            errors.append({'kind': 'PHYSICAL_PARENT_NOT_CANONICAL_CLASS', 'uid': uid})
        if body == 'convertible':
            if parent['description'] != 'a car that has top that can be folded or removed' or proof['reviewed_type_sense'] != 'CAR_CONVERTIBLE':
                errors.append({'kind': 'WRONG_CONVERTIBLE_SENSE', 'uid': uid})
        elif body == 'coupe':
            if not parent['description'].startswith('a motor vehicle with four wheels') or not proof.get('coupe_fine_scope_pending'):
                errors.append({'kind': 'UNPROVED_FINE_COUPE_SCOPE', 'uid': uid})
        else:
            errors.append({'kind': 'UNREVIEWED_BODY', 'uid': uid})
        if not preflight:
            rows = c.execute('SELECT r.status,e.payload FROM entity_relations r JOIN evidence e ON e.evidence_id=r.evidence_id WHERE r.subject_uid=? AND r.object_uid=? AND r.relation=? AND r.source=?', (uid, op['parent'], op['relation'], op['source'])).fetchall()
            if len(rows) != 1 or rows[0][0] != 'ACTIVE' or json.loads(rows[0][1]) != proof:
                errors.append({'kind': 'ACTUAL_PHYSICAL_TYPE_DIFFERS', 'uid': uid})
    if not preflight:
        count = c.execute('SELECT count(*) FROM entity_relations WHERE source=? AND status=?', (ops[0]['source'], 'ACTIVE')).fetchone()[0]
        if count != len(ops): errors.append({'kind': 'EXTRA_OR_MISSING_BODY_TYPES'})
        meta = c.execute("SELECT value FROM metadata WHERE key='oem_body_scope_repairs'").fetchone()
        if not meta or json.loads(meta[0]).get('manifest_sha256') != sha((inputs / 'structure_oem_body_scope_repairs.json').read_bytes()):
            errors.append({'kind': 'MANIFEST_NOT_BOUND'})
    metadata = {r['key']: json.loads(r['value']) for r in c.execute('SELECT * FROM metadata')}
    if not preflight:
        frozen = metadata.get('structure_frozen_build_manifest', {}).get('inputs', {})
        for name in ('structure_oem_body_scope_repairs.json', manifest['operations_file']):
            if frozen.get(name) != sha((inputs / name).read_bytes()):
                errors.append({'kind': 'FROZEN_BUILD_INPUT_NOT_BOUND', 'name': name})
    report = {'database_revision': metadata.get('database_revision'), 'release': metadata.get('release'), 'operations_sha256': sha(raw), 'operation_count': len(ops), 'incremental_inputs_frozen': not preflight, 'schema': 'FINEATLAS_INDEPENDENT_OEM_BODY_SCOPE_AUDIT_V1', 'pass': not errors, 'preflight_only': preflight, 'database': str(database), 'manifest_sha256': sha((inputs / 'structure_oem_body_scope_repairs.json').read_bytes()), 'operations': dict(Counter(x['relation'] for x in ops)), 'errors': errors}
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report)); c.close(); return not errors


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database', type=Path, required=True); p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--preflight', action='store_true')
    a = p.parse_args(); raise SystemExit(0 if run(a.database, a.inputs, a.output, a.preflight) else 1)
