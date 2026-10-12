"""CPU-only experimental query/constraint adapter; never reads evaluation gold.

Input JSONL: item_id, query, optional domain and task_dataset_context. Gold labels
and source IDs belong exclusively to a separate private evaluation process.
Output has model-facing feedback and returned-choice constraints only.
"""
import argparse
import json
from pathlib import Path
from fineatlas.experiment import FineAtlasExperimentTool
from fineatlas.task_contract import RunConfig


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-config', type=Path, required=True)
    p.add_argument('--queries', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--private-candidates', type=Path, required=True)
    p.add_argument('--limit', type=int, default=10)
    args = p.parse_args()
    config = RunConfig.read(args.run_config)
    allowed = {'item_id', 'query', 'domain', 'task_dataset_context'}
    seen = set()
    with FineAtlasExperimentTool(config) as tool, args.queries.open() as source, args.output.open('w') as output, args.private_candidates.open('w') as private:
        for line in source:
            row = json.loads(line)
            if set(row) - allowed or not isinstance(row.get('query'), str) or not row.get('item_id') or row['item_id'] in seen:
                raise ValueError('Duplicate/invalid item or forbidden gold/UID query fields')
            seen.add(row['item_id'])
            result = tool.query(row['query'], domain=row.get('domain'), dataset=row.get('task_dataset_context'), limit=args.limit)
            constraints = tool.allowed_choices(result)
            output.write(json.dumps({'item_id': row['item_id'], 'feedback': tool.candidate_wire(result),
                                     'allowed_choices': constraints, 'retrieval_diagnostics': {
                                         k: result['retrieval_diagnostics'][k] for k in ('scan_complete', 'incomplete_streams')},
                                     'run_config': config.to_dict()}, ensure_ascii=False) + '\n')
            private.write(json.dumps({'item_id': row['item_id'], 'result': result}, ensure_ascii=False) + '\n')
    print(json.dumps({'processed': len(seen), 'training_started': False, 'inference_mode': config.inference_mode}))


if __name__ == '__main__':
    main()
