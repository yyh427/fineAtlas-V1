"""Exact prior history and independent complete-part scope cannot be bypassed."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import test_audit_source_contract_candidate as original


class PriorStatusAndPrimaryScopeTest(unittest.TestCase):
    def fixture(self, root):
        return original.SourceContractCandidateAuditTest().fixture(root)

    def rebind(self, con, inputs, name):
        manifest = json.loads(con.execute(
            "SELECT value FROM metadata WHERE key='structure_frozen_build_manifest'").fetchone()[0])
        manifest['inputs'][name] = original.AUDIT.sha((inputs / name).read_bytes())
        con.execute("UPDATE metadata SET value=? WHERE key='structure_frozen_build_manifest'",
                    (json.dumps(manifest),))
        con.commit()

    def test_preexisting_rejected_duplicate_preserved_without_fabricated_new_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            con, db, inputs, _ = self.fixture(Path(tmp))
            con.execute("UPDATE entity_relations SET status='REJECTED' WHERE id=8")
            con.execute('DELETE FROM usability_changes WHERE id=8')
            prior = inputs / 'source_contract_prior_status_distributions.json'
            data = json.loads(prior.read_text())
            data['counts']['prior_status_counts'] = {'ACTIVE': 1, 'REJECTED': 1}
            data['entries'][0]['prior_status_reason_distribution'] = [
                {'status': 'ACTIVE', 'reason': None, 'count': 1},
                {'status': 'REJECTED', 'reason': None, 'count': 1},
            ]
            prior.write_text(json.dumps(data));self.rebind(con, inputs, prior.name)
            result = original.AUDIT.audit(db, inputs, Path(tmp) / 'retained')
            self.assertTrue(result['pass'], result['failures'])
            self.assertEqual(result['counts']['frozen_originally_active_source_rows'], 1)
            self.assertEqual(result['counts']['existing_terminal_source_rows_preserved'], 1)
            con.execute("UPDATE entity_relations SET status='REVIEW' WHERE id=8");con.commit()
            rejected = original.AUDIT.audit(db, inputs, Path(tmp) / 'arbitrary-nonactive')
            self.assertFalse(rejected['pass'])
            self.assertTrue(any('FROZEN_PRIOR_STATUS_REASON_DISTRIBUTION_DIFFERS' in f.get('errors', [])
                                for f in rejected['failures']))
            con.close()

    def test_prior_asset_is_required_and_must_match_frozen_metadata_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            con, db, inputs, _ = self.fixture(Path(tmp))
            prior = inputs / 'source_contract_prior_status_distributions.json'
            data = json.loads(prior.read_text());data['counts']['original_source_rows'] = 99
            prior.write_text(json.dumps(data))
            result = original.AUDIT.audit(db, inputs, Path(tmp) / 'unbound')
            self.assertFalse(result['pass'])
            self.assertTrue(any(f['check'] == 'PRIOR_SOURCE_STATUSES_NOT_BOUND_TO_DATABASE_REVISION'
                                for f in result['failures']))
            prior.unlink()
            result = original.AUDIT.audit(db, inputs, Path(tmp) / 'missing')
            self.assertTrue(any(f['check'] == 'MISSING_INDEPENDENT_FROZEN_PRIOR_SOURCE_STATUS_INVENTORY'
                                for f in result['failures']))
            con.close()

    def test_preserved_rejection_reason_is_not_interchangeable(self):
        row = {'id': 999, 'status': 'REJECTED', 'reason': 'Changed historical reason'}
        prior = {'multiplicity': 1, 'prior_status_reason_distribution': [
            {'status': 'REJECTED', 'reason': 'Original historical reason', 'count': 1}]}
        errors = original.AUDIT.prior_disposition_errors(None, 'edges', [row], prior,
                                                        'input', ledger_index={})
        self.assertIn('FROZEN_PRIOR_STATUS_REASON_DISTRIBUTION_DIFFERS', errors)

    def protection_fixture(self):
        audit = original.AUDIT
        sr = {'P1001': '1N4148WS-G', 'P1000': '86460', 'T8270': 'Single',
              'url': '/diodes/ss-schottky/'}
        parent = {'uid': 'vishay-type:small-signal-switching-diode', 'data': '{}',
                  'description': 'small-signal switching diode type explicitly declared in Vishay product technology/description.'}
        raw = {'source_id': 'vishay-switching', 'source_record': sr,
               'parent_uid': parent['uid'], 'source_sha256': audit.sha('original vendor table')}
        child = {'uid': 'vishay-part:1n4148ws-g', 'data': json.dumps(raw),
                 'source': 'Vishay native parametric catalog'}
        native = {'source_record_uid': child['uid'], 'native_record_sha256': audit.sha(child['data']),
                  'reviewed_parent_uid': parent['uid'], 'parent_definition_sha256': audit.sha(parent['description']),
                  'source_snapshot_sha256': raw['source_sha256'], 'source_scope_entails_parent': True}
        record = {'child_source_record': child, 'parent_source_record': parent,
                  'independent_native_scope_witness': native, 'table': 'entity_relations',
                  'locator': {'content_sha256': audit.sha('original claim')}}
        proof = {'source_record_uid': child['uid'], 'native_record_sha256': audit.sha(child['data']),
                 'reviewed_parent_uid': parent['uid'], 'parent_native_record_sha256': audit.sha(parent['data']),
                 'parent_definition_sha256': audit.sha(parent['description']),
                 'source_catalog_snapshot_sha256': raw['source_sha256'], 'native_part_number': sr['P1001'],
                 'native_document_id': sr['P1000'], 'native_circuit_configuration': sr['T8270'],
                 'native_catalog_row_url_preserved': sr['url'], 'individual_semantic_review': True,
                 'source_scope_entails_parent': True, 'identity_assertion': False,
                 'synthetic_adapter_description_used_as_scope_evidence': False,
                 'scope_observation': 'Exact publisher subject, class title and complete single-part circuit reviewed.',
                 'primary_datasheet': {'publisher': 'Vishay Semiconductors',
                     'request_uri': 'https://www.vishay.com/doc?86460',
                     'final_uri': 'https://www.vishay.com/docs/86460/1n4148ws-g.pdf', 'http_status': 200,
                     'document_number': '86460', 'document_product_header': '1N4148WS-G',
                     'document_class_title': 'Small Signal Fast Switching Diode',
                     'parts_table_circuit_configuration': 'Single', 'revision': 'Rev. 1.2',
                     'pdf_sha256': audit.sha('PDF bytes'), 'extracted_text_sha256': audit.sha('native text'),
                     'retrieved_utc': '2026-10-09T18:00:00Z', 'primary_source_text_only': True,
                     'field_locators': {'product_header': {'page': 1, 'line': 1},
                         'class_title': {'page': 1, 'line': 12},
                         'circuit_configuration': {'page': 1, 'line': 65,
                             'section': 'PARTS TABLE', 'column': 'CIRCUIT CONFIGURATION'}}}}
        case = {'uid': child['uid'], 'parent': parent['uid'], 'table': record['table'],
                'locator': record['locator'], 'disposition': 'PROTECTED_PRIMARY_SCOPE_SUPPORTED', 'proof': proof}
        case['manual_proof_sha256'] = audit.sha(json.dumps(proof, sort_keys=True))
        return record, case

    def test_menu_route_and_flags_alone_cannot_protect_a_part(self):
        record, case = self.protection_fixture()
        self.assertTrue(original.AUDIT.protection_errors(record))
        self.assertEqual(original.AUDIT.protection_errors(record, additional_cases=[case]), [])

    def test_primary_whole_subject_circuit_class_document_and_publisher_are_required(self):
        record, case = self.protection_fixture()
        for field, value in [('document_product_header', '1N4148WS'),
                             ('parts_table_circuit_configuration', 'Dual'),
                             ('document_class_title', 'Small Signal Schottky Diode'),
                             ('document_number', '99999'),
                             ('final_uri', 'https://vendor-copy.example/docs/86460/part.pdf')]:
            with self.subTest(field=field):
                wrong = copy.deepcopy(case);wrong['proof']['primary_datasheet'][field] = value
                wrong['manual_proof_sha256'] = original.AUDIT.sha(json.dumps(wrong['proof'], sort_keys=True))
                self.assertTrue(original.AUDIT.protection_errors(record, additional_cases=[wrong]))

    def test_primary_proof_is_not_reusable_for_another_source_locator(self):
        record, case = self.protection_fixture()
        case['locator'] = {'content_sha256': original.AUDIT.sha('different source claim')}
        self.assertIn('ADDITIONAL_PRIMARY_PROTECTION_CASE_OR_PROOF_MISMATCH',
                      original.AUDIT.protection_errors(record, additional_cases=[case]))


if __name__ == '__main__':
    unittest.main()
