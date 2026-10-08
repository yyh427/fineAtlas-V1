#!/usr/bin/env python3
"""Actual public before/after paths for labels and source-wide physical fields."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas import FineAtlas


def run(database,baseline,inputs,output):
    classes={};selected={}
    for line in (inputs/'unified_field_refinements.jsonl').open():
        r=json.loads(line)
        if r['op']=='class':classes[r['uid']]=r
        elif r['op']=='link' and r['parent'] not in selected:selected[r['parent']]=r
    result={}
    with FineAtlas(baseline,relation_view='taxonomy') as before,FineAtlas(database) as after:
        for domain,dataset,parents in [
            ('aircraft','fgvc_aircraft',['authority-refinement:single-piston-land','authority-refinement:single-piston-sea','authority-refinement:single-piston-amphibian']),
            ('cars','stanford_cars',['authority-refinement:gasoline-epa-compact','authority-refinement:gasoline-epa-midsize','authority-refinement:gasoline-epa-large'])]:
            rows=[]
            for class_id in ('1','2'):
                b=before.target(dataset,class_id);a=after.target(dataset,class_id)
                rows.append({'kind':'benchmark','class_id':class_id,'label':a['label'],
                             'before_uid':b['target_uid'],'after_uid':a['target_uid'],
                             'before':before.path_result(b['target_uid']),
                             'after':after.task_path(dataset,class_id),
                             'meaning':'Preserved source roles and view-specific typed paths; path length alone is not an improvement claim'})
            for parent in parents:
                r=selected[parent];uid=r['uid']
                page=after.browse_children_page(parent,node_kind='MODEL' if domain=='aircraft' else 'CONFIGURATION',limit=20)
                location=after.browse_location(uid,domain=domain)
                rows.append({'kind':'nonbenchmark_source_field','uid':uid,'label':after.node(uid)['label'],
                             'before':before.path_result(uid),'after':after.path_result(uid),
                             'new_intermediate_uid':parent,'definition':classes[parent]['definition'],
                             'source_field_evidence':r['proof'],'relation':r['relation'],
                             'location':location,'representative_parent_page':page,
                             'meaning':'Explicit native field narrows the existing physical class; no model-series name guessing or source UID deletion'})
            result[domain]=rows
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:len(v) for k,v in result.items()}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('database','baseline','inputs','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.database,a.baseline,a.inputs,a.output)
