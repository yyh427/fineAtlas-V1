"""Mandatory independent sixth-delta evidence; the old registry stays intact."""
from pathlib import Path

from structure_delivery_delta_registry import DeltaAudit, input_path, validate_delta_receipt

SPEC = DeltaAudit('primary-aircraft-family', 'src/fineatlas/structure_primary_aircraft_family_repairs.py',
                 'structure_primary_aircraft_family_repairs.json', 'audit_primary_aircraft_family_repairs.py',
                 'FINEATLAS_INDEPENDENT_PRIMARY_AIRCRAFT_FAMILY_AUDIT_V1', 'primary_aircraft_family_repairs')


def require_primary_aircraft_receipt(report, database, inputs, revision, code_root):
    if input_path(SPEC, Path(inputs), Path(code_root)) is None:
        raise ValueError('Primary-aircraft child requires its frozen sixth delta')
    value = validate_delta_receipt(SPEC, Path(report), Path(database), Path(inputs), revision, Path(code_root))
    if value is None:
        raise ValueError('Complete actual primary-aircraft family evidence is required')
    return value
