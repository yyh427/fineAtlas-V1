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

    def test_absent_parent_roles_remain_absent_without_exact_correction(self):
        for table in ('node_profiles', 'normalization_roles'):
            self.assertIsNone(AUDIT.temporal_row(table, None, [], uid='source:parent'))
            with self.assertRaisesRegex(ValueError, 'explicit parent UID'):
                AUDIT.temporal_row(table, None, [])

    def test_exact_creation_from_absent_parent_role(self):
        for table, key in (('node_profiles', 'profile'),
                           ('normalization_roles', 'normalization_role')):
            after = {'uid': 'source:parent', 'node_kind': 'CLASS'}
            correction = {'op': 'correct_role', 'uid': after['uid'],
                          'before_' + key: None, 'after_' + key: after}
            self.assertEqual(AUDIT.temporal_row(table, None, [correction], uid=after['uid']), after)
            self.assertIsNone(AUDIT.temporal_row(table, None, [correction], uid='source:other'))
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                AUDIT.temporal_row(table, None, [correction, correction], uid=after['uid'])
            correction['before_' + key] = after
            with self.assertRaisesRegex(ValueError, 'exact source-eight'):
                AUDIT.temporal_row(table, None, [correction], uid=after['uid'])

    def test_wrong_uid_in_history_or_new_role_is_rejected(self):
        before = {'uid': 'source:parent', 'node_kind': 'MODEL'}
        with self.assertRaisesRegex(ValueError, 'another parent UID'):
            AUDIT.temporal_row('node_profiles', before, [], uid='source:other')
        correction = {'op': 'correct_role', 'uid': before['uid'], 'before_profile': before,
                      'after_profile': {'uid': 'source:other', 'node_kind': 'CLASS'}}
        with self.assertRaisesRegex(ValueError, 'another parent UID'):
            AUDIT.temporal_row('node_profiles', before, [correction])

    def test_unapproved_creation_of_absent_parent_role_fails_sql_audit(self):
        parent = {'uid': 'source:parent', 'component_id': 1}
        manifest = {'parent_components': {parent['uid']: {
            'before_node': parent, 'before_profile': None, 'before_normalization_role': None,
            'component_nodes': [parent], 'component_bridges': [], 'parent_edges': [],
            'parent_typed': []}}}
        with sqlite3.connect(':memory:') as con:
            con.row_factory = sqlite3.Row
            con.execute('CREATE TABLE nodes(uid TEXT, component_id INTEGER)')
            con.execute('CREATE TABLE node_profiles(uid TEXT, node_kind TEXT)')
            con.execute('CREATE TABLE normalization_roles(uid TEXT)')
            con.execute('INSERT INTO nodes VALUES (?, ?)', (parent['uid'], 1))
            AUDIT.verify_parent_component(con, manifest, parent['uid'])
            con.execute('INSERT INTO node_profiles VALUES (?, ?)', (parent['uid'], 'CLASS'))
            with self.assertRaisesRegex(ValueError, 'parent role declaration changed'):
                AUDIT.verify_parent_component(con, manifest, parent['uid'])


if __name__ == '__main__':
    unittest.main()
