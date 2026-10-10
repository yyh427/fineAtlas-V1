"""Frozen, bounded ancestor indexes for explicitly typed text-training rewards.

This is a common-ancestor metric, not the generic undirected graph distance.
Neither identity nor scientific correctness is inferred from reachability.
"""
from collections import deque
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from .semantics import QueryLimitError

POLICIES = {
    'classification': {
        'roles': frozenset(('CLASS', 'BIOLOGICAL_VARIANT')),
        'relations': frozenset(('IS_A', 'TAXONOMIC_PARENT', 'NATIVE_CLASSIFICATION_PARENT')),
    },
    'design': {
        'roles': frozenset(('CLASS', 'MODEL', 'MODEL_FAMILY')),
        'relations': frozenset(('IS_A', 'TAXONOMIC_PARENT', 'NATIVE_CLASSIFICATION_PARENT',
                                'DESIGN_TYPE_OF', 'NATIVE_DESIGN_PARENT', 'SERIES_MEMBER_OF')),
    },
    'configuration': {
        'roles': frozenset(('CLASS', 'MODEL', 'MODEL_FAMILY', 'CONFIGURATION')),
        'relations': frozenset(('IS_A', 'TAXONOMIC_PARENT', 'NATIVE_CLASSIFICATION_PARENT',
                                'DESIGN_TYPE_OF', 'NATIVE_DESIGN_PARENT', 'SERIES_MEMBER_OF',
                                'CONFIGURATION_OF')),
    },
    'annotation': {
        'roles': frozenset(('DATASET_CATEGORY', 'CLASS', 'BIOLOGICAL_VARIANT')),
        'relations': frozenset(('DEPICTS_TYPE', 'IS_A', 'TAXONOMIC_PARENT',
                                'NATIVE_CLASSIFICATION_PARENT')),
    },
}
# Explicit opt-in: a source configuration may have a grounded physical type
# without a confirmed model/family parent. Historical configuration stays frozen.
POLICIES['configuration_types'] = {
    'roles': POLICIES['configuration']['roles'],
    'relations': POLICIES['configuration']['relations'] | frozenset(('CONFIGURATION_TYPE_OF',)),
}
DATASET_POLICIES = {
    'cub200': 'classification', 'flowers102': 'classification',
    'pets37': 'classification', 'stanford_dogs': 'classification',
    'fgvc_aircraft': 'design', 'stanford_cars': 'configuration',
}
COARSE_RANKS = frozenset(('domain_root', 'domain_entry', 'portal'))


