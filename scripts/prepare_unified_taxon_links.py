#!/usr/bin/env python3
"""Admit taxon-concept identities using shared primary identifiers, not names.

AviList species concepts must match nondeprecated Wikidata rank/name claims
AND the published Cornell code AND the published BirdLife/IUCN identifier.
Names only check contradictions. WordNet identity additionally requires the
explicit WordNet 3.1 identifier and the full scientific lemma in that synset.
This adapter processes the complete retrieved source scope, not benchmark IDs.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import pandas as pd


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def values(entity, prop):
    out=[]
    for claim in entity.get('claims',{}).get(prop,[]):
        if claim.get('rank')=='deprecated':continue
        snak=claim.get('mainsnak',{})
        if snak.get('snaktype')=='value' and 'datavalue' in snak:
            out.append(snak['datavalue']['value'])
    return out


def prepare(database,sources,output):
    output.mkdir(parents=True,exist_ok=True)
    table=pd.read_excel(sources/'avilist-v2025b.xlsx',sheet_name=0).fillna('')
    avisha=sha(sources/'avilist-v2025b.xlsx')
    bycode=defaultdict(list);byname=defaultdict(list);native=[]
    for original in table.to_dict('records'):
        row={k:v.item() if hasattr(v,'item') else v for k,v in original.items()}
        if str(row['Taxon_rank']).lower()!='species':continue
        uid='avilist:'+str(row['Scientific_name']).strip().lower()
        record={'uid':uid,'row':row,'source_uri':'https://doi.org/10.2173/avilist.v2025b','source_sha256':avisha}
        native.append(record)
        code=str(row['Species_code_Cornell_Lab']).strip()
        if code and row['English_name_Clements_v2025']:
            bycode[code].append(record)
        for field in ('English_name_AviList','English_name_Clements_v2025','English_name_BirdLife_v10'):
            name=str(row[field]).strip()
            if name:byname[name.lower()].append(uid)
    c=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
    accepted=[];review=[];counts=Counter();assigned=defaultdict(set)
    for file in sorted((sources/'wikidata').glob('batch-*.json')):
        filehash=sha(file)
        for qid,entity in json.loads(file.read_text()).get('entities',{}).items():
            ranks=[v.get('id') for v in values(entity,'P105') if isinstance(v,dict)]
            if ranks!=['Q7432']:
                counts['not_unambiguously_species']+=1;continue
            codes=values(entity,'P3444');matches=[]
            for code in codes:
                matches.extend(bycode.get(code,[]))
            matches={r['uid']:r for r in matches}
            if len(matches)!=1:
                counts['missing_or_ambiguous_primary_code']+=1;continue
            native_record=next(iter(matches.values()));row=native_record['row']
            birdids={str(v) for p in ('P5257','P627') for v in values(entity,p)}
            match=re.search(r'/factsheet/([0-9]+)',str(row['BirdLife_DataZone_URL']))
            scientific={str(v).strip().lower() for v in values(entity,'P225')}
            expected=str(row['Scientific_name']).strip().lower()
            if not match or match[1] not in birdids or not row['English_name_BirdLife_v10'] or scientific!={expected}:
                review.append({'uid':'wikidata:'+qid,'candidate_uid':native_record['uid'],
                    'reason':'PRIMARY_IDENTIFIER_OR_SCIENTIFIC_SCOPE_CONFLICT','cornell_codes':codes,
                    'birdlife_claims':sorted(birdids),'scientific_claims':sorted(scientific),
                    'source_file':str(file.relative_to(sources))})
                counts['identifier_or_scope_conflict']+=1;continue
            left='wikidata:'+qid;right=native_record['uid']
            nodes=[c.execute('SELECT uid,label,rank,visibility,source,data FROM nodes WHERE uid=?',(u,)).fetchone() for u in (left,right)]
            if any(n is None or n['visibility']!='ACTIVE' for n in nodes):
                counts['endpoint_missing_or_not_admitted']+=1;continue
            if str(nodes[1]['rank']).lower()!='species' or str(nodes[1]['label']).lower()!=expected:
                raise ValueError('Retained AviList endpoint differs from primary row: '+right)
            proof={'basis':'SHARED_CORNELL_AND_BIRDLIFE_CONCEPT_IDENTIFIERS_WITH_MATCHING_SPECIES_RANK',
                'scientific_name':row['Scientific_name'],'wikidata_qid':qid,'wikidata_lastrevid':entity.get('lastrevid'),
                'wikidata_snapshot':str(file.relative_to(sources)),'wikidata_snapshot_sha256':filehash,
                'avilist_version':'v2025b','avilist_snapshot_sha256':avisha,'avilist_sequence':row['Sequence'],
                'cornell_code':row['Species_code_Cornell_Lab'],'birdlife_id':match[1],
                'properties':['P3444','P5257/P627','P105','P225'],
                'role_basis':'Both endpoints denote the species concept/organism class, not the spreadsheet or database record itself',
                'identity_scope':'Species concepts with matching identifiers and scope; no name-only restoration',
                'source_uri':'https://www.wikidata.org/wiki/'+qid,'license':'Wikidata CC0; AviList CC BY 4.0'}
            accepted.append({'left_uid':left,'right_uid':right,'proof':proof})
            assigned[right].add(left)
            # Identifier alone is not enough if the synset denotes a wider class.
            for value in values(entity,'P8814'):
                code=str(value).removesuffix('-n')
                if not re.fullmatch('[0-9]{8}',code):continue
                wn='wordnet31:'+code+'-n'
                n=c.execute('SELECT * FROM nodes WHERE uid=?',(wn,)).fetchone()
                if not n or n['visibility']!='ACTIVE':continue
                data=json.loads(n['data'] or '{}')
                lemmas={str(s).replace('_',' ').strip().lower() for s in data.get('labels',[])}
                if expected not in lemmas:
                    review.append({'uid':wn,'candidate_uid':right,'reason':'EXPLICIT_WORDNET_ID_BUT_NO_EXACT_SPECIES_LEMMA','wikidata_qid':qid})
                    continue
                accepted.append({'left_uid':wn,'right_uid':right,'proof':{**proof,
                    'basis':'EXPLICIT_WORDNET31_ID_PLUS_MATCHING_SCIENTIFIC_SPECIES_LEMMA_AND_PRIMARY_TAXON_CONCEPT',
                    'wordnet31_identifier':code,'wordnet_native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),
                    'wordnet_definition':n['description']}})
    # A source concept cannot silently absorb two conflicting Wikidata objects.
    ambiguous={k for k,v in assigned.items() if len(v)>1}
    safe=[]
    for link in accepted:
        if link['right_uid'] in ambiguous:
            review.append({'uid':link['left_uid'],'candidate_uid':link['right_uid'],'reason':'MULTIPLE_SOURCE_OBJECTS_CLAIM_SAME_CONCEPT_IDS'})
        else:safe.append(link)
    for name,uids in byname.items():byname[name]=sorted(set(uids))
    for filename,value in [('unified_taxon_identities.json',safe),('unified_taxon_identity_reviews.json',review),
                           ('unified_avilist_native_records.json',native),('unified_avilist_name_index.json',byname)]:
        (output/filename).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    summary={'primary_species_records':len(native),'admitted_identity_links':len(safe),
             'admitted_native_species':len({r['right_uid'] for r in safe}),
             'ambiguous_concept_ids':len(ambiguous),'explicit_reviews':len(review),**counts}
    (output/'unified_taxon_summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--sources',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.database,a.sources,a.output)
