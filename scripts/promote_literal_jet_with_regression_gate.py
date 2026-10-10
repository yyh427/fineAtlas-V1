#!/usr/bin/env python3
"""Require complete fifth and sixth public delivery before unchanged regression promotion."""
import argparse
from pathlib import Path
import subprocess
import sys

from coordinate_literal_jet_delivery import LiteralJetCoordinator, ROOT


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--literal-jet-delivery-config',type=Path,required=True)
    args,remaining=parser.parse_known_args(argv)
    forwarded=argparse.ArgumentParser(add_help=False)
    forwarded.add_argument('--source',type=Path,required=True)
    forwarded.add_argument('--source-inputs',type=Path,required=True)
    original,_=forwarded.parse_known_args(remaining)
    coordinator=LiteralJetCoordinator(args.literal_jet_delivery_config)
    if (Path(coordinator.c['database']).resolve() != original.source.resolve()
            or coordinator.inputs != original.source_inputs.resolve()):
        raise ValueError('Promotion source must be the actual fifth-gated delivery candidate')
    coordinator.validate_public_primary()
    finalized=coordinator.root/'literal_jet_finalized_extension.json'
    if not finalized.exists():
        raise ValueError('Complete original and fifth finalization is required before promotion')
    from coordinate_structure_delivery import read
    from _download import digest
    report=read(finalized)
    if (report.get('pass') is not True or report.get('database_revision') != coordinator.meta['database_revision']
            or report.get('public_extension_sha256') != digest(coordinator.root/'public/checks/literal_jet_public_extension.json')):
        raise ValueError('Actual finalized fifth extension is stale or invalid')
    family_finalized=coordinator.root/'primary_aircraft_finalized_extension.json'
    family=read(family_finalized)
    if (family.get('schema') != 'FINEATLAS_PRIMARY_AIRCRAFT_FINALIZED_EXTENSION_V1'
            or family.get('pass') is not True or family.get('database_revision') != coordinator.meta['database_revision']
            or family.get('public_extension_sha256') != digest(coordinator.root/'public/checks/primary_aircraft_public_extension.json')):
        raise ValueError('Actual finalized sixth extension is stale or invalid')
    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/promote_structure_with_regression_gate.py'),*remaining],check=True)


if __name__=='__main__':main()
