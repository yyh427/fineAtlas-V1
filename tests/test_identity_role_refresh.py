import hashlib, sqlite3, unittest
from fineatlas.hierarchy import validate_identity_role_only


class IdentityRoleRefreshTest(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.c.executescript('''
          CREATE TABLE nodes(uid TEXT,component_id INTEGER,data TEXT,visibility TEXT,source TEXT,rank TEXT);
          CREATE TABLE node_profiles(uid TEXT,node_kind TEXT,attributes TEXT);
          CREATE TABLE edges(status TEXT,child_uid TEXT,parent_uid TEXT);
          CREATE TABLE entity_relations(status TEXT,subject_uid TEXT,object_uid TEXT);
          CREATE TABLE view_paths(component_id INTEGER,witness_id INTEGER);
          INSERT INTO nodes VALUES('alias',1,'{}','ACTIVE','wikidata','named_refinement');
          INSERT INTO nodes VALUES('native-model',1,'{}','ACTIVE','faa','model');
          INSERT INTO view_paths VALUES(1,123);
        ''')
        digest = hashlib.sha256(b'{}').hexdigest()
        self.records = [{'op':'role','uid':'alias','role':'MODEL','proof':{
            'native_design_authority_uid':'native-model',
            'native_record_sha256':digest,'authority_native_record_sha256':digest}}]

    def test_verified_isolated_alias_preserves_existing_path(self):
        before = list(self.c.execute('SELECT * FROM view_paths'))
        self.assertTrue(validate_identity_role_only(self.c,self.records)['graph_admission_unchanged'])
        self.c.execute("INSERT INTO node_profiles VALUES('alias','MODEL','{}')")
        self.assertTrue(validate_identity_role_only(self.c,self.records)['graph_admission_unchanged'])
        self.assertEqual(before,list(self.c.execute('SELECT * FROM view_paths')))

    def test_incident_assertions_require_rebuild_in_both_directions(self):
        for table, columns, status in [('edges','child_uid,parent_uid','ACTIVE'),
                                      ('edges','child_uid,parent_uid','TYPED_ACTIVE'),
                                      ('entity_relations','subject_uid,object_uid','ACTIVE')]:
            for endpoints in [('alias','other'),('other','alias')]:
                with self.subTest(table=table,status=status,endpoints=endpoints):
                    self.c.execute(f'INSERT INTO {table}(status,{columns}) VALUES(?,?,?)',(status,*endpoints))
                    with self.assertRaises(ValueError):validate_identity_role_only(self.c,self.records)
                    self.c.execute(f'DELETE FROM {table}')

    def test_identity_and_source_proof_cannot_be_substituted(self):
        self.c.execute("UPDATE nodes SET component_id=2 WHERE uid='native-model'")
        with self.assertRaises(ValueError):validate_identity_role_only(self.c,self.records)
        self.c.execute("UPDATE nodes SET component_id=1,data='changed' WHERE uid='native-model'")
        with self.assertRaises(ValueError):validate_identity_role_only(self.c,self.records)
