#!/usr/bin/env python3
"""Gate stable preparation without changing the completed parent's recipes.

Use all promote_structure_stable.py arguments plus the four required legacy
matrix/adjudication arguments. The existing public-download, independent-build,
source-hash, unchanged-semantic and version-only checks remain mandatory.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from audit_legacy_pair_regressions import audit

ROOT = Path(__file__).resolve().parents[1]


def validate_regressions(args):
    with sqlite3.connect(args.source.resolve().as_uri() + '?mode=ro&immutable=1',
                         uri=True) as con:
        meta = {key: json.loads(value) for key, value in con.execute('SELECT * FROM metadata')}
    report = audit(args.legacy_reference, args.legacy_baseline_matrix,
                   args.legacy_candidate_matrix, args.source_inputs / 'legacy_policies.json',
                   args.legacy_dispositions, args.reports / 'legacy-regressions')
    if not report['pass'] or report['candidate_revision'] != meta['database_revision']:
        raise ValueError('Every fixed-policy loss needs bound independent adjudication; stable promotion blocked')
    frozen = meta['structure_frozen_build_manifest']['inputs']['legacy_policies.json']
    if frozen != report['policy_sha256']:
        raise ValueError('Regression matrix policy differs from the source database freeze')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('legacy-reference', 'legacy-baseline-matrix', 'legacy-candidate-matrix',
                 'legacy-dispositions', 'source', 'source-inputs', 'reports'):
        parser.add_argument('--' + name, type=Path, required=True)
    args, remaining = parser.parse_known_args(argv)
    if not __debug__:
        raise RuntimeError('Optimized Python is forbidden for mandatory structural checks')
    validate_regressions(args)
    # Only remove this wrapper's extra arguments. Delegate all original required
    # options to the unmodified promotion implementation and its existing guards.
    command = [sys.executable, '-B', str(ROOT / 'scripts/promote_structure_stable.py'),
               '--source', str(args.source), '--source-inputs', str(args.source_inputs),
               '--reports', str(args.reports), *remaining]
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
