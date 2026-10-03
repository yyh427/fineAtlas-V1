"""Read-only graph adapter preserving the frozen source view."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from fineatlas._graph.structural_v3 import V8StructuralRepairViewV3


class V25Index(V8StructuralRepairViewV3):
    """V4 typed DAG plus deterministic SAME_CONCEPT repairs.

    Overlay bridges are zero-rank equivalences.  They are never exposed as
    IS-A edges.  Existing V4 alignments are deterministically ordered and no
    longer truncated at an arbitrary first 16 rows for extension entities.
    """

    kind = "fineatlas_v25_identity_access"

    def __init__(self, descriptor: str | Path):
        self.v25_descriptor_path = Path(descriptor).resolve()
        self.v25_config = json.loads(
            self.v25_descriptor_path.read_text(encoding="utf-8"))
        super().__init__(self.v25_config["base_index"])
        overlay = Path(self.v25_config["identity_overlay"]).resolve()
        self.con.execute(
            "ATTACH DATABASE ? AS v25",
            (f"file:{overlay}?mode=ro&immutable=1",),
        )

    @lru_cache(maxsize=300_000)
    def _equivalents(self, uid: str) -> list[str]:
        values: set[str] = set()
        if self._source_graph(uid) == "v3":
            values.update(row[0] for row in self.con.execute(
                """
                SELECT extension_uid FROM aln.alignments WHERE v3_uid=?
                ORDER BY confidence DESC,
                  CASE alignment_type
                    WHEN 'SOURCE_ID_EQUIVALENCE' THEN 0
                    WHEN 'ENTITY_EQUIVALENCE' THEN 1
                    WHEN 'STRUCTURED_IDENTITY_EQUIVALENCE' THEN 2
                    ELSE 3 END,
                  extension_uid
                LIMIT 256
                """,
                (uid,),
            ))
            if self.con.execute(
                "SELECT 1 FROM aln.sqlite_master "
                "WHERE type='table' AND name='semantic_bridges'"
            ).fetchone():
                values.update(row[0] for row in self.con.execute(
                    """
                    SELECT CASE WHEN left_uid=? THEN right_uid ELSE left_uid END
                    FROM aln.semantic_bridges
                    WHERE left_uid=? OR right_uid=?
                    ORDER BY confidence DESC,1 LIMIT 128
                    """,
                    (uid, uid, uid),
                ))
        else:
            values.update(row[0] for row in self.con.execute(
                """
                SELECT v3_uid FROM aln.alignments WHERE extension_uid=?
                ORDER BY confidence DESC,
                  CASE alignment_type
                    WHEN 'SOURCE_ID_EQUIVALENCE' THEN 0
                    WHEN 'ENTITY_EQUIVALENCE' THEN 1
                    WHEN 'STRUCTURED_IDENTITY_EQUIVALENCE' THEN 2
                    ELSE 3 END,
                  v3_uid
                LIMIT 256
                """,
                (uid,),
            ))
        values.update(self._source_name_equivalents(uid))
        values.update(row[0] for row in self.con.execute(
            """
            SELECT CASE WHEN left_uid=? THEN right_uid ELSE left_uid END
            FROM v25.bridges WHERE left_uid=? OR right_uid=?
            ORDER BY confidence DESC,1 LIMIT 64
            """,
            (uid, uid, uid),
        ))
        values.discard(uid)
        return sorted(values)


def open_descriptor(path: str | Path) -> tuple[V25Index, Path]:
    descriptor = Path(path).resolve()
    config = json.loads(descriptor.read_text(encoding="utf-8"))
    return V25Index(descriptor), Path(config["identity_overlay"]).resolve()
