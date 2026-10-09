"""Freeze a separate R3 review of every R2 WordNet species-rank restoration."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fineatlas.structure_biology import digest
from fineatlas.structure_biology_scope import whole_scope_review, SCHEMA, INPUT_NAME


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--r2-input', required=True)
    p.add_argument('--database', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    r2path = Path(args.r2_input)
    r2 = json.loads(r2path.read_text())
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(Path(args.database).resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA temp_store=MEMORY')
    ledger = []; reviews = []
    for repair in r2['rank_repairs']:
        n = dict(c.execute('SELECT * FROM nodes WHERE uid=?', (repair['uid'],)).fetchone())
        reason = whole_scope_review(n['description'])
        evidence = {'uid': n['uid'], 'label': n['label'], 'definition': n['description'],
                    'scientific_senses': repair['proof']['scientific_senses'],
                    'native_scope_candidates': repair['proof']['corroborating_native_records'],
                    'decision': 'WHOLE_DEFINITION_SCOPE_REVIEW' if reason else 'RETAIN_R2_SINGLE_SCOPE_DECLARATION',
                    'reason': reason or 'Source subject does not declare a quantified group; unique native species rank corroboration retained. Variation/hybrid modifiers do not alone change extent.',
                    'whole_definition_checked': True,
                    'description_sha256': hashlib.sha256(n['description'].encode()).hexdigest(),
                    'source_data_sha256': hashlib.sha256(n['data'].encode()).hexdigest()}
        ledger.append(evidence)
        if not reason:
            continue
        peers = [x[0] for x in c.execute('SELECT uid FROM nodes WHERE component_id=? ORDER BY uid', (n['component_id'],))]
        bridges = [dict(x) for x in c.execute("SELECT * FROM bridges WHERE status='ACTIVE' AND relation='SAME_CONCEPT' AND (left_uid=? OR right_uid=?)", (n['uid'], n['uid']))]
        if peers != [n['uid']] or bridges:
            raise ValueError('Broad scope has existing identity peers; requires individual source-equivalence review: ' + n['uid'])
        targets = [dict(x) for x in c.execute('SELECT * FROM dataset_targets WHERE target_uid=?', (n['uid'],))]
        if targets:
            raise ValueError('Broad rank declaration has direct world mappings; requires label-only scope review: ' + n['uid'])
        reviews.append({'uid': n['uid'], 'component_id': n['component_id'],
                        'identity_peers': peers, 'active_same_concept_bridges': bridges,
                        'source_data_sha256': evidence['source_data_sha256'],
                        'description_sha256': evidence['description_sha256'],
                        'proof': {**evidence, 'source_uri': 'https://wordnet.princeton.edu/',
                                  'source_version': 'WordNet 3.1',
                                  'scope_disposition': 'ORIGINAL_BROAD_CLASS_PRESERVED',
                                  'identity_splits_required': False,
                                  'direct_dataset_targets': targets,
                                  'entity_disposition': 'PRESERVE',
                                  'native_taxa_preserved': True}})
    report = {'schema': SCHEMA, 'r2_file_sha256': hashlib.sha256(r2path.read_bytes()).hexdigest(),
              'r2_payload_sha256': digest(r2), 'audited_rank_restorations': len(ledger),
              'rank_reviews': reviews,
              'rules': 'Full source definition subject, not scientific-name-only matching; anchored quantified group declarations fail closed. Single-taxon variation and named hybrid taxa remain eligible.',
              'original_r2_frozen_unchanged': True,
              'remaining_r2_single_scope_rank_declarations': len(ledger)-len(reviews),
              'ledger_sha256': digest(ledger)}
    (out / INPUT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    (out / 'r2_all_rank_whole_scope_ledger.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'audited': len(ledger), 'scope_reviews': len(reviews),
                      'retained': len(ledger)-len(reviews), 'delta': str(out / INPUT_NAME),
                      'delta_sha256': hashlib.sha256((out / INPUT_NAME).read_bytes()).hexdigest()}))
    c.close()

if __name__ == '__main__':
    main()
