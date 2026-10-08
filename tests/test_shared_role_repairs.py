"""Shared source-scope repairs reject invented grain and survive independent IDs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fineatlas.hierarchy import (apply_refinements, locate_source_assertion,
                                 source_assertion_sha256)
from fineatlas.migration import Migration

spec = importlib.util.spec_from_file_location(
    'prepare_shared_role_repairs', Path(__file__).resolve().parents[1] / 'scripts/prepare_shared_role_repairs.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class SharedRoleRepairsTest(unittest.TestCase):
    def database(self):
        c = sqlite3.connect(':memory:')
        c.row_factory = sqlite3.Row
        c.executescript('''
            CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,description TEXT,data TEXT,
              source TEXT,rank TEXT,visibility TEXT,component_id INTEGER);
            CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT);
            CREATE TABLE edges(child_uid TEXT,parent_uid TEXT,relation TEXT,source TEXT,layer TEXT);
            CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,
              relation TEXT,status TEXT,source TEXT,evidence_id TEXT,data TEXT);
            CREATE TABLE bridges(id INTEGER PRIMARY KEY,left_uid TEXT,right_uid TEXT,relation TEXT,
              confidence REAL,source TEXT,layer TEXT,data TEXT,status TEXT,reason TEXT);
            CREATE TABLE components(id INTEGER PRIMARY KEY,depth INTEGER,wordnet_reachable INTEGER);
            CREATE TABLE evidence(evidence_id TEXT,payload TEXT,payload_sha256 TEXT,source_uri TEXT);
            CREATE TABLE source_catalogs(source TEXT PRIMARY KEY,uri TEXT,license TEXT,sha256 TEXT,coverage TEXT);
        ''')
        return c

    def add_node(self, c, uid, label, definition, role, component, source='wikidata'):
        payload = json.dumps({'definition': definition})
        c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?)',
                  (uid, label, definition, payload, source, role.lower(), 'ACTIVE', component))
        c.execute('INSERT INTO node_profiles VALUES(?,?)', (uid, role))
        c.execute('INSERT OR IGNORE INTO components VALUES(?,NULL,0)', (component,))
        return prepare.node(c, uid)

    def generic_review(self, c):
        n = self.add_node(c, 'wikidata:Q1', 'basket', 'A basket is a container that holds things.', 'MODEL_FAMILY', 1)
        p = self.add_node(c, 'wordnet31:parent', 'container', 'An object that holds things.', 'CLASS', 2)
        return {'uid': n['uid'], 'members': [{'uid': n['uid'], 'role': n['role'],
                 'native_record_sha256': prepare.digest(n['data'])}],
                'definition': n['description'], 'definition_head': 'container',
                'semantic_scope': 'GENERIC_PHYSICAL_KIND', 'scope_observation': 'Generic containers across makers.',
                'uri': 'https://example.org/basket', 'license': 'Retained attribution',
                'parents': [{'uid': p['uid'], 'native_record_sha256': prepare.digest(p['data']),
                             'definition': p['description'], 'entailment_observation': 'Basket holds things.'}]}

    def test_generic_definition_repairs_role_without_changing_source_payload(self):
        c = self.database()
        review = self.generic_review(c)
        before = list(c.execute('SELECT uid,data FROM nodes'))
        rows = prepare.generic_kind_operations(c, review, Path('/tmp'))
        self.assertEqual([(r['op'], r.get('role', r.get('relation'))) for r in rows],
                         [('role', 'CLASS'), ('link', 'IS_A')])
        self.assertEqual([tuple(x) for x in c.execute('SELECT uid,data FROM nodes')], [tuple(x) for x in before])

    def test_generic_decision_does_not_spread_to_an_identity_peer_of_another_source(self):
        c = self.database()
        review = self.generic_review(c)
        other = self.add_node(c, 'manufacturer:Basket-17', 'Basket 17', 'A branded basket model.', 'MODEL', 1, 'manufacturer')
        review['members'].append({'uid': other['uid'], 'role': other['role'],
                                  'native_record_sha256': prepare.digest(other['data'])})
        with self.assertRaisesRegex(ValueError, 'different source identifier'):
            prepare.generic_kind_operations(c, review, Path('/tmp'))

    def test_generic_label_or_instance_evidence_cannot_erase_source_grain(self):
        for change in ('named', 'instance', 'payload', 'membership'):
            with self.subTest(change=change):
                c = self.database()
                review = self.generic_review(c)
                if change == 'named':
                    c.execute("UPDATE nodes SET label='Brand Basket X1' WHERE uid='wikidata:Q1'")
                elif change == 'instance':
                    c.execute("UPDATE node_profiles SET node_kind='INSTANCE' WHERE uid='wikidata:Q1'")
                    review['members'][0]['role'] = 'INSTANCE'
                elif change == 'payload':
                    c.execute("UPDATE nodes SET data='{}' WHERE uid='wikidata:Q1'")
                else:
                    self.add_node(c, 'wikidata-v4:Q1', 'basket', 'Generic basket.', 'MODEL', 1)
                with self.assertRaises(ValueError):
                    prepare.generic_kind_operations(c, review, Path('/tmp'))

    def test_source_only_parent_is_not_silently_activated(self):
        c = self.database()
        review = self.generic_review(c)
        c.execute("UPDATE nodes SET visibility='SOURCE_ONLY' WHERE uid='wordnet31:parent'")
        with self.assertRaisesRegex(ValueError, 'visibility'):
            prepare.generic_kind_operations(c, review, Path('/tmp'))

    def test_incident_configuration_relation_requires_separate_scope_review(self):
        c = self.database()
        review = self.generic_review(c)
        self.add_node(c, 'config', 'Configuration A', 'Reusable configuration.', 'CONFIGURATION', 3)
        c.execute("INSERT INTO entity_relations VALUES(4,'config','wikidata:Q1','CONFIGURATION_OF','ACTIVE','source','e','{}')")
        with self.assertRaisesRegex(ValueError, 'Incoming typed relation'):
            prepare.generic_kind_operations(c, review, Path('/tmp'))

    def test_source_locator_ignores_surrogate_id_but_checks_every_source_field(self):
        c = self.database()
        c.execute("INSERT INTO entity_relations VALUES(91,'a','b','DESIGN_TYPE_OF','ACTIVE','native','e','{\"scope\":1}')")
        row = c.execute('SELECT * FROM entity_relations').fetchone()
        locator = prepare.assertion_locator(row, 'entity_relations')
        c.execute('UPDATE entity_relations SET id=107')
        self.assertEqual(locate_source_assertion(c, 'entity_relations', locator)['id'], 107)
        c.execute("UPDATE entity_relations SET status='HIERARCHY_SUPERSEDED'")
        self.assertEqual(locate_source_assertion(c, 'entity_relations', locator)['status'], 'HIERARCHY_SUPERSEDED')
        c.execute("UPDATE entity_relations SET data='{\"scope\":2}'")
        with self.assertRaises(ValueError):
            locate_source_assertion(c, 'entity_relations', locator)

    def test_ambiguous_duplicate_source_assertions_are_not_arbitrarily_selected(self):
        c = self.database()
        c.execute("INSERT INTO entity_relations VALUES(1,'a','b','DESIGN_TYPE_OF','ACTIVE','native','e','{}')")
        locator = prepare.assertion_locator(c.execute('SELECT * FROM entity_relations').fetchone(), 'entity_relations')
        c.execute("INSERT INTO entity_relations VALUES(2,'a','b','DESIGN_TYPE_OF','ACTIVE','native','e','{}')")
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            locate_source_assertion(c, 'entity_relations', locator)

    def test_replay_preserves_original_source_payloads_and_is_split_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            c = self.database()
            for uid, role in [('epa-model:a', 'MODEL_FAMILY'), ('wikidata:Q1', 'MODEL'), ('wikidata-v4:Q1', 'MODEL')]:
                self.add_node(c, uid, uid, 'Source scope.', role, 1)
            self.add_node(c, 'generic', 'Generic', 'Physical kind.', 'CLASS', 2)
            c.execute("INSERT INTO bridges VALUES(700,'epa-model:a','wikidata:Q1','SAME_CONCEPT',0.99,'epa','original','{\"original\":true}','ACTIVE',NULL)")
            c.execute("INSERT INTO bridges VALUES(701,'wikidata:Q1','wikidata-v4:Q1','SAME_CONCEPT',1,'same-qid','original','{}','ACTIVE',NULL)")
            c.execute("INSERT INTO entity_relations VALUES(810,'wikidata:Q1','generic','DESIGN_TYPE_OF','ACTIVE','derived','e','{\"retained\":true}')")
            bridge = c.execute('SELECT * FROM bridges WHERE id=700').fetchone()
            typed = c.execute('SELECT * FROM entity_relations').fetchone()
            records = [
                {'op': 'split_identity_source', 'uid': 'epa-model:a', 'parent': 'wikidata:Q1',
                 'locator': prepare.assertion_locator(bridge, 'bridges'), 'source': 'Scope review',
                 'uri': 'https://example.org/scope', 'proof': {'basis': 'DIFFERENT_GENERATION_SCOPE'}},
                {'op': 'withdraw_typed_source', 'uid': 'wikidata:Q1',
                 'locator': prepare.assertion_locator(typed, 'entity_relations'), 'source': 'Scope review',
                 'uri': 'https://example.org/scope', 'proof': {'basis': 'INCOMPATIBLE_ROLE_SOURCE'}}]
            # Independent replay assigns different IDs before applying the
            # exact same frozen source queue.
            c.execute('UPDATE bridges SET id=1777 WHERE id=700')
            c.execute('UPDATE entity_relations SET id=1888 WHERE id=810')
            m = Migration.__new__(Migration)
            m.c = c
            m.inputs = Path(folder)
            (m.inputs / 'shared_role_repairs.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in records))
            m.evidence = lambda *args: 'scope-evidence'
            changes = []
            m.change = lambda *args: changes.append(args)
            meta = {}
            m.meta = lambda k, v: meta.update({k: v})
            first = apply_refinements(m, 'shared_role_repairs.jsonl')
            self.assertEqual(first['identity_groups_split'], 1)
            parts = list(c.execute('SELECT uid,component_id FROM nodes ORDER BY uid'))
            self.assertNotEqual(dict(parts)['epa-model:a'], dict(parts)['wikidata:Q1'])
            self.assertEqual(dict(parts)['wikidata:Q1'], dict(parts)['wikidata-v4:Q1'])
            count = c.execute('SELECT count(*) FROM components').fetchone()[0]
            source_payloads = [tuple(r) for r in c.execute('SELECT uid,data FROM nodes ORDER BY uid')]
            second = apply_refinements(m, 'shared_role_repairs.jsonl')
            self.assertEqual(second['identity_source_splits_already_applied'], 1)
            self.assertEqual(c.execute('SELECT count(*) FROM components').fetchone()[0], count)
            self.assertEqual([tuple(x) for x in c.execute('SELECT uid,component_id FROM nodes ORDER BY uid')], [tuple(x) for x in parts])
            self.assertEqual([tuple(x) for x in c.execute('SELECT uid,data FROM nodes ORDER BY uid')], source_payloads)
            self.assertEqual(len(changes), 2)
            self.assertEqual(c.execute('SELECT data FROM bridges WHERE id=1777').fetchone()[0], bridge['data'])
            self.assertEqual(c.execute('SELECT data FROM entity_relations WHERE id=1888').fetchone()[0], typed['data'])

    def test_native_aggregation_witness_checks_raw_fields_not_only_evidence_title(self):
        c = self.database()
        raw = json.dumps({'year': 2012, 'make': 'Honda', 'model': 'Accord Coupe', 'baseModel': 'Accord'})
        self.add_node(c, 'epa:1', 'Car config', '', 'CONFIGURATION', 1, 'epa')
        c.execute('UPDATE nodes SET data=? WHERE uid=?', (raw, 'epa:1'))
        c.execute("INSERT INTO entity_relations VALUES(8,'epa:1','family','CONFIGURATION_OF','ACTIVE','EPA','e','{}')")
        c.execute('INSERT INTO evidence VALUES(?,?,?,?)', ('e', raw, prepare.digest(raw), 'https://fueleconomy.gov/1'))
        w = {'locator': prepare.assertion_locator(c.execute('SELECT * FROM entity_relations').fetchone(), 'entity_relations'),
             'native_record_sha256': prepare.digest(raw), 'evidence_sha256': prepare.digest(raw)}
        self.assertEqual(prepare.checked_native_witness(c, w)[0]['baseModel'], 'Accord')
        changed = raw.replace('Accord Coupe', 'Different design')
        c.execute('UPDATE nodes SET data=? WHERE uid=?', (changed, 'epa:1'))
        w['native_record_sha256'] = prepare.digest(changed)
        with self.assertRaisesRegex(ValueError, 'retained native fields'):
            prepare.checked_native_witness(c, w)


if __name__ == '__main__':
    unittest.main()
