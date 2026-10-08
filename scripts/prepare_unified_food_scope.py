#!/usr/bin/env python3
"""Resolve native food concepts with explicit P279 and separately reviewed definitions.

This uses source-declared classification, not menu, ingredient or country edges.
The independent scope file is a review record, never a name-prefix classifier.
"""
import argparse,hashlib,json,pathlib,sqlite3,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'src'))
from fineatlas.semantics import role_expression
p=argparse.ArgumentParser(description=__doc__)
for name in ('database','primary','scope-facts','output'):p.add_argument('--'+name,type=pathlib.Path,required=True)
a=p.parse_args();raw=a.primary.read_bytes();entities=json.loads(raw)['entities'];sha=hashlib.sha256(raw).hexdigest();facts=json.loads(a.scope_facts.read_text());c=sqlite3.connect(a.database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
parent=c.execute('SELECT n.*,p.node_kind role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',('wikidata:Q2095',)).fetchone()
assert parent and parent['visibility']=='ACTIVE' and parent['role']=='CLASS'
assert c.execute("SELECT 1 FROM view_paths WHERE view='unified' AND component_id=?",(parent['component_id'],)).fetchone()
ops=[]
for q,f in facts['accepted_food_concepts'].items():
 e=entities[q];uid='wikidata:'+q;n=c.execute('SELECT n.*,'+role_expression('n','p')+' current_role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(uid,)).fetchone()
 if n['current_role'] not in ('UNKNOWN','CLASS'):raise ValueError('Existing role requires separate scope review: '+uid)
 assert n['visibility']=='ACTIVE' and n['label']==e['labels']['en']['value'] and f['concept_not_named_meal_instance']
 claims=[s for s in e.get('claims',{}).get('P279',[]) if s.get('rank')!='deprecated' and not s.get('qualifiers') and s.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id')=='Q2095']
 assert claims and e.get('lastrevid') and f['definition'] and f['url']
 proof={'basis':'EXPLICIT_PRIMARY_FOOD_SUBCLASS_AND_INDEPENDENT_CONCEPT_SCOPE','qid':q,'primary_snapshot_sha256':sha,'primary_lastrevid':e['lastrevid'],'primary_P279_claim_ids':[s['id'] for s in claims],
 'source_uri':'https://www.wikidata.org/wiki/'+q,'independent_scope':f,'native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),
 'source_role':'Source-defined food kind/category','native_rank':n['rank'],'allowed_views':['taxonomy','unified'],
 'relation_semantics':'Native declared food classification; no country/ingredient menu edges or invented finer recipe families','strict_IS_A_asserted':False,'biomedical_claims_asserted':False,
 'parent_native_record_sha256':hashlib.sha256(parent['data'].encode()).hexdigest(),'license':'Wikidata CC0; independent factual scope summaries with encyclopedia attribution'}
 ops.extend([{'op':'role','uid':uid,'role':'CLASS','source':'Explicit current native food classification','uri':proof['source_uri'],'proof':proof},
 {'op':'link','uid':uid,'parent':parent['uid'],'relation':'NATIVE_CLASSIFICATION_PARENT','axis':'native_food_classification','source':'Explicit current native food classification','uri':proof['source_uri'],'proof':proof}])
a.output.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in ops));print(json.dumps({'concepts':len(facts['accepted_food_concepts']),'operations':len(ops),'primary_sha256':sha,'strict_IS_A_added':0,'name_prefix_rules':0}))
