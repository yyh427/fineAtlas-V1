"""Run a domain query without assuming one result, one parent or connectivity."""

import argparse
from fineatlas import FineAtlas

p = argparse.ArgumentParser()
p.add_argument("database")
p.add_argument("--domain", default="birds")
p.add_argument("--query", default="albatross")
a = p.parse_args()
with FineAtlas(a.database, relation_view="taxonomy") as tree:
    print(tree.browse_domain(a.domain, limit=3))
    candidates = tree.search(a.query, domain=a.domain, limit=3)
    for node in candidates:
        print(node["uid"], node["label"], tree.path_result(node["uid"]))
        print(tree.eligibility(node["uid"], "hierarchy"))
    if len(candidates) >= 2:
        print(tree.lca(candidates[0]["uid"], candidates[1]["uid"]))
        print(tree.distance(candidates[0]["uid"], candidates[1]["uid"]))
