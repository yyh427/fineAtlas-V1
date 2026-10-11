"""Retain full raw preservation and require exact later subject-scope history."""
from pathlib import Path

from structure_delivery_source_guard import validate_source_preservation as validate_original_preservation


def validate_source_preservation(report_path, database, baseline, reference,
                                 inputs, revision, code_root):
    report = validate_original_preservation(
        report_path, database, baseline, reference, inputs, revision, code_root)
    # The original guard checks every raw table, exactly 170 authorized
    # visibility changes, input hashes and both original delta audit censuses.
    # It does not authorize later changes to an old type assertion's status.
    # Require the independent real-row temporal audit as a second gate.
    from structure_subject_scope_temporal_contract import require_temporal_subject_receipt
    from structure_delivery_delta_registry import required_deltas
    required = any(spec.name == 'complete-subject-scope'
                   for spec in required_deltas(Path(inputs), Path(code_root)))
    if required:
        rows = [row for row in report.get('independent_actual_audits', [])
                if row.get('delta') == 'complete-subject-scope']
        if len(rows) != 1:
            raise ValueError('Exactly one complete actual temporal subject audit is required')
        require_temporal_subject_receipt(
            Path(rows[0]['report']), Path(database), Path(inputs), revision, Path(code_root))
    return report
