import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

PATH=Path(__file__).resolve().parents[1]/'scripts/promote_stable_candidate.py'
spec=importlib.util.spec_from_file_location('promote_stable_candidate',PATH)
promote=importlib.util.module_from_spec(spec);spec.loader.exec_module(promote)

class StablePromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.old,self.new,self.old_inputs,self.inputs=[self.root/n for n in ('old-code','new-code','old-inputs','new-inputs')]
        for d in (self.old,self.new):
            (d/'src/fineatlas').mkdir(parents=True);(d/'scripts').mkdir()
            (d/'src/fineatlas/__init__.py').write_text("__version__ = '1.10.1rc1'\n")
            (d/'src/fineatlas/semantics.py').write_text('def relation(x): return x\n')
            (d/'scripts/finalize_unified_metadata.py').write_text('ORIGINAL_RECIPE = True\n')
            (d/'scripts/promote_stable_candidate.py').write_text('PROMOTION_RECIPE = True\n')
            (d/'pyproject.toml').write_text('[project]\nversion="1.10.1"\n')
        (self.new/'src/fineatlas/__init__.py').write_text("__version__ = '1.10.1'\n")
        for d,v in ((self.old_inputs,'v1.10.1-repair-review'),(self.inputs,'v1.10.1')):
            d.mkdir();(d/'review_release.json').write_text(json.dumps({'version':v,'purpose':'same scope'}))
            (d/'source.json').write_text('{"uid":"unchanged"}')
        policy={'identity_cost':0,'rule':'all valid parents'}
        freeze={'inputs':promote.files_digest(self.old_inputs),
                'code':{str(p.relative_to(self.old)):promote.digest_file(p) for p in sorted((self.old/'src/fineatlas').glob('*.py'))},
                'build_scripts':{'scripts/finalize_unified_metadata.py':promote.digest_file(self.old/'scripts/finalize_unified_metadata.py')},
                'source_graph_revision':'original-graph-sha', 'policy_sha256':promote.canonical_hash(policy)}
        parent=promote.canonical_hash(freeze)
        self.meta={'unified_ready':True,'usability_indexes_ready':True,'browse_indexes_ready':True,
                   'database_revision':'original-final-revision','browse_index_revision':'original-final-revision',
                   'browse_parent_revision':parent,'browse_source_revision':parent,'release':'v1.10.1-repair-review',
                   'unified_frozen_build_manifest':freeze,'unified_source_graph_revision':'original-graph-sha',
                   'unified_policy_sha256':freeze['policy_sha256'],'unified_policy_definition':policy}
    def reuse(self):return promote.validate_reuse(self.meta,self.old,self.old_inputs,self.new,self.inputs)
    def test_version_only_reuses_graph_but_freezes_new_recipe_and_rebuilds_browse(self):
        result=self.reuse();self.assertEqual(result,self.reuse())
        self.assertEqual(result['manifest']['source_graph_revision'],'original-graph-sha')
        self.assertNotEqual(result['revision'],self.meta['browse_parent_revision'])
        self.assertIn('scripts/promote_stable_candidate.py',result['manifest']['build_scripts'])
        self.assertTrue(result['manifest']['promotion']['browse_indexes_rebuilt'])
        self.assertFalse(result['manifest']['promotion']['semantic_graph_recomputed'])
    def test_changed_semantic_sdk_rejected(self):
        (self.new/'src/fineatlas/semantics.py').write_text('def relation(x): return None\n')
        with self.assertRaisesRegex(ValueError,'Semantic SDK'):self.reuse()
    def test_init_code_hidden_alongside_version_rejected(self):
        with (self.new/'src/fineatlas/__init__.py').open('a') as f:f.write('DEFAULT_RELATION = "taxonomy"\n')
        with self.assertRaisesRegex(ValueError,'beyond version'):self.reuse()
    def test_new_sdk_module_rejected(self):
        (self.new/'src/fineatlas/extra.py').write_text('X = 1\n')
        with self.assertRaisesRegex(ValueError,'SDK inventory'):self.reuse()
    def test_version_mismatch_rejected(self):
        (self.new/'src/fineatlas/__init__.py').write_text("__version__ = '1.10.2'\n")
        with self.assertRaisesRegex(ValueError,'exactly match'):self.reuse()
    def test_changed_source_input_rejected(self):
        (self.inputs/'source.json').write_text('{"uid":"different"}')
        with self.assertRaisesRegex(ValueError,'Only review_release'):self.reuse()
    def test_changed_release_scope_rejected(self):
        (self.inputs/'review_release.json').write_text(json.dumps({'version':'v1.10.1','purpose':'new scope'}))
        with self.assertRaisesRegex(ValueError,'Only review_release.version'):self.reuse()
    def test_mutated_old_input_rejected(self):
        (self.old_inputs/'source.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Frozen input'):self.reuse()
    def test_original_build_recipe_change_rejected(self):
        (self.new/'scripts/finalize_unified_metadata.py').write_text('DIFFERENT_RECIPE=True\n')
        with self.assertRaisesRegex(ValueError,'Original build recipe'):self.reuse()
    def test_stale_browse_parent_rejected(self):
        self.meta['browse_source_revision']='another-source'
        with self.assertRaisesRegex(ValueError,'browse parent'):self.reuse()
    def test_policy_payload_drift_rejected(self):
        self.meta['unified_policy_definition']['identity_cost']=1
        with self.assertRaisesRegex(ValueError,'policy fingerprint'):self.reuse()
    def test_metadata_freeze_leaves_semantic_records_and_schema_exact(self):
        db=self.root/'candidate.sqlite'
        with sqlite3.connect(db) as c:
            c.executescript('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);CREATE TABLE source(uid TEXT PRIMARY KEY,payload TEXT);CREATE TABLE semantic_links(child TEXT,parent TEXT);CREATE INDEX semantic_parent ON semantic_links(parent);')
            c.executemany('INSERT INTO metadata VALUES(?,?)',[(k,json.dumps(v)) for k,v in self.meta.items()])
            c.execute('INSERT INTO source VALUES(?,?)',('raw:one','{"data": "exact original"}'))
            c.execute('INSERT INTO semantic_links VALUES(?,?)',('raw:one','root:one'))
            records=c.execute('SELECT * FROM source').fetchall()+c.execute('SELECT * FROM semantic_links').fetchall()
            schema=c.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        result=self.reuse();promote.freeze_promoted_metadata(db,result)
        with sqlite3.connect(db) as c:
            self.assertEqual(records,c.execute('SELECT * FROM source').fetchall()+c.execute('SELECT * FROM semantic_links').fetchall())
            self.assertEqual(schema,c.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall())
        m=promote.read_metadata(db)
        self.assertFalse(m['browse_indexes_ready']);self.assertEqual(m['database_revision'],result['revision'])
        self.assertEqual(m['review_version'],'v1.10.1');self.assertEqual(m['unified_source_graph_revision'],'original-graph-sha')
        self.assertEqual(m['browse_index_revision'],'original-final-revision')
    def evidence(self):
        rows={name:{'database':str(self.root/name),'database_revision':self.meta['database_revision'],'sha256':name+'-sha','pass':True,'integrity_check':['ok'],'file_unchanged_during_checks':True} for name in ('primary','reproduction')}
        integrity={'complete':True,'all_pass':True,'artifacts':rows}
        comparison={'complete':True,'pass':True,'artifact_hashes_bound':True,'final_view_statistics_pass':True,'exit_code':0,'logical_table_count':105,**{n:{'database_sha256':r['sha256'],'database_revision':r['database_revision']} for n,r in rows.items()}}
        acceptance={'all_pass':True,'ended_utc':'done','candidate_unchanged':True,'inputs_unchanged':True,'database_sha256':'primary-sha','database_revision':self.meta['database_revision'],'jobs':{str(i):{'exit_code':0,'verdict':{'pass':True},'ended_utc':'done'} for i in ['domains','labels','structure','preservation','nonfocus','browse','contracts','cycles','witnesses','cli','same-policy','global-contracts','usability','living-focused','repair-focus','self-reward']}}
        return integrity,comparison,acceptance
    def test_reproduction_proof_transfers_only_through_complete_exact_comparison(self):
        args=self.evidence();selected=promote.validate_evidence(self.meta,self.root/'reproduction',*args)
        self.assertEqual(selected['sha256'],'reproduction-sha')
        args[1]['complete']=False
        with self.assertRaisesRegex(ValueError,'comparison'):promote.validate_evidence(self.meta,self.root/'reproduction',*args)
    def test_wrong_acceptance_sha_rejected(self):
        args=self.evidence();args[2]['database_sha256']='unrelated'
        with self.assertRaisesRegex(ValueError,'not bound'):promote.validate_evidence(self.meta,self.root/'primary',*args)
    def test_integrity_comparison_hash_disagreement_rejected(self):
        args=self.evidence();args[1]['reproduction']['database_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'bindings differ'):promote.validate_evidence(self.meta,self.root/'primary',*args)
    def test_partial_acceptance_not_reused(self):
        args=self.evidence();args[2]['jobs']['structure']['ended_utc']=None
        with self.assertRaisesRegex(ValueError,'jobs not complete'):promote.validate_evidence(self.meta,self.root/'primary',*args)
    def test_existing_destination_never_overwritten(self):
        dest=self.root/'existing';dest.write_text('KEEP')
        with self.assertRaisesRegex(ValueError,'overwrite'):promote.validate_paths(self.root/'primary',dest,self.root/'staging')
        self.assertEqual(dest.read_text(),'KEEP')

if __name__=='__main__':unittest.main()
