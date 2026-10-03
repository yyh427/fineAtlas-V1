from __future__ import annotations

import json
import re
import sqlite3
from collections import deque
from pathlib import Path


def norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def tokens(text: str) -> list[str]:
    return [x for x in norm(text).split() if len(x) > 2]


class DynamicIndex:
    """Query-time retrieval over an isolated YAGO or FineAtlas SQLite index."""

    def __init__(self, path: str | Path, kind: str):
        self.path, self.kind = str(path), kind
        self.con = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro&immutable=1", uri=True)
        self.has_fts = bool(
            kind == "yago"
            and self.con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='nodes_fts'"
            ).fetchone()
        )

    def lookup(self, query: str, limit: int = 12, domain: str | None = None) -> list[dict]:
        terms = tokens(query)[:6]
        if not terms: return []
        if self.kind == "yago" and self.has_fts:
            # Prefer documents containing every visual-concept term.  If that
            # is too restrictive, use a bounded OR query.  FTS ranking avoids
            # the old table-order bias from ``LIKE ... LIMIT``.
            expressions = [" AND ".join(f'"{term}"' for term in terms)]
            if len(terms) > 1:
                expressions.append(" OR ".join(f'"{term}"' for term in terms))
            gathered: dict[str, dict] = {}
            for expression in expressions:
                rows = self.con.execute(
                    """
                    SELECT n.uid,n.label,n.aliases,n.description,bm25(nodes_fts)
                    FROM nodes_fts JOIN nodes n ON n.rowid=nodes_fts.rowid
                    WHERE nodes_fts MATCH ? ORDER BY bm25(nodes_fts) LIMIT ?
                    """,
                    (expression, limit * 3),
                ).fetchall()
                for uid, label, aliases, description, rank_score in rows:
                    gathered.setdefault(
                        uid,
                        {
                            "uid": uid,
                            "label": label,
                            "aliases": aliases,
                            "description": description,
                            "domains": "",
                            "data": {},
                            "match_score": -float(rank_score),
                        },
                    )
                if len(gathered) >= limit:
                    break
            return list(gathered.values())[:limit]
        clauses, args = [], []
        for term in terms:
            if self.kind == "fineatlas":
                clauses.append("(lower(label) LIKE ? OR lower(description) LIKE ?)")
                args.extend([f"%{term}%"] * 2)
            else:
                clauses.append("(lower(label) LIKE ? OR lower(aliases) LIKE ? OR lower(description) LIKE ?)")
                args.extend([f"%{term}%"] * 3)
        if self.kind == "fineatlas" and domain:
            clauses.append("domains LIKE ?"); args.append(f'%"{domain}"%')
        select = "uid,label,'',description,domains,'{}'" if self.kind == "fineatlas" else "uid,label,aliases,description,'','{}'"
        sql = "SELECT " + select + " FROM nodes WHERE " + " OR ".join(clauses) + " LIMIT ?"
        args.append(limit)
        rows = []
        for uid, label, aliases, description, domains, data in self.con.execute(sql, args):
            score = sum(norm(term) in norm(str(label) + " " + str(aliases) + " " + str(description)) for term in terms)
            rows.append({"uid": uid, "label": label, "aliases": aliases, "description": description, "domains": domains, "data": json.loads(data) if data else {}, "match_score": score})
        rows.sort(key=lambda x: (-x["match_score"], norm(x["label"]), x["uid"]))
        return rows[:limit]

    def neighbors(self, uid: str, direction: str = "children", limit: int = 24, roles: tuple[str, ...] | None = None) -> list[dict]:
        if direction not in {"children", "parents"}: raise ValueError(direction)
        column = "parent_uid" if direction == "children" else "child_uid"
        target = "child_uid" if direction == "children" else "parent_uid"
        args: list[object] = [uid]
        role_sql = ""
        if roles:
            role_sql = " AND e.navigation_role IN (" + ",".join("?" for _ in roles) + ")"
            args.extend(roles)
        args.append(limit)
        node_select = "n.uid,n.label,'',n.description,n.domains,'{}'" if self.kind == "fineatlas" else "n.uid,n.label,n.aliases,n.description,'','{}'"
        edge_select = "e.child_uid,e.parent_uid,e.relation,e.layer,e.role,e.navigation_role,e.facet_family,e.classification_basis,e.child_facet_span" if self.kind == "fineatlas" else "e.child_uid,e.parent_uid,e.relation,'','','','','',''"
        rows = self.con.execute(f"""
          SELECT {edge_select},
                 {node_select}
          FROM edges e JOIN nodes n ON n.uid=e.{target}
          WHERE e.{column}=? {role_sql} LIMIT ?
        """, args).fetchall()
        out = []
        for row in rows:
            child, parent, relation, layer, role, nav, facet = row[:7]
            edge_data = {"child_uid": child, "parent_uid": parent, "relation": relation, "layer": layer, "role": role, "navigation_role": nav, "facet_family": facet}
            if self.kind == "fineatlas": edge_data.update({"classification_basis": row[7], "child_facet_span": row[8]})
            uid2, label, aliases, desc, domains = row[-6:-1]
            out.append({"uid": uid2, "label": label, "aliases": aliases, "description": desc, "domains": domains, "edge": edge_data, "data": {}})
        return out

    def exact_label_uids(self, label: str, limit: int = 8) -> list[str]:
        rows = self.con.execute("SELECT uid FROM nodes WHERE lower(label)=? LIMIT ?", (norm(label), limit)).fetchall()
        return [x[0] for x in rows]

    def descendant_distance(self, anchor_uids: list[str], target_uids: list[str], max_depth: int = 6, beam: int = 80) -> int | None:
        """Bounded post-hoc reachability; never used by inference."""
        targets=set(target_uids); frontier=set(anchor_uids); seen=set(frontier)
        if frontier & targets: return 0
        for depth in range(1,max_depth+1):
            nxt=[]
            for uid in sorted(frontier):
                nxt.extend(x["uid"] for x in self.neighbors(uid,"children",beam,("PRIMARY_BACKBONE","PRIMARY_IS_A","PRIMARY_TAXONOMY","PRIMARY_TYPED_REFINEMENT")))
            frontier=set(nxt[:beam])-seen; seen|=frontier
            if frontier & targets:return depth
            if not frontier:break
        return None

    def close(self): self.con.close()


