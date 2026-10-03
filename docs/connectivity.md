# 节点连接状态与分类准入

FineAtlas V1 中，**8,735,597** 个保留来源 UID 从 WordNet 根可达，占 8,916,979 个保留 UID 的 **98.0%**。来源 UID 数不等于去重后的现实概念数。

六个数据集的 **755/755** 个目标通过根路径检查，每个数据集内部的目标 UID 和身份组均不重复。有效分类图无环，全部 5,852,220 个可达身份组的父组、递减深度和分类证据检查通过。见 [验证报告](../VALIDATION.json)。这些检查验证类别映射和结构，不衡量图像识别准确率或认证全部来源断言。

## 查询状态与路径

```python
from fineatlas import FineAtlas

with FineAtlas("/path/to/fineatlas.sqlite", view="all") as graph:
    print(graph.connection_status("wikidata:Q1002954")) # CONNECTED / ACTIVE
    print(graph.path("wikidata:Q1002954"))
    print(graph.connection_status("vpic-make:445"))     # METADATA_ONLY / NOT_REQUIRED
    print(graph.connection_status("ott:4019065"))       # SOURCE_RECORD_ONLY / NOT_REQUIRED
    print(graph.connection_status("ott:1083295"))       # SOURCE_SCOPE_CONFLICT / REVIEW
```

```bash
fineatlas --data-dir /path/to/fineatlas.sqlite connection-status ott:1083295
```

接口返回接通状态 `status`、原因 `reason`、记录用途 `record_role`、分类准入 `tree_admission`；来源范围记录还带 `source_flags`。

| 分类准入 | 含义 | 使用方式 |
|---|---|---|
| `ACTIVE` | 有效分类节点，可达 WordNet 根 | 用于默认导航及任务类别映射 |
| `NOT_REQUIRED` | 厂商、属性或明确非分类来源记录 | 用于溯源，无需挂入分类树 |
| `REVIEW` | 分类、身份或来源范围证据尚未解决 | 检查证据后再决定是否采用 |

仅有来源 `inconsistent` 标志不足以把记录判为非分类对象。`NOT_REQUIRED` 记录仍留在同一数据库中，可查询来源和辅助关系。

默认 `view="wordnet"` 浏览已接通节点；`view="all"` 检查全部保留记录。`path()` 默认分类深度上限为 64，可以显式增加；身份桥不增加分类深度。

## 可查询的示例

| UID | 类别 |
|---|---|
| `wikidata:Q1002954` | Formula One car |
| `wikidata:Q1025029` | Cachena 牛品种 |
| `wikidata:Q1002275` | Bugatti Model 100 飞机 |
| `wikidata:Q10328349` | square watermelon |
| `wikidata:Q10561609` | corpse detection dog |
| `wikidata:Q1057750` | radish |
| `wikidata:Q248608` | Lycidae 甲虫类群 |

训练或浏览时以 UID、实际路径和边证据为依据。名称相同、属于同一厂商或具有同一属性，不足以推断类别身份相同或存在父子分类关系。

## 未接通记录

| 原因 | UID 数 | 分类准入 |
|---|---:|---|
| `MISSING_ROOT_CONNECTION`：已有层级，根入口尚缺 | 4,717 | REVIEW |
| `CLASSIFICATION_REVIEW`：分类证据待审 | 10,467 | REVIEW |
| `INSUFFICIENT_HIERARCHY_EVIDENCE`：缺层级证据 | 28 | REVIEW |
| `IDENTITY_REVIEW`：身份待审 | 47 | REVIEW |
| `SOURCE_SCOPE_CONFLICT`：来源范围冲突 | 1,270 | REVIEW |
| `HISTORICAL_QUARANTINE`：关系隔离 | 182 | REVIEW |
| `SOURCE_NON_TAXON_OR_CONTAINER`：非分类/容器记录 | 83,828 | NOT_REQUIRED |
| `AUXILIARY_RECORD`：厂商、品牌、属性 | 80,843 | NOT_REQUIRED |

合计 181,382 个未接通 UID，其中 **16,711 个待审**，**164,671 个用于来源或辅助溯源**。计数见 [连接诊断报告](../CONNECTIVITY.json)。完整 [unconnected_nodes.csv.gz](https://github.com/yyh427/fineAtlas-V1/releases/download/v1.3.0/unconnected_nodes.csv.gz) 包含 UID、标签、原因、来源标志、记录用途和分类准入，是可选诊断附件。运行接口只需要数据库。
