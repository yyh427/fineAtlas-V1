import copy
import json
from pathlib import Path
import unittest

from fineatlas.catalogue import inspect_listing, listing_uid


class LivingCatalogueTests(unittest.TestCase):
    def setUp(self):
        config = Path(__file__).resolve().parents[1] / "configs/living_product_type_rules.json"
        self.rules = {r["product_type"]: r for r in json.loads(config.read_text())["rules"]}
        self.record = {
            "domain_name": "amazon.com", "item_id": "SOURCE-1",
            "product_type": [{"value": "TABLE"}],
            "item_name": [{"language_tag": "en_US", "value": "Rivet Coffee Table, Walnut"}],
            "node": [{"node_name": "/Categories/Furniture/Living Room Furniture/Tables/Coffee Tables"}],
            "model_number": [{"value": "CT-1"}],
        }

    def test_source_type_and_category_support_refined_furniture_connection(self):
        verdict = inspect_listing(self.record, self.rules["TABLE"])
        self.assertEqual(verdict["status"], "ADMIT_SOURCE_CONFIGURATION")
        self.assertIn("wordnet31:03067971-n", verdict["parent_uids"])
        self.assertFalse(verdict["world_model_identity_verified"])
        self.assertEqual(verdict["role"], "CONFIGURATION")

    def test_same_name_on_other_marketplace_is_independent_source_identity(self):
        other = {**self.record, "domain_name": "amazon.co.uk"}
        self.assertNotEqual(listing_uid(self.record), listing_uid(other))

    def test_accessory_and_swatches_do_not_become_furniture_configurations(self):
        for title in ("Coffee Table Replacement Leg", "Walnut Fabric Sample Swatch", "Coffee Table Cover"):
            row = copy.deepcopy(self.record)
            row["item_name"][0]["value"] = title
            self.assertEqual(inspect_listing(row, self.rules["TABLE"])["status"], "REVIEW")

    def test_title_alone_cannot_override_native_classification(self):
        row = copy.deepcopy(self.record)
        row["node"] = [{"node_name": "/Categories/Office/Stationery"}]
        self.assertEqual(inspect_listing(row, self.rules["TABLE"])["reason"], "CATALOGUE_SCOPE_NOT_CORROBORATED")
        row["product_type"].append({"value": "SOFA"})
        self.assertEqual(inspect_listing(row, self.rules["TABLE"])["reason"], "NATIVE_TYPE_AMBIGUOUS")

    def test_malformed_and_missing_native_fields_remain_review(self):
        for change in ({"product_type": "TABLE"}, {"node": None}, {"item_name": []},
                       {"item_name": [{"language_tag": None, "value": "Table"}]}):
            row = {**self.record, **change}
            self.assertEqual(inspect_listing(row, self.rules["TABLE"])["status"], "REVIEW")

    def test_size_conflict_is_not_silently_selected_from_one_language(self):
        row = copy.deepcopy(self.record)
        row["item_name"] = [{"language_tag": "en_US", "value": "Queen Coffee Table"},
                            {"language_tag": "de_DE", "value": "King Coffee Table"}]
        self.assertEqual(inspect_listing(row, self.rules["TABLE"])["reason"], "MULTILINGUAL_SIZE_CONFLICT")

    def test_backed_stool_uses_seat_and_narrow_stool_requires_scope_evidence(self):
        row = copy.deepcopy(self.record)
        row['product_type']=[{'value':'STOOL_SEATING'}]
        row['node']=[{'node_name':'Furniture/Kitchen/Stools/Barstools'}]
        row['item_name'][0]['value']='Counter Stool with Back and Arms'
        checked=inspect_listing(row,self.rules['STOOL_SEATING'])
        self.assertEqual(checked['parent_uids'],['wordnet31:04169042-n'])
        row['item_name'][0]['value']='Backless Counter Stool'
        row['bullet_point']=[{'language_tag':'en_US','value':'Armless design'}]
        self.assertIn('wordnet31:04334034-n',inspect_listing(row,self.rules['STOOL_SEATING'])['parent_uids'])
        row['bullet_point'].append({'language_tag':'en_US','value':'With arms'})
        self.assertNotIn('wordnet31:04334034-n',inspect_listing(row,self.rules['STOOL_SEATING'])['parent_uids'])

    def test_packing_cube_accessory_cannot_be_a_luggage_case(self):
        row=copy.deepcopy(self.record)
        row['product_type']=[{'value':'LUGGAGE'}]
        row['item_name'][0]['value']='Luggage Travel Packing Cubes'
        row['node']=[{'node_name':'Luggage/Packing Organizers'}]
        self.assertEqual(inspect_listing(row,self.rules['LUGGAGE'])['status'],'REVIEW')

    def test_mixed_component_kit_is_review_but_multiseat_scope_uses_seat(self):
        row=copy.deepcopy(self.record)
        row['product_type']=[{'value':'CHAIR'}]
        row['node']=[{'node_name':'Furniture/Living Room Furniture/Chairs'}]
        row['item_name'][0]['value']='Barrel Chair with Ottoman'
        self.assertEqual(inspect_listing(row,self.rules['CHAIR'])['status'],'REVIEW')
        row['item_name'][0]['value']='Two-Seater Loveseat Chair'
        self.assertEqual(inspect_listing(row,self.rules['CHAIR'])['parent_uids'],['wordnet31:04169042-n'])

    def test_incandescent_wordnet_sense_is_not_used_for_all_led_bulbs(self):
        self.assertNotIn("LIGHT_BULB", self.rules)


if __name__ == "__main__":
    unittest.main()
