"""Append independently reviewed complete-owned physical types at a checkpoint.

Raw source objects, identities and dataset mappings remain unchanged. Explicit
source-grain corrections and incompatible relation reviews retain their full
before declarations and histories. Parent classes must already be admitted;
activation and new nodes are outside this additive contract.
"""
from __future__ import annotations

from collections import Counter
import json
import re
from pathlib import Path

from .hierarchy import source_assertion_sha256, validate_link_roles
from .semantics import role_expression
from .structure_complete_owned_type_rules import complete_owned_physical_genus, owned_generic_class_scope
from .structure_owned_scope_repairs import validate_batch_cycles
from .structure_regression_repairs import sha

INPUT_NAME = 'structure_complete_owned_type_repairs.json'
OPERATION_NAME = 'hierarchy_complete_owned_type_repairs.jsonl'
METADATA_KEY = 'complete_owned_type_repairs'
SOURCE = 'Reviewed complete owned physical type and source range'


def dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def parent_manifest_sha256(value):
    # The immutable completed-parent manifest contract predates this stage.
    # Its documented ordinary JSON hash is separate from evidence encoding.
    return sha(json.dumps(value,sort_keys=True,ensure_ascii=False))


def safe_input(inputs, name):
    if not isinstance(name, str) or Path(name).name != name or name in ('', '.', '..'):
        raise ValueError('Scope evidence must be an explicit safe frozen input')
    return inputs / name


