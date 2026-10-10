# Aircraft child checkpoint

Keep the completed nine-stage repaired parents and every frozen implementation
and input unchanged. This checkpoint adds new files only. It applies the sealed
literal-jet, primary-aircraft family and owned-scope adapters once each and recomputes the whole graph and every browse index.
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
child database, reproduction, eight-stage build receipts, extended frozen inputs,
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
entry point additionally requires the actual completed eight-stage child receipts
and both local audits for each of the three new deltas. The public action performs the independent
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
actual public fifth- and sixth- and seventh-delta evidence and all three finalized extensions before delegating to the unchanged promotion
and regression wrappers. Repeat the additive local/package/public/finalize actions
for the stable artifacts. The stable configuration points `primary_build` and
`reproduction_build` to the stable build receipts, and `lineage_primary_build`
and `lineage_reproduction_build` to the two completed eight-stage candidate
receipts. No release upload or recommendation change is performed by these
scripts.


The independent seventh `owned_scope_repairs` stage follows primary-aircraft
family repair. It binds `structure_owned_scope_repairs.json` and
`hierarchy_owned_scope_repairs.jsonl`, with actual audit
`audit_owned_scope_repairs.py`. Its complete operation census includes grounded
links, exact bridge reviews and exact typed-relation reviews. Preserve relation
names, source records, UIDs and all old claim/history evidence. Repartitioning an
identity component is a derived repair, not a new source assertion or a dataset
identity promotion. Prior metadata and stage receipts remain historical records;
the full graph and browse rebuild follows these source edits.

Its actual double-local, public and finalized evidence is retained separately as
`owned_scope_local_extension.json`, `public/checks/owned_scope_public_extension.json`
and `owned_scope_finalized_extension.json`. The public extension binds the sixth
extension, actual downloaded database revision/byte hash, complete installed SDK
inventory, frozen inputs and exact dynamic seventh operation census. All actions
and stable preparation require all three independent new deltas. Neither a
review operation nor a non-navigation source derivation reference may be counted
as restored hierarchy coverage. Reports must distinguish lawful new connections,
evidenced withdrawals, derived identity migration and still-pending dataset scope.
# Portable primary source verification

The final inputs must include `structure_primary_source_snapshots.json`; its
hash is bound by the actual final database freeze. Its document IDs, official
HTTPS URIs and body hashes must exactly match the unchanged sixth-delta facts.
Full manufacturer PDF/HTML bytes are not added to the release input archive
without an explicit redistribution permission.

Set the delivery config `primary_snapshots_directory` to the explicit existing
verified local source directory. Both local database audits use that directory,
and acceptance rehashes all external files and binds every source-owned SQL
payload document. The auditor never reads the historical absolute locator.

The public action retrieves each registry document once into the new
`delivery_root/public/source-snapshots` directory and records the actual HTTPS
response URI, MIME, byte count, timestamp and full SHA256. It passes this explicit
directory to the actual public SQL auditor. Reuse is allowed only with a complete
valid retrieval receipt and unchanged actual files. A source permission failure,
changed official response or incomplete prior attempt preserves a failure receipt
and blocks publication; it does not substitute local bytes or overwrite failures.

`primary_aircraft_public_extension.json` binds this retrieval receipt alongside
the independent actual database audit. Finalize and the stable promotion wrapper
recheck this evidence through the same mandatory public validation chain.

The final inputs also include `structure_regression_temporal_parent_reference.json`.
This records the unchanged original SQL audit's actual PASS on the completed
four-delta parent, its exact report text/hash, original code/input hashes and
completed parent receipt. The final regression auditor checks every original
source witness and relation again. Only exact frozen seventh-delta before/after
rows plus actual later history and the independent owned-scope audit permit a
subsequent assertion withdrawal or mapping migration. All unaffected requirements
remain intact; no old audit report is fabricated for the final database.

The new public executor retains every original job and public evidence key. Its
regression job calls this additive temporal auditor. Local package and public
delivery require both actual final local temporal reports, and public finalize
requires the real downloaded-database temporal report and its nested actual
seventh-delta evidence.

