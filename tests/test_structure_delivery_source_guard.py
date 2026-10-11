"""Public raw preservation cannot be inferred from partial or stale evidence."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from _download import digest
from structure_delivery_source_guard import validate_source_preservation


class PublicSourceGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name); self.inputs = self.root / 'inputs'; self.inputs.mkdir()
        (self.inputs / 'policy.json').write_text('{}'); self.frozen = {'policy.json': digest(self.inputs / 'policy.json')}
        self.db = self.root / 'public.sqlite'; self.base = self.root / 'formal.sqlite'
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE metadata(key,value)'); c.executemany('INSERT INTO metadata VALUES(?,?)', [('database_revision', json.dumps('actual')), ('structure_frozen_build_manifest', json.dumps({'inputs': self.frozen}))])
        with sqlite3.connect(self.base) as c: c.execute('CREATE TABLE nodes(uid,visibility)')
        self.reference = self.root / 'reference.json'; self.report = self.root / 'public-source.json'
        table = {'columns': ['uid', 'visibility'], 'max_baseline_rowid': 1, 'baseline': {'sha256': 'original-hash', 'rows': 1}}
        self.reference.write_text(json.dumps({'tables': {'nodes': table}}))
        self.value = {'schema': 'FINEATLAS_RESUMED_RAW_SOURCE_PRESERVATION_V1', 'pass': True, 'complete': True, 'candidate': str(self.db), 'baseline': str(self.base), 'database_revision': 'actual',
                      'allowed_fields': ['nodes.visibility'], 'frozen_input_fingerprints': self.frozen, 'independent_actual_audits': [], 'audited_visibility_changes': [],
                      'tables': {'nodes': {**table, 'pass': True, 'candidate_with_audited_visibility': table['baseline']}}}
    def tearDown(self): self.tmp.cleanup()
    def check(self):
        self.report.write_text(json.dumps(self.value))
        return validate_source_preservation(self.report, self.db, self.base, self.reference, self.inputs, 'actual', self.root / 'code')
    def test_complete_exact_raw_reference(self): self.assertTrue(self.check()['pass'])
    def test_partial_hash_census_rejected(self):
        self.value['complete'] = False
        with self.assertRaises(ValueError): self.check()
    def test_stale_database_revision_rejected(self):
        self.value['database_revision'] = 'parent'
        with self.assertRaises(ValueError): self.check()
    def test_other_public_artifact_rejected(self):
        self.value['candidate'] = str(self.base)
        with self.assertRaises(ValueError): self.check()
    def test_raw_data_hash_loss_is_not_visibility_waiver(self):
        self.value['tables']['nodes']['candidate_with_audited_visibility'] = {'sha256': 'changed-raw', 'rows': 1}
        with self.assertRaisesRegex(ValueError, 'retained raw'): self.check()
    def test_missing_original_table_rejected(self):
        self.value['tables'] = {}
        with self.assertRaises(ValueError): self.check()
    def test_extra_unfrozen_input_rejected(self):
        (self.inputs / 'unfrozen.json').write_text('{}')
        with self.assertRaises(ValueError): self.check()
    def test_unexplained_visibility_waiver_rejected(self):
        self.value['audited_visibility_changes'] = [{'uid': 'arbitrary', 'before': 'ACTIVE', 'after': 'SOURCE_ONLY', 'delta': 'cars-projection-view'}]
        with self.assertRaisesRegex(ValueError, 'census'): self.check()
    def test_raw_field_waiver_rejected(self):
        self.value['allowed_fields'].append('nodes.data')
        with self.assertRaises(ValueError): self.check()

if __name__ == '__main__': unittest.main()
