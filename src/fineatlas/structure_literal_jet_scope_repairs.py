"""Retain a source-owned jet-aircraft genus without narrowing it to airplanes."""
from __future__ import annotations

import json
import re
from .hierarchy import source_assertion_sha256, validate_link_roles
from .semantics import role_expression
from .structure_regression_repairs import sha
from .structure_subject_scope_rules import own_family_scope, scoped_subject_genus

INPUT_NAME = 'structure_literal_jet_scope_repairs.json'
OPERATION_NAME = 'hierarchy_literal_jet_scope_repairs.jsonl'
METADATA_KEY = 'literal_jet_scope_repairs'
SOURCE = 'Reviewed literal source jet-aircraft physical scope'


def literal_jet_aircraft_first_scope(statement: str, label: str) -> bool:
    """Require the first entire subject scope to assert the physical compound.

    The retained generic parser checks the source subject, adjective grammar,
    grain and parts/fiction/coordination guards. The compound must occur in that
    first clause, never an incidental sentence, historical relative or example.
    """
    parsed = scoped_subject_genus(statement, label)
    if not parsed or parsed[0].casefold() != 'aircraft':
        return False
    first = re.split(r'[.;]|\s+(?:that|which|whose|with|without|for|to|in|near|of|by|from|since|used|intended|designed|developed|manufactured|produced|built|made|released|introduced|marketed|capable)\b', statement, maxsplit=1, flags=re.I)[0]
    return bool(re.search(r'\bjet\s+aircraft\s*$', first, re.I))


def parent_whole_jet_scope(statement: str, label: str) -> bool:
    text = re.sub(r'\([^()]*\)', '', statement).strip()
    match = re.match(r'^(?:A|An)\s+(.+?)\s+is an aircraft propelled by one or more jet engines\.', text, re.I)
    words = lambda value: re.findall(r'[a-z0-9]+', value.casefold())
    return bool(match and words(match[1]) == words(label))


