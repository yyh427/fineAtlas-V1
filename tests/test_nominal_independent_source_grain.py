"""Independent controls for missing profiles, pending grain and view limits."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/audit_nominal_design_scope_repairs.py'
SPEC = importlib.util.spec_from_file_location('independent_source_grain_controls', SCRIPT)
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)


class IndependentSourceGrain(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.inputs = Path(self.temp.name)
        self.c = sqlite3.connect(':memory:'); self.c.row_factory = sqlite3.Row
        self.c.executescript('CREATE TABLE nodes(uid TEXT PRIMARY KEY,rank TEXT,domain TEXT,visibility TEXT,data TEXT);'
                            'CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,domain TEXT,source_uri TEXT,evidence_id TEXT,attributes TEXT);'
                            'CREATE TABLE normalization_roles(uid TEXT PRIMARY KEY,source_role TEXT,canonical_role TEXT,status TEXT,evidence_id TEXT,source TEXT,prior_profile TEXT);')
        self.node = {'uid': 'source:design', 'rank': '', 'domain': '', 'visibility': 'ACTIVE',
                     'data': A.dump({'description': 'A reusable named camera design.'})}
        self.c.execute('INSERT INTO nodes VALUES (:uid,:rank,:domain,:visibility,:data)', self.node)

    def tearDown(self):
        self.c.close(); self.temp.cleanup()

    def operation(self, target='MODEL', before=None, allowed_views=None):
        if before:
            self.c.execute('INSERT INTO node_profiles VALUES (:uid,:node_kind,:domain,:source_uri,:evidence_id,:attributes)', before)
        status = 'REVIEW' if target == 'UNKNOWN' else 'VERIFIED'
        kinds = {'MODEL': 'OWNED_NAMED_REUSABLE_DESIGN_PROGRAMME',
                 'INSTANCE': 'OWNED_NAMED_OPERATIONAL_PHYSICAL_INSTANCE',
                 'UNKNOWN': 'SOURCE_NOMINAL_OR_INDIVIDUAL_GRAIN_PENDING'}
        approval = {'uid': self.node['uid'], 'before_role': before['node_kind'] if before else 'CLASS',
                    'source_role_scope_kind': target, 'before_profile': before, 'before_normalization': None}
        if target == 'UNKNOWN':
            approval.update(after_role_status='REVIEW', allowed_views=[], quarantine_role_grain=True)
        review = {'accepted_source_scope_only': True, 'approved_source_role_corrections': [approval]}
        raw = A.dump(review); (self.inputs/'review.json').write_text(raw)
        proof = {'kind': 'SOURCE_REVIEWED_WHOLE_NOMINAL_DESIGN_SCOPE',
                 'world_identity_assertion': False, 'no_identity_merges': True, 'whole_subject_scope_review': True,
                 'before_node': self.node, 'native_record_sha256': A.sha(self.node['data']),
                 'source_review_locator': {'file': 'review.json', 'sha256': A.sha(raw)},
                 'source_scope_review_record': review, 'source_role': 'UNSPECIFIED', 'native_rank': '',
                 'source_role_scope_kind': kinds[target], 'role_status': status,
                 'source_witnesses': [{'uid': self.node['uid'], 'data_sha256': A.sha(self.node['data']),
                                       'field_path': 'description', 'statement': 'A reusable named camera design.'}]}
        if target == 'UNKNOWN': proof['allowed_views'] = []
        elif allowed_views is not None: proof['allowed_views'] = allowed_views
        eid = 'usability:' + A.sha(A.dump(proof))
        attrs = __import__('json').loads(before['attributes']) if before else {}
        attrs.update(source_role='UNSPECIFIED', native_rank='', role_status=status, role_evidence_id=eid)
        if target == 'UNKNOWN': attrs['allowed_views'] = []
        after = {'uid': self.node['uid'], 'node_kind': target, 'domain': '',
                 'source_uri': 'https://example.org/source', 'evidence_id': eid, 'attributes': A.dump(attrs)}
        norm = {'uid': self.node['uid'], 'source_role': 'UNSPECIFIED', 'canonical_role': target,
                'status': status, 'evidence_id': eid, 'source': A.SOURCE, 'prior_profile': A.dump(before or {})}
        return {'op': 'correct_role', 'uid': self.node['uid'], 'parent': self.node['uid'],
                'relation': 'ROLE_ADJUDICATION', 'classification_axis': 'source_grain',
                'source': A.SOURCE, 'uri': after['source_uri'], 'proof': proof,
                'before_profile': before, 'before_normalization_role': None,
                'after_profile': after, 'after_normalization_role': norm}

    def test_missing_profile_is_preserved_as_none_not_fabricated_history(self):
        op = self.operation()
        result = A.check_role_operation(self.c, self.inputs, op, False)
        self.assertEqual((result['before_role'], result['after_role']), ('CLASS', 'MODEL'))
        self.assertIsNone(A.row_at(self.c, 'node_profiles', self.node['uid']))
        op['after_normalization_role']['prior_profile'] = '{"node_kind":"CLASS"}'
        with self.assertRaisesRegex(ValueError, 'unrelated profile'):
            A.check_role_operation(self.c, self.inputs, op, False)

    def test_missing_profile_cannot_invent_a_previous_verified_role(self):
        op = self.operation()
        op['proof']['before_role'] = 'MODEL_FAMILY'
        with self.assertRaisesRegex(ValueError, 'historical role'):
            A.check_role_operation(self.c, self.inputs, op, False)

    def test_pending_grain_cannot_claim_verified_or_expand_views(self):
        op = self.operation('UNKNOWN')
        A.check_role_operation(self.c, self.inputs, op, False)
        op['proof']['role_status'] = 'VERIFIED'
        with self.assertRaisesRegex(ValueError, 'confidence'):
            A.check_role_operation(self.c, self.inputs, op, False)

    def test_pending_quarantine_requires_explicit_independent_source_decision(self):
        op = self.operation('UNKNOWN')
        op['proof']['allowed_views'] = ['taxonomy']
        with self.assertRaisesRegex(ValueError, 'quarantine'):
            A.check_role_operation(self.c, self.inputs, op, False)

    def test_verified_role_cannot_change_existing_view_restriction(self):
        prior = {'uid': self.node['uid'], 'node_kind': 'CLASS', 'domain': '', 'source_uri': 'retained',
                 'evidence_id': '', 'attributes': A.dump({'allowed_views': ['taxonomy']})}
        op = self.operation('MODEL', prior, [])
        with self.assertRaisesRegex(ValueError, 'loosen source view'):
            A.check_role_operation(self.c, self.inputs, op, False)

    def use_retained_source_approval(self, op, pending=False):
        target = op['after_profile']['node_kind']
        record = {'node': self.node, 'node_profiles': op['before_profile'],
                  'normalization_roles': None, 'edges': [], 'entity_relations': [], 'bridges': []}
        review = {'accepted_source_scope_only': True, 'approved_source_roles': [[self.node['uid'], target]],
                  ('complete_before_records' if pending else 'source_role_records'): {self.node['uid']: record}}
        if pending:
            review['cases'] = [{'uid': self.node['uid'], 'after_role_status': 'REVIEW',
                                'allowed_views': [], 'quarantine_role_grain': True}]
            op['proof']['quarantine_role_grain'] = True
        raw = A.dump(review); (self.inputs/'review.json').write_text(raw)
        op['proof']['source_scope_review_record'] = review
        op['proof']['source_review_locator']['sha256'] = A.sha(raw)
        eid = 'usability:' + A.sha(A.dump(op['proof']))
        op['after_profile']['evidence_id'] = eid
        attrs = __import__('json').loads(op['after_profile']['attributes'])
        attrs['role_evidence_id'] = eid
        op['after_profile']['attributes'] = A.dump(attrs)
        op['after_normalization_role']['evidence_id'] = eid

    def test_source_peer_approval_keeps_original_none_records(self):
        op = self.operation(); self.use_retained_source_approval(op)
        A.check_role_operation(self.c, self.inputs, op, False)
        review = op['proof']['source_scope_review_record']
        review['source_role_records'][self.node['uid']]['node_profiles'] = {'node_kind': 'CLASS'}
        raw = A.dump(review); (self.inputs/'review.json').write_text(raw)
        op['proof']['source_review_locator']['sha256'] = A.sha(raw)
        with self.assertRaisesRegex(ValueError, 'exact original role'):
            A.check_role_operation(self.c, self.inputs, op, False)

    def test_pending_peer_case_requires_exact_quarantine_flag(self):
        op = self.operation('UNKNOWN'); self.use_retained_source_approval(op, pending=True)
        A.check_role_operation(self.c, self.inputs, op, False)
        op['proof']['quarantine_role_grain'] = False
        with self.assertRaisesRegex(ValueError, 'quarantine'):
            A.check_role_operation(self.c, self.inputs, op, False)

    def test_individual_relationship_is_separate_from_class_or_family_inclusion(self):
        self.assertTrue(A.allowed('INSTANCE_OF', 'INSTANCE', 'CLASS'))
        self.assertFalse(A.allowed('IS_A', 'INSTANCE', 'CLASS'))
        self.assertFalse(A.allowed('NATIVE_DESIGN_PARENT', 'INSTANCE', 'MODEL_FAMILY'))
        self.assertFalse(A.allowed('DESIGN_TYPE_OF', 'UNKNOWN', 'CLASS'))

    def whole_object_pending_operation(self):
        op = self.operation('UNKNOWN')
        reason = 'Own retained scope mixes a physical object and its abstract configuration.'
        decision = {'uid': self.node['uid'], 'before_node': self.node,
                    'before_profiles': [], 'before_normalization_roles': [],
                    'after_role_status': 'REVIEW', 'allowed_views': [],
                    'quarantine_role_grain': True, 'scope_reason': reason,
                    'pending_whole_scope': 'Source sense separation remains unconfirmed.'}
        review = {'accepted_source_scope_only': True,
                  'approved_source_roles': [[self.node['uid'], 'UNKNOWN']], 'cases': [decision]}
        proof = op['proof']
        proof.update(source_role_scope_kind='SOURCE_WHOLE_OBJECT_GRAIN_PENDING',
                     quarantine_role_grain=True, scope_observation=reason,
                     source_scope_review_record=review)
        self.reseal_operation(op)
        return op

    def reseal_operation(self, op):
        proof = op['proof']
        raw = A.dump(proof['source_scope_review_record'])
        (self.inputs/'review.json').write_text(raw)
        proof['source_review_locator']['sha256'] = A.sha(raw)
        eid = 'usability:' + A.sha(A.dump(proof))
        op['after_profile']['evidence_id'] = eid
        attrs = __import__('json').loads(op['after_profile']['attributes'])
        attrs['role_evidence_id'] = eid
        op['after_profile']['attributes'] = A.dump(attrs)
        op['after_normalization_role']['evidence_id'] = eid

    def test_whole_object_pending_keeps_exact_source_case_and_missing_prior_rows(self):
        op = self.whole_object_pending_operation()
        A.check_role_operation(self.c, self.inputs, op, False)
        op['proof']['source_scope_review_record']['cases'][0]['before_profiles'] = [{'node_kind': 'CLASS'}]
        self.reseal_operation(op)
        with self.assertRaisesRegex(ValueError, 'exact original role'):
            A.check_role_operation(self.c, self.inputs, op, False)

    def test_whole_object_ambiguity_cannot_substitute_a_nominal_grain_rationale(self):
        op = self.whole_object_pending_operation()
        op['proof']['scope_observation'] = 'Only the name suggests a programme.'
        self.reseal_operation(op)
        with self.assertRaisesRegex(ValueError, 'exact independent scope decision'):
            A.check_role_operation(self.c, self.inputs, op, False)

    def test_whole_object_pending_requires_retained_unresolved_scope(self):
        op = self.whole_object_pending_operation()
        op['proof']['source_scope_review_record']['cases'][0]['pending_whole_scope'] = ''
        self.reseal_operation(op)
        with self.assertRaisesRegex(ValueError, 'exact independent scope decision'):
            A.check_role_operation(self.c, self.inputs, op, False)


if __name__ == '__main__':
    unittest.main()
