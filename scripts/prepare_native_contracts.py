#!/usr/bin/env python3
"""Normalize source-field relations without mistaking model references for ISA.

EPA year+baseModel/year+model and model+baseModel declare product
configuration membership, not class subsumption. Raw source declarations stay
in original_relation/provenance; reviewed typed statements retain their field keys.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3

p = argparse.ArgumentParser()
p.add_argument("--database", required=True)
p.add_argument("--output", required=True)
a = p.parse_args()
c = sqlite3.connect(
    Path(a.database).resolve().as_uri() + "?mode=ro&immutable=1", uri=True
)
c.row_factory = sqlite3.Row
facts = {}
reviews = []
for row in c.execute("SELECT * FROM nodes WHERE uid GLOB 'epa:[0-9]*' ORDER BY uid"):
    data = json.loads(row["data"])
    if not all(data.get(k) for k in ("id", "make", "model", "baseModel", "year")):
        reviews.append(
            {"uid": row["uid"], "reason": "Incomplete native EPA identity fields"}
        )
        continue
    if not str(data["year"]).isdigit() or str(data["id"]) != row["uid"].split(":")[-1]:
        reviews.append(
            {"uid": row["uid"], "reason": "Native record identity/year mismatch"}
        )
        continue
    year = int(data["year"])
    if not 1886 <= year <= 2200:
        raise ValueError("Invalid native manufacturing year")
    edges = list(
        c.execute(
            "SELECT * FROM edges WHERE child_uid=? AND source IN ('epa','epa_identity_v2') AND source_relation IN ('year+baseModel','year+model')",
            (row["uid"],),
        )
    )
    for e in edges:
        parent = c.execute(
            "SELECT * FROM nodes WHERE uid=?", (e["parent_uid"],)
        ).fetchone()
        field = "baseModel" if e["source_relation"] == "year+baseModel" else "model"
        expected = (data["make"] + " " + data[field]).casefold()
        if not parent or parent["label"].casefold() != expected:
            reviews.append(
                {"edge_id": e["id"], "reason": "Native model-field endpoint differs"}
            )
            continue
        proof = {
            "native_record_id": data["id"],
            "native_record_sha256": hashlib.sha256(row["data"].encode()).hexdigest(),
            "year": year,
            "make": data["make"],
            "model": data["model"],
            "baseModel": data["baseModel"],
            "source_relation": e["source_relation"],
            "native_parent_field": field,
            "role_basis": "EPA native year/make/model fields describe reusable product configuration",
            "relationship_basis": "Native configuration references model; not asserted subset classification",
            "license": "US federal public-domain data",
        }
        key = (row["uid"], parent["uid"])
        facts[key] = dict(
            uid=row["uid"],
            label=row["label"],
            role="CONFIGURATION",
            domain=row["domain"],
            normalize_existing=True,
            source="EPA normalized native fields",
            source_uri="https://www.fueleconomy.gov/ws/rest/vehicle/" + data["id"],
            proof=proof,
            parents=[{"uid": parent["uid"], "relation": "CONFIGURATION_OF"}],
            normalize_edge_ids=[e["id"]],
        )
        if field != "model":
            continue
        for variant_edge in c.execute(
            "SELECT * FROM edges WHERE child_uid=? AND source='epa_identity_v2' AND source_relation='model+baseModel'",
            (parent["uid"],),
        ):
            base = c.execute(
                "SELECT * FROM nodes WHERE uid=?", (variant_edge["parent_uid"],)
            ).fetchone()
            if (
                not base
                or base["label"].casefold()
                != (data["make"] + " " + data["baseModel"]).casefold()
            ):
                reviews.append(
                    {
                        "edge_id": variant_edge["id"],
                        "reason": "Native baseModel differs",
                    }
                )
                continue
            key = (parent["uid"], base["uid"])
            facts[key] = dict(
                uid=parent["uid"],
                label=parent["label"],
                role="CONFIGURATION",
                domain=parent["domain"],
                normalize_existing=True,
                source="EPA normalized native fields",
                source_uri="https://www.fueleconomy.gov/ws/rest/vehicle/" + data["id"],
                proof={**proof, "source_relation": "model+baseModel"},
                parents=[{"uid": base["uid"], "relation": "CONFIGURATION_OF"}],
                normalize_edge_ids=[variant_edge["id"]],
            )
with open(a.output, "w") as f:
    for key in sorted(facts):
        f.write(json.dumps(facts[key], ensure_ascii=False) + "\n")
summary = {
    "typed_connections": len(facts),
    "normalized_source_uids": len({x[0] for x in facts}),
    "original_edge_ids": len(
        {i for r in facts.values() for i in r["normalize_edge_ids"]}
    ),
    "review": reviews,
}
Path(a.output).with_suffix(".summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2)
)
print({k: v if k != "review" else len(v) for k, v in summary.items()})