def node(c, uid):
    return c.execute('SELECT n.*, '+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?', (uid,)).fetchone()


def witness_value(data, path):
    value = data
    for part in path.split('.'):
        if not isinstance(value, dict) or part not in value:
            raise ValueError('Complete own source field is missing')
        value = value[part]
    return value


def validate_witness(c, witness):
    n = c.execute('SELECT data FROM nodes WHERE uid=?', (witness['uid'],)).fetchone()
    if not n or sha(n['data']) != witness['data_sha256']:
        raise ValueError('Complete source record changed')
    if witness_value(json.loads(n['data']), witness['field_path']) != witness['statement']:
        raise ValueError('Full source statement differs from its original field')


def scope_inventory(c, uid):
    return {
        'edges_incoming':[dict(r) for r in c.execute('SELECT * FROM edges WHERE parent_uid=? ORDER BY id',(uid,))],
        'edges_outgoing':[dict(r) for r in c.execute('SELECT * FROM edges WHERE child_uid=? ORDER BY id',(uid,))],
        'typed_incoming':[dict(r) for r in c.execute('SELECT * FROM entity_relations WHERE object_uid=? ORDER BY id',(uid,))],
        'typed_outgoing':[dict(r) for r in c.execute('SELECT * FROM entity_relations WHERE subject_uid=? ORDER BY id',(uid,))],
        'identity_bridges':[dict(r) for r in c.execute('SELECT * FROM bridges WHERE left_uid=? OR right_uid=? ORDER BY id',(uid,uid))],
    }


def validate_serial_instance(c, op, manifest, instance_review, operations):
    proof=op['proof'];uid=op['uid']
    record=proof['source_instance_review_record']
    actual_record=next((r for r in (instance_review or {}).get('records',[]) if r['uid']==uid),None)
    if actual_record!=record or record.get('approved_new_role')!='INSTANCE' or record.get('source_grain_disposition')!='OWN_SERIAL_AND_OPERATIONAL_DESIGNATION_SUPPORT_INSTANCE':
        raise ValueError('Named individual requires its independent whole own scope approval')
    if proof['source_instance_review_locator']!={'file':manifest.get('source_instance_review_file'),'sha256':manifest.get('source_instance_review_sha256'),'uid':uid}:
        raise ValueError('Physical instance review is not the exact frozen SOURCE input')
    source_record=record['complete_source_record'];n=node(c,uid)
    raw=dict(c.execute('SELECT * FROM nodes WHERE uid=?',(uid,)).fetchone())
    if raw!=source_record['before_node'] or sha(n['data'])!=proof['native_record_sha256']:
        raise ValueError('Serial physical source has changed')
    fields=source_record['all_own_fields']
    for w in fields:validate_witness(c,w)
    # A serial alone or one prototype is not enough: the complete own predicate
    # identifies a built ordinal vehicle plus its distinct operational name.
    own=' '.join(w['statement'] for w in fields)
    if not re.search(r'\b\d+(?:st|nd|rd|th)\s+airship\s+built\b',own,re.I) or not re.search(r'\b(?:tactical|military)\s+(?:designation|number)|\bserved\b.+\bas\s+L\d+',own,re.I):
        raise ValueError('An ordinal design name cannot establish physical instance grain')
    inventory=scope_inventory(c,uid)
    if any(r['status']=='ACTIVE' for r in inventory['identity_bridges']):
        raise ValueError('Instance migration cannot infer scope from an active identity peer')
    if op['op']=='correct_role':
        if proof.get('before_scope_declarations')!=inventory or proof['source_witnesses']!=fields:
            raise ValueError('Individual role must preserve its whole previous scope inventory')
        retirement={o['before_assertion']['id']:o for o in operations if o['op']=='review_typed_relation'}
        for row in inventory['typed_outgoing']:
            if row['status']=='ACTIVE' and row['relation']!='INSTANCE_OF':
                if row['id']not in retirement or retirement[row['id']]['before_assertion']!=row:
                    raise ValueError('Role migration would abandon an active physical declaration')
        if any(r['status']in ('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE') for r in inventory['edges_outgoing']):
            raise ValueError('Individual migration needs explicit review of active class edges')
    return record


def validate_additional_grain(c, op, manifest, reviews, operations):
    p=op['proof'];uid=op['uid'];locator=p['source_additional_role_review_locator']
    slots={manifest.get('source_additional_grain_review_file'):manifest.get('source_additional_grain_review_sha256'),manifest.get('source_uncertain_individual_review_file'):manifest.get('source_uncertain_individual_review_sha256')}
    report=(reviews or {}).get(locator['file']);record=p['source_additional_role_review_record']
    if not report or slots.get(locator['file'])!=locator['sha256']or locator['uid']!=uid or next((r for r in report.get('records',[])if r['uid']==uid),None)!=record:
        raise ValueError('Additional grain requires its exact independent complete source review')
    original=record.get('complete_source_record')or record.get('complete_source_census_record')
    raw=dict(c.execute('SELECT *FROM nodes WHERE uid=?',(uid,)).fetchone())
    before=original.get('before_node')or original['complete_before_node']
    if {k:before.get(k)for k in raw}!=raw or sha(raw['data'])!=p['native_record_sha256']:
        raise ValueError('Additional object grain cannot borrow another source object')
    fields=original.get('all_own_fields')or original['all_retained_own_contexts']
    for w in fields:validate_witness(c,w)
    own=' '.join(w['statement']for w in fields)
    approved=record.get('approved_new_role')
    if approved is None:
        if record.get('source_grain_disposition')!='OWN_UNNAMED_PHYSICAL_OBJECT_VS_UNIQUE_DESIGN_GRAIN_AMBIGUOUS'or not re.search(r'otherwise unnamed',own,re.I):
            raise ValueError('Unknown role must describe the specific unresolved source grain')
        approved='UNKNOWN'
    elif approved=='MODEL':
        if record.get('source_role_scope_kind')!='OWNED_REUSABLE_MANUFACTURER_KIT_AIRCRAFT_DESIGN'or not all(re.search(x,own,re.I)for x in(r'\bdesigned\b',r'\bmarketed\b',r'\b(?:plans|kit)\b')):
            raise ValueError('Reusable kit-design grain requires its own producer/programme assertion')
    elif approved=='INSTANCE':
        if record.get('source_role_scope_kind')!='OWNED_NAMED_OPERATIONAL_AIRCRAFT_WITH_SPECIFIC_CONFIGURATION_AND_COST'or not all(re.search(x,own,re.I)for x in(r'\baircraft\b',r'\boperated by\b',r'\bseating capacity\b',r'\bit cost\b',r"the jet.s name")):
            raise ValueError('Named physical instance requires complete operational object scope')
    else:raise ValueError('Unapproved additional source-grain decision')
    inventory=scope_inventory(c,uid)
    if any(r['status']=='ACTIVE'for r in inventory['identity_bridges']):raise ValueError('Additional grain cannot silently migrate an identity component')
    if op['op']=='correct_role':
        if approved!=op['after_profile']['node_kind']or p['source_witnesses']!=[{k:v for k,v in w.items()if k!='bound_source_names'}for w in fields] or p['before_scope_declarations']!=inventory:
            raise ValueError('Additional role migration changed original complete source declarations')
        wanted='REVIEW'if approved=='UNKNOWN'else'VERIFIED'
        if p.get('role_status')!=wanted or p.get('allowed_views')!=([]if approved=='UNKNOWN'else['taxonomy','membership']):raise ValueError('Uncertain grain cannot activate hierarchy or claim verified certainty')
        for table,key,operation in [('edges','edges_outgoing','review_class_edge'),('entity_relations','typed_outgoing','review_typed_relation')]:
            for r in inventory[key]:
                if r['status']in('ACTIVE','BACKBONE_ACTIVE','TYPED_ACTIVE')and not any(o['op']==operation and o['before_assertion']==r for o in operations):raise ValueError('Additional role must reconcile every existing active classification')
    return record


def validate_complete_owned_type_repairs(c, manifest, operations, source_review, role_review=None, compound_senses=(), instance_review=None, additional_reviews=None):
    if manifest.get('schema') != 'FINEATLAS_COMPLETE_OWNED_TYPE_REPAIRS_V1' or not operations:
        raise ValueError('Unknown or empty complete owned scope repair')
    if type(manifest.get('operation_count')) is not int or manifest['operation_count'] != len(operations):
        raise ValueError('Complete owned scope count is not bound')
    raw_keys = [(o['uid'], o['parent'], o['relation']) for o in operations]
    if len(set(raw_keys)) != len(raw_keys):
        raise ValueError('Duplicate complete owned scope assertion')
    if source_review.get('accepted_source_scope_only') is not True or source_review.get('operations_sha256') != manifest['operations_sha256'] or sorted(map(tuple, source_review.get('approved_keys', []))) != sorted(raw_keys):
        raise ValueError('Every exact source assertion requires independent full-range approval')
    bound = manifest.get('completed_parent_binding') or {}
    meta = {r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM metadata')}
    if meta.get('database_revision') != bound.get('database_revision') or not bound.get('frozen_manifest_sha256') or parent_manifest_sha256(meta.get('structure_frozen_build_manifest')) != bound['frozen_manifest_sha256']:
        raise ValueError('This delta does not bind the actual completed checkpoint')
    role_overrides = {o['uid']:o['after_profile']['node_kind'] for o in operations if o.get('op')=='correct_role'}
    role_records={r['uid']:r for r in (role_review or {}).get('records',[])}
    for o in operations:
        p = o['proof']
        if o['source'] != SOURCE or not o.get('uri', '').startswith('https://'):
            raise ValueError('Only attributed approved physical links are supported')
        if o.get('op')=='retain_source_scope_reference':
            validate_additional_grain(c,o,manifest,additional_reviews,operations)
            before=p['original_assertion'];table=p['original_assertion_table']
            if table not in('edges','entity_relations')or p.get('navigation_allowed')is not False or p.get('allowed_views')!=[]or p.get('is_class_inclusion')is not False or o['relation']not in('SOURCE_NATIVE_CLASSIFICATION_REFERENCE','SOURCE_PHYSICAL_CLASS_REFERENCE'):
                raise ValueError('Retained source reference cannot grant hierarchy or identity')
            actual=c.execute('SELECT *FROM '+table+' WHERE id=?',(before['id'],)).fetchone()
            if not actual or dict(actual)!=before or source_assertion_sha256(actual)!=p['original_assertion_content_sha256']or not any(x.get('before_assertion')==before and x['op']in('review_typed_relation','review_class_edge')for x in operations):raise ValueError('Non-navigation source reference must preserve its exact reviewed original')
            continue
        if o.get('op')in('review_typed_relation','review_class_edge'):
            before=o['before_assertion'];table='edges'if o['op']=='review_class_edge'else'entity_relations';actual=c.execute('SELECT * FROM '+table+' WHERE id=?',(before['id'],)).fetchone()
            if not actual or dict(actual)!=before or before['status']!='ACTIVE' or before['child_uid'if table=='edges'else'subject_uid']!=o['uid'] or before['parent_uid'if table=='edges'else'object_uid']!=o['parent'] or before['relation']!=o['relation'] or o.get('after_status')!='SOURCE_SCOPE_REVIEW' or source_assertion_sha256(actual)!=o['content_sha256']:
                raise ValueError('Physical encoding migration changed an original declaration')
            if p.get('kind')=='SOURCE_OWNED_GRAIN_INCOMPATIBLE_CLASSIFICATION_REVIEW':
                validate_additional_grain(c,o,manifest,additional_reviews,operations)
                if p.get('original_source_fact_retained')is not True or not any(x['op']=='retain_source_scope_reference'and x['proof']['original_assertion']==before for x in operations):raise ValueError('Role encoding review must retain its original source fact')
                continue
            validate_serial_instance(c,o,manifest,instance_review,operations)
            if p.get('kind')!='INSTANCE_SCOPE_TYPED_ENCODING_MIGRATION' or before['relation']!='DESIGN_TYPE_OF' or role_overrides.get(o['uid'])!='INSTANCE' or p.get('original_physical_fact_retained')is not True or not any(x['op']=='link'and x['uid']==o['uid']and x['relation']=='INSTANCE_OF'and x['parent']==p.get('replacement_parent')for x in operations):
                raise ValueError('Old physical classification must migrate to a grounded instance relation')
            continue
        if o.get('op')=='correct_role':
            is_instance=p.get('kind')=='INSTANCE_SCOPE_ROLE_MIGRATION';is_additional=p.get('kind')=='SOURCE_OWNED_ADDITIONAL_GRAIN_MIGRATION_V1';is_reviewed_migration=is_instance or is_additional
            n=node(c,o['uid']);record=validate_additional_grain(c,o,manifest,additional_reviews,operations)if is_additional else validate_serial_instance(c,o,manifest,instance_review,operations)if is_instance else p['source_role_review_record']
            locator=p.get('source_role_review_locator')
            if not is_reviewed_migration and role_records.get(o['uid'])!=record or (not is_reviewed_migration and locator!={'file':manifest.get('source_role_review_file'),'sha256':manifest.get('source_role_review_sha256'),'uid':o['uid']}):
                raise ValueError('Source role lacks its actual frozen independent review')
            if not n or n['visibility']!='ACTIVE' or o['uid']!=o['parent'] or o['relation']!='ROLE_ADJUDICATION' or o['after_profile']['node_kind'] not in {'CLASS','MODEL','MODEL_FAMILY','INSTANCE','UNKNOWN'}:
                raise ValueError('Source grain correction is not an admitted object role')
            if (record['uid']!=o['uid'] or ((record.get('approved_new_role')or'UNKNOWN') if is_reviewed_migration else record['approved_role'])!=o['after_profile']['node_kind'] or (p['source_model_role_before'] if is_reviewed_migration else record['current_role'])!=n['role'] or (not is_reviewed_migration and record['source_data_sha256']!=sha(n['data'])) or p.get('world_identity_assertion')is not False or p.get('no_identity_merges')is not True):
                raise ValueError('Source grain cannot be inferred from another identity or role')
            for w in p['source_witnesses']:validate_witness(c,w)
            approved_fields=p['source_witnesses']if is_reviewed_migration else [{**w,'field':w.get('field',w['field_path'].split('.')[-1]),'data_sha256':w.get('data_sha256',record['source_data_sha256'])}for w in record['full_own_source_fields']]
            if p['source_witnesses']!=approved_fields or (p['complete_before_node']if is_reviewed_migration else record['complete_source_node'])!=dict(c.execute('SELECT * FROM nodes WHERE uid=?',(o['uid'],)).fetchone()):
                raise ValueError('Role lacks its independently reviewed complete own definition')
            for table,field in [('node_profiles','before_profile'),('normalization_roles','before_normalization_role')]:
                actual=c.execute('SELECT * FROM '+table+' WHERE uid=?',(o['uid'],)).fetchone()
                if (dict(actual) if actual else None)!=o[field]:raise ValueError('Original source role declaration changed')
            if not is_reviewed_migration and (c.execute("SELECT 1 FROM bridges WHERE (left_uid=? OR right_uid=?) AND status='ACTIVE'",(o['uid'],o['uid'])).fetchone() or c.execute("SELECT 1 FROM edges WHERE child_uid=? AND status IN ('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE')",(o['uid'],)).fetchone() or c.execute("SELECT 1 FROM entity_relations WHERE subject_uid=? AND status='ACTIVE'",(o['uid'],)).fetchone()):
                raise ValueError('Role with active identity or hierarchy needs a separate migration contract')
            attrs=json.loads(o['before_profile']['attributes'])if o['before_profile']else{}
            eid='usability:'+sha(dump(p));attrs.update(source_role=p['source_role'],native_rank=n['rank'],role_status='REVIEW'if o['after_profile']['node_kind']=='UNKNOWN'else'VERIFIED',role_evidence_id=eid)
            if p.get('allowed_views')is not None:attrs['allowed_views']=p['allowed_views']
            attrs.pop('canonical_scope_guard',None);attrs.pop('canonical_scope_evidence_id',None)
            if o['after_profile']['node_kind']=='CLASS':
                if p.get('basis')!='REVIEWED_GENERIC_WHOLE_SUBJECT_REPLACES_ADAPTER_DESIGN_ROLE' or p.get('individual_semantic_review')is not True or not p.get('source_statement')or not p.get('subject_kind_head'):
                    raise ValueError('A reusable physical class requires an explicit generic range guard')
                attrs.update(canonical_scope_guard='GENERIC_PHYSICAL_KIND',canonical_scope_evidence_id=eid)
            after={**(o['before_profile']or{'uid':n['uid'],'domain':n['domain']}),'node_kind':o['after_profile']['node_kind'],'source_uri':o['uri'],'evidence_id':eid,'attributes':dump(attrs)}
            norm={**(o['before_normalization_role']or{'uid':n['uid'],'source_role':p['source_role'],'status':'VERIFIED','prior_profile':dump(o['before_profile']or{})}),'canonical_role':o['after_profile']['node_kind'],'evidence_id':eid,'source':SOURCE}
            if o['after_profile']['node_kind']=='UNKNOWN':norm['status']='REVIEW'
            if after!=o['after_profile']or norm!=o['after_normalization_role']:raise ValueError('Role correction changed unrelated source fields')
            continue
        if o.get('op') != 'link' or o['relation'] not in {'DESIGN_TYPE_OF','IS_A','INSTANCE_OF'}:
            raise ValueError('Unknown complete owned type operation')
        if p.get('world_identity_assertion') is not False or p.get('no_identity_merges') is not True or p.get('whole_subject_scope_review') is not True or p.get('classification_axis') != 'physical_structure':
            raise ValueError('Physical scope cannot promote identity, mapping or another axis')
        child, parent = node(c, o['uid']), node(c, o['parent'])
        if not child or not parent or child['visibility'] != 'ACTIVE' or parent['visibility'] != 'ACTIVE' or parent['role'] != 'CLASS':
            raise ValueError('Physical source endpoints must already be admitted')
        if sha(child['data']) != p['native_record_sha256'] or sha(parent['data']) != p['parent_native_record_sha256']:
            raise ValueError('Complete endpoint range changed')
        current_role=role_overrides.get(o['uid'],child['role'])
        validate_link_roles(o['relation'], current_role, parent['role'])
        if current_role != p['source_model_role']:
            raise ValueError('Source role changed since its complete-scope review')
        witnesses = p.get('source_witnesses', [])
        if not witnesses or witnesses[0]['uid'] != o['uid'] or not any(w['uid'] == o['parent'] for w in witnesses):
            raise ValueError('Whole own object and whole parent sense require source witnesses')
        for w in witnesses + p.get('source_full_contexts', []):
            validate_witness(c, w)
        own = witnesses[0]
        instance_link=o['relation']=='INSTANCE_OF'
        if instance_link:
            if p.get('kind')=='OWNED_NAMED_OPERATIONAL_AIRCRAFT_INSTANCE_CLASSIFICATION':
                validate_additional_grain(c,o,manifest,additional_reviews,operations)
                sense=p.get('aviation_compound_scope_review')
                if not sense or sense not in compound_senses or sense.get('compound')!='business jet':raise ValueError('Instance jet kind needs the complete independently bound businessjet sense')
                validate_witness(c,sense['definition_witness'])
                if not any(re.search(r'aircraft class powered by jet propulsion engines',w['statement'],re.I)for w in witnesses if w['uid']==o['parent']):raise ValueError('Instance jet kind cannot be narrowed to fixed-wing or plane')
            else:validate_serial_instance(c,o,manifest,instance_review,operations)
            if p.get('kind')=='OWNED_SERIAL_PHYSICAL_INSTANCE_CLASSIFICATION' and (current_role!='INSTANCE' or 'airship'not in parent['label'].casefold()):raise ValueError('Instance target must be its whole grounded physical class')
        expanded_pc=p.get('kind')=='OWNED_EXPANDED_PC_COMPLETE_SOURCE_SCOPE'
        if expanded_pc:
            rec=p['personal_computer_scope_review'];locator=p['personal_computer_scope_review_locator']
            if (additional_reviews or {}).get(locator['file'])!=rec or locator!={'file':manifest.get('source_personal_computer_review_file'),'sha256':manifest.get('source_personal_computer_review_sha256'),'uid':o['uid'],'parent':o['parent'],'relation':o['relation']} or rec.get('accepted_source_scope_only')is not True or rec.get('approved_keys')!=[[o['uid'],o['parent'],o['relation']]]:
                raise ValueError('Expanded PC requires the exact independent complete SOURCE approval')
            if rec['complete_child']!=dict(c.execute('SELECT *FROM nodes WHERE uid=?',(o['uid'],)).fetchone()) or rec['complete_parent']!=dict(c.execute('SELECT *FROM nodes WHERE uid=?',(o['parent'],)).fetchone()) or current_role!='MODEL_FAMILY':
                raise ValueError('Expanded PC cannot borrow another programme or change source grain')
            if witnesses!=[{**w,'field':w['field_path']}for w in rec['source_witnesses']] or not re.match(r'The .+Personal Computer in its various incarnations was a legacy-free PC\b',own['statement'],re.I) or not re.match(r'A personal computer \(PC\).*computer designed for personal use\.',witnesses[1]['statement'],re.I):
                raise ValueError('Whole expanded PC subject and intended personal-use sense are required')
        parsed = None if instance_link or expanded_pc else complete_owned_physical_genus(own['statement'], child['label'], own.get('bound_source_names', []),compound_senses)
        if not instance_link and not expanded_pc and (parsed != p['selected_physical_predicate'] or parsed['parent'] != o['parent']):
            raise ValueError('Selected physical kind is not the owned first assertion')
        if parsed and parsed['predicate_kind']=='OWNED_COMPOUND_WITH_INDEPENDENT_GENERIC_AVIATION_SENSE':
            sense=next((s for s in compound_senses if s['uid']==parsed['compound_source_uid']and s['compound']==parsed['aviation_compound']),None)
            if not sense or p.get('aviation_compound_scope_review')!=sense:
                raise ValueError('Physical compound has no precise independent source sense binding')
            actual=c.execute('SELECT * FROM nodes WHERE uid=?',(sense['uid'],)).fetchone()
            if not actual or dict(actual)!=sense['complete_before_node']:
                raise ValueError('Complete generic aviation sense source changed')
            validate_witness(c,sense['definition_witness'])
            if sense.get('fixed_wing_scope_witness'):validate_witness(c,sense['fixed_wing_scope_witness'])
        if current_role == 'CLASS' and json.loads(child['data']).get('node_type') != 'WORDNET_SYNSET':
            generic=p.get('generic_class_scope_witness',own)
            validate_witness(c,generic)
            if generic['uid']!=o['uid'] or not owned_generic_class_scope(generic['statement'],child['label'],generic.get('bound_source_names',[])):
                raise ValueError('Default import rank is not a universal class proof')
        reviewed = manifest['parent_components'][o['parent']]
        for table, field in [('node_profiles','before_profile'),('normalization_roles','before_normalization_role')]:
            actual = c.execute('SELECT * FROM '+table+' WHERE uid=?', (o['parent'],)).fetchone()
            if (dict(actual) if actual else None) != reviewed[field]:
                raise ValueError('Parent canonical role or admission declaration changed')
        actual_nodes = [dict(r) for r in c.execute('SELECT * FROM nodes WHERE component_id=? ORDER BY uid', (parent['component_id'],))]
        if actual_nodes != reviewed['component_nodes']:
            raise ValueError('Parent whole source identity component changed')
        for field, table, clause in [('component_bridges','bridges','left_uid IN (SELECT uid FROM nodes WHERE component_id=?) OR right_uid IN (SELECT uid FROM nodes WHERE component_id=?)'),('parent_edges','edges','child_uid=?'),('parent_typed','entity_relations','subject_uid=?')]:
            params = (parent['component_id'],parent['component_id']) if table == 'bridges' else (o['parent'],)
            if [dict(r) for r in c.execute('SELECT * FROM '+table+' WHERE '+clause+' ORDER BY id', params)] != reviewed[field]:
                raise ValueError('Parent scope history or admitted outgoing relations changed')
        for prior in p.get('prior_assertions', []):
            table = prior['table']
            if table not in ('entity_relations', 'edges'):
                raise ValueError('Unknown prior declaration table')
            row = c.execute('SELECT * FROM '+table+' WHERE id=?', (prior['id'],)).fetchone()
            if not row or source_assertion_sha256(row) != prior['content_sha256'] or row['status'] != prior['status']:
                raise ValueError('Previous source declaration or disposition changed')
        table = 'edges' if o['relation'] == 'IS_A' else 'entity_relations'
        clause = 'child_uid=? AND parent_uid=?' if table == 'edges' else 'subject_uid=? AND object_uid=?'
        if c.execute('SELECT 1 FROM '+table+' WHERE '+clause+' AND relation=? AND source=?', (o['uid'],o['parent'],o['relation'],SOURCE)).fetchone():
            raise ValueError('Complete owned type stage was already applied')
    validate_batch_cycles(c, operations, {})


def apply_reviewed_role(m, o):
    """Apply an exact source role; UNKNOWN remains explicitly under review."""
    m.role(o['uid'],o['after_profile']['node_kind'],o['proof'],SOURCE,o['uri'])
    if o['after_profile']['node_kind']=='UNKNOWN':
        m.c.execute('UPDATE node_profiles SET attributes=?WHERE uid=?',(o['after_profile']['attributes'],o['uid']))
        m.c.execute("UPDATE normalization_roles SET status='REVIEW'WHERE uid=?",(o['uid'],))
    actual={t:dict(m.c.execute('SELECT *FROM '+table+' WHERE uid=?',(o['uid'],)).fetchone())for t,table in [('profile','node_profiles'),('normalization_role','normalization_roles')]}
    if actual!={'profile':o['after_profile'],'normalization_role':o['after_normalization_role']}:
        raise ValueError('Applied role differs from frozen complete own-source grain')
    old={'profile':o['before_profile'],'normalization_role':o['before_normalization_role']}
    m.change(METADATA_KEY,'role_source_adjudication',o['uid'],old,actual,o['proof'])
    return {'uid':o['uid'],'before_sha256':sha(dump(old)),'after_sha256':sha(dump(actual))}

def apply_complete_owned_type_repairs(m):
    path = m.inputs / INPUT_NAME
    if not path.exists():
        return {'status': 'not_requested'}
    manifest = json.loads(path.read_text())
    if manifest['operations_file'] != OPERATION_NAME:
        raise ValueError('Unexpected complete owned scope operations input')
    raw = safe_input(m.inputs, OPERATION_NAME).read_bytes()
    operations = [json.loads(line) for line in raw.decode().splitlines() if line]
    review_raw = safe_input(m.inputs, manifest['source_review_file']).read_bytes()
    if sha(raw) != manifest['operations_sha256'] or sha(review_raw) != manifest['source_review_sha256']:
        raise ValueError('Frozen source operations or independent approval bytes changed')
    role_review=None
    if any(o.get('op')=='correct_role'for o in operations):
        role_raw=safe_input(m.inputs,manifest['source_role_review_file']).read_bytes()
        if sha(role_raw)!=manifest['source_role_review_sha256']:raise ValueError('Independent complete source grain review changed')
        role_review=json.loads(role_raw)
    additional_reviews={}
    for prefix in('source_additional_grain_review','source_uncertain_individual_review','source_personal_computer_review'):
        if manifest.get(prefix+'_file'):
            additional_raw=safe_input(m.inputs,manifest[prefix+'_file']).read_bytes()
            if sha(additional_raw)!=manifest[prefix+'_sha256']:raise ValueError('Additional grain source review bytes changed')
            additional_reviews[manifest[prefix+'_file']]=json.loads(additional_raw)
    instance_review=None
    if manifest.get('source_instance_review_file'):
        instance_raw=safe_input(m.inputs,manifest['source_instance_review_file']).read_bytes()
        if sha(instance_raw)!=manifest['source_instance_review_sha256']:raise ValueError('Independent physical instance SOURCE bytes changed')
        instance_review=json.loads(instance_raw)
    compound_senses=[]
    if manifest.get('compound_senses_file'):
        compound_raw=safe_input(m.inputs,manifest['compound_senses_file']).read_bytes()
        if sha(compound_raw)!=manifest['compound_senses_sha256']:raise ValueError('Complete independent compound aviation definitions changed')
        compound_senses=json.loads(compound_raw)['senses']
    validate_complete_owned_type_repairs(m.c, manifest, operations, json.loads(review_raw),role_review,compound_senses,instance_review,additional_reviews)
    protected_tables = ('nodes','node_profiles','normalization_roles','bridges','dataset_targets','dataset_mapping_checks')
    role_uids=sorted(o['uid']for o in operations if o['op']=='correct_role')
    # Stable ordered checksums include every source object and mapping rather
    # than only the benchmark vicinity. No mutable build output is consulted.
    def fingerprint(table):
        order = 'uid' if table in ('nodes','node_profiles','normalization_roles') else 'id' if table == 'bridges' else 'dataset,class_id'
        import hashlib
        digest = hashlib.sha256()
        where=' WHERE uid NOT IN ('+','.join('?'for _ in role_uids)+')' if role_uids and table in ('node_profiles','normalization_roles')else''
        for row in m.c.execute('SELECT * FROM '+table+where+' ORDER BY '+order,role_uids if where else ()):
            digest.update((dump(dict(row))+'\n').encode())
        return digest.hexdigest()
    protected_before = {t:fingerprint(t) for t in protected_tables}
    role_diffs=[]
    for o in operations:
        if o['op']!='correct_role':continue
        role_diffs.append(apply_reviewed_role(m,o))
    for o in operations:
        if o['op']not in('review_typed_relation','review_class_edge'):continue
        before=o['before_assertion'];table='edges'if o['op']=='review_class_edge'else'entity_relations'
        m.c.execute("UPDATE "+table+" SET status='SOURCE_SCOPE_REVIEW'WHERE id=?",(before['id'],))
        m.change(METADATA_KEY,'class_scope_review'if table=='edges'else'typed_scope_review',str(before['id']),before,{'status':'SOURCE_SCOPE_REVIEW'},o['proof'])
    canonical_links = set()
    for o in operations:
        if o['op']!='link':continue
        p = o['proof']
        a, b = node(m.c, o['uid']), node(m.c, o['parent'])
        canonical_links.add((a['component_id'], b['component_id'], o['relation']))
        if o['relation'] == 'IS_A':
            eid = m.evidence(SOURCE,o['uri'],p,'HIERARCHY_REFINEMENT')
            m.c.execute('INSERT INTO edges(child_uid,parent_uid,relation,original_relation,facet_family,classification_basis,navigation_role,source,source_relation,confidence,provenance,data,layer,status,reason) VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)', (o['uid'],o['parent'],'IS_A','IS_A','NATIVE_OBJECT_KIND',p['kind'],'SOURCE_VALIDATED',SOURCE,'COMPLETE_OWNED_PHYSICAL_PREDICATE',dump({'evidence_ids':[eid]}),dump({'eligible_for_final_dag':True,'admission_basis':p,'classification_axis':'physical_structure'}),'v1.8-hierarchy-review','ACTIVE','Independent complete owned physical kind and parent scope review'))
        else:
            m.typed(o['uid'],o['parent'],o['relation'],p,SOURCE,o['uri'])
            row = m.c.execute('SELECT id,data FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',(o['uid'],o['parent'],o['relation'],SOURCE)).fetchone()
            data = json.loads(row['data']);data['classification_axis']='physical_structure'
            m.c.execute('UPDATE entity_relations SET data=? WHERE id=?',(dump(data),row['id']))
        m.change(METADATA_KEY,'complete_owned_type_append',o['uid'],{'prior_assertions':p['prior_assertions']},{'parent_uid':o['parent'],'relation':o['relation']},p)
    references=0
    for o in operations:
        if o['op']!='retain_source_scope_reference':continue
        m.typed(o['uid'],o['parent'],o['relation'],o['proof'],SOURCE,o['uri'])
        m.c.execute("UPDATE entity_relations SET status='SOURCE_DECLARED'WHERE subject_uid=?AND object_uid=?AND relation=?AND source=?",(o['uid'],o['parent'],o['relation'],SOURCE))
        row=m.c.execute('SELECT *FROM entity_relations WHERE subject_uid=?AND object_uid=?AND relation=?AND source=?',(o['uid'],o['parent'],o['relation'],SOURCE)).fetchone()
        data=json.loads(row['data']);data.update(navigation_allowed=False,allowed_views=[],is_class_inclusion=False)
        m.c.execute('UPDATE entity_relations SET data=?WHERE id=?',(dump(data),row['id']))
        row=m.c.execute('SELECT *FROM entity_relations WHERE id=?',(row['id'],)).fetchone()
        m.change(METADATA_KEY,'complete_owned_source_scope_reference',o['uid'],o['proof']['original_assertion'],dict(row),o['proof']);references+=1
    if any(fingerprint(t) != protected_before[t] for t in protected_tables):
        raise ValueError('Complete owned physical types changed source roles, identities or mappings')
    counts = dict(Counter(o['relation'] for o in operations))
    links=sum(o['op']=='link'for o in operations)
    m.c.execute('INSERT INTO source_catalogs VALUES(?,?,?,?,?)',('Hierarchy refinement: '+SOURCE,operations[0]['uri'],'Derived factual source-scope assertions; original source records, attribution and licenses retained',sha(raw),dump({'source_operations':len(operations),'source_assertions_added':links,'physical_kind_and_explicit_grain_review_only':True,'source_review_sha256':manifest['source_review_sha256']})))
    m.meta(METADATA_KEY, {'manifest_sha256':sha(path.read_bytes()),'operations_sha256':sha(raw),'operation_count':len(operations),'operations':counts,'source_assertions_added':links,'roles_corrected':len(role_diffs),'source_scope_references_added':references,'class_encodings_reviewed':sum(o['op']=='review_class_edge'for o in operations),'typed_encodings_reviewed':sum(o['op']=='review_typed_relation'for o in operations),'role_allowed_differences':role_diffs,'protected_table_hashes':protected_before,'distinct_canonical_directions_asserted':len(canonical_links),'new_nodes':0,'mapping_promotions':0,'positive_identity_merges':0,'source_declarations_preserved':True,'completed_parent_binding':manifest['completed_parent_binding']})
    m.c.commit()
    return {'status':'PASS','source_assertions_added':links,'roles_corrected':len(role_diffs),'typed_encodings_reviewed':sum(o['op']=='review_typed_relation'for o in operations),'distinct_canonical_directions_asserted':len(canonical_links),'new_nodes':0,'mapping_promotions':0,'positive_identity_merges':0}
