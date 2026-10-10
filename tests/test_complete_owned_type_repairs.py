import copy
import json
import sqlite3
import unittest

from fineatlas.structure_complete_owned_type_repairs import (
    SOURCE, dump, safe_input, parent_manifest_sha256, validate_complete_owned_type_repairs,
)
from fineatlas.structure_complete_owned_type_rules import complete_owned_physical_genus
from fineatlas.structure_regression_repairs import sha
from pathlib import Path
from fineatlas.migration import Migration


class CompleteOwnedTypeContractTest(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.c.executescript('''
            CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,data TEXT,visibility TEXT,source TEXT,rank TEXT,component_id INTEGER);
            CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT);
            CREATE TABLE normalization_roles(uid TEXT PRIMARY KEY,canonical_role TEXT);
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE bridges(id INTEGER PRIMARY KEY,left_uid TEXT,right_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);
            CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);
            CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);
        ''')
        raw = dump({'description':'Named model is a twinjet airliner.'})
        parent_raw = dump({'gloss':'a jet plane propelled by two jet engines'})
        self.c.executemany('INSERT INTO nodes VALUES(?,?,?,?,?,?,?)', [
            ('model','Named model',raw,'ACTIVE','publisher','model',1),
            ('wordnet31:04510794-n','twinjet',parent_raw,'ACTIVE','wordnet31','type',2),
        ])
        self.c.executemany('INSERT INTO node_profiles VALUES(?,?)', [
            ('model','MODEL'),('wordnet31:04510794-n','CLASS')])
        self.c.executemany('INSERT INTO metadata VALUES(?,?)', [
            ('database_revision',dump('parent-revision')),
            ('structure_frozen_build_manifest',dump({'inputs':{'old.json':'old-sha'}}))])
        child = dict(self.c.execute("SELECT * FROM nodes WHERE uid='model'").fetchone())
        parent = dict(self.c.execute("SELECT * FROM nodes WHERE uid='wordnet31:04510794-n'").fetchone())
        own = {'uid':'model','field':'description','field_path':'description','statement':'Named model is a twinjet airliner.','data_sha256':sha(raw),'bound_source_names':[]}
        pw = {'uid':parent['uid'],'field':'gloss','field_path':'gloss','statement':'a jet plane propelled by two jet engines','data_sha256':sha(parent_raw)}
        self.op = {'op':'link','uid':'model','parent':parent['uid'],'relation':'DESIGN_TYPE_OF','source':SOURCE,'uri':'https://example.org/source','proof':{
            'world_identity_assertion':False,'no_identity_merges':True,'whole_subject_scope_review':True,
            'classification_axis':'physical_structure','native_record_sha256':sha(raw),
            'parent_native_record_sha256':sha(parent_raw),'source_model_role':'MODEL',
            'source_witnesses':[own,pw],'source_full_contexts':[own],
            'selected_physical_predicate':complete_owned_physical_genus(own['statement'],child['label']),
            'prior_assertions':[],
        }}
        self.manifest = {'schema':'FINEATLAS_COMPLETE_OWNED_TYPE_REPAIRS_V1','operation_count':1,'operations_sha256':'exact-ops-sha','completed_parent_binding':{'database_revision':'parent-revision','frozen_manifest_sha256':parent_manifest_sha256({'inputs':{'old.json':'old-sha'}})},'parent_components':{parent['uid']:{'before_node':parent,'before_profile':{'uid':parent['uid'],'node_kind':'CLASS'},'before_normalization_role':None,'component_nodes':[parent],'component_bridges':[],'parent_edges':[],'parent_typed':[]}}}
        self.approval = {'accepted_source_scope_only':True,'operations_sha256':'exact-ops-sha','approved_keys':[['model',parent['uid'],'DESIGN_TYPE_OF']]}

    def tearDown(self):
        self.c.close()

    def test_owned_first_scope_and_exact_parent_checkpoint_are_required(self):
        validate_complete_owned_type_repairs(self.c,self.manifest,[self.op],self.approval)
        altered = copy.deepcopy(self.manifest)
        altered['completed_parent_binding']['database_revision'] = 'other-build'
        with self.assertRaisesRegex(ValueError,'completed checkpoint'):
            validate_complete_owned_type_repairs(self.c,altered,[self.op],self.approval)

    def test_source_approval_is_not_an_extra_or_subset_permission(self):
        approval = copy.deepcopy(self.approval)
        approval['approved_keys'].append(['another',self.op['parent'],'DESIGN_TYPE_OF'])
        with self.assertRaisesRegex(ValueError,'independent full-range approval'):
            validate_complete_owned_type_repairs(self.c,self.manifest,[self.op],approval)

    def test_endpoint_source_and_parent_identity_scope_are_bound(self):
        self.c.execute("UPDATE nodes SET data='{}' WHERE uid='model'")
        with self.assertRaisesRegex(ValueError,'endpoint range'):
            validate_complete_owned_type_repairs(self.c,self.manifest,[self.op],self.approval)

    def test_parent_role_cannot_become_narrow_source_model(self):
        self.c.execute("UPDATE node_profiles SET node_kind='MODEL' WHERE uid=?",(self.op['parent'],))
        with self.assertRaisesRegex(ValueError,'already be admitted'):
            validate_complete_owned_type_repairs(self.c,self.manifest,[self.op],self.approval)

    def test_complete_own_field_cannot_be_replaced_by_a_related_article(self):
        op = copy.deepcopy(self.op)
        op['proof']['source_witnesses'][0]['statement'] = 'Another model is a twinjet airliner.'
        with self.assertRaisesRegex(ValueError,'original field'):
            validate_complete_owned_type_repairs(self.c,self.manifest,[op],self.approval)

    def test_boolean_count_and_unsafe_paths_are_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['operation_count'] = True
        with self.assertRaisesRegex(ValueError,'count'):
            validate_complete_owned_type_repairs(self.c,manifest,[self.op],self.approval)
        for filename in ('../outside.json','/tmp/source.json','', '..'):
            with self.assertRaises(ValueError): safe_input(Path('/inputs'),filename)

    def test_role_evidence_matches_real_migration_encoding(self):
        c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
        c.executescript('''
            CREATE TABLE nodes(uid TEXT,label TEXT,domain TEXT,rank TEXT,data TEXT);
            CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,domain TEXT,source_uri TEXT,evidence_id TEXT,attributes TEXT);
            CREATE TABLE normalization_roles(uid TEXT PRIMARY KEY,source_role TEXT,canonical_role TEXT,status TEXT,evidence_id TEXT,source TEXT,prior_profile TEXT);
            CREATE TABLE evidence(layer TEXT,evidence_id TEXT PRIMARY KEY,source TEXT,source_uri TEXT,retrieved_utc TEXT,claim TEXT,payload TEXT,sha256 TEXT);
            CREATE TABLE usability_changes(stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT);
        ''')
        c.execute('INSERT INTO nodes VALUES(?,?,?,?,?)',('named','Named programme','computers','class','{}'))
        before={'uid':'named','node_kind':'CLASS','domain':'computers','source_uri':'https://example.org/original','evidence_id':'old','attributes':'{}'}
        c.execute('INSERT INTO node_profiles VALUES(?,?,?,?,?,?)',tuple(before.values()))
        proof={'source_role':'MODEL','native_rank':'class','source_statement':'重复制造的计算机 programme','scope_observation':'A programme with many produced machines.'}
        eid='usability:'+sha(dump(proof))
        m=Migration.__new__(Migration);m.c=c;m.legacy_evidence_fallback=None
        actual_eid=m.role('named','MODEL',proof,SOURCE,'https://example.org/original')
        self.assertEqual(eid,actual_eid)
        after=dict(c.execute("SELECT * FROM node_profiles WHERE uid='named'").fetchone())
        self.assertEqual(after['attributes'],dump({'source_role':'MODEL','native_rank':'class','role_status':'VERIFIED','role_evidence_id':eid}))
        norm=dict(c.execute("SELECT * FROM normalization_roles WHERE uid='named'").fetchone())
        self.assertEqual(norm['prior_profile'],dump(before))
        self.assertEqual(c.execute('SELECT payload FROM evidence').fetchone()[0],dump(proof))
        c.close()


if __name__ == '__main__':
    unittest.main()

class SerialIndividualMigrationContractTest(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
        self.c.executescript('''
            CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,data TEXT,visibility TEXT,source TEXT,rank TEXT,component_id INTEGER);
            CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT);
            CREATE TABLE normalization_roles(uid TEXT PRIMARY KEY,canonical_role TEXT);
            CREATE TABLE bridges(id INTEGER PRIMARY KEY,left_uid TEXT,right_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);
            CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);
            CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);
        ''')
        self.statement='The named airship was the 51st airship built and had tactical designation L81.'
        data=dump({'definition':self.statement})
        self.c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?)',('serial','named airship',data,'ACTIVE','source','class',1))
        self.c.execute('INSERT INTO node_profiles VALUES(?,?)',('serial','MODEL'))
        from fineatlas.structure_complete_owned_type_repairs import scope_inventory
        self.w={'uid':'serial','field':'definition','field_path':'definition','statement':self.statement,'data_sha256':sha(data)}
        self.record={'uid':'serial','approved_new_role':'INSTANCE','source_grain_disposition':'OWN_SERIAL_AND_OPERATIONAL_DESIGNATION_SUPPORT_INSTANCE','complete_source_record':{'before_node':dict(self.c.execute('SELECT * FROM nodes').fetchone()),'all_own_fields':[self.w]}}
        self.proof={'kind':'INSTANCE_SCOPE_ROLE_MIGRATION','native_record_sha256':sha(data),'source_instance_review_record':self.record,'source_instance_review_locator':{'file':'instances.json','sha256':'bound','uid':'serial'},'source_witnesses':[self.w],'before_scope_declarations':scope_inventory(self.c,'serial')}
        self.op={'op':'correct_role','uid':'serial','parent':'serial','relation':'ROLE_ADJUDICATION','proof':self.proof}
        self.manifest={'source_instance_review_file':'instances.json','source_instance_review_sha256':'bound'}
        self.review={'records':[self.record]}

    def validate(self,ops=None):
        from fineatlas.structure_complete_owned_type_repairs import validate_serial_instance
        return validate_serial_instance(self.c,self.op,self.manifest,self.review,ops or[self.op])

    def test_built_serial_with_operational_name_is_individual(self):
        self.assertEqual(self.validate()['approved_new_role'],'INSTANCE')

    def test_active_model_type_requires_exact_encoding_migration(self):
        self.c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?)',(9,'serial','aircraft','DESIGN_TYPE_OF','original','ACTIVE','{}'))
        from fineatlas.structure_complete_owned_type_repairs import scope_inventory
        self.proof['before_scope_declarations']=scope_inventory(self.c,'serial')
        with self.assertRaisesRegex(ValueError,'abandon'):
            self.validate()
        before=dict(self.c.execute('SELECT * FROM entity_relations').fetchone())
        self.validate([self.op,{'op':'review_typed_relation','before_assertion':before}])

    def test_single_prototype_is_not_built_serial_individual_evidence(self):
        text='The named aircraft is a single prototype design.';data=dump({'definition':text})
        self.c.execute('UPDATE nodes SET data=?',(data,))
        self.record['complete_source_record']['before_node']['data']=data
        self.w.update(statement=text,data_sha256=sha(data));self.proof['native_record_sha256']=sha(data)
        with self.assertRaisesRegex(ValueError,'ordinal design'):
            self.validate()

    def test_active_identity_cannot_be_borrowed_for_individual_scope(self):
        self.c.execute('INSERT INTO bridges VALUES(?,?,?,?,?,?,?)',(1,'serial','other','SAME_CONCEPT','source','ACTIVE','{}'))
        with self.assertRaisesRegex(ValueError,'identity peer'):
            self.validate()

