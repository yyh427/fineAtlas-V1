"""Transactional repairs on an isolated full candidate, with reversible row receipts.

Large inherited graph tables are not copied or rebuilt here. Added subgraphs are
checked and only their new-component query/browse indexes are materialized.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from ._text import norm
from .task_contract import exact_name
from .semantics import VIEWS, VIEW_BITS, classification_roles, terminal_relations

LAYER = 'native755-integration-20261012'
CORE_COUNTS = {'cub200': 200, 'fgvc_aircraft': 100, 'flowers102': 102,
               'pets37': 37, 'stanford_dogs': 120, 'stanford_cars': 196}
CORE_DOMAINS = {'cub200': 'birds', 'fgvc_aircraft': 'aircraft', 'flowers102': 'plants',
                'pets37': 'animals', 'stanford_dogs': 'animals', 'stanford_cars': 'cars'}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class RepairWriter:
    def __init__(self, database: str | Path, *, expected_revision: str):
        self.path = Path(database).resolve()
        self.c = sqlite3.connect(self.path)
        self.c.row_factory = sqlite3.Row
        self.c.execute('PRAGMA cache_size=-65536')
        self.c.execute('PRAGMA temp_store=MEMORY')
        self.c.execute('PRAGMA journal_mode=DELETE')
        self.metadata = {r[0]: json.loads(r[1]) for r in self.c.execute('SELECT key,value FROM metadata')}
        if self.metadata['database_revision'] != expected_revision:
            self.c.close()
            raise ValueError('Candidate revision changed: reconcile before writing')
        self.c.executescript('''
        CREATE TABLE IF NOT EXISTS repair_packages(package_id TEXT PRIMARY KEY,input_sha256 TEXT NOT NULL,
          status TEXT NOT NULL,summary TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS repair_changes(sequence INTEGER PRIMARY KEY,package_id TEXT NOT NULL,
          table_name TEXT NOT NULL,key_json TEXT NOT NULL,before_json TEXT,after_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS repair_changes_package ON repair_changes(package_id,sequence);
        CREATE TABLE IF NOT EXISTS native_classes(dataset TEXT NOT NULL,class_id TEXT NOT NULL,
          namespace TEXT NOT NULL,source_version TEXT NOT NULL,uid TEXT NOT NULL,label TEXT NOT NULL,
          raw_label TEXT NOT NULL,role TEXT NOT NULL,object_granularity TEXT NOT NULL,domain TEXT NOT NULL,
          training_id_verified INTEGER NOT NULL,proof TEXT NOT NULL,evidence_ids TEXT NOT NULL,
          PRIMARY KEY(dataset,class_id,source_version),UNIQUE(uid));
        CREATE TABLE IF NOT EXISTS native_class_names(uid TEXT NOT NULL,name TEXT NOT NULL,
          normalized_name TEXT NOT NULL,search_name TEXT NOT NULL,evidence_id TEXT NOT NULL,
          PRIMARY KEY(uid,name));
        CREATE INDEX IF NOT EXISTS native_class_names_exact ON native_class_names(normalized_name,uid);
        CREATE INDEX IF NOT EXISTS native_classes_uid ON native_classes(uid);
        CREATE INDEX IF NOT EXISTS dataset_scope_targets_uid ON dataset_scope_targets(source_uid);
        CREATE TABLE IF NOT EXISTS world_mapping_dispositions(dataset TEXT NOT NULL,class_id TEXT NOT NULL,
          uid TEXT,stored_status TEXT,effective_status TEXT NOT NULL,reason TEXT NOT NULL,
          missing_evidence TEXT NOT NULL,evidence_ids TEXT NOT NULL,PRIMARY KEY(dataset,class_id));
        CREATE TABLE IF NOT EXISTS integrated_dataset_versions(dataset TEXT NOT NULL,source_version TEXT NOT NULL,
          payload TEXT NOT NULL,PRIMARY KEY(dataset,source_version));
        CREATE TABLE IF NOT EXISTS increment_reconciliation(kind TEXT NOT NULL,object_key TEXT NOT NULL,
          disposition TEXT NOT NULL,reason TEXT NOT NULL,payload TEXT NOT NULL,
          PRIMARY KEY(kind,object_key));
        CREATE TABLE IF NOT EXISTS integrated_fg_objects(kind TEXT NOT NULL,key TEXT NOT NULL,
          payload TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(kind,key));
        CREATE TABLE IF NOT EXISTS dataset_answer_contracts(dataset TEXT PRIMARY KEY,payload TEXT NOT NULL);
        ''')
        self.c.commit()
        self.next_component = self.c.execute('SELECT max(id)+1 FROM components').fetchone()[0]
        self.added_nodes: dict[str, dict] = {}
        self.new_arcs: list[dict] = []
        self.stage = ''

    def begin(self, stage: str, inputs: Any) -> bool:
        row = self.c.execute('SELECT * FROM repair_packages WHERE package_id=?', (stage,)).fetchone()
        signature = digest(inputs)
        if row:
            if row['input_sha256'] != signature:
                raise ValueError('Package ID reused with different inputs')
            if row['status'] == 'APPLIED':
                return False
            if row['status'] != 'ROLLED_BACK':
                raise ValueError('Unknown package disposition')
            self.c.execute('DELETE FROM repair_changes WHERE package_id=?', (stage,))
            self.c.execute('DELETE FROM repair_packages WHERE package_id=?', (stage,))
            self.c.commit()
        self.stage = stage
        self.input_signature = signature
        self.c.execute('BEGIN IMMEDIATE')
        return True

    def put(self, table: str, key: dict, row: dict) -> None:
        if not self.stage or not self.c.in_transaction:
            raise ValueError('Begin an explicit repair package')
        where = ' AND '.join(k + '=?' for k in key)
        old = self.c.execute('SELECT * FROM ' + table + ' WHERE ' + where, tuple(key.values())).fetchone()
        before = dict(old) if old else None
        if before == row:
            return
        if before:
            self.c.execute('UPDATE ' + table + ' SET ' + ','.join(k + '=?' for k in row) + ' WHERE ' + where,
                           [*row.values(), *key.values()])
        else:
            self.c.execute('INSERT INTO ' + table + '(' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')',
                           tuple(row.values()))
        self.c.execute('INSERT INTO repair_changes(package_id,table_name,key_json,before_json,after_json) VALUES (?,?,?,?,?)',
                       (self.stage, table, canonical(key), canonical(before) if before is not None else None, canonical(row)))

    def meta(self, key: str, value: Any) -> None:
        self.put('metadata', {'key': key}, {'key': key, 'value': canonical(value)})

    def delete(self, table: str, key: dict) -> None:
        where = ' AND '.join(k + '=?' for k in key)
        old = self.c.execute('SELECT * FROM ' + table + ' WHERE ' + where, tuple(key.values())).fetchone()
        if not old:
            return
        self.c.execute('DELETE FROM ' + table + ' WHERE ' + where, tuple(key.values()))
        self.c.execute('INSERT INTO repair_changes(package_id,table_name,key_json,before_json,after_json) VALUES (?,?,?,?,?)',
                       (self.stage, table, canonical(key), canonical(dict(old)), 'null'))

    def finish(self, summary: dict) -> dict:
        prior_revision = json.loads(self.c.execute("SELECT value FROM metadata WHERE key='database_revision'").fetchone()[0])
        changes = [dict(r) for r in self.c.execute('SELECT table_name,key_json,after_json FROM repair_changes WHERE package_id=? ORDER BY sequence', (self.stage,))]
        revision = digest({'parent': prior_revision, 'package': self.stage, 'input': self.input_signature, 'changes': changes})
        self.meta('database_revision', revision)
        self.meta('repair_parent_revision', prior_revision)
        self.meta('release', 'v1.11.0rc1+native755.integrated.20261012')
        summary.update(database_revision=revision, parent_revision=prior_revision, changed_rows=len(changes))
        self.c.execute('INSERT INTO repair_packages VALUES (?,?,?,?)', (self.stage, self.input_signature, 'APPLIED', canonical(summary)))
        self.c.commit()
        self.stage = ''
        return summary

    def evidence(self, payload: dict, *, uri: str, source: str, claim: str) -> str:
        raw = canonical(payload)
        eid = 'repair755:' + hashlib.sha256(raw.encode()).hexdigest()
        row = dict(layer=LAYER, evidence_id=eid, source_name=source, source_uri=uri,
                   retrieved_utc=payload.get('retrieved_utc'), claim_type=claim,
                   payload=raw, payload_sha256=hashlib.sha256(raw.encode()).hexdigest())
        self.put('evidence', {'layer': LAYER, 'evidence_id': eid}, row)
        return eid

    def alias(self, uid: str, name: str, *, evidence_id: str, source: str) -> None:
        if not name.strip():
            return
        if not self.c.execute('SELECT 1 FROM aliases WHERE uid=? AND alias=?', (uid, norm(name))).fetchone():
            cur = self.c.execute('INSERT INTO aliases VALUES (?,?,?,?,?,?)',
                                 (norm(name), uid, name, source, LAYER, canonical({'evidence_id': evidence_id})))
            # Rowid is a locator here, never a source identity. Keep reversible
            # alias/FTS changes alongside ordinary keyed records.
            rowid = cur.lastrowid
            row = dict(self.c.execute('SELECT * FROM aliases WHERE rowid=?', (rowid,)).fetchone())
            self.c.execute('INSERT INTO repair_changes(package_id,table_name,key_json,before_json,after_json) VALUES (?,?,?,?,?)',
                           (self.stage, 'aliases', canonical({'rowid': rowid}), None, canonical(row)))
            self.c.execute('INSERT INTO alias_search(rowid,alias) VALUES (?,?)', (rowid, norm(name)))
        self.put('node_names', {'uid': uid, 'name': name, 'language': 'en', 'source': source},
                 dict(uid=uid, name=name, language='en', preferred=0, source=source, evidence_id=evidence_id))

    def add_node(self, row: dict, *, evidence_id: str) -> bool:
        uid = row['uid']
        if self.c.execute('SELECT 1 FROM nodes WHERE uid=?', (uid,)).fetchone():
            return False
        component = self.next_component
        self.next_component += 1
        self.put('components', {'id': component}, dict(id=component, wordnet_reachable=0, depth=None,
                                                      parent_component_id=None, witness_edge_id=None))
        attrs = {k: v for k, v in row.items() if k not in ('raw_record', 'aliases')}
        self.put('nodes', {'uid': uid}, dict(uid=uid, label=row['label'], domain=row['domain'],
                 domains=canonical([row['domain']]), source=row.get('source', 'Source-native dataset'),
                 rank=row.get('rank') or row['role'].lower(), description=row.get('definition') or '',
                 data=canonical(row), layer=LAYER, visibility='ACTIVE', component_id=component))
        self.put('node_profiles', {'uid': uid}, dict(uid=uid, node_kind=row['role'], domain=row['domain'],
                 source_uri=row.get('source_uri') or '', evidence_id=evidence_id, attributes=canonical(attrs)))
        self.added_nodes[uid] = {**row, 'component_id': component}
        for name in [row['label'], *row.get('aliases', [])]:
            self.alias(uid, name, evidence_id=evidence_id, source=row.get('source', 'Source-native dataset'))
        return True

    def add_relation(self, child: str, parent: str, relation: str, *, source: str,
                     evidence_id: str, proof: dict, status: str = 'ACTIVE') -> bool:
        from .hierarchy import validate_link_roles
        from .semantics import role_expression
        rows = [self.c.execute('SELECT n.component_id,' + role_expression('n','p') + ' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?', (uid,)).fetchone() for uid in (child, parent)]
        if not all(rows):
            raise ValueError('Relation endpoint missing')
        validate_link_roles(relation, rows[0]['role'], rows[1]['role'])
        if rows[0]['component_id'] == rows[1]['component_id']:
            raise ValueError('Structural identity loop')
        source = LAYER + ':' + source
        hierarchical = relation in ('IS_A', 'TAXONOMIC_PARENT', 'NATIVE_CLASSIFICATION_PARENT')
        table = 'edges' if hierarchical else 'entity_relations'
        left, right = ('child_uid', 'parent_uid') if hierarchical else ('subject_uid', 'object_uid')
        if self.c.execute('SELECT 1 FROM ' + table + ' WHERE ' + left + '=? AND ' + right + '=? AND relation=? AND source=?',
                          (child, parent, relation, source)).fetchone():
            return False
        next_id = self.c.execute('SELECT coalesce(max(id),0)+1 FROM ' + table).fetchone()[0]
        if hierarchical:
            admitted = 'ACTIVE' if relation == 'IS_A' else 'TYPED_ACTIVE'
            row = dict(id=next_id, child_uid=child, parent_uid=parent, relation=relation, original_relation=relation,
                       facet_family=proof.get('facet') or proof.get('facet_family') or 'SOURCE_DECLARED_CLASSIFICATION',
                       typed_refinement_kind='', classification_basis='EXPLICIT_SOURCE_STATEMENT', navigation_role='',
                       source=source, source_relation=relation, confidence=1.0, provenance=canonical({'evidence_id': evidence_id}),
                       data=canonical(proof), layer=LAYER, status=admitted if status == 'ACTIVE' else status,
                       reason='Grounded original-source relation; no inferred identity')
        else:
            row = dict(id=next_id, subject_uid=child, object_uid=parent, relation=relation, status=status,
                       source=source, evidence_id=evidence_id, data=canonical(proof))
        self.put(table, {'id': next_id}, row)
        if status == 'ACTIVE':
            self.new_arcs.append({'child': child, 'parent': parent, 'relation': relation,
                                  'id': next_id, 'storage': 'edge' if hierarchical else 'entity',
                                  'child_component': rows[0]['component_id'], 'parent_component': rows[1]['component_id'],
                                  'child_role': rows[0]['role'], 'parent_role': rows[1]['role']})
        return True

    def refresh_new_indexes(self) -> dict:
        """Materialize only added components; old cache rows remain untouched."""
        added = self.added_nodes
        outgoing = defaultdict(list)
        for arc in self.new_arcs:
            if arc['child'] in added:
                outgoing[arc['child']].append(arc)
        pending = {u: len({a['parent'] for a in outgoing[u] if a['parent'] in added}) for u in added}
        reverse = defaultdict(set)
        for u in added:
            for arc in outgoing[u]:
                if arc['parent'] in added:
                    reverse[arc['parent']].add(u)
        queue = deque(sorted(u for u, count in pending.items() if count == 0))
        ordered = []
        while queue:
            uid = queue.popleft()
            ordered.append(uid)
            for child in sorted(reverse[uid]):
                pending[child] -= 1
                if not pending[child]:
                    queue.append(child)
        if len(ordered) != len(added):
            raise ValueError('Added subgraph has a cycle')
        counts = Counter()
        for view in VIEWS:
            for uid in ordered:
                own = added[uid]
                candidates, class_candidates = [], []
                for arc in outgoing[uid]:
                    relation = arc['relation']
                    ordinary = (relation == 'IS_A' and view != 'membership') or (
                        relation in ('TAXONOMIC_PARENT', 'NATIVE_CLASSIFICATION_PARENT') and view in ('taxonomy', 'unified'))
                    if ordinary and (own['role'] not in classification_roles(view) or arc['parent_role'] not in classification_roles(view)):
                        continue
                    terminal = relation in terminal_relations(own['role'], view)
                    if not ordinary and not terminal:
                        continue
                    parent = self.c.execute('SELECT * FROM view_paths WHERE view=? AND component_id=?',
                                            (view, arc['parent_component'])).fetchone()
                    if parent:
                        candidates.append((parent['depth'] + 1, arc['parent'], arc, dict(parent), terminal))
                    if ordinary:
                        pure = self.c.execute('SELECT * FROM view_roots WHERE view=? AND component_id=? AND root_reachable=1',
                                              (view, arc['parent_component'])).fetchone()
                        if pure:
                            class_candidates.append((pure['depth'] + 1, arc['parent'], arc))
                    self._browse_arc(view, arc)
                if candidates:
                    depth, _, arc, parent, terminal = min(candidates, key=lambda x: (x[0], x[1], x[2]['id']))
                    row = dict(view=view, component_id=own['component_id'], depth=depth,
                               parent_component_id=arc['parent_component'],
                               witness_id=arc['id'] if arc['storage'] == 'edge' else -arc['id'],
                               contains_terminal=int(terminal or parent['contains_terminal']),
                               typed_route=int(terminal or parent['typed_route']),
                               contains_navigation=int(parent['contains_navigation'] or arc['relation'] in ('NATIVE_CLASSIFICATION_PARENT', 'REUSABLE_TYPE_MEMBERSHIP', 'REGULATED_AS')))
                    self.put('view_paths', {'view': view, 'component_id': own['component_id']}, row)
                    counts[view + '_paths'] += 1
                    if terminal:
                        self.put('view_terminal_connections', {'view': view, 'uid': uid},
                                 dict(view=view, uid=uid, class_uid=arc['parent'], witness_relation_id=arc['id'], depth=depth))
                    # Preserve all admitted parent domain memberships, rather
                    # than treating the one cached witness as unique ancestry.
                    domains = {}
                    for _, _, admitted, _, _ in candidates:
                        for d in self.c.execute('SELECT domain_id,depth FROM domain_components WHERE view=? AND component_id=?',
                                                (view, admitted['parent_component'])):
                            domains[d['domain_id']] = min(domains.get(d['domain_id'], 10**9), d['depth'] + 1)
                    for domain, local_depth in domains.items():
                        self.put('domain_components', {'domain_id': domain, 'view': view, 'component_id': own['component_id']},
                                 dict(domain_id=domain, view=view, component_id=own['component_id'], depth=local_depth,
                                      category='typed' if terminal else 'classification'))
                        self.put('domain_members', {'domain_id': domain, 'view': view, 'uid': uid},
                                 dict(domain_id=domain, view=view, uid=uid, role=own['role'], depth=local_depth))
                if class_candidates:
                    depth, _, arc = min(class_candidates, key=lambda x: (x[0], x[1], x[2]['id']))
                    self.put('view_roots', {'view': view, 'component_id': own['component_id']},
                             dict(view=view, component_id=own['component_id'], root_reachable=1, depth=depth,
                                  parent_component_id=arc['parent_component'], witness_id=arc['id']))
                    if view == 'unified':
                        self.put('components', {'id': own['component_id']},
                                 dict(id=own['component_id'], wordnet_reachable=1, depth=depth,
                                      parent_component_id=arc['parent_component'], witness_edge_id=arc['id']))
        for uid, own in added.items():
            allowed = own.get('allowed_views')
            mask = sum(VIEW_BITS[v] for v in VIEWS if allowed is None or ('taxonomy' if v == 'unified' else v) in allowed)
            self.put('browse_nodes', {'uid': uid}, dict(uid=uid, component_id=own['component_id'], role=own['role'],
                                                       view_mask=mask, source=own.get('source', 'Source-native dataset')))
        return dict(counts)

    def _browse_arc(self, view: str, arc: dict) -> None:
        key = dict(view=view, parent_component=arc['parent_component'], child_component=arc['child_component'],
                   role=arc['child_role'], relation=arc['relation'])
        self.put('browse_links', key, {**key, 'representative_uid': arc['child'], 'storage': arc['storage'],
                                       'record_id': arc['id'], 'source_arc_count': 1})
        count_key = {k: key[k] for k in ('view', 'parent_component', 'role', 'relation')}
        row = self.c.execute('SELECT count(*) n,sum(source_arc_count) arcs FROM browse_links WHERE view=? AND parent_component=? AND role=? AND relation=?',
                             tuple(count_key.values())).fetchone()
        self.put('browse_link_counts', count_key, {**count_key, 'concept_count': row['n'], 'source_arc_count': row['arcs']})
        self.put('browse_cached_parents', {'view': view, 'parent_component': arc['parent_component']},
                 dict(view=view, parent_component=arc['parent_component']))


def build_core(database: Path, expected_revision: str, originals: Path, increment: Path) -> dict:
    from .api import FineAtlas
    annotations = json.loads(originals.read_text())
    for check in annotations['file_checks']:
        file = Path(check['path'])
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != check['sha256']:
            raise ValueError('Original annotation changed: ' + str(file))
    inc = sqlite3.connect(increment.resolve().as_uri() + '?mode=ro', uri=True)
    mappings = {(r['dataset'], r['class_id']): r for (payload,) in inc.execute("SELECT payload FROM fg_objects WHERE kind='mappings'")
                if (r := json.loads(payload)).get('scope') == 'source_native' and r['dataset'] in CORE_COUNTS}
    inc.close()
    with FineAtlas(database) as atlas:
        world = {(d, t['class_id']): t for d in CORE_COUNTS for t in atlas.task_labels(d, requirement='native_label')}
        native = {(r['dataset'], r['class_id']): dict(r) for r in atlas.con.execute('SELECT * FROM dataset_scope_targets')}
    writer = RepairWriter(database, expected_revision=expected_revision)
    inputs = {'annotations_sha256': hashlib.sha256(originals.read_bytes()).hexdigest(),
              'increment_mappings': {d + ':' + cid: digest(m) for (d, cid), m in mappings.items()}}
    if not writer.begin('native755-core-v1', inputs):
        writer.c.close()
        return {'status': 'ALREADY_APPLIED', 'changed_rows': 0}
    counts = Counter()
    for dataset, expected in CORE_COUNTS.items():
        labels = annotations['labels'][dataset]
        if len(labels) != expected:
            raise ValueError('Original label count mismatch')
        for cid, original_label in labels.items():
            mapping, target = mappings[(dataset, cid)], world[(dataset, cid)]
            if norm(original_label) != norm(mapping['standard_name']):
                record = mapping.get('raw_record', {})
                retained = record.get('raw_record', {})
                crosswalk = record.get('id_crosswalk_sha256')
                verified_hashes = {check['sha256'] for check in annotations['file_checks'] if check['dataset'] == dataset}
                if (not isinstance(retained, dict)
                    or norm(retained.get('original_local_class_name', '')) != norm(original_label)
                    or norm(retained.get('author_category', {}).get('name', '')) != norm(mapping['standard_name'])
                    or crosswalk not in verified_hashes):
                    raise ValueError('Increment native ID/name mismatch: ' + dataset + ':' + cid)
                counts['evidenced_author_vs_local_label_differences'] += 1
            current = native.get((dataset, cid))
            uid = current['source_uid'] if current else mapping['source_uid']
            namespace = current['namespace'] if current else uid.rsplit(':', 2)[0]
            version = current['source_version'] if current else mapping['version']
            node = writer.c.execute('SELECT uid FROM nodes WHERE uid=?', (uid,)).fetchone()
            proof = {'basis': 'ORIGINAL_ANNOTATION_ID_AND_FULL_LABEL', 'dataset': dataset,
                     'class_id': cid, 'original_label': original_label, 'increment_native_record': mapping,
                     'original_file_checks': [c for c in annotations['file_checks'] if c['dataset'] == dataset],
                     'retrieved_utc': '2026-10-12', 'world_identity_is_not_asserted': True}
            source_uri = writer.c.execute('SELECT source_uri FROM dataset_catalogs WHERE dataset=?', (dataset,)).fetchone()[0]
            eid = writer.evidence(proof, uri=source_uri, source=dataset + ' original annotation', claim='SOURCE_NATIVE_CATEGORY_ID')
            role = current['role'] if current else 'DATASET_CATEGORY'
            if not node:
                writer.add_node(dict(uid=uid, label=original_label, role=role, domain=CORE_DOMAINS[dataset],
                                     source=dataset, source_uri=source_uri, rank='dataset_category',
                                     source_version=version, identity_scope='SOURCE_NATIVE_LABEL',
                                     object_granularity=mapping['object_granularity'], aliases=[mapping['raw_name']]), evidence_id=eid)
                writer.add_relation(uid, mapping['boundary_anchors'][0], 'DEPICTS_TYPE', source=dataset,
                                    evidence_id=eid, proof=proof)
            writer.put('native_classes', {'dataset': dataset, 'class_id': cid, 'source_version': version},
                       dict(dataset=dataset, class_id=cid, namespace=namespace, source_version=version,
                            uid=uid, label=original_label, raw_label=mapping['raw_name'], role=role,
                            object_granularity=mapping['object_granularity'], domain=CORE_DOMAINS[dataset],
                            training_id_verified=1, proof=canonical(proof), evidence_ids=canonical([eid])))
            if not current:
                writer.put('dataset_scope_targets', {'dataset': dataset, 'class_id': cid, 'namespace': namespace, 'source_version': version},
                           dict(dataset=dataset, class_id=cid, namespace=namespace, source_version=version,
                                source_uid=uid, role=role, decision_status='SOURCE_DECLARED', proof=canonical(proof), label=original_label))
            for name in {original_label, mapping['raw_name'], mapping['standard_name'], target['label']}:
                writer.put('native_class_names', {'uid': uid, 'name': name},
                           dict(uid=uid, name=name, normalized_name=exact_name(name), search_name=norm(name), evidence_id=eid))
                writer.alias(uid, name, evidence_id=eid, source=dataset + ' original label')
            confirmed = target['identity_verified']
            writer.put('world_mapping_dispositions', {'dataset': dataset, 'class_id': cid},
                       dict(dataset=dataset, class_id=cid, uid=target['target_uid'], stored_status=target['decision_status'],
                            effective_status='CONFIRMED' if confirmed else 'REVIEW',
                            reason='Current rc1 effective identity state; original registration retained',
                            missing_evidence='' if confirmed else 'Exact original annotation range to world object crosswalk',
                            evidence_ids=canonical(target.get('evidence_ids') or [])))
            counts['native_classes'] += 1
            counts['world_confirmed'] += int(confirmed)
            counts['world_review'] += int(not confirmed)
            counts['stored_verified_effective_review'] += int(target.get('stored_identity_claim_verified', False) and not confirmed)
    indexes = writer.refresh_new_indexes()
    writer.meta('native755_ready', True)
    writer.meta('native755_rules', 'native-world-exact-v1')
    result = writer.finish({'status': 'APPLIED', **dict(counts), 'added_native_nodes': len(writer.added_nodes), 'index_changes': indexes})
    writer.c.close()
    return result


def repair_local_index_encoding(database: Path, expected_revision: str) -> dict:
    """Repair only this run's appended cache rows; source graph is unchanged."""
    writer = RepairWriter(database, expected_revision=expected_revision)
    if not writer.begin('local-index-encoding-v1', {'rules': 'negative-entity-witness-and-source-admission-mask-v1'}):
        writer.c.close()
        return {'status': 'ALREADY_APPLIED', 'changed_rows': 0}
    inserted = [json.loads(r[0]) for r in writer.c.execute("SELECT after_json FROM repair_changes WHERE table_name='nodes' AND before_json IS NULL")]
    counts = Counter()
    for node in inserted:
        uid, comp = node['uid'], node['component_id']
        own = writer.c.execute('SELECT node_kind,attributes FROM node_profiles WHERE uid=?', (uid,)).fetchone()
        attrs = json.loads(own['attributes'])
        for view in VIEWS:
            row = writer.c.execute('SELECT * FROM view_paths WHERE view=? AND component_id=?', (view, comp)).fetchone()
            if row and row['witness_id'] and row['witness_id'] > 0:
                typed = writer.c.execute('SELECT r.id,n.component_id child_component,p.component_id parent_component FROM entity_relations r JOIN nodes n ON n.uid=r.subject_uid JOIN nodes p ON p.uid=r.object_uid WHERE r.id=?', (row['witness_id'],)).fetchone()
                if typed and typed['child_component'] == comp and typed['parent_component'] == row['parent_component_id']:
                    corrected = dict(row)
                    corrected['witness_id'] = -typed['id']
                    writer.put('view_paths', {'view': view, 'component_id': comp}, corrected)
                    counts['corrected_typed_witnesses'] += 1
            for link in list(writer.c.execute("SELECT * FROM browse_links WHERE view=? AND child_component=? AND storage='typed'", (view, comp))):
                corrected = dict(link)
                corrected['storage'] = 'entity'
                key = {k: corrected[k] for k in ('view', 'parent_component', 'child_component', 'role', 'relation')}
                writer.put('browse_links', key, corrected)
                counts['corrected_browse_storage'] += 1
        allowed = attrs.get('allowed_views')
        mask = sum(VIEW_BITS[v] for v in VIEWS if allowed is None or ('taxonomy' if v == 'unified' else v) in allowed)
        writer.put('browse_nodes', {'uid': uid}, dict(uid=uid, component_id=comp, role=own['node_kind'], view_mask=mask, source=node['source']))
    result = writer.finish({'status': 'APPLIED', **dict(counts), 'checked_new_nodes': len(inserted),
                            'source_relation_changes': 0})
    writer.c.close()
    return result


