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
LINK_ROLES['TAXONOMIC_PARENT']=({'CLASS','BIOLOGICAL_VARIANT'},{'CLASS','BIOLOGICAL_VARIANT'})
LINK_ROLES['NATIVE_DESIGN_PARENT']=({'MODEL','MODEL_FAMILY'},{'MODEL','MODEL_FAMILY'})
LINK_ROLES['CONFIGURATION_OF']=({'CONFIGURATION'},{'MODEL','MODEL_FAMILY','CONFIGURATION'})
LINK_ROLES['DEPICTS_TYPE']=({'DATASET_CATEGORY'},{'CLASS','BIOLOGICAL_VARIANT'})
LINK_ROLES['HAS_ATTRIBUTE']=(
    {'CLASS','BIOLOGICAL_VARIANT','DATASET_CATEGORY','MODEL','MODEL_FAMILY','CONFIGURATION'},
    {'ATTRIBUTE'})

def validate_link_roles(relation, child_role, parent_role):
    roles=LINK_ROLES.get(relation)
    if not roles or child_role not in roles[0] or parent_role not in roles[1]:
        raise ValueError(f'Refinement relation {relation} cannot join {child_role} to {parent_role}')


def source_assertion_content(row):
    """Stable source content; row IDs and later dispositions are not identity."""
    return {key: value for key, value in dict(row).items()
            if key not in {'id', 'status', 'reason'}}


def source_assertion_sha256(row):
    return hashlib.sha256(json.dumps(source_assertion_content(row), sort_keys=True).encode()).hexdigest()


def locate_source_assertion(c, table, locator):
    """Resolve one exact frozen assertion across independent replay row IDs.

    The complete original content is checked after indexed endpoint lookup.
    Same names or a different source claim never substitute for this assertion.
    Ambiguous identical duplicates require review instead of picking the first.
    """
    endpoint_columns = {'entity_relations': ('subject_uid', 'object_uid'),
                        'bridges': ('left_uid', 'right_uid')}
    if table not in endpoint_columns:
        raise ValueError('Unsupported frozen assertion table')
    left, right = endpoint_columns[table]
    keys = (left, right, 'relation', 'source')
    if not all(locator.get(key) for key in keys) or not locator.get('content_sha256'):
        raise ValueError('Frozen assertion locator needs exact endpoints, source and content hash')
    rows = c.execute('SELECT * FROM ' + table + ' WHERE ' +
                     ' AND '.join(key + '=?' for key in keys),
                     tuple(locator[key] for key in keys)).fetchall()
    matches = [row for row in rows if source_assertion_sha256(row) == locator['content_sha256']]
    if len(matches) != 1:
        raise ValueError('Frozen source assertion is missing, changed or ambiguous')
    return matches[0]

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

UNIFIED_INPUT_PREFIXES={
    'structure_biology_identity_scope_facts.jsonl':'structure_biology_identity_scope',
    'structure_cars_author_scope_operations.jsonl':'structure_cars_author_scope',
    'structure_vehicle_source_scope_operations.jsonl':'structure_vehicle_source_scope_operations',
    'unified_field_refinements.jsonl':'unified_field',
    'unified_role_links.jsonl':'unified_role_navigation',
    'unified_classification_projection.jsonl':'unified_classification_projection',
    'unified_source_scope.jsonl':'unified_source_scope',
    'unified_navigation_completion.jsonl':'unified_navigation_completion',
    'unified_design_scope.jsonl':'unified_design_scope',
    'unified_breed_parents.jsonl':'unified_breed_parents',
    'unified_regulatory_roles.jsonl':'unified_regulatory_roles',
    'unified_taxonomic_scope.jsonl':'unified_taxonomic_scope',
    'unified_biological_units.jsonl':'unified_biological_units',
    'unified_final_role_links.jsonl':'unified_final_role_navigation',
    'unified_root_contracts.jsonl':'unified_root_contracts',
    'shared_role_repairs.jsonl':'shared_role_repairs',
    'repair_role_links.jsonl':'repair_role_navigation',
    'annotation_taxonomic_navigation.jsonl':'annotation_taxonomic_navigation',
}

