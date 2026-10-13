"""Generic phrase/issued-handle scope and pagination acceptance; no images or gold."""
from pathlib import Path
import json
from fineatlas.experiment import FineAtlasExperimentTool


def main():
    p=__import__('argparse').ArgumentParser();p.add_argument('--root',type=Path,required=True)
    r=p.parse_args().root
    cases=[('stanford_cars','BMW'),('stanford_cars','Audi'),('stanford_cars','Chevrolet'),
           ('fgvc_aircraft','Boeing aircraft'),('fgvc_aircraft','Airbus aircraft'),
           ('stanford_dogs','toy dog'),('stanford_dogs','wild dog'),('stanford_dogs','terrier'),
           ('pets37','domestic cat'),('pets37','dog'),('flowers102','Dahlia'),
           ('flowers102','Rosa'),('flowers102','Lamiaceae'),('cub200','Mimidae'),('cub200','Pelecanus')]
    records=[];errors=[];public=[]
    with FineAtlasExperimentTool(str(r/'artifacts/run_config.json')) as tool:
        entries=tool.entries();wire=tool.candidate_wire(entries)
        assert 'class_id' not in wire and 'wordnet31:' not in wire and 'stanford-cars-' not in wire
        for ds,text in cases:
            initial=tool.query(text,dataset=ds,limit=30)
            pool=initial['navigation_candidates']+initial['candidates']
            # Generic, model-visible navigation descriptors; no gold/source ID.
            # Do not treat a source-scoped taxonomy field as an equivalent
            # world anchor. Inspect the first issued type alternatives instead.
            types=[x for x in pool if x['role'] in ['CLASS','BIOLOGICAL_VARIANT','MODEL','MODEL_FAMILY','TAXON']]
            exact=[x for x in types if x['label'].casefold().replace('_',' ')==text.casefold()]
            # Both answer and navigation rows can be navigated. Retain
            # same-name alternatives; a source field is not an identity proof.
            anchors=exact[:16] or types[:4]
            if not anchors:errors.append({'query':text,'error':'No model-issued anchor'});continue
            result=tool.scope([x['handle'] for x in anchors],dataset=ds,limit=80)
            handles=tool.allowed_choices(result);feedback=tool.candidate_wire(result)
            assert 'class_id' not in feedback and ':label:' not in feedback and ':category:' not in feedback
            ids=[x['presentation_key'] for x in result['candidates']]
            assert len(ids)==len(set(ids))
            allkeys=list(ids);cursor=result['next_cursor'];page_count=1
            while cursor:
                nextpage=tool.scope([x['handle'] for x in anchors],dataset=ds,limit=80,cursor=cursor)
                assert tool.allowed_choices(nextpage)==tuple(x['handle'] for x in nextpage['candidates'])
                allkeys.extend(x['presentation_key'] for x in nextpage['candidates']);cursor=nextpage['next_cursor'];page_count+=1
                assert page_count<1000
            assert len(allkeys)==len(set(allkeys))
            expanded=tool.scope(anchors[0]['handle'],dataset=ds,limit=20,expand=True)
            assert tool.allowed_choices(expanded)==tuple(x['handle'] for x in expanded['candidates'])
            original=tool.scope([x['handle'] for x in anchors],dataset=ds,limit=10)
            assert [x['uid'] for x in original['candidates']]==[x['uid'] for x in result['candidates'][:10]]
            record={'dataset':ds,'model_query':text,'anchors_chosen_from_public_response':[x['label'] for x in anchors],
                    'eligible_answers_first_page':len(handles),'unique_range_candidates':len(allkeys),
                    'pages':page_count,'duplicates':0,'scan_complete':result['retrieval_diagnostics']['scan_complete'],
                    'answer_roles':[x['role'] for x in result['candidates']], 'model_recognition_measured':False}
            record['native_answers_first_page']=sum(x['native_answer_eligible'] for x in result['candidates'])
            record['incomplete_reasons']=result['retrieval_diagnostics']['incomplete_reasons']
            record['bounded_partial']=not record['scan_complete']
            bounded_valid=(record['bounded_partial'] and record['native_answers_first_page']>0
                and bool(record['incomplete_reasons']) and
                set(record['incomplete_reasons']).issubset({'NODE_BUDGET','EDGE_BUDGET'}))
            records.append(record);public.append({'query':text,'feedback':feedback})
            print(json.dumps(record,ensure_ascii=False),flush=True)
            (r/'reports/model_scope_checkpoint.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
            if not handles or (record['bounded_partial'] and not bounded_valid):errors.append(record)
        # Explicit root expansion sanity: source maker navigation must be visible.
        car_entry=next(x for x in entries['navigation_candidates'] if x['label']=='cars and road motor vehicles')
        expanded=tool.scope(car_entry['handle'],dataset='stanford_cars',limit=20,expand=True,node_budget=100000,edge_budget=500000)
        root_navigation=list(expanded['navigation_candidates']); root_cursor=expanded['next_cursor']; root_pages=1
        while root_cursor:
            page=tool.scope(car_entry['handle'],dataset='stanford_cars',limit=20,expand=True,cursor=root_cursor,node_budget=100000,edge_budget=500000)
            root_navigation.extend(page['navigation_candidates']);root_cursor=page['next_cursor'];root_pages+=1
            assert root_pages<1000
        motor_entry=next(x for x in root_navigation if 'motor' in x['label'].lower())
        maker_page=tool.scope(motor_entry['handle'],dataset='stanford_cars',limit=80,expand=True,
            target_granularity=['source_make_scope'],node_budget=100000,edge_budget=500000)
        assert any('BMW' in x['label'] for x in maker_page['navigation_candidates'])
        root_probe={'public_labels_first20':[x['label'] for x in expanded['navigation_candidates']],
                    'scan_complete':expanded['retrieval_diagnostics']['scan_complete'], 'total_navigation_choices':len(root_navigation), 'pages':root_pages, 'typed_maker_navigation_count':len(maker_page['navigation_candidates']), 'BMW_present_in_paged_range':True}
        with __import__('contextlib').suppress(ValueError):
            # A UID string must never be accepted as an issued anchor handle.
            tool.scope('stanford-cars-2013:class:38')
            raise AssertionError('Gold UID anchor was accepted')
    result={'passed':not errors,'records':records,'errors':errors,'root_expansion':root_probe,
            'scope':'15 generic phrase -> issued handles -> range/expand/pagination/constraints; no images',
        'complete_ranges':sum(x['scan_complete'] for x in records),
        'bounded_partial_ranges':[x['model_query'] for x in records if x['bounded_partial']],
            'database_revision':tool.config.database_revision,'model_recognition_measured':False}
    (r/'reports/model_scope_acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (r/'reports/model_scope_public_feedback.json').write_text(json.dumps(public,ensure_ascii=False,indent=2))
    print(json.dumps({'passed':result['passed'],'cases':len(records),'errors':errors},ensure_ascii=False))
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
