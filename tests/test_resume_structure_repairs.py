"""A resumed build must bind its completed parent and unchanged source stages."""
import hashlib
import json
from pathlib import Path
import sqlite3
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from resume_structure_repairs import PARENT_STAGES, validate_parent_receipt, verify_parent_byte_copy


class CompletedParentBindingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.database = self.root / "parent.sqlite"
        self.fingerprints = {
            "inputs": {"original.json": "a" * 64},
            "code": {"src/fineatlas/core.py": "b" * 64},
            "packaging": {"pyproject.toml": "c" * 64},
        }
        metadata = {
            "release": "v1.11.0rc1", "database_revision": "final-revision",
            "structure_frozen_build_manifest": self.fingerprints,
            "unified_ready": True, "usability_indexes_ready": True,
            "browse_indexes_ready": True, "browse_parent_revision": "source-revision",
            "browse_source_revision": "source-revision",
            "browse_index_revision": "final-revision",
        }
        with sqlite3.connect(self.database) as con:
            con.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)")
            con.executemany("INSERT INTO metadata VALUES(?,?)",
                            [(key, json.dumps(value)) for key, value in metadata.items()])
        (self.root / "started_fingerprints.json").write_text(json.dumps(self.fingerprints))
        (self.root / "build_status.json").write_text(json.dumps(
            {name: {"status": "PASS"} for name in PARENT_STAGES}))
        self.receipt = self.root / "build_complete.json"
        self.row = {
            "schema": "FINEATLAS_STRUCTURE_BUILD_COMPLETE_V1", "complete": True,
            "pass": True, "build_id": "independent-parent-build", "ended_utc": "2026-10-10",
            "database": str(self.database), "release": "v1.11.0rc1",
            "revision": "final-revision", "source_graph_revision": "source-revision",
        }
        self.save_receipt()
        self.integrity = self.root / "parent-integrity.json"
        self.seal = {
            "pass": True, "complete": True, "integrity_pass": True,
            "file_unchanged_during_checks": True, "all_frozen_inputs_and_recipes_checked": True,
            "integrity_check": ["ok"], "database": str(self.database),
            "database_revision": "final-revision", "release": "v1.11.0rc1",
            "bytes": self.database.stat().st_size,
            "sha256": hashlib.sha256(self.database.read_bytes()).hexdigest(),
        }
        self.integrity.write_text(json.dumps(self.seal))

    def save_receipt(self):
        for name in ("started_fingerprints", "build_status"):
            self.row[name + "_sha256"] = hashlib.sha256(
                (self.root / (name + ".json")).read_bytes()).hexdigest()
        self.receipt.write_text(json.dumps(self.row))

    def test_additive_repair_recipe_retains_original_inventory(self):
        new = json.loads(json.dumps(self.fingerprints))
        new["inputs"]["grounded_repairs.json"] = "d" * 64
        new["code"]["src/fineatlas/structure_regression_repairs.py"] = "e" * 64
        row, metadata, seal = validate_parent_receipt(self.database, self.receipt, new, self.integrity)
        self.assertEqual(row["build_id"], "independent-parent-build")
        self.assertTrue(metadata["browse_indexes_ready"])

    def test_changed_original_scope_input_requires_replay(self):
        new = json.loads(json.dumps(self.fingerprints))
        new["inputs"]["original.json"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "Previously executed"):
            validate_parent_receipt(self.database, self.receipt, new, self.integrity)

    def test_incomplete_parent_cannot_be_used_even_with_rehashed_receipt(self):
        states = {name: {"status": "PASS"} for name in PARENT_STAGES}
        states["embed_browse_indexes"]["status"] = "RUNNING"
        (self.root / "build_status.json").write_text(json.dumps(states))
        self.save_receipt()
        with self.assertRaisesRegex(ValueError, "must have completed"):
            validate_parent_receipt(self.database, self.receipt, self.fingerprints, self.integrity)

    def test_actual_cache_revision_must_match_parent(self):
        with sqlite3.connect(self.database) as con:
            con.execute("UPDATE metadata SET value=? WHERE key='browse_source_revision'",
                        (json.dumps("unrelated-source"),))
        with self.assertRaisesRegex(ValueError, "browse revision"):
            validate_parent_receipt(self.database, self.receipt, self.fingerprints, self.integrity)

    def test_changed_parent_stage_evidence_is_rejected(self):
        with (self.root / "build_status.json").open("a") as stream:
            stream.write(" ")
        with self.assertRaisesRegex(ValueError, "Parent build evidence changed"):
            validate_parent_receipt(self.database, self.receipt, self.fingerprints, self.integrity)

    def test_changed_raw_source_cannot_use_unchanged_metadata_and_receipt(self):
        with sqlite3.connect(self.database) as con:
            con.execute("CREATE TABLE source_facts(uid TEXT,definition TEXT)")
            con.execute("INSERT INTO source_facts VALUES('source:1','altered whole-object scope')")
        output = self.root / "copied.sqlite"
        shutil.copy2(self.database, output)
        with self.assertRaisesRegex(ValueError, "independent integrity seal"):
            verify_parent_byte_copy(self.database, output, self.seal)

    def test_independent_copy_matches_sealed_parent_bytes(self):
        output = self.root / "copied.sqlite"
        shutil.copy2(self.database, output)
        self.assertEqual(verify_parent_byte_copy(self.database, output, self.seal), self.seal["sha256"])

    def test_missing_integrity_seal_cannot_be_substituted_by_build_receipt(self):
        self.integrity.write_text(json.dumps(self.row))
        with self.assertRaisesRegex(ValueError, "whole-file hash seal"):
            validate_parent_receipt(self.database, self.receipt, self.fingerprints, self.integrity)


if __name__ == "__main__":
    unittest.main()
