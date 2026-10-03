"""Standard-library, read-only interface to the consolidated SQLite graph."""
from __future__ import annotations

from collections import deque
import json
from pathlib import Path
import sqlite3

from ._text import norm, tokens


class SingleAtlas:
    """Query one SQLite file; default navigation follows the WordNet projection.

    ``view='all'`` includes unconnected source hierarchies. Node inspection and
    the target catalog retain archived UIDs regardless of navigation view.
    """

    def __init__(self, path: str | Path, view: str = 'wordnet'):
        if view not in ('wordnet', 'all'):
            raise ValueError('view must be wordnet or all')
        path = Path(path).resolve()
        self.path_file = path / 'fineatlas.sqlite' if path.is_dir() else path
        if not self.path_file.is_file():
            raise FileNotFoundError(self.path_file)
        self.con = sqlite3.connect(self.path_file.as_uri() + '?mode=ro&immutable=1', uri=True)
        self.con.row_factory = sqlite3.Row
        self.view = view
        self.metadata = {row['key']: json.loads(row['value']) for row in self.con.execute('SELECT * FROM metadata')}
        if self.metadata.get('schema') != 'FINEATLAS_SINGLE_DB_V1':
            self.con.close()
            raise ValueError('Unsupported single-database schema')
        self.roots = {'entity': self.metadata['root_uid']}
        self._closed = False

    @staticmethod
    def _limit(limit: int) -> None:
        if limit < 1:
            raise ValueError('limit must be positive')

    def _node(self, row, edge: dict | None = None) -> dict | None:
        if not row:
            return None
        result = dict(row)
        result['data'] = json.loads(result.get('data') or '{}')
        result['edge'] = edge or {}
        result['aliases'] = ''
        return result

    def node(self, uid: str) -> dict | None:
        return self._node(self.con.execute('''SELECT n.*,c.wordnet_reachable,c.depth AS wordnet_depth
            FROM nodes n JOIN components c ON c.id=n.component_id WHERE n.uid=?''', (uid,)).fetchone())

    def connection_status(self, uid: str) -> dict | None:
        """Explain the structural connection state without inventing a parent."""
        node = self.node(uid)
        if not node:
            return None
        result = {'uid': uid, 'wordnet_reachable': bool(node['wordnet_reachable']),
                  'wordnet_depth': node['wordnet_depth']}
        if node['visibility'] != 'ACTIVE':
            return {**result, 'status': 'ARCHIVED', 'reason': node['visibility']}
        if node['wordnet_reachable']:
            return {**result, 'status': 'CONNECTED', 'record_role': 'CLASSIFICATION_NODE',
                    'tree_admission': 'ACTIVE', 'reason': 'Validated path to the WordNet root'}
        if self.con.execute("SELECT 1 FROM sqlite_master WHERE name='node_dispositions'").fetchone():
            row = self.con.execute('SELECT status,record_role,tree_admission,reason,source_flags FROM node_dispositions WHERE uid=?', (uid,)).fetchone()
            if row:
                return {**result, **dict(row)}
        if self.con.execute("SELECT 1 FROM sqlite_master WHERE name='source_scope_reviews'").fetchone():
            row = self.con.execute('SELECT flags,verdict FROM source_scope_reviews WHERE uid=?', (uid,)).fetchone()
            if row:
                return {**result, 'status': 'SOURCE_SCOPE_REVIEW', 'reason': row['verdict'], 'source_flags': row['flags']}
        hierarchy = self.con.execute('''SELECT 1 FROM nodes u JOIN edges e
            ON e.child_uid=u.uid OR e.parent_uid=u.uid
            WHERE u.component_id=? AND e.status='ACTIVE' LIMIT 1''', (node['component_id'],)).fetchone()
        auxiliary_use = self.con.execute("SELECT 1 FROM edges WHERE parent_uid=? AND relation IN ('HAS_ATTRIBUTE','MANUFACTURED_BY') AND status='AUXILIARY' LIMIT 1", (uid,)).fetchone()
        if not hierarchy and (node['rank'] in ('manufacturer', 'make', 'attribute') or auxiliary_use):
            return {**result, 'status': 'AUXILIARY_RECORD',
                    'reason': 'Source record describes provenance or attributes; it has no accepted classification'}
        if self.con.execute("SELECT 1 FROM bridges WHERE status='REVIEW' AND (left_uid=? OR right_uid=?) LIMIT 1", (uid, uid)).fetchone():
            return {**result, 'status': 'IDENTITY_REVIEW',
                    'reason': 'A source identity claim needs independent review'}
        if self.con.execute('SELECT 1 FROM suppressed_edges WHERE child_uid=? LIMIT 1', (uid,)).fetchone():
            return {**result, 'status': 'HISTORICAL_QUARANTINE',
                    'reason': 'A source relation was previously rejected as classification'}
        return {**result, 'status': 'MISSING_ROOT_CONNECTION' if hierarchy else 'INSUFFICIENT_HIERARCHY_EVIDENCE',
                'reason': 'Accepted source hierarchy lacks a proved root entry' if hierarchy
                          else 'No accepted classification connects this identity component'}

    def _visible_sql(self, alias: str) -> str:
        expression = f"{alias}.visibility='ACTIVE'"
        if self.view == 'wordnet':
            expression += f' AND {alias}.component_id IN (SELECT id FROM components WHERE wordnet_reachable=1)'
        return expression

    def exact(self, text: str, limit: int = 20) -> list[dict]:
        self._limit(limit)
        rows = self.con.execute(f'''SELECT DISTINCT n.* FROM aliases a JOIN nodes n ON n.uid=a.uid
            WHERE a.alias=? AND {self._visible_sql('n')}
            ORDER BY n.layer DESC,n.uid LIMIT ?''', (norm(text), limit))
        return [self._node(row) for row in rows]

    def search(self, text: str, limit: int = 20, domain: str | None = None) -> list[dict]:
        self._limit(limit)
        query = norm(text)
        terms = tokens(text)[:6] or query.split()[:6]
        if not terms:
            return []
        found = {row['uid']: row for row in self.exact(text, max(80, limit * 4))}
        domain_sql = ''
        domain_args = []
        if domain:
            domain_sql = ' AND (n.domain=? OR EXISTS (SELECT 1 FROM json_each(n.domains) d WHERE d.value=?))'
            domain_args = [domain, domain]
        filters = ['a.alias LIKE ? ESCAPE \'\\\'' for _ in terms]
        escaped = [term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') for term in terms]
        # FTS accelerates broad searches without requiring third-party packages.
        if self.con.execute("SELECT 1 FROM sqlite_master WHERE name='alias_search'").fetchone():
            fts = ' AND '.join('"' + term.replace('"', '""') + '"' for term in terms)
            sql = f'''SELECT DISTINCT n.* FROM alias_search f JOIN aliases a ON a.rowid=f.rowid
                JOIN nodes n ON n.uid=a.uid WHERE alias_search MATCH ? AND {self._visible_sql('n')}{domain_sql}
                ORDER BY n.layer DESC,n.uid LIMIT ?'''
            args = [fts, *domain_args, max(80, limit * 4)]
        else:
            sql = f'''SELECT DISTINCT n.* FROM aliases a JOIN nodes n ON n.uid=a.uid
                WHERE {' AND '.join(filters)} AND {self._visible_sql('n')}{domain_sql}
                ORDER BY n.layer DESC,n.uid LIMIT ?'''
            args = [*[f'%{term}%' for term in escaped], *domain_args, max(80, limit * 4)]
        for row in self.con.execute(sql, args):
            item = self._node(row)
            found.setdefault(item['uid'], item)
        values = list(found.values())
        if domain:
            values = [row for row in values if row['domain'] == domain or domain in json.loads(row['domains'] or '[]')]
        return sorted(values, key=lambda row: (norm(row['label']) != query,
                      -sum(term in norm(row['label']) for term in terms), row['label'], row['uid']))[:limit]

    def equivalents(self, uid: str) -> list[str]:
        row = self.con.execute('SELECT component_id FROM nodes WHERE uid=?', (uid,)).fetchone()
        if not row:
            return []
        return [x[0] for x in self.con.execute("SELECT uid FROM nodes WHERE component_id=? AND uid<>? AND visibility='ACTIVE' ORDER BY uid", (row[0], uid))]

    @staticmethod
    def _edge(row) -> dict:
        edge = dict(row)
        edge['data'] = json.loads(edge.get('data') or '{}')
        return edge

    def neighbors(self, uid: str, direction: str = 'children', limit: int = 20,
                  structural_only: bool = True) -> list[dict]:
        self._limit(limit)
        if direction not in ('children', 'parents'):
            raise ValueError('direction must be children or parents')
        own = self.con.execute('SELECT component_id,visibility FROM nodes WHERE uid=?', (uid,)).fetchone()
        if not own or own['visibility'] != 'ACTIVE':
            return []
        endpoint, target = ('parent_uid', 'child_uid') if direction == 'children' else ('child_uid', 'parent_uid')
        status = "e.status='ACTIVE'" if structural_only else "e.status IN ('ACTIVE','AUXILIARY','REVIEW')"
        result = {}
        cursor = self.con.execute(f'''SELECT e.* FROM nodes u JOIN edges e ON e.{endpoint}=u.uid
            JOIN nodes t ON t.uid=e.{target} WHERE u.component_id=? AND {status}
            AND u.visibility='ACTIVE' AND {self._visible_sql('t')}
            ORDER BY e.confidence DESC,e.source,e.{target},e.id''', (own['component_id'],))
        for raw in cursor:
            edge = self._edge(raw)
            if edge[endpoint] != uid:
                edge['via_alignment'] = edge[endpoint]
                edge['alignment_relation'] = 'CROSS_SOURCE_SAME_CONCEPT'
            target_uid = edge[target]
            if target_uid in result:
                result[target_uid]['edge_evidence'].append(edge)
            elif len(result) < limit:
                item = self.node(target_uid)
                item['edge'] = edge
                item['edge_evidence'] = [edge]
                result[target_uid] = item
            else:
                break
        return list(result.values())

    def _identity_steps(self, start: str, goal: str) -> list[dict]:
        if start == goal:
            return []
        queue = deque([start])
        previous = {start: None}
        while queue:
            uid = queue.popleft()
            for raw in self.con.execute('''SELECT * FROM bridges WHERE status='ACTIVE'
                AND (left_uid=? OR right_uid=?) ORDER BY confidence DESC,id''', (uid, uid)):
                other = raw['right_uid'] if raw['left_uid'] == uid else raw['left_uid']
                if other in previous:
                    continue
                previous[other] = (uid, dict(raw))
                if other == goal:
                    path = []
                    current = goal
                    while previous[current] is not None:
                        child, edge = previous[current]
                        edge['data'] = json.loads(edge['data'] or '{}')
                        path.append(self._step(child, current, edge))
                        current = child
                    return list(reversed(path))
                queue.append(other)
        raise RuntimeError(f'Missing identity witness between {start} and {goal}')

    def _step(self, child: str, parent: str, edge: dict) -> dict:
        return {'uid': child, 'label': self.node(child)['label'], 'parent_uid': parent,
                'parent_label': self.node(parent)['label'], 'edge': edge}

    def path(self, uid: str, anchors: list[str] | None = None, max_depth: int = 64) -> list[dict]:
        if max_depth < 0:
            raise ValueError('max_depth must be nonnegative')
        own = self.node(uid)
        if not own or own['visibility'] != 'ACTIVE':
            return []
        if anchors and anchors != [self.metadata['root_uid']]:
            return self._custom_path(uid, anchors, max_depth)
        if not own['wordnet_reachable'] or own['wordnet_depth'] > max_depth:
            return []
        current = uid
        upward = []
        while True:
            component = self.con.execute('SELECT * FROM components WHERE id=(SELECT component_id FROM nodes WHERE uid=?)', (current,)).fetchone()
            if component['depth'] == 0:
                upward.extend(self._identity_steps(current, self.metadata['root_uid']))
                return list(reversed(upward))
            edge = self._edge(self.con.execute('SELECT * FROM edges WHERE id=?', (component['witness_edge_id'],)).fetchone())
            upward.extend(self._identity_steps(current, edge['child_uid']))
            upward.append(self._step(edge['child_uid'], edge['parent_uid'], edge))
            current = edge['parent_uid']

    def _custom_path(self, uid: str, anchors: list[str], max_depth: int) -> list[dict]:
        queue = deque([(uid, [], 0)])
        seen = {uid}
        goals = set(anchors)
        while queue:
            current, path, depth = queue.popleft()
            if current in goals:
                return list(reversed(path))
            for (other,) in self.con.execute('''SELECT CASE WHEN left_uid=? THEN right_uid ELSE left_uid END
                FROM bridges WHERE status='ACTIVE' AND (left_uid=? OR right_uid=?)''', (current, current, current)):
                if other not in seen:
                    seen.add(other)
                    queue.append((other, path + self._identity_steps(current, other), depth))
            if depth >= max_depth:
                continue
            for raw in self.con.execute("SELECT * FROM edges WHERE child_uid=? AND status='ACTIVE'", (current,)):
                parent = raw['parent_uid']
                if parent not in seen:
                    seen.add(parent)
                    queue.append((parent, path + [self._step(current, parent, self._edge(raw))], depth + 1))
        return []

    def target(self, dataset: str, class_id: str | int) -> dict | None:
        row = self.con.execute('SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?', (dataset, str(class_id))).fetchone()
        if not row:
            return None
        result = dict(row)
        for name in ('evidence_ids', 'provenance'):
            result[name] = json.loads(result[name] or ('[]' if name == 'evidence_ids' else '{}'))
        return result

    def stats(self) -> dict:
        return {**self.metadata, 'navigation_view': self.view, 'roots': self.roots}

    def close(self) -> None:
        if not self._closed:
            self.con.close()
            self._closed = True

    def __enter__(self) -> 'SingleAtlas':
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
