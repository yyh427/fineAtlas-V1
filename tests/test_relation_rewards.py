"""Independent DAG, role, applicability and frozen-snapshot reward regressions."""
import json
import sqlite3
import unittest
from pathlib import Path

import test_single
import test_public_mechanisms
from fineatlas import FineAtlas


class RewardIndexTest(unittest.TestCase):
    setUp = test_single.TypedInterfaceTest.setUp
    tearDown = test_single.TypedInterfaceTest.tearDown
    add = staticmethod(test_public_mechanisms.PublicMechanismsTest.add)

    def prepare(self, change=None):
        self.tree.close()
        c=sqlite3.connect(self.path)
        c.execute('DROP TABLE dataset_targets')
        c.execute('CREATE TABLE dataset_targets(dataset TEXT,class_id TEXT,label TEXT,target_uid TEXT,decision_status TEXT,identity_basis TEXT,granularity_basis TEXT,evidence_ids TEXT,provenance TEXT)')
        self.add(c,'a','left',10,('type:river',),rank='species')
        self.add(c,'b','right',11,('type:river',),rank='species')
        for cid,uid in [('1','a'),('2','b')]:
            c.execute('INSERT INTO dataset_targets VALUES(?,?,?,?,?,?,?,?,?)',
                      ('cub200',cid,cid,uid,'VERIFIED','independent fixture','species','[]','{}'))
        if change:change(c)
        c.commit();c.close();self.tree=FineAtlas(self.path)

    def test_source_only_unknown_target_does_not_promote_stored_identity_claim(self):
        def change(c):
            c.execute("UPDATE nodes SET visibility='SOURCE_ONLY',rank='type_or_product_model' WHERE uid='a'")
        self.prepare(change)
        target=self.tree.target('cub200','1')
        self.assertTrue(target['stored_identity_claim_verified'])
        self.assertFalse(target['identity_verified'])
        self.assertFalse(target['task_admission']['identity_verified'])
        self.assertTrue(target['native_label_admission']['usable'])
        pair=self.tree.relation_reward_index('cub200').query('1','2')
        self.assertFalse(pair['applicable'])
        self.assertIsNone(pair['distance'])

    def test_all_lowest_ancestors_are_retained(self):
        def change(c):
            self.add(c,'other','other common type',12,('type:root',))
            for uid in ('a','b'):
                c.execute("INSERT INTO edges(child_uid,parent_uid,relation,status,source,data,provenance) VALUES(?,?,'IS_A','ACTIVE','fixture','{}','[]')",(uid,'other'))
        self.prepare(change)
        index=self.tree.relation_reward_index('cub200')
        r=index.query('1','2')
        self.assertEqual(r['status'],'APPLICABLE')
        self.assertEqual({n['uid'] for n in r['lcas']},{'type:river','other'})
        self.assertEqual(r['distance'],2)
        self.assertEqual(len(list(index.pairs())),1)

    def test_coarse_floor_and_its_ancestors_do_not_fabricate_reward(self):
        self.prepare()
        r=self.tree.relation_reward_index('cub200',coarse_roots=['type:river']).query('1','2')
        self.assertEqual(r['status'],'COARSE_COMMON_ANCESTOR_ONLY')
        self.assertFalse(r['applicable']);self.assertIsNone(r['distance'])

    def test_review_unknown_and_work_limit_are_explicit(self):
        self.prepare()
        index=self.tree.relation_reward_index('cub200',excluded_labels={'1':'scope unconfirmed'})
        self.assertEqual(index.query('1','2')['status'],'ENDPOINT_NOT_APPLICABLE')
        self.assertIsNone(index.query('1','2')['distance'])
        self.assertEqual(index.query('3','2')['status'],'UNKNOWN_LABEL')
        limited=self.tree.relation_reward_index('cub200',max_nodes=1)
        self.assertEqual(limited.query('1','2')['reasons']['1'],'ANCESTOR_LIMIT')

    def test_frozen_index_survives_view_change_and_database_close(self):
        self.prepare()
        index=self.tree.relation_reward_index('cub200')
        self.tree.relation_view='membership';self.tree.close()
        r=index.query('1','2')
        self.assertEqual(r['relation_view'],'strict')
        self.assertEqual(r['distance'],2)

    def test_identity_aliases_have_zero_cost(self):
        def change(c):
            self.add(c,'alias','another source representation',12,rank='species')
            c.execute("UPDATE nodes SET component_id=10 WHERE uid='alias'")
            c.execute("INSERT INTO bridges VALUES(1,'a','alias','SAME_CONCEPT','ACTIVE',1,'{\"basis\":\"independent fixture identity\"}')")
            c.execute("UPDATE dataset_targets SET target_uid='alias' WHERE class_id='2'")
        self.prepare(change)
        r=self.tree.relation_reward_index('cub200').query('1','2')
        self.assertEqual(r['distance'],0)

    def test_cycles_are_not_silently_scored(self):
        def change(c):
            c.execute("INSERT INTO edges(child_uid,parent_uid,relation,status,source,data,provenance) VALUES('type:river','a','IS_A','ACTIVE','fixture','{}','[]')")
        self.prepare(change)
        r=self.tree.relation_reward_index('cub200').query('1','2')
        self.assertEqual(r['status'],'CYCLIC_LINEAGE')
        self.assertIsNone(r['distance'])

    def test_review_policy_is_bound_to_revision_view_and_root(self):
        self.prepare()
        path=Path(self.temp.name)/'policy.json'
        review={'schema':'FINEATLAS_RELATION_REWARD_REVIEW_V1',
                'database_revision':self.tree._revision,'relation_view':'strict','root_uid':self.tree.root_uid,
                'datasets':{'cub200':{'policy':'classification','excluded_labels':{}}}}
        path.write_text(json.dumps(review))
        self.assertTrue(self.tree.relation_reward_index('cub200',review_policy=path).query('1','2')['applicable'])
        review['database_revision']='other';path.write_text(json.dumps(review))
        with self.assertRaisesRegex(ValueError,'does not match'):
            self.tree.relation_reward_index('cub200',review_policy=path)

    def test_attribute_and_directory_arcs_cannot_become_class_rewards(self):
        def change(c):
            c.execute("UPDATE dataset_targets SET target_uid='attr:1' WHERE class_id='1'")
        self.prepare(change)
        r=self.tree.relation_reward_index('cub200').query('1','2')
        self.assertEqual(r['status'],'ENDPOINT_NOT_APPLICABLE')
        self.assertIn('ROLE_NOT_APPLICABLE',r['reasons']['1'])

    def test_export_preserves_all_labels_and_explicit_invalid_pair_mask(self):
        def change(c):
            c.execute('CREATE TABLE dataset_mapping_checks(dataset TEXT,class_id TEXT,status TEXT,reason TEXT,proof TEXT)')
            c.execute("INSERT INTO dataset_mapping_checks VALUES('cub200','1','ANNOTATION_SCOPE_REVIEW','annotation scope unresolved','{}')")
        self.prepare(change)
        out=Path(self.temp.name)/'training'
        report=self.tree.export_training('cub200',out)
        rows=[json.loads(line) for line in (out/'labels.jsonl').read_text().splitlines()]
        pairs=[json.loads(line) for line in (out/'pairs.jsonl').read_text().splitlines()]
        self.assertEqual(report['labels'],2)
        self.assertEqual(report['pairs'],1)
        self.assertTrue(all(r['category_reward_applicable'] for r in rows))
        self.assertEqual(pairs[0]['status'],'ENDPOINT_NOT_APPLICABLE')
        self.assertIsNone(pairs[0]['distance'])
        self.assertEqual(rows[0]['path']['status'],'CONNECTED')

    def test_legacy_string_provenance_is_not_treated_as_a_mapping(self):
        def change(c):
            c.execute('UPDATE edges SET data=?',(json.dumps({'admission_basis':'Retained native source statement'}),))
        self.prepare(change)
        self.assertEqual(self.tree.relation_reward_index('cub200').query('1','2')['distance'],2)

    def test_conflicting_ancestor_identity_cannot_manufacture_a_reward(self):
        def change(c):
            self.add(c,'ambiguous-ancestor','model representation of a class',12,rank='model')
            c.execute("UPDATE nodes SET component_id=1 WHERE uid='ambiguous-ancestor'")
        self.prepare(change)
        result=self.tree.relation_reward_index('cub200').query('1','2')
        self.assertEqual(result['status'],'IDENTITY_LINEAGE_ROLE_CONFLICT')
        self.assertFalse(result['applicable'])
        self.assertIsNone(result['distance'])
        self.assertEqual(result['conflicts'][0]['roles'],['CLASS','MODEL'])


if __name__=='__main__':unittest.main()
