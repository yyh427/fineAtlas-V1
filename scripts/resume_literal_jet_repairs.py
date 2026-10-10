#!/usr/bin/env python3
"""Append the frozen aircraft and owned-scope deltas to completed independent resumed parents.

No original source or prior repair stage is replayed. Preserve the original
structure_resume_parent adjudication lineage while recording this new layer
separately; recompute the complete graph and all browse indexes.
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
    build_fingerprints, final_artifact_binding,
    freeze_metadata, require_stable_build, start_build, write_build_complete,
)
from fineatlas.migration import Migration, digest_file
from fineatlas.unified_build import ram_graphs

if inventory_code(ROOT) != PREIMPORT_INVENTORY:
    raise ValueError("Resume implementation changed during import")

from resume_structure_repairs import (STAGES as PARENT_STAGES,
    validate_resumed_parent_independence, verify_parent_byte_copy)

STAGES = ("verify_completed_resumed_parent_copy", "literal_jet_scope_repairs",
          "primary_aircraft_family_repairs", "owned_scope_repairs", "whole_graph_recomputation", "freeze_metadata", "browse_staging", "embed_browse_indexes")


def read_metadata(database):
    with sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True) as con:
        return {key: json.loads(value) for key, value in con.execute("SELECT * FROM metadata")}


def validate_literal_jet_parent_receipt(database, receipt_path, fingerprints, integrity_path):
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
        raise ValueError("All nine resumed parent stages must have completed")
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
    if (receipt.get('required_stages') != list(PARENT_STAGES)
            or not meta.get('structure_resume_parent', {}).get('parent_revision')):
        raise ValueError('A complete prior repair checkpoint with original lineage is required')
    return receipt, meta, seal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "parent-build", "peer-parent-build", "parent-integrity", "peer-parent-integrity", "baseline", "database", "inputs",
                 "reports", "browse-staging"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    for name, path in vars(args).items():
        setattr(args, name, path.resolve())
    from structure_literal_jet_delivery_guard import SPEC, input_path
    from structure_primary_aircraft_delivery_guard import SPEC as FAMILY_SPEC
    from structure_owned_scope_delivery_guard import SPEC as OWNED_SPEC
    for spec in (SPEC, FAMILY_SPEC, OWNED_SPEC):
        if input_path(spec, args.inputs, ROOT) is None:
            raise ValueError("Child requires its sealed frozen input: " + spec.name)
    from primary_source_snapshot_delivery import REGISTRY_NAME, registry
    from structure_regression_temporal_contract import REFERENCE
    for name in (REGISTRY_NAME, REFERENCE):
        if not (args.inputs / name).is_file():
            raise ValueError('Child requires its portable frozen acceptance input: ' + name)
    registry(args.inputs)
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
        independence = validate_resumed_parent_independence(args.parent_build, args.peer_parent_build)
        receipt, meta, seal = validate_literal_jet_parent_receipt(
            args.source, args.parent_build, fingerprints, args.parent_integrity)
        peer = json.loads(args.peer_parent_build.read_text())
        peer_source = Path(peer["database"]).resolve()
        validate_literal_jet_parent_receipt(peer_source, args.peer_parent_build, fingerprints, args.peer_parent_integrity)
        if any(Path(str(peer_source)+suffix).exists() for suffix in ("-wal","-journal","-shm")):
            raise ValueError("Peer completed source must be closed without sidecars")
        if (peer.get("revision") != receipt["revision"] or args.source.samefile(peer_source)
                or peer.get("build_id") == receipt["build_id"]):
            raise ValueError("Literal-jet delta needs two distinct complete current parent databases")
        temporal = json.loads((args.inputs / REFERENCE).read_text())
        reference_hash = temporal.get('completed_parent_build_sha256')
        bound_parent = receipt if reference_hash == digest_file(args.parent_build) else peer
        original_report = json.loads(temporal['audit_receipt_text'])
        if (reference_hash not in (digest_file(args.parent_build),digest_file(args.peer_parent_build))
                or temporal.get('completed_parent_build') != bound_parent
                or temporal.get('parent_revision') != receipt['revision']
                or original_report.get('pass') is not True or original_report.get('preflight_only') is not False
                or original_report.get('errors') != []
                or Path(original_report.get('database','')).resolve() != Path(bound_parent['database']).resolve()
                or temporal.get('original_manifest_sha256') != digest_file(args.inputs / 'structure_regression_repairs.json')
                or temporal.get('original_auditor_sha256') != digest_file(ROOT / 'scripts/audit_structure_regression_repairs.py')):
            raise ValueError('Actual original parent SQL audit must bind one of the two completed source receipts')
        protection = protect_output(args.database, args.inputs, args.baseline, (args.source, peer_source))
        source_sha = verify_parent_byte_copy(args.source, args.database, seal)
        return {"parent_build_id": receipt["build_id"], "parent_revision": meta["database_revision"],
                "parent_receipt_sha256": digest_file(args.parent_build),
                "parent_integrity_sha256": digest_file(args.parent_integrity),
                "peer_parent_integrity_sha256": digest_file(args.peer_parent_integrity),
                "peer_parent_receipt_sha256": digest_file(args.peer_parent_build),
                "parent_database_sha256": source_sha, "parent_database": str(args.source),
                "previous_source_stages_replayed": False, "previous_repair_stages_replayed": False,
                "independent_previous_checkpoint": independence,
                "preserved_structure_resume_parent": meta["structure_resume_parent"], "protection": protection}

    lineage = stage("verify_completed_resumed_parent_copy", verify)
    migration = Migration(args.database, args.inputs, args.reports / "graph-build")
    from fineatlas.structure_literal_jet_scope_repairs import apply_literal_jet_scope_repairs
    original_metadata = read_metadata(args.database)
    original_stages = list(migration.c.execute('SELECT * FROM usability_stages ORDER BY stage'))
    def apply_fifth():
        result = apply_literal_jet_scope_repairs(migration)
        if result.get("status") != "PASS":
            raise ValueError("Actual literal-jet delta was not applied")
        return result

    stage("literal_jet_scope_repairs", apply_fifth)
    literal_metadata = read_metadata(args.database)['literal_jet_scope_repairs']
    from fineatlas.structure_primary_aircraft_family_repairs import apply_primary_aircraft_family_repairs

    def apply_sixth():
        result = apply_primary_aircraft_family_repairs(migration)
        if result.get("status") != "PASS":
            raise ValueError("Actual primary-aircraft family delta was not applied")
        return result

    stage("primary_aircraft_family_repairs", apply_sixth)
    family_metadata = read_metadata(args.database)['primary_aircraft_family_repairs']
    from fineatlas.structure_owned_scope_repairs import apply_owned_scope_repairs

    def apply_seventh():
        result = apply_owned_scope_repairs(migration)
        if result.get("status") != "PASS":
            raise ValueError("Actual owned-scope delta was not applied")
        return result

    stage("owned_scope_repairs", apply_seventh)
    current = read_metadata(args.database)
    if current.get('primary_aircraft_family_repairs') != family_metadata:
        raise ValueError('Owned-scope delta changed the independent primary-aircraft binding')
    if current.get('literal_jet_scope_repairs') != literal_metadata:
        raise ValueError('Primary-aircraft delta changed the independent literal-jet binding')
    mutable_readiness = {'usability_indexes_ready', 'unified_ready', 'browse_indexes_ready'}
    if (any(current.get(key) != value for key, value in original_metadata.items() if key not in mutable_readiness)
            or original_stages != list(migration.c.execute('SELECT * FROM usability_stages ORDER BY stage'))):
        raise ValueError('New repair stages modified prior metadata or source stage history')
    migration.meta("structure_delta_resume_parent", {
        "parent_revision": lineage["parent_revision"], "previous_source_stages_replayed": False,
        "previous_repair_stages_replayed": False, "repair_recipe": "resume_literal_jet_repairs.py",
        "all_derived_indexes_recomputed": True,
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
    if read_metadata(args.database).get('structure_resume_parent') != lineage['preserved_structure_resume_parent']:
        raise ValueError('Original scope adjudication lineage was changed')
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
