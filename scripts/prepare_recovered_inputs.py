#!/usr/bin/env python3
"""Restore native year configurations to their evidenced broader model scope.

An EPA baseModel key is not a drive/body variant. This source-wide recovery
keeps rejected narrower edges and never promotes configuration membership to ISA.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas._text import norm

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
for e in c.execute(
    "SELECT * FROM edges WHERE source_relation='model_year_body_projection' ORDER BY id"
):
    child = c.execute("SELECT * FROM nodes WHERE uid=?", (e["child_uid"],)).fetchone()
    if child["rank"] not in ("model_year", "configuration"):
        continue
    m = re.search(r"\b((?:19|20)\d{2})\b", child["label"])
    if not m:
        continue
    year = int(m[1])
    provenance = json.loads(e["provenance"])
    ids = (
        provenance.get("evidence_ids", [])
        if isinstance(provenance, dict)
        else provenance
    )
    for eid in ids:
        ev = c.execute("SELECT * FROM evidence WHERE evidence_id=?", (eid,)).fetchone()
        if (
            not ev
            or hashlib.sha256(ev["payload"].encode()).hexdigest()
            != ev["payload_sha256"]
        ):
            continue
        payload = json.loads(ev["payload"])
        candidates = list(payload.get("epa_records", []))
        for r in payload.get("presentations", []):
            fields = r.get("source_fields", {})
            if isinstance(fields, str):
                fields = json.loads(fields)
            candidates.append(
                {
                    "graph_uid": r.get("graph_uid"),
                    "record": {**fields, "base_uid": r.get("base_identity_uid")},
                }
            )
        for r in candidates:
            record = r.get("record", {})
            native = c.execute(
                "SELECT * FROM nodes WHERE uid=?", (r.get("graph_uid"),)
            ).fetchone()
            if not native:
                continue
            fields = json.loads(native["data"])
            # Follow the imported native baseModel field relation: old source
            # hashes may use different normalization and cannot be guessed.
            parents = list(
                c.execute(
                    "SELECT p.* FROM edges e JOIN nodes p ON p.uid=e.parent_uid WHERE e.child_uid=? AND e.source='epa' AND e.source_relation='year+baseModel'",
                    (native["uid"],),
                )
            )
            parent = parents[0] if len(parents) == 1 else None
            parent_uid = parent["uid"] if parent else None
            expected = norm(
                str(fields.get("make", "")) + " " + str(fields.get("baseModel", ""))
            )
            if (
                not parent
                or parent["visibility"] != "ACTIVE"
                or parent["rank"] != "model"
                or norm(parent["label"]) != expected
            ):
                continue
            if (
                str(fields.get("year")) != str(year)
                or str(record.get("model_year")) != str(year)
                or fields.get("baseModel") != record.get("base_model")
            ):
                continue
            key = (child["uid"], parent_uid)
            proof = {
                "native_record_uid": native["uid"],
                "native_record_sha256": hashlib.sha256(
                    native["data"].encode()
                ).hexdigest(),
                "source_evidence_id": eid,
                "year": year,
                "make": fields["make"],
                "base_model": fields["baseModel"],
                "role_basis": "Existing source-backed model-year configuration identity",
                "relationship_basis": "Independent native year/make/baseModel fields; broader model membership only",
                "license": "US federal public-domain source data",
                "narrower_legacy_edge_id": e["id"],
            }
            facts[key] = {
                "uid": child["uid"],
                "label": child["label"],
                "role": "CONFIGURATION",
                "domain": child["domain"],
                "normalize_existing": True,
                "source": "EPA native base-model scope recovery",
                "source_uri": "https://www.fueleconomy.gov/ws/rest/vehicle/"
                + native["uid"].split(":")[-1],
                "proof": proof,
                "parents": [{"uid": parent_uid, "relation": "CONFIGURATION_OF"}],
            }
with open(a.output, "w") as f:
    for key in sorted(facts):
        f.write(json.dumps(facts[key], ensure_ascii=False) + "\n")
Path(a.output).with_suffix(".summary.json").write_text(
    json.dumps(
        {"connections": len(facts), "source_uids": len({k[0] for k in facts})}, indent=2
    )
)
print(len(facts), "broader native connections")
