"""Prefer witnessed finer routes while retaining every independent source arc."""
import json


def build_preferences(c):
    c.executescript('''BEGIN;
    CREATE TABLE IF NOT EXISTS browse_preferences(
      view TEXT NOT NULL,parent_component INTEGER NOT NULL,child_component INTEGER NOT NULL,
      role TEXT NOT NULL,relation TEXT NOT NULL,via_component INTEGER NOT NULL,
      first_storage TEXT NOT NULL,first_record_id INTEGER NOT NULL,
      second_storage TEXT NOT NULL,second_record_id INTEGER NOT NULL,
      PRIMARY KEY(view,parent_component,child_component,role,relation)) WITHOUT ROWID;
    CREATE TEMP TABLE IF NOT EXISTS browse_large_parents(view TEXT,parent_component INTEGER,
      PRIMARY KEY(view,parent_component)) WITHOUT ROWID;
    CREATE TEMP TABLE IF NOT EXISTS browse_role_conflicts(component_id INTEGER PRIMARY KEY);
    DELETE FROM browse_preferences;
    DELETE FROM browse_large_parents;
    DELETE FROM browse_role_conflicts;
    INSERT INTO browse_large_parents
      SELECT view,parent_component FROM browse_link_counts
      GROUP BY view,parent_component HAVING sum(concept_count)>=100;
    INSERT OR IGNORE INTO browse_large_parents
      SELECT DISTINCT view,parent_component FROM browse_links WHERE relation='CONFIGURATION_OF';
    INSERT INTO browse_role_conflicts SELECT component_id FROM browse_nodes
      GROUP BY component_id HAVING count(DISTINCT role)>1;
    COMMIT;
    ''')
    has_registry=any(c.execute('SELECT 1 FROM '+r[1]+".sqlite_master WHERE name='domain_registry'").fetchone()
                     for r in c.execute('PRAGMA database_list').fetchall())
    if has_registry:
        roots={u for r in c.execute('SELECT root_uids FROM domain_registry') for u in json.loads(r[0])}
        for uid in sorted(roots):
            row=c.execute('SELECT component_id FROM nodes WHERE uid=?',(uid,)).fetchone()
            if row:
                c.executemany('INSERT OR IGNORE INTO browse_large_parents VALUES(?,?)',
                              [(v,row[0]) for v in ['strict','taxonomy','membership']])
    # Only declared relation compositions qualify. Regulatory and directory
    # relationships are not treated as inferred physical subclass inclusion.
    compositions="""
       (coarse.relation='IS_A' AND first.relation='IS_A' AND second.relation='IS_A')
       OR (coarse.relation IN ('TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT')
           AND first.relation=coarse.relation AND second.relation IN ('IS_A',coarse.relation))
       OR (coarse.relation='CONFIGURATION_OF' AND first.relation='CONFIGURATION_OF'
           AND second.relation='CONFIGURATION_OF')
       OR (coarse.relation='DESIGN_TYPE_OF'
           AND ((first.relation='DESIGN_TYPE_OF' AND second.relation='IS_A')
             OR (first.relation IN ('NATIVE_DESIGN_PARENT','SERIES_MEMBER_OF')
                 AND second.relation='DESIGN_TYPE_OF')))
       OR (coarse.relation='INSTANCE_OF' AND first.relation='INSTANCE_OF' AND second.relation='IS_A')
       OR (coarse.relation='CONFIGURATION_TYPE_OF' AND first.relation='CONFIGURATION_TYPE_OF'
           AND second.relation='IS_A')
       OR (coarse.relation='NATIVE_DESIGN_PARENT' AND first.relation='NATIVE_DESIGN_PARENT'
           AND second.relation='NATIVE_DESIGN_PARENT')
    """
    c.execute(f"""INSERT OR IGNORE INTO browse_preferences
      SELECT coarse.view,coarse.parent_component,coarse.child_component,coarse.role,coarse.relation,
             first.parent_component,first.storage,first.record_id,second.storage,second.record_id
      FROM browse_large_parents large
      CROSS JOIN browse_links coarse ON coarse.view=large.view AND coarse.parent_component=large.parent_component
      CROSS JOIN browse_links first INDEXED BY browse_links_child
             ON first.view=coarse.view AND first.child_component=coarse.child_component
      CROSS JOIN browse_links second ON second.view=coarse.view AND second.parent_component=coarse.parent_component
             AND second.child_component=first.parent_component
      WHERE first.parent_component<>coarse.parent_component
       AND first.parent_component<>coarse.child_component AND first.role=coarse.role
       AND NOT EXISTS(SELECT 1 FROM browse_role_conflicts rc WHERE rc.component_id IN
           (coarse.child_component,coarse.parent_component,first.parent_component))
       AND ({compositions})
      ORDER BY coarse.view,coarse.parent_component,coarse.child_component,coarse.role,coarse.relation,
               first.parent_component,first.record_id,second.record_id""")
    rows=c.execute('SELECT view,role,relation,count(*) FROM browse_preferences GROUP BY view,role,relation').fetchall()
    return {'preferences':sum(r[3] for r in rows),
            'by_view_role_relation':[{'view':r[0],'role':r[1],'relation':r[2],'count':r[3]} for r in rows],
            'basis':'Two surviving admitted source links through a finer intermediate identity; declared relation composition only',
            'source_links_deleted':0,'new_semantic_nodes':0,
            'role_conflict_components_retained':c.execute('SELECT count(*) FROM browse_role_conflicts').fetchone()[0]}
