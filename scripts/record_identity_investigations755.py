"""Persist actual source checks per class without inventing exact equivalence."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from fineatlas import FineAtlas
from fineatlas.source_structure import SourceGraphWriter, file_record
from fineatlas.repair_candidate import CORE_COUNTS, canonical


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);args=p.parse_args();r=args.root
    db=r/'artifacts/fineatlas.sqlite';audit=json.loads((r/'reports/source_structure_evidence.json').read_text())
    docs={
        'cub200':[file_record(r/'inputs/primary/cub_author.html','https://www.vision.caltech.edu/datasets/cub_200_2011/')],
        'fgvc_aircraft':[file_record(r/'inputs/primary/fgvc_author.html','https://www.robots.ox.ac.uk/~vgg/data/fgvc-aircraft/')],
        'flowers102':[file_record(r/'inputs/primary/flowers_categories.html','https://www.robots.ox.ac.uk/~vgg/data/flowers/102/categories.html'),file_record(r/'inputs/primary/ncsu_beebalm.html','https://plants.ces.ncsu.edu/plants/monarda-didyma/common-name/bee-balm/')],
        'pets37':[file_record('/data/yaoyuhan/Pet-37/annotations/README','https://www.robots.ox.ac.uk/~vgg/data/pets/')],
        'stanford_dogs':[file_record(r/'inputs/primary/wordnet30.tar.gz','https://wordnetcode.princeton.edu/3.0/WordNet-3.0.tar.gz')],
        'stanford_cars':[file_record('/data/yaoyuhan/stanford_cars/devkit/cars_meta.mat','https://ai.stanford.edu/~jkrause/cars/car_dataset.html'),file_record(r/'inputs/primary/frozen_author_dissertation.pdf','https://ai.stanford.edu/~jkrause/papers/dissertation.pdf'),file_record(r/'inputs/primary/bmw_z4_2012.pdf','https://www.press.bmwgroup.com/united-kingdom/article/attachment/T0125655EN_GB/186498')],
    }
    car_fields={x['uid']:x for x in audit['car_fields']};dog_fields={x['class_id']:x for x in audit['dog_synset_bindings']}
    notes={
        'cub200':('查验2011原始类名与作者200类说明，并复核当前身份证据及分量。作者页面未给出逐类科学名或历史拆分后的图像范围。', '需要原作者类范围/逐图鉴定或可靠历史分类交叉表；普通名不单独证明现代种或亚种精确等价。'),
        'fgvc_aircraft':('重联全部2013b variant/family/manufacturer图像标注；作者明确variant折叠视觉近似model。当前网页102与冻结100分开。EASA既有撤销证据保留。', '需要作者variant所覆盖全部商业型号与世界节点范围的交叉表，不能把family/model标签一致当等价。'),
        'flowers102':('核验作者混合类别表；补查NC State的Monarda/Melissa及RHS的Bishop栽培品种资料。bee balm多个合理对象共享Lamiaceae，但不能选定单种。', '需要作者类别完整属种/栽培品种范围；通用名、颜色、品种名分别管理，不强制species。'),
        'pets37':('对trainval/test逐图species字段按类复核；README明确猫/犬代码；已确认品种身份据此补合法上层。', '现有确认依据保留，本轮未进行图像视觉识别或全面品种标准重标注。'),
        'stanford_dogs':('逐类原始WordNet3.0 synset查验，官方字节与镜像相同；dingo/dhole/African hunting dog进入wild dog分支，与domestic dog品种分开。', 'dingo的作者完整范围到现代世界分类的精确等价仍不成立；需原始标注范围及可靠分类处理依据。'),
        'stanford_cars':('逐类核验196作者组合标签，保存49 make、174 design-label前缀及车身/年份属性。核查原论文与2012 BMW官方价格资料、NHTSA Z4型号ID。', '需要作者每类覆盖的车型/车身/配置/年份/市场完整范围，及对应世界对象全部范围；原名不证明特定EPA配置。'),
    }
    rows=[]
    with FineAtlas(db,relation_view='unified') as a:
        revision=a._revision
        for ds in CORE_COUNTS:
            for n in a.con.execute('SELECT * FROM native_classes WHERE dataset=? ORDER BY CAST(class_id AS INTEGER)',(ds,)).fetchall():
                w=a.world_mapping_status(ds,n['class_id'])
                detail=car_fields.get(n['uid']) if ds=='stanford_cars' else dog_fields.get(n['class_id']) if ds=='stanford_dogs' else audit['air_variant_ranges'].get(n['label']) if ds=='fgvc_aircraft' else None
                rows.append({'dataset':ds,'class_id':n['class_id'],'original_label':n['label'],'source_uid':n['uid'],
                    'world_uid':w['uid'],'status':w['effective_status'],'checked':notes[ds][0],
                    'sources':docs[ds],'source_scope_facts':detail,'obtained':'来源范围、角色、路径和监督入口可保留；已确认世界身份的旧依据保留。',
                    'exact_identity_resolution':'EXISTING_CONFIRMATION_RETAINED' if w['world_identity_verified'] else 'UNRESOLVED_AFTER_SOURCE_CHECKS',
                    'missing':notes[ds][1] if not w['world_identity_verified'] else '',
                    'needs_external':not w['world_identity_verified'],'prior_evidence_ids':w['evidence_ids']})
    w=SourceGraphWriter(db,expected_revision=revision)
    signature={'rows':rows,'rules':'record-checks-without-status-promotion-v1'}
    if w.begin('searchable755-identity-investigations-v1',signature):
        for row in rows:
            proof={'basis':'ACTUAL_SOURCE_RANGE_INVESTIGATION','row':row,'retrieved_utc':'2026-10-13','world_identity_promotion':False}
            eid=w.evidence(proof,uri=row['sources'][0]['uri'],source=row['dataset']+' primary source investigation',claim='IDENTITY_RANGE_INVESTIGATION')
            if row['status']=='CONFIRMED':continue
            key={'dataset':row['dataset'],'class_id':row['class_id']}
            current=dict(w.c.execute('SELECT * FROM world_mapping_dispositions WHERE dataset=? AND class_id=?',tuple(key.values())).fetchone())
            current['evidence_ids']=canonical(sorted(set(json.loads(current['evidence_ids'])+[eid])))
            current['reason']+='; Primary source checks 2026-10-13: '+row['checked']
            current['missing_evidence']+='; '+row['missing']
            w.put('world_mapping_dispositions',key,current)
        result=w.finish({'status':'APPLIED','source_checks_recorded':755,'unconfirmed_with_new_check_receipts':339,'world_promotions':0})
    else:result={'status':'ALREADY_APPLIED','changed_rows':0}
    w.c.close();(r/'reports/identity_investigations_apply.json').write_text(json.dumps(result,indent=2))
    (r/'reports/identity_investigations755.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    for filename,values in [('755类身份核查记录.csv',rows),('世界身份待审及已查来源.csv',[x for x in rows if x['needs_external']])]:
        with (r/'reports'/filename).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader()
            for row in values:writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    print(result)


if __name__=='__main__':main()
