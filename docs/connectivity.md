# 连接与使用契约

分类层默认以 WordNet entity 为根，ACTIVE IS_A 形成允许多父的无环 DAG。身份对应独立保存；名字相同不建立 SAME_CONCEPT。准入节点可以属于不连接默认根的独立来源分支；请按所选视图检查实际根路径。

INSTANCE、ATTRIBUTE、DATASET_CATEGORY 使用明确的类型连接，ORGANIZATION 保存来源信息。SOURCE_ONLY 保存未获准入的来源记录，其角色和保留原因分别记录，不统一解释为 UNKNOWN。

统一领域入口是导航视图，汇集经核验的原生根，不产生新的分类或身份关系。领域重叠，生态生境与物理地物等不同维度保留来源范围。

`connection_status(uid)` 与 `path_result(uid)` 使用相同视图和根，分别报告严格分类、原生层次和明确类型连接。训练和评估应使用 `task_labels()` 的逐视图、逐要求准入结果。原生任务标签身份始终保留；NATIVE_LABEL_ONLY 不表示现实类型对应已经核验。

[候选库统计](review_statistics.json)、[候选库验证](review_validation.json)和[各领域边界](review_domains.csv)记录实际范围。原生导航路径存在不表示严格分类可达；结构验证不表示每条科学事实已经认证，也不表示领域已经穷尽。
