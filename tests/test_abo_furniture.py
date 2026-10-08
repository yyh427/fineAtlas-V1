import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fineatlas.migration import Migration

SPEC = importlib.util.spec_from_file_location('prepare_abo_furniture', Path(__file__).resolve().parents[1] / 'scripts/prepare_abo_furniture.py')
ABO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ABO)


class FurnitureTrialTests(unittest.TestCase):
    def fixture(self, folder):
        folder = Path(folder)
        database = folder / 'trial.sqlite'
        with sqlite3.connect(database) as c:
            c.executescript('''
              CREATE TABLE nodes(uid TEXT UNIQUE NOT NULL,label TEXT,domain TEXT,domains TEXT,source TEXT,rank TEXT,description TEXT,data TEXT,layer TEXT,visibility TEXT NOT NULL DEFAULT 'ACTIVE',component_id INTEGER);
              CREATE TABLE components(id INTEGER PRIMARY KEY,wordnet_reachable INTEGER,depth INTEGER,parent_component_id INTEGER,witness_edge_id INTEGER);
              CREATE TABLE evidence(layer TEXT,evidence_id TEXT,source_name TEXT,source_uri TEXT,retrieved_utc TEXT,claim_type TEXT,payload TEXT,payload_sha256 TEXT,PRIMARY KEY(layer,evidence_id));
              CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT NOT NULL,domain TEXT NOT NULL,source_uri TEXT NOT NULL,evidence_id TEXT NOT NULL,attributes TEXT NOT NULL DEFAULT '{}');
              CREATE TABLE aliases(alias TEXT,uid TEXT,raw_alias TEXT,source TEXT,layer TEXT,data TEXT);
              CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT NOT NULL,object_uid TEXT NOT NULL,relation TEXT NOT NULL,status TEXT NOT NULL,source TEXT NOT NULL,evidence_id TEXT NOT NULL,data TEXT NOT NULL,UNIQUE(subject_uid,object_uid,relation,source));
              CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,relation TEXT,source TEXT,layer TEXT);
            ''')
            uid = ABO.REVIEWED[('amazon.com', 'B072ZLCB3M')][1]
            c.execute('INSERT INTO components(id) VALUES(1)')
            c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?)', (uid, 'table', 'furniture', '["furniture"]', 'wordnet', 'class', 'Physical furniture table', '{}', 'fixture', 'ACTIVE', 1))
        record = {'domain_name': 'amazon.com', 'item_id': 'B072ZLCB3M',
                  'item_name': [{'language_tag': 'en_US', 'value': 'Rivet Bristol Side Table, Walnut'}],
                  'product_type': [{'value': 'TABLE'}], 'model_number': [{'value': 'CT-355C'}],
                  'node': [{'node_id': 123, 'node_name': '/Furniture/Tables/End Tables'}],
                  'color': [{'language_tag': 'en_US', 'value': 'Walnut'}]}
        sample = folder / 'sample.json'
        sample.write_text(json.dumps([record, {'domain_name': 'amazon.co.uk', 'item_id': 'B07CTPR73M',
                                              'item_name': [{'language_tag': 'en_GB', 'value': 'Stone Brown Swatch'}],
                                              'product_type': [{'value': 'SOFA'}]}]))
        readme = folder / 'README.txt'
        readme.write_text('Attribution: Amazon.com; Matthieu Guillaumin')
        license = folder / 'LICENSE.txt'
        license.write_text('Creative Commons Attribution 4.0 International Public License')
        output = folder / 'inputs'
        ABO.prepare(database, sample, output, readme, license)
        return database, output, record, sample, readme, license

    def migration(self, database, inputs, folder):
        m = Migration(database, inputs, Path(folder) / 'reports')
        m.schema()
        return m

    def test_native_list_fields_preserved_and_swatch_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as folder:
            database, inputs, record, *_ = self.fixture(folder)
            rows = [json.loads(line) for line in (inputs / 'abo_furniture_records.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['proof']['native_record'], record)
            self.assertEqual(rows[0]['role'], 'CONFIGURATION')
            self.assertEqual(rows[0]['relation'], 'CONFIGURATION_TYPE_OF')
            self.assertTrue(rows[0]['proof']['not_global_model_identity'])
            reviews = json.loads((inputs / 'abo_furniture_reviews.json').read_text())
            self.assertEqual(reviews[0]['reason'], 'PRODUCT_TYPE_SAYS_SOFA_BUT_TITLE_IS_FABRIC_SWATCH')

    def test_real_migration_replay_preserves_payload_role_license_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            database, inputs, record, *_ = self.fixture(folder)
            m = self.migration(database, inputs, folder)
            self.assertEqual(ABO.apply_abo_inputs(m)['abo_new_source_uids'], 1)
            changes = m.c.execute('SELECT count(*) FROM usability_changes').fetchone()[0]
            self.assertEqual(ABO.apply_abo_inputs(m)['abo_new_source_uids'], 0)
            self.assertEqual(ABO.apply_abo_inputs(m)['status'], 'VERIFIED_NO_OP')
            self.assertEqual(m.c.execute('SELECT count(*) FROM usability_changes').fetchone()[0], changes)
            uid = ABO.listing_uid('amazon.com', 'B072ZLCB3M')
            actual = m.c.execute('SELECT n.data,p.node_kind FROM nodes n JOIN node_profiles p USING(uid) WHERE uid=?', (uid,)).fetchone()
            self.assertEqual(json.loads(actual['data'])['native_record'], record)
            self.assertEqual(actual['node_kind'], 'CONFIGURATION')
            self.assertEqual(m.c.execute('SELECT count(*) FROM entity_relations').fetchone()[0], 1)
            self.assertIn('CC BY 4.0', m.c.execute('SELECT license FROM source_catalogs').fetchone()[0])
            self.assertEqual(m.c.execute('SELECT count(*) FROM edges').fetchone()[0], 0)
            m.c.close()

    def test_replay_checks_connection_instead_of_blindly_skipping(self):
        with tempfile.TemporaryDirectory() as folder:
            database, inputs, *_ = self.fixture(folder)
            m = self.migration(database, inputs, folder)
            ABO.apply_abo_inputs(m)
            m.c.execute("UPDATE entity_relations SET status='REVIEW'")
            with self.assertRaisesRegex(ValueError, 'no longer matches'):
                ABO.apply_abo_inputs(m)
            m.c.close()

    def test_promoting_native_listing_to_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            database, inputs, *_ = self.fixture(folder)
            path = inputs / 'abo_furniture_records.jsonl'
            row = json.loads(path.read_text())
            row['role'] = 'MODEL'
            path.write_text(json.dumps(row) + '\n')
            m = self.migration(database, inputs, folder)
            with self.assertRaisesRegex(ValueError, 'global model or instance'):
                ABO.apply_abo_inputs(m)
            self.assertEqual(m.c.execute('SELECT count(*) FROM nodes').fetchone()[0], 1)
            m.c.close()

    def test_trial_budget_rejects_larger_sample(self):
        with tempfile.TemporaryDirectory() as folder:
            database, inputs, record, sample, readme, license = self.fixture(folder)
            sample.write_text(json.dumps([record] * 201))
            with self.assertRaisesRegex(ValueError, 'source-row budget'):
                ABO.prepare(database, sample, inputs, readme, license)


if __name__ == '__main__':
    unittest.main()
