"""Micro fixtures for semantic acceptance; no production database is opened."""
import importlib.util
import json
from itertools import combinations
import sys
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'run_unified_repair_acceptance.py'
spec = importlib.util.spec_from_file_location('repair_acceptance', SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.revision = 'frozen-revision'
        self.expected = {'domains':1, 'samples':1, 'browse_parent_revision':'source-revision'}

    def dump(self, name, value):
        runner.write(self.root / name, value)

    def pair(self, **changes):
        value = {'dataset':'cub200','left':'1','right':'2','database_revision':self.revision,
                 'relation_view':'unified','status':'ENDPOINT_NOT_APPLICABLE','applicable':False,
                 'distance':None,'reasons':{'1':'ANNOTATION_SCOPE_REVIEW'},'identity_step_cost':0,'lcas':[]}
        value.update(changes)
        return value

    def test_review_pair_is_retained_and_masked(self):
        self.assertEqual(runner.validate_pair(self.pair(),self.revision,'unified','cub200',{'1','2'}),('1','2'))

    def test_exit_zero_cannot_supply_missing_result(self):
        with self.assertRaises(FileNotFoundError):
            runner.semantic_gate('preservation', self.root, self.revision, self.expected)

    def test_review_and_revision_contract_negative_cases(self):
        for changed in ({'distance':0},{'applicable':True},{'reasons':{}},
                        {'database_revision':'other'}, {'status':'INTERFACE_SCHEMA_NOT_SUPPORTED'},
                        {'identity_step_cost':1}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                runner.validate_pair(self.pair(**changed),self.revision,'unified','cub200',{'1','2'})

    def test_applicable_requires_lca_and_numeric_distance(self):
        good = self.pair(status='APPLICABLE',applicable=True,distance=0,lcas=[{'uid':'native:type'}])
        runner.validate_pair(good,self.revision,'unified','cub200',{'1','2'})
        for changed in ({'lcas':[]},{'distance':None},{'distance':True},{'distance':-1}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                runner.validate_pair({**good,**changed},self.revision,'unified','cub200',{'1','2'})

    def test_legacy_unrooted_and_review_roles_are_not_structural_failure(self):
        result = {t+'_dangling_'+scope+'_records':0 for t in ('edges','entity_relations')
                  for scope in ('retained','admitted')}
        result.update(raw_source_unrooted_records_excluded_to_inflate_pass_rate=False,
                      identity_role_conflicts=[{'roles':2}],unrooted_classification_records=[{'records':999}],
                      universal_all_active_source_navigation_complete=False)
        self.dump('summary.json',{'structure':result})
        self.assertTrue(runner.semantic_gate('structure',self.root,self.revision,self.expected)['pass'])
        result['edges_dangling_retained_records'] = 1
        self.dump('summary.json',{'structure':result})
        with self.assertRaises(ValueError):
            runner.semantic_gate('structure',self.root,self.revision,self.expected)

    def test_nonfocus_requires_preservation_and_original_root_no_regression(self):
        row = {'uid':'native:1','preserved':True,'original_status':'DISCONNECTED','unified_status':'DISCONNECTED'}
        self.dump('nonfocus.json',[row])
        self.dump('summary.json',{'nonfocus':{'count':1,'preserved':1,'regressions':0}})
        self.assertTrue(runner.semantic_gate('nonfocus',self.root,self.revision,self.expected)['pass'])
        row['original_status'] = 'CONNECTED'
        self.dump('nonfocus.json',[row])
        with self.assertRaises(ValueError):
            runner.semantic_gate('nonfocus',self.root,self.revision,self.expected)

    def test_missing_cycle_view_cannot_pass(self):
        row = {'acyclic':True,'default_preferred_graph_acyclic':True,'cyclic_or_cycle_dependent_vertices':0,
               'processed_vertices':2,'incident_identity_vertices':2,'unique_arcs':1}
        self.dump('result.json',{view:row for view in runner.VIEWS})
        self.assertTrue(runner.semantic_gate('cycles',self.root,self.revision,self.expected)['pass'])
        self.dump('result.json',{'unified':row})
        with self.assertRaises(ValueError):
            runner.semantic_gate('cycles',self.root,self.revision,self.expected)

    def test_preservation_summary_cannot_pass_with_false_verdict(self):
        self.dump('summary.json',{'preservation':{'pass':False}})
        with self.assertRaises(ValueError):
            runner.semantic_gate('preservation',self.root,self.revision,self.expected)

    def test_index_contract_summary_checks_must_be_zero(self):
        row = {'all_pass':True,'all_indexed_relations':1,'checks':{'missing_source_arcs':1},
               'new_semantic_relations':0,'new_semantic_nodes':0}
        self.dump('result.json',row)
        with self.assertRaises(ValueError):
            runner.semantic_gate('contracts',self.root,self.revision,self.expected)
        row['checks']['missing_source_arcs'] = 0
        self.dump('result.json',row)
        self.assertTrue(runner.semantic_gate('contracts',self.root,self.revision,self.expected)['pass'])

    def test_snapshot_tracks_revision_stat_and_nonempty_wal(self):
        database = self.root / 'fixture.sqlite'
        with sqlite3.connect(database) as con:
            con.execute('CREATE TABLE metadata(key TEXT,value TEXT)')
            con.execute('INSERT INTO metadata VALUES(?,?)',('database_revision',json.dumps(self.revision)))
        before = runner.snapshot(database)
        self.assertEqual(before['metadata']['database_revision'],self.revision)
        with sqlite3.connect(database) as con:
            con.execute('UPDATE metadata SET value=?',(json.dumps('changed'),))
        self.assertNotEqual(runner.snapshot(database),before)
        Path(str(database)+'-wal').write_bytes(b'not-frozen')
        with self.assertRaises(ValueError):
            runner.snapshot(database)

    def test_readiness_pins_build_default_and_browse_revision(self):
        metadata = {'release':'v1.10.1-repair-review','database_revision':self.revision,
                    'unified_ready':True,'usability_indexes_ready':True,'browse_indexes_ready':True,
                    'default_relation_view':'unified','supported_relation_views':list(runner.VIEWS),
                    'browse_index_revision':self.revision,'browse_parent_revision':'source-revision'}
        runner.readiness({'metadata':metadata},'v1.10.1-repair-review')
        for key,value in (('unified_ready',False),('default_relation_view','taxonomy'),
                          ('browse_index_revision','stale'),('release','v1.7')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.readiness({'metadata':{**metadata,key:value}},'v1.10.1-repair-review')

    def test_resume_hashes_include_pair_jsonl(self):
        (self.root/'pairs.jsonl').write_text('{"distance":null}\n')
        before = runner.result_hashes(self.root)
        (self.root/'pairs.jsonl').write_text('{"distance":0}\n')
        self.assertNotEqual(before,runner.result_hashes(self.root))

    def make_database(self, name, revision, ready=False):
        path = self.root / name
        metadata = {'database_revision':revision,'release':'v1.10.1-repair-review'}
        if ready:
            metadata.update(unified_ready=True, usability_indexes_ready=True, browse_indexes_ready=True,
                default_relation_view='unified', supported_relation_views=list(runner.VIEWS),
                browse_index_revision=revision, browse_parent_revision='source-revision')
        with sqlite3.connect(path) as con:
            con.execute('CREATE TABLE metadata(key TEXT,value TEXT)')
            con.executemany('INSERT INTO metadata VALUES(?,?)',[(k,json.dumps(v)) for k,v in metadata.items()])
            con.execute('CREATE TABLE domain_registry(domain_id INTEGER)')
            con.execute('INSERT INTO domain_registry VALUES(1)')
        return path

    def test_real_exit_zero_jobs_with_invalid_json_are_failed_and_receipted(self):
        candidate = self.make_database('candidate.sqlite',self.revision,True)
        base = self.make_database('base.sqlite','base')
        old = self.make_database('old.sqlite','old')
        scripts = self.root / 'code' / 'scripts'
        scripts.mkdir(parents=True)
        fake = "import argparse,json,pathlib\np=argparse.ArgumentParser();p.add_argument('--output');a,_=p.parse_known_args();o=pathlib.Path(a.output)\nif o.suffix=='.json':o.write_text('{}')\nelse:o.mkdir(exist_ok=True);(o/'summary.json').write_text('{}')\n"
        names = ['audit_unified_candidate.py','audit_unified_browsing.py','audit_browse_contracts.py',
                 'audit_browse_cycles.py','audit_browse_witnesses.py','audit_browse_cli.py',
                 'compare_unified_reward_policy.py','run_unified_repair_acceptance.py']
        for name in names:
            (scripts/name).write_text(fake)
        samples = self.root / 'samples.json'; samples.write_text('[{"uid":"native:1"}]')
        primary = self.root / 'primary.json'; primary.write_text('[]')
        reports = self.root / 'reports'
        argv = [str(SCRIPT),'--database',str(candidate),'--source-baseline',str(base),
                '--browse-baseline',str(old),'--browse-staging',str(candidate),
                '--primary-records',str(primary),'--samples',str(samples),'--reports',str(reports),
                '--expected-release','v1.10.1-repair-review','--workers','4']
        with patch.object(runner,'ROOT',self.root/'code'), patch.object(sys,'argv',argv):
            self.assertEqual(runner.main(),1)
        receipt = json.loads((reports/'acceptance_receipt.json').read_text())
        self.assertFalse(receipt['all_pass'])
        self.assertEqual(receipt['database_sha256'],runner.sha(candidate))
        self.assertEqual(receipt['database_revision'],self.revision)
        self.assertEqual(set(receipt['jobs']),set(receipt['planned_jobs']))
        self.assertTrue(receipt['candidate_unchanged'])
        self.assertEqual(receipt['jobs']['preservation']['exit_code'],0)
        self.assertFalse(receipt['jobs']['preservation']['verdict']['pass'])
        self.assertIsNotNone(receipt['jobs']['preservation']['started_utc'])
        self.assertIsNotNone(receipt['jobs']['preservation']['ended_utc'])
        self.assertIsNone(receipt['jobs']['self-reward']['exit_code'])
        self.assertFalse((reports/'.acceptance.lock').exists())
        with patch.object(sys,'argv',argv), self.assertRaisesRegex(ValueError,'Reports directory exists'):
            runner.main()

    def test_complete_real_export_is_checked_and_mask_bypass_rejected(self):
        summaries = {}
        for dataset, count in runner.DATASETS.items():
            folder = self.root / 'training' / dataset
            folder.mkdir(parents=True)
            rows = [{'target':{'class_id':str(i)},'snapshot_revision':self.revision,'relation_view':'unified',
                     'category_reward_applicable':True,'hierarchy_endpoint_applicable':i!=1,
                     'hierarchy_endpoint_reason':'ANNOTATION_SCOPE_REVIEW' if i==1 else None}
                    for i in range(1,count+1)]
            (folder/'labels.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows))
            statuses = {}
            with (folder/'pairs.jsonl').open('w') as stream:
                for a,b in combinations(range(1,count+1),2):
                    pair = self.pair(dataset=dataset,left=str(a),right=str(b))
                    if a!=1:
                        pair.update(status='APPLICABLE',applicable=True,distance=2,lcas=[{'uid':'native:type'}])
                        pair.pop('reasons')
                    statuses[pair['status']] = statuses.get(pair['status'],0)+1
                    stream.write(json.dumps(pair)+'\n')
            summary = {'labels':count,'pairs':count*(count-1)//2,'pair_statuses':statuses,
                       'database_revision':self.revision,'relation_view':'unified',
                       'category_reward_preserved':True,'nonapplicable_distance':None}
            runner.write(folder/'summary.json',summary)
            summaries[dataset]=summary
        counts = runner.validate_pair_files(self.root,summaries,self.revision,'unified',training=True)
        self.assertEqual(sum(counts.values()),56917)
        folder = self.root/'training'/'pets37'
        rows = (folder/'pairs.jsonl').read_text().splitlines()
        pair = json.loads(rows[0])
        pair.update(status='APPLICABLE',applicable=True,distance=0,lcas=[{'uid':'native:type'}])
        pair.pop('reasons')
        rows[0] = json.dumps(pair)
        (folder/'pairs.jsonl').write_text('\n'.join(rows)+'\n')
        with self.assertRaisesRegex(ValueError,'bypasses frozen endpoint'):
            runner.validate_pair_files(self.root,summaries,self.revision,'unified',training=True)

    def test_repair_focus_requires_actual_result_and_exact_revision(self):
        with self.assertRaises(FileNotFoundError):
            runner.semantic_gate('repair-focus',self.root,self.revision,self.expected)
        for value in ({'all_pass':False,'database_revision':self.revision},
                      {'all_pass':True,'database_revision':'other-candidate'},
                      {'all_pass':True}, {'database_revision':self.revision}):
            self.dump('result.json',value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner.semantic_gate('repair-focus',self.root,self.revision,self.expected)
        self.dump('result.json',{'all_pass':True,'database_revision':self.revision})
        self.assertTrue(runner.semantic_gate('repair-focus',self.root,self.revision,self.expected)['pass'])

    def test_living_summary_needs_real_bounded_batch(self):
        scopes={'kitchen_and_tableware':155,'lighting':43,'bags_and_luggage':24,'toys':51}
        rows=[{'domain':name,'expected_source_wordnet_synsets':n,'missing_wordnet_scope_uids':[],
               'public_complete_pagination_matches_cache':True,
               'root_statuses':{str(i):'CONNECTED' for i in range(3 if index==0 else 2)}}
              for index,(name,n) in enumerate(scopes.items())]
        good={'status':'PASS','issues':[],'database_revision':self.revision,'current_domains':95,
              'protected_original_domains':91,'protected_aliases_checked':588,'attachment_rules_checked':163,
              'new_domains':rows,'furniture_configurations':[{'uid':str(i),'pass':True,
                  'native_payload_retained':True,'status':'CONNECTED'} for i in range(4)]}
        self.dump('result.json',good)
        self.assertTrue(runner.semantic_gate('living-focused',self.root,self.revision,self.expected)['pass'])
        good['furniture_configurations'] = []
        self.dump('result.json',good)
        with self.assertRaises(ValueError):
            runner.semantic_gate('living-focused',self.root,self.revision,self.expected)


if __name__ == '__main__':
    unittest.main()
