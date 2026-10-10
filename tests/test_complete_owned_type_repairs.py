import copy
import json
import sqlite3
import unittest

from fineatlas.structure_complete_owned_type_repairs import (
    SOURCE, dump, safe_input, validate_complete_owned_type_repairs,
)
from fineatlas.structure_complete_owned_type_rules import complete_owned_physical_genus
from fineatlas.structure_regression_repairs import sha
from pathlib import Path


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
        self.manifest = {'schema':'FINEATLAS_COMPLETE_OWNED_TYPE_REPAIRS_V1','operation_count':1,'operations_sha256':'exact-ops-sha','completed_parent_binding':{'database_revision':'parent-revision','frozen_manifest_sha256':sha(dump({'inputs':{'old.json':'old-sha'}}))},'parent_components':{parent['uid']:{'before_node':parent,'before_profile':{'uid':parent['uid'],'node_kind':'CLASS'},'before_normalization_role':None,'component_nodes':[parent],'component_bridges':[],'parent_edges':[],'parent_typed':[]}}}
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


if __name__ == '__main__':
    unittest.main()
