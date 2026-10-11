"""Recognize exact modern source-review envelopes in the legacy library audit.

No keyword, label or source namespace supplies proof. Modern evidence is usable
only through the complete current Source8/9 receipt and its exact frozen operation,
before/after rows, evidence payload and history entry. The legacy auditor and all
its other structural checks remain unchanged.
"""
from __future__ import annotations
import json
from pathlib import Path

from structure_ninth_complete_type_temporal_contract import require_complete_type_receipt
from structure_nominal_design_scope_delivery_guard import require_nominal_scope_receipt

ROOT = Path(__file__).resolve().parents[1]
ROLE_KINDS = {'SOURCE_OWNED_GRAIN_CORRECTION_V1', 'SOURCE_REVIEWED_WHOLE_NOMINAL_DESIGN_SCOPE'}
CLASS_KIND = 'SOURCE_REVIEWED_WHOLE_NOMINAL_DESIGN_SCOPE'


def row(con, table, uid):
    value = con.execute('SELECT * FROM ' + table + ' WHERE uid=?', (uid,)).fetchone()
    return dict(value) if value else None


class ReviewedLibraryEvidence:
    def __init__(self, database, inputs, complete_receipt, nominal_receipt):
        import sqlite3
        database, inputs = Path(database).resolve(), Path(inputs).resolve()
        with sqlite3.connect(database.as_uri() + '?mode=ro&immutable=1', uri=True) as con:
            revision = json.loads(con.execute("SELECT value FROM metadata WHERE key='database_revision'").fetchone()[0])
        require_nominal_scope_receipt(nominal_receipt, database, inputs, revision, ROOT)
        require_complete_type_receipt(complete_receipt, database, inputs, revision, ROOT)
        self.roles, self.class_reviews = {}, {}
        for filename in ('structure_complete_owned_type_repairs.json', 'structure_nominal_design_scope_repairs.json'):
            manifest = json.loads((inputs / filename).read_text())
            for line in (inputs / manifest['operations_file']).open():
                if not line.strip():
                    continue
                operation = json.loads(line)
                if operation['op'] == 'correct_role':
                    self.roles[operation['uid']] = operation
                elif operation['op'] == 'review_class_edge':
                    key = ('edges', operation['before_assertion']['id'])
                    if key in self.class_reviews:
                        raise ValueError('Duplicate exact class source review')
                    self.class_reviews[key] = operation

    def role_evidence(self, con, uid, old_role, new_role, original):
        legacy = original(con, uid, old_role, new_role)
        if legacy is not None:
            return legacy
        operation = self.roles.get(uid)
        if not operation:
            return None
        before = operation['before_profile']
        expected_profile, expected_norm = operation['after_profile'], operation['after_normalization_role']
        if (not before or before.get('uid') != uid or before.get('node_kind') != old_role
                or expected_profile.get('uid') != uid or expected_profile.get('node_kind') != new_role
                or expected_norm.get('canonical_role') != new_role or expected_norm.get('status') != 'VERIFIED'
                or row(con, 'node_profiles', uid) != expected_profile
                or row(con, 'normalization_roles', uid) != expected_norm):
            return None
        evidence = con.execute('SELECT payload FROM evidence WHERE evidence_id=?', (expected_norm['evidence_id'],)).fetchone()
        if not evidence:
            return None
        proof = json.loads(evidence[0])
        if proof != operation['proof'] or proof.get('kind') not in ROLE_KINDS:
            return None
        return {'uid': uid, 'old_role': old_role, 'new_role': new_role,
                'evidence_id': expected_norm['evidence_id'], 'basis': proof['kind'],
                'modern_complete_source_operation_verified': True,
                'generic_kind_field_alone_is_not_proof': True}

    def withdrawal_evidence(self, con, before_path, original, *, baseline_con=None, ledger_index=None):
        result = original(con, before_path, baseline_con=baseline_con, ledger_index=ledger_index)
        present = {(entry['storage'], entry['record_id']) for entry in result}
        for step in before_path.get('path', []):
            edge = step['edge']
            if edge['relation'] == 'SAME_CONCEPT' or 'subject_uid' in edge or edge.get('terminal_connection'):
                continue
            key = ('edges', edge['id'])
            operation = self.class_reviews.get(key)
            if not operation or key in present:
                continue
            before = operation['before_assertion']
            if (operation.get('table') != 'edges' or operation.get('after_status') != 'SOURCE_SCOPE_REVIEW'
                    or (step['uid'], step['parent_uid'], edge['relation']) !=
                    (before['child_uid'], before['parent_uid'], before['relation'])):
                continue
            current_row = con.execute('SELECT * FROM edges WHERE id=?', (edge['id'],)).fetchone()
            if not current_row:
                continue
            current = dict(current_row)
            if current != {**before, 'status': operation['after_status']}:
                continue
            if baseline_con is not None:
                baseline = baseline_con.execute('SELECT * FROM edges WHERE id=?', (edge['id'],)).fetchone()
                if not baseline or dict(baseline) != before:
                    continue
            ledgers = (ledger_index.get(str(edge['id']), []) if ledger_index is not None else
                       con.execute('SELECT stage,object_type,object_id,before_json,after_json,evidence '
                                   'FROM usability_changes WHERE object_id=? ORDER BY id', (str(edge['id']),)))
            proof = operation['proof']
            if proof.get('kind') != CLASS_KIND:
                continue
            for ledger in ledgers:
                if (ledger['stage'] != 'nominal_design_scope_repairs'
                        or ledger['object_type'] != 'class_scope_review'
                        or json.loads(ledger['before_json']) != before
                        or json.loads(ledger['after_json']) != {'status': current['status']}
                        or json.loads(ledger['evidence']) != proof):
                    continue
                result.append({'storage': 'edges', 'record_id': edge['id'], 'new_status': current['status'],
                               'stage': ledger['stage'], 'basis': proof['kind'],
                               'modern_complete_source_operation_verified': True,
                               'scientific_identity_is_now_confirmed': False})
                present.add(key)
                break
        return result
