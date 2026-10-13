"""Prepare and apply separately journaled, evidence-bound local source scopes."""
import argparse
import json
from pathlib import Path
from fineatlas import FineAtlas
from fineatlas.source_structure import prepare_source_graph, apply_source_graph
from fineatlas.repair_candidate import apply_scope_operations


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--apply',action='store_true')
    a=p.parse_args();db=a.root/'artifacts/fineatlas.sqlite'
    plan_file=a.root/'inputs/source_graph_plan.json';links_file=a.root/'inputs/source_existing_connections.json'
    if not plan_file.exists():
        with FineAtlas(db,relation_view='unified') as atlas:
            plan,links,audit=prepare_source_graph(atlas,a.root)
        for file,value in [(plan_file,plan),(links_file,links),(a.root/'reports/source_structure_evidence.json',audit)]:
            file.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    if a.apply:
        with FineAtlas(db) as atlas:revision=atlas._revision
        result=apply_source_graph(db,revision,plan_file)
        (a.root/'reports/source_concepts_apply.json').write_text(json.dumps(result,indent=2))
        with FineAtlas(db) as atlas:revision=atlas._revision
        result=apply_scope_operations(db,revision,links_file,package_id='searchable755-existing-connections-v1')
        (a.root/'reports/source_connections_apply.json').write_text(json.dumps(result,indent=2))
        print(result,flush=True)


if __name__=='__main__':main()
