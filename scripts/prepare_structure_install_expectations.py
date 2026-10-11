"""Operational generator: actual accepted local artifact -> public expectations."""
import argparse,collections,json,pathlib
from fineatlas import FineAtlas
p=argparse.ArgumentParser();p.add_argument('--database',type=pathlib.Path,required=True);p.add_argument('--acceptance',type=pathlib.Path,required=True);p.add_argument('--manifest',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
r=json.loads(a.acceptance.read_text());m=json.loads(a.manifest.read_text())
if not r.get('local_all_pass'):raise RuntimeError('Complete local acceptance required')
for k in ('release','database_revision'):
 if r[k]!=m[k]:raise RuntimeError('Accepted manifest mismatch '+k)
if r['database_sha256']!=m['database']['sha256']:raise RuntimeError('Accepted SHA mismatch')
world=('cub200','fgvc_aircraft','flowers102','pets37','stanford_dogs','stanford_cars')
x={'schema':'FINEATLAS_UNIFIED_ACCEPTANCE_V1','release':m['release'],'database_revision':m['database_revision'],'database_sha256':m['database']['sha256'],'domain_inventory':m['domain_inventory'],'domains':{'actual':m['domain_count'],'public_contract_passes':m['domain_count']},'pairs':{},'labels':{}}
with FineAtlas(a.database) as t:
 domains={z['domain']:z['root_uids'] for z in t.domains()}
 if set(domains)!=set(m['domain_inventory']) or any(set(domains[k])!=set(m['domain_inventory'][k]) for k in domains):raise RuntimeError('Actual accepted domain inventory differs')
 for ds in world:
  statuses=collections.Counter(z['status'] for z in t.relation_reward_index(ds).pairs());x['pairs'][ds]={'pairs':sum(statuses.values()),'pair_statuses':dict(statuses)}
for view in ('strict','taxonomy','membership','unified'):
 with FineAtlas(a.database,relation_view=view) as t:
  c=collections.Counter()
  for ds in world:
   for z in t.task_labels(ds):
    q=t.connection_status(z['target_uid']);path=t.path_result(z['target_uid'])
    if q['path_status']!=path['status']:raise RuntimeError('Actual path mismatch')
    c['labels']+=1;c['stored_identity_claim_verified']+=z['stored_identity_claim_verified'];c['identity_verified']+=z['identity_verified'];c['root_reachable']+=q['root_reachable'];c['path_state_consistent']+=1;c['hierarchy_admitted']+=z['task_admission']['usable']
  x['labels'][view]=dict(c)
a.output.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');print('ACCEPTED EXPECTATIONS',a.output,flush=True)
