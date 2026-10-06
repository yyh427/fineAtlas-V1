#!/usr/bin/env python3
import argparse
from pathlib import Path
import sqlite3, sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas.source_adapters import recheck_legacy_terminals

p = argparse.ArgumentParser()
p.add_argument("--database", required=True)
p.add_argument("--output", required=True)
p.add_argument("--legacy-cache")
a = p.parse_args()
c = sqlite3.connect(Path(a.database).resolve().as_uri() + "?mode=ro", uri=True)
c.row_factory = sqlite3.Row
root = Path(a.legacy_cache).resolve() if a.legacy_cache else None


def read(name):
    if not root or not name:
        return None
    original = Path(name)
    # Only cache-relative paths; never read arbitrary external payload paths.
    candidates = [
        root / original.name,
        root / "cars" / original.name,
        root / "horticultural_sources" / original.name,
    ]
    for candidate in candidates:
        if candidate.is_file() and candidate.resolve().is_relative_to(root):
            return candidate.read_bytes()
    return None


print(recheck_legacy_terminals(c, a.output, snapshot_reader=read))
