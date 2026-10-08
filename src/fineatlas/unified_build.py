"""Replay unified source rules and materialize existing graph caches in RAM.

This uses the existing Migration graph implementation and schema. The output
is still one FineAtlas SQLite database. No parallel hierarchy storage format.
"""
import json
import re
import time

DERIVED_TABLES = ('view_roots','view_paths','view_terminal_connections',
                  'domain_components','domain_members')


def ram_graphs(migration):
    """Run the same full graph checks, then atomically apply only cache diffs.

    The 1.8 taxonomy build spent most time rewriting unchanged domain rows.
    Temporary tables shadow those caches during a full recomputation; primary
    graph rows and source declarations remain in the normal candidate database.
    A failure leaves the candidate marked incomplete and safely resumable.
    """
    m=migration;c=m.c;c.execute('PRAGMA temp_store=MEMORY')
    m.meta('usability_indexes_ready',False);m.meta('unified_ready',False);c.commit()
    for table in DERIVED_TABLES:
        sql=c.execute("SELECT sql FROM main.sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()[0]
        sql=re.sub(r'^CREATE TABLE(?: IF NOT EXISTS)?', 'CREATE TEMP TABLE',sql,flags=re.I)
        c.execute(sql)
    started=time.monotonic();print('FULL GRAPH RECOMPUTATION INTO RAM',flush=True)
    result=m.graphs()
    # graphs() writes metadata last; do not expose it as ready until all of its
    # frozen witnesses and memberships have been committed to persistent tables.
    m.meta('usability_indexes_ready',False);m.meta('unified_ready',False);c.commit()
    stats={}
    for table in DERIVED_TABLES:
        cols=c.execute('PRAGMA main.table_info('+table+')').fetchall()
        names=[r[1] for r in cols];keys=[r[1] for r in sorted(cols,key=lambda x:x[5]) if r[5]]
        key=' AND '.join('n.'+k+' IS o.'+k for k in keys)
        eq=' AND '.join('n.'+k+' IS o.'+k for k in names)
        count=c.execute('SELECT count(*) FROM temp.'+table).fetchone()[0]
        print('PERSIST CACHE DIFF',table,count,flush=True)
        c.execute('BEGIN')
        c.execute('DELETE FROM main.'+table+' AS o WHERE NOT EXISTS(SELECT 1 FROM temp.'+table+' n WHERE '+eq+')')
        removed=c.execute('SELECT changes()').fetchone()[0]
        c.execute('INSERT INTO main.'+table+' SELECT n.* FROM temp.'+table+' n WHERE NOT EXISTS(SELECT 1 FROM main.'+table+' o WHERE '+key+')')
        inserted=c.execute('SELECT changes()').fetchone()[0]
        c.commit();stats[table]={'rows':count,'removed_or_changed':removed,'inserted_or_changed':inserted}
        c.execute('DROP TABLE temp.'+table)
    m.meta('unified_ready',True);m.meta('usability_indexes_ready',True)
    m.meta('default_relation_view','unified');m.meta('supported_relation_views',['strict','taxonomy','membership','unified'])
    m.meta('unified_wordnet_version','3.1');c.commit()
    stats['seconds']=time.monotonic()-started
    (m.out/'ram_graph_persistence.json').write_text(json.dumps(stats,indent=2)+'\n')
    return result
