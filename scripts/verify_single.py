#!/usr/bin/env python3
"""Verify the single database's release checksum and SQLite integrity."""
import argparse
import json
from pathlib import Path
import sqlite3
from download_data import digest

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT)
    args = parser.parse_args()
    expected = json.loads((ROOT/'single_download.json').read_text())['database']
    path = args.data_dir / expected['name'] if args.data_dir.is_dir() else args.data_dir
    assert path.stat().st_size == expected['bytes'], 'Database size mismatch'
    assert digest(path) == expected['sha256'], 'Database checksum mismatch'
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
    print('Single database: SHA-256 and SQLite integrity PASS')


if __name__ == '__main__':
    main()
