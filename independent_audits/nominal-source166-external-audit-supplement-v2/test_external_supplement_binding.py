import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import external_audit_supplement_binding as binding
import package_external_audit_supplement as packaging


class SupplementCodeBinding(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.public=Path(self.temp.name)/'public'
        self.root=self.public/'external-audit-supplement/version'
        self.here=self.root/'nominal-design-scope-final-plan-v1';self.here.mkdir(parents=True)
        self.source=self.here/'observer.py';self.source.write_text('# independent fixture source\n')
        self.manifest={'schema':'FINEATLAS_INDEPENDENT_EXTERNAL_AUDIT_SUPPLEMENT_CODE_V1','supplement_version':'source166-class-case-v2','frozen_source9_input_seal_sha256':'seal','original_frozen_observer_failed':True,'files':{'nominal-design-scope-final-plan-v1/observer.py':binding.digest(self.source)}}
        self.mp=self.root/'SUPPLEMENT_CODE_MANIFEST.json';self.mp.write_text(json.dumps(self.manifest))
        self.archive=self.public/'supplement.tar.gz';self.archive.write_bytes(b'archive fixture')
        self.plan={'final_source_seal_sha256':'seal','external_audit_supplement':{'manifest':str(self.mp),'manifest_sha256':binding.digest(self.mp),'archive_url':'https://example.invalid/release/supplement.tar.gz','archive_sha256':binding.digest(self.archive),'archive_bytes':self.archive.stat().st_size},'execution':{'fresh-public':{'command':['python','-B','observer','--database',str(self.public/'data/fineatlas.sqlite')]}}}
        self.proof={'schema':'FINEATLAS_EXTERNAL_AUDIT_SUPPLEMENT_DOWNLOAD_PROOF_V1','fresh_download':True,'network_request':True,'authenticated':False,'source_url':self.plan['external_audit_supplement']['archive_url'],'response_url':'https://example.invalid/assets/supplement.tar.gz','archive':str(self.archive),'archive_sha256':binding.digest(self.archive),'archive_bytes':self.archive.stat().st_size,'archive_stamp':[self.archive.stat().st_size,self.archive.stat().st_mtime_ns,self.archive.stat().st_ino],'extracted_root':str(self.root),'manifest_sha256':binding.digest(self.mp),'member_sha256':{**self.manifest['files'],'SUPPLEMENT_CODE_MANIFEST.json':binding.digest(self.mp)}}
        self.pp=self.public/'supplement-download.json';self.save_proof()
    def save_proof(self):
        self.pp.write_text(json.dumps(self.proof));self.plan['execution']['fresh-public'].update(external_audit_supplement_download_receipt=str(self.pp),external_audit_supplement_download_receipt_sha256=binding.digest(self.pp))
    def require(self,phase='fresh-public'):return binding.require_supplement(self.plan,phase,self.here)
    def test_exact_local_manifest_source_binding(self):self.assertTrue(self.require('local')['pass'])
    def test_exact_public_download_fixture_binding(self):self.assertTrue(self.require()['pass'])
    def test_missing_supplement_cannot_run_original_failed_source(self):
        del self.plan['external_audit_supplement'];self.assertRaises(KeyError,self.require)
    def test_source_changed_after_manifest_rejected(self):
        self.source.write_text('# changed\n');self.assertRaises(AssertionError,self.require)
    def test_non_network_receipt_cannot_certify_public(self):
        self.proof['network_request']=False;self.save_proof();self.assertRaises(AssertionError,self.require)
    def test_cached_receipt_cannot_certify_fresh_public(self):
        self.proof['fresh_download']=False;self.save_proof();self.assertRaises(AssertionError,self.require)
    def test_archive_wrong_hash_rejected(self):
        self.archive.write_bytes(b'different');self.assertRaises(AssertionError,self.require)
    def test_old_agent_manifest_cannot_be_borrowed_public(self):
        other=Path(self.temp.name)/'agent';self.root.rename(other);self.here=other/self.here.name;self.plan['external_audit_supplement']['manifest']=str(other/'SUPPLEMENT_CODE_MANIFEST.json');self.assertRaises(AssertionError,self.require)
    def test_undeclared_code_file_rejected(self):
        (self.root/'injected.py').write_text('# injected\n');self.assertRaises(AssertionError,self.require)
    def test_different_source_input_seal_rejected(self):
        self.plan['final_source_seal_sha256']='other';self.assertRaises(AssertionError,self.require)
    def test_archive_packaging_is_deterministic(self):
        first=packaging.package(self.root,Path(self.temp.name)/'one.tar.gz');second=packaging.package(self.root,Path(self.temp.name)/'two.tar.gz');self.assertEqual(first['archive_sha256'],second['archive_sha256'])


if __name__=='__main__':unittest.main()
