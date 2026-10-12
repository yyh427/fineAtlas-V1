"""Apply a reconciled increment to the separately writable complete candidate."""
import argparse
import json
from pathlib import Path
from fineatlas.repair_candidate import integrate_increment

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--database', type=Path, required=True)
    p.add_argument('--expected-revision', required=True)
    p.add_argument('--increment', type=Path, required=True)
    p.add_argument('--source-validation', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = integrate_increment(a.database, a.expected_revision, a.increment, a.source_validation)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False), flush=True)
