"""Keep the complete 1,978-operation contract with exact later scope reviews."""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path

from structure_delivery_delta_registry import REGISTERED_DELTAS, validate_delta_receipt
from structure_regression_temporal_contract import TemporalContract, ROOT, sha, require_temporal_receipt


def validate_subject_parent_reference(reference,inputs,code_root=ROOT):
    inputs,code_root=Path(inputs),Path(code_root)
    receipt=json.loads(reference.get('subject_audit_receipt_text') or '{}')
    manifest_path=inputs/'structure_complete_subject_scope_repairs.json'
    manifest=json.loads(manifest_path.read_text())
    raw=(inputs/manifest['operations_file']).read_bytes()
    operations=[json.loads(line)for line in raw.decode().splitlines()if line]
    if (receipt.get('schema')!='FINEATLAS_INDEPENDENT_COMPLETE_SUBJECT_SCOPE_AUDIT_V1'
            or receipt.get('pass')is not True or receipt.get('preflight_only')is not False
            or receipt.get('errors')!=[] or receipt.get('database_revision')!=reference['parent_revision']
            or receipt.get('operations')!=dict(Counter(op['relation']for op in operations))
            or receipt.get('operation_count')!=len(operations)
            or receipt.get('manifest_sha256')!=sha(manifest_path.read_bytes())
            or receipt.get('operations_sha256')!=sha(raw) or manifest.get('operations_sha256')!=sha(raw)
            or sha(reference['subject_audit_receipt_text'])!=reference.get('subject_audit_receipt_sha256')
            or reference.get('original_subject_auditor_sha256')!=sha((code_root/'scripts/audit_complete_subject_scope_repairs.py').read_bytes())
            or reference.get('original_subject_manifest_sha256')!=sha(manifest_path.read_bytes())):
        raise ValueError('Actual unchanged complete-subject parent SQL audit PASS must remain frozen')
    return receipt


class SubjectTemporalContract(TemporalContract):
    def __init__(self,database,inputs,output,connection):
        super().__init__(database,inputs,output,connection)
        validate_subject_parent_reference(json.loads(self.reference_path.read_text()),self.inputs)

    def receipt_binding(self):
        value=super().receipt_binding()
        value['temporal_subject_contract']='FINEATLAS_EXACT_LATER_COMPLETE_SUBJECT_TRANSITIONS_V1'
        value['original_subject_contract_fully_checked']=True
        return value


def require_temporal_subject_receipt(report_path,database,inputs,revision,code_root=ROOT):
    spec=next(spec for spec in REGISTERED_DELTAS if spec.name=='complete-subject-scope')
    report=validate_delta_receipt(spec,Path(report_path),Path(database),Path(inputs),revision,Path(code_root))
    if (not report or report.get('temporal_subject_contract')!='FINEATLAS_EXACT_LATER_COMPLETE_SUBJECT_TRANSITIONS_V1'
            or report.get('original_subject_contract_fully_checked')is not True):
        raise ValueError('Complete actual temporal subject-scope SQL contract evidence required')
    require_temporal_receipt(report_path,database,inputs,revision)
    value=json.loads((Path(inputs)/'structure_regression_temporal_parent_reference.json').read_text())
    validate_subject_parent_reference(value,inputs,code_root)
    return report
