"""Independent DAG witnesses exercise bad branches and strict endpoints."""
import unittest

import test_relation_rewards as reward_tests


class RewardBranchIsolationTest(unittest.TestCase):
    setUp = reward_tests.RewardIndexTest.setUp
    tearDown = reward_tests.RewardIndexTest.tearDown
    prepare = reward_tests.RewardIndexTest.prepare
    add = staticmethod(reward_tests.RewardIndexTest.add)

    def reviewed(self, **options):
        return self.tree.relation_reward_index('cub200', admission_mode='reviewed_paths', **options)

    def test_unrelated_conflict_is_excluded_with_evidence(self):
        def change(c):
            self.add(c, 'ambiguous', 'conflicting branch', 12, ('type:root',))
            self.add(c, 'ambiguous-model', 'model source', 13, rank='model')
            c.execute("UPDATE nodes SET component_id=12 WHERE uid='ambiguous-model'")
            c.execute("INSERT INTO edges(child_uid,parent_uid,relation,status,source,data,provenance) "
                      "VALUES('a','ambiguous','IS_A','ACTIVE','fixture','{}','[\"proof:1\"]')")
        self.prepare(change)
        legacy = self.tree.relation_reward_index('cub200').query('1','2')
        self.assertEqual(legacy['status'], 'IDENTITY_LINEAGE_ROLE_CONFLICT')
        result = self.reviewed().query('1','2')
        self.assertEqual(result['distance'], 2)
        self.assertEqual(result['resolution'], 'FINE_VALID')
        excluded = result['excluded_branches']['1']
        self.assertEqual(excluded[0]['exclusion_reason'], 'IDENTITY_ROLE_CONFLICT')
        self.assertEqual(excluded[0]['parent_uid'], 'ambiguous')
        self.assertEqual(excluded[0]['source'], 'fixture')
        for side in ('left','right'):
            path = result['selected_paths'][0][side]['path']
            self.assertEqual(len(path), 1)
            self.assertEqual(path[0]['parent_uid'], 'type:river')
            self.assertEqual(path[0]['edge']['relation'], 'IS_A')

    def test_essential_conflict_cannot_be_bypassed(self):
        def change(c):
            self.add(c,'river-model','model scope',12,rank='model')
            c.execute("UPDATE nodes SET component_id=1 WHERE uid='river-model'")
        self.prepare(change)
        result = self.reviewed().query('1','2')
        self.assertFalse(result['applicable'])
        self.assertIsNone(result['distance'])
        self.assertEqual(result['reasons']['1'], 'NO_VALID_TASK_BOUNDARY_PATH')
        self.assertEqual(result['excluded_branches']['1'][0]['exclusion_reason'], 'IDENTITY_ROLE_CONFLICT')

    def test_endpoint_conflict_remains_strict(self):
        def change(c):
            self.add(c,'endpoint-model','different role',12,rank='model')
            c.execute("UPDATE nodes SET component_id=10 WHERE uid='endpoint-model'")
        self.prepare(change)
        result = self.reviewed().query('1','2')
        self.assertEqual(result['reasons']['1'],'IDENTITY_ROLE_CONFLICT')
        self.assertIsNone(result['distance'])

    def test_cycle_sibling_is_isolated_but_cycle_endpoint_is_rejected(self):
        def change(c):
            self.add(c,'cycle-one','cycle one',12,('type:root',))
            self.add(c,'cycle-two','cycle two',13,('cycle-one',))
            for child,parent in [('cycle-one','cycle-two'),('a','cycle-one')]:
                c.execute("INSERT INTO edges(child_uid,parent_uid,relation,status,source,data,provenance) "
                          "VALUES(?,?,'IS_A','ACTIVE','fixture','{}','[\"proof:1\"]')",(child,parent))
        self.prepare(change)
        self.assertEqual(self.tree.relation_reward_index('cub200').query('1','2')['status'],'CYCLIC_LINEAGE')
        result = self.reviewed().query('1','2')
        self.assertEqual(result['distance'],2)
        self.assertIn('CYCLIC_BRANCH',{e['exclusion_reason'] for e in result['excluded_branches']['1']})

    def test_uncertain_placement_cannot_be_used_for_a_path(self):
        def change(c):
            c.execute("UPDATE edges SET data='{\"admission_basis\":{\"placement_uncertain\":true}}' WHERE child_uid='a'")
        self.prepare(change)
        path = self.reviewed().path('1')
        self.assertFalse(path['task_path_valid'])
        self.assertTrue(path['navigation_root_reachable'])
        self.assertEqual(path['excluded_branches'][0]['exclusion_reason'],'PLACEMENT_UNCERTAIN')

    def test_component_coarse_rank_does_not_depend_on_alias_selection(self):
        def change(c):
            self.add(c,'river-entry','same identity, coarse entry rank',12,rank='domain_entry')
            c.execute("UPDATE nodes SET component_id=1 WHERE uid='river-entry'")
        self.prepare(change)
        result = self.reviewed().query('1','2')
        self.assertEqual(result['resolution'],'COARSE_VALID')
        self.assertEqual(result['status'],'COARSE_COMMON_ANCESTOR_ONLY')
        self.assertIsNone(result['distance'])


if __name__ == '__main__':
    unittest.main()
