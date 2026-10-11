#!/usr/bin/env python3
"""Run every library check with complete, exact Source8/9 evidence schemas."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

if not __debug__:
    raise RuntimeError('Mandatory source/library checks cannot run optimized')

import audit_structure_library as legacy
from structure_library_review_evidence import ReviewedLibraryEvidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'database', 'inventory', 'output', 'inputs', 'complete-owned-audit', 'nominal-scope-audit'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--installed-sdk', action='store_true')
    args = parser.parse_args()
    evidence = ReviewedLibraryEvidence(args.database, args.inputs, args.complete_owned_audit, args.nominal_scope_audit)
    role_original, withdrawal_original = legacy.role_change_evidence, legacy.withdrawal_evidence
    legacy.role_change_evidence = lambda con, uid, old, new: evidence.role_evidence(con, uid, old, new, role_original)
    legacy.withdrawal_evidence = lambda con, path, **kwargs: evidence.withdrawal_evidence(con, path, withdrawal_original, **kwargs)
    try:
        result = legacy.audit(args.baseline, args.database, args.inventory, args.output)
    finally:
        legacy.role_change_evidence, legacy.withdrawal_evidence = role_original, withdrawal_original
    result['complete_source_review_evidence_schemas_checked'] = True
    result['legacy_library_checks_retained'] = True
    legacy.write(args.output / 'summary.json', result)
    print({key: result[key] for key in ('pass', 'failure_count')}, flush=True)
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
