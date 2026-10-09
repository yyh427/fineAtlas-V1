"""Organization facts retain source UID scope and stay outside classification."""
import json
from pathlib import Path
import sqlite3
import unittest
import test_single
from fineatlas import FineAtlas
from fineatlas.browse_index import build_browse_index


class SourceGroupsTest(unittest.TestCase):
    setUp = test_single.TypedInterfaceTest.setUp
    tearDown = test_single.TypedInterfaceTest.tearDown

    def build(self):
        self.tree.close()
        c = sqlite3.connect(self.path)
        c.executescript('''CREATE TABLE source_groups(group_uid TEXT PRIMARY KEY, namespace TEXT,source_version TEXT,source_group_id TEXT,label TEXT,parent_group_uid TEXT,source_uri TEXT,proof TEXT);
        CREATE TABLE source_group_members(group_uid TEXT,member_uid TEXT,source_member_id TEXT,relation TEXT,status TEXT,proof TEXT,PRIMARY KEY(group_uid,member_uid));
        CREATE TABLE source_field_values(uid TEXT,field TEXT,value TEXT,source TEXT,evidence_id TEXT,PRIMARY KEY(uid,field,value,source));''')
        for i in range(3):
            c.execute('INSERT INTO source_groups VALUES(?,?,?,?,?,?,?,?)',
                      (f'group:{i}', 'registry', '2026', str(i), f'Group {i}', None, 'https://example.org', '{"source_id":true}'))
        c.executemany('INSERT INTO source_group_members VALUES(?,?,?,?,?,?)',
                      [('group:0','type:river','native:1','ORGANIZATION_GROUP_MEMBER','ACTIVE','{}'),
                       ('group:0','geo:1','native:2','ORGANIZATION_GROUP_MEMBER','ACTIVE','{}'),
                       ('group:0','cat:1','native:3','ORGANIZATION_GROUP_MEMBER','REVIEW','{}')])
        c.execute("UPDATE node_profiles SET attributes=? WHERE uid='geo:1'",(json.dumps({'source_native_manufacturers':['Native Maker']}),))
        c.executemany('INSERT INTO source_field_values VALUES(?,?,?,?,?)',
                      [('geo:1','color','蓝色','source','proof:1'),
                       ('geo:1','organization_group','Registry Group 0','source','proof:1')])
        c.commit(); c.close()
        build_browse_index(self.path, Path(self.temp.name)/'reports')
        self.tree = FineAtlas(self.path)

    def test_source_members_are_distinct_and_review_does_not_enter(self):
        self.build()
        before = self.tree.path_result('geo:1')
        groups = self.tree.source_groups_page('registry', 1)
        self.assertEqual(groups['items'][0]['source_member_uids'], 2)
        page = self.tree.source_group_members_page('group:0', 1)
        self.assertTrue(page['has_more'])
        second = self.tree.source_group_members_page('group:0', 1, cursor=page['next_cursor'])
        self.assertFalse(second['has_more'])
        self.assertEqual({x['uid'] for x in page['items']+second['items']}, {'type:river','geo:1'})
        self.assertTrue(all(not x['is_a'] for x in page['items']))
        self.assertEqual(before, self.tree.path_result('geo:1'))
        with self.assertRaises(ValueError):
            self.tree.source_group_members_page('group:1', 1, cursor=page['next_cursor'])
        self.assertEqual(self.tree.source_group_members_page('absent')['status'], 'UNKNOWN_SOURCE_GROUP')
        path = Path(self.temp.name)/'groups.jsonl'
        self.assertEqual(self.tree.export_source_groups(path, namespace='registry')['source_memberships'], 2)
        self.assertTrue(all(not json.loads(line)['is_a'] for line in path.read_text().splitlines()))

    def test_metadata_facets_are_indexed_from_native_fields(self):
        self.build()
        for field, value in [('color','蓝色'),('organization_group','Registry Group 0'),('manufacturer','Native Maker')]:
            row = self.tree.con.execute('SELECT value FROM browse_facets WHERE uid=? AND facet=?', ('geo:1',field)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], value)
        items = self.tree.browse_children_page('type:river',node_kind='INSTANCE',filters={'color':'蓝色'})['items']
        self.assertEqual([x['uid'] for x in items], ['geo:1'])

    def test_old_database_has_explicit_unavailable_result(self):
        self.assertEqual(self.tree.source_groups_page()['status'], 'SOURCE_GROUPS_NOT_AVAILABLE')

if __name__ == '__main__':
    unittest.main()
