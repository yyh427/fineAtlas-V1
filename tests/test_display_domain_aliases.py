"""Display-name insertion preserves existing navigation scopes and identities."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from fineatlas.display_aliases import apply_display_domain_aliases


class DisplayDomainNamesTest(unittest.TestCase):
    def test_scoped_names_are_idempotent_and_collisions_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
            c.executescript('CREATE TABLE domain_registry(domain_id INTEGER,canonical_name TEXT,description TEXT,root_uids TEXT); CREATE TABLE domain_aliases(alias TEXT PRIMARY KEY,domain_id INTEGER,provenance TEXT);')
            c.execute('INSERT INTO domain_registry VALUES(1,?,?,?)',('lighting','Defined light sources','["native:lamp"]'))
            class Replay:
                inputs=root
                def evidence(self,*args):return 'proof:navigation'
                def change(self,*args):self.changes.append(args)
            m=Replay();m.c=c;m.changes=[]
            record={'schema':'FINEATLAS_NAVIGATION_NAMES_V1','source_uri':'https://example.org/config',
                    'domains':[{'domain':'lighting','definition':'Defined light sources','root_uids':['native:lamp'],'aliases':['照明','灯具']}]}
            (root/'display_domain_aliases.json').write_text(json.dumps(record))
            self.assertEqual(apply_display_domain_aliases(m)['new_navigation_aliases'],2)
            self.assertEqual(apply_display_domain_aliases(m)['existing_aliases_preserved'],2)
            self.assertEqual(len(m.changes),2)
            c.execute("UPDATE domain_aliases SET domain_id=2 WHERE alias='灯具'")
            with self.assertRaises(ValueError):apply_display_domain_aliases(m)

if __name__=='__main__':unittest.main()
