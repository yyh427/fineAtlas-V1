"""Repair native-class access only on a separately backed-up complete candidate."""
from pathlib import Path
import argparse
import json
from fineatlas.repair_candidate import build_core

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--database', type=Path, required=True)
    p.add_argument('--expected-revision', required=True)
    p.add_argument('--original-annotations', type=Path, required=True)
    p.add_argument('--increment', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = build_core(a.database, a.expected_revision, a.original_annotations, a.increment)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False), flush=True)
