"""Source-role guards: an identifier/rank field cannot erase instance evidence."""
from __future__ import annotations

def allows_model_extraction(native_payload: dict, profile: dict | None) -> bool:
    """Keep conflicting canonical instance declarations out of model extraction.

    A later manufacturer adapter may re-adjudicate a role with independent
    design evidence. A nominal definition plus a historical `rank=model`
    field alone does not justify replacing an accepted instance declaration.
    """
    roles = {(profile or {}).get('node_kind'), native_payload.get('node_kind')}
    return not roles.intersection({'INSTANCE','ATTRIBUTE','ORGANIZATION','DATASET_CATEGORY','BIOLOGICAL_VARIANT'})


def nominal_role_decision(native: dict, declaration: dict) -> tuple[str | None, str]:
    """Evaluate retained definitions, never a UID, rank or P31 alone.

    Historical/location evidence identifies a particular object. A standard
    computer used on multiple platforms describes a design. Other disagreements
    require review instead of forcing either role.
    """
    import re
    text = (native.get('definition') or native.get('intro') or '') + ' ' + declaration.get('sentence', '')
    lower = text.casefold()
    if ('computer' in lower and re.search(r'\bstandard\b', lower)
            and re.search(r'\bplatforms\b', lower)
            and re.search(r'\b(?:first unit|instruction set|starting in)\b', lower)):
        return 'MODEL', 'Reusable standard computer for multiple platforms; retained independent design definition'
    if (re.search(r'\bship\b', lower)
            and re.search(r'\b(?:built|wrecked|sank|scrapped|captured|requisitioned|operated|sailing|caught fire|arrive|transported|in (?:the )?service|belonged)\b', lower)):
        return 'INSTANCE', 'Named vessel with individual construction, service or historical event evidence'
    if ('building' in lower and re.search(r'\b(?:standing|located|situated)\b', lower)):
        return 'INSTANCE', 'Named building with independently stated physical location'
    return None, 'Retained nominal definition does not independently settle individual versus reusable design'


def design_grain_for_claims(claims: list[dict]) -> tuple[str | None, str]:
    """Prefer an explicit design group over a historical generic model rank.

    An independent series/family definition supports a group; an explicit native
    family declaration cannot be erased by another representation's old rank.
    Original declarations are retained by the caller.
    """
    import re
    if any(re.search(r'\b(?:series|family)\s+of\b', p.get('nominal_head', ''), re.I) for p in claims):
        return 'MODEL_FAMILY', 'Independent definition explicitly describes a series or family of designs'
    declared = {p.get('native_role_claim', {}).get('role') for p in claims
                if p.get('native_role_claim', {}).get('native_meta_uid')}
    if 'MODEL_FAMILY' in declared:
        return 'MODEL_FAMILY', 'Explicit native family declaration takes precedence over a generic adapter model rank'
    if declared == {'MODEL'}:
        return 'MODEL', 'Explicit native design declaration; no independent family scope established'
    return None, 'Conflicting design granularity lacks independent family or specific-model evidence'
