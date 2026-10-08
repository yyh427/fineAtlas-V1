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
c.execute("PRAGMA other.cache_size=-1048576")
out = Path(a.output)
out.parent.mkdir(parents=True, exist_ok=True)
results = {}
def schema_inventory(schema):
    # Include FTS/shadow/runtime-stage table definitions even though their
    # duplicate or runtime row content is intentionally excluded below.
    found = {}
    for name, sql in c.execute(
        "SELECT name,sql FROM " + schema + ".sqlite_master WHERE type='table' "
        "AND name NOT GLOB 'sqlite_*' ORDER BY name"
    ):
        escaped = name.replace('"', '""')
        columns = [list(row) for row in c.execute(
            'PRAGMA ' + schema + '.table_xinfo("' + escaped + '")')]
        found[name] = {'definition': sql, 'columns': columns}
    return found

primary_schema, reproduction_schema = schema_inventory('main'), schema_inventory('other')
schema_result = {
    'primary_only_tables': sorted(set(primary_schema) - set(reproduction_schema)),
    'reproduction_only_tables': sorted(set(reproduction_schema) - set(primary_schema)),
    'different_table_schemas': {
        table: {'primary': primary_schema[table], 'reproduction': reproduction_schema[table]}
        for table in sorted(set(primary_schema) & set(reproduction_schema))
        if primary_schema[table] != reproduction_schema[table]},
    'table_counts': [len(primary_schema), len(reproduction_schema)],
}
schema_result['pass'] = not any(schema_result[key] for key in (
    'primary_only_tables', 'reproduction_only_tables', 'different_table_schemas'))
results['schema_inventory'] = schema_result
def object_inventory(schema):
    return {(kind, name): {'type': kind, 'name': name, 'table_name': table, 'sql': sql}
            for kind, name, table, sql in c.execute(
                'SELECT type,name,tbl_name,sql FROM ' + schema + '.sqlite_master '
                "WHERE name NOT GLOB 'sqlite_*' ORDER BY type,name")}

primary_objects, reproduction_objects = object_inventory('main'), object_inventory('other')
objects_result = {
    'primary_only_objects': [primary_objects[key]
        for key in sorted(set(primary_objects) - set(reproduction_objects))],
    'reproduction_only_objects': [reproduction_objects[key]
        for key in sorted(set(reproduction_objects) - set(primary_objects))],
    'different_object_definitions': [
        {'primary': primary_objects[key], 'reproduction': reproduction_objects[key]}
        for key in sorted(set(primary_objects) & set(reproduction_objects))
        if primary_objects[key] != reproduction_objects[key]],
    'object_counts': [len(primary_objects), len(reproduction_objects)],
}
objects_result['pass'] = not any(objects_result[key] for key in (
    'primary_only_objects', 'reproduction_only_objects', 'different_object_definitions'))
results['schema_objects'] = objects_result
out.write_text(json.dumps(results, indent=2))
if not schema_result['pass'] or not objects_result['pass']:
    raise SystemExit('Reproduction schema/table inventory mismatch; see ' + str(out))
# FTS shadow tables duplicate alias content. Their MATCH behaviour is checked
# by public audits; compare the actual native alias and node records here.
tables = [
    r[0]
    for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*' AND name NOT LIKE 'alias_search%' ORDER BY name"
    )
]
for table in tables:
    if table in ("usability_stages", "browse_build_stages"):
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
