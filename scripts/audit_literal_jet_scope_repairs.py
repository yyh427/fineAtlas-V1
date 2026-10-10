#!/usr/bin/env python3
"""Independently audit literal physical jet scopes using source SQL and receipts."""
from __future__ import annotations
import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import re
import sqlite3

INPUT_NAME = 'structure_literal_jet_scope_repairs.json'
SOURCE = 'Reviewed literal source jet-aircraft physical scope'


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def role(c, n):
    p = c.execute('SELECT node_kind FROM node_profiles WHERE uid=?', (n['uid'],)).fetchone()
    if p and p[0]:
        return p[0]
    return {'model': 'MODEL', 'model_family': 'MODEL_FAMILY', 'series': 'MODEL_FAMILY', 'model_year': 'CONFIGURATION', 'configuration': 'CONFIGURATION'}.get(n['rank'].lower(), 'CLASS')


def content(row):
    return sha(json.dumps({k: row[k] for k in row.keys() if k not in ('id', 'status', 'reason')}, sort_keys=True))


def parent_root_route(c, start):
    queue = deque([(start, [])]); visited = set()
    while queue:
        uid, path = queue.popleft()
        if uid == 'wordnet31:00001740-n':
            return path
        if uid in visited:
            continue
        visited.add(uid)
        n = c.execute('SELECT * FROM nodes WHERE uid=?', (uid,)).fetchone()
        if not n or n['visibility'] != 'ACTIVE' or role(c, n) != 'CLASS':
            continue
        for peer in c.execute('SELECT uid FROM nodes WHERE component_id=?', (n['component_id'],)):
            for e in c.execute("SELECT * FROM edges WHERE child_uid=? AND relation='IS_A' AND status IN ('ACTIVE','BACKBONE_ACTIVE')", (peer[0],)):
                queue.append((e['parent_uid'], path + [dict(e)]))
    return None


