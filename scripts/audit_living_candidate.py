#!/usr/bin/env python3
"""Independent source/SQL/public-SDK acceptance of the living candidate.

No builder, source adapter, graph admission helper, or private SDK judge is used.
The four old hashes are frozen 1.10.1 preservation evidence, not type rules.
"""
from __future__ import annotations

if not __debug__:
    raise RuntimeError("Optimized Python is forbidden for mandatory structural checks")


import argparse
from collections import Counter, defaultdict, deque
import copy
import hashlib
import json
from pathlib import Path
import random
import re
import sqlite3
import sys
import tempfile
import time
from urllib.parse import quote

if '--installed-sdk' not in sys.argv:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
else:
    import fineatlas
    assert Path(fineatlas.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()) and 'site-packages' in Path(fineatlas.__file__).parts, 'Use the installed SDK'

VIEWS = ('strict', 'taxonomy', 'unified')
DOMAINS = ('furniture', 'lighting', 'bags_and_luggage',
           'kitchen_and_tableware', 'toys', 'hand_tools')
CHINESE = {'furniture': '家具', 'lighting': '照明', 'bags_and_luggage': '箱包',
           'kitchen_and_tableware': '厨具餐具', 'toys': '玩具', 'hand_tools': '手工具'}
OLD_HASHES = {
    'abo-listing:amazon.com:B072ZLCB3M': 'e9ad22afcce651a3dece0b06cb8e0af940cd77bf7d2f15d1736e5bd59d3c808a',
    'abo-listing:amazon.com:B07TMH6289': '8de82116da6584a6862c3e4fbb6c22d71de6694ab929207e825119f531dab106',
    'abo-listing:amazon.com:B075X4QMW7': '12e699a6e325933a3be3338b2250d61d6fc9f28fca0f75721392d0d64df69999',
    'abo-listing:amazon.com:B07F2X8K62': '794bedf0683ca64407321da4d96968e06cc58f2dd250e13194a1ad5ade12f5e8',
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def native_fields(native):
    fields = {'catalogue': {x.get('node_name') for x in native.get('node', [])
                           if isinstance(x, dict) and isinstance(x.get('node_name'), str)
                           and x.get('node_name')},
              'native_product_type': {x['value'] for x in native.get('product_type', [])}}
    for source, field in [('brand', 'brand'), ('color', 'color'),
                          ('material', 'material'), ('model_number', 'native_model')]:
        fields[field] = {x['value'] for x in native.get(source, [])
                         if isinstance(x, dict) and isinstance(x.get('value'), str)}
    return {(field, value) for field, values in fields.items() for value in values if value}


def audit_record(c, expected, *, views=VIEWS):
    """Inspect a real row against independent frozen expectations and source arcs."""
    uid = expected['uid']
    errors = []

    def require(condition, name):
        if not condition:
            errors.append({'uid': uid, 'check': name})

    node = c.execute('SELECT * FROM nodes WHERE uid=?', (uid,)).fetchone()
    require(node is not None, 'source_uid_exists')
    if node is None:
        return errors
    profile = c.execute('SELECT * FROM node_profiles WHERE uid=?', (uid,)).fetchone()
    require(node['visibility'] == 'ACTIVE', 'active_source_configuration')
    require(profile and profile['node_kind'] == 'CONFIGURATION', 'configuration_role')
    require(node['domain'] == expected['domain'], 'source_domain')
    proof = json.loads(node['data'])
    native = proof.get('native_record', {})
    require(sha(native) == expected['record_sha256'] == proof.get('source_record_sha256'),
            'native_record_preserved_hash')
    require(native == expected['proof']['native_record'], 'native_record_exact')
    source_uid = 'abo-listing:' + quote(str(native.get('domain_name', '')), safe='') + ':' + quote(
        str(native.get('item_id', '')), safe='')
    require(uid == source_uid, 'marketplace_source_identity')
    if expected.get('legacy'):
        require(proof.get('not_global_model_identity') is True and
                proof.get('not_physical_instance') is True, 'legacy_source_scope_only')
    else:
        require(proof == expected['proof'], 'frozen_proof_preserved')
        require(proof.get('world_model_identity_verified') is False and
                proof.get('cross_source_identity_inferred') is False and
                proof.get('identity_scope') == 'SOURCE_CATALOGUE_CONFIGURATION',
                'world_identity_unconfirmed')
    require('CC BY 4.0' in proof.get('license', '') and bool(proof.get('license_uri')),
            'source_license')
    require(not c.execute("SELECT 1 FROM edges WHERE child_uid=? AND status IN "
                          "('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE') LIMIT 1", (uid,)).fetchone(),
            'no_configuration_classification_edges')
    require(not c.execute("SELECT 1 FROM bridges WHERE status='ACTIVE' AND relation='SAME_CONCEPT' "
                          "AND (left_uid=? OR right_uid=?) LIMIT 1", (uid, uid)).fetchone(),
            'no_cross_source_identity_bridge')
    require(c.execute('SELECT count(*) FROM nodes WHERE component_id=?',
                      (node['component_id'],)).fetchone()[0] == 1,
            'source_configuration_component_distinct')
    active = c.execute("SELECT * FROM entity_relations WHERE subject_uid=? AND status='ACTIVE'",
                       (uid,)).fetchall()
    require({(r['object_uid'], r['relation']) for r in active} ==
            {(p, 'CONFIGURATION_TYPE_OF') for p in expected['parent_uids']},
            'actual_typed_parent_set')
    for relation in active:
        evidence = c.execute('SELECT * FROM evidence WHERE evidence_id=?',
                             (relation['evidence_id'],)).fetchone()
        require(bool(relation['source']) and evidence is not None, 'typed_source_evidence')
        require(json.loads(relation['data']).get('is_class_inclusion') is False,
                'typed_relation_not_is_a')
        if evidence:
            require(hashlib.sha256(evidence['payload'].encode()).hexdigest() ==
                    evidence['payload_sha256'], 'typed_evidence_hash')
            require(json.loads(evidence['payload']).get('source_record_sha256') == expected['record_sha256'],
                    'typed_evidence_source_record')
    for parent, parent_proof in expected['parent_proofs'].items():
        actual = c.execute('SELECT data,description FROM nodes WHERE uid=?', (parent,)).fetchone()
        parent_profile = c.execute('SELECT node_kind FROM node_profiles WHERE uid=?', (parent,)).fetchone()
        require(not parent_profile or parent_profile[0] == 'CLASS', 'configuration_type_parent_is_class')
        require(actual and actual['description'] == parent_proof['definition'] and
                hashlib.sha256(actual['data'].encode()).hexdigest() ==
                parent_proof['native_record_sha256'], 'parent_definition_scope_preserved')
        require(parent not in ('wordnet31:00001740-n', 'wordnet31:00002684-n',
                               'wordnet31:00001930-n'), 'no_arbitrary_broad_root_parent')
    if re.search(r'\b(?:two.seater|2.seater|loveseat|love seat)\b', node['label'], re.I):
        if native.get('product_type') == [{'value': 'CHAIR'}]:
            require(set(expected['parent_uids']) == {'wordnet31:04169042-n'},
                    'multiseat_not_single_person_chair')
    for name in native.get('item_name', []):
        if not isinstance(name, dict) or not isinstance(name.get('value'), str) or not name['value'].strip():
            continue
        language = (name.get('language_tag') or 'und').replace('_', '-')
        require(c.execute('SELECT 1 FROM node_names WHERE uid=? AND name=? AND language=?',
                          (uid, name['value'], language)).fetchone() is not None,
                'source_name_language_preserved')
        require(c.execute('SELECT 1 FROM aliases WHERE uid=? AND raw_alias=?',
                          (uid, name['value'])).fetchone() is not None,
                'raw_source_alias_searchable')
    field_rows = c.execute('SELECT * FROM source_field_values WHERE uid=?', (uid,)).fetchall()
    fields = {(r['field'], r['value']) for r in field_rows if r['value']}
    require(native_fields(native) <= fields, 'all_native_source_fields_preserved')
    require(fields <= native_fields(native), 'no_fabricated_or_relabelled_source_fields')
    for field_row in field_rows:
        evidence = c.execute('SELECT * FROM evidence WHERE evidence_id=?',
                             (field_row['evidence_id'],)).fetchone()
        require(bool(field_row['source']) and evidence and
                json.loads(evidence['payload']).get('source_record_sha256') == expected['record_sha256'],
                'source_field_provenance')
    for field, value in fields:
        if not value:
            continue
        require(c.execute('SELECT 1 FROM browse_facets WHERE uid=? AND facet=? AND value=?',
                          (uid, field, value)).fetchone() is not None, 'native_facet_indexed')
    domain = c.execute('SELECT * FROM domain_registry WHERE canonical_name=?',
                       (expected['domain'],)).fetchone()
    require(domain is not None, 'domain_registered')
    if not domain:
        return errors
    for view in views:
        member = c.execute('SELECT * FROM domain_members WHERE domain_id=? AND view=? AND uid=?',
                           (domain['domain_id'], view, uid)).fetchone()
        require(member is not None and member['role'] == 'CONFIGURATION', 'domain_members:' + view)
        path = c.execute('SELECT * FROM view_paths WHERE view=? AND component_id=?',
                         (view, node['component_id'])).fetchone()
        require(path is not None and path['depth'] > 0 and path['contains_terminal'] == 1
                and path['typed_route'] == 1 and path['witness_id'] < 0, 'typed_root_cache:' + view)
        if path:
            witness = c.execute('SELECT * FROM entity_relations WHERE id=?',
                                (-path['witness_id'],)).fetchone()
            require(witness and witness['subject_uid'] == uid and witness['status'] == 'ACTIVE'
                    and witness['relation'] == 'CONFIGURATION_TYPE_OF'
                    and witness['object_uid'] in expected['parent_uids'], 'typed_cache_witness:' + view)
        for relation in active:
            parent = c.execute('SELECT component_id FROM nodes WHERE uid=?',
                               (relation['object_uid'],)).fetchone()
            if parent is None:
                require(False, 'typed_parent_exists')
                continue
            link = c.execute("SELECT * FROM browse_links WHERE view=? AND parent_component=? "
                             "AND child_component=? AND role='CONFIGURATION' AND relation=?",
                             (view, parent[0], node['component_id'], relation['relation'])).fetchone()
            require(link is not None and link['storage'] == 'entity' and
                    link['record_id'] == relation['id'], 'typed_browse_source_link:' + view)
    return errors


def trace_cached_witness(c, view, component, root_component, memo):
    """Independently follow signed witnesses and strictly decreasing cache depths."""
    trail, seen = [], set()
    while component not in memo:
        if component in seen:
            return 'CACHE_CYCLE'
        seen.add(component)
        path = c.execute('SELECT * FROM view_paths WHERE view=? AND component_id=?',
                         (view, component)).fetchone()
        if not path:
            return 'MISSING_PATH_RECORD'
        trail.append(component)
        if path['depth'] == 0:
            if component != root_component or path['witness_id'] is not None:
                return 'FALSE_ROOT'
            memo[component] = True
            break
        witness = path['witness_id']
        if not witness:
            return 'MISSING_WITNESS'
        if witness < 0:
            arc = c.execute('SELECT subject_uid child,object_uid parent,status,relation FROM entity_relations WHERE id=?',
                            (-witness,)).fetchone()
            legal = arc and arc['status'] == 'ACTIVE' and arc['relation'] == 'CONFIGURATION_TYPE_OF'
        else:
            arc = c.execute('SELECT child_uid child,parent_uid parent,status,relation FROM edges WHERE id=?',
                            (witness,)).fetchone()
            legal = arc and ((arc['relation'] == 'IS_A' and arc['status'] in
                             (('ACTIVE', 'BACKBONE_ACTIVE') if view == 'unified' else ('ACTIVE',))) or
                            (view != 'strict' and arc['relation'] in ('TAXONOMIC_PARENT', 'NATIVE_CLASSIFICATION_PARENT')
                             and arc['status'] == 'TYPED_ACTIVE'))
        if not legal:
            return 'ILLEGAL_SOURCE_WITNESS'
        endpoints = {r['uid']: r for r in c.execute('SELECT uid,component_id,visibility FROM nodes WHERE uid IN (?,?)',
                                                  (arc['child'], arc['parent']))}
        if len(endpoints) != 2 or endpoints[arc['child']]['component_id'] != component:
            return 'WITNESS_ENDPOINT_MISMATCH'
        parent_component = endpoints[arc['parent']]['component_id']
        next_path = c.execute('SELECT depth FROM view_paths WHERE view=? AND component_id=?',
                             (view, parent_component)).fetchone()
        if (not next_path or next_path[0] != path['depth'] - 1 or
                path['parent_component_id'] != parent_component or
                any(r['visibility'] != 'ACTIVE' for r in endpoints.values())):
            return 'DEPTH_OR_PARENT_MISMATCH'
        component = parent_component
    for item in trail:
        memo[item] = True
    return None


def native_boundary_path(c, uid, roots, view):
    queue = deque([(uid, [])])
    seen = {uid}
    while queue:
        current, path = queue.popleft()
        if current in roots:
            return path
        for arc in c.execute('SELECT id,parent_uid,relation,status FROM edges WHERE child_uid=?', (current,)):
            legal = (arc['relation'] == 'IS_A' and arc['status'] in
                     (('ACTIVE', 'BACKBONE_ACTIVE') if view == 'unified' else ('ACTIVE',))) or (
                view != 'strict' and arc['relation'] in ('TAXONOMIC_PARENT', 'NATIVE_CLASSIFICATION_PARENT')
                and arc['status'] == 'TYPED_ACTIVE')
            if not legal or arc['parent_uid'] in seen:
                continue
            seen.add(arc['parent_uid'])
            queue.append((arc['parent_uid'], path + [dict(arc)]))
        if len(seen) > 10000:
            raise RuntimeError('Native boundary search exceeded explicit work bound')
    return None


def collect_pages(fetch, *, limit, key='uid'):
    items, cursors, cursor, pages = [], set(), None, 0
    while True:
        page = fetch(limit, cursor)
        pages += 1
        values = page['items']
        if page.get('status') not in (None, 'OK', 'EMPTY'):
            raise AssertionError('Unexpected page status: ' + str(page.get('status')))
        items.extend(values)
        after = page['next_cursor']
        if bool(after) != bool(page['has_more']):
            raise AssertionError('Cursor/has_more inconsistency')
        if not after:
            break
        if after in cursors or not values:
            raise AssertionError('Cursor repeated or empty advancing page')
        cursors.add(after)
        cursor = after
        if pages > 10000:
            raise AssertionError('Pagination work bound exceeded')
    keys = [item[key] for item in items]
    if len(keys) != len(set(keys)):
        raise AssertionError('Duplicate item across keyset pages')
    return items, pages


def self_test():
    """Real malformed SQL fixtures for the source/cache errors found this round."""
    native = {'domain_name': 'amazon.fixture', 'item_id': 'ONE',
              'product_type': [{'value': 'CHAIR'}],
              'item_name': [{'language_tag': 'en_US', 'value': 'Two-Seater Loveseat Chair'}],
              'node': [{'node_name': '/Furniture/Chairs'}], 'brand': [{'value': 'Source brand'}]}
    uid, parent = 'abo-listing:amazon.fixture:ONE', 'wordnet31:04169042-n'
    proof = {'native_record': native, 'source_record_sha256': sha(native),
             'license': 'CC BY 4.0', 'license_uri': 'https://source/CC-BY',
             'world_model_identity_verified': False, 'cross_source_identity_inferred': False,
             'identity_scope': 'SOURCE_CATALOGUE_CONFIGURATION'}
    expected = {'uid': uid, 'domain': 'furniture', 'record_sha256': sha(native), 'proof': proof,
                'parent_uids': [parent], 'parent_proofs': {parent: {'definition': 'a seat',
                    'native_record_sha256': hashlib.sha256(b'{}').hexdigest()}}}
    c = sqlite3.connect(':memory:');c.row_factory = sqlite3.Row
    c.executescript('''
      CREATE TABLE nodes(uid PRIMARY KEY,label,domain,data,description,visibility,component_id);
      CREATE TABLE node_profiles(uid PRIMARY KEY,node_kind);
      CREATE TABLE entity_relations(id PRIMARY KEY,subject_uid,object_uid,relation,status,source,evidence_id,data);
      CREATE TABLE evidence(evidence_id PRIMARY KEY,payload,payload_sha256);
      CREATE TABLE edges(id PRIMARY KEY,child_uid,parent_uid,relation,status);
      CREATE TABLE bridges(left_uid,right_uid,status,relation);
      CREATE TABLE node_names(uid,name,language);
      CREATE TABLE aliases(uid,raw_alias);
      CREATE TABLE source_field_values(uid,field,value,source,evidence_id);
      CREATE TABLE browse_facets(uid,facet,value);
      CREATE TABLE domain_registry(domain_id,canonical_name,root_uids);
      CREATE TABLE domain_members(domain_id,view,uid,role);
      CREATE TABLE view_paths(view,component_id,depth,contains_terminal,typed_route,witness_id,parent_component_id);
      CREATE TABLE browse_links(view,parent_component,child_component,role,relation,storage,record_id);
    ''')
    c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?)', (uid, native['item_name'][0]['value'],
        'furniture', canonical(proof), '', 'ACTIVE', 2))
    c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?)', (parent, 'seat', 'furniture', '{}', 'a seat', 'ACTIVE', 1))
    c.execute('INSERT INTO node_profiles VALUES(?,?)', (uid, 'CONFIGURATION'))
    c.execute('INSERT INTO node_profiles VALUES(?,?)', (parent, 'CLASS'))
    c.execute('INSERT INTO entity_relations VALUES(1,?,?,?,?,?,?,?)',
              (uid, parent, 'CONFIGURATION_TYPE_OF', 'ACTIVE', 'source', 'proof',
               canonical({'is_class_inclusion': False})))
    c.execute('INSERT INTO evidence VALUES(?,?,?)', ('proof', canonical(proof), sha(proof)))
    c.execute('INSERT INTO node_names VALUES(?,?,?)', (uid, native['item_name'][0]['value'], 'en-US'))
    c.execute('INSERT INTO aliases VALUES(?,?)', (uid, native['item_name'][0]['value']))
    for field, value in native_fields(native):
        c.execute('INSERT INTO source_field_values VALUES(?,?,?,?,?)', (uid, field, value, 'source', 'proof'))
        c.execute('INSERT INTO browse_facets VALUES(?,?,?)', (uid, field, value))
    c.execute('INSERT INTO domain_registry VALUES(1,?,?)', ('furniture', canonical([parent])))
    for view in VIEWS:
        c.execute('INSERT INTO domain_members VALUES(1,?,?,?)', (view, uid, 'CONFIGURATION'))
        c.execute('INSERT INTO view_paths VALUES(?,2,1,1,1,-1,1)', (view,))
        c.execute('INSERT INTO browse_links VALUES(?,1,2,?,?,?,1)',
                  (view, 'CONFIGURATION', 'CONFIGURATION_TYPE_OF', 'entity'))
    assert not audit_record(c, expected)
    mutations = [
        ('delete domain member', "DELETE FROM domain_members WHERE view='unified'", 'domain_members:unified'),
        ('missing alias', 'DELETE FROM aliases', 'raw_source_alias_searchable'),
        ('missing source field', "DELETE FROM source_field_values WHERE field='brand'", 'all_native_source_fields_preserved'),
        ('brand relabelled manufacturer', "UPDATE source_field_values SET field='manufacturer' WHERE field='brand'", 'no_fabricated_or_relabelled_source_fields'),
        ('missing facet', "DELETE FROM browse_facets WHERE facet='brand'", 'native_facet_indexed'),
        ('missing browse link', "DELETE FROM browse_links WHERE view='taxonomy'", 'typed_browse_source_link:taxonomy'),
        ('wrong relation', "UPDATE entity_relations SET relation='IS_A'", 'actual_typed_parent_set'),
        ('missing evidence', 'DELETE FROM evidence', 'typed_source_evidence'),
        ('wrong role', "UPDATE node_profiles SET node_kind='MODEL'", 'configuration_role'),
        ('typed parent wrong role', "UPDATE node_profiles SET node_kind='MODEL' WHERE uid='" + parent + "'", 'configuration_type_parent_is_class'),
        ('scope changed', "UPDATE nodes SET description='single person chair' WHERE component_id=1", 'parent_definition_scope_preserved'),
        ('fake root cache', "UPDATE view_paths SET witness_id=1 WHERE view='unified'", 'typed_root_cache:unified'),
        ('source class edge', "INSERT INTO edges VALUES(1,'" + uid + "','" + parent + "','IS_A','ACTIVE')", 'no_configuration_classification_edges'),
    ]
    for label, sql, check in mutations:
        c.execute('SAVEPOINT malformed')
        c.execute(sql)
        errors = audit_record(c, expected)
        assert any(e['check'] == check for e in errors), (label, errors)
        c.execute('ROLLBACK TO malformed');c.execute('RELEASE malformed')
    changed = copy.deepcopy(expected)
    changed['parent_uids'] = ['wordnet31:03005231-n']
    assert any(e['check'] == 'multiseat_not_single_person_chair' for e in audit_record(c, changed))
    print(canonical({'self_test': 'PASS', 'malformed_sql_regressions': len(mutations) + 1}))


