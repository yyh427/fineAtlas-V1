#!/usr/bin/env python3
"""Compare snapshots with identical explicit relation/source/grain policies."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas import FineAtlas
from build_unified_candidate import label_key

CONFIGS={
 'cub200':{'policy':'classification','coarse_roots':['wordnet31:01505702-n','v4root:bird','ott:81461'],'source_scope':'avilist','requirement':'species'},
 'fgvc_aircraft':{'policy':'design','coarse_roots':['wordnet31:02689427-n'],'requirement':'model_design'},
 'flowers102':{'policy':'classification','coarse_roots':['wordnet31:00017402-n'],'requirement':'species'},
 'pets37':{'policy':'classification','coarse_roots':['wordnet31:00015568-n'],'requirement':'hierarchy'},
 'stanford_dogs':{'policy':'classification','coarse_roots':['wordnet31:02086723-n'],'requirement':'hierarchy'},
 'stanford_cars':{'policy':'configuration','coarse_roots':['wordnet31:02961779-n'],'requirement':'configuration'},
}

def run(database,view,primary_records,output):
    output.mkdir(parents=True,exist_ok=True);keys={}
    for r in json.loads(primary_records.read_text()):
        for field in ('English_name_AviList','English_name_Clements_v2025','English_name_BirdLife_v10'):
            name=r['row'].get(field)
            if name:keys.setdefault(label_key(name),set()).add(r['uid'])
    with FineAtlas(database,relation_view=view) as tree:
        excluded={str(r['class_id']):'No unique full primary checklist annotation alignment'
                  for r in tree.task_labels('cub200') if len(keys.get(label_key(r['label']),set()))!=1}
        summary={}
        for dataset,config in CONFIGS.items():
            index=tree.relation_reward_index(dataset,excluded_labels=excluded if dataset=='cub200' else None,**config)
            counts=Counter()
            with (output/(dataset+'_pairs.jsonl')).open('w') as stream:
                for pair in index.pairs():
                    counts[pair['status']]+=1;stream.write(json.dumps(pair,ensure_ascii=False)+'\n')
            summary[dataset]={'pairs':sum(counts.values()),'statuses':dict(counts),'configuration':config,
                              'annotation_review_labels':sorted(excluded) if dataset=='cub200' else [],
                              'revision':tree._revision,'view':view,
                              'policy_definition':'Exact same typed source/grain/floor rules; snapshot target/identity/edge differences remain observable',
                              'scientific_or_visual_reward_calibration':False}
            (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
            print(dataset,summary[dataset],flush=True)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--view',default='unified');p.add_argument('--primary-records',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    run(a.database,a.view,a.primary_records,a.output)
