import unittest
from fineatlas.structure_biology_scope import whole_scope_review
from fineatlas.structure_biology import corroborated_species_rank


class WholeDefinitionScopeTests(unittest.TestCase):
    def test_future_rank_preparation_rejects_seed_species_shortcut(self):
        record = {'source':'wordnet31', 'data':'{"labels":["Dahlia_pinnata"]}',
                  'description':'any of several plants of or developed from the species Dahlia pinnata having tuberous roots'}
        native = [{'uid':'wfo:test-pinnata', 'label':'Dahlia pinnata', 'rank':'species'}]
        self.assertIsNone(corroborated_species_rank(record, native))
        record['description'] = 'A tuberous Mexican species cultivated in many varieties'
        self.assertEqual(corroborated_species_rank(record, native)['rank'], 'species')

    def test_quantified_cultivars_do_not_become_one_species(self):
        self.assertIsNotNone(whole_scope_review('any of various cultivars of the genus Brassica oleracea grown for their edible leaves or flowers'))

    def test_dahlia_developed_plants_are_broader_than_seed_species(self):
        self.assertIsNotNone(whole_scope_review('any of several plants of or developed from the species Dahlia pinnata having tuberous roots'))

    def test_rex_hybrid_group_is_not_seed_species(self):
        self.assertIsNotNone(whole_scope_review('any of numerous usually rhizomatous hybrid begonias derived from an East Indian plant'))

    def test_unknown_new_quantified_definition_fails_closed(self):
        self.assertIsNotNone(whole_scope_review('any of many plants producing flowers'))
        self.assertIsNotNone(whole_scope_review('a group of cultivated plants'))

    def test_within_species_varieties_are_preserved(self):
        self.assertIsNone(whole_scope_review('Eurasian plant with pink to purple-red spice-scented usually double flowers; widely cultivated in many varieties and many colors'))
        self.assertIsNone(whole_scope_review('highly variable species of very large primitive ferns'))

    def test_single_named_hybrid_is_not_blanket_rejected(self):
        self.assertIsNone(whole_scope_review('hybrid garden flower derived from Chrysanthemum maximum and Chrysanthemum lacustre having large white flower heads'))
        self.assertIsNone(whole_scope_review('small hybrid apricot of Asia and Asia Minor having purplish twigs'))

    def test_character_quantification_is_not_extent_quantification(self):
        self.assertIsNone(whole_scope_review('plant with several racemes; all parts poisonous; if any spines present, short'))
        self.assertIsNone(whole_scope_review('one of several East Indian trees yielding gutta-percha'))


if __name__ == '__main__':
    unittest.main()
