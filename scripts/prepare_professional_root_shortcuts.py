#!/usr/bin/env python3
import argparse,collections,hashlib,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.semantics import role_expression
p=argparse.ArgumentParser(description='Prepare only redundant root arcs with a complete professional CLASS witness');p.add_argument('--database',required=True);p.add_argument('--inputs',required=True);p.add_argument('--output',required=True);a=p.parse_args();I=Path(a.inputs);O=Path(a.output);O.mkdir(parents=True,exist_ok=True)
c=sqlite3.connect(Path(a.database).resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA temp_store=MEMORY')
classes={r['uid']:r for name in ['hierarchy_facts.jsonl','hierarchy_extensions.jsonl'] for r in map(json.loads,(I/name).open()) if r['op']=='class'}
roles={r['uid']:r['role'] for r in map(json.loads,(I/'hierarchy_role_repairs.jsonl').open()) if r['op']=='role'}
c.execute('CREATE TEMP TABLE mids(uid TEXT PRIMARY KEY)');c.executemany('INSERT INTO mids VALUES(?)',[(u,) for u in classes]);c.execute('CREATE TEMP TABLE rootcomps(id INTEGER PRIMARY KEY)')
rootuids={u for r in c.execute('SELECT root_uids FROM domain_registry') for u in json.loads(r[0])};c.executemany('INSERT OR IGNORE INTO rootcomps VALUES(?)',[(c.execute('SELECT component_id FROM nodes WHERE uid=?',(u,)).fetchone()[0],) for u in rootuids])
cache={};members={};parents={}
def node(uid):
 if uid not in cache:
  r=c.execute('SELECT n.uid,n.component_id,n.visibility,n.data,p.attributes,'+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(uid,)).fetchone();cache[uid]=dict(r);cache[uid]['role']=roles.get(uid,r['role']);cache[uid]['views']=json.loads(r['attributes'] or '{}').get('allowed_views',['strict','taxonomy'])
 return cache[uid]
def links(comp):
 if comp not in parents:
  out=[]
  for (uid,) in c.execute("SELECT uid FROM nodes WHERE component_id=? AND visibility='ACTIVE'",(comp,)):
   if node(uid)['role']!='CLASS':continue
   for e in c.execute("SELECT id,child_uid,parent_uid FROM edges WHERE child_uid=? AND status='ACTIVE' AND relation='IS_A' ORDER BY id",(uid,)):
    p=node(e['parent_uid'])
    if p['role']=='CLASS' and p['visibility']=='ACTIVE':out.append(dict(e))
  parents[comp]=out
 return parents[comp]
def witness(start,target,required_views):
 todo=collections.deque([(node(start)['component_id'],[])]);seen=set()
 while todo:
  comp,path=todo.popleft()
  if comp==target:return path
  if comp in seen:continue
  seen.add(comp)
  if len(seen)>10000:raise ValueError('Professional ancestor walk exceeded exact bound')
  for e in links(comp):
   a,b=node(e['child_uid']),node(e['parent_uid'])
   if not required_views.issubset(set(a['views'])&set(b['views'])):continue
   todo.append((b['component_id'],path+[e['id']]))
 return None
sql="""SELECT e.*,a.id alternate_first_edge,a.parent_uid middle_uid,p.component_id root_component
 FROM mids m JOIN edges a ON a.parent_uid=m.uid JOIN edges e ON e.child_uid=a.child_uid
 JOIN nodes p ON p.uid=e.parent_uid JOIN rootcomps r ON r.id=p.component_id
 WHERE a.status='ACTIVE' AND a.relation='IS_A' AND e.status='ACTIVE' AND e.relation='IS_A' AND a.id<>e.id
 ORDER BY e.id,a.id"""
rows=c.execute(sql).fetchall();out=[];seen=set();rejected=[]
for e in rows:
 if e['id'] in seen:continue
 a,b,m=node(e['child_uid']),node(e['parent_uid']),node(e['middle_uid'])
 if any(n['role']!='CLASS' or n['visibility']!='ACTIVE' for n in [a,b,m]):continue
 views=set(a['views'])&set(b['views'])&{'strict','taxonomy'}
 if not views or not views.issubset(set(m['views'])):continue
 path=witness(e['middle_uid'],e['root_component'],views)
 if path is None:rejected.append({'edge_id':e['id'],'reason':'No complete all-CLASS alternate source path in every admitted view'});continue
 proof={'basis':'REDUNDANT_ROOT_EDGE_WITH_ALL_CLASS_PROFESSIONAL_WITNESS','original_edge_id':e['id'],'original_source':e['source'],'professional_middle_uid':e['middle_uid'],'alternate_source_arc_ids':[e['alternate_first_edge'],*path],'preserved_views':sorted(views),'identity_links_cost_zero':True,'native_record_sha256':hashlib.sha256(a['data'].encode()).hexdigest(),'license':'Original source declarations and attribution retained'}
 out.append({'op':'withdraw_edge','uid':e['child_uid'],'parent':e['parent_uid'],'edge_id':e['id'],'source':'Professional class root shortcut reduction','uri':classes[e['middle_uid']]['uri'],'proof':proof});seen.add(e['id'])
# Expand any witness that uses another withdrawn shortcut to surviving arcs.
replacements={r['edge_id']:r['proof']['alternate_source_arc_ids'] for r in out}
def expand(edge_id,seen=()):
 if edge_id not in replacements:return [edge_id]
 if edge_id in seen:raise ValueError('Professional witness dependency cycle')
 return [x for e in replacements[edge_id] for x in expand(e,seen+(edge_id,))]
for r in out:
 r['proof']['alternate_source_arc_ids']=[x for e in r['proof']['alternate_source_arc_ids'] for x in expand(e)]
 if set(r['proof']['alternate_source_arc_ids'])&replacements.keys():raise ValueError('Witness would be withdrawn')
 r['proof']['alternate_arcs_remain_active_after_bundle']=True
with (O/'root_shortcut_repairs.jsonl').open('w') as f:
 for r in out:f.write(json.dumps(r,sort_keys=True,ensure_ascii=False)+'\n')
summary={'candidate_pairs':len(rows),'witnessed_root_shortcuts':len(out),'by_professional_domain':dict(collections.Counter(classes[r['proof']['professional_middle_uid']]['domain'] for r in out)),'unproved_pairs_retained':len(rejected),'removed_source_claims':0};(O/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
