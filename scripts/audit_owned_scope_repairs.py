#!/usr/bin/env python3
"""Audit owned-scope changes through source SQL, without importing the builder."""
from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
INPUT_NAME = 'structure_owned_scope_repairs.json'
SOURCE = 'Complete owned source scope adjudication'
REVIEW_TABLES = {'review_bridge': 'bridges', 'review_typed_relation': 'entity_relations'}
NAVIGATION_ROLES = {
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


def row_at(con, table, identifier, key='id'):
    if table not in {'nodes', 'edges', 'entity_relations', 'bridges', 'evidence', 'node_profiles'}:
        raise ValueError('Unsafe source witness table')
    if key not in {'uid', 'id', 'evidence_id'}:
        raise ValueError('Unsafe source witness key')
    row = con.execute('SELECT * FROM ' + table + ' WHERE ' + key + '=?', (identifier,)).fetchone()
    return dict(row) if row else None


def node_role(con, node):
    profile = row_at(con, 'node_profiles', node['uid'], 'uid')
    return (profile.get('node_kind') if profile else None) or {
        'model': 'MODEL', 'model_family': 'MODEL_FAMILY', 'series': 'MODEL_FAMILY',
        'configuration': 'CONFIGURATION', 'model_year': 'CONFIGURATION',
    }.get((node['rank'] or '').lower(), 'CLASS')


def source_witness(con, witness):
    table = witness.get('table', 'nodes')
    identifier = witness.get('id') if table != 'nodes' else witness['uid']
    row = row_at(con, table, identifier, 'uid' if table == 'nodes' else 'id')
    if not row or sha(row['data']) != witness['data_sha256']:
        raise ValueError('Whole retained source witness bytes changed')
    data = json.loads(row['data'])
    field = witness['field']
    value = data
    for part in field.split('.'):
        value = value.get(part) if isinstance(value, dict) else None
    if value is None and '.' not in field:
        value = data.get('evidence_record', {}).get(field)
    if value != witness['statement']:
        raise ValueError('Witness is not its exact complete retained field')
    return row


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


def identity_peer(con, first, second):
    left, right = (row_at(con, 'nodes', uid, 'uid') for uid in (first, second))
    if (not left or not right or left['visibility'] != 'ACTIVE' or right['visibility'] != 'ACTIVE'
            or left['component_id'] != right['component_id'] or node_role(con, left) != node_role(con, right)):
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
    return re.split(r'[.;]\s+|\s+(?:which|that|whose|derived|based|replacing|built|designed|manufactured|produced)\b',
                    predicate, maxsplit=1, flags=re.I)[0]


def role_valid(con, relation, left, right):
    allowed = NAVIGATION_ROLES.get(relation)
    return bool(allowed and node_role(con, left) in allowed[0] and node_role(con, right) in allowed[1])


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
            "AND relation='IS_A' AND status IN ('ACTIVE','BACKBONE_ACTIVE')", (peer['uid'],)))
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
                        or not role_valid(con, op['relation'], child, parent)):
                    raise ValueError('Actual grounded endpoint bytes or role grain differ')
                if proof.get('world_identity_assertion') is not False or proof.get('no_identity_merges') is not True:
                    raise ValueError('A physical type link cannot certify an identity merge')
                witnesses = proof['source_witnesses']
                if len(witnesses) < 2 or not proof.get('whole_subject_scope_review'):
                    raise ValueError('Whole own subject and complete parent scope are required')
                own = witnesses[0]['statement']
                phrase = own_assertion_phrase(own)
                if re.search(r'\b(?:not|never|fictional|virtual|imaginary|toy|scale model|parts? of|engine for)\b', phrase, re.I):
                    raise ValueError('Incidental or incompatible clause cannot supply the own physical genus')
                genus = proof.get('physical_genus')
                words = lambda value: re.findall(r'[^\W_]+', value.casefold(), re.UNICODE)
                if not isinstance(genus, str) or not words(genus):
                    raise ValueError('Physical genus must be explicit in the whole source review')
                declared_words, phrase_words = words(genus), words(phrase)
                if not any(phrase_words[i:i + len(declared_words)] == declared_words
                           for i in range(len(phrase_words) - len(declared_words) + 1)):
                    raise ValueError('Declared physical genus exists only outside the own first assertion')
                if (witnesses[0].get('table', 'nodes') == 'nodes'
                        and not identity_peer(con, child['uid'], witnesses[0]['uid'])):
                    raise ValueError('Attached different-source object cannot supply the own scope')
                if not preflight:
                    table = 'edges' if op['relation'] == 'IS_A' else 'entity_relations'
                    left, right = ('child_uid', 'parent_uid') if table == 'edges' else ('subject_uid', 'object_uid')
                    rows = con.execute('SELECT * FROM ' + table + ' WHERE ' + left + '=? AND ' + right + '=? AND relation=? AND source=?',
                                       (op['uid'], op['parent'], op['relation'], SOURCE)).fetchall()
                    if len(rows) != 1 or rows[0]['status'] != 'ACTIVE' or json.loads(rows[0]['data']).get('admission_basis') != proof:
                        raise ValueError('Actual new scoped link is absent or differs')
                    eid = 'usability:' + sha(dump(proof)); evidence = row_at(con, 'evidence', eid, 'evidence_id')
                    if not evidence or evidence['payload'] != dump(proof) or evidence['payload_sha256'] != sha(dump(proof)):
                        raise ValueError('Actual new physical link evidence differs')
                    if table == 'entity_relations' and rows[0]['evidence_id'] != eid:
                        raise ValueError('Actual typed link points at a different evidence record')
                    exact_history(con, 'owned_scope_link', op['uid'], {'prior_assertions': proof.get('prior_assertions', [])},
                                  {'parent_uid': op['parent'], 'relation': op['relation']}, proof)
                    if reaches(con, op['parent'], op['uid']):
                        raise ValueError('New direction creates a canonical source identity cycle')
                    routes[op['uid']] = reaches(con, op['uid'], 'wordnet31:00001740-n')
                    if not routes[op['uid']]:
                        raise ValueError('New legal connection does not reach the physical root')
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
                    exact_history(con, 'bridge_scope_review' if table == 'bridges' else 'typed_scope_review',
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
              'primary_snapshots_dir': str(Path(primary_snapshots_dir).resolve()) if primary_snapshots_dir else None,
              'verified_primary_sources': verified_sources, 'identity_component_censuses': len(partition_sets),
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
