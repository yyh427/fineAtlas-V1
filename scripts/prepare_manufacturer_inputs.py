#!/usr/bin/env python3
"""Extract published identifiers, never generate combinations from ordering keys.

Publisher model designations and actual orderable part identifiers are distinct.
The historical Murata catalogue is a publisher-authored mirrored document; only
factual catalogue identifiers are exported, not the original copyrighted PDF.
"""

import argparse, hashlib, html, json, re, sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas._text import norm
from fineatlas.nominal import WordNetKinds
from bs4 import BeautifulSoup

p = argparse.ArgumentParser()
p.add_argument("--sources", required=True)
p.add_argument("--database", required=True)
p.add_argument("--output", required=True)
a = p.parse_args()
S = Path(a.sources)
c = sqlite3.connect(Path(a.database).resolve().as_uri() + "?mode=ro", uri=True)


def root(name):
    row = c.execute(
        "SELECT canonical_root_uid FROM domain_entries WHERE domain=?", (name,)
    ).fetchone()
    if not row:
        raise ValueError("Required declared source domain missing: " + name)
    return row[0]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub("<[^>]+>", " ", value))).strip()


facts = []
reviews = []


def add(uid, label, role, domain, source, uri, proof, parents, aliases=()):
    facts.append(
        dict(
            uid=uid,
            label=label,
            role=role,
            domain=domain,
            source=source,
            source_uri=uri,
            proof=proof,
            parents=parents,
            aliases=list(aliases),
        )
    )


# The catalogue contains explicit Part Number rows; X/# ordering placeholders
# and illustrative numbering explanations cannot become actual part identities.
path = S / "ceramic_final_0"
body = (S / "ceramic_final_0.txt").read_text()
url = "https://dsvr.org/kompo/datasheets/GRM155F51A334ZE01D.pdf"
catalog_pages = [page for page in body.split("\f") if "Part Number" in page]
part_body = "\n".join(catalog_pages)
source_sha = sha(path)
parts = sorted(
    set(
        re.findall(
            r"\b(?:GRM|GJM|GCM|GRT|GQM|GNM|LLL|LLR|LLA|LLM|GRJ|GR7|GA3|GMA)[A-Z0-9]{12,18}\b",
            part_body,
        )
    )
)
series = sorted({s[:3] for s in parts})
ceramic = root("ceramic_capacitors")
for value in series:
    # Publisher explicitly names these series in the catalogue headings.
    if not any(
        value in group.split("/")
        for group in re.findall(r"\b([A-Z0-9]{3}(?:/[A-Z0-9]{3})*)\s+Series\b", body)
    ):
        reviews.append(
            {"source_id": value, "reason": "Series designation lacks explicit heading"}
        )
        continue
    proof = {
        "manufacturer": "Murata",
        "series_designation": value,
        "source_sha256": source_sha,
        "catalogue": "C02E-16",
        "catalogue_imprint": "10.12.20",
        "catalogue_date_interpretation": "2010-12-20",
        "license": "Publisher copyright retained; factual identifiers only; original document not redistributed",
        "role_basis": "Explicit manufacturer series heading",
        "source_role": "manufacturer series",
        "coverage": "Historical catalogue; availability and current specifications not asserted",
    }
    add(
        "murata-series:" + value,
        "Murata " + value + " series",
        "MODEL_FAMILY",
        "ceramic_capacitors",
        "Murata C02E-16 catalogue",
        url,
        proof,
        [{"uid": ceramic, "relation": "DESIGN_TYPE_OF"}],
        [value + " series"],
    )
admitted_series = {x["proof"]["series_designation"] for x in facts}
for value in parts:
    if value[:3] not in admitted_series:
        reviews.append({"source_id": value, "reason": "No admitted series heading"})
        continue
    proof = {
        "manufacturer": "Murata",
        "part_number": value,
        "series_designation": value[:3],
        "source_sha256": source_sha,
        "catalogue": "C02E-16",
        "catalogue_imprint": "10.12.20",
        "catalogue_date_interpretation": "2010-12-20",
        "license": "Publisher copyright retained; factual identifiers only; original document not redistributed",
        "role_basis": "Complete literal published catalogue part number; no ordering-key expansion",
        "source_role": "catalog part / configuration",
        "coverage": "Catalogue configuration, not serialized physical instance or a distinct model family",
    }
    add(
        "murata-part:" + value,
        "Murata " + value,
        "CONFIGURATION",
        "ceramic_capacitors",
        "Murata C02E-16 catalogue",
        url,
        proof,
        [{"uid": "murata-series:" + value[:3], "relation": "CONFIGURATION_OF"}],
        [value],
    )
