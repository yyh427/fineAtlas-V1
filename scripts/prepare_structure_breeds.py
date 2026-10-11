#!/usr/bin/env python3
"""Freeze complete VBO host reviews and explicit FCI registry group facts."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.structure_breeds import prepare_structure_breeds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database','vbo','fci','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--host-review',type=Path)
    parser.add_argument('--catalogue-review',type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare_structure_breeds(args.database,args.vbo,args.fci,args.output,
                                             host_review=args.host_review,catalogue_review=args.catalogue_review),indent=2))


if __name__ == '__main__':
    main()