def install_answer_contracts(database: Path, expected_revision: str, configuration: Path) -> dict:
    definitions = json.loads(configuration.read_text())
    if set(definitions) != set(CORE_COUNTS):
        raise ValueError('Six original dataset contracts required')
    writer = RepairWriter(database, expected_revision=expected_revision)
    if not writer.begin('dataset-answer-contracts-v1', definitions):
        writer.c.close()
        return {'status': 'ALREADY_APPLIED', 'changed_rows': 0}
    for dataset, definition in definitions.items():
        proof = {'definition': definition, 'source_annotation_identity_is_independent': True,
                 'unknown_granularity_is_not_filled': True, 'retrieved_utc': '2026-10-12'}
        eid = writer.evidence(proof, uri=definition['source_uri'], source=dataset + ' task definition',
                              claim='TASK_ANSWER_SCOPE_POLICY_NOT_NEW_WORLD_FACT')
        writer.put('dataset_answer_contracts', {'dataset': dataset},
                   dict(dataset=dataset, payload=canonical({**definition, 'evidence_id': eid})))
    writer.meta('dataset_answer_rules', 'native-world-exact-v1')
    result = writer.finish({'status': 'APPLIED', 'dataset_contracts': len(definitions),
                            'world_identity_changes': 0, 'hierarchy_changes': 0})
    writer.c.close()
    return result


