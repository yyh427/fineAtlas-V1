#!/usr/bin/env python3
"""Reproduce unified domains, source identities, all labels/pairs and retention.

Output files are stage checkpoints. A summary is not an unconditional semantic
certification: unresolved source concepts and annotation grain remain visible.
"""
import argparse
import csv
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas import FineAtlas
from fineatlas.semantics import role_expression, edge_predicate, source_admission_view
from fineatlas.engineering_roles import definition_head
from fineatlas.hierarchy import source_assertion_sha256, locate_source_assertion
from fineatlas.role_contracts import reviewed_generic_class
from export_text_training import DATASETS

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def domains(tree,out):
    result=[]
    for domain in tree.domains():
        name=domain['domain'];entry=tree.domain(name)
        rules=[json.loads(r[0]) for r in tree.con.execute(
            'SELECT payload FROM unified_domain_rules WHERE domain_id=? ORDER BY native_root_uid',
            (entry['domain_id'],))]
        members=[dict(r) for r in tree.con.execute('''SELECT dc.category,count(*) identities,
            sum(CASE WHEN vp.component_id IS NULL THEN 1 ELSE 0 END) no_root_witness
            FROM domain_components dc LEFT JOIN view_paths vp ON vp.component_id=dc.component_id AND vp.view=dc.view
            WHERE dc.domain_id=? AND dc.view='unified' GROUP BY dc.category''',(entry['domain_id'],))]
        roots=[]
        for rule in rules:
            root=rule['native_root_uid'];path=tree.path_result(root)
            reached=path['status'] in ('ROOT','CONNECTED')
            roots.append({'native_root_uid':root,'wordnet_anchor_uid':rule['wordnet_anchor_uid'],
                          'synset_id':rule['synset_id'],'definition':rule['definition'],
                          'attachment_relation':rule['relation'],'basis':rule['selection_basis'],
                          'status':path['status'],'path':path['path'],'root_reachable':reached})
        browser=tree.browse_children_page(name,20)
        alias_checks=[{'alias':alias,'resolved_domain':(tree.domain(alias) or {}).get('domain')}
                      for alias in domain.get('aliases',[])]
        role_checks=[]
        for role,count in tree.con.execute("SELECT role,count(*) FROM domain_members WHERE domain_id=? AND view='unified' GROUP BY role",(entry['domain_id'],)):
            page=tree.domain_page(name,limit=1,node_kind=role)
            checked={'role':role,'member_source_uids':count,'returned':len(page['items'])}
            if page['items']:
                n=page['items'][0]
                found=tree.search_page(n['label'],domain=name,node_kind=role,exact=True,limit=100)
                checked['search_contains_member_identity']=any(x['component_id']==n['component_id'] for x in found['items'])
                checked['search_truncated']=found['has_more']
                token_search=tree.search_page(n['label'],domain=name,node_kind=role,limit=100)
                checked['token_search_contains_member_identity']=any(x['component_id']==n['component_id'] for x in token_search['items'])
            role_checks.append(checked)
        result.append({'domain':name,'entry_uid':entry['entry_uid'],'roots':roots,
                       'member_census':members,'browser_status':browser['status'],
                       'alias_checks':alias_checks,'role_interface_checks':role_checks,
                       'default_page_count':len(browser['items']),
                       'pass':bool(roots) and all(r['root_reachable'] for r in roots)
                              and all(r['no_root_witness']==0 for r in members)
                              and browser['status'] in ('OK','EMPTY')
                              and all(a['resolved_domain']==name for a in alias_checks)
                              and all(r['returned']==1 and r['search_contains_member_identity'] and r['token_search_contains_member_identity'] for r in role_checks)})
        write(out/'domains.json',result)
        print('DOMAIN',name,result[-1]['pass'],flush=True)
    return {'domains':len(result),'passed':sum(r['pass'] for r in result),
            'all_domain_members_checked_by_frozen_root_witness_join':True}

