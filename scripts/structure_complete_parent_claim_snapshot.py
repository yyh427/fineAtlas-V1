"""Portable independently read parent assertion states, without source document text."""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

from _download import digest
from portable_complete_structure_lineage import require_complete_type_build, require_source_parent_binding

SCHEMA='FINEATLAS_PORTABLE_PARENT_ASSERTION_STATES_V1'


def row_sha(row):
    return hashlib.sha256(json.dumps(dict(row),sort_keys=True).encode()).hexdigest()


def write_parent_snapshot(config, output, accepted):
    inputs=Path(config['inputs']);receipt_path=Path(config['primary_build'])
    complete=require_complete_type_build(receipt_path);lineage_path=receipt_path.parent/'parent_lineage.json'
    lineage=json.loads(lineage_path.read_text());parent=Path(lineage['parent_database']).resolve()
    reference=json.loads((inputs/'structure_regression_temporal_parent_reference.json').read_text())
    _, integrity = require_source_parent_binding(config, 'primary', receipt_path, complete)
    if (reference.get('parent_revision') == lineage['parent_revision']
            or complete['revision'] != accepted['database_revision']):
        raise ValueError('A historical four-delta temporal parent cannot replace the actual closed owned-scope parent')
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
        'actual_parent_integrity_sha256':lineage['parent_integrity_sha256'],
        'historical_temporal_reference_is_current_parent':False,
        'parent_binding_basis':'Actual complete six-stage child lineage and independently verified complete eight-stage source parent; historical temporal reference remains unchanged proof of its earlier stage',
        'generator_sha256':digest(Path(__file__)),'canonical_assertions':len(payload['quarantines']),
        'scope':'Completed parent SQL full-row hashes and exact historical statuses/reasons; derived validation evidence, not primary semantic proof'}
    if header['canonical_assertions']!=81579:raise ValueError('Incomplete original quarantine census')
    if len({(item['table'],item['original_source_assertion']['id'])for item in payload['quarantines']})!=81579:
        raise ValueError('Canonical original source assertions must be unique')
    result=[]
    with sqlite3.connect(parent.as_uri()+'?mode=ro&immutable=1',uri=True)as con:
        con.row_factory=sqlite3.Row;con.execute('PRAGMA query_only=ON');con.execute('PRAGMA cache_size=-65536')
        rev=json.loads(con.execute('SELECT value FROM metadata WHERE key="database_revision"').fetchone()[0])
        if rev!=lineage['parent_revision']:raise ValueError('Actual SQL parent revision differs from completed lineage')
        frozen=json.loads(con.execute("SELECT value FROM metadata WHERE key='structure_frozen_build_manifest'").fetchone()[0])
        parent_frozen=json.loads((Path(config['primary_parent_build']).parent/'frozen_metadata.json').read_text())
        if frozen!=parent_frozen['manifest']:raise ValueError('Actual c933 parent frozen inventory changed')
        if frozen['inputs'].get(source_path.name)!=digest(source_path):raise ValueError('81579 original source contract differs from actual completed parent freeze')
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


def compare_current_parent_assertion_rows(con, snapshots, inputs):
    """Compare raw source rows to c933; permit only exact frozen later status history.

    Roles/profiles are adjudications checked by the complete-type independent auditor.
    They never normalize or replace raw source assertions in this comparison.
    """
    inputs=Path(inputs);meta={key:json.loads(value)for key,value in con.execute('SELECT key,value FROM metadata')}
    manifest_path=inputs/'structure_complete_owned_type_repairs.json';manifest=json.loads(manifest_path.read_text())
    operation_path=inputs/manifest['operations_file'];freeze=meta['structure_frozen_build_manifest']['inputs']
    if digest(manifest_path)!=freeze.get(manifest_path.name)or digest(operation_path)!=manifest['operations_sha256']or digest(operation_path)!=freeze.get(operation_path.name):
        raise ValueError('Later source status permissions require actual frozen complete-type operations')
    operations=[json.loads(line)for line in operation_path.read_text().splitlines()if line]
    permissions={}
    for op in operations:
        if op.get('op')not in('review_typed_relation','review_class_edge'):continue
        table='entity_relations'if op['op']=='review_typed_relation'else'edges';before=op['before_assertion']
        content={k:v for k,v in before.items()if k not in('id','status','reason')}
        if hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest()!=op['content_sha256']or op['after_status']!='SOURCE_SCOPE_REVIEW':
            raise ValueError('Later source review does not bind exact original content and scope-review status')
        after={**before,'status':op['after_status']};current=con.execute('SELECT * FROM '+table+' WHERE id=?',(before['id'],)).fetchone()
        if not current or dict(current)!=after:raise ValueError('Later type-role source review modified producer/data/provenance')
        kind='typed_scope_review'if table=='entity_relations'else'class_scope_review'
        histories=con.execute('SELECT before_json,after_json,evidence FROM usability_changes WHERE stage="complete_owned_type_repairs"AND object_type=?AND object_id=?',(kind,str(before['id']))).fetchall()
        if sum(json.loads(h['before_json'])==before and json.loads(h['after_json'])=={'status':op['after_status']}and json.loads(h['evidence'])==op['proof']for h in histories)!=1:
            raise ValueError('Later source type-role withdrawal lacks its unique exact source/evidence history')
        key=(table,before['id'])
        if key in permissions:raise ValueError('Duplicate later source assertion permission')
        permissions[key]=(before,after)
    source_path=inputs/'structure_source_contracts.json.gz'
    if digest(source_path)!=freeze.get(source_path.name):raise ValueError('Original whole-source contract input changed')
    source_payload=json.loads(gzip.decompress(source_path.read_bytes()))
    originals={(r['table'],r['original_source_assertion']['id']):r['original_source_assertion']for r in source_payload['quarantines']}
    checked=0;used=set()
    for snapshot in snapshots:
        table=snapshot['table'];locator=snapshot['locator'];keys=[k for k in('child_uid','parent_uid','subject_uid','object_uid','relation','source','layer')if k in locator]
        candidates=con.execute('SELECT * FROM '+table+' WHERE '+'AND '.join(k+'=?'for k in keys),[locator[k]for k in keys]).fetchall()
        original=originals[(table,snapshot['canonical_id'])];content={k:v for k,v in original.items()if k not in('id','status','reason')}
        by_id={r['id']:dict(r)for r in candidates if {k:v for k,v in dict(r).items()if k not in('id','status','reason')}==content};expected={r['id']:r for r in snapshot['rows']}
        # IDs plus full-row hashes preserve every historical sibling and exact multiplicity.
        matching=by_id
        if set(matching)!=set(expected):raise ValueError('Original c933 source sibling row deleted or replaced')
        for rid,row in matching.items():
            prior=expected[rid]
            if row_sha(row)!=prior['row_sha256']:
                permission=permissions.get((table,rid))
                if not permission or row_sha(permission[0])!=prior['row_sha256']or permission[1]!=row:
                    raise ValueError('Unexplained raw source status/content changed after c933')
                used.add((table,rid))
            elif row['status']!=prior['status']or row.get('reason')!=prior['reason']:
                raise ValueError('Historical source status/reason differs from its complete raw-row digest')
            checked+=1
    return {'pass':True,'canonical_assertions':len(snapshots),'historical_source_rows_checked':checked,
        'exact_later_source_status_permissions_used':len(used),'role_profile_normalization_applied_to_source_rows':False,
        'scope':'Current raw claims compared to exact c933 parent hashes; only individually frozen later source reviews with original full-row/history may change status. Roles never rewrite source producer data.'}
