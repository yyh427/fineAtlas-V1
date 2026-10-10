"""Complete subject and sense contracts use no label or identifier exceptions."""
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.structure_subject_scope_rules import ordinary_class_genus,scoped_subject_genus


class CompleteSubjectScopeRules(unittest.TestCase):
    def test_count_qualified_engine_is_a_design_modifier(self):
        for phrase in ('single-engine general aviation biplane','twin-engine general aviation biplane','four-engine transport airplane'):
            result=scoped_subject_genus(phrase+' developed in 1930','Example')
            self.assertIsNotNone(result)
        self.assertIsNone(scoped_subject_genus('aircraft engine','Example'))
        self.assertIsNone(scoped_subject_genus('an engine for a biplane','Example'))
    def test_biplane_native_parent_does_not_assert_all_are_powered(self):
        self.assertEqual(scoped_subject_genus('single-engine general aviation biplane','Example'),('biplane','wikidata:Q223818'))
        self.assertEqual(scoped_subject_genus('military helicopter','Example'),('helicopter','wikidata:Q34486'))
        self.assertEqual(scoped_subject_genus('military monoplane','Example'),('monoplane','wikidata:Q627537'))
    def test_whole_subject_alias_can_define_an_ordinary_camera(self):
        self.assertEqual(ordinary_class_genus('An Internet Protocol camera, or IP camera, is a type of digital video camera that sends images.','IP camera',['Internet Protocol camera']),('camera','wikidata:Q15328'))
    def test_virtual_software_camera_is_not_a_physical_camera(self):
        self.assertIsNone(ordinary_class_genus('A virtual camera is a camera in 3D software.','virtual camera'))
    def test_negative_toy_scope_is_not_a_physical_camera(self):
        self.assertIsNone(ordinary_class_genus('A toy camera is a camera that is not a real physical camera.','toy camera'))
    def test_functional_toy_film_camera_retains_its_actual_genus(self):
        self.assertEqual(ordinary_class_genus('A toy camera is a simple film camera with a photographic lens.','toy camera'),('camera','wikidata:Q15328'))
    def test_movie_purpose_does_not_make_an_aircraft_fictional(self):
        self.assertEqual(ordinary_class_genus('A reduced-gravity aircraft is a type of fixed-wing aircraft for making movie shots.','reduced-gravity aircraft'),('fixed-wing aircraft','wikidata:Q2875704'))
    def test_router_woodworking_and_network_senses_differ(self):
        self.assertIsNone(ordinary_class_genus('A wood router is a router designed to cut wood.','wood router'))
        self.assertEqual(ordinary_class_genus('A core router is a router designed to operate in Internet networks.','core router'),('router','wikidata:Q5318'))
    def test_specific_source_parent_retained(self):
        self.assertEqual(ordinary_class_genus('A gaming computer is a specialized personal computer designed for games.','gaming computer'),('personal computer','wikidata:Q16338'))
        self.assertEqual(ordinary_class_genus('A DSLR is a digital camera with an image sensor.','DSLR'),('digital camera','wikidata:Q62927'))
    def test_multi_chip_microprocessor_is_not_single_chip_parent(self):
        self.assertEqual(scoped_subject_genus('family of microprocessors developed by Company','Example'),('microprocessors','wikidata:Q5297'))
    def test_associated_airliner_is_not_the_business_jets_type(self):
        self.assertIsNone(scoped_subject_genus('business jet derived from a family of commercial airliners','Example'))
    def test_named_single_subject_does_not_supply_ordinary_class_grain(self):
        self.assertIsNone(ordinary_class_genus('Brand 42 is a computer built by a manufacturer.','Brand 42'))
    def test_unpowered_fixed_wing_type_keeps_native_scope(self):
        self.assertEqual(scoped_subject_genus('non-powered fixed-wing aircraft','Example'),('fixed-wing aircraft','wikidata:Q2875704'))
    def test_mixed_owned_scope_is_not_reduced_to_one_kind(self):
        self.assertIsNone(scoped_subject_genus('family of laptops and desktop computers','Example'))

if __name__=='__main__':unittest.main()
