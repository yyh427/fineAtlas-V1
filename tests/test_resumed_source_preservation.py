"""Visibility migration permits must not hide changes to raw source facts."""
from pathlib import Path
import sqlite3
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit_resumed_source_preservation as audit


class VisibilityPreservation(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.con.execute('CREATE TABLE nodes(uid,label,data,visibility)')
        self.con.executemany('INSERT INTO nodes VALUES (?,?,?,?)', [
            ('source:one', 'One', '{"raw":1}', 'ACTIVE'),
            ('source:two', 'Two', '{"raw":2}', 'ACTIVE')])
        self.columns = ['uid', 'label', 'data', 'visibility']
        self.original = audit.digest_rows(self.con, 'nodes', self.columns, 2)[0]
        self.permit = {'source:one': {'before': 'ACTIVE', 'after': 'SOURCE_ONLY',
                                     'delta': 'cars-projection-view'}}

    def tearDown(self):
        self.con.close()

    def test_explicit_visibility_migration_preserves_raw_checksum(self):
        self.con.execute("UPDATE nodes SET visibility='SOURCE_ONLY' WHERE uid='source:one'")
        actual, changes = audit.digest_rows(self.con, 'nodes', self.columns, 2, self.permit)
        self.assertEqual(actual['sha256'], self.original['sha256'])
        self.assertEqual(len(changes), 1)

    def test_missing_actual_migration_is_rejected(self):
        with self.assertRaises(ValueError):
            audit.digest_rows(self.con, 'nodes', self.columns, 2, self.permit)

    def test_other_visibility_changes_remain_visible(self):
        self.con.execute("UPDATE nodes SET visibility='SOURCE_ONLY'")
        actual, _ = audit.digest_rows(self.con, 'nodes', self.columns, 2, self.permit)
        self.assertNotEqual(actual['sha256'], self.original['sha256'])

    def test_raw_payload_changes_cannot_be_normalized(self):
        self.con.execute("UPDATE nodes SET visibility='SOURCE_ONLY',data='changed' WHERE uid='source:one'")
        actual, _ = audit.digest_rows(self.con, 'nodes', self.columns, 2, self.permit)
        self.assertNotEqual(actual['sha256'], self.original['sha256'])

    def test_original_row_removal_is_detected(self):
        self.con.execute("DELETE FROM nodes WHERE uid='source:two'")
        actual, _ = audit.digest_rows(self.con, 'nodes', self.columns, 2)
        self.assertNotEqual(actual['rows'], self.original['rows'])
        self.assertNotEqual(actual['sha256'], self.original['sha256'])

    def test_compatibility_entry_retains_every_other_acceptance_check(self):
        original = (ROOT / 'scripts/accept_structure_candidate.py').read_text()
        resumed = (ROOT / 'scripts/accept_resumed_structure_candidate.py').read_text()
        resumed = resumed.replace("command('audit_resumed_source_preservation.py'", "command('audit_structure_preservation.py'")
        resumed = resumed.replace("'--inputs',a.inputs,'--reference',a.reference", "'--reference',a.reference")
        self.assertEqual(resumed, original)


if __name__ == '__main__':
    unittest.main()
