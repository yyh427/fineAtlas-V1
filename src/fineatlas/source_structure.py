"""Source adapters for grounded local scopes, separate from world equivalence."""
from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path
import re
import zipfile

from .repair_candidate import RepairWriter, canonical, digest, apply_scope_operations


def file_record(path, uri):
    path = Path(path)
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'uri': uri}


class SourceGraphWriter(RepairWriter):
    release = 'v1.11.0rc1+native755.graph.20261013'


def apply_source_graph(database, expected_revision, plan_path):
    """New source concepts first; existing endpoint caches replay separately."""
    plan = json.loads(Path(plan_path).read_text())
    w = SourceGraphWriter(database, expected_revision=expected_revision)
    package = plan['package_id']
    if not w.begin(package, plan):
        w.c.close()
        return {'status': 'ALREADY_APPLIED', 'changed_rows': 0}
    try:
        for source in plan['source_files']:
            if hashlib.sha256(Path(source['path']).read_bytes()).hexdigest() != source['sha256']:
                raise ValueError('Frozen source changed: ' + source['path'])
        for node in plan['nodes']:
            proof = node['proof']
            eid = w.evidence(proof, uri=node['source_uri'], source=node['source'], claim='SOURCE_CONCEPT_SCOPE')
            if not w.add_node(node, evidence_id=eid):
                raise ValueError('New source scope UID already exists without package receipt')
        for link in plan['new_child_links']:
            if link['child_uid'] not in w.added_nodes:
                raise ValueError('Existing child connections must use reconciled cache stage')
            proof = link['proof']
            eid = w.evidence(proof, uri=link['source_uri'], source=link['source'], claim='SOURCE_CLASSIFICATION_SCOPE')
            w.add_relation(link['child_uid'], link['parent_uid'], link['relation'],
                           source=link['source'], evidence_id=eid, proof=proof)
        indexes = w.refresh_new_indexes()
        w.meta('searchable755_scope_rules', 'grounded-mixed-range-v1')
        result = w.finish({'status': 'APPLIED', 'new_source_concepts': len(plan['nodes']),
                           'new_concept_relations': len(plan['new_child_links']), 'index_changes': indexes})
        return result
    except Exception:
        w.c.rollback()
        raise
    finally:
        w.c.close()


