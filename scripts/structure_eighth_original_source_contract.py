"""Read actual later audits and exact histories before interpreting old contracts.

Historical fingerprints are computed from frozen before rows. Current SQL rows
are never substituted or changed, and unrelated mutations remain failures.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from structure_owned_scope_delivery_guard import require_owned_scope_receipt
from structure_complete_owned_type_delivery_guard import require_complete_type_receipt

ROOT=Path(__file__).resolve().parents[1]


def sha(value):
    return hashlib.sha256(value.encode()if isinstance(value,str)else value).hexdigest()


def content_sha(row):
    return sha(json.dumps({k:v for k,v in dict(row).items()if k not in {'id','status','reason'}},sort_keys=True))


class LaterSourceContract:
    def __init__(self,c,database,inputs,owned_audit,complete_owned_audit=None):
        self.c=c;self.database=Path(database).resolve();self.inputs=Path(inputs).resolve()
        self.metadata={r['key']:json.loads(r['value'])for r in c.execute('SELECT *FROM metadata')}
        self.revision=self.metadata['database_revision'];self.frozen=self.metadata['structure_frozen_build_manifest']
        self.owned=require_owned_scope_receipt(owned_audit,self.database,self.inputs,self.revision,ROOT)
        self.audit_bindings=[{'path':str(Path(owned_audit).resolve()),'sha256':sha(Path(owned_audit).read_bytes())}]
        self.operations=[]
        for name in ('structure_owned_scope_repairs.json','structure_complete_owned_type_repairs.json'):
            path=self.inputs/name
            if not path.exists():continue
            manifest=json.loads(path.read_bytes());raw=(self.inputs/manifest['operations_file']).read_bytes()
            if sha(path.read_bytes())!=self.frozen['inputs'].get(name)or sha(raw)!=manifest['operations_sha256']or sha(raw)!=self.frozen['inputs'].get(manifest['operations_file']):
                raise ValueError('Later SOURCE operations must be exact frozen actual inputs')
            stage='owned_scope_repairs'if name=='structure_owned_scope_repairs.json'else'complete_owned_type_repairs'
            self.operations.extend((stage,json.loads(line))for line in raw.decode().splitlines()if line)
            if stage=='complete_owned_type_repairs':
                if complete_owned_audit is None:raise ValueError('Actual complete-owned type audit required for this child')
                require_complete_type_receipt(complete_owned_audit,self.database,self.inputs,self.revision,ROOT)
                self.audit_bindings.append({'path':str(Path(complete_owned_audit).resolve()),'sha256':sha(Path(complete_owned_audit).read_bytes())})
        self.checked_reviews=[];self.checked_mappings=[]

    def replacement_transition(self,repair):
        options=[(stage,o)for stage,o in self.operations if o['op']=='review_typed_relation'and o['uid']==repair['uid']and o['parent']==repair['parent']and o['relation']==repair['relation']and o['before_assertion']['source']==repair['source']]
        if not options:return None
        if len(options)!=1:raise ValueError('Ambiguous frozen replacement review permission')
        stage,o=options[0];before=o['before_assertion'];row=self.c.execute('SELECT *FROM entity_relations WHERE id=?',(before['id'],)).fetchone()
        if (before['status']!='ACTIVE'or o['after_status']!='SOURCE_SCOPE_REVIEW'or not row
                or dict(row)!={**before,'status':'SOURCE_SCOPE_REVIEW'}
                or content_sha(before)!=o['content_sha256']
                or json.loads(before['data']).get('admission_basis')!=repair['proof']):
            raise ValueError('Later review does not preserve this exact original SOURCE replacement')
        matches=self.c.execute("SELECT *FROM usability_changes WHERE stage=?AND object_type='typed_scope_review'AND object_id=?",(stage,str(before['id']))).fetchall()
        if len([r for r in matches if json.loads(r['before_json'])==before and json.loads(r['after_json'])=={'status':'SOURCE_SCOPE_REVIEW'}and json.loads(r['evidence'])==o['proof']])!=1:
            raise ValueError('Exact later SOURCE replacement review history is missing')
        roles=[(s,p)for s,p in self.operations if p['op']=='correct_role'and p['uid']==repair['uid']]
        oldrole=None
        if roles:
            if len(roles)!=1:raise ValueError('Ambiguous later SOURCE role transition')
            role_stage,role=roles[0];oldrole=(role['before_profile']or{}).get('node_kind')
            profile=self.c.execute('SELECT *FROM node_profiles WHERE uid=?',(repair['uid'],)).fetchone()
            norm=self.c.execute('SELECT *FROM normalization_roles WHERE uid=?',(repair['uid'],)).fetchone()
            if not profile or not norm or dict(profile)!=role['after_profile']or dict(norm)!=role['after_normalization_role']:
                raise ValueError('Current SOURCE canonical role differs from the precise later transition')
            histories=self.c.execute("SELECT *FROM usability_changes WHERE stage=?AND object_type IN('role_scope_correction','role_source_adjudication')AND object_id=?",(role_stage,repair['uid'])).fetchall()
            a={'profile':role['before_profile'],'normalization_role':role['before_normalization_role']};b={'profile':role['after_profile'],'normalization_role':role['after_normalization_role']}
            if len([r for r in histories if json.loads(r['before_json'])==a and json.loads(r['after_json'])==b and json.loads(r['evidence'])==role['proof']])!=1:
                raise ValueError('SOURCE role history does not match the frozen whole-object grain decision')
        result={'uid':repair['uid'],'id':before['id'],'content_sha256':o['content_sha256'],'historical_role':oldrole,'status':'SOURCE_SCOPE_REVIEW','stage':stage,'proof':o['proof'],'current_assertion':dict(row)}
        self.checked_reviews.append(result);return result

    def historical_mapping_hash(self,table):
        if table not in {'dataset_targets','dataset_mapping_checks'}:raise ValueError('Unsupported mapping table')
        current={(r['dataset'],str(r['class_id'])):dict(r)for r in self.c.execute('SELECT *FROM '+table)}
        earlier=dict(current)
        fields={'dataset_targets':('before_target','after_target'),'dataset_mapping_checks':('before_check','after_check')};before_field,after_field=fields[table]
        for stage,o in self.operations:
            if o['op']not in ('migrate_nominal_design_mapping','review_dataset_mapping'):continue
            key=(o['dataset'],str(o['class_id']));before=o[before_field];after=o[after_field]
            if current.get(key)!=after:raise ValueError('Current author mapping is not the exact later frozen after row')
            historykind='nominal_design_mapping'
            histories=self.c.execute('SELECT *FROM usability_changes WHERE stage=?AND object_type=?AND object_id=?',(stage,historykind,o['dataset']+':'+str(o['class_id']))).fetchall()
            a={'target':o['before_target'],'check':o['before_check']};b={'target':o['after_target'],'check':o['after_check']}
            if len([r for r in histories if json.loads(r['before_json'])==a and json.loads(r['after_json'])==b and json.loads(r['evidence'])==o['proof']])!=1:
                raise ValueError('Exact later author mapping history missing')
            if before is None:earlier.pop(key,None)
            else:earlier[key]=before
            self.checked_mappings.append({'table':table,'dataset':key[0],'class_id':key[1],'before_sha256':sha(json.dumps(before,sort_keys=True)),'after_sha256':sha(json.dumps(after,sort_keys=True))})
        rows=sorted(earlier.values(),key=lambda x:json.dumps(x,sort_keys=True))
        return sha(json.dumps(rows,sort_keys=True))

    def binding(self):
        return {'temporal_original_source_contract':'FINEATLAS_EXACT_LATER_SOURCE_REPLACEMENT_AND_AUTHOR_MAPPING_V1','actual_later_source_audits':self.audit_bindings,'later_exact_source_replacement_reviews':self.checked_reviews,'later_exact_author_mapping_histories':self.checked_mappings,'current_role_and_mapping_rows_were_not_rewritten':True}
