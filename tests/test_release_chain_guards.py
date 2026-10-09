"""Release acceptance must identify the exact revision and complete table schema."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_chain_verifier', ROOT / 'scripts/verify_unified_install.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class ReleaseRevisionBindingTests(unittest.TestCase):
    def test_same_revision_does_not_accept_another_pinned_file_hash(self):
        expected={'release':'review','database_revision':'same','database_sha256':'accepted-file'}
        manifest={'release':'review','database_revision':'same','database':{'sha256':'other-file'}}
        with self.assertRaisesRegex(AssertionError,'file hash differs'):
            verifier.validate_acceptance_revision(expected,manifest)

    def test_same_release_inventory_and_totals_do_not_accept_an_older_revision(self):
        expected = {'release': 'v1.10.1-repair-review', 'database_revision': 'older-graph',
                    'domains': {'actual': 95, 'public_contract_passes': 95}, 'pairs': {'dataset': {'pairs': 3}}}
        manifest = {'release': expected['release'], 'database_revision': 'newer-graph', 'domain_count': 95}
        with self.assertRaisesRegex(AssertionError, 'revision differs'):
            verifier.validate_acceptance_revision(expected, manifest)

    def test_current_exact_revision_is_accepted(self):
        value = {'release': 'v1.10.1-repair-review', 'database_revision': 'current-graph'}
        self.assertEqual(verifier.validate_acceptance_revision(value, value), 'current-graph')

    def test_missing_snapshot_revision_is_not_legacy_fallback(self):
        value = {'release': 'v1.10.1-repair-review', 'database_revision': 'current-graph'}
        with self.assertRaisesRegex(AssertionError, 'Expected validation lacks'):
            verifier.validate_acceptance_revision({'release': value['release']}, value)
        with self.assertRaisesRegex(AssertionError, 'Published manifest lacks'):
            verifier.validate_acceptance_revision(value, {'release': value['release']})

    def test_revision_guard_runs_before_database_queries_or_receipt_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifest.json').write_text(json.dumps({'release': 'same-review', 'database_revision': 'new'}))
            (root / 'expected.json').write_text(json.dumps({'release': 'same-review', 'database_revision': 'old'}))
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/verify_unified_install.py'),
                '--database', str(root / 'does-not-exist.sqlite'), '--manifest', str(root / 'manifest.json'),
                '--expected-validation', str(root / 'expected.json'), '--output', str(root / 'verification')],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Acceptance revision differs', result.stderr)
            self.assertFalse((root / 'verification').exists())


class ReproductionSchemaGuardTests(unittest.TestCase):
    def compare(self, modifier=None, setup=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('primary', 'reproduction'):
                with sqlite3.connect(root / (name + '.sqlite')) as c:
                    c.executescript('''CREATE TABLE records(uid TEXT PRIMARY KEY,value TEXT);
                      INSERT INTO records VALUES('a','same');
                      CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
                      INSERT INTO metadata VALUES('usability_view_statistics','{"unified":{"nodes":1,"seconds":2}}');''')
                    if setup:
                        setup(c)
                    if name == 'reproduction' and modifier:
                        modifier(c)
            output = root / 'comparison.json'
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/compare_reproductions.py'),
                '--database', str(root / 'primary.sqlite'), '--reproduction', str(root / 'reproduction.sqlite'),
                '--output', str(output)], capture_output=True, text=True)
            return result, json.loads(output.read_text())

    def test_equal_logical_rows_and_schema_pass(self):
        result, report = self.compare()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(report['schema_inventory']['pass'])
        self.assertTrue(report['records']['pass'])

    def test_unexpected_reproduction_table_fails_despite_all_expected_rows_matching(self):
        result, report = self.compare(lambda c: c.execute('CREATE TABLE unexpected(uid TEXT)'))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['schema_inventory']['reproduction_only_tables'], ['unexpected'])
        self.assertFalse(report['schema_inventory']['pass'])

    def test_missing_reproduction_table_has_explicit_failed_inventory(self):
        result, report = self.compare(lambda c: c.execute('DROP TABLE records'))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['schema_inventory']['primary_only_tables'], ['records'])

    def test_same_rows_with_different_constraint_fails_schema(self):
        def change(c):
            c.executescript('''ALTER TABLE records RENAME TO old_records;
              CREATE TABLE records(uid TEXT PRIMARY KEY,value TEXT NOT NULL);
              INSERT INTO records SELECT * FROM old_records; DROP TABLE old_records;''')
        result, report = self.compare(change)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('records', report['schema_inventory']['different_table_schemas'])

    def test_ignored_runtime_rows_do_not_hide_their_changed_table_schema(self):
        result, report = self.compare(lambda c: c.execute('CREATE TABLE browse_build_stages(name TEXT)'))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['schema_inventory']['reproduction_only_tables'], ['browse_build_stages'])

    def test_existing_row_content_difference_still_fails(self):
        result, report = self.compare(lambda c: c.execute("UPDATE records SET value='changed'"))
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(report['schema_inventory']['pass'])
        self.assertFalse(report['records']['pass'])

    def test_missing_explicit_index_is_not_hidden_by_equal_tables(self):
        result, report = self.compare(
            lambda c: c.execute('DROP INDEX records_value'),
            lambda c: c.execute('CREATE INDEX records_value ON records(value)'))
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(report['schema_inventory']['pass'])
        self.assertEqual(report['schema_objects']['primary_only_objects'][0]['name'], 'records_value')

    def test_same_named_partial_index_with_changed_predicate_fails(self):
        result, report = self.compare(
            lambda c: c.executescript("DROP INDEX records_value; CREATE INDEX records_value ON records(value) WHERE value='different';"),
            lambda c: c.execute("CREATE INDEX records_value ON records(value) WHERE value='same'"))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['schema_objects']['different_object_definitions'][0]['primary']['type'], 'index')

    def test_changed_view_definition_fails_with_equal_underlying_rows(self):
        result, report = self.compare(
            lambda c: c.executescript("DROP VIEW visible_records; CREATE VIEW visible_records AS SELECT * FROM records WHERE value='absent';"),
            lambda c: c.execute('CREATE VIEW visible_records AS SELECT * FROM records'))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['schema_objects']['different_object_definitions'][0]['primary']['type'], 'view')

    def test_changed_trigger_body_fails_before_any_trigger_is_fired(self):
        result, report = self.compare(
            lambda c: c.executescript("DROP TRIGGER reject_delete; CREATE TRIGGER reject_delete BEFORE DELETE ON records BEGIN SELECT RAISE(ABORT,'different'); END;"),
            lambda c: c.execute("CREATE TRIGGER reject_delete BEFORE DELETE ON records BEGIN SELECT RAISE(ABORT,'preserve'); END"))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['schema_objects']['different_object_definitions'][0]['primary']['type'], 'trigger')

    def test_extra_view_has_explicit_failed_object_inventory(self):
        result, report = self.compare(lambda c: c.execute('CREATE VIEW extra AS SELECT uid FROM records'))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['schema_objects']['reproduction_only_objects'][0]['name'], 'extra')

    def test_sqlite_similar_user_object_is_not_mistaken_for_builtin(self):
        result, report = self.compare(lambda c: c.execute('CREATE VIEW sqlitex_user AS SELECT uid FROM records'))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report['schema_objects']['reproduction_only_objects'][0]['name'], 'sqlitex_user')

    def test_runtime_values_remain_permitted_with_identical_schema(self):
        def modify(c):
            c.execute("UPDATE metadata SET value=? WHERE key='usability_view_statistics'",
                      ('{"unified":{"nodes":1,"seconds":99}}',))
            c.execute("UPDATE browse_build_stages SET seconds=99")
        result, report = self.compare(modify, lambda c: c.executescript(
            "CREATE TABLE browse_build_stages(name TEXT PRIMARY KEY,seconds REAL); INSERT INTO browse_build_stages VALUES('done',1);"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(report['schema_objects']['pass'])
        self.assertTrue(report['view_statistics_without_runtime']['pass'])


if __name__ == '__main__':
    unittest.main()
