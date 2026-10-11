"""Source cohorts, immutable reports and public artifact scope must stay bound.

Only synthetic files are used; these fixtures never prove a real public download.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'independent_expanded_source_contract', ROOT / 'scripts/structure_acceptance_contract.py')
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class ExpandedSourceAcceptanceGuardsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        self.bindings = {}
        self.ledger = [
            {'dataset': 'cub200', 'class_id': str(i), 'prior_mapping_check': {
                'status': 'ANNOTATION_SCOPE_REVIEW' if i <= 15 else 'PRIMARY_SOURCE_CORROBORATED'}}
            for i in range(1, 201)]
        self.native = [
            {'dataset': dataset, 'class_id': str(i), 'uid': dataset + ':category:' + str(i)}
            for dataset, total in (('flowers102', 102), ('cub200', 200))
            for i in range(1, total + 1)]
        self.biology = {
            'reviewed_label_count': 200, 'new_label_scope_reviews': 12,
            'all_200_ledger_sha256': hashlib.sha256(canonical(self.ledger).encode()).hexdigest(),
            'mapping_reviews': [{'dataset': 'cub200', 'class_id': str(i)} for i in range(16, 28)]}
        self.vehicle = {
            'schema': 'FINEATLAS_VEHICLE_SOURCE_SCOPE_MANIFEST_V1',
            'producer_snapshots': [
                {'portable_file': 'epa_vehicles.csv.gz', 'rows': 50242},
                {'portable_file': 'faa_ACFTREF.txt.gz', 'rows': 94043}],
            'source_native_uid_inventory': 220248, 'projection_inventory': 169,
            'nhtsa_inventory': 28, 'operation_counts': {'CONFIGURATION_TYPE_OF': 50242, 'IS_A': 1}}
        self.identity = {'reviewed_identity_groups': [
            {'class_id': str(16 + index), 'actual_active_bridges': [
                {'id': 1 + index}] + ([{'id': 13 + index}] if index < 5 else [])}
            for index in range(12)], 'repairs': [{'before_bridge': {'id': 17}}]}
        self.input_file('structure_biology_identity_scope.json', self.identity)
        self.input_file('all_200_version_scope_ledger.json', self.ledger)
        self.input_file('structure_biology.json', {'native_labels': self.native})
        self.input_file('cub_annotation_version_scope.json', self.biology)
        self.input_file('structure_vehicle_source_scope.json', self.vehicle)
        self.cars_author = {'schema': 'FINEATLAS_CARS_AUTHOR_SCOPE_V1',
            'scope_targets': [{'dataset': 'stanford_cars', 'class_id': str(i)} for i in range(1, 197)],
            'world_mapping_reviews': [{'before': {'dataset': 'stanford_cars', 'class_id': str(i)}}
                                      for i in range(1, 197)], 'source_native_pair_count': 19110,
            'source_native_label_count': 196, 'world_mappings_reviewed': 196}
        self.input_file('structure_cars_author_scope.json', self.cars_author)
        self.fingerprints = {'inputs': self.bindings, 'code': {}, 'packaging': {}}
        self.expected = contract.frozen_supplemental_expectations(self.inputs, self.fingerprints)

    def tearDown(self):
        self.temp.cleanup()

    def input_file(self, name, value):
        path = self.inputs / name
        path.write_text(json.dumps(value), encoding='utf-8')
        self.bindings[name] = contract.file_sha256(path)

    def report(self, name, database):
        return {**copy.deepcopy(self.expected[name]), 'pass': True, 'public_api_checked': True,
                'revision': 'synthetic-revision', 'database': str(database)}

    def write_report(self, name, value, public):
        path = self.root / ('public-' + name + '.json')
        path.write_text(json.dumps(value), encoding='utf-8')
        public['evidence'][name] = {'path': str(path), 'sha256': contract.file_sha256(path), 'pass': True}

    def public_fixture(self):
        database = self.root / 'synthetic-not-a-real-database.sqlite'
        database.write_bytes(b'SYNTHETIC NOT A FINEATLAS DATABASE')
        stat = database.stat()
        stamp = [stat.st_size, stat.st_mtime_ns, stat.st_ino]
        database_sha = contract.file_sha256(database)
        full = {'cub200': 200, 'fgvc_aircraft': 100, 'flowers102': 102,
                'pets37': 37, 'stanford_dogs': 120, 'stanford_cars': 196}
        modes = ('legacy', 'reviewed_old_floors', 'reviewed_new_floors', 'source_native',
                 'reviewed_rank_floors', 'source_native_rank_floors')
        counts = {mode: {dataset: {'labels': total, 'pairs': total * (total - 1) // 2}
                        for dataset, total in full.items()
                        if not mode.startswith('source_native')
                        or dataset in {'cub200', 'flowers102', 'fgvc_aircraft'}
                        or (mode == 'source_native_rank_floors' and dataset == 'stanford_cars')} for mode in modes}
        receipt = {'database_sha256': database_sha, 'database_revision': 'synthetic-revision',
                   'release': 'synthetic-release', 'matrix_expected_counts': counts,
                   'fingerprints': copy.deepcopy(self.fingerprints), 'supplemental_audits': {}}
        public = {'all_pass': True, 'public_download_unauthenticated': True,
                  'matching_installed_sdk': True, 'database_sha256': database_sha,
                  'database_revision': 'synthetic-revision', 'release': 'synthetic-release',
                  'ended_utc': 'synthetic-end', 'evidence': {}}
        bound = {'database': str(database), 'database_revision': 'synthetic-revision'}
        download = {**bound, 'database_sha256': database_sha, 'authenticated': False,
                    'fresh_download': True, 'release': 'synthetic-release', 'artifact_stamp': stamp,
                    'public_download_urls': ['https://example.invalid/synthetic'], 'asset_proofs': [{
                        'url': 'https://example.invalid/synthetic', 'fresh_download': True,
                        'network_request': True, 'authenticated': False, 'initial_cached_bytes': 0,
                        'http_status': 200}]}
        sdk = {**bound, 'all_pass': True, 'installed_sdk': True, 'database_sha256': database_sha,
               'release': 'synthetic-release', 'artifact_stamp': stamp}
        reports = {
            'download': download, 'installed-sdk': sdk,
            'full-six-matrix': {mode: {**bound, 'datasets': {
                dataset: {'counts': row} for dataset, row in datasets.items()}}
                for mode, datasets in counts.items()},
            'living': {**bound, 'status': 'PASS', 'errors': []},
            'whole-library': {**bound, 'pass': True}, 'exports': {**bound, 'pass': True},
            'public-cli': {**bound, 'all_pass': True}, 'source-contracts': {**bound, 'pass': True}}
        for name in self.expected:
            local = self.root / ('local-' + name + '.json')
            local.write_text(json.dumps(self.report(name, self.root / 'local.sqlite')))
            receipt['supplemental_audits'][name] = {
                'path': str(local), 'sha256': contract.file_sha256(local),
                'expected': copy.deepcopy(self.expected[name])}
            reports[name] = self.report(name, database)
        for name, report in reports.items():
            self.write_report(name, report, public)
        evidence = self.root / 'synthetic-evidence.json'
        evidence.write_text(json.dumps(public))
        return public, receipt, evidence

    def test_expectations_use_complete_frozen_source_cohorts(self):
        b = self.expected['biology-version-scope']
        self.assertEqual(b['all_200_original_targets_checked'], 200)
        self.assertEqual(b['new_label_scope_reviews_checked'], 12)
        self.assertEqual(b['native_sql_labels_checked'], 302)
        self.assertEqual(b['native_public_paths_checked'], 302)
        self.assertEqual(b['world_exact_guard_rejections_checked'], 12)
        self.assertEqual(b['mapping_status_counts'], {
            'ANNOTATION_SCOPE_REVIEW': 27, 'PRIMARY_SOURCE_CORROBORATED': 173})
        self.assertEqual(b['scientific_identity_scope_cases_checked'], 12)
        self.assertEqual(b['scientific_identity_bridges_checked'], 17)
        self.assertEqual(b['scientific_identity_scope_splits_checked'], 1)
        c = self.expected['vehicle-source-scope']['cohort_counts']
        self.assertEqual(c['epa_configurations'], 50242)
        self.assertEqual(c['faa_models'], 94043)
        self.assertEqual(c['producer_native_uid_inventory'], 220248)
        self.assertEqual(c['projection_inventory'], 169)
        self.assertEqual(c['cars_author_native_labels'], 196)
        self.assertEqual(c['cars_author_world_mapping_reviews'], 196)
        self.assertEqual(c['cars_author_native_pairs'], 19110)

    def test_changed_source_asset_is_not_rebound_from_a_report(self):
        (self.inputs / 'structure_biology.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'frozen input changed'):
            contract.frozen_supplemental_expectations(self.inputs, self.fingerprints)

    def test_partial_199_cub_ledger_is_rejected_even_when_fingerprinted(self):
        self.input_file('all_200_version_scope_ledger.json', self.ledger[:-1])
        self.biology['all_200_ledger_sha256'] = hashlib.sha256(canonical(self.ledger[:-1]).encode()).hexdigest()
        self.input_file('cub_annotation_version_scope.json', self.biology)
        with self.assertRaises(ValueError):
            contract.frozen_supplemental_expectations(self.inputs, self.fingerprints)

    def test_missing_or_duplicate_author_native_label_is_not_a_complete_302_cohort(self):
        for native in (self.native[:-1], self.native[:-1] + [copy.deepcopy(self.native[0])]):
            with self.subTest(count=len(native)):
                self.input_file('structure_biology.json', {'native_labels': native})
                with self.assertRaises(ValueError):
                    contract.frozen_supplemental_expectations(self.inputs, self.fingerprints)

    def test_fewer_or_previously_reviewed_new_cases_cannot_self_fill_expectations(self):
        for cases in (self.biology['mapping_reviews'][:-1],
                      [{'dataset': 'cub200', 'class_id': str(i)} for i in range(1, 13)]):
            with self.subTest(case_ids=[r['class_id'] for r in cases]):
                payload = copy.deepcopy(self.biology)
                payload['mapping_reviews'] = cases
                payload['new_label_scope_reviews'] = len(cases)
                self.input_file('cub_annotation_version_scope.json', payload)
                with self.assertRaises(ValueError):
                    contract.frozen_supplemental_expectations(self.inputs, self.fingerprints)

    def test_scientific_identity_review_requires_each_of_12_groups_17_bridges_one_split(self):
        for kind in ('missing_group', 'missing_bridge', 'extra_split', 'duplicate_group'):
            extent = copy.deepcopy(self.identity)
            if kind == 'missing_group':
                extent['reviewed_identity_groups'].pop()
            elif kind == 'missing_bridge':
                extent['reviewed_identity_groups'][0]['actual_active_bridges'].pop()
            elif kind == 'extra_split':
                extent['repairs'].append(copy.deepcopy(extent['repairs'][0]))
            else:
                extent['reviewed_identity_groups'][-1]['class_id'] = extent['reviewed_identity_groups'][-2]['class_id']
            self.input_file('structure_biology_identity_scope.json', extent)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                contract.frozen_supplemental_expectations(self.inputs, self.fingerprints)

    def test_identity_split_count_boolean_does_not_equal_one_reviewed_split(self):
        name = 'biology-version-scope'
        for value in (True, 1.0, 0):
            report = self.report(name, self.root / 'db.sqlite')
            report['scientific_identity_scope_splits_checked'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                contract.validate_supplemental_report(name, report, self.expected[name], 'synthetic-revision')

    def test_partial_publisher_cohorts_cannot_self_fill_frozen_expectations(self):
        for key, value in (('epa', 50241), ('faa', 94042), ('native', 220247)):
            manifest = copy.deepcopy(self.vehicle)
            if key == 'native':
                manifest['source_native_uid_inventory'] = value
            else:
                manifest['producer_snapshots'][0 if key == 'epa' else 1]['rows'] = value
            self.input_file('structure_vehicle_source_scope.json', manifest)
            with self.subTest(cohort=key), self.assertRaises(ValueError):
                contract.frozen_supplemental_expectations(self.inputs, self.fingerprints)

    def test_partial_reports_cannot_supply_own_expected_200_302_12_counts(self):
        name = 'biology-version-scope'
        for field, value in (('all_200_original_targets_checked', 12),
                             ('native_sql_labels_checked', 200),
                             ('native_public_paths_checked', 12),
                             ('world_exact_guard_rejections_checked', 1)):
            with self.subTest(field=field):
                report = self.report(name, self.root / 'db.sqlite')
                report[field] = value
                with self.assertRaises(ValueError):
                    contract.validate_supplemental_report(name, report, self.expected[name], 'synthetic-revision')

    def test_nested_boolean_and_float_counts_are_not_integer_source_counts(self):
        name = 'vehicle-source-scope'
        for value in (True, 1.0):
            report = self.report(name, self.root / 'db.sqlite')
            report['cohort_counts']['new_relation_counts']['IS_A'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                contract.validate_supplemental_report(name, report, self.expected[name], 'synthetic-revision')

    def test_cars_author_native_and_world_review_cohorts_are_each_complete_unique_196(self):
        for kind in ('missing_native', 'duplicate_native', 'missing_world', 'duplicate_world', 'partial_pairs'):
            author = copy.deepcopy(self.cars_author)
            if kind == 'missing_native':
                author['scope_targets'].pop()
            elif kind == 'duplicate_native':
                author['scope_targets'][-1] = copy.deepcopy(author['scope_targets'][0])
            elif kind == 'missing_world':
                author['world_mapping_reviews'].pop()
            elif kind == 'duplicate_world':
                author['world_mapping_reviews'][-1] = copy.deepcopy(author['world_mapping_reviews'][0])
            else:
                author['source_native_pair_count'] = 19000
            self.input_file('structure_cars_author_scope.json', author)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                contract.frozen_supplemental_expectations(self.inputs, self.fingerprints)

    def test_cars_declared_native_world_and_pair_counts_are_strict_integers(self):
        for field, value in (('source_native_label_count', 195), ('world_mappings_reviewed', 195),
                             ('source_native_label_count', 196.0), ('world_mappings_reviewed', 196.0),
                             ('source_native_pair_count', 19110.0)):
            author = copy.deepcopy(self.cars_author)
            author[field] = value
            self.input_file('structure_cars_author_scope.json', author)
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                contract.frozen_supplemental_expectations(self.inputs, self.fingerprints)

    def test_only_new_native_rank_policy_has_cars_196_while_old_native_has_three_domains(self):
        public, receipt, evidence = self.public_fixture()
        old = receipt['matrix_expected_counts']['source_native']
        new = receipt['matrix_expected_counts']['source_native_rank_floors']
        self.assertEqual(set(old), {'cub200', 'flowers102', 'fgvc_aircraft'})
        self.assertEqual(set(new), set(old) | {'stanford_cars'})
        self.assertEqual(sum(row['labels'] for row in old.values()), 402)
        self.assertEqual(sum(row['pairs'] for row in old.values()), 30001)
        self.assertEqual(sum(row['labels'] for row in new.values()), 598)
        self.assertEqual(sum(row['pairs'] for row in new.values()), 49111)
        for mode in ('legacy', 'reviewed_old_floors', 'reviewed_new_floors', 'reviewed_rank_floors'):
            self.assertEqual(sum(row['labels'] for row in receipt['matrix_expected_counts'][mode].values()), 755)
            self.assertEqual(sum(row['pairs'] for row in receipt['matrix_expected_counts'][mode].values()), 56917)
        contract.validate_public_evidence(public, receipt, evidence)
        for mode in ('source_native', 'source_native_rank_floors'):
            p, r = copy.deepcopy(public), copy.deepcopy(receipt)
            matrix = json.loads(Path(p['evidence']['full-six-matrix']['path']).read_text())
            if mode == 'source_native':
                r['matrix_expected_counts'][mode]['stanford_cars'] = copy.deepcopy(new['stanford_cars'])
                matrix[mode]['datasets']['stanford_cars'] = copy.deepcopy(matrix['source_native_rank_floors']['datasets']['stanford_cars'])
            else:
                del r['matrix_expected_counts'][mode]['stanford_cars']
                del matrix[mode]['datasets']['stanford_cars']
            self.write_report('full-six-matrix', matrix, p)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                contract.validate_public_evidence(p, r, evidence)

    def test_public_matrix_counts_keep_integer_type_under_exact_mode_comparison(self):
        for bad_value in (True, 1.0):
            public, receipt, evidence = self.public_fixture()
            matrix_path = Path(public['evidence']['full-six-matrix']['path'])
            matrix = json.loads(matrix_path.read_text())
            receipt['matrix_expected_counts']['reviewed_new_floors']['cub200']['APPLICABLE'] = 1
            matrix['reviewed_new_floors']['datasets']['cub200']['counts']['APPLICABLE'] = 1
            self.write_report('full-six-matrix', matrix, public)
            contract.validate_public_evidence(public, receipt, evidence)
            matrix['reviewed_new_floors']['datasets']['cub200']['counts']['APPLICABLE'] = bad_value
            self.write_report('full-six-matrix', matrix, public)
            with self.subTest(value=bad_value), self.assertRaises(ValueError):
                contract.validate_public_evidence(public, receipt, evidence)

    def test_complete_public_fixture_passes_as_a_contract_fixture(self):
        public, receipt, evidence = self.public_fixture()
        self.assertEqual(contract.validate_public_evidence(public, receipt, evidence), contract.file_sha256(evidence))

    def test_required_supplement_cannot_be_deleted_from_receipt_or_public_jobs(self):
        for where in ('receipt', 'public'):
            public, receipt, evidence = self.public_fixture()
            for name in self.expected:
                with self.subTest(where=where, name=name):
                    p, r = copy.deepcopy(public), copy.deepcopy(receipt)
                    if where == 'receipt':
                        del r['supplemental_audits'][name]
                    else:
                        del p['evidence'][name]
                    with self.assertRaises(ValueError):
                        contract.validate_public_evidence(p, r, evidence)

    def test_every_actual_report_must_bind_download_path_and_revision(self):
        names = ('living', 'whole-library', 'exports', 'public-cli', 'source-contracts',
                 'biology-version-scope', 'vehicle-source-scope', 'full-six-matrix')
        for name in names:
            for field, value in (('database', str(self.root / 'OTHER.sqlite')),
                                 ('database_revision', 'OLD-REVISION')):
                public, receipt, evidence = self.public_fixture()
                row = json.loads(Path(public['evidence'][name]['path']).read_text())
                if name == 'full-six-matrix':
                    row['reviewed_new_floors'][field] = value
                else:
                    row[field] = value
                    if field == 'database_revision' and name in self.expected:
                        row['revision'] = value
                self.write_report(name, row, public)
                with self.subTest(name=name, field=field), self.assertRaises(ValueError):
                    contract.validate_public_evidence(public, receipt, evidence)

    def test_local_supplement_hash_and_content_are_retained(self):
        for tamper_hash in (True, False):
            public, receipt, evidence = self.public_fixture()
            local = receipt['supplemental_audits']['biology-version-scope']
            path = Path(local['path'])
            report = json.loads(path.read_text())
            report['native_public_paths_checked'] = 12
            path.write_text(json.dumps(report))
            if not tamper_hash:
                local['sha256'] = contract.file_sha256(path)
            with self.subTest(stale_hash=tamper_hash), self.assertRaises(ValueError):
                contract.validate_public_evidence(public, receipt, evidence)

    def test_true_false_are_never_integer_process_exit_codes(self):
        receipt = {'schema': 'FINEATLAS_STRUCTURE_ACCEPTANCE_V1',
                   **{key: True for key in ('complete', 'all_pass', 'candidate_unchanged',
                                            'inputs_unchanged', 'code_unchanged')},
                   'ended_utc': 'synthetic', 'jobs': {name: {
                       'pass': True, 'exit_code': 0, 'ended_utc': 'synthetic'}
                       for name in contract.REQUIRED_JOBS}}
        contract.validate_completed_acceptance(receipt)
        for value in (False, True, 0.0):
            changed = copy.deepcopy(receipt)
            changed['jobs']['contracts']['exit_code'] = value
            with self.subTest(exit_code=value), self.assertRaises(ValueError):
                contract.validate_completed_acceptance(changed)

    def test_optimized_acceptance_cli_is_rejected_before_database_access(self):
        result = subprocess.run([sys.executable, '-O', str(ROOT / 'scripts/accept_structure_candidate.py'), '--help'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Optimized Python is forbidden', result.stderr)


if __name__ == '__main__':
    unittest.main()
