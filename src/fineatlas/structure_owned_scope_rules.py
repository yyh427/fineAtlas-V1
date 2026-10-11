"""Guard own first-subject physical genera without interpreting KB hints.

Modifiers describe a whole physical design. A related, derived or replaced
object in a trailing clause cannot supply the design's genus. Source classes
retain their complete sense and powered/unpowered distinctions.
"""
from __future__ import annotations
import re
from .structure_subject_scope_rules import scoped_subject_genus, GENERAL_MODIFIERS

MODIFIERS = GENERAL_MODIFIERS | frozenset('much modified long career configuration and or united states bay assault towed competition performance weight sports artillery acrobatic miniature miniature built kit pod boom strut braced tail tailed FAI class standard one launched self launch reverse staggered tricycle gear gull engined long distance narrow gap bay lifting span early unfinished general purpose amateur metre meter sport place amateur-built designation prototypes unused original simple small seater place engined wings national projected multirole long haul mailplanes amphibian tourer multirole personnel torpedo jetted Swedish company second performance licensing training distance created second racer night artillery civilian original projected unfinished ordinary common model models design designs family series transport racer mailplane mailplanes tourer purpose prototype prototypes rescue regional propeller jet turboprop narrowbody widebody airliners passenger seat single-seater five-seat one-design high-speed low-powered training single-bay equal-span three-engined pusher-engined winged scope comma designed made trainer very us west east long range kit narrow gap torpedo span powered launched launch metre meter lsa fai tail tailed taildragger equipment equipped sports amateur seat seater class carrier distance bay multi multi-purpose multirole haul office monoplane monoplanes military light civilian electric electricity two-bay configuration amphibious mailplane mailplanes tourer touring trainer trainers transport project launched aircraft jet taildragger'.split()) | frozenset('japanese german french british american russian soviet canadian australian italian spanish swiss swedish dutch norwegian danish finnish polish czech czechoslovak hungarian romanian portuguese serbian yugoslav chinese brazilian argentinian israeli ukrainian south korean north indonesian indian malaysian egyptian icelandic intended prototype prototypes planned proposed project experimental demonstration demonstrator observation reconnaissance surveillance patrol training trainer touring advertising cabin sport light sporting utility agricultural multipurpose multi purpose primary secondary naval navy civil civilian commercial executive business military ambulance rescue transport commuter regional powered jet piston turbine turboprop turboshaft gas diesel gasoline petrol engine engines seat seats seating passenger passengers freight cargo propeller propellers sail motor glider parasol wing wings winged shoulder lifting conventional flying float hull high low mid medium powered power all metal wooden composite cantilever semi sesquiplane water waterborne attack combat fighter bomber interceptor reconnaissance scout trainer aerobatic night day modular single twin triple four six eight open cockpit enclosed advanced supersonic subsonic homebuilt ultralight ultra short take off landing VTOL STOL rotary remote controlled unmanned uncrewed robot robotic coaxial pusher canard tailless delta swept forward backward tractor pure rigid semi-rigid non-rigid rigid-hulled powered-lift purpose built award winning second third fourth fifth standard fast first early late decade century world war interwar post pre onetime unsuccessful never-produced production design version maritime aeronautical jet-propelled jet-powered'.split())
MODIFIERS |= frozenset('trial trials test company s five gun t equal carrying unusual compound microlift microlight aerobatics hauling mail speed farman type pitcairn launching dragger'.split())
FINE = (
 (r'jet (?:airliner|airplane)(?:\s+(?:family|series|model))?', 'wordnet31:03601053-n'),
 (r'(?:twin[ -]turboprop|turboprop)(?:\s+(?:[0-9]+[ -]passenger|commuter|regional))*\s+(?:airliner|airplane)(?:\s+(?:family|series|model))?', 'wordnet31:04018858-n'),
 (r'twinjet\s+(?:airliner|airplane|aircraft)(?:\s+(?:family|series|model))?', 'wordnet31:04510794-n'),
 (r'(?:jets?|jet aircraft|jet trainer(?: aircraft)?(?: design)?|jet fighter(?: aircraft)?|jet bomber(?: aircraft)?)(?:\s+(?:family|series|model|design studies))?', 'wikidata:Q206592'),
 (r'(?:motor[ -]glider|motorglider)(?:\s+(?:designs?|aircraft)|\s+and ultralight aircraft)?', 'wikidata:Q1930290'),
 (r'(?:gliders?|sailplanes?)(?:\s+(?:designs?|aircraft))?', 'wikidata:Q2165278'),
 (r'(?:autogyro|autogiro|gyroplane|gyrocopter)(?:\s+(?:designs?|aircraft))?', 'wikidata:Q208708'),
 (r'(?:airship|dirigible)(?: aircraft)?', 'wikidata:Q133585'),
 (r'(?:flying boat)(?: (?:fighter|aircraft|ultralight(?: and light-sport)? aircraft))?', 'wikidata:Q1153376'),
 (r'(?:seaplane|floatplane)(?: aircraft)?', 'wikidata:Q115940'),
 (r'biplanes?(?:\s+(?:observation |trainer |fighter |bomber |naval |torpedo |training |reconnaissance |scout )*(?:aircraft|fighter|bomber|floatplanes?|seaplane|glider|designs?|prototype|mailplanes?|kit aircraft|ultralight aircraft|trainer(?:/tourer)? aircraft|sports flying boat|long-range bomber|bomber-transport|trainer|passenger aircraft|transport design))?', 'wikidata:Q223818'),
 (r'monoplanes?(?:\s+(?:(?:night |fighter |bomber |reconnaissance |and )*)(?:aircraft|fighter|bomber|glider|designs?|prototype|transport design|racing aircraft|racer|kit aircraft|light multipurpose aircraft|sports flying boat|amphibian tourer))?', 'wikidata:Q627537'),
 (r'triplane', 'wikidata:Q106459641'),
 (r'helicopter(?:\s+(?:family|series|model|design))?', 'wikidata:Q34486'),
 (r'(?:airplane|aeroplane)(?:\s+design)?', 'wordnet31:02694015-n'),
 (r'fixed-wing aircraft(?:\s+design)?', 'wikidata:Q2875704'),
 (r'(?:aircraft|rotorcraft)(?: (?:family|series|model|version|designs?|prototypes?))?', 'wordnet31:02689427-n'),
)

