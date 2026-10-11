#!/usr/bin/env python3
"""Independently inspect complete-source type repairs using read-only SQL.

This auditor deliberately imports neither the new builder nor its grammar.
Unsealed source diagnostics cannot count as candidate acceptance.
"""
from __future__ import annotations

if not __debug__:
    raise RuntimeError('Mandatory complete-source checks cannot run optimized')

import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

INPUT_NAME = 'structure_complete_owned_type_repairs.json'
SOURCE = 'Reviewed complete owned physical type and source range'
TABLE_KEYS = {'nodes': 'uid', 'node_profiles': 'uid', 'normalization_roles': 'uid',
              'edges': 'id', 'bridges': 'id', 'entity_relations': 'id',
              'evidence': 'evidence_id'}


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def row_at(con, table, identifier):
    if table not in TABLE_KEYS:
        raise ValueError('Unsafe witness table')
    row = con.execute('SELECT * FROM ' + table + ' WHERE ' + TABLE_KEYS[table] + '=?',
                      (identifier,)).fetchone()
    return dict(row) if row else None


def assertion_sha(row):
    return sha(json.dumps({k: v for k, v in row.items()
                          if k not in {'id', 'status', 'reason'}}, sort_keys=True))


def role(con, node):
    profile = row_at(con, 'node_profiles', node['uid'])
    if profile and profile.get('node_kind'):
        return profile['node_kind']
    return {'model': 'MODEL', 'product_model': 'MODEL', 'aircraft_model': 'MODEL',
            'vehicle_model': 'MODEL', 'series': 'MODEL_FAMILY', 'model_family': 'MODEL_FAMILY',
            'configuration': 'CONFIGURATION', 'instance': 'INSTANCE',
            'unknown': 'UNKNOWN', 'type_or_product_model': 'UNKNOWN',
            'biological_variant': 'BIOLOGICAL_VARIANT', 'dataset_category': 'DATASET_CATEGORY',
            'manufacturer': 'ORGANIZATION', 'attribute': 'ATTRIBUTE'}.get(
                (node.get('rank') or '').lower(), 'CLASS')


def source_field(con, witness):
    node = row_at(con, 'nodes', witness['uid'])
    if not node or sha(node['data']) != witness['data_sha256']:
        raise ValueError('Complete source object bytes do not match the witness')
    data = json.loads(node['data'])
    value = data
    path = witness.get('field_path') or witness.get('field')
    if not isinstance(path, (str, list)):
        raise ValueError('Explicit retained source field path required')
    parts = path.split('.') if isinstance(path, str) else path
    for part in parts:
        value = value.get(part) if isinstance(value, dict) else None
    if value is None and len(parts) == 1:
        value = data.get('evidence_record', {}).get(parts[0])
    if value != witness['statement'] or not isinstance(value, str) or not value.strip():
        raise ValueError('Source witness is not the exact complete retained field')
    return node, value


def complete_source_fields(node):
    data = json.loads(node['data'])
    fields = {}
    for name in ('description', 'wikidata_description', 'definition', 'wikipedia_intro', 'gloss'):
        value, path = data.get(name), name
        if value is None:
            value, path = data.get('evidence_record', {}).get(name), 'evidence_record.' + name
        if isinstance(value, str) and value:
            fields[path] = value
    return fields


def verify_complete_scope_fields(node, witnesses):
    data = json.loads(node['data']); actual = []
    names = ('description','wikidata_description','definition','wikipedia_intro','gloss')
    for container in (data, data.get('evidence_record', {})):
        for name in names:
            value = container.get(name)
            if isinstance(value,str) and value:
                actual.append((name,value))
    declared = {(str(w.get('field_path') or w.get('field')).split('.')[-1],w['statement'])
                for w in witnesses if w['uid']==node['uid']}
    # Repeated adapter aliases with equal values add no new scope. Distinct
    # complete source values still require their own exact retained witness.
    if declared != set(actual):
        raise ValueError('A complete retained own or parent scope value was omitted or changed')


def verify_parent_component(con, manifest, uid):
    reviewed = manifest['parent_components'][uid]
    parent = row_at(con, 'nodes', uid)
    if parent != reviewed['before_node']:
        raise ValueError('Whole parent source node changed')
    for table, key in (('node_profiles', 'before_profile'),
                       ('normalization_roles', 'before_normalization_role')):
        if row_at(con, table, uid) != reviewed[key]:
            raise ValueError('Independent whole parent role declaration changed')
    nodes = [dict(r) for r in con.execute('SELECT * FROM nodes WHERE component_id=? ORDER BY uid',
                                         (parent['component_id'],))]
    if nodes != reviewed['component_nodes']:
        raise ValueError('Whole source parent identity component changed')
    for table, key in (('bridges', 'component_bridges'), ('edges', 'parent_edges'),
                       ('entity_relations', 'parent_typed')):
        for before in reviewed[key]:
            if row_at(con, table, before['id']) != before:
                raise ValueError('Retained parent source claim or scope disposition changed')


def exact_source_review_record(inputs, proof, locator_key, record_key, uid):
    locator = proof[locator_key]; name = locator['file']
    if Path(name).name != name or locator['uid'] != uid:
        raise ValueError('Unsafe or unrelated complete source verdict')
    raw = (inputs / name).read_bytes()
    if sha(raw) != locator['sha256']:
        raise ValueError('Exact independent source verdict bytes changed')
    records = [r for r in json.loads(raw)['records'] if r['uid'] == uid]
    if len(records) != 1 or records[0] != proof[record_key]:
        raise ValueError('Complete source verdict differs from exact reviewed record')
    return records[0]


def independently_check_serial_instance(con, inputs, op, ops, preflight):
    proof = op['proof']; uid = op['uid']
    record = exact_source_review_record(inputs, proof, 'source_instance_review_locator',
                                       'source_instance_review_record', uid)
    if (record.get('approved_new_role') != 'INSTANCE'
            or record.get('source_grain_disposition') != 'OWN_SERIAL_AND_OPERATIONAL_DESIGNATION_SUPPORT_INSTANCE'):
        raise ValueError('No independent approval of complete serial individual scope')
    retained = record['complete_source_record']; node = row_at(con, 'nodes', uid)
    if node != retained['before_node'] or sha(node['data']) != proof['native_record_sha256']:
        raise ValueError('Complete individual source object changed')
    fields = retained['all_own_fields']
    for witness in fields:
        if witness['uid'] != uid:
            raise ValueError('Individual grain cannot come from another object')
        source_field(con, witness)
    verify_complete_scope_fields(node,fields)
    full = ' '.join(w['statement'] for w in fields)
    if not (re.search(r'\b\d+(?:st|nd|rd|th)\s+airship\s+built\b', full, re.I)
            and re.search(r'\b(?:tactical|military)\s+(?:designation|number)|\bserved\b.+\bas\s+L\d+', full, re.I)):
        raise ValueError('Ordinal name alone does not identify an individual built physical entity')
    if op['op'] == 'correct_role':
        inventory = proof['before_scope_declarations']
        selections = (('edges_incoming','edges','parent_uid'), ('edges_outgoing','edges','child_uid'),
                      ('typed_incoming','entity_relations','object_uid'), ('typed_outgoing','entity_relations','subject_uid'))
        migrations = {o['before_assertion']['id']: o for o in ops if o['op'] == 'review_typed_relation'}
        for key, table, column in selections:
            rows = [dict(r) for r in con.execute('SELECT * FROM '+table+' WHERE '+column+'=? ORDER BY id',(uid,))]
            # New directions are independently checked below; only preserved
            # old inventory is compared with the original scope declaration.
            if not preflight:
                rows = [r for r in rows if r['source'] != SOURCE]
                for row in rows:
                    migration = migrations.get(row['id']) if table == 'entity_relations' else None
                    if migration:
                        if row != {**migration['before_assertion'], 'status': migration['after_status']}:
                            raise ValueError('Old individual encoding changed beyond exact approved status')
                        row['status'] = migration['before_assertion']['status']
            if rows != inventory[key]:
                raise ValueError('Individual before scope inventory changed')
            if key == 'edges_outgoing' and any(r['status'] in {'ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE'} for r in rows):
                raise ValueError('An active class edge needs a separate precise individual migration')
            if key == 'typed_outgoing':
                for row in rows:
                    if row['status'] == 'ACTIVE' and row['relation'] != 'INSTANCE_OF' and row['id'] not in migrations:
                        raise ValueError('Individual role would abandon a legal physical assertion')
        bridges = [dict(r) for r in con.execute('SELECT * FROM bridges WHERE left_uid=? OR right_uid=? ORDER BY id',(uid,uid))]
        if bridges != inventory['identity_bridges'] or any(r['status'] == 'ACTIVE' for r in bridges):
            raise ValueError('Individual identity component requires its own scope adjudication')
    return record