def rollback(database: Path, package_id: str) -> dict:
    c = sqlite3.connect(database)
    c.row_factory = sqlite3.Row
    package = c.execute('SELECT * FROM repair_packages WHERE package_id=?', (package_id,)).fetchone()
    if not package or package['status'] != 'APPLIED':
        c.close()
        return {'status': 'NOT_APPLIED'}
    newest = c.execute("SELECT package_id FROM repair_changes ORDER BY sequence DESC LIMIT 1").fetchone()[0]
    if newest != package_id:
        raise ValueError('Rollback must follow reverse application order')
    changes = list(c.execute('SELECT * FROM repair_changes WHERE package_id=? ORDER BY sequence DESC', (package_id,)))
    with c:
        for change in changes:
            table, key = change['table_name'], json.loads(change['key_json'])
            where = ' AND '.join(k + '=?' for k in key)
            actual = c.execute('SELECT * FROM ' + table + ' WHERE ' + where, tuple(key.values())).fetchone()
            if canonical(dict(actual) if actual else None) != change['after_json']:
                raise ValueError('Record changed after repair; refusing destructive rollback')
            before = json.loads(change['before_json']) if change['before_json'] else None
            if table == 'aliases':
                c.execute('INSERT INTO alias_search(alias_search,rowid,alias) VALUES (\'delete\',?,?)',
                          (key['rowid'], json.loads(change['after_json'])['alias']))
            if before is None:
                c.execute('DELETE FROM ' + table + ' WHERE ' + where, tuple(key.values()))
            elif actual is not None:
                c.execute('UPDATE ' + table + ' SET ' + ','.join(k + '=?' for k in before) + ' WHERE ' + where,
                          [*before.values(), *key.values()])
            else:
                c.execute('INSERT INTO ' + table + '(' + ','.join(before) + ') VALUES (' + ','.join('?' for _ in before) + ')', tuple(before.values()))
        c.execute("UPDATE repair_packages SET status='ROLLED_BACK' WHERE package_id=?", (package_id,))
    c.close()
    return {'status': 'ROLLED_BACK', 'changed_rows': len(changes)}


