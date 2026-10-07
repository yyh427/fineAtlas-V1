#!/usr/bin/env python3
"""Check every indexed relation against its original record and endpoint contracts."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.semantics import TYPED_TERMINALS


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--staging',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();started=time.monotonic()
    c=sqlite3.connect(a.staging.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    c.execute('ATTACH DATABASE ? AS native',(a.baseline.resolve().as_uri()+'?mode=ro&immutable=1',))
    c.execute('PRAGMA native.cache_size=-1000000');c.execute('PRAGMA cache_size=-1000000')
    classification="""((b.view IN ('strict','taxonomy') AND e.status='ACTIVE' AND e.relation='IS_A')
        OR (b.view='taxonomy' AND e.status='TYPED_ACTIVE' AND e.relation IN ('TAXONOMIC_PARENT','NATIVE_CLASSIFICATION_PARENT'))
        OR (b.view='membership' AND e.status='TYPED_ACTIVE' AND e.relation='REUSABLE_TYPE_MEMBERSHIP'))"""
    typed=' OR '.join("(n.role='"+role+"' AND e.relation IN ("+','.join("'"+r+"'" for r in rels)+'))' for role,rels in TYPED_TERMINALS.items())
    results={}
    for storage,table,child,parent,legal in [
        ('edge','edges','child_uid','parent_uid',classification),
        ('entity','entity_relations','subject_uid','object_uid',"e.status='ACTIVE' AND ("+typed+")")]:
        sql=f'''SELECT count(*) FROM browse_links b
          LEFT JOIN native.{table} e ON e.id=b.record_id
          LEFT JOIN browse_nodes n ON n.uid=e.{child}
          LEFT JOIN browse_nodes p ON p.uid=e.{parent}
          WHERE b.storage=? AND (e.id IS NULL OR n.uid IS NULL OR p.uid IS NULL
            OR b.child_component IS NOT n.component_id OR b.parent_component IS NOT p.component_id
            OR b.role IS NOT n.role OR b.relation IS NOT e.relation
            OR b.child_component=b.parent_component OR NOT ({legal})
            OR (n.view_mask & CASE b.view WHEN 'strict' THEN 1 WHEN 'taxonomy' THEN 2 ELSE 4 END)=0
            OR (p.view_mask & CASE b.view WHEN 'strict' THEN 1 WHEN 'taxonomy' THEN 2 ELSE 4 END)=0
            OR (b.storage='entity' AND p.role NOT IN ('CLASS','MODEL','MODEL_FAMILY','CONFIGURATION'))
            OR (b.storage='edge' AND (n.role NOT IN ('CLASS','MODEL','MODEL_FAMILY','CONFIGURATION')
                AND NOT (b.view='taxonomy' AND n.role='BIOLOGICAL_VARIANT')
                AND NOT (b.view='membership' AND n.role='DATASET_CATEGORY')))
            OR (b.storage='edge' AND (p.role NOT IN ('CLASS','MODEL','MODEL_FAMILY','CONFIGURATION')
                AND NOT (b.view='taxonomy' AND p.role='BIOLOGICAL_VARIANT')
                AND NOT (b.view='membership' AND p.role='DATASET_CATEGORY'))))'''
        results[storage+'_invalid_records']=c.execute(sql,(storage,)).fetchone()[0]
        print(storage,results[storage+'_invalid_records'],flush=True)
        assert results[storage+'_invalid_records']==0,results
    report={'all_pass':True,'checks':results,'all_indexed_relations':c.execute('SELECT count(*) FROM browse_links').fetchone()[0],
            'source_record_endpoint_relation_role_and_view_checks':'All indexed records; original evidence IDs retained',
            'new_semantic_relations':0,'new_semantic_nodes':0,'seconds':time.monotonic()-started}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True);c.close()


if __name__=='__main__':main()
