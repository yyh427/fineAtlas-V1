"""Require the actual appended type checkpoint and independent source audit."""
import json
from pathlib import Path
import sqlite3

from _download import digest
from structure_delivery_delta_registry import DeltaAudit, input_path, validate_delta_receipt

SPEC = DeltaAudit('nominal-design-scope', 'src/fineatlas/structure_nominal_design_scope_repairs.py',
                 'structure_nominal_design_scope_repairs.json', 'audit_nominal_design_scope_repairs.py',
                 'FINEATLAS_INDEPENDENT_NOMINAL_DESIGN_SCOPE_AUDIT_V1', 'nominal_design_scope_repairs')
STAGES = ('verify_complete_owned_type_parent_copy', 'nominal_design_scope_repairs',
          'whole_graph_recomputation', 'freeze_metadata', 'browse_staging', 'embed_browse_indexes')


def require_nominal_scope_child_build(receipt_path):
    # The new portable checker also verifies exact lineage and the actual
    # whole-byte-copy stage, so a relabelled ancestor cannot satisfy this gate.
    from portable_nominal_structure_lineage import require_nominal_scope_build
    return require_nominal_scope_build(receipt_path)


def require_nominal_scope_receipt(report, database, inputs, revision, code_root):
    database, inputs, code_root = map(Path, (database, inputs, code_root))
    manifest_path = input_path(SPEC, inputs, code_root)
    if manifest_path is None:
        raise ValueError('Nominal-scope child requires frozen ninth delta inputs')
    value = validate_delta_receipt(SPEC, Path(report), database, inputs, revision, code_root)
    if (value is None or value.get('candidate_acceptance') is not True
            or value.get('unsealed_source_diagnostic') is not False):
        raise ValueError('An unsealed source diagnostic cannot authorize packaging')
    manifest = json.loads(manifest_path.read_bytes())
    name = manifest['source_review_file']
    if not isinstance(name, str) or Path(name).name != name or not (inputs / name).is_file():
        raise ValueError('Safe independent source-review input required')
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as con:
        meta = {key: json.loads(raw) for key, raw in con.execute('SELECT * FROM metadata')}
    freeze = meta['structure_frozen_build_manifest']
    if (digest(inputs / name) != manifest['source_review_sha256']
            or freeze['inputs'].get(name) != manifest['source_review_sha256']
            or freeze['code'].get('scripts/' + SPEC.auditor) != digest(code_root / 'scripts' / SPEC.auditor)):
        raise ValueError('Independent scope review and actual auditor bytes must be frozen')
    operations = [json.loads(line) for line in (inputs / manifest['operations_file']).read_text().splitlines() if line]
    def expected_key(op):
        key = (op['uid'], op['parent'], op['relation'])
        return (*key, op['before_assertion']['id']) if op['op'] == 'review_class_edge' else key
    def checked_key(row):
        key = (row['uid'], row['parent'], row['relation'])
        return (*key, row['reviewed_original_id']) if 'reviewed_original_id' in row else key
    expected = {expected_key(o) for o in operations}
    checked = value.get('checked_complete_source', [])
    if (len(expected) != len(operations) or len(checked) != len(expected)
            or {checked_key(row) for row in checked} != expected):
        raise ValueError('Every exact source operation needs its independent complete-field check')
    return value
