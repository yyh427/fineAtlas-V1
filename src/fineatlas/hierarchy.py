"""Evidence-backed refinements replayed before shared graph construction.

Only explicit typed operations are accepted. Original source endpoints and
declarations remain intact; no lexical matching occurs during migration.
"""
from __future__ import annotations
import collections, hashlib, json
from pathlib import Path
from .semantics import role_expression

LINK_ROLES = {'IS_A':({'CLASS'},{'CLASS'}),'DESIGN_TYPE_OF':({'MODEL','MODEL_FAMILY'},{'CLASS'}),'CONFIGURATION_TYPE_OF':({'CONFIGURATION'},{'CLASS'}),'CONFIGURATION_OF':({'CONFIGURATION'},{'MODEL','MODEL_FAMILY'}),'INSTANCE_OF':({'INSTANCE'},{'CLASS','MODEL','MODEL_FAMILY'}),'SERIES_MEMBER_OF':({'MODEL'},{'MODEL_FAMILY'})}
LINK_ROLES['REGULATED_AS']=({'MODEL','CONFIGURATION'},{'CLASS'})
LINK_ROLES['NATIVE_CLASSIFICATION_PARENT']=({'CLASS'},{'CLASS'})
LINK_ROLES['NATIVE_DESIGN_PARENT']=({'MODEL','MODEL_FAMILY'},{'MODEL','MODEL_FAMILY'})

def validate_link_roles(relation, child_role, parent_role):
    roles=LINK_ROLES.get(relation)
    if not roles or child_role not in roles[0] or parent_role not in roles[1]:
        raise ValueError(f'Refinement relation {relation} cannot join {child_role} to {parent_role}')

def reconcile_instance_endpoints(m):
    """Apply authoritative later instance roles to earlier inclusion claims.

    This runs after all frozen role cohorts. Only excluded endpoint roles are
    touched; source declarations remain intact. Such arcs cannot enter any
    admitted classification graph, so removing them preserves existing views.
    """
    c = m.c
    rows = c.execute("""SELECT e.*,p.node_kind child_role,q.node_kind parent_role
      FROM edges e LEFT JOIN node_profiles p ON p.uid=e.child_uid
      LEFT JOIN node_profiles q ON q.uid=e.parent_uid
      WHERE e.status='ACTIVE' AND e.relation='IS_A'
      AND (p.node_kind='INSTANCE' OR q.node_kind='INSTANCE') ORDER BY e.id""").fetchall()
    count = 0
    for row in rows:
        individual = row['child_uid'] if row['child_role']=='INSTANCE' else row['parent_uid']
        decision = c.execute("SELECT r.evidence_id,r.canonical_role,p.attributes FROM normalization_roles r JOIN node_profiles p ON p.uid=r.uid WHERE r.uid=?",(individual,)).fetchone()
        if not decision or decision['canonical_role']!='INSTANCE' or json.loads(decision['attributes']).get('role_status')!='VERIFIED':
            raise ValueError('Instance endpoint lacks an authoritative role decision: '+individual)
        for table in ('view_roots','view_paths'):
            if c.execute(f'SELECT 1 FROM {table} WHERE witness_id=? LIMIT 1',(row['id'],)).fetchone():
                raise ValueError('Invalid inclusion has a cached admitted witness; rebuild required')
        native = c.execute('SELECT source_uri FROM node_profiles WHERE uid=?',(individual,)).fetchone()[0]
        proof = {'basis':'AUTHORITATIVE_INSTANCE_ROLE_EXCLUDES_ORDINARY_INCLUSION',
                 'individual_uid':individual,'role_evidence_id':decision['evidence_id'],
                 'original_edge_id':row['id'],'original_source':row['source'],
                 'license':'Original source attribution and assertion retained'}
        source = 'Canonical instance endpoint contract'
        eid = m.evidence(source,native,proof,'HIERARCHY_ENDPOINT_CONTRACT')
        data = json.loads(row['data'] or '{}')
        data.update(eligible_for_final_dag=False,hierarchy_disposition=proof,hierarchy_evidence_id=eid)
        before = {k:row[k] for k in row.keys() if k not in {'child_role','parent_role'}}
        c.execute("UPDATE edges SET status='HIERARCHY_SUPERSEDED',data=?,reason=? WHERE id=?",(json.dumps(data,sort_keys=True),proof['basis'],row['id']))
        m.change('hierarchy','edge',row['id'],before,{'status':'HIERARCHY_SUPERSEDED'},proof)
        record = {'op':'canonical_instance_endpoint_exclusion','uid':row['child_uid'],
                  'parent':row['parent_uid'],'edge_id':row['id'],'source':source,'uri':native,'proof':proof}
        payload = json.dumps(record,sort_keys=True,ensure_ascii=False)
        c.execute('INSERT OR IGNORE INTO hierarchy_decisions VALUES (?,?,?,?,?,?)',
                  (hashlib.sha256(payload.encode()).hexdigest(),record['op'],record['uid'],record['parent'],eid,payload))
        count += 1
    m.meta('strict_classification_edges',c.execute("SELECT count(*) FROM edges WHERE status='ACTIVE' AND relation='IS_A'").fetchone()[0])
    m.meta('hierarchy_endpoint_contracts',{'superseded_instance_inclusions':count,'graph_admission_unchanged':True})
    c.commit()
    return {'superseded_instance_inclusions':count,'graph_admission_unchanged':True}

