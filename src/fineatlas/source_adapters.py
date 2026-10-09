"""Conservative adapters for recoverable native, non-P31 relations.

Source-specific field names belong here; public queries use normalized contracts.
No benchmark UID or expected path occurs in the admission rules.
"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re

from ._text import norm


def recheck_legacy_terminals(c, output, *, snapshot_reader=None):
    """Recover configuration/descriptor links, preserving old review rows.

    Existing EPA source rows independently verify year/make/base-model keys.
    NHTSA and other authorities require their cached source bytes when available.
    Review outcomes are emitted when proof is not sufficient.
    """
    columns = "model_year_body_projection", "official_colour_class"
    count = 0
    with Path(output).open("w", encoding="utf-8") as f:
        for raw in c.execute(
            "SELECT * FROM edges WHERE source_relation IN (?,?) ORDER BY id", columns
        ):
            e = dict(raw)
            child = dict(
                c.execute(
                    "SELECT * FROM nodes WHERE uid=?", (e["child_uid"],)
                ).fetchone()
            )
            parent = dict(
                c.execute(
                    "SELECT * FROM nodes WHERE uid=?", (e["parent_uid"],)
                ).fetchone()
            )
            p = json.loads(e["provenance"] or "{}")
            ids = p.get("evidence_ids", []) if isinstance(p, dict) else p
            records = []
            for eid in ids:
                r = c.execute(
                    "SELECT * FROM evidence WHERE evidence_id=? ORDER BY layer", (eid,)
                ).fetchone()
                if (
                    r
                    and hashlib.sha256(r["payload"].encode()).hexdigest()
                    == r["payload_sha256"]
                ):
                    records.append((dict(r), json.loads(r["payload"])))
            result = {
                "edge_id": e["id"],
                "child_uid": child["uid"],
                "parent_uid": parent["uid"],
                "decision": "REVIEW",
                "reason": "Native field or authority evidence could not validate this typed connection",
                "proof": {
                    "source_relation": e["source_relation"],
                    "source_evidence_ids": ids,
                },
                "source": e["source"],
                "source_uri": "",
            }
            if (
                e["source_relation"] == "model_year_body_projection"
                and child["rank"] in ("model_year", "configuration")
                and parent["rank"] in ("model", "product_model")
            ):
                year_match = re.search(r"\b((?:19|20)\d{2})\b", child["label"])
                year = int(year_match[1]) if year_match else None
                native = []
                for ev, payload in records:
                    candidates = list(payload.get("epa_records", []))
                    for row in payload.get("presentations", []):
                        fields = row.get("source_fields", {})
                        if isinstance(fields, str):
                            fields = json.loads(fields)
                        candidates.append(
                            {
                                "graph_uid": row.get("graph_uid"),
                                "record": {
                                    **fields,
                                    "base_uid": row.get("base_identity_uid"),
                                },
                            }
                        )
                    for candidate in candidates:
                        claim = candidate.get("record", {})
                        uid = candidate.get("graph_uid")
                        n = (
                            c.execute(
                                "SELECT data FROM nodes WHERE uid=?", (uid,)
                            ).fetchone()
                            if uid
                            else None
                        )
                        if not n:
                            continue
                        source = json.loads(n[0])
                        base = source.get("baseModel") or claim.get("base_model")
                        declared = claim.get("base_uid", "")
                        if (
                            year
                            and int(source.get("year", 0)) == year
                            and int(claim.get("model_year", 0)) == year
                            and declared.endswith(parent["uid"])
                            and norm(parent["label"])
                            == norm(str(source.get("make", "")) + " " + str(base or ""))
                        ):
                            native.append(
                                {
                                    "uid": uid,
                                    "year": year,
                                    "year_identity_reverified": True,
                                    "make": source["make"],
                                    "base_model": base,
                                    "source_record_sha256": hashlib.sha256(
                                        n[0].encode()
                                    ).hexdigest(),
                                    "evidence_id": ev["evidence_id"],
                                }
                            )
                    nhtsa = payload.get("nhtsa", {})
                    if not native and nhtsa.get("verified") and snapshot_reader:
                        name = nhtsa.get("models_cache") or json.loads(
                            parent["data"] or "{}"
                        ).get("source_cache")
                        snapshot = snapshot_reader(name) if name else None
                        if snapshot:
                            try:
                                data = json.loads(snapshot)
                            except (ValueError, UnicodeDecodeError):
                                data = {}
                            models = data.get("Results", [])
                            expected = json.loads(parent["data"] or "{}").get(
                                "model_row", {}
                            )
                            for model in models:
                                if (
                                    model == expected
                                    and str(year) in str(name)
                                    and norm(parent["label"])
                                    == norm(
                                        model.get("Make_Name", "")
                                        + " "
                                        + model.get("Model_Name", "")
                                    )
                                ):
                                    native.append(
                                        {
                                            "native_model": model,
                                            "retained_configuration_year": year,
                                            "year_identity_reverified": False,
                                            "snapshot_sha256": hashlib.sha256(
                                                snapshot
                                            ).hexdigest(),
                                            "evidence_id": ev["evidence_id"],
                                        }
                                    )
                if not native and snapshot_reader:
                    pdata = json.loads(parent["data"] or "{}")
                    name = pdata.get("source_cache")
                    snapshot = snapshot_reader(name) if name else None
                    expected = pdata.get("model_row")
                    if snapshot and expected and year and str(year) in str(name):
                        document = json.loads(snapshot)
                        if (
                            expected in document.get("Results", [])
                            and norm(parent["label"])
                            == norm(
                                expected.get("Make_Name", "")
                                + " "
                                + expected.get("Model_Name", "")
                            )
                            and norm(child["label"]).startswith(
                                norm(parent["label"]) + " "
                            )
                        ):
                            native.append(
                                {
                                    "native_model": expected,
                                    "retained_configuration_year": year,
                                    "year_identity_reverified": False,
                                    "snapshot_sha256": hashlib.sha256(
                                        snapshot
                                    ).hexdigest(),
                                    "source_uri": "https://vpic.nhtsa.dot.gov/api/",
                                }
                            )
                if native:
                    result.update(
                        decision="ADMIT",
                        relation="CONFIGURATION_OF",
                        role="CONFIGURATION",
                        source_uri="https://www.fueleconomy.gov/feg/ws/index.shtml"
                        if native[0].get("uid")
                        else "https://vpic.nhtsa.dot.gov/api/",
                        reason="Native EPA year/base-model or authority model-list fields verify broad configuration-to-model membership; no IS_A asserted",
                    )
                    result["proof"].update(
                        {
                            "verified_native_records": native,
                            "scope": "CONFIGURATION_TO_REUSABLE_MODEL",
                            "body_identity_rechecked": False,
                            "year_identity_reverified": any(
                                x.get("year_identity_reverified", False) for x in native
                            ),
                            "nhtsa_year_boundary": "Native NHTSA list and MYR identify compilation/model scope, not independent model-year/trim evidence",
                        }
                    )
            elif (
                e["source_relation"] == "official_colour_class"
                and child["rank"] == "horticultural_color_class"
            ):
                attrs = json.loads(child["data"])
                code = attrs.get("ads_code")
                for ev, payload in records:
                    snapshot = (
                        snapshot_reader(payload.get("snapshot_path"))
                        if snapshot_reader
                        else None
                    )
                    if (
                        snapshot
                        and hashlib.sha256(snapshot).hexdigest()
                        == payload.get("snapshot_sha256")
                        and code
                        and code.encode() in snapshot
                    ):
                        result.update(
                            decision="ADMIT",
                            relation="ATTRIBUTE_KIND_OF",
                            role="ATTRIBUTE",
                            source_uri=payload["source_uri"],
                            reason="Official horticultural colour code is an attribute category, not a biological species or subtype",
                        )
                        result["proof"].update(
                            {
                                "official_code": code,
                                "source_uri": payload["source_uri"],
                                "source_sha256": payload["snapshot_sha256"],
                                "classified_type_uid": parent["uid"],
                            }
                        )
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
            count += 1
    return count
