"""Versioned, evidence-preserving incremental subgraphs, independent of main builds.

An overlay contains a frozen upward identity closure and explicitly admitted
source deltas. It never writes the referenced source database. Public graph
queries operate on normalized roles/relations rather than dataset names.
"""
from __future__ import annotations
from collections import defaultdict, deque
import base64
import hashlib
import json
from pathlib import Path
import sqlite3
import unicodedata
from typing import Any
from .hierarchy import LINK_ROLES, validate_link_roles

SCHEMA = 'FINEATLAS_FG_INCREMENTAL_V1'
KINDS = ('datasets', 'sources', 'nodes', 'relations', 'mappings', 'evidence')
UPWARD = {
    'strict': {'IS_A'},
    'taxonomy': {'IS_A', 'TAXONOMIC_PARENT', 'NATIVE_CLASSIFICATION_PARENT'},
    'membership': {'REUSABLE_TYPE_MEMBERSHIP'},
    'unified': {'IS_A', 'TAXONOMIC_PARENT', 'NATIVE_CLASSIFICATION_PARENT',
                'DESIGN_TYPE_OF', 'NATIVE_DESIGN_PARENT', 'SERIES_MEMBER_OF',
                'CONFIGURATION_OF', 'CONFIGURATION_TYPE_OF', 'DEPICTS_TYPE'},
}
ACTIVE = {'ACTIVE', 'TYPED_ACTIVE', 'BACKBONE_ACTIVE', 'VERIFIED'}
RELATION_ROLES = dict(LINK_ROLES)
RELATION_ROLES.update({
    'REUSABLE_TYPE_MEMBERSHIP': ({'CLASS','DATASET_CATEGORY'}, {'CLASS','DATASET_CATEGORY'}),
    'ATTRIBUTE_KIND_OF': ({'ATTRIBUTE'}, {'CLASS'}),
    'MANUFACTURED_BY': ({'CLASS','MODEL','MODEL_FAMILY','CONFIGURATION'}, {'ORGANIZATION'}),
    'GROUPED_IN_SOURCE': ({'DATASET_CATEGORY'}, {'SOURCE_GROUP'}),
    'ORGANIZATION_GROUP_MEMBER': ({'CLASS','MODEL','MODEL_FAMILY'}, {'ORGANIZATION'}),
})
DOMAIN_FAMILIES={'animal':'animals','animals':'animals','birds':'animals','dog_breeds':'animals','cat_breeds':'animals','plant':'plants','plants':'plants','fungi':'fungi','food':'foods','food_dishes':'foods','foods':'foods','cars':'vehicles','aircraft':'vehicles','vehicle':'vehicles','vehicles':'vehicles'}

def domain_relation_error(relation: str, child: dict, parent: dict) -> bool:
    if relation not in {'IS_A','TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT'}:return False
    a=DOMAIN_FAMILIES.get(child.get('domain'));b=DOMAIN_FAMILIES.get(parent.get('domain'))
    return bool(a and b and a!=b)

ALL_UPWARD = set().union(*UPWARD.values())
TASK_ROLES = {'classification':{'CLASS','BIOLOGICAL_VARIANT'}, 'design':{'MODEL','MODEL_FAMILY'},
              'configuration':{'CONFIGURATION'}}

def validate_relation_roles(relation: str, child_role: str, parent_role: str) -> None:
    allowed=RELATION_ROLES.get(relation)
    if not allowed or child_role not in allowed[0] or parent_role not in allowed[1]:
        raise ValueError(f'Unsupported relation or endpoint roles: {relation} {child_role} -> {parent_role}')


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def normalize_name(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', value).replace('_', ' ').casefold().split())


def object_key(kind: str, row: dict[str, Any]) -> str:
    if kind == 'datasets': return row['dataset']+'@'+row['version']
    if kind == 'mappings': return row['dataset']+'@'+row['version']+':'+str(row['class_id'])+':'+row.get('scope', 'world')
    if kind == 'relations': return row.get('id') or digest({k:row.get(k) for k in ('child_uid','parent_uid','relation','source','source_version','evidence_id')})
    return row.get('uid') or row.get('evidence_id') or row['id']


def open_store(path: str | Path, *, create: bool = False,
               read_only: bool = False) -> sqlite3.Connection:
    path = Path(path).resolve()
    if create and read_only:
        raise ValueError('Cannot create a read-only store')
    if create:
        if path.exists(): raise ValueError('Refuse to overwrite an existing store')
        path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(path)
        c.executescript('''CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE fg_objects(kind TEXT,key TEXT,payload TEXT,sha256 TEXT,PRIMARY KEY(kind,key));
        CREATE TABLE fg_packages(id TEXT PRIMARY KEY,sha256 TEXT,status TEXT,manifest TEXT,sequence INTEGER UNIQUE);
        CREATE TABLE fg_events(sequence INTEGER PRIMARY KEY,package_id TEXT,action TEXT,payload TEXT);
        CREATE TABLE fg_changes(package_id TEXT,kind TEXT,key TEXT,prior TEXT,current_sha256 TEXT,PRIMARY KEY(package_id,kind,key));''')
        c.execute('INSERT INTO metadata VALUES (?,?)',('schema',canonical(SCHEMA)));c.commit()
    else:
        if not path.is_file():
            raise ValueError('An existing independent store is required')
        c = sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) if read_only else sqlite3.connect(path)
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='fg_objects'").fetchone():
            c.close(); raise ValueError('Writes are allowed only to an independent FG overlay')
        if c.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0] != canonical(SCHEMA):
            c.close(); raise ValueError('Unsupported overlay schema')
    c.row_factory=sqlite3.Row
    return c


