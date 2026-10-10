"""Registered additive source deltas require independently bound actual audits.

Keep the validated OEM interface separate. New adapters declare literal input
names; auditors may vary in semantics while using this common evidence contract.
"""
from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

from _download import digest

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DeltaAudit:
    name: str
    module: str
    fallback_input: str
    auditor: str
    schema: str
    metadata_key: str | None = None


REGISTERED_DELTAS = (
    DeltaAudit('complete-subject-scope', 'src/fineatlas/structure_complete_subject_scope_repairs.py',
               'structure_complete_subject_scope_repairs.json', 'audit_complete_subject_scope_repairs.py',
               'FINEATLAS_INDEPENDENT_COMPLETE_SUBJECT_SCOPE_AUDIT_V1'),
    DeltaAudit('cars-projection-view', 'src/fineatlas/structure_cars_projection_view_repairs.py',
               'structure_cars_projection_view_repairs.json', 'audit_cars_projection_view_repairs.py',
               'FINEATLAS_INDEPENDENT_CARS_PROJECTION_VIEW_AUDIT_V1', 'cars_projection_view_repairs'),
)


def input_path(spec: DeltaAudit, inputs: Path, code_root: Path = ROOT) -> Path | None:
    module = code_root / spec.module
    if not module.exists():
        if (inputs / spec.fallback_input).exists():
            raise ValueError('Frozen delta input lacks its adapter: ' + spec.name)
        return None
    values = []
    for statement in ast.parse(module.read_text()).body:
        if isinstance(statement, ast.Assign) and any(isinstance(x, ast.Name) and x.id == 'INPUT_NAME' for x in statement.targets):
            values.append(ast.literal_eval(statement.value))
    if len(values) != 1 or not isinstance(values[0], str) or Path(values[0]).name != values[0]:
        raise ValueError('Delta adapter must declare one safe literal INPUT_NAME')
    path = inputs / values[0]
    return path if path.exists() else None


def required_deltas(inputs: Path, code_root: Path = ROOT) -> list[DeltaAudit]:
    return [spec for spec in REGISTERED_DELTAS if input_path(spec, inputs, code_root) is not None]


def validate_delta_receipt(spec: DeltaAudit, report_path: Path, database: Path,
                           inputs: Path, revision: str, code_root: Path = ROOT) -> dict | None:
    manifest_path = input_path(spec, inputs, code_root)
    if manifest_path is None:
        return None
    report = json.loads(report_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    operation_name = manifest['operations_file']
    operation_path = (inputs / operation_name).resolve()
    if not operation_path.is_relative_to(inputs.resolve()):
        raise ValueError('Delta operations escape the frozen input directory')
    records = [json.loads(line) for line in operation_path.read_text().splitlines() if line]
    count = manifest['operation_count']
    if type(count) is not int or count < 1 or len(records) != count:
        raise ValueError('Complete nonempty frozen delta operation census required')
    expected_relations = dict(Counter(row['relation'] for row in records))
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as con:
        meta = {key: json.loads(value) for key, value in con.execute('SELECT * FROM metadata')}
    frozen = meta['structure_frozen_build_manifest']['inputs']
    if (meta['database_revision'] != revision or frozen.get(manifest_path.name) != digest(manifest_path) or
            frozen.get(operation_name) != digest(operation_path) or
            digest(operation_path) != manifest['operations_sha256']):
        raise ValueError('Actual delta inputs or database differ from the frozen snapshot')
    if spec.metadata_key:
        applied = meta.get(spec.metadata_key, {})
        if (applied.get('manifest_sha256') != frozen[manifest_path.name] or
                applied.get('operations_sha256') != frozen[operation_name] or
                type(applied.get('operation_count')) is not int or applied['operation_count'] != count):
            raise ValueError('Actual applied delta metadata does not bind the frozen operations: ' + spec.name)
    if (report.get('schema') != spec.schema or report.get('pass') is not True or
            report.get('preflight_only') is not False or report.get('errors') != [] or
            Path(report.get('database', '')).resolve() != database.resolve() or
            report.get('database_revision') != revision or
            report.get('manifest_sha256') != frozen[manifest_path.name] or
            report.get('operations_sha256') != frozen[operation_name] or
            type(report.get('operation_count')) is not int or report['operation_count'] != count or
            report.get('operations') != expected_relations or
            any(type(value) is not int for value in report.get('operations', {}).values())):
        raise ValueError('Complete actual delta audit with exact revision, manifests and census required: ' + spec.name)
    return report
