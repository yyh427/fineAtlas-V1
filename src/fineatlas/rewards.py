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
    """

    def __init__(self, atlas, dataset, *, policy=None, excluded_labels=None,
                 blocked_ancestors=(), coarse_roots=(), review_policy=None, max_nodes=10000,
                 uids=None, source_scope=None, requirement=None):
        if not isinstance(max_nodes, int) or max_nodes < 1:
            raise ValueError('max_nodes must be a positive integer')
        self.review_policy_sha256 = None
        if review_policy is not None:
            if excluded_labels is not None or blocked_ancestors or coarse_roots or policy is not None or source_scope is not None or requirement is not None:
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
            source_scope = config.get('source_scope')
            requirement = config.get('requirement')
            self.review_policy_sha256 = hashlib.sha256(raw).hexdigest()
        policy = policy or DATASET_POLICIES.get(dataset)
        if policy not in POLICIES:
            raise ValueError('Select classification, design or configuration policy')
        self.dataset, self.policy = dataset, policy
        self.relation_view, self.revision = atlas.relation_view, atlas._revision
        self.root_uid = atlas.root_uid
        self.source_scope = source_scope
        self.requirement = requirement or 'hierarchy'
        self.allowed_relations = sorted(POLICIES[policy]['relations'])
        self._nodes, self._parents, self._closures, self._labels = {}, {}, {}, {}
        self._identity_roles = {}
        self._conflicted_components = set()
        denied = {str(k): str(v) for k,v in (excluded_labels or {}).items()}
        self._blocked = set(blocked_ancestors) | {self.root_uid}
        self._blocked_components = {atlas._basic(u)['component_id'] for u in self._blocked if atlas._basic(u)}
        self._floor_components = {atlas._basic(u)['component_id'] for u in coarse_roots if atlas._basic(u)}
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
            targets=atlas.task_labels(dataset,requirement=self.requirement)
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
                     'identity_verified': target['identity_verified'], 'reason': reason}
            self._labels[cid] = label
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

    def _parents_of(self, atlas, uid):
        own = atlas._basic(uid)
        comp = own['component_id']
        if comp not in self._parents:
            accepted = []
            roles = POLICIES[self.policy]['roles']
            for parent, edge in atlas._parents(uid):
                # A source can retain an explicitly unplaced taxon for honest
                # navigation without certifying its uncertain lineage reward.
                basis=edge.get('data',{}).get('admission_basis',{})
                if isinstance(basis,dict) and basis.get('placement_uncertain'):
                    continue
                child = atlas._basic(edge['child_uid'])
                pn = atlas._basic(parent)
                if (edge['relation'] in self.allowed_relations and
                        child['node_kind'] in roles and pn['node_kind'] in roles):
                    if self.source_scope is not None and not (
                        child['source']==self.source_scope and
                        (pn['source']==self.source_scope or pn['component_id'] in self._floor_components)):
                        continue
                    accepted.append((parent, pn['component_id']))
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
            if comp not in self._identity_roles:
                from .semantics import role_expression
                roles={r[0] for r in atlas.con.execute(
                    'SELECT DISTINCT '+role_expression('n','p')+
                    ' FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.component_id=?',
                    (comp,))}
                self._identity_roles[comp]=sorted(roles)
                if len(roles)>1:self._conflicted_components.add(comp)
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

    def query(self, left, right):
        left, right = str(left), str(right)
        base = {'dataset':self.dataset, 'left':left, 'right':right,
                'database_revision':self.revision, 'relation_view':self.relation_view,
                'root_uid':self.root_uid, 'policy':self.policy,
                'metric':'minimum_upward_informative_lca_arc_sum',
                'identity_step_cost':0, 'allowed_relations':self.allowed_relations,
                'review_policy_sha256':self.review_policy_sha256,
                'source_scope':self.source_scope, 'requirement':self.requirement,
                'validation':'STRUCTURAL_SCREEN_ONLY; source/granularity review remains separate',
                'applicable':False, 'distance':None, 'lcas':[]}
        if left not in self._labels or right not in self._labels:
            return {**base, 'status':'UNKNOWN_LABEL'}
        reasons = {c:self._labels[c]['reason'] for c in (left,right) if self._labels[c]['reason']}
        if reasons:
            return {**base, 'status':'ENDPOINT_NOT_APPLICABLE', 'reasons':reasons}
        a, b = self._closures[left], self._closures[right]
        conflicts=(a.keys()|b.keys())&self._conflicted_components
        if conflicts:
            return {**base,'status':'IDENTITY_LINEAGE_ROLE_CONFLICT',
                    'conflicts':[{'component_id':c,'uid':self._nodes[c]['uid'],
                                  'roles':self._identity_roles[c]} for c in sorted(conflicts)]}
        if (a.keys() | b.keys()) & (self._cyclic_or_cycle_dependent | self._self_cycles):
            return {**base,'status':'CYCLIC_LINEAGE'}
        common = a.keys() & b.keys()
        if not common:
            return {**base, 'status':'NO_COMMON_ANCESTOR'}
        # Compute all DAG LCAs; immediate parent closure is sufficient because
        # ancestor sets are upward-closed. Do not arbitrarily choose one LCA.
        nonlowest = set()
        for c in common:
            nonlowest.update(pc for _,pc in self._parents.get(c,()) if pc in common and pc != c)
        lowest = sorted(common-nonlowest, key=lambda c:self._nodes[c]['uid'])
        base['lcas'] = [{**self._nodes[c], 'left_distance':a[c], 'right_distance':b[c]} for c in lowest]
        informative = [c for c in lowest if self._nodes[c]['rank'] not in COARSE_RANKS
                       and c not in self._blocked_components]
        if not informative:
            return {**base, 'status':'COARSE_COMMON_ANCESTOR_ONLY'}
        # More general common ancestors cannot provide a spurious short cut:
        # distance is minimized over informative LCAs, not over all graph roots.
        return {**base, 'status':'APPLICABLE', 'applicable':True,
                'distance':min(a[c]+b[c] for c in informative)}

    def pairs(self):
        """Stream all unordered distinct-label pairs in deterministic ID order."""
        from itertools import combinations
        ids = sorted(self._labels, key=lambda x:(len(x),x))
        for left,right in combinations(ids,2):
            yield self.query(left,right)
