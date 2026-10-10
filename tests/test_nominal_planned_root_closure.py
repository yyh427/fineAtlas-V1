"""Independent SQL controls for preflight plans versus actual post-build paths."""
import importlib.util
from pathlib import Path
import sqlite3
import unittest

SPEC = importlib.util.spec_from_file_location(
    'nominal_root_controls', Path(__file__).resolve().parents[1] /
    'scripts/audit_nominal_design_scope_repairs.py')
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)


class PlannedRootClosure(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.c.executescript(
            'CREATE TABLE nodes(uid TEXT PRIMARY KEY,rank TEXT,component_id INTEGER,visibility TEXT);'
            'CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,attributes TEXT);'
            'CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,relation TEXT,status TEXT);'
            'CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,relation TEXT,status TEXT);')
        self.root = 'wordnet31:00001740-n'
        self.c.executemany('INSERT INTO nodes VALUES (?,?,?,?)',
                          [('source', 'class', 1, 'ACTIVE'), (self.root, 'class', 2, 'ACTIVE')])
        self.c.executemany('INSERT INTO node_profiles VALUES (?,?,?)',
                          [('source', 'CLASS', '{}'), (self.root, 'CLASS', '{}')])
        self.link = {'op': 'link', 'uid': 'source', 'parent': self.root, 'relation': 'IS_A'}

    def tearDown(self):
        self.c.close()

    def test_preflight_plan_cannot_stand_in_for_post_build_real_edge(self):
        A.check_planned_root_closure(self.c, [self.link])
        with self.assertRaisesRegex(ValueError, 'no legitimate planned root'):
            A.check_planned_root_closure(self.c, [self.link], post=True)
        self.c.execute('INSERT INTO edges VALUES (1,?,?,?,?)',
                       ('source', self.root, 'IS_A', 'ACTIVE'))
        A.check_planned_root_closure(self.c, [self.link], post=True)

    def test_precise_withdrawal_of_last_parent_blocks_closure(self):
        self.c.execute('INSERT INTO edges VALUES (1,?,?,?,?)',
                       ('source', self.root, 'IS_A', 'ACTIVE'))
        review = {'op': 'review_class_edge', 'uid': 'source', 'parent': self.root,
                  'before_assertion': {'id': 1}}
        with self.assertRaisesRegex(ValueError, 'no legitimate planned root'):
            A.check_planned_root_closure(self.c, [review])
        A.check_planned_root_closure(self.c, [review, self.link])

    def test_role_adjudication_requires_compatible_real_relation(self):
        correction = {'op': 'correct_role', 'uid': 'source', 'parent': 'source',
                      'after_profile': {'node_kind': 'MODEL', 'attributes': '{}'}}
        with self.assertRaisesRegex(ValueError, 'no legitimate planned root'):
            A.check_planned_root_closure(self.c, [correction, self.link])
        typed = {**self.link, 'relation': 'DESIGN_TYPE_OF'}
        A.check_planned_root_closure(self.c, [correction, typed])

    def test_source_view_quarantine_cannot_admit_a_normal_class(self):
        self.c.execute("UPDATE node_profiles SET attributes=? WHERE uid='source'",
                       (A.dump({'allowed_views': []}),))
        with self.assertRaisesRegex(ValueError, 'no legitimate planned root'):
            A.check_planned_root_closure(self.c, [self.link])

    def test_pending_unknown_is_not_counted_as_a_navigable_root_path(self):
        correction = {'op': 'correct_role', 'uid': 'source', 'parent': 'source',
                      'after_profile': {'node_kind': 'UNKNOWN', 'attributes': A.dump({'allowed_views': []})}}
        A.check_planned_root_closure(self.c, [correction])
        # Source approval is checked by the role auditor; this closure exemption
        # grants no edge or navigation to the ambiguous object.
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM edges').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
