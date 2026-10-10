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
    targets = [tuple(row) for row in m.c.execute("SELECT * FROM dataset_targets ORDER BY dataset,class_id")]
    node_count = m.c.execute("SELECT count(*) FROM nodes").fetchone()[0]
    result = apply_refinements(m, operation_name)
    if node_count != m.c.execute("SELECT count(*) FROM nodes").fetchone()[0] or targets != [tuple(row) for row in m.c.execute("SELECT * FROM dataset_targets ORDER BY dataset,class_id")]:
        raise ValueError("Directional scope repair changed entities or target mappings")
    m.meta("structure_regression_repairs", {"manifest_sha256": sha(path.read_bytes()),
        "operations_sha256": sha(raw), "operation_count": len(operations),
        "prior_claims_preserved": True, "world_identity_promotions": 0})
    m.c.commit()
    return {"status": "PASS", **result, "world_identity_promotions": 0}