def review_version(inputs):
    path = Path(inputs)/'review_release.json'
    if path.exists():
        value = json.loads(path.read_text())['version']
        if value not in {'v1.8.0-hierarchy-review', 'v1.8.1-hierarchy-review', 'v1.10.0-unified-review', 'v1.10.1-repair-review',
                         'v1.11.0-structure-review', 'v1.11.0rc1', 'v1.11.0'}:
            raise ValueError('Unsupported hierarchy candidate version')
        return value
    return VERSION if (Path(inputs)/'hierarchy_facts.jsonl').exists() else 'v1.7.1-review'

def validate_identity_role_only(c, records):
    """Prove an isolated source alias can adopt its native design identity.

    CLASS and design roles have identical classification admission. With no
    incident admitted assertions, changing this alias cannot alter any graph,
    witness, scope, terminal connection or classification weight.
    """
    for r in records:
        if r.get('op')!='role' or r.get('role') not in {'MODEL','MODEL_FAMILY'}:
            raise ValueError('Identity role refresh only accepts design role decisions')
        uid=r['uid'];authority=r['proof'].get('native_design_authority_uid')
        n=c.execute('SELECT n.component_id,n.data,n.visibility,'+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(uid,)).fetchone()
        a=c.execute('SELECT n.component_id,n.source,n.data,n.visibility,p.attributes,'+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(authority,)).fetchone()
        if not n or not a or n['visibility']!='ACTIVE' or a['visibility']!='ACTIVE' or n['component_id']!=a['component_id'] or n['role'] not in {'CLASS',r['role']} or a['role']!=r['role']:
            raise ValueError('Alias lacks an admitted same-identity native design authority')
        if a['source'] not in {'faa','epa'} and json.loads(a['attributes'] or '{}').get('role_status')!='VERIFIED':
            raise ValueError('Identity authority has no explicit verified design grain')
        for value,key in [(n,'native_record_sha256'),(a,'authority_native_record_sha256')]:
            if hashlib.sha256(value['data'].encode()).hexdigest()!=r['proof'].get(key):
                raise ValueError('Identity role source checksum differs')
        if c.execute("SELECT 1 FROM edges WHERE status IN ('ACTIVE','TYPED_ACTIVE') AND (child_uid=? OR parent_uid=?) LIMIT 1",(uid,uid)).fetchone() or c.execute("SELECT 1 FROM entity_relations WHERE status='ACTIVE' AND (subject_uid=? OR object_uid=?) LIMIT 1",(uid,uid)).fetchone():
            raise ValueError('Alias has incident assertions; a complete graph rebuild is required')
    return {'source_uids':len(records),'graph_admission_unchanged':True}

def apply_identity_role_repairs(m):
    path=m.inputs/'hierarchy_identity_role_repairs.jsonl'
    if not path.exists():return {'status':'not_requested'}
    records=[json.loads(line) for line in path.open() if line.strip()]
    proof=validate_identity_role_only(m.c,records)
    result=apply_refinements(m,path.name)
    return {**result,**proof}

