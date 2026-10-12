"""Scope, identity and gold-blind inference regressions on independent tiny graphs."""
import inspect
import json
import sqlite3
import unittest

from fineatlas import FineAtlas, __version__
from fineatlas.experiment import FineAtlasExperimentTool
from fineatlas.task_contract import RunConfig, exact_name
import test_single


class NativeContractTest(unittest.TestCase):
    setUp = test_single.TypedInterfaceTest.setUp
    tearDown = test_single.TypedInterfaceTest.tearDown

    def prepare(self, change=None):
        self.tree.close()
        with sqlite3.connect(self.path) as c:
            for name in ('label', 'target_uid', 'identity_basis', 'granularity_basis', 'evidence_ids', 'provenance'):
                c.execute('ALTER TABLE dataset_targets ADD COLUMN ' + name + ' TEXT')
            c.execute("INSERT INTO dataset_targets VALUES('fixture','1','VERIFIED','river/outdoor','type:river','','','[]','{}')")
            c.executescript('''
            CREATE TABLE dataset_mapping_checks(dataset TEXT,class_id TEXT,status TEXT,reason TEXT,proof TEXT);
            INSERT INTO dataset_mapping_checks VALUES('fixture','1','ANNOTATION_SCOPE_REVIEW','Unconfirmed original range','{}');
            CREATE TABLE native_classes(dataset TEXT,class_id TEXT,namespace TEXT,source_version TEXT,uid TEXT,
              label TEXT,raw_label TEXT,role TEXT,object_granularity TEXT,domain TEXT,training_id_verified INTEGER,
              proof TEXT,evidence_ids TEXT);
            INSERT INTO native_classes VALUES('fixture','1','fixture-native','v1','cat:1','river/outdoor',
              'river/outdoor','DATASET_CATEGORY','supervision_label','fixture',1,'{"source":"original"}','["proof:1"]');
            CREATE TABLE native_class_names(uid TEXT,name TEXT,normalized_name TEXT,search_name TEXT,evidence_id TEXT);
            INSERT INTO native_class_names VALUES('cat:1','river/outdoor','river/outdoor','river outdoor','proof:1');
            CREATE TABLE world_mapping_dispositions(dataset TEXT,class_id TEXT,uid TEXT,stored_status TEXT,
              effective_status TEXT,reason TEXT,missing_evidence TEXT,evidence_ids TEXT);
            INSERT INTO world_mapping_dispositions VALUES('fixture','1','type:river','VERIFIED','REVIEW',
              'Original range unresolved','Author range proof','["proof:1"]');
            ''')
            c.executemany('INSERT OR REPLACE INTO metadata VALUES(?,?)',
                          [('database_revision', json.dumps('fixture-revision')),
                           ('repair_code_commit', json.dumps('fixture-commit')),
                           ('default_relation_view', json.dumps('unified')), ('unified_ready', 'true')])
            if change:
                change(c)
        self.tree = FineAtlas(self.path)

    def test_review_keeps_native_supervision_and_is_not_world_exact(self):
        self.prepare()
        self.assertTrue(self.tree.native_class('fixture', '1')['native_usable'])
        world = self.tree.target('fixture', '1')
        self.assertEqual(world['decision_status'], 'VERIFIED')
        self.assertFalse(world['identity_verified'])
        result = self.tree.evaluate_exact('fixture', '1', predicted_uid='cat:1')
        self.assertTrue(result['native_exact'])
        self.assertIsNone(result['world_exact'])
        self.assertIsNone(result['hierarchy_reward'])
        self.assertFalse(self.tree.evaluate_exact('fixture', '1', predicted_uid='type:river')['native_exact'])

    def test_full_qualifiers_survive_name_evaluation(self):
        self.prepare()
        self.assertTrue(self.tree.evaluate_exact('fixture', '1', predicted_label='RIVER/OUTDOOR')['native_exact'])
        self.assertFalse(self.tree.evaluate_exact('fixture', '1', predicted_label='river')['native_exact'])
        self.assertNotEqual(exact_name('BMW Z4 Convertible 2012'), exact_name('BMW Z4 Coupe 2012'))
        self.assertNotEqual(exact_name('BAE 146-200'), exact_name('BAE 146-300'))

    def test_legacy_world_registry_native_reference_remains_native_exact(self):
        def change(c):
            c.execute("UPDATE dataset_targets SET target_uid='cat:1',decision_status='VERIFIED_NATIVE_LABEL'")
            c.execute("UPDATE world_mapping_dispositions SET uid='cat:1'")
        self.prepare(change)
        world = self.tree.world_mapping_status('fixture','1')
        self.assertEqual(world['target_object_scope'], 'SOURCE_NATIVE_LABEL')
        result = self.tree.evaluate_exact('fixture','1', predicted_uid=world['uid'])
        self.assertTrue(result['native_exact'])
        self.assertIsNone(result['world_exact'])

    def test_unregistered_native_scope_is_never_a_world_answer(self):
        def change(c):
            c.execute('INSERT INTO node_profiles VALUES(?,?,?,?,?,?)', ('type:river','CLASS','fixture','',
                'proof:1', json.dumps({'identity_scope':'SOURCE_NATIVE_DATASET_CATEGORY'})))
        self.prepare(change)
        self.assertFalse(self.tree.candidate_contract('type:river')['world_answer_eligible'])
        self.assertEqual(self.tree.world_mapping_status('fixture','1')['target_object_scope'], 'SOURCE_NATIVE_LABEL')

    def test_ambiguous_full_name_returns_candidates_and_no_exact_guess(self):
        def change(c):
            c.execute("INSERT INTO native_classes SELECT dataset,'2',namespace,source_version,'type:root',label,raw_label,role,object_granularity,domain,training_id_verified,proof,evidence_ids FROM native_classes")
            c.execute("INSERT INTO native_class_names VALUES('type:root','river/outdoor','river/outdoor','river outdoor','proof:1')")
        self.prepare(change)
        result = self.tree.resolve_native_name('river/outdoor', dataset='fixture')
        self.assertEqual(result['status'], 'AMBIGUOUS')
        self.assertEqual(len(result['items']), 2)
        self.assertFalse(self.tree.evaluate_exact('fixture', '1', predicted_label='river/outdoor')['native_exact'])

    def test_query_has_no_gold_arguments_and_constraints_use_returned_handles(self):
        self.prepare()
        config = RunConfig(str(self.path), 'fixture-revision', __version__, 'fixture-commit')
        tool = FineAtlasExperimentTool(config)
        try:
            result = tool.query('river/outdoor')
            handles = tool.allowed_choices(result)
            self.assertTrue(handles)
            self.assertTrue(all(h in tool._choices for h in handles))
            with self.assertRaises(ValueError):
                tool.select('unreturned-gold-choice')
            wire = tool.candidate_wire(result)
            self.assertNotIn('cat:1', wire)
            self.assertNotIn('class_id', wire)
            self.assertNotIn('class_id', inspect.signature(tool.query).parameters)
            self.assertNotIn('gold', inspect.signature(tool.query).parameters)
            self.assertEqual(result['inference_mode'], 'open')
        finally:
            tool.close()

    def test_configuration_rejects_whitelist_and_reward_without_explicit_mode(self):
        with self.assertRaises(ValueError):
            RunConfig('db', 'revision', 'sdk', 'commit', closed_dataset='fixture')
        with self.assertRaises(ValueError):
            RunConfig('db', 'revision', 'sdk', 'commit', hierarchy_reward_enabled=True)

    def test_issued_constraints_reject_mutated_identity_or_task_context(self):
        self.prepare()
        config = RunConfig(str(self.path), 'fixture-revision', __version__, 'fixture-commit')
        with FineAtlasExperimentTool(config) as tool:
            result = tool.query('river/outdoor')
            handle = result['candidates'][0]['handle']
            original_uid = result['candidates'][0]['uid']
            result['candidates'][0]['uid'] = 'type:river'
            with self.assertRaisesRegex(ValueError, 'modified'):
                tool.allowed_choices(result)
            self.assertEqual(tool.select(handle)['uid'], original_uid)

    def test_short_model_tokens_are_not_silently_dropped(self):
        def change(c):
            c.execute("INSERT INTO aliases VALUES('bmw z4 convertible 2012','type:river')")
            c.execute("INSERT INTO aliases VALUES('bmw 128 convertible 2012','geo:1')")
        self.prepare(change)
        self.assertEqual([n['uid'] for n in self.tree.search('BMW Z4 Convertible 2012')], ['type:river'])

    def test_navigation_is_filtered_before_answer_budget(self):
        def change(c):
            c.execute("UPDATE nodes SET label='river/outdoor' WHERE uid='type:root'")
            c.execute("UPDATE nodes SET label='Native river label' WHERE uid='cat:1'")
            c.execute("INSERT INTO aliases VALUES('river outdoor','type:root')")
        self.prepare(change)
        page = self.tree.candidate_search('river/outdoor', 1, dataset='fixture', purpose='answers')
        self.assertEqual(page['items'][0]['uid'], 'cat:1')
        navigation = self.tree.candidate_search('river/outdoor', 1, dataset='fixture', purpose='navigation')
        self.assertEqual(navigation['items'][0]['uid'], 'type:root')

    def test_bad_native_role_or_missing_proof_cannot_enter_supervision(self):
        for clause in ("role='MODEL'", "proof='{}'"):
            if clause != "role='MODEL'":
                self.tearDown(); self.setUp()
            self.prepare(lambda c: c.execute('UPDATE native_classes SET ' + clause))
            self.assertFalse(self.tree.native_class('fixture', '1')['native_usable'])
            self.assertFalse(self.tree.candidate_contract('cat:1', dataset='fixture')['native_answer_eligible'])

    def test_source_class_tables_are_not_an_open_world_whitelist(self):
        def change(c):
            c.execute('CREATE TABLE dataset_answer_contracts(dataset TEXT,payload TEXT)')
            c.execute('INSERT INTO dataset_answer_contracts VALUES(?,?)', ('cub200', json.dumps({'world_roles':['CLASS'], 'world_ranks':['species']})))
            c.execute("INSERT INTO nodes SELECT 'species:unregistered','Unregistered bird',domain,domains,source,'species',description,data,layer,visibility,33 FROM nodes WHERE uid='type:root'")
            c.execute('INSERT INTO components VALUES(33,1,1,0,NULL)')
        self.prepare(change)
        self.assertTrue(self.tree.candidate_contract('species:unregistered', dataset='cub200')['world_answer_eligible'])
        self.assertFalse(self.tree.candidate_contract('type:root')['answer_eligible'])

    def test_task_navigation_component_is_not_a_final_answer(self):
        def change(c):
            c.execute('CREATE TABLE dataset_answer_contracts(dataset TEXT,payload TEXT)')
            c.execute('INSERT INTO dataset_answer_contracts VALUES(?,?)',
                      ('cub200', json.dumps({'world_roles':['CLASS'], 'navigation_only_uids':['type:river']})))
        self.prepare(change)
        result = self.tree.candidate_contract('type:river', dataset='cub200')
        self.assertFalse(result['answer_eligible'])
        self.assertTrue(result['navigation_eligible'])
        self.assertEqual(result['reason'], 'TASK_COARSE_OBJECT_IS_NAVIGATION_ONLY')
        self.assertTrue(self.tree.candidate_contract('cat:1', dataset='fixture')['answer_eligible'])

    def test_object_scope_preserves_unregistered_bird_and_rejects_other_species(self):
        def change(c):
            c.execute('CREATE TABLE dataset_answer_contracts(dataset TEXT,payload TEXT)')
            c.execute('INSERT INTO dataset_answer_contracts VALUES(?,?)', ('cub200', json.dumps({
                'world_roles':['CLASS'], 'world_ranks':['species'], 'world_navigation_anchors':['bird:root']})))
            for uid,rank,comp in [('bird:root','class',33),('bird:outside','species',34),('other:species','species',35)]:
                c.execute("INSERT INTO nodes SELECT ?,?,domain,domains,source,?,description,data,layer,visibility,? FROM nodes WHERE uid='type:root'", (uid,uid,rank,comp))
                c.execute('INSERT INTO components VALUES(?,1,1,0,NULL)', (comp,))
            c.execute("INSERT INTO edges VALUES(10,'bird:outside','bird:root','IS_A','ACTIVE','fixture',1,'[\"proof:1\"]','{}')")
            c.execute("INSERT INTO edges VALUES(11,'bird:root','type:root','IS_A','ACTIVE','fixture',1,'[\"proof:1\"]','{}')")
        self.prepare(change)
        self.assertTrue(self.tree.candidate_contract('bird:outside', dataset='cub200')['world_answer_eligible'])
        result = self.tree.candidate_contract('other:species', dataset='cub200')
        self.assertFalse(result['world_answer_eligible'])
        self.assertTrue(result['navigation_eligible'])

    def test_unknown_world_class_unit_is_navigation_without_guessing_rank(self):
        def change(c):
            c.execute('CREATE TABLE dataset_answer_contracts(dataset TEXT,payload TEXT)')
            c.execute('INSERT INTO dataset_answer_contracts VALUES(?,?)', ('cub200', json.dumps({
                'world_roles':['CLASS'], 'require_world_class_unit_evidence':True})))
        self.prepare(change)
        result = self.tree.candidate_contract('type:river', dataset='cub200')
        self.assertFalse(result['world_answer_eligible'])
        self.assertEqual(result['reason'], 'WORLD_CLASS_UNIT_NOT_ESTABLISHED_FOR_TASK')

    def test_confirmed_object_scope_does_not_require_navigation_path(self):
        def change(c):
            c.execute("UPDATE dataset_mapping_checks SET status='VERIFIED'")
            c.execute("UPDATE world_mapping_dispositions SET effective_status='CONFIRMED'")
            c.execute("DELETE FROM edges WHERE child_uid='type:river'")
            c.execute('CREATE TABLE dataset_answer_contracts(dataset TEXT,payload TEXT)')
            c.execute('INSERT INTO dataset_answer_contracts VALUES(?,?)',
                      ('fixture', json.dumps({'world_roles':['CLASS'], 'world_navigation_anchors':['unreachable:anchor']})))
        self.prepare(change)
        self.assertTrue(self.tree.world_mapping_status('fixture','1')['world_identity_verified'])
        self.assertTrue(self.tree.candidate_contract('type:river', dataset='fixture')['world_answer_eligible'])
        self.assertTrue(self.tree.evaluate_exact('fixture','1', predicted_uid='type:river')['native_exact'])


