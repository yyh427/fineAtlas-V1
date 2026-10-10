"""Checked incremental scope refinements; preserve all prior claims and identities."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .hierarchy import apply_refinements, source_assertion_sha256, validate_link_roles
from .semantics import role_expression

INPUT_NAME = "structure_regression_repairs.json"


def sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def validate_regression_repairs(c, manifest: dict, operations: list[dict]) -> None:
    """Bind full source ranges, old assertions and roles before any mutation."""
    if manifest.get("schema") != "FINEATLAS_STRUCTURE_REGRESSION_REPAIRS_V1":
        raise ValueError("Unknown incremental scope repair schema")
    if not operations or any(op.get("op") != "link" for op in operations):
        raise ValueError("Incremental range repairs can only append typed links")
    seen = set()
    for op in operations:
        uid, parent = op["uid"], op["parent"]
        key = (uid, parent, op["relation"])
        if key in seen:
            raise ValueError("Duplicate incremental range repair")
        seen.add(key)
        proof = op["proof"]
        if proof.get("world_identity_assertion") is not False or proof.get("no_identity_merges") is not True:
            raise ValueError("Directional scope cannot establish world identity")
        if not proof.get("whole_subject_scope_review") or not proof.get("scope_observation"):
            raise ValueError("Full subject/parent scope needs explicit review")
        endpoints = []
        for target, prefix in ((uid, "native"), (parent, "parent_native")):
            row = c.execute("SELECT n.*, " + role_expression("n", "p") + " role "
                "FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?", (target,)).fetchone()
            if not row or row["visibility"] != "ACTIVE" or sha(row["data"]) != proof[prefix + "_record_sha256"]:
                raise ValueError("Frozen scope source changed: " + target)
            endpoints.append(row)
        validate_link_roles(op["relation"], endpoints[0]["role"], endpoints[1]["role"])
        for witness in proof.get("source_witnesses", []):
            row = c.execute("SELECT data FROM nodes WHERE uid=?", (witness["uid"],)).fetchone()
            if not row or sha(row[0]) != witness["data_sha256"]:
                raise ValueError("Independent scope witness changed")
            payload = json.loads(row[0])
            value = payload.get(witness["field"])
            if value is None:
                value = payload.get("evidence_record", {}).get(witness["field"])
            if not isinstance(value, str) or witness["statement"] not in value:
                raise ValueError("Independent scope statement is absent from its source")
        prior = proof.get("prior_assertion")
        if prior:
            rows = c.execute("SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?",
                (prior["subject_uid"], prior["object_uid"], prior["relation"], prior["source"])).fetchall()
            if not any(source_assertion_sha256(row) == prior["content_sha256"] and row["status"] == prior["status"] for row in rows):
                raise ValueError("Prior source assertion or review changed")
        if not proof.get("source_witnesses"):
            raise ValueError("Scope repairs require frozen source text")


def apply_structure_regression_repairs(m):
    """Append reviewed connections before graph and browse cache recomputation."""
    path = m.inputs / INPUT_NAME
    if not path.exists():
        return {"status": "not_requested"}
    manifest = json.loads(path.read_text())
    operation_name = manifest["operations_file"]
    operation_path = (m.inputs / operation_name).resolve()
    if not operation_path.is_relative_to(m.inputs.resolve()) or operation_name != "hierarchy_contract_repairs.jsonl":
        raise ValueError("Incremental input must use the existing append-only hierarchy contract")
    raw = operation_path.read_bytes()
    if sha(raw) != manifest["operations_sha256"]:
        raise ValueError("Incremental operation checksum changed")
    operations = [json.loads(line) for line in raw.decode().splitlines() if line]
    if len(operations) != manifest["operation_count"]:
        raise ValueError("Incremental operations are incomplete")
    validate_regression_repairs(m.c, manifest, operations)
    for review in manifest.get("mapping_reviews", []):
        target = m.c.execute("SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?", (review["dataset"], review["class_id"])).fetchone()
        check = m.c.execute("SELECT * FROM dataset_mapping_checks WHERE dataset=? AND class_id=?", (review["dataset"], review["class_id"])).fetchone()
        if not target or target["target_uid"] != review["target_uid"] or sha(json.dumps(dict(target), sort_keys=True)) != review["target_record_sha256"] or (dict(check) if check else None) != review["before_check"]:
            raise ValueError("Mapping review no longer binds the retained original claim")
        for witness in review["source_witnesses"]:
            row = m.c.execute("SELECT data FROM nodes WHERE uid=?", (witness["uid"],)).fetchone()
            data = json.loads(row[0]) if row else {}
            text = data.get(witness["field"]) or data.get("evidence_record", {}).get(witness["field"])
            if not row or sha(row[0]) != witness["data_sha256"] or text != witness["statement"]:
                raise ValueError("Mapping range evidence changed")
    targets = [tuple(row) for row in m.c.execute("SELECT * FROM dataset_targets ORDER BY dataset,class_id")]
    node_count = m.c.execute("SELECT count(*) FROM nodes").fetchone()[0]
    result = apply_refinements(m, operation_name)
    if node_count != m.c.execute("SELECT count(*) FROM nodes").fetchone()[0] or targets != [tuple(row) for row in m.c.execute("SELECT * FROM dataset_targets ORDER BY dataset,class_id")]:
        raise ValueError("Directional scope repair changed entities or target mappings")
    for review in manifest.get("mapping_reviews", []):
        proof = {**review, "input_sha256": sha(path.read_bytes()), "world_identity_assertion": False,
            "original_target_retained": True, "review_is_not_proof_of_false_identity": True}
        eid = m.evidence("Reviewed retained mapping scope", review["source_uri"], proof, "DATASET_MAPPING_SCOPE_REVIEW")
        after = {"dataset": review["dataset"], "class_id": review["class_id"], "status": "ANNOTATION_SCOPE_REVIEW", "reason": review["reason"], "proof": json.dumps(proof, sort_keys=True)}
        m.c.execute("INSERT OR REPLACE INTO dataset_mapping_checks(dataset,class_id,status,reason,proof) VALUES (?,?,?,?,?)", tuple(after[k] for k in ("dataset", "class_id", "status", "reason", "proof")))
        m.c.execute("INSERT OR IGNORE INTO dataset_mapping_history(id,dataset,class_id,namespace,source_version,before_record,after_record,evidence_id,decision) VALUES (?,?,?,?,?,?,?,?,?)", (sha(json.dumps(proof,sort_keys=True)), review["dataset"], review["class_id"], "world", "v1.11.0rc1", json.dumps(review["before_check"],sort_keys=True), json.dumps(after,sort_keys=True), eid, "ANNOTATION_SCOPE_REVIEW"))
        m.change("structure_regression_repairs", "mapping_scope_review", review["dataset"]+":"+review["class_id"], review["before_check"], after, proof)
    m.meta("structure_regression_repairs", {"manifest_sha256": sha(path.read_bytes()),
        "operations_sha256": sha(raw), "operation_count": len(operations),
        "prior_claims_preserved": True, "world_identity_promotions": 0,
        "mapping_scope_reviews": len(manifest.get("mapping_reviews", []))})
    m.c.commit()
    return {"status": "PASS", **result, "world_identity_promotions": 0}
