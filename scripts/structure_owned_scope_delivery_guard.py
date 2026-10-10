"""Require the independent owned-scope repair audit for this child checkpoint."""
from pathlib import Path

from structure_delivery_delta_registry import DeltaAudit, input_path, validate_delta_receipt

SPEC = DeltaAudit('owned-scope', 'src/fineatlas/structure_owned_scope_repairs.py',
                 'structure_owned_scope_repairs.json', 'audit_owned_scope_repairs.py',
                 'FINEATLAS_INDEPENDENT_OWNED_SCOPE_AUDIT_V1', 'owned_scope_repairs')


def require_owned_scope_receipt(report, database, inputs, revision, code_root):
    if input_path(SPEC, Path(inputs), Path(code_root)) is None:
        raise ValueError('Owned-scope child requires its frozen seventh delta')
    value = validate_delta_receipt(SPEC, Path(report), Path(database), Path(inputs), revision, Path(code_root))
    if value is None:
        raise ValueError('Complete actual owned-scope evidence is required')
    return value
