import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import types
import sys
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/extend_structure_checkpoint.py'
spec = importlib.util.spec_from_file_location('structure_checkpoint_recipe', SCRIPT)
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)


class CheckpointSafetyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root/'source.sqlite'
        with sqlite3.connect(self.database) as c:
            c.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)')
            c.executemany('INSERT INTO metadata VALUES (?,?)', [(key,json.dumps(value)) for key,value in {
                'release':'v1.11.0rc1','database_revision':'protected-revision',
                'unified_ready':False,'usability_indexes_ready':False}.items()])
        self.inputs = self.root/'inputs'; self.inputs.mkdir()
        self.production = self.root/'production.sqlite'
        shutil.copyfile(self.database, self.production)
        (self.inputs/'baseline.json').write_text(json.dumps({'database_revision':'protected-revision'}))
        (self.inputs/'structure_source_contracts.json').write_text('{}')
        (self.inputs/'structure_protected_paths.json').write_text(json.dumps({
            'schema':'FINEATLAS_PROTECTED_PATHS_V1','files':[
                {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'role':role}
                for path,role in ((self.production,'PRODUCTION'),(self.database,'SOURCE_CHECKPOINT'))]}))
        self.status = self.root/'status.json'
        self.status.write_text(json.dumps({name:{'status':'PASS'} for name in recipe.SOURCE_STAGES}))
        self.receipt = self.root/'receipt.json'

    def tearDown(self):
        self.temp.cleanup()

    def test_capture_refuses_pending_journal_or_incomplete_sources(self):
        journal = Path(str(self.database)+'-journal'); journal.touch()
        with self.assertRaisesRegex(ValueError,'sidecars'):
            recipe.capture(self.database,self.inputs,self.status,self.receipt)
        journal.unlink()
        self.status.write_text('{}')
        with self.assertRaisesRegex(ValueError,'source replay'):
            recipe.capture(self.database,self.inputs,self.status,self.receipt)

    def test_extension_refuses_same_inode(self):
        recipe.capture(self.database,self.inputs,self.status,self.receipt)
        args = types.SimpleNamespace(receipt=self.receipt,database=self.database,baseline=self.production,
                                     inputs=self.inputs,reports=self.root/'reports')
        with self.assertRaisesRegex(ValueError,'SOURCE_CHECKPOINT'):
            recipe.build(args)

    def test_changed_prior_input_rejected_before_any_mutation(self):
        recipe.capture(self.database,self.inputs,self.status,self.receipt)
        copy = self.root/'copy.sqlite'; shutil.copyfile(self.database,copy)
        (self.inputs/'baseline.json').write_text('{"database_revision":"tampered"}')
        args = types.SimpleNamespace(receipt=self.receipt,database=copy,baseline=self.production,
                                     inputs=self.inputs,reports=self.root/'reports')
        with patch.object(recipe,'Migration') as migration:
            with self.assertRaisesRegex(ValueError,'Previously replayed input changed'):
                recipe.build(args)
            migration.assert_not_called()
        states=json.loads((args.reports/'build_status.json').read_text())
        self.assertEqual(states['verify_source_checkpoint_copy']['status'],'FAIL')

    def candidate_args(self):
        recipe.capture(self.database,self.inputs,self.status,self.receipt)
        copy = self.root/'copy.sqlite'; shutil.copyfile(self.database,copy)
        return types.SimpleNamespace(receipt=self.receipt,database=copy,baseline=self.production,
                                     inputs=self.inputs,reports=self.root/'reports')

    def test_deceptive_baseline_fails_before_migration(self):
        args = self.candidate_args()
        fake = self.root/'deceptive-baseline.sqlite'; shutil.copyfile(self.production,fake)
        args.baseline = fake
        with patch.object(recipe,'Migration') as migration:
            with self.assertRaisesRegex(ValueError,'registered production inode'):
                recipe.build(args)
            migration.assert_not_called()

    def test_code_change_during_verification_fails_before_migration(self):
        args = self.candidate_args()
        builder = sys.modules['build_structure_candidate']
        old_inventory = builder.PREIMPORT_CODE_INVENTORY
        changed = {'value':False}
        original_digest = recipe.digest_file
        def digest(path):
            value = original_digest(path)
            if path == args.database:
                changed['value'] = True
            return value
        def inventory(root):
            if changed['value']:
                return {'code':{'simulated-sdk.py':'0'*64},'packaging':old_inventory['packaging']}
            return old_inventory
        with patch.object(builder,'inventory_code',side_effect=inventory), patch.object(recipe,'digest_file',side_effect=digest), patch.object(recipe,'Migration') as migration:
            with self.assertRaisesRegex(ValueError,'before SDK import'):
                recipe.build(args)
            migration.assert_not_called()
        self.assertEqual(json.loads((args.reports/'build_status.json').read_text())['verify_source_checkpoint_copy']['status'],'FAIL')

    def test_new_input_during_verification_fails_before_migration(self):
        args = self.candidate_args()
        original_digest = recipe.digest_file
        def digest(path):
            value = original_digest(path)
            if path == args.database:
                (self.inputs/'unexpected-new-input.json').write_text('{}')
            return value
        with patch.object(recipe,'digest_file',side_effect=digest), patch.object(recipe,'Migration') as migration:
            with self.assertRaisesRegex(ValueError,'frozen inputs changed'):
                recipe.build(args)
            migration.assert_not_called()

    def test_complete_receipt_requires_all_pass_and_binds_actual_files(self):
        builder = sys.modules['build_structure_candidate']
        with sqlite3.connect(self.database) as c:
            c.execute("UPDATE metadata SET value=? WHERE key='database_revision'",(json.dumps('final-revision'),))
            c.execute("UPDATE metadata SET value='true' WHERE key IN ('unified_ready','usability_indexes_ready')")
            c.executemany('INSERT INTO metadata VALUES (?,?)',[(key,json.dumps(value)) for key,value in {
                'browse_indexes_ready':True,'browse_parent_revision':'source-graph-revision',
                'browse_source_revision':'source-graph-revision','browse_index_revision':'final-revision'}.items()])
        reports = self.root/'receipt-reports'
        fingerprints, context = builder.start_build(self.inputs,reports)
        states = {name:{'status':'PASS'} for name in recipe.BUILD_STAGES}
        states['whole_graph_recomputation']['status'] = 'FAIL'
        (reports/'build_status.json').write_text(json.dumps(states))
        with self.assertRaisesRegex(ValueError,'Every required build stage'):
            builder.write_build_complete(reports,self.database,'v1.11.0rc1','final-revision',context,states,recipe.BUILD_STAGES,'source-graph-revision')
        self.assertFalse((reports/'build_complete.json').exists())
        states['whole_graph_recomputation']['status'] = 'PASS'
        (reports/'build_status.json').write_text(json.dumps(states))
        with self.assertRaisesRegex(ValueError,'actual database release and revision'):
            builder.write_build_complete(reports,self.database,'v1.11.0rc1','source-graph-revision',context,states,recipe.BUILD_STAGES,'source-graph-revision')
        self.assertFalse((reports/'build_complete.json').exists())
        receipt = builder.write_build_complete(reports,self.database,'v1.11.0rc1','final-revision',context,states,recipe.BUILD_STAGES,'source-graph-revision')
        self.assertEqual(receipt['revision'],'final-revision')
        self.assertEqual(receipt['source_graph_revision'],'source-graph-revision')
        self.assertEqual(receipt['cache_bindings']['browse_index_revision'],'final-revision')
        self.assertEqual(receipt['schema'],'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1')
        self.assertIs(receipt['pass'],True)
        self.assertIs(receipt['complete'],True)
        self.assertEqual(receipt['build_status_sha256'],hashlib.sha256((reports/'build_status.json').read_bytes()).hexdigest())
        self.assertEqual(receipt['started_fingerprints_sha256'],hashlib.sha256((reports/'started_fingerprints.json').read_bytes()).hexdigest())
        self.assertEqual(json.loads((reports/'started_fingerprints.json').read_text()),fingerprints)
        other = self.root/'second-receipt-reports'
        _, other_context = builder.start_build(self.inputs,other)
        self.assertNotEqual(context['build_id'],other_context['build_id'])
        with self.assertRaisesRegex(ValueError,'fresh report directory'):
            builder.start_build(self.inputs,reports)
        with sqlite3.connect(self.database) as c:
            self.assertFalse(c.execute("SELECT 1 FROM metadata WHERE key IN ('build_id','pid','started_utc')").fetchone())

    def test_capture_cannot_overwrite_protected_database_or_status(self):
        for destination in (self.production,self.database,self.status):
            original = destination.read_bytes()
            with self.assertRaises(ValueError):
                recipe.capture(self.database,self.inputs,self.status,destination)
            self.assertEqual(destination.read_bytes(),original)


if __name__ == '__main__':
    unittest.main()
