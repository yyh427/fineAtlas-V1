"""Optional OEM inputs become mandatory actual-data evidence when frozen."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import coordinate_structure_delivery as delivery
import structure_delivery_oem_guard as guard
from _download import digest


class OEMEvidenceGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.code = self.root / 'code'
        module = self.code / guard.MODULE
        module.parent.mkdir(parents=True)
        module.write_text("INPUT_NAME = 'renamed-oem-repairs.json'\n")
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        self.operations = self.inputs / 'oem-operations.jsonl'
        self.operations.write_text('{"relation":"CONFIGURATION_TYPE_OF"}\n')
        self.manifest = self.inputs / 'renamed-oem-repairs.json'
        self.manifest.write_text(json.dumps({'operations_file': self.operations.name,
            'operations_sha256': digest(self.operations), 'operation_count': 1}))
        self.database = self.root / 'database.sqlite'
        with sqlite3.connect(self.database) as con:
            con.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)')
            con.executemany('INSERT INTO metadata VALUES(?,?)', [
                ('database_revision', json.dumps('actual-revision')),
                ('structure_frozen_build_manifest', json.dumps({'inputs': {
                    self.manifest.name: digest(self.manifest), self.operations.name: digest(self.operations)}}))])
        self.report = self.root / 'oem-audit.json'
        self.value = {'schema': 'FINEATLAS_INDEPENDENT_OEM_BODY_SCOPE_AUDIT_V1',
            'pass': True, 'preflight_only': False, 'errors': [], 'database': str(self.database),
            'database_revision': 'actual-revision', 'manifest_sha256': digest(self.manifest),
            'operations_sha256': digest(self.operations), 'operation_count': 1,
            'operations': {'CONFIGURATION_TYPE_OF': 1}}
        self.report.write_text(json.dumps(self.value))

    def validate(self):
        return guard.validate_oem_receipt(self.report, self.database, self.inputs,
                                          'actual-revision', self.code)

    def test_adapter_input_name_is_dynamic_and_complete_receipt_passes(self):
        self.assertEqual(guard.optional_oem_input(self.inputs, self.code), self.manifest)
        self.assertTrue(self.validate()['pass'])

    def test_absent_optional_input_requires_no_receipt(self):
        self.manifest.unlink()
        self.report.unlink()
        self.assertIsNone(self.validate())

    def test_missing_receipt_rejected_when_input_is_frozen(self):
        self.report.unlink()
        with self.assertRaises(FileNotFoundError):
            self.validate()

    def test_preflight_cannot_substitute_for_actual_audit(self):
        self.value['preflight_only'] = True
        self.report.write_text(json.dumps(self.value))
        with self.assertRaisesRegex(ValueError, 'Complete actual'):
            self.validate()

    def test_stale_revision_rejected(self):
        self.value['database_revision'] = 'old-candidate'
        self.report.write_text(json.dumps(self.value))
        with self.assertRaises(ValueError):
            self.validate()

    def test_changed_manifest_or_operation_bytes_rejected(self):
        self.operations.write_text('{"relation":"WRONG"}\n')
        with self.assertRaisesRegex(ValueError, 'frozen snapshot'):
            self.validate()

    def test_report_from_other_database_rejected(self):
        self.value['database'] = str(self.root / 'other.sqlite')
        self.report.write_text(json.dumps(self.value))
        with self.assertRaises(ValueError):
            self.validate()

    def test_partial_operation_census_rejected(self):
        self.value['operation_count'] = 0
        self.report.write_text(json.dumps(self.value))
        with self.assertRaises(ValueError):
            self.validate()

    def test_finalize_cannot_omit_public_oem_evidence(self):
        coordinator = delivery.Coordinator.__new__(delivery.Coordinator)
        coordinator.root = self.root
        coordinator.inputs = self.inputs
        coordinator.accepted = lambda: {'database_revision': 'actual-revision'}
        extension = {'pass': True, 'database_revision': 'actual-revision',
                     'database': str(self.root / 'public/data/fineatlas.sqlite'), 'evidence': {}}
        target = self.root / 'public/checks/resume_public_extension.json'
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(extension))
        with patch.object(delivery, 'optional_oem_input', return_value=self.manifest):
            with patch.object(coordinator, 'execute') as execute:
                with self.assertRaisesRegex(ValueError, 'actual public OEM evidence'):
                    coordinator.finalize()
                execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
