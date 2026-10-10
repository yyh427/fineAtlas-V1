"""Review owned physical genera before selecting a broader source field.

This additive grammar does not change the already frozen source parsers.
An owned nominal member predicate can state its physical kind, whereas a
derived-from or merely mentioned object's kind cannot supply that predicate.
"""
from __future__ import annotations

import re

from .structure_owned_scope_rules import MODIFIERS, own_first_kind, owned_physical_genus, words
from .structure_subject_scope_rules import CLASS_GENERA, CLASS_MODIFIERS


def owned_complete_head(statement: str, label: str, source_names=()) -> tuple[str, str] | None:
    text = statement.strip()
    copula = re.search(r"\b(?:is|was|are|were)\b\s+", text, re.I)
    first = re.split(r"[.;]\s+(?=[A-Z])", text[copula.end():] if copula else text, maxsplit=1)[0]
    if re.search(r"\b(?:fictional|imaginary|virtual|replica|scale model|not real|not physical|toy)\b", first, re.I):
        return None
    head = own_first_kind(statement, label, source_names)
    if head and head != "member":
        # Semicolons always end a declaration, even when the next historical
        # clause starts with lowercase. It cannot supply a missing jet kind.
        return head.split(';', 1)[0].strip(), "OWNED_FIRST_PHYSICAL_PREDICATE"
    if not copula:
        return None
    prefix = re.sub(r"^(?:the|an?)\s+", "", text[:copula.start()].strip(), flags=re.I)
    if not any(words(prefix) == words(name) for name in (label, *source_names)):
        return None
    member = re.match(r"(?:an?\s+)?member of (?:the\s+)?(.+?) (?:family|series|range) of (.+)", first, re.I)
    if not member or re.search(r"\b(?:derived|based|part|engine|component|prototype for|project for)\b", member[1], re.I):
        return None
    # Only this first, complete member-of-family-of predicate supplies kind.
    # Nothing from a following comparison, purpose or historical clause does.
    kind = re.split(r"[.;]|\s+(?:with|that|which|whose|for|built|manufactured|produced|derived|based)\b", member[2], maxsplit=1, flags=re.I)[0]
    return kind.strip(" ,"), "OWNED_MEMBER_OF_FAMILY_OF_PHYSICAL_PREDICATE"


