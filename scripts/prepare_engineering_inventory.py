#!/usr/bin/env python3
"""Export retained engineering scope records for reproducible source review."""
import sqlite3,json,collections,sys,time,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
p=argparse.ArgumentParser();p.add_argument('--database',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();O=a.output;O.mkdir(parents=True,exist_ok=True)
from fineatlas.semantics import role_expression
c=sqlite3.connect(a.database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA temp_store=MEMORY');c.execute('PRAGMA cache_size=-500000')
excluded=set('animals birds plants fungi bacteria archaea mountains mountain_ranges rivers lakes islands beaches valleys volcanoes glaciers deserts aquifers waterfalls forests wetlands rocks minerals clouds habitats marine_habitats coastal_habitats freshwater_habitats forest_habitats grasslands scrub_and_tundra sparse_vegetation_habitats agricultural_habitats artificial_habitats habitat_complexes food_products dishes'.split())
domains=[dict(r) for r in c.execute('SELECT * FROM domain_registry ORDER BY domain_id') if r['canonical_name'] not in excluded]
records={};stats={}
for d in domains:
 rows=c.execute('SELECT n.*,p.node_kind,p.attributes,'+role_expression('n','p')+" role FROM domain_members m JOIN nodes n ON n.uid=m.uid LEFT JOIN node_profiles p ON p.uid=n.uid WHERE m.domain_id=? AND m.view='taxonomy' AND n.visibility='ACTIVE' AND m.role IN ('CLASS','MODEL','MODEL_FAMILY')",(d['domain_id'],));count=collections.Counter()
 for row in rows:
  n=dict(row);count[n['role']]+=1
  if n['uid'] not in records:records[n['uid']]={**n,'scopes':[]}
  records[n['uid']]['scopes'].append(d['canonical_name'])
 stats[d['canonical_name']]=dict(count)
 print('DOMAIN',d['canonical_name'],dict(count),flush=True)
with (O/'engineering_nodes.jsonl').open('w') as f:
 for u,n in sorted(records.items()):f.write(json.dumps(n,ensure_ascii=False)+'\n')
(O/'engineering_inventory.json').write_text(json.dumps({'domains':len(domains),'source_uids':len(records),'roles':dict(collections.Counter(n['role'] for n in records.values())),'domain_roles':stats,'domain_registry':domains},ensure_ascii=False,indent=2)+'\n');print('COMPLETE',len(records),flush=True)
