#!/usr/bin/env python3
"""Parse complete sanitized openFDA UDI inputs; never inspect GMDN fields."""

import argparse, collections, gzip, hashlib, json, re, sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas.nominal import WordNetKinds

p = argparse.ArgumentParser()
p.add_argument("--sources", required=True)
p.add_argument("--output", required=True)
p.add_argument("--dispositions", required=True)
p.add_argument("--medical-root")
p.add_argument("--database", required=True)
a = p.parse_args()
O = Path(a.sources)
out = Path(a.output)
counts = collections.Counter()
seen = {}
types = {}
classification_sha256 = hashlib.sha256(
    (O / "fda_classification.json").read_bytes()
).hexdigest()
classes = json.load(open(O / "fda_classification.json"))
fda_version = classes["meta"]["last_updated"]
native = sqlite3.connect(Path(a.database).resolve().as_uri() + "?mode=ro", uri=True)
kinds = WordNetKinds(native)
strict_types = set()
if not a.medical_root:
    a.medical_root = native.execute(
        "SELECT canonical_root_uid FROM domain_entries WHERE domain='medical_devices'"
    ).fetchone()[0]
if not native.execute(
    "SELECT 1 FROM nodes WHERE uid=? AND visibility='ACTIVE'", (a.medical_root,)
).fetchone():
    raise ValueError("Medical scope endpoint is not grounded in the source database")


def emit(f, data):
    f.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")