The same exact transition rule applies to the third complete-subject stage.
`audit_temporal_complete_subject_scope_repairs.py` checks every original source
record, role, witness, relation proof, preserved prior claim and activation.
Current ACTIVE counts subtract only exact frozen later withdrawals whose raw row
and review history match. The parent reference includes the original third SQL
audit's actual PASS on revision 3445, original source hashes and complete census.
Both local databases and the fresh public database require this temporal report;
the raw preservation compatibility audit calls the same real SQL auditor before
permitting the previously frozen 170 visibility changes.



The delivery config must also set `formal_baseline_verification_record` to the
retained v1.10.1 public prerequisite record. Packaging copies that record and its
five hash-bound historical public proofs into a separate regression support
archive. This records historical verification; it does not claim a fresh formal
download during this candidate turn.

The support archive contains the original disposition ledger bytes, the formal
pair reference, baseline pair and label snapshots, source-row digests, domain
inventory, and every hash-bound ledger evidence file. Historical absolute
locators remain unchanged in the ledger and act only as registry keys. The public
auditor never opens those historical paths. Whole external manufacturer PDFs or
HTML documents require explicit source retrieval or redistribution authorization;
packaging rejects them as implicit support members.

`package` adds `regression_support_manifest.json` and the named
`fineatlas-<release>-regression-support.tar.zst` to `delivery_assets.json`. Upload
these assets together with the SDK, inputs, and data. `public` downloads both
assets over unauthenticated HTTPS into the new public directory, validates their
SHA and size, safely extracts only declared regular files, and invokes
`audit_portable_legacy_pair_regressions.py`. The manifest, original ledger hash,
actual final candidate matrix, and policy must agree. Finalize and stable
preparation reject missing fresh transfer receipts or a host-file fallback.

The same explicit `primary_snapshots_directory` is passed to local first/third
temporal audits, the owned-scope auditor, and source preservation. Public retrieval
first obtains the eight sixth-delta documents, then retrieves only the additional
seventh-delta documents from `structure_owned_source_snapshots.json` into
`public/source-snapshots`. Shared documents retain their first fresh retrieval
receipt and bytes. Both registries, all required source byte hashes, the full nine
author annotation files, and all 10,000 annotations are checked. A failed request
or changed source response is preserved and blocks continuation; no absolute
agent-path fallback is available.

For a clean external environment, obtain the formal baseline from the official
[v1.10.1 release](https://github.com/yyh427/fineAtlas-V1/releases/tag/v1.10.1).
Use its `scripts/download_single.py --output-dir ./formal-data`, then verify
`fineatlas.sqlite` against SHA-256
`804192429ffda283da6b509d344778c3ebebbe4f34e59db82c32ea23e9957bc5` and
size `68495904768` bytes before supplying its explicit path as `baseline` in the
delivery config. The verified formal revision is
`1325af79323e77270650075f01bf22d34bbf2f9a072f22cdc651019e615f5b77`.
An existing read-only copy with the retained complete public verification may be
reused. Candidate data, SDK, frozen inputs, runtime support, and official source
snapshots still require their own actual fresh public transfers.


Set `primary_parent_integrity` and `reproduction_parent_integrity` to the two
complete, independently verified parent integrity receipts used by the child
recipe. Packaging calls the unchanged physical parent-independence validator
against the real two closed parent databases. It retains the original child
completion, lineage, stage/fingerprint files and complete parent byte-hash seals
in the runtime support archive. It also independently reads every original
quarantined claim and historical sibling from the completed parent, retaining
full-row hashes and exact status/reason states without redistributing source
document text.

The standalone public executor verifies these freshly downloaded historical
bytes with `portable_structure_lineage.py`. Its receipt explicitly states
`physical_parent_inodes_rechecked_here=false`: recorded build IDs, distinct
source inodes, source whole-file SHA and the original actual physical audit are
historical build evidence. A clean public machine performs the full current SDK,
SQL, API, CLI, export and source-byte audits on its downloaded final database;
it does not pretend to recreate the old physical inode values. Normal local
coordinator and build entry points continue to call the original physical
independence validator.
