#!/usr/bin/env python3
"""Recover all definitional product-family types, using independent head nouns.

The allowed parent is selected from native WordNet lexical type declarations,
not from source P31 claims, benchmark roots or target paths.
"""

import argparse, hashlib, json, re, sqlite3, sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas._text import norm
from fineatlas.nominal import WordNetKinds
from fineatlas.role_contracts import allows_model_extraction

p = argparse.ArgumentParser()
p.add_argument("--database", required=True)
p.add_argument("--definitions", required=True)
p.add_argument("--output", required=True)
a = p.parse_args()
c = sqlite3.connect(Path(a.database).resolve().as_uri() + "?mode=ro", uri=True)
c.row_factory = sqlite3.Row
records = json.load(open(a.definitions))
count = 0
reviews = []
artifact_roots = {
    r[0]
    for r in c.execute(
        "SELECT DISTINCT n.uid FROM aliases a CROSS JOIN nodes n ON n.uid=a.uid WHERE a.alias='artifact' AND n.uid LIKE 'wordnet31:%' AND n.visibility='ACTIVE'"
    )
}
parent_scopes = {}
kinds = WordNetKinds(c, include_native=True)
meta_roles = {}
for child, label, desc, uid in c.execute(
    "SELECT e.child_uid,p.label,p.description,p.uid FROM edges e JOIN nodes p ON p.uid=e.parent_uid WHERE e.original_relation='TYPED_REFINEMENT' AND e.source_relation='P31' AND (lower(p.label) LIKE '%model%' OR lower(p.label) LIKE '%family%' OR lower(p.label) LIKE '%series%')"
):
    lower = label.casefold()
    if any(
        word in (lower + " " + desc.casefold())
        for word in (
            "aircraft",
            "vehicle",
            "automobile",
            "product",
            "computer",
            "device",
            "weapon",
            "instrument",
        )
    ):
        meta_roles[child] = {
            "role": "MODEL_FAMILY"
            if "family" in lower or "series" in lower
            else "MODEL",
            "native_meta_uid": uid,
            "native_meta_label": label,
            "native_meta_definition": desc,
        }


def artifact_type(uid):
    if uid in parent_scopes:
        return parent_scopes[uid]
    todo = [uid]
    seen = set()
    while todo and len(seen) < 1000:
        own = todo.pop()
        if own in artifact_roots:
            parent_scopes[uid] = True
            return True
        if own in seen:
            continue
        seen.add(own)
        todo.extend(
            r[0]
            for r in c.execute(
                "SELECT parent_uid FROM edges WHERE child_uid=? AND relation='IS_A' AND status='ACTIVE' AND parent_uid LIKE 'wordnet31:%'",
                (own,),
            )
        )
    parent_scopes[uid] = False
    return False


