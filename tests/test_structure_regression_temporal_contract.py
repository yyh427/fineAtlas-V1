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
        directory=Path(__file__).resolve().parent
        coordinator.c={'primary_snapshots_directory':str(directory)}
        with patch.object(delivery.Coordinator,'cmd',side_effect=lambda script,*values,**kw:[script,*values]):
            self.assertEqual(coordinator.cmd('audit_structure_regression_repairs.py','--database','actual'),
                ['audit_temporal_structure_regression_repairs.py','--database','actual','--primary-snapshots-dir',directory])
            self.assertEqual(coordinator.cmd('audit_structure_library.py','--database','actual'),
                ['audit_structure_library.py','--database','actual'])
    def test_new_public_executor_preserves_every_other_job_byte_for_byte(self):
        scripts=Path(__file__).resolve().parents[1]/'scripts'
        original=(scripts/'run_structure_public_checks.py').read_text()
        actual=(scripts/'run_literal_jet_public_checks.py').read_text()
        expected=original.replace("cmd('audit_structure_regression_repairs.py'","cmd('audit_temporal_structure_regression_repairs.py'")
        expected=expected.replace("cmd('audit_resumed_source_preservation.py'","cmd('audit_owned_source_preservation.py'")
        expected=expected.replace('registered=required_deltas(a.inputs,a.code)',
            "registered=required_deltas(a.inputs,a.code)\nfrom dataclasses import replace\nfrom structure_subject_scope_temporal_contract import require_temporal_subject_receipt\nregistered=[replace(spec,auditor='audit_temporal_complete_subject_scope_repairs.py') if spec.name=='complete-subject-scope' else spec for spec in registered]")
        expected=expected.replace(" validate_delta_receipt(spec,report,a.database,a.inputs,d['database_revision'],a.code)",
            " validate_delta_receipt(spec,report,a.database,a.inputs,d['database_revision'],a.code)\n if spec.name=='complete-subject-scope':require_temporal_subject_receipt(report,a.database,a.inputs,d['database_revision'],a.code)")
        expected=expected.replace('from structure_delivery_source_guard import validate_source_preservation',
                                  'from structure_owned_source_guard import validate_source_preservation')
        expected=expected.replace("'legacy-dispositions'):p.add_argument", "'legacy-dispositions','regression-support-registry','primary-snapshots-dir'):p.add_argument")
        expected=expected.replace("def cmd(script,*args):return [str(a.python),'-B',str(a.code/'scripts'/script),*map(str,args)]",
            "def cmd(script,*args):\n if script in {'audit_owned_source_preservation.py','audit_temporal_structure_regression_repairs.py','audit_temporal_complete_subject_scope_repairs.py'}:args=(*args,'--primary-snapshots-dir',a.primary_snapshots_dir)\n return [str(a.python),'-B',str(a.code/'scripts'/script),*map(str,args)]")
        expected=expected.replace("from resume_structure_repairs import validate_resumed_parent_independence\nparent_proof=validate_resumed_parent_independence(a.primary_build,a.reproduction_build)\naccepted=read(a.acceptance)",
            "from portable_structure_lineage import validate_portable_parent_independence\nfrom structure_regression_support import PortableRegressionSupport\naccepted=read(a.acceptance)\nsupport=PortableRegressionSupport(a.regression_support_registry)\nparent_proof=validate_portable_parent_independence(support,a.primary_build,a.reproduction_build,accepted)")
        expected=expected.replace("cmd('audit_legacy_pair_regressions.py'","cmd('audit_portable_legacy_pair_regressions.py'")
        expected=expected.replace("'--output',a.output/'legacy-regressions'))","'--output',a.output/'legacy-regressions','--support-registry',a.regression_support_registry))")
        self.assertEqual(actual,expected)


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


class TemporalDocumentaryBinding(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.inputs=self.root/'inputs';self.inputs.mkdir()
        self.directory=self.root/'snapshots';self.directory.mkdir()
        for name in (temporal.REFERENCE,'structure_owned_scope_repairs.json'):(self.inputs/name).write_text('{}')
        self.owned=self.root/'owned.json';self.owned.write_text('{}');self.report=self.root/'temporal.json'
        self.value={'pass':True,'preflight_only':False,'errors':[],'database_revision':'revision',
            'database':str(self.root/'actual.sqlite'),'original_contract_fully_checked':True,
            'temporal_contract':'FINEATLAS_EXACT_LATER_SCOPE_TRANSITIONS_V1',
            'temporal_parent_reference_sha256':temporal.sha((self.inputs/temporal.REFERENCE).read_bytes()),
            'owned_manifest_sha256':temporal.sha((self.inputs/'structure_owned_scope_repairs.json').read_bytes()),
            'owned_actual_audit':{'path':str(self.owned),'sha256':temporal.sha(self.owned.read_bytes())},
            'primary_snapshots_dir':str(self.directory)}
    def validate(self,actual):
        self.report.write_text(json.dumps(self.value))
        with patch.object(temporal,'require_owned_scope_receipt',return_value=actual):
            return temporal.require_temporal_receipt(self.report,self.root/'actual.sqlite',self.inputs,'revision')
    def test_actual_later_and_temporal_source_directory_agree(self):
        self.assertTrue(self.validate({'primary_snapshots_dir':str(self.directory)})['pass'])
    def test_missing_temporal_source_binding_is_not_accepted(self):
        del self.value['primary_snapshots_dir']
        with self.assertRaises(ValueError):self.validate({'primary_snapshots_dir':str(self.directory)})
    def test_other_host_source_directory_cannot_replace_same_audited_bytes(self):
        elsewhere=self.root/'old-host-sources';elsewhere.mkdir()
        with self.assertRaises(ValueError):self.validate({'primary_snapshots_dir':str(elsewhere)})
