"""Bind complete public raw preservation to the downloaded database and freeze."""
import json
from pathlib import Path
import sqlite3

from _download import digest
from structure_delivery_delta_registry import input_path, required_deltas, validate_delta_receipt


def validate_source_preservation(report_path, database, baseline, reference, inputs, revision, code_root):
    report_path, database, baseline, reference, inputs = map(Path, (report_path, database, baseline, reference, inputs))
    report = json.loads(report_path.read_text())
    reference_tables = json.loads(reference.read_text())['tables']
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as con:
        metadata = {k: json.loads(v) for k, v in con.execute('SELECT * FROM metadata')}
    frozen = metadata['structure_frozen_build_manifest']['inputs']
    actual = {str(path.relative_to(inputs)): digest(path) for path in sorted(inputs.rglob('*')) if path.is_file()}
    if (report.get('schema') != 'FINEATLAS_RESUMED_RAW_SOURCE_PRESERVATION_V1'
            or report.get('pass') is not True or report.get('complete') is not True
            or Path(report.get('candidate', '')).resolve() != database.resolve()
            or Path(report.get('baseline', '')).resolve() != baseline.resolve()
            or report.get('database_revision') != revision or metadata.get('database_revision') != revision
            or report.get('allowed_fields') != ['nodes.visibility']
            or report.get('frozen_input_fingerprints') != frozen or actual != frozen
            or set(report.get('tables', {})) != set(reference_tables)):
        raise ValueError('Complete public raw preservation with exact database, freeze and source tables required')
    for name, row in report['tables'].items():
        expected = reference_tables[name]
        if (row.get('pass') is not True or row.get('columns') != expected['columns']
                or row.get('max_baseline_rowid') != expected['max_baseline_rowid']
                or row.get('baseline', {}).get('sha256') != expected['baseline']['sha256']
                or row.get('baseline', {}).get('rows') != expected['baseline']['rows']
                or row.get('candidate_with_audited_visibility', {}).get('sha256') != expected['baseline']['sha256']
                or row.get('candidate_with_audited_visibility', {}).get('rows') != expected['baseline']['rows']):
            raise ValueError('Every retained raw source row must match the immutable reference: ' + name)
    audits = {row['delta']: row for row in report.get('independent_actual_audits', [])}
    required = [spec for spec in required_deltas(inputs, code_root) if spec.name in {'complete-subject-scope', 'cars-projection-view'}]
    if len(audits) != len(report.get('independent_actual_audits', [])) or set(audits) != {spec.name for spec in required}:
        raise ValueError('Source visibility compatibility lacks complete actual independent delta evidence')
    permissions = {}
    for spec in required:
        manifest = json.loads(input_path(spec, inputs, code_root).read_text())
        rows = ([(r["uid"], r["before_node"]["visibility"], r["visibility_after"]) for r in manifest["source_projections"]]
                if spec.name == "cars-projection-view" else
                [(r["uid"], r["before_visibility"], "ACTIVE") for r in manifest.get("source_class_activations", [])])
        for uid, before, after in rows:
            if uid in permissions: raise ValueError("Duplicate source visibility permission")
            permissions[uid] = {"uid": uid, "before": before, "after": after, "delta": spec.name}
        evidence = audits[spec.name]; path = Path(evidence['report'])
        if digest(path) != evidence['sha256']:
            raise ValueError('Independent source migration evidence changed')
        validate_delta_receipt(spec, path, database, inputs, revision, code_root)
    applicable = {}
    with sqlite3.connect(baseline.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as con:
        for uid, permit in permissions.items():
            row = con.execute('SELECT visibility FROM nodes WHERE uid=?', (uid,)).fetchone()
            if row:
                if row[0] != permit['before']: raise ValueError('Original source visibility differs from frozen permission')
                applicable[uid] = permit
    changes = report.get('audited_visibility_changes', [])
    if len(changes) != len(applicable) or {row.get('uid'): row for row in changes} != applicable:
        raise ValueError('Complete exact audited visibility migration census required')
    return report
