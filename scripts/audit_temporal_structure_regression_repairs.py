#!/usr/bin/env python3
"""Full original SQL regression contract with exact frozen later-stage transitions."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3

from structure_regression_temporal_contract import TemporalContract

SOURCE = 'Reviewed retained whole-object scope recovery'

def digest(raw):
    return hashlib.sha256(raw.encode() if isinstance(raw, str) else raw).hexdigest()

def run(database: Path, inputs: Path, output: Path, preflight: bool = False):
    manifest = json.loads((inputs / 'structure_regression_repairs.json').read_text())
    raw = (inputs / manifest['operations_file']).read_bytes()
    if digest(raw) != manifest['operations_sha256']:
        raise ValueError('Frozen repair input has changed')
    ops = [json.loads(line) for line in raw.decode().splitlines()]
    c = sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    c.row_factory = sqlite3.Row
    errors, counts = [], Counter()
    temporal = TemporalContract(database, inputs, output, c)
    temporal.run_owned_actual_audit()
    for op in ops:
        proof = op['proof']; uid, parent = op['uid'], op['parent']
        nodes = [c.execute('SELECT * FROM nodes WHERE uid=?', (key,)).fetchone() for key in (uid, parent)]
        if any(n is None for n in nodes):
            errors.append({'kind': 'MISSING_SOURCE_ENDPOINT', 'uid': uid}); continue
        if [digest(n['data']) for n in nodes] != [proof['native_record_sha256'], proof['parent_native_record_sha256']]:
            errors.append({'kind': 'COMPLETE_SOURCE_RANGE_CHANGED', 'uid': uid})
        if proof['world_identity_assertion'] is not False or not proof['no_identity_merges']:
            errors.append({'kind': 'PHYSICAL_RANGE_PROMOTED_IDENTITY', 'uid': uid})
        prior = proof.get('prior_assertion')
        if prior:
            originals = c.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?', tuple(prior[k] for k in ('subject_uid', 'object_uid', 'relation', 'source'))).fetchall()
            matching = [row for row in originals if digest(json.dumps({k: row[k] for k in row.keys() if k not in ('id', 'status', 'reason')}, sort_keys=True)) == prior['content_sha256']]
            if len(matching) != 1 or matching[0]['status'] != temporal.expected_assertion_status(dict(matching[0]), prior['status']):
                errors.append({'kind': 'OLD_DECLARATION_OR_REVIEW_OVERWRITTEN', 'uid': uid})
        texts = []
        for item in proof['source_witnesses']:
            row = c.execute('SELECT data FROM nodes WHERE uid=?', (item['uid'],)).fetchone()
            data = json.loads(row[0]); text = data.get(item['field']) or data.get('evidence_record', {}).get(item['field'])
            if digest(row[0]) != item['data_sha256'] or not text or item['statement'] not in text:
                errors.append({'kind': 'SOURCE_STATEMENT_NOT_IN_FROZEN_RECORD', 'uid': uid})
            texts.append(item['statement'])
        if op['relation'] == 'DESIGN_TYPE_OF':
            if proof.get('repair_kind') == 'COMPLETE_OWN_OBJECT_PHYSICAL_SCOPE':
                if proof.get('reviewed_physical_genus') not in ('airliner', 'aircraft', 'airplane', 'jet', 'twinjet', 'biplane', 'warplane') or proof['source_witnesses'][0]['uid'] != uid or proof['source_witnesses'][0]['field'] != 'description':
                    errors.append({'kind': 'OWN_OBJECT_PHYSICAL_SCOPE_NOT_BOUND', 'uid': uid})
            elif not prior or prior['relation'] != 'DESIGN_TYPE_OF' or prior['status'] != 'ACTIVE':
                errors.append({'kind': 'NOT_PRIOR_ADMITTED_WHOLE_DESIGN_SCOPE', 'uid': uid})
            elif matching:
                old_proof = json.loads(matching[0]['data'])['admission_basis']
                if old_proof.get('matched_explicit_genus') not in ('airliner', 'airliners') or old_proof.get('source_statement') != texts[0]:
                    errors.append({'kind': 'NOT_EXPLICIT_SUBJECT_AIRLINER_RANGE', 'uid': uid})
            if proof.get('repair_kind') == 'COMPLETE_OWN_OBJECT_PHYSICAL_SCOPE' and proof.get('reviewed_physical_genus') != 'airliner':
                if texts[1] != proof.get('reviewed_parent_definition'):
                    errors.append({'kind': 'GENERIC_AIRCRAFT_RANGE_NOT_CONFIRMED', 'uid': uid})
            elif 'fixed-wing powered aircraft' not in texts[1] or 'cargo or passengers in commercial service' not in texts[1]:
                errors.append({'kind': 'AIRLINER_PARENT_RANGE_NOT_CONFIRMED', 'uid': uid})
        elif op['relation'] == 'IS_A':
            if 'fixed-wing powered aircraft' not in texts[0] or not texts[1].startswith('an aircraft that has a fixed wing and is powered by propellers or jets'):
                errors.append({'kind': 'GENERIC_RANGE_DOES_NOT_ENTAIL_POWERED_FIXED_WING', 'uid': uid})
        elif op['relation'] == 'NATIVE_DESIGN_PARENT':
            if not prior or prior['status'] != 'SOURCE_SCOPE_REVIEW' or not any(word in texts[0].lower() for word in ('variant', 'version')) or len(texts) < 3:
                errors.append({'kind': 'DESIGN_FAMILY_SCOPE_UNCORROBORATED', 'uid': uid})
            if proof['source_witnesses'][2]['uid'].split(':')[-1] != parent.split(':')[-1]:
                errors.append({'kind': 'CORROBORATION_IS_NOT_THIS_FAMILY_ID', 'uid': uid})
        else:
            errors.append({'kind': 'UNREVIEWED_RELATION', 'uid': uid})
        if not preflight:
            if op['relation'] == 'IS_A':
                actual = c.execute("SELECT r.*, e.payload proof FROM edges r JOIN hierarchy_decisions h ON h.subject_uid=r.child_uid AND h.object_uid=r.parent_uid AND h.operation='link' AND h.evidence_id IN (SELECT value FROM json_each(r.provenance,'$.evidence_ids')) JOIN evidence e ON e.evidence_id=h.evidence_id WHERE r.child_uid=? AND r.parent_uid=? AND r.source=? AND r.relation=?", (uid, parent, SOURCE, op['relation'])).fetchall()
            else:
                actual = c.execute('SELECT r.*,e.payload proof FROM entity_relations r JOIN evidence e ON e.evidence_id=r.evidence_id WHERE r.subject_uid=? AND r.object_uid=? AND r.source=? AND r.relation=?', (uid, parent, SOURCE, op['relation'])).fetchall()
            if len(actual) != 1 or actual[0]['status'] != temporal.expected_assertion_status(dict(actual[0]), 'ACTIVE') or json.loads(actual[0]['proof']) != proof:
                errors.append({'kind': 'ACTUAL_NEW_ASSERTION_OR_EVIDENCE_DIFFER', 'uid': uid})
        counts[op['relation']] += 1
    for review in manifest.get('mapping_reviews', []):
        target = c.execute('SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?', (review['dataset'], review['class_id'])).fetchone()
        transition = temporal.mapping_transition(review)
        original_target = transition['before_target'] if transition else dict(target) if target else None
        if not target or digest(json.dumps(original_target, sort_keys=True)) != review['target_record_sha256']:
            errors.append({'kind': 'ORIGINAL_WORLD_TARGET_NOT_PRESERVED', 'dataset': review['dataset'], 'class_id': review['class_id']})
        for w in review['source_witnesses']:
            row = c.execute('SELECT data FROM nodes WHERE uid=?', (w['uid'],)).fetchone()
            data = json.loads(row[0]) if row else {}
            text = data.get(w['field']) or data.get('evidence_record', {}).get(w['field'])
            if not row or digest(row[0]) != w['data_sha256'] or text != w['statement']:
                errors.append({'kind': 'MAPPING_RANGE_WITNESS_CHANGED', 'uid': w['uid']})
        if not preflight:
            check = c.execute('SELECT * FROM dataset_mapping_checks WHERE dataset=? AND class_id=?', (review['dataset'], review['class_id'])).fetchone()
            expected_check = transition['after_check'] if transition else None
            if (not check or (dict(check) != expected_check if expected_check is not None else
                    check['status'] != 'ANNOTATION_SCOPE_REVIEW' or check['reason'] != review['reason'])):
                errors.append({'kind': 'MAPPING_SCOPE_REVIEW_NOT_APPLIED', 'class_id': review['class_id']})
            history = c.execute("SELECT count(*) FROM dataset_mapping_history WHERE dataset=? AND class_id=? AND namespace='world' AND decision='ANNOTATION_SCOPE_REVIEW'", (review['dataset'], review['class_id'])).fetchone()[0]
            if not history:
                errors.append({'kind': 'MAPPING_SCOPE_HISTORY_MISSING', 'class_id': review['class_id']})
    if not preflight:
        actual_count = sum(c.execute("SELECT count(*) FROM " + table + " WHERE source=? AND status='ACTIVE'", (SOURCE,)).fetchone()[0] for table in ('edges', 'entity_relations'))
        expected_active_count = temporal.expected_active_count(SOURCE, len(ops))
        if actual_count != expected_active_count:
            errors.append({'kind': 'EXTRA_OR_MISSING_NEW_SCOPE_ASSERTIONS', 'actual': actual_count})
        meta = {r['key']: json.loads(r['value']) for r in c.execute('SELECT * FROM metadata')}
        if meta.get('structure_regression_repairs', {}).get('manifest_sha256') != digest((inputs / 'structure_regression_repairs.json').read_bytes()):
            errors.append({'kind': 'NEW_MANIFEST_NOT_BOUND_TO_DATABASE'})
    report = {'schema': 'FINEATLAS_INDEPENDENT_STRUCTURE_REGRESSION_REPAIRS_AUDIT_V1', 'database': str(database), 'pass': not errors, 'preflight_only': preflight, 'operations': dict(counts), 'old_declarations_preserved': not any(e['kind'] == 'OLD_DECLARATION_OR_REVIEW_OVERWRITTEN' for e in errors), 'errors': errors}
    report.update(temporal.receipt_binding())
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'errors'})); c.close()
    return not errors

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--database', type=Path, required=True); p.add_argument('--inputs', type=Path, required=True); p.add_argument('--output', type=Path, required=True); p.add_argument('--preflight', action='store_true'); a = p.parse_args()
    raise SystemExit(0 if run(a.database, a.inputs, a.output, a.preflight) else 1)
