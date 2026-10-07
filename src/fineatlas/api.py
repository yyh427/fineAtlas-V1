"""Public interface to the FineAtlas V1 SQLite database."""

from __future__ import annotations

import os
import json
from pathlib import Path

from .consistent import ConsistentAtlas
from .browsing import BrowsingAtlas


class FineAtlas(BrowsingAtlas, ConsistentAtlas):
    """Open a SQLite file or a directory containing ``fineatlas.sqlite``.

    The default location is FINEATLAS_DATA_DIR, then the working directory.
    Use one instance per thread/process and close it with a context manager.
    """

    def __init__(
        self,
        data_dir: str | Path | None = None,
        *,
        view: str | None = None,
        relation_view: str = "strict",
        root: str | None = None,
        language: str = "en",
        browse_index: str | Path | None = None,
    ):
        path = data_dir or os.environ.get("FINEATLAS_DATA_DIR") or Path.cwd()
        super().__init__(
            path,
            view=view or "wordnet",
            relation_view=relation_view,
            root=root,
            language=language,
        )
        if browse_index is not None:
            try:
                if 'browse_links' in self._tables:
                    raise ValueError('External browse indexes require an unindexed frozen baseline')
                index_path=Path(browse_index).resolve()
                if not index_path.is_file():raise FileNotFoundError(index_path)
                self.con.execute('ATTACH DATABASE ? AS fineatlas_browse',
                                 (index_path.as_uri()+'?mode=ro&immutable=1',))
                indexed={r[0]:json.loads(r[1]) for r in self.con.execute('SELECT key,value FROM fineatlas_browse.metadata')}
                if indexed.get('schema')!='FINEATLAS_BROWSE_INDEX_V1' or not indexed.get('browse_indexes_ready'):
                    raise ValueError('External browse artifact is incomplete or has the wrong schema')
                if indexed.get('browse_source_revision')!=self._revision:
                    raise ValueError('External browse artifact belongs to another source revision')
                if indexed.get('browse_index_revision')!=indexed.get('database_revision'):
                    raise ValueError('External browse artifact revision is inconsistent')
                tables={r[0] for r in self.con.execute("SELECT name FROM fineatlas_browse.sqlite_master WHERE type='table' AND name LIKE 'browse_%'")}
                if not {'browse_nodes','browse_links','browse_facets','browse_link_counts','browse_preferences'}<=tables:
                    raise ValueError('External browse artifact is missing required tables')
                self.metadata['browse_source_release']=self.metadata.get('release')
                self.metadata.update({k:v for k,v in indexed.items() if k.startswith('browse_') or k in ('release','database_revision')})
                self._revision=indexed['database_revision'];self._tables.update(tables)
                self.browse_index_path=index_path
            except Exception:
                self.close();raise
