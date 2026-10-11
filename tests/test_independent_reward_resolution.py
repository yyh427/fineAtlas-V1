"""Source-role resolution must independently catch non-WordNet type LCAs."""
import importlib.util
from pathlib import Path
import sqlite3
import unittest

spec=importlib.util.spec_from_file_location('independent_reward_audit',
    Path(__file__).resolve().parents[1]/'scripts/audit_structure_rewards.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)


class IndependentRewardResolutionTest(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
        self.c.executescript('''
          CREATE TABLE nodes(uid TEXT,component_id INTEGER,source TEXT,rank TEXT,visibility TEXT);
          CREATE TABLE browse_nodes(uid TEXT,role TEXT);
          CREATE TABLE node_profiles(uid TEXT,attributes TEXT);
          CREATE TABLE edges(child_uid TEXT,parent_uid TEXT,relation TEXT,status TEXT,data TEXT);
          CREATE TABLE entity_relations(subject_uid TEXT,object_uid TEXT,relation TEXT,status TEXT,data TEXT);
          INSERT INTO nodes VALUES('root',1,'native','class','ACTIVE');
          INSERT INTO nodes VALUES('native:gasoline-car',2,'native','class','ACTIVE');
          INSERT INTO nodes VALUES('native:documented-model',3,'native','model','ACTIVE');
          INSERT INTO nodes VALUES('portal',4,'native','domain_entry','ACTIVE');
          INSERT INTO browse_nodes VALUES('root','CLASS');
          INSERT INTO browse_nodes VALUES('native:gasoline-car','CLASS');
          INSERT INTO browse_nodes VALUES('native:documented-model','MODEL');
          INSERT INTO browse_nodes VALUES('portal','CLASS');
          INSERT INTO edges VALUES('native:gasoline-car','root','IS_A','ACTIVE','{}');
          INSERT INTO edges VALUES('portal','root','IS_A','ACTIVE','{}');
          INSERT INTO entity_relations VALUES('native:documented-model','native:gasoline-car','DESIGN_TYPE_OF','ACTIVE','{}');
        ''')
        self.graph=audit.IndependentGraph(self.c,'configuration_types',None,['root'])

    def tearDown(self):
        self.c.close()

    def test_generic_source_type_is_coarse_without_a_wordnet_uid_exception(self):
        self.assertEqual(audit.independent_informative_lcas(self.graph,{2},
            {'coarse_lca_roles':['CLASS']},'root'),set())
        self.assertEqual(audit.independent_informative_lcas(self.graph,{2},{},'root'),{2})

    def test_real_model_can_distinguish_configurations_under_ordinary_type_floor(self):
        self.assertEqual(audit.independent_informative_lcas(self.graph,{3},
            {'coarse_lca_roles':['CLASS']},'root'),{3})

    def test_legacy_floor_and_portal_cannot_manufacture_fine_resolution(self):
        self.assertEqual(audit.independent_informative_lcas(self.graph,{1,2},
            {'coarse_roots':['native:gasoline-car']},'root'),set())
        self.assertEqual(audit.independent_informative_lcas(self.graph,{4},{},'root'),set())


if __name__=='__main__':
    unittest.main()
