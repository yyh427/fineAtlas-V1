"""Independent source field and relation-boundary controls; no builder imports."""
import importlib.util
from pathlib import Path
import sqlite3
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/audit_nominal_design_scope_repairs.py'
SPEC = importlib.util.spec_from_file_location('independent_nominal_scope_auditor', SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class IndependentNominalScopeControls(unittest.TestCase):
    def test_family_membership_and_role_are_distinct(self):
        self.assertTrue(AUDIT.allowed('NATIVE_DESIGN_PARENT', 'MODEL', 'MODEL_FAMILY'))
        self.assertTrue(AUDIT.allowed('DESIGN_TYPE_OF', 'MODEL_FAMILY', 'CLASS'))
        self.assertFalse(AUDIT.allowed('IS_A', 'MODEL_FAMILY', 'CLASS'))
        self.assertFalse(AUDIT.allowed('NATIVE_DESIGN_PARENT', 'INSTANCE', 'MODEL_FAMILY'))
        self.assertFalse(AUDIT.allowed('SOURCE_MODEL_REFERENCE', 'MODEL', 'MODEL_FAMILY'))

    def test_complete_source_range_does_not_drop_mixed_purpose_qualification(self):
        node = {'data': AUDIT.dump({'description': 'Business jet family', 'evidence_record': {
            'wikipedia_intro': 'Civil executive jets; a separate cargo design was derived later.'}})}
        self.assertEqual(AUDIT.complete_fields(node), {
            ('description', 'Business jet family'),
            ('wikipedia_intro', 'Civil executive jets; a separate cargo design was derived later.')})

    def test_equal_aliases_do_not_hide_distinct_source_values(self):
        data = {'description': 'Family', 'evidence_record': {'description': 'Family'}}
        self.assertEqual(AUDIT.complete_fields({'data': AUDIT.dump(data)}), {('description', 'Family')})
        data['evidence_record']['description'] = 'One member of a family'
        self.assertEqual(len(AUDIT.complete_fields({'data': AUDIT.dump(data)})), 2)

    def test_source_witness_is_complete_actual_field_not_cherry_picked_span(self):
        con = sqlite3.connect(':memory:'); con.row_factory = sqlite3.Row
        con.execute('CREATE TABLE nodes(uid TEXT PRIMARY KEY,data TEXT)')
        raw = AUDIT.dump({'definition': 'A fixed-wing jet aircraft; rotors are outside this scope.'})
        con.execute('INSERT INTO nodes VALUES (?,?)', ('own', raw))
        witness = {'uid': 'own', 'data_sha256': AUDIT.sha(raw), 'field_path': 'definition', 'statement': 'A fixed-wing jet aircraft'}
        with self.assertRaisesRegex(ValueError, 'complete original field'):
            AUDIT.check_witness(con, witness)
        witness['statement'] = 'A fixed-wing jet aircraft; rotors are outside this scope.'
        self.assertEqual(AUDIT.check_witness(con, witness)['uid'], 'own')
        witness['data_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            AUDIT.check_witness(con, witness)
        con.close()

    def test_unsafe_source_locator_and_table_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'safe portable'):
            AUDIT.read_input(Path('/tmp'), '../source.json')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            AUDIT.row_at(None, 'sqlite_master', 'source')

    def test_root_navigation_respects_actual_view_admission_and_relation_status(self):
        con = sqlite3.connect(':memory:'); con.row_factory = sqlite3.Row
        con.executescript('CREATE TABLE nodes(uid TEXT PRIMARY KEY,rank TEXT,component_id INTEGER,visibility TEXT);'
                          'CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,attributes TEXT);'
                          'CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,relation TEXT,status TEXT);'
                          'CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,relation TEXT,status TEXT);')
        con.executemany('INSERT INTO nodes VALUES (?,?,?,?)', [('source', 'class', 1, 'ACTIVE'), ('root', 'class', 2, 'ACTIVE')])
        con.executemany('INSERT INTO node_profiles VALUES (?,?,?)', [('source', 'CLASS', '{}'), ('root', 'CLASS', '{}')])
        con.execute("INSERT INTO edges VALUES (1,'source','root','IS_A','TYPED_ACTIVE')")
        self.assertFalse(AUDIT.reaches(con, 'source', 'root'))
        con.execute("UPDATE edges SET status='ACTIVE'")
        self.assertTrue(AUDIT.reaches(con, 'source', 'root'))
        con.execute('UPDATE node_profiles SET attributes=? WHERE uid=?', (AUDIT.dump({'allowed_views': []}), 'root'))
        self.assertFalse(AUDIT.reaches(con, 'source', 'root'))
        con.execute('UPDATE node_profiles SET attributes=? WHERE uid=?', (AUDIT.dump({'allowed_views': ['taxonomy']}), 'root'))
        self.assertTrue(AUDIT.reaches(con, 'source', 'root'))
        con.execute("UPDATE node_profiles SET node_kind='UNKNOWN' WHERE uid='root'")
        self.assertFalse(AUDIT.reaches(con, 'source', 'root'))
        con.close()

    def test_component_bucket_without_real_identity_bridge_cannot_supply_source_scope(self):
        con = sqlite3.connect(':memory:'); con.row_factory = sqlite3.Row
        con.executescript('CREATE TABLE nodes(uid TEXT PRIMARY KEY,rank TEXT,component_id INTEGER,visibility TEXT);'
                          'CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,attributes TEXT);'
                          'CREATE TABLE bridges(id INTEGER PRIMARY KEY,left_uid TEXT,right_uid TEXT,relation TEXT,status TEXT);')
        con.executemany('INSERT INTO nodes VALUES (?,?,?,?)', [('own', 'model', 1, 'ACTIVE'), ('other', 'model', 1, 'ACTIVE')])
        con.executemany('INSERT INTO node_profiles VALUES (?,?,?)', [('own', 'MODEL', '{}'), ('other', 'MODEL', '{}')])
        own = AUDIT.row_at(con, 'nodes', 'own'); other = AUDIT.row_at(con, 'nodes', 'other')
        self.assertFalse(AUDIT.witnessed_peer(con, own, other))
        con.execute("INSERT INTO bridges VALUES (1,'own','other','SAME_CONCEPT','ACTIVE')")
        self.assertTrue(AUDIT.witnessed_peer(con, own, other))
        con.execute("UPDATE node_profiles SET node_kind='MODEL_FAMILY' WHERE uid='other'")
        self.assertFalse(AUDIT.witnessed_peer(con, own, other))
        con.close()

    def test_source_content_hash_and_exact_status_are_separate(self):
        original = {'id': 1, 'status': 'SOURCE_SCOPE_REVIEW', 'reason': 'historic', 'data': 'whole original fact'}
        reviewed = {**original, 'id': 9, 'status': 'ACTIVE', 'reason': 'later'}
        self.assertEqual(AUDIT.assertion_sha(original), AUDIT.assertion_sha(reviewed))
        changed = {**original, 'data': 'different scope'}
        self.assertNotEqual(AUDIT.assertion_sha(original), AUDIT.assertion_sha(changed))
        self.assertNotEqual(original, reviewed)


if __name__ == '__main__':
    unittest.main()
