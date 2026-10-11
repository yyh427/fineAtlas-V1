"""A historical third-stage PASS cannot stand for a final temporal audit."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import structure_subject_scope_temporal_contract as subject


class SubjectReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.inputs=self.root/'inputs';self.inputs.mkdir()
        self.code=self.root/'code';(self.code/'scripts').mkdir(parents=True)
        script=self.code/'scripts/audit_complete_subject_scope_repairs.py';script.write_text('# original\n')
        self.operations=self.inputs/'ops.jsonl';self.operations.write_text('{"relation":"DESIGN_TYPE_OF"}\n')
        self.manifest=self.inputs/'structure_complete_subject_scope_repairs.json'
        self.manifest.write_text(json.dumps({'operations_file':'ops.jsonl','operations_sha256':subject.sha(self.operations.read_bytes())}))
        receipt={'schema':'FINEATLAS_INDEPENDENT_COMPLETE_SUBJECT_SCOPE_AUDIT_V1','pass':True,
            'preflight_only':False,'errors':[],'database_revision':'actual-parent','operations':{'DESIGN_TYPE_OF':1},
            'operation_count':1,'manifest_sha256':subject.sha(self.manifest.read_bytes()),'operations_sha256':subject.sha(self.operations.read_bytes())}
        self.reference={'parent_revision':'actual-parent','subject_audit_receipt_text':json.dumps(receipt),
            'subject_audit_receipt_sha256':subject.sha(json.dumps(receipt)),
            'original_subject_auditor_sha256':subject.sha(script.read_bytes()),
            'original_subject_manifest_sha256':subject.sha(self.manifest.read_bytes())}
    def validate(self):return subject.validate_subject_parent_reference(self.reference,self.inputs,self.code)
    def replace_receipt(self,**changes):
        value=json.loads(self.reference['subject_audit_receipt_text']);value.update(changes)
        self.reference['subject_audit_receipt_text']=json.dumps(value)
        self.reference['subject_audit_receipt_sha256']=subject.sha(json.dumps(value))
    def test_exact_actual_original_third_parent_pass(self):self.assertTrue(self.validate()['pass'])
    def test_missing_original_third_actual_receipt_blocked(self):
        del self.reference['subject_audit_receipt_text']
        with self.assertRaises(ValueError):self.validate()
    def test_preflight_is_not_historical_actual_pass(self):
        self.replace_receipt(preflight_only=True)
        with self.assertRaises(ValueError):self.validate()
    def test_wrong_historical_revision_blocked(self):
        self.replace_receipt(database_revision='different')
        with self.assertRaises(ValueError):self.validate()
    def test_old_failed_audit_not_sanctioned(self):
        self.replace_receipt(pass_=False,errors=['wrong scope'])
        with self.assertRaises(ValueError):self.validate()
    def test_original_whole_census_cannot_be_partial(self):
        self.replace_receipt(operation_count=0,operations={})
        with self.assertRaises(ValueError):self.validate()
    def test_original_auditor_code_hash_preserved(self):
        (self.code/'scripts/audit_complete_subject_scope_repairs.py').write_text('changed')
        with self.assertRaises(ValueError):self.validate()
    def test_parent_receipt_text_hash_cannot_change(self):
        self.reference['subject_audit_receipt_sha256']='wrong'
        with self.assertRaises(ValueError):self.validate()
    def test_plain_1978_pass_cannot_satisfy_final_temporal_guard(self):
        with patch.object(subject,'validate_delta_receipt',return_value={'pass':True}):
            with self.assertRaises(ValueError):subject.require_temporal_subject_receipt('r','d','i','actual')
    def test_full_temporal_guard_must_also_validate_owned_actual_receipt(self):
        report={'temporal_subject_contract':'FINEATLAS_EXACT_LATER_COMPLETE_SUBJECT_TRANSITIONS_V1',
                'original_subject_contract_fully_checked':True}
        with patch.object(subject,'validate_delta_receipt',return_value=report),patch.object(subject,'require_temporal_receipt',side_effect=ValueError('missing owned actual')):
            with self.assertRaisesRegex(ValueError,'owned actual'):subject.require_temporal_subject_receipt('r','d','i','actual')


if __name__=='__main__':unittest.main()
