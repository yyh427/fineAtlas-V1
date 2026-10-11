"""Modern proof envelopes must bind exact reviewed rows, never marker strings."""
import json
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from structure_library_review_evidence import ReviewedLibraryEvidence


class ModernLibraryProofTest(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.con.row_factory = sqlite3.Row
        self.con.executescript('''
          CREATE TABLE node_profiles(uid TEXT,node_kind TEXT,evidence_id TEXT);
          CREATE TABLE normalization_roles(uid TEXT,canonical_role TEXT,status TEXT,evidence_id TEXT);
          CREATE TABLE evidence(evidence_id TEXT,payload TEXT);
          CREATE TABLE edges(id INTEGER,child_uid TEXT,parent_uid TEXT,relation TEXT,status TEXT,source TEXT);
          CREATE TABLE usability_changes(id INTEGER PRIMARY KEY,stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT);
        ''')
        self.helper = ReviewedLibraryEvidence.__new__(ReviewedLibraryEvidence)
        self.proof = {'kind': 'SOURCE_REVIEWED_WHOLE_NOMINAL_DESIGN_SCOPE', 'whole_subject_scope_review': True}
        self.profile = {'uid': 'source:child', 'node_kind': 'MODEL', 'evidence_id': 'evidence:role'}
        self.norm = {'uid': 'source:child', 'canonical_role': 'MODEL', 'status': 'VERIFIED', 'evidence_id': 'evidence:role'}
        self.con.execute('INSERT INTO node_profiles VALUES(?,?,?)', tuple(self.profile.values()))
        self.con.execute('INSERT INTO normalization_roles VALUES(?,?,?,?)', tuple(self.norm.values()))
        self.con.execute('INSERT INTO evidence VALUES(?,?)', ('evidence:role', json.dumps(self.proof)))
        self.role_op = {'before_profile': {'uid': 'source:child', 'node_kind': 'CLASS'},
                        'after_profile': self.profile, 'after_normalization_role': self.norm, 'proof': self.proof}
        self.helper.roles = {'source:child': self.role_op}
        self.before = {'id': 17, 'child_uid': 'source:child', 'parent_uid': 'source:parent',
                       'relation': 'IS_A', 'status': 'ACTIVE', 'source': 'retained evidence'}
        self.con.execute('INSERT INTO edges VALUES(?,?,?,?,?,?)', tuple(({**self.before, 'status': 'SOURCE_SCOPE_REVIEW'}).values()))
        self.class_op = {'table': 'edges', 'after_status': 'SOURCE_SCOPE_REVIEW',
                         'before_assertion': self.before, 'proof': self.proof}
        self.helper.class_reviews = {('edges', 17): self.class_op}
        self.con.execute('INSERT INTO usability_changes(stage,object_type,object_id,before_json,after_json,evidence) VALUES(?,?,?,?,?,?)',
                         ('nominal_design_scope_repairs', 'class_scope_review', '17', json.dumps(self.before),
                          json.dumps({'status': 'SOURCE_SCOPE_REVIEW'}), json.dumps(self.proof)))
        self.path = {'path': [{'uid': 'source:child', 'parent_uid': 'source:parent',
                              'edge': {'id': 17, 'relation': 'IS_A'}}]}

    def tearDown(self):
        self.con.close()

    def role(self):
        return self.helper.role_evidence(self.con, 'source:child', 'CLASS', 'MODEL', lambda *args: None)

    def withdrawal(self):
        return self.helper.withdrawal_evidence(self.con, self.path, lambda *args, **kwargs: [])

    def test_exact_reviewed_role_schema_is_accepted(self):
        self.assertEqual(self.role()['basis'], self.proof['kind'])

    def test_kind_marker_without_current_reviewed_operation_is_rejected(self):
        self.helper.roles = {}
        self.assertIsNone(self.role())

    def test_role_payload_tampering_is_rejected(self):
        self.con.execute('UPDATE evidence SET payload=?', (json.dumps({**self.proof, 'tampered': True}),))
        self.assertIsNone(self.role())

    def test_current_role_row_tampering_is_rejected(self):
        self.con.execute("UPDATE normalization_roles SET status='REVIEW'")
        self.assertIsNone(self.role())

    def test_baseline_role_mismatch_is_rejected(self):
        self.helper.roles['source:child'] = {**self.role_op, 'before_profile': {'uid': 'source:child', 'node_kind': 'INSTANCE'}}
        self.assertIsNone(self.role())

    def test_exact_class_scope_history_is_accepted(self):
        self.assertEqual(len(self.withdrawal()), 1)

    def test_unknown_history_storage_is_rejected(self):
        self.con.execute("UPDATE usability_changes SET object_type='unrelated'")
        self.assertEqual(self.withdrawal(), [])

    def test_before_history_tampering_is_rejected(self):
        self.con.execute('UPDATE usability_changes SET before_json=?', (json.dumps({**self.before, 'source': 'other'}),))
        self.assertEqual(self.withdrawal(), [])

    def test_unreviewed_current_source_changes_are_rejected(self):
        self.con.execute("UPDATE edges SET source='changed'")
        self.assertEqual(self.withdrawal(), [])

    def test_incorrect_baseline_row_is_rejected(self):
        baseline = sqlite3.connect(':memory:')
        baseline.row_factory = sqlite3.Row
        baseline.execute('CREATE TABLE edges(id INTEGER,child_uid TEXT,parent_uid TEXT,relation TEXT,status TEXT,source TEXT)')
        baseline.execute('INSERT INTO edges VALUES(?,?,?,?,?,?)', tuple(({**self.before, 'source': 'different baseline'}).values()))
        result = self.helper.withdrawal_evidence(self.con, self.path, lambda *args, **kwargs: [], baseline_con=baseline)
        baseline.close()
        self.assertEqual(result, [])

    def test_legacy_proof_is_retained(self):
        legacy = {'basis': 'retained original basis'}
        self.assertIs(self.helper.role_evidence(self.con, 'source:child', 'CLASS', 'MODEL', lambda *args: legacy), legacy)


if __name__ == '__main__':
    unittest.main()
