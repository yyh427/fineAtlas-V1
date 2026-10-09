import unittest

from fineatlas.engineering_roles import engineering_role_hint,definition_head,aircraft_engine_conditions


class EngineeringRoleEvidenceTest(unittest.TestCase):
    def test_multiword_manufacturer_subject_verification(self):
        text='The Carrera is a two-seat ultralight aircraft designed by Advanced Aeromarine.'
        self.assertTrue(definition_head(text,'Advanced Aeromarine Carrera'))
        self.assertFalse(definition_head('The Brio is a city car produced by Honda.','Honda New Small Concept'))
        self.assertFalse(definition_head('The Letord Let.5 was probably the most numerous of a family of aircraft.','Letord Let.7'))
        self.assertEqual(engineering_role_hint('wikidata','','aircraft','late Merlin-powered Spitfire','1942 fighter aircraft family by Supermarine')[0],'MODEL_FAMILY')
        self.assertIsNone(engineering_role_hint('wikidata','','aircraft','Code One','', 'Code One is the name of the aircraft which carries the President. Its current aircraft is a Boeing 747-8.')[0])

    def test_designation_period_does_not_truncate_kind(self):
        text='The Letord Let.7 was one of a series of French aircraft designed for reconnaissance.'
        self.assertIn('aircraft',definition_head(text,'Letord Let.7'))
        self.assertEqual(engineering_role_hint('wikidata','','aircraft','Letord Let.7','',text)[0],'MODEL')

    def test_named_construction_and_vessel_history(self):
        self.assertEqual(engineering_role_hint('wikidata','','aircraft','Wittman Tailwind','light aircraft','The Wittman Tailwind is a light aircraft for homebuilding. It is constructed with wood wings.')[0],'MODEL')
        self.assertIsNone(engineering_role_hint('wikidata','','cars','Trophy Truck','vehicle used in racing','A trophy truck is a vehicle used in high-speed racing. The class was introduced in 1994.')[0])
        self.assertIsNone(engineering_role_hint('wikidata','','aircraft','Question Mark','experimental aircraft', 'Question Mark was a modified transport airplane of the United States Army Air Corps.')[0])
        self.assertIsNone(engineering_role_hint('wikidata','','cars','Woodie','type of station wagon','A woodie is an automobile where the bodywork is constructed of wood.')[0])
        self.assertEqual(engineering_role_hint('wikidata','','ships','Norman Court','British clipper','Norman Court was a composite built clipper ship, designed by William Rennie.')[0],'INSTANCE')
        self.assertEqual(engineering_role_hint('wikidata','','ships','Yinmahu','naval vessel',"Yinmahu is a semi-submersible ship of the People's Liberation Army Navy.")[0],'INSTANCE')
        self.assertIsNone(engineering_role_hint('wikidata','','ships','Museum ship','ship type','A museum ship is a type of ship used by a navy for display.')[0])

    def test_native_engine_conditions_preserve_unit_and_exact_count(self):
        narrow=aircraft_engine_conditions('aircraft with 2 tractor-piston-propeller engines')
        broad=aircraft_engine_conditions('aircraft with piston-propeller engines')
        self.assertEqual(narrow[0],broad[0]);self.assertTrue(narrow[1]>broad[1])
        self.assertFalse(narrow[1]>=aircraft_engine_conditions('aircraft with 3 engines')[1])
        self.assertNotEqual(narrow[0],aircraft_engine_conditions('aircraft with 2 tractor propellers')[0])
        self.assertIsNone(aircraft_engine_conditions('aircraft with multiple engine options'))
        self.assertIsNone(aircraft_engine_conditions('Boeing 737 with 2 engines'))
    def test_native_model_variant(self):
        role, _ = engineering_role_hint('epa', 'model_variant', 'car', 'Porsche Carrera', '')
        self.assertEqual(role, 'MODEL')

    def test_explicit_design_scope(self):
        self.assertEqual(engineering_role_hint('wikidata_v4_p31', 'named_refinement', 'aircraft', 'Tutor', 'trainer aircraft family by Canadair')[0], 'MODEL_FAMILY')
        self.assertEqual(engineering_role_hint('wikidata_v4_p31', 'named_refinement', 'aircraft', 'Skymaster', 'utility aircraft model by Cessna')[0], 'MODEL')

    def test_group_words_in_other_clauses_do_not_set_grain(self):
        for label, desc in [('supermini', 'car size classification, larger than a city car and smaller than a small family car'), ('Panthermobile', 'Car from the TV series, The Pink Panther Show'), ('GPU', 'electronic circuit for model training'), ('Silex Piano', 'The Silex Piano is a musical instrument of the Lithophone family.'), ('Apple Watch Series 1', 'Apple Watch Series 1 named Apple smartwatch generation; regional and material hardware variants are configurations.'), ('accordion', 'Accordions are a family of box-shaped musical instruments.')]:
            self.assertIsNone(engineering_role_hint('wikidata', 'class', 'cars', label, desc)[0])

    def test_explicit_models_do_not_require_manufacturing_verb(self):
        self.assertEqual(engineering_role_hint('wikidata', '', 'cars', 'Gardner-Serpollet Type L', 'The Gardner-Serpollet Type L is a 1905 model of steam-powered automobile by Gardner-Serpollet.')[0], 'MODEL')
        self.assertEqual(engineering_role_hint('wikidata', '', 'tractors', 'Fiat 850/850 DT', 'tractor model')[0], 'MODEL')
        self.assertEqual(engineering_role_hint('wikidata', '', 'tractors', 'New Holland T9', 'Articulated tractor series by CNH Industrial')[0], 'MODEL_FAMILY')
        self.assertEqual(engineering_role_hint('wikidata', '', 'locomotives', 'DRG Class 86', 'The DRG Class 86 was a standard goods train tank locomotive.')[0], 'MODEL_FAMILY')

    def test_numbered_vehicle_design_and_unique_object_review(self):
        self.assertEqual(engineering_role_hint('wikidata', '', 'aircraft', 'Caproni Ca.100', 'type of aircraft', 'The Caproni Ca.100 was the standard trainer aircraft of the Regia Aeronautica.')[0], 'MODEL')
        self.assertIsNone(engineering_role_hint('wikidata', '', 'aircraft', 'Custom ABC-100', 'one-off aircraft')[0])

    def test_instrument_invention_does_not_make_a_manufacturer_model(self):
        self.assertIsNone(engineering_role_hint('wikidata', '', 'musical_instruments', 'Swedish lute', 'A Swedish lute is a lute-like musical instrument.', 'The Swedish lute is a musical instrument developed by Swedish instrument makers.')[0])

    def test_nonnumeric_consumer_products_and_standards(self):
        self.assertEqual(engineering_role_hint('wikidata','class','smartphones','BlackBerry Classic','smartphone manufactured by BlackBerry')[0],'MODEL')
        self.assertEqual(engineering_role_hint('wikidata','class','smartphones','iPhone 11','2019 smartphone model produced by Apple Inc.')[0],'MODEL')
        self.assertIsNone(engineering_role_hint('wikidata','class','electronic_components','LPDDR','series of computer memory standards for laptops and mobile devices')[0])

    def test_collective_context_does_not_override_single_model_or_unique_history(self):
        self.assertIsNone(engineering_role_hint('wikidata','class','aircraft','Douglas DC-1','airliner','The Douglas DC-1 was the first model of an aircraft series. Only one example was produced.')[0])
        self.assertEqual(engineering_role_hint('wikidata','class','aircraft','DC-2','airliner','The DC-2 was the second model of the commercial transport aircraft series.')[0],'MODEL')
        self.assertEqual(engineering_role_hint('wikidata','class','locomotives','New Zealand DH class locomotive','diesel-electric locomotive')[0],'MODEL_FAMILY')
        self.assertEqual(engineering_role_hint('wikidata','class','ships','BRP Hilario Ruiz','The BRP Hilario Ruiz is the eighth ship of its class.')[0],'INSTANCE')

    def test_coordinated_functions_and_proposed_design_adjectives(self):
        self.assertEqual(engineering_role_hint('wikidata','class','aircraft','Dassault HU-25 Guardian','search and rescue aircraft family by Dassault')[0],'MODEL_FAMILY')
        self.assertEqual(engineering_role_hint('wikidata','class','aircraft','Il-14LIK','navigation and radar calibration aircraft model by Ilyushin')[0],'MODEL')
        self.assertEqual(engineering_role_hint('wikidata','class','aircraft','F-106E Delta Dart','1968 proposed fighter airplane model by Convair')[0],'MODEL')

    def test_definition_must_describe_its_subject(self):
        self.assertEqual(definition_head('The air itself is the vibrator in the primary sense.','4 Aerophones'),'')
        self.assertEqual(definition_head('Drums with tubular bodies. The membrane is a thin layer.','Tubular drums'),'Drums')
        self.assertEqual(definition_head('The Caproni Ca.100 was a trainer aircraft built by Caproni.','Caproni Ca.100'),'trainer aircraft')
        self.assertEqual(definition_head('Kettle drum from the Tamasheq people.','Akilwa'),'Kettle drum')
        self.assertEqual(definition_head('European Future Advanced Rotorcraft (EuroFAR) was a proposed tiltrotor aircraft.','EuroFAR'),'proposed tiltrotor aircraft')
        text='PWS-40 Junak (Junak literally means "brave young man") was a Polish trainer aircraft of the 1930s.'
        self.assertEqual(engineering_role_hint('wikidata','','aircraft','PWS-40 Junak',text,text)[0],'MODEL')

    def test_verified_subject_aliases_and_diacritics(self):
        text='The Renault Embleme is a crossover concept car unveiled in 2024.'
        self.assertEqual(engineering_role_hint('wikidata','','cars','Renault Emblème','motor vehicle',text)[0],'MODEL')
        current='The Lockheed Martin E-130J is a planned communication relay aircraft.'
        self.assertEqual(definition_head(current,'Lockheed E-XX'),'')
        self.assertEqual(definition_head(current,'Lockheed E-XX',subject_aliases=('Lockheed Martin E-130J',)),'planned communication relay aircraft')
        related='The Honda Brio is a city car produced by Honda.'
        self.assertEqual(definition_head(related,'Honda New Small Concept',subject_aliases=('Honda Small Concept',)),'')
        self.assertEqual(engineering_role_hint('wikidata','','cars','Maxton Rollerskate','American sportscar','The Maxton Rollerskate is an American sports roadster built in the early 1990s.')[0],'MODEL')
        short='BAHA is an unmanned aerial vehicle developed by HAVELSAN.'
        self.assertEqual(engineering_role_hint('wikidata','','aircraft','Havelsan BAHA','aircraft',short)[0],'MODEL')
        self.assertEqual(definition_head('The Brio is a city car produced by Honda.','Honda New Small Concept'),'')

    def test_rank_or_number_alone_does_not_settle_role(self):
        self.assertIsNone(engineering_role_hint('wikidata_v4_p31', 'named_refinement', 'aircraft', 'Unknown 100', '')[0])
        self.assertIsNone(engineering_role_hint('wikidata', 'class', 'cars', 'electric car', 'car powered by electricity')[0])

    def test_individual_vessel_evidence(self):
        self.assertEqual(engineering_role_hint('wikidata', 'class', 'ships', 'Marella Explorer 2', 'Marella Explorer 2 was the lead ship of the Century class.')[0], 'INSTANCE')
        self.assertIsNone(engineering_role_hint('wikidata', 'class', 'ships', 'cruise ship', 'A cruise ship is a passenger ship used for pleasure voyages.')[0])

    def test_independent_developer_and_subject_designation(self):
        self.assertEqual(engineering_role_hint('wikidata','','cars','Alpha Wolf','pickup truck','The Alpha Wolf is an electric pickup truck concept by American electric vehicle company Alpha Motor Corporation.')[0],'MODEL')
        self.assertEqual(engineering_role_hint('wikidata','','aircraft','Texas Aircraft Stallion','ultralight aircraft','The Texas Aircraft Stallion is a light-sport aircraft under development by INPAER.')[0],'MODEL')
        self.assertEqual(engineering_role_hint('wikidata','','aircraft','Partenavia Aeroscooter','type of aircraft','The Partenavia P.53 Aeroscooter was a single-seat light aircraft.')[0],'MODEL')
        self.assertIsNone(engineering_role_hint('wikidata','','aircraft','light aircraft','type of aircraft','A light aircraft is an aircraft under a maximum weight.')[0])
        self.assertEqual(engineering_role_hint('wikidata','','aircraft','ITV Diamant','French paraglider','The ITV Diamant is a French paraglider designed and produced by ITV Parapentes.')[0],'MODEL')
        self.assertEqual(engineering_role_hint('wikidata','','aircraft','Sopwith Gunbus','','The Sopwith Gunbus was a British fighter aircraft of the First World War.')[0],'MODEL')

    def test_generic_class_body_and_redirect_are_not_model_evidence(self):
        self.assertIsNone(engineering_role_hint('wikidata','','cars','station wagon','auto body-style','A station wagon is an automotive body-style variant of a sedan with an extended roof.')[0])
        self.assertIsNone(engineering_role_hint('wikidata','','cars','compact MPV','compact multi-purpose vehicle','Compact MPV is a vehicle size class for the middle size of MPVs. They are built and sold in many countries.')[0])
        self.assertIsNone(engineering_role_hint('wikidata','','cars','Honda New Small Concept','','The Honda Brio is a city car produced by Honda.')[0])
        self.assertIsNone(engineering_role_hint('wikidata','','cars','Vintage car','car','A Vintage car is any car manufactured in a specified historical period.')[0])


if __name__ == '__main__':
    unittest.main()
