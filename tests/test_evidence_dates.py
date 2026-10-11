import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import types
import unittest
from fineatlas.evidence_dates import apply_evidence_dates,prepare_evidence_dates
from fineatlas.migration import Migration


class EvidenceDateTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.baseline=self.root/'baseline.sqlite';self.db=self.root/'copy.sqlite'
        with sqlite3.connect(self.baseline) as c:
            c.execute('CREATE TABLE evidence(layer TEXT,evidence_id TEXT,source_name TEXT,source_uri TEXT,retrieved_utc TEXT,claim_type TEXT,payload TEXT,payload_sha256 TEXT,PRIMARY KEY(layer,evidence_id))')
            c.execute('INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?)',('old','original','source','uri','2026-10-05','FACT','{}','raw'))
        shutil.copyfile(self.baseline,self.db)
        self.c=sqlite3.connect(self.db);self.c.row_factory=sqlite3.Row
        self.c.execute('INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?)',('new','candidate','source','uri','2026-10-05','FACT','{}','new'))
        self.c.commit();self.inputs=self.root/'inputs';self.inputs.mkdir()
        self.path=self.inputs/'structure_evidence_dates.json'
        self.changes=[]
        self.m=types.SimpleNamespace(c=self.c,db=self.db,inputs=self.inputs,change=lambda *args:self.changes.append(args))

    def tearDown(self):self.c.close();self.temp.cleanup()

    def test_only_candidate_placeholder_changes_and_replays(self):
        result=prepare_evidence_dates(self.db,self.baseline,self.path)
        self.assertEqual(result['candidate_only_placeholder_dates'],1)
        self.assertEqual(apply_evidence_dates(self.m)['candidate_only_dates_corrected'],1)
        self.assertIsNone(self.c.execute("SELECT retrieved_utc FROM evidence WHERE evidence_id='candidate'").fetchone()[0])
        self.assertEqual(self.c.execute("SELECT retrieved_utc FROM evidence WHERE evidence_id='original'").fetchone()[0],'2026-10-05')
        self.assertEqual(apply_evidence_dates(self.m)['already_correct'],1)
        self.assertEqual(len(self.changes),1)

    def test_injected_historical_row_is_rejected(self):
        prepare_evidence_dates(self.db,self.baseline,self.path)
        payload=json.loads(self.path.read_text())
        payload['rows']=[dict(self.c.execute("SELECT * FROM evidence WHERE evidence_id='original'").fetchone())]
        self.path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError,'historical source evidence'):apply_evidence_dates(self.m)
        self.assertEqual(self.c.execute("SELECT retrieved_utc FROM evidence WHERE evidence_id='original'").fetchone()[0],'2026-10-05')

    def test_no_default_source_retrieval_date_is_invented(self):
        eid=Migration.evidence(self.m,'new source','uri',{'basis':'local retained record review'})
        self.assertIsNone(self.c.execute('SELECT retrieved_utc FROM evidence WHERE evidence_id=?',(eid,)).fetchone()[0])
        explicit=Migration.evidence(self.m,'new source','uri',{'basis':'actual download','retrieved_utc':'2026-10-09T11:00:00Z'})
        self.assertEqual(self.c.execute('SELECT retrieved_utc FROM evidence WHERE evidence_id=?',(explicit,)).fetchone()[0],'2026-10-09T11:00:00Z')


if __name__=='__main__':unittest.main()
