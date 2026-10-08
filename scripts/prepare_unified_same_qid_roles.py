#!/usr/bin/env python3
"""Reconcile historical role bugs only using frozen primary scope for the exact same QID.

No role inheritance across FAA/EPA/taxon identifiers, and no role guessing from
names. Original source records/identities/relations remain independent and intact.
"""
import argparse,collections,hashlib,json,pathlib,sqlite3,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'src'))
from fineatlas.semantics import role_expression
p=argparse.ArgumentParser(description=__doc__)
for name in ('database','inputs','output'):p.add_argument('--'+name,type=pathlib.Path,required=True)
a=p.parse_args();c=sqlite3.connect(a.database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
primary=collections.defaultdict(list)
for f in a.inputs.glob('*.jsonl'):
 if f.name=='unified_root_contracts.jsonl':continue
 for line in f.open():
  r=json.loads(line)
  if r.get('op')=='role' and r.get('uid','').startswith(('wikidata:','wikidata-v4:')) and r.get('proof',{}).get('basis','').startswith('DEFINED_PRIMARY_'):
   primary[r['uid'].split(':')[1]].append((f.name,r))
records=[];reviews=[]
for q,decisions in sorted(primary.items()):
 roles={r['role'] for _,r in decisions}
 if len(roles)!=1:reviews.append({'qid':q,'reason':'Frozen primary role decisions conflict'});continue
 role=next(iter(roles));file,authority=decisions[-1]
 nodes=list(c.execute('SELECT n.*,p.node_kind,'+role_expression('n','p')+' current_role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid IN (?,?) AND n.visibility=\'ACTIVE\'',('wikidata:'+q,'wikidata-v4:'+q)))
 for n in nodes:
  if n['current_role']==role:continue
  if n['current_role']=='MODEL_FAMILY' and role=='MODEL':
   reviews.append({'uid':n['uid'],'reason':'A primary model unit does not independently disprove the established family scope; leave source-grain review explicit'});continue
  peers=list(c.execute('SELECT uid FROM nodes WHERE component_id=? AND visibility=\'ACTIVE\'',(n['component_id'],)))
  if any(v['uid'] not in ('wikidata:'+q,'wikidata-v4:'+q) for v in peers):
   reviews.append({'uid':n['uid'],'reason':'Identity group contains a different source identifier/grain; not changed by exact-QID rule'});continue
  if n['label']!=authority['proof']['primary_label']:
   reviews.append({'uid':n['uid'],'reason':'Full retained scope/name differs from frozen primary scope'});continue
  proof={**authority['proof'],'basis':'EXACT_QID_FROZEN_PRIMARY_SCOPE_RECONCILES_HISTORICAL_ROLE',
   'primary_role_rule':{'input':file,'authority_uid':authority['uid'],'role':role,'proof':authority['proof']},
   'native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),'native_rank':n['rank'],
   'prior_role':n['current_role'],'same_qid':q,'identity_changed':False,'source_role':'Primary concept role for the exact same Wikidata identifier',
   'no_name_based_inference':True,'license':'Wikidata CC0'}
  records.append({'op':'role','uid':n['uid'],'role':role,'source':'Exact-QID primary scope reconciliation','uri':authority['uri'],'proof':proof})
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
a.output.with_suffix('.summary.json').write_text(json.dumps({'source_alias_role_repairs':len(records),'by_role':dict(collections.Counter(r['role'] for r in records)),'reviews':reviews,'identity_groups_split_or_merged':0,'classification_edges_added':0,'original_source_payloads_modified':0},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'source_alias_role_repairs':len(records),'by_role':dict(collections.Counter(r['role'] for r in records)),'reviews':len(reviews)}))
