"""R3 whole-definition scope review, separate from the frozen R2 rank input."""
from __future__ import annotations
import hashlib
import json
import re

from .structure_biology import canonical_json, digest

INPUT_NAME = 'structure_biology_scope.json'
SCHEMA = 'FINEATLAS_BIOLOGY_WHOLE_SCOPE_V1'
STAGE = 'v1.11-biological-whole-definition-scope'


def whole_scope_review(description: str) -> str | None:
    """Reject a declaration of a group; preserve variation within one taxon.

    Quantification modifies the identity's full extent only when it introduces
    the definition's subject. 'Cultivated in many varieties', a plant having
    several racemes, and a single named hybrid taxon do not declare a group.
    This lexical guard only removes an unsupported rank: it proves no identity,
    taxonomic parent or equivalence between a genus and a botanical species.
    """
    head = description.strip().lower()
    if re.match(r'^(?:any|all) of (?:the )?(?:various|several|numerous|many)\b', head):
        return 'Definition denotes a quantified group, not one whole species scope'
    if re.match(r'^(?:a|the) (?:group|collection|assemblage) of\b', head):
        return 'Definition explicitly declares a group extent'
    if re.match(r'^(?:all|any) (?:the )?(?:plants|species|cultivars|varieties|hybrids)\b.*\bgenus\b', head):
        return 'Definition denotes a genus-wide or multi-taxon extent'
    return None


def apply_structure_biology_scope(m):
    path = m.inputs / INPUT_NAME
    if not path.exists():
        return {'status': 'not_requested'}
    payload = json.loads(path.read_text())
    if payload.get('schema') != SCHEMA:
        raise ValueError('Unsupported whole-definition biological scope input')
    fingerprint = digest(payload)
    old = m.c.execute('SELECT value FROM metadata WHERE key=?',
                      ('structure_biology_scope_input_sha256',)).fetchone()
    if old and json.loads(old[0]) == fingerprint:
        return {'status': 'already_applied', 'input_sha256': fingerprint}
    base = m.c.execute('SELECT value FROM metadata WHERE key=?',
                       ('structure_biology_input_sha256',)).fetchone()
    if not base or json.loads(base[0]) != payload['r2_payload_sha256']:
        raise ValueError('R3 must follow exactly the frozen R2 biological input')
    for item in payload['rank_reviews']:
        uid = item['uid']
        node = m.c.execute('SELECT * FROM nodes WHERE uid=?', (uid,)).fetchone()
        if (not node or node['source'] != 'wordnet31' or node['visibility'] != 'ACTIVE'
                or hashlib.sha256(node['data'].encode()).hexdigest() != item['source_data_sha256']
                or hashlib.sha256(node['description'].encode()).hexdigest() != item['description_sha256']
                or node['component_id'] != item['component_id']
                or not whole_scope_review(node['description'])):
            raise ValueError('Whole-definition source scope drift: ' + uid)
        peers = sorted(r[0] for r in m.c.execute('SELECT uid FROM nodes WHERE component_id=?',
                                               (node['component_id'],)))
        if peers != item['identity_peers']:
            raise ValueError('Whole-definition identity component drift: ' + uid)
        prior = m.c.execute('SELECT * FROM node_taxon_ranks WHERE uid=?', (uid,)).fetchone()
        if not prior or prior['rank'] != 'species' or prior['status'] != 'SOURCE_DECLARED':
            raise ValueError('R3 requires the original R2 rank declaration: ' + uid)
        proof = {**item['proof'], 'input_sha256': fingerprint,
                 'original_rank_record': dict(prior), 'original_source_data_sha256': item['source_data_sha256']}
        eid = m.evidence('WordNet full-definition biological scope',
                         'https://wordnet.princeton.edu/', proof,
                         'WHOLE_DEFINITION_SCOPE_REVIEW', license='WordNet 3.1 license')
        m.c.execute('INSERT OR REPLACE INTO node_taxon_ranks VALUES(?,?,?,?,?)',
                    (uid, None, 'WHOLE_DEFINITION_SCOPE_REVIEW', eid,
                     'Original broad CLASS retained; scientific lemma does not narrow full definition'))
        m.change(STAGE, 'taxon_whole_scope_review', uid, dict(prior),
                 {'rank': None, 'status': 'WHOLE_DEFINITION_SCOPE_REVIEW',
                  'entity_disposition': 'PRESERVE'}, proof)
    m.meta('structure_biology_scope_input_sha256', fingerprint)
    result = {'reviewed_rank_restorations': payload['audited_rank_restorations'],
              'whole_definition_scope_reviews': len(payload['rank_reviews']),
              'retained_single_scope_rank_declarations': payload['audited_rank_restorations'] - len(payload['rank_reviews']),
              'identity_splits': 0, 'dataset_mappings_changed': 0,
              'source_nodes_or_raw_changed': 0, 'requires_cache_rebuild': True,
              'input_sha256': fingerprint}
    m.meta('structure_biology_scope_summary', result)
    m.c.commit()
    return result
