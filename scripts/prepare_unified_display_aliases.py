#!/usr/bin/env python3
"""Freeze missing searchable aliases for existing names across all active nodes.

These are existing labels/names, not new inferred names or identity mappings.
The primary alias index and FTS are updated together by Migration.alias().
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas._text import norm


def prepare(database,output):
    c=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    c.create_function('display_alias_norm',1,lambda x:norm(x or ''),deterministic=True)
    c.execute('PRAGMA cache_size=-1000000')
    rows=c.execute("""SELECT n.uid,n.label,n.source,n.data FROM nodes n
        WHERE n.visibility='ACTIVE' AND n.label IS NOT NULL AND n.label<>''
        AND NOT EXISTS(SELECT 1 FROM aliases a WHERE a.uid=n.uid AND a.alias=display_alias_norm(n.label))
        UNION ALL SELECT n.uid,s.name,s.source,n.data FROM node_names s JOIN nodes n ON n.uid=s.uid
        WHERE n.visibility='ACTIVE' AND s.name<>''
        AND NOT EXISTS(SELECT 1 FROM aliases a WHERE a.uid=n.uid AND a.alias=display_alias_norm(s.name))""")
    output.parent.mkdir(parents=True,exist_ok=True);count=0
    with output.open('w') as f:
        for uid,name,source,data in rows:
            if not norm(name):continue
            f.write(json.dumps({'uid':uid,'name':name,'original_name_source':source,
                                'native_record_sha256':hashlib.sha256(data.encode()).hexdigest(),
                                'basis':'Existing retained node label/name lacks its exact normalized search alias; indexing only, no identity/role change'})+'\n');count+=1
    print(json.dumps({'existing_names_missing_alias':count}));c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();prepare(a.database,a.output)
