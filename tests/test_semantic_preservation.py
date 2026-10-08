"""Semantic loss exceptions require frozen facts, current scope and real arcs."""
import copy
import contextlib
import hashlib
import importlib.util
import json
import io
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/audit_unified_candidate.py'
sys.path.insert(0,str(SCRIPT.parent))
spec=importlib.util.spec_from_file_location('semantic_preservation',SCRIPT)
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)


class FixtureTree:
    root_uid='wordnet31:root'
    relation_view='unified'

    def __init__(self,c):self.con=c

    def _basic(self,uid):
        r=self.con.execute("SELECT n.*,coalesce(p.node_kind,'CLASS') node_kind FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?",(uid,)).fetchone()
        return dict(r) if r else None

    def _parents(self,uid,include_terminal=True):
        return [(r['parent_uid'],dict(r)) for r in self.con.execute("SELECT * FROM edges WHERE child_uid=? AND relation='IS_A' AND status='ACTIVE'",(uid,))]

    def path_result(self,uid):
        path=[];current=uid;seen=set()
        while current!=self.root_uid:
            if current in seen:return {'status':'UNREACHABLE','path':[]}
            seen.add(current);parents=self._parents(current,include_terminal=False)
            if not parents:return {'status':'UNREACHABLE','path':[]}
            parent,edge=parents[0];path.append({'edge':edge});current=parent
        return {'status':'CONNECTED' if path else 'ROOT','path':list(reversed(path))}


