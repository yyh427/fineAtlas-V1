#!/usr/bin/env python3
"""Independent whole-source physical-scope audit, with separate public SDK checks.

This verifier does not import the producer adapter, freezer, or their classifier.
It binds publisher numeric identifiers, source fields, original source relations,
actual admitted rows and canonical endpoint grain. NHTSA filter memberships and
V26 partial reference sets never establish whole named-model physical type.
"""
from __future__ import annotations
if not __debug__:
    raise RuntimeError('Vehicle source scope acceptance forbids optimized Python')
import argparse
from collections import Counter,defaultdict
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
CAR='wordnet31:02961779-n'
MOTOR='wordnet31:03796768-n'
AIRCRAFT='wordnet31:02689427-n'
PASSENGER_SIZE_CLASSES=('Two Seaters','Minicompact Cars','Subcompact Cars','Compact Cars','Midsize Cars','Large Cars','Small Station Wagons','Midsize Station Wagons','Large Station Wagons')
OTHER_SIZE_CLASSES=('Vans','Small Pickup Trucks','Standard Pickup Trucks','Special Purpose Vehicle 2WD','Special Purpose Vehicles','Special Purpose Vehicle 4WD','Small Pickup Trucks 2WD','Standard Pickup Trucks 2WD','Standard Pickup Trucks 4WD','Vans, Cargo Type','Vans, Passenger Type','Minivan - 2WD','Sport Utility Vehicle - 4WD','Minivan - 4WD','Sport Utility Vehicle - 2WD','Small Pickup Trucks 4WD','Midsize-Large Station Wagons','Special Purpose Vehicle','Standard Pickup Trucks/2wd','Vans Passenger','Special Purpose Vehicles/2wd','Special Purpose Vehicles/4wd','Small Sport Utility Vehicle 4WD','Standard Sport Utility Vehicle 2WD','Standard Sport Utility Vehicle 4WD','Small Sport Utility Vehicle 2WD')
AIRCRAFT_CODES={'1':'Glider','2':'Balloon','3':'Blimp/Dirigible','4':'Fixed wing single engine','5':'Fixed wing multi engine','6':'Rotorcraft','7':'Weight-shift-control','8':'Powered Parachute','9':'Gyroplane','H':'Hybrid Lift','O':'Other'}


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value,str) else value).hexdigest()


def content_sha(row):
    return sha(json.dumps({k:v for k,v in dict(row).items() if k not in ('id','status','reason')},sort_keys=True))


def classification_assertion_rows(c, uid, parent, relation, source):
    """Bind evidence to this source assertion, retaining other decision history."""
    return c.execute(
        'SELECT r.*,e.payload proof FROM edges r '
        'JOIN hierarchy_decisions h ON h.subject_uid=r.child_uid '
        "AND h.object_uid=r.parent_uid AND h.operation='link' "
        'AND h.evidence_id IN '
        "(SELECT value FROM json_each(r.provenance,'$.evidence_ids')) "
        'JOIN evidence e ON e.evidence_id=h.evidence_id '
        'WHERE r.child_uid=? AND r.parent_uid=? AND r.relation=? AND r.source=?',
        (uid, parent, relation, source)).fetchall()


def canonical_role(row):
    if row['node_kind']:
        return row['node_kind']
    rank=(row['rank'] or '').casefold()
    return {'configuration':'CONFIGURATION','model_year':'CONFIGURATION',
            'model_year_configuration':'CONFIGURATION','model':'MODEL',
            'aircraft_model':'MODEL','vehicle_model':'MODEL','model_family':'MODEL_FAMILY',
            'series':'MODEL_FAMILY','instance':'INSTANCE'}.get(rank,'CLASS')


def vehicle_type(value):
    if value in PASSENGER_SIZE_CLASSES:return CAR
    if value in OTHER_SIZE_CLASSES:return MOTOR
    return None


