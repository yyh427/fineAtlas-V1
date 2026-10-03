# 数据库结构与 WordNet 导航

FineAtlas V1 使用一个 `fineatlas.sqlite`。Python 和 CLI 通过只读 SQLite 连接查询，数据库无需服务器、模型或其他来源数据库。

| 表或视图 | 用途 |
|---|---|
| `nodes` | 来源 UID、标签、定义、原始元数据、显示状态和身份组 |
| `edges` | 分类及辅助关系、分类轴、来源、证据和状态 |
| `aliases` / `alias_search` | 名称、别名与全文索引 |
| `bridges` | `SAME_CONCEPT` 身份对齐 |
| `evidence` | 分类或身份关系的来源证据及内容哈希 |
| `dataset_targets` | 六个数据集的 755 个类别到 UID 的映射 |
| `components` | 身份组、WordNet 可达性、深度和路径证据 |
| `node_dispositions` | 记录用途、分类准入状态与未接通原因 |
| `pruning` | 默认导航中裁剪的 WordNet UID 及理由 |
| `classification_repairs` / `source_scope_reviews` | 关系准入和来源范围核对记录 |
| `suppressed_edges` / `target_revisions` | 被隔离关系和类别映射的溯源记录 |
| `inputs` / `source_tables` / `archive_*` | 来源导入清单及辅助溯源数据 |
| `active_nodes` / `active_edges` | 全部来源的保留节点和有效分类边，含未接通分支 |
| `wordnet_nodes` / `wordnet_edges` | 从 WordNet 根可达的有效导航视图 |

`nodes.uid` 唯一，不同来源 UID 仍可能表示同一概念。外部引用使用 UID；`component_id` 仅用于库内身份分组。分类边按 **child → parent** 保存。`edges.status='ACTIVE'` 的规范关系为 `IS_A`，原始关系保存在 `original_relation`。

## 分类关系和身份关系

图允许多父节点，是可以按树浏览的无环 DAG。`SAME_CONCEPT` 独立保存在 `bridges`，不属于分类关系，也不增加分类深度。详细路径会显式标注身份步骤。

属性、厂商和部件关系不作为 `IS_A`。待审、辅助、隔离及裁剪记录不进入默认有效分类路径。直接读取 `edges` 全表时必须检查 `status`。

默认使用 `view="wordnet"`。使用 `FineAtlas(path, view="all")` 可以检查尚未接通的来源分支和辅助记录。节点用途与准入状态见 [连接诊断](connectivity.md)。

## WordNet 下位细化

入口为 `wordnet31:00001740-n`（entity）。WordNet 提供通用类型骨架，来源分类补充物种、品种、型号和菜品等细粒度节点。

汽车入口是 `wordnet31:02961779-n`，飞机入口是 `wordnet31:02689427-n`。默认导航分别裁剪 32 和 47 个 WordNet 原细分，由来源原生分类承担下位细化；目标类别、跨来源端点和必要祖先受保护。裁剪记录保存在库内，标记 `PRUNED_WORDNET`。不同词义不会仅因名称相同而合并。

## 直接 SQL

```python
import sqlite3
from pathlib import Path

path = Path("fineatlas.sqlite").resolve()
with sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True) as db:
    print(db.execute("SELECT uid,label FROM wordnet_nodes LIMIT 10").fetchall())
    print(db.execute("SELECT child_uid,parent_uid FROM wordnet_edges LIMIT 10").fetchall())
    print(db.execute("SELECT uid,record_role,tree_admission FROM node_dispositions LIMIT 10").fetchall())
```

来源记录中的原始路径属于溯源元数据，不是运行依赖。一个接口实例用于一个线程或进程，推荐用 `with` 自动关闭连接。