def key(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


with (
    out.open("w") as f,
    gzip.open(a.dispositions, "wt", encoding="utf-8", compresslevel=1) as ledger,
):
    for row in sorted(classes["results"], key=lambda x: x["product_code"]):
        code = row["product_code"]
        name = row.get("device_name", "").strip()
        definition = row.get("definition", "").strip()
        if not name:
            continue
        uid = "fda-device-type:" + code
        types[code] = uid
        physical_parent = kinds.clinical_kind(name, definition)
        if physical_parent:
            strict_types.add(code)
            counts["independently_grounded_physical_type_nodes"] += 1
        proof = {
            "source_sha256": classification_sha256,
            "native_record_sha256": key(row),
            "product_code": code,
            "device_name": name,
            "definition": definition,
            "regulation_number": row.get("regulation_number"),
            "device_class_attribute": row.get("device_class"),
            "review_panel_attribute": row.get("review_panel"),
            "last_updated": fda_version,
            "license": "CC0",
            "source_field": "device_name; FDA device classification catalogue",
            "allowed_views": ["strict", "taxonomy", "membership"]
            if physical_parent
            else ["taxonomy"],
            "nominal_physical_type_uid": physical_parent,
            "scope": "Native regulatory classification; code/panel are attributes, not IS_A parents",
        }
        emit(
            f,
            {
                "uid": uid,
                "label": name,
                "role": "CLASS",
                "domain": "medical_devices",
                "source": "openFDA device classification",
                "source_uri": "https://api.fda.gov/device/classification.json?search=product_code:"
                + code,
                "proof": proof,
                "parents": [
                    {
                        "uid": a.medical_root,
                        "relation": "NATIVE_CLASSIFICATION_PARENT",
                        "native_relation": "FDA_REGULATED_DEVICE_KIND",
                    }
                ]
                + (
                    [
                        {"uid": physical_parent, "relation": "IS_A"},
                        {"uid": a.medical_root, "relation": "IS_A"},
                    ]
                    if physical_parent
                    else []
                ),
                "inclusion_basis": "Original regulatory navigation stays native. Strict inclusion is independently admitted only for a unique native artifact-kind head in the FDA device-name/definition field; intended medical use follows the FDA medical-device classification scope. Class number, specialty and review panel stay attributes.",
            },
        )
        counts["device_type_nodes"] += 1
    for path in sorted((O / "fda_udi").glob("*.sanitized.json.gz")):
        document = json.loads(gzip.decompress(path.read_bytes()))
        snapshot = document["source_sha256"]
        native_uri = document["source_uri"]
        for r in document["results"]:
            counts["source_records"] += 1
            model = r.get("version_or_model_number", "").strip()
            company = r.get("company_name", "").strip()
            brand = r.get("brand_name", "").strip()
            description = r.get("device_description", "")
            source_id = r.get("public_device_record_key", "")
            codes = sorted(
                {
                    x.get("code")
                    for x in r.get("product_codes", [])
                    if x.get("code") in types
                }
            )
            safe = (
                model.casefold()
                not in (
                    "",
                    "n/a",
                    "na",
                    "none",
                    "not applicable",
                    "unknown",
                    "not available",
                )
                and company
                and brand
                and codes
            )
            pattern = (
                r"\bmodel(?:\s*(?:number|no\.?|#))?\s*[:=-]?\s*[\"\']?"
                + re.escape(model)
                + r"(?![A-Za-z0-9])"
            )
            role_text = brand + "; " + description
            explicit = bool(
                safe
                and "model" in role_text.casefold()
                and model.casefold() in role_text.casefold()
                and re.search(pattern, role_text, re.I)
            )
            sizes = r.get("device_sizes", [])
            dimensioned = [
                x
                for x in sizes
                if x.get("value")
                and x.get("unit")
                and re.fullmatch(r"\d+(?:\.\d+)?", str(x["value"]))
                and float(x["value"]) > 0
            ]
            configured = bool(
                safe
                and not explicit
                and r.get("catalog_number", "").strip() == model
                and dimensioned
                and r.get("device_count_in_base_package") == "1"
                and r.get("is_kit") == "false"
            )
            role = "MODEL" if explicit else "CONFIGURATION" if configured else None
            if r.get("record_status") != "Published":
                reason = "UNPUBLISHED_SOURCE_RECORD"
            elif not safe:
                reason = "INSUFFICIENT_NATIVE_MODEL_IDENTITY_OR_TYPE"
            elif role is None:
                reason = "VERSION_OR_MODEL_ROLE_AMBIGUOUS"
            else:
                ident = (
                    role,
                    company,
                    brand,
                    model,
                    tuple(codes),
                    json.dumps(dimensioned, sort_keys=True) if configured else "",
                )
                uid = (
                    "fda-device-model:" if role == "MODEL" else "fda-device-config:"
                ) + key(ident)
                if ident in seen:
                    reason = "DUPLICATE_NATIVE_DESIGN_OR_PACKAGING_RECORD"
                    counts["duplicate_source_records"] += 1
                else:
                    reason = (
                        "ADMITTED_EXPLICIT_MODEL"
                        if role == "MODEL"
                        else "ADMITTED_SIZED_CATALOG_CONFIGURATION"
                    )
                    seen[ident] = uid
                    physical = bool(
                        re.search(
                            r"\b(?:is|are|consists? of)\s+(?:an?\s+|the\s+)?[^.;]{0,180}\b(?:device|instrument|monitor|pump|catheter|implant|machine|battery)\b",
                            description[:500],
                            re.I,
                        )
                    ) and not re.search(
                        r"\b(?:software|algorithm|application|firmware)\b",
                        description[:250],
                        re.I,
                    )
                    proof = {
                        "company_name": company,
                        "brand_name": brand,
                        "version_or_model_number": model,
                        "catalog_number": r.get("catalog_number"),
                        "device_sizes": sizes,
                        "source_model_role_field": role_text if explicit else None,
                        "device_description": description,
                        "physical_device_definition_verified": physical,
                        "allowed_views": ["strict", "taxonomy", "membership"]
                        if physical or any(x in strict_types for x in codes)
                        else ["taxonomy"],
                        "source_record_key": source_id,
                        "source_uri": native_uri,
                        "source_sha256": snapshot,
                        "last_updated": document["meta"]["last_updated"],
                        "primary_di": [
                            x["id"]
                            for x in r.get("identifiers", [])
                            if x.get("type") == "Primary"
                        ],
                        "product_codes": codes,
                        "license": "CC0; no GMDN fields used or retained",
                        "role_basis": "Manufacturer-reported text explicitly calls this native value a model"
                        if explicit
                        else "Matching catalog/model identifier, quantitative device-size fields and one-device base package define a catalog configuration; no model or firmware identity asserted",
                        "packaging_identifiers_are_instances": False,
                        "scope": "Source-reported product design reference; not an individual manufactured object",
                    }
                    emit(
                        f,
                        {
                            "uid": uid,
                            "label": company + " " + brand + " " + model,
                            "role": role,
                            "domain": "medical_devices",
                            "source": "openFDA GUDID manufacturer-reported model"
                            if role == "MODEL"
                            else "openFDA GUDID sized catalog configuration",
                            "source_uri": "https://api.fda.gov/device/udi.json?search=public_device_record_key:"
                            + source_id,
                            "proof": proof,
                            "parents": [
                                {"uid": types[code], "relation": "REGULATED_AS"}
                                for code in codes
                            ]
                            + (
                                [
                                    {
                                        "uid": a.medical_root,
                                        "relation": "DESIGN_TYPE_OF"
                                        if role == "MODEL"
                                        else "CONFIGURATION_TYPE_OF",
                                    }
                                ]
                                if physical
                                else []
                            ),
                        },
                    )
                    counts[
                        "unique_model_nodes"
                        if role == "MODEL"
                        else "unique_configuration_nodes"
                    ] += 1
            counts[reason] += 1
            emit(
                ledger,
                {
                    "source_record_key": source_id,
                    "decision": reason,
                    "uid": seen.get(
                        (
                            role,
                            company,
                            brand,
                            model,
                            tuple(codes),
                            json.dumps(dimensioned, sort_keys=True)
                            if configured
                            else "",
                        )
                    ),
                    "source_snapshot": path.name,
                    "source_sha256": snapshot,
                },
            )
        print(
            "FDA parsed",
            path.name,
            counts["source_records"],
            counts["unique_model_nodes"],
            flush=True,
        )
summary = {
    "counts": dict(counts),
    "coverage": "All 52 openFDA UDI partitions and the complete device classification endpoint; conservative explicit-model admission",
    "limitations": [
        "Version/model ambiguity retained; no firmware versions reclassified as models",
        "UDI device identifiers describe registered device/packaging definitions, not physical-instance serial IDs",
        "Regulatory type assignments are REGULATED_AS, not MODEL IS_A",
        "Product code and review panel not converted into directory hierarchy",
        "Cross-source same-name records are not merged without identifier evidence",
    ],
}
out.with_suffix(".summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2)
)
print(json.dumps(summary, ensure_ascii=False), flush=True)