def integrate_increment(database: Path, expected_revision: str, increment: Path, source_validation: Path) -> dict:
    """Reconcile a v1.10-dependent increment into rc1; never replay old closure."""
    from .fg_incremental import open_store, read_objects, object_key, ACTIVE, validate_relation_roles, domain_relation_error
    from .semantics import role_expression
    validation = json.loads(source_validation.read_text())
    if not validation.get('passed'):
        raise ValueError('Increment source/contract validation did not pass')
    store = open_store(increment, read_only=True)
    objects = read_objects(store)
    inc_meta = {r[0]: json.loads(r[1]) for r in store.execute('SELECT key,value FROM metadata')}
    exported = [dict(r) for r in store.execute('SELECT * FROM fg_objects ORDER BY kind,key')]
    store.close()
    writer = RepairWriter(database, expected_revision=expected_revision)
    inputs = {'increment_revision': inc_meta['revision'],
              'effective_objects': digest([(r['kind'], r['key'], r['sha256']) for r in exported]),
              'source_validation': digest(validation), 'reconciliation_rules': 'retain-rc1-no-inherited-replay-v1'}
    if not writer.begin('increment-integrated-v1', inputs):
        writer.c.close()
        return {'status': 'ALREADY_APPLIED', 'changed_rows': 0}
    counts = Counter()
    evidence = {r['evidence_id']: r for r in objects['evidence']}
    nodes = {r['uid']: r for r in objects['nodes']}
    evidence_map = {}
    for row in exported:
        writer.put('integrated_fg_objects', {'kind': row['kind'], 'key': row['key']}, row)
    def disposition(kind: str, key: str, decision: str, reason: str, payload: dict):
        writer.put('increment_reconciliation', {'kind': kind, 'object_key': key},
                   dict(kind=kind, object_key=key, disposition=decision, reason=reason, payload=canonical(payload)))
        counts[decision] += 1
    for ev in objects['evidence']:
        if ev.get('content_sha256') != digest(ev.get('raw_record', {})):
            raise ValueError('Increment evidence changed since validation')
        raw = ev.get('raw_record', {})
        evidence_map[ev['evidence_id']] = writer.evidence(ev, uri=ev.get('source_uri') or raw.get('source_uri') or '',
                            source=ev.get('source') or raw.get('source_name') or 'Frozen incremental source',
                            claim='INCREMENT_SOURCE_EVIDENCE_RETAINED')
    for record in objects['datasets']:
        writer.put('integrated_dataset_versions', {'dataset': record['dataset'], 'source_version': record['version']},
                   dict(dataset=record['dataset'], source_version=record['version'], payload=canonical(record)))
        existing = writer.c.execute('SELECT 1 FROM dataset_catalogs WHERE dataset=?', (record['dataset'],)).fetchone()
        if not existing:
            count = record.get('expected_labels') or record.get('expected_classes') or record.get('observed_classes')
            writer.put('dataset_catalogs', {'dataset': record['dataset']},
                       dict(dataset=record['dataset'], source_uri=record.get('source_uri', ''),
                            source_sha256=digest(record), expected_classes=count,
                            label_scope=record.get('scope') or record.get('count_scope', 'source_native')))
            counts['new_dataset_catalogs'] += 1
    for uid, incoming in nodes.items():
        actual = writer.c.execute('SELECT n.*,' + role_expression('n','p') + ' actual_role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?', (uid,)).fetchone()
        if incoming.get('node_origin') == 'FROZEN_BASELINE':
            if not actual:
                disposition('nodes', uid, 'ISOLATED_MISSING_BASELINE', 'Referenced old closure node absent from rc1', incoming)
                continue
            raw = incoming.get('raw_record', {})
            same = all(actual[k] == v for k, v in raw.items() if k in actual.keys() and k != 'component_id')
            disposition('nodes', uid, 'RETAIN_CURRENT_BASELINE' if same and actual['actual_role'] == incoming['role'] else 'RECONCILED_CURRENT_CHANGED',
                        'Existing rc1 node/profile/component retained; old frozen closure is provenance only', incoming)
            continue
        if actual:
            disposition('nodes', uid, 'RETAIN_EXISTING_SOURCE_NODE',
                        'No profile/rank/visibility replacement; compare outgoing delta assertions individually', incoming)
            continue
        eid = evidence_map.get(incoming.get('evidence_id'))
        if not eid:
            eid = writer.evidence(incoming, uri=incoming.get('source_uri', ''), source=incoming['source'],
                                  claim='FROZEN_INCREMENT_SOURCE_NODE')
        row = dict(incoming)
        # Only source-version identities are claimed. Field-derived identifiers
        # are not upgraded to accepted cross-source world taxonomy concepts.
        if row.get('world_identity_status') == 'REVIEW':
            row['identity_scope'] = 'SOURCE_VERSION_CONCEPT'
        writer.add_node(row, evidence_id=eid)
        counts['normalized_new_nodes'] += 1
        disposition('nodes', uid, 'INTEGRATED_NEW_SOURCE_NODE', 'Source UID and frozen source-range payload retained', incoming)
    for relation in objects['relations']:
        key = object_key('relations', relation)
        if relation.get('inherited'):
            disposition('relations', key, 'INHERITED_ASSERTION_NOT_REPLAYED',
                        'v1.10 closure assertion never overwrites rc1 relations; semantic withdrawals handled as explicit repair packages', relation)
            continue
        if relation.get('status') not in ACTIVE:
            disposition('relations', key, 'ISOLATED_SOURCE_REVIEW', 'Unconfirmed source relation remains documentary, not admitted', relation)
            continue
        try:
            endpoints = [writer.c.execute('SELECT n.*,' + role_expression('n','p') + ' actual_role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?', (u,)).fetchone()
                         for u in (relation['child_uid'], relation['parent_uid'])]
            if not all(endpoints):
                raise ValueError('Current endpoint missing')
            validate_relation_roles(relation['relation'], endpoints[0]['actual_role'], endpoints[1]['actual_role'])
            if domain_relation_error(relation['relation'], dict(endpoints[0]), dict(endpoints[1])):
                raise ValueError('Cross-domain inclusion conflict')
            if relation['child_uid'] not in writer.added_nodes:
                # No global cache invalidation is guessed. A separate, grounded
                # existing-subgraph repair must handle such assertions.
                raise ValueError('Existing-child change requires independent current-subgraph reconciliation')
            if relation['relation'] in ('GROUPED_IN_SOURCE', 'HAS_ATTRIBUTE', 'MANUFACTURED_BY', 'ORGANIZATION_GROUP_MEMBER'):
                disposition('relations', key, 'INTEGRATED_CATALOGUE_RELATION',
                            'Available in provenance/catalogue API; never a strict hierarchy edge', relation)
                continue
            eid = evidence_map[relation['evidence_id']]
            changed = writer.add_relation(relation['child_uid'], relation['parent_uid'], relation['relation'],
                                          source=relation['source'], evidence_id=eid,
                                          proof={**relation, 'admission_basis': 'EXPLICIT_FROZEN_SOURCE_RELATION'})
            counts['normalized_new_relations'] += int(changed)
            disposition('relations', key, 'INTEGRATED_GROUNDED_RELATION', 'Current endpoint roles compatible; local DAG checked before commit', relation)
        except ValueError as exc:
            disposition('relations', key, 'ISOLATED_CURRENT_CONFLICT', str(exc), relation)
    datasets = {r['dataset']: r for r in objects['datasets']}
    for mapping in objects['mappings']:
        dataset, cid = mapping['dataset'], str(mapping['class_id'])
        key = object_key('mappings', mapping)
        if mapping.get('scope') == 'world':
            current = writer.c.execute('SELECT * FROM world_mapping_dispositions WHERE dataset=? AND class_id=?', (dataset, cid)).fetchone()
            if current:
                row = dict(current)
                if mapping.get('mapping_type') != 'EXACT' or mapping.get('identity_status') not in ('VERIFIED', 'SOURCE_CONFIRMED'):
                    row.update(effective_status='BROADER' if mapping.get('mapping_type') == 'BROADER' else 'REVIEW',
                               reason=mapping.get('reason') or 'Independent frozen full-range review lacks exact-world crosswalk',
                               missing_evidence='Exhaustive original label range to current world object range crosswalk',
                               evidence_ids=canonical(sorted(set(json.loads(row['evidence_ids']) +
                                                         [evidence_map[e] for e in mapping.get('evidence_ids', []) if e in evidence_map]))))
                    writer.put('world_mapping_dispositions', {'dataset': dataset, 'class_id': cid}, row)
                disposition('mappings', key, 'RECONCILED_WORLD_MAPPING',
                            'Current UID and original stored claim retained; only evidence-grounded conservative effective disposition applied', mapping)
            else:
                disposition('mappings', key, 'ISOLATED_EXTENSION_WORLD_MAPPING',
                            'New world crosswalk retained in integrated scope API; not promoted into legacy dataset_targets', mapping)
            continue
        if dataset in CORE_COUNTS:
            disposition('mappings', key, 'RETAIN_CORE_NATIVE_CLASS',
                        'Original755 validated canonical class entry retained; alternate source record not silently equated', mapping)
            continue
        uid = mapping.get('label_uid') or mapping.get('source_uid')
        own = writer.c.execute('SELECT n.*,' + role_expression('n','p') + ' actual_role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?', (uid,)).fetchone()
        if not own:
            disposition('mappings', key, 'ISOLATED_MISSING_SOURCE_CATEGORY', 'Stable source category node is absent', mapping)
            continue
        record = datasets[dataset]
        usable = bool(record.get('numeric_training_ids_verified', True) and
                      mapping.get('numeric_training_class_id_verified', True) and mapping.get('scope') != 'publication_table')
        eid = writer.evidence(mapping, uri=mapping.get('source_uri', ''), source=dataset,
                              claim='FROZEN_EXTENSION_CATEGORY_SCOPE')
        version = mapping['version']
        namespace = uid.rsplit(':', 1)[0]
        proof = {'mapping': mapping, 'dataset_scope': record, 'increment_revision': inc_meta['revision'],
                 'numeric_training_ids_verified': usable, 'world_identity_is_not_asserted': True}
        writer.put('native_classes', {'dataset': dataset, 'class_id': cid, 'source_version': version},
                   dict(dataset=dataset, class_id=cid, namespace=namespace, source_version=version, uid=uid,
                        label=mapping['standard_name'], raw_label=mapping['raw_name'], role=own['actual_role'],
                        object_granularity=mapping.get('object_granularity', 'UNKNOWN_SOURCE_UNIT'), domain=own['domain'],
                        training_id_verified=int(usable), proof=canonical(proof), evidence_ids=canonical([eid])))
        writer.put('dataset_scope_targets', {'dataset': dataset, 'class_id': cid, 'namespace': namespace, 'source_version': version},
                   dict(dataset=dataset, class_id=cid, namespace=namespace, source_version=version, source_uid=uid,
                        role=own['actual_role'], decision_status='SOURCE_DECLARED' if usable else 'REVIEW',
                        proof=canonical(proof), label=mapping['standard_name']))
        for name in {mapping['raw_name'], mapping['standard_name']}:
            writer.put('native_class_names', {'uid': uid, 'name': name},
                       dict(uid=uid, name=name, normalized_name=exact_name(name), search_name=norm(name), evidence_id=eid))
            writer.alias(uid, name, evidence_id=eid, source=dataset + ' original label')
        counts['extension_native_classes'] += 1
        counts['extension_training_ids_usable'] += int(usable)
        disposition('mappings', key, 'INTEGRATED_EXTENSION_NATIVE_CLASS' if usable else 'ISOLATED_TRAINING_ID_SCOPE',
                    'Original source/version ID retained; blocked source authentication remains blocked' if not usable else 'Verified numeric source IDs available', mapping)
    indexes = writer.refresh_new_indexes()
    writer.meta('fg_integration_receipt', {'increment_revision': inc_meta['revision'],
                'increment_baseline_revision': inc_meta['baseline_revision'], 'integration_base': expected_revision,
                'old_closure_replayed': False, 'core_denominator': 755,
                'independent_increment_acceptance_is_full_candidate_acceptance': False})
    result = writer.finish({'status': 'APPLIED', **dict(counts), 'index_changes': indexes,
                            'increment_revision': inc_meta['revision']})
    writer.c.close()
    return result