def independently_check_typed_review(con, inputs, op, ops, preflight):
    proof = op['proof']; before = op['before_assertion']
    independently_check_serial_instance(con, inputs, op, ops, preflight)
    if (proof.get('kind') != 'INSTANCE_SCOPE_TYPED_ENCODING_MIGRATION'
            or proof.get('original_physical_fact_retained') is not True
            or before['subject_uid'] != op['uid'] or before['object_uid'] != op['parent']
            or before['relation'] != op['relation'] or op['relation'] != 'DESIGN_TYPE_OF'
            or before['status'] != 'ACTIVE' or op['after_status'] != 'SOURCE_SCOPE_REVIEW'
            or assertion_sha(before) != op['content_sha256']):
        raise ValueError('Unsupported or ungrounded original physical encoding review')
    replacement = [o for o in ops if o['op'] == 'link' and o['uid'] == op['uid']
                   and o['parent'] == proof['replacement_parent'] and o['relation'] == 'INSTANCE_OF']
    corrected = [o for o in ops if o['op'] == 'correct_role' and o['uid'] == op['uid']
                 and o['after_profile']['node_kind'] == 'INSTANCE']
    if len(replacement) != 1 or len(corrected) != 1:
        raise ValueError('Reviewed physical fact lacks its exact new compatible classification')
    actual = row_at(con, 'entity_relations', before['id'])
    if actual != (before if preflight else {**before, 'status': op['after_status']}):
        raise ValueError('Actual original relation changed beyond approved encoding status')
    if not preflight:
        rows = con.execute('SELECT before_json,after_json,evidence FROM usability_changes WHERE stage=? AND object_type=? AND object_id=?',
                           ('complete_owned_type_repairs','typed_scope_review',str(before['id']))).fetchall()
        if sum(json.loads(r['before_json']) == before and json.loads(r['after_json']) == {'status':op['after_status']}
               and json.loads(r['evidence']) == proof for r in rows) != 1:
            raise ValueError('Exact original physical fact review history is missing')
    return {'uid':op['uid'],'parent':op['parent'],'relation':op['relation'],'reviewed_original_id':before['id']}


def independently_check_additional_grain(con, inputs, op):
    proof = op['proof']; uid = op['uid']
    record = exact_source_review_record(inputs, proof, 'source_additional_role_review_locator',
                                       'source_additional_role_review_record', uid)
    retained = record.get('complete_source_census_record') or record.get('complete_source_record')
    before_node = retained.get('complete_before_node') or retained.get('before_node')
    node = row_at(con, 'nodes', uid)
    raw_before = {k:v for k,v in before_node.items() if k not in {'node_kind','virtual_role'}}
    if node != raw_before or node != proof.get('complete_before_node', node) or sha(node['data']) != proof['native_record_sha256']:
        raise ValueError('Whole additional source object changed')
    witnesses = retained.get('all_retained_own_contexts') or retained.get('all_own_fields')
    fields = {}
    for witness in witnesses:
        if witness['uid'] != uid:
            raise ValueError('Own grain cannot be inferred from another design or entity')
        _, statement = source_field(con, witness)
        fields[witness.get('field_path') or witness.get('field')] = statement
    verify_complete_scope_fields(node,witnesses)
    full = ' '.join(fields.values()); target = record.get('approved_new_role')
    if target == 'MODEL':
        if (record.get('source_role_scope_kind') != 'OWNED_REUSABLE_MANUFACTURER_KIT_AIRCRAFT_DESIGN'
                or not re.search(r'\bdesigned by\b', full, re.I)
                or not re.search(r'\b(?:plans or in kit form|plans or kits)\b', full, re.I)):
            raise ValueError('Kit design needs explicit reusable plans and own design evidence')
    elif target == 'INSTANCE':
        if (record.get('source_role_scope_kind') != 'OWNED_NAMED_OPERATIONAL_AIRCRAFT_WITH_SPECIFIC_CONFIGURATION_AND_COST'
                or not re.search(r'\boperated by\b', full, re.I)
                or not re.search(r'\bcost\b.+\b(?:acquire|interior|fit)\b', full, re.I)
                or not re.search(r'\bjet.s name\b', full, re.I)):
            raise ValueError('Named individual requires its own operational and fitted-airframe scope')
    elif target is None:
        if (record.get('source_grain_disposition') != 'OWN_UNNAMED_PHYSICAL_OBJECT_VS_UNIQUE_DESIGN_GRAIN_AMBIGUOUS'
                or not re.search(r'\bunnamed\b', full, re.I)
                or not re.search(r'\b(?:aircraft|plane|machine)\b', full, re.I)):
            raise ValueError('Uncertain design versus entity scope needs its explicit complete source review')
        target = 'UNKNOWN'
    else:
        raise ValueError('Additional grain requires a separately reviewed contract')
    if op['op'] == 'correct_role' and op['after_profile']['node_kind'] != target:
        raise ValueError('Additional role differs from its independently reviewed own grain')
    return record, target


def independently_check_scope_inventory(con, proof, ops, preflight):
    uid = proof['complete_before_node']['uid']; inventory = proof['before_scope_declarations']
    reviews = {(('edges' if o['op'] == 'review_class_edge' else 'entity_relations'),o['before_assertion']['id']):o
               for o in ops if o['op'] in {'review_class_edge','review_typed_relation'}}
    for key, table, column in (('edges_incoming','edges','parent_uid'), ('edges_outgoing','edges','child_uid'),
                               ('typed_incoming','entity_relations','object_uid'), ('typed_outgoing','entity_relations','subject_uid')):
        rows = [dict(r) for r in con.execute('SELECT * FROM '+table+' WHERE '+column+'=? ORDER BY id',(uid,))]
        if not preflight:
            rows = [r for r in rows if r['source'] != SOURCE]
            for row in rows:
                change = reviews.get((table,row['id']))
                if change:
                    if row != {**change['before_assertion'],'status':change['after_status']}:
                        raise ValueError('Old source classification changed beyond exact approved encoding')
                    row['status'] = change['before_assertion']['status']
        if rows != inventory[key]:
            raise ValueError('Whole additional-role before inventory changed')
        if key.endswith('outgoing'):
            for row in rows:
                if row['status'] in {'ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE'} and (table,row['id']) not in reviews:
                    raise ValueError('New grain would abandon an active classification')
    rows = [dict(r) for r in con.execute('SELECT * FROM bridges WHERE left_uid=? OR right_uid=? ORDER BY id',(uid,uid))]
    if rows != inventory['identity_bridges'] or any(r['status'] == 'ACTIVE' for r in rows):
        raise ValueError('New grain cannot silently alter an active identity component')


