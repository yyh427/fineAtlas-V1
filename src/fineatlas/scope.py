"""Evidence-preserving bounded ranges over classification and typed references.

The graph supplies the pool. Dataset context supplies answer rules, never an
implicit class whitelist. A reference path does not establish world identity.
"""
from __future__ import annotations

import base64
import copy
from collections import deque
import hashlib
import json

from ._text import norm
from .hierarchy import validate_link_roles
from .semantics import classification_roles, edge_predicate, terminal_relations

SCOPE_RULES = 'grounded-mixed-range-v1'
SOURCE_UNIT_GRAINS = {
    'publisher_visual_variant': {'variant', 'visual_variant'},
    'publisher_breed_label': {'breed'},
    'source_breed_label': {'breed'},
    'source_wild_canid_species_label': {'species'},
    'author_make_design_body_year_annotation': {'annotation_combination'},
}


class ScopeAtlas:
    def _scope_members(self, uid):
        identity = self._presentation_identity(uid)
        return identity['member_uids'] if identity['status'] == 'ACCEPTED' else [uid]

    def _scope_links(self, uid, *, direction='children', mixed=True):
        """Indexed endpoint queries; no cached unique-parent assumption."""
        own = self._basic(uid)
        if not self._node_admitted(own):
            return
        seen = set()
        for member in self._scope_members(uid):
            endpoint = 'parent_uid' if direction == 'children' else 'child_uid'
            for row in self.con.execute(
                    f'SELECT * FROM edges e WHERE e.{endpoint}=? AND '
                    + edge_predicate(self.relation_view) + ' ORDER BY e.id', (member,)):
                child, parent = self._basic(row['child_uid']), self._basic(row['parent_uid'])
                if (not self._node_admitted(child) or not self._node_admitted(parent)
                        or child['node_kind'] not in classification_roles(self.relation_view)
                        or parent['node_kind'] not in classification_roles(self.relation_view)):
                    continue
                key = ('edges', row['id'])
                if key in seen:
                    continue
                seen.add(key)
                yield self._scope_arc(dict(row), 'edges')
            if not mixed or 'entity_relations' not in self._tables:
                continue
            endpoint = 'object_uid' if direction == 'children' else 'subject_uid'
            for row in self.con.execute(
                    f"SELECT * FROM entity_relations WHERE {endpoint}=? AND status='ACTIVE' ORDER BY id",
                    (member,)):
                child, parent = self._basic(row['subject_uid']), self._basic(row['object_uid'])
                if not self._node_admitted(child) or not self._node_admitted(parent):
                    continue
                if row['relation'] not in terminal_relations(child['node_kind'], self.relation_view):
                    continue
                try:
                    validate_link_roles(row['relation'], child['node_kind'], parent['node_kind'])
                except ValueError:
                    continue
                key = ('entity_relations', row['id'])
                if key in seen:
                    continue
                seen.add(key)
                yield self._scope_arc(dict(row), 'entity_relations')

    @staticmethod
    def _scope_arc(row, storage):
        data = json.loads(row.get('data') or '{}')
        provenance = row.get('provenance') or '{}'
        try:
            provenance = json.loads(provenance)
        except (ValueError, TypeError):
            provenance = {'source_provenance': provenance}
        if not isinstance(provenance, dict):
            provenance = {'source_provenance': provenance}
        if not isinstance(data, dict):
            data = {'source_claim': data}
        eid = row.get('evidence_id') or provenance.get('evidence_id') or data.get('evidence_id')
        return {'child_uid': row.get('child_uid', row.get('subject_uid')),
                'parent_uid': row.get('parent_uid', row.get('object_uid')),
                'relation': row['relation'], 'storage': storage, 'id': row['id'],
                'source': row['source'], 'evidence_id': eid,
                'source_provenance': provenance, 'claim': data,
                'strict_inclusion': storage == 'edges' and row['relation'] == 'IS_A'}

    def _scope_pool(self, anchors, *, mixed, max_depth, node_budget, edge_budget):
        context = (self._revision, self.relation_view, tuple(anchors), mixed,
                   max_depth, node_budget, edge_budget)
        if not hasattr(self, '_range_cache'):
            self._range_cache = {}
        if context in self._range_cache:
            return self._range_cache[context]
        values, queue, anchor_keys = {}, deque(), set()
        for anchor in anchors:
            entry = self.domain(anchor)
            for uid in entry['root_uids'] if entry else [anchor]:
                if not self._node_admitted(self._basic(uid)):
                    raise ValueError('Missing or inadmissible scope anchor: ' + uid)
                identity = self._presentation_identity(uid)
                key = identity['key'] or 'uid:' + uid
                anchor_keys.add(key)
                if key not in values:
                    values[key] = {'uid': uid, 'path': [], 'depth': 0,
                                   'representations': set(self._scope_members(uid)), 'incoming': {}}
                    queue.append(key)
        incomplete, edges = set(), 0
        while queue:
            parent_key = queue.popleft()
            parent = values[parent_key]
            if parent['depth'] >= max_depth:
                continue
            for arc in self._scope_links(parent['uid'], mixed=mixed):
                edges += 1
                if edges > edge_budget:
                    incomplete.add('EDGE_BUDGET')
                    queue.clear()
                    break
                identity = self._presentation_identity(arc['child_uid'])
                key = identity['key'] or 'uid:' + arc['child_uid']
                if key == parent_key:
                    incomplete.add('IDENTITY_SELF_LOOP')
                    continue
                step = {**arc, 'from_uid': parent['uid'], 'to_uid': arc['child_uid'],
                        'from_label': self._basic(parent['uid'])['label'],
                        'to_label': self._basic(arc['child_uid'])['label']}
                if arc['parent_uid'] != parent['uid']:
                    transfer = self._presentation_identity(parent['uid'])
                    step['parent_identity_transfer'] = transfer
                if key not in values:
                    if len(values) >= node_budget:
                        incomplete.add('NODE_BUDGET')
                        queue.clear()
                        break
                    values[key] = {'uid': arc['child_uid'], 'path': parent['path'] + [step],
                                   'depth': parent['depth'] + 1, 'representations': set(), 'incoming': {}}
                    queue.append(key)
                values[key]['representations'].update(self._scope_members(arc['child_uid']))
                values[key]['incoming'][(arc['storage'], arc['id'])] = arc
        pool = {'values': values, 'anchor_keys': anchor_keys, 'edges_scanned': edges,
                'scan_complete': not incomplete, 'incomplete_reasons': sorted(incomplete)}
        if len(self._range_cache) >= 8:
            self._range_cache.pop(next(iter(self._range_cache)))
        self._range_cache[context] = pool
        return pool

    def scope_candidates(self, anchors, *, limit=20, cursor=None, dataset=None,
                         target_granularity=None, purpose='answers', route_mode='mixed',
                         max_depth=16, node_budget=20000, edge_budget=100000, text=None):
        """Model-chosen anchors -> dynamic candidates, aliases and typed paths.

        source_category is an explicit annotation-unit request, not a dataset
        enumeration. With no grain constraint the pool includes world objects.
        """
        if isinstance(anchors, str):
            anchors = [anchors]
        anchors = sorted(set(anchors))
        grains = sorted(set(target_granularity or []))
        if (not anchors or len(anchors) > 16 or not 1 <= limit <= 1000
                or not 1 <= max_depth <= 64 or not 1 <= node_budget <= 100000
                or not 1 <= edge_budget <= 500000):
            raise ValueError('Invalid bounded scope query')
        if purpose not in ('answers', 'navigation', 'discovery') or route_mode not in ('mixed', 'classification'):
            raise ValueError('Unknown scope purpose or route mode')
        context = hashlib.sha256(json.dumps([self._revision, SCOPE_RULES, self.relation_view,
            anchors, dataset, grains, purpose, route_mode, max_depth, node_budget, edge_budget, text],
            sort_keys=True).encode()).hexdigest()
        offset = 0
        if cursor:
            try:
                token = json.loads(base64.urlsafe_b64decode(cursor))
                if token['context'] != context or type(token['offset']) is not int or token['offset'] < 0:
                    raise ValueError('Mismatched context')
                offset = token['offset']
            except Exception as exc:
                raise ValueError('Invalid or stale scope cursor') from exc
        pool = self._scope_pool(anchors, mixed=route_mode == 'mixed', max_depth=max_depth,
                                node_budget=node_budget, edge_budget=edge_budget)
        if not hasattr(self, '_range_native_uids'):
            self._range_native_uids = {r[0] for r in self.con.execute('SELECT uid FROM native_classes')} if 'native_classes' in self._tables else set()
        if not hasattr(self, '_range_item_cache'):
            self._range_item_cache = {}
        cached_items = self._range_item_cache.get(context)
        candidates = [] if cached_items is None else cached_items
        for key, reached in pool['values'].items() if cached_items is None else ():
            if key in pool['anchor_keys']:
                continue
            uid = reached['uid']
            native = uid in self._range_native_uids
            if grains == ['source_category'] and not native:
                continue
            node = self.node(uid)
            grain = 'source_category' if native else self.effective_granularity(uid)['unit'] or 'UNKNOWN'
            grain_options = {grain}
            if native:
                grain_options.update(r[0] for r in self.con.execute('SELECT object_granularity FROM native_classes WHERE uid=?', (uid,)))
                grain_options.add(node.get('attributes', {}).get('source_unit'))
                grain_options.update(SOURCE_UNIT_GRAINS.get(node.get('attributes', {}).get('source_unit'), set()))
            if grains and not grain_options.intersection(grains):
                continue
            contract = self.candidate_contract(uid, dataset=dataset)
            if purpose == 'answers' and not contract['answer_eligible']:
                continue
            if purpose == 'navigation' and (contract['answer_eligible'] or not contract['navigation_eligible']):
                continue
            aliases = [node['label']]
            for member in sorted(reached['representations']):
                aliases.extend(n.get('name') or n.get('raw_alias') or n.get('alias', '') for n in self.aliases(member, 100))
            aliases = sorted(set(a for a in aliases if a))
            if text and not all(t in norm(' '.join(aliases)) for t in norm(text).split()):
                continue
            path = reached['path']
            candidates.append({**node, 'presentation_key': key, 'answer_contract': contract,
                'scope_granularity': grain, 'name_index': aliases,
                'representations': [{'uid': u, 'label': self._basic(u)['label']} for u in sorted(reached['representations'])],
                'reachability': {'anchors': anchors, 'path': path,
                    'strict_descendant': all(e['strict_inclusion'] for e in path),
                    'source_category_reference': native and any(e['relation'] in ('DEPICTS_TYPE','DEPICTS_DESIGN') for e in path),
                    'native_class_reference': native,
                    'world_identity_equivalence_implied': False,
                    'incoming_evidence': list(reached['incoming'].values())}})
        candidates.sort(key=lambda r: (len(r['reachability']['path']),
            r['answer_contract']['answer_eligible'] if max_depth==1 and purpose=='discovery' else False,
            r['label'].casefold() if max_depth==1 and purpose=='discovery' else '', r['uid']))
        if cached_items is None:
            if len(self._range_item_cache) >= 8:
                self._range_item_cache.pop(next(iter(self._range_item_cache)))
            self._range_item_cache[context] = candidates
        items = copy.deepcopy(candidates[offset:offset + limit])
        more = offset + limit < len(candidates)
        token = base64.urlsafe_b64encode(json.dumps({'context': context, 'offset': offset + limit}).encode()).decode() if more else None
        return {'items': items, 'has_more': more, 'next_cursor': token,
                'database_revision': self._revision, 'relation_view': self.relation_view,
                'scope_rules': SCOPE_RULES, 'diagnostics': {'anchors': anchors,
                    'scan_complete': pool['scan_complete'], 'incomplete_reasons': pool['incomplete_reasons'],
                    'visited_presentations': len(pool['values']), 'edges_scanned': pool['edges_scanned'],
                    'declared_max_depth': max_depth,
                    'ranking': 'depth; navigation first and label for direct expansion; UID otherwise',
                    'eligible_presentations': len(candidates), 'aggregate_before_truncation': True,
                    'dataset_is_implicit_whitelist': False, 'model_recognition_measured': False}}

    def expand_scope(self, anchor, **kwargs):
        entry = self.domain(anchor)
        if entry:
            # A domain is a portal to its registered roots. Present those
            # choices first, rather than silently expanding all roots together.
            limit = kwargs.pop('limit', 20)
            cursor = kwargs.pop('cursor', None)
            dataset = kwargs.get('dataset')
            context = hashlib.sha256(json.dumps([self._revision, self.relation_view,
                entry['uid'], dataset, 'DOMAIN_ENTRY_ROOT', kwargs], sort_keys=True).encode()).hexdigest()
            if not 1 <= limit <= 1000:
                raise ValueError('Invalid domain-root page limit')
            offset = 0
            if cursor:
                try:
                    token = json.loads(base64.urlsafe_b64decode(cursor))
                    if token['context'] != context or type(token['offset']) is not int or token['offset'] < 0:
                        raise ValueError('Mismatched root cursor')
                    offset = token['offset']
                except Exception as exc:
                    raise ValueError('Invalid or stale scope cursor') from exc
            grouped = {}
            for uid in sorted(entry['root_uids']):
                node = self.node(uid)
                if not node or not self._node_admitted(self._basic(uid)):
                    continue
                identity = self._presentation_identity(uid)
                key = identity['key'] or 'uid:'+uid
                arc = {'from_uid':entry['uid'], 'to_uid':uid,
                    'from_label':entry['label'], 'to_label':node['label'],
                    'relation':'DOMAIN_ENTRY_ROOT', 'strict_inclusion':False,
                    'source':'domain_registry', 'evidence_id':None,
                    'source_provenance':{'domain':entry['domain'], 'registered_root_uids':entry['root_uids'],
                        'claim':'Configured navigation entrance, not biological or design inclusion'}}
                if key in grouped:
                    grouped[key]['reachability']['incoming_evidence'].append(arc)
                    continue
                contract = self.candidate_contract(uid, dataset=dataset)
                contract.update(native_answer_eligible=False, world_answer_eligible=False,
                    answer_eligible=False, navigation_eligible=True, reason='DOMAIN_ROOT_NAVIGATION_CHOICE')
                grouped[key] = {**node, 'presentation_key':key, 'answer_contract':contract,
                    'name_index':[node['label']], 'representations':[{'uid':u,'label':self._basic(u)['label']}
                        for u in self._scope_members(uid)], 'reachability':{'path':[arc],
                        'strict_descendant':False, 'world_identity_equivalence_implied':False,
                        'incoming_evidence':[arc]}}
            rows = sorted(grouped.values(), key=lambda n:(n['label'].casefold(),n['uid']))
            more = offset+limit < len(rows)
            token = base64.urlsafe_b64encode(json.dumps({'context':context,'offset':offset+limit}).encode()).decode() if more else None
            return {'items':copy.deepcopy(rows[offset:offset+limit]), 'has_more':more, 'next_cursor':token,
                'diagnostics':{'scan_complete':True, 'incomplete_reasons':[], 'eligible_presentations':len(rows),
                    'aggregate_before_truncation':True, 'dataset_is_implicit_whitelist':False,
                    'navigation_relation':'DOMAIN_ENTRY_ROOT', 'model_recognition_measured':False},
                'scope_rules':SCOPE_RULES, 'database_revision':self._revision, 'relation_view':self.relation_view}
        return self.scope_candidates(anchor, max_depth=1, purpose='discovery', **kwargs)

    def scope_path(self, uid, domain, *, max_depth=64, node_budget=10000):
        """Structural witness only; it never chooses an anchor for a model."""
        entry = self.domain(domain)
        if not entry or not self._node_admitted(self._basic(uid)):
            return {'status': 'NOT_FOUND', 'path': []}
        roots = {self._presentation_identity(u)['key'] or 'uid:'+u: u for u in entry['root_uids']}
        parents = list(self._scope_links(uid, direction='parents'))
        def priority(arc):
            parent = arc['parent_uid']
            if parent.startswith(('stanford-cars-2013:design-label-scope:', 'wordnet30-source:')):
                return 0
            if parent in entry['root_uids']:
                return 2
            return 1
        parents.sort(key=lambda e: (priority(e), e['parent_uid'], e['id']))
        for initial in parents:
            queue = deque([(initial['parent_uid'], [initial])])
            seen = set()
            while queue:
                current, path = queue.popleft()
                identity = self._presentation_identity(current)
                key = identity['key'] or 'uid:'+current
                if key in seen:
                    continue
                seen.add(key)
                if len(seen) > node_budget:
                    return {'status': 'QUERY_LIMIT', 'path': []}
                if key in roots:
                    root = roots[key]
                    steps = []
                    from_uid = root
                    for arc in reversed(path):
                        steps.append({**arc, 'from_uid': from_uid, 'to_uid': arc['child_uid'],
                            'from_label': self._basic(from_uid)['label'],
                            'to_label': self._basic(arc['child_uid'])['label'],
                            'parent_identity_transfer': self._presentation_identity(from_uid)
                                if arc['parent_uid'] != from_uid else None})
                        from_uid = arc['child_uid']
                    return {'status': 'CONNECTED', 'domain_entry': entry['uid'], 'root_uid': root,
                            'path': steps, 'world_identity_equivalence_implied': False}
                if len(path) >= max_depth:
                    continue
                for arc in self._scope_links(current, direction='parents'):
                    queue.append((arc['parent_uid'], path+[arc]))
        return {'status': 'UNREACHABLE_IN_VIEW', 'domain_entry': entry['uid'], 'path': []}
