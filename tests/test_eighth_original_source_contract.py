"""Exact temporal permissions cannot hide current source/mapping mutations."""
import json
from pathlib import Path
import sqlite3
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from structure_eighth_original_source_contract import LaterSourceContract,content_sha,sha


class EighthOriginalSourceContractTest(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
        self.c.executescript('''
          CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,relation TEXT,status TEXT,source TEXT,evidence_id TEXT,data TEXT);
          CREATE TABLE node_profiles(uid TEXT,node_kind TEXT);
          CREATE TABLE normalization_roles(uid TEXT,canonical_role TEXT);
          CREATE TABLE usability_changes(stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT);
          CREATE TABLE dataset_targets(dataset TEXT,class_id TEXT,label TEXT,target_uid TEXT);
          CREATE TABLE dataset_mapping_checks(dataset TEXT,class_id TEXT,status TEXT);
        ''')
        self.contract=LaterSourceContract.__new__(LaterSourceContract)
        self.contract.c=self.c;self.contract.checked_reviews=[];self.contract.checked_mappings=[]
        self.original_proof={'complete_source':'original whole record'}
        self.before={'id':1,'subject_uid':'model','object_uid':'class','relation':'DESIGN_TYPE_OF','status':'ACTIVE','source':'first','evidence_id':'original-eid','data':json.dumps({'admission_basis':self.original_proof})}
        self.c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',tuple({**self.before,'status':'SOURCE_SCOPE_REVIEW'}.values()))
        self.operation={'op':'review_typed_relation','uid':'model','parent':'class','relation':'DESIGN_TYPE_OF','before_assertion':self.before,'content_sha256':content_sha(self.before),'after_status':'SOURCE_SCOPE_REVIEW','proof':{'independent_scope_review':'unknown narrow scope'}}
        self.contract.operations=[('owned_scope_repairs',self.operation)]
        self.c.execute('INSERT INTO usability_changes VALUES(?,?,?,?,?,?)',('owned_scope_repairs','typed_scope_review','1',json.dumps(self.before),json.dumps({'status':'SOURCE_SCOPE_REVIEW'}),json.dumps(self.operation['proof'])))
        self.repair={'uid':'model','parent':'class','relation':'DESIGN_TYPE_OF','source':'first','proof':self.original_proof}

    def test_frozen_precise_original_and_later_history_are_required(self):
        self.assertEqual(self.contract.replacement_transition(self.repair)['id'],1)
        self.c.execute("UPDATE entity_relations SET evidence_id='another'")
        with self.assertRaisesRegex(ValueError,'exact original'):
            self.contract.replacement_transition(self.repair)

    def test_unlisted_scope_review_does_not_grant_permission(self):
        self.contract.operations=[]
        self.assertIsNone(self.contract.replacement_transition(self.repair))

    def test_missing_exact_history_cannot_authorize_old_status_change(self):
        self.c.execute('DELETE FROM usability_changes')
        with self.assertRaisesRegex(ValueError,'history'):
            self.contract.replacement_transition(self.repair)

    def test_mapping_fingerprint_preserves_current_rows_and_omits_only_prior_missing_check(self):
        before={'dataset':'aircraft','class_id':'1','label':'old','target_uid':'old-uid'}
        after={**before,'target_uid':'new-uid'};newcheck={'dataset':'aircraft','class_id':'1','status':'VERIFIED'}
        operation={'op':'migrate_nominal_design_mapping','dataset':'aircraft','class_id':'1','before_target':before,'after_target':after,'before_check':None,'after_check':newcheck,'proof':{'primary_scope':'exact'}}
        self.contract.operations=[('owned_scope_repairs',operation)]
        self.c.execute('INSERT INTO dataset_targets VALUES(?,?,?,?)',tuple(after.values()))
        self.c.execute('INSERT INTO dataset_mapping_checks VALUES(?,?,?)',tuple(newcheck.values()))
        self.c.execute('INSERT INTO usability_changes VALUES(?,?,?,?,?,?)',('owned_scope_repairs','nominal_design_mapping','aircraft:1',json.dumps({'target':before,'check':None}),json.dumps({'target':after,'check':newcheck}),json.dumps(operation['proof'])))
        self.assertEqual(self.contract.historical_mapping_hash('dataset_targets'),sha(json.dumps([before],sort_keys=True)))
        self.assertEqual(self.contract.historical_mapping_hash('dataset_mapping_checks'),sha(json.dumps([],sort_keys=True)))
        self.assertEqual(dict(self.c.execute('SELECT *FROM dataset_targets').fetchone()),after)
        self.c.execute("UPDATE dataset_targets SET target_uid='unapproved'")
        with self.assertRaisesRegex(ValueError,'exact later frozen'):
            self.contract.historical_mapping_hash('dataset_targets')
