"""Independent scope regressions: publisher fields and partial evidence differ."""
import gzip
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/audit_vehicle_source_scope.py'
spec=importlib.util.spec_from_file_location('independent_vehicle',SCRIPT)
A=importlib.util.module_from_spec(spec);spec.loader.exec_module(A)

import sys
sys.path.insert(0,str(SCRIPT.parents[1]/'src'))
from fineatlas.structure_vehicle_source_scope import validate_native_configuration_operation


class VehicleScopeTests(unittest.TestCase):
    def test_assertion_uses_its_evidence_and_preserves_other_endpoint_history(self):
        with sqlite3.connect(':memory:') as c:
            c.row_factory=sqlite3.Row
            c.executescript('''
                CREATE TABLE edges(child_uid,parent_uid,relation,source,status,provenance);
                CREATE TABLE hierarchy_decisions(subject_uid,object_uid,operation,evidence_id);
                CREATE TABLE evidence(evidence_id,payload);
            ''')
            for evidence_id, operation in [('old','link'),('withdrawn','withdraw_edge'),('current','link')]:
                c.execute('INSERT INTO hierarchy_decisions VALUES(?,?,?,?)',('child','parent',operation,evidence_id))
                c.execute('INSERT INTO evidence VALUES(?,?)',(evidence_id,json.dumps({'proof':evidence_id})))
            c.execute('INSERT INTO edges VALUES(?,?,?,?,?,?)',
                      ('child','parent','IS_A','new source','ACTIVE',json.dumps({'evidence_ids':['current']})))
            rows=A.classification_assertion_rows(c,'child','parent','IS_A','new source')
            self.assertEqual(len(rows),1)
            self.assertEqual(json.loads(rows[0]['proof']),{'proof':'current'})
            self.assertEqual(c.execute('SELECT count(*) FROM hierarchy_decisions').fetchone()[0],3)
            c.execute('UPDATE edges SET provenance=?',(json.dumps({'evidence_ids':['absent']}),))
            self.assertEqual(A.classification_assertion_rows(c,'child','parent','IS_A','new source'),[])
            # A matching unbound proof cannot rescue the actual wrong binding.
            c.execute('UPDATE edges SET provenance=?',(json.dumps({'evidence_ids':['old']}),))
            wrong=A.classification_assertion_rows(c,'child','parent','IS_A','new source')
            self.assertNotEqual(json.loads(wrong[0]['proof']),{'proof':'current'})

    def test_forged_configuration_scope_cannot_replay(self):
        fields={'id':'42','make':'Example','model':'Publisher truck','year':'2012','VClass':'Standard Pickup Trucks','baseModel':'Publisher truck'}
        proof={'native_fields':fields,'primary_csv_sha256':'a'*64,'no_lifting_to_entire_model':True,'world_identity_assertion':False}
        op={'uid':'epa:42','parent':A.CAR,'proof':proof}
        with self.assertRaisesRegex(ValueError,'enum scope'):
            validate_native_configuration_operation(op,fields,'a'*64)
        op['parent']=A.MOTOR
        validate_native_configuration_operation(op,fields,'a'*64)
        op['uid']='epa:43'
        with self.assertRaisesRegex(ValueError,'publisher record'):
            validate_native_configuration_operation(op,fields,'a'*64)

    def test_physical_type_cannot_claim_world_annotation_identity(self):
        fields={'id':'42','make':'Example','model':'Publisher car','year':'2012','VClass':'Compact Cars','baseModel':'Publisher car'}
        op={'uid':'epa:42','parent':A.CAR,'proof':{'native_fields':fields,'primary_csv_sha256':'a'*64,'no_lifting_to_entire_model':True,'world_identity_assertion':True}}
        with self.assertRaisesRegex(ValueError,'entire-model'):
            validate_native_configuration_operation(op,fields,'a'*64)

    def test_literal_size_enum_not_name_token(self):
        self.assertEqual(A.vehicle_type('Compact Cars'),A.CAR)
        self.assertIsNone(A.vehicle_type('A compact Cars word appears somewhere'))
        self.assertIsNone(A.vehicle_type('Experimental Cars'))
        self.assertIsNone(A.vehicle_type('compact cars'))

    def test_trucks_suv_van_do_not_become_four_wheel_car(self):
        for name in ('Standard Pickup Trucks','Small Sport Utility Vehicle 4WD','Vans, Cargo Type','Special Purpose Vehicles'):
            self.assertEqual(A.vehicle_type(name),A.MOTOR)
        self.assertNotEqual(A.vehicle_type('Sport Utility Vehicle - 4WD'),A.CAR)

    def test_legacy_combined_wagon_enum_does_not_guess_passenger_alias(self):
        self.assertEqual(A.vehicle_type('Midsize-Large Station Wagons'),A.MOTOR)
        self.assertNotEqual(A.vehicle_type('Midsize-Large Station Wagons'),A.CAR)

    def test_source_code_version_and_single_multi_engine(self):
        self.assertEqual(A.AIRCRAFT_CODES['5'],'Fixed wing multi engine')
        self.assertEqual(A.AIRCRAFT_CODES['6'],'Rotorcraft')
        self.assertNotIn('0',A.AIRCRAFT_CODES)
        self.assertEqual(A.AIRCRAFT_CODES['O'],'Other')

    def test_actual_model_id_filter_is_not_scope_proof(self):
        row={'Make_ID':476,'Model_ID':1938,'Model_Name':'Ram'}
        for catalogue in ('Passenger Car','Truck','Bus','Multipurpose Passenger Vehicle (MPV)','Incomplete Vehicle'):
            self.assertIsNone(A.catalogue_model_type(row,catalogue))

    def test_correct_ids_still_not_an_exhaustive_named_projection(self):
        refs=[{'uid':'epa:31323','model':'V8 Vantage','VClass':'Two Seaters'}]
        self.assertIsNone(A.reference_set_whole_projection_type(refs))
        self.assertIsNone(A.reference_set_whole_projection_type(refs,'Named Roadster configuration; supporting EPA example'))

    def test_input_digest_precedes_decoding(self):
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);payload=p/'payload.json.gz';payload.write_bytes(gzip.compress(b'{}'))
            (p/'structure_vehicle_source_scope.json').write_text(json.dumps({'schema':'FINEATLAS_VEHICLE_SOURCE_SCOPE_MANIFEST_V1','payload_file':payload.name,'payload_sha256':'0'*64}))
            with self.assertRaisesRegex(ValueError,'checksum'):A.load_frozen(p)

    def test_input_cannot_escape_frozen_directory(self):
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);(p/'structure_vehicle_source_scope.json').write_text(json.dumps({'schema':'FINEATLAS_VEHICLE_SOURCE_SCOPE_MANIFEST_V1','payload_file':'../unrelated.json','payload_sha256':'0'*64}))
            with self.assertRaisesRegex(ValueError,'escapes'):A.load_frozen(p)

    def test_statement_hash_excludes_row_id_not_source_content(self):
        row={'id':1,'subject_uid':'faa:A','object_uid':'kind:4','source':'FAA','relation':'DESIGN_TYPE_OF','data':'native dictionary','status':'ACTIVE'}
        relocated=dict(row,id=999)
        self.assertEqual(A.content_sha(row),A.content_sha(relocated))
        self.assertNotEqual(A.content_sha(row),A.content_sha(dict(row,data='Different source scope')))


if __name__=='__main__':unittest.main()