def validate_condition_shortcut(m,r):
    from .engineering_roles import aircraft_engine_conditions
    c=m.c;proof=r['proof'];replacement=proof.get('replacement_parent')
    if r['relation']!='IS_A' or not replacement:raise ValueError('Condition shortcut needs a class replacement')
    def n(u):return c.execute('SELECT n.label,n.data,n.component_id,n.visibility,'+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(u,)).fetchone()
    child,parent,old=n(r['uid']),n(replacement),n(r['parent'])
    if not all(x and x['visibility']=='ACTIVE' and x['role']=='CLASS' for x in (child,parent,old)):raise ValueError('Condition shortcut endpoints must be active classes')
    a,b=aircraft_engine_conditions(child['label']),aircraft_engine_conditions(parent['label'])
    if not a or not b or a[0]!=b[0] or not a[1]>b[1]:raise ValueError('Native conditions do not strictly entail the replacement')
    if hashlib.sha256(child['data'].encode()).hexdigest()!=proof.get('native_record_sha256') or hashlib.sha256(parent['data'].encode()).hexdigest()!=proof.get('native_parent_sha256'):raise ValueError('Native condition source checksum differs')
    if not c.execute("SELECT 1 FROM edges WHERE child_uid=? AND parent_uid=? AND relation='IS_A' AND status='ACTIVE'",(r['uid'],replacement)).fetchone():raise ValueError('Condition replacement lacks a surviving inclusion')
    witness=c.execute("""WITH RECURSIVE up(component_id) AS (
      VALUES (?) UNION SELECT pn.component_id FROM up
      JOIN nodes cn ON cn.component_id=up.component_id AND cn.visibility='ACTIVE'
      JOIN edges e ON e.child_uid=cn.uid AND e.status='ACTIVE' AND e.relation='IS_A'
      JOIN nodes pn ON pn.uid=e.parent_uid AND pn.visibility='ACTIVE'
      LEFT JOIN node_profiles cp ON cp.uid=cn.uid LEFT JOIN node_profiles pp ON pp.uid=pn.uid
      WHERE coalesce(cp.node_kind,'CLASS')='CLASS' AND coalesce(pp.node_kind,'CLASS')='CLASS')
      SELECT 1 FROM up WHERE component_id=? LIMIT 1""",(parent['component_id'],old['component_id'])).fetchone()
    if not witness:raise ValueError('Withdrawing a condition shortcut would lose its ancestor witness')


def withdraw_frozen_link(m,r,eid):
    """Supersede only an exact stored claim with a later grain conflict."""
    c=m.c;uid=r['uid']
    prior=c.execute('SELECT payload FROM hierarchy_decisions WHERE id=?',(r['proof']['original_frozen_decision_id'],)).fetchone()
    if not prior:raise ValueError('Missing exact prior frozen link decision')
    claim=json.loads(prior[0]);parent=r['parent'];rel=r['relation']
    if (claim.get('op'),claim.get('uid'),claim.get('parent'),claim.get('relation'),claim.get('source'))!=('link',uid,parent,rel,r['proof']['original_frozen_source']):
        raise ValueError('Prior frozen link differs from completion withdrawal')
    endpoints=[c.execute('SELECT n.visibility,'+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(u,)).fetchone() for u in (uid,parent)]
    roles=LINK_ROLES.get(rel)
    if roles and all(e and e['visibility']=='ACTIVE' and e['role'] in permitted for e,permitted in zip(endpoints,roles)):
        if r['proof'].get('basis')=='STRICT_NATIVE_CONDITIONS_WITH_SURVIVING_ANCESTOR_REPLACE_SHORTCUT':
            validate_condition_shortcut(m,r)
        else:
            # A retained source definition can also disprove an earlier lexical
            # parent whose noun came from the purpose of the whole subject.
            proof=r['proof'];replacement=proof.get('replacement_parent')
            if rel!='IS_A' or proof.get('basis')!='VERIFIED_SUBJECT_GENUS_SUPERSEDES_PRIOR_FROZEN_LINK' or not replacement:
                raise ValueError('Completion withdrawal has no endpoint-grain conflict')
            from .engineering_roles import definition_head
            from .nominal import WordNetKinds
            native=c.execute('SELECT label,data,component_id FROM nodes WHERE uid=?',(uid,)).fetchone()
            head=definition_head(proof.get('source_statement',''),native['label'],subject_aliases=proof.get('native_subject_aliases',()))
            if not head or head!=proof.get('subject_kind_head') or hashlib.sha256(native['data'].encode()).hexdigest()!=proof.get('native_record_sha256'):
                raise ValueError('Replacement lacks an independently verified whole-subject genus')
            target=c.execute('SELECT n.component_id,n.visibility,'+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(replacement,)).fetchone()
            old_comp=c.execute('SELECT component_id FROM nodes WHERE uid=?',(parent,)).fetchone()[0]
            if not target or target['visibility']!='ACTIVE' or target['role']!='CLASS' or target['component_id']==old_comp:
                raise ValueError('Replacement genus is missing or unchanged')
            k=WordNetKinds(c,include_native=True);words=head.split();candidates=set()
            for size in range(min(7,len(words)),0,-1):
                candidates=k.contextual_candidates(' '.join(words[-size:]),proof.get('source_statement',''))
                if candidates:break
            comps={c.execute('SELECT component_id FROM nodes WHERE uid=?',(v,)).fetchone()[0] for v in candidates}
            if target['component_id'] not in comps or old_comp in comps:
                raise ValueError('The lexical genus does not independently distinguish the replacement')
            same_identity=native['component_id']==target['component_id']
            if not same_identity and not c.execute("SELECT 1 FROM edges WHERE child_uid=? AND parent_uid=? AND relation='IS_A' AND status='ACTIVE'",(uid,replacement)).fetchone():
                raise ValueError('Replacement needs a surviving independently evidenced class link')
    if rel=='IS_A':
        rows=c.execute('SELECT * FROM edges WHERE child_uid=? AND parent_uid=? AND relation=? AND source=? AND layer=?',(uid,parent,rel,claim['source'],LAYER)).fetchall()
        for e in rows:
            data=json.loads(e['data'] or '{}');data.update(eligible_for_final_dag=False,hierarchy_disposition=r['proof'],hierarchy_evidence_id=eid)
            c.execute("UPDATE edges SET status='HIERARCHY_SUPERSEDED',data=?,reason=? WHERE id=?",(json.dumps(data,sort_keys=True),r['proof']['basis'],e['id']))
            m.change('hierarchy','edge',e['id'],dict(e),{'status':'HIERARCHY_SUPERSEDED'},r['proof'])
    else:
        rows=c.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',(uid,parent,rel,claim['source'])).fetchall()
        for e in rows:
            c.execute("UPDATE entity_relations SET status='HIERARCHY_SUPERSEDED' WHERE id=?",(e['id'],));m.change('hierarchy','typed',e['id'],dict(e),{'status':'HIERARCHY_SUPERSEDED'},r['proof'])
    if not rows and c.execute('SELECT component_id FROM nodes WHERE uid=?',(uid,)).fetchone()[0]!=c.execute('SELECT component_id FROM nodes WHERE uid=?',(parent,)).fetchone()[0]:
        raise ValueError('Prior frozen link has no stored assertion or identity witness')
    return len(rows)


