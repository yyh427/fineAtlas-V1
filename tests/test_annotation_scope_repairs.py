"""Exact source typography must not manufacture biological or design identity."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sqlite3

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_annotation_scope_repairs.py"
spec = importlib.util.spec_from_file_location("annotation_scope", SCRIPT)
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


class ExactAnnotationScopeTest(unittest.TestCase):
    def species(self, uid, name, rank="species"):
        return {"uid": uid, "row": {"Taxon_rank": rank, "English_name_AviList": name,
                                  "English_name_Clements_v2025": name, "English_name_BirdLife_v10": name}}

    def test_possessive_typography_preserves_name_letters(self):
        self.assertEqual(scope.typography_key("Forster’s Tern"), scope.typography_key("Forsters_Tern"))
        self.assertNotEqual(scope.typography_key("Forster Tern"), scope.typography_key("Forsters Tern"))
        self.assertNotEqual(scope.typography_key("Williams Warbler"), scope.typography_key("William Warbler"))

    def test_case_spacing_hyphenation_and_fullwidth_are_typography_only(self):
        self.assertEqual(scope.typography_key("ＳＡＹ’s Phoebe"), scope.typography_key("Says-Phoebe"))
        self.assertNotEqual(scope.typography_key("White Pelican"), scope.typography_key("American White Pelican"))

    def test_full_species_name_is_unique_and_ranked(self):
        index, _ = scope.checklist_index([self.species("species:1", "Forster's Tern"), self.species("genus:1", "Tern", "genus")])
        self.assertEqual(scope.exact_candidate("Forsters Tern", index), ("species:1", None))
        self.assertIsNone(scope.exact_candidate("Tern", index))

    def test_ambiguous_name_collision_never_selects_first_species(self):
        index, _ = scope.checklist_index([self.species("species:1", "Test Bird"), self.species("species:2", "Test Bird")])
        self.assertIsNone(scope.exact_candidate("Test Bird", index))

    def test_historical_split_short_name_and_genus_scope_are_not_narrowed(self):
        index, _ = scope.checklist_index([self.species("species:1", "Northern House Wren"),
                                         self.species("species:2", "Northern Yellow Warbler"),
                                         self.species("species:3", "Northern Cardinal")])
        for label in ("House Wren", "Yellow Warbler", "Cardinal", "Sayornis", "Mockingbird"):
            self.assertIsNone(scope.exact_candidate(label, index), label)

    def test_reviewed_full_spelling_alias_is_explicit_and_bounded(self):
        index, _ = scope.checklist_index([self.species("species:1", "Arctic Tern")])
        aliases = {scope.typography_key("Artic Tern"): {"primary_name": "Arctic Tern"}}
        self.assertEqual(scope.exact_candidate("Artic Tern", index, aliases)[0], "species:1")
        self.assertIsNone(scope.exact_candidate("Artic Tern", index))
        self.assertIsNone(scope.exact_candidate("Artic Bird", index, aliases))

    def test_crj_family_and_variant_join_use_image_identifiers(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for split, count in (("train", 34), ("val", 33), ("test", 33)):
                fields = {field: [] for field in ("variant", "family", "manufacturer")}
                for variant in ("CRJ-200", "CRJ-700", "CRJ-900"):
                    for number in range(count):
                        image_id = split + "_" + variant + "_" + str(number)
                        fields["variant"].append(image_id + " " + variant)
                        fields["family"].append(image_id + " " + ("CRJ-200" if variant == "CRJ-200" else "CRJ-700"))
                        fields["manufacturer"].append(image_id + " Canadair")
                for field, rows in fields.items():
                    # Deliberate different line order prevents accidental row-number joins.
                    if field == "family":
                        rows.reverse()
                    (root / ("images_" + field + "_" + split + ".txt")).write_text("\n".join(rows) + "\n")
            cohort = scope.source_annotations(root)
            self.assertEqual(len(cohort["records"]), 300)
            crj900 = [row for row in cohort["source_hierarchy"] if row["variant"] == "CRJ-900"][0]
            self.assertEqual(crj900["family"], "CRJ-700")
            family = root / "images_family_train.txt"
            family.write_text(family.read_text().replace("CRJ-700", "CRJ-900", 1))
            with self.assertRaisesRegex(ValueError, "cohort differs"):
                scope.source_annotations(root)

    def test_ott_taxon_snapshot_rejects_identifier_rank_and_version_drift(self):
        snapshot = {"version": "3.7draft3", "native_taxonomy_sha256": scope.OTT_SHA,
                    "records": [{"uid": uid, "name": name, "rank": rank, "parent_uid": parent,
                                 "sourceinfo": external_id, "raw_line_sha256": "retained-row-sha"}
                                for uid, name, rank, parent, external_id in (
                                    ("509187", "Centramoebida", "order", "5246821", "ncbi:555407"),
                                    ("5246821", "Longamoebia", "order", "673585", "ncbi:1485168"),
                                    ("673585", "Discosea", "class", "1064655", "ncbi:555280"))]}
        self.assertEqual(scope.validate_ott_records(snapshot)["509187"]["name"], "Centramoebida")
        for field, value in (("rank", "class"), ("name", "Wrong scope"), ("sourceinfo", "ncbi:1")):
            bad = copy.deepcopy(snapshot)
            bad["records"][0][field] = value
            with self.assertRaises(ValueError):
                scope.validate_ott_records(bad)
        snapshot["version"] = "3.7"
        with self.assertRaises(ValueError):
            scope.validate_ott_records(snapshot)

    def historical_fixture(self, folder, *, changed_scope=False, different_component=False):
        root = Path(folder)
        db = root / "db.sqlite"
        with sqlite3.connect(db) as c:
            c.executescript("""CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,rank TEXT,component_id INTEGER,data TEXT,visibility TEXT);
              CREATE TABLE dataset_targets(dataset TEXT,class_id TEXT,label TEXT,target_uid TEXT,decision_status TEXT,identity_basis TEXT,granularity_basis TEXT,evidence_ids TEXT,provenance TEXT);
              CREATE TABLE dataset_mapping_checks(dataset TEXT,class_id TEXT,status TEXT,reason TEXT,proof TEXT);""")
            c.executemany("INSERT INTO nodes VALUES(?,?,?,?,?,?)", [("species:1", "Testus birdus", "species", 1, "{}", "ACTIVE"),
                                                                   ("annotation:1", "Old complete bird name", "species", 2 if different_component else 1, "{}", "ACTIVE")])
            c.execute("INSERT INTO dataset_targets VALUES('cub200','99','Old complete bird name','annotation:1','VERIFIED','','','[]','{}')")
            c.execute("INSERT INTO dataset_mapping_checks VALUES('cub200','99','ANNOTATION_SCOPE_REVIEW','','{}')")
        record = self.species("species:1", "New complete bird name")
        record.update(source_uri="https://example.org/primary-checklist", source_sha256="frozen-checklist-sha")
        record["row"]["Scientific_name"] = "Testus birdus"
        checklist = root / "checklist.json"
        checklist.write_text(json.dumps([record]))
        evidence = root / "evidence.json"
        evidence.write_text(json.dumps({"reviewed_full_name_bridges": [{"class_id": "99", "annotation_label": "Old complete bird name",
                              "primary_name": "New complete bird name", "required_scientific_name": "Testus birdus",
                              "biological_scope_changed": changed_scope,
                              "source_evidence": [{"source_uri": "https://example.org/author-name-correction",
                                                   "finding_paraphrase": "Explicit complete English-name rename without species change"}]}]}))
        return db, checklist, evidence, root / "output"

    def test_documentary_complete_name_bridge_preserves_existing_species_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            summary = scope.prepare_historical_aliases(*self.historical_fixture(folder))
            self.assertEqual(summary["documented_full_name_repairs"], 1)
            self.assertEqual(summary["species_scope_changes"], 0)
            self.assertEqual(summary["new_world_identity_merges"], 0)

    def test_documentary_old_name_cannot_pick_one_daughter_of_a_split(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "unchanged biological scope"):
                scope.prepare_historical_aliases(*self.historical_fixture(folder, changed_scope=True))

    def test_historical_name_cannot_manufacture_a_cross_source_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "cannot create an identity"):
                scope.prepare_historical_aliases(*self.historical_fixture(folder, different_component=True))


if __name__ == "__main__":
    unittest.main()
