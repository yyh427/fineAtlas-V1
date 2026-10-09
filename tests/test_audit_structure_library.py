"""Independent release auditing must catch real regressions, not waive a cohort."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/audit_structure_library.py'
SPEC = importlib.util.spec_from_file_location('library_audit', SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class LibraryAuditTest(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.con.row_factory = sqlite3.Row
        self.con.executescript('''
          CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,source TEXT,rank TEXT,
            visibility TEXT,component_id INTEGER);
          CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,attributes TEXT);
          CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,
            relation TEXT,status TEXT,source TEXT);
          CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,
            object_uid TEXT,relation TEXT,status TEXT,source TEXT);
          CREATE TABLE bridges(id INTEGER PRIMARY KEY,left_uid TEXT,right_uid TEXT,
            relation TEXT,status TEXT);
          CREATE TABLE usability_changes(id INTEGER PRIMARY KEY,stage TEXT,object_type TEXT,
            object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT);
          CREATE TABLE normalization_roles(uid TEXT PRIMARY KEY,canonical_role TEXT,status TEXT,evidence_id TEXT);
          CREATE TABLE evidence(evidence_id TEXT PRIMARY KEY,payload TEXT);
          INSERT INTO nodes VALUES('root','Root','wordnet31','class','ACTIVE',1);
          INSERT INTO nodes VALUES('child','Child','native','species','ACTIVE',2);
          INSERT INTO nodes VALUES('model','Model','official','model','ACTIVE',3);
          INSERT INTO nodes VALUES('maker','Manufacturer','official','manufacturer','ACTIVE',4);
          INSERT INTO nodes VALUES('hidden','Excluded scope','native','class','ACTIVE',5);
          INSERT INTO node_profiles VALUES('hidden','CLASS','{"allowed_views":["membership"]}');
          INSERT INTO edges VALUES(1,'child','root','IS_A','ACTIVE','authority');
          INSERT INTO edges VALUES(2,'model','root','IS_A','ACTIVE','authority');
          INSERT INTO edges VALUES(3,'hidden','root','IS_A','ACTIVE','authority');
          INSERT INTO entity_relations VALUES(1,'model','root','DESIGN_TYPE_OF','ACTIVE','official');
          INSERT INTO entity_relations VALUES(2,'maker','root','DESIGN_TYPE_OF','ACTIVE','official');
        ''')

    def tearDown(self):
        self.con.close()

    def path(self, uid='child', table='edges', relation='IS_A'):
        edge={'id':1,'relation':relation}
        if table=='entity_relations':edge['terminal_connection']=True
        return {'status':'CONNECTED','root_uid':'root','path':[
            {'uid':uid,'parent_uid':'root','edge':edge}]}

    def test_independent_raw_branch_counts_separate_model_and_ignore_catalogue(self):
        rows=[dict(r) for r in AUDIT.raw_branch_rows(self.con)]
        self.assertEqual(rows,[
            {'parent_component':1,'role':'CLASS','relation':'IS_A','concept_count':1,'source_arc_count':1},
            {'parent_component':1,'role':'MODEL','relation':'DESIGN_TYPE_OF','concept_count':1,'source_arc_count':1}])

    def test_source_paths_cannot_substitute_ordinary_is_a_for_model_design(self):
        self.assertEqual(AUDIT.path_errors(self.con,self.path(),'child'),[])
        errors=AUDIT.path_errors(self.con,self.path('model'),'model')
        self.assertTrue(any(r['reason']=='MISSING_NATIVE_PATH_ASSERTION' for r in errors))
        wrong=self.path('model');wrong['path'][0]['edge']['id']=2
        errors=AUDIT.path_errors(self.con,wrong,'model')
        self.assertTrue(any(r['reason']=='ILLEGAL_UNIFIED_ROLE_OR_RELATION' for r in errors))
        proper=self.path('model','entity_relations','DESIGN_TYPE_OF')
        self.assertEqual(AUDIT.path_errors(self.con,proper,'model'),[])

    def test_unexplained_disconnection_is_failure_even_if_other_claim_reviewed(self):
        self.con.execute("UPDATE edges SET status='REVIEW' WHERE id=1")
        disconnected={'status':'DISCONNECTED','path':[]}
        kind,proof=AUDIT.classify_sample(self.con,self.path(),disconnected,'CLASS','CLASS','child')
        self.assertEqual(kind,'UNKNOWN_REACHABILITY_REGRESSION')
        self.assertEqual(proof,[])
        # Same record ID with different original endpoints is not its witness.
        self.con.execute('INSERT INTO usability_changes VALUES(1,?,?,?,?,?,?)',(
            'adjudication','edge','1',json.dumps({'child_uid':'other','parent_uid':'root','relation':'IS_A'}),
            '{}',json.dumps({'basis':'A separate source scope was withdrawn'})))
        self.assertEqual(AUDIT.withdrawal_evidence(self.con,self.path()),[])

    def test_exact_retired_witness_requires_specific_ledger_and_preserves_review_status(self):
        self.con.execute("UPDATE edges SET status='REVIEW' WHERE id=1")
        self.con.execute('INSERT INTO usability_changes VALUES(1,?,?,?,?,?,?)',(
            'identity_scope','edge','1',json.dumps({'child_uid':'child','parent_uid':'root','relation':'IS_A'}),
            '{}',json.dumps({'basis':'Official source identifier scope differs','disposition_category':'SOURCE_SCOPE_NOT_EQUIVALENT'})))
        kind,proof=AUDIT.classify_sample(self.con,self.path(),{'status':'DISCONNECTED','path':[]},'CLASS','CLASS','child')
        self.assertEqual(kind,'EXPLAINED_REVIEW_WITHDRAWAL')
        self.assertFalse(proof[0]['scientific_identity_is_now_confirmed'])

    def test_identity_step_requires_active_exact_source_bridge(self):
        self.con.execute('INSERT INTO bridges VALUES(1,?,?,?,?)',('child','root','SAME_CONCEPT','ACTIVE'))
        path=self.path(relation='SAME_CONCEPT')
        self.assertTrue(AUDIT.path_errors(self.con,path,'child'))
        self.con.execute("UPDATE nodes SET component_id=1 WHERE uid='child'")
        self.assertEqual(AUDIT.path_errors(self.con,path,'child'),[])
        self.con.execute("UPDATE bridges SET status='REVIEW'")
        self.assertTrue(AUDIT.path_errors(self.con,path,'child'))

    def test_role_change_cannot_pass_with_evidence_for_another_role(self):
        self.con.execute('INSERT INTO normalization_roles VALUES(?,?,?,?)',('child','MODEL','VERIFIED','proof'))
        self.con.execute('INSERT INTO evidence VALUES(?,?)',('proof',json.dumps({'basis':'Explicit source model record'})))
        kind,_=AUDIT.classify_sample(self.con,self.path(),self.path(),'CLASS','CONFIGURATION','child')
        self.assertEqual(kind,'UNKNOWN_ROLE_REGRESSION')
        kind,proof=AUDIT.classify_sample(self.con,self.path(),self.path(),'CLASS','MODEL','child')
        self.assertEqual(kind,'EVIDENCED_ROLE_CHANGE')
        self.assertEqual(proof[0]['evidence_id'],'proof')
        self.con.execute("UPDATE normalization_roles SET status='REVIEW'")
        kind,_=AUDIT.classify_sample(self.con,self.path(),self.path(),'CLASS','MODEL','child')
        self.assertEqual(kind,'UNKNOWN_ROLE_REGRESSION')


if __name__ == '__main__':
    unittest.main()
