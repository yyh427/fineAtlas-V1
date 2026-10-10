# Aircraft child checkpoint

Keep the completed nine-stage repaired parents and every frozen implementation
and input unchanged. This checkpoint adds new files only. It applies the sealed
literal-jet and primary-aircraft family adapters once each and recomputes the whole graph and every browse index.
It does not replay any earlier source or repair stage. The original
`structure_resume_parent` metadata remains intact; this layer records its
completed nine-stage parent revision in `structure_delta_resume_parent`.

Use two independent copies of the two completed parent databases. Each source
requires its actual complete integrity report, full-file SHA-256 and matching
build receipt. The two sources must have different build IDs and inodes. Never
copy a source that still has an active writer or SQLite sidecars. For example,
using the existing repaired artifacts as the sources:

```bash
python -B scripts/resume_literal_jet_repairs.py \
  --source /data/path/artifacts/resumed-regression-candidate/fineatlas.sqlite \
  --parent-build /data/path/reports/resumed-regression-candidate-build/build_complete.json \
  --peer-parent-build /data/path/reports/resumed-regression-reproduction-build/build_complete.json \
  --parent-integrity /data/path/reports/resumed-local-acceptance/primary-integrity.json \
  --peer-parent-integrity /data/path/reports/resumed-local-acceptance/reproduction-integrity.json \
  --baseline /data/path/formal-v1.10.1/fineatlas-primary.sqlite \
  --database /data/path/artifacts/literal-jet-candidate/fineatlas.sqlite \
  --inputs /data/path/inputs-aircraft-primary-final \
  --reports /data/path/reports/literal-jet-candidate-build \
  --browse-staging /data/path/artifacts/literal-jet-candidate/browse-staging.sqlite

python -B scripts/resume_literal_jet_repairs.py \
  --source /data/path/artifacts/resumed-regression-reproduction/fineatlas.sqlite \
  --parent-build /data/path/reports/resumed-regression-reproduction-build/build_complete.json \
  --peer-parent-build /data/path/reports/resumed-regression-candidate-build/build_complete.json \
  --parent-integrity /data/path/reports/resumed-local-acceptance/reproduction-integrity.json \
  --peer-parent-integrity /data/path/reports/resumed-local-acceptance/primary-integrity.json \
  --baseline /data/path/formal-v1.10.1/fineatlas-primary.sqlite \
  --database /data/path/artifacts/literal-jet-reproduction/fineatlas.sqlite \
  --inputs /data/path/inputs-aircraft-primary-final \
  --reports /data/path/reports/literal-jet-reproduction-build \
  --browse-staging /data/path/artifacts/literal-jet-reproduction/browse-staging.sqlite
```

Supply existing actual integrity paths; do not manufacture reports matching the
illustrative names. Before either command, the child database must already be an
independent byte-for-byte copy of its own source. Existing failed child reports
and databases must be investigated and retained before choosing new paths.

Use the configuration fields in `resumed_delivery_coordinator.md`, with the new
child database, reproduction, seven-stage build receipts, extended frozen inputs,
fresh output directories and an actual child-revision loss disposition ledger.
The additive coordinator is mandatory for all actions:

```bash
python -B scripts/coordinate_literal_jet_delivery.py local --config /data/path/literal-jet-delivery.json
python -B scripts/coordinate_literal_jet_delivery.py package --config /data/path/literal-jet-delivery.json
python -B scripts/coordinate_literal_jet_delivery.py public --config /data/path/literal-jet-delivery.json
python -B scripts/coordinate_literal_jet_delivery.py finalize --config /data/path/literal-jet-delivery.json
```

The old fourteen local jobs, four previous repair auditors, source preservation,
regression gate and exact original public evidence keys remain mandatory. Each
entry point additionally requires the actual completed seven-stage child receipts
and both local audits for each of the two new deltas. The public action performs the independent
literal-jet SQL audit against the freshly downloaded database and inputs, then
verifies every installed SDK source file against the frozen inventory in the
isolated public environment. Missing either new SDK module, a preflight report or a
nine-stage parent snapshot cannot qualify as a completed child.

The independent sixth-delta auditor is `audit_primary_aircraft_family_repairs.py`,
bound to `structure_primary_aircraft_family_repairs.json` and
`hierarchy_primary_aircraft_family_repairs.jsonl`. Its operation count and relation
census are derived from the actual frozen files, never a proposed queue count.
The explicit `primary_aircraft_family_repairs` stage runs after the independent
literal-jet stage and before the whole-graph/index rebuild. It cannot change the
literal-jet binding, original metadata or prior source-stage history. Official
world model-to-family direction does not confirm a dataset label's exact model
identity; the actual sixth auditor must keep those mappings unchanged.

Additional fifth evidence lives in `literal_jet_local_extension.json`,
`public/checks/literal_jet_public_extension.json` and
`literal_jet_finalized_extension.json`. The sixth evidence is kept separately in `primary_aircraft_local_extension.json`,
`public/checks/primary_aircraft_public_extension.json` and
`primary_aircraft_finalized_extension.json`. Its public extension binds the
unchanged original public proof, fifth public extension, complete installed SDK
proof and actual sixth auditor receipt. Neither delta can substitute for the
other. The original public proof and repair extension are retained separately. Finalization binds the actual revision,
downloaded database, all frozen input hashes, full operation census, applied
metadata, installed SDK inventory and unchanged original public proof.

For each stable copy, use `promote_literal_jet_with_regression_gate.py` with
`--literal-jet-delivery-config` pointing to the fully finalized candidate delivery
configuration and all original promotion/regression arguments. Its `--source`
and `--source-inputs` must identify that candidate exactly. The wrapper requires
actual public fifth- and sixth-delta evidence and both finalized extensions before delegating to the unchanged promotion
and regression wrappers. Repeat the additive local/package/public/finalize actions
for the stable artifacts. The stable configuration points `primary_build` and
`reproduction_build` to the stable build receipts, and `lineage_primary_build`
and `lineage_reproduction_build` to the two completed seven-stage candidate
receipts. No release upload or recommendation change is performed by these
scripts.
