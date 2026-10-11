"""Explicit actual SOURCE7/8/9 receipts preserve complete earlier SQL checks."""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path
import sqlite3
from structure_regression_temporal_contract import ROOT, REFERENCE, sha
from structure_eighth_owned_scope_temporal_contract import EighthRegressionTemporalContract
from structure_eighth_subject_scope_temporal_contract import EighthSubjectTemporalContract

NINTH_INPUT = 'structure_nominal_design_scope_repairs.json'


def verified_path(evidence):
    path = Path(evidence.get('path', '/MISSING'))
    if not path.is_file() or sha(path.read_bytes()) != evidence.get('sha256'):
        raise ValueError('Current actual SOURCE evidence bytes changed')
    return path


def require_current_sources(owned, complete, nominal, database, inputs, revision, code_root=ROOT):
    from structure_ninth_owned_scope_temporal_contract import require_temporal_ninth_owned_scope_receipt
    from structure_ninth_complete_type_temporal_contract import require_temporal_ninth_complete_type_receipt
    from structure_nominal_design_scope_delivery_guard import require_nominal_scope_receipt
    a = require_nominal_scope_receipt(nominal, database, inputs, revision, code_root)
    b = require_temporal_ninth_complete_type_receipt(complete, database, inputs, revision, code_root)
    c = require_temporal_ninth_owned_scope_receipt(owned, database, inputs, revision, code_root)
    if verified_path(b['temporal_ninth_auditor']['verified_source9_audit']).resolve() != Path(nominal).resolve():
        raise ValueError('SOURCE8 must identify the supplied exact actual SOURCE9 receipt')
    if verified_path(c['complete_type_actual_audit']).resolve() != Path(complete).resolve():
        raise ValueError('SOURCE7 must identify the supplied exact actual SOURCE8 receipt')
    if verified_path(c['nominal_scope_actual_audit']).resolve() != Path(nominal).resolve():
        raise ValueError('SOURCE7 must identify the supplied exact actual SOURCE9 receipt')
    return a, b, c


