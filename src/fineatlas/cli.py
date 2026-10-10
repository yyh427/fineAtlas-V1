from __future__ import annotations

import argparse
import json
import sys
from .api import FineAtlas


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query the FineAtlas V1 SQLite database."
    )
    parser.add_argument("--data-dir", help="SQLite file or downloaded data directory")
    parser.add_argument('--browse-index',help='Readonly, revision-bound browse artifact for an unindexed frozen baseline')
    parser.add_argument(
        "--view", choices=["wordnet", "all"], help="Navigation view (default: wordnet)"
    )
    parser.add_argument(
        "--relation-view",
        choices=["strict", "taxonomy", "membership", "unified"],
        default=None,
        help="Relation navigation: strict IS_A, native taxonomy, or source membership",
    )
    parser.add_argument(
        "--root", help="Grounded native UID for the selected hierarchy root"
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Preferred display language with grounded fallback",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("stats")
    sub.add_parser("datasets")
    sub.add_parser("domains")
    p = sub.add_parser("domain")
    p.add_argument("name")
    p = sub.add_parser("domain-children")
    p.add_argument("name")
    p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("instances")
    p.add_argument("uid")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--direct", action="store_true")
    p = sub.add_parser("relations")
    p.add_argument("uid")
    p.add_argument("--relation")
    p.add_argument("--direction", choices=["outgoing", "incoming"], default="outgoing")
    p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("node")
    p.add_argument("uid")
    p = sub.add_parser("connection-status")
    p.add_argument("uid")
    p = sub.add_parser("exact")
    p.add_argument("text")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--node-kind")
    p = sub.add_parser("search")
    p.add_argument("text")
    p.add_argument("--domain")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--node-kind")
    p = sub.add_parser("neighbors")
    p.add_argument("uid")
    p.add_argument("--direction", choices=["parents", "children"], default="children")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--include-auxiliary", action="store_true")
    p = sub.add_parser("path")
    p.add_argument("uid")
    p.add_argument("--anchor", action="append")
    p.add_argument("--max-depth", type=int, default=256)
    p = sub.add_parser("equivalents")
    p.add_argument("uid")
    p = sub.add_parser("target")
    p.add_argument("dataset")
    p.add_argument("class_id")
    for command in ('task-path','reward-pair','export-training'):
        p=sub.add_parser(command)
        p.add_argument('dataset')
        if command=='task-path':p.add_argument('class_id')
        elif command=='reward-pair':
            p.add_argument('left');p.add_argument('right')
        else:p.add_argument('output')
        p.add_argument('--admission-mode',choices=['legacy','reviewed_paths'],default='legacy')
        p.add_argument('--target-scope',choices=['world','source_native'],default='world')
        p.add_argument('--source-namespace')
        p.add_argument('--source-version')
        p.add_argument('--task-boundary',action='append',default=[])
    for command in ('source-groups-page','source-group-members-page','export-source-groups'):
        p=sub.add_parser(command)
        if command=='source-group-members-page':p.add_argument('group_uid')
        else:
            p.add_argument('--namespace');p.add_argument('--source-version')
        if command=='export-source-groups':p.add_argument('output')
        else:
            p.add_argument('--limit',type=int,default=20);p.add_argument('--cursor')
        if command=='source-group-members-page':p.add_argument('--domain')
    p = sub.add_parser("browse-domain")
    p.add_argument("name")
    p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("browse-summary")
    p.add_argument("parent")
    for command in ("browse-page", "browse-groups"):
        p=sub.add_parser(command)
        p.add_argument("parent")
        p.add_argument("--limit",type=int,default=20)
        p.add_argument("--node-kind",default="CLASS" if command=="browse-page" else "MODEL")
        p.add_argument("--relation")
        p.add_argument("--cursor")
        p.add_argument("--include-coarse",action="store_true")
        if command=="browse-page":
            p.add_argument("--filter",action="append",default=[],metavar="FIELD=VALUE")
            p.add_argument("--domain")
        else:p.add_argument("--group-by",default="manufacturer")
    p=sub.add_parser("browse-path")
    p.add_argument("uid")
    p.add_argument("--anchor",action="append")
    p.add_argument("--max-depth",type=int,default=256)
    p=sub.add_parser("locate")
    p.add_argument("text")
    p.add_argument("--domain",required=True)
    p.add_argument("--limit",type=int,default=20)
    p=sub.add_parser("source-members-page")
    p.add_argument("uid")
    p.add_argument("--limit",type=int,default=20)
    p.add_argument("--cursor")
    for command, positional in [
        ("domain-page", "name"),
        ("instances-page", "uid"),
        ("search-page", "text"),
    ]:
        p = sub.add_parser(command)
        p.add_argument(positional)
        p.add_argument("--limit", type=int, default=20)
        p.add_argument("--cursor")
        if command == "search-page":
            p.add_argument("--domain")
            p.add_argument("--node-kind")
            p.add_argument("--exact", action="store_true")
        elif command == "domain-page":
            p.add_argument("--node-kind")
        else:
            p.add_argument("--direct", action="store_true")
    p = sub.add_parser("path-result")
    p.add_argument("uid")
    p.add_argument("--anchor", action="append")
    p.add_argument("--max-depth", type=int, default=256)
    p = sub.add_parser("aliases")
    p.add_argument("uid")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--name-language")
    p = sub.add_parser("identity")
    p.add_argument("uid")
    p = sub.add_parser("ancestors")
    p.add_argument("uid")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--include-self", action="store_true")
    p = sub.add_parser("lca")
    p.add_argument("left")
    p.add_argument("right")
    p.add_argument('--policy',choices=['classification','design','configuration','configuration_types'])
    p = sub.add_parser("distance")
    p.add_argument("left")
    p.add_argument("right")
    p.add_argument('--policy',choices=['classification','design','configuration','configuration_types'])
    p.add_argument(
        "--direction",
        choices=["upward", "downward", "undirected", "common_ancestor"],
        default=None,
    )
    requirements = [
        "identity",
        "native_label",
        "hierarchy",
        "strict_classification",
        "species",
        "model",
        "model_design",
        "configuration",
        "instance",
    ]
    p = sub.add_parser("eligibility")
    p.add_argument("uid")
    p.add_argument("--requirement", choices=requirements, default="hierarchy")
    p = sub.add_parser("task-labels")
    p.add_argument("dataset")
    p.add_argument("--requirement", choices=requirements, default="hierarchy")
    p.add_argument("--usable-only", action="store_true")
    p = sub.add_parser("export-domain")
    p.add_argument("name")
    p.add_argument("output")
    p.add_argument("--page-size", type=int, default=1000)
    p.add_argument("--node-kind")
    p.add_argument("--requirement", choices=requirements, default="hierarchy")
    args = parser.parse_args()
    with FineAtlas(
        args.data_dir,
        view=args.view,
        relation_view=args.relation_view,
        root=args.root,
        language=args.language,
        browse_index=args.browse_index,
    ) as graph:
        if args.command == "stats":
            result = graph.stats()
        elif args.command == "domains":
            result = graph.domains()
        elif args.command == "domain":
            result = graph.domain(args.name)
        elif args.command == "domain-children":
            result = graph.domain_children(args.name, args.limit)
        elif args.command == "datasets":
            result = graph.datasets()
        elif args.command == "instances":
            result = graph.instances(args.uid, args.limit, not args.direct)
        elif args.command == "relations":
            result = graph.relations(
                args.uid, args.relation, args.direction, args.limit
            )
        elif args.command == "node":
            result = graph.node(args.uid)
        elif args.command == "connection-status":
            result = graph.connection_status(args.uid)
        elif args.command == "exact":
            result = graph.exact(args.text, args.limit, node_kind=args.node_kind)
        elif args.command == "search":
            result = graph.search(
                args.text, args.limit, args.domain, node_kind=args.node_kind
            )
        elif args.command == "neighbors":
            result = graph.neighbors(
                args.uid, args.direction, args.limit, not args.include_auxiliary
            )
        elif args.command == "path":
            result = graph.path(args.uid, args.anchor, args.max_depth)
        elif args.command == "equivalents":
            result = graph.equivalents(args.uid)
        elif args.command == "target":
            result = graph.target(args.dataset, args.class_id)
        elif args.command in ('task-path','reward-pair','export-training'):
            options={'admission_mode':args.admission_mode,'target_scope':args.target_scope,
                     'source_namespace':args.source_namespace,'source_version':args.source_version,
                     'task_boundary_roots':args.task_boundary}
            if args.command=='export-training':
                result=graph.export_training(args.dataset,args.output,**options)
            elif args.command=='task-path':
                result=graph.task_path(args.dataset,args.class_id,**options)
            else:
                result=graph.relation_reward_index(args.dataset,**options).query(args.left,args.right)
        elif args.command=='source-groups-page':
            result=graph.source_groups_page(args.namespace,args.limit,source_version=args.source_version,cursor=args.cursor)
        elif args.command=='source-group-members-page':
            result=graph.source_group_members_page(args.group_uid,args.limit,domain=args.domain,cursor=args.cursor)
        elif args.command=='export-source-groups':
            result=graph.export_source_groups(args.output,namespace=args.namespace,source_version=args.source_version)
        elif args.command == "browse-domain":
            result = graph.browse_domain(args.name, args.limit)
        elif args.command == "browse-summary":
            result=graph.browse_summary(args.parent)
        elif args.command == "browse-page":
            filters={}
            for selector in args.filter:
                if '=' not in selector:parser.error('--filter must be FIELD=VALUE')
                field,value=selector.split('=',1)
                if field in filters:parser.error('Duplicate filter field: '+field)
                filters[field]=value
            result=graph.browse_children_page(args.parent,args.limit,
                node_kind=None if args.node_kind=='ALL' else args.node_kind,
                relation=args.relation,cursor=args.cursor,filters=filters,
                domain=args.domain,include_coarse=args.include_coarse)
        elif args.command == "browse-groups":
            result=graph.browse_groups(args.parent,args.group_by,args.limit,
                node_kind=None if args.node_kind=='ALL' else args.node_kind,
                relation=args.relation,cursor=args.cursor,include_coarse=args.include_coarse)
        elif args.command == "browse-path":
            result=graph.browse_path_result(args.uid,args.anchor,args.max_depth)
        elif args.command == "locate":
            result=graph.locate(args.text,args.domain,args.limit)
        elif args.command == "source-members-page":
            result=graph.source_members_page(args.uid,args.limit,cursor=args.cursor)
        elif args.command == "domain-page":
            result = graph.domain_page(
                args.name, args.limit, cursor=args.cursor, node_kind=args.node_kind
            )
        elif args.command == "instances-page":
            result = graph.instances_page(
                args.uid, args.limit, cursor=args.cursor, recursive=not args.direct
            )
        elif args.command == "search-page":
            result = graph.search_page(
                args.text,
                args.limit,
                args.domain,
                cursor=args.cursor,
                node_kind=args.node_kind,
                exact=args.exact,
            )
        elif args.command == "path-result":
            result = graph.path_result(args.uid, args.anchor, args.max_depth)
        elif args.command == "aliases":
            result = graph.aliases(args.uid, args.limit, language=args.name_language)
        elif args.command == "identity":
            result = graph.identity(args.uid)
        elif args.command == "ancestors":
            result = graph.ancestors(
                args.uid, args.limit, include_self=args.include_self
            )
        elif args.command == "lca":
            result = graph.lca(args.left, args.right, policy=args.policy)
        elif args.command == "distance":
            result = graph.distance(args.left, args.right, direction=args.direction, policy=args.policy)
        elif args.command == "eligibility":
            result = graph.eligibility(args.uid, args.requirement)
        elif args.command == "task-labels":
            result = graph.task_labels(
                args.dataset, args.requirement, usable_only=args.usable_only
            )
        elif args.command == "export-domain":
            result = graph.export_domain(
                args.name,
                args.output,
                page_size=args.page_size,
                node_kind=args.node_kind,
                requirement=args.requirement,
            )
        else:
            raise RuntimeError("Unimplemented CLI command")
        if hasattr(result, "has_more"):
            if args.command in ("aliases", "ancestors"):
                result = {
                    "items": list(result),
                    "has_more": result.has_more,
                    "truncated": result.truncated,
                }
            elif result.has_more:
                print(
                    "Result truncated; use the corresponding stable page query for complete results.",
                    file=sys.stderr,
                )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
