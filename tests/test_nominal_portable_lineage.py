"""Source9 historical evidence must preserve both actual parent generations."""
import json
from pathlib import Path
import shutil
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import portable_nominal_structure_lineage as nominal
import test_complete_portable_lineage as complete_fixture


class NominalThreeGenerationControls(unittest.TestCase):
    def setUp(self):
        self.old=complete_fixture.CompletePortableLineageControls();self.old.setUp();self.addCleanup(self.old.doCleanups)
        self.root=self.old.root;self.support=SimpleNamespace(root=self.root)
        foundation=self.root/'source8-foundation';foundation.mkdir();shutil.move(str(self.root/'builds'),str(foundation/'builds'))
        self.foundation=foundation;self.foundation_proof=self.old.proof
        for name in ('primary','reproduction'):
            folder=foundation/'builds'/name;path=folder/'build_complete.json';value=json.loads(path.read_text())
            value['source_graph_revision']='source8-graph';value['database']='/no-public-host/source8-'+name+'.sqlite'
            path.write_text(json.dumps(value));(folder/'frozen_metadata.json').write_text(json.dumps({'revision':'source8-graph','manifest':self.old.inventory}))
            row=next(row for row in self.foundation_proof['children']if row['name']==name)
            for file in folder.rglob('*'):
                if file.is_file():row['files'][str(file.relative_to(folder))]={'member':str(file.relative_to(foundation)),'sha256':nominal.digest(file)}
        (foundation/'builds/build-independence.json').write_text(json.dumps(self.foundation_proof))
        self.inventory={group:{**values}for group,values in self.old.inventory.items()};self.inventory['inputs']['nominal-new-input']='nominal-source-sha'
        self.accepted={'database_revision':'nominal-final','database_sha256':'nominal-final-sha','fingerprints':self.inventory}
        rows=[]
        for index,name in enumerate(('primary','reproduction')):
            folder=self.root/'builds'/name;parent=folder/'source-parent';parent.mkdir(parents=True)
            source=foundation/'builds'/name
            for filename in ('build_complete.json','parent_lineage.json','started_fingerprints.json','build_status.json','frozen_metadata.json'):
                shutil.copyfile(source/filename,parent/filename)
            parent_value=json.loads((parent/'build_complete.json').read_text())
            seal={'database':parent_value['database'],'database_revision':'final','sha256':'final-sha','integrity_check':['ok'],**{key:True for key in ('pass','complete','integrity_pass','file_unchanged_during_checks','all_frozen_inputs_and_recipes_checked')}}
            (folder/'parent_integrity.json').write_text(json.dumps(seal))
            lineage={'schema':'FINEATLAS_REPAIR_PARENT_LINEAGE_V1','resumed_build_id':'nominal-'+name,'resumed_revision':'nominal-final',
                'parent_build_id':parent_value['build_id'],'parent_revision':'final','parent_database':parent_value['database'],
                'parent_source_inode':[2049,index+20],'parent_database_sha256':'final-sha',
                'parent_integrity_sha256':nominal.digest(folder/'parent_integrity.json'),'parent_receipt_sha256':nominal.digest(parent/'build_complete.json')}
            (folder/'parent_lineage.json').write_text(json.dumps(lineage));(folder/'started_fingerprints.json').write_text(json.dumps(self.inventory))
            states={stage:{'status':'PASS'}for stage in nominal.STAGES};states[nominal.STAGES[0]]['result']={key:lineage[key]for key in ('parent_database_sha256','parent_integrity_sha256','parent_receipt_sha256','parent_build_id','parent_revision')}
            (folder/'build_status.json').write_text(json.dumps(states))
            child={'schema':'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1','complete':True,'pass':True,'build_id':'nominal-'+name,'revision':'nominal-final','ended_utc':'complete',
                'parent_build_id':lineage['parent_build_id'],'parent_source_inode':lineage['parent_source_inode'],'required_stages':list(nominal.STAGES),
                **{filename+'_sha256':nominal.digest(folder/(filename+'.json'))for filename in ('parent_lineage','started_fingerprints','build_status')}}
            (folder/'build_complete.json').write_text(json.dumps(child))
            rows.append({'name':name,'files':{str(file.relative_to(folder)):{'member':str(file.relative_to(self.root)),'sha256':nominal.digest(file)}for file in folder.rglob('*')if file.is_file()},
                'source_parent_build_id':parent_value['build_id'],'source_parent_revision':'final','source_parent_whole_sha256':'final-sha'})
        self.proof={'schema':nominal.SCHEMA,'pass':True,'candidate_revision':'nominal-final','candidate_sha256':'nominal-final-sha','current_host_actual_inodes_checked':True,
            'original_lineage_validator_sha256':nominal.digest(Path(nominal.__file__).with_name('resume_structure_repairs.py')),'children':rows,
            'actual_local_physical_parent_audit':{'pass':True,'parent_build_ids':['child-primary','child-reproduction'],'resumed_build_ids':['nominal-primary','nominal-reproduction'],'distinct_source_inodes':True,'parent_revision':'final'},
            'source8_foundation':{'accepted':self.old.accepted,'proof_sha256':nominal.digest(foundation/'builds/build-independence.json')}}
        self.save()
    def save(self):(self.root/'builds/build-independence.json').write_text(json.dumps(self.proof))
    def validate(self):return nominal.validate_portable_parent_independence(self.support,self.root/'builds/primary/build_complete.json',self.root/'builds/reproduction/build_complete.json',self.accepted)
    def test_all_three_closed_generations_verify_without_opening_host_databases(self):
        value=self.validate();self.assertFalse(value['physical_parent_inodes_rechecked_here']);self.assertTrue(value['complete_type_parent_historical_ancestry']['pass'])
    def test_old_source8_six_stage_recipe_cannot_impersonate_nominal_six_stage_recipe(self):
        path=self.root/'builds/primary/build_complete.json';value=json.loads(path.read_text());value['required_stages']=list(nominal.require_complete_type_build(self.foundation/'builds/primary/build_complete.json')['required_stages']);path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.validate()
    def test_missing_or_modified_c933_eight_stage_ancestry_is_rejected(self):
        (self.foundation/'builds/primary/source-parent/frozen_metadata.json').write_text('{}')
        with self.assertRaises(ValueError):self.validate()
    def test_validly_rehashed_current_implementation_cannot_replace_accepted_final_inventory(self):
        path=self.root/'builds/primary/started_fingerprints.json';value=json.loads(path.read_text());value['code']['old-code']='replacement';path.write_text(json.dumps(value))
        receipt=path.with_name('build_complete.json');value=json.loads(receipt.read_text());value['started_fingerprints_sha256']=nominal.digest(path);receipt.write_text(json.dumps(value))
        for filename in ('started_fingerprints.json','build_complete.json'):self.proof['children'][0]['files'][filename]['sha256']=nominal.digest(path.with_name(filename))
        self.save()
        with self.assertRaisesRegex(ValueError,'accepted complete frozen inventory'):self.validate()
    def test_shared_direct_source8_parents_are_rejected(self):
        self.proof['actual_local_physical_parent_audit']['distinct_source_inodes']=False;self.save()
        with self.assertRaises(ValueError):self.validate()
    def test_missing_actual_local_parent_integrity_proof_is_rejected(self):
        self.proof['actual_local_physical_parent_audit']['pass']=False;self.save()
        with self.assertRaises(ValueError):self.validate()
    def test_public_receipt_cannot_borrow_host_path(self):
        with self.assertRaises(ValueError):nominal.validate_portable_parent_independence(self.support,'/host/source8/build_complete.json',self.root/'builds/reproduction/build_complete.json',self.accepted)
    def test_ancestor_inventory_retains_its_original_candidate_identity(self):
        self.assertEqual(self.proof['source8_foundation']['accepted']['database_revision'],'final');self.assertNotEqual(self.accepted['database_revision'],'final')
        self.validate()
    def test_foundation_candidate_sha_cannot_differ_from_direct_source8_whole_sha(self):
        self.proof['source8_foundation']['accepted']={**self.old.accepted,'database_sha256':'unrelated-source8-sha'};self.save()
        with self.assertRaises(ValueError):self.validate()
    def test_configuration_binding_does_not_replace_c933_or_mutate_original_keys(self):
        config={'primary_build':'source9-p','reproduction_build':'source9-r','primary_parent_build':'source8-p','reproduction_parent_build':'source8-r',
            'nominal_primary_parent_build':'source8-p','nominal_reproduction_parent_build':'source8-r',
            'lineage_primary_build':'c933-p','lineage_reproduction_build':'c933-r','primary_parent_integrity':'3445-p'}
        result=nominal.source8_config(config);self.assertEqual(result['primary_build'],'source8-p');self.assertEqual(result['primary_parent_build'],'c933-p')
        self.assertEqual(config['primary_build'],'source9-p');self.assertEqual(config['primary_parent_build'],'source8-p');self.assertEqual(result['primary_parent_integrity'],'3445-p')
        config['nominal_primary_parent_build']='wrong-source8-p'
        with self.assertRaises(ValueError):nominal.source8_config(config)

if __name__=='__main__':unittest.main()
