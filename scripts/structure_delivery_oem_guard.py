"""Bind optional frozen OEM repairs to complete independent actual-data audits."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import sqlite3

from _download import digest

ROOT = Path(__file__).resolve().parents[1]
MODULE = 'src/fineatlas/structure_oem_body_scope_repairs.py'


def optional_oem_input(inputs: Path, code_root: Path = ROOT) -> Path | None:
    """Read the adapter's declared INPUT_NAME without importing its classifier."""
    module = code_root / MODULE
    if not module.exists():
        if (inputs / 'structure_oem_body_scope_repairs.json').exists():
            raise ValueError('Frozen OEM inputs lack their adapter module')
        return None
    names = []
    for statement in ast.parse(module.read_text()).body:
        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'INPUT_NAME' for target in statement.targets):
            names.append(ast.literal_eval(statement.value))
    if len(names) != 1 or not isinstance(names[0], str) or Path(names[0]).name != names[0]:
        raise ValueError('OEM adapter must declare one safe literal INPUT_NAME')
    path = inputs / names[0]
    return path if path.exists() else None


def validate_oem_receipt(report_path: Path, database: Path, inputs: Path,
                         revision: str, code_root: Path = ROOT) -> dict | None:
    manifest_path = optional_oem_input(inputs, code_root)
    if manifest_path is None:
        return None
    report = json.loads(report_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    operation_name = manifest['operations_file']
    operations = (inputs / operation_name).resolve()
    if not operations.is_relative_to(inputs.resolve()):
        raise ValueError('OEM operation input escapes the frozen directory')
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as con:
        meta = {key: json.loads(value) for key, value in con.execute('SELECT * FROM metadata')}
    frozen = meta['structure_frozen_build_manifest']['inputs']
    if (meta['database_revision'] != revision or
            frozen.get(manifest_path.name) != digest(manifest_path) or
            frozen.get(operation_name) != digest(operations) or
            digest(operations) != manifest['operations_sha256']):
        raise ValueError('Actual OEM inputs or database differ from the frozen snapshot')
    if (report.get('schema') != 'FINEATLAS_INDEPENDENT_OEM_BODY_SCOPE_AUDIT_V1' or
            report.get('pass') is not True or report.get('preflight_only') is not False or
            report.get('errors') != [] or
            Path(report.get('database', '')).resolve() != database.resolve() or
            report.get('database_revision') != revision or
            report.get('manifest_sha256') != frozen[manifest_path.name] or
            report.get('operations_sha256') != frozen[operation_name] or
            report.get('operation_count') != manifest['operation_count'] or
            sum(report.get('operations', {}).values()) != manifest['operation_count']):
        raise ValueError('Complete actual OEM audit with exact revision and manifests required')
    return report
