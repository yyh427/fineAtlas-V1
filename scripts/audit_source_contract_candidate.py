#!/usr/bin/env python3
"""Read-only independent acceptance of frozen source-contract dispositions.

No production adapter parser or graph admission function is called. Complete
source assertions, exact multiplicities, individual disposition ledgers and
literal parent scope are checked independently. Semantic sampling has a frozen
expected ledger and is reported separately from full mechanical coverage.
"""
from __future__ import annotations

if not __debug__:
    raise RuntimeError('Independent acceptance refuses optimized Python; run without -O or PYTHONOPTIMIZE.')

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlsplit

REVIEW_STATUS='SOURCE_SCOPE_REVIEW'
NATIVE_RELATIONS={'NATIVE_DESIGN_PARENT','REGULATED_AS'}
ROLE_RELATIONS={'CLASS':'IS_A','MODEL':'DESIGN_TYPE_OF','MODEL_FAMILY':'DESIGN_TYPE_OF',
                'INSTANCE':'INSTANCE_OF','CONFIGURATION':'CONFIGURATION_TYPE_OF','BIOLOGICAL_VARIANT':'IS_A'}
RAW_FIELDS=('label','source','rank','description','data','domain','domains','layer')


class AssertionMultiplicityError(ValueError):
    def __init__(self,expected,observed):
        self.observed_count=observed
        super().__init__('Exact frozen assertion multiplicity differs: expected '+str(expected)+', found '+str(observed))


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value,str) else value).hexdigest()


def assertion_sha(row):
    # Stable raw source payload; SQL row IDs and subsequent dispositions do not
    # identify the source statement. This definition is declared locally.
    return sha(json.dumps({k:v for k,v in dict(row).items() if k not in {'id','status','reason'}},sort_keys=True))


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def connect(path):
    con=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    con.row_factory=sqlite3.Row;con.execute('PRAGMA query_only=ON')
    con.execute('PRAGMA temp_store=MEMORY');con.execute('PRAGMA cache_size=-262144')
    return con


