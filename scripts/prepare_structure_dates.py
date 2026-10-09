#!/usr/bin/env python3
"""Freeze correction of candidate-only legacy source-date placeholders."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.evidence_dates import prepare_evidence_dates

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('checkpoint','baseline','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare_evidence_dates(a.checkpoint,a.baseline,a.output)))
