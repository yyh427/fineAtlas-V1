#!/usr/bin/env python3
"""Apply frozen repair deltas to a completed independent structural snapshot.

Preserve completed source stages and their original fingerprints. Recompute all
derived graph and browse indexes after the additive repair stage. This recipe
does not accept an interrupted database or claim independent acceptance.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.pycache_prefix = str(Path(os.environ.get("TMPDIR", str(ROOT.parent / "tmp"))) /
                        ("resume-import-" + uuid.uuid4().hex))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from structure_build_safety import inventory_code, protect_output, require_unoptimized

require_unoptimized()
PREIMPORT_INVENTORY = inventory_code(ROOT)
from build_structure_candidate import (
    BUILD_STAGES as PARENT_STAGES, build_fingerprints, final_artifact_binding,
    freeze_metadata, require_stable_build, start_build, write_build_complete,
)
from fineatlas.migration import Migration, digest_file
from fineatlas.unified_build import ram_graphs

if inventory_code(ROOT) != PREIMPORT_INVENTORY:
    raise ValueError("Resume implementation changed during import")

STAGES = ("verify_completed_parent_copy", "grounded_regression_repairs", "grounded_oem_body_repairs",
          "complete_subject_scope_repairs", "cars_projection_view_repairs",
          "whole_graph_recomputation", "freeze_metadata", "browse_staging",
          "embed_browse_indexes")


def read_metadata(database):
    with sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True) as con:
        return {key: json.loads(value) for key, value in con.execute("SELECT * FROM metadata")}


def validate_parent_receipt(database, receipt_path, fingerprints, integrity_path):
    """Bind all completed parent stages and unchanged source inputs and code."""
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get("schema") != "FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1" or
            receipt.get("complete") is not True or receipt.get("pass") is not True or
            not receipt.get("build_id") or not receipt.get("ended_utc") or
            Path(receipt["database"]).resolve() != database.resolve()):
        raise ValueError("A completed parent build for this exact source is required")
    directory = receipt_path.parent
    for name in ("started_fingerprints", "build_status"):
        if digest_file(directory / (name + ".json")) != receipt.get(name + "_sha256"):
            raise ValueError("Parent build evidence changed: " + name)
    states = json.loads((directory / "build_status.json").read_text())
    if set(states) != set(PARENT_STAGES) or any(row.get("status") != "PASS" for row in states.values()):
        raise ValueError("All original source and index stages must have completed")
    parent = json.loads((directory / "started_fingerprints.json").read_text())
    for group in ("inputs", "code", "packaging"):
        for name, digest in parent[group].items():
            if fingerprints[group].get(name) != digest:
                raise ValueError("Previously executed implementation/input changed: " + name)
    meta = read_metadata(database)
    manifest = meta.get("structure_frozen_build_manifest", {})
    if any(manifest.get(group) != parent[group] for group in ("inputs", "code", "packaging")):
        raise ValueError("Actual parent database is not bound to its source build inventory")
    binding = final_artifact_binding(database, receipt["release"], receipt["source_graph_revision"])
    if binding["revision"] != receipt["revision"]:
        raise ValueError("Parent database revision differs from its completion receipt")
    seal = json.loads(integrity_path.read_text())
    if (any(seal.get(key) is not True for key in (
            "pass", "complete", "integrity_pass", "file_unchanged_during_checks",
            "all_frozen_inputs_and_recipes_checked")) or seal.get("integrity_check") != ["ok"] or
            Path(seal.get("database", "")).resolve() != database.resolve() or
            seal.get("database_revision") != receipt["revision"] or
            seal.get("release") != receipt["release"] or seal.get("bytes") != database.stat().st_size or
            not isinstance(seal.get("sha256"), str) or len(seal["sha256"]) != 64):
        raise ValueError("A complete integrity and whole-file hash seal for the parent is required")
    return receipt, meta, seal


def verify_parent_byte_copy(source, output, seal):
    before = source.stat()
    source_sha = digest_file(source)
    if source_sha != seal["sha256"]:
        raise ValueError("Completed parent source bytes differ from the independent integrity seal")
    if digest_file(output) != source_sha or output.stat().st_size != before.st_size:
        raise ValueError("Repair output is not an exact independent parent copy")
    after = source.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("Completed source changed during copy verification")
    return source_sha


def validate_resumed_parent_independence(primary_receipt, reproduction_receipt):
    """Require two distinct completed parents, not two copies of one parent."""
    rows = []
    for path in (primary_receipt, reproduction_receipt):
        receipt = json.loads(path.read_text())
        lineage_path = path.parent / "parent_lineage.json"
        if digest_file(lineage_path) != receipt.get("parent_lineage_sha256"):
            raise ValueError("Resumed parent lineage is missing or changed")
        lineage = json.loads(lineage_path.read_text())
        if (receipt.get("complete") is not True or receipt.get("pass") is not True or
                lineage.get("resumed_build_id") != receipt.get("build_id") or
                lineage.get("resumed_revision") != receipt.get("revision") or
                lineage.get("parent_build_id") != receipt.get("parent_build_id") or
                not receipt.get("parent_build_id") or
                lineage.get("parent_source_inode") != receipt.get("parent_source_inode")):
            raise ValueError("Resumed parent lineage differs from its completion receipt")
        source = Path(lineage["parent_database"]).resolve(strict=True)
        if [source.stat().st_dev, source.stat().st_ino] != lineage["parent_source_inode"]:
            raise ValueError("Resumed parent source inode changed")
        rows.append((receipt, lineage, source))
    if (rows[0][0]["build_id"] == rows[1][0]["build_id"] or
            rows[0][0]["parent_build_id"] == rows[1][0]["parent_build_id"] or
            rows[0][2].samefile(rows[1][2])):
        raise ValueError("Two distinct independently completed parent builds are required")
    if rows[0][1]["parent_revision"] != rows[1][1]["parent_revision"]:
        raise ValueError("Resumed parents belong to different semantic snapshots")
    return {"pass": True, "parent_build_ids": [row[0]["parent_build_id"] for row in rows],
            "resumed_build_ids": [row[0]["build_id"] for row in rows],
            "distinct_source_inodes": True, "parent_revision": rows[0][1]["parent_revision"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "parent-build", "parent-integrity", "baseline", "database", "inputs",
                 "reports", "browse-staging"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    for name, path in vars(args).items():
        setattr(args, name, path.resolve())
    fingerprints, context = start_build(args.inputs, args.reports)
    states = {}
    temp = args.database.parent / "tmp"
    temp.mkdir(exist_ok=True)
    os.environ.update(TMPDIR=str(temp), SQLITE_TMPDIR=str(temp))

    def stage(name, function):
        began = time.monotonic()
        states[name] = {"status": "RUNNING", "started_utc":
                        datetime.datetime.now(datetime.timezone.utc).isoformat()}
        status = args.reports / "build_status.json"
        status.write_text(json.dumps(states, indent=2) + "\n")
        print("START", name, flush=True)
        try:
            require_stable_build(args.inputs, fingerprints)
            states[name].update(status="PASS", result=function())
            require_stable_build(args.inputs, fingerprints)
        except Exception as error:
            states[name].update(status="FAIL", error=str(error))
            raise
        finally:
            states[name]["seconds"] = time.monotonic() - began
            status.write_text(json.dumps(states, indent=2) + "\n")
        print("PASS", name, flush=True)
        return states[name]["result"]

    def verify():
        for database in (args.source, args.database):
            if any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-journal", "-shm")):
                raise ValueError("Source and independent copy must be closed without sidecars")
        receipt, meta, seal = validate_parent_receipt(
            args.source, args.parent_build, fingerprints, args.parent_integrity)
        protection = protect_output(args.database, args.inputs, args.baseline, (args.source,))
        source_sha = verify_parent_byte_copy(args.source, args.database, seal)
        return {"parent_build_id": receipt["build_id"], "parent_revision": meta["database_revision"],
                "parent_receipt_sha256": digest_file(args.parent_build),
                "parent_integrity_sha256": digest_file(args.parent_integrity),
                "parent_database_sha256": source_sha, "parent_database": str(args.source),
                "previous_source_stages_replayed": False, "protection": protection}

    lineage = stage("verify_completed_parent_copy", verify)
    migration = Migration(args.database, args.inputs, args.reports / "graph-build")
    from fineatlas.structure_regression_repairs import apply_structure_regression_repairs
    stage("grounded_regression_repairs", lambda: apply_structure_regression_repairs(migration))
    from fineatlas.structure_oem_body_scope_repairs import apply_oem_body_scope_repairs
    stage("grounded_oem_body_repairs", lambda: apply_oem_body_scope_repairs(migration))
    from fineatlas.structure_complete_subject_scope_repairs import apply_complete_subject_scope_repairs
    stage("complete_subject_scope_repairs", lambda: apply_complete_subject_scope_repairs(migration))
    from fineatlas.structure_cars_projection_view_repairs import apply_cars_projection_view_repairs
    stage("cars_projection_view_repairs", lambda: apply_cars_projection_view_repairs(migration))
    migration.meta("structure_resume_parent", {
        "parent_revision": lineage["parent_revision"], "previous_source_stages_replayed": False,
        "repair_recipe": "resume_structure_repairs.py", "all_derived_indexes_recomputed": True,
    })
    migration.c.commit()
    stage("whole_graph_recomputation", lambda: ram_graphs(migration))
    frozen = stage("freeze_metadata", lambda: freeze_metadata(migration, fingerprints))
    (args.reports / "frozen_metadata.json").write_text(json.dumps(frozen, indent=2) + "\n")
    migration.c.close()
    release = json.loads((args.inputs / "review_release.json").read_text())["version"]
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": str(ROOT / "src"), "PYTHONPYCACHEPREFIX": sys.pycache_prefix}
    env.pop("PYTHONOPTIMIZE", None)

    def command(name, values):
        with (args.reports / (name + ".log")).open("w") as log:
            subprocess.run([sys.executable, "-B", *map(str, values)], cwd=ROOT, env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        return {"log": str(args.reports / (name + ".log"))}

    stage("browse_staging", lambda: command("browse_staging", [ROOT / "scripts/stage_browse_indexes.py",
          "--source", args.database, "--output", args.browse_staging,
          "--reports", args.reports / "browse-build", "--release", release]))
    stage("embed_browse_indexes", lambda: command("embed_browse_indexes", [ROOT / "scripts/apply_browse_indexes.py",
          "--database", args.database, "--staging", args.browse_staging,
          "--source-revision", frozen["revision"], "--output", args.reports / "browse_application.json"]))
    require_stable_build(args.inputs, fingerprints)
    binding = final_artifact_binding(args.database, release, frozen["revision"])
    lineage_path = args.reports / "parent_lineage.json"
    lineage_path.write_text(json.dumps(
        {"schema": "FINEATLAS_REPAIR_PARENT_LINEAGE_V1", **lineage,
         "resumed_build_id": context["build_id"], "resumed_revision": binding["revision"],
         "parent_source_inode": [args.source.stat().st_dev, args.source.stat().st_ino]},
        indent=2) + "\n")
    context.update(parent_build_id=lineage["parent_build_id"],
                   parent_lineage_sha256=digest_file(lineage_path),
                   parent_source_inode=[args.source.stat().st_dev, args.source.stat().st_ino])
    write_build_complete(args.reports, args.database, release, binding["revision"], context,
                         states, STAGES, source_graph_revision=frozen["revision"])


if __name__ == "__main__":
    main()
