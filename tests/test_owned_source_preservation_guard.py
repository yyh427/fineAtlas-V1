"""Later scope history must never bypass the whole original raw-source guard."""
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import structure_owned_source_guard as guard


class OwnedSourcePreservationGuardTests(unittest.TestCase):
    def setUp(self):
        self.arguments = tuple(Path(x) for x in (
            '/audit/source.json', '/artifact/final.sqlite', '/baseline/formal.sqlite',
            '/support/raw-reference.json', '/frozen/inputs')) + ('final-revision', Path('/frozen/code'))
        self.temporal = Mock()
        self.module = types.ModuleType('structure_subject_scope_temporal_contract')
        self.module.require_temporal_subject_receipt = self.temporal
        self.spec = types.SimpleNamespace(name='complete-subject-scope')
        self.report = {'independent_actual_audits': [
            {'delta': 'complete-subject-scope', 'report': '/audit/actual-third.json'}]}

    def invoke(self, report=None, original_error=None, required=True):
        with patch.dict(sys.modules, {'structure_subject_scope_temporal_contract': self.module}), \
                patch.object(guard, 'validate_original_preservation',
                             return_value=self.report if report is None else report,
                             side_effect=original_error) as original, \
                patch('structure_delivery_delta_registry.required_deltas',
                      return_value=[self.spec] if required else []):
            result = guard.validate_source_preservation(*self.arguments)
            original.assert_called_once_with(*self.arguments)
            return result

    def test_original_failure_cannot_be_waived_by_temporal_evidence(self):
        with self.assertRaisesRegex(ValueError, 'raw source differs'):
            self.invoke(original_error=ValueError('raw source differs'))
        self.temporal.assert_not_called()

    def test_missing_actual_third_audit_fails(self):
        with self.assertRaisesRegex(ValueError, 'Exactly one'):
            self.invoke({'independent_actual_audits': []})
        self.temporal.assert_not_called()

    def test_duplicate_actual_third_audit_fails(self):
        with self.assertRaisesRegex(ValueError, 'Exactly one'):
            self.invoke({'independent_actual_audits': self.report['independent_actual_audits'] * 2})
        self.temporal.assert_not_called()

    def test_temporal_failure_is_fatal_after_raw_source_pass(self):
        self.temporal.side_effect = ValueError('Unreviewed type status changed')
        with self.assertRaisesRegex(ValueError, 'Unreviewed type status'):
            self.invoke()

    def test_actual_temporal_audit_binds_current_snapshot_and_code(self):
        result = self.invoke()
        self.assertIs(result, self.report)
        self.temporal.assert_called_once_with(
            Path('/audit/actual-third.json'), self.arguments[1], self.arguments[4],
            self.arguments[5], self.arguments[6])

    def test_other_migration_audit_cannot_replace_required_third_audit(self):
        with self.assertRaisesRegex(ValueError, 'Exactly one'):
            self.invoke({'independent_actual_audits': [
                {'delta': 'cars-projection-view', 'report': '/audit/cars.json'}]})
        self.temporal.assert_not_called()


if __name__ == '__main__':
    unittest.main()
