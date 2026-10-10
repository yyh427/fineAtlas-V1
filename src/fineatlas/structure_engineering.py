"""Frozen, source-scoped engineering hierarchy repairs.

Author-defined datasets and regulatory records are identities in their own
namespaces. Neither exact names nor native grouping fields assert commercial
cross-source equivalence. Preparation is read-only; replay belongs to Migration.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3

from .hierarchy import apply_refinements, source_assertion_sha256, locate_source_assertion
from .semantics import role_expression

INPUT_NAME = "structure_engineering.json"
OPERATIONS_NAME = "structure_engineering_operations.jsonl"
FGVC_URI = "https://www.robots.ox.ac.uk/~vgg/data/fgvc-aircraft/"
EPA_URI = "https://www.fueleconomy.gov/feg/download.shtml"
FAA_URI = "https://registry.faa.gov/database/ardata.pdf"


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha(value):
    raw = value if isinstance(value, bytes) else value.encode()
    return hashlib.sha256(raw).hexdigest()


def fgvc_annotations(directory):
    """Join all split fields by ID and reject missing/ambiguous memberships."""
    directory = Path(directory)
    records, files, seen = [], [], set()
    for split in ("train", "val", "test"):
        fields = {}
        for field in ("variant", "family", "manufacturer"):
            path = directory / f"images_{field}_{split}.txt"
            raw = path.read_bytes()
            files.append({"file": path.name, "sha256": sha(raw), "bytes": len(raw)})
            values = [line.split(" ", 1) for line in raw.decode().splitlines() if line]
            if any(len(pair) != 2 or not pair[1].strip() for pair in values):
                raise ValueError("Malformed native annotation: " + path.name)
            fields[field] = dict(values)
            if len(fields[field]) != len(values):
                raise ValueError("Duplicate native annotation ID: " + path.name)
        if len({frozenset(rows) for rows in fields.values()}) != 1:
            raise ValueError("Native annotation field ID sets differ")
        for image_id in sorted(fields["variant"]):
            if image_id in seen:
                raise ValueError("Native annotation ID occurs in several splits")
            seen.add(image_id)
            records.append({"image_id": image_id, "split": split,
                            **{field: fields[field][image_id] for field in fields}})
    memberships = defaultdict(set)
    for record in records:
        memberships[record["variant"]].add((record["family"], record["manufacturer"]))
    if any(len(parents) != 1 for parents in memberships.values()):
        raise ValueError("A native variant has incompatible family/manufacturer scopes")
    return {"source_version": "2013b", "source_uri": FGVC_URI,
            "files": files, "record_count": len(records),
            "annotation_records_sha256": sha(canonical(records)),
            "hierarchy": [{"variant": variant, "family": next(iter(parents))[0],
                           "manufacturer": next(iter(parents))[1],
                           "records": sum(r["variant"] == variant for r in records)}
                          for variant, parents in sorted(memberships.items())]}


def checked_epa_membership(config, variant, base, evidence):
    """Native grouping uses literal fields and existing source identifiers."""
    required = ("id", "year", "make", "model", "baseModel")
    if any(not str(config.get(key, "")).strip() for key in required):
        raise ValueError("EPA grouping lacks required literal native fields")
    if variant["source"] != "epa" or base["source"] != "epa":
        raise ValueError("Native EPA grouping cannot import a cross-source identity")
    if variant["rank"] != "model_variant" or base["rank"] != "model":
        raise ValueError("EPA grouping endpoint source grains differ")
    if variant["label"] != config["make"] + " " + config["model"]:
        raise ValueError("Variant scope disagrees with the literal EPA model field")
    if base["label"] != config["make"] + " " + config["baseModel"]:
        raise ValueError("Base scope disagrees with the literal EPA baseModel field")
    for proof in evidence:
        if any(str(proof.get(key, "")) != str(config[key])
               for key in ("year", "make", "model", "baseModel")):
            raise ValueError("Retained EPA relation evidence disagrees with native fields")
    return {key: config[key] for key in required}


def assertion_locator(row):
    return {key: row[key] for key in ("left_uid", "right_uid", "relation", "source")} | {
        "content_sha256": source_assertion_sha256(row)}


def name_only_scope_conflict(bridge, left, right):
    """Reject uncorroborated name-only source-equivalence claims.

    A role difference alone never disproves identity. Here the *stored claim*
    expressly uses a name/model string rather than an identifier crosswalk,
    irrespective of whether its roles happen to agree. It cannot authorize contraction. Exact-QID
    and independently adjudicated assertions remain intact.
    """
    native = {"faa", "epa", "vpic"}
    if left["source"] not in native and right["source"] not in native:
        return None
    payload = json.loads(bridge["data"] or "{}")
    if payload.get("alignment_type") == "SOURCE_ID_EQUIVALENCE":
        return None
    if payload.get("independent_source_crosswalk") or payload.get("reviewed_scope_equivalence"):
        return None
    claimed = payload.get("alignment_type") == "STRUCTURED_IDENTITY_EQUIVALENCE"
    claimed |= bridge["source"] == "FAA_ACFTREF+Wikidata_P31" and str(
        payload.get("evidence", "")).startswith("exact FAA MFR=")
    if not claimed:
        return None
    return {"basis": "UNSUPPORTED_NAME_ONLY_ENGINEERING_IDENTITY_WITHDRAWN",
            "scope_observation": "Stored source claim matches manufacturer/model names; "
            "it contains no source-ID crosswalk or independent equality of covered "
            f"designs. Retained endpoint scopes are {left['role']} and {right['role']}.",
            "left_role": left["role"], "right_role": right["role"],
            "asserted_inequality": False, "world_identity_status": "REVIEW",
            "original_source_payload_and_endpoints_preserved": True,
            "no_replacement_identity_inferred": True,
            "individual_semantic_review": True,
            "license": "Derived factual source scope; original source terms retained"}


def independent_scope_equivalence(c, bridge):
    """Protect an existing individual source-ID-bound OEM/native scope review."""
    uids = {bridge["left_uid"], bridge["right_uid"]}
    for uid in uids:
        rows = c.execute("SELECT e.* FROM node_profiles p JOIN evidence e ON e.evidence_id=p.evidence_id WHERE p.uid=?", (uid,)).fetchall()
        for row in rows:
            if sha(row["payload"]) != row["payload_sha256"]:
                raise ValueError("Independent scope review evidence checksum mismatch")
            proof = json.loads(row["payload"])
            if (proof.get("basis") == "INDEPENDENT_MANUFACTURER_FAMILY_AND_NATIVE_AGGREGATION_SCOPE"
                and proof.get("individual_semantic_review") and proof.get("scope_observation")
                and uids <= set(proof.get("identity_member_uids", []))
                and proof.get("native_witnesses") and any(source.get("kind") == "MANUFACTURER_FAMILY_DEFINITION"
                    for source in proof.get("external_sources", []))):
                for witness in proof["native_witnesses"]:
                    claim = locate_source_assertion(c, "entity_relations", witness["locator"])
                    raw = c.execute("SELECT data FROM nodes WHERE uid=?", (claim["subject_uid"],)).fetchone()
                    if (claim["status"] != "ACTIVE" or claim["relation"] != "CONFIGURATION_OF"
                        or claim["object_uid"] not in proof["identity_member_uids"]
                        or not raw or sha(raw[0]) != witness["native_record_sha256"]):
                        raise ValueError("Prior approved scope has a changed native identity witness")
                return {"evidence_id": row["evidence_id"], "payload_sha256": row["payload_sha256"],
                        "basis": proof["basis"], "scope_observation": proof["scope_observation"],
                        "identity_member_uids": proof["identity_member_uids"],
                        "external_sources": proof["external_sources"], "native_witnesses": proof["native_witnesses"]}
    return None


def reviewed_grain_operations(c, path):
    """Replay individually frozen OEM grain adjudications, never label rules."""
    if not path:
        return [], [], {}
    path = Path(path)
    reviews = json.loads(path.read_text())
    operations, dispositions, roles = [], [], {}
    for review in reviews:
        proof = review["proof"]
        if not proof.get("individual_semantic_review") or not proof.get("scope_observation"):
            raise ValueError("Engineering grain review lacks an individual scope adjudication")
        snapshot = path.parent / review["snapshot_file"]
        if not snapshot.is_file() or sha(snapshot.read_bytes()) != review["snapshot_sha256"]:
            raise ValueError("Reviewed OEM scope snapshot changed")
        for uid, expected in review["native_member_hashes"].items():
            n = c.execute("SELECT n.*," + role_expression("n", "p") + " role FROM nodes n "
                "LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?", (uid,)).fetchone()
            if not n or sha(n["data"]) != expected or n["visibility"] != "ACTIVE":
                raise ValueError("Reviewed design source record changed")
            if n["role"] not in {"CLASS", "MODEL", "MODEL_FAMILY"}:
                raise ValueError("Grain repair cannot replace another source unit")
            role = review["role"]
            if role not in {"MODEL", "MODEL_FAMILY"}:
                raise ValueError("OEM design repair requires a named design grain")
            roles[uid] = role
            p = {**proof, "native_record_sha256": expected,
                 "prior_role": n["role"], "source_role": "Individually OEM-documented named design",
                 "external_source": {"url": review["uri"], "sha256": review["snapshot_sha256"]},
                 "allowed_views": ["strict", "taxonomy", "membership", "unified"]}
            operations.append({"op": "role", "uid": uid, "role": role,
                "source": "Reviewed OEM engineering design grain", "uri": review["uri"], "proof": p})
            for edge in c.execute("SELECT * FROM edges WHERE child_uid=? AND relation='IS_A' AND status='ACTIVE'", (uid,)):
                if edge["parent_uid"] not in review["verified_type_parents"]:
                    raise ValueError("A former class inclusion lacks an independent reviewed replacement type")
                dispositions.append({"uid": uid, "parent": edge["parent_uid"], "locator": {
                    **{key: edge[key] for key in ("child_uid", "parent_uid", "relation", "source", "layer")},
                    "content_sha256": source_assertion_sha256(edge)}, "proof": p})
                operations.append({"op": "link", "uid": uid, "parent": edge["parent_uid"],
                    "relation": "DESIGN_TYPE_OF", "source": "Reviewed OEM engineering design grain",
                    "uri": review["uri"], "proof": {**p, "basis": "NAMED_FACTORY_DESIGN_HAS_EVIDENCED_PHYSICAL_TYPE_NOT_CLASS_INCLUSION",
                    "native_original_assertion": dispositions[-1]["locator"]}})
            incoming = c.execute("SELECT 1 FROM edges WHERE parent_uid=? AND relation='IS_A' AND status='ACTIVE' LIMIT 1", (uid,)).fetchone()
            if incoming:
                raise ValueError("Reviewed role change needs a separate incoming-class assertion adjudication")
    return operations, dispositions, roles


def reviewed_same_object_scopes(c, path):
    """Explicit individual OEM/registry/native-field equality adjudications."""
    if not path:
        return []
    path = Path(path)
    results = []
    for review in json.loads(path.read_text()):
        proof = review.get("approved_scope_equivalence")
        if not proof:
            continue
        if not proof.get("individual_semantic_review") or not proof.get("scope_observation"):
            raise ValueError("Same-object scope review lacks individual adjudication")
        for uid, expected in proof["native_member_hashes"].items():
            row = c.execute("SELECT data FROM nodes WHERE uid=?", (uid,)).fetchone()
            if not row or sha(row[0]) != expected:
                raise ValueError("Same-object source scope payload changed")
        kinds = set()
        years = set()
        for source in proof["external_sources"]:
            snapshot = path.parent / source["file"]
            if not snapshot.is_file() or sha(snapshot.read_bytes()) != source["sha256"]:
                raise ValueError("Same-object OEM/registry scope evidence changed")
            kinds.add(source["kind"])
            if source["kind"] == "VPIC_MODEL_YEAR_SAMPLE":
                rows = json.loads(snapshot.read_text()).get("Results", [])
                if not any(row.get("Make_ID") == source["make_id"] and row.get("Model_ID") == source["model_id"] for row in rows):
                    raise ValueError("Registry code is not present in frozen model-year evidence")
                years.add(source["model_year"])
        if not {"OEM_MODEL_MANUAL", "VPIC_MODEL_YEAR_SAMPLE"} <= kinds or len(years) < 2:
            raise ValueError("Explicit scope equality needs an OEM design plus native registry ID scopes")
        for witness in proof["native_witnesses"]:
            row = c.execute("SELECT data FROM nodes WHERE uid=?", (witness["uid"],)).fetchone()
            if not row or sha(row[0]) != witness["sha256"]:
                raise ValueError("Same-object native configuration witness changed")
            raw = json.loads(row[0])
            if any(str(raw.get(key, "")) != str(value) for key, value in witness["fields"].items()):
                raise ValueError("Same-object native scope fields changed")
        results.append(proof)
    return results


def prepare_structure_engineering(database, annotations, output, *, sources=None,
                                  baseline_labels=None, conflict_components=None,
                                  reviewed_roles=None):
    """Freeze exact node payloads, native witnesses, and source dispositions."""
    database, output = Path(database), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(database.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA query_only=ON")
    cohort = fgvc_annotations(annotations)
    if cohort["record_count"] != 10000 or len(cohort["hierarchy"]) != 100:
        raise ValueError("This frozen source version requires the complete 100-variant cohort")
    nodes, links, targets, operations, inventory = [], [], [], [], []
    grain_ops, edge_dispositions, corrected_roles = reviewed_grain_operations(c, reviewed_roles)
    same_object_reviews = reviewed_same_object_scopes(c, reviewed_roles)
    operations.extend(grain_ops)
    native_source = "fgvc_aircraft_native"
    common = {"basis": "COMPLETE_AUTHOR_DECLARED_VARIANT_FAMILY_ANNOTATION_JOIN",
              "source_uri": FGVC_URI, "source_version": "2013b",
              "annotation_files": cohort["files"],
              "annotation_records_sha256": cohort["annotation_records_sha256"],
              "identity_scope": "SOURCE_NATIVE", "world_exact_identity_verified": False,
              "source_native_identity_verified": True,
              "no_name_based_identity_merge": True,
              "allowed_views": ["strict", "taxonomy", "membership", "unified"],
              "license": "Source-derived annotation facts only; no photographs or image rights redistributed"}
    def native_uid(unit, name):
        return "fgvc-aircraft-2013b:" + unit + ":" + name.casefold()
    families = sorted({r["family"] for r in cohort["hierarchy"]})
    for unit, names, role in (("family", families, "MODEL_FAMILY"),
                              ("variant", [r["variant"] for r in cohort["hierarchy"]], "MODEL")):
        for name in names:
            uid = native_uid(unit, name)
            proof = {**common, "native_label": name, "native_unit": unit,
                     "source_role": "Author-declared aircraft " + unit,
                     "semantic_grain": "SOURCE_NATIVE_AIRCRAFT_" + unit.upper()}
            nodes.append({"uid": uid, "label": name + " [FGVC " + unit + "]",
                          "native_label": name, "role": role, "domain": "aircraft",
                          "source": native_source, "uri": FGVC_URI, "proof": proof})
            operations.append({"op": "role", "uid": uid, "role": role,
                               "source": native_source, "uri": FGVC_URI, "proof": proof})
            if unit == "family":
                links.append({"op": "link", "uid": uid,
                              "parent": "wordnet31:02689427-n", "relation": "DESIGN_TYPE_OF",
                              "source": native_source, "uri": FGVC_URI,
                              "proof": {**proof, "scope_observation": "Every joined source family groups aircraft variants; aircraft type only, no world commercial identity asserted"}})
    source_targets = list(c.execute("SELECT * FROM dataset_targets WHERE dataset='fgvc_aircraft'"))
    if len(source_targets) != 100:
        raise ValueError("Retained dataset target cohort differs")
    by_label = {r["label"]: dict(r) for r in source_targets}
    for record in cohort["hierarchy"]:
        proof = {**common, "native_membership": record,
                 "source_role": "Author-declared aircraft variant"}
        uid = native_uid("variant", record["variant"])
        links.append({"op": "link", "uid": uid,
                      "parent": native_uid("family", record["family"]),
                      "relation": "SERIES_MEMBER_OF", "source": native_source,
                      "uri": FGVC_URI, "proof": proof})
        if record["variant"] not in by_label:
            raise ValueError("Author variant lacks a retained exact dataset label")
        original = by_label[record["variant"]]
        targets.append({"dataset": "fgvc_aircraft", "class_id": original["class_id"],
                        "label": original["label"], "namespace": "fgvc-aircraft-2013b",
                        "source_version": "2013b", "source_uid": uid, "role": "MODEL",
                        "decision_status": "SOURCE_DECLARED", "proof": proof})
    operations.extend(links)
    # Retained source-native configuration evidence supplies exact model/base
    # references. No reconstruction from prefixes, aliases or external names.
    source_nodes = {r["uid"]: dict(r) for r in c.execute(
        "SELECT n.*," + role_expression("n", "p") + " role FROM nodes n "
        "LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.source IN ('epa','faa','vpic')")}
    for uid in corrected_roles:
        if uid in source_nodes:
            source_nodes[uid]["role"] = corrected_roles[uid]
    all_epa_variants = {uid for uid, n in source_nodes.items() if n["rank"] == "model_variant"}
    witnesses, rejected = {}, []
    query = """SELECT a.subject_uid,a.object_uid variant_uid,b.object_uid base_uid,
      a.evidence_id variant_evidence,b.evidence_id base_evidence
      FROM entity_relations a JOIN entity_relations b ON b.subject_uid=a.subject_uid
      WHERE a.status='ACTIVE' AND b.status='ACTIVE'
      AND a.relation='CONFIGURATION_OF' AND b.relation='CONFIGURATION_OF'
      AND a.object_uid LIKE 'epa-variant:%' AND b.object_uid LIKE 'epa-model:%'
      ORDER BY a.subject_uid,a.object_uid,b.object_uid"""
    for row in c.execute(query):
        key = (row["variant_uid"], row["base_uid"])
        if key in witnesses:
            continue
        native = source_nodes.get(row["subject_uid"])
        if not native:
            rejected.append({"uid": row["variant_uid"], "reason": "Source configuration missing"})
            continue
        evidence = [c.execute("SELECT * FROM evidence WHERE evidence_id=?", (row[key],)).fetchone()
                    for key in ("variant_evidence", "base_evidence")]
        if any(not e or sha(e["payload"]) != e["payload_sha256"] for e in evidence):
            raise ValueError("Native EPA source evidence checksum mismatch")
        try:
            fields = checked_epa_membership(json.loads(native["data"]),
                source_nodes[row["variant_uid"]], source_nodes[row["base_uid"]],
                [json.loads(e["payload"]) for e in evidence])
        except ValueError as exc:
            rejected.append({"uid": row["variant_uid"], "reason": str(exc)})
            continue
        witnesses[key] = {"native_record_uid": native["uid"],
                          "native_record_sha256": sha(native["data"]), "native_fields": fields,
                          "evidence_ids": [e["evidence_id"] for e in evidence],
                          "evidence_sha256": [e["payload_sha256"] for e in evidence],
                          "uri": evidence[0]["source_uri"]}
    base_variants = defaultdict(set)
    for (variant_uid, base_uid), witness in witnesses.items():
        base_variants[base_uid].add(variant_uid)
    # Exact-key EPA identity repairs previously contracted the plain model with
    # a baseModel aggregate even when that aggregate includes other models.
    # The retained native sets provide a literal counterexample to equality.
    split_ids = set()
    for b in c.execute("SELECT * FROM bridges WHERE status='ACTIVE' AND relation='SAME_CONCEPT' AND source='v25_epa_identity_repair'"):
        left, right = b["left_uid"], b["right_uid"]
        if right not in base_variants or len(base_variants[right]) < 2 or left not in base_variants[right]:
            continue
        different = next(uid for uid in sorted(base_variants[right]) if uid != left)
        counterexample = witnesses[(different, right)]
        proof = {"basis": "EPA_MODEL_SCOPE_IS_STRICT_SUBSET_OF_BASEMODEL_AGGREGATE",
                 "disposition_category": "confirmed_scope_difference",
                 "scope_observation": "Native model key denotes one literal make/model; "
                 "baseModel key also groups the frozen different-model witness. Equal "
                 "normalized labels or key strings cannot make these scopes equal.",
                 "counterexample": counterexample, "original_source_payload_and_endpoints_preserved": True,
                 "no_replacement_identity_inferred": True, "license": "US federal public-domain data"}
        operations.append({"op": "split_identity_source", "uid": left, "parent": right,
                           "locator": assertion_locator(b), "source": "Reviewed EPA literal grouping scope",
                           "uri": counterexample["uri"], "proof": proof})
        split_ids.add(b["id"])
    cross_bridge_inventory = []
    for b in c.execute("""SELECT b.* FROM bridges b WHERE b.status='ACTIVE' AND b.relation='SAME_CONCEPT'
       AND (b.source IN ('faa','epa','vpic','FAA_ACFTREF+Wikidata_P31'))"""):
        endpoints = []
        for uid in (b["left_uid"], b["right_uid"]):
            n = source_nodes.get(uid)
            if not n:
                r = c.execute("SELECT n.*," + role_expression("n", "p") + " role FROM nodes n "
                    "LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?", (uid,)).fetchone()
                n = dict(r) if r else None
            endpoints.append(n)
        for n in endpoints:
            if n and n["uid"] in corrected_roles:
                n["role"] = corrected_roles[n["uid"]]
        if not all(endpoints):
            raise ValueError("Engineering identity claim has a missing source endpoint")
        protected = independent_scope_equivalence(c, b)
        if not protected:
            protected = next((review for review in same_object_reviews if
                {b["left_uid"], b["right_uid"]} <= set(review["native_member_hashes"])), None)
        evaluation = dict(b)
        if protected:
            claim = json.loads(b["data"] or "{}")
            claim["reviewed_scope_equivalence"] = protected
            evaluation["data"] = canonical(claim)
        proof = name_only_scope_conflict(evaluation, *endpoints)
        item = {"locator": assertion_locator(b), "left_uid": b["left_uid"],
                "right_uid": b["right_uid"], "left_role": endpoints[0]["role"],
                "right_role": endpoints[1]["role"], "status": "WITHDRAW_UNSUPPORTED_IDENTITY" if proof else (
                    "PRESERVED_INDEPENDENT_SCOPE_EQUIVALENCE" if protected else "PRESERVED_NATIVE_SOURCE_IDENTITY")}
        item["original_alignment_payload"] = json.loads(b["data"] or "{}")
        item["independent_scope_equivalence"] = protected
        item["disposition_category"] = "unproven_name_only_identity" if proof else (
            "same_scope_role_corrected" if any(n["uid"] in corrected_roles for n in endpoints) else "preserved")
        cross_bridge_inventory.append(item)
        if proof:
            proof["disposition_category"] = "unproven_name_only_identity"
            uri = FAA_URI if any(n["source"] == "faa" for n in endpoints) else EPA_URI
            proof.update(native_member_hashes={n["uid"]: sha(n["data"]) for n in endpoints})
            operations.append({"op": "split_identity_source", "uid": b["left_uid"],
                               "parent": b["right_uid"], "locator": assertion_locator(b),
                               "source": "Reviewed engineering source identity contract", "uri": uri, "proof": proof})
            split_ids.add(b["id"])
    variant_bases = defaultdict(set)
    for variant_uid, base_uid in witnesses:
        variant_bases[variant_uid].add(base_uid)
    ambiguous = {uid for uid, parents in variant_bases.items() if len(parents) != 1}
    for (variant_uid, base_uid), witness in sorted(witnesses.items()):
        variant, base = source_nodes[variant_uid], source_nodes[base_uid]
        if variant_uid in ambiguous:
            inventory.append({"uid": variant_uid, "parent": base_uid, "status": "REVIEW",
                "reason": "Literal native model aggregate has several baseModel keys across retained configurations; some-record grouping does not establish full-scope parent inclusion",
                "candidate_parents": sorted(variant_bases[variant_uid])})
            continue
        proof = {"basis": "EXACT_RETAINED_EPA_MODEL_AND_BASEMODEL_NATIVE_CONFIGURATION_FIELDS",
                 **witness, "identity_scope": "SOURCE_NATIVE", "source_role": "EPA model variant",
                 "source_relation": "model+baseModel", "is_class_inclusion": False,
                 "no_commercial_generation_claim": True, "no_name_based_identity_merge": True,
                 "allowed_views": ["strict", "taxonomy", "membership", "unified"],
                 "license": "US federal public-domain data"}
        relation = "CONFIGURATION_OF" if variant["role"] == "CONFIGURATION" else "NATIVE_DESIGN_PARENT"
        existing = c.execute("SELECT 1 FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND status='ACTIVE' LIMIT 1",
                             (variant_uid, base_uid, relation)).fetchone()
        status = "EXISTING_NATIVE_PARENT_PRESERVED" if existing else "PREPARED_NATIVE_PARENT"
        if (variant["component_id"] == base["component_id"] and len(base_variants[base_uid]) == 1
                and witness["native_fields"]["model"] == witness["native_fields"]["baseModel"]):
            status = "SAME_NATIVE_AGGREGATE_SCOPE_NO_SELF_ARC"
        if not existing:
            if status != "SAME_NATIVE_AGGREGATE_SCOPE_NO_SELF_ARC":
                operations.append({"op": "link", "uid": variant_uid, "parent": base_uid,
                                   "relation": relation, "source": "EPA literal model/baseModel native hierarchy",
                                   "uri": witness["uri"], "proof": proof})
        inventory.append({"uid": variant_uid, "parent": base_uid,
                          "source_role": variant["role"], "parent_role": base["role"],
                          "native_fields": witness["native_fields"], "relation": relation, "status": status})
    missing = sorted(all_epa_variants - {key[0] for key in witnesses})
    inventory.extend({"uid": uid, "status": "REVIEW", "reason": "No complete retained native configuration pair passing field and evidence checks"} for uid in missing)
    withdrawn_components = set()
    component_claims = defaultdict(list)
    for operation in operations:
        if operation["op"] != "split_identity_source":
            continue
        for uid in (operation["uid"], operation["parent"]):
            component = c.execute("SELECT component_id FROM nodes WHERE uid=?", (uid,)).fetchone()[0]
            withdrawn_components.add(component)
            component_claims[component].append(operation["locator"])
    mapping_reviews, mapping_inventory = [], []
    for row in c.execute("SELECT * FROM dataset_targets ORDER BY dataset,class_id"):
        target = dict(row)
        node = c.execute("SELECT component_id FROM nodes WHERE uid=?", (target["target_uid"],)).fetchone()
        affected = bool(node and node[0] in withdrawn_components)
        depends_on_contraction = "SAME_CONCEPT" in target["identity_basis"]
        review = affected and depends_on_contraction and target["decision_status"] == "VERIFIED"
        mapping_inventory.append({"dataset": target["dataset"], "class_id": target["class_id"],
            "label": target["label"], "uid": target["target_uid"],
            "identity_basis": target["identity_basis"], "withdrawn_identity_component": affected,
            "basis_depends_on_contraction": depends_on_contraction,
            "status": "ANNOTATION_SCOPE_REVIEW" if review else "ORIGINAL_MAPPING_PRESERVED"})
        if review:
            prior_check = c.execute("SELECT * FROM dataset_mapping_checks WHERE dataset=? AND class_id=?",
                (target["dataset"], target["class_id"])).fetchone()
            mapping_reviews.append({"before": target, "before_sha256": sha(canonical(target)),
                "before_check": dict(prior_check) if prior_check else None,
                "proof": {"basis": "FROZEN_MAPPING_DEPENDS_ON_WITHDRAWN_UNPROVEN_IDENTITY_CONTRACTION",
                    "scope_observation": "The retained mapping declares a unique SAME_CONCEPT component as its identity basis. Source-name contraction claims in that component have been withdrawn; no independent commercial scope crosswalk is supplied by its frozen pass witness. Native annotation identity remains valid in its separate namespace.",
                    "withdrawn_claim_locators": list({canonical(x): x for x in component_claims[node[0]]}.values()),
                    "entity_identity_and_relations_invalidated": False,
                    "source_native_scope_target": native_uid("variant", target["label"]) if target["dataset"] == "fgvc_aircraft" else None,
                    "status": "ANNOTATION_SCOPE_REVIEW", "world_exact_identity_verified": False,
                    "source_uri": FGVC_URI if target["dataset"] == "fgvc_aircraft" else EPA_URI,
                    "license": "Derived mapping scope audit; original evidence and mapping retained in history"}})
    payload = {"schema_version": 1, "baseline_database": str(database.resolve()),
               "fgvc_cohort": cohort, "nodes": nodes, "scope_targets": targets,
               "operations": operations, "epa_inventory": inventory,
               "edge_dispositions": edge_dispositions,
               "corrected_roles": corrected_roles,
               "world_mapping_reviews": mapping_reviews,
               "mapping_dependency_inventory": mapping_inventory,
               "epa_rejected_witnesses": rejected, "identity_claim_inventory": cross_bridge_inventory}
    payload["manufacturer_catalogs"] = [
        {"manufacturer": maker, "relationship": "SOURCE_NATIVE_MANUFACTURER_DIRECTORY",
         "variants": [native_uid("variant", row["variant"]) for row in cohort["hierarchy"] if row["manufacturer"] == maker],
         "families": sorted({native_uid("family", row["family"]) for row in cohort["hierarchy"] if row["manufacturer"] == maker}),
         "is_class_inclusion": False, "is_design_lineage": False}
        for maker in sorted({row["manufacturer"] for row in cohort["hierarchy"]})]
    payload["identity_disposition_ledger"] = []
    for operation in operations:
        if operation["op"] != "split_identity_source":
            continue
        locator = operation["locator"]
        rows = c.execute("SELECT * FROM bridges WHERE left_uid=? AND right_uid=? AND source=? AND relation=?",
            tuple(locator[key] for key in ("left_uid", "right_uid", "source", "relation"))).fetchall()
        original = next(row for row in rows if source_assertion_sha256(row) == locator["content_sha256"])
        payload["identity_disposition_ledger"].append({"locator": locator,
            "disposition_category": operation["proof"]["disposition_category"],
            "original_source_assertion": dict(original), "review": operation["proof"]})
    if sources:
        payload["external_sources"] = json.loads(Path(sources).read_text())
    if baseline_labels:
        labels = json.loads(Path(baseline_labels).read_text())
        comps = json.loads(Path(conflict_components).read_text()) if conflict_components else []
        relevant = [r for r in labels if r["dataset"] in {"fgvc_aircraft", "stanford_cars"}]
        native_targets = {(t["dataset"], t["class_id"]): t for t in targets}
        payload["label_issue_ledger"] = []
        withdrawn_members = {op[key] for op in operations if op["op"] == "split_identity_source" for key in ("uid", "parent")}
        for r in relevant:
            affected = [q for q in comps if q["dataset"] == r["dataset"] and any(str(t["class_id"]) == str(r["class_id"]) for t in q["labels_with_ancestor_component"])]
            if not r.get("reason") and not affected:
                continue
            native = native_targets.get((r["dataset"], r["class_id"]))
            payload["label_issue_ledger"].append({"dataset": r["dataset"], "class_id": r["class_id"],
                "label": r["label"], "original_target_uid": r["uid"], "baseline_reason": r.get("reason"),
                "baseline_ancestor_conflicts": [q["component_id"] for q in affected],
                "identity_source_disposition": "UNSUPPORTED_CONTRACTION_WITHDRAWN" if r["uid"] in withdrawn_members or any(m["uid"] in withdrawn_members for q in affected for m in q["members"]) else "RETAINED_FOR_INDEPENDENT_GRAIN_REVIEW",
                "native_source_target": native["source_uid"] if native else None,
                "world_mapping_status": "PRESERVED; source-native admission reported separately",
                "remaining": "Commercial exact range/generation equality requires independent documentary crosswalk; coarse ancestors remain legitimate"})
    c.close()
    (output / INPUT_NAME).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    (output / OPERATIONS_NAME).write_text("".join(canonical(op) + "\n" for op in operations))
    summary = {"native_fgvc_variants": 100, "native_fgvc_families": len(families),
               "native_fgvc_scope_mappings": len(targets), "native_epa_variants_total": len(all_epa_variants),
               "native_epa_variant_base_links_prepared": sum(r['status'] == 'PREPARED_NATIVE_PARENT' for r in inventory),
               "native_epa_variant_base_links_preserved": sum(r['status'] == 'EXISTING_NATIVE_PARENT_PRESERVED' for r in inventory),
               "native_epa_equal_aggregate_scopes_no_self_arc": sum(r['status'] == 'SAME_NATIVE_AGGREGATE_SCOPE_NO_SELF_ARC' for r in inventory),
               "native_epa_variants_review": len(missing) + len(ambiguous),
               "native_epa_variants_ambiguous_historical_base_keys": len(ambiguous),
               "exact_identity_claims_withdrawn": len(split_ids),
               "all_dataset_mappings_dependency_audited": len(mapping_inventory),
               "world_mappings_source_scope_review": len(mapping_reviews),
               "operations": dict(Counter(op["op"] for op in operations)),
               "source_database_modified": False, "input_sha256": sha((output / INPUT_NAME).read_bytes()),
               "operations_sha256": sha((output / OPERATIONS_NAME).read_bytes())}
    summary["identity_dispositions_by_category"] = dict(Counter(
        row["disposition_category"] for row in payload["identity_disposition_ledger"]))
    summary["independent_scope_equivalence_claims_preserved"] = sum(
        row["status"] == "PRESERVED_INDEPENDENT_SCOPE_EQUIVALENCE" for row in cross_bridge_inventory)
    (output / "structure_engineering_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def apply_structure_engineering(m):
    """Replay after shared role/identity adjudication, before graph/cache builds."""
    path = m.inputs / INPUT_NAME
    if not path.exists():
        return {"status": "not_requested"}
    payload = json.loads(path.read_text())
    operations = [json.loads(line) for line in (m.inputs / OPERATIONS_NAME).read_text().splitlines() if line]
    if operations != payload["operations"]:
        raise ValueError("Frozen engineering operation file differs from its manifest")
    # Preflight *all* protected old source payloads before any write.
    hashes = {}
    def collect_hashes(proof):
        if isinstance(proof, list):
            for item in proof:
                collect_hashes(item)
        elif isinstance(proof, dict):
            hashes.update(proof.get("native_member_hashes", {}))
            if proof.get("native_record_uid") and proof.get("native_record_sha256"):
                hashes[proof["native_record_uid"]] = proof["native_record_sha256"]
            if proof.get("uid") and proof.get("sha256") and proof.get("fields"):
                hashes[proof["uid"]] = proof["sha256"]
            if proof.get("native_record_sha256") and proof.get("locator", {}).get("subject_uid"):
                hashes[proof["locator"]["subject_uid"]] = proof["native_record_sha256"]
            for item in proof.values():
                if isinstance(item, (dict, list)):
                    collect_hashes(item)
    for op in operations:
        proof = op["proof"]
        collect_hashes(proof)
        if proof.get("native_record_sha256") and not proof.get("native_record_uid"):
            hashes[op["uid"]] = proof["native_record_sha256"]
    for item in payload["identity_claim_inventory"]:
        if item.get("independent_scope_equivalence"):
            collect_hashes(item["independent_scope_equivalence"])
    for uid, expected in hashes.items():
        row = m.c.execute("SELECT data FROM nodes WHERE uid=?", (uid,)).fetchone()
        if not row or sha(row[0]) != expected:
            raise ValueError("Protected native engineering payload drift: " + uid)
    checked_dispositions = []
    for disposition in payload.get("edge_dispositions", []):
        locator = disposition["locator"]
        keys = ("child_uid", "parent_uid", "relation", "source", "layer")
        rows = m.c.execute("SELECT * FROM edges WHERE " + " AND ".join(key + "=?" for key in keys),
                           tuple(locator[key] for key in keys)).fetchall()
        matches = [row for row in rows if source_assertion_sha256(row) == locator["content_sha256"]]
        if len(matches) != 1:
            raise ValueError("Reviewed prior class assertion changed or is ambiguous")
        checked_dispositions.append((disposition, matches[0]))
    counts = Counter()
    fingerprint = sha(path.read_bytes())
    for review in payload.get("world_mapping_reviews", []):
        original = review["before"]
        current = m.c.execute("SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?",
            (original["dataset"], original["class_id"])).fetchone()
        provenance = json.loads(current["provenance"] or "{}") if current else {}
        if provenance.get("structure_engineering_world_review_sha256") == fingerprint:
            continue
        if not current or sha(canonical(dict(current))) != review["before_sha256"]:
            raise ValueError("World mapping drift before engineering identity dependency review")
        proof = {**review["proof"], "input_sha256": fingerprint, "original_record": original,
                 "original_mapping_check": review["before_check"]}
        eid = m.evidence("Reviewed engineering mapping dependency", proof["source_uri"], proof, "DATASET_MAPPING_SCOPE_REVIEW")
        provenance["structure_engineering_world_review_sha256"] = fingerprint
        after = {**original, "decision_status": "REVIEW",
            "identity_basis": "World scope review: prior contraction-dependent mapping retained in history",
            "provenance": canonical(provenance)}
        m.c.execute("INSERT OR IGNORE INTO dataset_mapping_history(id,dataset,class_id,namespace,source_version,before_record,after_record,evidence_id,decision) VALUES (?,?,?,?,?,?,?,?,?)",
            (sha(canonical(proof)), original["dataset"], original["class_id"], "world", "v1.10.1",
             canonical(original), canonical(after), eid, "ANNOTATION_SCOPE_REVIEW"))
        m.c.execute("UPDATE dataset_targets SET decision_status=?,identity_basis=?,provenance=? WHERE dataset=? AND class_id=?",
            (after["decision_status"], after["identity_basis"], after["provenance"], original["dataset"], original["class_id"]))
        m.c.execute("INSERT OR REPLACE INTO dataset_mapping_checks(dataset,class_id,status,reason,proof) VALUES (?,?,?,?,?)",
            (original["dataset"], original["class_id"], "ANNOTATION_SCOPE_REVIEW", review["proof"]["scope_observation"], canonical(proof)))
        m.change("structure_engineering", "mapping_scope", original["dataset"] + ":" + original["class_id"], original, after, proof)
        counts["world_mapping_scope_reviews"] += 1
    for disposition, row in checked_dispositions:
        if row["status"] == "ACTIVE":
            m.c.execute("UPDATE edges SET status='HIERARCHY_SUPERSEDED',reason=? WHERE id=?",
                ("OEM-reviewed named design cannot be an ordinary class inclusion", row["id"]))
            m.change("structure_engineering", "source_edge", row["id"], dict(row),
                {"status": "HIERARCHY_SUPERSEDED"}, disposition["proof"])
            counts["named_design_prior_isa_superseded"] += 1
        elif row["status"] != "HIERARCHY_SUPERSEDED":
            raise ValueError("Reviewed prior class assertion disposition drift")
    for node in payload["nodes"]:
        counts["new_source_native_nodes"] += m.add_node(node["uid"], node["label"], node["role"],
            node["domain"], node["source"], node["uri"], node["proof"])
        m.alias(node["uid"], node["native_label"], node["source"], "en")
    for target in payload["scope_targets"]:
        values = [target[key] for key in ("dataset", "class_id", "namespace", "source_version", "source_uid", "role", "decision_status")]
        values += [canonical(target["proof"]), target["label"]]
        prior = m.c.execute("SELECT * FROM dataset_scope_targets WHERE dataset=? AND class_id=? AND namespace=? AND source_version=?", tuple(values[:4])).fetchone()
        if prior and (prior["source_uid"] != target["source_uid"] or prior["proof"] != values[-2]):
            raise ValueError("Native dataset namespace/version scope drift")
        m.c.execute("INSERT OR IGNORE INTO dataset_scope_targets(dataset,class_id,namespace,source_version,source_uid,role,decision_status,proof,label) VALUES (?,?,?,?,?,?,?,?,?)", values)
        counts["source_native_scope_mappings"] += prior is None
        if prior is None:
            eid = m.evidence("fgvc_aircraft_native", FGVC_URI, target["proof"], "DATASET_SOURCE_NATIVE_SCOPE")
            m.c.execute("INSERT OR IGNORE INTO dataset_mapping_history(id,dataset,class_id,namespace,source_version,before_record,after_record,evidence_id,decision) VALUES (?,?,?,?,?,?,?,?,?)",
                (sha(canonical(target)), target["dataset"], target["class_id"], target["namespace"],
                 target["source_version"], "{}", canonical(target), eid, "SOURCE_NATIVE_SCOPE_ADDED"))
    counts.update(apply_refinements(m, OPERATIONS_NAME))
    for node in payload["nodes"]:
        profile = m.c.execute("SELECT attributes FROM node_profiles WHERE uid=?", (node["uid"],)).fetchone()
        attrs = json.loads(profile[0])
        attrs.update(identity_scope="SOURCE_NATIVE", world_exact_identity_verified=False,
            source_native_identity_verified=True, source_native_namespace="fgvc-aircraft-2013b",
            native_source_version="2013b", source_native_unit=node["proof"]["native_unit"],
            semantic_grain=node["proof"]["semantic_grain"],
            native_rank="aircraft_family" if node["proof"]["native_unit"] == "family" else "aircraft_model")
        memberships = [row for row in payload["fgvc_cohort"]["hierarchy"] if
            (row["variant"] if node["proof"]["native_unit"] == "variant" else row["family"]) == node["native_label"]]
        attrs["source_native_manufacturers"] = sorted({row["manufacturer"] for row in memberships})
        m.c.execute("UPDATE node_profiles SET attributes=? WHERE uid=?", (canonical(attrs), node["uid"]))
    m.meta("structure_engineering_input_sha256", sha(path.read_bytes()))
    preserved = []
    for item in payload["identity_claim_inventory"]:
        if not item.get("independent_scope_equivalence"):
            continue
        proof = item["independent_scope_equivalence"]
        eid = m.evidence("Reviewed engineering same-object scope", FGVC_URI if "faa" in item["locator"]["source"] else EPA_URI,
            proof, "INDEPENDENT_SOURCE_SCOPE_EQUIVALENCE_REVIEW")
        preserved.append({"locator": item["locator"], "evidence_id": eid, "proof": proof})
    m.meta("structure_engineering_protected_identity_scope_reviews", preserved)
    m.meta("fgvc_source_native_manufacturer_catalogs", payload.get("manufacturer_catalogs", []))
    m.meta("fgvc_source_native_namespace", {"namespace": "fgvc-aircraft-2013b", "source_version": "2013b",
        "source": "fgvc_aircraft_native", "task_boundary_roots": ["wordnet31:02689427-n"],
        "manufacturer_relationship": "CATALOG_FACET_ONLY", "world_identity_assertions_added": 0})
    m.c.commit()
    return dict(counts)
