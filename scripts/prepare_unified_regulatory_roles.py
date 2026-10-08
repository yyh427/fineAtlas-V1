#!/usr/bin/env python3
"""Restore FDA catalog-record roles from their explicit native source scope.

Manufacturer model text and regulatory catalogue titles are different fields.
This adapter never infers a model role from a catalogue title containing Models.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3


def prepare(database,output):
    c=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
    records=[]
    for n in c.execute("SELECT n.*,p.node_kind FROM nodes n JOIN node_profiles p ON p.uid=n.uid WHERE n.source='openFDA device classification' AND p.node_kind<>'CLASS'"):
        data=json.loads(n['data'])
        if not data.get('scope','').startswith('Native regulatory classification') or not data.get('definition'):
            raise ValueError('Regulatory scope is not explicitly defined: '+n['uid'])
        proof={'basis':'EXPLICIT_NATIVE_REGULATORY_CLASSIFICATION_SCOPE_OVERRIDES_LEXICAL_MODEL_WORD',
               'native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),
               'allowed_views':['taxonomy'],'native_rank':'class','source_role':'regulatory_classification',
               'definition':data['definition'],'source_sha256':data['source_sha256'],
               'prior_role':n['node_kind'],'scope':data['scope'],
               'not_physical_model_or_manufactured_instance':True}
        base={'uid':n['uid'],'source':'openFDA source regulatory classification contract',
              'uri':'https://open.fda.gov/apis/device/classification/','proof':proof}
        records.append({**base,'op':'role','role':'CLASS'})
        for e in c.execute("SELECT id,object_uid FROM entity_relations WHERE subject_uid=? AND status='ACTIVE' AND relation='DESIGN_TYPE_OF'",(n['uid'],)):
            records.append({**base,'op':'withdraw_typed','relation_id':e['id'],'parent':e['object_uid'],
                            'proof':{**proof,'basis':'REGULATORY_CLASSIFICATION_RECORD_IS_NOT_A_PRODUCT_DESIGN',
                                     'replacement_navigation':'Retained native regulatory classification parent to medical-device type; no equipment/component IS_A invented'}})
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(''.join(json.dumps(r)+'\n' for r in records))
    print(json.dumps({'operations':len(records),'roles':sum(r['op']=='role' for r in records)}));c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();prepare(a.database,a.output)
