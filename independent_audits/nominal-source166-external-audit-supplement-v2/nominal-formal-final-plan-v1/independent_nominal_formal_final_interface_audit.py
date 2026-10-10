#!/usr/bin/env python3
"""External read-only completed-snapshot audit; imports no build classifiers.

Direct entrance/big-branch pages and source witnesses are reconstructed from
raw nodes/profiles/claims. Legacy pair endpoint admission is public SDK output;
its geometry is independently recomputed from raw source assertions. This is
structural verification, not certification of unresolved source identities.
"""
from __future__ import annotations

if not __debug__:
    raise RuntimeError('Optimized Python is forbidden for mandatory independent audit gates')

import argparse
from collections import Counter, deque
import hashlib
import gzip
import itertools
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

DATASETS = {'cub200': 200, 'fgvc_aircraft': 100, 'flowers102': 102, 'pets37': 37, 'stanford_dogs': 120, 'stanford_cars': 196}
TERMINALS = {'INSTANCE': {'INSTANCE_OF'}, 'ATTRIBUTE': {'ATTRIBUTE_KIND_OF'}, 'DATASET_CATEGORY': {'DEPICTS_TYPE'},
             'CONFIGURATION': {'CONFIGURATION_OF', 'CONFIGURATION_TYPE_OF', 'REGULATED_AS'},
             'MODEL': {'DESIGN_TYPE_OF', 'REGULATED_AS', 'SERIES_MEMBER_OF', 'NATIVE_DESIGN_PARENT'}, 'MODEL_FAMILY': {'DESIGN_TYPE_OF', 'NATIVE_DESIGN_PARENT'}}
ROLES = {'classification': {'CLASS', 'BIOLOGICAL_VARIANT'}, 'design': {'CLASS', 'MODEL', 'MODEL_FAMILY'}, 'configuration': {'CLASS', 'MODEL', 'MODEL_FAMILY', 'CONFIGURATION'}}
RELATIONS = {'classification': {'IS_A', 'TAXONOMIC_PARENT', 'NATIVE_CLASSIFICATION_PARENT'},
             'design': {'IS_A', 'TAXONOMIC_PARENT', 'NATIVE_CLASSIFICATION_PARENT', 'DESIGN_TYPE_OF', 'NATIVE_DESIGN_PARENT', 'SERIES_MEMBER_OF'},
             'configuration': {'IS_A', 'TAXONOMIC_PARENT', 'NATIVE_CLASSIFICATION_PARENT', 'DESIGN_TYPE_OF', 'NATIVE_DESIGN_PARENT', 'SERIES_MEMBER_OF', 'CONFIGURATION_OF'}}
COARSE = {'domain_root', 'domain_entry', 'portal'}
NON_NAVIGATION_REFERENCES = {'SOURCE_DESIGN_DERIVATION_REFERENCE'}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as s:
        while raw := s.read(4 * 1024 * 1024): h.update(raw)
    return h.hexdigest()


def write(path, value):
    temporary = Path(str(path) + '.tmp'); temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n'); temporary.replace(path)


def file_inventory(root, suffixes=None):
    result = {}
    for path in sorted(Path(root).rglob('*')):
        if path.is_file() and (suffixes is None or path.suffix in suffixes):
            assert not path.is_symlink(), 'Frozen inventory contains a symbolic link'
            result[str(path.relative_to(root))] = digest(path)
    return result


def verified_owned_reviews(connection, inputs):
    """Exact frozen later reviews from each actual source stage; never wildcard."""
    result = {}
    for name,stage_name in [('structure_owned_scope_repairs.json','owned_scope_repairs'),
                            ('structure_complete_owned_type_repairs.json','complete_owned_type_repairs'),
                            ('structure_nominal_design_scope_repairs.json','nominal_design_scope_repairs')]:
        path=Path(inputs)/name
        if not path.exists():continue
        manifest=json.loads(path.read_text());operation_path=Path(inputs)/manifest['operations_file']
        assert digest(operation_path)==manifest['operations_sha256']
        operations=[json.loads(line)for line in operation_path.read_text().splitlines()if line]
        assert len(operations)==manifest['operation_count']
        for op in operations:
            table={'review_bridge':'bridges','review_typed_relation':'entity_relations','review_class_edge':'edges'}.get(op.get('op'))
            if table is None:continue
            before=op['before_assertion'];content={k:v for k,v in before.items()if k not in {'id','status','reason'}}
            assert hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest()==op['content_sha256']
            actual=connection.execute('SELECT *FROM '+table+' WHERE id=?',(before['id'],)).fetchone()
            after={**before,'status':op['after_status']}
            assert before['status']=='ACTIVE'and op['after_status']=='SOURCE_SCOPE_REVIEW'and actual and dict(actual)==after
            kind={'bridges':'bridge_scope_review','entity_relations':'typed_scope_review','edges':'class_scope_review'}[table]
            histories=connection.execute('SELECT *FROM usability_changes WHERE object_id=?AND object_type=?AND stage=?',
                (str(before['id']),kind,stage_name)).fetchall()
            assert sum(json.loads(h['before_json'])==before and json.loads(h['after_json'])=={'status':'SOURCE_SCOPE_REVIEW'}and json.loads(h['evidence'])==op['proof']for h in histories)==1
            key=(table,before['id']);assert key not in result,'Duplicate source-status withdrawal permission'
            result[key]=(before,after)
    return result


def verify_nominal_source_approval(connection, inputs, op, approval_key):
    proof=op['proof'];locator=proof['source_review_locator']
    assert proof['whole_subject_scope_review']is True and proof['world_identity_assertion']is False and proof['no_identity_merges']is True
    assert isinstance(locator['file'],str)and Path(locator['file']).name==locator['file']
    path=Path(inputs)/locator['file'];assert digest(path)==locator['sha256']
    review=json.loads(path.read_text());assert review==proof['source_scope_review_record']and review['accepted_source_scope_only']is True
    if approval_key!='approved_source_role_corrections':
        assert [op['uid'],op['parent'],op['relation']]in review[approval_key]
    for witness in proof['source_witnesses']:
        row=connection.execute('SELECT *FROM nodes WHERE uid=?',(witness['uid'],)).fetchone();assert row
        assert hashlib.sha256(row['data'].encode()).hexdigest()==witness['data_sha256']
        parts=witness['field_path']
        if witness.get('field_storage')=='node_column':
            assert parts=='description','Only the actual retained description column is source-approved'
            value=row['description'];assert hashlib.sha256(value.encode()).hexdigest()==witness['field_sha256']
        else:
            assert witness.get('field_storage','node_data')=='node_data'
            value=json.loads(row['data'])
            for part in (parts.split('.')if isinstance(parts,str)else parts):value=value[part]
        assert value==witness['statement']and isinstance(value,str)and value
    return review


def verify_added_complete_class_case(op, review):
    """Read only the four independently approved complete-record case schemas."""
    schemas = {
        'FINEATLAS_DESIGNED_OR_USED_MILITARY_CLASS_TO_PURPOSE_DESIGNED_OR_SCOPE_REVIEW_V1',
        'FINEATLAS_FALCON900_SR20_AND_LANDPLANE_COMPLETE_SOURCE_DIRECTIONS_REVIEW_V1',
        'FINEATLAS_WORDNET_JET_PLANE_TO_BROADER_SOURCE_JET_AIRCRAFT_SOURCE_REVIEW_V1',
        'FINEATLAS_SLR_GENERIC_ROOT_AND_747300_NOMINAL_VERSION_SOURCE_REVIEW_V1',
    }
    assert review['schema'] in schemas
    triple = (op['uid'], op['parent'], op['relation'])
    assert list(triple) in review['approved_source_directions']
    assert review['accepted_source_scope_only'] is True
    matches = []
    for case in review['cases']:
        if (case.get('uid'), case.get('parent'), case.get('relation')) == triple:
            matches.append((case, case))
        fallback = case.get('legitimate_fallback', {})
        if (fallback.get('uid'), fallback.get('parent'), fallback.get('relation')) == triple:
            assert review['schema'] == 'FINEATLAS_DESIGNED_OR_USED_MILITARY_CLASS_TO_PURPOSE_DESIGNED_OR_SCOPE_REVIEW_V1'
            assert case.get('uid') == op['uid'] and case.get('relation') == op['relation']
            matches.append((case, fallback))
    assert len(matches) == 1, 'A complete class direction requires one exact case'
    case, direction = matches[0]
    own_record = case['own_complete_record']
    parent_record = direction['parent_complete_record']
    for record, node_key, hash_key, uid in (
        (own_record, 'before_node', 'native_record_sha256', op['uid']),
        (parent_record, 'parent_before_node', 'parent_native_record_sha256', op['parent']),
    ):
        assert isinstance(record, dict) and isinstance(record.get('node'), dict)
        node = record['node']
        assert set(node) == {'uid','label','domain','domains','source','rank','description','data','layer','visibility','component_id'}, 'Complete normalized SQL node row is required'
        assert node == op['proof'][node_key] and node['uid'] == uid
        raw_sha = hashlib.sha256(node['data'].encode()).hexdigest()
        assert raw_sha == op['proof'][hash_key]
        recorded_sha = record.get('data_sha256', record.get('node_data_sha256'))
        if recorded_sha is None:
            assert direction is not case and node_key == 'parent_before_node'
            assert review['schema'] == 'FINEATLAS_DESIGNED_OR_USED_MILITARY_CLASS_TO_PURPOSE_DESIGNED_OR_SCOPE_REVIEW_V1'
            # This exact source document stores the complete fallback SQL node,
            # not a second SHA field. The mandatory frozen op raw SHA above
            # still binds every byte of that original node.data.
        else:
            assert recorded_sha == raw_sha
    reason = direction['whole_scope_reason']
    assert isinstance(reason, str) and reason.strip(), 'Complete source scope reason is mandatory'
    return case


def verify_nominal_classification_axis(op, review):
    """Admit exact approved class intensions and identify abstract configurations."""
    axis=op['classification_axis'];proof=op['proof']
    assert axis==proof['classification_axis']
    if axis=='class_intension':
        assert op['relation']=='IS_A'
        if review['schema'].startswith('FINEATLAS_'):
            verify_added_complete_class_case(op, review)
            return None
        assert review['schema']in {'SOURCE_NINE_PROFESSIONAL_CORRECT_COMMON_PARENT_SOURCE_APPROVAL_V1','SOURCE_NINE_SIX_OLD_LCA_SHARED_PATTERN_WHOLE_SOURCE_DIRECTION_REVIEW_V1','SOURCE_NINE_SIX_OLD_LCA_SHARED_PATTERN_WHOLE_SOURCE_DIRECTION_REVIEW_V2','SOURCE_NINE_ADDITIONAL_OLD_LCA_LITERAL_DESIGN_PURPOSE_AND_COMMON_PARENT_REVIEW_V2'}
        cases=[case for case in review['cases']if (case.get('child_uid'),case.get('parent_uid'),case.get('relation'))==(op['uid'],op['parent'],op['relation'])]
        assert len(cases)==1
        if 'abstract' not in cases[0].get('limits','').lower():return None
        parent=cases[0]['parent']['node']
        assert parent==proof['parent_before_node']
        assert 'arrangement of parts or elements' in json.loads(parent['data'])['gloss']
        return cases[0]
    assert axis in {'IS_A':{'physical_intension'},'DESIGN_TYPE_OF':{'purpose','function','physical_intension'},'INSTANCE_OF':{'physical_intension'},'NATIVE_DESIGN_PARENT':{'design_family'}}[op['relation']]
    return None


