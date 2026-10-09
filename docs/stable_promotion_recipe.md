# Stable 1.10.1 promotion recipe

`python -B scripts/promote_stable_candidate.py` prepares a new stable artifact from a fully accepted candidate. It never publishes, merges, changes defaults, or edits its source. Two independent promotions must use the separately checked primary and reproduction candidates as their respective sources.

Reuse is limited to unchanged semantics. The script verifies the old embedded frozen manifest against every actual source input, the complete SDK file inventory and original build-script hashes. The new SDK must differ only in the literal `__version__` value; the new inputs may differ only in `review_release.json.version`. Added/removed SDK/input files, another input field, a semantic implementation change or an original recipe change causes rejection and requires a complete baseline rebuild. The accepted candidate's graph namespace/`unified_source_graph_revision`, typed contracts, policies, WordNet usage and source/identity records remain unchanged. Historical `usability_stages` input fingerprints remain historical records of the actual candidate build; they are not relabeled as stages executed with stable inputs. This script does not call `Migration.run`, which would legitimately invalidate those old input fingerprints.

The candidate's exact full SHA, byte size and revision must match its independent integrity proof. The completed comparison must bind both primary/reproduction exact SHAs and revisions, contain 105 logical tables and have a successful final view-statistics result and exit zero. The completed original public acceptance receipt must bind the compared primary and include all 16 named successful jobs. Reproduction inherits that acceptance only through the completed exact logical/schema comparison. The script verifies a new independent copy's full SHA and rejects hardlinks and existing destinations.

Only release/review-version, frozen-manifest and browser-readiness/revision metadata change before rebuilding indexes. The new manifest freezes all 62 input hashes, all 20 SDK hashes, the original 13 recipe hashes, this promotion script as the 14th recipe and `pyproject.toml`. It also records the original candidate's common semantic revision/frozen-manifest fingerprint. Different physical primary/reproduction SHAs appear only in each execution report; they do not make their new semantic revisions differ.

Browser indexes must be rebuilt. `browse_index.py` fingerprints the parent revision and four implementation files; the final revision also includes the release. Relabeling the old browser cache would give incorrect cache provenance. The recipe therefore creates a new browser staging artifact and uses the existing checked embedding CLI against the new exact parent revision. It leaves source/semantic records untouched. Expected browser reconstruction cost is approximately 15–16 minutes per independently promoted file, based on the previous full build; file verification/copy and final complete validation add separate measured costs.

Example, with absolute paths and real completed original receipts:

```sh
python -B scripts/promote_stable_candidate.py \
  --source OLD_RUN/fineatlas-primary.sqlite \
  --source-code OLD_RUN/code \
  --source-inputs OLD_RUN/inputs \
  --inputs NEW_RUN/inputs \
  --database NEW_RUN/fineatlas-primary.sqlite \
  --browse-staging NEW_RUN/fineatlas-primary-browse.sqlite \
  --reports NEW_RUN/reports/primary-promotion \
  --integrity OLD_RUN/reports/artifact_integrity_and_hashes.json \
  --comparison-completion OLD_RUN/reports/reproduction_comparison_complete.json \
  --acceptance OLD_RUN/reports/public-reverification/acceptance/acceptance_receipt.json
```

Use the old reproduction source with distinct new output/report paths for the second execution. The formal driver owns task launch and resource scheduling. Temporary files use the new output directory's `tmp` on `/data`.

`promotion_complete.json` means preparation is complete. It is not acceptance or publication. Both new candidates require independent full 105-table and all-schema-object comparison, integrity/full artifact hashes, explicit old→new source/semantic preservation, and the complete 16-job regression. The existing strict comparison script remains unchanged: it should compare the two stable promotions, whose metadata must agree exactly except its established runtime-statistics exception. Running it on old review versus stable correctly rejects the intentionally different release/frozen metadata; that difference is not a reason to add an ignore list. An old→new preservation report must enumerate the allowed metadata deltas while requiring raw/source/semantic rows and object schemas to remain exact.

The complete acceptance's repair-focus checker accepts additional recipe/packaging manifest keys: it checks every input and loaded SDK hash without assuming 13 recipe files. It does not itself verify `build_scripts` or packaging hashes. This promotion recipe verifies those at the beginning, immediately before metadata freeze and after browser construction. The release controller should also bind them in its frozen-build receipt and final unchanged-input/code check; the 16 successful jobs alone do not replace that separate recipe-freeze proof.

The full local frozen inputs and internal review/failure ledgers remain local. Public reproducibility claims must state that complete rebuilding requires those same frozen inputs; uploading a compact manifest is not uploading all input records.
