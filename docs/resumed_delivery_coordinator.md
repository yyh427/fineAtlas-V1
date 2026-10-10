# Resumed candidate delivery

Freeze these additive delivery scripts before starting repaired builds. They
preserve the original construction and publication implementations. They do not
upload assets, change the recommendation or promote a GitHub release.

Keep the completed parent artifacts and their original integrity reports. For
each independently copied parent, the continuation command requires the actual
`--parent-integrity` report from the original local acceptance. The two sources
must have different completed parent build IDs and different file inodes. Existing
exact continuation commands are documented in the recovery notes; do not replay
the source stages or replace their receipts.

After both repaired builds finish, prepare a JSON configuration outside the
frozen source/input directory. All paths must identify the same completed build:

```json
{
  "delivery_root": "/data/path/delivery-repaired-candidate",
  "database": "/data/path/artifacts/repaired-candidate/fineatlas.sqlite",
  "reproduction": "/data/path/artifacts/repaired-reproduction/fineatlas.sqlite",
  "primary_build": "/data/path/reports/repaired-candidate-build/build_complete.json",
  "reproduction_build": "/data/path/reports/repaired-reproduction-build/build_complete.json",
  "inputs": "/data/path/inputs-resume",
  "baseline": "/data/path/formal-v1.10.1/fineatlas-primary.sqlite",
  "inventory": "/data/path/reports/baseline-domain-inventory.json",
  "reference": "/data/path/reports/baseline-full-source-row-digests.json",
  "legacy_reference": "/data/path/six_domain_hierarchy_review_20261009/all_pairs.csv",
  "legacy_baseline_matrix": "/data/path/reports/baseline-factor-matrix-v6",
  "legacy_dispositions": "/data/path/reports/repaired-candidate-loss-dispositions.json",
  "local_output": "/data/path/reports/repaired-local-acceptance",
  "licenses": "/data/path/artifacts/public-input-licenses",
  "public_base_url": "https://github.com/yyh427/fineAtlas-V1/releases/download/v1.11.0rc1"
}
```

Run the following stages with the frozen code and a matching build environment:

```bash
python -B scripts/coordinate_structure_delivery.py local --config /data/path/delivery.json
python -B scripts/coordinate_structure_delivery.py package --config /data/path/delivery.json
```

`local` requires distinct resumed parents, runs all original independent local
checks, audits actual repaired statements in both artifacts, and accounts for
every fixed-policy loss. Existing running/failed local acceptance is preserved
and must be investigated. The disposition file must be generated from the actual
repaired database and matrix; merely rebinding the previous candidate is invalid.

When the OEM adapter's declared `INPUT_NAME` exists in the frozen inputs, local
acceptance additionally runs `audit_oem_body_scope_repairs.py` against both actual
databases. Its receipts must bind the exact database path/revision, frozen
manifest hash, operation hash and complete operation census. A preflight-only
receipt, missing report or stale revision cannot satisfy this requirement.

`package` checks the accepted database byte hash, creates the data parts, verifies
every wheel module against the frozen SDK inventory, and roundtrips a complete
input/license archive. Assets are listed with SHA-256 and sizes in
`delivery_root/package/delivery_assets.json`. The list contains the wheel, input
archive, `review_data.json`, installed expectations and every data chunk. Add
`delivery_assets.json` itself to the reviewed GitHub upload list.

The main agent then uses the established release controller to create the exact
new prerelease tag at the reviewed code commit and upload these assets. Existing
releases and mismatching asset names are preserved. The release controller's
authentication remains local; its credentials never enter the package or logs.
Do not promote or mark the release latest at this stage.

Once every asset is public:

```bash
python -B scripts/coordinate_structure_delivery.py public --config /data/path/delivery.json
python -B scripts/coordinate_structure_delivery.py finalize --config /data/path/delivery.json
```