class UncertainRoleExecutionTest(unittest.TestCase):
    def test_unknown_role_is_review_and_keeps_original_normalization_history(self):
        from fineatlas.structure_complete_owned_type_repairs import apply_reviewed_role
        c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
        c.executescript('''
        CREATE TABLE nodes(uid TEXT,label TEXT,domain TEXT,rank TEXT,data TEXT);
        CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,domain TEXT,source_uri TEXT,evidence_id TEXT,attributes TEXT);
        CREATE TABLE normalization_roles(uid TEXT PRIMARY KEY,source_role TEXT,canonical_role TEXT,status TEXT,evidence_id TEXT,source TEXT,prior_profile TEXT);
        CREATE TABLE evidence(layer TEXT,evidence_id TEXT PRIMARY KEY,source TEXT,source_uri TEXT,retrieved_utc TEXT,claim TEXT,payload TEXT,sha256 TEXT);
        CREATE TABLE usability_changes(stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT);
        ''')
        c.execute('INSERT INTO nodes VALUES(?,?,?,?,?)',('ambiguous','Unnamed aircraft','aircraft','model','{}'))
        before={'uid':'ambiguous','node_kind':'MODEL','domain':'aircraft','source_uri':'https://example.org/native','evidence_id':'original','attributes':dump({'original_scope':'preserved'})}
        c.execute('INSERT INTO node_profiles VALUES(?,?,?,?,?,?)',tuple(before.values()))
        norm={'uid':'ambiguous','source_role':'MODEL','canonical_role':'MODEL','status':'VERIFIED','evidence_id':'original','source':'original','prior_profile':'{}'}
        c.execute('INSERT INTO normalization_roles VALUES(?,?,?,?,?,?,?)',tuple(norm.values()))
        proof={'source_role':'UNKNOWN','allowed_views':[],'scope_observation':'Physical object versus nominal design unresolved.'}
        eid='usability:'+sha(dump(proof))
        after={**before,'node_kind':'UNKNOWN','evidence_id':eid,'attributes':dump({'original_scope':'preserved','source_role':'UNKNOWN','native_rank':'model','role_status':'REVIEW','role_evidence_id':eid,'allowed_views':[]})}
        after_norm={**norm,'canonical_role':'UNKNOWN','status':'REVIEW','evidence_id':eid,'source':SOURCE}
        op={'uid':'ambiguous','uri':before['source_uri'],'proof':proof,'before_profile':before,'before_normalization_role':norm,'after_profile':after,'after_normalization_role':after_norm}
        m=Migration.__new__(Migration);m.c=c;m.legacy_evidence_fallback=None
        apply_reviewed_role(m,op)
        self.assertEqual(dict(c.execute('SELECT *FROM normalization_roles').fetchone()),after_norm)
        self.assertEqual(dict(c.execute('SELECT *FROM node_profiles').fetchone()),after)
        history=c.execute("SELECT before_json,after_json FROM usability_changes WHERE stage='complete_owned_type_repairs'").fetchone()
        self.assertEqual(json.loads(history['before_json']),{'profile':before,'normalization_role':norm})
        self.assertEqual(json.loads(history['after_json']),{'profile':after,'normalization_role':after_norm})
        self.assertEqual(c.execute('SELECT payload FROM evidence').fetchone()[0],dump(proof))
        c.close()
