# Structural candidate migration and comparison

The recommended formal release remains **v1.10.1** until the candidate's local,
regression, and public installation checks all complete. A completed build or
passing unit test suite alone does not change that recommendation.

## Compare the same labels and policies

Keep all 755 original labels and 56,917 unordered within-dataset pairs. The
formal release's `unified_reward_policies` are the fixed comparison policies.
Compare formal and candidate data with those policies before comparing new
task policies. The compatibility SDK must reproduce the formal SDK's original
pair statuses, distances, and common-ancestor UIDs exactly.

Every previously applicable pair that becomes inapplicable requires a bound
disposition: its first changed decision, affected endpoint or identity
component, source evidence, and a check for omitted legal connections. An
unexplained change or unresolved engineering omission blocks recommendation.
A missing source crosswalk remains uncertain; it is not evidence that the old
mapping was scientifically disproved.

## Keep identity and inclusion separate

Original source records, reviewed identities, dataset annotations, and mapping
history remain separate. A dataset author's variant/family relationship can
be established while the corresponding exact commercial identity remains
unconfirmed. An EPA reference configuration does not necessarily describe the
whole scope of a Cars annotation. A manufacturer's name or matching product
string alone is insufficient for identity equivalence.

Evidence can independently establish a directional model/family or physical
type relationship. Preserve such relationships after splitting identities.
Restoring a reviewed directional declaration must retain the old declaration
and its review history; it must not merge a model with a family to recover a
coverage statistic.

`target_scope='source_native'` selects the author's frozen annotation namespace
and version. It is a separate projection, not restoration of the old world's
exact identities or design distances. Ordinary shared types can provide valid
coarse structure. Inapplicable fine distances remain `null`, with reasons;
the original label remains available for class accuracy supervision.

## Resume without discarding verified source work

`scripts/resume_structure_repairs.py` takes an independently copied, completed
structural parent, its actual build receipt, and its independent whole-file
integrity report (`--parent-integrity`). It verifies every original
source input and executed implementation fingerprint. Only additive frozen
repair inputs and implementation files are admitted. Changed original inputs
require replay of their affected source stages instead of silent reuse.

The recipe applies the grounded repair delta, recomputes all graph views,
freezes a new revision, and rebuilds and embeds browser indexes. Use two
separately built parent artifacts, distinct output files, and a clean matching
environment for reproduction. Parent source stages retain their historical
fingerprints; they are not relabeled as newly executed stages.

Run the recipe once for each independently completed parent. Substitute actual
completed paths; never copy or read a database while its build is writing it:

```bash
python -B scripts/resume_structure_repairs.py \
  --source /run/artifacts/parent-primary/fineatlas.sqlite \
  --parent-build /run/reports/parent-primary/build_complete.json \
  --parent-integrity /run/reports/parent-acceptance/primary-integrity.json \
  --baseline /formal/v1.10.1/fineatlas-primary.sqlite \
  --database /run/artifacts/repair-primary/fineatlas.sqlite \
  --inputs /run/inputs-repair \
  --reports /run/reports/repair-primary \
  --browse-staging /run/artifacts/repair-primary/browse.sqlite
```

The reproduction command must instead use the independently built
`parent-reproduction` source, its build receipt, its `reproduction-integrity.json`,
and distinct repair output/report paths. Copy each source to its corresponding
output before invoking the recipe. Both copies are checked against the original
independent whole-file SHA-256 before mutation. A matching SQLite revision alone
does not establish unchanged source bytes.

Before acceptance and promotion,
`validate_resumed_parent_independence(primary_receipt, reproduction_receipt)`
must verify distinct original build IDs and source inodes, distinct resumed
build IDs, matching parent semantic revisions, and intact lineage receipts.
Two copies of the same completed parent do not qualify as independent builds.

The resulting `build_complete.json` still requires independent full-library
contracts, all labels and pairs, search/pagination/export checks, the fixed
policy regression gate, public download, and matching installed SDK checks.
Keep the old release and all previous candidate snapshots intact.
