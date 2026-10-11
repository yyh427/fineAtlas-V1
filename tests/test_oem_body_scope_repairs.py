"""Reject sample lifting, stale scope, unsupported body senses and identity promotion."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fineatlas.structure_oem_body_scope_repairs import digest, validate_oem_body_scope_repairs


class BodyScopeContracts(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:'); self.c.row_factory = sqlite3.Row
        self.c.executescript('CREATE TABLE nodes(uid TEXT,data TEXT,visibility TEXT,source TEXT,rank TEXT,description TEXT); CREATE TABLE node_profiles(uid TEXT,node_kind TEXT); CREATE TABLE evidence(evidence_id TEXT,payload TEXT);')
        scope = {'manufacturer':'Maker','model':'Car','body':'convertible','model_year':2012}
        native = json.dumps({'scope':scope,'projection_kind':'REUSABLE_MODEL_CONFIGURATION','evidence_ids':['review']})
        parent = '{}'; payload = json.dumps({'scope':scope,'definition':'Complete reusable convertible body range.','review':{'verdict':'PASS'},'proofs':[{'sha256':'proof'}]})
        self.c.executemany('INSERT INTO nodes VALUES(?,?,?,?,?,?)', [('own',native,'ACTIVE','manufacturer','model_year_configuration',''),('type',parent,'ACTIVE','wordnet31','','a car that has top that can be folded or removed')])
        self.c.execute('INSERT INTO evidence VALUES(?,?)',('review',payload))
        self.op = {'op':'link','uid':'own','parent':'type','relation':'CONFIGURATION_TYPE_OF','proof':{'world_identity_assertion':False,'no_identity_merges':True,'whole_subject_intensional_scope':True,'scope_observation':'Manufacturer defines complete convertible body range.','native_record_sha256':digest(native),'parent_native_record_sha256':digest(parent),'own_complete_scope':scope,'original_scope_evidence_id':'review','original_scope_payload_sha256':digest(payload),'manufacturer_whole_body_scope_review':True,'manufacturer_material_hashes':['proof'],'reviewed_type_sense':'CAR_CONVERTIBLE'}}
        self.manifest = {'schema':'FINEATLAS_OEM_BODY_SCOPE_REPAIRS_V1'}
    def tearDown(self): self.c.close()
    def validate(self, op=None): validate_oem_body_scope_repairs(self.c,self.manifest,[op or self.op])
    def test_entire_convertible_constraint_passes(self): self.validate()
    def test_world_identity_is_not_entailed(self):
        op=copy.deepcopy(self.op);op['proof']['world_identity_assertion']=True
        with self.assertRaisesRegex(ValueError,'exact world'):self.validate(op)
    def test_reference_samples_do_not_define_entire_range(self):
        op=copy.deepcopy(self.op);op['proof']['whole_subject_intensional_scope']=False
        with self.assertRaisesRegex(ValueError,'reference set'):self.validate(op)
    def test_complete_definition_is_not_lifted_from_different_scope(self):
        payload=json.dumps({'scope':{'model':'Other'},'definition':'Another car','review':{'verdict':'PASS'}})
        self.c.execute('UPDATE evidence SET payload=?',(payload,));self.op['proof']['original_scope_payload_sha256']=digest(payload)
        with self.assertRaisesRegex(ValueError,'entail'):self.validate()
    def test_proof_materials_cannot_be_replaced(self):
        op=copy.deepcopy(self.op);op['proof']['manufacturer_material_hashes']=['unrelated']
        with self.assertRaisesRegex(ValueError,'manufacturer'):self.validate(op)
    def test_convertible_financial_or_furniture_sense_rejected(self):
        self.c.execute("UPDATE nodes SET description='a convertible security' WHERE uid='type'")
        with self.assertRaisesRegex(ValueError,'physical car sense'):self.validate()
    def test_scope_change_requires_new_source_review(self):
        self.c.execute("UPDATE nodes SET data='{}' WHERE uid='own'")
        with self.assertRaisesRegex(ValueError,'ranges changed'):self.validate()
    def test_repeated_operation_rejected(self):
        with self.assertRaisesRegex(ValueError,'unique'):validate_oem_body_scope_repairs(self.c,self.manifest,[self.op,self.op])

if __name__ == '__main__': unittest.main()
