"""Whole-subject physical scope rules; literal guarded noun phrases, never KB hints."""
from __future__ import annotations
import re
from .structure_source_contracts import GENERAL_MODIFIERS as ORIGINAL_MODIFIERS, own_family_scope

# Each anchor has a separately checked complete physical range. In particular
# broad biplanes are not asserted to be powered airplanes.
GENERA = (
    (r'(?:fixed[ -]wing aircraft)', 'wikidata:Q2875704', 'fixed wings'),
    (r'(?:airliners?)', 'wikidata:Q210932', 'cargo or passengers'),
    (r'(?:biplanes?)', 'wikidata:Q223818', 'two main wings'),
    (r'(?:airplanes?|aeroplanes?)', 'wordnet31:02694015-n', 'fixed wing'),
    (r'(?:monoplanes?)', 'wikidata:Q627537', 'one main lifting surface'),
    (r'(?:helicopters?)', 'wikidata:Q34486', 'powered rotary wings'),
    (r'(?:aircraft|rotorcraft)', 'wordnet31:02689427-n', 'vehicle that can fly'),
    (r'(?:automobiles?|cars?)', 'wordnet31:02961779-n', 'four wheels'),
    (r'(?:locomotives?)', 'wordnet31:03690149-n', 'self-propelled engine'),
    (r'(?:laptops?|laptop computers?|notebook computers?|subnotebook computers?)', 'wordnet31:03648120-n', 'portable computer'),
    (r'(?:computers?)', 'wordnet31:03086983-n', 'calculations automatically'),
    (r'(?:dinnerware)', 'wordnet31:03207306-n', 'tableware'),
    (r'(?:loudspeakers?)', 'wordnet31:03696785-n', 'electro-acoustic'),
    (r'(?:microprocessors?)', 'wikidata:Q5297', 'single integrated circuit'),
    (r'(?:capacitors?)', 'wordnet31:02958683-n', 'electric charge'),
)
ADDITIONAL_MODIFIERS = frozenset('aviation unpowered nonpowered retractable folding foldable amphibious ultralight ultra lightweight long short range fourth fifth sixth generation year yearly person coupe convertible roadster hatchback saloon sedan station wagon door doors seats aerobatic aerobatics aerial sporting allweather all weather twinjet trijet quadjet tandem seaplane pressurized pressurised unpressurized unpressurised highwing lowwing sweptwing swept straight tailless canard float floatplane flying boat amphibian pusher deltawing delta winged crop dusting advanced basic intermediate tactical strategic medical evacuation firefighting air ambulance electrically modernized modernised'.split())
GENERAL_MODIFIERS = ORIGINAL_MODIFIERS | ADDITIONAL_MODIFIERS