def words(value):return re.findall(r'[^\W_]+',value.casefold(),re.UNICODE)

def own_first_kind(statement,label,source_names=()):
    text=statement.strip()
    # Remove nested parenthetical name annotations without truncating a
    # designation such as F.E.3 before its copula.
    for _ in range(6):
        cleaned=re.sub(r'\([^()]*\)','',text)
        if cleaned==text:break
        text=cleaned
    text=re.sub(r'\([^)]*$', '',text) if '(' in text and not re.search(r'\b(?:is|was|are|were)\b',text) else text
    # Remove only ordinary same-subject name annotations, not range clauses.
    text=re.sub(r',\s*(?:previously|originally) (?:designated|known as|called) [^,]+,','',text,flags=re.I)
    m=re.search(r'\b(?:is|was|are|were)\b\s+',text,re.I)
    if m:
        prefix=re.sub(r'^(?:the|an?)\s+','',text[:m.start()].strip(),flags=re.I)
        prefix=re.sub(r'\([^)]*$', '', prefix).strip()
        prefix=re.sub(r',?\s+(?:often |also )called\s+[^,]+$', '',prefix,flags=re.I).strip(' ,')
        if words(prefix)!=words(label):
            wanted=words(label);present=words(prefix)
            alias_prefix=bool(re.match(re.escape(label)+r'\s*,?\s+(?:or|also called|also known as|sometimes called|previously designated|referred to)\b',prefix,re.I))
            leading_company=bool(len(present)>len(wanted)and present[-len(wanted):]==wanted and not re.search(r'\b(?:of|from|for|based|derived|replaced|including|contains|version|family)\b',prefix,re.I)and all(t[0].isupper()for t in prefix.split()[:-len(label.split())]))
            coordinated_names=bool(wanted and ' '.join(wanted)in ' '.join(present)and re.search(r'[,]|\b(?:and|or)\b',prefix,re.I)and not re.search(r'\b(?:of|from|based|derived|replaced|predecessor|successor|ancestor|including|contains)\b',prefix,re.I))
            # Proper-name appositions are part of the owned named subject,
            # never a related family/model phrase or lowercase type noun.
            suffix=prefix[len(label):].strip(' ,') if prefix.casefold().startswith(label.casefold()) else ''
            named_suffix=bool(suffix and len(suffix.split())<=4 and all(re.fullmatch(r'[A-Z][A-Za-z]*|"[A-Z][A-Za-z]*"',t)for t in suffix.split()) and not re.search(r'\b(?:Family|Series|Model|Version|MAX|Neo|Mark|Mk)\b',suffix,re.I))
            bound_source_name=any(words(prefix)==words(name) or (prefix.startswith(name+' ') and all(re.fullmatch(r'[A-Z][a-zA-Z]+',token) for token in prefix[len(name):].split()) and not re.search(r'\b(?:family|series|model|version|MAX|Neo)\b',prefix[len(name):],re.I))for name in source_names)
            repeated_subject=bool(prefix.startswith(label+' The ') and len(prefix.split(' The ',1)[1].split())<=5 and not re.search(r'\b(?:of|from|for|family|version|part)\b',prefix,re.I))
            annotated_label=re.fullmatch(r'(.+?)\s*\(([^()]+)\)',label)
            explicit_alias=re.fullmatch(r'(.+?)\s*,\s*also known as (?:the )?(.+?)\s*,?',prefix,re.I)
            parenthetical_alias=False
            if annotated_label and explicit_alias:
                base=words(annotated_label[1]);alternate=words(annotated_label[2]);first=words(explicit_alias[1]);alias=words(explicit_alias[2])
                parenthetical_alias=bool(base==alias and first and alternate and first[-len(alternate):]==alternate and first[0]==base[0] and not re.search(r'\b(?:family|series|version|model|neo|max)\b',annotated_label[2],re.I))
            if not(alias_prefix or leading_company or coordinated_names or named_suffix or repeated_subject or bound_source_name or parenthetical_alias):return None
        text=text[m.end():]
    text=re.split(r'[.;]\s+(?=[A-Z])',text,maxsplit=1)[0]
    text=re.sub(r'^(?:an?|the)\s+','',text,flags=re.I)
    text=re.sub(r'^(?:family|series|line|range|type|kind|class)\s+of\s+','',text,flags=re.I)
    transformed=re.match(r'[^.]*\bdevelopment of\s+.+?\s+into\s+(an? .+)$',text,re.I)
    if transformed:text=transformed[1]
    text=re.sub(r'^(?:the )?(?:first|one|second) of (?:an? )?(?:series|family) of\s+','',text,flags=re.I)
    # Manufacturing adjectives before the genus differ from trailing
    # manufacturing clauses; keep the following own noun phrase.
    text=re.sub(r'\bdesigned and built\s+(?=single|two|three|four|[a-z]+-wing)','',text,flags=re.I)
    text=re.sub(r'\bamateur built(?=\s+aircraft)', 'amateur-built',text,flags=re.I)
    text=re.sub(r'\bdesigned\s+(?=biplane|monoplane|helicopter|airplane)','',text,flags=re.I)
    # A comma apposition may restate the own head more specifically, while
    # relative clauses merely describing other objects remain excluded.
    app=re.match(r'[^,]*\baircraft(?:\s+(?:built|produced|manufactured)\s+by [^,]+)?,\s+(an? [^,]+)',text,re.I)
    if app:text=app[1]
    text=re.split(r',\s+(?:the |an? further |powered|intended|capable)',text,maxsplit=1,flags=re.I)[0]
    text=re.split(r'\s+(?:that|which|whose|with|without|for|to|by|from|in|as|built|designed|developed|manufactured|produced|introduced|intended|featuring|derived|based|replacing|being|used|ordered|seating|capable|created|much modified|made|of|proposed)\b',text,maxsplit=1,flags=re.I)[0].strip(' ,. ')
    text=re.sub(r'\s+and$','',text)
    text=re.sub(r'^(?:an?|the)\s+','',text,flags=re.I)
    if re.search(r'\b(?:toy|model of|scale model|parts? of|engine for|fictional|virtual|imaginary|not|never|nonphysical|fake|replica)\b',text,re.I):return None
    return text

