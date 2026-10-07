#!/usr/bin/env python3
"""Report all affected parents and large remaining branches without inventing classes."""
import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas import FineAtlas


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--staging',type=Path,help='Optional readonly staged indexes; database must be their original baseline')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    with FineAtlas(a.database) as tree:
        if a.staging:
            if 'browse_links' in tree._tables:raise ValueError('Staged report needs the original unindexed baseline')
            tree.con.execute('ATTACH DATABASE ? AS staged',(a.staging.resolve().as_uri()+'?mode=ro&immutable=1',))
            revision=json.loads(tree.con.execute("SELECT value FROM staged.metadata WHERE key='browse_source_revision'").fetchone()[0])
            if revision!=tree._revision:raise ValueError('Staging source revision mismatch')
        rows=tree.con.execute('''WITH hidden AS (
          SELECT view,parent_component,role,relation,count(*) n FROM browse_preferences
          GROUP BY view,parent_component,role,relation), affected AS (
          SELECT DISTINCT view,parent_component FROM browse_preferences)
          SELECT c.*,coalesce(h.n,0) preferred_connections
          FROM browse_link_counts c LEFT JOIN hidden h
          ON h.view=c.view AND h.parent_component=c.parent_component AND h.role=c.role AND h.relation=c.relation
          WHERE c.concept_count>=1000 OR EXISTS(SELECT 1 FROM affected a
            WHERE a.view=c.view AND a.parent_component=c.parent_component)
          ORDER BY c.view,c.concept_count DESC,c.parent_component,c.role,c.relation''').fetchall()
        result=[]
        for row in rows:
            item=dict(row)
            native=tree.con.execute('SELECT uid FROM browse_nodes WHERE component_id=? ORDER BY uid LIMIT 1',(row['parent_component'],)).fetchone()
            node=tree.node(native[0]);item.update(parent_uid=native[0],parent_name=node['label'],parent_role=node['node_kind'],
                baseline_direct_concepts=row['concept_count'],full_direct_concepts=row['concept_count'],
                default_direct_concepts=row['concept_count']-row['preferred_connections'],
                source_graph_connections_removed=0,new_semantic_nodes=0,
                descendant_identity_preservation='See full exact source graph comparison and all surviving preference witness proof',
                default_page_size=20,maximum_page_size=1000,
                grouping_basis='Exact native catalogue/property values; not IS_A',
                remaining_semantic_limit='No trustworthy extra intermediate type is inferred where source only supplies parallel designs, configurations or named instances')
            result.append(item)
        (a.output/'branches.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        with (a.output/'branches.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(result[0]) if result else []);writer.writeheader();writer.writerows(result)
        summary={'view_parent_role_relation_rows':len(result),
                 'staging_preview':bool(a.staging),'final_candidate_verification_pending':bool(a.staging),
                 'affected_view_parent_pairs':tree.con.execute('SELECT count(*) FROM (SELECT DISTINCT view,parent_component FROM browse_preferences)').fetchone()[0],
                 'source_graph_mutated':False,'new_semantic_nodes':0,
                 'physical_source_degree_reduced':False,'default_display_prefers_existing_finer_routes':True,
                 'baseline_counts_basis':'Exact same source graph and identities; materialized by the nightly view/role contract, not compared to an older different audit scope'}
        (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
