"""Exact later transitions supplement, rather than erase, the original SQL audit."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from collections import Counter

from structure_owned_scope_delivery_guard import require_owned_scope_receipt

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = 'structure_regression_temporal_parent_reference.json'


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def json_hash(value):
    return sha(json.dumps(value, sort_keys=True))


class TemporalContract:
    def __init__(self, database, inputs, output, connection):
        self.database = Path(database).resolve(); self.inputs = Path(inputs).resolve()
        self.output = Path(output); self.c = connection
        self.meta = {r['key']:json.loads(r['value']) for r in self.c.execute('SELECT * FROM metadata')}
        self.reference_path = self.inputs / REFERENCE
        reference = json.loads(self.reference_path.read_text())
        frozen = self.meta['structure_frozen_build_manifest']['inputs']
        parent = self.meta['structure_delta_resume_parent']['parent_revision']
        prior = json.loads(reference['audit_receipt_text'])
        complete = reference['completed_parent_build']
        original = json.loads((self.inputs / 'structure_regression_repairs.json').read_text())
        original_operations = [json.loads(line) for line in
            (self.inputs / original['operations_file']).read_text().splitlines() if line]
        if (reference.get('schema') != 'FINEATLAS_TEMPORAL_REGRESSION_PARENT_REFERENCE_V1'
                or reference.get('parent_revision') != parent or complete.get('revision') != parent
                or complete.get('pass') is not True or complete.get('complete') is not True
                or prior.get('pass') is not True or prior.get('preflight_only') is not False
                or prior.get('errors') != [] or prior.get('old_declarations_preserved') is not True
                or prior.get('schema') != 'FINEATLAS_INDEPENDENT_STRUCTURE_REGRESSION_REPAIRS_AUDIT_V1'
                or prior.get('operations') != dict(Counter(op['relation'] for op in original_operations))
                or len(complete.get('required_stages', [])) != 9
                or sha(reference['audit_receipt_text']) != reference['audit_receipt_sha256']
                or reference.get('original_auditor_sha256') != sha((ROOT / 'scripts/audit_structure_regression_repairs.py').read_bytes())
                or reference.get('original_manifest_sha256') != frozen.get('structure_regression_repairs.json')
                or frozen.get(REFERENCE) != sha(self.reference_path.read_bytes())):
            raise ValueError('Actual unchanged original parent SQL PASS and final frozen temporal reference required')
        manifest = json.loads((self.inputs / 'structure_owned_scope_repairs.json').read_text())
        raw = (self.inputs / manifest['operations_file']).read_bytes()
        if sha(raw) != manifest['operations_sha256']:
            raise ValueError('Later transition operations differ from the actual frozen input')
        operations = [json.loads(line) for line in raw.decode().splitlines() if line]
        self.reviews = [op for op in operations if op['op'] in ('review_bridge','review_typed_relation')]
        self.mappings = [op for op in operations if op['op'] in ('migrate_nominal_design_mapping','review_dataset_mapping')]
        if len({(op['dataset'],str(op['class_id'])) for op in self.mappings}) != len(self.mappings):
            raise ValueError('Duplicate temporal mapping permissions')
        self.owned_report = self.output.with_name(self.output.stem + '-owned-actual.json')

    def run_owned_actual_audit(self):
        subprocess.run([sys.executable,'-B',str(ROOT / 'scripts/audit_owned_scope_repairs.py'),
            '--database',str(self.database),'--inputs',str(self.inputs),'--output',str(self.owned_report)],check=True)
        require_owned_scope_receipt(self.owned_report,self.database,self.inputs,
                                    self.meta['database_revision'],ROOT)

    def expected_assertion_status(self, current, original_status):
        # A JOIN-generated proof column is not an original source row field.
        current = {key:value for key,value in current.items() if key != 'proof'}
        permissions = [op for op in self.reviews if op['op'] == 'review_typed_relation'
                       and op['before_assertion'].get('id') == current.get('id')
                       and set(op['before_assertion']) == set(current)]
        if not permissions:
            return original_status
        if len(permissions) != 1:
            raise ValueError('Ambiguous later source assertion review')
        op = permissions[0]; before = op['before_assertion']
        after = dict(before); after['status'] = 'SOURCE_SCOPE_REVIEW'
        if (op.get('after_status') != 'SOURCE_SCOPE_REVIEW' or before['status'] != original_status
                or current != after or op['content_sha256'] != json_hash({k:v for k,v in before.items() if k not in ('id','status','reason')})):
            raise ValueError('Later review permission does not exactly preserve the original raw assertion')
        rows = self.c.execute("SELECT before_json,after_json,evidence FROM usability_changes WHERE stage='owned_scope_repairs' AND object_type='typed_scope_review' AND object_id=?",(str(before['id']),)).fetchall()
        matches = [r for r in rows if json.loads(r['before_json']) == before
                   and json.loads(r['after_json']) == {'status':'SOURCE_SCOPE_REVIEW'}
                   and json.loads(r['evidence']) == op['proof']]
        if len(matches) != 1:
            raise ValueError('Actual exact later assertion review history is missing')
        return 'SOURCE_SCOPE_REVIEW'

    def mapping_transition(self, review):
        matches = [op for op in self.mappings if (op['dataset'],str(op['class_id'])) ==
                   (review['dataset'],str(review['class_id']))]
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError('Ambiguous mapping migration')
        op = matches[0]
        if json_hash(op['before_target']) != review['target_record_sha256']:
            raise ValueError('Later mapping migration is not the original reviewed target')
        if (op['before_check'].get('status') != 'ANNOTATION_SCOPE_REVIEW'
                or op['before_check'].get('reason') != review['reason']):
            raise ValueError('Later mapping migration did not preserve the actual original review disposition')
        target = self.c.execute('SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?',
                                (op['dataset'],op['class_id'])).fetchone()
        check = self.c.execute('SELECT * FROM dataset_mapping_checks WHERE dataset=? AND class_id=?',
                               (op['dataset'],op['class_id'])).fetchone()
        if not target or not check or dict(target) != op['after_target'] or dict(check) != op['after_check']:
            raise ValueError('Final mapping/check differs from the exact frozen migration')
        rows = self.c.execute("SELECT before_json,after_json,evidence FROM usability_changes WHERE stage='owned_scope_repairs' AND object_type='nominal_design_mapping' AND object_id=?",
                              (op['dataset']+':'+str(op['class_id']),)).fetchall()
        before = {'target':op['before_target'],'check':op['before_check']}
        after = {'target':op['after_target'],'check':op['after_check']}
        if len([r for r in rows if json.loads(r['before_json']) == before and
                json.loads(r['after_json']) == after and json.loads(r['evidence']) == op['proof']]) != 1:
            raise ValueError('Actual precise later nominal mapping history is absent')
        return op

    def expected_active_count(self, source, old_count):
        withdrawals = [op for op in self.reviews if op['op'] == 'review_typed_relation'
                       and op['before_assertion']['source'] == source
                       and op['before_assertion']['status'] == 'ACTIVE']
        for op in withdrawals:
            row = self.c.execute('SELECT * FROM entity_relations WHERE id=?',(op['before_assertion']['id'],)).fetchone()
            if not row or self.expected_assertion_status(dict(row),'ACTIVE') != 'SOURCE_SCOPE_REVIEW':
                raise ValueError('Frozen withdrawal not actually applied')
        total = sum(self.c.execute('SELECT count(*) FROM '+table+' WHERE source=?',(source,)).fetchone()[0]
                    for table in ('edges','entity_relations'))
        if total != old_count:
            raise ValueError('Later transition lost or added an original repair assertion')
        return old_count - len(withdrawals)

    def receipt_binding(self):
        return {'temporal_contract':'FINEATLAS_EXACT_LATER_SCOPE_TRANSITIONS_V1',
                'database_revision':self.meta['database_revision'],
                'temporal_parent_reference_sha256':sha(self.reference_path.read_bytes()),
                'owned_manifest_sha256':sha((self.inputs / 'structure_owned_scope_repairs.json').read_bytes()),
                'owned_actual_audit':{'path':str(self.owned_report.resolve()),'sha256':sha(self.owned_report.read_bytes())},
                'original_contract_fully_checked':True,
                'later_mapping_permissions':len(self.mappings),'later_assertion_permissions':len(self.reviews)}


def require_temporal_receipt(report, database, inputs, revision):
    report, database, inputs = Path(report), Path(database), Path(inputs)
    value = json.loads(report.read_text())
    if (value.get('pass') is not True or value.get('preflight_only') is not False
            or value.get('errors') != [] or value.get('database_revision') != revision
            or Path(value.get('database','')).resolve() != database.resolve()
            or value.get('original_contract_fully_checked') is not True
            or value.get('temporal_contract') != 'FINEATLAS_EXACT_LATER_SCOPE_TRANSITIONS_V1'
            or value.get('temporal_parent_reference_sha256') != sha((inputs / REFERENCE).read_bytes())
            or value.get('owned_manifest_sha256') != sha((inputs / 'structure_owned_scope_repairs.json').read_bytes())):
        raise ValueError('Complete actual temporal regression SQL contract evidence required')
    owned = value.get('owned_actual_audit',{})
    if sha(Path(owned.get('path','/MISSING')).read_bytes()) != owned.get('sha256'):
        raise ValueError('Actual independent later-stage audit evidence changed')
    require_owned_scope_receipt(owned['path'],database,inputs,revision,ROOT)
    return value
