#!/usr/bin/env python3
"""Prepare bounded, reviewed role repairs without modifying the source database.

Reviews name exact identity members and frozen payloads. Generic kinds require
whole-subject definitions and reviewed parent definitions. Nameplate families
require independent family scope, native configurations and stable source IDs.
Scope disagreements are withdrawn by exact bridge ID rather than changing the
meaning of a source UID. Output operations use the existing root-contract replay.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fineatlas.engineering_roles import definition_head
from fineatlas.hierarchy import validate_link_roles, source_assertion_sha256, locate_source_assertion, apply_refinements
from fineatlas.semantics import role_expression


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def assertion_locator(row, table):
    keys = ('subject_uid', 'object_uid') if table == 'entity_relations' else ('left_uid', 'right_uid')
    return {**{k: row[k] for k in (*keys, 'relation', 'source')},
            'content_sha256': source_assertion_sha256(row)}


def node(c, uid):
    r = c.execute('SELECT n.*,' + role_expression('n', 'p') +
                  ' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',
                  (uid,)).fetchone()
    if not r:
        raise ValueError('Missing source UID: ' + uid)
    return dict(r)


def checked_node(c, review):
    n = node(c, review['uid'])
    if n['visibility'] != 'ACTIVE' or digest(n['data']) != review['native_record_sha256']:
        raise ValueError('Source visibility or payload changed: ' + n['uid'])
    if review.get('label', n['label']) != n['label']:
        raise ValueError('Source label changed: ' + n['uid'])
    return n


def checked_group(c, review):
    n = node(c, review['uid'])
    members = [node(c, r[0]) for r in c.execute(
        'SELECT uid FROM nodes WHERE component_id=? ORDER BY uid', (n['component_id'],))]
    frozen = {r['uid']: r for r in review['members']}
    if set(frozen) != {r['uid'] for r in members}:
        raise ValueError('Identity membership changed: ' + n['uid'])
    for m in members:
        checked_node(c, frozen[m['uid']])
        if m['role'] != frozen[m['uid']]['role']:
            raise ValueError('Canonical source role changed: ' + m['uid'])
    return n, members


def checked_external(review, root):
    result = []
    for r in review.get('external_sources', []):
        path = (root / r['file']).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError('External snapshot escapes review directory')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != r['sha256']:
            raise ValueError('External snapshot changed: ' + r['file'])
        if not r.get('url') or not r.get('scope_observation'):
            raise ValueError('External source needs a reviewed scope observation')
        result.append(r)
    return result


def independent_definition(n):
    payload = json.loads(n['data'] or '{}')
    statement = payload.get('definition') or n.get('description') or ''
    if not statement:
        statements = [e.get('text', '') for e in payload.get('evidence', [])
                      if e.get('source') == 'wikipedia_intro']
        statement = ' '.join(statements)
    return statement


def generic_kind_operations(c, review, root):
    n, members = checked_group(c, review)
    definition = independent_definition(n)
    head = definition_head(definition, n['label'])
    if not definition or definition != review['definition'] or head != review['definition_head']:
        raise ValueError('Whole-subject generic definition changed')
    if review.get('semantic_scope') != 'GENERIC_PHYSICAL_KIND' or not review.get('scope_observation'):
        raise ValueError('Generic repair lacks an individual scope review')
    # Restrict the automatic replay to the conservative reviewed generic cohort.
    # An article saying a named product "is a vacuum cleaner" is not enough.
    if n['label'] != n['label'].lower() or re.search(r'\b(?:series|family|line|range) of\b', head or '', re.I):
        raise ValueError('Named design/group cannot use generic-kind repair')
    if not (re.match(r'\s*An?\s+' + re.escape(n['label']) + r'\b', definition, re.I)
            or re.search(r'\b(?:type|kind|class|category) of\b', head or '', re.I)):
        raise ValueError('Generic definition does not establish a repeatable kind')
    qid = n['uid'].split(':')[-1]
    if any(m['uid'].split(':')[-1] != qid or not m['uid'].startswith(
            ('wikidata:', 'wikidata-v4:', 'v26-wikidata:')) for m in members):
        raise ValueError('Generic role cannot spread to a different source identifier')
    if any(m['role'] not in {'CLASS', 'MODEL', 'MODEL_FAMILY'} for m in members):
        raise ValueError('Instance, configuration or unresolved source grain needs independent adjudication')
    external = checked_external(review, root)
    proof = {'basis': 'REVIEWED_GENERIC_WHOLE_SUBJECT_REPLACES_ADAPTER_DESIGN_ROLE',
             'source_statement': definition, 'subject_kind_head': head,
             'individual_semantic_review': True, 'scope_observation': review['scope_observation'],
             'identity_member_uids': sorted(m['uid'] for m in members),
             'original_source_payload_and_endpoints_preserved': True,
             'no_name_based_identity': True, 'source_role': 'Independently defined reusable physical kind',
             'allowed_views': ['strict', 'taxonomy', 'membership', 'unified'],
             'external_sources': external, 'license': review['license']}
    records = []
    for m in members:
        p = {**proof, 'native_record_sha256': digest(m['data']), 'prior_role': m['role'],
             'native_rank': m['rank']}
        if m['role'] != 'CLASS':
            records.append({'op': 'role', 'uid': m['uid'], 'role': 'CLASS',
                            'source': 'Reviewed shared generic-kind contracts', 'uri': review['uri'], 'proof': p})
        for t in c.execute("SELECT * FROM entity_relations WHERE subject_uid=? AND status='ACTIVE'", (m['uid'],)):
            target = node(c, t['object_uid'])
            try:
                validate_link_roles(t['relation'], 'CLASS', target['role'])
            except ValueError:
                if t['relation'] not in {'DESIGN_TYPE_OF', 'SERIES_MEMBER_OF', 'NATIVE_DESIGN_PARENT'}:
                    raise ValueError('Unreviewed outgoing typed role conflict: ' + str(t['id']))
                records.append({'op': 'withdraw_typed_source', 'uid': m['uid'],
                                'locator': assertion_locator(t, 'entity_relations'),
                                'source': 'Reviewed shared generic-kind contracts', 'uri': review['uri'],
                                'proof': {**p, 'basis': 'GENERIC_KIND_IS_NOT_DESIGN_TERMINAL',
                                          'original_relation_sha256': digest(json.dumps(dict(t), sort_keys=True)),
                                          'original_relation': t['relation'], 'original_parent_uid': t['object_uid']}})
        for t in c.execute("SELECT * FROM entity_relations WHERE object_uid=? AND status='ACTIVE'", (m['uid'],)):
            source = node(c, t['subject_uid'])
            try:
                validate_link_roles(t['relation'], source['role'], 'CLASS')
            except ValueError as exc:
                raise ValueError('Incoming typed relation needs separate review: ' + str(t['id'])) from exc
    for parent_review in review['parents']:
        parent = checked_node(c, parent_review)
        if parent['role'] != 'CLASS' or parent['description'] != parent_review['definition']:
            raise ValueError('Reviewed parent definition or role changed')
        if not parent_review.get('entailment_observation'):
            raise ValueError('Reviewed class link lacks a scope entailment')
        if parent['component_id'] == n['component_id']:
            raise ValueError('Generic parent would be an identity self arc')
        # A complete source parent inventory is exported for review by the
        # caller; this operation adds only this specifically reviewed parent.
        records.append({'op': 'link', 'uid': n['uid'], 'parent': parent['uid'], 'relation': 'IS_A',
                        'source': 'Reviewed shared generic-kind contracts', 'uri': review['uri'],
                        'proof': {**proof, 'native_record_sha256': digest(n['data']),
                                  'parent_native_record_sha256': digest(parent['data']),
                                  'parent_definition': parent['description'],
                                  'entailment_observation': parent_review['entailment_observation'],
                                  'not_created_for_root_reachability': True}})
    return records


def checked_native_witness(c, w):
    r = locate_source_assertion(c, 'entity_relations', w['locator'])
    if not r or r['status'] != 'ACTIVE' or r['relation'] != 'CONFIGURATION_OF':
        raise ValueError('Native configuration witness changed')
    ev = c.execute('SELECT * FROM evidence WHERE evidence_id=? LIMIT 1', (r['evidence_id'],)).fetchone()
    if not ev or digest(ev['payload']) != ev['payload_sha256'] or ev['payload_sha256'] != w['evidence_sha256']:
        raise ValueError('Native witness evidence checksum differs')
    source = checked_node(c, {'uid': r['subject_uid'], 'native_record_sha256': w['native_record_sha256']})
    fields = json.loads(ev['payload'])
    raw = json.loads(source['data'])
    if source['source'] != 'epa' or any(str(fields.get(k, '')) != str(raw.get(k, ''))
                                       for k in ('year', 'make', 'model', 'baseModel')):
        raise ValueError('EPA normalized witness differs from retained native fields')
    if not fields.get('year') or not fields.get('make') or not fields.get('baseModel'):
        raise ValueError('EPA scope witness lacks native aggregation keys')
    return fields, ev['source_uri']


def family_operations(c, review, root):
    n, members = checked_group(c, review)
    if review.get('semantic_scope') != 'REUSABLE_NAMEPLATE_FAMILY' or not review.get('scope_observation'):
        raise ValueError('Family role needs a reviewed nameplate scope')
    if any(m['role'] not in {'MODEL', 'MODEL_FAMILY'} for m in members):
        raise ValueError('Family inheritance cannot overwrite another source grain')
    external = checked_external(review, root)
    if not external or not any(x.get('kind') == 'MANUFACTURER_FAMILY_DEFINITION' for x in external):
        raise ValueError('Family scope needs an independent manufacturer definition')
    witnesses = [checked_native_witness(c, w) for w in review['native_witnesses']]
    years = {int(w['year']) for w, _ in witnesses}
    keys = {(w['make'], w['baseModel']) for w, _ in witnesses}
    if len(years) < 2 or len(keys) != 1:
        raise ValueError('Native family witness does not describe one aggregate source key')
    member_uids = {m['uid'] for m in members}
    if any(locate_source_assertion(c, 'entity_relations', w['locator'])['object_uid']
           not in member_uids for w in review['native_witnesses']):
        raise ValueError('Native aggregation witness belongs to a different identity group')
    for m in members:
        if not m['uid'].startswith('vpic-model:'):
            continue
        make_id, model_id = [int(x) for x in m['uid'].split(':')[1:]]
        samples = [s for s in external if s.get('kind') == 'VPIC_MODEL_YEAR_SAMPLE']
        matches = []
        for s in samples:
            document = json.loads((root / s['file']).read_text())
            found = [r for r in document.get('Results', [])
                     if r.get('Make_ID') == make_id and r.get('Model_ID') == model_id]
            if found:
                matches.append(s.get('model_year'))
        if len(set(matches)) < 2 or None in matches:
            raise ValueError('vPIC model ID is not verified in multiple native model-year lists')
    proof = {'basis': 'INDEPENDENT_MANUFACTURER_FAMILY_AND_NATIVE_AGGREGATION_SCOPE',
             'individual_semantic_review': True, 'scope_observation': review['scope_observation'],
             'external_sources': external, 'native_witnesses': review['native_witnesses'],
             'native_make_base_model': sorted(keys), 'sample_native_years': sorted(years),
             'identity_member_uids': sorted(member_uids), 'no_identity_merges': True,
             'no_generation_or_chassis_equivalence_asserted': True,
             'manufacturers_are_facets_only': True, 'original_source_payload_and_endpoints_preserved': True,
             'source_role': 'Native nameplate aggregate with independently established family scope',
             'allowed_views': ['strict', 'taxonomy', 'membership', 'unified'], 'license': review['license']}
    return [{'op': 'role', 'uid': m['uid'], 'role': 'MODEL_FAMILY',
             'source': 'Reviewed native nameplate family scope', 'uri': review['uri'],
             'proof': {**proof, 'native_record_sha256': digest(m['data']), 'prior_role': m['role'],
                       'native_rank': m['rank']}} for m in members if m['role'] != 'MODEL_FAMILY']


def split_operations(c, review, root):
    _, members = checked_group(c, review)
    checked_external(review, root)
    if review.get('semantic_scope') != 'DIFFERENT_SOURCE_SCOPE' or not review.get('scope_observation'):
        raise ValueError('Identity split requires a reviewed scope counterexample')
    for witness in review.get('native_witnesses', []):
        checked_native_witness(c, witness)
    uids = {m['uid'] for m in members}
    records = []
    resolved = review.get('resolved_member_roles', {})
    if resolved and set(resolved) != uids:
        raise ValueError('Scope separation must review every original identity member role')
    for m in members:
        if m['uid'] not in resolved:
            continue
        target = resolved[m['uid']]
        if m['role'] not in {'CLASS', 'MODEL', 'MODEL_FAMILY'} or target not in {'MODEL', 'MODEL_FAMILY'}:
            raise ValueError('Source separation cannot replace an independently different grain')
        if not review.get('role_scope_observations', {}).get(m['uid']):
            raise ValueError('Separated source member needs its own role/scope observation')
        if m['role'] != target:
            records.append({'op': 'role', 'uid': m['uid'], 'role': target,
                            'source': 'Reviewed separated native design scope', 'uri': review['uri'],
                            'proof': {'basis': 'INDEPENDENT_DESIGN_SCOPE_AFTER_FALSE_IDENTITY_REJECTION',
                                      'native_record_sha256': digest(m['data']), 'prior_role': m['role'],
                                      'native_rank': m['rank'], 'source_role': 'Independently reviewed native design scope',
                                      'scope_observation': review['role_scope_observations'][m['uid']],
                                      **({'native_scope_witnesses': review['native_witnesses']} if review.get('native_witnesses') else {}),
                                      'external_sources': review.get('external_sources', []),
                                      'identity_separation_required': True, 'manufacturers_are_facets_only': True,
                                      'allowed_views': ['strict', 'taxonomy', 'membership', 'unified'],
                                      'original_source_payload_and_endpoints_preserved': True,
                                      'license': review['license']}})
    for frozen in review['bridges']:
        r = locate_source_assertion(c, 'bridges', frozen['locator'])
        if not r or r['status'] != 'ACTIVE' or r['relation'] != 'SAME_CONCEPT':
            raise ValueError('Frozen identity assertion no longer active')
        if not {r['left_uid'], r['right_uid']}.issubset(uids):
            raise ValueError('Identity split leaves the reviewed source group')
        records.append({'op': 'split_identity_source', 'uid': r['left_uid'], 'parent': r['right_uid'],
                        'locator': frozen['locator'], 'source': 'Reviewed source scope identity separation',
                        'uri': review['uri'], 'proof': {
                            'basis': 'SOURCE_SCOPE_COUNTEREXAMPLE_REJECTS_NAME_ONLY_IDENTITY',
                            'individual_semantic_review': True, 'scope_observation': review['scope_observation'],
                            **({'native_scope_witnesses': review['native_witnesses']} if review.get('native_witnesses') else {}),
                            'original_bridge_content_sha256': frozen['locator']['content_sha256'], 'external_sources': review.get('external_sources', []),
                            'original_source_payload_and_endpoints_preserved': True,
                            'no_replacement_identity_inferred': True, 'license': review['license']}})
    return records


def prepare(database, reviews, output):
    database, reviews, output = map(Path, (database, reviews, output))
    if output.resolve() in {database.resolve(), reviews.resolve()}:
        raise ValueError('Output must not overwrite a protected input')
    manifest = json.loads(reviews.read_text())
    c = sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    methods = {'generic_kind': generic_kind_operations, 'nameplate_family': family_operations,
               'scope_split': split_operations}
    records = []
    outcomes = []
    for review in manifest['reviews']:
        if review.get('verdict') != 'APPROVED':
            outcomes.append({'uid': review['uid'], 'status': 'REVIEW', 'reason': review['reason']})
            continue
        if review['kind'] not in methods:
            raise ValueError('Unsupported source review kind')
        cohort = methods[review['kind']](c, review, reviews.parent)
        records.extend(cohort)
        outcomes.append({'uid': review['uid'], 'status': 'PREPARED', 'kind': review['kind'],
                         'operations': len(cohort), 'member_uids': [m['uid'] for m in review['members']]})
    c.close()
    records = list({json.dumps(r, sort_keys=True, ensure_ascii=False): r for r in records}.values())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in records))
    summary = {'database': str(database.resolve()), 'reviews_sha256': hashlib.sha256(reviews.read_bytes()).hexdigest(),
               'prepared_operations': len(records), 'by_operation': dict(Counter(r['op'] for r in records)),
               'outcomes': outcomes, 'original_source_database_modified': False,
               'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
               'replay_interface': 'apply_shared_repairs(m): shared_role_repairs.jsonl before final typed-role navigation and graph rebuild',
               'note': 'PREPARED is not BUILT or VERIFIED; full graph and task regressions remain required'}
    output.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    return summary


def apply_shared_repairs(m):
    """Replay the stable, independently prepared queue in the migration connection."""
    return apply_refinements(m, 'shared_role_repairs.jsonl')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for field in ('database', 'reviews', 'output'):
        p.add_argument('--' + field, type=Path, required=True)
    args = p.parse_args()
    result = prepare(args.database, args.reviews, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != 'outcomes'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
