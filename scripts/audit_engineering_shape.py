#!/usr/bin/env python3
"""Census actual generic parents, rather than using mixed-view maximum depth.

Source UIDs remain distinct; verified identity components are counted once.
Definition-based role suggestions are review candidates, not accuracy scores.
"""
import argparse
import collections
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.engineering_roles import ENGINEERING_DOMAINS,engineering_role_hint,definition_head
from fineatlas.semantics import role_expression
from fineatlas._text import norm

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--definitions',type=Path)
    p.add_argument('--refinements',type=Path,nargs='*',help='Preview retained-UID type/role/edge refinements without modifying the input database')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(a.database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    c.row_factory=sqlite3.Row;c.execute('PRAGMA temp_store=MEMORY');c.execute('PRAGMA cache_size=-500000')
    definitions=json.loads(a.definitions.read_text()) if a.definitions else {}
    reg=[dict(r) for r in c.execute('SELECT * FROM domain_registry ORDER BY canonical_name') if r['canonical_name'] in ENGINEERING_DOMAINS]
    node_cache={};component_cache={};children_cache={}
    proposed_roles={};proposed_visibility={};withdrawn=set();new_edges=collections.defaultdict(list);extra_active=collections.defaultdict(set)
    for path in a.refinements or []:
        for line in path.open():
            r=json.loads(line);op=r['op'];u=r['uid']
            if op=='role':proposed_roles[u]=r['role']
            elif op=='source_review':proposed_roles[u]='UNKNOWN';proposed_visibility[u]='SOURCE_ONLY'
            elif op=='activate_native_type':
                proposed_roles[u]='CLASS';proposed_visibility[u]='ACTIVE'
                comp=c.execute('SELECT component_id FROM nodes WHERE uid=?',(u,)).fetchone()[0];extra_active[comp].add(u)
                for parent in r['parents']:new_edges[parent].append({'id':None,'child_uid':u})
            elif op=='withdraw_edge':withdrawn.add(r['edge_id'])
            elif op=='link' and r['relation']=='IS_A':new_edges[r['parent']].append({'id':None,'child_uid':u})
            elif op in {'withdraw_typed','link'}:pass
            else:raise ValueError('The retained-UID preview does not support operation '+op)
    def node(u):
        if u not in node_cache:
            r=c.execute('SELECT n.*,p.attributes,'+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(u,)).fetchone()
            node_cache[u]=dict(r) if r else None
            if r:
                node_cache[u]['role']=proposed_roles.get(u,node_cache[u]['role'])
                node_cache[u]['visibility']=proposed_visibility.get(u,node_cache[u]['visibility'])
        return node_cache[u]
    def generic_members(comp):
        if comp not in component_cache:
            members={r[0] for r in c.execute("SELECT uid FROM nodes WHERE component_id=? AND visibility='ACTIVE'",(comp,))}|extra_active[comp]
            component_cache[comp]=sorted(u for u in members if admitted(u))
        return component_cache[comp]
    def admitted(u):
        n=node(u)
        allowed=json.loads(n.get('attributes') or '{}').get('allowed_views')
        return n['visibility']=='ACTIVE' and n['role']=='CLASS' and (allowed is None or 'strict' in allowed or u in extra_active[n['component_id']])
    def children(comp):
        if comp not in children_cache:
            found={}
            for u in generic_members(comp):
                edges=list(c.execute("SELECT id,child_uid FROM edges WHERE parent_uid=? AND relation='IS_A' AND status='ACTIVE'",(u,)))+new_edges[u]
                for e in edges:
                    if e['id'] in withdrawn:continue
                    n=node(e['child_uid'])
                    if admitted(n['uid']) and n['component_id']!=comp:
                        found.setdefault(n['component_id'],[]).append({'edge_id':e['id'],'child_uid':n['uid'],'parent_uid':u})
            children_cache[comp]=found
        return children_cache[comp]
    summaries=[];root_children={};wide=[];all_classes={};class_domains=collections.defaultdict(set)
    for d in reg:
        name=d['canonical_name'];roots={node(u)['component_id'] for u in json.loads(d['root_uids'])}
        depth={comp:0 for comp in roots};todo=collections.deque(sorted(roots))
        while todo:
            comp=todo.popleft()
            for child in children(comp):
                if child not in depth:depth[child]=depth[comp]+1;todo.append(child)
        layers=collections.Counter(depth.values());uid_layers=collections.Counter()
        for comp,level in depth.items():
            for u in generic_members(comp):
                all_classes[u]=node(u);class_domains[u].add(name);uid_layers[level]+=1
        groups={ch for comp in roots for ch in children(comp)}
        root_children[name]=[node(generic_members(comp)[0]) for comp in sorted(groups)]
        widths=collections.Counter(len(children(comp)) for comp in depth)
        summary={'domain':name,'strict_generic_identity_groups':len(depth),'strict_generic_source_uids':sum(uid_layers.values()),'layers_identity_groups':[layers[i] for i in range(max(layers,default=0)+1)],'layers_source_uids':[uid_layers[i] for i in range(max(layers,default=0)+1)],'root_direct_generic_groups':len(groups),'parents_with_over_100_generic_children':sum(n for w,n in widths.items() if w>100),'largest_generic_fanout':max(widths,default=0)}
        summaries.append(summary)
        for comp in sorted(depth,key=lambda v:(-len(children(v)),v))[:12]:
            u=generic_members(comp)[0]
            wide.append({'domain':name,'uid':u,'label':node(u)['label'],'component_id':comp,'depth':depth[comp],'direct_generic_child_groups':len(children(comp)),'source_witnesses':children(comp)})
        print(name,summary['layers_identity_groups'],'root',len(groups),flush=True)
    aliases=collections.defaultdict(set)
    for u,n in all_classes.items():
        if not u.startswith('wordnet31:'):continue
        names={r[0] for r in c.execute('SELECT alias FROM aliases WHERE uid=?',(u,))}
        for domain in class_domains[u]:aliases[domain].update(names)
    reviews=[]
    for u,n in all_classes.items():
        if u.startswith(('wordnet31:','hierarchy-type:')):continue
        raw=json.loads(n['data']);e=raw.get('evidence_record',{})
        desc=raw.get('wikidata_description') or e.get('wikidata_description') or raw.get('description') or n['description'] or ''
        rec=definitions.get('wikidata:'+u.split(':')[-1],{})
        available=[rec.get('intro',''),raw.get('definition') or raw.get('intro') or e.get('wikipedia_intro') or '']
        intro=max((s for s in available if s and definition_head(s,n['label'])),key=len,default='')
        domains=class_domains[u];domain=n['domain'] if n['domain'] in domains else next((d for d in ['ships','locomotives','tractors','cars','aircraft','smartphones'] if d in domains),sorted(domains)[0])
        hint,basis=engineering_role_hint(n['source'],n['rank'],domain,n['label'],desc,intro,generic_label=norm(n['label']) in aliases[domain])
        if hint:
            reviews.append({'uid':u,'label':n['label'],'canonical_role':n['role'],'suggested_role':hint,'basis':basis,'domains':sorted(domains),'description':desc,'definition':intro})
    for filename,obj in [('engineering_layers.json',summaries),('engineering_root_children.json',root_children),('engineering_widest_parents.json',wide),('engineering_grain_reviews.json',reviews)]:
        (a.output/filename).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    (a.output/'summary.json').write_text(json.dumps({'mode':'PROPOSED_FROM_FROZEN_REFINEMENTS' if a.refinements else 'ACTUAL_DATABASE','domains':len(reg),'generic_source_uids_examined':len(all_classes),'remaining_role_suggestions_for_review':len(reviews),'counting':'ACTIVE CLASS-only IS_A; verified source identity groups; no design terminals or navigation edges counted as generic layers'},indent=2)+'\n')
    print('COMPLETE',len(reg),'domains',len(all_classes),'generic UIDs; review candidates',len(reviews),flush=True)

if __name__=='__main__':main()
