"""Bounded direct-link browsing; catalogue facets never become graph parents."""

from __future__ import annotations

import base64
import json

from .semantics import ROLE_ALIASES, VIEW_BITS


FACETS = frozenset({
    "source", "manufacturer", "native_model", "base_model", "year",
    "aircraft_type", "engine_type", "vehicle_class", "country", "admin1",
    "series", "catalogue",
    "brand", "color", "material", "native_product_type", "organization_group",
})


class BrowsingAtlas:
    """Mixin using an independently rebuilt, version-bound direct-link index."""

    def _browse_scope(self, parent):
        entry = self.domain(parent)
        uids = entry["root_uids"] if entry else [parent]
        nodes = [self._basic(u) for u in uids]
        admitted = [n for n in nodes if self._node_admitted(n)]
        if not admitted:
            return None, "NOT_FOUND" if not any(nodes) else "NOT_ADMITTED"
        if self.view=='wordnet' and self.root_uid!=self.metadata['root_uid']:
            root_component=self._basic(self.root_uid)['component_id']
            admitted=[n for n in admitted if n['component_id']==root_component or
                      self.path_result(n['uid'],anchors=[self.root_uid])['status'] in ('ROOT','CONNECTED')]
            if not admitted:return None,'OUT_OF_ROOT'
        if "browse_links" not in self._tables or not self.metadata.get("browse_indexes_ready"):
            return None, "INDEX_REQUIRED"
        if self.metadata.get("browse_index_revision") != self._revision:
            return None, "STALE_INDEX"
        return {
            "parent": parent,
            "components": sorted({n["component_id"] for n in admitted}),
            "domain": entry["domain"] if entry else None,
        }, "OK"

    def _browse_context(self, method, scope, kind, relation, filters, extra=None):
        return self._page_context(method, [scope, kind, relation, [list(x) for x in sorted(filters.items())], extra])

    @staticmethod
    def _browse_filters(filters):
        filters = dict(filters or {})
        for key, value in filters.items():
            if key not in FACETS or not isinstance(value, str) or not value:
                raise ValueError("Unknown or empty catalogue facet: " + str(key))
        return filters

    @staticmethod
    def _browse_cursor(context, after):
        return base64.urlsafe_b64encode(json.dumps({
            "context": context, "after": str(after),
        }, sort_keys=True).encode()).decode().rstrip("=")

    def _browse_empty(self, status, **extra):
        return {
            "status": status, "items": [], "has_more": False,
            "next_cursor": None, "relation_view": self.relation_view,
            "database_revision": self._revision, **extra,
        }

    def _browse_where(self, scope, kind, relation, filters, alias="b", include_coarse=False):
        marks = ",".join("?" for _ in scope["components"])
        sql = f"{alias}.view=? AND {alias}.parent_component IN ({marks})"
        args = [self.relation_view, *scope["components"]]
        if scope.get("domain"):
            entry = self.domain(scope["domain"])
            sql += f" AND EXISTS(SELECT 1 FROM domain_components dc WHERE dc.domain_id=? AND dc.view=? AND dc.component_id={alias}.child_component)"
            args += [entry["domain_id"], self.relation_view]
        if not include_coarse and 'browse_preferences' in self._tables:
            sql += f""" AND NOT EXISTS(SELECT 1 FROM browse_preferences bp WHERE bp.view={alias}.view
                AND bp.parent_component={alias}.parent_component AND bp.child_component={alias}.child_component
                AND bp.role={alias}.role AND bp.relation={alias}.relation)"""
        if kind == "PRODUCT_DESIGN":
            sql += f" AND {alias}.role IN ('MODEL','MODEL_FAMILY')"
        elif kind:
            sql += f" AND {alias}.role=?"
            args.append(ROLE_ALIASES.get(kind, kind))
        if relation:
            sql += f" AND {alias}.relation=?"
            args.append(relation)
        for facet, value in sorted(filters.items()):
            sql += f""" AND EXISTS(SELECT 1 FROM browse_facets f
                JOIN browse_nodes bn ON bn.uid=f.uid WHERE f.component_id={alias}.child_component
                AND f.facet=? AND f.value=? AND (bn.view_mask & ?)<>0)"""
            args += [facet, value, VIEW_BITS[self.relation_view]]
        return sql, args

    def _browse_node(self, component, role, domain=None):
        scope, args = self._domain_filter(domain) if domain else ("", [])
        bit = VIEW_BITS[self.relation_view]
        row = self.con.execute(f"""SELECT n.* FROM browse_nodes bn
            CROSS JOIN nodes n WHERE bn.component_id=? AND bn.role=?
            AND (bn.view_mask & ?)<>0 AND n.uid=bn.uid {scope}
            ORDER BY bn.uid LIMIT 1""", [component, role, bit, *args]).fetchone()
        return self._node(row)

    def browse_children_page(self, parent, limit=20, *, node_kind="CLASS",
                             relation=None, filters=None, cursor=None, domain=None, include_coarse=False):
        """Direct children only, identity groups deduplicated, keyset paginated.

        The default selects ordinary types. Select MODEL, SERIES, CONFIGURATION,
        INSTANCE, or None explicitly to inspect other real link roles.
        """
        self._limit(limit)
        if limit > 1000:
            raise ValueError("Browse page limit must be at most 1000")
        filters = self._browse_filters(filters)
        scope, status = self._browse_scope(parent)
        if not scope:
            return self._browse_empty(status, requested_parent=parent)
        selected_domain = domain or scope["domain"]
        if selected_domain and not self.domain(selected_domain):
            return self._browse_empty("UNKNOWN_DOMAIN", requested_domain=selected_domain)
        if selected_domain:
            scope = {**scope, "domain": self.domain(selected_domain)["domain"]}
        context = self._browse_context("browse_children", scope, node_kind, relation, filters, include_coarse)
        after = self._after(cursor, context)
        try:
            after_component = int(after) if after else -1
        except ValueError as error:
            raise ValueError("Invalid browse component cursor") from error
        where, args = self._browse_where(scope, node_kind, relation, filters, include_coarse=include_coarse)
        rows = self.con.execute(f"""SELECT b.child_component,min(b.role),group_concat(DISTINCT b.role)
            FROM browse_links b WHERE {where} AND b.child_component>?
            GROUP BY b.child_component ORDER BY b.child_component LIMIT ?""",
            [*args, after_component, limit + 1]).fetchall()
        items = []
        for row in rows[:limit]:
            item = self._browse_node(row[0], row[1], scope["domain"])
            if item is None:
                raise ValueError("Browse index disagrees with admitted domain membership")
            links = self.con.execute(f"""SELECT b.* FROM browse_links b WHERE {where}
                AND b.child_component=? ORDER BY b.parent_component,b.relation,b.role""",
                [*args, row[0]]).fetchall()
            evidence = []
            for link in links:
                table = "edges" if link["storage"] == "edge" else "entity_relations"
                proof = self.con.execute(f"SELECT * FROM {table} WHERE id=?", (link["record_id"],)).fetchone()
                edge = self._edge(proof)
                if table == "entity_relations":
                    edge.update(child_uid=proof["subject_uid"], parent_uid=proof["object_uid"], terminal_connection=True)
                evidence.append({"relation": link["relation"], "source": proof["source"],
                                 "source_child_uid": edge["child_uid"], "source_parent_uid": edge["parent_uid"],
                                 "edge": edge, "source_arc_count": link["source_arc_count"]})
            item["browse_connections"] = evidence
            item["identity_component"] = row[0]
            item["browse_roles"] = sorted(row[2].split(','))
            identity_roles=[r[0] for r in self.con.execute(
                'SELECT DISTINCT role FROM browse_nodes WHERE component_id=? ORDER BY role',(row[0],))]
            item["identity_roles"] = identity_roles
            item["identity_role_conflict"] = len(identity_roles) > 1
            item["source_members_available"] = True
            items.append(item)
        more = len(rows) > limit
        return {
            "status": "OK" if items else "EMPTY", "items": items,
            "has_more": more,
            "next_cursor": self._browse_cursor(context, rows[limit-1][0]) if more else None,
            "relation_view": self.relation_view, "database_revision": self._revision,
            "scope": scope, "node_kind": node_kind, "filters": filters,
            "direct_only": True, "identity_deduplicated": True,
            "grouping_is_classification": False,
            "coarse_source_connections_retained": True, "include_coarse": include_coarse,
            "preferred_routes_have_source_witnesses": True,
        }

    def browse_summary(self, parent, *, include_coarse=True):
        scope, status = self._browse_scope(parent)
        if not scope:
            return {"status": status, "requested_parent": parent, "relations": []}
        marks = ",".join("?" for _ in scope["components"])
        rows = self.con.execute(f"""SELECT role,relation,sum(concept_count) concepts,
            sum(source_arc_count) source_arcs FROM browse_link_counts
            WHERE view=? AND parent_component IN ({marks})
            GROUP BY role,relation ORDER BY role,relation""", [self.relation_view, *scope["components"]])
        hidden={(r[0],r[1]):r[2] for r in self.con.execute(f'''SELECT role,relation,count(*)
            FROM browse_preferences WHERE view=? AND parent_component IN ({marks})
            GROUP BY role,relation''',[self.relation_view,*scope['components']])}
        items=[]
        for row in rows:
            item=dict(row);item['full_direct_concepts']=item['concepts']
            item['default_presented_concepts']=item['concepts']-hidden.get((item['role'],item['relation']),0)
            if not include_coarse:item['concepts']=item['default_presented_concepts']
            items.append(item)
        return {"status": "OK", "scope": scope, "relation_view": self.relation_view,
                "relations": items, "default_node_kind": "CLASS",
                "source_arcs_describe_preserved_full_graph":True,
                "include_coarse":include_coarse,
                "counts_overlap_across_relations_or_roots": True,
                "directory_groups_are_graph_nodes": False}

    def browse_groups(self, parent, group_by="manufacturer", limit=20, *,
                      node_kind="MODEL", relation=None, cursor=None, include_coarse=False):
        """Page exact native catalogue values, explicitly separate from IS_A."""
        self._limit(limit)
        if limit > 1000 or group_by not in FACETS:
            raise ValueError("Unknown facet or browse page limit exceeds 1000")
        scope, status = self._browse_scope(parent)
        if not scope:
            return self._browse_empty(status, requested_parent=parent)
        context = self._browse_context("browse_groups", scope, node_kind, relation, {}, [group_by,include_coarse])
        after = self._after(cursor, context)
        where, args = self._browse_where(scope, node_kind, relation, {}, include_coarse=include_coarse)
        bit = VIEW_BITS[self.relation_view]
        role=ROLE_ALIASES.get(node_kind,node_kind)
        cached=(not scope.get('domain') and len(scope['components'])==1 and role and role!='PRODUCT_DESIGN' and relation is None
                and 'browse_group_cache' in self._tables and self.con.execute(
                    'SELECT 1 FROM browse_cached_parents WHERE view=? AND parent_component=?',
                    (self.relation_view,scope['components'][0])).fetchone())
        if cached:
            rows=self.con.execute('''SELECT value,concepts FROM browse_group_cache
                WHERE view=? AND parent_component=? AND mode=? AND role=? AND facet=? AND value>?
                ORDER BY value LIMIT ?''',(self.relation_view,scope['components'][0],
                'full' if include_coarse else 'preferred',role,group_by,after,limit+1)).fetchall()
        else:
            rows = self.con.execute(f"""SELECT f.value,count(DISTINCT b.child_component) concepts
            FROM browse_links b JOIN browse_facets f ON f.component_id=b.child_component
            JOIN browse_nodes bn ON bn.uid=f.uid
            WHERE {where} AND f.facet=? AND f.value>? AND (bn.view_mask & ?)<>0
            GROUP BY f.value ORDER BY f.value LIMIT ?""", [*args, group_by, after, bit, limit+1]).fetchall()
        more = len(rows)>limit
        return {"status": "OK" if rows else "NO_NATIVE_VALUES",
                "items": [{"value": r[0], "concepts": r[1], "filters": {group_by: r[0]},
                           "node_kind": node_kind, "relation": relation,
                           "group_kind": "SOURCE_CATALOGUE_FACET", "is_a": False} for r in rows[:limit]],
                "has_more": more,
                "next_cursor": self._browse_cursor(context, rows[limit-1][0]) if more else None,
                "relation_view": self.relation_view, "database_revision": self._revision,
                "group_by": group_by, "source_values_only": True,
                "count_index_used":bool(cached),
                "missing_values_remain_browsable_without_filter": True}

    def source_members_page(self, uid, limit=20, *, cursor=None):
        self._limit(limit)
        if limit>1000:
            raise ValueError("Page limit must be at most 1000")
        own=self._basic(uid)
        if not own:
            return self._browse_empty("NOT_FOUND", requested_uid=uid)
        context=self._page_context("source_members", [own["component_id"]])
        after=self._after(cursor, context)
        rows=self.con.execute("SELECT * FROM nodes WHERE component_id=? AND uid>? ORDER BY uid LIMIT ?",
                              (own["component_id"],after,limit+1))
        result=self._page(rows,limit,context)
        result.update(status="OK", verified_identity_group=True, includes_retained_source_only=True)
        return result

    def browse_location(self, uid, domain=None):
        own=self._basic(uid)
        if not own:
            return {"status":"NOT_FOUND","uid":uid}
        if domain:
            entry=self.domain(domain)
            if not entry:
                return {"status":"UNKNOWN_DOMAIN","uid":uid,"domain":domain}
            present=self.con.execute("SELECT 1 FROM domain_components WHERE domain_id=? AND view=? AND component_id=?",
                                     (entry["domain_id"],self.relation_view,own["component_id"])).fetchone()
            if not present:
                return {"status":"OUT_OF_DOMAIN","uid":uid,"domain":entry["domain"]}
        scope,status=self._browse_scope(uid)
        if not scope:
            return {"status":status,"uid":uid}
        parents=self.con.execute("SELECT DISTINCT parent_component,relation,role FROM browse_links WHERE view=? AND child_component=? ORDER BY parent_component,relation LIMIT 101",
                                 (self.relation_view,own["component_id"])).fetchall()
        values=[]
        for row in parents[:100]:
            p=self.con.execute("SELECT uid FROM browse_nodes WHERE component_id=? AND (view_mask & ?)<>0 ORDER BY uid LIMIT 1",
                               (row[0],VIEW_BITS[self.relation_view])).fetchone()
            if p:values.append({"uid":p[0],"relation":row[1],"child_role":row[2]})
        facets=[dict(r) for r in self.con.execute("SELECT uid,facet,value,source_field FROM browse_facets WHERE component_id=? ORDER BY facet,value,uid LIMIT 101",(own["component_id"],))]
        path=self.path_result(uid)
        return {"status":"OK","uid":uid,"domain":entry["domain"] if domain else None,
                "parents":values,"parents_truncated":len(parents)>100,
                "facets":facets[:100],"facets_truncated":len(facets)>100,
                "path":path,"connection_status":self.connection_status(uid),
                "relation_view":self.relation_view,"directory_facets_are_is_a":False}

    def locate(self, text, domain, limit=20):
        self._limit(limit)
        if limit>1000:
            raise ValueError('Location page limit must be at most 1000')
        if not self.domain(domain):
            return self._browse_empty("UNKNOWN_DOMAIN",requested_domain=domain)
        page=self.search_page(text,limit=limit,domain=domain)
        locations=[self.browse_location(n["uid"],domain) for n in page["items"]]
        return {"status":"MATCHES" if locations else "NO_MATCH", "query":text,
                "items":locations,"has_more":page["has_more"],
                "search_next_cursor":page["next_cursor"],"relation_view":self.relation_view,
                "identity_not_inferred_from_names":True}

    def browse_path_result(self, uid, anchors=None, max_depth=256):
        """Show surviving finer source routes, separately from shortest distance."""
        shortest=self.path_result(uid,anchors,max_depth)
        if shortest['status'] not in ('ROOT','CONNECTED'):
            return {**shortest,'selection':'witnessed_finer_route','path_is_shortest':True}
        scope,status=self._browse_scope(uid)
        if not scope:
            return {**shortest,'selection':'shortest_fallback','browse_index_status':status}
        def expand(child,parent,edge,stack=()):
            if edge['relation']=='SAME_CONCEPT':return [self._step_for(child,parent,edge)]
            a,b=self._basic(child),self._basic(parent)
            key=(self.relation_view,b['component_id'],a['component_id'],a['node_kind'],edge['relation'])
            if key in stack:
                raise ValueError('Finer-route preference dependency cycle')
            if len(stack)>max_depth:
                raise ValueError('Finer-route expansion exceeds max_depth')
            pref=self.con.execute('SELECT * FROM browse_preferences WHERE view=? AND parent_component=? AND child_component=? AND role=? AND relation=?',key).fetchone()
            if not pref:return [self._step_for(child,parent,edge)]
            result=[];current=child
            for storage,rid in [(pref['first_storage'],pref['first_record_id']),
                                (pref['second_storage'],pref['second_record_id'])]:
                table='edges' if storage=='edge' else 'entity_relations'
                raw=self.con.execute(f'SELECT * FROM {table} WHERE id=?',(rid,)).fetchone()
                proof=self._edge(raw)
                if storage=='entity':proof.update(child_uid=raw['subject_uid'],parent_uid=raw['object_uid'],terminal_connection=True)
                c,p=proof['child_uid'],proof['parent_uid']
                if current!=c:result.extend(self._identity_steps(current,c))
                result.extend(expand(c,p,proof,stack+(key,)));current=p
            if current!=parent:result.extend(self._identity_steps(current,parent))
            return result
        upward=[]
        for step in reversed(shortest['path']):
            upward.extend(expand(step['uid'],step['parent_uid'],step['edge']))
        nonidentity=sum(x['edge']['relation']!='SAME_CONCEPT' for x in upward)
        if nonidentity>max_depth:
            return {**shortest,'status':'DEPTH_LIMIT','path':[],
                    'shortest_status':shortest['status'],'selection':'witnessed_finer_route'}
        return {**shortest,'path':list(reversed(upward)),'distance':nonidentity,
                'shortest_distance':shortest.get('distance'),
                'path_is_shortest':nonidentity==shortest.get('distance'),
                'selection':'witnessed_finer_route','source_graph_unchanged':True}
