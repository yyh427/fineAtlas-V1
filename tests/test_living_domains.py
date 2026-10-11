import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fineatlas.migration import Migration

SPEC = importlib.util.spec_from_file_location('prepare_living_domains', Path(__file__).resolve().parents[1] / 'scripts/prepare_living_domains.py')
LIVING = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LIVING)


class LivingPortalTests(unittest.TestCase):
    def fixture(self, folder):
        class Candidate:
            portals = Migration.portals

            def evidence(self, *args):
                return 'fixture-evidence'

            def change(self, *args):
                self.changes.append(args)

            def meta(self, key, value):
                self.c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', (key, json.dumps(value)))
        m = Candidate()
        m.inputs = Path(folder)
        m.changes = []
        m.c = sqlite3.connect(':memory:')
        m.c.row_factory = sqlite3.Row
        m.c.executescript('''
          CREATE TABLE nodes(uid TEXT PRIMARY KEY,component_id INTEGER,visibility TEXT,data TEXT,description TEXT);
          CREATE TABLE domain_entries(domain TEXT PRIMARY KEY,entry_uid TEXT,label TEXT,root_uid TEXT,root_uids TEXT,description TEXT);
          CREATE TABLE domain_entry_roots(domain TEXT,uid TEXT);
          CREATE TABLE domain_registry(domain_id INTEGER PRIMARY KEY,canonical_name TEXT,entry_uid TEXT,label TEXT,root_uids TEXT,description TEXT);
          CREATE TABLE domain_aliases(alias TEXT PRIMARY KEY,domain_id INTEGER,provenance TEXT);
          CREATE TABLE aliases(alias TEXT,uid TEXT);
          CREATE TABLE unified_domain_rules(domain_id INTEGER,native_root_uid TEXT,wordnet_anchor_uid TEXT,payload TEXT,PRIMARY KEY(domain_id,native_root_uid));
          CREATE TABLE unified_backbone_nodes(uid TEXT PRIMARY KEY,payload TEXT);
          CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
          CREATE TABLE dataset_targets(dataset TEXT,class_id TEXT,target_uid TEXT);
        ''')
        m.c.execute("INSERT INTO dataset_targets VALUES('task','1','food')")
        prior = []
        for did, name, uid in ((1, 'dishes', 'food'), (2, 'furniture', 'furn')):
            r = {'domain_id': did, 'canonical_name': name, 'entry_uid': 'fineatlas-domain:' + name,
                 'label': name, 'root_uids': json.dumps([uid]), 'description': name}
            prior.append(r)
            m.c.execute('INSERT INTO domain_registry VALUES(?,?,?,?,?,?)', tuple(r.values()))
            m.c.execute('INSERT INTO domain_entries VALUES(?,?,?,?,?,?)', (name, r['entry_uid'], name, uid, r['root_uids'], name))
            m.c.execute('INSERT INTO nodes VALUES(?,?,?,?,?)', (uid, did, 'ACTIVE', '{}', 'definition'))
            m.c.execute('INSERT INTO domain_aliases VALUES(?,?,?)', (name, did, '{}'))
            rule = {'domain': name, 'domain_id': did, 'native_root_uid': uid, 'wordnet_anchor_uid': uid}
            m.c.execute('INSERT INTO unified_domain_rules VALUES(?,?,?,?)', (did, uid, uid, json.dumps(rule)))
        m.c.execute("INSERT INTO domain_aliases VALUES('old custom alias',2,'{\"basis\":\"protected\"}')")
        aliases = [dict(r) for r in m.c.execute('SELECT a.*,r.canonical_name FROM domain_aliases a JOIN domain_registry r USING(domain_id)')]
        entries, rules, nodes = [], [], []
        for domain, label, roots, description in LIVING.DOMAINS:
            entries.append({'domain': domain, 'label': label, 'root_uids': list(roots), 'description': description,
                            'source_uri': 'https://wordnet.princeton.edu', 'proof': {'basis': 'fixture'}})
            for uid in roots:
                m.c.execute('INSERT INTO nodes VALUES(?,?,?,?,?)', (uid, len(nodes) + 10, 'ACTIVE', '{}', 'definition'))
                nodes.append({'uid': uid, 'definition': 'definition', 'native_record_sha256': hashlib.sha256(b'{}').hexdigest()})
                rules.append({'domain': domain, 'native_root_uid': uid, 'wordnet_anchor_uid': uid})
        (m.inputs / 'new_domains.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in entries))
        for filename, data in [('living_domain_rules.json', rules), ('living_backbone_nodes.json', nodes),
                               ('living_domains_manifest.json', {'prior_domains': prior, 'prior_aliases': aliases, 'new_domains': 4, 'new_root_rules': 9,
                                                                'prior_attachment_rule_keys': [json.loads(r[0]) for r in m.c.execute('SELECT payload FROM unified_domain_rules')]})]:
            (m.inputs / filename).write_text(json.dumps(data))
        return m

    def test_stable_domain_ids_preserve_rules_aliases_food_and_tasks(self):
        with tempfile.TemporaryDirectory() as folder:
            m = self.fixture(folder)
            result = LIVING.apply_living_inputs(m)
            self.assertEqual(result['total_attachment_rules'], 11)
            self.assertEqual(m.c.execute('SELECT count(*) FROM domain_registry').fetchone()[0], 6)
            for row in m.c.execute('SELECT * FROM unified_domain_rules'):
                actual = m.c.execute('SELECT canonical_name,root_uids FROM domain_registry WHERE domain_id=?', (row['domain_id'],)).fetchone()
                self.assertEqual(actual['canonical_name'], json.loads(row['payload'])['domain'])
                self.assertIn(row['native_root_uid'], json.loads(actual['root_uids']))
            furn = m.c.execute("SELECT domain_id FROM domain_registry WHERE canonical_name='furniture'").fetchone()[0]
            self.assertEqual(furn, 2)
            self.assertTrue(result['old_domain_ids_preserved'])
            self.assertEqual(result['old_attachment_rules_remapped'], 0)
            self.assertEqual(m.c.execute("SELECT domain_id FROM domain_aliases WHERE alias='old custom alias'").fetchone()[0], furn)
            self.assertEqual(json.loads(m.c.execute("SELECT root_uids FROM domain_registry WHERE canonical_name='dishes'").fetchone()[0]), ['food'])
            self.assertEqual(tuple(m.c.execute('SELECT * FROM dataset_targets').fetchone()), ('task', '1', 'food'))
            self.assertFalse(json.loads(m.c.execute("SELECT value FROM metadata WHERE key='browse_indexes_ready'").fetchone()[0]))
            changes = len(m.changes)
            self.assertEqual(LIVING.apply_living_inputs(m)['status'], 'VERIFIED_NO_OP')
            self.assertEqual(len(m.changes), changes)

    def test_additive_stage_keeps_the_original_application_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            m = self.fixture(folder)
            old = {'input_sha256': 'protected-history', 'summary': {'original': True}}
            m.meta('living_domains_application', old)
            with self.assertRaisesRegex(ValueError, 'already applied'):
                LIVING.apply_living_inputs(m)
            result=LIVING.apply_living_inputs(m, stage_key='living_coverage_extension_application')
            self.assertEqual(result['status'], 'APPLIED')
            actual=json.loads(m.c.execute("SELECT value FROM metadata WHERE key='living_domains_application'").fetchone()[0])
            self.assertEqual(actual, old)
            repeated=LIVING.apply_living_inputs(m, stage_key='living_coverage_extension_application')
            self.assertEqual(repeated['status'], 'VERIFIED_NO_OP')

    def test_historical_broader_raw_entry_does_not_replace_reviewed_registry_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            m = self.fixture(folder)
            # Actual earbuds counterexample: historical raw roots included named
            # designs, while the reviewed canonical registry kept its generic type.
            m.c.execute("INSERT INTO nodes VALUES('historical-design',99,'ACTIVE','{}','Named design')")
            m.c.execute("UPDATE domain_entries SET root_uids='[\"furn\",\"historical-design\"]' WHERE domain='furniture'")
            old_entries = [tuple(r) for r in m.c.execute('SELECT * FROM domain_entries ORDER BY domain')]
            old_registry = [tuple(r) for r in m.c.execute('SELECT * FROM domain_registry ORDER BY domain_id')]
            old_aliases = [tuple(r) for r in m.c.execute('SELECT * FROM domain_aliases ORDER BY alias')]
            LIVING.apply_living_inputs(m)
            self.assertEqual([tuple(r) for r in m.c.execute('SELECT * FROM domain_registry WHERE domain_id<=2 ORDER BY domain_id')], old_registry)
            for before in old_entries:
                self.assertEqual(tuple(m.c.execute('SELECT * FROM domain_entries WHERE domain=?', (before[0],)).fetchone()), before)
            for before in old_aliases:
                self.assertEqual(tuple(m.c.execute('SELECT * FROM domain_aliases WHERE alias=?', (before[0],)).fetchone()), before)
            self.assertEqual(json.loads(m.c.execute("SELECT root_uids FROM domain_registry WHERE canonical_name='furniture'").fetchone()[0]), ['furn'])

    def test_default_portal_reconstruction_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            m = self.fixture(folder)
            m.c.execute("INSERT INTO nodes VALUES('historical-design',99,'ACTIVE','{}','Named design')")
            m.c.execute("UPDATE domain_entries SET root_uids='[\"furn\",\"historical-design\"]' WHERE domain='furniture'")
            m.portals()
            self.assertEqual(set(json.loads(m.c.execute("SELECT root_uids FROM domain_registry WHERE canonical_name='furniture'").fetchone()[0])), {'furn', 'historical-design'})

    def test_additive_portals_reject_duplicate_root_group_without_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            m = self.fixture(folder)
            path = m.inputs / 'new_domains.jsonl'
            entries = [json.loads(line) for line in path.read_text().splitlines()]
            m.c.execute("INSERT INTO nodes VALUES('native-furn-alias',2,'ACTIVE','{}','Same furniture identity')")
            entries.append({'domain': 'duplicate-furniture', 'label': 'Duplicate furniture', 'root_uids': ['native-furn-alias'],
                            'description': 'Duplicate scope', 'source_uri': 'https://example.org', 'proof': {'basis': 'review'}})
            path.write_text(''.join(json.dumps(r) + '\n' for r in entries))
            with self.assertRaisesRegex(ValueError, 'duplicates a complete existing root'):
                m.portals(preserve_registry=True)
            self.assertEqual(m.c.execute('SELECT count(*) FROM domain_registry').fetchone()[0], 2)

    def test_additive_portals_reject_protected_alias_collision(self):
        with tempfile.TemporaryDirectory() as folder:
            m = self.fixture(folder)
            path = m.inputs / 'new_domains.jsonl'
            entries = [json.loads(line) for line in path.read_text().splitlines()]
            entries[0]['domain'] = 'old custom alias'
            path.write_text(''.join(json.dumps(r) + '\n' for r in entries))
            with self.assertRaisesRegex(ValueError, 'conflicts with a protected alias'):
                m.portals(preserve_registry=True)
            self.assertEqual(m.c.execute('SELECT count(*) FROM domain_registry').fetchone()[0], 2)
            self.assertEqual(m.c.execute('SELECT count(*) FROM domain_entries').fetchone()[0], 2)
            self.assertEqual(m.c.execute('SELECT count(*) FROM domain_entries').fetchone()[0], 2)
            self.assertEqual(m.changes, [])

    def test_additive_portals_reject_canonical_scope_conflict_before_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            m = self.fixture(folder)
            path = m.inputs / 'new_domains.jsonl'
            entries = [json.loads(line) for line in path.read_text().splitlines()]
            entries.append({'domain': 'furniture', 'label': 'Furniture', 'root_uids': ['food'],
                            'description': 'Wrong scope', 'source_uri': 'https://example.org', 'proof': {'basis': 'review'}})
            path.write_text(''.join(json.dumps(r) + '\n' for r in entries))
            with self.assertRaisesRegex(ValueError, 'different protected scope'):
                m.portals(preserve_registry=True)
            self.assertEqual(m.c.execute('SELECT count(*) FROM domain_registry').fetchone()[0], 2)

    def test_altered_frozen_inputs_do_not_reapply_an_existing_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            m = self.fixture(folder)
            LIVING.apply_living_inputs(m)
            path = m.inputs / 'living_domain_rules.json'
            path.write_text(path.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'inputs differ'):
                LIVING.apply_living_inputs(m)

    def test_no_op_still_checks_existing_semantic_state(self):
        with tempfile.TemporaryDirectory() as folder:
            m = self.fixture(folder)
            LIVING.apply_living_inputs(m)
            m.c.execute("DELETE FROM domain_aliases WHERE alias='old custom alias'")
            with self.assertRaisesRegex(ValueError, 'lost a protected'):
                LIVING.apply_living_inputs(m)

    def test_wrong_native_definition_is_rejected_before_portal_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            m = self.fixture(folder)
            m.c.execute('UPDATE nodes SET description=? WHERE uid=?', ('changed', LIVING.DOMAINS[0][2][0]))
            with self.assertRaisesRegex(ValueError, 'Frozen living synset changed'):
                LIVING.apply_living_inputs(m)
            self.assertEqual(m.c.execute('SELECT count(*) FROM domain_registry').fetchone()[0], 2)

    def test_stale_rule_registry_assignment_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            m = self.fixture(folder)
            m.c.execute('UPDATE unified_domain_rules SET domain_id=99 WHERE domain_id=2')
            with self.assertRaisesRegex(ValueError, 'does not match registry'):
                LIVING.apply_living_inputs(m)


if __name__ == '__main__':
    unittest.main()
