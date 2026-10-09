"""Native subclass declarations must not override conflicting concept scope."""
import json,pathlib,sqlite3,subprocess,sys,tempfile,unittest

class NativeFoodScopeTest(unittest.TestCase):
    def preview(self,qualified=False,named_instance=False,changed_label=False):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);db=root/'graph.sqlite'
            with sqlite3.connect(db) as c:
                c.execute('CREATE TABLE nodes(uid TEXT,label TEXT,source TEXT,rank TEXT,data TEXT,visibility TEXT,component_id INTEGER)')
                c.execute('CREATE TABLE node_profiles(uid TEXT,node_kind TEXT)')
                c.execute('CREATE TABLE view_paths(view TEXT,component_id INTEGER)')
                c.executemany('INSERT INTO nodes VALUES(?,?,?,?,?,?,?)',[('wikidata:Q2095','food','wikidata','class','{}','ACTIVE',1),('wikidata:Q1','Food kind','wikidata','unknown','{}','ACTIVE',2)])
                c.executemany('INSERT INTO node_profiles VALUES(?,?)',[('wikidata:Q2095','CLASS'),('wikidata:Q1','UNKNOWN')])
                c.execute("INSERT INTO view_paths VALUES('unified',1)")
            claim={'id':'Q1$claim','rank':'normal','mainsnak':{'datavalue':{'value':{'id':'Q2095'}}}}
            if qualified:claim['qualifiers']={'P518':[{'applies_to_part':True}]}
            primary={'entities':{'Q1':{'lastrevid':12,'labels':{'en':{'value':'Changed scope' if changed_label else 'Food kind'}},'claims':{'P279':[claim]}}}}
            facts={'accepted_food_concepts':{'Q1':{'definition':'A repeatable food preparation','url':'https://example.org/definition','concept_not_named_meal_instance':not named_instance}}}
            for name,x in [('primary.json',primary),('facts.json',facts)]:(root/name).write_text(json.dumps(x))
            output=root/'preview.jsonl';script=pathlib.Path(__file__).resolve().parents[1]/'scripts/prepare_unified_food_scope.py'
            r=subprocess.run([sys.executable,str(script),'--database',str(db),'--primary',str(root/'primary.json'),'--scope-facts',str(root/'facts.json'),'--output',str(output)],capture_output=True,text=True)
            return r,[json.loads(s) for s in output.read_text().splitlines()] if output.exists() else []

    def test_unqualified_classification_with_independent_kind_scope_is_native(self):
        result,rows=self.preview();self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(rows[1]['relation'],'NATIVE_CLASSIFICATION_PARENT');self.assertFalse(rows[1]['proof']['strict_IS_A_asserted'])

    def test_part_qualified_food_assertion_does_not_become_universal_subclass(self):
        result,rows=self.preview(qualified=True);self.assertNotEqual(result.returncode,0);self.assertEqual(rows,[])

    def test_named_meal_instance_is_not_promoted_to_class(self):
        result,rows=self.preview(named_instance=True);self.assertNotEqual(result.returncode,0);self.assertEqual(rows,[])

    def test_current_scope_change_is_not_silently_accepted(self):
        result,rows=self.preview(changed_label=True);self.assertNotEqual(result.returncode,0);self.assertEqual(rows,[])

if __name__=='__main__':unittest.main()
