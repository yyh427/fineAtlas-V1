#!/usr/bin/env python3
"""Repeat a complete task/portal audit through the public read-only SDK.

Counts are observed, never forced to an expected dataset/version total.
Native classification, strict inclusion and typed root reachability stay separate.
"""

from __future__ import annotations
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas import FineAtlas


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sample_path(tree, uid):
    result = tree.path_result(uid)
    state = tree.connection_status(uid)
    connected = result["status"] in ("CONNECTED", "ROOT")
    if state is not None and state.get("root_reachable", False) != connected:
        raise AssertionError("Path/status contradiction: " + uid)
    return {
        "uid": uid,
        "status": result["status"],
        "distance": result.get("distance"),
        "path": [
            {
                "child_uid": s.get("uid"),
                "parent_uid": s.get("parent_uid"),
                "relation": s["edge"]["relation"],
                "source": s["edge"].get("source"),
                "evidence": s["edge"].get("provenance") or s["edge"].get("evidence_id"),
                "label": s.get("label"),
                "parent_label": s.get("parent_label"),
            }
            for s in result["path"]
        ],
        "connection": state,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", required=True)
    p.add_argument("--output", required=True)
    p.add_argument(
        "--baseline-targets", help="Optional baseline audit dataset_views.json"
    )
    p.add_argument(
        "--six-datasets",
        nargs="+",
        default=[
            "cub200",
            "fgvc_aircraft",
            "flowers102",
            "pets37",
            "stanford_cars",
            "stanford_dogs",
        ],
    )
    a = p.parse_args()
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    all_tasks = []
    all_portals = []
    samples = []
    search_checks = []
    errors = []
    started = time.perf_counter()
    for view in ("strict", "taxonomy", "membership"):
        with FineAtlas(a.database, relation_view=view) as tree:
            dump(out / (view + "_statistics.json"), tree.stats())
            targets = list(
                tree.con.execute(
                    "SELECT dataset,class_id FROM dataset_targets ORDER BY dataset,length(class_id),class_id"
                )
            )
            for index, (dataset, class_id) in enumerate(targets, 1):
                target = tree.target(dataset, class_id)
                uid = target["target_uid"]
                path = sample_path(tree, uid)
                requirements = {
                    r: target["native_label_admission"] if r == "native_label" else tree.eligibility(
                        uid,
                        r,
                        identity_verified=True
                        if r == "native_label"
                        else target["identity_verified"]
                        if r
                        in (
                            "identity",
                            "strict_classification",
                            "species",
                            "model",
                            "configuration",
                        )
                        else target["mapping_verified"],
                    )
                    for r in (
                        "native_label",
                        "identity",
                        "hierarchy",
                        "strict_classification",
                        "species",
                        "model",
                        "model_design",
                        "configuration",
                        "instance",
                    )
                }
                all_tasks.append(
                    {
                        "dataset": dataset,
                        "class_id": class_id,
                        "label": target.get("label"),
                        "target_uid": uid,
                        "relation_view": view,
                        "decision_status": target["decision_status"],
                        "identity_verified": target["identity_verified"],
                        "mapping_verified": target["mapping_verified"],
                        "mapping_kind": target["mapping_kind"],
                        "path": path,
                        "requirements": requirements,
                    }
                )
                if index % 200 == 0:
                    print("TASKS", view, index, len(targets), flush=True)
            for portal in tree.domains(include_aliases=True):
                name = portal.get("requested_domain", portal["domain"])
                roots = tree.domain_roots(name)
                children = tree.domain_children(name, 3)
                page = tree.domain_page(name, 3)
                instances = tree.domain_instances(name, 3)
                selector = "fineatlas-domain:" + name
                if tree.path_result(selector)["status"] != "NAVIGATION_ONLY":
                    raise AssertionError("Invalid portal contract: " + name)
                members = {
                    n["uid"]: n
                    for n in [*children, *page["items"], *instances["items"]]
                }
                checks = []
                for uid, n in sorted(members.items()):
                    # Compare the identical scoped exact-name condition; paged
                    # lookup avoids confusing result truncation with a miss.
                    cursor = None
                    found = False
                    count = 0
                    while True:
                        found_page = tree.search_page(
                            n["label"], 200, domain=name, cursor=cursor, exact=True
                        )
                        count += len(found_page["items"])
                        found = found or any(
                            x["uid"] == uid for x in found_page["items"]
                        )
                        cursor = found_page["next_cursor"]
                        if found or not cursor:
                            break
                    alias = tree.con.execute(
                        "SELECT 1 FROM aliases WHERE uid=? AND alias IN (?,?) LIMIT 1",
                        (
                            uid,
                            __import__("fineatlas._text", fromlist=["norm"]).norm(
                                n["label"]
                            ),
                            __import__(
                                "fineatlas._text", fromlist=["legacy_norm"]
                            ).legacy_norm(n["label"]),
                        ),
                    ).fetchone()
                    check = {
                        "domain": name,
                        "view": view,
                        "uid": uid,
                        "label": n["label"],
                        "stored_exact_alias": bool(alias),
                        "found_in_scope": found,
                        "examined_results": count,
                    }
                    checks.append(check)
                    search_checks.append(check)
                    if alias and not found:
                        errors.append({"kind": "MEMBER_SEARCH_MISS", **check})
                record = {
                    "requested_domain": name,
                    "canonical_domain": portal["domain"],
                    "relation_view": view,
                    "roots": [n["uid"] for n in roots],
                    "children": [n["uid"] for n in children],
                    "page_uids": [n["uid"] for n in page["items"]],
                    "instance_uids": [n["uid"] for n in instances["items"]],
                    "search_checks": checks,
                }
                all_portals.append(record)
                # Root, immediate subdivision and independent terminal sample
                # from each role are observed through the same public interface.
                selected = {
                    n["uid"]: n
                    for n in [*roots, *children, *page["items"], *instances["items"]]
                }
                for role in ("MODEL", "MODEL_FAMILY", "CONFIGURATION", "INSTANCE"):
                    role_page = tree.domain_page(name, 1, node_kind=role)
                    for n in role_page["items"]:
                        selected[n["uid"]] = n
                for uid, n in selected.items():
                    if n.get("navigation_only"):
                        continue
                    samples.append(
                        {
                            "domain": name,
                            "canonical_domain": portal["domain"],
                            "view": view,
                            "role": n["node_kind"],
                            "source_role": n.get("source_role"),
                            "native_rank": n.get("native_rank"),
                            "source_label": n.get("source_label"),
                            "path": sample_path(tree, uid),
                        }
                    )
                print("PORTAL", view, name, len(selected), flush=True)
            dump(out / (view + "_portal_checkpoint.json"), all_portals)
    summaries = []
    for dataset in sorted({r["dataset"] for r in all_tasks}):
        for view in ("strict", "taxonomy", "membership"):
            rows = [
                r
                for r in all_tasks
                if r["dataset"] == dataset and r["relation_view"] == view
            ]
            summaries.append(
                {
                    "dataset": dataset,
                    "view": view,
                    "labels": len(rows),
                    "strict_class_root": sum(
                        r["path"]["connection"].get(
                            "strict_classification_root_reachable", False
                        )
                        for r in rows
                    ),
                    "class_root_in_view": sum(
                        r["path"]["connection"].get(
                            "class_root_reachable_in_view", False
                        )
                        for r in rows
                    ),
                    "typed_root": sum(
                        r["path"]["connection"].get("typed_root_reachable", False)
                        for r in rows
                    ),
                    "root_path": sum(
                        r["path"]["status"] in ("CONNECTED", "ROOT") for r in rows
                    ),
                    **{
                        r + "_usable": sum(x["requirements"][r]["usable"] for x in rows)
                        for r in rows[0]["requirements"]
                    },
                }
            )
    with (out / "task_labels.jsonl").open("w") as f:
        for r in all_tasks:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (out / "six_dataset_labels.jsonl").open("w") as f:
        for r in all_tasks:
            if r["dataset"] in a.six_datasets:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (out / "task_summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    dump(out / "task_summary.json", summaries)
    dump(out / "portals.json", all_portals)
    dump(out / "search_scope_checks.json", search_checks)
    with (out / "stratified_paths.jsonl").open("w") as f:
        for r in samples:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = {
        "observed_task_records": len(all_tasks) // 3,
        "observed_legacy_portals": len(all_portals) // 3,
        "six_dataset_labels": sum(
            r["labels"]
            for r in summaries
            if r["view"] == "strict" and r["dataset"] in a.six_datasets
        ),
        "view_task_checks": len(all_tasks),
        "view_portal_checks": len(all_portals),
        "public_path_samples": len(samples),
        "member_search_checks": len(search_checks),
        "errors": errors,
        "seconds": time.perf_counter() - started,
        "semantic_boundary": "Interface/contract audit and source-grounded sampled paths; not a scientific certification of all claims.",
    }
    dump(out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if errors:
        raise SystemExit("Public interface audit failed; see summary.json")


if __name__ == "__main__":
    main()
