# FineAtlas 1.10.1 正式默认版：结果与证据边界

本地正式数据为 `v1.10.1`、SDK `1.10.1`、默认视图 `unified`、WordNet3.1。**本地正式验收PASS：两源独立提升、匹配浏览索引重建、105张逻辑表／模式比较、103张非浏览表的来源语义保留检查及16阶段完整验收均已通过。本地283项单元测试通过。正式代码CI、公网安装和GitHub main／Latest切换仍为PENDING。** 普通用户的目标流程见 [README](../README.md)，旧1.6和候选的独立安装及回退见 [迁移说明](migration_v1.10.1.md)。

正式数据库的SHA、字节数和revision以 [unified_data.json](../unified_data.json)为准；SDK固定标签／commit以 [unified_code.json](../unified_code.json)为准。此次完整本地验收于2026-10-09 02:42:52 UTC结束，绑定以下正式主库；历史候选SHA不作为正式附件校验。

| 正式主库字段 | 已验收值 |
|---|---|
| release / SDK | `v1.10.1` / `1.10.1` |
| database revision | `1325af79323e77270650075f01bf22d34bbf2f9a072f22cdc651019e615f5b77` |
| SHA-256 | `804192429ffda283da6b509d344778c3ebebbe4f34e59db82c32ea23e9957bc5` |
| 文件字节数 | 68,495,904,768 |

两份正式输出各自从此前独立构建、比较验收的repair主库和复现库提升；来源语义历史namespace保留，正式SDK／版本元数据按审定范围重新冻结，仅重建匹配浏览派生索引。105张逻辑表及模式比较通过；103张非浏览表的来源语义保留比较通过，允许的冻结元数据变化单列，不宣称所有元数据或物理文件逐字不变。精确配方见 [stable_promotion_recipe.md](stable_promotion_recipe.md)。

正式提升沿用已验证的通用来源角色修复、四个生活入口和四条家具目录配置。入口组织已有分类和原生专业记录；9个接入点是既有WordNet synset，不是9个新增类型。原91个规范领域与兼容入口保留，图内容共95个领域；正式版不扩展新来源范围。

原修复候选已完成16阶段完整本地验收、独立复建及实际无凭据公开安装复验。此次正式本地验收以自身代码、文件SHA和revision重新核验并通过：全部95域、755标签四视图、六个数据集56,917个不同类别对、全图结构与循环、原源内容保留、非重点样本、全局合同、实际已安装SDK API、CLI、分页及聚焦修复。源历史和语义记录独立比较；运行时间和物理SQLite布局分别保留。

正式版验收通过状态、实际测试数量和绑定校验值以 [验收汇总](unified_validation.json)、[逐阶段验收](unified_acceptance_status.json)、[复现对照](unified_reproduction.json)及 [外部安装复验](unified_external_verification.md)为准。16个实际阶段均exit0且语义PASS，283项为此次本地测试数；正式代码提交的CI数量及全新公网环境结果仍待独立凭据，不把旧候选的PASS、提交或测试数量当作此次正式结果。

## 标签和视图

以下为此次正式本地验收快照的统计；正式公网复验仍须对照相同快照。根可达、身份和奖励mask分别计数。

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

仍有4180条导航角色来源记录／4180唯一UID未取得准入根路径，对应2976个当前身份组；283个身份组存在角色差异。CUB仍有15个注释范围REVIEW，CRJ-700来源variant/family已验证但精确世界身份继续REVIEW。独立语义断点数量未测；身份组、弱连通分量和断点数量不等价。原UID、声明和证据保留，不强挂统一根。完整内部台账和失败证据留在本地，公开仓库展示使用所需汇总。

正式发布目标是替换普通用户的默认选择；当前远端默认切换仍为PENDING，旧1.6和全部候选的代码、附件与回退路径仍保留。默认unified有意区别于旧strict查询；显式strict用于当前库的严格关系兼容查询，完整历史结果需旧代码和旧库配套固定。

结构、合同、路径、SDK和安装验收不等于每条来源关系／身份独立科学认证，也不解决全部注释范围或视觉奖励校准。没有运行图像识别或模型训练。16阶段runner不自行执行live下载；无凭据下载和全新安装由独立发布流程产生真实凭据。正式版本号不提升world identity flag，也不改变不适用层次项的mask。
