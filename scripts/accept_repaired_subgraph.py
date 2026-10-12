"""Check actual repaired assertions, identity components and upward closure."""
from collections import Counter, defaultdict, deque
import argparse
import json
from pathlib import Path
from fineatlas import FineAtlas
from fineatlas.hierarchy import validate_link_roles
from fineatlas.semantics import role_expression


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    errors, counts, isolated = [], Counter(), []
    with FineAtlas(args.database) as a:
        a.con.execute('PRAGMA cache_size=-65536')
        added = {json.loads(r[0])['uid'] for r in a.con.execute("SELECT key_json FROM repair_changes WHERE table_name='nodes' AND before_json IS NULL")}
        changed = defaultdict(set)
        for row in a.con.execute("SELECT table_name,key_json FROM repair_changes WHERE table_name IN ('edges','entity_relations')"):
            changed[row['table_name']].add(json.loads(row['key_json'])['id'])
        affected = set(added)
        for table, ids in changed.items():
            for rid in sorted(ids):
                row = dict(a.con.execute('SELECT * FROM ' + table + ' WHERE id=?', (rid,)).fetchone())
                counts['checked_' + table] += 1
                hierarchical = table == 'edges'
                child, parent = (row['child_uid'], row['parent_uid']) if hierarchical else (row['subject_uid'], row['object_uid'])
                affected.add(child)
                if row['status'] not in ('ACTIVE', 'TYPED_ACTIVE', 'BACKBONE_ACTIVE'):
                    counts['documentary_review_assertions'] += 1
                    continue
                left, right = a.node(child), a.node(parent)
                try:
                    if not left or not right:
                        raise ValueError('Missing endpoint')
                    validate_link_roles(row['relation'], left['node_kind'], right['node_kind'])
                    if left['component_id'] == right['component_id']:
                        raise ValueError('Identity component structural self loop')
                    if left['visibility'] != 'ACTIVE' or right['visibility'] != 'ACTIVE':
                        raise ValueError('Active assertion uses nonactive endpoint')
                    if hierarchical and row['relation'] == 'IS_A' and (not row['facet_family'] or not row['provenance']):
                        raise ValueError('Strict edge lacks facet or provenance')
                    evidence = json.loads(row['provenance']).get('evidence_id') if hierarchical else row['evidence_id']
                    if not evidence or not a.con.execute('SELECT 1 FROM evidence WHERE evidence_id=?', (evidence,)).fetchone():
                        raise ValueError('Grounded evidence record missing')
                    counts['active_' + row['relation']] += 1
                except (ValueError, KeyError, TypeError) as exc:
                    errors.append({'table': table, 'id': rid, 'child_uid': child, 'parent_uid': parent, 'error': str(exc)})
        # Include old ancestors, so a cycle cannot hide across the new/old boundary.
        queue = deque(sorted(affected)); visited = set(); graph = defaultdict(set)
        structural = {'IS_A', 'TAXONOMIC_PARENT', 'NATIVE_CLASSIFICATION_PARENT', 'REUSABLE_TYPE_MEMBERSHIP',
                      'DESIGN_TYPE_OF', 'NATIVE_DESIGN_PARENT', 'SERIES_MEMBER_OF', 'CONFIGURATION_OF',
                      'CONFIGURATION_TYPE_OF', 'DEPICTS_TYPE', 'INSTANCE_OF', 'ATTRIBUTE_KIND_OF', 'REGULATED_AS'}
        while queue:
            uid = queue.popleft()
            node = a.node(uid)
            if not node or node['component_id'] in visited:
                continue
            comp = node['component_id']; visited.add(comp)
            if len(visited) > 150000:
                errors.append({'error': 'Upward closure work bound exceeded; incomplete cycle verification'})
                break
            for member, in a.con.execute('SELECT uid FROM nodes WHERE component_id=?', (comp,)):
                arcs = list(a.con.execute("SELECT parent_uid,relation FROM edges WHERE child_uid=? AND status IN ('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE')", (member,)))
                arcs += list(a.con.execute("SELECT object_uid,relation FROM entity_relations WHERE subject_uid=? AND status='ACTIVE'", (member,)))
                for parent, relation in arcs:
                    if relation not in structural:
                        continue
                    n = a.node(parent)
                    if n and n['component_id'] != comp:
                        graph[comp].add(n['component_id']); queue.append(parent)
        pending = {c: len(graph[c]) for c in visited}; reverse = defaultdict(set)
        for child, parents in graph.items():
            for parent in parents:
                reverse[parent].add(child)
        queue = deque(c for c, n in pending.items() if n == 0); ordered = 0
        while queue:
            parent = queue.popleft(); ordered += 1
            for child in reverse[parent]:
                pending[child] -= 1
                if pending[child] == 0:
                    queue.append(child)
        cyclic = [c for c, n in pending.items() if n]
        if cyclic:
            errors.append({'error': 'Cycle in conservative union of legal upward relation types', 'components': cyclic[:100]})
        components = {a.node(uid)['component_id']: uid for uid in affected}
        for comp, uid in components.items():
            identity = a._presentation_identity(uid)
            counts['identity_' + identity['status']] += 1
            if identity['status'] != 'ACCEPTED':
                isolated.append({'uid': uid, 'component_id': comp, **identity})
        result = {'passed': not errors, 'database_revision': a._revision,
                  'scope': 'Every repair-written relation and affected component plus its current upward closure; inherited full graph semantics not claimed',
                  'added_nodes': len(added), 'upward_components': len(visited), 'acyclic_components': ordered,
                  'counts': dict(counts), 'errors': errors, 'isolated_identity_components': isolated}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('isolated_identity_components', 'errors')}, ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
