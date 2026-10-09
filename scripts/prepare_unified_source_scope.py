#!/usr/bin/env python3
"""Ground unconnected product and cultivar records using explicit source units.

Product admission requires a frozen, defined P31 design unit, a manufacturer
and an unchanged full entity label. Cultivar admission requires P105 cultivar,
P225 scientific name, and a P171 parent whose primary taxon scope is explicit.
No series/name-prefix guessing, no restoration of rejected identity bridges.
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

PRODUCT_RULES={
 'Q3231690':{'unit_label':'car model','role':'MODEL','root':'wordnet31:02961779-n',
             'semantic_definition':'Industrial car design associated with a manufacturer; DESIGN_TYPE_OF car, never ordinary IS_A car'},
 'Q15056995':{'unit_label':'aircraft model','role':'MODEL','root':'wordnet31:02689427-n',
              'semantic_definition':'Specific aircraft design/specification, distinguished from its family; role navigation only'},
 'Q15056993':{'unit_label':'aircraft family','role':'MODEL_FAMILY','root':'wordnet31:02689427-n',
              'semantic_definition':'Related aircraft models sharing a basic design; role navigation only'},
}
RANKS={'Q7432':'species','Q34740':'genus','Q35409':'family','Q36602':'order',
       'Q37517':'class','Q38348':'phylum','Q36732':'kingdom','Q68947':'subspecies'}

def values(entity,prop):
    result=[]
    for claim in entity.get('claims',{}).get(prop,[]):
        if claim.get('rank')=='deprecated':continue
        if prop in ('P31','P105','P171','P279') and claim.get('qualifiers'):
            # An applies-to-part, disputed or contextual assertion is not a
            # universal inclusion/role. Frozen raw claims remain available.
            continue
        snak=claim.get('mainsnak',{})
        if snak.get('snaktype')!='value':continue
        value=snak.get('datavalue',{}).get('value')
        if isinstance(value,dict):value=value.get('id')
        if isinstance(value,str):result.append(value)
    return sorted(set(result))

def full_key(label):
    return ' '.join(re.findall(r'\w+',label.casefold()))

def prepare(database,snapshots,parents,output):
    c=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
    source={};origin={}
    for directory in (snapshots,parents,parents.parent/'wikidata-cultivar-units'):
        for path in sorted(directory.glob('batch-*.json')):
            raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
            for q,e in json.loads(raw).get('entities',{}).items():
                source[q]=e;origin[q]={'path':directory.name+'/'+path.name,'sha256':sha,'lastrevid':e.get('lastrevid')}
    for q,rule in PRODUCT_RULES.items():
        e=source.get(q,{})
        if e.get('labels',{}).get('en',{}).get('value')!=rule['unit_label']:
            raise ValueError('Primary design-unit definition differs: '+q)
        rule['definition_snapshot']=origin[q]
        rule['source_definition']=e.get('descriptions',{}).get('en',{}).get('value')
        if not rule['source_definition']:raise ValueError('Missing primary unit definition')
    rows=c.execute(f'''SELECT n.*,p.node_kind profile_role,p.attributes,{role_expression('n','p')} current_role
        FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid LEFT JOIN view_paths v ON v.component_id=n.component_id AND v.view='taxonomy'
        WHERE n.visibility='ACTIVE' AND v.component_id IS NULL AND n.uid GLOB 'wikidata*:*' ORDER BY n.uid''').fetchall()
    records=[];reviews=[];counts=Counter()
    for n in rows:
        q=n['uid'].split(':',1)[1];e=source.get(q)
        if not e or e.get('missing') is not None:
            reviews.append({'uid':n['uid'],'reason':'Missing current primary entity'});continue
        kinds=values(e,'P31');rank=values(e,'P105');scientific=values(e,'P225')
        primary_label=e.get('labels',{}).get('en',{}).get('value','')
        if full_key(n['label'])!=full_key(primary_label):
            reviews.append({'uid':n['uid'],'reason':'Source label/scope changed; no automatic concept reinterpretation','current_label':primary_label});continue
        attrs=json.loads(n['attributes'] or '{}')
        if attrs.get('allowed_views')==[] or n['current_role'] not in ('CLASS','MODEL','MODEL_FAMILY','BIOLOGICAL_VARIANT'):
            reviews.append({'uid':n['uid'],'reason':'Existing admission/role contract requires separate review'});continue
        proof={'source_uri':'https://www.wikidata.org/wiki/'+q,'qid':q,
               'snapshot':origin[q],'primary_label':primary_label,
               'native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),
               'current_P31':kinds,'current_P105':rank,'current_P225':scientific,
               'record_is_not_concept':'UID remains a source representation; biological/design scope is grounded by primary property declarations',
               'license':'Wikidata CC0','retrieved_utc':'2026-10-08'}
        matches=[q for q in PRODUCT_RULES if q in kinds]
        role=None;links=[]
        if len(matches)==1 and values(e,'P176'):
            rule=PRODUCT_RULES[matches[0]];role=rule['role']
            proof.update(basis='DEFINED_PRIMARY_DESIGN_UNIT_PLUS_MANUFACTURER_AND_UNCHANGED_ENTITY_SCOPE',
                         unit_rule=rule,manufacturers=values(e,'P176'),
                         no_family_membership_inferred_from_name=True)
            links=[(rule['root'],'DESIGN_TYPE_OF')]
            # P279 may supply a narrower *already admitted* native type/design.
            # P361 and manufacturer IDs never become classification edges.
            for parentq in values(e,'P279'):
                for p in c.execute(f'''SELECT n.uid,{role_expression('n','p')} role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid
                    JOIN view_paths vp ON vp.component_id=n.component_id AND vp.view='taxonomy'
                    WHERE n.uid IN (?,?) AND n.visibility='ACTIVE' ''',('wikidata:'+parentq,'wikidata-v4:'+parentq)):
                    if p['role']=='CLASS':links.append((p['uid'],'DESIGN_TYPE_OF'))
                    elif p['role'] in ('MODEL','MODEL_FAMILY'):links.append((p['uid'],'NATIVE_DESIGN_PARENT'))
        elif rank==['Q4886'] or any(q in kinds and (q=='Q4886' or 'Q4886' in values(source.get(q,{}),'P279'))
            for q in ('Q4886','Q26817508','Q15731356','Q21160573','Q21157076','Q12179886','Q115606891','Q20898395','Q49621791')):
            parent_ids=values(e,'P171')
            inherited_units={}
            if not parent_ids:
                for unit in kinds:
                    if unit not in ('Q21157076','Q12179886','Q49621791'):continue
                    ue=source.get(unit,{})
                    if 'Q4886' in values(ue,'P279'):
                        parents_of_unit=values(ue,'P171')
                        parent_ids.extend(parents_of_unit)
                        if parents_of_unit:inherited_units[unit]={'snapshot':origin[unit],'P171':parents_of_unit}
                parent_ids=sorted(set(parent_ids))
            for parentq in parent_ids:
                pe=source.get(parentq,{})
                if len(values(pe,'P225'))!=1 or len(values(pe,'P105'))!=1 or values(pe,'P105')[0] not in RANKS:continue
                for p in c.execute(f'''SELECT n.uid,{role_expression('n','p')} role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid
                    JOIN view_paths vp ON vp.component_id=n.component_id AND vp.view='taxonomy'
                    WHERE n.uid IN (?,?) AND n.visibility='ACTIVE' ''',('wikidata:'+parentq,'wikidata-v4:'+parentq)):
                    if p['role']=='CLASS':links.append((p['uid'],'TAXONOMIC_PARENT'))
            if links:
                role='BIOLOGICAL_VARIANT';proof.update(basis='EXPLICIT_CULTIVAR_UNIT_AND_SOURCE_PARENT_TAXON',
                    allowed_views=['taxonomy','unified'],native_rank='cultivar',
                    cultivar_unit_snapshots={q:origin.get(q) for q in kinds if q in source and (q=='Q4886' or 'Q4886' in values(source[q],'P279'))},
                    **({'inherited_unit_taxon_scope':inherited_units,
                        'parent_composition':'P31 membership in explicitly defined cultivar unit plus its unqualified P171 taxon scope; no scientific-name prefix inference'} if inherited_units else {}),
                    parent_scope={q:{'snapshot':origin.get(q),'P225':values(source.get(q,{}),'P225'),
                                      'P105':values(source.get(q,{}),'P105')} for q in parent_ids},
                    biological_scope='Cultivated organism group; not a nomenclatural registration row and not a wild species')
        if not role or not links:
            reviews.append({'uid':n['uid'],'reason':'Explicit design/cultivar scope or compatible connected parent is not established','P31':kinds,'P105':rank});continue
        peer_roles={r[0] for r in c.execute(f'''SELECT {role_expression('n','p')} role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid
            WHERE n.component_id=? AND n.visibility='ACTIVE' ''',(n['component_id'],))}
        if peer_roles-{'CLASS',role}:
            reviews.append({'uid':n['uid'],'reason':'Identity-group grain conflicts with fresh primary declaration','roles':sorted(peer_roles),'primary_role':role});continue
        if role=='BIOLOGICAL_VARIANT':
            peer_ranks={r[0] for r in c.execute('''SELECT coalesce(t.rank,json_extract(p.attributes,'$.native_rank'),n.rank)
                FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid LEFT JOIN node_taxon_ranks t ON t.uid=n.uid
                WHERE n.component_id=? AND n.visibility='ACTIVE' ''',(n['component_id'],))}
            if peer_ranks & set(RANKS.values()):
                reviews.append({'uid':n['uid'],'reason':'Cultivar identity group contains a different native taxonomic rank','ranks':sorted(str(r) for r in peer_ranks)});continue
        if n['profile_role'] is not None and n['profile_role']!=role:
            reviews.append({'uid':n['uid'],'reason':'Existing canonical role needs independent re-adjudication','primary_role':role});continue
        records.append({'op':'role','uid':n['uid'],'role':role,'source':'Verified current primary product/cultivar scope',
                        'uri':proof['source_uri'],'proof':proof})
        for parent,relation in sorted(set(links)):
            records.append({'op':'link','uid':n['uid'],'parent':parent,'relation':relation,
                            'axis':'native_design_navigation' if role!='BIOLOGICAL_VARIANT' else 'native_taxonomic_placement',
                            'source':'Verified current primary product/cultivar scope',
                            'uri':proof['source_uri'],'proof':proof})
        counts[role]+=1
    output.mkdir(parents=True,exist_ok=True)
    with (output/'unified_source_scope.jsonl').open('w') as stream:
        for r in records:stream.write(json.dumps(r,ensure_ascii=False)+'\n')
    (output/'unified_source_scope_reviews.json').write_text(json.dumps(reviews,ensure_ascii=False,indent=2)+'\n')
    (output/'unified_source_scope_rules.json').write_text(json.dumps(PRODUCT_RULES,indent=2)+'\n')
    summary={'source_records_checked':len(rows),'accepted_roles':dict(counts),'operations':len(records),
             'reviews':len(reviews),'name_prefix_family_rules':0,'forced_new_root_edges':0,
             'coarse_design_navigation':'Defined source units of car/aircraft designs entail role-specific design type, not IS_A; explicit existing P279 gives narrower links where admitted',
             'annotation_reward_grain':'Structural usability and accepted design unit do not certify dataset annotation scope'}
    (output/'unified_source_scope_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True);c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--snapshots',type=Path,required=True);p.add_argument('--parents',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    prepare(a.database,a.snapshots,a.parents,a.output)
