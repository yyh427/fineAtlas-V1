# FineAtlas V1

FineAtlas 是保留来源 UID、原生分类、产品家族／型号／配置及命名实例的本地 SQLite 图数据库。正式版为 `v1.10.1`，SDK `1.10.1`，默认查询视图为 `unified`。原 `v1.6.0` 和所有候选继续保留，可独立安装与回退。

**正式发布及完整公网复验PASS：** [正式Release](https://github.com/yyh427/fineAtlas-V1/releases/tag/v1.10.1)已公开并设为Latest，main已更新为正式默认版；[main CI](https://github.com/yyh427/fineAtlas-V1/actions/runs/37879689603)的Python3.10／3.12均通过。正式版已完成两源独立提升、匹配浏览索引重建、105张逻辑表／模式比较、103张非浏览表的来源语义保留检查和16阶段完整本地验收。普通默认main clone、全新环境安装与283项测试已实际通过；六分片无认证默认下载的SHA均通过。整库SHA／字节数、默认stats、安装检查及实际已安装SDK的95域／755标签四视图／56,917对API复验均通过，九步默认公网流程及完整16阶段回归均已实际PASS；全图回归于2026-10-09 04:27:32 UTC结束。凭据见 [实际公网复验](docs/unified_external_validation.json)。

## 默认下载与使用

需要 Python 3.10+ 和解压工具 `zstd`（Linux 可用 `apt install zstd`，macOS 可用 `brew install zstd`）。查询使用 Python 标准库和 SQLite，不需要 GPU、API key 或数据库服务器。

图数据库约68.5GB；分片和临时解压还需空间，建议数据盘预留90GB以上。正式文件大小以清单的 `database.bytes` 为准。升级时为新版本选择新目录，保留旧库。

四个生活入口和家具目录配置的范围说明见 [生活领域](docs/living_domains_v1.10.1.md)。

正式默认流程不需要指定 Git 分支、下载清单或查询视图：

```bash
git clone https://github.com/yyh427/fineAtlas-V1.git
cd fineAtlas-V1
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install .
python3 scripts/download_single.py --output-dir ./data
fineatlas --data-dir ./data stats
python3 scripts/check_installation.py --data-dir ./data
python3 scripts/verify_unified_install.py \
  --database ./data/fineatlas.sqlite --output ./verification
```

预期 `stats` 显示数据版本 `v1.10.1` 和默认视图 `unified`；SDK `1.10.1` 由安装检查核验。下载器默认读取当前代码的正式 [unified_data.json](unified_data.json)，逐片与流式解压核对大小、SHA-256、版本和修订，拒绝覆盖不同哈希的已有库。安装检查使用实际已安装 SDK，核对数据收据、图／浏览索引与代码，再运行代表查询；完整安装复验对照当前正式验收快照。

精确 SDK 标签／commit 见 [unified_code.json](unified_code.json)，数据清单独立固定数据库和附件。正式版从已验收修复候选独立提升并重新冻结，不能把候选数据库与正式版代码混装。结果与限制见 [统一层次结果](docs/unified_results.md)。

需要旧版本时，显式指定 [v1.6.0 清单](legacy_single_download_v1.6.0.json) 并使用另一数据目录；候选也必须显式选择其清单。完整旧代码／数据安装、从 1.6 迁移和回退步骤见 [版本迁移](docs/migration_v1.10.1.md)。旧版本和候选都不因正式发布而删除。

## 视图和关系

统一骨架选择 WordNet **3.1** 的大类及其必要上层路径。使用的 synset、定义、来源校验值和领域接入依据保存在数据库的 `unified_backbone_nodes`、`unified_wordnet_usage`、`unified_domain_rules` 中；各领域的原生 UID 和细分结构保留。

| 视图 | 意义 |
|---|---|
| `unified` | `v1.10.1` 的默认视图：选定 WordNet 骨架、原生类型／生物分类及分角色导航 |
| `strict` | 当前角色合同下准入的严格 `IS_A`；明确指定以兼容旧查询 |
| `taxonomy` | 原有原生分类视图，保留 `TAXONOMIC_PARENT`、`NATIVE_CLASSIFICATION_PARENT` |
| `membership` | 独立来源成员视图，通常需要指定原生局部根 |

`SAME_CONCEPT` 解析经核验的等价来源表示，成本为零，不增加分类深度。`IS_A` 表示普通类型包含；生物或专业来源父级保留原始关系语义。`DESIGN_TYPE_OF`、`NATIVE_DESIGN_PARENT`、`SERIES_MEMBER_OF`、`CONFIGURATION_OF`、`INSTANCE_OF` 分别导航设计、系列、配置和实例。`REGULATED_AS` 是监管目录导航，不参与分类／设计距离奖励。目录、制造商、年份和其他属性分组不会转成 `IS_A`。

从 1.6 升级时，默认 `unified` 是有意变化。需要严格关系查询可显式加 `--relation-view strict`，或在 Python 中传 `relation_view='strict'`。要完整复现 1.6 的旧输出，还应固定 1.6 代码与旧数据库；新库的显式 `strict` 不承诺逐字复现所有旧结果。

允许合理多父关系。入口 `fineatlas-domain:<domain>` 是导航目录，不作为普通类别进入分类 DAG。`source_hierarchy()` 可查看保留的原始来源声明，包含未准入的记录及处置状态。

## 查询

```python
from fineatlas import FineAtlas

with FineAtlas('/path/to/fineatlas-unified/fineatlas.sqlite') as tree:
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

当前保留的限制包括 CUB **15** 个注释范围 REVIEW、CRJ-700 已验证来源层次但世界精确身份仍 REVIEW；Cars **19,110** 对中只有 **135** 对适用于层次奖励。仍有 **4,180** 个未接入导航来源 UID，对应 **2,976** 个身份组，以及 **283** 个身份角色冲突组。身份确认、根可达和奖励 `applicable` 分开检查；不适用的层次项跳过并保留类别正确性奖励。

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
