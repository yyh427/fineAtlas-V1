#!/usr/bin/env python3
"""Rebuild into a new database, verifying the frozen baseline first."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(16 * 1024 * 1024):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--database", type=Path, required=True)
    p.add_argument("--reports", type=Path, required=True)
    a = p.parse_args()
    if a.database.exists():
        raise ValueError("Output already exists; choose a new database")
    if a.baseline.resolve() == a.database.resolve():
        raise ValueError("Cannot overwrite baseline")
    manifest = json.loads((a.inputs / "baseline.json").read_text())
    actual = sha(a.baseline)
    if actual != manifest["database_sha256"]:
        raise ValueError("Protected baseline SHA256 mismatch")
    a.database.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(a.baseline, a.database)
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("migrate_review.py")),
            "--database",
            str(a.database),
            "--inputs",
            str(a.inputs),
            "--reports",
            str(a.reports),
        ],
        check=True,
    )
    print(
        json.dumps(
            {
                "database": str(a.database),
                "sha256": sha(a.database),
                "baseline_sha256": actual,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
