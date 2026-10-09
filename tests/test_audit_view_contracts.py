"""Actual source/graph/cache micro fixtures for view-aware contract auditing."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import unittest

path=Path(__file__).resolve().parents[1]/'scripts'/'audit_contracts.py'
spec=importlib.util.spec_from_file_location('view_contract_audit',path)
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)


class ViewContractsTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.addCleanup(self.c.close)
        self.c.executescript('''
          CREATE TABLE nodes(uid TEXT PRIMARY KEY,component_id INTEGER,visibility TEXT,rank TEXT,source TEXT);
          CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,attributes TEXT);
          CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,status TEXT,relation TEXT);
          CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,status TEXT,relation TEXT);
          CREATE TABLE view_roots(view TEXT,component_id INTEGER,depth INTEGER,parent_component_id INTEGER,witness_id INTEGER);
          CREATE TABLE view_paths(view TEXT,component_id INTEGER,depth INTEGER,parent_component_id INTEGER,witness_id INTEGER);
          CREATE TABLE browse_links(view TEXT,parent_component INTEGER,child_component INTEGER,role TEXT,relation TEXT,storage TEXT,record_id INTEGER);
        ''')
        self.node('root',1,'CLASS')

    def node(self,uid,component,role,views=None,visibility='ACTIVE'):
        self.c.execute('INSERT INTO nodes VALUES(?,?,?,?,?)',(uid,component,visibility,'class','fixture'))
        self.c.execute('INSERT INTO node_profiles VALUES(?,?,?)',(uid,role,json.dumps({} if views is None else {'allowed_views':views})))

    def edge(self,eid,child,parent='root',relation='IS_A',status='ACTIVE'):
        self.c.execute('INSERT INTO edges VALUES(?,?,?,?,?)',(eid,child,parent,status,relation))

    def browse(self,view,eid,child,parent=1,role='CLASS',relation='IS_A',storage='edge'):
        self.c.execute('INSERT INTO browse_links VALUES(?,?,?,?,?,?,?)',(view,parent,child,role,relation,storage,eid))

    def witness(self,view,child,eid,parent=1,classification=True):
        self.c.execute('INSERT INTO view_paths VALUES(?,?,?,?,?)',(view,child,1,parent,eid))
        if classification:self.c.execute('INSERT INTO view_roots VALUES(?,?,?,?,?)',(view,child,1,parent,eid))

    def failures(self):
        return {k:self.c.execute(v).fetchone()[0] for k,v in audit.view_graph_contract_queries().items()
                if self.c.execute(v).fetchone()[0]}

    def test_taxonomy_only_class_and_variant_witnesses_are_admitted_in_unified(self):
        for component,role in ((2,'CLASS'),(3,'BIOLOGICAL_VARIANT')):
            uid=str(component);self.node(uid,component,role,['taxonomy'])
            self.edge(component,uid);self.witness('unified',component,component)
        self.assertEqual(self.failures(),{})
        census=audit.raw_strict_exclusion_census(self.c)
        self.assertEqual(sum(x['retained_active_ISA_records'] for x in census['child_uid']),2)

    def test_source_view_rules_fail_if_taxonomy_only_uid_leaks_into_strict(self):
        self.node('restricted',2,'CLASS',['taxonomy']);self.edge(1,'restricted')
        self.browse('strict',1,2);self.witness('strict',2,1)
        failures=self.failures()
        self.assertEqual(failures['strict_full_classification_graph_contract'],1)
        self.assertEqual(failures['view_paths_class_witness_contract'],1)
        self.assertEqual(failures['view_roots_class_witness_contract'],1)

    def test_biological_variant_cannot_borrow_admission_from_class_identity_peer(self):
        self.node('variant',2,'BIOLOGICAL_VARIANT',['taxonomy'])
        self.node('class-peer',2,'CLASS')
        self.edge(1,'variant');self.browse('strict',1,2);self.witness('strict',2,1)
        self.assertEqual(self.failures()['strict_full_classification_graph_contract'],1)

    def test_instance_strict_classification_fails_even_in_unrooted_component(self):
        self.node('instance',2,'INSTANCE');self.node('orphan-class',3,'CLASS')
        self.edge(1,'instance','orphan-class');self.browse('strict',1,2,parent=3,role='CLASS')
        self.assertEqual(self.failures()['strict_full_classification_graph_contract'],1)
        self.assertEqual(self.c.execute('SELECT count(*) FROM view_roots').fetchone()[0],0)

    def test_missing_admitted_source_arc_is_checked_without_root_witness(self):
        self.node('class',2,'CLASS');self.edge(1,'class')
        self.assertEqual(self.failures()['strict_full_graph_missing_admitted_source_arcs'],1)
        self.browse('strict',1,2)
        self.assertEqual(self.failures(),{})

    def test_duplicate_source_identity_pair_needs_one_graph_representative(self):
        self.node('a',2,'CLASS');self.node('peer',2,'CLASS')
        self.edge(1,'a');self.edge(2,'peer');self.browse('strict',1,2)
        self.assertEqual(self.failures(),{})
        self.c.execute('DELETE FROM browse_links')
        self.assertEqual(self.failures()['strict_full_graph_missing_admitted_source_arcs'],1)

    def test_identity_self_source_arc_is_zero_depth_not_graph_edge(self):
        self.node('root-peer',1,'CLASS');self.edge(1,'root-peer')
        self.assertEqual(self.failures(),{})
        self.browse('strict',1,1)
        self.assertEqual(self.failures()['strict_full_classification_graph_contract'],1)

    def test_typed_witness_requires_current_active_role_relation_and_parent(self):
        self.node('model',2,'MODEL',['taxonomy'])
        self.c.execute("INSERT INTO entity_relations VALUES(1,'model','root','ACTIVE','DESIGN_TYPE_OF')")
        self.witness('unified',2,-1,classification=False)
        self.assertEqual(self.failures(),{})
        for sql in ("UPDATE entity_relations SET status='REVIEW'",
                    "UPDATE entity_relations SET status='ACTIVE',relation='INSTANCE_OF'",
                    "UPDATE entity_relations SET relation='DESIGN_TYPE_OF';UPDATE node_profiles SET node_kind='INSTANCE' WHERE uid='root'",
                    "UPDATE node_profiles SET node_kind='CLASS' WHERE uid='root';UPDATE nodes SET visibility='SOURCE_ONLY' WHERE uid='model'"):
            with self.subTest(sql=sql):
                self.c.executescript(sql)
                self.assertEqual(self.failures()['view_paths_typed_witness_contract'],1)

    def test_missing_witness_record_and_wrong_component_are_failures(self):
        self.node('class',2,'CLASS');self.witness('taxonomy',2,999)
        self.assertEqual(self.failures()['view_paths_class_witness_contract'],1)
        self.edge(999,'class');self.c.execute('UPDATE view_paths SET parent_component_id=99')
        self.assertEqual(self.failures()['view_paths_class_witness_contract'],1)

    def test_unknown_view_cannot_fall_through_shared_mapping(self):
        self.node('class',2,'CLASS');self.edge(1,'class');self.witness('unknown',2,1)
        self.assertEqual(self.failures()['view_paths_unknown_views'],1)
        self.assertEqual(self.failures()['view_paths_class_witness_contract'],1)

    def test_typed_relation_cannot_enter_strict_classification_cache(self):
        self.node('model',2,'MODEL');self.c.execute("INSERT INTO entity_relations VALUES(1,'model','root','ACTIVE','DESIGN_TYPE_OF')")
        self.witness('strict',2,-1)
        self.assertEqual(self.failures()['typed_relations_entering_classification_caches'],1)

    def test_wrong_relation_or_status_strict_graph_fails(self):
        self.node('class',2,'CLASS');self.edge(1,'class');self.browse('strict',1,2)
        for sql in ("UPDATE edges SET relation='TAXONOMIC_PARENT',status='TYPED_ACTIVE'",
                    "UPDATE edges SET relation='IS_A',status='REVIEW'"):
            self.c.execute(sql)
            self.assertEqual(self.failures()['strict_full_classification_graph_contract'],1)


if __name__=='__main__':unittest.main()
