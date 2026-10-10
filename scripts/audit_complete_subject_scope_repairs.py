#!/usr/bin/env python3
"""Independent SQL source/range/history audit, without importing the builder rules."""
from __future__ import annotations
import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import re
import sqlite3

SOURCE = 'Reviewed complete source subject and physical type recovery'


def sha(raw): return hashlib.sha256(raw.encode() if isinstance(raw,str) else raw).hexdigest()


def role(c,n):
    p=c.execute('SELECT node_kind FROM node_profiles WHERE uid=?',(n['uid'],)).fetchone()
    if p and p[0]:return p[0]
    rank=n['rank'].lower()
    return 'MODEL' if rank in ('model','product_model','aircraft_model','vehicle_model') else 'MODEL_FAMILY' if rank in ('model_family','series') else 'INSTANCE' if rank=='instance' else 'CONFIGURATION' if rank in ('model_year','model_year_configuration','configuration') else 'CLASS'


def root_reachable(c,uid):
    queue=deque([uid]);seen=set()
    while queue:
        key=queue.popleft()
        if key=='wordnet31:00001740-n':return True
        if key in seen:continue
        seen.add(key)
        if len(seen)>10000:return False
        queue.extend(r[0] for r in c.execute("SELECT DISTINCT parent_uid FROM edges WHERE child_uid IN (SELECT uid FROM nodes WHERE component_id=(SELECT component_id FROM nodes WHERE uid=?)) AND ((status IN ('ACTIVE','BACKBONE_ACTIVE') AND relation='IS_A') OR (status='TYPED_ACTIVE' AND relation IN ('TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT')))",(key,)))
    return False


