"""Nominal grounding: modern native kinds, homonyms and design-role exclusion."""

import json, sqlite3, unittest
from fineatlas.nominal import WordNetKinds, object_kind_head


class NominalContractsTest(unittest.TestCase):
    def test_purpose_target_cannot_be_the_subject_type(self):
        self.assertEqual(object_kind_head("world's first operational jet engine to power an aircraft"), "world's first operational jet engine")
        self.assertEqual(object_kind_head('machine for manufacturing cars'), 'machine')
        self.assertEqual(object_kind_head('flying machine such as an aeroplane'), 'flying machine')
        self.assertEqual(object_kind_head('gas-turbine-powered locomotive with a generator'), 'gas-turbine-powered locomotive')
        self.assertEqual(object_kind_head('device enabling a single-engine aircraft to fire its armament'), 'device')
        self.assertEqual(object_kind_head('engine powering an aircraft'), 'engine')

    def test_native_scope_follows_verified_identity_group(self):
        c=sqlite3.connect(':memory:')
        c.executescript("CREATE TABLE nodes(uid TEXT,label TEXT,rank TEXT,description TEXT,data TEXT,visibility TEXT,component_id INTEGER);CREATE TABLE aliases(alias TEXT,uid TEXT);CREATE TABLE edges(child_uid TEXT,parent_uid TEXT,status TEXT,relation TEXT);CREATE TABLE node_profiles(uid TEXT,node_kind TEXT);")
        c.executemany('INSERT INTO nodes VALUES(?,?,?,?,?,?,?)',[
            ('wordnet31:artifact','artifact','class','Physical artifact','{}','ACTIVE',1),
            ('native:artifact','artifact','class','Physical artifact','{}','ACTIVE',1),
            ('native:device','device','class','A physical device','{}','ACTIVE',2)])
        c.execute("INSERT INTO aliases VALUES('artifact','wordnet31:artifact')")
        c.execute("INSERT INTO edges VALUES('native:device','native:artifact','ACTIVE','IS_A')")
        k=WordNetKinds(c,include_native=True)
        self.assertTrue(k.artifact_type('native:device'))
        self.assertTrue(k.within('native:device',{'wordnet31:artifact'}))

    def test_functional_device_definition_excludes_decorative_device_sense(self):
        c=sqlite3.connect(':memory:')
        c.executescript("CREATE TABLE nodes(uid TEXT,label TEXT,rank TEXT,description TEXT,data TEXT,visibility TEXT,component_id INTEGER);CREATE TABLE aliases(alias TEXT,uid TEXT);CREATE TABLE edges(child_uid TEXT,parent_uid TEXT,status TEXT,relation TEXT);CREATE TABLE node_profiles(uid TEXT,node_kind TEXT);")
        for u,desc,comp in [('wordnet31:artifact','a physical artifact',1),('wordnet31:functional','an instrumentality invented for a particular purpose',2),('wordnet31:ornamental','any ornamental pattern or design',3)]:
            c.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?)',(u,'device','class',desc,'{}','ACTIVE',comp))
            c.execute('INSERT INTO aliases VALUES(?,?)',('artifact' if comp==1 else 'device',u))
            if comp!=1:c.execute("INSERT INTO edges VALUES(?,?,'ACTIVE','IS_A')",(u,'wordnet31:artifact'))
        k=WordNetKinds(c)
        self.assertEqual(len(k.candidates('device')),2)
        self.assertEqual(k.contextual_candidates('device','A gear is a device enabling an aircraft to fire its armament.'),{'wordnet31:functional'})
        self.assertEqual(len(k.contextual_candidates('device','A decorative device')),2)

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