def owned_physical_genus(statement,label,source_names=()):
    head=own_first_kind(statement,label,source_names)
    if head:
        mixed=re.fullmatch(r'(.*?)\bglider and motor glider',head,re.I)
        if mixed and all(v in MODIFIERS or v.isdigit() for v in words(mixed[1])):
            return 'glider and motor glider','wikidata:Q2165278'
        # "biplane, single-engine homebuilt aircraft" declares one own
        # physical head with a same-object comma apposition.
        app=re.fullmatch(r'(biplane|monoplane|helicopter|glider),\s+(.+) aircraft',head,re.I)
        if app and all(t in MODIFIERS or t.isdigit()for t in words(app[2])):
            head=app[1]
        for pattern,parent in FINE:
            if parent=='wordnet31:02689427-n':continue
            m=re.search(r'\b('+pattern+r')$',head,re.I)
            if not m:continue
            prefix=head[:m.start()].strip(' ,-/')
            tokens=words(prefix)
            if any(not(v in MODIFIERS or re.fullmatch(r'\d+(?:s|th|st|nd|rd)?',v))for v in tokens):continue
            slash_scope=re.sub(r'\b\d+/\d+-seat\b|trainer/tourer','',head,flags=re.I)
            if '/'in slash_scope or (re.search(r'\b(?:and|or)\b',prefix,re.I)and re.search(r'\b(?:airship|glider|helicopter|biplane|monoplane|airplane)\b',prefix,re.I)):continue
            if parent in {'wikidata:Q133585','wikidata:Q206592','wordnet31:04510794-n'}and re.search(r'\b(?:unpowered|nonpowered|non-powered)\b',head,re.I):continue
            return m[1],parent
    # An own nominal subject can explicitly carry its physical noun phrase
    # before a historical copula (e.g. 'the X glider was a development ...').
    subject=re.sub(r'\([^()]*\)','',statement).strip()
    copula=re.search(r'\b(?:is|was|are|were)\b\s+',subject,re.I)
    if copula and not re.search(r'\b(?:fictional|virtual|toy|model of|not real|replica|imaginary)\b',subject[:copula.end()+80],re.I):
        prefix=re.sub(r'^(?:the|an?)\s+','',subject[:copula.start()].strip(),flags=re.I)
        match=re.match(re.escape(label)+r'\s+(.+)$',prefix,re.I)
        if match:
            noun=match[1].strip();nested=owned_physical_genus(noun,label)
            if nested and nested[1]!='wordnet31:02689427-n':return nested
    # Preserve the previously checked restrictive grammar for ordinary kinds.
    result=scoped_subject_genus(re.sub(r'\b(wide|narrow)body\b',r'\1-body',statement,flags=re.I),label)
    if result and result[1]=='wordnet31:02694015-n'and head and re.search(r'\b(?:unpowered|nonpowered|non-powered)\b',head,re.I):return None
    if result:return result
    if head and re.search(r'\b(?:aircraft|rotorcraft)(?: (?:family|series|model|version|designs?|prototypes?))?$',head,re.I):
        m=re.search(r'\b(?:aircraft|rotorcraft)(?: (?:family|series|model|version|designs?|prototypes?))?$',head,re.I);prefix=head[:m.start()];tokens=words(prefix)
        if all(v in MODIFIERS or re.fullmatch(r'\d+(?:s|th|st|nd|rd)?',v)for v in tokens):return m[0],'wordnet31:02689427-n'
    return None