def run(database,inputs,output,preflight=False):
    database=database.resolve();manifest_path=inputs/'structure_complete_subject_scope_repairs.json';manifest=json.loads(manifest_path.read_text());raw=(inputs/manifest['operations_file']).read_bytes();ops=[json.loads(x) for x in raw.decode().splitlines() if x]
    c=sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row;errors=[]
    if sha(raw)!=manifest['operations_sha256'] or type(manifest['operation_count']) is not int or len(ops)!=manifest['operation_count']:
        errors.append({'kind':'INPUT_NOT_BOUND'})
    if len({(x['uid'],x['parent'],x['relation']) for x in ops})!=len(ops):errors.append({'kind':'DUPLICATE_SEMANTIC_TRIPLE'})
    parent_routes={}
    activation_uids={x['uid'] for x in manifest.get('source_class_activations',[])}
    for activation in manifest.get('source_class_activations',[]):
        n=c.execute('SELECT * FROM nodes WHERE uid=?',(activation['uid'],)).fetchone();data=json.loads(n['data']) if n else {}
        if not n or sha(n['data'])!=activation['native_record_sha256'] or data.get('definition')!=activation['statement'] or 'string instruments, or chordophones, are musical instruments that produce sound from vibrating strings' not in activation['statement'] or role(c,n)!='CLASS' or n['visibility']!=(activation['before_visibility'] if preflight else 'ACTIVE'):
            errors.append({'kind':'SOURCE_CLASS_ACTIVATION_NOT_BOUND','uid':activation['uid']})
        if not preflight and not c.execute("SELECT 1 FROM usability_changes WHERE stage='complete_subject_scope_repairs' AND object_type='source_visibility' AND object_id=?",(activation['uid'],)).fetchone():
            errors.append({'kind':'ACTIVATION_HISTORY_MISSING','uid':activation['uid']})
    for op in ops:
        uid=op['uid'];proof=op['proof'];n=c.execute('SELECT * FROM nodes WHERE uid=?',(uid,)).fetchone();p=c.execute('SELECT * FROM nodes WHERE uid=?',(op['parent'],)).fetchone()
        if not n or not p:errors.append({'kind':'MISSING_ENDPOINT','uid':uid});continue
        if sha(n['data'])!=proof['native_record_sha256'] or sha(p['data'])!=proof['parent_native_record_sha256']:
            errors.append({'kind':'WHOLE_RANGE_CHANGED','uid':uid})
        if proof['world_identity_assertion'] is not False or not proof['no_identity_merges']:
            errors.append({'kind':'TYPE_PROMOTED_TO_IDENTITY','uid':uid})
        expected={'CLASS':'IS_A','MODEL':'DESIGN_TYPE_OF','MODEL_FAMILY':'DESIGN_TYPE_OF','INSTANCE':'INSTANCE_OF'}.get(role(c,n))
        if expected!=op['relation'] or role(c,p)!='CLASS' or (n['visibility']!='ACTIVE' and not (preflight and uid in activation_uids and n['visibility']=='SOURCE_ONLY')) or (p['visibility']!='ACTIVE' and not (preflight and op['parent'] in activation_uids and p['visibility']=='SOURCE_ONLY')):
            errors.append({'kind':'ROLE_OR_VISIBILITY_INCOMPATIBLE','uid':uid})
        witness=proof['source_witnesses'][0];owned=json.loads(n['data'])
        if witness['uid']!=uid or witness['field'] not in ('description','definition') or owned.get(witness['field'])!=witness['statement']:
            errors.append({'kind':'NOT_OWNED_COMPLETE_SUBJECT_STATEMENT','uid':uid})
        for w in proof['source_witnesses']:
            r=c.execute('SELECT data FROM nodes WHERE uid=?',(w['uid'],)).fetchone();d=json.loads(r[0]) if r else {};text=d.get(w['field']) or d.get('evidence_record',{}).get(w['field'])
            if not r or sha(r[0])!=w['data_sha256'] or text!=w['statement']:
                errors.append({'kind':'SOURCE_WITNESS_CHANGED','uid':uid})
        statement=witness['statement'];genus=proof['reviewed_physical_genus']
        if not re.search(r'\b'+re.escape(genus)+r'\b',statement,re.I):errors.append({'kind':'GENUS_NOT_IN_OWN_SUBJECT','uid':uid})
        if role(c,n)=='CLASS' and proof['reviewed_rule']=='UNIVERSAL_OWN_CLASS_DEFINITION' and (not re.match(r'^(?:A|An)\s+',statement) or not re.search(r'\bis\b',statement)):
            errors.append({'kind':'CLASS_GRAIN_NOT_UNIVERSAL_SOURCE_DEFINITION','uid':uid})
        if role(c,n)=='MODEL_FAMILY' and not re.search(r'\b(?:family|series|line|range)\b',statement,re.I):errors.append({'kind':'OWN_FAMILY_SCOPE_NOT_DECLARED','uid':uid})
        # Specific native senses are independently checked against the complete
        # retained parent. They deliberately exclude narrower homonyms.
        parent_statement=proof['source_witnesses'][1]['statement']
        if genus.casefold() in ('biplane','biplanes') and 'two main wings stacked one above the other' not in parent_statement:
            errors.append({'kind':'BIPLANE_SCOPE_CHANGED','uid':uid})
        if genus.casefold() in ('monoplane','monoplanes') and 'one main lifting surface' not in parent_statement:
            errors.append({'kind':'MONOPLANE_SCOPE_NARROWED_TO_POWERED','uid':uid})
        if genus.casefold() in ('helicopter','helicopters') and 'powered rotary wings' not in parent_statement:
            errors.append({'kind':'HELICOPTER_NATIVE_SCOPE_CHANGED','uid':uid})
        if genus.casefold() in ('microprocessor','microprocessors') and ('single integrated circuit' not in parent_statement or 'small number of ICs' not in parent_statement):
            errors.append({'kind':'MICROPROCESSOR_SCOPE_NARROWED_TO_SINGLE_CHIP','uid':uid})
        if genus.casefold()=='camera' and 'capture and store images and videos' not in parent_statement:
            errors.append({'kind':'CAMERA_SCOPE_NARROWED_TO_PHOTO_OR_TV','uid':uid})
        for k,table,fields in [('prior_assertion','entity_relations',('subject_uid','object_uid')),('prior_edge','edges',('child_uid','parent_uid'))]:
            prior=proof.get(k)
            if prior:
                rows=c.execute('SELECT * FROM '+table+' WHERE '+fields[0]+'=? AND '+fields[1]+'=? AND relation=? AND source=?',(prior[fields[0]],prior[fields[1]],prior['relation'],prior['source'])).fetchall()
                if not any(sha(json.dumps({key:r[key] for key in r.keys() if key not in ('id','status','reason')},sort_keys=True))==prior['content_sha256'] and r['status']==prior['status'] for r in rows):
                    errors.append({'kind':'ORIGINAL_SOURCE_ASSERTION_OR_REVIEW_OVERWRITTEN','uid':uid})
        if not preflight:
            if op['relation']=='IS_A':
                rows=c.execute("SELECT r.status,e.payload FROM edges r JOIN hierarchy_decisions h ON h.subject_uid=r.child_uid AND h.object_uid=r.parent_uid AND h.operation='link' AND h.evidence_id IN (SELECT value FROM json_each(r.provenance,'$.evidence_ids')) JOIN evidence e ON e.evidence_id=h.evidence_id WHERE r.child_uid=? AND r.parent_uid=? AND r.source=? AND r.relation=?",(uid,op['parent'],SOURCE,op['relation'])).fetchall()
            else:
                rows=c.execute('SELECT r.status,e.payload FROM entity_relations r JOIN evidence e ON e.evidence_id=r.evidence_id WHERE r.subject_uid=? AND r.object_uid=? AND r.source=? AND r.relation=?',(uid,op['parent'],SOURCE,op['relation'])).fetchall()
            if len(rows)!=1 or rows[0][0]!='ACTIVE' or json.loads(rows[0][1])!=proof:errors.append({'kind':'ACTUAL_APPEND_OR_EVIDENCE_DIFFERS','uid':uid})
            if op['parent'] not in parent_routes:parent_routes[op['parent']]=root_reachable(c,op['parent'])
            if not parent_routes[op['parent']]:errors.append({'kind':'SOURCE_TYPE_PARENT_NOT_ROOT_REACHABLE','uid':uid,'parent':op['parent']})
    metadata={r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM metadata')}
    if not preflight:
        frozen=metadata.get('structure_frozen_build_manifest',{}).get('inputs',{})
        for name in (manifest_path.name,manifest['operations_file']):
            if frozen.get(name)!=sha((inputs/name).read_bytes()):errors.append({'kind':'FROZEN_INPUT_NOT_BOUND','name':name})
        meta=metadata.get('complete_subject_scope_repairs',{})
        if meta.get('manifest_sha256')!=sha(manifest_path.read_bytes()) or meta.get('operation_count')!=len(ops):errors.append({'kind':'APPLY_MANIFEST_NOT_BOUND'})
        actual=sum(c.execute('SELECT count(*) FROM '+t+" WHERE source=? AND status='ACTIVE'",(SOURCE,)).fetchone()[0] for t in ('edges','entity_relations'))
        if actual!=len(ops):errors.append({'kind':'ACTUAL_APPEND_COUNT_DIFFERS','count':actual})
    report={'schema':'FINEATLAS_INDEPENDENT_COMPLETE_SUBJECT_SCOPE_AUDIT_V1','database':str(database),'database_revision':metadata.get('database_revision'),'release':metadata.get('release'),'pass':not errors,'preflight_only':preflight,'manifest_sha256':sha(manifest_path.read_bytes()),'operations_sha256':sha(raw),'operation_count':len(ops),'operations':dict(Counter(o['relation'] for o in ops)),'added_assertions':len(ops),'new_semantic_links':len(ops),'withdrawn_assertions':0,'source_class_activations':len(activation_uids),'parent_root_reachability':parent_routes,'errors':errors}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('errors','parent_root_reachability')}));c.close();return not errors


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args();raise SystemExit(0 if run(a.database,a.inputs,a.output,a.preflight) else 1)
