#!/usr/bin/env python3
"""Replay human source adjudications, with literal checks and content hashes.

Reviewed claims are source facts supplied as data, not special SDK answers.
They may normalize role/membership only; this adapter never creates ISA edges.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

p = argparse.ArgumentParser()
p.add_argument("--database", required=True)
p.add_argument("--claims", required=True)
p.add_argument("--sources", required=True)
p.add_argument("--output", required=True)
a = p.parse_args()
c = sqlite3.connect(
    Path(a.database).resolve().as_uri() + "?mode=ro&immutable=1", uri=True
)
c.row_factory = sqlite3.Row
root = Path(a.sources).resolve()
facts = []
for claim in json.loads(Path(a.claims).read_text()):
    snapshots = []
    for source in claim["sources"]:
        file = (root / source["path"]).resolve()
        text = (root / source["text_path"]).resolve()
        if not file.is_relative_to(root) or not text.is_relative_to(root):
            raise ValueError("Source path escapes frozen directory")
        if hashlib.sha256(file.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("Authority source hash differs")
        normalized = " ".join(text.read_text().casefold().split())
        for literal in source["required_literals"]:
            if " ".join(literal.casefold().split()) not in normalized:
                raise ValueError("Reviewed literal absent from source")
        snapshots.append(
            {
                k: v
                for k, v in source.items()
                if k not in ("path", "text_path", "required_literals")
            }
        )
    node = c.execute(
        "SELECT * FROM nodes WHERE uid=?", (claim["subject_uid"],)
    ).fetchone()
    parent = c.execute(
        "SELECT * FROM nodes WHERE uid=?", (claim["parent_uid"],)
    ).fetchone()
    if not node or not parent or parent["visibility"] != "ACTIVE":
        raise ValueError("Reviewed native endpoint missing")
    if claim["relation"] != "CONFIGURATION_OF" or node["rank"] not in (
        "model_year",
        "configuration",
    ):
        raise ValueError("Unsupported reviewed role/claim")
    proof = {
        "adjudication": claim["adjudication"],
        "scope": claim["scope"],
        "source_snapshots": snapshots,
        "source_sha256": snapshots[0]["sha256"],
        "source_role": node["rank"],
        "role_basis": "Existing native configuration identity retained; authority verifies membership in this reusable model scope",
        "year_identity_reverified": claim["year_identity_reverified"],
        "license": "Publisher copyright retained; factual source identifiers and membership only",
    }
    facts.append(
        dict(
            uid=node["uid"],
            label=node["label"],
            role="CONFIGURATION",
            domain=node["domain"],
            normalize_existing=True,
            source="Reviewed primary manufacturer/government model scope",
            source_uri=snapshots[0]["source_uri"],
            proof=proof,
            parents=[{"uid": parent["uid"], "relation": claim["relation"]}],
        )
    )
with open(a.output, "w") as f:
    for fact in facts:
        f.write(json.dumps(fact, ensure_ascii=False) + "\n")
print(len(facts), "reviewed native membership statements")
