# FineAtlas V1

FineAtlas 是可在本地使用的细粒度分类图：以 WordNet 的通用概念为入口，向下连接物种、品种、车型、型号、器件类型及具体菜品。

**运行时只需要一个 `fineatlas.sqlite`。** 数据库保留来源 UID、别名、定义和分类证据，提供 WordNet 根到细粒度类别的查询路径。

Python 3.10+，查询仅使用标准库和 SQLite，无需 GPU、模型权重、API key 或数据库服务器。

## 下载与使用

**本项目已公开，任何人都可以通过链接查看仓库、下载数据库。** 完整数据库在 [FineAtlas V1 下载页](https://github.com/yyh427/fineAtlas-V1/releases/latest)。Git 仓库仅保存接口、说明和数据清单；源码 ZIP 不包含数据库。

```bash
git clone https://github.com/yyh427/fineAtlas-V1.git
cd fineAtlas-V1
python3 -m pip install -e .

# Linux: sudo apt install zstd
# macOS: brew install zstd
python3 scripts/download_single.py --output-dir /path/to/fineatlas-data

fineatlas --data-dir /path/to/fineatlas-data stats
fineatlas --data-dir /path/to/fineatlas-data exact 'laser diode'
fineatlas --data-dir /path/to/fineatlas-data path 'wikidata:Q321098'
python3 scripts/check_installation.py --data-dir /path/to/fineatlas-data
```

下载脚本支持中断后重试，并校验每个分片及最终数据库的 SHA-256。分片只是下载包装，解压后只有 **一个数据库**，约 **28.64 GB**；建议准备 40 GB 可用空间。主要支持 Linux/macOS，Windows 可用 WSL。

手动安装时，从当前发布页下载全部 `*.sqlite.zst.part-*` 分片和 `SHA256SUMS*` 校验文件，放到同一目录：

```bash
sha256sum -c SHA256SUMS*
cat *.sqlite.zst.part-* | zstd -dc > fineatlas.sqlite
python3 scripts/verify_single.py --data-dir /path/to/fineatlas.sqlite
```

也可设置 `FINEATLAS_DATA_DIR=/path/to/fineatlas.sqlite`。

## 节点数量与连接情况

| 项目 | FineAtlas V1 |
|---|---:|
| 全部来源 UID 节点 | 8,917,058 |
| 当前保留节点 | 8,916,979 |
| 从 WordNet 根可达的保留节点 | **8,735,597（98.0%）** |
| 尚未接通 WordNet 的保留节点 | 181,382 |
| 全部来源有效 `IS_A` 记录 | 8,817,082 |
| 别名记录 | 17,105,509 |
| 已裁剪 WordNet 节点 | 79 |
| 数据库文件 | **1** |

UID 数不是去重后的现实概念数，不同来源可能分别表示同一概念。有效边数包含未接通分支和来源重复证据，也不是默认 WordNet 视图的独立概念边数。完整计数、哈希和裁剪结果见 [SINGLE_DATABASE.json](SINGLE_DATABASE.json)，按来源命名空间的连接情况见 [coverage.csv](docs/coverage.csv)。

**六个数据集共 755 个类别均通过节点身份和 WordNet 根路径检查；每个数据集内部的目标 UID 与身份组均不重复。** 检查覆盖 CUB-200（200）、FGVC Aircraft（100）、Flowers-102（102）、Oxford Pets（37）、Stanford Dogs（120）、Stanford Cars（196）。这验证类别映射和路径，不衡量图像识别准确率，也不替代所有继承断言的逐条语义审查。见 [验证报告](VALIDATION.json)。

## 节点准入与结构

有效分类图允许多父节点，是可以按树浏览的无环 DAG。`SAME_CONCEPT` 表示同身份来源记录，单独保存，不增加分类深度；属性、厂商和部件关系不作为 `IS_A` 父子关系。

未进入 WordNet 导航的 181,382 个来源 UID 分为：

| 处理 | UID 数 | 使用方式 |
|---|---:|---|
| 厂商、品牌、属性及明确非分类/容器来源记录 | 164,671 | 用于溯源；`tree_admission=NOT_REQUIRED` |
| 分类或身份证据尚未解决的记录 | 16,711 | 保留待审；`tree_admission=REVIEW` |

逐节点状态、示例与完整清单见 [连接诊断说明](docs/connectivity.md)。`path()` 和 CLI 默认分类深度上限为 64。

## 覆盖的领域

| 领域 | 已有细化内容 | 当前范围 |
|---|---|---|
| 动物、鸟类 | 分类阶元、物种、亚种、犬猫品种 | 大规模细粒度覆盖|
| 植物 | 物种、变种、栽培品种 | 大规模分类与品种层 |
| 真菌、细菌、古菌 | 来源原生物种分类 | 大规模生命分类分支 |
| 飞行器 | 飞行器类型、家族、型号 | 型号覆盖较多，部分来源路径较浅 |
| 汽车与机动车 | 车型、年款、变体 | 多来源身份与型号细化 |
| 家具 | 桌椅床柜、用途/设计类型 | 已有 Getty/Wikidata 等扩展，尚未覆盖全部商品型号 |
| 服饰、鞋帽及配件 | 服装、鞋帽和具体类型 | 专业与通用类型分类 |
| 工具 | 切割、钻孔、木工、机床等类型 | Getty 与 Wikidata 类型细化 |
| 乐器 | 乐器类型及构造/分类体系 | MIMO 等来源；分类编号不等同于商品型号 |
| 食物、菜品 | 食品产品、加工状态、组合类、具体菜品 | FoodOn 和 Wikidata 等；食材、菜品、部件分别保留 |
| 电子与计算相关 | 手机型号、元件、晶体管、二极管、电容、电阻、集成电路等 | 部分分支已有多层路 |
| 家电 | 冰箱、吸尘器、吊扇、慢炖锅等 | 已接入部分类型，覆盖仍稀疏 |
| 建筑 | 住宅、宗教、工业、商业及部分交通建筑 | 具体功能类别仍有缺口 |
| 医疗器械 | 听诊器、除颤器、手术器械等 | 合法类型路径已有，专业覆盖仍较薄 |
| 其他现实领域 | WordNet 通用概念骨架 | 有类型节点不代表已有现实型号/身份层 |

领域之间存在重叠。此表说明图中已经有哪些内容，不代表整个现实世界的覆盖率。


## WordNet 在上层，FineAtlas 如何向下补齐

默认入口是 `wordnet31:00001740-n`（entity）。WordNet 提供通用类型骨架；来源原生分类和细粒度身份层通过已有身份对齐或经定义核对的分类连接接入。

例如汽车分支的一条实际路径，在隐藏同概念的来源表示后可读作：

```text
entity → … → motor_vehicle → car
                              └─ AM General Hummer H1
                                   └─ AM General Hummer H1 4-door SUV 2000
```

数据库保留 WordNet、Wikidata 和来源原生入口的不同 UID。接口返回的详细路径会显式标注中间的 `SAME_CONCEPT`，它表示身份对齐，不增加分类深度，也不会被当作 `IS_A`。

汽车意义的 `car` 入口是 `wordnet31:02961779-n`。它下方不再要求沿用 WordNet 的全部旧细分：默认导航裁剪汽车原细分 32 个、飞机原细分 47 个，以接入的来源细化分支承担下位分类；仍被数据集目标或跨来源连接使用的 WordNet 节点及必要祖先继续保留。其他同名词义不受名字匹配影响。

默认导航只显示 WordNet 可达的有效节点。尚未接通的分支继续保存在同一个数据库，使用 `view="all"` 检查。图允许多父节点，是可按树浏览的 DAG；未强制把每个现实概念压成单父节点。具体存储和裁剪规则见 [single_database.md](docs/single_database.md)。

## Python 接口

```python
from fineatlas import FineAtlas

with FineAtlas("/path/to/fineatlas.sqlite") as tree:
    candidates = tree.exact("laser diode")
    uid = candidates[0]["uid"]
    print(tree.node(uid))
    print(tree.connection_status(uid))
    print(tree.neighbors(uid, direction="parents"))
    print(tree.path(uid))
    print(tree.neighbors("wordnet31:02961779-n", direction="children", limit=100))

# 检查包括尚未接通的分支在内的全部有效来源分类
with FineAtlas("/path/to/fineatlas.sqlite", view="all") as tree:
    print(tree.exact("food material"))
```

| 方法 | 返回内容 |
|---|---|
| `connection_status(uid)` | 接通状态、原因、记录用途 `record_role` 与分类准入 `tree_admission` |
| `node(uid)` | 节点、来源、原始元数据、显示状态及 WordNet 可达性；可检查裁剪节点 |
| `exact(text, limit=20)` | 当前视图内的规范化标签/别名精确匹配；保留歧义 UID |
| `search(text, limit=20, domain=None)` | 当前视图内的别名全文查询 |
| `neighbors(uid, direction="children", limit=20)` | 有效父/子节点及边证据；跨来源身份路径会标记 `via_alignment` |
| `path(uid, anchors=None, max_depth=64)` | 默认返回 WordNet 根到目标的证据路径；未到达或超深度返回 `[]` |
| `equivalents(uid)` | 同身份组中的其他来源 UID |
| `target(dataset, class_id)` | 六数据集类别到节点的可选映射 |
| `stats()` | 数据库计数、裁剪和连接情况 |

分类边按 **child → parent** 保存。规范有效关系为 `IS_A`；历史来源关系保存在 `original_relation`。身份桥独立保存为 `SAME_CONCEPT`。`path()` 的深度限制计算分类步数，身份桥不增加分类深度。不要把属性、厂商、部件或同名标签直接作为分类关系。

`neighbors(..., structural_only=False)` 可查看辅助和待审记录；历史隔离、环路隔离和裁剪记录仍不会成为有效分类。直接 SQL 用户可读取 `wordnet_nodes`、`wordnet_edges` 或 `active_nodes`、`active_edges` 视图。一个实例用于一个线程/进程，请用上下文管理器或调用 `close()`。

CLI 支持 `stats`、`node`、`connection-status`、`exact`、`search`、`neighbors`、`path`、`equivalents` 和 `target`。`--data-dir`、`--view` 写在子命令之前：

```bash
fineatlas --data-dir /path/to/fineatlas.sqlite --view all exact 'food material'
fineatlas --data-dir /path/to/fineatlas.sqlite target cub200 1
```

目标目录的标识为 `cub200`、`fgvc_aircraft`、`flowers102`、`pets37`、`stanford_dogs`、`stanford_cars`。映射提供类别身份，不提供识别模型。

## 来源与许可

来源包括 WordNet、Wikidata、Open Tree of Life、World Flora Online、AviList、FoodOn、Getty AAT、MIMO、MeSH、FAA、vPIC、EPA 等。原始来源身份、证据及哈希保留在数据库中。来源及许可说明见 [DATA_SOURCES.md](DATA_SOURCES.md)。

接口代码使用 MIT；第三方数据遵循各自来源许可，不因打包而获得统一的新数据许可。数据库通过只读接口查询，下载和安装时校验 SHA-256。

FineAtlas is a local, multi-source fine-grained taxonomy. The latest release uses one SQLite database, with a WordNet-rooted navigation view and retained source fragments for inspection.
