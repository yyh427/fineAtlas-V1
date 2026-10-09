#!/usr/bin/env python3
"""Freeze exact annotation repairs, source-native designs and taxon evidence.

Preparation reads the protected database and source snapshots. Application is
explicit and intended only for a new candidate via apply_scope_repairs(m).
Source-native navigation never certifies a dataset's exact world identity.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas.hierarchy import apply_refinements, validate_link_roles

CHECKLIST_FIELDS = ("English_name_AviList", "English_name_Clements_v2025", "English_name_BirdLife_v10")
SOURCE_URI = "https://www.robots.ox.ac.uk/~vgg/data/fgvc-aircraft/"
OTT_SHA = "b852611c131ebe678f8b2e9d5fe6b7fae073bb0f563230ef684e03ee9e151389"
INPUT_NAME = "annotation_scope_repairs.json"
NAVIGATION_NAME = "annotation_taxonomic_navigation.jsonl"
HISTORICAL_NAME = "annotation_historical_alias_repairs.json"


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def typography_key(name):
    """Full-label typography only; retain every letter, including possessive s.

    Forster's and Forsters converge; Forster and Forsters do not. No suffix,
    lexical prefix, edit-distance or biological-range inference is permitted.
    """
    return "".join(ch for ch in unicodedata.normalize("NFKC", name).casefold() if ch.isalnum())


def checklist_index(records):
    index = defaultdict(set)
    species = {}
    for record in records:
        row = record["row"]
        if str(row.get("Taxon_rank", "")).casefold() != "species":
            continue
        species[record["uid"]] = record
        for field in CHECKLIST_FIELDS:
            name = str(row.get(field, "")).strip()
            if name:
                index[typography_key(name)].add(record["uid"])
    return index, species


def exact_candidate(label, index, reviewed_aliases=None):
    key = typography_key(label)
    alias = (reviewed_aliases or {}).get(key)
    if alias:
        # An explicit full-name correction is local, documentary and bounded.
        key = typography_key(alias["primary_name"])
    candidates = index.get(key, set())
    if len(candidates) != 1:
        return None
    return next(iter(candidates)), alias


def source_annotations(directory):
    """Join all three authoritative splits by image ID; freeze only metadata."""
    wanted = {"CRJ-200", "CRJ-700", "CRJ-900"}
    records = []
    files = []
    for split in ("train", "val", "test"):
        fields = {}
        for field in ("variant", "family", "manufacturer"):
            path = directory / ("images_" + field + "_" + split + ".txt")
            raw = path.read_bytes()
            files.append({"filename": path.name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
            pairs = [line.split(" ", 1) for line in raw.decode().splitlines() if line]
            fields[field] = dict(pairs)
            if len(fields[field]) != len(pairs):
                raise ValueError("Duplicate image ID in " + path.name)
        if len({frozenset(rows) for rows in fields.values()}) != 1:
            raise ValueError("Annotation ID sets differ within " + split)
        for image_id, variant in fields["variant"].items():
            if variant in wanted:
                records.append({"image_id": image_id, "split": split, "variant": variant,
                                "family": fields["family"][image_id], "manufacturer": fields["manufacturer"][image_id]})
    counts = Counter((r["variant"], r["family"], r["manufacturer"]) for r in records)
    expected = Counter({("CRJ-200", "CRJ-200", "Canadair"): 100,
                        ("CRJ-700", "CRJ-700", "Canadair"): 100,
                        ("CRJ-900", "CRJ-700", "Canadair"): 100})
    if counts != expected or len({r["image_id"] for r in records}) != 300:
        raise ValueError("CRJ source cohort differs from the reviewed 2013b annotation scope")
    return {"source_version": "FGVC-Aircraft 2013b", "source_uri": SOURCE_URI,
            "files": files, "records": sorted(records, key=lambda r: (r["split"], r["image_id"])),
            "source_hierarchy": [{"variant": v, "family": f, "manufacturer": m, "records": n}
                                 for (v, f, m), n in sorted(counts.items())],
            "source_license_scope": "Source-derived label facts and citation only; no photographs or image rights redistributed"}


def validate_ott_records(snapshot):
    if snapshot["version"] != "3.7draft3" or snapshot["native_taxonomy_sha256"] != OTT_SHA:
        raise ValueError("Protected OTT source version/checksum differs")
    rows = {r["uid"]: r for r in snapshot["records"]}
    expected = {"509187": ("Centramoebida", "order", "5246821", "ncbi:555407"),
                "5246821": ("Longamoebia", "order", "673585", "ncbi:1485168"),
                "673585": ("Discosea", "class", "1064655", "ncbi:555280")}
    for uid, (name, rank, parent, external_id) in expected.items():
        row = rows.get(uid, {})
        if (row.get("name"), row.get("rank"), row.get("parent_uid")) != (name, rank, parent):
            raise ValueError("Frozen OTT taxon name/rank/parent differs: " + uid)
        if external_id not in row["sourceinfo"].split(",") or not row.get("raw_line_sha256"):
            raise ValueError("Frozen OTT source identifiers or row hash missing: " + uid)
    return rows


def retained_node(c, uid):
    node = c.execute("SELECT * FROM nodes WHERE uid=?", (uid,)).fetchone()
    if not node or node["visibility"] != "ACTIVE":
        raise ValueError("Missing active source endpoint: " + uid)
    return {"uid": uid, "label": node["label"], "rank": node["rank"], "component_id": node["component_id"],
            "native_record_sha256": hashlib.sha256(node["data"].encode()).hexdigest()}


def prepare(database, checklist, annotations, ott_snapshot, output):
    c = sqlite3.connect(database.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    c.row_factory = sqlite3.Row
    output.mkdir(parents=True, exist_ok=True)
    native_records = json.loads(checklist.read_text())
    index, species = checklist_index(native_records)
    # This is the single documentary typo correction. It is not a fuzzy rule.
    aliases = {typography_key("Artic Tern"): {"primary_name": "Arctic Tern",
               "reason": "Exact reviewed dataset spelling correction; same retained Sterna paradisaea identity",
               "required_scientific_name": "Sterna paradisaea"}}
    cub = []
    unresolved = []
    for check in c.execute("SELECT * FROM dataset_mapping_checks WHERE dataset='cub200' AND status='ANNOTATION_SCOPE_REVIEW' ORDER BY CAST(class_id AS INTEGER)"):
        target = dict(c.execute("SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?", (check["dataset"], check["class_id"])).fetchone())
        match = exact_candidate(target["label"], index, aliases)
        if not match:
            unresolved.append({"class_id": target["class_id"], "label": target["label"], "target_uid": target["target_uid"],
                               "decision": "ANNOTATION_SCOPE_REVIEW", "reason": "No unique exact full primary species name; historical/split/genus scope remains documentary review"})
            continue
        primary_uid, alias = match
        primary = retained_node(c, primary_uid)
        original = retained_node(c, target["target_uid"])
        record = species[primary_uid]
        if original["component_id"] != primary["component_id"]:
            unresolved.append({"class_id": target["class_id"], "label": target["label"], "target_uid": target["target_uid"],
                               "decision": "ANNOTATION_SCOPE_REVIEW", "reason": "Exact names do not authorize a new cross-source identity or species-range change"})
            continue
        if alias and record["row"]["Scientific_name"] != alias["required_scientific_name"]:
            raise ValueError("Audited annotation typo has a different biological scope")
        proof = {"basis": "EXACT_PRIMARY_FULL_NAME_TYPOGRAPHY_WITH_EXISTING_IDENTITY_SCOPE",
                 "source_version": "AviList v2025b", "source_uri": record["source_uri"],
                 "source_sha256": record["source_sha256"], "scientific_name": record["row"]["Scientific_name"],
                 "sequence": record["row"]["Sequence"], "primary_uid": primary_uid,
                 "original_target_uid": target["target_uid"], "primary_record": record,
                 "primary_node": primary, "original_node": original, "reviewed_alias": alias,
                 "label_normalization": "Full-label NFKC/case/punctuation/spacing only; all letters including possessive s retained",
                 "cross_source_identity_assertions_added": 0, "species_scope_changes": 0,
                 "license": "AviList CC BY 4.0", "retrieved_utc": "2026-10-08"}
        cub.append({"dataset": "cub200", "class_id": target["class_id"], "label": target["label"],
                    "before": target, "before_sha256": digest(target), "before_check": dict(check),
                    "resolved_target_uid": target["target_uid"], "proof": proof})
    cohort = source_annotations(annotations)
    crj_target = dict(c.execute("SELECT * FROM dataset_targets WHERE dataset='fgvc_aircraft' AND label='CRJ-700'").fetchone())
    if crj_target["target_uid"] != "wikidata-v4:Q137829174":
        raise ValueError("CRJ target no longer matches the reviewed frozen source record")
    source_nodes = []
    source_links = []
    for unit, names, role in (("family", ("CRJ-200", "CRJ-700"), "MODEL_FAMILY"),
                              ("variant", ("CRJ-200", "CRJ-700", "CRJ-900"), "MODEL")):
        for name in names:
            uid = "fgvc-aircraft-2013b:" + unit + ":" + name.casefold()
            proof = {"basis": "EXPLICIT_AUTHOR_HIERARCHY_UNIT_WITH_COMPLETE_THREE_SPLIT_ANNOTATION_JOIN",
                     "source_version": cohort["source_version"], "source_uri": SOURCE_URI,
                     "annotation_cohort_sha256": digest(cohort), "native_label": name, "native_unit": unit,
                     "native_rank": "aircraft_family" if unit == "family" else "aircraft_model",
                     "source_role": "Author-declared aircraft " + unit, "allowed_views": ["strict", "taxonomy", "membership"],
                     "semantic_grain": "SOURCE_NATIVE_AIRCRAFT_" + unit.upper(),
                     "world_exact_identity_verified": False, "no_name_based_identity_merge": True,
                     "license": cohort["source_license_scope"], "retrieved_utc": "2026-10-08"}
            source_nodes.append({"uid": uid, "native_label": name, "label": name + " [FGVC " + unit + "]",
                                 "role": role, "proof": proof})
            if unit == "family":
                source_links.append({"uid": uid, "parent": "wordnet31:02689427-n", "relation": "DESIGN_TYPE_OF", "proof": proof})
            else:
                family = "CRJ-200" if name == "CRJ-200" else "CRJ-700"
                source_links.append({"uid": uid, "parent": "fgvc-aircraft-2013b:family:" + family.casefold(),
                                     "relation": "SERIES_MEMBER_OF", "proof": {**proof, "explicit_native_family": family,
                                     "membership_basis": "All source annotation rows for this variant agree on the family"}})
    rows = validate_ott_records(json.loads(ott_snapshot.read_text()))
    child = retained_node(c, "ott:509187")
    parent = retained_node(c, "ott:673585")
    if (child["label"], child["rank"], parent["label"], parent["rank"]) != ("Centramoebida", "order", "Discosea", "class"):
        raise ValueError("Current taxon endpoint scope differs")
    original_edge = dict(c.execute("SELECT * FROM edges WHERE id=8107652").fetchone())
    if (original_edge["child_uid"], original_edge["parent_uid"], original_edge["status"]) != ("ott:509187", "ott:5246821", "REVIEW"):
        raise ValueError("Disputed original intermediate edge no longer matches")
    ott_proof = {"basis": "INDEPENDENT_PHYLOGENOMIC_HIGHER_TAXON_PLACEMENT_AVOIDS_DISPUTED_INTERMEDIATE",
                 "native_source_version": "OTT 3.7draft3", "native_source_sha256": OTT_SHA,
                 "native_record": rows["509187"], "native_parent_record": rows["673585"],
                 "disputed_intermediate_record": rows["5246821"], "original_edge_id": 8107652,
                 "original_edge_sha256": digest(original_edge), "original_status_preserved": "REVIEW",
                 "native_record_sha256": child["native_record_sha256"], "parent_node": parent,
                 "source_uri": "https://doi.org/10.1016/j.ympev.2017.06.019",
                 "independent_publication": {"authors": "Yonas I. Tekle; Fiona C. Wood", "year": 2017,
                   "doi": "10.1016/j.ympev.2017.06.019", "pmid": "28669813",
                   "findings_paraphrase": "Discosea is recovered as a monophyletic group including its taxonomic orders and Centramoebida; Longamoebia sensu Smirnov 2011 is rejected as nonmonophyletic. The accepted higher placement omits that disputed intermediate."},
                 "current_catalogue_corroboration": {"source_uri": "https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=555407",
                   "child_taxid": "555407", "higher_parent_taxid": "555280", "higher_path": ["Discosea", "Longamoebia", "Centramoebida"],
                   "independence_note": "NCBI is an OTT input and is corroboration only; the phylogenomic publication is the independent evidence"},
                 "strict_classification": False, "world_identity_assertions_added": 0,
                 "placement_scope": "Corroborated higher taxon placement; original complete intermediate taxonomy is not reconstructed",
                 "source_flags_preserved": True, "license": "Derived taxonomic facts; author citation and original source attribution retained",
                 "retrieved_utc": "2026-10-08"}
    navigation = {"op": "link", "uid": "ott:509187", "parent": "ott:673585", "relation": "TAXONOMIC_PARENT",
                  "axis": "native_taxonomic_placement", "source": "Independent phylogenomic higher-taxonomy evidence",
                  "uri": ott_proof["source_uri"], "proof": ott_proof}
    payload = {"schema": "FINEATLAS_ANNOTATION_SCOPE_REPAIRS_V1", "cub_repairs": cub, "cub_unresolved": unresolved,
               "crj_cohort": cohort, "crj_nodes": source_nodes, "crj_links": source_links,
               "crj_target": {"before": crj_target, "before_sha256": digest(crj_target),
                              "resolved_target_uid": "fgvc-aircraft-2013b:variant:crj-700"},
               "retained_nodes": [child, parent, retained_node(c, "wordnet31:02689427-n")],
               "ott_original_edge": original_edge, "ott_original_edge_sha256": digest(original_edge),
               "navigation_input_sha256": hashlib.sha256((json.dumps(navigation, ensure_ascii=False) + "\n").encode()).hexdigest()}
    (output / INPUT_NAME).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    (output / NAVIGATION_NAME).write_text(json.dumps(navigation, ensure_ascii=False) + "\n")
    summary = {"cub_identity_scope_repairs": len(cub), "cub_remaining_annotation_reviews": len(unresolved),
               "cub_repaired_labels": [{"class_id": r["class_id"], "label": r["label"]} for r in cub],
               "crj_source_nodes": len(source_nodes), "crj_source_typed_links": len(source_links),
               "crj_world_identity_verified": False, "crj_original_target_retained": crj_target["target_uid"],
               "ott_higher_taxonomy_links": 1, "ott_disputed_intermediate_decision": "REVIEW preserved",
               "strict_IS_A_added": 0, "identity_merges_added": 0, "input_sha256": digest(payload)}
    (output / "annotation_scope_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    c.close()
    return summary


def _validate_retained(c, record):
    actual = retained_node(c, record["uid"])
    if actual != record:
        raise ValueError("Retained endpoint source/scope changed: " + record["uid"])


def prepare_historical_aliases(database, checklist, evidence_path, output):
    """Accept individually reviewed full-name bridges, never word deletions.

    The documentary bridge is additional to an unchanged existing species
    identity group. A split's old name cannot certify one modern daughter.
    """
    c = sqlite3.connect(database.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    c.row_factory = sqlite3.Row
    index, species = checklist_index(json.loads(checklist.read_text()))
    evidence = json.loads(evidence_path.read_text())
    repairs = []
    for rule in evidence["reviewed_full_name_bridges"]:
        if rule.get("biological_scope_changed") is not False or not rule.get("source_evidence"):
            raise ValueError("Historical full-name bridge lacks unchanged biological scope evidence")
        if not all(r.get("source_uri") and r.get("finding_paraphrase") for r in rule["source_evidence"]):
            raise ValueError("Historical full-name evidence lacks a primary citation")
        match = exact_candidate(rule["primary_name"], index)
        if not match:
            raise ValueError("Reviewed historical name has no unique full modern species name")
        primary_uid = match[0]
        primary_record = species[primary_uid]
        if primary_record["row"]["Scientific_name"] != rule["required_scientific_name"]:
            raise ValueError("Reviewed historical name has different scientific scope")
        target = c.execute("SELECT * FROM dataset_targets WHERE dataset='cub200' AND class_id=?", (rule["class_id"],)).fetchone()
        check = c.execute("SELECT * FROM dataset_mapping_checks WHERE dataset='cub200' AND class_id=?", (rule["class_id"],)).fetchone()
        if not target or target["label"] != rule["annotation_label"] or not check or check["status"] != "ANNOTATION_SCOPE_REVIEW":
            raise ValueError("Historical annotation differs from the individually reviewed row")
        before = dict(target)
        primary_node = retained_node(c, primary_uid)
        original_node = retained_node(c, before["target_uid"])
        if original_node["component_id"] != primary_node["component_id"]:
            raise ValueError("Historical common-name bridge cannot create an identity or shrink scope")
        proof = {"basis": "DOCUMENTED_FULL_HISTORICAL_NAME_WITH_UNCHANGED_EXISTING_SPECIES_SCOPE",
                 "source_uri": rule["source_evidence"][0]["source_uri"], "source_version": "AviList v2025b with bounded historical-name primary evidence",
                 "source_sha256": primary_record["source_sha256"], "scientific_name": rule["required_scientific_name"],
                 "primary_uid": primary_uid, "primary_record": primary_record, "primary_node": primary_node,
                 "original_node": original_node, "reviewed_full_name_bridge": rule,
                 "historical_evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                 "species_scope_changes": 0, "cross_source_identity_assertions_added": 0,
                 "label_normalization": "Audited complete-name correspondence only; no general prefix/suffix deletion or geographic inference",
                 "license": "Derived common-name/taxon facts; original primary citations retained; AviList CC BY 4.0",
                 "retrieved_utc": "2026-10-08"}
        repairs.append({"before": before, "before_sha256": digest(before), "before_check": dict(check),
                        "resolved_target_uid": before["target_uid"], "proof": proof})
    output.mkdir(parents=True, exist_ok=True)
    payload = {"schema": "FINEATLAS_DOCUMENTED_FULL_NAME_BRIDGES_V1", "repairs": repairs,
               "rejected_ambiguous_bridges": evidence.get("rejected_ambiguous_bridges", [])}
    (output / HISTORICAL_NAME).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    summary = {"documented_full_name_repairs": len(repairs), "labels": [r["before"]["label"] for r in repairs],
               "new_world_identity_merges": 0, "species_scope_changes": 0, "input_sha256": digest(payload)}
    (output / "annotation_historical_alias_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    c.close()
    return summary


def apply_scope_supplement(m):
    """Replay bounded documentary name bridges after the initial scope batch."""
    path = m.inputs / HISTORICAL_NAME
    if not path.exists():
        return {"status": "not_requested"}
    payload = json.loads(path.read_text())
    if payload.get("schema") != "FINEATLAS_DOCUMENTED_FULL_NAME_BRIDGES_V1":
        raise ValueError("Unsupported documentary annotation bridge schema")
    c = m.c
    fingerprint = digest(payload)
    for repair in payload["repairs"]:
        _validate_retained(c, repair["proof"]["primary_node"])
        _validate_retained(c, repair["proof"]["original_node"])
        before = repair["before"]
        row = c.execute("SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?", (before["dataset"], before["class_id"])).fetchone()
        if not row:
            raise ValueError("Historical target missing")
        if digest(dict(row)) != repair["before_sha256"]:
            prior = json.loads(row["provenance"] or "{}").get("unified_scope_repair", {})
            if (prior.get("input_sha256") != fingerprint or row["label"] != before["label"]
                    or row["target_uid"] != repair["resolved_target_uid"] or row["decision_status"] != "VERIFIED"):
                raise ValueError("Historical source annotation drift before replay")
    c.executescript("""
      CREATE TABLE IF NOT EXISTS annotation_scope_target_history(stage TEXT,dataset TEXT,class_id TEXT,original_record TEXT,PRIMARY KEY(stage,dataset,class_id));
      CREATE TABLE IF NOT EXISTS dataset_target_history(dataset TEXT,class_id TEXT,original_target_uid TEXT,original_record TEXT,PRIMARY KEY(dataset,class_id));
      CREATE TABLE IF NOT EXISTS dataset_mapping_checks(dataset TEXT,class_id TEXT,status TEXT,reason TEXT,proof TEXT,PRIMARY KEY(dataset,class_id));
    """)
    count = 0
    for repair in payload["repairs"]:
        before = repair["before"]
        current = c.execute("SELECT provenance FROM dataset_targets WHERE dataset=? AND class_id=?", (before["dataset"], before["class_id"])).fetchone()
        if json.loads(current[0] or "{}").get("unified_scope_repair", {}).get("input_sha256") == fingerprint:
            continue
        proof = {**repair["proof"], "input_sha256": fingerprint, "original_target_uid": before["target_uid"],
                 "resolved_target_uid": repair["resolved_target_uid"]}
        stage = "v1.10-documented-annotation-alias"
        for table, values in (("dataset_target_history", (before["dataset"], before["class_id"], before["target_uid"], canonical_json(before))),
                              ("annotation_scope_target_history", (stage, before["dataset"], before["class_id"], canonical_json(before)))):
            c.execute("INSERT OR IGNORE INTO " + table + " VALUES(?,?,?,?)", values)
        eid = m.evidence("Documented complete historical annotation name", proof["source_uri"], proof, "SOURCE_NATIVE_LABEL_ALIGNMENT")
        provenance = json.loads(before["provenance"] or "{}")
        provenance["unified_scope_repair"] = proof
        ids = sorted(set(json.loads(before["evidence_ids"] or "[]") + [eid]))
        reason = "Primary documentary full-name bridge; unchanged retained species scope; no lexical or geographic narrowing"
        c.execute("UPDATE dataset_targets SET decision_status='VERIFIED',identity_basis=?,granularity_basis=?,evidence_ids=?,provenance=? WHERE dataset=? AND class_id=?",
                  (reason, "Species scope preserved under documented English-name/genus-combination changes", canonical_json(ids), canonical_json(provenance), before["dataset"], before["class_id"]))
        c.execute("INSERT OR REPLACE INTO dataset_mapping_checks VALUES(?,?,?,?,?)",
                  (before["dataset"], before["class_id"], "PRIMARY_SOURCE_CORROBORATED", reason, canonical_json(proof)))
        after = dict(c.execute("SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?", (before["dataset"], before["class_id"])).fetchone())
        m.alias(before["target_uid"], before["label"], "Documented complete historical annotation name", "en")
        m.change(stage, "task", before["dataset"] + ":" + before["class_id"], before, after, proof)
        count += 1
    m.meta("annotation_historical_alias_input_sha256", fingerprint)
    m.meta("annotation_historical_alias_repaired", count)
    c.commit()
    return {"documented_full_name_repairs": count, "species_scope_changes": 0, "identity_merges_added": 0}


def apply_scope_repairs(m):
    """Apply frozen deltas only; no graph construction, source downloads or merge."""
    path = m.inputs / INPUT_NAME
    if not path.exists():
        return {"status": "not_requested"}
    payload = json.loads(path.read_text())
    if payload.get("schema") != "FINEATLAS_ANNOTATION_SCOPE_REPAIRS_V1":
        raise ValueError("Unsupported annotation repair schema")
    navigation = m.inputs / NAVIGATION_NAME
    if hashlib.sha256(navigation.read_bytes()).hexdigest() != payload["navigation_input_sha256"]:
        raise ValueError("Frozen higher-taxonomy decision checksum differs")
    c = m.c
    for record in payload["retained_nodes"]:
        _validate_retained(c, record)
    for node in payload["crj_nodes"]:
        existing = c.execute("SELECT data,visibility,label FROM nodes WHERE uid=?", (node["uid"],)).fetchone()
        if existing:
            profile = c.execute("SELECT node_kind FROM node_profiles WHERE uid=?", (node["uid"],)).fetchone()
            if (json.loads(existing["data"]) != node["proof"] or existing["visibility"] != "ACTIVE"
                    or existing["label"] != node["label"] or not profile or profile[0] != node["role"]):
                raise ValueError("Existing native design UID has different scope")
    for repair in payload["cub_repairs"]:
        _validate_retained(c, repair["proof"]["primary_node"])
        _validate_retained(c, repair["proof"]["original_node"])
    edge = c.execute("SELECT * FROM edges WHERE id=?", (payload["ott_original_edge"]["id"],)).fetchone()
    if not edge or digest(dict(edge)) != payload["ott_original_edge_sha256"]:
        raise ValueError("Disputed original OTT assertion changed before repair")
    # Preflight every target before mutating any graph/source data.
    for repair in payload["cub_repairs"] + [payload["crj_target"]]:
        before = repair["before"]
        target = c.execute("SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?", (before["dataset"], before["class_id"])).fetchone()
        if not target:
            raise ValueError("Frozen target missing")
        if digest(dict(target)) != repair["before_sha256"]:
            prior = json.loads(target["provenance"] or "{}").get("unified_scope_repair", {})
            stable_fields = ("dataset", "class_id", "label")
            expected_status = "VERIFIED" if before["dataset"] == "cub200" else "VERIFIED_NATIVE_LABEL"
            if (prior.get("input_sha256") != digest(payload)
                    or any(target[key] != before[key] for key in stable_fields)
                    or target["target_uid"] != repair["resolved_target_uid"]
                    or target["decision_status"] != expected_status):
                raise ValueError("Dataset target drift before replay: " + before["dataset"] + ":" + before["class_id"])
    counts = Counter()
    c.executescript("""
      CREATE TABLE IF NOT EXISTS annotation_scope_target_history(stage TEXT,dataset TEXT,class_id TEXT,original_record TEXT,PRIMARY KEY(stage,dataset,class_id));
      CREATE TABLE IF NOT EXISTS dataset_target_history(dataset TEXT,class_id TEXT,original_target_uid TEXT,original_record TEXT,PRIMARY KEY(dataset,class_id));
      CREATE TABLE IF NOT EXISTS dataset_mapping_checks(dataset TEXT,class_id TEXT,status TEXT,reason TEXT,proof TEXT,PRIMARY KEY(dataset,class_id));
    """)
    stage = "v1.10-annotation-scope-repair"
    fingerprint = digest(payload)

    def update_target(repair, proof, decision, check_status, reason):
        before = repair["before"]
        current = dict(c.execute("SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?", (before["dataset"], before["class_id"])).fetchone())
        if json.loads(current["provenance"] or "{}").get("unified_scope_repair", {}).get("input_sha256") == fingerprint:
            return False
        c.execute("INSERT OR IGNORE INTO dataset_target_history VALUES(?,?,?,?)",
                  (before["dataset"], before["class_id"], before["target_uid"], canonical_json(before)))
        c.execute("INSERT OR IGNORE INTO annotation_scope_target_history VALUES(?,?,?,?)",
                  (stage, before["dataset"], before["class_id"], canonical_json(before)))
        proof = {**proof, "input_sha256": fingerprint, "original_target_uid": before["target_uid"],
                 "resolved_target_uid": repair["resolved_target_uid"]}
        source = "Reviewed annotation source scope"
        eid = m.evidence(source, proof["source_uri"], proof, "SOURCE_NATIVE_LABEL_ALIGNMENT")
        provenance = json.loads(before["provenance"] or "{}")
        provenance["unified_scope_repair"] = proof
        evidence_ids = sorted(set(json.loads(before["evidence_ids"] or "[]") + [eid]))
        c.execute("UPDATE dataset_targets SET target_uid=?,decision_status=?,identity_basis=?,granularity_basis=?,evidence_ids=?,provenance=? WHERE dataset=? AND class_id=?",
                  (repair["resolved_target_uid"], decision, reason, "Source-native scope and exact world identity are assessed separately; prior target retained in history",
                   canonical_json(evidence_ids), canonical_json(provenance), before["dataset"], before["class_id"]))
        c.execute("INSERT OR REPLACE INTO dataset_mapping_checks VALUES(?,?,?,?,?)",
                  (before["dataset"], before["class_id"], check_status, reason, canonical_json(proof)))
        after = dict(c.execute("SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?", (before["dataset"], before["class_id"])).fetchone())
        m.change(stage, "task", before["dataset"] + ":" + before["class_id"], before, after, proof)
        return True

    for repair in payload["cub_repairs"]:
        counts["cub_exact_scope_repairs"] += update_target(repair, repair["proof"], "VERIFIED", "PRIMARY_SOURCE_CORROBORATED",
                              "Unique full primary species name after reviewed typography; existing exact identity scope retained")
        m.alias(repair["resolved_target_uid"], repair["label"], "Reviewed dataset full-label typography", "en")
    source = "FGVC-Aircraft 2013b author-defined native hierarchy"
    c.execute("INSERT OR REPLACE INTO source_catalogs VALUES(?,?,?,?,?)",
              (source, SOURCE_URI, payload["crj_cohort"]["source_license_scope"], digest(payload["crj_cohort"]),
               canonical_json({"source_version": "2013b", "frozen_cohort_annotation_records": 300,
                               "native_family_units": 2, "native_variant_units": 3, "world_identity_assertions": 0})))
    for node in payload["crj_nodes"]:
        counts["new_source_design_nodes"] += m.add_node(node["uid"], node["label"], node["role"], "aircraft", source, SOURCE_URI,
                                node["proof"], "Author-defined " + node["proof"]["native_unit"] + " unit; exact commercial identity remains reviewed")
        retained = c.execute("SELECT data FROM nodes WHERE uid=?", (node["uid"],)).fetchone()
        profile = c.execute("SELECT node_kind,attributes FROM node_profiles WHERE uid=?", (node["uid"],)).fetchone()
        if not retained or json.loads(retained[0]) != node["proof"] or not profile or profile["node_kind"] != node["role"]:
            raise ValueError("Existing native design UID has different scope")
        attrs = json.loads(profile["attributes"])
        attrs.update(semantic_grain=node["proof"]["semantic_grain"], source_native_unit=node["proof"]["native_unit"],
                     world_exact_identity_verified=False, native_source_version="FGVC-Aircraft 2013b")
        c.execute("UPDATE node_profiles SET attributes=? WHERE uid=?", (canonical_json(attrs), node["uid"]))
        m.alias(node["uid"], node["native_label"], source, "en")
    for link in payload["crj_links"]:
        roles = [c.execute("SELECT coalesce(p.node_kind,'CLASS') FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?", (uid,)).fetchone()[0]
                 for uid in (link["uid"], link["parent"])]
        validate_link_roles(link["relation"], *roles)
        m.typed(link["uid"], link["parent"], link["relation"], link["proof"], source, SOURCE_URI)
    proof = {"basis": "VERIFIED_NATIVE_VARIANT_LABEL_WITH_WORLD_IDENTITY_REVIEW", "source_uri": SOURCE_URI,
             "source_version": "FGVC-Aircraft 2013b", "annotation_cohort_sha256": digest(payload["crj_cohort"]),
             "native_hierarchy": payload["crj_cohort"]["source_hierarchy"], "native_label_verified": True,
             "world_exact_identity_verified": False, "commercial_scope_review": "Original Q137829174 redirects to a broader CRJ family; no equivalent exact commercial design assertion",
             "same_spelling_family_and_variant_remain_distinct": True,
             "license": payload["crj_cohort"]["source_license_scope"], "retrieved_utc": "2026-10-08"}
    counts["crj_native_target_repairs"] += update_target(payload["crj_target"], proof, "VERIFIED_NATIVE_LABEL", "ANNOTATION_SCOPE_REVIEW",
                    "Native CRJ-700 variant and source family hierarchy verified; exact commercial model/world identity remains documentary review")
    # This addition bypasses a disputed intermediate; it never updates it.
    counts.update(apply_refinements(m, NAVIGATION_NAME))
    if digest(dict(c.execute("SELECT * FROM edges WHERE id=8107652").fetchone())) != payload["ott_original_edge_sha256"]:
        raise AssertionError("Disputed source assertion was modified")
    m.meta("annotation_scope_repair_input_sha256", fingerprint)
    m.meta("annotation_scope_repair_summary", dict(counts))
    m.meta("browse_indexes_ready", False)
    c.commit()
    return dict(counts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "checklist", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("annotations", "ott-snapshot", "historical-evidence"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.historical_evidence:
        result = prepare_historical_aliases(args.database, args.checklist, args.historical_evidence, args.output)
    else:
        if not args.annotations or not args.ott_snapshot:
            parser.error("Initial scope batch requires --annotations and --ott-snapshot")
        result = prepare(args.database, args.checklist, args.annotations, args.ott_snapshot, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
