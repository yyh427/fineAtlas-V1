"""Preserve original SOURCE7 checks with explicitly audited SOURCE8/9 timepoints."""
from __future__ import annotations
import json
from pathlib import Path
import sqlite3

from _download import digest
from structure_eighth_owned_scope_temporal_contract import (
    EighthOwnedTemporalContract,
    require_temporal_eighth_owned_scope_receipt,
)
from structure_ninth_complete_type_temporal_contract import require_complete_type_receipt
from structure_nominal_design_scope_delivery_guard import require_nominal_scope_receipt

ROOT=Path(__file__).resolve().parents[1]
SCHEMA='FINEATLAS_EXACT_NINTH_CURRENT_OWNED_SCOPE_AUDIT_V1'


def load_nominal_operations(database, inputs, report, revision, code_root):
    inputs,report=Path(inputs),Path(report)
    actual=require_nominal_scope_receipt(report,database,inputs,revision,code_root)
    manifest_path=inputs/'structure_nominal_design_scope_repairs.json'
    manifest=json.loads(manifest_path.read_bytes());path=inputs/manifest['operations_file']
    operations=[json.loads(line)for line in path.read_text().splitlines()if line]
    if digest(path)!=manifest['operations_sha256']or len(operations)!=manifest['operation_count']:
        raise ValueError('Exact complete current nominal operation inventory required')
    return operations,{'path':str(report.resolve()),'sha256':digest(report),
        'manifest_sha256':digest(manifest_path),'operations_sha256':actual['operations_sha256']}


def exact_nominal_after(c, operations, table, before):
    """Only one frozen full-row transition may replace an earlier expectation."""
    if before is None:return None,None
    choices=[]
    for op in operations:
        if table=='edges'and op['op']=='review_class_edge'and op['before_assertion']['id']==before['id']:
            if op['before_assertion']!=before or op.get('after_status','SOURCE_SCOPE_REVIEW')!='SOURCE_SCOPE_REVIEW':
                raise ValueError('Nominal class withdrawal differs from the exact old assertion')
            after={**before,'status':'SOURCE_SCOPE_REVIEW'}
            kind,identifier='class_scope_review',str(before['id'])
            historical_before,historical_after=before,{'status':'SOURCE_SCOPE_REVIEW'}
        elif table in {'node_profiles','normalization_roles'}and op['op']=='correct_role'and op['uid']==before['uid']:
            key='profile'if table=='node_profiles'else'normalization_role'
            if op['before_'+key]!=before:raise ValueError('Nominal role migration differs from its full earlier role row')
            after=op['after_'+key];kind,identifier='role_source_adjudication',op['uid']
            historical_before={'profile':op['before_profile'],'normalization_role':op['before_normalization_role']}
            historical_after={'profile':op['after_profile'],'normalization_role':op['after_normalization_role']}
        else:continue
        row=c.execute('SELECT *FROM '+table+' WHERE '+('id'if table=='edges'else'uid')+'=?',(before['id']if table=='edges'else before['uid'],)).fetchone()
        if not row or dict(row)!=after:raise ValueError('Current raw SOURCE row differs from exact approved nominal after state')
        rows=c.execute('SELECT before_json,after_json,evidence FROM usability_changes WHERE stage="nominal_design_scope_repairs"AND object_type=?AND object_id=?',(kind,identifier)).fetchall()
        if sum(json.loads(r['before_json'])==historical_before and json.loads(r['after_json'])==historical_after and json.loads(r['evidence'])==op['proof']for r in rows)!=1:
            raise ValueError('Exact current nominal full-row history must be unique')
        choices.append((after,op))
    if len(choices)>1:raise ValueError('Ambiguous later nominal full-row permission')
    return choices[0]if choices else(before,None)


