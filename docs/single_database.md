# 单数据库结构

所有分类、实例、别名、证据和数据集目录位于同一个 SQLite 文件，运行时不需要外部服务。

| 表/视图 | 内容 |
|---|---|
| `nodes` | 原生 UID、标签、定义、来源、可见性、身份组 |
| `aliases` / `alias_search` | Unicode 别名、原生型号编号及全文检索 |
| `edges` / `active_edges` | 来源关系及有效 `IS_A` 分类记录；方向 child → parent |
| `bridges` | 经审查的 `SAME_CONCEPT`，独立于分类边 |
| `components` | 身份组、分类根可达性、递减深度和路径证据 |
| `node_profiles` | 扩展记录的节点种类、领域、来源及 JSON 参数；旧来源仍使用原生 rank/data |
| `entity_relations` | `INSTANCE_OF`、`ATTRIBUTE_KIND_OF`、`DEPICTS_TYPE`、`LOCATED_IN` 等明确关系 |
| `entity_connections` / `connected_entities` | 已连接的实例、属性、任务类别与类型路径证据 |
| `dataset_targets` | 13 个目录的 1,822 个原生类别和映射状态 |
| `dataset_catalogs` | 原生标签目录的来源、哈希、类别数和语义范围 |
| `evidence` | 证据编号、来源链接、原生字段和记录摘要 |
| `domain_entries` / `domain_entry_roots` | 每领域一个导航入口及各原生分类根 |
| `admission_decisions` / `task_mapping_admissions` | 来源记录和任务标签的准入用途 |
| `metadata` | 当前统计、领域入口、数据集与验证信息 |
| `normalization_roles` / `usability_changes` | 原始角色、规范决定、保留的先前角色与变更证据 |
| `node_names` / `node_definitions` / `node_taxon_ranks` | 有来源和语言的名称、独立定义及原生分类阶元 |
| `domain_registry` / `domain_aliases` / `domain_members` | 规范入口、兼容别名和逐视图成员范围 |
| `view_roots` / `view_paths` / `view_terminal_connections` | 严格或原生分类路径、混合路径和类型连接的分别索引 |
| `pruning` / `suppressed_edges` | 裁剪与隔离记录，保留原始身份但不激活不合格分类 |
| `wordnet_nodes` / `wordnet_edges` | 分类根可达的导航投影 |

扩展节点使用 `CLASS`、`MODEL_FAMILY`、`MODEL`、`INSTANCE`、`ATTRIBUTE`、`DATASET_CATEGORY`、`ORGANIZATION` 或 `UNKNOWN`。`node_profiles` 不覆盖全部继承来源；接口按原生 rank 补充显示种类，混合或未确认型号保留 UNKNOWN。

参数是结构化文本事实，不提供图片。GeoNames 坐标采用 WGS84；海拔、区域字段仅在原生记录存在时保留。国家归属连接按来源字段保存，不保证唯一归属或独立的边界裁定。

产品 UID 保留目录意义：Apple 按原生条目与年份区分，复用的硬件编号是别名；Canon 使用博物馆原生目录编号；GeForce 表示显卡产品规格，厂商伙伴板卡身份不自动等同；SSD 容量变体是参数。不同目录的同名型号不按名字自动合并。

类别编号保持目录的原生编号范围。场景任务标签不是物理类型的 `IS_A` 子类；在定义范围一致时，使用 `DEPICTS_TYPE` 指向被描绘类型。NATIVE_LABEL_ONLY 保留任务身份，不能作为已审查现实类型映射使用。

数据库推荐只读访问。接口使用不可变只读连接，更新数据库后应关闭并重新打开接口实例。下载分片合并解压后只有一个文件，分片不是多个数据库。

## 关系视图

`active_edges` 仅包含严格有效的 `IS_A`。接口的 `taxonomy` 视图另包含已准入的 `TAXONOMIC_PARENT` 和 `NATIVE_CLASSIFICATION_PARENT`；`membership` 只包含 `REUSABLE_TYPE_MEMBERSHIP`。`components` 中的可达性和路径证据以严格视图计算，候选库的逐视图索引分别保存在 `view_*` 表中。`BIOLOGICAL_VARIANT` 标记原生无阶元的菌株等记录，`native_rank` 保留原始阶元；该角色不进入严格分类 DAG。

本分支使用 v1.8.1-hierarchy-review 候选库，文件与哈希见 [review_data.json](../review_data.json)。`single_download.json` 保留正式版 v1.6.0 下载配置；候选库使用独立清单和新目录安装。精确统计见 [review_statistics.json](review_statistics.json)，查询与训练要求见 [public_api.md](public_api.md)。