def independently_check_additional_review(con, inputs, op, ops, preflight):
    proof = op['proof']; before = op['before_assertion']
    independently_check_additional_grain(con, inputs, op)
    table = 'edges' if op['op'] == 'review_class_edge' else 'entity_relations'
    left,right = ('child_uid','parent_uid') if table == 'edges' else ('subject_uid','object_uid')
    if (proof.get('kind') != 'SOURCE_OWNED_GRAIN_INCOMPATIBLE_CLASSIFICATION_REVIEW'
            or proof.get('original_source_fact_retained') is not True
            or proof.get('ordinary_class_inclusion_not_asserted') is not True
            or before[left] != op['uid'] or before[right] != op['parent']
            or before['relation'] != op['relation'] or before['status'] != 'ACTIVE'
            or op['after_status'] != 'SOURCE_SCOPE_REVIEW' or assertion_sha(before) != op['content_sha256']):
        raise ValueError('Additional encoding review is not the complete exact old assertion')
    roles = [o for o in ops if o['op']=='correct_role' and o['uid']==op['uid']]
    references = [o for o in ops if o['op']=='retain_source_scope_reference'
                  and o['proof']['original_assertion_table']==table and o['proof']['original_assertion']==before]
    if len(roles)!=1 or len(references)!=1 or roles[0]['after_profile']['node_kind'] not in {'INSTANCE','UNKNOWN'}:
        raise ValueError('Reviewed classification needs its exact grain correction and retained source reference')
    if proof['role_correction_evidence_id'] != roles[0]['after_profile']['evidence_id']:
        raise ValueError('Encoding review references another role adjudication')
    actual = row_at(con,table,before['id'])
    if actual != (before if preflight else {**before,'status':op['after_status']}):
        raise ValueError('Exact original source classification changed')
    if not preflight:
        object_type = 'class_scope_review' if table=='edges' else 'typed_scope_review'
        rows=con.execute('SELECT before_json,after_json,evidence FROM usability_changes WHERE stage=? AND object_type=? AND object_id=?',
                         ('complete_owned_type_repairs',object_type,str(before['id']))).fetchall()
        if sum(json.loads(r['before_json'])==before and json.loads(r['after_json'])=={'status':op['after_status']}
               and json.loads(r['evidence'])==proof for r in rows)!=1:
            raise ValueError('Exactly one precise additional-grain classification history required')
    return {'uid':op['uid'],'parent':op['parent'],'relation':op['relation'],'reviewed_original_id':before['id']}


def independently_check_source_reference(con, inputs, op, ops, preflight):
    proof=op['proof']; independently_check_additional_grain(con,inputs,op)
    before=proof['original_assertion']; table=proof['original_assertion_table']
    if (table not in {'edges','entity_relations'} or assertion_sha(before)!=proof['original_assertion_content_sha256']
            or proof.get('kind')!='RETAINED_SOURCE_SCOPE_REFERENCE_AFTER_GRAIN_REVIEW'
            or proof.get('navigation_allowed') is not False or proof.get('allowed_views')!=[]
            or proof.get('is_class_inclusion') is not False or proof.get('design_or_instance_grain_certified') is not False
            or op['relation'] not in {'SOURCE_NATIVE_CLASSIFICATION_REFERENCE','SOURCE_PHYSICAL_CLASS_REFERENCE'}):
        raise ValueError('Retained scope reference cannot assert navigation, identity or distances')
    reviews=[o for o in ops if o['op'] in {'review_class_edge','review_typed_relation'} and o['before_assertion']==before]
    if len(reviews)!=1 or reviews[0]['uid']!=op['uid'] or reviews[0]['parent']!=op['parent']:
        raise ValueError('Retained reference lacks its exact original classification migration')
    if not preflight:
        rows=con.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',
                         (op['uid'],op['parent'],op['relation'],SOURCE)).fetchall()
        if len(rows)!=1 or rows[0]['status']!='SOURCE_DECLARED':
            raise ValueError('Retained source scope must remain a single non-navigation declaration')
        data=json.loads(rows[0]['data'])
        if data.get('admission_basis')!=proof or data.get('navigation_allowed') is not False or data.get('allowed_views')!=[]:
            raise ValueError('Retained non-navigation scope differs from precise source proof')
        eid='usability:'+sha(dump(proof));evidence=row_at(con,'evidence',eid)
        if not evidence or evidence['payload']!=dump(proof) or evidence['payload_sha256']!=sha(dump(proof)) or evidence['source_name']!=SOURCE or evidence['source_uri']!=op['uri'] or rows[0]['evidence_id']!=eid:
            raise ValueError('Non-navigation reference lost its canonical whole-source evidence')
        histories=con.execute('SELECT before_json,after_json,evidence FROM usability_changes WHERE stage=? AND object_type=? AND object_id=?',
                              ('complete_owned_type_repairs','complete_owned_source_scope_reference',op['uid'])).fetchall()
        if sum(json.loads(r['before_json'])==before and json.loads(r['after_json'])==dict(rows[0]) and json.loads(r['evidence'])==proof for r in histories)!=1:
            raise ValueError('Retained original source declaration lacks its exact history')
    return {'uid':op['uid'],'parent':op['parent'],'relation':op['relation'],'navigation_allowed':False}


