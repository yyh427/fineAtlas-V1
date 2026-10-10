"""Own jet-aircraft type scope must survive without promoting identity or wing range."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.structure_literal_jet_scope_repairs import SOURCE, literal_jet_aircraft_first_scope, parent_whole_jet_scope, validate_literal_jet_scope_repairs
from fineatlas.structure_regression_repairs import sha

class LiteralJetScopeContracts(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
        self.c.executescript('''CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,data TEXT,visibility TEXT,source TEXT,rank TEXT,component_id INTEGER);
            CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT);
            CREATE TABLE entity_relations(subject_uid TEXT,object_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);
            CREATE TABLE bridges(left_uid TEXT,right_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);''')
        self.statement='business jet aircraft'
        self.parent_statement='A jet aircraft (or simply jet) is an aircraft propelled by one or more jet engines. Jets are nearly always fixed-wing aircraft.'
        raws=[json.dumps({'description':self.statement}),json.dumps({'evidence_record':{'wikipedia_intro':self.parent_statement}})]
        self.c.executemany('INSERT INTO nodes VALUES(?,?,?,?,?,?,?)',[('model','Model',raws[0],'ACTIVE','publisher','model',1),('parent','jet aircraft',raws[1],'ACTIVE','publisher','',2)])
        self.c.executemany('INSERT INTO node_profiles VALUES(?,?)',[('model','MODEL'),('parent','CLASS')])
        self.manifest={'schema':'FINEATLAS_LITERAL_JET_SCOPE_REPAIRS_V1','parent_components':{'parent':{'uids':['parent'],'bridge_content_status_hashes':[]}}}
        self.op={'op':'link','uid':'model','parent':'parent','relation':'DESIGN_TYPE_OF','source':SOURCE,'uri':'urn:source:model','proof':{'world_identity_assertion':False,'no_identity_merges':True,'whole_subject_scope_review':True,'scope_observation':'Own first clause and complete parent range reviewed.','native_record_sha256':sha(raws[0]),'parent_native_record_sha256':sha(raws[1]),'source_witnesses':[{'uid':'model','field':'description','statement':self.statement,'data_sha256':sha(raws[0])},{'uid':'parent','field':'wikipedia_intro','statement':self.parent_statement,'data_sha256':sha(raws[1])}],'prior_assertions':[]}}
    def tearDown(self):self.c.close()
    def test_complete_literal_scope_accepts_broader_nonfixedwing_parent(self):
        validate_literal_jet_scope_repairs(self.c,self.manifest,[self.op])
    def test_historical_or_incidental_jet_is_not_owned_first_genus(self):
        self.assertFalse(literal_jet_aircraft_first_scope('attack aircraft prototype; first jet aircraft built in Japan','Model'))
        self.assertFalse(literal_jet_aircraft_first_scope('an aircraft that replaced a jet aircraft','Model'))
    def test_negation_and_parts_cannot_supply_jet_aircraft_scope(self):
        for statement in ('an engine for jet aircraft','a jet aircraft part','a toy jet aircraft','not a jet aircraft','software for jet aircraft','fictional jet aircraft'):
            self.assertFalse(literal_jet_aircraft_first_scope(statement,'Model'),statement)
    def test_different_subject_is_not_owned(self):
        self.assertFalse(literal_jet_aircraft_first_scope('Another model is a jet aircraft','Model'))
    def test_source_declared_proposal_is_design_type_not_production_claim(self):
        self.assertTrue(literal_jet_aircraft_first_scope('proposed general aviation jet aircraft by Publisher','Model'))
    def test_powered_fixed_wing_parent_does_not_replace_broad_jet_aircraft(self):
        self.assertFalse(parent_whole_jet_scope('an airplane powered by one or more jet engines','jet aircraft'))
    def test_identity_promotion_rejected(self):
        op=copy.deepcopy(self.op);op['proof']['world_identity_assertion']=True
        with self.assertRaisesRegex(ValueError,'identity'):validate_literal_jet_scope_repairs(self.c,self.manifest,[op])
    def test_source_role_change_rejected(self):
        self.c.execute("UPDATE node_profiles SET node_kind='CONFIGURATION' WHERE uid='model'")
        with self.assertRaises(ValueError):validate_literal_jet_scope_repairs(self.c,self.manifest,[self.op])
    def test_parent_model_is_not_class(self):
        self.c.execute("UPDATE node_profiles SET node_kind='MODEL' WHERE uid='parent'")
        with self.assertRaises(ValueError):validate_literal_jet_scope_repairs(self.c,self.manifest,[self.op])
    def test_source_scope_hash_change_rejected(self):
        self.c.execute("UPDATE nodes SET data='{}' WHERE uid='model'")
        with self.assertRaisesRegex(ValueError,'range changed'):validate_literal_jet_scope_repairs(self.c,self.manifest,[self.op])
    def test_changed_equivalence_component_rejected(self):
        self.c.execute("INSERT INTO nodes VALUES('plane','jet airplane','{}','ACTIVE','publisher','',2)")
        with self.assertRaisesRegex(ValueError,'component changed'):validate_literal_jet_scope_repairs(self.c,self.manifest,[self.op])
    def test_added_narrow_bridge_requires_new_scope_review(self):
        self.c.execute("INSERT INTO bridges VALUES('parent','narrow','SAME_CONCEPT','publisher','ACTIVE','{}')")
        with self.assertRaisesRegex(ValueError,'scope bridge changed'):validate_literal_jet_scope_repairs(self.c,self.manifest,[self.op])
    def test_prior_review_must_be_retained_exactly(self):
        op=copy.deepcopy(self.op);op['proof']['prior_assertions']=[{'subject_uid':'model','object_uid':'parent','relation':'DESIGN_TYPE_OF','source':'old','status':'SOURCE_SCOPE_REVIEW','content_sha256':'0'*64}]
        with self.assertRaisesRegex(ValueError,'declaration'):validate_literal_jet_scope_repairs(self.c,self.manifest,[op])
    def test_duplicate_operations_rejected(self):
        with self.assertRaisesRegex(ValueError,'unique'):validate_literal_jet_scope_repairs(self.c,self.manifest,[self.op,self.op])

if __name__=='__main__':unittest.main()
