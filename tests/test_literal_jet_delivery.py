"""Additive checkpoint gates preserve old hashes and require actual fifth receipts."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import coordinate_literal_jet_delivery as delivery
import resume_literal_jet_repairs as resume
import promote_literal_jet_with_regression_gate as promotion
from structure_literal_jet_delivery_guard import SPEC, require_literal_jet_receipt
import test_structure_delivery_oem_guard as controls
import verify_literal_jet_installed_sdk as installed
from structure_literal_jet_delivery_guard import require_literal_jet_child_build, CHILD_STAGES
from structure_primary_aircraft_delivery_guard import SPEC as FAMILY_SPEC, require_primary_aircraft_receipt


class FifthReceiptGuards(controls.OEMEvidenceGuards):
    def setUp(self):
        super().setUp(); self.spec=SPEC
        module=self.code/SPEC.module; module.parent.mkdir(parents=True,exist_ok=True)
        module.write_text("INPUT_NAME = 'renamed-oem-repairs.json'\n")
        self.value['schema']=SPEC.schema; self.report.write_text(json.dumps(self.value))
        with sqlite3.connect(self.database) as c:
            c.execute('INSERT INTO metadata VALUES(?,?)',(SPEC.metadata_key,json.dumps({'manifest_sha256':self.value['manifest_sha256'],'operations_sha256':self.value['operations_sha256'],'operation_count':1})))
    def validate(self): return require_literal_jet_receipt(self.report,self.database,self.inputs,'actual-revision',self.code)
    def test_absent_optional_input_requires_no_receipt(self):
        self.manifest.unlink()
        with self.assertRaisesRegex(ValueError,'frozen fifth'): self.validate()
    def test_missing_fifth_delta_cannot_use_prior_only_delivery(self):
        self.manifest.unlink()
        with self.assertRaisesRegex(ValueError,'frozen fifth'): self.validate()
    def test_no_applied_metadata_cannot_claim_actual_fifth_pass(self):
        with sqlite3.connect(self.database) as c: c.execute('DELETE FROM metadata WHERE key=?',(SPEC.metadata_key,))
        with self.assertRaisesRegex(ValueError,'applied delta'): self.validate()
    def test_finalization_checks_fifth_before_original_core(self):
        coordinator=delivery.LiteralJetCoordinator.__new__(delivery.LiteralJetCoordinator)
        with patch.object(coordinator,'validate_public_fifth',side_effect=ValueError('missing fifth')):
            with patch.object(delivery.Coordinator,'finalize') as old:
                with self.assertRaisesRegex(ValueError,'missing fifth'): coordinator.finalize()
                old.assert_not_called()
    def test_promotion_cannot_bypass_actual_fifth_public_proof(self):
        with patch.object(promotion,'LiteralJetCoordinator') as factory:
            factory.return_value.c={'database':'/candidate'}; factory.return_value.inputs=Path('/inputs')
            factory.return_value.validate_public_primary.side_effect=ValueError('missing actual public fifth')
            with patch.object(promotion.subprocess,'run') as old:
                with self.assertRaisesRegex(ValueError,'missing actual'):
                    promotion.main(['--literal-jet-delivery-config','config','--source','/candidate','--source-inputs','/inputs'])
                old.assert_not_called()
    def test_package_cannot_skip_actual_fifth_local_checks(self):
        coordinator=delivery.LiteralJetCoordinator.__new__(delivery.LiteralJetCoordinator)
        with patch.object(coordinator,'validate_local_fifth',side_effect=ValueError('missing local fifth')):
            with patch.object(delivery.Coordinator,'package') as old:
                with self.assertRaises(ValueError): coordinator.package()
                old.assert_not_called()

    def test_public_cannot_skip_actual_fifth_local_checks(self):
        coordinator=delivery.LiteralJetCoordinator.__new__(delivery.LiteralJetCoordinator)
        with patch.object(coordinator,'validate_local_fifth',side_effect=ValueError('missing local fifth')):
            with patch.object(delivery.Coordinator,'public') as old:
                with self.assertRaises(ValueError): coordinator.public()
                old.assert_not_called()


class ChildAndInstalledSdkGuards(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
    def child(self, stages):
        path=self.root/'build_complete.json'
        value={'schema':'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1','complete':True,'pass':True,'build_id':'child','ended_utc':'now','required_stages':list(stages)}
        for name,data in [('started_fingerprints',{}),('build_status',{stage:{'status':'PASS'} for stage in stages})]:
            target=self.root/(name+'.json'); target.write_text(json.dumps(data)); value[name+'_sha256']=resume.digest_file(target)
        path.write_text(json.dumps(value)); return path
    def test_completed_six_stage_child_passes(self):
        self.assertTrue(require_literal_jet_child_build(self.child(CHILD_STAGES))['pass'])
    def test_old_nine_stage_parent_cannot_impersonate_child(self):
        with self.assertRaisesRegex(ValueError,'seven-stage'): require_literal_jet_child_build(self.child(resume.PARENT_STAGES))
    def test_previous_six_stage_child_without_sixth_delta_rejected(self):
        stages=tuple(x for x in CHILD_STAGES if x!='primary_aircraft_family_repairs')
        with self.assertRaisesRegex(ValueError,'seven-stage'): require_literal_jet_child_build(self.child(stages))
    def test_missing_sixth_sdk_module_cannot_pass(self):
        package,frozen=self.inventory(); (package/'structure_primary_aircraft_family_repairs.py').unlink()
        with self.assertRaisesRegex(ValueError,'complete frozen'): installed.verify_source_inventory(package,self.root/'venv',frozen)
    def test_partial_actual_child_rejected(self):
        path=self.child(CHILD_STAGES); status=self.root/'build_status.json'; data=json.loads(status.read_text()); data['literal_jet_scope_repairs']['status']='RUNNING'; status.write_text(json.dumps(data))
        value=json.loads(path.read_text()); value['build_status_sha256']=resume.digest_file(status); path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'Every actual'): require_literal_jet_child_build(path)
    def inventory(self):
        package=self.root/'venv/lib/site-packages/fineatlas'; package.mkdir(parents=True)
        for name in ('__init__.py','structure_literal_jet_scope_repairs.py','structure_primary_aircraft_family_repairs.py'): (package/name).write_text('# actual installed source\n')
        frozen={'src/fineatlas/'+p.name:resume.digest_file(p) for p in package.glob('*.py')}
        return package,frozen
    def test_complete_installed_fifth_source_inventory_passes(self):
        package,frozen=self.inventory(); self.assertEqual(len(installed.verify_source_inventory(package,self.root/'venv',frozen)),3)
    def test_missing_new_sdk_module_cannot_pass(self):
        package,frozen=self.inventory(); (package/'structure_literal_jet_scope_repairs.py').unlink()
        with self.assertRaisesRegex(ValueError,'complete frozen'): installed.verify_source_inventory(package,self.root/'venv',frozen)
    def test_checkout_cannot_substitute_for_installed_sdk(self):
        package,frozen=self.inventory()
        with self.assertRaisesRegex(ValueError,'isolated installed'): installed.verify_source_inventory(package,self.root/'other-venv',frozen)
    def test_edited_installed_sdk_module_cannot_pass(self):
        package,frozen=self.inventory(); (package/'__init__.py').write_text('edited')
        with self.assertRaises(ValueError): installed.verify_source_inventory(package,self.root/'venv',frozen)


class SixthReceiptGuards(controls.OEMEvidenceGuards):
    def setUp(self):
        super().setUp(); self.spec=FAMILY_SPEC
        module=self.code/FAMILY_SPEC.module; module.parent.mkdir(parents=True,exist_ok=True)
        module.write_text("INPUT_NAME = 'renamed-oem-repairs.json'\n")
        self.value['schema']=FAMILY_SPEC.schema; self.report.write_text(json.dumps(self.value))
        with sqlite3.connect(self.database) as c:
            c.execute('INSERT INTO metadata VALUES(?,?)',(FAMILY_SPEC.metadata_key,json.dumps({'manifest_sha256':self.value['manifest_sha256'],'operations_sha256':self.value['operations_sha256'],'operation_count':1})))
    def validate(self): return require_primary_aircraft_receipt(self.report,self.database,self.inputs,'actual-revision',self.code)
    def test_absent_optional_input_requires_no_receipt(self):
        self.manifest.unlink()
        with self.assertRaisesRegex(ValueError,'frozen sixth'): self.validate()
    def test_fifth_receipt_cannot_satisfy_sixth_contract(self):
        self.value['schema']=SPEC.schema; self.report.write_text(json.dumps(self.value))
        with self.assertRaisesRegex(ValueError,'Complete actual'): self.validate()
    def test_old_parent_without_applied_sixth_metadata_rejected(self):
        with sqlite3.connect(self.database) as c: c.execute('DELETE FROM metadata WHERE key=?',(FAMILY_SPEC.metadata_key,))
        with self.assertRaisesRegex(ValueError,'applied delta'): self.validate()
    def test_finalize_blocks_missing_sixth_before_original_core(self):
        coordinator=delivery.LiteralJetCoordinator.__new__(delivery.LiteralJetCoordinator)
        with patch.object(coordinator,'validate_public_primary',side_effect=ValueError('missing sixth')):
            with patch.object(delivery.Coordinator,'finalize') as old:
                with self.assertRaisesRegex(ValueError,'missing sixth'): coordinator.finalize()
                old.assert_not_called()
    def test_local_gate_requires_actual_sixth_despite_fifth_success(self):
        coordinator=delivery.LiteralJetCoordinator.__new__(delivery.LiteralJetCoordinator)
        coordinator.root=self.root; coordinator.c={'database':str(self.database),'reproduction':str(self.database)}
        coordinator.inputs=self.inputs; coordinator.meta={'database_revision':'actual-revision'}
        with patch.object(coordinator,'validate_child_builds'), patch.object(delivery,'ROOT',self.code), patch.object(delivery,'require_literal_jet_receipt',return_value={'pass':True}):
            with self.assertRaises(FileNotFoundError): coordinator.validate_local_fifth()
    def test_package_blocks_missing_actual_sixth_despite_fifth_success(self):
        coordinator=delivery.LiteralJetCoordinator.__new__(delivery.LiteralJetCoordinator)
        coordinator.root=self.root; coordinator.c={'database':str(self.database),'reproduction':str(self.database)}
        coordinator.inputs=self.inputs; coordinator.meta={'database_revision':'actual-revision'}
        with patch.object(coordinator,'validate_child_builds'), patch.object(delivery,'ROOT',self.code), patch.object(delivery,'require_literal_jet_receipt',return_value={'pass':True}), patch.object(delivery.Coordinator,'package') as old:
            with self.assertRaises(FileNotFoundError): coordinator.package()
            old.assert_not_called()
    def test_public_blocks_missing_actual_sixth_despite_fifth_success(self):
        coordinator=delivery.LiteralJetCoordinator.__new__(delivery.LiteralJetCoordinator)
        coordinator.root=self.root; coordinator.c={'database':str(self.database),'reproduction':str(self.database)}
        coordinator.inputs=self.inputs; coordinator.meta={'database_revision':'actual-revision'}
        with patch.object(coordinator,'validate_child_builds'), patch.object(delivery,'ROOT',self.code), patch.object(delivery,'require_literal_jet_receipt',return_value={'pass':True}), patch.object(delivery.Coordinator,'public') as old:
            with self.assertRaises(FileNotFoundError): coordinator.public()
            old.assert_not_called()
    def test_actual_public_sixth_preflight_cannot_finalize(self):
        import shutil
        coordinator=delivery.LiteralJetCoordinator.__new__(delivery.LiteralJetCoordinator)
        coordinator.root=self.root; coordinator.fingerprints={'code':{FAMILY_SPEC.module:'module-hash'}}
        db=self.root/'public/data/fineatlas.sqlite'; db.parent.mkdir(parents=True); shutil.copy(self.database,db)
        inputs=self.root/'public/frozen/inputs'; inputs.parent.mkdir(parents=True); shutil.copytree(self.inputs,inputs)
        checks=self.root/'public/checks'; checks.mkdir()
        fifth_path=checks/'literal_jet_public_extension.json'; fifth_path.write_text('{}')
        sdk={'path':'already-validated-sdk','sha256':'sdk-proof'}
        fifth={'database_revision':'actual-revision','database_sha256':'actual-sha','original_public_verification_sha256':'parent-proof','evidence':{'installed-sdk-inventory':sdk}}
        self.value.update(database=str(db),preflight_only=True)
        report=checks/'primary-aircraft-family.json'; report.write_text(json.dumps(self.value))
        extension={'schema':'FINEATLAS_PRIMARY_AIRCRAFT_PUBLIC_EXTENSION_V1','pass':True,'database':str(db),'database_revision':'actual-revision','database_sha256':'actual-sha','original_public_verification_sha256':'parent-proof','literal_jet_public_extension_sha256':resume.digest_file(fifth_path),'evidence':{'primary-aircraft-family':{'path':str(report),'sha256':resume.digest_file(report)},'installed-sdk-inventory':sdk}}
        (checks/'primary_aircraft_public_extension.json').write_text(json.dumps(extension))
        with patch.object(coordinator,'validate_public_fifth',return_value=(fifth,{})),patch.object(delivery,'ROOT',self.code),patch.object(delivery.Coordinator,'finalize') as old:
            with self.assertRaisesRegex(ValueError,'Complete actual'): coordinator.finalize()
            old.assert_not_called()
    def test_stable_wrapper_requires_actual_sixth_public_evidence(self):
        with patch.object(promotion,'LiteralJetCoordinator') as factory:
            factory.return_value.c={'database':'/candidate'}; factory.return_value.inputs=Path('/inputs')
            factory.return_value.validate_public_primary.side_effect=ValueError('missing actual sixth public')
            with patch.object(promotion.subprocess,'run') as old:
                with self.assertRaisesRegex(ValueError,'missing actual sixth'):
                    promotion.main(['--literal-jet-delivery-config','config','--source','/candidate','--source-inputs','/inputs'])
                old.assert_not_called()


class CompleteResumedParentGuards(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.db=self.root/'parent.sqlite'; self.receipt=self.root/'build_complete.json'; self.integrity=self.root/'integrity.json'
        self.original={'inputs':{'prior.json':'old-input'},'code':{'src/fineatlas/old.py':'old-code'},'packaging':{'pyproject.toml':'old-package'}}
        self.extended=copy.deepcopy(self.original); self.extended['inputs']['fifth.json']='new'; self.extended['code']['scripts/new.py']='new-code'
        meta={'structure_frozen_build_manifest':self.original,'database_revision':'parent','release':'v1.11.0rc1','browse_parent_revision':'graph','browse_source_revision':'graph','browse_index_revision':'parent','unified_ready':True,'usability_indexes_ready':True,'browse_indexes_ready':True,'structure_resume_parent':{'parent_revision':'057'}}
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE metadata(key,value)'); c.executemany('INSERT INTO metadata VALUES(?,?)',[(k,json.dumps(v)) for k,v in meta.items()])
        self.states={stage:{'status':'PASS'} for stage in resume.PARENT_STAGES}
        self.value={'schema':'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1','complete':True,'pass':True,'build_id':'distinct-parent','ended_utc':'2026-10-10','database':str(self.db),'release':'v1.11.0rc1','source_graph_revision':'graph','revision':'parent','required_stages':list(resume.PARENT_STAGES)}
        self.seal={'pass':True,'complete':True,'integrity_pass':True,'file_unchanged_during_checks':True,'all_frozen_inputs_and_recipes_checked':True,'integrity_check':['ok'],'database':str(self.db),'database_revision':'parent','release':'v1.11.0rc1','bytes':self.db.stat().st_size,'sha256':'0'*64}
        self.persist()
    def persist(self):
        (self.root/'started_fingerprints.json').write_text(json.dumps(self.original)); (self.root/'build_status.json').write_text(json.dumps(self.states))
        for name in ('started_fingerprints','build_status'): self.value[name+'_sha256']=resume.digest_file(self.root/(name+'.json'))
        self.receipt.write_text(json.dumps(self.value)); self.integrity.write_text(json.dumps(self.seal))
    def validate(self): return resume.validate_literal_jet_parent_receipt(self.db,self.receipt,self.extended,self.integrity)
    def tearDown(self): self.tmp.cleanup()
    def test_complete_nine_stage_parent_accepts_only_additive_inventory(self): self.assertEqual(self.validate()[1]['structure_resume_parent']['parent_revision'],'057')
    def test_changed_prior_code_cannot_start_child(self):
        self.extended['code']['src/fineatlas/old.py']='changed'
        with self.assertRaisesRegex(ValueError,'implementation/input'): self.validate()
    def test_changed_prior_input_cannot_start_child(self):
        del self.extended['inputs']['prior.json']
        with self.assertRaises(ValueError): self.validate()
    def test_partial_source_parent_cannot_start_child(self):
        self.states.pop(resume.PARENT_STAGES[0]); self.persist()
        with self.assertRaisesRegex(ValueError,'nine resumed'): self.validate()
    def test_whole_hash_integrity_receipt_required(self):
        self.seal['integrity_pass']=False; self.persist()
        with self.assertRaisesRegex(ValueError,'integrity'): self.validate()
    def test_changed_parent_build_evidence_rejected(self):
        (self.root/'build_status.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'evidence changed'): self.validate()
    def test_original_scope_lineage_is_required(self):
        with sqlite3.connect(self.db) as c: c.execute("DELETE FROM metadata WHERE key='structure_resume_parent'")
        self.seal['bytes']=self.db.stat().st_size; self.persist()
        with self.assertRaisesRegex(ValueError,'original lineage'): self.validate()

if __name__=='__main__': unittest.main()