def verify_nominal_role_transition(connection, inputs, op):
    assert op['op']=='correct_role'and op['uid']==op['parent']and op['relation']=='ROLE_ADJUDICATION'and op['classification_axis']=='source_grain'
    proof=op['proof'];review=verify_nominal_source_approval(connection,inputs,op,'approved_source_role_corrections')
    before={'profile':op['before_profile'],'normalization_role':op['before_normalization_role']}
    after={'profile':op['after_profile'],'normalization_role':op['after_normalization_role']}
    target=after['profile']['node_kind']
    node=dict(connection.execute('SELECT *FROM nodes WHERE uid=?',(op['uid'],)).fetchone())
    fallback={'model':'MODEL','product_model':'MODEL','aircraft_model':'MODEL','vehicle_model':'MODEL','series':'MODEL_FAMILY','model_family':'MODEL_FAMILY','instance':'INSTANCE','unknown':'UNKNOWN','type_or_product_model':'UNKNOWN'}
    old_role=before['profile']['node_kind']if before['profile']else fallback.get((node['rank']or'').lower(),'CLASS')
    assert old_role!=target and target in {'MODEL','MODEL_FAMILY','INSTANCE','UNKNOWN'}
    approved=[row for row in review.get('approved_source_role_corrections',[])if row['uid']==op['uid']]
    old_approval=len(approved)==1 and approved[0]['before_profile']==before['profile']and approved[0]['before_normalization']==before['normalization_role']and approved[0]['before_role']==old_role and approved[0]['source_role_scope_kind']==target
    source_record=(review.get('source_role_records')or review.get('complete_before_records')or{}).get(op['uid'])
    new_approval=source_record is not None and [op['uid'],target]in review.get('approved_source_roles',[])and source_record.get('node')==node and source_record.get('node_profiles')==before['profile']and source_record.get('normalization_roles')==before['normalization_role']
    cases=[case for case in review.get('cases',[])if case.get('uid')==op['uid']]
    assert len(cases)<=1,'A source grain adjudication needs one unambiguous exact case'
    case=cases[0]if cases else{}
    case_approval=[op['uid'],target]in review.get('approved_source_roles',[])and case.get('before_node')==node and case.get('before_profiles')==([before['profile']]if before['profile']else[])and case.get('before_normalization_roles')==([before['normalization_role']]if before['normalization_role']else[])
    assert old_approval or new_approval or case_approval
    assert node==proof['before_node']and hashlib.sha256(node['data'].encode()).hexdigest()==proof['native_record_sha256']
    for table,key in [('node_profiles','profile'),('normalization_roles','normalization_role')]:
        assert dict(connection.execute('SELECT *FROM '+table+' WHERE uid=?',(op['uid'],)).fetchone())==after[key]
    old_attrs=json.loads(before['profile']['attributes'])if before['profile']else{};new_attrs=json.loads(after['profile']['attributes'])
    status='REVIEW'if target=='UNKNOWN'else'VERIFIED'
    source_role=before['normalization_role']['source_role']if before['normalization_role']else old_attrs.get('source_role',node['rank']or'UNSPECIFIED')
    native_rank=old_attrs.get('native_rank',node['rank'])
    source_grains={'WHOLE_NOMINAL_MULTIMODEL_PROGRAMME':'MODEL_FAMILY','OWNED_NAMED_REUSABLE_DESIGN_PROGRAMME':'MODEL','OWNED_NAMED_OPERATIONAL_PHYSICAL_INSTANCE':'INSTANCE','SOURCE_NOMINAL_OR_INDIVIDUAL_GRAIN_PENDING':'UNKNOWN','SOURCE_WHOLE_OBJECT_GRAIN_PENDING':'UNKNOWN'}
    assert source_grains.get(proof['source_role_scope_kind'])==target and proof['role_status']==status and proof['source_role']==source_role and proof['native_rank']==native_rank
    if target=='UNKNOWN':
        decision=review.get('source_role_decisions',{}).get(op['uid'])or case
        assert decision.get('quarantine_role_grain')is True and decision.get('after_role_status')=='REVIEW'and decision.get('allowed_views')==[] and proof.get('allowed_views')==[] and proof.get('quarantine_role_grain')is True
        if proof['source_role_scope_kind']=='SOURCE_WHOLE_OBJECT_GRAIN_PENDING':
            assert isinstance(decision.get('pending_whole_scope'),str)and decision['pending_whole_scope']and isinstance(decision.get('scope_reason'),str)and decision['scope_reason']
            assert proof['scope_observation']==decision['scope_reason'],'Whole-object ambiguity needs its original exact scope decision'
    elif proof.get('allowed_views')is not None:assert proof['allowed_views']==old_attrs.get('allowed_views')
    histories=connection.execute('SELECT before_json,after_json,evidence FROM usability_changes WHERE stage="nominal_design_scope_repairs"AND object_type="role_source_adjudication"AND object_id=?',(op['uid'],)).fetchall()
    assert sum(json.loads(row['before_json'])==before and json.loads(row['after_json'])==after and json.loads(row['evidence'])==proof for row in histories)==1
    eid='usability:'+hashlib.sha256(json.dumps(proof,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    expected_attrs={key:value for key,value in old_attrs.items()if key not in {'canonical_scope_guard','canonical_scope_evidence_id'}}
    expected_attrs.update(source_role=source_role,native_rank=native_rank,role_status=status,role_evidence_id=eid)
    if target=='UNKNOWN':expected_attrs['allowed_views']=[]
    assert new_attrs==expected_attrs
    expected_profile={**(before['profile']or{'uid':op['uid'],'domain':node.get('domain')or''}),'node_kind':target,'source_uri':op['uri'],'evidence_id':eid,'attributes':json.dumps(expected_attrs,ensure_ascii=False,sort_keys=True,separators=(',',':'))}
    expected_norm={**(before['normalization_role']or{'uid':op['uid'],'source_role':source_role,'status':status,'prior_profile':json.dumps(before['profile']or{},ensure_ascii=False,sort_keys=True,separators=(',',':'))}),'canonical_role':target,'evidence_id':eid,'source':op['source']}
    if target=='UNKNOWN':expected_norm['status']='REVIEW'
    elif before['normalization_role']:assert before['normalization_role']['status']=='VERIFIED'
    assert after['profile']==expected_profile and after['normalization_role']==expected_norm
    evidence=connection.execute('SELECT *FROM evidence WHERE evidence_id=?',(eid,)).fetchone()
    assert evidence and json.loads(evidence['payload'])==proof and hashlib.sha256(evidence['payload'].encode()).hexdigest()==evidence['payload_sha256']
    assert evidence['source_name']==op['source']and evidence['source_uri']==op['uri']and after['profile']['evidence_id']==eid and after['normalization_role']['evidence_id']==eid
    return {'uid':op['uid'],'before_role':old_role,'after_role':target,'after_role_status':status,'exact_source_role_history_preserved':True}


def verify_nominal_class_withdrawal(connection, inputs, op):
    assert op['op']=='review_class_edge'and op['table']=='edges'and op['relation']=='IS_A'
    verify_nominal_source_approval(connection,inputs,op,'approved_source_reviews')
    before=op['before_assertion'];assert before['child_uid']==op['uid']and before['parent_uid']==op['parent']and before['status']=='ACTIVE'
    after={**before,'status':'SOURCE_SCOPE_REVIEW'}
    assert dict(connection.execute('SELECT *FROM edges WHERE id=?',(before['id'],)).fetchone())==after
    content={key:value for key,value in before.items()if key not in {'id','status','reason'}}
    assert hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest()==op['content_sha256']
    retained=op['proof']['withdrawn_scope_witness'];assert retained['before_assertion']==before and retained['table']=='edges'
    assert retained['content_sha256']==op['content_sha256']and retained['data_sha256']==hashlib.sha256(before['data'].encode()).hexdigest()
    value=json.loads(before['data'])
    for part in retained['field_path']:value=value[part]
    assert value==retained['statement']and value
    histories=connection.execute('SELECT before_json,after_json,evidence FROM usability_changes WHERE stage="nominal_design_scope_repairs"AND object_type="class_scope_review"AND object_id=?',(str(before['id']),)).fetchall()
    assert sum(json.loads(row['before_json'])==before and json.loads(row['after_json'])=={'status':'SOURCE_SCOPE_REVIEW'}and json.loads(row['evidence'])==op['proof']for row in histories)==1
    assert_no_assertion_index_leak(connection,'edges',before['id'])
    return {'uid':op['uid'],'parent':op['parent'],'withdrawn_edge_id':before['id'],'after_status':'SOURCE_SCOPE_REVIEW','raw_source_and_history_preserved':True}


def assert_no_assertion_index_leak(connection, table, identifier):
    if table == 'bridges': return
    storage = 'entity' if table == 'entity_relations' else 'edge'
    assert not connection.execute('SELECT 1 FROM browse_links WHERE storage=? AND record_id=?',(storage,identifier)).fetchone()
    witness_identifier=-identifier if table=='entity_relations'else identifier
    for cache in ('view_roots','view_paths'):
        assert not connection.execute('SELECT 1 FROM '+cache+' WHERE witness_id=?',(witness_identifier,)).fetchone(),'Reviewed/reference assertion leaked into an actual root-path witness'
    # Edge and entity IDs occupy separate namespaces. Edge ID equality does not
    # identify an entity terminal witness and must not withdraw a lawful link.
    if table == 'entity_relations':
        assert not connection.execute('SELECT 1 FROM view_terminal_connections WHERE witness_relation_id=?',(identifier,)).fetchone()
        assert not connection.execute('SELECT 1 FROM entity_connections WHERE witness_relation_id=?',(identifier,)).fetchone()


def verify_source_declared_reference(connection, row, proof):
    assert row['status'] == 'SOURCE_DECLARED'
    data=json.loads(row['data'])
    assert data.get('allowed_views') == [] and data.get('navigation_eligible') is False and data.get('admission_basis') == proof
    evidence=connection.execute('SELECT payload,payload_sha256 FROM evidence WHERE evidence_id=?',(row['evidence_id'],)).fetchone()
    assert evidence and json.loads(evidence[0]) == proof and hashlib.sha256(evidence[0].encode()).hexdigest() == evidence[1]
    assert_no_assertion_index_leak(connection,'entity_relations',row['id'])


def verify_retained_design_reference(connection, op):
    before=op['before_assertion'];proof=op['proof']
    assert before['status']=='SOURCE_SCOPE_REVIEW'and before['relation']=='NATIVE_DESIGN_PARENT'
    assert proof['original_reference_relation']==before and proof.get('source_native_objects_preserved')is True
    assert proof.get('no_identity_merges')is True and proof.get('world_identity_assertion')is False
    assert dict(connection.execute('SELECT * FROM entity_relations WHERE id=?',(before['id'],)).fetchone())==before
    content={k:v for k,v in before.items()if k not in{'id','status','reason'}}
    assert hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest()==op['content_sha256']
    bridge=proof['original_source_identifier_bridge']
    assert dict(connection.execute('SELECT * FROM bridges WHERE id=?',(bridge['id'],)).fetchone())==bridge
    assert bridge['status']=='ACTIVE'and {bridge['left_uid'],bridge['right_uid']}=={op['uid'],before['subject_uid']}
    rows=connection.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',
        (op['uid'],op['parent'],op['relation'],op['source'])).fetchall();assert len(rows)==1
    row=rows[0];verify_source_declared_reference(connection,row,proof)
    assert json.loads(row['data']).get('classification_axis')=='design_derivation_reference'
    assert_no_assertion_index_leak(connection,'entity_relations',before['id'])
    after={'subject_uid':op['uid'],'object_uid':op['parent'],'relation':op['relation'],'status':'SOURCE_DECLARED','source':op['source']}
    histories=connection.execute('SELECT before_json,after_json,evidence FROM usability_changes WHERE stage="owned_scope_repairs" AND object_type="owned_non_navigation_design_reference" AND object_id=?',(op['uid'],)).fetchall()
    assert sum(json.loads(h['before_json'])==before and json.loads(h['after_json'])==after and json.loads(h['evidence'])==proof for h in histories)==1
    return row


def verify_unknown_catalog_isolation(connection, uid):
    node=connection.execute('SELECT component_id,visibility FROM nodes WHERE uid=?',(uid,)).fetchone()
    assert node and node['visibility']=='ACTIVE'
    catalog=connection.execute('SELECT * FROM browse_nodes WHERE uid=?',(uid,)).fetchone()
    assert catalog and catalog['role']=='UNKNOWN' and catalog['view_mask']==0 and catalog['component_id']==node['component_id']
    assert not connection.execute('SELECT 1 FROM browse_links WHERE child_component=? OR parent_component=?',(node['component_id'],node['component_id'])).fetchone()
    assert not connection.execute('SELECT 1 FROM domain_members WHERE uid=?',(uid,)).fetchone()
    assert not connection.execute('SELECT 1 FROM domain_components WHERE component_id=?',(node['component_id'],)).fetchone()
    assert not connection.execute('SELECT 1 FROM view_terminal_connections WHERE uid=?',(uid,)).fetchone()
    assert not connection.execute('SELECT 1 FROM entity_connections WHERE uid=?',(uid,)).fetchone()
    return dict(catalog)


def verify_scientific_host_edge(row, proof):
    assert row['relation']=='TAXONOMIC_PARENT' and row['status']=='TYPED_ACTIVE'
    data=json.loads(row['data'])
    assert data.get('admission_basis')==proof
    assert data.get('eligible_for_final_typed_graph')is True and data.get('eligible_for_final_dag')is False
    assert proof['host_taxon_scope_review']['child_remains_biological_variant']is True
    assert proof['host_taxon_scope_review']['species_identity_assertion']is False


def check_quarantine_states(item, current_rows, parent_rows, histories, sanctioned_reviews=None):
    original = item['original_source_assertion']
    excluded = {'id','status','reason'}
    wanted = {key:value for key,value in original.items() if key not in excluded}
    def matches(rows):
        return [dict(row) for row in rows if {key:value for key,value in dict(row).items() if key not in excluded} == wanted]
    current, parent = matches(current_rows), matches(parent_rows)
    expected_count = item['locator'].get('source_assertion_multiplicity',1)
    assert len(current) == len(parent) == expected_count, {'changed_original_assertion':item['locator']}
    # Every historical sibling must retain its own audited state and reason.
    parent_by_id = {row['id']:row for row in parent}
    assert set(parent_by_id) == {row['id'] for row in current}
    for row in current:
        prior = parent_by_id[row['id']]
        if row != prior:
            sanctioned = (sanctioned_reviews or {}).get((item['table'],row['id']))
            assert sanctioned == (prior,row) and row['status'] == 'SOURCE_SCOPE_REVIEW' and {k:v for k,v in row.items() if k != 'status'} == {k:v for k,v in prior.items() if k != 'status'}, {'historical_status_or_raw_change':item['locator']}

    canonical = [row for row in current if row['id'] == original['id']]
    assert len(canonical) == 1 and canonical[0]['status'] == 'SOURCE_SCOPE_REVIEW', {'canonical_scope_review_lost':item['locator']}
    witness = []
    for history in histories:
        before = json.loads(history['before_json']); after = json.loads(history['after_json']); proof = json.loads(history['evidence'])
        if (before == original and after.get('status') == 'SOURCE_SCOPE_REVIEW'
                and proof.get('asserted_semantically_false') is False
                and proof.get('source_assertion_locator') == item['locator']): witness.append(history)
    assert witness, {'frozen_quarantine_history_missing':item['locator']}
    return current


def check_portable_quarantine_states(item, current_rows, parent_state, histories, sanctioned_reviews=None):
    original=item['original_source_assertion'];wanted={k:v for k,v in original.items()if k not in{'id','status','reason'}}
    current=[dict(row)for row in current_rows if {k:v for k,v in dict(row).items()if k not in{'id','status','reason'}}==wanted]
    assert parent_state['table']==item['table'] and parent_state['locator']==item['locator']
    assert len(current)==len(parent_state['rows'])==item['locator'].get('source_assertion_multiplicity',1)
    prior={row['id']:row for row in parent_state['rows']};assert set(prior)=={row['id']for row in current}
    for row in current:
        expected=prior[row['id']];actual=hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()
        if actual!=expected['row_sha256']:
            permission=(sanctioned_reviews or {}).get((item['table'],row['id']))
            assert permission and permission[1]==row and row['status']=='SOURCE_SCOPE_REVIEW'
            before=permission[0]
            assert hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()==expected['row_sha256']
            assert before['status']==expected['status'] and before.get('reason')==expected['reason']
            assert {k:v for k,v in row.items()if k!='status'}=={k:v for k,v in before.items()if k!='status'}
        else:assert row['status']==expected['status'] and row.get('reason')==expected['reason']
    canonical=[row for row in current if row['id']==original['id']]
    assert len(canonical)==1 and canonical[0]['status']=='SOURCE_SCOPE_REVIEW'
    assert any(json.loads(h['before_json'])==original and json.loads(h['after_json']).get('status')=='SOURCE_SCOPE_REVIEW'
        and json.loads(h['evidence']).get('asserted_semantically_false')is False
        and json.loads(h['evidence']).get('source_assertion_locator')==item['locator']for h in histories)
    return current


def stamp(path):
    s = Path(path).stat(); return [s.st_size, s.st_mtime_ns, s.st_ino]


def role_sql():
    cases = {'ORGANIZATION': ['manufacturer', 'make'], 'INSTANCE': ['instance'], 'ATTRIBUTE': ['attribute', 'horticultural_color_class'],
             'MODEL': ['model', 'product_model', 'aircraft_model', 'vehicle_model'], 'MODEL_FAMILY': ['model_family', 'series'],
             'CONFIGURATION': ['model_year', 'configuration', 'model_year_configuration'], 'UNKNOWN': ['unknown', 'type_or_product_model'],
             'DATASET_CATEGORY': ['dataset_category'], 'BIOLOGICAL_VARIANT': ['biological_variant']}
    fallback = "CASE WHEN lower(n.source)='wfo' AND lower(n.rank)='series' THEN 'CLASS' ELSE CASE lower(coalesce(n.rank,'')) " + ' '.join("WHEN '" + rank + "' THEN '" + role + "'" for role, ranks in cases.items() for rank in ranks) + " ELSE 'CLASS' END END"
    return 'coalesce(p.node_kind,' + fallback + ')'


class RawSource:
    def __init__(self, con, view='unified', policy=None, scope=None, floors=()):
        self.c, self.view, self.policy, self.scope = con, view, policy, scope
        self.nodes, self.parents = {}, {}; self.floors = {self.node(u)['component_id'] for u in floors}
    def node(self, uid):
        if uid not in self.nodes:
            if len(self.nodes) >= 10000: self.nodes.clear()
            row = self.c.execute('SELECT n.*,' + role_sql() + ' role,p.attributes FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?', (uid,)).fetchone()
            self.nodes[uid] = dict(row) if row else None
        return self.nodes[uid]
    def admitted(self, row):
        if not row or row['visibility'] != 'ACTIVE': return False
        roles = {'CLASS','MODEL','MODEL_FAMILY','CONFIGURATION'} | set(TERMINALS) | ({'BIOLOGICAL_VARIANT'} if self.view in ('taxonomy','unified') else set())
        if row['role'] not in roles: return False
        allowed = json.loads(row['attributes'] or '{}').get('allowed_views')
        return not isinstance(allowed, list) or ('taxonomy' if self.view == 'unified' else self.view) in allowed
    def class_roles(self):
        return {'CLASS', 'BIOLOGICAL_VARIANT'} if self.view == 'unified' else {'CLASS', 'MODEL', 'MODEL_FAMILY', 'CONFIGURATION'} | ({'BIOLOGICAL_VARIANT'} if self.view == 'taxonomy' else {'DATASET_CATEGORY'} if self.view == 'membership' else set())
    def edge_legal(self, row):
        return ((row['status'] == 'ACTIVE' and row['relation'] == 'IS_A') if self.view == 'strict' else
                (row['status'] == 'TYPED_ACTIVE' and row['relation'] == 'REUSABLE_TYPE_MEMBERSHIP') if self.view == 'membership' else
                (row['status'] == 'ACTIVE' and row['relation'] == 'IS_A') or
                (row['status'] == 'TYPED_ACTIVE' and row['relation'] in {'TAXONOMIC_PARENT', 'NATIVE_CLASSIFICATION_PARENT'}) or
                (self.view == 'unified' and row['status'] == 'BACKBONE_ACTIVE' and row['relation'] == 'IS_A'))
    def accepted(self, child, parent, edge, storage):
        if not self.admitted(child) or not self.admitted(parent): return False
        if storage == 'edge':
            legal = self.edge_legal(edge) and child['role'] in self.class_roles() and parent['role'] in self.class_roles()
        else:
            legal = edge['status'] == 'ACTIVE' and edge['relation'] in TERMINALS.get(child['role'], ()) and parent['role'] in (self.class_roles() | {'CLASS', 'MODEL', 'MODEL_FAMILY', 'CONFIGURATION'})
        if self.policy:
            legal &= child['role'] in ROLES[self.policy] and parent['role'] in ROLES[self.policy] and edge['relation'] in RELATIONS[self.policy]
            basis = json.loads(edge['data'] or '{}').get('admission_basis', {})
            if isinstance(basis, dict) and basis.get('placement_uncertain'): return False
            if self.scope and not (child['source'] == self.scope and (parent['source'] == self.scope or parent['component_id'] in self.floors)): return False
        return legal
    def next(self, comp):
        if comp not in self.parents:
            values = set()
            for table, left, right, storage in [('edges', 'child_uid', 'parent_uid', 'edge'), ('entity_relations', 'subject_uid', 'object_uid', 'entity')]:
                for row in self.c.execute('SELECT e.* FROM nodes n JOIN ' + table + ' e ON e.' + left + '=n.uid WHERE n.component_id=?', (comp,)):
                    child, parent = self.node(row[left]), self.node(row[right])
                    if self.accepted(child, parent, row, storage) and comp != parent['component_id']: values.add(parent['component_id'])
            self.parents[comp] = values
        return self.parents[comp]
    def closure(self, uid):
        node = self.node(uid)
        if not self.admitted(node): return {}
        result = {node['component_id']: 0}; todo = deque(result)
        while todo:
            comp = todo.popleft()
            for parent in self.next(comp):
                if parent not in result: result[parent] = result[comp] + 1; todo.append(parent)
            if len(result) > 10000: raise RuntimeError('Independent traversal exceeds declared 10000-component bound')
        return result
    def direct(self, components, coarse=True, domain=None):
        values = set()
        for comp in components:
            for table, left, right, storage in [('edges', 'child_uid', 'parent_uid', 'edge'), ('entity_relations', 'subject_uid', 'object_uid', 'entity')]:
                for row in self.c.execute('SELECT e.* FROM nodes n JOIN ' + table + ' e ON e.' + right + '=n.uid WHERE n.component_id=?', (comp,)):
                    child, parent = self.node(row[left]), self.node(row[right])
                    if not self.accepted(child, parent, row, storage) or child['component_id'] == parent['component_id']: continue
                    if domain and not self.c.execute('SELECT 1 FROM domain_components WHERE domain_id=? AND view=? AND component_id=?', (domain, self.view, child['component_id'])).fetchone(): continue
                    if not coarse and self.c.execute('SELECT 1 FROM browse_preferences WHERE view=? AND parent_component=? AND child_component=? AND role=? AND relation=?', (self.view, comp, child['component_id'], child['role'], row['relation'])).fetchone(): continue
                    values.add(child['component_id'])
        return values


def collect_pages(call, key, expected, revision, limit=127):
    cursor = None; cursors = set(); values = set(); pages = 0
    while True:
        result = call(limit=limit, cursor=cursor); pages += 1
        assert result['database_revision'] == revision, result
        assert result.get('status') not in {'STALE_INDEX', 'INDEX_REQUIRED', 'UNKNOWN_DOMAIN'}, result
        batch = [row[key] for row in result['items']]
        assert len(batch) == len(set(batch)) and not (values & set(batch)), 'Duplicate paginated item'
        values.update(batch)
        assert bool(result['next_cursor']) == bool(result['has_more']), result
        if not result['has_more']: break
        cursor = result['next_cursor']; assert cursor not in cursors, 'Repeated cursor'; cursors.add(cursor)
    assert values == set(expected), {'missing': list(set(expected) - values)[:8], 'extra': list(values - set(expected))[:8], 'returned': len(values), 'expected': len(expected)}
    return {'pages': pages, 'items': len(values)}


def witness(raw, result, uid):
    if result['status'] not in {'ROOT', 'CONNECTED'}: return 0
    current = result.get('root_uid'); count = 0
    for step in result['path']:
        edge = step['edge']; child = raw.node(step['uid']); parent = raw.node(step['parent_uid'])
        if edge['relation'] == 'SAME_CONCEPT':
            row = raw.c.execute('SELECT * FROM bridges WHERE id=?', (edge['id'],)).fetchone()
            assert row and row['status'] == 'ACTIVE' and {row['left_uid'], row['right_uid']} == {child['uid'], parent['uid']} and child['component_id'] == parent['component_id']
        else:
            storage = 'entity' if edge.get('terminal_connection') or 'subject_uid' in edge else 'edge'; table = 'entity_relations' if storage == 'entity' else 'edges'
            row = raw.c.execute('SELECT * FROM ' + table + ' WHERE id=?', (edge['id'],)).fetchone()
            left, right = ('subject_uid', 'object_uid') if storage == 'entity' else ('child_uid', 'parent_uid')
            assert row and row[left] == child['uid'] and row[right] == parent['uid'] and row['relation'] == edge['relation']
            assert raw.accepted(child, parent, row, storage), {'uid': uid, 'bad_step': step}
            count += 1
        if current is not None: assert parent['uid'] == current
        current = child['uid']
    assert current == uid
    return count


def validate_class_global_and_task_status(uid,path,task,raw_global_root,raw_boundary):
    # A CLASS may fail global endpoint admission before the task boundary is assessed.
    if raw_global_root:
        assert path['status'] in {'CONNECTED','ROOT'}, path
        if raw_boundary:
            assert task['status']!='ENDPOINT_NOT_APPLICABLE', task
            assert task['task_boundary_reachable'][uid]is True, task
        else:
            assert task['status']=='ENDPOINT_NOT_APPLICABLE'and task['distance']is None and task['applicable']is False, task
            assert task['reasons']=={uid:'NO_VALID_TASK_BOUNDARY_PATH'}, task
            assert task['navigation_root_reachable'][uid]is True and task['task_boundary_reachable'][uid]is False, task
    else:
        assert not raw_boundary, 'A rooted task boundary cannot be reached from an unrooted CLASS'
        assert path['status']=='UNREACHABLE'and path['path']==[], path
        assert task['status']=='ENDPOINT_NOT_APPLICABLE'and task['distance']is None and task['applicable']is False, task
        assert task['reasons']=={uid:'ENDPOINT_NOT_ADMITTED: UNREACHABLE'}, task
        assert task['navigation_root_reachable'][uid]is False and task['task_boundary_reachable'][uid]is None, task


def main():
    if not __debug__: raise RuntimeError('Independent acceptance cannot run with optimized Python')
    p = argparse.ArgumentParser(); p.add_argument('--code', type=Path, required=True); p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--database', type=Path, required=True); p.add_argument('--primary-build', type=Path, required=True); p.add_argument('--reproduction-build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--baseline', type=Path, required=True); p.add_argument('--installed-sdk', action='store_true'); p.add_argument('--large-branch-minimum', type=int, default=1001); p.add_argument('--require-final-child', action='store_true'); p.add_argument('--required-input-count', type=int); p.add_argument('--primary-snapshots-dir', type=Path); p.add_argument('--support-registry', type=Path); p.add_argument('--formal-delivery-config',type=Path); p.add_argument('--review-only-watch-uid',action='append',default=[])
    a = p.parse_args(); a.database = a.database.resolve(); a.output.mkdir(parents=True, exist_ok=True)
    assert a.require_final_child, 'Only actual completed nominal-design-scope final children can use this auditor'
    primary = json.loads(a.primary_build.read_text()); reproduction = json.loads(a.reproduction_build.read_text())
    assert primary['complete'] is True and primary['pass'] is True and reproduction['complete'] is True and reproduction['pass'] is True
    assert primary['revision'] == reproduction['revision'] and primary['build_id'] != reproduction['build_id']
    assert Path(primary['database']).resolve() != Path(reproduction['database']).resolve()
    if not a.installed_sdk:
        assert Path(primary['database']).stat().st_ino != Path(reproduction['database']).stat().st_ino
    if not a.installed_sdk: sys.path.insert(0, str(a.code / 'src'))
    import fineatlas
    if a.installed_sdk: assert 'site-packages' in Path(fineatlas.__file__).parts and Path(fineatlas.__file__).resolve().is_relative_to(Path(sys.prefix))
    from fineatlas import FineAtlas
    c = sqlite3.connect(a.database.as_uri() + '?mode=ro&immutable=1', uri=True); c.row_factory = sqlite3.Row; c.execute('PRAGMA query_only=ON'); c.execute('PRAGMA cache_size=-131072')
    meta = {r['key']: json.loads(r['value']) for r in c.execute('SELECT * FROM metadata')}; revision = meta['database_revision']
    assert revision == primary['revision'] and meta['browse_index_revision'] == revision
    frozen = meta['structure_frozen_build_manifest']
    actual_inputs = file_inventory(a.inputs)
    assert actual_inputs == frozen['inputs'], 'All actual frozen inputs must match the completed database'
    if a.required_input_count is not None: assert len(actual_inputs) == a.required_input_count
    assert fineatlas.__version__==meta['release'].removeprefix('v')
    assert meta.get('nominal_design_scope_repairs')and meta.get('complete_owned_type_repairs')and meta.get('owned_scope_repairs')
    from independent_nominal_formal_binding import bind_formal_sources
    formal_binding=bind_formal_sources(a,meta)
    complete_lineage=meta['structure_nominal_design_resume_parent']
    assert complete_lineage['repair_recipe']=='resume_nominal_design_scope_repairs.py'
    assert complete_lineage['all_derived_indexes_recomputed']is True
    assert complete_lineage['previous_source_stages_replayed']is False and complete_lineage['previous_repair_stages_replayed']is False
    if a.installed_sdk:
        package = Path(fineatlas.__file__).resolve().parent
        actual_code = {'src/fineatlas/' + name: value for name,value in file_inventory(package,{'.py'}).items()}
        wanted_code = {name:value for name,value in frozen['code'].items() if name.startswith('src/fineatlas/')}
    else:
        actual_code = {}
        for directory in ('src/fineatlas','scripts','configs'):
            actual_code.update({directory + '/' + name:value for name,value in file_inventory(a.code / directory,{'.py','.json'}).items()})
        wanted_code = frozen['code']
        assert digest(a.code / 'pyproject.toml') == frozen['packaging']['pyproject.toml']
    assert actual_code == wanted_code, 'Actual SDK/code differs from the completed database inventory'
    lineage_path=Path(formal_binding['actual_promotion_metadata_path'])
    lineage={'parent_database':formal_binding['source_database'],'parent_revision':formal_binding['source_revision'],
             'parent_database_sha256':formal_binding['source_database_sha256'],'parent_receipt_sha256':formal_binding['source_receipt_sha256']}
    scope_parent=Path(lineage['parent_database']).resolve();parent_connection=None;portable_states=None
    if a.installed_sdk:
        assert a.support_registry is not None and a.support_registry.resolve()==a.database.parent.parent/'regression-support/support-registry.json'
        support=json.loads(a.support_registry.read_text());support_root=a.support_registry.resolve().parent
        assert support['database_revision']==revision and support['database_sha256']==json.loads((a.database.parent/'public_download_proof.json').read_text())['database_sha256']
        for name,expected in support['files'].items():
            member=Path(name);assert not member.is_absolute()and '..'not in member.parts and '\\'not in name
            file=support_root/member;assert not file.is_symlink()and file.resolve().is_relative_to(support_root)and digest(file)==expected
        assert a.primary_build.resolve()==support_root/'builds/primary/build_complete.json' and a.reproduction_build.resolve()==support_root/'builds/reproduction/build_complete.json'
        parent_snapshot=support_root/'parent-assertion-states.jsonl.gz'
        assert digest(parent_snapshot)==support['parent_assertion_snapshot_sha256']
        with gzip.open(parent_snapshot,'rt')as stream:
            header=json.loads(next(stream));entries=[json.loads(line)for line in stream if line]
        assert header==support['parent_assertion_snapshot_binding'] and header['pass']is True
        assert header['schema']=='FINEATLAS_PORTABLE_FORMAL_NOMINAL_DIRECT_PARENT_ASSERTION_STATES_V1' and header['candidate_revision']==revision
        assert header['parent_revision']==lineage['parent_revision'] and header['parent_database_sha256']==lineage['parent_database_sha256']
        assert header['parent_receipt_sha256']==lineage['parent_receipt_sha256'] and header['actual_child_build_receipt_sha256']==digest(a.primary_build)
        assert header['quarantine_manifest_sha256']==digest(a.inputs/'structure_source_contracts.json.gz')
        assert header['source9_foundation_header']['candidate_revision']==lineage['parent_revision']
        assert header['source9_foundation_header']['c933_foundation_header']['frozen_temporal_parent_reference_sha256']==digest(a.inputs/'structure_regression_temporal_parent_reference.json')
        assert header['source9_foundation_header']['grandparent_revision']==meta['structure_complete_type_resume_parent']['parent_revision']
        assert digest(support_root/'source9-foundation/parent-assertion-states.jsonl.gz')==header['source9_foundation_snapshot_sha256']
        assert digest(support_root/'source9-foundation/source8-foundation/parent-assertion-states.jsonl.gz')==header['source9_foundation_header']['c933_foundation_snapshot_sha256']
        assert len(entries)==header['canonical_assertions']==81579
        portable_states={(row['table'],row['canonical_id']):row for row in entries};assert len(portable_states)==len(entries)
        parent_stamp=None
    else:
        assert not any(Path(str(scope_parent)+suffix).exists()for suffix in('-wal','-shm','-journal'))
        parent_connection=sqlite3.connect(scope_parent.as_uri()+'?mode=ro&immutable=1',uri=True)
        parent_connection.row_factory=sqlite3.Row;parent_connection.execute('PRAGMA query_only=ON');parent_connection.execute('PRAGMA cache_size=-65536')
        parent_meta={r['key']:json.loads(r['value'])for r in parent_connection.execute('SELECT * FROM metadata')}
        assert parent_meta['database_revision']==lineage['parent_revision']
        parent_stamp=stamp(scope_parent)
    binding = {'scope_parent':str(scope_parent),'scope_parent_revision':lineage['parent_revision'],'scope_parent_stamp':parent_stamp,'scope_parent_basis':'fresh-public-full-row-hash-evidence'if a.installed_sdk else 'actual-closed-parent-sql','scope_parent_lineage_sha256':digest(lineage_path),'revision': revision, 'database': str(a.database), 'stamp': stamp(a.database), 'code': str(a.code.resolve()), 'inputs': str(a.inputs.resolve()), 'sdk': fineatlas.__version__, 'snapshot_role':'actual-formal-four-stage-version-only-artifact','actual_formal_source_binding':formal_binding, 'script_sha256':digest(__file__),'formal_binding_implementation_sha256':digest(Path(__file__).with_name('independent_nominal_formal_binding.py')), 'frozen_input_count': len(actual_inputs), 'frozen_input_fingerprints': actual_inputs, 'sdk_code_fingerprints': actual_code, 'primary_receipt_sha256': digest(a.primary_build), 'reproduction_receipt_sha256': digest(a.reproduction_build)}
    snapshot_registry_path = a.inputs / 'structure_primary_source_snapshots.json'
    source_files = {};owned_source_files={};owned_registry_path=a.inputs/'structure_owned_source_snapshots.json'
    if a.require_final_child:
        assert snapshot_registry_path.is_file(), 'Final child portable source registry is absent'
    if snapshot_registry_path.exists():
        assert a.primary_snapshots_dir is not None, 'An explicit primary snapshot directory is mandatory'
        snapshot_registry = json.loads(snapshot_registry_path.read_text())
        assert snapshot_registry['schema'] == 'FINEATLAS_PORTABLE_PRIMARY_SOURCE_SNAPSHOTS_V1'
        assert snapshot_registry['documents'], 'Empty external registry cannot skip final source validation'
        assert len({entry['filename'] for entry in snapshot_registry['documents'].values()}) == len(snapshot_registry['documents'])
        snapshots = a.primary_snapshots_dir.resolve()
        if a.installed_sdk:
            assert snapshots == a.database.parent.parent / 'source-snapshots', 'Public audit cannot borrow historical local source bytes'
        for doc_id, entry in snapshot_registry['documents'].items():
            filename = entry['filename']
            assert filename and Path(filename).name == filename and filename not in ('.','..') and '\\' not in filename
            path = snapshots / filename
            assert path.is_file() and not path.is_symlink() and path.resolve().parent == snapshots
            assert digest(path) == entry['sha256'], {'document_id':doc_id,'official_snapshot_changed':str(path)}
            source_files[doc_id] = {'path':str(path),'sha256':digest(path),'stamp':stamp(path)}
        binding.update(primary_snapshots_directory=str(snapshots),primary_snapshot_files=source_files)
        if owned_registry_path.exists():
            owned_registry=json.loads(owned_registry_path.read_text())
            assert owned_registry['schema']=='FINEATLAS_PORTABLE_PRIMARY_SOURCE_SNAPSHOTS_V1'
            for doc_id,entry in owned_registry['documents'].items():
                filename=entry['filename'];assert filename and Path(filename).name==filename and filename not in('.','..')and '\\'not in filename
                path=snapshots/filename;assert path.is_file()and not path.is_symlink()and path.resolve().parent==snapshots
                assert digest(path)==entry['sha256']
                owned_source_files[doc_id]={'path':str(path),'sha256':entry['sha256'],'stamp':stamp(path)}
            binding.update(owned_source_registry_sha256=digest(owned_registry_path),owned_primary_snapshot_files=owned_source_files)

    checkpoint = a.output / 'checkpoint.json'; previous = json.loads(checkpoint.read_text()) if checkpoint.exists() else {'binding': binding, 'completed': {}}
    assert previous['binding'] == binding, 'Checkpoint belongs to different actual snapshot or independent auditor'
    def stage(name, run):
        if name in previous['completed']:
            receipt = previous['completed'][name]
            assert digest(receipt['path']) == receipt['sha256'], 'Completed independent evidence changed'
            result = json.loads(Path(receipt['path']).read_text())
            assert result.get('pass') is True and result.get('revision') == revision
            return receipt
        start = time.monotonic(); print('START', name, flush=True)
        try:
            value = run(); value['seconds'] = time.monotonic() - start; write(a.output / (name + '.json'), value)
            previous['completed'][name] = {'path': str(a.output / (name + '.json')), 'sha256': digest(a.output / (name + '.json'))}; write(checkpoint, previous)
            print('PASS', name, value['seconds'], flush=True); return value
        except BaseException as e:
            write(a.output / (name + '-failure.json'), {'pass': False, 'revision': revision, 'error': repr(e)}); raise
    manifest = json.loads((a.inputs / 'structure_cars_projection_view_repairs.json').read_text()); projection_uids = {x['uid'] for x in manifest['source_projections']}
    def entrances():
        rows = []; total = Counter()
        for view in ('strict', 'taxonomy', 'membership', 'unified'):
            with FineAtlas(a.database, relation_view=view) as sdk:
                raw = RawSource(c, view); domains = sdk.domains()
                expected = {r['canonical_name']: json.loads(r['root_uids']) for r in c.execute('SELECT * FROM domain_registry')}
                assert {x['domain']: x['root_uids'] for x in domains} == expected
                for entry in domains:
                    for alias in entry['aliases']: assert sdk.domain(alias)['domain_id'] == entry['domain_id']
                    comps = {raw.node(uid)['component_id'] for uid in entry['root_uids'] if raw.admitted(raw.node(uid))}
                    for coarse in (True, False):
                        expected_children = raw.direct(comps, coarse, entry['domain_id'])
                        result = collect_pages(lambda **kw: sdk.browse_children_page(entry['domain'], node_kind=None, include_coarse=coarse, **kw), 'identity_component', expected_children, revision)
                        rows.append({'view': view, 'domain': entry['domain'], 'include_coarse': coarse, **result}); total['direct_pages'] += result['pages']; total['direct_items'] += result['items']
                    expected_members={r[0]for r in c.execute('SELECT uid FROM domain_members WHERE domain_id=?AND view=?',(entry['domain_id'],view))}
                    result=collect_pages(lambda **kw:sdk.domain_page(entry['domain'],node_kind=None,**kw),'uid',expected_members,revision,997)
                    rows.append({'view':view,'domain':entry['domain'],'kind':'ALL_ROLES','complete_members':result});total['all_member_pages']+=result['pages'];total['all_member_items']+=result['items']
                    # A separately paginated member list: whole typed-configuration subset
                    # for every portal; full all-role root branches above remain direct.
                    expected_configs = {r[0] for r in c.execute("SELECT uid FROM domain_members WHERE domain_id=? AND view=? AND role='CONFIGURATION'", (entry['domain_id'], view))}
                    result = collect_pages(lambda **kw: sdk.domain_page(entry['domain'], node_kind='CONFIGURATION', **kw), 'uid', expected_configs, revision, 997)
                    rows.append({'view': view, 'domain': entry['domain'], 'kind': 'CONFIGURATION', **result}); total['configuration_pages'] += result['pages']; total['configuration_items'] += result['items']
                write(a.output / ('entrances-' + view + '.json'), rows)
        return {'pass': True, 'revision': revision, 'domains': len(expected), 'views': 4, 'census': dict(total), 'records': rows, 'scope': 'Complete direct pagination of all four-view domain entrances, both route display modes; full CONFIGURATION member pagination for every entrance. Complete all-role recursive member pagination is also independently checked for every overlapping domain.'}
    def whole_source_claim_census():
        payload = json.loads(gzip.decompress((a.inputs / 'structure_source_contracts.json.gz').read_bytes()))
        old_states = Counter(); linked = Counter(); new_records = []; old_count = 0
        raw = RawSource(c)
        owned_reviews = verified_owned_reviews(c,a.inputs)
        for item in payload['quarantines']:
            old_count += 1; table = item['table']; locator = item['locator']
            assert item['asserted_semantically_false'] is False
            keys = [key for key in ('child_uid','parent_uid','subject_uid','object_uid','relation','source','layer') if key in locator]
            rows = c.execute('SELECT * FROM ' + table + ' WHERE ' + ' AND '.join(key + '=?' for key in keys), [locator[key] for key in keys]).fetchall()
            parent_rows = parent_connection.execute('SELECT * FROM ' + table + ' WHERE ' + ' AND '.join(key + '=?' for key in keys), [locator[key] for key in keys]).fetchall()if parent_connection else None
            histories = c.execute('SELECT * FROM usability_changes WHERE object_id=? AND object_type=? AND stage=?',
                (str(item['original_source_assertion']['id']),table,'source_semantic_contract')).fetchall()
            matches = (check_quarantine_states(item,rows,parent_rows,histories,owned_reviews)if parent_connection else
                check_portable_quarantine_states(item,rows,portable_states[table,item['original_source_assertion']['id']],histories,owned_reviews))
            for row in matches: old_states[table + ':' + row['relation'] + ':' + row['status']] += 1
            for prefix in ('child','parent'):
                node = raw.node(item[prefix + '_source_record']['uid']); assert hashlib.sha256(node['data'].encode()).hexdigest() == item[prefix + '_raw_sha256']
        assert old_count == 81579
        write(a.output / 'all-81579-quarantine-state-preservation.json', {'pass':True,'revision':revision,'scope_parent':str(scope_parent),'scope_parent_revision':lineage['parent_revision'],'canonical_quarantines':old_count,'all_same_content_sibling_states':dict(old_states),'precise_frozen_owned_withdrawals':len(owned_reviews),'policy':'Frozen canonical original assertion ID plus exact ACTIVE-to-scope-review history; every historical sibling retains the completed parent raw row, status and reason. No arbitrary REJECTED allowance.'})
        input_names = ['structure_regression_repairs.json','structure_oem_body_scope_repairs.json','structure_complete_subject_scope_repairs.json']
        # Enumerate additive frozen manifests, including later mapping deltas;
        # only actual link operations contribute to the source-arc census.
        for path in sorted(a.inputs.glob('structure_*.json')):
            candidate = json.loads(path.read_text())
            if path.name not in input_names and isinstance(candidate,dict) and candidate.get('operations_file') and 'operations_sha256' in candidate and 'operation_count' in candidate:
                input_names.append(path.name)
        expected_new_count = 0; reviewed_references = []
        for input_name in input_names:
            frozen = json.loads((a.inputs / input_name).read_text()); operation_path = a.inputs / frozen['operations_file']
            assert digest(operation_path) == frozen['operations_sha256']
            operations = [json.loads(line) for line in operation_path.read_text().splitlines() if line]; assert len(operations) == frozen['operation_count']
            for op in operations:
                review_table={'review_bridge':'bridges','review_typed_relation':'entity_relations','review_class_edge':'edges'}.get(op.get('op'))
                if review_table:
                    assert_no_assertion_index_leak(c,review_table,op['before_assertion']['id'])
                if op.get('op')=='retain_design_reference':
                    reference=verify_retained_design_reference(c,op)
                    reviewed_references.append({'uid':op['uid'],'parent':op['parent'],'relation':reference['relation'],'source':reference['source'],
                        'record_id':reference['id'],'preserved_original_record_id':op['before_assertion']['id'],'standalone_retained_reference':True})
                if op.get('non_navigation_reference_relation'):
                    source=op['source']+': prior-bridge:'+op['content_sha256']
                    refs=c.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',
                        (op['uid'],op['parent'],op['non_navigation_reference_relation'],source)).fetchall()
                    assert len(refs)==1
                    verify_source_declared_reference(c,refs[0],op['proof'])
                    reviewed_references.append({'uid':op['uid'],'parent':op['parent'],'relation':refs[0]['relation'],'source':source,'record_id':refs[0]['id']})
            link_operations = [op for op in operations if op.get('op') == 'link']
            expected_new_count += len(link_operations)
            for op in link_operations:
                table = 'edges' if op['relation'] in {'IS_A','TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT'} else 'entity_relations'
                left,right = ('child_uid','parent_uid') if table == 'edges' else ('subject_uid','object_uid')
                rows = c.execute('SELECT * FROM ' + table + ' WHERE ' + left + '=? AND ' + right + '=? AND relation=? AND source=?', (op['uid'],op['parent'],op['relation'],op['source'])).fetchall()
                assert len(rows) == 1, {'new_assertion_multiplicity':op['uid'],'relation':op['relation']}
                row = rows[0]; reference = op['relation'] in NON_NAVIGATION_REFERENCES
                withdrawal=owned_reviews.get((table,row['id']))
                if withdrawal:
                    assert withdrawal[1]==dict(row)and withdrawal[0]['status']=='ACTIVE'and row['status']=='SOURCE_SCOPE_REVIEW'
                    assert_no_assertion_index_leak(c,table,row['id'])
                else:assert row['status'] == 'SOURCE_DECLARED' if reference else row['status'] in {'ACTIVE','TYPED_ACTIVE'}, {'new_assertion_wrong_status':op['uid'],'relation':op['relation'],'status':row['status']}
                if reference:
                    verify_source_declared_reference(c,row,op['proof'])
                    assert not c.execute('SELECT 1 FROM browse_links WHERE relation=? LIMIT 1',(op['relation'],)).fetchone(), 'Non-navigation derivation reference leaked into an actual browse index'
                if table == 'entity_relations': evidence_id = row['evidence_id']
                else:
                    provenance = json.loads(row['provenance'])
                    evidence_ids = provenance.get('evidence_ids',[]) if isinstance(provenance,dict) else provenance
                    assert isinstance(evidence_ids,list) and len(evidence_ids) == 1
                    evidence_id = evidence_ids[0]
                evidence = c.execute('SELECT payload,payload_sha256 FROM evidence WHERE evidence_id=?', (evidence_id,)).fetchone()
                assert evidence and json.loads(evidence[0]) == op['proof'] and hashlib.sha256(evidence[0].encode()).hexdigest() == evidence[1]
                assert json.loads(row['data'])['admission_basis'] == op['proof']
                child, parent = raw.node(op['uid']), raw.node(op['parent'])
                assert hashlib.sha256(child['data'].encode()).hexdigest() == op['proof']['native_record_sha256']
                if 'parent_native_record_sha256' in op['proof']: assert hashlib.sha256(parent['data'].encode()).hexdigest() == op['proof']['parent_native_record_sha256']
                views = []
                for view in ('strict','taxonomy','membership','unified'):
                    contract = RawSource(c,view)
                    if contract.accepted(child,parent,row,'edge' if table == 'edges' else 'entity') and child['component_id'] != parent['component_id']:
                        match = c.execute('SELECT 1 FROM browse_links WHERE view=? AND parent_component=? AND child_component=? AND role=? AND relation=?', (view,parent['component_id'],child['component_id'],child['role'],op['relation'])).fetchone()
                        assert match, {'missing_actual_typed_index':op['uid'],'view':view}; views.append(view)
                if reference or withdrawal: assert views == [], {'non_navigation_reference_admitted':op['uid']}
                else: assert views, {'no_legal_browse_view':op['uid']}
                linked[input_name + ':' + op['relation']] += 1
                new_records.append({'uid':op['uid'],'parent':op['parent'],'relation':op['relation'],'source':op['source'],'record_id':row['id'],'storage':table,'status':row['status'],'navigation_eligible':not reference and not withdrawal,'later_scope_withdrawal':bool(withdrawal),'index_views':views})
        assert len(new_records) == expected_new_count
        assert sum(x['operation_count'] for x in (json.loads((a.inputs / name).read_text()) for name in input_names[:3])) == 2802
        write(a.output / 'all-new-source-index-links.json',new_records)
        write(a.output / 'all-reviewed-nonnavigation-source-references.json',reviewed_references)
        # All changed original visibility rows must equal the frozen review cohorts.
        allowed = {x['uid']: ('ACTIVE','SOURCE_ONLY') for x in manifest['source_projections']}
        third = json.loads((a.inputs / 'structure_complete_subject_scope_repairs.json').read_text())
        for x in third.get('source_class_activations',[]): allowed[x['uid']] = (x['before_visibility'],'ACTIVE')
        c.execute('ATTACH DATABASE ? AS original', (a.baseline.resolve().as_uri()+'?mode=ro&immutable=1',))
        actual = {r[0]:(r[1],r[2]) for r in c.execute('SELECT b.uid,b.visibility,n.visibility FROM original.nodes b JOIN main.nodes n ON n.uid=b.uid WHERE b.visibility IS NOT n.visibility')}
        assert actual == allowed and len(actual) == 170, {'visibility_census':len(actual),'expected':len(allowed)}
        for uid in allowed:
            before = c.execute('SELECT * FROM original.nodes WHERE uid=?',(uid,)).fetchone(); after = raw.node(uid)
            assert all(after.get(k) == v for k,v in dict(before).items() if k not in {'component_id','visibility'})
        c.execute('DETACH DATABASE original')
        return {'pass':True,'revision':revision,'old_scope_review_assertions':old_count,'old_states':dict(old_states),'new_source_assertions':len(new_records),'new_scope_links':sum(row['navigation_eligible'] for row in new_records),'new_nonnavigation_references':sum(row['relation']in NON_NAVIGATION_REFERENCES for row in new_records),'reviewed_nonnavigation_references':len(reviewed_references),'exact_later_scope_withdrawals':sum(row['later_scope_withdrawal']for row in new_records),'new_links':dict(linked),'exact_original_visibility_changes':len(actual),'limits':'SOURCE_SCOPE_REVIEW retained as pending evidence, not a declaration that every old claim is false. New sourced connections do not restore unresolved fine source/model scope.'}
    def primary_source_document_census():
        reviewed = json.loads((a.inputs / 'structure_primary_aircraft_family_repairs.json').read_text())['primary_documents']
        external = {key:value for key,value in reviewed.items() if value.get('source_kind') != 'SOURCE_OWNED_COMPLETE_DESCRIPTION'}
        assert set(external) == set(snapshot_registry['documents']) == set(source_files)
        owned = {}
        for doc_id, document in reviewed.items():
            if doc_id in external:
                entry = snapshot_registry['documents'][doc_id]
                assert entry['sha256'] == document['sha256'] and entry['source_uri'] == document['source_uri']
                assert entry['hash_basis'] == 'HTTP_RESPONSE_BODY_BYTES' and entry['source_uri'].startswith('https://')
                assert entry['revision_locator'] and entry['mime_type'] and entry['redistribution_authorization']
            else:
                row = c.execute('SELECT data FROM nodes WHERE uid=?',(document['database_source_uid'],)).fetchone()
                assert row and hashlib.sha256(row[0].encode()).hexdigest() == document['sha256']
                owned[doc_id] = {'uid':document['database_source_uid'],'sha256':document['sha256']}
        retrieval_sha = None
        if a.installed_sdk:
            path = a.database.parent.parent / 'checks/primary-source-retrieval.json'
            receipt = json.loads(path.read_text())
            assert receipt['schema'] == 'FINEATLAS_FRESH_PRIMARY_SOURCE_RETRIEVAL_V1'
            assert receipt['pass'] is True and receipt['complete'] is True and receipt['fresh_official_https_retrieval'] is True
            assert receipt['registry_sha256'] == digest(snapshot_registry_path) and Path(receipt['snapshots_directory']).resolve() == snapshots
            assert set(receipt['documents']) == set(external)
            from urllib.parse import urlparse
            for doc_id, row in receipt['documents'].items():
                entry = snapshot_registry['documents'][doc_id]
                assert row['source_uri'] == entry['source_uri'] and row['sha256'] == entry['sha256']
                assert row['retrieved_from_network'] is True and row['http_status'] == 200 and row['retrieved_utc']
                assert row['mime_type'] == entry['mime_type'] and row['byte_count'] == Path(source_files[doc_id]['path']).stat().st_size
                final = urlparse(row['final_uri']); official = urlparse(entry['source_uri'])
                assert final.scheme == 'https' and final.hostname == official.hostname
            retrieval_sha = digest(path)
        return {'pass':True,'revision':revision,'source_registry_sha256':digest(snapshot_registry_path),
                'actual_external_files':source_files,'actual_source_owned_sql_documents':owned,
                'fresh_public_retrieval_receipt_sha256':retrieval_sha,'absolute_historical_path_fallback':False}
    if source_files:
        stage('primary-portable-source-document-census', primary_source_document_census)
    def owned_primary_source_census():
        owned_manifest=json.loads((a.inputs/'structure_owned_scope_repairs.json').read_text())
        ops_path=a.inputs/owned_manifest['operations_file'];assert digest(ops_path)==owned_manifest['operations_sha256']
        operations=[json.loads(line)for line in ops_path.read_text().splitlines()if line]
        def docs(raw):
            if isinstance(raw,dict):
                if raw.get('source_kind')=='PRIMARY_MANUFACTURER_OR_REGULATOR':yield raw
                for v in raw.values():yield from docs(v)
            elif isinstance(raw,list):
                for v in raw:yield from docs(v)
        needed={(doc['source_uri'],doc['sha256'])for op in operations for doc in docs(op.get('proof',{}))}
        registered={}
        for registry in(snapshot_registry,owned_registry):
            for entry in registry['documents'].values():
                key=(entry['source_uri'],entry['sha256'])
                if key in registered:assert registered[key]==entry
                registered[key]=entry
        assert needed<=set(registered)
        verified={}
        for uri,sha in needed:
            entry=registered[uri,sha];path=snapshots/entry['filename']
            assert uri.startswith('https://')and entry['hash_basis']=='HTTP_RESPONSE_BODY_BYTES'
            assert path.is_file()and not path.is_symlink()and digest(path)==sha
            verified[entry['filename']]={'source_uri':uri,'sha256':sha}
        annotations=[]
        if any(op['op']=='migrate_nominal_design_mapping'for op in operations):
            author={row['file']:row for row in owned_manifest['author_annotation_files']};assert len(author)==9
            seen=set()
            for split in('train','val','test'):
                values={}
                for field in('variant','family','manufacturer'):
                    name='images_'+field+'_'+split+'.txt';row=author[name];filename=row.get('filename',name)
                    assert filename and Path(filename).name==filename
                    path=a.inputs/filename;assert digest(path)==row['sha256']and path.stat().st_size==row['bytes']
                    parsed=[line.split(' ',1)for line in path.read_text().splitlines()if line]
                    assert all(len(r)==2 and r[1]for r in parsed)
                    values[field]=dict(parsed);assert len(values[field])==len(parsed)
                assert len({frozenset(v)for v in values.values()})==1
                for image in sorted(values['variant']):
                    assert image not in seen;seen.add(image)
                    annotations.append({'image_id':image,'split':split,**{field:v[image]for field,v in values.items()}})
            assert len(annotations)==10000 and len({r['variant']for r in annotations})==100
        retrieval=None
        if a.installed_sdk:
            path=a.database.parent.parent/'checks/owned-source-retrieval.json';receipt=json.loads(path.read_text())
            primary_path=a.database.parent.parent/'checks/primary-source-retrieval.json'
            assert receipt['schema']=='FINEATLAS_FRESH_OWNED_SOURCE_RETRIEVAL_V1'and receipt['pass']is True and receipt['complete']is True and receipt['errors']==[]
            assert receipt['fresh_additional_official_https_retrieval']is True and receipt['registry_sha256']==digest(owned_registry_path)
            assert receipt['preserved_primary_retrieval_sha256']==digest(primary_path)and Path(receipt['snapshots_directory']).resolve()==snapshots
            primary_keys={(r['source_uri'],r['sha256'])for r in snapshot_registry['documents'].values()}
            extra={key:r for key,r in owned_registry['documents'].items()if(r['source_uri'],r['sha256'])not in primary_keys}
            assert set(receipt['documents'])==set(extra)
            from urllib.parse import urlparse
            for key,entry in extra.items():
                row=receipt['documents'][key];path=snapshots/entry['filename']
                assert row['source_uri']==entry['source_uri']and row['sha256']==entry['sha256']and row['filename']==entry['filename']
                assert row['http_status']==200 and row['retrieved_from_network']is True and row['retrieved_utc']
                assert row['byte_count']==path.stat().st_size and row['mime_type']==entry['mime_type']
                assert urlparse(row['final_uri']).scheme=='https'and urlparse(row['final_uri']).hostname==urlparse(entry['source_uri']).hostname
            retrieval=digest(a.database.parent.parent/'checks/owned-source-retrieval.json')
        return {'pass':True,'revision':revision,'actual_required_primary_sources':verified,'author_annotations_verified':len(annotations),
            'owned_source_registry_sha256':digest(owned_registry_path),'actual_source_files':owned_source_files,
            'fresh_additional_public_retrieval_sha256':retrieval,'host_source_fallback':False}
    if owned_source_files:stage('owned-portable-source-and-author-annotation-census',owned_primary_source_census)
    stage('whole-source-claim-and-index-census', whole_source_claim_census)
    def whole_active_identity_role_census():
        rows=[dict(r)for r in c.execute('SELECT n.component_id,count(DISTINCT '+role_sql()+') role_count,min(n.uid) representative_uid FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility="ACTIVE" GROUP BY n.component_id HAVING role_count>1')]
        write(a.output/'whole-active-identity-role-conflicts.json',rows)
        assert not rows, {'unexplained_active_identity_role_conflicts':rows}
        no_profile=dict(c.execute('SELECT '+role_sql()+' role,count(*) FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility="ACTIVE" AND p.uid IS NULL GROUP BY role'))
        operations=[];owned_path=a.inputs/'structure_owned_scope_repairs.json'
        if owned_path.exists():
            frozen=json.loads(owned_path.read_text());operations=[json.loads(line)for line in(a.inputs/frozen['operations_file']).read_text().splitlines()if line]
        checked=[]
        with FineAtlas(a.database,relation_view='unified')as sdk:
            raw=RawSource(c)
            for uid in sorted({op['uid']for op in operations if op.get('op')=='correct_role'}):
                actual=raw.node(uid);node=sdk.node(uid)
                assert node['node_kind']==actual['role']
                op=next(op for op in operations if op.get('op')=='correct_role'and op['uid']==uid)
                normalize=c.execute('SELECT * FROM normalization_roles WHERE uid=?',(uid,)).fetchone()
                profile=c.execute('SELECT * FROM node_profiles WHERE uid=?',(uid,)).fetchone()
                assert normalize and profile and dict(normalize)==op['after_normalization_role']and dict(profile)==op['after_profile']
                assert normalize['canonical_role']==actual['role']
                proof=c.execute('SELECT payload FROM evidence WHERE evidence_id=?',(normalize['evidence_id'],)).fetchone();assert proof and json.loads(proof[0])==op['proof']and json.loads(proof[0]).get('basis')
                histories=c.execute('SELECT before_json,after_json,evidence FROM usability_changes WHERE stage="owned_scope_repairs" AND object_type="role_scope_correction" AND object_id=?',(uid,)).fetchall()
                before={'profile':op['before_profile'],'normalization_role':op['before_normalization_role']};after={'profile':op['after_profile'],'normalization_role':op['after_normalization_role']}
                assert sum(json.loads(h['before_json'])==before and json.loads(h['after_json'])==after and json.loads(h['evidence'])==op['proof']for h in histories)==1
                path=sdk.path_result(uid)
                if actual['role']=='UNKNOWN':
                    assert normalize['status']=='REVIEW'and json.loads(profile['attributes'])['allowed_views']==[]and path['status']=='VIEW_NOT_APPLICABLE'
                    verify_unknown_catalog_isolation(c,uid)
                    distance=sdk.distance(uid,meta['root_uid'],policy='design');assert distance['distance']is None and not distance.get('applicable')
                else:assert normalize['status']=='VERIFIED';witness(raw,path,uid)
                checked.append({'uid':uid,'public_role':node['node_kind'],'raw_canonical_role':actual['role'],'source_rank':actual['rank'],'normalization_role':dict(normalize),'navigation_status':path['status']})
        return {'pass':True,'revision':revision,'active_mixed_role_components':0,'all_no_profile_active_source_role_counts':no_profile,
            'actual_adjudicated_role_public_checks':checked,'scope':'Whole active component canonical-role census includes no-profile native rank fallback; source-backed corrected roles, normalization evidence and public navigation checked separately.'}
    stage('whole-active-identity-role-census',whole_active_identity_role_census)
    def complete_owned_type_role_and_public_scope_checks():
        manifest_path=a.inputs/'structure_complete_owned_type_repairs.json'
        assert manifest_path.exists(),'Final child requires actual complete-owned source inputs'
        frozen=json.loads(manifest_path.read_text());ops_path=a.inputs/frozen['operations_file']
        assert digest(ops_path)==frozen['operations_sha256']
        operations=[json.loads(line)for line in ops_path.read_text().splitlines()if line]
        allowed={'link','correct_role','review_typed_relation','review_class_edge','retain_source_scope_reference'}
        assert all(op.get('op')in allowed for op in operations),'New source operation requires an explicit independent contract'
        assert len(operations)==frozen['operation_count']
        role_ops=[op for op in operations if op['op']=='correct_role'];link_ops=[op for op in operations if op['op']=='link']
        role_records=[];public_records=[];references=[]
        raw=RawSource(c)
        freeze_inputs=meta['structure_frozen_build_manifest']['inputs']
        def own_field(record,field_path):
            value=record
            for key in field_path.split('.'):
                assert isinstance(value,dict)and key in value,'Missing complete own-source field'
                value=value[key]
            return value
        for op in role_ops:
            uid=op['uid'];proof=op['proof'];own=raw.node(uid)
            variants=[(proof.get(prefix+'_record'),proof.get(prefix+'_locator'))for prefix in
                      ('source_role_review','source_instance_review','source_additional_role_review')]
            selected=[pair for pair in variants if pair[0]is not None];assert len(selected)==1
            review,locator=selected[0];assert review['uid']==uid and locator['uid']==uid
            role=review.get('approved_role',review.get('approved_new_role')or 'UNKNOWN')
            assert role==op['after_profile']['node_kind']==own['role']
            assert role in {'CLASS','MODEL','MODEL_FAMILY','INSTANCE','UNKNOWN'}
            assert hashlib.sha256(own['data'].encode()).hexdigest()==proof['native_record_sha256']
            before_node=proof.get('complete_before_node')or review.get('complete_source_node')
            assert before_node and {key:own[key]for key in before_node}==before_node,'Role change modified raw source object'
            assert locator['file']==Path(locator['file']).name
            review_file=a.inputs/locator['file'];assert digest(review_file)==locator['sha256']==freeze_inputs[locator['file']]
            approved=json.loads(review_file.read_text());assert review in approved['records']
            for w in proof['source_witnesses']:
                source=raw.node(w['uid']);assert hashlib.sha256(source['data'].encode()).hexdigest()==w['data_sha256']
                assert own_field(json.loads(source['data']),w['field_path'])==w['statement']
            for table,field in [('node_profiles','after_profile'),('normalization_roles','after_normalization_role')]:
                row=c.execute('SELECT *FROM '+table+' WHERE uid=?',(uid,)).fetchone();assert row and dict(row)==op[field]
            norm=op['after_normalization_role'];profile=op['after_profile'];attrs=json.loads(profile['attributes'])
            wanted='REVIEW'if role=='UNKNOWN'else'VERIFIED'
            assert own['role']==norm['canonical_role']==profile['node_kind']and norm['status']==wanted and attrs['role_status']==wanted
            if role=='UNKNOWN':assert attrs['allowed_views']==[] and proof['allowed_views']==[]
            if role=='CLASS':assert attrs['canonical_scope_guard']=='GENERIC_PHYSICAL_KIND'and proof['individual_semantic_review']is True
            evidence=c.execute('SELECT *FROM evidence WHERE evidence_id=?',(profile['evidence_id'],)).fetchone()
            assert evidence and json.loads(evidence['payload'])==proof and evidence['payload_sha256']==hashlib.sha256(evidence['payload'].encode()).hexdigest()
            assert evidence['source_name']==op['source']and evidence['source_uri']==op['uri']
            histories=c.execute('SELECT before_json,after_json,evidence FROM usability_changes WHERE stage="complete_owned_type_repairs"AND object_type="role_source_adjudication"AND object_id=?',(uid,)).fetchall()
            before={'profile':op['before_profile'],'normalization_role':op['before_normalization_role']};after={'profile':profile,'normalization_role':norm}
            assert sum(json.loads(h['before_json'])==before and json.loads(h['after_json'])==after and json.loads(h['evidence'])==proof for h in histories)==1
            assert proof['world_identity_assertion']is False and proof['no_identity_merges']is True
            role_records.append({'uid':uid,'after_role':role,'complete_source_sha256':proof['native_record_sha256'],'frozen_review_sha256':locator['sha256'],'actual_history_matches':1})
        for op in operations:
            if op['op']!='retain_source_scope_reference':continue
            proof=op['proof'];before=proof['original_assertion'];table=proof['original_assertion_table']
            assert table in {'edges','entity_relations'}and proof['navigation_allowed']is False and proof['allowed_views']==[]and proof['is_class_inclusion']is False
            content={k:v for k,v in before.items()if k not in {'id','status','reason'}}
            assert hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest()==proof['original_assertion_content_sha256']
            assert any(review['op']in {'review_typed_relation','review_class_edge'}and review['before_assertion']==before for review in operations)
            original=c.execute('SELECT *FROM '+table+' WHERE id=?',(before['id'],)).fetchone()
            assert original and dict(original)=={**before,'status':'SOURCE_SCOPE_REVIEW'}
            rows=c.execute('SELECT *FROM entity_relations WHERE subject_uid=?AND object_uid=?AND relation=?AND source=?',(op['uid'],op['parent'],op['relation'],op['source'])).fetchall();assert len(rows)==1
            row=rows[0];data=json.loads(row['data'])
            assert row['status']=='SOURCE_DECLARED'and data['allowed_views']==[]and data['navigation_allowed']is False and data['is_class_inclusion']is False and data['admission_basis']==proof
            evidence=c.execute('SELECT payload,payload_sha256 FROM evidence WHERE evidence_id=?',(row['evidence_id'],)).fetchone()
            assert evidence and json.loads(evidence['payload'])==proof and hashlib.sha256(evidence['payload'].encode()).hexdigest()==evidence['payload_sha256']
            assert_no_assertion_index_leak(c,'entity_relations',row['id']);assert_no_assertion_index_leak(c,table,before['id'])
            histories=c.execute('SELECT before_json,after_json,evidence FROM usability_changes WHERE stage="complete_owned_type_repairs"AND object_type="complete_owned_source_scope_reference"AND object_id=?',(op['uid'],)).fetchall()
            assert sum(json.loads(h['before_json'])==before and json.loads(h['after_json'])==dict(row)and json.loads(h['evidence'])==proof for h in histories)==1
            references.append({'uid':op['uid'],'parent':op['parent'],'reference_id':row['id'],'reviewed_original_id':before['id'],'no_navigation_index_leak':True})
        affected={op['uid']for op in operations}
        for view in ('strict','taxonomy','membership','unified'):
            with FineAtlas(a.database,relation_view=view)as sdk:
                raw=RawSource(c,view)
                for uid in sorted(affected):
                    own=raw.node(uid);node=sdk.node(uid);assert node['node_kind']==own['role']
                    path=sdk.path_result(uid);state=sdk.connection_status(uid);closure=raw.closure(uid)
                    rooted=raw.node(meta['root_uid'])['component_id']in closure
                    assert state['root_reachable']==rooted and path['status']==state['path_status'];witness(raw,path,uid)
                    parents=sdk.neighbors(uid,'parents',10000);assert not parents.has_more
                    if own['role']=='UNKNOWN':
                        assert path['status']=='VIEW_NOT_APPLICABLE'and path['path']==[] and state['root_reachable']is False
                        assert sdk.distance(uid,uid,policy='design')['distance']is None and sdk.lca(uid,uid,policy='design')['applicable']is False
                        assert not parents
                        assert not c.execute('SELECT 1 FROM browse_links WHERE view=?AND (parent_component=?OR child_component=?)',(view,own['component_id'],own['component_id'])).fetchone()
                        assert not c.execute('SELECT 1 FROM domain_components WHERE view=?AND component_id=?',(view,own['component_id'])).fetchone()
                        assert not c.execute('SELECT 1 FROM view_roots WHERE view=?AND component_id=?AND root_reachable=1',(view,own['component_id'])).fetchone(),'UNKNOWN has a cached admitted root'
                        assert not c.execute('SELECT 1 FROM view_paths WHERE view=?AND component_id=?',(view,own['component_id'])).fetchone(),'UNKNOWN has a cached admitted root path'
                        assert not c.execute("SELECT 1 FROM view_terminal_connections WHERE uid=?",(uid,)).fetchone()
                        assert not c.execute("SELECT 1 FROM entity_connections WHERE uid=?AND wordnet_reachable=1",(uid,)).fetchone()
                        catalogue=c.execute('SELECT role,view_mask FROM browse_nodes WHERE uid=?',(uid,)).fetchone()
                        assert catalogue and catalogue['role']=='UNKNOWN'and catalogue['view_mask']==0
                    checked=[]
                    for op in (op for op in link_ops if op['uid']==uid):
                        storage='edge'if op['relation']=='IS_A'else'entity';table='edges'if storage=='edge'else'entity_relations';left,right=('child_uid','parent_uid')if storage=='edge'else('subject_uid','object_uid')
                        claims=[dict(row)for row in c.execute('SELECT * FROM '+table+' WHERE '+left+'=? AND '+right+'=? AND relation=?',(uid,op['parent'],op['relation']))if row['source']==op['source']and json.loads(row['data']).get('admission_basis')==op['proof']]
                        assert len(claims)==1;claim=claims[0];parent=raw.node(op['parent']);accepted=raw.accepted(own,parent,claim,storage)
                        exposed=[p for p in parents if p['uid']==op['parent']and p['edge']['id']==claim['id']and p['edge']['relation']==op['relation']]
                        assert bool(exposed)==accepted, 'Actual final source fine-parent API inclusion differs from raw view contract'
                        if accepted:assert parent['component_id']in closure
                        checked.append({'parent':op['parent'],'relation':op['relation'],'record_id':claim['id'],'raw_view_eligible':accepted,'public_parent_visible':bool(exposed)})
                    public_records.append({'uid':uid,'view':view,'canonical_role':own['role'],'global_root_reachable':rooted,'navigation_status':path['status'],'new_exact_parent_assertions':checked})
        return {'pass':True,'revision':revision,'source_manifest_sha256':digest(manifest_path),'operations_sha256':digest(ops_path),'operation_count':len(operations),'actual_source_roles':role_records,'retained_source_scope_references':references,'all_view_public_scope_checks':public_records,'scope':'Exact approved final delta roles, own raw source rows, evidence/history and all-view public parent/root witnesses; no identity or label mapping inferred from a role.'}
    stage('complete-owned-type-role-and-public-scope-checks',complete_owned_type_role_and_public_scope_checks)

    def nominal_design_scope_exact_source_and_public_views():
        manifest_path=a.inputs/'structure_nominal_design_scope_repairs.json';assert manifest_path.is_file()
        manifest=json.loads(manifest_path.read_text());operations_path=a.inputs/manifest['operations_file']
        assert digest(manifest_path)==meta['structure_frozen_build_manifest']['inputs'][manifest_path.name]
        assert digest(operations_path)==manifest['operations_sha256']==meta['structure_frozen_build_manifest']['inputs'][operations_path.name]
        operations=[json.loads(line)for line in operations_path.read_text().splitlines()if line]
        assert len(operations)==manifest['operation_count']and operations
        assert {op['op']for op in operations}<={'link','correct_role','review_class_edge'},'A new operation kind requires an explicit independent observer contract.'
        role_ops={op['uid']:op for op in operations if op['op']=='correct_role'}
        assert len(role_ops)==sum(op['op']=='correct_role'for op in operations),'Duplicate nominal role transition'
        role_records=[verify_nominal_role_transition(c,a.inputs,op)for op in role_ops.values()]
        withdrawal_records=[verify_nominal_class_withdrawal(c,a.inputs,op)for op in operations if op['op']=='review_class_edge']
        records=[];sources=Counter()
        for op in (op for op in operations if op['op']=='link'):
            axis=op['classification_axis'];proof=op['proof']
            source_review=verify_nominal_source_approval(c,a.inputs,op,'approved_source_directions')
            verify_nominal_classification_axis(op,source_review)
            assert proof['whole_subject_scope_review']is True and proof['world_identity_assertion']is False and proof['no_identity_merges']is True
            table,left,right=('edges','child_uid','parent_uid')if op['relation']=='IS_A'else('entity_relations','subject_uid','object_uid')
            rows=c.execute('SELECT *FROM '+table+' WHERE '+left+'=?AND '+right+'=?AND relation=?AND source=?',(op['uid'],op['parent'],op['relation'],op['source'])).fetchall()
            assert len(rows)==1;row=rows[0];assert row['status']=='ACTIVE'
            data=json.loads(row['data']);assert data['admission_basis']==proof and data['classification_axis']==axis
            eid='usability:'+hashlib.sha256(json.dumps(proof,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            evidence=c.execute('SELECT *FROM evidence WHERE evidence_id=?',(eid,)).fetchone()
            assert evidence and json.loads(evidence['payload'])==proof and hashlib.sha256(evidence['payload'].encode()).hexdigest()==evidence['payload_sha256']
            assert evidence['source_name']==op['source']and evidence['source_uri']==op['uri']
            if table=='edges':assert eid in json.loads(row['provenance'])['evidence_ids']and data['eligible_for_final_dag']is True
            else:assert row['evidence_id']==eid and data['is_class_inclusion']is False
            original=proof['before_node'];parent=proof['parent_before_node'];actual=RawSource(c)
            for before in (original,parent):
                node=actual.node(before['uid']);assert {key:node[key]for key in before}==before
            for prefix,uid in (('',op['uid']),('parent_',op['parent'])):
                profile=proof[prefix+'before_profile'];normalization=proof[prefix+'before_normalization_role']
                if uid in role_ops:
                    correction=role_ops[uid]
                    assert profile==correction['before_profile']and normalization==correction['before_normalization_role']
                    profile=correction['after_profile'];normalization=correction['after_normalization_role']
                assert dict(c.execute('SELECT *FROM node_profiles WHERE uid=?',(uid,)).fetchone()or{})==(profile or{})
                assert dict(c.execute('SELECT *FROM normalization_roles WHERE uid=?',(uid,)).fetchone()or{})==(normalization or{})
            history=c.execute('SELECT *FROM usability_changes WHERE stage="nominal_design_scope_repairs"AND object_type="nominal_scope_link"AND object_id=?',(op['uid'],)).fetchall()
            assert sum(json.loads(h['before_json'])=={'prior_assertions':proof['prior_assertions']}and json.loads(h['after_json'])=={'table':table,'added_assertion':dict(row)}and json.loads(h['evidence'])==proof for h in history)==1
            for view in ('strict','taxonomy','membership','unified'):
                with FineAtlas(a.database,relation_view=view)as sdk:
                    raw=RawSource(c,view);child,parent=raw.node(op['uid']),raw.node(op['parent']);eligible=raw.accepted(child,parent,row,'edge'if table=='edges'else'entity')
                    neighbors=sdk.neighbors(op['uid'],'parents',10000);assert not neighbors.has_more
                    visible=any(parent_node['uid']==op['parent']and parent_node['edge']['id']==row['id']and parent_node['edge']['relation']==op['relation']for parent_node in neighbors)
                    assert eligible==visible,'New nominal scope source view admission differs from actual public parent interface'
                    path=sdk.path_result(op['uid']);state=sdk.connection_status(op['uid']);closure=raw.closure(op['uid']);rooted=raw.node(meta['root_uid'])['component_id']in closure
                    assert path['status']==state['path_status']and state['root_reachable']==rooted;witness(raw,path,op['uid'])
                    records.append({'uid':op['uid'],'parent':op['parent'],'view':view,'classification_axis':axis,'source_record_id':row['id'],'raw_view_eligible':eligible,'public_parent_exposed':visible,'root_reachable':rooted,'public_path_status':path['status']})
            sources[op['source']]+=1
        for uid in sorted({op['uid']for op in operations if op['op']!='link'}):
            for view in ('strict','taxonomy','membership','unified'):
                with FineAtlas(a.database,relation_view=view)as sdk:
                    raw=RawSource(c,view);own=raw.node(uid);path=sdk.path_result(uid);state=sdk.connection_status(uid)
                    rooted=raw.node(meta['root_uid'])['component_id']in raw.closure(uid)
                    assert path['status']==state['path_status']and state['root_reachable']==rooted;witness(raw,path,uid)
                    parents=sdk.neighbors(uid,'parents',10000);assert not parents.has_more
                    if own['role']=='UNKNOWN':
                        verify_unknown_catalog_isolation(c,uid)
                        distance=sdk.distance(uid,uid,policy='classification',admission_mode='reviewed_paths')
                        assert path['status']=='VIEW_NOT_APPLICABLE'and not rooted and distance['distance']is None and distance['applicable']is False
                        assert not list(parents),'Review-only nominal grain cannot expose navigable parents'
                    for review in (op for op in operations if op['op']=='review_class_edge'and op['uid']==uid):
                        assert not any(parent['edge']['id']==review['before_assertion']['id']and parent['edge']['relation']=='IS_A'for parent in parents),'Reviewed original class scope leaked into SDK parent navigation'
                    records.append({'uid':uid,'view':view,'canonical_role':own['role'],'root_reachable':rooted,'public_path_status':path['status'],'exact_role_or_scope_transition':True})
        actual_sources={source:sum(c.execute('SELECT count(*)FROM '+table+' WHERE source=?',(source,)).fetchone()[0]for table in ('edges','entity_relations'))for source in sources}
        assert actual_sources==dict(sources)
        assert meta['nominal_design_scope_repairs']['operation_kinds']==dict(Counter(op['op']for op in operations))
        return {'pass':True,'revision':revision,'manifest_sha256':digest(manifest_path),'operations_sha256':digest(operations_path),'operation_count':len(operations),'operation_kinds':dict(Counter(op['op']for op in operations)),'actual_source_assertion_counts':actual_sources,'exact_source_role_adjudications':role_records,'exact_source_scope_withdrawals':withdrawal_records,'four_view_public_results':records,'scope':'Actual source9 nominal family/type or generic physical inclusion assertions, exact source-grain corrections or over-narrow class withdrawals; original object fields/source proof/history and public view witnesses. No model identity or commercial label mapping follows from a new direction.'}
    stage('nominal-design-scope-source-and-public-view-consistency',nominal_design_scope_exact_source_and_public_views)

    def repaired_host_views_exports_and_unknown_isolation():
        frozen=json.loads((a.inputs/'structure_owned_scope_repairs.json').read_text())
        ops_path=a.inputs/frozen['operations_file'];assert digest(ops_path)==frozen['operations_sha256']
        operations=[json.loads(line)for line in ops_path.read_text().splitlines()if line]
        hosts=[op for op in operations if op.get('op')=='link'and op.get('relation')=='TAXONOMIC_PARENT'
               and op.get('proof',{}).get('basis')=='OWNED_BIOLOGICAL_CULTIVAR_AND_COMPLETE_SCIENTIFIC_HOST_SCOPE']
        unknown=[op for op in operations if op.get('op')=='correct_role'and op['after_profile']['node_kind']=='UNKNOWN']
        records=[];exports=[];unknown_records=[];cli_records=[]
        def cli_path(uid,view,expected):
            command=[sys.executable,'-B','-m','fineatlas','--data-dir',str(a.database),'--relation-view',view,'path-result',uid]
            environment=dict(os.environ);environment['PYTHONDONTWRITEBYTECODE']='1'
            if a.installed_sdk:environment.pop('PYTHONPATH',None)
            else:environment['PYTHONPATH']=str(a.code/'src')
            completed=subprocess.run(command,check=True,capture_output=True,text=True,env=environment)
            result=json.loads(completed.stdout)
            assert result==expected, 'CLI and public SDK disagree on a repaired source role/path'
            cli_records.append({'view':view,'uid':uid,'command':command,'exit_code':completed.returncode,'status':result['status']})
        for view in('strict','taxonomy','membership','unified'):
            with FineAtlas(a.database,relation_view=view)as sdk:
                raw=RawSource(c,view);export_domains=set()
                for op in hosts:
                    rows=c.execute('SELECT * FROM edges WHERE child_uid=? AND parent_uid=? AND relation=? AND source=?',
                        (op['uid'],op['parent'],op['relation'],op['source'])).fetchall();assert len(rows)==1
                    row=rows[0];verify_scientific_host_edge(row,op['proof'])
                    assert not c.execute('SELECT 1 FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',
                        (op['uid'],op['parent'],op['relation'],op['source'])).fetchone(), 'Biological host stored as non-navigable entity relation'
                    node=sdk.node(op['uid']);assert node['node_kind']=='BIOLOGICAL_VARIANT'
                    neighbors=sdk.neighbors(op['uid'],'parents',10000);assert not neighbors.has_more
                    exact=[p for p in neighbors if p['uid']==op['parent']and p['edge']['id']==row['id']and p['edge']['relation']=='TAXONOMIC_PARENT']
                    path=sdk.path_result(op['uid']);state=sdk.connection_status(op['uid'])
                    assert path['status']==state['path_status']
                    hierarchy=sdk.eligibility(op['uid'],'hierarchy');species=sdk.eligibility(op['uid'],'species')
                    assert species['usable']is False, 'Cultivar host navigation silently promoted a species endpoint'
                    distance=sdk.distance(op['uid'],op['parent'],policy='classification')
                    if view in('taxonomy','unified'):
                        assert len(exact)==1 and path['status']=='CONNECTED'and state['root_reachable']is True
                        assert raw.node(meta['root_uid'])['component_id']in raw.closure(op['uid'])
                        witness(raw,path,op['uid']);assert hierarchy['usable']is True
                        cli_path(op['uid'],view,path)
                        assert distance['applicable']is True and distance['distance']==1
                        membership=[r[0]for r in c.execute('SELECT dr.canonical_name FROM domain_members dm JOIN domain_registry dr ON dr.domain_id=dm.domain_id WHERE dm.uid=? AND dm.view=?',(op['uid'],view))]
                        assert membership, 'Rooted cultivar missing from every actual domain member index'
                        export_domains.update(membership)
                    else:
                        assert not exact and path['status']=='VIEW_NOT_APPLICABLE'and state['view_admitted']is False and state['root_reachable']is False
                        assert hierarchy['usable']is False and distance['distance']is None and not distance['applicable']
                    records.append({'view':view,'uid':op['uid'],'host_uid':op['parent'],'record_id':row['id'],'storage':'edge',
                        'source_status':row['status'],'public_role':node['node_kind'],'navigation_status':path['status'],
                        'hierarchy_eligibility':hierarchy,'species_eligibility':species,'classification_distance':distance})
                for op in unknown:
                    uid=op['uid'];node=sdk.node(uid);assert node['node_kind']=='UNKNOWN'and node['visibility']=='ACTIVE'
                    path=sdk.path_result(uid);state=sdk.connection_status(uid)
                    assert path['status']=='VIEW_NOT_APPLICABLE'and state['view_admitted']is False and not path['path']and state['root_reachable']is False
                    cli_path(uid,view,path)
                    assert not sdk.neighbors(uid,'parents',10000)and not sdk.neighbors(uid,'children',10000)
                    assert sdk.browse_children_page(uid)['status']=='NOT_ADMITTED'
                    verify_unknown_catalog_isolation(c,uid)
                    assert not c.execute('SELECT 1 FROM domain_members WHERE uid=? AND view=?',(uid,view)).fetchone()
                    distances={}
                    for policy in('classification','design','configuration'):
                        result=sdk.distance(uid,meta['root_uid'],policy=policy)
                        assert result['distance']is None and result['applicable']is False and result.get('reasons')
                        distances[policy]=result
                    unknown_records.append({'view':view,'uid':uid,'source_visibility':node['visibility'],'path':path,'connection_status':state,'distances':distances})
                for domain in sorted(export_domains):
                    path=a.output/('host-biological-variant-domain-export-'+view+'-'+domain+'.jsonl')
                    result=sdk.export_domain(domain,path,node_kind='BIOLOGICAL_VARIANT',page_size=997)
                    expected={r[0]for r in c.execute('SELECT dm.uid FROM domain_members dm JOIN domain_registry dr ON dr.domain_id=dm.domain_id WHERE dr.canonical_name=? AND dm.view=? AND dm.role="BIOLOGICAL_VARIANT"',(domain,view))}
                    seen=set();host_seen=set()
                    for line in path.read_text().splitlines():
                        exported=json.loads(line);uid=exported['node']['uid'];assert uid not in seen;seen.add(uid)
                        assert exported['relation_view']==view and exported['node']['node_kind']=='BIOLOGICAL_VARIANT'
                        for op in hosts:
                            if uid==op['uid']:
                                source_row=next(r for r in records if r['view']==view and r['uid']==uid)
                                assert any(e['id']==source_row['record_id']and e['relation']=='TAXONOMIC_PARENT'and e['parent_uid']==op['parent']for e in exported['parents'])
                                assert exported['task_admission']['usable']is True;host_seen.add(uid)
                    assert seen==expected and result['nodes']==len(seen)
                    needed={op['uid']for op in hosts if op['uid']in expected};assert host_seen==needed
                    exports.append({'view':view,'domain':domain,'complete_biological_variant_export_rows':len(seen),'host_uids':sorted(host_seen),'path':str(path),'sha256':digest(path)})
        return {'pass':True,'revision':revision,'actual_frozen_host_operations':len(hosts),'host_view_results':records,
            'complete_scientific_domain_exports':exports,'actual_matching_cli_paths':cli_records,'actual_frozen_unknown_role_operations':len(unknown),'unknown_public_checks':unknown_records,
            'scope':'Cultivar host source edges are typed scientific navigation in taxonomy/unified, with public parents/root/distance/export consistency. They remain mixed-grain biological variants, unsuitable for species-only tasks. UNKNOWN retains raw ACTIVE visibility but cannot enter any four-view domain/navigation/reward.'}
    stage('repaired-host-views-exports-and-unknown-isolation',repaired_host_views_exports_and_unknown_isolation)
    def abstract_configuration_task_boundary_isolation():
        manifest_path=a.inputs/'structure_nominal_design_scope_repairs.json'
        manifest=json.loads(manifest_path.read_text());ops_path=a.inputs/manifest['operations_file']
        assert digest(ops_path)==manifest['operations_sha256']
        operations=[json.loads(line)for line in ops_path.read_text().splitlines()if line]
        abstract=[]
        for op in operations:
            if op.get('op')=='link'and op.get('classification_axis')=='class_intension':
                review=verify_nominal_source_approval(c,a.inputs,op,'approved_source_directions')
                case=verify_nominal_classification_axis(op,review)
                if case is not None:abstract.append(op)
        records=[]
        for op in abstract:
            review=verify_nominal_source_approval(c,a.inputs,op,'approved_source_directions')
            case=verify_nominal_classification_axis(op,review)
            assert case is not None
            for view in('strict','taxonomy','membership','unified'):
                with FineAtlas(a.database,relation_view=view)as sdk:
                    raw=RawSource(c,view);own=raw.node(op['uid']);assert own['role']=='CLASS'
                    path=sdk.path_result(op['uid']);state=sdk.connection_status(op['uid'])
                    closure=raw.closure(op['uid']);rooted=raw.node(meta['root_uid'])['component_id']in closure
                    assert state['root_reachable']==rooted and state['path_status']==path['status']
                    witness(raw,path,op['uid'])
                    boundaries=[]
                    for domain in('aircraft','locomotives'):
                        entrance=sdk.domain(domain);assert entrance
                        boundary=entrance['root_uids'];goals={raw.node(uid)['component_id']for uid in boundary}
                        task_raw=RawSource(c,view,'classification');task_closure=task_raw.closure(op['uid'])
                        assert not(set(task_closure)&goals),'Abstract configuration acquired physical vehicle task ancestry'
                        task=sdk.distance(op['uid'],op['uid'],policy='classification',admission_mode='reviewed_paths',task_boundary_roots=boundary)
                        assert task['distance']is None and task['applicable']is False and task.get('reasons')
                        assert not c.execute('SELECT 1 FROM domain_members WHERE domain_id=?AND view=?AND uid=?',(entrance['domain_id'],view,op['uid'])).fetchone(),'Abstract source annotation leaked into physical domain members'
                        assert not c.execute('SELECT 1 FROM domain_components WHERE domain_id=?AND view=?AND component_id=?',(entrance['domain_id'],view,own['component_id'])).fetchone(),'Abstract configuration component leaked into physical domain navigation'
                        boundaries.append({'domain':domain,'explicit_boundary_roots':boundary,'raw_task_boundary_reachable':False,'actual_domain_member':False,'task_metric':task})
                    records.append({'uid':op['uid'],'view':view,'canonical_role':own['role'],'source_axis':op['classification_axis'],'source_scope_limits':case['limits'],'raw_source_domains':json.loads(own['domains']or'[]'),'global_navigation_root_reachable':rooted,'global_path_status':path['status'],'physical_task_boundaries':boundaries})
        return {'pass':True,'revision':revision,'manifest_sha256':digest(manifest_path),'operations_sha256':digest(ops_path),'actual_frozen_abstract_configuration_links':len(abstract),'records':records,'scope':'Exact source-approved abstract class intension is distinct from physical aircraft or locomotive identity, persisted domain navigation, and classification task applicability.'}
    stage('abstract-configuration-physical-task-boundary-isolation',abstract_configuration_task_boundary_isolation)
    stage('all-domain-entrance-pagination', entrances)
    def large_branches():
        rows = []
        for view in ('strict', 'taxonomy', 'membership', 'unified'):
            with FineAtlas(a.database, relation_view=view) as sdk:
                raw = RawSource(c, view)
                for comp, count in c.execute('SELECT parent_component,count(DISTINCT child_component) FROM browse_links WHERE view=? GROUP BY parent_component HAVING count(DISTINCT child_component)>=?', (view, a.large_branch_minimum)):
                    uid = c.execute('SELECT uid FROM browse_nodes WHERE component_id=? ORDER BY uid LIMIT 1', (comp,)).fetchone()[0]
                    expected = raw.direct([comp]); result = collect_pages(lambda **kw: sdk.browse_children_page(uid, node_kind=None, include_coarse=True, **kw), 'identity_component', expected, revision, 997)
                    rows.append({'view': view, 'parent_uid': uid, 'raw_count': len(expected), 'index_count': count, **result}); assert len(expected) == count
                    write(a.output / 'large-branches-progress.json', rows)
        return {'pass': True, 'revision': revision, 'complete_above_minimum': a.large_branch_minimum, 'records': rows}
    stage('all-large-direct-branches', large_branches)
    def labels_and_sources():
        counts = Counter(); records = []; endpoints = [dict(r) for r in c.execute('SELECT * FROM dataset_targets WHERE dataset IN (' + ','.join('?' for _ in DATASETS) + ')', list(DATASETS))]; assert len(endpoints) == 755
        for view in ('strict', 'taxonomy', 'membership', 'unified'):
            with FineAtlas(a.database, relation_view=view) as sdk:
                raw = RawSource(c, view)
                for row in endpoints:
                    uid = row['target_uid']; path = sdk.path_result(uid); state = sdk.connection_status(uid)
                    assert path['status'] == state['path_status'] and state['root_reachable'] == (path['status'] in {'ROOT', 'CONNECTED'})
                    steps = witness(raw, path, uid); counts[view + ':' + path['status']] += 1
                    if uid in projection_uids:
                        assert path['status'] == 'NOT_ADMITTED' and not state['root_reachable']
                        assert sdk.browse_children_page(uid)['status'] == 'NOT_ADMITTED'
                        distance = sdk.distance(uid, meta['root_uid'], policy='configuration'); assert distance['distance'] is None and not distance.get('applicable')
                    records.append({'view': view, 'dataset': row['dataset'], 'class_id': row['class_id'], 'uid': uid, 'status': path['status'], 'witness_nonidentity_arcs': steps})
        for uid in projection_uids:
            assert not c.execute('SELECT 1 FROM browse_nodes WHERE uid=?', (uid,)).fetchone()
            assert not c.execute('SELECT 1 FROM domain_members WHERE uid=?', (uid,)).fetchone()
        assert c.execute("SELECT count(*) FROM entity_relations WHERE relation='SOURCE_MODEL_REFERENCE' AND status='ACTIVE'").fetchone()[0] == 0
        return {'pass': True, 'revision': revision, 'labels': 755, 'views': 4, 'source_only_projection_count': len(projection_uids), 'states': dict(counts), 'records': records}
    stage('all-label-source-witnesses', labels_and_sources)
    def source_class_domain_and_task_boundaries():
        owned_path=a.inputs/'structure_owned_scope_repairs.json';records=[]
        if not owned_path.exists():return {'pass':True,'revision':revision,'records':records}
        scope=json.loads(owned_path.read_text());operations=[json.loads(line)for line in(a.inputs/scope['operations_file']).read_text().splitlines()if line]
        with FineAtlas(a.database,relation_view='unified')as sdk:
            raw=RawSource(c,'unified','classification');entry=sdk.domain('aircraft');boundary=entry['root_uids'];goals={raw.node(uid)['component_id']for uid in boundary}
            candidates={r[0]for r in c.execute('SELECT n.uid FROM nodes n JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility="ACTIVE" AND p.node_kind="CLASS" AND p.domain="tools" AND EXISTS(SELECT 1 FROM json_each(n.domains) d WHERE d.value="aircraft")')}
            for op in operations:
                if op.get('op')!='link':continue
                child,parent=raw.node(op['uid']),raw.node(op['parent'])
                if child and parent and 'aircraft'in json.loads(child['domains']or'[]')and parent['role']=='CLASS':candidates.add(parent['uid'])
            for uid in sorted(candidates):
                own=raw.node(uid);node=sdk.node(uid);profile=c.execute('SELECT domain FROM node_profiles WHERE uid=?',(uid,)).fetchone()
                if 'aircraft'in json.loads(own['domains']or'[]'):
                    assert node['domain']=='aircraft'and 'aircraft'in json.loads(node['domains'])
                registered=c.execute('SELECT 1 FROM domain_members WHERE domain_id=? AND view="unified" AND uid=?',(entry['domain_id'],uid)).fetchone()
                text=own['label'];normalized=' '.join(re.sub(r'[\W_]+',' ',text.lower()).split());legacy=' '.join(re.sub(r'[^a-z0-9]+',' ',text.lower()).split())or normalized
                expected={r[0]for r in c.execute('SELECT DISTINCT n.uid FROM aliases a JOIN nodes origin ON origin.uid=a.uid JOIN nodes n ON n.component_id=origin.component_id JOIN domain_members dm ON dm.uid=n.uid WHERE a.alias IN (?,?) AND dm.domain_id=? AND dm.view="unified"',(normalized,legacy,entry['domain_id']))if raw.admitted(raw.node(r[0]))}
                result=collect_pages(lambda **kw:sdk.search_page(text,domain='aircraft',exact=True,**kw),'uid',expected,revision,13)
                if registered:assert uid in expected
                closure=raw.closure(uid);reachable=bool(set(closure)&goals)
                task=sdk.distance(uid,uid,policy='classification',admission_mode='reviewed_paths',task_boundary_roots=boundary)
                path=sdk.path_result(uid);witness(raw,path,uid)
                global_root=raw.node(meta['root_uid'])['component_id']in closure
                validate_class_global_and_task_status(uid,path,task,global_root,reachable)
                records.append({'uid':uid,'native_domains':json.loads(own['domains']or'[]'),'profile_hint_domain':profile[0]if profile else None,
                    'public_domain':node['domain'],'public_profile_hint':node.get('profile_domain'),'actual_domain_member':bool(registered),'complete_exact_search':result,
                    'global_navigation_status':path['status'],'explicit_task_boundary':boundary,'raw_task_boundary_reachable':reachable,'sdk_task_relation':task})
        return {'pass':True,'revision':revision,'source_class_parents_checked':len(records),'records':records,
            'scope':'Native domain declaration/display, persisted actual domain filters, global navigation, and explicit classification task-boundary reachability are checked separately; no generic root connection substitutes for a task path.'}
    stage('source-class-domain-and-explicit-task-boundaries',source_class_domain_and_task_boundaries)
    def system_source_root_and_aircraft_boundary_isolation():
        frozen=json.loads((a.inputs/'structure_owned_scope_repairs.json').read_text());operation_file=a.inputs/frozen['operations_file']
        assert digest(operation_file)==frozen['operations_sha256']
        operations=[json.loads(line)for line in operation_file.read_text().splitlines()if line]
        heads=[op for op in operations if op.get('op')=='link'and op.get('proof',{}).get('owned_physical_scope_kind')=='OWNED_PHYSICAL_INSTRUMENTALITY'
               and 'physical_instrumentality_scope_review'in op.get('proof',{})]
        carrier_reviews=[op for op in operations if op.get('op')=='review_class_edge'and op.get('proof',{}).get('basis')=='OWNED_SYSTEM_NOT_ITS_CARRIER_PLATFORM']
        assert heads and carrier_reviews, 'The final child omitted the requested frozen system/carrier scope adjudication'
        assert {op['uid']for op in heads}=={op['uid']for op in carrier_reviews}, 'A reviewed system-carrier inclusion needs its independently grounded broad instrumentality replacement'
        raw=RawSource(c);uids={op['uid']for op in heads};systems={raw.node(uid)['component_id']for uid in uids}
        design_ops=[op for op in operations if op.get('op')=='link'and op.get('relation')=='DESIGN_TYPE_OF'and raw.node(op['parent'])['component_id']in systems]
        assert design_ops, 'Frozen source system nominal-design scope was omitted'
        for op in design_ops:
            own=raw.node(op['uid']);proof=op['proof'];scope=proof['nominal_design_type_scope_review']
            assert own['role']in('MODEL','MODEL_FAMILY')and proof['whole_subject_scope_review']is True
            assert proof['owned_physical_scope_kind']=='OWNED_NOMINAL_DESIGN_FUNCTION_OR_PURPOSE'
            assert proof['dataset_mapping_promotion']is False and proof['world_identity_assertion']is False and proof['no_identity_merges']is True
            assert scope['uid']==op['uid']and scope['parent']==op['parent']and scope['proposed_relation']=='DESIGN_TYPE_OF'
            assert scope['owned_complete_source_witness']['uid']==op['uid']
            assert scope['owned_complete_source_witness']['data_sha256']==hashlib.sha256(own['data'].encode()).hexdigest()
            uids.add(own['uid'])
        # Historical incoming aircraft function assertions are inspected separately;
        # their own physical aircraft scope does not establish system-model identity.
        historical_incoming=[]
        for component in systems:
            for row in c.execute('SELECT r.* FROM entity_relations r JOIN nodes p ON p.uid=r.object_uid WHERE p.component_id=? AND r.status="ACTIVE" AND r.relation="DESIGN_TYPE_OF"',(component,)):
                if row['subject_uid']not in uids:historical_incoming.append(dict(row))
        records=[];pagination=[];watch_records=[]
        for view in('strict','taxonomy','membership','unified'):
            with FineAtlas(a.database,relation_view=view)as sdk:
                entrance=sdk.domain('aircraft');assert entrance
                boundary=entrance['root_uids'];raw=RawSource(c,view);goals={raw.node(uid)['component_id']for uid in boundary}
                for uid in sorted(uids):
                    own=raw.node(uid);policy='classification'if own['role']=='CLASS'else'design'
                    source_closure=raw.closure(uid);root_reachable=raw.node(meta['root_uid'])['component_id']in source_closure
                    path=sdk.path_result(uid);status=sdk.connection_status(uid)
                    assert status['root_reachable']==root_reachable and path['status']==status['path_status']
                    if view in('taxonomy','unified'):assert root_reachable and path['status']=='CONNECTED'
                    witness(raw,path,uid)
                    task_raw=RawSource(c,view,policy);task_closure=task_raw.closure(uid)
                    boundary_reachable=bool(set(task_closure)&goals);assert not boundary_reachable, 'System range was inherited from its aircraft carrier or manufacturer'
                    result=sdk.distance(uid,uid,policy=policy,admission_mode='reviewed_paths',task_boundary_roots=boundary)
                    assert result['status']=='ENDPOINT_NOT_APPLICABLE'and result['distance']is None and result['applicable']is False
                    if view in('taxonomy','unified'):assert 'NO_VALID_TASK_BOUNDARY_PATH'in result['reasons'].values()
                    assert not c.execute('SELECT 1 FROM domain_members WHERE domain_id=? AND view=? AND uid=?',(entrance['domain_id'],view,uid)).fetchone(), 'Native aircraft annotation leaked an unrelated system into the aircraft domain'
                    assert not c.execute('SELECT 1 FROM domain_components WHERE domain_id=? AND view=? AND component_id=?',(entrance['domain_id'],view,own['component_id'])).fetchone()
                    records.append({'view':view,'uid':uid,'canonical_role':own['role'],'raw_native_domains':json.loads(own['domains']or'[]'),
                        'root_path_status':path['status'],'raw_global_root_reachable':root_reachable,'aircraft_task_boundary':boundary,
                        'raw_aircraft_task_boundary_reachable':False,'actual_aircraft_domain_member':False,'explicit_aircraft_task_metric':result})
                for role in sorted({raw.node(uid)['role']for uid in uids}):
                    expected={r[0]for r in c.execute('SELECT uid FROM domain_members WHERE domain_id=? AND view=? AND role=?',(entrance['domain_id'],view,role))}
                    assert not(expected&uids)
                    result=collect_pages(lambda **kw:sdk.domain_page('aircraft',node_kind=role,**kw),'uid',expected,revision,997)
                    pagination.append({'view':view,'domain':'aircraft','role':role,'complete_domain_member_pages':result,'system_uid_leak_count':0})
                for uid in a.review_only_watch_uid:
                    own=raw.node(uid);assert own and own['visibility']=='SOURCE_ONLY'
                    assert not any(op.get('uid')==uid and op.get('op')in('link','correct_role')for op in operations)
                    path=sdk.path_result(uid);state=sdk.connection_status(uid)
                    assert path['status']=='NOT_ADMITTED'and state['root_reachable']is False and not raw.closure(uid)
                    assert not c.execute('SELECT 1 FROM browse_nodes WHERE uid=?',(uid,)).fetchone()
                    assert not c.execute('SELECT 1 FROM domain_members WHERE uid=?',(uid,)).fetchone()
                    metric=sdk.distance(uid,meta['root_uid'],policy='classification')
                    assert metric['distance']is None and metric['applicable']is False
                    watch_records.append({'view':view,'uid':uid,'source_visibility':own['visibility'],'public_path':path,'distance':metric})
        return {'pass':True,'revision':revision,'frozen_instrumentality_scope_replacements':len(heads),'frozen_carrier_scope_reviews':len(carrier_reviews),
            'dynamic_system_and_design_uids':sorted(uids),'historical_incoming_not_certified_as_system_designs':historical_incoming,'cohort_basis':'Frozen new complete own nominal-system design operations, not historical incoming TYPE declarations','records':records,'complete_aircraft_role_pagination':pagination,'explicit_source_only_regression_watches':watch_records,
            'scope':'Source-native domain annotation is provenance. A physical system and its declared system designs can reach the global artifact root while remaining outside the explicit aircraft task boundary and actual aircraft domain tree. Generic UID structural distances are not asserted to be aircraft label rewards.'}
    stage('system-source-root-and-aircraft-boundary-isolation',system_source_root_and_aircraft_boundary_isolation)
    def retained_design_references_and_scoped_physical_paths():
        manifest=json.loads((a.inputs/'structure_owned_scope_repairs.json').read_text());path=a.inputs/manifest['operations_file']
        assert digest(path)==manifest['operations_sha256']
        operations=[json.loads(line)for line in path.read_text().splitlines()if line]
        references=[op for op in operations if op.get('op')=='retain_design_reference']
        links=[op for op in operations if op.get('op')=='link'and 'design_derivation_physical_scope_review'in op.get('proof',{})]
        assert references and {op['uid']for op in references}=={op['uid']for op in links}
        source_path=a.inputs/manifest['source_design_derivation_review_file'];assert source_path.name==manifest['source_design_derivation_review_file']
        assert digest(source_path)==manifest['source_design_derivation_review_sha256']
        source=json.loads(source_path.read_text());assert source['source_revision']==manifest['completed_parent_revision']
        raw=RawSource(c);records=[];views=[]
        for op in references:
            reference=verify_retained_design_reference(c,op);proof=op['proof']
            physical=next(link for link in links if link['uid']==op['uid']);physical_proof=physical['proof']
            matches=[r for r in source['physical_reference_records']if r['uid']==op['uid']];assert len(matches)==1
            review=matches[0]
            assert proof['design_derivation_scope_review']==physical_proof['design_derivation_physical_scope_review']==review
            assert review['identity_or_mapping_promotion']is False and review['configuration_equality_assertion']is False
            assert review['design_purpose_not_inherited_from_operator']is True and review['future_narrow_parent_kind_not_certified']is True
            assert physical_proof['no_design_purpose_inheritance']is True and physical_proof['no_identity_merges']is True
            assert physical_proof['world_identity_assertion']is False and physical_proof['classification_axis']=='physical_structure'
            assert physical['relation']=='DESIGN_TYPE_OF'and physical['parent']==review['proposed_broad_physical_link']['parent']
            assert physical_proof['literal_own_aircraft_genus_asserted']==review['proposed_broad_physical_link']['literal_own_aircraft_genus_asserted']
            for candidate in(op,physical):
                assert candidate['proof']['source_review_locator']=={'file':source_path.name,'sha256':digest(source_path),'uid':candidate['uid'],'parent':candidate['parent'],'relation':candidate['relation']}
            for group in('child_source_objects','parent_source_objects'):
                for item in review[group]:
                    before=item['node'];after=raw.node(before['uid'])
                    assert all(after.get(k)==v for k,v in before.items()if k!='component_id')
                    assert hashlib.sha256(after['data'].encode()).hexdigest()==item['native_data_sha256']
            for before in review['preserved_original_relations']:
                assert dict(c.execute('SELECT * FROM entity_relations WHERE id=?',(before['id'],)).fetchone())==before
            for bridge in review['parent_own_same_primary_source_bridge']:
                assert dict(c.execute('SELECT * FROM bridges WHERE id=?',(bridge['id'],)).fetchone())==bridge and bridge['status']=='ACTIVE'
            records.append({'uid':op['uid'],'reference_parent_uid':op['parent'],'reference_record_id':reference['id'],'reference_status':reference['status'],
                'original_reviewed_relation_id':op['before_assertion']['id'],'physical_parent_uid':physical['parent'],'literal_own_aircraft_genus_asserted':physical_proof['literal_own_aircraft_genus_asserted'],
                'identity_or_mapping_promoted':False,'purpose_inherited':False,'configuration_equality_asserted':False})
        for view in('strict','taxonomy','membership','unified'):
            with FineAtlas(a.database,relation_view=view)as sdk:
                raw=RawSource(c,view,'design')
                for op in references:
                    parent_component=raw.node(op['parent'])['component_id'];closure=raw.closure(op['uid'])
                    assert parent_component not in closure, 'Preserved reference was reused as an active model-family navigation arc'
                    neighbors=sdk.neighbors(op['uid'],'parents',10000);assert not neighbors.has_more
                    assert not any(parent['edge']['relation']=='SOURCE_DESIGN_DERIVATION_REFERENCE'or raw.node(parent['uid'])['component_id']==parent_component for parent in neighbors)
                    task=sdk.distance(op['uid'],op['uid'],policy='design',admission_mode='reviewed_paths',task_boundary_roots=[op['parent']])
                    assert task['status']=='ENDPOINT_NOT_APPLICABLE'and task['distance']is None and task['applicable']is False
                    if view in('taxonomy','unified'):assert 'NO_VALID_TASK_BOUNDARY_PATH'in task['reasons'].values()
                    physical=next(link for link in links if link['uid']==op['uid']);physical_parent=raw.node(physical['parent'])['component_id']
                    if view in('strict','taxonomy','unified'):
                        assert physical_parent in closure
                        assert any(parent['uid']==physical['parent']and parent['edge']['relation']=='DESIGN_TYPE_OF'for parent in neighbors)
                        path=sdk.path_result(op['uid']);assert path['status']=='CONNECTED';witness(RawSource(c,view),path,op['uid'])
                    views.append({'view':view,'uid':op['uid'],'no_design_reference_parent_route':True,'reference_parent_task_metric':task,
                        'broad_physical_parent_reachable':physical_parent in closure,'public_navigable_parent_relations':sorted({parent['edge']['relation']for parent in neighbors})})
        return {'pass':True,'revision':revision,'standalone_retained_design_references':len(references),'scoped_physical_replacements':len(links),
            'portable_source_review_sha256':digest(source_path),'records':records,'public_view_and_reward_route_checks':views,
            'scope':'Complete reviewed nominal design derivation facts are preserved without identity, purpose or configuration inheritance; SOURCE_DECLARED refs are excluded from navigation/indexes and reviewed training task routes. Independently proved broad aircraft physical edges remain navigable.'}
    stage('retained-design-references-and-scoped-physical-paths',retained_design_references_and_scoped_physical_paths)



    def all_pairs():
        configs = json.loads((a.inputs / 'legacy_policies.json').read_text()); counts = Counter(); rows = []; totals = Counter()
        with FineAtlas(a.database, relation_view='unified') as sdk:
            for dataset, size in DATASETS.items():
                conf = configs[dataset]; index = sdk.relation_reward_index(dataset, **conf); assert len(index.labels) == size
                raw = RawSource(c, 'unified', conf['policy'], conf.get('source_scope'), conf.get('coarse_roots', []))
                closures = {cid: raw.closure(label['uid']) for cid, label in index.labels.items() if not label['reason']}
                blocked = {raw.node(meta['root_uid'])['component_id']}
                for uid in conf.get('coarse_roots', []): blocked.update(raw.closure(uid))
                for answer in index.pairs():
                    left, right = answer['left'], answer['right']; totals[dataset] += 1; counts[dataset + ':' + answer['status']] += 1
                    assert answer['database_revision'] == revision
                    if answer['status'] == 'ENDPOINT_NOT_APPLICABLE':
                        assert answer['distance'] is None and answer.get('reasons')
                        for cid, reason in answer['reasons'].items():
                            target = c.execute('SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?', (dataset, cid)).fetchone()
                            check = c.execute('SELECT * FROM dataset_mapping_checks WHERE dataset=? AND class_id=?', (dataset, cid)).fetchone()
                            if reason.startswith('ANNOTATION_SCOPE_REVIEW'): assert check and check['status'] == 'ANNOTATION_SCOPE_REVIEW'
                            if reason.startswith('IDENTITY_UNCONFIRMED'): assert target['decision_status'] != 'VERIFIED' or not sdk.target(dataset, cid)['identity_verified']
                    elif answer['status'] in {'APPLICABLE', 'COARSE_COMMON_ANCESTOR_ONLY', 'NO_COMMON_ANCESTOR'}:
                        one, two = closures[left], closures[right]; common = set(one) & set(two)
                        # Exclude a common candidate if another common descendant reaches it.
                        lowest = {comp for comp in common if not any(comp in raw.next(other) for other in common if other != comp)}
                        assert {x['component_id'] for x in answer['lcas']} == lowest
                        informative = lowest - blocked
                        informative = {comp for comp in informative if not any(x['component_id'] == comp and x['rank'] in COARSE for x in answer['lcas'])}
                        expected_status = 'APPLICABLE' if informative else 'COARSE_COMMON_ANCESTOR_ONLY' if common else 'NO_COMMON_ANCESTOR'
                        assert answer['status'] == expected_status, (dataset, left, right, answer['status'], expected_status)
                        expected_distance = min(one[comp] + two[comp] for comp in informative) if informative else None
                        assert answer['distance'] == expected_distance
                    else:
                        assert answer['distance'] is None and answer.get('conflicts', []) or answer['status'] == 'CYCLIC_LINEAGE', answer
                    rows.append({'dataset': dataset, 'left': left, 'right': right, 'status': answer['status'], 'distance': answer['distance'], 'lca_components': sorted(x['component_id'] for x in answer['lcas'])})
                assert totals[dataset] == size * (size - 1) // 2
        assert sum(totals.values()) == 56917
        write(a.output / 'independent-all-pairs.json', rows)
        return {'pass': True, 'revision': revision, 'pairs': 56917, 'dataset_totals': dict(totals), 'states': dict(counts), 'policy_sha256': digest(a.inputs / 'legacy_policies.json'), 'endpoint_semantics': 'Public SDK frozen endpoint decisions with raw annotation scope rejection binding; geometry independently traverses raw source assertions and profiles, no build classifier or cached role imports.'}
    stage('all-fixed-policy-pair-geometry', all_pairs)
    def names_filters_and_cli():
        records = []; queries = set(); filters = []; cli_records = []
        with FineAtlas(a.database, relation_view='unified') as sdk:
            raw = RawSource(c)
            for entry in sdk.domains():
                # English/native and Chinese names for every actual root, when present.
                for uid in entry['root_uids']:
                    node = raw.node(uid)
                    if not raw.admitted(node): continue
                    queries.add((node['label'], entry['domain']))
                    for name, language in c.execute("SELECT name,language FROM node_names WHERE uid=? ORDER BY preferred DESC,name", (uid,)):
                        if language.lower().startswith('zh'): queries.add((name, entry['domain']))
                comps = {raw.node(uid)['component_id'] for uid in entry['root_uids'] if raw.admitted(raw.node(uid))}
                children = raw.direct(comps, True, entry['domain_id'])
                selected = None
                for comp in sorted(children):
                    for facet, value, uid in c.execute('SELECT facet,value,uid FROM browse_facets WHERE component_id=? ORDER BY facet,value,uid', (comp,)):
                        if facet in {'source','manufacturer','year','brand','color','country','material','catalogue','series'} and raw.admitted(raw.node(uid)):
                            selected = (facet, value); break
                    if selected: break
                if selected:
                    facet, value = selected
                    matching = set()
                    for comp in children:
                        if any(raw.admitted(raw.node(r[0])) for r in c.execute('SELECT uid FROM browse_facets WHERE component_id=? AND facet=? AND value=?', (comp, facet, value))): matching.add(comp)
                    result = collect_pages(lambda **kw: sdk.browse_children_page(entry['domain'], node_kind=None, filters={facet:value}, include_coarse=True, **kw), 'identity_component', matching, revision)
                    filters.append({'domain': entry['domain'], 'facet': facet, 'value': value, **result})
            # Every Chinese source name among the already integrated living records.
            living_records = []
            for filename in ('living_catalogue_records.jsonl','living_catalogue_extension_records.jsonl'):
                living_records.extend(json.loads(line) for line in (a.inputs / filename).read_text().splitlines() if line)
            living_admitted = {r['uid']: r for r in living_records if r.get('status') == 'ADMIT_SOURCE_CONFIGURATION'}
            for uid, row in living_admitted.items():
                assert raw.admitted(raw.node(uid)), {'missing_living_uid':uid}
                for name, language in c.execute('SELECT name,language FROM node_names WHERE uid=?', (uid,)):
                    if language.lower().startswith('zh'): queries.add((name, row['domain']))
            for text, domain in sorted(queries):
                normalized = ' '.join(re.sub(r'[\W_]+',' ', text.lower()).split())
                legacy = ' '.join(re.sub(r'[^a-z0-9]+',' ', text.lower()).split()) or normalized
                expected = set()
                for row in c.execute('SELECT DISTINCT n.uid FROM aliases a JOIN nodes origin ON origin.uid=a.uid JOIN nodes n ON n.component_id=origin.component_id JOIN domain_members dm ON dm.uid=n.uid JOIN domain_registry dr ON dr.domain_id=dm.domain_id WHERE a.alias IN (?,?) AND dr.canonical_name=? AND dm.view=?', (normalized,legacy,domain,'unified')):
                    if raw.admitted(raw.node(row[0])): expected.add(row[0])
                result = collect_pages(lambda **kw: sdk.search_page(text, domain=domain, exact=True, **kw), 'uid', expected, revision, 13)
                records.append({'text': text,'domain':domain,'chinese':bool(re.search('[\u3400-\u9fff]',text)), **result})
                assert expected, {'name_not_indexed_or_wrong_scope':text,'domain':domain}
            # Cursor context mismatch must reject reuse across actual domain scopes.
            domain_names = [x['domain'] for x in sdk.domains()]
            for domain in domain_names:
                page = sdk.domain_page(domain, limit=1)
                if page['next_cursor']:
                    other = next(x for x in domain_names if x != domain)
                    try: sdk.domain_page(other, limit=1, cursor=page['next_cursor'])
                    except ValueError: break
                    raise AssertionError('Cross-domain cursor was accepted')
            for case in (["browse-page","furniture","--limit","3"], ["browse-page","lighting","--node-kind","CONFIGURATION","--limit","3"], ["path-result",sorted(projection_uids)[0]], ["distance",sorted(projection_uids)[0],meta['root_uid'],"--policy","configuration"]):
                command = [sys.executable,'-m','fineatlas','--data-dir',str(a.database),*case]
                environment = dict(os.environ)
                if a.installed_sdk: environment.pop('PYTHONPATH',None)
                else: environment['PYTHONPATH'] = str(a.code / 'src')
                completed = subprocess.run(command, check=True, capture_output=True, text=True, env=environment); value = json.loads(completed.stdout)
                assert value.get('status') not in {'STALE_INDEX','INDEX_REQUIRED'}
                if case[0] == 'path-result': assert value['status'] == 'NOT_ADMITTED' and value['path'] == []
                if case[0] == 'distance': assert value['distance'] is None
                cli_records.append({'command':command,'value':value,'exit_code':completed.returncode})
        return {'pass':True,'revision':revision,'exact_name_queries':len(records),'chinese_queries':sum(x['chinese'] for x in records),'living_admitted_configuration_census':len(living_admitted),'queries':records,'facet_filter_full_pagination':filters,'cli':cli_records,'scope':'Every admitted domain-root native name and available Chinese root names; all Chinese names on integrated living configurations; one actual nonempty facet filter per domain where available.'}
    stage('names-domain-filters-and-cli', names_filters_and_cli)
    assert all(stamp(Path(row['path'])) == row['stamp'] and digest(row['path']) == row['sha256'] for row in [*source_files.values(),*owned_source_files.values()]), 'Explicit source bytes changed during audit'
    assert stamp(a.database) == binding['stamp'] and (a.installed_sdk or stamp(scope_parent) == parent_stamp), 'Readonly audit artifact or scope parent changed'
    write(a.output / 'summary.json', {'schema': 'FINEATLAS_EXTERNAL_COMPLETE_OWNED_TYPE_FINAL_INTERFACE_AUDIT_V1', 'pass': True, 'binding': binding, 'completed': previous['completed']})


if __name__ == '__main__': main()
