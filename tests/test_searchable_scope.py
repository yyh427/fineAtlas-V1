import json
import sqlite3
import unittest
from fineatlas import FineAtlas, __version__
from fineatlas.experiment import FineAtlasExperimentTool
from fineatlas.task_contract import RunConfig
import test_native755_contract as native_fixture


class SearchableScopeTest(unittest.TestCase):
    setUp=native_fixture.NativeContractTest.setUp
    tearDown=native_fixture.NativeContractTest.tearDown
    prepare=native_fixture.NativeContractTest.prepare

    def test_domain_expansion_issues_roots_before_descendants(self):
        def change(c):
            c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', ('domain_roots', json.dumps([
                {'domain':'fixture','uid':'fineatlas-domain:fixture','label':'fixture domain',
                 'root_uids':['type:root'],'description':'Configured source root'}])))
        self.prepare(change)
        tool=FineAtlasExperimentTool(RunConfig(str(self.path),'fixture-revision',__version__,'fixture-commit'))
        try:
            entry=tool.entries()['navigation_candidates'][0]
            roots=tool.scope(entry['handle'],dataset='fixture',expand=True)
            self.assertEqual(roots['candidates'],[])
            self.assertEqual([r['uid'] for r in roots['navigation_candidates']],['type:root'])
            route=roots['navigation_candidates'][0]['reachability']['path'][0]
            self.assertEqual(route['relation'],'DOMAIN_ENTRY_ROOT')
            self.assertFalse(route['strict_inclusion'])
            page=tool.scope(roots['navigation_candidates'][0]['handle'],dataset='fixture')
            self.assertIn('cat:1',[r['uid'] for r in page['candidates']])
        finally:tool.close()

    def test_reference_is_reachable_and_not_strict_inclusion(self):
        self.prepare()
        page=self.tree.scope_candidates('type:root',dataset='fixture',target_granularity=['source_category'])
        self.assertEqual([n['uid'] for n in page['items']],['cat:1'])
        path=page['items'][0]['reachability']
        self.assertEqual([e['relation'] for e in path['path']],['IS_A','DEPICTS_TYPE'])
        self.assertFalse(path['strict_descendant'])
        self.assertTrue(path['source_category_reference'])
        self.assertFalse(path['world_identity_equivalence_implied'])
        strict=self.tree.scope_candidates('type:root',route_mode='classification',target_granularity=['source_category'])
        self.assertEqual(strict['items'],[])

    def test_actual_expand_returns_reference_and_no_gold_is_required(self):
        self.prepare()
        self.assertIn('cat:1',[n['uid'] for n in self.tree.expand_scope('type:river')['items']])
        tool=FineAtlasExperimentTool(RunConfig(str(self.path),'fixture-revision',__version__,'fixture-commit'))
        try:
            with self.assertRaises(ValueError):tool.scope('type:river')
            initial=tool.query('Same Name',dataset='fixture')
            anchors=[r['handle'] for r in initial['candidates']+initial['navigation_candidates'] if r['uid']=='type:river']
            result=tool.scope(anchors,dataset='fixture',target_granularity=['source_category'])
            self.assertTrue(tool.allowed_choices(result))
            self.assertNotIn('cat:1',tool.candidate_wire(result))
            self.assertIn('source=',tool.candidate_wire(result))
            result['candidates'][0]['uid']='type:root'
            with self.assertRaises(ValueError):tool.allowed_choices(result)
        finally:tool.close()

    def test_multi_parent_aggregation_and_pagination(self):
        def change(c):
            c.execute("INSERT INTO entity_relations VALUES(99,'cat:1','type:root','DEPICTS_TYPE','ACTIVE','second source','proof:2','{}')")
        self.prepare(change)
        first=self.tree.scope_candidates('type:root',purpose='discovery',limit=1)
        found=[];cursor=None
        while True:
            page=self.tree.scope_candidates('type:root',purpose='discovery',limit=1,cursor=cursor)
            found.extend(page['items'])
            if not page['has_more']:break
            cursor=page['next_cursor']
        keys=[n['presentation_key'] for n in found]
        self.assertEqual(len(keys),len(set(keys)))
        cat=next(n for n in found if n['uid']=='cat:1')
        self.assertEqual(len(cat['reachability']['incoming_evidence']),2)
        if first['next_cursor']:
            with self.assertRaises(ValueError):self.tree.scope_candidates('type:river',cursor=first['next_cursor'])

    def test_budget_is_not_misreported_as_no_relationship(self):
        self.prepare()
        page=self.tree.scope_candidates('type:root',node_budget=1)
        self.assertFalse(page['diagnostics']['scan_complete'])
        self.assertIn('NODE_BUDGET',page['diagnostics']['incomplete_reasons'])

    def test_original_variant_grain_survives_native_unit_selection(self):
        def change(c):c.execute("UPDATE native_classes SET object_granularity='visual_variant'")
        self.prepare(change)
        page=self.tree.scope_candidates('type:root',dataset='fixture',target_granularity=['visual_variant'])
        self.assertEqual([n['uid'] for n in page['items']],['cat:1'])

    def test_scope_is_open_beyond_registered_native_classes(self):
        def change(c):
            c.execute("INSERT INTO nodes SELECT 'world:new','New type',domain,domains,source,'class',description,data,layer,visibility,6 FROM nodes WHERE uid='type:river'")
            c.execute('INSERT INTO components VALUES(6,1,1,0,88)')
            c.execute("INSERT INTO edges VALUES(88,'world:new','type:root','IS_A','ACTIVE','fixture',1,'{}','{}')")
        self.prepare(change)
        page=self.tree.scope_candidates('type:root',dataset='fixture')
        self.assertIn('world:new',[n['uid'] for n in page['items']])
        self.assertNotIn('world:new',self.tree._range_native_uids)

    def test_design_reference_has_its_own_role_contract(self):
        from fineatlas.hierarchy import validate_link_roles
        validate_link_roles('DEPICTS_DESIGN','DATASET_CATEGORY','MODEL')
        with self.assertRaises(ValueError):validate_link_roles('DEPICTS_TYPE','DATASET_CATEGORY','MODEL')
        with self.assertRaises(ValueError):validate_link_roles('DEPICTS_DESIGN','CLASS','MODEL')

    def test_cached_pages_are_not_mutated_by_caller_results(self):
        self.prepare()
        page=self.tree.scope_candidates('type:root',dataset='fixture',target_granularity=['source_category'])
        page['items'][0]['uid']='fake:gold'
        page['items'][0]['reachability']['path'][0]['relation']='FALSE_EQUIVALENCE'
        again=self.tree.scope_candidates('type:root',dataset='fixture',target_granularity=['source_category'])
        self.assertEqual(again['items'][0]['uid'],'cat:1')
        self.assertEqual(again['items'][0]['reachability']['path'][0]['relation'],'IS_A')

    def test_source_concept_and_world_component_scope_conflict_is_isolated(self):
        def change(c):
            c.execute("INSERT INTO node_profiles VALUES('type:river','CLASS','fixture','','proof:1',?)",(json.dumps({'identity_scope':'SOURCE_VERSION_CONCEPT'}),))
            c.execute("INSERT INTO nodes SELECT 'world:alias','Same Name',domain,domains,source,rank,description,data,layer,visibility,component_id FROM nodes WHERE uid='type:river'")
        self.prepare(change)
        identity=self.tree._presentation_identity('type:river')
        self.assertEqual(identity['status'],'ISOLATED_REVIEW')
        self.assertEqual(identity['reason'],'IDENTITY_SCOPE_CONFLICT')

    def test_missing_rank_uses_proven_component_declared_rank(self):
        def change(c):
            c.execute("UPDATE nodes SET rank='' WHERE uid='type:river'")
            c.execute("INSERT INTO nodes SELECT 'world:alias','Known Species',domain,domains,source,'species',description,data,layer,visibility,component_id FROM nodes WHERE uid='type:river'")
            c.execute("INSERT INTO bridges VALUES(77,'type:river','world:alias','SAME_CONCEPT','ACTIVE',1,'{}')")
        self.prepare(change)
        grain=self.tree.effective_granularity('type:river')
        self.assertEqual(grain['rank'],'species')
        self.assertEqual(grain['basis'],'ACCEPTED_IDENTITY_COMPONENT_DECLARED_RANK')
        self.assertIn(77,grain['bridge_ids'])

    def test_declared_source_unit_does_not_depend_on_world_confirmation(self):
        def change(c):
            c.execute("UPDATE node_profiles SET attributes=? WHERE uid='cat:1'",(json.dumps({'source_unit':'publisher_breed_label'}),))
        self.prepare(change)
        self.assertEqual([n['uid'] for n in self.tree.scope_candidates('type:root',dataset='fixture',target_granularity=['breed'])['items']],['cat:1'])
        self.assertFalse(self.tree.world_mapping_status('fixture','1')['world_identity_verified'])


if __name__=='__main__':unittest.main()
