"""Read-only graph adapter preserving the frozen source view."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import sqlite3
from typing import Any

from fineatlas._graph.base import _v8_ext_edge_contract, norm
from fineatlas._graph.v32 import V32Index


class V33Index(V32Index):
    kind = "fineatlas_v33_systematic_cross_domain"

    def __init__(self, descriptor: str | Path):
        self.v33_descriptor_path = Path(descriptor).resolve()
        self.v33_descriptor = json.loads(self.v33_descriptor_path.read_text(encoding="utf-8"))
        super().__init__(self.v33_descriptor["base_v32_index"])
        self.v33_connections = [
            sqlite3.connect(f"file:{Path(item['path']).resolve()}?mode=ro&immutable=1", uri=True)
            for item in self.v33_descriptor["batch_overlays"]
        ]
        self.v33_new_uids = {
            uid for con in self.v33_connections
            for (uid,) in con.execute("SELECT uid FROM nodes")
        }
        self.v33_suppressed_edges: set[tuple[str, str]] = set()
        for con in self.v33_connections:
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='suppressed_edges'").fetchone():
                self.v33_suppressed_edges.update(
                    (child, parent) for child, parent in con.execute(
                        "SELECT child_uid,parent_uid FROM suppressed_edges"))

    def _node(self, uid: str, edge: dict | None = None) -> dict:
        for con in reversed(self.v33_connections):
            row = con.execute(
                "SELECT label,domain,source,rank,data FROM nodes WHERE uid=?", (uid,)
            ).fetchone()
            if row:
                label, domain, source, rank, raw = row
                data = json.loads(raw or "{}")
                return {"uid": uid, "label": str(label), "aliases": "",
                        "description": str(data.get("description") or ""),
                        "domains": json.dumps(data.get("domains") or [domain]),
                        "domain": str(domain), "source": str(source),
                        "rank": str(rank), "edge": edge or {}, "data": data}
        return super()._node(uid, edge)

    @lru_cache(maxsize=300_000)
    def _equivalents(self, uid: str) -> list[str]:
        values = set(super()._equivalents(uid))
        for con in self.v33_connections:
            values.update(row[0] for row in con.execute(
                """SELECT CASE WHEN left_uid=? THEN right_uid ELSE left_uid END
                   FROM bridges WHERE left_uid=? OR right_uid=?
                   ORDER BY confidence DESC,1 LIMIT 256""", (uid, uid, uid)))
        values.discard(uid)
        return sorted(values)

    def exact_label_uids(self, label: str, limit: int = 32) -> list[str]:
        query = norm(label)
        values = []
        for con in reversed(self.v33_connections):
            values.extend(row[0] for row in con.execute(
                "SELECT uid FROM aliases WHERE alias=? ORDER BY uid LIMIT ?", (query, limit)))
        # Old lexical tables can point to a UID before the graph node existed.
        values.extend(uid for uid in super().exact_label_uids(label, limit * 2)
                      if uid not in self.v33_new_uids)
        return list(dict.fromkeys(values))[:limit]

    def aliases_for_uid(self, uid: str, limit: int = 8) -> list[str]:
        values = []
        for con in reversed(self.v33_connections):
            values.extend(row[0] for row in con.execute(
                "SELECT raw_alias FROM aliases WHERE uid=? ORDER BY alias,raw_alias LIMIT ?",
                (uid, limit * 2)))
        if uid not in self.v33_new_uids:
            values.extend(super().aliases_for_uid(uid, limit * 2))
        own = norm((self._node(uid) or {}).get("label", ""))
        distinct: dict[str, str] = {}
        for value in values:
            key = norm(value)
            if key and key != own:
                distinct.setdefault(key, value)
        return list(distinct.values())[:limit]

    def _native_neighbors_v8(
        self, uid: str, direction: str, scan_limit: int,
        roles: tuple[str, ...] | None = None,
    ) -> list[dict]:
        rows = super()._native_neighbors_v8(uid, direction, scan_limit, roles)
        endpoint, target = (("parent_uid", "child_uid") if direction == "children"
                            else ("child_uid", "parent_uid"))
        for con in self.v33_connections:
            role_sql = ""
            args: list[Any] = [uid]
            if roles:
                role_sql = " AND navigation_role IN (" + ",".join("?" for _ in roles) + ")"
                args.extend(roles)
            args.append(scan_limit)
            query = (f"SELECT {target},child_uid,parent_uid,relation,facet_family,"
                     "typed_refinement_kind,classification_basis,navigation_role,"
                     f"source,confidence,provenance FROM edges WHERE {endpoint}=? "
                     f"{role_sql} ORDER BY navigation_role,facet_family,source,{target} "
                     "LIMIT ?")
            for target_uid, child, parent, relation, facet, kind, basis, nav, source, confidence, provenance in con.execute(query, args):
                edge = _v8_ext_edge_contract(
                    child=child, parent=parent, relation=relation,
                    facet_family=facet, typed_refinement_kind=kind,
                    classification_basis=basis, navigation_role=nav,
                    source=source, confidence=confidence, provenance=provenance,
                )
                node = self._node(target_uid, edge)
                if node:
                    rows.append(node)
        return [row for row in rows if (
            row.get("edge", {}).get("child_uid"),
            row.get("edge", {}).get("parent_uid")) not in self.v33_suppressed_edges]

    def close(self) -> None:
        for con in self.v33_connections:
            con.close()
        super().close()
