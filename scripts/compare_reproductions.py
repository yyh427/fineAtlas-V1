#!/usr/bin/env python3
"""Compare the complete schema and every ordinary logical source/public table.

Measured runtime stages and actual SQLite FTS virtual/shadow storage are explicit
exclusions. An ordinary table whose name resembles an FTS table is still checked.
"""
from __future__ import annotations

if not __debug__:
    raise RuntimeError('Independent reproduction checks require Python assertions; optimization is forbidden')

import argparse
import json
from pathlib import Path
import re
import sqlite3

RUNTIME_TABLES = frozenset({'usability_stages', 'browse_build_stages'})
FTS_SHADOW_SUFFIXES = {
    'fts3': frozenset({'content', 'segments', 'segdir', 'docsize', 'stat'}),
    'fts4': frozenset({'content', 'segments', 'segdir', 'docsize', 'stat'}),
    'fts5': frozenset({'data', 'idx', 'content', 'docsize', 'config'}),
}


def quote(value):
    return '"' + value.replace('"', '""') + '"'


def schema_inventory(c, schema):
    found = {}
    for name, sql in c.execute('SELECT name,sql FROM ' + schema + '.sqlite_master '
                              "WHERE type='table' AND name NOT GLOB 'sqlite_*' ORDER BY name"):
        columns = [list(row) for row in c.execute('PRAGMA ' + schema + '.table_xinfo(' + quote(name) + ')')]
        found[name] = {'definition': sql, 'columns': columns}
    return found


def object_inventory(c, schema):
    return {(kind, name): {'type': kind, 'name': name, 'table_name': table, 'sql': sql}
            for kind, name, table, sql in c.execute(
                'SELECT type,name,tbl_name,sql FROM ' + schema + '.sqlite_master '
                "WHERE name NOT GLOB 'sqlite_*' ORDER BY type,name")}


def excluded_tables(c, schema, inventory):
    """Require SQLite's object type AND an actual FTS owner SQL declaration.

    Neither the alias_search name nor a source-supplied naming convention proves
    a shadow table. SQLite table_list classifies ordinary tables as 'table', even
    when their names happen to start with a virtual table's name.
    """
    types = {row[1]: row[2] for row in c.execute('PRAGMA ' + schema + '.table_list')
             if row[0] == schema and row[1] in inventory}
    if set(types) != set(inventory):
        raise ValueError('SQLite table_list must identify the complete actual table inventory')
    excluded = {name: 'EXPLICIT_MEASURED_RUNTIME_STAGE' for name in RUNTIME_TABLES if name in inventory}
    roots = {}
    for name, record in inventory.items():
        spellings = [name, quote(name), '`'+name.replace('`','``')+'`',
                     '['+name+']', "'"+name.replace("'", "''")+"'"]
        table_name = '(?:'+'|'.join(re.escape(value) for value in spellings)+')'
        # Anchor the actual CREATE owner and module, not a USING phrase in a
        # quoted identifier, column expression, or trailing SQL comment.
        pattern = (r'^\s*CREATE\s+VIRTUAL\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?'
                   +table_name+r'\s+USING\s+(?:[\"\'`\[])?(fts[345])(?:[\"\'`\]])?\s*\(')
        match = re.match(pattern, record['definition'] or '', re.I)
        if types[name] == 'virtual' and match:
            roots[name] = match[1].lower()
            excluded[name] = 'SQLITE_FTS_VIRTUAL_' + match[1].upper()
    for name in inventory:
        if types[name] != 'shadow':
            continue
        owners = [root for root, module in roots.items()
                  if any(name == root + '_' + suffix for suffix in FTS_SHADOW_SUFFIXES[module])]
        if len(owners) == 1:
            excluded[name] = 'SQLITE_FTS_SHADOW_OF:' + owners[0]
    return excluded


