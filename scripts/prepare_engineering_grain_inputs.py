#!/usr/bin/env python3
"""Review engineering grain using scoped native senses and retained definitions."""
from pathlib import Path
import sys,json,collections,re,sqlite3,argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
p=argparse.ArgumentParser();p.add_argument('--database',required=True,type=Path);p.add_argument('--inventory',required=True,type=Path);p.add_argument('--wordnet',required=True,type=Path);p.add_argument('--definitions',required=True,type=Path);p.add_argument('--supplement',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();O=a.output;O.mkdir(parents=True,exist_ok=True)
from fineatlas.engineering_roles import engineering_role_hint,definition_head,ENGINEERING_DOMAINS,native_subject_aliases
from fineatlas._text import norm
from fineatlas.role_contracts import allows_model_extraction
c=sqlite3.connect(a.database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
from functools import lru_cache
w=sqlite3.connect(a.wordnet.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
native_parents=collections.defaultdict(set)
for child,parent in w.execute('SELECT child_uid,parent_uid FROM edges'):native_parents[child].add(parent)
@lru_cache(None)
def native_ancestors(uid):
 found=set();todo=[uid]
 while todo:
  current=todo.pop()
  if current in found:continue
  found.add(current);todo.extend(native_parents[current]-found)
 return found
wordnet_roots={}
for name,roots in c.execute('SELECT canonical_name,root_uids FROM domain_registry'):
 values=set()
 for uid in json.loads(roots):
  comp=c.execute('SELECT component_id FROM nodes WHERE uid=?',(uid,)).fetchone()[0]
  values.update(r[0] for r in c.execute("SELECT uid FROM nodes WHERE component_id=? AND uid LIKE 'wordnet31:%'",(comp,)))
 wordnet_roots[name]=values
generic_aliases=collections.defaultdict(set)
for line in a.inventory.open():
 n=json.loads(line)
 if not n['uid'].startswith('wordnet31:'):continue
 aliases={a[0] for a in c.execute('SELECT alias FROM aliases WHERE uid=?',(n['uid'],))}
 for d in n['scopes']:
  if wordnet_roots.get(d) and native_ancestors(n['uid']) & wordnet_roots[d]:generic_aliases[d].update(aliases)
generic_aliases['car']=generic_aliases['cars']
D=json.loads(a.definitions.read_text()); native_definitions={}
for line in a.inventory.open():
 n=json.loads(line);raw=json.loads(n['data']);e=raw.get('evidence_record',{});value=raw.get('definition') or raw.get('intro') or e.get('wikipedia_intro') or ''
 q='wikidata:'+n['uid'].split(':')[-1]
 if len(value)>len(native_definitions.get(q,'')):native_definitions[q]=value
aliases_by_qid={}
if a.supplement:
 for snapshot in a.supplement.glob('Q*.json'):
  item=json.loads(snapshot.read_bytes()).get('entities',{}).get(snapshot.stem,{})
  if item:aliases_by_qid[snapshot.stem]=native_subject_aliases(item)
out=[];counts=collections.Counter();samples=collections.defaultdict(list);uncertain=collections.defaultdict(list)
for line in a.inventory.open():
 n=json.loads(line)
 if n['uid'].startswith(('wordnet31:','hierarchy-type:')) or n['role']=='MODEL' and n['source']=='faa':continue
 raw=json.loads(n['data']);e=raw.get('evidence_record',{});desc=raw.get('wikidata_description') or e.get('wikidata_description') or raw.get('description') or n['description'] or ''
 subject_aliases=aliases_by_qid.get(n['uid'].split(':')[-1],());independent=D.get('wikidata:'+n['uid'].split(':')[-1],{});available=[independent.get('intro',''),native_definitions.get('wikidata:'+n['uid'].split(':')[-1],'')];own=[s for s in available if s and definition_head(s,n['label'],subject_aliases=subject_aliases)];definition=max(own,key=len,default='')
 domains=[d for d in n['scopes'] if d in ENGINEERING_DOMAINS];priority=['ships','locomotives','tractors','cars','aircraft','smartphones','tablets','laptops','desktop_computers','smartwatches','fitness_trackers','camera_lenses','camera_bodies','digital_cameras','cameras','game_consoles','headphones','earbuds','network_routers','network_switches','printers'];domain=n['domain'] if n['domain'] in ENGINEERING_DOMAINS and n['domain'] not in {'tools','electronic_equipment','electronic_devices','computer_hardware','clothing','home_appliances'} else next((d for d in priority if d in domains),domains[0] if domains else n['domain']);role,basis=engineering_role_hint(n['source'],n['rank'],domain,n['label'],desc,definition,generic_label=norm(n['label']) in generic_aliases[domain],subject_aliases=subject_aliases)
 named_definition=norm(n['label']) in norm(definition[:220])
 independent_design=n['role']=='CLASS' and role in {'MODEL','MODEL_FAMILY'} and named_definition and re.search(r'\b(?:manufactured|produced|developed|built|marketed)\b[^.;]{0,100}\bby\b|\b(?:model|family|series) of\b',definition,re.I) and not re.search(r'\b(?:serial number|registration number|tail number)\b',definition,re.I)
 if role and n['role']!=role and (role=='INSTANCE' or allows_model_extraction(raw,{'node_kind':n['role']}) or independent_design):
  x={'uid':n['uid'],'component_id':n['component_id'],'label':n['label'],'prior_role':n['role'],'role':role,'domain':domain,'scopes':n['scopes'],'basis':basis,'description':desc,'definition':definition,'native_subject_aliases':list(subject_aliases),'independent_native_role_adjudication':bool(independent_design and not allows_model_extraction(raw,{'node_kind':n['role']})),'source_uri':independent.get('source_uri') or raw.get('source_uri') or 'https://www.wikidata.org/wiki/'+n['uid'].split(':')[-1]};out.append(x);counts[domain,role]+=1
  if len(samples[domain])<15:samples[domain].append(x)
 elif n['role']=='CLASS' and not n['uid'].startswith('hierarchy-type:') and domain in {'cars','aircraft','ships','locomotives','tractors','smartphones'}:
  if len(uncertain[domain])<150:uncertain[domain].append({'uid':n['uid'],'label':n['label'],'description':desc,'definition':definition[:500]})
with (O/'grain_proposals.jsonl').open('w') as f:
 for x in out:f.write(json.dumps(x,ensure_ascii=False)+'\n')
(O/'grain_scan_summary.json').write_text(json.dumps({'role_change_proposals':len(out),'by_domain_role':{d+'/'+r:n for (d,r),n in counts.items()},'samples':samples,'uncertain_samples':uncertain},ensure_ascii=False,indent=2)+'\n');print('PROPOSALS',len(out),dict(counts),flush=True)
for d,xs in samples.items():print(d,[(x['label'],x['role']) for x in xs[:6]],flush=True)
