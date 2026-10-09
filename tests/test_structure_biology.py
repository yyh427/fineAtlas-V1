"""Biological annotation scope must not poison the real-world entity graph."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fineatlas.migration import Migration
from fineatlas.structure_biology import (
    SCHEMA, INPUT_NAME, LINK_INPUT_NAME, apply_structure_biology,
    corroborated_species_rank, digest, validate_payload,
)


class BiologicalScopeTest(unittest.TestCase):
    def scientific_record(self, labels, definition='A flowering plant'):
        return {'uid':'wordnet31:sense', 'source':'wordnet31', 'description':definition,
                'data':json.dumps({'labels':labels})}

    def native(self, name='Campanula medium', rank='species', uid='wfo:one'):
        return {'uid':uid, 'label':name, 'rank':rank, 'source':'wfo', 'data':'{}'}

    def test_common_name_does_not_authorize_rank_or_identity(self):
        self.assertIsNone(corroborated_species_rank(
            self.scientific_record(['canterbury_bells']), [self.native()]))
        result = corroborated_species_rank(
            self.scientific_record(['Campanula_medium']), [self.native()])
        self.assertEqual(result['rank'], 'species')
        self.assertFalse(result['identity_merge_authorized'])
        self.assertFalse(result['dataset_mapping_authorized'])

    def test_native_homonyms_and_conflicting_grains_fail_closed(self):
        record = self.scientific_record(['Campanula_medium'])
        self.assertIsNone(corroborated_species_rank(record,
            [self.native(), self.native(uid='wfo:another-source-record')]))
        self.assertIsNone(corroborated_species_rank(record, [self.native(rank='genus')]))
        self.assertIsNone(corroborated_species_rank(
            self.scientific_record(['Campanula_medium'],
                'any plant of the genus Campanula'), [self.native()]))

    def test_lexical_same_sense_cannot_equate_distinct_native_species(self):
        self.assertIsNone(corroborated_species_rank(
            self.scientific_record(['Cirsium_vulgare','Cirsium_lanceolatum']),
            [self.native('Cirsium vulgare'), self.native('Cirsium lanceolatum',uid='wfo:two')]))
        self.assertIsNone(corroborated_species_rank(
            self.scientific_record(['Anthurium_andraeanum','Anthurium_scherzerianum']),
            [self.native('Anthurium andraeanum'), self.native('Anthurium scherzerianum',uid='wfo:two')]))
        self.assertIsNone(corroborated_species_rank(
            self.scientific_record(['Macrozamia_spiralis','Macrozamia_communis']),
            [self.native('Macrozamia spiralis'), self.native('Macrozamia communis',uid='wfo:two')]))

    def test_frozen_payload_cannot_bypass_native_scope_uniqueness(self):
        payload=self.minimal_payload({})
        payload['rank_repairs']=[{'uid':'wordnet31:sense','rank':'species','proof':{
            'identity_merge_authorized':False,'dataset_mapping_authorized':False,
            'corroborating_native_records':[self.native(),self.native(uid='wfo:two')]}}]
        with self.assertRaisesRegex(ValueError,'one confirmed native scope UID'):
            validate_payload(payload)

    def minimal_payload(self, target):
        proof = {'source_uri':'https://author.example/categories','source_version':'2008',
                 'namespace':'author', 'source_publisher':'Author native metadata',
                 'native_rank':'dataset_category', 'world_exact_identity_verified':False}
        return {'schema':SCHEMA, 'retained_nodes':[{
            'uid':'wfo:plant', 'label':'Native plant', 'source':'wfo', 'rank':'species',
            'data_sha256':hashlib.sha256(b'{}').hexdigest()}],
            'links_sha256':hashlib.sha256(b'').hexdigest(), 'rank_repairs':[],
            'native_labels':[{'dataset':'flowers102','class_id':'96',
                'uid':'author:category:96','label':'camellia','role':'DATASET_CATEGORY',
                'proof':proof,'links':[{'parent':'wfo:plant','relation':'DEPICTS_TYPE',
                                      'proof':{'scope_resolution':'REVIEWED_BROAD_SCOPE'}}]}],
            'mapping_reviews':[{'entity_disposition':'PRESERVE', 'before_target':target,
                'before_target_sha256':digest(target), 'before_check':None,
                'proof':{'reason':'Species extent unconfirmed; native label remains usable',
                         'source_uri':'https://author.example/categories'}}]}

    def test_colour_and_label_contracts_reject_fake_species_scope(self):
        payload = self.minimal_payload({})
        payload['native_labels'][0]['links'][0]['relation']='HAS_ATTRIBUTE'
        with self.assertRaises(ValueError):validate_payload(payload)
        payload['native_labels'][0]['links'][0]['proof']['subject_scope_uid']='wfo:dahlia'
        validate_payload(payload)
        payload['native_labels'][0]['proof']['world_exact_identity_verified']=True
        with self.assertRaises(ValueError):validate_payload(payload)

    def test_label_review_preserves_world_entity_history_and_replays_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); database=root/'candidate.sqlite'; inputs=root/'inputs';inputs.mkdir()
            c=sqlite3.connect(database)
            c.executescript('''
              CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
              CREATE TABLE components(id INTEGER PRIMARY KEY,depth INTEGER,wordnet_reachable INTEGER);
              CREATE TABLE nodes(uid TEXT UNIQUE,label TEXT,domain TEXT,domains TEXT,source TEXT,
                rank TEXT,description TEXT,data TEXT,layer TEXT,visibility TEXT,component_id INTEGER);
              CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,relation TEXT,status TEXT,source TEXT,layer TEXT);
              CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,domain TEXT,source_uri TEXT,evidence_id TEXT,attributes TEXT);
              CREATE TABLE evidence(layer TEXT,id TEXT PRIMARY KEY,source TEXT,source_uri TEXT,retrieved TEXT,claim TEXT,data TEXT,sha256 TEXT);
              CREATE TABLE aliases(alias TEXT,uid TEXT,name TEXT,source TEXT,layer TEXT,data TEXT);
              CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,
                relation TEXT,status TEXT,source TEXT,evidence_id TEXT,data TEXT,
                UNIQUE(subject_uid,object_uid,relation,source));
              CREATE TABLE dataset_targets(dataset TEXT,class_id TEXT,label TEXT,target_uid TEXT,
                decision_status TEXT,identity_basis TEXT,granularity_basis TEXT,evidence_ids TEXT,provenance TEXT,
                PRIMARY KEY(dataset,class_id));
              CREATE TABLE dataset_mapping_checks(dataset TEXT,class_id TEXT,status TEXT,reason TEXT,proof TEXT,
                PRIMARY KEY(dataset,class_id));
              CREATE TABLE dataset_target_history(dataset TEXT,class_id TEXT,original_target_uid TEXT,original_record TEXT,
                PRIMARY KEY(dataset,class_id));
              CREATE TABLE annotation_scope_target_history(stage TEXT,dataset TEXT,class_id TEXT,original_record TEXT,
                PRIMARY KEY(stage,dataset,class_id));
              CREATE TABLE dataset_scope_targets(dataset TEXT,class_id TEXT,namespace TEXT,source_version TEXT,
                source_uid TEXT,role TEXT,decision_status TEXT,proof TEXT,label TEXT,
                PRIMARY KEY(dataset,class_id,namespace,source_version));
              INSERT INTO components VALUES(1,NULL,0);
              INSERT INTO nodes VALUES('wfo:plant','Native plant','plant','["plant"]','wfo','species','','{}','native','ACTIVE',1);
              INSERT INTO dataset_targets VALUES('flowers102','96','camellia','wfo:plant','VERIFIED','prior evidence','species','[]','{}');
              INSERT INTO dataset_target_history VALUES('flowers102','96','oldest-source-uid','original preserved history');
            ''');c.commit();c.row_factory=sqlite3.Row
            target=dict(c.execute('SELECT * FROM dataset_targets').fetchone());c.close()
            payload=self.minimal_payload(target)
            (inputs/INPUT_NAME).write_text(json.dumps(payload));(inputs/LINK_INPUT_NAME).write_bytes(b'')
            m=Migration(database,inputs,root/'reports');m.schema()
            with patch('fineatlas.structure_biology.apply_refinements',return_value={}):
                result=apply_structure_biology(m)
                self.assertEqual(result['native_category_nodes_added'],1)
                self.assertEqual(apply_structure_biology(m)['status'],'already_applied')
            self.assertEqual(dict(m.c.execute('SELECT * FROM dataset_targets').fetchone()),target)
            self.assertEqual(m.c.execute("SELECT visibility FROM nodes WHERE uid='wfo:plant'").fetchone()[0],'ACTIVE')
            self.assertEqual(m.c.execute('SELECT original_target_uid FROM dataset_target_history').fetchone()[0],'oldest-source-uid')
            self.assertEqual(m.c.execute('SELECT count(*) FROM dataset_scope_targets').fetchone()[0],1)
            self.assertEqual(m.c.execute('SELECT relation FROM entity_relations').fetchone()[0],'DEPICTS_TYPE')
            self.assertEqual(m.c.execute('SELECT status FROM dataset_mapping_checks').fetchone()[0],'ANNOTATION_SCOPE_REVIEW')
            self.assertEqual(m.c.execute('SELECT count(*) FROM annotation_scope_target_history').fetchone()[0],1)
            m.c.close()


if __name__=='__main__':unittest.main()