def prepare_source_graph(atlas, root):
    """Compile source-specific evidence into normalized explicit operations."""
    root = Path(root)
    nodes, new_links, old_links, files = {}, [], [], {}

    def source(path, uri):
        item = file_record(path, uri)
        files[item['path']] = item
        return item

    def proof(basis, docs, **facts):
        return {'basis': basis, 'source_files': docs, 'retrieved_utc': '2026-10-13',
                'world_identity_assertion': False, 'scope_is_dataset_whitelist': False, **facts}

    def node(uid, label, domain, role, docs, **attrs):
        row = {'uid': uid, 'label': label, 'domain': domain, 'role': role,
               'rank': role.lower(), 'source': 'Publisher grounded source scopes',
               'source_uri': docs[0]['uri'], 'source_version': '20261013',
               'identity_scope': 'SOURCE_VERSION_CONCEPT', 'object_granularity': 'source_type_scope',
               'aliases': [], 'proof': proof('EXPLICIT_SOURCE_SCOPE', docs), **attrs}
        if uid in nodes and nodes[uid] != row:
            raise ValueError('Conflicting source concept')
        nodes[uid] = row
        return uid

    def link(child, parent, relation, docs, basis, **facts):
        claim = {'child_uid': child, 'parent_uid': parent, 'relation': relation,
                 'source': 'searchable755-source-20261013', 'source_version': '20261013'}
        p = proof(basis, docs, admitted_claims=[claim], **facts)
        op = {'op': 'add_relation', **claim, 'source_uri': docs[0]['uri'], 'proof': p}
        (new_links if child in nodes else old_links).append(op)

    # The labels remain full annotation combinations. Prefix scopes include all
    # recorded variants of that literal prefix; they are not OEM generations.
    car_uri = 'https://ai.stanford.edu/~jkrause/papers/dissertation.pdf'
    car_docs = [source('/data/yaoyuhan/stanford_cars/devkit/cars_meta.mat',
                       'https://ai.stanford.edu/~jkrause/cars/car_dataset.html'),
                source(root/'inputs/primary/frozen_author_dissertation.pdf', car_uri)]
    makes = ('AM General|Acura|Aston Martin|Audi|BMW|Bentley|Bugatti|Buick|Cadillac|Chevrolet|'
             'Chrysler|Daewoo|Dodge|Eagle|FIAT|Ferrari|Fisker|Ford|GMC|Geo|HUMMER|Honda|Hyundai|'
             'Infiniti|Isuzu|Jaguar|Jeep|Lamborghini|Land Rover|Lincoln|MINI|Maybach|Mazda|McLaren|'
             'Mercedes-Benz|Mitsubishi|Nissan|Plymouth|Porsche|Ram|Rolls-Royce|Scion|Spyker|Suzuki|'
             'Tesla|Toyota|Volkswagen|Volvo|smart').split('|')
    bodies = ('Cargo Van Minivan', 'Crew Cab', 'Extended Cab', 'Regular Cab', 'Quad Cab',
              'Club Cab', 'Cargo Van', 'Passenger Van', 'Wagon Van', 'SuperCab',
              'Convertible', 'Hatchback', 'Minivan', 'Sedan', 'Coupe', 'Wagon', 'SUV', 'Van')
    car_fields = []
    for n in atlas.con.execute("SELECT * FROM native_classes WHERE dataset='stanford_cars' ORDER BY CAST(class_id AS INTEGER)"):
        label = n['label']
        matches = [m for m in makes if label.startswith(m+' ')]
        if len(matches) != 1 or not re.search(r' \d{4}$', label):
            raise ValueError('Author make/year boundary requires manual review: ' + label)
        make, year = matches[0], label[-4:]
        tail = label[len(make)+1:-5]
        body = next((b for b in bodies if tail.endswith(' '+b)), None)
        design = tail[:-len(body)-1] if body else tail
        make_uid = 'stanford-cars-2013:make-scope:' + make.casefold()
        design_uid = 'stanford-cars-2013:design-label-scope:' + (make+' '+design).casefold()
        if make_uid not in nodes:
            node(make_uid, make+' vehicles [source make scope]', 'cars', 'CLASS', car_docs,
                 aliases=[make+' vehicles', make], object_granularity='source_make_scope')
            link(make_uid, 'wordnet31:03796768-n', 'IS_A', car_docs,
                 'PUBLISHER_ROAD_VEHICLE_SCOPE_AND_LITERAL_MAKE_PARTITION', make=make,
                 dissertation_zero_based_pages=[39,40,41], company_identity_is_not_asserted=True)
        if design_uid not in nodes:
            node(design_uid, make+' '+design+' [source design-label scope]', 'cars', 'CLASS', car_docs,
                 aliases=[make+' '+design], object_granularity='source_design_label_scope',
                 oem_model_or_trim_equivalence='UNKNOWN')
            link(design_uid, make_uid, 'IS_A', car_docs,
                 'LITERAL_SOURCE_LABEL_PREFIX_SCOPE_INCLUSION', make=make, design_label_prefix=design,
                 semantic_scope='Source-label predicate, not model generation or OEM trim identity')
        fields = {'make_literal': make, 'design_label_prefix': design, 'body_literal': body,
                  'year_literal': year, 'oem_trim_scope': 'UNKNOWN', 'original_label': label}
        car_fields.append({'uid': n['uid'], **fields})
        link(n['uid'], design_uid, 'DEPICTS_TYPE', car_docs,
             'AUTHOR_ANNOTATION_CATEGORY_REFERENCES_ITS_LITERAL_DESIGN_LABEL_SCOPE',
             class_id=n['class_id'], fields=fields, exact_world_configuration=False)
        for key, value in [('year', year), ('body', body)]:
            if not value:
                continue
            uid = 'stanford-cars-2013:attribute:'+key+':'+value.casefold()
            if uid not in nodes:
                node(uid, value+' [author '+key+' attribute]', 'cars', 'ATTRIBUTE', car_docs,
                     object_granularity='author_'+key+'_attribute')
            link(n['uid'], uid, 'HAS_ATTRIBUTE', car_docs, 'EXPLICIT_AUTHOR_LABEL_ATTRIBUTE', fields=fields)

    # Rejoin actual image-level author triples. A family/manufacturer conflict
    # remains multi-valued; it must not be resolved by string guessing.
    folder = Path('/data/yaoyuhan/FineAtlas-Eval/v1/cache/fgvc-aircraft-2013b/fgvc-aircraft-2013b/data')
    air_uri = 'https://www.robots.ox.ac.uk/~vgg/data/fgvc-aircraft/'
    air_docs = [source(folder/f'images_{k}_{s}.txt', air_uri)
                for s in ('train','val','test') for k in ('variant','family','manufacturer')]
    air_docs.append(source(root/'inputs/primary/fgvc_author.html', air_uri))
    families, variants = defaultdict(set), defaultdict(set)
    for split in ('train','val','test'):
        fields = {k: dict(line.split(' ',1) for line in (folder/f'images_{k}_{split}.txt').read_text().splitlines())
                  for k in ('variant','family','manufacturer')}
        if len(set(map(tuple, (x.keys() for x in fields.values())))) != 1:
            if not all(set(fields['variant']) == set(v) for v in fields.values()):
                raise ValueError('Author image annotation sets differ')
        for image, variant in fields['variant'].items():
            family, manufacturer = fields['family'][image], fields['manufacturer'][image]
            families[family].add(manufacturer)
            variants[variant].add((family,manufacturer))
    air_audit = []
    for family, manufacturers in sorted(families.items()):
        family_uid = 'fgvc-aircraft-2013b:family:'+family.casefold()
        if not atlas.node(family_uid):
            raise ValueError('Existing author family missing: '+family)
        for make in sorted(manufacturers):
            uid = 'fgvc-aircraft-2013b:manufacturer-type-scope:'+make.casefold()
            if uid not in nodes:
                node(uid, make+' aircraft [publisher manufacturer scope]', 'aircraft', 'CLASS', air_docs,
                     aliases=[make+' aircraft'], object_granularity='source_manufacturer_scope')
                link(uid,'wordnet31:02689427-n','IS_A',air_docs,
                     'AUTHOR_AIRCRAFT_MANUFACTURER_ANNOTATION_SCOPE', manufacturer=make)
            # Only unanimous author triples support the whole family inclusion.
            if len(manufacturers) == 1:
                link(family_uid,uid,'DESIGN_TYPE_OF',air_docs,
                     'UNANIMOUS_AUTHOR_FAMILY_MANUFACTURER_TRIPLES', family=family,manufacturer=make)
        air_audit.append({'family':family,'manufacturers':sorted(manufacturers),
                          'whole_family_connection_supported':len(manufacturers)==1})

    # Stanford Dogs IDs refer to WordNet3.0, not same-offset WordNet3.1. Retain
    # the original sense namespace and its explicit hypernym pointer records.
    archive = root/'inputs/primary/wordnet30_nltk.zip'
    wn_docs = [source(archive,'https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip')]
    wn_uri = 'https://wordnet.princeton.edu/download/current-version'
    with zipfile.ZipFile(archive) as z:
        raw = z.read('wordnet/data.noun').decode()
        license_text = z.read('wordnet/LICENSE').decode()
        if '3.0' not in raw[:5000] or 'Princeton' not in license_text:
            raise ValueError('Unexpected WordNet release or provenance')
    senses = {}
    for line in raw.splitlines():
        if not line or not line[0].isdigit():
            continue
        head, gloss = line.split('|',1); tokens=head.split(); count=int(tokens[3],16)
        words=[tokens[4+2*i] for i in range(count)]; pos=4+2*count; pointers=int(tokens[pos]);pos+=1
        parents=[tokens[pos+4*i+1] for i in range(pointers) if tokens[pos+4*i]=='@' and tokens[pos+4*i+2]=='n']
        senses[tokens[0]]={'offset':tokens[0],'lemmas':words,'gloss':gloss.strip(),
                           'parents':parents,'raw_record':line,'raw_record_sha256':hashlib.sha256(line.encode()).hexdigest()}
    canine = [k for k,v in senses.items() if 'canine' in v['lemmas'] and 'nonretractile claws' in v['gloss']]
    if len(canine)!=1:raise ValueError('Canine source sense ambiguous')
    canine=canine[0];known=atlas.node('wordnet31:02085998-n')
    if known['description'].strip()!=senses[canine]['gloss']:
        raise ValueError('Cross-version broad canine sense not identical; review required')
    dog_bindings=[]; needed=set();paths={}
    for n in atlas.con.execute("SELECT * FROM native_classes WHERE dataset='stanford_dogs'"):
        original=json.loads(n['proof'])['increment_native_record']['raw_record'];syn=original['native_synset'].removeprefix('n')
        queue=deque([(syn,[])]);seen=set();found=None
        while queue:
            uid,path=queue.popleft()
            if uid in seen:continue
            seen.add(uid)
            if uid==canine:found=path+[uid];break
            if uid not in senses:raise ValueError('Original synset missing from3.0')
            queue.extend((p,path+[uid]) for p in senses[uid]['parents'])
        if not found:raise ValueError('Canid source class lacks original taxonomy path')
        needed.update(found);paths[syn]=found
        dog_bindings.append({'uid':n['uid'],'class_id':n['class_id'],'synset':syn,'path':found})
    for syn in sorted(needed):
        rec=senses[syn];uid='wordnet30-source:'+syn+'-n'
        node(uid,rec['lemmas'][0].replace('_',' ')+' [WordNet3.0 sense]', 'animals','CLASS',wn_docs,
             source='Princeton WordNet3.0',source_uri=wn_uri,source_version='3.0',
             aliases=[x.replace('_',' ') for x in rec['lemmas']],definition=rec['gloss'],
             object_granularity='lexical_canid_type',source_synset=rec)
    for syn in sorted(needed):
        uid='wordnet30-source:'+syn+'-n'
        if syn==canine:
            link(uid,'wordnet31:02085998-n','IS_A',wn_docs,
                 'CROSS_VERSION_IDENTICAL_FULL_BROAD_SENSE_INCLUSION', original=senses[syn],
                 target_uid=known['uid'],target_gloss=known['description'],target_source=known['source'])
        else:
            for parent in senses[syn]['parents']:
                if parent in needed:
                    link(uid,'wordnet30-source:'+parent+'-n','IS_A',wn_docs,
                         'ORIGINAL_WORDNET30_EXPLICIT_HYPERNYM_POINTER',original=senses[syn],parent_record=senses[parent])
    for b in dog_bindings:
        link(b['uid'],'wordnet30-source:'+b['synset']+'-n','DEPICTS_TYPE',wn_docs,
             'DATASET_ORIGINAL_SYNSET_SCOPE_REFERENCE',native_source=atlas.native_class('stanford_dogs',b['class_id'])['proof'],
             source_synset=senses[b['synset']],exact_world_equivalence_not_derived=True)

    # Original pet species fields are explicit, unlike inference from breed text.
    pet_uri='https://www.robots.ox.ac.uk/~vgg/data/pets/'
    pet_docs=[source('/data/yaoyuhan/Pet-37/annotations/README',pet_uri),
              source('/data/yaoyuhan/Pet-37/annotations/test.txt',pet_uri),
              source('/data/yaoyuhan/Pet-37/annotations/trainval.txt',pet_uri),
              source(root/'inputs/primary/pets_author.html',pet_uri)]
    species=defaultdict(set)
    for name in ['test.txt','trainval.txt']:
        for line in Path('/data/yaoyuhan/Pet-37/annotations',name).read_text().splitlines():
            if line and not line.startswith('#'):
                _,cid,sp,_=line.split();species[cid].add(sp)
    pet_audit=[]
    for n in atlas.con.execute("SELECT * FROM native_classes WHERE dataset='pets37'"):
        sp=species[n['class_id']]
        if len(sp)!=1 or not sp<={'1','2'}:raise ValueError('Pet species code is ambiguous')
        parent='wordnet31:02124460-n' if sp=={'1'} else 'wordnet31:02086723-n'
        link(n['uid'],parent,'DEPICTS_TYPE',pet_docs,'UNANIMOUS_ORIGINAL_PET_SPECIES_FIELD',species_code=list(sp)[0],
             original_class_id=n['class_id'],readme_count_typo_not_used_for_species_identity=True)
        world=atlas.world_mapping_status('pets37',n['class_id'])
        if world['world_identity_verified']:
            link(world['uid'],parent,'IS_A',pet_docs,'CONFIRMED_BREED_SCOPE_WITH_UNANIMOUS_ORIGINAL_SPECIES_FIELD',
                 mapping_evidence_ids=world['evidence_ids'],world_uid=world['uid'],species_code=list(sp)[0])
        pet_audit.append({'class_id':n['class_id'],'species_code':list(sp)[0],'parent':parent})
    plan={'package_id':'searchable755-source-concepts-v1','source_files':list(files.values()),
          'nodes':list(nodes.values()),'new_child_links':new_links}
    return plan,old_links,{'car_fields':car_fields,'air_families':air_audit,'air_variant_ranges':{k:sorted(v) for k,v in variants.items()},
                            'dog_synset_bindings':dog_bindings,'pets_species_fields':pet_audit}
