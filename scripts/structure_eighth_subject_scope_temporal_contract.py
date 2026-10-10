"""Exact later physical-grain transitions preserve every 1978 SOURCE check."""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from structure_subject_scope_temporal_contract import SubjectTemporalContract
from structure_regression_temporal_contract import ROOT, sha

REFERENCE='structure_complete_type_temporal_parent_reference.json'


def assertion_hash(row):
    return sha(json.dumps({k:v for k,v in row.items()if k not in ('id','status','reason')},sort_keys=True))


class EighthSubjectTemporalContract(SubjectTemporalContract):
    def __init__(self,database,inputs,output,connection,primary_snapshots_dir=None):
        super().__init__(database,inputs,output,connection,primary_snapshots_dir)
        self.eighth_manifest_path=self.inputs/'structure_complete_owned_type_repairs.json'
        self.eighth_manifest=json.loads(self.eighth_manifest_path.read_bytes())
        raw=(self.inputs/self.eighth_manifest['operations_file']).read_bytes()
        frozen=self.meta['structure_frozen_build_manifest']['inputs']
        if (sha(raw)!=self.eighth_manifest['operations_sha256']
                or frozen.get(self.eighth_manifest_path.name)!=sha(self.eighth_manifest_path.read_bytes())
                or frozen.get(self.eighth_manifest['operations_file'])!=sha(raw)
                or frozen.get(REFERENCE)!=sha((self.inputs/REFERENCE).read_bytes())):
            raise ValueError('Exact later physical-grain operations and temporal reference must be frozen')
        self.eighth_operations=[json.loads(line)for line in raw.decode().splitlines()if line]
        self.eighth_roles={o['uid']:o for o in self.eighth_operations if o['op']=='correct_role'}
        self.eighth_reviews=[o for o in self.eighth_operations if o['op']=='review_typed_relation']
        reference=json.loads((self.inputs/REFERENCE).read_bytes())
        receipt=json.loads(reference.get('subject_audit_receipt_text')or '{}')
        original_manifest_path=self.inputs/'structure_complete_subject_scope_repairs.json'
        original_manifest=json.loads(original_manifest_path.read_bytes())
        original_raw=(self.inputs/original_manifest['operations_file']).read_bytes()
        original_ops=[json.loads(line)for line in original_raw.decode().splitlines()if line]
        parent=self.meta['structure_complete_type_resume_parent']['parent_revision']
        if (reference.get('schema')!='FINEATLAS_COMPLETE_TYPE_SUBJECT_TEMPORAL_PARENT_REFERENCE_V1'
                or reference.get('parent_revision')!=parent
                or self.eighth_manifest['completed_parent_binding']['database_revision']!=parent
                or receipt.get('schema')!='FINEATLAS_INDEPENDENT_COMPLETE_SUBJECT_SCOPE_AUDIT_V1'
                or receipt.get('pass')is not True or receipt.get('preflight_only')is not False
                or receipt.get('errors')!=[] or receipt.get('database_revision')!=parent
                or receipt.get('manifest_sha256')!=sha(original_manifest_path.read_bytes())
                or receipt.get('operations_sha256')!=sha(original_raw)
                or receipt.get('operation_count')!=len(original_ops)
                or receipt.get('operations')!=dict(Counter(o['relation']for o in original_ops))
                or receipt.get('temporal_subject_contract')!='FINEATLAS_EXACT_LATER_COMPLETE_SUBJECT_TRANSITIONS_V1'
                or receipt.get('original_subject_contract_fully_checked')is not True
                or sha(reference['subject_audit_receipt_text'])!=reference.get('subject_audit_receipt_sha256')
                or reference.get('original_subject_temporal_auditor_sha256')!=sha((ROOT/'scripts/audit_temporal_complete_subject_scope_repairs.py').read_bytes())
                or reference.get('original_subject_manifest_sha256')!=sha(original_manifest_path.read_bytes())):
            raise ValueError('A real unchanged complete 8-stage parent SOURCE3 audit PASS is required')
        self.eighth_report=self.output.with_name(self.output.stem+'-complete-type-actual.json')

    def run_owned_actual_audit(self):
        super().run_owned_actual_audit()
        subprocess.run([sys.executable,'-B',str(ROOT/'scripts/audit_complete_owned_type_repairs.py'),
            '--database',str(self.database),'--inputs',str(self.inputs),'--output',str(self.eighth_report)],check=True)
        report=json.loads(self.eighth_report.read_bytes())
        if (report.get('schema')!='FINEATLAS_INDEPENDENT_COMPLETE_OWNED_TYPE_AUDIT_V1'
                or report.get('pass')is not True or report.get('preflight_only')is not False
                or report.get('errors')!=[] or report.get('candidate_acceptance')is not True
                or report.get('database_revision')!=self.meta['database_revision']
                or Path(report.get('database','')).resolve()!=self.database
                or report.get('manifest_sha256')!=sha(self.eighth_manifest_path.read_bytes())
                or report.get('operations_sha256')!=self.eighth_manifest['operations_sha256']
                or report.get('operation_count')!=len(self.eighth_operations)):
            raise ValueError('Actual independent exact later role/review/link SOURCE checks must pass')

    def expected_original_subject_role(self,uid,current_role):
        op=self.eighth_roles.get(uid)
        if not op:return current_role
        # The original stage's design-grain check is a historical statement,
        # permitted only by a frozen exact role migration with verified after.
        before=op.get('before_profile')
        if not before or not before.get('node_kind'):
            raise ValueError('Original SOURCE subject needs an actual earlier canonical role')
        after=self.c.execute('SELECT * FROM node_profiles WHERE uid=?',(uid,)).fetchone()
        norm=self.c.execute('SELECT * FROM normalization_roles WHERE uid=?',(uid,)).fetchone()
        if not after or not norm or dict(after)!=op['after_profile']or dict(norm)!=op['after_normalization_role']or current_role!=op['after_profile']['node_kind']:
            raise ValueError('Later role permission lacks its exact current after declarations')
        history=self.c.execute("SELECT * FROM usability_changes WHERE stage='complete_owned_type_repairs'AND object_type='role_source_adjudication'AND object_id=?",(uid,)).fetchall()
        old={'profile':op['before_profile'],'normalization_role':op['before_normalization_role']}
        new={'profile':op['after_profile'],'normalization_role':op['after_normalization_role']}
        if len([r for r in history if json.loads(r['before_json'])==old and json.loads(r['after_json'])==new and json.loads(r['evidence'])==op['proof']])!=1:
            raise ValueError('Later role migration must retain complete exact before/after SOURCE history')
        return before['node_kind']

    def expected_assertion_status(self,current,original_status):
        current={k:v for k,v in current.items()if k!='proof'}
        permissions=[o for o in self.eighth_reviews if o['before_assertion']['id']==current.get('id')and set(o['before_assertion'])==set(current)]
        if not permissions:return super().expected_assertion_status(current,original_status)
        if len(permissions)!=1:raise ValueError('Ambiguous later individual relation permission')
        op=permissions[0];before=op['before_assertion'];after={**before,'status':'SOURCE_SCOPE_REVIEW'}
        if (before['status']!=original_status or op.get('after_status')!='SOURCE_SCOPE_REVIEW'
                or current!=after or assertion_hash(before)!=op['content_sha256']):
            raise ValueError('Later individual encoding review must preserve the complete old assertion')
        rows=self.c.execute("SELECT * FROM usability_changes WHERE stage='complete_owned_type_repairs'AND object_type='typed_scope_review'AND object_id=?",(str(before['id']),)).fetchall()
        if len([r for r in rows if json.loads(r['before_json'])==before and json.loads(r['after_json'])=={'status':'SOURCE_SCOPE_REVIEW'}and json.loads(r['evidence'])==op['proof']])!=1:
            raise ValueError('Exact later typed encoding review history is absent')
        return 'SOURCE_SCOPE_REVIEW'

    def expected_active_count(self,source,old_count):
        after_seventh=super().expected_active_count(source,old_count)
        permissions=[o for o in self.eighth_reviews if o['before_assertion']['source']==source and o['before_assertion']['status']=='ACTIVE']
        for op in permissions:
            current=self.c.execute('SELECT * FROM entity_relations WHERE id=?',(op['before_assertion']['id'],)).fetchone()
            if not current or self.expected_assertion_status(dict(current),'ACTIVE')!='SOURCE_SCOPE_REVIEW':
                raise ValueError('Exact later SOURCE assertion withdrawal was not applied')
        return after_seventh-len(permissions)

    def receipt_binding(self):
        value=super().receipt_binding()
        value.update(eighth_temporal_subject_contract='FINEATLAS_EXACT_COMPLETE_OWNED_TYPE_SUBJECT_TRANSITIONS_V1',
            original_subject_scope_checks_preserved=True,
            complete_type_manifest_sha256=sha(self.eighth_manifest_path.read_bytes()),
            complete_type_temporal_reference_sha256=sha((self.inputs/REFERENCE).read_bytes()),
            complete_type_actual_audit={'path':str(self.eighth_report.resolve()),'sha256':sha(self.eighth_report.read_bytes())},
            later_complete_type_role_permissions=len(self.eighth_roles),
            later_complete_type_typed_permissions=len(self.eighth_reviews))
        return value
