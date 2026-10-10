"""Formal delivery cannot skip semantic/public gates or use the six-stage package."""
import importlib
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))


class FormalCoordinatorGateControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module=importlib.import_module('coordinate_nominal_formal_delivery')
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.obj=self.module.FormalNominalScopeCoordinator.__new__(self.module.FormalNominalScopeCoordinator)
        self.obj.root=self.root;self.obj.inputs=self.root/'inputs';self.obj.meta={'database_revision':'actual-formal'}
        self.obj.c={'legacy_dispositions':str(self.root/'ledger.json')};(self.root/'ledger.json').write_text('{}')
    def test_package_calls_all_semantic_gates_before_original_packager(self):
        cls=self.module.FormalNominalScopeCoordinator
        for guard in ('validate_child_builds','validate_local_fifth','require_local_temporal','require_local_complete_type','require_local_nominal_scope'):
            with self.subTest(guard=guard),ExitStack()as stack:
                for other in ('validate_child_builds','validate_local_fifth','require_local_temporal','require_local_complete_type','require_local_nominal_scope'):
                    stack.enter_context(patch.object(cls,other,side_effect=ValueError('missing actual required proof')if other==guard else None))
                package=stack.enter_context(patch.object(self.module.Coordinator,'package'))
                with self.assertRaises(ValueError):self.obj.package()
                package.assert_not_called()
    def test_finalize_cannot_bypass_actual_formal_nominal_public_guard(self):
        with patch.object(self.module.FormalNominalScopeCoordinator,'validate_public_nominal_scope',side_effect=ValueError('missing actual formal public')),patch.object(self.module.Coordinator,'finalize')as finalize:
            with self.assertRaises(ValueError):self.obj.finalize()
            finalize.assert_not_called()
    def test_actual_public_requires_both_source8_and_nominal_scope_receipts(self):
        with patch.object(self.module.FormalNominalScopeCoordinator,'require_local_complete_type'),patch.object(self.module.FormalNominalScopeCoordinator,'require_local_nominal_scope'),patch.object(self.module.NominalScopePriorCoordinator,'public'),patch.object(self.module,'require_complete_type_receipt',side_effect=ValueError('actual source8 missing')):
            with self.assertRaises(ValueError):self.obj.public()
        with patch.object(self.module.FormalNominalScopeCoordinator,'require_local_complete_type'),patch.object(self.module.FormalNominalScopeCoordinator,'require_local_nominal_scope'),patch.object(self.module.NominalScopePriorCoordinator,'public'),patch.object(self.module,'require_complete_type_receipt'),patch.object(self.module,'require_nominal_scope_receipt',side_effect=ValueError('actual nominal missing')):
            with self.assertRaises(ValueError):self.obj.public()
    def test_package_override_uses_formal_support_instead_of_the_candidate_six_stage_support(self):
        self.assertIn('Coordinator.package(self)',__import__('inspect').getsource(self.module.FormalNominalScopeCoordinator.package))
        self.assertEqual(self.module.package_support.__module__,'structure_nominal_formal_regression_support')
    def test_current_public_extension_explicitly_identifies_four_stages(self):
        public=self.root/'public/checks';public.mkdir(parents=True)
        (public/'formal_nominal_public_extension.json').write_text(json.dumps({'schema':'FINEATLAS_FORMAL_NOMINAL_PUBLIC_EXTENSION_V1','pass':True,'database_revision':'actual-formal','database_sha256':'sha','actual_stage_count':6,'semantic_candidate_stage_count':6,'generation_count':4}))
        with patch.object(self.module.FormalNominalScopeCoordinator,'validate_public_owned'),patch.object(self.module.FormalNominalScopeCoordinator,'accepted',return_value={'database_revision':'actual-formal','database_sha256':'sha'}):
            with self.assertRaises(ValueError):self.obj.validate_public_complete_type()

    def test_constructor_populates_original_controller_with_actual_formal_receipts(self):
        config={'formal_code_root':str(self.module.ROOT),'delivery_root':str(self.root),
            'inputs':str(self.root/'inputs'),'database':str(self.root/'formal.sqlite'),
            'primary_build':str(self.root/'primary/build_complete.json'),
            'reproduction_build':str(self.root/'reproduction/build_complete.json')}
        for name in ('primary','reproduction'):
            path=Path(config[name+'_build']);path.parent.mkdir();path.write_text('{}')
        path=self.root/'config.json';path.write_text(json.dumps(config))
        fingerprints={'inputs':{},'code':{},'packaging':{}}
        builds=[({'build_id':'actual-four-'+name,'revision':'formal'},
            {'build_id':'actual-six-'+name,'revision':'source9'})for name in ('primary','reproduction')]
        with patch.object(self.module,'metadata',return_value={'structure_frozen_build_manifest':fingerprints}),patch.object(self.module,'build_fingerprints',return_value=fingerprints),patch.object(self.module.FormalNominalScopeCoordinator,'validate_child_builds',return_value=builds):
            obj=self.module.FormalNominalScopeCoordinator(path)
        self.assertIs(obj.parents,obj.final_parents)
        self.assertEqual(obj.lineage_primary,Path(config['primary_build']))
        self.assertEqual(obj.lineage_reproduction,Path(config['reproduction_build']))
        self.assertEqual(obj.parents['stage_count'],4)
        self.assertEqual([row['actual_formal_build_id']for row in obj.parents['records']],['actual-four-primary','actual-four-reproduction'])

    def test_public_replaces_existing_evidence_flags_once_with_downloaded_four_stage_paths(self):
        support=SimpleNamespace(root=self.root/'public/regression-support',path=self.root/'public/regression-support/registry.json')
        self.obj.c['public_base_url']='https://example.invalid/release'
        flags=('--reference','--inventory','--primary-build','--reproduction-build','--legacy-reference','--legacy-baseline-matrix','--legacy-dispositions')
        values=['--code',self.module.ROOT]
        for flag in flags:values.extend([flag,'/historical-host'+flag])
        with patch.object(self.module,'read',return_value={}),patch.object(self.module,'download_public_support',return_value=(support,None)),patch.object(self.module.FormalNominalScopeCoordinator,'accepted',return_value={}),patch.object(self.module.FormalNominalScopeCoordinator,'prepare_public_primary_snapshots',return_value=self.root/'public/source-snapshots'):
            command=self.obj.cmd('run_structure_public_checks.py',*values)
        self.assertTrue(command[2].endswith('run_nominal_formal_public_checks.py'))
        for flag in (*flags,'--regression-support-registry','--primary-snapshots-dir'):
            self.assertEqual(command.count(flag),1)
            self.assertNotIn('historical-host',command[command.index(flag)+1])
        self.assertEqual(command[command.index('--primary-build')+1],str(support.root/'builds/primary/build_complete.json'))

    def test_duplicate_parent_receipt_flag_is_rejected_before_public_execution(self):
        support=SimpleNamespace(root=self.root,path=self.root/'registry.json')
        self.obj.c['public_base_url']='https://example.invalid/release'
        with patch.object(self.module,'read',return_value={}),patch.object(self.module,'download_public_support',return_value=(support,None)),patch.object(self.module.FormalNominalScopeCoordinator,'accepted',return_value={}),patch.object(self.module.FormalNominalScopeCoordinator,'prepare_public_primary_snapshots',return_value=self.root):
            with self.assertRaises(ValueError):self.obj.cmd('run_structure_public_checks.py','--primary-build','old','--primary-build','new')

    def test_primary_public_override_preserves_every_prior_condition_with_formal_support_binding(self):
        import ast
        import inspect
        import textwrap
        original=self.module.NominalScopePriorCoordinator.validate_public_primary
        formal=self.module.FormalNominalScopeCoordinator.validate_public_primary
        self.assertEqual(ast.dump(ast.parse(textwrap.dedent(inspect.getsource(original)))),
            ast.dump(ast.parse(textwrap.dedent(inspect.getsource(formal)))))
        self.assertEqual(formal.__globals__['require_public_support'].__module__,
            'structure_nominal_formal_regression_support')
        self.assertNotEqual(original.__globals__['require_public_support'].__module__,
            formal.__globals__['require_public_support'].__module__)

    def test_original_local_controller_writes_factual_formal_parent_proof(self):
        self.obj.c.update(local_output=str(self.root/'local'),database=str(self.root/'primary.sqlite'),
            reproduction=str(self.root/'reproduction.sqlite'),baseline='baseline',inventory='inventory',reference='reference',
            primary_build='formal-primary-four-stage',reproduction_build='formal-repro-four-stage',legacy_reference='legacy-reference',
            legacy_baseline_matrix='legacy-baseline')
        self.obj.parents={'schema':'FINEATLAS_ACTUAL_FORMAL_VERSION_ONLY_PARENT_INDEPENDENCE_V1','stage_count':4}
        self.obj.fingerprints={'code':{},'inputs':{},'packaging':{}}
        def execute(name,command):
            for relative in ('primary-scope-repairs.json','reproduction-scope-repairs.json','local-legacy-regressions/summary.json'):
                path=self.root/relative;path.parent.mkdir(exist_ok=True,parents=True);path.write_text('{}')
        with patch.object(self.module.Coordinator,'execute',side_effect=execute),patch.object(self.module.FormalNominalScopeCoordinator,'cmd',side_effect=lambda *args:list(args)),patch('coordinate_structure_delivery.optional_oem_input',return_value=None),patch('coordinate_structure_delivery.required_deltas',return_value=[]):
            self.module.Coordinator.local(self.obj)
        receipt=json.loads((self.root/'local_complete.json').read_text())
        self.assertEqual(receipt['parents'],self.obj.parents)
        self.assertEqual(receipt['parents']['stage_count'],4)

if __name__=='__main__':unittest.main()
