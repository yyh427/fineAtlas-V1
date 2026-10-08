# FineAtlas V1

FineAtlas 是保留来源 UID、原生分类、产品家族／型号／配置及命名实例的本地 SQLite 图数据库。本分支的 SDK 是 `1.10.0rc1`，统一候选为 `v1.10.0-unified-review`，查询视图固定为 `unified`。候选与正式版本分开发布，不覆盖旧库。

## 固定代码和数据

候选清单为 [unified_data.json](unified_data.json)，包含分发附件、完整数据库 SHA-256、图修订、默认视图和索引版本。最终核验结果、代码版本及未确认项见 [统一层次结果](docs/unified_results.md)。不要将 PyPI 中其他版本的 SDK、旧数据库或 `v1.9` 浏览索引与本候选混用。

```bash
# 在本候选对应的 GitHub tag / commit 中执行
python3 -m pip install .
python3 scripts/download_single.py --manifest unified_data.json \
  --output-dir /path/to/fineatlas-unified
fineatlas --data-dir /path/to/fineatlas-unified --relation-view unified stats
```

下载器检查每个附件和完整数据库的大小、SHA-256、默认视图及图／浏览索引修订；拒绝覆盖已有不同哈希的库。需要 Python 3.10+、SQLite 和解压工具 `zstd`，查询不需要 GPU、API key 或数据库服务。

旧正式版使用 [single_download.json](single_download.json) 单独下载。历史 `v1.8.1` 和 `v1.9` 清单与报告继续保留，它们不代表本候选的验收结果。

## 视图和关系

统一骨架选择 WordNet **3.1** 的大类及其必要上层路径。使用的 synset、定义、来源校验值和领域接入依据保存在数据库的 `unified_backbone_nodes`、`unified_wordnet_usage`、`unified_domain_rules` 中；各领域的原生 UID 和细分结构保留。

| 视图 | 意义 |
|---|---|
| `unified` | 本候选的默认视图：选定 WordNet 骨架、原生类型／生物分类及分角色导航 |
| `strict` | 当前角色合同下准入的严格 `IS_A`；明确指定以兼容旧查询 |
| `taxonomy` | 原有原生分类视图，保留 `TAXONOMIC_PARENT`、`NATIVE_CLASSIFICATION_PARENT` |
| `membership` | 独立来源成员视图，通常需要指定原生局部根 |

`SAME_CONCEPT` 解析经核验的等价来源表示，成本为零，不增加分类深度。`IS_A` 表示普通类型包含；生物或专业来源父级保留原始关系语义。`DESIGN_TYPE_OF`、`NATIVE_DESIGN_PARENT`、`SERIES_MEMBER_OF`、`CONFIGURATION_OF`、`INSTANCE_OF` 分别导航设计、系列、配置和实例。`REGULATED_AS` 是监管目录导航，不参与分类／设计距离奖励。目录、制造商、年份和其他属性分组不会转成 `IS_A`。

允许合理多父关系。入口 `fineatlas-domain:<domain>` 是导航目录，不作为普通类别进入分类 DAG。`source_hierarchy()` 可查看保留的原始来源声明，包含未准入的记录及处置状态。

## 查询

```python
from fineatlas import FineAtlas

with FineAtlas('/path/to/fineatlas-unified/fineatlas.sqlite',
               relation_view='unified') as tree:
    print(tree.metadata['release'], tree.metadata['database_revision'])
    print(tree.domains())
    print(tree.browse_children_page('aircraft', limit=20))
    print(tree.browse_children_page('aircraft', limit=20, node_kind='MODEL'))
    print(tree.locate('albatross', domain='birds', limit=10))

    target = tree.target('cub200', '1')
    print(target)
    print(tree.task_path('cub200', '1'))
    print(tree.connection_status(target['target_uid']))
    print(tree.ancestors_result(target['target_uid']))

    reward = tree.relation_reward_index('cub200')
    print(reward.query('1', '2'))
    tree.export_training('cub200', '/path/to/cub-training')
```

`path_result()` 展示统一视图的确定性路径；`task_path()` 还遵守对应数据集的来源和关系策略。CUB 的训练查询选择 AviList 原生分类，其他来源 UID 通过核验身份解析进入同一体系。每一步保留原始 UID、来源和边类型。路径、连接状态和任务准入使用同一指定视图，但它们与奖励适用性分别报告。

`browse_children_page()` 查询直接关系，默认单页 20 条，最多 1,000 条，采用确定排序、索引和版本绑定游标。型号、家族、配置、实例可分别筛选。`include_coarse=True` 显示保留的粗连接；默认浏览优先显示有真实替代细分路径的关系。`browse_groups()` 提供制造商、来源字段、年份等目录分组，返回结果明确标注为属性浏览。

## 纯文本 SFT 和 RL

755 个原始标签继续保留。身份确认、统一骨架接入、合法原生路径、特定关系奖励适用性是四项独立检查。

```bash
python3 scripts/export_text_training.py \
  --database /path/to/fineatlas-unified/fineatlas.sqlite \
  --output /path/to/text-training
```

导出包含原标签、节点角色、来源、任务路径及奖励有效性／原因。所有不同类别对均输出，不能用于层次奖励时 `applicable=false`、`distance=null`；训练端跳过该层次项，继续保留类别正确性奖励。

LCA 返回明确关系策略下全部最低公共祖先身份组。距离为经有信息量 LCA 的最小向上边数之和；身份步为零。不使用所有关系的无向最短路。只有领域大类等过宽共同祖先、身份／粒度未确认、祖先身份组角色冲突或视图不适用时，不制造最大错误距离。跨领域通用 UID 查询没有校准为分类错误奖励。

不同数据集的策略和覆盖率见最终结果报告。合法路径不代表该类全部类别对适合训练，也不代表实际识别能力已经验证。

## 重建、验收和恢复

[构建与恢复说明](docs/unified_build.md) 给出冻结输入、基线、构建步骤和检查点。实现复用既有 Migration、图缓存和浏览索引格式。生产库、旧候选、原始来源和原始标签历史不覆盖；大数据库和原始大文件不提交 Git。

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 scripts/audit_unified_candidate.py \
  --database /path/to/fineatlas-unified/fineatlas.sqlite \
  --baseline /path/to/v1.8.1/fineatlas.sqlite \
  --samples /path/to/frozen-nonfocus-samples.json \
  --output /path/to/unified-audit
python3 scripts/audit_unified_browsing.py \
  --database /path/to/fineatlas-unified/fineatlas.sqlite \
  --baseline /path/to/v1.9/fineatlas.sqlite \
  --output /path/to/browse-audit
```

完整接口规则见 [public_api.md](docs/public_api.md)，来源授权与新增证据说明见 [DATA_SOURCES.md](DATA_SOURCES.md)。本轮不运行图像识别、视觉模型训练或图像推理；结构、语义抽查和接口检查不能表述为全部科学事实已逐条认证。
