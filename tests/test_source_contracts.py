"""Counterexamples from retained source meanings, without a GPU or live network."""
import json
import sqlite3
import unittest

from fineatlas.structure_source_contracts import own_subject_genus, own_family_scope, locate, _locator


class SourceContractsTest(unittest.TestCase):
    def test_named_argument_is_not_genus(self):
        self.assertEqual(own_subject_genus("prototype fighter aircraft, licence-built version of the Bristol Bulldog", "Nakajima J.S.S.F."), ("aircraft", "wordnet31:02689427-n"))
        self.assertIsNone(own_subject_genus("proposed F-35 Canadian-service model by Lockheed Martin", "CF-35 Lightning II"))

    def test_qualifier_not_architectural_genus(self):
        self.assertEqual(own_subject_genus("The SPARC Enterprise series is a range of UNIX server computers based on the SPARC V9 architecture.", "SPARC Enterprise"), ("computers", "wordnet31:03086983-n"))
        self.assertIsNone(own_subject_genus("The Solid State Logic SL 4000 is a series of large-format analogue mixing consoles designed by SSL.", "Solid State Logic SL 4000"))

    def test_polysemous_and_coordinated_heads_review(self):
        self.assertIsNone(own_subject_genus("The BYD B series are a line of battery electric buses produced by BYD.", "BYD B series"))
        self.assertIsNone(own_subject_genus("The Foday Explorer is a series of compact and midsize SUVs manufactured by Foday.", "Foday Explorer"))
        self.assertIsNone(own_subject_genus("The West Point Treatment Plant is a major wastewater treatment plant in Seattle.", "West Point Treatment Plant"))

    def test_subject_binding_and_purpose(self):
        self.assertIsNone(own_subject_genus("The unrelated article is a computer.", "Subject X"))
        self.assertIsNone(own_subject_genus("An engine for aircraft.", "Engine"))
        self.assertIsNone(own_subject_genus("scale model aircraft", "Toy"))
        self.assertIsNone(own_subject_genus("a computer architecture", "Architecture"))

    def test_label_packaging_negation_and_mentions_are_not_types(self):
        examples = ["Foo is not an aircraft", "Foo is not a car", "Foo is not a computer",
                    "Foo is possibly a car", "Foo is an alleged computer", "Foo is a book about aircraft",
                    "Foo is a museum displaying aircraft", "Foo is a game named Cars",
                    "Foo's designer says it is an aircraft", "Foo that flies is an aircraft",
                    "Native source label: Foo aircraft; subject definition: A software simulator for pilots."]
        for text in examples:
            self.assertIsNone(own_subject_genus(text, "Foo aircraft" if text.startswith("Native") else "Foo"), text)

    def test_native_parent_scope_cardinality(self):
        self.assertIsNone(own_subject_genus("Foo is a three-wheeled automobile", "Foo"))
        self.assertIsNone(own_subject_genus("Foo is a three-wheeled kit car", "Foo"))
        self.assertIsNone(own_subject_genus("Foo is a car with three wheels", "Foo"))
        self.assertIsNone(own_subject_genus("Foo is a car which is a toy", "Foo"))
        self.assertIsNone(own_subject_genus("Foo is a car that is fictional", "Foo"))
        self.assertEqual(own_subject_genus("Foo is a car that appears in a film", "Foo"), ("car", "wordnet31:02961779-n"))
        self.assertEqual(own_subject_genus("Foo is a four-wheeled automobile", "Foo"), ("automobile", "wordnet31:02961779-n"))

    def test_coordinated_scope_and_subject_family(self):
        self.assertIsNone(own_subject_genus("Chromebook is a line of laptops, desktops, tablets and all-in-one computers that run ChromeOS", "Chromebook"))
        self.assertIsNone(own_subject_genus("Foo is a line of laptops and desktop computers", "Foo"))
        self.assertFalse(own_family_scope("The MacBook Neo is a laptop in the MacBook family developed by Apple", "MacBook Neo"))
        self.assertFalse(own_family_scope("Foo is a single aircraft developed by a family company", "Foo"))
        self.assertTrue(own_family_scope("The SPARC Enterprise series is a range of UNIX server computers based on the SPARC architecture", "SPARC Enterprise"))
        self.assertTrue(own_family_scope("1969 utility aircraft family with two turboprop engines", "PA-31T Cheyenne"))

    def test_locator_survives_id_and_status_but_rejects_payload_drift(self):
        c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
        c.execute("CREATE TABLE entity_relations(id INTEGER,subject_uid TEXT,object_uid TEXT,relation TEXT,status TEXT,source TEXT,evidence_id TEXT,data TEXT)")
        row = {"id": 1, "subject_uid": "source:x", "object_uid": "source:y", "relation": "DESIGN_TYPE_OF", "status": "ACTIVE", "source": "old-proof", "evidence_id": "e", "data": json.dumps({"native": "untouched"})}
        locator = _locator("entity_relations", row)
        c.execute("INSERT INTO entity_relations VALUES (?,?,?,?,?,?,?,?)", tuple(row.values()))
        c.execute("UPDATE entity_relations SET id=101,status='SOURCE_SCOPE_REVIEW'")
        self.assertEqual(locate(c, "entity_relations", locator)["id"], 101)
        c.execute("UPDATE entity_relations SET data='{}'")
        with self.assertRaises(ValueError): locate(c, "entity_relations", locator)


if __name__ == "__main__":
    unittest.main()
