from __future__ import annotations

import argparse
import json
from .api import FineAtlas


def main() -> None:
    parser = argparse.ArgumentParser(description='Query the FineAtlas V1 SQLite database.')
    parser.add_argument('--data-dir', help='SQLite file or downloaded data directory')
    parser.add_argument('--view', choices=['wordnet','all'], help='Navigation view (default: wordnet)')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('stats')
    sub.add_parser('datasets')
    sub.add_parser('domains')
    p = sub.add_parser('domain'); p.add_argument('name')
    p = sub.add_parser('domain-children'); p.add_argument('name'); p.add_argument('--limit',type=int,default=20)
    p = sub.add_parser('instances'); p.add_argument('uid'); p.add_argument('--limit', type=int, default=20); p.add_argument('--direct', action='store_true')
    p = sub.add_parser('relations'); p.add_argument('uid'); p.add_argument('--relation'); p.add_argument('--direction', choices=['outgoing','incoming'], default='outgoing'); p.add_argument('--limit', type=int, default=20)
    p = sub.add_parser('node'); p.add_argument('uid')
    p = sub.add_parser('connection-status'); p.add_argument('uid')
    p = sub.add_parser('exact'); p.add_argument('text'); p.add_argument('--limit', type=int, default=20); p.add_argument('--node-kind')
    p = sub.add_parser('search'); p.add_argument('text'); p.add_argument('--domain'); p.add_argument('--limit', type=int, default=20); p.add_argument('--node-kind')
    p = sub.add_parser('neighbors'); p.add_argument('uid'); p.add_argument('--direction', choices=['parents','children'], default='children'); p.add_argument('--limit', type=int, default=20); p.add_argument('--include-auxiliary', action='store_true')
    p = sub.add_parser('path'); p.add_argument('uid'); p.add_argument('--anchor', action='append'); p.add_argument('--max-depth', type=int, default=256)
    p = sub.add_parser('equivalents'); p.add_argument('uid')
    p = sub.add_parser('target'); p.add_argument('dataset'); p.add_argument('class_id')
    args = parser.parse_args()
    with FineAtlas(args.data_dir, view=args.view) as graph:
        if args.command == 'stats': result = graph.stats()
        elif args.command == 'domains': result = graph.domains()
        elif args.command == 'domain': result = graph.domain(args.name)
        elif args.command == 'domain-children': result = graph.domain_children(args.name,args.limit)
        elif args.command == 'datasets': result = graph.datasets()
        elif args.command == 'instances': result = graph.instances(args.uid, args.limit, not args.direct)
        elif args.command == 'relations': result = graph.relations(args.uid, args.relation, args.direction, args.limit)
        elif args.command == 'node': result = graph.node(args.uid)
        elif args.command == 'connection-status':
            result = graph.connection_status(args.uid)
        elif args.command == 'exact': result = graph.exact(args.text, args.limit, node_kind=args.node_kind)
        elif args.command == 'search': result = graph.search(args.text, args.limit, args.domain, node_kind=args.node_kind)
        elif args.command == 'neighbors': result = graph.neighbors(args.uid, args.direction, args.limit, not args.include_auxiliary)
        elif args.command == 'path': result = graph.path(args.uid, args.anchor, args.max_depth)
        elif args.command == 'equivalents': result = graph.equivalents(args.uid)
        else: result = graph.target(args.dataset, args.class_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
