#!/usr/bin/env python3
"""Compare live explicit rank metadata with the frozen native P105 source."""

import argparse, gzip, hashlib, json, sqlite3
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--database", required=True)
p.add_argument("--native-manifest", required=True)
p.add_argument("--native-relations", required=True)
p.add_argument("--snapshots", required=True)
p.add_argument("--output", required=True)
a = p.parse_args()
c = sqlite3.connect(Path(a.database).resolve().as_uri() + "?mode=ro", uri=True)
c.execute(
    "ATTACH DATABASE ? AS native",
    (Path(a.native_relations).resolve().as_uri() + "?mode=ro",),
)
labels = json.loads(Path(a.native_manifest).read_text())["rank_labels"]
live = {}
D = Path(a.snapshots)
for file in sorted(D.glob("*.json.gz")):
    data = json.loads(gzip.decompress(file.read_bytes()))
    sha = hashlib.sha256(file.read_bytes()).hexdigest()
    for q, item in data.get("entities", {}).items():
        statements = [
            x
            for x in item.get("claims", {}).get("P105", [])
            if x.get("rank") != "deprecated"
        ]
        preferred = [x for x in statements if x.get("rank") == "preferred"]
        values = {
            x.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
            for x in preferred or statements
        }
        values.discard(None)
        if values:
            live[q] = {"values": values, "snapshot": file.name, "source_sha256": sha}
probe = D / "sparql_probe.json"
if probe.exists():
    data = json.loads(probe.read_text())
    sha = hashlib.sha256(probe.read_bytes()).hexdigest()
    for row in data.get("results", {}).get("bindings", []):
        q = row["item"]["value"].rsplit("/", 1)[-1]
        rank = row["rank"]["value"].rsplit("/", 1)[-1]
        item = live.setdefault(
            q, {"values": set(), "snapshot": probe.name, "source_sha256": sha}
        )
        item["values"].add(rank)
count = 0
disagree = 0
with Path(a.output).open("w") as out:
    for q, item in sorted(live.items()):
        native = list(
            c.execute(
                "SELECT value_qid,statement_rank FROM native.relations WHERE child_qid=? AND property='P105' AND statement_rank<>'deprecated'",
                (q,),
            )
        )
        preferred = [r for r in native if r[1] == "preferred"]
        before = {r[0] for r in preferred or native}
        current = item["values"]
        conflict = bool(before and before != current) or len(current) > 1
        status = "CONFLICT_REVIEW" if conflict else "SOURCE_DECLARED"
        proof = {
            "source_entity_id": q,
            "property": "P105",
            "native_rank_qids": sorted(before),
            "live_rank_qids": sorted(current),
            "source_snapshot": item["snapshot"],
            "source_sha256": item["source_sha256"],
            "license": "CC0",
            "basis": "Explicit taxon-rank metadata; preserved-source/live differences stay REVIEW; no IS_A assertion",
        }
        for (uid,) in c.execute(
            "SELECT uid FROM nodes WHERE uid IN (?,?,?)",
            ("wikidata:" + q, "wikidata-v4:" + q, "v26-wikidata:" + q),
        ):
            rank = (
                labels.get(next(iter(current)), next(iter(current))).casefold()
                if len(current) == 1
                else None
            )
            out.write(
                json.dumps(
                    dict(
                        uid=uid,
                        rank=rank,
                        status=status,
                        source="Wikidata current explicit P105",
                        source_uri="https://www.wikidata.org/wiki/" + q,
                        proof=proof,
                    ),
                    ensure_ascii=False,
                )
                + "\n"
            )
            count += 1
            disagree += conflict
print(
    count,
    "rank declarations",
    disagree,
    "preserved/live differences retained as REVIEW",
)
