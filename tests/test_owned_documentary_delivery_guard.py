"""Actual documentary and author bytes cannot be replaced by receipt counts."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import structure_owned_scope_delivery_guard as guard


class OwnedDocumentaryGuards(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.inputs=self.root/'inputs';self.inputs.mkdir()
        self.snapshots=self.root/'explicit-snapshots';self.snapshots.mkdir()
        self.database=self.root/'database.sqlite';self.manifest=self.inputs/'structure_owned_scope_repairs.json'
        self.source=self.snapshots/'official.pdf';self.source.write_bytes(b'%PDF actual body')
        self.doc={'source_kind':'PRIMARY_MANUFACTURER_OR_REGULATOR','source_uri':'https://example.gov/official.pdf',
            'sha256':hashlib.sha256(self.source.read_bytes()).hexdigest()}
        self.op={'op':'link','proof':{'primary_documents':[self.doc]}}
        self.value={'primary_snapshots_dir':str(self.snapshots),'verified_primary_sources':{
            'official.pdf':{key:self.doc[key]for key in ('source_uri','sha256')}}}
        self.registry=self.inputs/'structure_owned_source_snapshots.json'
        self.registry.write_text(json.dumps({'schema':'FINEATLAS_PORTABLE_PRIMARY_SOURCE_SNAPSHOTS_V1',
            'documents':{'official':{'filename':'official.pdf','source_uri':self.doc['source_uri'],
                                   'sha256':self.doc['sha256'],'hash_basis':'HTTP_RESPONSE_BODY_BYTES'}}}))
        with sqlite3.connect(self.database)as c:c.execute('CREATE TABLE metadata(key,value)')
        self.files=[];self.save()
    def save(self):
        (self.inputs/'ops.jsonl').write_text(json.dumps(self.op)+'\n')
        self.manifest.write_text(json.dumps({'operations_file':'ops.jsonl','author_annotation_files':self.files}))
        frozen={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in self.inputs.iterdir()}
        with sqlite3.connect(self.database)as c:
            c.execute('DELETE FROM metadata');c.execute('INSERT INTO metadata VALUES(?,?)',
                ('structure_frozen_build_manifest',json.dumps({'inputs':frozen})))
    def validate(self):
        with patch.object(guard,'input_path',return_value=self.manifest),patch.object(guard,'validate_delta_receipt',return_value=self.value):
            return guard.require_owned_scope_receipt('actual-report',self.database,self.inputs,'revision',self.root)
    def test_exact_required_source_set_and_real_bytes_pass(self):self.assertIs(self.validate(),self.value)
    def test_report_cannot_omit_required_document(self):
        self.value['verified_primary_sources']={}
        with self.assertRaises(ValueError):self.validate()
    def test_report_cannot_add_unrequired_document(self):
        self.value['verified_primary_sources']['extra.pdf']={'sha256':'invented','source_uri':'https://example.gov/extra'}
        with self.assertRaises(ValueError):self.validate()
    def test_valid_report_with_changed_body_fails(self):
        self.source.write_bytes(b'changed response')
        with self.assertRaises(ValueError):self.validate()
    def test_actual_source_directory_required(self):
        self.value['primary_snapshots_dir']=None
        with self.assertRaises(ValueError):self.validate()
    def test_unfrozen_registry_cannot_supply_source(self):
        self.registry.write_text(self.registry.read_text()+' ')
        with self.assertRaises(ValueError):self.validate()
    def annotations(self):
        self.op['op']='migrate_nominal_design_mapping'
        self.value['author_annotations_verified']=10000
        for i in range(9):
            path=self.inputs/('author-'+str(i)+'.txt');path.write_text('original author bytes '+str(i))
            self.files.append({'filename':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
        self.save()
    def test_nine_frozen_actual_author_files_and_complete_census_pass(self):
        self.annotations();self.validate()
    def test_count_without_actual_author_files_cannot_pass(self):
        self.annotations();(self.inputs/self.files[0]['filename']).unlink()
        with self.assertRaises(ValueError):self.validate()
    def test_partial_annotation_census_cannot_pass(self):
        self.annotations();self.value['author_annotations_verified']=9999
        with self.assertRaises(ValueError):self.validate()


if __name__=='__main__':unittest.main()
