"""Bind a local installation to the accepted core code and exact database."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fineatlas import FineAtlas, __version__
from fineatlas.task_contract import RunConfig

REVISION = "563950e014f84b17401a39efc389672e9bb3032e4cc934cf43d0885168cf0002"
CORE_COMMIT = "1cbc84aa57af48f00f3d5ae27b835ae1a8e8efe7"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.database.resolve() == args.output.resolve():
        raise ValueError("Configuration must not overwrite the database")
    config = RunConfig(str(args.database.resolve()), REVISION, __version__, CORE_COMMIT)
    with FineAtlas(args.database, relation_view="unified") as atlas:
        config.validate(atlas)
    args.output.write_text(json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "config": str(args.output.resolve()),
                      "database_revision": REVISION, "sdk_version": __version__}))


if __name__ == "__main__":
    main()
