"""Ground broad navigation without upgrading ambiguous world equivalence."""
import argparse
import json
from pathlib import Path
from fineatlas import FineAtlas
from fineatlas.source_structure import file_record
from fineatlas.repair_candidate import apply_scope_operations


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--apply',action='store_true');args=p.parse_args()
    r=args.root;db=r/'artifacts/fineatlas.sqlite';operations=[]
    with FineAtlas(db,relation_view='unified') as a:
        def link(ds,cid,parent,relation,docs,basis,**facts):
            native=a.native_class(ds,cid)
            claim={'child_uid':native['uid'],'parent_uid':parent,'relation':relation,
                   'source':'searchable755-primary-navigation','source_version':'20261013'}
            proof={'basis':basis,'source_files':docs,'admitted_claims':[claim],
                'native_source_proof':native['proof'],'original_label':native['label'],
                'world_identity_assertion':False,'retrieved_utc':'2026-10-13',**facts}
            operations.append({'op':'add_relation',**claim,'source_uri':docs[0]['uri'],'proof':proof})
        vpic=json.loads((r/'reports/vpic_bmw_model_receipt.json').read_text())
        docs=[file_record(r/'inputs/primary/vpic_bmw_models.json',vpic['uri']),
              file_record(r/'inputs/primary/bmw_z4_2012.pdf','https://www.press.bmwgroup.com/united-kingdom/article/attachment/T0125655EN_GB/186498')]
        link('stanford_cars','38','vpic-model:452:1725','DEPICTS_DESIGN',docs,
             'AUTHOR_Z4_LABEL_AND_OFFICIAL_2012_MODEL_WITH_NHTSA_MAKE_MODEL_ID',
             official_model_record=vpic['target'],oem_document_scope='UK price list effective March2012; seven listed Z4 variants; no exhaustive author trim/market assertion',
             exact_epa_configuration=False,world_model_is_navigation_not_source_exact=True)
        docs=[file_record(r/'inputs/primary/ncsu_beebalm.html','https://plants.ces.ncsu.edu/plants/monarda-didyma/common-name/bee-balm/'),
              file_record(r/'inputs/primary/ncsu_melissa.html','https://plants.ces.ncsu.edu/plants/melissa-officinalis/'),
              file_record(r/'inputs/primary/flowers_categories.html','https://www.robots.ox.ac.uk/~vgg/data/flowers/102/categories.html')]
        if not all('Lamiaceae' in Path(x['path']).read_text() for x in docs[:2]):
            raise ValueError('Plant family facts not present in saved primary pages')
        link('flowers102','92','wfo:wfo-7000000318','DEPICTS_TYPE',docs,
             'COMMON_NAME_ALTERNATIVES_SHARE_PRIMARY_CONFIRMED_BROAD_FAMILY',
             alternatives=['Monarda species/cultivars','Melissa officinalis historical lexical sense'],
             family='Lamiaceae',correct_genus_or_species='UNKNOWN',
             source_scope_is_broad_name_upper_bound=True,full_author_annotation_range_not_verified=True)
        rev=a._revision
    file=r/'inputs/primary_navigation_operations.json';file.write_text(json.dumps(operations,ensure_ascii=False,indent=2))
    if args.apply:
        result=apply_scope_operations(db,rev,file,package_id='searchable755-primary-navigation-v1')
        (r/'reports/primary_navigation_apply.json').write_text(json.dumps(result,indent=2));print(result)


if __name__=='__main__':main()
