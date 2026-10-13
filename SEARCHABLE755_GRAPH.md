# Source classes in searchable typed ranges

This isolated candidate continues commit f198381582283de8ab658d20dd55be6a90f725ed.
It adds indexed mixed-relation traversal, source-scoped object ranges, source
WordNet3.0 types and evidence-bound connections. It does not select production,
release or training defaults. Historical interfaces and artifacts stay separate.

## Public model interface

Use the delivered SDK and run_config.json together:

```python
from fineatlas.experiment import FineAtlasExperimentTool

with FineAtlasExperimentTool('/path/to/run_config.json') as tool:
    entries = tool.entries()
    # The model chooses an issued navigation handle, or queries its own phrase.
    response = tool.query('BMW', dataset='stanford_cars', limit=20)
    print(tool.candidate_wire(response))
    # selected_handle must come from this session's response, never evaluation.
    selected_handle = response['navigation_candidates'][0]['handle']
    scope = tool.scope(selected_handle, dataset='stanford_cars', limit=20)
    print(tool.candidate_wire(scope))
    allowed = tool.allowed_choices(scope)
```

The example first row is illustrative. A model must select the appropriate
returned handle itself; the adapter does not supply the known correct parent.
Use `expand=True` for a single navigation step and `cursor` for deterministic
paging of the same range. `experiment_scope755.py` accepts session-bound JSONL
actions `entries`, `query`, `expand`, and `scope`, and writes public feedback
separately from private UID/path records. Gold IDs are rejected as request keys.
Ground truth belongs solely to the private evaluator after candidate selection.

Default open mode returns eligible world objects and source annotation units
found in the graph range; it does not enumerate a dataset as a whitelist.
An explicit target grain limits the declared unit. For heterogeneous tasks use
the original source annotation unit rather than pretending all nodes are species,
breeds or exact configurations. `source_category` is an explicit backend source
unit selector; the structural755 acceptance uses it and is not model recall.
Supported source aliases include `variant`/`visual_variant`, `breed` for declared
source breeds, `species` for declared wild-species labels, and
`annotation_combination` for the author car combinations. World REVIEW never
removes an independently declared source unit. Raw absent/conflicting ranks are
preserved; effective peer ranks require connected, compatible accepted identity.

## Typed paths and bounds

`FineAtlas.scope_candidates(anchors, ...)` is the reusable backend primitive.
Its classification edges use the selected relation_view. Mixed mode additionally
uses active, endpoint-role-valid design, series, configuration and source type
references. `DEPICTS_DESIGN` joins an annotation category to MODEL/MODEL_FAMILY;
`DEPICTS_TYPE` retains CLASS/BIOLOGICAL_VARIANT parents. `SOURCE_TYPE_REFERENCE`
retains the source dictionary sense to canonical broad type reference without
creating a strict refinement or changing world identity.

Each candidate carries `reachability.path`, edge types, source, evidence,
identity transfer proofs, raw representations and name_index. `strict_descendant`
is true only for an all-IS_A path. Source references are returned explicitly.
World/source and conflicting components are not collapsed by label similarity.
Equivalent representations and multiple paths aggregate before final paging.

The declared maximum depth defines the requested range. Node/edge work bounds
have explicit incomplete diagnostics, independent of result pagination. An empty
partial query is not proof of disconnection. Direct expansion prioritizes
navigation rows and then names; deeper candidates retain depth/UID order. This
new navigation ranking is not a visual-accuracy improvement. Search ranking is
separately reported with the same original755 names and budgets10/80.

## Source semantics

Cars make and design-label nodes denote the objects covered by source labels
sharing those literal predicates. They are not manufacturers as organizations,
nor asserted OEM generations or trims. Body/year are HAS_ATTRIBUTE facts, not
IS_A. The road-vehicle entrance includes the publisher's pickup/van scope.
Aircraft manufacturer type scopes use unanimous image-level author triples;
family/model/variant are not equated by matching strings. Dogs original synset
IDs use verified WordNet3.0 bytes, with explicit type paths for domestic breeds
and wild canids. Existing confirmed world types gain canonical parent pointers
only after full parent gloss and complete WordNet lemma-set matches across
versions. Those are lexical type relations, not evolutionary or kennel history.

## Reconstruction, validation and rollback

Prepared source_graph_plan.json and exact existing endpoint operation files are
immutable evidence packages. Journaled packages have guarded before/after rows.
Run build_searchable755_graph.py, finalize_searchable755_scope.py,
prepare_primary_navigation755.py, record_identity_investigations755.py and
connect_confirmed_dog_types755.py with the independent root. Existing package IDs
cannot be reused with different inputs. Source alignment operations are recorded
separately to distinguish the cross-version reference from strict inclusion.

The acceptance scripts produce per-class complete paths, actual expansion,
dynamic candidate probes and exact evaluation; these do not measure image-based
anchor selection. Fixed56917 pairs retain their old endpoint/admission rules.
Source navigation diagnostic scopes do not automatically become hierarchy rewards.
The delivered configuration disables hierarchy rewards.

To return to the previous delivery, use its original SDK/config/database. To
undo this round inside a disposable copy, roll back journal packages in reverse
order, stopping at revision fb63d9dfbbeba5a9d59289d147e65310cc5003b47b0b23c33d18a83793c2fa7f,
then use the matching previous SDK and update only its explicit database path.
Never run rollback on production or a database in use by another task. The
round rollback validator performs inverse writes in a transaction and discards
them; it checks logical restoration, not byte-identical file recovery.

Domain expansion first returns the registered classification roots as navigation
choices (`DOMAIN_ENTRY_ROOT`). This is a configured entrance relation, not an
IS_A claim and not world identity proof. Continue expanding an issued root
handle to inspect its real graph children. Scope ranges on a domain remain the
explicit union of registered roots; bounded scans report incomplete ranges.
Navigation feedback includes source provenance so same-name, unconfirmed
representations can be distinguished. The acceptance fixture selects up to four
issued type alternatives; it does not assume source-scoped fields are world
identities or use gold classes to choose anchors.
