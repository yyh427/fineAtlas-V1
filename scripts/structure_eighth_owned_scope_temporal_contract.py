"""Exact later grain reviews preserve the full earlier 1194 SOURCE audit."""
import hashlib
import json
from pathlib import Path
import sqlite3
from structure_complete_owned_type_delivery_guard import require_complete_type_receipt
from structure_owned_scope_delivery_guard import require_owned_scope_receipt as require_original_receipt

ROOT=Path(__file__).resolve().parents[1]
sha=lambda x:hashlib.sha256(x.encode()if isinstance(x,str)else x).hexdigest()


def verify_exact_retired_owned_link(c,original,review,role):
    before=review['before_assertion'];current=c.execute('SELECT *FROM entity_relations WHERE id=?',(before['id'],)).fetchone()
    if (review['op']!='review_typed_relation' or role['op']!='correct_role'
            or review['uid']!=original['uid']or review['parent']!=original['parent']or review['relation']!=original['relation']
            or role['uid']!=original['uid']or before['subject_uid']!=original['uid']or before['object_uid']!=original['parent']
            or before['relation']!=original['relation']or before['source']!=original['source']
            or before['status']!='ACTIVE'or review['after_status']!='SOURCE_SCOPE_REVIEW'
            or json.loads(before['data']).get('admission_basis')!=original['proof']
            or sha(json.dumps({k:v for k,v in before.items()if k not in('id','status','reason')},sort_keys=True))!=review['content_sha256']
            or not current or dict(current)!={**before,'status':'SOURCE_SCOPE_REVIEW'}):
        raise ValueError('Later SOURCE review is not the complete exact earlier link')
    if (role['after_profile']['node_kind']!='UNKNOWN'or role['after_normalization_role']['status']!='REVIEW'
            or json.loads(role['after_profile']['attributes']).get('allowed_views')!=[]
            or json.loads(role['after_profile']['attributes']).get('role_status')!='REVIEW'
            or not role['before_profile']or role['before_profile']['node_kind']not in('MODEL','MODEL_FAMILY')):
        raise ValueError('Later unresolved grain must retain exact reviewed certainty')
    for table,expected in [('node_profiles',role['after_profile']),('normalization_roles',role['after_normalization_role'])]:
        row=c.execute('SELECT *FROM '+table+' WHERE uid=?',(original['uid'],)).fetchone()
        if not row or dict(row)!=expected:raise ValueError('Current canonical role differs from frozen later source scope')
    old={'profile':role['before_profile'],'normalization_role':role['before_normalization_role']};after={'profile':role['after_profile'],'normalization_role':role['after_normalization_role']}
    for kind,identifier,a,b,p in [('role_source_adjudication',original['uid'],old,after,role['proof']),('typed_scope_review',str(before['id']),before,{'status':'SOURCE_SCOPE_REVIEW'},review['proof'])]:
        rows=c.execute("SELECT *FROM usability_changes WHERE stage='complete_owned_type_repairs'AND object_type=?AND object_id=?",(kind,identifier)).fetchall()
        if len([r for r in rows if json.loads(r['before_json'])==a and json.loads(r['after_json'])==b and json.loads(r['evidence'])==p])!=1:raise ValueError('Precise later SOURCE role/review history is absent')
    refs=c.execute("SELECT *FROM entity_relations WHERE subject_uid=?AND source=?AND relation='SOURCE_PHYSICAL_CLASS_REFERENCE'",(original['uid'],review['source'])).fetchall()
    matches=[r for r in refs if r['status']=='SOURCE_DECLARED'and json.loads(r['data']).get('admission_basis',{}).get('original_assertion')==before and json.loads(r['data']).get('navigation_allowed')is False and json.loads(r['data']).get('allowed_views')==[]]
    if len(matches)!=1:raise ValueError('Reviewed physical source fact must survive as one exact non-navigation reference')
    return {'uid':original['uid'],'parent':original['parent'],'relation':original['relation'],'id':before['id'],'content_sha256':review['content_sha256'],'historical_role':role['before_profile']['node_kind'],'current_role':'UNKNOWN','current_status':'SOURCE_SCOPE_REVIEW','retained_reference_id':matches[0]['id']}


