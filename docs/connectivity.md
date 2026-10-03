# V35 连接修复与剩余记录

V35 / v1.2.0 使用一个只读 SQLite 数据库。节点身份来自来源 UID；连接必须是有证据支持的类型包含或独立身份对齐。不能从标签相同、目录位置或知识库候选关系推断 `IS_A`。

## 为什么 V34 中有未接通节点

- 一些专业来源的原生分类完整，但它们的上层入口没有连接到合适的 WordNet 词义。
- 旧名称对齐把同名或科学名称相似的对象合并，可能使原本无环的原生分类产生循环；V34 为避免循环隔离了部分分类边。
- OTT 导出时遗漏了非分类/容器标志，部分序列和样本记录因而获得不合适的分类路径。
- FAA/vPIC/EPA 中的厂商、品牌、属性是溯源辅助记录。它们的存在不意味着它们必须成为产品类别。
- 部分 Wikidata 身份没有可接受的分类父边；MeSH/MIMO 的部分关系已经在历史审查中被拒绝，不能仅为连通而恢复。

## 本次结果

| 来源命名空间 | V34 可达 UID | V35 可达 UID | V35 保留 UID |
|---|---:|---:|---:|
| OTT | 3,968,731 | 4,444,068 | 4,529,570 |
| vPIC 型号 | 468 | 31,869 | 31,869 |
| Getty AAT | 2,052 | 3,630 | 3,630 |
| MIMO Hornbostel–Sachs | 0 | 641 | 641 |
| MIMO keyword | 1 | 2,500 | 2,572 |
| Wikidata | 3,201,083 | 3,209,143 | 3,484,448 |

新增接通 589,672 个 UID，撤回 70,156 个不可靠旧可达状态，净增接通 519,516 个。总可达数由 7,955,564 提升到 8,475,080，占 8,916,971 个保留来源 UID 的 95.0%。不同来源 UID 不等于不同现实概念。

- 34 个来源范围核对后的入口接入：OTT 细胞生物、MIMO 完整乐器类别、Getty 工具/设备/建筑等分支。
- OTT `life` 混合容器未直接挂到 organism；仅核对后的细胞生物入口接入。85,098 个带 `not_otu`、`was_container`、`inconsistent` 或 `merged` 标志的记录退出有效分类/身份关系。
- 31,869 条 vPIC 型号边改接 WordNet vehicle。目录包含拖车，来源并不支持把所有型号都认定为 self-propelled motor_vehicle。具体车型的独立身份路径继续保留。
- 224 条与来源原生分类冲突的名称对齐转为 `REVIEW`；原始记录和冲突来源边 ID 留存。不能由环路判定其中每条对齐都错误，因此需要独立标识符与范围复核。
- 全图重新收缩身份、检查环路并重建路径证据；1 条仍循环的分类记录保持隔离。190 对历史隔离关系和 79 个 WordNet 裁剪节点继续屏蔽。

所有 755 个六数据集目标和 59 个 V33 新增节点的实际 WordNet 路径通过；全部 5,591,228 个可达身份组的递减深度、父组和有效边证据通过检查，并额外抽查 500 条新增接通节点的完整路径。详见 [VALIDATION_V35.json](../VALIDATION_V35.json)。这些检查不衡量图像识别准确率，也不替代全部继承断言的逐条语义审查。

## 检查某个节点

```python
from fineatlas import FineAtlas

with FineAtlas("/path/to/fineatlas.sqlite", view="all") as graph:
    print(graph.connection_status("ott:93302"))          # CONNECTED
    print(graph.connection_status("ott:4019065"))        # SOURCE_SCOPE_REVIEW
    print(graph.connection_status("vpic-make:445"))      # AUXILIARY_RECORD
    print(graph.connection_status("mimo-keyword:2205"))  # MISSING_ROOT_CONNECTION
    print(graph.path("ott:93302"))
```

```bash
fineatlas --data-dir /path/to/fineatlas.sqlite connection-status ott:4019065
```

状态还包括 `INSUFFICIENT_HIERARCHY_EVIDENCE`、`IDENTITY_REVIEW`、`HISTORICAL_QUARANTINE` 和 `ARCHIVED`。诊断说明当前快照的证据情况，并不宣称对象永远不能分类。旧 31 文件接口不提供此方法；V34 单库也可使用，来源标志审核信息仅在 V35 中提供。

当前最大分类深度为 48，单库与 CLI 默认 `max_depth=64`；可按需显式指定。身份桥不增加分类深度。一个节点是否可达由全图证据确定，`path()` 的深度参数只是返回路径的搜索/显示限制。

## 剩余清单

剩余 441,891 个 UID 中，264,717 个缺少有效层级证据，10,876 个已有层级但缺根入口，175 个需身份复核，182 个涉及历史隔离；另有 80,843 个辅助记录与 85,098 个非分类/容器来源记录。

分类计数见 [CONNECTIVITY_V35.json](../CONNECTIVITY_V35.json)。完整逐节点 CSV（UID、标签、原因、来源标志）作为 [unconnected_nodes.csv.gz](https://github.com/yyh427/fineAtlas-V1/releases/download/v1.2.0/unconnected_nodes.csv.gz) 发布；它是诊断附件，运行接口只需要数据库。后续补证应生成新快照，保留本次待审与隔离记录。
