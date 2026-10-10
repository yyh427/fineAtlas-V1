"""Portable evidence cannot fall back to historical files on the host."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import structure_regression_support as support
import audit_portable_legacy_pair_regressions as audit


class PortableRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.directory=self.root/'public-support';self.directory.mkdir()
        self.host=self.root/'historical-agent-evidence.json';self.host.write_text('{"review":"actual"}')
        file=self.directory/'evidence.json';file.write_bytes(self.host.read_bytes())
        ledger=self.directory/'dispositions.json';ledger.write_text('{"groups":[]}')
        self.row={'path':str(self.host),'sha256':support.digest(file)}
        self.value={'schema':support.SCHEMA,'original_ledger_bytes_preserved':True,
            'historical_paths_are_registry_keys_only':True,'dispositions_sha256':support.digest(ledger),
            'evidence_locator_map':{str(self.host):'evidence.json'},
            'files':{'evidence.json':support.digest(file),'dispositions.json':support.digest(ledger)}}
        formal=self.directory/'formal/formal-baseline-verification.json';formal.parent.mkdir();formal.write_text(json.dumps({'preserved_public_evidence':{}}))
        self.value['files']['formal/formal-baseline-verification.json']=support.digest(formal)
        self.value.update(formal_baseline_verification_record_sha256=support.digest(formal),formal_baseline_evidence_locators={})
        self.registry=self.directory/'support-registry.json';self.save()
    def save(self):self.registry.write_text(json.dumps(self.value))
    def test_exact_original_bytes_resolve_only_inside_public_support(self):
        actual=support.PortableRegressionSupport(self.registry)
        self.assertEqual(actual.evidence(self.row,self.directory/'dispositions.json'),self.directory/'evidence.json')
    def test_missing_portable_file_cannot_borrow_existing_host_evidence(self):
        (self.directory/'evidence.json').unlink()
        with self.assertRaises(ValueError):support.PortableRegressionSupport(self.registry)
        self.assertTrue(self.host.is_file())
    def test_changed_public_evidence_does_not_use_correct_host_copy(self):
        (self.directory/'evidence.json').write_text('wrong public bytes')
        with self.assertRaises(ValueError):support.PortableRegressionSupport(self.registry)
    def test_missing_locator_has_no_host_fallback(self):
        actual=support.PortableRegressionSupport(self.registry)
        with self.assertRaisesRegex(ValueError,'host fallback'):
            actual.evidence({'path':'/another/host/file','sha256':self.row['sha256']},self.directory/'dispositions.json')
    def test_absolute_archive_registry_member_rejected(self):
        self.value['files']={str(self.host):self.row['sha256']};self.save()
        with self.assertRaises(ValueError):support.PortableRegressionSupport(self.registry)
    def test_path_traversal_member_rejected(self):
        self.value['files']={'../historical-agent-evidence.json':self.row['sha256']};self.save()
        with self.assertRaises(ValueError):support.PortableRegressionSupport(self.registry)
    def test_original_ledger_cannot_be_rewritten_to_make_paths_relative(self):
        (self.directory/'dispositions.json').write_text('rewritten')
        with self.assertRaises(ValueError):support.PortableRegressionSupport(self.registry)
    def test_symlink_to_host_cannot_substitute(self):
        p=self.directory/'evidence.json';p.unlink();p.symlink_to(self.host)
        with self.assertRaises(ValueError):support.PortableRegressionSupport(self.registry)
    def test_self_citing_ledger_is_still_rejected(self):
        self.value['evidence_locator_map'][str(self.host)]='dispositions.json';self.save()
        actual=support.PortableRegressionSupport(self.registry)
        with self.assertRaises(ValueError):actual.evidence(self.row,self.directory/'dispositions.json')
    def test_empty_external_evidence_is_not_accepted(self):
        actual=support.PortableRegressionSupport(self.registry)
        with self.assertRaises(ValueError):audit.evidence_files([],self.directory/'dispositions.json',actual)
    def test_host_ledger_is_rejected_even_if_same_bytes(self):
        actual=support.PortableRegressionSupport(self.registry)
        host=self.root/'host-ledger.json';host.write_bytes((self.directory/'dispositions.json').read_bytes())
        with self.assertRaises(ValueError):actual.evidence(self.row,host)
    def test_nested_ledger_evidence_collection_preserves_declared_locators(self):
        self.assertEqual(list(support.evidence_rows({'groups':[{'evidence':[self.row],'labels':[{'source_evidence':[self.row]}]}]})),[self.row,self.row])
    def test_real_package_compression_and_hash_verified_roundtrip(self):
        config={'legacy_dispositions':str(self.directory/'dispositions.json'),
            'legacy_reference':str(self.root/'formal.csv'),'reference':str(self.root/'rows.json'),
            'inventory':str(self.root/'inventory.json'),'legacy_baseline_matrix':str(self.root/'baseline'),
            'delivery_root':str(self.root/'delivery'),'formal_baseline_verification_record':str(self.root/'formal-record.json')}
        Path(config['formal_baseline_verification_record']).write_text(json.dumps({'schema':'FINEATLAS_FORMAL_PUBLIC_BASELINE_PREREQUISITE_V1',
            'all_pass':True,'release':'v1.10.1','actual_public_default_install_verified':True,
            'fresh_download_this_candidate_turn':False,'preserved_public_evidence':{}}))
        for key in ('legacy_reference','reference','inventory'):Path(config[key]).write_text('original material')
        baseline=Path(config['legacy_baseline_matrix']);baseline.mkdir()
        for name in ('legacy-pairs.csv',*[f'legacy-{dataset}-labels.json'for dataset in support.DATASETS]):(baseline/name).write_text('original matrix')
        ledger=Path(config['legacy_dispositions']);ledger.write_text(json.dumps({'groups':[{'evidence':[self.row]}]}))
        gate={'pass':True,'complete':True,'candidate_revision':'actual-final',
            'dispositions_sha256':support.digest(ledger),'baseline_matrix_sha256':support.digest(baseline/'legacy-pairs.csv'),
            'reference_export_sha256':support.digest(Path(config['legacy_reference'])),
            'policy_sha256':'old-policy','candidate_matrix_sha256':'actual-final-matrix'}
        target=Path(config['delivery_root'])/'local-legacy-regressions/summary.json';target.parent.mkdir(parents=True);target.write_text(json.dumps(gate))
        accepted={'release':'v1.11.0rc1','database_revision':'actual-final','database_sha256':'actual-byte-sha'}
        manifest,archive=support.package_support(config,self.root/'package',accepted)
        extracted=support.PortableRegressionSupport(self.root/'package/roundtrip/support-registry.json')
        self.assertEqual((extracted.root/'dispositions.json').read_bytes(),ledger.read_bytes())
        self.assertEqual(extracted.value['candidate_matrix_sha256'],'actual-final-matrix')
        self.assertEqual(extracted.evidence(self.row,extracted.root/'dispositions.json').read_bytes(),self.host.read_bytes())
        self.assertEqual(json.loads(manifest.read_text())['archive']['sha256'],support.digest(archive))


if __name__=='__main__':unittest.main()
