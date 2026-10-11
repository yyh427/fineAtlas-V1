"""Require the actual appended type checkpoint and independent source audit."""
import json
from pathlib import Path
import sqlite3

from _download import digest
from structure_delivery_delta_registry import DeltaAudit, input_path, validate_delta_receipt

SPEC = DeltaAudit('complete-owned-type', 'src/fineatlas/structure_complete_owned_type_repairs.py',
                 'structure_complete_owned_type_repairs.json', 'audit_temporal_ninth_complete_owned_type_repairs.py',
                 'FINEATLAS_INDEPENDENT_COMPLETE_OWNED_TYPE_AUDIT_V1', 'complete_owned_type_repairs')
STAGES = ('verify_complete_owned_scope_parent_copy', 'complete_owned_type_repairs',
          'whole_graph_recomputation', 'freeze_metadata', 'browse_staging', 'embed_browse_indexes')


def require_complete_type_child_build(receipt_path):
    # The new portable checker also verifies exact lineage and the actual
    # whole-byte-copy stage, so a relabelled ancestor cannot satisfy this gate.
    from portable_complete_structure_lineage import require_complete_type_build
    return require_complete_type_build(receipt_path)


def require_temporal_ninth_complete_type_receipt(report, database, inputs, revision, code_root):
    database, inputs, code_root = map(Path, (database, inputs, code_root))
    manifest_path = input_path(SPEC, inputs, code_root)
    if manifest_path is None:
        raise ValueError('Complete-source child requires frozen eighth delta inputs')
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
    expected = {(o['uid'], o['parent'], o['relation']) for o in operations}
    checked = value.get('checked_complete_source', [])
    if len(checked) != len(expected) or {(r['uid'], r['parent'], r['relation']) for r in checked} != expected:
        raise ValueError('Every added source direction needs its independent complete-field check')
    temporal = value.get('temporal_ninth_auditor', {})
    binding = temporal.get('verified_source9_audit')
    if (temporal.get('name') != SPEC.auditor
            or temporal.get('sha256') != digest(code_root / 'scripts' / SPEC.auditor)
            or not isinstance(binding, dict)):
        raise ValueError('Actual frozen ninth temporal executor and source-nine audit required')
    from structure_nominal_design_scope_delivery_guard import require_nominal_scope_receipt
    prior_report = Path(binding['path'])
    later = require_nominal_scope_receipt(prior_report, database, inputs, revision, code_root)
    if (binding.get('sha256') != digest(prior_report)
            or binding.get('operations_sha256') != later['operations_sha256']):
        raise ValueError('Actual source-nine temporal permission changed')
    return value

require_complete_type_receipt = require_temporal_ninth_complete_type_receipt
