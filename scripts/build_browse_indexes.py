#!/usr/bin/env python3
"""Build resumable browse indexes on an explicitly separate candidate file."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.browse_index import build_browse_index

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',type=Path,required=True)
    p.add_argument('--reports',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--release')
    a=p.parse_args()
    if a.database.resolve()==a.baseline.resolve() or a.database.samefile(a.baseline):
        raise ValueError('Browse indexes must be built on an independent candidate, not the baseline')
    if not a.database.is_file():raise ValueError('Copy or rebuild a candidate first')
    print(json.dumps(build_browse_index(a.database,a.reports,release=a.release),indent=2))

if __name__=='__main__':main()