def referenced_nominal_transitions(originals, nominal_operations):
    """Derive permissions from original source witnesses, not a reported count."""
    def serial(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    original_rows=set()
    def visit(value):
        if isinstance(value,dict):
            original_rows.add(serial(value))
            for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    visit(originals)
    result=[]
    for op in nominal_operations:
        if op['op']=='review_class_edge':
            before=op['before_assertion']
            # An old SOURCE7 link is itself part of the before row's proof,
            # even when its newly assigned database id was not known at input.
            was_old_link=any(o['op']=='link'and(o['uid'],o['parent'],o['relation'],o['source'])==
                (op['uid'],op['parent'],op['relation'],before['source'])and
                json.loads(before['data']).get('admission_basis')==o['proof']for o in originals)
            if serial(before)in original_rows or was_old_link:
                result.append(('edges',before))
        elif op['op']=='correct_role':
            for table,key in [('node_profiles','profile'),('normalization_roles','normalization_role')]:
                before=op['before_'+key]
                if before is not None and serial(before)in original_rows:result.append((table,before))
    return result


class NinthOwnedTemporalContract(EighthOwnedTemporalContract):
    def __init__(self,c,database,inputs,actual_audit,nominal_scope_audit,fixture_only=False):
        if fixture_only:raise ValueError('Ninth source acceptance cannot use an unfrozen fixture')
        metadata={r['key']:json.loads(r['value'])for r in c.execute('SELECT *FROM metadata')}
        require_complete_type_receipt(actual_audit,database,inputs,metadata['database_revision'],ROOT)
        self.nominal_operations,self.nominal_binding=load_nominal_operations(database,inputs,nominal_scope_audit,metadata['database_revision'],ROOT)
        super().__init__(c,database,inputs,actual_audit,False)
        self.nominal_checked=[]
        original_manifest=json.loads((self.inputs/'structure_owned_scope_repairs.json').read_bytes())
        originals=[json.loads(line)for line in(self.inputs/original_manifest['operations_file']).read_text().splitlines()if line]
        for table,before in referenced_nominal_transitions(originals,self.nominal_operations):self.expected_row(table,before)

    def expected_row(self,table,before):
        after,permission=exact_nominal_after(self.c,self.nominal_operations,table,before)
        if permission:
            item={'table':table,'identifier':before.get('id',before.get('uid')),
                'before':before,'after':after,'proof':permission['proof']}
            if item not in self.nominal_checked:self.nominal_checked.append(item)
        return after

    def transition(self,original):
        transition=super().transition(original)
        if transition:return transition
        if original['op']!='link'or original['relation']!='IS_A':return None
        matches=[op for op in self.nominal_operations if op['op']=='review_class_edge'
            and(op['uid'],op['parent'],op['relation'],op['before_assertion']['source'])==
            (original['uid'],original['parent'],original['relation'],original['source'])]
        if len(matches)>1:raise ValueError('Ambiguous nominal retirement of an old SOURCE7 link')
        if not matches:return None
        review=matches[0];before=review['before_assertion']
        if json.loads(before['data']).get('admission_basis')!=original['proof']:
            raise ValueError('Nominal withdrawal is not the original SOURCE7 complete source proof')
        self.expected_row('edges',before)
        roles=[op for op in self.nominal_operations if op['op']=='correct_role'and op['uid']==original['uid']]
        if len(roles)>1:raise ValueError('Ambiguous nominal SOURCE7 historical role')
        historical_role=(roles[0]['before_profile']or{}).get('node_kind','CLASS')if roles else 'CLASS'
        return {'historical_role':historical_role,'current_status':'SOURCE_SCOPE_REVIEW','source9_exact_review':True}

    def binding(self):
        return {**super().binding(),'ninth_temporal_owned_scope_contract':SCHEMA,
            'nominal_scope_actual_audit':self.nominal_binding,
            'later_exact_nominal_full_row_transitions':self.nominal_checked,
            'all_original_owned_scope_checks_preserved':True}


def require_temporal_ninth_owned_scope_receipt(report,database,inputs,revision,code_root=ROOT):
    report,database,inputs,code_root=map(Path,(report,database,inputs,code_root))
    value=require_temporal_eighth_owned_scope_receipt(report,database,inputs,revision,code_root)
    if value.get('ninth_temporal_owned_scope_contract')!=SCHEMA or value.get('all_original_owned_scope_checks_preserved')is not True:
        raise ValueError('Actual entire SOURCE7 audit with current SOURCE8/9 guards required')
    actual=value['complete_type_actual_audit'];actual_path=Path(actual['path'])
    if digest(actual_path)!=actual['sha256']:raise ValueError('Current ninth SOURCE8 actual evidence changed')
    require_complete_type_receipt(actual_path,database,inputs,revision,code_root)
    binding=value['nominal_scope_actual_audit'];operations,expected_binding=load_nominal_operations(database,inputs,binding['path'],revision,code_root)
    if binding!=expected_binding:raise ValueError('Exact actual SOURCE9 permission bytes differ')
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)as c:
        c.row_factory=sqlite3.Row;metadata={k:json.loads(v)for k,v in c.execute('SELECT *FROM metadata')}
        for name in('audit_temporal_ninth_owned_scope_repairs.py','structure_ninth_owned_scope_temporal_contract.py'):
            if metadata['structure_frozen_build_manifest']['code'].get('scripts/'+name)!=digest(code_root/'scripts'/name):raise ValueError('Actual current ninth owned scope implementation must be frozen')
        transitions=value.get('later_exact_nominal_full_row_transitions')
        if not isinstance(transitions,list):raise ValueError('Explicit exact SOURCE9 transition inventory required')
        seen=set()
        for item in transitions:
            key=(item['table'],item['identifier'])
            if key in seen:raise ValueError('Duplicate reported nominal full-row transition')
            seen.add(key);after,op=exact_nominal_after(c,operations,item['table'],item['before'])
            if not op or after!=item['after']or op['proof']!=item['proof']:raise ValueError('Unapproved later nominal source row transition')
        mf=json.loads((inputs/'structure_owned_scope_repairs.json').read_bytes())
        originals=[json.loads(line)for line in(inputs/mf['operations_file']).read_text().splitlines()if line]
        expected=[]
        for table,before in referenced_nominal_transitions(originals,operations):
            after,op=exact_nominal_after(c,operations,table,before)
            expected.append({'table':table,'identifier':before.get('id',before.get('uid')),'before':before,'after':after,'proof':op['proof']})
        canonical=lambda row:json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        if {canonical(row)for row in transitions}!={canonical(row)for row in expected}:
            raise ValueError('Every referenced SOURCE7 later nominal transition must be checked exactly')
    return value


require_owned_scope_receipt=require_temporal_ninth_owned_scope_receipt
