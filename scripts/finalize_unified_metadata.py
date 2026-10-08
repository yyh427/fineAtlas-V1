#!/usr/bin/env python3
"""Freeze unified query policies after graph checks and before index building."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.migration import digest_file

def finalize(database,inputs):
    c=sqlite3.connect(database);c.row_factory=sqlite3.Row
    meta={r[0]:json.loads(r[1]) for r in c.execute('SELECT * FROM metadata')}
    if not meta.get('unified_ready') or not meta.get('usability_indexes_ready'):
        raise ValueError('Full unified graph recomputation must pass first')
    if meta.get('browse_indexes_ready'):
        raise ValueError('Freeze policies before building browser indexes')
    c.execute('''CREATE TABLE IF NOT EXISTS unified_wordnet_usage(
        uid TEXT PRIMARY KEY,synset_id TEXT,label TEXT,definition TEXT,
        selection_basis TEXT,source_record_sha256 TEXT)''')
    c.execute('DELETE FROM unified_wordnet_usage')
    selected={r[0] for r in c.execute('SELECT uid FROM unified_backbone_nodes')}
    for n in c.execute('''SELECT n.uid,n.label,n.description,n.data FROM nodes n JOIN view_roots v
        ON v.component_id=n.component_id AND v.view='unified'
        WHERE n.uid GLOB 'wordnet31:????????-n' AND n.visibility='ACTIVE' ''').fetchall():
        if not n['description']:raise ValueError('Admitted WordNet noun lacks its definition: '+n['uid'])
        c.execute('INSERT INTO unified_wordnet_usage VALUES(?,?,?,?,?,?)',
                  (n['uid'],'eng-31-'+n['uid'].split(':')[1],n['label'],n['description'],
                   'Selected upper domain skeleton or required hypernym' if n['uid'] in selected else
                   'Retained WordNet-native fine concept admitted by original hypernym/typed native classification contracts; not an invented upper attachment',
                   hashlib.sha256(n['data'].encode()).hexdigest()))
    policies={
        'cub200':{'policy':'classification','source_scope':'avilist',
                  'requirement':'species','coarse_roots':['wordnet31:01505702-n','v4root:bird','ott:81461']},
        'fgvc_aircraft':{'policy':'design','requirement':'model_design',
                         'coarse_roots':['wordnet31:02689427-n']},
        'flowers102':{'policy':'classification','requirement':'species',
                      'coarse_roots':['wordnet31:00017402-n']},
        'pets37':{'policy':'classification','requirement':'hierarchy',
                  'coarse_roots':['wordnet31:00015568-n']},
        'stanford_dogs':{'policy':'classification','requirement':'hierarchy',
                        'coarse_roots':['wordnet31:02086723-n']},
        'stanford_cars':{'policy':'configuration','requirement':'configuration',
                        'coarse_roots':['wordnet31:02961779-n']},
    }
    # The dog root ID is verified from the actual root record, never guessed
    # from offsets of another WordNet version.
    for config in policies.values():
        for root in config['coarse_roots']:
            if not c.execute("SELECT 1 FROM nodes WHERE uid=? AND visibility='ACTIVE'",(root,)).fetchone():
                raise ValueError('Missing policy floor '+root)
    raw={'schema':'FINEATLAS_UNIFIED_POLICY_V1','datasets':policies,
         'wordnet_version':'3.1','identity_cost':0,
         'lca':'all lowest common identity-group ancestors',
         'distance':'minimum upward arc sum through informative LCAs under one explicit typed policy',
         'cross_domain_reward':'NOT_CALIBRATED; generic UID query is navigation only',
         'annotation_scope_review':'Skip hierarchy term; retain category reward',
         'identity_lineage_conflict':'Mixed source roles at an endpoint or ancestor make the hierarchy term inapplicable; no arbitrary maximum penalty',
         'source_scope':'AviList concept hierarchy selected for CUB; verified identities resolve other UIDs into that source',
         'source_views':'source_hierarchy exposes direct original declarations; legacy strict/taxonomy/membership retained'}
    policy_sha=hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()
    freeze={'inputs':{p.name:digest_file(p) for p in sorted(inputs.iterdir()) if p.is_file()},
            'code':{str(p.relative_to(Path(__file__).resolve().parents[1])):digest_file(p)
                    for p in sorted((Path(__file__).resolve().parents[1]/'src/fineatlas').glob('*.py'))},
            'source_graph_revision':meta['database_revision'],'policy_sha256':policy_sha}
    revision=hashlib.sha256(json.dumps(freeze,sort_keys=True).encode()).hexdigest()
    baseline=json.loads((inputs/'baseline.json').read_text())
    for key,value in {'unified_reward_policies':policies,'unified_policy_definition':raw,
        'unified_policy_sha256':policy_sha,'unified_frozen_build_manifest':freeze,
        'unified_source_graph_revision':meta['database_revision'],
        'database_revision':revision,'baseline_release':baseline['release'],
        'source_graph_changed':True,'default_relation_view':'unified',
        'unified_wordnet_usage_table':'unified_wordnet_usage',
        'unified_evidence_capture_date':'2026-10-08',
        'browse_indexes_ready':False,'browse_parent_revision':revision}.items():
        c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(key,json.dumps(value)))
    c.commit();c.close();return {'revision':revision,'manifest':freeze}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=finalize(a.database,a.inputs)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(result['revision'],flush=True)
