"""New frozen deltas cannot be omitted from public extension acceptance."""
import json
from pathlib import Path
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


if __name__ == '__main__':
    unittest.main()
