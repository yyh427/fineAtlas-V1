#!/usr/bin/env python3
"""Audit owned-scope changes through source SQL, without importing the builder."""
from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
from html import unescape
import json
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
INPUT_NAME = 'structure_owned_scope_repairs.json'
SOURCE = 'Complete owned source scope adjudication'
REVIEW_TABLES = {'review_bridge': 'bridges', 'review_typed_relation': 'entity_relations',
                 'review_class_edge': 'edges'}
NAVIGATION_ROLES = {
    'INSTANCE_OF': ({'INSTANCE'}, {'CLASS'}),
    'IS_A': ({'CLASS'}, {'CLASS'}),
    'DESIGN_TYPE_OF': ({'MODEL', 'MODEL_FAMILY'}, {'CLASS'}),
    'NATIVE_DESIGN_PARENT': ({'MODEL', 'MODEL_FAMILY'}, {'MODEL', 'MODEL_FAMILY'}),
    'SERIES_MEMBER_OF': ({'MODEL'}, {'MODEL_FAMILY'}),
    'CONFIGURATION_TYPE_OF': ({'CONFIGURATION'}, {'CLASS'}),
    'CONFIGURATION_OF': ({'CONFIGURATION'}, {'MODEL', 'MODEL_FAMILY', 'CONFIGURATION'}),
    'TAXONOMIC_PARENT': ({'CLASS', 'BIOLOGICAL_VARIANT'}, {'CLASS', 'BIOLOGICAL_VARIANT'}),
    'NATIVE_CLASSIFICATION_PARENT': ({'CLASS'}, {'CLASS'}),
}


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def assertion_content(row):
    return sha(json.dumps({k: v for k, v in dict(row).items()
                           if k not in {'id', 'status', 'reason'}}, sort_keys=True))


def verify_edge_grounding(row, evidence_id, relation):
    provenance = json.loads(row['provenance'])
    identifiers = provenance.get('evidence_ids', []) if isinstance(provenance, dict) else provenance
    if evidence_id not in identifiers:
        raise ValueError('Actual navigable edge lacks its own evidence reference')
    data = json.loads(row['data'])
    if relation == 'TAXONOMIC_PARENT':
        if row['status'] != 'TYPED_ACTIVE' or data.get('eligible_for_final_typed_graph') is not True:
            raise ValueError('Biological host is missing from the scientific typed graph')
        if data.get('eligible_for_final_dag') is not False:
            raise ValueError('Biological host must preserve its distinct scientific relation')
    elif relation == 'IS_A' and data.get('eligible_for_final_dag') is not True:
        raise ValueError('Legal ordinary class link is absent from the final DAG')


def row_at(con, table, identifier, key='id'):
    if table not in {'nodes', 'edges', 'entity_relations', 'bridges', 'evidence', 'node_profiles', 'normalization_roles'}:
        raise ValueError('Unsafe source witness table')
    if key not in {'uid', 'id', 'evidence_id'}:
        raise ValueError('Unsafe source witness key')
    row = con.execute('SELECT * FROM ' + table + ' WHERE ' + key + '=?', (identifier,)).fetchone()
    return dict(row) if row else None


def node_role(con, node):
    profile = row_at(con, 'node_profiles', node['uid'], 'uid')
    if profile and profile.get('node_kind'):
        return profile['node_kind']
    rank = (node.get('rank') or '').lower()
    if (node.get('source') or '').lower() == 'wfo' and rank == 'series':
        return 'CLASS'
    return {
        'model': 'MODEL', 'product_model': 'MODEL', 'aircraft_model': 'MODEL', 'vehicle_model': 'MODEL',
        'model_family': 'MODEL_FAMILY', 'series': 'MODEL_FAMILY',
        'configuration': 'CONFIGURATION', 'model_year': 'CONFIGURATION', 'model_year_configuration': 'CONFIGURATION',
        'instance': 'INSTANCE', 'manufacturer': 'ORGANIZATION', 'make': 'ORGANIZATION',
        'attribute': 'ATTRIBUTE', 'horticultural_color_class': 'ATTRIBUTE',
        'unknown': 'UNKNOWN', 'type_or_product_model': 'UNKNOWN',
        'dataset_category': 'DATASET_CATEGORY', 'biological_variant': 'BIOLOGICAL_VARIANT',
    }.get(rank, 'CLASS')


def source_witness(con, witness):
    table = witness.get('table', 'nodes')
    identifier = witness.get('evidence_id') if table == 'evidence' else witness.get('id') if table != 'nodes' else witness['uid']
    key = 'evidence_id' if table == 'evidence' else 'uid' if table == 'nodes' else 'id'
    row = row_at(con, table, identifier, key)
    field_name = 'payload' if table == 'evidence' else 'data'
    if not row or sha(row[field_name]) != witness['data_sha256']:
        raise ValueError('Whole retained source witness bytes changed')
    if table == 'evidence' and row['payload_sha256'] != witness['data_sha256']:
        raise ValueError('Retained evidence payload index differs from its actual bytes')
    data = json.loads(row[field_name])
    field = witness['field']
    value = data
    for part in field.split('.'):
        value = value.get(part) if isinstance(value, dict) else None
    if value is None and '.' not in field:
        value = data.get('evidence_record', {}).get(field)
    if value != witness['statement']:
        raise ValueError('Witness is not its exact complete retained field')
    return row


def source_assertion_witness(con, witness, uid, reviewed=None):
    before = witness['before']
    actual = row_at(con, witness['table'], before['id'])
    expected = dict(before)
    if reviewed and (witness['table'], before['id']) in reviewed:
        expected['status'] = 'SOURCE_SCOPE_REVIEW'
    if (actual != expected or sha(dump(before)) != witness['before_fullrow_sha256']
            or (before.get('child_uid') or before.get('subject_uid')) != uid
            or not witness.get('original_source_uri', '').startswith('https://')):
        raise ValueError('Retained complete own source assertion or provenance changed')
    value = json.loads(before['data'])
    for key in witness['field_path']:
        value = value.get(key) if isinstance(value, dict) else None
    if value != witness['statement']:
        raise ValueError('Own source sentence is not the complete original assertion field')
    return value


def primary_documents(value):
    if isinstance(value, dict):
        if value.get('source_kind') == 'PRIMARY_MANUFACTURER_OR_REGULATOR':
            yield value
        for item in value.values():
            yield from primary_documents(item)
    elif isinstance(value, list):
        for item in value:
            yield from primary_documents(item)


def author_annotations(inputs, manifest):
    files = manifest.get('author_annotation_files')
    if not files:
        raise ValueError('The original nine complete author annotation files must be portable')
    files = {row['file']: row for row in files}
    records, seen = [], set()
    for split in ('train', 'val', 'test'):
        columns = {}
        for field in ('variant', 'family', 'manufacturer'):
            name = 'images_' + field + '_' + split + '.txt'
            registered = files.get(name)
            if not registered:
                raise ValueError('Missing complete author annotation field: ' + name)
            filename = registered.get('filename', name)
            if Path(filename).name != filename:
                raise ValueError('Unsafe author annotation filename')
            raw = (inputs / filename).read_bytes()
            if sha(raw) != registered['sha256'] or len(raw) != registered['bytes']:
                raise ValueError('Original author annotation bytes differ')
            parsed = [line.split(' ', 1) for line in raw.decode().splitlines() if line]
            if any(len(row) != 2 or not row[1] for row in parsed):
                raise ValueError('Malformed author annotation field')
            columns[field] = dict(parsed)
            if len(columns[field]) != len(parsed):
                raise ValueError('Duplicate author image in an annotation field')
        if len({frozenset(column) for column in columns.values()}) != 1:
            raise ValueError('Author variant/family/manufacturer image universes differ')
        for image in sorted(columns['variant']):
            if image in seen:
                raise ValueError('Author image occurs in more than one split')
            seen.add(image)
            records.append({'image_id': image, 'split': split,
                            **{field: values[image] for field, values in columns.items()}})
    if len(records) != 10000 or len({r['variant'] for r in records}) != 100:
        raise ValueError('Frozen complete 2013b author annotation census differs')
    return records


