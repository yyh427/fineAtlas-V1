"""Four-generation public proofs keep the three-generation candidate unchanged."""
import json
from pathlib import Path
import shutil
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import portable_nominal_formal_lineage as formal
import test_nominal_portable_lineage as candidate_fixture


class FourGenerationPortableControls(unittest.TestCase):
    def setUp(self):
        self.old=candidate_fixture.NominalThreeGenerationControls();self.old.setUp();self.addCleanup(self.old.doCleanups)
        self.root=self.old.root;foundation=self.root/'source9-foundation';foundation.mkdir()
        shutil.move(str(self.root/'builds'),str(foundation/'builds'));shutil.move(str(self.root/'source8-foundation'),str(foundation/'source8-foundation'))
        self.inventory={group:{**values}for group,values in self.old.inventory.items()}
        self.stable_inventory={group:{**values}for group,values in self.old.inventory.items()}
        texts={'__init__.py':'from .api import FineAtlas\n__version__ = "1.11.0rc1"\n','pyproject.toml':'[project]\nname = "fineatlas"\nversion = "1.11.0rc1"\n','review_release.json':json.dumps({'version':'v1.11.0rc1','facts':'unchanged'})}
        mapping={'__init__.py':('code','src/fineatlas/__init__.py'),'pyproject.toml':('packaging','pyproject.toml'),'review_release.json':('inputs','review_release.json')}
        for prefix,inventory in (('source9',self.inventory),('formal',self.stable_inventory)):
            directory=self.root/'versions'/prefix;directory.mkdir(parents=True)
            for name,text in texts.items():
                path=directory/name;path.write_text(text if prefix=='source9'else text.replace('1.11.0rc1','1.11.0'))
                group,key=mapping[name];inventory[group][key]=formal.digest(path)
        candidate_proof=self.old.proof
        for name in ('primary','reproduction'):
            folder=foundation/'builds'/name;(folder/'started_fingerprints.json').write_text(json.dumps(self.inventory))
            child=json.loads((folder/'build_complete.json').read_text());child['started_fingerprints_sha256']=formal.digest(folder/'started_fingerprints.json');(folder/'build_complete.json').write_text(json.dumps(child))
            (folder/'frozen_metadata.json').write_text(json.dumps({'revision':'source9-graph','manifest':{**self.inventory,'schema':'source9-semantic'}}))
            selected=next(row for row in candidate_proof['children']if row['name']==name)
            for filename in ('started_fingerprints.json','build_complete.json'):
                selected['files'][filename]['sha256']=formal.digest(folder/filename)
        (foundation/'builds/build-independence.json').write_text(json.dumps(candidate_proof))
        accepted_candidate={**self.old.accepted,'fingerprints':self.inventory}
        self.accepted={'database_revision':'formal-final','database_sha256':'formal-primary-sha','fingerprints':self.stable_inventory}
        self.records=[]
        for index,name in enumerate(('primary','reproduction')):
            folder=self.root/'builds'/name;folder.mkdir(parents=True)
            source9=foundation/'builds'/name
            parent=json.loads((source9/'build_complete.json').read_text());whole='nominal-final-sha'if name=='primary'else'nominal-repro-sha'
            seal={'pass':True,'complete':True,'integrity_pass':True,'integrity_check':['ok'],'file_unchanged_during_checks':True,'all_frozen_inputs_and_recipes_checked':True,'database_revision':'nominal-final','sha256':whole}
            (folder/'source9_integrity.json').write_text(json.dumps(seal))
            states={stage:{'status':'PASS','result':{}}for stage in formal.STAGES};states[formal.STAGES[0]]['result']={'parent_revision':'nominal-final','source_sha256':whole,'graphs_recomputed':False};states[formal.STAGES[-1]]['result']={'revision':'formal-final','source_unchanged':True}
            (folder/'build_status.json').write_text(json.dumps(states));(folder/'started_fingerprints.json').write_text(json.dumps(self.stable_inventory))
            source_freeze=json.loads((source9/'frozen_metadata.json').read_text())['manifest']
            promotion={'release':'v1.11.0','revision':'formal-semantic','manifest':{**self.stable_inventory,'promotion':{'parent_candidate_revision':'nominal-final','parent_frozen_manifest_sha256':formal.canonical_hash(source_freeze),'semantic_graph_recomputed':False,'browse_indexes_rebuilt':True}}}
            (folder/'promotion_metadata.json').write_text(json.dumps(promotion));(folder/'promotion_complete.json').write_text(json.dumps({'release':'v1.11.0','complete':True,'pass':True,'source_unchanged':True,'database_revision':'formal-final','source_sha256':whole,'requires_full_new_acceptance_and_public_download':True}))
            receipt={'schema':'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1','complete':True,'pass':True,'build_id':'formal-'+name,'revision':'formal-final','release':'v1.11.0','ended_utc':'historical','semantic_reuse_only':True,'requires_independent_acceptance':True,
                **{filename+'_sha256':formal.digest(folder/(filename+'.json'))for filename in ('build_status','started_fingerprints')}}
            (folder/'build_complete.json').write_text(json.dumps(receipt))
            self.records.append({'name':name,'files':{path.name:{'member':str(path.relative_to(self.root)),'sha256':formal.digest(path)}for path in folder.iterdir()},
                'formal_build_id':'formal-'+name,'source9_build_id':parent['build_id'],'source9_revision':'nominal-final','source9_whole_sha256':whole,
                'actual_source_inode':[2049,index+40],'actual_formal_inode':[2049,index+50]})
        self.proof={'schema':formal.SCHEMA,'pass':True,'formal_revision':'formal-final','formal_sha256':'formal-primary-sha','actual_local_four_distinct_inodes_checked':True,
            'version_only_promoter_sha256':formal.digest(Path(formal.__file__).with_name('promote_structure_stable.py')),'children':self.records,'source9_accepted':accepted_candidate,
            'source9_foundation_proof_sha256':formal.digest(foundation/'builds/build-independence.json')}
        self.support=SimpleNamespace(root=self.root);self.save()
    def save(self):(self.root/'builds/formal-four-generation-independence.json').write_text(json.dumps(self.proof))
    def validate(self):return formal.validate_portable_parent_independence(self.support,self.root/'builds/primary/build_complete.json',self.root/'builds/reproduction/build_complete.json',self.accepted)
    def test_actual_four_stage_pair_with_unchanged_source9_source8_and_c933_proofs_passes(self):
        result=self.validate();self.assertFalse(result['physical_parent_inodes_rechecked_here']);self.assertTrue(result['historical_source9_three_generation_proof']['pass'])
    def test_missing_candidate_or_c933_foundation_is_rejected(self):
        (self.root/'source9-foundation/source8-foundation/builds/primary/source-parent/frozen_metadata.json').unlink()
        with self.assertRaises((ValueError,FileNotFoundError)):self.validate()
    def test_two_formal_promotions_cannot_reuse_one_candidate_inode(self):
        self.proof['children'][1]['actual_source_inode']=self.proof['children'][0]['actual_source_inode'];self.save()
        with self.assertRaises(ValueError):self.validate()
    def test_validly_rehashed_formal_init_logic_change_is_rejected(self):
        path=self.root/'versions/formal/__init__.py';path.write_text(path.read_text()+'FineAtlas = None\n');self.accepted['fingerprints']['code']['src/fineatlas/__init__.py']=formal.digest(path)
        folder=self.root/'builds/primary';(folder/'started_fingerprints.json').write_text(json.dumps(self.stable_inventory));receipt=json.loads((folder/'build_complete.json').read_text());receipt['started_fingerprints_sha256']=formal.digest(folder/'started_fingerprints.json');(folder/'build_complete.json').write_text(json.dumps(receipt))
        for name in ('started_fingerprints.json','build_complete.json'):self.proof['children'][0]['files'][name]['sha256']=formal.digest(folder/name)
        self.save()
        with self.assertRaises(ValueError):self.validate()
    def test_candidate_revision_or_original_whole_sha_cannot_be_rebound_to_formal(self):
        self.proof['source9_accepted']['database_revision']='formal-final';self.save()
        with self.assertRaises(ValueError):self.validate()
    def test_public_proof_cannot_use_real_or_missing_host_path(self):
        with self.assertRaises(ValueError):formal.validate_portable_parent_independence(self.support,'/historical/host/build_complete.json',self.root/'builds/reproduction/build_complete.json',self.accepted)

if __name__=='__main__':unittest.main()