class V4DynamicIndex:
    """Read-only overlay over V3, source-native V4 DAGs, and equivalence bridges.

    Equivalence is traversed by the query engine and is deliberately not copied
    into the hierarchy as IS-A.  This preserves acyclicity and provenance.
    """

    def __init__(self, config_path: str | Path):
        self.kind = "fineatlas_v4"
        self.config_path = Path(config_path).resolve()
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        # ``uri=True`` is required for SQLite to interpret the read-only
        # ``file:...?mode=ro&immutable=1`` names used by ATTACH.  Without it, some Python
        # builds treat the full URI as a literal path and fail to open V4.
        self.con = sqlite3.connect(":memory:", uri=True)
        for schema, key in (
            ("v3", "v3_graph"),
            ("ext", "extension"),
            ("aln", "alignment"),
            ("lex", "lexical_sidecar"),
        ):
            uri = f"file:{Path(self.config[key]).resolve()}?mode=ro&immutable=1"
            self.con.execute(f"ATTACH DATABASE ? AS {schema}", (uri,))
        col = self.config.get("col_vernacular_sidecar")
        if col and Path(col).exists():
            self.con.execute(
                "ATTACH DATABASE ? AS col",
                (f"file:{Path(col).resolve()}?mode=ro&immutable=1",),
            )
            self.has_col = True
        else:
            self.has_col = False
        source_names = self.config.get("source_name_variants_sidecar")
        if source_names:
            name_path = Path(source_names)
            if not name_path.exists():
                raise FileNotFoundError(name_path)
            self.con.execute("ATTACH DATABASE ? AS names",
                (f"file:{name_path.resolve()}?mode=ro&immutable=1",))
            self.has_source_names = True
        else:
            self.has_source_names = False
        self.con.execute("PRAGMA query_only=ON")
        self.roots = self.config.get("roots", {})

    @staticmethod
    def _source_graph(uid: str) -> str:
        return "v3" if uid.startswith(("wikidata:", "wordnet31:")) else "ext"

    def _node(self, uid: str, edge: dict | None = None) -> dict:
        graph = self._source_graph(uid)
        if graph == "v3":
            row = self.con.execute(
                "SELECT label,data FROM v3.nodes WHERE uid=?", (uid,)
            ).fetchone()
            if not row:
                return {}
            label, raw_data = row
            try:
                data = json.loads(raw_data or "{}")
            except (TypeError, json.JSONDecodeError):
                data = {}
            description = str(data.get("description") or data.get("gloss") or "")
            domains = data.get("domains")
            if not isinstance(domains, list):
                # The normalized lexical sidecar carries the domain annotation
                # for old V3 nodes whose compact node JSON predates it.
                domain_rows = self.con.execute(
                    "SELECT domains FROM lex.v3_aliases WHERE uid=? LIMIT 8", (uid,)
                ).fetchall()
                parsed_domains: set[str] = set()
                for (value,) in domain_rows:
                    try:
                        loaded = json.loads(value or "[]")
                    except (TypeError, json.JSONDecodeError):
                        loaded = []
                    if isinstance(loaded, list):
                        parsed_domains.update(str(item) for item in loaded if item)
                domains = sorted(parsed_domains)
            domains = json.dumps(domains or [])
            rank = str(data.get("rank") or data.get("taxonomic_rank") or "")
            source = str(data.get("source") or uid.split(":", 1)[0])
        else:
            row = self.con.execute(
                "SELECT label,domain,source,rank,data FROM ext.nodes WHERE uid=?", (uid,)
            ).fetchone()
            if not row:
                return {}
            label, domain, source, rank, raw_data = row
            try:
                data = json.loads(raw_data or "{}")
            except (TypeError, json.JSONDecodeError):
                data = {}
            description = str(data.get("description") or "")
            domains = json.dumps([domain]) if domain else "[]"
        return {
            "uid": uid,
            "label": label,
            "aliases": "",
            "description": description,
            "domains": domains,
            "source": source,
            "rank": rank,
            "edge": edge or {},
            "data": data,
        }

    def _alias_candidates(self, query: str, limit: int) -> list[tuple[str, str, str]]:
        query_norm = norm(query)
        candidates: list[tuple[str, str, str]] = []
        if not query_norm:
            return candidates
        candidates.extend(
            (row[0], "v3", row[1])
            for row in self.con.execute(
                "SELECT uid,alias FROM lex.v3_aliases WHERE alias=? LIMIT ?",
                (query_norm, limit * 4),
            )
        )
        candidates.extend(
            (row[0], "ext", row[1])
            for row in self.con.execute(
                "SELECT uid,alias FROM lex.extension_aliases WHERE alias=? LIMIT ?",
                (query_norm, limit * 4),
            )
        )
        if self.has_col:
            candidates.extend(
                (row[0], "ext", row[1])
                for row in self.con.execute(
                    "SELECT extension_uid,alias FROM col.aliases WHERE alias=? LIMIT ?",
                    (query_norm, limit * 4),
                )
            )
        if self.has_source_names:
            candidates.extend(
                (row[0], "ext", row[1])
                for row in self.con.execute(
                    "SELECT uid,alias FROM names.aliases WHERE alias=? "
                    "ORDER BY uid,alias LIMIT ?", (query_norm, limit * 4),
                )
            )
        # Indexed prefix probes are a bounded candidate generator, not a
        # semantic match.  Graph/domain checks and ranking happen below.
        if len(candidates) < limit:
            for token in tokens(query)[:5]:
                low, high = token, token + "\U0010ffff"
                candidates.extend(
                    (row[0], "v3", row[1])
                    for row in self.con.execute(
                        """
                        SELECT uid,alias FROM lex.v3_aliases
                        WHERE alias>=? AND alias<? LIMIT ?
                        """,
                        (low, high, limit * 3),
                    )
                )
                candidates.extend(
                    (row[0], "ext", row[1])
                    for row in self.con.execute(
                        """
                        SELECT uid,alias FROM lex.extension_aliases
                        WHERE alias>=? AND alias<? LIMIT ?
                        """,
                        (low, high, limit * 3),
                    )
                )
                if self.has_col:
                    candidates.extend(
                        (row[0], "ext", row[1])
                        for row in self.con.execute(
                            """
                            SELECT extension_uid,alias FROM col.aliases
                            WHERE alias>=? AND alias<? LIMIT ?
                            """,
                            (low, high, limit * 3),
                        )
                    )
        return candidates

    def lookup(self, query: str, limit: int = 12, domain: str | None = None) -> list[dict]:
        query_tokens = set(tokens(query))
        query_norm = norm(query)
        scored: dict[str, tuple[float, dict]] = {}
        root_uids = set(self.roots.values())
        for uid, graph, matched_alias in self._alias_candidates(query, max(12, limit)):
            row = self._node(uid)
            if not row:
                continue
            domains = str(row.get("domains") or "")
            if domain and domains not in {"", "[]", "null"} and f'"{domain}"' not in domains:
                # vPIC's vehicle candidates may still be useful for car only
                # after a high-confidence alignment to a V3 car node.
                if not (
                    domain == "car"
                    and row.get("source") == "vpic"
                    and self.con.execute(
                        """
                        SELECT 1 FROM aln.alignments a JOIN lex.v3_aliases n ON n.uid=a.v3_uid
                        WHERE a.extension_uid=? AND n.domains LIKE '%"car"%' LIMIT 1
                        """,
                        (uid,),
                    ).fetchone()
                ):
                    continue
            alias_tokens = set(tokens(matched_alias))
            overlap = len(query_tokens & alias_tokens) / max(1, len(query_tokens | alias_tokens))
            score = overlap * 8.0
            if matched_alias == query_norm:
                score += 8.0
            if norm(str(row.get("label") or "")) == query_norm:
                score += 4.0
            if uid in root_uids:
                score += 4.0 if len(query_tokens) <= 2 else 0.0
            rank = str(row.get("rank") or "").casefold()
            if rank in {"species", "subspecies", "model", "model_variant", "model_year"}:
                score += 1.0
            row.update({"match_score": score, "matched_alias": matched_alias, "graph": graph})
            if uid not in scored or score > scored[uid][0]:
                scored[uid] = (score, row)
        return [
            item[1]
            for item in sorted(
                scored.values(), key=lambda value: (-value[0], norm(value[1]["label"]), value[1]["uid"])
            )[:limit]
        ]

    def aliases_for_uid(self, uid: str, limit: int = 8) -> list[str]:
        """Return explicit names only, ordered for human-facing candidate cards.

        COL vernacular names come first for biological entities.  Descriptions
        and WordNet glosses are deliberately excluded: they are useful context,
        but are not aliases.
        """
        values: list[tuple[int, str]] = []
        if self.has_col and self._source_graph(uid) == "ext":
            values.extend(
                (0, row[0])
                for row in self.con.execute(
                    "SELECT alias FROM col.aliases WHERE extension_uid=? LIMIT ?",
                    (uid, limit * 3),
                )
            )
        table = "v3_aliases" if self._source_graph(uid) == "v3" else "extension_aliases"
        raw_column = "raw_alias"
        values.extend(
            (1, row[0])
            for row in self.con.execute(
                f"SELECT {raw_column} FROM lex.{table} WHERE uid=? LIMIT ?",
                (uid, limit * 4),
            )
        )
        label = norm(self._node(uid).get("label", ""))
        cleaned: dict[str, tuple[int, str]] = {}
        for priority, value in values:
            raw = " ".join(str(value or "").replace("_", " ").split())
            key = norm(raw)
            if not key or key == label or len(raw) > 100:
                continue
            previous = cleaned.get(key)
            if previous is None or (priority, len(raw), raw.casefold()) < (
                previous[0], len(previous[1]), previous[1].casefold()
            ):
                cleaned[key] = (priority, raw)
        return [
            value
            for _, value in sorted(
                cleaned.values(), key=lambda item: (item[0], len(item[1].split()), len(item[1]), item[1].casefold())
            )[:limit]
        ]

    def _native_neighbors(self, uid: str, direction: str, limit: int) -> list[dict]:
        graph = self._source_graph(uid)
        if direction == "children":
            endpoint, target = "parent_uid", "child_uid"
        else:
            endpoint, target = "child_uid", "parent_uid"
        if graph == "v3":
            rows = self.con.execute(
                f"""
                SELECT {target},child_uid,parent_uid,relation,layer,role,
                       navigation_role,facet_family,data
                FROM v3.edges WHERE {endpoint}=? LIMIT ?
                """,
                (uid, limit),
            ).fetchall()
            out = []
            for target_uid, child, parent, relation, layer, role, nav, facet, raw_data in rows:
                try:
                    data = json.loads(raw_data or "{}")
                except (TypeError, json.JSONDecodeError):
                    data = {}
                basis = data.get("classification_basis") or data.get("facet_basis") or ""
                evidence = data.get("evidence_record") or {}
                span = evidence.get("child_facet_span") if isinstance(evidence, dict) else ""
                edge = {
                    "child_uid": child,
                    "parent_uid": parent,
                    "relation": relation,
                    "layer": layer,
                    "role": role,
                    "navigation_role": nav,
                    "facet_family": facet,
                    "classification_basis": basis,
                    "child_facet_span": span,
                    "typed_refinement_kind": data.get("typed_refinement_kind"),
                    "confidence": data.get("confidence"),
                    "provenance": data.get("verification_provenance") or data.get("source_records"),
                    "source": "fineatlas_v3",
                }
                node = self._node(target_uid, edge)
                if node:
                    out.append(node)
            return out
        rows = self.con.execute(
            f"""
            SELECT {target},child_uid,parent_uid,relation,facet_family,
                   typed_refinement_kind,classification_basis,navigation_role,
                   source,confidence,provenance
            FROM ext.edges WHERE {endpoint}=? LIMIT ?
            """,
            (uid, limit),
        ).fetchall()
        out = []
        for target_uid, child, parent, relation, facet, kind, basis, nav, source, confidence, provenance in rows:
            edge = {
                "child_uid": child,
                "parent_uid": parent,
                "relation": relation,
                "layer": source,
                "role": "PRIMARY" if nav.startswith("PRIMARY") else "AUXILIARY",
                "navigation_role": nav,
                "facet_family": facet,
                "typed_refinement_kind": kind,
                "classification_basis": basis,
                "child_facet_span": "",
                "confidence": confidence,
                "provenance": provenance,
                "source": source,
            }
            node = self._node(target_uid, edge)
            if node:
                out.append(node)
        return out

    def _source_name_equivalents(self, uid: str) -> list[str]:
        if not self.has_source_names:
            return []
        return [row[0] for row in self.con.execute(
            """SELECT CASE WHEN left_uid=? THEN right_uid ELSE left_uid END AS other
            FROM names.equivalences WHERE left_uid=? OR right_uid=?
            ORDER BY other LIMIT 64""", (uid, uid, uid)
        )]

    def _equivalents(self, uid: str) -> list[str]:
        if self._source_graph(uid) == "v3":
            values = [
                row[0]
                for row in self.con.execute(
                    "SELECT extension_uid FROM aln.alignments WHERE v3_uid=? LIMIT 64", (uid,)
                )
            ]
            if self.con.execute(
                "SELECT 1 FROM aln.sqlite_master WHERE type='table' AND name='semantic_bridges'"
            ).fetchone():
                values.extend(
                    row[0]
                    for row in self.con.execute(
                        """
                        SELECT CASE WHEN left_uid=? THEN right_uid ELSE left_uid END
                        FROM aln.semantic_bridges
                        WHERE left_uid=? OR right_uid=? LIMIT 32
                        """,
                        (uid, uid, uid),
                    )
                )
            return sorted(set(values) | set(self._source_name_equivalents(uid)))
        values = [
            row[0]
            for row in self.con.execute(
                "SELECT v3_uid FROM aln.alignments WHERE extension_uid=? LIMIT 16", (uid,)
            )
        ]
        return sorted(set(values) | set(self._source_name_equivalents(uid)))

    def entity_key(self, uid: str) -> str:
        """Deterministic one-hop equivalence key used only for deduplication."""
        endpoints = {uid, *self._equivalents(uid)}
        # A semantic bridge may be reached from an extension through its V3
        # alignment, so close one additional bounded hop.
        for endpoint in list(endpoints):
            if self._source_graph(endpoint) == "v3":
                endpoints.update(self._equivalents(endpoint))
        v3_endpoints = sorted(value for value in endpoints if self._source_graph(value) == "v3")
        return v3_endpoints[0] if v3_endpoints else sorted(endpoints)[0]

    def neighbors(
        self,
        uid: str,
        direction: str = "children",
        limit: int = 24,
        roles: tuple[str, ...] | None = None,
    ) -> list[dict]:
        if direction not in {"children", "parents"}:
            raise ValueError(direction)
        rows = self._native_neighbors(uid, direction, limit * 2)
        # Expand one source-equivalence hop without presenting it as IS-A.
        for equivalent in self._equivalents(uid)[:16]:
            for row in self._native_neighbors(equivalent, direction, limit):
                row["edge"] = {
                    **row.get("edge", {}),
                    "via_alignment": equivalent,
                    "alignment_relation": "CROSS_SOURCE_SAME_CONCEPT",
                }
                rows.append(row)
        if roles:
            rows = [r for r in rows if r.get("edge", {}).get("navigation_role") in roles]
        unique = {}
        for row in rows:
            unique.setdefault(row["uid"], row)
        return list(unique.values())[:limit]

    def exact_label_uids(self, label: str, limit: int = 32) -> list[str]:
        query = norm(label)
        rows = self.con.execute(
            """
            SELECT uid FROM lex.v3_aliases WHERE alias=?
            UNION
            SELECT uid FROM lex.extension_aliases WHERE alias=?
            LIMIT ?
            """,
            (query, query, limit),
        ).fetchall()
        uids = [row[0] for row in rows]
        if self.has_source_names:
            uids.extend(row[0] for row in self.con.execute(
                "SELECT uid FROM names.aliases WHERE alias=? ORDER BY uid LIMIT ?",
                (query, limit)))
        return list(dict.fromkeys(uids))[:limit]

    def path_to_anchors(self, uid: str, anchor_uids: list[str], max_depth: int = 24) -> list[dict]:
        roots = set(anchor_uids)
        if not roots:
            return []
        queue = deque([(uid, [])])
        seen = {uid}
        while queue and len(seen) < 4000:
            current, path = queue.popleft()
            if current in roots:
                return list(reversed(path))
            # A validated cross-source SAME_CONCEPT root is a legal zero-rank
            # arrival, not an IS-A step.  Neighbor expansion alone cannot
            # detect this because an equivalent root has no native parent.
            matched_root = sorted(roots & set(self._equivalents(current)))
            if matched_root:
                root_uid = matched_root[0]
                alignment_step = {
                    "uid": current,
                    "label": self._node(current).get("label", current),
                    "parent_uid": root_uid,
                    "parent_label": self._node(root_uid).get("label", root_uid),
                    "edge": {"relation": "SAME_CONCEPT",
                             "navigation_role": "DOMAIN_ALIGNMENT",
                             "facet_family": "CROSS_SOURCE_EQUIVALENCE",
                             "alignment_relation": "CROSS_SOURCE_SAME_CONCEPT"},
                }
                return list(reversed([*path, alignment_step]))
            if len(path) >= max_depth:
                continue
            for parent in self.neighbors(
                current,
                "parents",
                16,
                (
                    "PRIMARY_BACKBONE",
                    "PRIMARY_IS_A",
                    "PRIMARY_TAXONOMY",
                    "PRIMARY_TYPED_REFINEMENT",
                    "DOMAIN_ALIGNMENT",
                ),
            ):
                if parent["uid"] in seen:
                    continue
                seen.add(parent["uid"])
                queue.append(
                    (
                        parent["uid"],
                        [
                            *path,
                            {
                                "uid": current,
                                "label": self._node(current).get("label", current),
                                "parent_uid": parent["uid"],
                                "parent_label": parent["label"],
                                "edge": parent.get("edge", {}),
                            },
                        ],
                    )
                )
        return []

    def path_to_roots(self, uid: str, domain: str, max_depth: int = 24) -> list[dict]:
        root = self.roots.get(domain)
        return self.path_to_anchors(uid, [root] if root else [], max_depth)

    def descendant_distance(
        self, anchor_uids: list[str], target_uids: list[str], max_depth: int = 8, beam: int = 80
    ) -> int | None:
        targets = set(target_uids)
        frontier = set(anchor_uids)
        seen = set(frontier)
        if frontier & targets:
            return 0
        for depth in range(1, max_depth + 1):
            nxt = []
            for uid in sorted(frontier):
                nxt.extend(row["uid"] for row in self.neighbors(uid, "children", beam))
            frontier = set(nxt) - seen
            seen |= frontier
            if frontier & targets:
                return depth
            if not frontier:
                break
        return None

    def close(self) -> None:
        self.con.close()


