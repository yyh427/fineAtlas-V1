"""Frozen canonical roles must settle before final design navigation replay."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'src'))
from fineatlas.hierarchy import apply_refinements
from fineatlas.migration import Migration

spec=importlib.util.spec_from_file_location('unified_replay_order_builder',ROOT/'scripts/build_unified_candidate.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class CanonicalRoleReplayOrderTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();folder=Path(self.temp.name)
        self.inputs=folder/'inputs';self.inputs.mkdir()
        database=folder/'candidate.sqlite'
        self.uid='maker:model-17';self.parent='wordnet31:aircraft'
        self.native=json.dumps({'manufacturer_model_id':'17','declared_scope':'one named aircraft design'})
        with sqlite3.connect(database) as c:
            c.executescript("""
              CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
              CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,domain TEXT,domains TEXT,source TEXT,rank TEXT,
                description TEXT,data TEXT,layer TEXT,visibility TEXT,component_id INTEGER);
              CREATE TABLE components(id INTEGER PRIMARY KEY,depth INTEGER,wordnet_reachable INTEGER);
              CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,domain TEXT,source_uri TEXT,evidence_id TEXT,attributes TEXT);
              CREATE TABLE evidence(layer TEXT,evidence_id TEXT,source_name TEXT,source_uri TEXT,retrieved_utc TEXT,
                claim_type TEXT,payload TEXT,payload_sha256 TEXT,PRIMARY KEY(layer,evidence_id));
              CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,relation TEXT,source TEXT,layer TEXT,status TEXT,data TEXT);
              CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,relation TEXT,status TEXT,
                source TEXT,evidence_id TEXT,data TEXT,UNIQUE(subject_uid,object_uid,relation,source));
              CREATE TABLE dataset_targets(dataset TEXT,class_id TEXT,label TEXT,target_uid TEXT,decision_status TEXT,
                identity_basis TEXT,granularity_basis TEXT,evidence_ids TEXT,provenance TEXT,PRIMARY KEY(dataset,class_id));
            """)
            c.executemany('INSERT INTO components VALUES(?,NULL,0)',[(1,),(2,)])
            c.executemany('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?)',[
                (self.uid,'Maker Model 17','aircraft','["aircraft"]','manufacturer','model',
                 'Maker Model 17 is one documented aircraft design.',self.native,'fixture','ACTIVE',1),
                (self.parent,'aircraft','aircraft','["aircraft"]','wordnet31','class',
                 'A vehicle that can fly.','{}','fixture','ACTIVE',2)])
            # The stale canonical CLASS profile, rather than the native rank,
            # determines endpoint roles until the frozen root contract is run.
            c.execute('INSERT INTO node_profiles VALUES(?,?,?,?,?,?)',
                      (self.uid,'CLASS','aircraft','source:historical','historical-evidence','{}'))
        for name in ('unified_backbone_nodes','unified_backbone_edges','unified_domain_rules',
                     'unified_taxon_identities','unified_opentree_identities','unified_avilist_native_records'):
            (self.inputs/(name+'.json')).write_text('[]\n')
        (self.inputs/'unified_field_refinements.jsonl').write_text('')
        (self.inputs/'review_release.json').write_text(json.dumps({'version':'v1.10.1-repair-review'})+'\n')
        proof={'basis':'PRIMARY_EXPLICIT_NAMED_DESIGN_UNIT_WITH_UNCHANGED_SOURCE_SCOPE',
               'native_record_sha256':hashlib.sha256(self.native.encode()).hexdigest(),
               'native_rank':'aircraft_model','source_role':'Manufacturer-defined aircraft model',
               'allowed_views':['strict','taxonomy','membership'],
               'scope_statement':'A named aircraft design; not an ordinary reusable physical class.'}
        base={'uid':self.uid,'source':'Frozen manufacturer design-unit evidence','uri':'https://example.org/model-17','proof':proof}
        role={**base,'op':'role','role':'MODEL'}
        link={**base,'op':'link','parent':self.parent,'relation':'DESIGN_TYPE_OF'}
        (self.inputs/'unified_root_contracts.jsonl').write_text(json.dumps(role)+'\n')
        (self.inputs/'unified_final_role_links.jsonl').write_text(json.dumps(link)+'\n')
        self.m=Migration(database,self.inputs,folder/'reports');self.m.schema()

    def tearDown(self):
        self.m.c.close();self.temp.cleanup()

    def test_full_frozen_apply_settles_model_before_final_design_navigation(self):
        with contextlib.redirect_stdout(io.StringIO()):
            summary=builder.apply(self.m)
        role=self.m.c.execute('SELECT node_kind FROM node_profiles WHERE uid=?',(self.uid,)).fetchone()[0]
        relation=self.m.c.execute('SELECT * FROM entity_relations WHERE subject_uid=?',(self.uid,)).fetchone()
        self.assertEqual(role,'MODEL')
        self.assertEqual((relation['object_uid'],relation['relation'],relation['status']),
                         (self.parent,'DESIGN_TYPE_OF','ACTIVE'))
        role_change=self.m.c.execute("SELECT id,before_json,after_json FROM usability_changes WHERE stage='roles' AND object_id=?",(self.uid,)).fetchone()
        typed_change=self.m.c.execute("SELECT id FROM usability_changes WHERE stage='relations' AND object_type='typed' AND object_id=?",(self.uid,)).fetchone()
        self.assertEqual(json.loads(role_change['before_json'])['node_kind'],'CLASS')
        self.assertEqual(json.loads(role_change['after_json'])['node_kind'],'MODEL')
        self.assertLess(role_change['id'],typed_change['id'])
        self.assertEqual(summary['role_decisions'],1)
        self.assertEqual(summary['professional_links'],1)
        self.assertEqual(self.m.c.execute('SELECT data FROM nodes WHERE uid=?',(self.uid,)).fetchone()[0],self.native)
        self.assertEqual(self.m.c.execute('SELECT count(*) FROM hierarchy_decisions').fetchone()[0],2)

    def test_reversed_final_navigation_rejects_class_to_class_design_relation(self):
        with self.assertRaisesRegex(ValueError,'DESIGN_TYPE_OF cannot join CLASS to CLASS'):
            apply_refinements(self.m,'unified_final_role_links.jsonl')
        self.assertEqual(self.m.c.execute('SELECT node_kind FROM node_profiles WHERE uid=?',(self.uid,)).fetchone()[0],'CLASS')
        self.assertEqual(self.m.c.execute('SELECT count(*) FROM entity_relations').fetchone()[0],0)
        self.assertEqual(self.m.c.execute('SELECT count(*) FROM hierarchy_decisions').fetchone()[0],0)
        self.assertEqual(self.m.c.execute('SELECT data FROM nodes WHERE uid=?',(self.uid,)).fetchone()[0],self.native)


if __name__=='__main__':unittest.main()
