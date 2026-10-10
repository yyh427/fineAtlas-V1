# Fixed-policy regression acceptance

A full structural acceptance receipt does not explain losses relative to the
formal release. Before stable promotion, run `audit_legacy_pair_regressions.py`
against the original v1.10.1 SDK export, a current-SDK formal-data matrix, and the
completed candidate matrix. It independently reads all 755 labels and 56,917
pairs without importing SDK graph or build adjudication functions.

The original and compatible formal-data exports must agree on every status,
distance and LCA UID. The report separates losses, gains, valid pairs with changed
source paths/LCA/distance, unchanged valid pairs and pairs invalid in both builds.
Every loss must have exactly one external disposition. The manifest is bound to
the candidate revision, both CSV SHA-256 hashes and the frozen old policy hash.
Endpoint UIDs and the first failed stage are checked against actual label and
pair records. Hashes bind all source, mapping, parent-chain and legal-connection
review files. A missing pair, stale evidence, an uncorrected engineering omission,
or a mismatch with the formal SDK blocks the gate.

Disposition manifests use schema
`FINEATLAS_LEGACY_PAIR_REGRESSION_DISPOSITIONS_V1`, with top-level
`candidate_revision`, `baseline_matrix_sha256`, `candidate_matrix_sha256`,
`policy_sha256`, and `groups`. Each group contains:

- `id`, `category` (the eight cause categories in the recovery contract),
  `disposition`, `first_changed_stage`, `decision_reason`, and explicit
  `pairs: [[dataset, left, right], ...]`.
- `labels`, containing the affected endpoints' `dataset`, `class_id`, `old_uid`,
  `new_uid`, `old_role`, `new_role`, `mapping`, `parent_chain`, `decision_reason`,
  and `source_evidence`.
- `legal_connection_check: {status, evidence}` and group-level `evidence`.
  Every evidence item has `path` and `sha256`; relative paths resolve against the
  disposition manifest directory.

Accepted dispositions are `WITHDRAWAL_JUSTIFIED` and category 7
`PENDING_SOURCE_EVIDENCE`. A pending identity assertion remains a limitation;
passing the accounting gate does not confirm that identity or restore its
distance. Categories 2 through 6 describe repairable losses and cannot pass while
present among lost pairs. Legal connection checks must say `NO_LEGAL_CONNECTION_LOSS`
or `FIXED` and supply independently reviewable evidence. The auditor verifies
bindings and coverage; source truth still requires the cited independent review.

Use `promote_structure_with_regression_gate.py` with every original
`promote_structure_stable.py` argument and the required `--legacy-reference`,
`--legacy-baseline-matrix`, `--legacy-candidate-matrix`, and
`--legacy-dispositions`. It reruns the gate and matches its candidate revision to
the accepted database and frozen policy before invoking the unmodified promotion
implementation. Its public verification and independent-build requirements
remain mandatory. The additive wrapper preserves all parent recipe hashes during
checkpoint continuation. A candidate or policy
change requires fresh matrices and fresh adjudication; rebinding an old report
without checking the actual candidate is insufficient.
