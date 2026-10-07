"""Engineering grain evidence; a type word or historical rank is insufficient."""
from __future__ import annotations
import re
import unicodedata
from .nominal import object_kind_head

ENGINEERING_DOMAINS = frozenset('bridges buildings aircraft car cars ships locomotives tractors computers desktop_computers laptops single_board_computers computer_hardware computer_monitors smartphones tablets wearable_computers smartwatches fitness_trackers game_consoles gpus graphics_cards solid_state_drives network_routers network_switches printers cameras camera_bodies digital_cameras camera_lenses television_sets loudspeakers headphones earbuds electronic_components electronic_devices electronic_equipment integrated_circuits microprocessors semiconductor_devices semiconductor_diodes ceramic_capacitors pcbs source_electronic_devices source_integrated_circuits source_semiconductor_diodes tools hand_tools power_tools medical_devices surgical_instruments home_appliances furniture clothing musical_instruments sports_equipment'.split())
OBJECT = r'\b(?:aircraft|airliner|airship|blimp|paraglider|paramotor|kitplane|bushplane|feederliner|aeroplane|airplane|plane|seaplane|flying boat|helicopter|glider|sailplane|gyroplane|autogyro|autogyra|rotorcraft|airlifter|freighter|bomber|fighter|interceptor|ornithopter|sportplane|monoplane|biplane|sesquiplane|floatplane|quadruplane|jet|drone|UAV|UCAV|ultralight|car|automobile|vehicle|truck|bus|SUV|van|minivan|microvan|campervan|racingcar|sportscar|roadster|microcar|pickup|saloon|minibus|MPV|sedan|coupe|crossover|convertible|hatchback|tractor|locomotive|train|engine|motor|ship|vessel|boat|destroyer|frigate|cruiser|battleship|submarine|computer|laptop|tablet|smartphone|phone|watch|camera|lens|printer|processor|microprocessor|multiprocessor|microcontroller|chip|circuit|capacitor|diode|router|switch|console|headphone|earbud|speaker|television|GPU|graphics card|SSD|drive|keyboard|instrument|device|machine|equipment|product|chair|furniture|tool)s?\b'


def subject_words(text):
    """Fold diacritics for subject verification, without merging identities."""
    text = ''.join(ch for ch in unicodedata.normalize('NFKD', text or '')
                   if not unicodedata.combining(ch))
    return re.findall(r'[^\W_]+', text.casefold())


def native_subject_aliases(entity):
    """Names asserted by one exact source entity, never related articles."""
    values = [entity.get('labels', {}).get('en', {}).get('value'),
              entity.get('sitelinks', {}).get('enwiki', {}).get('title')]
    values.extend(a.get('value') for a in entity.get('aliases', {}).get('en', []))
    return tuple(sorted({v for v in values if v and
                         (len(subject_words(v)) > 1 or len(v) >= 4)}))


def aircraft_engine_conditions(label):
    """Read explicit aircraft engine/propeller classification conditions."""
    match=re.fullmatch(r'aircraft with (?:(\d+) )?((?:(?:tractor|piston-propeller|turboprop|turbine)[ -])*)(engines?|propellers?)',label or '',re.I)
    if not match:return None
    count,qualifiers,unit=match.groups()
    words=re.findall(r'piston-propeller|tractor|turboprop|turbine',qualifiers.lower())
    if len(words)!=len(set(words)):return None
    conditions=set(words)
    if count:conditions.add('count:'+str(int(count)))
    return ('engine' if unit.lower().startswith('engine') else 'propeller',frozenset(conditions))


