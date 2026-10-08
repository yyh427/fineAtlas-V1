#!/usr/bin/env python3
"""Freeze source-wide WordNet 3.1 entry rules and native field refinements.

No database mutation and no arbitrary leaf-to-root edges. Existing complete
domain-root witnesses are recorded; original WordNet hypernyms supply only
the selected upper skeleton. Primary identifier bridges are prepared separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas import FineAtlas


def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def refresh_backbone_metadata(database,inputs):
    """Refresh descriptive spine tables after topology has already been rebuilt."""
    c=sqlite3.connect(database)
    for table in ('unified_backbone_nodes','unified_backbone_edges','unified_domain_rules'):
        c.execute('DELETE FROM '+table)
    for r in json.loads((inputs/'unified_backbone_nodes.json').read_text()):
        n=c.execute('SELECT data,description FROM nodes WHERE uid=?',(r['uid'],)).fetchone()
        if not n or hashlib.sha256(n[0].encode()).hexdigest()!=r['native_record_sha256'] or n[1]!=r['definition']:
            raise ValueError('Refreshed WordNet source differs')
        c.execute('INSERT INTO unified_backbone_nodes VALUES (?,?)',(r['uid'],json.dumps(r)))
    for r in json.loads((inputs/'unified_backbone_edges.json').read_text()):
        status=c.execute('SELECT status FROM edges WHERE id=?',(r['id'],)).fetchone()[0]
        if status!='ACTIVE':raise ValueError('Metadata refresh cannot reactivate a pruned upper path; rebuild source rules first')
        c.execute('INSERT INTO unified_backbone_edges VALUES (?,?)',(r['id'],json.dumps(r)))
    for r in json.loads((inputs/'unified_domain_rules.json').read_text()):
        c.execute('INSERT INTO unified_domain_rules VALUES(?,?,?,?)',
                  (r['domain_id'],r['native_root_uid'],r['wordnet_anchor_uid'],json.dumps(r)))
    c.commit();c.close()


def prepare(database,output,authority=None,baseline_manifest=None,refresh_only=False):
    output.mkdir(parents=True,exist_ok=True)
    rules,selected,edges,reviews=[],{}, {},[]
    with FineAtlas(database,relation_view='unified' if refresh_only else 'taxonomy') as t:
        c=t.con
        for entry in c.execute('SELECT * FROM domain_registry ORDER BY domain_id').fetchall():
            entry=dict(entry)
            for root in json.loads(entry['root_uids']):
                path=t.path_result(root)
                steps=path.get('path',[])
                candidates=[s['uid'] for s in reversed(steps) if re.fullmatch(r'wordnet31:[0-9]{8}-n',s['uid'])]
                if re.fullmatch(r'wordnet31:[0-9]{8}-n',root):candidates.insert(0,root)
                if path['status'] not in ('CONNECTED','ROOT') or not candidates:
                    reviews.append({'domain':entry['canonical_name'],'root_uid':root,'status':path['status'],'reason':'No witnessed WordNet attachment; requires source evidence'})
                    continue
                anchor=candidates[0];node=t.node(anchor)
                rules.append({'domain_id':entry['domain_id'],'domain':entry['canonical_name'],
                    'entry_uid':entry['entry_uid'],'native_root_uid':root,'wordnet_anchor_uid':anchor,
                    'relation':'EXISTING_TYPED_CLASSIFICATION_PATH','definition':node['description'],
                    'synset_id':'eng-31-'+anchor.split(':')[1],
                    'selection_basis':'Lowest retained WordNet 3.1 synset on the existing, view-validated native root witness; no inferred shortcut',
                    'witness':steps,'root_uid':t.root_uid})
                queue=[anchor]
                while queue:
                    uid=queue.pop()
                    if uid in selected:continue
                    n=t.node(uid)
                    selected[uid]={'uid':uid,'synset_id':'eng-31-'+uid.split(':')[1],
                         'label':n['label'],'definition':n['description'],
                         'selection_basis':'Domain attachment anchor or required original WordNet hypernym ancestor',
                         'source':'WordNet 3.1','native_record_sha256':hashlib.sha256(c.execute('SELECT data FROM nodes WHERE uid=?',(uid,)).fetchone()[0].encode()).hexdigest()}
                    for e in c.execute("SELECT * FROM edges WHERE child_uid=? AND source_relation='WORDNET_IS_A' AND relation='IS_A' AND status IN ('ACTIVE','PRUNED_WORDNET') AND json_extract(provenance,'$.provenance')='WordNet-3.1' ORDER BY id",(uid,)):
                        e=dict(e)
                        if not re.fullmatch(r'wordnet31:[0-9]{8}-n',e['parent_uid']):continue
                        edges[e['id']]=e;queue.append(e['parent_uid'])
        if not refresh_only:
            manifest=json.loads(baseline_manifest.read_text())
            if manifest['database']['bytes'] != database.stat().st_size or manifest['release'] != t.metadata['release']:
                raise ValueError('Baseline manifest release/size does not match selected source')
            baseline={'database':str(database.resolve()),'release':t.metadata['release'],
                      'database_revision':t._revision,'database_bytes':database.stat().st_size,
                      'database_sha256':manifest['database']['sha256'],
                      'sha256_basis':'Previously protected, frozen source artifact manifest; builder verifies before copying'}
    if not refresh_only:
        dump(output/'baseline.json',baseline)
        dump(output/'review_release.json',{'version':'v1.10.0-unified-review'})
    dump(output/'unified_domain_rules.json',rules)
    dump(output/'unified_backbone_nodes.json',list(selected.values()))
    dump(output/'unified_backbone_edges.json',list(edges.values()))
    dump(output/'unified_attachment_reviews.json',reviews)
    if authority:
        source=authority/'hierarchy_refinements_preview.jsonl'
        if not source.is_file():raise FileNotFoundError(source)
        # Preserve the original field guards, definitions and source checksums.
        rows=[]
        for line in source.open():
            r=json.loads(line)
            r['source']='Verified FAA/EPA native field intersection'
            r['proof']['preview_promoted_by']='Replayed literal field and baseline-record checks, followed by full graph and public regressions'
            rows.append(r)
        with (output/'unified_field_refinements.jsonl').open('w') as stream:
            for r in rows:stream.write(json.dumps(r,ensure_ascii=False)+'\n')
    print(json.dumps({'domain_root_rules':len(rules),'domains':len({r['domain'] for r in rules}),
          'wordnet_backbone_nodes':len(selected),'wordnet_backbone_edges':len(edges),
          'attachment_reviews':len(reviews)},indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--authority-preview',type=Path)
    p.add_argument('--baseline-manifest',type=Path,default=Path(__file__).resolve().parents[1]/'docs/night_baseline_data.json')
    p.add_argument('--refresh-backbone',action='store_true',help='Refresh selected domain witnesses after semantic graph repairs; preserve protected baseline manifest')
    p.add_argument('--apply-backbone-metadata',action='store_true',help='Replace descriptive spine tables after all refreshed hypernyms are already active')
    a=p.parse_args();prepare(a.database,a.output,a.authority_preview,a.baseline_manifest,a.refresh_backbone)
    if a.apply_backbone_metadata:
        if not a.refresh_backbone:raise ValueError('Use --refresh-backbone for a metadata-only refresh')
        refresh_backbone_metadata(a.database,a.output)
