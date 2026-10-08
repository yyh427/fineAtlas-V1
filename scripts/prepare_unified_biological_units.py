#!/usr/bin/env python3
"""Place source-defined cultivar/breed classes under corroborated native scopes.

Cultivars receive deliberately broad, source-backed genus anchors. Their
source UIDs and cultivar grain remain intact; no exact species identity is
invented. Potato-variety units that also contain trademarks are not admitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.semantics import role_expression
from prepare_unified_source_scope import values,full_key

RULES={
    'Q958314':{'label':'grape variety','definition':'variety of grape plant',
               'field':'P171','value':'Q30046','role':'BIOLOGICAL_VARIANT','parent':'ott:329893',
               'scientific_scope':'Vitis','basis':'Primary grape-variety scope and declared grape-plant taxon; genus anchor covers both cultivated species and hybrids'},
    'Q1639967':{'label':'hybrid grape','definition':'grape varieties from crossings of different grape species',
               'field':'P171','value':'Q191019','role':'BIOLOGICAL_VARIANT','parent':'ott:329893',
               'scientific_scope':'Vitis','basis':'Explicit hybrid-grape genus placement; no exact species assignment'},
    'Q15731356':{'label':'apple cultivar','definition':'cultivar of apple (Malus domestica)',
               'role':'BIOLOGICAL_VARIANT','parent':'ott:208026','scientific_scope':'Malus',
               'basis':'Primary definition explicitly names Malus domestica; native Malus genus is a conservative anchor for cultivated/hybrid scope'},
    'Q12045585':{'label':'cattle breed','definition':'selectively bred form of the domesticated cattle',
               'field':'P279','value':'Q830','role':'CLASS','parent':'wikidata:Q830',
               'scientific_scope':'domesticated cattle','basis':'Explicit source-defined cattle-breed organism class and cattle supertype, not a breed registration document'},
}
SCOPE_REVIEWS={'Q749165':'Wine name and cultivated-organism P31/P171 claims have conflicting concept grain; documentary alignment is required'}


def prepare(database,snapshots,units,scopes,taxonomy,output):
    c=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
    entities={};origins={}
    for directory in (snapshots,units,scopes):
        for path in sorted(directory.glob('batch-*.json')):
            raw=path.read_bytes()
            for q,e in json.loads(raw).get('entities',{}).items():
                entities[q]=e;origins[q]={'file':directory.name+'/'+path.name,'sha256':hashlib.sha256(raw).hexdigest(),'lastrevid':e.get('lastrevid')}
    native={};h=hashlib.sha256()
    with taxonomy.open('rb') as stream:
        for raw in stream:
            h.update(raw);p=[s.strip() for s in raw.decode().split('|')]
            if p[0] in ('329893','208026','3902985'):
                native['ott:'+p[0]]={'uid':p[0],'parent_uid':p[1],'name':p[2],'rank':p[3],
                                      'sourceinfo':p[4],'flags':p[6] if len(p)>6 else '',
                                      'raw_line_sha256':hashlib.sha256(raw).hexdigest()}
    checksum=h.hexdigest()
    if checksum!='b852611c131ebe678f8b2e9d5fe6b7fae073bb0f563230ef684e03ee9e151389':raise ValueError('Native taxon input differs')
    vitis=entities['Q191019']
    if values(vitis,'P9157')!=['329893'] or values(vitis,'P685')!=['3603'] or values(vitis,'P105')!=['Q34740']:
        raise ValueError('Primary Vitis genus identifiers/rank differ from the native anchor')
    if native['ott:3902985']['name']!='Malus domestica' or native['ott:3902985']['parent_uid']!='208026':
        raise ValueError('Named apple species lacks its original native Malus genus parent')
    for q,r in RULES.items():
        e=entities[q]
        if e.get('labels',{}).get('en',{}).get('value')!=r['label'] or e.get('descriptions',{}).get('en',{}).get('value')!=r['definition']:
            raise ValueError('Primary organism-unit definition differs: '+q)
        if r.get('field') and r['value'] not in values(e,r['field']):raise ValueError('Primary unit scope assertion differs: '+q)
        n=c.execute('SELECT * FROM nodes WHERE uid=? AND visibility=\'ACTIVE\'',(r['parent'],)).fetchone()
        if not n:raise ValueError('Native organism scope not admitted')
        if r['parent'].startswith('ott:'):
            row=native[r['parent']]
            if row['name']!=r['scientific_scope'] or row['rank']!='genus' or n['label']!=row['name']:
                raise ValueError('Native genus scope differs')
        r.update(primary_unit_snapshot=origins[q],native_parent_record=native.get(r['parent']),
                 native_parent_payload_sha256=hashlib.sha256(n['data'].encode()).hexdigest(),
                 native_taxonomy_version='OTT 3.7draft3',native_taxonomy_sha256=checksum)
        if r['scientific_scope']=='Vitis':r['primary_genus_identifier_scope']={'qid':'Q191019','P9157':'329893','P685':'3603','P105':'Q34740','snapshot':origins['Q191019']}
        elif r['scientific_scope']=='Malus':r['native_definition_species_ancestor']=native['ott:3902985']
        else:r['primary_cattle_scope']={'qid':'Q830','label':entities['Q830']['labels']['en']['value'],'definition':entities['Q830']['descriptions']['en']['value'],'snapshot':origins['Q830']}
    records=[];reviews=[]
    for n in c.execute(f"""SELECT n.*,p.attributes,{role_expression('n','p')} role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid
        LEFT JOIN view_paths v ON v.component_id=n.component_id AND v.view='unified'
        WHERE n.visibility='ACTIVE' AND n.uid GLOB 'wikidata*:*' AND v.component_id IS NULL"""):
        q=n['uid'].split(':')[1];e=entities.get(q,{})
        found=[r for k,r in RULES.items() if k in values(e,'P31')]
        if not found:continue
        if q in SCOPE_REVIEWS:
            reviews.append({'uid':n['uid'],'reason':SCOPE_REVIEWS[q],'individual_scope_review':True});continue
        if len({r['parent'] for r in found})!=1:
            reviews.append({'uid':n['uid'],'reason':'Conflicting defined organism-unit scopes'});continue
        r=found[0];names=[e.get('labels',{}).get('en',{}).get('value','')]+[a['value'] for a in e.get('aliases',{}).get('en',[])]
        if full_key(n['label']) not in {full_key(s) for s in names if s}:
            reviews.append({'uid':n['uid'],'reason':'Historical organism label/scope not corroborated'});continue
        rank=values(e,'P105');attrs=json.loads(n['attributes'] or '{}')
        if n['role'] not in ('CLASS',r['role']) or attrs.get('allowed_views')==[] or (rank and any(x not in ('Q4886','Q767728','Q4150646') for x in rank)):
            reviews.append({'uid':n['uid'],'reason':'Existing role/admission or explicit taxon rank conflicts with cultivar/breed scope'});continue
        proof={'basis':'DEFINED_PRIMARY_ORGANISM_UNIT_WITH_CONSERVATIVE_NATIVE_SCOPE',
               'source_uri':'https://www.wikidata.org/wiki/'+q,'snapshot':origins[q],'primary_label':names[0],
               'P31':values(e,'P31'),'P105':rank,'unit_rules':found,
               'native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),
               'allowed_views':['taxonomy'],'source_role':'Source-defined '+r['label'],
               'native_rank':n['rank'],'retrieved_utc':'2026-10-08',
               'exact_species_identity_asserted':False,'genus_anchor_is_not_cultivar_identity':True}
        base={'uid':n['uid'],'source':'Primary organism-unit scope','uri':proof['source_uri'],'proof':proof}
        records.extend([{**base,'op':'role','role':r['role']},
                        {**base,'op':'link','parent':r['parent'],'relation':'TAXONOMIC_PARENT' if r['role']=='BIOLOGICAL_VARIANT' else 'NATIVE_CLASSIFICATION_PARENT'}])
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(''.join(json.dumps(r)+'\n' for r in records))
    output.with_suffix('.summary.json').write_text(json.dumps({'roles':len(records)//2,'rules':RULES,'reviews':reviews},indent=2)+'\n')
    print(json.dumps({'roles':len(records)//2,'reviews':len(reviews)}));c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('database','snapshots','units','scopes','taxonomy','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();prepare(a.database,a.snapshots,a.units,a.scopes,a.taxonomy,a.output)
