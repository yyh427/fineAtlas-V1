"""Gold-blind experiment adapter. A returned handle is the only constrained choice.

This is a new interface/version, not a reinterpretation of historical V26 runs.
No model, image reader or training process is started by this module.
"""
from __future__ import annotations

import hashlib
import json
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
            (answers if eligibility['answer_eligible'] else navigation).append(row)
            if eligibility['answer_eligible']:
                self._choices[handle] = row
        for item in nav_page['items']:
            eligibility = item['answer_contract']
            navigation.append({**item, **eligibility, 'answer_eligible': False})
        result_id = hashlib.sha256(json.dumps([self.config.to_dict(), text, domain, dataset, limit,
                                               [r['handle'] for r in answers]], sort_keys=True).encode()).hexdigest()
        self._result_choices[result_id] = tuple(r['handle'] for r in answers)
        return {'query': text, 'candidates': answers, 'navigation_candidates': navigation,
                'candidate_count': len(answers), 'inference_mode': self.config.inference_mode,
                'result_id': result_id, 'task_dataset_context': dataset,
                'run_config': self.config.to_dict(), 'retrieval_diagnostics': page['diagnostics'],
                'evaluation_rules': self.config.evaluation_rules}

    @staticmethod
    def candidate_wire(result: dict) -> str:
        # Backend provenance includes UIDs; model feedback intentionally omits
        # source numeric class IDs, gold labels and dataset-wide class lists.
        rows = []
        for item in result['candidates']:
            statuses = ','.join(sorted({s['effective_status'] for s in item.get('mapping_statuses', [])})) or 'UNASSESSED_FOR_DATASET'
            grain = item.get('object_granularity') or 'UNKNOWN'
            rows.append(f"{item['label']} [choice={item['handle']}; scope={item['identity_scope']}; role={item['role']}; grain={grain}; world_mapping={statuses}]")
        for item in result['navigation_candidates']:
            statuses = ','.join(sorted({s['effective_status'] for s in item.get('mapping_statuses', [])})) or 'UNASSESSED_FOR_DATASET'
            grain = item.get('object_granularity') or 'UNKNOWN'
            rows.append(f"{item['label']} [navigation; scope={item['identity_scope']}; role={item['role']}; grain={grain}; world_mapping={statuses}; reason={item['reason']}]")
        return '\n'.join(rows) or '(no candidates returned)'

    def allowed_choices(self, result: dict) -> tuple[str, ...]:
        """Generate constraints from eligible returned rows, never full vocabularies."""
        if result['run_config'] != self.config.to_dict():
            raise ValueError('Candidate result belongs to another rule configuration')
        expected = self._result_choices.get(result.get('result_id'))
        actual = tuple(row['handle'] for row in result['candidates'])
        if expected is None or actual != expected:
            raise ValueError('Candidate result is unissued or was modified')
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
