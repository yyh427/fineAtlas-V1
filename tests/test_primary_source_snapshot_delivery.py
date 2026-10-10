"""Public source snapshots cannot borrow a host file or unverified retrieval."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import primary_source_snapshot_delivery as sources


class PortableSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.inputs = self.root / 'inputs'; self.inputs.mkdir()
        self.data = b'%PDF source snapshot'; self.sha = hashlib.sha256(self.data).hexdigest()
        self.entry = {'filename':'official.pdf','source_uri':'https://www.boeing.com/example.pdf',
            'sha256':self.sha,'hash_basis':'HTTP_RESPONSE_BODY_BYTES','mime_type':'application/pdf',
            'revision_locator':'REV sealed','redistribution_authorization':'NOT_ASSERTED_SOURCE_BYTES_NOT_PACKAGED'}
        self.registry = {'schema':sources.REGISTRY_SCHEMA,'documents':{'doc':self.entry}}
        self.manifest = {'primary_documents':{'doc':{'source_uri':self.entry['source_uri'],'sha256':self.sha}}}
        self.save(); self.directory = self.root / 'new-public-snapshots'; self.report = self.root / 'retrieval.json'
    def save(self):
        (self.inputs/sources.REGISTRY_NAME).write_text(json.dumps(self.registry))
        (self.inputs/'structure_primary_aircraft_family_repairs.json').write_text(json.dumps(self.manifest))
    def make_receipt(self):
        self.directory.mkdir(); (self.directory/'official.pdf').write_bytes(self.data)
        row=dict(self.entry); row.update(final_uri=self.entry['source_uri'],http_status=200,
            retrieved_from_network=True,retrieved_utc='now',byte_count=len(self.data))
        value={'schema':sources.RECEIPT_SCHEMA,'pass':True,'complete':True,'fresh_official_https_retrieval':True,
            'registry_sha256':sources.digest(self.inputs/sources.REGISTRY_NAME),
            'snapshots_directory':str(self.directory),'documents':{'doc':row},'errors':[]}
        self.report.write_text(json.dumps(value)); return value
    def test_complete_fresh_http_receipt_and_bytes_pass(self):
        self.make_receipt(); self.assertTrue(sources.require_fresh_retrieval(self.report,self.inputs,self.directory)['pass'])
    def test_local_presence_does_not_substitute_for_network_receipt(self):
        value=self.make_receipt(); value['documents']['doc']['retrieved_from_network']=False
        self.report.write_text(json.dumps(value))
        with self.assertRaises(ValueError): sources.require_fresh_retrieval(self.report,self.inputs,self.directory)
    def test_changed_actual_bytes_block_even_valid_receipt(self):
        self.make_receipt(); (self.directory/'official.pdf').write_bytes(b'changed')
        with self.assertRaises(ValueError): sources.require_fresh_retrieval(self.report,self.inputs,self.directory)
    def test_absolute_or_traversal_registry_locator_blocked(self):
        for name in ('/host/old.pdf','../old.pdf','sub/old.pdf','..','bad\\old.pdf'):
            self.entry['filename']=name; self.save()
            with self.assertRaises(ValueError): sources.registry(self.inputs)
    def test_non_https_and_unofficial_redirect_blocked(self):
        value=self.make_receipt(); value['documents']['doc']['final_uri']='https://unofficial.example/file'
        self.report.write_text(json.dumps(value))
        with self.assertRaises(ValueError): sources.require_fresh_retrieval(self.report,self.inputs,self.directory)
    def test_unreceipted_existing_directory_never_reused(self):
        self.directory.mkdir()
        with patch.object(sources.urllib.request,'build_opener') as network:
            with self.assertRaisesRegex(ValueError,'must be new'): sources.retrieve(self.inputs,self.directory,self.report)
            network.assert_not_called()
    def test_symlink_to_host_source_is_rejected(self):
        self.make_receipt(); file=self.directory/'official.pdf'; file.unlink()
        host=self.root/'host.pdf'; host.write_bytes(self.data); file.symlink_to(host)
        with self.assertRaises(ValueError): sources.require_fresh_retrieval(self.report,self.inputs,self.directory)
    def test_official_failure_preserves_material_and_prevents_repeat(self):
        with patch.object(sources.urllib.request,'build_opener') as network:
            network.return_value.open.side_effect=PermissionError('official denied')
            with self.assertRaises(PermissionError): sources.retrieve(self.inputs,self.directory,self.report)
        failure=self.report.with_suffix('.failed.json')
        self.assertFalse(json.loads(failure.read_text())['pass'])
        with self.assertRaises(ValueError): sources.retrieve(self.inputs,self.directory,self.report)
    def test_fresh_network_response_is_written_then_completely_revalidated(self):
        from email.message import Message
        response=io.BytesIO(self.data); response.status=200
        response.headers=Message(); response.headers['Content-Type']='application/pdf'
        response.geturl=lambda:self.entry['source_uri']
        with patch.object(sources.urllib.request,'build_opener') as network:
            network.return_value.open.return_value=response
            self.assertTrue(sources.retrieve(self.inputs,self.directory,self.report)['pass'])
            network.return_value.open.assert_called_once()
        with patch.object(sources.urllib.request,'build_opener') as network:
            self.assertTrue(sources.retrieve(self.inputs,self.directory,self.report)['pass'])
            network.assert_not_called()
    def test_changed_http_response_saved_as_failure_and_cannot_pass(self):
        from email.message import Message
        response=io.BytesIO(b'updated official bytes'); response.status=200
        response.headers=Message(); response.headers['Content-Type']='application/pdf'
        response.geturl=lambda:self.entry['source_uri']
        with patch.object(sources.urllib.request,'build_opener') as network:
            network.return_value.open.return_value=response
            with self.assertRaises(ValueError): sources.retrieve(self.inputs,self.directory,self.report)
        self.assertTrue(self.report.with_suffix('.failed.json').exists())
        self.assertFalse(self.report.exists())
        self.assertEqual((self.directory/'official.pdf').read_bytes(),b'updated official bytes')


if __name__ == '__main__': unittest.main()
