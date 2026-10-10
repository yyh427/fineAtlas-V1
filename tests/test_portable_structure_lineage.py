"""Portable history must keep exact physical build evidence and its limits."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import portable_structure_lineage as portable
from structure_literal_jet_delivery_guard import CHILD_STAGES


class PortableLineageControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.support=SimpleNamespace(root=self.root)
        self.accepted={'database_revision':'final','database_sha256':'final-sha'}
        rows=[]
        for index,name in enumerate(('primary','reproduction')):
            folder=self.root/'builds'/name;folder.mkdir(parents=True)
            started=folder/'started_fingerprints.json';started.write_text('{}')
            status=folder/'build_status.json';status.write_text(json.dumps({stage:{'status':'PASS'}for stage in CHILD_STAGES}))
            seal={'sha256':'parent-whole-sha','database_revision':'parent-revision','integrity_check':['ok'],
                **{key:True for key in('pass','complete','integrity_pass','file_unchanged_during_checks','all_frozen_inputs_and_recipes_checked')}}
            integrity=folder/'parent_integrity.json';integrity.write_text(json.dumps(seal))
            lineage={'resumed_build_id':'child-'+name,'resumed_revision':'final','parent_build_id':'parent-'+name,
                'parent_source_inode':[2049,index+10],'parent_revision':'parent-revision',
                'parent_database':'/unavailable-clean-host/parent-'+name+'.sqlite',
                'parent_database_sha256':'parent-whole-sha','parent_integrity_sha256':portable.digest(integrity)}
            path=folder/'parent_lineage.json';path.write_text(json.dumps(lineage))
            child={'schema':'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1','pass':True,'complete':True,
                'build_id':lineage['resumed_build_id'],'revision':'final','ended_utc':'historical',
                'parent_build_id':lineage['parent_build_id'],'parent_source_inode':lineage['parent_source_inode'],
                'parent_lineage_sha256':portable.digest(path),'required_stages':list(CHILD_STAGES),
                'started_fingerprints_sha256':portable.digest(started),'build_status_sha256':portable.digest(status)}
            (folder/'build_complete.json').write_text(json.dumps(child))
            rows.append({'name':name,'files':{p.name:{'member':str(p.relative_to(self.root)),'sha256':portable.digest(p)}for p in folder.iterdir()}})
        self.proof={'schema':portable.SCHEMA,'pass':True,'candidate_revision':'final','candidate_sha256':'final-sha',
            'current_host_actual_inodes_checked':True,'children':rows,
            'original_lineage_validator_sha256':portable.digest(Path(portable.__file__).with_name('resume_structure_repairs.py')),
            'actual_local_physical_parent_audit':{'pass':True,'parent_build_ids':['parent-primary','parent-reproduction'],
                'resumed_build_ids':['child-primary','child-reproduction'],'distinct_source_inodes':True,'parent_revision':'parent-revision'}}
        self.save()
    def save(self):(self.root/'builds/build-independence.json').write_text(json.dumps(self.proof))
    def validate(self):return portable.validate_portable_parent_independence(self.support,
        self.root/'builds/primary/build_complete.json',self.root/'builds/reproduction/build_complete.json',self.accepted)
    def test_fresh_exact_history_verifies_without_claiming_new_inode_check(self):
        result=self.validate();self.assertTrue(result['immutable_historical_lineage_bytes_checked'])
        self.assertFalse(result['physical_parent_inodes_rechecked_here'])
    def test_host_build_receipt_cannot_replace_downloaded_original(self):
        with self.assertRaises(ValueError):portable.validate_portable_parent_independence(self.support,'/old/host/receipt',
            self.root/'builds/reproduction/build_complete.json',self.accepted)
    def test_changed_parent_full_byte_seal_blocks(self):
        path=self.root/'builds/primary/parent_integrity.json';value=json.loads(path.read_text());value['sha256']='wrong';path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.validate()
    def test_missing_actual_historical_physical_audit_blocks(self):
        self.proof['current_host_actual_inodes_checked']=False;self.save()
        with self.assertRaises(ValueError):self.validate()
    def test_claim_of_non_independent_parents_blocks(self):
        self.proof['actual_local_physical_parent_audit']['parent_build_ids']=['same','same'];self.save()
        with self.assertRaises(ValueError):self.validate()
    def test_wrong_final_candidate_binding_blocks(self):
        self.proof['candidate_revision']='intermediate';self.save()
        with self.assertRaises(ValueError):self.validate()
    def test_changed_child_stage_status_blocks(self):
        path=self.root/'builds/primary/build_status.json';path.write_text('{}')
        with self.assertRaises(ValueError):self.validate()


if __name__=='__main__':unittest.main()
