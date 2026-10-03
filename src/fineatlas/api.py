from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from ._graph.v33 import V33Index
from ._graph.structural import structural_edge_allowed
from ._graph.base import norm, tokens

HIERARCHY_ROLES = (
    'PRIMARY_BACKBONE', 'PRIMARY_IS_A', 'PRIMARY_TAXONOMY',
    'PRIMARY_TYPED_REFINEMENT', 'SEMANTIC_NAVIGATION',
)
DEFAULT_ANCHORS = ('wordnet31:00001740-n', 'foodon:FOODON_00001002')


class FineAtlas:
    """Open a downloaded FineAtlas-V1 bundle using read-only SQLite connections.

    ``data_dir`` is the directory containing ``bundle.json`` and ``data/``.
    It defaults to FINEATLAS_DATA_DIR, then the current working directory.
    Instances own SQLite connections: use one instance per thread/process.
    """

    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir or os.environ.get('FINEATLAS_DATA_DIR') or Path.cwd()).resolve()
        manifest_path = self.data_dir / 'bundle.json'
        if not manifest_path.is_file():
            raise FileNotFoundError(f'Missing {manifest_path}; pass the downloaded bundle directory.')
        self.manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        for item in self.manifest['files']:
            path = self.data_dir / item['path']
            if not path.is_file() or path.stat().st_size != item['bytes']:
                raise FileNotFoundError(f'Missing or incomplete graph data: {path}. Run scripts/download_data.py.')
        self._runtime = tempfile.TemporaryDirectory(prefix='fineatlas-')
        runtime = Path(self._runtime.name)

        def resolve(value: Any) -> Any:
            if isinstance(value, dict) and set(value) == {'data'}:
                return str((self.data_dir / value['data']).resolve())
            if isinstance(value, dict) and set(value) == {'descriptor'}:
                return str(runtime / (value['descriptor'] + '.json'))
            if isinstance(value, dict):
                return {key: resolve(item) for key, item in value.items()}
            if isinstance(value, list):
                return [resolve(item) for item in value]
            return value

        for name, template in self.manifest['descriptors'].items():
            (runtime / (name + '.json')).write_text(json.dumps(resolve(template)), encoding='utf-8')
        try:
            self._index = V33Index(runtime / (self.manifest['entry'] + '.json'))
        except Exception:
            self._runtime.cleanup()
            raise
        self.roots = dict(self._index.roots)
        self._closed = False

    def node(self, uid: str) -> dict | None:
        """Return a node's label, source, rank, domains and retained metadata."""
        return self._index._node(uid) or None

    def exact(self, text: str, limit: int = 20) -> list[dict]:
        """Return exact normalized label/alias matches; preserve ambiguous UIDs."""
        if limit < 1:
            raise ValueError('limit must be positive')
        rows = [self.node(uid) for uid in self._index.exact_label_uids(text, limit)]
        return [row for row in rows if row]

    def search(self, text: str, limit: int = 20, domain: str | None = None) -> list[dict]:
        """Search base lexical stores and every retained overlay's aliases.

        Exact label/alias matches are returned first. This is a bounded text
        lookup, without a model, embeddings or dataset-specific ranking.
        """
        if limit < 1:
            raise ValueError('limit must be positive')
        query = norm(text)
        terms = tokens(text)[:6] or query.split()[:6]
        if not terms:
            return []
        exact_uids = self._index.exact_label_uids(text, max(limit * 4, 80))
        found = {}

        def add(row: dict) -> None:
            if not row:
                return
            if domain:
                domains = row.get('domains') or '[]'
                if isinstance(domains, str):
                    try: domains = json.loads(domains)
                    except ValueError: domains = []
                if row.get('domain') != domain and domain not in domains:
                    return
            found.setdefault(row['uid'], row)

        for uid in exact_uids:
            add(self.node(uid))
        for row in self._index.lookup(text, max(limit * 4, 80), domain):
            add(row)
        stores = [(self._index.con, schema + '.') for schema in ('v26', 'v27', 'v28')]
        stores += [(getattr(self._index, name), '') for name in ('v29_con', 'v30_con', 'v31_con')]
        stores += [(con, '') for con in self._index.v32_connections + self._index.v33_connections]
        clause = ' AND '.join('alias LIKE ?' for _ in terms)
        for con, prefix in stores:
            for (uid,) in con.execute(f'SELECT DISTINCT uid FROM {prefix}aliases WHERE {clause} ORDER BY uid LIMIT ?',
                                       [*[f'%{term}%' for term in terms], max(limit * 4, 80)]):
                add(self.node(uid))
        exact_set = set(exact_uids)
        def order(row):
            label = norm(row.get('label', ''))
            return (0 if label == query else 1 if row['uid'] in exact_set else 2,
                    -sum(term in label for term in terms), label, row['uid'])
        return sorted(found.values(), key=order)[:limit]

    def neighbors(self, uid: str, direction: str = 'children', limit: int = 20,
                  structural_only: bool = True) -> list[dict]:
        """Return parents/children with edge contracts and source provenance.

        Quarantined edges remain suppressed even with structural_only=False.
        The latter also exposes auxiliary links for source inspection.
        """
        if direction not in ('children', 'parents'):
            raise ValueError('direction must be children or parents')
        if limit < 1:
            raise ValueError('limit must be positive')
        rows = self._index.neighbors(uid, direction, max(limit, limit * 4) if structural_only else limit,
                                     HIERARCHY_ROLES if structural_only else None)
        if structural_only:
            rows = [row for row in rows if structural_edge_allowed(row)]
        return rows[:limit]

    def path(self, uid: str, anchors: list[str] | None = None, max_depth: int = 32) -> list[dict]:
        """Return a bounded anchor-to-node witness path, or [] if none is found.

        SAME_CONCEPT identity alignment can connect source presentations; it
        does not constitute a classification refinement. The root itself may
        be omitted from the returned steps; parent_uid identifies each step.
        """
        return self._index.path_to_anchors(uid, list(anchors or DEFAULT_ANCHORS), max_depth)

    def equivalents(self, uid: str) -> list[str]:
        """Return source presentations linked by the query view's identity bridges."""
        return self._index._equivalents(uid)

    def target(self, dataset: str, class_id: str | int) -> dict | None:
        """Read the optional six-dataset category-to-node catalog."""
        return self._index.dataset_target(dataset, str(class_id))

    def stats(self) -> dict:
        """Return the verified bundle inventory, counting policy and roots."""
        return {'release': self.manifest['release'], 'graph_version': self.manifest['graph_version'],
                **self.manifest['counts'], 'count_policy': self.manifest['count_policy'], 'roots': self.roots}

    def close(self) -> None:
        if not self._closed:
            try:
                self._index.close()
            finally:
                self._runtime.cleanup()
                self._closed = True

    def __enter__(self) -> 'FineAtlas':
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
