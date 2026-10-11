"""Keep c933, completed Source8, and nominal child claim states as distinct evidence."""
from __future__ import annotations
import gzip
import json
import re
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from _download import digest
from portable_nominal_structure_lineage import (require_nominal_scope_build,
    require_source_parent_binding, source8_config, source8_accepted_record)
from structure_complete_parent_claim_snapshot import (
    write_parent_snapshot as write_c933_snapshot, row_sha,
    compare_current_parent_assertion_rows as compare_c933_current)
from structure_complete_regression_support import verify_complete_parent_snapshot

SCHEMA='FINEATLAS_PORTABLE_NOMINAL_DIRECT_PARENT_ASSERTION_STATES_V1'


def read_snapshot(path):
    with gzip.open(path,'rt')as source:
        header=json.loads(next(source));rows=[json.loads(line)for line in source if line]
    return header,rows


def source_rows(con,item,original):
    table=item['table'];locator=item['locator']
    if table not in ('edges','entity_relations'):raise ValueError('Unexpected source claim table')
    keys=[key for key in ('child_uid','parent_uid','subject_uid','object_uid','relation','source','layer')if key in locator]
    content={key:value for key,value in original.items()if key not in ('id','status','reason')}
    candidates=con.execute('SELECT *FROM '+table+' WHERE '+' AND '.join(key+'=?'for key in keys),[locator[key]for key in keys])
    return [dict(row)for row in candidates if {key:value for key,value in dict(row).items()if key not in ('id','status','reason')}==content]


def write_parent_snapshot(config,output,accepted):
    """Produce original c933 evidence, then independently inspect the direct Source8 parent."""
    output=Path(output);foundation=output.parent/'source8-foundation'
    historical_path=foundation/'parent-assertion-states.jsonl.gz'
    historic=write_c933_snapshot(source8_config(config),historical_path,source8_accepted_record(config))
    foundation_registry={'database_revision':historic['candidate_revision'],
        'parent_assertion_snapshot_sha256':digest(historical_path),'parent_assertion_snapshot_binding':historic}
    (foundation/'foundation-claims-registry.json').write_text(json.dumps(foundation_registry,indent=2)+'\n')
    _,snapshots=read_snapshot(historical_path)
    receipt=Path(config['primary_build']);child=require_nominal_scope_build(receipt)
    parent,seal=require_source_parent_binding(config,'primary',receipt,child)
    database=Path(parent['database']).resolve();stat=database.stat();stamp=(stat.st_size,stat.st_mtime_ns,stat.st_ino)
    originals=json.loads(gzip.decompress((Path(config['inputs'])/'structure_source_contracts.json.gz').read_bytes()))
    originals={(row['table'],row['original_source_assertion']['id']):row['original_source_assertion']for row in originals['quarantines']}
    current=[]
    with sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)as con:
        con.row_factory=sqlite3.Row;con.execute('PRAGMA query_only=ON')
        transition=compare_c933_current(con,snapshots,config['inputs'])
        for snapshot in snapshots:
            rows=source_rows(con,snapshot,originals[(snapshot['table'],snapshot['canonical_id'])])
            if {row['id']for row in rows}!={row['id']for row in snapshot['rows']}:
                raise ValueError('Direct Source8 parent lost original source multiplicity')
            current.append({**snapshot,'rows':[{'id':row['id'],'status':row['status'],'reason':row.get('reason'),'row_sha256':row_sha(row)}for row in sorted(rows,key=lambda row:row['id'])]})
    stat=database.stat()
    if (stat.st_size,stat.st_mtime_ns,stat.st_ino)!=stamp:raise ValueError('Direct Source8 parent changed during independent raw claim census')
    lineage=json.loads(receipt.with_name('parent_lineage.json').read_text())
    header={'schema':SCHEMA,'pass':True,'candidate_revision':accepted['database_revision'],
        'parent_revision':parent['revision'],'parent_database_sha256':seal['sha256'],
        'parent_receipt_sha256':digest(config['primary_parent_build']),
        'actual_child_build_receipt_sha256':digest(receipt),'actual_child_lineage_sha256':digest(receipt.with_name('parent_lineage.json')),
        'actual_parent_integrity_sha256':lineage['parent_integrity_sha256'],
        'grandparent_revision':historic['parent_revision'],'grandparent_database_sha256':historic['parent_database_sha256'],
        'c933_foundation_snapshot_sha256':digest(historical_path),'c933_foundation_header':historic,
        'source8_exact_transition_comparison':transition,'canonical_assertions':len(current),
        'source_assertion_rows':sum(len(row['rows'])for row in current),
        'quarantine_manifest_sha256':digest(Path(config['inputs'])/'structure_source_contracts.json.gz'),
        'scope':'Distinct c933 eight-stage historical foundation, actual Source8 six-stage immediate parent, and nominal six-stage current child. Only exact frozen Source8 status/history transitions are allowed; no scientific certification is inferred.',
        'generator_sha256':digest(__file__)}
    if len(current)!=81579 or len({(row['table'],row['canonical_id'])for row in current})!=81579:
        raise ValueError('Complete81579 unique direct parent source claims required')
    with output.open('xb')as destination:
        with gzip.GzipFile(fileobj=destination,mode='wb',mtime=0)as stream:
            stream.write((json.dumps(header,sort_keys=True)+'\n').encode())
            for row in current:stream.write((json.dumps(row,sort_keys=True)+'\n').encode())
    return header


