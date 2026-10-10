# Scope and training migration for the resumed candidate

The recommended formal release remains **v1.10.1** until the resumed candidate
passes actual-data, independent interface, public-download and publication gates.
The completed four-delta checkpoint is an intermediate parent, not the final
v1.11.0rc1 artifact. Final statistics must identify a single database revision,
frozen input inventory, SDK inventory and task policy.

## Identity and relationship changes

Retain source objects, adjudicated identities, dataset labels and label mappings
separately. A native visual variant can describe a nominal aircraft design while
including several customer configurations. It does not establish equality between
a configuration-directory row and the complete design. Same-name objects with
different scopes retain distinct UIDs; prior mappings and source claims remain
available through change history.

`NATIVE_DESIGN_PARENT` records a reviewed model/family direction. Physical kinds
use `DESIGN_TYPE_OF` or `CONFIGURATION_TYPE_OF` with source-supported whole scopes.
An official "based on" statement can instead be a
`SOURCE_DESIGN_DERIVATION_REFERENCE`: it is retained as evidence with
`SOURCE_DECLARED` status and is excluded from navigation and distance calculation.
This avoids inheriting a passenger-only type from a passenger design into a
freighter derivative.

WordNet links require the correct sense and complete scope. A source's broad
car concept cannot be equated with a four-wheel-only WordNet sense when the
source includes three-wheel automobiles. Unsupported identity or type claims
retain their original content and review history. A broader physical parent is
added only when independently supported; root reachability alone is insufficient.

A source description of an automotive design can support a broad motor-vehicle
type without establishing a four-wheel body or passenger-only purpose. Preserve
those narrower claims as separate evidence decisions. Likewise, an aircraft
family with military or corporate derivatives can retain a physical aircraft,
jet or wing-geometry type while a whole-family commercial-airliner type is reviewed.
Neither connection certifies a dataset label's precise world identity.

Correct a source object's canonical role when the complete source identifies a
named physical member of a design. `INSTANCE_OF` then preserves its physical
classification without treating it as the complete `MODEL` or `MODEL_FAMILY`.
Keep the original role evidence and exact before/after normalization history.
An unprofiled source representation's default role also requires review when an
active identity peer has a different evidenced role; a shared label alone cannot
resolve that conflict.

## Select and retain an explicit task policy

Use the frozen policy files distributed with the artifact. Keep the formal
release's `legacy_policies.json` unchanged for data-regression comparisons.
Policies for reviewed paths and resolution are separate experimental conditions.
Source-native annotation routes describe the author's hierarchy and do not
certify precise commercial identity or recover the old world-object distance.

```python
import json
from pathlib import Path
from fineatlas import FineAtlas

dataset = "fgvc_aircraft"
policies = json.loads(
    Path("frozen/inputs/reviewed_resolution_policies.json").read_text()
)
scope = "source_native"  # Choose "world" for adjudicated world-design mappings.
config = policies[dataset]
if scope == "source_native":
    config = config["source_native"]
options = {key: value for key, value in config.items() if key in {
    "policy", "requirement", "source_scope", "coarse_roots",
    "coarse_lca_roles", "task_boundary_roots",
}}

with FineAtlas("fineatlas.sqlite", relation_view="unified") as atlas:
    index = atlas.relation_reward_index(
        dataset, admission_mode="reviewed_paths", target_scope=scope, **options
    )
    left, right = list(index.labels)[:2]
    result = index.query(left, right)
    print(result["status"], result["distance"])
    atlas.export_training(
        dataset, "training-export", admission_mode="reviewed_paths",
        target_scope=scope, **options
    )
```

An invalid or coarse-only distance stays `null`; inspect the returned status
and endpoint reason. Exports retain category labels and their classification
reward independently of the hierarchy mask. Root navigation, task-boundary
reachability, world identity and fine relation resolution are separate checks.
An applicable graph distance is not a calibrated measure of visual similarity.

For CRJ-700, report native variant/family verification, commercial identity
review and availability under each selected task independently. For Flowers,
keep species tasks separate from mixed-grain annotation tasks. For biological
datasets, retain the taxonomy version and distinguish breed-organization groups
from biological parentage.

## Release evidence

Publish the final six-dataset A/B/C/D comparison, complete first-stage pair-loss
ledger, affected scope withdrawals, domain and living-adapter results, code/data
hashes and fresh public-download verification with the completed artifact.
Intermediate checkpoint numbers and unit-test counts do not replace those gates.
