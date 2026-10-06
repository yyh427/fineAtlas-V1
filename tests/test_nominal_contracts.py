"""Nominal grounding: modern native kinds, homonyms and design-role exclusion."""

import json, sqlite3, unittest
from fineatlas.nominal import WordNetKinds


class NominalContractsTest(unittest.TestCase):
    def test_native_kind_requires_artifact_scope_and_generic_role(self):
        c = sqlite3.connect(":memory:")
        c.executescript(
            "CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,rank TEXT,description TEXT,data TEXT,visibility TEXT,component_id INTEGER);CREATE TABLE aliases(alias TEXT,uid TEXT);CREATE TABLE edges(child_uid TEXT,parent_uid TEXT,status TEXT,relation TEXT);CREATE TABLE node_profiles(uid TEXT,node_kind TEXT);"
        )
        for uid, label, rank, definition, comp in [
            ("wordnet31:artifact", "artifact", "class", "Physical object", 1),
            ("native:smart", "Smartwatch", "class", "A wearable electronic device", 2),
            ("native:brand", "Brand Smartwatch", "", "Manufacturer model family", 3),
            (
                "native:abstract",
                "Smartwatch concept",
                "class",
                "A nonphysical account",
                4,
            ),
        ]:
            c.execute(
                "INSERT INTO nodes VALUES(?,?,?,?,?,?,?)",
                (uid, label, rank, definition, "{}", "ACTIVE", comp),
            )
        c.executemany(
            "INSERT INTO aliases VALUES(?,?)",
            [
                ("artifact", "wordnet31:artifact"),
                ("smartwatch", "native:smart"),
                ("smartwatch", "native:brand"),
                ("smartwatch", "native:abstract"),
            ],
        )
        c.executemany(
            "INSERT INTO edges VALUES(?,?,?,?)",
            [
                ("native:smart", "wordnet31:artifact", "ACTIVE", "IS_A"),
                ("native:brand", "wordnet31:artifact", "ACTIVE", "IS_A"),
            ],
        )
        k = WordNetKinds(c, include_native=True)
        # An old named-design alias may be a model year. It cannot be an
        # object-kind parent for a sentence ending in that same year.
        c.execute("INSERT INTO aliases VALUES('2010','native:smart')")
        self.assertFalse(k.candidates('2010'))
        self.assertEqual(k.unique_artifact("smartwatch"), "native:smart")
        self.assertEqual(k.resolve_head("small GPS smartwatch"), "native:smart")
        c.execute("INSERT INTO nodes VALUES('wordnet31:water','water supply','class','A water supply facility','{}','ACTIVE',6)")
        c.execute("INSERT INTO aliases VALUES('water','wordnet31:water')")
        c.execute("INSERT INTO edges VALUES('wordnet31:water','wordnet31:artifact','ACTIVE','IS_A')")
        self.assertIsNone(k.resolve_head('large aquifer in Kenya containing saline water'))
        self.assertEqual(k.resolve_head('small GPS smartwatch containing a water sensor'),'native:smart')
        c.execute(
            "INSERT INTO nodes VALUES('native:other','Smartwatch','class','Independent physical type','{}','ACTIVE',5)"
        )
        c.execute("INSERT INTO aliases VALUES('smartwatch','native:other')")
        c.execute(
            "INSERT INTO edges VALUES('native:other','wordnet31:artifact','ACTIVE','IS_A')"
        )
        self.assertIsNone(k.representative(k.candidates("smartwatch")))
        self.assertIsNone(WordNetKinds(c).unique_artifact("smartwatch"))