with open(a.output, "w") as out:
    for row in c.execute(
        "SELECT * FROM nodes WHERE visibility IN ('ACTIVE','SOURCE_ONLY') AND rank IN ('named_refinement','type_or_product_model','model','product_model','model_family','series')  ORDER BY uid"
    ):
        desc = row["description"]
        label = row["label"]
        family = bool(re.search(r"\bfamily\b", desc, re.I))
        native_role = meta_roles.get(row["uid"])
        native_definition = json.loads(row["data"] or "{}")
        profile=c.execute('SELECT * FROM node_profiles WHERE uid=?',(row['uid'],)).fetchone()
        if not allows_model_extraction(native_definition,dict(profile) if profile else None):
            reviews.append({'uid':row['uid'],'reason':'Existing explicit non-design role or reviewed generic CLASS must be re-adjudicated with independent scope evidence; native rank/P31 is insufficient'})
            continue
        explicit_model = (
            row["rank"] in ("model", "product_model", "model_family", "series")
            and "independent encyclopedia definition" in row["source"]
            and native_definition.get("definition") == desc
        )
        if explicit_model and not native_role:
            native_role = {
                "role": "MODEL_FAMILY"
                if row["rank"] in ("model_family", "series")
                else "MODEL",
                "native_meta_label": "",
                "native_meta_definition": "",
                "basis": "Native source adapter model role with retained independent definition",
            }
        if not family and not native_role:
            continue
        role = "MODEL_FAMILY" if family else native_role["role"]
        if re.search(
            r"\b(?:manufacturer|company|business|dynasty|gene|protein|language|clade|organism|festival|person)\b",
            desc,
            re.I,
        ):
            continue
        q = row["uid"].split(":")[-1]
        record = records.get("wikidata:" + q, {})
        intro = record.get("intro", "") or (desc if explicit_model else "")
        statement = re.sub(r"\([^()]*\)", "", intro)
        m = re.search(
            r"\b(?:is|was|are|were)\s+(?:an?|the)\s+([^.;]{1,200})", statement, re.I
        )
        if not m:
            reviews.append(
                {"uid": row["uid"], "reason": "No independent definitional head"}
            )
            continue
        head = re.split(
            r"\b(?:that|which|with|for|designed|developed|built|produced|manufactured|made|introduced|released|sold|and|but)\b",
            m[1],
            maxsplit=1,
            flags=re.I,
        )[0].strip(" ,")
        if re.search(
            r"\b(?:manufacturer|company|organisation|organization|group of people|country)\b",
            head,
            re.I,
        ):
            continue
        meta_head = (native_role or {}).get("native_meta_label", "").casefold()
        scope = re.sub(r"\b(?:model|family|series)\b", "", meta_head).strip()
        scope_uid = kinds.unique_artifact(scope) if scope else None
        if native_role and not scope_uid and not explicit_model:
            definition = native_role.get("native_meta_definition", "")
            dm = re.search(
                r"([^.;]{0,120})\b(?:model|family|series)\b", definition, re.I
            )
            scope_words = norm(dm[1]).split() if dm else []
            for size in range(min(4, len(scope_words)), 0, -1):
                scope_uid = kinds.unique_artifact(" ".join(scope_words[-size:]))
                if scope_uid:
                    break
            if not scope_uid:
                reviews.append(
                    {
                        "uid": row["uid"],
                        "reason": "Source product scope cannot be independently grounded without ambiguity",
                        "head": head,
                        "scope": scope,
                    }
                )
                continue
        parent = kinds.resolve_head(head, scope_uid)
        if not parent:
            reviews.append(
                {
                    "uid": row["uid"],
                    "reason": "Independent nominal sense is ambiguous, absent or incompatible with source scope",
                    "head": head,
                    "scope": scope,
                }
            )
            continue
        pn = c.execute("SELECT * FROM nodes WHERE uid=?", (parent,)).fetchone()
        # The source explicitly describes a product family; unrelated biological,
        # organizational and abstract families are never model references.
        if not kinds.artifact_type(parent):
            reviews.append(
                {
                    "uid": row["uid"],
                    "reason": "Nominal parent is not in the native artifact-type scope",
                    "head": head,
                }
            )
            continue
        proof = {
            "source_entity_id": q,
            "source_description": desc,
            "independent_definition_uri": "https://en.wikipedia.org/wiki/"
            + quote(
                record.get("enwiki_title")
                or native_definition.get("attributes", {}).get("enwiki_title")
                or label.replace(" ", "_")
            ),
            "independent_definition_sha256": hashlib.sha256(intro.encode()).hexdigest(),
            "nominal_head": head,
            "nominal_type_uid": parent,
            "nominal_type_definition": pn["description"],
            "nominal_type_definition_sha256": hashlib.sha256(
                pn["description"].encode()
            ).hexdigest(),
            "native_type_scope": "Existing admitted generic type; identifier-grounded group and artifact ancestry required",
            "native_role_claim": native_role,
            "role_basis": "Native source declares product model/family; independent definition identifies a reusable design of this nominal type",
            "relationship_basis": "Product-design reference to a grounded object type; no P31 converted into IS_A",
            "license": "CC0 Wikidata facts; independent Wikipedia factual statement attribution retained",
        }
        for (uid,) in c.execute(
            "SELECT uid FROM nodes WHERE uid IN (?,?,?)",
            ("wikidata:" + q, "wikidata-v4:" + q, "v26-wikidata:" + q),
        ):
            own = c.execute('SELECT data FROM nodes WHERE uid=?', (uid,)).fetchone()
            own_profile = c.execute('SELECT * FROM node_profiles WHERE uid=?', (uid,)).fetchone()
            if not allows_model_extraction(json.loads(own[0] or '{}'), dict(own_profile) if own_profile else None):
                reviews.append({'uid': uid, 'reason': 'Independent source UID has explicit non-design role'})
                continue
            native = c.execute(
                "SELECT label,domain,visibility FROM nodes WHERE uid=?", (uid,)
            ).fetchone()
            if native["visibility"] not in ("ACTIVE", "SOURCE_ONLY"):
                continue
            out.write(
                json.dumps(
                    {
                        "uid": uid,
                        "label": native["label"],
                        "role": role,
                        "domain": native["domain"] or row["domain"],
                        "normalize_existing": True,
                        "activate_existing": native["visibility"] == "SOURCE_ONLY",
                        "source": "Independent native product-family definition",
                        "source_uri": "https://www.wikidata.org/wiki/" + q,
                        "proof": proof,
                        "parents": [{"uid": parent, "relation": "DESIGN_TYPE_OF"}],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            count += 1
Path(a.output).with_suffix(".summary.json").write_text(
    json.dumps(
        {"normalized_source_uids": count, "retained_review": reviews},
        ensure_ascii=False,
        indent=2,
    )
)
print(count, "source family records", len(reviews), "reviews")