def independently_check_role(con, inputs, op, preflight, ops=()):
    proof = op['proof']
    node = row_at(con, 'nodes', op['uid'])
    is_instance = proof.get('kind') == 'INSTANCE_SCOPE_ROLE_MIGRATION'
    is_additional = proof.get('kind') == 'SOURCE_OWNED_ADDITIONAL_GRAIN_MIGRATION_V1'
    if (op['uid'] != op['parent'] or op['relation'] != 'ROLE_ADJUDICATION'
            or proof.get('kind') not in {'SOURCE_OWNED_GRAIN_CORRECTION_V1', 'INSTANCE_SCOPE_ROLE_MIGRATION','SOURCE_OWNED_ADDITIONAL_GRAIN_MIGRATION_V1'}
            or (not is_instance and not is_additional and proof.get('source_native_objects_preserved') is not True)
            or proof.get('no_identity_merges') is not True
            or not node or sha(node['data']) != proof['native_record_sha256']):
        raise ValueError('Role correction is not bound to the preserved source object')
    if is_additional:
        source_record,target = independently_check_additional_grain(con,inputs,op)
        independently_check_scope_inventory(con,proof,ops,preflight)
    else:
        source_record = (independently_check_serial_instance(con, inputs, op, ops, preflight) if is_instance
                         else exact_source_review_record(inputs, proof, 'source_role_review_locator', 'source_role_review_record', op['uid']))
        target = op['after_profile']['node_kind']
        if source_record.get('approved_new_role' if is_instance else 'approved_role') != target:
            raise ValueError('Role correction differs from the complete own source judgement')
    statements = []
    for witness in proof['source_witnesses']:
        if witness['uid'] != op['uid']:
            raise ValueError('Another source object cannot supply this role')
        statements.append(source_field(con, witness)[1])
    own_fields = {w.get('field_path') or w.get('field'): w['statement'] for w in proof['source_witnesses']}
    verify_complete_scope_fields(node,proof['source_witnesses'])
    full = ' '.join(statements)
    kind = proof['source_role_scope_kind']
    if target == 'CLASS':
        if (kind != 'OWNED_UNIVERSAL_DESIGN_CATEGORY_ACROSS_NAMED_MANUFACTURER_MODELS'
                or not re.search(r'\btype of\b', full, re.I)
                or not re.search(r'\b(?:manufacturers|manufactured by different|category)\b', full, re.I)):
            raise ValueError('Universal category needs explicit independent class grain')
    elif target == 'MODEL_FAMILY':
        if (kind != 'OWNED_NAMED_PROGRAMME_WITH_EXPLICIT_DISTINCT_MODEL_VERSIONS'
                or not (re.search(r'\bin its various incarnations\b', full, re.I)
                        or re.search(r'\blaboratory model\b[^.]*\bdesignated\b[^.]*\bproduction as\b', full, re.I))):
            raise ValueError('Named family requires explicit own multi-version scope')
    elif target == 'MODEL':
        allowed = {'OWNED_REUSABLE_NAMED_DESIGN_PROGRAMME',
                   'OWNED_REUSABLE_HOMEBUILT_AIRCRAFT_DESIGN_FOR_CONSTRUCTION',
                   'OWNED_REUSABLE_MANUFACTURER_KIT_AIRCRAFT_DESIGN'}
        if kind not in allowed or not re.search(
                r'\b(?:production|manufactured|processor|project|their own copy|participants|'
                r'homebuilt construction|kit form|amateur construction)\b', full, re.I):
            raise ValueError('Reusable design programme requires explicit complete source evidence')
    elif target == 'INSTANCE':
        if not ((is_instance and kind == 'OWNED_SERIAL_AND_OPERATIONAL_DESIGNATION_PHYSICAL_INSTANCE') or (is_additional and kind == 'OWNED_NAMED_OPERATIONAL_AIRCRAFT_WITH_SPECIFIC_CONFIGURATION_AND_COST')):
            raise ValueError('Individual grain needs its precise independent contract')
    elif target == 'UNKNOWN':
        if not is_additional or kind != 'SOURCE_MODEL_OR_INDIVIDUAL_SCOPE_PENDING' or proof.get('role_status') != 'REVIEW' or proof.get('allowed_views') != []:
            raise ValueError('Uncertain grain must remain explicit REVIEW outside navigation views')
    else:
        raise ValueError('New role scope requires a separate independent contract')
    eid = 'usability:' + sha(dump(proof))
    before = op['before_profile']
    old_norm = op['before_normalization_role']
    attrs = json.loads(before['attributes']) if before else {}
    attrs.update(source_role=proof['source_role'], native_rank=node['rank'],
                 role_status='REVIEW' if target=='UNKNOWN' else 'VERIFIED', role_evidence_id=eid)
    if proof.get('allowed_views') is not None:
        if (not is_instance and not is_additional) or proof['allowed_views'] != ([] if target=='UNKNOWN' else ['taxonomy','membership']):
            raise ValueError('Unexpected role view migration')
        attrs['allowed_views'] = proof['allowed_views']
    attrs.pop('canonical_scope_guard', None)
    attrs.pop('canonical_scope_evidence_id', None)
    if target == 'CLASS' and proof.get('basis') == 'REVIEWED_GENERIC_WHOLE_SUBJECT_REPLACES_ADAPTER_DESIGN_ROLE':
        if (proof.get('individual_semantic_review') is not True
                or proof.get('source_statement') not in statements
                or not proof.get('subject_kind_head') or not proof.get('scope_observation')):
            raise ValueError('Generic class guard must bind the complete own semantic evidence')
        attrs.update(canonical_scope_guard='GENERIC_PHYSICAL_KIND', canonical_scope_evidence_id=eid)
    expected_profile = {**(before or {'uid': node['uid'], 'domain': node['domain']}),
                        'node_kind': target, 'source_uri': op['uri'],
                        'evidence_id': eid, 'attributes': dump(attrs)}
    expected_norm = {**(old_norm or {'uid': node['uid'], 'source_role': proof['source_role'],
                        'status': 'VERIFIED', 'prior_profile': dump(before or {})}),
                     'canonical_role': target, 'evidence_id': eid, 'source': SOURCE}
    if target == 'UNKNOWN':
        expected_norm['status'] = 'REVIEW'
    if op['after_profile'] != expected_profile or op['after_normalization_role'] != expected_norm:
        raise ValueError('Role adjudication changed unrelated fields or canonical serialization')
    for table, suffix in (('node_profiles', 'profile'), ('normalization_roles', 'normalization_role')):
        expected = op[('before_' if preflight else 'after_') + suffix]
        if row_at(con, table, op['uid']) != expected:
            raise ValueError('Actual role profile differs from the exact source adjudication')
    if op['after_profile']['evidence_id'] != eid or op['after_normalization_role']['evidence_id'] != eid:
        raise ValueError('Role correction lacks canonical complete-source evidence binding')
    if not preflight:
        evidence = row_at(con, 'evidence', eid)
        if (not evidence or evidence['payload'] != dump(proof) or evidence['payload_sha256'] != sha(dump(proof))
                or evidence['source_name'] != SOURCE or evidence['source_uri'] != op['uri']):
            raise ValueError('Actual role evidence differs from its whole source adjudication')
        histories = con.execute('SELECT before_json,after_json,evidence FROM usability_changes '
            'WHERE stage=? AND object_type=? AND object_id=?',
            ('complete_owned_type_repairs', 'role_source_adjudication', op['uid'])).fetchall()
        before = {'profile': op['before_profile'], 'normalization_role': op['before_normalization_role']}
        after = {'profile': op['after_profile'], 'normalization_role': op['after_normalization_role']}
        matches = [h for h in histories if json.loads(h['before_json']) == before
                   and json.loads(h['after_json']) == after and json.loads(h['evidence']) == proof]
        if len(matches) != 1:
            raise ValueError('Exactly one preserved complete-source role history required')
    return {'uid': op['uid'], 'parent': op['parent'], 'relation': op['relation'],
            'canonical_role': target, 'complete_source_sha256': proof['native_record_sha256']}