def owned_reconfigurable_fixed_wing(statement,label):
    """Both explicitly declared structural options share fixed-wing scope."""
    head=own_first_kind(statement,label)
    if not head or not re.search(r'\baircraft\b',head,re.I):return False
    return bool(re.search(r'\bcould fly either as a biplane or as a (?:parasol (?:winged |wing )?)?monoplane\b',statement,re.I))


def owned_named_instance_genus(statement,label):
    """A named one-of-N physical example inherits its stated design kind.

    Merely building one prototype is not evidence that the design concept
    itself is an instance. The own name must identify the individual member.
    """
    member = re.search(r'\bOne of them\s*[—–-]\s*(?:the )?'+re.escape(label)+r'\s*[—–-]',statement,re.I)
    if not member or not re.search(r'\b(?:Two|Three|Four|\d+) examples were built\.',statement[:member.start()],re.I):return None
    first=statement.split('.',1)[0]
    copula=re.search(r'\b(?:is|was)\s+',first,re.I)
    if not copula:return None
    design=re.sub(r'^The\s+','',first[:copula.start()].strip(),flags=re.I)
    if words(design)==words(label):return None
    return owned_physical_genus(first,design)


def bound_owned_source_names(data,label,statement):
    """Titles supply spelling evidence only within the named own concept.

    An article about a different design, including the label as one of its
    instances, is not an alias of that individual source object.
    """
    record=data.get('evidence_record',{})
    if record.get('wikipedia_redirect_chain'):return []
    label_words=words(label)
    output=[]
    for name in (data.get('enwiki_title'),record.get('wikipedia_title'),record.get('enwiki_title')):
        if not isinstance(name,str)or name in output:continue
        title_words=words(name)
        # Numeric variants cannot expand a family/base design by name alone.
        if title_words==label_words or (len(title_words)==len(label_words)+1 and title_words[:len(label_words)]==label_words and title_words[-1].isalpha()):output.append(name)
        # An explicit company-model designation connects a source spelling
        # to the own base-design name; a mere article title cannot do this.
        parenthetical=re.search(r'\(\s*company model\s+([^()]+)\)',statement,re.I)
        if parenthetical and label_words and title_words and title_words[0]==label_words[0] and words(parenthetical[1])==label_words[1:] and name not in output:
            output.append(name)
    return output