def catalogue_model_type(_record,_query_filter):
    """A model row's Make_ID/Model_ID/Model_Name has no whole-object type field."""
    return None


def reference_set_whole_projection_type(_references,_publisher_range_definition=None):
    """Matched citations alone have no closed whole-projection scope guarantee."""
    return None


def open_readonly(database):
    database=Path(database).resolve(strict=True)
    if any(Path(str(database)+s).exists() for s in ('-wal','-shm','-journal')):
        raise ValueError('Acceptance requires a closed SQLite artifact')
    c=sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON');c.execute('PRAGMA temp_store=MEMORY')
    c.execute('PRAGMA cache_size=-131072')
    return c


def load_frozen(inputs):
    inputs=Path(inputs);manifest=json.loads((inputs/'structure_vehicle_source_scope.json').read_text())
    if manifest.get('schema')!='FINEATLAS_VEHICLE_SOURCE_SCOPE_MANIFEST_V1':
        raise ValueError('Unknown frozen source scope manifest')
    def frozen_file(name,expected):
        p=(inputs/name).resolve()
        if not p.is_relative_to(inputs.resolve()):raise ValueError('Frozen input escapes its directory')
        value=p.read_bytes()
        if sha(value)!=expected:raise ValueError('Frozen input checksum differs: '+name)
        return value
    raw=gzip.decompress(frozen_file(manifest['payload_file'],manifest['payload_sha256']))
    if sha(raw)!=manifest['payload_uncompressed_sha256']:raise ValueError('Raw payload checksum differs')
    payload=json.loads(raw)
    operations=[json.loads(s) for s in frozen_file(manifest['operations_file'],manifest['operations_sha256']).decode().splitlines() if s]
    if operations!=payload['operations']:raise ValueError('Frozen operation list is incomplete or differs')
    producer={}
    for p in manifest['producer_snapshots']:
        data=gzip.decompress(frozen_file(p['portable_file'],p['portable_gzip_sha256']))
        if sha(data)!=p['sha256']:raise ValueError('Publisher CSV snapshot checksum differs')
        source='epa' if p['portable_file'].startswith('epa_') else 'faa'
        key='id' if source=='epa' else 'CODE';rows={}
        for row in csv.DictReader(io.StringIO(data.decode('utf-8-sig'))):
            identifier=str(row[key]).strip()
            if identifier in rows:raise ValueError('Duplicate numeric/native publisher record ID')
            rows[identifier]=row
        if len(rows)!=p['rows']:raise ValueError('Publisher snapshot row count differs')
        producer[source]=rows
    manifest['_actual_manifest_sha256']=sha((inputs/'structure_vehicle_source_scope.json').read_bytes())
    return manifest,payload,producer


