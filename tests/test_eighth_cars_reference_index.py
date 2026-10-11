import sqlite3
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_temporal_cars_projection_view_repairs import source_reference_navigation_leaks

class SourceReferenceIndexLeakTest(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.executescript('CREATE TABLE browse_links(storage TEXT,record_id INTEGER);CREATE TABLE view_terminal_connections(witness_relation_id INTEGER);CREATE TABLE view_paths(witness_id INTEGER);')
    def tearDown(self):self.c.close()
    def test_real_entity_storage_leak_is_detected(self):
        self.c.execute('INSERT INTO browse_links VALUES(?,?)',('entity',7));self.assertEqual(source_reference_navigation_leaks(self.c,7),['browse_links'])
    def test_distinct_edge_id_cannot_be_mistaken_for_entity_reference(self):
        self.c.execute('INSERT INTO browse_links VALUES(?,?)',('edge',7));self.assertEqual(source_reference_navigation_leaks(self.c,7),[])
    def test_terminal_and_negative_typed_path_witnesses_are_both_checked(self):
        self.c.execute('INSERT INTO view_terminal_connections VALUES(7)');self.c.execute('INSERT INTO view_paths VALUES(-7)');self.assertEqual(set(source_reference_navigation_leaks(self.c,7)),{'view_terminal_connections','view_paths'})
