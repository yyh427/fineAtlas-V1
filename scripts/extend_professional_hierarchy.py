#!/usr/bin/env python3
"""Add controlled, member-evidenced engineering type intersections.

Predicates are restricted to established structure, operating principle and
functional type terms. No classifier uses a brand, year, price, size threshold
or catalogue folder as an ordinary parent. Broad families are not narrowed
from an incidental feature mentioned later in their description.
"""
import argparse,collections,hashlib,json,re,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas._text import norm
from fineatlas.semantics import role_expression
from fineatlas.nominal import DEFINITION_SQL
from bs4 import BeautifulSoup
p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--inputs',required=True);p.add_argument('--definitions',required=True);p.add_argument('--sources',required=True);a=p.parse_args()
I=Path(a.inputs);S=Path(a.sources);definitions=json.loads(Path(a.definitions).read_text());c=sqlite3.connect(Path(a.database).resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');c.execute('PRAGMA cache_size=-500000')
core=I/'hierarchy_facts.jsonl';records=[json.loads(l) for l in core.open() if l.strip()];extension_summary=I/'engineering_refinement_summary.json'
if extension_summary.exists() and hashlib.sha256(core.read_bytes()).hexdigest()==json.loads(extension_summary.read_text())['sha256']:records=records[:-json.loads(extension_summary.read_text())['new_operations']]
current_roles={r['uid']:r['role'] for r in records if r['op']=='role'};ROOTS={r['canonical_name']:json.loads(r['root_uids']) for r in c.execute('SELECT * FROM domain_registry')}
for domain,roots in list(ROOTS.items()):
 generic=[]
 for uid in roots:
  kind=c.execute('SELECT '+role_expression('n','p')+' FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(uid,)).fetchone()[0]
  if current_roles.get(uid,kind)=='CLASS':generic.append(uid)
 if generic:ROOTS[domain]=generic
 else:raise ValueError('Domain lacks a generic root: '+domain)
def sha(x):return hashlib.sha256(x.encode()).hexdigest()
# (domain, key, label, parent keys, evidence phrase, precise predicate)
RULES=[]
def add(domain,key,label,parents,pattern,predicate):RULES.append({'domain':domain,'key':key,'label':label,'parents':parents,'pattern':re.compile(pattern,re.I),'predicate':predicate})
add('aircraft','fixed-wing','fixed-wing aircraft',[],r'fixed[ -]wing aircraft|\b(?:airplane|monoplane)\b','is a fixed-wing aircraft')
add('aircraft','4','single-engine fixed-wing aircraft',['fixed-wing'],r'single[ -](?:engine|engined)[^.]{0,70}(?:airplane|monoplane)','has one engine and a fixed-wing structure')
add('aircraft','5','multi-engine fixed-wing aircraft',['fixed-wing'],r'(?:multi|twin|two|four)[ -](?:engine|engined)[^.]{0,70}(?:airplane|monoplane)','has multiple engines and a fixed-wing structure')
for domain in ['computer_monitors','television_sets']:
 noun='computer monitor' if domain=='computer_monitors' else 'television set'
 add(domain,'flat','flat-panel '+noun,[],r'flat[ -]panel|\b(?:LCD|OLED|plasma)\b','uses a flat-panel display technology')
 add(domain,'lcd','LCD '+noun,['flat'],r'\bLCD\b|liquid[ -]crystal','uses liquid-crystal display technology')
 add(domain,'oled','OLED '+noun,['flat'],r'\bOLED\b|organic light[ -]emitting','uses an organic light-emitting display panel')
 add(domain,'plasma','plasma-panel '+noun,['flat'],r'plasma (?:panel|display|television|TV|screen)','uses a plasma display panel')
 add(domain,'crt','CRT '+noun,[],r'\bCRT\b|cathode[ -]ray','uses a cathode-ray-tube display')
for domain in ['cameras','digital_cameras']:
 if domain!='digital_cameras':add(domain,'slr','single-lens-reflex camera',[],r'single[ -]lens reflex|\b(?:SLR|DSLR)\b','uses a single-lens-reflex optical arrangement')
 add(domain,'dslr','digital single-lens-reflex camera',[] if domain=='digital_cameras' else ['slr'],r'digital single[ -]lens reflex|\bDSLR\b','is a digital camera with a single-lens-reflex arrangement')
 add(domain,'mirrorless','mirrorless interchangeable-lens '+('digital camera' if domain=='digital_cameras' else 'camera'),[],r'mirrorless (?:digital )?interchangeable[ -]lens|\bMILC\b','has an interchangeable lens and no reflex mirror')
 add(domain,'compact','compact '+('digital camera' if domain=='digital_cameras' else 'camera'),[],r'compact (?:digital )?camera|point[ -]and[ -]shoot','is a compact camera')
add('camera_lenses','zoom','zoom camera lens',[],r'zoom lens','has a variable focal length for imaging')
add('camera_lenses','prime','prime camera lens',[],r'prime lens|fixed[ -]focal[ -]length lens','has a fixed focal length for imaging')
add('camera_lenses','macro','macro camera lens',[],r'macro lens','is designed for close-up macro imaging')
add('camera_lenses','telephoto','telephoto camera lens',[],r'telephoto lens','uses a telephoto imaging-lens design')
add('network_switches','managed','managed network switch',[],r'\bmanaged\b(?:[ -]+[\w+/-]+){0,5}[ -]+switch','provides switch-management and configuration functions')
add('network_switches','smart','web-managed smart network switch',['managed'],r'\b(?:Easy Smart|Smart Managed|Smart) (?:\w+[ -]+){0,3}Switch','provides web-based switch management functions')
add('network_switches','unmanaged','unmanaged network switch',[],r'\bunmanaged\b(?:[ -]+[\w+/-]+){0,5}[ -]+switch','is an unmanaged network switching device')
add('network_switches','modular','modular network switch',[],r'modular (?:network |Ethernet )?switch|modular chassis','has a modular switching hardware structure')
add('network_routers','wireless','wireless network router',[],r'wireless[ -]+router|Wi[ -]?Fi(?:[ -]+[\w+/-]+){0,4}[ -]+router|WLAN[ -]+router','provides wireless routing functions')
add('network_routers','wifi6','Wi-Fi 6 network router',['wireless'],r'Wi[ -]?Fi[ -]+6(?![E\w])','supports Wi-Fi 6 (IEEE 802.11ax) wireless networking')
add('network_routers','wifi6e','Wi-Fi 6E network router',['wifi6'],r'Wi[ -]?Fi[ -]+6E\b','supports Wi-Fi 6E wireless networking')
add('network_routers','wifi7','Wi-Fi 7 network router',['wireless'],r'Wi[ -]?Fi[ -]+7\b','supports Wi-Fi 7 (IEEE 802.11be) wireless networking')
add('network_routers','dsl','DSL modem-router',[],r'(?:A?DSL|VDSL)(?:2\+?)? (?:modem[ -]?)?router','combines DSL modem access with routing')
add('solid_state_drives','flash','flash-memory solid-state drive',[],r'\bNAND\b|flash[ -](?:memory|based)','uses flash memory as its storage medium')
add('solid_state_drives','nvme','NVMe solid-state drive',[],r'\bNVMe\b','supports the Non-Volatile Memory Express storage interface')
add('solid_state_drives','sata','SATA solid-state drive',[],r'\bSATA\b','uses a Serial ATA storage interface')
add('solid_state_drives','external','external solid-state drive',[],r'portable SSD|external (?:solid[ -]state|SSD)','is a solid-state drive designed for external connection')
add('solid_state_drives','usb','USB external solid-state drive',['external'],r'USB[^.]{0,40}(?:SSD|solid)|(?:SSD|solid)[^.]{0,40}USB','is an external solid-state drive using a USB connection')
add('solid_state_drives','m2nvme','M.2 NVMe solid-state drive',['nvme'],r'(?=.*\bNVMe\b)(?=.*\bM\.?2\b)','supports NVMe and has an M.2 physical form factor')
for domain in ['integrated_circuits','source_integrated_circuits']:
 add(domain,'analog','analog integrated circuit',[],r'analog (?:integrated circuit|IC)|analogue (?:integrated circuit|IC)','implements analog integrated-circuit operation')
 add(domain,'digital','digital integrated circuit',[],r'digital (?:integrated circuit|IC)','implements digital integrated-circuit operation')
 add(domain,'mixed','mixed-signal integrated circuit',[],r'mixed[ -]signal (?:integrated circuit|IC)','combines analog and digital operation in an integrated circuit')
 add(domain,'memory','memory integrated circuit',[],r'memory (?:integrated circuit|IC|chip)','is an integrated circuit used for data storage')
 add(domain,'programmable','programmable logic integrated circuit',[],r'field[ -]programmable gate array|\bFPGA\b|programmable logic (?:device|IC)','implements programmable logic in an integrated circuit')
for domain in ['semiconductor_diodes','source_semiconductor_diodes','semiconductor_devices']:
 add(domain,'junction','junction semiconductor diode',[],r'p[ -]?n[ -]junction (?:semiconductor )?diode|junction diode','operates as a semiconductor junction diode')
 add(domain,'schottky','Schottky semiconductor diode',[],r'Schottky (?:barrier )?diode','uses a metal-semiconductor Schottky junction')
 add(domain,'led','light-emitting semiconductor diode',[],r'light[ -]emitting (?:semiconductor )?diode|\bLED diode\b','emits light through semiconductor diode operation')
 add(domain,'laser','semiconductor laser diode',[],r'laser diode','operates as a semiconductor diode laser')
 add(domain,'rectifier','semiconductor rectifier diode',[],r'rectifier diode','is a semiconductor diode used for rectification')
add('microprocessors','risc','RISC microprocessor',[],r'\bRISC\b|reduced instruction set','implements a reduced-instruction-set processor architecture')
add('microprocessors','cisc','CISC microprocessor',[],r'\bCISC\b|complex instruction set','implements a complex-instruction-set processor architecture')
add('gpus','integrated','integrated graphics processing unit',[],r'integrated (?:graphics processing unit|graphics processor|GPU)','is implemented as an integrated graphics processing unit')
add('gpus','discrete','discrete graphics processing unit',[],r'discrete (?:graphics processing unit|graphics processor|GPU)','is implemented as a discrete graphics processing unit')
add('graphics_cards','discrete','discrete graphics card',[],r'discrete graphics card|add[ -]in (?:graphics|video) (?:card|board)','is an add-in graphics board')
add('printers','inkjet','inkjet printer',[],r'ink[ -]?jet','prints by depositing ink droplets')
add('printers','laser','laser printer',[],r'laser printer','prints through a laser-based electrostatic printing process')
add('printers','thermal','thermal printer',[],r'thermal printer','prints through a thermal printing process')
add('printers','dotmatrix','dot-matrix printer',[],r'dot[ -]matrix printer','prints through dot-matrix impact printing')
add('desktop_computers','aio','all-in-one desktop computer',[],r'all[ -]in[ -]one (?:desktop|computer|PC)','integrates the desktop computer and display in one assembly')
add('desktop_computers','workstation','desktop workstation',[],r'desktop workstation|workstation computer','is a desktop workstation computer')
add('laptops','convertible','convertible laptop computer',[],r'convertible (?:laptop|notebook)|2[ -]in[ -]1 (?:laptop|notebook)','has a convertible laptop structure')
add('laptops','detachable','detachable laptop computer',[],r'detachable (?:laptop|notebook)|detachable keyboard','has a detachable laptop keyboard/display structure')
add('tablets','slate','slate tablet computer',[],r'slate (?:tablet|computer)|slate[ -]style','has a slate tablet structure')
add('single_board_computers','stick','stick personal computer',[],r'\bstick PC\b|PC on a stick','is a single-board personal computer in an elongated plug-in enclosure')
add('single_board_computers','embedded','embedded single-board computer',[],r'embedded (?:single[ -]board|computer)|embedded computing','is a single-board computer designed for embedded computing')
add('smartphones','foldable','foldable smartphone',[],r'foldable smartphone|folding smartphone','has a folding smartphone display/structure')
add('smartphones','clamshell','clamshell foldable smartphone',['foldable'],r'clamshell (?:foldable )?smartphone|foldable clamshell|foldable flip (?:phone|smartphone)','has a clamshell folding smartphone structure')
add('smartphones','book','book-style foldable smartphone',['foldable'],r'book[ -](?:style|type) foldable|book[ -]like fold','has a book-style folding smartphone structure')
add('headphones','overear','over-ear headphones',[],r'over[ -]ear|circumaural','has an over-ear headphone structure')
add('headphones','onear','on-ear headphones',[],r'on[ -]ear|supra[ -]aural','has an on-ear headphone structure')
add('headphones','inear','in-ear headphones',[],r'in[ -]ear|earbud','has an in-ear headphone structure')
add('earbuds','wired','wired earbud',[],r'wired (?:earbud|in[ -]ear)','connects through a physical audio cable')
add('earbuds','wireless','wireless earbud',[],r'wireless[ -]+(?:earbud|in[ -]ear)','has a wireless earbud structure')
add('earbuds','truewireless','true-wireless earbud',['wireless'],r'true[ -]wireless','has a true-wireless earbud structure')
add('loudspeakers','dynamic','moving-coil loudspeaker',[],r'moving[ -]coil|dynamic loudspeaker','uses a moving-coil acoustic transducer')
add('loudspeakers','electrostatic','electrostatic loudspeaker',[],r'electrostatic (?:speaker|loudspeaker)','uses an electrostatic acoustic transducer')
add('smartwatches','hybrid','hybrid smartwatch',[],r'["“]?hybrid["”]?[ -]+smartwatch|hybrid smart watch','combines a conventional watch display with smartwatch functions')
add('smartwatches','gps','GPS smartwatch',[],r'GPS smartwatch|GPS smart watch','is a smartwatch with GPS functionality')
add('fitness_trackers','wearable','wearable fitness tracker',[],r'wearable (?:fitness|activity) tracker|fitness band|smart band|activity band','is a fitness tracker designed to be worn on the body')
add('fitness_trackers','wrist','wrist-worn fitness tracker',['wearable'],r'wrist[ -](?:worn|based|band)|fitness band|smart band|activity band','is a wearable fitness tracker designed for the wrist')
add('wearable_computers','wrist','wrist-worn wearable computer',[],r'smartwatch|smart watch|fitness band|wrist[ -](?:worn|based|band)','is a wearable computer designed for the wrist')
add('wearable_computers','head','head-worn wearable computer',[],r'head[ -]mounted|smart glasses','is a wearable computer designed for the head')
add('locomotives','steam','steam locomotive',[],r'steam locomotive','is propelled through a steam locomotive power system')
add('locomotives','diesel','diesel locomotive',[],r'diesel(?:[ -](?:electric|hydraulic))? locomotive','is propelled through a diesel locomotive power system')
add('locomotives','dieselelectric','diesel-electric locomotive',['diesel'],r'diesel[ -]electric locomotive','uses diesel-electric power transmission')
add('locomotives','dieselhydraulic','diesel-hydraulic locomotive',['diesel'],r'diesel[ -]hydraulic locomotive','uses diesel-hydraulic power transmission')
add('locomotives','electric','electric locomotive',[],r'(?<!diesel[ -])electric locomotive','uses an electric locomotive power system')
add('tractors','tracked','tracked tractor',[],r'tracked tractor|crawler tractor','uses a tracked tractor running structure')
add('tractors','wheeled','wheeled tractor',[],r'wheeled tractor|wheel tractor','uses a wheeled tractor running structure')
add('ships','sailing','sailing ship',[],r'sailing ship|sailboat','is a ship propelled through sails')
add('ships','motor','motor ship',[],r'motor ship|motor vessel','is a ship propelled through engines')
add('game_consoles','home','home video game console',[],r'home (?:video )?game console|home (?:video )?gaming console','is designed for stationary home use with an external display')
add('game_consoles','handheld','handheld video game console',[],r'handheld (?:video )?game console|handheld (?:video )?gaming console','is a portable video game console with integrated controls and display')
add('game_consoles','hybrid','hybrid video game console',[],r'hybrid (?:video )?game console','supports both stationary television and handheld video-game operation')
bydomain=collections.defaultdict(list)
for rule in RULES:bydomain[rule['domain']].append(rule)
types={};named_types={};members=collections.Counter();new=[];withheld=[]
types['aircraft','fixed-wing']='wikidata:Q2875704'
types['network_routers','wireless']='tplink-type:wi-fi-router'
types['network_switches','unmanaged']='tplink-type:unmanaged-network-switch'
types['smartphones','foldable']='wikidata:Q63542282'
for r in records:
 if r['op']=='class' and r['uid'].startswith('hierarchy-type:aircraft-'):
  for rule in bydomain['aircraft']:
   if norm(rule['label'])==norm(r['label']):types['aircraft',rule['key']]=r['uid']
def class_uid(rule,origin):
 key=rule['domain'],rule['key']
 if key in types:return types[key]
 if rule['label'] in named_types:
  types[key]=named_types[rule['label']];return types[key]
 # Reuse an independently declared generic type with this exact name.
 candidates=[]
 for row in c.execute('SELECT n.uid,n.label,'+DEFINITION_SQL+' description,'+role_expression('n','p')+' role FROM aliases a JOIN nodes n ON n.uid=a.uid LEFT JOIN node_profiles p ON p.uid=n.uid WHERE a.alias=? AND n.visibility=?',(norm(rule['label']),'ACTIVE')):
  if current_roles.get(row['uid'],row['role'])=='CLASS' and (row['uid'].startswith('wordnet31:') or re.search(r'\b(?:is a|is an|type of|class of)\b',row['description'],re.I)):
   candidates.append(row['uid'])
 uid=sorted(set(candidates),key=lambda x:(not x.startswith('wikidata:'),x))[0] if candidates else 'hierarchy-type:'+rule['domain']+'-'+rule['key']
 types[key]=uid;named_types[rule['label']]=uid
 parent_uids=[]
 for parentkey in rule['parents']:
  parent=next(x for x in bydomain[rule['domain']] if x['key']==parentkey);parent_uids.append(class_uid(parent,origin))
 parent_uids=parent_uids or [ROOTS[rule['domain']][0]]
 rootlabel=c.execute('SELECT label FROM nodes WHERE uid=?',(ROOTS[rule['domain']][0],)).fetchone()[0].replace('_',' ')
 definition='An object of the '+rootlabel+' type that '+rule['predicate']+'.'
 pr={'basis':'CONTROLLED_PROFESSIONAL_TYPE_PREDICATE_WITH_SOURCE_DECLARED_MEMBER','definition':definition,'predicate':rule['predicate'],'native_member_uid':origin['uid'],'native_member_record_sha256':origin['record_sha256'],'source_statement':origin['statement'],'source_uri':origin['uri'],'license':'Retained source attribution; derived factual and logical type definition'}
 if uid.startswith('hierarchy-type:'):
  new.append({'op':'class','uid':uid,'label':rule['label'],'domain':rule['domain'],'parents':parent_uids,'definition':definition,'axis':'structure_or_operating_principle','source':'Retained source professional type predicates','uri':origin['uri'],'proof':pr})
 else:
  for parent in parent_uids:
   if uid!=parent:new.append({'op':'link','uid':uid,'parent':parent,'relation':'IS_A','source':'Retained source professional type predicates','uri':origin['uri'],'proof':pr})
 return uid
garmin_manifest=json.loads((S/'garmin_manifest.json').read_text())
for domain,rules in bydomain.items():
 domain_id=c.execute('SELECT domain_id FROM domain_registry WHERE canonical_name=?',(domain,)).fetchone()[0]
 for n in c.execute('SELECT n.uid,n.label,n.description,n.data,'+role_expression('n','p')+' role,p.source_uri FROM domain_members m JOIN nodes n ON n.uid=m.uid LEFT JOIN node_profiles p ON p.uid=n.uid WHERE m.domain_id=? AND m.view=? ORDER BY n.uid',(domain_id,'strict')):
  role=current_roles.get(n['uid'],n['role'])
  if role not in {'CLASS','MODEL','MODEL_FAMILY','CONFIGURATION','INSTANCE'}:continue
  if n['uid'] in ROOTS[domain]:continue
  raw=json.loads(n['data']);record=definitions.get('wikidata:'+n['uid'].split(':')[-1],{});intro=record.get('intro') or raw.get('definition') or n['description']
  statement=re.sub(r'\([^()]*\)','',intro).split('. ')[0][:800]
  payload=raw.get('source_record',{})
  name=payload.get('native_name') or payload.get('name') or raw.get('manufacturer_designation') or ''
  # Native structured model descriptions are explicit fields, not site menus.
  native_description=payload.get('description','')
  if native_description and not record.get('intro'):statement=native_description[:800]
  # Freeze a bounded primary product description for Garmin wearables. Never
  # scan navigation or footer text to infer a product feature.
  extra_statement=''
  if raw.get('publisher')=='Garmin' and raw.get('source_sha256'):
   for entry in garmin_manifest:
    if entry.get('sha256')!=raw['source_sha256']:continue
    body=(S/entry['path']).read_bytes()
    if hashlib.sha256(body).hexdigest()!=entry['sha256']:raise ValueError('Garmin source checksum mismatch')
    soup=BeautifulSoup(body,'html.parser');info=soup.select_one('#product-info')
    if info:extra_statement=info.get_text(' ',strip=True)[:1200]
    break
  if raw.get('publisher')=='Google' and n['uid']=='fitbit-model:charge-6':
   body=(S/'fitbit_charge6_blog.html').read_bytes()
   if hashlib.sha256(body).hexdigest()!=raw['source_sha256']:raise ValueError('Fitbit source checksum mismatch')
   soup=BeautifulSoup(body,'html.parser');article=soup.select_one('article') or soup.select_one('main')
   if article:extra_statement=article.get_text(' ',strip=True)[:2200]
  if domain=='fitness_trackers' and extra_statement and re.search(r'\b(?:wrist|band)\b',extra_statement,re.I):
   # All seven products have body-worn evidence in their own primary field.
   name+=' wrist-worn wearable fitness tracker'
   statement=statement+' '+extra_statement

  # Features of an included component do not classify the containing product.
  defining=re.split(r'\b(?:with|featuring|equipped|including|includes|supports|compatible|used in|for)\b',statement,maxsplit=1,flags=re.I)[0]
  text=defining+' '+name
  # A plural product family cannot acquire a feature from one later variant.
  if role=='MODEL_FAMILY' and re.search(r'\b(?:including|versions|variants|range of|line of)\b',statement,re.I):
   withheld.append({'domain':domain,'uid':n['uid'],'reason':'Family scope cannot be narrowed from incidental features'});continue
  if not text.strip():continue
  if role=='CLASS' and not current_roles.get(n['uid']) and re.search(r'\b(?:is a type|is a class|are types|are classes)\b',statement,re.I):continue
  matches=[]
  for rule in rules:
   # 'unmanaged' must never be parsed as the positive term 'managed'.
   if rule['key']=='managed' and re.search(r'\bunmanaged\b',text,re.I):continue
   if rule['pattern'].search(text):matches.append(rule)
  if not matches:continue
  origin={'uid':n['uid'],'statement':statement or name,'record_sha256':sha(n['data']),'uri':n['source_uri'] or record.get('source_uri') or raw.get('source_uri') or 'https://www.wikidata.org/wiki/'+n['uid'].split(':')[-1]}
  parent_keys={k for rule in matches for k in rule['parents']}
  for rule in matches:
   uid=class_uid(rule,origin)
   if uid==n['uid'] or rule['key'] in parent_keys:continue
   parent_component=c.execute('SELECT component_id FROM nodes WHERE uid=?',(uid,)).fetchone()
   member_component=c.execute('SELECT component_id FROM nodes WHERE uid=?',(n['uid'],)).fetchone()
   if parent_component and parent_component[0]==member_component[0]:continue
   rel={'CLASS':'IS_A','MODEL':'DESIGN_TYPE_OF','MODEL_FAMILY':'DESIGN_TYPE_OF','CONFIGURATION':'CONFIGURATION_TYPE_OF','INSTANCE':'INSTANCE_OF'}[role]
   pr={'basis':'SOURCE_DECLARED_PROFESSIONAL_PREDICATE_IN_EXACT_REFERENT_SCOPE','source_statement':origin['statement'],'native_record_sha256':origin['record_sha256'],'predicate':rule['predicate'],'scope_role':role,'license':'Original source attribution and terms retained'}
   new.append({'op':'link','uid':n['uid'],'parent':uid,'relation':rel,'source':'Retained source professional type predicates','uri':origin['uri'],'proof':pr});members[domain]+=1
 print('ENGINEERING',domain,'links',members[domain],flush=True)
# Existing USGS confined/unconfined aquifers are retained; ENVO adds only native subtypes.
# Removing broad shortcuts is conditional on the new, evidenced path. Every
# source statement remains in the edge table with its native endpoints intact.
for r in list(new):
 if r['op']!='link' or r['uid'] in ROOTS.get(next((d for d in ROOTS if d in r['parent']),''),[]):continue
 for d in members:
  if not r['parent'].startswith('hierarchy-type:'+d+'-'):continue
  for rootuid in ROOTS[d]:
   for e in c.execute("SELECT id FROM edges WHERE child_uid=? AND parent_uid=? AND status='ACTIVE' AND relation='IS_A'",(r['uid'],rootuid)):
    new.append({'op':'withdraw_edge','uid':r['uid'],'parent':rootuid,'edge_id':e[0],'source':r['source'],'uri':r['uri'],'proof':{'basis':'EVIDENCED_PROFESSIONAL_PATH_REPLACES_BROAD_CATALOGUE_SHORTCUT','replacement_parent':r['parent'],'license':'Original declaration retained'}})
allrecords=records+new
with core.open('w') as f:
 for r in allrecords:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
(I/'engineering_refinement_summary.json').write_text(json.dumps({'types':len(types),'new_operations':len(new),'members_by_domain':dict(members),'withheld_family_scopes':len(withheld),'sha256':hashlib.sha256(core.read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n')
(I/'engineering_scope_reviews.json').write_text(json.dumps(withheld,ensure_ascii=False,indent=2)+'\n')
print('COMPLETE ENGINEERING',len(types),len(new),dict(members),flush=True)
