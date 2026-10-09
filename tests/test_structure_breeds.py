"""Catalogue facts cannot become identity, subtype, or visual-distance claims."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fineatlas.migration import Migration
from fineatlas.structure_breeds import (
    INPUT_NAME,LINKS_NAME,RELATION,SCHEMA,apply_structure_breeds,canonical,
    host_candidates,identifier_memberships,parse_fci_catalogue,sha,validate_host_review,
)


class StructureBreedTest(unittest.TestCase):
    def source_node(self, refs=('FCI:122',)):
        return {'id':'http://purl.obolibrary.org/obo/VBO_001','lbl':'Labrador Retriever (Dog)',
                'meta':{'xrefs':[{'val':r} for r in refs]}}

    def catalogue(self):
        return {'source_version':'frozen','standards':{
            '122':[{'native_group_path':['group8','section8.1']}],
            '80':[{'native_group_path':['group9','section9.3']}]}}

    def test_same_name_without_registry_identifier_is_not_admitted(self):
        rows,status=identifier_memberships(self.source_node(()),self.catalogue())
        self.assertEqual(rows,[])
        self.assertEqual(status,'NO_SOURCE_FCI_IDENTIFIER')

    def test_identifier_join_preserves_native_uid_and_relation_semantics(self):
        rows,status=identifier_memberships(self.source_node(),self.catalogue())
        self.assertEqual({r['group_uid'] for r in rows},{'group8','section8.1'})
        self.assertTrue(all(r['proof']['identity_merge_authorized'] is False for r in rows))
        self.assertTrue(all(r['proof']['is_class_inclusion'] is False for r in rows))

    def test_cross_group_ambiguity_and_unknown_registry_ids_fail_closed(self):
        rows,status=identifier_memberships(self.source_node(('FCI:122','FCI:80')),self.catalogue())
        self.assertEqual(rows,[])
        self.assertEqual(status,'INCOMPATIBLE_ORGANIZATION_GROUP_SCOPES')
        rows,status=identifier_memberships(self.source_node(('FCI:999',)),self.catalogue())
        self.assertEqual(rows,[])

    def test_variety_ambiguity_retains_only_shared_organization_container(self):
        catalogue=self.catalogue()
        catalogue['standards']['122'].append({'native_group_path':['group8','othersection']})
        rows,status=identifier_memberships(self.source_node(),catalogue)
        self.assertEqual([r['group_uid'] for r in rows],['group8'])

    def test_scientific_lemma_is_candidate_evidence_and_requires_scope_review(self):
        source={'id':'http://purl.obolibrary.org/obo/NCBITaxon_9685','lbl':'Felis catus',
                'meta':{'basicPropertyValues':[{'pred':'http://purl.obolibrary.org/obo/ncbitaxon#has_rank','val':'NCBITaxon_species'}]}}
        wordnet=[{'uid':'wn:cat','label':'domestic cat','description':'a domestic feline',
                  'data':json.dumps({'labels':['Felis_catus']})}]
        candidate=host_candidates([source],wordnet)[0]
        with self.assertRaisesRegex(ValueError,'individual'):
            validate_host_review(candidate,{'status':'CANDIDATE_ONLY'})
        review={'status':'APPROVED_TYPE_INCLUSION','scope_reason':'Source species is included in domestic feline type',
                'target_uid':'wn:cat','is_class_inclusion':True,'identity_merge_authorized':False}
        self.assertEqual(validate_host_review(candidate,review)['uid'],'wn:cat')
        review['identity_merge_authorized']=True
        with self.assertRaises(ValueError):validate_host_review(candidate,review)
        wordnet[0]['data']=json.dumps({'labels':['cat']})
        self.assertEqual(host_candidates([source],wordnet)[0]['candidates'],[])

    def frozen_pages(self, directory, *, duplicate=False):
        manifest=[]
        for group in range(1,11):
            standard=101 if duplicate else group+100
            raw=(f'<h2>Group {group} : Native group {group}</h2><ul><li>'
                 '<span id="ContentPlaceHolder1_SectionsRepeater_SectionLabel_0">Section 1 : Native section</span>'
                 f'<a class="nom" href="/en/nomenclature/BREED-{standard}.html">Breed ({standard})</a>'
                 '</li></ul>').encode()
            path=directory/f'group-{group}.html';path.write_bytes(raw)
            manifest.append({'group':group,'url':f'https://www.fci.be/group/{group}',
                             'path':path.name,'sha256':sha(raw)})
        (directory/'fci-manifest.json').write_text(json.dumps(manifest))

    def test_complete_official_groups_parse_sections_without_class_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.frozen_pages(root)
            parsed=parse_fci_catalogue(root)
            self.assertEqual(len(parsed['groups']),20)
            self.assertEqual(len(parsed['standards']),10)
            self.assertTrue(all(g['proof']['is_class_inclusion'] is False for g in parsed['groups']))
            self.assertTrue(all(parsed['source_version'] in g['group_uid'] for g in parsed['groups']))
            (root/'group-1.html').write_text('changed source')
            with self.assertRaisesRegex(ValueError,'hash changed'):parse_fci_catalogue(root)

    def test_official_identifier_cannot_occur_in_incompatible_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.frozen_pages(root,duplicate=True)
            with self.assertRaisesRegex(ValueError,'incompatible groups'):parse_fci_catalogue(root)

    def replay_fixture(self, root):
        database=root/'candidate.sqlite';inputs=root/'inputs';inputs.mkdir()
        c=sqlite3.connect(database)
        c.executescript('''
          CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
          CREATE TABLE nodes(uid TEXT UNIQUE,label TEXT,domain TEXT,domains TEXT,source TEXT,
            rank TEXT,description TEXT,data TEXT,layer TEXT,visibility TEXT,component_id INTEGER);
          CREATE TABLE edges(id INTEGER PRIMARY KEY,child_uid TEXT,parent_uid TEXT,relation TEXT,
            original_relation TEXT,facet_family TEXT,classification_basis TEXT,navigation_role TEXT,
            source TEXT,source_relation TEXT,confidence REAL,provenance TEXT,data TEXT,layer TEXT,
            status TEXT,reason TEXT);
          CREATE TABLE evidence(layer TEXT,id TEXT PRIMARY KEY,source TEXT,source_uri TEXT,
            retrieved TEXT,claim TEXT,data TEXT,sha256 TEXT);
          CREATE TABLE entity_relations(id INTEGER PRIMARY KEY,subject_uid TEXT,object_uid TEXT,
            relation TEXT,status TEXT,source TEXT,evidence_id TEXT,data TEXT);
          CREATE TABLE node_profiles(uid TEXT PRIMARY KEY,node_kind TEXT,domain TEXT,
            source_uri TEXT,evidence_id TEXT,attributes TEXT);
          CREATE TABLE aliases(alias TEXT,uid TEXT);
          CREATE TABLE components(id INTEGER PRIMARY KEY,wordnet_reachable INTEGER,depth INTEGER);
          INSERT INTO components VALUES(1,1,1),(2,1,0);
          INSERT INTO nodes VALUES('vbo:breed','Source breed','animal','[]','Vertebrate Breed Ontology','class','','{}','native','ACTIVE',1);
          INSERT INTO nodes VALUES('wn:host','Host type','animal','[]','wordnet31','class','','{}','native','ACTIVE',2);
        ''');c.commit();c.close()
        group={'group_uid':'fci:frozen:8','namespace':'fci','source_version':'frozen',
               'source_group_id':'8','label':'Native registered group','parent_group_uid':None,
               'source_uri':'https://www.fci.be/8','proof':{'is_class_inclusion':False}}
        member={'group_uid':group['group_uid'],'member_uid':'vbo:breed','source_member_id':'FCI:122',
                'relation':RELATION,'status':'ACTIVE','proof':{'identity_merge_authorized':False}}
        link={'op':'link','uid':'vbo:breed','parent':'wn:host','relation':'IS_A',
              'source':'reviewed host source','uri':'https://authority.example/host',
              'proof':{'basis':'Source explicitly includes reviewed host','is_class_inclusion':True,
                       'identity_merge_authorized':False}}
        payload={'schema':SCHEMA,'retained_nodes':[{'uid':'vbo:breed','label':'Source breed',
                   'source':'Vertebrate Breed Ontology','rank':'class','data_sha256':sha('{}')}],
                 'members':[member],'links':[link],'fci_catalogue':{'groups':[group],'source_version':'frozen'}}
        (inputs/INPUT_NAME).write_text(json.dumps(payload))
        (inputs/LINKS_NAME).write_text(canonical(link)+'\n')
        migration=Migration(database,inputs,root/'reports');migration.schema()
        return migration,payload

    def test_candidate_replay_separates_grouping_and_inclusion_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            m,payload=self.replay_fixture(Path(tmp))
            result=apply_structure_breeds(m)
            self.assertEqual(result['source_groups_added'],1)
            self.assertEqual(result['organization_memberships_added'],1)
            self.assertEqual(m.c.execute('SELECT count(*) FROM edges').fetchone()[0],1)
            self.assertEqual(tuple(m.c.execute('SELECT child_uid,parent_uid,relation FROM edges').fetchone()),
                             ('vbo:breed','wn:host','IS_A'))
            self.assertEqual(m.c.execute('SELECT relation FROM source_group_members').fetchone()[0],RELATION)
            self.assertEqual(m.c.execute("SELECT value FROM source_field_values WHERE field='organization_group'").fetchone()[0],'fci:frozen:8')
            self.assertEqual(m.c.execute('SELECT count(*) FROM nodes').fetchone()[0],2)
            self.assertEqual(apply_structure_breeds(m)['status'],'already_applied')
            m.meta('schema','FINEATLAS_SINGLE_DB_V1');m.meta('root_uid','wn:host')
            m.meta('usability_indexes_ready',True);m.c.commit()
            m.c.close()
            from fineatlas import FineAtlas
            with FineAtlas(Path(tmp)/'candidate.sqlite') as tree:
                groups=tree.source_groups_page('fci')
                self.assertEqual(groups['items'][0]['source_member_uids'],1)
                self.assertFalse(groups['items'][0]['classification_distance_applicable'])
                page=tree.source_group_members_page('fci:frozen:8')
                self.assertEqual(page['items'][0]['uid'],'vbo:breed')
                exported=tree.export_source_groups(Path(tmp)/'groups.jsonl')
                self.assertEqual(exported['source_memberships'],1)

    def test_protected_source_change_is_rejected_before_catalogue_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            m,payload=self.replay_fixture(Path(tmp))
            m.c.execute("UPDATE nodes SET data='{\"changed\":true}' WHERE uid='vbo:breed'");m.c.commit()
            with self.assertRaisesRegex(ValueError,'payload drift'):apply_structure_breeds(m)
            self.assertEqual(m.c.execute('SELECT count(*) FROM source_groups').fetchone()[0],0)
            self.assertEqual(m.c.execute('SELECT count(*) FROM source_group_members').fetchone()[0],0)
            m.c.close()


if __name__=='__main__':unittest.main()
