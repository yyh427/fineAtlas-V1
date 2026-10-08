#!/usr/bin/env python3
"""Attach retained source assertions and frozen review reasons to every unrooted UID.

This exposes evidence gaps; it never changes admission or repairs a graph.
"""
import argparse,collections,csv,gzip,json,pathlib,sqlite3
p=argparse.ArgumentParser(description=__doc__)
for name in ('database','inputs','unrooted-csv','output'):p.add_argument('--'+name,type=pathlib.Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
reviews=collections.defaultdict(list)
for f in sorted(a.inputs.glob('*review*.json')):
    data=json.loads(f.read_text())
    rows=data if isinstance(data,list) else data.get('reviews',[]) if isinstance(data,dict) else []
    for r in rows:
        if isinstance(r,dict) and isinstance(r.get('uid'),str):reviews[r['uid']].append({'file':f.name,'review':r})
c=sqlite3.connect(a.database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
counts=collections.Counter();examples={};n=0
with gzip.open(a.output/'unresolved_evidence.jsonl.gz','wt') as stream:
    for row in csv.DictReader(a.unrooted_csv.open()):
        uid=row['uid'];parents=[]
        for r in c.execute('''SELECT e.parent_uid,e.relation,e.status,e.reason,e.source,p.label parent_label,
            v.component_id parent_has_unified_path FROM edges e LEFT JOIN nodes p ON p.uid=e.parent_uid
            LEFT JOIN view_paths v ON v.component_id=p.component_id AND v.view='unified'
            WHERE e.child_uid=? ORDER BY e.id''',(uid,)):
            q=dict(r);q['parent_has_unified_path']=q['parent_has_unified_path'] is not None;parents.append(q)
        for r in c.execute('''SELECT e.object_uid parent_uid,e.relation,e.status,e.source,p.label parent_label,
            v.component_id parent_has_unified_path FROM entity_relations e LEFT JOIN nodes p ON p.uid=e.object_uid
            LEFT JOIN view_paths v ON v.component_id=p.component_id AND v.view='unified'
            WHERE e.subject_uid=? ORDER BY e.id''',(uid,)):
            q=dict(r);q['parent_has_unified_path']=q['parent_has_unified_path'] is not None;parents.append(q)
        reasons=[r['review'].get('reason','Frozen source review') for r in reviews[uid]]
        if not reasons:
            reasons=sorted({x['reason'] for x in parents if x.get('reason')})
        if not reasons:
            reasons=['Retained parent lacks admitted unified path' if parents else 'No retained source parent assertion']
        record={**row,'frozen_reviews':reviews[uid],'retained_parent_assertions':parents,'evidence_gap_reasons':reasons,
            'action':'Retained; not force-attached or silently excluded. Requires source scope/role/parent evidence before admission.'}
        stream.write(json.dumps(record,ensure_ascii=False)+'\n');n+=1
        for reason in reasons:counts[reason]+=1;examples.setdefault(reason,record)
(a.output/'unresolved_summary.json').write_text(json.dumps({'source_records':n,'reasons_nonexclusive':dict(counts),'representative_objects':list(examples.values()),'all_records_retained':True,'all_unresolved_individually_adjudicated':False},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'source_records':n,'distinct_evidence_gap_reasons':len(counts)}))
