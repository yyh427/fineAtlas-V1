"""Professional hierarchy guards cover source rank and terminal granularity."""
import sqlite3,unittest
from fineatlas.hierarchy import validate_link_roles,reconcile_instance_endpoints
from fineatlas.nominal import WordNetKinds
from fineatlas.semantics import edge_predicate,role_expression,role_for_rank

class HierarchyContractsTest(unittest.TestCase):
    def test_later_instance_decision_excludes_earlier_isa_without_changing_cached_views(self):
        c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
        c.executescript('''CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,status TEXT,relation TEXT,data TEXT,source TEXT,reason TEXT);
          CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,attributes TEXT,source_uri TEXT);
          CREATE TABLE normalization_roles(uid TEXT,canonical_role TEXT,evidence_id TEXT);
          CREATE TABLE view_roots(witness_id INTEGER);CREATE TABLE view_paths(witness_id INTEGER);
          CREATE TABLE hierarchy_decisions(id TEXT PRIMARY KEY,operation TEXT,subject_uid TEXT,object_uid TEXT,evidence_id TEXT,payload TEXT);
          INSERT INTO edges VALUES(1,'named-aquifer','water-facility','ACTIVE','IS_A','{"eligible_for_final_dag":true}','original assertion','');
          INSERT INTO edges VALUES(2,'physical-subtype','generic-type','ACTIVE','IS_A','{}','native inclusion','');
          INSERT INTO node_profiles VALUES('named-aquifer','INSTANCE','{"role_status":"VERIFIED"}','https://example.org/particular-place');
          INSERT INTO normalization_roles VALUES('named-aquifer','INSTANCE','independent-location-proof');
          INSERT INTO view_paths VALUES(2);''')
        class Migration:
            def __init__(self):self.c=c;self.changes=[];self.metadata={}
            def evidence(self,*args):return 'endpoint-evidence'
            def change(self,*args):self.changes.append(args)
            def meta(self,k,v):self.metadata[k]=v
        m=Migration();result=reconcile_instance_endpoints(m)
        self.assertTrue(result['graph_admission_unchanged'])
        self.assertEqual(c.execute('SELECT child_uid,parent_uid,status FROM edges WHERE id=1').fetchone()[:],('named-aquifer','water-facility','HIERARCHY_SUPERSEDED'))
        self.assertEqual(c.execute('SELECT status FROM edges WHERE id=2').fetchone()[0],'ACTIVE')
        self.assertEqual(c.execute('SELECT witness_id FROM view_paths').fetchone()[0],2)
        self.assertEqual(reconcile_instance_endpoints(m)['superseded_instance_inclusions'],0)
        c.execute("UPDATE edges SET status='ACTIVE' WHERE id=1");c.execute('INSERT INTO view_roots VALUES(1)')
        with self.assertRaises(ValueError):reconcile_instance_endpoints(m)

    def test_native_car_line_classification_does_not_certify_physical_subtype(self):
        c=sqlite3.connect(':memory:')
        c.executescript("CREATE TABLE edges(status TEXT,relation TEXT); INSERT INTO edges VALUES('TYPED_ACTIVE','NATIVE_CLASSIFICATION_PARENT');")
        self.assertEqual(c.execute('SELECT count(*) FROM edges e WHERE '+edge_predicate('strict')).fetchone()[0],0)
        self.assertEqual(c.execute('SELECT count(*) FROM edges e WHERE '+edge_predicate('taxonomy')).fetchone()[0],1)
        validate_link_roles('REGULATED_AS','CONFIGURATION','CLASS')
        with self.assertRaises(ValueError):validate_link_roles('REGULATED_AS','CLASS','CLASS')

    def test_source_rank_is_not_product_grain(self):
        self.assertEqual(role_for_rank('series','wfo'),'CLASS')
        self.assertEqual(role_for_rank('series','manufacturer'),'MODEL_FAMILY')
        c=sqlite3.connect(':memory:')
        c.executescript('CREATE TABLE nodes(uid TEXT,rank TEXT,source TEXT); CREATE TABLE node_profiles(uid TEXT,node_kind TEXT);')
        c.executemany('INSERT INTO nodes VALUES(?,?,?)',[('plant','series','wfo'),('product','series','manufacturer'),('explicit','series','wfo')])
        c.execute("INSERT INTO node_profiles VALUES('explicit','BIOLOGICAL_VARIANT')")
        got=dict(c.execute('SELECT n.uid,'+role_expression('n','p')+' FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid'))
        self.assertEqual(got,{'plant':'CLASS','product':'MODEL_FAMILY','explicit':'BIOLOGICAL_VARIANT'})

    def test_named_design_alias_cannot_be_a_generic_parent(self):
        c=sqlite3.connect(':memory:')
        c.executescript("CREATE TABLE nodes(uid TEXT,label TEXT,description TEXT,data TEXT,visibility TEXT DEFAULT 'ACTIVE'); CREATE TABLE node_profiles(uid TEXT,node_kind TEXT); CREATE TABLE aliases(alias TEXT,uid TEXT);")
        c.executemany('INSERT INTO nodes(uid,label,description,data) VALUES(?,?,?,?)',[
            ('pc','Toshiba T3100','A portable computer manufactured by Toshiba in 1986.','{}'),
            ('gpu','graphics processing unit','A graphics processing unit is a specialized electronic circuit used for model training.','{}'),
            ('printer','3D printer','A machine used to manufacture three-dimensional objects.','{}'),
            ('place','Estonia','','{}'),
            ('ship','Marella Explorer 2','Marella Explorer 2 was the lead ship of the Century class of cruise ships.','{}'),
            ('family','Brand Smartwatch','Manufacturer model family','{}')])
        k=WordNetKinds(c)
        self.assertFalse(k.generic_type('pc'))
        self.assertFalse(k.generic_type('family'))
        self.assertFalse(k.generic_type('place'))
        self.assertFalse(k.generic_type('ship'))
        self.assertTrue(k.generic_type('gpu'))
        self.assertTrue(k.generic_type('printer'))

    def test_refinements_preserve_exact_terminal_scope(self):
        for rel,a,b in [('IS_A','CLASS','CLASS'),('DESIGN_TYPE_OF','MODEL','CLASS'),('DESIGN_TYPE_OF','MODEL_FAMILY','CLASS'),('CONFIGURATION_TYPE_OF','CONFIGURATION','CLASS'),('CONFIGURATION_OF','CONFIGURATION','MODEL'),('INSTANCE_OF','INSTANCE','MODEL')]:
            validate_link_roles(rel,a,b)
        for rel,a,b in [('IS_A','MODEL','CLASS'),('IS_A','INSTANCE','CLASS'),('DESIGN_TYPE_OF','CLASS','MODEL'),('CONFIGURATION_TYPE_OF','MODEL_FAMILY','CLASS'),('PART_OF','CLASS','CLASS')]:
            with self.subTest(relation=rel,child=a,parent=b),self.assertRaises(ValueError):validate_link_roles(rel,a,b)
