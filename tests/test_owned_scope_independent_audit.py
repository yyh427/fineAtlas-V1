"""Independent SQL/source checks fail on same-name and local-file shortcuts."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_owned_scope_repairs as audit


class IndependentOwnedSourceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.con = sqlite3.connect(':memory:')
        self.con.row_factory = sqlite3.Row
        self.con.executescript('''
          CREATE TABLE nodes(uid TEXT, data TEXT, rank TEXT, component_id INTEGER,
                             visibility TEXT, label TEXT);
          CREATE TABLE node_profiles(uid TEXT,node_kind TEXT);
          CREATE TABLE bridges(id INTEGER,left_uid TEXT,right_uid TEXT,relation TEXT,status TEXT);
          CREATE TABLE edges(id INTEGER,data TEXT);
        ''')
        for uid in ('design-a', 'source-a'):
            self.con.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?)',
                             (uid, '{}', 'model', 1, 'ACTIVE', 'Shared name'))
            self.con.execute('INSERT INTO node_profiles VALUES(?,?)', (uid, 'MODEL'))

    def tearDown(self):
        self.con.close()
        self.temp.cleanup()

    def test_shared_component_and_name_do_not_prove_owned_source_identity(self):
        self.assertFalse(audit.identity_peer(self.con, 'design-a', 'source-a'))

    def test_abbreviated_design_name_does_not_truncate_real_type_assertion(self):
        statement = 'The G.A.C. 102 Aristocrat is a cabin monoplane built in the US.'
        self.assertEqual(audit.own_assertion_phrase(statement), 'a cabin monoplane')
        self.assertNotIn('glider', audit.own_assertion_phrase(
            'The Prototype is an aircraft derived from a glider.'))

    def test_retired_identity_claim_cannot_supply_an_own_source_witness(self):
        self.con.execute("INSERT INTO bridges VALUES(1,'design-a','source-a','SAME_CONCEPT','SOURCE_SCOPE_REVIEW')")
        self.assertFalse(audit.identity_peer(self.con, 'design-a', 'source-a'))

    def test_active_identity_peer_preserves_own_role_scope(self):
        self.con.execute("INSERT INTO bridges VALUES(1,'design-a','source-a','SAME_CONCEPT','ACTIVE')")
        self.assertTrue(audit.identity_peer(self.con, 'design-a', 'source-a'))
        self.con.execute("UPDATE node_profiles SET node_kind='MODEL_FAMILY' WHERE uid='source-a'")
        self.assertFalse(audit.identity_peer(self.con, 'design-a', 'source-a'))

    def test_retained_definition_field_is_checked_in_original_source_bytes(self):
        raw = json.dumps({'admission_basis': {'source_statement': 'A car is a motor vehicle with wheels.'}})
        self.con.execute('INSERT INTO edges VALUES(1,?)', (raw,))
        witness = {'table': 'edges', 'id': 1, 'field': 'admission_basis.source_statement',
                   'statement': 'A car is a motor vehicle with wheels.', 'data_sha256': audit.sha(raw)}
        self.assertEqual(audit.source_witness(self.con, witness)['data'], raw)
        self.con.execute('UPDATE edges SET data=?', (raw.replace('motor vehicle', 'four-wheel car'),))
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            audit.source_witness(self.con, witness)

    def test_historical_absolute_primary_path_is_not_a_download_locator(self):
        path = self.root / 'unpublished.pdf'
        path.write_bytes(b'official source fixture')
        operations = [{'proof': {'document': {'source_kind': 'PRIMARY_MANUFACTURER_OR_REGULATOR',
                       'source_uri': 'https://manufacturer.example/spec.pdf',
                       'sha256': audit.sha(path.read_bytes()), 'local_snapshot_path': str(path)}}}]
        with self.assertRaisesRegex(ValueError, 'Explicit portable'):
            audit.verify_primary_sources(self.root, operations, None)
        with self.assertRaisesRegex(ValueError, 'portable byte locator'):
            audit.verify_primary_sources(self.root, operations, self.root)

    def test_explicit_primary_registry_requires_complete_matching_bytes(self):
        path = self.root / 'spec.pdf'; path.write_bytes(b'complete original source')
        doc = {'source_uri': 'https://manufacturer.example/spec.pdf', 'sha256': audit.sha(path.read_bytes()),
               'filename': 'spec.pdf', 'hash_basis': 'HTTP_RESPONSE_BODY_BYTES'}
        (self.root / 'structure_primary_source_snapshots.json').write_text(json.dumps({
            'schema': 'FINEATLAS_PORTABLE_PRIMARY_SOURCE_SNAPSHOTS_V1', 'documents': {'spec': doc}}))
        ops = [{'proof': {'document': {**doc, 'source_kind': 'PRIMARY_MANUFACTURER_OR_REGULATOR'}}}]
        self.assertEqual(set(audit.verify_primary_sources(self.root, ops, self.root)), {'spec.pdf'})
        path.write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            audit.verify_primary_sources(self.root, ops, self.root)

    def test_primary_registry_cannot_escape_explicit_source_directory(self):
        doc = {'source_uri': 'https://manufacturer.example/spec.pdf', 'sha256': '0' * 64,
               'filename': '../external.pdf', 'hash_basis': 'HTTP_RESPONSE_BODY_BYTES'}
        (self.root / 'structure_primary_source_snapshots.json').write_text(json.dumps({
            'schema': 'FINEATLAS_PORTABLE_PRIMARY_SOURCE_SNAPSHOTS_V1', 'documents': {'spec': doc}}))
        ops = [{'proof': {'document': {**doc, 'source_kind': 'PRIMARY_MANUFACTURER_OR_REGULATOR'}}}]
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            audit.verify_primary_sources(self.root, ops, self.root)

    def test_full_annotation_join_is_distinct_from_approved_subset(self):
        files = []
        for split, beginning, end in (('train', 0, 34), ('val', 34, 67), ('test', 67, 100)):
            for field in ('variant', 'family', 'manufacturer'):
                lines = []
                for variant in range(100):
                    for index in range(beginning, end):
                        value = 'Model ' + str(variant) if field == 'variant' else 'Common ' + field
                        lines.append(str(variant * 100 + index).zfill(7) + ' ' + value)
                raw = ('\n'.join(lines) + '\n').encode()
                name = 'images_' + field + '_' + split + '.txt'
                (self.root / name).write_bytes(raw)
                files.append({'file': name, 'sha256': audit.sha(raw), 'bytes': len(raw)})
        manifest = {'author_annotation_files': files}
        records = audit.author_annotations(self.root, manifest)
        self.assertEqual(len(records), 10000)
        self.assertEqual(sum(r['variant'] == 'Model 42' for r in records), 100)
        (self.root / files[0]['file']).write_bytes(b'approved subset only\n')
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            audit.author_annotations(self.root, manifest)


if __name__ == '__main__':
    unittest.main()
