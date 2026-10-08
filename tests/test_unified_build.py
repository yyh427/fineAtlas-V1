"""Cache diff materialization must equal a full frozen recomputation."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import subprocess
import sys
from fineatlas.unified_build import DERIVED_TABLES,ram_graphs

class RamMaterializationTest(unittest.TestCase):
    def test_changed_added_removed_and_null_rows_match_recomputed_tables(self):
        with tempfile.TemporaryDirectory() as folder:
            class Migration:
                def meta(self,key,value):
                    self.c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(key,json.dumps(value)))
                def graphs(self):
                    for table in DERIVED_TABLES:
                        self.c.execute('DELETE FROM '+table)
                        self.c.executemany('INSERT INTO '+table+' VALUES(?,?)',
                                           [('unchanged',None),('changed','new'),('added','new')])
                    self.c.commit()
                    return {'recomputation':'fixture'}
            m=Migration();m.out=Path(folder);m.c=sqlite3.connect(':memory:')
            m.c.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)')
            for table in DERIVED_TABLES:
                m.c.execute('CREATE TABLE '+table+'(key TEXT PRIMARY KEY,value TEXT) WITHOUT ROWID')
                m.c.executemany('INSERT INTO '+table+' VALUES(?,?)',
                               [('unchanged',None),('changed','old'),('removed','old')])
            m.c.commit()
            ram_graphs(m)
            for table in DERIVED_TABLES:
                self.assertEqual(m.c.execute('SELECT * FROM '+table+' ORDER BY key').fetchall(),
                                 [('added','new'),('changed','new'),('unchanged',None)])
            self.assertTrue(json.loads(m.c.execute("SELECT value FROM metadata WHERE key='unified_ready'").fetchone()[0]))
            m.c.close()


class FrozenBrowserApplicationTest(unittest.TestCase):
    def run_application(self,source_revision):
        with tempfile.TemporaryDirectory() as folder:
            candidate=Path(folder)/'candidate.sqlite';staging=Path(folder)/'index.sqlite'
            for path,metadata in ((candidate,{'database_revision':'graph-new','browse_parent_revision':'graph-new'}),
                                  (staging,{'schema':'FINEATLAS_BROWSE_INDEX_V1','browse_indexes_ready':True,
                                            'browse_source_revision':'graph-new','database_revision':'indexed-new',
                                            'browse_index_revision':'indexed-new'})):
                with sqlite3.connect(path) as c:
                    c.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)')
                    c.executemany('INSERT INTO metadata VALUES(?,?)',[(k,json.dumps(v)) for k,v in metadata.items()])
                    if path==staging:
                        c.execute('CREATE TABLE browse_fixture(uid TEXT PRIMARY KEY)')
                        c.execute("INSERT INTO browse_fixture VALUES('retained')")
            script=Path(__file__).resolve().parents[1]/'scripts/apply_browse_indexes.py'
            result=subprocess.run([sys.executable,str(script),'--database',str(candidate),
                                   '--staging',str(staging),'--source-revision',source_revision,
                                   '--output',str(Path(folder)/'report.json')],capture_output=True,text=True)
            with sqlite3.connect(candidate) as c:
                meta={k:json.loads(v) for k,v in c.execute('SELECT * FROM metadata')}
            return result,meta

    def test_graph_changing_candidate_uses_its_own_frozen_revision(self):
        result,meta=self.run_application('graph-new')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(meta['database_revision'],'indexed-new')
        self.assertTrue(meta['browse_indexes_ready'])

    def test_wrong_revision_cannot_attach_indexes(self):
        result,meta=self.run_application('different-graph')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(meta['database_revision'],'graph-new')

if __name__=='__main__':unittest.main()
