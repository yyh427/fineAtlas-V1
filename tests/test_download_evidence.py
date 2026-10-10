"""Actual tiny HTTP/cache/installer proof checks; no external release downloads."""
from __future__ import annotations
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import _download as downloader
spec=importlib.util.spec_from_file_location('independent_download_single',ROOT/'scripts/download_single.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


class DownloadEvidenceTests(unittest.TestCase):
    def setUp(self):
        base=ROOT.parent/'tmp';base.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='download-evidence-test-',dir=base)
        self.work=Path(self.temp.name)
        self.payload=b'actual tiny HTTP source bytes\n'*53
        self.requests=[]
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.requests.append({'path':self.path,'range':self.headers.get('Range'),
                                       'authorization':self.headers.get('Authorization')})
                body=owner.payload;start=0
                if self.headers.get('Range'):
                    start=int(self.headers['Range'].removeprefix('bytes=').removesuffix('-'))
                    self.send_response(206)
                    self.send_header('Content-Range',f'bytes {start}-{len(body)-1}/{len(body)}')
                else:self.send_response(200)
                self.send_header('Content-Length',str(len(body)-start));self.end_headers()
                self.wfile.write(body[start:])
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/tiny.part'
        self.proxy=patch.dict(os.environ,{'NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost'})
        self.proxy.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
        self.proxy.stop();self.temp.cleanup()

    def expected(self):
        return {'sha256':hashlib.sha256(self.payload).hexdigest(),'bytes':len(self.payload)}

    def quiet_download(self,url,path,expected):
        with contextlib.redirect_stdout(io.StringIO()):return downloader.download(url,path,expected)

    def test_verified_asset_cache_never_sends_request_and_is_not_fresh(self):
        path=self.work/'cache.part';path.write_bytes(self.payload)
        with patch.object(downloader,'urlopen',side_effect=AssertionError('Cache must not send a request')):
            proof=self.quiet_download(self.url,path,self.expected())
        self.assertFalse(proof['network_request']);self.assertFalse(proof['fresh_download'])
        self.assertEqual(proof['disposition'],'VERIFIED_LOCAL_CACHE')
        self.assertEqual(proof['initial_cached_bytes'],len(self.payload));self.assertEqual(self.requests,[])

    def test_recovered_complete_download_cache_is_not_network(self):
        path=self.work/'recovered.part';path.with_name(path.name+'.download').write_bytes(self.payload)
        with patch.object(downloader,'urlopen',side_effect=AssertionError('Recovery must not request')):
            proof=self.quiet_download(self.url,path,self.expected())
        self.assertEqual(path.read_bytes(),self.payload)
        self.assertFalse(proof['fresh_download']);self.assertFalse(proof['network_request'])
        self.assertEqual(proof['disposition'],'RECOVERED_LOCAL_CACHE')

    def test_actual_fresh_http_download_has_status_hash_and_zero_cache(self):
        path=self.work/'fresh.part';proof=self.quiet_download(self.url,path,self.expected())
        self.assertEqual(path.read_bytes(),self.payload)
        self.assertTrue(proof['fresh_download']);self.assertTrue(proof['network_request'])
        self.assertEqual(proof['http_status'],200);self.assertEqual(proof['initial_cached_bytes'],0)
        self.assertEqual(proof['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(proof['bytes'],path.stat().st_size);self.assertEqual(proof['url'],self.url)
        self.assertFalse(proof['authenticated']);self.assertEqual(len(self.requests),1)
        self.assertIsNone(self.requests[0]['authorization'])

    def test_partial_real_http_resume_is_network_but_not_fresh(self):
        path=self.work/'resumed.part';path.with_name(path.name+'.download').write_bytes(self.payload[:111])
        proof=self.quiet_download(self.url,path,self.expected())
        self.assertTrue(proof['network_request']);self.assertFalse(proof['fresh_download'])
        self.assertEqual(proof['http_status'],206);self.assertEqual(proof['initial_cached_bytes'],111)
        self.assertEqual(self.requests[0]['range'],'bytes=111-');self.assertEqual(path.read_bytes(),self.payload)

    def test_file_uri_is_rejected_or_explicitly_not_public_network(self):
        source=self.work/'offline-source.part';source.write_bytes(self.payload);path=self.work/'offline-copy.part'
        try:proof=self.quiet_download(source.as_uri(),path,self.expected())
        except (ValueError,RuntimeError) as error:
            self.assertRegex(str(error).lower(),'http|network|scheme|public|local')
        else:
            self.assertFalse(proof['network_request'],'A file:// read is not an HTTP network request')
            self.assertFalse(proof['fresh_download'],'A local copy cannot be fresh public verification')
            self.assertNotEqual(proof['disposition'],'PUBLIC_NETWORK_DOWNLOAD')
        self.assertEqual(self.requests,[])

    def install_fixture(self):
        if not shutil.which('zstd'):self.skipTest('Real installer fixture requires repository release zstd tool')
        source=self.work/'tiny-source.sqlite'
        with sqlite3.connect(source) as c:
            c.execute('CREATE TABLE records(uid TEXT PRIMARY KEY,scope TEXT)')
            c.execute('INSERT INTO records VALUES(?,?)',('source:1','preserved raw source'))
        self.payload=subprocess.run(['zstd','-q','-c',str(source)],stdout=subprocess.PIPE,check=True).stdout
        metadata={'release':'explicit-legacy-fixture','base_url':self.url.rsplit('/',1)[0],
                  'database':{'name':'fineatlas.sqlite','bytes':source.stat().st_size,
                              'sha256':hashlib.sha256(source.read_bytes()).hexdigest()},
                  'assets':[{'name':'tiny.part',**self.expected()}]}
        return source,metadata

    def test_installer_cached_parts_cannot_claim_fresh_download(self):
        source,metadata=self.install_fixture();output=self.work/'cached-install'
        downloads=output/'downloads';downloads.mkdir(parents=True);(downloads/'tiny.part').write_bytes(self.payload)
        with patch.object(downloader,'urlopen',side_effect=AssertionError('Installer cached parts must never request')):
            with contextlib.redirect_stdout(io.StringIO()):database=installer.install(output,metadata)
        proof=json.loads((output/'public_download_proof.json').read_text())
        self.assertFalse(proof['fresh_download']);self.assertFalse(proof['asset_proofs'][0]['network_request'])
        self.assertEqual(database.read_bytes(),source.read_bytes());self.assertEqual(self.requests,[])

    def test_installer_actual_network_records_per_asset_proofs(self):
        source,metadata=self.install_fixture();output=self.work/'http-install'
        with contextlib.redirect_stdout(io.StringIO()):database=installer.install(output,metadata)
        proof=json.loads((output/'public_download_proof.json').read_text())
        self.assertTrue(proof['fresh_download']);self.assertEqual(len(proof['asset_proofs']),1)
        asset=proof['asset_proofs'][0]
        self.assertTrue(asset['network_request']);self.assertEqual(asset['http_status'],200)
        self.assertEqual(proof['public_download_urls'],[asset['url']])
        self.assertEqual(asset['initial_cached_bytes'],0);self.assertEqual(asset['sha256'],self.expected()['sha256'])
        self.assertEqual(database.read_bytes(),source.read_bytes());self.assertEqual(len(self.requests),1)

    def test_unknown_mock_download_return_never_certifies_network(self):
        source,metadata=self.install_fixture();output=self.work/'unknown-install'
        def offline_copy(url,path,expected):path.write_bytes(self.payload)
        with patch.object(installer,'download',side_effect=offline_copy):
            with contextlib.redirect_stdout(io.StringIO()):database=installer.install(output,metadata)
        proof=json.loads((output/'public_download_proof.json').read_text())
        self.assertFalse(proof['fresh_download']);self.assertFalse(proof['asset_proofs'][0]['network_request'])
        self.assertEqual(proof['asset_proofs'][0]['disposition'],'UNKNOWN')
        self.assertEqual(database.read_bytes(),source.read_bytes());self.assertEqual(self.requests,[])


if __name__=='__main__':unittest.main()
