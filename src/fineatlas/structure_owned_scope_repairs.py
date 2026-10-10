"""Add grounded owned-scope links and preserve individually reviewed old claims.

This additive checkpoint never edits an imported UID, raw payload or old proof.
Directional physical scope, dataset design resolution and identity equivalence
are separate decisions. Changed identities are repartitioned from surviving
source bridges before the caller rebuilds all graph and browse indexes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import re

from .hierarchy import source_assertion_sha256, validate_link_roles
from .migration import dump
from .semantics import role_expression
from .structure_regression_repairs import sha
from .structure_owned_scope_rules import (
    owned_physical_genus,
    owned_reconfigurable_fixed_wing,
    owned_named_instance_genus,
    bound_owned_source_names,
    owned_motor_vehicle_design_scope,
    owned_role_scope,
    owned_self_twinjet_scope,
    owned_universal_variant_genus,
)

INPUT_NAME = 'structure_owned_scope_repairs.json'
OPERATION_NAME = 'hierarchy_owned_scope_repairs.jsonl'
METADATA_KEY = 'owned_scope_repairs'
SOURCE = 'Complete owned source scope adjudication'
LINKS = {'IS_A', 'DESIGN_TYPE_OF', 'NATIVE_DESIGN_PARENT', 'INSTANCE_OF', 'TAXONOMIC_PARENT'}
REVIEWS = {'review_bridge': 'bridges', 'review_typed_relation': 'entity_relations', 'review_class_edge': 'edges'}
MAPPINGS = {'migrate_nominal_design_mapping', 'review_dataset_mapping'}


def node(c, uid):
    return c.execute('SELECT n.*, '+role_expression('n', 'p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?', (uid,)).fetchone()


def owned_identity_peer(c, child, witness):
    """Source fields belong to the own object only through actual live identity."""
    if child == witness:return True
    role=node(c,child)['role'];todo=[child];seen=set()
    while todo:
        current=todo.pop()
        if current in seen:continue
        seen.add(current)
        for b in c.execute("SELECT left_uid,right_uid FROM bridges WHERE relation='SAME_CONCEPT' AND status='ACTIVE' AND (left_uid=? OR right_uid=?)",(current,current)):
            peer=b['right_uid'] if b['left_uid']==current else b['left_uid']
            n=node(c,peer)
            if not n or n['role'] != role:continue
            if peer==witness:return True
            todo.append(peer)
    return False


def qualified_seamount_scope(statement, label):
    """Own qualified genus; a mention of seamount in a relative clause fails."""
    first = re.split(r'[.;]\s+(?=[A-Z])', statement, maxsplit=1)[0]
    first = re.sub(r'^In [^,]+,\s*', '', first, flags=re.I)
    first = re.sub(r'\(\s*\)', '', first)
    first = re.sub(r',\s*also called [^,]+,', '', first, flags=re.I)
    match = re.fullmatch(r'(?:the |a |an )?(.+?)\s+(?:is|was)\s+(?:an? )?(?:isolated )?underwater (?:volcanic )?mountain\s*\(seamount\)(?:\s+with\b.*)?', first.strip(), re.I)
    words = lambda v: re.findall(r'[a-z0-9]+', v.casefold())
    return bool(match and words(match[1]) == words(label))


def _witness(c, w):
    table = w.get('table', 'nodes')
    if table not in {'nodes', 'edges', 'entity_relations', 'evidence'}:
        raise ValueError('Unexpected complete source witness table')
    column='payload'if table=='evidence'else'data'
    key='evidence_id'if table=='evidence'else'uid'if table=='nodes'else'id'
    r=c.execute('SELECT '+column+' FROM '+table+' WHERE '+key+'=?',(w[key],)).fetchone()
    if not r or sha(r[0]) != w['data_sha256']:
        raise ValueError('Complete source witness changed')
    d = json.loads(r[0])
    value = d
    for part in w['field'].split('.'):
        value = value.get(part) if isinstance(value, dict) else None
    if value is None and '.' not in w['field']:
        value = d.get('evidence_record', {}).get(w['field'])
    if value != w['statement']:
        raise ValueError('Witness is not the complete owned source field')
    if w.get('bound_source_names'):
        record = d.get('evidence_record', {})
        label = c.execute('SELECT label FROM nodes WHERE uid=?', (w['uid'],)).fetchone()[0]
        allowed = set(bound_owned_source_names(d, label, w['statement']))
        if record.get('wikipedia_redirect_chain') or not set(w['bound_source_names']) <= allowed:
            raise ValueError('Subject name is not a non-redirect source title')


def _assertion_witness(c, witness):
    """Bind a retained owned sentence to its full immutable source assertion."""
    table = witness['table']
    if table not in {'edges', 'entity_relations'}:
        raise ValueError('Only retained source assertions can supply a scope')
    before = witness['before']
    actual = c.execute('SELECT * FROM '+table+' WHERE id=?', (before['id'],)).fetchone()
    if not actual or dict(actual) != before or sha(dump(before)) != witness['before_fullrow_sha256']:
        raise ValueError('Retained own source assertion changed')
    value = json.loads(before['data'])
    for part in witness['field_path']:
        value = value[part]
    if value != witness['statement'] or not witness['original_source_uri'].startswith('https://'):
        raise ValueError('Retained sentence does not match its original field')


def motor_vehicle_class_scope(proof, own, parent, label):
    """Road motorized scope plus a retained own wheeled-vehicle definition.

    This permits three-wheeled source cars without equating them to a
    four-wheel WordNet car, or admitting a train into a road-vehicle class.
    """
    if parent['statement'] != 'a self-propelled wheeled vehicle that does not run on rails':
        return False
    road_sources = [own] + proof.get('retained_source_context_witnesses', [])
    if not any(re.search(r'\bmotorized road vehicle\b', w['statement'], re.I) for w in road_sources):
        return False
    witnesses = proof.get('source_assertion_witnesses', [])
    for w in witnesses:
        sentence = w['statement']
        m = re.fullmatch(r'(?:an? |the )?(.+?)\s+(?:is|was)\s+(?:an? )?motor vehicle with wheels\.?', sentence.strip(), re.I)
        if m and re.search(r'\b'+re.escape(label)+r'\b', m[1], re.I):
            return True
    return False


def expected_partitions(c, operations):
    """Compute logical partitions without writing the preflight database."""
    retired = {o['before_assertion']['id'] for o in operations if o['op'] == 'review_bridge'}
    affected = {node(c, o['uid'])['component_id'] for o in operations if o['op'] == 'review_bridge'}
    parts = {}
    for old in sorted(affected):
        members = sorted(r[0] for r in c.execute('SELECT uid FROM nodes WHERE component_id=?', (old,)))
        adjacent = {u: set() for u in members}
        for u in members:
            for b in c.execute("SELECT * FROM bridges WHERE status='ACTIVE' AND relation='SAME_CONCEPT' AND (left_uid=? OR right_uid=?)", (u, u)):
                if b['id'] not in retired and b['left_uid'] in adjacent and b['right_uid'] in adjacent:
                    adjacent[b['left_uid']].add(b['right_uid'])
                    adjacent[b['right_uid']].add(b['left_uid'])
        seen, groups = set(), []
        for u in members:
            if u in seen: continue
            todo, group = [u], []
            while todo:
                current = todo.pop()
                if current in seen: continue
                seen.add(current); group.append(current)
                todo.extend(adjacent[current] - seen)
            groups.append(sorted(group))
        parts[old] = groups
    return parts


def validate_batch_cycles(c, operations, partitions):
    canon = {}
    for old, groups in partitions.items():
        for i, group in enumerate(groups):
            for u in group: canon[u] = ('split', old, i)
    def component(uid): return canon.get(uid, ('existing', node(c, uid)['component_id']))
    proposed = defaultdict(set)
    endpoints = defaultdict(set)
    for o in operations:
        if o['op'] == 'link':
            a, b = component(o['uid']), component(o['parent'])
            if a == b: raise ValueError('Hierarchy cannot link equivalent source objects')
            proposed[a].add(b); endpoints[a].add(o['uid']); endpoints[b].add(o['parent'])
    typed_retired = {o['before_assertion']['id'] for o in operations if o['op'] == 'review_typed_relation'}
    class_retired = {o['before_assertion']['id'] for o in operations if o['op'] == 'review_class_edge'}
    cached = {}
    role_overrides = {o['uid']:o['after_profile']['node_kind']for o in operations if o['op']=='correct_role'}
    def parents(key):
        if key in cached: return cached[key]
        if key[0] == 'split': peers = partitions[key[1]][key[2]]
        else: peers = [r[0] for r in c.execute('SELECT uid FROM nodes WHERE component_id=?', (key[1],))]
        result = set(proposed.get(key, ()))
        for u in peers:
            n = node(c, u)
            if n['visibility'] != 'ACTIVE': continue
            for r in c.execute("SELECT * FROM entity_relations WHERE subject_uid=? AND status='ACTIVE' AND relation IN ('NATIVE_DESIGN_PARENT','DESIGN_TYPE_OF','SERIES_MEMBER_OF','CONFIGURATION_OF','CONFIGURATION_TYPE_OF','TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT','INSTANCE_OF')", (u,)):
                if r['id'] in typed_retired: continue
                p = node(c, r['object_uid'])
                if not p or p['visibility'] != 'ACTIVE': continue
                try: validate_link_roles(r['relation'], role_overrides.get(n['uid'],n['role']), role_overrides.get(p['uid'],p['role']))
                except ValueError: continue
                target = component(p['uid'])
                if target != key: result.add(target)
            if role_overrides.get(n['uid'],n['role']) == 'CLASS':
                for r in c.execute("SELECT id,parent_uid FROM edges WHERE child_uid=? AND status IN ('ACTIVE','BACKBONE_ACTIVE') AND relation='IS_A'", (u,)):
                    if r['id'] in class_retired:continue
                    p = node(c, r['parent_uid'])
                    if p and p['visibility'] == 'ACTIVE' and role_overrides.get(p['uid'],p['role']) == 'CLASS' and component(p['uid']) != key: result.add(component(p['uid']))
        cached[key] = result
        return result
    for child, ps in proposed.items():
        for parent in ps:
            stack, visited = [parent], set()
            while stack:
                current = stack.pop()
                if current == child: raise ValueError('Proposed batch closes a canonical component cycle')
                if current not in visited:
                    visited.add(current); stack.extend(parents(current))


def validate_owned_scope_repairs(c, manifest, operations):
    if manifest.get('schema') != 'FINEATLAS_OWNED_SCOPE_REPAIRS_V1' or type(manifest.get('operation_count')) is not int or manifest['operation_count'] != len(operations) or not operations:
        raise ValueError('Owned scope input schema/count is invalid')
    seen = set()
    role_overrides = {o['uid']:o['after_profile']['node_kind'] for o in operations if o['op']=='correct_role'}
    for o in operations:
        key = (o['op'], o.get('dataset'), o.get('class_id'), o['uid'], o['parent'], o['relation'], o.get('content_sha256'))
        if key in seen or o.get('source') != SOURCE or not o.get('uri', '').startswith('https://'):
            raise ValueError('Scope operations must be unique and attributed')
        seen.add(key)
        p = o['proof']
        if not p.get('scope_observation') or not p.get('license'):
            raise ValueError('Every scope decision needs a reason and source terms')
        for w in p.get('source_witnesses', []) + p.get('retained_source_context_witnesses', []): _witness(c, w)
        for witness in p.get('source_assertion_witnesses', []): _assertion_witness(c, witness)
        if p.get('supporting_class_definition'):_witness(c,p['supporting_class_definition'])
        for u, before in p.get('source_nodes', {}).items():
            actual = c.execute('SELECT * FROM nodes WHERE uid=?', (u,)).fetchone()
            if not actual or dict(actual) != before: raise ValueError('Reviewed source object changed')
        for u, before in p.get('counterexamples', {}).items():
            actual = c.execute('SELECT * FROM nodes WHERE uid=?', (u,)).fetchone()
            if not actual or dict(actual) != before: raise ValueError('Whole-range counterexample changed')
        for e in p.get('evidence_witnesses', []):
            actual = c.execute('SELECT * FROM evidence WHERE evidence_id=?', (e['evidence_id'],)).fetchone()
            if not actual or dict(actual) != e or sha(e['payload']) != e['payload_sha256']: raise ValueError('Original producer evidence changed')
        if o['op'] == 'link':
            a, b = node(c, o['uid']), node(c, o['parent'])
            if not a or not b or a['visibility'] != 'ACTIVE' or b['visibility'] != 'ACTIVE' or sha(a['data']) != p['native_record_sha256'] or sha(b['data']) != p['parent_native_record_sha256']:
                raise ValueError('Owned physical endpoints changed')
            validate_link_roles(o['relation'], role_overrides.get(a['uid'], a['role']), role_overrides.get(b['uid'], b['role']))
            if o['relation'] not in LINKS or p.get('world_identity_assertion') is not False or p.get('no_identity_merges') is not True: raise ValueError('Directional genus cannot certify world identity')
            if not p.get('whole_subject_scope_review') or len(p.get('source_witnesses', [])) < 2: raise ValueError('Both own and parent scopes must be retained')
            own = p['source_witnesses'][0]
            if own.get('table','nodes')=='nodes' and not owned_identity_peer(c,a['uid'],own['uid']):raise ValueError('Different-source component cannot supply an owned field without active role-compatible identity')
            if o['relation'] == 'TAXONOMIC_PARENT':
                review=p['host_taxon_scope_review'];parent=p['source_witnesses'][1]
                if role_overrides.get(a['uid'],a['role'])!='BIOLOGICAL_VARIANT' or not review['source_host_not_fruit'] or not review['child_remains_biological_variant'] or review['species_identity_assertion']is not False:raise ValueError('Host lineage must preserve biological cultivar grain')
                parent_data=json.loads(b['data']);parent_description=parent_data.get('wikidata_description')or parent_data.get('description')or parent_data.get('evidence_record',{}).get('wikidata_description','')
                if review['parent_taxon_rank']!='species' or not re.search(r'\bspecies\b',parent_description,re.I):raise ValueError('Biological host must independently denote a living source taxon')
                if review['host_scientific_name']not in parent['statement'] or review['child_owned_host_phrase']not in own['statement'] or review['parent_owned_host_phrase']not in parent['statement']:raise ValueError('Scientific host and complete own definition do not close')
                if own.get('table')=='evidence':
                    payload=json.loads(c.execute('SELECT payload FROM evidence WHERE evidence_id=?',(own['evidence_id'],)).fetchone()[0])
                    if payload.get('child_uid')!=a['uid']:raise ValueError('Independent complete cultivar sentence belongs to another object')
                elif own.get('uid')!=a['uid']:raise ValueError('Biological host needs its own source object definition')
                for support in review.get('retained_primary_taxonomic_or_classifier_assertions',[]):
                    row=c.execute('SELECT * FROM edges WHERE id=?',(support['id'],)).fetchone()
                    if not row or dict(row)!=support:raise ValueError('Retained primary cultivar host declaration changed')
            elif o['relation'] == 'IS_A':
                parent = p['source_witnesses'][1]
                geographic = qualified_seamount_scope(own['statement'], a['label']) and parent['statement'] == 'an underwater mountain rising above the ocean floor'
                road_vehicle = motor_vehicle_class_scope(p, own, parent, a['label'])
                if not (geographic or road_vehicle): raise ValueError('Owned ordinary class and parent whole sense are not closed')
            else:
                kind = p.get('owned_physical_scope_kind')
                if kind == 'OWNED_UNIVERSAL_VARIANTS':
                    result = owned_universal_variant_genus(own['statement'], a['label'])
                elif kind == 'OWNED_SELF_TWINJET':
                    result = ('twinjet', 'wordnet31:04510794-n') if owned_self_twinjet_scope(own['statement'], a['label']) else None
                elif kind == 'OWNED_COMPLETE_RECONFIGURABLE_FIXED_WING':
                    result = ('fixed-wing aircraft', 'wikidata:Q2875704') if owned_reconfigurable_fixed_wing(own['statement'], a['label']) else None
                elif kind == 'OWNED_NAMED_INSTANCE_OF_STATED_DESIGN_KIND':
                    if o['relation'] != 'INSTANCE_OF':raise ValueError('Physical individual cannot be promoted to design genus')
                    result = owned_named_instance_genus(own['statement'], a['label'])
                elif kind == 'OWNED_MOTOR_VEHICLE_DESIGN':
                    parent = p['source_witnesses'][1]
                    complete_car = p.get('source_assertion_witnesses', [])
                    if parent['statement'] != 'a self-propelled wheeled vehicle that does not run on rails' or not complete_car or not re.search(r'\bis a motor vehicle with wheels\.?$',complete_car[0]['statement'],re.I):raise ValueError('Automotive design lacks independently grounded broad motor-vehicle sense')
                    result = ('motor vehicle','wordnet31:03796768-n') if owned_motor_vehicle_design_scope(own['statement'],a['label'],own.get('bound_source_names',())) else None
                elif kind == 'PRIMARY_MANUFACTURER_WHOLE_NOMINAL_MOTOR_VEHICLE':
                    scope=p['primary_manufacturer_scope'];doc=scope['document'];facts=scope['scope_facts']
                    if own.get('table')!='entity_relations':raise ValueError('Primary nominal object lacks its retained producer binding')
                    origin=c.execute('SELECT * FROM entity_relations WHERE id=?',(own['id'],)).fetchone();basis=json.loads(origin['data'])['admission_basis']
                    if origin['subject_uid']!=a['uid'] or basis['primary_label']!=a['label'] or scope['nominal_design_name']!=a['label'] or scope['title']!=a['label']+' model series':raise ValueError('Manufacturer document belongs to a different nominal source object')
                    if doc['source_kind']!='PRIMARY_MANUFACTURER_OR_REGULATOR' or not re.fullmatch(r'[0-9a-f]{64}',doc['sha256']) or not doc['source_uri'].startswith('https://') or not scope['primary_scope_covers_whole_named_design'] or scope['four_wheel_assertion']is not False or scope['category_same_concept_assertion']is not False or not facts['licensed_bubble_car_design'] or not facts['self_propulsion_combustion_engine']:raise ValueError('Primary complete manufacturer range is not independently defined')
                    if p['source_witnesses'][1]['statement']!='a self-propelled wheeled vehicle that does not run on rails':raise ValueError('Primary automotive scope does not prove a narrower parent sense')
                    result=('motor vehicle','wordnet31:03796768-n')
                else:
                    result = owned_physical_genus(re.sub(r'\b(wide|narrow)body\b', r'\1-body', own['statement'], flags=re.I), a['label'], own.get('bound_source_names', ()))
                if not result or result[1] != b['uid'] or b['uid'] == 'wordnet31:02961779-n': raise ValueError('Owned complete physical genus does not entail its selected source parent')
            for prior in p.get('prior_assertions', []):
                actual = c.execute('SELECT * FROM '+prior['table']+' WHERE id=?', (prior['before']['id'],)).fetchone()
                if not actual or dict(actual) != prior['before'] or source_assertion_sha256(actual) != prior['content_sha256']: raise ValueError('Existing source parent history changed')
        elif o['op'] in REVIEWS:
            before = o['before_assertion']; table = REVIEWS[o['op']]
            actual = c.execute('SELECT * FROM '+table+' WHERE id=?', (before['id'],)).fetchone()
            cols = ('left_uid','right_uid') if table == 'bridges' else ('child_uid','parent_uid') if table=='edges' else ('subject_uid','object_uid')
            if not actual or dict(actual) != before or source_assertion_sha256(actual) != o['content_sha256'] or (before[cols[0]], before[cols[1]], before['relation']) != (o['uid'],o['parent'],o['relation']) or before['status'] != 'ACTIVE' or o['after_status'] != 'SOURCE_SCOPE_REVIEW': raise ValueError('Review must bind exactly its original active assertion')
            if o['op'] == 'review_bridge' and o['relation'] != 'SAME_CONCEPT': raise ValueError('Identity scope review must retain a true identity declaration')
            if p['basis'] not in {'INCOMPATIBLE_WHOLE_SOURCE_AND_NARROW_WORDNET_SENSE','INSUFFICIENT_WHOLE_PARENT_RANGE_EVIDENCE','HISTORICAL_TAXON_VERSION_WHOLE_SCOPE_GAP','OWNED_WHOLE_PURPOSE_RANGE_INCOMPATIBLE_WITH_COMMERCIAL_TYPE','BIOLOGICAL_VARIANT_NOT_FRUIT_OR_ORDINARY_CLASS','INSUFFICIENT_NAMED_INDIVIDUAL_ROLE_SCOPE'}: raise ValueError('Unknown individually grounded scope review kind')
            if not p.get('source_native_objects_preserved'): raise ValueError('Review cannot delete source objects')
        elif o['op'] in MAPPINGS:
            key = (o['dataset'], o['class_id'])
            for table, field in [('dataset_targets','before_target'),('dataset_mapping_checks','before_check')]:
                actual = c.execute('SELECT * FROM '+table+' WHERE dataset=? AND class_id=?', key).fetchone()
                if (dict(actual) if actual else None) != o[field]: raise ValueError('Mapping no longer has its frozen original adjudication')
            if o['relation'] != 'DATASET_MODEL_DESIGN_MAPPING' or o['after_target']['dataset'] != o['dataset'] or o['after_target']['class_id'] != o['class_id'] or json.loads(o['after_check']['proof']) != p: raise ValueError('Mapping after state and full proof disagree')
            if o['op'] == 'migrate_nominal_design_mapping':
                target = node(c, o['uid']); native = node(c, o['parent']); review = p['nominal_design_scope_review']
                if not target or target['role'] not in {'MODEL', 'MODEL_FAMILY'} or target['visibility'] != 'ACTIVE' or sha(target['data']) != p['native_record_sha256'] or not native or sha(native['data']) != p['source_native_record_sha256']: raise ValueError('Nominal source design or author variant changed')
                if dict(c.execute('SELECT * FROM node_profiles WHERE uid=?',(o['uid'],)).fetchone()) != review['world_profile']: raise ValueError('Frozen design role/proof changed')
                if o['after_target']['target_uid'] != target['uid'] or o['after_target']['decision_status'] != 'VERIFIED' or o['after_check']['status'] != 'PRIMARY_SOURCE_CORROBORATED': raise ValueError('Positive nominal mapping must have exact corroborated final state')
                if p['task_grain'] != 'model_design' or p['category_same_concept_assertion'] is not False or p['world_identity_bridge_assertion'] is not False or p['customer_configuration_equivalence_assertion'] is not False: raise ValueError('Author model-design resolution cannot restore entity/sample equivalence')
                if review['approved_base_model_design_target_uid'] != target['uid'] or review['author_variant'] != o['before_target']['label'] or review['category_world_model_identity_assertion'] is not False or not review['primary_base_model_designation_evidence']: raise ValueError('Author intent and complete primary nominal design resolution do not close')
                if len(review['actual_author_annotations']) != 100 or {(r['family'],r['manufacturer']) for r in review['actual_author_annotations']} != {(review['author_family'],review['manufacturer'])}: raise ValueError('Frozen native cohort is ambiguous')
            elif o['after_target']['target_uid'] != o['before_target']['target_uid'] or o['after_target']['decision_status'] != 'REVIEW' or o['after_check']['status'] != 'ANNOTATION_SCOPE_REVIEW': raise ValueError('Scope review cannot silently invent a target')
        elif o['op'] == 'correct_role':
            a = node(c, o['uid'])
            for table, field in [('node_profiles','before_profile'),('normalization_roles','before_normalization_role')]:
                actual = c.execute('SELECT * FROM '+table+' WHERE uid=?',(o['uid'],)).fetchone()
                if (dict(actual) if actual else None) != o[field]:raise ValueError('Original canonical role adjudication changed')
            target_role=o['after_profile']['node_kind']
            if not a or a['visibility'] != 'ACTIVE' or o['uid'] != o['parent'] or o['relation'] != 'ROLE_ADJUDICATION' or target_role not in {'MODEL','MODEL_FAMILY','BIOLOGICAL_VARIANT','INSTANCE','UNKNOWN'} or o['after_normalization_role']['canonical_role'] != target_role:raise ValueError('Role correction is not a grounded source grain')
            if not p.get('source_native_objects_preserved') or len(p.get('source_witnesses',[])) != 1:raise ValueError('Source whole role statement must be preserved')
            role_w=p['source_witnesses'][0]
            if role_w['uid']!=a['uid']:
                ground=p.get('same_source_identifier_role_grounding')
                if not ground:raise ValueError('Role cannot be copied from a different source object')
                for field,uid in [('before_own_node',a['uid']),('before_independent_definition_node',role_w['uid'])]:
                    actual=c.execute('SELECT * FROM nodes WHERE uid=?',(uid,)).fetchone()
                    if not actual or dict(actual)!=ground[field]:raise ValueError('Same-source complete scope binding changed')
                own_data=json.loads(a['data']);definition_data=json.loads(ground['before_independent_definition_node']['data'])
                bridge=ground['before_identity_bridge'];actual=c.execute('SELECT * FROM bridges WHERE id=?',(bridge['id'],)).fetchone()
                if not actual or dict(actual)!=bridge or bridge['status']!='ACTIVE'or bridge['relation']!='SAME_CONCEPT' or not own_data.get('qid')or own_data['qid']!=definition_data.get('qid')or a['label']!=ground['before_independent_definition_node']['label']:raise ValueError('Independent producer definition lacks a complete same-source identifier scope binding')
            if owned_role_scope(role_w['statement'],a['label'])!=target_role:raise ValueError('Own complete source does not declare the selected role')
            before = o['before_profile']; norm = o['before_normalization_role']
            eid = 'usability:'+sha(dump(p)); attrs = json.loads(before['attributes']) if before else {}
            attrs.update(source_role=p.get('source_role', attrs.get('source_role','UNSPECIFIED')), native_rank=p.get('native_rank', attrs.get('native_rank',a['rank'])),role_status='VERIFIED',role_evidence_id=eid)
            attrs.pop('canonical_scope_guard',None);attrs.pop('canonical_scope_evidence_id',None)
            if target_role=='UNKNOWN':attrs.update(role_status='REVIEW',allowed_views=[])
            expected_profile = {**(before or {'uid':a['uid'],'domain':a['domain']}),'node_kind':target_role,'source_uri':o['uri'],'evidence_id':eid,'attributes':dump(attrs)}
            expected_norm = {**(norm or {'uid':a['uid'],'source_role':p.get('source_role')or a['rank']or'UNSPECIFIED','status':'VERIFIED','prior_profile':dump(before or {})}),'canonical_role':target_role,'evidence_id':eid,'source':SOURCE}
            if target_role=='UNKNOWN':expected_norm['status']='REVIEW'
            if o['after_profile'] != expected_profile or o['after_normalization_role'] != expected_norm:raise ValueError('Corrected role must preserve all unrelated original profile and source fields')
        else: raise ValueError('Unknown owned scope operation')
    partitions = expected_partitions(c, operations)
    validate_batch_cycles(c, operations, partitions)
    return partitions


def apply_owned_scope_repairs(m):
    path = m.inputs / INPUT_NAME
    if not path.exists(): return {'status':'not_requested'}
    manifest = json.loads(path.read_text())
    if manifest['operations_file'] != OPERATION_NAME: raise ValueError('Unexpected owned scope operations path')
    raw = (m.inputs / OPERATION_NAME).read_bytes()
    if sha(raw) != manifest['operations_sha256']: raise ValueError('Owned scope operation bytes changed')
    operations = [json.loads(line) for line in raw.decode().splitlines() if line]
    if m.c.execute('SELECT 1 FROM metadata WHERE key=?',(METADATA_KEY,)).fetchone(): raise ValueError('Owned scope checkpoint already applied; do not allocate identity partitions twice')
    partitions = validate_owned_scope_repairs(m.c, manifest, operations)
    node_count = m.c.execute('SELECT count(*) FROM nodes').fetchone()[0]
    counts = Counter()
    for o in operations:
        if o['op'] != 'correct_role':continue
        m.role(o['uid'],o['after_profile']['node_kind'],o['proof'],SOURCE,o['uri'])
        if o['after_profile']['node_kind']=='UNKNOWN':
            m.c.execute('UPDATE node_profiles SET attributes=? WHERE uid=?',(o['after_profile']['attributes'],o['uid']))
            m.c.execute("UPDATE normalization_roles SET status='REVIEW' WHERE uid=?",(o['uid'],))
        after = {'profile':dict(m.c.execute('SELECT * FROM node_profiles WHERE uid=?',(o['uid'],)).fetchone()),'normalization_role':dict(m.c.execute('SELECT * FROM normalization_roles WHERE uid=?',(o['uid'],)).fetchone())}
        if after != {'profile':o['after_profile'],'normalization_role':o['after_normalization_role']}:raise ValueError('Corrected actual role differs from its frozen source decision')
        m.change(METADATA_KEY,'role_scope_correction',o['uid'],{'profile':o['before_profile'],'normalization_role':o['before_normalization_role']},after,o['proof'])
        counts['roles_corrected'] += 1
    for o in operations:
        if o['op'] not in REVIEWS: continue
        before = o['before_assertion']; table = REVIEWS[o['op']]
        m.c.execute('UPDATE '+table+" SET status='SOURCE_SCOPE_REVIEW' WHERE id=?", (before['id'],))
        m.change(METADATA_KEY,'bridge_scope_review' if table=='bridges' else 'class_scope_review' if table=='edges' else 'typed_scope_review',before['id'],before,{'status':'SOURCE_SCOPE_REVIEW'},o['proof'])
        counts[o['op']] += 1
        if o.get('non_navigation_reference_relation'):
            source = SOURCE+': prior-bridge:'+o['content_sha256']; eid=m.evidence(source,o['uri'],o['proof'],o['non_navigation_reference_relation'])
            m.c.execute('INSERT INTO entity_relations(subject_uid,object_uid,relation,status,source,evidence_id,data) VALUES(?,?,?,?,?,?,?)',(o['uid'],o['parent'],o['non_navigation_reference_relation'],'SOURCE_DECLARED',source,eid,dump({'admission_basis':o['proof'],'allowed_views':[],'navigation_eligible':False})))
            counts['non_navigation_references'] += 1
    for old, groups in partitions.items():
        for i, group in enumerate(groups):
            if i == 0: continue
            new = m.c.execute('SELECT coalesce(max(id),0)+1 FROM components').fetchone()[0]
            m.c.execute('INSERT INTO components(id,depth,wordnet_reachable) VALUES (?,NULL,0)',(new,))
            m.c.executemany('UPDATE nodes SET component_id=? WHERE uid=?', ((new,u)for u in group))
        m.change(METADATA_KEY,'identity_component_repartition',old,{'component_id':old,'uids':sorted(u for g in groups for u in g)},{'partitions':groups},{'basis':'SURVIVING_ACTIVE_SOURCE_IDENTITY_CONNECTED_COMPONENTS','reviewed_bridge_content_sha256':[o['content_sha256']for o in operations if o['op']=='review_bridge' and o['uid']in {u for g in groups for u in g}]})
        counts['component_partitions_added'] += len(groups)-1
    for o in operations:
        p=o['proof']
        if o['op']=='link':
            if o['relation']=='IS_A':
                eid=m.evidence(SOURCE,o['uri'],p,'HIERARCHY_REFINEMENT')
                m.c.execute("INSERT INTO edges(child_uid,parent_uid,relation,original_relation,facet_family,classification_basis,navigation_role,source,source_relation,confidence,provenance,data,layer,status,reason) VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)",(o['uid'],o['parent'],'IS_A','IS_A','NATIVE_OBJECT_KIND',p['basis'],'SOURCE_VALIDATED',SOURCE,'EVIDENCED_SUBSUMPTION',dump({'evidence_ids':[eid]}),dump({'eligible_for_final_dag':True,'admission_basis':p,'classification_axis':'physical_structure'}),'v1.8-hierarchy-review','ACTIVE','Complete owned source and parent ranges independently reviewed'))
            else: m.typed(o['uid'],o['parent'],o['relation'],p,SOURCE,o['uri'])
            m.change(METADATA_KEY,'owned_scope_link',o['uid'],{'prior_assertions':p.get('prior_assertions',[])},{'parent_uid':o['parent'],'relation':o['relation']},p);counts['source_links_added'] += 1
        elif o['op'] in MAPPINGS:
            eid=m.evidence(SOURCE,o['uri'],p,'DATASET_NOMINAL_DESIGN_SCOPE')
            after=o['after_target']; check=o['after_check']
            if eid not in json.loads(after['evidence_ids']):
                raise ValueError('Current mapping must expose its newly grounded evidence')
            m.c.execute('INSERT OR REPLACE INTO dataset_targets VALUES(?,?,?,?,?,?,?,?,?)',tuple(after[k]for k in('dataset','class_id','label','target_uid','decision_status','identity_basis','granularity_basis','evidence_ids','provenance')))
            m.c.execute('INSERT OR REPLACE INTO dataset_mapping_checks VALUES(?,?,?,?,?)',tuple(check[k]for k in('dataset','class_id','status','reason','proof')))
            before={'target':o['before_target'],'check':o['before_check']}; complete={'target':after,'check':check}
            m.change(METADATA_KEY,'nominal_design_mapping',o['dataset']+':'+o['class_id'],before,complete,p)
            m.c.execute('INSERT INTO dataset_mapping_history VALUES(?,?,?,?,?,?,?,?,?)',(sha(dump(o)),o['dataset'],o['class_id'],'world','v1.11.0rc1',dump(before),dump(complete),eid,check['status']))
            counts[o['op']] += 1
    if node_count != m.c.execute('SELECT count(*) FROM nodes').fetchone()[0]: raise ValueError('Owned scope cannot create or delete source identities')
    m.c.execute('INSERT INTO source_catalogs VALUES(?,?,?,?,?)',('Hierarchy refinement: '+SOURCE,operations[0]['uri'],'Derived factual scope decisions; original source attribution and terms preserved',sha(raw),dump({'operations':dict(Counter(o['relation']for o in operations)),'decision_counts':dict(counts),'source_assertions_preserved':True})))
    m.meta(METADATA_KEY,{'manifest_sha256':sha(path.read_bytes()),'operations_sha256':sha(raw),'operation_count':len(operations),'operations':dict(Counter(o['relation']for o in operations)),'decision_counts':dict(counts),'new_nodes':0,'positive_identity_merges':0})
    m.c.commit()
    return {'status':'PASS',**dict(counts),'new_nodes':0,'positive_identity_merges':0}
