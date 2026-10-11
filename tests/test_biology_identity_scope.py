"""Real source-concept counterexample must not become a name-only split."""
import copy
import json
from pathlib import Path
import sqlite3
import unittest

from fineatlas.structure_biology_identity_scope import preflight, validate


class BiologicalIdentityScopeTest(unittest.TestCase):
    def setUp(self):
        self.payload=json.loads((Path(__file__).parent/'fixtures/carduelis_source_extent_counterexample.json').read_text())
        self.case=self.payload['repairs'][0]
        self.operations=[{'op':'split_identity_source','locator':self.case['locator'],
                          'proof':self.case['proof']}]
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
        self.c.execute('CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,source TEXT,rank TEXT,data TEXT,description TEXT,visibility TEXT,component_id INTEGER)')
        for i,node in enumerate(self.case['proof']['retained_nodes'],100):
            comp=1 if node['uid'] in self.case['prior_component_members'] else i
            self.c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?)',
                tuple(node[k] for k in ('uid','label','source','rank','data','description','visibility'))+(comp,))
        for table,row in [('bridges',self.case['before_bridge']),('edges',self.case['proof']['native_parent_witness'])]:
            self.c.execute('CREATE TABLE '+table+' ('+','.join(k+(' INTEGER' if type(v) is int else ' REAL' if type(v) is float else ' TEXT') for k,v in row.items())+')')
            self.c.execute('INSERT INTO '+table+' VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))

    def tearDown(self):
        self.c.close()

    def test_real_extent_inclusion_exclusion_and_original_source_rows(self):
        validate(self.payload,self.operations)
        preflight(self.c,self.payload)
        self.assertEqual(self.case['proof']['native_parent_witness']['child_uid'],'ott:559274')
        self.assertEqual(self.case['proof']['modern_excluded_species_record']['Scientific_name'],'Carduelis caniceps')

    def test_uncertain_annotation_alone_cannot_authorize_a_split(self):
        payload=copy.deepcopy(self.payload);payload['repairs'][0]['proof']['source_scope_conflict']=False
        operations=copy.deepcopy(self.operations);operations[0]['proof']=payload['repairs'][0]['proof']
        with self.assertRaisesRegex(ValueError,'preserve real entities'):
            validate(payload,operations)

    def test_same_scientific_scope_does_not_prove_different_extent(self):
        payload=copy.deepcopy(self.payload);proof=payload['repairs'][0]['proof']
        proof['modern_excluded_species_record']=copy.deepcopy(proof['modern_narrow_species_record'])
        operations=copy.deepcopy(self.operations);operations[0]['proof']=proof
        with self.assertRaisesRegex(ValueError,'separate species extent'):
            validate(payload,operations)

    def test_native_containment_drift_cannot_be_replaced_by_its_name(self):
        self.c.execute("UPDATE edges SET status='REVIEW'")
        with self.assertRaisesRegex(ValueError,'containment range counterexample'):
            preflight(self.c,self.payload)

    def test_changed_source_identity_evidence_must_fail_before_mutation(self):
        self.c.execute("UPDATE bridges SET source='different publisher'")
        with self.assertRaisesRegex(ValueError,'original ACTIVE'):
            preflight(self.c,self.payload)


if __name__=='__main__':
    unittest.main()
