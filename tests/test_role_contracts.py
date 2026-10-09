"""Model extraction must not erase positive source-instance declarations."""
import unittest
from fineatlas.role_contracts import allows_model_extraction, nominal_role_decision, design_grain_for_claims

class SourceRoleContractsTest(unittest.TestCase):
    def test_profile_instance_outranks_old_generic_model_field(self):
        self.assertFalse(allows_model_extraction({'node_kind':'MODEL'},{'node_kind':'INSTANCE'}))
        self.assertFalse(allows_model_extraction({'node_kind':'INSTANCE'},None))
        self.assertFalse(allows_model_extraction({'node_kind':'INSTANCE'},{'node_kind':'CLASS'}))
    def test_design_declarations_and_unassessed_conceptual_roles_remain_candidates(self):
        self.assertTrue(allows_model_extraction({'node_kind':'MODEL'},{'node_kind':'MODEL'}))
        self.assertTrue(allows_model_extraction({'node_kind':'CLASS'},{'node_kind':'CLASS'}))
        self.assertTrue(allows_model_extraction({},None))
    def test_non_design_roles_are_not_replaced_by_nominal_product_nouns(self):
        for role in ['ORGANIZATION','ATTRIBUTE','DATASET_CATEGORY','BIOLOGICAL_VARIANT']:
            with self.subTest(role=role):self.assertFalse(allows_model_extraction({'node_kind':role},None))

    def test_individual_events_and_design_evidence_are_distinct(self):
        self.assertEqual(nominal_role_decision({'definition':'Example was a cargo ship built in 1850 and wrecked in 1860.'}, {})[0], 'INSTANCE')
        self.assertEqual(nominal_role_decision({'definition':'Example was the standard computer for ship and submarine platforms, with the first unit delivered in 1984.'}, {})[0], 'MODEL')
        self.assertEqual(nominal_role_decision({'definition':'Example observatory is a building standing on Example Avenue.'}, {})[0], 'INSTANCE')

    def test_rank_and_noun_alone_do_not_settle_role(self):
        for native in [{'node_kind':'MODEL','rank':'model'}, {'definition':'Example is a missile system.'}, {'definition':'Example is a computer.'}]:
            self.assertIsNone(nominal_role_decision(native, {'final_role':'INSTANCE'})[0])

    def test_explicit_family_is_not_overwritten_by_legacy_model_rank(self):
        family={'native_role_claim':{'role':'MODEL_FAMILY','native_meta_uid':'native:family'},'nominal_head':'agricultural aircraft'}
        fallback={'native_role_claim':{'role':'MODEL','basis':'Historical adapter rank'},'nominal_head':'agricultural aircraft'}
        self.assertEqual(design_grain_for_claims([family,fallback])[0],'MODEL_FAMILY')
        self.assertEqual(design_grain_for_claims([fallback,family])[0],'MODEL_FAMILY')

    def test_independent_series_definition_settles_design_grain(self):
        model={'native_role_claim':{'role':'MODEL','native_meta_uid':'native:model'},'nominal_head':'series of experimental aircraft'}
        self.assertEqual(design_grain_for_claims([model])[0],'MODEL_FAMILY')
        self.assertIsNone(design_grain_for_claims([{'native_role_claim':{'role':'MODEL'},'nominal_head':'aircraft'}])[0])