def apply_refinements(migration, input_name='hierarchy_facts.jsonl'):
    m=migration;c=m.c;path=m.inputs/input_name
    if any((m.inputs/name).exists() for name in ['hierarchy_facts.incomplete','hierarchy_work.incomplete']):
        raise ValueError('Hierarchy source preparation is incomplete; resume this stage after its frozen manifest is ready')
    if not path.exists(): return {'status':'not_requested'}
    if input_name.startswith('unified_') and input_name not in UNIFIED_INPUT_PREFIXES:
        raise ValueError('Unsupported unified source input; no source rules have been applied: '+input_name)
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
        attrs.update(classification_axis=r.get('axis','physical_structure'),semantic_grain=r.get('semantic_grain','native_regulatory_type' if r.get('axis')=='native_regulatory_classification' else 'professional_type'),hierarchy_definition=r['definition'])
        c.execute('UPDATE node_profiles SET attributes=? WHERE uid=?',(json.dumps(attrs,sort_keys=True),r['uid']))
        for name in r.get('aliases',[]):m.alias(r['uid'],name,r['source'])
    # Canonical roles must settle before any parent inclusion is evaluated.
    for r in records:
        if r['op']=='role':m.role(r['uid'],r['role'],r['proof'],r['source'],r['uri'])
        elif r['op']=='activate_native_type':
            n=c.execute('SELECT * FROM nodes WHERE uid=?',(r['uid'],)).fetchone()
            if not n or not r['uid'].startswith('wordnet31:') or n['visibility'] not in {'PRUNED_WORDNET','ACTIVE'}:
                raise ValueError('Native type restoration requires a retained WordNet record')
            if hashlib.sha256(n['data'].encode()).hexdigest()!=r['proof'].get('native_record_sha256') or n['description']!=r['definition'] or not r.get('parents'):
                raise ValueError('Native type source definition or checksum differs')
            m.role(r['uid'],'CLASS',{**r['proof'],'allowed_views':['strict','taxonomy','membership']},r['source'],r['uri'])
            c.execute("UPDATE nodes SET visibility='ACTIVE' WHERE uid=?",(r['uid'],))
            m.change('hierarchy','source_visibility',r['uid'],{'visibility':n['visibility']},{'visibility':'ACTIVE'},r['proof'])
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
        elif op=='activate_native_type':
            for parent in r['parents']:add_class_edge(uid,parent,r)
            counts['restored_native_types']+=1
        elif op=='role':
            counts['role_decisions']+=1
            if r['proof'].get('basis') in ('DEFINED_PRIMARY_DESIGN_UNIT_PLUS_MANUFACTURER_AND_UNCHANGED_ENTITY_SCOPE',
                                         'DEFINED_PRIMARY_DESIGN_UNIT_AND_CORROBORATED_FULL_ENTITY_SCOPE'):
                prior=json.loads(c.execute('SELECT attributes FROM node_profiles WHERE uid=?',(uid,)).fetchone()[0])
                attributes={**prior,'verified_wikidata_manufacturer_ids':r['proof']['manufacturers'],
                            'source_scope_snapshot':r['proof']['snapshot'],
                            'native_design_scope':r['proof']['unit_rule']['semantic_definition']}
                c.execute('UPDATE node_profiles SET attributes=? WHERE uid=?',(json.dumps(attributes,sort_keys=True),uid))
                m.change('verified_source_scope','profile_attributes',uid,prior,attributes,r['proof'])
        elif op=='source_review':
            n=c.execute('SELECT visibility FROM nodes WHERE uid=?',(uid,)).fetchone()
            if not n:raise ValueError('Missing source-review record')
            if not r['proof'].get('review_reason'):raise ValueError('Missing unresolved-grain review reason')
            m.role(uid,'UNKNOWN',{**r['proof'],'allowed_views':[]},r['source'],r['uri'])
            c.execute("UPDATE nodes SET visibility='SOURCE_ONLY' WHERE uid=?",(uid,))
            m.change('hierarchy','source_visibility',uid,dict(n),{'visibility':'SOURCE_ONLY'},r['proof'])
            counts['source_records_retained_for_review']+=1
        elif op=='link':
            parent=r['parent'];rel=r['relation']
            if rel in ('IS_A','NATIVE_CLASSIFICATION_PARENT','TAXONOMIC_PARENT'):
                add_class_edge(uid,parent,r,rel)
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
        elif op=='quarantine_source_edge':
            e=c.execute('SELECT * FROM edges WHERE id=?',(r['edge_id'],)).fetchone()
            if not e or (e['child_uid'],e['parent_uid'])!=(uid,r['parent']):raise ValueError('Source semantic quarantine endpoints differ')
            if not r['proof'].get('individual_semantic_review') or not r['proof'].get('source_scope_conflict'):
                raise ValueError('Source quarantine requires an explicit semantic counterexample')
            alternatives=r['proof'].get('replacement_edge_ids',[])
            if not alternatives or not all(c.execute("SELECT 1 FROM edges WHERE id=? AND child_uid=? AND status='ACTIVE' AND relation='IS_A'",(rid,uid)).fetchone() for rid in alternatives):
                raise ValueError('Source correction lacks retained valid alternative parents')
            # Keep the entire original source payload and endpoints untouched;
            # the new disposition and review live in their normal ledgers.
            c.execute("UPDATE edges SET status='HIERARCHY_SUPERSEDED' WHERE id=?",(e['id'],))
            m.change('source_semantic_contract','edge',e['id'],dict(e),{'status':'HIERARCHY_SUPERSEDED'},r['proof'])
            counts['invalid_source_arcs_quarantined']+=1
        elif op=='withdraw_typed_source':
            e=locate_source_assertion(c,'entity_relations',r['locator'])
            if e['subject_uid']!=uid or e['status'] not in {'ACTIVE','HIERARCHY_SUPERSEDED'}:
                raise ValueError('Exact typed source withdrawal has incompatible scope/status')
            if e['status']=='ACTIVE':
                c.execute("UPDATE entity_relations SET status='HIERARCHY_SUPERSEDED' WHERE id=?",(e['id'],))
                m.change('hierarchy','typed',e['id'],dict(e),{'status':'HIERARCHY_SUPERSEDED'},r['proof'])
                counts['superseded_exact_typed_sources']+=1
            else:counts['typed_source_withdrawals_already_applied']+=1
        elif op=='withdraw_typed':
            e=c.execute('SELECT * FROM entity_relations WHERE id=?',(r['relation_id'],)).fetchone()
            if not e or e['subject_uid']!=uid:raise ValueError('Typed withdrawal differs')
            c.execute("UPDATE entity_relations SET status='HIERARCHY_SUPERSEDED' WHERE id=?",(e['id'],));m.change('hierarchy','typed',e['id'],dict(e),{'status':'HIERARCHY_SUPERSEDED'},r['proof'])
        elif op=='withdraw_frozen_link':
            counts['superseded_prior_frozen_links']+=withdraw_frozen_link(m,r,eid)
        elif op=='restore_edge':
            e=c.execute('SELECT * FROM edges WHERE id=?',(r['edge_id'],)).fetchone()
            if not e or (e['child_uid'],e['parent_uid'])!=(uid,r['parent']):raise ValueError('Restoration endpoints differ from frozen source')
            original=c.execute("SELECT before_json FROM usability_changes WHERE stage='hierarchy' AND object_type='edge' AND object_id=? ORDER BY id LIMIT 1",(str(e['id']),)).fetchone()
            before=json.loads(original[0]) if original else None
            if not before or before['status']!='ACTIVE':raise ValueError('No original active declaration for restoration')
            c.execute('UPDATE edges SET status=?,data=?,reason=? WHERE id=?',(before['status'],before['data'],before['reason'],e['id']))
            m.change('hierarchy','edge',e['id'],dict(e),{'status':'ACTIVE','restored_original_admission':True},r['proof'])
        elif op in ('split_identity','split_identity_source'):
            b=(locate_source_assertion(c,'bridges',r['locator']) if op=='split_identity_source'
               else c.execute('SELECT * FROM bridges WHERE id=?',(r['bridge_id'],)).fetchone())
            if not b or {b['left_uid'],b['right_uid']}!={uid,r['parent']}:raise ValueError('Identity withdrawal differs')
            if b['status']=='GRAIN_REJECTED' and b['reason']==r['proof']['basis']:
                # Replaying the same source review cannot allocate more
                # components or invent another identity partition.
                counts['identity_source_splits_already_applied']+=1
                continue
            if b['status']!='ACTIVE' or b['relation']!='SAME_CONCEPT':
                raise ValueError('Identity withdrawal needs its original active source declaration')
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
    prefix={'hierarchy_facts.jsonl':'hierarchy','hierarchy_extensions.jsonl':'hierarchy_extension','hierarchy_contract_repairs.jsonl':'hierarchy_contract_repair','hierarchy_role_repairs.jsonl':'hierarchy_role_repair','hierarchy_semantic_repairs.jsonl':'hierarchy_semantic_repair','hierarchy_identity_role_repairs.jsonl':'hierarchy_identity_role_repair','hierarchy_type_repairs.jsonl':'hierarchy_type_repair','hierarchy_shape_repairs.jsonl':'hierarchy_shape_repair','hierarchy_structure_repairs.jsonl':'hierarchy_structure_repair','hierarchy_shape_completion.jsonl':'hierarchy_shape_completion','hierarchy_subject_repairs.jsonl':'hierarchy_subject_repair','hierarchy_admission_reviews.jsonl':'hierarchy_admission_review',
            **UNIFIED_INPUT_PREFIXES, 'structure_biology_links.jsonl':'structure_biology_links', 'structure_engineering_operations.jsonl':'structure_engineering_operations', 'structure_breeds_links.jsonl':'structure_breeds_links', 'structure_source_contracts_operations.jsonl':'structure_source_contracts_operations', 'structure_vehicle_source_scope_operations.jsonl':'structure_vehicle_source_scope_operations', 'structure_biology_identity_scope_facts.jsonl':'structure_biology_identity_scope', 'structure_cars_author_scope_operations.jsonl':'structure_cars_author_scope'}[input_name]
    m.meta('release',review_version(m.inputs));m.meta(prefix+'_revision',hashlib.sha256(path.read_bytes()).hexdigest());m.meta(prefix+'_refinement_counts',dict(counts));c.commit()
    return dict(counts)
