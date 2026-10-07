"""Shared public contracts; source declarations never imply strict inclusion."""

from __future__ import annotations

CLASS_ROLES = frozenset({"CLASS", "MODEL", "MODEL_FAMILY", "CONFIGURATION"})
VIEWS = ("strict", "taxonomy", "membership")
ROLE_ALIASES = {"SERIES": "MODEL_FAMILY"}
TYPED_TERMINALS = {
    "INSTANCE": ("INSTANCE_OF",),
    "ATTRIBUTE": ("ATTRIBUTE_KIND_OF",),
    "DATASET_CATEGORY": ("DEPICTS_TYPE",),
    "CONFIGURATION": ("CONFIGURATION_OF", "CONFIGURATION_TYPE_OF", "REGULATED_AS"),
    "MODEL": ("DESIGN_TYPE_OF", "REGULATED_AS", "SERIES_MEMBER_OF", "NATIVE_DESIGN_PARENT"),
    "MODEL_FAMILY": ("DESIGN_TYPE_OF", "NATIVE_DESIGN_PARENT"),
}


def edge_predicate(view: str, alias: str = "e") -> str:
    if view not in VIEWS:
        raise ValueError("relation_view must be strict, taxonomy or membership")
    strict = f"{alias}.status='ACTIVE' AND {alias}.relation='IS_A'"
    if view == "taxonomy":
        return f"(({strict}) OR ({alias}.status='TYPED_ACTIVE' AND {alias}.relation IN ('TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT')))"
    if view == "membership":
        return f"{alias}.status='TYPED_ACTIVE' AND {alias}.relation='REUSABLE_TYPE_MEMBERSHIP'"
    return strict


def role_for_rank(rank: str | None, source: str | None = None) -> str:
    rank = (rank or "").casefold()
    if rank == 'series' and (source or '').casefold() == 'wfo':
        return 'CLASS'
    groups = {
        "ORGANIZATION": {"manufacturer", "make"},
        "INSTANCE": {"instance"},
        "ATTRIBUTE": {"attribute", "horticultural_color_class"},
        "MODEL": {"model", "product_model", "aircraft_model", "vehicle_model"},
        "MODEL_FAMILY": {"model_family", "series"},
        "CONFIGURATION": {"model_year", "configuration", "model_year_configuration"},
        "UNKNOWN": {"unknown", "type_or_product_model"},
        "DATASET_CATEGORY": {"dataset_category"},
        "BIOLOGICAL_VARIANT": {"biological_variant"},
    }
    return next((role for role, ranks in groups.items() if rank in ranks), "CLASS")


def role_expression(node="n", profile="p"):
    """Exactly the same legacy-role fallback used by public node inspection."""
    cases = {
        "ORGANIZATION": ("manufacturer", "make"),
        "INSTANCE": ("instance",),
        "ATTRIBUTE": ("attribute", "horticultural_color_class"),
        "MODEL": ("model", "product_model", "aircraft_model", "vehicle_model"),
        "MODEL_FAMILY": ("model_family", "series"),
        "CONFIGURATION": ("model_year", "configuration", "model_year_configuration"),
        "UNKNOWN": ("unknown", "type_or_product_model"),
        "DATASET_CATEGORY": ("dataset_category",),
        "BIOLOGICAL_VARIANT": ("biological_variant",),
    }
    sql = (
        "CASE WHEN lower(coalesce(" + node + ".source,''))='wfo' AND lower(coalesce("+node+".rank,''))='series' THEN 'CLASS' ELSE CASE lower(coalesce("
        + node
        + ".rank,'')) "
        + " ".join(
            "WHEN '" + rank + "' THEN '" + role + "'"
            for role, ranks in cases.items()
            for rank in ranks
        )
        + " ELSE 'CLASS' END END"
    )
    return "coalesce(" + profile + ".node_kind," + sql + ")" if profile else sql


class QueryLimitError(RuntimeError):
    """A graph query stopped at its declared work bound, not at unreachability."""


class ResultList(list):
    """Backward-compatible list with explicit bounded-result metadata."""

    def __init__(self, items=(), *, has_more=False):
        super().__init__(items)
        self.has_more = bool(has_more)
        self.truncated = self.has_more
