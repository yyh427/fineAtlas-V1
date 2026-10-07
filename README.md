# FineAtlas V1

FineAtlas 是可本地检索、浏览和导出的细粒度分类与实体数据库。WordNet 提供上层概念，数据库保留生物原生分类、产品家族/型号/配置、地理命名实例，以及各来源的独立 UID 和证据。

数据位于一个 `fineatlas.sqlite` 文件，包含名称、别名、定义、来源、关系和角色；不含图片、特征或模型权重。Python 3.10+ 查询只使用标准库和 SQLite，无需 GPU、API key 或数据库服务。

## 安装与数据

```bash
python3 -m pip install -e .
# 下载正式版数据库；需要 zstd，拒绝覆盖已有不同哈希的数据库
python3 scripts/download_single.py --output-dir /path/to/fineatlas-data
fineatlas --data-dir /path/to/fineatlas-data stats
```

本分支的接口版本为 `1.8.0rc1`，对应候选数据库 `v1.8.0-hierarchy-review`。新库的独立下载清单及 SHA-256 见 [review_data.json](review_data.json)；原有正式版下载清单保持独立。下载、解压和重建请为新库选择新的目录。

```bash
python3 scripts/download_single.py --manifest review_data.json \
  --output-dir /path/to/fineatlas-review
```

## 数据范围

准确计数及各视图的统计口径见 [新版统计](docs/review_statistics.json)和[各领域覆盖边界](docs/review_domains.csv)。来源 UID 数包含不同来源的独立表示，不等于现实对象或类别的去重数量。领域范围可以重叠，不能将其计数相加。

覆盖动物、鸟类、植物、真菌、微生物；山峰、山脉、河流、湖泊、岛屿及其他自然地物；生境、矿物、天气；汽车、飞行器；计算机、相机、电子器件及可穿戴产品；工具、乐器、家具、服饰、食品、建筑和医疗设备。不同领域根据真实体系区分物种、型号、配置和命名实例，覆盖不表示穷尽所有品牌、物种或对象。

## 关系、身份和领域

这是允许多父节点的 DAG。默认根为 `wordnet31:00001740-n`，默认 `relation_view="strict"`。

| 视图 | 分类/导航边 | 用途 |
|---|---|---|
| `strict` | 已准入的 `IS_A` | 严格下位类型 |
| `taxonomy` | `IS_A`、`TAXONOMIC_PARENT`、`NATIVE_CLASSIFICATION_PARENT` | 保留生物及专业来源原生层次，并显示真实关系 |
| `membership` | `REUSABLE_TYPE_MEMBERSHIP` | 独立来源成员关系，通常应使用原生根进行局部查询 |

`INSTANCE_OF`、`DESIGN_TYPE_OF`、`CONFIGURATION_OF`、`ATTRIBUTE_KIND_OF`、`DEPICTS_TYPE` 等类型连接分别保留，路径中的边不会改写为 `IS_A`。`NATIVE_DESIGN_PARENT` 保留来源中的型号/系列父关系，端点只能是型号或型号家族。原生/混合路径存在，不代表严格分类路径存在。

中间层按来源支持的结构、工作原理或生态类型逐渐细分。航空器使用 FAA 结构与动力字段；电子产品使用有定义的专业类型；地物保留原生环境分类。家族、型号和配置通过明确的类型关系接入这些类别。不同维度允许多父连接，不将品牌、年份、材料或监管分组统一串成子类链。各领域的普通 `CLASS` 层分布及范围见 [层次统计](docs/review_hierarchy.csv)；新增类别的定义、父节点及来源见 [专业类别清单](docs/review_middle_classes.csv)。

不同领域或来源可以同名，UID 保持独立。身份组只使用有依据的来源对应。身份映射、节点角色、视图准入、根可达性和任务准入分别返回；`VERIFIED` 身份不直接表示可用于完整层次训练。

规范入口可用名称、`fineatlas-domain:<domain>` 和不歧义的名称别名访问。旧入口继续作为兼容别名。领域检索、分页、实例浏览和导出使用相同视图下的成员范围；`source:<tag>` 单独选择原始来源域。导航入口不作为分类节点挂入 DAG。

## 查询与使用

