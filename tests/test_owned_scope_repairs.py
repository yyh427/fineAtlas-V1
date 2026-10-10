"""Grounded source kinds, role changes and canonical batch safety."""
import copy
import sqlite3
import unittest

from fineatlas.migration import dump
from fineatlas.structure_regression_repairs import sha
from fineatlas.structure_owned_scope_rules import (
    bound_owned_source_names, owned_named_instance_genus,
    owned_physical_genus, owned_reconfigurable_fixed_wing,
)
from fineatlas.structure_owned_scope_repairs import (
    SOURCE, expected_partitions, validate_batch_cycles,
    validate_owned_scope_repairs,
)


class OwnedScopeGrammarTests(unittest.TestCase):
    def test_modifiers_and_abbreviated_names_retain_the_own_kind(self):
        samples = [
            ('The X was a very small single-seat sports monoplane.', 'X', 'wikidata:Q627537'),
            ('The G.A.C. 102 was a single-engine biplane.', 'G.A.C. 102', 'wikidata:Q223818'),
            ('The X are US-built open-cockpit biplane mailplanes derived from Y.', 'X', 'wikidata:Q223818'),
            ('The X was a biplane, the first aircraft launched from a ship.', 'X', 'wikidata:Q223818'),
            ('The X glider was a development of Y.', 'X', 'wikidata:Q2165278'),
            ('The X is a family of experimental tailless glider designs.', 'X', 'wikidata:Q2165278'),
            ('The X is a powered motor-glider and ultralight aircraft.', 'X', 'wikidata:Q1930290'),
        ]
        for text, label, parent in samples:
            with self.subTest(text=text):
                self.assertEqual(owned_physical_genus(text, label)[1], parent)

    def test_related_type_and_incidental_technology_are_not_own_kind(self):
        for text in ('The Y is a jet aircraft.', 'The X is an engine for jet aircraft.',
                     'The X is a virtual jet aircraft.', 'The X is a toy biplane.',
                     'The X is an aircraft using jet flap technology.'):
            with self.subTest(text=text):
                result = owned_physical_genus(text, 'X')
                self.assertTrue(result is None or result[1] == 'wordnet31:02689427-n')

    def test_numeric_model_suffix_cannot_expand_a_base_design(self):
        for suffix in ('500', 'C1', 'Mk II', 'NEO', 'MAX'):
            self.assertIsNone(owned_physical_genus('The X '+suffix+' is a jet aircraft.', 'X'))

    def test_different_article_title_is_not_an_owned_alias(self):
        data = {'enwiki_title': 'Another Model', 'evidence_record': {'wikipedia_title': 'Another Model'}}
        self.assertEqual(bound_owned_source_names(data, 'Named Flyer', 'Another Model is a biplane.'), [])

    def test_motor_glider_shared_glider_class_keeps_engine_compatible_scope(self):
        self.assertEqual(owned_physical_genus('The X is a glider and motor glider.', 'X')[1], 'wikidata:Q2165278')
        self.assertFalse(owned_reconfigurable_fixed_wing('The X is an aircraft based on a biplane.', 'X'))
        self.assertTrue(owned_reconfigurable_fixed_wing('The X was an aircraft that could fly either as a biplane or as a parasol winged monoplane.', 'X'))

    def test_named_member_and_single_prototype_have_distinct_roles(self):
        article = 'The Design is an early biplane. Two examples were built. One of them—the Named Flyer—in 1911 flew across a continent.'
        self.assertEqual(owned_named_instance_genus(article, 'Named Flyer')[1], 'wikidata:Q223818')
        self.assertIsNone(owned_named_instance_genus(article, 'Design'))
        self.assertIsNone(owned_named_instance_genus('The X is a biplane. Only one was built.', 'X'))


