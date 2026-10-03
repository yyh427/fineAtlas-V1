"""Read-only graph adapter preserving the frozen source view."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from fineatlas._graph.base import _v8_ext_edge_contract, norm
from fineatlas._graph.v25 import V25Index


class V26Index(V25Index):
    """Frozen V25 plus the independently versioned completion delta."""

    kind = "fineatlas_v26_six_dataset_completion"

    def __init__(self, descriptor: str | Path):
        self.v26_descriptor_path = Path(descriptor).resolve()
        self.v26_config = json.loads(
            self.v26_descriptor_path.read_text(encoding="utf-8"))
        super().__init__(self.v26_config["base_v25_index"])
        overlay = Path(self.v26_config["completion_overlay"]).resolve()
        self.con.execute(
            "ATTACH DATABASE ? AS v26", (f"file:{overlay}?mode=ro&immutable=1",))

    def _node(self, uid: str, edge: dict | None = None) -> dict:
        row = self.con.execute(
            "SELECT label,domain,source,rank,data FROM v26.nodes WHERE uid=?",
            (uid,),
        ).fetchone()
        if not row:
            return super()._node(uid, edge)
        label, domain, source, rank, raw_data = row
        try:
            data = json.loads(raw_data or "{}")
        except (TypeError, json.JSONDecodeError):
            data = {}
        return {
            "uid": uid,
            "label": str(label or uid),
            "aliases": "",
            "description": str(data.get("description") or ""),
            "domains": json.dumps([domain] if domain else []),
            "domain": str(domain or ""),
            "source": str(source or "fineatlas_v26"),
            "rank": str(rank or ""),
            "edge": edge or {},
            "data": data,
        }

    @lru_cache(maxsize=300_000)
    def _equivalents(self, uid: str) -> list[str]:
        values = set(super()._equivalents(uid))
        values.update(row[0] for row in self.con.execute(
            """
            SELECT CASE WHEN left_uid=? THEN right_uid ELSE left_uid END
            FROM v26.bridges WHERE left_uid=? OR right_uid=?
            ORDER BY confidence DESC,1 LIMIT 256
            """,
            (uid, uid, uid),
        ))
        values.discard(uid)
        return sorted(values)

    def exact_label_uids(self, label: str, limit: int = 32) -> list[str]:
        query = norm(label)
        values = [row[0] for row in self.con.execute(
            "SELECT uid FROM v26.aliases WHERE alias=? ORDER BY uid LIMIT ?",
            (query, limit),
        )]
        values.extend(super().exact_label_uids(label, limit * 2))
        return list(dict.fromkeys(values))[:limit]

    def aliases_for_uid(self, uid: str, limit: int = 8) -> list[str]:
        values = [row[0] for row in self.con.execute(
            "SELECT raw_alias FROM v26.aliases WHERE uid=? "
            "ORDER BY alias,raw_alias LIMIT ?", (uid, limit * 2))]
        values.extend(super().aliases_for_uid(uid, limit * 2))
        label = norm((self._node(uid) or {}).get("label", ""))
        unique: dict[str, str] = {}
        for value in values:
            key = norm(value)
            if key and key != label:
                unique.setdefault(key, str(value))
        return list(unique.values())[:limit]

    def _native_neighbors_v8(
        self, uid: str, direction: str, scan_limit: int,
        roles: tuple[str, ...] | None = None,
    ) -> list[dict]:
        rows = super()._native_neighbors_v8(uid, direction, scan_limit, roles)
        endpoint, target = (
            ("parent_uid", "child_uid") if direction == "children"
            else ("child_uid", "parent_uid")
        )
        role_sql = ""
        args: list[Any] = [uid]
        if roles:
            role_sql = " AND navigation_role IN (" + ",".join("?" for _ in roles) + ")"
            args.extend(roles)
        args.append(scan_limit)
        delta = self.con.execute(
            f"""
            SELECT {target},child_uid,parent_uid,relation,facet_family,
                   typed_refinement_kind,classification_basis,navigation_role,
                   source,confidence,provenance
            FROM v26.edges WHERE {endpoint}=? {role_sql}
            ORDER BY navigation_role,facet_family,source,{target},relation LIMIT ?
            """,
            args,
        ).fetchall()
        for target_uid, child, parent, relation, facet, kind, basis, nav, source, confidence, provenance in delta:
            edge = _v8_ext_edge_contract(
                child=child, parent=parent, relation=relation,
                facet_family=facet, typed_refinement_kind=kind,
                classification_basis=basis, navigation_role=nav,
                source=source, confidence=confidence, provenance=provenance,
            )
            node = self._node(target_uid, edge)
            if node:
                rows.append(node)
        return rows

    def dataset_target(self, dataset: str, class_id: str) -> dict[str, Any] | None:
        row = self.con.execute(
            """
            SELECT dataset,class_id,label,target_uid,decision_status,
                   identity_basis,granularity_basis,evidence_ids,provenance
            FROM v26.dataset_targets WHERE dataset=? AND class_id=?
            """, (str(dataset), str(class_id)),
        ).fetchone()
        if not row:
            return None
        keys = (
            "dataset", "class_id", "label", "target_uid", "decision_status",
            "identity_basis", "granularity_basis", "evidence_ids", "provenance",
        )
        value = dict(zip(keys, row))
        for key in ("evidence_ids", "provenance"):
            try:
                default = "[]" if key == "evidence_ids" else "{}"
                value[key] = json.loads(value[key] or default)
            except (TypeError, json.JSONDecodeError):
                pass
        return value


def open_descriptor(path: str | Path) -> tuple[V26Index, Path]:
    descriptor = Path(path).resolve()
    config = json.loads(descriptor.read_text(encoding="utf-8"))
    return V26Index(descriptor), Path(config["completion_overlay"]).resolve()
