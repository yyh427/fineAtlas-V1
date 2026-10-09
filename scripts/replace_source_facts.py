#!/usr/bin/env python3
"""Replace one regenerated adapter's records without altering other frozen facts."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--replacement', type=Path, required=True)
    p.add_argument('--source', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Output exists; choose a new destination')
    old, new = {}, {}
    with a.output.open('x') as out:
        for line in a.input.open():
            row = json.loads(line)
            if row['source'] == a.source:
                old.setdefault(row['uid'], []).append(row)
            else:
                out.write(line)
        for line in a.replacement.open():
            row = json.loads(line)
            if row['source'] != a.source: raise ValueError('Replacement source differs')
            new.setdefault(row['uid'], []).append(row)
            out.write(json.dumps(row,ensure_ascii=False)+'\n')
    def digest(path):
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(8*1024*1024), b''): h.update(block)
        return h.hexdigest()
    report = {'source':a.source,'input_sha256':digest(a.input),'replacement_sha256':digest(a.replacement),
              'output_sha256':digest(a.output),'old_records':sum(map(len,old.values())),
              'new_records':sum(map(len,new.values())),
              'removed_uids':sorted(old.keys()-new.keys()),'added_uids':sorted(new.keys()-old.keys()),
              'changed_retained_uids':sorted(u for u in old.keys()&new.keys() if old[u]!=new[u])}
    a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))


if __name__ == '__main__': main()
