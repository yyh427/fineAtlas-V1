"""Source-only adjudication preserves raw records, legal types and author mappings."""
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fineatlas.migration import Migration
from fineatlas.structure_cars_projection_view_repairs import apply_cars_projection_view_repairs, sha, source_assertion_sha256
spec = importlib.util.spec_from_file_location('independent_projection_auditor', ROOT / 'scripts/audit_cars_projection_view_repairs.py')
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


class CarsProjectionReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name); self.inputs = self.root / 'inputs'; self.inputs.mkdir()
        self.db = self.root / 'fineatlas.sqlite'; self.c = sqlite3.connect(self.db); self.c.row_factory = sqlite3.Row
        self.c.executescript('''CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,domain TEXT,domains TEXT,source TEXT,rank TEXT,description TEXT,data TEXT,layer TEXT,visibility TEXT,component_id INTEGER);
            CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,domain TEXT,source_uri TEXT,evidence_id TEXT,attributes TEXT);
            CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,relation TEXT,status TEXT,source TEXT,evidence_id TEXT,data TEXT);
            CREATE TABLE evidence(layer TEXT,evidence_id TEXT,source_name TEXT,source_uri TEXT,retrieved_utc TEXT,claim_type TEXT,payload TEXT,payload_sha256 TEXT,PRIMARY KEY(layer,evidence_id));
            CREATE TABLE normalization_roles(uid TEXT PRIMARY KEY,source_role TEXT,canonical_role TEXT,status TEXT,evidence_id TEXT,source TEXT,prior_profile TEXT);
            CREATE TABLE usability_changes(id INTEGER PRIMARY KEY,stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT);
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE dataset_targets(dataset TEXT,class_id TEXT,label TEXT,target_uid TEXT,decision_status TEXT);
            CREATE TABLE dataset_mapping_checks(dataset TEXT,class_id TEXT,status TEXT);
            CREATE TABLE browse_nodes(uid TEXT);
            CREATE TABLE browse_links(storage TEXT,record_id INTEGER);
            CREATE TABLE view_terminal_connections(uid TEXT,witness_relation_id INTEGER);
            CREATE TABLE view_paths(witness_id INTEGER);''')
        label = 'Sample Model Coupe 2009'; self.uid = 'v26-car:' + sha('\0'.join(('stanford_cars', '1', label)))[:32]
        self.c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?)', (self.uid, label, 'car', '["car"]', 'FineAtlas V26 source projection', 'model_year', '', json.dumps({'dataset_alias': label}), 'legacy', 'ACTIVE', 1))
        self.c.execute('INSERT INTO node_profiles VALUES(?,?,?,?,?,?)', (self.uid, 'CONFIGURATION', 'car', 'author', 'role', json.dumps({'source_role': 'model_year'})))
        for uid, source, rank, cid in [('parent', 'NHTSA vPIC', 'model', 2), ('oem', 'OEM manufacturer', 'configuration', 3), ('epa', 'epa', 'configuration', 4)]:
            self.c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?)', (uid, uid, 'car', '["car"]', source, rank, '', '{}', 'legacy', 'ACTIVE', cid))
        for i, (uid, source) in enumerate([(self.uid, 'producer-one'), (self.uid, 'producer-two'), ('oem', 'official'), ('epa', 'publisher')], 1):
            self.c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)', (i, uid, 'parent', 'CONFIGURATION_OF', 'ACTIVE', source, 'native', '{}'))
        self.c.execute('INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?)', ('source', 'native', 'publisher', 'uri', '2026-10-01', 'native', '{}', sha('{}')))
        self.c.execute('INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?)', ('source', 'role', 'publisher', 'uri', '2026-10-01', 'role', '{}', sha('{}')))
        self.c.execute('INSERT INTO dataset_targets VALUES(?,?,?,?,?)', ('stanford_cars', '1', label, self.uid, 'REVIEW'))
        self.c.execute('INSERT INTO dataset_mapping_checks VALUES(?,?,?)', ('stanford_cars', '1', 'ANNOTATION_SCOPE_REVIEW'))
        before = dict(self.c.execute('SELECT * FROM nodes WHERE uid=?', (self.uid,)).fetchone())
        profile = dict(self.c.execute('SELECT * FROM node_profiles WHERE uid=?', (self.uid,)).fetchone())
        target = dict(self.c.execute('SELECT * FROM dataset_targets').fetchone())
        check = dict(self.c.execute('SELECT * FROM dataset_mapping_checks').fetchone())
        origin = {'dataset': 'stanford_cars', 'class_id': '1', 'official_label': label, 'deterministic_constructor_uid': self.uid,
                  'original_overlay_node': before, 'original_overlay_target': target, 'author_source_origin_proven': True, 'author_origin_does_not_close_world_configuration_range': True}
        self.entry = {'uid': self.uid, 'before_node': before, 'before_profile': profile, 'before_role': 'CONFIGURATION', 'native_record_sha256': sha(before['data']),
                      'origin': origin, 'canonical_role_after': 'UNKNOWN', 'visibility_after': 'SOURCE_ONLY', 'allowed_views_after': [], 'reason': 'Author references do not close the world range.',
                      'before_current_target': target, 'before_mapping_check': check}
        self.ops = []
        for row in self.c.execute('SELECT * FROM entity_relations WHERE subject_uid=?', (self.uid,)).fetchall():
            old = dict(row); h = source_assertion_sha256(old)
            self.ops.append({'op': 'review_world_projection_relation', 'uid': self.uid, 'parent': 'parent', 'relation': 'CONFIGURATION_OF',
                             'source': 'Reviewed author-derived configuration projection scope', 'uri': 'source-uri', 'after_status': 'SOURCE_SCOPE_REVIEW', 'new_reference_relation': 'SOURCE_MODEL_REFERENCE', 'new_reference_status': 'SOURCE_DECLARED',
                             'before_relation': old, 'locator': {**{k: old[k] for k in ('subject_uid', 'object_uid', 'relation', 'source', 'status')}, 'content_sha256': h},
                             'proof': {'basis': 'AUTHOR_DERIVED_PROJECTION_REFERENCE_DOES_NOT_PROVE_WHOLE_WORLD_CONFIGURATION_INCLUSION', 'world_identity_assertion': False, 'new_parent_task_relation': False,
                                       'no_identity_merges': True, 'scope_evidence_gap': True, 'source_scope_conflict': False, 'parent_data_has_closed_whole_model_scope': False,
                                       'source_origin': origin, 'review_reason': self.entry['reason'], 'old_relation_content_sha256': h,
                                       'native_record_sha256': sha(before['data']), 'parent_native_record_sha256': sha('{}'), 'parent_source': 'NHTSA vPIC', 'license': 'Original'}})
        protected = [{'uid': uid, 'source': uid, 'before_node': dict(self.c.execute('SELECT * FROM nodes WHERE uid=?', (uid,)).fetchone()), 'before_profile': None, 'current_configuration_of_claims': [dict(r) for r in self.c.execute('SELECT * FROM entity_relations WHERE subject_uid=?', (uid,))]} for uid in ('oem', 'epa')]
        self.manifest = {'schema': 'FINEATLAS_CARS_PROJECTION_VIEW_REPAIRS_V1', 'operations_file': 'cars_projection_view_repairs.jsonl', 'operation_count': 2, 'operations': {'CONFIGURATION_OF': 2},
                         'source_projection_count': 1, 'source_projections': [self.entry], 'new_nodes': 0, 'mapping_promotions': 0, 'legacy_whole_world_claims_are_pending_not_proven_false': True, 'preserved_nonprojection_configs': protected}
        self.write_inputs()
        self.m = Migration.__new__(Migration); self.m.c = self.c; self.m.inputs = self.inputs
        self.c.execute('INSERT INTO metadata VALUES(?,?)', ('database_revision', json.dumps('fixture-revision')))
        self.c.commit()

    def write_inputs(self):
        raw = ''.join(json.dumps(x) + '\n' for x in self.ops).encode(); self.manifest['operations_sha256'] = sha(raw)
        (self.inputs / 'cars_projection_view_repairs.jsonl').write_bytes(raw)
        (self.inputs / 'structure_cars_projection_view_repairs.json').write_text(json.dumps(self.manifest))

    def apply(self):
        result = apply_cars_projection_view_repairs(self.m)
        frozen = {'inputs': {p.name: sha(p.read_bytes()) for p in self.inputs.iterdir()}}
        self.c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', ('structure_frozen_build_manifest', json.dumps(frozen))); self.c.commit()
        return result

    def audit(self, preflight=False):
        return audit.run(self.db, self.inputs, self.root / 'audit.json', preflight)

    def tearDown(self): self.c.close(); self.tmp.cleanup()

    def test_preflight_then_source_only_with_distinct_retained_claims(self):
        self.assertTrue(self.audit(True)); result = self.apply(); self.assertEqual(result['retained_source_references'], 2)
        self.assertTrue(self.audit())
        refs = self.c.execute("SELECT status,source FROM entity_relations WHERE relation='SOURCE_MODEL_REFERENCE'").fetchall()
        self.assertEqual(len({r['source'] for r in refs}), 2); self.assertEqual({r['status'] for r in refs}, {'SOURCE_DECLARED'})
        self.assertEqual(self.c.execute('SELECT count(*) FROM nodes').fetchone()[0], 4)
        self.assertEqual(self.c.execute("SELECT count(*) FROM entity_relations WHERE subject_uid IN ('oem','epa') AND status='ACTIVE'").fetchone()[0], 2)

    def test_changed_source_payload_is_rejected_before_mutation(self):
        self.c.execute("UPDATE nodes SET data='changed' WHERE uid=?", (self.uid,)); self.c.commit()
        with self.assertRaises(ValueError): self.apply()
        self.assertEqual(self.c.execute('SELECT visibility FROM nodes WHERE uid=?', (self.uid,)).fetchone()[0], 'ACTIVE')

    def test_missing_active_claim_census_is_rejected(self):
        self.ops.pop(); self.manifest['operation_count'] = 1; self.manifest['operations'] = {'CONFIGURATION_OF': 1}; self.write_inputs()
        with self.assertRaisesRegex(ValueError, 'every active'): self.apply()

    def test_illegal_identity_promotion_is_rejected(self):
        self.ops[0]['proof']['world_identity_assertion'] = True; self.write_inputs()
        with self.assertRaises(ValueError): self.apply()

    def test_late_failure_rolls_back_source_roles_and_claims(self):
        original = self.m.change
        def fail(stage, kind, *args):
            if kind == 'source_model_reference': raise RuntimeError('injected failure')
            return original(stage, kind, *args)
        self.m.change = fail
        with self.assertRaisesRegex(RuntimeError, 'injected'): self.apply()
        self.assertEqual(self.c.execute('SELECT node_kind FROM node_profiles WHERE uid=?', (self.uid,)).fetchone()[0], 'CONFIGURATION')
        self.assertEqual(self.c.execute('SELECT count(*) FROM usability_changes').fetchone()[0], 0)
        self.assertEqual(self.c.execute("SELECT count(*) FROM entity_relations WHERE status='ACTIVE'").fetchone()[0], 4)

    def test_independent_auditor_rejects_active_reference(self):
        self.apply(); self.c.execute("UPDATE entity_relations SET status='ACTIVE' WHERE relation='SOURCE_MODEL_REFERENCE'"); self.c.commit()
        self.assertFalse(self.audit())

    def test_independent_auditor_rejects_reference_in_distance_cache(self):
        self.apply(); rid = self.c.execute("SELECT id FROM entity_relations WHERE relation='SOURCE_MODEL_REFERENCE' LIMIT 1").fetchone()[0]
        self.c.execute('INSERT INTO view_paths VALUES(?)', (-rid,)); self.c.commit(); self.assertFalse(self.audit())

    def test_independent_auditor_rejects_legal_oem_epa_withdrawal(self):
        self.apply(); self.c.execute("UPDATE entity_relations SET status='SOURCE_SCOPE_REVIEW' WHERE subject_uid='oem'"); self.c.commit(); self.assertFalse(self.audit())

    def test_independent_auditor_rejects_missing_role_history(self):
        self.apply(); self.c.execute("DELETE FROM usability_changes WHERE object_type='node_profiles'"); self.c.commit(); self.assertFalse(self.audit())

    def test_independent_auditor_rejects_author_mapping_promotion(self):
        self.apply(); self.c.execute("UPDATE dataset_targets SET decision_status='VERIFIED'"); self.c.commit(); self.assertFalse(self.audit())

    def test_independent_auditor_rejects_source_data_change(self):
        self.apply(); self.c.execute("UPDATE nodes SET label='renamed' WHERE uid=?", (self.uid,)); self.c.commit(); self.assertFalse(self.audit())

    def test_independent_auditor_rejects_legal_epa_role_demotion(self):
        self.apply(); self.c.execute("UPDATE nodes SET visibility='SOURCE_ONLY' WHERE uid='epa'"); self.c.commit(); self.assertFalse(self.audit())

    def test_missing_current_mapping_freeze_cannot_build(self):
        del self.entry['before_mapping_check']; self.write_inputs()
        with self.assertRaisesRegex(ValueError, 'current mapping'): self.apply()

    def test_reapply_requires_new_parent(self):
        self.apply()
        with self.assertRaisesRegex(ValueError, 'already applied'): self.apply()


if __name__ == '__main__': unittest.main()
