"""Independent scope regressions: publisher fields and partial evidence differ."""
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/audit_vehicle_source_scope.py'
spec=importlib.util.spec_from_file_location('independent_vehicle',SCRIPT)
A=importlib.util.module_from_spec(spec);spec.loader.exec_module(A)

import sys
sys.path.insert(0,str(SCRIPT.parents[1]/'src'))
from fineatlas.structure_vehicle_source_scope import validate_native_configuration_operation


class VehicleScopeTests(unittest.TestCase):
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