def definition_head(text, subject_label=None, *, subject_aliases=()):
    """Return the subject kind in the first definitional clause."""
    original_text=text or ''
    text = re.sub(r'\([^()]*\)', '', original_text)
    text = re.split(r'[.;]\s+(?=[A-Z])',text,maxsplit=1)[0]
    match = re.search(r'\b(?:is|was|are|were)\s+(?:an?|the)\s+([^.;]{1,240})', text, re.I)
    original_copula=re.search(r'\b(?:is|was|are|were)\b',original_text,re.I)
    if original_copula and subject_label:
        labels=[subject_label, *subject_aliases]
        label_word_sets=[subject_words(re.sub(r'\([^()]*\)','',label)) for label in labels if label]
        original_prefix=original_text[:original_copula.start()] if original_copula else text[:match.start()]
        prefix_words=set(subject_words(original_prefix))
        manufacturer_subject=False
        for words in label_word_sets:
            maker=re.search(r'\b(?:developed|manufactured|produced|designed|built)\s+by\s+([^,.;]{1,100})',original_text,re.I)
            if not maker:continue
            maker_words=set(subject_words(maker[1]))
            for split in range(1,len(words)):
                if all(w in maker_words for w in words[:split]) and all(w in prefix_words for w in words[split:]):
                    manufacturer_subject=True;break
        if label_word_sets and not manufacturer_subject and not any(words and all(w in prefix_words for w in words) for words in label_word_sets) and not re.fullmatch(r'\s*(?:it|this|these|they)\s*',original_prefix,re.I):
            return ''
    value = match[1] if match else re.split(r'[.;]\s+(?=[A-Z])',text,maxsplit=1)[0]
    for boundary in re.finditer(r'\s+(?:by|from|since|built|produced|manufactured|released|introduced|made|created|revealed|unveiled|ordered|proposed|but|and(?=\s+(?:is|was|has|had|can|was|were|produced|manufactured|built)\b))\b',value,re.I):
        if boundary.group().strip().lower() in {'by','from','since'} or re.search(OBJECT,value[:boundary.start()],re.I):
            value=value[:boundary.start()];break
    return object_kind_head(value)