def identity_peer(con, first, second, overrides=None):
    left, right = (row_at(con, 'nodes', uid, 'uid') for uid in (first, second))
    overrides = overrides or {}
    if (not left or not right or left['visibility'] != 'ACTIVE' or right['visibility'] != 'ACTIVE'
            or left['component_id'] != right['component_id']
            or overrides.get(first, node_role(con, left)) != overrides.get(second, node_role(con, right))):
        return False
    queue, seen = deque([first]), set()
    while queue:
        uid = queue.popleft()
        if uid == second:
            return True
        if uid in seen:
            continue
        seen.add(uid)
        for bridge in con.execute("SELECT left_uid,right_uid FROM bridges WHERE status='ACTIVE' "
                                  "AND relation='SAME_CONCEPT' AND (left_uid=? OR right_uid=?)", (uid, uid)):
            queue.extend([bridge[0], bridge[1]])
    return False


def verify_primary_sources(inputs, operations, directory):
    needed = {(doc['source_uri'], doc['sha256'])
              for op in operations for doc in primary_documents(op['proof'])}
    if not needed:
        return {}
    if directory is None or not Path(directory).is_dir():
        raise ValueError('Explicit portable primary source snapshots are required')
    registered = {}
    for name in ('structure_primary_source_snapshots.json', 'structure_owned_source_snapshots.json'):
        path = inputs / name
        if not path.exists():
            continue
        registry = json.loads(path.read_text())
        if registry.get('schema') != 'FINEATLAS_PORTABLE_PRIMARY_SOURCE_SNAPSHOTS_V1':
            raise ValueError('Unsupported portable source registry')
        for key, doc in registry['documents'].items():
            locator = (doc['source_uri'], doc['sha256'])
            if locator in registered and registered[locator] != doc:
                raise ValueError('Conflicting complete primary source locator')
            registered[locator] = doc
    verified = {}
    directory = Path(directory).resolve()
    for uri, expected in sorted(needed):
        doc = registered.get((uri, expected))
        if not doc or not uri.startswith('https://') or doc.get('hash_basis') != 'HTTP_RESPONSE_BODY_BYTES':
            raise ValueError('Required complete primary document lacks a portable byte locator')
        filename = doc['filename']
        if Path(filename).name != filename or not filename:
            raise ValueError('Unsafe primary source filename')
        path = directory / filename
        if not path.is_file() or not path.resolve().is_relative_to(directory) or sha(path.read_bytes()) != expected:
            raise ValueError('Actual complete primary source bytes differ: ' + filename)
        verified[filename] = {'source_uri': uri, 'sha256': expected}
    return verified


def exact_history(con, kind, identifier, before, after, proof):
    rows = con.execute('SELECT before_json,after_json,evidence FROM usability_changes '
                       'WHERE stage=? AND object_type=? AND object_id=?',
                       ('owned_scope_repairs', kind, str(identifier))).fetchall()
    matches = [r for r in rows if json.loads(r['before_json']) == before
               and json.loads(r['after_json']) == after and json.loads(r['evidence']) == proof]
    if len(matches) != 1:
        raise ValueError('Exactly one preserved precise scope change history is required')


def own_assertion_phrase(statement):
    # Abbreviated design names before the copula contain periods. Separate the
    # actual asserted predicate first, rather than treating those as sentences.
    copula = re.search(r'\b(?:is|was|are|were)\s+', statement, re.I)
    predicate = statement[copula.end():] if copula else statement
    predicate = re.sub(r'^(an?\s+)proposed\s+', r'\1', predicate, flags=re.I)
    predicate = re.sub(r'\bamateur built\b', 'amateur-built', predicate, flags=re.I)
    # A development INTO a physical kind describes the resulting own design;
    # a development OF another kind alone does not.
    transformed = re.match(r'[^.]*\bdevelopment of\s+.+?\s+into\s+(an? .+)', predicate, re.I)
    if transformed:
        predicate = transformed[1]
    predicate = re.sub(r'\bdesigned and built\s+(?=single|two|three|four|[a-z]+-wing)', '', predicate, flags=re.I)
    predicate = re.sub(r'\bdesigned\s+(?=biplane|monoplane|helicopter|airplane)', '', predicate, flags=re.I)
    apposition = re.match(r'[^,]*\baircraft(?:\s+built\s+by [^,]+)?,\s+(an? [^,]+)', predicate, re.I)
    if apposition:
        predicate = apposition[1]
    return re.split(r'[.;]\s+|\s+(?:which|that|whose|derived|based|replacing|built|designed|manufactured|produced|proposed|introduced|made|from|by|used|for)\b',
                    predicate, maxsplit=1, flags=re.I)[0]


def scoped_assertion_phrase(statement, scope_kind, label):
    if scope_kind == 'OWNED_NAMED_INSTANCE_OF_STATED_DESIGN_KIND':
        return named_instance_phrase(statement, label)
    if scope_kind == 'OWNED_COMPLETE_RECONFIGURABLE_FIXED_WING':
        phrase = own_assertion_phrase(statement)
        match = re.search(r'\bcould fly either as a (biplane or as a parasol (?:winged )?monoplane)\b', statement, re.I)
        if not re.search(r'\baircraft\b', phrase, re.I) or not match:
            raise ValueError('Whole structural alternatives do not establish fixed-wing scope')
        return re.sub(r'\bor as a parasol (?:winged )?', 'or parasol ', match[1], flags=re.I)
    if scope_kind == 'OWNED_UNIVERSAL_VARIANTS':
        match = re.search(r'(?:^|[.!?]\s+)All variants\s+(?:are|were)\s+([^.!?]+)', statement, re.I)
        if not match:
            raise ValueError('Universal physical kind needs an explicit complete all-variants assertion')
        return re.split(r'\s+(?:with|that|which|whose)\b', match[1], maxsplit=1, flags=re.I)[0]
    if scope_kind == 'OWNED_SELF_TWINJET':
        copula = re.search(r'\b(?:is|was|are|were)\s+', statement, re.I)
        words = lambda text: re.findall(r'[^\W_]+', text.casefold(), re.UNICODE)
        lead = re.sub(r'^(?:the|an?)\s+', '', statement[:copula.start()].strip(), flags=re.I) if copula else ''
        if words(lead) != words(label) or not re.search(r'\b(?:aircraft|airliners?|family)\b', own_assertion_phrase(statement), re.I):
            raise ValueError('Self-anaphor needs the explicitly named own aircraft design scope')
        match = re.search(r'\bthe twinjet\s+(?:has|had|retained|features|featured|is|was|came)\b([^.!?]*)', statement, re.I)
        if not match or re.search(r'\b(?:not|never|fictional|virtual|toy|replica)\b', match[0], re.I):
            raise ValueError('Own twinjet anaphor is absent or incompatible')
        return match[0]
    if scope_kind not in {None, 'OWNED_FIRST_SUBJECT', 'RETAINED_SOURCE_CLASS_MOTOR_VEHICLE', 'OWNED_MOTOR_VEHICLE_DESIGN',
                          'OWNED_BIOLOGICAL_CULTIVAR_HOST_TAXON'}:
        raise ValueError('Unrecognized whole physical scope declaration')
    return own_assertion_phrase(statement)