def complete_owned_physical_genus(statement: str, label: str, source_names=(), compound_senses=()) -> dict | None:
    found = owned_complete_head(statement, label, source_names)
    if not found:
        return None
    head, basis = found
    normalized = re.sub(r"\b(wide|narrow)body\b", r"\1-body", head, flags=re.I)
    normalized = re.sub(r"\b(short|medium|long)[ -]+to[ -]+(short|medium|long)[ -]+range\b", r"\1 \2 range", normalized, flags=re.I)
    normalized = re.sub(r"\btwin[ -]+jet\b", "twinjet", normalized, flags=re.I)
    # Commas separating adjective groups cannot drop a coordinated noun kind.
    normalized = re.sub(r",\s*", " ", normalized)
    if re.search(r"\b(?:and|or|not|never)\b", normalized, re.I):
        return None
    # Resolve only an exact compound supplied by a separately retained generic
    # definition. A source domain or the bare word jet supplies no aviation
    # sense. These definitions are sense witnesses, not new navigation nodes.
    for sense in compound_senses:
        compound = sense['compound']
        if not re.fullmatch(r'[a-z]+(?: [a-z]+)+', compound):
            continue
        match = re.search(r'\b'+re.escape(compound)+r's?(?: (?:family|series|model))?$', normalized, re.I)
        if not match:
            continue
        prefix = normalized[:match.start()].strip()
        if not all(t in MODIFIERS or t.isdigit() for t in words(prefix)):
            continue
        definition = sense['definition_statement']
        definition_scope = owned_complete_head(definition, sense.get('source_label',compound), sense.get('source_names',()))
        if not definition_scope or not re.search(r'\b(?:jet[- ]powered|jet aircraft|aircraft.*jet engines|jet[- ]propelled)\b', definition_scope[0], re.I):
            continue
        # A generic business jet class does not entail fixed-wing scope. The
        # regional-airliner sense needs its separately bound complete airplane
        # scope; no "nearly always" inference is made.
        fixed = bool(sense.get('fixed_wing_scope_witness'))
        two = bool(re.search(r'\b(?:twin|two|2)[ -]+engine(?:d|s)?\b', prefix, re.I))
        return {'head':head,'genus':'twinjet' if fixed and two else 'jet aircraft',
                'parent':'wordnet31:04510794-n' if fixed and two else 'wordnet31:03601053-n' if fixed else 'wikidata:Q206592',
                'predicate_kind':'OWNED_COMPOUND_WITH_INDEPENDENT_GENERIC_AVIATION_SENSE',
                'aviation_compound':compound,'compound_source_uid':sense['uid'],
                'fixed_wing_evidence':'independent complete compound and airliner scope' if fixed else None,
                'two_jet_engine_evidence':re.search(r'\b(?:twin|two|2)[ -]+engine(?:d|s)?\b',prefix,re.I)[0] if fixed and two else None}
    end = re.search(r"\b(airliners?|airplanes?|aeroplanes?|aircraft|rotorcraft)(?:\s+(?:family|series|model|designs?))?$", normalized, re.I)
    if end:
        prefix = normalized[:end.start()].strip()
        tokens = words(prefix)
        if all(t in MODIFIERS or t.isdigit() or t in {"twinjet", "trijet", "quadjet"} for t in tokens):
            fixed_wing_noun = end[1].casefold() not in {"aircraft", "rotorcraft"}
            two_jets = "twinjet" in tokens or bool(re.search(r"\b(?:twin|two|2)[ -]+engine(?:d|s)?\b", prefix, re.I) and "jet" in tokens)
            if re.search(r"\b(?:unpowered|nonpowered|non-powered)\b", prefix, re.I) and any(t in {"jet", "twinjet", "trijet", "quadjet", "turboprop"} for t in tokens):
                return None
            if two_jets and (fixed_wing_noun or (end[1].casefold() == "aircraft" and re.search(r"\bfixed[ -]wing\b", prefix, re.I))):
                return {"head": head, "genus": "twinjet", "parent": "wordnet31:04510794-n", "predicate_kind": basis, "fixed_wing_evidence": end[1] if fixed_wing_noun else "fixed-wing", "two_jet_engine_evidence": "twinjet" if "twinjet" in tokens else re.search(r"\b(?:twin|two|2)[ -]+engine(?:d|s)?\b", prefix, re.I)[0] + " jet"}
            if "jet" in tokens or "twinjet" in tokens or "trijet" in tokens or "quadjet" in tokens:
                return {"head": head, "genus": "jet aircraft", "parent": "wordnet31:03601053-n" if fixed_wing_noun else "wikidata:Q206592", "predicate_kind": basis, "fixed_wing_evidence": end[1] if fixed_wing_noun else None}
            if "turboprop" in tokens and fixed_wing_noun:
                return {"head": head, "genus": "turboprop airplane", "parent": "wordnet31:04018858-n", "predicate_kind": basis, "fixed_wing_evidence": end[1]}
    # A specific digital-camera/personal-computer declaration precedes its
    # broader camera/computer noun. Do not discard a proven specific modifier.
    for pattern, uid, _ in CLASS_GENERA:
        match = re.search(r"\b(" + pattern + r")$", normalized, re.I)
        if match and all(t in MODIFIERS | CLASS_MODIFIERS or t.isdigit() for t in words(normalized[:match.start()])):
            if uid == "wikidata:Q5318" and not re.search(r"\b(?:Internet|network|networking|data packets)\b", statement, re.I):
                continue
            if uid == "wikidata:Q1929430" and not re.search(r"\bp[–-]n junction\b", statement, re.I):
                continue
            return {"head": head, "genus": match[1], "parent": uid, "predicate_kind": basis}
    # Retain the frozen own-head and parent sense distinctions for all domains.
    literal = owned_physical_genus(head, label)
    if literal and literal[1] != "wordnet31:02961779-n":
        # A jet is also a fluid stream. An aircraft sense must be established
        # by this owned predicate, never a domain tag or a later example.
        if literal[1] == "wikidata:Q206592" and not re.search(
            r"\b(?:aircraft|airplanes?|aeroplanes?|airliners?|rotorcraft)\b", head, re.I
        ):
            return None
        return {"head": head, "genus": literal[0], "parent": literal[1], "predicate_kind": basis}
    return None


def owned_generic_class_scope(statement: str, label: str, source_names=()) -> bool:
    """Separate explicit universal kinds from named production programmes.

    Import rank and another representation's role are deliberately unused.
    This establishes class grain; physical kind and full range still require
    their independent checks.
    """
    found = owned_complete_head(statement, label, source_names)
    if found is None:
        return False
    text = statement.strip()
    copula = re.search(r"\b(?:is|was|are|were)\b\s+", text, re.I)
    predicate = text[copula.end():] if copula else text
    predicate = re.split(r"[.;]\s+(?=[A-Z])", predicate, maxsplit=1)[0]
    if re.match(r"(?:an?\s+)?(?:type|kind|category|class) of\b", predicate, re.I):
        return True
    # Plural intensions are universal only when followed by a defining
    # relative clause. A production series of named products is different.
    if re.match(r"(?:an?\s+)?(?:[a-z-]+\s+){0,8}(?:instruments|aircraft|cameras|computers|devices)\s+(?:that|which)\b", predicate, re.I):
        return True
    prefix = text[:copula.start()].strip() if copula else ""
    if not re.match(r"^(?:a|an)\s+", prefix, re.I):
        return False
    # Explicitly named product/production statements are insufficient for a
    # class intension even when an importer assigned rank='class'.
    if re.search(r"\b(?:manufactured in series|units were (?:built|produced)|systems were (?:built|produced)|computer project|processor project|announced in|in its various incarnations)\b", text, re.I):
        return False
    return True