class V5DynamicIndex(V4DynamicIndex):
    """Deterministic V5 query view over the frozen V4 graph assets.

    The underlying V3/V4 databases remain read-only.  V5 changes only query
    semantics: every bounded query is ordered, and source-equivalent entities
    are collapsed before they can consume the navigation budget.
    """

    kind = "fineatlas_v5"

    def __init__(self, config_path: str | Path):
        super().__init__(config_path)
        self.kind = "fineatlas_v5"

    def _alias_candidates(self, query: str, limit: int) -> list[tuple[str, str, str]]:
        query_norm = norm(query)
        if not query_norm:
            return []
        candidates: list[tuple[str, str, str]] = []
        candidates.extend(
            (row[0], "v3", row[1])
            for row in self.con.execute(
                "SELECT uid,alias FROM lex.v3_aliases WHERE alias=? "
                "ORDER BY uid,alias LIMIT ?",
                (query_norm, limit * 4),
            )
        )
        candidates.extend(
            (row[0], "ext", row[1])
            for row in self.con.execute(
                "SELECT uid,alias FROM lex.extension_aliases WHERE alias=? "
                "ORDER BY uid,alias LIMIT ?",
                (query_norm, limit * 4),
            )
        )
        if self.has_col:
            candidates.extend(
                (row[0], "ext", row[1])
                for row in self.con.execute(
                    "SELECT extension_uid,alias FROM col.aliases WHERE alias=? "
                    "ORDER BY extension_uid,alias LIMIT ?",
                    (query_norm, limit * 4),
                )
            )
        if self.has_source_names:
            candidates.extend(
                (row[0], "ext", row[1])
                for row in self.con.execute(
                    "SELECT uid,alias FROM names.aliases WHERE alias=? "
                    "ORDER BY uid,alias LIMIT ?", (query_norm, limit * 4),
                )
            )
        if len(candidates) < limit:
            for token in tokens(query)[:5]:
                low, high = token, token + "\U0010ffff"
                candidates.extend(
                    (row[0], "v3", row[1])
                    for row in self.con.execute(
                        "SELECT uid,alias FROM lex.v3_aliases "
                        "WHERE alias>=? AND alias<? ORDER BY alias,uid LIMIT ?",
                        (low, high, limit * 3),
                    )
                )
                candidates.extend(
                    (row[0], "ext", row[1])
                    for row in self.con.execute(
                        "SELECT uid,alias FROM lex.extension_aliases "
                        "WHERE alias>=? AND alias<? ORDER BY alias,uid LIMIT ?",
                        (low, high, limit * 3),
                    )
                )
                if self.has_col:
                    candidates.extend(
                        (row[0], "ext", row[1])
                        for row in self.con.execute(
                            "SELECT extension_uid,alias FROM col.aliases "
                            "WHERE alias>=? AND alias<? "
                            "ORDER BY alias,extension_uid LIMIT ?",
                            (low, high, limit * 3),
                        )
                    )
        return candidates

    def lookup(self, query: str, limit: int = 12, domain: str | None = None) -> list[dict]:
        """Alias-aware entity linking without a fine-rank preference."""
        query_tokens = set(tokens(query))
        query_norm = norm(query)
        scored: dict[str, tuple[float, dict]] = {}
        root_uids = set(self.roots.values())
        for uid, graph, matched_alias in self._alias_candidates(query, max(12, limit)):
            row = self._node(uid)
            if not row:
                continue
            domains = str(row.get("domains") or "")
            if domain and domains not in {"", "[]", "null"} and f'"{domain}"' not in domains:
                if not (
                    domain == "car"
                    and row.get("source") == "vpic"
                    and self.con.execute(
                        "SELECT 1 FROM aln.alignments a "
                        "JOIN lex.v3_aliases n ON n.uid=a.v3_uid "
                        "WHERE a.extension_uid=? AND n.domains LIKE '%\"car\"%' "
                        "ORDER BY a.v3_uid LIMIT 1",
                        (uid,),
                    ).fetchone()
                ):
                    continue
            alias_norm = norm(matched_alias)
            alias_tokens = set(tokens(matched_alias))
            overlap = len(query_tokens & alias_tokens) / max(1, len(query_tokens | alias_tokens))
            score = overlap * 8.0
            exact_alias = alias_norm == query_norm
            exact_label = norm(str(row.get("label") or "")) == query_norm
            if exact_alias:
                score += 8.0
            if exact_label:
                score += 4.0
            if uid in root_uids and len(query_tokens) <= 2:
                score += 4.0
            row.update(
                {
                    "match_score": score,
                    "matched_alias": matched_alias,
                    "graph": graph,
                    "exact_alias_match": exact_alias,
                    "exact_label_match": exact_label,
                    "exact_identity_match": exact_alias or exact_label,
                }
            )
            entity = self.entity_key(uid)
            current = scored.get(entity)
            tie = (score, int(exact_label), -len(norm(row.get("label", ""))))
            old_tie = None
            if current:
                old = current[1]
                old_tie = (
                    current[0],
                    int(old.get("exact_label_match", False)),
                    -len(norm(old.get("label", ""))),
                )
            if current is None or tie > old_tie or (tie == old_tie and row["uid"] < current[1]["uid"]):
                row["equivalence_key"] = entity
                scored[entity] = (score, row)
        return [
            item[1]
            for item in sorted(
                scored.values(),
                key=lambda value: (
                    -int(value[1].get("exact_identity_match", False)),
                    -value[0],
                    norm(value[1]["label"]),
                    value[1]["uid"],
                ),
            )[:limit]
        ]

    def aliases_for_uid(self, uid: str, limit: int = 8) -> list[str]:
        values: list[tuple[int, str]] = []
        if self.has_col and self._source_graph(uid) == "ext":
            values.extend(
                (0, row[0])
                for row in self.con.execute(
                    "SELECT alias FROM col.aliases WHERE extension_uid=? "
                    "ORDER BY alias LIMIT ?",
                    (uid, limit * 3),
                )
            )
        table = "v3_aliases" if self._source_graph(uid) == "v3" else "extension_aliases"
        values.extend(
            (1, row[0])
            for row in self.con.execute(
                f"SELECT raw_alias FROM lex.{table} WHERE uid=? "
                "ORDER BY alias,raw_alias LIMIT ?",
                (uid, limit * 4),
            )
        )
        label = norm(self._node(uid).get("label", ""))
        cleaned: dict[str, tuple[int, str]] = {}
        for priority, value in values:
            raw = " ".join(str(value or "").replace("_", " ").split())
            key = norm(raw)
            if not key or key == label or len(raw) > 100:
                continue
            previous = cleaned.get(key)
            if previous is None or (priority, len(raw), raw.casefold()) < (
                previous[0], len(previous[1]), previous[1].casefold()
            ):
                cleaned[key] = (priority, raw)
        return [
            value
            for _, value in sorted(
                cleaned.values(),
                key=lambda item: (
                    item[0], len(item[1].split()), len(item[1]), item[1].casefold()
                ),
            )[:limit]
        ]

    def _native_neighbors(self, uid: str, direction: str, limit: int) -> list[dict]:
        graph = self._source_graph(uid)
        endpoint, target = (
            ("parent_uid", "child_uid")
            if direction == "children"
            else ("child_uid", "parent_uid")
        )
        if graph == "v3":
            rows = self.con.execute(
                f"""
                SELECT {target},child_uid,parent_uid,relation,layer,role,
                       navigation_role,facet_family,data
                FROM v3.edges WHERE {endpoint}=?
                ORDER BY {target},relation,navigation_role,facet_family LIMIT ?
                """,
                (uid, limit),
            ).fetchall()
            out = []
            for target_uid, child, parent, relation, layer, role, nav, facet, raw_data in rows:
                try:
                    data = json.loads(raw_data or "{}")
                except (TypeError, json.JSONDecodeError):
                    data = {}
                evidence = data.get("evidence_record") or {}
                edge = {
                    "child_uid": child,
                    "parent_uid": parent,
                    "relation": relation,
                    "layer": layer,
                    "role": role,
                    "navigation_role": nav,
                    "facet_family": facet,
                    "classification_basis": data.get("classification_basis") or data.get("facet_basis") or "",
                    "child_facet_span": evidence.get("child_facet_span", "") if isinstance(evidence, dict) else "",
                    "typed_refinement_kind": data.get("typed_refinement_kind"),
                    "confidence": data.get("confidence"),
                    "provenance": data.get("verification_provenance") or data.get("source_records"),
                    "source": "fineatlas_v3",
                }
                node = self._node(target_uid, edge)
                if node:
                    out.append(node)
            return out
        rows = self.con.execute(
            f"""
            SELECT {target},child_uid,parent_uid,relation,facet_family,
                   typed_refinement_kind,classification_basis,navigation_role,
                   source,confidence,provenance
            FROM ext.edges WHERE {endpoint}=?
            ORDER BY {target},relation,navigation_role,facet_family,source LIMIT ?
            """,
            (uid, limit),
        ).fetchall()
        out = []
        for target_uid, child, parent, relation, facet, kind, basis, nav, source, confidence, provenance in rows:
            edge = {
                "child_uid": child,
                "parent_uid": parent,
                "relation": relation,
                "layer": source,
                "role": "PRIMARY" if str(nav).startswith("PRIMARY") else "AUXILIARY",
                "navigation_role": nav,
                "facet_family": facet,
                "typed_refinement_kind": kind,
                "classification_basis": basis,
                "child_facet_span": "",
                "confidence": confidence,
                "provenance": provenance,
                "source": source,
            }
            node = self._node(target_uid, edge)
            if node:
                out.append(node)
        return out

    def _equivalents(self, uid: str) -> list[str]:
        if self._source_graph(uid) == "v3":
            values = [
                row[0]
                for row in self.con.execute(
                    "SELECT extension_uid FROM aln.alignments WHERE v3_uid=? "
                    "ORDER BY extension_uid LIMIT 64",
                    (uid,),
                )
            ]
            if self.con.execute(
                "SELECT 1 FROM aln.sqlite_master "
                "WHERE type='table' AND name='semantic_bridges'"
            ).fetchone():
                values.extend(
                    row[0]
                    for row in self.con.execute(
                        """
                        SELECT CASE WHEN left_uid=? THEN right_uid ELSE left_uid END AS other
                        FROM aln.semantic_bridges
                        WHERE left_uid=? OR right_uid=? ORDER BY other LIMIT 32
                        """,
                        (uid, uid, uid),
                    )
                )
            return sorted(set(values) | set(self._source_name_equivalents(uid)))
        values = [
            row[0]
            for row in self.con.execute(
                "SELECT v3_uid FROM aln.alignments WHERE extension_uid=? "
                "ORDER BY v3_uid LIMIT 16",
                (uid,),
            )
        ]
        return sorted(set(values) | set(self._source_name_equivalents(uid)))

    def neighbors(
        self,
        uid: str,
        direction: str = "children",
        limit: int = 24,
        roles: tuple[str, ...] | None = None,
    ) -> list[dict]:
        if direction not in {"children", "parents"}:
            raise ValueError(direction)
        rows = self._native_neighbors(uid, direction, max(limit * 3, 48))
        for equivalent in self._equivalents(uid)[:16]:
            for row in self._native_neighbors(equivalent, direction, max(limit * 2, 32)):
                row["edge"] = {
                    **row.get("edge", {}),
                    "via_alignment": equivalent,
                    "alignment_relation": "CROSS_SOURCE_SAME_CONCEPT",
                }
                rows.append(row)
        if roles:
            rows = [
                row for row in rows
                if row.get("edge", {}).get("navigation_role") in roles
            ]
        unique: dict[str, dict] = {}
        for row in sorted(
            rows,
            key=lambda value: (
                self.entity_key(value["uid"]),
                norm(value.get("label", "")),
                value["uid"],
                str(value.get("edge", {}).get("relation") or ""),
            ),
        ):
            unique.setdefault(self.entity_key(row["uid"]), row)
        return list(unique.values())[:limit]


