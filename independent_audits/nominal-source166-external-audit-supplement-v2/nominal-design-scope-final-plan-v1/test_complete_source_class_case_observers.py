import copy
import hashlib
import json
import unittest
import independent_nominal_design_scope_final_interface_audit as audit


def node(uid):
    return dict(uid=uid,label='same label',domain='aircraft',domains='["aircraft"]',source='source',rank='class',description='complete class',data='{"definition":"complete source class"}',layer='source',visibility='ACTIVE',component_id=1)


class CompleteClassCases(unittest.TestCase):
    def setUp(self):
        own=node('own');parent=node('parent')
        def record(n):return {'node':n,'data_sha256':hashlib.sha256(n['data'].encode()).hexdigest()}
        self.case={'uid':'own','parent':'parent','relation':'IS_A','own_complete_record':record(own),'parent_complete_record':record(parent),'whole_scope_reason':'Whole complete source entails this common class.'}
        self.review={'schema':'FINEATLAS_WORDNET_JET_PLANE_TO_BROADER_SOURCE_JET_AIRCRAFT_SOURCE_REVIEW_V1','accepted_source_scope_only':True,'approved_source_directions':[['own','parent','IS_A']],'cases':[self.case]}
        self.op={'uid':'own','parent':'parent','relation':'IS_A','classification_axis':'class_intension','proof':{'classification_axis':'class_intension','before_node':own,'parent_before_node':parent,'native_record_sha256':record(own)['data_sha256'],'parent_native_record_sha256':record(parent)['data_sha256']}}
    def verify(self):return audit.verify_nominal_classification_axis(self.op,self.review)
    def test_four_exact_direct_schema_variants(self):
        for schema in ['FINEATLAS_DESIGNED_OR_USED_MILITARY_CLASS_TO_PURPOSE_DESIGNED_OR_SCOPE_REVIEW_V1','FINEATLAS_FALCON900_SR20_AND_LANDPLANE_COMPLETE_SOURCE_DIRECTIONS_REVIEW_V1','FINEATLAS_WORDNET_JET_PLANE_TO_BROADER_SOURCE_JET_AIRCRAFT_SOURCE_REVIEW_V1','FINEATLAS_SLR_GENERIC_ROOT_AND_747300_NOMINAL_VERSION_SOURCE_REVIEW_V1']:
            self.review['schema']=schema;self.assertIsNone(self.verify())
    def test_exact_military_fallback_preserves_distinct_reviewed_parent(self):
        self.review['schema']='FINEATLAS_DESIGNED_OR_USED_MILITARY_CLASS_TO_PURPOSE_DESIGNED_OR_SCOPE_REVIEW_V1'
        self.case['legitimate_fallback']={k:self.case[k]for k in ['uid','parent','relation','parent_complete_record','whole_scope_reason']};self.case['parent']='reviewed-purpose'
        self.assertIsNone(self.verify())
    def test_unknown_schema_rejected(self):
        self.review['schema']='FINEATLAS_INVENTED_APPROVAL';self.assertRaises(AssertionError,self.verify)
    def test_direction_not_approved_rejected(self):
        self.review['approved_source_directions']=[];self.assertRaises(AssertionError,self.verify)
    def test_same_label_wrong_uid_rejected(self):
        self.case['own_complete_record']['node']['uid']='different';self.assertRaises(AssertionError,self.verify)
    def test_ambiguous_cases_rejected(self):
        self.review['cases'].append(copy.deepcopy(self.case));self.assertRaises(AssertionError,self.verify)
    def test_incomplete_node_even_rehashed_both_copies_rejected(self):
        del self.case['own_complete_record']['node']['description'];self.assertRaises(AssertionError,self.verify)
    def test_empty_parent_record_rejected(self):
        self.case['parent_complete_record']={};self.assertRaises((AssertionError,KeyError),self.verify)
    def test_raw_source_hash_changed_rejected(self):
        self.case['parent_complete_record']['data_sha256']='0'*64;self.assertRaises(AssertionError,self.verify)
    def test_empty_whole_scope_reason_rejected(self):
        self.case['whole_scope_reason']='  ';self.assertRaises(AssertionError,self.verify)
    def test_military_fallback_without_full_own_record_rejected(self):
        self.review['schema']='FINEATLAS_DESIGNED_OR_USED_MILITARY_CLASS_TO_PURPOSE_DESIGNED_OR_SCOPE_REVIEW_V1';self.case['legitimate_fallback']=copy.deepcopy(self.case);self.case['parent']='old';del self.case['own_complete_record'];self.assertRaises(KeyError,self.verify)
    def test_fallback_from_other_schema_rejected(self):
        self.case['legitimate_fallback']=copy.deepcopy(self.case);self.case['parent']='old';self.assertRaises(AssertionError,self.verify)


    def fallback_without_duplicate_sha(self):
        self.review['schema']='FINEATLAS_DESIGNED_OR_USED_MILITARY_CLASS_TO_PURPOSE_DESIGNED_OR_SCOPE_REVIEW_V1'
        self.case['legitimate_fallback']={k:copy.deepcopy(self.case[k])for k in ['uid','parent','relation','parent_complete_record','whole_scope_reason']}
        del self.case['legitimate_fallback']['parent_complete_record']['data_sha256']
        self.case['parent']='reviewed-purpose'
    def test_exact_full_military_fallback_without_duplicate_hash_field(self):
        self.fallback_without_duplicate_sha();self.assertIsNone(self.verify())
    def test_fallback_computed_hash_must_match_frozen_proof(self):
        self.fallback_without_duplicate_sha();self.op['proof']['parent_native_record_sha256']='0'*64;self.assertRaises(AssertionError,self.verify)
    def test_fallback_explicit_wrong_hash_cannot_use_missing_field_branch(self):
        self.fallback_without_duplicate_sha();self.case['legitimate_fallback']['parent_complete_record']['data_sha256']='0'*64;self.assertRaises(AssertionError,self.verify)
    def test_military_fallback_same_label_wrong_parent_uid_is_rejected(self):
        self.fallback_without_duplicate_sha();self.case['legitimate_fallback']['parent_complete_record']['node']['uid']='different';self.assertRaises(AssertionError,self.verify)


if __name__=='__main__':unittest.main()
