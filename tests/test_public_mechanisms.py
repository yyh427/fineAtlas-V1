"""Independent synthetic public-interface regressions across domains and views."""

import json, sqlite3, unittest
import test_single
from fineatlas import FineAtlas
from fineatlas.semantics import QueryLimitError


class PublicMechanismsTest(unittest.TestCase):
    setUp = test_single.TypedInterfaceTest.setUp
    tearDown = test_single.TypedInterfaceTest.tearDown

    def mutate(self, fn):
        self.tree.close()
        c = sqlite3.connect(self.path)
        fn(c)
        c.commit()
        c.close()
        self.tree = FineAtlas(self.path)

    def test_stats_uses_current_census_and_declares_aggregate_root(self):
        def change(c):
            c.execute("CREATE TABLE domain_entries(uid TEXT)")
            c.execute("INSERT INTO domain_entries VALUES('portal:1')")
        self.mutate(change)
        self.tree.metadata.update({
            "counts": {"nodes": 1}, "edge_statuses": {"ACTIVE": 999},
            "nodes": 7, "active_nodes": 6, "source_only_nodes": 1,
            "strict_classification_edges": 3, "aliases": 8, "canonical_domains": 1,
            "usability_role_counts": {"CLASS": 3, "MODEL_FAMILY": 1, "INSTANCE": 2},
            "usability_view_statistics": {
                "strict": {"class_root_source_uids": 2, "class_root_groups": 2,
                           "typed_terminal_root_uids": 1},
                "taxonomy": {"class_root_source_uids": 4, "class_root_groups": 3,
                             "typed_terminal_root_uids": 2}}})
        self.tree.relation_view = "taxonomy"
        stats = self.tree.stats()
        self.assertEqual(stats["counts"]["nodes"], 7)
        self.assertEqual(stats["counts"]["retained_classification_uids"], 4)
        self.assertEqual(stats["counts"]["classification_root_source_uids_in_view"], 4)
        self.assertEqual(stats["counts"]["strict_root_reachable_classification_uids"], 2)
        self.assertNotIn("edge_statuses", stats)
        self.tree.root_uid = "type:river"
        self.assertEqual(self.tree.stats()["statistics_root_uid"], "type:root")

    @staticmethod
    def add(c, uid, label, comp, parents=(), rank="class", kind=None):
        c.execute(
            "INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                uid,
                label,
                "independent",
                '["independent"]',
                "independent",
                rank,
                "Grounded synthetic kind",
                "{}",
                "fixture",
                "ACTIVE",
                comp,
            ),
        )
        c.execute(
            "INSERT INTO components VALUES(?,?,?,?,?)",
            (comp, int(bool(parents)), 1 if parents else None, None, None),
        )
        c.execute("INSERT INTO aliases VALUES(?,?)", (label.lower(), uid))
        if kind:
            c.execute(
                "INSERT INTO node_profiles VALUES(?,?,?,?,?,?)",
                (uid, kind, "independent", "https://example.org", "proof:1", "{}"),
            )
        for parent in parents:
            c.execute(
                "INSERT INTO edges(child_uid,parent_uid,relation,status,source,confidence,provenance,data) VALUES(?,?,?,?,?,?,?,?)",
                (uid, parent, "IS_A", "ACTIVE", "fixture", 1, '["proof:1"]', "{}"),
            )

    def test_portal_path_unknown_and_unreachable_are_distinct(self):
        self.tree.metadata["domain_roots"] = [
            {
                "domain": "water",
                "uid": "fineatlas-domain:water",
                "entry_uid": "fineatlas-domain:water",
                "root_uids": ["type:river"],
            }
        ]
        self.assertEqual(self.tree.path("fineatlas-domain:water"), [])
        self.assertEqual(
            self.tree.path_result("fineatlas-domain:water")["status"], "NAVIGATION_ONLY"
        )
        self.assertEqual(self.tree.path_result("absent")["status"], "NOT_FOUND")
        self.mutate(lambda c: self.add(c, "detached:1", "Disconnected object type", 20))
        self.assertEqual(self.tree.path_result("detached:1")["status"], "UNREACHABLE")
        self.assertFalse(self.tree.connection_status("detached:1")["root_reachable"])
        with self.assertRaises(ValueError):
            self.tree.path("type:river", anchors=["absent"])

    def test_scope_search_browse_and_instance_pages_agree(self):
        self.mutate(lambda c: self.add(c, "outside:1", "Same Name", 20, ("type:root",)))
        self.tree.metadata["domain_roots"] = [
            {
                "domain": "water",
                "uid": "fineatlas-domain:water",
                "entry_uid": "fineatlas-domain:water",
                "root_uids": ["type:river"],
            }
        ]
        found = self.tree.search("Same Name", domain="water")
        self.assertEqual({n["uid"] for n in found}, {"type:river", "geo:1"})
        self.assertNotIn(
            "outside:1", {n["uid"] for n in self.tree.domain_page("water")["items"]}
        )
        self.assertEqual(
            self.tree.domain_instances("water")["items"][0]["uid"], "geo:1"
        )
        self.assertEqual(self.tree.instances("water")[0]["uid"], "geo:1")
        with self.assertRaises(ValueError):
            self.tree.search("Same Name", domain="undefined")

    def test_language_fallback_preserves_source_and_alias_evidence(self):
        def change(c):
            c.execute(
                "CREATE TABLE node_names(uid TEXT,name TEXT,language TEXT,preferred INTEGER,source TEXT,evidence_id TEXT)"
            )
            c.executemany(
                "INSERT INTO node_names VALUES(?,?,?,?,?,?)",
                [
                    ("type:river", "河流", "zh", 1, "fixture", "proof:1"),
                    ("type:river", "river", "en", 1, "fixture", "proof:1"),
                    (
                        "legacy:mixed",
                        "Scientificus example",
                        "mul",
                        1,
                        "fixture",
                        "proof:1",
                    ),
                ],
            )

        self.mutate(change)
        with FineAtlas(self.path, language="zh") as tree:
            self.assertEqual(tree.node("type:river")["label"], "河流")
            self.assertEqual(tree.node("type:river")["source_label"], "Same Name")
            self.assertEqual(
                tree.aliases("type:river", language="zh")[0]["evidence_id"], "proof:1"
            )
            self.assertEqual(tree.node("legacy:mixed")["label_language"], "mul")

    def test_stable_keyset_pages_and_cursor_scope(self):
        def change(c):
            for i in range(9):
                self.add(c, f"page:{i:03d}", f"Page item {i}", 20 + i, ("type:root",))

        self.mutate(change)
        cursor = None
        uids = []
        while True:
            page = self.tree.search_page("page", 3, cursor=cursor)
            uids.extend(n["uid"] for n in page["items"])
            cursor = page["next_cursor"]
            if not cursor:
                break
        self.assertEqual(uids, [f"page:{i:03d}" for i in range(9)])
        cursor = self.tree.search_page("page", 3)["next_cursor"]
        with self.assertRaises(ValueError):
            self.tree.search_page("other", 3, cursor=cursor)
        with FineAtlas(self.path, relation_view="taxonomy") as tree:
            with self.assertRaises(ValueError):
                tree.search_page("page", 3, cursor=cursor)
        self.assertTrue(self.tree.search("page", 2).has_more)

    def test_dag_multiple_lcas_directed_distance_and_ancestors(self):
        def change(c):
            self.add(c, "independent:a", "Type A", 20, ("type:root",))
            self.add(c, "independent:b", "Type B", 21, ("type:root",))
            self.add(
                c,
                "independent:left",
                "Terminal left",
                22,
                ("independent:a", "independent:b"),
            )
            self.add(
                c,
                "independent:right",
                "Terminal right",
                23,
                ("independent:a", "independent:b"),
            )

        self.mutate(change)
        self.assertEqual(
            {
                n["uid"]
                for n in self.tree.lca("independent:left", "independent:right")["items"]
            },
            {"independent:a", "independent:b"},
        )
        self.assertEqual(
            self.tree.distance("independent:left", "independent:right")["distance"], 2
        )
        self.assertEqual(
            self.tree.distance("independent:left", "type:root", direction="upward")[
                "distance"
            ],
            2,
        )
        self.assertEqual(
            self.tree.distance("type:root", "independent:left", direction="downward")[
                "distance"
            ],
            2,
        )
        self.assertEqual(
            self.tree.distance(
                "independent:left", "independent:right", direction="upward"
            )["status"],
            "UNREACHABLE",
        )
        self.assertEqual(
            {n["uid"] for n in self.tree.ancestors("independent:left")},
            {"independent:a", "independent:b", "type:root"},
        )
        with self.assertRaises(QueryLimitError):
            self.tree.distance("independent:left", "independent:right", max_nodes=1)

    def test_view_rules_and_task_requirements_do_not_change_identity(self):
        self.mutate(
            lambda c: c.execute(
                "UPDATE node_profiles SET attributes=? WHERE uid=?",
                (json.dumps({"allowed_views": ["taxonomy"]}), "attr:1"),
            )
        )
        self.assertEqual(
            self.tree.path_result("attr:1")["status"], "VIEW_NOT_APPLICABLE"
        )
        self.assertEqual(self.tree.exact("斑纹"), [])
        with FineAtlas(self.path, relation_view="taxonomy") as tree:
            self.assertTrue(tree.connection_status("attr:1")["root_reachable"])
            self.assertTrue(
                tree.eligibility("attr:1", identity_verified=True)["usable"]
            )
            self.assertFalse(
                tree.eligibility(
                    "attr:1", "strict_classification", identity_verified=True
                )["usable"]
            )
            self.assertFalse(
                tree.eligibility("attr:1", identity_verified=False)["usable"]
            )
        self.assertFalse(
            self.tree.eligibility("geo:1", "species", identity_verified=True)["usable"]
        )
        self.assertEqual(
            self.tree.path_result("legacy:mixed")["status"], "VIEW_NOT_APPLICABLE"
        )

    def test_custom_root_filters_global_search_consistently(self):
        self.mutate(lambda c: self.add(c, "outside:1", "Same Name", 20, ("type:root",)))
        with FineAtlas(self.path, root="type:river") as tree:
            self.assertEqual(
                {n["uid"] for n in tree.search("same name")}, {"type:river", "geo:1"}
            )
            self.assertFalse(tree.connection_status("outside:1")["root_reachable"])
            self.assertEqual(tree.path_result("type:river")["status"], "ROOT")

    def test_native_dataset_label_survives_absent_world_type_mapping(self):
        def change(c):
            c.execute("ALTER TABLE dataset_targets ADD COLUMN label TEXT")
            c.execute("ALTER TABLE dataset_targets ADD COLUMN target_uid TEXT")
            c.execute("ALTER TABLE dataset_targets ADD COLUMN evidence_ids TEXT DEFAULT '[]'")
            c.execute("ALTER TABLE dataset_targets ADD COLUMN provenance TEXT DEFAULT '{}'")
            c.execute("INSERT INTO dataset_targets(dataset,class_id,decision_status,label,target_uid) VALUES('native-catalog','1','NATIVE_LABEL_ONLY','Unmapped native label','native-catalog:1')")
        self.mutate(change)
        for view in ('strict','taxonomy','membership'):
            with self.subTest(view=view), FineAtlas(self.path,relation_view=view) as tree:
                labels = tree.task_labels('native-catalog',requirement='native_label',usable_only=True)
                self.assertEqual([r['class_id'] for r in labels],['1'])
                self.assertFalse(labels[0]['identity_verified'])
                self.assertTrue(labels[0]['native_label_admission']['usable'])
                self.assertEqual(tree.task_labels('native-catalog',requirement='hierarchy',usable_only=True),[])
                self.assertEqual(tree.task_labels('native-catalog',requirement='strict_classification',usable_only=True),[])

    def test_custom_root_intersects_domain_instances_and_exports(self):
        def change(c):
            self.add(c, 'outside:1', 'Same Name', 20, ('type:root',))
            self.add(c, 'outside:instance', 'Same Name', 21, rank='instance', kind='INSTANCE')
            c.execute("INSERT INTO entity_relations VALUES(4,'outside:instance','outside:1','INSTANCE_OF','ACTIVE','fixture','proof:1','{}')")
            c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', ('domain_roots',json.dumps([{'domain':'mixed','uid':'fineatlas-domain:mixed','entry_uid':'fineatlas-domain:mixed','root_uids':['type:root']}])) )
        self.mutate(change)
        expected = {'type:river','geo:1','attr:1','cat:1'}
        for materialized in (False, True):
            if materialized:
                def indexes(c):
                    c.executescript('''
                      CREATE TABLE domain_registry(domain_id INTEGER PRIMARY KEY,canonical_name TEXT,entry_uid TEXT,label TEXT,root_uids TEXT,description TEXT);
                      CREATE TABLE domain_aliases(alias TEXT PRIMARY KEY,domain_id INTEGER,provenance TEXT);
                      CREATE TABLE domain_members(domain_id INTEGER,view TEXT,uid TEXT,role TEXT,depth INTEGER,PRIMARY KEY(domain_id,view,uid));
                      CREATE TABLE view_paths(view TEXT,component_id INTEGER,depth INTEGER,parent_component_id INTEGER,witness_id INTEGER,contains_terminal INTEGER,PRIMARY KEY(view,component_id));
                    ''')
                    c.execute("INSERT INTO domain_registry VALUES(1,'mixed','fineatlas-domain:mixed','Mixed scope','[\"type:root\"]','Fixture')")
                    c.execute("INSERT INTO domain_aliases VALUES('mixed',1,'{}')")
                    for uid,role,comp in [('type:root','CLASS',0),('type:river','CLASS',1),('geo:1','INSTANCE',2),('attr:1','ATTRIBUTE',3),('cat:1','DATASET_CATEGORY',5),('outside:1','CLASS',20),('outside:instance','INSTANCE',21)]:
                        c.execute('INSERT INTO domain_members VALUES(?,?,?,?,?)',(1,'strict',uid,role,0))
                        c.execute('INSERT INTO view_paths VALUES(?,?,?,?,?,?)',('strict',comp,0,None,None,0))
                self.mutate(indexes)
            with self.subTest(materialized=materialized), FineAtlas(self.path,root='type:river') as tree:
                self.assertEqual({n['uid'] for n in tree.domain_page('mixed')['items']},expected)
                self.assertEqual({n['uid'] for n in tree.search('same name',domain='mixed')},{'type:river','geo:1'})
                self.assertEqual(tree.search('same name',domain='source:independent'),[])
                self.assertEqual([n['uid'] for n in tree.domain_instances('mixed')['items']],['geo:1'])
                self.assertEqual([n['uid'] for n in tree.instances('type:root')],['geo:1'])
                self.assertEqual(tree.instances('outside:1'),[])
                self.assertEqual([n['uid'] for n in tree.domain_children('mixed')],['type:river'])
                path = self.path.parent/'export.jsonl'
                tree.export_domain('mixed',path)
                self.assertEqual({json.loads(line)['node']['uid'] for line in path.read_text().splitlines()},expected)

    def test_identity_corruption_and_incomplete_migration_are_not_hidden(self):
        def change(c):
            c.execute("UPDATE nodes SET component_id=1 WHERE uid='legacy:mixed'")
            c.execute(
                "INSERT INTO node_profiles VALUES('legacy:mixed','CLASS','fixture','https://example.org','proof:1','{}')"
            )

        self.mutate(change)
        with self.assertRaises(RuntimeError):
            self.tree.path("legacy:mixed")
        with self.assertRaises(ValueError):
            self.mutate(
                lambda c: c.execute(
                    "INSERT INTO metadata VALUES(?,?)",
                    ("usability_indexes_ready", "false"),
                )
            )

    def test_migrated_witnesses_domains_and_multilingual_entry_aliases(self):
        def change(c):
            c.executescript("""
            CREATE TABLE view_paths(view TEXT,component_id INTEGER,depth INTEGER,parent_component_id INTEGER,witness_id INTEGER,contains_terminal INTEGER,PRIMARY KEY(view,component_id));
            CREATE TABLE view_terminal_connections(view TEXT,uid TEXT,class_uid TEXT,witness_relation_id INTEGER,depth INTEGER,PRIMARY KEY(view,uid));
            CREATE TABLE domain_registry(domain_id INTEGER PRIMARY KEY,canonical_name TEXT,entry_uid TEXT,label TEXT,root_uids TEXT,description TEXT);
            CREATE TABLE domain_aliases(alias TEXT PRIMARY KEY,domain_id INTEGER,provenance TEXT);
            CREATE TABLE domain_members(domain_id INTEGER,view TEXT,uid TEXT,role TEXT,depth INTEGER,PRIMARY KEY(domain_id,view,uid));
            """)
            c.executemany(
                "INSERT INTO view_paths VALUES(?,?,?,?,?,?)",
                [
                    ("strict", 0, 0, None, None, 0),
                    ("strict", 1, 1, 0, 1, 0),
                    ("strict", 2, 2, 1, -1, 1),
                ],
            )
            c.execute(
                "INSERT INTO view_terminal_connections VALUES('strict','geo:1','type:river',1,2)"
            )
            c.execute(
                "INSERT INTO domain_registry VALUES(?,?,?,?,?,?)",
                (
                    1,
                    "water_bodies",
                    "fineatlas-domain:water_bodies",
                    "water types",
                    json.dumps(["type:river"]),
                    "Native declared scope",
                ),
            )
            c.executemany(
                "INSERT INTO domain_aliases VALUES(?,?,?)",
                [("water_bodies", 1, "{}"), ("water", 1, "{}"), ("河流", 1, "{}")],
            )
            c.executemany(
                "INSERT INTO domain_members VALUES(?,?,?,?,?)",
                [
                    (1, "strict", "type:river", "CLASS", 0),
                    (1, "strict", "geo:1", "INSTANCE", 1),
                ],
            )
            c.execute(
                "INSERT INTO metadata VALUES(?,?)", ("usability_indexes_ready", "true")
            )

        self.mutate(change)
        for name in ("water_bodies", "fineatlas-domain:water_bodies", "water", "河流"):
            self.assertEqual(self.tree.domain(name)["domain"], "water_bodies")
            self.assertEqual(
                self.tree.domain_instances(name)["items"][0]["uid"], "geo:1"
            )
            self.assertEqual(
                {x["uid"] for x in self.tree.search("Same Name", domain=name)},
                {"type:river", "geo:1"},
            )
        result = self.tree.path_result("geo:1")
        self.assertEqual(
            [x["edge"]["relation"] for x in result["path"]], ["IS_A", "INSTANCE_OF"]
        )
        state = self.tree.connection_status("geo:1")
        self.assertTrue(state["root_reachable"])
        self.assertFalse(state["classification_root_reachable"])
        self.assertTrue(self.tree.node("geo:1")["typed_root_reachable"])

    def test_peer_taxonomic_rank_is_evidence_separate_from_native_rank(self):
        def change(c):
            self.add(c, "taxon:unranked", "Taxon with native ID", 20, ("type:root",))
            c.execute("UPDATE nodes SET rank='' WHERE uid='taxon:unranked'")
            self.add(c, "taxon:species", "Native species", 21, rank="species")
            c.execute("UPDATE nodes SET component_id=20 WHERE uid='taxon:species'")

        self.mutate(change)
        n = self.tree.node("taxon:unranked")
        self.assertEqual(n["native_rank"], "")
        self.assertEqual(n["normalized_rank"], "species")
        self.assertTrue(
            self.tree.eligibility(n["uid"], "species", identity_verified=True)["usable"]
        )

        def conflict(c):
            self.add(c, "taxon:genus", "Conflicting source genus", 22, rank="genus")
            c.execute("UPDATE nodes SET component_id=20 WHERE uid='taxon:genus'")

        self.mutate(conflict)
        self.assertEqual(
            self.tree.node("taxon:unranked")["rank_status"], "CONFLICT_REVIEW"
        )
        self.assertFalse(
            self.tree.eligibility("taxon:unranked", "species", identity_verified=True)[
                "usable"
            ]
        )

    def test_raw_source_rank_and_definition_are_recovered_without_mutation(self):
        def change(c):
            self.add(c, "taxon:raw", "Source rank only", 20, ("type:root",))
            c.execute(
                "UPDATE nodes SET rank='',description='',data=? WHERE uid='taxon:raw'",
                (
                    json.dumps(
                        {
                            "taxonomic_ranks": ["species"],
                            "description": "Native factual definition",
                        }
                    ),
                ),
            )

        self.mutate(change)
        n = self.tree.node("taxon:raw")
        self.assertEqual(n["normalized_rank"], "species")
        self.assertEqual(n["description"], "Native factual definition")
        self.assertTrue(
            self.tree.eligibility(n["uid"], "species", identity_verified=True)["usable"]
        )
        self.assertEqual(
            self.tree.con.execute(
                "SELECT rank,description FROM nodes WHERE uid='taxon:raw'"
            ).fetchone()[1],
            "",
        )

    def test_custom_root_does_not_use_unknown_peer_class_edges(self):
        def change(c):
            self.add(c, "unrelated:parent", "Disconnected parent", 20)
            self.add(c, "eligible:class", "Admitted record", 21)
            self.add(
                c,
                "ineligible:unknown",
                "Uncertain peer",
                22,
                ("unrelated:parent",),
                rank="type_or_product_model",
            )
            c.execute("UPDATE nodes SET component_id=21 WHERE uid='ineligible:unknown'")

        self.mutate(change)
        with FineAtlas(self.path, root="unrelated:parent") as tree:
            self.assertFalse(
                tree.connection_status("eligible:class")["class_root_reachable_in_view"]
            )
            self.assertEqual(
                tree.path_result("eligible:class")["status"], "UNREACHABLE"
            )

    def test_conceptual_identity_peers_share_real_design_connections(self):
        def change(c):
            self.add(c, "design:class", "Native ontology representation", 20)
            self.add(
                c,
                "design:model",
                "Native model representation",
                21,
                rank="model",
                kind="MODEL",
            )
            c.execute("UPDATE nodes SET component_id=20 WHERE uid='design:model'")
            c.execute(
                "INSERT INTO bridges VALUES(90,'design:class','design:model','SAME_CONCEPT','ACTIVE',1,'{\"native_identifier\":\"fixture-design-1\"}')"
            )
            c.execute(
                "INSERT INTO entity_relations VALUES(90,'design:model','type:river','DESIGN_TYPE_OF','ACTIVE','native-model-scope','proof:1','{}')"
            )

        self.mutate(change)
        path = self.tree.path_result("design:class")
        self.assertEqual(path["status"], "CONNECTED")
        self.assertEqual(
            self.tree.distance("design:class", "type:root", direction="upward")[
                "distance"
            ],
            2,
        )
        self.assertEqual(
            {x["uid"] for x in self.tree.ancestors("design:class")},
            {"type:river", "type:root"},
        )
        self.assertEqual(self.tree.node("design:class")["normalized_role"], "CLASS")
        self.assertFalse(
            self.tree.eligibility("design:class", "model", identity_verified=True)[
                "usable"
            ]
        )