class NinthMixin:
    def __init__(self, database, inputs, output, connection, primary_snapshots_dir=None,
                 owned_audit=None, complete_owned_audit=None, nominal_scope_audit=None):
        super().__init__(database, inputs, output, connection, primary_snapshots_dir)
        if not all((owned_audit, complete_owned_audit, nominal_scope_audit)):
            raise ValueError('Explicit current SOURCE7, SOURCE8 and SOURCE9 actual receipts required')
        self.owned_report = Path(owned_audit)
        self.eighth_report = Path(complete_owned_audit)
        self.nominal_report = Path(nominal_scope_audit)
        self.ninth_manifest_path = self.inputs / NINTH_INPUT
        self.ninth_manifest = json.loads(self.ninth_manifest_path.read_bytes())
        raw = (self.inputs / self.ninth_manifest['operations_file']).read_bytes()
        frozen = self.meta['structure_frozen_build_manifest']['inputs']
        if sha(raw) != self.ninth_manifest['operations_sha256'] or frozen.get(NINTH_INPUT) != sha(self.ninth_manifest_path.read_bytes()) or frozen.get(self.ninth_manifest['operations_file']) != sha(raw):
            raise ValueError('Exact ninth SOURCE operations must be frozen')
        self.ninth_operations = [json.loads(line) for line in raw.decode().splitlines() if line]
        self.ninth_roles = {o['uid']: o for o in self.ninth_operations if o['op'] == 'correct_role'}
        self.ninth_reviews = [o for o in self.ninth_operations if o['op'] == 'review_class_edge']
        if len(self.ninth_roles) != sum(o['op'] == 'correct_role' for o in self.ninth_operations):
            raise ValueError('Duplicate ninth SOURCE role permissions')

    def run_owned_actual_audit(self):
        # These were already executed once by the coordinator. Never execute an
        # output path again or use a historical receipt as current evidence.
        _, _, owned = require_current_sources(self.owned_report, self.eighth_report,
            self.nominal_report, self.database, self.inputs, self.meta['database_revision'])
        if self.primary_snapshots_dir is None or Path(owned.get('primary_snapshots_dir') or '/MISSING').resolve() != self.primary_snapshots_dir.resolve():
            raise ValueError('Actual SOURCE executors must bind the same explicit snapshots')

    def expected_original_subject_role(self, uid, current_role):
        op = self.ninth_roles.get(uid)
        if not op:
            return super().expected_original_subject_role(uid, current_role)
        for table, expected in [('node_profiles', op['after_profile']), ('normalization_roles', op['after_normalization_role'])]:
            row = self.c.execute('SELECT * FROM '+table+' WHERE uid=?', (uid,)).fetchone()
            if (dict(row) if row else None) != expected:
                raise ValueError('Ninth SOURCE historical role permission lacks exact current after')
        if current_role != op['after_profile']['node_kind']:
            raise ValueError('Ninth SOURCE canonical current role differs')
        before = {'profile': op['before_profile'], 'normalization_role': op['before_normalization_role']}
        after = {'profile': op['after_profile'], 'normalization_role': op['after_normalization_role']}
        self._history('role_source_adjudication', uid, before, after, op['proof'])
        rank = op['proof']['before_node']['rank'].lower()
        historical_default = ('MODEL' if rank in ('model','product_model','aircraft_model','vehicle_model') else
            'MODEL_FAMILY' if rank in ('model_family','series') else 'INSTANCE' if rank == 'instance' else
            'CONFIGURATION' if rank in ('model_year','model_year_configuration','configuration') else 'CLASS')
        role = op['before_profile']['node_kind'] if op['before_profile'] else historical_default
        if 'before_role' in op['proof'] and op['proof']['before_role'] != role:
            raise ValueError('Unprofiled historical role must derive from the unchanged original rank')
        return super().expected_original_subject_role(uid, role)

    def _history(self, kind, identifier, before, after, proof):
        rows = self.c.execute("SELECT * FROM usability_changes WHERE stage='nominal_design_scope_repairs' AND object_type=? AND object_id=?", (kind, str(identifier))).fetchall()
        if len([r for r in rows if json.loads(r['before_json']) == before and json.loads(r['after_json']) == after and json.loads(r['evidence']) == proof]) != 1:
            raise ValueError('Exact ninth SOURCE original/current history is missing')

    def expected_assertion_status(self, current, original_status):
        current = {k: v for k, v in current.items() if k != 'proof'}
        permissions = [o for o in self.ninth_reviews if o['before_assertion']['id'] == current.get('id') and set(o['before_assertion']) == set(current)]
        if not permissions:
            return super().expected_assertion_status(current, original_status)
        if len(permissions) != 1:
            raise ValueError('Ambiguous ninth SOURCE exact assertion permission')
        op = permissions[0]
        before = op['before_assertion']
        if before['status'] != original_status or current != dict(before, status='SOURCE_SCOPE_REVIEW') or sha(json.dumps({k:v for k,v in before.items() if k not in ('id','status','reason')},sort_keys=True)) != op['content_sha256']:
            raise ValueError('Ninth SOURCE review changed complete original assertion content')
        self._history('class_scope_review', before['id'], before, {'status': 'SOURCE_SCOPE_REVIEW'}, op['proof'])
        return 'SOURCE_SCOPE_REVIEW'

    def expected_active_count(self, source, old_count):
        count = super().expected_active_count(source, old_count)
        permissions = [o for o in self.ninth_reviews if o['before_assertion']['source'] == source and o['before_assertion']['status'] == 'ACTIVE']
        for op in permissions:
            current = self.c.execute('SELECT * FROM edges WHERE id=?', (op['before_assertion']['id'],)).fetchone()
            if not current or self.expected_assertion_status(dict(current), 'ACTIVE') != 'SOURCE_SCOPE_REVIEW':
                raise ValueError('Ninth SOURCE exact withdrawal was not actually applied')
        return count - len(permissions)

    def receipt_binding(self):
        value = super().receipt_binding()
        value.update(ninth_temporal_source_contract='FINEATLAS_EXACT_NINTH_SOURCE_TRANSITIONS_V1',
            original_ninth_propagated_checks_preserved=True,
            nominal_scope_manifest_sha256=sha(self.ninth_manifest_path.read_bytes()),
            nominal_scope_actual_audit={'path': str(self.nominal_report.resolve()), 'sha256': sha(self.nominal_report.read_bytes())},
            ninth_role_permission_count=len(self.ninth_roles), ninth_class_review_permission_count=len(self.ninth_reviews))
        return value


class NinthRegressionTemporalContract(NinthMixin, EighthRegressionTemporalContract):
    pass


class NinthSubjectTemporalContract(NinthMixin, EighthSubjectTemporalContract):
    pass


