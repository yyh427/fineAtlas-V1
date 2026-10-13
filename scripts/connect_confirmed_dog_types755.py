"""Use original sense pointers and exact full parent definitions, never names alone."""
import argparse
import json
from pathlib import Path
from fineatlas import FineAtlas
from fineatlas._text import norm
from fineatlas.repair_candidate import apply_scope_operations
from fineatlas.source_structure import file_record


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--apply',action='store_true');args=p.parse_args()
    r=args.root;db=r/'artifacts/fineatlas.sqlite'
    plan=json.loads((r/'inputs/source_graph_plan.json').read_text())
    senses={n['source_synset']['offset']:n['source_synset'] for n in plan['nodes'] if 'source_synset' in n}
    source=file_record(r/'inputs/primary/wordnet30.tar.gz','https://wordnetcode.princeton.edu/3.0/WordNet-3.0.tar.gz')
    operations=[];audit=[];matched={}
    with FineAtlas(db,relation_view='unified') as a:
        revision=a._revision
        for native in a.con.execute("SELECT * FROM native_classes WHERE dataset='stanford_dogs'").fetchall():
            world=a.world_mapping_status('stanford_dogs',native['class_id'])
            raw=json.loads(native['proof'])['increment_native_record']['raw_record'];syn=raw['native_synset'].removeprefix('n')
            if not world['world_identity_verified']:
                audit.append({'class_id':native['class_id'],'status':'UNCONFIRMED_WORLD_NOT_CONNECTED','world_status':world['effective_status']});continue
            for parent in senses[syn]['parents']:
                if parent not in senses:
                    audit.append({'class_id':native['class_id'],'parent':parent,'status':'ORIGINAL_SECONDARY_PARENT_NEEDS_SEPARATE_SOURCE_CHECK'});continue
                record=senses[parent]
                if parent not in matched:
                    wanted={norm(w) for w in record['lemmas']};matches=[]
                    for node in a.exact(record['lemmas'][0].replace('_',' '),100):
                        if not node['uid'].startswith('wordnet31:') or node['node_kind']!='CLASS':continue
                        words={norm(x['name']) for x in a.aliases(node['uid'],100) if x['source']=='wordnet31'}
                        if words==wanted and node['description']==record['gloss']:
                            matches.append({'uid':node['uid'],'gloss':node['description'],'lemmas':sorted(words),
                                            'source':node['source'],'identity':a._presentation_identity(node['uid'])})
                    matched[parent]=matches
                matches=matched[parent]
                if len(matches)!=1 or matches[0]['identity']['status']!='ACCEPTED':
                    audit.append({'class_id':native['class_id'],'parent':parent,'status':'FULL_PARENT_SENSE_CROSS_VERSION_MATCH_NOT_UNIQUE','matches':matches});continue
                target=matches[0]
                claim={'child_uid':world['uid'],'parent_uid':target['uid'],'relation':'IS_A',
                       'source':'searchable755-confirmed-dog-parent','source_version':'20261013'}
                proof={'basis':'CONFIRMED_OBJECT_IDENTITY_WITH_ORIGINAL_SYNSET_HYPERNYM_AND_EXACT_FULL_PARENT_SENSE',
                    'source_files':[source],'admitted_claims':[claim],'original_class_id':native['class_id'],
                    'original_source_uid':native['uid'],'original_sense':senses[syn],
                    'original_parent_sense':record,'current_canonical_parent':target,
                    'world_full_scope_evidence_ids':world['evidence_ids'],'world_identity_promotion':False,
                    'semantic_relation':'WordNet lexical type inclusion, not kennel-club group or evolutionary lineage',
                    'retrieved_utc':'2026-10-13'}
                operations.append({'op':'add_relation',**claim,'source_uri':source['uri'],'proof':proof})
                audit.append({'class_id':native['class_id'],'world_uid':world['uid'],'parent':target['uid'],
                              'status':'GROUNDED_FULL_PARENT_SENSE_MATCH','source_parent_sense':parent})
    f=r/'inputs/confirmed_dog_parent_operations.json';f.write_text(json.dumps(operations,ensure_ascii=False,indent=2))
    (r/'reports/confirmed_dog_parent_evidence.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    if args.apply:
        result=apply_scope_operations(db,revision,f,package_id='searchable755-confirmed-dog-parents-v1')
        (r/'reports/confirmed_dog_parents_apply.json').write_text(json.dumps(result,indent=2));print(result)
    else:print('grounded connections',len(operations),'isolated records',len([x for x in audit if x['status']!='GROUNDED_FULL_PARENT_SENSE_MATCH']))


if __name__=='__main__':main()
