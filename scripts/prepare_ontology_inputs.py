#!/usr/bin/env python3
"""Read the VBO ontology and native OpenTree external-identifier mappings.

Only live biological classes under imported NCBI taxa are included. Status,
country, foundation-stock and phenotype properties do not become IS_A. A
publisher-scoped breed identifier stays distinct from a scientific species.
"""

import argparse, collections, hashlib, json, re, sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas._text import norm

p = argparse.ArgumentParser()
p.add_argument("--sources", required=True)
p.add_argument("--database", required=True)
p.add_argument("--output", required=True)
a = p.parse_args()
O = Path(a.sources) / "vbo"
path = O / "vbo.json"
g = json.loads(path.read_text())["graphs"][0]
sha = hashlib.sha256(path.read_bytes()).hexdigest()
c = sqlite3.connect(Path(a.database).resolve().as_uri() + "?mode=ro", uri=True)
c.row_factory = sqlite3.Row
license = next(
    x["val"]
    for x in g["meta"]["basicPropertyValues"]
    if x["pred"] == "http://purl.org/dc/terms/license"
)
if license != "https://creativecommons.org/licenses/by/4.0/":
    raise ValueError("Source licence changed; inspect before importing")
source_nodes = {
    n["id"]: n
    for n in g["nodes"]
    if n.get("type") == "CLASS" and not n.get("meta", {}).get("deprecated", False)
}
parents = collections.defaultdict(list)
children = collections.defaultdict(list)
for e in g["edges"]:
    if e["pred"] == "is_a" and e["sub"] in source_nodes and e["obj"] in source_nodes:
        parents[e["sub"]].append(e["obj"])
        children[e["obj"]].append(e["sub"])
seeds = {u for u in source_nodes if re.search(r"/NCBITaxon_\d+$", u)}
eligible = set(seeds)
queue = list(seeds)
for uid in queue:
    for child in children[uid]:
        if child not in eligible:
            eligible.add(child)
            queue.append(child)


def uid(value):
    return "vbo:" + value.rsplit("/", 1)[-1]


def rank(n):
    for value in n.get("meta", {}).get("basicPropertyValues", []):
        if value["pred"].endswith("has_rank"):
            return value["val"].rsplit("_", 1)[-1]
    return "breed" if "/VBO_" in n["id"] else "no rank"


def names(n):
    return [n["lbl"]] + [
        x["val"]
        for x in n.get("meta", {}).get("synonyms", [])
        if x["pred"] == "hasExactSynonym"
    ]


# Catalogue-scoped breed matching requires a unique registered designation,
# the same declared animal scope and explicit existing breed role. A shared
# raw name alone is never enough (country/registry variants remain separate).
registered = collections.defaultdict(set)
for own in eligible:
    n = source_nodes[own]
    if "/VBO_" not in own or rank(n) != "breed":
        continue
    species = [
        p
        for p in parents[own]
        if "/NCBITaxon_" in p and rank(source_nodes[p]) in ("species", "subspecies")
    ]
    if len(species) != 1:
        continue
    for synonym in n.get("meta", {}).get("synonyms", []):
        if synonym["pred"] == "hasExactSynonym" and synonym.get(
            "synonymType", ""
        ).endswith("most_common_name"):
            registered[(norm(synonym["val"]), species[0])].add(own)
identities = collections.defaultdict(list)
review = []
mapping_count = 0
mapping_fail = []
for (name, species), vals in registered.items():
    if len(vals) != 1:
        continue
    animal = source_nodes[species]["lbl"]
    scope_names = {
        norm(x) for x in names(source_nodes[species]) if not re.search(r"[<>()]", x)
    }
    common = [x for x in scope_names if " " not in x and x.isalpha() and len(x) > 2]
    if not common:
        continue
    rows = list(
        c.execute(
            "SELECT DISTINCT n.uid,n.label,n.description,n.rank FROM aliases a CROSS JOIN nodes n WHERE a.alias=? AND n.uid=a.uid AND n.uid GLOB 'wikidata*'",
            (name,),
        )
    )
    for row in rows:
        if norm(row["label"]) != name or "breed" not in row["description"].casefold():
            continue
        if not any(
            re.search(r"\b" + re.escape(word) + r"\b", row["description"], re.I)
            for word in common
        ):
            continue
        own = next(iter(vals))
        identities[own].append(
            {
                "uid": row["uid"],
                "basis": "Unique VBO most-common registered breed designation, independently declared source breed role and matching native animal scope",
                "registered_designation": name,
                "native_taxon_uri": species,
                "native_source_breed_label": source_nodes[own]["lbl"],
                "existing_label": row["label"],
                "existing_breed_definition": row["description"],
            }
        )