def run(database, inputs, output):
    from fineatlas import FineAtlas
    start = time.monotonic();output.mkdir(parents=True, exist_ok=True)
    input_file = inputs / 'living_catalogue_records.jsonl' if inputs.is_dir() else inputs
    manifest_file = input_file.with_name('living_catalogue_manifest.json')
    manifest = json.loads(manifest_file.read_text())
    rows = [json.loads(line) for line in input_file.open()]
    errors, stages = [], {}
    if file_sha(input_file) != manifest['records_sha256']:
        raise ValueError('Frozen living input SHA differs from its source manifest')
    c = sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    c.row_factory = sqlite3.Row;c.execute('PRAGMA query_only=ON')
    metadata = {r[0]: json.loads(r[1]) for r in c.execute('SELECT key,value FROM metadata')}
    if not metadata.get('usability_indexes_ready') or not metadata.get('browse_indexes_ready'):
        raise ValueError('Candidate graph/browse indexes not ready; audit cannot accept a partial build')
    if metadata.get('browse_index_revision') != metadata.get('database_revision'):
        raise ValueError('Candidate browse index revision differs')
    if set(manifest['existing_uids']) != set(OLD_HASHES):
        raise ValueError('Frozen old-four source UID cohort differs from protected 1.10.1')
    old_fields = {r['uid']: r for r in manifest.get('existing_source_fields', [])}
    if set(old_fields) != set(OLD_HASHES):
        raise ValueError('Frozen preserved-source field cohort missing or ambiguous')
    expected = {r['uid']: {**r, 'parent_proofs': r['proof']['parents']} for r in rows}
    if len(expected) != len(rows):
        raise ValueError('Duplicate source identity in frozen batch')
    for uid, raw_hash in OLD_HASHES.items():
        node = c.execute('SELECT * FROM nodes WHERE uid=?', (uid,)).fetchone()
        if not node:
            errors.append({'uid': uid, 'check': 'protected_1_10_1_source_uid_preserved'});continue
        proof = json.loads(node['data'])
        if old_fields[uid]['record_sha256'] != raw_hash or old_fields[uid]['native_record'] != proof['native_record']:
            errors.append({'uid': uid, 'check': 'old_native_record_matches_frozen_source_fields'})
        expected[uid] = {'uid': uid, 'domain': 'furniture', 'label': node['label'],
            'legacy': True, 'record_sha256': raw_hash, 'proof': proof,
            'parent_uids': [proof['parent_uid']], 'parent_proofs': {proof['parent_uid']: {
                'definition': proof['parent_definition'],
                'native_record_sha256': proof['parent_native_record_sha256']}}}
    actual_abo = {r[0] for r in c.execute("SELECT uid FROM nodes WHERE uid GLOB 'abo-listing:*'")}
    if actual_abo != set(expected):
        errors.append({'check': 'complete_source_uid_inventory', 'missing': sorted(set(expected) - actual_abo),
                       'unexpected': sorted(actual_abo - set(expected))})
    print('START independent SQL/source/cache checks', flush=True)
    root = c.execute('SELECT component_id FROM nodes WHERE uid=?', (metadata['root_uid'],)).fetchone()[0]
    path_memos = {v: {} for v in VIEWS}
    for index, row in enumerate(expected.values(), 1):
        errors.extend(audit_record(c, row))
        component = c.execute('SELECT component_id FROM nodes WHERE uid=?', (row['uid'],)).fetchone()
        if component:
            for view in VIEWS:
                problem = trace_cached_witness(c, view, component[0], root, path_memos[view])
                if problem:
                    errors.append({'uid': row['uid'], 'check': 'full_root_source_witness:' + view, 'reason': problem})
        if index % 1000 == 0:
            print('SQL checked', index, 'errors', len(errors), flush=True)
    stages['all_source_sql_seconds'] = time.monotonic() - start
    boundary_paths = []
    for domain in DOMAINS:
        registry = c.execute('SELECT * FROM domain_registry WHERE canonical_name=?', (domain,)).fetchone()
        if not registry:
            errors.append({'check': 'domain_registered', 'domain': domain});continue
        roots = set(json.loads(registry['root_uids']))
        parents = sorted({p for r in expected.values() if r['domain'] == domain for p in r['parent_uids']})
        for view in VIEWS:
            for parent in parents:
                path = native_boundary_path(c, parent, roots, view)
                if path is None:
                    errors.append({'check': 'native_domain_boundary_path', 'domain': domain, 'view': view, 'parent': parent})
                boundary_paths.append({'domain': domain, 'view': view, 'parent': parent,
                                       'roots': sorted(roots), 'source_path': path})
    (output / 'native_boundary_paths.json').write_text(json.dumps(boundary_paths, ensure_ascii=False, indent=2) + '\n')
    samples = []
    types = defaultdict(list)
    for row in rows:
        types[row['proof']['reviewed_native_product_type']].append(row)
    for typ, group in sorted(types.items()):
        samples.extend(random.Random('20261009:' + typ).sample(sorted(group, key=lambda r: r['uid']), min(5, len(group))))
    samples.extend(expected[uid] for uid in sorted(OLD_HASHES) if uid in expected)
    public, exported, pagination, timings = [], [], [], []
    print('START public SDK names/paths/domains/pagination/exports', flush=True)
    for view in VIEWS:
        with FineAtlas(database, relation_view=view) as atlas:
            for row in samples:
                then = time.monotonic()
                try:
                    found, pages = collect_pages(lambda limit, cursor: atlas.search_page(
                        row['label'], limit=limit, cursor=cursor, domain=row['domain'],
                        node_kind='CONFIGURATION', exact=True), limit=17)
                    assert row['uid'] in {n['uid'] for n in found}, 'exact search omitted source UID'
                    path = atlas.path_result(row['uid'])
                    assert path['status'] in ('ROOT', 'CONNECTED') and path['path'], path['status']
                    assert any(s.get('edge', {}).get('relation') == 'CONFIGURATION_TYPE_OF' for s in path['path']), 'public path dropped typed source relation'
                    location = atlas.browse_location(row['uid'], domain=row['domain'])
                    assert location['status'] == 'OK' and location['parents'], location['status']
                    public.append({'view': view, 'uid': row['uid'], 'exact_pages': pages,
                                   'path_status': path['status'], 'path': path['path']})
                except Exception as error:
                    errors.append({'check': 'public_exact_path_browse', 'uid': row['uid'], 'view': view,
                                   'error': repr(error)})
                timings.append(time.monotonic() - then)
            for domain in DOMAINS:
                try:
                    entry = atlas.domain(domain)
                    chinese = atlas.domain(CHINESE[domain])
                    assert entry and chinese and chinese['domain'] == domain, 'Chinese entry lookup failed'
                    portal = atlas.browse_domain(CHINESE[domain], limit=7)
                    assert portal['roots'], 'Chinese portal cannot browse real roots'
                    sql_all = {r[0] for r in c.execute('SELECT uid FROM domain_members WHERE domain_id=? AND view=? AND role=?',
                        (entry['domain_id'], view, 'CONFIGURATION'))}
                    size = 3 if len(sql_all) <= 100 else 97
                    nodes, pages = collect_pages(lambda limit, cursor: atlas.domain_page(
                        domain, limit=limit, cursor=cursor, node_kind='CONFIGURATION'), limit=size)
                    assert {n['uid'] for n in nodes} == sql_all, 'domain keyset/SQL inventory mismatch'
                    assert pages > 1, 'no multipage keyset exercise'
                    expected_abo = {u for u, r in expected.items() if r['domain'] == domain}
                    assert {u for u in sql_all if u.startswith('abo-listing:')} == expected_abo, 'domain ABO source UID inventory mismatch'
                    pagination.append({'view': view, 'domain': domain, 'source_configurations': len(expected_abo),
                                       'all_configurations': len(nodes), 'pages': pages, 'page_size': size,
                                       'chinese_entry': CHINESE[domain]})
                    path = output / (domain + '.' + view + '.configurations.jsonl')
                    then = time.monotonic()
                    result = atlas.export_domain(domain, path, page_size=47, node_kind='CONFIGURATION')
                    export_rows = [json.loads(line) for line in path.open()]
                    uids = [r['node']['uid'] for r in export_rows]
                    assert len(uids) == len(set(uids)) and set(uids) == sql_all, 'complete export/SQL/keyset mismatch'
                    assert result['nodes'] == len(uids), 'export count differs'
                    for exported_row in export_rows:
                        uid = exported_row['node']['uid']
                        if uid in expected:
                            assert exported_row['node']['node_kind'] == 'CONFIGURATION'
                            assert {r['relation'] for r in exported_row['parents']} == {'CONFIGURATION_TYPE_OF'}
                    exported.append({**result, 'bytes': path.stat().st_size, 'sha256': file_sha(path),
                                     'seconds': time.monotonic() - then})
                except Exception as error:
                    errors.append({'check': 'public_domain_pagination_export', 'domain': domain, 'view': view,
                                   'error': repr(error)})
            # Exhaust actual direct typed browsing under the broadest tested type.
            count, parent_component = c.execute("SELECT count(*),parent_component FROM browse_links WHERE view=? "
                "AND role='CONFIGURATION' AND relation='CONFIGURATION_TYPE_OF' AND representative_uid GLOB 'abo-listing:*' "
                "GROUP BY parent_component ORDER BY count(*) DESC LIMIT 1", (view,)).fetchone()
            parent = c.execute('SELECT uid FROM nodes WHERE component_id=? ORDER BY uid LIMIT 1',
                               (parent_component,)).fetchone()[0]
            try:
                items, pages = collect_pages(lambda limit, cursor: atlas.browse_children_page(
                    parent, limit=limit, cursor=cursor, node_kind='CONFIGURATION',
                    relation='CONFIGURATION_TYPE_OF', include_coarse=True), limit=79, key='identity_component')
                sql_components = {r[0] for r in c.execute("SELECT child_component FROM browse_links WHERE view=? "
                    "AND parent_component=? AND role='CONFIGURATION' AND relation='CONFIGURATION_TYPE_OF'", (view, parent_component))}
                assert {n['identity_component'] for n in items} == sql_components
                assert pages > 1
                pagination.append({'view': view, 'direct_parent': parent, 'items': len(items), 'pages': pages})
            except Exception as error:
                errors.append({'check': 'public_direct_browse_keyset', 'view': view, 'error': repr(error)})
    stages['total_seconds'] = time.monotonic() - start
    memberships = dict(c.execute("SELECT view,count(*) FROM domain_members WHERE uid GLOB 'abo-listing:*' GROUP BY view"))
    result = {'status': 'PASS' if not errors else 'FAIL', 'database': str(database.resolve()),
        'database_revision': metadata.get('database_revision'), 'input_sha256': file_sha(input_file),
        'new_source_configuration_inputs': len(rows), 'protected_old_source_uids': len(OLD_HASHES),
        'deduplicated_source_configuration_total': len(expected), 'all_source_inventory': len(actual_abo),
        'new_world_models_or_ordinary_classes': 0, 'public_fixed_samples': len(samples),
        'rooted_views_checked': list(VIEWS), 'membership_view_inventory_only': memberships.get('membership', 0),
        'domain_configuration_counts': dict(Counter(r['domain'] for r in expected.values())),
        'public_checks': len(public), 'pagination': pagination, 'exports': exported, 'errors': errors,
        'error_counts': dict(Counter(e['check'] for e in errors)), 'timings': stages,
        'public_sample_query_max_seconds': max(timings, default=0),
        'scope': 'Independent source SQL witnesses plus public SDK; no builder/adapter/internal admission function',
        'membership_limit': 'Native membership has no universal WordNet root witness; observed inventory reported without policy relaxation'}
    (output / 'public_fixed_sample_paths.json').write_text(json.dumps(public, ensure_ascii=False, indent=2) + '\n')
    (output / 'living_candidate_acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(canonical({k: result[k] for k in ('status', 'deduplicated_source_configuration_total',
        'public_checks', 'error_counts', 'timings')}), flush=True)
    c.close()
    return 0 if not errors else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path)
    parser.add_argument('--inputs', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--installed-sdk', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test();return 0
    if any(getattr(args, key) is None for key in ('database', 'inputs', 'output')):
        parser.error('--database --inputs --output are required unless --self-test')
    return run(args.database, args.inputs, args.output)


if __name__ == '__main__':
    raise SystemExit(main())
