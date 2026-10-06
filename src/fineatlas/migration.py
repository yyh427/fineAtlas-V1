"""Repeatable, staged review migration. SDK users do not need NumPy/SciPy.

The source adapters emit proofs, never inferred IS_A from arbitrary source edges.
An existing published database is an immutable input to this CLI.
"""

from __future__ import annotations
import collections
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

from ._text import norm
from .role_contracts import allows_model_extraction, nominal_role_decision, design_grain_for_claims
from .semantics import (
    CLASS_ROLES,
    TYPED_TERMINALS,
    VIEWS,
    edge_predicate,
    role_for_rank,
    role_expression,
)

LAYER = "v1.7-generality-review"


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


class Migration:
    def __init__(self, database, inputs, reports):
        self.db = Path(database).resolve()
        self.inputs = Path(inputs).resolve()
        self.out = Path(reports).resolve()
        self.out.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(self.db)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA cache_size=-1048576")
        self.c.execute("PRAGMA temp_store=MEMORY")
        self.c.execute("PRAGMA journal_mode=DELETE")
        self.c.execute(
            "CREATE TABLE IF NOT EXISTS usability_stages(stage TEXT PRIMARY KEY,input_sha256 TEXT NOT NULL,completed_utc TEXT NOT NULL,summary TEXT NOT NULL)"
        )
        self.c.commit()

    def schema(self):
        self.c.executescript("""
        CREATE TABLE IF NOT EXISTS node_taxon_ranks(uid TEXT PRIMARY KEY,rank TEXT,status TEXT NOT NULL,evidence_id TEXT NOT NULL,source TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS node_definitions(uid TEXT PRIMARY KEY,description TEXT NOT NULL,source TEXT NOT NULL,source_uri TEXT NOT NULL,evidence_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS normalization_roles(uid TEXT PRIMARY KEY,source_role TEXT NOT NULL,
          canonical_role TEXT NOT NULL,status TEXT NOT NULL,evidence_id TEXT NOT NULL,source TEXT NOT NULL,prior_profile TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS node_names(uid TEXT NOT NULL,name TEXT NOT NULL,language TEXT NOT NULL,
          preferred INTEGER NOT NULL,source TEXT NOT NULL,evidence_id TEXT NOT NULL,
          PRIMARY KEY(uid,name,language,source)) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS usability_changes(id INTEGER PRIMARY KEY,stage TEXT NOT NULL,
          object_type TEXT NOT NULL,object_id TEXT NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL,evidence TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS relation_rechecks(edge_id INTEGER PRIMARY KEY,decision TEXT NOT NULL,
          reason TEXT NOT NULL,new_relation TEXT,evidence TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS source_catalogs(source TEXT PRIMARY KEY,source_uri TEXT NOT NULL,
          license TEXT NOT NULL,input_sha256 TEXT NOT NULL,coverage TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS domain_registry(domain_id INTEGER PRIMARY KEY,canonical_name TEXT UNIQUE NOT NULL,
          entry_uid TEXT NOT NULL,label TEXT NOT NULL,root_uids TEXT NOT NULL,description TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS domain_aliases(alias TEXT PRIMARY KEY,domain_id INTEGER NOT NULL,
          provenance TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS domain_components(domain_id INTEGER NOT NULL,view TEXT NOT NULL,
          component_id INTEGER NOT NULL,depth INTEGER NOT NULL,category TEXT NOT NULL,
          PRIMARY KEY(domain_id,view,component_id)) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS domain_members(domain_id INTEGER NOT NULL,view TEXT NOT NULL,
          uid TEXT NOT NULL,role TEXT NOT NULL,depth INTEGER NOT NULL,
          PRIMARY KEY(domain_id,view,uid)) WITHOUT ROWID;
        CREATE INDEX IF NOT EXISTS domain_members_role ON domain_members(domain_id,view,role,uid);
        CREATE TABLE IF NOT EXISTS view_roots(view TEXT NOT NULL,component_id INTEGER NOT NULL,
          root_reachable INTEGER NOT NULL,depth INTEGER NOT NULL,parent_component_id INTEGER,
          witness_id INTEGER,PRIMARY KEY(view,component_id)) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS view_paths(view TEXT NOT NULL,component_id INTEGER NOT NULL,depth INTEGER NOT NULL,
          parent_component_id INTEGER,witness_id INTEGER,contains_terminal INTEGER NOT NULL,typed_route INTEGER NOT NULL,contains_navigation INTEGER NOT NULL,
          PRIMARY KEY(view,component_id)) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS view_terminal_connections(view TEXT NOT NULL,uid TEXT NOT NULL,
          class_uid TEXT NOT NULL,witness_relation_id INTEGER NOT NULL,depth INTEGER NOT NULL,
          PRIMARY KEY(view,uid)) WITHOUT ROWID;
        CREATE INDEX IF NOT EXISTS nodes_component_visibility ON nodes(component_id,visibility,uid);
        CREATE UNIQUE INDEX IF NOT EXISTS usability_source_arc ON edges(child_uid,parent_uid,relation,source,layer) WHERE layer='v1.7-generality-review';
        CREATE INDEX IF NOT EXISTS instances_by_type_uid ON entity_relations(object_uid,relation,status,subject_uid);
        """)
        self.meta("usability_indexes_ready", False)
        self.c.execute("PRAGMA analysis_limit=1000")
        self.c.execute("ANALYZE")
        self.c.commit()

    def meta(self, key, value):
        self.c.execute(
            "INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, dump(value))
        )

    def change(self, stage, kind, uid, before, after, evidence):
        self.c.execute(
            "INSERT INTO usability_changes(stage,object_type,object_id,before_json,after_json,evidence) VALUES (?,?,?,?,?,?)",
            (stage, kind, str(uid), dump(before), dump(after), dump(evidence)),
        )

    def evidence(
        self, source, uri, payload, claim="REVIEWED_SOURCE_FACT", license="CC0"
    ):
        raw = dump(payload)
        eid = "usability:" + hashlib.sha256(raw.encode()).hexdigest()
        self.c.execute(
            "INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?,?,?,?)",
            (
                LAYER,
                eid,
                source,
                uri,
                payload.get("retrieved_utc", "2026-10-05"),
                claim,
                raw,
                hashlib.sha256(raw.encode()).hexdigest(),
            ),
        )
        return eid

    def role(self, uid, kind, proof, source, uri):
        n = self.c.execute("SELECT * FROM nodes WHERE uid=?", (uid,)).fetchone()
        if not n:
            raise ValueError("Role endpoint missing: " + uid)
        prior = self.c.execute(
            "SELECT * FROM node_profiles WHERE uid=?", (uid,)
        ).fetchone()
        eid = self.evidence(source, uri, proof, "NORMALIZED_ROLE")
        if uid not in {
            r[0]
            for r in self.c.execute(
                "SELECT uid FROM normalization_roles WHERE uid=?", (uid,)
            )
        }:
            self.c.execute(
                "INSERT INTO normalization_roles VALUES (?,?,?,?,?,?,?)",
                (
                    uid,
                    proof.get("source_role") or n["rank"] or "UNSPECIFIED",
                    kind,
                    "VERIFIED",
                    eid,
                    source,
                    dump(dict(prior) if prior else {}),
                ),
            )
        attrs = json.loads(prior["attributes"]) if prior else {}
        # Keep the first source/profile snapshot, but expose the latest
        # canonical decision and its evidence in this current-state table.
        self.c.execute('UPDATE normalization_roles SET canonical_role=?,evidence_id=?,source=? WHERE uid=?',
                       (kind,eid,source,uid))
        if proof.get("allowed_views") is not None:
            attrs["allowed_views"] = proof["allowed_views"]
        attrs["source_role"] = proof.get(
            "source_role", attrs.get("source_role", n["rank"] or "UNSPECIFIED")
        )
        attrs.update(
            {
                "native_rank": proof.get(
                    "native_rank", attrs.get("native_rank", n["rank"])
                ),
                "role_status": "VERIFIED",
                "role_evidence_id": eid,
            }
        )
        self.c.execute(
            "INSERT OR REPLACE INTO node_profiles VALUES (?,?,?,?,?,?)",
            (
                uid,
                kind,
                prior["domain"] if prior else n["domain"],
                uri,
                eid,
                dump(attrs),
            ),
        )
        self.change(
            "roles",
            "node",
            uid,
            dict(prior) if prior else {"native_rank": n["rank"]},
            {"node_kind": kind},
            proof,
        )
        return eid

    def typed(self, child, parent, relation, proof, source, uri):
        eid = self.evidence(source, uri, proof, "TYPED_CONNECTION")
        current = self.c.execute(
            "SELECT status,evidence_id FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?",
            (child, parent, relation, source),
        ).fetchone()
        if current and current["status"] == "ACTIVE" and current["evidence_id"] == eid:
            return
        components = [
            self.c.execute(
                "SELECT component_id FROM nodes WHERE uid=?", (u,)
            ).fetchone()[0]
            for u in (child, parent)
        ]
        status = "REVIEW" if components[0] == components[1] else "ACTIVE"
        self.c.execute(
            "INSERT INTO entity_relations(subject_uid,object_uid,relation,status,source,evidence_id,data) VALUES (?,?,?,?,?,?,?) ON CONFLICT(subject_uid,object_uid,relation,source) DO UPDATE SET status=excluded.status,evidence_id=excluded.evidence_id,data=excluded.data",
            (
                child,
                parent,
                relation,
                status,
                source,
                eid,
                dump(
                    {
                        "admission_basis": proof,
                        "is_class_inclusion": False,
                        "identity_contraction_review": status == "REVIEW",
                    }
                ),
            ),
        )
        self.change(
            "relations",
            "typed",
            child,
            {},
            {"parent_uid": parent, "relation": relation},
            proof,
        )

    def add_node(self, uid, label, kind, domain, source, uri, proof, description=""):
        if self.c.execute("SELECT 1 FROM nodes WHERE uid=?", (uid,)).fetchone():
            return False
        comp = self.c.execute(
            "SELECT coalesce(max(id),-1)+1 FROM components"
        ).fetchone()[0]
        self.c.execute(
            "INSERT INTO components(id,depth,wordnet_reachable) VALUES (?,NULL,0)",
            (comp,),
        )
        self.c.execute(
            "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                uid,
                label,
                domain,
                dump([domain]),
                source,
                kind.lower(),
                description,
                dump(proof),
                LAYER,
                "ACTIVE",
                comp,
            ),
        )
        self.role(uid, kind, proof, source, uri)
        self.alias(uid, label, source, "en", True)
        self.change(
            "source_additions", "node", uid, {}, {"label": label, "role": kind}, proof
        )
        return True

    def alias(self, uid, name, source, language="und", preferred=False, eid=""):
        if not name.strip():
            return
        self.c.execute(
            "INSERT INTO node_names VALUES (?,?,?,?,?,?) ON CONFLICT(uid,name,language,source) DO UPDATE SET preferred=max(preferred,excluded.preferred),evidence_id=excluded.evidence_id",
            (uid, name, language, int(preferred), source, eid),
        )
        normalized = norm(name)
        if not self.c.execute(
            "SELECT 1 FROM aliases WHERE alias=? AND uid=?", (normalized, uid)
        ).fetchone():
            cur = self.c.execute(
                "INSERT INTO aliases VALUES (?,?,?,?,?,?)",
                (
                    normalized,
                    uid,
                    name,
                    source,
                    LAYER,
                    dump({"language": language, "evidence_id": eid}),
                ),
            )
            if self.c.execute(
                "SELECT 1 FROM sqlite_master WHERE name='alias_search'"
            ).fetchone():
                self.c.execute(
                    "INSERT INTO alias_search(rowid,alias) VALUES (?,?)",
                    (cur.lastrowid, normalized),
                )

    def names(self):
        added = 0
        entities = 0
        paths = sorted((self.inputs / "wikidata").glob("*.json.gz"))
        for file_index, path in enumerate(paths, 1):
            data = json.loads(gzip.decompress(path.read_bytes()))
            sha = digest_file(path)
            for q, item in data.get("entities", {}).items():
                if "missing" in item:
                    continue
                uids = [
                    r[0]
                    for r in self.c.execute(
                        "SELECT uid FROM nodes WHERE uid IN (?,?,?)",
                        ("wikidata:" + q, "wikidata-v4:" + q, "v26-wikidata:" + q),
                    )
                ]
                if not uids:
                    continue
                eid = self.evidence(
                    "Wikidata",
                    "https://www.wikidata.org/wiki/" + q,
                    {
                        "source_entity_id": q,
                        "source_file": path.name,
                        "source_sha256": sha,
                        "labels": item.get("labels", {}),
                        "aliases": item.get("aliases", {}),
                        "license": "CC0",
                    },
                    "MULTILINGUAL_NAMES",
                )
                entities += 1
                for uid in uids:
                    for lang, obj in item.get("labels", {}).items():
                        name = obj["value"]
                        self.alias(uid, name, "Wikidata", lang, True, eid)
                        added += 1
                    for lang, values in item.get("aliases", {}).items():
                        for obj in values:
                            self.alias(uid, obj["value"], "Wikidata", lang, False, eid)
                            added += 1
            if file_index % 25 == 0:
                self.c.commit()
                print("NAMES", file_index, len(paths), added, flush=True)
                (self.out / "names_progress.json").write_text(
                    dump(
                        {
                            "files_completed": file_index,
                            "files_total": len(paths),
                            "name_assertions": added,
                        }
                    )
                )
        self.c.commit()
        self.c.execute(
            "INSERT OR REPLACE INTO source_catalogs VALUES (?,?,?,?,?)",
            (
                "Wikidata",
                "https://www.wikidata.org",
                "CC0",
                hashlib.sha256(
                    "".join(digest_file(p) for p in paths).encode()
                ).hexdigest(),
                dump(
                    {
                        "fetched_batches": len(paths),
                        "matched_entities": entities,
                        "name_assertions": added,
                    }
                ),
            ),
        )
        return {
            "fetched_batches": len(paths),
            "matched_entities": entities,
            "name_assertions": added,
        }

    def native_metadata(self):
        path = self.inputs / "native_metadata.jsonl.gz"
        if not path.exists():
            return {}
        sha = digest_file(path)
        count = 0
        counts = collections.Counter()
        known = {
            r[0]
            for r in self.c.execute(
                "SELECT uid FROM nodes WHERE uid LIKE 'wikidata:%' OR uid LIKE 'wikidata-v4:%' OR uid LIKE 'v26-wikidata:%'"
            )
        }
        unnamed = {
            r[0]
            for r in self.c.execute(
                "SELECT uid FROM nodes WHERE label GLOB 'Q[0-9]*' OR label=uid"
            )
        }
        named = {r[0] for r in self.c.execute("SELECT DISTINCT uid FROM node_names")}
        descriptions = []
        ranks_to_save = []
        eid = None

        def flush():
            self.c.executemany(
                "INSERT OR REPLACE INTO node_definitions VALUES (?,?,?,?,?)",
                descriptions,
            )
            self.c.executemany(
                "INSERT OR REPLACE INTO node_taxon_ranks VALUES (?,?,?,?,?)",
                ranks_to_save,
            )
            self.c.commit()
            descriptions.clear()
            ranks_to_save.clear()

        with gzip.open(path, "rt") as rows:
            for row in rows:
                item = json.loads(row)
                qid = item["qid"]
                if count % 10000 == 0:
                    eid = self.evidence(
                        "Wikidata native dump metadata",
                        "https://www.wikidata.org/wiki/Wikidata:Database_download",
                        {
                            "source_sha256": sha,
                            "source_batch": count // 10000,
                            "license": "CC0",
                            "basis": "Exact native QID; explicit source metadata and non-deprecated P105 statements; preferred statements take precedence",
                        },
                        "NATIVE_METADATA_BATCH",
                    )
                for uid in item["uids"]:
                    if uid.split(":")[-1] != qid or uid not in known:
                        raise ValueError("Native metadata identifier not grounded")
                    if item.get("description"):
                        descriptions.append(
                            (
                                uid,
                                item["description"],
                                "Wikidata native dump metadata",
                                "https://www.wikidata.org/wiki/" + qid,
                                eid,
                            )
                        )
                        counts["description_uids"] += 1
                    ranks = item["effective_ranks"]
                    if ranks:
                        status = (
                            "SOURCE_DECLARED" if len(ranks) == 1 else "CONFLICT_REVIEW"
                        )
                        ranks_to_save.append(
                            (
                                uid,
                                ranks[0] if len(ranks) == 1 else None,
                                status,
                                eid,
                                "Wikidata native P105",
                            )
                        )
                        counts[status] += 1
                    if item.get("label") and uid in unnamed and uid not in named:
                        self.alias(
                            uid,
                            item["label"],
                            "Wikidata native dump metadata",
                            "en",
                            True,
                            eid,
                        )
                        counts["recovered_label_uids"] += 1
                        named.add(uid)
                count += 1
                if count % 10000 == 0:
                    flush()
                    if count % 100000 == 0:
                        print("NATIVE METADATA", count, dict(counts), flush=True)
        flush()
        self.c.execute(
            "INSERT OR REPLACE INTO source_catalogs VALUES (?,?,?,?,?)",
            (
                "Wikidata native dump metadata",
                "https://www.wikidata.org/wiki/Wikidata:Database_download",
                "CC0",
                sha,
                dump(
                    {
                        "records": count,
                        **dict(counts),
                        "role": "metadata and taxon-rank annotations only; no ISA claims",
                    }
                ),
            ),
        )
        self.c.commit()
        return {"records": count, **dict(counts)}

    def definitions(self):
        count = 0
        expression = "coalesce(nullif(json_extract(n.data,'$.wikidata_description'),''),nullif(json_extract(n.data,'$.evidence_record.wikidata_description'),''))"
        query = (
            "SELECT n.uid,"
            + expression
            + " FROM nodes n WHERE n.description='' AND (n.uid LIKE 'wikidata:%' OR n.uid LIKE 'wikidata-v4:%' OR n.uid LIKE 'v26-wikidata:%') AND "
            + expression
            + " IS NOT NULL ORDER BY n.uid"
        )
        for uid, description in self.c.execute(query):
            source_uri = "https://www.wikidata.org/wiki/" + uid.split(":")[-1]
            eid = self.evidence(
                "Wikidata native description",
                source_uri,
                {
                    "uid": uid,
                    "description": description,
                    "basis": "Explicit native source description field retained in original node payload",
                    "license": "CC0",
                },
                "NATIVE_DESCRIPTION",
            )
            self.c.execute(
                "INSERT OR REPLACE INTO node_definitions VALUES (?,?,?,?,?)",
                (uid, description, "Wikidata", source_uri, eid),
            )
            count += 1
        self.c.commit()
        return {"recovered_native_descriptions": count}

    def source_ranks(self):
        path = self.inputs / "source_ranks.jsonl"
        counts = collections.Counter()
        if not path.exists():
            return {}
        for line in path.open():
            row = json.loads(line)
            eid = self.evidence(
                row["source"], row["source_uri"], row["proof"], "NATIVE_TAXON_RANK"
            )
            node = self.c.execute(
                "SELECT visibility FROM nodes WHERE uid=?", (row["uid"],)
            ).fetchone()
            if not node:
                raise ValueError("Taxon rank endpoint missing")
            self.c.execute(
                "INSERT OR REPLACE INTO node_taxon_ranks VALUES (?,?,?,?,?)",
                (row["uid"], row["rank"], row["status"], eid, row["source"]),
            )
            counts[row["status"]] += 1
        self.c.commit()
        return dict(counts)

    def accepted_proofs(self):
        """Replay adapter outputs with source hashes and normalized contract gates."""
        counts = collections.Counter()
        path = self.inputs / "relation_proofs.jsonl"
        if not path.exists():
            return dict(counts)
        for line in path.open():
            p = json.loads(line)
            edge = self.c.execute(
                "SELECT * FROM edges WHERE id=?", (p["edge_id"],)
            ).fetchone()
            if not edge:
                raise ValueError("Original relation absent")
            if (
                edge["child_uid"] != p["child_uid"]
                or edge["parent_uid"] != p["parent_uid"]
            ):
                raise ValueError("Proof endpoints differ")
            if p["decision"] == "ADMIT":
                for snapshot in p.get("snapshots", []):
                    if (
                        digest_file(self.inputs / snapshot["path"])
                        != snapshot["sha256"]
                    ):
                        raise ValueError("Source snapshot hash differs")
                relation = p["relation"]
                kind = p["role"]
                if relation not in TYPED_TERMINALS.get(kind, ()):
                    raise ValueError("Typed relation/role mismatch")
                parent = self.c.execute(
                    "SELECT visibility FROM nodes WHERE uid=?", (p["parent_uid"],)
                ).fetchone()
                if not parent or parent[0] != "ACTIVE":
                    raise ValueError("Typed proof has nonadmitted type")
                self.role(
                    p["child_uid"], kind, p["proof"], p["source"], p["source_uri"]
                )
                self.typed(
                    p["child_uid"],
                    p["parent_uid"],
                    relation,
                    p["proof"],
                    p["source"],
                    p["source_uri"],
                )
            self.c.execute(
                "INSERT OR REPLACE INTO relation_rechecks VALUES (?,?,?,?,?)",
                (
                    p["edge_id"],
                    p["decision"],
                    p["reason"],
                    p.get("relation"),
                    dump(p["proof"]),
                ),
            )
            counts[p["decision"]] += 1
        # Every legacy refinement is included, including untouched evidence gaps.
        self.c.execute("""INSERT OR IGNORE INTO relation_rechecks SELECT id,'REVIEW',
          'Source refinement claim alone does not establish subtype or typed terminal identity',NULL,provenance
          FROM edges WHERE original_relation='TYPED_REFINEMENT' """)
        self.c.commit()
        return dict(counts)

    def align_identity(self, uid, link, proof, source, uri):
        if not link.get("basis"):
            raise ValueError("Identity alignment lacks an explicit basis")
        own = self.c.execute(
            "SELECT component_id FROM nodes WHERE uid=?", (uid,)
        ).fetchone()
        target = self.c.execute(
            "SELECT component_id,visibility FROM nodes WHERE uid=?", (link["uid"],)
        ).fetchone()
        if not own or not target or target["visibility"] != "ACTIVE":
            raise ValueError("Identity endpoint not grounded")
        payload = {"identity_basis": link, "source_fact": proof}
        eid = self.evidence(source, uri, payload, "SOURCE_IDENTIFIER_ALIGNMENT")
        if not self.c.execute(
            "SELECT 1 FROM bridges WHERE left_uid=? AND right_uid=? AND relation='SAME_CONCEPT' AND status='ACTIVE'",
            (uid, link["uid"]),
        ).fetchone():
            self.c.execute(
                "INSERT INTO bridges(left_uid,right_uid,relation,confidence,source,layer,data,status,reason) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    uid,
                    link["uid"],
                    "SAME_CONCEPT",
                    1,
                    source,
                    LAYER,
                    dump({"evidence_ids": [eid], "identity_basis": link}),
                    "ACTIVE",
                    link["basis"],
                ),
            )
            self.change(
                "identity",
                "bridge",
                uid,
                {"component_id": own[0]},
                {"identity_uid": link["uid"], "component_id": target[0]},
                payload,
            )
        if own[0] != target[0]:
            self.c.execute(
                "UPDATE nodes SET component_id=? WHERE component_id=?",
                (target[0], own[0]),
            )
            # Preserve old component identifiers and their history; emptied
            # components are not counted as live identities by statistics.

    def source_facts(self):
        counts = collections.Counter()
        catalogs = {}
        path = self.inputs / "source_facts.jsonl"
        if not path.exists():
            return {}
        for line in path.open():
            p = json.loads(line)
            for snap in p.get("snapshots", []):
                if digest_file(self.inputs / snap["path"]) != snap["sha256"]:
                    raise ValueError("Source hash mismatch")
            source = p["source"]
            uri = p["source_uri"]
            proof = p["proof"]
            if source == 'Independent native product-family definition':
                native = self.c.execute('SELECT data FROM nodes WHERE uid=?', (p['uid'],)).fetchone()
                profile = self.c.execute('SELECT node_kind FROM node_profiles WHERE uid=?', (p['uid'],)).fetchone()
                if native and not allows_model_extraction(json.loads(native[0] or '{}'), dict(profile) if profile else None):
                    raise ValueError('Stale model extraction input conflicts with explicit source role: ' + p['uid'])
            catalog = catalogs.setdefault(
                source,
                {
                    "source_uri": uri,
                    "licenses": set(),
                    "facts": 0,
                    "parent_assertions": 0,
                },
            )
            catalog["facts"] += 1
            catalog["parent_assertions"] += len(p.get("parents", []))
            catalog["licenses"].add(
                proof.get("license", "Source terms not supplied; retain for review")
            )
            if self.add_node(
                p["uid"], p["label"], p["role"], p["domain"], source, uri, proof
            ):
                counts[source] += 1
            elif p.get("normalize_existing"):
                if p.get("activate_existing"):
                    prior = self.c.execute(
                        "SELECT visibility FROM nodes WHERE uid=?", (p["uid"],)
                    ).fetchone()[0]
                    if (
                        not proof.get("independent_definition_sha256")
                        or not proof.get("nominal_type_uid")
                        or not proof.get("role_basis")
                    ):
                        raise ValueError(
                            "Source-only promotion lacks independent scope/role evidence"
                        )
                    self.c.execute(
                        "UPDATE nodes SET visibility='ACTIVE' WHERE uid=?", (p["uid"],)
                    )
                    self.change(
                        "admission",
                        "node",
                        p["uid"],
                        {"visibility": prior},
                        {"visibility": "ACTIVE"},
                        proof,
                    )
                    counts["source_only_independently_admitted"] += (
                        prior == "SOURCE_ONLY"
                    )
                self.role(p["uid"], p["role"], proof, source, uri)
                counts["normalized_existing"] += 1
            for edge_id in p.get("normalize_edge_ids", []):
                original = self.c.execute(
                    "SELECT * FROM edges WHERE id=?", (edge_id,)
                ).fetchone()
                if (
                    not original
                    or original["child_uid"] != p["uid"]
                    or not any(x["uid"] == original["parent_uid"] for x in p["parents"])
                ):
                    raise ValueError("Native relation normalization endpoints differ")
                if (
                    p["role"] != "CONFIGURATION"
                    or original["source_relation"]
                    not in ("year+baseModel", "year+model", "model+baseModel")
                    or not proof.get("native_record_sha256")
                ):
                    raise ValueError("Native relation normalization proof absent")
                normalized = json.loads(original["data"])
                normalized["eligible_for_final_dag"] = False
                normalized["normalized_relation"] = "CONFIGURATION_OF"
                normalized["admission_basis"] = proof
                self.c.execute(
                    "UPDATE edges SET relation='CONFIGURATION_OF',status='TYPED_ACTIVE',data=?,reason='Native product configuration reference; original source declaration retained' WHERE id=?",
                    (dump(normalized), edge_id),
                )
                self.change(
                    "native_contract",
                    "edge",
                    edge_id,
                    dict(original),
                    {"relation": "CONFIGURATION_OF", "status": "TYPED_ACTIVE"},
                    proof,
                )
                counts["native_isa_normalized"] += 1
            for link in p.get("identity_links", []):
                self.align_identity(p["uid"], link, proof, source, uri)
            for alias in p.get("aliases", []):
                self.alias(p["uid"], alias, source, "en", False)
            for parent in p.get("parents", []):
                endpoint = self.c.execute(
                    "SELECT visibility FROM nodes WHERE uid=?", (parent["uid"],)
                ).fetchone()
                if not endpoint or endpoint[0] != "ACTIVE":
                    raise ValueError("Missing fact parent")
                relation = parent["relation"]
                if relation in TYPED_TERMINALS.get(p["role"], ()):
                    self.typed(p["uid"], parent["uid"], relation, proof, source, uri)
                elif relation in (
                    "IS_A",
                    "TAXONOMIC_PARENT",
                    "NATIVE_CLASSIFICATION_PARENT",
                ) and (
                    p["role"] in CLASS_ROLES
                    or p["role"] == "BIOLOGICAL_VARIANT"
                    and relation == "TAXONOMIC_PARENT"
                ):
                    eid = self.evidence(source, uri, proof, "GROUNDED_INCLUSION")
                    if not p.get("inclusion_basis"):
                        raise ValueError("No explicit inclusion basis")
                    child_comp = self.c.execute(
                        "SELECT component_id FROM nodes WHERE uid=?", (p["uid"],)
                    ).fetchone()[0]
                    parent_comp = self.c.execute(
                        "SELECT component_id FROM nodes WHERE uid=?", (parent["uid"],)
                    ).fetchone()[0]
                    redundant = child_comp == parent_comp
                    self.c.execute(
                        """INSERT OR IGNORE INTO edges(child_uid,parent_uid,relation,original_relation,facet_family,
                      classification_basis,navigation_role,source,source_relation,confidence,provenance,data,layer,status,reason)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            p["uid"],
                            parent["uid"],
                            relation,
                            relation,
                            "NATIVE_OBJECT_KIND"
                            if relation == "IS_A"
                            else "NATIVE_NAVIGATION",
                            p["inclusion_basis"],
                            "SOURCE_VALIDATED",
                            source,
                            parent.get("native_relation", relation),
                            1,
                            dump({"evidence_ids": [eid]}),
                            dump(
                                {
                                    "eligible_for_final_dag": relation == "IS_A"
                                    and not redundant,
                                    "admission_basis": p["inclusion_basis"],
                                }
                            ),
                            LAYER,
                            "REVIEW"
                            if redundant
                            else "ACTIVE"
                            if relation == "IS_A"
                            else "TYPED_ACTIVE",
                            "Verified identity endpoints make this native non-strict subsumption redundant"
                            if redundant
                            else "Source fact and endpoint role reviewed",
                        ),
                    )
                else:
                    raise ValueError("Unsupported source relation")
        input_sha = digest_file(path)
        for source, catalog in sorted(catalogs.items()):
            license = "; ".join(sorted(catalog.pop("licenses")))
            uri = catalog.pop("source_uri")
            catalog["new_source_uids"] = counts[source]
            self.c.execute(
                "INSERT OR REPLACE INTO source_catalogs VALUES (?,?,?,?,?)",
                (source, uri, license, input_sha, dump(catalog)),
            )
        reviews = self.inputs / "edge_reviews.jsonl"
        if reviews.exists():
            for line in reviews.open():
                p = json.loads(line)
                original = self.c.execute(
                    "SELECT * FROM edges WHERE id=?", (p["edge_id"],)
                ).fetchone()
                if not original or original["source_relation"] not in (
                    "year+baseModel",
                    "year+model",
                    "model+baseModel",
                ):
                    raise ValueError("Native edge review source differs")
                data = json.loads(original["data"])
                data["eligible_for_final_dag"] = False
                data["review_evidence"] = p
                self.c.execute(
                    "UPDATE edges SET status='REVIEW',data=?,reason=? WHERE id=?",
                    (dump(data), p["reason"], p["edge_id"]),
                )
                self.c.execute(
                    "INSERT OR REPLACE INTO relation_rechecks VALUES (?,?,?,?,?)",
                    (p["edge_id"], "REVIEW", p["reason"], None, dump(p)),
                )
                self.change(
                    "native_contract",
                    "edge",
                    p["edge_id"],
                    dict(original),
                    {"status": "REVIEW"},
                    p,
                )
                counts["native_relation_endpoint_reviews"] += 1
        self.c.commit()
        return dict(counts)

    def task_updates(self):
        path = self.inputs / "task_updates.jsonl"
        count = 0
        if not path.exists():
            return {"task_scope_updates": 0}
        for line in path.open():
            p = json.loads(line)
            prior = self.c.execute(
                "SELECT * FROM dataset_targets WHERE dataset=? AND class_id=?",
                (p["dataset"], p["class_id"]),
            ).fetchone()
            if not prior:
                raise ValueError("Native task identity absent")
            n = self.c.execute(
                "SELECT visibility FROM nodes WHERE uid=?", (p["target_uid"],)
            ).fetchone()
            if not n or n[0] != "ACTIVE":
                raise ValueError("Normalized task mapping endpoint not admitted")
            eid = self.evidence(
                "Native task botanical scope",
                p["source_uri"],
                p["proof"],
                "TASK_MAPPING_SCOPE",
            )
            provenance = json.loads(prior["provenance"])
            provenance["normalized_scope"] = {
                "prior_mapping": p["raw_prior"],
                "relation": p["mapping_relation"],
                "mapped_type_uid": p["mapping_parent_uid"],
                "evidence_id": eid,
            }
            ids = json.loads(prior["evidence_ids"])
            ids.append(eid)
            self.c.execute(
                "UPDATE dataset_targets SET target_uid=?,decision_status=?,identity_basis=?,granularity_basis=?,evidence_ids=?,provenance=? WHERE dataset=? AND class_id=?",
                (
                    p["target_uid"],
                    p["decision_status"],
                    "Native task category identity preserved; botanical type connected through "
                    + p["mapping_relation"],
                    p["proof"]["scope_basis"],
                    dump(sorted(set(ids))),
                    dump(provenance),
                    p["dataset"],
                    p["class_id"],
                ),
            )
            self.change(
                "tasks",
                "target",
                p["dataset"] + ":" + p["class_id"],
                dict(prior),
                p,
                p["proof"],
            )
            count += 1
        self.c.commit()
        return {"task_scope_updates": count}

    def portals(self):
        new_domains = self.inputs / "new_domains.jsonl"
        if new_domains.exists():
            for line in new_domains.read_text().splitlines():
                entry = json.loads(line)
                roots = entry["root_uids"]
                for uid in roots:
                    node = self.c.execute(
                        "SELECT visibility FROM nodes WHERE uid=?", (uid,)
                    ).fetchone()
                    if not node or node[0] != "ACTIVE":
                        raise ValueError("Domain root is not grounded: " + uid)
                if not entry.get("proof") or not entry.get("source_uri"):
                    raise ValueError("Domain scope lacks source evidence")
                eid = self.evidence(
                    "Declared native domain scope",
                    entry["source_uri"],
                    entry["proof"],
                    "DOMAIN_SCOPE",
                )
                before = self.c.execute(
                    "SELECT * FROM domain_entries WHERE domain=?", (entry["domain"],)
                ).fetchone()
                self.c.execute(
                    "INSERT OR REPLACE INTO domain_entries VALUES (?,?,?,?,?,?)",
                    (
                        entry["domain"],
                        "fineatlas-domain:" + entry["domain"],
                        entry["label"],
                        roots[0],
                        dump(roots),
                        entry["description"],
                    ),
                )
                self.c.execute(
                    "DELETE FROM domain_entry_roots WHERE domain=?", (entry["domain"],)
                )
                self.c.executemany(
                    "INSERT INTO domain_entry_roots VALUES (?,?)",
                    ((entry["domain"], uid) for uid in roots),
                )
                self.change(
                    "portals",
                    "entry",
                    entry["domain"],
                    dict(before) if before else {},
                    entry,
                    {"evidence_id": eid},
                )
        self.c.execute("DELETE FROM domain_registry")
        self.c.execute("DELETE FROM domain_aliases")
        groups = collections.defaultdict(list)
        for r in self.c.execute("SELECT * FROM domain_entries ORDER BY domain"):
            item = dict(r)
            roots = json.loads(item["root_uids"])
            comps = tuple(
                sorted(
                    {
                        self.c.execute(
                            "SELECT component_id FROM nodes WHERE uid=?", (u,)
                        ).fetchone()[0]
                        for u in roots
                    }
                )
            )
            groups[comps].append(item)
        for i, (comps, items) in enumerate(
            sorted(groups.items(), key=lambda x: min(y["domain"] for y in x[1])), 1
        ):
            canonical = min(
                items,
                key=lambda x: (
                    x["domain"].startswith("source_"),
                    len(x["domain"]),
                    x["domain"],
                ),
            )
            roots = sorted({u for x in items for u in json.loads(x["root_uids"])})
            self.c.execute(
                "INSERT INTO domain_registry VALUES (?,?,?,?,?,?)",
                (
                    i,
                    canonical["domain"],
                    canonical["entry_uid"],
                    canonical["label"],
                    dump(roots),
                    canonical["description"],
                ),
            )
            for entry in items:
                for alias in {
                    entry["domain"],
                    entry["entry_uid"].removeprefix("fineatlas-domain:"),
                }:
                    self.c.execute(
                        "INSERT OR REPLACE INTO domain_aliases VALUES (?,?,?)",
                        (
                            alias,
                            i,
                            dump(
                                {
                                    "old_entry_uid": entry["entry_uid"],
                                    "basis": "Identical grounded root identity-group sets",
                                }
                            ),
                        ),
                    )
        candidates = collections.defaultdict(set)
        for row in self.c.execute("SELECT domain_id,root_uids FROM domain_registry"):
            for uid in json.loads(row["root_uids"]):
                for (alias,) in self.c.execute(
                    "SELECT alias FROM aliases WHERE uid=?", (uid,)
                ):
                    if alias and not re.fullmatch(r"q\d+", alias):
                        candidates[alias].add(row["domain_id"])
        ambiguous = 0
        for alias, ids in sorted(candidates.items()):
            if (
                len(ids) == 1
                and not self.c.execute(
                    "SELECT 1 FROM domain_aliases WHERE alias=?", (alias,)
                ).fetchone()
            ):
                self.c.execute(
                    "INSERT INTO domain_aliases VALUES (?,?,?)",
                    (
                        alias,
                        next(iter(ids)),
                        dump(
                            {
                                "basis": "Unambiguous stored native root name or multilingual alias"
                            }
                        ),
                    ),
                )
            elif len(ids) > 1:
                ambiguous += 1
        self.c.commit()
        return {
            "ambiguous_native_aliases_not_added": ambiguous,
            "original_portals": sum(map(len, groups.values())),
            "canonical_portals": len(groups),
        }

    def graphs(self):
        """Build version-bound root witnesses and shared multi-domain membership."""
        import numpy as np
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import breadth_first_order, connected_components

        c = self.c
        N = c.execute("SELECT max(id)+1 FROM components").fetchone()[0]
        root = c.execute(
            "SELECT component_id FROM nodes WHERE uid=(SELECT json_extract(value,'$') FROM metadata WHERE key='root_uid')"
        ).fetchone()[0]
        roles = role_expression("n", "p")
        category_mask = np.zeros(N, bool)
        class_mask = np.zeros(N, bool)
        class_weight = np.zeros(N, np.int32)
        terminal_role = {}
        role_counts = collections.Counter()
        for comp, role, count in c.execute(
            "SELECT n.component_id,"
            + roles
            + ",count(*) FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility='ACTIVE' GROUP BY 1,2"
        ):
            role_counts[role] += count
            if role == "DATASET_CATEGORY":
                category_mask[comp] = True
            if role in TYPED_TERMINALS and role not in CLASS_ROLES:
                terminal_role[comp] = role
            if role in CLASS_ROLES:
                class_mask[comp] = True
                class_weight[comp] += count
        variant = np.zeros(N, bool)
        for (comp,) in c.execute(
            "SELECT n.component_id FROM node_profiles p JOIN nodes n ON n.uid=p.uid WHERE p.node_kind='BIOLOGICAL_VARIANT' AND n.visibility='ACTIVE'"
        ):
            variant[comp] = True
        c.execute("DELETE FROM domain_members")
        c.execute("DELETE FROM view_paths")
        c.execute("DELETE FROM view_roots")
        c.execute("DELETE FROM view_terminal_connections")
        c.execute("DELETE FROM domain_components")
        c.commit()
        summaries = {}
        entries = [
            dict(r)
            for r in c.execute("SELECT * FROM domain_registry ORDER BY domain_id")
        ]
        for view in VIEWS:
            start = time.monotonic()
            blocked = np.zeros(N, bool)
            allowed = (
                class_mask | variant
                if view == "taxonomy"
                else class_mask | category_mask
                if view == "membership"
                else class_mask
            ).copy()
            for (comp,) in c.execute(
                """SELECT n.component_id FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility='ACTIVE' GROUP BY n.component_id HAVING sum(CASE WHEN json_type(p.attributes,'$.allowed_views')='array' AND NOT EXISTS(SELECT 1 FROM json_each(p.attributes,'$.allowed_views') j WHERE j.value=?) THEN 0 ELSE 1 END)=0""",
                (view,),
            ):
                blocked[comp] = True
            allowed[blocked] = False
            chunks = []
            cur = c.execute(
                """SELECT p.component_id,a.component_id,e.id FROM edges e JOIN nodes p ON p.uid=e.parent_uid
                JOIN nodes a ON a.uid=e.child_uid LEFT JOIN node_profiles pp ON pp.uid=p.uid LEFT JOIN node_profiles ap_role ON ap_role.uid=a.uid WHERE p.visibility='ACTIVE' AND a.visibility='ACTIVE' AND NOT EXISTS(SELECT 1 FROM node_profiles ap WHERE ap.uid IN (a.uid,p.uid) AND json_type(ap.attributes,'$.allowed_views')='array' AND NOT EXISTS(SELECT 1 FROM json_each(ap.attributes,'$.allowed_views') av WHERE av.value=?)) AND """
                + edge_predicate(view)
                + " AND "
                + role_expression("a", "ap_role")
                + " IN ("
                + ",".join(
                    "'" + r + "'"
                    for r in sorted(
                        CLASS_ROLES
                        | (
                            {"BIOLOGICAL_VARIANT"}
                            if view == "taxonomy"
                            else {"DATASET_CATEGORY"}
                            if view == "membership"
                            else set()
                        )
                    )
                )
                + ") AND "
                + role_expression("p", "pp")
                + " IN ("
                + ",".join(
                    "'" + r + "'"
                    for r in sorted(
                        CLASS_ROLES
                        | (
                            {"BIOLOGICAL_VARIANT"}
                            if view == "taxonomy"
                            else {"DATASET_CATEGORY"}
                            if view == "membership"
                            else set()
                        )
                    )
                )
                + ")",
                (view,),
            )
            while rows := cur.fetchmany(250000):
                chunks.append(np.asarray(rows, dtype=np.int64))
            triples = np.concatenate(chunks) if chunks else np.empty((0, 3), np.int64)
            del chunks
            triples = triples[allowed[triples[:, 0]] & allowed[triples[:, 1]]]
            g = coo_matrix(
                (np.ones(len(triples), np.int8), (triples[:, 0], triples[:, 1])),
                shape=(N, N),
            ).tocsr()
            g.data[:] = 1
            # Strong components reveal cycles anywhere, including disconnected branches.
            _, scc = connected_components(g, directed=True, connection="strong")
            cycle_arcs = int(np.count_nonzero(scc[triples[:, 0]] == scc[triples[:, 1]]))
            if cycle_arcs:
                raise ValueError(
                    f"{view} has {cycle_arcs} within-SCC arcs; migration is not accepted"
                )
            order, pred = breadth_first_order(
                g, root, directed=True, return_predecessors=True
            )
            depth = np.full(N, -1, np.int32)
            depth[root] = 0
            for v in order[1:]:
                depth[v] = depth[pred[v]] + 1
            witness = np.full(N, np.iinfo(np.int64).max, np.int64)
            good = pred[triples[:, 1]] == triples[:, 0]
            np.minimum.at(witness, triples[good, 1], triples[good, 2])
            c.executemany(
                "INSERT INTO view_roots VALUES (?,?,1,?,?,?)",
                (
                    (
                        view,
                        int(v),
                        int(depth[v]),
                        int(pred[v]) if v != root else None,
                        int(witness[v]) if v != root else None,
                    )
                    for v in order
                ),
            )
            c.commit()
            if view == "strict":
                c.execute(
                    "UPDATE components SET wordnet_reachable=0,depth=NULL,parent_component_id=NULL,witness_edge_id=NULL WHERE wordnet_reachable=1 AND NOT EXISTS(SELECT 1 FROM view_roots vr WHERE vr.view='strict' AND vr.component_id=components.id)"
                )
                c.execute(
                    """UPDATE components SET wordnet_reachable=1,depth=vr.depth,parent_component_id=vr.parent_component_id,witness_edge_id=vr.witness_id FROM view_roots vr WHERE vr.view='strict' AND components.id=vr.component_id AND (components.wordnet_reachable IS NOT 1 OR components.depth IS NOT vr.depth OR components.witness_edge_id IS NOT vr.witness_id)"""
                )
                c.commit()
            # A separate mixed path index includes explicit role-compatible arcs.
            # It never changes strict classification reachability or its counts.
            terminals = []
            for role, rels in TYPED_TERMINALS.items():
                marks = ",".join("?" for _ in rels)
                query = f"""SELECT t.component_id,n.component_id,-r.id FROM entity_relations r
                  JOIN nodes n ON n.uid=r.subject_uid JOIN nodes t ON t.uid=r.object_uid
                  LEFT JOIN node_profiles p ON p.uid=n.uid LEFT JOIN node_profiles tp ON tp.uid=t.uid WHERE {role_expression("t", "tp")} IN ('CLASS','MODEL','MODEL_FAMILY','CONFIGURATION' {",'BIOLOGICAL_VARIANT'" if view == "taxonomy" else ""}) AND NOT EXISTS(SELECT 1 FROM node_profiles bp WHERE bp.uid IN (n.uid,t.uid) AND json_type(bp.attributes,'$.allowed_views')='array' AND NOT EXISTS(SELECT 1 FROM json_each(bp.attributes,'$.allowed_views') av WHERE av.value=?)) AND r.status='ACTIVE'
                  AND n.visibility='ACTIVE' AND t.visibility='ACTIVE' AND r.relation IN ({marks}) AND {roles}=?"""
                cur = c.execute(query, (view, *rels, role))
                while rows := cur.fetchmany(250000):
                    values = np.asarray(rows, dtype=np.int64)
                    values = values[allowed[values[:, 0]] & ~blocked[values[:, 1]]]
                    terminals.append(values)
            typed = (
                np.concatenate(terminals) if terminals else np.empty((0, 3), np.int64)
            )
            mixed = np.concatenate([triples, typed])
            del terminals, typed
            browse = coo_matrix(
                (np.ones(len(mixed), np.int8), (mixed[:, 0], mixed[:, 1])), shape=(N, N)
            ).tocsr()
            browse.data[:] = 1
            _, mixscc = connected_components(browse, directed=True, connection="strong")
            if np.count_nonzero(mixscc[mixed[:, 0]] == mixscc[mixed[:, 1]]):
                raise ValueError(
                    "Mixed hierarchy has cyclic typed arcs; review identities and roles"
                )
            mixorder, mixpred = breadth_first_order(
                browse, root, directed=True, return_predecessors=True
            )
            mixdepth = np.full(N, -1, np.int32)
            mixdepth[root] = 0
            mixwitness = np.zeros(N, np.int64)
            ok = mixpred[mixed[:, 1]] == mixed[:, 0]
            keys = np.where(
                mixed[ok, 2] > 0,
                mixed[ok, 2],
                np.iinfo(np.int64).max // 2 - mixed[ok, 2],
            )
            choices = np.full(N, np.iinfo(np.int64).max, np.int64)
            np.minimum.at(choices, mixed[ok, 1], keys)
            chosen = keys == choices[mixed[ok, 1]]
            mixwitness[mixed[ok, 1][chosen]] = mixed[ok, 2][chosen]
            has_terminal = np.zeros(N, bool)
            for v in mixorder[1:]:
                mixdepth[v] = mixdepth[mixpred[v]] + 1
                has_terminal[v] = has_terminal[mixpred[v]] or mixwitness[v] < 0

            def propagate(seeds):
                from collections import deque

                found = np.zeros(N, bool)
                found[seeds] = True
                queue = deque(map(int, seeds))
                while queue:
                    v = queue.popleft()
                    for child in browse.indices[
                        browse.indptr[v] : browse.indptr[v + 1]
                    ]:
                        if not found[child]:
                            found[child] = True
                            queue.append(int(child))
                return found

            typed_seeds = np.unique(
                mixed[(mixed[:, 2] < 0) & (mixdepth[mixed[:, 0]] >= 0), 1]
            )
            typed_routes = propagate(typed_seeds)
            nav_ids = {
                r[0]
                for r in c.execute(
                    "SELECT id FROM edges WHERE status IN ('ACTIVE','TYPED_ACTIVE') AND relation IN ('NATIVE_CLASSIFICATION_PARENT','REUSABLE_TYPE_MEMBERSHIP')"
                )
            }
            regulated_ids = {
                -r[0]
                for r in c.execute(
                    "SELECT id FROM entity_relations WHERE status='ACTIVE' AND relation='REGULATED_AS'"
                )
            }
            nav_witness_ids = nav_ids | regulated_ids
            nav_seed_mask = np.fromiter(
                (int(w) in nav_witness_ids for w in mixed[:, 2]), bool, len(mixed)
            )
            navigation_routes = propagate(
                np.unique(mixed[nav_seed_mask & (mixdepth[mixed[:, 0]] >= 0), 1])
            )
            c.executemany(
                "INSERT INTO view_paths VALUES (?,?,?,?,?,?,?,?)",
                (
                    (
                        view,
                        int(v),
                        int(mixdepth[v]),
                        int(mixpred[v]) if v != root else None,
                        int(mixwitness[v]) if v != root else None,
                        int(has_terminal[v]),
                        int(typed_routes[v]),
                        int(navigation_routes[v]),
                    )
                    for v in mixorder
                ),
            )
            for role, rels in TYPED_TERMINALS.items():
                marks = ",".join("?" for _ in rels)
                c.execute(
                    f"""INSERT OR IGNORE INTO view_terminal_connections
                  SELECT ?,n.uid,r.object_uid,r.id,vp.depth+1 FROM entity_relations r JOIN nodes n ON n.uid=r.subject_uid
                  JOIN nodes t ON t.uid=r.object_uid LEFT JOIN node_profiles p ON p.uid=n.uid
                  JOIN view_paths vp ON vp.component_id=t.component_id AND vp.view=?
                  WHERE r.status='ACTIVE' AND n.visibility='ACTIVE' AND t.visibility='ACTIVE'
                  AND r.relation IN ({marks}) AND {roles}=? AND NOT EXISTS(SELECT 1 FROM node_profiles bp WHERE bp.uid IN (n.uid,t.uid) AND json_type(bp.attributes,'$.allowed_views')='array' AND NOT EXISTS(SELECT 1 FROM json_each(bp.attributes,'$.allowed_views') av WHERE av.value=vp.view)) ORDER BY vp.depth,r.id""",
                    (view, view, *rels, role),
                )
            c.commit()
            outdegree = np.diff(g.indptr)
            global_classes = (depth >= 0) & allowed
            _, weak = connected_components(g, directed=False, connection="weak")
            live_groups = np.flatnonzero(allowed)
            weak_counts = collections.Counter(map(int, weak[live_groups]))
            frontier = np.flatnonzero(
                allowed & (depth < 0) & (np.diff(g.tocsc().indptr) == 0)
            )
            (self.out / (view + "_unrooted_frontier.json")).write_text(
                dump(
                    {
                        "component_ids": list(map(int, frontier)),
                        "meaning": "Admitted groups without a parent in this view; absence may be intentional for native taxonomy or typed designs, not automatically a missing source",
                    }
                )
            )
            summary = {
                "class_root_groups": int(global_classes.sum()),
                "class_root_source_uids": int(class_weight[global_classes].sum()),
                "class_groups_total": int(allowed.sum()),
                "arcs": int(g.nnz),
                "provenance_rows": len(triples),
                "cycle_arcs": cycle_arcs,
                "weak_components": len(weak_counts),
                "unrooted_weak_components": len(weak_counts)
                - (1 if root in live_groups else 0),
                "unrooted_frontier_groups": len(frontier),
                "max_root_shortest_depth": int(depth[global_classes].max()),
                "typed_terminal_root_uids": c.execute(
                    "SELECT count(*) FROM view_terminal_connections WHERE view=?",
                    (view,),
                ).fetchone()[0],
                "domains": [],
            }
            cache = {}
            for entry in entries:
                native_roots = json.loads(entry["root_uids"])
                ds = np.full(N, -1, np.int32)
                for uid in native_roots:
                    comp = c.execute(
                        "SELECT component_id FROM nodes WHERE uid=?", (uid,)
                    ).fetchone()[0]
                    if comp not in cache:
                        seq, pp = breadth_first_order(
                            browse, comp, directed=True, return_predecessors=True
                        )
                        dd = np.full(N, -1, np.int32)
                        dd[comp] = 0
                        for v in seq[1:]:
                            dd[v] = dd[pp[v]] + 1
                        cache[comp] = (seq, dd[seq])
                    seq, values = cache[comp]
                    old = ds[seq]
                    ds[seq] = np.where(old < 0, values, np.minimum(old, values))
                selected = np.flatnonzero((ds >= 0) & allowed)
                c.executemany(
                    "INSERT INTO domain_components VALUES (?,?,?,?,?)",
                    (
                        (entry["domain_id"], view, int(v), int(ds[v]), "CLASSIFICATION")
                        for v in selected
                    ),
                )
                terminal_groups = np.flatnonzero((ds >= 0) & ~allowed)
                c.executemany(
                    "INSERT OR IGNORE INTO domain_components VALUES (?,?,?,?,?)",
                    (
                        (
                            entry["domain_id"],
                            view,
                            int(v),
                            int(ds[v]),
                            terminal_role[int(v)],
                        )
                        for v in terminal_groups
                        if int(v) in terminal_role
                    ),
                )
                item = {
                    "domain": entry["canonical_name"],
                    "domain_id": entry["domain_id"],
                    "class_groups": len(selected),
                    "class_source_uids": int(class_weight[selected].sum()),
                    "levels": int(ds[selected].max()) if len(selected) else None,
                    "leaf_groups": int((outdegree[selected] == 0).sum()),
                    "strict_or_view_root_groups": int((depth[selected] >= 0).sum()),
                    "terminals": dict(
                        c.execute(
                            "SELECT category,count(*) FROM domain_components WHERE domain_id=? AND view=? AND category<>'CLASSIFICATION' GROUP BY category",
                            (entry["domain_id"], view),
                        )
                    ),
                }
                summary["domains"].append(item)
                c.commit()
                print(
                    "scope",
                    view,
                    entry["canonical_name"],
                    len(selected),
                    item["terminals"],
                    flush=True,
                )
            admitted_roles = sorted(
                CLASS_ROLES
                | set(TYPED_TERMINALS)
                | ({"BIOLOGICAL_VARIANT"} if view == "taxonomy" else set())
            )
            markers = ",".join("?" for _ in admitted_roles)
            for entry in entries:
                c.execute(
                    f"""INSERT INTO domain_members SELECT dc.domain_id,dc.view,n.uid,{roles},dc.depth
                   FROM domain_components dc CROSS JOIN nodes n LEFT JOIN node_profiles p ON p.uid=n.uid
                   WHERE dc.domain_id=? AND dc.view=? AND n.component_id=dc.component_id AND n.visibility='ACTIVE'
                   AND {roles} IN ({markers}) AND NOT EXISTS(SELECT 1 FROM node_profiles bp WHERE bp.uid=n.uid
                   AND json_type(bp.attributes,'$.allowed_views')='array' AND NOT EXISTS(SELECT 1 FROM json_each(bp.attributes,'$.allowed_views') av WHERE av.value=?))""",
                    (entry["domain_id"], view, *admitted_roles, view),
                )
                c.commit()
            summary["seconds"] = round(time.monotonic() - start, 3)
            summaries[view] = summary
            (self.out / (view + "_graph.json")).write_text(
                json.dumps(summary, ensure_ascii=False, indent=2)
            )
            print("VIEW COMPLETE", view, summary["class_root_groups"], flush=True)
            del (
                typed_routes,
                navigation_routes,
                nav_seed_mask,
                nav_ids,
                regulated_ids,
                nav_witness_ids,
            )
            del weak, weak_counts, frontier, live_groups
            del (
                g,
                browse,
                mixed,
                mixorder,
                mixpred,
                mixdepth,
                mixwitness,
                has_terminal,
                triples,
                pred,
                witness,
                cache,
                depth,
            )
        self.meta(
            "database_revision",
            hashlib.sha256(
                dump(
                    {
                        "version": "v1.7.1-review",
                        "baseline": json.loads(
                            (self.inputs / "baseline.json").read_text()
                        ),
                        "inputs": [
                            (str(f.relative_to(self.inputs)), digest_file(f))
                            for f in sorted(self.inputs.rglob("*"))
                            if f.is_file()
                        ],
                        "build_code": [
                            (f.name, digest_file(f))
                            for f in (
                                Path(__file__),
                                Path(__file__).with_name("semantics.py"),
                            )
                        ],
                    }
                ).encode()
            ).hexdigest(),
        )
        self.meta("baseline_release", "v1.6.0")
        self.meta("release", "v1.7.1-review")
        self.meta("review_version", "v1.7.1-review")
        self.meta("usability_indexes_ready", True)
        self.meta("usability_role_counts", dict(role_counts))
        self.meta("nodes", c.execute("SELECT count(*) FROM nodes").fetchone()[0])
        self.meta(
            "usability_view_statistics",
            {
                v: {k: x for k, x in s.items() if k not in ("domains",)}
                for v, s in summaries.items()
            },
        )
        counts = {
            r[0]: r[1]
            for r in c.execute(
                "SELECT visibility,count(*) FROM nodes GROUP BY visibility"
            )
        }
        for key, value in {
            "active_nodes": counts.get("ACTIVE", 0),
            "source_only_nodes": counts.get("SOURCE_ONLY", 0),
            "strict_classification_edges": c.execute(
                "SELECT count(*) FROM edges WHERE status='ACTIVE' AND relation='IS_A'"
            ).fetchone()[0],
            "aliases": c.execute("SELECT count(*) FROM aliases").fetchone()[0],
            "identity_components": c.execute(
                "SELECT count(DISTINCT component_id) FROM nodes"
            ).fetchone()[0],
            "connected_entities": summaries["strict"]["typed_terminal_root_uids"],
            "retained_classification_uids": sum(
                role_counts.get(role, 0) for role in CLASS_ROLES
            ),
            "canonical_domains": len(entries),
            "cycle_check": "PASS: all components in all declared view graphs",
        }.items():
            self.meta(key, value)
        c.execute("PRAGMA analysis_limit=1000")
        c.execute("ANALYZE")
        c.commit()
        return summaries

    def role_reconciliation(self):
        """Replay independently checked nominal roles across the entire source scope.

        Source declarations remain immutable; canonical decisions and superseded
        relation admission are separate, evidenced records.
        """
        rows = self.c.execute("""SELECT r.*,n.data native_data,n.description,n.rank,p.node_kind
          FROM entity_relations r JOIN nodes n ON n.uid=r.subject_uid
          LEFT JOIN node_profiles p ON p.uid=n.uid
          WHERE r.status='ACTIVE' AND r.relation='INSTANCE_OF'
          AND json_extract(r.data,'$.basis') LIKE 'INDEPENDENT_NOMINAL%' ORDER BY r.id""").fetchall()
        counts = collections.Counter()
        ledger = []
        for row in rows:
            native = json.loads(row['native_data'] or '{}')
            declaration = json.loads(row['data'] or '{}')
            prior = row['node_kind'] or role_for_rank(row['rank'])
            # Positive instance profiles are retained unless the independent
            # definition conflicts with an explicit native design declaration.
            decision, reason = nominal_role_decision(native, declaration)
            contradictory_design = (native.get('node_kind') == 'MODEL'
                                    and 'missile system' in native.get('definition', '').casefold())
            if prior == 'INSTANCE' and decision != 'MODEL' and not contradictory_design:
                counts['consistent_instance_relations'] += 1
                continue
            proof = {'basis': 'INDEPENDENT_NOMINAL_ROLE_RECONCILIATION',
                     'source_role': native.get('node_kind', prior), 'prior_role': prior,
                     'native_record_sha256': hashlib.sha256(row['native_data'].encode()).hexdigest(),
                     'original_relation_id': row['id'], 'original_evidence_id': row['evidence_id'],
                     'definition': native.get('definition', row['description']),
                     'declaration': declaration, 'role_basis': reason,
                     'license': 'Retained original source attribution and terms'}
            uri = declaration.get('source_uri', '')
            if decision == 'INSTANCE':
                self.role(row['subject_uid'], decision, proof, 'Retained independent nominal role evidence', uri)
                counts['instance_role_relations_reconciled'] += 1
            elif decision == 'MODEL':
                self.role(row['subject_uid'], decision, proof, 'Retained independent nominal design evidence', uri)
                self.typed(row['subject_uid'], row['object_uid'], 'DESIGN_TYPE_OF', proof,
                           'Retained independent nominal design evidence', uri)
                self.c.execute("UPDATE entity_relations SET status='SUPERSEDED' WHERE id=?", (row['id'],))
                self.change('role_reconciliation', 'entity_relation', row['id'], dict(row),
                            {'status':'SUPERSEDED','normalized_relation':'DESIGN_TYPE_OF'}, proof)
                counts['design_relations_reconciled'] += 1
            else:
                self.c.execute("UPDATE entity_relations SET status='REVIEW' WHERE id=?", (row['id'],))
                self.role(row['subject_uid'], 'UNKNOWN', proof, 'Unresolved independent nominal role evidence', uri)
                self.change('role_reconciliation', 'entity_relation', row['id'], dict(row),
                            {'status':'REVIEW','reason':reason}, proof)
                counts['insufficient_evidence_relations'] += 1
            ledger.append({'relation_id':row['id'],'uid':row['subject_uid'],'prior_role':prior,
                           'decision':decision or 'REVIEW','reason':reason,'proof':proof})
        self.c.commit()
        (self.out/'role_reconciliation_ledger.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2))
        return {'scanned_nominal_relations':len(rows),**dict(counts)}

    def adjudicate_design_grain(self):
        groups = collections.defaultdict(list)
        for line in (self.inputs/'source_facts.jsonl').open():
            row = json.loads(line)
            if row['source'] == 'Independent native product-family definition':
                groups[row['uid']].append(row)
        ledger = []
        for uid, rows in sorted(groups.items()):
            if len({r['role'] for r in rows}) < 2: continue
            role, reason = design_grain_for_claims([r['proof'] for r in rows])
            if role is None:
                raise ValueError('Unadjudicated conflicting design-grain input: '+uid)
            prior = self.c.execute('SELECT node_kind FROM node_profiles WHERE uid=?',(uid,)).fetchone()[0]
            if prior not in ('MODEL','MODEL_FAMILY'):
                raise ValueError('Design-grain input conflicts with a non-design canonical role: '+uid)
            allowed = TYPED_TERMINALS[role]
            marks = ','.join('?' for _ in allowed)
            if self.c.execute(f"SELECT 1 FROM entity_relations WHERE subject_uid=? AND status='ACTIVE' AND relation IN ('DESIGN_TYPE_OF','SERIES_MEMBER_OF','REGULATED_AS','INSTANCE_OF') AND relation NOT IN ({marks}) LIMIT 1",(uid,*allowed)).fetchone():
                raise ValueError('Design-grain correction requires relationship re-adjudication: '+uid)
            proof = {'basis':'INDEPENDENT_DESIGN_GRAIN_RECONCILIATION','role_basis':reason,
                     'original_claims':[r['proof'] for r in rows],
                     'independent_definition_hashes':sorted({r['proof']['independent_definition_sha256'] for r in rows}),
                     'license':'Original source attribution and terms retained'}
            self.role(uid,role,proof,'Retained independent design grain declarations',rows[0]['source_uri'])
            ledger.append({'uid':uid,'prior_role':prior,'canonical_role':role,'reason':reason,'claims':proof['original_claims']})
        self.c.commit()
        (self.out/'design_grain_ledger.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2))
        return {'source_uids_scanned':len(groups),'conflicting_source_uids':len(ledger),
                'changed_roles':sum(x['prior_role']!=x['canonical_role'] for x in ledger)}

    def sync_role_contracts(self):
        """Refresh current role projections without changing graph topology.

        Model/family grain adjudication is confined to role-compatible design
        arcs. Original source/profile snapshots and role histories are retained.
        """
        rows = self.c.execute('SELECT r.uid,r.canonical_role,p.node_kind,p.evidence_id FROM normalization_roles r JOIN node_profiles p ON p.uid=r.uid WHERE r.canonical_role<>p.node_kind OR r.evidence_id<>p.evidence_id').fetchall()
        for row in rows:
            source = self.c.execute('SELECT source_name FROM evidence WHERE evidence_id=? ORDER BY layer LIMIT 1',(row['evidence_id'],)).fetchone()[0]
            self.c.execute('UPDATE normalization_roles SET canonical_role=?,evidence_id=?,source=? WHERE uid=?',
                           (row['node_kind'],row['evidence_id'],source,row['uid']))
        changed_members = self.c.execute('''UPDATE domain_members SET role=(SELECT p.node_kind FROM node_profiles p WHERE p.uid=domain_members.uid)
          WHERE EXISTS(SELECT 1 FROM node_profiles p WHERE p.uid=domain_members.uid AND p.node_kind<>domain_members.role)''').rowcount
        counts = dict(self.c.execute('SELECT '+role_expression('n','p')+",count(*) FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility='ACTIVE' GROUP BY 1"))
        self.meta('usability_role_counts',counts)
        self.meta('database_revision',hashlib.sha256(dump({'version':'v1.7.1-review',
            'baseline':json.loads((self.inputs/'baseline.json').read_text()),
            'inputs':[(str(f.relative_to(self.inputs)),digest_file(f)) for f in sorted(self.inputs.rglob('*')) if f.is_file()],
            'build_code':[(f.name,digest_file(f)) for f in (Path(__file__),Path(__file__).with_name('semantics.py'))]}).encode()).hexdigest())
        self.c.commit()
        return {'refreshed_current_normalization_decisions':len(rows),'refreshed_domain_role_rows':changed_members}

    def run(self, stages):
        self.schema()
        mutated = False
        for stage in stages:
            fingerprint = hashlib.sha256(
                dump(
                    {
                        "code": [
                            (f.name, digest_file(f))
                            for f in (
                                Path(__file__),
                                Path(__file__).with_name("semantics.py"),
                                Path(__file__).with_name("role_contracts.py"),
                            )
                        ],
                        "inputs": [
                            (str(p.relative_to(self.inputs)), digest_file(p))
                            for p in sorted(self.inputs.rglob("*"))
                            if p.is_file()
                        ],
                    }
                ).encode()
            ).hexdigest()
            prior = self.c.execute(
                "SELECT input_sha256 FROM usability_stages WHERE stage=?", (stage,)
            ).fetchone()
            if prior and prior[0] == fingerprint:
                print("SKIP UNCHANGED", stage, flush=True)
                continue
            mutated = True
            print("START", stage, flush=True)
            result = getattr(self, stage)()
            self.c.execute(
                "INSERT OR REPLACE INTO usability_stages VALUES (?,?,?,?)",
                (
                    stage,
                    fingerprint,
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    dump(result),
                ),
            )
            self.c.commit()
            (self.out / (stage + "_summary.json")).write_text(
                json.dumps(result, ensure_ascii=False, indent=2)
            )
            print("COMPLETE", stage, flush=True)
        if self.c.execute(
            "SELECT 1 FROM usability_stages WHERE stage='graphs'"
        ).fetchone() and (not mutated or "graphs" in stages or ('sync_role_contracts' in stages and set(stages).issubset({'adjudicate_design_grain','sync_role_contracts'}))):
            self.meta("usability_indexes_ready", True)
            self.c.commit()
        self.c.close()
