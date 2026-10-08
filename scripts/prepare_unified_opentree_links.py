#!/usr/bin/env python3
"""Match explicit OpenTree identifiers and scope against a frozen OTT export.

Shared names discover nothing here: P9157 supplies the native identifier.
Scientific names and ranks reject conflicting claims. Extracted source rows
are frozen so rebuilding does not require rereading the complete export.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_unified_taxon_links import values

RANKS={'Q7432':'species','Q34740':'genus','Q35409':'family','Q36602':'order',
       'Q37517':'class','Q38348':'phylum','Q36732':'kingdom','Q68947':'subspecies',
       'Q713623':'no rank'}


def prepare(database,sources,taxonomy,output):
    wanted={};counts=Counter();reviews=[]
    files=list(sorted((sources/'wikidata').glob('batch-*.json')))
    for name in ['wikidata-roots.json','wikidata-roots-retained.json']:
        if (sources/name).exists() and 'entities' in json.loads((sources/name).read_text()):
            files.append(sources/name);break
    for file in files:
        digest=hashlib.sha256(file.read_bytes()).hexdigest()
        for qid,e in json.loads(file.read_text()).get('entities',{}).items():
            ids=values(e,'P9157');ranks=[r.get('id') for r in values(e,'P105') if isinstance(r,dict)]
            if len(ids)!=1 or len(ranks)!=1 or ranks[0] not in RANKS:continue
            uid='ott:'+str(ids[0])
            wanted.setdefault(uid,[]).append({'qid':qid,'entity':e,'rank':RANKS[ranks[0]],
                'snapshot':str(file.relative_to(sources)),'snapshot_sha256':digest})
    rows={};h=hashlib.sha256()
    with taxonomy.open('rb') as stream:
        for raw in stream:
            h.update(raw)
            parts=raw.decode('utf-8').split('\t|\t')
            if len(parts)>=6 and 'ott:'+parts[0].strip() in wanted:
                rows['ott:'+parts[0].strip()]={'uid':parts[0].strip(),'parent_uid':parts[1].strip(),
                   'name':parts[2].strip(),'rank':parts[3].strip(),'sourceinfo':parts[4].strip(),
                   'uniqname':parts[5].strip(),'raw_line_sha256':hashlib.sha256(raw).hexdigest()}
    taxonomy_sha=h.hexdigest()
    version=(taxonomy.parent/'version.txt').read_text().strip()
    c=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
    accepted=[];extract=[]
    roots={r['native_root_uid']:r['wordnet_anchor_uid'] for r in
           json.loads((output/'unified_domain_rules.json').read_text())}
    for uid,claims in sorted(wanted.items()):
        row=rows.get(uid)
        if row is None:counts['native_id_not_in_frozen_version']+=1;continue
        extract.append(row)
        passing=[]
        for claim in claims:
            names={str(v).strip().lower() for v in values(claim['entity'],'P225')}
            if names!={row['name'].lower()} or claim['rank']!=row['rank']:
                reviews.append({'uid':'wikidata:'+claim['qid'],'native_uid':uid,
                     'reason':'EXPLICIT_OTT_ID_WITH_NAME_OR_RANK_SCOPE_CONFLICT',
                     'wikidata_rank':claim['rank'],'native_rank':row['rank'],'wikidata_names':sorted(names),'native_name':row['name']})
                continue
            passing.append(claim)
        qids={r['qid'] for r in passing}
        if len(qids)!=1:
            counts['missing_or_conflicting_scope']+=1;continue
        claim=passing[0];left='wikidata:'+claim['qid']
        nodes=[c.execute('SELECT uid,rank,label,visibility FROM nodes WHERE uid=?',(u,)).fetchone() for u in (left,uid)]
        if any(n is None or n['visibility']!='ACTIVE' for n in nodes):
            reviews.append({'uid':left,'native_uid':uid,'reason':'ENDPOINT_NOT_ADMITTED',
                            'endpoints':[dict(n) if n else None for n in nodes]})
            counts['endpoint_not_admitted']+=1;continue
        if nodes[1]['label'].lower()!=row['name'].lower() or nodes[1]['rank']!=row['rank']:
            raise ValueError('Frozen export and retained native node disagree: '+uid)
        proof={
            'basis':'EXPLICIT_OPEN_TREE_NATIVE_ID_WITH_MATCHING_NAME_RANK_AND_TAXON_SCOPE',
            'wikidata_qid':claim['qid'],'wikidata_lastrevid':claim['entity'].get('lastrevid'),
            'wikidata_snapshot':claim['snapshot'],'wikidata_snapshot_sha256':claim['snapshot_sha256'],
            'property':'P9157','value':row['uid'],'native_taxonomy_version':version,
            'native_taxonomy_sha256':taxonomy_sha,'native_record':row,
            'source_uri':'https://www.wikidata.org/wiki/'+claim['qid'],
            'role_basis':'Ranked taxon concepts denote organism classes; data rows/documents are not merged with those classes',
            'license':'Wikidata CC0; retain OpenTree source attribution'}
        accepted.append({'left_uid':left,'right_uid':uid,'proof':proof})
        # Curated domain heads additionally have explicit WordNet 3.1 IDs.
        # This is a bounded root adjudication, not a name-based leaf matcher.
        anchor=roots.get(uid)
        ids={str(v).removesuffix('-n') for v in values(claim['entity'],'P8814')}
        if anchor and anchor.split(':')[1].removesuffix('-n') in ids and row['rank']=='class':
            wn=c.execute('SELECT label,description,data,visibility FROM nodes WHERE uid=?',(anchor,)).fetchone()
            label=claim['entity'].get('labels',{}).get('en',{}).get('value','')
            if wn and wn['visibility']=='ACTIVE' and wn['label'].lower()==label.lower():
                accepted.append({'left_uid':uid,'right_uid':anchor,'proof':{**proof,
                    'basis':'CURATED_COARSE_CLASS_ROOT_WITH_EXPLICIT_OTT_AND_WORDNET31_IDENTIFIERS',
                    'rule_scope':'Individual domain-root adjudication; not a universal genus/species-name rule',
                    'wordnet31_identifier':anchor.split(':')[1],
                    'wordnet_definition':wn['description'],
                    'wordnet_native_record_sha256':hashlib.sha256(wn['data'].encode()).hexdigest(),
                    'definition_review':'Native ranked taxon concept and the named, explicitly identified WordNet organism class; raw source records remain evidence, not category children'}})
    for name,value in [('unified_opentree_identities.json',accepted),('unified_opentree_identity_reviews.json',reviews),
                       ('unified_opentree_native_records.json',extract)]:
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    summary={'native_taxonomy_sha256':taxonomy_sha,'explicit_id_candidates':len(wanted),
             'accepted_links':len(accepted),'scope_reviews':len(reviews),**counts}
    (output/'unified_opentree_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--sources',type=Path,required=True);p.add_argument('--taxonomy',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    prepare(a.database,a.sources,a.taxonomy,a.output)
