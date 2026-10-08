"""Default selection, typed navigation and unsupported endpoint regressions."""
import json
import sqlite3
import unittest
from fineatlas import FineAtlas
import test_single

class UnifiedTest(unittest.TestCase):
    setUp=test_single.TypedInterfaceTest.setUp
    tearDown=test_single.TypedInterfaceTest.tearDown

    def unified(self,ready=True):
        self.tree.close()
        with sqlite3.connect(self.path) as c:
            c.executemany('INSERT OR REPLACE INTO metadata VALUES(?,?)',
                         [('default_relation_view',json.dumps('unified')),
                          ('unified_ready',json.dumps(ready))])
        self.tree=FineAtlas(self.path)

    def test_default_comes_from_snapshot_and_legacy_stays_explicit(self):
        self.unified()
        self.assertEqual(self.tree.relation_view,'unified')
        with FineAtlas(self.path,relation_view='strict') as old:
            self.assertEqual(old.relation_view,'strict')

    def test_incomplete_snapshot_cannot_expose_unified(self):
        self.tree.close()
        with sqlite3.connect(self.path) as c:
            c.execute("INSERT INTO metadata VALUES('default_relation_view','\"unified\"')")
        with self.assertRaises(ValueError):FineAtlas(self.path)

    def test_unknown_queries_are_structured(self):
        self.unified()
        self.assertEqual(self.tree.path_result('missing')['status'],'NOT_FOUND')
        self.assertEqual(self.tree.connection_status('missing')['status'],'NOT_FOUND')
        self.assertEqual(self.tree.ancestors_result('missing')['status'],'NOT_FOUND')
        self.assertEqual(self.tree.source_hierarchy('missing')['status'],'NOT_FOUND')
        self.assertIsNone(self.tree.distance('missing','type:river')['distance'])
        self.assertEqual(self.tree.domain_page('missing')['reason'],'UNKNOWN_DOMAIN')
        self.assertEqual(self.tree.search_page('river',domain='missing')['reason'],'UNKNOWN_DOMAIN')
        self.assertEqual(self.tree.browse_domain('missing')['reason'],'UNKNOWN_DOMAIN')

    def test_native_record_view_keeps_original_uids(self):
        self.unified()
        result=self.tree.source_hierarchy('type:river')
        self.assertFalse(result['identity_expanded'])
        self.assertEqual(result['items'][0]['parent_uid'],'type:root')
        self.assertEqual(len(self.tree.ancestors_result('type:river')['items']),1)

    def test_unified_does_not_use_undirected_mixed_distance(self):
        self.unified()
        self.assertEqual(self.tree.distance('type:root','type:river',direction='undirected')['status'],
                         'UNSUPPORTED_DIRECTION')

    def test_regulatory_navigation_is_visible_without_becoming_classification(self):
        self.tree.close()
        with sqlite3.connect(self.path) as c:
            c.execute("UPDATE nodes SET rank='model' WHERE uid='legacy:mixed'")
            c.execute("INSERT INTO entity_relations VALUES(4,'legacy:mixed','type:river','REGULATED_AS','ACTIVE','fixture','proof:1','{}')")
            c.executemany('INSERT OR REPLACE INTO metadata VALUES(?,?)',
                          [('default_relation_view',json.dumps('unified')),('unified_ready','true')])
        self.tree=FineAtlas(self.path)
        path=self.tree.path_result('legacy:mixed')
        self.assertEqual(path['status'],'CONNECTED')
        self.assertEqual(path['path'][-1]['edge']['relation'],'REGULATED_AS')
        result=self.tree.distance('legacy:mixed','type:river',policy='design')
        self.assertFalse(result['applicable'])
        self.assertIsNone(result['distance'])

if __name__=='__main__':unittest.main()
