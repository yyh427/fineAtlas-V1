#!/usr/bin/env python3
"""Check documentary scopes, preserved identities and actual hierarchy using SQL."""
from __future__ import annotations
import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import re
import sqlite3

INPUT_NAME='structure_primary_aircraft_family_repairs.json'
SOURCE='Primary documented aircraft design-family scope'

def sha(value):return hashlib.sha256(value.encode()if isinstance(value,str)else value).hexdigest()
def content(r):return sha(json.dumps({k:r[k]for k in r.keys()if k not in('id','status','reason')},sort_keys=True))
def name(text):return ' '.join(re.findall(r'[a-z0-9]+',text.casefold()))
def role(c,n):
 p=c.execute('SELECT node_kind FROM node_profiles WHERE uid=?',(n['uid'],)).fetchone()
 return p[0]if p and p[0]else {'model':'MODEL','model_family':'MODEL_FAMILY','series':'MODEL_FAMILY','model_year':'CONFIGURATION','configuration':'CONFIGURATION'}.get(n['rank'].lower(),'CLASS')

def canonical_parents(c, component):
    """Own SQL admission, independent from builder contracts and cached DAG."""
    for peer in c.execute('SELECT * FROM nodes WHERE component_id=?AND visibility="ACTIVE"',(component,)):
        cr=role(c,peer)
        for r in c.execute("SELECT * FROM entity_relations WHERE subject_uid=?AND status='ACTIVE'AND relation IN('NATIVE_DESIGN_PARENT','DESIGN_TYPE_OF','SERIES_MEMBER_OF')",(peer['uid'],)):
            parent=c.execute('SELECT * FROM nodes WHERE uid=?',(r['object_uid'],)).fetchone()
            if not parent or parent['visibility']!='ACTIVE':continue
            pr=role(c,parent)
            allowed=(cr in('MODEL','MODEL_FAMILY')and pr in('MODEL','MODEL_FAMILY'))if r['relation']=='NATIVE_DESIGN_PARENT'else(cr in('MODEL','MODEL_FAMILY')and pr=='CLASS')if r['relation']=='DESIGN_TYPE_OF'else(cr=='MODEL'and pr=='MODEL_FAMILY')
            if allowed:yield parent['component_id'],[peer['uid'],r['relation'],parent['uid']]
        if cr=='CLASS':
            for r in c.execute("SELECT parent_uid FROM edges WHERE child_uid=?AND status IN('ACTIVE','BACKBONE_ACTIVE')AND relation='IS_A'",(peer['uid'],)):
                parent=c.execute('SELECT * FROM nodes WHERE uid=?',(r[0],)).fetchone()
                if parent and parent['visibility']=='ACTIVE'and role(c,parent)=='CLASS':yield parent['component_id'],[peer['uid'],'IS_A',parent['uid']]

def component_route(c, uid, target_uid):
    """Independent BFS over raw statements and canonical peers, not index cache."""
    target=c.execute('SELECT component_id FROM nodes WHERE uid=?',(target_uid,)).fetchone();start=c.execute('SELECT component_id FROM nodes WHERE uid=?',(uid,)).fetchone()
    if not target or not start:return None
    queue=deque([(start[0],[uid])]);seen=set()
    while queue:
        component,path=queue.popleft()
        if component==target[0]:return path
        if component in seen:continue
        seen.add(component)
        for parent,steps in canonical_parents(c,component):queue.append((parent,path+steps))
    return None

