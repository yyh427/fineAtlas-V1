#!/usr/bin/env python3
"""All-record invariants, source inventory triage and portal role/depth census."""

from __future__ import annotations

if not __debug__:
    raise RuntimeError("Optimized Python is forbidden for mandatory structural checks")

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas.semantics import (role_expression, VIEWS, TYPED_TERMINALS,
    source_admission_view, classification_roles, navigation_parent_roles,
    terminal_relations, edge_predicate)


def _values(values):
    return ','.join("'" + value.replace("'", "''") + "'" for value in sorted(values))


def _source_view(view):
    return "CASE " + ' '.join("WHEN " + view + "='" + v + "' THEN '" +
        source_admission_view(v) + "'" for v in VIEWS) + " ELSE NULL END"


def _admitted(node, profile, view):
    return (f"{node}.visibility='ACTIVE' AND (json_type({profile}.attributes,'$.allowed_views') IS NOT 'array' "
            f"OR EXISTS(SELECT 1 FROM json_each({profile}.attributes,'$.allowed_views') av "
            f"WHERE av.value={_source_view(view)}))")


def _class_legal(view):
    child, parent = role_expression('n','np'), role_expression('t','tp')
    return '(' + ' OR '.join(f"({view}='{v}' AND ({edge_predicate(v)}) "
        f"AND {child} IN ({_values(classification_roles(v))}) "
        f"AND {parent} IN ({_values(classification_roles(v))}))" for v in VIEWS) + ')'


def _typed_legal(view):
    child, parent = role_expression('n','np'), role_expression('t','tp')
    choices = []
    for v in VIEWS:
        terminals = ' OR '.join(f"({child}='{role}' AND e.relation IN ({_values(terminal_relations(role,v))}))"
            for role in sorted(TYPED_TERMINALS) if terminal_relations(role,v))
        choices.append(f"({view}='{v}' AND e.status='ACTIVE' AND ({terminals}) "
            f"AND {parent} IN ({_values(navigation_parent_roles(v))}))")
    return '(' + ' OR '.join(choices) + ')'


def view_graph_contract_queries():
    """Inspect actual admitted arcs/caches; retained declarations are not admission.

    Source view and role/relation rules match the public interface. Unknown
    views fail explicitly. Strict full-graph checks include unrooted components,
    rather than accepting a root witness as proof that other arcs are legal.
    """
    joins = " LEFT JOIN nodes n ON n.uid=e.{child} LEFT JOIN nodes t ON t.uid=e.{parent} " \
            "LEFT JOIN node_profiles np ON np.uid=n.uid LEFT JOIN node_profiles tp ON tp.uid=t.uid "
    queries = {}
    known = _values(VIEWS)
    for table in ('view_roots','view_paths','browse_links'):
        queries[table+'_unknown_views'] = f"SELECT count(*) FROM {table} WHERE view NOT IN ({known})"
    for cache in ('view_roots','view_paths'):
        queries[cache+'_invalid_root_witness_shape'] = f"SELECT count(*) FROM {cache} WHERE (depth=0 AND (parent_component_id IS NOT NULL OR witness_id IS NOT NULL)) OR (depth>0 AND (parent_component_id IS NULL OR witness_id IS NULL OR witness_id=0)) OR depth<0"
        sql = f"SELECT count(*) FROM {cache} v LEFT JOIN edges e ON e.id=v.witness_id " + joins.format(child='child_uid',parent='parent_uid')
        invalid = (f"e.id IS NULL OR n.uid IS NULL OR t.uid IS NULL OR NOT ({_class_legal('v.view')}) "
            f"OR NOT ({_admitted('n','np','v.view')}) OR NOT ({_admitted('t','tp','v.view')}) "
            "OR v.component_id IS NOT n.component_id OR v.parent_component_id IS NOT t.component_id")
        queries[cache+'_class_witness_contract'] = sql + f"WHERE v.witness_id>0 AND ({invalid})"
    queries['typed_relations_entering_classification_caches'] = "SELECT count(*) FROM view_roots WHERE witness_id<0"
    sql = "SELECT count(*) FROM view_paths v LEFT JOIN entity_relations e ON e.id=-v.witness_id " + joins.format(child='subject_uid',parent='object_uid')
    invalid = (f"e.id IS NULL OR n.uid IS NULL OR t.uid IS NULL OR NOT ({_typed_legal('v.view')}) "
        f"OR NOT ({_admitted('n','np','v.view')}) OR NOT ({_admitted('t','tp','v.view')}) "
        "OR v.component_id IS NOT n.component_id OR v.parent_component_id IS NOT t.component_id")
    queries['view_paths_typed_witness_contract'] = sql + f"WHERE v.witness_id<0 AND ({invalid})"
    strict_legal = (f"({edge_predicate('strict')}) AND {role_expression('n','np')} IN ({_values(classification_roles('strict'))}) "
        f"AND {role_expression('t','tp')} IN ({_values(classification_roles('strict'))}) "
        f"AND ({_admitted('n','np',repr('strict'))}) AND ({_admitted('t','tp',repr('strict'))})")
    sql = "SELECT count(*) FROM browse_links b LEFT JOIN edges e ON e.id=b.record_id " + joins.format(child='child_uid',parent='parent_uid')
    queries['strict_full_classification_graph_contract'] = sql + (f"WHERE b.view='strict' AND b.storage='edge' AND "
        f"(e.id IS NULL OR n.uid IS NULL OR t.uid IS NULL OR NOT ({strict_legal}) "
        f"OR b.role IS NOT {role_expression('n','np')} OR b.relation IS NOT e.relation "
        "OR b.child_component IS NOT n.component_id OR b.parent_component IS NOT t.component_id "
        "OR b.child_component=b.parent_component)")
    sql = "SELECT count(*) FROM edges e " + joins.format(child='child_uid',parent='parent_uid')
    queries['strict_full_graph_missing_admitted_source_arcs'] = (
        "SELECT count(*) FROM (SELECT DISTINCT t.component_id parent_component,n.component_id child_component,"
        + role_expression('n','np') + " child_role,e.relation FROM edges e "
        + joins.format(child='child_uid',parent='parent_uid')
        + f"WHERE ({strict_legal}) AND n.component_id<>t.component_id) expected "
        + "WHERE NOT EXISTS(SELECT 1 FROM browse_links b WHERE b.view='strict' AND b.storage='edge' "
        + "AND b.parent_component=expected.parent_component AND b.child_component=expected.child_component "
        + "AND b.role=expected.child_role AND b.relation=expected.relation)")
    return queries


