import unittest

from fineatlas.engineering_roles import engineering_role_hint


class EngineeringRoleEvidenceTest(unittest.TestCase):
    def test_native_model_variant(self):
        role, _ = engineering_role_hint('epa', 'model_variant', 'car', 'Porsche Carrera', '')
        self.assertEqual(role, 'MODEL')

    def test_explicit_design_scope(self):
        self.assertEqual(engineering_role_hint('wikidata_v4_p31', 'named_refinement', 'aircraft', 'Tutor', 'trainer aircraft family by Canadair')[0], 'MODEL_FAMILY')
        self.assertEqual(engineering_role_hint('wikidata_v4_p31', 'named_refinement', 'aircraft', 'Skymaster', 'utility aircraft model by Cessna')[0], 'MODEL')

    def test_rank_or_number_alone_does_not_settle_role(self):
        self.assertIsNone(engineering_role_hint('wikidata_v4_p31', 'named_refinement', 'aircraft', 'Unknown 100', '')[0])
        self.assertIsNone(engineering_role_hint('wikidata', 'class', 'cars', 'electric car', 'car powered by electricity')[0])

    def test_individual_vessel_evidence(self):
        self.assertEqual(engineering_role_hint('wikidata', 'class', 'ships', 'Marella Explorer 2', 'Marella Explorer 2 was the lead ship of the Century class.')[0], 'INSTANCE')
        self.assertIsNone(engineering_role_hint('wikidata', 'class', 'ships', 'cruise ship', 'A cruise ship is a passenger ship used for pleasure voyages.')[0])


if __name__ == '__main__':
    unittest.main()
