# Public query contract

The SDK is read-only. Open `FineAtlas(path, view="wordnet", relation_view="strict", root=None, language="en")`. `root=None` selects the stored WordNet entity root. A custom root must be a real native node UID, not a navigation portal. `view="all"` exposes retained source records for inspection; visibility does not grant hierarchy admission. Large custom-root scopes have an explicit work bound.

## Views and roles

Strict classification uses ACTIVE IS_A only. Taxonomy additionally permits admitted TAXONOMIC_PARENT and NATIVE_CLASSIFICATION_PARENT; membership is the separate REUSABLE_TYPE_MEMBERSHIP graph, not the union of the other views. Compatible INSTANCE_OF, DESIGN_TYPE_OF, CONFIGURATION_OF, CONFIGURATION_TYPE_OF, SERIES_MEMBER_OF, REGULATED_AS, ATTRIBUTE_KIND_OF and DEPICTS_TYPE connections are preserved as typed steps. REGULATED_AS is regulatory navigation, not physical subtype identity.

CLASS is a reusable category. MODEL is a named product design. MODEL_FAMILY is a named series/family; CONFIGURATION is an orderable part, SKU, sized variant or year configuration. INSTANCE is a concrete named/serialized object. Biological variants and task categories have distinct roles. None of these roles are automatically interchangeable.

Native source UID, label, rank, role, domain and raw payload are retained. Display names prefer the requested language, then English, multilingual scientific names and undetermined language. Missing reliable names fall back to the UID and set `label_fallback`. `normalized_rank` uses explicit native grades and unambiguous accepted identity peers; conflicting grades remain CONFLICT_REVIEW. A source-declared grade is metadata, not independent scientific certification.

## Queries

- `node(uid)`, `identity(uid)`, `aliases(uid, limit=100, language=None)` expose identifiers, roles, source/name evidence and accepted identity links. `node.aliases_truncated` marks its bounded alias summary.
- `domains(include_aliases=False)`, `domain(name)`, `domain_roots(name)` inspect scopes. Legacy names and portal UIDs resolve to the canonical entry; native root aliases are added only when unambiguous.
- `search(query, limit=20, domain=None, node_kind=None)` and `exact(label, ...)` return all matching independent source identities within the bound. `PRODUCT_DESIGN` includes MODEL and MODEL_FAMILY; `SERIES` maps to MODEL_FAMILY. Equal labels do not cause identity merging.
- `browse_domain(name, limit=20)` returns separate roots, children and a page of instances. `domain_children(name, limit=20)` returns classification children, not a counterfeit instance list.
- `search_page(query, limit=20, cursor=None, domain=None, node_kind=None)`, `domain_page(name, limit=20, cursor=None, node_kind=None)`, `domain_instances(name, limit=20, cursor=None)`, `instances_page(type_uid, limit=20, cursor=None, recursive=True)` return `{items, next_cursor, has_more, ...}`. Sorting is stable by source UID. Cursors bind the revision, SDK contract, visibility, view, root and selector. Follow `next_cursor` until null; do not switch conditions mid-pagination.
- `neighbors(uid, direction="children", limit=20)` and `instances(uid_or_domain, limit=20, recursive=True)` keep compatible legacy list behaviour. ResultList exposes `truncated` and `has_more`; the CLI warns on stderr.

Canonical scope selectors compute descendants under the declared relations and typed roles. An object may appear in multiple legitimate scopes. `source:<tag>` filters original domain tags instead. An unknown scope raises ValueError; it never falls back to global search.

With an explicit custom root and `view="wordnet"`, search, domain pages, child browsing, instance pages and domain exports intersect the domain/type selector with that root's admitted descendants. `view="all"` retains source inspection behaviour. Native domain roots describe the domain's source scope; they are not replaced by the custom root.

## Paths, reachability and failures

