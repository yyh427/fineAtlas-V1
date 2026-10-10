"""A resumed build must bind its completed parent and unchanged source stages."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from resume_structure_repairs import PARENT_STAGES, validate_parent_receipt


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

    def save_receipt(self):
        for name in ("started_fingerprints", "build_status"):
            self.row[name + "_sha256"] = hashlib.sha256(
                (self.root / (name + ".json")).read_bytes()).hexdigest()
        self.receipt.write_text(json.dumps(self.row))

    def test_additive_repair_recipe_retains_original_inventory(self):
        new = json.loads(json.dumps(self.fingerprints))
        new["inputs"]["grounded_repairs.json"] = "d" * 64
        new["code"]["src/fineatlas/structure_regression_repairs.py"] = "e" * 64
        row, metadata = validate_parent_receipt(self.database, self.receipt, new)
        self.assertEqual(row["build_id"], "independent-parent-build")
        self.assertTrue(metadata["browse_indexes_ready"])

    def test_changed_original_scope_input_requires_replay(self):
        new = json.loads(json.dumps(self.fingerprints))
        new["inputs"]["original.json"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "Previously executed"):
            validate_parent_receipt(self.database, self.receipt, new)

    def test_incomplete_parent_cannot_be_used_even_with_rehashed_receipt(self):
        states = {name: {"status": "PASS"} for name in PARENT_STAGES}
        states["embed_browse_indexes"]["status"] = "RUNNING"
        (self.root / "build_status.json").write_text(json.dumps(states))
        self.save_receipt()
        with self.assertRaisesRegex(ValueError, "must have completed"):
            validate_parent_receipt(self.database, self.receipt, self.fingerprints)

    def test_actual_cache_revision_must_match_parent(self):
        with sqlite3.connect(self.database) as con:
            con.execute("UPDATE metadata SET value=? WHERE key='browse_source_revision'",
                        (json.dumps("unrelated-source"),))
        with self.assertRaisesRegex(ValueError, "browse revision"):
            validate_parent_receipt(self.database, self.receipt, self.fingerprints)

    def test_changed_parent_stage_evidence_is_rejected(self):
        with (self.root / "build_status.json").open("a") as stream:
            stream.write(" ")
        with self.assertRaisesRegex(ValueError, "Parent build evidence changed"):
            validate_parent_receipt(self.database, self.receipt, self.fingerprints)


if __name__ == "__main__":
    unittest.main()
