# FineAtlas V1 连接修复与剩余记录

FineAtlas V1 使用一个只读 SQLite 数据库，默认以 WordNet 根浏览。来源 UID、定义和证据留存，身份对齐与分类关系分别表达。

## 修复结果

WordNet 可达来源 UID 从 V35 的 8,475,080 增至 **8,735,597**，占 8,916,979 个保留来源 UID 的 **98.0%**。新增接通 260,509 个原有 UID，另新增 8 个车型/配置 UID，没有原已接通 UID 失去根路径。不同来源 UID 可能代表同一现实概念。

- 恢复 254,335 条范围核对后的分类边：包括正式种下分类，以及有定义证据的分面子类。另有 28,072 条候选保持待审。
- 补齐 77 个有来源定义支持的分支入口，涉及动物品种、植物、食物、航空器等。
- 撤回 488 条粗细范围不一致的车辆身份桥与 248 条不成立的变体父边，保留原有独立车型父路径。
- 为 Aston Martin Virage Coupe/Volante 和 Spyker C8 Spyder/Laviolette 补入 4 个独立车身型号与 4 个独立年款配置节点。Stanford Cars 类别 10、11、179、180 改用独立配置 UID，标签不变；旧映射留在 `target_revisions`。
- 190 对历史隔离关系、79 个 WordNet 裁剪节点和原有 1 条循环记录继续屏蔽；全图复核无新增循环。

车辆年款与车身证据保留来源 URL、文档作者和冻结哈希；厂商的商品页面提供型号字段，实例 VIN 不成为分类节点。车型目录与配置类别的范围不同，相关记录不能直接视为 `SAME_CONCEPT`。

六个数据集的 **755/755** 个目标通过根路径检查，且每个数据集内部的目标 UID 和身份组均唯一；59 个 V33 新增节点保留并通过路径检查。全部 5,852,220 个可达身份组的父组、递减深度和有效分类证据通过检查，并抽查 500 条新增接通节点的完整路径。详见 [验证报告](../VALIDATION_V36.json)。检查不衡量图像识别准确率，也不替代全部继承来源断言的逐条语义审查。

## 先前未接通的示例

以下节点在 FineAtlas V1 均能返回实际 WordNet 根路径：

| UID | 示例 |
|---|---|
| `wikidata:Q1002954` | Formula One car |
| `wikidata:Q1025029` | Cachena 牛品种 |
| `wikidata:Q1002275` | Bugatti Model 100 飞机 |
| `wikidata:Q10328349` | square watermelon |
| `wikidata:Q10561609` | corpse detection dog |
| `wikidata:Q1057750` | radish |
| `wikidata:Q248608` | Lycidae 甲虫类群 |

训练或浏览时使用实际返回的路径与证据，不要把同名词、属性、厂商和部件强制变成分类父节点。

## 检查某个节点

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

`connection_status()` 返回 `status`、`reason`、`record_role`、`tree_admission`、`source_flags`。已接通节点为 `CLASSIFICATION_NODE` / `ACTIVE`；明确辅助记录为 `NOT_REQUIRED`；证据尚未解决为 `REVIEW`。`NOT_REQUIRED` 只说明该记录当前用途不需要分类挂接，不会删除它或其溯源关系。仅有来源冲突标记不足以判定为非分类记录。

默认 `view="wordnet"` 浏览已接通节点；`view="all"` 检查全部保留记录。`path()` 默认分类深度上限 64，可显式增加；身份桥不增加分类深度。旧 31 文件接口不提供此诊断方法，V34/V35 单库兼容接口，但不含 FineAtlas V1 的用途准入字段表。

## 剩余记录

| 原因 | UID 数 | 分类准入 |
|---|---:|---|
| `MISSING_ROOT_CONNECTION`：已有层级，根入口尚缺 | 4,717 | REVIEW |
| `CLASSIFICATION_REVIEW`：分类证据待审 | 10,467 | REVIEW |
| `INSUFFICIENT_HIERARCHY_EVIDENCE`：缺层级证据 | 28 | REVIEW |
| `IDENTITY_REVIEW`：身份待审 | 47 | REVIEW |
| `SOURCE_SCOPE_CONFLICT`：来源范围冲突 | 1,270 | REVIEW |
| `HISTORICAL_QUARANTINE`：历史隔离 | 182 | REVIEW |
| `SOURCE_NON_TAXON_OR_CONTAINER`：明确非分类/容器记录 | 83,828 | NOT_REQUIRED |
| `AUXILIARY_RECORD`：厂商、品牌、属性 | 80,843 | NOT_REQUIRED |

合计 181,382 个未接通 UID，其中 **16,711 个待审**，**164,671 个仅作来源或辅助记录**。未接通不等于同一类问题，也不能只为连通率恢复被拒绝的分类关系。

计数见 [连接诊断报告](../CONNECTIVITY_V36.json)。完整 [unconnected_nodes.csv.gz](https://github.com/yyh427/fineAtlas-V1/releases/download/v1.3.0/unconnected_nodes.csv.gz) 包含 UID、标签、原因、来源标志、记录用途和分类准入。它是诊断附件，运行时只需数据库。来源定义与正式种下名称范围的规则分别见 [ICZN Article 5](https://code.iczn.org/chapter-2-the-number-of-words-in-the-scientific-names-of-animals/article-5-principle-of-binominal-nomenclature/) 和 [ICN Article 24](https://www.iapt-taxon.org/nomen/pages/main/art_24.html)；候选知识库父关系自身不构成准入证明。后续补证生成新快照，保留本次待审与隔离记录。
