"""Public paging of evidenced source organization groups, outside taxonomy."""
from __future__ import annotations

import json
from pathlib import Path


def source_group_kind(group):
    proof = json.loads(group['proof'])
    return ('SOURCE_NATIVE_CATALOG_DIRECTORY' if proof.get('kind') == 'SOURCE_NATIVE_CATALOG_DIRECTORY'
            else 'SOURCE_ORGANIZATION_GROUP')


class SourceGroupAtlas:
    def source_directories(self, domain, limit=20):
        """Related publisher directories explicitly associated with an entry.

        Directory navigation does not assert that a source product is a type
        descendant, or change its identity/path/learning admission.
        """
        self._limit(limit)
        if limit > 1000:
            raise ValueError('Source directory page limit must be at most 1000')
        entry = self.domain(domain)
        if not entry or 'source_groups' not in self._tables:
            return []
        rows = self.con.execute('''SELECT g.* FROM source_groups g
            WHERE json_extract(g.proof,'$.kind')='SOURCE_NATIVE_CATALOG_DIRECTORY'
            AND EXISTS(SELECT 1 FROM json_each(g.proof,'$.navigation_domains') d WHERE d.value=?)
            ORDER BY g.group_uid LIMIT ?''',(entry['domain'],limit)).fetchall()
        return [{**dict(row), 'group_kind':source_group_kind(row), 'is_a':False,
                 'classification_distance_applicable':False,
                 'scope_semantics':'Related publisher directory; source record membership'} for row in rows]

    def source_groups_page(self, namespace=None, limit=20, *, source_version=None, cursor=None):
        self._limit(limit)
        if limit > 1000:
            raise ValueError("Source group page limit must be at most 1000")
        if "source_groups" not in self._tables:
            return {"status": "SOURCE_GROUPS_NOT_AVAILABLE", "items": [], "has_more": False,
                    "next_cursor": None, "is_a": False}
        context = self._page_context("source_groups", [namespace, source_version])
        after = self._after(cursor, context)
        where, values = ["g.group_uid>?"], [after]
        if namespace is not None:
            where.append("g.namespace=?")
            values.append(namespace)
        if source_version is not None:
            where.append("g.source_version=?")
            values.append(source_version)
        rows = self.con.execute(
            "SELECT g.* FROM source_groups g WHERE " + " AND ".join(where) +
            " ORDER BY g.group_uid LIMIT ?", [*values, limit + 1]).fetchall()
        items = []
        for row in rows[:limit]:
            admitted = "('ACTIVE','SOURCE_DECLARED')" if source_group_kind(row) == 'SOURCE_NATIVE_CATALOG_DIRECTORY' else "('ACTIVE')"
            counts = self.con.execute(
                "SELECT count(*),count(DISTINCT n.component_id) FROM source_group_members s "
                "JOIN nodes n ON n.uid=s.member_uid WHERE s.group_uid=? AND s.status IN "+admitted,
                (row["group_uid"],)).fetchone()
            items.append({**dict(row), "source_member_uids": counts[0], "identity_groups": counts[1],
                          "group_kind": source_group_kind(row), "is_a": False,
                          "classification_distance_applicable": False})
        more = len(rows) > limit
        return {"status": "OK", "items": items, "has_more": more,
                "next_cursor": self._browse_cursor(context, rows[limit - 1]["group_uid"]) if more else None,
                "is_a": False, "database_revision": self._revision}

    def source_group_members_page(self, group_uid, limit=20, *, domain=None, cursor=None):
        self._limit(limit)
        if limit > 1000:
            raise ValueError("Source group page limit must be at most 1000")
        if "source_groups" not in self._tables:
            return {"status": "SOURCE_GROUPS_NOT_AVAILABLE", "items": [], "has_more": False, "next_cursor": None}
        group = self.con.execute("SELECT * FROM source_groups WHERE group_uid=?", (group_uid,)).fetchone()
        if group is None:
            return {"status": "UNKNOWN_SOURCE_GROUP", "items": [], "has_more": False, "next_cursor": None}
        entry = self.domain(domain) if domain else None
        if domain and not entry:
            return {"status": "UNKNOWN_DOMAIN", "items": [], "has_more": False, "next_cursor": None}
        context = self._page_context("source_group_members", [group_uid, domain])
        after = self._after(cursor, context)
        admitted = "('ACTIVE','SOURCE_DECLARED')" if source_group_kind(group) == 'SOURCE_NATIVE_CATALOG_DIRECTORY' else "('ACTIVE')"
        sql = "SELECT s.* FROM source_group_members s JOIN nodes n ON n.uid=s.member_uid WHERE s.group_uid=? AND s.status IN "+admitted+" AND s.member_uid>?"
        args = [group_uid, after]
        if entry:
            sql += " AND EXISTS(SELECT 1 FROM domain_members d WHERE d.uid=s.member_uid AND d.domain_id=? AND d.view=?)"
            args.extend([entry["domain_id"], self.relation_view])
        rows = self.con.execute(sql + " ORDER BY s.member_uid LIMIT ?", [*args, limit + 1]).fetchall()
        items = [{**self.node(row["member_uid"]), "group_membership": dict(row),
                  "group_kind": source_group_kind(group), "is_a": False} for row in rows[:limit]]
        more = len(rows) > limit
        return {"status": "OK", "items": items, "group": dict(group), "has_more": more,
                "next_cursor": self._browse_cursor(context, rows[limit - 1]["member_uid"]) if more else None,
                "source_uids_are_not_collapsed": True, "database_revision": self._revision,
                "classification_distance_applicable": False}

    def export_source_groups(self, path, *, namespace=None, source_version=None):
        """Export every source group and explicit membership without graph edges."""
        count = 0
        cursor = None
        with Path(path).open("w", encoding="utf-8") as output:
            while True:
                page = self.source_groups_page(namespace, 1000, source_version=source_version, cursor=cursor)
                if page["status"] != "OK":
                    raise ValueError(page["status"])
                for group in page["items"]:
                    membership_cursor = None
                    while True:
                        members = self.source_group_members_page(group["group_uid"], 1000, cursor=membership_cursor)
                        for member in members["items"]:
                            output.write(json.dumps({"group": group, "member": member,
                                                     "is_a": False}, ensure_ascii=False) + "\n")
                            count += 1
                        if not members["has_more"]:
                            break
                        membership_cursor = members["next_cursor"]
                if not page["has_more"]:
                    break
                cursor = page["next_cursor"]
        return {"source_memberships": count, "namespace": namespace,
                "database_revision": self._revision, "is_a": False}
