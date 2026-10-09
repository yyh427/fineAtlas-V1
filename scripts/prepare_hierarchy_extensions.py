#!/usr/bin/env python3
"""Use exact native product fields to complete sparse professional branches."""
import argparse,collections,hashlib,json,re,sqlite3,sys
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.semantics import role_expression
p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--inputs',required=True);p.add_argument('--sources',required=True);p.add_argument('--definitions',required=True);a=p.parse_args()
I=Path(a.inputs);S=Path(a.sources);c=sqlite3.connect(Path(a.database).resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
prior=[json.loads(l) for l in (I/'hierarchy_facts.jsonl').open()];roles={r['uid']:r['role'] for r in prior if r['op']=='role'};known={r['uid'] for r in prior if r['op']=='class'};rows=[];types={};counts=collections.Counter();definitions=json.loads(Path(a.definitions).read_text());refs={r['key']:r for r in json.loads((S/'manifest.json').read_text()) if 'sha256' in r};cache={}
def sha(t):return hashlib.sha256(t.encode()).hexdigest()
def node(u):
 if u not in cache:
  r=c.execute('SELECT n.*,'+role_expression('n','p')+' role,p.source_uri FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(u,)).fetchone();cache[u]=dict(r) if r else None
 return cache[u]
def kind(u):return roles.get(u,'CLASS' if u in known else node(u)['role'])
reg={r['canonical_name']:dict(r) for r in c.execute('SELECT * FROM domain_registry')};rootmap={d:[u for u in json.loads(r['root_uids']) if kind(u)=='CLASS'] for d,r in reg.items()}
def cls(key,label,d,parents,definition,uri,proof,axis):
 u='hierarchy-type:'+key
 if u not in known and u not in types:
  types[u]=True;rows.append({'op':'class','uid':u,'label':label,'domain':d,'parents':parents,'definition':definition,'axis':axis,'source':'Additional exact-source professional type definitions','uri':uri,'proof':{'basis':'SOURCE_DEFINED_PROFESSIONAL_TYPE','definition':definition,'license':'Retained source attribution and terms; original factual type definitions',**proof}})
 return u
def link(u,parent,uri,proof,relation=None):
 rel=relation or {'CLASS':'IS_A','MODEL':'DESIGN_TYPE_OF','MODEL_FAMILY':'DESIGN_TYPE_OF','CONFIGURATION':'CONFIGURATION_TYPE_OF','INSTANCE':'INSTANCE_OF'}.get(kind(u))
 if rel:
  rows.append({'op':'link','uid':u,'parent':parent,'relation':rel,'source':'Additional exact native-field professional classification','uri':uri,'proof':{'basis':'EXACT_REFERENT_NATIVE_FIELD_TYPE_ENTAILMENT','native_record_sha256':sha(node(u)['data']),'scope_role':kind(u),'license':'Original source attribution and terms retained',**proof}});counts[proof['domain']]+=1
# Parentheses in manufacturer headings often contain genuine hardware fields.
# GPS/cellular statements apply to the published configuration, never a family.
sat=None;gps=None;cell=None
id=reg['smartwatches']['domain_id']
for n in c.execute("SELECT n.uid,n.data FROM domain_members m JOIN nodes n ON n.uid=m.uid WHERE m.domain_id=? AND m.view='strict' ORDER BY n.uid",(id,)):
 raw=json.loads(n['data']);heading=raw.get('attributes',{}).get('catalog_heading','')
 if not heading or raw.get('source')!='Apple model-identification support':continue
 if not re.search(r'\bGPS\b',heading) or kind(n['uid']) not in {'MODEL','CONFIGURATION'}:continue
 uri=raw['source_uri'];pr={'domain':'smartwatches','native_catalog_heading':heading,'no_lifting_to_product_family':True}
 sat=cls('smartwatches-satellite-navigation','satellite-navigation-capable smartwatch','smartwatches',rootmap['smartwatches'][:1],'A smartwatch supporting satellite-based position determination.',uri,pr,'navigation_capability')
 gps=cls('smartwatches-gps','GPS smartwatch','smartwatches',[sat],'A satellite-navigation-capable smartwatch supporting the Global Positioning System.',uri,pr,'navigation_capability')
 parent=gps
 if re.search(r'\bCellular\b',heading):parent=cls('smartwatches-cellular-gps','cellular GPS smartwatch','smartwatches',[gps],'A GPS smartwatch also supporting cellular-network communication.',uri,pr,'navigation_and_communication')
 link(n['uid'],parent,uri,pr)
# Explicit native tablet platform descriptions classify factory design scope.
# Linux and Android stay parallel here: kernel ancestry is not OS identity.
id=reg['tablets']['domain_id']
for n in c.execute("SELECT n.uid,n.label,n.data,n.description FROM domain_members m JOIN nodes n ON n.uid=m.uid WHERE m.domain_id=? AND m.view='strict' ORDER BY n.uid",(id,)):
 if kind(n['uid']) not in {'CLASS','MODEL','CONFIGURATION'} or n['uid'] in rootmap['tablets']:continue
 raw=json.loads(n['data']);record=definitions.get('wikidata:'+n['uid'].split(':')[-1],{});statement=(record.get('intro') or raw.get('definition') or n['description']).split('. ')[0][:700]
 platform='Android' if re.search(r'Android[ -](?:based|powered)[^.]{0,90}tablet|Android tablet',statement,re.I) else 'Linux' if re.search(r'Linux[ -]based[^.]{0,70}tablet',statement,re.I) else None
 if not platform:continue
 uri=record.get('source_uri') or raw.get('source_uri') or 'https://www.wikidata.org/wiki/'+n['uid'].split(':')[-1]
 parent=cls('tablets-'+platform.lower(),platform+' tablet computer','tablets',rootmap['tablets'][:1],'A tablet computer designed and marketed for the '+platform+' operating platform; arbitrary later software changes are outside this factory design scope.',uri,{'domain':'tablets','source_statement':statement,'factory_design_scope':True},'factory_operating_platform')
 link(n['uid'],parent,uri,{'domain':'tablets','source_statement':statement,'factory_design_scope':True,'no_software_version_inference':True})
# Source-defined diaphragm structure organises existing reusable speaker types.
for u in ['wikidata:Q1326952','wikidata:Q5157037']:
 n=node(u);text=n['description'];uri='https://en.wikipedia.org/wiki/'+('Moving_iron_speaker' if u.endswith('Q1326952') else 'Compression_driver')
 if not re.search(r'diaphragm',text,re.I):continue
 parent=cls('loudspeakers-diaphragm','diaphragm loudspeaker','loudspeakers',rootmap['loudspeakers'][:1],'A loudspeaker that generates sound using the motion of a solid diaphragm.',uri,{'domain':'loudspeakers','source_statement':text[:650]},'acoustic_transduction_structure')
 link(u,parent,uri,{'domain':'loudspeakers','source_statement':text[:650],'complete_generic_type_definition':True})
# EPA VClass is a comparable-car-line classification. The two-seater rule
# uses a majority of a car line, so it cannot certify a particular trim's
# seat count. Preserve these useful native groups as taxonomy navigation.
for n in c.execute("SELECT n.uid,n.data FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.source='epa' AND n.visibility='ACTIVE' AND "+role_expression('n','p')+"='CONFIGURATION' ORDER BY n.uid"):
 d=json.loads(n['data']);v=d.get('VClass','')
 if not ('Station Wagons' in v or v=='Two Seaters'):continue
 key=re.sub(r'[^a-z0-9]+','-',v.lower()).strip('-');uri='https://www.fueleconomy.gov/feg/ws/index.shtml'
 parent=cls('cars-epa-'+key,'EPA '+v+' car-line category','cars',rootmap['cars'][:1],'The native EPA comparable passenger-car-line category labelled '+v+'. This is a regulatory classification of comparable car lines, not a certification of each configuration body or seat count.',uri,{'domain':'cars','native_VClass':v,'allowed_views':['taxonomy'],'classification_is_not_configuration_measurement':True,'regulatory_definition_uri':'https://www.govinfo.gov/content/pkg/CFR-2014-title40-vol30/pdf/CFR-2014-title40-vol30-sec600-315-08.pdf'},'native_regulatory_classification')
 for record in rows:
  if record['op']=='class' and record['uid']==parent:record['parent_relation']='NATIVE_CLASSIFICATION_PARENT';break
 link(n['uid'],parent,uri,{'domain':'cars','native_VClass':v,'native_year':d.get('year'),'no_physical_seat_count_or_body_form_inference':True},relation='REGULATED_AS')
# Aquifer material structure has genuine inclusion: an alluvial aquifer is
# an unconsolidated-deposit aquifer. Named geographic objects remain instances.
u='usgs-water:alluvial-aquifer';n=node(u);uri=n['source_uri'] or 'https://www.usgs.gov/special-topics/water-science-school/science/water-science-glossary'
parent=cls('aquifers-unconsolidated','unconsolidated-deposit aquifer','aquifers',rootmap['aquifers'][:1],'An aquifer whose water-bearing geological matrix consists of unconsolidated deposits.',uri,{'domain':'aquifers','native_definition':n['description']},'geological_matrix')
link(u,parent,uri,{'domain':'aquifers','native_definition':n['description'],'native_material_phrase':'unconsolidated material'})
for u in ['wikidata:Q114315923','wikidata:Q14943738','wikidata:Q17051936','wikidata:Q28228271','wikidata:Q4917225','wikidata:Q4917720','wikidata:Q6734741','wikidata:Q7418743']:
 n=node(u);text=n['description'];rec=definitions.get(u,{});text=rec.get('intro') or text
 if not re.search(r'\baquifer\b',text,re.I) or not re.search(r'\b(?:in|surrounds|surrounding|located|situated|resides|lies|named after)\b[^.;]{0,150}\b[A-Z][a-z]',text):raise ValueError('Named aquifer lacks particular-place evidence: '+u)
 uri=rec.get('source_uri') or n['source_uri'] or 'https://www.wikidata.org/wiki/'+u.split(':')[-1]
 members=c.execute('SELECT uid,visibility FROM nodes WHERE component_id=? AND uid IN (?,?,?)',(n['component_id'],u,'wikidata-v4:'+u.split(':')[-1],'v26-wikidata:'+u.split(':')[-1])).fetchall()
 for member in members:
  if member['visibility']!='ACTIVE':continue
  v=member['uid'];roles[v]='INSTANCE'
  rows.append({'op':'role','uid':v,'role':'INSTANCE','source':'Independent particular geographic feature definitions','uri':uri,'proof':{'basis':'NAMED_AQUIFER_WITH_INDEPENDENT_PARTICULAR_PLACE_SCOPE','definition':text[:900],'native_record_uid':u,'native_record_sha256':sha(n['data']),'license':'Wikipedia CC BY-SA 4.0; source attribution retained'}})
  # No ordinary inclusion edge may use this individual as either endpoint.
  for e in c.execute("SELECT id,child_uid,parent_uid FROM edges WHERE status='ACTIVE' AND relation='IS_A' AND (child_uid=? OR parent_uid=?)",(v,v)):
   rows.append({'op':'withdraw_edge','uid':e['child_uid'],'parent':e['parent_uid'],'edge_id':e['id'],'source':'Independent particular geographic feature definitions','uri':uri,'proof':{'basis':'INDIVIDUAL_GEOGRAPHIC_FEATURE_IS_NOT_AN_ORDINARY_CLASS_ENDPOINT','individual_uid':v,'license':'Original source declaration retained'}})
  target='usgs-aquifer:unconfined-aquifer' if re.search(r'\bunconfined aquifer\b',text,re.I) else rootmap['aquifers'][0]
  link(v,target,uri,{'domain':'aquifers','definition':text[:900],'particular_place_scope':True})
# Established surgical working functions organise physical instrument types.
# A purpose/working-function type is explicit and parallel to material/form.
id=reg['surgical_instruments']['domain_id']
functions=[('cutting','cutting surgical instrument',r'\b(?:cut|cutting|cutter|blade|slices)\b','performs surgical cutting'),('holding','grasping and holding surgical instrument',r'\b(?:hold|holding|clamp|clamping|grasping)\b','grasps, holds or clamps tissue or surgical working objects'),('dilating','dilating surgical instrument',r'\b(?:dilate|dilating|dilatation|distend)\b','dilates or distends a surgical opening'),('scraping','scraping and debridement surgical instrument',r'\b(?:scraping|debriding|debridement)\b','scrapes or debrides biological tissue or debris')]
for n in c.execute("SELECT n.uid,n.description,n.data FROM domain_members m JOIN nodes n ON n.uid=m.uid WHERE m.domain_id=? AND m.view='strict' ORDER BY n.uid",(id,)):
 if kind(n['uid'])!='CLASS' or n['uid'] in rootmap['surgical_instruments']:continue
 raw=json.loads(n['data']);text=(raw.get('definition') or n['description']).split('. ')[0][:600]
 uri=raw.get('source_uri') or node(n['uid'])['source_uri'] or ('https://wordnet.princeton.edu/' if n['uid'].startswith('wordnet31:') else 'https://www.wikidata.org/wiki/'+n['uid'].split(':')[-1])
 for k,label,pattern,predicate in functions:
  if not re.search(pattern,text,re.I):continue
  parent=cls('surgical-'+k,label,'surgical_instruments',rootmap['surgical_instruments'][:1],'A surgical instrument that '+predicate+'.',uri,{'domain':'surgical_instruments','native_working_definition':text},'surgical_working_function')
  link(n['uid'],parent,uri,{'domain':'surgical_instruments','native_working_definition':text,'whole_instrument_function':True})
# EUNIS complex groups are defined on the whole habitat complex. Its plants
# and water bodies remain components, never IS_A parents of that complex.
for u in ['eunis2012:X04','eunis2012:X09','eunis2012:X10','eunis2012:X06','eunis2012:X13','eunis2012:X14','eunis2012:X15','eunis2012:X16']:
 n=node(u);text=n['description'];uri=n['source_uri'] or 'https://eunis.eea.europa.eu/habitats-code.jsp'
 peat=u=='eunis2012:X04';key='peatland' if peat else 'woody-vegetation';label='peatland habitat complex' if peat else 'woody-vegetation habitat complex'
 definition='A habitat complex characterised by peatland habitat elements.' if peat else 'A habitat complex containing structurally defined woody-vegetation elements such as tree layers, hedgerows or woodland patches.'
 parent=cls('habitat-complex-'+key,label,'habitat_complexes',rootmap['habitat_complexes'][:1],definition,uri,{'domain':'habitat_complexes','native_complex_code':u,'native_complex_definition':text[:900],'whole_complex_predicate_not_component_IS_A':True,'native_source_version':'EUNIS 2012','native_complex_scheme_provisional_status_retained':True},'habitat_complex_structure')
 link(u,parent,uri,{'domain':'habitat_complexes','native_complex_code':u,'native_complex_definition':text[:900],'whole_complex_predicate_not_component_IS_A':True,'native_source_version':'EUNIS 2012'})
# Source terrain definitions support a real desert-surface intermediate.
# Hamada is a high bedrock plateau; reg is a gravel/stone-covered plain.
for u in ['geonames-feature:T.HMDA','geonames-feature:T.REG']:
 n=node(u);uri='https://www.geonames.org/export/codes.html'
 parent=cls('deserts-rocky-surface','rocky-surface desert','deserts',rootmap['deserts'][:1],'A desert characterised by bedrock, stone or gravel terrain rather than predominantly mobile sand dunes.',uri,{'domain':'deserts','native_feature_code':u,'native_definition':n['description']},'dominant_surface_structure')
 link(u,parent,uri,{'domain':'deserts','native_feature_code':u,'native_definition':n['description'],'no_named_desert_surface_guess':True})
# Match whole primary product sections before using wireless earbud facts.
ref=refs['airpods_pro3'];body=(S/ref['path']).read_bytes()
if hashlib.sha256(body).hexdigest()!=ref['sha256']:raise ValueError('AirPods source checksum differs')
soup=BeautifulSoup(body,'html.parser');text=(soup.select_one('main') or soup).get_text(' ',strip=True)
if not all(x in text for x in ['AirPods Pro 3','Bluetooth','ear tips']):raise ValueError('AirPods technical document lacks exact-model connectivity/fit fields')
u='apple-model:c0f86089ceef6af4bd3e';pr={'domain':'earbuds','source_sha256':ref['sha256'],'published_model':'AirPods Pro 3','source_fields':['Bluetooth connectivity','individually powered earbuds','silicone ear tips'],'family_scope_not_inferred':True}
parent=cls('earbuds-truewireless','true-wireless earbud','earbuds',['hierarchy-type:earbuds-wireless'],'A wireless earbud whose two earpieces communicate without a physical cable connecting them.',ref['uri'],pr,'wireless_connection_structure')
link(u,parent,ref['uri'],pr)
# Primary RTX 3090/3090 Ti card specification supplies GPU/capability facts.
ref=refs['nvidia_cards'];body=(S/ref['path']).read_bytes()
if hashlib.sha256(body).hexdigest()!=ref['sha256']:raise ValueError('NVIDIA source checksum differs')
text=BeautifulSoup(body,'html.parser').get_text(' ',strip=True)
if not all(x in text for x in ['GPU Engine Specs','CUDA','3090']):raise ValueError('NVIDIA card specification fields unavailable')
gpu=cls('graphics_cards-gpu-based','GPU-based graphics card','graphics_cards',rootmap['graphics_cards'][:1],'A graphics card whose graphics processing is performed by an incorporated graphics processing unit; the card is a whole assembly distinct from that GPU.',ref['uri'],{'domain':'graphics_cards','source_sha256':ref['sha256'],'source_field':'GPU Engine Specs'},'processing_structure')
compute=cls('graphics_cards-gpu-compute','general-purpose-GPU-computing graphics card','graphics_cards',[gpu],'A GPU-based graphics card whose incorporated GPU supports general-purpose programmable computation.',ref['uri'],{'domain':'graphics_cards','source_sha256':ref['sha256'],'source_field':'NVIDIA CUDA Cores'},'computation_capability')
for u in ['nvidia-geforce-card:geforce-rtx-3090','nvidia-geforce-card:geforce-rtx-3090-ti']:
 if node(u):link(u,compute,ref['uri'],{'domain':'graphics_cards','source_sha256':ref['sha256'],'native_card_designation':node(u)['label'],'source_field':'NVIDIA CUDA Cores','card_and_gpu_not_identity':True})
# Canonical portals use professional roots. Legacy source portal records and
# aliases are retained, including their original catalogue root statements.
for d,entry in reg.items():
 old=json.loads(entry['root_uids']);roots=rootmap[d]
 if d=='computer_hardware' and 'wikidata:Q3966' in roots:roots=['wikidata:Q3966']+[u for u in roots if u!='wikidata:Q3966']
 if roots!=old:rows.append({'op':'portal_roots','uid':entry['entry_uid'],'domain':d,'roots':roots,'source':'Professional domain-root role clarification','uri':'https://github.com/yyh427/fineAtlas-V1','proof':{'basis':'GENERIC_PROFESSIONAL_DOMAIN_ROOTS_WITH_LEGACY_SOURCE_PORTALS_RETAINED','source_roots':old,'canonical_roots':roots,'roles':{u:kind(u) for u in old},'license':'FineAtlas derived scope metadata'}})
# Omit broad source roots only after an explicit new-class parent chain proves
# the alternative. Different typed grain relations, e.g. CONFIGURATION_OF,
# remain useful and are retained.
parents={r['uid']:r['parents'] for r in prior+rows if r['op']=='class' and r.get('parent_relation','IS_A')=='IS_A'};withdrawn={r['edge_id'] for r in prior if r['op']=='withdraw_edge'};typed_withdrawn={r['relation_id'] for r in prior if r['op']=='withdraw_typed'}
def class_ancestors(u):
 seen=set();todo=[u]
 while todo:
  v=todo.pop()
  if v in seen:continue
  seen.add(v);todo.extend(parents.get(v,[]))
 return seen-{u}
for r in list(rows):
 if r['op']!='link' or r['relation']=='REGULATED_AS':continue
 ancestors=class_ancestors(r['parent']);comps={node(u)['component_id'] for u in ancestors if node(u)}
 for e in c.execute("SELECT e.id,e.parent_uid,p.component_id FROM edges e JOIN nodes p ON p.uid=e.parent_uid WHERE e.child_uid=? AND e.status='ACTIVE' AND e.relation='IS_A'",(r['uid'],)):
  if e['id'] not in withdrawn and e['component_id'] in comps:
   rows.append({'op':'withdraw_edge','uid':r['uid'],'parent':e['parent_uid'],'edge_id':e['id'],'source':r['source'],'uri':r['uri'],'proof':{'basis':'EXPLICIT_PROFESSIONAL_TYPE_CHAIN_REPLACES_BROAD_SHORTCUT','replacement_parent':r['parent'],'license':'Original source declaration retained'}});withdrawn.add(e['id'])
 for e in c.execute("SELECT e.id,p.component_id FROM entity_relations e JOIN nodes p ON p.uid=e.object_uid WHERE e.subject_uid=? AND e.status='ACTIVE' AND e.relation IN ('DESIGN_TYPE_OF','CONFIGURATION_TYPE_OF')",(r['uid'],)):
  if e['id'] not in typed_withdrawn and e['component_id'] in comps:
   rows.append({'op':'withdraw_typed','uid':r['uid'],'relation_id':e['id'],'source':r['source'],'uri':r['uri'],'proof':{'basis':'EXPLICIT_PROFESSIONAL_TYPE_CHAIN_REPLACES_BROAD_SHORTCUT','replacement_parent':r['parent'],'license':'Original source declaration retained'}});typed_withdrawn.add(e['id'])
# Exact-source licensing applies to stored text evidence as well as labels.
for r in rows:
 if 'en.wikipedia.org/' in r['uri']:r['proof']['license']='Wikipedia CC BY-SA 4.0; source URL and retained snapshot attribution preserved'
rows=list({json.dumps(r,ensure_ascii=False,sort_keys=True):r for r in rows}.values())
output=I/'hierarchy_extensions.jsonl'
with output.open('w') as f:
 for r in rows:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
(I/'hierarchy_extensions_manifest.json').write_text(json.dumps({'records':len(rows),'new_classes':len(types),'links_by_domain':dict(counts),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'references':list(refs.values())},indent=2)+'\n')
print('EXTENSIONS',len(rows),len(types),dict(counts),flush=True)
