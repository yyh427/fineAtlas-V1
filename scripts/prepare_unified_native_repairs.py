#!/usr/bin/env python3
"""Project retained native classifications and ranked infraspecific parents.

No root is invented. Record-only, merged and inactive taxon parents are not
reactivated. Explicit unplaced/infraspecific flags remain in the evidence.
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

def prepare(database,taxonomy,output):
    c=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
    records=[];reviews=[]
    for r in c.execute(f'''SELECT r.*,n.data raw_data,{role_expression('n','p')} child_role,
        {role_expression('pn','pp')} parent_role FROM entity_relations r
        JOIN nodes n ON n.uid=r.subject_uid LEFT JOIN node_profiles p ON p.uid=n.uid
        JOIN nodes pn ON pn.uid=r.object_uid LEFT JOIN node_profiles pp ON pp.uid=pn.uid
        WHERE r.status='ACTIVE' AND r.relation IN ('NATIVE_CLASSIFICATION_PARENT','TAXONOMIC_PARENT')
        AND n.visibility='ACTIVE' AND pn.visibility='ACTIVE' '''):
        allowed=('CLASS',) if r['relation']=='NATIVE_CLASSIFICATION_PARENT' else ('CLASS','BIOLOGICAL_VARIANT')
        if r['child_role'] not in allowed or r['parent_role'] not in allowed:
            reviews.append({'id':r['id'],'reason':'Incompatible original classification endpoint roles'});continue
        proof={'basis':'RETAINED_EXPLICIT_NATIVE_CLASSIFICATION_STORED_IN_ENTITY_TABLE',
               'original_relation_id':r['id'],'original_relation':r['relation'],
               'original_evidence_id':r['evidence_id'],'original_data':json.loads(r['data'] or '{}'),
               'source_statement_retained':True,'no_new_parent_or_identity':True,
               'native_record_sha256':hashlib.sha256(r['raw_data'].encode()).hexdigest()}
        records.append({'op':'link','uid':r['subject_uid'],'parent':r['object_uid'],
                        'axis':'native_source_classification',
                        'relation':r['relation'],'source':'Retained source classification storage projection',
                        'uri':r['subject_uid'],'proof':proof})
    candidates={}
    for r in c.execute(f'''SELECT e.*,n.data raw_data,p.attributes,{role_expression('n','p')} child_role,
        {role_expression('pn','pp')} parent_role FROM edges e
        JOIN nodes n ON n.uid=e.child_uid JOIN node_profiles p ON p.uid=n.uid
        JOIN nodes pn ON pn.uid=e.parent_uid LEFT JOIN node_profiles pp ON pp.uid=pn.uid
        WHERE e.status='REVIEW' AND n.source='ott' AND n.visibility='ACTIVE' AND pn.visibility='ACTIVE'
        AND p.node_kind='BIOLOGICAL_VARIANT' AND e.reason LIKE '%Native unranked infraspecific%' '''):
        if r['parent_role'] not in ('CLASS','BIOLOGICAL_VARIANT'):
            reviews.append({'id':r['id'],'reason':'Native parent is not an admitted taxon concept'});continue
        candidates[r['child_uid'].split(':',1)[1]]=dict(r)
    h=hashlib.sha256();native={}
    with taxonomy.open('rb') as stream:
        nextline=next(stream);h.update(nextline)
        for raw in stream:
            h.update(raw);parts=[p.strip() for p in raw.decode().split('|')]
            if parts[0] in candidates:
                native[parts[0]]={'uid':parts[0],'parent_uid':parts[1],'name':parts[2],
                    'rank':parts[3],'sourceinfo':parts[4],'flags':parts[6] if len(parts)>6 else '',
                    'raw_line_sha256':hashlib.sha256(raw).hexdigest()}
    checksum=h.hexdigest()
    if checksum!='b852611c131ebe678f8b2e9d5fe6b7fae073bb0f563230ef684e03ee9e151389':
        raise ValueError('Native OTT 3.7draft3 input differs from frozen source')
    for ident,r in candidates.items():
        row=native.get(ident)
        if not row or 'ott:'+row['parent_uid']!=r['parent_uid'] or row['rank']!='no rank - terminal':
            reviews.append({'id':r['id'],'reason':'Retained infraspecific claim differs from native taxon row'});continue
        attrs=json.loads(r['attributes']);rawproof=attrs.get('native_record',{})
        if rawproof.get('parent_uid')!=r['parent_uid'] or row['name']!=rawproof.get('name'):
            reviews.append({'id':r['id'],'reason':'Independent retained rank/parent evidence differs'});continue
        proof={'basis':'EXPLICIT_NATIVE_INFRASPECIFIC_PARENT_PRESERVED_AS_TAXONOMIC_NOT_STRICT_INCLUSION',
               'native_source_version':'OTT 3.7draft3','native_source_sha256':checksum,
               'native_record':row,'original_edge_id':r['id'],
               'native_record_sha256':hashlib.sha256(r['raw_data'].encode()).hexdigest(),
               'retained_rank_evidence':rawproof,'strict_classification':False,
               'placement_uncertain':'unplaced' in {f.strip() for f in row['flags'].split(',')},
               'source_uri':'https://tree.opentreeoflife.org/about/taxonomy-version/ott3.7'}
        records.append({'op':'link','uid':r['child_uid'],'parent':r['parent_uid'],
            'axis':'native_taxonomic_placement',
            'relation':'TAXONOMIC_PARENT','source':'OTT source-declared infraspecific taxonomy placement',
            'uri':proof['source_uri'],'proof':proof})
    with output.open('w') as stream:
        for r in records:stream.write(json.dumps(r,ensure_ascii=False)+'\n')
    summary={'records':len(records),'by_source':dict(Counter(r['source'] for r in records)),
             'reviews':reviews,'restored_taxon_visibility':0,'made_up_parent_nodes':0,
             'unplaced_flags_preserved':True,'native_taxonomy_sha256':checksum}
    output.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True);c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--taxonomy',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.database,a.taxonomy,a.output)
