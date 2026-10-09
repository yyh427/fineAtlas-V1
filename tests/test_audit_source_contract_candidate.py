"""Acceptance must bind each disposition to its exact original source claim."""
import importlib.util
import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('source_candidate_audit',Path(__file__).resolve().parents[1]/'scripts/audit_source_contract_candidate.py')
AUDIT=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class SourceContractCandidateAuditTest(unittest.TestCase):
    def test_optimized_python_is_rejected_before_cli_or_database_access(self):
        result=subprocess.run([sys.executable,'-O',str(Path(__file__).resolve().parents[1]/'scripts/audit_source_contract_candidate.py')],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Independent acceptance refuses optimized Python',result.stderr)
        self.assertNotIn('the following arguments are required',result.stderr)

    def test_subject_parser_independent_vetoes_named_mentions_and_parent_scope(self):
        for text in ['Foo is not an aircraft', 'Foo is a book about aircraft',
                     'Foo is a museum displaying aircraft', "Foo\'s designer says it is an aircraft"]:
            self.assertTrue(AUDIT.own_literal_scope(text,'Foo','aircraft','a vehicle that can fly'),text)
        self.assertTrue(AUDIT.own_literal_scope('Foo is a three-wheeled car','Foo','car','a motor vehicle with four wheels'))
        self.assertTrue(AUDIT.own_literal_scope('Foo is a car with three wheels','Foo','car','a motor vehicle with four wheels'))
        self.assertTrue(AUDIT.own_literal_scope('Foo is a car whose wheel count is three','Foo','car','a motor vehicle with four wheels'))
        self.assertEqual(AUDIT.own_literal_scope('Foo is a car competing with a three-wheeled automobile','Foo','car','a motor vehicle with four wheels'),[])
        self.assertTrue(AUDIT.own_literal_scope('Native source label: Foo aircraft; subject definition: A software simulator for pilots','Foo aircraft','aircraft','a vehicle that can fly'))
        self.assertEqual(AUDIT.own_literal_scope('Foo is a military aircraft developed by Example','Foo','aircraft','a vehicle that can fly'),[])
        self.assertTrue(AUDIT.own_literal_scope('Foo is a line of laptops, desktops, tablets and all-in-one computers','Foo','laptop','a portable computer','MODEL_FAMILY'))
        self.assertTrue(AUDIT.own_literal_scope('Foo is a laptop in the Example family','Foo','laptop','a portable computer','MODEL_FAMILY'))
        self.assertEqual(AUDIT.own_literal_scope('Foo is a family of aircraft and aircraft models developed by Example','Foo','aircraft','a vehicle that can fly','MODEL_FAMILY'),[])

    def schema(self,path):
        con=sqlite3.connect(path);con.row_factory=sqlite3.Row
        con.executescript('''
          CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
          CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,source TEXT,rank TEXT,
            description TEXT,data TEXT,domain TEXT,domains TEXT,layer TEXT,visibility TEXT);
          CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT);
          CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,
            relation TEXT,status TEXT,source TEXT,evidence_id TEXT,data TEXT);
          CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,
            relation TEXT,source TEXT,layer TEXT,status TEXT,data TEXT,reason TEXT);
          CREATE TABLE usability_changes(id INTEGER PRIMARY KEY,stage TEXT,object_type TEXT,
            object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT);
        ''')
        return con

    def fixture(self,root):
        inputs=root/'inputs';inputs.mkdir();database=root/'candidate.sqlite';baseline=root/'baseline.sqlite'
        con=self.schema(database);old=self.schema(baseline);old.commit();old.close()
        rows=[('foo','Foo','documented manufacturer','model','A named car model','{}','cars','[]','native','ACTIVE'),
              ('car','car','wordnet31','class','a motor vehicle with four wheels','{}','cars','[]','native','ACTIVE')]
        con.executemany('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?)',rows)
        con.executemany('INSERT INTO node_profiles VALUES(?,?)',[('foo','MODEL'),('car','CLASS')])
        original={'id':7,'subject_uid':'foo','object_uid':'car','relation':'DESIGN_TYPE_OF','status':'ACTIVE',
                  'source':'Old lexical inference','evidence_id':'old-proof','data':'{"original":"evidence"}'}
        con.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',tuple(original.values()))
        con.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',(8,*tuple(original.values())[1:]))
        child=dict(con.execute("SELECT n.*,'MODEL' role FROM nodes n WHERE uid='foo'").fetchone())
        parent=dict(con.execute("SELECT n.*,'CLASS' role FROM nodes n WHERE uid='car'").fetchone())
        locator={k:original[k] for k in ('subject_uid','object_uid','relation','source')}
        locator.update(content_sha256=AUDIT.assertion_sha(original),source_assertion_multiplicity=2)
        statement='Foo is a sports car manufactured by Example'
        record={'table':'entity_relations','locator':locator,'original_source_assertion':original,
                'child_source_record':child,'parent_source_record':parent,'child_raw_sha256':AUDIT.sha('{}'),
                'parent_raw_sha256':AUDIT.sha('{}'),'source_statement':statement,'decision':'SOURCE_SCOPE_REVIEW'}
        proof={'source_record_uid':'foo','native_record_sha256':AUDIT.sha('{}'),'reviewed_parent_uid':'car',
               'parent_definition':parent['description'],'parent_definition_sha256':AUDIT.sha(parent['description']),
               'source_statement':statement,'matched_explicit_genus':'car','original_claim_locators':[locator],
               'individual_semantic_review':False,'human_individual_review':False,'reviewed_rule_verified':True,'source_scope_entails_parent':True}
        repair={'uid':'foo','parent':'car','relation':'DESIGN_TYPE_OF','source':'Frozen physical scope','uri':'https://authority.example/Foo','proof':proof}
        payload={'baseline_database':str(baseline),'quarantines':[record],'protected':[],
                 'reviewed_genus_anchors':[{'uid':'car','raw_sha256':AUDIT.sha('{}'),'definition_sha256':AUDIT.sha(parent['description'])}],
                 'repairs':[repair]}
        source=inputs/'structure_source_contracts.json';source.write_text(json.dumps(payload))
        ops=inputs/'structure_source_contracts_operations.jsonl';ops.write_text(json.dumps({'op':'link',**repair})+'\n')
        expected=inputs/'source_contract_independent_expectations.json';expected.write_text(json.dumps({'cases':[
            {'uid':'foo','parent':'car','origin':'independent-fixture','disposition':'PHYSICAL_PARENT_DIRECTION_SUPPORTED','required':True,'expected_role':'MODEL'}]}))
        native_inventory=inputs/'source_contract_native_preservation.json'
        native_inventory.write_text(json.dumps({'claims':[],'original_source_rows':0,'scope':'Explicitly empty synthetic fixture native cohort'}))
        input_sha=AUDIT.sha(source.read_bytes())
        con.execute("UPDATE entity_relations SET status='SOURCE_SCOPE_REVIEW'")
        for index in (7,8):
            before={**original,'id':index}
            con.execute('INSERT INTO usability_changes VALUES(?,?,?,?,?,?,?)',(index,'source_semantic_contract','entity_relations',str(index),json.dumps(before),'{"status":"SOURCE_SCOPE_REVIEW"}',json.dumps({'basis':'UNREVIEWED_LEXICAL_PARENT_SCOPE','candidate_input_sha256':input_sha})))
        con.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',(9,'foo','car','DESIGN_TYPE_OF','ACTIVE',repair['source'],'new-proof',json.dumps({'admission_basis':proof})))
        metadata={'unified_ready':True,'usability_indexes_ready':True,'browse_indexes_ready':True,'database_revision':'frozen-revision',
                  'browse_index_revision':'frozen-revision','structure_frozen_build_manifest':{'inputs':{
                      p.name:AUDIT.sha(p.read_bytes()) for p in (source,ops,expected,native_inventory)}}}
        con.executemany('INSERT INTO metadata VALUES(?,?)',[(k,json.dumps(v)) for k,v in metadata.items()]);con.commit()
        return con,database,inputs,locator

    def test_exact_duplicate_multiplicity_and_each_row_change_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            con,database,inputs,locator=self.fixture(Path(tmp))
            self.assertEqual(len(AUDIT.locate(con,'entity_relations',locator)),2)
            result=AUDIT.audit(database,inputs,Path(tmp)/'pass')
            self.assertTrue(result['pass'],result['failures'])
            con.execute('DELETE FROM usability_changes WHERE id=8');con.commit()
            result=AUDIT.audit(database,inputs,Path(tmp)/'missing-ledger')
            self.assertFalse(result['pass'])
            self.assertTrue(any('MISSING_EXACT_SOURCE_SCOPE_CHANGE_LEDGER:8' in f.get('errors',[]) for f in result['failures']))
            con.execute('DELETE FROM entity_relations WHERE id=8');con.commit()
            with self.assertRaisesRegex(ValueError,'multiplicity'):AUDIT.locate(con,'entity_relations',locator)
            con.close()

    def test_metadata_unready_and_frozen_proof_mutation_are_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            con,database,inputs,_=self.fixture(Path(tmp))
            con.execute("UPDATE metadata SET value='false' WHERE key='browse_indexes_ready'")
            con.execute("UPDATE entity_relations SET data='{}' WHERE id=9");con.commit()
            result=AUDIT.audit(database,inputs,Path(tmp)/'blocked')
            self.assertFalse(result['pass'])
            self.assertTrue(any(f['check']=='DATABASE_NOT_FULLY_READY' for f in result['failures']))
            self.assertTrue(any('FROZEN_REPLACEMENT_RELATION_OR_PROOF_NOT_IN_ACTIVE_DATABASE' in f.get('errors',[]) for f in result['failures']))
            con.close()

    def test_compressed_input_binds_archive_and_underlying_payload_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            con,database,inputs,_=self.fixture(Path(tmp))
            source=inputs/'structure_source_contracts.json';plain=source.read_bytes()
            compressed=inputs/'structure_source_contracts.json.gz';compressed.write_bytes(gzip.compress(plain,mtime=0));source.unlink()
            expected=inputs/'source_contract_independent_expectations.json';data=json.loads(expected.read_text())
            data['candidate_payload_sha256']=AUDIT.sha(plain);expected.write_text(json.dumps(data))
            metadata=json.loads(con.execute("SELECT value FROM metadata WHERE key='structure_frozen_build_manifest'").fetchone()[0])
            metadata['inputs'].pop(source.name);metadata['inputs'][compressed.name]=AUDIT.sha(compressed.read_bytes());metadata['inputs'][expected.name]=AUDIT.sha(expected.read_bytes())
            con.execute("UPDATE metadata SET value=? WHERE key='structure_frozen_build_manifest'",(json.dumps(metadata),))
            for row in con.execute('SELECT id,evidence FROM usability_changes').fetchall():
                proof=json.loads(row['evidence']);proof['candidate_input_sha256']=AUDIT.sha(compressed.read_bytes())
                con.execute('UPDATE usability_changes SET evidence=? WHERE id=?',(json.dumps(proof),row['id']))
            con.commit();result=AUDIT.audit(database,inputs,Path(tmp)/'compressed-pass')
            self.assertTrue(result['pass'],result['failures'])
            self.assertEqual(result['input_sha256'],AUDIT.sha(compressed.read_bytes()))
            self.assertEqual(result['payload_sha256'],AUDIT.sha(plain));con.close()

    def test_compute_capability_table_never_proves_gpu_whole_object_type(self):
        record={'child_source_record':{'uid':'nvidia:tesla-s870','source':'NVIDIA native CUDA GPU model table',
                                     'data':json.dumps({'source_record':{'gpu_model_designation':'Tesla S870','compute_capability':'1.0'}})},
                'parent_source_record':{'uid':'nvidia-type:cuda-capable-gpu','description':'A graphics processing unit supporting CUDA'}}
        self.assertTrue(AUDIT.protection_errors(record))

    def test_commercial_membership_requires_actual_relation_and_complete_primary_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            con=sqlite3.connect(Path(tmp)/'publisher.sqlite')
            con.execute('CREATE TABLE evidence(evidence_id TEXT,payload TEXT)')
            uri='https://support.apple.com/en-us/108043';ids=['A2436','A2437']
            raw={'evidence_id':'publisher-section','source_uri':uri,'attributes':{'native_model_identifiers':ids,'catalog_heading':'Example iPad'}}
            child={'uid':'apple:model','source':'Apple model-identification support','node_kind':'MODEL','data':json.dumps(raw)}
            parent={'uid':'apple:ipad','source':child['source'],'node_kind':'MODEL_FAMILY','data':json.dumps({'source_uri':uri})}
            con.execute('INSERT INTO evidence VALUES(?,?)',('publisher-section',json.dumps({'native_model_identifiers':ids,'source_sha256':'snapshot','source_section_sha256':'section'})))
            proof={'kind':'PUBLISHER_DECLARED_COMMERCIAL_LINE_MEMBERSHIP','actual_relation':'SERIES_MEMBER_OF','identity_scope':'SOURCE_NATIVE_COMMERCIAL_LINE',
                   'is_design_lineage':False,'is_class_inclusion':False,'is_visual_distance':False,'native_model_identifiers':ids,
                   'source_snapshot_sha256':'snapshot','source_section_sha256':'section','parent_native_record_sha256':AUDIT.sha(parent['data'])}
            inventory={child['uid']:{'parent':parent['uid'],'source_record_sha256':AUDIT.sha(child['data']),'parent_record_sha256':AUDIT.sha(parent['data']),
                                    'source_uri':uri,'heading':'Example iPad','source_snapshot_sha256':'snapshot','native_model_identifiers':ids,
                                    'independently_extracted_section_identifiers':ids,'semantic_scope':'PUBLISHER_COMMERCIAL_PRODUCT_LINE_MEMBERSHIP_ONLY','errors':[]}}
            repair={'relation':'SERIES_MEMBER_OF','proof':proof}
            self.assertEqual(AUDIT.commercial_membership_errors(con,repair,child,parent,inventory),[])
            repair['relation']='NATIVE_DESIGN_PARENT'
            self.assertIn('COMMERCIAL_LINE_HAS_INCORRECT_ACTUAL_RELATION_OR_SCOPE',AUDIT.commercial_membership_errors(con,repair,child,parent,inventory))
            repair['relation']='SERIES_MEMBER_OF';inventory[child['uid']]['independently_extracted_section_identifiers']=['A2436']
            self.assertIn('COMMERCIAL_LINE_SOURCE_SCOPE_DIFFERS_FROM_INDEPENDENT_PRIMARY_SECTION',AUDIT.commercial_membership_errors(con,repair,child,parent,inventory))
            con.close()

    def test_native_preservation_cannot_fold_identical_original_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);con,database,inputs,_=self.fixture(root)
            old=sqlite3.connect(root/'baseline.sqlite')
            for record_id in (50,51):
                row=(record_id,'foo','car','REGULATED_AS','ACTIVE','Native registry','native-proof','{"native":"unmodified"}')
                old.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',row)
                con.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',row)
            old.commit();old.close();con.commit()
            row=dict(con.execute('SELECT * FROM entity_relations WHERE id=50').fetchone())
            locator={k:row[k] for k in ('subject_uid','object_uid','relation','source')}
            locator.update(content_sha256=AUDIT.assertion_sha(row),source_assertion_multiplicity=2)
            inventory=inputs/'source_contract_native_preservation.json'
            inventory.write_text(json.dumps({'claims':[{'table':'entity_relations','locator':locator,'original_source_assertion':row}],'original_source_rows':2}))
            metadata=json.loads(con.execute("SELECT value FROM metadata WHERE key='structure_frozen_build_manifest'").fetchone()[0])
            metadata['inputs'][inventory.name]=AUDIT.sha(inventory.read_bytes())
            con.execute("UPDATE metadata SET value=? WHERE key='structure_frozen_build_manifest'",(json.dumps(metadata),));con.commit()
            result=AUDIT.audit(database,inputs,root/'native-pass')
            self.assertTrue(result['pass'],result['failures'])
            con.execute('DELETE FROM entity_relations WHERE id=51');con.commit()
            result=AUDIT.audit(database,inputs,root/'native-fold')
            self.assertFalse(result['pass'])
            failure=next(f for f in result['failures'] if f['check']=='ORIGINAL_NATIVE_OR_REGULATORY_ASSERTION_CHANGED')
            self.assertEqual(failure['original_multiplicity'],2)
            self.assertEqual(failure['candidate_multiplicity'],1)
            con.close()


if __name__=='__main__':unittest.main()
