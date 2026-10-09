#!/usr/bin/env python3
"""Freeze conservative professional refinements from retained native records.

No brand/year grouping, Cartesian products or guessed model equivalences.
The evidence includes exact source-record hashes and scope-specific predicates.
"""
import argparse,collections,hashlib,json,re,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas._text import norm
from fineatlas.semantics import role_expression
from fineatlas.nominal import WordNetKinds
p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--sources',required=True);p.add_argument('--definitions',required=True);p.add_argument('--output',required=True);a=p.parse_args()
c=sqlite3.connect(Path(a.database).resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');c.execute('PRAGMA cache_size=-500000');c.execute('PRAGMA temp_store=MEMORY')
OUT=Path(a.output);OUT.mkdir(parents=True,exist_ok=True);S=Path(a.sources);ROLE=role_expression('n','p');facts=[];classes={};roles={};reviews=[];decisions=collections.Counter();nodecache={}
def sha(text):return hashlib.sha256(text.encode()).hexdigest()
def node(uid):
 if uid not in nodecache:
  row=c.execute('SELECT n.*,'+ROLE+' role,p.attributes FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(uid,)).fetchone();nodecache[uid]=dict(row) if row else None
 return nodecache[uid]
registry={r['canonical_name']:dict(r) for r in c.execute('SELECT * FROM domain_registry')}
def root(domain):return json.loads(registry[domain]['root_uids'])[0]
def proof(basis,**extra):return {'basis':basis,'license':'Original source attribution and terms retained; derived factual classification',**extra}
def add(op,uid,source,uri,pr,**kw):facts.append({'op':op,'uid':uid,'source':source,'uri':uri,'proof':pr,**kw})
def cls(key,label,domain,parents,definition,source,uri,axis='physical_structure',pr=None):
 reused={'aircraft-heavier-than-air':'wikidata:Q154503','aircraft-lighter-than-air':'wikidata:Q1299477','aircraft-powered':'wikidata:Q1949826','aircraft-2':'wikidata:Q183951','aircraft-3':'wikidata:Q133585','aircraft-6':'wikidata:Q949801','aircraft-9':'wikidata:Q208708'}
 uid=reused.get(key,'hierarchy-type:'+key)
 if uid in reused.values():
  for parent in parents:
   if uid!=parent:link(uid,parent,pr or proof('SOURCE_DEFINED_PHYSICAL_TYPE',definition=definition),source,uri,rel='IS_A')
  return uid
 if uid not in classes:
  r={'op':'class','uid':uid,'label':label,'domain':domain,'parents':parents,'definition':definition,'axis':axis,'source':source,'uri':uri,'proof':pr or proof('SOURCE_DEFINED_PHYSICAL_TYPE',definition=definition)};classes[uid]=r
 return uid
def link(uid,parent,pr,source,uri,rel=None):
 role=roles.get(uid,node(uid)['role'] if node(uid) else 'CLASS')
 relation=rel or {'CLASS':'IS_A','MODEL':'DESIGN_TYPE_OF','MODEL_FAMILY':'DESIGN_TYPE_OF','CONFIGURATION':'CONFIGURATION_TYPE_OF','INSTANCE':'INSTANCE_OF'}.get(role)
 if relation:add('link',uid,source,uri,pr,parent=parent,relation=relation)
def withdraw(uid,parent,pr,source,uri):
 for row in c.execute("SELECT id FROM edges WHERE child_uid=? AND parent_uid=? AND status='ACTIVE' AND relation='IS_A'",(uid,parent)):
  add('withdraw_edge',uid,source,uri,pr,parent=parent,edge_id=row[0])
def role(uid,kind,pr,uri):
 n=node(uid)
 if not n:return
 members=[uid]
 if re.match(r'^(?:wikidata|wikidata-v4|v26-wikidata):Q\d+$',uid):
  qid=uid.split(':')[-1];members=[x[0] for x in c.execute('SELECT uid FROM nodes WHERE component_id=? AND uid IN (?,?,?)',(n['component_id'],'wikidata:'+qid,'wikidata-v4:'+qid,'v26-wikidata:'+qid))]
  if kind=='MODEL' and any(node(x)['role']=='MODEL_FAMILY' for x in members):kind='MODEL_FAMILY'
 for member in members:
  if node(member)['role']==kind:continue
  roles[member]=kind;add('role',member,'Retained independent role definitions',uri,{**pr,'native_record_uid':uid},role=kind)
  if kind=='CLASS':
   for rel in c.execute("SELECT id FROM entity_relations WHERE subject_uid=? AND status='ACTIVE' AND relation IN ('DESIGN_TYPE_OF','SERIES_MEMBER_OF')",(member,)):
    add('withdraw_typed',member,'Retained independent role definitions',uri,proof('GENERIC_SUBJECT_IS_NOT_A_NAMED_DESIGN_TERMINAL',role_evidence=pr),relation_id=rel[0])
# An alternative path must be witnessed across identity components before a
# broad source edge can be omitted from the derived hierarchy.
ancestor_cache={}
def ancestor_components(uid):
 comp=node(uid)['component_id']
 if comp in ancestor_cache:return ancestor_cache[comp]
 todo=[comp];seen=set();parents=set()
 while todo and len(seen)<1000:
  current=todo.pop()
  if current in seen:continue
  seen.add(current)
  for e in c.execute("SELECT DISTINCT p.uid,p.component_id FROM nodes x JOIN edges e ON e.child_uid=x.uid JOIN nodes p ON p.uid=e.parent_uid LEFT JOIN node_profiles pp ON pp.uid=p.uid WHERE x.component_id=? AND e.status='ACTIVE' AND e.relation='IS_A' AND p.visibility='ACTIVE' AND "+role_expression('p','pp')+"='CLASS'",(current,)):
   if e[1]!=comp:parents.add(e[1]);todo.append(e[1])
 ancestor_cache[comp]=parents;return parents
def prune_broad(uid,parent,pr,source,uri):
 ancestors=ancestor_components(parent)
 for e in c.execute("SELECT e.id,e.parent_uid,p.component_id FROM edges e JOIN nodes p ON p.uid=e.parent_uid WHERE e.child_uid=? AND e.status='ACTIVE' AND e.relation='IS_A'",(uid,)):
  if e[2] in ancestors:
   add('withdraw_edge',uid,source,uri,proof('EXISTING_GENERIC_INCLUSION_PATH_REPLACES_BROAD_SHORTCUT',replacement_parent=parent,ancestor_component=e[2],member_evidence=pr),parent=e[1],edge_id=e[0])
 for e in c.execute("SELECT e.id,e.object_uid,p.component_id FROM entity_relations e JOIN nodes p ON p.uid=e.object_uid WHERE e.subject_uid=? AND e.status='ACTIVE' AND e.relation IN ('DESIGN_TYPE_OF','CONFIGURATION_TYPE_OF')",(uid,)):
  if e[2] in ancestors:
   add('withdraw_typed',uid,source,uri,proof('EXISTING_GENERIC_INCLUSION_PATH_REPLACES_BROAD_SHORTCUT',replacement_parent=parent,ancestor_component=e[2],member_evidence=pr),relation_id=e[0])
# Source-aware botanical rank, with every retained series record covered.
for row in c.execute("SELECT uid,rank,data FROM nodes WHERE source='wfo' AND lower(rank)='series' AND visibility='ACTIVE'"):
 # Save an explicit current profile even when the fixed shared fallback is CLASS.
 roles[row['uid']]='CLASS';add('role',row['uid'],'WFO botanical rank semantics','https://www.iapt-taxon.org/nomen/pages/main/art_4.html',proof('NATIVE_BOTANICAL_SERIES_RANK',native_rank=row['rank'],native_record_sha256=sha(row['data'])),role='CLASS')
generic=['wikidata:Q385642','wikidata-v4:Q385642','wikidata:Q63759','wikidata:Q63542282','wikidata:Q15078724','wikidata:Q35872']
for uid in generic:
 n=node(uid)
 if n:role(uid,'CLASS',proof('INDEPENDENT_GENERIC_SUBJECT_DEFINITION',definition=n['description'] or json.loads(n['data']).get('evidence_record',{}).get('wikipedia_intro',''),native_record_sha256=sha(n['data'])),'https://www.wikidata.org/wiki/'+uid.split(':')[-1])
for uid in ['wikidata:Q3704893','wikidata-v4:Q3704893']:
 n=node(uid)
 if n:role(uid,'MODEL',proof('IDENTICAL_QID_AUTOMOBILE_SUBJECT',definition=n['description'],native_record_sha256=sha(n['data'])),'https://www.wikidata.org/wiki/Q3704893')
add('split_identity','epa:45337','EPA retained configuration fields','https://www.fueleconomy.gov/feg/ws/index.shtml',proof('CONFIGURATION_AND_GENERATIONAL_DESIGN_HAVE_DIFFERENT_GRAIN',native_record_sha256=sha(node('epa:45337')['data']),fields={k:json.loads(node('epa:45337')['data'])[k] for k in ['year','model','trany','displ']}),parent='wikidata:Q116700422',bridge_id=22711)
link('epa:45337','wikidata:Q116700422',proof('NATIVE_YEAR_CONFIGURATION_OF_GENERATIONAL_DESIGN'),'EPA retained configuration fields','https://www.fueleconomy.gov/feg/ws/index.shtml',rel='CONFIGURATION_OF')
withdraw('wikidata:Q7827640','wikidata:Q1473171',proof('GENERIC_PORTABLE_PC_ALIAS_IS_NOT_IBM_MODEL_IDENTITY'),'Retained independent device definition','https://macdat.net/files/pdf/toshiba/service_manual/t3100.pdf')
role('wikidata:Q7827640','MODEL',proof('NAMED_TOSHIBA_DESIGN_WITH_MANUFACTURER_AND_VERSION_SCOPE',definition=node('wikidata:Q7827640')['description']),'https://macdat.net/files/pdf/toshiba/service_manual/t3100.pdf')
link('wikidata:Q7827640','wikidata:Q1820120',proof('INDEPENDENT_PORTABLE_COMPUTER_DESIGN_DEFINITION'),'Retained independent device definition','https://macdat.net/files/pdf/toshiba/service_manual/t3100.pdf',rel='DESIGN_TYPE_OF')
# FAA type codes: freeze only documented native interpretations.
FAA='https://registry.faa.gov/database/ardata.pdf';FAA_SOURCE='FAA native aircraft reference fields';pdfsha=hashlib.sha256((S/'faa_dictionary.pdf').read_bytes()).hexdigest()
heavier=cls('aircraft-heavier-than-air','heavier-than-air aircraft','aircraft',[root('aircraft')],'An aircraft relying on aerodynamic or propulsive lift rather than buoyancy.',FAA_SOURCE,FAA,pr=proof('FAA_AERODYNAMIC_AIRCRAFT_STRUCTURE',codes=['1','4','5','6','7','8','9'],dictionary_sha256=pdfsha))
lighter=cls('aircraft-lighter-than-air','lighter-than-air aircraft','aircraft',[root('aircraft')],'An aircraft supported through buoyant lift.',FAA_SOURCE,FAA,pr=proof('FAA_BUOYANT_AIRCRAFT_STRUCTURE',codes=['2','3'],dictionary_sha256=pdfsha))
fixed='wikidata:Q2875704'
link(fixed,heavier,proof('FIXED_WING_AERODYNAMIC_STRUCTURE',dictionary_sha256=pdfsha),FAA_SOURCE,FAA,rel='IS_A')
airtypes={'1':('gliding aircraft','An aircraft in the native FAA glider category; self-launching motor gliders are not excluded.'),'2':('balloon','A balloon aircraft supported by buoyancy.'),'3':('airship','A blimp or dirigible aircraft.'),'4':('single-engine fixed-wing aircraft','A fixed-wing aircraft with one engine.'),'5':('multi-engine fixed-wing aircraft','A fixed-wing aircraft with multiple engines.'),'6':('rotorcraft','An aircraft in the native FAA rotorcraft category; no narrower helicopter inference is made.'),'7':('weight-shift-control aircraft','An aircraft controlled by weight shift.'),'8':('powered parachute aircraft','An aircraft in the native powered-parachute category.'),'9':('gyroplane','An aircraft in the native gyroplane category.'),'H':('hybrid-lift aircraft','An aircraft in the native hybrid-lift category.')}
engine={'1':'reciprocating-engine','2':'turboprop','3':'turboshaft','4':'turbojet','5':'turbofan','6':'ramjet','7':'two-cycle-engine','8':'four-cycle-engine','10':'electric-motor','11':'rotary-engine'}
mapped_faa=[]
powered=cls('aircraft-powered','powered aircraft','aircraft',[root('aircraft')],'An aircraft whose propulsion is supplied by a documented engine or motor.',FAA_SOURCE,FAA,'propulsion',proof('FAA_NONZERO_PROPULSION_TYPE',dictionary_sha256=pdfsha))
for n in c.execute("SELECT n.uid,n.label,n.data,e.id FROM nodes n JOIN edges e ON e.child_uid=n.uid WHERE n.source='faa' AND e.parent_uid='v4root:aircraft' AND e.relation='IS_A' AND e.status='ACTIVE' ORDER BY n.uid"):
 data=json.loads(n['data']);code=str(data.get('TYPE-ACFT','')).strip();eng=str(data.get('TYPE-ENG','')).strip();num=str(data.get('NO-ENG','')).strip()
 if code not in airtypes:
  if eng in engine:
   parent=cls('aircraft-propulsion-'+eng,engine[eng]+' aircraft','aircraft',[powered],'A powered aircraft propelled by the documented '+engine[eng]+' engine or motor type.',FAA_SOURCE,FAA,'propulsion',proof('FAA_KNOWN_PROPULSION_WITH_UNRESOLVED_STRUCTURE',engine_code=eng,dictionary_sha256=pdfsha))
   pr=proof('NATIVE_PROPULSION_ONLY_NO_STRUCTURE_GUESS',native_record_sha256=sha(n['data']),native_fields={k:data.get(k) for k in ['CODE','TYPE-ACFT','TYPE-ENG','NO-ENG']},dictionary_sha256=pdfsha)
   link(n['uid'],parent,pr,FAA_SOURCE,FAA,rel='DESIGN_TYPE_OF');withdraw(n['uid'],'v4root:aircraft',pr,FAA_SOURCE,FAA);mapped_faa.append({'uid':n['uid'],'parent':parent,'unresolved_structure':True});continue
  reviews.append({'domain':'aircraft','uid':n['uid'],'reason':'No documented finer native aircraft type','fields':data});continue
 label,definition=airtypes[code];parents=[fixed] if code in {'4','5'} else [lighter] if code in {'2','3'} else [heavier] if code in {'1','6','7','8','9'} else [root('aircraft')]
 if code=='9':
  rotor=cls('aircraft-6',airtypes['6'][0],'aircraft',[heavier],airtypes['6'][1],FAA_SOURCE,FAA,pr=proof('FAA_AIRCRAFT_STRUCTURE',code='6',dictionary_sha256=pdfsha));parents=[rotor]
 parent=cls('aircraft-'+code,label,'aircraft',parents,definition,FAA_SOURCE,FAA,pr=proof('FAA_AIRCRAFT_TYPE_ENUMERATION',code=code,dictionary_sha256=pdfsha))
 conflict=(code=='4' and num.isdigit() and int(num)!=1) or (code=='5' and num.isdigit() and int(num)<=1)
 if conflict:
  reviews.append({'domain':'aircraft','uid':n['uid'],'reason':'Aircraft type and engine count disagree; fixed-wing scope retained','fields':data});parent=fixed
 elif code in {'4','5','6','9'} and eng in engine and (not num.isdigit() or int(num)>0):
  stem=engine[eng]+' '+label
  parent=cls('aircraft-'+code+'-engine-'+eng,stem,'aircraft',[parent],definition+' Propulsion uses the native '+engine[eng]+' engine type.',FAA_SOURCE,FAA,'structure_and_propulsion',proof('OBSERVED_PROFESSIONAL_STRUCTURE_PROPULSION_INTERSECTION',aircraft_code=code,engine_code=eng,dictionary_sha256=pdfsha))
 pr=proof('NATIVE_MODEL_SCOPE_ENTAILS_PROFESSIONAL_TYPE',native_record_sha256=sha(n['data']),native_fields={k:data.get(k) for k in ['CODE','TYPE-ACFT','TYPE-ENG','NO-ENG']},dictionary_sha256=pdfsha,scope='FAA manufacturer/model/series record, not a serial individual')
 link(n['uid'],parent,pr,FAA_SOURCE,FAA,rel='DESIGN_TYPE_OF');withdraw(n['uid'],'v4root:aircraft',pr,FAA_SOURCE,FAA);mapped_faa.append({'uid':n['uid'],'parent':parent,'field_conflict':conflict})
decisions['FAA_mapped']=len(mapped_faa);print('FAA mapped',len(mapped_faa),'classes',len(classes),flush=True)
# Medical scope intersections follow the native WordNet inclusion chains.
medroot=root('medical_devices');medical_cache={};BROAD={'entity','physical entity','object','whole','artifact','instrumentality','device','equipment','instrumentation'}
def medical_type(uid,seen=None):
 if uid in medical_cache:return medical_cache[uid]
 n=node(uid)
 if not n or not uid.startswith('wordnet31:'):return medroot
 medical_domain_id=registry['medical_devices']['domain_id']
 if c.execute("SELECT 1 FROM domain_components WHERE domain_id=? AND view='strict' AND component_id=? AND category='CLASSIFICATION'",(medical_domain_id,n['component_id'])).fetchone():
  medical_cache[uid]=uid;return uid
 if norm(n['label']) in BROAD:return medroot
 seen=(seen or set())|{uid};parents=[]
 for e in c.execute("SELECT parent_uid FROM edges WHERE child_uid=? AND status='ACTIVE' AND relation='IS_A' AND parent_uid LIKE 'wordnet31:%'",(uid,)):
  if e[0] not in seen:parents.append(medical_type(e[0],seen))
 parents=sorted(set(parents)) or [medroot]
 definition='A medical device that is a '+n['label'].replace('_',' ')+'. Physical type definition: '+n['description']
 result=cls('medical-'+uid.replace(':','-'),'medical '+n['label'].replace('_',' '),'medical_devices',sorted(set(parents+[uid])),definition,'FDA physical-head scope and WordNet native inclusion','https://open.fda.gov/apis/device/classification/','medical_physical_structure',proof('MEDICAL_DEVICE_INTERSECTION_WITH_VERIFIED_NATIVE_PHYSICAL_TYPE',physical_uid=uid,physical_definition=n['description'],logical_form=['medical_device',uid]))
 medical_cache[uid]=result;return result
medical_count=0
for row in c.execute("SELECT n.uid,n.data FROM nodes n JOIN node_profiles p ON p.uid=n.uid WHERE n.source='openFDA device classification' AND n.visibility='ACTIVE' AND p.node_kind='CLASS' AND EXISTS(SELECT 1 FROM json_each(p.attributes,'$.allowed_views') x WHERE x.value='strict') ORDER BY n.uid"):
 data=json.loads(row['data']);physical=data.get('nominal_physical_type_uid')
 if not physical:continue
 parent=medical_type(physical)
 if parent==medroot:continue
 pr=proof('RETAINED_VERIFIED_PHYSICAL_HEAD_REFINEMENT',native_record_sha256=sha(row['data']),physical_type_uid=physical,product_code=data.get('product_code'),source_sha256=data.get('source_sha256'),regulatory_code_is_not_a_physical_parent=True)
 link(row['uid'],parent,pr,'FDA physical-head scope and WordNet native inclusion','https://open.fda.gov/apis/device/classification/',rel='IS_A');withdraw(row['uid'],medroot,pr,'FDA physical-head scope and WordNet native inclusion','https://open.fda.gov/apis/device/classification/');medical_count+=1
decisions['FDA_physical_types_refined']=medical_count;print('Medical refined',medical_count,flush=True)
# Controlled propulsion types are applied to EPA configurations only.
carroot=root('cars');EPA='https://www.fueleconomy.gov/feg/ws/index.shtml';combustion=cls('car-combustion','internal-combustion-powered car','cars',[carroot],'A car configuration powered by an internal combustion engine.','EPA retained powertrain fields',EPA,'propulsion')
carpower={};epa_count=0
for row in c.execute("SELECT n.uid,n.data FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.source='epa' AND n.visibility='ACTIVE' AND "+ROLE+"='CONFIGURATION' ORDER BY n.uid"):
 d=json.loads(row['data']);fuel=d.get('fuelType1','');alt=d.get('atvType','');vclass=d.get('VClass','')
 # A non-car light truck must not acquire a passenger-car classification.
 if not any(x in vclass for x in ['Cars','Station Wagons']):continue
 kind='electric' if fuel=='Electricity' else 'hybrid' if 'Hybrid' in alt else 'diesel' if fuel=='Diesel' else 'gasoline' if 'Gasoline' in fuel else None
 if not kind:continue
 if kind not in carpower:
  pp=[carroot] if kind in {'electric','hybrid'} else [combustion]
  carpower[kind]=cls('car-'+kind,kind+'-powered car','cars',pp,'A car configuration whose documented powertrain is '+kind+'.','EPA retained powertrain fields',EPA,'propulsion',proof('NATIVE_CONFIGURATION_POWERTRAIN_TYPE',powertrain=kind))
 pr=proof('NATIVE_CONFIGURATION_FIELDS_ONLY',native_record_sha256=sha(row['data']),fields={k:d.get(k) for k in ['VClass','fuelType1','fuelType2','atvType','year','model']},no_lifting_to_entire_model=True)
 link(row['uid'],carpower[kind],pr,'EPA retained powertrain fields',EPA,rel='CONFIGURATION_TYPE_OF');epa_count+=1
decisions['EPA_configurations_classified']=epa_count;print('EPA classified',epa_count,flush=True)
# Retain the native ENVO source hierarchy within explicitly reviewed feature scopes.
terms=json.loads((S/'envo_terms.json').read_text());envo_sha=hashlib.sha256((S/'envo.obo').read_bytes()).hexdigest();scope_labels={'mountain range':'mountain_ranges','mountain':'mountains','waterfall':'waterfalls','river':'rivers','lake':'lakes','island':'islands','beach':'beaches','valley':'valleys','volcano':'volcanoes','glacier':'glaciers','aquifer':'aquifers','cloud':'clouds','desert':'deserts'}
children=collections.defaultdict(list)
for uid,t in terms.items():
 if t['obsolete']=='true':continue
 for parent in t['is_a']:children[parent].append(uid)
native_added={}
for label,domain in scope_labels.items():
 seed=next(uid for uid,t in terms.items() if t['name']==label);todo=list(children[seed]);selected=set()
 while todo:
  uid=todo.pop()
  if uid in selected:continue
  selected.add(uid);todo.extend(children[uid])
 for uid in sorted(selected):
  t=terms[uid];native_uid='envo:'+uid.replace(':','_')
  if node(native_uid):continue
  parents=[root(domain) if x==seed else 'envo:'+x.replace(':','_') for x in t['is_a'] if x==seed or x in selected]
  if not parents:continue
  # Root source record is retained in the frozen ontology; root correspondence
  # supplies scope, not a duplicate artificial intermediate concept.
  definition=t['definition'];pr=proof('NATIVE_ENVO_IS_A_WITH_REVIEWED_FEATURE_ROOT_SCOPE',native_id=uid,native_parent_ids=t['is_a'],scope_source_id=seed,canonical_scope_uid=root(domain),scope_definition=terms[seed]['definition'],source_sha256=envo_sha)
  classes[native_uid]={'op':'class','uid':native_uid,'label':t['name'],'domain':domain,'parents':parents,'definition':definition or 'Native ENVO subtype of '+label+'.','axis':'native_environmental_feature','source':'Environment Ontology native is_a','uri':'http://purl.obolibrary.org/obo/'+uid.replace(':','_'),'proof':pr};native_added[uid]=domain
decisions['ENVO_feature_classes']=len(native_added);print('ENVO feature classes',len(native_added),flush=True)
# Physical capacitor mounting is documented by the retained catalogue heading.
caproot=root('ceramic_capacitors');mlcc='vishay-type:multilayer-ceramic-capacitor';capuri='https://www.murata.com/products/capacitor/ceramiccapacitor/overview/lineup';capsha=hashlib.sha256((S/'murata_lineup.html').read_bytes()).hexdigest()
chip=cls('chip-mlcc','chip multilayer ceramic capacitor','ceramic_capacitors',[mlcc],'A multilayer ceramic capacitor constructed in chip form for surface mounting.','Murata chip monolithic ceramic capacitor catalogue',capuri,'construction_and_mounting',proof('EXPLICIT_CATALOGUE_CHIP_MONOLITHIC_HEADING',source_sha256=capsha,retained_catalogue='C02E-16'))
for n in c.execute("SELECT uid,data FROM nodes WHERE uid LIKE 'murata-series:%' AND visibility='ACTIVE' ORDER BY uid"):
 pr=proof('RETAINED_CHIP_MONOLITHIC_SERIES_CATALOGUE_SCOPE',native_record_sha256=sha(n['data']),catalogue='C02E-16',series=n['uid'].split(':')[-1])
 link(n['uid'],chip,pr,'Murata chip monolithic ceramic capacitor catalogue',capuri,rel='DESIGN_TYPE_OF')
 # Original broad type remains a valid recorded statement, but ceases to be
 # the only shortest catalogue route in the canonical derived graph.
 for rel in c.execute("SELECT id FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation='DESIGN_TYPE_OF' AND status='ACTIVE'",(n['uid'],caproot)):
  add('withdraw_typed',n['uid'],'Murata chip monolithic ceramic capacitor catalogue',capuri,pr,relation_id=rel[0])
# General retained-definition heads: only a verified generic parent can be used.
definitions=json.loads(Path(a.definitions).read_text());kinds=WordNetKinds(c,include_native=True)
scope_domains=[d for d in registry if d not in {'plants','animals','birds','fungi','bacteria','archaea'} and 'habitat' not in d]
rows=c.execute('SELECT n.uid,n.label,n.description,n.data,n.source,n.rank,'+ROLE+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility=\'ACTIVE\' AND (n.source LIKE \'%independent%\' OR n.rank IN (\'named_refinement\',\'type_or_product_model\')) ORDER BY n.uid').fetchall()
head_count=0
for n in rows:
 if n['role'] in {'INSTANCE','ORGANIZATION','ATTRIBUTE','BIOLOGICAL_VARIANT','DATASET_CATEGORY','UNKNOWN'}:continue
 raw=json.loads(n['data']);record=definitions.get('wikidata:'+n['uid'].split(':')[-1],{});intro=record.get('intro') or raw.get('definition') or n['description']
 statement=re.sub(r'\([^()]*\)','',intro)
 match=re.search(r'\b(?:is|was|are|were)\s+(?:an?|the)\s+([^.;]{1,180})',statement,re.I)
 if not match:continue
 head=re.split(r'\b(?:that|which|with|for|designed|developed|built|produced|manufactured|made|introduced|released|sold|unveiled|awarded|announced|by|since|from|used|as|and|but)\b',match[1],maxsplit=1,flags=re.I)[0].strip(' ,')
 if re.search(r'\b(?:program|project|nameplate|proposal|concept|study)\s*$',head,re.I):continue
 # A positive independent design declaration needs a proper product subject
 # plus manufacturing/development or an explicit design-family definition.
 named=bool(re.match(r'[A-Z][a-z]{2,}\b[^.]{0,70}\d',n['label']) or re.search(r'\b[A-Z]{2,}[- ]?\d',n['label']) or (re.match(r'[A-Z]',n['label']) and re.search(r'\b(?:designed|manufactured|produced|developed|made) by\b',statement[:500],re.I)))
 if re.search(r'\b(?:serial number|registration number|tail number|sole example|only example|wrecked|sank|scrapped)\b',statement[:600],re.I):continue
 declared_design=bool(re.search(r'\b(?:manufactured|developed|produced|released|introduced|designed)\b',statement[:500],re.I))
 family=bool(re.search(r'\b(?:family|series) of\b',head,re.I))
 parent=kinds.resolve_head(head)
 if not parent or parent==n['uid'] or not kinds.artifact_type(parent):continue
 if c.execute("SELECT 1 FROM entity_relations WHERE subject_uid=? AND relation='INSTANCE_OF' AND status='ACTIVE' LIMIT 1",(n['uid'],)).fetchone():continue
 if named and (declared_design or family) and n['role']=='CLASS':
  role(n['uid'],'MODEL_FAMILY' if family else 'MODEL',proof('NAMED_DESIGN_WITH_INDEPENDENT_DEFINITION',label=n['label'],sentence=statement[:600],native_record_sha256=sha(n['data'])),record.get('source_uri') or 'https://www.wikidata.org/wiki/'+n['uid'].split(':')[-1])
  for r in c.execute("SELECT id FROM entity_relations WHERE subject_uid=? AND relation='INSTANCE_OF' AND status='ACTIVE'",(n['uid'],)):
   add('withdraw_typed',n['uid'],'Independent design and grain evidence',record.get('source_uri') or 'https://www.wikidata.org/wiki/'+n['uid'].split(':')[-1],proof('CONFLICTING_DESIGN_OR_INSTANCE_REQUIRES_REVIEW',sentence=statement[:600]),relation_id=r[0])
 # Adding already supported narrower parents is safe; removing a broad parent
 # is done only after an actual existing inclusion path is witnessed.
 if not kinds.generic_type(parent) or roles.get(parent,node(parent)['role'])!='CLASS':continue
 nn=node(parent)
 if nn['component_id']==node(n['uid'])['component_id']:continue
 pr=proof('INDEPENDENT_NOMINAL_HEAD_AND_GENERIC_PARENT_DEFINITION',native_record_sha256=sha(n['data']),sentence=statement[:600],head=head,parent_definition=nn['description'],parent_uid=parent)
 uri=record.get('source_uri') or raw.get('source_uri') or 'https://www.wikidata.org/wiki/'+n['uid'].split(':')[-1]
 link(n['uid'],parent,pr,'Retained independent generic-head definition',uri);prune_broad(n['uid'],parent,pr,'Retained independent generic-head definition',uri);head_count+=1
decisions['retained_definition_professional_links']=head_count
output=OUT/'hierarchy_facts.jsonl';allrecords=list({json.dumps(r,ensure_ascii=False,sort_keys=True):r for r in list(classes.values())+facts}.values())
with output.open('w') as f:
 for r in allrecords:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
(OUT/'hierarchy_preparation.json').write_text(json.dumps({'classes':len(classes),'operations':len(allrecords),'counts':dict(decisions),'reviews':len(reviews),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n')
(OUT/'hierarchy_source_reviews.json').write_text(json.dumps(reviews,ensure_ascii=False,indent=2)+'\n');(OUT/'FAA_mapping.json').write_text(json.dumps(mapped_faa,ensure_ascii=False,indent=2)+'\n')
(OUT/'hierarchy_facts.incomplete').unlink(missing_ok=True)
print('COMPLETE',len(classes),len(allrecords),dict(decisions),flush=True)