def verify_nominal_parent_snapshot(support):
    direct=support.root/'parent-assertion-states.jsonl.gz';header,rows=read_snapshot(direct)
    foundation=support.root/'source8-foundation'
    registry=json.loads((foundation/'foundation-claims-registry.json').read_text())
    historic,old_rows=verify_complete_parent_snapshot(SimpleNamespace(root=foundation,value=registry))
    child_path=support.root/'builds/primary/build_complete.json';child=require_nominal_scope_build(child_path)
    lineage_path=child_path.with_name('parent_lineage.json');lineage=json.loads(lineage_path.read_text())
    if (digest(direct)!=support.value['parent_assertion_snapshot_sha256']or header!=support.value['parent_assertion_snapshot_binding']
            or header.get('schema')!=SCHEMA or header.get('pass')is not True
            or header.get('candidate_revision')!=support.value['database_revision']
            or child['revision']!=support.value['database_revision']or header.get('parent_revision')!=lineage['parent_revision']
            or header.get('parent_database_sha256')!=lineage['parent_database_sha256']
            or header.get('parent_receipt_sha256')!=lineage['parent_receipt_sha256']
            or header.get('actual_parent_integrity_sha256')!=lineage['parent_integrity_sha256']
            or header.get('actual_child_build_receipt_sha256')!=digest(child_path)
            or header.get('actual_child_lineage_sha256')!=digest(lineage_path)
            or header.get('c933_foundation_snapshot_sha256')!=digest(foundation/'parent-assertion-states.jsonl.gz')
            or header.get('c933_foundation_header')!=historic or header.get('grandparent_revision')!=historic['parent_revision']
            or header.get('grandparent_database_sha256')!=historic['parent_database_sha256']
            or historic['candidate_revision']!=header['parent_revision']
            or header.get('source8_exact_transition_comparison',{}).get('pass')is not True
            or header.get('source8_exact_transition_comparison',{}).get('canonical_assertions')!=81579
            or header.get('source8_exact_transition_comparison',{}).get('historical_source_rows_checked')!=header.get('source_assertion_rows')
            or not isinstance(header.get('quarantine_manifest_sha256'),str)or not re.fullmatch('[a-f0-9]{64}',header['quarantine_manifest_sha256'])
            or header.get('quarantine_manifest_sha256')!=historic['quarantine_manifest_sha256']
            or header.get('quarantine_manifest_sha256')!=json.loads((support.root/'builds/primary/source-parent/started_fingerprints.json').read_text())['inputs'].get('structure_source_contracts.json.gz')):
        raise ValueError('Three-generation exact source snapshot binding required')
    if len(rows)!=81579 or len({(r['table'],r['canonical_id'])for r in rows})!=81579:
        raise ValueError('All81579 direct source parent claims are required')
    old={(row['table'],row['canonical_id']):row for row in old_rows}
    for row in rows:
        prior=old.get((row['table'],row['canonical_id']))
        if (not prior or row['locator']!=prior['locator']or len(row['rows'])!=len(prior['rows'])
                or len({r['id']for r in row['rows']})!=len(row['rows'])
                or {r['id']for r in row['rows']}!={r['id']for r in prior['rows']}):
            raise ValueError('Source8 direct snapshot cannot replace original c933 claim provenance or multiplicity')
        canonical=[r for r in row['rows']if r['id']==row['canonical_id']]
        if len(canonical)!=1 or canonical[0]['status']!='SOURCE_SCOPE_REVIEW':
            raise ValueError('Canonical original source quarantine cannot be promoted by a nominal repair')
        if any(not isinstance(r['row_sha256'],str)or not re.fullmatch('[a-f0-9]{64}',r['row_sha256']) for r in row['rows']):
            raise ValueError('Complete exact direct-parent row hashes required')
    if sum(len(row['rows'])for row in rows)!=header['source_assertion_rows']:
        raise ValueError('Direct parent historical sibling rows incomplete')
    return header,rows


def compare_current_parent_assertion_rows(con,snapshots,inputs):
    """Source9 links may not rewrite any canonical source claim or historical sibling."""
    source=json.loads(gzip.decompress((Path(inputs)/'structure_source_contracts.json.gz').read_bytes()))
    originals={(r['table'],r['original_source_assertion']['id']):r['original_source_assertion']for r in source['quarantines']}
    count=0
    for snapshot in snapshots:
        rows=source_rows(con,snapshot,originals[(snapshot['table'],snapshot['canonical_id'])])
        expected={r['id']:r for r in snapshot['rows']}
        if {r['id']for r in rows}!=set(expected):raise ValueError('Nominal delta changed source claim multiplicity')
        for row in rows:
            prior=expected[row['id']]
            if row_sha(row)!=prior['row_sha256']or row['status']!=prior['status']or row.get('reason')!=prior['reason']:
                raise ValueError('Nominal delta cannot mutate raw source claim or adjudication history')
            count+=1
    return {'pass':True,'canonical_assertions':len(snapshots),'historical_source_rows_checked':count,
        'exact_later_source_status_permissions_used':0,'role_profile_normalization_applied_to_source_rows':False,
        'scope':'Current nominal child raw claims equal the independently inspected Source8 immediate parent; historical c933 transitions remain separately archived.'}
