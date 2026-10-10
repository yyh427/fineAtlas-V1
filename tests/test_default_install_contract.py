"""Real tiny SQLite installs reject mixed artifacts, SDKs and stale defaults."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
def module(name):
    spec=importlib.util.spec_from_file_location(name,SCRIPTS/(name+'.py'))
    result=importlib.util.module_from_spec(spec)
    with mock.patch.object(sys,'path',[str(SCRIPTS),*sys.path]):spec.loader.exec_module(result)
    return result
downloader=module('download_single')
verifier=module('verify_unified_install')
quickcheck=module('check_installation')


class DefaultInstallContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.sdk_dir=self.root/'environment/lib/python3.11/site-packages/fineatlas'
        self.sdk_dir.mkdir(parents=True)
        self.sdk_file=self.sdk_dir/'__init__.py';self.sdk_file.write_text('__version__ = "1.10.1"\n')
        self.sdk=SimpleNamespace(__file__=str(self.sdk_file),__version__='1.10.1')
        self.meta={'schema':'FINEATLAS_SINGLE_DB_V1','release':'v1.10.1','database_revision':'b'*64,
                   'default_relation_view':'unified','supported_relation_views':['strict','taxonomy','membership','unified'],
                   'unified_ready':True,'usability_indexes_ready':True,'browse_indexes_ready':True,
                   'browse_index_revision':'b'*64,
                   'unified_frozen_build_manifest':{'code':{'src/fineatlas/__init__.py':hashlib.sha256(self.sdk_file.read_bytes()).hexdigest()}}}
        self.database=self.root/'data/fineatlas.sqlite';self.database.parent.mkdir()
        self.write_db()
        self.manifest={'release':'v1.10.1','candidate':False,'database_revision':'b'*64,'sdk_version':'1.10.1',
                       'default_relation_view':'unified','supported_relation_views':self.meta['supported_relation_views'],
                       'database':{'name':self.database.name,'bytes':self.database.stat().st_size,
                                   'sha256':hashlib.sha256(self.database.read_bytes()).hexdigest()},'assets':[]}

    def write_db(self):
        with sqlite3.connect(self.database) as con:
            con.execute('CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT)')
            con.execute('DELETE FROM metadata')
            con.executemany('INSERT INTO metadata VALUES (?,?)',[(k,json.dumps(v)) for k,v in self.meta.items()])

    def sdk_patch(self):return mock.patch.dict(sys.modules,{'fineatlas':self.sdk})

    def test_default_chooses_formal_unified(self):
        path=self.root/'unified_data.json';path.write_text(json.dumps(self.manifest))
        (self.root/'single_download.json').write_text(json.dumps({'release':'v1.6.0'}))
        self.assertEqual(downloader.default_manifest(self.root),path)

    def test_default_never_silently_chooses_legacy_or_candidate(self):
        legacy=self.root/'single_download.json';legacy.write_text(json.dumps({'release':'v1.6.0'}))
        with self.assertRaises(RuntimeError):downloader.default_manifest(self.root)
        candidate=copy.deepcopy(self.manifest);candidate['candidate']=True
        (self.root/'unified_data.json').write_text(json.dumps(candidate))
        with self.assertRaises(RuntimeError):downloader.default_manifest(self.root)

    def test_absent_default_or_missing_exact_revision_rejected(self):
        with self.assertRaises(FileNotFoundError):downloader.default_manifest(self.root)
        broken=copy.deepcopy(self.manifest);broken.pop('database_revision')
        with self.assertRaises(RuntimeError):downloader.validate_manifest(broken)

    def test_reusing_hash_verified_database_writes_actual_receipt(self):
        with self.sdk_patch():
            self.assertEqual(downloader.install(self.database.parent,self.manifest),self.database)
        self.assertEqual(json.loads((self.database.parent/'single_database.json').read_text()),self.manifest)

    def test_foreign_receipt_rejected_before_download_or_reuse(self):
        (self.database.parent/'single_database.json').write_text(json.dumps({'release':'v1.6.0'}))
        with self.sdk_patch(),self.assertRaises(RuntimeError):downloader.install(self.database.parent,self.manifest)

    def test_exact_sha_refuses_existing_different_bytes(self):
        manifest=copy.deepcopy(self.manifest);manifest['database']['sha256']='a'*64
        with self.sdk_patch(),self.assertRaises(RuntimeError):downloader.install(self.database.parent,manifest)

    def test_release_revision_view_and_index_mismatch_rejected(self):
        for field,value in [('release','v1.10.1-repair-review'),('database_revision','c'*64),
                            ('default_relation_view','strict'),('browse_index_revision','c'*64),
                            ('browse_indexes_ready',False),('schema','unknown')]:
            old=copy.deepcopy(self.meta);self.meta[field]=value;self.write_db()
            with self.subTest(field=field),self.sdk_patch(),self.assertRaises(RuntimeError):
                downloader.verify_revision(self.database,self.manifest)
            self.meta=old;self.write_db()

    def test_installed_wrong_sdk_version_or_frozen_file_rejected(self):
        self.sdk.__version__='1.10.1rc1'
        with self.sdk_patch(),self.assertRaises(RuntimeError):downloader.runtime_sdk(self.manifest)
        self.sdk.__version__='1.10.1';self.sdk_file.write_text('different SDK bytes\n')
        with self.sdk_patch(),self.assertRaises(RuntimeError):downloader.verify_revision(self.database,self.manifest)

    def test_structure_freeze_uses_new_sdk_inventory_and_never_old_fallback(self):
        self.meta['structure_frozen_build_manifest']={'code':{
            'src/fineatlas/__init__.py':hashlib.sha256(self.sdk_file.read_bytes()).hexdigest(),
            'scripts/build_structure_candidate.py':'build-hash',
            'configs/types.json':'configuration-hash'}}
        self.meta['unified_frozen_build_manifest']['code']['src/fineatlas/__init__.py']='superseded-baseline-hash'
        verifier.validate_runtime_install(self.meta,self.manifest,self.sdk)
        extra=self.sdk_dir/'unexpected.py';extra.write_text('unfrozen code')
        with self.assertRaisesRegex(AssertionError,'inventory differs'):
            verifier.validate_runtime_install(self.meta,self.manifest,self.sdk)
        extra.unlink()
        self.meta['structure_frozen_build_manifest']['code']={}
        with self.assertRaises(AssertionError):
            verifier.validate_runtime_install(self.meta,self.manifest,self.sdk)

    def test_runtime_install_binds_actual_frozen_sdk(self):
        result=verifier.validate_runtime_install(self.meta,self.manifest,self.sdk)
        self.assertEqual(result['sdk_version'],'1.10.1')
        for field,value in [('release','v1.6.0'),('browse_index_revision','c'*64),('supported_relation_views',['strict'])]:
            bad=copy.deepcopy(self.meta);bad[field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):verifier.validate_runtime_install(bad,self.manifest,self.sdk)

    def test_installed_site_packages_required(self):
        verifier.validate_installed_sdk(self.sdk,self.root/'environment')
        source_sdk=SimpleNamespace(__file__=str(self.root/'code/src/fineatlas/__init__.py'))
        with self.assertRaises(AssertionError):verifier.validate_installed_sdk(source_sdk,self.root/'environment')

    def test_receipt_size_and_live_sqlite_sidecar_rejected(self):
        with self.assertRaises(AssertionError):verifier.validate_install_receipt(self.database,self.manifest)
        (self.database.parent/'single_database.json').write_text(json.dumps(self.manifest))
        verifier.validate_install_receipt(self.database,self.manifest)
        Path(str(self.database)+'-wal').write_bytes(b'live')
        with self.assertRaises(AssertionError):verifier.validate_install_receipt(self.database,self.manifest)

    def test_explicit_historical_download_retains_official_sha_contract(self):
        historical={'release':'v1.6.0','database':self.manifest['database'],'assets':[]}
        self.assertEqual(downloader.install(self.database.parent,historical),self.database)
        self.assertEqual(json.loads((self.database.parent/'single_database.json').read_text()),historical)

    def laser_parent(self):
        uid='hierarchy-type:semiconductor_diodes-led'
        return {'uid':uid,'label':'light-emitting semiconductor diode','node_kind':'CLASS',
                'edge':{'relation':'IS_A','status':'ACTIVE','navigation_role':'SOURCE_VALIDATED',
                        'child_uid':'wikidata:Q321098','parent_uid':uid}}

    def test_actual_unified_professional_parent_accepts_its_uid_and_legal_edge(self):
        parent=self.laser_parent()
        self.assertEqual(quickcheck.validate_laser_parent([parent],True),parent['uid'])
        parent['label']='display synonym'
        self.assertEqual(quickcheck.validate_laser_parent([parent],True),parent['uid'])

    def test_old_label_or_inactive_wrong_role_or_wrong_endpoint_is_not_source_admission(self):
        with self.assertRaises(AssertionError):quickcheck.validate_laser_parent([{'label':'semiconductor diode'}],True)
        for key,value in [('relation','DESIGN_TYPE'),('status','REVIEW'),('navigation_role','REVIEW'),
                          ('child_uid','native:other'),('parent_uid','wordnet31:03207444-n')]:
            parent=self.laser_parent();parent['edge'][key]=value
            with self.subTest(key=key),self.assertRaises(AssertionError):quickcheck.validate_laser_parent([parent],True)
        parent=self.laser_parent();parent['node_kind']='MODEL'
        with self.assertRaises(AssertionError):quickcheck.validate_laser_parent([parent],True)


if __name__=='__main__':unittest.main()
