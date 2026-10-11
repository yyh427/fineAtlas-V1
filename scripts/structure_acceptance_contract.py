"""Required evidence for a structural candidate; no inferred acceptance."""
REQUIRED_JOBS = frozenset({
    'integrity', 'source-preservation', 'logical-reproduction', 'whole-library',
    'contracts', 'cycles', 'witnesses', 'public-cli', 'full-six-matrix',
    'living', 'source-contracts', 'source-freeze', 'exports', 'public-install',
})



SUPPLEMENTAL_AUDITS = {
    'biology-version-scope': {
        'input': 'cub_annotation_version_scope.json',
        'script': 'audit_structure_biology_version_scope.py',
        'report': 'biology_version_scope_acceptance.json',
        'fields': ('input_sha256','all_200_original_targets_checked',
                   'new_label_scope_reviews_checked','mapping_status_counts',
                   'native_sql_labels_checked','native_public_paths_checked',
                   'world_exact_guard_rejections_checked', 'identity_scope_input_sha256',
                   'scientific_identity_scope_cases_checked','scientific_identity_bridges_checked',
                   'scientific_identity_scope_splits_checked'),
    },
    'vehicle-source-scope': {
        'input': 'structure_vehicle_source_scope.json',
        'script': 'audit_vehicle_source_scope.py',
        'report': 'vehicle_source_scope_acceptance.json',
        'fields': ('input_sha256','cohort_counts'),
    },
}



