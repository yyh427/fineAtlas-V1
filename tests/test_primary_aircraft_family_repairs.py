"""Documented family direction, physical range, canonical cycles and attribution."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.structure_primary_aircraft_family_repairs import SOURCE, validate_primary_aircraft_family_repairs, validate_proposed_component_cycles, own_physical_genus, owned_twinjet_scope
from fineatlas.structure_regression_repairs import sha

class PrimaryAircraftScopeContracts(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
        self.c.executescript('''CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,data TEXT,visibility TEXT,source TEXT,rank TEXT,component_id INTEGER);
        CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT);
        CREATE TABLE entity_relations(subject_uid TEXT,object_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);
        CREATE TABLE bridges(left_uid TEXT,right_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);
        CREATE TABLE edges(child_uid TEXT,parent_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);''')
        for uid,label,component,rank in [('child','Atlas-100',1,'model'),('parent','Atlas',2,'model_family')]:
            self.c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?)',(uid,label,json.dumps({'description':'airliner model'if uid=='child'else'airliner family'}),'ACTIVE','publisher',rank,component))
            self.c.execute('INSERT INTO node_profiles VALUES(?,?)',(uid,'MODEL'if uid=='child'else'MODEL_FAMILY'))
        self.doc={'source_uri':'https://producer.test/designs','sha256':'a'*64}
        self.fact={'verdict':'PASS','relation':'NATIVE_DESIGN_PARENT','child_nominal_names':['Atlas-100'],'parent_nominal_name':'Atlas','parent_role':'MODEL_FAMILY','allowed_child_roles':['MODEL'],'scope_observation':'Whole manufacturer design list names Atlas-100 within Atlas.','primary_source_locators':[{'document_id':'official','locator':'Complete model list','factual_scope_declaration':{'whole_parent_name':'Atlas','whole_named_design_members':['Atlas-100']}}]}
        self.manifest={'schema':'FINEATLAS_PRIMARY_AIRCRAFT_FAMILY_REPAIRS_V1','operation_count':1,'reviewed_scope_facts':{'scope':self.fact},'primary_documents':{'official':self.doc},'accepted_design_object_sources':['publisher'],'identity_components':{'child':{'uids':['child'],'bridge_content_status_hashes':[]},'parent':{'uids':['parent'],'bridge_content_status_hashes':[]}}}
        self.op={'op':'link','uid':'child','parent':'parent','relation':'NATIVE_DESIGN_PARENT','source':SOURCE,'uri':self.doc['source_uri'],'proof':{'whole_nominal_design_scope_review':True,'world_identity_assertion':False,'dataset_mapping_promotion':False,'no_identity_merges':True,'primary_scope_fact_id':'scope','primary_scope_fact':self.fact,'primary_documents':{'official':self.doc},'prior_assertions':[],'source_witnesses':[]}}
        for uid,key in [('child','native_record_sha256'),('parent','parent_native_record_sha256')]:
            raw=self.c.execute('SELECT data FROM nodes WHERE uid=?',(uid,)).fetchone()[0];self.op['proof'][key]=sha(raw);self.op['proof']['source_witnesses'].append({'uid':uid,'field':'description','statement':json.loads(raw)['description'],'data_sha256':sha(raw)})
    def tearDown(self):self.c.close()
    def validate(self):validate_primary_aircraft_family_repairs(self.c,self.manifest,[self.op])
    def test_direction_does_not_merge_family_identity(self):self.validate()
    def test_wrong_producer_uri_rejected(self):
        self.op['uri']='https://another.test/design';self.assertRaises(ValueError,self.validate)
    def test_visual_identity_promotion_rejected(self):
        self.op['proof']['world_identity_assertion']=True;self.assertRaises(ValueError,self.validate)
    def test_author_mapping_promotion_rejected(self):
        self.op['proof']['dataset_mapping_promotion']=True;self.assertRaises(ValueError,self.validate)
    def test_changed_raw_source_rejected(self):
        self.c.execute("UPDATE nodes SET data='{}'WHERE uid='child'");self.assertRaises(ValueError,self.validate)
    def test_changed_source_role_rejected(self):
        self.c.execute("UPDATE node_profiles SET node_kind='DATASET_CATEGORY'WHERE uid='child'");self.assertRaises(ValueError,self.validate)
    def test_partial_or_homonymous_document_names_rejected(self):
        self.fact['child_nominal_names']=['Atlas-100ER'];self.assertRaises(ValueError,self.validate)
    def test_old_withdrawal_history_is_not_overwritten(self):
        self.op['proof']['prior_assertions']=[{'subject_uid':'child','object_uid':'parent','relation':'NATIVE_DESIGN_PARENT','source':'old','status':'SOURCE_SCOPE_REVIEW','content_sha256':'0'*64}];self.assertRaises(ValueError,self.validate)
    def test_boolean_count_is_not_valid_manifest_count(self):
        self.manifest['operation_count']=True;self.assertRaises(ValueError,self.validate)
    def test_duplicate_assertions_rejected(self):
        self.assertRaises(ValueError,validate_primary_aircraft_family_repairs,self.c,self.manifest,[self.op,self.op])
    def test_two_new_directions_cannot_close_batch_cycle(self):
        ops=[{'uid':'child','parent':'parent','relation':'NATIVE_DESIGN_PARENT'},{'uid':'parent','parent':'child','relation':'NATIVE_DESIGN_PARENT'}]
        self.assertRaises(ValueError,validate_proposed_component_cycles,self.c,ops)
    def test_existing_peer_direction_cannot_close_canonical_cycle(self):
        self.c.execute("INSERT INTO nodes VALUES('peer','Atlas peer','{}','ACTIVE','publisher','model_family',2)")
        self.c.execute("INSERT INTO node_profiles VALUES('peer','MODEL_FAMILY')")
        self.c.execute("INSERT INTO entity_relations VALUES('peer','child','NATIVE_DESIGN_PARENT','existing','ACTIVE','{}')")
        self.assertRaises(ValueError,validate_proposed_component_cycles,self.c,[self.op])
    def test_non_navigation_derivation_does_not_form_family_cycle(self):
        ops=[{'uid':'child','parent':'parent','relation':'NATIVE_DESIGN_PARENT'},{'uid':'parent','parent':'child','relation':'SOURCE_DESIGN_DERIVATION_REFERENCE'}]
        validate_proposed_component_cycles(self.c,ops)
    def test_unrelated_source_jet_statement_cannot_be_owned(self):
        self.c.execute("INSERT INTO nodes VALUES('other','Another','{}','ACTIVE','publisher','model',3)")
        self.op['proof']['source_witnesses'].append({'uid':'other','field':'description','statement':'','data_sha256':sha('{}')});self.assertRaises(ValueError,self.validate)
    def test_widebody_normalization_preserves_real_first_genus(self):
        self.assertEqual(own_physical_genus('widebody airliner family','Atlas')[1],'wikidata:Q210932')
        self.assertEqual(own_physical_genus('narrowbody airliner','Atlas')[1],'wikidata:Q210932')
    def test_modifier_normalization_does_not_accept_toy_incidental_or_negated_airliner(self):
        for text in ['toy widebody airliner','not a widebody airliner','an engine for a widebody airliner','Another is a widebody airliner','widebody airliner that is not a real physical aircraft']:
            self.assertIsNone(own_physical_genus(text,'Atlas'),text)
    def test_whole_family_twinjet_preserves_private_and_commercial_use(self):
        self.assertTrue(owned_twinjet_scope('The Atlas is a family of five-abreast twinjet airliners. A private business version uses the same design.', 'Atlas'))
    def test_incidental_other_model_twinjet_does_not_define_the_subject(self):
        self.assertFalse(owned_twinjet_scope('Another aircraft is a twinjet airliner.', 'Atlas'))
        self.assertFalse(owned_twinjet_scope('The Atlas is an aircraft that replaced a twinjet airliner.', 'Atlas'))
    def test_design_derivation_scope_must_be_explicitly_non_navigation(self):
        self.op['relation']='SOURCE_DESIGN_DERIVATION_REFERENCE';self.fact['relation']=self.op['relation'];self.assertRaises(ValueError,self.validate)

if __name__=='__main__':unittest.main()