def node(con,uid):
    row=con.execute('SELECT n.*,p.node_kind FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(uid,)).fetchone()
    if not row:return None
    result=dict(row)
    if not result['node_kind']:
        rank=(result.get('rank') or '').lower()
        result['node_kind']=next((role for role,ranks in {
            'MODEL':{'model','product_model','aircraft_model','vehicle_model'},'MODEL_FAMILY':{'model_family','series'},
            'CONFIGURATION':{'model_year','configuration','model_year_configuration'},'INSTANCE':{'instance'},
            'ATTRIBUTE':{'attribute','horticultural_color_class'},'ORGANIZATION':{'make','manufacturer'},
            'UNKNOWN':{'unknown','type_or_product_model'},'DATASET_CATEGORY':{'dataset_category'},
            'BIOLOGICAL_VARIANT':{'biological_variant'}}.items() if rank in ranks),'CLASS')
        if rank=='series' and (result.get('source') or '').lower()=='wfo':result['node_kind']='CLASS'
    return result


def locate(con,table,locator):
    keys={'edges':('child_uid','parent_uid','relation','source','layer'),
          'entity_relations':('subject_uid','object_uid','relation','source')}.get(table)
    if not keys or not locator.get('content_sha256') or any(not locator.get(k) for k in keys):
        raise ValueError('Incomplete or unsupported exact assertion locator')
    rows=con.execute('SELECT * FROM '+table+' WHERE '+' AND '.join(k+'=?' for k in keys),tuple(locator[k] for k in keys)).fetchall()
    matches=[row for row in rows if assertion_sha(row)==locator['content_sha256']]
    count=locator.get('source_assertion_multiplicity')
    if not isinstance(count,int) or isinstance(count,bool) or count<1 or len(matches)!=count:
        raise AssertionMultiplicityError(count,len(matches))
    return matches


def own_literal_scope(statement,label,genus,parent_definition,role=None):
    """Independent vetoes, including contradictions to the selected sense.

    The frozen reviewed rule supplies its literal genus. This independent
    checker verifies that it belongs to the subject clause, rather than using
    the adapter to repeat its positive decision.
    """
    if not genus:return ['MISSING_FROZEN_LITERAL_GENUS']
    errors=[];text=statement.strip()
    if text.lower().startswith('native source label:'):
        match=re.fullmatch(r'Native source label:\s*(.*?);\s*subject definition:\s*(.+)',text,re.I|re.S)
        if not match or match[1].strip().casefold()!=label.strip().casefold():return ['UNPARSED_LABEL_WRAPPER']
        text=match[2]
    text=re.sub(r'\([^()]*\)','',text)
    text=re.split(r'[.;]\s+(?=[A-Z])',text,maxsplit=1)[0]
    copula=re.search(r'\b(is|was|are|were)\s+',text,re.I)
    if copula:
        prefix=text[:copula.start()]
        words=lambda v:re.findall(r'[a-z0-9]+',v.casefold())
        wanted=words(label);actual=words(prefix)
        if actual[:1]==['the']:actual=actual[1:]
        if actual[:-1]==wanted and actual[-1:] in (['series'],['family'],['range'],['model']):actual=actual[:-1]
        if wanted!=actual:errors.append('COPULA_SUBJECT_IS_NOT_THE_SOURCE_REFERENT')
        text=text[copula.end():]
    # Before any dependent clause, the asserted genus must already be present.
    main=re.split(r'[,;]|\s+(?:whose|which|that|for|to|in|of|by|from|since|based|with|without|used|intended|designed|developed|manufactured|produced|built|made|released|introduced|marketed|capable|containing|consisting|featuring|belonging)\b',text,maxsplit=1,flags=re.I)[0]
    family_constructor=bool(re.match(r'^(?:an?|the)?\s*(family|series|line|range|type|kind|class)\s+of\b',text,re.I))
    # A mention of another object's family in a dependent clause cannot
    # establish that this subject itself is a family.
    if role=='MODEL_FAMILY' and not family_constructor and not re.search(r'\b(?:family|families|series|line|range)\b',main,re.I):
        errors.append('MODEL_FAMILY_GRAIN_ONLY_MENTIONED_OUTSIDE_THE_SUBJECT_HEAD')
    # A family/type of noun is a scope constructor, not a dependent purpose.
    if family_constructor:
        text=re.sub(r'^(?:an?|the)?\s*(?:family|series|line|range|type|kind|class)\s+of\s+','',text,flags=re.I)
        main=re.split(r'[,;]|\s+(?:whose|which|that|for|to|in|of|by|from|based|with|without|used|intended|designed|developed|manufactured|produced|built|made|released|introduced|marketed|capable|containing|consisting|featuring|belonging)\b',text,maxsplit=1,flags=re.I)[0]
    if not re.search(r'\b'+re.escape(genus)+r'\b',main,re.I):errors.append('GENUS_IS_ONLY_IN_A_DEPENDENT_CLAUSE_OR_NAME')
    if re.search(r'\b(?:not|never|neither|no)\b',main,re.I):errors.append('NEGATED_TYPE_ASSERTION')
    if re.search(r'\b(?:about|named|called|mentions?|depicting|displaying|book|game|museum|encyclopedia|simulator|simulation|software|architecture|language|protocol|standard|fictional|imaginary|toy|replica|fleet)\b',main,re.I):errors.append('NON_PHYSICAL_SUBJECT_OR_MENTION')
    # Preserve coordinate heads before inspecting them. Cutting at the first
    # comma would incorrectly turn a line of laptops, desktops and tablets
    # into a line consisting exclusively of laptops.
    head=re.split(r'[;]|\s+(?:whose|which|that|for|to|in|of|by|from|since|based|with|without|used|intended|designed|developed|manufactured|produced|built|made|released|introduced|marketed|capable|containing|consisting|featuring|belonging)\b',text,maxsplit=1,flags=re.I)[0]
    coordinates=[s.strip(' ,') for s in re.split(r',|\s+(?:and|or)\s+',head,flags=re.I) if s.strip(' ,')]
    genus_pattern=r'\b'+re.escape(genus)+r'(?:s|es)?\b'
    if re.search(r'\s+(?:and|or)\s+',head,re.I) and len(coordinates)>1 and re.search(genus_pattern,coordinates[0],re.I) and any(not re.search(genus_pattern,s,re.I) for s in coordinates[1:]):
        errors.append('COORDINATE_SUBJECT_SCOPE_EXTENDS_BEYOND_SELECTED_GENUS')
    if 'four wheels' in parent_definition.casefold():
        nonfour=r'(?:one|two|three|five|six|single|twin|1|2|3|5|6)'
        # A literal count in the head or an immediate body qualifier belongs
        # to this subject. Mentions of another competing car or a trailer do
        # not. Inspect qualifiers before cutting them for positive genus use.
        in_head=re.search(r'\b'+nonfour+r'[ -]wheel(?:s|ed|er)?\b',main,re.I)
        body=re.search(r'\b(?:with|having|on)\s+(?:(?:only|exactly|just)\s+|a total of\s+)?'+nonfour+r'\s+wheels\b|\bwhose\s+(?:wheel count\s+is\s+|wheels\s+(?:number|total)\s+)'+nonfour+r'\b',text,re.I)
        if in_head or body:errors.append('WHOLE_SUBJECT_CONTRADICTS_FOUR_WHEEL_PARENT_SCOPE')
    return errors


def ledger_matches(con,table,row,input_sha,*,ledger_index=None,required_prior_status=None):
    changes = (ledger_index.get((table,str(row['id'])),()) if ledger_index is not None else con.execute("SELECT * FROM usability_changes WHERE stage='source_semantic_contract' AND object_type=? AND object_id=?",(table,str(row['id']))))
    for change in changes:
        prior=json.loads(change['before_json']);proof=json.loads(change['evidence']);after=json.loads(change['after_json'])
        if required_prior_status is not None and (prior.get('status')!=required_prior_status or prior.get('reason')!=dict(row).get('reason')):
            continue
        if assertion_sha(prior)==assertion_sha(row) and proof.get('basis')=='UNREVIEWED_LEXICAL_PARENT_SCOPE' and proof.get('candidate_input_sha256')==input_sha and after.get('status')==REVIEW_STATUS:
            return True
    return False


def prior_disposition_errors(con,table,matches,prior_entry,input_sha,*,ledger_index=None):
    """Preserve prior terminal history, and require exactly the active withdrawals.

    Original duplicate assertions are identified by content and multiplicity;
    numeric row IDs are used only to join each actual candidate change ledger.
    A nonactive current status never substitutes for an exact frozen prior state.
    """
    if prior_entry is None:return ['MISSING_EXACT_FROZEN_PRIOR_STATUS_DISTRIBUTION']
    expected=Counter();active=Counter();errors=[]
    for item in prior_entry.get('prior_status_reason_distribution',()):
        status,reason,count=item.get('status'),item.get('reason'),item.get('count')
        if not isinstance(status,str) or not status or not isinstance(count,int) or isinstance(count,bool) or count<1:
            return ['INVALID_FROZEN_PRIOR_STATUS_DISTRIBUTION']
        expected[(REVIEW_STATUS if status=='ACTIVE' else status,reason)]+=count
        if status=='ACTIVE':active[reason]+=count
    if sum(expected.values())!=prior_entry.get('multiplicity') or len(matches)!=prior_entry.get('multiplicity'):
        errors.append('FROZEN_PRIOR_STATUS_MULTIPLICITY_DIFFERS')
    actual=Counter((row['status'],dict(row).get('reason')) for row in matches)
    if actual!=expected:errors.append('FROZEN_PRIOR_STATUS_REASON_DISTRIBUTION_DIFFERS')
    observed_active_withdrawals=Counter()
    for row in matches:
        if row['status']==REVIEW_STATUS and ledger_matches(con,table,row,input_sha,ledger_index=ledger_index,required_prior_status='ACTIVE'):
            observed_active_withdrawals[dict(row).get('reason')]+=1
    if observed_active_withdrawals!=active:
        errors.append('EXACT_ORIGINALLY_ACTIVE_SCOPE_CHANGE_LEDGER_DISTRIBUTION_DIFFERS')
        # Retain actionable existing error identifiers for actual missing ledgers.
        for row in matches:
            if row['status']==REVIEW_STATUS and active[dict(row).get('reason')] and not ledger_matches(con,table,row,input_sha,ledger_index=ledger_index,required_prior_status='ACTIVE'):
                errors.append('MISSING_EXACT_SOURCE_SCOPE_CHANGE_LEDGER:'+str(row['id']))
    return errors


def additional_primary_protection_errors(record,case):
    """Match exact independently frozen manufacturer whole-part evidence."""
    child,parent=record['child_source_record'],record['parent_source_record']
    raw=json.loads(child['data']);sr=raw.get('source_record',{});proof=case.get('proof',{});primary=proof.get('primary_datasheet',{});errors=[]
    if (case.get('uid')!=child['uid'] or case.get('parent')!=parent['uid'] or case.get('table')!=record['table']
        or case.get('locator')!=record['locator'] or case.get('disposition')!='PROTECTED_PRIMARY_SCOPE_SUPPORTED'
        or case.get('manual_proof_sha256')!=sha(json.dumps(proof,sort_keys=True))):errors.append('ADDITIONAL_PRIMARY_PROTECTION_CASE_OR_PROOF_MISMATCH')
    for key,value in [('source_record_uid',child['uid']),('native_record_sha256',sha(child['data'])),
                      ('reviewed_parent_uid',parent['uid']),('parent_native_record_sha256',sha(parent['data'])),
                      ('parent_definition_sha256',sha(parent['description'])),('source_catalog_snapshot_sha256',raw.get('source_sha256')),
                      ('native_part_number',sr.get('P1001')),('native_document_id',str(sr.get('P1000'))),
                      ('native_circuit_configuration',sr.get('T8270')),('native_catalog_row_url_preserved',sr.get('url'))]:
        if value is None or proof.get(key)!=value:errors.append('ADDITIONAL_PRIMARY_SCOPE_BINDING_MISMATCH:'+key)
    if (primary.get('document_product_header')!=sr.get('P1001') or primary.get('document_number')!=str(sr.get('P1000'))
        or primary.get('parts_table_circuit_configuration')!='Single' or sr.get('T8270')!='Single'
        or primary.get('publisher')!='Vishay Semiconductors'
        or str(primary.get('document_class_title','')).lstrip('_') not in ('Small Signal Fast Switching Diode','Small Signal Switching Diodes, High Voltage')):
        errors.append('OFFICIAL_DATASHEET_FULL_SUBJECT_CIRCUIT_OR_CLASS_SCOPE_DIFFERS')
    request=urlsplit(primary.get('request_uri',''));final=urlsplit(primary.get('final_uri',''))
    if (request.scheme!='https' or request.hostname not in ('www.vishay.com','vishay.com') or request.path!='/doc'
        or request.query!=str(sr.get('P1000')) or final.scheme!='https' or final.hostname not in ('www.vishay.com','vishay.com')
        or not final.path.startswith('/docs/'+str(sr.get('P1000'))+'/') or not final.path.endswith('.pdf')
        or primary.get('http_status')!=200):errors.append('OFFICIAL_DATASHEET_PUBLISHER_DOCUMENT_ID_OR_FETCH_NOT_BOUND')
    if any(not re.fullmatch(r'[0-9a-f]{64}',str(primary.get(key,''))) for key in ('pdf_sha256','extracted_text_sha256')):
        errors.append('OFFICIAL_DATASHEET_SNAPSHOT_HASH_MISSING')
    if not primary.get('retrieved_utc') or not primary.get('revision') or primary.get('primary_source_text_only') is not True:
        errors.append('OFFICIAL_DATASHEET_VERSION_OR_SOURCE_RECORD_MISSING')
    fields=primary.get('field_locators',{})
    for key in ('product_header','class_title','circuit_configuration'):
        field=fields.get(key,{})
        if field.get('page')!=1 or not isinstance(field.get('line'),int) or isinstance(field.get('line'),bool) or field['line']<1:
            errors.append('OFFICIAL_DATASHEET_FIELD_LOCATOR_MISSING:'+key)
    if fields.get('circuit_configuration',{}).get('section')!='PARTS TABLE' or fields.get('circuit_configuration',{}).get('column')!='CIRCUIT CONFIGURATION':
        errors.append('SINGLE_CIRCUIT_NOT_LOCATED_IN_WHOLE_PART_TABLE')
    if (proof.get('individual_semantic_review') is not True or proof.get('source_scope_entails_parent') is not True
        or proof.get('identity_assertion') is not False or proof.get('synthetic_adapter_description_used_as_scope_evidence') is not False
        or not proof.get('scope_observation')):errors.append('ADDITIONAL_PRIMARY_PROTECTION_MISSTATES_ITS_SCOPE')
    return errors


def protection_errors(record,independent_expectations=(),additional_cases=()):
    child,parent=record['child_source_record'],record['parent_source_record'];raw=json.loads(child['data']);sr=raw.get('source_record',{});proof=record.get('independent_native_scope_witness') or {};errors=[]
    if child['source']!='Vishay native parametric catalog':
        expected=next((r for r in independent_expectations if r.get('uid')==child['uid'] and r.get('parent')==parent['uid'] and r.get('disposition')=='PROTECTED_PRIMARY_SCOPE_SUPPORTED'),None)
        if (not expected or expected.get('manual_proof_sha256')!=sha(json.dumps(proof,sort_keys=True))
            or proof.get('individual_semantic_review') is not True or not proof.get('scope_observation') or not proof.get('primary_sources')):
            return ['PROTECTED_WHOLE_OBJECT_SCOPE_HAS_NO_INDEPENDENT_TYPE_EVIDENCE']
        for key,value in [('source_record_uid',child['uid']),('reviewed_parent_uid',parent['uid']),('native_record_sha256',sha(child['data'])),
                          ('parent_native_record_sha256',sha(parent['data'])),('parent_definition_sha256',sha(parent['description']))]:
            if proof.get(key)!=value:errors.append('INDEPENDENT_PRIMARY_SOURCE_SCOPE_WITNESS_MISMATCH:'+key)
        if proof.get('source_scope_entails_parent') is not True or proof.get('identity_assertion') is not False:errors.append('PRIMARY_SCOPE_PROTECTION_MISSTATES_DIRECTIONAL_TYPE_AS_IDENTITY')
        return errors
    additional=next((case for case in additional_cases if case.get('uid')==child['uid'] and case.get('parent')==parent['uid']),None)
    if sr.get('url')!='/diodes/switching/':
        if additional is None:errors.append('PROTECTED_NATIVE_CATALOG_ROUTE_REQUIRES_EXACT_PRIMARY_SCOPE_REVIEW')
        else:errors.extend(additional_primary_protection_errors(record,additional))
    if (raw.get('source_id')!='vishay-switching' or sr.get('T8270')!='Single'
        or not sr.get('P1001') or child['uid']!='vishay-part:'+str(sr['P1001']).lower()
        or raw.get('parent_uid')!=parent['uid'] or parent['uid']!='vishay-type:small-signal-switching-diode'
        or 'small-signal switching diode' not in parent['description'].casefold()):errors.append('PROTECTED_NATIVE_PART_AND_PARENT_WHOLE_BODY_SCOPE_MISMATCH')
    for key,expected in [('source_record_uid',child['uid']),('native_record_sha256',sha(child['data'])),('reviewed_parent_uid',parent['uid']),('parent_definition_sha256',sha(parent['description'])),('source_snapshot_sha256',raw.get('source_sha256'))]:
        if not expected or proof.get(key)!=expected:errors.append('PROTECTED_NATIVE_SCOPE_WITNESS_MISMATCH:'+key)
    if proof.get('source_scope_entails_parent') is not True:errors.append('PROTECTED_NATIVE_SCOPE_NOT_CONFIRMED')
    return errors


def commercial_membership_errors(con,repair,child,parent,inventory):
    """A documentary commercial line is neither type inclusion nor ancestry."""
    proof=repair['proof'];errors=[];raw=json.loads(child['data']);pr=json.loads(parent['data'])
    expected=inventory.get(child['uid']);evrow=con.execute('SELECT payload FROM evidence WHERE evidence_id=?',(raw.get('evidence_id'),)).fetchone()
    ev=json.loads(evrow[0]) if evrow else {};ids=raw.get('attributes',{}).get('native_model_identifiers')
    if repair['relation']!='SERIES_MEMBER_OF' or proof.get('actual_relation')!='SERIES_MEMBER_OF' or proof.get('kind')!='PUBLISHER_DECLARED_COMMERCIAL_LINE_MEMBERSHIP' or proof.get('identity_scope')!='SOURCE_NATIVE_COMMERCIAL_LINE':errors.append('COMMERCIAL_LINE_HAS_INCORRECT_ACTUAL_RELATION_OR_SCOPE')
    if child['source']!='Apple model-identification support' or parent['source']!=child['source'] or child['node_kind']!='MODEL' or parent['node_kind']!='MODEL_FAMILY':errors.append('COMMERCIAL_LINE_ENDPOINT_SOURCE_OR_ROLE_CHANGED')
    for field in ('is_design_lineage','is_class_inclusion','is_visual_distance'):
        if proof.get(field) is not False:errors.append('COMMERCIAL_MEMBERSHIP_FALSE_SEMANTIC_CLAIM:'+field)
    if not expected or expected.get('errors') or expected.get('semantic_scope')!='PUBLISHER_COMMERCIAL_PRODUCT_LINE_MEMBERSHIP_ONLY':errors.append('COMMERCIAL_MEMBERSHIP_NOT_IN_INDEPENDENT_COMPLETE_PRIMARY_SECTION_INVENTORY')
    else:
        comparisons={'parent':parent['uid'],'source_record_sha256':sha(child['data']),'parent_record_sha256':sha(parent['data']),
                     'source_uri':raw.get('source_uri'),'heading':raw.get('attributes',{}).get('catalog_heading'),
                     'source_snapshot_sha256':proof.get('source_snapshot_sha256'),'native_model_identifiers':sorted(ids or [])}
        if any(expected.get(k)!=v for k,v in comparisons.items()) or not set(ids or [])<=set(expected.get('independently_extracted_section_identifiers',[])):errors.append('COMMERCIAL_LINE_SOURCE_SCOPE_DIFFERS_FROM_INDEPENDENT_PRIMARY_SECTION')
    if not ids or ids!=ev.get('native_model_identifiers') or ids!=proof.get('native_model_identifiers') or raw.get('source_uri')!=pr.get('source_uri') or not str(raw.get('source_uri','')).startswith('https://support.apple.com/'):errors.append('COMMERCIAL_LINE_MODEL_SECTION_OR_DECLARED_PRODUCT_LINE_MISMATCH')
    for field,expected_value in [('parent_native_record_sha256',sha(parent['data'])),('source_snapshot_sha256',ev.get('source_sha256')),('source_section_sha256',ev.get('source_section_sha256'))]:
        if not expected_value or proof.get(field)!=expected_value:errors.append('COMMERCIAL_LINE_PRIMARY_WITNESS_MISMATCH:'+field)
    return errors


def audit(database,inputs,output):
    started=time.monotonic();database=Path(database);inputs=Path(inputs);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    source=inputs/'structure_source_contracts.json'
    if not source.exists():source=inputs/'structure_source_contracts.json.gz'
    raw=source.read_bytes();input_sha=sha(raw);payload_raw=gzip.decompress(raw) if source.suffix=='.gz' else raw
    payload_sha=sha(payload_raw);payload=json.loads(payload_raw)
    operations_path=inputs/'structure_source_contracts_operations.jsonl'
    operations=[json.loads(line) for line in operations_path.read_text().splitlines() if line]
    expectations_path=inputs/'source_contract_independent_expectations.json'
    expectations=json.loads(expectations_path.read_text()) if expectations_path.is_file() else {'cases':[]}
    manual_expectations={(r['uid'],r.get('parent')):r for r in expectations['cases'] if r.get('manual_proof_sha256')}
    membership_inventory={r['uid']:r for r in expectations.get('publisher_membership_inventory',{}).get('rows',[])}
    con=connect(database);failures=[];counts=Counter();records=[]
    metadata={r[0]:json.loads(r[1]) for r in con.execute('SELECT * FROM metadata')};revision=metadata.get('database_revision')
    # Scan the actual immutable change ledger once; preserve every duplicate
    # locator and validate its original content below. This is an independent
    # read-only acceleration, not a builder-produced acceptance cache.
    ledger_index=defaultdict(list)
    for change in con.execute("SELECT * FROM usability_changes WHERE stage='source_semantic_contract'"):
        ledger_index[(change['object_type'],change['object_id'])].append(change)
    print('ACTUAL SOURCE LEDGER INDEXED',sum(map(len,ledger_index.values())),flush=True)
    if expectations.get('candidate_payload_sha256') and expectations['candidate_payload_sha256']!=payload_sha:failures.append({'check':'INDEPENDENT_EXPECTATIONS_REFER_TO_DIFFERENT_SOURCE_PAYLOAD'})
    if any(metadata.get(k) is not True for k in ('unified_ready','usability_indexes_ready','browse_indexes_ready')):failures.append({'check':'DATABASE_NOT_FULLY_READY'})
    if not revision or metadata.get('browse_index_revision')!=revision:failures.append({'check':'CACHE_REVISION_MISMATCH'})
    freeze=metadata.get('structure_frozen_build_manifest',{});frozen_inputs=freeze.get('inputs',{})
    if freeze.get('schema')=='FINEATLAS_STRUCTURE_BUILD_V1':
        if metadata.get('browse_parent_revision')!=sha(json.dumps(freeze,sort_keys=True)):failures.append({'check':'BROWSE_SOURCE_REVISION_NOT_BOUND_TO_FROZEN_GRAPH'})
        if freeze.get('code',{}).get('scripts/audit_source_contract_candidate.py')!=sha(Path(__file__).read_bytes()):failures.append({'check':'AUDITOR_CODE_DIFFERS_FROM_FROZEN_CODE'})
    for path in (source,operations_path):
        if frozen_inputs.get(str(path.relative_to(inputs)))!=sha(path.read_bytes()):failures.append({'check':'INPUT_NOT_BOUND_TO_ACCEPTED_DATABASE_REVISION','file':path.name})
    prior_path=inputs/'source_contract_prior_status_distributions.json.gz'
    if not prior_path.is_file():prior_path=inputs/'source_contract_prior_status_distributions.json'
    prior_entries={};prior_counts=Counter()
    if not prior_path.is_file():failures.append({'check':'MISSING_INDEPENDENT_FROZEN_PRIOR_SOURCE_STATUS_INVENTORY'})
    else:
        prior_asset=prior_path.read_bytes()
        if frozen_inputs.get(prior_path.name)!=sha(prior_asset):failures.append({'check':'PRIOR_SOURCE_STATUSES_NOT_BOUND_TO_DATABASE_REVISION'})
        prior=json.loads(gzip.decompress(prior_asset) if prior_path.suffix=='.gz' else prior_asset)
        if (prior.get('schema')!='FINEATLAS_INDEPENDENT_PRIOR_SOURCE_DISPOSITIONS_V1'
            or prior.get('source_contract_payload_sha256')!=payload_sha
            or not re.fullmatch(r'[0-9a-f]{64}',str(prior.get('source_checkpoint_sha256','')))):
            failures.append({'check':'PRIOR_SOURCE_STATUSES_REFER_TO_DIFFERENT_OR_UNGROUNDED_SOURCE_CHECKPOINT'})
        for item in prior.get('entries',[]):
            key=(item.get('table'),item.get('locator',{}).get('content_sha256'))
            if key in prior_entries:failures.append({'check':'DUPLICATE_PRIOR_SOURCE_STATUS_LOCATOR','key':key})
            prior_entries[key]=item
            for part in item.get('prior_status_reason_distribution',[]):
                count=part.get('count')
                if not isinstance(count,int) or isinstance(count,bool) or count<1:
                    failures.append({'check':'INVALID_PRIOR_SOURCE_STATUS_COUNT','key':key});continue
                prior_counts[part.get('status')]+=count
        requested={(r['table'],r['locator']['content_sha256']) for r in payload['quarantines']}
        if (set(prior_entries)!=requested or prior.get('counts',{}).get('locators')!=len(prior_entries)
            or prior.get('counts',{}).get('original_source_rows')!=sum(prior_counts.values())
            or prior.get('counts',{}).get('prior_status_counts')!=dict(prior_counts)):
            failures.append({'check':'COMPLETE_PRIOR_SOURCE_STATUS_COHORT_OR_COUNTS_DIFFER'})
    additional_path=inputs/'source_contract_additional_protection_witnesses.json';additional_cases=[]
    if additional_path.is_file():
        if frozen_inputs.get(additional_path.name)!=sha(additional_path.read_bytes()):failures.append({'check':'ADDITIONAL_PRIMARY_PROTECTIONS_NOT_BOUND_TO_DATABASE_REVISION'})
        additional=json.loads(additional_path.read_text());additional_cases=additional.get('cases',[])
        if (additional.get('schema')!='FINEATLAS_INDEPENDENT_ADDITIONAL_PROTECTIONS_V1'
            or additional.get('source_contract_payload_sha256')!=payload_sha or additional.get('count')!=len(additional_cases)):
            failures.append({'check':'ADDITIONAL_PRIMARY_PROTECTIONS_REFER_TO_DIFFERENT_SOURCE_PAYLOAD'})
        original_protected={(r['table'],r['locator']['content_sha256']) for r in payload['protected']}
        extra_keys=[(r.get('table'),r.get('locator',{}).get('content_sha256')) for r in additional_cases]
        if len(set(extra_keys))!=len(extra_keys) or not set(extra_keys)<=original_protected:
            failures.append({'check':'ADDITIONAL_PRIMARY_PROTECTION_LOCATOR_COHORT_DIFFERS'})
    role_operations=payload.get('role_operations',[])
    if role_operations:
        roles_path=inputs/'structure_source_contracts_roles.jsonl'
        if not roles_path.is_file() or frozen_inputs.get(roles_path.name)!=sha(roles_path.read_bytes()):failures.append({'check':'REVIEWED_GRAIN_OPERATIONS_NOT_BOUND_TO_REVISION'})
        elif [json.loads(line) for line in roles_path.read_text().splitlines() if line]!=[{'op':'role',**r} for r in role_operations]:failures.append({'check':'REVIEWED_GRAIN_OPERATION_FILE_DIFFERS_FROM_PAYLOAD'})
        for op in role_operations:
            current=node(con,op['uid']);proof=op['proof'];errors=[]
            role_row=con.execute('SELECT canonical_role,status,evidence_id FROM normalization_roles WHERE uid=?',(op['uid'],)).fetchone()
            if not current or current['node_kind']!=op['role'] or not role_row or role_row['canonical_role']!=op['role'] or role_row['status']!='VERIFIED':errors.append('REVIEWED_GRAIN_NOT_INSTALLED_AS_VERIFIED_SOURCE_ROLE')
            if current and (proof.get('source_record_uid')!=op['uid'] or proof.get('native_record_sha256')!=sha(current['data'])):errors.append('REVIEWED_GRAIN_SOURCE_UID_OR_HASH_MISMATCH')
            if not proof.get('individual_semantic_review') or not proof.get('scope_observation') or not proof.get('source_statement'):errors.append('REVIEWED_GRAIN_LACKS_ACTUAL_SCOPE_DECISION')
            if role_row:
                evidence=con.execute('SELECT payload FROM evidence WHERE evidence_id=?',(role_row['evidence_id'],)).fetchone()
                if not evidence or json.loads(evidence[0])!=proof:errors.append('REVIEWED_GRAIN_EVIDENCE_DIFFERS_FROM_FROZEN_DECISION')
            if errors:failures.append({'check':'REVIEWED_WHOLE_SUBJECT_GRAIN','uid':op['uid'],'errors':errors})
    catalogue_checks=[];catalogue_groups={r['group_uid']:r for r in payload.get('source_catalog_groups',[])}
    catalogue_members=payload.get('source_catalog_members',[])
    for group_uid,group in catalogue_groups.items():
        stored=con.execute('SELECT * FROM source_groups WHERE group_uid=?',(group_uid,)).fetchone();proof=group['proof'];errors=[]
        if not stored or any(stored[k]!=group[k] for k in group if k!='proof') or json.loads(stored['proof'])!=proof:errors.append('FROZEN_NATIVE_DIRECTORY_NOT_PRESENT_EXACTLY')
        if proof.get('kind')!='SOURCE_NATIVE_CATALOG_DIRECTORY' or proof.get('is_class_inclusion') is not False or proof.get('is_design_lineage') is not False:errors.append('NATIVE_DIRECTORY_MISREPRESENTED_AS_TYPE_OR_DESIGN_LINEAGE')
        if group['source_version']!='sha256:'+proof.get('source_snapshot_sha256','') or group['source_group_id']!=proof.get('source_id'):errors.append('NATIVE_DIRECTORY_SOURCE_VERSION_OR_ID_MISMATCH')
        if con.execute('SELECT 1 FROM nodes WHERE uid=?',(group_uid,)).fetchone():errors.append('NATIVE_DIRECTORY_POLLUTES_ENTITY_IDENTITY_OR_CLASSIFICATION_GRAPH')
        if errors:failures.append({'check':'NATIVE_CATALOG_DIRECTORY','group_uid':group_uid,'errors':errors})
    listed=set()
    for member in catalogue_members:
        uid=member['member_uid'];listed.add(uid);group=catalogue_groups.get(member['group_uid']);current=node(con,uid);proof=member['proof'];errors=[]
        stored=con.execute('SELECT * FROM source_group_members WHERE group_uid=? AND member_uid=?',(member['group_uid'],uid)).fetchone()
        if not stored or any(stored[k]!=member[k] for k in member if k!='proof') or json.loads(stored['proof'])!=proof:errors.append('FROZEN_NATIVE_CATALOG_ENTRY_NOT_PRESENT_EXACTLY')
        if member['relation']!='CATALOG_ENTRY' or member['status']!='SOURCE_DECLARED':errors.append('NATIVE_DIRECTORY_RELATION_OR_DOCUMENTARY_STATUS_INCORRECT')
        for field in ('is_class_inclusion','is_design_lineage','world_physical_type_verified_by_directory','world_identity_assertion'):
            if proof.get(field) is not False:errors.append('NATIVE_CATALOGUE_FALSE_TYPE_OR_WORLD_SCOPE_ASSERTION:'+field)
        if not group or not current:errors.append('DANGLING_NATIVE_DIRECTORY_ENTRY')
        else:
            raw_node=json.loads(current['data']);source_record=raw_node.get('source_record',{});field=proof.get('native_identifier_field')
            canon=group['namespace']=='canon-camera-museum-catalogue'
            intel=group['namespace']=='intel-ark-native-catalogue'
            expected_pairs=[('source_record_uid',uid),('native_record_sha256',sha(current['data'])),('source_uri',raw_node.get('source_uri'))]
            if canon:
                attrs=raw_node.get('attributes',{})
                evrow=con.execute('SELECT payload FROM evidence WHERE evidence_id=?',(raw_node.get('evidence_id'),)).fetchone()
                ev=json.loads(evrow[0]) if evrow else {}
                expected_pairs.extend([('source_snapshot_sha256',ev.get('source_sha256')),('catalog_category',attrs.get('catalog_category')),('native_catalog_id',attrs.get('native_catalog_id'))])
                if current['source']!='Canon Camera Museum' or uid!='canon:'+str(attrs.get('native_catalog_id')) or any(ev.get(k)!=attrs.get(k) for k in ('catalog_category','native_catalog_id')):errors.append('CANON_NATIVE_ID_OR_DECLARED_CATEGORY_DOES_NOT_MATCH_THE_SOURCE_EVIDENCE')
                if group['source_group_id']!=attrs.get('catalog_category') or group['proof']['source_snapshot_sha256']!=ev.get('source_sha256') or group['source_uri']!=ev.get('source_uri'):errors.append('CANON_ENTRY_ASSIGNED_TO_DIFFERENT_SOURCE_CATEGORY_OR_SNAPSHOT')
                if member['source_member_id']!=attrs.get('native_catalog_id'):errors.append('CANON_NATIVE_CATALOGUE_ID_CHANGED')
            elif intel:
                expected_pairs=[('source_record_uid',uid),('native_record_sha256',sha(current['data'])),('source_snapshot_sha256',raw_node.get('source_sha256')),('intel_ark_id',source_record.get('intel_ark_id')),('native_collection_uri',raw_node.get('source_uri')),('source_uri',source_record.get('specifications_uri'))]
                if current['source'] not in ('intel-core-ark','intel-ultra-ark') or uid!='intel-ark:'+str(source_record.get('intel_ark_id')) or member['source_member_id']!=source_record.get('intel_ark_id'):errors.append('INTEL_NATIVE_SKU_IDENTIFIER_CHANGED')
                if group['source_group_id']!=current['source'] or group['source_uri']!=raw_node.get('source_uri') or group['proof']['source_snapshot_sha256']!=raw_node.get('source_sha256'):errors.append('INTEL_SKU_ASSIGNED_TO_DIFFERENT_SOURCE_COLLECTION_OR_SNAPSHOT')
            else:
                expected_pairs.extend([('source_id',raw_node.get('source_id')),('source_snapshot_sha256',raw_node.get('source_sha256'))])
                if field not in ('gpu_model_designation','P1009','P1001') or member['source_member_id']!=str(source_record.get(field)) or proof.get('native_identifier')!=source_record.get(field):errors.append('NATIVE_CATALOGUE_IDENTIFIER_OR_SCOPE_FIELD_CHANGED')
                if group['source_group_id']!=raw_node.get('source_id') or group['proof']['source_snapshot_sha256']!=raw_node.get('source_sha256'):errors.append('ENTRY_ASSIGNED_TO_DIFFERENT_NATIVE_SOURCE_DIRECTORY')
                if proof.get('native_compute_capability')!=source_record.get('compute_capability') or proof.get('native_topology')!=source_record.get('T8270'):errors.append('NATIVE_CATALOGUE_ATTRIBUTE_OR_CONFIGURATION_LOST')
                if current['source']=='Vishay native parametric catalog' and proof.get('native_family_range')!=source_record.get('P1001'):errors.append('VISHAY_PART_ID_AND_NATIVE_FAMILY_RANGE_WERE_COLLAPSED')
            for key,value in expected_pairs:
                if not value or proof.get(key)!=value:errors.append('NATIVE_CATALOGUE_RECORD_WITNESS_MISMATCH:'+key)
        catalogue_checks.append({'uid':uid,'group_uid':member['group_uid'],'errors':errors})
        if errors:failures.append({'check':'NATIVE_CATALOG_ENTRY',**catalogue_checks[-1]})
    # The independently scanned retained source cohort must equal the directory
    # inventory; a large published list cannot hide omitted native records.
    retained=set()
    for source_name,prefix in [('NVIDIA native CUDA GPU model table','nvidia-cuda-gpu:'),('Vishay native parametric catalog','vishay-part:'),('Canon Camera Museum','canon:'),('intel-core-ark','intel-ark:'),('intel-ultra-ark','intel-ark:')]:
        retained.update(r[0] for r in con.execute('SELECT uid FROM nodes WHERE source=? AND substr(uid,1,?)=?',(source_name,len(prefix),prefix)))
    if retained!=listed:failures.append({'check':'FULL_NATIVE_SOURCE_DIRECTORY_INVENTORY_MISMATCH','missing_uids':sorted(retained-listed),'unexpected_uids':sorted(listed-retained)})
    originals={};native_nodes={};anchors={r['uid']:r for r in payload['reviewed_genus_anchors']}
    native_review_hashes={(r['table'],r['locator']['content_sha256']) for r in payload['quarantines'] if r['original_source_assertion']['relation'] in NATIVE_RELATIONS}
    for disposition,cohort in [('QUARANTINED',payload['quarantines']),('PROTECTED',payload['protected'])]:
        seen=set()
        for number,record in enumerate(cohort,1):
            table=record['table'];locator=record['locator'];key=(table,json.dumps(locator,sort_keys=True))
            originals[(table,locator['content_sha256'])]=record;native_nodes[record['child_source_record']['uid']]=record['child_source_record']
            errors=[]
            if assertion_sha(record['original_source_assertion'])!=locator['content_sha256']:errors.append('FROZEN_ORIGINAL_ASSERTION_DIFFERS_FROM_ITS_LOCATOR')
            for field,hash_key in [('child_source_record','child_raw_sha256'),('parent_source_record','parent_raw_sha256')]:
                frozen=record[field];current=node(con,frozen['uid'])
                if not current or sha(frozen['data'])!=record[hash_key] or any(current.get(k)!=frozen.get(k) for k in RAW_FIELDS):errors.append('ORIGINAL_SOURCE_RECORD_SCOPE_OR_PAYLOAD_DRIFT:'+frozen['uid'])
            if disposition=='PROTECTED':
                errors.extend(protection_errors(record,expectations['cases'],additional_cases))
                current_child=node(con,record['child_source_record']['uid']);current_parent=node(con,record['parent_source_record']['uid'])
                if not current_child or not current_parent or current_parent['node_kind']!='CLASS' or ROLE_RELATIONS.get(current_child['node_kind'])!=record['original_source_assertion']['relation']:errors.append('PROTECTED_ASSERTION_RELATION_DOES_NOT_MATCH_CORRECTED_SUBJECT_GRAIN')
            if key not in seen:
                seen.add(key)
                try:matches=locate(con,table,locator)
                except ValueError as exc:errors.append(str(exc));matches=[]
                if disposition=='QUARANTINED':
                    prior_entry=prior_entries.get((table,locator['content_sha256']))
                    if prior_entry is not None and (prior_entry.get('locator')!=locator or prior_entry.get('multiplicity')!=locator['source_assertion_multiplicity']):
                        errors.append('FROZEN_PRIOR_ASSERTION_LOCATOR_DIFFERS_FROM_QUARANTINE')
                    errors.extend(prior_disposition_errors(con,table,matches,prior_entry,input_sha,ledger_index=ledger_index))
                for row in matches:
                    counts[disposition+'_source_rows']+=1
                    if disposition=='QUARANTINED':
                        if row['status']==REVIEW_STATUS:counts['source_scope_review_current_rows']+=1
                        else:counts['existing_terminal_source_rows_preserved']+=1
                    elif row['status']!=record['original_source_assertion']['status']:errors.append('PROTECTED_NATIVE_ASSERTION_STATUS_CHANGED:'+str(row['id']))
            if errors:failures.append({'check':'EXACT_SOURCE_DISPOSITION','disposition':disposition,'locator':locator,'errors':errors})
            if number%10000==0:print(disposition,number,flush=True)
    if operations!=[{'op':'link',**r} for r in payload['repairs']]:failures.append({'check':'FROZEN_OPERATIONS_DIFFER_FROM_REPAIRS'})
    counts['frozen_originally_active_source_rows']=prior_counts['ACTIVE']
    counts['frozen_preexisting_terminal_source_rows']=sum(n for status,n in prior_counts.items() if status!='ACTIVE')
    withheld_count=payload.get('summary',{}).get('alternate_claim_type_routes_withheld_for_family_scope',0)
    withheld_checks=[]
    if withheld_count:
        withheld_path=inputs/'withheld_family_alternate_candidates.json'
        if not withheld_path.is_file():failures.append({'check':'MISSING_FROZEN_UNCONFIRMED_FAMILY_ALTERNATE_ROUTES'})
        else:
            withheld_raw=withheld_path.read_bytes();withheld=json.loads(withheld_raw)
            if frozen_inputs.get(withheld_path.name)!=sha(withheld_raw) or withheld.get('final_manifest_sha256')!=payload_sha:failures.append({'check':'WITHHELD_ENDPOINT_SCOPE_CASES_NOT_BOUND_TO_CANDIDATE_REVISION'})
            if withheld.get('count')!=withheld_count or len(withheld.get('items',[]))!=withheld_count:failures.append({'check':'WITHHELD_ENDPOINT_SCOPE_INVENTORY_COUNT_DIFFERS'})
            grain={r['uid']:r for r in payload.get('grain_dispositions',[])}
            for item in withheld.get('items',[]):
                uid=item['uid'];old=item['candidate_type_claim_withheld'];current=node(con,uid);errors=[]
                if item.get('frozen_role_scope_disposition')!=grain.get(uid) or item.get('status')!='WITHHELD_BEFORE_FINAL_OPERATIONS' or item.get('world_family_scope_confirmation') is not False:errors.append('WITHHELD_ENDPOINT_SCOPE_DECISION_DIFFERS_FROM_FROZEN_SOURCE_REVIEW')
                if not current or current['node_kind']!=item['canonical_role'] or sha(current['data'])!=old['proof']['native_record_sha256']:errors.append('WITHHELD_ENDPOINT_ROLE_OR_SOURCE_PAYLOAD_CHANGED')
                if any(r['uid']==uid for r in payload['repairs']):errors.append('UNCONFIRMED_ENDPOINT_WAS_REINTRODUCED_BY_ANOTHER_FROZEN_REPAIR')
                if con.execute("SELECT 1 FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=? AND status='ACTIVE'",(uid,item['parent'],item['relation'],old['source'])).fetchone():errors.append('UNCONFIRMED_ENDPOINT_BYPASSED_VIA_ALTERNATE_TYPE_ROUTE')
                withheld_checks.append({'uid':uid,'parent':item['parent'],'canonical_role':item['canonical_role'],'errors':errors})
                if errors:failures.append({'check':'UNCONFIRMED_FAMILY_ALTERNATE_ROUTE',**withheld_checks[-1]})
    memberships=[r for r in payload['repairs'] if r['relation']=='SERIES_MEMBER_OF']
    if memberships!=payload.get('source_membership_repairs',[]):failures.append({'check':'COMMERCIAL_MEMBERSHIP_COHORT_NOT_SEPARATED_EXACTLY'})
    if {r['uid'] for r in memberships}!=set(membership_inventory):failures.append({'check':'COMMERCIAL_LINE_FULL_PRIMARY_SECTION_INVENTORY_MISMATCH'})
    groups=defaultdict(list)
    for repair in payload['repairs']:
        uid=repair['uid'];proof=repair['proof'];child=node(con,uid);parent=node(con,repair['parent']);frozen=native_nodes.get(uid);errors=[]
        if not child or not parent or not frozen:errors.append('MISSING_REPLACEMENT_SOURCE_ENDPOINT')
        else:
            commercial=repair['relation']=='SERIES_MEMBER_OF'
            if child['visibility']!='ACTIVE' or (not commercial and (parent['node_kind']!='CLASS' or ROLE_RELATIONS.get(child['node_kind'])!=repair['relation'])):errors.append('REPLACEMENT_ENDPOINT_ROLE_SCOPE_MISMATCH')
            if proof.get('source_record_uid')!=uid or proof.get('native_record_sha256')!=sha(child['data']):errors.append('REPLACEMENT_NATIVE_SUBJECT_HASH_OR_UID_MISMATCH')
            manual=proof.get('human_individual_review') is True
            anchor=anchors.get(parent['uid'])
            if proof.get('reviewed_parent_uid')!=parent['uid'] or (not commercial and proof.get('parent_definition')!=parent['description']) or proof.get('parent_definition_sha256')!=sha(parent['description']):errors.append('REPLACEMENT_PARENT_SENSE_OR_HASH_MISMATCH')
            if commercial:
                errors.extend(commercial_membership_errors(con,repair,child,parent,membership_inventory))
                counts['source_native_commercial_memberships_checked']+=1
            elif manual:
                expected=manual_expectations.get((uid,parent['uid']))
                if (not expected or expected.get('manual_proof_sha256')!=sha(json.dumps(proof,sort_keys=True))
                    or proof.get('parent_native_record_sha256')!=sha(parent['data']) or proof.get('individual_semantic_review') is not True):errors.append('INDIVIDUAL_SCOPE_REPAIR_NOT_IN_INDEPENDENT_FROZEN_MANUAL_REVIEW')
                if not any(op['uid']==uid and op['role']==child['node_kind'] and op['proof'].get('source_statement')==proof.get('source_statement') for op in role_operations):errors.append('INDIVIDUAL_SCOPE_REPAIR_LACKS_THE_MATCHING_SOURCE_GRAIN_REVIEW')
            else:
                if not anchor or anchor['raw_sha256']!=sha(parent['data']):errors.append('AUTOMATED_REPLACEMENT_NOT_USING_THE_FROZEN_NATIVE_GENUS_SENSE')
                if proof.get('individual_semantic_review') is not False or proof.get('human_individual_review') is not False or proof.get('reviewed_rule_verified') is not True:errors.append('AUTOMATED_RULE_MISREPRESENTED_AS_INDIVIDUAL_SEMANTIC_CERTIFICATION')
            if proof.get('source_scope_entails_parent') is not True:errors.append('REPLACEMENT_DIRECTIONAL_TYPE_SCOPE_NOT_AFFIRMED')
            witnesses=[originals.get((table,l['content_sha256'])) for l in proof.get('original_claim_locators',[]) for table in ('edges','entity_relations') if (table,l['content_sha256']) in originals]
            if not manual and (not witnesses or any(w['child_source_record']['uid']!=uid for w in witnesses) or (not commercial and not any(w['source_statement']==proof.get('source_statement') for w in witnesses))):errors.append('REPLACEMENT_STATEMENT_NOT_IN_THE_FROZEN_SUBJECT_WITNESS')
            if not manual and not commercial:errors.extend(own_literal_scope(proof.get('source_statement',''),child['label'],proof.get('matched_explicit_genus',''),parent['description'],child['node_kind']))
            table='edges' if repair['relation']=='IS_A' else 'entity_relations';ck,pk=('child_uid','parent_uid') if table=='edges' else ('subject_uid','object_uid')
            matches=con.execute('SELECT * FROM '+table+' WHERE '+ck+'=? AND '+pk+'=? AND relation=? AND source=? AND status=\'ACTIVE\'',(uid,repair['parent'],repair['relation'],repair['source'])).fetchall()
            if not any(json.loads(row['data']).get('admission_basis')==proof for row in matches):errors.append('FROZEN_REPLACEMENT_RELATION_OR_PROOF_NOT_IN_ACTIVE_DATABASE')
        record={'uid':uid,'parent':repair['parent'],'relation':repair['relation'],'role':child['node_kind'] if child else None,'source_statement':proof.get('source_statement'),'errors':errors}
        records.append(record);groups[(record['role'],record['parent'])].append(record);counts['replacement_claims_checked']+=1
        if errors:failures.append({'check':'REPLACEMENT_SCOPE',**record})
    expected_checks=[]
    if not expectations_path.exists():failures.append({'check':'MISSING_INDEPENDENT_FROZEN_SEMANTIC_EXPECTATIONS'})
    else:
        if frozen_inputs.get(expectations_path.name)!=sha(expectations_path.read_bytes()):failures.append({'check':'SEMANTIC_EXPECTATIONS_NOT_REVISION_BOUND'})
        cases=expectations['cases']
        fixed_uids={r['uid'] for r in payload.get('confirmed_counterexamples',[])}
        reviewed_fixed={r['uid'] for r in cases if r['origin']=='original_32_counterexample'}
        if not fixed_uids<=reviewed_fixed:failures.append({'check':'ORIGINAL_COUNTEREXAMPLES_NOT_ALL_COVERED','missing_uids':sorted(fixed_uids-reviewed_fixed)})
        final_sample_keys={(r['uid'],r['parent']) for rows in groups.values() for r in sorted(rows,key=lambda r:sha('independent-source-contract-20261009:'+r['uid']))[:5]}
        reviewed_sample_keys={(r['uid'],r.get('parent')) for r in cases if r['origin']=='final_stratified_scope'}
        if fixed_uids and not final_sample_keys<=reviewed_sample_keys:failures.append({'check':'FINAL_STRATIFIED_SAMPLE_NOT_IN_FROZEN_REVIEW','missing':sorted(final_sample_keys-reviewed_sample_keys)})
        for expected in cases:
            matched=[r for r in records if r['uid']==expected['uid'] and (not expected.get('parent') or r['parent']==expected['parent'])]
            current=node(con,expected['uid']);errors=[]
            if expected['disposition']=='REPLACEMENT_PROHIBITED' and matched:errors.append('SCOPE_REVIEW_SUBJECT_WAS_RECONNECTED_WITHOUT_INDEPENDENT_REVIEW')
            if expected['disposition']=='PHYSICAL_PARENT_DIRECTION_SUPPORTED' and expected.get('required',False) and not matched:errors.append('REVIEWED_LITERAL_REPLACEMENT_MISSING')
            if expected['disposition']=='COMMERCIAL_SOURCE_MEMBERSHIP_SUPPORTED' and expected.get('required',False) and not any(r['relation']=='SERIES_MEMBER_OF' for r in matched):errors.append('SOURCE_NATIVE_COMMERCIAL_MEMBERSHIP_MISSING')
            if expected.get('expected_source_statement_sha256') and any(sha(r.get('source_statement') or '')!=expected['expected_source_statement_sha256'] for r in matched):errors.append('FROZEN_INDEPENDENT_SUBJECT_STATEMENT_CHANGED')
            if expected['disposition'] in ('ORIGINAL_NATIVE_SCOPE_REVIEW_REQUIRED','ORIGINAL_NATIVE_DECLARATION_RETAINED'):
                try:original_rows=locate(con,expected['table'],expected['locator'])
                except ValueError as exc:errors.append(str(exc));original_rows=[]
                wanted_status=REVIEW_STATUS if expected['disposition']=='ORIGINAL_NATIVE_SCOPE_REVIEW_REQUIRED' else 'ACTIVE'
                if any(r['status']!=wanted_status for r in original_rows):errors.append('FROZEN_INDEPENDENT_NATIVE_PARENT_SCOPE_DISPOSITION_CHANGED')
            if expected.get('expected_role') and (not current or current['node_kind']!=expected['expected_role']):errors.append('INDEPENDENT_ROLE_GRAIN_EXPECTATION_DIFFERS')
            expected_checks.append({'uid':expected['uid'],'origin':expected['origin'],'expected':expected['disposition'],'matching_new_claims':len(matched),'errors':errors})
            if errors:failures.append({'check':'FROZEN_SEMANTIC_CASE',**expected_checks[-1]})
    protected_by_key={(r['table'],r['locator']['content_sha256']):r for r in payload['protected']}
    for expected in additional_cases:
        record=protected_by_key.get((expected.get('table'),expected.get('locator',{}).get('content_sha256')));errors=[]
        if record is None:errors.append('ADDITIONAL_PROTECTION_NOT_IN_EXACT_ORIGINAL_PROTECTED_COHORT')
        else:
            errors.extend(additional_primary_protection_errors(record,expected))
            current=node(con,expected['uid'])
            if not current or current['node_kind']!=expected.get('expected_role'):errors.append('ADDITIONAL_PROTECTION_SOURCE_ROLE_SCOPE_CHANGED')
            try:matches=locate(con,record['table'],record['locator'])
            except ValueError as exc:errors.append(str(exc));matches=[]
            if not matches or any(row['status']!='ACTIVE' for row in matches):errors.append('ADDITIONAL_PRIMARY_PROTECTION_NOT_PRESERVED_ACTIVE')
        expected_checks.append({'uid':expected.get('uid'),'origin':expected.get('origin'),'expected':expected.get('disposition'),
                                'additional_primary_scope_case':True,'errors':errors})
        if errors:failures.append({'check':'FROZEN_ADDITIONAL_PRIMARY_SCOPE_CASE',**expected_checks[-1]})
    native=[];native_path=inputs/'source_contract_native_preservation.json'
    if not native_path.is_file():native_path=inputs/'source_contract_native_preservation.json.gz'
    if not native_path.is_file():failures.append({'check':'MISSING_INDEPENDENT_FROZEN_NATIVE_PRESERVATION_INVENTORY'})
    else:
        if frozen_inputs.get(native_path.name)!=sha(native_path.read_bytes()):failures.append({'check':'NATIVE_SOURCE_PRESERVATION_INVENTORY_NOT_REVISION_BOUND'})
        inventory_raw=native_path.read_bytes()
        inventory=json.loads(gzip.decompress(inventory_raw) if native_path.suffix=='.gz' else inventory_raw)
        if sum(r['locator']['source_assertion_multiplicity'] for r in inventory['claims'])!=inventory['original_source_rows']:failures.append({'check':'NATIVE_PRESERVATION_COHORT_COUNT_INCONSISTENT'})
        for claim in inventory['claims']:
            locator=claim['locator'];errors=[]
            if locator['relation'] not in NATIVE_RELATIONS:errors.append('FROZEN_NATIVE_ASSERTION_SCOPE_MISMATCH')
            if claim.get('original_source_assertion'):
                if assertion_sha(claim['original_source_assertion'])!=locator['content_sha256']:errors.append('FROZEN_NATIVE_ASSERTION_CONTENT_MISMATCH')
            elif inventory.get('content_provenance')!='INDEPENDENT_RAW_SQL_COMPLETE_IMMUTABLE_SOURCE_ASSERTION_DIGESTS':errors.append('NATIVE_CONTENT_DIGEST_LACKS_INDEPENDENT_SOURCE_CENSUS_PROVENANCE')
            observed=None
            try:matches=locate(con,claim['table'],locator)
            except ValueError as exc:errors.append(str(exc));matches=[];observed=getattr(exc,'observed_count',None)
            reviewed=(claim['table'],locator['content_sha256']) in native_review_hashes
            if reviewed:
                prior_entry=prior_entries.get((claim['table'],locator['content_sha256']))
                if prior_disposition_errors(con,claim['table'],matches,prior_entry,input_sha,ledger_index=ledger_index):
                    errors.append('NATIVE_SCOPE_WITHDRAWAL_LACKS_ITS_EXACT_FROZEN_PRIOR_STATE_AND_CHANGE_LEDGER')
            elif any(row['status']!='ACTIVE' for row in matches):errors.append('ORIGINAL_NATIVE_ASSERTION_RETIRED_WITHOUT_FROZEN_SCOPE_REVIEW')
            native.append({k:locator[k] for k in ('subject_uid','object_uid','relation','source','content_sha256')}|
                          {'original_multiplicity':locator['source_assertion_multiplicity'],'candidate_multiplicity':len(matches) if observed is None else observed,
                           'native_source_contents_preserved':not errors,'actual_scope_disposition':'EXACT_SOURCE_SCOPE_REVIEW' if reviewed else 'ACTIVE_NATIVE_DECLARATION',
                           'active_native_semantics_certified_by_raw_preservation':False,'preserved':not errors})
            if errors:failures.append({'check':'ORIGINAL_NATIVE_OR_REGULATORY_ASSERTION_CHANGED',**native[-1],'errors':errors})
    # New documentary design/regulatory assertions are checked against the
    # exact frozen operations, including their original source proof.
    for path in sorted(inputs.glob('*operations.jsonl')):
        if frozen_inputs.get(path.name)!=sha(path.read_bytes()):
            failures.append({'check':'NATIVE_OPERATION_INPUT_NOT_BOUND_TO_DATABASE_REVISION','file':path.name})
        for line in path.read_text().splitlines():
            op=json.loads(line)
            if op.get('op')!='link' or op.get('relation') not in NATIVE_RELATIONS:continue
            matches=con.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=? AND status=\'ACTIVE\'',(op['uid'],op['parent'],op['relation'],op['source'])).fetchall()
            ok=any(json.loads(row['data']).get('admission_basis')==op['proof'] for row in matches)
            native.append({'subject_uid':op['uid'],'object_uid':op['parent'],'relation':op['relation'],'frozen_operation_file':path.name,'preserved':ok})
            if not ok:failures.append({'check':'FROZEN_NATIVE_OR_REGULATORY_OPERATION_NOT_RETAINED',**native[-1]})
    samples=[r for key,rows in sorted(groups.items()) for r in sorted(rows,key=lambda r:sha('independent-source-contract-20261009:'+r['uid']))[:5]]
    save(output/'replacement_full_machine_checks.json',records);save(output/'fixed_final_stratified_samples.json',samples)
    save(output/'frozen_semantic_expectations.json',expected_checks);save(output/'native_and_regulatory_preservation.json',native)
    save(output/'native_catalogue_full_inventory.json',catalogue_checks)
    save(output/'withheld_family_alternate_routes.json',withheld_checks)
    summary={'pass':not failures,'database':str(database),'database_revision':revision,'input_sha256':input_sha,'payload_sha256':payload_sha,
             'counts':dict(counts),'semantic_sample_groups':len(groups),'semantic_samples':len(samples),'frozen_expected_cases':len(expected_checks),
             'original_frozen_expected_cases':len(expectations.get('cases',[])),'additional_primary_scope_cases':len(additional_cases),
             'native_preservation_cases':len(native),'native_preservation_pass':all(r['preserved'] for r in native),
             'native_catalogue_groups':len(catalogue_groups),'native_catalogue_members':len(catalogue_checks),'native_catalogue_full_cohort':len(retained),
             'withheld_endpoint_scope_alternate_routes_checked':len(withheld_checks),
             'failure_count':len(failures),'failures':failures,'all_semantic_facts_certified':False,'seconds':time.monotonic()-started}
    save(output/'summary.json',summary);con.close();print(json.dumps({k:v for k,v in summary.items() if k!='failures'},ensure_ascii=False),flush=True)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('database','inputs','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if not audit(args.database,args.inputs,args.output)['pass']:raise SystemExit(1)


if __name__=='__main__':main()
