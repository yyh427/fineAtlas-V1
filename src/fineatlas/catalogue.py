"""Validate source listings against separately reviewed type correspondences.

The stable source key identifies a catalogue configuration. Neither a title nor
a product-type field establishes cross-source identity or a worldwide model.
"""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import quote


def canonical_record(record: dict) -> bytes:
    return json.dumps(record, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode()


def listing_uid(record: dict) -> str:
    if not record.get("domain_name") or not record.get("item_id"):
        raise ValueError("A listing needs a source domain and item identifier")
    return "abo-listing:" + quote(record["domain_name"], safe="") + ":" + quote(
        record["item_id"], safe="")


def field_values(record: dict, field: str) -> list[str]:
    value = record.get(field, [])
    if not isinstance(value, list) or any(
        not isinstance(v, dict) or not isinstance(v.get("value"), str) for v in value
    ):
        raise ValueError("Malformed native list field: " + field)
    return [v["value"] for v in value]


def inspect_listing(record: dict, rule: dict) -> dict:
    """Require native type, corroborating title and catalogue scope together."""
    try:
        uid = listing_uid(record)
        types = field_values(record, "product_type")
    except (ValueError, TypeError) as error:
        return {"status": "REVIEW", "reason": str(error)}
    if types != [rule["product_type"]]:
        return {"status": "REVIEW", "uid": uid, "reason": "NATIVE_TYPE_AMBIGUOUS"}
    names = record.get("item_name", [])
    if not isinstance(names, list):
        return {"status": "REVIEW", "uid": uid, "reason": "MALFORMED_NAMES"}
    english = sorted({v.get("value", "").strip() for v in names
                      if isinstance(v, dict) and isinstance(v.get("language_tag"), str)
                      and v["language_tag"].startswith("en")
                      and isinstance(v.get("value"), str) and v["value"].strip()})
    if not english:
        return {"status": "REVIEW", "uid": uid, "reason": "NO_REVIEWABLE_ENGLISH_TITLE"}
    if len(english) != 1:
        return {"status": "REVIEW", "uid": uid, "reason": "ENGLISH_SCOPE_CONFLICT"}
    title = english[0]
    if any(re.search(pattern, title, re.I) for pattern in rule["reject_title_patterns"]):
        return {"status": "REVIEW", "uid": uid, "reason": "ACCESSORY_OR_SCOPE_CONFLICT", "label": title}
    if not any(re.search(pattern, title, re.I) for pattern in rule["title_patterns"]):
        return {"status": "REVIEW", "uid": uid, "reason": "TITLE_DOES_NOT_CORROBORATE_TYPE", "label": title}
    native_nodes = record.get("node") or []
    if not isinstance(native_nodes, list):
        return {"status": "REVIEW", "uid": uid, "reason": "MALFORMED_CATALOGUE"}
    paths = sorted({v.get("node_name", v.get("path", "")) for v in native_nodes
                    if isinstance(v, dict) and isinstance(
                        v.get("node_name", v.get("path", "")), str)})
    if not any(re.search(pattern, path, re.I) for pattern in rule["catalogue_patterns"]
               for path in paths):
        return {"status": "REVIEW", "uid": uid, "reason": "CATALOGUE_SCOPE_NOT_CORROBORATED", "label": title}
    size_terms = set()
    for value in names:
        if isinstance(value, dict) and isinstance(value.get("value"), str):
            size_terms.update(x.casefold() for x in re.findall(
                r"\b(?:queen|king|twin)\b", value["value"], re.I))
    if len(size_terms) > 1:
        return {"status": "REVIEW", "uid": uid, "reason": "MULTILINGUAL_SIZE_CONFLICT", "label": title}
    base_parent = rule["parent_uid"]
    allow_refinements = True
    for override in rule.get("scope_overrides", []):
        if re.search(override["title_pattern"], title, re.I):
            base_parent = override["parent_uid"]
            allow_refinements = override.get("allow_refinements", True)
            break
    parents = [base_parent]
    refinements = []
    evidence_text = title + " " + " ".join(
        v.get("value", "") for v in record.get("bullet_point", [])
        if isinstance(v, dict) and isinstance(v.get("value"), str)
        and isinstance(v.get("language_tag"), str) and v["language_tag"].startswith("en"))
    for finer in rule.get("refinements", []) if allow_refinements else []:
        if any(not re.search(pattern, evidence_text, re.I)
               for pattern in finer.get("required_evidence_patterns", [])):
            continue
        if any(re.search(pattern, evidence_text, re.I)
               for pattern in finer.get("reject_evidence_patterns", [])):
            continue
        if re.search(finer["title_pattern"], title, re.I) and any(
            re.search(finer["catalogue_pattern"], path, re.I) for path in paths
        ):
            parents.append(finer["parent_uid"])
            refinements.append(finer["parent_uid"])
    return {"status": "ADMIT_SOURCE_CONFIGURATION", "uid": uid, "label": title,
            "role": "CONFIGURATION", "domain": rule["domain"],
            "parent_uids": list(dict.fromkeys(parents)),
            "refined_parent_uids": refinements, "catalogue_paths": paths,
            "record_sha256": hashlib.sha256(canonical_record(record)).hexdigest(),
            "world_model_identity_verified": False}
