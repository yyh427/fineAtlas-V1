import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fineatlas.migration import Migration
from fineatlas.hierarchy import source_assertion_sha256
from fineatlas.nominal_design_scope_contracts import dump, inventory, sha, validate_operations
from fineatlas.structure_nominal_design_scope_repairs import (
    INPUT_NAME, OPERATION_NAME, SOURCE, apply_nominal_design_scope_repairs,
)


class NominalScopeContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.inputs = Path(self.tmp.name)
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.c.executescript('''
            CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,data TEXT,visibility TEXT,source TEXT,rank TEXT,component_id INTEGER,domain TEXT);
            CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,domain TEXT,source_uri TEXT,evidence_id TEXT,attributes TEXT);
            CREATE TABLE normalization_roles(uid TEXT PRIMARY KEY,source_role TEXT,canonical_role TEXT,status TEXT,evidence_id TEXT,source TEXT,prior_profile TEXT);
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE bridges(id INTEGER PRIMARY KEY,left_uid TEXT,right_uid TEXT,relation TEXT,source TEXT,status TEXT,data TEXT);
            CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,relation TEXT,original_relation TEXT,facet_family TEXT,typed_refinement_kind TEXT,classification_basis TEXT,navigation_role TEXT,source TEXT,source_relation TEXT,confidence REAL,provenance TEXT,data TEXT,layer TEXT,status TEXT,reason TEXT);
            CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,relation TEXT,status TEXT,source TEXT,evidence_id TEXT,data TEXT,UNIQUE(subject_uid,object_uid,relation,source));
            CREATE TABLE dataset_targets(dataset TEXT,class_id TEXT,uid TEXT);
            CREATE TABLE dataset_mapping_checks(dataset TEXT,class_id TEXT,status TEXT);
            CREATE TABLE source_catalogs(source TEXT PRIMARY KEY,source_uri TEXT,license TEXT,input_sha256 TEXT,coverage TEXT);
            CREATE TABLE evidence(layer TEXT,id TEXT PRIMARY KEY,source TEXT,source_uri TEXT,retrieved_utc TEXT,claim TEXT,payload TEXT,payload_sha256 TEXT);
            CREATE TABLE usability_changes(id INTEGER PRIMARY KEY,stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT);
        ''')
        for uid, role, component, statement in [
            ('programme', 'MODEL_FAMILY', 1, 'The Example programme is a family of civilian VIP jets.'),
            ('purpose', 'CLASS', 2, 'Civil jet aircraft designed to transport executives and VIPs.'),
            ('variant', 'MODEL', 3, 'A nominal version of the Example programme.'),
            ('propjet', 'CLASS', 4, 'An aircraft class with fixed wings powered by turbine-driven propellers.'),
            ('aircraft', 'CLASS', 5, 'A vehicle capable of flight.'),
        ]:
            self.c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?)', (uid, uid, dump({'definition': statement}), 'ACTIVE', 'source', role.lower(), component, 'fixture'))
            self.c.execute('INSERT INTO node_profiles VALUES(?,?,?,?,?,?)', (uid, role, 'fixture', 'source:original', 'original-eid', '{}'))
        self.frozen = {'inputs': {'old.json': 'original-input-sha'}}
        self.c.executemany('INSERT INTO metadata VALUES(?,?)', [
            ('database_revision', dump('complete-parent')),
            ('structure_frozen_build_manifest', dump(self.frozen)),
            ('root_uid', dump('aircraft')),
        ])
        # Existing complete parent has physical roots for its programme/classes.
        for i, uid, relation in [(1, 'programme', 'DESIGN_TYPE_OF'), (2, 'purpose', 'IS_A'), (3, 'variant', 'DESIGN_TYPE_OF')]:
            if relation == 'IS_A':
                self.c.execute("INSERT INTO edges(id,child_uid,parent_uid,relation,source,status,data) VALUES(? ,?,'aircraft',?,'original','ACTIVE','{}')", (i, uid, relation))
            else:
                self.c.execute("INSERT INTO entity_relations(id,subject_uid,object_uid,relation,status,source,evidence_id,data) VALUES(?,?,'aircraft',?,'ACTIVE','original','old-eid','{}')", (i, uid, relation))
        self.ops = [self.operation('programme', 'purpose', 'DESIGN_TYPE_OF', 'purpose'),
                    self.operation('variant', 'programme', 'NATIVE_DESIGN_PARENT', 'design_family'),
                    self.operation('propjet', 'aircraft', 'IS_A', 'physical_intension')]
        keys = [[o['uid'], o['parent'], o['relation']] for o in self.ops]
        self.semantic = {'accepted_source_scope_only': True, 'approved_source_directions': keys}
        self.semantic_sha = sha(dump(self.semantic))
        for op in self.ops:
            op['proof']['source_review_locator'] = {'file': 'semantic.json', 'sha256': self.semantic_sha, 'uid': op['uid'], 'parent': op['parent'], 'relation': op['relation']}
            op['proof']['source_scope_review_record'] = self.semantic
        self.raw = ''.join(dump(o)+'\n' for o in self.ops).encode()
        self.approval = {'accepted_source_scope_only': True, 'operations_sha256': sha(self.raw), 'approved_keys': keys}
        affected = sorted({o[k] for o in self.ops for k in ('uid', 'parent')})
        self.manifest = {'schema': 'FINEATLAS_NOMINAL_DESIGN_SCOPE_REPAIRS_V1', 'operations_file': OPERATION_NAME, 'operations_sha256': sha(self.raw), 'operation_count': len(self.ops), 'source_review_file': 'approval.json', 'source_review_sha256': sha(dump(self.approval)), 'semantic_review_files': [{'file': 'semantic.json', 'sha256': self.semantic_sha}], 'completed_parent_binding': {'database_revision': 'complete-parent', 'frozen_manifest_sha256': sha(json.dumps(self.frozen, sort_keys=True, ensure_ascii=False))}, 'scope_inventories': {u: inventory(self.c, u) for u in affected}}
        self.reviews = {'semantic.json': {'sha256': self.semantic_sha, 'record': self.semantic}}
        self.c.commit()

    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()

    def operation(self, uid, parent, relation, axis):
        proof = {'kind': 'SOURCE_REVIEWED_WHOLE_NOMINAL_DESIGN_SCOPE', 'classification_axis': axis, 'world_identity_assertion': False, 'no_identity_merges': True, 'whole_subject_scope_review': True, 'scope_observation': 'Complete independent source range is reviewed.', 'license': 'Complete original source attribution retained.', 'prior_assertions': [], 'composition_scope_review': {'whole_parent_range_reviewed': True, 'active_derivation_conflation_absent': True, 'scope_observation': 'Range membership remains distinct from design derivation.', 'non_admitted_derivations': []}}
        witnesses = []
        for current, prefix in [(uid, ''), (parent, 'parent_')]:
            row = dict(self.c.execute('SELECT * FROM nodes WHERE uid=?', (current,)).fetchone())
            proof[prefix+'before_node'] = row
            profile = self.c.execute('SELECT * FROM node_profiles WHERE uid=?', (current,)).fetchone()
            proof[prefix+'before_profile'] = dict(profile) if profile else None
            proof[prefix+'before_normalization_role'] = None
            proof['parent_native_record_sha256' if prefix else 'native_record_sha256'] = sha(row['data'])
            witnesses.append({'uid': current, 'field_path': 'definition', 'statement': json.loads(row['data'])['definition'], 'data_sha256': sha(row['data'])})
        proof['source_witnesses'] = witnesses
        proof['parent_conditions'] = [{'condition': 'Full own source range matches the reviewed parent.', 'exact_spans': [{'witness_index': 0, 'text': witnesses[0]['statement']}, {'witness_index': 1, 'text': witnesses[1]['statement']}]}]
        return {'op': 'link', 'uid': uid, 'parent': parent, 'relation': relation, 'classification_axis': axis, 'source': SOURCE, 'uri': 'https://example.org/source/'+uid, 'proof': proof}

    def validate(self, operations=None, manifest=None, approval=None):
        validate_operations(self.c, manifest or self.manifest, operations or self.ops, approval or self.approval, self.reviews, SOURCE)

    def write_inputs(self):
        for name, data in [(INPUT_NAME, dump(self.manifest).encode()), (OPERATION_NAME, self.raw), ('approval.json', dump(self.approval).encode()), ('semantic.json', dump(self.semantic).encode())]:
            (self.inputs/name).write_bytes(data)

    def migration(self):
        m = Migration.__new__(Migration)
        m.c = self.c
        m.inputs = self.inputs
        return m

    def freeze_changed_operations(self):
        keys = [[o['uid'], o['parent'], o['relation']] for o in self.ops]
        self.semantic['approved_source_directions'] = [k for k, o in zip(keys, self.ops) if o['op'] == 'link']
        self.semantic['approved_source_reviews'] = [k for k, o in zip(keys, self.ops) if o['op'] == 'review_class_edge']
        self.semantic_sha = sha(dump(self.semantic))
        for op in self.ops:
            op['proof']['source_review_locator'] = {'file': 'semantic.json', 'sha256': self.semantic_sha, 'uid': op['uid'], 'parent': op['parent'], 'relation': op['relation']}
            op['proof']['source_scope_review_record'] = self.semantic
        for op in self.ops:
            if op['op'] != 'correct_role':
                continue
            p = op['proof']
            eid = 'usability:'+sha(dump(p))
            prior = op['before_profile']
            attrs = json.loads(prior['attributes']) if prior else {}
            target = op['after_profile']['node_kind']
            status = 'REVIEW' if target == 'UNKNOWN' else 'VERIFIED'
            if p.get('allowed_views') is not None:
                attrs['allowed_views'] = p['allowed_views']
            attrs.update(source_role=p['source_role'], native_rank=p['native_rank'], role_status=status, role_evidence_id=eid)
            attrs.pop('canonical_scope_guard', None); attrs.pop('canonical_scope_evidence_id', None)
            op['after_profile'] = {'uid': op['uid'], 'node_kind': target, 'domain': prior['domain'] if prior else p['before_node']['domain'], 'source_uri': op['uri'], 'evidence_id': eid, 'attributes': dump(attrs)}
            norm=op['before_normalization_role']
            op['after_normalization_role'] = dict(norm, canonical_role=target, evidence_id=eid, source=SOURCE) if norm else {'uid': op['uid'], 'source_role': p['source_role'], 'canonical_role': target, 'status': status, 'evidence_id': eid, 'source': SOURCE, 'prior_profile': dump(prior or {})}
            if target == 'UNKNOWN': op['after_normalization_role']['status']='REVIEW'
        self.raw = ''.join(dump(o)+'\n' for o in self.ops).encode()
        self.approval = {'accepted_source_scope_only': True, 'operations_sha256': sha(self.raw), 'approved_keys': keys}
        self.manifest.update(operations_sha256=sha(self.raw), operation_count=len(self.ops), source_review_sha256=sha(dump(self.approval)), semantic_review_files=[{'file': 'semantic.json', 'sha256': self.semantic_sha}], scope_inventories={u: inventory(self.c, u) for u in sorted({o[k] for o in self.ops for k in ('uid', 'parent')})})
        self.reviews = {'semantic.json': {'sha256': self.semantic_sha, 'record': self.semantic}}

    def add_role_and_review(self):
        role = self.operation('variant', 'variant', 'ROLE_ADJUDICATION', 'source_grain')
        role['op'] = 'correct_role'
        role.update(before_profile=role['proof']['before_profile'], before_normalization_role=None,
                    after_profile={'node_kind': 'MODEL_FAMILY'})
        role['proof'].update(source_role_scope_kind='WHOLE_NOMINAL_MULTIMODEL_PROGRAMME', role_status='VERIFIED', source_role='model', native_rank='model')
        self.semantic['approved_source_role_corrections'] = [{'uid': 'variant', 'before_role': 'MODEL', 'source_role_scope_kind': 'MODEL_FAMILY', 'before_profile': role['before_profile'], 'before_normalization': None}]
        old_data = dump({'admission_basis': {'source_statement': 'A utility object is an airplane or helicopter.'}})
        self.c.execute("INSERT INTO edges(id,child_uid,parent_uid,relation,source,data,status,reason) VALUES(7,'purpose','aircraft','IS_A','retained source',?,'ACTIVE','original judgement')", (old_data,))
        original = dict(self.c.execute('SELECT * FROM edges WHERE id=7').fetchone())
        review = self.operation('purpose', 'aircraft', 'IS_A', 'physical_intension')
        review.update(op='review_class_edge', table='edges', before_assertion=original, content_sha256=source_assertion_sha256(original))
        review['proof']['withdrawn_scope_witness'] = {'table': 'edges', 'before_assertion': original, 'content_sha256': review['content_sha256'], 'data_sha256': sha(old_data), 'field_path': ['admission_basis', 'source_statement'], 'statement': 'A utility object is an airplane or helicopter.', 'witness_kind': 'RETAINED_COMPLETE_SOURCE_STATEMENT'}
        self.ops.extend([role, review])
        self.freeze_changed_operations()

    def new_source_role(self, target, missing_profile=False):
        if missing_profile:
            self.c.execute("DELETE FROM node_profiles WHERE uid='propjet'")
        self.ops = [o for o in self.ops if o['uid'] != 'propjet']
        role = self.operation('propjet','propjet','ROLE_ADJUDICATION','source_grain')
        role.update(op='correct_role', before_profile=role['proof']['before_profile'], before_normalization_role=None, after_profile={'node_kind':target})
        kind={'MODEL':'OWNED_NAMED_REUSABLE_DESIGN_PROGRAMME','INSTANCE':'OWNED_NAMED_OPERATIONAL_PHYSICAL_INSTANCE','UNKNOWN':'SOURCE_NOMINAL_OR_INDIVIDUAL_GRAIN_PENDING'}[target]
        role['proof'].update(source_role_scope_kind=kind, role_status='REVIEW' if target=='UNKNOWN' else 'VERIFIED', source_role='class', native_rank='class')
        self.semantic['approved_source_roles']=[['propjet',target]]
        self.semantic['source_role_records']={'propjet':{'node':role['proof']['before_node'],'node_profiles':role['before_profile'],'normalization_roles':None}}
        if target=='UNKNOWN':
            decision={'after_role_status':'REVIEW','allowed_views':[],'quarantine_role_grain':True}
            self.semantic['source_role_decisions']={'propjet':decision};role['proof'].update(allowed_views=[],quarantine_role_grain=True)
        self.ops.append(role)
        if target!='UNKNOWN':
            self.ops.append(self.operation('propjet','aircraft','INSTANCE_OF' if target=='INSTANCE' else 'DESIGN_TYPE_OF','physical_intension'))
        self.freeze_changed_operations()
        return role

    def test_real_default_class_without_profile_receives_grounded_model_and_physics(self):
        role=self.new_source_role('MODEL',missing_profile=True)
        self.write_inputs();result=apply_nominal_design_scope_repairs(self.migration())
        self.assertEqual(result['role_changes'],1)
        self.assertIsNone(role['before_profile']);self.assertIsNone(role['before_normalization_role'])
        self.assertEqual(dict(self.c.execute("SELECT * FROM normalization_roles WHERE uid='propjet'").fetchone()),role['after_normalization_role'])
        self.assertEqual(role['after_normalization_role']['prior_profile'],'{}')
        self.assertEqual(self.c.execute("SELECT rank FROM nodes WHERE uid='propjet'").fetchone()[0],'class')

    def test_named_instance_has_real_physical_membership_and_complete_history(self):
        role=self.new_source_role('INSTANCE')
        self.write_inputs();apply_nominal_design_scope_repairs(self.migration())
        row=self.c.execute("SELECT * FROM entity_relations WHERE subject_uid='propjet' AND source=?",(SOURCE,)).fetchone()
        self.assertEqual((row['relation'],row['status']),('INSTANCE_OF','ACTIVE'))
        self.assertEqual(dict(self.c.execute("SELECT * FROM node_profiles WHERE uid='propjet'").fetchone()),role['after_profile'])

    def test_unknown_source_grain_helper_writes_review_and_disables_navigation(self):
        role=self.new_source_role('UNKNOWN',missing_profile=True)
        self.write_inputs();apply_nominal_design_scope_repairs(self.migration())
        profile=dict(self.c.execute("SELECT * FROM node_profiles WHERE uid='propjet'").fetchone())
        norm=dict(self.c.execute("SELECT * FROM normalization_roles WHERE uid='propjet'").fetchone())
        self.assertEqual((profile['node_kind'],norm['status']),('UNKNOWN','REVIEW'))
        self.assertEqual(json.loads(profile['attributes'])['allowed_views'],[])
        self.assertEqual(profile,role['after_profile']);self.assertEqual(norm,role['after_normalization_role'])
        meta=json.loads(self.c.execute("SELECT value FROM metadata WHERE key='nominal_design_scope_repairs'").fetchone()[0])
        self.assertEqual(meta['navigation_disabled_source_grain_uids'],['propjet'])

    def test_pending_list_is_not_permission_to_quarantine_source_object(self):
        self.new_source_role('UNKNOWN')
        del self.semantic['source_role_decisions']['propjet']['quarantine_role_grain'];self.freeze_changed_operations()
        with self.assertRaisesRegex(ValueError,'explicit independent quarantine'):
            self.validate()

    def test_role_correction_cannot_leave_old_class_inclusion_active(self):
        self.c.execute("INSERT INTO edges(id,child_uid,parent_uid,relation,source,status,data) VALUES(8,'propjet','aircraft','IS_A','old','ACTIVE','{}')")
        self.new_source_role('MODEL')
        with self.assertRaisesRegex(ValueError,'IS_A cannot join MODEL'):
            self.validate()

    def test_two_original_class_rows_same_direction_are_both_exactly_reviewed(self):
        self.add_role_and_review();second=copy.deepcopy(self.ops[-1]);second['before_assertion']['id']=8
        cols=list(second['before_assertion']);self.c.execute('INSERT INTO edges('+','.join(cols)+') VALUES('+','.join('?'for _ in cols)+')',tuple(second['before_assertion'].values()))
        second['proof']['withdrawn_scope_witness']['before_assertion']=second['before_assertion'];self.ops.append(second);self.freeze_changed_operations()
        self.write_inputs();result=apply_nominal_design_scope_repairs(self.migration())
        self.assertEqual(result['class_scope_reviews'],2)
        self.assertEqual([r[0]for r in self.c.execute('SELECT status FROM edges WHERE id IN(7,8) ORDER BY id')],['SOURCE_SCOPE_REVIEW']*2)
        self.assertEqual(self.c.execute("SELECT count(*) FROM usability_changes WHERE object_type='class_scope_review'").fetchone()[0],2)

    def test_all_three_scoped_relations_validate(self):
        self.validate()

    def test_source_range_cannot_be_changed_behind_same_label(self):
        self.c.execute("UPDATE nodes SET data='{}' WHERE uid='programme'")
        with self.assertRaisesRegex(ValueError, 'source endpoint'):
            self.validate()

    def test_parent_conditions_require_exact_owned_spans(self):
        ops = copy.deepcopy(self.ops)
        ops[0]['proof']['parent_conditions'][0]['exact_spans'][0]['text'] = 'a complete cargo family'
        with self.assertRaisesRegex(ValueError, 'outside its complete source field'):
            self.validate(operations=ops)

    def test_nominal_derivation_cannot_silently_inherit_purpose(self):
        self.c.execute("INSERT INTO entity_relations VALUES(4,'variant','programme','NATIVE_DESIGN_PARENT','ACTIVE','original','old-eid','{}')")
        original = dict(self.c.execute('SELECT * FROM entity_relations WHERE id=4').fetchone())
        from fineatlas.hierarchy import source_assertion_sha256
        ops = copy.deepcopy(self.ops)
        ops[0]['proof']['composition_scope_review']['non_admitted_derivations'] = [{'table': 'entity_relations', 'before_assertion': original, 'content_sha256': source_assertion_sha256(original)}]
        with self.assertRaisesRegex(ValueError, 'must not inherit'):
            self.validate(operations=ops)

    def test_unsupported_axis_and_wrong_role_are_rejected(self):
        ops = copy.deepcopy(self.ops)
        ops[1]['classification_axis'] = 'purpose'
        with self.assertRaisesRegex(ValueError, 'axis'):
            self.validate(operations=ops)
        self.c.execute("UPDATE node_profiles SET node_kind='MODEL' WHERE uid='purpose'")
        with self.assertRaisesRegex(ValueError, 'profile changed'):
            self.validate()

    def test_component_bucket_does_not_allow_unbridged_source_body(self):
        row = self.ops[0]['proof']['before_node']
        self.c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?)', ('lookalike', 'lookalike', row['data'], 'ACTIVE', 'other', 'model_family', 1, 'fixture'))
        self.c.execute("INSERT INTO node_profiles VALUES('lookalike','MODEL_FAMILY','fixture','source:other','original-eid','{}')")
        ops = copy.deepcopy(self.ops)
        ops[0]['proof']['source_witnesses'][0]['uid'] = 'lookalike'
        with self.assertRaisesRegex(ValueError, 'admitted same-role identity path'):
            self.validate(operations=ops)

    def test_extra_review_key_and_boolean_count_fail_closed(self):
        approval = copy.deepcopy(self.approval)
        approval['approved_keys'].append(['unreviewed', 'purpose', 'DESIGN_TYPE_OF'])
        with self.assertRaisesRegex(ValueError, 'exactly all operations'):
            self.validate(approval=approval)
        manifest = copy.deepcopy(self.manifest)
        manifest['operation_count'] = True
        with self.assertRaisesRegex(ValueError, 'operation count'):
            self.validate(manifest=manifest)

    def test_parent_incoming_inventory_is_not_a_waiver(self):
        self.c.execute("INSERT INTO entity_relations VALUES(4,'variant','programme','NATIVE_DESIGN_PARENT','ACTIVE','other','old-eid','{}')")
        with self.assertRaisesRegex(ValueError, 'composition changed'):
            self.validate()

    def test_real_migration_appends_types_family_and_class_with_exact_evidence(self):
        self.write_inputs()
        before = [tuple(r) for r in self.c.execute('SELECT * FROM nodes ORDER BY uid')]
        result = apply_nominal_design_scope_repairs(self.migration())
        self.assertEqual(result['source_assertions_added'], 3)
        self.assertEqual(before, [tuple(r) for r in self.c.execute('SELECT * FROM nodes ORDER BY uid')])
        rows = self.c.execute('SELECT * FROM entity_relations WHERE source=? ORDER BY id', (SOURCE,)).fetchall()
        self.assertEqual(len(rows), 2)
        for row, op in zip(rows, self.ops):
            eid = 'usability:'+sha(dump(op['proof']))
            self.assertEqual(row['evidence_id'], eid)
            self.assertEqual(json.loads(row['data'])['classification_axis'], op['classification_axis'])
            self.assertEqual(self.c.execute('SELECT payload FROM evidence WHERE id=?', (eid,)).fetchone()[0], dump(op['proof']))
        edge = self.c.execute('SELECT * FROM edges WHERE source=?', (SOURCE,)).fetchone()
        self.assertEqual(edge['status'], 'ACTIVE')
        self.assertTrue(json.loads(edge['data'])['eligible_for_final_dag'])
        histories = self.c.execute("SELECT * FROM usability_changes WHERE stage='nominal_design_scope_repairs'").fetchall()
        self.assertEqual(len(histories), 3)
        self.assertTrue(all(r['object_type'] == 'nominal_scope_link' for r in histories))
        self.assertEqual(json.loads(histories[2]['after_json'])['added_assertion'], dict(edge))

    def test_actual_apply_failure_rolls_back_all_new_rows(self):
        self.write_inputs()
        self.c.execute('INSERT INTO source_catalogs VALUES(?,?,?,?,?)', ('Hierarchy refinement: '+SOURCE, 'old-uri', 'old-license', 'old-sha', '{}'))
        self.c.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            apply_nominal_design_scope_repairs(self.migration())
        self.assertEqual(self.c.execute('SELECT count(*) FROM edges').fetchone()[0], 1)
        self.assertEqual(self.c.execute('SELECT count(*) FROM entity_relations').fetchone()[0], 2)
        for table in ('evidence', 'usability_changes'):
            self.assertEqual(self.c.execute('SELECT count(*) FROM '+table).fetchone()[0], 0)

    def test_real_mixed_apply_corrects_role_and_reviews_only_original_status(self):
        self.add_role_and_review()
        original = dict(self.c.execute('SELECT * FROM edges WHERE id=7').fetchone())
        self.write_inputs()
        result = apply_nominal_design_scope_repairs(self.migration())
        self.assertEqual((result['source_assertions_added'], result['role_changes'], result['class_scope_reviews']), (3, 1, 1))
        self.assertEqual(dict(self.c.execute('SELECT * FROM edges WHERE id=7').fetchone()), dict(original, status='SOURCE_SCOPE_REVIEW'))
        role = self.ops[3]
        self.assertEqual(dict(self.c.execute("SELECT * FROM node_profiles WHERE uid='variant'").fetchone()), role['after_profile'])
        self.assertEqual(dict(self.c.execute("SELECT * FROM normalization_roles WHERE uid='variant'").fetchone()), role['after_normalization_role'])
        history = self.c.execute("SELECT * FROM usability_changes WHERE stage='nominal_design_scope_repairs' AND object_type='role_source_adjudication'").fetchone()
        self.assertEqual(json.loads(history['after_json'])['profile'], role['after_profile'])
        meta = json.loads(self.c.execute("SELECT value FROM metadata WHERE key='nominal_design_scope_repairs'").fetchone()[0])
        self.assertEqual(meta['allowed_role_differences'], ['variant'])

    def test_role_evidence_must_use_real_compact_migration_encoding(self):
        self.add_role_and_review()
        self.ops[3]['after_profile']['evidence_id'] = 'usability:'+sha(json.dumps(self.ops[3]['proof'], sort_keys=True, ensure_ascii=False))
        with self.assertRaisesRegex(ValueError, 'Migration canonical encoding'):
            self.validate()

    def test_retained_statement_cannot_be_borrowed_from_unrelated_node(self):
        self.add_role_and_review()
        self.ops[4]['proof']['withdrawn_scope_witness']['statement'] = 'A utility object is always fixed-wing.'
        with self.assertRaisesRegex(ValueError, 'retained assertion range witness'):
            self.validate()

    def test_all_owned_definition_fields_are_required(self):
        self.c.execute("UPDATE nodes SET data=? WHERE uid='programme'", (dump({'definition': 'The Example programme is a family of civilian VIP jets.', 'description': 'This family also includes cargo derivatives.'}),))
        ops = copy.deepcopy(self.ops)
        row = dict(self.c.execute("SELECT * FROM nodes WHERE uid='programme'").fetchone())
        for op in ops:
            p = op['proof']
            for prefix, uid in [('', op['uid']), ('parent_', op['parent'])]:
                if uid == 'programme':
                    p[prefix+'before_node'] = row
                    p['parent_native_record_sha256' if prefix else 'native_record_sha256'] = sha(row['data'])
            for w in p['source_witnesses']:
                if w['uid'] == 'programme':
                    w['data_sha256'] = sha(row['data'])
        with self.assertRaisesRegex(ValueError, 'Every retained whole'):
            self.validate(operations=ops)

    def test_two_new_class_links_cannot_form_a_batch_cycle(self):
        reverse = self.operation('aircraft', 'propjet', 'IS_A', 'physical_intension')
        self.ops.append(reverse)
        self.freeze_changed_operations()
        with self.assertRaisesRegex(ValueError, 'canonical component cycle'):
            self.validate()

    def test_parent_scope_without_root_cannot_be_declared_connected(self):
        self.c.execute("UPDATE edges SET status='SOURCE_SCOPE_REVIEW' WHERE child_uid='purpose'")
        self.manifest['scope_inventories']['purpose'] = inventory(self.c, 'purpose')
        self.manifest['scope_inventories']['aircraft'] = inventory(self.c, 'aircraft')
        with self.assertRaisesRegex(ValueError, 'legitimate planned root path'):
            self.validate()

    def test_active_identity_alias_cannot_hide_a_component_cycle(self):
        self.c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?)', ('prop-alias', 'alias', dump({'definition': 'A turbine-powered airplane class.'}), 'ACTIVE', 'source', 'class', 4, 'fixture'))
        self.c.execute("INSERT INTO node_profiles VALUES('prop-alias','CLASS','fixture','source:alias','old','{}')")
        self.c.execute("INSERT INTO bridges VALUES(1,'propjet','prop-alias','SAME_CONCEPT','source','ACTIVE','{}')")
        self.c.execute("INSERT INTO edges(id,child_uid,parent_uid,relation,source,status,data) VALUES(5,'aircraft','prop-alias','IS_A','original','ACTIVE','{}')")
        self.manifest['scope_inventories'] = {u: inventory(self.c, u) for u in list(self.manifest['scope_inventories'])+['prop-alias']}
        with self.assertRaisesRegex(ValueError, 'canonical component cycle'):
            self.validate()

    def test_role_change_cannot_drop_a_legal_existing_parent_relation(self):
        self.add_role_and_review()
        self.c.execute("INSERT INTO entity_relations VALUES(5,'variant','programme','SERIES_MEMBER_OF','ACTIVE','original','old-eid','{}')")
        self.manifest['scope_inventories']['variant'] = inventory(self.c, 'variant')
        self.manifest['scope_inventories']['programme'] = inventory(self.c, 'programme')
        with self.assertRaisesRegex(ValueError, 'SERIES_MEMBER_OF cannot join MODEL_FAMILY'):
            self.validate()

    def test_late_mixed_apply_failure_restores_roles_and_reviewed_old_rows(self):
        self.add_role_and_review()
        original_profile = dict(self.c.execute("SELECT * FROM node_profiles WHERE uid='variant'").fetchone())
        original_edge = dict(self.c.execute('SELECT * FROM edges WHERE id=7').fetchone())
        self.c.execute('INSERT INTO source_catalogs VALUES(?,?,?,?,?)', ('Hierarchy refinement: '+SOURCE, 'old-uri', 'old-license', 'old-sha', '{}'))
        self.c.commit()
        self.write_inputs()
        with self.assertRaises(sqlite3.IntegrityError):
            apply_nominal_design_scope_repairs(self.migration())
        self.assertEqual(dict(self.c.execute("SELECT * FROM node_profiles WHERE uid='variant'").fetchone()), original_profile)
        self.assertEqual(dict(self.c.execute('SELECT * FROM edges WHERE id=7').fetchone()), original_edge)
        self.assertEqual(self.c.execute('SELECT count(*) FROM normalization_roles').fetchone()[0], 0)
        self.assertEqual(self.c.execute('SELECT count(*) FROM evidence').fetchone()[0], 0)
        self.assertEqual(self.c.execute('SELECT count(*) FROM usability_changes').fetchone()[0], 0)

    def test_typed_active_isa_is_not_an_admitted_root_path(self):
        self.c.execute("UPDATE edges SET status='TYPED_ACTIVE' WHERE child_uid='purpose'")
        self.manifest['scope_inventories']['purpose'] = inventory(self.c, 'purpose')
        self.manifest['scope_inventories']['aircraft'] = inventory(self.c, 'aircraft')
        with self.assertRaisesRegex(ValueError, 'legitimate planned root path'):
            self.validate()

    def test_regulatory_reference_is_not_a_physical_ancestor(self):
        self.c.execute("DELETE FROM edges WHERE child_uid='purpose'")
        self.c.execute("INSERT INTO entity_relations VALUES(5,'purpose','aircraft','REGULATED_AS','ACTIVE','original','old-eid','{}')")
        self.manifest['scope_inventories']['purpose'] = inventory(self.c, 'purpose')
        self.manifest['scope_inventories']['aircraft'] = inventory(self.c, 'aircraft')
        with self.assertRaisesRegex(ValueError, 'legitimate planned root path'):
            self.validate()

    def test_membership_only_source_cannot_claim_unified_admission(self):
        self.c.execute("UPDATE node_profiles SET attributes=? WHERE uid='purpose'", (dump({'allowed_views': ['membership', 'unified']}),))
        self.ops = [self.operation('programme', 'purpose', 'DESIGN_TYPE_OF', 'purpose'), self.operation('variant', 'programme', 'NATIVE_DESIGN_PARENT', 'design_family'), self.operation('propjet', 'aircraft', 'IS_A', 'physical_intension')]
        self.freeze_changed_operations()
        with self.assertRaisesRegex(ValueError, 'actual unified source view'):
            self.validate()


if __name__ == '__main__':
    unittest.main()
