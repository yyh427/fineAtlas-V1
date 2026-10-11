"""Append source-owned complete subject scopes; preserve identities and originals."""
from __future__ import annotations
import json
import re
from .hierarchy import source_assertion_sha256, validate_link_roles, LAYER
from .semantics import role_expression
from .structure_regression_repairs import sha, validate_regression_repairs
from .structure_subject_scope_rules import ordinary_class_genus, scoped_subject_genus, own_family_scope

INPUT_NAME = 'structure_complete_subject_scope_repairs.json'
OPERATION_NAME = 'hierarchy_subject_scope_repairs.jsonl'
SOURCE = 'Reviewed complete source subject and physical type recovery'


def validate_complete_subject_scope_repairs(c, manifest, operations):
    if manifest.get('schema') != 'FINEATLAS_COMPLETE_SUBJECT_SCOPE_REPAIRS_V1':
        raise ValueError('Unknown complete subject scope schema')
    if not operations or len({(op['uid'],op['parent'],op['relation']) for op in operations})!=len(operations):
        raise ValueError('Complete scope operations must be nonempty and unique')
    if any(op.get('op')!='link' or not op.get('uri') or op.get('source')!=SOURCE for op in operations):
        raise ValueError('Complete source scopes only admit attributed append-only links')
    activations = manifest.get('source_class_activations', [])
    activation_uids={x['uid'] for x in activations}
    if len(activation_uids) != len(activations):
        raise ValueError('Source class activation declarations must be unique')
    for activation in activations:
        n = c.execute('SELECT n.*, '+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(activation['uid'],)).fetchone()
        if not n or n['role'] != 'CLASS' or n['visibility'] != activation['before_visibility'] or activation['before_visibility'] != 'SOURCE_ONLY' or sha(n['data']) != activation['native_record_sha256'] or not activation.get('source_uri') or activation.get('scope_decision') != 'ORDINARY_MUSICAL_CLASS_COMPLETE_INTENSIONAL_SCOPE':
            raise ValueError('Source activation does not bind the original ordinary class')
        data = json.loads(n['data'])
        if data.get('definition') != activation['statement'] or 'string instruments, or chordophones, are musical instruments that produce sound from vibrating strings' not in activation['statement']:
            raise ValueError('Source activation lacks whole-subject ordinary class scope')
    ordinary=[op for op in operations if op['uid'] not in activation_uids and op['parent'] not in activation_uids]
    if ordinary:
        validate_regression_repairs(c, {'schema':'FINEATLAS_STRUCTURE_REGRESSION_REPAIRS_V1'}, ordinary)
    for op in operations:
        for uid,key in ((op['uid'],'native_record_sha256'),(op['parent'],'parent_native_record_sha256')):
            n=c.execute('SELECT * FROM nodes WHERE uid=?',(uid,)).fetchone()
            if not n or sha(n['data'])!=op['proof'][key] or (n['visibility']!='ACTIVE' and not (uid in activation_uids and n['visibility']=='SOURCE_ONLY')):
                raise ValueError('Complete scope endpoint or activation source changed')
        for w in op['proof']['source_witnesses']:
            n=c.execute('SELECT data FROM nodes WHERE uid=?',(w['uid'],)).fetchone();data=json.loads(n[0]) if n else {}
            if not n or sha(n[0])!=w['data_sha256'] or (data.get(w['field']) or data.get('evidence_record',{}).get(w['field']))!=w['statement']:
                raise ValueError('Complete source witness changed')
        if op['proof'].get('world_identity_assertion') is not False or op['proof'].get('no_identity_merges') is not True:
            raise ValueError('Type does not establish exact identity')
    for op in operations:
        prior=op['proof'].get('prior_assertion')
        if prior:
            rows=c.execute('SELECT * FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=?',(prior['subject_uid'],prior['object_uid'],prior['relation'],prior['source'])).fetchall()
            if not any(source_assertion_sha256(r)==prior['content_sha256'] and r['status']==prior['status'] for r in rows):
                raise ValueError('Original directional source assertion or review changed')
        proof = op['proof']; witness = proof['source_witnesses'][0]
        row = c.execute('SELECT n.*, '+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(op['uid'],)).fetchone()
        raw = json.loads(row['data'])
        if witness['uid'] != op['uid'] or witness['field'] not in ('description','definition') or raw.get(witness['field']) != witness['statement']:
            raise ValueError('Genus must describe the entire owned source subject')
        parent = c.execute('SELECT n.*, '+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(op['parent'],)).fetchone()
        validate_link_roles(op['relation'],row['role'],parent['role'])
        if not proof.get('whole_subject_scope_review') or not proof.get('scope_observation'):
            raise ValueError('Complete source scope requires explicit full range review')
        role = row['role']; statement = witness['statement']
        expected_relation = {'CLASS':'IS_A','MODEL':'DESIGN_TYPE_OF','MODEL_FAMILY':'DESIGN_TYPE_OF','INSTANCE':'INSTANCE_OF'}.get(role)
        if expected_relation != op['relation']:
            raise ValueError('Current source grain cannot express this physical scope relation')
        if proof.get('reviewed_rule') == 'COMPLETE_ORDINARY_AIRCRAFT_CLASS_SCOPE':
            if role != 'CLASS' or 'aircraft class' not in statement or proof['source_witnesses'][1]['statement'] != 'a vehicle that can fly':
                raise ValueError('Ordinary aircraft genus must be an explicit class scope')
        elif proof.get('reviewed_rule') == 'COMPLETE_CULINARY_DESSERT_DISH_SCOPE':
            if role != 'CLASS' or not re.match(r'^(?:A|An)\s+.+?\bis a dish that consists of sweet foods',statement) or 'specific food preparation' not in proof['source_witnesses'][1]['statement']:
                raise ValueError('Culinary dessert scope does not entail prepared dish')
        elif proof.get('reviewed_rule') == 'COMPLETE_STRING_FAMILY_SOURCE_CLASS_SCOPE':
            if role != 'CLASS' or not re.match(r'^(?:A|An)\s+.+?\bis a musical instrument in the string family\.',statement) or 'produce sound from vibrating strings' not in proof['source_witnesses'][1]['statement']:
                raise ValueError('Source musical string-family scope is not declared')
        elif proof.get('reviewed_rule') == 'COMPLETE_STRING_INSTRUMENT_MUSICAL_SCOPE':
            if role != 'CLASS' or 'string instruments, or chordophones, are musical instruments that produce sound from vibrating strings' not in statement or 'musical tones or sounds' not in proof['source_witnesses'][1]['statement']:
                raise ValueError('String-instrument genus does not entail the broad musical sense')
        elif proof.get('reviewed_rule') == 'COMPLETE_NETWORK_DEVICE_CLASS_SCOPE':
            if role != 'CLASS' or not statement.startswith('A router is a computer and networking device that forwards data packets') or not proof['source_witnesses'][1]['statement'].startswith('an instrumentality invented for a particular purpose'):
                raise ValueError('Network device scope not entailed by the complete source genus')
        else:
            parsed = ordinary_class_genus(statement,row['label'],raw.get('aliases',())) if role == 'CLASS' else scoped_subject_genus(statement,row['label'])
            if not parsed or parsed != (proof['reviewed_physical_genus'], op['parent']):
                raise ValueError('Frozen rule does not entail this whole-subject physical parent: '+op['uid']+' role='+role+' parsed='+repr(parsed)+' proposed='+repr((proof['reviewed_physical_genus'],op['parent'])))
            if role == 'MODEL_FAMILY' and not own_family_scope(statement,row['label']):
                raise ValueError('Family grain lacks an owned family/series declaration')
        prior = proof.get('prior_edge')
        if prior:
            rows = c.execute('SELECT * FROM edges WHERE child_uid=? AND parent_uid=? AND relation=? AND source=?',(prior['child_uid'],prior['parent_uid'],prior['relation'],prior['source'])).fetchall()
            if not any(source_assertion_sha256(r) == prior['content_sha256'] and r['status'] == prior['status'] for r in rows):
                raise ValueError('Original class declaration or prior review changed')


