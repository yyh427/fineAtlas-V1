"""The replay CLI must never overwrite old candidates or a protected baseline."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import hashlib,json,sqlite3,subprocess,sys

spec=importlib.util.spec_from_file_location('repair_rebuild',Path(__file__).resolve().parents[1]/'scripts/rebuild_unified_repair.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class RebuildProtectionTests(unittest.TestCase):
    def test_existing_candidate_and_baseline_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);baseline=root/'baseline';candidate=root/'candidate';stage=root/'browse'
            baseline.write_bytes(b'protected');candidate.write_bytes(b'previous')
            with self.assertRaises(ValueError):module.validate_paths(baseline,candidate,stage)
            self.assertEqual(baseline.read_bytes(),b'protected');self.assertEqual(candidate.read_bytes(),b'previous')

    def test_shared_candidate_and_staging_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);baseline=root/'baseline';baseline.write_bytes(b'protected')
            with self.assertRaises(ValueError):module.validate_paths(baseline,root/'candidate',root/'candidate')

    def test_distinct_new_paths_are_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);baseline=root/'baseline';baseline.write_bytes(b'protected')
            module.validate_paths(baseline,root/'candidate',root/'browse')

    def test_relative_cli_paths_survive_subprocess_working_directory(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);baseline=root/'baseline.sqlite';inputs=root/'inputs';inputs.mkdir()
            with sqlite3.connect(baseline) as c:
                c.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)')
                c.execute('INSERT INTO metadata VALUES(?,?)',('database_revision',json.dumps('tiny-baseline')))
            original=baseline.read_bytes();sha=hashlib.sha256(original).hexdigest()
            (inputs/'baseline.json').write_text(json.dumps({'database_bytes':len(original),'database_sha256':sha,'database_revision':'tiny-baseline'}))
            (inputs/'review_release.json').write_text(json.dumps({'version':'v1.10.1-repair-review'}))
            result=subprocess.run([sys.executable,str(Path(module.__file__)),
                '--baseline','baseline.sqlite','--inputs','inputs','--database','candidate.sqlite',
                '--reports','reports','--browse-staging','browse.sqlite'],cwd=root,capture_output=True,text=True)
            # This deliberately incomplete fixture must fail at source replay,
            # after copying/validating the candidate at the caller's path.
            self.assertNotEqual(result.returncode,0)
            status=json.loads((root/'reports/rebuild_status.json').read_text())
            self.assertEqual(status['copy_verification']['status'],'PASS')
            self.assertEqual(status['source_and_graphs']['status'],'FAIL')
            self.assertEqual((root/'candidate.sqlite').read_bytes()[:16],b'SQLite format 3\x00')
            self.assertEqual(baseline.read_bytes(),original)

if __name__=='__main__':unittest.main()
