> 本文记录历史 V33 的分层存储。最新版 V35 只需一个数据库，见 [单库结构](single_database.md)。

# Storage and effective graph view

`bundle.json` is the portable dependency manifest. Each `files` entry identifies
one immutable SQLite snapshot, its size, SHA-256, table counts, relation counts
and UID namespaces. Paths are relative to the downloaded bundle directory.
The public API resolves them at runtime; original server paths are not required.

The complete graph uses a base graph, native source extension, name/alias stores,
identity bridges, successive refinement overlays and quarantine overlays. This
preserves source identities and contracts without silently flattening alignments
into classification edges.

| Store | Purpose |
|---|---|
| `data/v3/` | Unified WordNet/Wikidata graph |
| `data/v4/` | Source-native graph, alignment and lexical sidecars |
| `data/v25/` | Source identity projection |
| `data/v26/` | Six-dataset completion and optional target catalog |
| `data/v27/`–`data/v31/` | Cross-domain refinement records |
| `data/v31_accepted/` | Quarantined audited relations |
| `data/v32/` | Curated cross-domain batches |
| `data/v33/` | Latest refinement, identity and repair batches |

Inspect a source store without starting a server:

```python
import sqlite3
from pathlib import Path

path = Path('data/v33/wikidata_batch_0001.sqlite').resolve()
with sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True) as db:
    print(db.execute('PRAGMA table_info(nodes)').fetchall())
    print(db.execute('PRAGMA table_info(edges)').fetchall())
    print(db.execute('SELECT uid,label FROM nodes LIMIT 5').fetchall())
    print(db.execute('SELECT child_uid,parent_uid,relation FROM edges LIMIT 5').fetchall())
```

Schemas vary by source/layer: inspect `sqlite_master` and `PRAGMA table_info`
before writing bulk SQL. Node metadata and edge provenance may be JSON strings.
Evidence rows in overlays retain source claims, references and payload hashes.
Some historic provenance contains original source snapshot paths for attribution;
those references are metadata and are not needed to query the portable graph.

The raw tables are an archival representation. Effective navigation additionally
applies source equivalence, role contracts and the union of `suppressed_edges`
from the applicable repair stores. There are 190 quarantined endpoint pairs.
Never count `SAME_CONCEPT` as a classification edge or source `part-of`/attribute
relations as `IS_A`. Use `FineAtlas.neighbors()` for the effective public view.

The package needs no original source databases, remote service or model. All
data stores are opened read-only and immutable. Do not modify them in place;
retain the published hashes when making downstream overlays.
