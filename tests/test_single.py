"""Deterministic public-interface tests, without the full database."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fineatlas import FineAtlas


class TypedInterfaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'fineatlas.sqlite'
        c = sqlite3.connect(self.path)
        c.executescript('''
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,domain TEXT,domains TEXT,source TEXT,rank TEXT,description TEXT,data TEXT,layer TEXT,visibility TEXT,component_id INTEGER);
        CREATE TABLE components(id INTEGER PRIMARY KEY,wordnet_reachable INTEGER,depth INTEGER,parent_component_id INTEGER,witness_edge_id INTEGER);
        CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,relation TEXT,status TEXT,source TEXT,confidence REAL,provenance TEXT,data TEXT);
        CREATE TABLE bridges(id INTEGER PRIMARY KEY,left_uid TEXT,right_uid TEXT,relation TEXT,status TEXT,confidence REAL,data TEXT);
        CREATE TABLE aliases(alias TEXT,uid TEXT);
        CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,domain TEXT,source_uri TEXT,evidence_id TEXT,attributes TEXT);
        CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,relation TEXT,status TEXT,source TEXT,evidence_id TEXT,data TEXT);
        CREATE TABLE entity_connections(uid TEXT PRIMARY KEY,wordnet_reachable INTEGER,class_uid TEXT,witness_relation_id INTEGER,depth INTEGER);
        CREATE TABLE evidence(layer TEXT,evidence_id TEXT,payload TEXT);
        CREATE TABLE dataset_targets(dataset TEXT,class_id TEXT,decision_status TEXT);
        ''')
        c.executemany('INSERT INTO metadata VALUES(?,?)', [('schema',json.dumps('FINEATLAS_SINGLE_DB_V1')), ('root_uid',json.dumps('type:root'))])
        for uid,label,rank,comp in [('type:root','entity','class',0),('type:river','Same Name','class',1),('geo:1','Same Name','instance',2),('attr:1','斑纹','attribute',3),('legacy:mixed','Mixed','type_or_product_model',4),('cat:1','river/outdoor','dataset_category',5)]:
            c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?)',(uid,label,'fixture','["fixture"]','fixture',rank,'Fixture definition','{}','fixture','ACTIVE',comp))
        c.executemany('INSERT INTO components VALUES(?,?,?,?,?)',[(0,1,0,None,None),(1,1,1,0,1),(2,0,-1,None,None),(3,0,-1,None,None),(4,0,-1,None,None),(5,0,-1,None,None)])
        c.execute("INSERT INTO edges VALUES(1,'type:river','type:root','IS_A','ACTIVE','fixture',1,'[\"proof:1\"]','{}')")
        c.executemany('INSERT INTO node_profiles VALUES(?,?,?,?,?,?)', [('geo:1','INSTANCE','fixture','https://example.org','proof:1','{}'),('attr:1','ATTRIBUTE','fixture','https://example.org','proof:1','{}'),('cat:1','DATASET_CATEGORY','fixture','https://example.org','proof:1','{}')])
        for rid,uid,relation in [(1,'geo:1','INSTANCE_OF'),(2,'attr:1','ATTRIBUTE_KIND_OF'),(3,'cat:1','DEPICTS_TYPE')]:
            c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',(rid,uid,'type:river',relation,'ACTIVE','fixture','proof:1','{}'))
            c.execute('INSERT INTO entity_connections VALUES(?,?,?,?,?)',(uid,1,'type:river',rid,2))
        c.executemany('INSERT INTO aliases VALUES(?,?)',[('same name','type:river'),('same name','geo:1'),('斑纹','attr:1')])
        c.execute("INSERT INTO evidence VALUES('fixture','proof:1','{}')")
        c.commit();c.close()
        self.tree = FineAtlas(self.path)

    def tearDown(self):
        self.tree.close();self.temp.cleanup()

    def test_same_name_and_kind_filter(self):
        self.assertEqual(len(self.tree.exact('Same Name')),2)
        self.assertEqual(self.tree.exact('Same Name',node_kind='CLASS')[0]['uid'],'type:river')
        self.assertEqual(self.tree.exact('Same Name',node_kind='INSTANCE')[0]['uid'],'geo:1')
        self.assertEqual(self.tree.exact('斑纹')[0]['uid'],'attr:1')
        self.assertEqual(self.tree.node('legacy:mixed')['node_kind'],'UNKNOWN')

    def test_typed_navigation_excludes_instances_from_class_children(self):
        self.assertEqual(self.tree.neighbors('type:river'),[])
        self.assertEqual(self.tree.instances('type:river')[0]['uid'],'geo:1')
        self.assertEqual(self.tree.path('geo:1')[-1]['edge']['relation'],'INSTANCE_OF')
        self.assertEqual(self.tree.path('attr:1')[-1]['edge']['relation'],'ATTRIBUTE_KIND_OF')
        self.assertEqual(self.tree.path('cat:1')[-1]['edge']['relation'],'DEPICTS_TYPE')
        self.assertEqual(self.tree.connection_status('cat:1')['tree_admission'],'DATASET_CATEGORY_ONLY')
        self.assertEqual(self.tree.connection_status('geo:1')['tree_admission'],'INSTANCE_ONLY')
        self.assertEqual(len(self.tree.evidence('proof:1')),1)

    def test_instance_typing_respects_depth_limit(self):
        self.assertEqual(self.tree.path('geo:1',max_depth=1),[])
        self.assertEqual(len(self.tree.path('geo:1',max_depth=2)),2)
        self.assertEqual(self.tree.relations('type:river',direction='incoming',relation='INSTANCE_OF')[0]['subject_uid'],'geo:1')


if __name__ == '__main__':
    unittest.main()
