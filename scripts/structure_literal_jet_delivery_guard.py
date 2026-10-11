"""Additive fifth-delta evidence contract; the prior registry is immutable."""
from pathlib import Path
import json

from _download import digest

from structure_delivery_delta_registry import DeltaAudit, input_path, validate_delta_receipt

SPEC = DeltaAudit('literal-jet-scope', 'src/fineatlas/structure_literal_jet_scope_repairs.py',
                 'structure_literal_jet_scope_repairs.json', 'audit_literal_jet_scope_repairs.py',
                 'FINEATLAS_INDEPENDENT_LITERAL_JET_SCOPE_AUDIT_V1', 'literal_jet_scope_repairs')


def require_literal_jet_receipt(report, database, inputs, revision, code_root):
    if input_path(SPEC, Path(inputs), Path(code_root)) is None:
        raise ValueError('Literal-jet checkpoint requires its frozen fifth delta')
    value = validate_delta_receipt(SPEC, Path(report), Path(database), Path(inputs), revision, Path(code_root))
    if value is None:
        raise ValueError('Complete actual literal-jet evidence is required')
    return value


CHILD_STAGES = ("verify_completed_resumed_parent_copy", "literal_jet_scope_repairs",
                "primary_aircraft_family_repairs", "owned_scope_repairs", "whole_graph_recomputation", "freeze_metadata", "browse_staging", "embed_browse_indexes")


def require_literal_jet_child_build(receipt_path):
    """A prior nine-stage repair parent cannot stand in for this child build."""
    receipt_path = Path(receipt_path)
    value = json.loads(receipt_path.read_text())
    if (value.get('schema') != 'FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1'
            or value.get('complete') is not True or value.get('pass') is not True
            or not value.get('build_id') or not value.get('ended_utc')
            or value.get('required_stages') != list(CHILD_STAGES)):
        raise ValueError('Complete actual eight-stage literal-jet child build required')
    for name in ('started_fingerprints', 'build_status'):
        path = receipt_path.parent / (name + '.json')
        if digest(path) != value.get(name + '_sha256'):
            raise ValueError('Actual literal-jet child evidence changed: ' + name)
    states = json.loads((receipt_path.parent / 'build_status.json').read_text())
    if set(states) != set(CHILD_STAGES) or any(row.get('status') != 'PASS' for row in states.values()):
        raise ValueError('Every actual literal-jet child stage must pass')
    return value
