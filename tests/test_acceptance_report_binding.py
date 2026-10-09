"""Reports cannot be relabeled as a different candidate or compiled before acceptance."""
import hashlib,json,sqlite3,subprocess,sys,tempfile,unittest
from pathlib import Path
SCRIPT=Path(__file__).resolve().parents[1]/'scripts/report_unified_results.py'
class AcceptanceBindingTests(unittest.TestCase):
 def rejected(self,override,job_change=None):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);db=root/'candidate.sqlite';reports=root/'reports';reports.mkdir()
   with sqlite3.connect(db) as c:
    c.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)')
    c.executemany('INSERT INTO metadata VALUES(?,?)',[(k,json.dumps(v)) for k,v in {'release':'v1.10.1-repair-review','database_revision':'exact-revision'}.items()])
    c.execute('CREATE TABLE domain_registry(canonical_name TEXT,root_uids TEXT)')
   receipt={'all_pass':True,'jobs':{'domains':{'pass':True}},'release':'v1.10.1-repair-review','database_revision':'exact-revision','database_sha256':hashlib.sha256(db.read_bytes()).hexdigest()}
   if job_change is not None:
    output=reports/'domains'/'attempt-2';output.mkdir(parents=True)
    (output/'result.json').write_text('{}')
    job={'exit_code':0,'verdict':{'pass':True},'database_revision':'exact-revision',
         'database_sha256':receipt['database_sha256'],'output':str(output),
         'result_sha256':{'result.json':hashlib.sha256(b'{}').hexdigest()}}
    job.update(job_change);receipt['jobs']={'domains':job}
   receipt.update(override);(reports/'acceptance_receipt.json').write_text(json.dumps(receipt))
   r=subprocess.run([sys.executable,str(SCRIPT),'--reports',str(reports),'--output',str(root/'output'),'--workspace',str(root),'--database',str(db)],capture_output=True,text=True)
   self.assertNotEqual(r.returncode,0);self.assertFalse((root/'output').exists());return r.stderr
 def test_previous_revision_is_rejected(self):
  self.assertIn('candidate database_revision',self.rejected({'database_revision':'old'}))
 def test_same_revision_different_payload_is_rejected(self):
  self.assertIn('exact candidate file',self.rejected({'database_sha256':'0'*64}))
 def test_incomplete_acceptance_is_rejected(self):
  self.assertIn('explicit semantic verdicts',self.rejected({'all_pass':False}))
 def test_empty_acceptance_is_rejected(self):
  self.assertIn('explicit semantic verdicts',self.rejected({'jobs':{}}))
 def test_job_from_old_revision_is_rejected_after_candidate_hash_matches(self):
  self.assertIn('another candidate',self.rejected({}, {'database_revision':'old'}))
 def test_job_from_different_physical_file_is_rejected(self):
  self.assertIn('another candidate',self.rejected({}, {'database_sha256':'other'}))
 def test_failed_job_is_rejected_even_when_top_level_claims_pass(self):
  self.assertIn('Unaccepted result stage',self.rejected({}, {'verdict':{'pass':False}}))
 def test_modified_stage_file_is_rejected_after_success_receipt(self):
  self.assertIn('Accepted result files changed',self.rejected({}, {'result_sha256':{'result.json':'0'*64}}))
if __name__=='__main__':unittest.main()
