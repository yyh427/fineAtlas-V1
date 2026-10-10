#!/usr/bin/env python3
"""Fresh installed-SDK code inventory check for the additive public delta gate."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys


def verify_source_inventory(package, prefix, frozen):
    package = Path(package).resolve()
    if 'site-packages' not in package.parts or not package.is_relative_to(Path(prefix).resolve()):
        raise ValueError('Actual isolated installed SDK required')
    wanted={name[len('src/fineatlas/'):]:sha for name,sha in frozen.items() if name.startswith('src/fineatlas/')}
    actual={str(path.relative_to(package)):hashlib.sha256(path.read_bytes()).hexdigest() for path in package.rglob('*.py')}
    if actual != wanted or 'structure_literal_jet_scope_repairs.py' not in actual:
        raise ValueError('Actual installed SDK differs from the complete frozen source inventory')
    return actual


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    import fineatlas
    package=Path(fineatlas.__file__).resolve().parent
    with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as con:
        meta={k:json.loads(v) for k,v in con.execute('SELECT * FROM metadata')}
    actual = verify_source_inventory(package, sys.prefix, meta['structure_frozen_build_manifest']['code'])
    report={'schema':'FINEATLAS_LITERAL_JET_INSTALLED_SDK_V1','pass':True,'database':str(args.database.resolve()),
            'database_revision':meta['database_revision'],'release':meta['release'],'sdk_version':fineatlas.__version__,
            'sdk_package':str(package),'python_executable':sys.executable,'source_modules':actual,'full_source_inventory_checked':True}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