def raw_strict_exclusion_census(c):
    """Visible inventory of declarations whose endpoints do not admit strict IS_A."""
    result = {}
    roles = _values(classification_roles('strict'))
    for endpoint in ('child_uid','parent_uid'):
        role = role_expression('n','p')
        sql = (f"SELECT {role} role,json_extract(p.attributes,'$.allowed_views') allowed_views,count(*) records FROM edges e JOIN nodes n ON n.uid=e.{endpoint} "
            f"LEFT JOIN node_profiles p ON p.uid=n.uid WHERE e.status='ACTIVE' AND e.relation='IS_A' "
            f"AND ({role} NOT IN ({roles}) OR NOT ({_admitted('n','p',repr('strict'))})) "
            "GROUP BY 1,2 ORDER BY 1,2")
        result[endpoint] = []
        for row in c.execute(sql):
            allowed = json.loads(row[1]) if row[1] and row[1].startswith('[') else row[1]
            result[endpoint].append({'role':row[0],'allowed_views':allowed,
                'retained_active_ISA_records':row[2],'strict_admitted':False})
    return result


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
    counts['retained_raw_ISA_excluded_from_strict'] = raw_strict_exclusion_census(c)
    for key, sql in view_graph_contract_queries().items():
        check(key, sql)
    check(
        "unknown_active_instances",
        "SELECT count(*) FROM entity_relations r JOIN node_profiles p ON p.uid=r.subject_uid WHERE r.status='ACTIVE' AND r.relation='INSTANCE_OF' AND p.node_kind<>'INSTANCE'",
    )
    check('current_normalization_role_disagreement',
          'SELECT count(*) FROM normalization_roles r JOIN node_profiles p ON p.uid=r.uid WHERE r.canonical_role<>p.node_kind OR r.evidence_id<>p.evidence_id')
    check('domain_member_role_disagreement',
          'SELECT count(*) FROM domain_members m JOIN node_profiles p ON p.uid=m.uid WHERE m.role<>p.node_kind')
    check(
        "new_ISA_without_provenance",
        "SELECT count(*) FROM edges WHERE layer IN ('v1.7-generality-review','v1.8-hierarchy-review') AND status='ACTIVE' AND relation='IS_A' AND (provenance='{}' OR classification_basis='' OR coalesce(json_extract(data,'$.eligible_for_final_dag'),0)<>1)",
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