class EighthOwnedTemporalContract:
    def __init__(self,c,database,inputs,actual_audit,fixture_only=False):
        self.c=c;self.database=Path(database);self.inputs=Path(inputs);self.checked=[];self.metadata={r['key']:json.loads(r['value'])for r in c.execute('SELECT *FROM metadata')};self.actual=Path(actual_audit)
        self.mfpath=self.inputs/'structure_complete_owned_type_repairs.json';self.mf=json.loads(self.mfpath.read_bytes());raw=(self.inputs/self.mf['operations_file']).read_bytes();self.operations=[json.loads(l)for l in raw.decode().splitlines()if l]
        if sha(raw)!=self.mf['operations_sha256']:raise ValueError('Exact later operations changed')
        if not fixture_only:require_complete_type_receipt(self.actual,self.database,self.inputs,self.metadata['database_revision'],ROOT)
        else:
            report=json.loads(self.actual.read_bytes())
            if report.get('pass')is not True or report.get('candidate_acceptance')is not False or report.get('database_revision')!=self.metadata['database_revision']or Path(report.get('database','')).resolve()!=self.database.resolve()or report.get('operations_sha256')!=sha(raw):raise ValueError('Real fixture-only Source8 audit evidence required')
    def transition(self,original):
        if original['op']!='link':return None
        reviews=[o for o in self.operations if o['op']=='review_typed_relation'and(o['uid'],o['parent'],o['relation'],o['before_assertion']['source'])==(original['uid'],original['parent'],original['relation'],original['source'])]
        if not reviews:return None
        roles=[o for o in self.operations if o['op']=='correct_role'and o['uid']==original['uid']]
        if len(reviews)!=1 or len(roles)!=1:raise ValueError('Later SOURCE transition is ambiguous')
        result=verify_exact_retired_owned_link(self.c,original,reviews[0],roles[0]);self.checked.append(result);return result
    def binding(self):
        return {'eighth_temporal_owned_scope_contract':'FINEATLAS_EXACT_LATER_OWNED_SCOPE_GRAIN_TRANSITIONS_V1','original_owned_scope_checks_preserved':True,'complete_type_manifest_sha256':sha(self.mfpath.read_bytes()),'complete_type_actual_audit':{'path':str(self.actual.resolve()),'sha256':sha(self.actual.read_bytes())},'later_exact_owned_link_transitions':self.checked}


def require_temporal_eighth_owned_scope_receipt(report,database,inputs,revision,code_root):
    report,database,inputs,code_root=map(Path,(report,database,inputs,code_root));value=require_original_receipt(report,database,inputs,revision,code_root)
    if value.get('eighth_temporal_owned_scope_contract')!='FINEATLAS_EXACT_LATER_OWNED_SCOPE_GRAIN_TRANSITIONS_V1'or value.get('original_owned_scope_checks_preserved')is not True:raise ValueError('Entire earlier SOURCE7 audit and exact later scope transition must pass')
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)as c:meta={k:json.loads(v)for k,v in c.execute('SELECT *FROM metadata')}
    for name in('audit_temporal_eighth_owned_scope_repairs.py','structure_eighth_owned_scope_temporal_contract.py'):
        if meta['structure_frozen_build_manifest']['code'].get('scripts/'+name)!=sha((code_root/'scripts'/name).read_bytes()):raise ValueError('Current owned temporal implementations must be frozen')
    if value.get('original_owned_auditor_sha256')!=sha((code_root/'scripts/audit_owned_scope_repairs.py').read_bytes()):raise ValueError('Original entire SOURCE7 auditor bytes changed')
    e=value['complete_type_actual_audit'];p=Path(e['path'])
    if sha(p.read_bytes())!=e['sha256']:raise ValueError('Actual later complete SOURCE audit changed')
    require_complete_type_receipt(p,database,inputs,revision,code_root)
    mfpath=inputs/'structure_complete_owned_type_repairs.json';mf=json.loads(mfpath.read_bytes())
    if value.get('complete_type_manifest_sha256')!=sha(mfpath.read_bytes()):raise ValueError('Current temporal report identifies another later input')
    later=[json.loads(line)for line in(inputs/mf['operations_file']).read_text().splitlines()if line]
    oldmf=json.loads((inputs/'structure_owned_scope_repairs.json').read_text());originals=[json.loads(line)for line in(inputs/oldmf['operations_file']).read_text().splitlines()if line]
    expected=[]
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)as c:
        c.row_factory=sqlite3.Row
        for original in originals:
            if original['op']!='link':continue
            reviews=[o for o in later if o['op']=='review_typed_relation'and(o['uid'],o['parent'],o['relation'],o['before_assertion']['source'])==(original['uid'],original['parent'],original['relation'],original['source'])]
            if not reviews:continue
            roles=[o for o in later if o['op']=='correct_role'and o['uid']==original['uid']]
            if len(reviews)!=1 or len(roles)!=1:raise ValueError('Actual SOURCE transition permission inventory is ambiguous')
            expected.append(verify_exact_retired_owned_link(c,original,reviews[0],roles[0]))
    if value.get('later_exact_owned_link_transitions')!=expected:raise ValueError('Every precise old SOURCE7 later transition must be fully checked')
    return value


