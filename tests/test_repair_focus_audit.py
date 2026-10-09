import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import unittest

SPEC = importlib.util.spec_from_file_location('repair_focus_audit', Path(__file__).resolve().parents[1] / 'scripts/audit_repair_focus.py')
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class FocusCheckerTests(unittest.TestCase):
    def furniture(self, *, member=True):
        class Tree:
            root_uid = 'parent'

            def node(self, uid):
                return {'uid': uid, 'node_kind': 'CONFIGURATION' if uid == 'config' else 'CLASS',
                        'component_id': 1 if uid == 'config' else 2}

            def path_result(self, uid):
                return {'status': 'CONNECTED', 'path': [{'edge': {'id': 2, 'relation': 'CONFIGURATION_TYPE_OF',
                        'child_uid': 'config', 'parent_uid': 'parent'}}]}

            def connection_status(self, uid):
                return {'path_status': 'CONNECTED', 'root_reachable': True}

            def _parents(self, uid):
                return [('other', {'id': 1, 'relation': 'CONFIGURATION_TYPE_OF'}),
                        ('parent', {'id': 2, 'relation': 'CONFIGURATION_TYPE_OF'})]
        tree = Tree()
        tree.con = sqlite3.connect(':memory:')
        tree.con.row_factory = sqlite3.Row
        tree.con.executescript('''
          CREATE TABLE nodes(uid TEXT PRIMARY KEY,data TEXT);
          CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);
          CREATE TABLE domain_members(domain_id INTEGER,view TEXT,uid TEXT,role TEXT);
        ''')
        proof = {'native_record': {'product_type': [{'value': 'TABLE'}]}}
        row = {'uid': 'config', 'parent': 'parent', 'relation': 'CONFIGURATION_TYPE_OF', 'source': 'ABO', 'proof': proof}
        tree.con.execute('INSERT INTO nodes VALUES(?,?)', ('config', json.dumps(proof)))
        tree.con.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?)',
                         (2, 'config', 'parent', 'CONFIGURATION_TYPE_OF', 'ABO', 'ACTIVE', json.dumps({'admission_basis': proof})))
        tree.con.execute("INSERT INTO domain_members VALUES(37,'unified','parent','CLASS')")
        if member:
            tree.con.execute("INSERT INTO domain_members VALUES(37,'unified','config','CONFIGURATION')")
        return tree, row

    def test_positive_configuration_checks_the_actual_furniture_member(self):
        tree, row = self.furniture()
        self.assertTrue(AUDIT.furniture_record(tree, row, {'domain_id': 37})['pass'])

    def test_root_path_and_parent_membership_cannot_substitute_for_product_membership(self):
        tree, row = self.furniture(member=False)
        result = AUDIT.furniture_record(tree, row, {'domain_id': 37})
        self.assertTrue(result['legal_path']['pass'])
        self.assertFalse(result['actual_furniture_membership'])
        self.assertFalse(result['pass'])

    def test_full_source_payload_drift_fails(self):
        tree, row = self.furniture()
        tree.con.execute("UPDATE nodes SET data='{}' WHERE uid='config'")
        self.assertFalse(AUDIT.furniture_record(tree, row, {'domain_id': 37})['pass'])

    def test_legal_path_uses_all_parent_options_and_rejects_a_stale_witness(self):
        tree, _ = self.furniture()
        result = AUDIT.legal_path(tree, 'config')
        self.assertTrue(result['pass'])
        self.assertEqual(len(result['all_legal_direct_parent_options']), 2)
        tree.path_result = lambda uid: {'status': 'CONNECTED', 'path': [{'edge': {'id': 99,
            'relation': 'CONFIGURATION_TYPE_OF', 'child_uid': 'config', 'parent_uid': 'parent'}}]}
        self.assertFalse(AUDIT.legal_path(tree, 'config')['pass'])

    def test_recorded_role_operation_does_not_certify_a_wrong_current_role(self):
        tree, _ = self.furniture()
        tree.con.execute('CREATE TABLE hierarchy_decisions(id TEXT PRIMARY KEY,payload TEXT)')
        tree.con.execute('CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,evidence_id TEXT)')
        record = {'op': 'role', 'uid': 'config', 'role': 'CLASS', 'proof': {}}
        digest = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        tree.con.execute('INSERT INTO hierarchy_decisions VALUES(?,?)', (digest, json.dumps(record)))
        ledgers = {('roles', 'node', 'config'): [{'evidence': '{}', 'after_json': '{"node_kind":"CLASS"}'}]}
        result = AUDIT.shared_operation(tree, record, None, ledgers)
        self.assertTrue(result['frozen_decision_retained'])
        self.assertEqual(result['exact_role_ledger_records'], 1)
        self.assertFalse(result['pass'])

    def test_unmeasured_error_is_a_failed_check(self):
        checks = AUDIT.Checks()
        checks.run('missing_source', lambda: (_ for _ in ()).throw(ValueError('Missing source')))
        self.assertFalse(checks.items[0]['pass'])
        self.assertEqual(checks.items[0]['status'], 'ERROR')

    def test_matching_current_role_requires_the_exact_frozen_role_evidence(self):
        tree, _ = self.furniture()
        tree.node = lambda uid: {'uid': uid, 'node_kind': 'CLASS'}
        tree.con.execute('CREATE TABLE hierarchy_decisions(id TEXT PRIMARY KEY,payload TEXT)')
        tree.con.execute('CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,evidence_id TEXT)')
        record = {'op': 'role', 'uid': 'config', 'role': 'CLASS', 'proof': {}}
        digest = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        tree.con.execute('INSERT INTO hierarchy_decisions VALUES(?,?)', (digest, json.dumps(record)))
        tree.con.execute("INSERT INTO node_profiles VALUES('config','stale-evidence')")
        ledgers = {('roles', 'node', 'config'): [{'evidence': '{}', 'after_json': '{"node_kind":"CLASS"}'}]}
        self.assertFalse(AUDIT.shared_operation(tree, record, None, ledgers)['pass'])
        expected = 'usability:' + hashlib.sha256(b'{}').hexdigest()
        tree.con.execute('UPDATE node_profiles SET evidence_id=?', (expected,))
        self.assertTrue(AUDIT.shared_operation(tree, record, None, ledgers)['pass'])


if __name__ == '__main__':
    unittest.main()
