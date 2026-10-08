#!/usr/bin/env python3
"""Recover source-native OTT placements rejected solely by rank compatibility.

An explicitly declared native parent is navigation, not a strict IS_A inferred
from rank ordering. Previously disputed, synonym, unaccepted and independent
name/parent-conflict reviews are deliberately not overturned by this adapter.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.semantics import role_expression


def prepare(database,taxonomy,output):
    c=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
    candidates={}
    for e in c.execute(f"""SELECT e.*,n.label child_name,n.rank child_rank,n.data child_data,
        pn.label parent_name,pn.rank parent_rank,{role_expression('n','p')} child_role,
        {role_expression('pn','pp')} parent_role FROM edges e JOIN nodes n ON n.uid=e.child_uid
        JOIN nodes pn ON pn.uid=e.parent_uid LEFT JOIN node_profiles p ON p.uid=n.uid
        LEFT JOIN node_profiles pp ON pp.uid=pn.uid
        WHERE n.source='ott' AND pn.source='ott' AND n.visibility='ACTIVE' AND pn.visibility='ACTIVE'
        AND e.relation='TAXONOMIC_PARENT' AND e.status='REVIEW'
        AND e.reason='No unique compatible active native parent'"""):
        if e['child_role'] in ('CLASS','BIOLOGICAL_VARIANT') and e['parent_role'] in ('CLASS','BIOLOGICAL_VARIANT'):
            candidates[e['child_uid'].split(':')[1]]=dict(e)
    needed=set(candidates)|{e['parent_uid'].split(':')[1] for e in candidates.values()};native={};h=hashlib.sha256()
    with taxonomy.open('rb') as stream:
        for raw in stream:
            h.update(raw);p=[s.strip() for s in raw.decode().split('|')]
            if p[0] in needed:
                native[p[0]]={'uid':p[0],'parent_uid':p[1],'name':p[2],'rank':p[3],
                             'sourceinfo':p[4],'flags':p[6] if len(p)>6 else '',
                             'raw_line_sha256':hashlib.sha256(raw).hexdigest()}
    checksum=h.hexdigest()
    if checksum!='b852611c131ebe678f8b2e9d5fe6b7fae073bb0f563230ef684e03ee9e151389':raise ValueError('OTT source checksum differs')
    records=[];reviews=[]
    for ident,e in candidates.items():
        child=native.get(ident);parent=native.get(e['parent_uid'].split(':')[1])
        if not child or not parent or 'ott:'+child['parent_uid']!=e['parent_uid'] or child['name']!=e['child_name'] or parent['name']!=e['parent_name'] or child['rank']!=e['child_rank'] or parent['rank']!=e['parent_rank']:
            reviews.append({'edge_id':e['id'],'reason':'Exact native identifier, scope/name, parent or rank differs'});continue
        flags={s.strip() for s in child['flags'].split(',')}|{s.strip() for s in parent['flags'].split(',')}
        proof={'basis':'EXACT_SOURCE_NATIVE_PARENT_WITHOUT_RANK_ORDER_IS_A_INFERENCE',
               'native_source_version':'OTT 3.7draft3','native_source_sha256':checksum,
               'native_record':child,'native_parent_record':parent,'original_edge_id':e['id'],
               'original_review_reason':e['reason'],'original_record_retained':True,
               'native_record_sha256':hashlib.sha256(e['child_data'].encode()).hexdigest(),
               'strict_classification':False,'no_new_identity_or_parent':True,
               'placement_uncertain':bool(flags&{'unplaced','sibling_higher','major_rank_conflict','environmental','not_otu'}),
               'scope':'Source-declared synthesized taxon hierarchy; biological rank equality is not identity or a strict subclass proof',
               'source_uri':'https://tree.opentreeoflife.org/about/taxonomy-version/ott3.7'}
        records.append({'op':'link','uid':e['child_uid'],'parent':e['parent_uid'],
                        'relation':'TAXONOMIC_PARENT','axis':'native_taxonomic_placement',
                        'source':'OTT exact native taxonomic placement',
                        'uri':proof['source_uri'],'proof':proof})
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(''.join(json.dumps(r)+'\n' for r in records))
    output.with_suffix('.summary.json').write_text(json.dumps({'links':len(records),'reviews':reviews,'restored_visibility':0,'strict_IS_A_added':0},indent=2)+'\n')
    print(json.dumps({'links':len(records),'reviews':len(reviews)}));c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('database','taxonomy','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();prepare(a.database,a.taxonomy,a.output)