def compare(database, reproduction, output):
    database, reproduction, output = map(lambda p: Path(p).resolve(), (database, reproduction, output))
    if database == reproduction or database.samefile(reproduction):
        raise ValueError('Independent rebuilds require distinct files and inodes; hardlinks/symlinks are forbidden')
    if output in (database, reproduction) or (output.exists() and any(output.samefile(p) for p in (database, reproduction))):
        raise ValueError('Comparison report must never overwrite an input artifact')
    c = sqlite3.connect(database.as_uri() + '?mode=ro&immutable=1', uri=True)
    try:
        c.execute('PRAGMA query_only=ON')
        c.execute('PRAGMA cache_size=-1048576');c.execute('PRAGMA temp_store=MEMORY')
        c.execute('ATTACH DATABASE ? AS other', (reproduction.as_uri() + '?mode=ro&immutable=1',))
        c.execute('PRAGMA other.cache_size=-1048576')
        output.parent.mkdir(parents=True, exist_ok=True)
        results = {}
        def save():
            output.write_text(json.dumps(results, indent=2) + '\n')
        primary_schema, other_schema = schema_inventory(c, 'main'), schema_inventory(c, 'other')
        schema = {'primary_only_tables': sorted(set(primary_schema)-set(other_schema)),
                  'reproduction_only_tables': sorted(set(other_schema)-set(primary_schema)),
                  'different_table_schemas': {t: {'primary': primary_schema[t], 'reproduction': other_schema[t]}
                      for t in sorted(set(primary_schema)&set(other_schema)) if primary_schema[t] != other_schema[t]},
                  'table_counts': [len(primary_schema), len(other_schema)],
                  'table_names': [sorted(primary_schema), sorted(other_schema)]}
        schema['pass'] = not any(schema[k] for k in ('primary_only_tables','reproduction_only_tables','different_table_schemas'))
        results['schema_inventory'] = schema
        po, ro = object_inventory(c, 'main'), object_inventory(c, 'other')
        objects = {'primary_only_objects': [po[k] for k in sorted(set(po)-set(ro))],
                   'reproduction_only_objects': [ro[k] for k in sorted(set(ro)-set(po))],
                   'different_object_definitions': [{'primary':po[k], 'reproduction':ro[k]}
                       for k in sorted(set(po)&set(ro)) if po[k] != ro[k]],
                   'object_counts': [len(po),len(ro)]}
        objects['pass'] = not any(objects[k] for k in ('primary_only_objects','reproduction_only_objects','different_object_definitions'))
        results['schema_objects'] = objects;save()
        if not schema['pass'] or not objects['pass']:
            raise ValueError('Reproduction schema/table inventory mismatch')
        excluded = excluded_tables(c, 'main', primary_schema)
        if excluded != excluded_tables(c, 'other', other_schema):
            raise ValueError('Actual SQLite FTS/runtime exclusion inventories differ')
        tables = sorted(set(primary_schema)-set(excluded))
        accounting = {'pass': True, 'compared_content_tables': tables,
                      'excluded_content_tables': excluded,
                      'compared_content_count': len(tables), 'excluded_content_count': len(excluded),
                      'actual_table_count': len(primary_schema),
                      'complete_dynamic_inventory_accounting': set(tables)|set(excluded) == set(primary_schema)}
        if not accounting['complete_dynamic_inventory_accounting']:
            raise ValueError('Some ordinary table content is missing from the comparison')
        results['content_inventory'] = accounting;save()
        for table in tables:
            columns = list(c.execute('PRAGMA table_info(' + quote(table) + ')'))
            names = [x[1] for x in columns]
            keys = [x[1] for x in sorted(columns, key=lambda x:x[5]) if x[5]]
            counts = [c.execute('SELECT count(*) FROM ' + s + quote(table)).fetchone()[0] for s in ('','other.')]
            where = "WHERE a.key NOT IN ('usability_view_statistics')" if table == 'metadata' else ''
            if keys:
                join = ' AND '.join('a.'+quote(k)+' IS b.'+quote(k) for k in keys)
                mismatch = ' OR '.join('a.'+quote(k)+' IS NOT b.'+quote(k) for k in names if k not in keys) or '0'
                # Presence is independent of key nullability. A nullable native
                # primary key must not make a present source row look absent.
                marker = '__fineatlas_comparison_presence'
                while marker in names:marker += '_'
                sql = ('SELECT count(*) FROM '+quote(table)+' a LEFT JOIN (SELECT 1 AS '+quote(marker)+',* FROM other.'+
                       quote(table)+') b ON '+join+' '+where+(' AND ' if where else ' WHERE ')+
                       '(b.'+quote(marker)+' IS NULL OR ('+mismatch+'))')
                different = c.execute(sql).fetchone()[0]
            else:
                mismatch = ' OR '.join('a.'+quote(k)+' IS NOT b.'+quote(k) for k in names)
                different = c.execute('SELECT count(*) FROM '+quote(table)+' a LEFT JOIN other.'+quote(table)+
                    ' b ON a.rowid=b.rowid WHERE b.rowid IS NULL OR ('+mismatch+')').fetchone()[0]
            results[table] = {'counts':counts,'different_rows':different,'pass':counts[0]==counts[1] and not different}
            print(table, results[table], flush=True);save()
        values = []
        for s in ('','other.'):
            d = json.loads(c.execute("SELECT value FROM "+s+"metadata WHERE key='usability_view_statistics'").fetchone()[0])
            for view in d.values():view.pop('seconds',None)
            values.append(d)
        results['view_statistics_without_runtime'] = {'pass':values[0]==values[1]};save()
        if not all(r['pass'] for r in results.values()):
            raise ValueError('Reproduction mismatch')
        return results
    finally:
        c.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('database','reproduction','output'):
        p.add_argument('--'+name, required=True)
    args = p.parse_args()
    compare(args.database, args.reproduction, args.output)


if __name__ == '__main__':
    main()