def scoped_subject_genus(statement: str, label: str) -> tuple[str, str] | None:
    """Independent restrictive subject parser; never select a trailing token.

    An explicit genus is accepted only in the first subject clause, before
    relative/purpose/material/location clauses or named design arguments.
    This is a small reviewed statement contract, not a language-wide classifier.
    Anything outside it remains review. No identity equality is asserted.
    """
    whole_statement = statement or ""
    if re.search(r"\b(?:from|in)\s+(?:the\s+|a\s+)?(?:TV series|television series|a video game|a computer game|comic)\b|\b(?:fictional|imaginary|virtual)\b", whole_statement, re.I):
        return None
    text = re.sub(r"\([^()]*\)", "", whole_statement).strip()
    text = re.sub(r'\bnon[- ]powered\b','unpowered',text,flags=re.I)
    wrapper = re.fullmatch(r"Native source label:\s*(.*?);\s*subject definition:\s*(.+)", text, re.I | re.S)
    if wrapper:
        if wrapper[1].strip().casefold() != label.strip().casefold():
            return None
        text = wrapper[2].strip()
    elif ":" in text:
        return None  # unparsed source/label packaging is not a subject assertion
    text = re.split(r"[.;]\s+(?=[A-Z])", text, maxsplit=1)[0]
    copula = re.search(r"\b(?:is|was|are|were)\b\s+", text, re.I)
    if copula:
        prefix = text[:copula.start()]
        if re.search(r"\b(?:that|which|whose|who|where)\b", prefix, re.I):
            return None
        words = lambda value: re.findall(r"[a-z0-9]+", value.casefold())
        wanted, present = words(label), words(prefix)
        if present[:1] == ["the"]:
            present = present[1:]
        if present[:-1] == wanted and present[-1:] in (["series"], ["family"], ["range"], ["model"]):
            present = wanted
        if not wanted or wanted != present:
            return None  # a redirected or different-subject sentence
        text = text[copula.end():]
    text = re.sub(r"^(?:an?|the)\s+", "", text, flags=re.I)
    if re.match(r"(?:about|used|designed|produced|manufactured|built|made|located|called|named|known)\b", text, re.I):
        return None
    text = re.sub(r"^(?:family|series|line|range|type|kind|class)\s+of\s+", "", text, flags=re.I)
    # A comma before a restrictive/relative clause can coordinate distinct
    # subject kinds. Do not reduce a laptops/desktops/tablets range to laptops.
    main_scope = re.split(r"\s+(?:based|whose|with|without|that|which|for|to|in|near|of|by|from|since)\b|[.;]", text, maxsplit=1, flags=re.I)[0]
    if "," in main_scope and not re.match(r"\s*(?:licen[cs]e-built|(?:a )?version|originally|first|introduced|released|produced|manufactured|designed)\b", main_scope.split(",", 1)[1], re.I):
        return None
    text = re.split(r"\s+(?:based|whose|with|without|that|which|for|to|in|near|of|by|from|since|"
                    r"used|intended|designed|developed|manufactured|produced|built|made|released|"
                    r"introduced|marketed|capable|containing|consisting|featuring|belonging)\b|[,;]",
                    text, maxsplit=1, flags=re.I)[0].strip()
    if (not text or re.search(r"\b(?:toy|scale|miniature|fictional|imaginary|standard|protocol|"
                              r"architecture|language|software|parts?|components?|"
                              r"accessories|one-off|sole|only example|railroad|railway|cable|elevator|airship)\b", text, re.I)):
        return None
    # Engine is a modifier only when its explicit count/drive compound binds
    # to this subject, not an independent engine for another aircraft.
    engines = re.sub(r'\b(?:single|twin|double|two|three|four|six|eight|multi|[0-9]+)[ -]+engine(?:d)?\b', '', text, flags=re.I)
    if re.search(r'\bengine\b', engines, re.I):
        return None
    # Remaining coordinated nouns and unparsed parenthetical references are
    # not reduced to one last word. Pure size/adjective coordination is review.
    if re.search(r"\b(?:and|or|as)\b", text, re.I):
        return None
    if re.search(r"\b(?:not|never|no|neither|without)\b", text, re.I):
        return None
    for pattern, uid, definition_prefix in GENERA:
        matched = re.search(r"\b(" + pattern + r")\s*(?:model|variant|family|series|design|prototype)?\s*$", text, re.I)
        if matched:
            modifiers = re.findall(r"[A-Za-z]+|\d+", text[:matched.start()].casefold())
            if any(word not in GENERAL_MODIFIERS and not word.isdigit() for word in modifiers):
                continue
            if uid == "wordnet31:02961779-n":
                wheels = re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|single|twin|\d+)[ -]+wheel(?:s|ed|er)?\b", text, re.I)
                if wheels and wheels[1].casefold() not in {"four", "4"}:
                    continue  # the retained WordNet car sense requires four wheels
                # Relative/body qualifiers cannot disappear when the noun
                # phrase is cropped. This checks actual subject properties,
                # rather than any incidental mention of a different vehicle.
                count = r"(one|two|three|four|five|six|seven|eight|nine|ten|single|twin|\d+)"
                wheel_properties = re.finditer(r"\b(?:with|has|had|having|uses|using|on)\s+(?:only\s+)?" + count + r"[ -]+wheels?\b", whole_statement, re.I)
                if any(w[1].casefold() not in {"four", "4"} for w in wheel_properties):
                    continue
            if re.search(r"\b(?:that|which)\s+(?:is|was)\s+(?:an?\s+)?(?:toy|fictional|imaginary|scale model)\b|\b(?:that|which)\s+(?:is|was)\s+not\s+(?:an?\s+)?(?:real|physical)\b", whole_statement, re.I):
                continue
            return matched.group(1), uid
    return None



