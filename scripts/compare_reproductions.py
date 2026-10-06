#!/usr/bin/env python3
"""Compare every logical public/source record in two independent rebuilds.

Runtime stage timestamps/timings and SQLite physical layout are not semantic
records. Database hashes still identify each exact delivered file separately.
"""

import argparse, json, sqlite3
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--database", required=True)
p.add_argument("--reproduction", required=True)
p.add_argument("--output", required=True)
a = p.parse_args()
c = sqlite3.connect(
    Path(a.database).resolve().as_uri() + "?mode=ro&immutable=1", uri=True
)
c.execute("PRAGMA cache_size=-1048576")
c.execute("PRAGMA temp_store=MEMORY")
c.execute(
    "ATTACH DATABASE ? AS other",
    (Path(a.reproduction).resolve().as_uri() + "?mode=ro&immutable=1",),
)
out = Path(a.output)
out.parent.mkdir(parents=True, exist_ok=True)
results = {}
# FTS shadow tables duplicate alias content. Their MATCH behaviour is checked
# by public audits; compare the actual native alias and node records here.
tables = [
    r[0]
    for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alias_search%' ORDER BY name"
    )
]
for table in tables:
    if table == "usability_stages":
        continue
    columns = list(c.execute('PRAGMA table_info("' + table + '")'))
    names = [x[1] for x in columns]
    keys = [x[1] for x in sorted(columns, key=lambda x: x[5]) if x[5]]
    quote = lambda x: '"' + x.replace('"', '""') + '"'
    counts = [
        c.execute("SELECT count(*) FROM " + schema + quote(table)).fetchone()[0]
        for schema in ("", "other.")
    ]
    where = (
        "WHERE a.key NOT IN ('usability_view_statistics')"
        if table == "metadata"
        else ""
    )
    if keys:
        join = " AND ".join("a." + quote(k) + " IS b." + quote(k) for k in keys)
        mismatch = " OR ".join(
            "a." + quote(k) + " IS NOT b." + quote(k) for k in names if k not in keys
        )
        mismatch = "(" + mismatch + ")" if mismatch else "0"
        sql = (
            "SELECT count(*) FROM "
            + quote(table)
            + " a LEFT JOIN other."
            + quote(table)
            + " b ON "
            + join
            + " "
            + where
            + (" AND " if where else " WHERE ")
            + "(b."
            + quote(keys[0])
            + " IS NULL OR "
            + mismatch
            + ")"
        )
        different = c.execute(sql).fetchone()[0]
    else:
        # Native append-only rows have stable IDs/order; alias rows use rowid.
        mismatch = " OR ".join("a." + quote(k) + " IS NOT b." + quote(k) for k in names)
        different = c.execute(
            "SELECT count(*) FROM "
            + quote(table)
            + " a LEFT JOIN other."
            + quote(table)
            + " b ON a.rowid=b.rowid WHERE b.rowid IS NULL OR ("
            + mismatch
            + ")"
        ).fetchone()[0]
    results[table] = {
        "counts": counts,
        "different_rows": different,
        "pass": counts[0] == counts[1] and not different,
    }
    print(table, results[table], flush=True)
    out.write_text(json.dumps(results, indent=2))
# All view statistics must agree after removing measured build durations.
values = []
for schema in ("", "other."):
    d = json.loads(
        c.execute(
            "SELECT value FROM "
            + schema
            + "metadata WHERE key='usability_view_statistics'"
        ).fetchone()[0]
    )
    for view in d.values():
        view.pop("seconds", None)
    values.append(d)
results["view_statistics_without_runtime"] = {"pass": values[0] == values[1]}
out.write_text(json.dumps(results, indent=2))
if not all(r["pass"] for r in results.values()):
    raise SystemExit("Reproduction mismatch")
