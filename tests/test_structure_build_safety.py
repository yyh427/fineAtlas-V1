"""Independent filesystem safety scenarios; no production files or GPU."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from structure_build_safety import inventory_code, protect_output, require_unoptimized
import structure_build_safety as safety


class BuildSafetyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        self.production = self.root / "production.sqlite"
        self.checkpoint = self.root / "source.sqlite"
        self.accepted = self.root / "accepted.sqlite"
        with sqlite3.connect(self.production) as c:
            c.execute("CREATE TABLE metadata(key TEXT,value TEXT)")
            c.execute("INSERT INTO metadata VALUES ('database_revision','same-revision')")
        self.checkpoint.write_bytes(b"frozen source checkpoint")
        self.accepted.write_bytes(b"accepted immutable source")
        self.candidate = self.root / "candidate.sqlite"
        shutil.copyfile(self.production, self.candidate)
        self.original = {p: p.read_bytes() for p in (self.production, self.checkpoint, self.accepted)}
        self.registry = {"schema": "FINEATLAS_PROTECTED_PATHS_V1", "files": [
            {"path": str(p), "role": role, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p, role in ((self.production, "PRODUCTION"), (self.checkpoint, "SOURCE_CHECKPOINT"),
                            (self.accepted, "ACCEPTED_SOURCE"))]}
        self.write_registry()

    def write_registry(self):
        (self.inputs / "structure_protected_paths.json").write_text(json.dumps(self.registry))

    def tearDown(self):
        self.temp.cleanup()

    def unchanged(self):
        for path, content in self.original.items():
            self.assertEqual(path.read_bytes(), content)

    def test_independent_identical_copy_is_allowed_without_writes(self):
        result = protect_output(self.candidate, self.inputs, self.production)
        self.assertTrue(result["distinct_inode"])
        self.assertFalse(self.candidate.samefile(self.production))
        self.assertEqual(self.candidate.read_bytes(), self.production.read_bytes())
        self.unchanged()

    def test_every_registered_role_and_resolved_alias_are_protected(self):
        for record in self.registry["files"]:
            with self.assertRaises(ValueError):
                protect_output(Path(record["path"]), self.inputs)
        # A different string resolving to the same file does not create a copy.
        with self.assertRaises(ValueError):
            protect_output(self.root / "inputs" / ".." / "production.sqlite", self.inputs)
        self.unchanged()

    def test_hardlinks_and_symlinks_of_every_protected_role_are_rejected(self):
        for index, record in enumerate(self.registry["files"]):
            for kind in ("hard", "sym"):
                alias = self.root / (kind + str(index) + ".sqlite")
                if kind == "hard":
                    os.link(record["path"], alias)
                else:
                    alias.symlink_to(record["path"])
                with self.assertRaises(ValueError):
                    protect_output(alias, self.inputs, self.production)
        self.unchanged()

    def test_deceptive_baseline_copy_and_copied_metadata_are_rejected(self):
        fake = self.root / "fake-baseline.sqlite"
        shutil.copyfile(self.production, fake)
        for target in (self.production, self.candidate):
            with self.assertRaises(ValueError):
                protect_output(target, self.inputs, fake)
        metadata_only = self.root / "metadata-only.sqlite"
        with sqlite3.connect(metadata_only) as c:
            c.execute("CREATE TABLE metadata(key TEXT,value TEXT)")
            c.execute("INSERT INTO metadata VALUES ('database_revision','same-revision')")
            c.execute("CREATE TABLE pretend_independent_source(uid TEXT)")
        with self.assertRaises(ValueError):
            protect_output(self.candidate, self.inputs, metadata_only)
        self.unchanged()

    def test_baseline_alias_may_identify_the_actual_production_inode(self):
        alias = self.root / "production-alias.sqlite"
        alias.symlink_to(self.production)
        protect_output(self.candidate, self.inputs, alias)
        self.unchanged()

    def test_additional_protected_inode_is_not_an_output(self):
        extra = self.root / "another-owner.sqlite"
        extra.write_bytes(b"another owner's accepted source")
        alias = self.root / "extra-hardlink.sqlite"
        os.link(extra, alias)
        with self.assertRaises(ValueError):
            protect_output(alias, self.inputs, self.production, (extra,))
        self.assertEqual(extra.read_bytes(), b"another owner's accepted source")
        self.unchanged()

    def test_missing_target_registry_missing_source_and_invalid_registry_fail(self):
        with self.assertRaises(ValueError):
            protect_output(self.root / "not-pre-copied.sqlite", self.inputs)
        original = self.inputs / "structure_protected_paths.json"
        original.unlink()
        with self.assertRaises(ValueError):
            protect_output(self.candidate, self.inputs)
        self.write_registry()
        self.registry["files"][0]["path"] = "production.sqlite"
        self.write_registry()
        with self.assertRaises(ValueError):
            protect_output(self.candidate, self.inputs)
        self.registry["files"][0]["path"] = str(self.production)
        self.registry["files"][0]["sha256"] = "0" * 64
        self.write_registry()
        with self.assertRaises(ValueError):
            protect_output(self.candidate, self.inputs)
        self.unchanged()

    def test_registry_and_output_alias_changes_during_hash_are_rejected(self):
        digest = safety._digest_file
        alias = self.root / "changing-output.sqlite"
        alias.symlink_to(self.candidate)
        def swap_alias(path):
            value = digest(path)
            if path == self.production:
                alias.unlink()
                alias.symlink_to(self.production)
            return value
        with patch.object(safety, "_digest_file", side_effect=swap_alias):
            with self.assertRaisesRegex(ValueError, "output inode changed"):
                protect_output(alias, self.inputs, self.production)
        def change_registry(path):
            value = digest(path)
            if path == self.production:
                registry = self.inputs / "structure_protected_paths.json"
                registry.write_bytes(registry.read_bytes() + b"\n")
            return value
        with patch.object(safety, "_digest_file", side_effect=change_registry):
            with self.assertRaisesRegex(ValueError, "registry changed"):
                protect_output(self.candidate, self.inputs, self.production)
        self.unchanged()

    def test_missing_registered_file_is_not_ignored(self):
        self.registry["files"][1]["path"] = str(self.root / "missing-source.sqlite")
        self.write_registry()
        with self.assertRaisesRegex(ValueError, "must already exist"):
            protect_output(self.candidate, self.inputs, self.production)
        self.unchanged()

    def test_code_inventory_matches_existing_recipe_and_detects_change(self):
        tree = self.root / "code"
        for directory in ("src/fineatlas", "scripts", "configs"):
            (tree / directory).mkdir(parents=True)
        expected_content = {"src/fineatlas/sdk.py": b"x = 1\n", "scripts/a.py": b"print(1)\n",
                            "configs/rules.json": b'{}', "configs/nested/other.json": b'[]'}
        for name, content in expected_content.items():
            path = tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        (tree / "pyproject.toml").write_bytes(b"[project]\nname='synthetic'\n")
        (tree / "scripts" / "ignore.pyc").write_bytes(b"generated cache")
        (tree / "configs" / "ignore.txt").write_bytes(b"unrelated text")
        before = inventory_code(tree)
        self.assertEqual(before["code"], {name: hashlib.sha256(content).hexdigest()
                                          for name, content in expected_content.items()})
        self.assertEqual(before["packaging"], {"pyproject.toml": hashlib.sha256(
            (tree / "pyproject.toml").read_bytes()).hexdigest()})
        (tree / "src/fineatlas/sdk.py").write_bytes(b"x = 2\n")
        self.assertNotEqual(inventory_code(tree), before)

    def test_optimized_python_is_explicitly_rejected(self):
        require_unoptimized()
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        command = [sys.executable, "-B", "-O", "-c",
                   "import sys; sys.path.insert(0, " + repr(str(scripts)) + "); "
                   "from structure_build_safety import require_unoptimized; require_unoptimized()"]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Optimized Python is forbidden", result.stderr)


if __name__ == "__main__":
    unittest.main()
