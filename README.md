# FineAtlas V1

FineAtlas 是一个可在本地查询的细粒度分类与实体数据库。WordNet 提供上层通用概念，向下连接物种、品种、车型、型号、器件、食品、矿物和自然地物类型；具体山川河流、纹理属性和数据集任务类别分别通过明确的关系连接。

**运行时只需要一个 `fineatlas.sqlite`。** 数据包含文本标签、独立 UID、别名、定义、来源证据、型号参数、矿物化学式和地理坐标；**不含图片、图像特征、模型权重或图像训练集**。Python 3.10+，查询只使用标准库与 SQLite，无需 GPU、API key 或数据库服务器。

## 下载和开始使用

仓库与数据库公开，可直接分享 [FineAtlas V1](https://github.com/yyh427/fineAtlas-V1) 和 [数据库下载页](https://github.com/yyh427/fineAtlas-V1/releases/latest)。Git 源码 ZIP 包含接口和文档，数据库在 Releases 中。

```bash
git clone https://github.com/yyh427/fineAtlas-V1.git
cd fineAtlas-V1
python3 -m pip install -e .
# Linux: sudo apt install zstd；macOS: brew install zstd
python3 scripts/download_single.py --output-dir /path/to/fineatlas-data
fineatlas --data-dir /path/to/fineatlas-data stats
fineatlas --data-dir /path/to/fineatlas-data domains
fineatlas --data-dir /path/to/fineatlas-data datasets
python3 scripts/check_installation.py --data-dir /path/to/fineatlas-data
```

下载脚本支持重试和断点续传，校验全部分片及完整数据库的 SHA-256。分片仅用于下载包装，解压后是一个约 **37.49 GB** 的 SQLite 文件；建议准备 **70 GB** 可用空间。Linux/macOS 可直接使用，Windows 可用 WSL。也可设置 `FINEATLAS_DATA_DIR`。

## 数量和覆盖范围

| 项目 | 数量 |
|---|---:|
| 全部来源 UID | 12,328,610 |
| 保留为有效来源记录的 UID | 12,328,531 |
| WordNet 分类路径可达 UID | 8,741,157 |
| 通过实例、属性或任务类别关系可达 UID | 3,398,389 |
| 其余保留来源记录 | 188,985 |
| 有效 `IS_A` 来源记录 | 8,828,473 |
| 别名记录 | 23,349,238 |
| 数据集原始类别编号 | 1,822 |
| 数据库文件 | 1 |

UID 数包含不同来源对同一概念的表示；有效边数包含不同来源证据。它们不是去重后的现实概念数。其余保留来源记录包括厂商元数据、来源容器和待审分类，不保证全部具备分类路径。[完整统计](SINGLE_DATABASE.json)、[按来源覆盖](docs/coverage.csv)、[验证报告](VALIDATION.json)。

| 领域 | 可用细化内容 |
|---|---|
| 动物、鸟类、植物、真菌及微生物 | 多来源分类阶元、物种、亚种、植物栽培品种和犬猫品种 |
| 自然地理 | 64 个来源自然地物类型、3,389,795 个命名自然地物，另有 252 个国家/地区记录；包括山峰、山脉、河流、湖泊、岛屿、海湾、瀑布、冰川、沙漠和洞穴。地物保留 WGS84 坐标、原生编号和区域信息 |
| 矿物与天气 | IMA 原生矿物名录 6,239 个，6,143 个具有分类路径、96 个疑问状态保留待审；化学式与原生状态保留。WMO 10 个云属具有分类路径 |
| 电子产品与器件 | 计算机、手机、平板、穿戴设备、耳机、音箱、显卡、存储、显示器、网络设备、主板/单板电脑及电子元件；原生目录包括 Apple 257 个型号、Canon 915 个相机与 534 个镜头型号、GeForce 38 个显卡产品规格、Samsung 34 个 SSD 产品线 |
| 汽车与飞行器 | 汽车车型/年款/配置、飞行器家族与型号、多个原生登记目录 |
| 家具、服饰、工具及乐器 | 功能类型、结构类型与来源原生专业分类 |
| 食物、建筑、家电及医疗器械 | 菜品、食品加工类型、建筑功能、设备和器械类型；Food-101 原生食品任务类别单独保留 |
| 场景、遥感、纹理 | 数据集原生类别和已审查的类型/属性连接；场景上下文不强行合并为同一物理概念 |

领域存在重叠。厂商目录覆盖所列目录范围，参数或容量变化不自动产生视觉细粒度类别；不代表全世界所有品牌和型号已经穷尽。[领域入口列表](docs/domain_roots.json) 可直接用于浏览。

## 结构与同名策略

分类层是允许多父节点的 **无环 DAG**，可以按树浏览。`IS_A` 表示下位类型，`SAME_CONCEPT` 表示经审查的跨来源同身份，不增加分类深度。

- 类别、型号家族和可重复生产的型号进入分类层。
- 具体山峰、河流和历史实物通过 `INSTANCE_OF` 接到类型；位置用 `LOCATED_IN` 表示。
- 纹理属性通过 `ATTRIBUTE_KIND_OF` 连接；任务类别通过 `DEPICTS_TYPE` 连接。
- **同名可以保留，不同意义使用不同 UID。** 同名本身不能提供同身份凭据；继承来源中的身份桥仍需复核。查询会返回多个候选，需结合 UID、领域、定义和节点种类选取。
- 待审或隔离记录不进入有效分类路径。未接通记录保留在同一个数据库，可使用 `view="all"` 查看。

WordNet 的 car 与 aircraft 入口保留必要祖先及仍被映射使用的原节点，分别裁剪原细分 32 和 47 个，使用来源细化继续向下。其他同名词义保留独立 UID。

当前结构检查通过，但跨来源身份仍有已确认的语义问题：植物属与爬行动物分类群中同名的 `Sauria` 被旧身份桥错并，使植物路径能够进入鸟类分支。无环与根可达不能证明所有分类语义正确。详见 [身份错并证据](docs/identity_issue.json)；生物分支用于严格层级监督或树距离评价前，应先解决这类身份问题。

[领域层次和可达性统计](docs/domain_status.csv) 按有效分类图统计领域入口以下的最短层数，不计同身份桥的深度；命名实例单独计数。领域范围重叠，统计不能相加。`profile_tagged_*` 列仅统计有扩展档案且标注该领域的类型/型号，不代表整个领域的覆盖率；后代分支的根可达率也不包括未准入候选。

## Python 接口

```python
from fineatlas import FineAtlas

with FineAtlas("/path/to/fineatlas.sqlite") as tree:
    print(tree.domains())
    print(tree.datasets())
    candidates = tree.exact("laser diode", node_kind="CLASS")
    uid = candidates[0]["uid"]
    print(tree.node(uid))
    print(tree.path(uid))
    print(tree.neighbors(uid, direction="parents"))
    print(tree.target("cub200", "1"))

    # 命名地物独立于分类子节点。先查候选，再按来源编号选 UID。
    for item in tree.exact("Everest", node_kind="INSTANCE"):
        print(item["uid"], tree.node(item["uid"])["attributes"])
        print(tree.path(item["uid"]))

with FineAtlas("/path/to/fineatlas.sqlite", view="all") as tree:
    print(tree.search("airport terminal", node_kind="DATASET_CATEGORY"))
```

| 方法 | 用途 |
|---|---|
| `node(uid)` | 身份、定义、来源、`node_kind`、参数及分类/类型连接状态 |
| `exact(text, limit=20, node_kind=None)` | 标签/别名精确匹配，保留同名歧义 UID |
| `search(text, limit=20, domain=None, node_kind=None)` | 别名全文查询，可筛选领域/种类 |
| `neighbors(uid, direction="children", limit=20)` | 分类父子节点；默认仅有效 `IS_A` |
| `path(uid, anchors=None, max_depth=64)` | 根到目标的有证据路径；实例、属性、任务类别末步带明确关系 |
| `relations(uid, relation=None, direction="outgoing", limit=20)` | 有效的非分类关系及证据 |
| `instances(type_uid, limit=20, recursive=True)` | 类型及其子类型下面的具体实例 |
| `equivalents(uid)` | 同身份组的来源 UID |
| `connection_status(uid)` | 准入用途和连接状态 |
| `evidence(evidence_id)` | 对应证据记录及来源信息 |
| `target(dataset, class_id)` | 原生类别、映射决定与目标 UID |
| `datasets()` / `domains()` / `stats()` | 数据集覆盖、领域入口和全库统计 |

`wordnet_reachable` 指分类层路径，`entity_reachable` 指独立的类型连接缓存；具体地点不应加入分类子节点。`path()` 返回按根到目标排列的步骤，每项记录该节点及其父节点，第一步的 `parent_uid` 是根；根本身没有父边。无有效路径或超过深度上限返回 `[]`。

```bash
fineatlas --data-dir /path/to/fineatlas.sqlite exact 'Everest' --node-kind INSTANCE
fineatlas --data-dir /path/to/fineatlas.sqlite target cub200 1
fineatlas --data-dir /path/to/fineatlas.sqlite path 'wikidata:Q321098'
fineatlas --data-dir /path/to/fineatlas.sqlite relations 'geonames:1283416'
```

更多存储细节见 [数据库说明](docs/single_database.md)，连接契约见 [连接说明](docs/connectivity.md)。一份接口实例用于一个线程/进程，请使用上下文管理器或 `close()`。

## 数据来源与许可

接口代码使用 MIT。数据遵循各上游来源的许可与归属要求，包括 GeoNames 的 CC BY 4.0 和 IMA 名录的 CC BY-SA 3.0；重分发时保留证据和归属。详见 [DATA_SOURCES.md](DATA_SOURCES.md)。
