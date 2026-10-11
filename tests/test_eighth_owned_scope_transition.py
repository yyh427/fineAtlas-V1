import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from structure_eighth_owned_scope_temporal_contract import verify_exact_retired_owned_link

class ExactLaterOwnedLinkTest(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row;self.c.executescript('CREATE TABLE entity_relations(id INTEGER,subject_uid TEXT,object_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);CREATE TABLE node_profiles(uid TEXT,node_kind TEXT,attributes TEXT);CREATE TABLE normalization_roles(uid TEXT,canonical_role TEXT,status TEXT);CREATE TABLE usability_changes(stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT);')
        oldproof={'whole_subject_scope_review':True};self.original={'op':'link','uid':'old','parent':'aircraft','relation':'DESIGN_TYPE_OF','source':'earlier own SOURCE','proof':oldproof}
        before={'id':7,'subject_uid':'old','object_uid':'aircraft','relation':'DESIGN_TYPE_OF','source':self.original['source'],'status':'ACTIVE','data':json.dumps({'admission_basis':oldproof})}
        self.review={'op':'review_typed_relation','uid':'old','parent':'aircraft','relation':'DESIGN_TYPE_OF','source':'later SOURCE','before_assertion':before,'after_status':'SOURCE_SCOPE_REVIEW','content_sha256':hashlib.sha256(json.dumps({k:v for k,v in before.items()if k not in('id','status','reason')},sort_keys=True).encode()).hexdigest(),'proof':{'review':'object grain'}}
        a={'uid':'old','node_kind':'UNKNOWN','attributes':json.dumps({'allowed_views':[],'role_status':'REVIEW'})};n={'uid':'old','canonical_role':'UNKNOWN','status':'REVIEW'};self.role={'op':'correct_role','uid':'old','before_profile':{'uid':'old','node_kind':'MODEL'},'before_normalization_role':None,'after_profile':a,'after_normalization_role':n,'proof':{'scope':'ambiguous physical/design'}}
        self.c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?)',tuple({**before,'status':'SOURCE_SCOPE_REVIEW'}.values()));self.c.execute('INSERT INTO node_profiles VALUES(?,?,?)',tuple(a.values()));self.c.execute('INSERT INTO normalization_roles VALUES(?,?,?)',tuple(n.values()))
        old={'profile':self.role['before_profile'],'normalization_role':None};after={'profile':a,'normalization_role':n}
        for kind,identifier,l,r,p in [('role_source_adjudication','old',old,after,self.role['proof']),('typed_scope_review','7',before,{'status':'SOURCE_SCOPE_REVIEW'},self.review['proof'])]:self.c.execute('INSERT INTO usability_changes VALUES(?,?,?,?,?,?)',('complete_owned_type_repairs',kind,identifier,json.dumps(l),json.dumps(r),json.dumps(p)))
        data={'admission_basis':{'original_assertion':before},'navigation_allowed':False,'allowed_views':[]};self.c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?)',(8,'old','aircraft','SOURCE_PHYSICAL_CLASS_REFERENCE','later SOURCE','SOURCE_DECLARED',json.dumps(data)))
    def tearDown(self):self.c.close()
    def test_exact_status_role_history_and_nonnav_fact_all_required(self):self.assertEqual(verify_exact_retired_owned_link(self.c,self.original,self.review,self.role)['historical_role'],'MODEL')
    def test_other_uid_or_original_source_proof_cannot_borrow_permission(self):
        wrong=copy.deepcopy(self.original);wrong['proof']={'other_scope':True}
        with self.assertRaises(ValueError):verify_exact_retired_owned_link(self.c,wrong,self.review,self.role)
    def test_current_verified_unknown_is_not_accepted(self):
        self.c.execute("UPDATE normalization_roles SET status='VERIFIED'")
        with self.assertRaises(ValueError):verify_exact_retired_owned_link(self.c,self.original,self.review,self.role)
    def test_source_physical_fact_cannot_be_deleted(self):
        self.c.execute('DELETE FROM entity_relations WHERE id=8')
        with self.assertRaisesRegex(ValueError,'non-navigation reference'):verify_exact_retired_owned_link(self.c,self.original,self.review,self.role)
    def test_full_history_cannot_be_partial(self):
        self.c.execute("UPDATE usability_changes SET evidence='{}'WHERE object_type='typed_scope_review'")
        with self.assertRaisesRegex(ValueError,'history'):verify_exact_retired_owned_link(self.c,self.original,self.review,self.role)