def apply_complete_subject_scope_repairs(m):
    path = m.inputs / INPUT_NAME
    if not path.exists(): return {'status':'not_requested'}
    manifest = json.loads(path.read_text())
    if manifest['operations_file'] != OPERATION_NAME: raise ValueError('Unexpected complete subject scope operations input')
    raw = (m.inputs / OPERATION_NAME).read_bytes()
    if sha(raw) != manifest['operations_sha256']: raise ValueError('Complete subject scope input hash changed')
    operations = [json.loads(line) for line in raw.decode().splitlines() if line]
    if type(manifest['operation_count']) is not int or len(operations) != manifest['operation_count']:
        raise ValueError('Complete subject scope operations incomplete')
    validate_complete_subject_scope_repairs(m.c, manifest, operations)
    for activation in manifest.get('source_class_activations', []):
        n=m.c.execute('SELECT * FROM nodes WHERE uid=?',(activation['uid'],)).fetchone()
        if not n or sha(n['data']) != activation['native_record_sha256'] or n['visibility'] != activation['before_visibility'] or activation['scope_decision'] != 'ORDINARY_MUSICAL_CLASS_COMPLETE_INTENSIONAL_SCOPE':
            raise ValueError('Source class activation no longer binds its complete ordinary range')
        raw_scope=json.loads(n['data'])
        if raw_scope.get('definition') != activation['statement'] or 'string instruments, or chordophones, are musical instruments that produce sound from vibrating strings' not in activation['statement']:
            raise ValueError('Ordinary musical class activation lacks its complete source definition')
        m.role(activation['uid'],'CLASS',{**activation,'allowed_views':['strict','taxonomy','membership','unified']},SOURCE,activation['source_uri'])
        m.c.execute("UPDATE nodes SET visibility='ACTIVE' WHERE uid=?",(activation['uid'],))
        m.change('complete_subject_scope_repairs','source_visibility',activation['uid'],{'visibility':activation['before_visibility']},{'visibility':'ACTIVE'},activation)
    before = {table:[tuple(r) for r in m.c.execute('SELECT * FROM '+table+' ORDER BY dataset,class_id')] for table in ('dataset_targets','dataset_mapping_checks')}
    nodes = m.c.execute('SELECT count(*) FROM nodes').fetchone()[0]
    result = append_scope_links(m,operations)
    licenses=sorted({op['proof'].get('license','Original source attribution retained') for op in operations})
    m.c.execute('INSERT OR REPLACE INTO source_catalogs VALUES (?,?,?,?,?)',('Hierarchy refinement: '+SOURCE,operations[0]['uri'],'; '.join(licenses),sha(raw),json.dumps({'operations':len(operations),'classes_activated':len(manifest.get('source_class_activations',[])),'source_statement_retained':True},sort_keys=True)))
    if nodes != m.c.execute('SELECT count(*) FROM nodes').fetchone()[0] or any(before[t] != [tuple(r) for r in m.c.execute('SELECT * FROM '+t+' ORDER BY dataset,class_id')] for t in before):
        raise ValueError('Whole-subject scopes changed identities or exact dataset mappings')
    m.meta('complete_subject_scope_repairs',{'manifest_sha256':sha(path.read_bytes()),'operations_sha256':sha(raw),'operation_count':len(operations),'original_claims_retained':True,'world_mapping_promotions':0,'activated_source_classes':[x['uid'] for x in manifest.get('source_class_activations',[])]})
    m.c.commit();return {'status':'PASS',**result,'world_mapping_promotions':0}