def named_instance_phrase(statement, label):
    member = re.search(r'\bOne of them\s*[—–-]\s*(?:the )?' + re.escape(label) + r'\s*[—–-]', statement, re.I)
    if not member or not re.search(r'\b(?:Two|Three|Four|\d+) examples were built\.', statement[:member.start()], re.I):
        raise ValueError('Named physical member is not explicitly identified in the whole source')
    copula = re.search(r'\b(?:is|was)\s+', statement, re.I)
    if not copula or copula.start() >= member.start():
        raise ValueError('Named member has no independently stated design kind')
    design_name = re.sub(r'^The\s+', '', statement[:copula.start()].strip(), flags=re.I)
    words = lambda value: re.findall(r'[^\W_]+', value.casefold(), re.UNICODE)
    if words(design_name) == words(label):
        raise ValueError('A prototype count alone cannot turn a design into an instance')
    return own_assertion_phrase(statement)


def verify_physical_instrumentality_scope(proof, statement, parent_statement):
    review = proof['physical_instrumentality_scope_review']
    first = review['generic_own_system_clause']
    hardware = review['generic_physical_system_clause']
    installed = review['specific_installed_system_corroboration']
    if (not all(isinstance(value, str) and value and value in statement
                for value in (first, hardware, installed)) or not statement.startswith(first)):
        raise ValueError('Physical instrumentality needs the complete own generic and hardware assertions')
    expected = 'an artifact (or system of artifacts) that is instrumental in accomplishing some end'
    if parent_statement != expected or review['parent_whole_sense'] != expected:
        raise ValueError('Physical instrumentality cannot supply a narrower artifact-system sense')
    if (not re.search(r'\bsystem\s+is\s+an?\s+[^.!?]*\bradar\b[^.!?]*\bsystem\s+designed to detect\b', first, re.I)
            or not re.search(r'\b(?:aircraft|ships|vehicles|missiles)\b', first, re.I)
            or not re.search(r'\bradar system on\b[^.!?]*\baircraft\b[^.!?]*\ballows the operators to\b', hardware, re.I)
            or not re.search(r'\bsystem installed in\b[^.!?]*\bairframes\b', installed, re.I)
            or re.search(r'\b(?:not|never|fictional|virtual|imaginary|replica)\b', first + ' ' + hardware + ' ' + installed, re.I)):
        raise ValueError('Generic physical system must be distinguished from its carrier and operator')
    return own_assertion_phrase(first)


def verify_nominal_purpose_source(con, inputs, manifest, op, reviewed=None):
    proof = op['proof']
    locator = op.get('source_review_locator', proof.get('source_review_locator', {}))
    filename = manifest.get('source_purpose_review_file')
    if (not filename or Path(filename).name != filename or '\\' in filename
            or locator.get('file') != filename):
        raise ValueError('Nominal purpose requires its portable independent source review')
    raw = (Path(inputs) / filename).read_bytes()
    if sha(raw) != manifest.get('source_purpose_review_sha256') or locator.get('sha256') != sha(raw):
        raise ValueError('Independent source-purpose review bytes changed')
    source = json.loads(raw)
    if (source.get('schema') != 'FINEATLAS_SEVENTH_CORRECTED_DESIGN_OLD_ISA_SOURCE_TYPE_SCOPE_ADJUDICATION_V1'
            or source.get('source_revision') != manifest.get('completed_parent_revision')):
        raise ValueError('Independent purpose review belongs to a different source snapshot')
    records = [record for record in source['approved_type_records']
               if (record['uid'], record['parent'], record['proposed_relation']) ==
                  (op['uid'], op['parent'], op['relation'])]
    if (len(records) != 1 or locator.get('uid') != op['uid'] or locator.get('parent') != op['parent']
            or locator.get('relation') != op['relation'] or op['relation'] != 'DESIGN_TYPE_OF'):
        raise ValueError('Complete independent review does not approve this nominal direction')
    record = records[0]
    if (proof.get('nominal_design_type_scope_review') != record
            or record['status'] != 'SOURCE_TYPE_SCOPE_SUPPORTED_PENDING_ACTUAL_OPERATION'
            or record.get('no_identity_or_mapping_promotion') is not True):
        raise ValueError('Nominal purpose scope differs from its independent whole-source decision')
    own, parent = record['owned_complete_source_witness'], record['whole_parent_definition_witness']
    if proof.get('source_witnesses', [])[:2] != [own, parent]:
        raise ValueError('Nominal purpose does not retain the approved own and parent fields')
    if own['uid'] != op['uid'] or parent['uid'] != op['parent']:
        raise ValueError('Independent nominal fields belong to another endpoint')
    source_witness(con, own); source_witness(con, parent)
    before = record['original_full_active_assertion']
    if (before['child_uid'], before['parent_uid'], before['relation'], before['status']) != (
            op['uid'], op['parent'], 'IS_A', 'ACTIVE'):
        raise ValueError('Nominal migration does not preserve its original active direction')
    actual = row_at(con, 'edges', before['id'])
    expected = dict(before)
    precise_review = (reviewed or {}).get(('edges', before['id']))
    if precise_review:
        if precise_review['before_assertion'] != before:
            raise ValueError('Purpose migration uses another original class assertion')
        expected['status'] = 'SOURCE_SCOPE_REVIEW'
    if not actual or actual != expected:
        raise ValueError('Original class assertion or its exact scope review changed')
    for context in record.get('required_supporting_source_fields', []):
        source_witness(con, context['parent_owned_field'])
        relation = context['original_full_relation']
        if row_at(con, 'entity_relations', relation['id']) != relation:
            raise ValueError('Supporting native family declaration changed')
        node = row_at(con, 'nodes', context['complete_source_parent']['uid'], 'uid')
        if not node or {k: value for k, value in node.items() if k != 'component_id'} != {
                k: value for k, value in context['complete_source_parent'].items() if k != 'component_id'}:
            raise ValueError('Supporting whole source design object changed')
    if proof.get('classification_axis') not in {'function', 'purpose'}:
        raise ValueError('Nominal purpose must retain its distinct classification axis')
    if proof.get('physical_genus'):
        raise ValueError('Reviewed nominal purpose cannot claim a literal own physical genus')
    conditions = proof.get('parent_conditions', [])
    if (len(conditions) != 1 or conditions[0].get('parent_exact_span') != parent['statement']
            or conditions[0].get('complete_parent_definition') is not True
            or conditions[0].get('entailment_basis') != record.get('scope_reason')):
        raise ValueError('Nominal purpose lost its complete independently reviewed parent conditions')
    spans = proof.get('child_exact_spans', [])
    expected_witnesses = [own] + [item['parent_owned_field'] for item in
                                 record.get('required_supporting_source_fields', [])]
    if [item.get('witness') for item in spans] != expected_witnesses:
        raise ValueError('Nominal source conditions use a different own or supporting field')
    for index, item in enumerate(spans):
        expected_kind = ('OWN_COMPLETE_DECLARED_NOMINAL_FUNCTION_OR_PURPOSE' if index == 0 else
                         'COMPLETE_REFERENCED_DESIGN_PHYSICAL_CONTEXT_NOT_PURPOSE_INHERITANCE')
        if item.get('child_exact_span') != expected_witnesses[index]['statement'] or item.get('kind') != expected_kind:
            raise ValueError('Supporting physical context cannot silently transfer family purpose')
    return {'file': filename, 'sha256': sha(raw), 'uid': op['uid'], 'parent': op['parent']}


