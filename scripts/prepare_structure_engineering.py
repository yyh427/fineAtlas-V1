#!/usr/bin/env python3
"""Freeze source-native engineering repairs without changing the source DB."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas.structure_engineering import prepare_structure_engineering


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--baseline-labels", type=Path)
    parser.add_argument("--conflict-components", type=Path)
    parser.add_argument("--reviewed-roles", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare_structure_engineering(args.database, args.annotations, args.output,
        sources=args.sources, baseline_labels=args.baseline_labels,
        conflict_components=args.conflict_components, reviewed_roles=args.reviewed_roles), indent=2))


if __name__ == "__main__":
    main()
