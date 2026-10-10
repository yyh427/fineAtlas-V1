"""A source-state observer must retain historical siblings and exact later history."""
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import structure_complete_parent_claim_snapshot as snapshot

class SourceStateControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.inputs=Path(self.temp.name)
        self.db=sqlite3.connect(':memory:');self.addCleanup(self.db.close);self.db.row_factory=sqlite3.Row
        self.db.executescript('CREATE TABLE metadata(key TEXT,value TEXT);CREATE TABLE entity_relations(id INTEGER,subject_uid TEXT,object_uid TEXT,relation TEXT,source TEXT,data TEXT,status TEXT,reason TEXT,evidence_id TEXT);CREATE TABLE usability_changes(stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT);')
        self.old=[]
        for rid,status,reason in [(1,'REJECTED','Earlier grounded rejection'),(2,'REJECTED','Earlier native-sense rejection'),(3,'SOURCE_SCOPE_REVIEW',None)]:
            row={'id':rid,'subject_uid':'u','object_uid':'p','relation':'DESIGN_TYPE_OF','source':'retained-source','data':'{"whole":"raw"}','status':status,'reason':reason,'evidence_id':'original'}
            self.db.execute('INSERT INTO entity_relations VALUES(:id,:subject_uid,:object_uid,:relation,:source,:data,:status,:reason,:evidence_id)',row);self.old.append(row)
        self.rows=[{'table':'entity_relations','canonical_id':3,'locator':{'subject_uid':'u','object_uid':'p','relation':'DESIGN_TYPE_OF','source':'retained-source','source_assertion_multiplicity':3},'rows':[{'id':r['id'],'status':r['status'],'reason':r['reason'],'row_sha256':snapshot.row_sha(r)}for r in self.old]}]
        self.payload={'quarantines':[{'table':'entity_relations','original_source_assertion':{**self.old[2],'status':'ACTIVE'}}]}
        (self.inputs/'structure_source_contracts.json.gz').write_bytes(gzip.compress(json.dumps(self.payload).encode(),mtime=0));self.write_ops([])
    def write_ops(self,ops):
        op_path=self.inputs/'hierarchy_complete_owned_type_repairs.jsonl';op_path.write_text(''.join(json.dumps(o)+'\n'for o in ops));m={'operations_file':op_path.name,'operations_sha256':snapshot.digest(op_path)};p=self.inputs/'structure_complete_owned_type_repairs.json';p.write_text(json.dumps(m));freeze={name:snapshot.digest(self.inputs/name)for name in [p.name,op_path.name,'structure_source_contracts.json.gz']};self.db.execute('DELETE FROM metadata');self.db.execute('INSERT INTO metadata VALUES(?,?)',('structure_frozen_build_manifest',json.dumps({'inputs':freeze})))
    def check(self):return snapshot.compare_current_parent_assertion_rows(self.db,self.rows,self.inputs)
    def test_exact_old_rejected_scope_review_multiset_is_kept(self):
        answer=self.check();self.assertEqual(answer['historical_source_rows_checked'],3);self.assertFalse(answer['role_profile_normalization_applied_to_source_rows'])
    def test_reason_or_raw_producer_change_is_not_a_role_exception(self):
        for field,value in [('reason','rewritten'),('data','{}'),('source','new-source')]:
            with self.subTest(field=field):
                self.db.execute('UPDATE entity_relations SET '+field+'=? WHERE id=1',(value,))
                with self.assertRaises(ValueError):self.check()
                self.db.execute('UPDATE entity_relations SET '+field+'=? WHERE id=1',(self.old[0][field],))
    def test_duplicate_or_deleted_historical_siblings_are_rejected(self):
        row={**self.old[0],'id':4};self.db.execute('INSERT INTO entity_relations VALUES(:id,:subject_uid,:object_uid,:relation,:source,:data,:status,:reason,:evidence_id)',row)
        with self.assertRaises(ValueError):self.check()
        self.db.execute('DELETE FROM entity_relations WHERE id IN (4,1)')
        with self.assertRaises(ValueError):self.check()
    def test_blanket_scope_status_normalization_is_rejected(self):
        self.db.execute('UPDATE entity_relations SET status="SOURCE_SCOPE_REVIEW" WHERE id=1')
        with self.assertRaises(ValueError):self.check()
    def test_only_exact_frozen_later_fullrow_with_unique_history_can_change_status(self):
        before={**self.old[0],'status':'ACTIVE'};after={**before,'status':'SOURCE_SCOPE_REVIEW'}
        self.rows[0]['rows'][0].update(status='ACTIVE',row_sha256=snapshot.row_sha(before))
        self.db.execute('UPDATE entity_relations SET status="SOURCE_SCOPE_REVIEW"WHERE id=1')
        proof={'whole_source':'scope counterexample','role_review':'explicit instance'};op={'op':'review_typed_relation','uid':'u','parent':'p','relation':'DESIGN_TYPE_OF','before_assertion':before,'after_status':'SOURCE_SCOPE_REVIEW','proof':proof,'content_sha256':hashlib.sha256(json.dumps({k:v for k,v in before.items()if k not in('id','status','reason')},sort_keys=True).encode()).hexdigest()};self.write_ops([op])
        with self.assertRaises(ValueError):self.check()
        self.db.execute('INSERT INTO usability_changes VALUES(?,?,?,?,?,?)',('complete_owned_type_repairs','typed_scope_review','1',json.dumps(before),json.dumps({'status':'SOURCE_SCOPE_REVIEW'}),json.dumps(proof)))
        self.assertEqual(self.check()['exact_later_source_status_permissions_used'],1)
        self.db.execute('INSERT INTO usability_changes SELECT * FROM usability_changes')
        with self.assertRaises(ValueError):self.check()
    def test_unfrozen_source_operations_cannot_authorize_withdrawals(self):
        (self.inputs/'hierarchy_complete_owned_type_repairs.jsonl').write_text('{}\n')
        with self.assertRaises(ValueError):self.check()

if __name__=='__main__':unittest.main()
