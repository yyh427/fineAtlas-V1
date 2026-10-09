#!/usr/bin/env python3
"""Prepare a bounded furniture-listing trial from frozen ABO metadata.

Listings identify source catalogue product configurations, not independently
established worldwide design models or physical specimens. Original list-valued
fields and asset identifiers are retained; this script downloads no assets.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fineatlas._text import norm
from fineatlas.semantics import role_expression

SOURCE = 'Amazon Berkeley Objects furniture metadata bounded trial'
SOURCE_URI = 'https://amazon-berkeley-objects.s3.us-east-1.amazonaws.com/listings/metadata/listings_0.json.gz'
LICENSE_URI = 'https://amazon-berkeley-objects.s3.us-east-1.amazonaws.com/LICENSE-CC-BY-4.0.txt'
ATTRIBUTION = 'Amazon.com; Matthieu Guillaumin, Thomas Dideriksen, Kenan Deng, Himanshu Arora, Jasmine Collins and Jitendra Malik'
# Only these independently inspected native rows constitute this frozen batch.
REVIEWED = {
    ('amazon.com', 'B072ZLCB3M'): ('TABLE', 'wordnet31:04386330-n', 'Side Table'),
    ('amazon.com', 'B07TMH6289'): ('CHAIR', 'wordnet31:03005231-n', 'Recliner'),
    ('amazon.com', 'B075X4QMW7'): ('SOFA', 'wordnet31:04263630-n', 'Sectional Sofa'),
    ('amazon.com', 'B07F2X8K62'): ('CHAIR', 'wordnet31:03005231-n', 'Accent Chair'),
}
MAX_SAMPLE_ROWS = 200
MAX_IMPORTED_LISTINGS = 4


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical_record(record):
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def values(record, key):
    field = record.get(key, [])
    if not isinstance(field, list) or any(not isinstance(v, dict) or 'value' not in v for v in field):
        raise ValueError('ABO field is not the frozen list-of-values schema: ' + key)
    return [v['value'] for v in field]


def listing_uid(domain, item_id):
    return 'abo-listing:' + quote(domain, safe='') + ':' + quote(item_id, safe='')


def prepare(database, sample, output, source_readme, source_license):
    output.mkdir(parents=True, exist_ok=True)
    raw = sample.read_bytes()
    records = json.loads(raw)
    if not isinstance(records, list) or len(records) > MAX_SAMPLE_ROWS:
        raise ValueError('Furniture trial exceeds frozen source-row budget')
    if 'Creative Commons Attribution 4.0' not in source_license.read_text() or 'Matthieu Guillaumin' not in source_readme.read_text():
        raise ValueError('Missing official license/attribution evidence')
    c = sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    c.row_factory = sqlite3.Row
    accepted, reviews, seen = [], [], set()
    for index, record in enumerate(records):
        product_types = values(record, 'product_type')
        if not set(product_types).intersection({'SOFA', 'CHAIR', 'TABLE', 'BED'}):
            continue
        key = (record.get('domain_name'), record.get('item_id'))
        if key in seen:
            raise ValueError('Duplicate native catalogue identity')
        seen.add(key)
        names = [v['value'] for v in record.get('item_name', []) if v.get('language_tag') == 'en_US']
        if key not in REVIEWED:
            reason = ('PRODUCT_TYPE_SAYS_SOFA_BUT_TITLE_IS_FABRIC_SWATCH' if key[1] == 'B07CTPR73M' else
                      'MULTILINGUAL_CONFIGURATION_SCOPE_CONFLICT' if key[1] == 'B07B4SCB6T' else
                      'MODEL_NAME_AND_MARKETPLACE_TITLE_REQUIRE_SEPARATE_SCOPE_REVIEW')
            reviews.append({'source_identity': list(key), 'product_types': product_types,
                            'reason': reason, 'disposition': 'NOT_IMPORTED; original record retained in frozen sample',
                            'native_record_sha256': digest(canonical_record(record))})
            continue
        expected_type, parent, title_phrase = REVIEWED[key]
        if product_types != [expected_type] or len(names) != 1 or title_phrase not in names[0]:
            raise ValueError('Reviewed native listing scope differs: ' + str(key))
        if re.search(r'\b(swatch|cover|replacement|accessory|cushion)\b', names[0], re.I):
            raise ValueError('Furniture category does not entail the sold object type')
        if not values(record, 'model_number') or not record.get('node'):
            raise ValueError('Missing native design identifier/catalogue branch')
        uid = listing_uid(*key)
        existing = c.execute('SELECT data FROM nodes WHERE uid=?', (uid,)).fetchone()
        if existing:
            proof = json.loads(existing['data'])
            if proof.get('source_record_sha256') != digest(canonical_record(record)):
                raise ValueError('Existing native listing identity has different source payload')
            reviews.append({'source_identity': list(key), 'reason': 'ALREADY_IMPORTED_IDENTICAL_SOURCE_RECORD', 'disposition': 'DEDUPLICATED'})
            continue
        parent_node = c.execute('SELECT n.*,' + role_expression('n', 'p') + ' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?', (parent,)).fetchone()
        if not parent_node or parent_node['visibility'] != 'ACTIVE' or parent_node['role'] != 'CLASS':
            raise ValueError('Furniture type endpoint is not admitted CLASS')
        possible_name_matches = sorted({r[0] for r in c.execute('SELECT uid FROM aliases WHERE alias=? LIMIT 21', (norm(names[0]),))})
        possible_model_matches = sorted({r[0] for number in values(record, 'model_number') for r in c.execute('SELECT uid FROM aliases WHERE alias=? LIMIT 21', (norm(str(number)),))})
        proof = {'basis': 'EXPLICIT_REVIEWED_SOURCE_CATALOGUE_FURNITURE_CONFIGURATION',
                 'source_uri': SOURCE_URI, 'source_identity': {'domain_name': key[0], 'item_id': key[1]},
                 'source_sample_sha256': digest(raw), 'sample_row_index': index,
                 'source_record_sha256': digest(canonical_record(record)), 'native_record': record,
                 'source_role': 'Source catalogue product configuration identified by marketplace and item_id',
                 'native_rank': 'configuration', 'semantic_grain': 'source_catalogue_product_configuration',
                 'allowed_views': ['strict', 'taxonomy', 'membership'],
                 'type_evidence': {'product_type': product_types, 'english_title': names[0],
                                   'reviewed_title_phrase': title_phrase, 'native_catalogue_nodes': record['node']},
                 'parent_uid': parent, 'parent_definition': parent_node['description'],
                 'parent_native_record_sha256': digest(parent_node['data'].encode()),
                 'identity_policy': 'Only exact (domain_name,item_id) deduplication; no cross-marketplace, name or model-number identity bridge',
                 'not_global_model_identity': True, 'not_physical_instance': True,
                 'license': 'CC BY 4.0', 'license_uri': LICENSE_URI, 'attribution': ATTRIBUTION,
                 'retrieved_utc': '2026-10-08',
                 'modifications': 'Metadata subset selected; source catalogue configuration role and reviewed WordNet type connection added; native fields unchanged',
                 'possible_existing_name_matches': possible_name_matches,
                 'possible_existing_model_number_matches': possible_model_matches}
        accepted.append({'uid': uid, 'label': names[0], 'role': 'CONFIGURATION', 'domain': 'furniture',
                         'source': SOURCE, 'uri': SOURCE_URI, 'parent': parent,
                         'relation': 'CONFIGURATION_TYPE_OF', 'proof': proof,
                         'definition': 'Source catalogue configuration: ' + names[0]})
    if len(accepted) > MAX_IMPORTED_LISTINGS:
        raise ValueError('Furniture import exceeds fixed accepted-row budget')
    c.close()
    (output / 'abo_furniture_records.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in accepted))
    (output / 'abo_furniture_reviews.json').write_text(json.dumps(reviews, ensure_ascii=False, indent=2) + '\n')
    attribution = {'source': 'Amazon Berkeley Objects', 'copyright': '(c) Amazon.com', 'license': 'CC BY 4.0',
                   'license_uri': LICENSE_URI, 'attribution': ATTRIBUTION,
                   'source_uri': SOURCE_URI, 'source_sample_sha256': digest(raw),
                   'source_readme_sha256': digest(source_readme.read_bytes()), 'source_license_sha256': digest(source_license.read_bytes()),
                   'rows_examined': len(records), 'max_imported': MAX_IMPORTED_LISTINGS, 'accepted_configurations': len(accepted),
                   'reviewed_not_imported': len(reviews), 'new_models': 0, 'new_series': 0, 'new_instances': 0,
                   'images_downloaded': 0, '3d_assets_downloaded': 0,
                   'sampling': 'First 200 rows of metadata shard 0; biased small engineering trial, not coverage estimate',
                   'version_basis': 'Frozen actual sample SHA256; source is static published metadata without claimed semantic-version tag',
                   'identity_overlap': 'Exact source UIDs checked; worldwide concept overlap not inferred from names/model numbers',
                   'modifications': 'Bounded subset and configuration/type review; original list-valued metadata preserved'}
    (output / 'abo_furniture_manifest.json').write_text(json.dumps(attribution, ensure_ascii=False, indent=2) + '\n')
    (output / 'ABO_ATTRIBUTION.txt').write_text(json.dumps(attribution, ensure_ascii=False, indent=2) + '\n')
    return attribution


def apply_abo_inputs(m):
    """Admit the bounded native configurations to an independently built candidate."""
    path = m.inputs / 'abo_furniture_records.jsonl'
    if not path.exists():
        return {'abo_catalogue_configurations': 0}
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if len(rows) > MAX_IMPORTED_LISTINGS:
        raise ValueError('Furniture candidate exceeds frozen batch limit')
    manifest = json.loads((m.inputs / 'abo_furniture_manifest.json').read_text())
    fingerprint = digest(path.read_bytes() + b'\0' + (m.inputs / 'abo_furniture_manifest.json').read_bytes())
    stage = m.c.execute("SELECT value FROM metadata WHERE key='abo_furniture_application'").fetchone()
    stage = json.loads(stage[0]) if stage else None
    if stage and stage['input_sha256'] != fingerprint:
        raise ValueError('Furniture inputs differ from an already applied stage; rebuild from the protected baseline')
    imported = 0
    # Validate the entire batch before changing any candidate record.
    for row in rows:
        proof = row['proof']
        native = proof['native_record']
        if digest(canonical_record(native)) != proof['source_record_sha256'] or row['uid'] != listing_uid(native['domain_name'], native['item_id']):
            raise ValueError('Native furniture identity/payload changed')
        key = (native['domain_name'], native['item_id'])
        expected = REVIEWED.get(key)
        names = [v['value'] for v in native['item_name'] if v.get('language_tag') == 'en_US']
        if not expected or values(native, 'product_type') != [expected[0]] or row['parent'] != expected[1] or len(names) != 1 or expected[2] not in names[0] or row['label'] != names[0]:
            raise ValueError('Furniture row is outside the independently reviewed batch')
        if row['role'] != 'CONFIGURATION' or row['relation'] != 'CONFIGURATION_TYPE_OF' or row['parent'] != proof['parent_uid']:
            raise ValueError('Catalogue listing cannot be promoted into a global model or instance')
        parent = m.c.execute('SELECT n.*,' + role_expression('n', 'p') + ' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?', (row['parent'],)).fetchone()
        if not parent or parent['visibility'] != 'ACTIVE' or parent['role'] != 'CLASS' or digest(parent['data'].encode()) != proof['parent_native_record_sha256']:
            raise ValueError('Frozen furniture parent differs')
        existing = m.c.execute('SELECT data FROM nodes WHERE uid=?', (row['uid'],)).fetchone()
        if existing and json.loads(existing['data']).get('source_record_sha256') != proof['source_record_sha256']:
            raise ValueError('Candidate contains a conflicting catalogue identity')
        if existing:
            role = m.c.execute('SELECT node_kind FROM node_profiles WHERE uid=?', (row['uid'],)).fetchone()
            if not role or role[0] != 'CONFIGURATION':
                raise ValueError('Existing catalogue identity has an incompatible role')
        if stage:
            connection = m.c.execute('SELECT status,data FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',
                                     (row['uid'], row['parent'], row['relation'], row['source'])).fetchone()
            profile = m.c.execute('SELECT attributes FROM node_profiles WHERE uid=?', (row['uid'],)).fetchone()
            attributes = json.loads(profile[0]) if profile else {}
            if not existing or json.loads(existing['data']) != proof or not connection or connection['status'] != 'ACTIVE' or json.loads(connection['data']).get('admission_basis') != proof or attributes.get('allowed_views') != proof['allowed_views'] or attributes.get('license') != proof['license'] or attributes.get('source_identity') != proof['source_identity']:
                raise ValueError('Applied furniture stage no longer matches its frozen source/connection')
    if stage:
        catalog = m.c.execute('SELECT license,input_sha256 FROM source_catalogs WHERE source=?', (SOURCE,)).fetchone()
        if not catalog or 'CC BY 4.0' not in catalog['license'] or catalog['input_sha256'] != manifest['source_sample_sha256']:
            raise ValueError('Applied furniture stage lost its license/provenance')
        return {**stage['summary'], 'abo_new_source_uids': 0, 'status': 'VERIFIED_NO_OP'}
    for row in rows:
        proof = row['proof']
        native = proof['native_record']
        imported += m.add_node(row['uid'], row['label'], row['role'], row['domain'], row['source'], row['uri'], proof, row['definition'])
        m.typed(row['uid'], row['parent'], row['relation'], proof, row['source'], row['uri'])
        attrs = json.loads(m.c.execute('SELECT attributes FROM node_profiles WHERE uid=?', (row['uid'],)).fetchone()[0])
        attrs.update(semantic_grain='source_catalogue_product_configuration', source_identity=proof['source_identity'],
                     source_record_sha256=proof['source_record_sha256'], license=proof['license'],
                     license_uri=proof['license_uri'], attribution=proof['attribution'],
                     no_global_design_identity=True, no_physical_instance=True)
        m.c.execute('UPDATE node_profiles SET attributes=? WHERE uid=?', (json.dumps(attrs, ensure_ascii=False), row['uid']))
        # Keep native multilingual names with language tags, without creating any identity bridge.
        for name in native['item_name']:
            m.alias(row['uid'], name['value'], row['source'], name.get('language_tag', 'und'))
    m.c.execute('INSERT OR REPLACE INTO source_catalogs VALUES(?,?,?,?,?)',
                (SOURCE, SOURCE_URI, 'CC BY 4.0; ' + LICENSE_URI + '; attribution: ' + ATTRIBUTION,
                 manifest['source_sample_sha256'], json.dumps(manifest, ensure_ascii=False)))
    m.meta('abo_furniture_trial', manifest)
    summary = {'abo_catalogue_configurations': len(rows), 'abo_new_source_uids': imported,
               'new_global_models': 0, 'new_physical_instances': 0, 'identity_bridges_added': 0}
    m.meta('abo_furniture_application', {'input_sha256': fingerprint, 'summary': summary})
    m.c.commit()
    return {**summary, 'status': 'APPLIED'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('database', 'sample', 'output', 'source-readme', 'source-license'):
        parser.add_argument('--' + option, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.database, args.sample, args.output, args.source_readme, args.source_license)), flush=True)
