"""Later reviews must retain precise old source rows and both mapping stages."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import structure_regression_temporal_contract as temporal
import coordinate_literal_jet_delivery as delivery


class ExactTemporalTransitions(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:'); self.addCleanup(self.c.close); self.c.row_factory=sqlite3.Row
        self.c.execute('CREATE TABLE usability_changes(stage,object_type,object_id,before_json,after_json,evidence)')
        self.contract=temporal.TemporalContract.__new__(temporal.TemporalContract); self.contract.c=self.c
        self.before={'id':41,'subject_uid':'child','object_uid':'parent','relation':'DESIGN_TYPE_OF',
                     'source':'original producer','status':'ACTIVE','reason':None,'data':'{"raw":1}','evidence_id':'old'}
        self.op={'op':'review_typed_relation','before_assertion':self.before,'after_status':'SOURCE_SCOPE_REVIEW',
                 'content_sha256':temporal.json_hash({k:v for k,v in self.before.items() if k not in ('id','status','reason')}),
                 'proof':{'counterexample':'whole scope'}}
        self.contract.reviews=[self.op]; self.contract.mappings=[]
        self.current=dict(self.before,status='SOURCE_SCOPE_REVIEW')
        self.c.execute('INSERT INTO usability_changes VALUES(?,?,?,?,?,?)',('owned_scope_repairs','typed_scope_review','41',
            json.dumps(self.before),json.dumps({'status':'SOURCE_SCOPE_REVIEW'}),json.dumps(self.op['proof'])))
    def test_exact_frozen_later_review_and_history_pass(self):
        self.assertEqual(self.contract.expected_assertion_status(self.current,'ACTIVE'),'SOURCE_SCOPE_REVIEW')
    def test_unrelated_assertion_has_no_permission(self):
        current=dict(self.current,id=42)
        self.assertEqual(self.contract.expected_assertion_status(current,'ACTIVE'),'ACTIVE')
    def test_changed_raw_source_data_never_sanctioned(self):
        current=dict(self.current,data='changed')
        with self.assertRaises(ValueError): self.contract.expected_assertion_status(current,'ACTIVE')
    def test_changed_reason_never_sanctioned(self):
        current=dict(self.current,reason='rewritten')
        with self.assertRaises(ValueError): self.contract.expected_assertion_status(current,'ACTIVE')
    def test_rejected_state_not_a_generic_exception(self):
        current=dict(self.current,status='REJECTED')
        with self.assertRaises(ValueError): self.contract.expected_assertion_status(current,'ACTIVE')
    def test_frozen_before_status_must_match_old_contract(self):
        with self.assertRaises(ValueError): self.contract.expected_assertion_status(self.current,'SOURCE_SCOPE_REVIEW')
    def test_missing_actual_history_blocks_permission(self):
        self.c.execute('DELETE FROM usability_changes')
        with self.assertRaises(ValueError): self.contract.expected_assertion_status(self.current,'ACTIVE')
    def test_wrong_history_proof_blocks_permission(self):
        self.c.execute('UPDATE usability_changes SET evidence=?',(json.dumps({'different':'proof'}),))
        with self.assertRaises(ValueError): self.contract.expected_assertion_status(self.current,'ACTIVE')
    def test_duplicate_permission_blocked(self):
        self.contract.reviews.append(copy.deepcopy(self.op))
        with self.assertRaises(ValueError): self.contract.expected_assertion_status(self.current,'ACTIVE')
    def test_join_proof_is_derived_not_a_raw_field(self):
        current=dict(self.current,proof='derived joined evidence')
        self.assertEqual(self.contract.expected_assertion_status(current,'ACTIVE'),'SOURCE_SCOPE_REVIEW')
    def test_explicit_dispatch_changes_only_the_two_additive_executors(self):
        coordinator=delivery.LiteralJetCoordinator.__new__(delivery.LiteralJetCoordinator)
        with patch.object(delivery.Coordinator,'cmd',side_effect=lambda script,*values,**kw:[script,*values]):
            self.assertEqual(coordinator.cmd('audit_structure_regression_repairs.py','--database','actual'),
                ['audit_temporal_structure_regression_repairs.py','--database','actual'])
            self.assertEqual(coordinator.cmd('audit_structure_library.py','--database','actual'),
                ['audit_structure_library.py','--database','actual'])
    def test_new_public_executor_preserves_every_other_job_byte_for_byte(self):
        scripts=Path(__file__).resolve().parents[1]/'scripts'
        original=(scripts/'run_structure_public_checks.py').read_text()
        actual=(scripts/'run_literal_jet_public_checks.py').read_text()
        self.assertEqual(actual,original.replace("cmd('audit_structure_regression_repairs.py'",
                                               "cmd('audit_temporal_structure_regression_repairs.py'"))


class ExactMappingTransitions(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:'); self.addCleanup(self.c.close); self.c.row_factory=sqlite3.Row
        self.c.execute('CREATE TABLE dataset_targets(dataset,class_id,target_uid)')
        self.c.execute('CREATE TABLE dataset_mapping_checks(dataset,class_id,status,reason)')
        self.c.execute('CREATE TABLE usability_changes(stage,object_type,object_id,before_json,after_json,evidence)')
        self.before={'dataset':'aircraft','class_id':'66','target_uid':'old'}
        self.check={'dataset':'aircraft','class_id':'66','status':'ANNOTATION_SCOPE_REVIEW','reason':'old exact reason'}
        self.after=dict(self.before,target_uid='new')
        self.after_check=dict(self.check,status='PRIMARY_SOURCE_CORROBORATED',reason='new primary scope')
        self.op={'op':'migrate_nominal_design_mapping','dataset':'aircraft','class_id':'66',
            'before_target':self.before,'before_check':self.check,'after_target':self.after,
            'after_check':self.after_check,'proof':{'scope':'nominal model'}}
        self.contract=temporal.TemporalContract.__new__(temporal.TemporalContract); self.contract.c=self.c
        self.contract.mappings=[self.op]
        self.review={'dataset':'aircraft','class_id':'66','target_record_sha256':temporal.json_hash(self.before),'reason':'old exact reason'}
        self.c.execute('INSERT INTO dataset_targets VALUES(?,?,?)',tuple(self.after.values()))
        self.c.execute('INSERT INTO dataset_mapping_checks VALUES(?,?,?,?)',tuple(self.after_check.values()))
        self.c.execute('INSERT INTO usability_changes VALUES(?,?,?,?,?,?)',('owned_scope_repairs','nominal_design_mapping','aircraft:66',
            json.dumps({'target':self.before,'check':self.check}),json.dumps({'target':self.after,'check':self.after_check}),json.dumps(self.op['proof'])))
    def test_exact_frozen_migration_with_actual_history_passes(self):
        self.assertEqual(self.contract.mapping_transition(self.review),self.op)
    def test_unrelated_mapping_never_gets_permission(self):
        self.assertIsNone(self.contract.mapping_transition(dict(self.review,class_id='67')))
    def test_wrong_original_review_record_blocked(self):
        with self.assertRaises(ValueError): self.contract.mapping_transition(dict(self.review,target_record_sha256='wrong'))
    def test_final_mapping_still_old_or_wrong_cannot_pass(self):
        self.c.execute('UPDATE dataset_targets SET target_uid="wrong"')
        with self.assertRaises(ValueError): self.contract.mapping_transition(self.review)
    def test_current_check_must_exactly_match_frozen_after(self):
        self.c.execute('UPDATE dataset_mapping_checks SET reason="different"')
        with self.assertRaises(ValueError): self.contract.mapping_transition(self.review)
    def test_old_review_reason_cannot_be_rewritten_in_before(self):
        self.op['before_check']=dict(self.check,reason='invented')
        with self.assertRaises(ValueError): self.contract.mapping_transition(self.review)
    def test_missing_actual_later_mapping_history_blocks(self):
        self.c.execute('DELETE FROM usability_changes')
        with self.assertRaises(ValueError): self.contract.mapping_transition(self.review)


if __name__=='__main__': unittest.main()