# ---------------------------------------------------------------------------
# FineAtlas V8 evidence-preserving overlay
# ---------------------------------------------------------------------------

V8_IDENTITY_CARRIER_FACETS = {
    "TAXONOMIC_LINEAGE", "MODEL_IDENTITY", "TYPE_KIND", "OTHER_ATOMIC",
}
V8_VISUAL_FACETS = {
    "APPEARANCE_TEXTURE_PATTERN", "COLOR_APPEARANCE", "MORPHOLOGY_STRUCTURE",
    "STRUCTURE_CONFIGURATION", "PROPULSION_OR_ENERGY",
    "QUANTITATIVE_ATTRIBUTE", "MATERIAL_COMPOSITION",
}


def _v8_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        parts = []
        for key in sorted(value):
            text = _v8_text(value[key])
            if text:
                parts.append(f"{key}: {text}")
        return "; ".join(parts)
    if isinstance(value, (list, tuple, set)):
        return "; ".join(text for item in value if (text := _v8_text(item)))
    return str(value)


def _v8_confidence(data: dict) -> float | None:
    """Best-effort confidence without inventing values when the schema differs."""
    for key in (
        "confidence", "facet_confidence", "membership_confidence",
        "verification_confidence", "edge_confidence",
    ):
        value = data.get(key)
        try:
            if value is not None and str(value).strip() != "":
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _v8_is_gpu_verified_payload(data: dict) -> bool:
    """Return True only for the frozen evidence-grounded P279 contract.

    Many normalized V3 edges carry ``final_delta_type`` or an ``evidence_record``
    for deterministic ETL reasons.  Those fields alone do *not* mean the edge
    came from the GPU verification pipeline.  The production verifier writes a
    distinctive method/provenance plus a positive final status; require both so
    ordinary taxonomy edges never receive GPU-evidence priority.
    """
    method = str(data.get("verification_method") or "")
    provenance = data.get("verification_provenance")
    if isinstance(provenance, dict):
        provenance_rows = [provenance]
    elif isinstance(provenance, list):
        provenance_rows = [row for row in provenance if isinstance(row, dict)]
    else:
        provenance_rows = []
    fast_provenance = any(
        str(row.get("verifier") or "").startswith("QWEN3.5-9B_FAST_STAGE")
        for row in provenance_rows
    )
    fast_origin = (
        method == "FAST_JOINT_EDGE_VERIFICATION"
        or fast_provenance
        or isinstance(data.get("fast_stage1_check"), dict)
    )
    status = str(data.get("verification_status") or data.get("status") or "")
    positive = status == "VERIFIED_IS_A" or data.get("eligible_for_final_dag") is True
    return bool(fast_origin and positive)