def run(database,inputs,output,preflight=False,primary_snapshots_dir=None,primary_source_registry=None):
 database=database.resolve();path=inputs/INPUT_NAME;manifest=json.loads(path.read_text());raw=(inputs/manifest['operations_file']).read_bytes();ops=[json.loads(l)for l in raw.decode().splitlines()if l]
 registry_path=primary_source_registry or inputs/'structure_primary_source_snapshots.json'
 registry=json.loads(registry_path.read_text())if registry_path.is_file()else {}
 snapshots=primary_snapshots_dir.resolve()if primary_snapshots_dir is not None else None
 c=sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row;errors=[];checked_docs={};links=set();components=set()
 if sha(raw)!=manifest['operations_sha256']or type(manifest['operation_count'])is not int or len(ops)!=manifest['operation_count']or len({(x['uid'],x['parent'],x['relation'])for x in ops})!=len(ops):errors.append({'kind':'INPUT_BINDING_OR_UNIQUENESS_FAILED'})
 for op in ops:
  uid=op['uid'];proof=op['proof'];fact=manifest['reviewed_scope_facts'][proof['primary_scope_fact_id']]
  n=c.execute('SELECT * FROM nodes WHERE uid=?',(uid,)).fetchone();p=c.execute('SELECT * FROM nodes WHERE uid=?',(op['parent'],)).fetchone()
  if not n or not p:errors.append({'kind':'ENDPOINT_MISSING','uid':uid});continue
  if sha(n['data'])!=proof['native_record_sha256']or sha(p['data'])!=proof['parent_native_record_sha256']or n['visibility']!='ACTIVE'or p['visibility']!='ACTIVE':errors.append({'kind':'OWN_SOURCE_RANGE_OR_VISIBILITY_CHANGED','uid':uid})
  if role(c,n)not in('MODEL','MODEL_FAMILY')or role(c,p)not in(('CLASS',)if op['relation']=='DESIGN_TYPE_OF'else('MODEL','MODEL_FAMILY'))or role(c,p)!=fact['parent_role']or role(c,n)not in fact['allowed_child_roles']or op['relation']not in('NATIVE_DESIGN_PARENT','DESIGN_TYPE_OF','SOURCE_DESIGN_DERIVATION_REFERENCE') or n['component_id']==p['component_id']:errors.append({'kind':'NOMINAL_GRAIN_OR_DIRECTION_INVALID','uid':uid})
  if name(n['label'])not in[name(x)for x in fact['child_nominal_names']]or name(p['label'])!=name(fact['parent_nominal_name']):errors.append({'kind':'DOCUMENTED_NOMINAL_OBJECT_DOES_NOT_MATCH_OWN_SOURCE_NAME','uid':uid})
  if proof.get('primary_scope_fact')!=fact or proof.get('world_identity_assertion')is not False or proof.get('dataset_mapping_promotion')is not False or proof.get('no_identity_merges')is not True:errors.append({'kind':'DIRECTION_PROMOTED_TO_IDENTITY_OR_SCOPE_FACT_CHANGED','uid':uid})
  if proof.get('primary_documents')!={v['document_id']:manifest['primary_documents'][v['document_id']]for v in fact['primary_source_locators']}:errors.append({'kind':'DOCUMENTARY_PROVENANCE_DIFFERS','uid':uid})
  for loc in fact['primary_source_locators']:
   doc=manifest['primary_documents'][loc['document_id']]
   declared=loc['factual_scope_declaration']
   if declared.get('whole_parent_name')!=fact['parent_nominal_name']or declared.get('whole_named_design_members')!=fact['child_nominal_names']or declared.get('no_source_sample_attributes_generalized')is not True or not loc['locator']:errors.append({'kind':'PRIMARY_COMPLETE_SCOPE_DECLARATION_MISMATCH','uid':uid})
   if loc['document_id']not in checked_docs:
    if doc.get('source_kind')=='SOURCE_OWNED_COMPLETE_DESCRIPTION':
     owned=c.execute('SELECT data FROM nodes WHERE uid=?',(doc['database_source_uid'],)).fetchone();actual=sha(owned[0])if owned else None;local=Path('source-payload:'+doc['database_source_uid'])
    else:
     entry=registry.get('documents',{}).get(loc['document_id'],{})
     filename=entry.get('filename','')
     safe=bool(filename and Path(filename).name==filename and filename not in('.','..')and snapshots is not None)
     bound=registry.get('schema')=='FINEATLAS_PORTABLE_PRIMARY_SOURCE_SNAPSHOTS_V1'and entry.get('source_uri')==doc['source_uri']and entry.get('sha256')==doc['sha256']and entry.get('hash_basis')=='HTTP_RESPONSE_BODY_BYTES'
     local=snapshots/filename if safe else Path('MISSING_EXPLICIT_PRIMARY_SNAPSHOTS_DIR')
     actual=sha(local.read_bytes())if safe and bound and local.is_file()and local.resolve().is_relative_to(snapshots)else None
    checked_docs[loc['document_id']]={'path':str(local),'expected_sha256':doc['sha256'],'actual_sha256':actual,'pass':actual==doc['sha256']}
    if actual!=doc['sha256']:errors.append({'kind':'INDEPENDENT_PRIMARY_SOURCE_SNAPSHOT_CHANGED_OR_UNAVAILABLE','document_id':loc['document_id']})
  for w in proof['source_witnesses']:
   r=c.execute('SELECT data FROM nodes WHERE uid=?',(w['uid'],)).fetchone();data=json.loads(r[0])if r else {};text=data.get(w['field'])or data.get('evidence_record',{}).get(w['field'])
   if not r or sha(r[0])!=w['data_sha256']or text!=w['statement']:errors.append({'kind':'OWNED_FULL_SOURCE_FIELD_CHANGED','uid':uid,'witness_uid':w['uid']})
  if not {uid,op['parent']} <= {w['uid']for w in proof['source_witnesses']}:errors.append({'kind':'BOTH_WHOLE_OWN_ENDPOINTS_NOT_BOUND','uid':uid})
  for u in(uid,op['parent']):
   x=c.execute('SELECT component_id FROM nodes WHERE uid=?',(u,)).fetchone();reviewed=manifest['identity_components'][u];peers=sorted(r[0]for r in c.execute('SELECT uid FROM nodes WHERE component_id=?',(x[0],)));bridges=c.execute('SELECT * FROM bridges WHERE left_uid=? OR right_uid=?',(u,u)).fetchall()
   if peers!=reviewed['uids']or sorted(content(r)+':'+r['status']for r in bridges)!=reviewed['bridge_content_status_hashes']:errors.append({'kind':'SOURCE_COMPONENT_OR_IDENTITY_HISTORY_CHANGED','uid':u})
  for prior in proof['prior_assertions']:
   rr=c.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',tuple(prior[k]for k in('subject_uid','object_uid','relation','source'))).fetchall()
   if not any(content(r)==prior['content_sha256']and r['status']==prior['status']for r in rr):errors.append({'kind':'PRIOR_SOURCE_DECLARATION_LOST_OR_MODIFIED','uid':uid})
  if op['relation']=='DESIGN_TYPE_OF':
   own=next(w['statement']for w in proof['source_witnesses']if w['uid']==uid);head=re.split(r'[.;]|\s+(?:for|with|developed|manufactured|produced|by)\b',re.sub(r'\([^()]*\)','',own),maxsplit=1,flags=re.I)[0]
   if not re.search(r'\bairliner\s*(?:family|model|series)?\s*$',head,re.I)or re.search(r'\b(?:not|never|toy|virtual|fictional|imaginary|parts|engine for)\b',head,re.I):errors.append({'kind':'OWN_FIRST_PHYSICAL_GENUS_NOT_CLOSED','uid':uid})
   parent_statement=next(w['statement']for w in proof['source_witnesses']if w['uid']==op['parent']);kind=fact.get('physical_genus');expected={'airliner':'fixed-wing powered aircraft intended to carry cargo or passengers in commercial service','jet':'an airplane powered by one or more jet engines','twinjet':'a jet plane propelled by two jet engines'}
   if parent_statement!=expected.get(kind):errors.append({'kind':'PARENT_PHYSICAL_RANGE_OR_SENSE_NOT_CLOSED','uid':uid})
   owned_twinjets=[]
   for w in proof['source_witnesses']:
    if w['uid']==op['parent']:continue
    text=re.sub(r'\([^()]*\)','',w['statement']);first=re.split(r'[.;]\s+(?=[A-Z])',text,maxsplit=1)[0];copula=re.search(r'\b(?:is|was|are|were)\b\s+',first,re.I)
    if copula:
     subject=re.sub(r'^(?:the|an?)\s+','',first[:copula.start()].strip(),flags=re.I)
     if name(subject)!=name(n['label']):continue
     first=first[copula.end():]
    literal=re.search(r'\btwinjet\s+(?:airliners?|airplanes?)\b',first,re.I)
    self_engine=bool(copula and re.search(r'\bairliners?\b',first,re.I)and re.search(r'(?:^|\. )Powered by [^.]+ (?:under|beneath) its wings, the twinjet features\b',text,re.I))
    if (literal or self_engine)and not re.search(r'\b(?:fictional|virtual|toy|not|never|without)\b',first,re.I):owned_twinjets.append(w['uid'])
   if kind=='twinjet'and not owned_twinjets:errors.append({'kind':'TWINJET_COUNT_NOT_OWN_SUBJECT_PROPERTY','uid':uid})
  links.add((uid,op['parent'],op['relation']));components.add((n['component_id'],p['component_id'],op['relation']))
  if not preflight:
   rr=c.execute('SELECT r.*,e.payload FROM entity_relations r JOIN evidence e ON e.evidence_id=r.evidence_id WHERE r.subject_uid=? AND r.object_uid=? AND r.relation=? AND r.source=?',(uid,op['parent'],op['relation'],SOURCE)).fetchall()
   if len(rr)!=1 or rr[0]['status']!=('SOURCE_DECLARED'if op['relation']=='SOURCE_DESIGN_DERIVATION_REFERENCE'else'ACTIVE') or json.loads(rr[0]['payload'])!=proof or json.loads(rr[0]['data']).get('admission_basis')!=proof:errors.append({'kind':'ACTUAL_DIRECTION_OR_EVIDENCE_DIFFERS','uid':uid})
   if op['relation']=='SOURCE_DESIGN_DERIVATION_REFERENCE' and (json.loads(rr[0]['data']).get('allowed_views')!=[]or json.loads(rr[0]['data']).get('navigation_eligible')is not False):errors.append({'kind':'DESIGN_ANCESTRY_WRONGLY_NAVIGABLE','uid':uid})
   hh=c.execute("SELECT evidence,after_json FROM usability_changes WHERE stage='primary_aircraft_family_repairs'AND object_type='design_family_append'AND object_id=?",(uid,)).fetchall()
   matched=[r for r in hh if json.loads(r['after_json'])=={'parent_uid':op['parent'],'relation':op['relation']}and json.loads(r['evidence'])==proof]
   if len(matched)!=1:errors.append({'kind':'NEW_DIRECTION_HISTORY_NOT_EXACT','uid':uid})
 metadata={r['key']:json.loads(r['value'])for r in c.execute('SELECT * FROM metadata')}
 if not preflight:
  applied=metadata.get('primary_aircraft_family_repairs',{});frozen=metadata.get('structure_frozen_build_manifest',{}).get('inputs',{})
  if any(frozen.get(f)!=sha((inputs/f).read_bytes())for f in(INPUT_NAME,manifest['operations_file']))or applied.get('manifest_sha256')!=sha(path.read_bytes())or applied.get('operations_sha256')!=sha(raw)or type(applied.get('operation_count'))is not int or applied['operation_count']!=len(ops):errors.append({'kind':'FINAL_FROZEN_INPUT_OR_APPLY_RECEIPT_DIFFERS'})
  catalog=c.execute('SELECT * FROM source_catalogs WHERE source=?',('Hierarchy refinement: '+SOURCE,)).fetchone()
  if not catalog or catalog['input_sha256']!=sha(raw)or json.loads(catalog['coverage']).get('operations')!=dict(Counter(x['relation']for x in ops)):errors.append({'kind':'ACTUAL_SOURCE_CATALOG_ATTRIBUTION_NOT_BOUND'})
  actual=c.execute('SELECT count(*)FROM entity_relations WHERE source=?AND status IN ("ACTIVE","SOURCE_DECLARED")',(SOURCE,)).fetchone()[0]
  if actual!=len(ops):errors.append({'kind':'ACTUAL_SOURCE_ASSERTION_COUNT_DIFFERS','count':actual})
  routes={}
  for op in ops:
   if op['relation']=='SOURCE_DESIGN_DERIVATION_REFERENCE':continue
   routes[op['parent']]=component_route(c,op['parent'],metadata.get('root_uid'))
   if routes[op['parent']] is None:errors.append({'kind':'ACTUAL_DOCUMENTED_PARENT_NO_ROOT','uid':op['parent']})
   canonical_cycle=component_route(c,op['parent'],op['uid'])
   if canonical_cycle is not None:errors.append({'kind':'ACTUAL_CANONICAL_COMPONENT_CYCLE','uid':op['uid'],'path':canonical_cycle})
   cycle=c.execute("WITH RECURSIVE lin(uid) AS(SELECT object_uid FROM entity_relations WHERE subject_uid=?AND relation='NATIVE_DESIGN_PARENT'AND status='ACTIVE'UNION SELECT r.object_uid FROM entity_relations r JOIN lin l ON r.subject_uid=l.uid WHERE r.relation='NATIVE_DESIGN_PARENT'AND r.status='ACTIVE')SELECT 1 FROM lin WHERE uid=?LIMIT 1",(op['uid'],op['uid'])).fetchone()
   if cycle:errors.append({'kind':'ACTUAL_DESIGN_CYCLE','uid':op['uid']})
 report={'schema':'FINEATLAS_INDEPENDENT_PRIMARY_AIRCRAFT_FAMILY_AUDIT_V1','pass':not errors,'preflight_only':preflight,'database':str(database),'database_revision':metadata.get('database_revision'),'release':metadata.get('release'),'manifest_sha256':sha(path.read_bytes()),'operations_sha256':sha(raw),'operation_count':len(ops),'operations':dict(Counter(x['relation']for x in ops)),'added_source_assertions':len(ops),'distinct_uid_relation_links':len(links),'quotient_identity_directions_in_input':len(components),'navigation_assertions':sum(x['relation']!='SOURCE_DESIGN_DERIVATION_REFERENCE'for x in ops),'non_navigation_references':sum(x['relation']=='SOURCE_DESIGN_DERIVATION_REFERENCE'for x in ops),'actual_parent_root_routes':routes if not preflight else 'NOT_APPLIED_PARENT_SCOPE_ONLY','new_nodes':0,'world_identity_promotions':0,'dataset_mapping_promotions':0,'primary_snapshot_actual_hashes':checked_docs,'primary_source_registry_sha256':sha(registry_path.read_bytes())if registry_path.is_file()else None,'primary_snapshots_dir':str(snapshots)if snapshots else None,'pair_or_new_view_path_recovery_claimed':False,'errors':errors}
 output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n');c.close();print(json.dumps({k:v for k,v in report.items()if k not in('errors','primary_snapshot_actual_hashes')}));return not errors

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--preflight',action='store_true');p.add_argument('--primary-snapshots-dir',type=Path,help='Explicit directory containing verified official HTTP source snapshots; no absolute source fallback');p.add_argument('--primary-source-registry',type=Path,help='Portable registry; defaults to inputs/structure_primary_source_snapshots.json');a=p.parse_args();raise SystemExit(0 if run(a.database,a.inputs,a.output,a.preflight,a.primary_snapshots_dir,a.primary_source_registry) else 1)
