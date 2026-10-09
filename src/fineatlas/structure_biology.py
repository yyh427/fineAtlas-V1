"""Frozen biological scope repairs; annotation scope never invalidates a taxon.

This adapter does not download, infer equality from names, or build graph caches.
The caller applies it only to an independent candidate before graph rebuilding.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from .hierarchy import apply_refinements

INPUT_NAME = 'structure_biology.json'
LINK_INPUT_NAME = 'structure_biology_links.jsonl'
SCHEMA = 'FINEATLAS_STRUCTURE_BIOLOGY_V1'
STAGE = 'v1.11-biological-source-scope'


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def explicit_scientific_senses(record):
    """Return source-declared binomials, never guess from common-name tokens.

    The names are candidate *rank* evidence. They never authorize an identity
    merge, scientific parent, or a dataset's exact species interpretation.
    """
    result = []
    for lemma in json.loads(record.get('data') or '{}').get('labels', []):
        scientific = lemma.replace('_', ' ')
        if re.fullmatch(r'[A-Z][a-z]+ [a-z][a-z-]+', scientific):
            result.append(scientific)
    return sorted(set(result))


def corroborated_species_rank(record, native_records):
    """Accept only an explicit species sense with unambiguous native rank.

    A glossary sense explicitly covering an entire genus is not a species.
    Distinct native records with the same spelling remain separate; ambiguous
    candidate names fail closed rather than contracting their identities.
    """
    if record.get('source') != 'wordnet31':
        return None
    if re.search(r'\b(any|all) (?:\w+ )?plants?\b.*\bgenus\b',
                 record.get('description', ''), re.I):
        return None
    senses = explicit_scientific_senses(record)
    matches = [row for row in native_records if row['label'] in senses]
    by_name = {}
    for row in matches:
        by_name.setdefault(row['label'], []).append(row)
    if not by_name or any(len(rows) != 1 or rows[0]['rank'] != 'species'
                          for rows in by_name.values()):
        return None
    # A lexical synset can be broader than each named modern species. Different
    # native UIDs do not corroborate a single species extent, even when every
    # source record has rank species. No synonym equivalence is inferred here.
    if len({row['uid'] for row in matches}) != 1:
        return None
    return {'rank': 'species', 'scientific_senses': senses,
            'corroborating_native_records': sorted(matches, key=lambda row: row['uid']),
            'identity_merge_authorized': False,
            'dataset_mapping_authorized': False}


def validate_payload(payload):
    if payload.get('schema') != SCHEMA:
        raise ValueError('Unsupported biological repair input')
    for native in payload['native_labels']:
        proof = native['proof']
        if (not native['label'] or native['role'] != 'DATASET_CATEGORY'
                or not proof.get('source_uri') or not proof.get('source_version')
                or proof.get('world_exact_identity_verified') is not False):
            raise ValueError('Native annotation must preserve its source scope')
        for link in native['links']:
            if link['relation'] not in {'DEPICTS_TYPE', 'HAS_ATTRIBUTE'}:
                raise ValueError('Annotation relation cannot masquerade as identity')
            if link['relation'] == 'HAS_ATTRIBUTE' and not link['proof'].get('subject_scope_uid'):
                raise ValueError('Horticultural attribute needs an organism scope')
    for repair in payload['mapping_reviews']:
        if repair.get('entity_disposition') != 'PRESERVE' or not repair['proof'].get('reason'):
            raise ValueError('A label review cannot quarantine the world entity')
    for repair in payload['rank_repairs']:
        if (repair['proof'].get('identity_merge_authorized') is not False
                or repair['proof'].get('dataset_mapping_authorized') is not False
                or repair['rank'] != 'species'):
            raise ValueError('Rank evidence must not authorize identity or mapping')
        native = repair['proof'].get('corroborating_native_records', [])
        if not native or len({row['uid'] for row in native}) != 1:
            raise ValueError('Species rank requires one confirmed native scope UID')
    for review in payload.get('rank_reviews', []):
        if (review.get('rank') is not None or review.get('entity_disposition') != 'PRESERVE'
                or len({row['uid'] for row in review['proof']['native_scope_candidates']}) <= 1):
            raise ValueError('Ambiguous lexical scope must preserve broad CLASS and native UIDs')


def _verify_retained(c, retained):
    for record in retained:
        row = c.execute('SELECT uid,label,source,rank,data,visibility FROM nodes WHERE uid=?',
                        (record['uid'],)).fetchone()
        if not row or row['visibility'] != 'ACTIVE':
            raise ValueError('Missing biological source endpoint: ' + record['uid'])
        actual = {key: row[key] for key in ('uid', 'label', 'source', 'rank')}
        actual['data_sha256'] = hashlib.sha256(row['data'].encode()).hexdigest()
        if actual != record:
            raise ValueError('Biological source scope changed: ' + record['uid'])


def apply_structure_biology(m):
    """Replay source-native labels, rank evidence, and label-only reviews.

    Existing source UID, target, visibility, same-concept links and mapping
    histories are untouched. Every change is evidence-linked and idempotent.
    All affected graph/search/browse/training caches must subsequently rebuild.
    """
    path = m.inputs / INPUT_NAME
    if not path.exists():
        return {'status': 'not_requested'}
    payload = json.loads(path.read_text())
    validate_payload(payload)
    fingerprint = digest(payload)
    previous = m.c.execute('SELECT value FROM metadata WHERE key=?',
                           ('structure_biology_input_sha256',)).fetchone()
    if previous and json.loads(previous[0]) == fingerprint:
        return {'status': 'already_applied', 'input_sha256': fingerprint}
    _verify_retained(m.c, payload['retained_nodes'])
    if hashlib.sha256((m.inputs / LINK_INPUT_NAME).read_bytes()).hexdigest() != payload['links_sha256']:
        raise ValueError('Frozen biological links checksum differs')
    # Main migration owns this shared table. Never silently use a different
    # label key or assign world identity semantics to this source selector.
    columns = [r[1] for r in m.c.execute('PRAGMA table_info(dataset_scope_targets)')]
    expected = ['dataset', 'class_id', 'namespace', 'source_version', 'source_uid',
                'role', 'decision_status', 'proof', 'label']
    if columns != expected:
        raise ValueError('Main migration must install dataset_scope_targets contract')
    counts = Counter()
    for review in payload['mapping_reviews']:
        before = review['before_target']
        current = m.c.execute('SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?',
                              (before['dataset'], before['class_id'])).fetchone()
        if not current or digest(dict(current)) != review['before_target_sha256']:
            raise ValueError('Frozen biological annotation target drift')
        prior = m.c.execute('SELECT * FROM dataset_mapping_checks WHERE dataset=? AND class_id=?',
                            (before['dataset'], before['class_id'])).fetchone()
        if (dict(prior) if prior else None) != review['before_check']:
            raise ValueError('Prior mapping review changed')
        proof = {**review['proof'], 'input_sha256': fingerprint,
                 'world_entity_preserved': before['target_uid'],
                 'original_target_record': before,
                 'original_mapping_check': review['before_check']}
        m.evidence('Biological annotation scope review', proof['source_uri'], proof,
                   'LABEL_SCOPE_REVIEW')
        m.c.execute('INSERT OR IGNORE INTO dataset_target_history VALUES(?,?,?,?)',
                    (before['dataset'], before['class_id'], before['target_uid'], canonical_json(before)))
        m.c.execute('INSERT OR IGNORE INTO annotation_scope_target_history VALUES(?,?,?,?)',
                    (STAGE, before['dataset'], before['class_id'], canonical_json(before)))
        m.c.execute('INSERT OR REPLACE INTO dataset_mapping_checks VALUES(?,?,?,?,?)',
                    (before['dataset'], before['class_id'], 'ANNOTATION_SCOPE_REVIEW',
                     proof['reason'], canonical_json(proof)))
        m.change(STAGE, 'label_mapping_review', before['dataset'] + ':' + before['class_id'],
                 dict(prior) if prior else {}, {'status': 'ANNOTATION_SCOPE_REVIEW',
                 'reason': proof['reason']}, proof)
        counts['label_mapping_reviews'] += 1
    for repair in payload['rank_repairs']:
        prior = m.c.execute('SELECT * FROM node_taxon_ranks WHERE uid=?', (repair['uid'],)).fetchone()
        if (dict(prior) if prior else None) != repair['before_rank']:
            raise ValueError('Biological source rank changed before replay')
        proof = {**repair['proof'], 'input_sha256': fingerprint}
        eid = m.evidence('Declared scientific sense with native taxon rank', proof['source_uri'],
                         proof, 'SCIENTIFIC_SENSE_RANK')
        m.c.execute('INSERT OR REPLACE INTO node_taxon_ranks VALUES(?,?,?,?,?)',
                    (repair['uid'], repair['rank'], 'SOURCE_DECLARED', eid,
                     'WordNet scientific sense and frozen WFO native rank'))
        m.change(STAGE, 'taxon_rank', repair['uid'], dict(prior) if prior else {},
                 {'rank': repair['rank'], 'status': 'SOURCE_DECLARED'}, proof)
        counts['scientific_sense_ranks_restored'] += 1
    for review in payload.get('rank_reviews', []):
        prior = m.c.execute('SELECT * FROM node_taxon_ranks WHERE uid=?', (review['uid'],)).fetchone()
        if (dict(prior) if prior else None) != review['before_rank']:
            raise ValueError('Ambiguous biological source rank changed before replay')
        proof = {**review['proof'], 'input_sha256': fingerprint}
        eid = m.evidence('WordNet lexical sense and distinct native species scopes',
                         proof['source_uri'], proof, 'SCIENTIFIC_SCOPE_REVIEW')
        m.c.execute('INSERT OR REPLACE INTO node_taxon_ranks VALUES(?,?,?,?,?)',
                    (review['uid'], None, 'MULTI_SPECIES_SCOPE_REVIEW', eid,
                     'WordNet/WFO source scope ambiguity; original CLASS retained'))
        m.change(STAGE, 'taxon_rank_review', review['uid'], dict(prior) if prior else {},
                 {'rank': None, 'status': 'MULTI_SPECIES_SCOPE_REVIEW',
                  'entity_disposition': 'PRESERVE'}, proof)
        counts['scientific_sense_multi_species_scope_reviews'] += 1
    for native in payload['native_labels']:
        proof = {**native['proof'], 'input_sha256': fingerprint}
        source = proof['source_publisher']
        counts['native_category_nodes_added'] += int(m.add_node(
            native['uid'], native['label'], native['role'], 'task_categories',
            source, proof['source_uri'], proof, 'Source-native annotation category; world scope is represented by typed links'))
        m.alias(native['uid'], native['label'], source, 'en')
        # Public label role is source-declared; no scientific rank is assigned.
        m.c.execute('INSERT INTO dataset_scope_targets VALUES(?,?,?,?,?,?,?,?,?)',
                    (native['dataset'], native['class_id'], proof['namespace'],
                     proof['source_version'], native['uid'], native['role'],
                     'SOURCE_DECLARED', canonical_json(proof), native['label']))
        for link in native['links']:
            m.typed(native['uid'], link['parent'], link['relation'],
                    {**link['proof'], 'native_label_uid': native['uid'],
                     'input_sha256': fingerprint, 'mapping_is_identity': False}, source, proof['source_uri'])
            counts['native_' + link['relation'].lower() + '_links'] += 1
        counts['native_labels_retained'] += 1
    # Uses explicit endpoint/checksum contracts shared with other refinements.
    # This file is registered by the main migration, not a hidden manual patch.
    counts.update(apply_refinements(m, LINK_INPUT_NAME))
    m.meta('structure_biology_input_sha256', fingerprint)
    m.meta('structure_biology_summary', dict(counts))
    m.c.commit()
    return {**dict(counts), 'input_sha256': fingerprint,
            'source_uids_collapsed': 0, 'original_targets_deleted': 0,
            'world_identity_merges_added': 0, 'requires_cache_rebuild': True}