def _v8_v3_edge_contract(
    *, child: str, parent: str, relation: str, layer: str, role: str,
    navigation_role: str, facet_family: str, raw_data: object,
) -> dict:
    """Decode the full verified-edge contract stored in V3 edge JSON.

    V3 deliberately retained the original GPU verification payload.  Earlier
    evaluators exposed only a subset of it.  V8 keeps the raw contract while
    presenting stable normalized fields to navigation code.
    """
    try:
        data = json.loads(raw_data or "{}") if isinstance(raw_data, str) else dict(raw_data or {})
    except (TypeError, ValueError, json.JSONDecodeError):
        data = {}
    evidence = data.get("evidence_record")
    if not isinstance(evidence, dict):
        evidence = {}
    child_span = (
        evidence.get("child_facet_span") or data.get("child_facet_span") or ""
    )
    parent_span = (
        evidence.get("parent_facet_span") or data.get("parent_facet_span") or ""
    )
    parent_conditions = (
        evidence.get("parent_conditions")
        if evidence.get("parent_conditions") not in (None, "", [], {})
        else data.get("parent_conditions")
    )
    evidence_source = (
        evidence.get("evidence_source") or evidence.get("source")
        or data.get("evidence_source") or data.get("facet_evidence_source") or ""
    )
    verification_provenance = data.get("verification_provenance")
    facet_provenance = data.get("facet_provenance")
    provenance = (
        verification_provenance or facet_provenance or data.get("source_records")
        or evidence.get("provenance")
    )
    kind = data.get("typed_refinement_kind") or data.get("final_delta_type") or ""
    basis = data.get("classification_basis") or data.get("facet_basis") or ""
    return {
        "child_uid": child,
        "parent_uid": parent,
        "relation": relation,
        "layer": layer,
        "role": role,
        "navigation_role": navigation_role,
        "facet_family": facet_family or data.get("facet_family") or "UNKNOWN",
        "typed_refinement_kind": kind,
        "final_delta_type": data.get("final_delta_type") or kind,
        "classification_basis": basis,
        "facet_basis": data.get("facet_basis") or "",
        "child_facet_span": _v8_text(child_span),
        "parent_facet_span": _v8_text(parent_span),
        "parent_conditions": parent_conditions if parent_conditions is not None else "",
        "parent_conditions_text": _v8_text(parent_conditions),
        "evidence_source": _v8_text(evidence_source),
        "evidence_record": evidence,
        "confidence": _v8_confidence(data),
        "verification_provenance": verification_provenance,
        "facet_provenance": facet_provenance,
        "provenance": provenance,
        "source": "fineatlas_v3",
        "source_native": True,
        "verified_contract": _v8_is_gpu_verified_payload(data),
    }