def independently_declared_role(statement, label, scope_kind):
    if scope_kind is None:
        named_instance_phrase(statement, label)
        return 'INSTANCE'
    phrase = own_assertion_phrase(statement)
    if re.search(r'\b(?:not|never|fictional|virtual|toy|replica)\b', phrase, re.I):
        raise ValueError('Incompatible whole statement cannot resolve a canonical role')
    if scope_kind == 'OWNED_UNRESOLVED_DESIGN_VERSUS_MODIFIED_EXAMPLE':
        if not re.search(r'\bmodified example\b', phrase, re.I):
            raise ValueError('Unresolved individual/design role must retain its actual ambiguity')
        return 'UNKNOWN'
    if re.search(r'\b(?:cultivar|grape variety)\b', phrase, re.I):
        if scope_kind not in {'OWNED_HORTICULTURAL_VARIANT_ROLE', 'OWNED_BIOLOGICAL_CULTIVAR', 'OWNED_NOMINAL_DESIGN_ROLE'}:
            raise ValueError('Horticultural role requires its explicit whole-source scope review')
        return 'BIOLOGICAL_VARIANT'
    if scope_kind != 'OWNED_NOMINAL_DESIGN_ROLE':
        raise ValueError('Unknown complete source-role review kind')
    if re.search(r'\b(?:prototype|trainer|target) series\b', phrase, re.I):
        return 'MODEL_FAMILY'
    if re.search(r'\b(?:version|variant|conversion|third-generation)\b|\b(?:system|transport|car) model\b|\btest and trials prototype\b', phrase, re.I):
        return 'MODEL'
    if re.search(r'\bloitering munition\b', phrase, re.I) and re.search(r'\bproduced .+? by\b', statement, re.I):
        return 'MODEL'
    raise ValueError('Whole owned source does not independently declare a nominal design role')


def verify_same_identifier_role_source(con, proof, child):
    grounding = proof.get('same_source_identifier_role_grounding')
    if not grounding:
        raise ValueError('Role source must describe the own preserved object')
    own, definition, bridge = (grounding[k] for k in ('before_own_node', 'before_independent_definition_node', 'before_identity_bridge'))
    for before in (own, definition):
        actual = row_at(con, 'nodes', before['uid'], 'uid')
        if not actual or {k:v for k,v in actual.items() if k != 'component_id'} != {k:v for k,v in before.items() if k != 'component_id'}:
            raise ValueError('Same-identifier role review changed an original source object')
    data, other = json.loads(own['data']), json.loads(definition['data'])
    if (own['uid'] != child['uid'] or own['uid'] == definition['uid']
            or own['label'] != definition['label'] or not data.get('qid')
            or data['qid'] != other.get('qid') or own['uid'].split(':')[-1] != data['qid']
            or definition['uid'].split(':')[-1] != other['qid']
            or not own['source'].startswith('wikidata') or not definition['source'].startswith('wikidata')
            or bridge['status'] != 'ACTIVE' or bridge['relation'] != 'SAME_CONCEPT'
            or {bridge['left_uid'],bridge['right_uid']} != {own['uid'],definition['uid']}
            or row_at(con,'bridges',bridge['id']) != bridge
            or json.loads(bridge['data']).get('alignment_type') != 'SOURCE_ID_EQUIVALENCE'
            or other.get('evidence_record',{}).get('wikipedia_redirect_chain')
            or len(proof['source_witnesses']) != 1 or proof['source_witnesses'][0]['uid'] != definition['uid']):
        raise ValueError('Source identifier/name/range or exact original alignment does not close')
    return definition


def manufacturer_vehicle_phrase(proof, child, parent, retained, directory, verified):
    scope = proof['primary_manufacturer_scope']; doc = scope['document']
    matching = [name for name, row in verified.items()
                if (row['source_uri'], row['sha256']) == (doc['source_uri'], doc['sha256'])]
    if len(matching) != 1:
        raise ValueError('Manufacturer whole-design statement has no verified complete source bytes')
    raw = (Path(directory) / matching[0]).read_text()
    title = re.search(r'<title[^>]*>(.*?)</title>', raw, re.I | re.S)
    text = unescape(re.sub(r'<[^>]+>', ' ', raw))
    text = ' '.join(text.split())
    if (not title or unescape(title[1]).strip() != scope['title']
            or scope['nominal_design_name'] != child['label']
            or scope['title'] != child['label'] + ' model series'
            or not scope.get('primary_scope_covers_whole_named_design')
            or scope.get('four_wheel_assertion') is not False
            or scope.get('category_same_concept_assertion') is not False
            or parent['uid'] != 'wordnet31:03796768-n'
            or not retained or not re.search(r'\bindustrial car model\b', retained[0], re.I)):
        raise ValueError('Manufacturer design and retained UID nominal scope are not closed')
    name = re.escape(scope['nominal_design_name'])
    versions = scope.get('scope_facts', {}).get('nominal_version_names', [])
    condensed = re.sub(r'\s+', '', text).casefold()
    if (not versions or any(re.sub(r'\s+', '', version).casefold() not in condensed for version in versions)
            or not re.search(r'\blicence agreement\b.*?\b' + re.escape(scope['physical_genus']) + r'\b', text, re.I)
            or not re.search(r'As the ' + name + r',.*?engine.*?was installed in this vehicle', text, re.I)
            or not scope.get('scope_facts', {}).get('self_propulsion_combustion_engine')):
        raise ValueError('Complete primary paragraph does not establish the whole motorized vehicle program')
    return scope['physical_genus']


def verify_biological_host_scope(con, op, child, parent, overrides, reviewed):
    proof = op['proof']; scope = proof['host_taxon_scope_review']
    if (op['relation'] != 'TAXONOMIC_PARENT'
            or overrides.get(child['uid'], node_role(con, child)) != 'BIOLOGICAL_VARIANT'
            or node_role(con, parent) != 'CLASS' or scope.get('parent_taxon_rank') != 'species'
            or scope.get('child_remains_biological_variant') is not True
            or scope.get('source_host_not_fruit') is not True or scope.get('species_identity_assertion') is not False):
        raise ValueError('Cultivar host link changed biological grain or scientific identity scope')
    own, host = proof['source_witnesses'][:2]
    if own.get('table') == 'evidence':
        evidence = source_witness(con, own)
        payload = json.loads(evidence['payload'])
        if payload.get('child_uid') != child['uid'] or payload.get('definition_supported') is not True:
            raise ValueError('Biological definition evidence belongs to a different or unconfirmed source object')
    elif own.get('uid') != child['uid']:
        raise ValueError('Cultivar host requires an independent own whole source assertion')
    data = json.loads(parent['data']); description = data.get('wikidata_description') or data.get('description') or ''
    if (host.get('uid') != parent['uid'] or host.get('table', 'nodes') != 'nodes'
            or parent['label'] != scope['host_scientific_name']
            or not re.search(r'\bspecies\b', description, re.I)
            or scope['host_scientific_name'] not in host['statement']
            or scope['parent_owned_host_phrase'] not in host['statement']
            or scope['child_owned_host_phrase'] not in own['statement']):
        raise ValueError('Complete own host assertion does not match the actual living scientific taxon')
    claims = scope.get('retained_primary_taxonomic_or_classifier_assertions', [])
    if not claims:
        raise ValueError('Whole biological host must retain its original taxonomic or classifier provenance')
    for before in claims:
        expected = dict(before)
        if ('edges', before['id']) in reviewed:
            expected['status'] = 'SOURCE_SCOPE_REVIEW'
        if row_at(con, 'edges', before['id']) != expected or before['child_uid'] != child['uid']:
            raise ValueError('Original scientific or cultivar classifier declaration changed')


