#!/usr/bin/env python3
"""Admit explicit native design units even when their manufacturer is missing.

A manufacturer is a catalogue facet, not a prerequisite for recognizing a
source-declared model. Only the named, frozen source units below are accepted;
historical scope changes and existing incompatible role decisions stay reviewed.
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

UNITS={
    'Q3231690':('car model','MODEL','wordnet31:02961779-n'),
    'Q15056995':('aircraft model','MODEL','wordnet31:02689427-n'),
    'Q15056993':('aircraft family','MODEL_FAMILY','wordnet31:02689427-n'),
    'Q15061018':('proposed aircraft model','MODEL','wordnet31:02689427-n'),
    'Q45296117':('aircraft type','MODEL','wordnet31:02689427-n'),
    'Q55725952':('tractor model','MODEL','wikidata:Q39495'),
}


def prepare(database,snapshots,units,output):
    c=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
    entities={};origins={}
    for directory in (snapshots,units):
        for path in sorted(directory.glob('batch-*.json')):
            raw=path.read_bytes()
            for q,e in json.loads(raw).get('entities',{}).items():
                entities[q]=e;origins[q]={'file':directory.name+'/'+path.name,'sha256':hashlib.sha256(raw).hexdigest(),'lastrevid':e.get('lastrevid')}
    rules={}
    for q,(label,role,root) in UNITS.items():
        e=entities[q]
        if e.get('labels',{}).get('en',{}).get('value')!=label or not e.get('descriptions',{}).get('en',{}).get('value'):
            raise ValueError('Frozen design-unit definition differs: '+q)
        n=c.execute('SELECT uid,visibility FROM nodes WHERE uid=?',(root,)).fetchone()
        if not n or n['visibility']!='ACTIVE':raise ValueError('Design type endpoint not admitted: '+root)
        rules[q]={'qid':q,'label':label,'role':role,'root':root,
                  'semantic_definition':e['descriptions']['en']['value'],'snapshot':origins[q]}
    records=[];reviews=[]
    for n in c.execute(f"""SELECT n.*,p.attributes,{role_expression('n','p')} role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid
        LEFT JOIN view_paths v ON v.component_id=n.component_id AND v.view='unified'
        WHERE n.visibility='ACTIVE' AND n.uid GLOB 'wikidata*:*' AND v.component_id IS NULL"""):
        q=n['uid'].split(':')[1];e=entities.get(q,{})
        found=[r for k,r in rules.items() if k in values(e,'P31')]
        if not found:continue
        if len({r['role'] for r in found})!=1:
            reviews.append({'uid':n['uid'],'reason':'Conflicting model/family unit declarations'});continue
        rule=found[0];names=[e.get('labels',{}).get('en',{}).get('value','')]+[a['value'] for a in e.get('aliases',{}).get('en',[])]
        if full_key(n['label']) not in {full_key(s) for s in names if s}:
            reviews.append({'uid':n['uid'],'reason':'Historical source scope/name is not corroborated by primary full names'});continue
        attrs=json.loads(n['attributes'] or '{}')
        if n['role'] not in ('CLASS',rule['role']) or attrs.get('allowed_views')==[]:
            reviews.append({'uid':n['uid'],'reason':'Existing incompatible source role/admission requires independent review'});continue
        proof={'basis':'DEFINED_PRIMARY_DESIGN_UNIT_AND_CORROBORATED_FULL_ENTITY_SCOPE',
               'qid':q,'source_uri':'https://www.wikidata.org/wiki/'+q,'snapshot':origins[q],
               'primary_label':names[0],'P31':values(e,'P31'),'unit_rule':rule,
               'manufacturers':values(e,'P176'),'manufacturer_missing_is_not_role_uncertainty':True,
               'native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),
               'allowed_views':['strict','taxonomy','membership'],'native_rank':n['rank'],
               'source_role':'Explicit native '+rule['label'],'retrieved_utc':'2026-10-08',
               'not_an_IS_A_or_identity_assertion':True}
        base={'uid':n['uid'],'source':'Primary explicit design-unit scope','uri':proof['source_uri'],'proof':proof}
        records.extend([{**base,'op':'role','role':rule['role']},
                        {**base,'op':'link','relation':'DESIGN_TYPE_OF','parent':rule['root']}])
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(''.join(json.dumps(r)+'\n' for r in records))
    output.with_suffix('.summary.json').write_text(json.dumps({'records':len(records),'roles':len(records)//2,'rules':rules,'reviews':reviews},indent=2)+'\n')
    print(json.dumps({'roles':len(records)//2,'reviews':len(reviews)}));c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('database','snapshots','units','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();prepare(a.database,a.snapshots,a.units,a.output)
