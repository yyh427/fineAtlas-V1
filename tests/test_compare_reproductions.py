"""Real CLI regressions for independent artifact/schema/content comparison."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts/compare_reproductions.py'


class ReproductionComparisonTests(unittest.TestCase):
    def setUp(self):
        base=ROOT.parent/'tmp';base.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='compare-reproduction-test-',dir=base)
        self.work=Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def database(self, name, proof='same', ordinary_prefix=False, fts=False, seconds=1):
        path=self.work/name
        with sqlite3.connect(path) as c:
            c.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)')
            c.execute('INSERT INTO metadata VALUES(?,?)',('usability_view_statistics',json.dumps({'taxonomy':{'seconds':seconds,'nodes':1}})))
            c.execute('CREATE TABLE source_rows(uid TEXT PRIMARY KEY,proof TEXT)')
            c.execute('INSERT INTO source_rows VALUES(?,?)',('source:1','same'))
            if ordinary_prefix:
                c.execute('CREATE TABLE alias_search_review(uid INTEGER PRIMARY KEY,proof TEXT)')
                c.execute('INSERT INTO alias_search_review VALUES(1,?)',(proof,))
            if fts:
                c.execute('CREATE VIRTUAL TABLE alias_search USING fts5(name)')
                c.execute('INSERT INTO alias_search VALUES(?)',(proof,))
                # Resembles a real shadow name but SQLite says ordinary table.
                c.execute('CREATE TABLE alias_search_proof(uid INTEGER PRIMARY KEY,proof TEXT)')
                c.execute('INSERT INTO alias_search_proof VALUES(1,?)',('same',))
        return path

    def run_compare(self, left, right, optimize=False, output=None):
        args=[sys.executable]+(['-O'] if optimize else [])+[str(SCRIPT),'--database',str(left),'--reproduction',str(right),'--output',str(output or self.work/'result.json')]
        result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        return result

    def test_ordinary_alias_search_prefix_difference_rejected(self):
        a=self.database('a.sqlite','first',True);b=self.database('b.sqlite','second',True)
        p=self.run_compare(a,b)
        self.assertNotEqual(p.returncode,0,p.stdout)
        r=json.loads((self.work/'result.json').read_text())
        self.assertFalse(r['alias_search_review']['pass'])
        self.assertIn('alias_search_review',r['content_inventory']['compared_content_tables'])

    def test_same_file_hardlink_and_symlink_rejected(self):
        a=self.database('a.sqlite');b=self.work/'hardlink.sqlite';os.link(a,b)
        s=self.work/'symlink.sqlite';s.symlink_to(a)
        for p in (a,b,s):
            result=self.run_compare(a,p)
            self.assertNotEqual(result.returncode,0,result.stdout)
            self.assertIn('distinct files and inodes',result.stdout)

    def test_optimization_rejected(self):
        a=self.database('a.sqlite');b=self.database('b.sqlite')
        p=self.run_compare(a,b,True)
        self.assertNotEqual(p.returncode,0,p.stdout)
        self.assertIn('optimization is forbidden',p.stdout)

    def test_actual_fts_storage_excluded_ordinary_similar_name_compared(self):
        a=self.database('a.sqlite','first index',fts=True);b=self.database('b.sqlite','different index',fts=True)
        p=self.run_compare(a,b)
        self.assertEqual(p.returncode,0,p.stdout)
        r=json.loads((self.work/'result.json').read_text());account=r['content_inventory']
        self.assertIn('alias_search',account['excluded_content_tables'])
        self.assertIn('alias_search_data',account['excluded_content_tables'])
        self.assertIn('alias_search_proof',account['compared_content_tables'])
        self.assertEqual(account['actual_table_count'],account['compared_content_count']+account['excluded_content_count'])
        self.assertTrue(all(row['pass'] for row in r.values()))

    def test_complete_schema_inventory_rejects_added_table(self):
        a=self.database('a.sqlite');b=self.database('b.sqlite')
        with sqlite3.connect(b) as c:c.execute('CREATE TABLE late_source(uid TEXT PRIMARY KEY)')
        p=self.run_compare(a,b)
        self.assertNotEqual(p.returncode,0,p.stdout)
        r=json.loads((self.work/'result.json').read_text())
        self.assertFalse(r['schema_inventory']['pass'])
        self.assertEqual(r['schema_inventory']['reproduction_only_tables'],['late_source'])

    def test_only_measured_view_seconds_are_runtime_exception(self):
        a=self.database('a.sqlite',seconds=1);b=self.database('b.sqlite',seconds=3)
        self.assertEqual(self.run_compare(a,b).returncode,0)
        with sqlite3.connect(b) as c:
            c.execute('UPDATE metadata SET value=? WHERE key=?',(json.dumps({'taxonomy':{'seconds':3,'nodes':2}}),'usability_view_statistics'))
        p=self.run_compare(a,b)
        self.assertNotEqual(p.returncode,0,p.stdout)
        self.assertFalse(json.loads((self.work/'result.json').read_text())['view_statistics_without_runtime']['pass'])

    def test_output_cannot_overwrite_input_direct_hardlink_or_symlink(self):
        a=self.database('a.sqlite');b=self.database('b.sqlite');before=a.read_bytes()
        h=self.work/'output-hardlink';os.link(a,h)
        s=self.work/'output-symlink';s.symlink_to(a)
        for output in (a,h,s):
            p=self.run_compare(a,b,output=output)
            self.assertNotEqual(p.returncode,0,p.stdout)
            self.assertEqual(before,a.read_bytes())

    def test_key_only_table_different_identity_same_count_rejected(self):
        a=self.database('a.sqlite');b=self.database('b.sqlite')
        for db,uid in ((a,'source:left'),(b,'source:right')):
            with sqlite3.connect(db) as c:
                c.execute('CREATE TABLE identity_keys(uid TEXT PRIMARY KEY)')
                c.execute('INSERT INTO identity_keys VALUES(?)',(uid,))
        p=self.run_compare(a,b)
        self.assertNotEqual(p.returncode,0,p.stdout)
        self.assertFalse(json.loads((self.work/'result.json').read_text())['identity_keys']['pass'])

    def test_runtime_table_exclusions_are_explicit(self):
        a=self.database('a.sqlite');b=self.database('b.sqlite')
        for db,duration in ((a,1),(b,200)):
            with sqlite3.connect(db) as c:
                c.execute('CREATE TABLE usability_stages(stage TEXT PRIMARY KEY,runtime_seconds REAL)')
                c.execute('INSERT INTO usability_stages VALUES(?,?)',('rebuild',duration))
        p=self.run_compare(a,b)
        self.assertEqual(p.returncode,0,p.stdout)
        r=json.loads((self.work/'result.json').read_text())
        self.assertEqual(r['content_inventory']['excluded_content_tables']['usability_stages'],'EXPLICIT_MEASURED_RUNTIME_STAGE')

    def test_using_fts_in_quoted_virtual_name_does_not_prove_fts_module(self):
        a=self.database('a.sqlite');b=self.database('b.sqlite')
        for db,value in ((a,1),(b,2)):
            with sqlite3.connect(db) as c:
                c.execute('CREATE VIRTUAL TABLE "ordinary USING fts5" USING rtree(id,min_x,max_x)')
                c.execute('INSERT INTO "ordinary USING fts5" VALUES(1,?,?)',(value,value+1))
        p=self.run_compare(a,b)
        self.assertNotEqual(p.returncode,0,p.stdout)
        r=json.loads((self.work/'result.json').read_text())
        self.assertIn('ordinary USING fts5',r['content_inventory']['compared_content_tables'])
        self.assertNotIn('ordinary USING fts5',r['content_inventory']['excluded_content_tables'])

    def test_non_fts_virtual_and_shadow_are_not_name_excluded(self):
        a=self.database('a.sqlite');b=self.database('b.sqlite')
        for db,value in ((a,1),(b,2)):
            with sqlite3.connect(db) as c:
                c.execute('CREATE VIRTUAL TABLE alias_search_spatial USING rtree(id,min_x,max_x)')
                c.execute('INSERT INTO alias_search_spatial VALUES(1,?,?)',(value,value+1))
        p=self.run_compare(a,b)
        self.assertNotEqual(p.returncode,0,p.stdout)
        r=json.loads((self.work/'result.json').read_text())
        self.assertIn('alias_search_spatial',r['content_inventory']['compared_content_tables'])
        self.assertFalse(r['alias_search_spatial']['pass'])


if __name__ == '__main__':
    unittest.main()