`public` creates a new output directory, freshly downloads the SDK, inputs,
manifest and expectations without authentication, installs the downloaded wheel
into a new virtual environment, and runs the verified installer for every data
chunk. It checks the actual downloaded database with the installed SDK for all
domains/four views, labels/pairs, six policy matrices, source contracts, living
coverage, complete training exports and real CLI commands. It also reruns the
independent repaired-statement audit and complete fixed-policy regression gate.
Unknown paths, symlinks, duplicate archive members, omitted inputs, changed hashes,
stale SDK files, partial/cached transfers and copied parent lineage block progress.

The original temporary public executor's task set is reused in the newly frozen
`run_structure_public_checks.py`. It adds the repaired-statement and regression
checks. The original evidence contract requires an exact set of evidence keys,
so the additional bound checks are retained separately in
`public/checks/resume_public_extension.json`; the base proof remains
`public/checks/public_verification.json`. `finalize` requires both before invoking
the unchanged acceptance finalizer.
The same optional frozen OEM input makes the actual public OEM audit mandatory;
its receipt is included as `oem-body-scope` in the extension evidence. Finalization
rechecks its revision, exact downloaded database, complete census and frozen
manifest/operation hashes. The original acceptance job and public evidence key
sets remain unchanged.

Additional source deltas use `structure_delivery_delta_registry.py` while the
validated OEM interface remains separate. The complete-subject scope adapter
declares `structure_complete_subject_scope_repairs.json`; its actual auditor is
`audit_complete_subject_scope_repairs.py`. When this frozen input exists, both
local databases and the downloaded public database must have complete independent
receipts under `complete-subject-scope`. Counts are derived from the actual frozen
operation JSONL, including each relation's exact census. Missing reports, a
changed revision, a preflight-only result, Boolean counts or a different relation
distribution prevent packaging/finalization. Future registered adapters use the
same binding contract without adding keys to the original public evidence set.

The Cars projection-view adapter registers `cars-projection-view`, with input
`structure_cars_projection_view_repairs.json` and actual auditor
`audit_cars_projection_view_repairs.py`. Its review operations retain the original
`CONFIGURATION_OF` relation for the exact operation census. Applied metadata under
`cars_projection_view_repairs` must also bind the complete manifest/operations and
count. Its independent auditor must distinguish unsupported world inclusion from
retained source-reference provenance, verify UID/history preservation, and check
that independently evidenced configuration connections remain. Label mapping
review alone cannot excuse an unsupported active relation in a typed view.

For stable artifact preparation, use `promote_structure_with_regression_gate.py`
with all original promotion arguments, all four legacy gate arguments, and the
two `--primary-build`/`--reproduction-build` resumed candidate receipts. The wrapper
rechecks distinct original parent build IDs/inodes and matches both resumed
revisions to the regression matrix before delegating. Prepare two stable copies,
then repeat full local/package/public acceptance for the stable artifacts.
The stable delivery config uses its new primary/reproduction build receipts and
additionally supplies `lineage_primary_build` and `lineage_reproduction_build`
pointing to the independently resumed candidate ancestors. Their revisions must
match the stable freeze's `promotion.parent_candidate_revision`.

Only after stable public re-verification and explicit review of remaining source
limitations should the main agent publish the stable GitHub release and update
the recommended record. `v1.10.1` remains recommended while any mandatory gate is
incomplete.

`CONFIGURATION_TYPE_OF` is a directional physical-type connection from a
configuration to a class. It is admitted in typed navigation and the opt-in
`configuration_types` policy; the original frozen `configuration` policy excludes
it. Restored source-object navigation, confirmed dataset/world identity, fine
distance recovery and source-native annotation coverage must be reported
separately. Adding this relation cannot promote an unconfirmed author label
mapping or substitute native projections for missing world-object paths.

Resumed local delivery invokes the additive `accept_resumed_structure_candidate.py`
entry point. Its source preservation job still hashes every original source row;
it permits only frozen, independently audited `nodes.visibility` migrations.
The public executor runs that same full raw audit on the freshly downloaded
artifact using the original formal row-digest reference. The extra receipt is
recorded as `resumed-source-preservation` in the public extension, leaving the
original public evidence keys unchanged. Finalization checks its complete table
hashes, actual revision, frozen inputs, precise visibility census and all nested
third/fourth actual audit receipts. A missing or partial source receipt blocks
finalization.
