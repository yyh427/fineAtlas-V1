import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from fineatlas.repair_candidate import RepairWriter, rollback, verify_rollback_stack


class RepairRollbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'fixture.sqlite'
        with sqlite3.connect(self.path) as c:
            c.executescript('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE components(id INTEGER); CREATE TABLE dataset_scope_targets(source_uid TEXT);')
            c.execute('INSERT INTO metadata VALUES(?,?)', ('database_revision', json.dumps('root')))

    def tearDown(self):
        self.tmp.cleanup()

    def stage(self, name, previous, value):
        w = RepairWriter(self.path, expected_revision=previous)
        self.assertTrue(w.begin(name, {'operation': value}))
        if value is None:
            w.delete('metadata', {'key': 'test_value'})
        else:
            w.meta('test_value', value)
        result = w.finish({'status': 'APPLIED'})
        w.c.close()
        return result['database_revision']

    def test_stack_dry_run_preserves_candidate_and_actual_reverse_restores_deleted_row(self):
        one = self.stage('one', 'root', 'one')
        two = self.stage('two', one, None)
        proof = verify_rollback_stack(self.path)
        self.assertTrue(proof['passed'])
        self.assertEqual(proof['restored_base_revision_in_transaction'], 'root')
        with sqlite3.connect(self.path) as c:
            self.assertEqual(json.loads(c.execute("SELECT value FROM metadata WHERE key='database_revision'").fetchone()[0]), two)
        self.assertEqual(rollback(self.path, 'two')['status'], 'ROLLED_BACK')
        with sqlite3.connect(self.path) as c:
            self.assertEqual(json.loads(c.execute("SELECT value FROM metadata WHERE key='test_value'").fetchone()[0]), 'one')
        self.assertEqual(rollback(self.path, 'one')['status'], 'ROLLED_BACK')

    def test_refuses_to_overwrite_later_unjournaled_edits(self):
        self.stage('one', 'root', 'one')
        with sqlite3.connect(self.path) as c:
            c.execute("UPDATE metadata SET value=? WHERE key='test_value'", (json.dumps('someone else'),))
        with self.assertRaisesRegex(ValueError, 'changed after repair'):
            rollback(self.path, 'one')
        with sqlite3.connect(self.path) as c:
            self.assertEqual(json.loads(c.execute("SELECT value FROM metadata WHERE key='test_value'").fetchone()[0]), 'someone else')

    def test_idempotent_package_has_no_new_writes_and_changed_inputs_are_rejected(self):
        revision = self.stage('one', 'root', 'one')
        w = RepairWriter(self.path, expected_revision=revision)
        self.assertFalse(w.begin('one', {'operation': 'one'}))
        with self.assertRaisesRegex(ValueError, 'different inputs'):
            w.begin('one', {'operation': 'two'})
        w.c.close()


if __name__ == '__main__':
    unittest.main()
