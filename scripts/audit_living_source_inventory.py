#!/usr/bin/env python3
"""Independent raw inventory and exact locale-name audit of frozen living inputs.

No migration/build adjudication functions are imported. Source spellings belong
in node_names; aliases intentionally retain one spelling per normalized key.
The collision cases are additionally queried through the public domain search.
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
from fineatlas import FineAtlas


def audit(database: Path, inputs: Path, output: Path) -> dict:
    expected, hashes = {}, {}
    for name in ('living_catalogue_records.jsonl', 'living_catalogue_extension_records.jsonl'):
        path = inputs / name
        if not path.exists():
            continue
        with path.open('rb') as stream:
            hashes[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row['status'] == 'ADMIT_SOURCE_CONFIGURATION':
                if row['uid'] in expected and expected[row['uid']] != row:
                    raise ValueError('Contradictory source inventory: ' + row['uid'])
                expected[row['uid']] = row
    errors, collisions = [], []
    domains, names_checked = Counter(), 0
    con = sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    con.row_factory = sqlite3.Row
    revision = json.loads(con.execute("SELECT value FROM metadata WHERE key='database_revision'").fetchone()[0])
    for uid, row in expected.items():
        node = con.execute('SELECT n.*,p.node_kind FROM nodes n LEFT JOIN node_profiles p USING(uid) WHERE uid=?', (uid,)).fetchone()
        if not node:
            errors.append({'uid': uid, 'reason': 'MISSING_SOURCE_NODE'})
            continue
        native = json.loads(node['data'])
        if (node['node_kind'] != 'CONFIGURATION' or native.get('world_model_identity_verified') is not False or
                native.get('source_record_sha256') != row['record_sha256']):
            errors.append({'uid': uid, 'reason': 'ROLE_IDENTITY_OR_NATIVE_HASH_MISMATCH'})
        parents = {a[0] for a in con.execute("SELECT object_uid FROM entity_relations WHERE subject_uid=? AND status='ACTIVE' AND relation='CONFIGURATION_TYPE_OF'", (uid,))}
        if not set(row['parent_uids']) <= parents:
            errors.append({'uid': uid, 'reason': 'GROUNDED_PHYSICAL_PARENTS_MISSING'})
        names = {(a['name'], a['language'].replace('_', '-').lower())
                 for a in con.execute('SELECT name,language FROM node_names WHERE uid=?', (uid,))}
        for name in row['proof']['native_record'].get('item_name', []):
            names_checked += 1
            key = (name['value'], name['language_tag'].replace('_', '-').lower())
            if key not in names:
                errors.append({'uid': uid, 'reason': 'RAW_NAME_LOCALE_MISSING', 'name': name})
            if not con.execute('SELECT 1 FROM aliases WHERE uid=? AND raw_alias=?', (uid, name['value'])).fetchone():
                collisions.append({'uid': uid, 'name': name, 'domain': row['domain']})
        domains[row['domain']] += 1
    con.close()
    with FineAtlas(database, relation_view='unified') as atlas:
        if atlas._revision != revision:
            raise ValueError('Source changed during audit')
        for collision in collisions:
            rows = atlas.search(collision['name']['value'], domain=collision['domain'], limit=1000)
            collision['found_in_domain_search'] = any(row['uid'] == collision['uid'] for row in rows)
            if not collision['found_in_domain_search']:
                errors.append({'uid': collision['uid'], 'reason': 'NORMALIZED_SOURCE_ALIAS_NOT_SEARCHABLE'})
    report = {'schema': 'FINEATLAS_INDEPENDENT_LIVING_SOURCE_INVENTORY_V1',
              'pass': not errors, 'database': str(database.resolve()),
              'database_revision': revision, 'source_inputs_sha256': hashes,
              'source_configurations_checked': len(expected), 'domain_counts': dict(domains),
              'raw_source_names_checked': names_checked,
              'normalized_alias_collisions_checked': collisions, 'errors': errors,
              'scope': 'Every admitted frozen new configuration and native name/locale; full paging, protected old configurations and semantic source validation require separate audits.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    result = audit(**vars(parser.parse_args()))
    print(json.dumps({key: result[key] for key in ('pass', 'source_configurations_checked', 'raw_source_names_checked')}))
    raise SystemExit(0 if result['pass'] else 1)
