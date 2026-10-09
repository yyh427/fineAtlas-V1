#!/usr/bin/env python3
"""Freeze nonfocus controls by domain, source, role and observed issue before applying changes."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas import FineAtlas


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',required=True);p.add_argument('--seed',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    samples=json.loads(a.seed.read_text());existing={(r['view'],r['domain'],r['uid']) for r in samples}
    with FineAtlas(a.baseline) as tree:
        target_uids={tree.target(r[0],r[1])['target_uid'] for r in tree.con.execute('SELECT dataset,class_id FROM dataset_targets').fetchall()}
        # Pick one source/role representative per native member stratum, not
        # a benchmark list. Source payload and current role are never changed.
        rows=tree.con.execute('''SELECT dm.view,dr.canonical_name,n.source,dm.role,min(dm.uid)
          FROM domain_members dm JOIN domain_registry dr ON dr.domain_id=dm.domain_id
          JOIN nodes n ON n.uid=dm.uid
          GROUP BY dm.view,dm.domain_id,n.source,dm.role
          ORDER BY dm.view,dr.canonical_name,n.source,dm.role''').fetchall()
    for view in ('strict','taxonomy','membership'):
        with FineAtlas(a.baseline,relation_view=view) as tree:
            for v,domain,source,role,uid in rows:
                if v!=view or uid in target_uids or (v,domain,uid) in existing:continue
                node=tree.node(uid);path=tree.path_result(uid)
                samples.append({'view':v,'domain':domain,'uid':uid,'label':node['label'],
                                'role':role,'source':source,'status':path['status'],
                                'selection':'native domain/source/role stratum'})
                existing.add((v,domain,uid))
    for sample in samples:
        sample['issue_type']=('ROOT_UNREACHABLE' if sample['status'] not in ('ROOT','CONNECTED') else
                              'TYPED_ENTITY_ROUTE' if sample['role'] not in ('CLASS','BIOLOGICAL_VARIANT','DATASET_CATEGORY') else
                              'NATIVE_CLASSIFICATION' if sample['view']=='taxonomy' else 'CLASSIFICATION_CONTROL')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(samples,ensure_ascii=False,indent=2)+'\n')
    summary={'count':len(samples),'domains':len({r['domain'] for r in samples}),
             'sources':len({r['source'] for r in samples}),'roles':dict(Counter(r['role'] for r in samples)),
             'issues':dict(Counter(r['issue_type'] for r in samples)),
             'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),
             'benchmark_target_uids_excluded':True,'baseline':Path(a.baseline).name}
    a.output.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