def read_objects(c: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    out={k:[] for k in KINDS}
    for r in c.execute('SELECT * FROM fg_objects ORDER BY kind,key'):
        out[r['kind']].append(json.loads(r['payload']))
    return out


def validate_objects(objects: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Validate the effective graph, including baseline identity dependencies."""
    nodes={r['uid']:r for r in objects['nodes']}; evidence={r['evidence_id']:r for r in objects['evidence']}
    errors=[]; inherited=[]
    group={u:r.get('identity_group',u) for u,r in nodes.items()}
    for uid,node in nodes.items():
        if group[uid]!=uid:
            raw=node.get('raw_record',{})
            if node.get('node_origin')!='FROZEN_BASELINE' or not isinstance(raw,dict) or raw.get('uid')!=uid or group[uid]!='baseline-component:'+str(raw.get('component_id')) or node.get('baseline_record_sha256')!=digest(raw):
                errors.append(['unproved_identity_group',uid,group[uid]])
    for e in objects['evidence']:
        raw=e.get('raw_record',{})
        if not e.get('content_sha256') or e['content_sha256']!=digest(raw):
            errors.append(['evidence_content_hash',e['evidence_id']])
        if isinstance(raw,dict) and 'payload' in raw and raw.get('payload_sha256'):
            if hashlib.sha256((raw['payload'] if isinstance(raw['payload'],str) else canonical(raw['payload'])).encode()).hexdigest()!=raw['payload_sha256']:
                errors.append(['frozen_evidence_payload_hash',e['evidence_id']])
    for source in objects['sources']:
        if source.get('path') and source.get('sha256'):
            file=Path(source['path'])
            if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=source['sha256']:
                errors.append(['frozen_source_file_hash',source.get('id')])
    graph=defaultdict(set)
    for e in objects['relations']:
        if e['child_uid'] not in nodes or e['parent_uid'] not in nodes:
            errors.append(['dangling_relation',object_key('relations',e)]);continue
        if e.get('status') not in ACTIVE:continue
        if e.get('evidence_id') not in evidence:
            errors.append(['missing_evidence',object_key('relations',e)]);continue
        ev=evidence[e['evidence_id']]
        if e.get('inherited'):
            original=e.get('raw_record',{})
            original_child=original.get('child_uid',original.get('subject_uid'))
            original_parent=original.get('parent_uid',original.get('object_uid'))
            if original_child!=e['child_uid'] or original_parent!=e['parent_uid'] or original.get('relation')!=e['relation'] or ev.get('raw_record')!=original or ev.get('claim_scope')!='FROZEN_BASELINE_ASSERTION_NOT_NEW_SEMANTIC_PROOF' or original.get('status') not in ACTIVE or original.get('source')!=e.get('source') or e.get('id') not in ('baseline:edges:'+str(original.get('id')), 'baseline:entity_relations:'+str(original.get('id'))):
                errors.append(['invalid_inherited_assertion_guard',object_key('relations',e)])
        else:
            claim={k:e.get(k) for k in ('child_uid','parent_uid','relation','source','source_version')}
            if claim not in ev.get('admitted_claims',[]):errors.append(['unbound_structural_evidence',object_key('relations',e)])
            if ev.get('source_version')!=e.get('source_version'):errors.append(['source_version_mismatch',object_key('relations',e)])
        if not e.get('source_version') or not e.get('facet'):
            errors.append(['missing_source_version_or_facet',object_key('relations',e)])
        try:validate_relation_roles(e['relation'],nodes[e['child_uid']]['role'],nodes[e['parent_uid']]['role'])
        except ValueError as exc:
            errors.append(['role_contract',str(exc),object_key('relations',e)]);continue
        if domain_relation_error(e['relation'],nodes[e['child_uid']],nodes[e['parent_uid']]):
            errors.append(['cross_domain_type_inclusion',object_key('relations',e)])
        if e['relation'] in ALL_UPWARD:
            a,b=group[e['child_uid']],group[e['parent_uid']]
            if a==b:errors.append(['structural_identity_loop',object_key('relations',e)])
            graph[a].add(b)
    # Iterative topological reduction avoids Python recursion depth limits.
    indegree={g:0 for g in group.values()}
    for a,parents in graph.items():
        for b in parents:indegree[b]+=1
    q=deque(g for g,v in indegree.items() if not v);visited=0
    while q:
        a=q.popleft();visited+=1
        for b in graph[a]:
            indegree[b]-=1
            if not indegree[b]:q.append(b)
    cycles=sorted(g for g,v in indegree.items() if v)
    if cycles:errors.append(['cycle_or_cycle_dependents',cycles[:50]])
    counts=defaultdict(int)
    for m in objects['mappings']:
        counts[(m['dataset'],m['version'])]+=1
        if m.get('target_uid') and m['target_uid'] not in nodes:errors.append(['dangling_mapping',object_key('mappings',m)])
        if not m.get('raw_name') or not m.get('source_uid'):errors.append(['missing_native_label_or_uid',object_key('mappings',m)])
        if m.get('mapping_type')=='EXACT' and m.get('identity_status') not in ('VERIFIED','SOURCE_CONFIRMED'):
            errors.append(['unverified_exact_mapping',object_key('mappings',m)])
    for d in objects['datasets']:
        scope=d.get('count_scope','world')
        actual=sum(1 for m in objects['mappings'] if m['dataset']==d['dataset'] and m['version']==d['version'] and m.get('scope','world')==scope)
        if d.get('labels_available') and actual!=d['observed_classes']:
            errors.append(['label_count',d['dataset'],actual,d['observed_classes']])
    return {'passed':not errors,'errors':errors,'inherited_role_review':inherited,'cycle_check_scope':'effective_overlay_graph_with_explicit_closure_attestation','full_main_graph_certified':False,'counts':{k:len(v) for k,v in objects.items()}}


def apply_package(path: str | Path, package: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(package,(str,Path)):package=json.loads(Path(package).read_text())
    if package.get('schema')!=SCHEMA:raise ValueError('Wrong package schema')
    if package.get('complete_upward_identity_closure') is False:raise ValueError('Incomplete frozen ancestor closure')
    c=open_store(path)
    try:
        with c:
            c.execute('BEGIN IMMEDIATE')
            sha=digest(package);pid=package['package_id']
            prior=c.execute('SELECT * FROM fg_packages WHERE id=?',(pid,)).fetchone()
            if prior:
                if prior['sha256']!=sha:raise ValueError('Package ID reused for changed input')
                if prior['status']=='APPLIED':return {'status':'ALREADY_APPLIED','package_id':pid,'changed':0}
                # Exact byte replay after rollback is allowed and separately logged.
                c.execute('DELETE FROM fg_changes WHERE package_id=?',(pid,))
                c.execute('DELETE FROM fg_packages WHERE id=?',(pid,))
            meta={r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM metadata')}
            if meta.get('baseline_revision') and package['baseline_revision']!=meta['baseline_revision']:
                raise ValueError('Baseline changed; run compatibility review before replay')
            for dependency in package.get('baseline_dependencies',[]):
                actual=c.execute("SELECT payload FROM fg_objects WHERE kind='nodes' AND key=?",(dependency['uid'],)).fetchone()
                if not actual or json.loads(actual[0]).get('baseline_record_sha256')!=dependency['baseline_record_sha256']:
                    raise ValueError('Frozen endpoint scope dependency changed '+dependency['uid'])
            changed=0
            for kind in KINDS:
                seen=set()
                for row in package.get(kind,[]):
                    key=object_key(kind,row)
                    if key in seen:raise ValueError('Duplicate object key in package '+kind+':'+key)
                    seen.add(key)
                    old=c.execute('SELECT payload,sha256 FROM fg_objects WHERE kind=? AND key=?',(kind,key)).fetchone()
                    payload=canonical(row);new_sha=digest(row)
                    if old and old['sha256']==new_sha:continue
                    if old:
                        migration=package.get('migrations',{}).get(kind+':'+key)
                        if not migration or migration.get('prior_sha256')!=old['sha256'] or not migration.get('reason'):
                            raise ValueError('Object changed without explicit migration '+kind+':'+key)
                    c.execute('INSERT INTO fg_changes VALUES (?,?,?,?,?)',(pid,kind,key,old['payload'] if old else None,new_sha))
                    c.execute('INSERT OR REPLACE INTO fg_objects VALUES (?,?,?,?)',(kind,key,payload,new_sha));changed+=1
            report=validate_objects(read_objects(c))
            if not report['passed']:raise ValueError('Increment rejected: '+canonical(report['errors'][:12]))
            seq=c.execute('SELECT coalesce(max(sequence),0)+1 FROM fg_events').fetchone()[0]
            c.execute('INSERT INTO fg_events VALUES (?,?,?,?)',(seq,pid,'APPLIED',canonical({'package_sha256':sha,'changed':changed})))
            c.execute('INSERT INTO fg_packages VALUES (?,?,?,?,?)',(pid,sha,'APPLIED',canonical({k:v for k,v in package.items() if k not in KINDS}),seq))
            if 'domain_aliases' in package:
                c.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('domain_aliases',canonical(package['domain_aliases'])))
            if 'complete_upward_identity_closure' in package:
                c.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('complete_upward_identity_closure',canonical(package['complete_upward_identity_closure'])))
            c.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('baseline_revision',canonical(package['baseline_revision'])))
            c.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('revision',canonical(digest(read_objects(c)))))
            return {'status':'APPLIED','package_id':pid,'changed':changed,'validation':report}
    finally:c.close()


def rollback_package(path: str | Path, pid: str) -> dict[str, Any]:
    c=open_store(path)
    try:
        with c:
            c.execute('BEGIN IMMEDIATE')
            p=c.execute('SELECT * FROM fg_packages WHERE id=?',(pid,)).fetchone()
            if not p:raise ValueError('Unknown package')
            if p['status']=='ROLLED_BACK':return {'status':'ALREADY_ROLLED_BACK','changed':0}
            latest=c.execute("SELECT id FROM fg_packages WHERE status='APPLIED' ORDER BY sequence DESC LIMIT 1").fetchone()[0]
            if latest!=pid:raise ValueError('Rollback dependent packages in reverse apply order')
            rows=list(c.execute('SELECT * FROM fg_changes WHERE package_id=?',(pid,)))
            for r in rows:
                current=c.execute('SELECT sha256 FROM fg_objects WHERE kind=? AND key=?',(r['kind'],r['key'])).fetchone()
                if not current or current[0]!=r['current_sha256']:raise ValueError('Rollback conflicts with later mutation')
                if r['prior'] is None:c.execute('DELETE FROM fg_objects WHERE kind=? AND key=?',(r['kind'],r['key']))
                else:c.execute('UPDATE fg_objects SET payload=?,sha256=? WHERE kind=? AND key=?',(r['prior'],digest(json.loads(r['prior'])),r['kind'],r['key']))
            c.execute("UPDATE fg_packages SET status='ROLLED_BACK' WHERE id=?",(pid,))
            seq=c.execute('SELECT coalesce(max(sequence),0)+1 FROM fg_events').fetchone()[0]
            c.execute('INSERT INTO fg_events VALUES (?,?,?,?)',(seq,pid,'ROLLED_BACK',canonical({'changes':[dict(r) for r in rows]})))
            c.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('revision',canonical(digest(read_objects(c)))))
            return {'status':'ROLLED_BACK','package_id':pid,'changed':len(rows)}
    finally:c.close()


class IncrementalAtlas:
    """Generic public queries for an independently validated incremental store."""
    def __init__(self, path: str | Path, *, relation_view: str = 'unified') -> None:
        if relation_view not in UPWARD:raise ValueError('Unknown relation view')
        self.database_path=Path(path).resolve();self.relation_view=relation_view
        self.con=sqlite3.connect(self.database_path.as_uri()+'?mode=ro&immutable=1',uri=True);self.con.row_factory=sqlite3.Row
        self.metadata={r['key']:json.loads(r['value']) for r in self.con.execute('SELECT * FROM metadata')}
        if self.metadata.get('schema')!=SCHEMA:raise ValueError('Not an FG incremental store')
        self.objects=read_objects(self.con)
        self.nodes={r['uid']:r for r in self.objects['nodes']}
        self.groups=defaultdict(list)
        for u,n in self.nodes.items():self.groups[n.get('identity_group',u)].append(u)
        self.identity_crosswalks=defaultdict(list)
        for record in self.objects['sources']:
            if record.get('claim_scope')=='FROZEN_IDENTITY_CROSSWALK_HISTORY':
                raw=record['raw_record'];left,right=raw.get('left_uid'),raw.get('right_uid')
                if left in self.nodes and right in self.nodes and self._group(left)==self._group(right):self.identity_crosswalks[self._group(left)].append(record)
        self.direct_relations=defaultdict(list)
        for relation in self.objects['relations']:
            self.direct_relations[relation['child_uid']].append(relation)
        self.parents=defaultdict(list);self.children=defaultdict(list);self.catalog_children=defaultdict(list)
        for e in self.objects['relations']:
            if e.get('status') in ACTIVE and e['relation']=='GROUPED_IN_SOURCE':
                self.catalog_children[e['parent_uid']].append(e)
            if e.get('status') not in ACTIVE or e['relation'] not in UPWARD[relation_view]:continue
            try:validate_relation_roles(e['relation'],self.nodes[e['child_uid']]['role'],self.nodes[e['parent_uid']]['role'])
            except ValueError:continue
            a=self._group(e['child_uid']);b=self._group(e['parent_uid'])
            self.parents[a].append((b,e));self.children[b].append((a,e))
        self._name_index=defaultdict(set);self._token_index=defaultdict(set)
        for uid,node in self.nodes.items():
            for alias in [node['label'],*node.get('aliases',[])]:
                name=normalize_name(alias);self._name_index[name].add(uid)
                for token in name.split():self._token_index[token].add(uid)
        self._mapping_search_witnesses=defaultdict(list);self._supervision_aliases=defaultdict(set)
        for mapping in self.objects['mappings']:
            uid=mapping.get('target_uid')
            if uid not in self.nodes:continue
            for label in {mapping.get('raw_name'),mapping.get('standard_name')}-{None}:
                name=normalize_name(label);self._name_index[name].add(uid);self._supervision_aliases[uid].add(label)
                for token in name.split():self._token_index[token].add(uid)
                self._mapping_search_witnesses[(uid,name)].append({key:mapping.get(key) for key in ('dataset','version','class_id','scope','source_uid','mapping_type','identity_status')})
        self._ancestor_cache={}
        self._coarse_groups={self._group(u) for u,n in self.nodes.items() if n.get('coarse_anchor')}
        self._targets_by_label=defaultdict(list);self._labels_by_scope=defaultdict(list)
        for mapping in self.objects['mappings']:
            self._targets_by_label[(mapping['dataset'],str(mapping['class_id']),mapping.get('scope','world'))].append(mapping)
            self._labels_by_scope[(mapping['dataset'],mapping.get('scope','world'))].append(mapping)

    def _group(self,uid):
        return self.nodes[uid].get('identity_group',uid)

    def close(self):self.con.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def node(self,uid):return self.nodes.get(uid)
    def stats(self):
        from collections import Counter
        return {k:len(v) for k,v in self.objects.items()} | {'roles':dict(Counter(n['role'] for n in self.nodes.values())), 'semantic_grains':dict(Counter(n.get('semantic_grain') or n.get('rank') or n['role'] for n in self.nodes.values()))}

    def identity(self, uid: str) -> dict[str, Any]:
        if uid not in self.nodes:raise ValueError('Unknown UID '+uid)
        members=self.groups[self._group(uid)]
        witnesses=self.identity_crosswalks[self._group(uid)]
        return {'uid':uid,'identity_group':self._group(uid),'member_uids':members,'frozen_crosswalks':witnesses,'baseline_revision':self.metadata.get('baseline_revision'),'world_identity_independently_reverified':False}

    def _identity_step(self, left: str, right: str) -> dict[str, Any]:
        if left==right:return {}
        witness=self.identity(left)
        return {'from_uid':left,'to_uid':right,'identity_group':witness['identity_group'],'baseline_revision':witness['baseline_revision'],'crosswalk_ids':[r['id'] for r in witness['frozen_crosswalks']], 'claim_scope':'FROZEN_COMPONENT_MEMBERSHIP_NOT_NEW_WORLD_IDENTITY_PROOF'}

    def _page(self,rows,limit,cursor,context):
        if limit<1:raise ValueError('Limit must be positive')
        offset=0;token=digest({'context':context,'revision':self.metadata['revision'],'view':self.relation_view})
        if cursor:
            try:decoded=json.loads(base64.urlsafe_b64decode(cursor))
            except Exception as exc:raise ValueError('Invalid cursor') from exc
            if decoded['context']!=token:raise ValueError('Cursor belongs to another query or revision')
            offset=decoded['offset']
            if not isinstance(offset,int) or offset<0:raise ValueError('Invalid cursor offset')
        page=rows[offset:offset+limit];more=offset+limit<len(rows)
        next_cursor=base64.urlsafe_b64encode(canonical({'context':token,'offset':offset+limit}).encode()).decode() if more else None
        return {'items':page,'has_more':more,'next_cursor':next_cursor,'total':len(rows)}

    def search_page(self,text,limit=20,*,cursor=None,domain=None,node_kind=None):
        query=normalize_name(text)
        candidates=set(self._name_index.get(query,set()))
        terms=query.split()
        if terms:
            token_sets=[self._token_index.get(t,set()) for t in terms]
            candidates.update(set.intersection(*token_sets))
        if not candidates:
            candidates={uid for name,uids in self._name_index.items() if query in name for uid in uids}
        rows=[{**self.nodes[uid],'matched_label_mappings':self._mapping_search_witnesses.get((uid,query),[])} for uid in candidates if (not domain or self.nodes[uid].get('domain')==domain) and (not node_kind or self.nodes[uid]['role']==node_kind)]
        rows.sort(key=lambda n:(normalize_name(n['label'])!=query,normalize_name(n['label']),n['uid']))
        return self._page(rows,limit,cursor,['search',query,domain,node_kind])

    def search(self,text,limit=20,domain=None,*,node_kind=None):return self.search_page(text,limit,domain=domain,node_kind=node_kind)['items']
    def aliases(self,uid,limit=100):return sorted(set(self.nodes[uid].get('aliases',[]))|self._supervision_aliases[uid])[:limit]
    @staticmethod
    def _field(node,field):
        value=node
        for part in field.split('.'):
            value=value.get(part) if isinstance(value,dict) else None
        return value

    def relations_page(self, uid: str, limit: int = 20, *, cursor=None, status=None, relation=None):
        rows=[r for r in self.direct_relations.get(uid,[]) if (not status or r.get('status')==status) and (not relation or r['relation']==relation)]
        return self._page(sorted(rows,key=lambda r:object_key('relations',r)),limit,cursor,['relations',uid,status,relation])

    def source_members_page(self,uid,limit=20,*,cursor=None):
        rows=[{**self.nodes[e['child_uid']],'source_membership':e,'navigation_only':True} for e in self.catalog_children[uid]]
        return self._page(sorted(rows,key=lambda n:n['uid']),limit,cursor,['source_members',uid])

    def browse_children_page(self,parent,limit=20,*,cursor=None,node_kind=None,relation=None,filters=None):
        if parent not in self.nodes:raise ValueError('Unknown parent')
        if relation=='GROUPED_IN_SOURCE':return self.source_members_page(parent,limit,cursor=cursor)
        found={}
        for g,e in self.children[self._group(parent)]:
            for uid in self.groups[g]:
                n=self.nodes[uid]
                if node_kind and n['role']!=node_kind or relation and e['relation']!=relation:continue
                if filters and any(self._field(n,k)!=v for k,v in filters.items()):continue
                found[uid]=n
        return self._page(sorted(found.values(),key=lambda n:(normalize_name(n['label']),n['uid'])),limit,cursor,['browse',parent,node_kind,relation,filters])

    def browse_groups(self,parent,group_by='rank',limit=20,*,cursor=None):
        rows=self.browse_children_page(parent,limit=max(1,len(self.nodes)))['items']
        buckets=defaultdict(list)
        for n in rows:buckets[canonical(self._field(n,group_by))].append(n['uid'])
        result=[{'value':json.loads(value),'count':len(uids),'navigation_only':True,'field':group_by} for value,uids in sorted(buckets.items())]
        return self._page(result,limit,cursor,['facets',parent,group_by])

    def _ancestors(self,uid):
        if uid not in self.nodes:raise ValueError('Unknown UID '+uid)
        start=self._group(uid)
        if start in self._ancestor_cache:return self._ancestor_cache[start]
        dist={start:0};q=deque([start])
        while q:
            a=q.popleft()
            for b,e in self.parents[a]:
                if b not in dist:dist[b]=dist[a]+1;q.append(b)
        self._ancestor_cache[start]=dist;return dist

    def path_result(self,uid,anchors=None,max_depth=256):
        if uid not in self.nodes:return {'status':'UNKNOWN_UID','path':[],'reason':'UID missing from fixed subgraph'}
        anchors=set(anchors or [u for u,n in self.nodes.items() if n.get('wordnet_anchor')])
        target_groups={self._group(u) for u in anchors if u in self.nodes}
        start=self._group(uid);q=deque([(start,[]) ]);seen={start}
        while q:
            a,path=q.popleft()
            if a in target_groups:
                anchor=next(u for u in sorted(anchors) if u in self.nodes and self._group(u)==a)
                current=uid;annotated=[]
                for edge in path:
                    annotated.append({**edge,'source_version_scope':'FROZEN_BASELINE_RELEASE' if edge.get('inherited') else 'VERSIONED_SOURCE_ASSERTION','native_authority_version':None if edge.get('inherited') else edge.get('source_version'),'child_identity_witness':self._identity_step(current,edge['child_uid'])});current=edge['parent_uid']
                return {'status':'CONNECTED','uid':uid,'anchor_uid':anchor,'path':annotated,'anchor_identity_witness':self._identity_step(current,anchor),'relation_view':self.relation_view}
            if len(path)>=max_depth:continue
            for b,e in sorted(self.parents[a],key=lambda x:object_key('relations',x[1])):
                if b not in seen:seen.add(b);q.append((b,path+[e]))
        limited=any(v>=max_depth for v in self._ancestors(uid).values())
        return {'status':'QUERY_LIMIT' if limited else 'REVIEW','uid':uid,'path':[],'reason':'Path bound reached' if limited else 'No evidenced path in selected view'}

    def path(self,uid,anchors=None,max_depth=256):return self.path_result(uid,anchors,max_depth)['path']
    def lca(self,left,right,**kwargs):return self.relation_query(left,right,**kwargs)
    def distance(self,left,right,**kwargs):return self.relation_query(left,right,**kwargs)
    def target(self,dataset,class_id,*,version=None,target_scope='world'):
        rows=[r for r in self._targets_by_label.get((dataset,str(class_id),target_scope),[]) if not version or r['version']==version]
        if len(rows)>1:raise ValueError('Specify fixed dataset version')
        return rows[0] if rows else None
    def task_labels(self,dataset,*,version=None,target_scope='world'):
        return sorted([r for r in self._labels_by_scope.get((dataset,target_scope),[]) if not version or r['version']==version],key=lambda r:str(r['class_id']))
    def task_path(self,dataset,class_id,*,version=None,target_scope='world'):
        m=self.target(dataset,class_id,version=version,target_scope=target_scope)
        if not m:return {'status':'UNKNOWN_LABEL','path':[]}
        if not m.get('target_uid'):return {'status':'REVIEW','path':[],'reason':m.get('reason','Identity not confirmed'),'mapping':m}
        if self.relation_view not in m.get('applicable_views',[]):
            return {'status':'VIEW_NOT_APPLICABLE','path':[],'mapping':m,'hierarchy_task_usable':False,'reason':'Mapping scope does not authorize selected relation view'}
        p=self.path_result(m['target_uid'],m.get('boundary_anchors'))
        excluded={item.get('task') if isinstance(item,dict) else item for item in m.get('excluded_tasks',[])}
        role=self.nodes[m['target_uid']]['role']
        usable=(p['status']=='CONNECTED' and m['mapping_type']=='EXACT' and m['identity_status'] in ('VERIFIED','SOURCE_CONFIRMED') and role in set().union(*TASK_ROLES.values()) and 'exact_identity_hierarchy_reward' not in excluded and 'within_source_hierarchy_reward' not in excluded)
        if target_scope=='world' and any(('world_exact' in str(t) or 'world_identity' in str(t)) for t in excluded):usable=False
        return {**p,'mapping':m,'identity_status':m['identity_status'],'hierarchy_task_usable':usable,'reward_scope':target_scope}

    def _domain(self, value: str) -> str:
        aliases=self.metadata.get('domain_aliases',{})
        return aliases.get(value,value)

    def relation_query(self,left,right,*,coarse_roots=(),requirement='classification'):
        if left not in self.nodes or right not in self.nodes:return {'distance':None,'reason':'UNKNOWN_UID','fine_lcas':[],'coarse_lcas':[]}
        a,b=self.nodes[left],self.nodes[right]
        if a.get('domain') and b.get('domain') and self._domain(a.get('domain'))!=self._domain(b.get('domain')):return {'distance':None,'reason':'CROSS_DOMAIN_NOT_CALIBRATED','fine_lcas':[],'coarse_lcas':[]}
        if requirement not in TASK_ROLES:raise ValueError('Unknown typed task policy')
        if a['role'] not in TASK_ROLES[requirement] or b['role'] not in TASK_ROLES[requirement]:
            return {'distance':None,'reason':'ENDPOINT_ROLE_REQUIRES_TYPED_TASK_POLICY','fine_lcas':[],'coarse_lcas':[]}
        if a.get('identity_status') in ('REVIEW','UNKNOWN') or b.get('identity_status') in ('REVIEW','UNKNOWN'):
            return {'distance':None,'reason':'IDENTITY_REVIEW','fine_lcas':[],'coarse_lcas':[]}
        if len({self.nodes[u]['role'] for u in self.groups[self._group(left)]})>1 or len({self.nodes[u]['role'] for u in self.groups[self._group(right)]})>1:
            return {'distance':None,'reason':'IDENTITY_ROLE_CONFLICT','fine_lcas':[],'coarse_lcas':[]}
        aa,bb=self._ancestors(left),self._ancestors(right);common=set(aa)&set(bb)
        # A lowest common ancestor has no other common descendant.
        excluded=set()
        for g in common:
            representative=self.groups[g][0]
            excluded.update(set(self._ancestors(representative))&common-{g})
        lowest=common-excluded
        coarse={self._group(u) for u in coarse_roots if u in self.nodes}
        for root in coarse_roots:
            if root in self.nodes:coarse.update(self._ancestors(root))
        coarse.update(self._coarse_groups)
        fine=lowest-coarse;coarse_common=common&coarse
        unpack=lambda gs:sorted(self.groups[g][0] for g in gs)
        return {'distance':min((aa[g]+bb[g] for g in fine),default=None),'reason':None if fine else 'ONLY_COARSE_COMMON_ANCESTORS' if common else 'NO_COMMON_ANCESTOR_IN_SELECTED_VIEW','fine_lcas':unpack(fine),'coarse_lcas':unpack(coarse_common),'lowest_lcas':unpack(lowest),'lca_details':[{'representative_uid':self.groups[g][0],'member_uids':self.groups[g],'native_ranks':sorted({self.nodes[u].get('rank') for u in self.groups[g] if self.nodes[u].get('rank')}),'semantic_grains':sorted({self.nodes[u].get('semantic_grain') for u in self.groups[g] if self.nodes[u].get('semantic_grain')}),'coarse':g in coarse} for g in sorted(lowest)],'metric_scope':'TYPED_ONTOLOGY_PATH_LENGTH_NOT_EVOLUTIONARY_OR_VISUAL_DISTANCE','relation_view':self.relation_view}

    def export_training(self,dataset,directory,*,version=None,target_scope='world'):
        registrations=[d for d in self.objects['datasets'] if d['dataset']==dataset and (not version or d['version']==version)]
        numeric_ids_verified=all(d.get('numeric_training_ids_verified',True) for d in registrations)
        output=Path(directory);output.mkdir(parents=True,exist_ok=True)
        rows=[]
        for m in self.task_labels(dataset,version=version,target_scope=target_scope):
            r=self.task_path(dataset,m['class_id'],version=m['version'],target_scope=target_scope)
            rows.append({'dataset':dataset,'version':m['version'],'class_id':m['class_id'],'raw_name':m['raw_name'],'target_uid':m.get('target_uid'),'mapping_type':m['mapping_type'],'path':r['path'],'hierarchy_task_usable':r.get('hierarchy_task_usable',False),'excluded_tasks':m.get('excluded_tasks',[]),'reason':r.get('reason') or m.get('reason'),'label_supervision_usable':numeric_ids_verified,'native_training_ids_verified':numeric_ids_verified})
        (output/'labels.jsonl').write_text(''.join(canonical(r)+'\n' for r in rows))
        return {'labels':len(rows),'hierarchy_usable':sum(r['hierarchy_task_usable'] for r in rows),'label_supervision_usable':sum(r['label_supervision_usable'] for r in rows)}