def owned_predicate(statement, label, names=(), allow_other_kinds=False):
    text = statement.strip()
    copula = re.search(r'\b(?:is|was|are|were)\s+', text, re.I)
    if copula:
        lead = text[:copula.start()].strip()
        while re.search(r'\([^()]*\)', lead):
            lead = re.sub(r'\([^()]*\)', '', lead)
        lead = re.sub(r'^(?:the|an?)\s+', '', lead.strip(), flags=re.I)
        tokens = lambda s: re.findall(r'[^\W_]+', ''.join(c for c in unicodedata.normalize('NFKD', s.casefold()) if not unicodedata.combining(c)))
        alternatives = re.split(r'\s+(?:or|also known as|also called|sometimes referred to as)\s+|,', lead, flags=re.I)
        alternatives = [re.sub(r'[\"“”]', '', a).strip(' -') for a in alternatives]
        def grounded_name(a):
            actual = tokens(a)
            # A retained full own name may include the manufacturer, nickname
            # or coordinated designs. Classification concerns its first own
            # physical declaration, with exact source bytes and SOURCE verdict
            # checked independently; this does not create an identity merge.
            for name in (label, *names):
                own = tokens(name)
                if own and any(actual[i:i+len(own)] == own for i in range(len(actual))):
                    return True
            return False
        if not any(grounded_name(a) for a in alternatives):
            raise ValueError('Physical assertion belongs to another named subject')
        predicate = text[copula.end():]
    else:
        predicate = text
    member = re.match(r'(?:an?\s+)?member of (?:the\s+)?[^.;]+? '
                      r'(?:family|series|range) of (.+)', predicate, re.I)
    if member:
        predicate = member[1]
    predicate = re.sub(r'\bamateur built\b', 'amateur-built', predicate, flags=re.I)
    predicate = re.sub(r'\bdesigned and built\b(?=[^.;]*\b(?:aircraft|monoplane|biplane|airplane)\b)', '', predicate, flags=re.I)
    predicate = re.split(r'[.;]|\s+(?:which|that|whose|derived|based|replacing|built|'
                         r'manufactured|produced|introduced|made|from|by|used|for)\b',
                         predicate, maxsplit=1, flags=re.I)[0]
    if re.search(r'\b(?:not|fictional|virtual|imaginary|toy|replica|scale model)\b|\bnever (?:an?|real|physical)\b',
                 predicate, re.I):
        raise ValueError('Incompatible scope cannot establish a physical type')
    without_engine_count = re.sub(r'\b(?:single|twin|two|three|four|2|3|4)[ -]+engine(?:d|s)?\b',
                                 '', predicate, flags=re.I)
    if not allow_other_kinds and re.search(r'\b(?:engine|component|part|system|vehicle|car|automobile|water|vapor|vapour)\b',
                 without_engine_count, re.I):
        raise ValueError('Aircraft predicate refers to a different physical kind')
    return predicate


# Each contract expresses the source parent's physical meaning. Endpoint IDs
# are not a substitute for the complete source definition checked below.
PHYSICAL_SENSES = (
    (r"\btriplanes?\b", r"\b(?:3|three) main lifting surfaces\b"),
    (r"\bmonoplanes?\b", r"\bone main lifting surface\b"),
    (r"\bbiplanes?\b", r"\btwo main wings stacked\b"),
    (r"\bflying boats?\b", r"\baircraft\b.*\bboat hull\b.*\bwater\b"),
    (r"\b(?:seaplanes?|floatplanes?)\b", r"\bfixed-wing aircraft\b.*\b(?:landing|alighting)\b.*\bwater\b"),
    (r"\b(?:autogyros?|autogiros?|gyroplanes?|gyrocopters?)\b", r"\brotorcraft\b.*\brotor unpowered\b"),
    (r"\bhelicopters?\b", r"\bpowered rotary wings\b.*\blift\b"),
    (r"\b(?:airships?|dirigibles?)\b", r"\bpowered lighter-than-air aircraft\b"),
    (r"\b(?:motor[ -]?gliders?)\b", r"\bglider equipped with a motor\b"),
    (r"\b(?:gliders?|sailplanes?)\b", r"\bfree flight does not depend on an engine\b"),
    (r"\bfixed[ -]wing aircraft\b", r"\bheavier-than-air aircraft\b.*\bfixed wings\b"),
    (r"\b(?:airplanes?|aeroplanes?)\b", r"\baircraft that has a fixed wing\b.*\bpowered by propellers or jets\b"),
    (r"\b(?:aircraft|rotorcraft)\b", r"\ba vehicle that can fly\b"),
    (r"\bdigital cameras?\b", r"\bcamera that uses digital storage to capture images\b"),
    (r"\bcameras?\b", r"\binstrument used to capture and store images\b"),
    (r"\bpersonal computers?\b", r"\bcomputer designed for personal use\b"),
    (r"\b(?:laptops?|(?:sub)?notebook computers?)\b", r"\bportable computer small enough to use in your lap\b"),
    (r"\bmicroprocessors?\b", r"\bcomputer processor\b.*\bintegrated circuit\b"),
    (r"\bcomputers?\b", r"\bmachine for performing calculations automatically\b"),
    (r"\blocomotives?\b", r"\bself-propelled engine\b.*\bdraw trains along railway tracks\b"),
    (r"\bmusical instruments?\b", r"\bdevices or contrivances\b.*\bproduce musical tones or sounds\b"),
    (r"\bmedical devices?\b", r"\bdevice intended to be used for medical purposes\b"),
    (r"\bgarments?\b",r"\ban article of clothing\b"),
    (r"\bloudspeakers?\b",r"\belectro-acoustic transducer\b.*\bconverts electrical signals into sounds\b"),
    (r"\bcapacitors?\b",r"\belectrical device\b.*\bcapacity to store an electric charge\b"),
    (r"\bdesserts?\b",r"\bdish that consists of sweet foods\b"),
)


def independent_physical_entailment(phrase, definitions):
    """Compare the owned first predicate against the whole parent's meaning."""
    flag = re.I | re.S
    plane = bool(re.search(r"\b(?:airliners?|airplanes?|aeroplanes?|fixed[ -]wing)\b", phrase, re.I))
    jet = bool(re.search(r"\b(?:jet|twinjet|twin[ -]jet|trijet|quadjet)\b", phrase, re.I))
    if re.search(r"\btwo jet engines\b", definitions, re.I):
        return plane and jet and bool(re.search(r"\btwin[ -]?jet\b|\b(?:twin|two|2)[ -]engine", phrase, re.I))
    if re.search(r"\bexternal propeller\b.*\bdriven by a turbojet engine\b", definitions, flag):
        return plane and bool(re.search(r"\bturboprop\b", phrase, re.I))
    if re.search(r"\ban airplane powered by one or more jet engines\b", definitions, re.I):
        return plane and jet
    if re.search(r"\baircraft\b.*\b(?:powered|propelled)\b.*\bjet (?:propulsion )?engines?\b", definitions, flag):
        return jet and (plane or bool(re.search(r"\b(?:aircraft|rotorcraft)\b", phrase, re.I)))
    for own_pattern, parent_pattern in PHYSICAL_SENSES:
        if re.search(parent_pattern, definitions, flag):
            return bool(re.search(own_pattern, phrase, re.I))
    raise ValueError('Parent meaning requires a separately reviewed independent scope contract')


def independently_check_generic_class(con, op):
    proof = op['proof']; node = row_at(con, 'nodes', op['uid'])
    if json.loads(node['data']).get('node_type') == 'WORDNET_SYNSET':
        return
    witness = proof.get('generic_class_scope_witness')
    if witness is None:
        witness = next(w for w in proof['source_witnesses'] if w['uid'] == op['uid'])
    if witness['uid'] != op['uid']:
        raise ValueError('Generic class grain must be grounded in its own object')
    _, full = source_field(con, witness)
    declaration = re.split(r'[.;]\s+', full, maxsplit=1)[0]
    copula = re.search(r'\b(?:is|are|was|were)\s+', declaration, re.I)
    structural = re.search(r'\b(?:has|have)\s+',declaration,re.I)
    if copula is None and structural and re.fullmatch(r'A[n]? [a-z0-9 -]+',declaration[:structural.start()].strip()):
        copula = structural
    if not copula:
        raise ValueError('A thin type fragment or imported rank cannot establish universal class grain')
    predicate = declaration[copula.end():]
    generic = bool(re.match(r'(?:an?\s+)?(?:type|kind|category|class) of\b', predicate, re.I)
                   or re.match(r'(?:an?\s+)?(?:[a-z-]+\s+){0,8}(?:instruments|aircraft|cameras|computers|devices)\s+(?:that|which)\b', predicate, re.I)
                   or re.match(r'^(?:a|an)\s+', declaration, re.I))
    if not generic or re.search(r'\b(?:manufactured in series|units were built|computer project|processor project|announced in|in its various incarnations)\b', full, re.I):
        raise ValueError('A named reusable design is not an independently universal physical class')


