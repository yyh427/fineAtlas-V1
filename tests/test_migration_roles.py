"""Role reconciliation retains declarations and changes only evidenced admission."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fineatlas.migration import Migration


class MigrationRolesTest(unittest.TestCase):
    def test_current_normalization_keeps_original_snapshot_and_latest_decision(self):
        m = Migration.__new__(Migration)
        m.c = sqlite3.connect(':memory:'); m.c.row_factory = sqlite3.Row
        m.c.executescript('''
          CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,domain TEXT,rank TEXT,data TEXT);
          CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,domain TEXT,source_uri TEXT,evidence_id TEXT,attributes TEXT);
          CREATE TABLE normalization_roles(uid TEXT PRIMARY KEY,source_role TEXT,canonical_role TEXT,status TEXT,evidence_id TEXT,source TEXT,prior_profile TEXT);
          CREATE TABLE evidence(layer TEXT,evidence_id TEXT,source_name TEXT,source_uri TEXT,retrieved_utc TEXT,claim_type TEXT,payload TEXT,payload_sha256 TEXT,PRIMARY KEY(layer,evidence_id));
          CREATE TABLE usability_changes(id INTEGER PRIMARY KEY,stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT);
        ''')
        m.c.execute("INSERT INTO nodes VALUES('design','Design','fixture','class','{\"node_kind\":\"CLASS\"}')")
        m.c.execute("INSERT INTO node_profiles VALUES('design','CLASS','fixture','source:original','original-proof','{}')")
        m.role('design','MODEL_FAMILY',{'role_basis':'An explicitly documented design family'},'first-source','source:first')
        first = dict(m.c.execute('SELECT * FROM normalization_roles').fetchone())
        m.role('design','MODEL',{'role_basis':'Independent evidence identifies one specific model of that family'},'second-source','source:second')
        last = dict(m.c.execute('SELECT * FROM normalization_roles').fetchone())
        profile = dict(m.c.execute('SELECT * FROM node_profiles').fetchone())
        self.assertEqual(last['canonical_role'], 'MODEL')
        self.assertEqual(last['evidence_id'], profile['evidence_id'])
        self.assertEqual(last['source'], 'second-source')
        self.assertEqual(last['source_role'], first['source_role'])
        self.assertEqual(last['prior_profile'], first['prior_profile'])
        self.assertEqual(json.loads(last['prior_profile'])['node_kind'],'CLASS')
        self.assertEqual(m.c.execute('SELECT data FROM nodes').fetchone()[0],'{"node_kind":"CLASS"}')

    def test_scope_reconciliation_preserves_raw_declarations(self):
        with tempfile.TemporaryDirectory() as directory:
            m = Migration.__new__(Migration)
            m.out = Path(directory)
            m.c = sqlite3.connect(':memory:')
            m.c.row_factory = sqlite3.Row
            m.c.executescript('''
              CREATE TABLE nodes(uid TEXT PRIMARY KEY,data TEXT,description TEXT,rank TEXT);
              CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT);
              CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,
                relation TEXT,status TEXT,evidence_id TEXT,data TEXT);
            ''')
            definitions = [
                ('ship', 'CLASS', 'CLASS', 'Example was a cargo ship built in 1850.', 'INDEPENDENT_NOMINAL_DEFINITION'),
                ('design', 'CLASS', 'CLASS', 'Example was the standard computer for multiple platforms, with the first unit delivered in 1984.', 'INDEPENDENT_NOMINAL_DEFINITION'),
                ('ambiguous', 'MODEL', 'INSTANCE', 'Example is a missile system.', 'INDEPENDENT_NOMINAL_DEFINITION'),
                ('station', 'MODEL', 'INSTANCE', 'Example was a space station.', 'INDEPENDENT_NOMINAL_INSTANCE_TYPING'),
                ('unreviewed', 'CLASS', 'CLASS', 'Example is a ship.', 'P31'),
            ]
            for i, (uid, native, profile, definition, basis) in enumerate(definitions):
                m.c.execute('INSERT INTO nodes VALUES(?,?,?,?)', (uid, json.dumps({'node_kind':native,'definition':definition}), definition, 'class'))
                m.c.execute('INSERT INTO node_profiles VALUES(?,?)', (uid, profile))
                m.c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?)', (i, uid, 'parent', 'INSTANCE_OF', 'ACTIVE', 'original-proof', json.dumps({'basis':basis,'sentence':definition})))
            original = list(m.c.execute('SELECT uid,data FROM nodes'))
            original_relations = {r['id']:r['data'] for r in m.c.execute('SELECT id,data FROM entity_relations')}
            roles, typed = {}, []
            m.role = lambda uid, role, *args: roles.update({uid:role})
            m.typed = lambda *args: typed.append(args[:3])
            m.change = lambda *args: None
            result = m.role_reconciliation()
            self.assertEqual(result['scanned_nominal_relations'], 4)
            self.assertEqual(roles, {'ship':'INSTANCE', 'design':'MODEL', 'ambiguous':'UNKNOWN'})
            self.assertEqual(typed, [('design','parent','DESIGN_TYPE_OF')])
            self.assertEqual([tuple(r) for r in m.c.execute('SELECT uid,data FROM nodes')], [tuple(r) for r in original])
            self.assertEqual({r['id']:r['data'] for r in m.c.execute('SELECT id,data FROM entity_relations')}, original_relations)
            self.assertEqual(dict(m.c.execute('SELECT subject_uid,status FROM entity_relations')), {'ship':'ACTIVE','design':'SUPERSEDED','ambiguous':'REVIEW','station':'ACTIVE','unreviewed':'ACTIVE'})

    def test_stale_generated_model_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            m = Migration.__new__(Migration)
            m.inputs = Path(directory)
            m.c = sqlite3.connect(':memory:')
            m.c.row_factory = sqlite3.Row
            m.c.executescript('CREATE TABLE nodes(uid TEXT,data TEXT); CREATE TABLE node_profiles(uid TEXT,node_kind TEXT);')
            m.c.execute('INSERT INTO nodes VALUES(?,?)', ('instance', '{}'))
            m.c.execute('INSERT INTO node_profiles VALUES(?,?)', ('instance', 'INSTANCE'))
            (m.inputs/'source_facts.jsonl').write_text(json.dumps({'uid':'instance','source':'Independent native product-family definition','source_uri':'example','proof':{}})+'\n')
            with self.assertRaisesRegex(ValueError, 'Stale model extraction input'):
                m.source_facts()
