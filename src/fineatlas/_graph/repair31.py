"""Read-only graph adapter preserving the frozen source view."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from fineatlas._graph.v31 import V31Index


class V31AcceptedIndex(V31Index):
    kind = "fineatlas_v31_independent_acceptance_repair"

    def __init__(self, descriptor: str | Path):
        config = json.loads(Path(descriptor).read_text(encoding="utf-8"))
        super().__init__(config["base_v31_index"])
        repair = Path(config["repair_overlay"]).resolve()
        self.repair_con = sqlite3.connect(f"file:{repair}?mode=ro&immutable=1", uri=True)
        self._repair_suppressed_pairs = set(self.repair_con.execute(
            "SELECT child_uid,parent_uid FROM suppressed_edges"))

    def _native_neighbors_v8(
        self, uid: str, direction: str, scan_limit: int,
        roles: tuple[str, ...] | None = None,
    ) -> list[dict]:
        return [row for row in super()._native_neighbors_v8(
            uid, direction, scan_limit, roles)
            if (row.get("edge", {}).get("child_uid"),
                row.get("edge", {}).get("parent_uid")) not in self._repair_suppressed_pairs]

    def close(self) -> None:
        self.repair_con.close()
        self.v31_con.close()
        self.v30_con.close()
        super().close()
