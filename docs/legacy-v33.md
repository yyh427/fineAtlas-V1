> 本文是历史 V33 使用说明。FineAtlas V1 已修正部分车辆配置身份误合并，当前身份与路径复核结果见 [连接说明](connectivity.md)。

# fineAtlas-V1

FineAtlas 是一套可在本地查询的多来源细粒度分类图，提供从通用概念到物种、品种、车型、型号、器件类型和具体菜品的分类路径。

**本次公开发行名为 `fineAtlas-V1`，内容对应已冻结的 V33 完整查询视图（2026-09-28）。** 这是公开交付版本的 V1；内部存储层的 V3、V4、V25–V33 是同一个最终图的依赖，不需要用户从中选择一棵树。

Python 3.10+，运行时仅使用标准库和本地 SQLite；无需 GPU、模型权重、API key 或数据库服务器。

## 下载完整图并开始使用

仓库保存接口与说明；**完整数据库在 [Release v1.0.0](https://github.com/yyh427/fineAtlas-V1/releases/tag/v1.0.0)**。只点 GitHub 的源码 ZIP 或只执行 `git clone` 不包含树数据库。

```bash
git clone https://github.com/yyh427/fineAtlas-V1.git
cd fineAtlas-V1
python3 -m pip install -e .

# Linux: sudo apt install zstd
# macOS: brew install zstd
python3 scripts/download_data.py

fineatlas stats
python3 scripts/check_installation.py
fineatlas exact 'laser diode'
fineatlas neighbors 'wikidata:Q321098' --direction parents
fineatlas path 'wikidata:Q321098'
```

下载脚本会下载全部分片、核对 SHA-256、解压 31 个数据库并逐文件验证。下载中断可重新运行。需要 `zstd` 和约 **35 GB 可用磁盘空间**；数据库解压后约 **24.98 GB（23.26 GiB）**。主要支持 Linux/macOS，Windows 可使用 WSL。

也可以手动下载 Release 的所有 `fineatlas-v1-v33-data.tar.zst.part-*` 文件及 `SHA256SUMS`：

```bash
sha256sum -c SHA256SUMS
cat fineatlas-v1-v33-data.tar.zst.part-* | zstd -dc | tar -xf -
python3 scripts/verify_data.py
```

请在克隆后的仓库目录解压，最终目录中应同时有 `bundle.json`、`src/` 和 `data/`。数据库可以放到其他磁盘：

```bash
python3 scripts/download_data.py --output-dir /path/to/fineatlas-data
fineatlas --data-dir /path/to/fineatlas-data stats
# 也可设置 export FINEATLAS_DATA_DIR=/path/to/fineatlas-data
```

## 图的规模与计数口径

| 项目 | 本次完整快照 |
|---|---:|
| 物理节点记录 | **8,917,050** |
| 存储边记录 | **9,263,673** |
| SQLite 数据文件 | **31** |
| 基础跨来源对齐记录 | **4,373,364** |
| 完整 WordNet 3.1 名词骨架 | **82,192 个 synset** |
| 六数据集目标类别映射 | **755** |

上述节点/边数按依赖数据库实际表行统计。不同来源可分别保存同一概念，因此节点记录数不是全局去重概念数。存储边包含辅助证据和已隔离的原始记录，也不是当前有效 `IS_A` 边总数。具体每个文件的大小、SHA-256、表行数、关系和 UID 来源分布见 [`bundle.json`](../bundle.json)。

本次打包的查询一致性与校验记录见 [`VALIDATION.json`](../VALIDATION.json)。统一接口提供当前有效查询视图，保留 V33 的来源对齐、身份桥和错边屏蔽。190 条已隔离的历史错边不会从该接口重新出现。直接读原始 `edges` 表会看到部分历史记录，不能把它们全部当作有效分类。

## 覆盖的领域

| 领域 | 已有细化内容 | 当前范围 |
|---|---|---|
| 动物、鸟类 | 分类阶元、物种、亚种、犬猫品种 | 大规模细粒度覆盖；不同来源并非全部互相连通 |
| 植物 | 物种、变种、栽培品种 | 大规模分类与品种层 |
| 真菌、细菌、古菌 | 来源原生物种分类 | 大规模生命分类分支 |
| 飞行器 | 飞行器类型、家族、型号 | 型号覆盖较多，部分来源路径较浅 |
| 汽车与机动车 | 车型、年款、变体 | 多来源身份与型号细化 |
| 家具 | 桌椅床柜、用途/设计类型 | 已有 Getty/Wikidata 等扩展，尚未覆盖全部商品型号 |
| 服饰、鞋帽及配件 | 服装、鞋帽和具体类型 | 专业与通用类型分类 |
| 工具 | 切割、钻孔、木工、机床等类型 | Getty 与 Wikidata 类型细化 |
| 乐器 | 乐器类型及构造/分类体系 | MIMO 等来源；分类编号不等同于商品型号 |
| 食物、菜品 | 食品产品、加工状态、组合类、具体菜品 | FoodOn 和 Wikidata 等；食材、菜品、部件分别保留 |
| 电子与计算相关 | 手机型号、元件、晶体管、二极管、电容、电阻、集成电路等 | 部分分支已有多层路径，PCB 合法父路径仍缺 |
| 家电 | 冰箱、吸尘器、吊扇、慢炖锅等 | 已接入部分类型，覆盖仍稀疏 |
| 建筑 | 住宅、宗教、工业、商业及部分交通建筑 | 具体功能类别仍有缺口 |
| 医疗器械 | 听诊器、除颤器、手术器械等 | 合法类型路径已有，专业覆盖仍较薄 |
| 其他现实领域 | WordNet 通用概念骨架 | 有类型节点不代表已有现实型号/身份层 |

领域之间存在重叠。此表说明图中已经有哪些内容，不代表整个现实世界的覆盖率。

## 图结构和边的含义

FineAtlas 是允许多父节点的 **DAG 和多来源分类视图**。它可以像树一样向上/向下浏览，但不是强制单父、单根的树。

- 节点以来源 UID 标识，例如 `wikidata:Q321098`、`wordnet31:00001740-n`、`foodon:FOODON_00001002`；同名节点可能代表不同概念。
- 分类边按 **child → parent** 保存，`neighbors(..., direction="children")` 返回下位节点，`parents` 返回上位节点。
- `IS_A`、`WORDNET_IS_A`、`TAXONOMIC_REFINEMENT`、`REUSABLE_TYPE_REFINEMENT` 等用于不同来源的合法细化。
- `SAME_CONCEPT` 是跨来源同概念对齐，**不是父子关系，也不增加分类深度**。
- 来源、关系类型、facet、分类依据和证据保留在节点/边记录中；制造商、属性、部件等辅助关系不能直接解释成分类。
- `facet_family` 表示细化轴，如 `TYPE_KIND`、`TAXONOMIC_LINEAGE`、`MODEL_IDENTITY`、`STRUCTURE_CONFIGURATION`、`STATE_STATUS`。

示例路径：

```text
physical_entity → object → part → component → electronic component
  → semiconductor device → semiconductor diode → laser diode

physical_entity → matter → substance → food → nutriment → dish
  → vegetable dish → disanxian

physical_entity → object → whole → artifact → commodity → consumer_goods
  → durables → appliance → home_appliance → kitchen_appliance → slow cooker
```

路径可能跨来源对齐。接口返回实际步骤及边字段，请保留这些字段，不要仅用显示标签重建分类关系。

## Python 接口

```python
from fineatlas import FineAtlas

with FineAtlas("/path/to/fineAtlas-V1") as graph:
    matches = graph.exact("laser diode")
    node = graph.node("wikidata:Q321098")
    parents = graph.neighbors("wikidata:Q321098", direction="parents")
    children = graph.neighbors("wikidata:Q1929430", direction="children", limit=20)
    path = graph.path("wikidata:Q321098")
    similar_names = graph.search("ceramic capacitor", limit=10)
    equivalent_uids = graph.equivalents("wikidata:Q642345")
```

| 接口 | 返回内容 |
|---|---|
| `node(uid)` | 一个节点字典，缺失时为 `None` |
| `exact(text, limit=20)` | 归一化名称/别名精确匹配的节点列表；保留歧义 |
| `search(text, limit=20, domain=None)` | 有界文本搜索，精确命中优先；包含所有增量层的名称 |
| `neighbors(uid, direction="children", limit=20, structural_only=True)` | 合法上位/下位节点，附边合同和来源证据 |
| `path(uid, anchors=None, max_depth=32)` | 锚点到节点的有界见证路径，未找到时为 `[]` |
| `equivalents(uid)` | 查询视图中对齐的其他来源 UID |
| `target(dataset, class_id)` | 可选的数据集类别到节点映射 |
| `stats()` | 本次发行的规模、计数口径与原始领域根 |
| `close()` | 关闭所有连接；推荐用 `with` 自动管理 |

默认路径锚点是 WordNet `entity` 和 FoodOn `food product`。可以使用 `anchors=[...]` 指定自己的根。返回步骤可能省略锚点本身，可用 `parent_uid` 检查起点；空路径表示在本次有界查询内未找到，不能据此断言概念不存在。

节点主要字段为 `uid`、`label`、`description`、`source`、`rank`、`domain`/`domains`、`data`。邻接结果还包含 `edge`；部分结果有 `edge_evidence`、`equivalent_uids`。边中常见字段为 `child_uid`、`parent_uid`、`relation`、`facet_family`、`typed_refinement_kind`、`navigation_role`、`source`、`provenance`。来源不同，部分可选字段可能为空。一个名称命中多个 UID 时应检查身份和来源，而不是自动选第一项。

默认邻接只返回结构细化；`structural_only=False` 可查看辅助关系，已屏蔽错边仍保持屏蔽。`neighbors` 和 `search` 都受 `limit` 限制，不是完整批量导出。对全量源记录，可直接使用 SQLite 和 [`docs/storage.md`](storage.md)，同时应用屏蔽与身份合同。

每个实例拥有 SQLite 连接。多线程/多进程服务请每个线程/进程创建自己的实例。查询不修改下载的数据库；运行时描述符放在临时目录，支持移动数据目录和只读挂载。

## 命令行接口

```bash
fineatlas stats
fineatlas node 'wikidata:Q321098'
fineatlas exact 'Boeing 737'
fineatlas search 'laser diode' --limit 10
fineatlas neighbors 'wikidata:Q321098' --direction parents
fineatlas neighbors 'wikidata:Q1929430' --direction children --limit 50
fineatlas path 'wikidata:Q321098' --anchor 'wordnet31:00001740-n'
fineatlas equivalents 'wikidata:Q642345'
fineatlas target cub200 1
```

所有命令输出 JSON，便于脚本或服务读取。没有安装包时，也可从仓库运行 `PYTHONPATH=src python3 -m fineatlas stats`。

## 可选的六数据集类别目录

包含 CUB-200（200）、FGVC-Aircraft（100）、Flowers-102（102）、Oxford-IIIT Pet（37）、Stanford Dogs（120）、Stanford Cars（196），合计 755 条类别映射。目录只是方便用户检查已有目标身份，图的覆盖远大于这些类别。

冻结 V26 的 755 个类别曾全部通过身份、合法路径和粒度审计；后续 V33 保留相关依赖，并通过旧身份/边回归检查。该结果不代表视觉识别准确率为 100%，也不代表任意名称都能自动消歧。

## 数据来源与许可

主要来源包括 WordNet 3.1、Wikidata/Wikipedia、Open Tree of Life、World Flora Online、AviList、Catalogue of Life、FAA、EPA/vPIC、Getty AAT、FoodOn、MIMO，以及相关器件、建筑、家电和医疗类型的权威定义。具体身份和关系来源保留在数据库记录中。

不同来源适用各自许可与署名要求。接口代码的 MIT 许可不覆盖第三方数据；使用、再分发或商业使用前，请查阅 [`DATA_SOURCES.md`](../DATA_SOURCES.md)。

本发行包含完整树数据库、名称索引、分类证据、身份对齐和查询接口。内容面向树数据的使用，不包含模型训练、前置实验流程或图像数据。

---

**English quick start:** `fineAtlas-V1` distributes the complete frozen V33 classification graph. Clone this repository, install with `pip install -e .`, install `zstd`, then run `python3 scripts/download_data.py`. Use `from fineatlas import FineAtlas` for read-only node lookup, exact/alias matching, text search, parent/child navigation, identity alignment and bounded paths. Database assets are attached to Release `v1.0.0`; cloning alone does not download them. The 8.92M node rows and 9.26M stored edge rows preserve source identities and are not globally deduplicated concept/active-edge counts. Upstream data licenses remain applicable.