class RelationRewardIndex:
    """Materialize each label's legal ancestors once; query without a live DB.

    ``excluded_labels`` maps class IDs to evidence/review reasons. No endpoint
    remapping or graph repair takes place. Mutating the originating Atlas view
    cannot change this frozen index. Every non-applicable result has distance
    None; callers must skip its reward term, not assign a maximum penalty.

    ``legacy`` preserves the v1.10.1 ancestor-union gate. ``reviewed_paths``
    excludes unsafe branches, requires a legal path to task_boundary_roots,
    and freezes evidence-bearing witnesses. Coarse roots only set resolution;
    they never silently define the task boundary. Source-native label identity
    is documentary scope and does not confirm an exact world-object mapping.
    """

    def __init__(self, atlas, dataset, *, policy=None, excluded_labels=None,
                 blocked_ancestors=(), coarse_roots=(), review_policy=None, max_nodes=10000,
                 uids=None, source_scope=None, requirement=None, admission_mode='legacy',
                 task_boundary_roots=(), target_scope='world', source_namespace=None, source_version=None,
                 coarse_lca_roles=()):
        if admission_mode not in ('legacy', 'reviewed_paths'):
            raise ValueError('Select legacy or reviewed_paths admission mode')
        self.admission_mode = admission_mode
        if target_scope not in ('world', 'source_native'):
            raise ValueError('Select world or source_native target scope')
        if target_scope == 'source_native' and admission_mode != 'reviewed_paths':
            raise ValueError('Source-native task targets require reviewed_paths mode')
        self.target_scope, self.source_namespace, self.source_version = target_scope, source_namespace, source_version
        if not isinstance(max_nodes, int) or max_nodes < 1:
            raise ValueError('max_nodes must be a positive integer')
        self.review_policy_sha256 = None
        if review_policy is not None:
            if excluded_labels is not None or blocked_ancestors or coarse_roots or policy is not None or source_scope is not None or requirement is not None or task_boundary_roots or coarse_lca_roles:
                raise ValueError('A frozen review policy cannot be combined with policy overrides')
            raw = Path(review_policy).read_bytes()
            review = json.loads(raw)
            if (review.get('schema') != 'FINEATLAS_RELATION_REWARD_REVIEW_V1' or
                    review.get('database_revision') != atlas._revision or
                    review.get('relation_view') != atlas.relation_view or
                    review.get('root_uid') != atlas.root_uid):
                raise ValueError('Reward review policy does not match database revision, view and root')
            config = review['datasets'][dataset]
            policy = config['policy']
            excluded_labels = config.get('excluded_labels', {})
            blocked_ancestors = config.get('blocked_ancestors', ())
            coarse_roots = config.get('coarse_roots', ())
            coarse_lca_roles = config.get('coarse_lca_roles', ())
            source_scope = config.get('source_scope')
            requirement = config.get('requirement')
            task_boundary_roots = config.get('task_boundary_roots', ())
            self.review_policy_sha256 = hashlib.sha256(raw).hexdigest()
        policy = policy or DATASET_POLICIES.get(dataset)
        if policy not in POLICIES:
            raise ValueError('Select a supported relation policy: ' + ', '.join(sorted(POLICIES)))
        if policy == 'annotation' and (target_scope != 'source_native' or admission_mode != 'reviewed_paths'):
            raise ValueError('Annotation projection requires reviewed_paths and source_native scope')
        if isinstance(coarse_lca_roles,str) or not set(coarse_lca_roles)<=POLICIES[policy]['roles']:
            raise ValueError('Coarse LCA roles must be explicit admitted roles')
        if coarse_lca_roles and admission_mode!='reviewed_paths':
            raise ValueError('Role resolution floors require reviewed_paths')
        self.coarse_lca_roles = tuple(sorted(set(coarse_lca_roles)))
        self.dataset, self.policy = dataset, policy
        self.relation_view, self.revision = atlas.relation_view, atlas._revision
        self.root_uid = atlas.root_uid
        self.source_scope = source_scope
        self.requirement = requirement or 'hierarchy'
        self.allowed_relations = sorted(POLICIES[policy]['relations'])
        self._nodes, self._parents, self._closures, self._labels = {}, {}, {}, {}
        self._identity_roles = {}
        self._component_ranks = {}
        self._conflicted_components = set()
        self._edge_records, self._excluded_edges, self._paths = {}, {}, {}
        self._navigation_status = {}
        denied = {str(k): str(v) for k,v in (excluded_labels or {}).items()}
        self._blocked = set(blocked_ancestors) | {self.root_uid}
        self._blocked_components = {atlas._basic(u)['component_id'] for u in self._blocked if atlas._basic(u)}
        self._floor_components = {atlas._basic(u)['component_id'] for u in coarse_roots if atlas._basic(u)}
        self.task_boundary_roots = tuple(task_boundary_roots) or (self.root_uid,)
        for uid in self.task_boundary_roots:
            if atlas._basic(uid) is None:
                raise ValueError('Unknown task boundary UID: ' + uid)
        self._boundary_components = {atlas._basic(u)['component_id'] for u in self.task_boundary_roots}
        # Ancestors of a declared domain floor (e.g. bird, animal, entity) do
        # not distinguish errors within that domain. Never ascend past the
        # floor to manufacture an apparently informative ancestor.
        for uid in coarse_roots:
            basic = atlas._basic(uid)
            if basic is None:
                raise ValueError('Unknown coarse root UID: ' + uid)
            closure = self._collect(atlas, uid, max_nodes)
            self._blocked_components.update(closure)
        if uids is None:
            targets=atlas.task_labels(dataset,requirement=self.requirement,
                                      target_scope=target_scope,source_namespace=source_namespace,source_version=source_version)
        else:
            targets=[{'class_id':u,'target_uid':u,'label':u,'identity_verified':True,
                      'task_admission':atlas.eligibility(u,self.requirement)} for u in dict.fromkeys(uids)]
        for target in targets:
            cid, uid = str(target['class_id']), target['target_uid']
            reason = None
            basic = atlas._basic(uid)
            if not basic:
                reason = 'UNKNOWN_UID'
            elif cid in denied:
                reason = 'LABEL_REVIEW_REQUIRED: ' + denied[cid]
            elif target.get('mapping_review') and target['mapping_review']['status']=='ANNOTATION_SCOPE_REVIEW':
                reason = 'ANNOTATION_SCOPE_REVIEW: ' + target['mapping_review']['reason']
            elif self.relation_view not in ('strict', 'taxonomy', 'unified'):
                reason = 'VIEW_NOT_APPLICABLE'
            elif not target['identity_verified']:
                reason = 'IDENTITY_UNCONFIRMED'
            elif atlas.identity(uid)['role_status'] != 'CONSISTENT':
                reason = 'IDENTITY_ROLE_CONFLICT'
            elif not target['task_admission']['usable']:
                reason = 'ENDPOINT_NOT_ADMITTED: ' + str(target['task_admission'].get('reason'))
            elif basic['node_kind'] not in POLICIES[policy]['roles']:
                reason = 'ROLE_NOT_APPLICABLE'
            label = {'class_id': cid, 'uid': uid, 'label': target['label'],
                     'identity_verified': target['identity_verified'], 'reason': reason,
                     'target_scope':target_scope,
                     'identity_scope':target.get('identity_scope','WORLD_OBJECT'),
                     'source_namespace':target.get('source_namespace'),
                     'source_version':target.get('source_version'),
                     'world_identity_verified':target.get('world_identity_verified',target['identity_verified'])}
            self._labels[cid] = label
            if self.admission_mode == 'reviewed_paths' and basic:
                self._navigation_status[cid] = bool(atlas.connection_status(uid).get('root_reachable'))
            if reason:
                self._closures[cid] = {}
                continue
            try:
                self._closures[cid] = self._collect(atlas, uid, max_nodes)
            except QueryLimitError:
                label['reason'] = 'ANCESTOR_LIMIT'
                self._closures[cid] = {}
        self.labels = MappingProxyType({k: MappingProxyType(v.copy()) for k,v in self._labels.items()})
        # A source DAG contract must actually hold in the traversed subgraph.
        remaining = {c: {p for _,p in self._parents.get(c,()) if p != c}
                     for c in self._nodes}
        reverse = {}
        for c,pp in remaining.items():
            for p in pp:
                reverse.setdefault(p,set()).add(c)
        roots = deque(c for c,pp in remaining.items() if not pp)
        processed = set()
        while roots:
            p = roots.popleft()
            processed.add(p)
            for c in reverse.get(p,()):
                remaining[c].discard(p)
                if not remaining[c]: roots.append(c)
        self._cyclic_or_cycle_dependent = set(remaining)-processed
        self._self_cycles = {c for c,pp in self._parents.items() if any(p==c for _,p in pp)}
        if self.admission_mode == 'reviewed_paths':
            self._prepare_reviewed_paths(atlas, max_nodes)

    def _component_contract(self, atlas, comp):
        if comp not in self._identity_roles:
            from .semantics import role_expression
            rows = atlas.con.execute(
                'SELECT '+role_expression('n','p')+',n.rank FROM nodes n '
                'LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.component_id=?', (comp,))
            rows = list(rows)
            roles = {r[0] for r in rows}
            self._identity_roles[comp] = sorted(roles)
            self._component_ranks[comp] = {r[1] for r in rows}
            if len(roles) > 1:
                self._conflicted_components.add(comp)
        return comp not in self._conflicted_components

    def _parents_of(self, atlas, uid):
        own = atlas._basic(uid)
        comp = own['component_id']
        if comp not in self._parents:
            accepted = []
            self._edge_records[comp] = []
            self._excluded_edges[comp] = []
            roles = POLICIES[self.policy]['roles']
            for parent, edge in atlas._parents(uid):
                # A source can retain an explicitly unplaced taxon for honest
                # navigation without certifying its uncertain lineage reward.
                basis=edge.get('data',{}).get('admission_basis',{})
                if isinstance(basis,dict) and basis.get('placement_uncertain'):
                    self._excluded_edges[comp].append({**edge, 'exclusion_reason':'PLACEMENT_UNCERTAIN'})
                    continue
                child = atlas._basic(edge['child_uid'])
                pn = atlas._basic(parent)
                if (edge['relation'] in self.allowed_relations and
                        child['node_kind'] in roles and pn['node_kind'] in roles):
                    if self.source_scope is not None and not (
                        child['source']==self.source_scope and
                        (pn['source']==self.source_scope or pn['component_id'] in (
                            self._boundary_components if self.admission_mode == 'reviewed_paths' else self._floor_components))):
                        self._excluded_edges[comp].append({**edge, 'exclusion_reason':'SOURCE_SCOPE_NOT_APPLICABLE'})
                        continue
                    if self.admission_mode == 'reviewed_paths' and not self._component_contract(atlas, pn['component_id']):
                        self._excluded_edges[comp].append({**edge, 'exclusion_reason':'IDENTITY_ROLE_CONFLICT',
                                                          'roles':self._identity_roles[pn['component_id']]})
                        continue
                    accepted.append((parent, pn['component_id']))
                    self._edge_records[comp].append((parent, pn['component_id'], edge))
                else:
                    self._excluded_edges[comp].append({**edge, 'exclusion_reason':'RELATION_OR_ROLE_NOT_APPLICABLE'})
            self._parents[comp] = tuple(sorted(set(accepted)))
        return self._parents[comp]

    def _collect(self, atlas, uid, max_nodes):
        own = atlas._basic(uid)
        found = {own['component_id']: 0}
        queue = deque([uid])
        while queue:
            current = queue.popleft()
            basic = atlas._basic(current)
            comp = basic['component_id']
            self._component_contract(atlas, comp)
            if comp not in self._nodes:
                self._nodes[comp] = {k: basic.get(k) for k in
                                     ('uid','label','source','rank','node_kind','component_id')}
            for parent, pc in self._parents_of(atlas,current):
                if pc not in found:
                    if len(found) >= max_nodes:
                        raise QueryLimitError('Reward ancestor index exceeded max_nodes')
                    found[pc] = found[comp] + 1
                    queue.append(parent)
        return found

    def _cycle_components(self):
        """Identify actual cyclic SCCs without rejecting their safe siblings."""
        graph = {c:{p for _,p in self._parents.get(c,())} for c in self._nodes}
        reverse = {c:set() for c in graph}
        for c, parents in graph.items():
            for p in parents:
                reverse.setdefault(p,set()).add(c)
        seen, order = set(), []
        for start in graph:
            if start in seen:
                continue
            seen.add(start)
            stack = [(start, iter(graph[start]))]
            while stack:
                current, parents = stack[-1]
                parent = next(parents, None)
                if parent is None:
                    order.append(current)
                    stack.pop()
                elif parent not in seen:
                    seen.add(parent)
                    stack.append((parent, iter(graph.get(parent, ()))))
        seen, cyclic = set(), set()
        for start in reversed(order):
            if start in seen:
                continue
            group, stack = set(), [start]
            seen.add(start)
            while stack:
                current = stack.pop()
                group.add(current)
                for child in reverse.get(current, ()):
                    if child not in seen:
                        seen.add(child)
                        stack.append(child)
            if len(group) > 1 or start in graph.get(start, ()):
                cyclic.update(group)
        return cyclic

    def _prepare_reviewed_paths(self, atlas, max_nodes):
        cyclic = self._cycle_components()
        goals = self._boundary_components
        self._original_closures = {cid:set(closure) for cid,closure in self._closures.items()}
        # A locally valid branch is eligible only if it also has a valid route
        # to the task boundary. The unified navigation witness is not proof.
        reverse = {}
        for comp, records in self._edge_records.items():
            if comp in cyclic:
                continue
            for parent, pc, edge in records:
                if pc in cyclic:
                    self._excluded_edges[comp].append({**edge, 'exclusion_reason':'CYCLIC_BRANCH'})
                else:
                    reverse.setdefault(pc,set()).add(comp)
        boundary_valid = set(goals) - cyclic - self._conflicted_components
        queue = deque(boundary_valid)
        while queue:
            for child in reverse.get(queue.popleft(), ()):
                if child not in boundary_valid:
                    boundary_valid.add(child)
                    queue.append(child)
        self._reviewed_parents = {}
        for comp, records in self._edge_records.items():
            accepted = []
            for parent, pc, edge in records:
                if comp in cyclic or pc in cyclic:
                    continue
                if comp not in boundary_valid or pc not in boundary_valid:
                    self._excluded_edges[comp].append({**edge, 'exclusion_reason':'NO_VALID_TASK_BOUNDARY_PATH'})
                else:
                    accepted.append((parent, pc, edge))
            self._reviewed_parents[comp] = tuple(sorted(accepted, key=lambda x:(x[0],x[2].get('id',0))))
        self._boundary_goals = goals
        self._task_boundary_valid = boundary_valid
        for cid, label in self._labels.items():
            self._paths[cid] = {}
            if label['reason']:
                continue
            uid = label['uid']
            own = atlas._basic(uid)['component_id']
            if own not in boundary_valid:
                label['reason'] = 'NO_VALID_TASK_BOUNDARY_PATH'
                self._closures[cid] = {}
                continue
            found, witnesses = {own:0}, {own:{'uid':uid, 'upward':[]}}
            queue = deque([uid])
            while queue:
                current = queue.popleft()
                comp = atlas._basic(current)['component_id']
                for parent, pc, edge in self._reviewed_parents.get(comp, ()):
                    if pc in found:
                        continue
                    if len(found) >= max_nodes:
                        raise QueryLimitError('Reviewed reward index exceeded max_nodes')
                    try:
                        segment = atlas._identity_steps(current,edge['child_uid'])
                    except RuntimeError:
                        self._excluded_edges[comp].append({**edge, 'exclusion_reason':'IDENTITY_WITNESS_MISSING'})
                        continue
                    segment += [atlas._step_for(edge['child_uid'],parent,edge)]
                    witnesses[pc] = {'uid':parent, 'upward':witnesses[comp]['upward']+segment}
                    found[pc] = found[comp]+1
                    queue.append(parent)
            self._closures[cid], self._paths[cid] = found, witnesses
            if not (found.keys() & goals):
                label['reason'] = 'NO_VALID_TASK_BOUNDARY_PATH'
                self._closures[cid] = {}
        self.labels = MappingProxyType({k:MappingProxyType(v.copy()) for k,v in self._labels.items()})

    def path(self, class_id, *, max_depth=256):
        """Frozen reviewed task witness, ending at the declared task boundary."""
        if self.admission_mode != 'reviewed_paths':
            raise ValueError('Frozen task witnesses require reviewed_paths mode')
        if not isinstance(max_depth, int) or max_depth < 0:
            raise ValueError('max_depth must be a nonnegative integer')
        cid = str(class_id)
        base = {'dataset':self.dataset, 'class_id':cid, 'relation_view':self.relation_view,
                'database_revision':self.revision, 'admission_mode':self.admission_mode,
                'target_scope':self.target_scope, 'source_namespace':self.source_namespace, 'source_version':self.source_version,
                'root_uid':self.root_uid, 'policy':self.policy, 'source_scope':self.source_scope,
                'path':[], 'task_boundary_reachable':False, 'task_path_valid':False,
                'navigation_root_reachable':self._navigation_status.get(cid,False)}
        if cid not in self._labels:
            return {**base, 'status':'UNKNOWN_LABEL'}
        label = self._labels[cid]
        base.update(uid=label['uid'], training_endpoint_applicable=label['reason'] is None,
                    training_endpoint_reason=label['reason'], excluded_branches=self._excluded_for(cid))
        if label['reason']:
            return {**base, 'status':'ENDPOINT_NOT_APPLICABLE',
                    'task_boundary_reachable':False if label['reason']=='NO_VALID_TASK_BOUNDARY_PATH' else None,
                    'task_boundary_assessment':'NO_VALID_POLICY_ROUTE' if label['reason']=='NO_VALID_TASK_BOUNDARY_PATH'
                                               else 'NOT_ASSESSED_ENDPOINT_NOT_ADMITTED'}
        closure = self._closures[cid]
        goals = sorted(closure.keys() & self._boundary_goals,
                       key=lambda c:(closure[c],self._paths[cid][c]['uid']))
        if not goals:
            return {**base, 'status':'NO_POLICY_PATH'}
        goal = goals[0]
        base['task_boundary_reachable'] = True
        if closure[goal] > max_depth:
            return {**base, 'status':'DEPTH_LIMIT'}
        return {**base, 'status':'CONNECTED' if closure[goal] else 'ROOT',
                'task_path_valid':True, 'task_boundary_uid':self._paths[cid][goal]['uid'],
                'path':list(reversed(self._paths[cid][goal]['upward'])),
                'classification_arc_count':closure[goal], 'identity_steps_cost':0}

    def _excluded_for(self, cid):
        return [edge for comp in sorted(self._original_closures.get(cid, ()))
                for edge in self._excluded_edges.get(comp, ())]

    def query(self, left, right):
        left, right = str(left), str(right)
        base = {'dataset':self.dataset, 'left':left, 'right':right,
                'database_revision':self.revision, 'relation_view':self.relation_view,
                'root_uid':self.root_uid, 'policy':self.policy,
                'metric':'minimum_upward_informative_lca_arc_sum',
                'identity_step_cost':0, 'allowed_relations':self.allowed_relations,
                'review_policy_sha256':self.review_policy_sha256,
                'source_scope':self.source_scope, 'requirement':self.requirement,
                'admission_mode':self.admission_mode,
                'target_scope':self.target_scope, 'source_namespace':self.source_namespace, 'source_version':self.source_version,
                'validation':'STRUCTURAL_SCREEN_ONLY; source/granularity review remains separate',
                'applicable':False, 'distance':None, 'lcas':[]}
        if self.policy == 'annotation':
            base['metric_scope'] = 'Source annotation projection plus taxonomic arcs; not a pure IS_A distance'
        if self.admission_mode == 'reviewed_paths':
            base.update(resolution='UNCERTAIN', task_boundary_roots=list(self.task_boundary_roots),
                        selected_paths=[], excluded_branches={cid:self._excluded_for(cid) for cid in (left,right)},
                        navigation_root_reachable={cid:self._navigation_status.get(cid,False) for cid in (left,right)},
                        task_boundary_reachable={cid:(None if cid in self._labels and self._labels[cid]['reason']
                                                      and self._labels[cid]['reason']!='NO_VALID_TASK_BOUNDARY_PATH'
                                                      else bool(self._closures.get(cid,{}).keys() & self._boundary_goals))
                                                 for cid in (left,right)})
        if left not in self._labels or right not in self._labels:
            return {**base, 'status':'UNKNOWN_LABEL'}
        reasons = {c:self._labels[c]['reason'] for c in (left,right) if self._labels[c]['reason']}
        if reasons:
            return {**base, 'status':'ENDPOINT_NOT_APPLICABLE', 'reasons':reasons,
                    **({'resolution':'UNCERTAIN' if any('REVIEW' in r or 'IDENTITY' in r or 'LIMIT' in r for r in reasons.values())
                        else 'NOT_APPLICABLE'} if self.admission_mode == 'reviewed_paths' else {})}
        a, b = self._closures[left], self._closures[right]
        conflicts=(a.keys()|b.keys())&self._conflicted_components
        if conflicts:
            return {**base,'status':'IDENTITY_LINEAGE_ROLE_CONFLICT',
                    'conflicts':[{'component_id':c,'uid':self._nodes[c]['uid'],
                                  'roles':self._identity_roles[c]} for c in sorted(conflicts)]}
        if self.admission_mode == 'legacy' and (a.keys() | b.keys()) & (self._cyclic_or_cycle_dependent | self._self_cycles):
            return {**base,'status':'CYCLIC_LINEAGE'}
        common = a.keys() & b.keys()
        if not common:
            return {**base, 'status':'NO_COMMON_ANCESTOR'}
        # Compute all DAG LCAs; immediate parent closure is sufficient because
        # ancestor sets are upward-closed. Do not arbitrarily choose one LCA.
        nonlowest = set()
        for c in common:
            parents = ((p,pc) for p,pc,_ in self._reviewed_parents.get(c,())) if self.admission_mode == 'reviewed_paths' else self._parents.get(c,())
            nonlowest.update(pc for _,pc in parents if pc in common and pc != c)
        lowest = sorted(common-nonlowest, key=lambda c:self._nodes[c]['uid'])
        base['lcas'] = [{**self._nodes[c], 'left_distance':a[c], 'right_distance':b[c]} for c in lowest]
        informative = [c for c in lowest if not (
                           bool(self._component_ranks[c] & COARSE_RANKS) if self.admission_mode == 'reviewed_paths'
                           else self._nodes[c]['rank'] in COARSE_RANKS)
                       and c not in self._blocked_components
                       and not (self.admission_mode=='reviewed_paths'
                                and set(self._identity_roles[c]) & set(self.coarse_lca_roles))]
        if self.admission_mode == 'reviewed_paths':
            base['selected_paths'] = [
                {'component_id':c, 'left':{'uid':self._paths[left][c]['uid'],
                                         'path':list(reversed(self._paths[left][c]['upward']))},
                 'right':{'uid':self._paths[right][c]['uid'],
                          'path':list(reversed(self._paths[right][c]['upward']))}}
                for c in (informative or lowest)]
            base['task_path_valid'] = True
        if not informative:
            return {**base, 'status':'COARSE_COMMON_ANCESTOR_ONLY',
                    **({'resolution':'COARSE_VALID'} if self.admission_mode == 'reviewed_paths' else {})}
        # More general common ancestors cannot provide a spurious short cut:
        # distance is minimized over informative LCAs, not over all graph roots.
        return {**base, 'status':'APPLICABLE', 'applicable':True,
                'distance':min(a[c]+b[c] for c in informative),
                **({'resolution':'FINE_VALID'} if self.admission_mode == 'reviewed_paths' else {})}

    def pairs(self):
        """Stream all unordered distinct-label pairs in deterministic ID order."""
        from itertools import combinations
        ids = sorted(self._labels, key=lambda x:(len(x),x))
        for left,right in combinations(ids,2):
            yield self.query(left,right)