def _v8_ext_edge_contract(
    *, child: str, parent: str, relation: str, facet_family: str,
    typed_refinement_kind: object, classification_basis: object,
    navigation_role: str, source: object, confidence: object, provenance: object,
) -> dict:
    try:
        parsed_confidence = float(confidence) if confidence not in (None, "") else None
    except (TypeError, ValueError):
        parsed_confidence = None
    return {
        "child_uid": child,
        "parent_uid": parent,
        "relation": relation,
        "layer": source or "extension",
        "role": "PRIMARY" if str(navigation_role or "").startswith("PRIMARY") else "AUXILIARY",
        "navigation_role": navigation_role,
        "facet_family": facet_family or "UNKNOWN",
        "typed_refinement_kind": typed_refinement_kind or "",
        "final_delta_type": typed_refinement_kind or "",
        "classification_basis": classification_basis or "",
        "facet_basis": "",
        "child_facet_span": "",
        "parent_facet_span": "",
        "parent_conditions": "",
        "parent_conditions_text": "",
        "evidence_source": str(source or ""),
        "evidence_record": {},
        "confidence": parsed_confidence,
        "verification_provenance": None,
        "facet_provenance": None,
        "provenance": provenance,
        "source": source or "extension",
        "source_native": True,
        "verified_contract": False,
    }


