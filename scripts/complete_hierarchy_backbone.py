#!/usr/bin/env python3
"""Complete reviewed professional backbones from frozen primary definitions.

Native model fields and generic source vocabularies remain separate. A type
may be published without guessing which insufficiently described model fits.
"""
import argparse,collections,hashlib,json,sqlite3
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--inputs',required=True);p.add_argument('--sources',required=True);a=p.parse_args()
I=Path(a.inputs);S=Path(a.sources);c=sqlite3.connect(Path(a.database).resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
path=I/'hierarchy_facts.jsonl';records=[json.loads(l) for l in path.open()];new=[];classes={r['uid']:r for r in records if r['op']=='class'};registry={r['canonical_name']:json.loads(r['root_uids']) for r in c.execute('SELECT * FROM domain_registry')};refs={r['key']:r for r in json.loads((S/'professional_references.json').read_text()) if 'sha256' in r}
def source(key):
 ref=refs[key];body=(S/ref['path']).read_bytes()
 if hashlib.sha256(body).hexdigest()!=ref['sha256']:raise ValueError('Primary reference checksum differs')
 return ref

def cls(uid,label,domain,parents,definition,refkey,axis):
 if uid in classes or c.execute('SELECT 1 FROM nodes WHERE uid=?',(uid,)).fetchone():return uid
 ref=source(refkey);r={'op':'class','uid':uid,'label':label,'domain':domain,'parents':parents,'definition':definition,'axis':axis,'source':'Primary professional definitions: '+refkey,'uri':ref['uri'],'proof':{'basis':'REVIEWED_PRIMARY_PROFESSIONAL_TYPE_DEFINITION','definition':definition,'source_sha256':ref['sha256'],'license':'Publisher copyright retained; original factual and logical type definitions; attribution preserved','scope':'Generic structure or operating type; membership is not inferred from a brand or product folder'}}
 classes[uid]=r;new.append(r);return uid
# LCD operating principles, followed by native panel structure. All labels
# denote whole monitors using this panel, rather than panel/monitor identity.
flat=cls('hierarchy-type:computer_monitors-flat','flat-panel computer monitor','computer_monitors',registry['computer_monitors'][:1],'A computer monitor whose image is displayed on a flat panel.','eizo_lcd','display_structure')
lcd=cls('hierarchy-type:computer_monitors-lcd','LCD computer monitor','computer_monitors',[flat],'A flat-panel computer monitor using a liquid-crystal display panel.','eizo_lcd','display_operating_principle')
for key,name in [('ips','IPS'),('va','VA'),('tn','TN')]:
 cls('hierarchy-type:computer_monitors-lcd-'+key,name+' LCD computer monitor','computer_monitors',[lcd],'An LCD computer monitor whose liquid-crystal panel uses the '+name+' operating structure.','eizo_lcd','liquid_crystal_panel_structure')
# Native tractor running structure; two-track and four-track are actual
# professionally declared refinements, not cartesian combinations.
tracked=cls('hierarchy-type:tractors-tracked','tracked tractor','tractors',registry['tractors'][:1],'A tractor that uses ground-contact tracks as its running gear.','deere_tracks','running_structure')
wheeled=cls('hierarchy-type:tractors-wheeled','wheeled tractor','tractors',registry['tractors'][:1],'A tractor whose running gear uses ground-contact wheels.','deere_tracks','running_structure')
for n,label in [('two','two-track tractor'),('four','four-track tractor')]:
 cls('hierarchy-type:tractors-'+n+'track',label,'tractors',[tracked],'A tracked tractor with '+n+' ground-contact track units.','deere_tracks','running_structure')
# Desktop and 2-in-1 structures explicitly distinguished by Microsoft.
cls('hierarchy-type:desktop_computers-aio','all-in-one desktop computer','desktop_computers',registry['desktop_computers'][:1],'A desktop computer integrating system components and its display into a single chassis.','microsoft_forms','device_form')
# A detachable tablet is a tablet with the declared keyboard arrangement;
# tablet membership of individual notebook products is never guessed.
cls('hierarchy-type:tablets-detachable','detachable-keyboard tablet computer','tablets',registry['tablets'][:1],'A tablet computer designed for use with a detachable keyboard, permitting tablet and notebook-like operation.','microsoft_forms','device_form')
# Scoped hardware intersections allow computer components to be browsed
# by their independently defined function without treating PART_OF as ISA.
root='wikidata:Q3966'
for k,label,physical in [('input','computer input hardware','wordnet31:03168639-n'),('output','computer output hardware','wordnet31:03866568-n'),('storage','computer storage hardware','wordnet31:03750331-n')]:
 n=c.execute('SELECT description FROM nodes WHERE uid=?',(physical,)).fetchone()
 uid='hierarchy-type:hardware-'+k
 if uid not in classes:
  r={'op':'class','uid':uid,'label':label,'domain':'computer_hardware','parents':[root,physical],'definition':'Computer hardware that is a '+k+' device. Native physical definition: '+n[0],'axis':'hardware_function','source':'Retained WordNet device definitions and computer hardware scope','uri':'https://wordnet.princeton.edu/','proof':{'basis':'DEFINED_HARDWARE_AND_NATIVE_DEVICE_INTERSECTION','logical_form':[root,physical],'physical_definition':n[0],'license':'Princeton WordNet license and existing source attribution retained'}};classes[uid]=r;new.append(r)
 r=classes[uid]
 for member in {'input':['wordnet31:03168639-n'],'output':['wikidata:Q5290'],'storage':['wikidata:Q487343']}[k]:
  # The generic global input-device class is broader than computer-specific
  # hardware and is not asserted to be a subclass of this intersection.
  if k=='input':continue
  new.append({'op':'link','uid':member,'parent':uid,'relation':'IS_A','source':r['source'],'uri':r['uri'],'proof':{'basis':'EXPLICIT_COMPUTER_DEVICE_FUNCTION','definition':c.execute('SELECT description FROM nodes WHERE uid=?',(member,)).fetchone()[0],'license':'Retained source attribution'}})
# Primary professional GPU definitions were verified using the browser when
# direct origin download was refused. Freeze derived factual definitions and
# the inspection provenance, rather than claiming a missing PDF was cached.
intel='https://www.intel.com/content/www/us/en/support/articles/000057824/graphics.html'
for k in ['integrated','discrete']:
 uid='hierarchy-type:gpus-'+k
 if uid in classes:continue
 definition=('A graphics processing unit built into the processor.' if k=='integrated' else 'A graphics processing unit implemented separately from the processor.')
 r={'op':'class','uid':uid,'label':k+' graphics processing unit','domain':'gpus','parents':registry['gpus'][:1],'definition':definition,'axis':'processor_integration','source':'Intel graphics support Article 000057824','uri':intel,'proof':{'basis':'PRIMARY_INTEGRATED_DISCRETE_GPU_DEFINITIONS','definition':definition,'reference_inspection':'Browser inspection on 2026-10-06; article last reviewed 2024-09-04; direct origin returned HTTP 403','license':'Publisher copyright retained; derived factual definitions only'}};new.append(r);classes[uid]=r
# Native CUDA compute-capability records imply programmable general-purpose
# GPU computation. CUDA support remains a technical type, not a brand layer.
gpgpu='hierarchy-type:gpus-general-purpose-compute'
cuda='nvidia-type:cuda-capable-gpu'
if gpgpu not in classes:
 n=c.execute('SELECT description,data FROM nodes WHERE uid=?',(cuda,)).fetchone()
 r={'op':'class','uid':gpgpu,'label':'general-purpose-computing-capable graphics processing unit','domain':'gpus','parents':registry['gpus'][:1],'definition':'A graphics processing unit supporting programmable general-purpose computation in addition to graphics processing.','axis':'computation_capability','source':'NVIDIA native CUDA GPU compute capability definitions','uri':'https://developer.nvidia.com/cuda-gpus','proof':{'basis':'CUDA_GPU_NATIVE_PROGRAMMABLE_COMPUTATION_SCOPE','source_type_definition':n[0],'license':'Retained NVIDIA source attribution; factual type definition'}};new.append(r);classes[gpgpu]=r
new.append({'op':'link','uid':cuda,'parent':gpgpu,'relation':'IS_A','source':'NVIDIA native CUDA GPU compute capability definitions','uri':'https://developer.nvidia.com/cuda-gpus','proof':{'basis':'CUDA_COMPUTATION_IMPLIES_GENERAL_PURPOSE_GPU_CAPABILITY','license':'Retained NVIDIA source attribution'}})
# Remove root shortcuts only when an admitted new type has an explicit path
# to that exact root identity component. No typed configuration/design identity
# relation is removed: those represent a separate and useful grain relation.
parentmap=collections.defaultdict(set)
for r in records+new:
 if r['op']=='class':parentmap[r['uid']].update(r['parents'])
 elif r['op']=='link' and r['relation']=='IS_A':parentmap[r['uid']].add(r['parent'])
cache={}
def comp(uid):
 if uid not in cache:
  row=c.execute('SELECT component_id FROM nodes WHERE uid=?',(uid,)).fetchone();cache[uid]=row[0] if row else uid
 return cache[uid]
ancestor_cache={}
def ancestors(uid):
 if uid in ancestor_cache:return ancestor_cache[uid]
 todo=[uid];seen=set();anc=set()
 while todo and len(seen)<500:
  u=todo.pop()
  if u in seen:continue
  seen.add(u);anc.add(comp(u));todo.extend(parentmap[u])
  component=comp(u)
  if isinstance(component,int):
   todo.extend(x[0] for x in c.execute("SELECT DISTINCT e.parent_uid FROM nodes n JOIN edges e ON e.child_uid=n.uid WHERE n.component_id=? AND e.status='ACTIVE' AND e.relation='IS_A'",(component,)))
 ancestor_cache[uid]=anc;return anc
root_components={comp(u) for roots in registry.values() for u in roots}
removed={r['edge_id'] for r in records if r['op']=='withdraw_edge'};typed_removed={r['relation_id'] for r in records if r['op']=='withdraw_typed'}
for r in records+list(new):
 if r['op']!='link' or r['relation'] not in {'IS_A','DESIGN_TYPE_OF','CONFIGURATION_TYPE_OF'}:continue
 anc=ancestors(r['parent'])-{comp(r['parent'])}
 for e in c.execute("SELECT e.id,e.parent_uid,n.component_id FROM edges e JOIN nodes n ON n.uid=e.parent_uid WHERE e.child_uid=? AND e.status='ACTIVE' AND e.relation='IS_A'",(r['uid'],)):
  if e['id'] not in removed and e['component_id'] in anc and e['component_id'] in root_components:
   new.append({'op':'withdraw_edge','uid':r['uid'],'parent':e['parent_uid'],'edge_id':e['id'],'source':r['source'],'uri':r['uri'],'proof':{'basis':'WITNESSED_PROFESSIONAL_PATH_REPLACES_ROOT_SHORTCUT','replacement_parent':r['parent'],'root_component':e['component_id'],'license':'Original source declaration preserved'}});removed.add(e['id'])
 for e in c.execute("SELECT e.id,n.component_id FROM entity_relations e JOIN nodes n ON n.uid=e.object_uid WHERE e.subject_uid=? AND e.status='ACTIVE' AND e.relation IN ('DESIGN_TYPE_OF','CONFIGURATION_TYPE_OF')",(r['uid'],)):
  if e['id'] not in typed_removed and e['component_id'] in anc and e['component_id'] in root_components:
   new.append({'op':'withdraw_typed','uid':r['uid'],'relation_id':e['id'],'source':r['source'],'uri':r['uri'],'proof':{'basis':'WITNESSED_PROFESSIONAL_PATH_REPLACES_ROOT_SHORTCUT','replacement_parent':r['parent'],'root_component':e['component_id'],'license':'Original source declaration preserved'}});typed_removed.add(e['id'])
allrecords=list({json.dumps(r,ensure_ascii=False,sort_keys=True):r for r in records+new}.values())
with path.open('w') as f:
 for r in allrecords:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
(I/'backbone_completion.json').write_text(json.dumps({'operations':len(new),'total_operations':len(allrecords),'classes_by_domain':dict(collections.Counter(r['domain'] for r in allrecords if r['op']=='class')),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},indent=2)+'\n')
print('COMPLETE BACKBONE',len(new),len(allrecords),flush=True)
