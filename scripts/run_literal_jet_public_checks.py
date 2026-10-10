"""Execute independent checks on an actual fresh public download; never simulates receipts."""
import argparse,concurrent.futures,datetime,hashlib,json,os,pathlib,subprocess,sys,time,uuid
p=argparse.ArgumentParser()
for k in ('code','python','database','inputs','baseline','reference','inventory','manifest','expected','acceptance','output','primary-build','reproduction-build','legacy-reference','legacy-baseline-matrix','legacy-dispositions','regression-support-registry','primary-snapshots-dir'):p.add_argument('--'+k,type=pathlib.Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
if a.code.resolve()!=pathlib.Path(__file__).resolve().parents[1]:raise RuntimeError('Executor must use its own frozen checkout')
for k,v in vars(a).items():setattr(a,k,v.resolve())
def read(q):return json.loads(q.read_text())
def digest(q):
 h=hashlib.sha256()
 with q.open('rb') as s:
  while b:=s.read(4*1024*1024):h.update(b)
 return h.hexdigest()
def stamp(q):s=q.stat();return [s.st_size,s.st_mtime_ns,s.st_ino]
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(q,x):q.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(a.code/'scripts'))
from resume_structure_repairs import validate_resumed_parent_independence
parent_proof=validate_resumed_parent_independence(a.primary_build,a.reproduction_build)
accepted=read(a.acceptance)
from build_structure_candidate import build_fingerprints
if build_fingerprints(a.inputs)!=accepted['fingerprints']:raise RuntimeError('Public inputs or executable code differ from accepted freeze')
deps=read(a.database.parent.parent/'public_dependency_downloads.json')
if not deps or any(r.get('fresh_download') is not True or r.get('network_request') is not True or r.get('authenticated') is not False or r.get('initial_cached_bytes')!=0 for r in deps.values()):raise RuntimeError('Actual fresh public SDK/input/manifest/expectation downloads required')
download=a.database.parent/'public_download_proof.json';d=read(download)
if not accepted.get('local_all_pass') or not d.get('fresh_download') or d.get('authenticated') is not False:raise RuntimeError('Actual accepted candidate and fresh unauthenticated public download required')
if pathlib.Path(d['database']).resolve()!=a.database or stamp(a.database)!=d['artifact_stamp']:raise RuntimeError('Public artifact mismatch')
for k in ('release','database_revision','database_sha256'):
 if d[k]!=accepted[k]:raise RuntimeError('Accepted public artifact differs: '+k)
env=dict(os.environ);env.pop('PYTHONPATH',None);env.pop('PYTHONOPTIMIZE',None);temp=a.output/'tmp';temp.mkdir(exist_ok=True);env.update(TMPDIR=str(temp),SQLITE_TMPDIR=str(temp),PYTHONPYCACHEPREFIX=str(temp/uuid.uuid4().hex),PYTHONDONTWRITEBYTECODE='1')
def cmd(script,*args):
 if script in {'audit_owned_source_preservation.py','audit_temporal_structure_regression_repairs.py','audit_temporal_complete_subject_scope_repairs.py'}:args=(*args,'--primary-snapshots-dir',a.primary_snapshots_dir)
 return [str(a.python),'-B',str(a.code/'scripts'/script),*map(str,args)]
jobs={
 'resumed-source-preservation':cmd('audit_owned_source_preservation.py','--baseline',a.baseline,'--candidate',a.database,'--inputs',a.inputs,'--reference',a.reference,'--output',a.output/'resumed-source-preservation.json'),
 'installed-sdk':cmd('verify_unified_install.py','--database',a.database,'--manifest',a.manifest,'--expected-validation',a.expected,'--output',a.output/'installed-sdk'),
 'full-six-matrix':cmd('audit_structure_rewards.py','--database',a.database,'--inputs',a.inputs,'--output',a.output/'matrix','--installed-sdk'),
 'living':cmd('audit_living_candidate.py','--database',a.database,'--inputs',a.inputs,'--output',a.output/'living','--installed-sdk'),
 'whole-library':cmd('audit_structure_library.py','--baseline',a.baseline,'--database',a.database,'--inventory',a.inventory,'--output',a.output/'whole-library','--installed-sdk'),
 'public-cli':cmd('audit_browse_cli.py','--database',a.database,'--output',a.output/'public-cli','--installed-sdk'),
 'regression-repairs':cmd('audit_temporal_structure_regression_repairs.py','--database',a.database,'--inputs',a.inputs,'--output',a.output/'regression-repairs.json'),
 'source-contracts':cmd('audit_source_contract_candidate.py','--database',a.database,'--inputs',a.inputs,'--output',a.output/'source-contracts'),
}
sys.path.insert(0,str(a.code/'scripts'))
from structure_delivery_oem_guard import optional_oem_input, validate_oem_receipt
from structure_delivery_delta_registry import required_deltas, validate_delta_receipt
registered=required_deltas(a.inputs,a.code)
from dataclasses import replace
from structure_subject_scope_temporal_contract import require_temporal_subject_receipt
registered=[replace(spec,auditor='audit_temporal_complete_subject_scope_repairs.py') if spec.name=='complete-subject-scope' else spec for spec in registered]
for spec in registered:jobs[spec.name]=cmd(spec.auditor,'--database',a.database,'--inputs',a.inputs,'--output',a.output/(spec.name+'.json'))
oem_input=optional_oem_input(a.inputs,a.code)
if oem_input is not None:jobs['oem-body-scope']=cmd('audit_oem_body_scope_repairs.py','--database',a.database,'--inputs',a.inputs,'--output',a.output/'oem-body-scope.json')
from structure_acceptance_contract import SUPPLEMENTAL_AUDITS, frozen_supplemental_expectations
expected_sources=frozen_supplemental_expectations(a.inputs,accepted['fingerprints'])
if {name:row['expected'] for name,row in accepted.get('supplemental_audits',{}).items()}!=expected_sources:raise RuntimeError('Supplemental local expectations differ from actual frozen inputs')
for name in accepted.get('supplemental_audits',{}):
 spec=SUPPLEMENTAL_AUDITS[name]
 jobs[name]=cmd(spec['script'],'--database',a.database,'--inputs',a.inputs,'--output',a.output/name,'--installed-sdk')