# Classify from the publisher's product description, not the site navigation.
kinds = WordNetKinds(c, include_native=True)
seen_models = {}
seen_skus = set()
for item in json.loads((S / "garmin_manifest.json").read_text()):
    if item["status"] != "FETCHED":
        reviews.append(item)
        continue
    path = S / item["path"]
    body = path.read_text()
    uri = item["source_uri"]
    if sha(path) != item["sha256"]:
        raise ValueError("Manufacturer snapshot checksum differs")
    soup = BeautifulSoup(body, "html.parser")
    heading = soup.select_one("h1")
    sku = soup.select_one("meta[itemprop=productID]")
    info = soup.select_one("#product-info")
    if not heading or not sku or not info:
        reviews.append(
            {
                "source_uri": uri,
                "reason": "Native heading, productID or primary description missing",
            }
        )
        continue
    name = heading.get_text(" ", strip=True).replace("™", "").replace("®", "").strip()
    part = sku["content"]
    subtitles = [
        x.get_text(" ", strip=True)
        for x in soup.select(".app__product__info__subtitle")
    ]
    primary = next(
        (
            x
            for x in subtitles
            if re.search(
                r"\b(?:smartwatch|fitness tracker|activity tracker)\b", x, re.I
            )
        ),
        info.get_text(" ", strip=True)[:700],
    )
    match = re.search(
        r"\b(?:smartwatch|fitness tracker|activity tracker)\b", primary, re.I
    )
    kind = kinds.unique_artifact(match[0]) if match else None
    if not kind:
        reviews.append(
            {
                "source_uri": uri,
                "reason": "Primary product type lacks an unambiguous grounded generic identity",
                "primary_description": primary,
            }
        )
        continue
    domain = (
        "fitness_trackers" if "tracker" in match[0].casefold() else "wearable_computers"
    )
    role = (
        "CONFIGURATION" if re.search(r"\b\d+(?:\.\d+)?\s*mm\b", name, re.I) else "MODEL"
    )
    model = "garmin-model:" + hashlib.sha256(norm(name).encode()).hexdigest()
    if model not in seen_models:
        proof = {
            "publisher": "Garmin",
            "manufacturer_designation": name,
            "native_product_id": part,
            "source_sha256": sha(path),
            "source_role": "sized product configuration"
            if role == "CONFIGURATION"
            else "manufacturer product model designation",
            "primary_type_statement": match[0],
            "primary_field": "product subtitle or leading primary product description",
            "primary_field_sha256": hashlib.sha256(primary.encode()).hexdigest(),
            "nominal_type_uid": kind,
            "role_basis": "Explicit sized designation"
            if role == "CONFIGURATION"
            else "Publisher-scoped product model heading",
            "license": "Publisher copyright retained; factual product identifiers only",
            "identity_basis": "Publisher-scoped product heading; no cross-source label identity inferred",
        }
        add(
            model,
            "Garmin " + name,
            role,
            domain,
            "Garmin manufacturer catalogue",
            uri,
            proof,
            [
                {
                    "uid": kind,
                    "relation": "CONFIGURATION_TYPE_OF"
                    if role == "CONFIGURATION"
                    else "DESIGN_TYPE_OF",
                }
            ],
            [name],
        )
        seen_models[model] = name
    if part not in seen_skus:
        proof = {
            "publisher": "Garmin",
            "native_product_id": part,
            "manufacturer_designation": name,
            "source_sha256": sha(path),
            "source_role": "SKU configuration",
            "license": "Publisher copyright retained; factual identifiers only",
            "role_basis": "Native productID identifies the published variant separately from its product heading",
        }
        add(
            "garmin-sku:" + part,
            "Garmin " + name + " " + part,
            "CONFIGURATION",
            domain,
            "Garmin manufacturer catalogue",
            uri,
            proof,
            [{"uid": model, "relation": "CONFIGURATION_OF"}],
            [part],
        )
        seen_skus.add(part)
path = S / "fitbit_charge6_blog.html"
body = path.read_text()
kind = kinds.unique_artifact("fitness tracker")
if not kind:
    raise ValueError("Fitness tracker type lacks a grounded generic identity")
if re.search(r"Fitbit\s+Charge\s+6", text(body), re.I) and re.search(
    r"fitness tracker", text(body), re.I
):
    uri = "https://blog.google/products-and-platforms/devices/fitbit/fitness-tracker-charge-6/"
    add(
        "fitbit-model:charge-6",
        "Fitbit Charge 6",
        "MODEL",
        "fitness_trackers",
        "Google Fitbit manufacturer announcement",
        uri,
        {
            "publisher": "Google",
            "manufacturer_model": "Fitbit Charge 6",
            "source_sha256": sha(path),
            "source_role": "manufacturer product model",
            "role_basis": "Manufacturer explicitly identifies this named product as a fitness tracker",
            "license": "Publisher copyright retained; factual identifiers only",
        },
        [{"uid": kind, "relation": "DESIGN_TYPE_OF"}],
        ["Charge 6"],
    )
# A new domain uses the already-existing generic type. It does not assert that
# all activity trackers are computers, or add a manufacturer wrapper class.
entry = {
    "domain": "fitness_trackers",
    "label": "Fitness trackers",
    "root_uids": [kind],
    "description": "Activity/fitness tracker object type and source-grounded named designs/configurations; not asserted to be a subtype of wearable computer",
    "source_uri": "https://www.wikidata.org/wiki/" + kind.split(":")[-1],
    "proof": {
        "scope_basis": "Existing generic type with independent definition and admitted physical-device ancestry",
        "root_uid": kind,
        "license": "CC0",
    },
}
Path(a.output).with_name("new_domains.jsonl").write_text(
    json.dumps(entry, ensure_ascii=False) + "\n"
)
with Path(a.output).open("w") as f:
    for row in facts:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
summary = {
    "counts": {
        r: sum(x["role"] == r for x in facts)
        for r in sorted({x["role"] for x in facts})
    },
    "review": reviews,
    "parts_found": len(parts),
    "historical_murata_series": series,
    "garmin_pages": len(json.loads((S / "garmin_manifest.json").read_text())),
}
Path(a.output).with_suffix(".summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2)
)
print(json.dumps(summary, ensure_ascii=False))
