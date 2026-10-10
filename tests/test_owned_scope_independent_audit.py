"""Independent SQL/source checks fail on same-name and local-file shortcuts."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_owned_scope_repairs as audit


class IndependentOwnedSourceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.con = sqlite3.connect(':memory:')
        self.con.row_factory = sqlite3.Row
        self.con.executescript('''
          CREATE TABLE nodes(uid TEXT, data TEXT, rank TEXT, component_id INTEGER,
                             visibility TEXT, label TEXT);
          CREATE TABLE node_profiles(uid TEXT,node_kind TEXT);
          CREATE TABLE bridges(id INTEGER,left_uid TEXT,right_uid TEXT,relation TEXT,status TEXT);
          CREATE TABLE edges(id INTEGER,data TEXT,child_uid TEXT);
        ''')
        for uid in ('design-a', 'source-a'):
            self.con.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?)',
                             (uid, '{}', 'model', 1, 'ACTIVE', 'Shared name'))
            self.con.execute('INSERT INTO node_profiles VALUES(?,?)', (uid, 'MODEL'))

    def tearDown(self):
        self.con.close()
        self.temp.cleanup()

    def test_shared_component_and_name_do_not_prove_owned_source_identity(self):
        self.assertFalse(audit.identity_peer(self.con, 'design-a', 'source-a'))

    def test_source_evidence_must_be_attached_to_the_navigable_edge(self):
        row = {'status': 'TYPED_ACTIVE', 'provenance': json.dumps({'evidence_ids': ['own']}),
               'data': json.dumps({'eligible_for_final_typed_graph': True, 'eligible_for_final_dag': False})}
        audit.verify_edge_grounding(row, 'own', 'TAXONOMIC_PARENT')
        with self.assertRaisesRegex(ValueError, 'evidence reference'):
            audit.verify_edge_grounding(row, 'unrelated', 'TAXONOMIC_PARENT')
        row['data'] = json.dumps({'eligible_for_final_typed_graph': False, 'eligible_for_final_dag': False})
        with self.assertRaisesRegex(ValueError, 'scientific typed graph'):
            audit.verify_edge_grounding(row, 'own', 'TAXONOMIC_PARENT')
        row['data'] = json.dumps({'eligible_for_final_typed_graph': True, 'eligible_for_final_dag': True})
        with self.assertRaisesRegex(ValueError, 'distinct scientific relation'):
            audit.verify_edge_grounding(row, 'own', 'TAXONOMIC_PARENT')

    def test_abbreviated_design_name_does_not_truncate_real_type_assertion(self):
        statement = 'The G.A.C. 102 Aristocrat is a cabin monoplane built in the US.'
        self.assertEqual(audit.own_assertion_phrase(statement), 'a cabin monoplane')
        self.assertNotIn('glider', audit.own_assertion_phrase(
            'The Prototype is an aircraft derived from a glider.'))

    def test_universal_variant_scope_does_not_generalize_some_variants(self):
        statement = 'The Model family were aircraft. All variants were single-engine monoplanes with landing gear.'
        self.assertIn('monoplanes', audit.scoped_assertion_phrase(statement, 'OWNED_UNIVERSAL_VARIANTS', 'Model'))
        with self.assertRaisesRegex(ValueError, 'all-variants'):
            audit.scoped_assertion_phrase(statement.replace('All variants', 'Some variants'),
                                          'OWNED_UNIVERSAL_VARIANTS', 'Model')

    def test_anaphor_is_bound_to_named_own_design_and_positive_claim(self):
        statement = 'The Model family is a series of aircraft. The twinjet has six-abreast seating.'
        self.assertIn('twinjet', audit.scoped_assertion_phrase(statement, 'OWNED_SELF_TWINJET', 'Model family'))
        with self.assertRaisesRegex(ValueError, 'named own'):
            audit.scoped_assertion_phrase(statement, 'OWNED_SELF_TWINJET', 'Other family')
        with self.assertRaisesRegex(ValueError, 'absent or incompatible'):
            audit.scoped_assertion_phrase(statement.replace('has six', 'has never had six'),
                                          'OWNED_SELF_TWINJET', 'Model family')

    def test_named_member_is_an_instance_without_equating_it_with_design(self):
        source = 'The Model EX is an early biplane built by the maker. Two examples were built. One of them—the Flyer—crossed the country.'
        self.assertIn('biplane', audit.named_instance_phrase(source, 'Flyer'))
        with self.assertRaisesRegex(ValueError, 'explicitly identified'):
            audit.named_instance_phrase(source, 'Another Flyer')
        with self.assertRaisesRegex(ValueError, 'explicitly identified'):
            audit.named_instance_phrase(source.replace('One of them—the Flyer—', 'The prototype'), 'Flyer')
        with self.assertRaisesRegex(ValueError, 'prototype count'):
            audit.named_instance_phrase(source.replace('The Model EX', 'The Flyer'), 'Flyer')

    def test_instance_role_is_incompatible_with_design_type_link(self):
        self.assertTrue(audit.role_valid(self.con, 'INSTANCE_OF',
            {'uid':'design-a','rank':'model'}, {'uid':'class','rank':''}, {'design-a':'INSTANCE'}))

    def test_owned_version_and_series_roles_are_not_copied_from_peer(self):
        self.assertEqual(audit.independently_declared_role('training version of the base aircraft', 'Version',
                         'OWNED_NOMINAL_DESIGN_ROLE'), 'MODEL')
        self.assertEqual(audit.independently_declared_role('unmanned aerial target series', 'Series',
                         'OWNED_NOMINAL_DESIGN_ROLE'), 'MODEL_FAMILY')
        with self.assertRaisesRegex(ValueError, 'independently declare'):
            audit.independently_declared_role('kamikaze drone', 'Drone', 'OWNED_NOMINAL_DESIGN_ROLE')

    def test_modified_example_alone_preserves_role_ambiguity(self):
        self.assertEqual(audit.independently_declared_role('spin trial aircraft, modified example of the base',
                         'Version', 'OWNED_UNRESOLVED_DESIGN_VERSUS_MODIFIED_EXAMPLE'), 'UNKNOWN')
        with self.assertRaisesRegex(ValueError, 'explicitly identified'):
            audit.independently_declared_role('spin trial aircraft, modified example of the base', 'Version', None)

    def test_horticultural_source_cannot_supply_industrial_model_role(self):
        self.assertEqual(audit.independently_declared_role('apple cultivar', 'Cultivar',
                         'OWNED_HORTICULTURAL_VARIANT_ROLE'), 'BIOLOGICAL_VARIANT')
        with self.assertRaisesRegex(ValueError, 'explicit whole-source'):
            audit.independently_declared_role('apple cultivar', 'Cultivar', 'UNREVIEWED_PEER_ROLE')
        self.assertFalse(audit.role_valid(self.con, 'DESIGN_TYPE_OF',
            {'uid':'design-a','rank':'model'}, {'uid':'class','rank':''}, {'design-a':'INSTANCE'}))

    def test_resulting_own_design_kind_does_not_inherit_predecessor_kind(self):
        statement = 'The Model was a development of the earlier glider into a two-seat airplane.'
        self.assertIn('airplane', audit.own_assertion_phrase(statement))
        self.assertNotIn('glider', audit.own_assertion_phrase(statement))

    def test_proposed_design_kind_survives_unbuilt_status(self):
        statement = 'The Model was a proposed assault glider. None was built.'
        self.assertIn('glider', audit.own_assertion_phrase(statement))
        self.assertNotIn('not', audit.own_assertion_phrase('The Model was a prototype biplane proposed but not built.'))

    def test_reconfigurable_geometry_keeps_only_common_fixed_wing_scope(self):
        source = 'The Model was an amateur built aircraft that could fly either as a biplane or as a parasol winged monoplane.'
        self.assertEqual(audit.scoped_assertion_phrase(source, 'OWNED_COMPLETE_RECONFIGURABLE_FIXED_WING', 'Model'),
                         'biplane or parasol monoplane')
        with self.assertRaisesRegex(ValueError, 'structural alternatives'):
            audit.scoped_assertion_phrase(source.replace('could fly either', 'could never fly'),
                                         'OWNED_COMPLETE_RECONFIGURABLE_FIXED_WING', 'Model')

    def test_retired_identity_claim_cannot_supply_an_own_source_witness(self):
        self.con.execute("INSERT INTO bridges VALUES(1,'design-a','source-a','SAME_CONCEPT','SOURCE_SCOPE_REVIEW')")
        self.assertFalse(audit.identity_peer(self.con, 'design-a', 'source-a'))

    def test_active_identity_peer_preserves_own_role_scope(self):
        self.con.execute("INSERT INTO bridges VALUES(1,'design-a','source-a','SAME_CONCEPT','ACTIVE')")
        self.assertTrue(audit.identity_peer(self.con, 'design-a', 'source-a'))
        self.con.execute("UPDATE node_profiles SET node_kind='MODEL_FAMILY' WHERE uid='source-a'")
        self.assertFalse(audit.identity_peer(self.con, 'design-a', 'source-a'))

    def test_retained_definition_field_is_checked_in_original_source_bytes(self):
        raw = json.dumps({'admission_basis': {'source_statement': 'A car is a motor vehicle with wheels.'}})
        self.con.execute('INSERT INTO edges VALUES(1,?,?)', (raw, 'design-a'))
        witness = {'table': 'edges', 'id': 1, 'field': 'admission_basis.source_statement',
                   'statement': 'A car is a motor vehicle with wheels.', 'data_sha256': audit.sha(raw)}
        self.assertEqual(audit.source_witness(self.con, witness)['data'], raw)
        self.con.execute('UPDATE edges SET data=?', (raw.replace('motor vehicle', 'four-wheel car'),))
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            audit.source_witness(self.con, witness)

    def test_full_retained_definition_cannot_be_borrowed_from_another_subject(self):
        raw = json.dumps({'admission_basis': {'source_statement': 'A car is a motor vehicle.'}})
        self.con.execute('INSERT INTO edges VALUES(1,?,?)', (raw, 'design-a'))
        before = dict(self.con.execute('SELECT * FROM edges').fetchone())
        witness = {'table': 'edges', 'before': before, 'before_fullrow_sha256': audit.sha(audit.dump(before)),
                   'field_path': ['admission_basis', 'source_statement'], 'statement': 'A car is a motor vehicle.',
                   'original_source_uri': 'https://source.example/car'}
        self.assertEqual(audit.source_assertion_witness(self.con, witness, 'design-a'), witness['statement'])
        with self.assertRaisesRegex(ValueError, 'own source assertion'):
            audit.source_assertion_witness(self.con, witness, 'source-a')

    def test_whole_definition_evidence_uses_actual_payload_hash(self):
        self.con.execute('CREATE TABLE evidence(evidence_id TEXT,payload TEXT,payload_sha256 TEXT)')
        raw = audit.dump({'child_uid':'design-a','sentence':'A cultivar of domesticated apple.'})
        self.con.execute('INSERT INTO evidence VALUES(?,?,?)', ('definition',raw,audit.sha(raw)))
        witness = {'table':'evidence','evidence_id':'definition','field':'sentence',
                   'statement':'A cultivar of domesticated apple.','data_sha256':audit.sha(raw)}
        self.assertEqual(audit.source_witness(self.con,witness)['payload'],raw)
        self.con.execute("UPDATE evidence SET payload_sha256='wrong'")
        with self.assertRaisesRegex(ValueError,'payload index'):
            audit.source_witness(self.con,witness)

    def test_cultivar_host_requires_living_taxon_not_fruit_or_species_promotion(self):
        child={'uid':'design-a','rank':'biological_variant'}
        parent={'uid':'host','rank':'species','label':'Malus domestica',
                'data':audit.dump({'wikidata_description':'species of plant'})}
        own={'uid':'design-a','statement':'A cultivar of domesticated apple.'}
        host={'uid':'host','statement':'The domestic apple (Malus domestica) is a cultivated tree.'}
        before={'id':3,'data':'{}','child_uid':'design-a'}
        self.con.execute('INSERT INTO edges VALUES(?,?,?)',(3,'{}','design-a'))
        scope={'parent_taxon_rank':'species','child_remains_biological_variant':True,
               'source_host_not_fruit':True,'species_identity_assertion':False,
               'host_scientific_name':'Malus domestica','parent_owned_host_phrase':'domestic apple (Malus domestica)',
               'child_owned_host_phrase':'cultivar of domesticated apple',
               'retained_primary_taxonomic_or_classifier_assertions':[before]}
        op={'uid':'design-a','relation':'TAXONOMIC_PARENT',
            'proof':{'host_taxon_scope_review':scope,'source_witnesses':[own,host]}}
        audit.verify_biological_host_scope(self.con,op,child,parent,{'design-a':'BIOLOGICAL_VARIANT'}, {})
        fruit={**parent,'data':audit.dump({'wikidata_description':'edible fruit of an apple tree'})}
        with self.assertRaisesRegex(ValueError,'living scientific taxon'):
            audit.verify_biological_host_scope(self.con,op,child,fruit,{'design-a':'BIOLOGICAL_VARIANT'}, {})
        scope['species_identity_assertion']=True
        with self.assertRaisesRegex(ValueError,'biological grain'):
            audit.verify_biological_host_scope(self.con,op,child,parent,{'design-a':'BIOLOGICAL_VARIANT'}, {})

    def test_historical_absolute_primary_path_is_not_a_download_locator(self):
        path = self.root / 'unpublished.pdf'
        path.write_bytes(b'official source fixture')
        operations = [{'proof': {'document': {'source_kind': 'PRIMARY_MANUFACTURER_OR_REGULATOR',
                       'source_uri': 'https://manufacturer.example/spec.pdf',
                       'sha256': audit.sha(path.read_bytes()), 'local_snapshot_path': str(path)}}}]
        with self.assertRaisesRegex(ValueError, 'Explicit portable'):
            audit.verify_primary_sources(self.root, operations, None)
        with self.assertRaisesRegex(ValueError, 'portable byte locator'):
            audit.verify_primary_sources(self.root, operations, self.root)

    def test_explicit_primary_registry_requires_complete_matching_bytes(self):
        path = self.root / 'spec.pdf'; path.write_bytes(b'complete original source')
        doc = {'source_uri': 'https://manufacturer.example/spec.pdf', 'sha256': audit.sha(path.read_bytes()),
               'filename': 'spec.pdf', 'hash_basis': 'HTTP_RESPONSE_BODY_BYTES'}
        (self.root / 'structure_primary_source_snapshots.json').write_text(json.dumps({
            'schema': 'FINEATLAS_PORTABLE_PRIMARY_SOURCE_SNAPSHOTS_V1', 'documents': {'spec': doc}}))
        ops = [{'proof': {'document': {**doc, 'source_kind': 'PRIMARY_MANUFACTURER_OR_REGULATOR'}}}]
        self.assertEqual(set(audit.verify_primary_sources(self.root, ops, self.root)), {'spec.pdf'})
        path.write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            audit.verify_primary_sources(self.root, ops, self.root)

    def test_primary_registry_cannot_escape_explicit_source_directory(self):
        doc = {'source_uri': 'https://manufacturer.example/spec.pdf', 'sha256': '0' * 64,
               'filename': '../external.pdf', 'hash_basis': 'HTTP_RESPONSE_BODY_BYTES'}
        (self.root / 'structure_primary_source_snapshots.json').write_text(json.dumps({
            'schema': 'FINEATLAS_PORTABLE_PRIMARY_SOURCE_SNAPSHOTS_V1', 'documents': {'spec': doc}}))
        ops = [{'proof': {'document': {**doc, 'source_kind': 'PRIMARY_MANUFACTURER_OR_REGULATOR'}}}]
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            audit.verify_primary_sources(self.root, ops, self.root)

    def test_full_annotation_join_is_distinct_from_approved_subset(self):
        files = []
        for split, beginning, end in (('train', 0, 34), ('val', 34, 67), ('test', 67, 100)):
            for field in ('variant', 'family', 'manufacturer'):
                lines = []
                for variant in range(100):
                    for index in range(beginning, end):
                        value = 'Model ' + str(variant) if field == 'variant' else 'Common ' + field
                        lines.append(str(variant * 100 + index).zfill(7) + ' ' + value)
                raw = ('\n'.join(lines) + '\n').encode()
                name = 'images_' + field + '_' + split + '.txt'
                (self.root / name).write_bytes(raw)
                files.append({'file': name, 'sha256': audit.sha(raw), 'bytes': len(raw)})
        manifest = {'author_annotation_files': files}
        records = audit.author_annotations(self.root, manifest)
        self.assertEqual(len(records), 10000)
        self.assertEqual(sum(r['variant'] == 'Model 42' for r in records), 100)
        (self.root / files[0]['file']).write_bytes(b'approved subset only\n')
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            audit.author_annotations(self.root, manifest)


if __name__ == '__main__':
    unittest.main()
