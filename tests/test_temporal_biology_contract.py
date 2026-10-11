"""Later taxon uncertainty must retain exact source/history and never certify false taxa."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import structure_biology_temporal_contract as contract

class HistoricalTaxonomyControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.inputs=Path(self.temp.name)
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row;self.addCleanup(self.c.close)
        self.c.executescript('CREATE TABLE bridges(id INTEGER,left_uid TEXT,right_uid TEXT,relation TEXT,status TEXT,data TEXT,source TEXT);CREATE TABLE nodes(uid TEXT,data TEXT,rank TEXT,component_id INTEGER);CREATE TABLE entity_relations(id INTEGER,subject_uid TEXT,object_uid TEXT,relation TEXT,status TEXT,data TEXT);CREATE TABLE usability_changes(id INTEGER,stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT);CREATE TABLE browse_links(storage TEXT,record_id INTEGER);')
        self.ops=[];self.records=[]
        for rid in range(1,9):
            left,right='wn'+str(rid),'taxon'+str(rid);before={'id':rid,'left_uid':left,'right_uid':right,'relation':'SAME_CONCEPT','status':'ACTIVE','data':'original declaration','source':'original producer'};after={**before,'status':'SOURCE_SCOPE_REVIEW'}
            self.c.execute('INSERT INTO bridges VALUES(:id,:left_uid,:right_uid,:relation,:status,:data,:source)',after)
            proof={'basis':'HISTORICAL_TAXON_VERSION_WHOLE_SCOPE_GAP','versioned_taxon_source_review':{'whole_cross_version':'UNKNOWN'}}
            op={'op':'review_bridge','before_assertion':before,'proof':proof};self.ops.append(op)
            hist={'id':rid,'stage':'owned_scope_repairs','object_type':'bridge_scope_review','object_id':str(rid),'before_json':json.dumps(before),'after_json':json.dumps({'status':'SOURCE_SCOPE_REVIEW'}),'evidence':json.dumps(proof)};self.c.execute('INSERT INTO usability_changes VALUES(:id,:stage,:object_type,:object_id,:before_json,:after_json,:evidence)',hist)
            ref={'id':rid+100,'subject_uid':left,'object_uid':right,'relation':'NOMINAL_SCIENTIFIC_REFERENCE','status':'SOURCE_DECLARED','data':'{"allowed_views":[],"navigation_eligible":false}'};self.c.execute('INSERT INTO entity_relations VALUES(:id,:subject_uid,:object_uid,:relation,:status,:data)',ref)
            objects={uid:{'uid':uid,'data':'raw '+uid,'rank':'species','component_id':rid}for uid in (left,right)}
            for obj in objects.values():self.c.execute('INSERT INTO nodes VALUES(:uid,:data,:rank,:component_id)',obj)
            self.records.append({'before_bridge':before,'actual_after_bridge':after,'actual_history':[hist],'versioned_taxon_source_review':proof['versioned_taxon_source_review'],'scientifically_false_identity_asserted':False,'nominal_scientific_reference':ref,'actual_raw_objects':objects,'preserved_source_parents':{}})
        self.manifest={'operations_sha256':'sealed-source7','operation_count':1194,'operations_file':'hierarchy_owned_scope_repairs.jsonl'}
        self.review={'schema':'FINEATLAS_ACTUAL_EIGHT_TAXON_BRIDGE_TEMPORAL_SOURCE_RECEIPTS_V1','pass':True,'actual_parent_diagnostic_only':True,'final_finer_candidate_acceptance':False,'database_revision':'c933','source_operations_sha256':'sealed-source7','operation_count':1194,'source_operations_file':'/historical-host/hierarchy_owned_scope_repairs.jsonl','biological_bridge_count':8,'records':self.records}
        self.write()
    def write(self):
        self.path=self.inputs/'structure_temporal_biology_source_review.json';self.path.write_text(json.dumps(self.review));self.meta={'structure_complete_type_resume_parent':{'parent_revision':'c933'},'structure_frozen_build_manifest':{'inputs':{self.path.name:contract.digest(self.path)}}}
    def validate(self):return contract.require_frozen_taxonomy_source_review(self.c,self.inputs,self.manifest,self.ops,self.meta)
    def test_exact_historical_source_receipt_does_not_pretend_current_final_pass(self):
        answer=self.validate();self.assertEqual(answer['exact_eight_current_source_claims_and_histories_checked'],8);self.assertFalse(answer['historical_review_is_current_final_acceptance'])
    def test_old_parent_and_unsigned_rewritten_receipt_are_rejected(self):
        self.meta['structure_complete_type_resume_parent']['parent_revision']='3445'
        with self.assertRaises(ValueError):self.validate()
        self.meta['structure_complete_type_resume_parent']['parent_revision']='c933';self.path.write_text('{}')
        with self.assertRaises(ValueError):self.validate()
    def test_false_taxon_claim_or_final_rebinding_is_rejected(self):
        self.review['records'][0]['scientifically_false_identity_asserted']=True;self.write()
        with self.assertRaises(ValueError):self.validate()
        self.review['records'][0]['scientifically_false_identity_asserted']=False;self.review['final_finer_candidate_acceptance']=True;self.write()
        with self.assertRaises(ValueError):self.validate()
    def test_extra_or_missing_review_and_source_native_raw_change_are_rejected(self):
        self.ops=self.ops[:-1]
        with self.assertRaises(ValueError):self.validate()
        self.ops.append({'op':'review_bridge','before_assertion':self.records[-1]['before_bridge'],'proof':{'basis':'HISTORICAL_TAXON_VERSION_WHOLE_SCOPE_GAP','versioned_taxon_source_review':self.records[-1]['versioned_taxon_source_review']}})
        self.c.execute('UPDATE nodes SET rank="genus"WHERE uid="taxon1"')
        with self.assertRaises(ValueError):self.validate()
    def test_history_or_original_claim_producer_change_is_rejected(self):
        self.c.execute('UPDATE bridges SET source="rewritten"WHERE id=1')
        with self.assertRaises(ValueError):self.validate()
        self.c.execute('UPDATE bridges SET source="original producer"WHERE id=1');self.c.execute('DELETE FROM usability_changes WHERE id=1')
        with self.assertRaises(ValueError):self.validate()
    def test_nonnavigation_reference_index_leak_is_rejected(self):
        self.c.execute('INSERT INTO browse_links VALUES("entity",101)')
        with self.assertRaises(ValueError):self.validate()
    def test_preflight_and_unfrozen_diagnostics_never_satisfy_release_receipt(self):
        report=self.inputs/'report.json';report.write_text(json.dumps({'pass':True,'candidate_acceptance':False,'public_api_checked':True}))
        with self.assertRaises(ValueError):contract.require_temporal_biology_receipt(report,self.inputs/'db.sqlite',self.inputs,'final',self.inputs)

if __name__=='__main__':unittest.main()