def independently_check_expanded_pc(con, inputs, op, current_role):
    proof=op['proof'];locator=proof['personal_computer_scope_review_locator']
    if Path(locator['file']).name!=locator['file'] or any(locator[k]!=op[k] for k in ('uid','parent','relation')):
        raise ValueError('Expanded computer scope lacks its exact safe own-source locator')
    raw=(inputs/locator['file']).read_bytes();review=json.loads(raw)
    if (sha(raw)!=locator['sha256'] or review!=proof['personal_computer_scope_review']
            or review.get('accepted_source_scope_only') is not True
            or [op['uid'],op['parent'],op['relation']] not in review.get('approved_keys',[])
            or current_role!='MODEL_FAMILY'):
        raise ValueError('Expanded computer family scope differs from the independent source review')
    child,parent=(row_at(con,'nodes',op[k]) for k in ('uid','parent'))
    for node,key in ((child,'complete_child'),(parent,'complete_parent')):
        if node!=review[key]:
            raise ValueError('Complete independently reviewed PC source endpoint changed')
    own=[w for w in proof['source_witnesses'] if w['uid']==op['uid']]
    if len(own)!=1:
        raise ValueError('Expanded PC requires exactly one complete owned physical declaration')
    _,statement=source_field(con,own[0]);first=re.split(r'[.;]\s+',statement,maxsplit=1)[0]
    if not (re.search(r'\bPersonal Computer in its various incarnations\b',first,re.I)
            and re.search(r'\bwas a legacy-free PC\b',first,re.I)):
        raise ValueError('Desktop alone does not establish personal-computer intent or whole family scope')
    definitions=' '.join(w['statement']for w in proof['parent_whole_sense_fields'])
    if not (re.search(r'\bpersonal computer \(PC\)',definitions,re.I)
            and re.search(r'\bcomputer designed for personal use\b',definitions,re.I)):
        raise ValueError('The complete parent must expand PC and its personal-use intention')
    return first


def independently_check_aircraft_scope(con, op, current_role=None):
    proof = op['proof']; child = row_at(con, 'nodes', op['uid'])
    own = [w for w in proof['source_witnesses'] if w['uid'] == op['uid']]
    if len(own) != 1:
        raise ValueError('Exactly one complete owned physical assertion is required')
    _, statement = source_field(con, own[0])
    data = json.loads(child['data'])
    source_names = []
    for retained in (data, data.get('evidence_record', {})):
        for key in ('label', 'enwiki_title', 'wikipedia_title'):
            if isinstance(retained.get(key), str):
                source_names.append(retained[key])
    phrase = owned_predicate(statement, child['label'], source_names, allow_other_kinds=True)
    scope_phrase = phrase
    compound = proof.get('aviation_compound_scope_review')
    if compound:
        cnode, definition = source_field(con, compound['definition_witness'])
        if cnode != compound['complete_before_node'] or role(con, cnode) != 'CLASS':
            raise ValueError('Compound sense is not the preserved generic source object')
        for table, field in (('node_profiles', 'before_profile'), ('normalization_roles', 'before_normalization_role')):
            if row_at(con, table, cnode['uid']) != compound[field]:
                raise ValueError('Generic compound role changed')
        if not re.search(r'\b' + re.escape(compound['compound']) + r's?\b', phrase, re.I):
            raise ValueError('Generic compound does not name the owned physical predicate')
        meaning = owned_predicate(definition, cnode['label'])
        if not re.search(r'\b(?:jet[- ]powered|jet aircraft|aircraft.*jet engines|jet[- ]propelled)\b', meaning, re.I):
            raise ValueError('Generic compound lacks its own complete jet-aviation meaning')
        scope_phrase += ' ' + meaning
        if compound.get('fixed_wing_scope_witness'):
            _, fixed = source_field(con, compound['fixed_wing_scope_witness'])
            if not re.search(r'\b(?:fixed-wing|airplane|airliner)\b', fixed, re.I):
                raise ValueError('Compound fixed-wing scope is ungrounded')
            scope_phrase += ' ' + fixed
    definitions = ' '.join(w['statement'] for w in proof['parent_whole_sense_fields'])
    if not independent_physical_entailment(scope_phrase, definitions):
        raise ValueError('Owned physical predicate does not entail the complete parent meaning')
    context = ' '.join(w['statement'] for w in proof['source_full_contexts'])
    if re.search(r'\bdish that consists of sweet foods\b',definitions,re.I) and re.search(r'\b(?:sweet (?:or|and) savo[ur]+ry|savo[ur]+ry (?:or|and) sweet)\b',context,re.I):
        raise ValueError('A mixed sweet and savoury category cannot imply a universal sweet dessert scope')
    if re.search(r'\bglider\s*(?:/|and|or)\s*motor[ -]glider\b', phrase, re.I) and re.search(r'\bglider equipped with a motor\b', definitions, re.I):
        raise ValueError('Mixed powered and unpowered scope cannot imply universal motor hardware')
    if (current_role or role(con, child)) == 'MODEL_FAMILY':
        if re.search(r'\b(?:both|either|including|variants?|versions?)\b[^.!?]*'
                     r'\b(?:jet|turboprop|propeller|unpowered)\b[^.!?]*\b(?:and|or)\b'
                     r'[^.!?]*\b(?:jet|turboprop|propeller|unpowered)\b', context, re.I):
            raise ValueError('Whole family propulsion alternatives need independent range adjudication')
    return phrase


def raw_parents(con, uid):
    node = row_at(con, 'nodes', uid)
    if not node or node['visibility'] != 'ACTIVE':
        return []
    parents = []
    for peer in con.execute('SELECT * FROM nodes WHERE component_id=? AND visibility=?',
                            (node['component_id'], 'ACTIVE')):
        for table, left, right in (('edges', 'child_uid', 'parent_uid'),
                                   ('entity_relations', 'subject_uid', 'object_uid')):
            for edge in con.execute('SELECT * FROM ' + table + ' WHERE ' + left + '=? '
                                    "AND status IN ('ACTIVE','BACKBONE_ACTIVE','TYPED_ACTIVE')", (peer['uid'],)):
                target = row_at(con, 'nodes', edge[right])
                if not target or target['visibility'] != 'ACTIVE':
                    continue
                rr = edge['relation']; kinds = role(con, dict(peer)), role(con, target)
                allowed = (rr == 'IS_A' and kinds == ('CLASS', 'CLASS')
                           or rr == 'DESIGN_TYPE_OF' and kinds[0] in {'MODEL', 'MODEL_FAMILY'} and kinds[1] == 'CLASS'
                           or rr == 'INSTANCE_OF' and kinds == ('INSTANCE', 'CLASS')
                           or rr == 'NATIVE_DESIGN_PARENT' and all(k in {'MODEL', 'MODEL_FAMILY'} for k in kinds))
                if allowed and target['component_id'] != node['component_id']:
                    parents.append(target['uid'])
    return parents


