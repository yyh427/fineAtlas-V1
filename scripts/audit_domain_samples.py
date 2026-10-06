#!/usr/bin/env python3
"""Independent stratified path, pagination and export checks on a review database."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fineatlas import FineAtlas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    records, pagination, exports, dag_checks = [], [], [], []
    started = time.perf_counter()
    for view in ('strict', 'taxonomy', 'membership'):
        with FineAtlas(args.database, relation_view=view) as tree:
            for domain in tree.domains():
                name = domain['domain']
                identifier = tree.con.execute('SELECT domain_id FROM domain_registry WHERE canonical_name=?', (name,)).fetchone()[0]
                # Sample both the first source UID and a deepest member of every
                # role, independent of benchmark-label selection.
                groups = list(tree.con.execute('SELECT role,min(uid),max(depth) FROM domain_members WHERE domain_id=? AND view=? GROUP BY role', (identifier,view)))
                selected = set()
                for role, first, depth in groups:
                    selected.add(first)
                    deepest = tree.con.execute('SELECT uid FROM domain_members WHERE domain_id=? AND view=? AND role=? AND depth=? ORDER BY uid LIMIT 1',(identifier,view,role,depth)).fetchone()
                    if deepest: selected.add(deepest[0])
                for uid in sorted(selected):
                    result = tree.path_result(uid)
                    status = tree.connection_status(uid)
                    assert bool(status['root_reachable']) == (result['status'] in ('ROOT','CONNECTED')), (view,name,uid)
                    sources, relations = set(), []
                    for step in result['path']:
                        edge = step['edge']; relation = edge['relation']
                        child = edge.get('child_uid') or edge.get('subject_uid') or step.get('uid')
                        parent = edge.get('parent_uid') or edge.get('object_uid') or step.get('parent_uid')
                        if relation == 'SAME_CONCEPT':
                            a = tree.con.execute('SELECT component_id FROM nodes WHERE uid=?',(child,)).fetchone()
                            b = tree.con.execute('SELECT component_id FROM nodes WHERE uid=?',(parent,)).fetchone()
                            assert a and b and a[0] == b[0], (uid,step)
                        else:
                            native = tree.con.execute("SELECT 1 FROM edges WHERE child_uid=? AND parent_uid=? AND relation=? AND status IN ('ACTIVE','TYPED_ACTIVE')",(child,parent,relation)).fetchone()
                            typed = tree.con.execute("SELECT 1 FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND status='ACTIVE'",(child,parent,relation)).fetchone()
                            assert native or typed, (uid,edge)
                        relations.append(relation); sources.add(edge.get('source',''))
                    node = tree.node(uid)
                    records.append({'view':view,'domain':name,'uid':uid,'label':node['label'],'role':node['node_kind'],'source':node['source'],'status':result['status'],'relations':relations,'path_sources':sorted(sources),'path':result['path']})
                print('DOMAIN', view, name, len(selected), flush=True)
                (args.output/'progress.json').write_text(json.dumps({'view':view,'domain':name,'samples':len(records)}))
    with FineAtlas(args.database) as tree:
        for domain in ('mountain_ranges','fitness_trackers','ceramic_capacitors'):
            method = tree.domain_instances if domain == 'mountain_ranges' else tree.domain_page
            cursor, uids, pages = None, [], 0
            while True:
                page = method(domain,1000,cursor=cursor)
                values = [n['uid'] for n in page['items']]
                assert values == sorted(values)
                if uids and values: assert uids[-1] < values[0]
                uids.extend(values); pages += 1
                cursor = page['next_cursor']
                if not cursor: break
            assert len(uids) == len(set(uids))
            identifier = tree.con.execute('SELECT domain_id FROM domain_registry WHERE canonical_name=?',(domain,)).fetchone()[0]
            count = tree.con.execute("SELECT count(*) FROM domain_members WHERE domain_id=? AND view='strict'" + (" AND role='INSTANCE'" if domain=='mountain_ranges' else ''),(identifier,)).fetchone()[0]
            assert len(uids) == count
            pagination.append({'domain':domain,'items':count,'pages':pages,'complete':True,'stable_unique_order':True})
        for domain in ('fitness_trackers','ceramic_capacitors'):
            path = args.output/(domain+'.jsonl')
            result = tree.export_domain(domain,path,page_size=1000)
            rows = [json.loads(line) for line in path.open()]
            assert len(rows) == result['nodes']
            assert len({r['node']['uid'] for r in rows}) == len(rows)
            assert all(r['relation_view']=='strict' and r['domain']==domain for r in rows)
            exports.append(result)
        homonyms = tree.exact('mustang',100)
        assert len({n['uid'] for n in homonyms}) == len(homonyms)
        assert tree.path_result('not-a-real-source:identifier')['status']=='NOT_FOUND'
        # A SQL recursive closure provides an independent shortest-distance
        # oracle for native classification samples. Typed ancestry is covered
        # by the separate stratified path checks and synthetic DAG tests.
        seeds = [r[0] for r in tree.con.execute("SELECT child_uid FROM edges WHERE status='ACTIVE' AND relation='IS_A' AND child_uid LIKE 'wordnet31:%' GROUP BY child_uid HAVING count(DISTINCT parent_uid)>1 LIMIT 6")]
        for uid in seeds:
            expected = dict(tree.con.execute("""WITH RECURSIVE closure(id,depth) AS (
              SELECT component_id,0 FROM nodes WHERE uid=? UNION
              SELECT p.component_id,cl.depth+1 FROM closure cl CROSS JOIN nodes n
              CROSS JOIN edges e CROSS JOIN nodes p WHERE n.component_id=cl.id
              AND e.child_uid=n.uid AND e.parent_uid=p.uid AND e.relation='IS_A'
              AND e.status='ACTIVE' AND n.visibility='ACTIVE' AND p.visibility='ACTIVE'
              AND cl.depth<128) SELECT id,min(depth) FROM closure GROUP BY id""",(uid,)))
            # Avoid treating a pure-IS_A oracle as an oracle for mixed paths.
            typed = any(tree.con.execute("SELECT 1 FROM nodes n JOIN entity_relations r ON r.subject_uid=n.uid WHERE n.component_id=? AND r.status='ACTIVE' AND r.relation IN ('DESIGN_TYPE_OF','CONFIGURATION_OF','CONFIGURATION_TYPE_OF','SERIES_MEMBER_OF','REGULATED_AS') LIMIT 1",(comp,)).fetchone() for comp in expected)
            if typed: continue
            actual = {n['component_id']:n['distance'] for n in tree.ancestors(uid,include_self=True)}
            assert actual == expected, uid
            parents = list(tree.con.execute("SELECT parent_uid FROM edges WHERE child_uid=? AND relation='IS_A' AND status='ACTIVE'",(uid,)))
            parent = parents[0][0]
            distance = tree.distance(uid,parent,direction='upward')
            assert distance['distance']==1
            assert tree.distance(parent,uid,direction='downward')['distance']==1
            assert tree.distance(uid,parent,direction='undirected')['distance']==1
            lca = tree.lca(uid,parent)
            comp = tree.con.execute('SELECT component_id FROM nodes WHERE uid=?',(parent,)).fetchone()[0]
            assert {n['component_id'] for n in lca['items']} == {comp}
            dag_checks.append({'uid':uid,'direct_parents':len(parents),'ancestor_groups':len(expected),'independent_sql_distances':True,'directed_and_undirected_distances':True,'lca_identity_group':comp})
        assert dag_checks, 'No independent native DAG samples were checked'
        # Admission export agrees exactly with the per-label contract.
        for dataset, in tree.con.execute('SELECT DISTINCT dataset FROM dataset_targets'):
            all_labels = tree.task_labels(dataset, requirement='strict_classification')
            usable = tree.task_labels(dataset, requirement='strict_classification',usable_only=True)
            assert {r['class_id'] for r in usable} == {r['class_id'] for r in all_labels if r['task_admission']['usable']}
    (args.output/'samples.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    (args.output/'summary.json').write_text(json.dumps({'sampled_paths':len(records),'domains':len({r['domain'] for r in records}),'view_statuses':dict(Counter((r['view']+':'+r['status']) for r in records)),'pagination':pagination,'exports':exports,'independent_dag_checks':dag_checks,'seconds':time.perf_counter()-started,'boundary':'Stratified declared-source semantic paths; does not certify every scientific fact'},ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
