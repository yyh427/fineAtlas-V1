# FineAtlas 1.10.1 公开接口

正式 `v1.10.1` 的默认视图为 `unified`；两源独立提升、匹配浏览索引重建和16阶段完整本地验收已经通过。[正式Release](https://github.com/yyh427/fineAtlas-V1/releases/tag/v1.10.1)、main／Latest切换和Python3.10／3.12 CI已完成，普通默认clone、全新环境安装及283项测试通过；默认整库下载哈希、stats、安装检查及正式已安装SDK API均通过；九步默认公网流程及完整16阶段回归已实际PASS，全图于2026-10-09 04:27:32 UTC结束。`FineAtlas(path)` 从选定快照读取默认视图；旧快照保留自己的默认。`relation_view='strict'` 或 CLI `--relation-view strict` 显式选择当前角色合同的严格分类视图。完整复现1.6时固定旧代码与旧数据，见 [迁移说明](migration_v1.10.1.md)。构建未完成时拒绝暴露统一查询，外部索引的来源修订必须匹配数据库。

普通正式安装流程默认选择正式清单，统计和安装验证不需要补 `--manifest`、`--expected-validation` 或 `--relation-view unified`。核验使用已经安装的SDK、下载收据及正式验收快照，具体命令见 [README](../README.md)。

## 入口、搜索和浏览

`domains()` 列出规范领域、原生根和别名。`domain(name)` 接受规范名称、别名和 `fineatlas-domain:<name>`，目录入口不属于分类节点。按领域检索与 `domain_page()` 使用相同成员范围；`source:<tag>` 显式选择来源域。

`search_page(text, limit=20, domain=None, node_kind=None, cursor=None, exact=False)` 提供稳定分页。`domain_page()`、`domain_instances()`、`instances_page()` 查询领域成员和实例，旧列表接口通过 `.has_more/.truncated` 报告截断。未知领域在统一视图下返回 `NOT_FOUND/UNKNOWN_DOMAIN`；旧视图保留解释性的参数错误。

`browse_children_page(parent, limit=20, node_kind='CLASS', relation=None, filters=None, cursor=None, include_coarse=False)` 查询直接关系，最多 1,000 条。角色包括 `CLASS`、`BIOLOGICAL_VARIANT`、`MODEL`、`MODEL_FAMILY`（别名 `SERIES`）、`CONFIGURATION`、`INSTANCE`。`PRODUCT_DESIGN` 合并型号与家族角色用于筛选，不更改源角色。

`browse_summary()` 分开返回完整直接关系计数和默认展示计数。`include_coarse=True` 保留显示有证据的直接粗连接。默认偏好仅在完整图中存在核验过的替代细分路径时隐藏展示捷径，不删除源边。

`browse_groups(parent, group_by, ...)` 使用真实制造商、年份、国家等可用字段，明确为目录／属性分组。`locate(text, domain=...)` 和 `browse_location(uid, ...)` 定位搜索结果，不要求使用者预先知道原生 UID。游标绑定快照修订、视图、根和筛选条件，跨条件游标会拒绝使用。

## 身份、路径和状态

`node(uid)`、`identity(uid)`、`aliases(uid)` 保留不同来源 UID、原始标签、原生秩、当前角色及证据。角色不一致的身份组显式返回 `CONFLICT_REVIEW`；同名不会自动合并。

`path_result(uid)`、`connection_status(uid)`、`ancestors_result(uid)` 对缺节点、缺路径、未准入和深度／工作量上限返回明确状态。路径每步保留真实端点、边类型、来源、证据和零成本身份对应。全局确定路径只是一个路径见证，多父图不要求唯一父节点。

`task_path(dataset, class_id)` 遵守冻结的来源／关系策略，例如 CUB 选择 AviList 分类，再通过已核验身份关联其他表示。它与全局路径均保留源 UID，并单独标记训练端点是否适用。

`source_hierarchy(uid, direction='parents', limit=100)` 查看原始来源的直接声明，包括其准入／待审／停用状态，不扩展身份组，不把保留的原始声明自动认证为分类事实。

## LCA、距离和训练

`relation_reward_index(dataset)` 在冻结快照中批量缓存合法祖先，`query(class_id_a, class_id_b)` 查询，`pairs()` 遍历全部不同类别对。

| 策略 | 允许的关系 |
|---|---|
| `classification` | `IS_A`、`TAXONOMIC_PARENT`、`NATIVE_CLASSIFICATION_PARENT` |
| `design` | 上述分类边及 `DESIGN_TYPE_OF`、`NATIVE_DESIGN_PARENT`、`SERIES_MEMBER_OF` |
| `configuration` | 上述设计边及 `CONFIGURATION_OF` |

目录、属性、身份和监管关系不混算成分类深度，`CONFIGURATION_TYPE_OF` 不作为配置谱系距离的捷径。`REGULATED_AS` 仅用于监管导航。源数据声明的未定位／不确定分类放置不会作为可靠奖励边。

`lca(a,b,policy=...)` 返回全部最低公共祖先身份组；多个不可比较的 LCA 全部保留。`distance(a,b,policy=...)` 最小化经有信息量 LCA 的向上边数之和，身份成本为零。在 `unified` 中不支持把混合图无向最短路冒充分类距离。旧视图显式保留历史方向参数，不能直接当作训练奖励。

通用 UID 查询标记 `training_reward=false`：跨领域距离及其量纲没有校准为分类惩罚。训练使用数据集冻结策略，分别检查身份、角色、来源、粒度、循环、祖先身份冲突及共同祖先信息量。不可用返回原因与 `distance=null`，不返回任意最大距离。

`target()` 同时返回原存储的身份声明、当前核验状态、任务准入和映射待审理由。`export_training(dataset, directory)` 输出全部原始标签与全部类别对，并保留无效层次项的掩码；类别正确性奖励始终独立保留。SFT 可使用文本／原标签，RL 必须跳过不适用的层次项并报告覆盖率。

`eligibility()` 和可达性不等于奖励有效性。根可达、无环、能够输出数字均不能独自证明关系语义或训练适用性。

当前修复内容保留 CUB15 个注释范围REVIEW和CRJ-700精确世界身份REVIEW。Cars在configuration策略下135／19110 对适用，其他类别对保留具体原因与 `distance=null`；4180 个未接入来源UID／2976 个身份组及283 个角色冲突组也继续保留。正式版本号与默认视图切换不会自动解决这些范围、身份或视觉校准问题。

节点显示的领域优先由保留的原生领域声明经 `domain_registry`／别名表解析。旧扩展 profile 的领域提示有冲突时，公开 `domain` 使用原生声明，`profile_domain` 保留旧提示，`source_domain` 保留原始字段。领域成员资格仍由同一视图的合法分类／导航范围决定，不把一个显示字段当成分类边或奖励依据。
