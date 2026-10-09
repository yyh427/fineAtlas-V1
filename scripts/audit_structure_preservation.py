#!/usr/bin/env python3
"""Hash every retained source row independently of graph and SDK predicates.

The copied SQLite row sequence is an efficient streaming preservation witness;
source UID/content fields are hashed explicitly. Component changes are expected
identity decisions and are audited separately, never asserted to be raw facts.
"""
from __future__ import annotations

if not __debug__:
    raise RuntimeError("Optimized Python is forbidden for mandatory structural checks")

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import time


def digest_rows(c,table,columns,max_rowid):
    h=hashlib.sha256();count=0;start=time.monotonic()
    sql='SELECT '+','.join('"'+x+'"' for x in columns)+' FROM "'+table+'" WHERE rowid<=? ORDER BY rowid'
    for row in c.execute(sql,(max_rowid,)):
        payload=json.dumps(list(row),ensure_ascii=False,separators=(',',':')).encode()
        h.update(len(payload).to_bytes(8,'big'));h.update(payload);count+=1
        if count%1000000==0:print(table,count,round(time.monotonic()-start,1),flush=True)
    return {'sha256':h.hexdigest(),'rows':count,'seconds':time.monotonic()-start}


def run(baseline,candidate,output,reference=None):
    output.parent.mkdir(parents=True,exist_ok=True)
    base=sqlite3.connect(baseline.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    c=sqlite3.connect(candidate.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) if candidate else None
    tables=[r[0] for r in base.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('nodes','evidence','source_nodes','source_edges','source_bridges','source_entity_relations')")]
    saved=json.loads(reference.read_text()) if reference else None
    results={}
    for table in tables:
        columns=[r[1] for r in base.execute('PRAGMA table_info("'+table+'")') if not (table=='nodes' and r[1]=='component_id')]
        max_rowid=base.execute('SELECT max(rowid) FROM "'+table+'"').fetchone()[0]
        frozen=saved.get('tables',{}).get(table) if saved else None
        if frozen and (frozen['columns']!=columns or frozen['max_baseline_rowid']!=max_rowid):
            raise ValueError('Original source reference schema/row bound changed: '+table)
        left=frozen['baseline'] if frozen else digest_rows(base,table,columns,max_rowid)
        right=digest_rows(c,table,columns,max_rowid) if c else None
        results[table]={'columns':columns,'max_baseline_rowid':max_rowid,'baseline':left,'candidate':right,
                        'pass':right is None or (left['sha256']==right['sha256'] and left['rows']==right['rows'])}
        result={'baseline':str(baseline),'candidate':str(candidate) if candidate else None,'tables':results,'pass':all(x['pass'] for x in results.values())}
        output.write_text(json.dumps(result,indent=2)+'\n')
        print('TABLE',table,results[table]['pass'],flush=True)
    if not result['pass']:raise ValueError('Original source content changed or disappeared')
    base.close()
    if c:c.close()
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--reference',type=Path)
    a=p.parse_args();run(a.baseline,a.candidate,a.output,a.reference)
