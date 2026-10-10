"""Controls for exact prior withdrawals in the independent source-eight audit."""
import importlib.util
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/audit_temporal_ninth_complete_owned_type_repairs.py'
SPEC = importlib.util.spec_from_file_location('ninth_complete_audit_controls', SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class ExactTemporalWithdrawals(unittest.TestCase):
    def setUp(self):
        self.before = {'id': 24, 'child_uid': 'source:individual', 'parent_uid': 'source:class',
                       'relation': 'IS_A', 'source': 'Retained source', 'status': 'ACTIVE',
                       'reason': 'Original explanation', 'data': '{}', 'provenance': '{}'}
        self.prior = {'table': 'edges', 'id': 24, 'status': 'ACTIVE',
                      'content_sha256': AUDIT.assertion_sha(self.before)}
        self.op = {'op': 'review_class_edge', 'before_assertion': self.before,
                   'after_status': 'SOURCE_SCOPE_REVIEW', 'proof': {
                       'kind': 'SOURCE_OWNED_GRAIN_INCOMPATIBLE_CLASSIFICATION_REVIEW'}}

    def test_same_batch_class_review_requires_full_independent_check(self):
        with patch.object(AUDIT, 'independently_check_additional_review') as check:
            self.assertEqual(AUDIT.reviewed_prior_status(None, None, self.prior, [self.op], False),
                             'SOURCE_SCOPE_REVIEW')
            check.assert_called_once_with(None, None, self.op, [self.op], False)

    def test_preflight_remains_original_active_state(self):
        with patch.object(AUDIT, 'independently_check_additional_review') as check:
            self.assertEqual(AUDIT.reviewed_prior_status(None, None, self.prior, [self.op], True), 'ACTIVE')
            check.assert_not_called()

    def test_failed_scope_history_check_cannot_authorize_prior(self):
        with patch.object(AUDIT, 'independently_check_additional_review', side_effect=ValueError('History differs')):
            with self.assertRaisesRegex(ValueError, 'History differs'):
                AUDIT.reviewed_prior_status(None, None, self.prior, [self.op], False)

    def test_content_changed_before_review_is_rejected(self):
        self.op['before_assertion'] = {**self.before, 'data': '{"changed":true}'}
        with self.assertRaisesRegex(ValueError, 'original prior'):
            AUDIT.reviewed_prior_status(None, None, self.prior, [self.op], False)

    def test_duplicate_and_unapproved_reviews_fail(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            AUDIT.reviewed_prior_status(None, None, self.prior, [self.op, self.op], False)
        self.op['proof']['kind'] = 'Unreviewed'
        with self.assertRaisesRegex(ValueError, 'Unapproved'):
            AUDIT.reviewed_prior_status(None, None, self.prior, [self.op], False)

    def test_later_withdrawal_preserves_every_original_field(self):
        expected = AUDIT.temporal_row('edges', self.before, [self.op])
        self.assertEqual(expected, {**self.before, 'status': 'SOURCE_SCOPE_REVIEW'})
        self.assertEqual(self.before['status'], 'ACTIVE')
        self.op['before_assertion'] = {**self.before, 'reason': 'Rewritten explanation'}
        with self.assertRaisesRegex(ValueError, 'full original'):
            AUDIT.temporal_row('edges', self.before, [self.op])

    def test_role_timepoint_checks_full_before_profile(self):
        before = {'uid': 'source:programme', 'node_kind': 'MODEL', 'attributes': '{"allowed_views":["taxonomy"]}'}
        after = {**before, 'node_kind': 'MODEL_FAMILY'}
        correction = {'op': 'correct_role', 'uid': before['uid'], 'before_profile': before, 'after_profile': after}
        self.assertEqual(AUDIT.temporal_row('node_profiles', before, [correction]), after)
        correction['before_profile'] = {**before, 'attributes': '{}'}
        with self.assertRaisesRegex(ValueError, 'exact source-eight'):
            AUDIT.temporal_row('node_profiles', before, [correction])

    def test_no_review_keeps_prior_status(self):
        self.assertEqual(AUDIT.reviewed_prior_status(None, None, self.prior, [], False), 'ACTIVE')


if __name__ == '__main__':
    unittest.main()
