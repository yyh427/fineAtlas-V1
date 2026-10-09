"""Required evidence for a structural candidate; no inferred acceptance."""
REQUIRED_JOBS = frozenset({
    'integrity', 'source-preservation', 'logical-reproduction', 'whole-library',
    'contracts', 'cycles', 'witnesses', 'public-cli', 'full-six-matrix',
    'living', 'source-contracts', 'source-freeze', 'exports', 'public-install',
})


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
        if job.get('exit_code') != 0 or job.get('pass') is not True or not job.get('ended_utc'):
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
    evidence=public.get('evidence',{})
    if set(evidence)!=required:raise ValueError('Complete public verification evidence files required')
    reports={}
    for name,row in evidence.items():
        path=Path(row['path']).resolve(strict=True)
        if path==evidence_path.resolve():raise ValueError('Public evidence cannot cite itself')
        if file_sha256(path)!=row.get('sha256'):raise ValueError('Public evidence file changed: '+name)
        reports[name]=json.loads(path.read_text())
        if row.get('pass') is not True:raise ValueError('Public evidence job failed: '+name)
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
    if actual!=expected:raise ValueError('Public matrix must match every frozen mode and canonical dataset')
    full={'cub200':200,'fgvc_aircraft':100,'flowers102':102,'pets37':37,'stanford_dogs':120,'stanford_cars':196}
    for name,mode in expected.items():
        cohort={'cub200','fgvc_aircraft','flowers102'} if name.startswith('source_native') else set(full)
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
