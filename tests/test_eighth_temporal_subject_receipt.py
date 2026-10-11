import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import structure_eighth_subject_scope_temporal_contract as contract


class EighthTemporalReceiptTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.inputs=self.root/'inputs';self.inputs.mkdir();self.code=self.root/'code';(self.code/'scripts').mkdir(parents=True)
        names=('audit_temporal_eighth_complete_subject_scope_repairs.py','structure_eighth_subject_scope_temporal_contract.py','audit_complete_owned_type_repairs.py')
        for name in names:(self.code/'scripts'/name).write_text('immutable code\n')
        self.manifest={'operations_file':'ops.jsonl','completed_parent_binding':{'database_revision':'parent'}}
        (self.inputs/'structure_complete_owned_type_repairs.json').write_text(json.dumps(self.manifest));(self.inputs/'ops.jsonl').write_text(json.dumps({'op':'correct_role'})+'\n'+json.dumps({'op':'review_typed_relation'})+'\n');(self.inputs/contract.REFERENCE).write_text(json.dumps({'parent_revision':'parent'}));self.actual=self.root/'actual.json';self.actual.write_text('{}')
        self.report={'eighth_temporal_subject_contract':'FINEATLAS_EXACT_COMPLETE_OWNED_TYPE_SUBJECT_TRANSITIONS_V1','original_subject_scope_checks_preserved':True,'complete_type_manifest_sha256':contract.sha((self.inputs/'structure_complete_owned_type_repairs.json').read_bytes()),'complete_type_temporal_reference_sha256':contract.sha((self.inputs/contract.REFERENCE).read_bytes()),'complete_type_actual_audit':{'path':str(self.actual),'sha256':contract.sha(self.actual.read_bytes())},'owned_actual_audit':{'path':str(self.actual),'sha256':contract.sha(self.actual.read_bytes())},'later_complete_type_role_permissions':1,'later_complete_type_typed_permissions':1}
        self.db=self.root/'database.sqlite';c=sqlite3.connect(self.db);c.execute('CREATE TABLE metadata(key TEXT,value TEXT)');meta={'structure_complete_type_resume_parent':{'parent_revision':'parent'},'structure_frozen_build_manifest':{'inputs':{contract.REFERENCE:contract.sha((self.inputs/contract.REFERENCE).read_bytes())},'code':{'scripts/'+n:contract.sha((self.code/'scripts'/n).read_bytes())for n in names}}};c.executemany('INSERT INTO metadata VALUES(?,?)',[(k,json.dumps(v))for k,v in meta.items()]);c.commit();c.close()
    def tearDown(self):self.tmp.cleanup()
    def invoke(self):
        with patch('structure_subject_scope_temporal_contract.require_temporal_subject_receipt',return_value=self.report)as old,patch('structure_complete_owned_type_delivery_guard.require_complete_type_receipt')as actual,patch('structure_eighth_owned_scope_temporal_contract.require_temporal_eighth_owned_scope_receipt')as current_owned:
            result=contract.require_temporal_eighth_subject_receipt(self.root/'report.json',self.db,self.inputs,'final',self.code);old.assert_called_once();actual.assert_called_once();current_owned.assert_called_once();return result
    def test_delegates_entire_historical_gate_and_exact_current_source_gate(self):self.assertIs(self.invoke(),self.report)
    def test_parent_or_current_code_cannot_be_relabelled(self):
        (self.inputs/contract.REFERENCE).write_text(json.dumps({'parent_revision':'other'}))
        with self.assertRaises(ValueError):self.invoke()
    def test_historical_permission_census_cannot_waive_unlisted_reviews(self):
        self.report['later_complete_type_typed_permissions']=2
        with self.assertRaisesRegex(ValueError,'inventory'):self.invoke()
    def test_actual_eighth_receipt_bytes_cannot_change(self):
        self.actual.write_text('{"pass":true}')
        with self.assertRaisesRegex(ValueError,'evidence changed'):self.invoke()
    def test_failed_original_gate_is_not_converted_to_current_success(self):
        with patch('structure_subject_scope_temporal_contract.require_temporal_subject_receipt',side_effect=ValueError('old SOURCE failed')):
            with self.assertRaisesRegex(ValueError,'old SOURCE failed'):contract.require_temporal_eighth_subject_receipt(self.root/'report.json',self.db,self.inputs,'final',self.code)

class SubjectExecutorSingleInvocationTest(unittest.TestCase):
    def test_shared_executor_creates_source8_once_and_report_is_reused(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);mf=root/'manifest.json';mf.write_text('{}');db=root/'database.sqlite';db.touch()
            value=contract.EighthSubjectTemporalContract.__new__(contract.EighthSubjectTemporalContract);value.database=db;value.inputs=root;value.output=root/'audit.json';value.eighth_report=root/'audit-complete-type-actual.json';value.eighth_manifest_path=mf;value.eighth_manifest={'operations_sha256':'ops'};value.eighth_operations=[{}];value.meta={'database_revision':'final'}
            def actual_executor(obj):
                self.assertFalse(obj.eighth_report.exists())
                obj.eighth_report.write_text(json.dumps({'schema':'FINEATLAS_INDEPENDENT_COMPLETE_OWNED_TYPE_AUDIT_V1','pass':True,'preflight_only':False,'errors':[],'candidate_acceptance':True,'database_revision':'final','database':str(db),'manifest_sha256':contract.sha(mf.read_bytes()),'operations_sha256':'ops','operation_count':1}))
            with patch('structure_eighth_owned_scope_temporal_contract.run_eighth_owned_actual_audits',side_effect=actual_executor)as executor,patch.object(contract.subprocess,'run',side_effect=AssertionError('Duplicate external SOURCE8 execution')):
                value.run_owned_actual_audit();executor.assert_called_once_with(value)
