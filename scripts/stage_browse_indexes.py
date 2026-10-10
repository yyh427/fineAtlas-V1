#!/usr/bin/env python3
"""Build derived indexes in RAM, then persist one standalone staging artifact."""

if not __debug__:
    raise RuntimeError("Optimized Python is forbidden for mandatory structural checks")

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.browse_index import build_browse_index

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reports',type=Path,required=True)
    p.add_argument('--release',default='v1.9.0-night-review')
    a=p.parse_args()
    if not a.source.is_file() or a.output.exists():raise ValueError('Source missing or staging output already exists')
    if a.source.resolve()==a.output.resolve():raise ValueError('Cannot overwrite source')
    print(json.dumps(build_browse_index(a.output,a.reports,release=a.release,source=a.source),indent=2))

if __name__=='__main__':main()
