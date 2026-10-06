"""Ground lexical object-kind heads in a native, cycle-checked type ontology."""

from __future__ import annotations
import re
from ._text import norm

DEFINITION_SQL = "coalesce(nullif(n.description,''),json_extract(n.data,'$.wikidata_description'),json_extract(n.data,'$.evidence_record.wikidata_description'),json_extract(n.data,'$.description'),'')"

def object_kind_head(head):
    """Keep the noun phrase, excluding location, history and quantity clauses."""
    return re.split(r"\s+(?:in|near|located|situated|containing|originating|found|available|classified|capable)\b",
                    head,maxsplit=1,flags=re.I)[0].strip(' ,')


class WordNetKinds:
    def __init__(self, connection, *, include_native=False):
        self.c = connection
        self.cache = {}
        self.scope_cache = {}
        self.include_native = include_native
        self.artifact_roots = {
            r[0]
            for r in self.c.execute(
                "SELECT DISTINCT n.uid FROM aliases a CROSS JOIN nodes n ON n.uid=a.uid WHERE a.alias='artifact' AND n.uid LIKE 'wordnet31:%' AND n.visibility='ACTIVE'"
            )
        }

    def candidates(self, term):
        # Years, quantities and catalogue numbers cannot supply a lexical
        # object-kind head, even when an old product alias matches the number.
        if not re.search(r"[A-Za-z]", term):
            return set()
        candidates = {norm(term)}
        for value in list(candidates):
            if value.endswith("s") and not value.endswith(("ss", "series", "species")):
                candidates.add(value[:-1])
        constraint = (
            "(n.uid LIKE 'wordnet31:%' OR (coalesce(n.rank,'') IN ('class','') AND length("
            + DEFINITION_SQL
            + ")>0))"
            if self.include_native
            else "n.uid LIKE 'wordnet31:%'"
        )
        found = {
            r[0]
            for value in candidates
            for r in self.c.execute(
                "SELECT DISTINCT n.uid FROM aliases a CROSS JOIN nodes n ON n.uid=a.uid WHERE a.alias=? AND "
                + constraint
                + " AND n.visibility='ACTIVE'",
                (value,),
            )
        }
        return {
            uid for uid in found if self.generic_type(uid) and self.artifact_type(uid)
        }

    def generic_type(self, uid):
        if uid.startswith("wordnet31:"):
            return True
        row = self.c.execute(
            "SELECT " + DEFINITION_SQL + ",n.label,n.description FROM nodes n WHERE uid=?", (uid,)
        ).fetchone()
        # A short Wikidata description or historical CLASS rank is not an
        # independent reusable-type definition for a native lexical alias.
        if not row or not row[2] or re.search(
            r"^(?:an? )?(?:family|series|model|manufacturer|company|organization|organisation)\b|\b(?:is|was|are|were) (?:an? |the )?(?:[^.;]{0,35} )?(?:family|series|model|manufacturer|company|organization|organisation|line|range)\b",
            row[0],
            re.I,
        ):
            return False
        if (re.search(r'\b(?:lead|flag|sister)[ -]?ship\b',row[0],re.I)
                and not re.match(r'\s*an?\s',row[0],re.I)):
            return False
        # A historical CLASS/rank declaration is not independent type proof.
        # Proper commercial design names with explicit manufacturing or release
        # statements must not become parents for a generic alias such as PC.
        if (re.search(r'\b(?:manufactured|developed|produced|released|introduced)\b',row[0],re.I)
                and re.match(r'[A-Z][a-z]{2,}\b[^.]{0,70}\d',row[1])):
            return False
        if self.c.execute(
            "SELECT 1 FROM sqlite_master WHERE name='node_profiles'"
        ).fetchone():
            profile = self.c.execute(
                "SELECT node_kind FROM node_profiles WHERE uid=?", (uid,)
            ).fetchone()
            if profile and profile[0] != "CLASS":
                return False
        return True

    def representative(self, uids):
        groups = {}
        for uid in uids:
            component = self.c.execute(
                "SELECT component_id FROM nodes WHERE uid=?", (uid,)
            ).fetchone()[0]
            groups.setdefault(component, []).append(uid)
        if len(groups) != 1:
            return None
        return sorted(
            next(iter(groups.values())),
            key=lambda uid: (not uid.startswith("wordnet31:"), uid),
        )[0]

    def resolve_head(self, head, scope=None):
        # Location and quantity clauses describe the subject, not its kind.
        # A large aquifer "in Kenya containing ... water" cannot acquire the
        # artifact sense of "water" as its parent.
        head = object_kind_head(head)
        words = norm(head).split()
        for size in range(min(4, len(words)), 0, -1):
            candidates = self.candidates(" ".join(words[-size:]))
            if scope:
                candidates = {uid for uid in candidates if self.within(uid, {scope})}
            parent = self.representative(candidates)
            if parent:
                return parent
        return None

    def parent_uids(self, uid):
        if self.include_native:
            return [
                r[0]
                for r in self.c.execute(
                    "SELECT e.parent_uid FROM edges e JOIN nodes p ON p.uid=e.parent_uid WHERE e.child_uid=? AND e.status='ACTIVE' AND e.relation='IS_A' AND p.visibility='ACTIVE' AND (p.uid LIKE 'wordnet31:%' OR coalesce(p.rank,'') IN ('class',''))",
                    (uid,),
                )
            ]
        return [
            r[0]
            for r in self.c.execute(
                "SELECT parent_uid FROM edges WHERE child_uid=? AND status='ACTIVE' AND relation='IS_A' AND parent_uid LIKE 'wordnet31:%'",
                (uid,),
            )
        ]

    def within(self, uid, roots):
        todo = [uid]
        seen = set()
        while todo and len(seen) < 1000:
            current = todo.pop()
            if current in roots:
                return True
            if current in seen:
                continue
            seen.add(current)
            todo.extend(self.parent_uids(current))
        return False

    def artifact_type(self, uid):
        if uid in self.scope_cache:
            return self.scope_cache[uid]
        todo = [uid]
        seen = set()
        while todo and len(seen) < 1000:
            current = todo.pop()
            if current in self.artifact_roots:
                self.scope_cache[uid] = True
                return True
            if current in seen:
                continue
            seen.add(current)
            todo.extend(self.parent_uids(current))
        self.scope_cache[uid] = False
        return False

    def unique_artifact(self, term):
        term = norm(term)
        if term in self.cache:
            return self.cache[term]
        uid = self.representative(self.candidates(term))
        self.cache[term] = uid
        return self.cache[term]

    def clinical_kind(self, name, definition):
        """Use object-kind fields, never code/panel/class-number attributes.

        FDA names use an inverted noun, e.g. 'Catheter, balloon'. Definitions
        naming software, substances or anatomy cannot acquire artifact ISA.
        Ambiguous lexical senses remain native navigation only.
        """
        if re.search(
            r"\b(?:software|algorithm|application|reagent|drug|analyte|tissue|anatomical|organism)\b",
            name + " " + definition,
            re.I,
        ):
            return None
        principal = name.split(",")[0].strip()
        uid = self.unique_artifact(principal)
        if uid:
            return uid
        # A first indefinite object-kind definition supplies another grounded
        # head, before purpose, location, relative or composition clauses.
        m = re.match(r"\s*(?:a|an)\s+(.{1,180})", definition, re.I)
        if not m:
            return None
        head = re.split(
            r"\b(?:that|which|with|for|of|designed|used|intended|located|made|and)\b|[.;]",
            m[1],
            maxsplit=1,
            flags=re.I,
        )[0]
        words = norm(head).split()
        for size in range(min(4, len(words)), 0, -1):
            uid = self.unique_artifact(" ".join(words[-size:]))
            if uid:
                return uid
        return None
