"""Create an independently writable, consistent SQLite backup; never copy sidecars."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.destination.exists():
        raise SystemExit('Destination exists: refusing to replace it')
    temporary = args.destination.with_suffix('.snapshot-in-progress')
    if temporary.exists():
        raise SystemExit('Incomplete snapshot exists: inspect before retry')
    before = args.source.stat()
    started = time.time()
    last = started
    with sqlite3.connect(args.source.resolve().as_uri() + '?mode=ro') as source:
        source.execute('PRAGMA query_only=ON')
        source.execute('PRAGMA cache_size=-8192')
        with sqlite3.connect(temporary) as destination:
            def progress(status: int, remaining: int, total: int) -> None:
                nonlocal last
                now = time.time()
                if now - last >= 15 or remaining == 0:
                    print(json.dumps({'remaining_pages': remaining, 'total_pages': total,
                                      'elapsed_seconds': round(now - started, 1)}), flush=True)
                    last = now
                time.sleep(0.005)
            source.backup(destination, pages=8192, progress=progress, sleep=0.05)
            revision = destination.execute(
                "SELECT value FROM metadata WHERE key='database_revision'").fetchone()[0]
            pages = destination.execute('PRAGMA page_count').fetchone()[0]
    os.replace(temporary, args.destination)
    after = args.source.stat()
    receipt = {'method': 'sqlite3.Connection.backup; source mode=ro',
               'source': str(args.source), 'destination': str(args.destination),
               'database_revision': json.loads(revision), 'page_count': pages,
               'size': args.destination.stat().st_size,
               'elapsed_seconds': time.time() - started,
               'source_stat_before': {'size': before.st_size, 'mtime_ns': before.st_mtime_ns,
                                      'inode': before.st_ino},
               'source_stat_after': {'size': after.st_size, 'mtime_ns': after.st_mtime_ns,
                                     'inode': after.st_ino}}
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
