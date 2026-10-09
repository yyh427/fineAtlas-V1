import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/structure_acceptance_contract.py'
spec=importlib.util.spec_from_file_location('acceptance_contract_test',SCRIPT)
contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)


class AcceptanceBindingTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.fingerprints={'code':{'recipe.py':'same'},'inputs':{},'packaging':{}}
        self.databases=[];self.receipts=[]
        for i in range(2):
            directory=self.root/str(i);directory.mkdir()
            database=directory/'data.sqlite';database.write_bytes(b'fixture')
            (directory/'started_fingerprints.json').write_text(json.dumps(self.fingerprints))
            (directory/'build_status.json').write_text(json.dumps({'graph':{'status':'PASS'}}))
            row={'schema':'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1','build_id':str(i),
                 'complete':True,'pass':True,'ended_utc':'2026-10-09','database':str(database),
                 **{name+'_sha256':contract.file_sha256(directory/(name+'.json')) for name in ('started_fingerprints','build_status')}}
            receipt=directory/'build_complete.json';receipt.write_text(json.dumps(row))
            self.databases.append(database);self.receipts.append(receipt)

    def tearDown(self):self.temp.cleanup()

    def validate_builds(self):
        return contract.validate_independent_builds(*self.databases,*self.receipts,self.fingerprints)

    def test_real_independent_receipts_and_tampered_stage(self):
        self.assertEqual(len(self.validate_builds()),2)
        (self.receipts[1].parent/'build_status.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'evidence changed'):self.validate_builds()

    def test_same_inode_or_copied_build_id_rejected(self):
        self.databases[1].unlink();self.databases[1].hardlink_to(self.databases[0])
        with self.assertRaisesRegex(ValueError,'one file or aliases'):self.validate_builds()
        self.databases[1].unlink();shutil.copyfile(self.databases[0],self.databases[1])
        row=json.loads(self.receipts[1].read_text());row['build_id']='0';self.receipts[1].write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError,'Copied build receipt'):self.validate_builds()

    def test_dynamic_inventory_requires_every_table_accounted(self):
        row={'artifacts':{name:{'logical_table_inventory':['ordinary','alias_search_review','fts'],'table_count':3} for name in ('primary','reproduction')},
             'logical_table_count':3,'compared_content_tables':['ordinary','alias_search_review'],'excluded_content_tables':{'fts':'verified FTS virtual'}}
        contract.validate_comparison_inventory(row)
        row['compared_content_tables'].remove('alias_search_review')
        with self.assertRaisesRegex(ValueError,'accounting'):contract.validate_comparison_inventory(row)

    def test_boolean_public_proof_is_insufficient(self):
        row={'all_pass':True,'public_download_unauthenticated':True,'matching_installed_sdk':True,
             'ended_utc':'now','database_sha256':'hash','database_revision':'revision','release':'rc'}
        with self.assertRaisesRegex(ValueError,'evidence files'):
            contract.validate_public_evidence(row,row,self.root/'public.json')

    def test_completed_receipt_requires_every_job(self):
        with self.assertRaises(ValueError):contract.validate_completed_acceptance({'complete':True,'all_pass':True})


if __name__=='__main__':unittest.main()