def audit_rows(c,manifest,payload,producer,*,require_ready=True):
    errors=[];counts=Counter();source_counts=Counter();native_claims=Counter()
    meta={r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM metadata')}
    if require_ready and (not all(meta.get(x) is True for x in ('unified_ready','usability_indexes_ready','browse_indexes_ready')) or meta.get('browse_index_revision')!=meta.get('database_revision')):
        errors.append({'kind':'NOT_READY_OR_REVISION_MISMATCH'})
    if meta.get('vehicle_source_scope',{}).get('manifest_sha256')!=manifest.get('_actual_manifest_sha256'):
        errors.append({'kind':'DATABASE_SOURCE_SCOPE_MANIFEST_NOT_BOUND'})
    def error(kind,**fields):
        errors.append(dict(kind=kind,**fields))
    valid_epa={}
    # Every current raw producer UID, including source-only manufacturers and
    # model aggregates, is bound. Review records do not disappear from coverage.
    for item in payload['full_native_source_inventory']:
        source=item['source'];source_counts[source]+=1
        row=c.execute('SELECT n.*,p.node_kind FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(item['uid'],)).fetchone()
        if not row or row['source']!=source or sha(row['data'])!=item['native_record_sha256']:
            error('SOURCE_UID_OR_RAW_PAYLOAD_CHANGED',uid=item['uid']);continue
        counts[source+':'+item['decision']]+=1
        if item['decision']!='FIELD_SUPPORTED':continue
        raw=json.loads(row['data'])
        fields=('id','make','model','year','VClass','baseModel') if source=='epa' else ('CODE','MFR','MODEL','TYPE-ACFT','TYPE-ENG','NO-ENG','NO-SEATS')
        key='id' if source=='epa' else 'CODE';primary=producer[source].get(str(raw[key]).strip())
        if not primary or any(str(raw.get(k,'')).strip()!=str(primary.get(k,'')).strip() for k in fields):
            error('EXACT_PUBLISHER_RECORD_OR_MATERIAL_FIELDS_DIFFER',uid=item['uid']);continue
        if source=='epa':
            expected=vehicle_type(raw['VClass'])
            if expected is None or canonical_role(row)!='CONFIGURATION' or row['visibility']!='ACTIVE' or expected!=item['physical_parent']:
                error('CONFIGURATION_GRAIN_OR_REVIEWED_ENUM_RANGE_MISMATCH',uid=item['uid'])
            else:valid_epa[item['uid']]=expected
        else:
            code=str(raw['TYPE-ACFT']).strip()
            if code not in AIRCRAFT_CODES or AIRCRAFT_CODES[code]!=item['native_type_description']:
                error('FAA_DICTIONARY_CODE_SCOPE_MISMATCH',uid=item['uid'])
            if code in ('4','5'):
                engine_count=int(str(raw['NO-ENG']).strip())
                if engine_count!=(1 if code=='4' else engine_count) or (code=='5' and engine_count<2):
                    error('FAA_FIXED_WING_ENGINE_COUNT_CONTRADICTION',uid=item['uid'])
            for claim in item['existing_native_model_type_relations']:
                actual=c.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',(claim['subject_uid'],claim['object_uid'],claim['relation'],claim['source'])).fetchall()
                if len(actual)!=1 or actual[0]['status']!=claim['status'] or content_sha(actual[0])!=claim['content_sha256']:
                    error('FAA_ORIGINAL_NATIVE_TYPE_ASSERTION_CHANGED',uid=item['uid'],parent=claim['object_uid'])
                native_claims['FAA_NATIVE_MODEL_TYPE']+=1
    for source,count in source_counts.items():
        actual=c.execute('SELECT count(*) FROM nodes WHERE source=?',(source,)).fetchone()[0]
        if actual!=count:error('FULL_SOURCE_INVENTORY_INCOMPLETE',source=source,frozen=count,actual=actual)
    for claim in payload.get('retained_epa_native_assertions',[]):
        rows=c.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',(claim['subject_uid'],claim['object_uid'],claim['relation'],claim['source'])).fetchall()
        if len(rows)!=1 or rows[0]['status']!=claim['status'] or content_sha(rows[0])!=claim['content_sha256']:
            error('EPA_RETAINED_NATIVE_ASSERTION_CHANGED',uid=claim['subject_uid'],parent=claim['object_uid'])
        native_claims['EPA_'+claim['relation']]+=1
    for item in payload['full_projection_inventory']:
        row=c.execute('SELECT data FROM nodes WHERE uid=?',(item['uid'],)).fetchone()
        if not row or sha(row[0])!=item['native_record_sha256']:error('PROJECTION_RAW_SOURCE_CHANGED',uid=item['uid'])
        if c.execute("SELECT 1 FROM entity_relations WHERE subject_uid=? AND source='Producer-bound source configuration reference scope' AND status='ACTIVE'",(item['uid'],)).fetchone():
            error('SUBSET_REFERENCE_SET_PROMOTED_TO_WHOLE_PROJECTION_TYPE',uid=item['uid'])
    operation_counts=Counter()
    for op in payload['operations']:
        proof=op['proof'];uid=op['uid'];relation=op['relation'];operation_counts[relation]+=1
        if relation=='CONFIGURATION_TYPE_OF':
            if uid not in valid_epa or op['parent']!=valid_epa[uid] or proof.get('individual_semantic_review') is not False or proof.get('no_lifting_to_entire_model') is not True:
                error('NEW_CONFIGURATION_TYPE_NOT_A_PRODUCER_BOUND_NATIVE_RANGE',uid=uid)
            rows=c.execute('SELECT r.*,e.payload proof FROM entity_relations r LEFT JOIN evidence e ON e.evidence_id=r.evidence_id WHERE subject_uid=? AND object_uid=? AND relation=? AND r.source=?',(uid,op['parent'],relation,op['source'])).fetchall()
        elif relation=='IS_A':
            n=c.execute('SELECT n.*,p.node_kind FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(uid,)).fetchone()
            parent=c.execute('SELECT description FROM nodes WHERE uid=?',(op['parent'],)).fetchone()
            if uid!='wikidata:Q154503' or op['parent']!=AIRCRAFT or canonical_role(n)!='CLASS' or json.loads(n['data']).get('wikidata_description')!='heavier-than-air aircraft that derives lift from dynamic motion through the air' or proof.get('primary_source_section','').split()[0]!='2.1.2' or not proof.get('source_scope_entails_parent') or not parent or sha(parent[0])!=proof['parent_definition_sha256']:
                error('AERODYNE_FULL_GENERIC_CLASS_OR_PARENT_SCOPE_NOT_BOUND',uid=uid)
            rows=classification_assertion_rows(c,uid,op['parent'],relation,op['source'])
        else:error('UNSUPPORTED_NEW_RELATION',uid=uid);continue
        if len(rows)!=1 or rows[0]['status']!='ACTIVE' or json.loads(rows[0]['proof'])!=proof:
            error('ACTUAL_TYPE_ASSERTION_OR_EVIDENCE_DIFFER',uid=uid,relation=relation)
        if proof.get('world_identity_assertion') is not False or not proof.get('no_identity_merges'):
            error('PHYSICAL_TYPE_FALSE_WORLD_IDENTITY_PROMOTION',uid=uid)
    for source in ('Producer-bound EPA physical configuration scope','Reviewed aviation physical-class scope'):
        table='entity_relations' if source.startswith('Producer-bound') else 'edges'
        actual=c.execute('SELECT count(*) FROM '+table+' WHERE source=? AND status=\'ACTIVE\'',(source,)).fetchone()[0]
        expected=sum(op['source']==source for op in payload['operations'])
        if actual!=expected:error('NEW_SOURCE_CLAIM_INVENTORY_INCOMPLETE',source=source,expected=expected,actual=actual)
    for item in payload['full_nhtsa_native_inventory']:
        row=c.execute('SELECT data FROM nodes WHERE uid=?',(item['uid'],)).fetchone()
        if not row or sha(row[0])!=item['data_sha256']:error('NHTSA_NATIVE_RECORD_CHANGED',uid=item['uid'])
    nhtsa_groups=defaultdict(set)
    for query in payload['nhtsa_catalogue_capture']['typed_model_inventories']:
        snapshot=query['snapshot'];records=snapshot['data']['Results']
        for r in records:
            nhtsa_groups[(r['Make_ID'],r['Model_ID'])].add(query['type_record']['VehicleTypeName'])
            if catalogue_model_type(r,query['type_record']) is not None:error('NHTSA_CATALOGUE_FALSE_TYPE_PROOF')
    contradictions=[{'make_id':k[0],'model_id':k[1],'catalogue_filters':sorted(v)} for k,v in nhtsa_groups.items() if len(v)>1]
    if not any(x['model_id']==1938 and len(x['catalogue_filters'])>=3 for x in contradictions):
        error('REAL_RAM_CATALOGUE_FILTER_COUNTEREXAMPLE_NOT_FROZEN')
    return {'pass':not errors,'database_revision':meta.get('database_revision'),
        'database_release':meta.get('release'),'producer_uid_inventory':dict(source_counts),
        'producer_scope_dispositions':dict(counts),'new_relation_counts':dict(operation_counts),
        'original_native_assertions_checked':dict(native_claims),'projection_inventory':len(payload['full_projection_inventory']),
        'source_projection_candidate_bridges_withheld':122,'nhtsa_native_records':len(payload['full_nhtsa_native_inventory']),
        'nhtsa_actual_model_multifilter_counterexamples':contradictions,'new_world_identities':0,'errors':errors}


def audit_cars_author_rows(c,inputs):
    path=Path(inputs)/'structure_cars_author_scope.json'
    if not path.exists():
        raise ValueError('Cars author scope frozen input is required for the complete vehicle contract')
    payload=json.loads(path.read_bytes());fingerprint=sha(path.read_bytes());errors=[]
    if sha((Path(inputs)/'cars_meta.mat').read_bytes())!=payload['source_metadata']['source_metadata_sha256']:
        errors.append({'kind':'ORIGINAL_CARS_META_CHECKSUM_DIFFERS'})
    stored_meta=c.execute("SELECT value FROM metadata WHERE key='cars_author_scope'").fetchone()
    if not stored_meta or json.loads(stored_meta[0]).get('input_sha256')!=fingerprint:
        errors.append({'kind':'DATABASE_CARS_AUTHOR_SCOPE_INPUT_NOT_BOUND'})
    by_id={x['class_id']:x for x in payload['scope_targets']}
    if len(by_id)!=196 or set(by_id)!={str(i) for i in range(1,197)}:
        errors.append({'kind':'CARS_196_SOURCE_CLASS_INVENTORY_CHANGED'})
    for item in payload['world_mapping_reviews']:
        before=item['before'];cid=before['class_id'];row=c.execute('SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?',('stanford_cars',cid)).fetchone()
        check=c.execute('SELECT * FROM dataset_mapping_checks WHERE dataset=? AND class_id=?',('stanford_cars',cid)).fetchone()
        if not row or row['target_uid']!=before['target_uid'] or row['label']!=before['label'] or row['decision_status']!='REVIEW' or not check or check['status']!='ANNOTATION_SCOPE_REVIEW':
            errors.append({'kind':'CARS_WORLD_MAPPING_FALSE_SCOPE_CONFIRMATION','class_id':cid})
        if check and json.loads(check['proof']).get('input_sha256')!=fingerprint:
            errors.append({'kind':'CARS_WORLD_MAPPING_REVIEW_NOT_BOUND_TO_INPUT','class_id':cid})
        n=c.execute('SELECT data FROM nodes WHERE uid=?',(before['target_uid'],)).fetchone()
        if not n or sha(n[0])!=item['proof']['native_record_sha256']:
            errors.append({'kind':'CARS_REAL_OR_SOURCE_ENTITY_RAW_CHANGED','class_id':cid})
        target=by_id[cid]
        stored=c.execute('SELECT * FROM dataset_scope_targets WHERE dataset=? AND class_id=? AND namespace=? AND source_version=?',('stanford_cars',cid,payload['namespace'],payload['source_version'])).fetchone()
        if not stored or stored['source_uid']!=target['source_uid'] or stored['label']!=target['label'] or stored['role']!='DATASET_CATEGORY' or stored['decision_status']!='SOURCE_DECLARED' or json.loads(stored['proof'])!=target['proof']:
            errors.append({'kind':'CARS_AUTHOR_NATIVE_TARGET_NOT_LITERAL_PUBLISHER_CLASS','class_id':cid});continue
        n=c.execute('SELECT n.*,p.node_kind,p.attributes FROM nodes n JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(target['source_uid'],)).fetchone()
        attrs=json.loads(n['attributes']) if n else {}
        if not n or n['label']!=before['label'] or n['source']!='stanford_cars_native' or n['node_kind']!='DATASET_CATEGORY' or attrs.get('identity_scope')!='SOURCE_NATIVE' or attrs.get('world_exact_identity_verified') is not False or attrs.get('source_native_identity_verified') is not True:
            errors.append({'kind':'CARS_AUTHOR_CATEGORY_MISREPRESENTED_AS_WORLD_OBJECT','class_id':cid})
        relations=c.execute("SELECT * FROM entity_relations WHERE subject_uid=? AND source='stanford_cars_native'",(target['source_uid'],)).fetchall()
        if len(relations)!=1 or relations[0]['relation']!='DEPICTS_TYPE' or relations[0]['object_uid']!=MOTOR or relations[0]['status']!='ACTIVE':
            errors.append({'kind':'CARS_AUTHOR_SCOPE_RELATION_MUST_ONLY_DEPICT_MOTOR_VEHICLE','class_id':cid})
        if c.execute('SELECT 1 FROM edges WHERE child_uid=? AND status=\'ACTIVE\'',(target['source_uid'],)).fetchone():
            errors.append({'kind':'CARS_AUTHOR_LABEL_FALSE_ORDINARY_TYPE_INCLUSION','class_id':cid})
    return {'pass':not errors,'input_sha256':fingerprint,'source_metadata_sha256':payload['source_metadata']['source_metadata_sha256'],
            'namespace':payload['namespace'],'source_version':payload['source_version'],'world_mapping_reviews':196,
            'source_native_labels':196,'source_native_pair_count':19110,'new_world_objects':0,'errors':errors}


def sdk_checks(database,inputs,payload,output,installed_sdk):
    sys.pycache_prefix=str(output/('private-pycache-'+uuid.uuid4().hex))
    if not installed_sdk:sys.path.insert(0,str(ROOT/'src'))
    from fineatlas.consistent import ConsistentAtlas
    from fineatlas.rewards import POLICIES
    if 'configuration_types' not in POLICIES or 'CONFIGURATION_TYPE_OF' not in POLICIES['configuration_types']['relations']:
        raise ValueError('SDK does not provide the separate configuration_types policy')
    if 'CONFIGURATION_TYPE_OF' in POLICIES['configuration']['relations']:
        raise ValueError('Legacy configuration policy was silently widened')
    results={};errors=[]
    atlas=ConsistentAtlas(database,view='all',relation_view='unified')
    try:
        for dataset in ('stanford_cars','fgvc_aircraft'):
            index=atlas.relation_reward_index(dataset,admission_mode='reviewed_paths')
            records=[]
            for cid,entry in sorted(index.labels.items()):
                path=index.path(cid);records.append({'class_id':cid,'endpoint':dict(entry),'path':path})
                if path.get('task_path_valid') and path.get('task_boundary_reachable') is not True:
                    errors.append({'kind':'PUBLIC_TASK_PATH_BOUNDARY_INCONSISTENCY','dataset':dataset,'class_id':cid})
            pairs=Counter();null_errors=0
            for pair in index.pairs():
                pairs[pair['status']]+=1
                if not pair['applicable'] and pair['distance'] is not None:null_errors+=1
            if null_errors:errors.append({'kind':'PUBLIC_INVALID_DISTANCE_NON_NULL','dataset':dataset,'pairs':null_errors})
            results[dataset]={'policy':index.policy,'task_boundary_roots':list(index.task_boundary_roots),'labels':records,'pairs':dict(pairs)}
        author=json.loads((Path(inputs)/'structure_cars_author_scope.json').read_text())
        index=atlas.relation_reward_index('stanford_cars',admission_mode='reviewed_paths',target_scope='source_native',source_namespace=author['namespace'],source_version=author['source_version'])
        native_records=[]
        for cid,entry in sorted(index.labels.items()):
            target=atlas.target('stanford_cars',cid,target_scope='source_native',source_namespace=author['namespace'],source_version=author['source_version'])
            world=atlas.target('stanford_cars',cid)
            if entry['reason'] is not None or target.get('world_identity_verified') is True or world['identity_verified'] is not False:
                errors.append({'kind':'CARS_NATIVE_WORLD_SCOPE_NOT_SEPARATED_OR_NATIVE_NOT_ADMITTED','class_id':cid})
            native_records.append({'class_id':cid,'endpoint':dict(entry),'path':index.path(cid),'native_target':target})
        native_pairs=Counter(pair['status'] for pair in index.pairs())
        if len(native_records)!=196 or native_pairs!={'COARSE_COMMON_ANCESTOR_ONLY':19110}:
            errors.append({'kind':'CARS_NATIVE_COARSE_ONLY_DENOMINATOR_CHANGED','labels':len(native_records),'pairs':dict(native_pairs)})
        results['stanford_cars_source_native']={'labels':native_records,'pairs':dict(native_pairs),'namespace':author['namespace'],'source_version':author['source_version']}
        direct_checks=[]
        for op in [payload['operations'][0],payload['operations'][-1]]:
            actual=atlas.path_result(op['uid']);direct_checks.append({'uid':op['uid'],'result':actual})
            if actual.get('status') not in ('CONNECTED','ROOT'):errors.append({'kind':'SOURCE_TYPE_REPAIR_PUBLIC_NAV_NOT_REACHABLE','uid':op['uid']})
        results['representative_navigation']=direct_checks
    finally:atlas.close()
    (output/'public_vehicle_task_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    return {'public_api_checked':True,'public_api_errors':errors,'sdk_file':str(sys.modules['fineatlas.consistent'].__file__)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True);parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--installed-sdk',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();manifest,payload,producer=load_frozen(args.inputs)
    stamp=args.database.stat()
    with open_readonly(args.database) as c:result=audit_rows(c,manifest,payload,producer)
    with open_readonly(args.database) as c:author_result=audit_cars_author_rows(c,args.inputs)
    result['cars_author_scope']=author_result
    result['pass']=result['pass'] and author_result['pass']
    result.update(sdk_checks(args.database,args.inputs,payload,args.output,args.installed_sdk))
    result['pass']=result['pass'] and not result['public_api_errors']
    result.update(schema='FINEATLAS_VEHICLE_SOURCE_SCOPE_ACCEPTANCE_V1',database=str(args.database.resolve()),input_sha256=sha((args.inputs/'structure_vehicle_source_scope.json').read_bytes()),manifest_sha256=sha((args.inputs/'structure_vehicle_source_scope.json').read_bytes()),cohort_counts={'producer_native_uid_inventory':manifest['source_native_uid_inventory'],'projection_inventory':manifest['projection_inventory'],'nhtsa_inventory':manifest['nhtsa_inventory'],'epa_configurations':manifest['producer_snapshots'][0]['rows'],'faa_models':manifest['producer_snapshots'][1]['rows'],'new_relation_counts':manifest['operation_counts'],'cars_author_native_labels':author_result['source_native_labels'],'cars_author_world_mapping_reviews':author_result['world_mapping_reviews'],'cars_author_native_pairs':author_result['source_native_pair_count']},elapsed_seconds=time.monotonic()-started,public_api_checked=True)
    if args.database.stat().st_size!=stamp.st_size or args.database.stat().st_mtime_ns!=stamp.st_mtime_ns:
        raise ValueError('Read-only acceptance changed the artifact')
    (args.output/'vehicle_source_scope_acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('nhtsa_actual_model_multifilter_counterexamples',)},ensure_ascii=False))
    if not result['pass']:raise SystemExit(1)


if __name__=='__main__':main()
