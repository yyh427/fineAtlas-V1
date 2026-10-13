"""Compact model feedback; detailed identity and path contracts stay in the SDK."""
from __future__ import annotations

import re


def simple_feedback(result: dict) -> str:
    """Show names and session-issued choices without exposing source class IDs.

    Same-name alternatives retain separate handles. This only formats results;
    it never merges identities, changes eligibility, or changes traversal.
    """
    rows = []
    for group, kind in (("candidates", "choice"),
                        ("navigation_candidates", "navigation")):
        for item in result.get(group, []):
            label = " ".join(str(item["label"]).split())
            names = []
            for name in item.get("name_index", []):
                name = " ".join(str(name).split())
                if name and name != label and not re.match(r"^\d+[._]", name):
                    if name not in names:
                        names.append(name)
            aliases = "; names=" + " | ".join(names[:20]) if names else ""
            rows.append(f"{label} [{kind}={item['handle']}{aliases}]")
    return "\n".join(rows) or "(no candidates returned)"
