"""Seventh sources add one verified transfer without redownloading prior bytes."""
import hashlib
import io
import json
from email.message import Message
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import primary_source_snapshot_delivery as primary
import owned_source_snapshot_delivery as owned


class AdditionalSourceRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.inputs=self.root/'inputs';self.inputs.mkdir();self.directory=self.root/'snapshots';self.directory.mkdir()
        self.old_bytes=b'%PDF old verified';self.new_bytes=b'%PDF new official'
        def entry(name,uri,raw):return {'filename':name,'source_uri':uri,'sha256':hashlib.sha256(raw).hexdigest(),
            'hash_basis':'HTTP_RESPONSE_BODY_BYTES','mime_type':'application/pdf','revision_locator':'sealed revision',
            'redistribution_authorization':'NOT_ASSERTED_SOURCE_BYTES_NOT_PACKAGED'}
        self.old=entry('old.pdf','https://www.boeing.com/old.pdf',self.old_bytes)
        self.new=entry('new.pdf','https://www.easa.europa.eu/new.pdf',self.new_bytes)
        (self.inputs/primary.REGISTRY_NAME).write_text(json.dumps({'schema':primary.REGISTRY_SCHEMA,'documents':{'old':self.old}}))
        (self.inputs/'structure_primary_aircraft_family_repairs.json').write_text(json.dumps({'primary_documents':{'old':{'source_uri':self.old['source_uri'],'sha256':self.old['sha256']}}}))
        (self.inputs/owned.NAME).write_text(json.dumps({'schema':primary.REGISTRY_SCHEMA,'documents':{'new':self.new}}))
        (self.directory/'old.pdf').write_bytes(self.old_bytes)
        row=dict(self.old);row.update(final_uri=self.old['source_uri'],http_status=200,byte_count=len(self.old_bytes),retrieved_from_network=True,retrieved_utc='previous retrieval')
        self.first=self.root/'old-retrieval.json';self.first.write_text(json.dumps({'schema':primary.RECEIPT_SCHEMA,'pass':True,'complete':True,
            'fresh_official_https_retrieval':True,'registry_sha256':primary.digest(self.inputs/primary.REGISTRY_NAME),
            'snapshots_directory':str(self.directory),'documents':{'old':row},'errors':[]}))
        self.output=self.root/'new-retrieval.json'
    def response(self,data):
        result=io.BytesIO(data);result.status=200;result.headers=Message();result.headers['Content-Type']='application/pdf'
        result.geturl=lambda:self.new['source_uri'];return result
    def success(self):
        with patch.object(owned.urllib.request,'build_opener')as network:
            network.return_value.open.return_value=self.response(self.new_bytes)
            result=owned.retrieve_owned(self.inputs,self.directory,self.output,self.first)
            network.return_value.open.assert_called_once()
        return result
    def test_new_document_only_preserves_original_verified_source(self):
        old_receipt=primary.digest(self.first);self.assertTrue(self.success()['pass'])
        self.assertEqual((self.directory/'old.pdf').read_bytes(),self.old_bytes)
        self.assertEqual(primary.digest(self.first),old_receipt)
    def test_complete_second_receipt_resumes_without_any_new_request(self):
        self.success()
        with patch.object(owned.urllib.request,'build_opener')as network:
            self.assertTrue(owned.retrieve_owned(self.inputs,self.directory,self.output,self.first)['pass']);network.assert_not_called()
    def test_old_source_changed_blocks_additional_retrieval(self):
        (self.directory/'old.pdf').write_bytes(b'changed')
        with self.assertRaises(ValueError):owned.retrieve_owned(self.inputs,self.directory,self.output,self.first)
    def test_unreceipted_extra_file_is_never_borrowed(self):
        (self.directory/'new.pdf').write_bytes(self.new_bytes)
        with self.assertRaises(ValueError):owned.retrieve_owned(self.inputs,self.directory,self.output,self.first)
    def test_wrong_official_body_is_preserved_as_failure(self):
        with patch.object(owned.urllib.request,'build_opener')as network:
            network.return_value.open.return_value=self.response(b'changed official source')
            with self.assertRaises(ValueError):owned.retrieve_owned(self.inputs,self.directory,self.output,self.first)
        self.assertTrue(self.output.with_suffix('.failed.json').exists());self.assertFalse(self.output.exists())
        with self.assertRaises(ValueError):owned.retrieve_owned(self.inputs,self.directory,self.output,self.first)
    def test_conflicting_existing_source_filename_is_not_overwritten(self):
        self.new['filename']='old.pdf'
        (self.inputs/owned.NAME).write_text(json.dumps({'schema':primary.REGISTRY_SCHEMA,'documents':{'new':self.new}}))
        with self.assertRaises(ValueError):owned.retrieve_owned(self.inputs,self.directory,self.output,self.first)
    def test_changed_source_after_retrieval_cannot_finalize(self):
        self.success();(self.directory/'new.pdf').write_bytes(b'changed')
        with self.assertRaises(ValueError):owned.require_owned_retrieval(self.output,self.inputs,self.directory,self.first)


if __name__=='__main__':unittest.main()
