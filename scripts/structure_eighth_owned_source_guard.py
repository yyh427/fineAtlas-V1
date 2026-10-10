"""Require full historical raw preservation plus actual current SOURCE layers."""
from pathlib import Path
import json
import sqlite3

from _download import digest
from structure_owned_source_guard import validate_source_preservation as validate_original_preservation
from structure_eighth_subject_scope_temporal_contract import require_temporal_eighth_subject_receipt
from structure_complete_owned_type_delivery_guard import require_complete_type_receipt


def validate_source_preservation(report_path, database, baseline, reference, inputs, revision, code_root):
    report=validate_original_preservation(report_path,database,baseline,reference,inputs,revision,code_root)
    database,inputs,code_root=map(Path,(database,inputs,code_root))
    audits={r['delta']:r for r in report['independent_actual_audits']}
    require_temporal_eighth_subject_receipt(audits['complete-subject-scope']['report'],database,inputs,revision,code_root)
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)as c:
        meta={k:json.loads(v)for k,v in c.execute('SELECT *FROM metadata')}
    frozen=meta['structure_frozen_build_manifest']
    for name in('structure_eighth_owned_source_guard.py','audit_eighth_owned_source_preservation.py','audit_temporal_cars_projection_view_repairs.py','structure_eighth_original_source_contract.py'):
        if frozen['code'].get('scripts/'+name)!=digest(code_root/'scripts'/name):raise ValueError('Actual later raw-preservation implementation must be frozen')
    current_path=Path(audits['cars-projection-view']['report']);current=json.loads(current_path.read_bytes())
    if (current.get('temporal_original_source_contract')!='FINEATLAS_EXACT_LATER_SOURCE_REPLACEMENT_AND_AUTHOR_MAPPING_V1'
            or current.get('current_role_and_mapping_rows_were_not_rewritten')is not True
            or current.get('candidate_acceptance')is not True
            or current.get('auditor_code_sha256')!=digest(code_root/'scripts/audit_temporal_cars_projection_view_repairs.py')
            or current.get('original_auditor_sha256')!=digest(code_root/'scripts/audit_cars_projection_view_repairs.py')):
        raise ValueError('Complete current Cars preservation and exact later mapping histories are required')
    actual=current.get('actual_later_source_audits',[])
    if len(actual)!=2:raise ValueError('Actual SOURCE7 and SOURCE8 receipts are independently required')
    eighth_path=Path(actual[1]['path'])
    if digest(eighth_path)!=actual[1]['sha256']:raise ValueError('Current eighth source evidence changed')
    require_complete_type_receipt(eighth_path,database,inputs,revision,code_root)
    return report