def _v8_edge_signature(edge: dict) -> tuple:
    return (
        str(edge.get("child_uid") or ""), str(edge.get("parent_uid") or ""),
        str(edge.get("relation") or ""), str(edge.get("navigation_role") or ""),
        str(edge.get("facet_family") or ""), str(edge.get("source") or ""),
        norm(str(edge.get("child_facet_span") or "")),
        norm(str(edge.get("parent_facet_span") or "")),
        norm(str(edge.get("classification_basis") or "")),
    )


def _v8_edge_priority(edge: dict, active_facets: set[str] | None = None) -> tuple:
    """Stable evidence-first ordering; no benchmark labels or GT are used."""
    active = active_facets or set()
    facet = str(edge.get("facet_family") or "UNKNOWN")
    child_span = norm(str(edge.get("child_facet_span") or ""))
    parent_span = norm(str(edge.get("parent_facet_span") or ""))
    has_delta = bool(child_span and child_span != parent_span)
    verified = bool(edge.get("verified_contract"))
    has_parent_contract = bool(parent_span or _v8_text(edge.get("parent_conditions")))
    has_source = bool(edge.get("evidence_source"))
    nav = str(edge.get("navigation_role") or "")
    primary = nav.startswith("PRIMARY")
    facet_relevance = facet in active if active else facet in V8_VISUAL_FACETS
    conf = edge.get("confidence")
    try:
        conf_value = float(conf) if conf is not None else -1.0
    except (TypeError, ValueError):
        conf_value = -1.0
    # Lower tuple sorts first.  Evidence richness precedes source identity, so
    # an equivalent extension edge cannot silently erase a richer GPU edge.
    return (
        -int(verified and has_delta), -int(has_delta), -int(facet_relevance),
        -int(has_parent_contract), -int(has_source), -int(primary), -conf_value,
        str(edge.get("source") or ""), str(edge.get("facet_family") or ""),
        str(edge.get("child_uid") or ""), str(edge.get("parent_uid") or ""),
    )


