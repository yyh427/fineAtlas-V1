import unittest

from fineatlas.structure_complete_owned_type_rules import complete_owned_physical_genus, owned_generic_class_scope


def parent(statement, label="Named design"):
    result = complete_owned_physical_genus(statement, label)
    return result["parent"] if result else None


class CompleteOwnedTypeRulesTest(unittest.TestCase):
    def test_compound_sense_uses_independent_complete_first_definition(self):
        sense={'compound':'business jet','uid':'source:businessjet','definition_statement':'civil jet aircraft designed to transport executives'}
        found=complete_owned_physical_genus('prototype light business jet','Named design',compound_senses=[sense])
        assert found['parent']=='wikidata:Q206592'
        assert found['predicate_kind']=='OWNED_COMPOUND_WITH_INDEPENDENT_GENERIC_AVIATION_SENSE'
        assert complete_owned_physical_genus('a jet of vapor','spray',compound_senses=[sense]) is None
        wrong={**sense,'definition_statement':'a water spray; aircraft use jet engines'}
        assert complete_owned_physical_genus('business jet','Named design',compound_senses=[wrong]) is None

    def test_engine_count_and_plane_scope_are_both_required(self):
        assert parent("Twinjet regional airliner") == "wordnet31:04510794-n"
        assert parent("Named design is a twin-engine jet airliner.") == "wordnet31:04510794-n"
        assert parent("Named design is a fixed-wing two-engine jet aircraft.") == "wordnet31:04510794-n"
        assert parent("Named design is a two-engine jet aircraft.") == "wikidata:Q206592"
        assert parent("Named design is a twin-engine helicopter.") == "wikidata:Q34486"


    def test_generic_jet_scope_does_not_shrink_to_fixed_wing(self):
        assert parent("Named design is a jet aircraft.") == "wikidata:Q206592"
        assert parent("Named design is a regional jet airliner.") == "wordnet31:03601053-n"
        assert parent("Named design is a jet-powered rotorcraft.") == "wikidata:Q206592"
        assert parent("Named design is a twin-jet airliner.") == "wordnet31:04510794-n"
        assert parent("Named design is a twin jet airliner.") == "wordnet31:04510794-n"

    def test_jet_stream_and_nonaviation_propulsion_do_not_supply_aircraft_kind(self):
        assert parent("a jet of vapor", "spray") is None
        assert parent("a jet of water", "spray") is None
        assert parent("Named design is a jet-powered automobile.") is None
        assert parent("Named design is a jet engine.") is None
        assert parent("Named design is a spray. Aircraft also use jets.") is None
        assert parent("1943 fighter aircraft family; first single-engine jet in service") == "wordnet31:02689427-n"

    def test_universal_class_grain_is_independent_of_import_rank(self):
        assert owned_generic_class_scope("Named design is a category of aircraft.", "Named design")
        assert owned_generic_class_scope("Named design are musical instruments that vibrate.", "Named design")
        assert not owned_generic_class_scope("Named design is a computer manufactured in series.", "Named design")
        assert not owned_generic_class_scope("Named design is a computer project.", "Named design")
        assert not owned_generic_class_scope("A named design is a computer project.", "named design")


    def test_owned_member_predicate_retains_full_qualified_physical_kind(self):
        statement = ("Named design is a member of the Manufacturer family of short to medium range, "
                     "narrow-body, commercial passenger twin engine jet airliners; it carries passengers.")
        result = complete_owned_physical_genus(statement, "Named design")
        assert result["parent"] == "wordnet31:04510794-n"
        assert result["predicate_kind"] == "OWNED_MEMBER_OF_FAMILY_OF_PHYSICAL_PREDICATE"
        assert result["two_jet_engine_evidence"] == "twin engine jet"


    def test_different_family_article_and_historical_comparison_are_not_owned_scope(self):
        assert parent("Different family is a series of twinjet regional airliners.") is None
        assert parent("Named design is an aircraft derived from a twinjet regional airliner.") == "wordnet31:02689427-n"
        assert parent("Named design is an aircraft. Other aircraft are twinjet regional airliners.") == "wordnet31:02689427-n"
        assert parent("Named design was designed to replace a twinjet airliner.") is None


    def test_physical_kind_and_scope_negation_are_not_keyword_matches(self):
        assert parent("Named design is a virtual twinjet regional airliner.") is None
        assert parent("Named design is a toy twinjet regional airliner.") is None
        assert parent("Named design is an unpowered jet aircraft.") is None
        assert parent("Named design is an unpowered glider.") == "wikidata:Q2165278"
        assert parent("Named design is a twinjet or turboprop airliner.") is None
        assert parent("Named design is an engine for a twinjet airplane.") is None


    def test_common_finer_scope_patterns_apply_outside_aircraft(self):
        assert parent("Named design is a digital camera.") == "wikidata:Q62927"
        assert parent("Named design is a personal computer.") == "wikidata:Q16338"
        assert parent("Named design is a fictional digital camera.") is None
        assert parent("Named design is a car model.") is None

    def test_structural_genus_survives_training_and_model_noun_tails(self):
        assert parent('glider aircraft model designed in Finland')=='wikidata:Q2165278'
        assert parent('small, single engine, tandem seat floatplane training aircraft')=='wikidata:Q115940'
        assert parent('single-engined monoplane airplane')=='wikidata:Q627537'
        assert parent('tandem seat biplane basic trainer')=='wikidata:Q223818'
        assert parent('side-by-side seat biplane trainer')=='wikidata:Q223818'
        assert parent('motor-glider aircraft family')=='wikidata:Q1930290'
        assert parent('glider and motor glider')=='wikidata:Q2165278'
        assert parent('aircraft derived from a motor glider')=='wordnet31:02689427-n'

class OwnedWholeUnionScopeTest(unittest.TestCase):
    def test_motor_configuration_union_keeps_common_source_capability(self):
        for text in ('German glider / motor glider (2020)',
                     'two-seat glider / motor glider (2011)',
                     'glider and motor glider'):
            self.assertEqual(complete_owned_physical_genus(text,'object')['parent'],
                             'wikidata:Q2165278')

    def test_thin_type_metadata_does_not_establish_class_grain(self):
        self.assertFalse(owned_generic_class_scope('type of aircraft','Named Aircraft'))
        self.assertTrue(owned_generic_class_scope(
            'An autonomous aircraft is an aircraft which flies without a human pilot.',
            'autonomous aircraft'))
