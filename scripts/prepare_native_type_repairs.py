#!/usr/bin/env python3
"""Recover retained transport types from the original WordNet noun graph.

The reviewed vocabulary names physical or operational types. Named products,
maintenance condition, possession and individual race outcomes are excluded.
No new source UID or name-based identity merge is created.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

TRANSPORT_TYPES = frozenset('airbus airliner ambulance amphibian autogiro balloon barrage_balloon beach_wagon berlin biplane blimp brougham cab cargo_helicopter compact cruise_missile cruiser delta_wing dive_bomber double-prop fanjet fighter glider hang_glider hardtop hatchback hot-air_balloon hot_rod interceptor jeep jet jetliner jumbojet kamikaze kite_balloon meteorological_balloon minicab minicar minivan multiengine_airplane narrowbody_aircraft orthopter pace_car panda_car pilot_balloon propeller_plane propjet racer shooting_brake shuttle_helicopter single_prop single-rotor_helicopter ski-plane skyhook stealth_aircraft stealth_bomber stealth_fighter stock_car subcompact tanker_plane touring_car trial_balloon twinjet widebody_aircraft'.split())

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',required=True,type=Path)
    p.add_argument('--wordnet',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    c=sqlite3.connect(a.database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    c.row_factory=sqlite3.Row
    w=sqlite3.connect(a.wordnet.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    snapshot=hashlib.sha256(a.wordnet.read_bytes()).hexdigest()
    rows=[]
    for n in c.execute("SELECT * FROM nodes WHERE visibility='PRUNED_WORDNET' ORDER BY uid"):
        if n['label'] not in TRANSPORT_TYPES:continue
        if n['label']=='stock_car' and 'racing car' not in n['description']:continue
        native=w.execute('SELECT label,gloss FROM nodes WHERE uid=?',(n['uid'],)).fetchone()
        if not native or native[1]!=n['description']:
            raise ValueError('Retained definition differs from native WordNet: '+n['uid'])
        parents=sorted(x[0] for x in w.execute('SELECT parent_uid FROM edges WHERE child_uid=?',(n['uid'],)))
        if not parents:raise ValueError('Native type lacks a source hypernym')
        for parent in parents:
            pn=c.execute('SELECT visibility,label FROM nodes WHERE uid=?',(parent,)).fetchone()
            if not pn or pn['visibility'] not in {'ACTIVE','PRUNED_WORDNET'} or pn['visibility']=='PRUNED_WORDNET' and pn['label'] not in TRANSPORT_TYPES:
                raise ValueError('Reviewed native type requires an unavailable source parent: '+parent)
        rows.append({'op':'activate_native_type','uid':n['uid'],'definition':native[1],
                     'parents':parents,'source':'Princeton WordNet native transport hypernyms',
                     'uri':'https://wordnet.princeton.edu/',
                     'proof':{'basis':'RETAINED_GENERIC_TRANSPORT_TYPE_WITH_EXACT_NATIVE_WORDNET_HYPERNYMS',
                              'native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),
                              'wordnet_snapshot_sha256':snapshot,'native_gloss':native[1],
                              'native_hypernyms':parents,'license':'Princeton WordNet license; attribution retained'}})
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(''.join(json.dumps(r,sort_keys=True,ensure_ascii=False)+'\n' for r in rows))
    print(json.dumps({'restored_native_types':len(rows),'native_hypernyms':sum(len(r['parents']) for r in rows),'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()}))

if __name__=='__main__':main()