def reaches(con, start, destination):
    target = row_at(con, 'nodes', destination)
    queue, visited = deque([start]), set()
    while target and queue:
        node = row_at(con, 'nodes', queue.popleft())
        if not node or node['visibility'] != 'ACTIVE' or node['component_id'] in visited:
            continue
        if node['component_id'] == target['component_id']:
            return True
        visited.add(node['component_id'])
        queue.extend(raw_parents(con, node['uid']))
    return False


def run(database, inputs, output, preflight=False, allow_unsealed_inputs=False):
    database, inputs, output = (Path(p).resolve() for p in (database, inputs, output))
    if output.exists() or output == database or output.is_relative_to(inputs):
        raise ValueError('Audit output must be a new artifact outside preserved inputs')
    manifest_path = inputs / INPUT_NAME
    manifest = json.loads(manifest_path.read_bytes())
    filename = manifest['operations_file']
    if Path(filename).name != filename:
        raise ValueError('Unsafe operations filename')
    raw = (inputs / filename).read_bytes()
    ops = [json.loads(line) for line in raw.decode().splitlines() if line]
    if (manifest.get('schema') != 'FINEATLAS_COMPLETE_OWNED_TYPE_REPAIRS_V1'
            or manifest['operations_sha256'] != sha(raw)
            or type(manifest['operation_count']) is not int or manifest['operation_count'] != len(ops)
            or not ops or any(manifest.get(k) != 0 for k in ('new_nodes', 'positive_identity_merges', 'mapping_promotions'))):
        raise ValueError('Exact source operations and conservative mutation limits are required')
    errors, routes, checked, seen = [], {}, [], set()
    con = sqlite3.connect(database.as_uri() + '?mode=ro&immutable=1', uri=True)
    con.row_factory = sqlite3.Row
    metadata = {r['key']: json.loads(r['value']) for r in con.execute('SELECT * FROM metadata')}
    if not allow_unsealed_inputs:
        try:
            review_name = manifest['source_review_file']
            if not isinstance(review_name, str) or Path(review_name).name != review_name:
                raise ValueError('A safe portable independent source-review file is required')
            review_raw = (inputs / review_name).read_bytes()
            review = json.loads(review_raw)
            expected = sorted([o['uid'], o['parent'], o['relation']] for o in ops)
            if (sha(review_raw) != manifest['source_review_sha256']
                    or review.get('accepted_source_scope_only') is not True
                    or review.get('operations_sha256') != sha(raw)
                    or sorted(review.get('approved_keys', [])) != expected):
                raise ValueError('Independent source verdict does not bind every exact operation')
            binding = manifest['completed_parent_binding']
            if not isinstance(binding, dict) or set(binding) != {'database_revision', 'frozen_manifest_sha256'}:
                raise ValueError('Actual complete immutable parent binding is missing')
            if preflight:
                if (binding['database_revision'] != metadata.get('database_revision')
                        or binding['frozen_manifest_sha256'] != sha(json.dumps(
                            metadata['structure_frozen_build_manifest'], sort_keys=True, ensure_ascii=False))):
                    raise ValueError('Actual complete preflight parent is not the sealed source parent')
            else:
                applied = metadata.get('complete_owned_type_repairs', {})
                if (applied.get('manifest_sha256') != sha(manifest_path.read_bytes())
                        or applied.get('operations_sha256') != sha(raw)
                        or applied.get('operation_count') != len(ops)
                        or applied.get('completed_parent_binding') != binding
                        or meta_parent_revision(metadata) != binding['database_revision']):
                    raise ValueError('Actual applied repair metadata is not bound to exact frozen inputs')
                frozen = metadata.get('structure_frozen_build_manifest', {})
                for name in (INPUT_NAME, filename, review_name):
                    if frozen.get('inputs', {}).get(name) != sha((inputs / name).read_bytes()):
                        raise ValueError('Final complete-source input is missing from frozen metadata')
                if frozen.get('code', {}).get('scripts/audit_complete_owned_type_repairs.py') != sha(Path(__file__).read_bytes()):
                    raise ValueError('Actual independent auditor bytes were not frozen')
        except (KeyError, ValueError, TypeError, OSError) as exc:
            errors.append({'kind': 'EXACT_SOURCE_REVIEW_OR_COMPLETED_PARENT_NOT_BOUND', 'reason': str(exc)})
    for op in ops:
        try:
            signature = op['uid'], op['parent'], op['relation']
            if signature in seen or op['source'] != SOURCE or not op['uri'].startswith('https://'):
                raise ValueError('Duplicate or unattributed direction')
            seen.add(signature)
            proof = op['proof']
            if op['op'] == 'correct_role':
                checked.append(independently_check_role(con, inputs, op, preflight, ops))
                continue
            if op['op'] in {'review_class_edge','review_typed_relation'} and proof.get('kind')=='SOURCE_OWNED_GRAIN_INCOMPATIBLE_CLASSIFICATION_REVIEW':
                checked.append(independently_check_additional_review(con,inputs,op,ops,preflight))
                continue
            if op['op'] == 'retain_source_scope_reference':
                checked.append(independently_check_source_reference(con,inputs,op,ops,preflight))
                continue
            if op['op'] == 'review_typed_relation':
                checked.append(independently_check_typed_review(con, inputs, op, ops, preflight))
                continue
            if (op['op'] != 'link' or proof.get('kind') not in {'COMPLETE_OWNED_PHYSICAL_PREDICATE_V1', 'OWNED_SERIAL_PHYSICAL_INSTANCE_CLASSIFICATION','OWNED_NAMED_OPERATIONAL_AIRCRAFT_INSTANCE_CLASSIFICATION','OWNED_EXPANDED_PC_COMPLETE_SOURCE_SCOPE'}
                    or proof.get('classification_axis') != 'physical_structure'
                    or proof.get('no_identity_merges') is not True
                    or proof.get('source_native_objects_preserved') is not True
                    or proof.get('world_identity_assertion') is not False):
                raise ValueError('Unsupported mutation or unspecified source scope')
            child, parent = (row_at(con, 'nodes', op[k]) for k in ('uid', 'parent'))
            if not child or not parent or any(n['visibility'] != 'ACTIVE' for n in (child, parent)):
                raise ValueError('Grounded active endpoints are required')
            if sha(child['data']) != proof['native_record_sha256'] or sha(parent['data']) != proof['parent_native_record_sha256']:
                raise ValueError('Complete endpoint source bytes changed')
            verify_parent_component(con, manifest, op['parent'])
            expected = proof['complete_before_node']
            if {k: v for k, v in child.items() if k != 'component_id'} != {k: v for k, v in expected.items() if k != 'component_id'}:
                raise ValueError('Original source object fields changed')
            cr = next((o['after_profile']['node_kind'] for o in ops if o['op'] == 'correct_role' and o['uid'] == op['uid']), role(con, child))
            pr = role(con, parent)
            if not ((op['relation'] == 'DESIGN_TYPE_OF' and cr in {'MODEL', 'MODEL_FAMILY'} and pr == 'CLASS')
                    or (op['relation'] == 'IS_A' and cr == pr == 'CLASS')
                    or (op['relation'] == 'INSTANCE_OF' and cr == 'INSTANCE' and pr == 'CLASS')):
                raise ValueError('Relation is incompatible with actual endpoint roles')
            is_additional_link = bool(proof.get('source_additional_role_review_locator'))
            if is_additional_link:
                independently_check_additional_grain(con,inputs,op)
            is_instance_link = op['relation'] == 'INSTANCE_OF' and not is_additional_link
            if is_instance_link:
                independently_check_serial_instance(con, inputs, op, ops, preflight)
                parent_fields = complete_source_fields(parent)
                proof_parent_fields = [{'uid':parent['uid'],'data_sha256':sha(parent['data']),'field_path':k,'statement':v} for k,v in parent_fields.items()]
            else:
                proof_parent_fields = proof['parent_whole_sense_fields']
            collections = {'source_witnesses':proof['source_witnesses'], 'source_full_contexts':proof['source_instance_review_record']['complete_source_record']['all_own_fields'] if is_instance_link else proof['source_full_contexts'], 'parent_whole_sense_fields':proof_parent_fields}
            for collection in collections:
                if not collections.get(collection):
                    raise ValueError('Complete own and parent source contexts are required')
                for witness in collections[collection]:
                    source_field(con, witness)
            for node, collection in ((child, 'source_full_contexts'), (parent, 'parent_whole_sense_fields')):
                declared = {w.get('field_path') or w.get('field'): w['statement']
                            for w in collections[collection] if w['uid'] == node['uid']}
                verify_complete_scope_fields(node,collections[collection])
            for prior in proof['prior_assertions']:
                actual = row_at(con, prior['table'], prior['id'])
                permitted_review = next((o for o in ops if o['op'] == 'review_typed_relation' and o['before_assertion']['id'] == prior['id']), None) if prior['table'] == 'entity_relations' and not preflight else None
                expected_status = permitted_review['after_status'] if permitted_review else prior['status']
                if not actual or assertion_sha(actual) != prior['content_sha256'] or actual['status'] != expected_status:
                    raise ValueError('Original source assertion content or status changed')
            if proof['kind']=='OWNED_EXPANDED_PC_COMPLETE_SOURCE_SCOPE':
                phrase=independently_check_expanded_pc(con,inputs,op,cr)
            elif is_instance_link:
                definitions = ' '.join(w['statement'] for w in proof_parent_fields)
                if not re.search(r'\bpowered lighter-than-air aircraft\b', definitions, re.I):
                    raise ValueError('Physical individual needs the grounded airship class')
                phrase = 'Owned built serial individual airship'
            else:
                if cr == 'CLASS':
                    independently_check_generic_class(con, op)
                phrase = independently_check_aircraft_scope(con, op, cr)
            if not preflight:
                table, left, right = ('edges', 'child_uid', 'parent_uid') if op['relation'] == 'IS_A' else ('entity_relations', 'subject_uid', 'object_uid')
                rows = con.execute('SELECT * FROM ' + table + ' WHERE ' + left + '=? AND ' + right + '=? '
                                   'AND relation=? AND source=?', (*signature, SOURCE)).fetchall()
                if len(rows) != 1 or rows[0]['status'] != 'ACTIVE':
                    raise ValueError('Exactly one actual active direction is required')
                data = json.loads(rows[0]['data'])
                if data.get('admission_basis') != proof or data.get('classification_axis') != 'physical_structure':
                    raise ValueError('Actual direction lost its precise source scope')
                eid = 'usability:' + sha(dump(proof))
                evidence = row_at(con, 'evidence', eid)
                if (not evidence or evidence['payload'] != dump(proof) or evidence['payload_sha256'] != sha(dump(proof))
                        or evidence['source_name'] != SOURCE or evidence['source_uri'] != op['uri']):
                    raise ValueError('Actual canonical evidence differs')
                if table == 'entity_relations' and rows[0]['evidence_id'] != eid:
                    raise ValueError('Actual direction references different evidence')
                if table == 'edges':
                    provenance = json.loads(rows[0]['provenance'])
                    ids = provenance.get('evidence_ids', []) if isinstance(provenance, dict) else provenance
                    if eid not in ids or data.get('eligible_for_final_dag') is not True:
                        raise ValueError('Ordinary class edge is missing from the grounded final DAG')
                histories = con.execute('SELECT before_json,after_json,evidence FROM usability_changes '
                                        'WHERE stage=? AND object_type=? AND object_id=?',
                                        ('complete_owned_type_repairs', 'complete_owned_type_append', op['uid'])).fetchall()
                matches = [h for h in histories
                           if json.loads(h['before_json']) == {'prior_assertions': proof['prior_assertions']}
                           and json.loads(h['after_json']) == {'parent_uid': op['parent'], 'relation': op['relation']}
                           and json.loads(h['evidence']) == proof]
                if len(matches) != 1:
                    raise ValueError('Exactly one precise preserved source change history is required')
                if reaches(con, op['parent'], op['uid']):
                    raise ValueError('New physical direction creates a cycle')
                routes[op['uid']] = reaches(con, op['uid'], 'wordnet31:00001740-n')
                if not routes[op['uid']]:
                    raise ValueError('Actual physical parent chain does not reach the root')
            checked.append({'uid': op['uid'], 'parent': op['parent'], 'relation': op['relation'],
                            'owned_predicate': phrase, 'complete_source_sha256': proof['native_record_sha256']})
        except (ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            errors.append({'kind': 'ACTUAL_COMPLETE_SOURCE_OR_DIRECTION_DIFFERS', 'uid': op.get('uid'),
                           'parent': op.get('parent'), 'reason': str(exc)})
    if not preflight:
        actual_count = sum(con.execute('SELECT count(*) FROM ' + t + ' WHERE source=?',
                                      (SOURCE,)).fetchone()[0] for t in ('edges', 'entity_relations'))
        expected_links = sum(o['op'] in {'link','retain_source_scope_reference'} for o in ops)
        if actual_count != expected_links:
            errors.append({'kind': 'COMPLETE_NEW_SOURCE_DIRECTION_CENSUS_DIFFERS',
                           'actual': actual_count, 'expected': expected_links})
    report = {'schema': 'FINEATLAS_INDEPENDENT_COMPLETE_OWNED_TYPE_AUDIT_V1',
              'database': str(database), 'database_revision': metadata.get('database_revision'),
              'manifest_sha256': sha(manifest_path.read_bytes()), 'operations_sha256': sha(raw),
              'operation_count': len(ops), 'operations': dict(Counter(o['relation'] for o in ops)),
              'pass': not errors, 'preflight_only': bool(preflight or allow_unsealed_inputs),
              'unsealed_source_diagnostic': bool(allow_unsealed_inputs),
              'candidate_acceptance': bool(not preflight and not allow_unsealed_inputs and not errors),
              'actual_new_link_root_reachability': routes, 'checked_complete_source': checked,
              'errors': errors}
    con.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in {'checked_complete_source', 'errors', 'actual_new_link_root_reachability'}}))
    return not errors


def meta_parent_revision(metadata):
    lineage = metadata.get('structure_complete_type_resume_parent', {})
    if (lineage.get('repair_recipe') != 'resume_complete_owned_type_repairs.py'
            or lineage.get('previous_source_stages_replayed') is not False
            or lineage.get('previous_repair_stages_replayed') is not False
            or lineage.get('all_derived_indexes_recomputed') is not True):
        raise ValueError('Exact appended checkpoint lineage is missing')
    return lineage.get('parent_revision')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--allow-unsealed-inputs', action='store_true')
    args = parser.parse_args()
    raise SystemExit(0 if run(args.database, args.inputs, args.output, args.preflight,
                             args.allow_unsealed_inputs) else 1)