def validate_literal_jet_scope_repairs(c, manifest: dict, operations: list[dict]) -> None:
    if manifest.get('schema') != 'FINEATLAS_LITERAL_JET_SCOPE_REPAIRS_V1':
        raise ValueError('Unknown literal jet scope repair schema')
    if not operations or len({(x['uid'], x['parent'], x['relation']) for x in operations}) != len(operations):
        raise ValueError('Literal jet scope operations must be nonempty and unique')
    for op in operations:
        proof = op['proof']
        if op.get('op') != 'link' or op.get('relation') != 'DESIGN_TYPE_OF' or op.get('source') != SOURCE or not op.get('uri'):
            raise ValueError('Literal jet repairs only append attributed physical design types')
        if proof.get('world_identity_assertion') is not False or proof.get('no_identity_merges') is not True or proof.get('whole_subject_scope_review') is not True or not proof.get('scope_observation'):
            raise ValueError('Physical source scope cannot establish exact world identity')
        endpoints = []
        for uid, key in ((op['uid'], 'native_record_sha256'), (op['parent'], 'parent_native_record_sha256')):
            n = c.execute('SELECT n.*, '+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?', (uid,)).fetchone()
            if not n or n['visibility'] != 'ACTIVE' or sha(n['data']) != proof[key]:
                raise ValueError('Frozen source endpoint or complete range changed')
            endpoints.append(n)
        child, parent = endpoints
        validate_link_roles(op['relation'], child['role'], parent['role'])
        if child['component_id'] == parent['component_id']:
            raise ValueError('A physical type cannot contract into source identity')
        witnesses = proof.get('source_witnesses', [])
        if len(witnesses) != 2 or witnesses[0]['uid'] != op['uid'] or witnesses[0]['field'] != 'description' or witnesses[1]['uid'] != op['parent'] or witnesses[1]['field'] != 'wikipedia_intro':
            raise ValueError('Both complete own-source and parent-source fields must be bound')
        for witness in witnesses:
            n = c.execute('SELECT data FROM nodes WHERE uid=?', (witness['uid'],)).fetchone()
            data = json.loads(n['data']) if n else {}
            statement = data.get(witness['field']) or data.get('evidence_record', {}).get(witness['field'])
            if not n or sha(n['data']) != witness['data_sha256'] or statement != witness['statement']:
                raise ValueError('Whole source witness changed')
        own = witnesses[0]['statement']
        if not literal_jet_aircraft_first_scope(own, child['label']) or (child['role'] == 'MODEL_FAMILY' and not own_family_scope(own, child['label'])):
            raise ValueError('Owned first subject clause does not declare its literal jet-aircraft type')
        if not parent_whole_jet_scope(witnesses[1]['statement'], parent['label']):
            raise ValueError('Parent is not the complete broader aircraft-with-jet-propulsion sense')
        reviewed_component = manifest['parent_components'][op['parent']]
        current = sorted(r['uid'] for r in c.execute('SELECT uid FROM nodes WHERE component_id=?', (parent['component_id'],)))
        if current != reviewed_component['uids']:
            raise ValueError('Reviewed physical source component changed')
        bridges = c.execute('SELECT * FROM bridges WHERE left_uid=? OR right_uid=?', (op['parent'], op['parent'])).fetchall()
        if sorted(source_assertion_sha256(r)+':'+r['status'] for r in bridges) != reviewed_component['bridge_content_status_hashes']:
            raise ValueError('Physical source equivalence or scope bridge changed')
        for prior in proof['prior_assertions']:
            rows = c.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?', tuple(prior[k] for k in ('subject_uid','object_uid','relation','source'))).fetchall()
            if not any(source_assertion_sha256(r) == prior['content_sha256'] and r['status'] == prior['status'] for r in rows):
                raise ValueError('Original source declaration or review changed')
        if c.execute('SELECT 1 FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?', (op['uid'],op['parent'],op['relation'],SOURCE)).fetchone():
            raise ValueError('Literal scope must start from an unapplied checkpoint')


def apply_literal_jet_scope_repairs(m):
    path = m.inputs / INPUT_NAME
    if not path.exists():
        return {'status': 'not_requested'}
    manifest = json.loads(path.read_text())
    if manifest['operations_file'] != OPERATION_NAME:
        raise ValueError('Unexpected literal jet operations path')
    raw = (m.inputs / OPERATION_NAME).read_bytes()
    operations = [json.loads(line) for line in raw.decode().splitlines() if line]
    if sha(raw) != manifest['operations_sha256'] or type(manifest['operation_count']) is not int or len(operations) != manifest['operation_count']:
        raise ValueError('Literal jet input checksum/count changed')
    validate_literal_jet_scope_repairs(m.c, manifest, operations)
    affected = sorted({op[k] for op in operations for k in ('uid','parent')})
    markers = ','.join('?' for _ in affected)
    before_counts = {t: m.c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('nodes','node_profiles')}
    before_nodes = [tuple(r) for r in m.c.execute('SELECT * FROM nodes WHERE uid IN ('+markers+') ORDER BY uid', affected)]
    before_profiles = [tuple(r) for r in m.c.execute('SELECT * FROM node_profiles WHERE uid IN ('+markers+') ORDER BY uid', affected)]
    before_mappings = {table: [tuple(r) for r in m.c.execute('SELECT * FROM '+table+' ORDER BY dataset,class_id')] for table in ('dataset_targets','dataset_mapping_checks')}
    for op in operations:
        before = [dict(r) for r in m.c.execute('SELECT * FROM entity_relations WHERE subject_uid=?', (op['uid'],))]
        m.typed(op['uid'], op['parent'], op['relation'], op['proof'], SOURCE, op['uri'])
        m.change(METADATA_KEY, 'physical_type_append', op['uid'], {'retained_source_claims': before}, {'added_parent': op['parent'], 'relation': op['relation']}, op['proof'])
    if any(before_counts[t] != m.c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in before_counts) or before_nodes != [tuple(r) for r in m.c.execute('SELECT * FROM nodes WHERE uid IN ('+markers+') ORDER BY uid', affected)] or before_profiles != [tuple(r) for r in m.c.execute('SELECT * FROM node_profiles WHERE uid IN ('+markers+') ORDER BY uid', affected)] or any(before_mappings[t] != [tuple(r) for r in m.c.execute('SELECT * FROM '+t+' ORDER BY dataset,class_id')] for t in before_mappings):
        raise ValueError('Literal physical type repair changed raw identities, roles or mappings')
    m.c.execute('INSERT OR REPLACE INTO source_catalogs VALUES (?,?,?,?,?)', ('Hierarchy refinement: '+SOURCE, operations[0]['uri'], 'Source-derived factual type assertions; original descriptive-text attribution and terms retained', sha(raw), json.dumps({'operations':len(operations),'source_fields_retained':True,'world_identity_promotions':0},sort_keys=True)))
    m.meta(METADATA_KEY, {'manifest_sha256': sha(path.read_bytes()), 'operations_sha256': sha(raw), 'operation_count': len(operations), 'world_identity_promotions': 0, 'new_nodes': 0, 'source_parent_range_not_fixed_wing_only': True, 'old_claims_retained': True})
    m.c.commit()
    return {'status': 'PASS', 'physical_types_added': len(operations), 'new_semantic_links': len(operations), 'world_identity_promotions': 0}