class OwnedScopeDatabaseContracts(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:'); self.c.row_factory = sqlite3.Row
        self.c.executescript('''
        CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,data TEXT,visibility TEXT,rank TEXT,component_id INTEGER,source TEXT);
        CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT);
        CREATE TABLE bridges(id INTEGER,left_uid TEXT,right_uid TEXT,relation TEXT,status TEXT);
        CREATE TABLE entity_relations(id INTEGER,subject_uid TEXT,object_uid TEXT,relation TEXT,status TEXT);
        CREATE TABLE edges(id INTEGER,child_uid TEXT,parent_uid TEXT,relation TEXT,status TEXT);
        ''')
        self.c.executemany('INSERT INTO nodes VALUES(?,?,?,?,?,?,?)', [
            ('model', 'X', dump({'description': 'single-engine biplane'}), 'ACTIVE', 'model', 1,'publisher'),
            ('wikidata:Q223818', 'biplane', dump({'definition': 'A biplane is a fixed-wing aircraft with two main wings stacked one above the other.'}), 'ACTIVE', '', 2,'publisher'),
        ])
        self.c.executemany('INSERT INTO node_profiles VALUES(?,?)', [('model','MODEL'),('wikidata:Q223818','CLASS')])
        rows = {r['uid']: dict(r) for r in self.c.execute('SELECT * FROM nodes')}
        proof = {'basis': 'OWNED_FIRST_SUBJECT_PHYSICAL_GENUS_WITH_COMPLETE_PARENT_RANGE',
                 'scope_observation': 'Own entire source and complete parent range retained.', 'license': 'Original source terms retained',
                 'native_record_sha256': sha(rows['model']['data']), 'parent_native_record_sha256': sha(rows['wikidata:Q223818']['data']),
                 'whole_subject_scope_review': True, 'world_identity_assertion': False, 'no_identity_merges': True,
                 'source_witnesses': [{'uid': u, 'data_sha256': sha(rows[u]['data']), 'field': f, 'statement': s} for u,f,s in [
                     ('model','description','single-engine biplane'), ('wikidata:Q223818','definition','A biplane is a fixed-wing aircraft with two main wings stacked one above the other.')]]}
        self.op = {'op': 'link','uid':'model','parent':'wikidata:Q223818','relation':'DESIGN_TYPE_OF','source':SOURCE,'uri':'https://publisher.example/design','proof':proof}
        self.manifest = {'schema':'FINEATLAS_OWNED_SCOPE_REPAIRS_V1','operation_count':1}

    def tearDown(self): self.c.close()

    def test_readonly_preflight_keeps_existing_source_bytes(self):
        before = self.c.total_changes
        validate_owned_scope_repairs(self.c,self.manifest,[self.op])
        self.assertEqual(self.c.total_changes,before)

    def test_changed_source_or_role_is_not_reused(self):
        self.c.execute("UPDATE nodes SET data='{}' WHERE uid='model'")
        with self.assertRaises(ValueError): validate_owned_scope_repairs(self.c,self.manifest,[self.op])

    def test_configuration_cannot_use_a_design_type_relation(self):
        self.c.execute("UPDATE node_profiles SET node_kind='CONFIGURATION' WHERE uid='model'")
        with self.assertRaises(ValueError): validate_owned_scope_repairs(self.c,self.manifest,[self.op])

    def test_duplicate_or_bad_count_is_rejected(self):
        manifest = {**self.manifest,'operation_count':2}
        with self.assertRaises(ValueError): validate_owned_scope_repairs(self.c,manifest,[self.op,self.op])
        with self.assertRaises(ValueError): validate_owned_scope_repairs(self.c,self.manifest,[self.op,self.op])

    def test_two_new_links_cannot_form_a_batch_cycle(self):
        ops = [{'op':'link','uid':'model','parent':'wikidata:Q223818'}, {'op':'link','uid':'wikidata:Q223818','parent':'model'}]
        with self.assertRaisesRegex(ValueError,'cycle'): validate_batch_cycles(self.c,ops,{})

    def test_alias_component_cycle_is_rejected(self):
        self.c.execute("INSERT INTO nodes VALUES('alias','alias','{}','ACTIVE','',1,'publisher')")
        self.c.execute("INSERT INTO node_profiles VALUES('alias','CLASS')")
        self.c.execute("INSERT INTO edges VALUES(1,'wikidata:Q223818','alias','IS_A','ACTIVE')")
        with self.assertRaisesRegex(ValueError,'cycle'): validate_batch_cycles(self.c,[self.op],{})

    def test_retiring_one_bridge_preserves_independent_source_partition(self):
        self.c.execute("INSERT INTO nodes VALUES('source','source','{}','ACTIVE','',2,'publisher')")
        self.c.execute("INSERT INTO bridges VALUES(1,'source','wikidata:Q223818','SAME_CONCEPT','ACTIVE')")
        parts = expected_partitions(self.c,[{'op':'review_bridge','uid':'source','before_assertion':{'id':1}}])
        self.assertEqual(parts[2],[['source'],['wikidata:Q223818']])
        self.assertEqual(self.c.execute('SELECT status FROM bridges').fetchone()[0],'ACTIVE')


if __name__ == '__main__': unittest.main()