# Unlike the polymorphic bare noun router, these explicit physical source
# genera have complete retained definitions. CNC/wood/cutting router is excluded.
CLASS_GENERA = (
    (r'(?:musical instruments?)', 'wordnet31:03806455-n', 'musical tones or sounds'),
    (r'(?:garments?|articles? of clothing)', 'wordnet31:03423924-n', 'article of clothing'),
    (r'(?:desserts?)', 'wikidata:Q182940', 'sweet foods'),
    (r'(?:digital cameras?)', 'wikidata:Q62927', 'digital storage'),
    (r'(?:personal computers?)', 'wikidata:Q16338', 'personal use'),
    (r'(?:cameras?)', 'wikidata:Q15328', 'capture and store images and videos'),
    (r'(?:medical devices?)', 'wikidata:Q6554101', 'medical purposes'),
    (r'(?:network(?:ing)? routers?|routers?)', 'wikidata:Q5318', 'forwards data packets'),
    (r'(?:semiconductor diodes?)', 'wikidata:Q1929430', 'p–n junction'),
)
CLASS_MODIFIERS = frozenset('simple inexpensive cheap film digital video motion picture large format wooden handmade professional thermographic thermal imaging infrared action closed circuit television onboard underwater surveillance remote automatic specialised specialized home prosthetic implantable small basic electronic semiconductor networking network optical photographic fast silicon germanium junction p n'.split())


def ordinary_class_genus(statement: str, label: str, aliases=()):
    """Require a universal category definition with this exact source subject.

    This excludes bare declarations about named commercial models, instances,
    organizations and aggregate source catalogues. It does not fix their roles.
    """
    whole = statement or ''
    if re.search(r'\b(?:not|never|no)\s+(?:a\s+|an\s+)?(?:real|physical)\b|\b(?:fictional|imaginary)\b', whole, re.I):
        return None
    first = re.split(r'\.\s+(?=[A-Z])', whole, maxsplit=1)[0]
    if re.search(r'\b(?:software|virtual|simulated|simulation|rendering|3D)\b', first, re.I) and not re.search(r'\b(?:physical device|photographic film|image sensor)\b', first, re.I):
        return None
    if re.search(r'\btoy\b', label, re.I) and not re.search(r'\b(?:film camera|photographic film|image sensor|photographs|lens)\b', whole, re.I):
        return None
    text = re.sub(r'\([^()]*\)', '', whole).strip()
    copula = re.search(r'\b(?:is|are)\b\s+', text, re.I)
    if not copula or not re.match(r'^(?:a|an)\s+', text, re.I):
        return None
    prefix = text[:copula.start()].strip().rstrip(', ')
    prefix = re.split(r',|\s+or\s+|\s+also\s+', prefix, maxsplit=1, flags=re.I)[0]
    prefix = re.sub(r'^(?:a|an)\s+', '', prefix, flags=re.I).strip()
    words = lambda x: re.findall(r'[a-z0-9]+', x.casefold())
    if not any(words(prefix) == words(x) for x in (label, *aliases)):
        return None
    predicate = text[copula.end():]
    predicate = re.sub(r'\bnon[- ]powered\b','unpowered',predicate,flags=re.I)
    predicate = re.sub(r'^(?:a|an|the)\s+', '', predicate, flags=re.I)
    predicate = re.sub(r'^(?:type|kind|form|class)\s+of\s+', '', predicate, flags=re.I)
    if re.match(r'musical instrument in the string family\.', predicate, re.I):
        return 'string family', 'wikidata:Q1798603'
    # Preserve alternative subject types, negation and metaphor as review.
    clause = re.split(r'\s+(?:that|which|whose|with|without|for|to|used|designed|based|in|on|of)\b|[.;]', predicate, maxsplit=1, flags=re.I)[0].strip()
    if re.search(r'\b(?:and|or|not|no|toy|fictional|imaginary|scale|model|brand|trademark|manufacturer|product|software)\b', clause, re.I):
        return None
    for pattern, uid, definition in CLASS_GENERA + GENERA:
        match = re.search(r'\b('+pattern+r')\s*$', clause, re.I)
        if match:
            modifiers = re.findall(r'[a-z]+|\d+', clause[:match.start()].casefold())
            if all(x.isdigit() or x in GENERAL_MODIFIERS | CLASS_MODIFIERS for x in modifiers):
                if uid == 'wikidata:Q5318' and not re.search(r'\b(?:Internet|networks?|networking|data packets)\b', statement, re.I):
                    continue
                if uid == 'wikidata:Q1929430' and not re.search(r'\bp[–-]n junction\b', statement, re.I):
                    continue
                return match[1], uid
    return None
