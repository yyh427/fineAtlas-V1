"""Conservative engineering grain decisions from retained source evidence."""
from __future__ import annotations

import re


def engineering_role_hint(source, rank, domain, label, description, definition=''):
    """Return a supported design grain, or None when evidence is insufficient.

    Named-refinement ranks and P31 alone do not establish a reusable type.
    EPA's explicit model-variant declaration establishes a design record.
    Family/model words in an engineering description establish that grain.
    Individual-vessel evidence takes precedence over design interpretations.
    """
    text = (description or '') + ' ' + (definition or '')
    if re.search(r'\b(?:is|was)\s+(?:the|a)\s+(?:lead|sister|flag|co-flag)[ -]?ship\b', text, re.I):
        return 'INSTANCE', 'Independent description identifies a particular vessel'
    if source == 'epa' and rank == 'model_variant':
        return 'MODEL', 'Native EPA rank explicitly identifies a model variant'
    if domain not in {'aircraft', 'car', 'cars'}:
        return None, 'Engineering description outside this evidence scope'
    if re.search(r'\b(?:family|series)\b', description or '', re.I):
        return 'MODEL_FAMILY', 'Native engineering description explicitly identifies a family or series'
    if re.search(r'\b(?:model|variant)\b', description or '', re.I):
        return 'MODEL', 'Native engineering description explicitly identifies a model or variant'
    if (re.search(r'\b(?:manufactured|developed|produced|designed)\b', definition or '', re.I)
            and re.search(r'\b(?:aircraft|airliner|aeroplane|airplane|helicopter|car|automobile)\b', definition or '', re.I)
            and re.search(r'\d', label or '')):
        return 'MODEL', 'Independent manufacturing definition identifies a designated engineering design'
    return None, 'Retained description does not independently settle the design grain'
