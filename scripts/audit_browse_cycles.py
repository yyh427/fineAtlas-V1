#!/usr/bin/env python3
"""Kahn-check the complete indexed hierarchy, including typed design/configuration links."""
from array import array
from collections import deque
import argparse
import json
from pathlib import Path
import sqlite3
import time


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--staging',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    c=sqlite3.connect(a.staging.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    c.execute('PRAGMA cache_size=-1000000');results={}
    size=c.execute('SELECT max(component_id)+1 FROM browse_nodes').fetchone()[0]
    views=[r[0] for r in c.execute('SELECT DISTINCT view FROM browse_links ORDER BY view')]
    for view in views:
        tick=time.monotonic();degree=array('I',[0])*size;offset=array('I',[0])*(size+1)
        seen=bytearray(size);children=array('I');position=0
        for parent,child in c.execute('''SELECT parent_component,child_component FROM browse_links
            WHERE view=? GROUP BY parent_component,child_component ORDER BY parent_component,child_component''',(view,)):
            while position<=parent:offset[position]=len(children);position+=1
            children.append(child);degree[child]+=1;seen[parent]=seen[child]=1
        while position<=size:offset[position]=len(children);position+=1
        queue=deque(i for i in range(size) if seen[i] and degree[i]==0)
        visited=0
        while queue:
            node=queue.popleft();visited+=1
            for k in range(offset[node],offset[node+1]):
                child=children[k];degree[child]-=1
                if degree[child]==0:queue.append(child)
        vertices=sum(seen);remaining=vertices-visited
        results[view]={'unique_arcs':len(children),'incident_identity_vertices':vertices,
                       'processed_vertices':visited,'cyclic_or_cycle_dependent_vertices':remaining,
                       'acyclic':remaining==0,'seconds':time.monotonic()-tick,
                       'default_preferred_graph_acyclic':remaining==0}
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(results,indent=2)+'\n')
        print(view,results[view],flush=True)
        del degree,offset,seen,children
    c.close()
    if not all(r['acyclic'] for r in results.values()):raise SystemExit('Indexed hierarchy contains cycles; see report')


if __name__=='__main__':main()