def run(database, inputs, output, preflight=False):
    database = database.resolve(); path = inputs / INPUT_NAME
    manifest = json.loads(path.read_text()); raw = (inputs / manifest['operations_file']).read_bytes()
    ops = [json.loads(line) for line in raw.decode().splitlines() if line]
    c = sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1', uri=True); c.row_factory = sqlite3.Row
    errors = []; routes = {}
    if sha(raw) != manifest['operations_sha256'] or type(manifest['operation_count']) is not int or len(ops) != manifest['operation_count'] or len({(x['uid'], x['parent'], x['relation']) for x in ops}) != len(ops):
        errors.append({'kind': 'INPUT_NOT_EXACTLY_BOUND'})
    for op in ops:
        uid = op['uid']; proof = op['proof']
        n = c.execute('SELECT * FROM nodes WHERE uid=?', (uid,)).fetchone()
        p = c.execute('SELECT * FROM nodes WHERE uid=?', (op['parent'],)).fetchone()
        if not n or not p:
            errors.append({'kind': 'ENDPOINT_MISSING', 'uid': uid}); continue
        if sha(n['data']) != proof['native_record_sha256'] or sha(p['data']) != proof['parent_native_record_sha256'] or n['visibility'] != 'ACTIVE' or p['visibility'] != 'ACTIVE':
            errors.append({'kind': 'WHOLE_SOURCE_ENDPOINT_CHANGED', 'uid': uid})
        if role(c,n) not in ('MODEL','MODEL_FAMILY') or role(c,p) != 'CLASS' or op['relation'] != 'DESIGN_TYPE_OF':
            errors.append({'kind': 'SOURCE_GRAIN_OR_TYPE_RELATION_WRONG', 'uid': uid})
        if proof['world_identity_assertion'] is not False or proof['no_identity_merges'] is not True:
            errors.append({'kind': 'TYPE_PROMOTED_TO_EXACT_IDENTITY', 'uid': uid})
        witnesses = proof['source_witnesses']
        for w in witnesses:
            row = c.execute('SELECT data FROM nodes WHERE uid=?', (w['uid'],)).fetchone(); data = json.loads(row[0]) if row else {}
            statement = data.get(w['field']) or data.get('evidence_record', {}).get(w['field'])
            if not row or sha(row[0]) != w['data_sha256'] or statement != w['statement']:
                errors.append({'kind': 'SOURCE_FIELD_OR_BYTES_CHANGED', 'uid': uid})
        own = witnesses[0]['statement']; native = json.loads(n['data'])
        if witnesses[0]['uid'] != uid or witnesses[0]['field'] != 'description' or native.get('description') != own:
            errors.append({'kind': 'NOT_OWNED_SOURCE_TYPE_DECLARATION', 'uid': uid})
        # Independent check of the retained first literal noun phrase, not a call
        # to the construction-time classifier. Independent semantic review binds
        # complete statements and source scopes in the final source seal.
        first = re.split(r'[.;]|\s+(?:that|which|whose|for|by|from|since)\b', own, maxsplit=1, flags=re.I)[0]
        if not re.search(r'\bjet\s+aircraft\s*$', first, re.I) or re.search(r'\b(?:not|never|without|toy|engine|parts|fictional|virtual|software|and|or)\b', first, re.I):
            errors.append({'kind': 'JET_ONLY_IN_INCIDENTAL_OR_INCOMPATIBLE_CLAUSE', 'uid': uid})
        parent_statement = witnesses[1]['statement']
        if witnesses[1]['uid'] != op['parent'] or witnesses[1]['field'] != 'wikipedia_intro' or not re.match(r'^A jet aircraft \(or simply jet\) is an aircraft propelled by one or more jet engines\.', parent_statement):
            errors.append({'kind': 'PARENT_NOT_COMPLETE_BROADER_JET_PROPULSION_RANGE', 'uid': uid})
        component = manifest['parent_components'][op['parent']]
        peers = sorted(r[0] for r in c.execute('SELECT uid FROM nodes WHERE component_id=?', (p['component_id'],)))
        bridges = c.execute('SELECT * FROM bridges WHERE left_uid=? OR right_uid=?', (op['parent'],op['parent'])).fetchall()
        if peers != component['uids'] or sorted(content(r)+':'+r['status'] for r in bridges) != component['bridge_content_status_hashes']:
            errors.append({'kind': 'PARENT_IDENTITY_COMPONENT_OR_BRIDGES_CHANGED', 'uid': uid})
        for prior in proof['prior_assertions']:
            rows = c.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?', tuple(prior[k] for k in ('subject_uid','object_uid','relation','source'))).fetchall()
            if not any(content(r) == prior['content_sha256'] and r['status'] == prior['status'] for r in rows):
                errors.append({'kind': 'PRIOR_DECLARATION_OR_REVIEW_LOST', 'uid': uid})
        if op['parent'] not in routes:
            routes[op['parent']] = parent_root_route(c, op['parent'])
        if routes[op['parent']] is None:
            errors.append({'kind': 'PHYSICAL_CLASS_NO_ACTIVE_CLASS_ROOT_ROUTE', 'uid': uid})
        if not preflight:
            rows = c.execute('SELECT r.*,e.payload FROM entity_relations r JOIN evidence e ON e.evidence_id=r.evidence_id WHERE r.subject_uid=? AND r.object_uid=? AND r.relation=? AND r.source=?', (uid,op['parent'],op['relation'],SOURCE)).fetchall()
            if len(rows) != 1 or rows[0]['status'] != 'ACTIVE' or json.loads(rows[0]['payload']) != proof:
                errors.append({'kind': 'ACTUAL_TYPED_SCOPE_OR_EVIDENCE_DIFFERS', 'uid': uid})
            history = c.execute("SELECT evidence,after_json FROM usability_changes WHERE stage='literal_jet_scope_repairs' AND object_type='physical_type_append' AND object_id=?", (uid,)).fetchall()
            if len(history) != 1 or json.loads(history[0]['evidence']) != proof or json.loads(history[0]['after_json']) != {'added_parent': op['parent'], 'relation': op['relation']}:
                errors.append({'kind': 'NEW_TYPE_HISTORY_NOT_BOUND', 'uid': uid})
    metadata = {r['key']: json.loads(r['value']) for r in c.execute('SELECT * FROM metadata')}
    if not preflight:
        frozen = metadata.get('structure_frozen_build_manifest',{}).get('inputs',{}); applied = metadata.get('literal_jet_scope_repairs',{})
        if any(frozen.get(name) != sha((inputs/name).read_bytes()) for name in (INPUT_NAME,manifest['operations_file'])) or applied.get('manifest_sha256') != sha(path.read_bytes()) or applied.get('operations_sha256') != sha(raw) or type(applied.get('operation_count')) is not int or applied['operation_count'] != len(ops):
            errors.append({'kind': 'ACTUAL_APPLY_OR_FINAL_FROZEN_INPUT_HASHES_DIFFER'})
        actual = c.execute('SELECT count(*) FROM entity_relations WHERE source=? AND status=\'ACTIVE\'', (SOURCE,)).fetchone()[0]
        if actual != len(ops):
            errors.append({'kind': 'ACTUAL_APPEND_COUNT_DIFFERS', 'count': actual})
    report = {'schema':'FINEATLAS_INDEPENDENT_LITERAL_JET_SCOPE_AUDIT_V1','pass':not errors,'preflight_only':preflight,'database':str(database),'database_revision':metadata.get('database_revision'),'release':metadata.get('release'),'manifest_sha256':sha(path.read_bytes()),'operations_sha256':sha(raw),'operation_count':len(ops),'operations':dict(Counter(x['relation'] for x in ops)),'added_assertions':len(ops),'new_semantic_links':len(ops),'new_nodes':0,'world_identity_promotions':0,'source_parent_range_not_fixed_wing_only':True,'parent_active_class_root_routes':routes,'errors':errors}
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(report,indent=2)+'\n'); c.close()
    print(json.dumps({k:v for k,v in report.items() if k not in ('errors','parent_active_class_root_routes')})); return not errors


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--database',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args()
    raise SystemExit(0 if run(a.database,a.inputs,a.output,a.preflight) else 1)
