#!/usr/bin/env python3
"""Retain declared subtype evidence as role-specific design/config navigation.

The original IS_A records remain available in legacy views. Unified ordinary
classification uses types; source-declared design subsumption is navigated
with its explicit role instead. This creates no new parent identities/layers.
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


def prepare(database,output):
    c=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
    sql=f"""SELECT e.*,n.data native_data,p.evidence_id role_evidence,{role_expression('n','p')} child_role,
             {role_expression('pn','pp')} parent_role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid
             JOIN edges e ON e.child_uid=n.uid
             JOIN nodes pn ON pn.uid=e.parent_uid LEFT JOIN node_profiles pp ON pp.uid=pn.uid
             WHERE {role_expression('n','p')} IN ('MODEL','MODEL_FAMILY','CONFIGURATION')
             AND n.visibility='ACTIVE' AND pn.visibility='ACTIVE'
             AND e.status='ACTIVE' AND e.relation='IS_A' ORDER BY e.id"""
    counts=Counter();reviews=[]
    with output.open('w') as stream:
        for r in c.execute(sql):
            child,parent=r['child_role'],r['parent_role'];rel=None
            if child in ('MODEL','MODEL_FAMILY'):
                if parent=='CLASS':rel='DESIGN_TYPE_OF'
                elif parent in ('MODEL','MODEL_FAMILY'):rel='NATIVE_DESIGN_PARENT'
            elif child=='CONFIGURATION':
                if parent=='CLASS':rel='CONFIGURATION_TYPE_OF'
                elif parent in ('MODEL','MODEL_FAMILY','CONFIGURATION'):rel='CONFIGURATION_OF'
            if rel is None:
                reviews.append({'edge_id':r['id'],'uid':r['child_uid'],'parent':r['parent_uid'],
                                'reason':'Source roles cannot support typed design/configuration navigation'})
                continue
            proof={'basis':'ROLE_COMPATIBLE_REPLAY_OF_RETAINED_SOURCE_SUBSUMPTION',
                   'original_edge_id':r['id'],'original_source':r['source'],
                   'original_source_relation':r['source_relation'],'original_provenance':r['provenance'],
                   'original_declared_relation':'IS_A','role_evidence_id':r['role_evidence'],
                   'child_role':child,'parent_role':parent,
                   'native_record_sha256':hashlib.sha256(r['native_data'].encode()).hexdigest(),
                   'no_new_parent_or_depth':True,'original_record_preserved':True}
            record={'op':'link','uid':r['child_uid'],'parent':r['parent_uid'],'relation':rel,
                    'source':'Unified role navigation of retained declared subtype',
                    'uri':r['child_uid'],'proof':proof}
            stream.write(json.dumps(record,ensure_ascii=False)+'\n');counts[rel]+=1
    output.with_suffix('.summary.json').write_text(json.dumps({'relations':counts,'reviews':reviews,
                               'not_new_intermediate_classes':True},indent=2)+'\n')
    print(json.dumps(counts),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();prepare(a.database,a.output)
