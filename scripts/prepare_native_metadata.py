#!/usr/bin/env python3
"""Extract existing native IDs, metadata and explicit taxon-rank statements.

This repairs source-field extraction across all Wikidata namespaces. It does
not manufacture taxonomy arcs, species identities or product-model roles.
"""

import argparse, gzip, hashlib, json, sqlite3
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--database", required=True)
p.add_argument("--entities", required=True)
p.add_argument("--relations", required=True)
p.add_argument("--output", required=True)
a = p.parse_args()
c = sqlite3.connect(Path(a.database).resolve().as_uri() + "?mode=ro", uri=True)
c.row_factory = sqlite3.Row
c.execute("PRAGMA temp_store=MEMORY")
c.execute("PRAGMA cache_size=-1048576")
for alias, file in [("native", a.entities), ("grades", a.relations)]:
    c.execute(
        "ATTACH DATABASE ? AS " + alias, (Path(file).resolve().as_uri() + "?mode=ro",)
    )
c.execute("CREATE TEMP TABLE qids(qid TEXT PRIMARY KEY,uids TEXT) WITHOUT ROWID")
c.execute(
    "INSERT INTO qids SELECT substr(uid,instr(uid,':')+1),json_group_array(uid) FROM nodes WHERE visibility='ACTIVE' AND (uid LIKE 'wikidata:%' OR uid LIKE 'wikidata-v4:%' OR uid LIKE 'v26-wikidata:%') GROUP BY 1"
)
rank_labels = {
    r["value_qid"]: r["label"]
    for r in c.execute(
        "SELECT DISTINCT r.value_qid,e.label FROM grades.relations r JOIN native.entities e ON e.qid=r.value_qid WHERE r.property='P105'"
    )
}
c.execute("CREATE TEMP TABLE ranks(qid TEXT PRIMARY KEY,statements TEXT) WITHOUT ROWID")
c.execute(
    "INSERT INTO ranks SELECT r.child_qid,json_group_array(json_object('rank_qid',r.value_qid,'statement_rank',r.statement_rank)) FROM grades.relations r JOIN qids q ON q.qid=r.child_qid WHERE r.property='P105' GROUP BY 1"
)
count = 0
with_rank = 0
with gzip.GzipFile(filename=str(a.output), mode="wb", mtime=0) as f:
    for row in c.execute(
        "SELECT q.qid,q.uids,e.label,e.description,r.statements FROM qids q LEFT JOIN native.entities e ON e.qid=q.qid LEFT JOIN ranks r ON r.qid=q.qid ORDER BY q.qid"
    ):
        claims = json.loads(row["statements"] or "[]")
        usable = [x for x in claims if x["statement_rank"] != "deprecated"]
        preferred = [x for x in usable if x["statement_rank"] == "preferred"]
        effective = preferred or usable
        ranks = sorted(
            {
                rank_labels.get(x["rank_qid"], x["rank_qid"]).casefold()
                for x in effective
            }
        )
        item = dict(
            qid=row["qid"],
            uids=json.loads(row["uids"]),
            label=row["label"],
            description=row["description"],
            rank_statements=claims,
            effective_ranks=ranks,
        )
        f.write(
            (
                json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
            ).encode()
        )
        count += 1
        with_rank += bool(ranks)
        if count % 100000 == 0:
            print("METADATA", count, with_rank, flush=True)
manifest = {
    "source_uri": "https://www.wikidata.org/wiki/Wikidata:Database_download",
    "license": "CC0",
    "records": count,
    "rank_records": with_rank,
    "rank_labels": rank_labels,
    "metadata": dict(c.execute("SELECT * FROM grades.metadata")),
    "output_sha256": hashlib.sha256(Path(a.output).read_bytes()).hexdigest(),
}
Path(a.output).with_suffix(".manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2)
)
print(
    json.dumps(
        {k: v for k, v in manifest.items() if k not in ("rank_labels", "metadata")}
    )
)
