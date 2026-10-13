"""Bind an independently repaired candidate to a clean, committed SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from fineatlas import FineAtlas, __version__
from fineatlas.repair_candidate import RepairWriter
from fineatlas.task_contract import RunConfig, RULE_VERSION, PRESENTATION_VERSION
import fineatlas


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--database', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    args = p.parse_args()
    root = Path(fineatlas.__file__).resolve().parent
    checkout = root.parents[1]
    def git(*argv):
        return subprocess.run(['git', '-C', str(checkout), *argv], check=True, capture_output=True, text=True).stdout.strip()
    if git('status', '--porcelain'):
        raise ValueError('Commit the repair code before binding the candidate')
    commit = git('rev-parse', 'HEAD')
    manifest = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(root.glob('*.py'))}
    inputs = dict(commit=commit, sdk_version=__version__, sdk_manifest=manifest,
                  evaluation_rules=RULE_VERSION, presentation_rules=PRESENTATION_VERSION,
                  relation_view='unified', target_scope='source_native', admission_mode='reviewed_paths',
                  inference_mode='open', hierarchy_reward_enabled=False)
    inputs.update(scope_rules='grounded-mixed-range-v1',scope_route_mode='mixed')
    with FineAtlas(args.database) as a:
        revision = a._revision
    writer = RepairWriter(args.database, expected_revision=revision)
    writer.release = 'v'+__version__
    if writer.begin('code-contract-seal-' + commit[:12], inputs):
        for key, value in inputs.items():
            writer.meta('repair_code_commit' if key == 'commit' else 'repair_' + key, value)
        receipt = writer.finish({'status': 'SEALED', **inputs})
    else:
        receipt = {'status': 'ALREADY_SEALED', **inputs, 'database_revision': revision}
    writer.c.close()
    config = RunConfig(str(args.database.resolve()), receipt['database_revision'], __version__, commit)
    with FineAtlas(args.database, relation_view=config.relation_view) as a:
        config.validate(a)
    args.config.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2) + '\n')
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'database_revision': config.database_revision, 'code_commit': commit, 'config': str(args.config.resolve())}))


if __name__ == '__main__':
    main()
