"""Index original source configurations without rewriting their identity/data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from fineatlas.migration import Migration
from fineatlas.catalogue import canonical_record
SPEC=importlib.util.spec_from_file_location('living_preparer',Path(__file__).resolve().parents[1]/'scripts/prepare_living_expansion.py')
module=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(module)


class ExistingConfigurationFieldsTest(unittest.TestCase):
    def test_preserved_source_fields_keep_brand_separate_from_manufacturer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);database=root/'candidate.sqlite';inputs=root/'inputs';inputs.mkdir()
            c=sqlite3.connect(database)
            c.executescript('''CREATE TABLE nodes(uid TEXT PRIMARY KEY,data TEXT); CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
              CREATE TABLE source_field_values(uid TEXT,field TEXT,value TEXT,source TEXT,evidence_id TEXT,PRIMARY KEY(uid,field,value,source));
              CREATE TABLE source_catalogs(source TEXT PRIMARY KEY,source_uri TEXT,license TEXT,sha256 TEXT,manifest TEXT);
              CREATE TABLE evidence(layer TEXT,id TEXT PRIMARY KEY,source TEXT,source_uri TEXT,retrieved TEXT,claim TEXT,data TEXT,sha256 TEXT);''')
            record={'domain_name':'amazon.com','item_id':'old-id','product_type':[{'value':'TABLE'}],
                    'brand':[{'value':'Source Brand'}],'material':[{'value':'Wood'}]}
            uid='abo-listing:amazon.com:old-id';raw=json.dumps({'native_record':record,'old_evidence':'keep'})
            c.execute('INSERT INTO nodes VALUES(?,?)',(uid,raw));c.commit();c.close()
            (inputs/'living_catalogue_records.jsonl').write_text('')
            manifest={'records_sha256':hashlib.sha256(b'').hexdigest(),'archive_sha256':'source-hash',
                      'existing_source_fields':[{'uid':uid,'native_record':record,
                      'record_sha256':hashlib.sha256(canonical_record(record)).hexdigest(),
                      'catalogue_paths':['Furniture/Tables'],'source_member':'metadata.gz','source_line':4}]}
            (inputs/'living_catalogue_manifest.json').write_text(json.dumps(manifest))
            m=Migration(database,inputs,root/'reports')
            module.apply_living_expansion(m);module.apply_living_expansion(m)
            self.assertEqual(m.c.execute('SELECT data FROM nodes WHERE uid=?',(uid,)).fetchone()[0],raw)
            fields={r[0]:r[1] for r in m.c.execute('SELECT field,value FROM source_field_values WHERE uid=?',(uid,))}
            self.assertEqual(fields['brand'],'Source Brand');self.assertNotIn('manufacturer',fields)
            self.assertEqual(m.c.execute('SELECT count(*) FROM source_field_values').fetchone()[0],4)
            m.c.close()

if __name__=='__main__':unittest.main()
