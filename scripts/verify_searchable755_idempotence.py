"""Replay journaled operations without allowing semantic or revision drift."""
import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from fineatlas.repair_candidate import apply_scope_operations


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);r=p.parse_args().root
    saved=r/'checkpoints/initial_application_receipts.json'
    if not saved.exists():
        saved.write_text(json.dumps({p.name:json.loads(p.read_text()) for p in (r/'reports').glob('*_apply.json')},indent=2))
    def revision():
        with sqlite3.connect('file:'+str(r/'artifacts/fineatlas.sqlite')+'?mode=ro',uri=True) as c:
            return json.loads(c.execute("SELECT value FROM metadata WHERE key='database_revision'").fetchone()[0])
    before=revision();results=[]
    commands=[['build_searchable755_graph.py','--apply'],['finalize_searchable755_scope.py'],
        ['prepare_primary_navigation755.py','--apply'],['record_identity_investigations755.py'],
        ['connect_confirmed_dog_types755.py','--apply']]
    for script,*options in commands:
        args=[sys.executable,str(Path(__file__).parent/script),'--root',str(r),*options]
        done=subprocess.run(args,capture_output=True,text=True)
        results.append({'args':args,'exit':done.returncode,'output':done.stdout[-1800:],'error':done.stderr[-1800:]})
        print(script,done.returncode,done.stdout[-180:],flush=True)
        if done.returncode:break
    if not any(x['exit'] for x in results):
        result=apply_scope_operations(r/'artifacts/fineatlas.sqlite',revision(),r/'inputs/source_alignment_operations.json',package_id='searchable755-alignment-contract-v1')
        results.append({'package':'searchable755-alignment-contract-v1','result':result})
    after=revision();passed=before==after and len(results)==6 and not any(x.get('exit',0) for x in results)
    (r/'reports/round_idempotence_acceptance.json').write_text(json.dumps({'passed':passed,
        'revision_unchanged':before==after,'before':before,'after':after,'replays':results},indent=2))
    print('idempotence',passed)
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
