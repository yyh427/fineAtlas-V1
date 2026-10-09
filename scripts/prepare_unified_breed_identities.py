#!/usr/bin/env python3
"""Verify full dog-subtree cross-source concepts using WordNet 3.1 IDs.

Requires a primary unqualified dog-breed declaration, one explicit P8814 ID,
exact full native name/alias agreement and a WordNet dog-type definition.
Existing UIDs remain separate; source identifiers cost zero hierarchy depth.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.semantics import role_expression
from prepare_unified_source_scope import values,full_key

def prepare(database,snapshots,output):
    c=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
    links=[];reviews=[]
    dog_scope={}
    def wordnet_dog_scope(uid):
        if uid in dog_scope:return dog_scope[uid]
        todo=[uid];seen=set();found=False
        while todo:
            current=todo.pop()
            if current=='wordnet31:02086723-n':found=True;break
            if current in seen:continue
            seen.add(current)
            todo.extend(r[0] for r in c.execute("SELECT parent_uid FROM edges WHERE child_uid=? AND source_relation='WORDNET_IS_A' AND relation='IS_A'",(current,)))
        dog_scope[uid]=found;return found
    for path in sorted(snapshots.glob('batch-*.json')):
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        for q,e in json.loads(raw).get('entities',{}).items():
            ids=values(e,'P8814');kinds=values(e,'P31')
            if 'Q39367' not in kinds or len(ids)!=1 or not re.fullmatch(r'\d{8}-n',ids[0]):
                reviews.append({'qid':q,'reason':'No unambiguous unqualified dog-breed scope and explicit WordNet 3.1 ID','P8814':ids,'P31':kinds});continue
            wn='wordnet31:'+ids[0]
            n=c.execute('SELECT * FROM nodes WHERE uid=?',(wn,)).fetchone()
            if not n or n['visibility']!='ACTIVE':
                reviews.append({'qid':q,'reason':'WordNet endpoint not admitted','wordnet_uid':wn});continue
            native=json.loads(n['data']);lemmas=native.get('labels',[])
            names=[e.get('labels',{}).get('en',{}).get('value','')]+[a['value'] for a in e.get('aliases',{}).get('en',[])]
            shared={full_key(s) for s in names if s}&{full_key(s) for s in lemmas}
            if not shared or not wordnet_dog_scope(wn):
                reviews.append({'qid':q,'reason':'Native full-name or dog-type definition scope does not corroborate the identifier','wordnet_uid':wn});continue
            for node in c.execute(f'''SELECT n.*,{role_expression('n','p')} role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid
                WHERE n.uid IN (?,?) AND n.visibility='ACTIVE' ''',('wikidata:'+q,'wikidata-v4:'+q)):
                if node['role']!='CLASS':
                    reviews.append({'uid':node['uid'],'reason':'Endpoint role is not a biological breed class'});continue
                if full_key(node['label']) not in {full_key(s) for s in names if s}:
                    reviews.append({'uid':node['uid'],'reason':'Historical source representation has a different primary entity scope/name'});continue
                proof={'basis':'EXPLICIT_WORDNET31_IDENTIFIER_AND_FULL_PRIMARY_BREED_SCOPE',
                       'source_uri':'https://www.wikidata.org/wiki/'+q,'property':'P8814','value':ids[0],
                       'wikidata_snapshot':snapshots.name+'/'+path.name,'wikidata_snapshot_sha256':sha,
                       'wikidata_lastrevid':e.get('lastrevid'),'P31':kinds,
                       'primary_label':names[0],'matching_full_native_lemmas':sorted(shared),
                       'wordnet_version':'3.1','wordnet_definition':n['description'],
                       'native_wordnet_hypernym_scope':'Verified original WordNet 3.1 ancestors include dog, independent of definition-word heuristics',
                       'wordnet_native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),
                       'native_record_sha256':hashlib.sha256(node['data'].encode()).hexdigest(),
                       'scope':'Both denote the named dog breed/variety as an organism class, not a breed registration document',
                       'role_basis':'Dog-breed concept declaration and compatible CLASS endpoints',
                       'license':'Wikidata CC0; Princeton WordNet attribution retained','retrieved_utc':'2026-10-08'}
                links.append({'left_uid':node['uid'],'right_uid':wn,'proof':proof})
    output.mkdir(parents=True,exist_ok=True)
    (output/'unified_breed_identities.json').write_text(json.dumps(links,ensure_ascii=False,indent=2)+'\n')
    (output/'unified_breed_identity_reviews.json').write_text(json.dumps(reviews,ensure_ascii=False,indent=2)+'\n')
    summary={'accepted_source_identity_links':len(links),'wordnet_breed_concepts':len({r['right_uid'] for r in links}),
             'reviews':len(reviews),'identity_is_not_classification_depth':True,
             'discovery_scope':'Complete current dog-root subtree; no benchmark class list used',
             'review_reasons':dict(Counter(r['reason'] for r in reviews))}
    (output/'unified_breed_identity_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True);c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--snapshots',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.database,a.snapshots,a.output)
