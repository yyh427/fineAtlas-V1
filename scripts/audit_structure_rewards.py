#!/usr/bin/env python3
"""Frozen 755-label/56,917-pair matrix and independent SQL graph witnesses."""
from __future__ import annotations
import argparse
from collections import Counter, deque
import csv
import itertools
import json
from pathlib import Path
import sqlite3
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fineatlas import FineAtlas

DATASETS={'cub200':200,'fgvc_aircraft':100,'flowers102':102,'pets37':37,'stanford_dogs':120,'stanford_cars':196}
RELATIONS={'classification':{'IS_A','TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT'},
           'design':{'IS_A','TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT','DESIGN_TYPE_OF','NATIVE_DESIGN_PARENT','SERIES_MEMBER_OF'},
           'configuration':{'IS_A','TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT','DESIGN_TYPE_OF','NATIVE_DESIGN_PARENT','SERIES_MEMBER_OF','CONFIGURATION_OF'},
           'annotation':{'DEPICTS_TYPE','IS_A','TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT'}}
ROLES={'classification':{'CLASS','BIOLOGICAL_VARIANT'},'design':{'CLASS','MODEL','MODEL_FAMILY'},
       'configuration':{'CLASS','MODEL','MODEL_FAMILY','CONFIGURATION'},'annotation':{'DATASET_CATEGORY','CLASS','BIOLOGICAL_VARIANT'}}


class IndependentGraph:
    """Read admitted source arcs via browse index; no reward implementation calls."""
    def __init__(self,c,policy,scope,boundaries):
        self.c,self.policy,self.scope=c,policy,scope
        self.boundaries={self.node(u)['component_id'] for u in boundaries}
        self.nodes,self.parents={},{}
    def node(self,uid):
        row=self.c.execute('SELECT n.uid,n.component_id,n.source,n.rank,b.role,n.visibility FROM nodes n JOIN browse_nodes b ON b.uid=n.uid WHERE n.uid=?',(uid,)).fetchone()
        return dict(row) if row else None
    def component(self,comp):
        if comp not in self.nodes:
            self.nodes[comp]=[dict(r) for r in self.c.execute('SELECT n.uid,n.source,n.rank,b.role FROM nodes n JOIN browse_nodes b ON b.uid=n.uid WHERE n.component_id=?',(comp,))]
        return self.nodes[comp]
    def next(self,comp):
        if comp in self.parents:return self.parents[comp]
        roles={r['role'] for r in self.component(comp)}
        if len(roles)!=1:
            self.parents[comp]=set();return set()
        result=set()
        sql = """SELECT e.child_uid child,e.parent_uid parent,e.relation,e.data FROM nodes n JOIN edges e ON e.child_uid=n.uid
            WHERE n.component_id=? AND (e.status='ACTIVE' AND e.relation='IS_A' OR e.status='BACKBONE_ACTIVE' AND e.relation='IS_A' OR e.status='TYPED_ACTIVE' AND e.relation IN ('TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT'))
            UNION ALL SELECT e.subject_uid,e.object_uid,e.relation,e.data FROM nodes n JOIN entity_relations e ON e.subject_uid=n.uid WHERE n.component_id=? AND e.status='ACTIVE'"""
        for r in self.c.execute(sql,(comp,comp)):
            if r['relation'] not in RELATIONS[self.policy]:continue
            a,b=self.node(r['child']),self.node(r['parent'])
            if not a or not b or a['visibility']!='ACTIVE' or b['visibility']!='ACTIVE':continue
            if a['role'] not in ROLES[self.policy] or b['role'] not in ROLES[self.policy]:continue
            if a['component_id']==b['component_id']:continue
            if len({x['role'] for x in self.component(b['component_id'])})!=1:continue
            denied=False
            for uid in (a['uid'],b['uid']):
                profile=self.c.execute('SELECT attributes FROM node_profiles WHERE uid=?',(uid,)).fetchone()
                allowed=json.loads(profile[0]).get('allowed_views') if profile else None
                if isinstance(allowed,list) and 'taxonomy' not in allowed:denied=True
            if denied:continue
            if self.scope and (a['source']!=self.scope or (b['source']!=self.scope and b['component_id'] not in self.boundaries)):continue
            data=json.loads(r['data'])
            basis=data.get('admission_basis',{})
            if isinstance(basis,dict) and basis.get('placement_uncertain'):continue
            result.add(b['component_id'])
        self.parents[comp]=result
        return result
    def closure(self,uid):
        own=self.node(uid)
        if not own:return {}
        start=own['component_id'];dist={start:0};queue=deque([start])
        while queue:
            current=queue.popleft()
            for parent in self.next(current):
                if parent not in dist:dist[parent]=dist[current]+1;queue.append(parent)
        reverse={}
        for node in dist:
            for parent in self.next(node):
                reverse.setdefault(parent,set()).add(node)
        valid=set(self.boundaries & dist.keys());queue=deque(valid)
        while queue:
            for child in reverse.get(queue.popleft(),()):
                if child not in valid:valid.add(child);queue.append(child)
        if start not in valid:return {}
        # Full graph is independently Kahn-checked; cycles are not inferred from root reachability.
        return {k:v for k,v in dist.items() if k in valid}
    def validate_path(self,path):
        arcs=0
        for step in path:
            edge=step.get('edge',{})
            relation=edge.get('relation')
            if relation=='SAME_CONCEPT':
                a=self.node(step['uid']);b=self.node(step['parent_uid'])
                assert a and b and a['component_id']==b['component_id'],step
                continue
            assert relation in RELATIONS[self.policy],step
            child=edge.get('child_uid') or edge.get('subject_uid')
            parent=edge.get('parent_uid') or edge.get('object_uid')
            row=self.c.execute("SELECT 1 FROM edges WHERE child_uid=? AND parent_uid=? AND relation=? AND status IN ('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE') UNION ALL SELECT 1 FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND status='ACTIVE' LIMIT 1",(child,parent,relation,child,parent,relation)).fetchone()
            assert row,(child,parent,relation)
            assert self.node(parent)['component_id'] in self.next(self.node(child)['component_id']),step
            arcs+=1
        return arcs


