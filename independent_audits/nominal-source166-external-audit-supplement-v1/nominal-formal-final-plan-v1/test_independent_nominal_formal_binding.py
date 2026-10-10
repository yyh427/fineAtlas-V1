"""Formal observers distinguish real four-stage reuse from six-stage semantics."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest

import independent_nominal_formal_binding as binding
import run_final_nominal_formal_external_audit as runner

HERE=Path(__file__).resolve().parent

class FormalBindings(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.old=self.root/'source';self.new=self.root/'formal';self.old.mkdir();self.new.mkdir()
        for directory,version in((self.old,'1.11.0rc1'),(self.new,'1.11.0')):
            (directory/'__init__.py').write_text("__version__ = '"+version+"'\n")
            (directory/'pyproject.toml').write_text('version = "'+version+'"\n')
            (directory/'review_release.json').write_text(json.dumps({'version':'v'+version,'semantic':'same'}))
        self.old_files={name:self.old/name for name in('__init__.py','pyproject.toml','review_release.json')}
        self.new_files={name:self.new/name for name in self.old_files}
        def inventory(files):return {'code':{'src/fineatlas/__init__.py':binding.digest(files['__init__.py']),'scripts/same.py':'same'},'packaging':{'pyproject.toml':binding.digest(files['pyproject.toml'])},'inputs':{'review_release.json':binding.digest(files['review_release.json']),'same.json':'same'}}
        self.old_freeze=inventory(self.old_files);self.new_freeze=inventory(self.new_files)
    def check_versions(self):binding.version_literals(self.old_files,self.new_files,self.old_freeze,self.new_freeze,'v1.11.0')
    def test_exact_three_literal_changes_pass(self):self.check_versions()
    def test_semantic_sdk_source_change_is_rejected(self):
        self.new_freeze['code']['scripts/same.py']='different'
        with self.assertRaises(AssertionError):self.check_versions()
    def test_extra_sdk_module_is_rejected(self):
        self.new_freeze['code']['scripts/new.py']='new'
        with self.assertRaises(AssertionError):self.check_versions()
    def test_rehashed_sdk_body_change_is_not_a_version_change(self):
        self.new_files['__init__.py'].write_text("__version__ = '1.11.0'\nSEMANTIC=True\n");self.new_freeze['code']['src/fineatlas/__init__.py']=binding.digest(self.new_files['__init__.py'])
        with self.assertRaises(AssertionError):self.check_versions()
    def test_rehashed_input_scope_change_is_not_a_version_change(self):
        self.new_files['review_release.json'].write_text(json.dumps({'version':'v1.11.0','semantic':'changed'}));self.new_freeze['inputs']['review_release.json']=binding.digest(self.new_files['review_release.json'])
        with self.assertRaises(AssertionError):self.check_versions()
    def test_rehashed_packaging_dependency_change_is_rejected(self):
        self.new_files['pyproject.toml'].write_text('version = "1.11.0"\ndependencies=["new"]\n');self.new_freeze['packaging']['pyproject.toml']=binding.digest(self.new_files['pyproject.toml'])
        with self.assertRaises(AssertionError):self.check_versions()
    def test_same_version_cannot_claim_formal_promotion(self):
        self.new_freeze=copy.deepcopy(self.old_freeze)
        with self.assertRaises(AssertionError):self.check_versions()
    def test_actual_four_stage_contract_is_not_six_stage(self):
        row={'schema':'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1','complete':True,'pass':True,'semantic_reuse_only':True,'requires_independent_acceptance':True,'build_id':'formal','started_utc':'start','ended_utc':'end','required_stages':list(binding.NOMINAL_STAGES)}
        path=self.root/'build_complete.json';path.write_text(json.dumps(row))
        with self.assertRaises(AssertionError):binding.exact_formal_receipt(path)
    def actual_formal_fixture(self):
        path=self.root/'build_complete.json'
        states={name:{'status':'PASS','result':{}}for name in binding.FORMAL_STAGES}
        states[binding.FORMAL_STAGES[0]]['result']={'graphs_recomputed':False,'parent_revision':'actual-source9','source_sha256':'actual-source-sha'}
        states[binding.FORMAL_STAGES[-1]]['result']={'source_unchanged':True,'revision':'actual-formal'}
        promotion={'release':'v1.11.0','revision':'actual-formal','manifest':{'promotion':{'parent_candidate_revision':'actual-source9','semantic_graph_recomputed':False,'browse_indexes_rebuilt':True,'allowed_deltas':['review_release.version','SDK __version__ literal','packaging version literal']}}}
        complete={'complete':True,'pass':True,'source_unchanged':True,'requires_full_new_acceptance_and_public_download':True,'database_revision':'actual-formal','source_sha256':'actual-source-sha','release':'v1.11.0'}
        for name,value in(('build_status',states),('started_fingerprints',self.new_freeze),('promotion_metadata',promotion),('promotion_complete',complete)):(self.root/(name+'.json')).write_text(json.dumps(value))
        row={'schema':'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1','complete':True,'pass':True,'semantic_reuse_only':True,'requires_independent_acceptance':True,'build_id':'actual-formal-id','started_utc':'start','ended_utc':'end','revision':'actual-formal','release':'v1.11.0','source_sha256':'actual-source-sha','build_status_sha256':binding.digest(self.root/'build_status.json'),'started_fingerprints_sha256':binding.digest(self.root/'started_fingerprints.json')}
        path.write_text(json.dumps(row));return path,row,states
    def test_original_four_stage_format_without_six_stage_fields_passes(self):
        path,row,states=self.actual_formal_fixture()
        self.assertNotIn('required_stages',binding.exact_formal_receipt(path)[0])
    def test_fake_four_stage_semantic_recomputation_is_rejected_even_rehashed(self):
        path,row,states=self.actual_formal_fixture();states[binding.FORMAL_STAGES[0]]['result']['graphs_recomputed']=True
        (self.root/'build_status.json').write_text(json.dumps(states));row['build_status_sha256']=binding.digest(self.root/'build_status.json');path.write_text(json.dumps(row))
        with self.assertRaises(AssertionError):binding.exact_formal_receipt(path)
    def test_formal_four_stages_cannot_hide_a_repair_fifth_stage(self):
        path,row,states=self.actual_formal_fixture();states['nominal_design_scope_repairs']={'status':'PASS','result':{}}
        (self.root/'build_status.json').write_text(json.dumps(states));row['build_status_sha256']=binding.digest(self.root/'build_status.json');path.write_text(json.dumps(row))
        with self.assertRaises(AssertionError):binding.exact_formal_receipt(path)
    def test_semantic_candidate_receipt_cannot_claim_formal_reuse(self):
        path,row,states=self.actual_formal_fixture();row['semantic_reuse_only']=False;path.write_text(json.dumps(row))
        with self.assertRaises(AssertionError):binding.exact_formal_receipt(path)
    def test_pending_formal_plan_cannot_execute(self):
        with self.assertRaises(AssertionError):runner.authorize({'execution_authorized':False},'local')
    def test_candidate_plan_cannot_claim_formal_status(self):
        with self.assertRaises(AssertionError):runner.authorize({'execution_authorized':True,'status':'READY_ACTUAL_NOMINAL_FINAL_CHILD'},'local')
    def test_full_semantic_observer_functions_are_exactly_preserved(self):
        candidate=HERE.parent/'nominal-design-scope-final-plan-v1/independent_nominal_design_scope_final_interface_audit.py'
        formal=HERE/'independent_nominal_formal_final_interface_audit.py'
        def methods(path):
            tree=ast.parse(path.read_text());top={n.name:ast.dump(n,include_attributes=False)for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))and n.name!='main'}
            main=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='main')
            nested={n.name:ast.dump(n,include_attributes=False)for n in main.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
            return top,nested
        self.assertEqual(methods(candidate),methods(formal))

if __name__=='__main__':unittest.main()
