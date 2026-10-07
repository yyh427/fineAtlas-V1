#!/usr/bin/env python3
"""Attach a checked staging artifact to an independent source-preserving candidate."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--staging',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.database.samefile(a.baseline) or a.database.samefile(a.staging):raise ValueError('Candidate must be independent')
    c=sqlite3.connect(a.database)
    c.execute('PRAGMA cache_size=-500000');c.execute('PRAGMA busy_timeout=30000')
    c.execute('ATTACH DATABASE ? AS staged',(a.staging.resolve().as_uri()+'?mode=ro&immutable=1',))
    meta={r[0]:json.loads(r[1]) for r in c.execute('SELECT key,value FROM staged.metadata')}
    assert meta['schema']=='FINEATLAS_BROWSE_INDEX_V1' and meta['browse_indexes_ready']
    candidate_meta={r[0]:json.loads(r[1]) for r in c.execute('SELECT key,value FROM metadata')}
    expected=candidate_meta.get('browse_parent_revision',candidate_meta['database_revision'])
    assert expected==meta['browse_source_revision'],(expected,meta['browse_source_revision'])
    tables=[r[0] for r in c.execute("SELECT name FROM staged.sqlite_master WHERE type='table' AND name LIKE 'browse_%' ORDER BY name")]
    c.execute('BEGIN IMMEDIATE')
    c.execute("INSERT OR REPLACE INTO metadata VALUES('browse_indexes_ready','false')")
    for table in tables:
        assert table.replace('_','').isalnum()
        c.execute('DROP TABLE IF EXISTS '+table)
        sql=c.execute('SELECT sql FROM staged.sqlite_master WHERE type="table" AND name=?',(table,)).fetchone()[0]
        c.execute(sql)
        c.execute('INSERT INTO '+table+' SELECT * FROM staged.'+table)
        print('APPLIED',table,flush=True)
    for name,sql in c.execute("SELECT name,sql FROM staged.sqlite_master WHERE type='index' AND sql IS NOT NULL AND tbl_name LIKE 'browse_%'").fetchall():
        c.execute(sql)
    for key,value in meta.items():
        if key.startswith('browse_') or key in ('release','database_revision'):
            c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(key,json.dumps(value)))
    c.commit();c.execute('PRAGMA analysis_limit=1000');c.execute('ANALYZE');c.commit()
    result={'database':str(a.database),'staging':str(a.staging),'tables':tables,'source_revision':expected,'revision':meta['database_revision'],'source_graph_mutated':False,'complete':True}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');c.close()
    print('CANDIDATE BROWSE INDEX APPLICATION COMPLETE',flush=True)

if __name__=='__main__':main()
