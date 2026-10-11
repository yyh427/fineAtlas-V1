"""Activation cannot bypass original grain, parent role or declaration binding."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fineatlas.structure_complete_subject_scope_repairs import SOURCE, validate_complete_subject_scope_repairs
from fineatlas.structure_regression_repairs import sha

class SourceActivationContracts(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:'); self.c.row_factory = sqlite3.Row
        self.c.executescript('''CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,data TEXT,visibility TEXT,source TEXT,rank TEXT);
            CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT);
            CREATE TABLE entity_relations(subject_uid TEXT,object_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);
            CREATE TABLE edges(child_uid TEXT,parent_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);''')
        self.text = 'string instruments, or chordophones, are musical instruments that produce sound from vibrating strings'
        self.parent_text = 'any of various devices or contrivances that can be used to produce musical tones or sounds'
        raws = [json.dumps({'definition': self.text}), json.dumps({'definition': self.parent_text})]
        self.c.executemany('INSERT INTO nodes VALUES(?,?,?,?,?,?)', [('strings','strings',raws[0],'SOURCE_ONLY','publisher',''),('music','music',raws[1],'ACTIVE','publisher','')])
        self.c.executemany('INSERT INTO node_profiles VALUES(?,?)',[('strings','CLASS'),('music','CLASS')])
        self.manifest = {'schema':'FINEATLAS_COMPLETE_SUBJECT_SCOPE_REPAIRS_V1','source_class_activations':[{'uid':'strings','native_record_sha256':sha(raws[0]),'before_visibility':'SOURCE_ONLY','scope_decision':'ORDINARY_MUSICAL_CLASS_COMPLETE_INTENSIONAL_SCOPE','statement':self.text,'source_uri':'urn:source:strings'}]}
        self.op = {'op':'link','uid':'strings','parent':'music','relation':'IS_A','uri':'urn:source:strings','source':SOURCE,'proof':{'reviewed_rule':'COMPLETE_STRING_INSTRUMENT_MUSICAL_SCOPE','world_identity_assertion':False,'no_identity_merges':True,'whole_subject_scope_review':True,'scope_observation':'Whole source declares musical instruments.','native_record_sha256':sha(raws[0]),'parent_native_record_sha256':sha(raws[1]),'source_witnesses':[{'uid':'strings','field':'definition','statement':self.text,'data_sha256':sha(raws[0])},{'uid':'music','field':'definition','statement':self.parent_text,'data_sha256':sha(raws[1])}]}}
    def tearDown(self): self.c.close()
    def test_activation_only_operations_are_validated(self):
        validate_complete_subject_scope_repairs(self.c,self.manifest,[self.op])
    def test_activation_cannot_bypass_parent_class_grain(self):
        self.c.execute("UPDATE node_profiles SET node_kind='MODEL' WHERE uid='music'")
        with self.assertRaises(ValueError): validate_complete_subject_scope_repairs(self.c,self.manifest,[self.op])
    def test_activation_cannot_bypass_prior_review_content(self):
        op=copy.deepcopy(self.op); op['proof']['prior_edge']={'child_uid':'strings','parent_uid':'music','relation':'IS_A','source':'old','content_sha256':'0'*64,'status':'SOURCE_SCOPE_REVIEW'}
        with self.assertRaisesRegex(ValueError,'prior review'):validate_complete_subject_scope_repairs(self.c,self.manifest,[op])
    def test_activation_cannot_bypass_original_class_grain(self):
        self.c.execute("UPDATE node_profiles SET node_kind='MODEL' WHERE uid='strings'")
        with self.assertRaisesRegex(ValueError,'original ordinary class'):validate_complete_subject_scope_repairs(self.c,self.manifest,[self.op])
    def test_duplicate_activation_declarations_are_rejected(self):
        self.manifest['source_class_activations']*=2
        with self.assertRaisesRegex(ValueError,'unique'):validate_complete_subject_scope_repairs(self.c,self.manifest,[self.op])

if __name__=='__main__':unittest.main()
