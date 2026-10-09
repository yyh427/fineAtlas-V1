#!/usr/bin/env python3
"""Parse sourced native lineage and task category scope independently of labels.

Genus-guide common names cannot establish identity with a particular cultivar.
The adapter scans every frozen target; cases are not enumerated by class ID.
"""

import argparse, hashlib, json, re, sqlite3, sys
from pathlib import Path
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas._text import norm

p = argparse.ArgumentParser()
p.add_argument("--sources", required=True)
p.add_argument("--database", required=True)
p.add_argument("--output", required=True)
p.add_argument("--task-updates", required=True)
a = p.parse_args()
O = Path(a.sources) / "professional"
c = sqlite3.connect(Path(a.database).resolve().as_uri() + "?mode=ro", uri=True)
c.row_factory = sqlite3.Row
manifest = {
    r["name"]: r
    for r in json.loads((O / "manifest.json").read_text())
    if r["status"] == "FETCHED"
}
facts = []
updates = []
review = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content(path):
    soup = BeautifulSoup(path.read_text(), "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return soup, soup.get_text(" ", strip=True)


def genus_uid(name):
    values = {
        r["uid"]
        for r in c.execute(
            "SELECT n.uid,n.label FROM aliases a CROSS JOIN nodes n WHERE a.alias=? AND n.uid=a.uid AND n.rank='genus' AND n.source='wfo'",
            (norm(name),),
        )
        if norm(r["label"]) == norm(name)
    }
    if len(values) != 1:
        raise ValueError("Canonical native scientific genus is ambiguous: " + name)
    return next(iter(values))


# All fetched RHS genus guides; only an explicit guide heading qualifies.
for item in manifest.values():
    path = O / item["path"]
    if not item["name"].startswith("rhs_"):
        continue
    soup, txt = content(path)
    if "RHS Genus Guide" not in txt:
        continue
    title = soup.find("h1")
    if not title:
        continue
    scientific = title.get_text(" ", strip=True)
    parent = genus_uid(scientific)
    common = re.search(r"Common name:\s*([^\n]+?)\s+RHS\s*/", txt)
    names = {norm(scientific)}
    if common:
        names.add(norm(common[1]))
    for row in c.execute(
        "SELECT t.*,n.description,n.rank,n.label node_label FROM dataset_targets t JOIN nodes n ON n.uid=t.target_uid"
    ):
        if (
            norm(row["label"]) not in names
            or "cultivar" not in row["description"].casefold()
        ):
            continue
        native_uid = row["dataset"] + "-category:" + row["class_id"]
        proof = {
            "publisher": "Royal Horticultural Society",
            "native_source_id": item["source_uri"],
            "source_sha256": item["sha256"],
            "guide_type": "RHS Genus Guide",
            "scientific_genus": scientific,
            "common_name": common[1] if common else None,
            "native_task_dataset": row["dataset"],
            "native_task_class_id": row["class_id"],
            "native_task_label": row["label"],
            "scope_basis": "Source genus-guide name resolves the intended botanical category; no identity with one cultivar or one species is asserted",
            "license": "Publisher copyright retained; factual names and scope only",
        }
        facts.append(
            {
                "uid": native_uid,
                "label": row["label"],
                "role": "DATASET_CATEGORY",
                "domain": "task_categories",
                "source": "Native task category and RHS botanical scope",
                "source_uri": item["source_uri"],
                "proof": proof,
                "parents": [{"uid": parent, "relation": "DEPICTS_TYPE"}],
            }
        )
        updates.append(
            {
                "dataset": row["dataset"],
                "class_id": row["class_id"],
                "target_uid": native_uid,
                "decision_status": "VERIFIED_CATEGORY_MAPPING",
                "mapping_relation": "DEPICTS_TYPE",
                "mapping_parent_uid": parent,
                "proof": proof,
                "source_uri": item["source_uri"],
                "raw_prior": {
                    k: row[k]
                    for k in row.keys()
                    if k not in ("description", "rank", "node_label")
                },
            }
        )
# Explicit named cultivar and genus fields, preserving its biological-variant
# role and native taxonomic relation. Neither plant catalogue folders nor
# horticultural colours become IS_A.
for item in manifest.values():
    if not item["name"].startswith("rhs_"):
        continue
    path = O / item["path"]
    soup, txt = content(path)
    if "RHS Plant Profile" not in txt:
        continue
    title = soup.find("h1")
    name = title.get_text(" ", strip=True) if title else ""
    m = re.match(r"([A-Z][a-z]+)\s+['‘ʽ]([^'’]+)['’]", name)
    if not m:
        continue
    genus, cultivar = m.groups()
    parent = genus_uid(genus)
    candidates = list(
        c.execute(
            "SELECT n.uid,n.label,n.description FROM nodes n WHERE n.uid GLOB 'wikidata*' AND n.description LIKE '%cultivar%'"
        )
    )
    # Source publisher's full scientific cultivar identity must agree with the
    # independent native genus declaration, not merely a cultivar short name.
    for row in candidates:
        normalized = norm(re.sub("[ʽ‘’]", "\x27", row["label"]))
        if normalized != norm(genus + " " + cultivar):
            continue
        if genus.casefold() not in row["description"].casefold():
            continue
        proof = {
            "native_scientific_cultivar": genus + " '" + cultivar + "'",
            "publisher": "Royal Horticultural Society",
            "native_genus": genus,
            "source_sha256": item["sha256"],
            "source_role": "Cultivar",
            "native_rank": "cultivar",
            "allowed_views": ["taxonomy"],
            "license": "Publisher copyright retained; factual botanical identifiers only",
            "role_basis": "Publisher plant profile names an explicit cultivar within this genus; independent existing source declares the same cultivar and genus",
        }
        facts.append(
            {
                "uid": row["uid"],
                "label": row["label"],
                "role": "BIOLOGICAL_VARIANT",
                "normalize_existing": True,
                "domain": "plants",
                "source": "RHS cultivar profile",
                "source_uri": item["source_uri"],
                "proof": proof,
                "parents": [
                    {
                        "uid": parent,
                        "relation": "TAXONOMIC_PARENT",
                        "native_relation": "CULTIVAR_IN_GENUS",
                    }
                ],
                "inclusion_basis": "Publisher explicit scientific cultivar/genus declaration retained as native taxonomy, not strict species IS_A",
            }
        )
# Every recoverable native GBIF rank transition is checked against identifiers,
# rank and the source's native genus/family fields.
byid = {}
for item in manifest.values():
    if item["name"].startswith("gbif_"):
        doc = json.loads((O / item["path"]).read_text())
        byid[doc["key"]] = (doc, item)
for edge in c.execute(
    "SELECT * FROM edges WHERE source_relation IN ('genus_to_family','species_to_genus')"
):
    child = c.execute(
        "SELECT uid,label,rank,data FROM nodes WHERE uid=?", (edge["child_uid"],)
    ).fetchone()
    parent = c.execute(
        "SELECT uid,label,rank,data FROM nodes WHERE uid=?", (edge["parent_uid"],)
    ).fetchone()
    verified = None
    for doc, item in byid.values():
        if norm(doc.get("canonicalName", "")) != norm(child["label"]):
            continue
        key = "genus" if edge["source_relation"] == "species_to_genus" else "family"
        if (
            norm(doc.get(key, "")) == norm(parent["label"])
            and doc.get("rank", "").lower() == child["rank"]
        ):
            verified = (doc, item, key)
    if not verified:
        review.append(
            {
                "edge_id": edge["id"],
                "reason": "Native canonical name, rank or parent lineage differs",
            }
        )
        continue
    doc, item, key = verified
    proof = {
        "native_record_key": doc["key"],
        "native_rank": doc["rank"].lower(),
        "native_parent_field": key,
        "native_parent_name": doc[key],
        "native_parent_key": doc[key + "Key"],
        "native_source": doc,
        "source_sha256": item["sha256"],
        "license": "GBIF backbone facts; source attribution retained",
        "original_edge_id": edge["id"],
    }
    facts.append(
        {
            "uid": child["uid"],
            "label": child["label"],
            "role": "CLASS",
            "normalize_existing": True,
            "domain": "animals",
            "source": "GBIF native rank transition",
            "source_uri": item["source_uri"],
            "proof": proof,
            "parents": [
                {
                    "uid": parent["uid"],
                    "relation": "TAXONOMIC_PARENT",
                    "native_relation": key.upper() + "_LINEAGE",
                }
            ],
            "inclusion_basis": "Native GBIF taxon key, accepted rank and canonical parent lineage verified; retained TAXONOMIC_PARENT rather than broadening strict IS_A",
        }
    )
for path, rows in ((Path(a.output), facts), (Path(a.task_updates), updates)):
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
Path(a.output).with_suffix(".summary.json").write_text(
    json.dumps(
        {
            "source_facts": len(facts),
            "task_scope_repairs": len(updates),
            "review": review,
        },
        ensure_ascii=False,
        indent=2,
    )
)
print(
    "facts", len(facts), "task scope corrections", len(updates), "reviews", len(review)
)
