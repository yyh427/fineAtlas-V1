#!/usr/bin/env python3
"""Freeze catalogue configurations after inspecting type and title agreement."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fineatlas.catalogue import canonical_record, inspect_listing, listing_uid
from fineatlas.semantics import role_expression

SOURCE = "Amazon Berkeley Objects reviewed catalogue metadata"
SOURCE_URI = "https://amazon-berkeley-objects.s3.us-east-1.amazonaws.com/archives/abo-listings.tar"
LICENSE_URI = "https://amazon-berkeley-objects.s3.us-east-1.amazonaws.com/LICENSE-CC-BY-4.0.txt"


def digest_file(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            value.update(block)
    return value.hexdigest()


def source_records(archive):
    with tarfile.open(archive) as stream:
        for member in sorted(stream.getmembers(), key=lambda m: m.name):
            if member.isfile() and "/metadata/" in member.name and member.name.endswith(".json.gz"):
                with gzip.open(stream.extractfile(member), "rt", encoding="utf-8") as rows:
                    for line_number, line in enumerate(rows, 1):
                        yield member.name, line_number, json.loads(line)


def prepare(database, archive, rules_path, output, license_path, readme):
    output.mkdir(parents=True, exist_ok=True)
    rules = json.loads(rules_path.read_text())
    if rules["schema"] != "FINEATLAS_CATALOGUE_TYPE_RULES_V1":
        raise ValueError("Unsupported source type rule schema")
    license_text = license_path.read_text()
    if "Creative Commons Attribution 4.0" not in license_text:
        raise ValueError("Official metadata redistribution license missing")
    if "Amazon.com" not in readme.read_text():
        raise ValueError("Official source attribution missing")
    by_type = {row["product_type"]: row for row in rules["rules"]}
    if len(by_type) != len(rules["rules"]):
        raise ValueError("Ambiguous source type rules")
    conn = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    parents = {}
    for rule in by_type.values():
        for uid in [rule["parent_uid"], *[r["parent_uid"] for r in rule.get("refinements", [])], *[r["parent_uid"] for r in rule.get("scope_overrides", [])]]:
            row = conn.execute("SELECT n.uid,n.description,n.data,n.visibility," +
                               role_expression("n", "p") + " role FROM nodes n "
                               "LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?", (uid,)).fetchone()
            if not row or row["visibility"] != "ACTIVE" or row["role"] != "CLASS" or not row["description"]:
                raise ValueError("Type correspondence needs an active defined class: " + uid)
            parents[uid] = {"definition": row["description"],
                            "native_record_sha256": hashlib.sha256(row["data"].encode()).hexdigest()}
    archive_sha = digest_file(archive)
    rules_sha = digest_file(rules_path)
    counts, rejected, existing, existing_fields, seen = Counter(), [], [], [], set()
    destination = output / "living_catalogue_records.jsonl"
    with destination.open("w", encoding="utf-8") as target:
        for member, line, record in source_records(archive):
            counts["source_rows_examined"] += 1
            kinds = record.get("product_type", [])
            kinds = [x.get("value") for x in kinds if isinstance(x, dict)] if isinstance(kinds, list) else []
            chosen = [by_type[k] for k in kinds if k in by_type]
            if not chosen:
                continue
            verdict = inspect_listing(record, chosen[0])
            uid = verdict.get("uid")
            if uid in seen:
                raise ValueError("Source key duplicated: " + uid)
            if uid:
                seen.add(uid)
            if verdict["status"] != "ADMIT_SOURCE_CONFIGURATION":
                counts["review_" + verdict["reason"]] += 1
                rejected.append({**verdict, "member": member, "line": line,
                                 "product_types": kinds, "record_sha256": hashlib.sha256(canonical_record(record)).hexdigest()})
                continue
            old = conn.execute("SELECT data FROM nodes WHERE uid=?", (uid,)).fetchone()
            if old:
                raw = json.loads(old[0])
                old_record = raw.get("native_record")
                if old_record is None or canonical_record(old_record) != canonical_record(record):
                    raise ValueError("Existing source identity changed: " + uid)
                counts["existing_source_uid_preserved"] += 1
                existing.append(uid)
                existing_fields.append({'uid':uid,'native_record':record,
                    'record_sha256':verdict['record_sha256'],'catalogue_paths':verdict['catalogue_paths'],
                    'source_member':member,'source_line':line})
                continue
            proof = {"basis": "NATIVE_TYPE_TITLE_AND_CATALOGUE_SCOPE_AGREE",
                     "license": "CC BY 4.0", "license_uri": LICENSE_URI,
                     "source_uri": SOURCE_URI, "source_archive_sha256": archive_sha,
                     "source_member": member, "source_line": line,
                     "source_record_sha256": verdict["record_sha256"],
                     "rules_sha256": rules_sha, "native_record": record,
                     "identity_scope": "SOURCE_CATALOGUE_CONFIGURATION",
                     "world_model_identity_verified": False, "cross_source_identity_inferred": False,
                     "parents": {u: parents[u] for u in verdict["parent_uids"]},
                     "reviewed_native_product_type": kinds[0],
                     "allowed_views": ["strict", "taxonomy", "membership", "unified"]}
            row = {**verdict, "source": SOURCE, "uri": SOURCE_URI, "proof": proof}
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
            counts["new_" + verdict["domain"]] += 1
            counts["new_source_configurations"] += 1
            counts["refined_type_links"] += len(verdict["refined_parent_uids"])
    conn.close()
    manifest = {"schema": "FINEATLAS_LIVING_CATALOGUE_V1", "source": SOURCE,
                "source_uri": SOURCE_URI, "license": "CC BY 4.0", "license_uri": LICENSE_URI,
                "archive_sha256": archive_sha, "rules_sha256": rules_sha,
                "records_sha256": digest_file(destination), "counts": dict(counts),
                "existing_uids": existing, "existing_source_fields": existing_fields, "new_worldwide_models": 0, "new_instances": 0,
                "images_downloaded": 0, "3d_assets_downloaded": 0,
                "attribution": "Amazon.com; source README and dataset page attribution retained",
                "license_sha256": digest_file(license_path), "readme_sha256": digest_file(readme)}
    (output / "living_catalogue_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "living_catalogue_reviews.json").write_text(json.dumps(rejected, ensure_ascii=False, indent=2) + "\n")
    return manifest


def apply_living_expansion(m, *, input_prefix="living_catalogue", metadata_key="living_catalogue_expansion"):
    if not input_prefix or not input_prefix.replace("_", "").isalnum() or not metadata_key:
        raise ValueError("Explicit catalogue batch namespace required")
    records = m.inputs / (input_prefix + "_records.jsonl")
    if not records.exists():
        return {"status": "not_requested"}
    manifest = json.loads((m.inputs / (input_prefix + "_manifest.json")).read_text())
    if digest_file(records) != manifest["records_sha256"]:
        raise ValueError("Frozen catalogue batch checksum differs")
    counts = Counter()
    with records.open(encoding="utf-8") as record_stream:
        for line in record_stream:
            row = json.loads(line)
            proof = row["proof"]
            native = proof["native_record"]
            if listing_uid(native) != row["uid"] or hashlib.sha256(canonical_record(native)).hexdigest() != proof["source_record_sha256"]:
                raise ValueError("Source configuration identity or payload changed")
            for uid, expected in proof["parents"].items():
                parent = m.c.execute("SELECT data,description FROM nodes WHERE uid=?", (uid,)).fetchone()
                if not parent or hashlib.sha256(parent["data"].encode()).hexdigest() != expected["native_record_sha256"] or parent["description"] != expected["definition"]:
                    raise ValueError("Frozen parent type scope changed")
            existing = m.c.execute("SELECT data FROM nodes WHERE uid=?", (row["uid"],)).fetchone()
            if existing and json.loads(existing[0]).get("source_record_sha256") != proof["source_record_sha256"]:
                raise ValueError("Existing catalogue source UID differs")
            added = m.add_node(row["uid"], row["label"], "CONFIGURATION", row["domain"],
                               row["source"], row["uri"], proof, "Source catalogue configuration; worldwide model identity unconfirmed")
            counts["new_source_configurations"] += added
            evidence = m.evidence(row["source"], row["uri"], proof, "SOURCE_CONFIGURATION_TYPE")
            for uid in row["parent_uids"]:
                m.typed(row["uid"], uid, "CONFIGURATION_TYPE_OF", proof, row["source"], row["uri"])
                counts["configuration_type_links"] += 1
            for value in native.get("item_name", []):
                if isinstance(value, dict) and isinstance(value.get("value"), str):
                    language = value.get("language_tag", "und").replace("_", "-")
                    m.alias(row["uid"], value["value"], row["source"], language, False, evidence)
            fields = {"catalogue": row["catalogue_paths"],
                      "native_product_type": [proof["reviewed_native_product_type"]]}
            for source_key, key in [("brand", "brand"), ("color", "color"), ("material", "material"), ("model_number", "native_model")]:
                fields[key] = sorted({x["value"] for x in native.get(source_key, [])
                                      if isinstance(x, dict) and isinstance(x.get("value"), str)})
            for field, values in fields.items():
                for value in values:
                    m.c.execute("INSERT OR IGNORE INTO source_field_values VALUES(?,?,?,?,?)",
                                (row["uid"], field, value, row["source"], evidence))
            counts["domain_" + row["domain"]] += 1
    for preserved in manifest.get('existing_source_fields', []):
        uid=preserved['uid'];native=preserved['native_record']
        if listing_uid(native)!=uid or hashlib.sha256(canonical_record(native)).hexdigest()!=preserved['record_sha256']:
            raise ValueError('Frozen existing configuration payload differs')
        old=m.c.execute('SELECT data FROM nodes WHERE uid=?',(uid,)).fetchone()
        if not old or canonical_record(json.loads(old[0]).get('native_record'))!=canonical_record(native):
            raise ValueError('Existing configuration source identity changed')
        evidence=m.evidence(SOURCE,SOURCE_URI,{'basis':'Retained native metadata fields only',
            'source_record_sha256':preserved['record_sha256'],'source_archive_sha256':manifest['archive_sha256'],
            'source_member':preserved['source_member'],'source_line':preserved['source_line'],
            'identity_assertion':False,'native_record':native},'SOURCE_CONFIGURATION_FIELDS')
        fields={'catalogue':preserved['catalogue_paths']}
        for source_key,key in [('product_type','native_product_type'),('brand','brand'),('color','color'),('material','material'),('model_number','native_model')]:
            fields[key]=sorted({v['value'] for v in native.get(source_key,[]) if isinstance(v,dict) and isinstance(v.get('value'),str)})
        for field,values in fields.items():
            for value in values:
                m.c.execute('INSERT OR IGNORE INTO source_field_values VALUES(?,?,?,?,?)',(uid,field,value,SOURCE,evidence))
        counts['existing_configurations_field_indexed']+=1
    prior_catalog = m.c.execute("SELECT * FROM source_catalogs WHERE source=?", (SOURCE,)).fetchone()
    if prior_catalog and json.loads(prior_catalog[4]) != manifest:
        m.change("source_catalogue_batches", "source_catalog", SOURCE, dict(prior_catalog),
                 manifest, {"input_prefix": input_prefix, "source_archive_unchanged": prior_catalog[3] == manifest["archive_sha256"],
                            "previous_batch_metadata_preserved": True})
    m.c.execute("INSERT OR REPLACE INTO source_catalogs VALUES(?,?,?,?,?)",
                (SOURCE, SOURCE_URI, "CC BY 4.0; Amazon.com; attribution in frozen source README",
                 manifest["archive_sha256"], json.dumps(manifest, ensure_ascii=False)))
    m.meta(metadata_key, manifest)
    m.c.commit()
    return dict(counts)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "archive", "rules", "output", "license", "readme"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(prepare(args.database, args.archive, args.rules, args.output,
                             args.license, args.readme), indent=2), flush=True)
