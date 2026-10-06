#!/usr/bin/env python3
"""All-record invariants, source inventory triage and portal role/depth census."""

from __future__ import annotations
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas.semantics import role_expression


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", required=True)
    p.add_argument("--baseline", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(
        Path(a.database).resolve().as_uri() + "?mode=ro&immutable=1", uri=True
    )
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA cache_size=-1048576")
    c.execute("PRAGMA temp_store=MEMORY")
    c.execute(
        "ATTACH DATABASE ? AS base",
        (Path(a.baseline).resolve().as_uri() + "?mode=ro&immutable=1",),
    )
    checks = {}
    counts = {}
    role = role_expression("n", "p")

    def check(key, sql):
        checks[key] = c.execute(sql).fetchone()[0]
        print(key, checks[key], flush=True)
        (out / "contract_checkpoint.json").write_text(
            json.dumps({"checks": checks, "counts": counts}, indent=2)
        )

    check(
        "source_false_active_ISA",
        "SELECT count(*) FROM edges WHERE status='ACTIVE' AND relation='IS_A' AND json_extract(data,'$.eligible_for_final_dag')=0",
    )
    check(
        "baseline_nodes_deleted",
        "SELECT count(*) FROM base.nodes b LEFT JOIN nodes n ON n.uid=b.uid WHERE n.uid IS NULL",
    )
    check(
        "baseline_raw_nodes_changed",
        "SELECT count(*) FROM base.nodes b JOIN nodes n ON n.uid=b.uid WHERE b.data<>n.data",
    )
    check(
        "baseline_edges_deleted",
        "SELECT count(*) FROM base.edges b LEFT JOIN edges e ON e.id=b.id WHERE e.id IS NULL",
    )
    check(
        "original_edge_declarations_changed",
        "SELECT count(*) FROM base.edges b JOIN edges e ON e.id=b.id WHERE b.original_relation IS NOT e.original_relation OR b.source_relation IS NOT e.source_relation OR b.child_uid IS NOT e.child_uid OR b.parent_uid IS NOT e.parent_uid",
    )
    for endpoint in ("child_uid", "parent_uid"):
        check(
            "strict_" + endpoint + "_role",
            f"SELECT count(*) FROM edges e JOIN nodes n ON n.uid=e.{endpoint} LEFT JOIN node_profiles p ON p.uid=n.uid WHERE e.status='ACTIVE' AND e.relation='IS_A' AND {role} NOT IN ('CLASS','MODEL','MODEL_FAMILY','CONFIGURATION')",
        )
    check(
        "unknown_active_instances",
        "SELECT count(*) FROM entity_relations r JOIN node_profiles p ON p.uid=r.subject_uid WHERE r.status='ACTIVE' AND r.relation='INSTANCE_OF' AND p.node_kind<>'INSTANCE'",
    )
    check('current_normalization_role_disagreement',
          'SELECT count(*) FROM normalization_roles r JOIN node_profiles p ON p.uid=r.uid WHERE r.canonical_role<>p.node_kind OR r.evidence_id<>p.evidence_id')
    check('domain_member_role_disagreement',
          'SELECT count(*) FROM domain_members m JOIN node_profiles p ON p.uid=m.uid WHERE m.role<>p.node_kind')
    check(
        "view_witness_class_endpoint_admission",
        """SELECT count(*) FROM view_paths v JOIN edges e ON e.id=v.witness_id JOIN nodes n ON n.uid=e.child_uid JOIN nodes t ON t.uid=e.parent_uid
      WHERE v.witness_id>0 AND (n.visibility<>'ACTIVE' OR t.visibility<>'ACTIVE' OR EXISTS(SELECT 1 FROM node_profiles p WHERE p.uid IN(n.uid,t.uid) AND json_type(p.attributes,'$.allowed_views')='array' AND NOT EXISTS(SELECT 1 FROM json_each(p.attributes,'$.allowed_views') av WHERE av.value=v.view)))""",
    )
    check(
        "view_witness_typed_endpoint_admission",
        """SELECT count(*) FROM view_paths v JOIN entity_relations e ON e.id=-v.witness_id JOIN nodes n ON n.uid=e.subject_uid JOIN nodes t ON t.uid=e.object_uid
      WHERE v.witness_id<0 AND (n.visibility<>'ACTIVE' OR t.visibility<>'ACTIVE' OR e.status<>'ACTIVE' OR EXISTS(SELECT 1 FROM node_profiles p WHERE p.uid IN(n.uid,t.uid) AND json_type(p.attributes,'$.allowed_views')='array' AND NOT EXISTS(SELECT 1 FROM json_each(p.attributes,'$.allowed_views') av WHERE av.value=v.view)))""",
    )
    check(
        "new_ISA_without_provenance",
        "SELECT count(*) FROM edges WHERE layer='v1.7-generality-review' AND status='ACTIVE' AND relation='IS_A' AND (provenance='{}' OR classification_basis='' OR coalesce(json_extract(data,'$.eligible_for_final_dag'),0)<>1)",
    )
    check(
        "typed_relations_entering_strict_class_view",
        "SELECT count(*) FROM view_roots v JOIN edges e ON e.id=v.witness_id WHERE v.view='strict' AND (e.relation<>'IS_A' OR e.status<>'ACTIVE')",
    )
    check(
        "entry_root_inventory_mismatch",
        "SELECT count(*) FROM domain_entries d WHERE json_array_length(d.root_uids)<>(SELECT count(*) FROM domain_entry_roots r WHERE r.domain=d.domain)",
    )
    check(
        "missing_identity_bridge_endpoints",
        "SELECT count(*) FROM bridges b LEFT JOIN nodes n ON n.uid=b.left_uid LEFT JOIN nodes t ON t.uid=b.right_uid WHERE b.status='ACTIVE' AND b.relation='SAME_CONCEPT' AND (n.uid IS NULL OR t.uid IS NULL OR n.component_id<>t.component_id)",
    )
    check(
        "rejected_native_endpoint_edges_still_active",
        "SELECT count(*) FROM relation_rechecks r JOIN edges e ON e.id=r.edge_id WHERE r.reason='Native field endpoints differ from retained record' AND e.status='ACTIVE'",
    )
    for table in (
        "nodes",
        "edges",
        "aliases",
        "bridges",
        "entity_relations",
        "evidence",
        "node_names",
        "node_definitions",
        "node_taxon_ranks",
    ):
        counts[table] = c.execute("SELECT count(*) FROM " + table).fetchone()[0]
    counts["visibility"] = dict(
        c.execute("SELECT visibility,count(*) FROM nodes GROUP BY visibility")
    )
    counts["active_roles"] = dict(
        c.execute(
            "SELECT "
            + role
            + ",count(*) FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility='ACTIVE' GROUP BY 1"
        )
    )
    counts["normalizations"] = dict(
        c.execute("SELECT canonical_role,count(*) FROM normalization_roles GROUP BY 1")
    )
    counts["repair_role_decisions"] = dict(
        c.execute("SELECT final_role,count(*) FROM repair_node_decisions GROUP BY 1")
    )
    counts["repair_rank_decisions"] = dict(
        c.execute("SELECT verdict,count(*) FROM repair_rank_reviews GROUP BY 1")
    )
    counts["legacy_refinement_dispositions"] = dict(
        c.execute("SELECT decision,count(*) FROM relation_rechecks GROUP BY 1")
    )
    counts["rank_source_dispositions"] = dict(
        c.execute("SELECT status,count(*) FROM node_taxon_ranks GROUP BY 1")
    )
    counts["unresolved_Q_display"] = c.execute(
        "SELECT count(*) FROM nodes n WHERE n.visibility='ACTIVE' AND n.label GLOB 'Q[0-9]*' AND NOT EXISTS(SELECT 1 FROM node_names x WHERE x.uid=n.uid AND x.name NOT GLOB 'Q[0-9]*')"
    ).fetchone()[0]
    domains = []
    for r in c.execute(
        "SELECT d.canonical_name,m.view,m.role,count(*),count(DISTINCT n.component_id),max(m.depth),sum(m.depth=0) FROM domain_members m JOIN domain_registry d ON d.domain_id=m.domain_id JOIN nodes n ON n.uid=m.uid GROUP BY d.domain_id,m.view,m.role ORDER BY d.canonical_name,m.view,m.role"
    ):
        domains.append(
            dict(
                zip(
                    (
                        "domain",
                        "view",
                        "role",
                        "source_uids",
                        "identity_groups",
                        "maximum_shortest_depth",
                        "root_source_uids",
                    ),
                    r,
                )
            )
        )
    (out / "domain_role_census.json").write_text(json.dumps(domains, indent=2))
    # Every remaining source-only UID gets a recoverable disposition. Identity
    # peers are duplicates only when a prior accepted group exists, never by name.
    triage = Counter()
    by_domain = Counter()
    with gzip.open(out / "source_only_dispositions.jsonl.gz", "wt") as f:
        for r in c.execute(
            "SELECT n.uid,n.domain,n.rank,n.component_id,"
            + role
            + ",EXISTS(SELECT 1 FROM nodes x WHERE x.component_id=n.component_id AND x.visibility='ACTIVE') FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility='SOURCE_ONLY' ORDER BY n.uid"
        ):
            uid, domain, rank, component, kind, has_peer = r
            reason = (
                "DUPLICATE_SOURCE_REPRESENTATION"
                if has_peer
                else "NON_CLASSIFICATION_ROLE"
                if kind in ("ORGANIZATION", "ATTRIBUTE", "INSTANCE", "DATASET_CATEGORY")
                else "EVIDENCE_INSUFFICIENT_REVIEW"
            )
            triage[reason] += 1
            by_domain[(domain, reason)] += 1
            f.write(
                json.dumps(
                    dict(
                        uid=uid,
                        source_domain=domain,
                        native_rank=rank,
                        canonical_role=kind,
                        component_id=component,
                        disposition=reason,
                        retained=True,
                    ),
                    ensure_ascii=False,
                )
                + "\n"
            )
    counts["source_only_triage"] = dict(triage)
    counts["source_only_by_domain_reason"] = [
        dict(domain=d, reason=r, count=n) for (d, r), n in sorted(by_domain.items())
    ]
    # Regressions: preserve every previously accepted EUNIS and IMA identity,
    # role and native inclusion; source-specific scientific flags are retained.
    regressions = {}
    for label, prefix in [("EUNIS", "eunis%:%"), ("IMA", "ima-mineral:%")]:
        total = c.execute(
            "SELECT count(*) FROM base.nodes WHERE uid LIKE ?", (prefix,)
        ).fetchone()[0]
        changed = c.execute(
            "SELECT count(*) FROM base.nodes b LEFT JOIN nodes n ON n.uid=b.uid WHERE b.uid LIKE ? AND (n.uid IS NULL OR b.visibility<>n.visibility OR b.component_id<>n.component_id)",
            (prefix,),
        ).fetchone()[0]
        regressions[label] = {"baseline_uids": total, "changed_or_deleted": changed}
    result = {
        "checks": checks,
        "counts": counts,
        "regressions": regressions,
        "structural_contract_pass": not any(checks.values()),
        "semantic_boundary": "Declared source facts and contracts, not scientific certification or recognition accuracy",
    }
    (out / "contract.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    if any(checks.values()):
        raise SystemExit("All-library contract failed")


if __name__ == "__main__":
    main()