def append_scope_links(m,operations):
    """Use the retained edge/evidence contracts without altering the old recipe."""
    c=m.c
    c.execute("CREATE TABLE IF NOT EXISTS hierarchy_decisions(id TEXT PRIMARY KEY,operation TEXT NOT NULL,subject_uid TEXT NOT NULL,object_uid TEXT NOT NULL,evidence_id TEXT NOT NULL,payload TEXT NOT NULL)")
    for op in operations:
        proof=op['proof'];uid=op['uid'];parent=op['parent'];relation=op['relation']
        eid=m.evidence(op['source'],op['uri'],proof,'HIERARCHY_REFINEMENT')
        if relation=='IS_A':
            components=[c.execute('SELECT component_id FROM nodes WHERE uid=?',(x,)).fetchone()[0] for x in (uid,parent)]
            if components[0]==components[1]:raise ValueError('New scope link is already an identity contraction')
            c.execute("""INSERT INTO edges(child_uid,parent_uid,relation,original_relation,facet_family,classification_basis,navigation_role,source,source_relation,confidence,provenance,data,layer,status,reason) VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)""",(uid,parent,relation,relation,'NATIVE_OBJECT_KIND',proof['basis'],'SOURCE_VALIDATED',SOURCE,'EVIDENCED_SUBSUMPTION',json.dumps({'evidence_ids':[eid]}),json.dumps({'eligible_for_final_dag':True,'admission_basis':proof,'classification_axis':'physical_structure'}),LAYER,'ACTIVE','Complete owned subject and parent ranges independently reviewed'))
        else:
            m.typed(uid,parent,relation,proof,op['source'],op['uri'])
        c.execute('INSERT OR IGNORE INTO hierarchy_decisions VALUES (?,?,?,?,?,?)',(sha(json.dumps(op,sort_keys=True)),op['op'],uid,parent,eid,json.dumps(op,sort_keys=True)))
    return {'professional_links':len(operations)}
