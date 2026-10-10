"""An agreed plan must identify the actual final snapshot explicitly."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import run_final_nominal_design_scope_external_audit as runner

class PlanBindings(unittest.TestCase):
    def setUp(self):
        script=runner.HERE/'independent_nominal_design_scope_final_interface_audit.py'
        self.plan={'execution_authorized':True,'status':'READY_ACTUAL_NOMINAL_FINAL_CHILD','required_stages':list(runner.REQUIRED_STAGES),'final_code_commit':'code','final_source_seal_sha256':'seal','frozen_inputs_manifest_sha256':'inputs','actual_final_revision':'actual-final','actual_final_fingerprints':{'inputs':{},'code':{},'packaging':{}},'auditor_sha256':runner.digest(script),'execution':{'local':{'installed_sdk':False,'command':['python','-B',str(script),'--require-final-child','--database','db']}}}
    def test_explicit_final_plan_authorizes_matching_phase(self):
        self.assertFalse(runner.authorize(self.plan,'local')['installed_sdk'])
    def test_matching_source8_final_plan_cannot_impersonate_source9_recipe(self):
        self.plan['required_stages']=['verify_complete_owned_scope_parent_copy','complete_owned_type_repairs','whole_graph_recomputation','freeze_metadata','browse_staging','embed_browse_indexes']
        with self.assertRaises(AssertionError):runner.authorize(self.plan,'local')
    def test_old_source8_final_status_cannot_authorize_nominal_scope(self):
        self.plan['status']='READY_ACTUAL_FINAL_CHILD'
        with self.assertRaises(AssertionError):runner.authorize(self.plan,'local')
    def test_pending_plan_does_not_authorize(self):
        self.plan['execution_authorized']=False
        with self.assertRaises(AssertionError):runner.authorize(self.plan,'local')
    def test_unknown_final_revision_or_missing_frozen_inventory_is_rejected(self):
        for key in ('actual_final_revision','actual_final_fingerprints'):
            plan=copy.deepcopy(self.plan);plan[key]=None
            with self.assertRaises(AssertionError):runner.authorize(plan,'local')
    def test_changed_external_audit_source_is_rejected(self):
        self.plan['auditor_sha256']='different'
        with self.assertRaises(AssertionError):runner.authorize(self.plan,'local')
    def test_local_cannot_claim_installed_fresh_public_phase(self):
        self.plan['execution']['local']['installed_sdk']=True
        with self.assertRaises(AssertionError):runner.authorize(self.plan,'local')
    def test_two_matching_other_candidate_receipts_cannot_replace_approved_final(self):
        with tempfile.TemporaryDirectory()as t:
            paths=[]
            for name in ('primary','reproduction'):
                p=Path(t)/(name+'.json');p.write_text(json.dumps({'complete':True,'pass':True,'build_id':name,'revision':'other-matching-final'}));paths.append(str(p))
            with self.assertRaises(AssertionError):runner.physical_prerequisite(self.plan,{'build_receipts':paths})

    def public_receipt(self,directory):
        database=Path(directory)/'database.sqlite';database.write_bytes(b'fixture');stat=database.stat()
        receipt={'schema':'FINEATLAS_PUBLIC_DOWNLOAD_PROOF_V1','fresh_download':True,'authenticated':False,'asset_proofs':[{'fresh_download':True,'network_request':True}],'database_revision':'actual-final','database_sha256':'expected-whole-sha','database_bytes':stat.st_size,'database':str(database),'artifact_stamp':[stat.st_size,stat.st_mtime_ns,stat.st_ino]}
        path=Path(directory)/'download.json';path.write_text(json.dumps(receipt));self.plan['actual_final_database_sha256']='expected-whole-sha'
        return database,path,receipt

    def test_real_downloader_schema_requires_no_invented_pass_field(self):
        with tempfile.TemporaryDirectory()as t:
            database,path,receipt=self.public_receipt(t)
            self.assertNotIn('pass',runner.fresh_public_database_prerequisite(self.plan,{'public_download_receipt':path},database))

    def test_public_transfer_without_actual_network_is_rejected(self):
        with tempfile.TemporaryDirectory()as t:
            database,path,receipt=self.public_receipt(t);receipt['asset_proofs'][0]['network_request']=False;path.write_text(json.dumps(receipt))
            with self.assertRaises(AssertionError):runner.fresh_public_database_prerequisite(self.plan,{'public_download_receipt':path},database)

    def test_public_database_stamp_and_accepted_whole_sha_are_bound(self):
        with tempfile.TemporaryDirectory()as t:
            database,path,receipt=self.public_receipt(t);self.plan['actual_final_database_sha256']='another-whole-sha'
            with self.assertRaises(AssertionError):runner.fresh_public_database_prerequisite(self.plan,{'public_download_receipt':path},database)
            self.plan['actual_final_database_sha256']='expected-whole-sha';database.write_bytes(b'changed-database')
            with self.assertRaises(AssertionError):runner.fresh_public_database_prerequisite(self.plan,{'public_download_receipt':path},database)

if __name__=='__main__':unittest.main()