class V8DynamicIndex(V5DynamicIndex):
    """Evidence-preserving V8 query layer over the frozen V4 assets.

    Important: V5/V7 retrieval remains untouched.  V8 scans each source lane
    deeply enough to avoid pre-filter starvation, applies role filters in SQL,
    aggregates equivalent-entity evidence, and only then enforces the public
    result limit.
    """

    kind = "fineatlas_v8"
    _SCAN_FLOOR = 512
    _SCAN_MULTIPLIER = 128
    _SCAN_CEILING = 8192

    def __init__(self, config_path: str | Path):
        super().__init__(config_path)
        self.kind = "fineatlas_v8"

    @staticmethod
    def _scan_limit(limit: int) -> int:
        return min(
            V8DynamicIndex._SCAN_CEILING,
            max(V8DynamicIndex._SCAN_FLOOR, max(1, int(limit)) * V8DynamicIndex._SCAN_MULTIPLIER),
        )

    def _native_neighbors_v8(
        self, uid: str, direction: str, scan_limit: int,
        roles: tuple[str, ...] | None = None,
    ) -> list[dict]:
        graph = self._source_graph(uid)
        endpoint, target = (
            ("parent_uid", "child_uid") if direction == "children"
            else ("child_uid", "parent_uid")
        )
        role_sql = ""
        args: list[object] = [uid]
        if roles:
            role_sql = " AND navigation_role IN (" + ",".join("?" for _ in roles) + ")"
            args.extend(roles)
        args.append(scan_limit)
        if graph == "v3":
            rows = self.con.execute(
                f"""
                SELECT {target},child_uid,parent_uid,relation,layer,role,
                       navigation_role,facet_family,data
                FROM v3.edges
                WHERE {endpoint}=? {role_sql}
                ORDER BY navigation_role,facet_family,{target},relation,layer
                LIMIT ?
                """,
                args,
            ).fetchall()
            out: list[dict] = []
            for target_uid, child, parent, relation, layer, role, nav, facet, raw_data in rows:
                edge = _v8_v3_edge_contract(
                    child=child, parent=parent, relation=relation, layer=layer,
                    role=role, navigation_role=nav, facet_family=facet,
                    raw_data=raw_data,
                )
                node = self._node(target_uid, edge)
                if node:
                    out.append(node)
            return out
        rows = self.con.execute(
            f"""
            SELECT {target},child_uid,parent_uid,relation,facet_family,
                   typed_refinement_kind,classification_basis,navigation_role,
                   source,confidence,provenance
            FROM ext.edges
            WHERE {endpoint}=? {role_sql}
            ORDER BY navigation_role,facet_family,source,{target},relation
            LIMIT ?
            """,
            args,
        ).fetchall()
        out = []
        for target_uid, child, parent, relation, facet, kind, basis, nav, source, confidence, provenance in rows:
            edge = _v8_ext_edge_contract(
                child=child, parent=parent, relation=relation,
                facet_family=facet, typed_refinement_kind=kind,
                classification_basis=basis, navigation_role=nav,
                source=source, confidence=confidence, provenance=provenance,
            )
            node = self._node(target_uid, edge)
            if node:
                out.append(node)
        return out

    def _aggregate_entity_rows(
        self, rows: list[dict], active_facets: set[str] | None = None,
    ) -> list[dict]:
        grouped: dict[str, dict] = {}
        for row in rows:
            key = self.entity_key(row["uid"])
            bucket = grouped.setdefault(key, {
                "representatives": [], "edges": {}, "uids": set(),
            })
            bucket["representatives"].append(row)
            bucket["uids"].add(row["uid"])
            edge = dict(row.get("edge", {}))
            bucket["edges"].setdefault(_v8_edge_signature(edge), edge)
        merged: list[dict] = []
        for entity, bucket in grouped.items():
            evidence = sorted(
                bucket["edges"].values(),
                key=lambda edge: _v8_edge_priority(edge, active_facets),
            )
            representative = sorted(
                bucket["representatives"],
                key=lambda row: (
                    _v8_edge_priority(row.get("edge", {}), active_facets),
                    norm(row.get("label", "")), row["uid"],
                ),
            )[0]
            item = dict(representative)
            item["edge"] = dict(evidence[0]) if evidence else dict(representative.get("edge", {}))
            item["edge_evidence"] = evidence
            item["equivalence_key"] = entity
            item["equivalent_uids"] = sorted(bucket["uids"])
            item["edge"]["aggregated_evidence_count"] = len(evidence)
            item["edge"]["equivalent_uid_count"] = len(bucket["uids"])
            merged.append(item)
        merged.sort(key=lambda row: (
            _v8_edge_priority(row.get("edge", {}), active_facets),
            norm(row.get("label", "")), row["uid"],
        ))
        return merged

    def neighbors(
        self, uid: str, direction: str = "children", limit: int = 24,
        roles: tuple[str, ...] | None = None,
        active_facets: set[str] | None = None,
    ) -> list[dict]:
        if direction not in {"children", "parents"}:
            raise ValueError(direction)
        scan_limit = self._scan_limit(limit)
        rows = self._native_neighbors_v8(uid, direction, scan_limit, roles)
        # Source-equivalent lanes are scanned independently.  They no longer
        # compete for a shared SQL LIMIT before evidence can be compared.
        for equivalent in self._equivalents(uid)[:16]:
            equivalent_rows = self._native_neighbors_v8(
                equivalent, direction, scan_limit, roles
            )
            for row in equivalent_rows:
                row["edge"] = {
                    **row.get("edge", {}),
                    "via_alignment": equivalent,
                    "alignment_relation": "CROSS_SOURCE_SAME_CONCEPT",
                }
            rows.extend(equivalent_rows)
        return self._aggregate_entity_rows(rows, active_facets)[:limit]

    def evidence_for_edge(self, row: dict) -> list[dict]:
        """Return every retained source contract for a retrieved entity edge."""
        values = row.get("edge_evidence")
        if isinstance(values, list) and values:
            return [dict(value) for value in values if isinstance(value, dict)]
        edge = row.get("edge")
        return [dict(edge)] if isinstance(edge, dict) and edge else []
