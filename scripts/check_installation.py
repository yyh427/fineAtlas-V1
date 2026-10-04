#!/usr/bin/env python3
"""Check the downloaded graph's complete dependencies and representative queries."""
import argparse
import json
from pathlib import Path
from fineatlas import FineAtlas


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[1])
    args = p.parse_args()
    with FineAtlas(args.data_dir) as graph:
        examples = [('wikidata:Q321098','laser diode'),
                    ('wikidata:Q642345','slow cooker'),
                    ('wikidata:Q16860991','disanxian')]
        for uid, label in examples:
            assert graph.node(uid)['label'] == label, uid
            assert uid in {node['uid'] for node in graph.exact(label)}, label
            path = graph.path(uid)
            assert path and path[-1]['uid'] == uid, uid
            assert len({node['uid'] for node in path}) == len(path), 'repeated path node'
        assert graph.search('ceramic capacitor')[0]['uid'] == 'wikidata:Q337701'
        assert 'semiconductor diode' in {node['label'] for node in graph.neighbors('wikidata:Q321098','parents')}
        target = graph.target('cub200','1')
        assert target and target['target_uid'] == 'avilist:phoebastria nigripes'
        assert graph.domain('minerals')['entry_uid']=='fineatlas-domain:minerals'
        assert graph.domain_children('rivers')
        assert graph.node('eunis2021:T')['attributes']['native_level']==1
        assert graph.path('ima-mineral:quartz')
        print(json.dumps({'status':'PASS','graph':graph.stats(),'queries_checked':examples},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
