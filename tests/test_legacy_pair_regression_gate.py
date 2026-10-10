"""A release gate must reject unaccounted losses even when both matrices pass."""
import csv
import importlib.util
import itertools
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('legacy_gate', ROOT / 'scripts/audit_legacy_pair_regressions.py')
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class RegressionGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.baseline, cls.candidate = cls.root / 'baseline', cls.root / 'candidate'
        for directory in (cls.baseline, cls.candidate):
            directory.mkdir()
            with (directory / 'legacy-pairs.csv').open('w', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['dataset', 'left', 'right', 'status', 'distance', 'lca_uids'])
                for ds, n in gate.DATASETS.items():
                    labels = []
                    for cid in range(1, n + 1):
                        reason = 'ANNOTATION_SCOPE_REVIEW: documentary gap' if directory == cls.candidate and ds == 'fgvc_aircraft' and cid == 1 else None
                        labels.append({'class_id': str(cid), 'checked': {'uid': f'{ds}:{cid}', 'reason': reason}})
                    (directory / f'legacy-{ds}-labels.json').write_text(json.dumps(labels))
                    for a, b in itertools.combinations(range(1, n + 1), 2):
                        lost = directory == cls.candidate and ds == 'fgvc_aircraft' and a == 1
                        writer.writerow([ds, a, b, 'ENDPOINT_NOT_APPLICABLE' if lost else 'APPLICABLE', '' if lost else 2, '[]' if lost else '["root:fine"]'])
            (directory / 'summary.json').write_text(json.dumps({'legacy': {'database_revision': 'candidate-revision'}}))
        cls.policy = cls.root / 'policy.json'
        cls.policy.write_text('{}')
        cls.proof = cls.root / 'independent-review.json'
        cls.proof.write_text('{"scope_review": "independent source evidence"}')
        evidence = [{'path': str(cls.proof), 'sha256': gate.sha256(cls.proof)}]
        cls.manifest = {'schema': gate.SCHEMA, 'candidate_revision': 'candidate-revision',
                        'baseline_matrix_sha256': gate.sha256(cls.baseline / 'legacy-pairs.csv'),
                        'candidate_matrix_sha256': gate.sha256(cls.candidate / 'legacy-pairs.csv'),
                        'policy_sha256': gate.sha256(cls.policy), 'groups': [{
                            'id': 'source-scope', 'category': 7, 'disposition': 'PENDING_SOURCE_EVIDENCE',
                            'first_changed_stage': 'endpoint_mapping', 'decision_reason': 'Exhaustive author scope is undocumented',
                            'pairs': [['fgvc_aircraft', '1', str(b)] for b in range(2, 101)],
                            'labels': [{'dataset': 'fgvc_aircraft', 'class_id': '1', 'old_uid': 'fgvc_aircraft:1',
                                        'new_uid': 'fgvc_aircraft:1', 'old_role': 'MODEL', 'new_role': 'MODEL',
                                        'mapping': 'REVIEW', 'parent_chain': [], 'decision_reason': 'documentary gap', 'source_evidence': evidence}],
                            'legal_connection_check': {'status': 'NO_LEGAL_CONNECTION_LOSS', 'evidence': evidence}, 'evidence': evidence}]}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_manifest(self, mutate=lambda x: None):
        value = json.loads(json.dumps(self.manifest))
        mutate(value)
        path = self.root / 'dispositions.json'
        path.write_text(json.dumps(value))
        return gate.audit(self.baseline / 'legacy-pairs.csv', self.baseline, self.candidate,
                          self.policy, path, self.root / 'output')

    def test_complete_accounting_with_documented_pending_scope(self):
        report = self.run_manifest()
        self.assertTrue(report['pass'])
        self.assertEqual(report['pairs'], 56917)
        self.assertEqual(report['lost_pairs'], 99)

    def test_missing_pair_fails_even_when_all_other_checks_pass(self):
        report = self.run_manifest(lambda x: x['groups'][0]['pairs'].pop())
        self.assertFalse(report['pass'])
        self.assertEqual(report['unexplained_lost_pairs'], 1)

    def test_engineering_omission_cannot_be_relabelled_as_pending(self):
        report = self.run_manifest(lambda x: x['groups'][0].update(category=2))
        self.assertFalse(report['pass'])

    def test_wrong_first_stage_is_rejected(self):
        report = self.run_manifest(lambda x: x['groups'][0].update(first_changed_stage='lca_resolution'))
        self.assertFalse(report['pass'])

    def test_stale_artifact_binding_is_rejected(self):
        report = self.run_manifest(lambda x: x.update(candidate_revision='another-build'))
        self.assertFalse(report['pass'])

    def test_changed_source_evidence_is_rejected(self):
        report = self.run_manifest(lambda x: x['groups'][0]['evidence'][0].update(sha256='wrong'))
        self.assertFalse(report['pass'])

    def test_wrong_endpoint_uid_is_rejected(self):
        report = self.run_manifest(lambda x: x['groups'][0]['labels'][0].update(new_uid='other:model'))
        self.assertFalse(report['pass'])


if __name__ == '__main__':
    unittest.main()