# Parents must exist before relation replay, so emit all nodes first, then arcs.
facts = []
for own in sorted(eligible):
    n = source_nodes[own]
    ident_links = identities.get(own, [])
    if own in seeds:
        nid = own.rsplit("_", 1)[-1]
        mapping = O / "ott" / (nid + ".json")
        if mapping.exists():
            m = json.loads(mapping.read_text())
            target = "ott:" + str(m["ott_id"])
            native = c.execute(
                "SELECT uid,rank,visibility,label FROM nodes WHERE uid=?", (target,)
            ).fetchone()
            if (
                native
                and native["visibility"] == "ACTIVE"
                and "ncbi:" + nid in m.get("tax_sources", [])
                and not m.get("is_suppressed")
                and rank(n) == m.get("rank") == native["rank"]
            ):
                ident_links = [
                    {
                        "uid": target,
                        "basis": "OpenTree native API explicitly maps this NCBI taxon identifier to this OTT identifier",
                        "native_external_id": "ncbi:" + nid,
                        "native_mapping": m,
                        "mapping_source_uri": "https://api.opentreeoflife.org/v3/taxonomy/taxon_info",
                        "mapping_snapshot_sha256": hashlib.sha256(
                            mapping.read_bytes()
                        ).hexdigest(),
                    }
                ]
                mapping_count += 1
            else:
                mapping_fail.append(
                    {
                        "native_id": nid,
                        "reason": "Mapping endpoint absent, archived, suppressed or inconsistent in native taxonomic rank",
                    }
                )
        else:
            mapping_fail.append(
                {
                    "native_id": nid,
                    "reason": "Native identifier API failed; retained independent source taxonomy",
                }
            )
    proof = {
        "native_ontology_uri": own,
        "native_label": n["lbl"],
        "native_rank": rank(n),
        "source_role": "OWL biological class",
        "ontology_version": g["meta"]["version"],
        "source_sha256": sha,
        "license": "CC-BY-4.0",
        "attribution": "Monarch Initiative, Vertebrate Breed Ontology; Mullen et al. (2025), doi:10.1111/jvim.70133",
        "biological_scope": "Native asserted ancestor in imported NCBI taxonomy; statuses/countries excluded",
        "definition": n.get("meta", {}).get("definition", {}).get("val", ""),
    }
    facts.append(
        {
            "uid": uid(own),
            "label": n["lbl"],
            "role": "CLASS",
            "domain": "vertebrate_breeds" if "/VBO_" in own else "biological_taxonomy",
            "source": "Vertebrate Breed Ontology",
            "source_uri": own,
            "proof": proof,
            "parents": [],
            "aliases": names(n),
            "identity_links": ident_links,
        }
    )
for own in sorted(eligible):
    ps = [
        {"uid": uid(p), "relation": "IS_A", "native_relation": "RDFS_SUBCLASS_OF"}
        for p in parents[own]
        if p in eligible
    ]
    if not ps:
        continue
    facts.append(
        {
            "uid": uid(own),
            "label": source_nodes[own]["lbl"],
            "role": "CLASS",
            "domain": "vertebrate_breeds",
            "source": "Vertebrate Breed Ontology",
            "source_uri": own,
            "proof": {
                "native_ontology_uri": own,
                "asserted_native_parents": [p for p in parents[own] if p in eligible],
                "source_sha256": sha,
                "license": "CC-BY-4.0",
            },
            "parents": ps,
            "inclusion_basis": "Publisher-authored explicit OWL subclass axioms between live biological organism/breed classes; properties and metadata are not promoted into inclusion",
        }
    )
with Path(a.output).open("w") as f:
    for row in facts:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
summary = {
    "live_biological_nodes": len(eligible),
    "native_ncbi_to_ott_mappings": mapping_count,
    "native_mapping_boundaries": mapping_fail,
    "registry_scope_identity_links": sum(map(len, identities.values())),
    "strict_native_arc_rows": sum(len(x["parents"]) for x in facts),
    "excluded_nonbiological_or_deprecated_classes": len(source_nodes) - len(eligible),
    "license": license,
    "native_version": g["meta"]["version"],
}
Path(a.output).with_suffix(".summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2)
)
print(json.dumps(summary))
