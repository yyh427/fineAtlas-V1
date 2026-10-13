"""The new navigation contract cannot excuse bad SDK or database receipts."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

import fineatlas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("native755_installer", ROOT / "scripts/download_single.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class NativeDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite"
        modules = Path(fineatlas.__file__).resolve().parent
        signatures = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in modules.glob("*.py")}
        self.metadata = {
            "release": "fixture", "database_revision": "r" * 64,
            "default_relation_view": "unified", "native755_ready": True,
            "searchable755_ready": True, "unified_ready": True,
            "searchable755_scope_rules": "grounded-mixed-range-v1",
            "schema": "FINEATLAS_SINGLE_DB_V1",
            "supported_relation_views": ["strict", "taxonomy", "membership", "unified"],
            "repair_code_commit": "accepted-core",
            "repair_sdk_manifest": {k: v for k, v in signatures.items()
                                    if k != "model_display.py"},
            "browse_index_revision": "preserved-old-browse",
        }
        self.manifest = {
            "release": "fixture", "database_revision": "r" * 64,
            "default_relation_view": "unified", "sdk_version": fineatlas.__version__,
            "supported_relation_views": self.metadata["supported_relation_views"],
            "navigation_interface": "scope_candidates",
            "scope_rules": "grounded-mixed-range-v1", "core_code_commit": "accepted-core",
            "sdk_additions": {"model_display.py": signatures["model_display.py"]},
        }

    def tearDown(self):
        self.temp.cleanup()

    def write_metadata(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT)")
            connection.execute("DELETE FROM metadata")
            connection.executemany("INSERT INTO metadata VALUES(?,?)",
                                   [(k, json.dumps(v)) for k, v in self.metadata.items()])

    def test_pinned_mixed_scope_can_preserve_old_browse_receipt(self):
        self.write_metadata()
        installer.verify_revision(self.path, self.manifest)
        bad = copy.deepcopy(self.manifest)
        bad["navigation_interface"] = "legacy_browse"
        with self.assertRaises(RuntimeError):
            installer.verify_revision(self.path, bad)

    def test_revision_and_core_receipts_are_required(self):
        self.write_metadata()
        for key in ("database_revision", "core_code_commit"):
            bad = copy.deepcopy(self.manifest)
            bad[key] = "wrong"
            with self.assertRaises(RuntimeError):
                installer.verify_revision(self.path, bad)

    def test_extra_display_module_hash_and_inventory_are_checked(self):
        self.write_metadata()
        for additions in ({}, {"model_display.py": "0" * 64},
                          {**self.manifest["sdk_additions"], "__init__.py": "0" * 64}):
            bad = copy.deepcopy(self.manifest)
            bad["sdk_additions"] = additions
            with self.assertRaises(RuntimeError):
                installer.verify_revision(self.path, bad)

    def test_legacy_database_still_requires_matching_browse_cache(self):
        self.metadata["native755_ready"] = False
        self.write_metadata()
        with self.assertRaisesRegex(RuntimeError, "incomplete/stale"):
            installer.verify_revision(self.path, self.manifest)


if __name__ == "__main__":
    unittest.main()