def frozen_supplemental_expectations(inputs, fingerprints):
    """Derive complete cohorts from frozen source inputs, never from a report."""
    import hashlib
    import json
    from collections import Counter
    from pathlib import Path
    inputs=Path(inputs);bindings=fingerprints['inputs'];expected={}
    def load(name):
        path=inputs/name
        if file_sha256(path)!=bindings.get(name):
            raise ValueError('Supplemental frozen input changed: '+name)
        return json.loads(path.read_text())
    if SUPPLEMENTAL_AUDITS['biology-version-scope']['input'] in bindings:
        payload=load('cub_annotation_version_scope.json')
        ledger=load('all_200_version_scope_ledger.json')
        native=load('structure_biology.json')['native_labels']
        native_keys={(row['dataset'],str(row['class_id'])) for row in native}
        full_native={('cub200',str(i)) for i in range(1,201)} | {('flowers102',str(i)) for i in range(1,103)}
        if len(native)!=302 or native_keys!=full_native:
            raise ValueError('Complete unique Flowers/CUB source-native cohort is required')
        if len(ledger)!=200 or payload['reviewed_label_count']!=200:
            raise ValueError('The complete original CUB author cohort is required')
        canonical=lambda obj: json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        if hashlib.sha256(canonical(ledger).encode()).hexdigest()!=payload['all_200_ledger_sha256']:
            raise ValueError('Complete CUB ledger fingerprint differs')
        by_id={str(row['class_id']):row for row in ledger}
        states={cid:row['prior_mapping_check']['status'] for cid,row in by_id.items()}
        if len(states)!=200 or sum(x=='ANNOTATION_SCOPE_REVIEW' for x in states.values())!=15:
            raise ValueError('Original CUB scope-review cohort must be retained')
        ids={str(case['class_id']) for case in payload['mapping_reviews']}
        if (len(ids)!=12 or payload['new_label_scope_reviews']!=12 or len(payload['mapping_reviews'])!=12
                or not ids<=states.keys() or any(states[cid]=='ANNOTATION_SCOPE_REVIEW' for cid in ids)):
            raise ValueError('Incomplete temporal label review inventory')
        states.update({cid:'ANNOTATION_SCOPE_REVIEW' for cid in ids})
        expected['biology-version-scope']={
            'input_sha256':hashlib.sha256(canonical(payload).encode()).hexdigest(),
            'all_200_original_targets_checked':len(states),
            'new_label_scope_reviews_checked':len(ids),
            'mapping_status_counts':dict(Counter(states.values())),
            'native_sql_labels_checked':len(native),
            'native_public_paths_checked':len(native),
            'world_exact_guard_rejections_checked':len(ids),
        }
        extent=load('structure_biology_identity_scope.json')
        groups=extent['reviewed_identity_groups']
        bridges={row['id'] for group in groups for row in group['actual_active_bridges']}
        group_ids={str(group['class_id']) for group in groups}
        if len(groups)!=12 or group_ids!=ids or len(group_ids)!=12 or len(bridges)!=17 or len(extent['repairs'])!=1:
            raise ValueError('Complete fixed scientific extent review cohort is required')
        expected['biology-version-scope'].update(
            identity_scope_input_sha256=hashlib.sha256(canonical(extent).encode()).hexdigest(),
            scientific_identity_scope_cases_checked=len(groups),
            scientific_identity_bridges_checked=len(bridges),
            scientific_identity_scope_splits_checked=len(extent['repairs']))
    if SUPPLEMENTAL_AUDITS['vehicle-source-scope']['input'] in bindings:
        manifest=load('structure_vehicle_source_scope.json')
        if manifest['schema']!='FINEATLAS_VEHICLE_SOURCE_SCOPE_MANIFEST_V1':
            raise ValueError('Unsupported vehicle producer inventory')
        rows={row['portable_file']:row['rows'] for row in manifest['producer_snapshots']}
        if (type(rows.get('epa_vehicles.csv.gz')) is not int or rows['epa_vehicles.csv.gz']!=50242
                or type(rows.get('faa_ACFTREF.txt.gz')) is not int or rows['faa_ACFTREF.txt.gz']!=94043
                or type(manifest['source_native_uid_inventory']) is not int
                or manifest['source_native_uid_inventory']!=220248):
            raise ValueError('Complete frozen EPA/FAA publisher cohorts are required for this contract version')
        expected['vehicle-source-scope']={
            'input_sha256':bindings['structure_vehicle_source_scope.json'],
            'cohort_counts':{
                'producer_native_uid_inventory':manifest['source_native_uid_inventory'],
                'projection_inventory':manifest['projection_inventory'],
                'nhtsa_inventory':manifest['nhtsa_inventory'],
                'epa_configurations':rows['epa_vehicles.csv.gz'],
                'faa_models':rows['faa_ACFTREF.txt.gz'],
                'new_relation_counts':manifest['operation_counts'],
            },
        }
        author=load('structure_cars_author_scope.json')
        if author.get('schema')!='FINEATLAS_CARS_AUTHOR_SCOPE_V1':
            raise ValueError('Unknown complete Cars author-scope contract')
        native_keys={(row['dataset'],str(row['class_id'])) for row in author['scope_targets']}
        review_keys={(row['before']['dataset'],str(row['before']['class_id'])) for row in author['world_mapping_reviews']}
        complete_keys={('stanford_cars',str(i)) for i in range(1,197)}
        if (len(author['scope_targets'])!=196 or len(author['world_mapping_reviews'])!=196
                or native_keys!=complete_keys or review_keys!=complete_keys
                or type(author['source_native_pair_count']) is not int or author['source_native_pair_count']!=19110
                or type(author['source_native_label_count']) is not int or author['source_native_label_count']!=196
                or type(author['world_mappings_reviewed']) is not int or author['world_mappings_reviewed']!=196):
            raise ValueError('Complete unique Cars author and world-scope cohorts are required')
        expected['vehicle-source-scope']['cohort_counts'].update(
            cars_author_native_labels=len(native_keys),
            cars_author_world_mapping_reviews=len(review_keys),
            cars_author_native_pairs=len(native_keys)*(len(native_keys)-1)//2)
    return expected


def validate_supplemental_report(name, report, expected, revision):
    if name not in SUPPLEMENTAL_AUDITS:
        raise ValueError('Unknown supplemental source audit')
    if report.get('pass') is not True or report.get('public_api_checked') is not True:
        raise ValueError('Complete source and public API audit required: '+name)
    if report.get('revision',report.get('database_revision'))!=revision:
        raise ValueError('Supplemental audit revision differs: '+name)
    fields=SUPPLEMENTAL_AUDITS[name]['fields']
    import json
    if set(expected)!=set(fields) or any(expected[key] is None or json.dumps(report.get(key),sort_keys=True)!=json.dumps(expected[key],sort_keys=True) for key in fields):
        raise ValueError('Supplemental complete source cohort differs: '+name)
    return report


def validate_completed_acceptance(receipt):
    if receipt.get('schema') != 'FINEATLAS_STRUCTURE_ACCEPTANCE_V1':
        raise ValueError('Wrong structural acceptance schema')
    if not all(receipt.get(key) is True for key in ('complete', 'all_pass',
             'candidate_unchanged', 'inputs_unchanged', 'code_unchanged')) or not receipt.get('ended_utc'):
        raise ValueError('Structural acceptance must be complete and bound')
    jobs = receipt.get('jobs', {})
    if set(jobs) != REQUIRED_JOBS:
        raise ValueError('Required structural acceptance jobs missing or unexpected')
    for name, job in jobs.items():
        if type(job.get('exit_code')) is not int or job.get('exit_code') != 0 or job.get('pass') is not True or not job.get('ended_utc'):
            raise ValueError('Acceptance job incomplete or failed: '+name)
    return receipt


def file_sha256(path):
    import hashlib
    with path.open('rb') as stream:
        result=hashlib.sha256()
        while block:=stream.read(1024*1024):result.update(block)
    return result.hexdigest()


def validate_public_evidence(public, receipt, evidence_path):
    import json
    from pathlib import Path
    for key in ('all_pass','public_download_unauthenticated','matching_installed_sdk'):
        if public.get(key) is not True:raise ValueError('Missing actual public verification: '+key)
    for key in ('database_sha256','database_revision','release'):
        if public.get(key)!=receipt.get(key):raise ValueError('Public artifact binding mismatch: '+key)
    if not public.get('ended_utc'):raise ValueError('Public verification incomplete')
    required={'download','installed-sdk','full-six-matrix','living','whole-library','exports','public-cli','source-contracts'}
    supplements=receipt.get('supplemental_audits',{})
    expected_supplements={name for name,spec in SUPPLEMENTAL_AUDITS.items()
                          if spec['input'] in receipt.get('fingerprints',{}).get('inputs',{})}
    if not isinstance(supplements,dict) or set(supplements)!=expected_supplements:
        raise ValueError('Unknown supplemental source evidence')
    required |= set(supplements)
    evidence=public.get('evidence',{})
    if set(evidence)!=required:raise ValueError('Complete public verification evidence files required')
    reports={}
    for name,row in evidence.items():
        path=Path(row['path']).resolve(strict=True)
        if path==evidence_path.resolve():raise ValueError('Public evidence cannot cite itself')
        if file_sha256(path)!=row.get('sha256'):raise ValueError('Public evidence file changed: '+name)
        reports[name]=json.loads(path.read_text())
        if row.get('pass') is not True:raise ValueError('Public evidence job failed: '+name)
    for name,row in supplements.items():
        local_path=Path(row['path']).resolve(strict=True)
        if file_sha256(local_path)!=row['sha256']:
            raise ValueError('Local supplemental report changed: '+name)
        local_report=json.loads(local_path.read_text())
        validate_supplemental_report(name,local_report,row['expected'],receipt['database_revision'])
        validate_supplemental_report(name,reports[name],row['expected'],receipt['database_revision'])
    download=reports['download'];sdk=reports['installed-sdk']
    for name,flag in (('whole-library','pass'),('exports','pass'),('public-cli','all_pass'),('source-contracts','pass')):
        if reports[name].get(flag) is not True:raise ValueError('Public report failed: '+name)
    if reports['living'].get('status')!='PASS' or reports['living'].get('errors'):
        raise ValueError('Public living report failed')
    matrix=reports['full-six-matrix']
    expected=receipt.get('matrix_expected_counts')
    if not isinstance(expected,dict) or set(expected)!={'legacy','reviewed_old_floors','reviewed_new_floors','source_native','reviewed_rank_floors','source_native_rank_floors'}:
        raise ValueError('Frozen complete local matrix policy/count expectations required')
    actual={name:{dataset:row.get('counts') for dataset,row in mode.get('datasets',{}).items()} for name,mode in matrix.items()}
    if json.dumps(actual,sort_keys=True)!=json.dumps(expected,sort_keys=True):raise ValueError('Public matrix must match every frozen mode and canonical dataset')
    full={'cub200':200,'fgvc_aircraft':100,'flowers102':102,'pets37':37,'stanford_dogs':120,'stanford_cars':196}
    for name,mode in expected.items():
        cohort={'cub200','fgvc_aircraft','flowers102'} if name.startswith('source_native') else set(full)
        if name=='source_native_rank_floors' and 'structure_cars_author_scope.json' in receipt.get('fingerprints',{}).get('inputs',{}):
            cohort |= {'stanford_cars'}
        if set(mode)!=cohort or any(row.get('labels')!=full[dataset] or row.get('pairs')!=full[dataset]*(full[dataset]-1)//2 for dataset,row in mode.items()):
            raise ValueError('Incomplete matrix label/pair cohort: '+name)
    if download.get('database_sha256')!=receipt['database_sha256'] or download.get('authenticated') is not False or download.get('fresh_download') is not True or not download.get('public_download_urls'):
        raise ValueError('Actual unauthenticated full-file download receipt required')
    if download.get('release')!=receipt['release'] or download.get('database_revision')!=receipt['database_revision']:
        raise ValueError('Downloaded manifest release/revision mismatch')
    from urllib.parse import urlsplit
    asset_proofs=download.get('asset_proofs',[])
    if not asset_proofs or [row.get('url') for row in asset_proofs]!=download['public_download_urls'] or any(row.get('fresh_download') is not True or row.get('network_request') is not True or row.get('authenticated') is not False or row.get('initial_cached_bytes')!=0 or row.get('http_status') not in (200,206) or urlsplit(row.get('url','')).scheme.lower() not in {'http','https'} for row in asset_proofs):
        raise ValueError('Actual fresh per-asset public network download required')
    if sdk.get('all_pass') is not True or sdk.get('database_revision')!=receipt['database_revision'] or sdk.get('release')!=receipt['release'] or sdk.get('installed_sdk') is not True or sdk.get('database_sha256')!=receipt['database_sha256']:
        raise ValueError('Actual matching installed-SDK report required')
    if not download.get('database') or Path(download['database']).resolve()!=Path(sdk.get('database','')).resolve() or not download.get('artifact_stamp') or download['artifact_stamp']!=sdk.get('artifact_stamp'):
        raise ValueError('Installed SDK must check the actual unchanged downloaded file')
    public_path=Path(download['database']).resolve()
    bound_reports=[(name,reports[name]) for name in ('living','whole-library','exports','public-cli','source-contracts')]
    bound_reports += [(name,reports[name]) for name in supplements]
    bound_reports += [('full-six-matrix:'+name,mode) for name,mode in matrix.items()]
    for name,report in bound_reports:
        if (not report.get('database') or Path(report['database']).resolve()!=public_path
                or report.get('database_revision',report.get('revision'))!=receipt['database_revision']):
            raise ValueError('Public report must check the same downloaded artifact: '+name)
    actual=Path(download['database']).stat()
    if [actual.st_size,actual.st_mtime_ns,actual.st_ino]!=download['artifact_stamp']:
        raise ValueError('Public downloaded artifact changed during verification')
    return file_sha256(evidence_path)


def validate_comparison_inventory(comparison):
    artifacts=comparison.get('artifacts',{})
    if set(artifacts)!={'primary','reproduction'}:raise ValueError('Two independent artifact inventories required')
    inventories=[]
    for row in artifacts.values():
        inventory=row.get('logical_table_inventory')
        if not isinstance(inventory,list) or not inventory or len(set(inventory))!=len(inventory) or row.get('table_count')!=len(inventory):
            raise ValueError('Actual complete table inventory required')
        inventories.append(set(inventory))
    if inventories[0]!=inventories[1] or comparison.get('logical_table_count')!=len(inventories[0]):
        raise ValueError('Compared actual table inventories differ')
    compared=set(comparison.get('compared_content_tables',[]))
    excluded=set(comparison.get('excluded_content_tables',{}))
    if compared & excluded or compared | excluded != inventories[0]:
        raise ValueError('Complete compared/excluded table accounting required')
    return comparison


def validate_independent_builds(primary_path, reproduction_path, primary_build, reproduction_build, fingerprints):
    import json
    from pathlib import Path
    if primary_path.resolve()==reproduction_path.resolve() or primary_path.samefile(reproduction_path):
        raise ValueError('Independent reproduction cannot compare one file or aliases')
    receipts=[]
    for database,path in ((primary_path,primary_build),(reproduction_path,reproduction_build)):
        row=json.loads(path.read_text())
        if row.get('schema')!='FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1' or row.get('complete') is not True or row.get('pass') is not True or not row.get('build_id') or not row.get('ended_utc'):
            raise ValueError('Actual completed independent build receipt required')
        if Path(row['database']).resolve()!=database.resolve():raise ValueError('Build receipt names another artifact')
        base=path.parent
        for name in ('started_fingerprints','build_status'):
            target=base/(name+'.json')
            if file_sha256(target)!=row.get(name+'_sha256'):raise ValueError('Independent build evidence changed: '+name)
        if json.loads((base/'started_fingerprints.json').read_text())!=fingerprints:
            raise ValueError('Independent build used different code or inputs')
        states=json.loads((base/'build_status.json').read_text())
        if not states or any(stage.get('status')!='PASS' for stage in states.values()):raise ValueError('Build stages failed or incomplete')
        receipts.append({**row,'receipt_sha256':file_sha256(path),'receipt_path':str(path)})
    if receipts[0]['build_id']==receipts[1]['build_id']:raise ValueError('Copied build receipt cannot prove independent reconstruction')
    return receipts