def owned_motor_vehicle_design_scope(statement,label,source_names=()):
    head=own_first_kind(statement,label,source_names)
    if not head or re.search(r'\b(?:rail|railway|railroad|toy|virtual|fictional|imaginary|replica|scale|not)\b',head,re.I):return False
    return bool(re.search(r'\b(?:cars?|automobiles?|sportscars?)(?:\s+(?:model|family|series))?$',head,re.I))


def owned_role_scope(statement,label):
    """Normalize declared source grain independently of a peer's role."""
    if owned_named_instance_genus(statement,label):return 'INSTANCE'
    head=own_first_kind(statement,label)
    if not head:return None
    if re.search(r'\b(?:cultivar|grape variety)\b',head,re.I):return 'BIOLOGICAL_VARIANT'
    if re.search(r'\bmodified example\b',head,re.I):return 'UNKNOWN'
    if re.search(r'\b(?:prototype|trainer|target) series\b',head,re.I):return 'MODEL_FAMILY'
    if re.search(r'\b(?:version|variant|conversion)\b|\b(?:system|transport|car) model\b|\bthird-generation\b',head,re.I):return 'MODEL'
    if re.search(r'\btest and trials prototype\b',head,re.I):return 'MODEL'
    if head and re.search(r'\bloitering munition\b',head,re.I)and re.search(r'\bproduced .+? by\b',statement,re.I):return 'MODEL'
    return None


def owned_universal_variant_genus(statement,label):
    """A reviewed whole family paragraph may declare all variants' geometry."""
    first=re.split(r'[.;]\s+(?=[A-Z])',re.sub(r'\([^()]*\)','',statement),maxsplit=1)[0]
    m=re.search(r'\b(?:is|was|are|were)\b\s+',first,re.I)
    if not m:return None
    prefix=re.sub(r'^(?:the|an?)\s+','',first[:m.start()].strip(),flags=re.I)
    if not words(label) or ' '.join(words(label))not in ' '.join(words(prefix))or not re.search(r'\bfamily of aircraft\b',first[m.end():],re.I):return None
    # This is a whole family universal, never a description of one sample.
    clauses=re.findall(r'(?:^|[.;]\s+)All variants (?:were|are) ([^.]+)',statement,re.I)
    if len(clauses)!=1:return None
    return owned_physical_genus(clauses[0],label)


def owned_self_twinjet_scope(statement,label):
    """Whole named aircraft/family describes itself as the twinjet.

    A different named aircraft declared before the anaphor blocks inheritance.
    Engine attributes of a related variant alone are not this predicate.
    """
    head=own_first_kind(statement,label)
    if not head or not re.search(r'\b(?:aircraft|airliners?)(?: family| series)?$',head,re.I):return False
    flat=re.sub(r'\([^()]*\)','',statement)
    m=re.search(r'(?:^|[.;]\s+|,\s+)the twinjet\s+(?:has|had|features|featured|retained)\b',flat,re.I)
    if not m:return False
    tail=re.split(r'[.;]\s+(?=[A-Z])',flat,maxsplit=1)
    between=flat[len(tail[0]):m.start()]
    if re.search(r'\b(?:is|was|are|were)\s+(?:an?\s+)?(?:twinjet|jet aircraft|jet airliner|jet airplane)\b',between,re.I):return False
    return True


def owned_multi_generation_programme_scope(statement, label, review):
    """A whole named programme contains separately stated early/later generations."""
    if review.get('own_programme_name') != label or review.get('programme_definition') != statement:
        return False
    initial=review['initial_generations_clause'];later=review['later_generation_clause']
    if initial not in statement or later not in statement:
        return False
    tokens=words(label);short=tokens[-1] if tokens else ''
    return bool(short and re.fullmatch(r'The initial (?:three|four|five|six|[3-9]) generations of the '+re.escape(short)+r' were produced from [0-9]{4} to [0-9]{4}\.',initial,re.I) and re.fullmatch(r'The (?:fourth|fifth|sixth|seventh) generation has been produced since .+\.',later,re.I) and re.search(r'\bmanufactured and developed by\b',statement[:statement.find(initial)],re.I) and not re.search(r'\b(?:fictional|virtual|toy|scale replica)\b',statement[:statement.find(initial)],re.I))
