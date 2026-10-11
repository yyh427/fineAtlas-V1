"""Opt-in physical configuration paths preserve old policy and strict identity."""
import unittest
import test_relation_rewards as fixtures

class ConfigurationTypePolicyTest(unittest.TestCase):
    setUp = fixtures.RewardIndexTest.setUp
    tearDown = fixtures.RewardIndexTest.tearDown
    prepare = fixtures.RewardIndexTest.prepare
    add = staticmethod(fixtures.RewardIndexTest.add)

    def setup_configuration(self, status='ACTIVE', conflict=False):
        def change(c):
            for rid, uid in ((4, 'a'), (5, 'b')):
                c.execute("UPDATE nodes SET rank='configuration' WHERE uid=?", (uid,))
                c.execute('DELETE FROM edges WHERE child_uid=?', (uid,))
                c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',
                          (rid,uid,'type:river','CONFIGURATION_TYPE_OF',status,'fixture','proof:1','{}'))
                c.execute('INSERT INTO entity_connections VALUES(?,?,?,?,?)',
                          (uid,1,'type:river',rid,2))
            if conflict:
                self.add(c,'ambiguous','ambiguous source',20,rank='model')
                c.execute("UPDATE nodes SET component_id=10 WHERE uid='ambiguous'")
        self.prepare(change)

    def index(self, policy):
        return self.tree.relation_reward_index('cub200', policy=policy,
            requirement='configuration', admission_mode='reviewed_paths',
            task_boundary_roots=['type:root'], coarse_roots=['type:river'])

    def test_grounded_type_path_is_coarse_and_old_policy_stays_excluded(self):
        self.setup_configuration()
        old=self.index('configuration').query('1','2')
        self.assertIsNone(old['distance'])
        self.assertEqual(old['reasons']['1'],'NO_VALID_TASK_BOUNDARY_PATH')
        new=self.index('configuration_types').query('1','2')
        self.assertEqual(new['resolution'],'COARSE_VALID')
        self.assertIsNone(new['distance'])
        path=self.index('configuration_types').path('1')
        self.assertTrue(path['task_path_valid'])
        self.assertIn('CONFIGURATION_TYPE_OF',{x['edge']['relation'] for x in path['path']})

    def test_role_floor_catches_non_wordnet_ordinary_type_without_changing_paths(self):
        self.setup_configuration()
        options=dict(policy='configuration_types',requirement='configuration',
            admission_mode='reviewed_paths',task_boundary_roots=['type:root'])
        old=self.tree.relation_reward_index('cub200',**options)
        new=self.tree.relation_reward_index('cub200',coarse_lca_roles=['CLASS'],**options)
        self.assertEqual(old.query('1','2')['resolution'],'FINE_VALID')
        self.assertEqual(new.query('1','2')['resolution'],'COARSE_VALID')
        self.assertIsNone(new.query('1','2')['distance'])
        self.assertEqual(old.path('1'),new.path('1'))
        with self.assertRaises(ValueError):
            self.tree.relation_reward_index('cub200',policy='configuration_types',
                coarse_lca_roles=['CLASS'],admission_mode='legacy')

    def test_ordinary_type_resolution_floor_retains_real_model_common_ancestor(self):
        def change(c):
            c.execute("UPDATE nodes SET rank='model' WHERE uid='type:river'")
            c.execute("DELETE FROM edges WHERE child_uid='type:river'")
            c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',
                (1003,'type:river','type:root','DESIGN_TYPE_OF','ACTIVE','fixture','proof:1','{}'))
            c.execute('INSERT INTO entity_connections VALUES(?,?,?,?,?)',
                ('type:river',1,'type:root',1003,1))
            for rid,uid in ((1004,'a'),(1005,'b')):
                c.execute("UPDATE nodes SET rank='configuration' WHERE uid=?",(uid,))
                c.execute('DELETE FROM edges WHERE child_uid=?',(uid,))
                c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',
                    (rid,uid,'type:river','CONFIGURATION_OF','ACTIVE','fixture','proof:1','{}'))
                c.execute('INSERT INTO entity_connections VALUES(?,?,?,?,?)',
                    (uid,1,'type:river',rid,2))
        self.prepare(change)
        index=self.tree.relation_reward_index('cub200',policy='configuration_types',
            requirement='configuration',admission_mode='reviewed_paths',
            task_boundary_roots=['type:root'],coarse_lca_roles=['CLASS'])
        pair=index.query('1','2')
        self.assertEqual(pair['resolution'],'FINE_VALID')
        self.assertEqual(pair['distance'],2)
        self.assertEqual(pair['lcas'][0]['uid'],'type:river')

    def test_review_type_claim_cannot_become_a_valid_route(self):
        self.setup_configuration(status='REVIEW')
        new=self.index('configuration_types').query('1','2')
        self.assertIsNone(new['distance'])
        self.assertEqual(new['reasons']['1'],'ENDPOINT_NOT_ADMITTED: UNREACHABLE')

    def test_endpoint_identity_conflict_cannot_be_bypassed(self):
        self.setup_configuration(conflict=True)
        new=self.index('configuration_types').query('1','2')
        self.assertIsNone(new['distance'])
        self.assertEqual(new['reasons']['1'],'IDENTITY_ROLE_CONFLICT')

if __name__=='__main__':unittest.main()
