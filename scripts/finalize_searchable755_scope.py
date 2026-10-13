"""Journal task-unit declarations, official source provenance and entry bounds."""
import argparse
import hashlib
import json
from pathlib import Path
from fineatlas import FineAtlas
from fineatlas.source_structure import SourceGraphWriter, file_record
from fineatlas.repair_candidate import canonical, CORE_COUNTS


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);args=p.parse_args()
    r=args.root;db=r/'artifacts/fineatlas.sqlite'
    audit=json.loads((r/'reports/source_structure_evidence.json').read_text())
    official=json.loads((r/'reports/wordnet_official_bytes_match.json').read_text())
    docs=[file_record(r/'inputs/primary/wordnet30.tar.gz',official['official_uri']),
          file_record(r/'inputs/primary/bmw_z4_2012.pdf','https://www.press.bmwgroup.com/united-kingdom/article/attachment/T0125655EN_GB/186498'),
          file_record(r/'inputs/primary/fgvc_author.html','https://www.robots.ox.ac.uk/~vgg/data/fgvc-aircraft/'),
          file_record(r/'inputs/primary/flowers_categories.html','https://www.robots.ox.ac.uk/~vgg/data/flowers/102/categories.html'),
          file_record(r/'inputs/primary/ncsu_beebalm.html','https://plants.ces.ncsu.edu/plants/monarda-didyma/common-name/bee-balm/')]
    with FineAtlas(db) as a:rev=a._revision
    w=SourceGraphWriter(db,expected_revision=rev)
    inputs={'audit_sha256':hashlib.sha256((r/'reports/source_structure_evidence.json').read_bytes()).hexdigest(),
            'official':official,'source_files':docs,'scope_rules':'grounded-mixed-range-v1'}
    if not w.begin('searchable755-unit-and-entry-contract-v1',inputs):
        print('ALREADY_APPLIED');w.c.close();return
    proof={'basis':'OFFICIAL_SOURCE_BYTES_AND_AUTHOR_UNIT_DECLARATIONS','official':official,
           'source_files':docs,'retrieved_utc':'2026-10-13','world_identity_assertion':False}
    eid=w.evidence(proof,uri=official['official_uri'],source='Official WordNet and publisher source contracts',claim='SOURCE_UNIT_AND_OFFICIAL_BYTES')
    fields={x['uid']:x for x in audit['car_fields']}
    wild={'118':'source_dingo_label','119':'source_wild_canid_species_label','120':'source_wild_canid_species_label'}
    units={'cub200':'source_bird_annotation_class','fgvc_aircraft':'publisher_visual_variant',
           'flowers102':'heterogeneous_flower_annotation_class','pets37':'publisher_breed_label',
           'stanford_dogs':'source_breed_label','stanford_cars':'author_make_design_body_year_annotation'}
    for n in w.c.execute('SELECT * FROM native_classes').fetchall():
        if n['dataset'] not in CORE_COUNTS:continue
        old=w.c.execute('SELECT * FROM node_profiles WHERE uid=?',(n['uid'],)).fetchone()
        row=dict(old) if old else {'uid':n['uid'],'node_kind':n['role'],'domain':n['domain'],
                                    'source_uri':'','evidence_id':eid,'attributes':'{}'}
        attrs=json.loads(row['attributes']);attrs['source_unit']=wild.get(n['class_id'],units[n['dataset']]) if n['dataset']=='stanford_dogs' else units[n['dataset']]
        attrs['source_unit_evidence_ids']=sorted(set(attrs.get('source_unit_evidence_ids',[])+json.loads(n['evidence_ids'])+[eid]))
        if n['uid'] in fields:attrs['source_annotation_fields']=fields[n['uid']]
        row['attributes']=canonical(attrs);w.put('node_profiles',{'uid':n['uid']},row)
    # Original cars include pickups/vans; the automobile-only entry cannot
    # encompass them. Expose the documented road-vehicle boundary explicitly.
    row=dict(w.c.execute("SELECT * FROM domain_registry WHERE canonical_name='cars'").fetchone())
    roots=json.loads(row['root_uids']);roots=sorted(set(roots+['wordnet31:03796768-n']))
    row.update(root_uids=canonical(roots),label='cars and road motor vehicles',
        description='Author cars scope includes pickups/vans; automobile and road motor-vehicle entrances; no identity equivalence inferred')
    w.put('domain_registry',{'domain_id':row['domain_id']},row)
    w.put('domain_entry_roots',{'domain':'cars','root_uid':'wordnet31:03796768-n'},
          {'domain':'cars','root_uid':'wordnet31:03796768-n'})
    w.meta('searchable755_ready',True)
    w.meta('searchable755_acceptance_semantics','Structural paths and model-issued dynamic ranges, separate from recognition')
    result=w.finish({'status':'APPLIED','native_unit_declarations':755,'cars_entry_root_added':1,
                     'official_wordnet_bytes_verified':True,'world_identities_promoted':0})
    (r/'reports/unit_and_entry_apply.json').write_text(json.dumps(result,indent=2));print(result)
    w.c.close()


if __name__=='__main__':main()
