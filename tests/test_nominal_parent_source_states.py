"""Nominal links must not rewrite immediate-parent raw claims or their history."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import structure_nominal_parent_claim_snapshot as nominal
import test_complete_parent_source_states as complete_fixture


class NominalDirectParentSourceControls(unittest.TestCase):
    def setUp(self):
        self.old=complete_fixture.SourceStateControls();self.old.setUp();self.addCleanup(self.old.doCleanups)
        self.db,self.rows,self.inputs=self.old.db,self.old.rows,self.old.inputs
    def check(self):return nominal.compare_current_parent_assertion_rows(self.db,self.rows,self.inputs)
    def test_exact_rejected_and_scope_review_siblings_survive_all_three_generations(self):
        answer=self.check();self.assertEqual(answer['historical_source_rows_checked'],3);self.assertEqual(answer['exact_later_source_status_permissions_used'],0)
    def test_nominal_scope_cannot_rewrite_old_rejected_reason(self):
        self.db.execute('UPDATE entity_relations SET reason="nominal scope"WHERE id=1')
        with self.assertRaises(ValueError):self.check()
    def test_nominal_scope_cannot_blanket_normalize_rejected_statuses(self):
        self.db.execute('UPDATE entity_relations SET status="SOURCE_SCOPE_REVIEW"WHERE id=1')
        with self.assertRaises(ValueError):self.check()
    def test_nominal_scope_cannot_promote_a_previous_scope_review(self):
        self.db.execute('UPDATE entity_relations SET status="ACTIVE"WHERE id=3')
        with self.assertRaises(ValueError):self.check()
    def test_nominal_scope_cannot_rewrite_raw_producer_or_data(self):
        for field,value in [('source','Nominal new source'),('data','{}')]:
            with self.subTest(field=field):
                self.db.execute('UPDATE entity_relations SET '+field+'=?WHERE id=3',(value,))
                with self.assertRaises(ValueError):self.check()
                self.db.execute('UPDATE entity_relations SET '+field+'=?WHERE id=3',(self.old.old[2][field],))
    def test_deleted_or_new_same_content_sibling_is_rejected(self):
        row={**self.old.old[0],'id':4};self.db.execute('INSERT INTO entity_relations VALUES(:id,:subject_uid,:object_uid,:relation,:source,:data,:status,:reason,:evidence_id)',row)
        with self.assertRaises(ValueError):self.check()
        self.db.execute('DELETE FROM entity_relations WHERE id IN (4,1)')
        with self.assertRaises(ValueError):self.check()
    def test_identical_canonical_scope_review_cannot_mask_changed_rejected_sibling(self):
        self.db.execute('UPDATE entity_relations SET evidence_id="replacement"WHERE id=2')
        with self.assertRaises(ValueError):self.check()
    def test_review_permission_from_old_source8_does_not_allow_a_new_source9_mutation(self):
        self.db.execute('UPDATE entity_relations SET status="ACTIVE"WHERE id=1')
        self.db.execute('INSERT INTO usability_changes VALUES(?,?,?,?,?,?)',('complete_owned_type_repairs','typed_scope_review','1','{}','{}','{}'))
        with self.assertRaises(ValueError):self.check()


class PortableSnapshotBindingControls(unittest.TestCase):
    """Validate the actual public snapshot schema without fake current-parent aliases."""
    def setUp(self):
        import tempfile,json,gzip
        from types import SimpleNamespace
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.foundation=self.root/'source8-foundation';self.foundation.mkdir();(self.foundation/'parent-assertion-states.jsonl.gz').write_bytes(b'original independently generated c933 bytes')
        (self.foundation/'foundation-claims-registry.json').write_text('{}')
        folder=self.root/'builds/primary';(folder/'source-parent').mkdir(parents=True)
        self.original_sha='a'*64
        (folder/'source-parent/started_fingerprints.json').write_text(json.dumps({'inputs':{'structure_source_contracts.json.gz':self.original_sha}}))
        lineage={'parent_revision':'source8','parent_database_sha256':'source8-whole-sha','parent_receipt_sha256':'source8-receipt-sha','parent_integrity_sha256':'source8-integrity-sha'}
        (folder/'parent_lineage.json').write_text(json.dumps(lineage));(folder/'build_complete.json').write_text('{"revision":"source9"}')
        self.old_header={'candidate_revision':'source8','parent_revision':'c933','parent_database_sha256':'c933-whole-sha','quarantine_manifest_sha256':self.original_sha}
        self.rows=[{'table':'entity_relations','canonical_id':n,'locator':{'subject_uid':'u-'+str(n),'source_assertion_multiplicity':1},'rows':[{'id':n,'status':'SOURCE_SCOPE_REVIEW','reason':None,'row_sha256':'b'*64}]}for n in range(1,81580)]
        self.header={'schema':nominal.SCHEMA,'pass':True,'candidate_revision':'source9',**lineage,
            'actual_parent_integrity_sha256':lineage['parent_integrity_sha256'],
            'actual_child_build_receipt_sha256':nominal.digest(folder/'build_complete.json'),'actual_child_lineage_sha256':nominal.digest(folder/'parent_lineage.json'),
            'c933_foundation_snapshot_sha256':nominal.digest(self.foundation/'parent-assertion-states.jsonl.gz'),'c933_foundation_header':self.old_header,
            'grandparent_revision':'c933','grandparent_database_sha256':'c933-whole-sha','quarantine_manifest_sha256':self.original_sha,
            'source8_exact_transition_comparison':{'pass':True,'canonical_assertions':81579,'historical_source_rows_checked':81579},'source_assertion_rows':81579}
        self.snapshot_path=self.root/'parent-assertion-states.jsonl.gz';self.snapshot_path.write_bytes(b'actual independent direct-parent derived snapshot')
        self.support=SimpleNamespace(root=self.root,value={'database_revision':'source9','parent_assertion_snapshot_sha256':nominal.digest(self.snapshot_path),'parent_assertion_snapshot_binding':self.header})
    def verify(self,header=None,rows=None):
        from unittest.mock import patch
        with patch.object(nominal,'read_snapshot',return_value=(header or self.header,self.rows if rows is None else rows)),patch.object(nominal,'verify_complete_parent_snapshot',return_value=(self.old_header,self.rows)),patch.object(nominal,'require_nominal_scope_build',return_value={'revision':'source9'}):
            return nominal.verify_nominal_parent_snapshot(self.support)
    def test_exact_three_generation_snapshots_bind(self):
        header,rows=self.verify();self.assertEqual(header['grandparent_revision'],'c933');self.assertEqual(len(rows),81579)
    def test_duplicate_direct_sibling_is_rejected_even_with_old_unique_id_set(self):
        import copy
        rows=copy.deepcopy(self.rows);rows[0]['rows'].append(dict(rows[0]['rows'][0]))
        with self.assertRaises(ValueError):self.verify(rows=rows)
    def test_historical_c933_header_cannot_be_rebound_to_source9(self):
        import copy
        header=copy.deepcopy(self.header);header['c933_foundation_header']['candidate_revision']='source9';self.support.value['parent_assertion_snapshot_binding']=header
        with self.assertRaises(ValueError):self.verify(header=header)
    def test_whole_source_input_hash_and_actual_transition_count_must_match(self):
        import copy
        for field,value in [('quarantine_manifest_sha256','c'*64),('source_assertion_rows',81578)]:
            header=copy.deepcopy(self.header);header[field]=value;self.support.value['parent_assertion_snapshot_binding']=header
            with self.assertRaises(ValueError):self.verify(header=header)

if __name__=='__main__':unittest.main()
