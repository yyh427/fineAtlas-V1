"""Primary scope repairs must not spread through broad identity/source groups."""
import hashlib,json,pathlib,sqlite3,subprocess,sys,tempfile,unittest

class ExactPrimaryScopeTest(unittest.TestCase):
    def run_preview(self,extra_peer=False,old_role='MODEL',new_role='BIOLOGICAL_VARIANT',old_label='Cultivar A'):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);db=root/'db.sqlite';inputs=root/'inputs';inputs.mkdir();output=root/'preview.jsonl'
            with sqlite3.connect(db) as c:
                c.execute('CREATE TABLE nodes(uid TEXT,component_id INTEGER,label TEXT,data TEXT,rank TEXT,source TEXT,visibility TEXT)')
                c.execute('CREATE TABLE node_profiles(uid TEXT,node_kind TEXT)')
                c.executemany('INSERT INTO nodes VALUES(?,?,?,?,?,?,?)',[
                    ('wikidata:Q1',1,old_label,'{}','','wikidata','ACTIVE'),
                    ('wikidata-v4:Q1',1,'Cultivar A','{}','','wikidata','ACTIVE')])
                c.executemany('INSERT INTO node_profiles VALUES(?,?)',[('wikidata:Q1',old_role),('wikidata-v4:Q1',new_role)])
                if extra_peer:c.execute("INSERT INTO nodes VALUES('faa-aircraft:1',1,'other','{}','model','faa','ACTIVE')")
            rule={'op':'role','uid':'wikidata-v4:Q1','role':new_role,'uri':'https://www.wikidata.org/wiki/Q1','source':'Frozen primary scope','proof':{'basis':'DEFINED_PRIMARY_ORGANISM_UNIT_WITH_CONSERVATIVE_NATIVE_SCOPE','primary_label':'Cultivar A','native_record_sha256':hashlib.sha256(b'{}').hexdigest(),'P31':['cultivar-unit'],'unit_rules':[{'definition':'Source-defined cultivar'}]}}
            (inputs/'unified_biological_units.jsonl').write_text(json.dumps(rule)+'\n')
            result=subprocess.run([sys.executable,str(pathlib.Path(__file__).resolve().parents[1]/'scripts/prepare_unified_same_qid_roles.py'),'--database',str(db),'--inputs',str(inputs),'--output',str(output)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            return [json.loads(s) for s in output.read_text().splitlines()],json.loads(output.with_suffix('.summary.json').read_text())

    def test_explicit_primary_cultivar_scope_corrects_historical_model_role(self):
        rows,summary=self.run_preview();self.assertEqual(rows[0]['uid'],'wikidata:Q1');self.assertEqual(rows[0]['role'],'BIOLOGICAL_VARIANT')
        self.assertEqual(summary['identity_groups_split_or_merged'],0)

    def test_different_native_identifier_is_never_reinterpreted_by_same_qid_rule(self):
        rows,summary=self.run_preview(extra_peer=True);self.assertEqual(rows,[]);self.assertIn('different source identifier',summary['reviews'][0]['reason'])

    def test_defined_model_unit_does_not_erase_established_family_scope(self):
        rows,summary=self.run_preview(old_role='MODEL_FAMILY',new_role='MODEL');self.assertEqual(rows,[]);self.assertIn('family scope',summary['reviews'][0]['reason'])

    def test_changed_source_scope_is_not_relabelled(self):
        rows,summary=self.run_preview(old_label='Different concept');self.assertEqual(rows,[]);self.assertIn('scope/name differs',summary['reviews'][0]['reason'])

if __name__=='__main__':unittest.main()
