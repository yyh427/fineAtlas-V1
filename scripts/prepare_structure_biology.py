#!/usr/bin/env python3
"""Prepare replayable biological scope fixes from protected source snapshots.

No production writes, photographs, visual classifiers or inferred identity
merges occur. Frozen source labels, world mappings and task scope stay separate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fineatlas.structure_biology import (
    SCHEMA, INPUT_NAME, LINK_INPUT_NAME, canonical_json, corroborated_species_rank,
    digest, validate_payload, explicit_scientific_senses,
)

FLOWERS_URI = 'https://www.robots.ox.ac.uk/~vgg/data/flowers/102/categories.html'
CUB_URI = 'https://www.vision.caltech.edu/datasets/cub_200_2011/'
PLANT = 'wordnet31:00017402-n'
BIRD = 'wordnet31:01505702-n'


def freeze_scientific_senses(database, sources):
    """Bounded whole-WordNet pattern scan with one WFO native field lookup.

    This scans a UID prefix once rather than expanding millions of ancestries
    per label. Scientific names only supply native rank corroboration.
    """
    c = sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1', uri=True)
    c.row_factory = sqlite3.Row
    rows, names, checked = [], set(), 0
    for r in c.execute("""SELECT n.* FROM nodes n LEFT JOIN node_taxon_ranks r ON r.uid=n.uid
      WHERE n.uid GLOB 'wordnet31:*' AND n.visibility='ACTIVE' AND r.uid IS NULL"""):
        checked += 1
        scientific = explicit_scientific_senses(dict(r))
        if scientific:
            rows.append(dict(r)); names.update(scientific)
    native = [dict(r) for r in c.execute(
        "SELECT uid,label,rank,source,data FROM nodes WHERE uid GLOB 'wfo:*' "
        "AND visibility='ACTIVE' AND label IN ("+','.join('?' for x in names)+')', sorted(names))]
    sources.mkdir(parents=True, exist_ok=True)
    for name, data in [('wordnet_scientific_sense_cohort.json', rows),
                       ('wfo_scientific_sense_cohort.json', native)]:
        (sources/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    manifest = {'wordnet_missing_assertion_nodes_checked':checked,
        'scientific_sense_nodes':len(rows), 'scientific_sense_names':len(names),
        'corroborating_native_wfo_rows':len(native),
        'scope':'All active WordNet scientific senses lacking node_taxon_ranks; '
        'native WFO field rank only; no equality or dataset range inferred'}
    (sources/'scientific_sense_scan_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    c.close()
    return manifest


def prepare(database, baseline, sources, output):
    c = sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    output.mkdir(parents=True, exist_ok=True)
    reports = output.parent / 'reports'
    reports.mkdir(parents=True, exist_ok=True)
    label_rows = json.loads((baseline / 'labels.json').read_text())
    analysis = json.loads((baseline / 'analysis.json').read_text())
    native_taxa = json.loads((sources / 'wfo_scope_candidates.json').read_text())
    scientific_cohort = json.loads((sources / 'wordnet_scientific_sense_cohort.json').read_text())
    native_taxa = list({row['uid']: row for row in native_taxa +
        json.loads((sources / 'wfo_scientific_sense_cohort.json').read_text())}.values())
    primary = json.loads((sources / 'reviewed_primary_scope_facts.json').read_text())
    facts = {row['dataset_label']: row for row in primary['facts']}
    manifests = [row for name in ('fetch_manifest.json', 'additional_fetch_manifest.json', 'cub_fetch_manifest.json')
                 for row in json.loads((sources / name).read_text())]
    source_by_name = {row['name']: row for row in manifests}
    for row in manifests:
        if row.get('sha256'):
            actual = hashlib.sha256((sources / row.get('filename',row['name'] + '.html')).read_bytes()).hexdigest()
            if actual != row['sha256']:
                raise ValueError('Primary source snapshot changed')
    flower_source = source_by_name['oxford_flowers_categories']
    # The official page contains all original labels, including the questioned
    # pink-yellow category. Preserve the native label rather than replacing it
    # with the official organization's attribute identifier.
    html = (sources / 'oxford_flowers_categories.html').read_text().casefold()
    flowers = [r for r in label_rows if r['dataset'] == 'flowers102']
    def author_label(label):
        parts = label.split()
        # Preserve the inherited display label separately. The official page
        # independently contains the one-token category; no ontology mapping
        # changes are inferred from this documented duplicate-token typo.
        if len(parts) == 2 and parts[0] == parts[1] and parts[0].casefold() in html:
            return parts[0]
        return label
    if len(flowers) != 102 or any(author_label(r['label']).casefold() not in html for r in flowers):
        raise ValueError('Oxford primary category cohort differs from retained labels')
    retained = {}
    def node(uid):
        n = c.execute('SELECT * FROM nodes WHERE uid=?', (uid,)).fetchone()
        if not n or n['visibility'] != 'ACTIVE':
            raise ValueError('Inactive/missing biological endpoint: ' + uid)
        retained[uid] = {key: n[key] for key in ('uid', 'label', 'source', 'rank')}
        retained[uid]['data_sha256'] = hashlib.sha256(n['data'].encode()).hexdigest()
        return dict(n)
    node(PLANT); node(BIRD)
    def native_genus(name):
        found = [n for n in native_taxa if n['label'] == name and n['rank'] == 'genus']
        if len(found) != 1:
            raise ValueError('Genus has no unique retained native scope: ' + name)
        node(found[0]['uid'])
        return found[0]['uid']
    rank_repairs, mapping_reviews, native_labels, flowers_audit, cub_audit = [], [], [], [], []
    rank_reviews = []
    rank_by_uid = {}
    # Only explicit WordNet scientific senses receive rank corroboration. A
    # common label alone cannot turn a garden or colour class into a species.
    for frozen_scientific in scientific_cohort:
        n = frozen_scientific
        current = c.execute('SELECT * FROM nodes WHERE uid=?', (n['uid'],)).fetchone()
        if not current or dict(current) != n:
            raise ValueError('Frozen whole-WordNet scientific sense changed')
        if n['source'] == 'wordnet31':
            proof = corroborated_species_rank(n, native_taxa)
            if proof:
                node(n['uid'])
                native = proof['corroborating_native_records']
                for row in native: node(row['uid'])
                before = c.execute('SELECT * FROM node_taxon_ranks WHERE uid=?', (n['uid'],)).fetchone()
                proof.update(basis='SOURCE_EXPLICIT_SCIENTIFIC_SENSE_WITH_UNIQUE_NATIVE_SPECIES_RANK',
                    source_uri='https://wordnet.princeton.edu/',
                    wordnet_record_sha256=retained[n['uid']]['data_sha256'],
                    native_snapshot='Frozen existing WFO source UID/name/rank declarations',
                    native_snapshot_sha256=hashlib.sha256((sources / 'wfo_scientific_sense_cohort.json').read_bytes()).hexdigest(),
                    license='WordNet 3.1 license and original WFO attribution retained',
                    scope='Rank of the lexical scientific sense only; not a dataset scope or identity assertion')
                rank = {'uid': n['uid'], 'rank': 'species',
                        'before_rank': dict(before) if before else None, 'proof': proof}
                rank_repairs.append(rank); rank_by_uid[n['uid']] = rank
            else:
                senses = explicit_scientific_senses(n)
                candidates = [row for row in native_taxa if row['label'] in senses]
                by_name = {}
                for row in candidates: by_name.setdefault(row['label'], []).append(row)
                if (len({row['uid'] for row in candidates}) > 1 and by_name
                        and all(len(rows) == 1 and rows[0]['rank'] == 'species'
                                for rows in by_name.values())):
                    node(n['uid'])
                    for row in candidates: node(row['uid'])
                    prior = c.execute('SELECT * FROM node_taxon_ranks WHERE uid=?', (n['uid'],)).fetchone()
                    rank_reviews.append({'uid': n['uid'], 'label': n['label'],
                        'rank': None, 'entity_disposition': 'PRESERVE',
                        'before_rank': dict(prior) if prior else None, 'proof': {
                        'basis': 'LEXICAL_SYNSET_DOES_NOT_PROVE_MODERN_SPECIES_SCOPE_EQUIVALENCE',
                        'source_uri': 'https://wordnet.princeton.edu/',
                        'scientific_senses': senses,
                        'native_scope_candidates': sorted(candidates, key=lambda row: row['uid']),
                        'wordnet_definition': n['description'],
                        'wordnet_record_sha256': retained[n['uid']]['data_sha256'],
                        'native_snapshot_sha256': hashlib.sha256((sources / 'wfo_scientific_sense_cohort.json').read_bytes()).hexdigest(),
                        'reason': 'Distinct retained WFO species UIDs; no independent accepted synonym/concept-equivalence proof in frozen sources. Keep original CLASS scope; no species promotion, identity merge, parent inference or dataset exact mapping.',
                        'source_uids_preserved': True, 'original_class_scope_preserved': True,
                        'independent_equivalence_evidence': None,
                        'identity_merge_authorized': False, 'dataset_mapping_authorized': False}})
    # Individually audited source-vs-label scope differences. These only change
    # the annotation admission ledger, never the real object's visibility.
    review_reasons = {
        '27': 'WordNet maps Prince-of-Wales feathers to a Leptopteris fern sense; Oxford calls it a flower category but supplies no scientific-name scope. Common-name polysemy is unresolved; no replacement taxon guessed.',
        '40': 'Lenten rose is assigned to Helleborus viridis, while RHS herbarium documents H. orientalis under this common name. Exact dataset species/hybrid extent is not established.',
        '42': 'Daffodil is narrowed to Narcissus poeticus, but the independent RHS guide treats daffodils as a genus-level cultivated category. Author metadata does not establish the narrower species.',
        '45': 'Bolero deep blue is an author-declared garden selection label. An Eustoma species sense cannot establish the exact cultivar/selection identity. Primary current catalogue search found related Bolero names but no documentary exact 2008 selection alignment.',
        '46': 'Wallflower is assigned to Matthiola incana, while RHS documents Erysimum cheiri. Exact dataset species scope cannot be certified from common-name matching.',
        '47': 'Marigold is narrowed to Ursinia anthemoides; the author category metadata does not supply a unique species definition. Multiple marigold usages require annotation documentary alignment.',
        '80': 'Unqualified author category anthurium is narrowed to Anthurium andraeanum, while RHS documents Anthurium as a genus scope and WordNet lexical sense includes distinct Anthurium andraeanum/scherzerianum native species UIDs. No exact author species scope is documented; preserve both real taxa and the original target, review label only.',
        '83': 'Hibiscus is narrowed to Hibiscus aculeatus. Independent RHS tropical hibiscus documentation concerns H. rosa-sinensis; the unqualified author label does not certify one of these species.',
        '87': 'Magnolia is narrowed to Magnolia grandiflora; RHS documents a genus category containing multiple species and cultivated hybrids. Exact Oxford species coverage remains undocumented.',
        '92': 'Bee balm is assigned to the Melissa officinalis WordNet sense; RHS associates this common name with Monarda. Exact dataset scope is not uniquely established.',
        '96': 'Camellia is narrowed to Camellia flavida var. flavida; Oxford metadata lists only camellia, while RHS genus guide covers several species and cultivated hybrids. No documentary variety-level dataset definition was found.',
    }
    narrow_scope_labels = set(review_reasons)
    for item in flowers:
        target = dict(c.execute('SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?',
                               ('flowers102', item['class_id'])).fetchone())
        uid, cid = item['uid'], item['class_id']
        before_check = c.execute('SELECT * FROM dataset_mapping_checks WHERE dataset=? AND class_id=?',
                                  ('flowers102', cid)).fetchone()
        n = node(uid)
        if cid in review_reasons:
            fact = facts.get(item['label'])
            proof = {'basis': 'ANNOTATION_SCOPE_IS_DISTINCT_FROM_WORLD_ENTITY_VALIDITY',
                     'reason': review_reasons[cid], 'source_uri': fact['source_uri'] if fact else FLOWERS_URI,
                     'primary_scope_fact': fact, 'primary_scope_facts_sha256': digest(primary),
                     'author_category_source': flower_source,
                     'native_source_record': retained[uid], 'retrieved_utc': '2026-10-09',
                     'world_entity_disposition': 'PRESERVE', 'license': primary['license']}
            mapping_reviews.append({'dataset': 'flowers102', 'class_id': cid, 'label': item['label'],
                'entity_disposition': 'PRESERVE', 'before_target': target,
                'before_target_sha256': digest(target), 'before_check': dict(before_check) if before_check else None,
                'proof': proof})
        # A category is a metadata entity. Existing documented world identity
        # remains a distinct object connected through DEPICTS_TYPE, not SAME_CONCEPT.
        scope_uid, resolution = uid, 'RETAINED_REVIEWED_WORLD_MAPPING'
        scope_proof = {'basis': 'RETAINED_DOCUMENTED_MAPPING_AS_TYPED_SCOPE_ONLY',
                       'original_target': target, 'identity_is_scope': False}
        if cid in narrow_scope_labels:
            # Only Camellia/Magnolia and taxonomically consistent within-genus
            # alternatives authorize a genus scope; ambiguous genera stay at
            # the author-documented plant domain, not an arbitrarily selected species.
            safe_genus = {'40': 'Helleborus', '42': 'Narcissus', '80': 'Anthurium', '83': 'Hibiscus',
                          '87': 'Magnolia', '96': 'Camellia'}.get(cid)
            if safe_genus:
                scope_uid = native_genus(safe_genus); resolution = 'CORROBORATED_GENUS_SCOPE_ONLY'
                scope_proof = {'basis': 'PRIMARY_BOTANICAL_BROAD_SCOPE_WITHOUT_SPECIES_IDENTITY',
                    'source_fact': facts[item['label']], 'source_facts_sha256': digest(primary),
                    'original_narrow_target_retained': uid, 'exact_dataset_species_confirmed': False}
            else:
                scope_uid = PLANT; resolution = 'DOMAIN_ONLY'
                scope_proof = {'basis': 'AUTHOR_DOCUMENTED_FLOWER_CATEGORY_DOMAIN_ONLY',
                    'source': flower_source, 'review_reason': review_reasons[cid],
                    'informative_scope': False, 'exact_dataset_species_confirmed': False}
        elif item['role'] == 'DATASET_CATEGORY':
            links = c.execute("SELECT object_uid,data FROM entity_relations WHERE subject_uid=? AND relation='DEPICTS_TYPE' AND status='ACTIVE'", (uid,)).fetchall()
            if len(links) != 1: raise ValueError('Existing native category has ambiguous type scope')
            scope_uid = links[0]['object_uid']; node(scope_uid)
            resolution = 'RETAINED_PRIMARY_GENUS_GUIDE_SCOPE'
            scope_proof = {'basis': 'RETAINED_PRIMARY_RHS_GENUS_SCOPE',
                           'original_native_category_uid': uid, 'original_scope_proof': json.loads(links[0]['data'])}
        elif item['role'] == 'ATTRIBUTE':
            data = json.loads(n['data']); scope_uid = data['parent_uid']; node(scope_uid)
            resolution = 'HORTICULTURAL_COLOR_SCOPE'
            scope_proof = {'basis': 'AUTHOR_COLOR_QUALIFIED_DAHLIA_CATEGORY_WITH_OFFICIAL_SCOPED_ATTRIBUTE',
                'subject_scope_uid': scope_uid, 'original_attribute_uid': uid,
                'official_organization': 'American Dahlia Society', 'official_code': data['ads_code'],
                'native_color_record': data, 'official_color_source': source_by_name['ads_colors'],
                'exact_cultivar_or_species_asserted': False}
        links = [{'parent': scope_uid, 'relation': 'DEPICTS_TYPE', 'proof': scope_proof}]
        if item['role'] == 'ATTRIBUTE':
            links.append({'parent': uid, 'relation': 'HAS_ATTRIBUTE', 'proof': {**scope_proof,
                          'attribute_is_not_class_or_species': True}})
        native_uid = 'oxford-flowers102:category:' + cid
        proof = {'basis': 'COMPLETE_AUTHOR_NATIVE_CATEGORY_COHORT_WITH_SEPARATE_WORLD_SCOPE',
                 'namespace': 'oxford-flowers102', 'source_version': '2008-categories-20261009',
                 'source_uri': FLOWERS_URI, 'source_publisher': 'Oxford VGG Flowers102 author metadata',
                 'source_sha256': flower_source['sha256'], 'native_task_dataset': 'flowers102',
                 'native_task_class_id': cid, 'native_task_label': author_label(item['label']),
                 'inherited_task_label_preserved': item['label'],
                 'world_exact_identity_verified': False, 'world_target_uid': uid,
                 'world_mapping_review': review_reasons.get(cid), 'scope_resolution': resolution,
                 'native_rank': 'dataset_category', 'source_role': 'author-declared flower category',
                 'license': 'Author metadata facts and citation only; no photographs redistributed',
                 'retrieved_utc': '2026-10-09'}
        native_labels.append({'dataset': 'flowers102', 'class_id': cid, 'uid': native_uid,
                              'label': author_label(item['label']), 'role': 'DATASET_CATEGORY', 'proof': proof, 'links': links})
        flowers_audit.append({**item, 'original_target_retained': True,
            'rank_action': 'SOURCE_SCIENTIFIC_SENSE_RANK_RESTORED' if uid in rank_by_uid else 'PRESERVED',
            'mapping_action': 'LABEL_SCOPE_REVIEW_ENTITY_PRESERVED' if cid in review_reasons else 'PRESERVED',
            'scope_resolution': resolution, 'native_subject_uid': scope_uid,
            'native_relation': 'DEPICTS_TYPE', 'original_reason_preserved_in_baseline': item['reason'],
            'decision_reason': review_reasons.get(cid, 'Original source role/range preserved; native author category is independently retained'),
            'evidence': scope_proof})
    # All fifteen unresolved CUB labels get an individual disposition, including
    # historical split scope and intentional genus/broad category annotations.
    cub_reasons = {
        '17': 'The short annotation Cardinal is not an author-declared full species name. Cardinalis cardinalis is a candidate, but no documentary restriction of the dataset annotation to it was found.',
        '44': 'Frigatebird currently depicts Fregata genus. A broad/genus annotation cannot become a unique species through lexical matching.',
        '62': 'Herring Gull predates current split-sensitive checklist usage. The WordNet Larus argentatus sense does not determine the dataset extent across modern herring-gull taxa.',
        '70': 'Green Violetear is a documented old species complex split into Mexican and Lesser Violetears (AOS SACC proposal 796). An unchanged spelling/Colibri thalassinus identifier cannot certify the narrower modern daughter species.',
        '83': 'White breasted Kingfisher is an older checklist/common-name usage. Exact synonym and any split extent require dataset annotation documentation, not a token deletion from the modern English name.',
        '91': 'Mockingbird currently depicts Mimus genus. The broad annotation does not identify Northern Mockingbird uniquely.',
        '92': 'Nighthawk currently depicts Chordeiles genus. The broad annotation does not identify a unique species.',
        '101': 'White Pelican alone is not a unique full checklist name; author annotation evidence is needed to restrict it to Pelecanus erythrorhynchos rather than other white-pelican concepts.',
        '103': 'Sayornis is explicitly a genus-level annotation. Preserve this scope instead of coercing one phoebe species.',
        '105': 'Whip poor Will is a historical/broad English annotation. Exact modern species extent, including the Eastern/Mexican distinction, was not specified in the source label metadata.',
        '110': 'Geococcyx is explicitly a genus-level annotation. Preserve this scope instead of coercing one roadrunner species.',
        '130': 'Tree Sparrow is mapped to the WordNet Eurasian Passer montanus sense. The label alone also has other regional scientific uses; dataset scope is not established by the lexical sense.',
        '171': 'Myrtle Warbler has species/subspecies and checklist-scope differences. Preserve the original source UID and its source-specific rank; no forced identity with a checklist Yellow-rumped Warbler is introduced.',
        '182': 'Yellow Warbler old annotation extent is not fixed by its modern Setophaga aestiva candidate alone; modern daughter/split range requires documentary annotation alignment.',
        '196': 'House Wren is mapped to a legacy Troglodytes aedon lexical sense. Recent checklist split extent cannot be inferred from the unchanged binomial/common label.'}
    cub_facts = json.loads((sources/'cub_reviewed_scope_facts.json').read_text())
    cub_by_id = {cid:fact for fact in cub_facts['facts'] for cid in fact['class_ids']}
    cub_author = json.loads((sources/'cub_author_report_manifest.json').read_text())
    cub_research = json.loads((sources/'cub_research_author_hierarchy_manifest.json').read_text())
    cub_checklist = json.loads((sources/'avilist_native_scope_records.json').read_text())
    cub_source_scope = {'44':'fregata','62':'larus','70':'colibri','83':'halcyon',
        '91':'mimidae','92':'chordeiles','103':'sayornis','105':'antrostomus',
        '110':'geococcyx','171':'setophaga','182':'setophaga','196':'troglodytes'}
    for item in label_rows:
        if item['dataset'] != 'cub200' or not item['reason']: continue
        node(item['uid'])
        cub_audit.append({**item, 'decision': 'ANNOTATION_SCOPE_REVIEW_PRESERVED',
                          'world_entity_disposition': 'PRESERVE', 'reason_detail': cub_reasons[item['class_id']],
                          'evidence_checked': [CUB_URI, cub_author, cub_research,
                            cub_by_id[item['class_id']], 'Frozen AviList v2025b primary record names/ranks',
                            'Original dataset_targets and dataset_mapping_checks provenance'],
                          'documentary_broad_scope_uid':('avilist:'+cub_source_scope[item['class_id']]
                            if item['class_id'] in cub_source_scope else BIRD),
                          'missing_evidence': 'Author annotation extent and historical-to-fixed-checklist concept alignment',
                          'no_new_species_identity_or_false_parent': True})
    if len(cub_audit) != 15: raise ValueError('CUB unresolved baseline cohort changed')
    for item in label_rows:
        if item['dataset'] != 'cub200':continue
        target = dict(c.execute('SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?',
                               ('cub200',item['class_id'])).fetchone())
        cid = item['class_id']; scope_uid = item['uid']; resolution = 'RETAINED_REVIEWED_WORLD_MAPPING'
        node(item['uid'])
        scope_proof = {'basis':'RETAINED_DOCUMENTED_MAPPING_AS_TYPED_SCOPE_ONLY',
            'original_target':target,'mapping_is_identity':False}
        if item['reason']:
            scope_uid = 'avilist:'+cub_source_scope[cid] if cid in cub_source_scope else BIRD
            resolution = 'DOCUMENTED_BROAD_TAXON_SCOPE' if cid in cub_source_scope else 'DOMAIN_ONLY'
            node(scope_uid)
            scope_proof = {'basis':'DOCUMENTED_ANNOTATION_RANGE_WITHOUT_MODERN_SPECIES_NARROWING',
                'documentary_fact':cub_by_id[cid], 'scope_facts_sha256':digest(cub_facts),
                'author_technical_report':cub_author,'research_author_scope_snapshot':cub_research,
                'modern_checklist_source_records':cub_checklist,
                'original_world_mapping_review':item['reason'],
                'exact_dataset_species_confirmed':False,'informative_scope':resolution!='DOMAIN_ONLY',
                'scientific_parent_graph_created':False}
        proof={'basis':'PRESERVED_AUTHOR_NATIVE_BIRD_LABEL_WITH_SEPARATE_TAXON_SCOPE',
            'namespace':'caltech-cub200-2011','source_version':'2011-author-metadata-20261009',
            'source_uri':CUB_URI,'source_publisher':'Caltech-UCSD Birds author metadata',
            'author_report':cub_author,'baseline_author_label_record':target,
            'native_task_dataset':'cub200','native_task_class_id':cid,'native_task_label':item['label'],
            'world_exact_identity_verified':False,'world_target_uid':item['uid'],
            'world_mapping_review':item['reason'],'scope_resolution':resolution,
            'native_rank':'dataset_category','source_role':'author-declared bird category',
            'license':'Source-derived annotation facts and citation only; no photographs redistributed',
            'retrieved_utc':'2026-10-09'}
        native_labels.append({'dataset':'cub200','class_id':cid,'uid':'caltech-cub200-2011:category:'+cid,
            'label':item['label'],'role':'DATASET_CATEGORY','proof':proof,
            'links':[{'parent':scope_uid,'relation':'DEPICTS_TYPE','proof':scope_proof}]})
    # Exact native identifiers and independent scope definitions prove the
    # meaningful type bridge, rather than a convenience link to organism/entity.
    ott = {row['uid']: row for row in json.loads((sources / 'ott_scope_rows.json').read_text())}
    tracheophyta = ott['ott:10210']
    if tracheophyta['name'] != 'Tracheophyta' or 'ncbi:58023' not in tracheophyta['sourceinfo'].split(','):
        raise ValueError('OTT authoritative source scope changed')
    node('ott:10210'); vascular = node('wordnet31:13104346-n')
    if vascular['description'] != 'green plant having a vascular system: ferns, gymnosperms, angiosperms':
        raise ValueError('WordNet vascular-plant scope changed')
    bridge_proof = {'basis': 'IDENTIFIER_GROUNDED_NATIVE_TAXON_AND_INDEPENDENT_VASCULAR_PLANT_DEFINITION',
        'source_uri': source_by_name['tracheophyta_ncbi']['uri'],
        'native_taxon_record': tracheophyta, 'native_taxonomy_version': 'OTT 3.7draft3',
        'native_record_sha256': retained['ott:10210']['data_sha256'],
        'authority': source_by_name['tracheophyta_ncbi'],
        'authority_taxon_id': '58023', 'authority_common_name': 'vascular plants',
        'wordnet_parent_definition': vascular['description'],
        'wordnet_parent_payload_sha256': retained[vascular['uid']]['data_sha256'],
        'scope': 'Vascular plant inclusion only; no source UID equality or rank equivalence is asserted',
        'license': 'Native taxonomy facts and original source attribution retained'}
    links = [{'op': 'link', 'uid': 'ott:10210', 'parent': vascular['uid'], 'relation': 'IS_A',
              'source': 'Identifier-grounded native vascular-plant type scope',
              'uri': bridge_proof['source_uri'], 'proof': bridge_proof}]
    # Modern Magnoliophyta and Acrogymnospermae are sibling seed-plant scopes.
    # A historical/unsourced Cycadophytanae claim is retained as source material,
    # but its cross-scheme path into modern gymnosperms is not task evidence.
    bad = dict(c.execute('SELECT * FROM edges WHERE id=3303570').fetchone())
    if (bad['child_uid'], bad['parent_uid'], bad['relation'], bad['status']) != (
            'wikidata:Q98522415', 'wikidata:Q56639776', 'TAXONOMIC_PARENT', 'TYPED_ACTIVE'):
        raise ValueError('Historical source assertion changed')
    for uid in ('wikidata:Q98522415','wikidata:Q56639776','wikidata:Q14562931','wikidata:Q25814'): node(uid)
    modern = {'basis': 'MODERN_SEED_PLANT_SCOPE_EXCLUDES_UNCORROBORATED_CROSS_SCHEME_GYMNOSPERM_PATH',
        'historical_claim_retained': bad, 'original_source_assertion_sha256': digest(bad),
        'native_record_sha256': retained[bad['child_uid']]['data_sha256'],
        'source_uri': 'https://doi.org/10.1016/j.pld.2022.05.003',
        'independent_scientific_scope': 'Acrogymnospermae consists of extant gymnosperms, while angiosperms form a separate seed-plant scope',
        'primary_publication_snapshot': source_by_name['gymnosperm_phylogeny_paper'],
        'independent_ncbi_gymnosperm_lineage': source_by_name['ncbi_acrogymnospermae'],
        'independent_ncbi_angiosperm_lineage': source_by_name['magnoliopsida_ncbi'],
        'historical_scheme_truth': 'No complete primary Cycadophytanae scheme/version could be retrieved; this decision rejects mixed modern supervision, not the existence of a historical classification',
        'quarantine_scope': 'Withdrawn admitted arc only; source UID/data and exact assertion evidence/history remain',
        'license': 'Derived taxonomic facts and attribution; 2022 paper CC BY license retained'}
    links.append({'op': 'withdraw_edge', 'uid': bad['child_uid'], 'parent': bad['parent_uid'],
                  'edge_id': bad['id'], 'source': 'Reviewed incompatible taxonomic source scope',
                  'uri': modern['source_uri'], 'proof': modern})
    parent_proof = {'basis': 'INDEPENDENT_MODERN_ANGIOSPERM_TO_SEED_PLANT_SCOPE',
        'native_record_sha256': retained['wikidata:Q14562931']['data_sha256'],
        'source_uri': source_by_name['magnoliopsida_ncbi']['uri'],
        'authority': source_by_name['magnoliopsida_ncbi'], 'authority_taxon_id': '3398',
        'authority_synonym': 'Magnoliophyta', 'authority_parent_lineage': 'Spermatophyta',
        'source_scope': 'Modern angiosperm higher taxon lineage only; no rank equality or source identity merge',
        'strict_classification': False, 'license': 'Native taxonomy facts and original attribution retained'}
    links.append({'op': 'link', 'uid': 'wikidata:Q14562931', 'parent': 'wikidata:Q25814',
                  'relation': 'TAXONOMIC_PARENT', 'source': 'Independent modern angiosperm higher taxon scope',
                  'uri': parent_proof['source_uri'], 'proof': parent_proof})
    raw_links = ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in links).encode()
    (output / LINK_INPUT_NAME).write_bytes(raw_links)
    payload = {'schema': SCHEMA, 'baseline_revision': analysis['revision'],
        'rank_repairs': rank_repairs, 'rank_reviews': rank_reviews, 'mapping_reviews': mapping_reviews,
        'native_labels': native_labels, 'retained_nodes': sorted(retained.values(), key=lambda r:r['uid']),
        'links_sha256': hashlib.sha256(raw_links).hexdigest(),
        'source_manifest': manifests, 'primary_review_facts_sha256': digest(primary),
        'scope': 'Biological type bridge and source scheme; all 102 Flowers labels and all 15 remaining CUB annotations'}
    validate_payload(payload)
    (output / INPUT_NAME).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    unresolved_paths = [row for row in analysis['datasets']['flowers102']['task_policy_path_unconnected_labels'] if row['endpoint_applicable']]
    path_audit = [{'class_id':row['class_id'], 'label':row['label'],
        'baseline_status': row['status'], 'cause': 'OTT vascular-plant lineage reaches organism without passing the WordNet plant task boundary',
        'repair': links[0], 'source_identity_unchanged': True,
        'candidate_recheck_required': True} for row in unresolved_paths]
    (reports / 'flowers_all_labels.json').write_text(json.dumps(flowers_audit,ensure_ascii=False,indent=2)+'\n')
    (reports / 'flowers_37_excluded.json').write_text(json.dumps([r for r in flowers_audit if r['reason']],ensure_ascii=False,indent=2)+'\n')
    (reports / 'flowers_19_task_paths.json').write_text(json.dumps(path_audit,ensure_ascii=False,indent=2)+'\n')
    (reports / 'cub_15_annotation_scopes.json').write_text(json.dumps(cub_audit,ensure_ascii=False,indent=2)+'\n')
    (reports / 'wordnet_multi_species_scope_reviews.json').write_text(json.dumps(rank_reviews,ensure_ascii=False,indent=2)+'\n')
    summary = {'flowers_labels_audited':102, 'flowers_excluded_individually_audited':37,
        'flowers_task_paths_cause_audited':len(path_audit), 'cub_annotation_scopes_audited':15,
        'scientific_sense_rank_repairs':len(rank_repairs), 'new_label_mapping_reviews':len(mapping_reviews),
        'scientific_sense_multi_species_scope_reviews':len(rank_reviews),
        'scientific_sense_pattern_scan':json.loads((sources/'scientific_sense_scan_manifest.json').read_text()),
        'six_dataset_rank_repairs':sum(row['uid'] in {r['uid'] for r in flowers} for row in rank_repairs),
        'native_flower_labels':sum(r['dataset']=='flowers102' for r in native_labels),
        'native_cub_labels':sum(r['dataset']=='cub200' for r in native_labels),
        'native_scope_resolutions':dict(Counter(r['proof']['scope_resolution'] for r in native_labels)),
        'meaningful_type_bridges':1, 'cross_scheme_admitted_arcs_withdrawn':1,
        'modern_taxon_navigation_links':1, 'new_scientific_species_or_identity_merges':0,
        'input_sha256':digest(payload), 'links_sha256':payload['links_sha256'],
        'all_755_labels_56917_pairs_recheck_by_main': True,
        'pending_cub_world_annotation_scopes':15, 'historical_cycadophytanae_primary_scheme_unretrieved':True,
        'metrics_note':'Author categories and rank/mapping/policy changes are not new species or visual-accuracy gains'}
    (reports / 'biology_preparation_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    c.close()
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('database','baseline','sources','output'):p.add_argument('--'+key,required=True,type=Path)
    args=p.parse_args()
    if not (args.sources/'wordnet_scientific_sense_cohort.json').exists():
        freeze_scientific_senses(args.database,args.sources)
    print(json.dumps(prepare(args.database,args.baseline,args.sources,args.output),ensure_ascii=False,indent=2))
