"""Precompute catalogue counts for large parents; query pages remain bounded."""


def build_group_cache(c):
    c.executescript('''BEGIN;
      CREATE TABLE IF NOT EXISTS browse_group_cache(
        view TEXT NOT NULL,parent_component INTEGER NOT NULL,mode TEXT NOT NULL,
        role TEXT NOT NULL,facet TEXT NOT NULL,value TEXT NOT NULL,concepts INTEGER NOT NULL,
        PRIMARY KEY(view,parent_component,mode,role,facet,value)) WITHOUT ROWID;
      CREATE TABLE IF NOT EXISTS browse_cached_parents(
        view TEXT NOT NULL,parent_component INTEGER NOT NULL,
        PRIMARY KEY(view,parent_component)) WITHOUT ROWID;
      DELETE FROM browse_group_cache;
      DELETE FROM browse_cached_parents;
      INSERT INTO browse_cached_parents SELECT view,parent_component FROM browse_link_counts
        GROUP BY view,parent_component HAVING sum(concept_count)>=100;
      COMMIT;''')
    totals={}
    for mode in ['full','preferred']:
        preferred=" AND NOT EXISTS(SELECT 1 FROM browse_preferences bp WHERE bp.view=b.view AND bp.parent_component=b.parent_component AND bp.child_component=b.child_component AND bp.role=b.role AND bp.relation=b.relation)" if mode=='preferred' else ''
        c.execute(f"""INSERT INTO browse_group_cache
          SELECT b.view,b.parent_component,?,b.role,f.facet,f.value,count(DISTINCT b.child_component)
          FROM browse_cached_parents cp
          CROSS JOIN browse_links b ON b.view=cp.view AND b.parent_component=cp.parent_component
          CROSS JOIN browse_facets f ON f.component_id=b.child_component
          CROSS JOIN browse_nodes n ON n.uid=f.uid
          WHERE (n.view_mask & CASE b.view WHEN 'strict' THEN 1 WHEN 'taxonomy' THEN 2 WHEN 'unified' THEN 8 ELSE 4 END)<>0
          {preferred}
          GROUP BY b.view,b.parent_component,b.role,f.facet,f.value""",(mode,))
        totals[mode]=c.execute('SELECT changes()').fetchone()[0]
    return {'rows_by_mode':totals,'cached_view_parent_pairs':c.execute('SELECT count(*) FROM browse_cached_parents').fetchone()[0],
            'counts_are_distinct_identities_per_role':True,'catalogue_groups_are_not_graph_nodes':True}
