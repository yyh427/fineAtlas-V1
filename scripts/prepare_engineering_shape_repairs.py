#!/usr/bin/env python3
"""Freeze full-scope engineering grain and subject-type corrections.

This preparer reads a prior immutable candidate. All source assertions remain
in the ledger; every withdrawal names its exact original endpoints and ID.
"""
import argparse,collections,hashlib,json,re,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.nominal import WordNetKinds,object_kind_head
from fineatlas.engineering_roles import definition_head,OBJECT,native_subject_aliases,aircraft_engine_conditions
from fineatlas.semantics import role_expression
from fineatlas.hierarchy import LINK_ROLES

p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--inventory',required=True);p.add_argument('--proposals',required=True);p.add_argument('--definitions',required=True);p.add_argument('--supplement');p.add_argument('--grain-reviews',type=Path);p.add_argument('--subject-reviews',type=Path);p.add_argument('--output',required=True);a=p.parse_args()
c=sqlite3.connect(Path(a.database).resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');c.execute('PRAGMA temp_store=MEMORY');c.execute('PRAGMA cache_size=-500000')
O=Path(a.output);O.mkdir(parents=True,exist_ok=True);nodes={n['uid']:n for n in map(json.loads,Path(a.inventory).open())};definitions=json.loads(Path(a.definitions).read_text());proposals={n['uid']:n for n in map(json.loads,Path(a.proposals).open())};records=[];counts=collections.Counter();reviews=[];desired={};role_proof={};cached={};R=role_expression('n','p');source='Full engineering subject and grain evidence'
aliases_by_qid={};alias_snapshot_hashes={}
if a.supplement:
 for snapshot in Path(a.supplement).glob('Q*.json'):
  item=json.loads(snapshot.read_bytes()).get('entities',{}).get(snapshot.stem,{})
  if item:
   aliases_by_qid[snapshot.stem]=native_subject_aliases(item)
   alias_snapshot_hashes[snapshot.stem]=hashlib.sha256(snapshot.read_bytes()).hexdigest()
def own_head(text,u):return definition_head(text,node(u)['label'],subject_aliases=aliases_by_qid.get(u.split(':')[-1],()))

registry={d['canonical_name']:json.loads(d['root_uids']) for d in map(dict,c.execute('SELECT * FROM domain_registry'))}

def node(u):
 if u not in cached:
  if u in nodes:cached[u]=nodes[u]
  else:
   r=c.execute('SELECT n.*,p.attributes,'+R+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(u,)).fetchone();cached[u]=dict(r) if r else None
 return cached[u]
def kind(u):return desired.get(u,node(u)['role'])
def proof_for(u,basis,**extra):
 n=node(u);q=u.split(':')[-1];context={}
 if q in aliases_by_qid:context={'native_subject_aliases':list(aliases_by_qid[q]),'native_entity_snapshot_sha256':alias_snapshot_hashes[q]}
 independent=definitions.get('wikidata:'+q,{})
 if independent.get('source_snapshot_sha256'):context['independent_definition_snapshot_sha256']=independent['source_snapshot_sha256']
 return {'basis':basis,'native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),'native_rank':n['rank'],'license':'Native source attribution retained; Wikidata CC0 factual metadata; retained independent encyclopedia definition CC BY-SA 4.0',**context,**extra}
def uri(u):
 raw=json.loads(node(u)['data']);profile=c.execute('SELECT source_uri FROM node_profiles WHERE uid=?',(u,)).fetchone()
 if raw.get('source_uri'):return raw['source_uri']
 if profile and profile[0]:return profile[0]
 if node(u)['source']=='faa':return 'https://registry.faa.gov/database/ReleasableAircraft.zip'
 if node(u)['source']=='epa':return 'https://www.fueleconomy.gov/feg/download.shtml'
 return 'https://www.wikidata.org/wiki/'+u.split(':')[-1]
def emit(op,u,proof,**fields):
 records.append({'op':op,'uid':u,'source':source,'uri':uri(u),'proof':proof,**fields});counts[op]+=1

# Reuse an already evidenced grain only for the exact same source identifier
# inside an existing verified identity group. Matching labels never suffice;
# an explicit native INSTANCE remains outside automatic model extraction.
for u,n in sorted(nodes.items()):
 if n['role']!='CLASS' or n['visibility']!='ACTIVE' or u in desired:continue
 q=u.split(':')[-1]
 if not re.fullmatch(r'Q\d+',q):continue
 raw=json.loads(n['data'])
 if raw.get('node_kind')=='INSTANCE':continue
 authorities=[]
 for row in c.execute('SELECT n.*,p.attributes,'+R+" role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.component_id=? AND n.visibility='ACTIVE' AND n.uid LIKE ?",(n['component_id'],'%:'+q)):
  if row['uid']==u or row['role'] not in {'MODEL','MODEL_FAMILY'}:continue
  attrs=json.loads(row['attributes'] or '{}')
  if attrs.get('role_status')!='VERIFIED':continue
  for decision in c.execute("SELECT id,payload FROM hierarchy_decisions WHERE subject_uid=? AND operation='role' AND evidence_id=?",(row['uid'],attrs.get('role_evidence_id'))):
   claim=json.loads(decision['payload']);pr=claim['proof']
   if claim.get('role')!=row['role'] or pr.get('native_record_sha256')!=hashlib.sha256(row['data'].encode()).hexdigest():continue
   if pr.get('basis') not in {'EXPLICIT_NATIVE_DESIGN_DECLARATION_WITH_CORROBORATING_DESIGN_CONTEXT','NATIVE_NAMED_VERSION_WITH_INDEPENDENTLY_VERIFIED_DESIGN_PARENT','NATIVE_PRODUCT_MANUFACTURER_AND_PHYSICAL_DESCRIPTION'}:continue
   authorities.append((dict(row),decision['id'],claim))
 if not authorities or len({row['role'] for row,_,_ in authorities})!=1:continue
 authority,decision_id,claim=sorted(authorities,key=lambda x:x[0]['uid'])[0]
 role=authority['role'];proof=proof_for(u,'EXACT_SOURCE_IDENTITY_REUSES_CORROBORATED_DESIGN_GRAIN',authority_uid=authority['uid'],authority_frozen_decision_id=decision_id,authority_native_sha256=hashlib.sha256(authority['data'].encode()).hexdigest(),authority_basis=claim['proof']['basis'],source_identifier=q,verified_component_id=n['component_id'])
 desired[u]=role;role_proof[u]=proof;emit('role',u,proof,role=role)

# Explicit lists, brands and disambiguation pages are source records rather
# than reusable object kinds. Retain them with the exact exclusion reason.
for u,n in sorted(nodes.items()):
 if n['role']!='CLASS' or n['visibility']!='ACTIVE' or u.startswith('wordnet31:'):continue
 raw=json.loads(n['data']);e=raw.get('evidence_record',{})
 desc=raw.get('wikidata_description') or e.get('wikidata_description') or raw.get('description') or ''
 independent=definitions.get('wikidata:'+u.split(':')[-1],{}).get('intro') or raw.get('definition') or e.get('wikipedia_intro') or ''
 non_object=bool(re.search(r'\bWikimedia\s+(?:disambiguation\s+page|list\s+article|category)\b|^list of (?:concept )?(?:vehicles|aircraft|cars)\b|\b(?:car brand|car manufacturer|car maker|automotive brand|motor vehicle manufacturer)\b',desc,re.I))
 non_object=non_object or bool(re.search(r'\b(?:is|was)\s+(?:an?|the)\s+(?:\w+\s+){0,3}(?:car maker|aircraft company|automotive brand)\b|\bwas one of the automobile marques\b',independent,re.I))
 non_object=non_object or bool(re.search(r'\b(?:brand of (?:microcars|cars|automobiles)|(?:research and development|military|future|research) program)\b',desc+' '+independent,re.I))
 abstract_technique=bool(re.search(r'\b(?:evolution|combination) of\b[^.;]{0,100}\b(?:techniques|methods)\b',own_head(independent,u),re.I))
 independent_head=own_head(independent,u)
 development_program=bool(re.search(r'\b(?:program|programme|project)\b',independent_head,re.I) and not re.search(OBJECT,independent_head,re.I) and not proposals.get(u) or n['label'].startswith('Project ') and re.search(r'\bcode name given\b',independent_head,re.I))
 non_object=non_object or abstract_technique or development_program
 if non_object:
  desired[u]='UNKNOWN'
  proof=proof_for(u,'SOURCE_SUBJECT_IS_TECHNIQUE_NOT_A_PHYSICAL_PRODUCT_KIND' if abstract_technique else 'SOURCE_SUBJECT_IS_DEVELOPMENT_PROGRAM_NOT_A_VEHICLE_KIND' if development_program else 'NATIVE_SOURCE_EXPLICITLY_IDENTIFIES_NON_OBJECT_KIND_RECORD',source_statement=desc,independent_definition=independent,review_reason='Source defines an evolution or combination of techniques; prior artifact parents were extracted from the technique arguments' if abstract_technique else 'Source defines a development program or project code name; its proposed vehicle types remain separate source records' if development_program else 'Record denotes a list, disambiguation page, manufacturer or brand; no reusable physical type is asserted')
  role_proof[u]=proof;emit('source_review',u,proof)

# A single prototype can denote its design, its individual airframe, or both.
# Retain the exact declaration for review instead of admitting it as a generic
# class or using a designation alone to override explicit individual evidence.
for u,n in sorted(nodes.items()):
 if n['role']!='CLASS' or u in desired or n['visibility']!='ACTIVE' or u.startswith('wordnet31:'):continue
 if not any(d in {'aircraft','cars','ships','locomotives','tractors','car'} for d in n['scopes']):continue
 raw=json.loads(n['data']);e=raw.get('evidence_record',{})
 desc=raw.get('wikidata_description') or e.get('wikidata_description') or raw.get('description') or ''
 native=raw.get('definition') or raw.get('intro') or e.get('wikipedia_intro') or ''
 independent=definitions.get('wikidata:'+u.split(':')[-1],{}).get('intro') or ''
 text=' '.join([desc,native,independent])
 if not re.match(r'[A-Z]',n['label']) or not re.search(r'\b(?:one-off|sole example|only example|only one example|serial number|registration number|tail number)\b',text,re.I):continue
 proof=proof_for(u,'EXPLICIT_UNIQUE_OBJECT_DECLARATION_NEEDS_DESIGN_INSTANCE_ADJUDICATION',source_statement=text,review_reason='Unique prototype or individually identified object: retained record does not independently separate design identity from the physical instance')
 desired[u]='UNKNOWN';role_proof[u]=proof;emit('source_review',u,proof)

if a.grain_reviews:
 for case in map(json.loads,a.grain_reviews.open()):
  u=case['uid'];n=node(u)
  if not n or n['role']!='CLASS' or n['visibility']!='ACTIVE' or u in desired:continue
  snapshot=Path(a.supplement)/(u.split(':')[-1]+'.json')
  if hashlib.sha256(snapshot.read_bytes()).hexdigest()!=case['native_entity_snapshot_sha256'] or not case.get('review_reason') or not case.get('unavailable_source_revisions'):
   raise ValueError('Source-grain review lacks the exact source record and unavailable-reference evidence')
  if u in proposals:raise ValueError('Source-grain review conflicts with an independently supported design decision')
  desired[u]='UNKNOWN';proof=proof_for(u,'INDIVIDUALLY_REVIEWED_NATIVE_GRAIN_LACKS_SURVIVING_CORROBORATION',**case['proof'],review_reason=case['review_reason']);role_proof[u]=proof;emit('source_review',u,proof)

# Individually inspected subject records can remain unresolved even when their
# source survives: a redirected article or a short object description does not
# independently distinguish a factory design, individual or reusable kind.
if a.subject_reviews:
 for case in map(json.loads,a.subject_reviews.open()):
  u=case['uid'];n=node(u)
  if not n or n['role']!='CLASS' or n['visibility']!='ACTIVE' or u in desired:continue
  if u in proposals:continue
  if case.get('native_record_sha256')!=hashlib.sha256(n['data'].encode()).hexdigest() or not case.get('review_reason') or case.get('review_status')!='INDIVIDUALLY_INSPECTED':
   raise ValueError('Subject review lacks the exact retained record and individual inspection')
  snapshot=Path(a.supplement)/(u.split(':')[-1]+'.json')
  if hashlib.sha256(snapshot.read_bytes()).hexdigest()!=case.get('native_entity_snapshot_sha256'):
   raise ValueError('Subject review source snapshot changed')
  independent=case.get('retained_subject_definition','');head=own_head(independent,u)
  if re.search(r'\b(?:type|kind|category|class|form|variety) of\b|\b(?:body[ -]style|body type|size class)\b',head,re.I):
   raise ValueError('A source-defined generic kind needs a separate explicit adjudication')
  proof=proof_for(u,'INDIVIDUALLY_INSPECTED_SUBJECT_GRAIN_REMAINS_UNRESOLVED',review_reason=case['review_reason'],source_statement=case['source_statement'],independent_definition=independent,review_case_sha256=hashlib.sha256(json.dumps(case,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),review_status=case['review_status'])
  desired[u]='UNKNOWN';role_proof[u]=proof;emit('source_review',u,proof)

# Exact source aliases share an unresolved referent too. A second import of
# the same QID cannot silently restore a reviewed prototype as a generic kind.
for authority in list(desired):
 if desired[authority]!='UNKNOWN':continue
 n=node(authority);qid=authority.split(':')[-1]
 if not re.fullmatch(r'Q\d+',qid):continue
 for row in c.execute("SELECT uid FROM nodes WHERE component_id=? AND visibility='ACTIVE' AND uid LIKE ?",(n['component_id'],'%:'+qid)):
  u=row[0];alias=node(u)
  if u in desired or alias['role']!='CLASS':continue
  origin=role_proof[authority]
  proof=proof_for(u,'EXACT_SOURCE_ALIAS_RETAINS_UNRESOLVED_REFERENT_GRAIN',review_authority_uid=authority,review_authority_native_sha256=hashlib.sha256(n['data'].encode()).hexdigest(),review_authority_basis=origin['basis'],review_reason=origin['review_reason'],source_statement=origin.get('source_statement',origin.get('independent_definition','')))
  desired[u]='UNKNOWN';role_proof[u]=proof;emit('source_review',u,proof)

# Exact QID aliases denote the same referent, unlike name-based matches.
proposal_groups=collections.defaultdict(list)
for u,pr in proposals.items():proposal_groups[u.split(':')[-1],pr['component_id']].append((u,pr))
selected=[]
for q,group in sorted(proposal_groups.items()):
 roles={pr['role'] for _,pr in group}
 if len(roles)>1 and roles!={'MODEL','MODEL_FAMILY'}:
  reviews.append({'source_id':q,'reason':'Conflicting individual and design evidence requires source adjudication','proposals':group});continue
 # A collective definition is more specific than a designation-only hint.
 group.sort(key=lambda item:(item[1]['role']!='MODEL_FAMILY',len(item[1]['definition'])==0,item[0]))
 selected.append(group[0])
for u,pr in selected:
 n=node(u)
 if n['visibility']!='ACTIVE' or u.startswith('wordnet31:'):continue
 qid=u.split(':')[-1];aliases=[u]
 if re.fullmatch(r'Q\d+',qid):
  aliases += [r['uid'] for r in c.execute('SELECT uid FROM nodes WHERE component_id=? AND visibility=\'ACTIVE\' AND uid LIKE ?', (n['component_id'],'%:'+qid))]
 for v in sorted(set(aliases)):
  existing=node(v)
  if existing['role'] in {'INSTANCE','ORGANIZATION','ATTRIBUTE','CONFIGURATION','BIOLOGICAL_VARIANT','DATASET_CATEGORY','UNKNOWN'}:continue
  if existing['role']==pr['role'] or v in desired:continue
  proof=proof_for(v,pr['basis'],source_subject_uid=u,source_subject_native_sha256=hashlib.sha256(n['data'].encode()).hexdigest(),native_description=pr['description'],independent_definition=pr['definition'],native_subject_aliases=pr.get('native_subject_aliases',[]),independent_native_role_adjudication=pr.get('independent_native_role_adjudication',False),scope=pr['domain'])
  desired[v]=pr['role'];role_proof[v]=proof
  emit('role',v,proof,role=pr['role'])

# A source-stated named version plus a verified design parent establishes
# design grain even when the short statement omits the word aircraft/car.
for u,n in sorted(nodes.items()):
 if n['role']!='CLASS' or u in desired or n['visibility']!='ACTIVE' or u.startswith('wordnet31:'):continue
 raw=json.loads(n['data']);e=raw.get('evidence_record',{})
 desc=raw.get('wikidata_description') or e.get('wikidata_description') or raw.get('description') or ''
 if not re.search(r'\b(?:version|variant|generation|conversion|upgrade|model|series|family|prototype)\b',desc,re.I) or re.search(r'\b(?:fleet|in service|one-off|serial number|registration|TV series)\b',desc,re.I):continue
 if not re.search(r'[A-Z]',n['label']):continue
 for edge in c.execute("SELECT parent_uid FROM edges WHERE child_uid=? AND relation='IS_A' AND status='ACTIVE'",(u,)):
  v=edge[0]
  if kind(v) not in {'MODEL','MODEL_FAMILY'}:continue
  proof=proof_for(u,'NATIVE_NAMED_VERSION_WITH_INDEPENDENTLY_VERIFIED_DESIGN_PARENT',source_statement=desc,native_parent_uid=v,native_parent_label=node(v)['label'],native_parent_sha256=hashlib.sha256(node(v)['data'].encode()).hexdigest())
  role='MODEL_FAMILY' if re.search(r'\b(?:series|family)\b',desc,re.I) else 'MODEL'
  desired[u]=role;role_proof[u]=proof;emit('role',u,proof,role=role);break

# Fresh native declarations require corroboration: an independently verified
# design parent, or a manufacturer plus a retained subject definition. P31 or
# a historical rank alone cannot supply design grain or erase an instance role.
if a.supplement:
 supplement=Path(a.supplement)
 by_source_id=collections.defaultdict(list)
 for u,n in sorted(nodes.items()):by_source_id[u.split(':')[-1]].append((u,n))
 native_design_classes={'Q10929058':'MODEL','Q15056993':'MODEL_FAMILY','Q15056995':'MODEL','Q15126161':'MODEL','Q19723444':'MODEL','Q19723451':'MODEL','Q3231690':'MODEL','Q124054999':'MODEL','Q45296117':'MODEL','Q21451552':'MODEL_FAMILY'}
 for path in sorted(supplement.glob('Q*.json')):
  q=path.stem;item=json.loads(path.read_bytes()).get('entities',{}).get(q)
  if not item:continue
  def values(prop):return {r.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id') for r in item.get('claims',{}).get(prop,[]) if isinstance(r.get('mainsnak',{}).get('datavalue',{}).get('value',{}),dict)}
  declared=values('P31')&native_design_classes.keys()
  model_role='MODEL_FAMILY' if any(native_design_classes[v]=='MODEL_FAMILY' for v in declared) else 'MODEL'
  for u,n in by_source_id.get(q,[]):
   if n['visibility']!='ACTIVE' or n['role']!='CLASS' or u in desired:continue
   parents=[v for v in values('P279') if v]
   authorities=[]
   for parent_id in parents:
    for v in ['wikidata:'+parent_id,'wikidata-v4:'+parent_id]:
     pn=node(v)
     if pn and pn['visibility']=='ACTIVE' and kind(v) in {'MODEL','MODEL_FAMILY'}:authorities.append(v)
   raw=json.loads(n['data']);e=raw.get('evidence_record',{});record=definitions.get('wikidata:'+q,{})
   independent=record.get('intro') or raw.get('definition') or e.get('wikipedia_intro') or ''
   current_description=item.get('descriptions',{}).get('en',{}).get('value','')
   if raw.get('node_kind')=='INSTANCE' and not (declared and independent and own_head(independent,u) and re.search(r'\b(?:model|design|family|series|manufactured|produced|developed)\b',independent,re.I)):continue
   physical_description=bool(re.search(OBJECT,current_description,re.I))
   named_subject=bool(re.match(r'[A-Z]',n['label']) and independent and own_head(independent,u))
   # Manufacturer metadata and a named physical-product description are
   # independent factual context; generic WordNet types are never candidates.
   native_product=bool(values('P176') and physical_description and re.match(r'[A-Z]',n['label']) and not re.search(r'\b(?:manufacturer|company|brand|program|project)\b',current_description,re.I))
   if not ((declared and (authorities or values('P176') and (independent or physical_description) or named_subject)) or native_product):continue
   if re.search(r'\b(?:in (?:Iranian|Indian|Chinese|military|naval) service|in service with|fleet|operator)\b',n['label']+' '+item.get('descriptions',{}).get('en',{}).get('value',''),re.I):continue
   proof=proof_for(u,'NATIVE_PRODUCT_MANUFACTURER_AND_PHYSICAL_DESCRIPTION' if native_product and not declared else 'EXPLICIT_NATIVE_DESIGN_DECLARATION_WITH_CORROBORATING_DESIGN_CONTEXT',native_entity_snapshot_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),native_entity_uri='https://www.wikidata.org/wiki/Special:EntityData/'+q+'.json',native_design_class_ids=sorted(declared),manufacturer_ids=sorted(v for v in values('P176') if v),verified_design_parent_uids=sorted(authorities),native_subject_description=current_description,independent_subject_definition=independent)
   desired[u]=model_role;role_proof[u]=proof;emit('role',u,proof,role=model_role)

# An inherited canonical CLASS cannot silently erase an explicit native
# INSTANCE declaration. Already corroborated design decisions above stand;
# remaining disagreements retain their facts outside generic classification.
for u,n in sorted(nodes.items()):
 if n['role']!='CLASS' or u in desired or n['visibility']!='ACTIVE' or u.startswith('wordnet31:'):continue
 raw=json.loads(n['data'])
 if raw.get('node_kind')!='INSTANCE':continue
 independent=raw.get('definition') or raw.get('intro') or raw.get('evidence_record',{}).get('wikipedia_intro') or ''
 head=own_head(independent,u)
 if re.search(r'\b(?:type|kind|category|class|form) of\b',head,re.I):continue
 proof=proof_for(u,'NATIVE_INSTANCE_AND_INHERITED_CLASS_GRAIN_CONFLICT',native_role_declaration='INSTANCE',inherited_canonical_role='CLASS',independent_definition=independent,review_reason='Explicit native instance declaration conflicts with inherited CLASS; no independently corroborated design or generic-kind decision settles this record')
 desired[u]='UNKNOWN';role_proof[u]=proof;emit('source_review',u,proof)

# Operator populations and redirected historical identifiers cannot be
# silently converted into a factory design. Keep their raw records reviewable.
for u,n in sorted(nodes.items()):
 if n['role']!='CLASS' or u in desired or n['visibility']!='ACTIVE' or u.startswith('wordnet31:'):continue
 raw=json.loads(n['data']);e=raw.get('evidence_record',{})
 desc=raw.get('wikidata_description') or e.get('wikidata_description') or raw.get('description') or ''
 operator=bool(re.search(r'\b(?:in service with|in (?:Iranian|Indian|Chinese) service|in service with Iran|in Iranian service)\b',n['label']+' '+desc,re.I))
 redirected=False
 if a.supplement:
  snapshot=Path(a.supplement)/(u.split(':')[-1]+'.json')
  if snapshot.exists():
   entities=json.loads(snapshot.read_bytes()).get('entities',{})
   redirected=bool(u.split(':')[-1] not in entities and entities)
 if not operator and not redirected:continue
 if not any(kind(row[0]) in {'MODEL','MODEL_FAMILY'} for row in c.execute("SELECT parent_uid FROM edges WHERE child_uid=? AND relation='IS_A' AND status='ACTIVE'",(u,))):continue
 reason='Operator-defined population is not independently established as a specific factory design or generic object kind' if operator else 'Historical identifier now redirects to a broader design family; original model-versus-family grain needs separate source adjudication'
 proof=proof_for(u,'RETAINED_SOURCE_POPULATION_OR_REDIRECT_REQUIRES_GRAIN_REVIEW',source_statement=desc,original_label=n['label'],review_reason=reason)
 desired[u]='UNKNOWN';role_proof[u]=proof;emit('source_review',u,proof)

k=WordNetKinds(c,include_native=True);resolved={};candidates_cache={}
def candidates(term):
 if term not in candidates_cache:
  candidates_cache[term]={u for u in k.candidates(term) if kind(u)=='CLASS' and (json.loads(node(u).get('attributes') or '{}').get('allowed_views') is None or 'strict' in json.loads(node(u).get('attributes') or '{}')['allowed_views'])}
 return candidates_cache[term]
def parent(head,scopes=(),exclude_uid=None,context=''):
 key=head,tuple(scopes),exclude_uid,context
 if key in resolved:return resolved[key]
 cleaned=object_kind_head(head).lower()
 if re.match(r'\s*(?:sets?|groups?|pairs?|collections?|bundles?)\s+of\b',cleaned):return None
 cleaned=re.sub(r'\s+(?:concept|prototype|model|design|family|series)$','',cleaned)
 cleaned=re.sub(r'\bkettle drum\b','kettledrum',cleaned)
 words=re.sub(r'[^\w]+',' ',cleaned).split();chosen=None
 for size in range(min(7,len(words)),0,-1):
  cs=candidates(' '.join(words[-size:]))
  if ' '.join(words[-size:])=='device':cs &= k.contextual_candidates('device',context)
  if exclude_uid:cs={v for v in cs if node(v)['component_id']!=node(exclude_uid)['component_id'] and node(exclude_uid)['component_id'] not in ancestors(node(v)['component_id'])}
  preferred_scopes=[d for d in scopes if not (d in {'cars','car'} and re.search(r'\b(?:railroad|railway) car\b',cleaned))]
  within={u for u in cs if any(k.within(u,set(registry.get(d,[]))) for d in preferred_scopes)} if cs else set()
  chosen=k.representative(within) if within else None
  if not chosen and words[-1]=='car' and any(d in {'cars','car'} for d in scopes):
   # WordNet passenger_car is a railway carriage; a road-car definition
   # must fall back to the road sense rather than use that false friend.
   continue
  if not chosen:chosen=k.representative(cs)
  if chosen:break
 resolved[key]=chosen;return chosen

def subject(u):
 n=node(u);raw=json.loads(n['data']);e=raw.get('evidence_record',{});record=definitions.get('wikidata:'+u.split(':')[-1],{})
 desc=n['description'] or raw.get('wikidata_description') or e.get('wikidata_description') or raw.get('description','')
 full=record.get('intro') or raw.get('definition') or e.get('wikipedia_intro') or ''
 text=full or desc
 head=own_head(text,u)
 if not head and desc and text!=desc:head=own_head(desc,u);text=desc
 return head,text,record.get('source_uri') or uri(u)

new_generic_parents=collections.defaultdict(set);ancestor_cache={}
def ancestors(comp):
 if comp in ancestor_cache:return ancestor_cache[comp]
 todo=[comp];seen=set();found=set()
 while todo and len(seen)<3000:
  current=todo.pop()
  if current in seen:continue
  seen.add(current)
  for row in c.execute("SELECT e.id,e.child_uid,e.parent_uid,p.component_id FROM nodes member JOIN edges e ON e.child_uid=member.uid JOIN nodes p ON p.uid=e.parent_uid WHERE member.component_id=? AND member.visibility='ACTIVE' AND e.status='ACTIVE' AND e.relation='IS_A' AND p.visibility='ACTIVE'",(current,)):
   if row['id'] not in edge_ids and kind(row['child_uid'])=='CLASS' and kind(row['parent_uid'])=='CLASS':found.add(row['component_id']);todo.append(row['component_id'])
  for up in new_generic_parents[current]:found.add(up);todo.append(up)
 ancestor_cache[comp]=found;return found

changed=set(desired);edge_ids=set();relation_ids=set();links=set();type_targets={};changed_types={};subject_heads={}
def add_link(u,v,relation,proof):
 if u==v or node(u)['component_id']==node(v)['component_id']:return
 roles=LINK_ROLES.get(relation)
 if not roles or kind(u) not in roles[0] or kind(v) not in roles[1]:
  reviews.append({'uid':u,'parent':v,'reason':'Replacement lacks compatible endpoint grains','roles':[kind(u),kind(v)],'relation':relation});return
 if relation=='IS_A':
  uc=node(u)['component_id'];vc=node(v)['component_id']
  if uc in ancestors(vc):
   reviews.append({'uid':u,'parent':v,'reason':'Nominal inclusion would conflict with an existing semantic ancestor; withheld for review'});return
  new_generic_parents[uc].add(vc);ancestor_cache.clear()
 key=u,v,relation
 if key not in links:emit('link',u,proof,parent=v,relation=relation);links.add(key)
def withdraw_edge(e,proof):
 if e['id'] in edge_ids:return
 emit('withdraw_edge',e['child_uid'],proof,parent=e['parent_uid'],edge_id=e['id']);edge_ids.add(e['id'])
 if kind(e['child_uid'])=='CLASS':ancestor_cache.clear()
def withdraw_typed(e,proof):
 if e['id'] in relation_ids:return
 emit('withdraw_typed',e['subject_uid'],proof,relation_id=e['id']);relation_ids.add(e['id'])

# A corrected subject head overrides an old broad or argument-based parent.
# Recheck every new definitional claim, even if it already has a root path.
for u,n in nodes.items():
 if u.startswith('wordnet31:') or n['source']=='faa' or n['role'] not in {'CLASS','MODEL','MODEL_FAMILY'} or kind(u)=='UNKNOWN':continue
 # These fields explain an organological working principle, often naming
 # strings, air or membranes. Native broader links supply the class hierarchy;
 # the explanatory text cannot define the whole instrument's lexical genus.
 if u.startswith('mimo-hs:'):continue
 head,text,url=subject(u)
 if kind(u)=='CLASS' and re.search(r'\bclassification of steam locomotives\b',text[:350],re.I) and re.search(r'\bis a locomotive with\b',text[:500],re.I):
  # The source's notation explicitly restricts the whole locomotive class
  # to steam traction; the wheel counts do not become vehicle parents.
  head='steam locomotive'
 subject_heads[u]=(head,text)
 target=parent(head,n['scopes'],context=text) if head else None
 # Native generic labels retain structural qualifiers that short descriptions
 # often omit (for example "carrier-based monoplane with 2 engines"). Resolve
 # their literal object-kind phrase against an existing defined source type;
 # never use proper design names or manufacture a grouping from counts.
 if kind(u)=='CLASS' and re.match(r'[a-z]',n['label']) and not re.search(r'\b(?:railroad|railway) car\b',head,re.I):
  label_head=object_kind_head(n['label'])
  label_target=parent(label_head,n['scopes'],exclude_uid=u)
  if label_target and (not target or node(target)['component_id'] in ancestors(node(label_target)['component_id'])):
   head=label_head;target=label_target;text='Native source label: '+n['label']+'; subject definition: '+text
 if target and node(target)['component_id']!=n['component_id']:
  type_targets[u]=target
  if u in changed:
   proof=proof_for(u,'INDEPENDENT_SUBJECT_KIND_WITH_CANONICAL_DESIGN_GRAIN',source_statement=text[:1600],subject_kind_head=head,parent_definition=node(target)['description'],verified_parent_uid=target)
   if kind(u) in {'MODEL','MODEL_FAMILY'}:add_link(u,target,'DESIGN_TYPE_OF',proof)
   elif kind(u)=='INSTANCE':add_link(u,target,'INSTANCE_OF',proof)
  elif kind(u) in {'MODEL','MODEL_FAMILY'}:
   for e in c.execute("SELECT * FROM entity_relations WHERE subject_uid=? AND relation='DESIGN_TYPE_OF' AND status='ACTIVE'",(u,)):
    old=node(e['object_uid'])
    wrong_vehicle_root=(bool(re.search(r'\b(?:engine|motor)\b',head,re.I)) and any(old['component_id']==node(root)['component_id'] for root in registry.get('aircraft',[])))
    if kind(e['object_uid'])=='CLASS' and old['component_id']!=node(target)['component_id'] and (old['component_id'] in ancestors(node(target)['component_id']) or wrong_vehicle_root):
     proof=proof_for(u,'INDEPENDENT_DESIGN_KIND_WITH_CLASS_WITNESS_REFINES_BROAD_TYPE',source_statement=text[:1600],subject_kind_head=head,verified_parent_uid=target,original_relation_id=e['id'],original_parent_uid=e['object_uid'])
     add_link(u,target,'DESIGN_TYPE_OF',proof);withdraw_typed(dict(e),proof)
  elif kind(u)=='CLASS' and k.generic_type(u):
   proof=proof_for(u,'INDEPENDENT_GENERIC_SUBJECT_DEFINITION_ENTAILS_NARROWER_PARENT',source_statement=text[:1600],subject_kind_head=head,verified_parent_uid=target,parent_definition=node(target)['description'])
   add_link(u,target,'IS_A',proof)

# Exact conjunctions of native engine conditions entail broader native
# conjunctions. Count 2 never entails count 3; engine count never entails
# propeller count. All endpoints are existing independently retained classes.
condition_types={u:aircraft_engine_conditions(n['label']) for u,n in nodes.items() if kind(u)=='CLASS' and n['visibility']=='ACTIVE' and 'aircraft' in n['scopes']}
condition_types={u:v for u,v in condition_types.items() if v}
for u,(unit,conditions) in condition_types.items():
 for v,(parent_unit,parent_conditions) in condition_types.items():
  if unit!=parent_unit or not conditions>parent_conditions:continue
  # Retain immediate inclusions; more distant conditions have a real chain.
  if any(w not in {u,v} and middle_unit==unit and conditions>middle>parent_conditions for w,(middle_unit,middle) in condition_types.items()):continue
  proof=proof_for(u,'EXPLICIT_NATIVE_CLASSIFICATION_CONDITIONS_ENTAIL_BROADER_CONJUNCTION',source_statement=node(u)['label'],parent_source_statement=node(v)['label'],native_parent_sha256=hashlib.sha256(node(v)['data'].encode()).hexdigest(),condition_unit=unit,child_conditions=sorted(conditions),parent_conditions=sorted(parent_conditions),verified_parent_uid=v)
  add_link(u,v,'IS_A',proof);type_targets[u]=v

for u,n in nodes.items():
 if u.startswith('wordnet31:'):continue
 for e in c.execute("SELECT * FROM edges WHERE child_uid=? AND status='ACTIVE' AND relation='IS_A'",(u,)):
  e=dict(e);v=e['parent_uid'];pnode=node(v)
  if not pnode:continue
  admitted=kind(u)=='CLASS' and kind(v)=='CLASS'
  data=json.loads(e['data'] or '{}');claim=data.get('admission_basis',{})
  if not isinstance(claim,dict):claim={}
  head=claim.get('object_kind_head') or claim.get('nominal_head') or claim.get('head')
  checked=parent(head,n['scopes']) if head else None
  wrong_head=bool(head and checked and node(checked)['component_id']!=pnode['component_id'])
  if admitted and not wrong_head:
   target=type_targets.get(u)
   head,text=subject_heads.get(u,('',''))
   wrong_aircraft_root=bool(re.search(r'\b(?:air ?base|air station|airfield|airport|component|device|gear|engine|motor)\b',head,re.I)) and any(pnode['component_id']==node(root)['component_id'] for root in registry.get('aircraft',[]))
   wrong_road_root=bool(re.search(r'\b(?:railroad|railway) car\b',head,re.I)) and any(pnode['component_id']==node(root)['component_id'] for root in registry.get('cars',[]))
   if target and target!=v and (u,target,'IS_A') in links and (pnode['component_id'] in ancestors(node(target)['component_id']) or wrong_road_root or wrong_aircraft_root):
    proof=proof_for(u,'INDEPENDENT_GENERIC_PARENT_WITH_SURVIVING_CLASS_WITNESS_REPLACES_ROOT_SHORTCUT',replacement_parent=target,original_edge_id=e['id'])
    if wrong_aircraft_root:proof.update(basis='SOURCE_WHOLE_SUBJECT_KIND_IS_FACILITY_OR_COMPONENT_NOT_AIRCRAFT',subject_kind_head=head,source_statement=text)
    if wrong_road_root:proof.update(basis='SOURCE_DEFINITION_IDENTIFIES_RAILWAY_CARRIAGE_NOT_ROAD_CAR',subject_kind_head=head,source_statement=text)
    withdraw_edge(e,proof)
   else:
    for alternate in c.execute("SELECT id,parent_uid FROM edges WHERE child_uid=? AND status='ACTIVE' AND relation='IS_A' AND id<>?",(u,e['id'])):
     replacement=alternate['parent_uid']
     if alternate['id'] in edge_ids or kind(replacement)!='CLASS' or node(replacement)['component_id'] in {n['component_id'],pnode['component_id']}:continue
     if pnode['component_id'] in ancestors(node(replacement)['component_id']):
      proof=proof_for(u,'EXISTING_GENERIC_PARENT_WITH_SURVIVING_CLASS_WITNESS_REPLACES_BROAD_SHORTCUT',replacement_parent=replacement,alternate_source_edge_id=alternate['id'],original_edge_id=e['id'])
      withdraw_edge(e,proof);break
   continue
  basis='SOURCE_SUBJECT_KIND_REPLACES_LEGACY_ARGUMENT_OR_BROAD_PARENT' if wrong_head else 'CANONICAL_DESIGN_OR_INSTANCE_IS_NOT_ORDINARY_CLASS_INCLUSION'
  proof=proof_for(u,basis,original_edge_id=e['id'],original_parent_uid=v,original_basis=claim,canonical_roles=[kind(u),kind(v)])
  withdraw_edge(e,proof)
  if wrong_head and kind(checked)=='CLASS':
   rel={'CLASS':'IS_A','MODEL':'DESIGN_TYPE_OF','MODEL_FAMILY':'DESIGN_TYPE_OF','INSTANCE':'INSTANCE_OF'}.get(kind(u))
   if rel:add_link(u,checked,rel,{**proof,'correct_subject_kind_head':object_kind_head(head),'verified_parent_uid':checked});changed_types[u]=checked
  elif kind(u) in {'MODEL','MODEL_FAMILY'}:
   if kind(v) in {'MODEL','MODEL_FAMILY'}:add_link(u,v,'NATIVE_DESIGN_PARENT',proof)
   elif kind(v)=='CLASS':
    target=type_targets.get(u) or v
    add_link(u,target,'DESIGN_TYPE_OF',{**proof,'source_scope':'Independent subject kind preferred; original broad native type retained when narrower source evidence is unavailable'})
  elif kind(u)=='INSTANCE' and kind(v) in {'CLASS','MODEL','MODEL_FAMILY'}:add_link(u,type_targets.get(u,v),'INSTANCE_OF',proof)
  elif kind(u)=='CLASS' and kind(v) in {'MODEL','MODEL_FAMILY'}:
   target=type_targets.get(u)
   if target:add_link(u,target,'IS_A',proof)
   else:reviews.append({'uid':u,'reason':'Generic child formerly attached below a design lacks an independently grounded replacement','original_parent_uid':v})

# Existing native typed claims must also satisfy the final source grain.
seen=set()
for u in changed:
 for row in c.execute("SELECT * FROM entity_relations WHERE status='ACTIVE' AND (subject_uid=? OR object_uid=?)",(u,u)):
  e=dict(row)
  if e['id'] in seen:continue
  seen.add(e['id']);rel=e['relation'];u0=e['subject_uid'];v=e['object_uid'];roles=LINK_ROLES.get(rel)
  if not roles or kind(u0) in roles[0] and kind(v) in roles[1]:continue
  proof=proof_for(u0,'TYPED_ENDPOINTS_RECONCILED_WITH_INDEPENDENT_REFERENT_GRAIN',original_relation_id=e['id'],original_relation=rel,canonical_roles=[kind(u0),kind(v)])
  withdraw_typed(e,proof)
  if kind(u0) in {'MODEL','MODEL_FAMILY'} and kind(v) in {'MODEL','MODEL_FAMILY'}:add_link(u0,v,'NATIVE_DESIGN_PARENT',proof)
  elif kind(u0)=='INSTANCE' and kind(v) in {'CLASS','MODEL','MODEL_FAMILY'}:add_link(u0,v,'INSTANCE_OF',proof)
  elif kind(u0) in {'MODEL','MODEL_FAMILY'} and kind(v)=='CLASS':add_link(u0,type_targets.get(u0,v),'DESIGN_TYPE_OF',proof)

records=list({json.dumps(r,sort_keys=True,ensure_ascii=False):r for r in records}.values());path=O/'hierarchy_shape_repairs.jsonl'
with path.open('w') as f:
 for r in records:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
(O/'shape_preparation_reviews.json').write_text(json.dumps(reviews,ensure_ascii=False,indent=2)+'\n')
(O/'shape_preparation_summary.json').write_text(json.dumps({'records':len(records),'operations':dict(counts),'desired_roles':dict(collections.Counter(desired.values())),'role_uids':len(desired),'withdrawn_ISA':len(edge_ids),'withdrawn_typed':len(relation_ids),'source_grounded_links':len(links),'reviews':len(reviews),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n');print('FROZEN SHAPE PROPOSALS',len(records),dict(counts),'reviews',len(reviews),flush=True)
