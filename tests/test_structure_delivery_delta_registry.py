"""New frozen deltas cannot be omitted from public extension acceptance."""
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import coordinate_structure_delivery as delivery
import structure_delivery_delta_registry as registry
import test_structure_delivery_oem_guard as oem_controls


class RegisteredDeltaGuards(oem_controls.OEMEvidenceGuards):
    def setUp(self):
        super().setUp()
        self.spec = registry.REGISTERED_DELTAS[0]
        module = self.code / self.spec.module
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_text("INPUT_NAME = 'renamed-oem-repairs.json'\n")
        self.value['schema'] = self.spec.schema
        self.report.write_text(json.dumps(self.value))

    def validate(self):
        return registry.validate_delta_receipt(self.spec, self.report, self.database,
                                               self.inputs, 'actual-revision', self.code)

    def test_registry_requires_dynamic_adapter_input(self):
        self.assertEqual(registry.required_deltas(self.inputs, self.code), [self.spec])

    def test_same_count_wrong_relation_distribution_rejected(self):
        self.value['operations'] = {'IS_A': 1}
        self.report.write_text(json.dumps(self.value))
        with self.assertRaisesRegex(ValueError, 'census'):
            self.validate()

    def test_boolean_count_cannot_fake_integer_census(self):
        self.value['operation_count'] = True
        self.report.write_text(json.dumps(self.value))
        with self.assertRaises(ValueError):
            self.validate()

    def test_omitted_registered_delta_blocks_finalization(self):
        coordinator = delivery.Coordinator.__new__(delivery.Coordinator)
        coordinator.root = self.root
        coordinator.inputs = self.inputs
        coordinator.accepted = lambda: {'database_revision': 'actual-revision'}
        target = self.root / 'public/checks/resume_public_extension.json'
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({'pass': True, 'database_revision': 'actual-revision',
            'database': str(self.root / 'public/data/fineatlas.sqlite'), 'evidence': {}}))
        with patch.object(delivery, 'optional_oem_input', return_value=None):
            with patch.object(delivery, 'required_deltas', return_value=[self.spec]):
                with patch.object(coordinator, 'execute') as execute:
                    with self.assertRaisesRegex(ValueError, 'Frozen delta requires actual public evidence'):
                        coordinator.finalize()
                    execute.assert_not_called()


class CarsProjectionViewGuards(RegisteredDeltaGuards):
    def setUp(self):
        super().setUp()
        old_module = self.code / self.spec.module
        old_module.unlink()
        self.spec = registry.REGISTERED_DELTAS[1]
        module = self.code / self.spec.module
        module.write_text("INPUT_NAME = 'renamed-oem-repairs.json'\n")
        self.operations.write_text('{"op":"review_world_projection_relation","relation":"CONFIGURATION_OF"}\n')
        from _download import digest
        manifest = json.loads(self.manifest.read_text())
        manifest['operations_sha256'] = digest(self.operations)
        self.manifest.write_text(json.dumps(manifest))
        self.value['schema'] = self.spec.schema
        self.value['operations'] = {'CONFIGURATION_OF': 1}
        self.value['manifest_sha256'] = digest(self.manifest)
        self.value['operations_sha256'] = digest(self.operations)
        self.report.write_text(json.dumps(self.value))
        with sqlite3.connect(self.database) as con:
            con.execute('UPDATE metadata SET value=? WHERE key=?', (json.dumps({'inputs': {
                self.manifest.name: digest(self.manifest), self.operations.name: digest(self.operations)}}),
                'structure_frozen_build_manifest'))
            con.execute('INSERT INTO metadata VALUES(?,?)', (self.spec.metadata_key, json.dumps({
                'manifest_sha256': self.value['manifest_sha256'],
                'operations_sha256': self.value['operations_sha256'], 'operation_count': 1})))

    def test_view_review_count_is_bound_to_applied_metadata(self):
        with sqlite3.connect(self.database) as con:
            con.execute('UPDATE metadata SET value=? WHERE key=?',
                        (json.dumps({'manifest_sha256': 'old-manifest'}), self.spec.metadata_key))
        with self.assertRaisesRegex(ValueError, 'applied delta metadata'):
            self.validate()


if __name__ == '__main__':
    unittest.main()
