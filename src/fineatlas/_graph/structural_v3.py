"""Read-only graph adapter preserving the frozen source view."""
from __future__ import annotations

from collections import deque
from typing import Any, Mapping

from .structural import V8StructuralRepairView, structural_edge_allowed

_DOMAIN_KIND_TOKENS = {
    "animal": ("BREED_IDENTITY", "BREED"),
    "plant": ("CULTIVAR_IDENTITY", "CULTIVAR", "VARIETY", "VARIETAS"),
    "aircraft": ("MODEL_IDENTITY", "AIRCRAFT_MODEL", "AIRCRAFT_FAMILY", "SERIES"),
}

_ALLOWED_CONTAINER_ROLES = {
    "PRIMARY_TYPED_REFINEMENT", "PRIMARY_IS_A", "PRIMARY_BACKBONE",
    "PRIMARY_TAXONOMY", "SEMANTIC_NAVIGATION",
}


def typed_kind_matches_domain(kind: str, domain: str) -> bool:
    value = str(kind or "").upper()
    return any(token in value for token in _DOMAIN_KIND_TOKENS.get(domain, ()))


class V8StructuralRepairViewV3(V8StructuralRepairView):
    """V2 repair view + source-native typed-container domain projection."""

    kind = "fineatlas_v8_structural_repair_view_v3"

    def _domain_container_evidence(
        self, uid: str, domain: str, limit: int = 96,
    ) -> dict[str, Any] | None:
        """Return evidence only for a reusable typed container, never a leaf.

        A container is admitted when at least two distinct children are linked
        by source-native typed/taxonomic relations whose refinement kinds are
        compatible with the requested domain.  This prevents a single benchmark
        identity from becoming root-reachable merely because its node says
        ``domains=[...]``.
        """
        try:
            children = self.neighbors(uid, "children", limit, None)
        except Exception:
            children = []
        matched: list[dict[str, Any]] = []
        seen: set[str] = set()
        for child in children:
            child_uid = str(child.get("uid") or "")
            if not child_uid or child_uid in seen:
                continue
            edge = dict(child.get("edge") or {})
            role = str(edge.get("navigation_role") or edge.get("role") or "").upper()
            kind = str(edge.get("typed_refinement_kind") or "").upper()
            relation = str(edge.get("relation") or "").upper()
            if role not in _ALLOWED_CONTAINER_ROLES:
                continue
            if relation not in {"IS_A", "TAXONOMIC_REFINEMENT", "TYPED_REFINEMENT", "REUSABLE_TYPE_REFINEMENT"}:
                continue
            if not typed_kind_matches_domain(kind, domain):
                continue
            seen.add(child_uid)
            matched.append({
                "uid": child_uid,
                "kind": kind,
                "relation": relation,
                "source": str(edge.get("source") or ""),
            })
            if len(matched) >= 2:
                break
        if len(matched) < 2:
            return None
        return {
            "container_uid": str(uid),
            "domain": domain,
            "typed_child_count_lower_bound": len(matched),
            "typed_child_examples": matched,
        }

    def structural_path_to_roots(
        self, uid: str, domain: str, max_depth: int = 32,
    ) -> list[dict[str, Any]]:
        root = self.roots.get(domain)
        if not root:
            return []
        root = str(root)
        start = str(uid)
        queue = deque([(start, [])])
        seen = {start}
        while queue and len(seen) < 16000:
            current, path = queue.popleft()
            if current == root:
                return list(reversed(path))
            try:
                equivalents = set(self._equivalents(current))
            except Exception:
                equivalents = set()
            if root in equivalents:
                step = {
                    "uid": current,
                    "label": (self._node(current) or {}).get("label", current),
                    "parent_uid": root,
                    "parent_label": (self._node(root) or {}).get("label", root),
                    "edge": {
                        "relation": "SAME_CONCEPT",
                        "navigation_role": "DOMAIN_ALIGNMENT",
                        "facet_family": "CROSS_SOURCE_EQUIVALENCE",
                        "alignment_relation": "CROSS_SOURCE_SAME_CONCEPT",
                        "structural_repair_view": True,
                    },
                }
                return list(reversed([*path, step]))

            # Only after at least one genuine structural step from the queried
            # identity may a reusable typed container align to a domain root.
            # This avoids declaring an arbitrary leaf root-reachable from its
            # own domain tag.
            if path:
                evidence = self._domain_container_evidence(current, domain)
                if evidence:
                    step = {
                        "uid": current,
                        "label": (self._node(current) or {}).get("label", current),
                        "parent_uid": root,
                        "parent_label": (self._node(root) or {}).get("label", root),
                        "edge": {
                            "relation": "DOMAIN_CONTAINER_ALIGNMENT",
                            "navigation_role": "DOMAIN_ALIGNMENT",
                            "facet_family": "TYPED_CONTAINER_ALIGNMENT",
                            "typed_refinement_kind": "SOURCE_NATIVE_TYPED_CONTAINER",
                            "source": "read_only_structural_repair_v3",
                            "provenance": evidence,
                            "structural_repair_view": True,
                        },
                    }
                    return list(reversed([*path, step]))

            if len(path) >= max_depth:
                continue
            try:
                parents = self.neighbors(current, "parents", 64, None)
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
                        "label": (self._node(current) or {}).get("label", current),
                        "parent_uid": parent_uid,
                        "parent_label": str(parent.get("label") or parent_uid),
                        "edge": dict(parent.get("edge") or {}),
                    }],
                ))
        return []