def role_valid(con, relation, left, right, overrides=None):
    allowed = NAVIGATION_ROLES.get(relation)
    overrides = overrides or {}
    return bool(allowed and overrides.get(left['uid'], node_role(con, left)) in allowed[0]
                and overrides.get(right['uid'], node_role(con, right)) in allowed[1])


def raw_parents(con, uid):
    node = row_at(con, 'nodes', uid, 'uid')
    if not node or node['visibility'] != 'ACTIVE':
        return []
    parents = []
    for peer in con.execute('SELECT * FROM nodes WHERE component_id=?', (node['component_id'],)):
        peer = dict(peer)
        if peer['visibility'] != 'ACTIVE':
            continue
        rows = list(con.execute("SELECT parent_uid AS parent,relation FROM edges WHERE child_uid=? "
            "AND ((relation='IS_A' AND status IN ('ACTIVE','BACKBONE_ACTIVE')) "
            "OR (relation IN ('TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT') AND status='TYPED_ACTIVE'))", (peer['uid'],)))
        rows.extend(con.execute("SELECT object_uid AS parent,relation FROM entity_relations "
            "WHERE subject_uid=? AND status='ACTIVE'", (peer['uid'],)))
        for row in rows:
            target = row_at(con, 'nodes', row['parent'], 'uid')
            if target and target['visibility'] == 'ACTIVE' and role_valid(con, row['relation'], peer, target):
                if target['component_id'] != node['component_id']:
                    parents.append(target['uid'])
    return parents


def reaches(con, start, destination, root=False):
    target = row_at(con, 'nodes', destination, 'uid')
    queue, seen = deque([start]), set()
    while queue:
        uid = queue.popleft()
        node = row_at(con, 'nodes', uid, 'uid')
        if not node or node['visibility'] != 'ACTIVE' or node['component_id'] in seen:
            continue
        if target and node['component_id'] == target['component_id']:
            return True
        seen.add(node['component_id'])
        queue.extend(raw_parents(con, uid))
    return False


def verify_partition(con, members):
    members = set(members)
    if not members:
        raise ValueError('Original identity component member census is empty')
    adjacency = {uid: set() for uid in members}
    for uid in members:
        for row in con.execute("SELECT left_uid,right_uid FROM bridges WHERE status='ACTIVE' "
                               "AND relation='SAME_CONCEPT' AND (left_uid=? OR right_uid=?)", (uid, uid)):
            if row[0] in members and row[1] in members:
                adjacency[row[0]].add(row[1]); adjacency[row[1]].add(row[0])
    expected, visited = [], set()
    for uid in sorted(members):
        if uid in visited:
            continue
        todo, group = [uid], set()
        while todo:
            current = todo.pop()
            if current in group:
                continue
            group.add(current); todo.extend(adjacency[current] - group)
        expected.append(group); visited.update(group)
    actual = {}
    for uid in members:
        node = row_at(con, 'nodes', uid, 'uid')
        if not node:
            raise ValueError('Original identity object disappeared')
        actual.setdefault(node['component_id'], set()).add(uid)
    if {frozenset(x) for x in expected} != {frozenset(x) for x in actual.values()}:
        raise ValueError('Actual identity partitions disagree with surviving source bridges')
    for component, group in actual.items():
        peers = {r[0] for r in con.execute('SELECT uid FROM nodes WHERE component_id=?', (component,))}
        if peers != group:
            raise ValueError('Identity split gained unrelated source objects')
    return len(actual)


