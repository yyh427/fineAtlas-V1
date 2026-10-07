#!/usr/bin/env python3
"""Organise observed MIMO term mappings with their native structural classes.

The publisher's keyword-to-Hornbostel/Sachs mappings are classification
crosswalks. They do not merge source identities or certify universal IS_A.
Only observed leaf-term mappings create groups; broader family mappings remain
in the original source records because they may describe only some variants.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.semantics import role_expression

RDF='{http://www.w3.org/1999/02/22-rdf-syntax-ns#}'
SKOS='{http://www.w3.org/2004/02/skos/core#}'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['database','keywords','classification','shape','output']:p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(a.database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
    kw=ET.parse(a.keywords).getroot();hs=ET.parse(a.classification).getroot()
    concepts={e.get(RDF+'about'):e for e in kw if e.tag==SKOS+'Concept'}
    hconcepts={e.get(RDF+'about'):e for e in hs if e.tag==SKOS+'Concept'}
    kwsha=hashlib.sha256(a.keywords.read_bytes()).hexdigest();hsha=hashlib.sha256(a.classification.read_bytes()).hexdigest()
    shape=[json.loads(l) for l in a.shape.open()];withdrawn={r['edge_id'] for r in shape if r['op']=='withdraw_edge'}
    roles={r['uid']:r['role'] for r in shape if r['op']=='role'};roles.update({r['uid']:'UNKNOWN' for r in shape if r['op']=='source_review'})
    cache={}
    def node(u):
        if u not in cache:
            n=c.execute('SELECT n.*,'+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(u,)).fetchone()
            cache[u]=dict(n) if n else None
            if n:cache[u]['role']=roles.get(u,cache[u]['role'])
        return cache[u]
    source='MIMO observed native structural classification'
    license='Original MIMO source terms and attribution retained; derived classification facts; full upstream XML is not redistributed'
    groups=collections.defaultdict(list);review=[]
    for uri,e in sorted(concepts.items()):
        u='mimo-keyword:'+uri.rsplit('/',1)[-1];n=node(u)
        if not n or n['visibility']!='ACTIVE' or n['role']!='CLASS':continue
        if e.findall(SKOS+'narrower'):continue
        targets=sorted({x.get(RDF+'resource') for x in e.findall(SKOS+'exactMatch') if x.get(RDF+'resource') in hconcepts})
        if not targets:continue
        for original_parent in e.findall(SKOS+'broader'):
            parent_uri=original_parent.get(RDF+'resource');v='mimo-keyword:'+parent_uri.rsplit('/',1)[-1];pn=node(v)
            if not pn or pn['role']!='CLASS' or pn['visibility']!='ACTIVE':continue
            # Preserve all alternatives, explicitly in taxonomy navigation.
            for target in targets:
                h='mimo-hs:'+target.rsplit('/',1)[-1];hn=node(h)
                if not hn or hn['role']!='CLASS' or hn['visibility']!='ACTIVE':
                    review.append({'uid':u,'target':h,'reason':'Missing admitted native classification record'});continue
                groups[v,h].append((u,uri,parent_uri,target,targets))
    records=[];links=set();withdrawals=set()
    for (v,h),members in sorted(groups.items()):
        # Singletons gain the existing HS parent directly; avoid empty or
        # one-child intermediary groups that do not organise this vocabulary.
        uid='hierarchy-type:mimo-'+v.rsplit(':',1)[-1]+'-hs-'+h.rsplit(':',1)[-1]
        pr={'basis':'OBSERVED_NATIVE_INSTRUMENT_CLASSIFICATION_CROSSWALK','native_keyword_parent':v,'native_structural_parent':h,
            'keyword_snapshot_sha256':kwsha,'classification_snapshot_sha256':hsha,'native_mapping_predicate':'skos:exactMatch',
            'allowed_views':['taxonomy'],'variant_dependent_mapping':True,'identity_merge':False,'license':license}
        if len(members)>1:
            label=node(v)['label']+': '+node(h)['label'].split(' ',1)[-1]
            definition='Types in the MIMO '+node(v)['label']+' vocabulary mapped by the publisher to its '+node(h)['label']+' structural category. Multiple source mappings describe alternatives; this group is admitted for native taxonomy browsing.'
            records.append({'op':'class','uid':uid,'label':label,'domain':'musical_instruments','definition':definition,
                            'axis':'native_source_classification','semantic_grain':'native_source_classification','parents':[v,h],
                            'parent_relation':'NATIVE_CLASSIFICATION_PARENT','source':source,'uri':members[0][3],'proof':pr})
        else:uid=h
        for u,uri,puri,target,targets in members:
            proof={**pr,'basis':'NATIVE_INSTRUMENT_TERM_HAS_EXPLICIT_STRUCTURAL_CLASSIFICATION','native_record_sha256':hashlib.sha256(node(u)['data'].encode()).hexdigest(),
                   'native_term_uri':uri,'native_keyword_parent_uri':puri,'native_classifier_uri':target,'all_native_classifier_uris':targets}
            key=u,uid
            if key not in links:
                records.append({'op':'link','uid':u,'parent':uid,'relation':'NATIVE_CLASSIFICATION_PARENT','source':source,'uri':uri,'proof':proof});links.add(key)
            for edge in c.execute("SELECT id FROM edges WHERE child_uid=? AND parent_uid=? AND status='ACTIVE' AND relation='IS_A'",(u,v)):
                if edge['id'] in withdrawals or edge['id'] in withdrawn:continue
                records.append({'op':'withdraw_edge','uid':u,'parent':v,'edge_id':edge['id'],'source':source,'uri':uri,
                                'proof':{**proof,'basis':'NATIVE_CLASSIFICATION_CROSSWALK_REPLACES_FLAT_KEYWORD_PROJECTION','replacement_parent':uid,'original_source_broader_retained':True}})
                withdrawals.add(edge['id'])
    path=a.output/'hierarchy_structure_repairs.jsonl'
    path.write_text(''.join(json.dumps(r,sort_keys=True,ensure_ascii=False)+'\n' for r in records))
    summary={'operations':dict(collections.Counter(r['op'] for r in records)),'source_term_uids':len({r['uid'] for r in records if r['op']=='link'}),'observed_groups':len(groups),
             'classification_links':len(links),'replaced_flat_keyword_edges':len(withdrawals),'reviews':review,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    (a.output/'structure_preparation_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
