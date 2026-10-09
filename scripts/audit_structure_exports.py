#!/usr/bin/env python3
"""Check complete public training exports against independently checked matrices."""
from __future__ import annotations

if not __debug__:
    raise RuntimeError("Optimized Python is forbidden for mandatory structural checks")

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
import time
if '--installed-sdk' not in sys.argv:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
else:
    import fineatlas
    assert Path(fineatlas.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()) and 'site-packages' in Path(fineatlas.__file__).parts, 'Use the installed SDK'
from fineatlas import FineAtlas


def audit(database, inputs, matrix, output):
    output.mkdir(parents=True,exist_ok=True)
    old=json.loads((inputs/'legacy_policies.json').read_text())
    new=json.loads((inputs/'reviewed_policies.json').read_text())
    accepted=json.loads((matrix/'summary.json').read_text())
    results={}
    modes=[('legacy','legacy',old,'world'),
           ('reviewed_old_floors','reviewed_paths',old,'world'),
           ('reviewed_new_floors','reviewed_paths',new,'world'),
           ('source_native','reviewed_paths',new,'source_native')]
    resolution_path=inputs/'reviewed_resolution_policies.json'
    if resolution_path.exists():
        resolved=json.loads(resolution_path.read_text())
        modes.extend([('reviewed_rank_floors','reviewed_paths',resolved,'world'),
                      ('source_native_rank_floors','reviewed_paths',resolved,'source_native')])
    with FineAtlas(database) as tree:
        for name,admission,policies,scope in modes:
            start=time.monotonic();results[name]={}
            with (matrix/(name+'-pairs.csv')).open() as stream:
                records=iter(csv.DictReader(stream))
                for dataset,entry in accepted[name]['datasets'].items():
                    config=policies[dataset]
                    if scope=='source_native':config=config['source_native']
                    options={k:v for k,v in config.items() if k in {'policy','requirement','source_scope','coarse_roots'}}
                    directory=output/name/dataset
                    result=tree.export_training(dataset,directory,admission_mode=admission,
                        task_boundary_roots=new[dataset]['task_boundary_roots'] if admission=='reviewed_paths' else (),
                        target_scope=scope,**options)
                    checked_labels=json.loads((matrix/(name+'-'+dataset+'-labels.json')).read_text())
                    by_id={r['class_id']:r for r in checked_labels}
                    with (directory/'labels.jsonl').open() as labels:
                        seen=[]
                        for line in labels:
                            row=json.loads(line);cid=str(row['target']['class_id']);reference=by_id[cid]
                            assert row['category_reward_applicable'] is True
                            assert row['hierarchy_endpoint_applicable']==(reference['checked']['reason'] is None)
                            assert row['path']==reference['path']
                            assert row['snapshot_revision']==tree._revision
                            seen.append(cid)
                    assert len(seen)==len(set(seen))==len(by_id)==entry['counts']['labels']
                    statuses=Counter()
                    with (directory/'pairs.jsonl').open() as pairs:
                        for line in pairs:
                            pair=json.loads(line);reference=next(records)
                            assert reference['dataset']==dataset
                            assert (pair['left'],pair['right'],pair['status'])==(reference['left'],reference['right'],reference['status'])
                            distance=None if reference['distance']=='' else int(reference['distance'])
                            assert pair['distance']==distance
                            assert [x['uid'] for x in pair.get('lcas',[])]==json.loads(reference['lca_uids'])
                            assert pair['applicable'] or pair['distance'] is None
                            statuses[pair['status']]+=1
                    assert sum(statuses.values())==result['pairs']==entry['counts']['pairs']
                    assert dict(statuses)==result['pair_statuses']
                    results[name][dataset]={'pass':True,'labels':len(seen),'pairs':sum(statuses.values()),
                        'pair_statuses':dict(statuses),'export':str(directory)}
                    print('EXPORT PASS',name,dataset,len(seen),sum(statuses.values()),flush=True)
                assert next(records,None) is None,'Independent matrix has unconsumed rows'
            results[name]['seconds']=time.monotonic()-start
    final={'pass':True,'database_revision':tree._revision,'modes':results,
           'invalid_distances_remain_null':True,'all_dataset_labels_preserved':True}
    (output/'summary.json').write_text(json.dumps(final,indent=2)+'\n')
    return final


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('database','inputs','matrix','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--installed-sdk',action='store_true')
    a=p.parse_args();audit(a.database,a.inputs,a.matrix,a.output)
