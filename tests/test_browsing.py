"""Independent public browse regressions: roles, views, source identity, pages."""
import json
import sqlite3
from pathlib import Path
import unittest

import test_single
from fineatlas import FineAtlas
from fineatlas.browse_index import build_browse_index


class BrowsingTest(unittest.TestCase):
    setUp=test_single.TypedInterfaceTest.setUp
    tearDown=test_single.TypedInterfaceTest.tearDown

    def build(self, change=None):
        self.tree.close()
        c=sqlite3.connect(self.path)
        if change:change(c)
        c.commit();c.close()
        build_browse_index(self.path,Path(self.temp.name)/'reports')
        self.tree=FineAtlas(self.path)

    def add(self,c,uid,component,kind='MODEL',data=None,allowed=None):
        c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (uid,uid,'fixture','["fixture"]','faa',kind.lower(),'Native fixture definition',json.dumps(data or {}),'fixture','ACTIVE',component))
        c.execute('INSERT OR IGNORE INTO components VALUES(?,?,?,?,?)',(component,0,None,None,None))
        c.execute('INSERT INTO node_profiles VALUES(?,?,?,?,?,?)',
            (uid,kind,'fixture','https://example.org','proof:1',json.dumps({'allowed_views':allowed} if allowed else {})))

    def test_direct_typed_pages_do_not_confuse_descendants_and_types(self):
        def change(c):
            self.add(c,'family',10,'MODEL_FAMILY')
            self.add(c,'model',11)
            self.add(c,'sku',12,'CONFIGURATION')
            c.executemany('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',[
                (20,'family','type:river','DESIGN_TYPE_OF','ACTIVE','fixture','proof:1','{}'),
                (21,'model','family','NATIVE_DESIGN_PARENT','ACTIVE','fixture','proof:1','{}'),
                (22,'sku','model','CONFIGURATION_OF','ACTIVE','fixture','proof:1','{}')])
        self.build(change)
        self.assertEqual(self.tree.browse_children_page('type:river')['items'],[])
        family=self.tree.browse_children_page('type:river',node_kind='SERIES')['items']
        self.assertEqual([n['uid'] for n in family],['family'])
        self.assertEqual(self.tree.browse_children_page('family',node_kind='MODEL')['items'][0]['uid'],'model')
        self.assertEqual(self.tree.browse_children_page('model',node_kind='CONFIGURATION')['items'][0]['uid'],'sku')
        self.assertEqual(self.tree.browse_children_page('model',node_kind='CONFIGURATION')['items'][0]['browse_connections'][0]['relation'],'CONFIGURATION_OF')

    def test_keyset_complete_deduplicated_and_context_bound(self):
        def change(c):
            for i in range(17):
                self.add(c,f'm:{i:02d}',10+i,data={'MFR':'EXPLICIT MAKER','MODEL':'Source designation'})
                c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',(30+i,f'm:{i:02d}','type:river','DESIGN_TYPE_OF','ACTIVE','fixture','proof:1','{}'))
            self.add(c,'peer:00',10,data={'MFR':'EXPLICIT MAKER'})
            c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',(60,'peer:00','type:river','DESIGN_TYPE_OF','ACTIVE','second','proof:1','{}'))
        self.build(change)
        cursor=None;components=[]
        while True:
            page=self.tree.browse_children_page('type:river',4,node_kind='MODEL',cursor=cursor,filters={'manufacturer':'EXPLICIT MAKER'})
            self.assertLessEqual(len(page['items']),4)
            components += [n['identity_component'] for n in page['items']]
            cursor=page['next_cursor']
            if not cursor:break
        self.assertEqual(components,list(range(10,27)))
        p=self.tree.browse_children_page('type:river',4,node_kind='MODEL')
        with self.assertRaises(ValueError):
            self.tree.browse_children_page('type:river',4,node_kind='CLASS',cursor=p['next_cursor'])
        with FineAtlas(self.path,relation_view='taxonomy') as tree:
            with self.assertRaises(ValueError):tree.browse_children_page('type:river',4,node_kind='MODEL',cursor=p['next_cursor'])
        self.assertEqual(len(self.tree.source_members_page('m:00')['items']),2)

    def test_catalogue_facets_are_exact_not_name_prefixes(self):
        def change(c):
            for i,raw in enumerate([{'MFR':'Maker A'},{'MFR':'Maker B'},{}]):
                self.add(c,f'Maker A fictional prefix {i}',20+i,data=raw)
                c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',(30+i,f'Maker A fictional prefix {i}','type:river','DESIGN_TYPE_OF','ACTIVE','fixture','proof:1','{}'))
        self.build(change)
        groups=self.tree.browse_groups('type:river')
        self.assertEqual([x['value'] for x in groups['items']],['Maker A','Maker B'])
        self.assertTrue(all(not x['is_a'] for x in groups['items']))
        self.assertEqual(len(self.tree.browse_children_page('type:river',node_kind='MODEL')['items']),3)
        self.assertEqual(len(self.tree.browse_children_page('type:river',node_kind='MODEL',filters={'manufacturer':'Maker A'})['items']),1)

    def test_views_visibility_and_role_contract_are_respected(self):
        def change(c):
            self.add(c,'native-only',30,allowed=['taxonomy'])
            self.add(c,'wrong-role',31,'INSTANCE')
            c.executemany('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',[
                (30,'native-only','type:river','DESIGN_TYPE_OF','ACTIVE','fixture','proof:1','{}'),
                (31,'wrong-role','type:river','DESIGN_TYPE_OF','ACTIVE','fixture','proof:1','{}')])
        self.build(change)
        self.assertEqual(self.tree.browse_children_page('type:river',node_kind='MODEL')['items'],[])
        with FineAtlas(self.path,relation_view='taxonomy') as tree:
            self.assertEqual(tree.browse_children_page('type:river',node_kind='MODEL')['items'][0]['uid'],'native-only')
        self.assertEqual(self.tree.browse_children_page('type:river',node_kind='INSTANCE')['items'][0]['uid'],'geo:1')

    def test_structured_missing_parent_and_index(self):
        self.assertEqual(self.tree.browse_children_page('absent')['status'],'NOT_FOUND')
        self.assertEqual(self.tree.browse_children_page('type:river')['status'],'INDEX_REQUIRED')
        self.build()
        self.assertEqual(self.tree.browse_location('absent')['status'],'NOT_FOUND')
        self.assertEqual(self.tree.locate('same name','bad-domain')['status'],'UNKNOWN_DOMAIN')
        self.assertEqual(self.tree.browse_children_page('type:root')['items'][0]['uid'],'type:river')

    def test_preferred_configuration_route_preserves_full_source_connections(self):
        def change(c):
            self.add(c,'base',10,'MODEL')
            self.add(c,'variant',11,'CONFIGURATION')
            self.add(c,'year-config',12,'CONFIGURATION')
            c.executemany('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',[
                (30,'base','type:river','DESIGN_TYPE_OF','ACTIVE','fixture','proof:1','{}'),
                (31,'variant','base','CONFIGURATION_OF','ACTIVE','fixture','proof:1','{}'),
                (32,'year-config','variant','CONFIGURATION_OF','ACTIVE','fixture','proof:1','{}'),
                (33,'year-config','base','CONFIGURATION_OF','ACTIVE','fixture','proof:1','{}')])
            c.executemany('INSERT INTO entity_connections VALUES(?,?,?,?,?)',[
                ('base',1,'type:river',30,2),('variant',1,'base',31,3),('year-config',1,'base',33,3)])
        self.build(change)
        old=self.tree.path_result('year-config')
        specific=self.tree.browse_path_result('year-config')
        self.assertEqual(specific['status'],'CONNECTED')
        self.assertEqual(specific['shortest_distance'],old['distance'])
        self.assertGreater(specific['distance'],old['distance'])
        self.assertEqual([s['uid'] for s in specific['path']][-2:],['variant','year-config'])
        preferred=self.tree.browse_children_page('base',node_kind='CONFIGURATION')
        full=self.tree.browse_children_page('base',node_kind='CONFIGURATION',include_coarse=True)
        self.assertEqual([n['uid'] for n in preferred['items']],['variant'])
        self.assertEqual({n['uid'] for n in full['items']},{'variant','year-config'})
        self.assertEqual(self.tree.con.execute("SELECT status FROM entity_relations WHERE id=33").fetchone()[0],'ACTIVE')

    def test_regulatory_relationship_is_not_replaced_by_physical_type_path(self):
        def change(c):
            self.add(c,'base',10,'MODEL')
            self.add(c,'sku',11,'CONFIGURATION')
            c.executemany('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',[
                (30,'base','type:river','DESIGN_TYPE_OF','ACTIVE','fixture','proof:1','{}'),
                (31,'sku','base','CONFIGURATION_OF','ACTIVE','fixture','proof:1','{}'),
                (32,'sku','type:river','REGULATED_AS','ACTIVE','fixture','proof:1','{}')])
        self.build(change)
        self.assertEqual(self.tree.con.execute("SELECT count(*) FROM browse_preferences WHERE relation='REGULATED_AS'").fetchone()[0],0)

    def test_finer_route_cursor_cannot_be_reused_in_full_source_mode(self):
        def change(c):
            for i in range(3):
                self.add(c,'p:'+str(i),10+i)
                c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',(30+i,'p:'+str(i),'type:river','DESIGN_TYPE_OF','ACTIVE','fixture','proof:1','{}'))
        self.build(change)
        page=self.tree.browse_children_page('type:river',1,node_kind='MODEL')
        with self.assertRaises(ValueError):
            self.tree.browse_children_page('type:river',1,node_kind='MODEL',cursor=page['next_cursor'],include_coarse=True)

    def test_cached_catalogue_counts_equal_filtered_identity_pages(self):
        def change(c):
            for i in range(103):
                self.add(c,'model:'+str(i),10+i,data={'MFR':'A' if i<70 else 'B'})
                c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',
                          (30+i,'model:'+str(i),'type:river','DESIGN_TYPE_OF','ACTIVE','fixture','proof:1','{}'))
        self.build(change)
        groups=self.tree.browse_groups('type:river')
        self.assertTrue(groups['count_index_used'])
        self.assertEqual([(g['value'],g['concepts']) for g in groups['items']],[('A',70),('B',33)])
        for group in groups['items']:
            page=self.tree.browse_children_page('type:river',1000,node_kind='MODEL',filters=group['filters'])
            self.assertEqual(len(page['items']),group['concepts'])

    def test_custom_root_does_not_expose_outside_parent(self):
        self.build()
        with FineAtlas(self.path,root='type:river') as scoped:
            self.assertEqual(scoped.browse_children_page('type:root')['status'],'OUT_OF_ROOT')
            self.assertEqual(scoped.browse_children_page('type:river',node_kind='INSTANCE')['items'][0]['uid'],'geo:1')

    def test_admin_groups_require_both_native_country_and_admin(self):
        def change(c):
            for i,attributes in enumerate([{'country_code':'','admin_codes':['01']},
                                            {'country_code':'US','admin_codes':['']},
                                            {'country_code':'US','admin_codes':['CA']}]):
                uid='place:'+str(i);self.add(c,uid,10+i,'INSTANCE')
                c.execute('UPDATE node_profiles SET attributes=? WHERE uid=?',(json.dumps(attributes),uid))
                c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',
                          (30+i,uid,'type:river','INSTANCE_OF','ACTIVE','fixture','proof:1','{}'))
        self.build(change)
        self.assertEqual([g['value'] for g in self.tree.browse_groups('type:river','admin1',node_kind='INSTANCE')['items']],['US:CA'])

    def test_memory_staging_preserves_source_and_requires_matching_revision(self):
        self.tree.close()
        before=self.path.read_bytes()
        output=Path(self.temp.name)/'staging.sqlite'
        result=build_browse_index(output,Path(self.temp.name)/'stage-reports',source=self.path,release='fixture-review')
        self.assertTrue(result['staging_artifact_needs_attachment_to_candidate'])
        self.assertEqual(before,self.path.read_bytes())
        with sqlite3.connect(output) as staged:
            self.assertEqual(json.loads(staged.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0]),'FINEATLAS_BROWSE_INDEX_V1')
            self.assertGreater(staged.execute('SELECT count(*) FROM browse_links').fetchone()[0],0)
        self.tree=FineAtlas(self.path)

    def test_finer_route_lookup_uses_child_index_before_statistics_exist(self):
        # A tiny fixture cannot expose the catastrophic full-view scan, so
        # verify the critical access path independently of measured runtimes.
        from fineatlas.browse_preferences import build_preferences
        from fineatlas.browse_index import SCHEMA
        with sqlite3.connect(':memory:') as c:
            c.executescript(SCHEMA);statements=[]
            c.set_trace_callback(statements.append);build_preferences(c)
            c.set_trace_callback(None)
            query=next(q for q in statements if q.startswith('INSERT OR IGNORE INTO browse_preferences'))
            plan=[r[-1] for r in c.execute('EXPLAIN QUERY PLAN '+query)]
            self.assertTrue(any('SEARCH first USING INDEX browse_links_child' in step and 'child_component=?' in step for step in plan),plan)


if __name__=='__main__':unittest.main()