def _require(report_path, database, inputs, revision, code_root, subject):
    report_path, database, inputs, code_root = map(Path, (report_path, database, inputs, code_root))
    value = json.loads(report_path.read_bytes())
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1', uri=True) as c:
        meta = {k: json.loads(v) for k, v in c.execute('SELECT * FROM metadata')}
    frozen = meta['structure_frozen_build_manifest']
    # Preserve every original regression receipt field and source snapshot bind;
    # explicitly replace the obsolete downstream executor with current strict gates.
    if (value.get('pass') is not True or value.get('preflight_only') is not False or value.get('errors') != []
            or value.get('database_revision') != revision or meta['database_revision'] != revision
            or Path(value.get('database', '')).resolve() != database.resolve()
            or value.get('original_contract_fully_checked') is not True
            or value.get('temporal_contract') != 'FINEATLAS_EXACT_LATER_SCOPE_TRANSITIONS_V1'
            or value.get('temporal_parent_reference_sha256') != sha((inputs / REFERENCE).read_bytes())
            or value.get('owned_manifest_sha256') != sha((inputs / 'structure_owned_scope_repairs.json').read_bytes())
            or value.get('ninth_temporal_source_contract') != 'FINEATLAS_EXACT_NINTH_SOURCE_TRANSITIONS_V1'
            or value.get('original_ninth_propagated_checks_preserved') is not True):
        raise ValueError('Complete actual earlier SQL checks and strict ninth SOURCE receipt required')
    owned = verified_path(value['owned_actual_audit']); complete = verified_path(value['complete_type_actual_audit']); nominal = verified_path(value['nominal_scope_actual_audit'])
    _, _, owned_value = require_current_sources(owned, complete, nominal, database, inputs, revision, code_root)
    directory = Path(value.get('primary_snapshots_dir') or '/MISSING').resolve()
    if not directory.is_dir() or Path(owned_value.get('primary_snapshots_dir') or '/MISSING').resolve() != directory:
        raise ValueError('Original and current SOURCE snapshots differ')
    name = 'audit_temporal_ninth_complete_subject_scope_repairs.py' if subject else 'audit_temporal_ninth_structure_regression_repairs.py'
    for implementation in (name, 'structure_ninth_source_temporal_contract.py'):
        if frozen['code'].get('scripts/'+implementation) != sha((code_root/'scripts'/implementation).read_bytes()):
            raise ValueError('Actual ninth temporal implementations must be frozen')
    if subject:
        from structure_delivery_delta_registry import REGISTERED_DELTAS, validate_delta_receipt
        from structure_subject_scope_temporal_contract import validate_subject_parent_reference
        spec = next(s for s in REGISTERED_DELTAS if s.name == 'complete-subject-scope')
        validate_delta_receipt(spec, report_path, database, inputs, revision, code_root)
        validate_subject_parent_reference(json.loads((inputs/REFERENCE).read_bytes()), inputs, code_root)
        if value.get('temporal_subject_contract') != 'FINEATLAS_EXACT_LATER_COMPLETE_SUBJECT_TRANSITIONS_V1' or value.get('original_subject_contract_fully_checked') is not True or value.get('eighth_temporal_subject_contract') != 'FINEATLAS_EXACT_COMPLETE_OWNED_TYPE_SUBJECT_TRANSITIONS_V1' or value.get('original_subject_scope_checks_preserved') is not True:
            raise ValueError('Complete original subject and eighth temporal checks are required')
        from structure_eighth_subject_scope_temporal_contract import REFERENCE as EIGHTH_REFERENCE
        refpath = inputs/EIGHTH_REFERENCE
        ref = json.loads(refpath.read_bytes())
        mfpath = inputs/'structure_complete_owned_type_repairs.json'; mf = json.loads(mfpath.read_bytes())
        parent = meta['structure_complete_type_resume_parent']['parent_revision']
        if value.get('complete_type_manifest_sha256') != sha(mfpath.read_bytes()) or value.get('complete_type_temporal_reference_sha256') != sha(refpath.read_bytes()) or frozen['inputs'].get(EIGHTH_REFERENCE) != sha(refpath.read_bytes()) or ref.get('parent_revision') != parent or mf['completed_parent_binding']['database_revision'] != parent:
            raise ValueError('Actual complete eighth parent reference must remain unchanged')
        raw = (inputs/mf['operations_file']).read_bytes(); operations = [json.loads(l) for l in raw.decode().splitlines() if l]
        if value.get('later_complete_type_role_permissions') != sum(o['op']=='correct_role' for o in operations) or value.get('later_complete_type_typed_permissions') != sum(o['op']=='review_typed_relation' for o in operations):
            raise ValueError('Entire original eighth permission census must remain exact')
    elif value.get('eighth_regression_temporal_contract') != 'FINEATLAS_EXACT_CURRENT_OWNED_SCOPE_EXECUTOR_V1' or value.get('original_regression_scope_checks_preserved') is not True:
        raise ValueError('Entire original regression and eighth executor checks are required')
    mfpath=inputs/NINTH_INPUT; mf=json.loads(mfpath.read_bytes()); raw=(inputs/mf['operations_file']).read_bytes(); ops=[json.loads(l) for l in raw.decode().splitlines() if l]
    if value.get('nominal_scope_manifest_sha256') != sha(mfpath.read_bytes()) or value.get('ninth_role_permission_count') != sum(o['op']=='correct_role' for o in ops) or value.get('ninth_class_review_permission_count') != sum(o['op']=='review_class_edge' for o in ops):
        raise ValueError('Exact ninth SOURCE frozen permission inventory differs')
    return value


def require_temporal_ninth_regression_receipt(report_path, database, inputs, revision, code_root=ROOT):
    return _require(report_path, database, inputs, revision, code_root, False)


def require_temporal_ninth_subject_receipt(report_path, database, inputs, revision, code_root=ROOT):
    return _require(report_path, database, inputs, revision, code_root, True)
