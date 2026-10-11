"""Portable independently read parent assertion states, without source document text."""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

from _download import digest

SCHEMA='FINEATLAS_PORTABLE_PARENT_ASSERTION_STATES_V1'


def row_sha(row):
    return hashlib.sha256(json.dumps(dict(row),sort_keys=True).encode()).hexdigest()


def write_parent_snapshot(config, output, accepted):
    inputs=Path(config['inputs']);receipt_path=Path(config.get('lineage_primary_build',config['primary_build']))
    complete=json.loads(receipt_path.read_text());lineage_path=receipt_path.parent/'parent_lineage.json'
    lineage=json.loads(lineage_path.read_text());parent=Path(lineage['parent_database']).resolve()
    reference=json.loads((inputs/'structure_regression_temporal_parent_reference.json').read_text())
    if (complete.get('pass')is not True or complete.get('complete')is not True
            or complete.get('parent_lineage_sha256')!=digest(lineage_path)
            or reference.get('parent_revision')!=lineage['parent_revision']
            or reference.get('completed_parent_build_sha256')!=lineage['parent_receipt_sha256']
            or reference['completed_parent_build'].get('pass')is not True
            or reference['completed_parent_build'].get('complete')is not True):
        raise ValueError('Portable parent census requires the real completed child and frozen exact parent receipt')
    if any(Path(str(parent)+suffix).exists()for suffix in('-wal','-shm','-journal')):
        raise ValueError('Parent assertion snapshot must read a closed immutable database')
    stat=parent.stat();before_stamp=[stat.st_size,stat.st_mtime_ns,stat.st_ino]
    source_path=inputs/'structure_source_contracts.json.gz'
    payload=json.loads(gzip.decompress(source_path.read_bytes()))
    header={'schema':SCHEMA,'pass':False,'candidate_revision':accepted['database_revision'],
        'parent_revision':lineage['parent_revision'],'parent_database_sha256':lineage['parent_database_sha256'],
        'parent_receipt_sha256':lineage['parent_receipt_sha256'],
        'actual_child_build_receipt_sha256':digest(receipt_path),'actual_child_lineage_sha256':digest(lineage_path),
        'frozen_temporal_parent_reference_sha256':digest(inputs/'structure_regression_temporal_parent_reference.json'),
        'quarantine_manifest_sha256':digest(source_path),
        'generator_sha256':digest(Path(__file__)),'canonical_assertions':len(payload['quarantines']),
        'scope':'Completed parent SQL full-row hashes and exact historical statuses/reasons; derived validation evidence, not primary semantic proof'}
    if header['canonical_assertions']!=81579:raise ValueError('Incomplete original quarantine census')
    result=[]
    with sqlite3.connect(parent.as_uri()+'?mode=ro&immutable=1',uri=True)as con:
        con.row_factory=sqlite3.Row;con.execute('PRAGMA query_only=ON');con.execute('PRAGMA cache_size=-65536')
        rev=json.loads(con.execute('SELECT value FROM metadata WHERE key="database_revision"').fetchone()[0])
        if rev!=lineage['parent_revision']:raise ValueError('Actual SQL parent revision differs from completed lineage')
        for item in payload['quarantines']:
            table=item['table'];locator=item['locator'];original=item['original_source_assertion']
            if table not in('edges','entity_relations'):raise ValueError('Invalid original source table')
            keys=[key for key in('child_uid','parent_uid','subject_uid','object_uid','relation','source','layer')if key in locator]
            rows=con.execute('SELECT * FROM '+table+' WHERE '+' AND '.join(key+'=?'for key in keys),[locator[key]for key in keys]).fetchall()
            content={k:v for k,v in original.items()if k not in('id','status','reason')}
            rows=[row for row in rows if {k:v for k,v in dict(row).items()if k not in('id','status','reason')}==content]
            if len(rows)!=locator.get('source_assertion_multiplicity',1):raise ValueError('Parent source assertion multiplicity changed')
            canonical=[r for r in rows if r['id']==original['id']]
            if len(canonical)!=1 or canonical[0]['status']!='SOURCE_SCOPE_REVIEW':raise ValueError('Exact canonical parent quarantine missing')
            result.append({'table':table,'canonical_id':original['id'],'locator':locator,
                'rows':[{'id':r['id'],'status':r['status'],'reason':dict(r).get('reason'),'row_sha256':row_sha(r)}for r in sorted(rows,key=lambda r:r['id'])]})
    stat=parent.stat()
    if [stat.st_size,stat.st_mtime_ns,stat.st_ino]!=before_stamp:raise ValueError('Parent changed during independent census')
    header.update(pass_=True);header['pass']=header.pop('pass_');header['source_assertion_rows']=sum(len(r['rows'])for r in result)
    with Path(output).open('xb')as destination:
        with gzip.GzipFile(fileobj=destination,mode='wb',mtime=0)as stream:
            stream.write((json.dumps(header,sort_keys=True)+'\n').encode())
            for row in result:stream.write((json.dumps(row,sort_keys=True)+'\n').encode())
    return header
