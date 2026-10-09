"""Native locale variants are query-compatible without rewriting source names."""
import hashlib
import sqlite3
import unittest

import test_single
from fineatlas import FineAtlas


class LanguageTagCompatibilityTest(unittest.TestCase):
    tearDown = test_single.TypedInterfaceTest.tearDown

    def setUp(self):
        test_single.TypedInterfaceTest.setUp(self)
        self.tree.close()
        with sqlite3.connect(self.path) as c:
            c.execute('''CREATE TABLE node_names(uid TEXT,name TEXT,language TEXT,
                         source TEXT,evidence_id TEXT,preferred INTEGER)''')
            c.executemany('INSERT INTO node_names VALUES(?,?,?,?,?,?)', [
                ('type:river', 'American River', 'en_US', 'publisher', 'proof:US', 0),
                ('type:river', 'British River', 'en-GB', 'publisher', 'proof:GB', 0),
                ('type:river', '河流', 'zh_Hans', 'publisher', 'proof:CN', 0),
                ('type:river', 'Rio', 'pt-BR', 'publisher', 'proof:BR', 0),
                ('type:river', 'English fallback', 'en', 'publisher', 'proof:EN', 1),
            ])
            c.executemany('INSERT INTO aliases VALUES(?,?)', [
                ('american river', 'type:river'), ('british river', 'type:river'),
                ('河流', 'type:river'), ('rio', 'type:river'),
            ])
        self.tree = FineAtlas(self.path)

    def test_filter_accepts_both_separators_and_case_with_original_provenance(self):
        for requested in ('en-US', 'en_US', 'EN-us', 'EN_US'):
            with self.subTest(requested=requested):
                result = self.tree.aliases('type:river', language=requested)
                self.assertEqual([r['name'] for r in result], ['American River'])
                self.assertEqual(result[0]['language'], 'en_US')
                self.assertEqual(result[0]['evidence_id'], 'proof:US')
        for requested in ('en-GB', 'en_GB', 'EN-gb'):
            self.assertEqual([r['name'] for r in self.tree.aliases(
                'type:river', language=requested)], ['British River'])

    def test_region_and_script_remain_distinct(self):
        self.assertEqual(self.tree.aliases('type:river', language='en-CA'), [])
        self.assertEqual(self.tree.aliases('type:river', language='zh-Hant'), [])
        self.assertEqual([r['name'] for r in self.tree.aliases(
            'type:river', language='ZH-hans')], ['河流'])
        self.assertEqual([r['name'] for r in self.tree.aliases(
            'type:river', language='PT_br')], ['Rio'])

    def test_case_insensitive_und_keeps_legacy_alias_fallback(self):
        self.assertEqual(self.tree.aliases('type:river', language='UND'),
                         self.tree.aliases('type:river', language='und'))
        self.assertTrue(self.tree.aliases('type:river', language='UND'))

    def test_constructor_language_selects_names_for_node_and_public_search(self):
        for requested, title, native_tag in [
            ('en-US', 'American River', 'en_US'),
            ('EN_us', 'American River', 'en_US'),
            ('en_GB', 'British River', 'en-GB'),
            ('ZH-hans', '河流', 'zh_Hans'),
        ]:
            with self.subTest(requested=requested), FineAtlas(
                self.path, language=requested) as tree:
                node = tree.node('type:river')
                self.assertEqual(node['label'], title)
                self.assertEqual(node['label_language'], native_tag)
                exact = tree.search_page(title, exact=True, node_kind='CLASS')
                self.assertEqual([n['uid'] for n in exact['items']], ['type:river'])
                self.assertEqual(exact['items'][0]['label'], title)
                self.assertEqual(exact['items'][0]['label_language'], native_tag)
                approximate = tree.search_page(title, node_kind='CLASS')
                self.assertEqual(approximate['items'][0]['uid'], 'type:river')

    def test_unavailable_locale_keeps_existing_english_fallback(self):
        with FineAtlas(self.path, language='en-CA') as tree:
            self.assertEqual(tree.node('type:river')['label'], 'English fallback')

    def test_unavailable_locale_recognizes_uppercase_source_fallback_tag(self):
        self.tree.close()
        with sqlite3.connect(self.path) as c:
            c.execute("UPDATE node_names SET language='EN',preferred=0 WHERE language='en'")
            c.execute('INSERT INTO node_names VALUES(?,?,?,?,?,?)',
                      ('type:river', 'Rivière française', 'FR', 'publisher', 'proof:FR', 1))
        self.tree = FineAtlas(self.path, language='en-CA')
        node = self.tree.node('type:river')
        self.assertEqual(node['label'], 'English fallback')
        self.assertEqual(node['label_language'], 'EN')

    def test_read_queries_leave_raw_names_and_database_bytes_unchanged(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        rows = self.tree.con.execute('SELECT * FROM node_names ORDER BY name').fetchall()
        self.tree.aliases('type:river', language='en-US')
        self.tree.search_page('American River', exact=True)
        after_rows = self.tree.con.execute('SELECT * FROM node_names ORDER BY name').fetchall()
        self.assertEqual([tuple(r) for r in rows], [tuple(r) for r in after_rows])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()