def run_eighth_owned_actual_audits(contract):
    """Explicitly execute current auditors; do not patch historical contracts."""
    import subprocess
    import sys
    if contract.primary_snapshots_dir is None or not contract.primary_snapshots_dir.is_dir():raise ValueError('Explicit verified primary snapshots are required')
    contract.eighth_report=contract.output.with_name(contract.output.stem+'-complete-type-actual.json')
    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/audit_complete_owned_type_repairs.py'),'--database',str(contract.database),'--inputs',str(contract.inputs),'--output',str(contract.eighth_report)],check=True)
    require_complete_type_receipt(contract.eighth_report,contract.database,contract.inputs,contract.meta['database_revision'],ROOT)
    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/audit_temporal_eighth_owned_scope_repairs.py'),'--database',str(contract.database),'--inputs',str(contract.inputs),'--output',str(contract.owned_report),'--primary-snapshots-dir',str(contract.primary_snapshots_dir),'--complete-owned-audit',str(contract.eighth_report)],check=True)
    require_temporal_eighth_owned_scope_receipt(contract.owned_report,contract.database,contract.inputs,contract.meta['database_revision'],ROOT)


from structure_regression_temporal_contract import TemporalContract

class EighthRegressionTemporalContract(TemporalContract):
    def run_owned_actual_audit(self):run_eighth_owned_actual_audits(self)
    def receipt_binding(self):
        value=super().receipt_binding();value.update(eighth_regression_temporal_contract='FINEATLAS_EXACT_CURRENT_OWNED_SCOPE_EXECUTOR_V1',original_regression_scope_checks_preserved=True,complete_type_actual_audit={'path':str(self.eighth_report.resolve()),'sha256':sha(self.eighth_report.read_bytes())});return value


def require_temporal_eighth_regression_receipt(report_path,database,inputs,revision,code_root=ROOT):
    """Keep all 816 checks and explicitly verify the current SOURCE executors."""
    from structure_regression_temporal_contract import require_temporal_receipt
    report_path,database,inputs,code_root=map(Path,(report_path,database,inputs,code_root))
    value=require_temporal_receipt(report_path,database,inputs,revision)
    if (value.get('eighth_regression_temporal_contract')!='FINEATLAS_EXACT_CURRENT_OWNED_SCOPE_EXECUTOR_V1'
            or value.get('original_regression_scope_checks_preserved')is not True):raise ValueError('Entire SOURCE1 contract with the current owned executor is required')
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)as c:meta={k:json.loads(v)for k,v in c.execute('SELECT *FROM metadata')}
    for name in('audit_temporal_eighth_structure_regression_repairs.py','structure_eighth_owned_scope_temporal_contract.py'):
        if meta['structure_frozen_build_manifest']['code'].get('scripts/'+name)!=sha((code_root/'scripts'/name).read_bytes()):raise ValueError('Actual eighth SOURCE1 implementations must be frozen')
    evidence=value.get('complete_type_actual_audit')or{};path=Path(evidence.get('path',''))
    if not path.is_file()or sha(path.read_bytes())!=evidence.get('sha256'):raise ValueError('Current SOURCE8 evidence changed')
    require_complete_type_receipt(path,database,inputs,revision,code_root)
    owned=value['owned_actual_audit'];owned_path=Path(owned['path'])
    if sha(owned_path.read_bytes())!=owned['sha256']:raise ValueError('Current temporal SOURCE7 evidence changed')
    require_temporal_eighth_owned_scope_receipt(owned_path,database,inputs,revision,code_root)
    return value