def apply_scope_operations(database: Path, expected_revision: str, operations_file: Path) -> dict:
    """Execute explicitly evidenced repairs, checking current endpoint/record guards."""
    from .hierarchy import source_assertion_sha256
    from .semantics import edge_predicate, role_expression
    operations = json.loads(operations_file.read_text())
    writer = RepairWriter(database, expected_revision=expected_revision)
    if not writer.begin('grounded-current-scope-v1', operations):
        writer.c.close()
        return {'status': 'ALREADY_APPLIED', 'changed_rows': 0}
    affected, counts = set(), Counter()
    for operation in operations:
        proof = operation['proof']
        for document in proof.get('source_files', []):
            path = Path(document['path'])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != document['sha256']:
                raise ValueError('Source snapshot changed or missing')
        eid = writer.evidence(proof, uri=operation['source_uri'], source=operation['source'], claim='CURRENT_SCOPE_REPAIR')
        if operation['op'] == 'review_edge':
            locator = operation['locator']
            rows = list(writer.c.execute('SELECT * FROM edges WHERE child_uid=? AND parent_uid=? AND relation=? AND source=?',
                        tuple(locator[k] for k in ('child_uid', 'parent_uid', 'relation', 'source'))))
            matches = [r for r in rows if source_assertion_sha256(r) == locator['content_sha256']]
            if len(matches) != 1:
                raise ValueError('Current source assertion is changed or ambiguous')
            current = dict(matches[0])
            if current['status'] not in ('ACTIVE', 'TYPED_ACTIVE', 'BACKBONE_ACTIVE'):
                raise ValueError('Unexpected prior assertion status')
            current.update(status='REVIEW', reason=operation['reason'])
            writer.put('edges', {'id': current['id']}, current)
            component = writer.c.execute('SELECT component_id FROM nodes WHERE uid=?', (current['child_uid'],)).fetchone()[0]
            affected.add(component)
            counts['reviewed_existing_edges'] += 1
        elif operation['op'] == 'add_relation':
            child, parent = operation['child_uid'], operation['parent_uid']
            claim = {k: operation[k] for k in ('child_uid', 'parent_uid', 'relation', 'source', 'source_version')}
            if claim not in proof.get('admitted_claims', []):
                raise ValueError('New relation is not bound to exact source evidence')
            child_comp = writer.c.execute('SELECT component_id FROM nodes WHERE uid=?', (child,)).fetchone()[0]
            # Union of legal upward view types is used conservatively for cycle
            # safety; this does not admit those types into strict IS_A.
            queue, seen = deque([parent]), set()
            while queue:
                uid = queue.popleft()
                n = writer.c.execute('SELECT component_id FROM nodes WHERE uid=?', (uid,)).fetchone()
                if not n or n[0] in seen:
                    continue
                if n[0] == child_comp:
                    raise ValueError('Grounded addition would introduce an upward cycle')
                seen.add(n[0])
                if len(seen) > 10000:
                    raise ValueError('Cycle check work limit exceeded; no edge admitted')
                members = [r[0] for r in writer.c.execute('SELECT uid FROM nodes WHERE component_id=?', (n[0],))]
                for member in members:
                    queue.extend(r[0] for r in writer.c.execute("SELECT parent_uid FROM edges WHERE child_uid=? AND status IN ('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE') AND relation IN ('IS_A','TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT','REUSABLE_TYPE_MEMBERSHIP')", (member,)))
                    queue.extend(r[0] for r in writer.c.execute("SELECT object_uid FROM entity_relations WHERE subject_uid=? AND status='ACTIVE' AND relation IN ('DESIGN_TYPE_OF','NATIVE_DESIGN_PARENT','SERIES_MEMBER_OF','CONFIGURATION_OF','CONFIGURATION_TYPE_OF','DEPICTS_TYPE')", (member,)))
            writer.add_relation(child, parent, operation['relation'], source=operation['source'],
                                evidence_id=eid, proof=proof)
            affected.add(child_comp)
            counts['grounded_existing_component_connections'] += 1
        elif operation['op'] == 'revoke_world_exact':
            if (proof.get('basis') != 'PRIMARY_REGULATOR_DISTINCT_NOMINAL_GENERATION_MAPPING_REVIEW'
                or proof.get('assessment') != 'WRONG_COMMERCIAL_GENERATION_MAPPING_PRIMARY_WITHDRAWAL_JUSTIFIED'
                or not proof.get('source_files')):
                raise ValueError('Revocation needs distinct-object primary evidence, not uncertainty alone')
            key = {'dataset': operation['dataset'], 'class_id': operation['class_id']}
            row = writer.c.execute('SELECT * FROM world_mapping_dispositions WHERE dataset=? AND class_id=?', tuple(key.values())).fetchone()
            if not row or row['uid'] != operation['old_target_uid']:
                raise ValueError('World target changed since review')
            row = dict(row)
            row.update(effective_status='REVOKED_EXACT', reason=operation['reason'],
                       missing_evidence='Correct full-range world replacement UID remains unconfirmed',
                       evidence_ids=canonical(sorted(set(json.loads(row['evidence_ids']) + [eid]))))
            writer.put('world_mapping_dispositions', key, row)
            counts['revoked_old_world_exact_claims'] += 1
        else:
            raise ValueError('Unknown scope operation')
    # Expand downward to all affected cached components before recomputing,
    # including peers and all legitimate parent routes. Work bounds fail closed.
    queue = deque(sorted(affected))
    while queue:
        comp = queue.popleft()
        if len(affected) > 10000:
            raise ValueError('Affected subgraph too large for local repair; full rebuild required')
        for uid, in writer.c.execute('SELECT uid FROM nodes WHERE component_id=?', (comp,)):
            rows = list(writer.c.execute("SELECT n.component_id FROM edges e JOIN nodes n ON n.uid=e.child_uid WHERE e.parent_uid=? AND e.status IN ('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE')", (uid,)))
            rows += list(writer.c.execute("SELECT n.component_id FROM entity_relations e JOIN nodes n ON n.uid=e.subject_uid WHERE e.object_uid=? AND e.status='ACTIVE'", (uid,)))
            for row in rows:
                if row[0] not in affected:
                    affected.add(row[0]); queue.append(row[0])
    writer.added_nodes, writer.new_arcs = {}, []
    domain_ids = [r[0] for r in writer.c.execute('SELECT domain_id FROM domain_registry')]
    for comp in sorted(affected):
        members = list(writer.c.execute('SELECT n.*,' + role_expression('n','p') + ' role,p.attributes FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.component_id=?', (comp,)))
        for view in VIEWS:
            writer.delete('view_paths', {'view': view, 'component_id': comp})
            writer.delete('view_roots', {'view': view, 'component_id': comp})
            for domain in domain_ids:
                writer.delete('domain_components', {'domain_id': domain, 'view': view, 'component_id': comp})
            for row in list(writer.c.execute('SELECT * FROM browse_links WHERE view=? AND child_component=?', (view, comp))):
                writer.delete('browse_links', {k: row[k] for k in ('view', 'parent_component', 'child_component', 'role', 'relation')})
            for node in members:
                writer.delete('view_terminal_connections', {'view': view, 'uid': node['uid']})
                for domain in domain_ids:
                    writer.delete('domain_members', {'domain_id': domain, 'view': view, 'uid': node['uid']})
        for node in members:
            writer.added_nodes[node['uid']] = {'uid': node['uid'], 'role': node['role'], 'component_id': comp,
                                              'source': node['source'], **json.loads(node['attributes'] or '{}')}
            for edge in writer.c.execute("SELECT e.*,p.component_id parent_component," + role_expression('p','pp') + " parent_role FROM edges e JOIN nodes p ON p.uid=e.parent_uid LEFT JOIN node_profiles pp ON pp.uid=p.uid WHERE e.child_uid=? AND e.status IN ('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE')", (node['uid'],)):
                writer.new_arcs.append({'child': node['uid'], 'parent': edge['parent_uid'], 'relation': edge['relation'],
                                        'id': edge['id'], 'storage': 'edge', 'child_component': comp,
                                        'parent_component': edge['parent_component'], 'child_role': node['role'], 'parent_role': edge['parent_role']})
            for edge in writer.c.execute("SELECT e.*,p.component_id parent_component," + role_expression('p','pp') + " parent_role FROM entity_relations e JOIN nodes p ON p.uid=e.object_uid LEFT JOIN node_profiles pp ON pp.uid=p.uid WHERE e.subject_uid=? AND e.status='ACTIVE'", (node['uid'],)):
                writer.new_arcs.append({'child': node['uid'], 'parent': edge['object_uid'], 'relation': edge['relation'],
                                        'id': edge['id'], 'storage': 'entity', 'child_component': comp,
                                        'parent_component': edge['parent_component'], 'child_role': node['role'], 'parent_role': edge['parent_role']})
    indexes = writer.refresh_new_indexes()
    result = writer.finish({'status': 'APPLIED', **dict(counts), 'affected_components': len(affected), 'index_changes': indexes})
    writer.c.close()
    return result


