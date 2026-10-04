# FineAtlas V1

FineAtlas 是可本地查询的细粒度分类与实体数据库。WordNet 提供上层概念，向下连接物种、品种、车型、产品型号、器件、食品、矿物、自然地物及生境类型。

**全部数据位于一个 `fineatlas.sqlite` 文件。** 包含文本标签、独立 UID、别名、定义、来源证据、产品参数、矿物化学式和地理坐标；不含图片、图像特征或模型权重。Python 3.10+ 查询只使用标准库和 SQLite，无需 GPU、API key 或数据库服务器。

## 下载与使用

[公开仓库](https://github.com/yyh427/fineAtlas-V1)与[数据库下载页](https://github.com/yyh427/fineAtlas-V1/releases/latest)可以直接分享。源码 ZIP 包含接口与文档，数据库通过 Releases 下载。

```bash
git clone https://github.com/yyh427/fineAtlas-V1.git
cd fineAtlas-V1
python3 -m pip install -e .
# Linux: sudo apt install zstd；macOS: brew install zstd
python3 scripts/download_single.py --output-dir /path/to/fineatlas-data
fineatlas --data-dir /path/to/fineatlas-data stats
fineatlas --data-dir /path/to/fineatlas-data domains
fineatlas --data-dir /path/to/fineatlas-data domain forests
fineatlas --data-dir /path/to/fineatlas-data domain-children forests
python3 scripts/check_installation.py --data-dir /path/to/fineatlas-data
```

下载支持重试、断点续传和分片及整库 SHA-256 校验。分片合并解压后只有一个数据库，建议准备 80 GB 可用空间。Linux/macOS 可直接使用，Windows 可用 WSL。可设置 `FINEATLAS_DATA_DIR` 指定数据库位置。

## 节点与覆盖

| 项目 | 数量 |
|---|---:|
| 全部来源 UID | 12,361,588 |
| 分类路径可达 UID | 8,616,473 |
| 实例、属性和任务类别连接 UID | 3,399,533 |
| 仅保留来源记录的 UID | 260,025 |
| 有效 IS_A 来源记录 | 8,691,050 |
| 别名记录 | 23,388,838 |
| 统一领域浏览入口 | 92 |

来源 UID 和边数包含多个来源的独立表示与证据，不等于去重后的现实概念数。领域有重叠，计数不能相加。详见[完整统计](SINGLE_DATABASE.json)、[来源覆盖](docs/coverage.csv)和[领域层数](docs/domain_status.csv)。

| 领域 | 细化内容 |
|---|---|
| 动物、鸟类、植物、真菌、微生物 | 原生分类阶元、物种、亚种、栽培品种和犬猫品种 |
| 自然地理与生态 | 山峰、山脉、河流、湖泊、岛屿、冰川、洞穴等类型和命名实例；EEA EUNIS 2012/2021 共 9,144 个生境类别，原生层次最多 8 级；另有 USGS/NPS 的河流、湖泊、湿地、含水层和山地类型 |
| 矿物、天气 | IMA 6,239 个原生矿物记录，其中 6,143 个进入分类层；92 个化学成分细分类；WMO 10 个云属 |
| 电子产品与器件 | 计算机、手机、平板、相机、镜头、显卡、存储、网络设备、主板及元件；包含 Apple、Canon、NVIDIA、Samsung 等原生型号目录 |
| 汽车与飞行器 | 车型、年款、配置、飞行器家族和登记型号 |
| 工具、乐器、家具、服饰 | 功能、结构和来源专业类型 |
| 食品、建筑、家电、医疗器械 | 菜品、加工类型、建筑功能、设备和器械类型 |
| 场景、遥感、纹理 | 原生任务类别及经过核验的类型或属性连接 |

覆盖反映已导入的来源范围，不表示所有品牌、地物或科学类别已经穷尽。矿物分组表达化学成分，不推断晶体结构或替代 Dana/Strunz 分类。生境类型与具体地物分别保留。

## 层次与统一入口

分类层是允许多父节点的无环 DAG，可按树浏览。根是 `wordnet31:00001740-n`。所有准入分类节点都具有根路径，当前最长分类路径深度为 86。`IS_A` 表示下位类型，经过核验的 `SAME_CONCEPT` 表示身份对应，不增加分类深度。

**不同领域可以同名，UID 保持独立；名字相同本身不构成合并依据。** 查询返回多个候选时，应结合来源、定义、节点种类和 UID 选择。

每个领域只有一个 `fineatlas-domain:<domain>` 浏览入口。它汇集该领域的原生根，并保留不同来源和分类维度；入口本身是导航视图，不是新的 IS_A 类别。`domain_roots()` 查看这些根，`domain_children()` 从统一入口浏览子类。

类别、型号家族、型号及配置使用分类层。具体河流、山峰等通过 `INSTANCE_OF` 连接，纹理属性通过 `ATTRIBUTE_KIND_OF`，任务类别通过 `DEPICTS_TYPE`。位置关系使用 `LOCATED_IN`。这些关系不能作为 IS_A 分类边混用。

`SOURCE_ONLY` 记录保留原生身份和事实，但未获得分类准入；其本体归属为 UNKNOWN，不作为层次训练标签。可用 `view="all"` 检索，使用 `connection_status()` 检查用途。所有原生任务标签均保留；`NATIVE_LABEL_ONLY` 表示仅使用原生任务身份，没有已核验的现实类型映射。

## Python 接口

```python
from fineatlas import FineAtlas

with FineAtlas("/path/to/fineatlas.sqlite") as tree:
    print(tree.domains())
    print(tree.domain("forests"))
    print(tree.domain_roots("forests"))
    print(tree.domain_children("forests"))
    candidates = tree.exact("laser diode", node_kind="CLASS")
    uid = candidates[0]["uid"]
    print(tree.node(uid))
    print(tree.path(uid))
    print(tree.neighbors(uid, direction="parents"))
    print(tree.connection_status(uid))

with FineAtlas("/path/to/fineatlas.sqlite", view="all") as tree:
    print(tree.exact("quartz"))
```

新版增加 `relation_view`，旧调用默认使用 `"strict"`，只遍历有效 `IS_A`。浏览生物原生分类时使用 `"taxonomy"`，保留 `TAXONOMIC_PARENT`，它不等同于严格分类边；`"membership"` 单独查看来源类型成员关系。`neighbors()`、`domain_children()`、`path()` 按所选关系视图查询，返回边保留实际关系类型。严格视图下未接入根的节点可能没有路径；原生分类路径与严格分类路径应分别使用。原生变体的 `node_kind="BIOLOGICAL_VARIANT"` 和 `native_rank` 应保留，不作为物种、产品型号或命名实例。

```python
with FineAtlas("/path/to/fineatlas.sqlite", relation_view="taxonomy") as tree:
    print(tree.domain_children("birds"))
    print(tree.instances("geonames-feature:T.MTS", limit=20, recursive=False))
```

CLI 可增加 `--relation-view taxonomy`（放在子命令前）。更新已有安装时先运行 `git pull` 和 `python3 -m pip install -e .`，再将新版数据库下载到新的目录；下载器会拒绝覆盖哈希不同的已有数据库。

| 方法 | 用途 |
|---|---|
| `node(uid)` | 标签、定义、来源、节点种类和结构化参数 |
| `exact(text, limit=20, node_kind=None)` | 标签与别名精确匹配，保留独立同名 UID |
| `search(text, limit=20, domain=None, node_kind=None)` | 全文检索，按领域或节点种类筛选 |
| `domain(name)` / `domain_roots(name)` / `domain_children(name)` | 统一领域入口、原生根和子类浏览 |
| `neighbors(uid, direction="children", limit=20)` | 有效分类父子节点；领域入口 UID 返回该入口子类 |
| `path(uid, anchors=None, max_depth=256)` | 根到目标路径；类型连接的末步保留明确关系 |
| `instances(type_uid, limit=20, recursive=True)` | 类型下面的具体实例 |
| `relations(uid, relation=None)` / `evidence(evidence_id)` | 非分类关系与来源证据 |
| `equivalents(uid)` | 已核验的同身份来源 UID |
| `connection_status(uid)` | 分类准入和连接状态 |
| `target(dataset, class_id)` / `datasets()` | 原生任务编号及映射决定 |
| `domains()` / `stats()` | 领域入口和全库统计 |

无有效路径或超过指定深度上限时，`path()` 返回 `[]`。进行细粒度识别、层级监督或树距离评价时，先核查 `node_kind` 和准入状态，分别处理类别、实例和属性，并通过 UID 对齐训练标签。数据库提供分类知识与标签接口，不提供图像识别模型或训练图片。

数据库采用只读访问。一个接口实例用于一个线程/进程；使用上下文管理器或 `close()`。更换数据库文件后重新打开接口。[存储结构](docs/single_database.md)、[连接契约](docs/connectivity.md)、[验证结果](VALIDATION.json)。

## 来源与许可

接口代码采用 MIT。数据遵循各来源的许可与归属要求，重分发时保留证据和来源信息；详见 [DATA_SOURCES.md](DATA_SOURCES.md)。
