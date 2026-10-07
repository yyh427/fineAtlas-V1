#!/usr/bin/env python3
"""Finish a prepared hierarchy bundle; retain source terms and checksums."""
import argparse,datetime,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--inputs',required=True);p.add_argument('--sources',required=True);p.add_argument('--preserve-cohorts',action='store_true');a=p.parse_args();I=Path(a.inputs);S=Path(a.sources)
path=I/'hierarchy_facts.jsonl';records=[]
for line in path.open():
 r=json.loads(line)
 if not a.preserve_cohorts and 'en.wikipedia.org/' in r['uri']:
  r['proof']['license']='Wikipedia CC BY-SA 4.0; article URL and retained snapshot attribution preserved'
 elif not a.preserve_cohorts and r['source']=='Environment Ontology native is_a':r['proof']['license']='ENVO CC0 1.0'
 records.append(r)
if not a.preserve_cohorts:
 with path.open('w') as f:
  for r in records:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*1024*1024):h.update(b)
 return h.hexdigest()
release_path=I/'review_release.json';version=json.loads(release_path.read_text())['version'] if release_path.exists() else 'v1.8.0-hierarchy-review'
manifest={'version':version,'frozen_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'hierarchy_records':len(records),'source_files':[{'path':str(p.relative_to(S)),'sha256':digest(p),'bytes':p.stat().st_size} for p in sorted(S.rglob('*')) if p.is_file()],'inputs':[{'path':str(p.relative_to(I)),'sha256':digest(p),'bytes':p.stat().st_size} for p in sorted(I.rglob('*')) if p.is_file() and p.name not in {'hierarchy_work.incomplete','hierarchy_facts.incomplete','hierarchy_freeze.json'}]}
(I/'hierarchy_freeze.json').write_text(json.dumps(manifest,indent=2)+'\n')
(I/'hierarchy_work.incomplete').unlink(missing_ok=True)
print('FROZEN',len(records),digest(path),flush=True)
