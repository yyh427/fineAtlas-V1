# Native755 integrated candidate

This independent local candidate extends frozen v1.11.0rc1. It does not replace
v1.10.1, the original rc1 database, or historical V26 experimental code. No model
training or public release is part of this repair.

Use the exact database/SDK/code binding in the delivered `artifacts/run_config.json`.
The candidate validates the committed SDK file hashes, database revision and
relationship view before the experimental adapter can run. Accuracy experiments
use `source_native`, `reviewed_paths`, `unified`, open inference, and no hierarchy
reward. World identity and hierarchy applicability remain separate diagnostics.

From this checkout, use `PYTHONPATH=src` or install the delivered wheel into an
isolated environment. Backend category inspection is deliberately explicit:

```sh
PYTHONPATH=src python -m fineatlas --data-dir ../artifacts/fineatlas.sqlite --run-config ../artifacts/run_config.json native-class stanford_cars 38
PYTHONPATH=src python -m fineatlas --data-dir ../artifacts/fineatlas.sqlite --run-config ../artifacts/run_config.json native-resolve 'BMW Z4 Convertible 2012' --dataset stanford_cars
PYTHONPATH=src python -m fineatlas --data-dir ../artifacts/fineatlas.sqlite --run-config ../artifacts/run_config.json candidate-search 'European pipit' --domain bird --dataset cub200 --purpose answers --limit 10
```

`native-class`, `native-resolve` and original-label acceptance probes are private
data-management checks. Do not feed gold source IDs, true class labels or complete
dataset class lists into model inference. A task dataset context describes the
permitted answer unit; it is not a whitelist of that dataset's identities.

For an actual gold-blind query/constraint flow, create a JSONL query file with
`item_id`, `query` and optional `domain` / `task_dataset_context`. The adapter
rejects other fields. The evaluator must read ground truth in a separate process.

```sh
PYTHONPATH=src python scripts/experiment_native755.py --run-config ../artifacts/run_config.json --queries queries.jsonl --output model_feedback.jsonl --private-candidates private_candidates.jsonl
```

Only `model_feedback.jsonl` goes to the model. Its choices are opaque handles for
eligible returned candidates; navigation has no answer handle. Keep the private
candidate record out of the prompt. `FineAtlasExperimentTool.evaluate()` accepts
gold only in its private evaluation API, and uses the same candidate rules.

The default mode is open. An explicitly configured closed mode additionally
requires `inference_mode=closed` and a `closed_dataset`; never describe its recall
as cross-domain open retrieval. Namespace-qualified full-label resolution returns
ambiguity instead of guessing. Confirmed compatible source representations are
aggregated before truncation; source UID/provenance records remain intact.

Independent increment assertions are reconciled against current rc1 endpoints.
Frozen old closure is provenance, not an instruction to replace the current graph.
`integrated-datasets` and `integrated-relations` expose catalogue and isolated
source claims. NABirds mirror and VegFru publication-table IDs remain blocked for
numeric training supervision; this does not affect the original755 cohort.

Rollback is guarded by exact before/after row receipts in `repair_changes`.
Call `fineatlas.repair_candidate.rollback(path, package_id)` in reverse package
order, with no concurrent readers/writers; it refuses later unjournaled edits.
`verify_rollback_stack(path)` exercises reverse writes in one transaction and
rolls the transaction back, preserving the candidate. For operational fallback,
keep using the untouched v1.10.1 / rc1 database and its matching SDK/config.
Never point an old SDK at the new candidate and assume equivalent behavior.

The delivered reports contain original755 per-class acceptance, fixed-budget
query comparisons, fixed-denominator hierarchy diagnostics, source evidence,
isolations and subgraph consistency checks. They do not claim that the inherited
multi-million-node world graph is completely semantically verified.
