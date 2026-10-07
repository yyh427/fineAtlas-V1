#!/usr/bin/env python3
"""Save reproducible real command-line calls and their JSON outputs."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas import FineAtlas


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--browse-index')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    with FineAtlas(a.database,browse_index=a.browse_index) as tree:
        plane=tree.target('fgvc_aircraft','1')['target_uid']
        car=tree.target('stanford_cars','1')['target_uid']
        cases=[['browse-summary','aircraft'],['browse-summary','cars'],
               ['browse-page','aircraft','--limit','3'],
               ['browse-page','hierarchy-type:aircraft-4-engine-1','--node-kind','MODEL','--limit','3'],
               ['browse-groups','hierarchy-type:aircraft-4-engine-1','--group-by','manufacturer','--limit','3'],
               ['browse-groups','hierarchy-type:car-gasoline','--node-kind','CONFIGURATION','--group-by','year','--limit','3'],
               ['browse-path',plane],['browse-path',car],
               ['locate','Cessna','--domain','aircraft','--limit','3'],
               ['locate','Corvette','--domain','cars','--limit','3'],
               ['source-members-page',plane,'--limit','3'],
               ['browse-page','geonames-feature:H.STM','--node-kind','INSTANCE','--limit','3'],
               ['browse-groups','geonames-feature:H.STM','--node-kind','INSTANCE','--group-by','country','--limit','3'],
               ['browse-page','not-a-source:uid']]
    commands=[];records=[]
    for index,case in enumerate(cases):
        cmd=[sys.executable,'-m','fineatlas','--data-dir',a.database,
             *(['--browse-index',a.browse_index] if a.browse_index else []),*case]
        environment={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')+os.pathsep+os.environ.get('PYTHONPATH','')}
        result=subprocess.run(cmd,check=True,capture_output=True,text=True,env=environment)
        value=json.loads(result.stdout)
        if case[-1]=='not-a-source:uid':assert value['status']=='NOT_FOUND'
        elif value.get('status') in ('INDEX_REQUIRED','STALE_INDEX'):raise AssertionError(value)
        if 'items' in value:assert len(value['items'])<=3
        filename=f'{index:02d}-{case[0]}.json';(a.output/filename).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        commands.append(shlex.join(cmd));records.append({'command':cmd,'output':filename,'exit_code':result.returncode})
    (a.output/'commands.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\n'+ '\n'.join(commands)+'\n')
    (a.output/'summary.json').write_text(json.dumps({'all_pass':True,'real_cli_calls':len(records),'records':records},indent=2)+'\n')
    print('REAL CLI JSON CALLS PASS',len(records),flush=True)


if __name__=='__main__':main()