VERSION = 'v1.8.0-hierarchy-review'
LAYER = 'v1.8-hierarchy-review'

def apply_refinements(migration, input_name='hierarchy_facts.jsonl'):
    m=migration;c=m.c;path=m.inputs/input_name
    if any((m.inputs/name).exists() for name in ['hierarchy_facts.incomplete','hierarchy_work.incomplete']):
        raise ValueError('Hierarchy source preparation is incomplete; resume this stage after its frozen manifest is ready')
    if not path.exists(): return {'status':'not_requested'}
    counts=collections.Counter()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS hierarchy_decisions(id TEXT PRIMARY KEY,operation TEXT NOT NULL,
      subject_uid TEXT NOT NULL,object_uid TEXT NOT NULL,evidence_id TEXT NOT NULL,payload TEXT NOT NULL);
    CREATE UNIQUE INDEX IF NOT EXISTS hierarchy_source_arc ON edges(child_uid,parent_uid,relation,source,layer)
      WHERE layer='v1.8-hierarchy-review';
    ''')
    records=[]
    with path.open() as f:
        for line in f:
            if line.strip():records.append(json.loads(line))
    # Deduplicate identical frozen decisions without changing source order.
    records=list({json.dumps(r,sort_keys=True,ensure_ascii=False):r for r in records}.values())
    # Input order cannot change what endpoints exist when links are admitted.
    for r in records:
        if r['op']!='class':continue
        proof=r['proof']
        if not r.get('definition') or not proof.get('basis') or not r.get('parents'):
            raise ValueError('A professional class needs a definition, source basis and parents')
        counts['new_classes']+=m.add_node(r['uid'],r['label'],'CLASS',r['domain'],r['source'],r['uri'],proof,r['definition'])
        attrs=json.loads(c.execute('SELECT attributes FROM node_profiles WHERE uid=?',(r['uid'],)).fetchone()[0])
        attrs.update(classification_axis=r.get('axis','physical_structure'),semantic_grain='native_regulatory_type' if r.get('axis')=='native_regulatory_classification' else 'professional_type',hierarchy_definition=r['definition'])
        c.execute('UPDATE node_profiles SET attributes=? WHERE uid=?',(json.dumps(attrs,sort_keys=True),r['uid']))
        for name in r.get('aliases',[]):m.alias(r['uid'],name,r['source'])
    # Canonical roles must settle before any parent inclusion is evaluated.
    for r in records:
        if r['op']=='role':m.role(r['uid'],r['role'],r['proof'],r['source'],r['uri'])
    def endpoint_role(uid):
        row=c.execute('SELECT '+role_expression('n','p')+" role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=? AND n.visibility='ACTIVE'",(uid,)).fetchone()
        if not row:raise ValueError('Missing active refinement endpoint: '+uid)
        return row[0]
    def source_evidence(r):
        if not r.get('uri') or not r.get('proof',{}).get('basis'):raise ValueError('Missing refinement evidence')
        record_hash=r['proof'].get('native_record_sha256')
        if record_hash:
            native_uid=r['proof'].get('native_record_uid',r['uid'])
            native=c.execute('SELECT data FROM nodes WHERE uid=?',(native_uid,)).fetchone()
            if not native or hashlib.sha256(native[0].encode()).hexdigest()!=record_hash:
                raise ValueError('Frozen native-record checksum differs: '+native_uid)
        return m.evidence(r['source'],r['uri'],r['proof'],'HIERARCHY_REFINEMENT')
    def add_class_edge(child,parent,r,relation='IS_A'):
        a=c.execute('SELECT component_id,visibility FROM nodes WHERE uid=?',(child,)).fetchone()
        b=c.execute('SELECT component_id,visibility FROM nodes WHERE uid=?',(parent,)).fetchone()
        if not a or not b or a['visibility']!='ACTIVE' or b['visibility']!='ACTIVE':raise ValueError('Inactive or missing inclusion endpoint')
        if a['component_id']==b['component_id']:return
        validate_link_roles(relation,endpoint_role(child),endpoint_role(parent))
        eid=source_evidence(r)
        c.execute('''INSERT OR IGNORE INTO edges(child_uid,parent_uid,relation,original_relation,
          facet_family,classification_basis,navigation_role,source,source_relation,confidence,provenance,data,layer,status,reason)
          VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)''',
          (child,parent,relation,relation,'NATIVE_OBJECT_KIND' if relation=='IS_A' else 'NATIVE_NAVIGATION',r['proof']['basis'],'SOURCE_VALIDATED',r['source'],'EVIDENCED_SUBSUMPTION' if relation=='IS_A' else 'NATIVE_CLASSIFICATION_PARENT',json.dumps({'evidence_ids':[eid]}),
           json.dumps({'eligible_for_final_dag':relation=='IS_A','admission_basis':r['proof'],'classification_axis':r.get('axis','physical_structure')}),LAYER,'ACTIVE' if relation=='IS_A' else 'TYPED_ACTIVE','Definition or native-field scope entails professional parent'))
    for i,r in enumerate(records):
        op=r['op'];uid=r.get('uid','');eid=source_evidence(r)
        if op=='class':
            for parent in r['parents']:add_class_edge(uid,parent,r,r.get('parent_relation','IS_A'))
        elif op=='role':
            counts['role_decisions']+=1
        elif op=='link':
            parent=r['parent'];rel=r['relation']
            if rel=='IS_A':add_class_edge(uid,parent,r)
            else:
                validate_link_roles(rel,endpoint_role(uid),endpoint_role(parent))
                m.typed(uid,parent,rel,r['proof'],r['source'],r['uri'])
            counts['professional_links']+=1
        elif op=='withdraw_edge':
            e=c.execute('SELECT * FROM edges WHERE id=?',(r['edge_id'],)).fetchone()
            if not e or (e['child_uid'],e['parent_uid'])!=(uid,r['parent']):raise ValueError('Withdrawal endpoints differ from frozen source')
            data=json.loads(e['data'] or '{}');data.update(eligible_for_final_dag=False,hierarchy_disposition=r['proof'],hierarchy_evidence_id=eid)
            c.execute("UPDATE edges SET status='HIERARCHY_SUPERSEDED',data=?,reason=? WHERE id=?",(json.dumps(data,sort_keys=True),r['proof']['basis'],e['id']))
            m.change('hierarchy','edge',e['id'],dict(e),{'status':'HIERARCHY_SUPERSEDED'},r['proof']);counts['superseded_source_edges']+=1
        elif op=='withdraw_typed':
            e=c.execute('SELECT * FROM entity_relations WHERE id=?',(r['relation_id'],)).fetchone()
            if not e or e['subject_uid']!=uid:raise ValueError('Typed withdrawal differs')
            c.execute("UPDATE entity_relations SET status='HIERARCHY_SUPERSEDED' WHERE id=?",(e['id'],));m.change('hierarchy','typed',e['id'],dict(e),{'status':'HIERARCHY_SUPERSEDED'},r['proof'])
        elif op=='restore_edge':
            e=c.execute('SELECT * FROM edges WHERE id=?',(r['edge_id'],)).fetchone()
            if not e or (e['child_uid'],e['parent_uid'])!=(uid,r['parent']):raise ValueError('Restoration endpoints differ from frozen source')
            original=c.execute("SELECT before_json FROM usability_changes WHERE stage='hierarchy' AND object_type='edge' AND object_id=? ORDER BY id LIMIT 1",(str(e['id']),)).fetchone()
            before=json.loads(original[0]) if original else None
            if not before or before['status']!='ACTIVE':raise ValueError('No original active declaration for restoration')
            c.execute('UPDATE edges SET status=?,data=?,reason=? WHERE id=?',(before['status'],before['data'],before['reason'],e['id']))
            m.change('hierarchy','edge',e['id'],dict(e),{'status':'ACTIVE','restored_original_admission':True},r['proof'])
        elif op=='split_identity':
            b=c.execute('SELECT * FROM bridges WHERE id=?',(r['bridge_id'],)).fetchone()
            if not b or {b['left_uid'],b['right_uid']}!={uid,r['parent']}:raise ValueError('Identity withdrawal differs')
            c.execute("UPDATE bridges SET status='GRAIN_REJECTED',reason=? WHERE id=?",(r['proof']['basis'],b['id']))
            # Repartition only this old identity component using every surviving bridge.
            old=c.execute('SELECT component_id FROM nodes WHERE uid=?',(uid,)).fetchone()[0]
            members=[x[0] for x in c.execute('SELECT uid FROM nodes WHERE component_id=? ORDER BY uid',(old,))]
            adj={x:set() for x in members}
            for x in members:
                for bridge in c.execute("SELECT left_uid,right_uid FROM bridges WHERE status='ACTIVE' AND relation='SAME_CONCEPT' AND (left_uid=? OR right_uid=?)",(x,x)):
                    a,z=bridge
                    if a in adj and z in adj:adj[a].add(z);adj[z].add(a)
            seen=set();parts=[]
            for x in members:
                if x in seen:continue
                todo=[x];part=[]
                while todo:
                    v=todo.pop()
                    if v in seen:continue
                    seen.add(v);part.append(v);todo.extend(sorted(adj[v]-seen))
                parts.append(part)
            for part in parts[1:]:
                new=c.execute('SELECT max(id)+1 FROM components').fetchone()[0]
                c.execute('INSERT INTO components(id,depth,wordnet_reachable) VALUES (?,NULL,0)',(new,));c.executemany('UPDATE nodes SET component_id=? WHERE uid=?',((new,x) for x in part))
            m.change('hierarchy','identity',b['id'],dict(b),{'parts':parts},r['proof']);counts['identity_groups_split']+=len(parts)-1
        elif op=='portal_roots':
            entry=c.execute('SELECT * FROM domain_registry WHERE canonical_name=?',(r['domain'],)).fetchone()
            if not entry or not r['roots']:raise ValueError('Missing professional domain roots')
            if not set(r['roots']).issubset(json.loads(entry['root_uids'])):
                raise ValueError('Professional roots must retain existing source-root correspondence')
            for root in r['roots']:
                if endpoint_role(root)!='CLASS':raise ValueError('Professional domain root is not a generic type')
            c.execute('UPDATE domain_registry SET root_uids=? WHERE domain_id=?',(json.dumps(r['roots']),entry['domain_id']))
            m.change('hierarchy','portal',r['domain'],dict(entry),{'root_uids':r['roots']},r['proof']);counts['professional_portals']+=1
        else:raise ValueError('Unknown hierarchy operation '+op)
        decision=hashlib.sha256(json.dumps(r,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        c.execute('INSERT OR IGNORE INTO hierarchy_decisions VALUES (?,?,?,?,?,?)',(decision,op,uid,r.get('parent',''),eid,json.dumps(r,sort_keys=True,ensure_ascii=False)))
        if i%10000==0:c.commit();print('HIERARCHY',i,len(records),dict(counts),flush=True)
    by_source=collections.defaultdict(list)
    for r in records:by_source[r['source']].append(r)
    for source,rows in sorted(by_source.items()):
        licenses=sorted({r['proof'].get('license','Original source terms and attribution retained') for r in rows})
        c.execute('INSERT OR REPLACE INTO source_catalogs VALUES (?,?,?,?,?)',('Hierarchy refinement: '+source,rows[0]['uri'],'; '.join(licenses),hashlib.sha256(path.read_bytes()).hexdigest(),json.dumps({'operations':len(rows),'classes':sum(r['op']=='class' for r in rows),'source_statement_retained':True},sort_keys=True)))
    prefix={'hierarchy_facts.jsonl':'hierarchy','hierarchy_extensions.jsonl':'hierarchy_extension','hierarchy_contract_repairs.jsonl':'hierarchy_contract_repair','hierarchy_role_repairs.jsonl':'hierarchy_role_repair'}[input_name]
    m.meta('release',VERSION);m.meta(prefix+'_revision',hashlib.sha256(path.read_bytes()).hexdigest());m.meta(prefix+'_refinement_counts',dict(counts));c.commit()
    return dict(counts)
