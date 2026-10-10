#!/usr/bin/env python3
"""Require current nominal local/public proof before unchanged stable preparation."""
from __future__ import annotations

if not __debug__:
    raise RuntimeError('Mandatory nominal scope promotion checks cannot run optimized')

import argparse
from pathlib import Path
import subprocess
import sys

from _download import digest
from coordinate_nominal_design_scope_delivery import NominalDesignScopeCoordinator
from coordinate_structure_delivery import ROOT, read
from structure_nominal_regression_support import require_public_support


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nominal-delivery-config', type=Path, required=True)
    parser.add_argument('--source-name', choices=('primary', 'reproduction'), default='primary')
    args, remaining = parser.parse_known_args(argv)
    forwarded = argparse.ArgumentParser(add_help=False)
    for name in ('source', 'source-inputs', 'primary-build', 'reproduction-build'):
        forwarded.add_argument('--' + name, type=Path, required=True)
    original, _ = forwarded.parse_known_args(remaining)
    coordinator = NominalDesignScopeCoordinator(args.nominal_delivery_config)
    source_key = 'database' if args.source_name == 'primary' else 'reproduction'
    for value, expected in ((original.source, Path(coordinator.c[source_key])),
                            (original.source_inputs, coordinator.inputs),
                            (original.primary_build, Path(coordinator.c['primary_build'])),
                            (original.reproduction_build, Path(coordinator.c['reproduction_build']))):
        if value.resolve() != expected.resolve():
            raise ValueError('Promotion must identify the actually accepted nominal child and final builds')
    coordinator.require_local_nominal_scope()
    coordinator.validate_public_nominal_scope()
    accepted = coordinator.accepted()
    package = read(coordinator.root / 'package/delivery_assets.json')
    require_public_support(package, coordinator.root / 'public', accepted)
    finalized = read(coordinator.root / 'nominal_scope_finalized_extension.json')
    if (finalized.get('schema') != 'FINEATLAS_NOMINAL_SCOPE_FINALIZED_EXTENSION_V1'
            or finalized.get('pass') is not True
            or finalized.get('database_revision') != accepted['database_revision']
            or finalized.get('public_extension_sha256') != digest(coordinator.root / 'public/checks/nominal_scope_public_extension.json')):
        raise ValueError('Actual nominal local/public finalization is missing or stale')
    subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/promote_structure_with_regression_gate.py'),
                    *remaining], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
