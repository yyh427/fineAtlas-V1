"""Rank uncertainty cannot be bypassed through another identity representation."""
import json
import sqlite3
import unittest
import test_single
from fineatlas import FineAtlas


class TaxonRankReviewTest(unittest.TestCase):
    setUp=test_single.TypedInterfaceTest.setUp
    tearDown=test_single.TypedInterfaceTest.tearDown

    def test_review_blocks_species_inheritance_but_preserves_hierarchy(self):
        self.tree.close()
        c=sqlite3.connect(self.path)
        c.execute('CREATE TABLE node_taxon_ranks(uid TEXT PRIMARY KEY,rank TEXT,status TEXT,evidence_id TEXT,source TEXT)')
        c.execute("INSERT INTO nodes SELECT 'scientific:peer',label,domain,domains,source,'species',description,data,layer,visibility,component_id FROM nodes WHERE uid='type:river'")
        c.execute("INSERT INTO node_taxon_ranks VALUES('type:river',NULL,'MULTI_SPECIES_SCOPE_REVIEW','proof:1','independent scope review')")
        c.commit();c.close();self.tree=FineAtlas(self.path)
        node=self.tree.node('type:river')
        self.assertIsNone(node['normalized_rank'])
        self.assertEqual(node['rank_status'],'MULTI_SPECIES_SCOPE_REVIEW')
        self.assertFalse(self.tree.eligibility('type:river','species')['usable'])
        self.assertTrue(self.tree.eligibility('type:river','hierarchy')['usable'])
        self.assertEqual(self.tree.path_result('type:river')['status'],'CONNECTED')
        self.assertEqual(self.tree.node('scientific:peer')['native_rank'],'species')

if __name__=='__main__':unittest.main()
