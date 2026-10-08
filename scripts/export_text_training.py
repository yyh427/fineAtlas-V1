#!/usr/bin/env python3
"""Export frozen label and hierarchy-reward applicability for text SFT/RL."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas import FineAtlas

DATASETS=('cub200','fgvc_aircraft','flowers102','pets37','stanford_dogs','stanford_cars')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--dataset',choices=DATASETS,action='append')
    a=p.parse_args()
    with FineAtlas(a.database,relation_view='unified') as tree:
        for dataset in a.dataset or DATASETS:
            print(json.dumps(tree.export_training(dataset,a.output/dataset)),flush=True)

if __name__=='__main__':main()
