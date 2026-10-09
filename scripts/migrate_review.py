#!/usr/bin/env python3
"""Migrate a separately copied v1.6 database using frozen source inputs."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas.migration import Migration

p = argparse.ArgumentParser()
p.add_argument("--database", required=True)
p.add_argument("--inputs", required=True)
p.add_argument("--reports", required=True)
p.add_argument(
    "--stages",
    nargs="+",
    choices=[
        "names",
        "native_metadata",
        "definitions",
        "source_ranks",
        "accepted_proofs",
        "role_reconciliation",
        "source_facts",
        "adjudicate_design_grain",
        "sync_role_contracts",
        "task_updates",
        "portals",
        "hierarchy_refinements",
        "hierarchy_extensions",
        "hierarchy_endpoint_contracts",
        "hierarchy_contract_repairs",
        "hierarchy_role_repairs",
        "hierarchy_semantic_repairs",
        "hierarchy_identity_role_repairs",
        "hierarchy_type_repairs",
        "hierarchy_shape_repairs",
        "hierarchy_structure_repairs",
        "hierarchy_shape_completion",
        "hierarchy_subject_repairs",
        "hierarchy_admission_reviews",
        "graphs",
    ],
    default=[
        "names",
        "native_metadata",
        "definitions",
        "source_ranks",
        "accepted_proofs",
        "role_reconciliation",
        "source_facts",
        "adjudicate_design_grain",
        "task_updates",
        "portals",
        "hierarchy_refinements",
        "hierarchy_extensions",
        "hierarchy_endpoint_contracts",
        "hierarchy_contract_repairs",
        "hierarchy_role_repairs",
        "hierarchy_semantic_repairs",
        "hierarchy_identity_role_repairs",
        "hierarchy_type_repairs",
        "hierarchy_shape_repairs",
        "hierarchy_structure_repairs",
        "hierarchy_shape_completion",
        "hierarchy_subject_repairs",
        "hierarchy_admission_reviews",
        "sync_role_contracts",
        "graphs",
    ],
)
a = p.parse_args()
Migration(a.database, a.inputs, a.reports).run(a.stages)
