"""No duplicate executor; historical permissions require complete actual history."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from structure_ninth_source_temporal_contract import NinthMixin, require_current_sources, verified_path


class Base:
    def expected_original_subject_role(self, uid, role):
        return role
    def expected_assertion_status(self, current, original):
        return original

class Contract(NinthMixin, Base):
    pass


class TemporalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.p=Path(self.tmp.name)
        self.receipts=[]
        for name in ('owned','complete','nominal'):
            path=self.p/(name+'.json');path.write_text('{}');self.receipts.append(path)
        self.owned,self.complete,self.nominal=self.receipts
    def evidence(self,path):
        return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    def gates(self,wrong=False):
        calls=[]
        def nominal(*args):calls.append(('nominal',args));return {}
        def complete(*args):calls.append(('complete',args));return {'temporal_ninth_auditor':{'verified_source9_audit':self.evidence(self.owned if wrong else self.nominal)}}
        def owned(*args):calls.append(('owned',args));return {'complete_type_actual_audit':self.evidence(self.complete),'nominal_scope_actual_audit':self.evidence(self.nominal)}
        modules={}
        for name,api,func in [('structure_nominal_design_scope_delivery_guard','require_nominal_scope_receipt',nominal),('structure_ninth_complete_type_temporal_contract','require_temporal_ninth_complete_type_receipt',complete),('structure_ninth_owned_scope_temporal_contract','require_temporal_ninth_owned_scope_receipt',owned)]:
            module=types.ModuleType(name);setattr(module,api,func);modules[name]=module
        return modules,calls
    def test_supplied_receipts_verified_once_without_subprocess(self):
        modules,calls=self.gates()
        with patch.dict(sys.modules,modules),patch('subprocess.run',side_effect=AssertionError('duplicate executor')):
            require_current_sources(self.owned,self.complete,self.nominal,self.p/'db',self.p,'actual-revision')
        self.assertEqual([c[0]for c in calls],['nominal','complete','owned'])
        self.assertTrue(all(c[1][3]=='actual-revision' for c in calls))
    def test_individually_passing_receipts_cannot_cross_bind_another_stage(self):
        modules,_=self.gates(wrong=True)
        with patch.dict(sys.modules,modules),self.assertRaisesRegex(ValueError,'supplied exact actual SOURCE9'):
            require_current_sources(self.owned,self.complete,self.nominal,self.p/'db',self.p,'actual-revision')
    def test_changed_current_evidence_is_rejected(self):
        evidence=self.evidence(self.nominal);self.nominal.write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError,'bytes changed'):verified_path(evidence)
    def fixture(self):
        c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
        c.execute('CREATE TABLE usability_changes(stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT)')
        obj=object.__new__(Contract);obj.c=c
        before={'id':8,'child_uid':'c','parent_uid':'p','relation':'IS_A','status':'ACTIVE','data':'full','source':'old'}
        proof={'exact':'proof'}
        op={'before_assertion':before,'proof':proof,'content_sha256':hashlib.sha256(json.dumps({k:v for k,v in before.items()if k not in('id','status','reason')},sort_keys=True).encode()).hexdigest()}
        obj.ninth_reviews=[op]
        c.execute('INSERT INTO usability_changes VALUES(?,?,?,?,?,?)',('nominal_design_scope_repairs','class_scope_review','8',json.dumps(before),json.dumps({'status':'SOURCE_SCOPE_REVIEW'}),json.dumps(proof)))
        return c,obj,before
    def test_complete_class_before_and_actual_history_required(self):
        c,obj,before=self.fixture();self.addCleanup(c.close)
        self.assertEqual(obj.expected_assertion_status(dict(before,status='SOURCE_SCOPE_REVIEW'),'ACTIVE'),'SOURCE_SCOPE_REVIEW')
        with self.assertRaisesRegex(ValueError,'complete original'):
            obj.expected_assertion_status(dict(before,status='SOURCE_SCOPE_REVIEW',data='mutated'),'ACTIVE')
        c.execute('DELETE FROM usability_changes')
        with self.assertRaisesRegex(ValueError,'history is missing'):
            obj.expected_assertion_status(dict(before,status='SOURCE_SCOPE_REVIEW'),'ACTIVE')
    def test_same_direction_reviews_are_distinct_original_assertions(self):
        c,obj,before=self.fixture();self.addCleanup(c.close)
        other={**obj.ninth_reviews[0],'before_assertion':dict(before,id=9)};obj.ninth_reviews.append(other)
        self.assertEqual(obj.expected_assertion_status(dict(before,status='SOURCE_SCOPE_REVIEW'),'ACTIVE'),'SOURCE_SCOPE_REVIEW')
        with self.assertRaisesRegex(ValueError,'history is missing'):
            obj.expected_assertion_status(dict(before,id=9,status='SOURCE_SCOPE_REVIEW'),'ACTIVE')
    def test_unprofiled_history_cannot_invent_source_role(self):
        c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;self.addCleanup(c.close)
        c.executescript('CREATE TABLE node_profiles(uid TEXT,node_kind TEXT);CREATE TABLE normalization_roles(uid TEXT,status TEXT);CREATE TABLE usability_changes(stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT);')
        op={'before_profile':None,'before_normalization_role':None,'after_profile':{'uid':'u','node_kind':'MODEL'},'after_normalization_role':{'uid':'u','status':'VERIFIED'},'proof':{'before_node':{'rank':'named_refinement'},'before_role':'MODEL'}}
        c.execute('INSERT INTO node_profiles VALUES(?,?)',('u','MODEL'));c.execute('INSERT INTO normalization_roles VALUES(?,?)',('u','VERIFIED'))
        before={'profile':None,'normalization_role':None};after={'profile':op['after_profile'],'normalization_role':op['after_normalization_role']}
        def history():
            c.execute('DELETE FROM usability_changes');c.execute('INSERT INTO usability_changes VALUES(?,?,?,?,?,?)',('nominal_design_scope_repairs','role_source_adjudication','u',json.dumps(before),json.dumps(after),json.dumps(op['proof'])))
        history();obj=object.__new__(Contract);obj.c=c;obj.ninth_roles={'u':op}
        with self.assertRaisesRegex(ValueError,'unchanged original rank'):
            obj.expected_original_subject_role('u','MODEL')
        op['proof']['before_role']='CLASS';history()
        self.assertEqual(obj.expected_original_subject_role('u','MODEL'),'CLASS')

    def test_entire_earlier_sql_bodies_preserved(self):
        for suffix in ('structure_regression_repairs','complete_subject_scope_repairs'):
            old=(ROOT/'scripts'/('audit_temporal_eighth_'+suffix+'.py')).read_text()
            new=(ROOT/'scripts'/('audit_temporal_ninth_'+suffix+'.py')).read_text()
            start=old.index('    for op in ops:');end=old.index("    report =") if suffix=='structure_regression_repairs' else old.index("    report=")
            self.assertEqual(old[start:end],new[new.index('    for op in ops:'):new.index("    report =") if suffix=='structure_regression_repairs' else new.index("    report=")])

if __name__=='__main__':unittest.main()
