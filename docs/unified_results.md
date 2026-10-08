# FineAtlas 1.10.1 候选使用与验收

数据 `v1.10.1-repair-review`；代码 `v1.10.1-repair-code.1`；SDK `1.10.1rc1`；默认视图 `unified`；WordNet 3.1。

数据库修订：`da98222833499cf1bb84ff2f64376e5a4fb0594786e04a29694d5bb86c4b7492`。SHA-256：`62a9190f1330091d84b7259a7ef2865a6ee1d098d860159b6ebec30db5fd5391`。解压字节数：68,495,904,768。

本候选完成通用来源角色修复、四个生活领域入口和四条家具目录配置的有界试接入。新入口组织已有分类及原生专业数据，不把已有 WordNet 类别计为新建概念。原 91 个规范领域及其兼容入口保留，实际领域数为 95。

完整本地验收的 16 项均通过，包含全部领域、原标签、六个数据集全部 56,917 个不同类别对、全图结构及循环、源记录保留、固定非基准样本、全局合同、公开 API、真实 CLI 和聚焦语义检查。两份完整独立重建的逻辑数据与模式一致。实际检查范围与绑定校验值见 [验收汇总](unified_validation.json)、[逐阶段验收](unified_acceptance_status.json) 和 [复建对照](unified_reproduction.json)。实际无认证公网下载、独立安装和完整 16 项复验均通过，记录见 [安装核验](unified_external_verification.md)。公开代码固定到经 CI 和 252 项公开测试验证的提交 `b36616f66bec48a7e47f576739efe88df3b466f6`。

## 标签和视图

| 视图 | 标签 | 当前身份核验 | 根可达 | 路径／状态一致 | 路径准入 |
|---|---:|---:|---:|---:|---:|
| strict | 755 | 752 | 752 | 755 | 752 |
| taxonomy | 755 | 752 | 755 | 755 | 755 |
| unified | 755 | 737 | 755 | 755 | 755 |
| membership | 755 | 752 | 0 | 755 | 0 |

身份确认、根可达和层次路径准入分别统计。路径准入仅表示标签可用于相应视图的层次导航，不等同于训练奖励可用；类别对的奖励准入按下方导出表中的明确类型策略、范围审定和信息性共同祖先独立判定。CRJ-700 保留原生来源层次，但 FGVC 的 family 与 variant 范围不等价，其全球精确型号身份仍待证据；可达不计为身份确认。CUB 仅修复已有证据支持的历史全名和范围映射，其余未确认项继续保留。

## 训练导出

| 数据集 | 全部类别对 | 有效层次项 | 不适用状态及数量 |
|---|---:|---:|---|
| cub200 | 19900 | 8185 | COARSE_COMMON_ANCESTOR_ONLY: 8835; ENDPOINT_NOT_APPLICABLE: 2880 |
| fgvc_aircraft | 4950 | 3028 | ENDPOINT_NOT_APPLICABLE: 1295; IDENTITY_LINEAGE_ROLE_CONFLICT: 415; COARSE_COMMON_ANCESTOR_ONLY: 212 |
| flowers102 | 5151 | 1077 | ENDPOINT_NOT_APPLICABLE: 3071; COARSE_COMMON_ANCESTOR_ONLY: 1003 |
| pets37 | 666 | 638 | COARSE_COMMON_ANCESTOR_ONLY: 28 |
| stanford_dogs | 7140 | 717 | COARSE_COMMON_ANCESTOR_ONLY: 6423 |
| stanford_cars | 19110 | 135 | COARSE_COMMON_ANCESTOR_ONLY: 16336; IDENTITY_LINEAGE_ROLE_CONFLICT: 2639 |

完整对表见 [unified_pairs.jsonl.gz](unified_pairs.jsonl.gz)，四视图逐标签见 [unified_labels.csv](unified_labels.csv)。不适用项保留状态和原因，`applicable=false`、`distance=null`，训练继续保留类别正确性奖励。多父 DAG 使用明确类型策略下全部最低公共祖先，不使用全关系无向最短路。

## 领域和浏览

全部领域根、真实 WordNet synset、原定义和接入依据见 [领域表](unified_domains.csv) 与 [领域路径](unified_domains.json)。生活入口和 ABO 配置身份、许可及范围见 [生活领域](living_domains_v1.10.1.md)。大分支完整分页和相同查询规模的性能对照见 [性能](unified_performance.json)；新连接不代表清空 OS 缓存。

## 证据边界

当前仍有 4,180 条有效导航角色来源记录未取得准入根路径，283 个身份组存在角色差异。它们保留原始来源 UID、声明和证据，不强挂统一根。全量内部台账和失败证据保存在本地交付报告，公开仓库仅展示使用所需的汇总及已验证结果。

候选保留旧正式库和旧候选；它不具备无条件替换正式库的条件。没有运行图像识别或模型训练；结构、接口和范围检查不代表全部来源关系逐条科学认证或识别准确率提高。
