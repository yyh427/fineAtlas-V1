"""Aggregate compatible accepted identities before display limits, with provenance.

Only representation changes occur here. Node records and identity bridges remain
independent. Incomplete scans are explicitly reported rather than called exhaustive.
"""
from __future__ import annotations

import base64
from collections import defaultdict
import hashlib
import json
from ._text import norm
from .task_contract import PRESENTATION_VERSION


class PresentationAtlas:
    def _presentation_identity(self, uid: str) -> dict:
        if not hasattr(self, '_presentation_cache'):
            self._presentation_cache = {}
        node = self.node(uid)
        if not node:
            return {'key': 'uid:' + uid, 'status': 'NOT_FOUND', 'reason': 'Missing node'}
        component = node['component_id']
        if component in self._presentation_cache:
            return self._presentation_cache[component]
        identity = self.identity(uid)
        members = identity['members']
        scopes, ranks, grains = set(), set(), set()
        for member in members:
            native = []
            if 'dataset_scope_targets' in self._tables:
                native = list(self.con.execute('SELECT dataset,class_id,namespace,source_version FROM dataset_scope_targets WHERE source_uid=?',
                                               (member['uid'],)))
            if native:
                scopes.add(('native', tuple(tuple(r) for r in native)))
            elif member.get('attributes', {}).get('identity_scope') == 'SOURCE_NATIVE_LABEL':
                scopes.add(('native_unregistered', member['uid']))
            else:
                scopes.add(('world',))
            if member.get('normalized_rank'):
                ranks.add(member['normalized_rank'])
            if member.get('attributes', {}).get('object_granularity'):
                grains.add(member['attributes']['object_granularity'])
        parents = {m['uid']: m['uid'] for m in members}
        def find(value):
            while parents[value] != value:
                parents[value] = parents[parents[value]]
                value = parents[value]
            return value
        for link in identity['accepted_identity_links']:
            a, b = link['left_uid'], link['right_uid']
            if a in parents and b in parents:
                parents[find(a)] = find(b)
        connected = len({find(m) for m in parents}) == 1
        reason = ('IDENTITY_ROLE_CONFLICT' if identity['role_status'] != 'CONSISTENT'
                  else 'IDENTITY_SCOPE_CONFLICT' if len(scopes) > 1
                  else 'IDENTITY_GRANULARITY_CONFLICT' if len(ranks) > 1 or len(grains) > 1
                  else 'COMPONENT_WITHOUT_CONNECTED_ACCEPTED_PROOF' if not connected
                  else 'ACCEPTED_COMPATIBLE_IDENTITY')
        valid = reason == 'ACCEPTED_COMPATIBLE_IDENTITY'
        result = {'key': 'component:' + str(component) if valid else None,
                  'status': 'ACCEPTED' if valid else 'ISOLATED_REVIEW', 'reason': reason,
                  'member_uids': sorted(parents),
                  'accepted_bridge_ids': [r['id'] for r in identity['accepted_identity_links']]}
        self._presentation_cache[component] = result
        return result

    def candidate_search(self, text: str, limit: int = 20, domain: str | None = None,
                         *, node_kind: str | None = None, raw_scan_budget: int = 8192,
                         dataset: str | None = None, purpose: str = 'discovery', answer_scope: str = 'mixed') -> dict:
        return self.candidate_search_page(text, limit, domain, node_kind=node_kind,
                                          raw_scan_budget=raw_scan_budget, dataset=dataset,
                                          purpose=purpose, answer_scope=answer_scope)

    def candidate_search_page(self, text: str, limit: int = 20, domain: str | None = None,
                              *, node_kind: str | None = None, raw_scan_budget: int = 8192,
                              cursor: str | None = None, dataset: str | None = None,
                              purpose: str = 'discovery', answer_scope: str = 'mixed') -> dict:
        self._limit(limit)
        if limit > 1000 or not 1 <= raw_scan_budget <= 100000:
            raise ValueError('Display limit <=1000 and scan budget 1..100000 required')
        if purpose not in ('discovery', 'answers', 'navigation') or answer_scope not in ('mixed', 'source_native', 'world'):
            raise ValueError('Unknown candidate purpose or answer scope')
        context = hashlib.sha256(json.dumps([self._revision, self.relation_view, PRESENTATION_VERSION,
                                             text, domain, node_kind, raw_scan_budget, dataset, purpose, answer_scope], separators=(',', ':')).encode()).hexdigest()
        offset = 0
        if cursor:
            try:
                token = json.loads(base64.urlsafe_b64decode(cursor))
                if token['context'] != context or type(token['offset']) is not int or token['offset'] < 0:
                    raise ValueError('Cursor context mismatch')
                offset = token['offset']
            except Exception as exc:
                raise ValueError('Invalid or stale candidate cursor') from exc
        values, scans, incomplete = {}, 0, []
        for exact in (True, False):
            raw_cursor, count = None, 0
            while count < raw_scan_budget:
                page = self.search_page(text, min(256, raw_scan_budget - count), domain,
                                        node_kind=node_kind, cursor=raw_cursor, exact=exact)
                for node in page['items']:
                    values[node['uid']] = node
                count += len(page['items'])
                if not page['has_more']:
                    break
                raw_cursor = page['next_cursor']
            scans += count
            if page['has_more']:
                incomplete.append('exact' if exact else 'token')
        # Native registration has its own source range. It survives world-view
        # admission filters without changing those filters or claiming identity.
        if 'native_classes' in self._tables:
            terms = norm(text).split()
            if terms:
                sql = 'SELECT DISTINCT n.uid FROM native_classes n JOIN native_class_names a ON a.uid=n.uid WHERE '
                sql += ' AND '.join('a.search_name LIKE ? ESCAPE \'\\\'' for _ in terms)
                args = ['%' + t.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%' for t in terms]
                if domain:
                    entry = self.domain(domain)
                    if entry:
                        sql += ' AND n.domain=?'
                        args.append(entry['domain'])
                    else:
                        sql += ' AND 0'
                rows = list(self.con.execute(sql + ' ORDER BY n.uid LIMIT ?', [*args, raw_scan_budget + 1]))
                if len(rows) > raw_scan_budget:
                    incomplete.append('native')
                for row in rows[:raw_scan_budget]:
                    node = self.node(row['uid'])
                    if node and (node_kind is None or node['node_kind'] == node_kind):
                        values[node['uid']] = node
        ordered = sorted(values.values(), key=lambda n: (norm(n['label']) != norm(text), n['uid']))
        groups, conflicts = {}, {}
        for node in ordered:
            identity = self._presentation_identity(node['uid'])
            key = identity['key'] or 'uid:' + node['uid']
            if identity['status'] == 'ISOLATED_REVIEW':
                conflicts[node['component_id']] = identity
            if key not in groups:
                groups[key] = {**node, 'presentation_key': key, 'representations': [],
                               'identity_aggregation': identity}
            groups[key]['representations'].append({'uid': node['uid'], 'label': node['label'],
                                                  'source': node['source'], 'role': node['node_kind'],
                                                  'aliases': self.aliases(node['uid'], 100)})
        all_presentations = list(groups.values())
        all_items = []
        navigation_count = 0
        for item in all_presentations:
            if purpose == 'discovery':
                all_items.append(item)
                continue
            eligibility = self.candidate_contract(item['uid'], dataset=dataset)
            answer = eligibility['answer_eligible'] if answer_scope == 'mixed' else eligibility['native_answer_eligible'] if answer_scope == 'source_native' else eligibility['world_answer_eligible']
            navigation_count += int(not answer)
            if (purpose == 'answers' and answer) or (purpose == 'navigation' and not answer and eligibility['navigation_eligible']):
                all_items.append({**item, 'answer_contract': eligibility})
        items = all_items[offset:offset + limit]
        more = offset + limit < len(all_items)
        next_cursor = base64.urlsafe_b64encode(json.dumps({'context': context, 'offset': offset + limit}).encode()).decode() if more else None
        return {'items': items, 'has_more': more, 'next_cursor': next_cursor,
                'database_revision': self._revision, 'relation_view': self.relation_view,
                'presentation_rules': PRESENTATION_VERSION,
                'diagnostics': {'raw_unique_records': len(ordered), 'raw_scanned_records': scans,
                                'unique_presentations': len(all_presentations),
                                'eligible_presentations': len(all_items), 'navigation_only_presentations': navigation_count,
                                'purpose': purpose, 'answer_scope': answer_scope,
                                'aggregated_slots': len(ordered) - len(all_presentations),
                                'isolated_conflicts': list(conflicts.values()),
                                'raw_scan_budget_per_stream': raw_scan_budget,
                                'scan_complete': not incomplete, 'incomplete_streams': incomplete,
                                'ranking': 'existing exact-label priority then UID; aggregate before truncation',
                                'visual_accuracy_claim': False}}
