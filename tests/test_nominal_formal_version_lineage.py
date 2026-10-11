"""Formal reuse must use actual four-stage evidence and exact version literals."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import portable_nominal_formal_lineage as formal
from structure_acceptance_contract import validate_independent_builds


class FormalVersionOnlyControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.fingerprints={'inputs':{'review_release.json':'old-input'},'code':{'src/fineatlas/__init__.py':'old-code'},'packaging':{'pyproject.toml':'old-package'}}
        states={stage:{'status':'PASS','result':{}}for stage in formal.STAGES}
        states[formal.STAGES[0]]['result']={'parent_revision':'source9','source_sha256':'source9-whole','graphs_recomputed':False}
        states[formal.STAGES[-1]]['result']={'source_unchanged':True,'revision':'formal-final'}
        (self.root/'build_status.json').write_text(json.dumps(states));(self.root/'started_fingerprints.json').write_text(json.dumps(self.fingerprints))
        self.promotion={'release':'v1.11.0','revision':'formal-semantic','manifest':{'promotion':{'parent_candidate_revision':'source9','semantic_graph_recomputed':False,'browse_indexes_rebuilt':True}}}
        (self.root/'promotion_metadata.json').write_text(json.dumps(self.promotion))
        complete={'complete':True,'pass':True,'release':'v1.11.0','source_unchanged':True,'source_sha256':'source9-whole','database_revision':'formal-final','requires_full_new_acceptance_and_public_download':True}
        (self.root/'promotion_complete.json').write_text(json.dumps(complete))
        self.receipt={'schema':'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1','complete':True,'pass':True,'release':'v1.11.0','database':'formal.sqlite','build_id':'formal-id','ended_utc':'done','revision':'formal-final','semantic_reuse_only':True,'requires_independent_acceptance':True,
            'started_fingerprints_sha256':formal.digest(self.root/'started_fingerprints.json'),'build_status_sha256':formal.digest(self.root/'build_status.json')}
        self.path=self.root/'build_complete.json';self.save()
    def save(self):self.path.write_text(json.dumps(self.receipt))
    def test_actual_original_four_stage_receipt_without_fake_required_stages_is_supported(self):
        answer=formal.require_formal_version_only_build(self.path);self.assertTrue(answer['semantic_reuse_only']);self.assertNotIn('required_stages',answer)
    def test_six_stage_nominal_receipt_cannot_impersonate_formal_receipt(self):
        self.receipt['required_stages']=['verify_complete_owned_type_parent_copy','nominal_design_scope_repairs','whole_graph_recomputation','freeze_metadata','browse_staging','embed_browse_indexes'];self.save()
        with self.assertRaises(ValueError):formal.require_formal_version_only_build(self.path)
    def test_semantic_recompute_or_source_change_is_rejected(self):
        states=json.loads((self.root/'build_status.json').read_text());states[formal.STAGES[0]]['result']['graphs_recomputed']=True
        (self.root/'build_status.json').write_text(json.dumps(states));self.receipt['build_status_sha256']=formal.digest(self.root/'build_status.json');self.save()
        with self.assertRaises(ValueError):formal.require_formal_version_only_build(self.path)
    def test_missing_stage_and_incomplete_fresh_acceptance_requirement_are_rejected(self):
        self.receipt['requires_independent_acceptance']=False;self.save()
        with self.assertRaises(ValueError):formal.require_formal_version_only_build(self.path)
        self.receipt['requires_independent_acceptance']=True;states=json.loads((self.root/'build_status.json').read_text());del states['browse_staging']
        (self.root/'build_status.json').write_text(json.dumps(states));self.receipt['build_status_sha256']=formal.digest(self.root/'build_status.json');self.save()
        with self.assertRaises(ValueError):formal.require_formal_version_only_build(self.path)
    def test_parent_revision_and_actual_promotion_completion_must_match(self):
        self.promotion['manifest']['promotion']['parent_candidate_revision']='another-source9';(self.root/'promotion_metadata.json').write_text(json.dumps(self.promotion))
        with self.assertRaises(ValueError):formal.require_formal_version_only_build(self.path)
    def literal_fixture(self):
        source={'__init__.py':'from .api import FineAtlas\n__version__ = "1.11.0rc1"\n','pyproject.toml':'[project]\nname = "fineatlas"\nversion = "1.11.0rc1"\n','review_release.json':json.dumps({'version':'v1.11.0rc1','scope':'unchanged'})}
        stable={name:text.replace('1.11.0rc1','1.11.0')for name,text in source.items()}
        old={'inputs':{},'code':{},'packaging':{}};new={'inputs':{},'code':{},'packaging':{}}
        mapping={'__init__.py':('code','src/fineatlas/__init__.py'),'pyproject.toml':('packaging','pyproject.toml'),'review_release.json':('inputs','review_release.json')}
        for prefix,records,inventory in [('source9',source,old),('formal',stable,new)]:
            directory=self.root/'versions'/prefix;directory.mkdir(parents=True)
            for name,text in records.items():
                path=directory/name;path.write_text(text);group,key=mapping[name];inventory[group][key]=formal.digest(path)
        return old,new
    def test_exact_portable_three_literal_version_changes_pass(self):
        old,new=self.literal_fixture();formal.validate_portable_version_literals(self.root,old,new,'v1.11.0')
    def test_validly_rehashed_sdk_logic_change_is_not_a_version_only_change(self):
        old,new=self.literal_fixture();path=self.root/'versions/formal/__init__.py';path.write_text(path.read_text()+'FineAtlas = None\n');new['code']['src/fineatlas/__init__.py']=formal.digest(path)
        with self.assertRaises(ValueError):formal.validate_portable_version_literals(self.root,old,new,'v1.11.0')
    def test_rehashed_packaging_dependency_change_is_rejected(self):
        old,new=self.literal_fixture();path=self.root/'versions/formal/pyproject.toml';path.write_text(path.read_text()+'dependencies = ["new-semantic-adapter"]\n');new['packaging']['pyproject.toml']=formal.digest(path)
        with self.assertRaises(ValueError):formal.validate_portable_version_literals(self.root,old,new,'v1.11.0')
    def test_rehashed_source_input_scope_change_is_rejected(self):
        old,new=self.literal_fixture();path=self.root/'versions/formal/review_release.json';path.write_text(json.dumps({'version':'v1.11.0','scope':'altered semantic evidence'}));new['inputs']['review_release.json']=formal.digest(path)
        with self.assertRaises(ValueError):formal.validate_portable_version_literals(self.root,old,new,'v1.11.0')
    def test_new_version_bytes_cannot_borrow_old_or_host_hash(self):
        old,new=self.literal_fixture();new['code']['src/fineatlas/__init__.py']=old['code']['src/fineatlas/__init__.py']
        with self.assertRaises(ValueError):formal.validate_portable_version_literals(self.root,old,new,'v1.11.0')

    def original_controller_fixture(self):
        """Use the exact original four-stage receipt contract, without six-stage fields."""
        primary=self.root/'primary.sqlite';primary.write_bytes(b'fixture-primary')
        reproduction=self.root/'reproduction.sqlite';reproduction.write_bytes(b'fixture-reproduction')
        self.receipt['database']=str(primary);self.save()
        other=self.root/'reproduction-build';other.mkdir()
        for name in ('build_status.json','started_fingerprints.json'):
            (other/name).write_bytes((self.root/name).read_bytes())
        row={**self.receipt,'database':str(reproduction),'build_id':'independent-formal-id'}
        (other/'build_complete.json').write_text(json.dumps(row))
        return primary,reproduction,self.path,other/'build_complete.json'

    def test_original_acceptance_controller_accepts_genuine_four_stage_receipt_format(self):
        paths=self.original_controller_fixture()
        result=validate_independent_builds(*paths,self.fingerprints)
        self.assertEqual(len(result),2)
        self.assertTrue(all(row['semantic_reuse_only']for row in result))
        self.assertTrue(all('required_stages'not in row for row in result))

    def test_original_controller_rejects_changed_started_inventory_even_if_receipt_rehashed(self):
        paths=self.original_controller_fixture();fingerprints=paths[3].with_name('started_fingerprints.json')
        fingerprints.write_text(json.dumps({'inputs':{},'code':{},'packaging':{}}))
        row=json.loads(paths[3].read_text());row['started_fingerprints_sha256']=formal.digest(fingerprints);paths[3].write_text(json.dumps(row))
        with self.assertRaises(ValueError):validate_independent_builds(*paths,self.fingerprints)

    def test_original_controller_rejects_copied_receipt_or_wrong_artifact_and_schema(self):
        for field,value in [('build_id','formal-id'),('database','missing.sqlite'),('schema','FAKE_FORMAL_V1')]:
            with self.subTest(field=field),tempfile.TemporaryDirectory()as tmp:
                paths=self.original_controller_fixture();row=json.loads(paths[3].read_text());row[field]=value;paths[3].write_text(json.dumps(row))
                with self.assertRaises(ValueError):validate_independent_builds(*paths,self.fingerprints)
                # A new independent receipt folder is required for each control.
                __import__('shutil').rmtree(paths[3].parent)

if __name__=='__main__':unittest.main()
