#!/usr/bin/env python3
"""Align publisher product-type declarations with all matching source records.

The data declares the publisher/type/role, not SDK answers or root paths.
Only unambiguous source-scoped existing design identities are normalized.
"""

import argparse, hashlib, json, re, sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas._text import norm
from fineatlas.nominal import WordNetKinds
from fineatlas.semantics import TYPED_TERMINALS

p = argparse.ArgumentParser()
p.add_argument("--database", required=True)
p.add_argument("--catalog", required=True)
p.add_argument("--sources", required=True)
p.add_argument("--output", required=True)
a = p.parse_args()
c = sqlite3.connect(Path(a.database).resolve().as_uri() + "?mode=ro", uri=True)
c.row_factory = sqlite3.Row
kinds = WordNetKinds(c, include_native=True)
facts = []
review = []
root = Path(a.sources).resolve()
for catalog in json.loads(Path(a.catalog).read_text()):
    path = root / catalog["path"]
    body = " ".join((root / catalog["text_path"]).read_text().split())
    if hashlib.sha256(path.read_bytes()).hexdigest() != catalog["sha256"]:
        raise ValueError("Publisher snapshot SHA mismatch")
    parent = kinds.unique_artifact(catalog["object_type"])
    if not parent:
        raise ValueError(
            "Publisher object type lacks a unique grounded native identity"
        )
    for item in catalog["designs"]:
        for literal in item["source_literals"]:
            if literal.casefold() not in body.casefold():
                raise ValueError("Publisher design assertion absent: " + literal)
        rows = {
            r["uid"]: dict(r)
            for alias in item["native_aliases"]
            for r in c.execute(
                "SELECT n.* FROM aliases a CROSS JOIN nodes n WHERE a.alias=? AND n.uid=a.uid AND n.visibility='ACTIVE' AND n.rank IN ('named_refinement','model_variant','aircraft_model','model','type_or_product_model')",
                (norm(alias),),
            )
        }
        for uid, node in sorted(rows.items()):
            if (
                catalog["source_domain"] not in json.loads(node["domains"])
                and node["domain"] != catalog["source_domain"]
            ):
                review.append(
                    {
                        "uid": uid,
                        "reason": "Native source scope differs from publisher design scope",
                    }
                )
                continue
            role = item["role"]
            relation = "DESIGN_TYPE_OF"
            if relation not in TYPED_TERMINALS.get(role, ()):
                raise ValueError("Invalid design role")
            proof = {
                "publisher": catalog["publisher"],
                "source_sha256": catalog["sha256"],
                "source_role": node["rank"],
                "manufacturer_designation": item["designation"],
                "nominal_type_uid": parent,
                "role_basis": item["role_basis"],
                "relationship_basis": catalog["type_basis"],
                "license": "Publisher copyright retained; factual design identifiers only",
                "identity_basis": "Existing manufacturer-scoped named design matched to an explicit publisher design; source UIDs retained, no new same-name identity merge",
            }
            facts.append(
                dict(
                    uid=uid,
                    label=node["label"],
                    role=role,
                    domain=node["domain"],
                    normalize_existing=True,
                    source="Publisher-scoped aircraft design declarations",
                    source_uri=catalog["source_uri"],
                    proof=proof,
                    parents=[{"uid": parent, "relation": relation}],
                )
            )
with Path(a.output).open("w") as f:
    for row in facts:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
Path(a.output).with_suffix(".summary.json").write_text(
    json.dumps({"matched_source_uids": len(facts), "reviews": review}, indent=2)
)
print(len(facts), "publisher-source design matches")
