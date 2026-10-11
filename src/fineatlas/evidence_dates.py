"""Repair only candidate-created placeholder dates; preserve historical facts."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sqlite3

INPUT_NAME='structure_evidence_dates.json'


def prepare_evidence_dates(checkpoint, baseline, output):
    c=sqlite3.connect(Path(checkpoint).resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    c.row_factory=sqlite3.Row;c.execute('PRAGMA temp_store=MEMORY')
    c.execute('ATTACH DATABASE ? AS protected',(Path(baseline).resolve().as_uri()+'?mode=ro&immutable=1',))
    rows=[dict(r) for r in c.execute('''SELECT e.* FROM evidence e
        WHERE e.retrieved_utc='2026-10-05' AND json_type(e.payload,'$.retrieved_utc') IS NULL
        AND NOT EXISTS(SELECT 1 FROM protected.evidence b WHERE b.layer=e.layer AND b.evidence_id=e.evidence_id)
        ORDER BY e.layer,e.evidence_id''')]
    result={'schema':'FINEATLAS_CANDIDATE_PLACEHOLDER_DATE_REPAIR_V1',
            'protected_baseline':str(Path(baseline).resolve()),
            'reason':'A historical builder fallback is not evidence of actual source retrieval. Missing retrieval timestamps remain unknown; review date is separate metadata.',
            'replacement_retrieved_utc':None,'rows':rows}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');c.close()
    return {'candidate_only_placeholder_dates':len(rows),'replacement':None}


def apply_evidence_dates(m):
    path=m.inputs/INPUT_NAME
    payload=json.loads(path.read_text())
    if payload.get('schema')!='FINEATLAS_CANDIDATE_PLACEHOLDER_DATE_REPAIR_V1' or payload.get('replacement_retrieved_utc') is not None:
        raise ValueError('Unsupported evidence date repair contract')
    protected=Path(payload['protected_baseline']).resolve()
    if protected==m.db or protected.samefile(m.db):raise ValueError('Never modify protected baseline')
    m.c.execute('ATTACH DATABASE ? AS date_protected',(protected.as_uri()+'?mode=ro&immutable=1',))
    repaired=0;already=0
    input_sha=hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        for expected in payload['rows']:
            key=(expected['layer'],expected['evidence_id'])
            if m.c.execute('SELECT 1 FROM date_protected.evidence WHERE layer=? AND evidence_id=?',key).fetchone():
                raise ValueError('Evidence date repair would modify historical source evidence')
            actual=m.c.execute('SELECT * FROM evidence WHERE layer=? AND evidence_id=?',key).fetchone()
            if not actual:raise ValueError('Candidate-created evidence missing')
            row=dict(actual)
            if {k:v for k,v in row.items() if k!='retrieved_utc'}!={k:v for k,v in expected.items() if k!='retrieved_utc'} or row['retrieved_utc'] not in ('2026-10-05',None) or 'retrieved_utc' in json.loads(row['payload']):
                raise ValueError('Candidate evidence date/payload drift')
            if row['retrieved_utc'] is None:already+=1;continue
            m.c.execute('UPDATE evidence SET retrieved_utc=NULL WHERE layer=? AND evidence_id=?',key)
            m.change('evidence_date','evidence',json.dumps(key),row,{**row,'retrieved_utc':None},
                     {'basis':'UNKNOWN_RETRIEVAL_DATE_WITHOUT_FROZEN_SOURCE_TIMESTAMP',
                      'original_source_evidence_preserved':True,'input_sha256':input_sha})
            repaired+=1
        m.c.commit()
    finally:
        if m.c.in_transaction:m.c.rollback()
        m.c.execute('DETACH DATABASE date_protected')
    return {'candidate_only_dates_corrected':repaired,'already_correct':already,'historical_evidence_unchanged':True}
