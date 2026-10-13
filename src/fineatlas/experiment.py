"""Gold-blind experiment adapter. A returned handle is the only constrained choice.

This is a new interface/version, not a reinterpretation of historical V26 runs.
No model, image reader or training process is started by this module.
"""
from __future__ import annotations

import hashlib
import json
import copy
import re
from typing import Any
from .task_contract import RunConfig


class FineAtlasExperimentTool:
    def __init__(self, config: RunConfig | str):
        from .api import FineAtlas
        self.config = config if isinstance(config, RunConfig) else RunConfig.read(config)
        self.atlas = FineAtlas(self.config.database, relation_view=self.config.relation_view)
        try:
            self.config.validate(self.atlas)
        except Exception:
            self.atlas.close()
            raise
        self._choices: dict[str, dict[str, Any]] = {}
        self._result_choices: dict[str, tuple[str, ...]] = {}
        self._result_fingerprints: dict[str, str] = {}
        self._anchors: dict[str, str] = {}

    def close(self) -> None:
        self.atlas.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def query(self, text: str, *, domain: str | None = None, dataset: str | None = None, limit: int = 10) -> dict:
        """Accept model phrases only; gold IDs/labels/target UIDs are not inputs."""
        if self.config.inference_mode == 'closed' and dataset != self.config.closed_dataset:
            raise ValueError('Explicit closed mode must select its configured dataset')
        answer_scope = 'source_native' if self.config.inference_mode == 'closed' else 'world' if self.config.target_scope == 'world' else 'mixed'
        page = self.atlas.candidate_search(text, limit=limit, domain=domain, dataset=dataset,
                                          purpose='answers', answer_scope=answer_scope)
        nav_page = self.atlas.candidate_search(text, limit=limit, domain=domain, dataset=dataset,
                                              purpose='navigation', answer_scope=answer_scope)
        answers, navigation = [], []
        for item in page['items']:
            eligibility = item['answer_contract']
            if self.config.inference_mode == 'closed':
                eligibility['answer_eligible'] = eligibility['native_answer_eligible']
            handle = 'candidate-' + hashlib.sha256((self.config.database_revision + ':' + item['uid']).encode()).hexdigest()[:16]
            row = {**item, **eligibility, 'handle': handle}
            self._anchors[handle] = item['uid']
            (answers if eligibility['answer_eligible'] else navigation).append(row)
            if eligibility['answer_eligible']:
                self._choices[handle] = copy.deepcopy(row)
        for item in nav_page['items']:
            eligibility = item['answer_contract']
            handle = self._anchor_handle(item['uid'])
            navigation.append({**item, **eligibility, 'answer_eligible': False, 'handle': handle})
        result_id = hashlib.sha256(json.dumps([self.config.to_dict(), text, domain, dataset, limit,
                                               [r['handle'] for r in answers]], sort_keys=True).encode()).hexdigest()
        self._result_choices[result_id] = tuple(r['handle'] for r in answers)
        result = {'query': text, 'candidates': answers, 'navigation_candidates': navigation,
                'candidate_count': len(answers), 'inference_mode': self.config.inference_mode,
                'result_id': result_id, 'task_dataset_context': dataset,
                'run_config': self.config.to_dict(), 'retrieval_diagnostics': page['diagnostics'],
                'evaluation_rules': self.config.evaluation_rules}
        self._result_fingerprints[result_id] = self._constraint_fingerprint(result)
        return result

    def _anchor_handle(self, uid: str) -> str:
        handle = 'anchor-' + hashlib.sha256((self.config.database_revision + ':' + uid).encode()).hexdigest()[:16]
        self._anchors[handle] = uid
        return handle

    def entries(self) -> dict:
        """Initial public navigation choices, independent of any gold label."""
        navigation = []
        for domain in self.atlas.domains():
            navigation.append({'label': domain['label'], 'handle': self._anchor_handle(domain['uid']),
                'identity_scope': 'NAVIGATION', 'role': 'DOMAIN_ENTRY', 'object_granularity': None,
                'mapping_statuses': [], 'reason': 'DOMAIN_NAVIGATION_ENTRY', 'answer_eligible': False})
        return {'candidates': [], 'navigation_candidates': navigation, 'inference_mode': self.config.inference_mode}

    def scope(self, anchor_handles, *, dataset=None, target_granularity=None,
              limit=20, cursor=None, max_depth=16, node_budget=20000,
              edge_budget=100000, text=None, expand=False) -> dict:
        """Traverse only anchors the model actually received in this session."""
        from .scope import SCOPE_RULES
        if isinstance(anchor_handles, str):
            anchor_handles = [anchor_handles]
        if not anchor_handles or any(h not in self._anchors for h in anchor_handles):
            raise ValueError('Scope anchor was not issued to this model session')
        if self.config.inference_mode == 'closed' and dataset != self.config.closed_dataset:
            raise ValueError('Explicit closed mode must select its configured dataset')
        anchors = [self._anchors[h] for h in anchor_handles]
        options = dict(limit=limit, cursor=cursor, dataset=dataset,
            target_granularity=target_granularity, node_budget=node_budget,
            edge_budget=edge_budget, text=text, route_mode=self.config.scope_route_mode)
        page = (self.atlas.expand_scope(anchors[0], **options) if expand and len(anchors)==1 else
            self.atlas.scope_candidates(anchors, max_depth=1 if expand else max_depth,
                purpose='discovery' if expand else 'answers', **options))
        answers, navigation = [], []
        for item in page['items']:
            contract = item['answer_contract']
            eligible = (contract['native_answer_eligible'] if self.config.inference_mode == 'closed'
                        else contract['world_answer_eligible'] if self.config.target_scope == 'world'
                        else contract['answer_eligible'])
            handle = self._anchor_handle(item['uid'])
            row = {**item, **contract, 'answer_eligible': eligible, 'handle': handle}
            if eligible:
                self._choices[handle] = copy.deepcopy(row)
                answers.append(row)
            else:
                navigation.append(row)
        result_id = hashlib.sha256(json.dumps([self.config.to_dict(), anchor_handles, dataset,
            target_granularity, limit, cursor, max_depth, text, expand,
            [r['handle'] for r in answers]], sort_keys=True).encode()).hexdigest()
        result = {'candidates': answers, 'navigation_candidates': navigation,
            'candidate_count': len(answers), 'result_id': result_id,
            'inference_mode': self.config.inference_mode, 'task_dataset_context': dataset,
            'run_config': self.config.to_dict(), 'evaluation_rules': self.config.evaluation_rules,
            'retrieval_diagnostics': page['diagnostics'], 'has_more': page['has_more'],
            'next_cursor': page['next_cursor'], 'scope_rules': SCOPE_RULES}
        self._result_choices[result_id] = tuple(r['handle'] for r in answers)
        self._result_fingerprints[result_id] = self._constraint_fingerprint(result)
        return result

    @staticmethod
    def _constraint_fingerprint(result: dict) -> str:
        fields = ('handle', 'uid', 'label', 'answer_eligible', 'identity_scope', 'role')
        payload = [result['task_dataset_context'], result['inference_mode'],
                   [{**{key: row[key] for key in fields},
                     'object_granularity': row.get('object_granularity'),
                     'reachability': row.get('reachability'),
                     'name_index': row.get('name_index')} for row in result['candidates']]]
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def candidate_wire(result: dict) -> str:
        # Backend provenance includes UIDs; model feedback intentionally omits
        # source numeric class IDs, gold labels and dataset-wide class lists.
        rows = []
        for item in result['candidates']:
            statuses = ','.join(sorted({s['effective_status'] for s in item.get('mapping_statuses', [])})) or 'UNASSESSED_FOR_DATASET'
            grain = item.get('object_granularity') or 'UNKNOWN'
            route = item.get('reachability', {}).get('path', [])
            via = '; via=' + ' / '.join(e['relation'] + ':' + e['from_label'] for e in route) if route else ''
            names = [n for n in item.get('name_index', []) if not re.match(r'^\d+[._]', n)]
            aliases = '; names=' + ' | '.join(names[:20]) if names else ''
            rows.append(f"{item['label']} [choice={item['handle']}; source={item.get('source', 'UNKNOWN')}; scope={item['identity_scope']}; role={item['role']}; grain={grain}; world_mapping={statuses}{aliases}{via}]")
        for item in result['navigation_candidates']:
            statuses = ','.join(sorted({s['effective_status'] for s in item.get('mapping_statuses', [])})) or 'UNASSESSED_FOR_DATASET'
            grain = item.get('object_granularity') or 'UNKNOWN'
            rows.append(f"{item['label']} [navigation={item.get('handle', 'unissued')}; source={item.get('source', 'UNKNOWN')}; scope={item['identity_scope']}; role={item['role']}; grain={grain}; world_mapping={statuses}; reason={item['reason']}]")
        return '\n'.join(rows) or '(no candidates returned)'

    def allowed_choices(self, result: dict) -> tuple[str, ...]:
        """Generate constraints from eligible returned rows, never full vocabularies."""
        if result['run_config'] != self.config.to_dict():
            raise ValueError('Candidate result belongs to another rule configuration')
        expected = self._result_choices.get(result.get('result_id'))
        actual = tuple(row['handle'] for row in result['candidates'])
        if expected is None or actual != expected:
            raise ValueError('Candidate result is unissued or was modified')
        if self._result_fingerprints[result['result_id']] != self._constraint_fingerprint(result):
            raise ValueError('Candidate identity/eligibility context was modified')
        dataset = result['task_dataset_context']
        return tuple(row['handle'] for row in result['candidates']
                     if row['answer_eligible'] and self.atlas.candidate_contract(row['uid'], dataset=dataset)['answer_eligible'])

    def select(self, handle: str) -> dict:
        if handle not in self._choices:
            raise ValueError('Choice was not an eligible returned candidate')
        row = self._choices[handle]
        if not row['answer_eligible']:
            raise ValueError('Choice is not answer eligible under the shared rules')
        return dict(row)

    def evaluate(self, dataset: str, class_id: str, *, handle: str | None = None, label: str | None = None) -> dict:
        chosen = self.select(handle) if handle else None
        return self.atlas.evaluate_exact(dataset, class_id,
                                         predicted_uid=chosen['uid'] if chosen else None,
                                         predicted_label=label)
