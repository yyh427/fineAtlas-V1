"""Text normalization used by the database name and alias indexes."""
from __future__ import annotations

import re


def norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def tokens(text: str) -> list[str]:
    return [word for word in norm(text).split() if len(word) > 2]
