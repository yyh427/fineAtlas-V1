#!/usr/bin/env python3
"""Freeze role decisions for source designs previously counted as classes."""
import argparse,collections,hashlib,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.engineering_roles import engineering_role_hint
from fineatlas.semantics import role_expression
p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--gaps',required=True);p.add_argument('--output',required=True);a=p.parse_args()
c=sqlite3.connect(Path(a.database).resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
O=Path(a.output);O.mkdir(parents=True,exist_ok=True);audit=json.loads(Path(a.gaps).read_text());records=[];unresolved=[];decisions={r['uid']:r['role'] for r in [json.loads(l) for l in (O/'engineering_role_repairs.jsonl').open()]} if (O/'engineering_role_repairs.jsonl').exists() else {};role=role_expression('n','p')
for gap in audit['records']:
 n=dict(c.execute('SELECT * FROM nodes WHERE uid=?',(gap['uid'],)).fetchone());raw=json.loads(n['data']);e=raw.get('evidence_record',{});desc=n['description'] or raw.get('wikidata_description') or e.get('wikidata_description') or raw.get('description','');definition=raw.get('definition') or raw.get('intro') or e.get('wikipedia_intro') or ''
 scope=next((d for d in gap['domains'] if d in {'aircraft','cars'}),n['domain']);kind,basis=engineering_role_hint(n['source'],n['rank'],scope,n['label'],desc,definition)
 aliases=[dict(r) for r in c.execute('SELECT n.uid,n.label,n.source,n.rank,n.data,p.attributes,'+role+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.component_id=? AND n.visibility=\'ACTIVE\'',(n['component_id'],)) if r['role'] in {'MODEL','MODEL_FAMILY','CONFIGURATION'}]
 declared={r['role'] for r in aliases if json.loads(r['attributes'] or '{}').get('role_status')=='VERIFIED' or r['source'] in {'faa','epa'} or r['rank'] in {'aircraft_model','vehicle_model','product_model','model_family','model','configuration','model_year_configuration'}}
 if not kind and len(declared)==1:
  kind=next(iter(declared));basis='Verified identity component has one explicit native engineering grain'
 if not kind and n['rank']=='named_refinement' and n['source']=='wikidata_v4_p31' and scope in {'aircraft','car','cars'} and any(ch.isdigit() for ch in n['label']) and any(word in desc.lower() for word in ['aircraft','airliner','airlifter','helicopter','gyroplane','aeroplane','airplane','car','automobile']):
  kind='MODEL';basis='Named engineering refinement has a source-stated vehicle kind and a specific numbered design designation'
 if not kind and n['rank']=='named_refinement' and n['source']=='wikidata_v4_p31' and scope in {'aircraft','cars'}:
  parents=[dict(z) for z in c.execute("SELECT n.uid,n.label,n.rank,n.description,p.node_kind FROM edges e JOIN nodes n ON n.uid=e.parent_uid LEFT JOIN node_profiles p ON p.uid=n.uid WHERE e.child_uid=? AND e.status='ACTIVE'",(n['uid'],))]
  if any(z['uid'] in decisions or z['node_kind'] in {'MODEL','MODEL_FAMILY'} or 'family' in z['description'].lower() or 'series' in z['description'].lower() for z in parents):
   kind='MODEL';basis='Named engineering refinement is explicitly classified under an independently established design or family'
 if not kind:
  unresolved.append({'uid':n['uid'],'label':n['label'],'description':desc,'rank':n['rank'],'reason':basis,'domains':gap['domains']});continue
 proof={'basis':basis,'native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),'native_rank':n['rank'],'native_description':desc,'independent_definition':definition,'identity_native_grains':[{'uid':r['uid'],'role':r['role'],'native_record_sha256':hashlib.sha256(r['data'].encode()).hexdigest()} for r in aliases],'license':'CC0 Wikidata factual descriptions; retained encyclopedia material CC BY-SA 4.0; native US government facts public domain'}
 uri=raw.get('source_uri') or (('https://www.wikidata.org/wiki/'+raw.get('qid',n['uid'].split(':')[-1])) if n['source']!='epa' else 'https://www.fueleconomy.gov/feg/download.shtml')
 records.append({'op':'role','uid':n['uid'],'role':kind,'source':'Native engineering design grain repair','uri':uri,'proof':proof});decisions[n['uid']]=kind
# These generic concepts have explicit retained definitions, not model identifiers.
for uid in ['wikidata:Q13049940','wikidata:Q486975','wikidata:Q13135638']:
 n=c.execute('SELECT data FROM nodes WHERE uid=?',(uid,)).fetchone();raw=json.loads(n['data']);records.append({'op':'role','uid':uid,'role':'CLASS','source':'Independent generic type role repair','uri':raw['source_uri'],'proof':{'basis':'SOURCE_DEFINITION_IDENTIFIES_REUSABLE_GENERIC_TYPE','native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),'definition':raw['description'],'enwiki_title':raw['enwiki_title'],'license':'CC0 Wikidata factual definition'}});decisions[uid]='CLASS'
uid='wikidata:Q655030';n=c.execute('SELECT description,data FROM nodes WHERE uid=?',(uid,)).fetchone();kind,basis=engineering_role_hint('wikidata','class','ships','Marella Explorer 2',n['description']);assert kind=='INSTANCE';records.append({'op':'role','uid':uid,'role':kind,'source':'Independent individual vessel role repair','uri':'https://www.wikidata.org/wiki/Q655030','proof':{'basis':basis,'native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),'definition':n['description'],'license':'Retained encyclopedia definition CC BY-SA 4.0'}});decisions[uid]=kind
with (O/'engineering_role_repairs.jsonl').open('w') as f:
 for r in records:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
(O/'engineering_role_reviews.json').write_text(json.dumps(unresolved,ensure_ascii=False,indent=2)+'\n');(O/'engineering_role_repair_summary.json').write_text(json.dumps({'role_records':len(records),'role_counts':dict(collections.Counter(decisions.values())),'unresolved':len(unresolved)},indent=2)+'\n');print('ROLE PROPOSALS',len(records),dict(collections.Counter(decisions.values())),'unresolved',len(unresolved),flush=True)