def labels(database,out):
    per_view={}; examples=[]
    for view in ('strict','taxonomy','unified','membership'):
        rows=[];totals=Counter()
        with FineAtlas(database,relation_view=view) as tree:
            for ds in DATASETS:
                for t in tree.task_labels(ds):
                    uid=t['target_uid'];node=tree.node(uid);identity=tree.identity(uid)
                    path=tree.path_result(uid);state=tree.connection_status(uid)
                    peers=[]
                    for peer in identity.get('members',identity.get('representations',[])):
                        puid=peer.get('uid') if isinstance(peer,dict) else peer
                        if puid and puid!=uid:
                            peers.append({'uid':puid,'status':tree.connection_status(puid),
                                          'path_status':tree.path_result(puid)['status']})
                    row={'dataset':ds,'class_id':t['class_id'],'label':t['label'],'uid':uid,
                         'source':node['source'],'role':node['node_kind'],
                         'identity':identity,'mapping_review':t.get('mapping_review'),
                         'stored_identity_claim_verified':t.get('stored_identity_claim_verified',t['identity_verified']),
                         'identity_verified':t['identity_verified'],
                         'path':path,'state':state,'task_admission':t['task_admission'],
                         'peer_states':peers,'consistent':path['status']==state['path_status']}
                    rows.append(row);totals['labels']+=1;totals['stored_identity_claim_verified']+=row['stored_identity_claim_verified']
                    totals['identity_verified']+=t['identity_verified']
                    totals['root_reachable']+=state['root_reachable'];totals['path_state_consistent']+=row['consistent']
                    totals['hierarchy_admitted']+=t['task_admission']['usable']
                    if totals['labels']%25==0:print('LABEL',view,totals['labels'],flush=True)
            write(out/(view+'_labels.json'),rows)
        per_view[view]=dict(totals);write(out/'label_summary.json',per_view)
    with FineAtlas(database) as tree:
        pair_summaries={ds:tree.export_training(ds,out/'training'/ds) for ds in DATASETS}
        for a,b in [('1','2'),('100','101'),('3','1'),('2','3'),('77','78')]:
            x=tree.target('cub200',a);y=tree.target('cub200',b)
            index=tree.relation_reward_index('cub200')
            examples.append({'class_ids':[a,b],'labels':[x['label'],y['label']],
                             'uids':[x['target_uid'],y['target_uid']],
                             'paths':[tree.path_result(x['target_uid']),tree.path_result(y['target_uid'])],
                             'task_paths':[tree.task_path('cub200',a),tree.task_path('cub200',b)],
                             'source_representations':[tree.identity(x['target_uid']),tree.identity(y['target_uid'])],
                             'public_lca':tree.lca(x['target_uid'],y['target_uid']),
                             'public_distance':tree.distance(x['target_uid'],y['target_uid']),
                             'training_pair':index.query(a,b)})
        write(out/'cub_examples.json',examples);write(out/'pair_summary.json',pair_summaries)
    return {'views':per_view,'pairs':pair_summaries}

