"""Session-bound model navigation requests; no image gold or source IDs accepted."""
import argparse
import json
from contextlib import ExitStack
from pathlib import Path
from fineatlas.experiment import FineAtlasExperimentTool


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run-config',required=True)
    p.add_argument('--requests',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--private-candidates',type=Path,required=True)
    args=p.parse_args()
    allowed={'session_id','request_id','action','query','domain','task_dataset_context',
             'anchor_handles','target_granularity','limit','cursor','max_depth','node_budget','edge_budget'}
    sessions={};seen=set()
    with ExitStack() as stack:
        output=stack.enter_context(args.output.open('w'));private=stack.enter_context(args.private_candidates.open('w'))
        for line in args.requests.open():
            request=json.loads(line);key=(request.get('session_id'),request.get('request_id'))
            if set(request)-allowed or not all(key) or key in seen:
                raise ValueError('Invalid, duplicate or forbidden gold/UID fields')
            seen.add(key)
            if key[0] not in sessions:
                sessions[key[0]]=stack.enter_context(FineAtlasExperimentTool(args.run_config))
            tool=sessions[key[0]];action=request['action'];dataset=request.get('task_dataset_context')
            if action=='entries':result=tool.entries()
            elif action=='query':result=tool.query(request['query'],dataset=dataset,domain=request.get('domain'),limit=request.get('limit',20))
            elif action in ('scope','expand'):
                options={k:request[k] for k in ('limit','cursor','target_granularity','max_depth','node_budget','edge_budget') if k in request}
                result=tool.scope(request['anchor_handles'],dataset=dataset,text=request.get('query'),expand=action=='expand',**options)
            else:raise ValueError('Unknown navigation action')
            constraints=tool.allowed_choices(result) if action!='entries' else ()
            output.write(json.dumps({'session_id':key[0],'request_id':key[1],
                'feedback':tool.candidate_wire(result),'allowed_choices':constraints,
                'has_more':result.get('has_more',False),'next_cursor':result.get('next_cursor'),
                'retrieval_diagnostics':result.get('retrieval_diagnostics',{})},ensure_ascii=False)+'\n')
            private.write(json.dumps({'session_id':key[0],'request_id':key[1],'result':result},ensure_ascii=False)+'\n')
    print(json.dumps({'requests':len(seen),'sessions':len(sessions),'model_recognition_measured':False}))


if __name__=='__main__':main()
