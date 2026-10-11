"""Append physical types entailed by an already reviewed complete body constraint.

Whole-range scope and author annotation equality are separate. A nameplate list
or partial EPA citation set is not an intensional configuration definition.
"""
from __future__ import annotations
import hashlib
import json
from .hierarchy import apply_refinements, validate_link_roles
from .semantics import role_expression

INPUT_NAME = 'structure_oem_body_scope_repairs.json'

def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()

def validate_oem_body_scope_repairs(c, manifest, operations):
    if manifest.get('schema') != 'FINEATLAS_OEM_BODY_SCOPE_REPAIRS_V1':
        raise ValueError('Unknown complete body-constraint repair schema')
    if not operations or len({(op['uid'], op['parent'], op['relation']) for op in operations}) != len(operations):
        raise ValueError('Body type operations must be nonempty and unique')
    for op in operations:
        proof = op['proof']
        if op.get('op') != 'link' or op.get('relation') not in {'CONFIGURATION_TYPE_OF', 'DESIGN_TYPE_OF'}:
            raise ValueError('Body constraint repair only appends physical type declarations')
        if proof.get('world_identity_assertion') is not False or proof.get('no_identity_merges') is not True:
            raise ValueError('Body type cannot establish exact world/annotation identity')
        if proof.get('whole_subject_intensional_scope') is not True or not proof.get('scope_observation'):
            raise ValueError('Complete declared body constraint is required, not a reference set')
        row = c.execute('SELECT n.*, ' + role_expression('n','p') + ' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?', (op['uid'],)).fetchone()
        parent = c.execute('SELECT n.*, ' + role_expression('n','p') + ' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?', (op['parent'],)).fetchone()
        if not row or not parent or row['visibility'] != 'ACTIVE' or parent['visibility'] != 'ACTIVE' or digest(row['data']) != proof['native_record_sha256'] or digest(parent['data']) != proof['parent_native_record_sha256']:
            raise ValueError('Physical body endpoints or complete source ranges changed')
        validate_link_roles(op['relation'], row['role'], parent['role'])
        raw = json.loads(row['data'])
        if raw.get('scope') != proof['own_complete_scope'] or not isinstance(raw.get('scope'),dict) or not {'manufacturer','model','body'} <= raw['scope'].keys():
            raise ValueError('Source object does not declare the reviewed complete body constraint')
        if row['role'] == 'CONFIGURATION' and (raw.get('projection_kind') != 'REUSABLE_MODEL_CONFIGURATION' or 'model_year' not in raw['scope']):
            raise ValueError('Configuration must retain the original declared reusable year/body range')
        eid = proof['original_scope_evidence_id']
        if eid not in raw.get('evidence_ids', []):
            raise ValueError('Scope evidence is not bound to this source object')
        evidence = c.execute('SELECT payload FROM evidence WHERE evidence_id=?',(eid,)).fetchone()
        if not evidence or digest(evidence[0]) != proof['original_scope_payload_sha256']:
            raise ValueError('Original complete scope evidence changed')
        payload = json.loads(evidence[0]); definition_scope = payload.get('scope', {})
        if payload.get('review',{}).get('verdict') != 'PASS' or not payload.get('definition') or any(definition_scope.get(k) != v for k,v in raw['scope'].items()):
            raise ValueError('Original reviewed definition does not entail this entire source range')
        if not proof.get('manufacturer_whole_body_scope_review') or not payload.get('proofs') or proof.get('manufacturer_material_hashes') != sorted(item['sha256'] for item in payload['proofs']):
            raise ValueError('Independent manufacturer whole-range body review is required')
        if proof['reviewed_type_sense'] == 'CAR_CONVERTIBLE':
            if raw['scope']['body'] != 'convertible' or parent['description'] != 'a car that has top that can be folded or removed':
                raise ValueError('Convertible type must be the physical car sense entailed by the body constraint')
        elif proof['reviewed_type_sense'] == 'MOTOR_CAR_COARSE_BODY_ONLY':
            if raw['scope']['body'] != 'coupe' or not parent['description'].startswith('a motor vehicle with four wheels') or proof.get('coupe_fine_scope_pending') is not True:
                raise ValueError('Unproved narrow coupe properties cannot be inferred from a factory body designation')
        else:
            raise ValueError('Unreviewed physical body type sense')

def apply_oem_body_scope_repairs(m):
    path = m.inputs / INPUT_NAME
    if not path.exists(): return {'status':'not_requested'}
    manifest = json.loads(path.read_text())
    if manifest['operations_file'] != 'hierarchy_type_repairs.jsonl':
        raise ValueError('Unexpected supplemental body operation input')
    raw = (m.inputs / manifest['operations_file']).read_bytes()
    if digest(raw) != manifest['operations_sha256']:
        raise ValueError('Body repair operation checksum differs')
    operations = [json.loads(line) for line in raw.decode().splitlines() if line]
    if len(operations) != manifest['operation_count']:
        raise ValueError('Body repair operations are incomplete')
    validate_oem_body_scope_repairs(m.c, manifest, operations)
    targets = [tuple(r) for r in m.c.execute('SELECT * FROM dataset_targets ORDER BY dataset,class_id')]
    checks = [tuple(r) for r in m.c.execute('SELECT * FROM dataset_mapping_checks ORDER BY dataset,class_id')]
    node_count = m.c.execute('SELECT count(*) FROM nodes').fetchone()[0]
    result = apply_refinements(m, manifest['operations_file'])
    if node_count != m.c.execute('SELECT count(*) FROM nodes').fetchone()[0] or targets != [tuple(r) for r in m.c.execute('SELECT * FROM dataset_targets ORDER BY dataset,class_id')] or checks != [tuple(r) for r in m.c.execute('SELECT * FROM dataset_mapping_checks ORDER BY dataset,class_id')]:
        raise ValueError('Physical type repair changed entities or exact author mappings')
    m.meta('oem_body_scope_repairs', {'manifest_sha256':digest(path.read_bytes()), 'operations_sha256':digest(raw), 'physical_types_added':len(operations), 'world_mapping_promotions':0, 'coupe_fine_scope_inferred':False})
    m.c.commit()
    return {'status':'PASS',**result,'world_mapping_promotions':0}