class GenericSemanticPreservationTest(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
        self.c.executescript("""
          CREATE TABLE nodes(uid TEXT PRIMARY KEY,label TEXT,description TEXT,data TEXT,rank TEXT,visibility TEXT,component_id INTEGER);
          CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,evidence_id TEXT,attributes TEXT);
          CREATE TABLE normalization_roles(uid TEXT PRIMARY KEY,canonical_role TEXT,status TEXT,evidence_id TEXT);
          CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,relation TEXT,status TEXT,source TEXT,evidence_id TEXT,data TEXT);
          CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,relation TEXT,status TEXT,source TEXT,data TEXT,provenance TEXT);
          CREATE TABLE bridges(id INTEGER PRIMARY KEY,left_uid TEXT,right_uid TEXT,relation TEXT,status TEXT);
          CREATE TABLE hierarchy_decisions(id TEXT PRIMARY KEY,operation TEXT,subject_uid TEXT,object_uid TEXT,evidence_id TEXT,payload TEXT);
          CREATE TABLE evidence(layer TEXT,evidence_id TEXT,payload TEXT,payload_sha256 TEXT,source_uri TEXT,PRIMARY KEY(layer,evidence_id));
        """)
        self.statement='A basket is a container that holds things.'
        self.native=json.dumps({'definition':self.statement})
        self.parent_native=json.dumps({'definition':'A container holds objects.'})
        self.c.executemany('INSERT INTO nodes VALUES(?,?,?,?,?,?,?)',[
          ('wikidata:Q1','basket',self.statement,self.native,'model_family','ACTIVE',1),
          ('wordnet31:container','container','A container holds objects.',self.parent_native,'class','ACTIVE',2),
          ('wordnet31:root','entity','Anything.','{}','class','ACTIVE',3)])
        self.old={'id':7,'subject_uid':'wikidata:Q1','object_uid':'wordnet31:container','relation':'DESIGN_TYPE_OF',
                  'status':'ACTIVE','source':'Historical role adapter','evidence_id':'old-evidence','data':'{"original":true}'}
        self.current={**self.old,'status':'HIERARCHY_SUPERSEDED'}
        self.c.execute('INSERT INTO entity_relations VALUES(?,?,?,?,?,?,?,?)',tuple(self.current.values()))
        self.common={'source_statement':self.statement,'subject_kind_head':'container','individual_semantic_review':True,
                     'scope_observation':'Reusable baskets across makers, not a named model family.',
                     'identity_member_uids':['wikidata:Q1'],'native_record_sha256':hashlib.sha256(self.native.encode()).hexdigest(),
                     'no_name_based_identity':True,'original_source_payload_and_endpoints_preserved':True,
                     'source_role':'Independently defined reusable physical kind','allowed_views':['strict','taxonomy','membership','unified']}
        self.role={'op':'role','uid':'wikidata:Q1','role':'CLASS','source':'Reviewed shared generic-kind contracts',
                   'uri':'https://example.org/basket','proof':{**self.common,'basis':'REVIEWED_GENERIC_WHOLE_SUBJECT_REPLACES_ADAPTER_DESIGN_ROLE',
                         'prior_role':'MODEL_FAMILY','native_rank':'model_family'}}
        self.withdraw={'op':'withdraw_typed_source','uid':'wikidata:Q1','source':self.role['source'],'uri':self.role['uri'],
                       'locator':{'subject_uid':'wikidata:Q1','object_uid':'wordnet31:container','relation':'DESIGN_TYPE_OF',
                                  'source':self.old['source'],'content_sha256':audit.source_assertion_sha256(self.old)},
                       'proof':{**self.role['proof'],'basis':'GENERIC_KIND_IS_NOT_DESIGN_TERMINAL',
                                'original_relation':'DESIGN_TYPE_OF','original_parent_uid':'wordnet31:container'}}
        self.link={'op':'link','uid':'wikidata:Q1','parent':'wordnet31:container','relation':'IS_A','source':self.role['source'],
                   'uri':self.role['uri'],'proof':{**self.common,'basis':self.role['proof']['basis'],
                      'parent_definition':'A container holds objects.','parent_native_record_sha256':hashlib.sha256(self.parent_native.encode()).hexdigest(),
                      'entailment_observation':'The whole-subject definition explicitly states the container kind.',
                      'not_created_for_root_reachability':True}}
        self.decisions=[]
        self.install_decisions()
        self.tree=FixtureTree(self.c)

    def tearDown(self):self.c.close()

    def install_decisions(self):
        self.c.execute('DELETE FROM evidence');self.c.execute('DELETE FROM hierarchy_decisions')
        self.decisions=[]
        for r in [self.withdraw,self.role,self.link]:
            payload=json.dumps(r['proof'],ensure_ascii=False,sort_keys=True,separators=(',',':'))
            sha=hashlib.sha256(payload.encode()).hexdigest();eid='usability:'+sha
            self.c.execute('INSERT INTO evidence VALUES(?,?,?,?,?)',('v1.7-generality-review',eid,payload,sha,r['uri']))
            decision_payload=json.dumps(r,sort_keys=True,ensure_ascii=False)
            decision={'id':hashlib.sha256(decision_payload.encode()).hexdigest(),'operation':r['op'],'subject_uid':r['uid'],
                      'object_uid':r.get('parent',''),'evidence_id':eid,'payload':decision_payload}
            self.decisions.append(decision)
            self.c.execute('INSERT INTO hierarchy_decisions VALUES(?,?,?,?,?,?)',tuple(decision.values()))
        role_id=self.decisions[1]['evidence_id']
        attrs={'canonical_scope_guard':'GENERIC_PHYSICAL_KIND','role_status':'VERIFIED','role_evidence_id':role_id,
               'canonical_scope_evidence_id':role_id,'source_role':self.role['proof']['source_role'],
               'allowed_views':self.role['proof']['allowed_views']}
        self.c.execute('INSERT OR REPLACE INTO node_profiles VALUES(?,?,?,?)',('wikidata:Q1','CLASS',role_id,json.dumps(attrs)))
        self.c.execute('INSERT OR REPLACE INTO normalization_roles VALUES(?,?,?,?)',('wikidata:Q1','CLASS','VERIFIED',role_id))
        self.c.execute('DELETE FROM edges')
        self.c.execute('INSERT INTO edges VALUES(?,?,?,?,?,?,?,?)',(9,'wikidata:Q1','wordnet31:container','IS_A','ACTIVE',self.link['source'],
                       json.dumps({'admission_basis':self.link['proof']}),json.dumps({'evidence_ids':[self.decisions[2]['evidence_id']]})))
        self.c.execute('INSERT INTO edges VALUES(10,?,?,?,?,?,?,?)',('wordnet31:container','wordnet31:root','IS_A','ACTIVE','native','{}','{}'))
        self.c.commit()

    def verify(self):return audit.verify_generic_kind_correction(self.tree,self.old,self.current,self.decisions)

    def add_retained_legacy_inclusion(self):
        legacy=copy.deepcopy(self.link)
        legacy['source']='Retained independent generic-head definition'
        legacy['proof']['basis']='RETAINED_INDEPENDENT_GENERIC_HEAD'
        payload=json.dumps(legacy['proof'],ensure_ascii=False,sort_keys=True,separators=(',',':'))
        sha=hashlib.sha256(payload.encode()).hexdigest();eid='usability:'+sha
        self.c.execute('INSERT INTO evidence VALUES(?,?,?,?,?)',('v1.7-generality-review',eid,payload,sha,legacy['uri']))
        record=json.dumps(legacy,sort_keys=True,ensure_ascii=False)
        decision={'id':hashlib.sha256(record.encode()).hexdigest(),'operation':'link','subject_uid':legacy['uid'],
                  'object_uid':legacy['parent'],'evidence_id':eid,'payload':record}
        self.c.execute('INSERT INTO hierarchy_decisions VALUES(?,?,?,?,?,?)',tuple(decision.values()))
        self.decisions.insert(0,decision)
        self.c.execute('INSERT INTO edges VALUES(?,?,?,?,?,?,?,?)',(8,legacy['uid'],legacy['parent'],'IS_A','ACTIVE',legacy['source'],
                       json.dumps({'admission_basis':legacy['proof']}),json.dumps({'evidence_ids':[eid]})))
        self.c.commit()

    def test_reviewed_replacement_coexists_with_retained_older_inclusion(self):
        self.add_retained_legacy_inclusion()
        result=self.verify();self.assertTrue(result['verified_semantic_correction'],result)
        self.assertEqual(result['replacement_classification'][0]['edge_ids'],[9])

    def test_legacy_connected_inclusion_cannot_replace_missing_reviewed_decision(self):
        self.add_retained_legacy_inclusion()
        self.decisions=[d for d in self.decisions if d['id']!=self.decisions[-1]['id']]
        self.assertRejected('No independently reviewed')

    def test_legacy_inclusion_cannot_certify_a_changed_review_basis(self):
        self.link['proof']['basis']='UNRELATED_SCOPE';self.install_decisions()
        self.add_retained_legacy_inclusion();self.assertRejected('No independently reviewed')

    def test_qualifying_review_scope_still_requires_exact_reviewed_source(self):
        self.link['source']='Unreviewed forged source';self.install_decisions()
        self.assertRejected('Frozen semantic decision ledger/content differs')

    def assertRejected(self,fragment=None):
        result=self.verify();self.assertFalse(result['verified_semantic_correction'],result)
        if fragment:self.assertIn(fragment,result['rejection_reason'])

    def test_evidenced_generic_kind_status_only_correction_is_verified(self):
        result=self.verify();self.assertTrue(result['verified_semantic_correction'],result)
        self.assertEqual(result['replacement_classification'][0]['edge_ids'],[9])

    def test_forged_proof_without_matching_ledger_and_evidence_fails(self):
        forged=copy.deepcopy(self.decisions)
        payload=json.loads(forged[0]['payload']);payload['proof']['scope_observation']='Forged description'
        forged[0]['payload']=json.dumps(payload,sort_keys=True,ensure_ascii=False)
        result=audit.verify_generic_kind_correction(self.tree,self.old,self.current,forged)
        self.assertFalse(result['verified_semantic_correction'])

    def test_source_locator_sha_and_original_relation_data_must_match(self):
        self.withdraw['locator']['content_sha256']='wrong';self.install_decisions();self.assertRejected('checksum differs')

    def test_retained_statement_payload_sha_cannot_be_replaced(self):
        self.c.execute("UPDATE nodes SET data='{}' WHERE uid='wikidata:Q1'");self.assertRejected('exact native scope')

    def test_named_model_with_a_connected_path_is_not_a_generic_kind(self):
        self.c.execute("UPDATE nodes SET label='Basket Model X1' WHERE uid='wikidata:Q1'");self.assertRejected('whole-subject definition')

    def test_unreviewed_scope_cannot_be_exempted_by_root_connectivity(self):
        self.withdraw['proof']['individual_semantic_review']=False;self.install_decisions();self.assertRejected('individual semantic review')

    def test_replaced_source_endpoints_or_payload_fail_status_only_contract(self):
        self.current['object_uid']='wordnet31:root';self.assertRejected('status-only')

    def test_stale_canonical_guard_evidence_is_not_current_class_evidence(self):
        attrs=json.loads(self.c.execute('SELECT attributes FROM node_profiles').fetchone()[0]);attrs['canonical_scope_evidence_id']='stale'
        self.c.execute('UPDATE node_profiles SET attributes=?',(json.dumps(attrs),));self.assertRejected('scope guard')

    def test_role_evidence_payload_tamper_fails_even_when_path_is_connected(self):
        self.c.execute("UPDATE evidence SET payload='{}' WHERE evidence_id=?",(self.decisions[1]['evidence_id'],));self.assertRejected('retained evidence')

    def test_changed_parent_definition_and_hash_fail(self):
        self.c.execute("UPDATE nodes SET data='{}' WHERE uid='wordnet31:container'");self.assertRejected('parent source definition/checksum')

    def test_only_rooted_path_without_reviewed_classification_edge_fails(self):
        self.c.execute('DELETE FROM edges WHERE id=9')
        self.tree.path_result=lambda uid:{'status':'CONNECTED','path':[]}
        self.assertRejected('No independently reviewed')

    def test_cached_connected_witness_must_use_retained_legal_class_edges(self):
        original=self.tree.path_result('wikidata:Q1')
        self.c.execute("UPDATE edges SET status='REVIEW' WHERE id=10")
        self.tree.path_result=lambda uid: original if uid=='wikidata:Q1' else {'status':'CONNECTED','path':[original['path'][0]]}
        self.assertRejected('not an actual legal classification')

    def test_identity_member_change_and_normalization_drift_fail(self):
        self.c.execute("INSERT INTO nodes VALUES('maker:X','Model X','A named model.','{}','model','ACTIVE',1)")
        self.assertRejected('identity membership')
        self.c.execute("DELETE FROM nodes WHERE uid='maker:X'")
        self.c.execute("UPDATE normalization_roles SET canonical_role='MODEL'")
        self.assertRejected('normalization role ledger')

    def test_real_reverse_identity_witness_is_zero_depth_and_requires_its_bridge(self):
        self.c.execute("INSERT INTO nodes VALUES('wikidata:root','entity','Anything.','{}','class','ACTIVE',3)")
        self.c.execute("INSERT INTO bridges VALUES(21,'wordnet31:root','wikidata:root','SAME_CONCEPT','ACTIVE')")
        self.c.execute("UPDATE edges SET parent_uid='wikidata:root' WHERE id=10")
        identity={'uid':'wikidata:root','parent_uid':'wordnet31:root',
                  'edge':dict(self.c.execute('SELECT * FROM bridges').fetchone())}
        arc=dict(self.c.execute('SELECT * FROM edges WHERE id=10').fetchone())
        subject=dict(self.c.execute('SELECT * FROM edges WHERE id=9').fetchone())
        self.tree.path_result=lambda uid:{'status':'CONNECTED','path':[identity,{'edge':arc}]+([{'edge':subject}] if uid=='wikidata:Q1' else [])}
        result=self.verify();self.assertTrue(result['verified_semantic_correction'],result)
        self.c.execute('DELETE FROM bridges');self.assertRejected('no retained accepted bridge')

    def run_preservation(self):
        self.c.executescript("""
          CREATE TABLE dataset_targets(dataset TEXT,class_id TEXT,label TEXT,target_uid TEXT);
          CREATE TABLE dataset_target_history(dataset TEXT,class_id TEXT,original_target_uid TEXT);
          CREATE TABLE usability_changes(id INTEGER PRIMARY KEY,stage TEXT,object_type TEXT,object_id TEXT,evidence TEXT);
        """)
        self.c.commit()
        with tempfile.TemporaryDirectory() as folder:
            baseline=Path(folder)/'before.sqlite'
            with sqlite3.connect(baseline) as old:
                self.c.backup(old)
                old.execute("UPDATE entity_relations SET status='ACTIVE'")
                old.commit()
            with contextlib.redirect_stdout(io.StringIO()):
                return audit.preservation(self.tree,baseline,Path(folder)/'reports')

    def test_preservation_subtracts_only_explicitly_verified_generic_losses(self):
        result=self.run_preservation()
        self.assertEqual(result['explicitly_verified_generic_kind_corrections'],1)
        self.assertEqual(result['explicitly_verified_invalid_design_corrections'],0)
        self.assertEqual(result['unexpected_active_relation_losses'],0)
        self.assertTrue(result['pass'])

    def test_preservation_retains_unreviewed_loss_in_failure_count(self):
        self.withdraw['proof']['individual_semantic_review']=False;self.install_decisions()
        result=self.run_preservation()
        self.assertEqual(result['explicitly_verified_generic_kind_corrections'],0)
        self.assertEqual(result['unexpected_active_relation_losses'],1)
        self.assertFalse(result['pass'])

    def test_existing_fda_exception_is_retained_without_double_subtracting(self):
        native={'scope':'Native regulatory classification record','definition':'A retained regulated device classification.'}
        self.c.execute('UPDATE nodes SET data=? WHERE uid=?',(json.dumps(native),'wikidata:Q1'))
        # Insert the existing FDA ledger after the baseline fixtures are made;
        # no generic proof, role or source checksum is accepted for this record.
        original=self.tree.path_result
        self.tree.path_result=lambda uid:original(uid)
        self.c.executescript("""
          CREATE TABLE dataset_targets(dataset TEXT,class_id TEXT,label TEXT,target_uid TEXT);
          CREATE TABLE dataset_target_history(dataset TEXT,class_id TEXT,original_target_uid TEXT);
          CREATE TABLE usability_changes(id INTEGER PRIMARY KEY,stage TEXT,object_type TEXT,object_id TEXT,evidence TEXT);
        """)
        proof={'basis':'REGULATORY_CLASSIFICATION_RECORD_IS_NOT_A_PRODUCT_DESIGN','definition':native['definition']}
        self.c.execute('INSERT INTO usability_changes VALUES(1,?,?,?,?)',('hierarchy','typed','7',json.dumps(proof)))
        self.c.commit()
        with tempfile.TemporaryDirectory() as folder:
            baseline=Path(folder)/'before.sqlite'
            with sqlite3.connect(baseline) as old:
                self.c.backup(old);old.execute("UPDATE entity_relations SET status='ACTIVE'");old.commit()
            with contextlib.redirect_stdout(io.StringIO()):
                result=audit.preservation(self.tree,baseline,Path(folder)/'reports')
        self.assertEqual(result['explicitly_verified_invalid_design_corrections'],1)
        self.assertEqual(result['explicitly_verified_generic_kind_corrections'],0)
        self.assertEqual(result['unexpected_active_relation_losses'],0)
        self.assertTrue(result['pass'])


if __name__=='__main__':unittest.main()
