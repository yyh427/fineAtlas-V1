"""Append independently documented nominal design-family directions."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from .structure_subject_scope_rules import scoped_subject_genus
from .hierarchy import source_assertion_sha256, validate_link_roles
from .semantics import role_expression
from .structure_regression_repairs import sha

INPUT_NAME = 'structure_primary_aircraft_family_repairs.json'
OPERATION_NAME = 'hierarchy_primary_aircraft_family_repairs.jsonl'
METADATA_KEY = 'primary_aircraft_family_repairs'
SOURCE = 'Primary documented aircraft design-family scope'
NAVIGABLE = {'NATIVE_DESIGN_PARENT', 'DESIGN_TYPE_OF'}
REFERENCE = 'SOURCE_DESIGN_DERIVATION_REFERENCE'

def own_physical_genus(statement: str, label: str):
    # Orthographic normalization never changes the retained raw witness.
    normalized = re.sub(r'\b(wide|narrow)body\b', r'\1-body', statement, flags=re.I)
    return scoped_subject_genus(normalized, label)

def subject_is_nonphysical(statement: str) -> bool:
    head = re.split(r'[.;]|\s+(?:used|for|with|developed|manufactured)\b', statement, maxsplit=1, flags=re.I)[0]
    return bool(re.search(r'\b(?:fictional|virtual|imaginary|toy|scale model|model of|parts? of|engine for|not real|not physical)\b', head, re.I))

def validate_proposed_component_cycles(c, operations):
    """Traverse admitted canonical parents and the whole proposed batch."""
    proposed = defaultdict(set)
    for op in operations:
        if op['relation'] not in NAVIGABLE:
            continue
        child = c.execute('SELECT component_id FROM nodes WHERE uid=?', (op['uid'],)).fetchone()[0]
        parent = c.execute('SELECT component_id FROM nodes WHERE uid=?', (op['parent'],)).fetchone()[0]
        proposed[child].add(parent)
    cached = {}
    def parents(component):
        if component in cached:
            return cached[component]
        peers = [r[0] for r in c.execute('SELECT uid FROM nodes WHERE component_id=?', (component,))]
        marks = ','.join('?' for _ in peers)
        result = set(proposed.get(component, ()))
        sql = 'SELECT r.relation,b.component_id,' + role_expression('a','ap') + ' cr,' + role_expression('b','bp') + " pr FROM entity_relations r JOIN nodes a ON a.uid=r.subject_uid JOIN nodes b ON b.uid=r.object_uid LEFT JOIN node_profiles ap ON ap.uid=a.uid LEFT JOIN node_profiles bp ON bp.uid=b.uid WHERE r.status='ACTIVE' AND r.subject_uid IN (" + marks + ") AND r.relation IN ('NATIVE_DESIGN_PARENT','DESIGN_TYPE_OF','SERIES_MEMBER_OF','CONFIGURATION_OF','CONFIGURATION_TYPE_OF','TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT')"
        for r in c.execute(sql, peers):
            try: validate_link_roles(r['relation'], r['cr'], r['pr'])
            except ValueError: continue
            if r['component_id'] != component: result.add(r['component_id'])
        sql = 'SELECT b.component_id,' + role_expression('a','ap') + ' cr,' + role_expression('b','bp') + " pr FROM edges e JOIN nodes a ON a.uid=e.child_uid JOIN nodes b ON b.uid=e.parent_uid LEFT JOIN node_profiles ap ON ap.uid=a.uid LEFT JOIN node_profiles bp ON bp.uid=b.uid WHERE e.status IN ('ACTIVE','BACKBONE_ACTIVE') AND e.relation='IS_A' AND e.child_uid IN (" + marks + ')'
        for r in c.execute(sql, peers):
            if r['cr'] == r['pr'] == 'CLASS' and r['component_id'] != component: result.add(r['component_id'])
        cached[component] = result
        return result
    for child, ps in proposed.items():
        for parent in ps:
            stack, visited = [parent], set()
            while stack:
                current = stack.pop()
                if current == child:
                    raise ValueError('Proposed hierarchy closes a canonical component cycle')
                if current not in visited:
                    visited.add(current)
                    stack.extend(parents(current))


def normalized_name(value: str) -> str:
    return ' '.join(re.findall(r'[a-z0-9]+', value.casefold()))


def validate_primary_aircraft_family_repairs(c, manifest: dict, operations: list[dict]) -> None:
    if manifest.get('schema') != 'FINEATLAS_PRIMARY_AIRCRAFT_FAMILY_REPAIRS_V1':
        raise ValueError('Unknown primary design-family schema')
    if not operations or len({(x['uid'],x['parent'],x['relation']) for x in operations}) != len(operations):
        raise ValueError('Primary family operations must be nonempty and unique')
    if type(manifest.get('operation_count')) is not int or manifest['operation_count'] != len(operations):raise ValueError('Primary scope operation count is not exact')
    facts = manifest['reviewed_scope_facts']
    documents = manifest['primary_documents']
    for op in operations:
        proof = op['proof']
        if op.get('op') != 'link' or op.get('relation') not in NAVIGABLE | {REFERENCE} or op.get('source') != SOURCE:
            raise ValueError('Only attributed directional design-family connections are allowed')
        if proof.get('world_identity_assertion') is not False or proof.get('dataset_mapping_promotion') is not False or proof.get('whole_nominal_design_scope_review') is not True or proof.get('no_identity_merges') is not True:
            raise ValueError('Nominal family direction does not certify author visual identity')
        fact = facts[proof['primary_scope_fact_id']]
        if proof.get('primary_scope_fact') != fact or proof.get('primary_documents') != {loc['document_id']:documents[loc['document_id']] for loc in fact['primary_source_locators']}:
            raise ValueError('Source proof must retain the complete reviewed primary declaration')
        if fact.get('verdict') != 'PASS' or fact.get('relation') != op['relation'] or not fact.get('scope_observation') or not fact.get('primary_source_locators'):
            raise ValueError('Complete primary directional scope must be adjudicated')
        endpoints=[]
        for uid,key in ((op['uid'],'native_record_sha256'),(op['parent'],'parent_native_record_sha256')):
            n=c.execute('SELECT n.*, '+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(uid,)).fetchone()
            if not n or n['visibility']!='ACTIVE' or sha(n['data'])!=proof[key]:
                raise ValueError('Frozen own design object or complete source changed')
            if n['source'] not in manifest['accepted_design_object_sources']:
                raise ValueError('An author category or lookup-directory sample is not a nominal design object')
            endpoints.append(n)
        child,parent=endpoints
        if op['relation']==REFERENCE:
            if child['role'] not in {'MODEL','MODEL_FAMILY'} or parent['role'] not in {'MODEL','MODEL_FAMILY'}:raise ValueError('Design reference requires distinct nominal design scopes')
            if fact.get('scope_kind')!='DOCUMENTED_DESIGN_ANCESTRY_NON_NAVIGATION':raise ValueError('Derivation cannot be ordinary inclusion')
        else:validate_link_roles(op['relation'],child['role'],parent['role'])
        if child['component_id']==parent['component_id']:
            raise ValueError('Directional connection needs a distinct complete design parent')
        if normalized_name(child['label']) not in [normalized_name(v) for v in fact['child_nominal_names']] or normalized_name(parent['label'])!=normalized_name(fact['parent_nominal_name']):
            raise ValueError('Primary model declaration and source-owned endpoint names disagree')
        if child['role'] not in fact['allowed_child_roles'] or parent['role']!=fact['parent_role']:
            raise ValueError('Documented nominal grain cannot silently change roles')
        for loc in fact['primary_source_locators']:
            doc=documents[loc['document_id']]
            if not doc.get('source_uri','').startswith('https://') or not re.fullmatch('[a-f0-9]{64}',doc.get('sha256','')) or not loc.get('locator') or not loc.get('factual_scope_declaration'):
                raise ValueError('Independent primary document and complete factual direction must be bound')
            if op['uri']!=documents[fact['primary_source_locators'][0]['document_id']]['source_uri']:
                raise ValueError('Assertion provenance must cite its real primary producer')
        for witness in proof['source_witnesses']:
            n=c.execute('SELECT data FROM nodes WHERE uid=?',(witness['uid'],)).fetchone()
            data=json.loads(n['data']) if n else {};text=data.get(witness['field']) or data.get('evidence_record',{}).get(witness['field'])
            witnessed=c.execute('SELECT component_id FROM nodes WHERE uid=?',(witness['uid'],)).fetchone()
            if not witnessed or witnessed[0] not in {child['component_id'],parent['component_id']}:raise ValueError('An incidental related object is not an owned endpoint scope')
            if not n or sha(n['data'])!=witness['data_sha256'] or text!=witness['statement']:
                raise ValueError('Complete owned source witness changed')
        if not {op['uid'],op['parent']} <= {w['uid'] for w in proof['source_witnesses']}:
            raise ValueError('Both source-owned nominal endpoint scopes are required')
        for uid in (op['uid'],op['parent']):
            reviewed=manifest['identity_components'][uid]
            n=c.execute('SELECT component_id FROM nodes WHERE uid=?',(uid,)).fetchone()
            peers=sorted(r['uid'] for r in c.execute('SELECT uid FROM nodes WHERE component_id=?',(n['component_id'],)))
            bridges=c.execute('SELECT * FROM bridges WHERE left_uid=? OR right_uid=?',(uid,uid)).fetchall()
            if peers!=reviewed['uids'] or sorted(source_assertion_sha256(r)+':'+r['status'] for r in bridges)!=reviewed['bridge_content_status_hashes']:
                raise ValueError('Source identity component or reviewed equivalence scope changed')
        for prior in proof['prior_assertions']:
            rows=c.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',tuple(prior[k] for k in ('subject_uid','object_uid','relation','source'))).fetchall()
            if not any(source_assertion_sha256(r)==prior['content_sha256'] and r['status']==prior['status'] for r in rows):
                raise ValueError('Previous source declaration or status history changed')
        if c.execute('SELECT 1 FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',(op['uid'],op['parent'],op['relation'],SOURCE)).fetchone():
            raise ValueError('Primary family input cannot be applied twice')
        child_witness=next(w for w in proof['source_witnesses']if w['uid']==op['uid'])
        if subject_is_nonphysical(child_witness['statement']):raise ValueError('Nonphysical subject cannot inherit a physical design scope')
        if op['relation']=='DESIGN_TYPE_OF':
            matched=own_physical_genus(child_witness['statement'],child['label'])
            if not matched or matched[1]!='wikidata:Q210932':raise ValueError('Whole own subject must explicitly entail the retained physical genus')
            kind=fact.get('physical_genus')
            pw=next(w['statement']for w in proof['source_witnesses']if w['uid']==op['parent'])
            patterns={'airliner':r'^fixed-wing powered aircraft intended to carry cargo or passengers in commercial service$', 'jet':r'^an airplane powered by one or more jet engines$', 'twinjet':r'^a jet plane propelled by two jet engines$'}
            if kind not in patterns or not re.fullmatch(patterns[kind],pw,re.I):raise ValueError('Physical parent whole definition is not the reviewed sense')
            if kind=='twinjet' and not re.search(r'\btwinjet\b',child_witness['statement'],re.I):raise ValueError('Two jet engines cannot be inferred from a bare airliner label')
            if kind=='jet' and not any(re.search(r'\bis\s+(?:an?\s+)?(?:four[ -]engined\s+)?jet aircraft\b',w['statement'],re.I)for w in proof['source_witnesses']if w['uid']!=op['parent']):raise ValueError('Jet propulsion requires an owned complete subject statement')
            if kind not in {'airliner','twinjet','jet'}:raise ValueError('Unreviewed physical genus')
    validate_proposed_component_cycles(c,operations)



def apply_primary_aircraft_family_repairs(m):
    path=m.inputs/INPUT_NAME
    if not path.exists():
        return {'status':'not_requested'}
    manifest=json.loads(path.read_text())
    if manifest['operations_file']!=OPERATION_NAME:
        raise ValueError('Unexpected primary family operations path')
    raw=(m.inputs/OPERATION_NAME).read_bytes();operations=[json.loads(line) for line in raw.decode().splitlines() if line]
    if sha(raw)!=manifest['operations_sha256'] or type(manifest['operation_count']) is not int or len(operations)!=manifest['operation_count']:
        raise ValueError('Primary family input checksum or count changed')
    validate_primary_aircraft_family_repairs(m.c,manifest,operations)
    affected=sorted({op[k] for op in operations for k in ('uid','parent')});markers=','.join('?'for _ in affected)
    counts={t:m.c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('nodes','node_profiles')}
    before_nodes=[tuple(r)for r in m.c.execute('SELECT * FROM nodes WHERE uid IN ('+markers+') ORDER BY uid',affected)]
    before_profiles=[tuple(r)for r in m.c.execute('SELECT * FROM node_profiles WHERE uid IN ('+markers+') ORDER BY uid',affected)]
    mappings={t:[tuple(r)for r in m.c.execute('SELECT * FROM '+t+' ORDER BY dataset,class_id')]for t in ('dataset_targets','dataset_mapping_checks')}
    for op in operations:
        proof=op['proof']
        if op['relation']==REFERENCE:
            eid=m.evidence(SOURCE,op['uri'],proof,REFERENCE,proof['license'])
            m.c.execute('INSERT INTO entity_relations(subject_uid,object_uid,relation,status,source,evidence_id,data) VALUES (?,?,?,?,?,?,?)',(op['uid'],op['parent'],REFERENCE,'SOURCE_DECLARED',SOURCE,eid,json.dumps({'admission_basis':proof,'allowed_views':[],'navigation_eligible':False},sort_keys=True)))
        else:m.typed(op['uid'],op['parent'],op['relation'],proof,SOURCE,op['uri'])
        m.change(METADATA_KEY,'design_family_append',op['uid'],{'prior_assertions':op['proof']['prior_assertions']},{'parent_uid':op['parent'],'relation':op['relation']},proof)
    if any(counts[t]!=m.c.execute('SELECT count(*) FROM '+t).fetchone()[0]for t in counts) or before_nodes!=[tuple(r)for r in m.c.execute('SELECT * FROM nodes WHERE uid IN ('+markers+') ORDER BY uid',affected)] or before_profiles!=[tuple(r)for r in m.c.execute('SELECT * FROM node_profiles WHERE uid IN ('+markers+') ORDER BY uid',affected)] or any(mappings[t]!=[tuple(r)for r in m.c.execute('SELECT * FROM '+t+' ORDER BY dataset,class_id')]for t in mappings):
        raise ValueError('Directional family repair changed raw identities, roles or mappings')
    counters=dict(Counter(op['relation']for op in operations))
    m.c.execute('INSERT OR REPLACE INTO source_catalogs VALUES (?,?,?,?,?)',('Hierarchy refinement: '+SOURCE,operations[0]['uri'],'Derived factual source scopes and direction; original producer attribution and complete source terms retained',sha(raw),json.dumps({'operations':counters,'primary_documents':manifest['primary_documents'],'source_kind':'PRIMARY_DOCUMENTED_AND_COMPLETE_OWNED_SOURCE','old_claims_retained':True},sort_keys=True)))
    m.meta(METADATA_KEY,{'manifest_sha256':sha(path.read_bytes()),'operations_sha256':sha(raw),'operation_count':len(operations),'operations':counters,'non_navigation_references':counters.get(REFERENCE,0),'new_nodes':0,'world_identity_promotions':0,'dataset_mapping_promotions':0,'old_claims_retained':True})
    m.c.commit()
    return {'status':'PASS','source_assertions_added':len(operations),'operations':counters,'new_nodes':0,'world_identity_promotions':0,'dataset_mapping_promotions':0}
