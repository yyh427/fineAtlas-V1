# 单库结构与 WordNet 导航

V36 沿用 V34 对 V33 的 31 个 SQLite 依赖的合并结果，运行时使用 `fineatlas.sqlite`。运行时只有这个文件；`bundle.json` 仅用于历史 V33 版本。数据库按只读快照交付，身份对齐与分类边分开保存。

| 表或视图 | 用途 |
|---|---|
| `nodes` | 全部来源 UID、标签、定义、原始 JSON、来源层、显示状态及身份组 |
| `edges` | 原始分类/辅助记录、规范关系、证据、隔离状态 |
| `aliases` / `alias_search` | 别名与全文索引 |
| `bridges` | 跨来源身份对齐；不属于分类边 |
| `evidence` | 按来源层区分的证据及内容哈希 |
| `dataset_targets` | 六数据集 755 个类别的节点映射 |
| `target_revisions` | 来源范围复核后保留的历史类别映射 |
| `components` | 身份组、WordNet 可达性、层级深度和路径证据边 |
| `pruning` | 裁剪的 WordNet UID、替换入口及理由 |
| `classification_repairs` | 分类关系的准入或待审记录及冻结证据哈希 |
| `node_dispositions` | 未接通记录的用途、分类准入状态与原因 |
| `source_scope_reviews` | 冻结 OTT 标志、原始来源行及非分类/容器审核状态 |
| `suppressed_edges` | V33 的历史隔离记录 |
| `inputs` / `source_tables` | 31 个输入快照的哈希与各源表导入清单 |
| `archive_*` | 原有身份展示、年款、来源名称目录、拒绝记录及其他附属表 |
| `active_nodes` / `active_edges` | 全部来源的当前有效节点/分类边，含未接通分支 |
| `wordnet_nodes` / `wordnet_edges` | 从 WordNet 根可达的有效导航视图 |

`nodes.uid` 唯一，但不同 UID 仍可表示同一概念；`component_id` 是本快照内的身份组编号，不应作为跨版本稳定 ID。`edges.status='ACTIVE'` 的规范关系为 `IS_A`，原关系保存在 `original_relation`。`SAME_CONCEPT` 保存在 `bridges`；路径中的这类步骤不增加分类深度。

## 替换 WordNet 下位分支

目前配置汽车 `wordnet31:02961779-n` 和飞机 `wordnet31:02689427-n` 两个入口。只有入口通过既有身份对齐接到拥有多个有效下位节点的来源原生分支，才能裁剪旧细分。六数据集目标、跨来源连接端点及它们必需的 WordNet 祖先受保护。裁剪 UID 保留在原始表中，标记 `PRUNED_WORDNET`，不出现在默认导航中。

WordNet 的其他同名词义不会因为名字相同而被替换。例如汽车意义的 `car` 与铁路车厢意义的 `car` 是不同 UID。

## 有效边与环路

历史隔离边继续屏蔽。V35 先把与原生分类发生冲突的名称身份对齐转为 `REVIEW`，再重新检查整个分类图的环路：保留 WordNet 原生骨架与独立构建的来源原生层级，冲突时先隔离旧聚合层的分类连接；同优先级的环路无法确定正确方向时继续隔离。这是结构上的保守冲突处理，不能据此声称所有来源断言都经过新的语义审查。

原有仅凭标签匹配生成的 WordNet 根对齐仍为 `REVIEW`，不会直接成为分类边。目录、厂商、属性、部件关系不会为提高连通率而改成 `IS_A`。默认接口浏览 WordNet 可达视图；使用 `FineAtlas(path, view="all")` 可检查尚未接通的来源分支。

## 直接 SQL

```python
import sqlite3
from pathlib import Path

path = Path("fineatlas.sqlite").resolve()
with sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True) as db:
    print(db.execute("SELECT uid,label FROM wordnet_nodes LIMIT 10").fetchall())
    print(db.execute("SELECT child_uid,parent_uid FROM wordnet_edges LIMIT 10").fetchall())
    print(db.execute("SELECT uid,boundary_uid,reason FROM pruning").fetchall())
```

使用 `edges` 全表时必须读取 `status`；辅助、待审、历史隔离、环路隔离和裁剪记录均不属于有效分类边。来源记录含原始证据和历史路径元数据，这些路径不构成运行依赖。

V36 的来源范围审核与诊断接口见 [connectivity.md](connectivity.md)。

V36 恢复通过核验的种下分类和分面子类。厂商/品牌/属性以及来源标记的非分类、旧容器记录留在库内；`node_dispositions.tree_admission='NOT_REQUIRED'` 表示其用途无需分类树挂接，`REVIEW` 表示仍待补证。两类都不会进入默认 WordNet 导航。
