#!/usr/bin/env python3
"""Frozen indexed pagination, source-wide branches and equal-size timing checks."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas import FineAtlas

PARENTS=('hierarchy-type:aircraft-4-engine-1','hierarchy-type:car-gasoline',
         'geonames-feature:H.STM')

def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def pagination(tree,parent,kind,filters,include_coarse):
    scope,status=tree._browse_scope(parent)
    if status!='OK':return {'status':status,'pass':False}
    where,args=tree._browse_where(scope,kind,None,filters,include_coarse=include_coarse)
    expected={r[0] for r in tree.con.execute('SELECT DISTINCT b.child_component FROM browse_links b WHERE '+where,args)}
    actual=set();cursor=None;pages=0;duplicates=0
    while True:
        page=tree.browse_children_page(parent,1000,node_kind=kind,filters=filters,
                                      include_coarse=include_coarse,cursor=cursor)
        ids=[n['component_id'] for n in page['items']]
        duplicates+=sum(i in actual for i in ids);actual.update(ids);pages+=1
        if not page['next_cursor']:break
        cursor=page['next_cursor']
    sql='EXPLAIN QUERY PLAN SELECT b.child_component FROM browse_links b WHERE '+where+' AND b.child_component>? GROUP BY b.child_component ORDER BY b.child_component LIMIT ?'
    plan=[list(r) for r in tree.con.execute(sql,[*args,-1,21])]
    return {'status':'CHECKED','expected_identities':len(expected),'returned_identities':len(actual),
            'pages':pages,'duplicates':duplicates,'missing':len(expected-actual),
            'extra':len(actual-expected),'pass':expected==actual and duplicates==0,
            'query_plan':plan,'ordinary_query_page_limit':20,'maximum_page_limit':1000,
            'audit_full_identity_set_materialization_only':True}

def timings(database,view,parent,kind,filters):
    # One fresh process should run each snapshot's audit independently. Here
    # cold means a fresh SQLite/SDK connection; OS page cache is not purged.
    with FineAtlas(database,relation_view=view) as tree:
        samples=[];counts=[]
        for repeat in range(11):
            start=time.perf_counter()
            page=tree.browse_children_page(parent,20,node_kind=kind,filters=filters,include_coarse=True)
            elapsed=time.perf_counter()-start
            samples.append(elapsed);counts.append(len(page['items']))
    ordered=sorted(samples[1:])
    return {'view':view,'snapshot':str(database),'parent':parent,'kind':kind,'filters':filters,
            'cold_connection_seconds':samples[0],'warm_median_seconds':sum(ordered[4:6])/2,
            'warm_samples_seconds':samples[1:],'returned_counts':counts,
            'cache_condition':'Fresh SDK/SQLite connection then ten repeats; shared OS cache left intact',
            'page_limit':20,'include_coarse':True}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    checks={};branches=[]
    with FineAtlas(a.database) as tree:
        checks['plane_full']=pagination(tree,PARENTS[0],'MODEL',{'source':'faa'},True)
        checks['plane_preferred']=pagination(tree,PARENTS[0],None,{},False)
        checks['car_full']=pagination(tree,PARENTS[1],'CONFIGURATION',{},True)
        checks['car_preferred']=pagination(tree,PARENTS[1],None,{},False)
        for parent in PARENTS:
            branches.append({'parent':parent,'node':tree.node(parent),
                             'full':tree.browse_summary(parent,include_coarse=True),
                             'default':tree.browse_summary(parent,include_coarse=False),
                             'first_page':tree.browse_children_page(parent,20),
                             'manufacturer_groups':tree.browse_groups(parent,'manufacturer',20,node_kind=None),
                             'catalogue_grouping_is_classification':False})
        dump(a.output/'pagination.json',checks);dump(a.output/'branches.json',branches)
    comparisons=[]
    for parent,kind,filters in [(PARENTS[0],'MODEL',{'source':'faa'}),(PARENTS[1],'CONFIGURATION',{'source':'epa'})]:
        before=timings(a.baseline,'taxonomy',parent,kind,filters)
        after=timings(a.database,'unified',parent,kind,filters)
        comparisons.append({'before':before,'after':after,
                            'same_return_scale':before['returned_counts']==after['returned_counts']})
    dump(a.output/'performance.json',comparisons)
    summary={'pagination_pass':all(c['pass'] for c in checks.values()),
             'all_pages_checked':True,'same_return_scale':all(r['same_return_scale'] for r in comparisons),
             'browsing_improvement_is_not_semantic_depth_certification':True}
    dump(a.output/'summary.json',summary);print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
