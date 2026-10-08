"""View-consistent access, stable pages and DAG queries for FineAtlas."""

from __future__ import annotations

from collections import deque
import base64
import hashlib
import json
import re
from pathlib import Path

from .single import SingleAtlas
from ._text import norm, legacy_norm, tokens
from .semantics import (
    CLASS_ROLES,
    ROLE_ALIASES,
    TYPED_TERMINALS,
    VIEWS,
    QueryLimitError,
    ResultList,
    edge_predicate,
    role_for_rank,
    role_expression,
    source_admission_view,
    terminal_relations,
    classification_roles,
    navigation_parent_roles,
)


class ConsistentAtlas(SingleAtlas):
    def __init__(
        self, path, view="wordnet", relation_view=None, *, root=None, language="en"
    ):
        super().__init__(path, view=view, relation_view=relation_view)
        self.root_uid = root or self.metadata["root_uid"]
        self.language = language
        if (
            "usability_indexes_ready" in self.metadata
            and not self.metadata["usability_indexes_ready"]
        ):
            self.con.close()
            raise ValueError(
                "Database migration is incomplete; rebuild query indexes before use"
            )
        self._node_cache = {}
        self._parent_cache = {}
        self._domain_cache = {}
        self._revision = self.metadata.get(
            "database_revision",
            self.metadata.get("release", "") + ":" + str(self.path_file.stat().st_size),
        )
        if self.root_uid.startswith("fineatlas-domain:"):
            raise ValueError(
                "A navigation portal is not a hierarchy root; select a native root UID"
            )
        if not self.con.execute(
            "SELECT 1 FROM nodes WHERE uid=?", (self.root_uid,)
        ).fetchone():
            raise ValueError("Unknown hierarchy root UID: " + self.root_uid)
        self.roots = {"entity": self.root_uid}

    def _node(self, row, edge=None):
        if not row:
            return None
        native = dict(row)
        result = super()._node(row, edge)
        result["source_domain"] = native.get("domain", "")
        if not result.get("description"):
            raw = result.get("data") or {}
            description = (
                raw.get("wikidata_description")
                or (raw.get("evidence_record") or {}).get("wikidata_description")
                or raw.get("description")
            )
            if description:
                result["description"] = description
                result["definition_source"] = "Retained native source payload"
                result["definition_basis"] = {
                    "native_uid": result["uid"],
                    "native_payload_sha256": hashlib.sha256(
                        native["data"].encode()
                    ).hexdigest(),
                    "source": native.get("source"),
                }

        if not result.get("description") and "node_definitions" in self._tables:
            definition = self.con.execute(
                "SELECT * FROM node_definitions WHERE uid=?", (result["uid"],)
            ).fetchone()
            if definition:
                result["description"] = definition["description"]
                result["definition_source"] = definition["source"]
                result["definition_evidence_id"] = definition["evidence_id"]
        domains = json.loads(native.get("domains") or "[]")
        # Native domain declarations precede stale extension profile hints.
        # Resolve through the persisted registry, never through role/name rules.
        if "domain_registry" in self._tables:
            if not hasattr(self, "_native_domain_aliases"):
                self._native_domain_aliases = {
                    r[0]: r[1] for r in self.con.execute(
                        "SELECT a.alias,r.canonical_name FROM domain_aliases a "
                        "JOIN domain_registry r ON r.domain_id=a.domain_id"
                    )
                }
            declared = [native.get("domain", ""), *domains]
            resolved = [self._native_domain_aliases.get(str(x).casefold())
                        or self._native_domain_aliases.get(norm(str(x)))
                        for x in declared if x]
            resolved = [x for x in resolved if x]
            if resolved and result["domain"] != resolved[0]:
                result["profile_domain"] = result["domain"]
                result["domain"] = resolved[0]
                result["domain_basis"] = "Retained native declarations resolved by domain registry"
        if result["domain"] and result["domain"] not in domains:
            domains.append(result["domain"])
        result["domains"] = json.dumps(domains, ensure_ascii=False)
        has_profile = (
            "node_profiles" in self._tables
            and self.con.execute(
                "SELECT 1 FROM node_profiles WHERE uid=?", (result["uid"],)
            ).fetchone()
        )
        if not has_profile:
            result["node_kind"] = role_for_rank(result.get("rank"), result.get('source'))
        result["source_role"] = (
            result["attributes"].get(
                "source_role",
                result["attributes"].get("native_rank", native.get("rank")),
            )
            or "UNSPECIFIED"
        )
        result["normalized_role"] = result["node_kind"]
        native_rank = (result.get("native_rank") or result.get("rank") or "").casefold()
        taxonomic_ranks = {
            "species",
            "cultivar",
            "subspecies",
            "variety",
            "genus",
            "family",
            "order",
            "phylum",
            "kingdom",
            "domain",
        }
        own_rank = native_rank if native_rank in taxonomic_ranks else None
        raw_ranks = {
            str(x).casefold()
            for x in (result.get("data") or {}).get("taxonomic_ranks", [])
            if str(x).casefold() in taxonomic_ranks | {"class"}
        }
        if not own_rank and len(raw_ranks) == 1:
            own_rank = next(iter(raw_ranks))
        rank_assertion = (
            self.con.execute(
                "SELECT * FROM node_taxon_ranks WHERE uid=?", (result["uid"],)
            ).fetchone()
            if "node_taxon_ranks" in self._tables
            else None
        )
        if rank_assertion:
            result["source_taxon_rank"] = rank_assertion["rank"]
            result["taxon_rank_evidence_id"] = rank_assertion["evidence_id"]
            if rank_assertion["status"] == "SOURCE_DECLARED" and not own_rank:
                own_rank = rank_assertion["rank"]
        peer_ranks = set()
        if result["node_kind"] == "CLASS":
            peer_query = (
                "SELECT coalesce(t.rank,CASE WHEN json_array_length(json_extract(n.data,'$.taxonomic_ranks'))=1 THEN json_extract(n.data,'$.taxonomic_ranks[0]') END,nullif(n.rank,'class')) FROM nodes n LEFT JOIN node_taxon_ranks t ON t.uid=n.uid AND t.status='SOURCE_DECLARED' WHERE n.component_id=? AND n.visibility='ACTIVE'"
                if "node_taxon_ranks" in self._tables
                else "SELECT coalesce(CASE WHEN json_array_length(json_extract(data,'$.taxonomic_ranks'))=1 THEN json_extract(data,'$.taxonomic_ranks[0]') END,nullif(rank,'class')) FROM nodes WHERE component_id=? AND visibility='ACTIVE'"
            )
            for peer in self.con.execute(peer_query, (result["component_id"],)):
                if (peer[0] or "").casefold() in taxonomic_ranks | {"class"}:
                    peer_ranks.add(peer[0].casefold())
        result["normalized_rank"] = own_rank or (
            next(iter(peer_ranks)) if len(peer_ranks) == 1 else None
        )
        result["rank_status"] = (
            "CONFLICT_REVIEW"
            if len(peer_ranks) > 1
            else "SOURCE_DECLARED"
            if own_rank
            else "IDENTITY_PEER_SOURCE_DECLARED"
            if peer_ranks
            else "UNSPECIFIED"
        )
        if len(raw_ranks) > 1:
            result["rank_status"] = "CONFLICT_REVIEW"
            result["normalized_rank"] = None
        if rank_assertion and rank_assertion["status"] == "CONFLICT_REVIEW":
            result["rank_status"] = "CONFLICT_REVIEW"
            result["normalized_rank"] = None
        result["rank_basis"] = (
            "Native source rank; accepted identifier-grounded identity peers used only when unambiguous"
        )

        result["role_status"] = result["attributes"].get(
            "role_status",
            "SOURCE_ONLY_UNASSESSED"
            if native.get("visibility") == "SOURCE_ONLY"
            else "REVIEW"
            if result["node_kind"] == "UNKNOWN"
            else "SOURCE_DECLARED"
            if has_profile
            else "LEGACY_RANK_FALLBACK",
        )
        stored_aliases = self.aliases(result["uid"], limit=100)
        result["aliases"] = [x["name"] for x in stored_aliases]
        result["aliases_truncated"] = stored_aliases.truncated
        if "node_names" in self._tables:
            name = self.con.execute(
                """SELECT name,language,source,evidence_id FROM node_names
                WHERE uid=?
                ORDER BY (language=?) DESC,(language='en') DESC,(language='mul') DESC,(language='und') DESC,preferred DESC,source,name LIMIT 1""",
                (result["uid"], self.language),
            ).fetchone()
            if name:
                result["source_label"] = result["label"]
                result["label"] = name["name"]
                result["label_language"] = name["language"]
                result["label_source"] = name["source"]
                result["label_evidence_id"] = name["evidence_id"]
        result["label_fallback"] = bool(
            re.fullmatch(r"Q\d+", result["label"]) or result["label"] == result["uid"]
        )
        return result

    def aliases(self, uid, limit=100, *, language=None):
        self._limit(limit)
        values = []
        if "node_names" in self._tables:
            sql = "SELECT name,language,source,evidence_id,preferred FROM node_names WHERE uid=?"
            args = [uid]
            if language:
                sql += " AND language=?"
                args.append(language)
            values = [
                dict(r)
                for r in self.con.execute(
                    sql + " ORDER BY language,preferred DESC,name,source LIMIT ?",
                    [*args, limit + 1],
                )
            ]
        if language in (None, "und"):
            columns = {r[1] for r in self.con.execute("PRAGMA table_info(aliases)")}
            name = (
                "raw_alias"
                if "raw_alias" in columns
                else "original_alias"
                if "original_alias" in columns
                else "alias"
            )
            source_column = "source" if "source" in columns else "'stored_alias'"
            values.extend(
                {
                    "name": r[0],
                    "language": "und",
                    "source": r[1],
                    "evidence_id": None,
                    "preferred": 0,
                }
                for r in self.con.execute(
                    f"SELECT DISTINCT {name},{source_column} FROM aliases WHERE uid=? ORDER BY 1,2 LIMIT ?",
                    (uid, limit + 1),
                )
            )
        unique = {(v["name"], v["language"], v["source"]): v for v in values}
        result = sorted(
            unique.values(),
            key=lambda v: (v["language"], -v["preferred"], v["name"], v["source"]),
        )
        return ResultList(result[:limit], has_more=len(result) > limit)

    def node(self, uid):
        result = super().node(uid)
        if result and not result.get("navigation_only"):
            record = self._root_record(uid)
            if record is not None:
                result["root_reachable"] = record["root_reachable"]
                result["root_depth"] = record["depth"]
                result["typed_root_reachable"] = (
                    record["root_reachable"] and record["typed_route"]
                )
                result["relation_view"] = self.relation_view
                result["root_uid"] = self.root_uid
            if "view_terminal_connections" in self._tables:
                row = self.con.execute(
                    "SELECT depth FROM view_terminal_connections WHERE view='strict' AND uid=?",
                    (uid,),
                ).fetchone()
                result["entity_reachable"] = bool(row)
                result["typed_depth"] = row[0] if row else None
        return result

    def stats(self):
        result = super().stats()
        views = self.metadata.get("usability_view_statistics", {})
        if views:
            # The immutable baseline metadata is retained for provenance. Its
            # aggregate snapshots do not describe the migrated database.
            for key in ("counts", "edge_statuses", "bridge_statuses",
                        "typed_statuses", "coverage_by_namespace", "datasets",
                        "wordnet_reachable_components"):
                result.pop(key, None)
            selected = views[self.relation_view]
            roles = self.metadata.get("usability_role_counts", {})
            result["counts"] = {
                "nodes": self.metadata["nodes"],
                "active_nodes": self.metadata["active_nodes"],
                "source_only_nodes": self.metadata["source_only_nodes"],
                "active_edges": self.metadata["strict_classification_edges"],
                "aliases": self.metadata["aliases"],
                "retained_classification_uids": sum(roles.get(r, 0) for r in CLASS_ROLES),
                "strict_root_reachable_classification_uids": views["strict"]["class_root_source_uids"],
                "classification_root_groups_in_view": selected["class_root_groups"],
                "classification_root_source_uids_in_view": selected["class_root_source_uids"],
                "typed_terminal_root_uids_in_view": selected["typed_terminal_root_uids"],
                "canonical_domains": self.metadata["canonical_domains"],
                "domain_entries": self.con.execute("SELECT count(*) FROM domain_entries").fetchone()[0],
                "dataset_targets": self.con.execute("SELECT count(*) FROM dataset_targets").fetchone()[0],
            }
            result["statistics_root_uid"] = self.metadata["root_uid"]
            result["statistics_scope"] = "Whole database; rooted view counts use statistics_root_uid"
        return {
            **result,
            "database_revision": self._revision,
            "relation_view": self.relation_view,
            "root_uid": self.root_uid,
            "view_statistics": self.metadata.get("usability_view_statistics", {}),
            "role_counts": self.metadata.get("usability_role_counts", {}),
        }

    def _root_record(self, uid):
        if (
            "view_paths" not in self._tables
            or self.root_uid != self.metadata["root_uid"]
        ):
            return None
        own = self._basic(uid)
        if not own:
            return None
        if not self._node_admitted(own) or (
            not self._role_allowed(own["node_kind"])
            and own["node_kind"] not in TYPED_TERMINALS
        ):
            return None
        row = self.con.execute(
            "SELECT * FROM view_paths WHERE view=? AND component_id=?",
            (self.relation_view, own["component_id"]),
        ).fetchone()
        pure = (
            bool(
                self.con.execute(
                    "SELECT 1 FROM view_roots WHERE view=? AND component_id=?",
                    (self.relation_view, own["component_id"]),
                ).fetchone()
            )
            if "view_roots" in self._tables
            else bool(row and not row["contains_terminal"])
        )
        strict_allowed = own["node_kind"] in CLASS_ROLES and (
            own.get("allowed_views") is None or "strict" in own["allowed_views"]
        )
        strict = (
            bool(
                strict_allowed
                and self.con.execute(
                    "SELECT 1 FROM view_roots WHERE view='strict' AND component_id=?",
                    (own["component_id"],),
                ).fetchone()
            )
            if "view_roots" in self._tables
            else pure
            if self.relation_view == "strict"
            else False
        )
        return {
            "root_reachable": bool(row),
            "depth": row["depth"] if row else None,
            "terminal": bool(row and row["contains_terminal"]),
            "class_in_view": pure,
            "strict_class": strict,
            "typed_route": bool(
                row
                and (
                    row["typed_route"]
                    if "typed_route" in row.keys()
                    else row["contains_terminal"]
                )
            ),
            "navigation_route": bool(row and row["contains_navigation"])
            if row and "contains_navigation" in row.keys()
            else False,
        }

    def _witness_path(self, uid, record, max_depth):
        if not record["root_reachable"]:
            return {
                "uid": uid,
                "status": "UNREACHABLE",
                "path": [],
                "relation_view": self.relation_view,
                "root_uid": self.root_uid,
            }
        if record["depth"] > max_depth:
            return {
                "uid": uid,
                "status": "DEPTH_LIMIT",
                "path": [],
                "relation_view": self.relation_view,
                "root_uid": self.root_uid,
            }
        upward = []
        current = uid
        while True:
            own = self._basic(current)
            r = self.con.execute(
                "SELECT * FROM view_paths WHERE view=? AND component_id=?",
                (self.relation_view, own["component_id"]),
            ).fetchone()
            if not r:
                raise RuntimeError("Corrupt root witness; rebuild query indexes")
            if r["depth"] == 0:
                upward.extend(self._identity_steps(current, self.root_uid))
                break
            witness = r["witness_id"]
            table = "edges" if witness > 0 else "entity_relations"
            row = self.con.execute(
                "SELECT * FROM " + table + " WHERE id=?", (abs(witness),)
            ).fetchone()
            if row is None:
                raise RuntimeError("Missing path witness")
            edge = self._edge(row)
            if witness < 0:
                edge.update(
                    child_uid=row["subject_uid"],
                    parent_uid=row["object_uid"],
                    terminal_connection=True,
                )
            upward.extend(self._identity_steps(current, edge["child_uid"]))
            upward.append(self._step_for(edge["child_uid"], edge["parent_uid"], edge))
            current = edge["parent_uid"]
        return {
            "uid": uid,
            "status": "ROOT" if not upward else "CONNECTED",
            "path": list(reversed(upward)),
            "distance": record["depth"],
            "relation_view": self.relation_view,
            "root_uid": self.root_uid,
        }

    def _basic(self, uid):
        if uid not in self._node_cache:
            row = self.con.execute(
                "SELECT uid,label,rank,source,visibility,component_id FROM nodes WHERE uid=?",
                (uid,),
            ).fetchone()
            if row:
                value = dict(row)
                profile = (
                    self.con.execute(
                        "SELECT node_kind,attributes FROM node_profiles WHERE uid=?",
                        (uid,),
                    ).fetchone()
                    if "node_profiles" in self._tables
                    else None
                )
                value["node_kind"] = (
                    profile[0] if profile else role_for_rank(value["rank"],value.get('source'))
                )
                value["allowed_views"] = (
                    json.loads(profile[1]).get("allowed_views") if profile else None
                )
                self._node_cache[uid] = value
            else:
                self._node_cache[uid] = None
        return self._node_cache[uid]

    def _node_admitted(self, node):
        return bool(
            node
            and node["visibility"] == "ACTIVE"
            and (
                node.get("allowed_views") is None
                or source_admission_view(self.relation_view) in node["allowed_views"]
            )
        )

    def _role_allowed(self, role):
        return role in classification_roles(self.relation_view)

    def _parents(self, uid, *, include_terminal=True):
        key = (self.relation_view, uid, include_terminal)
        if key in self._parent_cache:
            return self._parent_cache[key]
        own = self._basic(uid)
        if not self._node_admitted(own):
            return []
        out = []
        if self._role_allowed(own["node_kind"]):
            for row in self.con.execute(
                f"""SELECT e.* FROM nodes a CROSS JOIN edges e
                CROSS JOIN nodes p WHERE a.component_id=? AND e.child_uid=a.uid
                AND p.uid=e.parent_uid AND a.visibility='ACTIVE' AND p.visibility='ACTIVE'
                AND {edge_predicate(self.relation_view)} ORDER BY e.id""",
                (own["component_id"],),
            ):
                parent = self._basic(row["parent_uid"])
                child = self._basic(row["child_uid"])
                if (
                    not self._node_admitted(child)
                    or not self._role_allowed(child["node_kind"])
                    or not self._node_admitted(parent)
                    or not self._role_allowed(parent["node_kind"])
                ):
                    continue
                edge = self._edge(row)
                out.append((edge["parent_uid"], edge))
        if include_terminal and "entity_relations" in self._tables:
            relations = (
                tuple(
                    sorted(
                        {
                            rel
                            for kind, rels in TYPED_TERMINALS.items()
                            if kind in CLASS_ROLES
                            for rel in terminal_relations(kind, self.relation_view)
                        }
                    )
                )
                if own["node_kind"] in CLASS_ROLES
                else terminal_relations(own["node_kind"], self.relation_view)
            )
            if relations:
                marks = ",".join("?" for _ in relations)
                for row in self.con.execute(
                    f"""SELECT r.* FROM nodes a CROSS JOIN entity_relations r WHERE a.component_id=? AND r.subject_uid=a.uid
                    AND r.status='ACTIVE' AND r.relation IN ({marks}) ORDER BY r.id""",
                    (own["component_id"], *relations),
                ):
                    parent = self._basic(row["object_uid"])
                    child = self._basic(row["subject_uid"])
                    if not self._node_admitted(child) or row[
                        "relation"
                    ] not in terminal_relations(child["node_kind"], self.relation_view):
                        continue
                    compatible = (
                        child["node_kind"] in CLASS_ROLES
                        if own["node_kind"] in CLASS_ROLES
                        else child["node_kind"] == own["node_kind"]
                    )
                    if not compatible:
                        continue
                    if self._node_admitted(parent) and parent["node_kind"] in navigation_parent_roles(self.relation_view):
                        edge = self._edge(row)
                        edge["child_uid"] = row["subject_uid"]
                        edge["parent_uid"] = edge["object_uid"]
                        edge["terminal_connection"] = True
                        out.append((edge["object_uid"], edge))
        self._parent_cache[key] = out
        return out

    def _step_for(self, uid, parent, edge):
        result = self._step(uid, parent, edge)
        result["relation_view"] = self.relation_view
        return result

    def path_result(self, uid, anchors=None, max_depth=256):
        if max_depth < 0:
            raise ValueError("max_depth must be nonnegative")
        if uid.startswith("fineatlas-domain:"):
            entry = self.domain(uid)
            return {
                "uid": uid,
                "status": "NAVIGATION_ONLY" if entry else "NOT_FOUND",
                "path": [],
                "relation_view": self.relation_view,
                "root_uid": self.root_uid,
                "root_uids": entry.get("root_uids", []) if entry else [],
            }
        own = self._basic(uid)
        if not own:
            return {
                "uid": uid,
                "status": "NOT_FOUND",
                "path": [],
                "relation_view": self.relation_view,
                "root_uid": self.root_uid,
            }
        if own["visibility"] != "ACTIVE":
            return {
                "uid": uid,
                "status": "NOT_ADMITTED",
                "path": [],
                "relation_view": self.relation_view,
                "root_uid": self.root_uid,
            }
        if not self._node_admitted(own) or (
            not self._role_allowed(own["node_kind"])
            and own["node_kind"] not in TYPED_TERMINALS
        ):
            return {
                "uid": uid,
                "status": "VIEW_NOT_APPLICABLE",
                "path": [],
                "relation_view": self.relation_view,
                "root_uid": self.root_uid,
            }
        record = (
            self._root_record(uid)
            if anchors is None or anchors == [self.root_uid]
            else None
        )
        if record is not None:
            return self._witness_path(uid, record, max_depth)
        goals = anchors or [self.root_uid]
        goal_nodes = [self._basic(g) for g in goals]
        if any(g is None for g in goal_nodes):
            raise ValueError("Unknown anchor UID")
        comps = {n["component_id"] for n in goal_nodes}
        queue = deque([(uid, [], 0)])
        seen = {own["component_id"]}
        depth_cut = False
        while queue:
            current, upward, depth = queue.popleft()
            node = self._basic(current)
            if node["component_id"] in comps:
                goal = next(
                    g
                    for g, n in zip(goals, goal_nodes)
                    if n["component_id"] == node["component_id"]
                )
                alignment = (
                    self._identity_steps(current, goal) if current != goal else []
                )
                return {
                    "uid": uid,
                    "status": "ROOT" if not upward and not alignment else "CONNECTED",
                    "path": list(reversed(upward + alignment)),
                    "relation_view": self.relation_view,
                    "root_uid": goal,
                    "distance": depth,
                }
            parents = self._parents(current)
            if depth >= max_depth:
                depth_cut = depth_cut or bool(parents)
                continue
            for parent, edge in parents:
                pn = self._basic(parent)
                if pn["component_id"] in seen:
                    continue
                seen.add(pn["component_id"])
                aligned = (
                    self._identity_steps(current, edge["child_uid"])
                    if current != edge["child_uid"]
                    else []
                )
                queue.append(
                    (
                        parent,
                        upward
                        + aligned
                        + [self._step_for(edge["child_uid"], parent, edge)],
                        depth + 1,
                    )
                )
            if len(seen) > 100000:
                raise QueryLimitError("Path search exceeded 100000 identity groups")
        return {
            "uid": uid,
            "status": "DEPTH_LIMIT" if depth_cut else "UNREACHABLE",
            "path": [],
            "relation_view": self.relation_view,
            "root_uid": self.root_uid,
        }

    def path(self, uid, anchors=None, max_depth=256):
        return self.path_result(uid, anchors, max_depth)["path"]

    def connection_status(self, uid):
        if uid.startswith("fineatlas-domain:"):
            entry = self.domain(uid)
            return (
                ({'uid':uid,'status':'NOT_FOUND','path_status':'NOT_FOUND','root_reachable':False,
                  'view_admitted':False,'relation_view':self.relation_view,'root_uid':self.root_uid}
                 if self.relation_view=='unified' else None)
                if not entry
                else {
                    "uid": uid,
                    "status": "NAVIGATION_ENTRY",
                    "tree_admission": "NAVIGATION_ONLY",
                    "root_uids": entry["root_uids"],
                    "relation_view": self.relation_view,
                }
            )
        node = self._basic(uid)
        if not node:
            return ({'uid':uid,'status':'NOT_FOUND','path_status':'NOT_FOUND',
                     'root_reachable':False,'view_admitted':False,
                     'relation_view':self.relation_view,'root_uid':self.root_uid}
                    if self.relation_view=='unified' else None)
        record = self._root_record(uid) if self._node_admitted(node) else None
        if record is not None:
            connected = record["root_reachable"]
            terminal = bool(record["typed_route"])
            strict_class = record["strict_class"]
            class_in_view = record["class_in_view"]
            native_navigation = record["navigation_route"]
            path = {
                "status": "CONNECTED"
                if connected and record["depth"]
                else "ROOT"
                if connected
                else "UNREACHABLE"
            }
        else:
            path = self.path_result(uid)
            connected = path["status"] in ("CONNECTED", "ROOT")
            terminal = any(s["edge"].get("terminal_connection") for s in path["path"])
            class_in_view = self._classification_reachable(uid, self.relation_view)
            strict_class = self._classification_reachable(uid, "strict")
            native_navigation = any(
                s["edge"]["relation"]
                in (
                    "NATIVE_CLASSIFICATION_PARENT",
                    "REUSABLE_TYPE_MEMBERSHIP",
                    "REGULATED_AS",
                )
                for s in path["path"]
            )
        return {
            "uid": uid,
            "status": path["status"],
            "path_status": path["status"],
            "relation_view": self.relation_view,
            "root_uid": self.root_uid,
            "record_role": node["node_kind"],
            "visibility": node["visibility"],
            "view_admitted": self._node_admitted(node)
            and (
                self._role_allowed(node["node_kind"])
                or node["node_kind"] in TYPED_TERMINALS
            ),
            "root_reachable": connected,
            "classification_root_reachable": class_in_view if self.relation_view=='unified' else strict_class,
            "strict_classification_root_reachable": strict_class,
            "class_root_reachable_in_view": class_in_view,
            "native_navigation_root_reachable": native_navigation,
            "typed_root_reachable": connected and terminal,
            "wordnet_reachable": bool(
                self.con.execute(
                    "SELECT wordnet_reachable FROM components WHERE id=?",
                    (node["component_id"],),
                ).fetchone()[0]
            ),
            "wordnet_depth": self.con.execute(
                "SELECT depth FROM components WHERE id=?", (node["component_id"],)
            ).fetchone()[0],
            "tree_admission": "NOT_ADMITTED"
            if node["visibility"] != "ACTIVE"
            else node["node_kind"] + "_ONLY"
            if node["node_kind"] in ("INSTANCE", "ATTRIBUTE", "DATASET_CATEGORY")
            else "TAXONOMY_ONLY"
            if node["node_kind"] == "BIOLOGICAL_VARIANT"
            else "ACTIVE"
            if connected
            else "NOT_ROOT_CONNECTED",
            "reason": "Path and status use the same relation view; typed terminal connections remain separate from class inclusion",
        }

    def _classification_reachable(self, uid, view):
        def applicable(own):
            return bool(
                own
                and own["visibility"] == "ACTIVE"
                and (
                    own["node_kind"] in classification_roles(view)
                )
                and (own.get("allowed_views") is None or source_admission_view(view) in own["allowed_views"])
            )

        own = self._basic(uid)
        if not applicable(own):
            return False
        if self.root_uid == self.metadata["root_uid"] and view == "strict":
            return bool(
                self.con.execute(
                    "SELECT wordnet_reachable FROM components WHERE id=?",
                    (own["component_id"],),
                ).fetchone()[0]
            )
        goal = self._basic(self.root_uid)["component_id"]
        queue = deque([uid])
        seen = {own["component_id"]}
        while queue:
            current = queue.popleft()
            comp = self._basic(current)["component_id"]
            if comp == goal:
                return True
            for row in self.con.execute(
                f"SELECT e.child_uid,e.parent_uid FROM nodes n CROSS JOIN edges e WHERE n.component_id=? AND e.child_uid=n.uid AND {edge_predicate(view)}",
                (comp,),
            ):
                child = self._basic(row[0])
                parent = self._basic(row[1])
                if (
                    applicable(child)
                    and applicable(parent)
                    and parent["component_id"] not in seen
                ):
                    seen.add(parent["component_id"])
                    queue.append(row[1])
                    if len(seen) > 100000:
                        raise QueryLimitError(
                            "Class-only root traversal exceeded 100000 groups"
                        )
        return False

    def _relation_sql(self, alias="e"):
        return edge_predicate(self.relation_view, alias)

    def domains(self, *, include_aliases=False):
        if "domain_registry" in self._tables:
            values = []
            for row in self.con.execute(
                "SELECT * FROM domain_registry ORDER BY domain_id"
            ):
                item = dict(row)
                item["domain"] = item.pop("canonical_name")
                item["root_uids"] = json.loads(item["root_uids"])
                item["uid"] = item["entry_uid"]
                item["aliases"] = [
                    r[0]
                    for r in self.con.execute(
                        "SELECT alias FROM domain_aliases WHERE domain_id=? ORDER BY alias",
                        (item["domain_id"],),
                    )
                ]
                values.append(item)
            if include_aliases:
                legacy = []
                for row in self.con.execute(
                    "SELECT domain FROM domain_entries ORDER BY domain"
                ):
                    item = self.domain(row[0])
                    item["requested_domain"] = row[0]
                    item["is_alias"] = row[0] != item["domain"]
                    legacy.append(item)
                return legacy
            return values
        # Compatibility for older schemas and synthetic fixtures.
        return super().domains()

    def domain(self, name):
        requested = name.removeprefix("fineatlas-domain:").casefold()
        if "domain_registry" in self._tables:
            row = self.con.execute(
                """SELECT r.* FROM domain_registry r JOIN domain_aliases a
                ON a.domain_id=r.domain_id WHERE a.alias IN (?,?) ORDER BY (a.alias=?) DESC LIMIT 1""",
                (requested, norm(requested), requested),
            ).fetchone()
            if not row:
                return None
            out = dict(row)
            out["domain"] = out.pop("canonical_name")
            out["root_uids"] = json.loads(out["root_uids"])
            out["uid"] = out["entry_uid"]
            out["requested_name"] = requested
            return out
        return super().domain(name)

    def identity(self, uid):
        own = self._basic(uid)
        if not own:
            return None
        members = [
            self._node(row)
            for row in self.con.execute(
                "SELECT * FROM nodes WHERE component_id=? ORDER BY uid",
                (own["component_id"],),
            )
        ]
        roles = sorted({n["node_kind"] for n in members})
        links = [
            dict(row)
            for row in self.con.execute(
                "SELECT b.* FROM nodes n CROSS JOIN bridges b WHERE n.component_id=? AND b.left_uid=n.uid AND b.status='ACTIVE' AND b.relation='SAME_CONCEPT' ORDER BY b.id",
                (own["component_id"],),
            )
        ]
        return {
            "component_id": own["component_id"],
            "members": members,
            "accepted_identity_links": links,
            "normalized_roles": roles,
            "role_status": "CONFLICT_REVIEW" if len(roles) > 1 else "CONSISTENT",
            "identity_is_training_admission": False,
        }

    def browse_domain(self, name, limit=20):
        entry = self.domain(name)
        if not entry:
            if self.relation_view=='unified':
                return {'status':'NOT_FOUND','reason':'UNKNOWN_DOMAIN','domain':name,
                        'roots':[],'children':[],'relation_view':self.relation_view}
            raise ValueError("Unknown domain: " + name)
        return {
            "entry": entry,
            "roots": self.domain_roots(name),
            "children": self.domain_children(name, limit),
            "instances": self.domain_instances(name, limit),
            "relation_view": self.relation_view,
            "scope_semantics": "Native roots and accepted hierarchy/typed descendants; roots are navigation scope, not new IS_A wrappers",
        }

    def _scope_components(self, name):
        if name in self._domain_cache:
            return self._domain_cache[name]
        entry = self.domain(name)
        if not entry:
            return None
        if "domain_components" in self._tables:
            self._domain_cache[name] = entry
            return entry
        # Old small databases use the same graph contract without materialization.
        seen = set()
        queue = deque(entry.get("root_uids") or [entry["uid"]])
        while queue:
            uid = queue.popleft()
            node = self._basic(uid)
            if not node or node["component_id"] in seen:
                continue
            seen.add(node["component_id"])
            for child in self._descendants_one(uid):
                queue.append(child)
            if len(seen) > 100000:
                raise QueryLimitError(
                    "Legacy domain traversal requires migration for large scopes"
                )
        entry = {**entry, "components": seen}
        self._domain_cache[name] = entry
        return entry

    def _domain_filter(self, domain, alias="n"):
        if not domain:
            return "", []
        entry = self._scope_components(domain)
        if entry:
            if "domain_members" in self._tables:
                return (
                    f" AND EXISTS(SELECT 1 FROM domain_members dm WHERE dm.domain_id=? AND dm.view=? AND dm.uid={alias}.uid)",
                    [entry["domain_id"], self.relation_view],
                )
            if "domain_components" in self._tables:
                return (
                    f""" AND EXISTS(SELECT 1 FROM domain_components dc WHERE dc.domain_id=?
                    AND dc.view=? AND dc.component_id={alias}.component_id)""",
                    [entry["domain_id"], self.relation_view],
                )
            comps = sorted(entry["components"])
            if not comps:
                return " AND 0", []
            return (
                f" AND {alias}.component_id IN ({','.join('?' for _ in comps)})",
                comps,
            )
        if domain.startswith("source:"):
            value = domain[7:]
            return (
                f" AND ({alias}.domain=? OR EXISTS(SELECT 1 FROM json_each({alias}.domains) d WHERE d.value=?))",
                [value, value],
            )
        # Existing callers using a source domain retain explicit source-tag behavior.
        exists = self.con.execute(
            "SELECT 1 FROM nodes WHERE domain=? LIMIT 1", (domain,)
        ).fetchone()
        if exists:
            return (
                f" AND ({alias}.domain=? OR EXISTS(SELECT 1 FROM json_each({alias}.domains) d WHERE d.value=?))",
                [domain, domain],
            )
        raise ValueError("Unknown domain selector: " + domain)

    def _visible_sql(self, alias):
        visible = (
            f"{alias}.visibility IN ('ACTIVE','SOURCE_ONLY')"
            if self.view == "all"
            else self._admission_sql(alias)
        )
        if self.view == "wordnet" and self.root_uid != self.metadata["root_uid"]:
            return visible + self._selected_root_sql(alias)
        if self.view == "wordnet" and "view_paths" in self._tables:
            return (
                visible
                + f""" AND (EXISTS(SELECT 1 FROM view_paths vr WHERE vr.view='{self.relation_view}'
                AND vr.component_id={alias}.component_id )
                OR EXISTS(SELECT 1 FROM view_terminal_connections tc WHERE tc.view='{self.relation_view}' AND tc.uid={alias}.uid))"""
            )
        if self.view == "wordnet" and self.relation_view == "strict":
            return super()._visible_sql(alias) + " AND " + self._admission_sql(alias)
        return visible

    def _selected_root_sql(self, alias="n"):
        """Intersect collection queries with the explicitly selected root."""
        if self.view == "wordnet" and self.root_uid != self.metadata["root_uid"]:
            self._custom_scope()
            return f" AND EXISTS(SELECT 1 FROM selected_root_components sr WHERE sr.id={alias}.component_id)"
        return ""

    def _kind_sql(self, alias="n"):
        fallback = role_expression(alias, None)
        return (
            f"coalesce((SELECT p.node_kind FROM node_profiles p WHERE p.uid={alias}.uid),{fallback})"
            if "node_profiles" in self._tables
            else fallback
        )

    def _admission_sql(self, alias="n"):
        role = self._kind_sql(alias)
        permitted = sorted(
            CLASS_ROLES
            | set(TYPED_TERMINALS)
            | ({"BIOLOGICAL_VARIANT"} if self.relation_view in ("taxonomy", "unified") else set())
        )
        roles = ",".join("'" + x + "'" for x in permitted)
        extra = ""
        if "node_profiles" in self._tables:
            extra = f" AND NOT EXISTS(SELECT 1 FROM node_profiles ap WHERE ap.uid={alias}.uid AND json_type(ap.attributes,'$.allowed_views')='array' AND NOT EXISTS(SELECT 1 FROM json_each(ap.attributes,'$.allowed_views') av WHERE av.value='{source_admission_view(self.relation_view)}'))"
        return f"{alias}.visibility='ACTIVE' AND {role} IN ({roles})" + extra

    def _custom_scope(self):
        if getattr(self, "_custom_scope_ready", False):
            return
        own = self._basic(self.root_uid)
        queue = deque([self.root_uid])
        seen = {own["component_id"]}
        while queue:
            current = queue.popleft()
            for child in self._descendants_one(current):
                node = self._basic(child)
                comp = node["component_id"]
                if comp not in seen:
                    seen.add(comp)
                    queue.append(child)
                if len(seen) > 100000:
                    raise QueryLimitError(
                        "Custom root scope exceeds 100000 identity groups; use view=all for explicitly local browsing or a precomputed root projection"
                    )
        self.con.execute(
            "CREATE TEMP TABLE selected_root_components(id INTEGER PRIMARY KEY)"
        )
        self.con.executemany(
            "INSERT INTO selected_root_components VALUES (?)", ((x,) for x in seen)
        )
        self._custom_scope_ready = True

    def _kind_filter(self, kind, alias="n"):
        if kind is None:
            return "", []
        if kind == "PRODUCT_DESIGN":
            return " AND " + self._kind_sql(alias) + " IN ('MODEL','MODEL_FAMILY')", []
        return " AND " + self._kind_sql(alias) + "=?", [ROLE_ALIASES.get(kind, kind)]

    def _page_context(self, method, args):
        return {
            "api_contract": "1.9.0rc1",
            "revision": self._revision,
            "view": self.relation_view,
            "visibility": self.view,
            "root": self.root_uid,
            "method": method,
            "args": args,
        }

    def _after(self, cursor, context):
        if cursor is None:
            return ""
        try:
            data = json.loads(
                base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            )
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("Invalid page cursor") from error
        if data.get("context") != context or not isinstance(data.get("after"), str):
            raise ValueError("Cursor belongs to another database, view or query")
        return data["after"]

    def _page(self, rows, limit, context):
        rows = list(rows)
        more = len(rows) > limit
        items = [self._node(r) for r in rows[:limit]]
        cursor = (
            base64.urlsafe_b64encode(
                json.dumps(
                    {"context": context, "after": items[-1]["uid"]}, sort_keys=True
                ).encode()
            )
            .decode()
            .rstrip("=")
            if more
            else None
        )
        return {
            "items": items,
            "next_cursor": cursor,
            "has_more": more,
            "relation_view": self.relation_view,
            "database_revision": self._revision,
        }

    def search_page(
        self, text, limit=20, domain=None, *, node_kind=None, cursor=None, exact=False
    ):
        self._limit(limit)
        if limit > 10000:
            raise ValueError("Page limit must be at most 10000")
        context = self._page_context(
            "exact" if exact else "search", [text, domain, node_kind]
        )
        after = self._after(cursor, context)
        q = norm(text)
        if not q:
            return {
                "items": [],
                "next_cursor": None,
                "has_more": False,
                "relation_view": self.relation_view,
                "database_revision": self._revision,
            }
        try:
            domain_sql, domain_args = self._domain_filter(domain)
        except ValueError:
            if self.relation_view!='unified':raise
            return {'status':'NOT_FOUND','reason':'UNKNOWN_DOMAIN','domain':domain,
                    'items':[],'next_cursor':None,'has_more':False,
                    'relation_view':self.relation_view,'database_revision':self._revision}
        kind_sql, kind_args = self._kind_filter(node_kind)
        visible = (
            self._visible_sql("n")
            if not domain
            else (
                "n.visibility IN ('ACTIVE','SOURCE_ONLY')"
                if self.view == "all"
                else self._admission_sql("n")
            )
        )
        if domain:
            visible += self._selected_root_sql("n")
        if exact:
            match = "a.alias IN (?,?)"
            match_args = [q, legacy_norm(text) or q]
            candidates = f"SELECT DISTINCT a.uid FROM aliases a WHERE {match}"
        elif "alias_search" in self._tables:
            terms = tokens(text)[:6] or q.split()[:6]
            fts = " AND ".join('"' + term.replace('"', '""') + '"' for term in terms)
            candidates = "SELECT DISTINCT a.uid FROM alias_search f CROSS JOIN aliases a ON a.rowid=f.rowid WHERE alias_search MATCH ?"
            match_args = [fts]
        else:
            terms = tokens(text)[:6] or q.split()[:6]
            filters = ["a.alias LIKE ? ESCAPE '\\'" for _ in terms]
            candidates = "SELECT DISTINCT a.uid FROM aliases a WHERE " + " AND ".join(
                filters
            )
            match_args = [
                "%"
                + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                + "%"
                for term in terms
            ]
        # Identity groups are grounded by admitted SAME_CONCEPT, never by labels.
        legacy_root_filter = (
            self.view == "wordnet"
            and not domain
            and "view_paths" not in self._tables
            and self.relation_view != "strict"
        )
        query_limit = 100001 if legacy_root_filter else limit + 1
        rows = self.con.execute(
            f"""WITH matches AS ({candidates})
            SELECT DISTINCT n.* FROM matches m CROSS JOIN nodes a ON a.uid=m.uid
            CROSS JOIN nodes n ON n.component_id=a.component_id WHERE {visible}
            AND n.uid>? {domain_sql}{kind_sql} ORDER BY n.uid LIMIT ?""",
            [*match_args, after, *domain_args, *kind_args, query_limit],
        )
        if legacy_root_filter:
            accepted = []
            for i, row in enumerate(rows):
                if i >= 100000:
                    raise QueryLimitError(
                        "Legacy root filtering exceeded 100000 matches; migrate this database"
                    )
                if self.connection_status(row["uid"])["root_reachable"]:
                    accepted.append(row)
                if len(accepted) > limit:
                    break
            rows = accepted
        return self._page(rows, limit, context)

    def exact(self, text, limit=20, *, node_kind=None):
        page = self.search_page(text, limit, node_kind=node_kind, exact=True)
        return ResultList(page["items"], has_more=page["has_more"])

    def search(self, text, limit=20, domain=None, *, node_kind=None):
        exact = self.search_page(text, limit, domain, node_kind=node_kind, exact=True)
        page = self.search_page(
            text, min(10000, max(80, limit * 4)), domain, node_kind=node_kind
        )
        values = {n["uid"]: n for n in [*exact["items"], *page["items"]]}
        ordered = sorted(
            values.values(), key=lambda n: (norm(n["label"]) != norm(text), n["uid"])
        )
        return ResultList(
            ordered[:limit],
            has_more=exact["has_more"] or page["has_more"] or len(ordered) > limit,
        )

    def domain_page(self, name, limit=20, *, cursor=None, node_kind=None):
        self._limit(limit)
        if limit > 10000:
            raise ValueError("Page limit must be at most 10000")
        entry = self.domain(name)
        if not entry:
            if self.relation_view=='unified':
                return {'status':'NOT_FOUND','reason':'UNKNOWN_DOMAIN','domain':name,
                        'items':[],'next_cursor':None,'has_more':False,
                        'relation_view':self.relation_view,'database_revision':self._revision}
            raise ValueError("Unknown domain: " + name)
        context = self._page_context("domain", [entry["domain"], node_kind])
        after = self._after(cursor, context)
        scope, args = self._domain_filter(name)
        kind, kargs = self._kind_filter(node_kind)
        root_scope = self._selected_root_sql("n")
        if "domain_members" in self._tables:
            role_clause = ""
            role_args = []
            if node_kind == "PRODUCT_DESIGN":
                role_clause = " AND dm.role IN ('MODEL','MODEL_FAMILY')"
            elif node_kind:
                role_clause = " AND dm.role=?"
                role_args = [ROLE_ALIASES.get(node_kind, node_kind)]
            rows = self.con.execute(
                f"""SELECT n.* FROM domain_members dm CROSS JOIN nodes n WHERE dm.domain_id=?
                AND dm.view=? {role_clause} AND dm.uid>? AND n.uid=dm.uid {root_scope} ORDER BY dm.uid LIMIT ?""",
                [entry["domain_id"], self.relation_view, *role_args, after, limit + 1],
            )
        elif "domain_components" in self._tables:
            rows = self.con.execute(
                f"""SELECT n.* FROM domain_components dc CROSS JOIN nodes n
                WHERE dc.domain_id=? AND dc.view=? AND n.component_id=dc.component_id
                AND {self._admission_sql("n")} AND n.uid>? {kind} {root_scope} ORDER BY n.uid LIMIT ?""",
                [entry["domain_id"], self.relation_view, after, *kargs, limit + 1],
            )
        else:
            rows = self.con.execute(
                f"""SELECT n.* FROM nodes n WHERE n.visibility='ACTIVE'
                AND n.uid>? {scope}{kind}{root_scope} ORDER BY n.uid LIMIT ?""",
                [after, *args, *kargs, limit + 1],
            )
        return self._page(rows, limit, context)

    def domain_instances(self, name, limit=20, *, cursor=None):
        return self.domain_page(name, limit, cursor=cursor, node_kind="INSTANCE")

    def instances_page(self, type_uid, limit=20, *, recursive=True, cursor=None):
        if type_uid.startswith("fineatlas-domain:") or self.domain(type_uid):
            return self.domain_instances(type_uid, limit, cursor=cursor)
        self._limit(limit)
        if limit > 10000:
            raise ValueError("Page limit must be at most 10000")
        own = self._basic(type_uid)
        context = self._page_context("instances", [type_uid, recursive])
        after = self._after(cursor, context)
        if not own:
            return {
                "items": [],
                "next_cursor": None,
                "has_more": False,
                "relation_view": self.relation_view,
                "database_revision": self._revision,
            }
        type_peers = [
            self._basic(r[0])
            for r in self.con.execute(
                "SELECT uid FROM nodes WHERE component_id=? AND visibility='ACTIVE'",
                (own["component_id"],),
            )
        ]
        # A native selector may refer to a grounded identity whose independently
        # admitted type representation comes from another source. This does not
        # change the selector UID's own role or training admission.
        if not self._node_admitted(own) or not any(
            self._node_admitted(peer) and self._role_allowed(peer["node_kind"])
            for peer in type_peers
        ):
            return {
                "items": [],
                "next_cursor": None,
                "has_more": False,
                "relation_view": self.relation_view,
                "status": "VIEW_NOT_APPLICABLE",
                "database_revision": self._revision,
            }
        # Versioned root witnesses avoid reconstructing a millions-node scope
        # when asking for the first few instances of the global root.
        if (
            recursive
            and type_uid == self.metadata["root_uid"]
            and "view_paths" in self._tables
        ):
            rows = self.con.execute(
                f"""WITH uids AS (
                SELECT DISTINCT r.subject_uid FROM entity_relations r CROSS JOIN nodes i
                WHERE r.status='ACTIVE' AND r.relation='INSTANCE_OF' AND r.subject_uid>?
                AND i.uid=r.subject_uid AND {self._admission_sql("i")} AND {self._kind_sql("i")}='INSTANCE'
                {self._selected_root_sql("i")}
                AND EXISTS(SELECT 1 FROM view_paths vp WHERE vp.view=? AND vp.component_id=i.component_id)
                ORDER BY r.subject_uid LIMIT ?)
                SELECT n.* FROM uids u CROSS JOIN nodes n WHERE n.uid=u.subject_uid ORDER BY n.uid""",
                (after, self.relation_view, limit + 1),
            )
            return self._page(rows, limit, context)
        if recursive:
            class_roles = ",".join(
                "'" + r + "'"
                for r in sorted(
                    CLASS_ROLES
                    | (
                        {"BIOLOGICAL_VARIANT"}
                        if self.relation_view in ("taxonomy", "unified")
                        else set()
                    )
                )
            )
            typed_policy = " OR ".join(
                f"({self._kind_sql('ch')}='{role}' AND r.relation IN ("
                + ",".join("'" + v + "'" for v in rels)
                + "))"
                for role, rels in TYPED_TERMINALS.items()
                if role in CLASS_ROLES
            )
            typed_scope = (
                (
                    f""" UNION SELECT ch.component_id FROM scopes s CROSS JOIN nodes p CROSS JOIN entity_relations r
                CROSS JOIN nodes ch WHERE p.component_id=s.id AND r.object_uid=p.uid
                AND r.status='ACTIVE' AND ch.uid=r.subject_uid AND {self._admission_sql("ch")}
                AND ({typed_policy})"""
                )
                if "entity_relations" in self._tables
                else ""
            )
            scopes = f"""WITH RECURSIVE scopes(id) AS (SELECT component_id FROM nodes WHERE uid=? UNION
                SELECT ch.component_id FROM scopes s CROSS JOIN nodes p CROSS JOIN edges e
                CROSS JOIN nodes ch WHERE p.component_id=s.id AND e.parent_uid=p.uid
                AND {self._relation_sql()} AND ch.uid=e.child_uid AND {self._admission_sql("ch")}
                AND {self._kind_sql("ch")} IN ({class_roles}){typed_scope})"""
        else:
            scopes = "WITH scopes(id) AS (SELECT component_id FROM nodes WHERE uid=?)"
        rows = self.con.execute(
            scopes
            + f""" SELECT DISTINCT n.* FROM scopes s CROSS JOIN nodes t
            CROSS JOIN entity_relations r CROSS JOIN nodes n
            WHERE t.component_id=s.id AND r.object_uid=t.uid AND r.relation='INSTANCE_OF'
            AND r.status='ACTIVE' AND n.uid=r.subject_uid AND {self._admission_sql("n")}
            AND {self._kind_sql("n")}='INSTANCE' AND n.uid>? {self._selected_root_sql("n")} ORDER BY n.uid LIMIT ?""",
            (type_uid, after, limit + 1),
        )
        return self._page(rows, limit, context)

    def instances(self, type_uid, limit=20, recursive=True):
        page = self.instances_page(type_uid, limit, recursive=recursive)
        return ResultList(page["items"], has_more=page["has_more"])

    def neighbors(self, uid, direction="children", limit=20, structural_only=True):
        if uid.startswith("fineatlas-domain:"):
            return self.domain_children(uid, limit) if direction == "children" else []
        if direction == "parents" and structural_only:
            out = []
            seen = set()
            for parent, edge in self._parents(uid):
                if parent in seen:
                    continue
                seen.add(parent)
                item = self.node(parent)
                item["edge"] = edge
                out.append(item)
            return ResultList(out[:limit], has_more=len(out) > limit)
        # Explicit UID navigation admits valid local branches even if the global
        # root is disconnected; membership/root status is returned separately.
        own = self._basic(uid)
        if not self._node_admitted(own):
            return []
        if direction not in ("children", "parents"):
            raise ValueError("direction must be children or parents")
        endpoint, target = (
            ("parent_uid", "child_uid")
            if direction == "children"
            else ("child_uid", "parent_uid")
        )
        status = (
            self._relation_sql()
            if structural_only
            else "e.status IN ('ACTIVE','TYPED_ACTIVE','AUXILIARY','REVIEW')"
        )
        values = {}
        root_scope = self._selected_root_sql("n") if direction == "children" else ""
        for row in self.con.execute(
            f"""SELECT e.* FROM nodes a CROSS JOIN edges e CROSS JOIN nodes n
            WHERE a.component_id=? AND e.{endpoint}=a.uid AND n.uid=e.{target}
            AND a.visibility='ACTIVE' AND n.visibility='ACTIVE' AND {status} {root_scope}
            ORDER BY e.{target},e.id""",
            (own["component_id"],),
        ):
            target_uid = row[target]
            target_node = self._basic(target_uid)
            if structural_only and (
                not self._role_allowed(own["node_kind"])
                or not self._node_admitted(self._basic(row["child_uid"]))
                or not self._node_admitted(self._basic(row["parent_uid"]))
                or not self._role_allowed(self._basic(row["child_uid"])["node_kind"])
                or not self._role_allowed(self._basic(row["parent_uid"])["node_kind"])
                or not self._node_admitted(target_node)
                or not (
                    self._role_allowed(target_node["node_kind"])
                    or (
                        self.relation_view == "membership"
                        and target_node["node_kind"] == "DATASET_CATEGORY"
                    )
                )
            ):
                continue
            if target_uid not in values:
                item = self.node(target_uid)
                item["edge"] = self._edge(row)
                item["edge_evidence"] = [self._edge(row)]
                values[target_uid] = item
                if len(values) > limit:
                    break
            else:
                values[target_uid]["edge_evidence"].append(self._edge(row))
        return ResultList(list(values.values())[:limit], has_more=len(values) > limit)

    def _ancestor_map(self, uid, max_nodes=100000):
        own = self._basic(uid)
        if not own:
            raise ValueError("Unknown node UID: " + uid)
        if not self._node_admitted(own) or not (
            self._role_allowed(own["node_kind"]) or own["node_kind"] in TYPED_TERMINALS
        ):
            raise ValueError("Node is not admitted to this ancestor view: " + uid)
        queue = deque([uid])
        found = {own["component_id"]: (uid, 0)}
        while queue:
            current = queue.popleft()
            distance = found[self._basic(current)["component_id"]][1]
            for parent, _ in self._parents(current):
                comp = self._basic(parent)["component_id"]
                if comp not in found:
                    found[comp] = (parent, distance + 1)
                    queue.append(parent)
            if len(found) > max_nodes:
                raise QueryLimitError("Ancestor query exceeded max_nodes")
        return found

    def relation_reward_index(self, dataset, *, policy=None, excluded_labels=None,
                              blocked_ancestors=(), coarse_roots=(), review_policy=None,
                              max_nodes=10000, source_scope=None, requirement=None):
        """Prepare a frozen, typed, bounded batch index for text tree rewards.

        Applicable results are structurally screened, not scientific validation.
        Use a reviewed label exclusion policy alongside the frozen DB revision.
        """
        from .rewards import RelationRewardIndex
        config=self.metadata.get('unified_reward_policies',{}).get(dataset,{}) if self.relation_view=='unified' else {}
        if review_policy is None and config and policy is None and not coarse_roots and source_scope is None and requirement is None:
            policy=config.get('policy');coarse_roots=config.get('coarse_roots',())
            source_scope=config.get('source_scope');requirement=config.get('requirement')
        return RelationRewardIndex(self, dataset, policy=policy,
                                   excluded_labels=excluded_labels,
                                   blocked_ancestors=blocked_ancestors,
                                   coarse_roots=coarse_roots, review_policy=review_policy,
                                   max_nodes=max_nodes, source_scope=source_scope,
                                   requirement=requirement)

    def export_training(self, dataset, directory, *, max_nodes=10000):
        """Export every original label and pair with an explicit reward mask.

        Invalid hierarchy terms do not remove labels or disable label accuracy.
        A common-ancestor distance is a typed navigation metric, not a validated
        measure of visual similarity or calibrated classification severity.
        """
        from collections import Counter
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        index=self.relation_reward_index(dataset,max_nodes=max_nodes)
        labels=self.task_labels(dataset,requirement=index.requirement)
        with (directory/'labels.jsonl').open('w',encoding='utf-8') as stream:
            for label in labels:
                checked=dict(index.labels[str(label['class_id'])])
                stream.write(json.dumps({'target':label,'path':self.task_path(dataset,label['class_id'],index=index),
                    'category_reward_applicable':True,'hierarchy_endpoint_applicable':checked['reason'] is None,
                    'hierarchy_endpoint_reason':checked['reason'],'snapshot_revision':self._revision,
                    'relation_view':self.relation_view},ensure_ascii=False)+'\n')
        counts=Counter()
        with (directory/'pairs.jsonl').open('w',encoding='utf-8') as stream:
            for pair in index.pairs():
                counts[pair['status']]+=1
                stream.write(json.dumps(pair,ensure_ascii=False)+'\n')
        result={'dataset':dataset,'labels':len(labels),'pairs':sum(counts.values()),
                'pair_statuses':dict(counts),'database_revision':self._revision,
                'relation_view':self.relation_view,'policy':index.policy,
                'source_scope':index.source_scope,'requirement':index.requirement,
                'nonapplicable_distance':None,'category_reward_preserved':True,
                'metric':'minimum_upward_informative_lca_arc_sum',
                'semantic_scope':'Retained evidence-backed relation policy and conservative endpoint screening; annotation/visual reward calibration is not certified'}
        (directory/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        return result

    def task_path(self,dataset,class_id,*,index=None,max_depth=256,max_nodes=10000):
        """Show the same typed/source lineage selected by the frozen task policy.

        A valid navigation path and an eligible training endpoint are distinct
        fields. Caller needs dataset/class ID, never native UID conventions.
        """
        target=self.target(dataset,class_id)
        if not target:return {'status':'UNKNOWN_LABEL','dataset':dataset,'class_id':str(class_id),'path':[]}
        index=index or self.relation_reward_index(dataset,max_nodes=max_nodes)
        from .rewards import POLICIES
        own=self._basic(target['target_uid']);policy=POLICIES[index.policy]
        label=index.labels[str(class_id)]
        base={'uid':target['target_uid'],'dataset':dataset,'class_id':str(class_id),
              'relation_view':self.relation_view,'policy':index.policy,'source_scope':index.source_scope,
              'training_endpoint_applicable':label['reason'] is None,
              'training_endpoint_reason':label['reason'],'root_uid':self.root_uid,'path':[]}
        if not self._node_admitted(own):return {**base,'status':'NOT_ADMITTED'}
        if own['node_kind'] not in policy['roles']:return {**base,'status':'ROLE_NOT_APPLICABLE'}
        goals=set(index._floor_components) or {self._basic(self.root_uid)['component_id']}
        queue=deque([(own['uid'],[],0)]);seen=set();depth_cut=False
        while queue:
            current,upward,depth=queue.popleft();comp=self._basic(current)['component_id']
            if comp in seen:continue
            seen.add(comp)
            if len(seen)>max_nodes:return {**base,'status':'QUERY_LIMIT'}
            if comp in goals:
                prefix=self.path_result(current,max_depth=max_depth-depth)
                if prefix['status'] not in ('ROOT','CONNECTED'):return {**base,'status':prefix['status']}
                return {**base,'status':'CONNECTED','path':prefix['path']+list(reversed(upward)),
                        'classification_arc_count':depth+prefix.get('distance',0),
                        'identity_steps_cost':0}
            if depth>=max_depth:depth_cut=True;continue
            for parent,edge in self._parents(current):
                child=self._basic(edge['child_uid']);pn=self._basic(parent)
                if edge['relation'] not in policy['relations'] or child['node_kind'] not in policy['roles'] or pn['node_kind'] not in policy['roles']:continue
                if index.source_scope is not None and not(child['source']==index.source_scope and
                    (pn['source']==index.source_scope or pn['component_id'] in goals)):continue
                aligned=self._identity_steps(current,edge['child_uid'])
                queue.append((parent,upward+aligned+[self._step_for(edge['child_uid'],parent,edge)],depth+1))
        return {**base,'status':'DEPTH_LIMIT' if depth_cut else 'NO_POLICY_PATH'}

    def ancestors(self, uid, limit=1000, *, include_self=False, max_nodes=100000):
        self._limit(limit)
        found = self._ancestor_map(uid, max_nodes)
        own = self._basic(uid)["component_id"]
        rows = sorted(
            ((u, d, c) for c, (u, d) in found.items() if include_self or c != own),
            key=lambda x: (x[1], x[0]),
        )
        items = [
            {**self.node(u), "distance": d, "relation_view": self.relation_view}
            for u, d, c in rows[:limit]
        ]
        return ResultList(items, has_more=len(rows) > limit)

    def ancestors_result(self, uid, limit=1000, *, include_self=False, max_nodes=100000):
        """Structured ancestor query; invalid endpoints never receive fake paths."""
        base={'uid':uid,'relation_view':self.relation_view,'root_uid':self.root_uid}
        status=self.path_result(uid)['status']
        if status not in ('CONNECTED','ROOT','UNREACHABLE'):
            return {**base,'status':status,'items':[],'has_more':False}
        try:
            items=self.ancestors(uid,limit,include_self=include_self,max_nodes=max_nodes)
        except QueryLimitError as error:
            return {**base,'status':'QUERY_LIMIT','reason':str(error),'items':[],'has_more':False}
        except ValueError as error:
            return {**base,'status':'VIEW_NOT_APPLICABLE','reason':str(error),'items':[],'has_more':False}
        return {**base,'status':status,'items':list(items),'has_more':items.has_more}

    def source_hierarchy(self, uid, *, direction='parents', limit=100):
        """Inspect direct retained source assertions without identity expansion.

        This native-record view includes disposition and does not assert that
        every original declaration is eligible for the unified classification.
        """
        self._limit(limit)
        if direction not in ('parents','children'):
            return {'status':'UNSUPPORTED_DIRECTION','items':[]}
        own=self._basic(uid)
        if own is None:return {'status':'NOT_FOUND','uid':uid,'items':[]}
        endpoint='child_uid' if direction=='parents' else 'parent_uid'
        other='parent_uid' if direction=='parents' else 'child_uid'
        rows=self.con.execute(f'''SELECT e.* FROM edges e JOIN nodes n ON n.uid=e.{other}
            WHERE e.{endpoint}=? AND n.source=? ORDER BY e.id LIMIT ?''',
            (uid,own['source'],limit+1)).fetchall()
        return {'status':'SOURCE_RECORD_VIEW','uid':uid,'source':own['source'],
                'direction':direction,'items':[dict(r) for r in rows[:limit]],
                'has_more':len(rows)>limit,'identity_expanded':False,
                'classification_admission_is_separate':True}

    def _typed_relation_query(self, left, right, policy, max_nodes):
        from .rewards import RelationRewardIndex,POLICIES
        if policy not in POLICIES:
            return {'status':'UNSUPPORTED_POLICY','applicable':False,'distance':None,'lcas':[],
                    'policy':policy,'relation_view':self.relation_view,'allowed_policies':sorted(POLICIES)}
        if not all(isinstance(u,str) and u for u in (left,right)):
            return {'status':'INVALID_UID','applicable':False,'distance':None,'lcas':[],
                    'relation_view':self.relation_view}
        blocked=[]
        if 'unified_domain_rules' in self._tables:
            blocked=[r[0] for r in self.con.execute('SELECT DISTINCT wordnet_anchor_uid FROM unified_domain_rules')]
        index=RelationRewardIndex(self,'uid',uids=[left,right],policy=policy,
                                  coarse_roots=blocked,max_nodes=max_nodes)
        result=index.query(left,right)
        result['training_reward']=False
        result['reward_note']='Generic UID relations are not calibrated classification penalties; use a frozen dataset reward index'
        return result

    def lca(self, left, right, *, max_nodes=100000, policy=None):
        if self.relation_view=='unified' or policy is not None:
            result=self._typed_relation_query(left,right,policy or 'classification',max_nodes)
            return {**result,'items':result['lcas'],
                    'status':'CONNECTED' if result['applicable'] else
                             'COMMON_ANCESTOR_INFORMATION_INSUFFICIENT' if result['status']=='COARSE_COMMON_ANCESTOR_ONLY' else result['status'],
                    'definition':'All lowest common identity-group ancestors under the explicit role/relation policy; identity costs zero; multiple LCAs retained'}
        a = self._ancestor_map(left, max_nodes)
        b = self._ancestor_map(right, max_nodes)
        common = set(a) & set(b)
        nonlowest = set()
        for comp in common:
            for parent, _ in self._parents(a[comp][0]):
                pc = self._basic(parent)["component_id"]
                if pc in common and pc != comp:
                    nonlowest.add(pc)
        candidates = sorted(common - nonlowest, key=lambda c: a[c][0])
        return {
            "status": "CONNECTED" if candidates else "NO_COMMON_ANCESTOR",
            "items": [
                {
                    **self.node(a[c][0]),
                    "left_distance": a[c][1],
                    "right_distance": b[c][1],
                }
                for c in candidates
            ],
            "relation_view": self.relation_view,
            "definition": "All lowest common identity-group ancestors in the selected directed DAG; multiple answers are retained",
        }

    def _descendants_one(self, uid):
        own = self._basic(uid)
        if not self._node_admitted(own) or not self._role_allowed(own["node_kind"]):
            return
        candidates = {
            r[0]
            for r in self.con.execute(
                f"SELECT e.child_uid FROM nodes n CROSS JOIN edges e WHERE n.component_id=? AND e.parent_uid=n.uid AND {self._relation_sql()}",
                (own["component_id"],),
            )
        }
        if "entity_relations" in self._tables:
            candidates.update(
                r[0]
                for r in self.con.execute(
                    "SELECT r.subject_uid FROM nodes n CROSS JOIN entity_relations r WHERE n.component_id=? AND r.object_uid=n.uid AND r.status='ACTIVE'",
                    (own["component_id"],),
                )
            )
        for child_uid in sorted(candidates):
            child = self._basic(child_uid)
            if not self._node_admitted(child):
                continue
            if any(
                self._basic(parent)["component_id"] == own["component_id"]
                for parent, edge in self._parents(child_uid)
            ):
                yield child_uid

    def distance(self, left, right, *, direction=None, max_nodes=100000, policy=None):
        if self.relation_view=='unified' or policy is not None:
            if direction not in (None,'common_ancestor'):
                return {'status':'UNSUPPORTED_DIRECTION','distance':None,'applicable':False,
                        'relation_view':self.relation_view,
                        'reason':'Unified comparison uses upward paths through legal LCAs, not an undirected union of relation types'}
            return self._typed_relation_query(left,right,policy or 'classification',max_nodes)
        direction=direction or 'undirected'
        if direction not in ("undirected", "upward", "downward"):
            raise ValueError("Invalid distance direction")
        a = self._basic(left)
        b = self._basic(right)
        if not a or not b:
            raise ValueError("Unknown distance endpoint UID")
        base = {
            "direction": direction,
            "relation_view": self.relation_view,
            "definition": "Shortest accepted hierarchy/role-compatible terminal arc count; grounded identity steps cost zero",
        }
        if (
            not self._node_admitted(a)
            or not self._node_admitted(b)
            or not (
                self._role_allowed(a["node_kind"]) or a["node_kind"] in TYPED_TERMINALS
            )
            or not (
                self._role_allowed(b["node_kind"]) or b["node_kind"] in TYPED_TERMINALS
            )
        ):
            return {**base, "status": "VIEW_NOT_APPLICABLE", "distance": None}
        if a["component_id"] == b["component_id"]:
            return {**base, "status": "CONNECTED", "distance": 0}

        def adjacent(uid, forward):
            flow = direction
            if not forward:
                flow = {
                    "upward": "downward",
                    "downward": "upward",
                    "undirected": "undirected",
                }[flow]
            if flow in ("upward", "undirected"):
                yield from (p for p, e in self._parents(uid))
            if flow in ("downward", "undirected"):
                yield from self._descendants_one(uid)

        fronts = [{a["component_id"]: left}, {b["component_id"]: right}]
        distances = [{a["component_id"]: 0}, {b["component_id"]: 0}]
        while all(fronts):
            side = 0 if len(fronts[0]) <= len(fronts[1]) else 1
            other = 1 - side
            new = {}
            best = None
            for comp, uid in fronts[side].items():
                d = distances[side][comp] + 1
                for target in adjacent(uid, side == 0):
                    tc = self._basic(target)["component_id"]
                    if tc in distances[side]:
                        continue
                    distances[side][tc] = d
                    new[tc] = target
                    if tc in distances[other]:
                        best = min(
                            best if best is not None else max_nodes,
                            d + distances[other][tc],
                        )
                    if sum(map(len, distances)) > max_nodes:
                        raise QueryLimitError(
                            "Distance exceeded max_nodes; no unreachable result was fabricated"
                        )
            if best is not None:
                return {**base, "status": "CONNECTED", "distance": best}
            fronts[side] = new
        return {**base, "status": "UNREACHABLE", "distance": None}

    def eligibility(self, uid, requirement="hierarchy", *, identity_verified=None):
        if requirement not in (
            "identity",
            "native_label",
            "hierarchy",
            "strict_classification",
            "species",
            "model",
            "model_design",
            "configuration",
            "instance",
        ):
            raise ValueError("Unknown task requirement")
        n = self.node(uid)
        if not n:
            return {
                "uid": uid,
                "usable": False,
                "reason": "NOT_FOUND",
                "identity_verified": identity_verified,
                "relation_view": self.relation_view,
            }
        status = self.connection_status(uid)
        role = n["node_kind"]
        rank = n.get("native_rank")
        normalized_rank = n.get("normalized_rank")
        role_ok = {
            "identity": True,
            "native_label": True,
            "hierarchy": role not in ("UNKNOWN", "ORGANIZATION")
            and (role != "BIOLOGICAL_VARIANT" or self.relation_view in ("taxonomy", "unified")),
            "strict_classification": role in CLASS_ROLES,
            "model_design": role in ("MODEL", "MODEL_FAMILY"),
            "species": role == "CLASS"
            and normalized_rank == "species"
            and n.get("rank_status") != "CONFLICT_REVIEW",
            "model": role == "MODEL",
            "configuration": role == "CONFIGURATION",
            "instance": role == "INSTANCE",
        }[requirement]
        root_ok = status.get("root_reachable", False)
        if requirement == "strict_classification":
            root_ok = (
                status.get("classification_root_reachable", False)
                and self.relation_view == "strict"
            )
        usable = (
            n["visibility"] == "ACTIVE"
            and (
                requirement in ("identity", "native_label")
                or status.get("view_admitted", False)
            )
            and role_ok
            and (requirement in ("identity", "native_label") or root_ok)
            and identity_verified is not False
        )
        reason = (
            "PASS"
            if usable
            else "IDENTITY_NOT_VERIFIED"
            if identity_verified is False
            else "ROLE_NOT_APPLICABLE"
            if not role_ok
            else "REQUIRED_ROOT_UNREACHABLE"
            if not root_ok and status["status"] in ("CONNECTED", "ROOT")
            else status["status"]
        )
        return {
            "uid": uid,
            "requirement": requirement,
            "usable": usable,
            "reason": reason,
            "identity_verified": identity_verified,
            "normalized_role": role,
            "native_rank": rank,
            "normalized_rank": normalized_rank,
            "rank_status": n.get("rank_status"),
            "view_admitted": status.get("view_admitted", False),
            "root_reachable": root_ok,
            "classification_root_reachable": status.get(
                "classification_root_reachable", False
            ),
            "typed_root_reachable": status.get("typed_root_reachable", False),
            "relation_view": self.relation_view,
            "root_uid": self.root_uid,
        }

    def target(self, dataset, class_id):
        result = super().target(dataset, class_id)
        if result:
            verified = result["decision_status"] in ("VERIFIED", "VERIFIED_ATTRIBUTE")
            result["identity_verified"] = verified
            result['stored_identity_claim_verified']=verified
            if 'dataset_mapping_checks' in self._tables:
                check=self.con.execute('SELECT status,reason,proof FROM dataset_mapping_checks WHERE dataset=? AND class_id=?',
                                       (dataset,str(class_id))).fetchone()
                result['mapping_review']=dict(check) if check else None
                if self.relation_view=='unified' and check and check['status']=='ANNOTATION_SCOPE_REVIEW':
                    verified=False
                    result['identity_verified']=False
            target_node = self._basic(result["target_uid"])
            if not target_node or target_node.get("visibility") != "ACTIVE" or target_node.get("node_kind") == "UNKNOWN":
                verified = False
                result["identity_verified"] = False
                result["world_identity_review"] = {
                    "reason": "TARGET_SCOPE_OR_ROLE_NOT_CONFIRMED",
                    "native_label_retained": True,
                    "stored_identity_claim_verified": result["stored_identity_claim_verified"],
                }
            result["mapping_verified"] = result["decision_status"].startswith(
                "VERIFIED"
            )
            result["native_label_verified"] = True
            result["native_label_admission"] = {
                "uid": result["target_uid"],
                "dataset": result["dataset"],
                "class_id": result["class_id"],
                "requirement": "native_label",
                "usable": True,
                "native_label_verified": True,
                "identity_verified": verified,
                "reason": "SOURCE_NATIVE_DATASET_LABEL; world-type mapping is assessed separately",
                "relation_view": self.relation_view,
                "root_uid": self.root_uid,
            }
            result["mapping_kind"] = (
                "EXACT_IDENTITY"
                if verified
                else "SOURCE_TYPED_MAPPING"
                if result["mapping_verified"]
                else "NATIVE_LABEL_ONLY"
            )
            if result.get('mapping_review') and result['mapping_review']['status']=='ANNOTATION_SCOPE_REVIEW':
                result['mapping_kind']='ANNOTATION_SCOPE_REVIEW'
            result["task_admission"] = self.eligibility(
                result["target_uid"], identity_verified=result["mapping_verified"]
            )
            result["task_admission"].update(
                identity_verified=verified,
                mapping_verified=result["mapping_verified"],
                admission_scope="Typed mapping and legal navigation; exact world identity and relation reward are separate",
            )
        return result

    def task_labels(self, dataset, requirement="hierarchy", *, usable_only=False):
        values = []
        for row in self.con.execute(
            "SELECT class_id FROM dataset_targets WHERE dataset=? ORDER BY length(class_id),class_id",
            (dataset,),
        ):
            target = self.target(dataset, row[0])
            target["task_admission"] = dict(target["native_label_admission"]) if requirement == "native_label" else self.eligibility(
                target["target_uid"],
                requirement,
                identity_verified=True
                if requirement == "native_label"
                else target["identity_verified"]
                if requirement
                in (
                    "identity",
                    "species",
                    "model",
                    "configuration",
                    "strict_classification",
                )
                else target["mapping_verified"],
            )
            if requirement == "hierarchy":
                target["task_admission"].update(
                    identity_verified=target["identity_verified"],
                    mapping_verified=target["mapping_verified"],
                    admission_scope="Typed mapping and legal navigation; exact world identity and relation reward are separate",
                )
            if not usable_only or target["task_admission"]["usable"]:
                values.append(target)
        return values

    def export_domain(
        self, name, path, *, page_size=1000, node_kind=None, requirement="hierarchy"
    ):
        path = Path(path)
        count = 0
        cursor = None
        with path.open("w", encoding="utf-8") as output:
            while True:
                page = self.domain_page(
                    name, page_size, cursor=cursor, node_kind=node_kind
                )
                for node in page["items"]:
                    uid = node["uid"]
                    parents = [e for p, e in self._parents(uid)]
                    output.write(
                        json.dumps(
                            {
                                "node": node,
                                "parents": parents,
                                "relation_view": self.relation_view,
                                "domain": self.domain(name)["domain"],
                                "task_admission": self.eligibility(uid, requirement),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    count += 1
                cursor = page["next_cursor"]
                if not cursor:
                    break
        return {
            "path": str(path),
            "nodes": count,
            "relation_view": self.relation_view,
            "domain": self.domain(name)["domain"],
            "database_revision": self._revision,
        }