def run(database, inputs, output, preflight=False, primary_snapshots_dir=None, allow_unfrozen_fixture=False):
    database, inputs, output = Path(database).resolve(), Path(inputs).resolve(), Path(output).resolve()
    path = inputs / INPUT_NAME
    manifest = json.loads(path.read_text())
    operation_name = manifest['operations_file']
    if Path(operation_name).name != operation_name:
        raise ValueError('Unsafe operations filename')
    raw = (inputs / operation_name).read_bytes()
    operations = [json.loads(line) for line in raw.decode().splitlines() if line]
    if (manifest.get('schema') != 'FINEATLAS_OWNED_SCOPE_REPAIRS_V1'
            or type(manifest.get('operation_count')) is not int
            or manifest['operation_count'] != len(operations) or not operations
            or manifest.get('operations_sha256') != sha(raw)):
        raise ValueError('Complete exact frozen source operations are required')
    if output.is_relative_to(inputs) or output == database:
        raise ValueError('Audit output must not replace a source artifact')
    con = sqlite3.connect(database.as_uri() + '?mode=ro&immutable=1', uri=True)
    con.row_factory = sqlite3.Row
    metadata = {r['key']: json.loads(r['value']) for r in con.execute('SELECT * FROM metadata')}
    errors, partition_sets, routes, verified_sources = [], set(), {}, {}
    verified_purpose_sources = []
    author_records = None
    if any(o['op'] == 'migrate_nominal_design_mapping' for o in operations):
        try:
            author_records = author_annotations(inputs, manifest)
        except (ValueError, KeyError, OSError) as exc:
            errors.append({'kind': 'AUTHOR_ANNOTATIONS_NOT_PORTABLY_VERIFIED', 'reason': str(exc)})
    try:
        verified_sources = verify_primary_sources(inputs, operations, primary_snapshots_dir)
    except (ValueError, KeyError, OSError) as exc:
        errors.append({'kind': 'PRIMARY_DOCUMENT_NOT_PORTABLY_VERIFIED', 'reason': str(exc)})
    reviewed = {(REVIEW_TABLES[o['op']], o['before_assertion']['id']): o
                for o in operations if o['op'] in REVIEW_TABLES}
    role_overrides = {o['uid']: o['after_profile']['node_kind'] for o in operations if o['op'] == 'correct_role'}
    seen = set()
    for op in operations:
        try:
            signature = (op['op'], op.get('dataset'), op.get('class_id'), op['uid'], op['parent'],
                         op['relation'], op.get('content_sha256'))
            if signature in seen or op['source'] != SOURCE or not op['uri'].startswith('https://'):
                raise ValueError('Duplicate or unattributed source operation')
            seen.add(signature)
            proof = op['proof']
            if not proof.get('license') or not proof.get('scope_observation'):
                raise ValueError('Complete source scope decision and attribution are required')
            for witness in proof.get('source_witnesses', []) + proof.get('retained_source_context_witnesses', []):
                source_witness(con, witness)
            retained_own_statements = []
            for witness in proof.get('source_assertion_witnesses', []):
                subject = op['uid']
                if proof.get('owned_physical_scope_kind') == 'OWNED_MOTOR_VEHICLE_DESIGN':
                    supporting = proof.get('supporting_class_definition', {})
                    source_witness(con, supporting)
                    subject = supporting['uid']
                    if (op['parent'] != 'wordnet31:03796768-n'
                            or witness['before'].get('parent_uid') != op['parent']
                            or not re.search(r'\bis a motor vehicle with wheels\.?$', witness['statement'], re.I)):
                        raise ValueError('Shared automotive class definition does not prove the broad motor-vehicle sense')
                retained_own_statements.append(source_assertion_witness(con, witness, subject, reviewed if not preflight else None))
            for collection in ('source_nodes', 'counterexamples'):
                for uid, before in proof.get(collection, {}).items():
                    actual = row_at(con, 'nodes', uid, 'uid')
                    if not actual or {k: v for k, v in actual.items() if k != 'component_id'} != {
                            k: v for k, v in before.items() if k != 'component_id'}:
                        raise ValueError('Original whole source object changed')
            for evidence in proof.get('evidence_witnesses', []):
                actual = row_at(con, 'evidence', evidence['evidence_id'], 'evidence_id')
                if actual != evidence or sha(evidence['payload']) != evidence['payload_sha256']:
                    raise ValueError('Original source evidence changed')
            for uid, tables in proof.get('prior_source_parents', {}).items():
                for table, records in tables.items():
                    for before in records:
                        actual = row_at(con, table, before['id'])
                        expected = dict(before)
                        if not preflight and (table, before['id']) in reviewed:
                            expected['status'] = 'SOURCE_SCOPE_REVIEW'
                        if actual != expected:
                            raise ValueError('Original exact source parent declaration changed')
            for prior in proof.get('prior_assertions', []):
                before = prior['before']; actual = row_at(con, prior['table'], before['id'])
                expected = dict(before)
                if not preflight and (prior['table'], before['id']) in reviewed:
                    expected['status'] = 'SOURCE_SCOPE_REVIEW'
                if actual != expected or assertion_content(actual) != prior['content_sha256']:
                    raise ValueError('Original exact source assertion or status history changed')
            if op['op'] == 'link':
                child, parent = (row_at(con, 'nodes', op[k], 'uid') for k in ('uid', 'parent'))
                if (not child or not parent or child['visibility'] != 'ACTIVE' or parent['visibility'] != 'ACTIVE'
                        or sha(child['data']) != proof['native_record_sha256']
                        or sha(parent['data']) != proof['parent_native_record_sha256']
                        or not role_valid(con, op['relation'], child, parent, role_overrides if preflight else None)):
                    raise ValueError('Actual grounded endpoint bytes or role grain differ')
                if proof.get('world_identity_assertion') is not False or proof.get('no_identity_merges') is not True:
                    raise ValueError('A physical type link cannot certify an identity merge')
                witnesses = proof['source_witnesses']
                if len(witnesses) < 2 or not proof.get('whole_subject_scope_review'):
                    raise ValueError('Whole own subject and complete parent scope are required')
                motor_design = proof.get('owned_physical_scope_kind') == 'OWNED_MOTOR_VEHICLE_DESIGN'
                manufacturer_design = proof.get('owned_physical_scope_kind') == 'PRIMARY_MANUFACTURER_WHOLE_NOMINAL_MOTOR_VEHICLE'
                biological_host = proof.get('owned_physical_scope_kind') == 'OWNED_BIOLOGICAL_CULTIVAR_HOST_TAXON'
                own = retained_own_statements[0] if retained_own_statements and not motor_design else witnesses[0]['statement']
                witness_node = row_at(con, 'nodes', witnesses[0].get('uid', child['uid']), 'uid')
                if biological_host:
                    verify_biological_host_scope(con, op, child, parent, role_overrides if preflight else {},
                                                 reviewed if not preflight else {})
                    phrase = witnesses[0]['statement']
                elif proof.get('owned_physical_scope_kind') == 'OWNED_PHYSICAL_INSTRUMENTALITY':
                    if op['relation'] != 'IS_A':
                        raise ValueError('Physical instrumentality scope requires ordinary class inclusion')
                    phrase = verify_physical_instrumentality_scope(proof, own, witnesses[1]['statement'])
                elif proof.get('owned_physical_scope_kind') == 'OWNED_NOMINAL_DESIGN_FUNCTION_OR_PURPOSE':
                    verified_purpose_sources.append(verify_nominal_purpose_source(
                        con, inputs, manifest, op, reviewed if not preflight else None))
                    phrase = own_assertion_phrase(own)
                elif manufacturer_design:
                    phrase = manufacturer_vehicle_phrase(proof, child, parent, retained_own_statements,
                                                         primary_snapshots_dir, verified_sources)
                    if witnesses[0]['statement'] != child['label'] or witnesses[1]['statement'] != 'a self-propelled wheeled vehicle that does not run on rails':
                        raise ValueError('Manufacturer program lost its exact own nominal designation or parent sense')
                else:
                    phrase = scoped_assertion_phrase(own, proof.get('owned_physical_scope_kind'),
                                                    witness_node['label'] if witness_node else child['label'])
                if motor_design and (not retained_own_statements
                        or witnesses[1]['statement'] != 'a self-propelled wheeled vehicle that does not run on rails'
                        or not re.search(r'\b(?:cars?|automobiles?|sportscars?)(?:\s+(?:model|family|series))?$', phrase.rstrip('. '), re.I)):
                    raise ValueError('Own automotive design and broad parent scope do not close')
                if proof.get('owned_physical_scope_kind') == 'OWNED_NAMED_INSTANCE_OF_STATED_DESIGN_KIND' and op['relation'] != 'INSTANCE_OF':
                    raise ValueError('A named physical member cannot supply a design TYPE link')
                if not biological_host and re.search(r'\b(?:not|never|fictional|virtual|imaginary|toy|scale model|parts? of|engine for)\b', phrase, re.I):
                    raise ValueError('Incidental or incompatible clause cannot supply the own physical genus')
                genus = proof.get('physical_genus')
                literal_physical_scope = (not biological_host and proof.get('owned_physical_scope_kind') !=
                                          'OWNED_NOMINAL_DESIGN_FUNCTION_OR_PURPOSE')
                words = lambda value: re.findall(r'[^\W_]+', value.casefold(), re.UNICODE)
                if literal_physical_scope and (not isinstance(genus, str) or not words(genus)):
                    raise ValueError('Physical genus must be explicit in the whole source review')
                declared_words, phrase_words = words(genus or ''), words(phrase)
                if literal_physical_scope and not any(phrase_words[i:i + len(declared_words)] == declared_words
                           for i in range(len(phrase_words) - len(declared_words) + 1)):
                    raise ValueError('Declared physical genus exists only outside the own first assertion')
                if (witnesses[0].get('table', 'nodes') == 'nodes'
                        and not identity_peer(con, child['uid'], witnesses[0]['uid'], role_overrides if preflight else None)):
                    raise ValueError('Attached different-source object cannot supply the own scope')
                if not preflight:
                    table = 'edges' if op['relation'] in {'IS_A','TAXONOMIC_PARENT'} else 'entity_relations'
                    left, right = ('child_uid', 'parent_uid') if table == 'edges' else ('subject_uid', 'object_uid')
                    rows = con.execute('SELECT * FROM ' + table + ' WHERE ' + left + '=? AND ' + right + '=? AND relation=? AND source=?',
                                       (op['uid'], op['parent'], op['relation'], SOURCE)).fetchall()
                    expected_status = 'TYPED_ACTIVE' if op['relation'] == 'TAXONOMIC_PARENT' else 'ACTIVE'
                    if len(rows) != 1 or rows[0]['status'] != expected_status or json.loads(rows[0]['data']).get('admission_basis') != proof:
                        raise ValueError('Actual new scoped link is absent or differs')
                    eid = 'usability:' + sha(dump(proof)); evidence = row_at(con, 'evidence', eid, 'evidence_id')
                    if not evidence or evidence['payload'] != dump(proof) or evidence['payload_sha256'] != sha(dump(proof)):
                        raise ValueError('Actual new physical link evidence differs')
                    if table == 'entity_relations' and rows[0]['evidence_id'] != eid:
                        raise ValueError('Actual typed link points at a different evidence record')
                    if (proof.get('owned_physical_scope_kind') == 'OWNED_NOMINAL_DESIGN_FUNCTION_OR_PURPOSE'
                            and json.loads(rows[0]['data']).get('classification_axis') != proof['classification_axis']):
                        raise ValueError('Actual nominal type has lost its function or purpose axis')
                    if table == 'edges':
                        verify_edge_grounding(rows[0], eid, op['relation'])
                    exact_history(con, 'owned_scope_link', op['uid'], {'prior_assertions': proof.get('prior_assertions', [])},
                                  {'parent_uid': op['parent'], 'relation': op['relation']}, proof)
                    if reaches(con, op['parent'], op['uid']):
                        raise ValueError('New direction creates a canonical source identity cycle')
                    routes[op['uid']] = reaches(con, op['uid'], 'wordnet31:00001740-n')
                    if not routes[op['uid']]:
                        raise ValueError('New legal connection does not reach the physical root')
            elif op['op'] == 'correct_role':
                child = row_at(con, 'nodes', op['uid'], 'uid')
                if (not child or child['visibility'] != 'ACTIVE' or op['uid'] != op['parent']
                        or op['relation'] != 'ROLE_ADJUDICATION' or not proof.get('source_native_objects_preserved')
                        or sha(child['data']) != proof['native_record_sha256']
                        or len(proof.get('source_witnesses', [])) != 1
                        ):
                    raise ValueError('Role adjudication is not grounded in the preserved own object')
                if proof['source_witnesses'][0]['uid'] != child['uid']:
                    verify_same_identifier_role_source(con, proof, child)
                target_role = independently_declared_role(proof['source_witnesses'][0]['statement'], child['label'],
                                                         proof.get('source_role_scope_kind'))
                if proof.get('canonical_role', target_role) != target_role:
                    raise ValueError('Declared canonical role conflicts with its whole source statement')
                before, norm = op['before_profile'], op['before_normalization_role']
                eid = 'usability:' + sha(dump(proof))
                attrs = json.loads(before['attributes']) if before else {}
                attrs.update(source_role=proof.get('source_role', attrs.get('source_role', 'UNSPECIFIED')),
                             native_rank=proof.get('native_rank', attrs.get('native_rank', child['rank'])),
                             role_status='VERIFIED', role_evidence_id=eid)
                attrs.pop('canonical_scope_guard', None); attrs.pop('canonical_scope_evidence_id', None)
                if target_role == 'UNKNOWN':
                    attrs.update(role_status='REVIEW', allowed_views=[])
                after = {**(before or {'uid': child['uid'], 'domain': child['domain']}),
                         'node_kind': target_role, 'source_uri': op['uri'], 'evidence_id': eid, 'attributes': dump(attrs)}
                after_norm = {**(norm or {'uid': child['uid'], 'source_role': proof.get('source_role') or child['rank'] or 'UNSPECIFIED',
                                        'status': 'VERIFIED', 'prior_profile': dump(before or {})}),
                              'canonical_role': target_role, 'evidence_id': eid, 'source': SOURCE}
                if target_role == 'UNKNOWN':
                    after_norm['status'] = 'REVIEW'
                if op['after_profile'] != after or op['after_normalization_role'] != after_norm:
                    raise ValueError('Role correction changed unrelated source profile fields')
                for table, part in (('node_profiles', 'profile'), ('normalization_roles', 'normalization_role')):
                    expected = op[('before_' if preflight else 'after_') + part]
                    if row_at(con, table, op['uid'], 'uid') != expected:
                        raise ValueError('Actual role profile or normalization history differs')
                if not preflight:
                    evidence = row_at(con, 'evidence', eid, 'evidence_id')
                    if not evidence or evidence['payload'] != dump(proof) or evidence['payload_sha256'] != sha(dump(proof)):
                        raise ValueError('New role has no actual complete source evidence')
                    exact_history(con, 'role_scope_correction', op['uid'],
                                  {'profile': before, 'normalization_role': norm},
                                  {'profile': after, 'normalization_role': after_norm}, proof)
            elif op['op'] in REVIEW_TABLES:
                table = REVIEW_TABLES[op['op']]; before = op['before_assertion']
                actual = row_at(con, table, before['id']); expected = dict(before)
                if not preflight:
                    expected['status'] = 'SOURCE_SCOPE_REVIEW'
                if (actual != expected or before['status'] != 'ACTIVE' or op['after_status'] != 'SOURCE_SCOPE_REVIEW'
                        or assertion_content(actual) != op['content_sha256']):
                    raise ValueError('Review changed source content or failed its exact original status transition')
                if not proof.get('source_native_objects_preserved'):
                    raise ValueError('Source objects must survive a scope review')
                if not preflight:
                    history_kind = {'bridges': 'bridge_scope_review', 'entity_relations': 'typed_scope_review',
                                    'edges': 'class_scope_review'}[table]
                    exact_history(con, history_kind,
                                  before['id'], before, {'status': 'SOURCE_SCOPE_REVIEW'}, proof)
                    for members in proof.get('source_component_uids', {}).values():
                        partition_sets.add(tuple(sorted(members)))
                    if op.get('non_navigation_reference_relation'):
                        source = SOURCE + ': prior-bridge:' + op['content_sha256']
                        refs = con.execute('SELECT * FROM entity_relations WHERE source=?', (source,)).fetchall()
                        if len(refs) != 1 or refs[0]['relation'] != op['non_navigation_reference_relation'] or refs[0]['status'] != 'SOURCE_DECLARED':
                            raise ValueError('Preserved original non-navigation reference differs')
                        data = json.loads(refs[0]['data'])
                        if data.get('allowed_views') != [] or data.get('navigation_eligible') is not False or data.get('admission_basis') != proof:
                            raise ValueError('Uncertain historical reference became navigational')
                        if con.execute("SELECT 1 FROM browse_links WHERE storage IN ('entity','entity_relations') AND record_id=? LIMIT 1", (refs[0]['id'],)).fetchone():
                            raise ValueError('Non-navigation source reference leaked into browsing')
            elif op['op'] in {'migrate_nominal_design_mapping', 'review_dataset_mapping'}:
                key = (op['dataset'], str(op['class_id']))
                for table, part in (('dataset_targets', 'target'), ('dataset_mapping_checks', 'check')):
                    row = con.execute('SELECT * FROM ' + table + ' WHERE dataset=? AND class_id=?', key).fetchone()
                    expected = op[('before_' if preflight else 'after_') + part]
                    if (dict(row) if row else None) != expected:
                        raise ValueError('Mapping/check differs from its exact frozen before or after adjudication')
                if json.loads(op['after_check']['proof']) != proof:
                    raise ValueError('Mapping check does not retain the whole decision proof')
                if op['op'] == 'migrate_nominal_design_mapping':
                    review = proof['nominal_design_scope_review']; target = row_at(con, 'nodes', op['uid'], 'uid')
                    if (not target or node_role(con, target) not in {'MODEL', 'MODEL_FAMILY'} or target['visibility'] != 'ACTIVE'
                            or sha(target['data']) != proof['native_record_sha256']
                            or row_at(con, 'node_profiles', op['uid'], 'uid') != review['world_profile']
                            or review['approved_base_model_design_target_uid'] != op['uid']
                            or proof.get('task_grain') != 'model_design'
                            or any(proof.get(k) is not False for k in ('category_same_concept_assertion',
                                'world_identity_bridge_assertion', 'customer_configuration_equivalence_assertion'))):
                        raise ValueError('Nominal design resolution crossed a role or identity scope boundary')
                    cohort = review['actual_author_annotations']
                    if (len(cohort) != 100 or len({r['image'] for r in cohort}) != 100
                            or {(r['family'], r['manufacturer']) for r in cohort} != {
                                (review['author_family'], review['manufacturer'])}
                            or review['author_variant'] != op['before_target']['label']):
                        raise ValueError('Complete retained author model-design cohort is inconsistent')
                    native = row_at(con, 'nodes', op['parent'], 'uid')
                    if (not native or sha(native['data']) != proof['source_native_record_sha256']
                            or not author_records):
                        raise ValueError('Author model-design source bytes have not been independently verified')
                    native_data = json.loads(native['data'])
                    if (native_data.get('annotation_records_sha256') != sha(dump(author_records))
                            or native_data.get('native_label') != review['author_variant']):
                        raise ValueError('Whole portable author join differs from the frozen native object')
                    declared = {r['image']: r for r in cohort}
                    actual_cohort = {r['image_id']: r for r in author_records if r['variant'] == review['author_variant']}
                    if declared.keys() != actual_cohort.keys():
                        raise ValueError('Nominal mapping cohort differs from actual native image membership')
                    for image, claim in declared.items():
                        if any(actual_cohort[image].get(k) != v for k, v in claim.items() if k != 'image'):
                            raise ValueError('Mapping source tuple differs from complete author annotations')
                elif op['after_target']['target_uid'] != op['before_target']['target_uid'] or op['after_check']['status'] != 'ANNOTATION_SCOPE_REVIEW':
                    raise ValueError('A negative mapping decision silently changed its target')
                if not preflight:
                    before = {'target': op['before_target'], 'check': op['before_check']}
                    after = {'target': op['after_target'], 'check': op['after_check']}
                    exact_history(con, 'nominal_design_mapping', op['dataset'] + ':' + str(op['class_id']), before, after, proof)
                    eid = 'usability:' + sha(dump(proof))
                    history = con.execute('SELECT * FROM dataset_mapping_history WHERE id=?', (sha(dump(op)),)).fetchone()
                    if (not history or json.loads(history['before_record']) != before or json.loads(history['after_record']) != after
                            or history['evidence_id'] != eid or history['decision'] != op['after_check']['status']):
                        raise ValueError('Preserved dataset mapping history differs')
                    evidence = row_at(con, 'evidence', eid, 'evidence_id')
                    if not evidence or evidence['payload'] != dump(proof) or evidence['payload_sha256'] != sha(dump(proof)):
                        raise ValueError('Actual model-design mapping evidence is missing')
                    if op['op'] == 'migrate_nominal_design_mapping' and eid not in json.loads(op['after_target']['evidence_ids']):
                        raise ValueError('New world mapping cannot expose its primary source evidence')
            else:
                raise ValueError('Unsupported source operation')
        except (ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            errors.append({'kind': 'ACTUAL_OPERATION_OR_SOURCE_SCOPE_DIFFERS', 'uid': op.get('uid'),
                           'op': op.get('op'), 'reason': str(exc)})
    if not preflight:
        for members in sorted(partition_sets):
            try:
                verify_partition(con, members)
            except ValueError as exc:
                errors.append({'kind': 'IDENTITY_SPLIT_NOT_EXACT', 'uids': members, 'reason': str(exc)})
        applied = metadata.get('owned_scope_repairs', {})
        counts = dict(Counter(o['relation'] for o in operations))
        if (applied.get('manifest_sha256') != sha(path.read_bytes()) or applied.get('operations_sha256') != sha(raw)
                or type(applied.get('operation_count')) is not int or applied['operation_count'] != len(operations)
                or applied.get('operations') != counts or applied.get('new_nodes') != 0 or applied.get('positive_identity_merges') != 0):
            errors.append({'kind': 'ACTUAL_APPLIED_METADATA_NOT_BOUND'})
        expected_links = sum(o['op'] == 'link' for o in operations)
        actual_links = sum(con.execute('SELECT count(*) FROM ' + table + ' WHERE source=?', (SOURCE,)).fetchone()[0]
                           for table in ('edges', 'entity_relations'))
        if actual_links != expected_links:
            errors.append({'kind': 'WHOLE_NEW_SOURCE_LINK_CENSUS_DIFFERS', 'actual': actual_links, 'expected': expected_links})
        if not allow_unfrozen_fixture:
            frozen = metadata.get('structure_frozen_build_manifest', {}).get('inputs', {})
            for name in (INPUT_NAME, operation_name):
                if frozen.get(name) != sha((inputs / name).read_bytes()):
                    errors.append({'kind': 'FINAL_FROZEN_INPUT_NOT_BOUND', 'name': name})
            expected_auditor = metadata.get('structure_frozen_build_manifest', {}).get('code', {}).get('scripts/audit_owned_scope_repairs.py')
            if expected_auditor != sha(Path(__file__).read_bytes()):
                errors.append({'kind': 'ACTUAL_INDEPENDENT_AUDITOR_NOT_FROZEN'})
    report = {'schema': 'FINEATLAS_INDEPENDENT_OWNED_SCOPE_AUDIT_V1', 'database': str(database),
              'database_revision': metadata.get('database_revision'), 'release': metadata.get('release'),
              'pass': not errors, 'preflight_only': bool(preflight or allow_unfrozen_fixture),
              'fixture_only': bool(allow_unfrozen_fixture), 'manifest_sha256': sha(path.read_bytes()),
              'operations_sha256': sha(raw), 'operation_count': len(operations),
              'operations': dict(Counter(o['relation'] for o in operations)),
              'added_source_links': sum(o['op'] == 'link' for o in operations),
              'reviewed_source_assertions': len(reviewed),
              'mapping_changes': sum(o['op'] in {'migrate_nominal_design_mapping', 'review_dataset_mapping'} for o in operations),
              'role_corrections': sum(o['op'] == 'correct_role' for o in operations),
              'primary_snapshots_dir': str(Path(primary_snapshots_dir).resolve()) if primary_snapshots_dir else None,
              'verified_primary_sources': verified_sources, 'identity_component_censuses': len(partition_sets),
              'verified_purpose_source_reviews': verified_purpose_sources,
              'author_annotations_verified': len(author_records) if author_records else 0,
              'actual_new_link_root_reachability': routes, 'new_nodes': 0, 'positive_identity_merges': 0,
              'errors': errors}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    con.close()
    print(json.dumps({k: v for k, v in report.items() if k not in {'errors', 'actual_new_link_root_reachability'}}))
    return not errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--primary-snapshots-dir', type=Path)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--allow-unfrozen-fixture', action='store_true')
    args = parser.parse_args()
    raise SystemExit(0 if run(args.database, args.inputs, args.output, args.preflight,
                             args.primary_snapshots_dir, args.allow_unfrozen_fixture) else 1)
