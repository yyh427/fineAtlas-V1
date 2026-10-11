"""Independent raw SQL role/withdrawal observers reject unbound later changes."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import independent_nominal_design_scope_final_interface_audit as audit


def payload(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


class ExactNominalTransitions(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.inputs=Path(self.temp.name)
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row;self.addCleanup(self.c.close)
        node={'uid':'own-family','data':payload({'description':'whole family with four nominal series'}),'component_id':1,'visibility':'ACTIVE','rank':'model'}
        profile={'uid':node['uid'],'node_kind':'MODEL','attributes':payload({'native_rank':'model','source_role':'nominal','role_status':'VERIFIED','role_evidence_id':'old'}),'evidence_id':'old','source_uri':'https://example.invalid/old'}
        norm={'uid':node['uid'],'canonical_role':'MODEL','source_role':'nominal','prior_profile':'{}','status':'VERIFIED','evidence_id':'old','source':'old'}
        review={'accepted_source_scope_only':True,'approved_source_role_corrections':[{'uid':node['uid'],'before_role':'MODEL','source_role_scope_kind':'MODEL_FAMILY','before_profile':profile,'before_normalization':norm}]}
        path=self.inputs/'source-review.json';path.write_text(payload(review))
        proof={'whole_subject_scope_review':True,'world_identity_assertion':False,'no_identity_merges':True,'before_node':node,'native_record_sha256':hashlib.sha256(node['data'].encode()).hexdigest(),'source_review_locator':{'file':path.name,'sha256':audit.digest(path)},'source_scope_review_record':review,'source_witnesses':[{'uid':node['uid'],'data_sha256':hashlib.sha256(node['data'].encode()).hexdigest(),'field_path':'description','statement':'whole family with four nominal series'}]}
        proof.update(source_role_scope_kind='WHOLE_NOMINAL_MULTIMODEL_PROGRAMME',role_status='VERIFIED',source_role='nominal',native_rank='model')
        eid='usability:'+hashlib.sha256(payload(proof).encode()).hexdigest()
        attrs={**json.loads(profile['attributes']),'role_evidence_id':eid}
        after_profile={**profile,'node_kind':'MODEL_FAMILY','attributes':payload(attrs),'evidence_id':eid,'source_uri':'https://example.invalid/source'}
        after_norm={**norm,'canonical_role':'MODEL_FAMILY','evidence_id':eid,'source':'nominal'}
        self.op={'op':'correct_role','uid':node['uid'],'parent':node['uid'],'relation':'ROLE_ADJUDICATION','classification_axis':'source_grain','source':'nominal','uri':'https://example.invalid/source','proof':proof,'before_profile':profile,'before_normalization_role':norm,'after_profile':after_profile,'after_normalization_role':after_norm}
        for table,row in [('nodes',node),('node_profiles',after_profile),('normalization_roles',after_norm),('evidence',{'evidence_id':eid,'payload':payload(proof),'payload_sha256':hashlib.sha256(payload(proof).encode()).hexdigest(),'source_name':'nominal','source_uri':self.op['uri']})]:
            self.c.execute('CREATE TABLE '+table+'('+','.join(key+(' INTEGER'if isinstance(value,int)else' TEXT')for key,value in row.items())+')')
            self.c.execute('INSERT INTO '+table+' VALUES('+','.join('?'for key in row)+')',list(row.values()))
        self.c.execute('CREATE TABLE usability_changes(stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT)')
        self.c.execute('INSERT INTO usability_changes VALUES(?,?,?,?,?,?)',('nominal_design_scope_repairs','role_source_adjudication',node['uid'],payload({'profile':profile,'normalization_role':norm}),payload({'profile':after_profile,'normalization_role':after_norm}),payload(proof)))

    def test_exact_role_source_full_rows_and_history_pass(self):
        self.assertTrue(audit.verify_nominal_role_transition(self.c,self.inputs,self.op)['exact_source_role_history_preserved'])

    def test_peer_role_copy_without_own_source_record_is_rejected(self):
        self.c.execute('UPDATE nodes SET data=?',(payload({'description':'only one model'}),))
        with self.assertRaises(AssertionError):audit.verify_nominal_role_transition(self.c,self.inputs,self.op)

    def test_current_correct_role_without_unique_transition_history_is_rejected(self):
        self.c.execute('INSERT INTO usability_changes SELECT *FROM usability_changes')
        with self.assertRaises(AssertionError):audit.verify_nominal_role_transition(self.c,self.inputs,self.op)

    def test_rehashed_source_review_cannot_authorize_another_role(self):
        row=json.loads((self.inputs/'source-review.json').read_text());row['approved_source_role_corrections'][0]['source_role_scope_kind']='CLASS'
        (self.inputs/'source-review.json').write_text(payload(row));op=copy.deepcopy(self.op);op['proof']['source_review_locator']['sha256']=audit.digest(self.inputs/'source-review.json');op['proof']['source_scope_review_record']=row
        with self.assertRaises(AssertionError):audit.verify_nominal_role_transition(self.c,self.inputs,op)

    def test_role_correction_cannot_broaden_view_restrictions(self):
        self.c.execute('UPDATE node_profiles SET attributes=?',(payload({'allowed_views':['taxonomy']}),))
        with self.assertRaises(AssertionError):audit.verify_nominal_role_transition(self.c,self.inputs,self.op)

    def test_source_review_has_no_host_absolute_fallback(self):
        op=copy.deepcopy(self.op);op['proof']['source_review_locator']['file']=str(self.inputs/'source-review.json')
        with self.assertRaises(AssertionError):audit.verify_nominal_role_transition(self.c,self.inputs,op)

    def test_source_column_description_requires_its_own_complete_byte_hash(self):
        self.c.execute('ALTER TABLE nodes ADD COLUMN description TEXT')
        text='actual retained column statement';self.c.execute('UPDATE nodes SET description=?',(text,))
        op=copy.deepcopy(self.op);witness=op['proof']['source_witnesses'][0]
        witness.update(field_storage='node_column',field_path='description',field_sha256=hashlib.sha256(text.encode()).hexdigest(),statement=text)
        audit.verify_nominal_source_approval(self.c,self.inputs,op,'approved_source_role_corrections')
        witness['field_sha256']='another-byte-hash'
        with self.assertRaises(AssertionError):audit.verify_nominal_source_approval(self.c,self.inputs,op,'approved_source_role_corrections')

    def test_source_column_is_not_an_arbitrary_raw_node_field(self):
        op=copy.deepcopy(self.op);op['proof']['source_witnesses'][0].update(field_storage='node_column',field_path='uid',statement='own-family',field_sha256=hashlib.sha256(b'own-family').hexdigest())
        with self.assertRaises(AssertionError):audit.verify_nominal_source_approval(self.c,self.inputs,op,'approved_source_role_corrections')

    def abstract_axis(self):
        parent={'uid':'source-configuration','data':payload({'gloss':'an arrangement of parts or elements'})}
        op={'uid':'source-wheel-arrangement','parent':parent['uid'],'relation':'IS_A','classification_axis':'class_intension','proof':{'classification_axis':'class_intension','parent_before_node':parent}}
        review={'schema':'SOURCE_NINE_PROFESSIONAL_CORRECT_COMMON_PARENT_SOURCE_APPROVAL_V1','cases':[{'child_uid':op['uid'],'parent_uid':op['parent'],'relation':'IS_A','limits':'Abstract root; no physical vehicle identity','parent':{'node':parent}}]}
        return op,review

    def test_source_approved_abstract_intension_has_its_own_contract(self):
        op,review=self.abstract_axis()
        self.assertIsNotNone(audit.verify_nominal_classification_axis(op,review))

    def test_abstract_axis_cannot_be_used_by_another_source_cohort(self):
        op,review=self.abstract_axis();review['schema']='SOURCE_NINE_ANY_OTHER_COHORT'
        with self.assertRaises(AssertionError):audit.verify_nominal_classification_axis(op,review)

    def test_abstract_axis_cannot_promote_a_physical_parent(self):
        op,review=self.abstract_axis();op['proof']['parent_before_node']['data']=payload({'gloss':'a vehicle conveying persons or goods'})
        with self.assertRaises(AssertionError):audit.verify_nominal_classification_axis(op,review)

    def test_abstract_axis_cannot_be_a_design_type_relation(self):
        op,review=self.abstract_axis();op['relation']='DESIGN_TYPE_OF'
        with self.assertRaises(AssertionError):audit.verify_nominal_classification_axis(op,review)

    def test_approved_generic_class_intension_is_separate_from_abstract_cohort(self):
        op,review=self.abstract_axis();review['cases'][0]['limits']='Directional class inclusion only; no SAME_CONCEPT inference'
        self.assertIsNone(audit.verify_nominal_classification_axis(op,review))

    def test_owned_physical_design_and_instance_axes_are_distinct(self):
        for relation in('DESIGN_TYPE_OF','INSTANCE_OF'):
            op={'relation':relation,'classification_axis':'physical_intension','proof':{'classification_axis':'physical_intension'}}
            self.assertIsNone(audit.verify_nominal_classification_axis(op,{}))
            op['classification_axis']=op['proof']['classification_axis']='class_intension'
            with self.assertRaises(AssertionError):audit.verify_nominal_classification_axis(op,{})

    def pending_whole_case(self):
        op=copy.deepcopy(self.op);proof=op['proof'];node=proof['before_node']
        reason='Whole object simultaneously denotes a physical artefact and an abstract configuration; source sense remains unresolved.'
        case={'uid':op['uid'],'before_node':node,'before_profiles':[op['before_profile']],'before_normalization_roles':[op['before_normalization_role']],'after_role':'UNKNOWN','after_role_status':'REVIEW','allowed_views':[],'quarantine_role_grain':True,'scope_reason':reason,'pending_whole_scope':'Future independent source-sense adjudication is required.'}
        review={'accepted_source_scope_only':True,'approved_source_roles':[[op['uid'],'UNKNOWN']],'cases':[case]}
        path=self.inputs/'whole-case-review.json';path.write_text(payload(review))
        proof.update(source_role_scope_kind='SOURCE_WHOLE_OBJECT_GRAIN_PENDING',role_status='REVIEW',allowed_views=[],quarantine_role_grain=True,scope_observation=reason,source_review_locator={'file':path.name,'sha256':audit.digest(path)},source_scope_review_record=review)
        eid='usability:'+hashlib.sha256(payload(proof).encode()).hexdigest()
        attrs=json.loads(op['before_profile']['attributes']);attrs.update(role_evidence_id=eid,role_status='REVIEW',allowed_views=[])
        op['after_profile']={**op['before_profile'],'node_kind':'UNKNOWN','attributes':payload(attrs),'evidence_id':eid,'source_uri':op['uri']}
        op['after_normalization_role']={**op['before_normalization_role'],'canonical_role':'UNKNOWN','status':'REVIEW','evidence_id':eid,'source':op['source']}
        self.c.execute('DELETE FROM node_profiles');self.c.execute('DELETE FROM normalization_roles');self.c.execute('DELETE FROM evidence');self.c.execute('DELETE FROM usability_changes')
        for table,row in(('node_profiles',op['after_profile']),('normalization_roles',op['after_normalization_role']),('evidence',{'evidence_id':eid,'payload':payload(proof),'payload_sha256':hashlib.sha256(payload(proof).encode()).hexdigest(),'source_name':op['source'],'source_uri':op['uri']})):
            self.c.execute('INSERT INTO '+table+' VALUES('+','.join('?'for k in row)+')',list(row.values()))
        self.c.execute('INSERT INTO usability_changes VALUES(?,?,?,?,?,?)',('nominal_design_scope_repairs','role_source_adjudication',op['uid'],payload({'profile':op['before_profile'],'normalization_role':op['before_normalization_role']}),payload({'profile':op['after_profile'],'normalization_role':op['after_normalization_role']}),payload(proof)))
        return op

    def test_whole_object_pending_exact_case_list_is_supported(self):
        op=self.pending_whole_case();self.assertEqual(audit.verify_nominal_role_transition(self.c,self.inputs,op)['after_role'],'UNKNOWN')

    def test_whole_object_pending_cannot_change_scope_reason(self):
        op=self.pending_whole_case();op['proof']['scope_observation']='Different scope reason'
        with self.assertRaises(AssertionError):audit.verify_nominal_role_transition(self.c,self.inputs,op)

    def test_whole_object_case_list_cannot_copy_a_different_profile(self):
        op=self.pending_whole_case();op['proof']['source_scope_review_record']['cases'][0]['before_profiles'][0]['node_kind']='CLASS'
        with self.assertRaises(AssertionError):audit.verify_nominal_role_transition(self.c,self.inputs,op)

    def test_whole_object_case_list_cannot_duplicate_a_source_decision(self):
        op=self.pending_whole_case();review=op['proof']['source_scope_review_record'];review['cases'].append(copy.deepcopy(review['cases'][0]));path=self.inputs/op['proof']['source_review_locator']['file'];path.write_text(payload(review));op['proof']['source_review_locator']['sha256']=audit.digest(path)
        with self.assertRaises(AssertionError):audit.verify_nominal_role_transition(self.c,self.inputs,op)

    def withdrawal(self):
        before={'id':7,'child_uid':'own-family','parent_uid':'narrow-parent','relation':'IS_A','status':'ACTIVE','source':'old-source','reason':'original reason','data':payload({'admission_basis':{'source_statement':'whole scope includes helicopters'}})}
        review={'accepted_source_scope_only':True,'approved_source_reviews':[['own-family','narrow-parent','IS_A']]}
        path=self.inputs/'withdrawal-review.json';path.write_text(payload(review))
        content={key:value for key,value in before.items()if key not in {'id','status','reason'}}
        content_sha=hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest()
        proof={**self.op['proof'],'source_review_locator':{'file':path.name,'sha256':audit.digest(path)},'source_scope_review_record':review,
            'withdrawn_scope_witness':{'table':'edges','before_assertion':before,'content_sha256':content_sha,'data_sha256':hashlib.sha256(before['data'].encode()).hexdigest(),'field_path':['admission_basis','source_statement'],'statement':'whole scope includes helicopters'}}
        op={'op':'review_class_edge','table':'edges','uid':'own-family','parent':'narrow-parent','relation':'IS_A','content_sha256':content_sha,'before_assertion':before,'proof':proof}
        self.c.execute('CREATE TABLE edges('+','.join(key+(' INTEGER'if isinstance(value,int)else' TEXT')for key,value in before.items())+')')
        self.c.execute('INSERT INTO edges VALUES('+','.join('?'for key in before)+')',list({**before,'status':'SOURCE_SCOPE_REVIEW'}.values()))
        self.c.execute('INSERT INTO usability_changes VALUES(?,?,?,?,?,?)',('nominal_design_scope_repairs','class_scope_review','7',payload(before),payload({'status':'SOURCE_SCOPE_REVIEW'}),payload(proof)))
        self.c.execute('CREATE TABLE browse_links(storage TEXT,record_id INTEGER)')
        self.c.execute('CREATE TABLE view_roots(witness_id INTEGER)');self.c.execute('CREATE TABLE view_paths(witness_id INTEGER)')
        return op

    def test_exact_withdrawal_preserves_original_reason_and_source_payload(self):
        self.assertTrue(audit.verify_nominal_class_withdrawal(self.c,self.inputs,self.withdrawal())['raw_source_and_history_preserved'])

    def test_withdrawal_cannot_delete_original_reason_or_leak_into_navigation(self):
        op=self.withdrawal();self.c.execute('INSERT INTO browse_links VALUES("edge",7)')
        with self.assertRaises(AssertionError):audit.verify_nominal_class_withdrawal(self.c,self.inputs,op)
        self.c.execute('DELETE FROM browse_links');self.c.execute('UPDATE edges SET reason=NULL')
        with self.assertRaises(AssertionError):audit.verify_nominal_class_withdrawal(self.c,self.inputs,op)


if __name__=='__main__':unittest.main()