def engineering_role_hint(source, rank, domain, label, description, definition='', *, generic_label=False, subject_aliases=()):
    """Return a supported role or leave the record for independent review.

    Words such as family/series only count within a product-group noun phrase.
    Purpose clauses, TV series and family-car size categories cannot set grain.
    Explicit individual histories take precedence over manufacturing evidence.
    """
    # Redirected or related articles cannot adjudicate the subject's grain.
    if definition and not definition_head(definition,label,subject_aliases=subject_aliases):
        definition=''
    texts = [x for x in (description, definition) if x]
    # Some adapters use a label-prefixed sentence rather than a definition.
    # Words inside that subject name cannot establish its role.
    texts = [re.sub(r'^'+re.escape(label)+r'\s+(?!is\b|was\b|are\b|were\b)', '', x, flags=re.I)
             if label and not re.search(r'\b(?:is|was|are|were)\s+(?:an?|the)\s+',x,re.I)
             else x for x in texts]
    text = ' '.join(texts)
    heads = [definition_head(x,label,subject_aliases=subject_aliases) for x in texts]
    named_class = bool(re.search(r'-class\b|\bClass\s+[A-Z0-9]|\bclass\s+[A-Z0-9]|\b[Cc]lass(?:\s+locomotive)?$', label or ''))
    ship_family = named_class and re.match(r'[A-Z]', label or '') and any(re.search(r'\b(?:ship|vessel|destroyer|frigate|cruiser|battleship|submarine|carrier|trawler)s?\b', h, re.I) for h in heads)
    # An indefinite lower-case subject introduces a reusable kind even when
    # its catalog label is title-cased and later paragraphs mention development.
    indefinite=re.match(r'^\s*An?\s+([^,;]{1,160})',definition or '')
    if indefinite:
        first=indefinite[1].split()[0]
        count=len(subject_words(label))
        if first[:1].islower() and subject_words(indefinite[1])[:count]==subject_words(label):
            return None, 'The independent definition introduces a reusable kind with an indefinite generic subject'
    if generic_label:
        return None, 'Independent lexical generic type is not a product-family declaration'
    if re.search(r'\b(?:is|are)\s+(?:any|every)\s+',definition,re.I):
        return None, 'The independent definition quantifies membership of a reusable kind'
    if any(re.search(r'\b(?:vehicle|car|aircraft|size|weight)\s+(?:size\s+)?(?:class|classification|category)\b',h,re.I) for h in heads):
        return None, 'The subject definition explicitly identifies a reusable vehicle classification'
    if any(re.search(r'\b(?:body[ -]style|body type|size class)\b',h,re.I) for h in heads):
        return None, 'A reusable body style or size class is not a manufacturer design variant'
    if any(re.search(r'\b(?:standards|protocols?|instruction set architectures?)\b|\bstandard(?:$|\s+(?:for|governing|defining)\b)',h,re.I) for h in heads):
        return None, 'A standard or architecture declaration is not a physical product family'
    if domain=='ships' and re.match(r'(?:Type|Project)\s+\d',label or '') and any(re.search(r'\b(?:ship|vessel|trawler|boat)\b',h,re.I) for h in heads):
        return 'MODEL_FAMILY', 'Source identifies a numbered ship-design type rather than a generic vessel kind'
    if domain == 'ships' and not ship_family:
        if (re.search(r'\b(?:lead|sister|flag|co-flag)[ -]?ship\b', text, re.I)
            or re.match(r'(?:USS|USNS|HMS|HMAS|HMCS|HNLMS|RFA|SS|MV|RMMV|ORP|USRC|USC&GSS?|BRP|INS|KDB|ROKS|TCG)\s', label or '') and any(re.search(r'\b(?:ship|vessel|destroyer|frigate|cruiser|battleship|submarine|liner|tanker)\b', h, re.I) for h in heads)
            or re.search(r'\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|eighteenth|nineteenth)\s+ship\b', text, re.I)
            or re.match(r'[A-Z]',label or '') and not any(re.search(r'\b(?:type|kind|category) of\b',h,re.I) for h in heads)
            and re.search(r'\b(?:ship|vessel|destroyer|frigate|cruiser|battleship|submarine|liner|tanker)\b', text, re.I)
            and re.search(r'\b(?:commissioned|decommissioned|laid down|sank|sunk|scrapped|wrecked|requisitioned|captured|hull number|built by|designed by|sailed|delivered|in service|served|operated)\b', text, re.I)):
            return 'INSTANCE', 'Independent vessel definition establishes an individual history'
    if domain=='ships' and not ship_family and re.match(r'[A-Z]',label or '') and definition_head(definition,label,subject_aliases=subject_aliases):
        generic_vessel=any(re.search(r'\b(?:type|kind|category|class) of\b',h,re.I) for h in heads)
        individual_context=re.search(r'\b(?:Navy|Naval Forces|formerly known as)\b|\bduring (?:his|her|its) \d{4} expedition\b|\bbetween \d{4} and \d{4}\b',text,re.I)
        if not generic_vessel and individual_context and any(re.search(r'\b(?:ship|vessel|destroyer|frigate|cruiser|battleship|submarine|liner|tanker)\b',h,re.I) for h in heads):
            return 'INSTANCE', 'Subject-specific vessel definition supplies an individual naval owner, prior name or dated service history'
    if source == 'epa' and rank == 'model_variant':
        return 'MODEL', 'Native EPA rank explicitly identifies a model variant'
    if any(re.match(r'(?:the )?(?:name|call sign)\b',h,re.I) for h in heads):
        return None, 'An operational name or call sign does not independently identify a factory design'
    if domain not in ENGINEERING_DOMAINS:
        return None, 'Engineering description outside this evidence scope'
    if re.search(r'\b(?:one-off|sole example|only example|only one example|serial number|registration number|tail number)\b', text, re.I):
        return None, 'Unique-object evidence requires independent instance/design adjudication'
    if ship_family:
        return 'MODEL_FAMILY', 'Named ship class explicitly groups vessel designs'
    # A named locomotive Class denotes a design class, not an ontology rank.
    if domain == 'locomotives' and named_class and re.search(r'\blocomo(?:tive|tives)\b', text, re.I):
        return 'MODEL_FAMILY', 'Named locomotive class with independently stated vehicle kind'
    if domain=='locomotives' and re.match(r'[A-Z]',label or '') and re.search(r'\bclass of\b[^.;]{0,80}\blocomo(?:tive|tives)\b',description,re.I):
        return 'MODEL_FAMILY', 'Named locomotive design class explicitly groups locomotives'
    for head in heads:
        if re.search(r'\bone of (?:a |the )?(?:series|family) of\b',head,re.I) and re.search(r'\d',label or '') and re.search(OBJECT,head,re.I):
            return 'MODEL', 'The designated subject is one model within an explicitly wider design series'
        if re.search(r'\b(?:first|second|third|single|individual)\s+model\s+of\b',head,re.I) and re.search(OBJECT,head,re.I):
            return 'MODEL', 'Definition identifies an individual model within a wider product series'
        named_group=bool(re.match(r'[A-Z0-9]',label or '') or re.search(r'\b[A-Z][a-z]{2,}',label or '') and re.search(OBJECT+r'\s+(?:family|series|line|range)\s+(?:by|from)\s+[A-Z]',description or ''))
        if named_group and (re.search(OBJECT+r'\s+(?:model\s+)?(?:family|series|line|range)\b', head, re.I) or re.search(r'\b(?:family|series|line|range)\s+of\s+[^.;]{0,70}'+OBJECT, head, re.I)):
            return 'MODEL_FAMILY', 'Product-group phrase explicitly identifies a design family or series'
        if re.fullmatch(r'(?:tractorline|tractor serie)', head.strip(), re.I):
            return 'MODEL_FAMILY', 'Native short description explicitly names a tractor product line'
        if re.search(r'\b(?:model|variant)\s+of\s+[^.;]{0,70}'+OBJECT, head, re.I) or re.search(OBJECT+r'\s+(?:model|variant)\b', head, re.I):
            return 'MODEL', 'Object-kind phrase explicitly identifies a model or variant'
    if domain in {'cars','car','aircraft','tractors','locomotives'} and re.search(r'\bmodel\s+[A-Z0-9]', label or '') and any(re.search(OBJECT,h,re.I) for h in heads):
        return 'MODEL', 'Explicit named model designation and independently stated vehicle kind'
    designation_label = (label or '')+' '+(' '.join(subject_aliases) if definition else '')
    designation = bool(re.search(r'\b[A-Z][A-Za-z]{1,}(?:[ .-]+[A-Za-z][A-Za-z]*){0,2}[ .-]*\d|\b[A-Z]{2,}[- ]\d|\b[A-Z]{2,}-[A-Z]+\b|\b[А-ЯA-Z]{1,4}[- .]?\d+[A-Z0-9-]*\b|\b[A-Z]\.[IVX]{1,}\b|\b[A-Z][a-z]+\s+[IVX]{1,4}\b', designation_label))
    designation = designation or bool(re.search(r'\b[^\W\d_]{1,}[ .-]+\d+[A-Za-z-]*\b',designation_label) and any(ch.isupper() for ch in label or ''))
    if domain in {'cars','car','aircraft','tractors','locomotives'} and designation and any(re.search(OBJECT, h, re.I) for h in heads):
        return 'MODEL', 'Specific engineering designation and source-stated vehicle kind identify a design'
    if domain in {'cars','car','aircraft','tractors','locomotives'} and re.match(r'[A-Z]', label or '') and re.search(r'\b(?:manufactured|developed|produced|designed|marketed|proposed|prototype)\b[^.;]{0,100}\bby\b', description or '', re.I) and any(re.search(OBJECT,h,re.I) for h in heads):
        return 'MODEL', 'Native description explicitly identifies a named vehicle design and its manufacturer'
    if domain in {'cars','car','aircraft','tractors','locomotives'} and re.match(r'[A-Z]',label or '') and any(re.search(OBJECT,h,re.I) for h in heads) and re.search(OBJECT+r'\s+(?:by|from)\s+[A-Z]',description):
        return 'MODEL', 'Native description identifies a named vehicle design and its manufacturer'
    if domain in {'cars','car','aircraft','tractors','locomotives'} and re.match(r'[A-Z]',label or '') and any(re.search(OBJECT,h,re.I) for h in heads):
        if re.search(OBJECT+r'\s+(?:concept\s+)?(?:by|from)\s+[A-Z]|\b(?:under|in) development by\s+[A-Z]',definition):
            return 'MODEL', 'Subject definition identifies a named vehicle design and its developer'
        prefix=re.split(r'\b(?:is|was|are|were)\b',definition,maxsplit=1,flags=re.I)[0]
        if re.search(r'\b(?:designated\s+)?[A-Z][a-z]+\s+(?:Model\s+)?[A-Z]?\.?\d',prefix):
            return 'MODEL', 'Independent subject clause supplies a specific vehicle design designation'
    # Do not interpret a generic definition's manufacturing/output clauses as
    # evidence of a specific design. The subject must be a named designation.
    # A short native "type of aircraft" describes both a reusable kind and a
    # named design. It cannot defeat a subject-specific independent definition.
    generic_heads=[definition_head(definition,label,subject_aliases=subject_aliases)] if definition else heads
    generic = any(re.search(r'\b(?:type|kind|category|class|form|variety)\s+of\b', h, re.I) for h in generic_heads)
    designation_evidence = re.match(r'[A-Z]', label or '') if domain in {'cars','car','aircraft','tractors','locomotives'} else designation
    factory_history = bool(re.search(r'\b(?:manufactured|developed|produced|designed|built|marketed|made|created|revealed|unveiled|proposed)\b', definition or '', re.I))
    named_subject_history = bool((re.search(r'\b(?:introduced|shown)\b',definition or '',re.I) or re.search(r'\bconstructed\b',definition or '',re.I) and re.search(r'\b(?:homebuilding|homebuilt|kits?|plans?)\b',definition or '',re.I)) and
                                 (designation or len(re.findall(r'\b[A-Z][\w-]+',label or ''))>=2) and
                                 definition_head(definition,label,subject_aliases=subject_aliases))
    if not generic and designation_evidence and (factory_history or named_subject_history) and any(re.search(OBJECT, h, re.I) for h in heads):
        return 'MODEL', 'Independent manufacturing definition identifies a designated engineering design'
    if domain in {'cars','car','aircraft','tractors','locomotives'} and not generic and re.match(r'[A-Z]',label or '') and definition_head(definition,label,subject_aliases=subject_aliases):
        if any(re.search(OBJECT,h,re.I) and re.search(r'\b(?:prototype|design|variant|conversion)\b',h,re.I) for h in heads):
            return 'MODEL', 'Subject-specific definition explicitly identifies a named vehicle design or prototype'
        if (re.search(r'\btype of aircraft\b',description,re.I) or domain=='aircraft' and len(re.findall(r'\b[A-Z][\w-]+',label))>=2 and re.match(r'^The\s+',definition)) and re.search(r'\b(?:19\d0s|20\d0s|World War|First World War|Second World War)\b',definition,re.I) and any(re.search(OBJECT,h,re.I) for h in heads):
            return 'MODEL', 'Native design-type declaration corroborated by a subject-specific historical aircraft definition'
        if domain=='aircraft' and re.search(r'\btype of aircraft\b',description,re.I) and len(re.findall(r'\b[A-Z][\w-]+',label))>=2 and any(re.search(OBJECT,h,re.I) for h in heads):
            return 'MODEL', 'Native aircraft-type declaration corroborated by a definition of the named design subject'
    consumer_domains = {'smartphones','tablets','computers','desktop_computers','laptops','smartwatches','fitness_trackers','cameras','digital_cameras','game_consoles','camera_lenses','network_routers','network_switches','headphones','earbuds','television_sets','printers'}
    if domain in consumer_domains and re.search(r'[A-Z]', label or '') and not generic and any(re.search(OBJECT,h,re.I) for h in heads) and re.search(r'\b(?:manufactured|developed|produced|designed|marketed|made)\s+(?:and\s+\w+\s+)?by\s+[A-Z]',text):
        return 'MODEL', 'Named consumer product with a source-stated manufacturer identifies a design'
    if domain in consumer_domains and re.search(r'[A-Z]',label or '') and not generic and any(re.search(OBJECT,h,re.I) for h in heads):
        if re.search(OBJECT+r'\s+(?:by|from)\s+[A-Z]',description):
            return 'MODEL', 'Native description names a specific consumer product and its manufacturer'
        if re.search(r'\b(?:announced|released|introduced|unveiled|launched)\b',definition,re.I):
            return 'MODEL', 'Independent definition supplies a named consumer product launch history'
    return None, 'Retained subject definition does not independently settle design grain'
