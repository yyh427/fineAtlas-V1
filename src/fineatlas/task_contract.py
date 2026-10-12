"""Shared, scope-explicit rules for candidates, feedback and exact evaluation.

Dataset categories are documentary supervision units. They are never promoted
to world identities by this module. Backend label checks are separate from
model-issued open queries and candidate constraints.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from pathlib import Path
import unicodedata
from typing import Any

RULE_VERSION = 'native-world-exact-v1'
PRESENTATION_VERSION = 'reviewed-scope-aggregation-v1'
SOURCE_NATIVE_SCOPES = frozenset(('SOURCE_NATIVE_LABEL', 'SOURCE_NATIVE_DATASET_CATEGORY',
                                  'SOURCE_SUPERVISION_CATEGORY'))


def exact_name(value: str) -> str:
    """Case/spacing/underscore normalization, retaining meaningful qualifiers."""
    return ' '.join(unicodedata.normalize('NFKC', value).replace('_', ' ').casefold().split())


@dataclass(frozen=True)
class RunConfig:
    database: str
    database_revision: str
    sdk_version: str
    code_commit: str
    relation_view: str = 'unified'
    target_scope: str = 'source_native'
    admission_mode: str = 'reviewed_paths'
    evaluation_rules: str = RULE_VERSION
    presentation_rules: str = PRESENTATION_VERSION
    inference_mode: str = 'open'
    closed_dataset: str | None = None
    hierarchy_reward_enabled: bool = False

    def __post_init__(self) -> None:
        if self.target_scope not in ('source_native', 'world'):
            raise ValueError('Unknown target scope')
        if self.relation_view not in ('strict', 'taxonomy', 'membership', 'unified'):
            raise ValueError('Unknown relation view')
        if self.admission_mode not in ('legacy', 'reviewed_paths'):
            raise ValueError('Unknown admission mode')
        if self.evaluation_rules != RULE_VERSION or self.presentation_rules != PRESENTATION_VERSION:
            raise ValueError('Unsupported rule version')
        if self.inference_mode not in ('open', 'closed'):
            raise ValueError('Select explicit open or closed mode')
        if (self.inference_mode == 'closed') != bool(self.closed_dataset):
            raise ValueError('Only an explicit closed mode may have a class whitelist')
        if self.hierarchy_reward_enabled:
            raise ValueError('Accuracy-priority experiments do not enable hierarchy rewards')
        if not all((self.database_revision, self.sdk_version, self.code_commit)):
            raise ValueError('Pin database, SDK and code versions')

    @classmethod
    def read(cls, path: str | Path) -> RunConfig:
        return cls(**json.loads(Path(path).read_text()))

    def validate(self, atlas: Any) -> None:
        from . import __version__
        if atlas.metadata.get('database_revision') != self.database_revision:
            raise ValueError('Run config belongs to another database revision')
        if atlas.relation_view != self.relation_view or __version__ != self.sdk_version:
            raise ValueError('Run config SDK or relationship view mismatch')
        if atlas.metadata.get('repair_code_commit') != self.code_commit:
            raise ValueError('Run config code receipt mismatch')
        manifest = atlas.metadata.get('repair_sdk_manifest')
        if atlas.metadata.get('native755_ready') and not manifest:
            raise ValueError('Repaired candidate code receipt is not sealed yet')
        if manifest:
            root = Path(__file__).resolve().parent
            for name, signature in manifest.items():
                file = root / name
                if (file.parent != root or not file.is_file()
                    or hashlib.sha256(file.read_bytes()).hexdigest() != signature):
                    raise ValueError('Installed SDK differs from candidate code receipt: ' + name)
            checkout = root.parents[1]
            if (checkout / '.git').exists():
                import subprocess
                head = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'],
                                      check=True, capture_output=True, text=True).stdout.strip()
                if head != self.code_commit:
                    raise ValueError('Checkout commit differs from pinned run config')

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskContractAtlas:
    """Mixin for the normalized complete database, with conservative identity rules."""

    def native_class(self, dataset: str, class_id: str, *, source_version: str | None = None) -> dict | None:
        if 'native_classes' not in self._tables:
            raise ValueError('This database has no repaired native-class contract')
        sql = 'SELECT * FROM native_classes WHERE dataset=? AND class_id=?'
        args = [dataset, str(class_id)]
        if source_version is not None:
            sql += ' AND source_version=?'
            args.append(source_version)
        rows = list(self.con.execute(sql + ' ORDER BY source_version,uid', args))
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError('Ambiguous dataset version: pin source_version')
        result = dict(rows[0])
        result['proof'] = json.loads(result['proof'])
        result['evidence_ids'] = json.loads(result['evidence_ids'])
        own = self.node(result['uid'])
        evidence_present = bool(result['evidence_ids']) and all(self.con.execute(
            'SELECT 1 FROM evidence WHERE evidence_id=? LIMIT 1', (eid,)).fetchone() for eid in result['evidence_ids'])
        result['native_usable'] = bool(result['training_id_verified'] and own and own['visibility'] == 'ACTIVE'
                                       and own['node_kind'] == result['role'] and result['namespace']
                                       and result['source_version'] and isinstance(result['proof'], dict)
                                       and result['proof'] and evidence_present)
        result['identity_scope'] = 'SOURCE_NATIVE_LABEL'
        result['world_mapping'] = self.world_mapping_status(dataset, str(class_id))
        return result

    def resolve_native_name(self, text: str, *, dataset: str | None = None,
                            namespace: str | None = None, source_version: str | None = None) -> dict:
        if 'native_class_names' not in self._tables:
            raise ValueError('This database has no repaired native-name contract')
        sql = '''SELECT DISTINCT n.* FROM native_class_names a JOIN native_classes n
                 ON n.uid=a.uid WHERE a.normalized_name=?'''
        args = [exact_name(text)]
        for key, value in [('dataset', dataset), ('namespace', namespace), ('source_version', source_version)]:
            if value is not None:
                sql += ' AND n.' + key + '=?'
                args.append(value)
        rows = [dict(r) for r in self.con.execute(sql + ' ORDER BY n.dataset,n.source_version,n.class_id,n.uid', args)]
        return {'status': 'NOT_FOUND' if not rows else 'RESOLVED' if len(rows) == 1 else 'AMBIGUOUS',
                'items': rows, 'query': text, 'identity_scope': 'SOURCE_NATIVE_LABEL',
                'resolution_basis': 'EVIDENCED_FULL_LABEL; no prefix or world-identity guess',
                'database_revision': self._revision}

    def world_mapping_status(self, dataset: str, class_id: str) -> dict:
        world = self.target(dataset, str(class_id), target_scope='world')
        disposition = None
        if 'world_mapping_dispositions' in self._tables:
            row = self.con.execute('SELECT * FROM world_mapping_dispositions WHERE dataset=? AND class_id=?',
                                   (dataset, str(class_id))).fetchone()
            disposition = dict(row) if row else None
        native_target = bool(world and 'native_classes' in self._tables and self.con.execute(
            'SELECT 1 FROM native_classes WHERE uid=? LIMIT 1', (world['target_uid'],)).fetchone())
        if world and 'node_profiles' in self._tables:
            scope = self.con.execute("SELECT json_extract(attributes,'$.identity_scope') FROM node_profiles WHERE uid=?",
                                     (world['target_uid'],)).fetchone()
            native_target = native_target or bool(scope and scope[0] in SOURCE_NATIVE_SCOPES)
        confirmed = bool(world and not native_target and world.get('identity_verified') and
                         (not disposition or disposition['effective_status'] == 'CONFIRMED'))
        return {'uid': world.get('target_uid') if world else None,
                'target_object_scope': 'SOURCE_NATIVE_LABEL' if native_target else 'WORLD_OBJECT_TARGET' if world else 'NO_WORLD_TARGET',
                'stored_status': world.get('decision_status') if world else None,
                'stored_identity_claim_verified': bool(world and world.get('stored_identity_claim_verified')),
                'effective_status': disposition['effective_status'] if disposition else 'CONFIRMED' if confirmed else 'REVIEW',
                'world_identity_verified': confirmed,
                'reason': disposition['reason'] if disposition else (world or {}).get('mapping_kind', 'NO_WORLD_MAPPING'),
                'evidence_ids': json.loads(disposition['evidence_ids']) if disposition else (world or {}).get('evidence_ids', []),
                'missing_evidence': disposition['missing_evidence'] if disposition else None,
                'historical_claim_retained': True}

    def candidate_contract(self, uid: str, *, dataset: str | None = None) -> dict:
        node = self.node(uid)
        if not node:
            return {'uid': uid, 'answer_eligible': False, 'navigation_eligible': False, 'reason': 'NOT_FOUND'}
        if node.get('navigation_only') or node.get('node_kind') == 'DOMAIN_ENTRY':
            return {'uid': uid, 'identity_scope': 'NAVIGATION', 'role': node['node_kind'],
                    'object_granularity': None, 'granularity_status': 'NAVIGATION_ONLY',
                    'native_answer_eligible': False, 'world_answer_eligible': False,
                    'answer_eligible': False, 'navigation_eligible': True,
                    'mapping_statuses': [], 'reason': 'NAVIGATION_ENTRY_NOT_EXACT_ANSWER'}
        native_rows = []
        if 'native_classes' in self._tables:
            native_rows = [dict(r) for r in self.con.execute('SELECT * FROM native_classes WHERE uid=?', (uid,))]
        native = [r for r in native_rows if dataset is None or r['dataset'] == dataset]
        usable_native = [r for r in native if self.native_class(
            r['dataset'], r['class_id'], source_version=r['source_version'])['native_usable']]
        role = node['node_kind']
        identity = self.identity(uid)
        role_consistent = bool(identity and identity['role_status'] == 'CONSISTENT')
        # Rank absence is reported, never repaired with a guessed species/breed.
        world_role = role in ('CLASS', 'BIOLOGICAL_VARIANT', 'MODEL', 'MODEL_FAMILY', 'CONFIGURATION', 'INSTANCE', 'ATTRIBUTE')
        source_scope = node.get('attributes', {}).get('identity_scope')
        world_unit = node.get('normalized_rank') or node.get('attributes', {}).get('object_granularity')
        world_eligible = bool(node['visibility'] == 'ACTIVE' and world_role and role_consistent
                              and uid != self.root_uid
                              and not native_rows and source_scope not in SOURCE_NATIVE_SCOPES
                              and source_scope != 'SOURCE_VERSION_CONCEPT')
        task_reason = None
        mapped = []
        mapped_statuses = []
        if dataset is not None and 'world_mapping_dispositions' in self._tables:
            mapped = list(self.con.execute('SELECT d.class_id,d.effective_status FROM world_mapping_dispositions d JOIN nodes n ON n.uid=d.uid WHERE d.dataset=? AND n.component_id=?',
                                          (dataset, node['component_id'])))
            mapped_statuses = [self.world_mapping_status(dataset, r['class_id']) for r in mapped]
        known_exact_scope = any(s['world_identity_verified'] for s in mapped_statuses)
        if dataset is not None and 'dataset_answer_contracts' in self._tables and world_eligible:
            definition = self.con.execute('SELECT payload FROM dataset_answer_contracts WHERE dataset=?', (dataset,)).fetchone()
            if definition:
                definition = json.loads(definition[0])
                if not hasattr(self, '_task_navigation_components'):
                    self._task_navigation_components = {}
                if dataset not in self._task_navigation_components:
                    self._task_navigation_components[dataset] = {
                        row[0] for u in definition.get('navigation_only_uids', [])
                        for row in self.con.execute('SELECT component_id FROM nodes WHERE uid=?', (u,))}
                if node['component_id'] in self._task_navigation_components[dataset] and not known_exact_scope:
                    world_eligible, task_reason = False, 'TASK_COARSE_OBJECT_IS_NAVIGATION_ONLY'
                elif role not in definition['world_roles']:
                    world_eligible, task_reason = False, 'WORLD_ROLE_NOT_TASK_ANSWER_UNIT'
                elif definition.get('world_ranks') is not None and node.get('normalized_rank') not in definition['world_ranks']:
                    world_eligible, task_reason = False, 'WORLD_GRAIN_NOT_TASK_ANSWER_UNIT_OR_UNKNOWN'
                elif definition.get('excluded_world_ranks') and node.get('normalized_rank') in definition['excluded_world_ranks']:
                    world_eligible, task_reason = False, 'WORLD_GRAIN_NOT_TASK_ANSWER_UNIT'
                elif (definition.get('require_world_class_unit_evidence') and role in ('CLASS', 'BIOLOGICAL_VARIANT')
                      and not known_exact_scope and (not world_unit or str(world_unit).upper() in ('UNKNOWN', 'UNKNOWN_SOURCE_UNIT', 'CLASS', 'TAXON'))):
                    world_eligible, task_reason = False, 'WORLD_CLASS_UNIT_NOT_ESTABLISHED_FOR_TASK'
                elif definition.get('world_navigation_anchors'):
                    anchors = definition['world_navigation_anchors']
                    if not known_exact_scope and (uid in anchors or not self.path_result(uid, anchors=anchors)['path']):
                        world_eligible, task_reason = False, 'NO_GROUNDED_TASK_OBJECT_SCOPE'
        if mapped:
            if mapped and not any(r['effective_status'] == 'CONFIRMED' for r in mapped):
                world_eligible, task_reason = False, 'DATASET_WORLD_MAPPING_NOT_CONFIRMED'
        native_eligible = bool(usable_native)
        return {'uid': uid, 'identity_scope': 'SOURCE_NATIVE_LABEL' if native_rows else source_scope or 'WORLD',
                'role': role, 'object_granularity': native_rows[0]['object_granularity'] if native_rows else world_unit,
                'granularity_status': 'SOURCE_DECLARED' if native_rows else node.get('rank_status', 'UNKNOWN'),
                'native_answer_eligible': native_eligible, 'world_answer_eligible': world_eligible,
                'answer_eligible': native_eligible or world_eligible,
                'navigation_eligible': bool(node['visibility'] == 'ACTIVE'),
                'world_identity_verified_for_dataset': any(s['world_identity_verified'] for s in
                    [self.world_mapping_status(r['dataset'], r['class_id']) for r in native] + mapped_statuses),
                'mapping_statuses': [self.world_mapping_status(r['dataset'], r['class_id']) for r in native] + mapped_statuses,
                'identity_role_status': identity['role_status'] if identity else 'UNKNOWN',
                'reason': 'SOURCE_NATIVE_LABEL_AVAILABLE' if native_eligible else 'WORLD_OBJECT_AVAILABLE' if world_eligible else task_reason or 'NAVIGATION_OR_REVIEW_ONLY'}

    def evaluate_exact(self, dataset: str, class_id: str, *, predicted_uid: str | None = None,
                       predicted_label: str | None = None, source_version: str | None = None) -> dict:
        """Private evaluator entry; class_id must never be forwarded to query()."""
        native = self.native_class(dataset, class_id, source_version=source_version)
        if not native or not native['native_usable']:
            return {'status': 'NOT_APPLICABLE', 'reason': 'NATIVE_CLASS_NOT_USABLE', 'native_exact': None, 'world_exact': None}
        native_hit = predicted_uid == native['uid'] if predicted_uid else False
        resolution = None
        if not predicted_uid and predicted_label is not None:
            resolution = self.resolve_native_name(predicted_label, dataset=dataset,
                                                  namespace=native['namespace'], source_version=native['source_version'])
            native_hit = resolution['status'] == 'RESOLVED' and resolution['items'][0]['uid'] == native['uid']
        mapping = native['world_mapping']
        world_hit = None
        if mapping['world_identity_verified']:
            world_hit = bool(native_hit)
            if predicted_uid and predicted_uid != native['uid']:
                left, right = self.node(mapping['uid']), self.node(predicted_uid)
                safe = self.candidate_contract(predicted_uid, dataset=dataset)
                world_hit = bool(left and right and safe['world_answer_eligible'] and
                                 left['component_id'] == right['component_id'] and
                                 self._presentation_identity(mapping['uid'])['status'] == 'ACCEPTED')
                if world_hit:
                    # A checked full-range class/world crosswalk permits both
                    # exact metrics, without merging the native and world UIDs.
                    native_hit = True
        return {'status': 'EVALUATED', 'native_exact': bool(native_hit), 'world_exact': world_hit,
                'world_identity_applicable': mapping['world_identity_verified'],
                'world_mapping_status': mapping['effective_status'],
                'name_resolution_status': resolution['status'] if resolution else None,
                'native_exact_basis': 'VERIFIED_FULL_RANGE_WORLD_CROSSWALK' if world_hit else 'SOURCE_NATIVE_UID_OR_UNAMBIGUOUS_FULL_LABEL' if native_hit else None,
                'hierarchy_reward_enabled': False, 'hierarchy_reward': None,
                'evaluation_rules': RULE_VERSION, 'database_revision': self._revision,
                'native_scope': {'namespace': native['namespace'], 'source_version': native['source_version']}}

    def native_relations(self, dataset: str, class_id: str) -> dict:
        native = self.native_class(dataset, class_id)
        if not native:
            return {'status': 'NOT_FOUND'}
        uid = native['uid']
        edges = [dict(r) for r in self.con.execute('SELECT * FROM edges WHERE child_uid=? ORDER BY id', (uid,))]
        typed = [dict(r) for r in self.con.execute('SELECT * FROM entity_relations WHERE subject_uid=? ORDER BY id', (uid,))]
        return {'status': 'AVAILABLE', 'uid': uid, 'relation_view': self.relation_view,
                'source_relations': edges + typed, 'navigation': self.path_result(uid),
                'world_mapping': native['world_mapping'],
                'hierarchy_diagnostic': 'Separate task-policy diagnostic; category registration is not IS_A proof',
                'hierarchy_reward_enabled': False}

    def integrated_datasets(self) -> list[dict]:
        if 'integrated_dataset_versions' not in self._tables:
            return []
        return [json.loads(r[0]) for r in self.con.execute('SELECT payload FROM integrated_dataset_versions ORDER BY dataset,source_version')]

    def integrated_mapping(self, dataset: str, class_id: str, *, scope: str, source_version: str) -> dict | None:
        key = dataset + '@' + source_version + ':' + str(class_id) + ':' + scope
        row = self.con.execute("SELECT o.payload,r.disposition,r.reason FROM integrated_fg_objects o JOIN increment_reconciliation r ON r.kind=o.kind AND r.object_key=o.key WHERE o.kind='mappings' AND o.key=?", (key,)).fetchone()
        if not row:
            return None
        return {'source_mapping': json.loads(row['payload']), 'integration_disposition': row['disposition'],
                'integration_reason': row['reason'], 'database_revision': self._revision,
                'effective_world_mapping': self.world_mapping_status(dataset, str(class_id)) if scope == 'world' else None,
                'raw_increment_status_is_world_supervision_approval': False}

    def integrated_relations(self, uid: str, *, limit: int = 100) -> dict:
        if not 1 <= limit <= 1000:
            raise ValueError('Limit must be 1..1000')
        rows = list(self.con.execute("SELECT o.payload,r.disposition,r.reason FROM integrated_fg_objects o JOIN increment_reconciliation r ON r.kind=o.kind AND r.object_key=o.key WHERE o.kind='relations' AND json_extract(o.payload,'$.child_uid')=? ORDER BY o.key LIMIT ?", (uid, limit + 1)))
        return {'uid': uid, 'items': [{'source_relation': json.loads(r['payload']),
                'integration_disposition': r['disposition'], 'integration_reason': r['reason'],
                'strict_hierarchy_eligible': r['disposition'] == 'INTEGRATED_GROUNDED_RELATION' and json.loads(r['payload'])['relation'] == 'IS_A'}
                for r in rows[:limit]], 'has_more': len(rows) > limit,
                'database_revision': self._revision, 'source_claim_is_not_admission': True}
