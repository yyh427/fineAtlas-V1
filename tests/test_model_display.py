"""Compact presentation must preserve real candidate choices and ambiguity."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from fineatlas import __version__
from fineatlas.experiment import FineAtlasExperimentTool
from fineatlas.model_display import simple_feedback
from fineatlas.task_contract import RunConfig
import test_native755_contract

spec = importlib.util.spec_from_file_location(
    "compact_navigation", Path(__file__).resolve().parents[1] / "scripts/navigate.py")
navigate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(navigate)


class ModelDisplayTests(unittest.TestCase):
    setUp = test_native755_contract.NativeContractTest.setUp
    tearDown = test_native755_contract.NativeContractTest.tearDown
    prepare = test_native755_contract.NativeContractTest.prepare

    def test_compact_feedback_retains_choices_and_separates_same_names(self):
        self.prepare()
        config = RunConfig(str(self.path), "fixture-revision", __version__, "fixture-commit")
        with FineAtlasExperimentTool(config) as tool:
            result = tool.query("river/outdoor")
            choices = tool.allowed_choices(result)
            compact = simple_feedback(result)
            self.assertTrue(choices)
            for choice in choices:
                self.assertIn(choice, compact)
            for hidden in ("world_mapping=", "scope=", "DEPICTS_TYPE", "cat:1", "source_unit="):
                self.assertNotIn(hidden, compact)
            self.assertEqual(tool.allowed_choices(result), choices)
            self.assertTrue(result["candidates"][0].get("mapping_statuses"))
        duplicate = {"candidates": [{"label": "same", "handle": "a"},
                                     {"label": "same", "handle": "b"}]}
        self.assertEqual(len(simple_feedback(duplicate).splitlines()), 2)

    def test_jsonl_default_is_simple_and_optional_diagnostics_keep_contract(self):
        self.prepare()
        config = RunConfig(str(self.path), "fixture-revision", __version__, "fixture-commit")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requests, output, diagnostics = (root / name for name in ("in", "out", "audit"))
            requests.write_text(json.dumps({"session_id": "s", "request_id": "q",
                                           "action": "query", "query": "river/outdoor"}) + "\n")
            navigate.run_requests(config, requests, output, diagnostics)
            model = json.loads(output.read_text())
            backend = json.loads(diagnostics.read_text())["result"]
            self.assertTrue(model["allowed_choices"])
            self.assertNotIn("world_mapping", model["feedback"])
            self.assertTrue(backend["candidates"][0]["mapping_statuses"])
            with self.assertRaises(ValueError):
                navigate.run_requests(config, requests, requests)
            requests.write_text(json.dumps({"session_id": "s", "request_id": "q",
                                           "action": "query", "query": "river/outdoor",
                                           "class_id": "1"}) + "\n")
            with self.assertRaises(ValueError):
                navigate.run_requests(config, requests, output)


if __name__ == "__main__":
    unittest.main()