results={};start_stamp=stamp(a.database)
def execute(name,argv):
 print('START ACTUAL PUBLIC CHECK',name,flush=True);start=time.monotonic()
 with (a.output/(name+'.log')).open('w') as stream:code=subprocess.run(argv,env=env,cwd=a.code,stdout=stream,stderr=subprocess.STDOUT).returncode
 row={'command':argv,'exit_code':code,'pass':code==0,'seconds':time.monotonic()-start,'ended_utc':utc()};print('END ACTUAL PUBLIC CHECK',name,code,round(row['seconds'],2),flush=True);return row
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 futures={pool.submit(execute,n,v):n for n,v in jobs.items()}
 for f in concurrent.futures.as_completed(futures):
  n=futures[f]
  try:results[n]=f.result()
  except Exception as e:results[n]={'pass':False,'error':str(e),'exit_code':-1}
  write(a.output/'execution.json',results)
if results['full-six-matrix'].get('pass'):results['exports']=execute('exports',cmd('audit_structure_exports.py','--database',a.database,'--inputs',a.inputs,'--matrix',a.output/'matrix','--output',a.output/'exports','--installed-sdk'))
else:results['exports']={'pass':False,'error':'Complete actual public matrix failed','exit_code':-1}
if results['full-six-matrix'].get('pass'):
 results['legacy-regressions']=execute('legacy-regressions',cmd('audit_portable_legacy_pair_regressions.py','--reference',a.legacy_reference,'--baseline',a.legacy_baseline_matrix,'--candidate',a.output/'matrix','--policy',a.inputs/'legacy_policies.json','--dispositions',a.legacy_dispositions,'--output',a.output/'legacy-regressions','--support-registry',a.regression_support_registry))
else:results['legacy-regressions']={'pass':False,'exit_code':-1,'error':'Public matrix failed'}
write(a.output/'execution.json',results)
if not all(z.get('pass') for z in results.values()) or stamp(a.database)!=start_stamp:raise RuntimeError('Actual public checks failed or downloaded artifact changed')
files={'download':download,'installed-sdk':a.output/'installed-sdk/external_validation.json','full-six-matrix':a.output/'matrix/summary.json','living':a.output/'living/living_candidate_acceptance.json','whole-library':a.output/'whole-library/summary.json','exports':a.output/'exports/summary.json','public-cli':a.output/'public-cli/summary.json','source-contracts':a.output/'source-contracts/summary.json'}
for name in accepted.get('supplemental_audits',{}):files[name]=a.output/name/SUPPLEMENTAL_AUDITS[name]['report']
proof={k:accepted[k] for k in ('release','database_revision','database_sha256')};proof.update(all_pass=True,public_download_unauthenticated=True,matching_installed_sdk=True,ended_utc=utc(),evidence={n:{'path':str(q),'sha256':digest(q),'pass':True} for n,q in files.items()})
sys.path.insert(0,str(a.code/'scripts'));from structure_acceptance_contract import validate_public_evidence
q=a.output/'public_verification.json';validate_public_evidence(proof,accepted,q);write(q,proof)
extension={'schema':'FINEATLAS_RESUMED_PUBLIC_EXTENSION_V1','pass':True,'database':str(a.database),'database_revision':d['database_revision'],'database_sha256':d['database_sha256'],'artifact_stamp':start_stamp,'parent_independence':parent_proof,'ended_utc':utc(),'evidence':{n:{'path':str(q),'sha256':digest(q)} for n,q in {'regression-repairs':a.output/'regression-repairs.json','legacy-regressions':a.output/'legacy-regressions/summary.json','sdk-and-input-downloads':a.database.parent.parent/'public_dependency_downloads.json'}.items()}}
if oem_input is not None:
 validate_oem_receipt(a.output/'oem-body-scope.json',a.database,a.inputs,d['database_revision'],a.code)
 extension['evidence']['oem-body-scope']={'path':str(a.output/'oem-body-scope.json'),'sha256':digest(a.output/'oem-body-scope.json')}
for spec in registered:
 report=a.output/(spec.name+'.json')
 validate_delta_receipt(spec,report,a.database,a.inputs,d['database_revision'],a.code)
 if spec.name=='complete-subject-scope':require_temporal_subject_receipt(report,a.database,a.inputs,d['database_revision'],a.code)
 extension['evidence'][spec.name]={'path':str(report),'sha256':digest(report)}
from structure_owned_source_guard import validate_source_preservation
source_report=a.output/'resumed-source-preservation.json'
validate_source_preservation(source_report,a.database,a.baseline,a.reference,a.inputs,d['database_revision'],a.code)
extension['evidence']['resumed-source-preservation']={'path':str(source_report),'sha256':digest(source_report)}
write(a.output/'resume_public_extension.json',extension)
print('ACTUAL FULL PUBLIC VERIFICATION PASS',q,flush=True)
