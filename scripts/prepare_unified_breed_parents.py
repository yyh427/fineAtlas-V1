#!/usr/bin/env python3
"""Replay full-subtree breed subtype claims into independently scoped WordNet types.

No label list, prefix grouping or breed ancestry inference is used. Each link
requires an unqualified primary P279, an explicit parent WordNet identifier,
full concept-name corroboration and the original WordNet dog-type ancestry.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.semantics import role_expression
from prepare_unified_source_scope import values,full_key

# These primary-ID claims disagree with the retained WordNet concept scope.
# They are excluded from admission, not from preservation or audit statistics.
PARENT_SCOPE_REVIEWS={
    'wordnet31:02099408-n':'German Schnauzer breed does not include every separately developed Schnauzer-related breed',
    'wordnet31:02112613-n':'Eskimo-dog synset is narrower than the broader husky group',
}


def prepare(database,children,parents,output):
    c=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    c.row_factory=sqlite3.Row
    entities={};origins={}
    for directory in (children,parents):
        for path in sorted(directory.glob('batch-*.json')):
            raw=path.read_bytes()
            for q,e in json.loads(raw).get('entities',{}).items():
                entities[q]=e
                origins[q]={'file':directory.name+'/'+path.name,'sha256':hashlib.sha256(raw).hexdigest(),'lastrevid':e.get('lastrevid')}
    scoped={}
    for q,e in entities.items():
        ids=values(e,'P8814')
        if len(ids)!=1:continue
        uid='wordnet31:'+ids[0]
        n=c.execute('SELECT * FROM nodes WHERE uid=? AND visibility=\'ACTIVE\'',(uid,)).fetchone()
        if not n:continue
        names=[e.get('labels',{}).get('en',{}).get('value','')]+[a['value'] for a in e.get('aliases',{}).get('en',[])]
        if not ({full_key(x) for x in names if x}&{full_key(x) for x in json.loads(n['data']).get('labels',[])}):continue
        seen=set();todo=[uid]
        while todo:
            x=todo.pop()
            if x in seen:continue
            seen.add(x)
            todo.extend(r[0] for r in c.execute("SELECT parent_uid FROM edges WHERE child_uid=? AND source_relation='WORDNET_IS_A' AND relation='IS_A'",(x,)))
        if 'wordnet31:02086723-n' in seen:scoped[q]=dict(n)
    records=[];reviews=[]
    child_ids=set()
    for path in children.glob('batch-*.json'):child_ids.update(json.loads(path.read_text()).get('entities',{}))
    for q in sorted(child_ids):
        e=entities[q]
        if 'Q39367' not in values(e,'P31'):continue
        names={full_key(x) for x in [e.get('labels',{}).get('en',{}).get('value','')]+[a['value'] for a in e.get('aliases',{}).get('en',[])] if x}
        for p in values(e,'P279'):
            if p=='Q144':continue  # Existing broad dog relation adds no middle layer.
            if p not in scoped:
                reviews.append({'qid':q,'parent_qid':p,'reason':'Explicit subtype parent lacks a verified admitted full-scope WordNet representation'})
                continue
            parent=scoped[p]
            if parent['uid'] in PARENT_SCOPE_REVIEWS:
                reviews.append({'qid':q,'parent_qid':p,'wordnet_uid':parent['uid'],
                                'reason':PARENT_SCOPE_REVIEWS[parent['uid']]})
                continue
            for n in c.execute(f"SELECT n.*,{role_expression('n','p')} role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid IN (?,?) AND n.visibility='ACTIVE'",('wikidata:'+q,'wikidata-v4:'+q)):
                if n['role']!='CLASS' or full_key(n['label']) not in names:
                    reviews.append({'uid':n['uid'],'reason':'Historical child scope/role cannot be corroborated'});continue
                if n['component_id']==parent['component_id']:continue
                proof={'basis':'PRIMARY_UNQUALIFIED_BREED_SUBTYPE_WITH_EXPLICIT_PARENT_WORDNET31_SCOPE',
                       'source_uri':'https://www.wikidata.org/wiki/'+q,'child_qid':q,'parent_qid':p,
                       'source_property':'P279','parent_identity_property':'P8814',
                       'child_snapshot':origins[q],'parent_snapshot':origins[p],
                       'child_primary_label':e.get('labels',{}).get('en',{}).get('value'),
                       'parent_primary_label':entities[p].get('labels',{}).get('en',{}).get('value'),
                       'parent_definition':parent['description'],
                       'native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),
                       'parent_native_record_sha256':hashlib.sha256(parent['data'].encode()).hexdigest(),
                       'scope':'Named organism breed subtype; original parent identifier resolved to its corroborated concept, no directory/group invention',
                       'source_assertion_not_independent_biological_validation':True,'retrieved_utc':'2026-10-08'}
                records.append({'op':'link','uid':n['uid'],'parent':parent['uid'],
                                'relation':'NATIVE_CLASSIFICATION_PARENT',
                                'source':'Verified primary dog-subtype concept scope',
                                'uri':proof['source_uri'],'proof':proof})
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
    output.with_suffix('.reviews.json').write_text(json.dumps(reviews,indent=2)+'\n')
    summary={'links':len(records),'children':len({r['uid'] for r in records}),'parent_types':len({r['parent'] for r in records}),
             'reviews':len(reviews),'review_reasons':dict(Counter(r['reason'] for r in reviews))}
    output.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary));c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('database','children','parents','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();prepare(a.database,a.children,a.parents,a.output)
