#!/usr/bin/env python3
"""Ground retained legacy Wikidata definitions, beyond prior adapter rows."""
import argparse,collections,hashlib,json,re,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas._text import norm
from fineatlas.nominal import WordNetKinds,DEFINITION_SQL,object_kind_head
from fineatlas.role_contracts import allows_model_extraction,nominal_role_decision
from fineatlas.semantics import role_expression
p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--inputs',required=True);p.add_argument('--definitions',required=True);a=p.parse_args();I=Path(a.inputs)
c=sqlite3.connect(Path(a.database).resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA cache_size=-500000');c.execute('PRAGMA query_only=ON')
base=[json.loads(l) for l in (I/'hierarchy_facts.jsonl').open()];extra=[json.loads(l) for l in (I/'hierarchy_extensions.jsonl').open()];roles={r['uid']:r['role'] for r in base+extra if r['op']=='role'};known={r['uid'] for r in base+extra if r['op']=='class'};already={r['uid'] for r in base if r['op']=='link' and r['proof']['basis']=='INDEPENDENT_NOMINAL_HEAD_AND_GENERIC_PARENT_DEFINITION'};roots={u for r in c.execute('SELECT root_uids FROM domain_registry') for u in json.loads(r[0])};definitions=json.loads(Path(a.definitions).read_text());kinds=WordNetKinds(c,include_native=True);new=[];counts=collections.Counter();cache={};lexical={};headcache={}
IGNORE_DOMAINS={'plants','animals','birds','fungi','bacteria','archaea','buildings','bridges','foods','dishes','mountains','mountain_ranges','aquifers','beaches','clouds','deserts','glaciers','islands','lakes','rivers','valleys','volcanoes','waterfalls'}
def node(u):
 if u not in cache:
  r=c.execute('SELECT n.*,'+role_expression('n','p')+' role,'+DEFINITION_SQL+' definition FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(u,)).fetchone();cache[u]=dict(r) if r else None
 return cache[u]
def kind(u):return roles.get(u,'CLASS' if u in known else node(u)['role'])
def generic_label(label):
 value=norm(label)
 if value not in lexical:lexical[value]=any(kinds.artifact_type(r[0]) for r in c.execute("SELECT a.uid FROM aliases a JOIN nodes n ON n.uid=a.uid WHERE a.alias=? AND a.uid LIKE 'wordnet31:%' AND n.visibility='ACTIVE'",(value,)))
 return lexical[value]
def generic_parent(u):
 if kind(u)!='CLASS' or not kinds.generic_type(u):return False
 n=node(u)
 return u.startswith('wordnet31:') or u in roots or n['label']==n['label'].lower() or re.search(r'\b(?:type|kind|class|form) of\b',n['definition'][:220],re.I) or re.match(r'\s*(?:a|an) '+re.escape(n['label']),n['definition'],re.I)
def parent_for_head(head):
 head=object_kind_head(head)
 if head in headcache:return headcache[head]
 words=norm(head).split();parent=None
 for length in range(min(4,len(words)),0,-1):
  candidates={u for u in kinds.candidates(' '.join(words[-length:])) if generic_parent(u)}
  parent=kinds.representative(candidates)
  if parent:break
 headcache[head]=parent;return parent
# No instance, source-only record or biological/organisation declaration is
# silently turned into a reusable design by a noun or historical rank.
scanned=0
for n in c.execute('SELECT n.uid,n.label,n.description,n.data,'+role_expression('n','p')+" role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility='ACTIVE' AND n.source IN ('wikidata','wikidata-v4') ORDER BY n.uid"):
 scanned+=1
 if scanned%10000==0:print('SCANNED',scanned,dict(counts),flush=True)
 u=n['uid'];current=roles.get(u,n['role'])
 if u in already or current not in {'CLASS','MODEL','MODEL_FAMILY'}:continue
 raw=json.loads(n['data'])
 if set(raw.get('domains',[])) & IGNORE_DOMAINS or raw.get('domain') in IGNORE_DOMAINS:continue
 record=definitions.get('wikidata:'+u.split(':')[-1],{});intro=record.get('intro') or raw.get('definition') or n['description']
 statement=re.sub(r'\([^()]*\)','',intro)
 match=re.search(r'\b(?:is|was|are|were)\s+(?:an?|the)\s+([^.;]{1,180})',statement,re.I)
 if not match:continue
 head=re.split(r'\b(?:that|which|with|for|designed|developed|built|produced|manufactured|made|introduced|released|sold|unveiled|awarded|announced|by|since|from|used|as|and|but)\b',match[1],maxsplit=1,flags=re.I)[0].strip(' ,')
 if re.search(r'\b(?:program|project|nameplate|proposal|concept|study)\s*$',head,re.I) or re.search(r'\b(?:software|programming|algorithm|language|protocol|framework|technology|architecture|microarchitecture|computing platform)\b',head,re.I):continue
 parent=parent_for_head(head)
 if not parent or not kinds.artifact_type(parent):continue
 if node(parent)['component_id']==node(u)['component_id']:continue
 if c.execute("SELECT 1 FROM entity_relations WHERE subject_uid=? AND status='ACTIVE' AND relation='INSTANCE_OF' LIMIT 1",(u,)).fetchone():continue
 named_code=bool(re.match(r'[A-Z][a-z]{2,}\b[^.]{0,70}\d',n['label']) or re.search(r'\b[A-Z]{2,}[- ]?\d',n['label']))
 proper=bool(re.match(r'[A-Z]',n['label']) and (len(re.findall(r'\b[A-Z][A-Za-z]+\b',n['label']))>=2 or not generic_label(n['label'])))
 generic_head=bool(re.search(r'\b(?:type|kind|class|form|variety) of\b',head,re.I))
 named=(named_code or proper) and u not in roots and (named_code or not generic_head)
 family=bool(re.search(r'\b(?:family|series|line|range) of\b',head,re.I) or ('-class' in n['label'].lower() and re.search(r'\bclass of\b',head,re.I)))
 if current=='CLASS' and not family and re.search(r'\b(?:satellite|spacecraft|orbiter|space station)\b',head,re.I):continue
 declared=bool(re.search(r'\b(?:manufactured|developed|produced|released|introduced|designed|made|announced)\b',statement[:550],re.I))
 if not family and re.search(r'\b(?:serial number|registration number|tail number|sole example|only example|wrecked|sank|scrapped|crashed|launched into|orbited)\b',statement[:700],re.I):continue
 uri=record.get('source_uri') or raw.get('source_uri') or 'https://www.wikidata.org/wiki/'+u.split(':')[-1]
 proof={'basis':'INDEPENDENT_LEGACY_ARTIFACT_DEFINITION_WITH_VERIFIED_GENERIC_HEAD','source_statement':statement[:700],'nominal_head':head,'parent_definition':node(parent)['definition'],'native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),'license':'Wikipedia CC BY-SA 4.0; article and retained snapshot attribution preserved' if 'en.wikipedia.org/' in uri else 'Original source attribution and terms retained'}
 if current in {'MODEL','MODEL_FAMILY'} and re.fullmatch(r'[a-z][a-z -]*',n['label']) and not re.search(r'\b(?:family|series|line|range) of\b',head,re.I) and (generic_head or generic_label(n['label'])):
  members=c.execute('SELECT uid,visibility FROM nodes WHERE component_id=? AND uid IN (?,?,?)',(node(u)['component_id'],'wikidata:'+u.split(':')[-1],'wikidata-v4:'+u.split(':')[-1],'v26-wikidata:'+u.split(':')[-1])).fetchall()
  for member in members:
   v=member['uid']
   if member['visibility']!='ACTIVE' or kind(v) not in {'MODEL','MODEL_FAMILY'}:continue
   roles[v]='CLASS';new.append({'op':'role','uid':v,'role':'CLASS','source':'Independent generic category definitions','uri':uri,'proof':{**proof,'basis':'PLAIN_GENERIC_REFERENT_WITH_INDEPENDENT_TYPE_OR_LEXICAL_DEFINITION','native_record_uid':u}});counts['generic_categories_restored']+=1
   for relation in c.execute("SELECT id FROM entity_relations WHERE subject_uid=? AND status='ACTIVE' AND relation IN ('DESIGN_TYPE_OF','SERIES_MEMBER_OF')",(v,)):
    new.append({'op':'withdraw_typed','uid':v,'relation_id':relation[0],'source':'Independent generic category definitions','uri':uri,'proof':{'basis':'GENERIC_CATEGORY_IS_NOT_A_NAMED_DESIGN_TERMINAL','license':'Original declaration retained'}})
  current=kind(u)
 profile=c.execute('SELECT * FROM node_profiles WHERE uid=?',(u,)).fetchone()
 canonical_profile={**(dict(profile) if profile else {}),'node_kind':current}
 if current=='CLASS' and named and (declared or family) and allows_model_extraction(raw,canonical_profile):
  # Named ship-class families take precedence over construction of their
  # members. Explicit individual histories remain outside model extraction.
  decision,reason=nominal_role_decision({'definition':statement},{})
  if decision=='INSTANCE' and not family:continue
  target='MODEL_FAMILY' if family else 'MODEL'
  members=c.execute('SELECT uid,visibility FROM nodes WHERE component_id=? AND uid IN (?,?,?)',(node(u)['component_id'],'wikidata:'+u.split(':')[-1],'wikidata-v4:'+u.split(':')[-1],'v26-wikidata:'+u.split(':')[-1])).fetchall()
  if any(kind(x['uid'])=='MODEL_FAMILY' for x in members):target='MODEL_FAMILY'
  for member in members:
   if member['visibility']!='ACTIVE' or kind(member['uid']) in {'INSTANCE','ORGANIZATION','UNKNOWN'} or kind(member['uid'])==target:continue
   roles[member['uid']]=target;new.append({'op':'role','uid':member['uid'],'role':target,'source':'Independent legacy referent and design grain definitions','uri':uri,'proof':{**proof,'basis':'NAMED_DESIGN_OR_DESIGN_FAMILY_WITH_INDEPENDENT_MANUFACTURING_OR_GROUP_SCOPE','native_record_uid':u}});counts['role_decisions']+=1
  current=kind(u)
 relation={'CLASS':'IS_A','MODEL':'DESIGN_TYPE_OF','MODEL_FAMILY':'DESIGN_TYPE_OF'}[current]
 new.append({'op':'link','uid':u,'parent':parent,'relation':relation,'source':'Independent legacy generic-head type refinements','uri':uri,'proof':proof});counts['type_links']+=1
# Resolve all proposed roles before final parents and shortcut decisions.
for r in new:
 if r['op']=='link' and kind(r['parent'])!='CLASS':raise ValueError('Proposed nominal parent is a named design: '+r['parent'])
ancestors_cache={}
def ancestors(u):
 comp=node(u)['component_id']
 if comp in ancestors_cache:return ancestors_cache[comp]
 todo=[comp];seen=set();found=set()
 while todo and len(seen)<500:
  value=todo.pop()
  if value in seen:continue
  seen.add(value)
  for row in c.execute("SELECT DISTINCT p.uid,p.component_id FROM nodes n JOIN edges e ON e.child_uid=n.uid JOIN nodes p ON p.uid=e.parent_uid WHERE n.component_id=? AND e.relation='IS_A' AND e.status='ACTIVE' AND p.visibility='ACTIVE'",(value,)):
   if kind(row['uid'])=='CLASS' and row['component_id']!=comp:found.add(row['component_id']);todo.append(row['component_id'])
 ancestors_cache[comp]=found;return found
removed={r['edge_id'] for r in base+extra if r['op']=='withdraw_edge'};typed_removed={r['relation_id'] for r in base+extra if r['op']=='withdraw_typed'}
for r in list(new):
 if r['op']!='link':continue
 anc=ancestors(r['parent'])
 for row in c.execute("SELECT e.id,e.parent_uid,p.component_id FROM edges e JOIN nodes p ON p.uid=e.parent_uid WHERE e.child_uid=? AND e.status='ACTIVE' AND e.relation='IS_A'",(r['uid'],)):
  if row['id'] not in removed and row['component_id'] in anc:
   new.append({'op':'withdraw_edge','uid':r['uid'],'parent':row['parent_uid'],'edge_id':row['id'],'source':r['source'],'uri':r['uri'],'proof':{'basis':'WITNESSED_GENERIC_CLASS_PATH_REPLACES_LEGACY_BROAD_SHORTCUT','replacement_parent':r['parent'],'license':'Original declaration retained'}});removed.add(row['id']);counts['root_shortcuts']+=1
 for row in c.execute("SELECT e.id,p.component_id FROM entity_relations e JOIN nodes p ON p.uid=e.object_uid WHERE e.subject_uid=? AND e.status='ACTIVE' AND e.relation='DESIGN_TYPE_OF'",(r['uid'],)):
  if row['id'] not in typed_removed and row['component_id'] in anc:
   new.append({'op':'withdraw_typed','uid':r['uid'],'relation_id':row['id'],'source':r['source'],'uri':r['uri'],'proof':{'basis':'WITNESSED_GENERIC_CLASS_PATH_REPLACES_LEGACY_BROAD_SHORTCUT','replacement_parent':r['parent'],'license':'Original declaration retained'}});typed_removed.add(row['id'])
result=list({json.dumps(r,ensure_ascii=False,sort_keys=True):r for r in extra+new}.values())
with (I/'hierarchy_extensions.jsonl').open('w') as f:
 for r in result:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
(I/'native_design_extension.json').write_text(json.dumps({'new_operations':len(new),'total_extension_records':len(result),'counts':dict(counts),'sha256':hashlib.sha256((I/'hierarchy_extensions.jsonl').read_bytes()).hexdigest()},indent=2)+'\n')
print('NATIVE LEGACY DEFINITIONS',len(new),dict(counts),flush=True)
