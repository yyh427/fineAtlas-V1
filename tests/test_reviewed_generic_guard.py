"""An accepted physical-kind review survives historical model-rank extraction."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from fineatlas.migration import Migration
from fineatlas.role_contracts import allows_model_extraction, reviewed_generic_class


class ReviewedGenericGuardTest(unittest.TestCase):
    def profile(self):
        return {'node_kind': 'CLASS', 'evidence_id': 'review:1', 'attributes': {
            'role_status': 'VERIFIED', 'role_evidence_id': 'review:1',
            'canonical_scope_guard': 'GENERIC_PHYSICAL_KIND', 'canonical_scope_evidence_id': 'review:1'}}

    def test_current_verified_scope_rejects_model_rank_and_p31_override(self):
        profile = self.profile()
        native = {'node_kind': 'MODEL_FAMILY', 'rank': 'model_family', 'P31': ['product-family']}
        self.assertTrue(reviewed_generic_class(profile))
        self.assertFalse(allows_model_extraction(native, profile))
        profile['attributes'] = json.dumps(profile['attributes'])
        self.assertFalse(allows_model_extraction(native, profile))

    def test_fallback_class_stale_marker_and_native_spoof_remain_unassessed(self):
        native = {'node_kind': 'MODEL', 'attributes': self.profile()['attributes']}
        self.assertTrue(allows_model_extraction(native, None))
        self.assertTrue(allows_model_extraction(native, {'node_kind': 'CLASS'}))
        for field, value in [('role_status', 'FALLBACK'), ('canonical_scope_guard', 'UNKNOWN'),
                             ('canonical_scope_evidence_id', 'old-review')]:
            p = self.profile()
            p['attributes'][field] = value
            with self.subTest(field=field):
                self.assertTrue(allows_model_extraction(native, p))

    def test_family_parser_keeps_named_design_positive_and_skips_reviewed_generic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / 'graph.sqlite'
            c = sqlite3.connect(db)
            c.executescript('''CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,description TEXT,
              data TEXT,source TEXT,rank TEXT,visibility TEXT,component_id INTEGER,domain TEXT);
              CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,attributes TEXT,evidence_id TEXT);
              CREATE TABLE aliases(alias TEXT,uid TEXT);
              CREATE TABLE edges(child_uid TEXT,parent_uid TEXT,relation TEXT,status TEXT,
                original_relation TEXT,source_relation TEXT);''')
            for i, (uid, label, definition, rank) in enumerate([
                ('wordnet31:fixture-artifact', 'artifact', 'A physical artifact.', 'class'),
                ('wordnet31:fixture-car', 'car', 'A motor vehicle.', 'class'),
                ('wikidata:Q1', 'basket', 'A basket is a container that holds things.', 'model_family'),
                ('wikidata:Q2', 'Brand Car X1', 'Brand Car X1 is a car manufactured by BrandCorp.', 'model')]):
                source = 'wordnet31' if uid.startswith('wordnet31:') else 'Wikidata + independent encyclopedia definition'
                c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?)',
                          (uid, label, definition, json.dumps({'definition': definition, 'node_kind': 'MODEL'}),
                           source, rank, 'ACTIVE', i + 1, 'car'))
            p = self.profile()
            c.execute('INSERT INTO node_profiles VALUES(?,?,?,?)',
                      ('wikidata:Q1', 'CLASS', json.dumps(p['attributes']), p['evidence_id']))
            c.execute("INSERT INTO node_profiles VALUES('wikidata:Q2','CLASS','{}','fallback')")
            c.executemany('INSERT INTO aliases VALUES(?,?)',
                          [('artifact', 'wordnet31:fixture-artifact'), ('car', 'wordnet31:fixture-car')])
            c.execute("INSERT INTO edges VALUES('wordnet31:fixture-car','wordnet31:fixture-artifact','IS_A','ACTIVE','IS_A','hypernym')")
            c.commit()
            c.close()
            definitions = root / 'definitions.json'
            definitions.write_text('{}')
            output = root / 'family.jsonl'
            result = subprocess.run([sys.executable, '-B',
                str(Path(__file__).resolve().parents[1] / 'scripts/prepare_family_inputs.py'),
                '--database', str(db), '--definitions', str(definitions), '--output', str(output)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual([(r['uid'], r['role']) for r in rows], [('wikidata:Q2', 'MODEL')])
            summary = json.loads(output.with_suffix('.summary.json').read_text())
            skip = next(x for x in summary['retained_review'] if x['uid'] == 'wikidata:Q1')
            self.assertIn('reviewed generic CLASS', skip['reason'])

    def test_stale_family_fact_replay_cannot_overwrite_accepted_generic(self):
        with tempfile.TemporaryDirectory() as directory:
            m = Migration.__new__(Migration)
            m.inputs = Path(directory)
            m.c = sqlite3.connect(':memory:')
            m.c.row_factory = sqlite3.Row
            m.c.executescript('CREATE TABLE nodes(uid TEXT,data TEXT); CREATE TABLE node_profiles(uid TEXT,node_kind TEXT,attributes TEXT,evidence_id TEXT);')
            p = self.profile()
            m.c.execute("INSERT INTO nodes VALUES('kind','{\"node_kind\":\"MODEL\"}')")
            m.c.execute('INSERT INTO node_profiles VALUES(?,?,?,?)',
                        ('kind', 'CLASS', json.dumps(p['attributes']), p['evidence_id']))
            (m.inputs / 'source_facts.jsonl').write_text(json.dumps({'uid': 'kind',
                'source': 'Independent native product-family definition', 'source_uri': 'example', 'proof': {}}) + '\n')
            with self.assertRaisesRegex(ValueError, 'Stale model extraction input'):
                m.source_facts()
            self.assertEqual(m.c.execute('SELECT node_kind FROM node_profiles').fetchone()[0], 'CLASS')


if __name__ == '__main__':
    unittest.main()