def run(database,inputs,out,baseline=False):
    out.mkdir(parents=True,exist_ok=True)
    old=json.loads((inputs/'legacy_policies.json').read_text());new=json.loads((inputs/'reviewed_policies.json').read_text())
    modes=[('legacy','legacy',old,'world'),('reviewed_old_floors','reviewed_paths',old,'world'),('reviewed_new_floors','reviewed_paths',new,'world')]
    if not baseline:modes.append(('source_native','reviewed_paths',new,'source_native'))
    summary={}
    with FineAtlas(database,relation_view='unified') as tree:
        for name,mode,configs,target_scope in modes:
            totals={};started=time.monotonic()
            with (out/(name+'-pairs.csv')).open('w') as stream:
                writer=csv.writer(stream);writer.writerow(['dataset','left','right','status','resolution','distance','lca_uids','lca_ranks'])
                for ds,expected in DATASETS.items():
                    config=configs[ds]
                    if target_scope=='source_native':
                        if 'source_native' not in config:continue
                        config=config['source_native']
                    options={k:v for k,v in config.items() if k in {'policy','requirement','source_scope','coarse_roots'}}
                    boundary=new[ds]['task_boundary_roots']
                    index=tree.relation_reward_index(ds,admission_mode=mode,target_scope=target_scope,
                            task_boundary_roots=boundary if mode=='reviewed_paths' else (),**options)
                    assert len(index.labels)==expected,(ds,len(index.labels))
                    graph=IndependentGraph(tree.con,index.policy,index.source_scope,boundary) if mode=='reviewed_paths' else None
                    labels=[];closures={};counts=Counter();lca_ranks=Counter();lca_labels=Counter();rank_by_identity={}
                    for cid,checked in index.labels.items():
                        target=tree.target(ds,cid,target_scope=target_scope,source_namespace=index.source_namespace,source_version=index.source_version)
                        uid=checked['uid'];path=tree.task_path(ds,cid,index=index)
                        counts['labels']+=1;counts['endpoint_applicable']+=checked['reason'] is None
                        counts['identity_scope_confirmed']+=checked['identity_verified']
                        counts['world_identity_confirmed']+=checked['world_identity_verified']
                        counts['navigation_root_reachable']+=bool(tree.connection_status(uid).get('root_reachable')) if uid else 0
                        counts['task_path_valid']+=path.get('task_path_valid',False)
                        if graph and checked['reason'] is None:
                            closure=graph.closure(uid);assert closure,(ds,cid,'independent boundary route missing')
                            closures[cid]=closure
                            arcs=graph.validate_path(path['path']);assert arcs==path['classification_arc_count'],(ds,cid)
                        labels.append({'class_id':cid,'label':checked['label'],'checked':dict(checked),'path':path,'target':target})
                    for pair in index.pairs():
                        counts['pairs']+=1;counts[pair['status']]+=1
                        resolution=pair.get('resolution') or {'APPLICABLE':'FINE_VALID','COARSE_COMMON_ANCESTOR_ONLY':'COARSE_VALID'}.get(pair['status'],'UNCERTAIN')
                        counts['resolution_'+resolution]+=1
                        if not pair['applicable']:assert pair['distance'] is None,pair
                        else:assert isinstance(pair['distance'],int) and pair['distance']>=0,pair
                        lcas=pair.get('lcas',[])
                        for lca in lcas:
                            rank_by_identity.setdefault(lca['component_id'], sorted({r[0] for r in tree.con.execute('SELECT rank FROM nodes WHERE component_id=?',(lca['component_id'],))}))
                            rank='|'.join(rank_by_identity[lca['component_id']]);lca_ranks[rank]+=1;lca_labels[lca['uid']]+=1
                        if graph and pair['left'] in closures and pair['right'] in closures:
                            aa,bb=closures[pair['left']],closures[pair['right']];common=aa.keys() & bb.keys()
                            higher=set().union(*(graph.next(x)&common for x in common)) if common else set()
                            lowest=common-higher
                            assert {x['component_id'] for x in lcas}==lowest,(ds,pair['left'],pair['right'],'independent LCA mismatch')
                            if pair['applicable']:
                                # Verify each exported path from real source statements, with identity cost zero.
                                for selected in pair['selected_paths']:
                                    lc=selected['component_id'];la=graph.validate_path(selected['left']['path']);lb=graph.validate_path(selected['right']['path'])
                                    assert (la,lb)==(aa[lc],bb[lc]),(ds,selected)
                                distance=min(aa[x['component_id']]+bb[x['component_id']] for x in lcas if x['component_id'] in {s['component_id'] for s in pair['selected_paths']})
                                assert pair['distance']==distance,(ds,pair)
                        writer.writerow([ds,pair['left'],pair['right'],pair['status'],resolution,pair['distance'],json.dumps([x['uid'] for x in lcas]),json.dumps([rank_by_identity[x['component_id']] for x in lcas])])
                    assert counts['pairs']==expected*(expected-1)//2
                    (out/(name+'-'+ds+'-labels.json')).write_text(json.dumps(labels,ensure_ascii=False,indent=2)+'\n')
                    totals[ds]={'counts':dict(counts),'lca_rank_distribution':dict(lca_ranks),'lca_uid_distribution':dict(lca_labels)}
                    print(name,ds,dict(counts),flush=True)
            summary[name]={'datasets':totals,'seconds':time.monotonic()-started}
            (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('database','inputs','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--baseline',action='store_true')
    a=p.parse_args();run(a.database,a.inputs,a.output,a.baseline)
