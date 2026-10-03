from __future__ import annotations

import argparse
import json
from .api import FineAtlas


def main() -> None:
    parser = argparse.ArgumentParser(description='Query the complete FineAtlas-V1 graph (V33 snapshot).')
    parser.add_argument('--data-dir', help='Directory containing bundle.json and data/')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('stats')
    p = sub.add_parser('node'); p.add_argument('uid')
    p = sub.add_parser('exact'); p.add_argument('text'); p.add_argument('--limit', type=int, default=20)
    p = sub.add_parser('search'); p.add_argument('text'); p.add_argument('--domain'); p.add_argument('--limit', type=int, default=20)
    p = sub.add_parser('neighbors'); p.add_argument('uid'); p.add_argument('--direction', choices=['parents','children'], default='children'); p.add_argument('--limit', type=int, default=20); p.add_argument('--include-auxiliary', action='store_true')
    p = sub.add_parser('path'); p.add_argument('uid'); p.add_argument('--anchor', action='append'); p.add_argument('--max-depth', type=int, default=32)
    p = sub.add_parser('equivalents'); p.add_argument('uid')
    p = sub.add_parser('target'); p.add_argument('dataset'); p.add_argument('class_id')
    args = parser.parse_args()
    with FineAtlas(args.data_dir) as graph:
        if args.command == 'stats': result = graph.stats()
        elif args.command == 'node': result = graph.node(args.uid)
        elif args.command == 'exact': result = graph.exact(args.text, args.limit)
        elif args.command == 'search': result = graph.search(args.text, args.limit, args.domain)
        elif args.command == 'neighbors': result = graph.neighbors(args.uid, args.direction, args.limit, not args.include_auxiliary)
        elif args.command == 'path': result = graph.path(args.uid, args.anchor, args.max_depth)
        elif args.command == 'equivalents': result = graph.equivalents(args.uid)
        else: result = graph.target(args.dataset, args.class_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
