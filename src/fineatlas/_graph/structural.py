"""Read-only graph adapter preserving the frozen source view."""
from __future__ import annotations

from collections import deque
from typing import Any, Mapping

from .base import V8DynamicIndex

_PRIMARY_ROLES = {
    "PRIMARY_BACKBONE", "PRIMARY_IS_A", "PRIMARY_TAXONOMY",
    "PRIMARY_TYPED_REFINEMENT", "DOMAIN_ALIGNMENT",
}

_SEMANTIC_RELATIONS = {
    "IS_A", "TAXONOMIC_REFINEMENT", "TYPED_REFINEMENT",
    "REUSABLE_TYPE_REFINEMENT",
}

_IDENTITY_TOKENS = (
    "BREED_IDENTITY", "CULTIVAR_IDENTITY", "MODEL_IDENTITY",
    "AIRCRAFT_MODEL", "AIRCRAFT_FAMILY", "SERIES",
    "GENERIC_TYPE_KIND", "TAXON", "TYPE_KIND",
)


def structural_edge_allowed(row: Mapping[str, Any]) -> bool:
    """Fail-closed structural edge policy used only by the repaired read view."""
    edge = dict(row.get("edge") or {})
    role = str(edge.get("navigation_role") or edge.get("role") or "").upper()
    if role in _PRIMARY_ROLES:
        return True
    if role != "SEMANTIC_NAVIGATION":
        return False
    relation = str(edge.get("relation") or "").upper()
    facet = str(edge.get("facet_family") or "").upper()
    kind = str(edge.get("typed_refinement_kind") or "").upper()
    if relation not in _SEMANTIC_RELATIONS:
        return False
    # Do not admit arbitrary semantic links.  They must still be explicit
    # taxonomy/type/model refinements from the frozen source graph.
    if facet in {"TAXONOMIC_LINEAGE", "TYPE_KIND", "MODEL_IDENTITY"}:
        return True
    return any(token in kind for token in _IDENTITY_TOKENS)


class V8StructuralRepairView(V8DynamicIndex):
    """V8 index with a non-mutating, provenance-preserving structural BFS."""

    kind = "fineatlas_v8_structural_repair_view_v1"

    def structural_path_to_anchors(
        self, uid: str, anchor_uids: list[str], max_depth: int = 32,
    ) -> list[dict[str, Any]]:
        roots = {str(x) for x in anchor_uids if x}
        if not roots:
            return []
        queue = deque([(str(uid), [])])
        seen = {str(uid)}
        while queue and len(seen) < 12000:
            current, path = queue.popleft()
            if current in roots:
                return list(reversed(path))
            try:
                equivalents = set(self._equivalents(current))
            except Exception:
                equivalents = set()
            matched_root = sorted(roots & equivalents)
            if matched_root:
                root_uid = matched_root[0]
                step = {
                    "uid": current,
                    "label": self._node(current).get("label", current),
                    "parent_uid": root_uid,
                    "parent_label": self._node(root_uid).get("label", root_uid),
                    "edge": {
                        "relation": "SAME_CONCEPT",
                        "navigation_role": "DOMAIN_ALIGNMENT",
                        "facet_family": "CROSS_SOURCE_EQUIVALENCE",
                        "alignment_relation": "CROSS_SOURCE_SAME_CONCEPT",
                        "structural_repair_view": True,
                    },
                }
                return list(reversed([*path, step]))
            if len(path) >= max_depth:
                continue
            try:
                parents = self.neighbors(current, "parents", 48, None)
            except Exception:
                parents = []
            parents = sorted(
                (row for row in parents if structural_edge_allowed(row)),
                key=lambda row: (str(row.get("uid") or ""), str(row.get("label") or "")),
            )
            for parent in parents:
                parent_uid = str(parent.get("uid") or "")
                if not parent_uid or parent_uid in seen:
                    continue
                seen.add(parent_uid)
                queue.append((
                    parent_uid,
                    [*path, {
                        "uid": current,
                        "label": self._node(current).get("label", current),
                        "parent_uid": parent_uid,
                        "parent_label": str(parent.get("label") or parent_uid),
                        "edge": dict(parent.get("edge") or {}),
                    }],
                ))
        return []

    def structural_path_to_roots(
        self, uid: str, domain: str, max_depth: int = 32,
    ) -> list[dict[str, Any]]:
        root = self.roots.get(domain)
        return self.structural_path_to_anchors(uid, [root] if root else [], max_depth=max_depth)
