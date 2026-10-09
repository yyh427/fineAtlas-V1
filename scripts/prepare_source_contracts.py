#!/usr/bin/env python3
"""Freeze a read-only full-cohort parent-scope review and explicit genus repairs."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas.structure_source_contracts import prepare_source_contracts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--fixed-review", type=Path)
    p.add_argument("--scope-protections", type=Path)
    p.add_argument("--role-reviews", type=Path)
    p.add_argument("--independent-review-directory", type=Path)
    args = p.parse_args()
    result = prepare_source_contracts(args.database, args.output, args.fixed_review,
                                    args.scope_protections, args.role_reviews, args.independent_review_directory)
    payload = json.loads((args.output / "structure_source_contracts.json").read_text())
    (args.output / "structure_source_contracts_operations.jsonl").write_text("".join(
        json.dumps({"op": "link", **r}, ensure_ascii=False, sort_keys=True) + "\n" for r in payload["repairs"]))
    (args.output / "structure_source_contracts_roles.jsonl").write_text("".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in payload["role_operations"]))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