def add_confirmed_identity_names(database: Path, expected_revision: str) -> dict:
    """Accept canonical/preferred names only under a confirmed full-range crosswalk."""
    from .api import FineAtlas
    additions, isolated = [], []
    with FineAtlas(database) as atlas:
        for row in atlas.con.execute('SELECT dataset,class_id FROM native_classes ORDER BY dataset,class_id'):
            if row['dataset'] not in CORE_COUNTS:
                continue
            native = atlas.native_class(row['dataset'], row['class_id'])
            world = native['world_mapping']
            if not world['world_identity_verified']:
                continue
            identity = atlas._presentation_identity(world['uid'])
            if identity['status'] != 'ACCEPTED':
                isolated.append({'dataset': row['dataset'], 'class_id': row['class_id'], 'reason': identity['reason']})
                continue
            for member in identity['member_uids']:
                node = atlas.node(member)
                names = [(node['label'], {'basis': 'ACCEPTED_WORLD_COMPONENT_CANONICAL_SOURCE_NAME',
                                         'source_uid': member, 'source_record': dict(atlas.con.execute('SELECT * FROM nodes WHERE uid=?', (member,)).fetchone())})]
                for preferred in atlas.con.execute('SELECT * FROM node_names WHERE uid=? AND preferred=1 AND evidence_id<>\'\'', (member,)):
                    if atlas.con.execute('SELECT 1 FROM evidence WHERE evidence_id=? LIMIT 1', (preferred['evidence_id'],)).fetchone():
                        names.append((preferred['name'], {'basis': 'EVIDENCED_PREFERRED_SOURCE_NAME', 'source_uid': member, 'name_record': dict(preferred)}))
                for name, witness in names:
                    # Display annotations such as '[FGVC variant]' are not
                    # stripped into guessed synonyms. Full source names only.
                    if not atlas.con.execute('SELECT 1 FROM native_class_names WHERE uid=? AND normalized_name=?',
                                             (native['uid'], exact_name(name))).fetchone():
                        additions.append({'uid': native['uid'], 'name': name, 'dataset': row['dataset'],
                                          'class_id': row['class_id'], 'world_mapping': world, 'witness': witness,
                                          'accepted_bridge_ids': identity['accepted_bridge_ids']})
    writer = RepairWriter(database, expected_revision=expected_revision)
    if not writer.begin('confirmed-source-names-v1', {'additions': additions, 'isolated': isolated}):
        writer.c.close()
        return {'status': 'ALREADY_APPLIED', 'changed_rows': 0}
    seen = set()
    for record in additions:
        if (record['uid'], exact_name(record['name'])) in seen:
            continue
        seen.add((record['uid'], exact_name(record['name'])))
        eid = writer.evidence(record, uri='urn:fineatlas:confirmed-full-range-world-crosswalk',
                              source='Source-name crosswalk under current effective identity', claim='EXACT_SCOPED_SOURCE_NAME')
        writer.put('native_class_names', {'uid': record['uid'], 'name': record['name']},
                   dict(uid=record['uid'], name=record['name'], normalized_name=exact_name(record['name']),
                        search_name=norm(record['name']), evidence_id=eid))
        writer.alias(record['uid'], record['name'], evidence_id=eid, source='Confirmed scoped source-name crosswalk')
    result = writer.finish({'status': 'APPLIED', 'accepted_scoped_names': len(seen), 'isolated_identity_components': isolated,
                            'world_identity_promotions': 0, 'name_only_identity_merges': 0})
    writer.c.close()
    return result
