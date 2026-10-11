"""Regression controls for the separate complete-source SQL auditor."""
import importlib.util
from pathlib import Path
import sqlite3
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'audit_complete_owned_type_repairs.py'
SPEC = importlib.util.spec_from_file_location('independent_complete_type_auditor', SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class IndependentCompleteSourceControls(unittest.TestCase):
    def test_unrelated_named_subject_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'another named subject'):
            AUDIT.owned_predicate('Different family is a twinjet airliner.', 'Named design')

    def test_parenthesized_designation_keeps_the_owned_subject(self):
        phrase = AUDIT.owned_predicate(
            'Named design (NATO reporting name: Example) is a twin-engine jet airliner.',
            'Named design')
        self.assertIn('twin-engine jet airliner', phrase)

    def test_engine_count_modifier_is_not_an_engine_object(self):
        self.assertIn('four-engine', AUDIT.owned_predicate(
            'Named design is a four-engine jet airliner.', 'Named design'))
        with self.assertRaisesRegex(ValueError, 'different physical kind'):
            AUDIT.owned_predicate('Named design is a jet engine for an aircraft.', 'Named design')

    def test_complete_member_predicate_and_later_comparison_differ(self):
        phrase = AUDIT.owned_predicate(
            'Named design is a member of the Maker family of twin-engine jet airliners.',
            'Named design')
        self.assertIn('jet airliners', phrase)
        self.assertNotIn('twinjet', AUDIT.owned_predicate(
            'Named design is an aircraft. Other aircraft are twinjet airliners.', 'Named design'))

    def test_virtual_and_negated_scope_are_rejected(self):
        for phrase in ('a fictional twinjet airliner', 'not a twinjet airliner',
                       'a toy twinjet airliner'):
            with self.subTest(phrase=phrase), self.assertRaises(ValueError):
                AUDIT.owned_predicate('Named design is ' + phrase + '.', 'Named design')

    def test_source_field_requires_the_complete_actual_field(self):
        con = sqlite3.connect(':memory:')
        con.row_factory = sqlite3.Row
        con.execute('CREATE TABLE nodes(uid TEXT PRIMARY KEY,data TEXT)')
        raw = AUDIT.dump({'description': 'Twinjet airliner. It also has a full source history.'})
        con.execute('INSERT INTO nodes VALUES (?,?)', ('source:one', raw))
        witness = {'uid': 'source:one', 'field': 'description', 'field_path': 'description',
                   'data_sha256': AUDIT.sha(raw), 'statement': 'Twinjet airliner.'}
        with self.assertRaisesRegex(ValueError, 'exact complete'):
            AUDIT.source_field(con, witness)
        witness['statement'] = 'Twinjet airliner. It also has a full source history.'
        self.assertEqual(AUDIT.source_field(con, witness)[1], witness['statement'])
        witness['data_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'bytes'):
            AUDIT.source_field(con, witness)
        con.close()

    def test_whole_context_inventory_preserves_range_qualifications(self):
        node = {'data': AUDIT.dump({'description': 'A dessert', 'evidence_record': {
            'wikipedia_intro': 'Named pudding is a sweet or savoury dish.'}})}
        self.assertEqual(AUDIT.complete_source_fields(node), {
            'description': 'A dessert',
            'evidence_record.wikipedia_intro': 'Named pudding is a sweet or savoury dish.'})

    def test_unknown_witness_tables_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            AUDIT.row_at(None, 'sqlite_master', 'nodes')

    def test_semicolon_history_does_not_supply_physical_scope(self):
        head = AUDIT.owned_predicate('1943 fighter aircraft family; first single-engine jet aircraft.', 'Design')
        self.assertNotIn('jet', head)

    def test_complete_parent_definition_controls_scope(self):
        self.assertTrue(AUDIT.independent_physical_entailment('fighter biplane aircraft',
            'A biplane is a fixed-wing aircraft with two main wings stacked one above the other.'))
        self.assertFalse(AUDIT.independent_physical_entailment('fighter monoplane aircraft',
            'A biplane is a fixed-wing aircraft with two main wings stacked one above the other.'))
        with self.assertRaisesRegex(ValueError, 'separately reviewed'):
            AUDIT.independent_physical_entailment('business jet', 'A jet is a stream of fluid.')

    def test_generic_jet_does_not_imply_two_engines_or_fixed_wings(self):
        twin = 'a jet plane propelled by two jet engines'
        self.assertFalse(AUDIT.independent_physical_entailment('jet aircraft', twin))
        self.assertFalse(AUDIT.independent_physical_entailment('twinjet rotorcraft', twin))
        self.assertTrue(AUDIT.independent_physical_entailment('twin-engine jet airliner', twin))

    def test_motor_scope_and_general_glider_scope_remain_separate(self):
        motor = 'glider equipped with a motor for launch and flight boost'
        glider = 'A glider is a fixed-wing aircraft whose free flight does not depend on an engine.'
        self.assertFalse(AUDIT.independent_physical_entailment('sailplane family', motor))
        self.assertTrue(AUDIT.independent_physical_entailment('sailplane family', glider))

    def test_non_aviation_complete_type_requires_its_own_parent_sense(self):
        self.assertTrue(AUDIT.independent_physical_entailment('digital cameras',
            'A digital camera is a camera that uses digital storage to capture images.'))
        self.assertFalse(AUDIT.independent_physical_entailment('film cameras',
            'A digital camera is a camera that uses digital storage to capture images.'))
        self.assertTrue(AUDIT.independent_physical_entailment('locomotive',
            'a wheeled vehicle consisting of a self-propelled engine that is used to draw trains along railway tracks'))

    def test_manufacturer_name_is_bound_by_complete_retained_name(self):
        self.assertIn('monoplane', AUDIT.owned_predicate(
            'The Maker Model-X was a monoplane.', 'Model-X', ['Maker Model-X']))
        with self.assertRaises(ValueError):
            AUDIT.owned_predicate('Another Model-Y was a monoplane.', 'Model-X', ['Maker Model-X'])

    def test_proposed_design_not_built_does_not_negate_its_design_kind(self):
        self.assertIn('airship', AUDIT.owned_predicate(
            'British airship, planned in 1930 but never build', 'R102'))

    def test_physical_declaration_does_not_stop_at_amateur_build_modifier(self):
        phrase = AUDIT.owned_predicate(
            'The Design is an experimental/amateur built aircraft designed by Maker.', 'Design')
        self.assertIn('aircraft', phrase)

    def test_equal_source_mirrors_and_distinct_scope_values(self):
        node={'uid':'source:one','data':AUDIT.dump({'description':'aircraft','evidence_record':{'description':'aircraft'}})}
        witness={'uid':'source:one','field_path':'description','statement':'aircraft'}
        AUDIT.verify_complete_scope_fields(node,[witness])
        node['data']=AUDIT.dump({'description':'aircraft','evidence_record':{'description':'part of an aircraft'}})
        with self.assertRaisesRegex(ValueError,'omitted'):
            AUDIT.verify_complete_scope_fields(node,[witness])
        AUDIT.verify_complete_scope_fields(node,[witness,{'uid':'source:one','field_path':'evidence_record.description','statement':'part of an aircraft'}])

    def test_own_first_physical_scope_does_not_inherit_derived_model_kind(self):
        first=AUDIT.owned_predicate('The Design is an aircraft based on a twinjet airliner.', 'Design')
        self.assertNotIn('twinjet',first)
        self.assertFalse(AUDIT.independent_physical_entailment(first,'a jet plane propelled by two jet engines'))