class PresentationTest(unittest.TestCase):
    setUp = test_single.TypedInterfaceTest.setUp
    tearDown = test_single.TypedInterfaceTest.tearDown

    def prepare(self, *, conflicting_role=False, mismatched_rank=False, proved=True):
        self.tree.close()
        with sqlite3.connect(self.path) as c:
            c.execute("INSERT INTO nodes SELECT 'type:river2',label,domain,domains,source,?,description,data,layer,visibility,component_id FROM nodes WHERE uid='type:river'",
                      ('species' if mismatched_rank else 'model' if conflicting_role else 'class',))
            c.execute("INSERT INTO aliases VALUES('same name','type:river2')")
            if proved:
                c.execute("INSERT INTO bridges VALUES(1,'type:river','type:river2','SAME_CONCEPT','ACTIVE',1,'{\"evidence\":\"independent identifiers\"}')")
        self.tree = FineAtlas(self.path)

    def test_accepted_identity_aggregation_happens_before_limit_and_preserves_sources(self):
        self.prepare()
        result = self.tree.candidate_search('Same Name', 2)
        self.assertEqual(len(result['items']), 2)
        merged = [r for r in result['items'] if len(r['representations']) == 2]
        self.assertEqual(len(merged), 1)
        self.assertEqual(result['diagnostics']['aggregated_slots'], 1)
        self.assertEqual(len(self.tree.exact('Same Name')), 3)

    def test_same_name_different_identity_is_retained(self):
        self.prepare()
        result = self.tree.candidate_search('Same Name', 10)
        self.assertEqual(len(result['items']), 2)  # class identity and separate named instance
        self.assertEqual({r['node_kind'] for r in result['items']}, {'CLASS', 'INSTANCE'})

    def test_role_conflict_and_unproved_component_are_isolated(self):
        for options in ({'conflicting_role': True}, {'proved': False}):
            # Each independent graph is created afresh to avoid mutation reuse.
            if options != {'conflicting_role': True}:
                self.tearDown(); self.setUp()
            self.prepare(**options)
            result = self.tree.candidate_search('Same Name', 10)
            self.assertEqual(len(result['items']), 3)
            self.assertTrue(result['diagnostics']['isolated_conflicts'])

    def test_cross_page_duplicates_are_absent_and_cursor_is_bound(self):
        self.prepare()
        page = self.tree.candidate_search_page('Same Name', 1)
        all_keys = [page['items'][0]['presentation_key']]
        while page['has_more']:
            page = self.tree.candidate_search_page('Same Name', 1, cursor=page['next_cursor'])
            all_keys.extend(n['presentation_key'] for n in page['items'])
        self.assertEqual(len(all_keys), len(set(all_keys)))
        first = self.tree.candidate_search_page('Same Name', 1)
        with self.assertRaises(ValueError):
            self.tree.candidate_search_page('Other Name', 1, cursor=first['next_cursor'])

    def test_work_bound_is_reported_as_incomplete(self):
        self.prepare()
        result = self.tree.candidate_search('Same Name', 10, raw_scan_budget=1)
        self.assertFalse(result['diagnostics']['scan_complete'])
        self.assertTrue(result['diagnostics']['incomplete_streams'])


if __name__ == '__main__':
    unittest.main()
