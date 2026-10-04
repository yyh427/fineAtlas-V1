# 连接与使用契约

分类层以 WordNet entity 为根，ACTIVE IS_A 形成无环 DAG。身份对应独立保存；名字相同不建立 SAME_CONCEPT。所有准入的 CLASS、MODEL_FAMILY、MODEL 和 CONFIGURATION 节点均具有分类根路径。

INSTANCE、ATTRIBUTE、DATASET_CATEGORY 使用明确的类型连接，ORGANIZATION 保存来源信息。它们不混入分类 DAG。SOURCE_ONLY 保存未获准入的来源记录，本体归属仍为 UNKNOWN。

统一领域入口是导航视图，汇集经核验的原生根，不产生新的分类或身份关系。领域重叠，生态生境与物理地物等不同维度保留来源范围。

`connection_status(uid)` 返回准入角色；`path(uid)` 返回分类或类型连接的有证据路径。训练和评估应按角色筛选。原生任务标签身份始终保留；NATIVE_LABEL_ONLY 不表示现实类型对应已经核验。

[当前统计](../CONNECTIVITY.json)与[结构验证](../VALIDATION.json)记录实际导入范围。100% 可达性适用于准入分类层，不覆盖全部来源记录，也不表示各领域已穷尽。
