"""Historical proof must identify the new c933 parent, without host fallbacks."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import portable_complete_structure_lineage as portable
from structure_literal_jet_delivery_guard import CHILD_STAGES


class CompletePortableLineageControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.support=SimpleNamespace(root=self.root)
        self.parent_inventory={'inputs':{'parent-input':'source-sha'},'code':{'old-code':'code-sha'},'packaging':{'package-rule':'packaging-sha'}}
        self.inventory={**self.parent_inventory,'inputs':{**self.parent_inventory['inputs'],'child-input':'child-sha'}}
        self.accepted={'database_revision':'final','database_sha256':'final-sha','fingerprints':self.inventory};rows=[]
        for index,name in enumerate(('primary','reproduction')):
            folder=self.root/'builds'/name;parent=folder/'source-parent';parent.mkdir(parents=True)
            (parent/'started_fingerprints.json').write_text(json.dumps(self.parent_inventory));(parent/'build_status.json').write_text(json.dumps({s:{'status':'PASS'}for s in CHILD_STAGES}))
            (parent/'parent_lineage.json').write_text('{}');(parent/'frozen_metadata.json').write_text(json.dumps({'revision':'source-graph','manifest':self.parent_inventory}))
            receipt={'schema':'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1','pass':True,'complete':True,'build_id':'owned-'+name,'revision':'c933','source_graph_revision':'source-graph','ended_utc':'historical','required_stages':list(CHILD_STAGES),'database':'/no-clean-host/c933-'+name+'.sqlite','started_fingerprints_sha256':portable.digest(parent/'started_fingerprints.json'),'build_status_sha256':portable.digest(parent/'build_status.json')}
            source_receipt=parent/'build_complete.json';source_receipt.write_text(json.dumps(receipt))
            seal={'sha256':'c933-whole','database_revision':'c933','database':receipt['database'],'integrity_check':['ok'],**{k:True for k in('pass','complete','integrity_pass','file_unchanged_during_checks','all_frozen_inputs_and_recipes_checked')}}
            integrity=folder/'parent_integrity.json';integrity.write_text(json.dumps(seal))
            lineage={'schema':'FINEATLAS_REPAIR_PARENT_LINEAGE_V1','resumed_build_id':'child-'+name,'resumed_revision':'final','parent_build_id':'owned-'+name,'parent_source_inode':[2049,index+10],'parent_revision':'c933','parent_database':receipt['database'],'parent_database_sha256':'c933-whole','parent_integrity_sha256':portable.digest(integrity),'parent_receipt_sha256':portable.digest(source_receipt)}
            (folder/'parent_lineage.json').write_text(json.dumps(lineage));(folder/'started_fingerprints.json').write_text(json.dumps(self.inventory))
            status={s:{'status':'PASS'}for s in portable.STAGES};status[portable.STAGES[0]]['result']={k:lineage[k]for k in ('parent_database_sha256','parent_integrity_sha256','parent_receipt_sha256','parent_build_id','parent_revision')};(folder/'build_status.json').write_text(json.dumps(status))
            child={'schema':'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1','pass':True,'complete':True,'build_id':lineage['resumed_build_id'],'revision':'final','ended_utc':'complete','parent_build_id':lineage['parent_build_id'],'parent_source_inode':lineage['parent_source_inode'],'parent_lineage_sha256':portable.digest(folder/'parent_lineage.json'),'required_stages':list(portable.STAGES),'started_fingerprints_sha256':portable.digest(folder/'started_fingerprints.json'),'build_status_sha256':portable.digest(folder/'build_status.json')};(folder/'build_complete.json').write_text(json.dumps(child))
            files={str(p.relative_to(folder)):{'member':str(p.relative_to(self.root)),'sha256':portable.digest(p)}for p in folder.rglob('*')if p.is_file()}
            rows.append({'name':name,'files':files,'source_parent_revision':'c933','source_parent_build_id':receipt['build_id'],'source_parent_whole_sha256':'c933-whole'})
        self.proof={'schema':portable.SCHEMA,'pass':True,'candidate_revision':'final','candidate_sha256':'final-sha','current_host_actual_inodes_checked':True,'children':rows,'original_lineage_validator_sha256':portable.digest(Path(portable.__file__).with_name('resume_structure_repairs.py')),'actual_local_physical_parent_audit':{'pass':True,'parent_build_ids':['owned-primary','owned-reproduction'],'resumed_build_ids':['child-primary','child-reproduction'],'distinct_source_inodes':True,'parent_revision':'c933'}}
        self.save()
    def save(self):(self.root/'builds/build-independence.json').write_text(json.dumps(self.proof))
    def validate(self):return portable.validate_portable_parent_independence(self.support,self.root/'builds/primary/build_complete.json',self.root/'builds/reproduction/build_complete.json',self.accepted)
    def test_closed_c933_history_verifies_without_opening_any_host_database(self):
        result=self.validate();self.assertFalse(result['physical_parent_inodes_rechecked_here']);self.assertTrue(result['immutable_historical_lineage_bytes_checked'])
    def test_package_uses_final_six_stage_children_even_when_eight_stage_lineage_keys_exist(self):
        config={};output=self.root/'new-package';output.mkdir()
        for name in ('primary','reproduction'):
            folder=self.root/'builds'/name
            config[name+'_build']=str(folder/'build_complete.json')
            config['lineage_'+name+'_build']=str(folder/'source-parent/build_complete.json')
            config[name+'_parent_build']=str(folder/'source-parent/build_complete.json')
            config['complete_type_'+name+'_parent_integrity']=str(folder/'parent_integrity.json')
        def binding(cfg,name,path,complete):
            self.assertEqual(Path(path),Path(config[name+'_build']))
            return json.loads(Path(cfg[name+'_parent_build']).read_text()),json.loads(Path(cfg['complete_type_'+name+'_parent_integrity']).read_text())
        with patch.object(portable,'validate_resumed_parent_independence',return_value=self.proof['actual_local_physical_parent_audit'])as independence,patch.object(portable,'require_source_parent_binding',side_effect=binding):
            members=portable.package_lineage_members(config,output,self.accepted)
        independence.assert_called_once_with(Path(config['primary_build']),Path(config['reproduction_build']))
        self.assertEqual(members['builds/primary/build_complete.json'],Path(config['primary_build']))
        self.assertEqual(members['builds/primary/source-parent/build_complete.json'],Path(config['lineage_primary_build']))

    def test_old_owned_stage_receipt_cannot_impersonate_final_child(self):
        path=self.root/'builds/primary/build_complete.json';value=json.loads(path.read_text());value['required_stages']=list(CHILD_STAGES);path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.validate()
    def test_stale3445_parent_binding_is_rejected(self):
        self.proof['children'][0]['source_parent_revision']='3445';self.save()
        with self.assertRaises(ValueError):self.validate()
    def test_validly_rehashed_child_inventory_cannot_replace_accepted_implementation(self):
        folder=self.root/'builds/primary';inventory=json.loads((folder/'started_fingerprints.json').read_text())
        inventory['code']['old-code']='changed';(folder/'started_fingerprints.json').write_text(json.dumps(inventory))
        receipt=json.loads((folder/'build_complete.json').read_text());receipt['started_fingerprints_sha256']=portable.digest(folder/'started_fingerprints.json');(folder/'build_complete.json').write_text(json.dumps(receipt))
        for name in ('started_fingerprints.json','build_complete.json'):
            self.proof['children'][0]['files'][name]['sha256']=portable.digest(folder/name)
        self.save()
        with self.assertRaisesRegex(ValueError,'accepted complete frozen inventory'):self.validate()
    def test_validly_rehashed_source_freeze_cannot_change_historical_graph(self):
        folder=self.root/'builds/primary';path=folder/'source-parent/frozen_metadata.json'
        value=json.loads(path.read_text());value['revision']='another-source-graph';path.write_text(json.dumps(value))
        self.proof['children'][0]['files']['source-parent/frozen_metadata.json']['sha256']=portable.digest(path);self.save()
        with self.assertRaisesRegex(ValueError,'actually frozen source-parent'):self.validate()
    def test_changed_complete_source_parent_or_whole_seal_is_rejected(self):
        path=self.root/'builds/primary/parent_integrity.json';value=json.loads(path.read_text());value['sha256']='changed';path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.validate()
    def test_shared_historical_parents_and_missing_physical_audit_are_rejected(self):
        self.proof['actual_local_physical_parent_audit']['distinct_source_inodes']=False;self.save()
        with self.assertRaises(ValueError):self.validate()
    def test_host_receipt_and_incomplete_child_states_are_rejected(self):
        with self.assertRaises(ValueError):portable.validate_portable_parent_independence(self.support,'/old-host/build.json',self.root/'builds/reproduction/build_complete.json',self.accepted)
        (self.root/'builds/primary/build_status.json').write_text('{}')
        with self.assertRaises(ValueError):self.validate()

if __name__=='__main__':unittest.main()
