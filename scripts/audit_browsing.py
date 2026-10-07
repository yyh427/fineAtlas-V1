#!/usr/bin/env python3
"""Exercise public browsing, fixed samples, full pages and matched query workloads."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fineatlas import FineAtlas


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database', required=True)
    p.add_argument('--baseline', required=True)
    p.add_argument('--fixed-samples', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
    start = time.monotonic(); portals=[]; aliases=[]; focus_checks=[]; fixed=[]; pages=[]; examples=[]; performance=[]
    for view in ('strict', 'taxonomy', 'membership'):
        with FineAtlas(a.database, relation_view=view) as tree, FineAtlas(a.baseline, relation_view=view) as old:
            for entry in tree.domains(include_aliases=True):
                name=entry.get('requested_domain',entry['domain'])
                for role in ('CLASS','SERIES','MODEL','CONFIGURATION','INSTANCE'):
                    result=tree.browse_children_page(name,3,node_kind=role)
                    assert len(result['items'])<=3 and result['direct_only'], (view,name,role,result)
                    for item in result['items']:
                        location=tree.browse_location(item['uid'],name)
                        assert location['status']=='OK', (view,name,item['uid'],location)
                        assert location['connection_status']['root_reachable']==(location['path']['status'] in ('ROOT','CONNECTED'))
                        found=False; cursor=None
                        while True:
                            matches=tree.search_page(item['label'],200,domain=name,cursor=cursor,exact=True)
                            found |= any(n['uid']==item['uid'] for n in matches['items'])
                            cursor=matches['next_cursor']
                            if found or not cursor:break
                        assert found,(view,name,item['uid'],'member missing from scoped search')
                    portals.append({'view':view,'entry':name,'role':role,'status':result['status'],'items':len(result['items'])})
                assert tree.browse_summary(name)['status']=='OK'
            for sample in json.loads(a.fixed_samples.read_text()):
                if sample['view']!=view:continue
                uid=sample['uid'];before=old.path_result(uid);after=tree.path_result(uid)
                assert before==after,(view,uid,'shortest path regression')
                assert old.connection_status(uid)==tree.connection_status(uid),(view,uid,'state regression')
                finer=tree.browse_path_result(uid)
                assert finer['status']==before['status'],(view,uid,finer['status'],before['status'])
                fixed.append({'view':view,'domain':sample['domain'],'uid':uid,'role':sample['role'],
                              'shortest_status':after['status'],'shortest_unchanged':True,
                              'display_changed':finer['path']!=before['path'],
                              'display_distance':finer.get('distance'),'shortest_distance':before.get('distance')})
            for alias, in tree.con.execute('SELECT alias FROM domain_aliases ORDER BY alias').fetchall():
                entry=tree.domain(alias);canonical=entry['domain']
                assert old.domain(alias)['domain']==canonical
                page=tree.browse_children_page(alias,1)
                same=tree.browse_children_page(canonical,1)
                assert page['status']==same['status'] and [n['uid'] for n in page['items']]==[n['uid'] for n in same['items']],(view,alias)
                aliases.append({'view':view,'alias':alias,'domain':canonical,'same_public_result':True})
            datasets=('cub200','fgvc_aircraft','flowers102','pets37','stanford_cars','stanford_dogs')
            for dataset in datasets:
                for class_id, in tree.con.execute('SELECT class_id FROM dataset_targets WHERE dataset=? ORDER BY length(class_id),class_id',(dataset,)).fetchall():
                    before=old.target(dataset,class_id);after=tree.target(dataset,class_id)
                    for field in ('target_uid','decision_status','identity_verified','mapping_verified','mapping_kind','native_label_admission'):
                        assert before[field]==after[field],(view,dataset,class_id,field)
                    uid=after['target_uid'];path=old.path_result(uid);display=tree.browse_path_result(uid)
                    assert display['status']==path['status'],(view,dataset,class_id,path['status'],display['status'])
                    focus_checks.append({'view':view,'dataset':dataset,'class_id':class_id,'uid':uid,
                                         'identity_and_label_preserved':True,'status':path['status'],
                                         'display_changed':path['path']!=display['path']})
        write(a.output/'portal_checks.json',portals);write(a.output/'fixed_samples.json',fixed)
        write(a.output/'alias_checks.json',aliases);write(a.output/'focus_browse_checks.json',focus_checks)
        print('PORTALS AND FIXED SAMPLES',view,len(portals),len(fixed),flush=True)
    with FineAtlas(a.database) as tree, FineAtlas(a.baseline) as old:
        largest=list(tree.con.execute("""SELECT parent_component,role,relation,count(*) n
          FROM browse_links WHERE view='strict' AND role IN ('MODEL','CONFIGURATION')
          GROUP BY parent_component,role,relation
          HAVING count(*)<=150000
          ORDER BY n DESC,parent_component,role,relation LIMIT 8"""))
        for parent,role,relation,total in largest:
            uid=tree.con.execute('SELECT uid FROM browse_nodes WHERE component_id=? ORDER BY uid LIMIT 1',(parent,)).fetchone()[0]
            for full in (True,False):
                expected={r[0] for r in tree.con.execute("""SELECT child_component FROM browse_links b
                  WHERE view='strict' AND parent_component=? AND role=? AND relation=?"""+
                  ('' if full else " AND NOT EXISTS(SELECT 1 FROM browse_preferences p WHERE p.view=b.view AND p.parent_component=b.parent_component AND p.child_component=b.child_component AND p.role=b.role AND p.relation=b.relation)"),(parent,role,relation))}
                actual=[];cursor=None;count=0;started=time.monotonic()
                while True:
                    result=tree.browse_children_page(uid,1000,node_kind=role,relation=relation,cursor=cursor,include_coarse=full)
                    ids=[n['identity_component'] for n in result['items']]
                    assert ids==sorted(ids) and len(ids)<=1000
                    if ids and actual:assert actual[-1]<ids[0]
                    actual.extend(ids);count+=1;cursor=result['next_cursor']
                    if not cursor:break
                assert len(actual)==len(set(actual)) and set(actual)==expected,(uid,role,relation,full)
                digest=hashlib.sha256('\n'.join(map(str,actual)).encode()).hexdigest()
                pages.append({'parent_uid':uid,'parent_label':tree.node(uid)['label'],'role':role,'relation':relation,
                              'include_coarse':full,'identities':len(actual),'pages':count,
                              'identity_set_sha256':digest,'complete_set_equal':True,'seconds':time.monotonic()-started})
                write(a.output/'complete_pagination.json',pages)
            scope,_=tree._browse_scope(uid)
            where,args=tree._browse_where(scope,role,relation,{},include_coarse=True)
            sql='SELECT b.child_component,min(b.role),group_concat(DISTINCT b.role) FROM browse_links b WHERE '+where+' AND b.child_component>? GROUP BY b.child_component ORDER BY b.child_component LIMIT ?'
            plan=[list(r) for r in tree.con.execute('EXPLAIN QUERY PLAN '+sql,[*args,-1,21])]
            assert any('SEARCH b USING' in r[-1] for r in plan),plan
            groups=tree.browse_groups(uid,'manufacturer',20,node_kind=role)
            for group in groups['items']:
                assert group['is_a'] is False
                predicate,parameters=tree._browse_where(scope,role,None,group['filters'])
                actual_count=tree.con.execute('SELECT count(DISTINCT b.child_component) FROM browse_links b WHERE '+predicate,parameters).fetchone()[0]
                assert actual_count==group['concepts'],(uid,group,actual_count)
            pages[-1]['query_plan']=plan;pages[-1]['group_count_index_used']=groups['count_index_used']
            durations=[]
            for repeat in range(6):
                tick=time.perf_counter()
                bounded=tree.browse_children_page(uid,20,node_kind=role,relation=relation)
                durations.append(time.perf_counter()-tick)
                assert len(bounded['items'])<=20
            pages[-1]['bounded_browse_performance']={
                'returned':len(bounded['items']),'first_query_seconds':durations[0],
                'repeat_median_seconds':statistics.median(durations[1:]),
                'os_cache':'shared, not flushed','sdk_connection':'already open'}
        # Compare the SAME legacy workload, result limit and connection/cache
        # conditions. Separate first connection query from repeated queries;
        # this does not claim OS page cache was flushed.
        for name in ('aircraft','cars','birds','mountain_ranges','ceramic_capacitors'):
            seed=old.domain_page(name,1)['items'][0]
            for operation in ('domain_page','search','instances','path'):
                for mode,database in (('before',a.baseline),('after',a.database)):
                    opened=time.perf_counter();subject=FineAtlas(database)
                    startup=time.perf_counter()-opened
                    with subject:
                        runs=[];signature=None
                        for i in range(6):
                            tick=time.perf_counter()
                            if operation=='domain_page':result=subject.domain_page(name,20)
                            elif operation=='search':result=subject.search_page(seed['label'],20,domain=name,exact=True)
                            elif operation=='instances':result=subject.domain_instances(name,20)
                            else:result=subject.path_result(seed['uid'])
                            runs.append(time.perf_counter()-tick)
                            current=([n['uid'] for n in result['items']] if operation!='path' else
                                     [result['status'],result.get('distance'),*[n['uid'] for n in result['path']]])
                            if signature is None:signature=current
                            assert signature==current
                        performance.append({'domain':name,'operation':operation,'version':mode,
                                            'returned':len(result['path']) if operation=='path' else len(result['items']),
                                            'result_uids':signature,'sdk_open_seconds':startup,
                                            'first_connection_query_seconds':runs[0],
                                            'repeat_median_seconds':statistics.median(runs[1:]),
                                            'os_cache':'not flushed; shared OS cache, fresh SDK connection'})
                assert performance[-1]['result_uids']==performance[-2]['result_uids']
        # Five independently selected source examples per transport domain:
        # coarse route replacements are real recorded relations, not labels.
        for domain in ('aircraft','cars'):
            entry=tree.domain(domain)
            selected=list(tree.con.execute("""SELECT p.child_component,min(n.uid) uid
              FROM browse_preferences p JOIN domain_components dc ON dc.component_id=p.child_component
              JOIN browse_nodes n ON n.component_id=p.child_component
              WHERE p.view='strict' AND dc.domain_id=? AND dc.view='strict'
              GROUP BY p.child_component ORDER BY p.child_component LIMIT 8""",(entry['domain_id'],)))
            # If a domain has no finer route, report representative native
            # grouping examples honestly instead of inventing new hierarchy.
            if len(selected)<3:
                selected=list(tree.con.execute("""SELECT DISTINCT n.component_id,n.uid
                  FROM domain_members dm JOIN browse_nodes n ON n.uid=dm.uid
                  JOIN browse_facets f ON f.uid=n.uid AND f.facet='manufacturer'
                  WHERE dm.domain_id=? AND dm.view='strict' ORDER BY n.component_id LIMIT 8""",(entry['domain_id'],)))
            focus=[];dataset='fgvc_aircraft' if domain=='aircraft' else 'stanford_cars'
            for row in tree.con.execute('SELECT class_id FROM dataset_targets WHERE dataset=? ORDER BY length(class_id),class_id',(dataset,)).fetchall():
                target=tree.target(dataset,row[0]);uid=target['target_uid']
                if tree.path_result(uid)['status'] not in ('ROOT','CONNECTED'):continue
                focus.append((tree.node(uid)['component_id'],uid))
                if len(focus)==2:break
            used={r[0] for r in focus}
            nonfocus=[r for r in selected if r[0] not in used][:3]
            selected=focus+nonfocus
            assert len(selected)>=5,(domain,'insufficient source examples')
            for component,uid in selected:
                before=old.path_result(uid);after=tree.browse_path_result(uid)
                examples.append({'domain':domain,'uid':uid,'label':tree.node(uid)['label'],
                                 'benchmark_example':uid in {r[1] for r in focus},
                                 'before':before,'after':after,'location':tree.browse_location(uid,domain),
                                 'interpretation':'Source-witnessed finer route' if before['path']!=after['path'] else 'Native catalogue grouping; no new semantic middle class'})
        assert tree.browse_children_page('unknown:uid')['status']=='NOT_FOUND'
        assert tree.locate('test','unknown-domain')['status']=='UNKNOWN_DOMAIN'
        write(a.output/'complete_pagination.json',pages);write(a.output/'path_examples.json',examples)
        write(a.output/'matched_performance.json',performance)
    summary={'all_pass':True,'portal_role_view_checks':len(portals),'fixed_nonfocus_samples':len(fixed),
             'all_stored_alias_view_checks':len(aliases),'focus_label_view_browse_checks':len(focus_checks),
             'focus_display_changes':sum(r['display_changed'] for r in focus_checks),
             'fixed_shortest_paths_and_states_unchanged':True,'fixed_display_changes':sum(s['display_changed'] for s in fixed),
             'complete_branch_page_checks':len(pages),'transport_examples':dict(Counter(e['domain'] for e in examples)),
             'performance_workloads_match':True,'seconds':time.monotonic()-start,
             'images_or_visual_models_run':False}
    write(a.output/'summary.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