`path_result(uid, anchors=None, max_depth=256)` distinguishes ROOT, CONNECTED, UNREACHABLE, NOT_FOUND, NOT_ADMITTED, VIEW_NOT_APPLICABLE, NAVIGATION_ONLY and DEPTH_LIMIT. `path()` retains the old list return, with an empty list for legitimate non-path outcomes; use `path_result()` for the reason. Portal calls return NAVIGATION_ONLY with native `root_uids`. Unknown anchor/root identifiers raise ValueError. Corrupt identity witnesses raise RuntimeError; query bounds raise QueryLimitError. Errors are not converted into empty success results.

Each step retains its real edge relation, endpoints, evidence/source and identity alignment. A displayed SAME_CONCEPT alignment is zero distance and does not invent taxonomy depth. The global precomputed path is a deterministic shortest admitted witness, not a claim that a DAG has one parent.

`connection_status()` uses the same root/view as `path_result()`. It separately reports view admission, `strict_classification_root_reachable`, `class_root_reachable_in_view`, `native_navigation_root_reachable`, `typed_root_reachable` and mixed `root_reachable`. Legacy `wordnet_reachable` retains global strict classification meaning even when the selected view changes.

`ancestors(uid, limit=1000, include_self=False, max_nodes=100000)` returns shortest upward distances by identity group. `lca(a, b, max_nodes=100000)` returns every common ancestor without a more specific common descendant, with separate distances to both inputs. `distance(a, b, direction="undirected", max_nodes=100000)` uses the selected hierarchy and compatible typed connections, with directed upward/downward alternatives. It returns UNREACHABLE with null distance for disconnected inputs. Identity links cost zero; hierarchy/type edges cost one. Pagination cannot silently make a graph calculation complete: bounds and truncation are explicit.

## Training selection and exports

`eligibility(uid, requirement="hierarchy", identity_verified=None)` checks the actual source record role, admission and root requirements. `None` means an external label mapping has not been asserted or assessed; it does not assert that mapping is verified. `target(dataset, class_id)` exposes both exact identity and broader typed mapping status. `task_labels(dataset, requirement="hierarchy", usable_only=False)` supplies mapping status explicitly.

Requirements: `native_label` retains native dataset identity without asserting hierarchy mapping; `identity` requires the verified exact mapping; `hierarchy` requires verified identity or typed mapping and a root path in the selected view; `strict_classification` additionally requires a pure strict IS_A path; `species`, `model`, `model_design`, `configuration`, `instance` require their declared terminal role/grade and a compatible root path. A genus-level task category connected by DEPICTS_TYPE can be hierarchy-usable while failing exact identity/species requirements. Year/trim identity boundaries remain separate from broad configuration-to-design membership evidence.

`export_domain(name, path, page_size=1000, node_kind=None, requirement="hierarchy")` writes all selected source UIDs in JSONL, retaining node identity, source role/raw provenance, normalized role, parent relationships and edge evidence, selected view and task admission. This is a domain export; benchmark-label admission is separately available from `task_labels()`.

## Migration and compatibility

Existing positional constructors, default strict relation view, UID identifiers and legacy path/list APIs are retained. New indexes and scope semantics apply to the review database; old databases use bounded contract-based traversals. Canonical domain filters now mean declared graph membership. Original source-domain filters use `source:<tag>`; old unambiguous raw domain names remain supported. Default domain listings deduplicate equivalent portals; use `include_aliases=True` for the legacy registry. Bare Q names and lost native rank/definition fields are recovered from source metadata, without rewriting original source payloads. Download into a new directory; rebuild refuses an existing destination and checks the v1.6 baseline hash.

Index readiness is transactional: incomplete migrations refuse queries. A database revision fingerprints all frozen inputs and graph-building code; stable cursors cannot be reused with a different revision. Per-stage source manifests and checks support resuming an unchanged migration. Changed inputs should be rebuilt from a fresh baseline, not repeatedly applied to an already changed publication.