```python
from fineatlas import FineAtlas

with FineAtlas('/path/to/fineatlas.sqlite', relation_view='taxonomy', language='zh') as tree:
    print(tree.domains())                       # 规范入口，去除重复展示
    print(tree.browse_domain('birds'))          # 原生根、子类及实例
    candidates = tree.search('albatross', domain='birds')
    if candidates:
        uid = candidates[0]['uid']
        print(tree.path_result(uid))           # 明确状态、路径及真实边类型
        print(tree.connection_status(uid))     # 与路径相同的视图及根
        print(tree.aliases(uid))
        print(tree.ancestors(uid))

    page = tree.domain_instances('mountain_ranges', limit=100)
    while True:
        for node in page['items']:
            print(node['uid'], node['label'])   # 保持 INSTANCE 身份
        if not page['next_cursor']:
            break
        page = tree.domain_instances('mountain_ranges', limit=100,
                                     cursor=page['next_cursor'])

    print(tree.search('汽车'))
    print(tree.search('山脉'))
    print(tree.task_labels('cub200', requirement='species', usable_only=True))
    tree.export_domain('fitness_trackers', '/path/to/trackers.jsonl')
```

浏览专业类别可使用 `neighbors(uid, direction='children')`，再按 `node_kind == 'CLASS'` 选择普通类别。型号和配置使用 `domain_page(..., node_kind='MODEL')`、`domain_page(..., node_kind='CONFIGURATION')` 查询，并通过 `path_result()` 查看其真实类型连接。新增专业类别的 `attributes.classification_axis` 和 `attributes.hierarchy_definition` 给出分类维度与定义；FDA、EPA 等监管节点应在 `taxonomy` 视图使用。

`node_kind="PRODUCT_DESIGN"` 查询型号及型号家族，`MODEL` 仅查询具体型号，`SERIES` 是 `MODEL_FAMILY` 的查询别名。`native_rank` 和 `source_role` 保留来源声明，`normalized_rank` 和 `normalized_role` 用于规范查询，冲突保持可见。

`search_page()`、`domain_page()`、`domain_instances()`、`instances_page()` 提供按 UID 排序的稳定分页。游标绑定数据库版本、视图、根和查询条件；跨条件使用会报错。旧列表接口保留，截断通过 `.truncated`/`.has_more` 明确标记。

`ancestors()` 返回祖先及最短向上距离。`lca()` 返回全部最近公共祖先身份组；多父 DAG 中可能有多个。`distance()` 支持 `upward`、`downward` 和 `undirected` 的最短路径；身份对应为零长度，声明的分类或类型连接为一步。不可达返回 `UNREACHABLE`，超出工作上限会报 `QueryLimitError`。

完整签名、返回状态、训练要求、迁移规则、导出格式和命令见 [接口文档](docs/public_api.md)；可运行示例见 [query_tree.py](examples/query_tree.py)。

## 重建与验证

```bash
python3 -m pip install -e '.[build]'
python3 scripts/rebuild_review.py \
  --baseline /path/to/v1.6/fineatlas.sqlite \
  --inputs /path/to/frozen-inputs \
  --database /path/to/new/fineatlas.sqlite \
  --reports /path/to/build-report
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 scripts/audit_usability.py --database /path/to/new/fineatlas.sqlite \
  --output /path/to/public-audit
```

重建验证基线哈希、保留原始来源字段，并为各视图重新建立版本绑定的查询索引。新来源通过统一事实格式和来源适配器接入。数据库、来源与代码的授权范围见 [DATA_SOURCES.md](DATA_SOURCES.md)。结构和接口检查通过不等于每条科学事实均已认证，也不证明识别准确率提高。

候选发布附件提供 `frozen-inputs.tar.zst`、逐文件哈希及来源清单。解压后将其中的 `role-corrected-frozen-inputs` 目录传给 `--inputs`。重建需要正式版 v1.6 基线及本分支代码；专业层次由 `hierarchy_refinements`、`hierarchy_extensions`、`hierarchy_contract_repairs`、`hierarchy_role_repairs`、`hierarchy_semantic_repairs`、`hierarchy_identity_role_repairs` 及规范端点合同阶段在图索引构建前重放。

Candidate task availability is listed per label and view in [review_task_labels.csv](docs/review_task_labels.csv). The 755 focused labels have individual typed path witnesses in [review_label_paths.jsonl](docs/review_label_paths.jsonl); unreachable results and their selected view are explicit.
