"""Portable byte-identical regression materials; historical paths are lookup keys."""
from __future__ import annotations
import json
import re
from pathlib import Path
import shutil
import subprocess
import tarfile

from _download import digest, download
from structure_parent_claim_snapshot import write_parent_snapshot
from portable_structure_lineage import package_lineage_members
from coordinate_structure_delivery import require_fresh, read, write

SCHEMA = 'FINEATLAS_PORTABLE_REGRESSION_SUPPORT_V1'
DATASETS = ('cub200','fgvc_aircraft','flowers102','pets37','stanford_dogs','stanford_cars')


def evidence_rows(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            yield value
        for child in value.values():
            yield from evidence_rows(child)
    elif isinstance(value, list):
        for child in value:
            yield from evidence_rows(child)


def safe_member(name):
    path = Path(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name:
        raise ValueError('Unsafe regression support member')
    return path


def extract_support(archive, output, expected):
    output=Path(output); output.mkdir(exist_ok=False,parents=True)
    seen=set()
    process=subprocess.Popen(['zstd','-dc','--',str(archive)],stdout=subprocess.PIPE)
    try:
        with process.stdout as pipe, tarfile.open(fileobj=pipe,mode='r|') as stream:
            for member in stream:
                path=safe_member(member.name)
                if not member.isfile() or member.name not in expected or member.name in seen:
                    raise ValueError('Unexpected, duplicate or nonregular support member')
                target=output/path; target.parent.mkdir(parents=True,exist_ok=True)
                with stream.extractfile(member) as source,target.open('xb') as destination:
                    shutil.copyfileobj(source,destination,4*1024*1024)
                if digest(target)!=expected[member.name]:raise ValueError('Downloaded support member hash differs')
                seen.add(member.name)
        if process.wait()!=0 or seen!=set(expected):raise ValueError('Incomplete downloaded regression support')
    finally:
        if process.stdout and not process.stdout.closed:process.stdout.close()
        if process.poll()is None:process.terminate()
        process.wait()


def package_support(config, output, accepted):
    output = Path(output); output.mkdir(exist_ok=False)
    ledger = Path(config['legacy_dispositions']).resolve()
    members = {'dispositions.json':ledger,'reference.csv':Path(config['legacy_reference']).resolve(),
               'source-row-digests.json':Path(config['reference']).resolve(),
               'domain-inventory.json':Path(config['inventory']).resolve()}
    baseline = Path(config['legacy_baseline_matrix']).resolve()
    for filename in ('legacy-pairs.csv',*[f'legacy-{dataset}-labels.json' for dataset in DATASETS]):
        members['baseline/'+filename] = baseline / filename
    value = read(ledger)
    formal_path=Path(config['formal_baseline_verification_record']).resolve()
    formal=read(formal_path)
    if (formal.get('schema')!='FINEATLAS_FORMAL_PUBLIC_BASELINE_PREREQUISITE_V1'
            or formal.get('all_pass')is not True or formal.get('release')!='v1.10.1'
            or formal.get('actual_public_default_install_verified')is not True
            or formal.get('fresh_download_this_candidate_turn')is not False):
        raise ValueError('Immutable historical formal public baseline verification is required')
    members['formal/formal-baseline-verification.json']=formal_path
    formal_locators={}
    for name,row in formal['preserved_public_evidence'].items():
        path=Path(row['path']).resolve(strict=True)
        if not path.is_file()or digest(path)!=row['sha256']:raise ValueError('Historical formal public proof changed')
        member='formal/'+safe_member(name).name;members[member]=path;formal_locators[row['path']]=member
    local_gate = read(Path(config['delivery_root']) / 'local-legacy-regressions/summary.json')
    if (local_gate.get('pass') is not True or local_gate.get('complete') is not True
            or local_gate.get('candidate_revision') != accepted['database_revision']
            or local_gate.get('dispositions_sha256') != digest(ledger)
            or local_gate.get('baseline_matrix_sha256') != digest(baseline/'legacy-pairs.csv')
            or local_gate.get('reference_export_sha256') != digest(members['reference.csv'])):
        raise ValueError('Runtime support must bind the completed actual local regression gate')
    locators = {}
    for row in evidence_rows(value):
        declared = row['path']; path = Path(declared)
        path = (path if path.is_absolute() else ledger.parent/path).resolve(strict=True)
        if not path.is_file() or path == ledger or digest(path) != row['sha256']:
            raise ValueError('Ledger evidence is absent, self-citing or changed: '+declared)
        # Whole third-party documents require their own explicit source registry
        # and retrieval authority, never automatic archive redistribution.
        if path.suffix.lower() not in {'.json','.jsonl','.csv','.py','.txt','.gz'}:
            raise ValueError('Evidence requires an explicit portable source retrieval/redistribution decision: '+declared)
        member = 'evidence/'+row['sha256']+path.suffix.lower()
        if declared in locators and locators[declared] != member:
            raise ValueError('Conflicting original evidence locator')
        locators[declared] = member; members[member] = path
    members.update(package_lineage_members(config,output,accepted))
    parent_snapshot=output/'parent-assertion-states.jsonl.gz'
    parent_header=write_parent_snapshot(config,parent_snapshot,accepted)
    members['parent-assertion-states.jsonl.gz']=parent_snapshot
    support = {'schema':SCHEMA,'database_revision':accepted['database_revision'],
        'database_sha256':accepted['database_sha256'],'policy_sha256':local_gate['policy_sha256'],
        'candidate_matrix_sha256':local_gate['candidate_matrix_sha256'],
        'dispositions_sha256':digest(ledger),'reference_export_sha256':digest(members['reference.csv']),
        'baseline_matrix_sha256':digest(baseline/'legacy-pairs.csv'),
        'parent_assertion_snapshot_sha256':digest(parent_snapshot),'parent_assertion_snapshot_binding':parent_header,
        'formal_baseline_verification_record_sha256':digest(formal_path),
        'formal_baseline_evidence_locators':formal_locators,
        'evidence_locator_map':locators,
        'files':{name:digest(path) for name,path in sorted(members.items())},
        'original_ledger_bytes_preserved':True,'historical_paths_are_registry_keys_only':True}
    registry_path = output/'support-registry.json'; write(registry_path,support)
    members['support-registry.json'] = registry_path
    expected = {name:digest(path) for name,path in sorted(members.items())}
    tar_path = output/'support.tar'
    with tarfile.open(tar_path,'w') as tar:
        for name,path in sorted(members.items()):
            safe_member(name)
            if digest(path) != expected[name]: raise ValueError('Support input changed while packaging')
            info=tar.gettarinfo(str(path),arcname=name)
            if not info.isfile(): raise ValueError('Support contains a nonregular source')
            info.uid=info.gid=info.mtime=0; info.uname=info.gname=''
            with path.open('rb') as stream: tar.addfile(info,stream)
    archive=output/('fineatlas-'+accepted['release']+'-regression-support.tar.zst')
    subprocess.run(['zstd','-T4','-8','-o',str(archive),'--',str(tar_path)],check=True)
    extract_support(archive,output/'roundtrip',expected); tar_path.unlink()
    manifest=output/'regression_support_manifest.json'
    write(manifest,{'schema':SCHEMA,'database_revision':accepted['database_revision'],
        'database_sha256':accepted['database_sha256'],'original_ledger_sha256':digest(ledger),
        'archive':{'name':archive.name,'bytes':archive.stat().st_size,'sha256':digest(archive)},
        'files':expected,'support_registry_sha256':digest(registry_path)})
    return manifest,archive


class PortableRegressionSupport:
    def __init__(self, registry_path):
        self.path=Path(registry_path).resolve(); self.root=self.path.parent
        self.value=read(self.path)
        if (self.value.get('schema') != SCHEMA or self.value.get('original_ledger_bytes_preserved') is not True
                or self.value.get('historical_paths_are_registry_keys_only') is not True):
            raise ValueError('Portable original-byte regression support registry required')
        for name,expected in self.value['files'].items():
            path=self.root/safe_member(name)
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(self.root) or digest(path)!=expected:
                raise ValueError('Actual portable regression material is absent or changed: '+name)
        if digest(self.root/'dispositions.json') != self.value['dispositions_sha256']:
            raise ValueError('Original regression ledger bytes changed')
        formal_path=self.root/'formal/formal-baseline-verification.json'
        if digest(formal_path)!=self.value['formal_baseline_verification_record_sha256']:
            raise ValueError('Historical formal baseline public prerequisite changed')
        for row in read(formal_path)['preserved_public_evidence'].values():
            member=self.value['formal_baseline_evidence_locators'].get(row['path'])
            if not member or digest(self.root/safe_member(member))!=row['sha256']:
                raise ValueError('Missing portable historical formal public verification proof')

    def evidence(self, row, dispositions):
        if Path(dispositions).resolve() != self.root/'dispositions.json':
            raise ValueError('Public regression auditor must read the portable original ledger')
        declared=row['path']; member=self.value['evidence_locator_map'].get(declared)
        if member is None:
            raise ValueError('Missing explicit support locator; host fallback is forbidden: '+declared)
        path=self.root/safe_member(member)
        if path == self.path or path == Path(dispositions).resolve() or digest(path)!=row['sha256']:
            raise ValueError('Self-citing or changed portable evidence')
        return path


def require_public_support(package, public, accepted):
    public=Path(public); descriptor=package.get('regression_support')
    if not descriptor: raise ValueError('Actual public regression support package is required')
    receipt_path=public/'regression-support-downloads.json'; proof=read(receipt_path)
    for name in ('manifest','archive'):
        require_fresh(proof[name]); asset=descriptor[name]
        path=public/safe_member(asset['name'])
        transfer=proof[name]
        if (transfer.get('sha256')!=asset['sha256']or transfer.get('bytes')!=asset['bytes']
                or transfer.get('http_status')not in(200,206)or not transfer.get('url','').startswith('https://')
                or transfer.get('disposition')!='PUBLIC_NETWORK_DOWNLOAD'):
            raise ValueError('Support transfer receipt must bind the actual HTTPS asset bytes')
        if path.is_symlink()or digest(path)!=asset['sha256'] or path.stat().st_size!=asset['bytes']:
            raise ValueError('Actual fresh support asset differs from package')
    manifest=read(public/descriptor['manifest']['name'])
    if (manifest.get('database_revision')!=accepted['database_revision']
            or manifest.get('database_sha256')!=accepted['database_sha256']
            or manifest.get('original_ledger_sha256')!=descriptor['original_ledger_sha256']):
        raise ValueError('Public support belongs to another accepted candidate')
    support=PortableRegressionSupport(public/'regression-support/support-registry.json')
    actual={'support-registry.json':digest(support.path),**support.value['files']}
    if actual!=manifest['files'] or digest(support.path)!=manifest['support_registry_sha256']:
        raise ValueError('Complete extracted support inventory is required')
    if support.value['database_revision']!=accepted['database_revision'] or support.value['database_sha256']!=accepted['database_sha256']:
        raise ValueError('Extracted support is bound to a different candidate')
    if support.value['dispositions_sha256']!=manifest['original_ledger_sha256']:
        raise ValueError('Original accepted regression ledger binding was lost')
    return support,receipt_path


def download_public_support(package, public, base_url, accepted):
    public=Path(public); descriptor=package.get('regression_support')
    if not descriptor: raise ValueError('Packaged regression support is absent')
    receipt=public/'regression-support-downloads.json'
    if receipt.exists(): return require_public_support(package,public,accepted)
    destination=public/'regression-support'
    if destination.exists(): raise ValueError('Preserve incomplete public support; investigate before resuming')
    proofs={}
    for name in ('manifest','archive'):
        asset=descriptor[name]; target=public/safe_member(asset['name'])
        if target.exists() or target.with_name(target.name+'.download').exists():
            raise ValueError('Fresh support download cannot reuse unreceipted host/cache material')
        proofs[name]=download(base_url.rstrip('/')+'/'+asset['name'],target,asset)
        require_fresh(proofs[name])
    manifest=read(public/descriptor['manifest']['name'])
    if manifest['archive']!={k:descriptor['archive'][k] for k in ('name','bytes','sha256')}:
        raise ValueError('Public support archive manifest differs from accepted package')
    extract_support(public/descriptor['archive']['name'],destination,manifest['files'])
    write(receipt,proofs)
    return require_public_support(package,public,accepted)