def structure(tree,out):
    c=tree.con;role=role_expression('n','p')
    result={}
    for table,left,right in [('edges','child_uid','parent_uid'),('entity_relations','subject_uid','object_uid')]:
        result[table+'_dangling_retained_records']=c.execute(f'''SELECT count(*) FROM {table} e
            LEFT JOIN nodes a ON a.uid=e.{left} LEFT JOIN nodes b ON b.uid=e.{right}
            WHERE a.uid IS NULL OR b.uid IS NULL''').fetchone()[0]
        result[table+'_dangling_admitted_records']=c.execute(f'''SELECT count(*) FROM {table} e
            LEFT JOIN nodes a ON a.uid=e.{left} LEFT JOIN nodes b ON b.uid=e.{right}
            WHERE e.status IN ('ACTIVE','TYPED_ACTIVE','BACKBONE_ACTIVE') AND (a.uid IS NULL OR b.uid IS NULL)''').fetchone()[0]
        write(out/'structure.json',result);print('STRUCTURE',table,flush=True)
    result['unrooted_classification_records']=[dict(r) for r in c.execute(f'''SELECT n.source,n.rank,{role} role,count(*) records,min(n.uid) example
        FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid LEFT JOIN view_roots vr ON vr.component_id=n.component_id AND vr.view='unified'
        WHERE n.visibility='ACTIVE' AND vr.component_id IS NULL AND {role} IN ('CLASS','BIOLOGICAL_VARIANT')
        AND (json_type(p.attributes,'$.allowed_views') IS NOT 'array' OR EXISTS(SELECT 1 FROM json_each(p.attributes,'$.allowed_views') j WHERE j.value='taxonomy'))
        GROUP BY 1,2,3 ORDER BY records DESC''')]
    result['unified_cached_statistics']=tree.metadata['usability_view_statistics']['unified']
    result['identity_role_conflicts']=[dict(r) for r in c.execute(f'''SELECT n.component_id,count(DISTINCT {role}) roles,count(*) representations,min(n.uid) example
        FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility='ACTIVE'
        GROUP BY n.component_id HAVING count(DISTINCT {role})>1''')]
    unresolved=0
    with (out/'unrooted_navigation_source_uids.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['uid','label','source','native_rank','current_role','role_evidence_status','reason'])
        for n in c.execute(f'''SELECT n.uid,n.label,n.source,n.rank,{role} role,p.attributes FROM nodes n
            LEFT JOIN node_profiles p ON p.uid=n.uid LEFT JOIN view_paths v ON v.component_id=n.component_id AND v.view='unified'
            WHERE n.visibility='ACTIVE' AND v.component_id IS NULL
            AND {role} IN ('CLASS','BIOLOGICAL_VARIANT','MODEL','MODEL_FAMILY','CONFIGURATION','INSTANCE')
            AND (json_type(p.attributes,'$.allowed_views') IS NOT 'array' OR EXISTS(SELECT 1 FROM json_each(p.attributes,'$.allowed_views') j WHERE j.value='taxonomy'))
            ORDER BY n.source,n.uid'''):
            attrs=json.loads(n['attributes'] or '{}')
            writer.writerow([n['uid'],n['label'],n['source'],n['rank'],n['role'],attrs.get('role_status','LEGACY_RANK_FALLBACK'),
                             'No admitted unified parent path; record preserved for source-grain/parent/identity review, not silently excluded or forcibly attached'])
            unresolved+=1
    result['unrooted_records_outside_classification_navigation_roles']=[dict(r) for r in c.execute(f"""SELECT {role} role,count(*) records,min(n.uid) example
        FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid LEFT JOIN view_paths v ON v.component_id=n.component_id AND v.view='unified'
        WHERE n.visibility='ACTIVE' AND v.component_id IS NULL
        AND {role} NOT IN ('CLASS','BIOLOGICAL_VARIANT','MODEL','MODEL_FAMILY','CONFIGURATION','INSTANCE')
        GROUP BY 1 ORDER BY records DESC""")]
    result['non_navigation_role_exclusion_basis']={
        'ATTRIBUTE':'Source attributes/catalogue fields, not ordinary subclass objects; exposed separately',
        'ORGANIZATION':'Named manufacturer/organization directory identity; no fabricated ordinary IS_A or type reward',
        'DATASET_CATEGORY':'Task label/depicted scope, not automatically a physical subclass; original task identity retained',
        'UNKNOWN':'Source role/grain not confirmed; retained as unresolved, not claimed integrated or reward-valid'}
    result['retained_unrooted_navigation_source_uids']=unresolved
    result['universal_all_active_source_navigation_complete']=unresolved==0
    result['raw_source_unrooted_records_excluded_to_inflate_pass_rate']=False
    write(out/'structure.json',result);return result

def _reviewed_decision(c, decision, operation, uid):
    """Validate a frozen decision against its ledger and evidence content."""
    record=json.loads(decision['payload']);proof=record['proof']
    fingerprint=hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if (decision['id']!=fingerprint or decision['operation']!=operation
        or decision['subject_uid']!=uid or record.get('op')!=operation
        or record.get('uid')!=uid or decision['object_uid']!=record.get('parent','')
        or record.get('source')!='Reviewed shared generic-kind contracts' or not record.get('uri')):
        raise ValueError('Frozen semantic decision ledger/content differs')
    stored=c.execute('SELECT * FROM hierarchy_decisions WHERE id=?',(decision['id'],)).fetchone()
    if not stored or any(stored[key]!=decision[key] for key in ('operation','subject_uid','object_uid','evidence_id','payload')):
        raise ValueError('Semantic decision is not present in the retained frozen ledger')
    evidence=c.execute("SELECT * FROM evidence WHERE layer='v1.7-generality-review' AND evidence_id=?",
                       (decision['evidence_id'],)).fetchone()
    if (not evidence or hashlib.sha256(evidence['payload'].encode()).hexdigest()!=evidence['payload_sha256']
        or decision['evidence_id']!='usability:'+evidence['payload_sha256']
        or json.loads(evidence['payload'])!=proof or evidence['source_uri']!=record['uri']):
        raise ValueError('Frozen semantic proof lacks matching retained evidence')
    return record


def _classification_witness(tree, uid):
    """A cached root status alone cannot stand in for retained legal edges."""
    path=tree.path_result(uid)
    if path.get('status') not in ('ROOT','CONNECTED'):
        raise ValueError('Reviewed classification replacement is not root-connected')
    current=uid
    # Public paths are ordered from the native root down to the subject.
    for step in reversed(path.get('path',[])):
        edge=step.get('edge',{})
        child=edge.get('child_uid',step.get('child_uid',step.get('uid')))
        parent=edge.get('parent_uid',step.get('parent_uid'))
        if child!=current or not parent:
            raise ValueError('Replacement witness has discontinuous source endpoints')
        a=tree._basic(child);b=tree._basic(parent)
        if (not a or not b or a.get('visibility')!='ACTIVE' or b.get('visibility')!='ACTIVE'
            or a.get('node_kind')!='CLASS' or b.get('node_kind')!='CLASS'):
            raise ValueError('Replacement witness contains a non-class endpoint')
        if any(n.get('allowed_views') is not None and source_admission_view(tree.relation_view) not in n['allowed_views']
               for n in (a,b)):
            raise ValueError('Replacement classification endpoint is excluded from this view')
        if edge.get('relation')=='SAME_CONCEPT':
            if a['component_id']!=b['component_id']:
                raise ValueError('Replacement identity step changes concept')
            bridges=tree.con.execute("SELECT * FROM bridges WHERE ((left_uid=? AND right_uid=?) OR (left_uid=? AND right_uid=?)) AND relation='SAME_CONCEPT' AND status='ACTIVE'",
                                      (child,parent,parent,child)).fetchall()
            bridges=[b for b in bridges if b['id']==edge.get('id')]
            if not bridges:
                raise ValueError('Replacement identity step has no retained accepted bridge')
        else:
            # The SDK collapses duplicate source arcs by identity. A cached
            # witness can use another retained legal declaration for the same
            # pair, so check the actual source row rather than a display choice.
            retained=tree.con.execute('SELECT e.* FROM edges e WHERE e.id=? AND e.child_uid=? AND e.parent_uid=? AND '+edge_predicate(tree.relation_view),
                                      (edge.get('id'),child,parent)).fetchone()
            if (edge.get('terminal_connection') or not retained
                or retained['relation']!=edge.get('relation')):
                raise ValueError('Replacement witness is not an actual legal classification edge')
        current=parent
    if current!=tree.root_uid:
        raise ValueError('Replacement witness does not reach the declared native root')
    return path


def verify_generic_kind_correction(tree, old, current, decisions):
    """Verify one specifically reviewed generic-kind design withdrawal.

    Status-only preservation, source locator, full-subject definition, current
    canonical role evidence and a reviewed legal classification replacement
    must all agree. No current root-path-only exception is accepted.
    """
    c=tree.con
    result={'original_id':old['id'],'uid':old['subject_uid'],'original_relation':old['relation'],
            'original_parent':old['object_uid'],'verified_semantic_correction':False}
    try:
        if (old['status']!='ACTIVE' or current['status']!='HIERARCHY_SUPERSEDED'
            or old['relation'] not in {'DESIGN_TYPE_OF','SERIES_MEMBER_OF','NATIVE_DESIGN_PARENT'}
            or dict(current)!={**dict(old),'status':'HIERARCHY_SUPERSEDED'}):
            raise ValueError('Generic withdrawal is not a status-only retained design assertion')
        uid=old['subject_uid']
        node=c.execute('SELECT * FROM nodes WHERE uid=?',(uid,)).fetchone()
        profile=c.execute('SELECT * FROM node_profiles WHERE uid=?',(uid,)).fetchone()
        if not node or node['visibility']!='ACTIVE' or not reviewed_generic_class(dict(profile) if profile else None):
            raise ValueError('Current CLASS lacks a consistent verified generic scope guard')
        attrs=json.loads(profile['attributes']);native_sha=hashlib.sha256(node['data'].encode()).hexdigest()
        candidates=[]
        for decision in decisions:
            if decision['operation']!='withdraw_typed_source' or decision['subject_uid']!=uid:continue
            record=_reviewed_decision(c,decision,'withdraw_typed_source',uid)
            locator=record.get('locator',{})
            if (locator.get('subject_uid'),locator.get('object_uid'),locator.get('relation'),locator.get('source'))!=(uid,old['object_uid'],old['relation'],old['source']):continue
            if locator.get('content_sha256')!=source_assertion_sha256(old):
                raise ValueError('Exact old source locator content checksum differs')
            if locate_source_assertion(c,'entity_relations',locator)['id']!=current['id']:
                raise ValueError('Frozen withdrawal refers to another source assertion')
            candidates.append((decision,record))
        if len(candidates)!=1:
            raise ValueError('No unique frozen generic-kind withdrawal matches this assertion')
        decision,withdrawal=candidates[0];proof=withdrawal['proof']
        if (proof.get('basis')!='GENERIC_KIND_IS_NOT_DESIGN_TERMINAL'
            or proof.get('native_record_sha256')!=native_sha
            or proof.get('original_relation')!=old['relation'] or proof.get('original_parent_uid')!=old['object_uid']
            or proof.get('prior_role') not in {'CLASS','MODEL','MODEL_FAMILY'}
            or proof.get('native_rank')!=node['rank']
            or proof.get('individual_semantic_review') is not True or not proof.get('scope_observation')
            or proof.get('no_name_based_identity') is not True
            or proof.get('original_source_payload_and_endpoints_preserved') is not True):
            raise ValueError('Generic withdrawal lacks exact native scope or individual semantic review')
        native=json.loads(node['data'] or '{}')
        statement=native.get('definition') or node['description'] or ''
        if not statement:
            statement=' '.join(e.get('text','') for e in native.get('evidence',[]) if e.get('source')=='wikipedia_intro')
        head=definition_head(statement,node['label'])
        if (not statement or statement!=proof.get('source_statement') or not head or head!=proof.get('subject_kind_head')
            or node['label']!=node['label'].lower()
            or re.search(r'\b(?:series|family|model|line|range) of\b',head,re.I)
            or not (re.match(r'\s*An?\s+'+re.escape(node['label'])+r'\b',statement,re.I)
                    or re.search(r'\b(?:type|kind|class|category) of\b',head,re.I))):
            raise ValueError('Retained whole-subject definition does not establish the reviewed generic kind')
        members=[dict(r) for r in c.execute('SELECT * FROM nodes WHERE component_id=? ORDER BY uid',(node['component_id'],))]
        if (sorted(m['uid'] for m in members)!=proof.get('identity_member_uids')
            or any(m['uid'].split(':')[-1]!=uid.split(':')[-1]
                   or not m['uid'].startswith(('wikidata:','wikidata-v4:','v26-wikidata:'))
                   or tree._basic(m['uid']).get('node_kind')!='CLASS'
                   or m['visibility']!='ACTIVE' for m in members)):
            raise ValueError('Generic decision changes source identity membership')
        role_rows=[r for r in decisions if r['operation']=='role' and r['subject_uid']==uid
                   and r['evidence_id']==profile['evidence_id']]
        if len(role_rows)!=1:
            raise ValueError('Current role evidence is not the unique frozen CLASS decision')
        role=_reviewed_decision(c,role_rows[0],'role',uid);role_proof=role['proof']
        common=('source_statement','subject_kind_head','individual_semantic_review','scope_observation',
                'identity_member_uids','native_record_sha256','no_name_based_identity')
        if (role.get('role')!='CLASS' or role_proof.get('basis')!='REVIEWED_GENERIC_WHOLE_SUBJECT_REPLACES_ADAPTER_DESIGN_ROLE'
            or any(role_proof.get(key)!=proof.get(key) for key in common)
            or any(role_proof.get(key)!=proof.get(key) for key in ('prior_role','native_rank'))
            or attrs.get('source_role')!=role_proof.get('source_role')
            or attrs.get('allowed_views')!=role_proof.get('allowed_views')):
            raise ValueError('Current canonical evidence does not corroborate this full generic scope')
        normalized=c.execute('SELECT * FROM normalization_roles WHERE uid=?',(uid,)).fetchone()
        if (not normalized or normalized['canonical_role']!='CLASS' or normalized['status']!='VERIFIED'
            or normalized['evidence_id']!=profile['evidence_id']):
            raise ValueError('Current normalization role ledger differs from guarded CLASS evidence')
        alternatives=[]
        for d in decisions:
            if d['operation']!='link' or d['subject_uid']!=uid:continue
            # The retained ledger also contains independent older inclusions.
            # Select this review's scope before checking its exact fingerprint;
            # an unrelated prior decision cannot certify this withdrawal.
            candidate=json.loads(d['payload'])
            if candidate.get('proof',{}).get('basis')!=role_proof['basis']:continue
            link=_reviewed_decision(c,d,'link',uid);lp=link['proof']
            if (link.get('relation')!='IS_A' or lp.get('basis')!=role_proof['basis']
                or any(lp.get(key)!=proof.get(key) for key in common)
                or not lp.get('entailment_observation') or lp.get('not_created_for_root_reachability') is not True):continue
            parent=c.execute('SELECT * FROM nodes WHERE uid=?',(link['parent'],)).fetchone()
            if (not parent or parent['visibility']!='ACTIVE' or parent['component_id']==node['component_id']
                or parent['description']!=lp.get('parent_definition')
                or hashlib.sha256(parent['data'].encode()).hexdigest()!=lp.get('parent_native_record_sha256')):
                raise ValueError('Reviewed alternative parent source definition/checksum changed')
            arcs=c.execute("SELECT * FROM edges WHERE child_uid=? AND parent_uid=? AND relation='IS_A' AND status='ACTIVE' AND source=?",
                           (uid,link['parent'],link['source'])).fetchall()
            arcs=[a for a in arcs if json.loads(a['data'] or '{}').get('admission_basis')==lp
                  and d['evidence_id'] in json.loads(a['provenance'] or '{}').get('evidence_ids',[])]
            if not arcs:continue
            if not any(p==link['parent'] and e.get('id') in {a['id'] for a in arcs}
                       for p,e in tree._parents(uid,include_terminal=False)):continue
            alternatives.append({'parent_uid':link['parent'],'edge_ids':[a['id'] for a in arcs],
                                 'decision_id':d['id'],'parent_path':_classification_witness(tree,link['parent'])})
        if not alternatives:
            raise ValueError('No independently reviewed retained legal classification replacement')
        result.update(verified_semantic_correction=True,withdrawal_decision_id=decision['id'],
                      role_evidence_id=profile['evidence_id'],replacement_classification=alternatives,
                      replacement_path=_classification_witness(tree,uid),source_record_retained=True)
    except (ValueError,KeyError,TypeError,sqlite3.DatabaseError,RuntimeError) as error:
        result['rejection_reason']=str(error)
    return result


def preservation(tree,baseline,out):
    c=tree.con;c.execute('ATTACH DATABASE ? AS before',(baseline.resolve().as_uri()+'?mode=ro&immutable=1',))
    result={}
    result['original_nodes_missing']=c.execute('SELECT count(*) FROM before.nodes a LEFT JOIN main.nodes b ON b.uid=a.uid WHERE b.uid IS NULL').fetchone()[0]
    result['original_source_payload_changed']=c.execute('SELECT count(*) FROM before.nodes a JOIN main.nodes b ON b.uid=a.uid WHERE a.data IS NOT b.data').fetchone()[0]
    result['original_active_nodes_removed']=c.execute("SELECT count(*) FROM before.nodes a JOIN main.nodes b ON b.uid=a.uid WHERE a.visibility='ACTIVE' AND b.visibility<>'ACTIVE'").fetchone()[0]
    write(out/'preservation.json',result);print('PRESERVATION original UID/payload/visibility',result,flush=True)
    for table,left,right in [('edges','child_uid','parent_uid'),('entity_relations','subject_uid','object_uid')]:
        result[table+'_original_records_missing_or_retargeted']=c.execute(f'''SELECT count(*) FROM before.{table} a LEFT JOIN main.{table} b ON b.id=a.id
            WHERE b.id IS NULL OR a.{left} IS NOT b.{left} OR a.{right} IS NOT b.{right} OR a.relation IS NOT b.relation OR a.data IS NOT b.data''').fetchone()[0]
        result[table+'_old_active_arc_not_preserved_or_identity_resolved']=c.execute(f'''SELECT count(*) FROM before.{table} a JOIN main.{table} b ON b.id=a.id
            JOIN nodes l ON l.uid=b.{left} JOIN nodes r ON r.uid=b.{right}
            WHERE a.status IN ('ACTIVE','TYPED_ACTIVE') AND b.status<>a.status
            AND NOT(b.status='IDENTITY_RESOLVED' AND l.component_id=r.component_id)''').fetchone()[0]
        write(out/'preservation.json',result);print('PRESERVATION',table,flush=True)
    result['all_original_task_labels_retained']=c.execute('''SELECT count(*) FROM before.dataset_targets a LEFT JOIN main.dataset_targets b
        ON a.dataset=b.dataset AND a.class_id=b.class_id WHERE b.class_id IS NULL OR b.label IS NOT a.label''').fetchone()[0]==0
    result['mapping_changes_have_original_target_history']=c.execute('''SELECT count(*) FROM before.dataset_targets a JOIN main.dataset_targets b
        ON a.dataset=b.dataset AND a.class_id=b.class_id LEFT JOIN dataset_target_history h ON h.dataset=a.dataset AND h.class_id=a.class_id
        WHERE a.target_uid<>b.target_uid AND (h.original_target_uid IS NULL OR h.original_target_uid<>a.target_uid)''').fetchone()[0]==0
    corrections=[]
    for old in c.execute("SELECT a.*,b.status current_status,n.data native_data,p.node_kind current_role FROM before.entity_relations a JOIN main.entity_relations b ON b.id=a.id JOIN nodes n ON n.uid=b.subject_uid LEFT JOIN node_profiles p ON p.uid=n.uid WHERE a.status='ACTIVE' AND b.status<>a.status AND b.status<>'IDENTITY_RESOLVED'"):
        native=json.loads(old['native_data'] or '{}')
        witnesses=[json.loads(r[0]) for r in c.execute("SELECT evidence FROM usability_changes WHERE object_type='typed' AND object_id=?",(str(old['id']),))]
        evidence=next((r for r in witnesses if r.get('basis')=='REGULATORY_CLASSIFICATION_RECORD_IS_NOT_A_PRODUCT_DESIGN'),None)
        path=tree.path_result(old['subject_uid'])
        checked=bool(old['relation']=='DESIGN_TYPE_OF' and old['current_status']=='HIERARCHY_SUPERSEDED'
                     and old['current_role']=='CLASS' and native.get('scope','').startswith('Native regulatory classification')
                     and evidence and evidence.get('definition')==native.get('definition')
                     and path['status'] in ('ROOT','CONNECTED'))
        corrections.append({'original_id':old['id'],'uid':old['subject_uid'],'original_relation':old['relation'],
                            'original_parent':old['object_uid'],'source_record_retained':True,
                            'replacement_path':path,'evidence':evidence,'verified_semantic_correction':checked})
    write(out/'corrected_source_relations.json',corrections)
    verified=sum(r['verified_semantic_correction'] for r in corrections)
    result['explicitly_verified_invalid_design_corrections']=verified
    generic_corrections=[]
    losses=[(dict(a),dict(c.execute('SELECT * FROM main.entity_relations WHERE id=?',(a['id'],)).fetchone()))
            for a in c.execute("SELECT a.* FROM before.entity_relations a JOIN main.entity_relations b ON b.id=a.id WHERE a.status='ACTIVE' AND b.status<>a.status AND b.status<>'IDENTITY_RESOLVED'")]
    subjects=sorted({a['subject_uid'] for a,b in losses})
    decisions=[]
    if subjects and c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hierarchy_decisions'").fetchone():
        marks=','.join('?' for _ in subjects)
        decisions=[dict(r) for r in c.execute("SELECT * FROM hierarchy_decisions WHERE subject_uid IN ("+marks+") AND operation IN ('withdraw_typed_source','role','link')",subjects)]
    fda_ids={r['original_id'] for r in corrections if r['verified_semantic_correction']}
    for old,current in losses:
        if old['id'] not in fda_ids:
            generic_corrections.append(verify_generic_kind_correction(tree,old,current,decisions))
    write(out/'corrected_generic_kind_relations.json',generic_corrections)
    verified_generic=sum(r['verified_semantic_correction'] for r in generic_corrections)
    result['explicitly_verified_generic_kind_corrections']=verified_generic
    root_corrections=[]
    for old in c.execute("SELECT a.*,b.status current_status FROM before.edges a JOIN main.edges b ON b.id=a.id WHERE a.status IN ('ACTIVE','TYPED_ACTIVE') AND b.status<>a.status AND b.status<>'IDENTITY_RESOLVED'"):
        proof=c.execute("SELECT evidence FROM usability_changes WHERE stage='source_semantic_contract' AND object_type='edge' AND object_id=? ORDER BY id DESC LIMIT 1",(str(old['id']),)).fetchone()
        proof=json.loads(proof[0]) if proof else None
        path=tree.path_result(old['child_uid'])
        checked=bool(proof and proof.get('individual_semantic_review') and proof.get('source_scope_conflict')
                     and old['current_status']=='HIERARCHY_SUPERSEDED' and path['status'] in ('ROOT','CONNECTED')
                     and proof.get('replacement_edge_ids') and all(c.execute("SELECT 1 FROM edges WHERE id=? AND child_uid=? AND status='ACTIVE'",(rid,old['child_uid'])).fetchone() for rid in proof['replacement_edge_ids']))
        root_corrections.append({'original_id':old['id'],'uid':old['child_uid'],'original_parent':old['parent_uid'],
                                 'evidence':proof,'replacement_path':path,'verified_semantic_correction':checked})
    write(out/'corrected_root_relations.json',root_corrections)
    verified_roots=sum(r['verified_semantic_correction'] for r in root_corrections)
    result['explicitly_verified_invalid_root_corrections']=verified_roots
    result['unexpected_active_relation_losses']=result['edges_old_active_arc_not_preserved_or_identity_resolved']+result['entity_relations_old_active_arc_not_preserved_or_identity_resolved']-verified-verified_roots-verified_generic
    result['descendant_identity_preservation_basis']='All original source UIDs, raw source payloads and original source endpoints/relations remain. Original valid arcs are retained or zero-depth identity-resolved. Explicitly documented incorrect FDA design, individually reviewed generic-kind design-role assertions and native root-parent arcs are quarantined with retained evidenced legal classification alternatives; their old wrong ancestor/domain sets are intentionally not certified as legitimate. Generic-kind exceptions require exact frozen source locators, full-subject definitions and consistent current canonical CLASS evidence. Focused wide-branch source UID sets are additionally checked by pagination audits.'
    zero_fields=['original_nodes_missing','original_source_payload_changed','original_active_nodes_removed',
                 'edges_original_records_missing_or_retargeted','entity_relations_original_records_missing_or_retargeted','unexpected_active_relation_losses']
    result['pass']=all(result[k]==0 for k in zero_fields) and result['all_original_task_labels_retained'] and result['mapping_changes_have_original_target_history']
    write(out/'preservation.json',result);return result

def nonfocus(tree,samples,out):
    result=[]
    for sample in json.loads(samples.read_text()):
        uid=sample['uid'];node=tree.node(uid);path=tree.path_result(uid)
        result.append({'uid':uid,'domain':sample['domain'],'source':sample['source'],
                       'original_view':sample['view'],'original_status':sample['status'],
                       'unified_status':path['status'],'preserved':node is not None,
                       'classification_or_navigation_available':path['status'] in ('ROOT','CONNECTED'),
                       'source_record':tree.source_hierarchy(uid,limit=3),
                       'sampling_scope':'Frozen nonbenchmark stratum; source semantics must be inspected separately'})
        if len(result)%100==0:print('NONFOCUS',len(result),flush=True)
    write(out/'nonfocus.json',result)
    summary={'count':len(result),'domains':len({r['domain'] for r in result}),
             'preserved':sum(r['preserved'] for r in result),
             'connected':sum(r['classification_or_navigation_available'] for r in result),
             'regressions':sum(r['original_status'] in ('ROOT','CONNECTED') and not r['classification_or_navigation_available'] for r in result),
             'semantic_all_edges_certified':False}
    write(out/'nonfocus_summary.json',summary);return summary

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--baseline',type=Path);p.add_argument('--samples',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--phase',choices=('domains','labels','structure','preservation','nonfocus'),action='append')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);summary={};start=time.monotonic()
    for phase in a.phase or ['domains','labels','structure','preservation','nonfocus']:
        with FineAtlas(a.database,relation_view='unified') as tree:
            if phase=='domains':result=domains(tree,a.output)
            elif phase=='labels':result=labels(a.database,a.output)
            elif phase=='structure':result=structure(tree,a.output)
            elif phase=='preservation':
                if not a.baseline:raise ValueError('--baseline required')
                result=preservation(tree,a.baseline,a.output)
            else:
                if not a.samples:raise ValueError('--samples required')
                result=nonfocus(tree,a.samples,a.output)
        summary[phase]=result;summary['elapsed_seconds']=time.monotonic()-start
        write(a.output/'summary.json',summary);print('PHASE COMPLETE',phase,flush=True)

if __name__=='__main__':main()
