#!/usr/bin/env python3
"""Check the downloaded graph's complete dependencies and representative queries."""
import argparse
import json
from pathlib import Path
from fineatlas import FineAtlas
import fineatlas


def validate_laser_parent(parents, unified):
    """Check the admitted professional class, rather than an old display label."""
    if not unified:
        assert 'semiconductor diode' in {node['label'] for node in parents}
        return None
    uid='hierarchy-type:semiconductor_diodes-led'
    matches=[node for node in parents if node.get('uid') == uid]
    assert len(matches) == 1, 'Missing admitted light-emitting semiconductor diode parent'
    parent=matches[0];edge=parent.get('edge',{})
    assert parent.get('node_kind') == 'CLASS', 'Professional diode parent is not a classification'
    assert edge.get('relation') == 'IS_A' and edge.get('status') == 'ACTIVE', 'Diode parent is not an active classification edge'
    assert edge.get('child_uid') == 'wikidata:Q321098' and edge.get('parent_uid') == uid, 'Diode parent edge endpoints differ'
    assert edge.get('navigation_role') == 'SOURCE_VALIDATED', 'Diode parent lacks source admission'
    return uid


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--manifest',type=Path,help='Explicit manifest for a separate preserved installation')
    args = p.parse_args()
    from download_single import default_manifest, verify_revision
    from verify_unified_install import validate_install_receipt, validate_runtime_install, validate_installed_sdk
    manifest=json.loads((args.manifest or default_manifest()).read_text())
    database=args.data_dir/manifest['database']['name']
    validate_install_receipt(database,manifest)
    verify_revision(database,manifest)
    if manifest.get('default_relation_view') == 'unified':
        validate_installed_sdk(fineatlas)
    with FineAtlas(args.data_dir) as graph:
        if manifest.get('default_relation_view') == 'unified':
            validate_runtime_install(graph.metadata,manifest,fineatlas)
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
        parent_uid=validate_laser_parent(graph.neighbors('wikidata:Q321098','parents'),
                                         manifest.get('default_relation_view') == 'unified')
        if parent_uid:
            parent_path=graph.path(parent_uid)
            assert parent_path and parent_path[-1]['uid'] == parent_uid, 'Admitted diode parent lacks a legal root path'
        target = graph.target('cub200','1')
        assert target and target['target_uid'] == 'avilist:phoebastria nigripes'
        assert graph.domain('minerals')['entry_uid']=='fineatlas-domain:minerals'
        assert graph.domain_children('rivers')
        assert graph.node('eunis2021:T')['attributes']['native_level']==1
        assert graph.path('ima-mineral:quartz')
        print(json.dumps({'status':'PASS','release':manifest['release'],
                          'database_revision':graph.metadata.get('database_revision'),
                          'database_sha256':manifest['database']['sha256'],
                          'sdk_version':fineatlas.__version__,'sdk_module':str(Path(fineatlas.__file__).resolve()),
                          'default_relation_view':graph.relation_view,
                          'graph':graph.stats(),'queries_checked':examples},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
