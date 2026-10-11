"""Incremental source binding rejects identity promotion and stale range evidence."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fineatlas.structure_regression_repairs import sha, validate_regression_repairs

class RegressionRepairContracts(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:'); self.c.row_factory = sqlite3.Row
        self.c.executescript('''CREATE TABLE nodes(uid TEXT PRIMARY KEY,data TEXT,visibility TEXT,source TEXT,rank TEXT);
            CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT);
            CREATE TABLE entity_relations(id INTEGER,subject_uid TEXT,object_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);''')
        self.model = json.dumps({'description': 'regional airliner family'})
        self.parent = json.dumps({'description': 'fixed-wing powered commercial aircraft'})
        self.c.executemany('INSERT INTO nodes VALUES(?,?,?,?,?)', [('model', self.model, 'ACTIVE', 'publisher', 'model_family'), ('parent', self.parent, 'ACTIVE', 'publisher', '')])
        self.op = {'op': 'link', 'uid': 'model', 'parent': 'parent', 'relation': 'DESIGN_TYPE_OF', 'proof': {
            'world_identity_assertion': False, 'no_identity_merges': True, 'whole_subject_scope_review': True,
            'scope_observation': 'The model statement entails this complete physical range.',
            'native_record_sha256': sha(self.model), 'parent_native_record_sha256': sha(self.parent),
            'source_witnesses': [{'uid': 'model', 'data_sha256': sha(self.model), 'field': 'description', 'statement': 'regional airliner family'}]}}
        self.manifest = {'schema': 'FINEATLAS_STRUCTURE_REGRESSION_REPAIRS_V1'}
    def tearDown(self): self.c.close()
    def test_valid_directional_design_range(self):
        validate_regression_repairs(self.c, self.manifest, [self.op])
    def test_identity_promotion_is_rejected(self):
        op = copy.deepcopy(self.op); op['proof']['world_identity_assertion'] = True
        with self.assertRaisesRegex(ValueError, 'world identity'):
            validate_regression_repairs(self.c, self.manifest, [op])
    def test_source_range_change_requires_new_review(self):
        self.c.execute('UPDATE nodes SET data=? WHERE uid=?', (json.dumps({'description': 'a book about aircraft'}), 'model'))
        with self.assertRaisesRegex(ValueError, 'source changed'):
            validate_regression_repairs(self.c, self.manifest, [self.op])
    def test_unbound_source_sentence_cannot_establish_scope(self):
        op = copy.deepcopy(self.op); op['proof']['source_witnesses'][0]['statement'] = 'commercial passenger aircraft'
        with self.assertRaisesRegex(ValueError, 'statement is absent'):
            validate_regression_repairs(self.c, self.manifest, [op])
    def test_design_family_is_not_ordinary_class_inclusion(self):
        op = copy.deepcopy(self.op); op['relation'] = 'IS_A'
        with self.assertRaisesRegex(ValueError, 'cannot join MODEL_FAMILY'):
            validate_regression_repairs(self.c, self.manifest, [op])
    def test_original_disposition_is_bound(self):
        self.c.execute('INSERT INTO entity_relations VALUES(1,?,?,?,?,?,?)', ('model', 'old', 'DESIGN_TYPE_OF', 'original', 'SOURCE_SCOPE_REVIEW', '{}'))
        op = copy.deepcopy(self.op); op['proof']['prior_assertion'] = {'subject_uid': 'model', 'object_uid': 'old', 'relation': 'DESIGN_TYPE_OF', 'source': 'original', 'status': 'ACTIVE', 'content_sha256': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'Prior source assertion'):
            validate_regression_repairs(self.c, self.manifest, [op])
    def test_arbitrary_mutations_are_rejected(self):
        op = copy.deepcopy(self.op); op['op'] = 'role'
        with self.assertRaisesRegex(ValueError, 'only append typed links'):
            validate_regression_repairs(self.c, self.manifest, [op])

if __name__ == '__main__': unittest.main()
