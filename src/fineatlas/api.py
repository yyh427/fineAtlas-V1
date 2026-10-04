"""Public interface to the FineAtlas V1 SQLite database."""
from __future__ import annotations

import os
from pathlib import Path

from .single import SingleAtlas


class FineAtlas(SingleAtlas):
    """Open a SQLite file or a directory containing ``fineatlas.sqlite``.

    The default location is FINEATLAS_DATA_DIR, then the working directory.
    Use one instance per thread/process and close it with a context manager.
    """

    def __init__(self, data_dir: str | Path | None = None, *,
                 view: str | None = None, relation_view: str = 'strict'):
        path = data_dir or os.environ.get('FINEATLAS_DATA_DIR') or Path.cwd()
        super().__init__(path, view=view or 'wordnet', relation_view=relation_view)
