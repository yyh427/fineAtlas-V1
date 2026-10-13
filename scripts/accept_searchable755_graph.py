"""Every source class: actual expansion, dynamic candidates and typed witnesses.

These are private structural probes, not a claim that a visual model chooses the
anchors. No full source-class list is sent to the experiment model interface.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from fineatlas import FineAtlas, __version__
from fineatlas.repair_candidate import CORE_COUNTS


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);args=p.parse_args()
    r=args.root;db=r/'artifacts/fineatlas.sqlite';rows=[];counts={};expansion={};ranges={};errors=[]
    out=r/'reports/graph_acceptance';out.mkdir(exist_ok=True)
    with FineAtlas(db,relation_view='unified') as a:
        def collect(anchor,depth,dataset=None,grains=None,purpose='discovery'):
            key=(anchor,depth,dataset,tuple(grains or []),purpose)
            cache=expansion if depth==1 and purpose=='discovery' else ranges
            if key in cache:return cache[key]
            cursor=None;uids=set();items=[];keys=set();pages=0;duplicates=0;diag={}
            while True:
                page=a.scope_candidates(anchor,max_depth=depth,dataset=dataset,
                    target_granularity=grains,purpose=purpose,limit=1000,cursor=cursor,
                    node_budget=100000,edge_budget=500000)
                pages+=1;diag=page['diagnostics']
                for n in page['items']:
                    duplicates+=int(n['presentation_key'] in keys);keys.add(n['presentation_key'])
                    uids.update(x['uid'] for x in n['representations']);items.append(n)
                if not page['has_more']:break
                cursor=page['next_cursor']
            value={'uids':uids,'items':items,'diagnostics':diag,'pages':pages,'duplicates':duplicates}
            cache[key]=value;return value
        for ds,expected in CORE_COUNTS.items():
            stats=Counter()
            natives=a.con.execute('SELECT * FROM native_classes WHERE dataset=? ORDER BY CAST(class_id AS INTEGER)',(ds,)).fetchall()
            if len(natives)!=expected:errors.append({'dataset':ds,'inventory_count':len(natives)})
            for n in natives:
                try:
                    node=a.node(n['uid']);world=a.world_mapping_status(ds,n['class_id']);path=a.scope_path(n['uid'],n['domain'])
                    steps=path.get('path',[]);expanded=[]
                    for step in steps:
                        page=collect(step['from_uid'],1)
                        expanded.append({'anchor':step['from_uid'],'child':step['to_uid'],
                            'found':step['to_uid'] in page['uids'],'scan_complete':page['diagnostics']['scan_complete'],
                            'pages':page['pages'],'duplicate_presentations':page['duplicates']})
                    # Use a non-self, broader anchor when the path supports it.
                    anchor=steps[-2]['from_uid'] if len(steps)>1 else path.get('root_uid')
                    depth=len(steps)-next((i for i,s in enumerate(steps) if s['from_uid']==anchor),0)
                    dynamic=collect(anchor,depth,ds,['source_category'],'answers') if anchor else None
                    eligible=a.candidate_contract(n['uid'],dataset=ds)
                    evaluation=a.evaluate_exact(ds,n['class_id'],predicted_uid=n['uid'])
                    native_parents=list(a._scope_links(n['uid'],direction='parents'))
                    def coarse_parent(uid):
                        parent=a.node(uid)
                        if parent.get('attributes',{}).get('identity_scope')=='SOURCE_VERSION_CONCEPT':
                            return False
                        return uid in {'wordnet31:01505702-n','wordnet31:00017402-n',
                            'wordnet31:00015568-n','wordnet31:03796768-n'} or parent.get('normalized_rank') in {
                            'kingdom','phylum','class','order','family'}
                    coarse=bool(native_parents) and all(coarse_parent(x['parent_uid']) for x in native_parents)
                    checks={'node':bool(node),'legal_path':path['status']=='CONNECTED' and bool(steps),
                            'actual_expand':bool(expanded) and all(x['found'] and x['scan_complete'] for x in expanded),
                            'dynamic_candidates':bool(dynamic and n['uid'] in dynamic['uids'] and dynamic['diagnostics']['scan_complete']),
                            'answer_eligible':eligible['native_answer_eligible'],'native_exact':evaluation['native_exact'],
                            'navigation_not_identity':not path.get('world_identity_equivalence_implied',True),
                            'duplicates':bool(dynamic and dynamic['duplicates']==0) and all(x['duplicate_presentations']==0 for x in expanded)}
                    source_unit=node.get('attributes',{}).get('source_unit','UNKNOWN')
                    row={'dataset':ds,'original_id':n['class_id'],'original_name':n['label'],'source_node':n['uid'],
                         'original_raw_label':n['raw_label'],
                         'author_name':json.loads(n['proof']).get('increment_native_record',{}).get('raw_record',{}).get('raw_record',{}).get('author_category',{}).get('name',n['label']),
                         'world_node':world['uid'],'world_status':world['effective_status'],
                         'granularity':{'source':n['object_granularity'],'source_unit':source_unit,
                            'world_rank':a.node(world['uid']).get('normalized_rank') if world['uid'] else None},
                         'domain_entry':path.get('domain_entry'),'domain_root':path.get('root_uid'),
                         'complete_path':steps,'relationship_types':[x['relation'] for x in steps],
                         'evidence':[{'id':x['evidence_id'],'source':x['source'],'provenance':x['source_provenance']} for x in steps],
                         'expansion_reachability':expanded,'dynamic_anchor':anchor,'dynamic_max_depth':depth,
                         'dynamic_candidate_eligible':checks['dynamic_candidates'],'answer_eligible':checks['answer_eligible'],
                         'native_exact':checks['native_exact'],'coarse_only':coarse,
                         'remaining':(['F_WORLD_RANGE_REVIEW'] if not world['world_identity_verified'] else [])+
                            (['F_FINE_STRUCTURE_MISSING'] if coarse else []),
                         'reproduce':{'method':'scope_candidates','anchors':[anchor],'dataset':ds,
                            'target_granularity':['source_category'],'max_depth':depth,
                            'node_budget':100000,'edge_budget':500000,'limit':1000},
                         'checks':checks,'passed':all(checks.values())}
                    rows.append(row)
                    for key,value in checks.items():stats[key]+=bool(value)
                    stats['classes']+=1;stats['passed']+=row['passed'];stats['world_'+world['effective_status']]+=1
                    stats['coarse_only']+=coarse
                    if not row['passed']:errors.append({'dataset':ds,'class_id':n['class_id'],'checks':checks})
                except Exception as exc:errors.append({'dataset':ds,'class_id':n['class_id'],'error':repr(exc)})
            counts[ds]=dict(stats);print(ds,dict(stats),flush=True)
            (out/'paths_and_checks755.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
        summary={'database':str(db),'database_revision':a._revision,'sdk_version':__version__,
            'scope':'All original755; model-independent structural witnesses and actual interfaces',
            'datasets':counts,'totals':dict(sum((Counter(x) for x in counts.values()),Counter())),
            'errors':errors,'passed':not errors and len(rows)==755,
            'model_recognition_measured':False,'world_semantic_full_certification':False}
        (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
        fields=list(rows[0])
        with (out/'755类可搜索图逐项验收.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})
        (out/'range_and_expansion_statistics.json').write_text(json.dumps([
            {'query':list(k),'pages':v['pages'],'duplicates':v['duplicates'],'diagnostics':v['diagnostics']}
            for cache in (expansion,ranges) for k,v in cache.items()],ensure_ascii=False,indent=2))
    if errors:raise SystemExit('Structural acceptance has incomplete items; inspect summary')


if __name__=='__main__':main()
