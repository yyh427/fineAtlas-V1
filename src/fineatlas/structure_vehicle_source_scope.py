"""Producer-bound ordinary physical type facts, without identity promotion.

The freezer admits native EPA configuration records only. FAA registered model
TYPE arcs already exist: the one new generic aerodyne inclusion restores their
legitimate aircraft ancestor. A reference set or maker catalogue is insufficient
for a named world model/configuration's whole scope.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter

INPUT_NAME = 'structure_vehicle_source_scope.json'


def _sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


# Reviewed publisher enum, rather than lexical matches or maker catalogues.
_PASSENGER=frozenset(('Two Seaters','Minicompact Cars','Subcompact Cars','Compact Cars',
    'Midsize Cars','Large Cars','Small Station Wagons','Midsize Station Wagons',
    'Large Station Wagons'))
_OTHER=frozenset(('Vans','Small Pickup Trucks','Standard Pickup Trucks',
    'Special Purpose Vehicle 2WD','Special Purpose Vehicles','Special Purpose Vehicle 4WD',
    'Small Pickup Trucks 2WD','Standard Pickup Trucks 2WD','Standard Pickup Trucks 4WD',
    'Vans, Cargo Type','Vans, Passenger Type','Minivan - 2WD','Sport Utility Vehicle - 4WD',
    'Minivan - 4WD','Sport Utility Vehicle - 2WD','Small Pickup Trucks 4WD',
    'Midsize-Large Station Wagons','Special Purpose Vehicle','Standard Pickup Trucks/2wd','Vans Passenger',
    'Special Purpose Vehicles/2wd','Special Purpose Vehicles/4wd',
    'Small Sport Utility Vehicle 4WD','Standard Sport Utility Vehicle 2WD',
    'Standard Sport Utility Vehicle 4WD','Small Sport Utility Vehicle 2WD'))


def validate_native_configuration_operation(operation,native_data,publisher_csv_sha256):
    proof=operation['proof'];fields=('id','make','model','year','VClass','baseModel')
    if any(proof['native_fields'].get(k)!=native_data.get(k) for k in fields):
        raise ValueError('Physical inclusion proof differs from the native configuration material fields')
    if operation['uid']!='epa:'+str(native_data['id']) or proof.get('primary_csv_sha256')!=publisher_csv_sha256:
        raise ValueError('Configuration identity is not the frozen publisher record')
    value=native_data['VClass']
    expected='wordnet31:02961779-n' if value in _PASSENGER else 'wordnet31:03796768-n' if value in _OTHER else None
    if not expected or operation['parent']!=expected:
        raise ValueError('Configuration ordinary physical parent differs from the reviewed enum scope')
    if not proof.get('no_lifting_to_entire_model') or proof.get('world_identity_assertion') is not False:
        raise ValueError('Physical fields cannot establish entire-model or author-annotation identity')


def _rows(c, table):
    return [dict(r) for r in c.execute('SELECT * FROM '+table+' ORDER BY 1,2')]


def apply_vehicle_source_scope(m):
    """Replay a complete checked source inventory before graph/cache construction."""
    path=m.inputs/INPUT_NAME
    if not path.exists():
        return {'status':'not_requested'}
    manifest=json.loads(path.read_text())
    if manifest.get('schema')!='FINEATLAS_VEHICLE_SOURCE_SCOPE_MANIFEST_V1':
        raise ValueError('Unrecognized vehicle source-scope manifest')
    compressed=(m.inputs/manifest['payload_file']).read_bytes()
    if _sha(compressed)!=manifest['payload_sha256']:
        raise ValueError('Vehicle source-scope payload checksum changed')
    raw=gzip.decompress(compressed)
    if _sha(raw)!=manifest['payload_uncompressed_sha256']:
        raise ValueError('Vehicle source-scope uncompressed checksum changed')
    payload=json.loads(raw)
    operation_file=m.inputs/manifest['operations_file']
    if _sha(operation_file.read_bytes())!=manifest['operations_sha256']:
        raise ValueError('Vehicle source-scope operation checksum changed')
    operations=[json.loads(line) for line in operation_file.read_text().splitlines() if line]
    if operations!=payload['operations'] or Counter(x['relation'] for x in operations)!=Counter(manifest['operation_counts']):
        raise ValueError('Vehicle operation manifest does not bind complete frozen operations')
    expected=Counter(x['source'] for x in payload['full_native_source_inventory'])
    for source,count in expected.items():
        if m.c.execute('SELECT count(*) FROM nodes WHERE source=?',(source,)).fetchone()[0]!=count:
            raise ValueError('Incomplete frozen producer source inventory: '+source)
    inventory=payload['full_native_source_inventory']+payload['full_projection_inventory']
    inventory += [dict(x,native_record_sha256=x['data_sha256']) for x in payload['full_nhtsa_native_inventory']]
    for item in inventory:
        current=m.c.execute('SELECT data FROM nodes WHERE uid=?',(item['uid'],)).fetchone()
        if not current or _sha(current[0])!=item['native_record_sha256']:
            raise ValueError('Producer source UID/payload changed: '+item['uid'])
    for operation in operations:
        if operation['source']=='Producer-bound source configuration reference scope':
            raise ValueError('Named projection physical scope is not established by its reference samples')
        if operation['source'].startswith('NHTSA'):
            raise ValueError('NHTSA typed model filters are catalogues, not physical type proof')
        proof=operation['proof']
        if proof.get('world_identity_assertion') is not False or proof.get('no_identity_merges') is not True:
            raise ValueError('Physical type repair must not promote world identity')
        if operation['relation']=='CONFIGURATION_TYPE_OF':
            row=m.c.execute('SELECT source,data FROM nodes WHERE uid=?',(operation['uid'],)).fetchone()
            if not row or row[0]!='epa' or not proof.get('no_lifting_to_entire_model'):
                raise ValueError('Only producer-bound EPA configurations are admitted')
            validate_native_configuration_operation(operation,json.loads(row['data']),manifest['producer_snapshots'][0]['sha256'])
    before_targets=_rows(m.c,'dataset_targets')
    before_checks=_rows(m.c,'dataset_mapping_checks')
    before_nodes=m.c.execute('SELECT count(*) FROM nodes').fetchone()[0]
    from .hierarchy import apply_refinements
    result=apply_refinements(m,manifest['operations_file'])
    if before_nodes!=m.c.execute('SELECT count(*) FROM nodes').fetchone()[0] or before_targets!=_rows(m.c,'dataset_targets') or before_checks!=_rows(m.c,'dataset_mapping_checks'):
        raise ValueError('Physical source scope unexpectedly changed nodes or world mappings')
    m.meta('vehicle_source_scope',{'manifest_sha256':_sha(path.read_bytes()),
        'payload_sha256':manifest['payload_sha256'],'operation_counts':manifest['operation_counts'],
        'producer_native_uid_inventory':len(payload['full_native_source_inventory']),
        'source_projections_review':len(payload['full_projection_inventory']),
        'nhtsa_catalogue_only_review':len(payload['full_nhtsa_native_inventory']),
        'new_nodes':0,'new_identities':0,'mapping_promotions':0,
        'source_projection_type_bridges_withheld':122,'old_configuration_policy_unchanged':True})
    m.c.commit()
    return {'status':'PASS','refinements':result,'physical_inclusion_claims':manifest['operation_counts'],
            'world_mapping_promotions':0,'source_projection_type_bridges_withheld':122}
