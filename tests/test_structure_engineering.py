"""Native grouping cannot silently assert cross-source identity or scope."""
import json
from pathlib import Path
import tempfile
import unittest

from fineatlas.structure_engineering import (
    checked_epa_membership, fgvc_annotations, name_only_scope_conflict,
)


class StructureEngineeringTests(unittest.TestCase):
    def annotations(self, root):
        for split in ("train", "val", "test"):
            values = {"variant": ["707-1", "707-2"],
                      "family": ["Author group", "Author group"],
                      "manufacturer": ["Maker", "Maker"]}
            for field, names in values.items():
                (root / f"images_{field}_{split}.txt").write_text(
                    "".join(f"{split}{i} {name}\n" for i, name in enumerate(names)))

    def test_native_author_membership_does_not_guess_family_from_model_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.annotations(root)
            cohort = fgvc_annotations(root)
            self.assertEqual(cohort["record_count"], 6)
            self.assertEqual({r["family"] for r in cohort["hierarchy"]}, {"Author group"})

    def test_incompatible_native_annotation_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.annotations(root)
            (root / "images_family_val.txt").write_text("val0 Different scope\nval1 Author group\n")
            with self.assertRaisesRegex(ValueError, "incompatible"):
                fgvc_annotations(root)

    def test_native_duplicate_ids_and_incomplete_field_joins_are_rejected(self):
        for mode in ("duplicate", "missing"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.annotations(root)
                (root / "images_variant_val.txt").write_text(
                    "val0 707-1\nval0 707-2\n" if mode == "duplicate" else "val0 707-1\n")
                with self.assertRaises(ValueError):
                    fgvc_annotations(root)

    def epa(self):
        raw = dict(id="42", year="2012", make="Maker", model="Sport Model", baseModel="Model")
        variant = dict(source="epa", rank="model_variant", label="Maker Sport Model")
        base = dict(source="epa", rank="model", label="Maker Model")
        return raw, variant, base, [dict(raw), dict(raw)]

    def test_native_epa_reference_requires_literal_fields_and_same_source(self):
        args = self.epa()
        self.assertEqual(checked_epa_membership(*args)["baseModel"], "Model")
        for mode in ("source", "grain", "label", "missing", "evidence"):
            raw, variant, base, evidence = self.epa()
            if mode == "source":
                base["source"] = "wikidata"
            elif mode == "grain":
                base["rank"] = "manufacturer"
            elif mode == "label":
                base["label"] = "Maker"
            elif mode == "missing":
                raw.pop("baseModel")
            else:
                evidence[0]["baseModel"] = "Another Model"
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                checked_epa_membership(raw, variant, base, evidence)

    def bridge(self):
        return dict(source="faa", data=json.dumps({"alignment_type": "STRUCTURED_IDENTITY_EQUIVALENCE"}))

    def test_role_difference_alone_does_not_split_proven_identity(self):
        left, right = dict(source="faa", role="MODEL"), dict(source="wikidata", role="MODEL_FAMILY")
        bridge = self.bridge()
        result = name_only_scope_conflict(bridge, left, right)
        self.assertEqual(result["world_identity_status"], "REVIEW")
        self.assertFalse(result["asserted_inequality"])
        for proof in ({"alignment_type": "SOURCE_ID_EQUIVALENCE"},
                      {"alignment_type": "STRUCTURED_IDENTITY_EQUIVALENCE", "independent_source_crosswalk": {"source_uri": "https://authority.example/crosswalk", "source_ids": ["a", "b"]}},
                      {"alignment_type": "STRUCTURED_IDENTITY_EQUIVALENCE", "reviewed_scope_equivalence": {"review_id": "independent-review-1"}}):
            bridge["data"] = json.dumps(proof)
            self.assertIsNone(name_only_scope_conflict(bridge, left, right))

    def test_same_scope_role_correction_keeps_existing_assertion(self):
        # The reviewed OEM grain corrects CLASS to MODEL before evaluating the
        # original bridge; equal roles do not create a new equivalence claim.
        bridge = self.bridge()
        bridge['data'] = json.dumps({'alignment_type': 'STRUCTURED_IDENTITY_EQUIVALENCE',
            'reviewed_scope_equivalence': {'evidence_id': 'frozen-oem-scope-review'}})
        self.assertIsNone(name_only_scope_conflict(bridge,
            dict(source="epa", role="MODEL"), dict(source="wikidata", role="MODEL")))

    def test_equal_roles_do_not_prove_same_named_model_identity(self):
        self.assertIsNotNone(name_only_scope_conflict(self.bridge(),
            dict(source="epa", role="MODEL"), dict(source="wikidata", role="MODEL")))


if __name__ == "__main__":
    unittest.main()
