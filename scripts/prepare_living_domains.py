#!/usr/bin/env python3
"""Freeze four grounded living-object portals; reuse imported WordNet concepts.

Preparation opens only a read-only database. apply_living_inputs is for the
builder's independent candidate, after semantic inputs and before graph/index
recomputation. Portal membership is navigation scope, never concept identity.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fineatlas import FineAtlas


DOMAINS = (
    ('kitchen_and_tableware', 'Kitchen utensils and tableware',
     ('wordnet31:03626258-n', 'wordnet31:04389081-n'),
     'Physical utensils for preparing food and articles for use at the table; prepared food is excluded.'),
    ('lighting', 'Lighting equipment',
     ('wordnet31:03641539-n', 'wordnet31:03641940-n', 'wordnet31:03672706-n'),
     'Physical lamps, lamp furniture and lighting fixtures, using distinct source synsets without merging senses.'),
    ('bags_and_luggage', 'Backpacks, handbags and luggage',
     ('wordnet31:02772753-n', 'wordnet31:02777157-n', 'wordnet31:02777635-n'),
     'Backpacks, personal handbags and travel luggage; unrelated senses of bag are excluded.'),
    ('toys', 'Toys and playthings', ('wordnet31:03971038-n',),
     'Artifacts designed to be played with; arbitrary scale models and generic objects are not inferred to be toys.'),
)
SOURCE_URI = 'https://wordnet.princeton.edu/download/current-version'


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def prepare(database, output):
    output.mkdir(parents=True, exist_ok=True)
    entries, rules, backbone = [], [], {}
    with FineAtlas(database, relation_view='unified') as atlas:
        c = atlas.con
        prior = [dict(r) for r in c.execute('SELECT * FROM domain_registry ORDER BY canonical_name')]
        for domain, label, roots, description in DOMAINS:
            existing = next((r for r in prior if r['canonical_name'] == domain), None)
            if existing and set(json.loads(existing['root_uids'])) != set(roots):
                raise ValueError('Existing portal has different scope: ' + domain)
            root_proofs = []
            for root in roots:
                node = c.execute('SELECT * FROM nodes WHERE uid=?', (root,)).fetchone()
                path = atlas.path_result(root)
                if not node or node['visibility'] != 'ACTIVE' or path['status'] not in ('ROOT', 'CONNECTED'):
                    raise ValueError('Root lacks a retained source witness: ' + root)
                root_proofs.append({'uid': root, 'label': node['label'], 'definition': node['description'],
                                    'native_record_sha256': hashlib.sha256(node['data'].encode()).hexdigest(),
                                    'synset_id': 'eng-31-' + root.split(':')[1], 'witness': path['path']})
                rules.append({'domain': domain, 'entry_uid': 'fineatlas-domain:' + domain,
                              'native_root_uid': root, 'wordnet_anchor_uid': root,
                              'relation': 'EXISTING_TYPED_CLASSIFICATION_PATH', 'definition': node['description'],
                              'synset_id': 'eng-31-' + root.split(':')[1], 'root_uid': atlas.root_uid,
                              'selection_basis': 'Explicit physical-object portal scope anchored to an already imported, root-connected WordNet 3.1 synset; no new hierarchy edge',
                              'witness': path['path']})
                # Capture every native WordNet parent, rather than only the display witness.
                queue = [root]
                while queue:
                    uid = queue.pop()
                    if uid in backbone:
                        continue
                    n = c.execute('SELECT * FROM nodes WHERE uid=?', (uid,)).fetchone()
                    if not n:
                        raise ValueError('Missing WordNet ancestor: ' + uid)
                    parents = [dict(r) for r in c.execute("SELECT * FROM edges WHERE child_uid=? AND source_relation='WORDNET_IS_A' AND parent_uid GLOB 'wordnet31:*' ORDER BY id", (uid,))]
                    backbone[uid] = {'uid': uid, 'synset_id': 'eng-31-' + uid.split(':')[1],
                                     'label': n['label'], 'definition': n['description'], 'source': 'WordNet 3.1',
                                     'selection_basis': 'Living portal root or original WordNet ancestor; descriptive metadata only',
                                     'native_record_sha256': hashlib.sha256(n['data'].encode()).hexdigest(),
                                     'original_parent_edge_ids': [r['id'] for r in parents]}
                    queue.extend(r['parent_uid'] for r in parents)
            entries.append({'domain': domain, 'label': label, 'root_uids': list(roots),
                            'description': description, 'source_uri': SOURCE_URI,
                            'proof': {'basis': 'DECLARED_PORTAL_UNION_OF_EXISTING_WORDNET_PHYSICAL_OBJECT_SYNSETS',
                                      'wordnet_version': '3.1', 'roots': root_proofs,
                                      'no_new_node_or_IS_A_or_identity': True,
                                      'portal_overlap_is_navigation_not_identity': True}})
        manifest = {'database_revision': atlas._revision, 'wordnet_version': '3.1',
                    'prior_domains': prior, 'new_domains': len(entries), 'new_root_rules': len(rules),
                    'added_class_nodes': 0, 'added_hierarchy_edges': 0,
                    'prior_aliases': [dict(r) for r in c.execute('SELECT a.*,r.canonical_name FROM domain_aliases a JOIN domain_registry r USING(domain_id) ORDER BY alias')],
                    'prior_attachment_rule_keys': [{k: json.loads(r['payload']).get(k) for k in ('domain', 'native_root_uid', 'wordnet_anchor_uid', 'synset_id', 'definition')} for r in c.execute('SELECT payload FROM unified_domain_rules ORDER BY domain_id,native_root_uid')],
                    'post_apply_requirements': ['Recompute all four graph/domain caches', 'Rebuild embedded browsing indexes against new revision', 'Check original domain scopes and aliases by canonical name']}
    (output / 'new_domains.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in entries))
    write_json(output / 'living_domain_rules.json', rules)
    write_json(output / 'living_backbone_nodes.json', sorted(backbone.values(), key=lambda r: r['uid']))
    write_json(output / 'living_domains_manifest.json', manifest)
    return {k: manifest[k] for k in ('new_domains', 'new_root_rules', 'added_class_nodes', 'added_hierarchy_edges')}


def apply_living_inputs(m, *, stage_key="living_domains_application"):
    """Extend canonical portals while verifying every protected attachment rule."""
    if not stage_key or not stage_key.replace("_", "").isalnum():
        raise ValueError("Explicit portal application namespace required")
    manifest_path = m.inputs / 'living_domains_manifest.json'
    if not manifest_path.exists():
        return {'living_domains': 0}
    c = m.c
    manifest = json.loads(manifest_path.read_text())
    fingerprint = hashlib.sha256(b''.join(name.encode() + b'\0' + (m.inputs / name).read_bytes() for name in
                                 ('new_domains.jsonl', 'living_domain_rules.json', 'living_backbone_nodes.json', 'living_domains_manifest.json'))).hexdigest()
    stage = c.execute("SELECT value FROM metadata WHERE key=?", (stage_key,)).fetchone()
    stage = json.loads(stage[0]) if stage else None
    if stage and stage['input_sha256'] != fingerprint:
        raise ValueError('Living portal inputs differ from an already applied stage; rebuild from the protected baseline')
    existing = {r['canonical_name']: dict(r) for r in c.execute('SELECT * FROM domain_registry')}
    for prior in manifest['prior_domains']:
        current = existing.get(prior['canonical_name'])
        if not current or set(json.loads(current['root_uids'])) != set(json.loads(prior['root_uids'])) or current['domain_id'] != prior['domain_id']:
            raise ValueError('Protected original domain scope/ID changed: ' + prior['canonical_name'])
    old_rules = []
    for row in c.execute('SELECT * FROM unified_domain_rules'):
        payload = json.loads(row['payload'])
        prior = next((r for r in existing.values() if r['domain_id'] == row['domain_id']), None)
        if not prior or payload['domain'] != prior['canonical_name'] or row['native_root_uid'] not in json.loads(prior['root_uids']):
            raise ValueError('Existing attachment rule does not match registry')
        old_rules.append(payload)
    nodes = json.loads((m.inputs / 'living_backbone_nodes.json').read_text())
    for node in nodes:
        native = c.execute('SELECT data,description,visibility FROM nodes WHERE uid=?', (node['uid'],)).fetchone()
        if not native or native['visibility'] != 'ACTIVE' or native['description'] != node['definition'] or hashlib.sha256(native['data'].encode()).hexdigest() != node['native_record_sha256']:
            raise ValueError('Frozen living synset changed: ' + node['uid'])
    if stage:
        entries = [json.loads(line) for line in (m.inputs / 'new_domains.jsonl').read_text().splitlines() if line.strip()]
        for entry in entries:
            current = existing.get(entry['domain'])
            if not current or set(json.loads(current['root_uids'])) != set(entry['root_uids']):
                raise ValueError('Applied living portal scope no longer matches frozen inputs')
        for alias in manifest['prior_aliases']:
            current = c.execute('SELECT domain_id FROM domain_aliases WHERE alias=?', (alias['alias'],)).fetchone()
            if not current or current[0] != existing[alias['canonical_name']]['domain_id']:
                raise ValueError('Applied stage lost a protected domain alias')
        expected = manifest['prior_attachment_rule_keys'] + json.loads((m.inputs / 'living_domain_rules.json').read_text())
        actual = {(r['domain'], r['native_root_uid']): r for r in old_rules}
        if len(actual) != len(expected):
            raise ValueError('Applied stage attachment-rule count differs')
        for rule in expected:
            current = actual.get((rule['domain'], rule['native_root_uid']))
            if not current or any(current.get(key) != rule.get(key) for key in ('wordnet_anchor_uid', 'synset_id', 'definition')):
                raise ValueError('Applied stage attachment-rule scope differs')
        return {**stage['summary'], 'status': 'VERIFIED_NO_OP'}
    portals = m.portals(preserve_registry=True)
    registry = {r['canonical_name']: dict(r) for r in c.execute('SELECT * FROM domain_registry')}
    for prior in manifest['prior_domains']:
        current = registry.get(prior['canonical_name'])
        if not current or set(json.loads(current['root_uids'])) != set(json.loads(prior['root_uids'])) or current['domain_id'] != prior['domain_id']:
            raise ValueError('Additive portal registration changed an original scope/ID')
    # portals() reconstructs root-derived aliases. Preserve every prior declared alias.
    for alias in manifest['prior_aliases']:
        did = registry[alias['canonical_name']]['domain_id']
        current = c.execute('SELECT domain_id FROM domain_aliases WHERE alias=?', (alias['alias'],)).fetchone()
        if current and current['domain_id'] != did:
            raise ValueError('Living portal alias conflicts with a protected alias: ' + alias['alias'])
        c.execute('INSERT OR REPLACE INTO domain_aliases VALUES(?,?,?)', (alias['alias'], did, alias['provenance']))
    rules = old_rules + json.loads((m.inputs / 'living_domain_rules.json').read_text())
    by_key = {}
    for rule in rules:
        entry = registry.get(rule['domain'])
        if not entry or rule['native_root_uid'] not in json.loads(entry['root_uids']):
            raise ValueError('Attachment rule no longer matches portal scope')
        rule = {**rule, 'domain_id': entry['domain_id']}
        by_key[(rule['domain_id'], rule['native_root_uid'])] = rule
    c.execute('DELETE FROM unified_domain_rules')
    c.executemany('INSERT INTO unified_domain_rules VALUES(?,?,?,?)',
                  [(r['domain_id'], r['native_root_uid'], r['wordnet_anchor_uid'], json.dumps(r, ensure_ascii=False)) for r in by_key.values()])
    for node in nodes:
        c.execute('INSERT OR REPLACE INTO unified_backbone_nodes VALUES(?,?)', (node['uid'], json.dumps(node, ensure_ascii=False)))
    m.meta('unified_attachment_rules', {'domains': len({r['domain_id'] for r in by_key.values()}),
                                      'rules': len(by_key), 'wordnet_version': '3.1',
                                      'selection_table': 'unified_backbone_nodes', 'rules_table': 'unified_domain_rules'})
    # Frozen browsing and membership tables must be regenerated before any publication.
    m.meta('browse_indexes_ready', False)
    m.meta('unified_ready', False)
    summary = {'living_domains': manifest['new_domains'], 'living_root_rules': manifest['new_root_rules'],
            'old_attachment_rules_checked': len(old_rules), 'old_attachment_rules_remapped': 0,
            'old_domain_ids_preserved': True, 'total_attachment_rules': len(by_key),
            'protected_original_domains': len(manifest['prior_domains']), 'portals': portals}
    m.meta(stage_key, {'input_sha256': fingerprint, 'summary': summary})
    c.commit()
    return {**summary, 'status': 'APPLIED'}


def prepare_expected_wordnet_scope(wordnet, output):
    """Freeze complete source-WordNet descendant sets for the four portal unions."""
    import sqlite3
    c = sqlite3.connect(wordnet.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    children = defaultdict(set)
    for child, parent in c.execute('SELECT child_uid,parent_uid FROM edges'):
        children[parent].add(child)
    scopes = []
    for domain, label, roots, _ in DOMAINS:
        descendants = set()
        queue = list(roots)
        while queue:
            uid = queue.pop()
            if uid in descendants:
                continue
            descendants.add(uid)
            queue.extend(children.get(uid, ()))
        scopes.append({'domain': domain, 'root_uids': list(roots), 'wordnet_source_uids': sorted(descendants),
                       'source_concept_count': len(descendants),
                       'root_direct_children': {root: sorted(children.get(root, ())) for root in roots}})
    c.close()
    result = {'wordnet_version': '3.1', 'source_sha256': hashlib.sha256(wordnet.read_bytes()).hexdigest(),
              'domains': scopes, 'count_basis': 'Unique source WordNet synsets in each portal union; domain overlap is allowed'}
    write_json(output, result)
    return {r['domain']: r['source_concept_count'] for r in scopes}


def audit_living_candidate(database, inputs, output):
    """Validate original scopes/aliases, complete WordNet cohorts and new configs."""
    manifest = json.loads((inputs / 'living_domains_manifest.json').read_text())
    expected = json.loads((inputs / 'living_expected_wordnet_scope.json').read_text())
    issues, domains, aliases = [], [], []
    with FineAtlas(database, relation_view='unified') as atlas:
        c = atlas.con
        registry = {r['canonical_name']: dict(r) for r in c.execute('SELECT * FROM domain_registry')}
        for prior in manifest['prior_domains']:
            current = registry.get(prior['canonical_name'])
            if not current or set(json.loads(current['root_uids'])) != set(json.loads(prior['root_uids'])):
                issues.append({'kind': 'PROTECTED_ORIGINAL_SCOPE_CHANGED', 'domain': prior['canonical_name']})
        for alias in manifest['prior_aliases']:
            actual = atlas.domain(alias['alias'])
            valid = bool(actual and actual['domain'] == alias['canonical_name'])
            aliases.append({'alias': alias['alias'], 'expected': alias['canonical_name'], 'pass': valid})
            if not valid:
                issues.append({'kind': 'PROTECTED_ALIAS_CHANGED', 'alias': alias['alias']})
        for scope in expected['domains']:
            entry = registry.get(scope['domain'])
            if not entry or set(json.loads(entry['root_uids'])) != set(scope['root_uids']):
                issues.append({'kind': 'NEW_SCOPE_MISSING_OR_CHANGED', 'domain': scope['domain']})
                continue
            roots = {uid: atlas.path_result(uid)['status'] for uid in scope['root_uids']}
            missing = []
            for uid in scope['wordnet_source_uids']:
                if not c.execute("SELECT 1 FROM domain_members WHERE domain_id=? AND view='unified' AND uid=?", (entry['domain_id'], uid)).fetchone():
                    missing.append(uid)
            cursor, paged, pages = None, [], 0
            while True:
                page = atlas.domain_page(scope['domain'], limit=100, cursor=cursor, node_kind='CLASS')
                paged.extend(item['uid'] for item in page['items'])
                pages += 1
                if not page['has_more']:
                    break
                cursor = page['next_cursor']
                if not cursor or pages >= 100:
                    issues.append({'kind': 'PUBLIC_PAGE_WORK_BOUND', 'domain': scope['domain']})
                    break
            cached = {r[0] for r in c.execute("SELECT uid FROM domain_members WHERE domain_id=? AND view='unified' AND role='CLASS'", (entry['domain_id'],))}
            pagination_valid = len(paged) == len(set(paged)) and set(paged) == cached
            if not pagination_valid:
                issues.append({'kind': 'PUBLIC_DOMAIN_PAGINATION_MISMATCH', 'domain': scope['domain']})
            result = {'domain': scope['domain'], 'root_statuses': roots,
                      'expected_source_wordnet_synsets': len(scope['wordnet_source_uids']),
                      'missing_wordnet_scope_uids': missing,
                      'class_source_uids': c.execute("SELECT count(*) FROM domain_members WHERE domain_id=? AND view='unified' AND role='CLASS'", (entry['domain_id'],)).fetchone()[0],
                      'class_identity_groups': c.execute("SELECT count(*) FROM domain_components WHERE domain_id=? AND view='unified' AND category='CLASSIFICATION'", (entry['domain_id'],)).fetchone()[0],
                      'public_pages': pages, 'public_paged_class_source_uids': len(paged),
                      'public_complete_pagination_matches_cache': pagination_valid}
            domains.append(result)
            if missing or any(status not in ('CONNECTED', 'ROOT') for status in roots.values()):
                issues.append({'kind': 'WORDNET_SCOPE_OR_ROOT_WITNESS_FAILED', 'domain': scope['domain'], 'missing': len(missing)})
        rules = [dict(r) for r in c.execute('SELECT * FROM unified_domain_rules')]
        for rule in rules:
            payload = json.loads(rule['payload'])
            entry = registry.get(payload['domain'])
            if not entry or entry['domain_id'] != rule['domain_id'] or rule['native_root_uid'] not in json.loads(entry['root_uids']):
                issues.append({'kind': 'ATTACHMENT_REGISTRY_MISMATCH', 'root_uid': rule['native_root_uid']})
        configurations = []
        furniture_path = inputs / 'abo_furniture_records.jsonl'
        if furniture_path.exists():
            for line in furniture_path.read_text().splitlines():
                row = json.loads(line)
                node = atlas.node(row['uid'])
                status = atlas.path_result(row['uid'])['status']
                native = c.execute('SELECT data FROM nodes WHERE uid=?', (row['uid'],)).fetchone()
                retained = bool(native and json.loads(native[0]).get('native_record') == row['proof']['native_record'])
                valid = bool(node and node['node_kind'] == 'CONFIGURATION' and status in ('CONNECTED', 'ROOT') and retained)
                configurations.append({'uid': row['uid'], 'status': status, 'native_payload_retained': retained, 'pass': valid})
                if not valid:
                    issues.append({'kind': 'FURNITURE_CONFIGURATION_FAILED', 'uid': row['uid']})
        result = {'status': 'PASS' if not issues else 'FAIL', 'database_revision': atlas._revision,
                  'protected_original_domains': len(manifest['prior_domains']),
                  'protected_aliases_checked': len(aliases), 'current_domains': len(registry),
                  'attachment_rules_checked': len(rules), 'new_domains': domains,
                  'furniture_configurations': configurations, 'aliases': aliases, 'issues': issues,
                  'scope_warning': 'This focused audit complements, and does not replace, whole-graph/cache/reward/nonfocus/public-download validation.'}
    write_json(output, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wordnet', type=Path, help='Also freeze full WordNet descendant cohorts for post-build auditing')
    parser.add_argument('--audit-inputs', type=Path, help='Audit a built candidate instead of preparing inputs')
    args = parser.parse_args()
    if args.audit_inputs:
        result = audit_living_candidate(args.database, args.audit_inputs, args.output)
        print(json.dumps({k: result[k] for k in ('status', 'current_domains', 'attachment_rules_checked', 'protected_original_domains', 'protected_aliases_checked')}), flush=True)
        if result['status'] != 'PASS':
            raise SystemExit(1)
    else:
        print(json.dumps(prepare(args.database, args.output)), flush=True)
        if args.wordnet:
            print(json.dumps(prepare_expected_wordnet_scope(args.wordnet, args.output / 'living_expected_wordnet_scope.json')), flush=True)
