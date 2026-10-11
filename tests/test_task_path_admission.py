"""Task boundaries are independent of navigation roots and coarse thresholds."""
import json
from pathlib import Path
import unittest

import test_relation_rewards as reward_tests


class TaskPathAdmissionTest(unittest.TestCase):
    setUp = reward_tests.RewardIndexTest.setUp
    tearDown = reward_tests.RewardIndexTest.tearDown
    prepare = reward_tests.RewardIndexTest.prepare
    add = staticmethod(reward_tests.RewardIndexTest.add)

    def test_coarse_floor_is_not_a_task_boundary(self):
        def change(c):
            self.add(c,'other-domain','other domain',12,('type:root',))
            c.execute("UPDATE edges SET parent_uid='other-domain' WHERE child_uid='a'")
        self.prepare(change)
        index = self.tree.relation_reward_index('cub200',admission_mode='reviewed_paths',
                                              coarse_roots=['type:river'],task_boundary_roots=['type:root'])
        path = self.tree.task_path('cub200','1',index=index)
        self.assertTrue(path['navigation_root_reachable'])
        self.assertTrue(path['task_boundary_reachable'])
        self.assertTrue(path['task_path_valid'])
        self.assertEqual(path['task_boundary_uid'],'type:root')
        narrowed = self.tree.relation_reward_index('cub200',admission_mode='reviewed_paths',
                                                 task_boundary_roots=['type:river'])
        path = narrowed.path('1')
        self.assertTrue(path['navigation_root_reachable'])
        self.assertFalse(path['task_boundary_reachable'])
        self.assertFalse(path['training_endpoint_applicable'])

    def test_source_scoped_boundary_path_ends_before_navigation_prefix(self):
        self.prepare()
        index = self.tree.relation_reward_index('cub200',admission_mode='reviewed_paths',
                                              source_scope='independent',task_boundary_roots=['type:river'])
        path = self.tree.task_path('cub200','1',index=index)
        self.assertEqual(path['classification_arc_count'],1)
        self.assertEqual(len(path['path']),1)
        self.assertEqual(path['path'][0]['uid'],'a')
        self.assertEqual(path['path'][0]['parent_uid'],'type:river')
        self.assertTrue(path['navigation_root_reachable'])
        self.assertEqual(index.query('1','2')['distance'],2)
        self.assertEqual(index.path('1',max_depth=0)['status'],'DEPTH_LIMIT')
        with self.assertRaises(ValueError):
            index.path('1',max_depth=-1)

    def test_source_scope_cannot_be_bypassed_by_an_unrelated_parent(self):
        self.prepare()
        index = self.tree.relation_reward_index('cub200',admission_mode='reviewed_paths',
                                              source_scope='wrong-source',task_boundary_roots=['type:river'])
        path=index.path('1')
        self.assertFalse(path['task_path_valid'])
        self.assertEqual(path['excluded_branches'][0]['exclusion_reason'],'SOURCE_SCOPE_NOT_APPLICABLE')

    def test_reviewed_export_uses_same_frozen_path_and_pair_contract(self):
        self.prepare()
        out=Path(self.temp.name)/'reviewed'
        summary=self.tree.export_training('cub200',out,admission_mode='reviewed_paths',
                                          task_boundary_roots=['type:river'])
        labels=[json.loads(line) for line in (out/'labels.jsonl').read_text().splitlines()]
        pairs=[json.loads(line) for line in (out/'pairs.jsonl').read_text().splitlines()]
        self.assertEqual(summary['admission_mode'],'reviewed_paths')
        self.assertTrue(all(label['path']['task_path_valid'] for label in labels))
        self.assertEqual(pairs[0]['distance'],2)
        self.assertEqual(pairs[0]['admission_mode'],'reviewed_paths')
        self.assertEqual(sum(len(pairs[0]['selected_paths'][0][side]['path']) for side in ('left','right')),2)

    def test_frozen_witness_survives_database_close(self):
        self.prepare()
        index=self.tree.relation_reward_index('cub200',admission_mode='reviewed_paths')
        self.tree.close()
        self.assertTrue(index.path('1')['task_path_valid'])
        self.assertEqual(index.query('1','2')['distance'],2)

    def test_a_different_dataset_index_cannot_be_used_for_task_path(self):
        self.prepare()
        index=self.tree.relation_reward_index('cub200',admission_mode='reviewed_paths')
        with self.assertRaisesRegex(ValueError,'does not match'):
            self.tree.task_path('other','1',index=index)

    def native_fixture(self, c):
        c.execute('CREATE TABLE dataset_scope_targets(dataset TEXT,class_id TEXT,namespace TEXT,source_version TEXT,source_uid TEXT,role TEXT,decision_status TEXT,proof TEXT,label TEXT)')
        for cid,uid,comp in [('1','native-one',12),('2','native-two',13)]:
            self.add(c,uid,'source annotation '+cid,comp,('type:river',),rank='species')
            c.execute('INSERT INTO dataset_scope_targets VALUES(?,?,?,?,?,?,?,?,?)',
                      ('cub200',cid,'author-labels','2026',uid,'CLASS','SOURCE_DECLARED',
                       '{"url":"https://example.org/official-annotations","sha256":"frozen-fixture"}',cid))
        c.execute('CREATE TABLE dataset_mapping_checks(dataset TEXT,class_id TEXT,status TEXT,reason TEXT,proof TEXT)')
        c.execute("INSERT INTO dataset_mapping_checks VALUES('cub200','1','ANNOTATION_SCOPE_REVIEW','world object uncertain','{}')")

    def test_native_scope_preserves_world_review_and_native_proof(self):
        self.prepare(self.native_fixture)
        world = self.tree.target('cub200','1')
        native = self.tree.target('cub200','1',target_scope='source_native')
        self.assertEqual(world['mapping_kind'],'ANNOTATION_SCOPE_REVIEW')
        self.assertEqual(native['identity_scope'],'SOURCE_NATIVE_LABEL')
        self.assertEqual(native['world_target_uid'],'a')
        self.assertEqual(native['source_version'],'2026')
        self.assertTrue(native['identity_verified'])
        index=self.tree.relation_reward_index('cub200',target_scope='source_native',
                                             admission_mode='reviewed_paths',task_boundary_roots=['type:river'])
        self.assertEqual(index.query('1','2')['distance'],2)
        path=self.tree.task_path('cub200','1',index=index)
        self.assertEqual(path['uid'],'native-one')
        self.assertTrue(path['task_path_valid'])
        with self.assertRaisesRegex(ValueError,'require reviewed_paths'):
            self.tree.relation_reward_index('cub200',target_scope='source_native')

    def test_native_empty_proof_and_namespace_ambiguity_are_rejected(self):
        def change(c):
            self.native_fixture(c)
            c.execute("UPDATE dataset_scope_targets SET proof='{}' WHERE class_id='1'")
            c.execute("INSERT INTO dataset_scope_targets SELECT dataset,class_id,namespace,'2027',source_uid,role,decision_status,proof,label FROM dataset_scope_targets WHERE class_id='2'")
        self.prepare(change)
        self.assertFalse(self.tree.target('cub200','1',target_scope='source_native')['identity_verified'])
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            self.tree.target('cub200','2',target_scope='source_native')
        index=self.tree.relation_reward_index('cub200',admission_mode='reviewed_paths',
                                             target_scope='source_native',source_version='2026',
                                             task_boundary_roots=['type:river'])
        result=index.query('1','2')
        self.assertEqual(result['reasons']['1'],'IDENTITY_UNCONFIRMED')
        self.assertIsNone(result['distance'])

    def test_annotation_projection_keeps_relation_and_excludes_color_attribute(self):
        def change(c):
            self.native_fixture(c)
            for cid,uid in [('1','native-one'),('2','native-two')]:
                c.execute("UPDATE nodes SET rank='dataset_category' WHERE uid=?",(uid,))
                c.execute("INSERT INTO node_profiles VALUES(?,'DATASET_CATEGORY','independent','https://example.org','proof:1','{}')",(uid,))
                c.execute("UPDATE dataset_scope_targets SET role='DATASET_CATEGORY' WHERE class_id=?",(cid,))
                c.execute('DELETE FROM edges WHERE child_uid=?',(uid,))
                c.execute("INSERT INTO entity_relations(subject_uid,object_uid,relation,status,source,evidence_id,data) VALUES(?,'type:river','DEPICTS_TYPE','ACTIVE','independent','proof:1','{}')",(uid,))
                c.execute("INSERT INTO entity_relations(subject_uid,object_uid,relation,status,source,evidence_id,data) VALUES(?,'attr:1','HAS_ATTRIBUTE','ACTIVE','independent','proof:1','{}')",(uid,))
        self.prepare(change)
        index=self.tree.relation_reward_index('cub200',policy='annotation',requirement='hierarchy',
                                             admission_mode='reviewed_paths',target_scope='source_native',
                                             task_boundary_roots=['type:river'])
        result=index.query('1','2')
        self.assertEqual(result['distance'],2)
        self.assertEqual(result['selected_paths'][0]['left']['path'][0]['edge']['relation'],'DEPICTS_TYPE')
        self.assertNotIn('attr:1',{node['uid'] for node in result['lcas']})
        self.assertIn('not a pure IS_A',result['metric_scope'])
        with self.assertRaisesRegex(ValueError,'requires reviewed_paths and source_native'):
            self.tree.relation_reward_index('cub200',policy='annotation',admission_mode='reviewed_paths')


if __name__ == '__main__':
    unittest.main()
