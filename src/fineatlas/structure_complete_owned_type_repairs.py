"""Append independently reviewed complete-owned physical types at a checkpoint.

No source object, identity bridge, role, dataset mapping or previous declaration
is overwritten. Parent classes must already be admitted; activation and new
nodes are deliberately outside this additive contract.
"""
from __future__ import annotations

from collections import Counter
import json
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
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


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


def validate_complete_owned_type_repairs(c, manifest, operations, source_review):
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
    if meta.get('database_revision') != bound.get('database_revision') or not bound.get('frozen_manifest_sha256') or sha(dump(meta.get('structure_frozen_build_manifest'))) != bound['frozen_manifest_sha256']:
        raise ValueError('This delta does not bind the actual completed checkpoint')
    for o in operations:
        p = o['proof']
        if o.get('op') != 'link' or o['source'] != SOURCE or not o.get('uri', '').startswith('https://') or o['relation'] not in {'DESIGN_TYPE_OF', 'IS_A'}:
            raise ValueError('Only attributed approved physical links are supported')
        if p.get('world_identity_assertion') is not False or p.get('no_identity_merges') is not True or p.get('whole_subject_scope_review') is not True or p.get('classification_axis') != 'physical_structure':
            raise ValueError('Physical scope cannot promote identity, mapping or another axis')
        child, parent = node(c, o['uid']), node(c, o['parent'])
        if not child or not parent or child['visibility'] != 'ACTIVE' or parent['visibility'] != 'ACTIVE' or parent['role'] != 'CLASS':
            raise ValueError('Physical source endpoints must already be admitted')
        if sha(child['data']) != p['native_record_sha256'] or sha(parent['data']) != p['parent_native_record_sha256']:
            raise ValueError('Complete endpoint range changed')
        validate_link_roles(o['relation'], child['role'], parent['role'])
        if child['role'] != p['source_model_role']:
            raise ValueError('Source role changed since its complete-scope review')
        witnesses = p.get('source_witnesses', [])
        if not witnesses or witnesses[0]['uid'] != o['uid'] or not any(w['uid'] == o['parent'] for w in witnesses):
            raise ValueError('Whole own object and whole parent sense require source witnesses')
        for w in witnesses + p.get('source_full_contexts', []):
            validate_witness(c, w)
        own = witnesses[0]
        parsed = complete_owned_physical_genus(own['statement'], child['label'], own.get('bound_source_names', []))
        if parsed != p['selected_physical_predicate'] or parsed['parent'] != o['parent']:
            raise ValueError('Selected physical kind is not the owned first assertion')
        if child['role'] == 'CLASS' and json.loads(child['data']).get('node_type') != 'WORDNET_SYNSET' and not owned_generic_class_scope(own['statement'], child['label'], own.get('bound_source_names', [])):
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
    validate_complete_owned_type_repairs(m.c, manifest, operations, json.loads(review_raw))
    protected_tables = ('nodes','node_profiles','normalization_roles','bridges','dataset_targets','dataset_mapping_checks')
    # Stable ordered checksums include every source object and mapping rather
    # than only the benchmark vicinity. No mutable build output is consulted.
    def fingerprint(table):
        order = 'uid' if table in ('nodes','node_profiles','normalization_roles') else 'id' if table == 'bridges' else 'dataset,class_id'
        import hashlib
        digest = hashlib.sha256()
        for row in m.c.execute('SELECT * FROM '+table+' ORDER BY '+order):
            digest.update((dump(dict(row))+'\n').encode())
        return digest.hexdigest()
    before = {t:fingerprint(t) for t in protected_tables}
    canonical_links = set()
    for o in operations:
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
    if any(fingerprint(t) != before[t] for t in protected_tables):
        raise ValueError('Complete owned physical types changed source roles, identities or mappings')
    counts = dict(Counter(o['relation'] for o in operations))
    m.c.execute('INSERT INTO source_catalogs VALUES(?,?,?,?,?)',('Hierarchy refinement: '+SOURCE,operations[0]['uri'],'Derived factual source-scope assertions; original source records, attribution and licenses retained',sha(raw),dump({'source_assertions':len(operations),'physical_structure_only':True,'source_review_sha256':manifest['source_review_sha256']})))
    m.meta(METADATA_KEY, {'manifest_sha256':sha(path.read_bytes()),'operations_sha256':sha(raw),'operation_count':len(operations),'operations':counts,'source_assertions_added':len(operations),'distinct_canonical_directions_asserted':len(canonical_links),'new_nodes':0,'mapping_promotions':0,'positive_identity_merges':0,'source_declarations_preserved':True,'completed_parent_binding':manifest['completed_parent_binding']})
    m.c.commit()
    return {'status':'PASS','source_assertions_added':len(operations),'distinct_canonical_directions_asserted':len(canonical_links),'new_nodes':0,'mapping_promotions':0,'positive_identity_merges':0}
