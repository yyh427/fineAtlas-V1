# 1.11 结构修复与范围迁移

本轮以发布的 1.10.1 数据和 SDK 为冻结对照，原始库 SHA-256 为 `804192429ffda283da6b509d344778c3ebebbe4f34e59db82c32ea23e9957bc5`。实际盘点为 95 个领域入口。候选在独立目录构建；旧版本、来源和标签历史保留。最终验收和公开下载的结果由本版本交付报告与精确产物清单给出。

## 身份、标签和关系

来源 UID 保持自身范围。同名、同品牌、同型号字符串不构成跨来源身份等价证明。撤销准入保留原桥的来源声明和历史；经证实范围不同的拆分与证据不足的等价待审分别统计。标签映射待审只影响该映射，现实对象及其合法关系继续保留。

`dataset_targets` 保持旧世界对象接口；`dataset_scope_targets` 存作者原生标签身份、命名空间、版本、角色和证据。`dataset_mapping_history` 及既有目标历史保留修改前记录。原生标签确认不等于全球对象身份确认。

航空器原生 family/variant、EPA 原生 model/baseModel、型号类型、配置、物种、品种及命名实例分别保存。FGVC 制造商为来源目录；商品品牌为 `brand` 分面，不能冒充 `manufacturer`。FCI 组织分组使用 `source_groups` 和 `source_group_members`，不进入分类或设计距离。

## 路径与分辨率

旧接口默认 `admission_mode='legacy'`，旧策略冻结于 `unified_reward_policies`。`reviewed_paths` 显式要求合法任务边界路径，只隔离不安全的祖先分支；不能借别的路径绕过未确认端点、非法关键关系或不兼容来源。返回实际路径、来源证据、关系及排除原因。统一根可达、任务边界可达和任务路径有效分别报告。

默认审阅策略使用 `native-taxonomic-rank-and-physical-type-floors-v4`：CUB 的固定 AviList 目级及更高真实父链、Flowers 的固定 WFO 目级及更高真实父链作为粗层门槛，共 299 个有原始 UID 和证据的门槛。科、属及合法的更细共同祖先单独统计。原 `reviewed_reward_policies_v1` 和 `unified_reward_policies` 完整保留，报告分别列旧策略、旧门槛审阅路径和新级别门槛；规则增益不计为新增知识。

新的返回分辨率为 `FINE_VALID`、`COARSE_VALID`、`UNCERTAIN`、`NOT_APPLICABLE`。粗层共同祖先可以有效存在，层次奖励距离仍为 `null`。不得用零或最大惩罚替代无效值。

Pets/Dogs 的任务边界均为 animal，以保留真实野生犬科标签。细层比较采用共同的家犬、家猫粗门槛及其上级；组织分组不作为生物距离。旧各域不同门槛的结果和 animal-only 敏感性结果单列，不当作新增品种知识。

Flowers/CUB 可显式使用来源标签投影：`DEPICTS_TYPE` 加审定分类关系；不是纯 `IS_A` 距离，也不确认唯一现代物种。颜色限定标签保持有植物范围的作者类别，`HAS_ATTRIBUTE` 不进入距离。

```python
from fineatlas import FineAtlas

with FineAtlas('/data/fineatlas/fineatlas.sqlite', relation_view='unified') as tree:
    old = tree.relation_reward_index('flowers102')
    native = tree.relation_reward_index(
        'flowers102', admission_mode='reviewed_paths', target_scope='source_native',
        source_namespace='oxford-flowers102', source_version='2008-categories-20261009')
    print(tree.task_path('flowers102', '96', index=native))
    tree.export_training('flowers102', '/data/fineatlas/flowers-native',
        admission_mode='reviewed_paths', target_scope='source_native',
        source_namespace='oxford-flowers102', source_version='2008-categories-20261009')
```

CUB 原生 namespace 为 `caltech-cub200-2011`，版本 `2011-author-metadata-20261009`；Aircraft 为 `fgvc-aircraft-2013b`，版本 `2013b`。保留完整 755 个类别标签；未审定的层次项不删除类别准确率监督。

```sh
fineatlas --data-dir /data/fineatlas task-path flowers102 96 \
  --admission-mode reviewed_paths --target-scope source_native \
  --source-namespace oxford-flowers102 --source-version 2008-categories-20261009
fineatlas --data-dir /data/fineatlas source-groups-page --namespace fci-nomenclature
fineatlas --data-dir /data/fineatlas browse-page 家具 --node-kind CONFIGURATION --limit 20
```

FCI namespace 的精确冻结值以 `source_organization_group_scope` 元数据为准；不指定 namespace 可浏览全部已有组织目录，避免把示例名当作来源 UID。

## 生物范围

原先 2,491 个单个科学名称命中的 WordNet 词义逐个检查完整定义；其中 9 个实际描述多个栽培品种或杂交集合，撤销单一物种级别并保留 `WHOLE_DEFINITION_SCOPE_REVIEW`。剩余 2,482 个只修复科学级别，不合并身份或自动确认数据集范围。另有 29 个词义命中多个不同 WFO 物种 UID，保留 `MULTI_SPECIES_SCOPE_REVIEW`。合计 38 个范围待审项不能通过其他表示继承级别，原始 UID、定义及普通导航继续保留。

Flowers 的现代来源父链和 plant 任务边界、sweet pea 的混合来源父链，以及 CUB 历史名称/现代拆分/宽标签逐项记录。camellia、anthurium 等缺少作者唯一物种范围的映射保持待审，作者原生标签仍可按审定属或更宽范围查询。没有为提高覆盖率制造中间分类或选择多数物种。

## 生活领域接入

完整 ABO 元数据归档共 147,702 行，未重复下载图像或 3D 资产。本轮核对原有入口和旧四条配置后，接入 4,527 个来源商品配置：家具 3,021、照明 700、箱包 644、厨具餐具 138、玩具 18、手工具 6。这些不是新增普通类别、全球型号或物理实例。原四条配置补同口径的字段索引，原载荷和关系不改写。

22 个原生产品类型经过标题、目录路径及 WordNet 定义联合审核；569 条更细类型连接只在证据吻合时接入。带靠背的 stool 连接到普通 seat，明确多人的 chair 类目录商品也保留 seat 范围；不误挂单人 chair 或无背无扶手的 stool。混合家具套装、收纳配件和电脑袖袋等歧义条目隔离审查。照明冲突记录保留普通 lamp 范围。

品牌、材料、颜色、原生产品类型、型号字符串和目录路径作为来源分面保存，不据此推断身份或设计血缘。五个指定领域已有真实入口和普通细类，本轮补配置表示及可检索字段；全域覆盖报告分别列普通细类、系列、型号、配置和实例。

## 可复现构建

准备脚本读取真实来源并输出冻结输入；构建器不下载或猜测来源。在有足够空间的数据盘建立两套独立副本，严禁生产库、已有候选或硬链接互相覆盖。

```sh
cp --reflink=auto --sparse=always --no-clobber BASELINE/fineatlas-primary.sqlite CANDIDATE/fineatlas.sqlite
TMPDIR=CANDIDATE/tmp PYTHONHASHSEED=0 python -B scripts/build_structure_candidate.py \
  --baseline BASELINE/fineatlas-primary.sqlite --database CANDIDATE/fineatlas.sqlite \
  --inputs FROZEN_INPUTS --reports CANDIDATE/reports --browse-staging CANDIDATE/browse.sqlite
```

`build_complete.json` 仅说明构建完成。必须另外执行独立原始 SQL 来源保留、全图无环与角色合同、全领域入口/分页、完整标签及类别对、生活领域真实落库/导出、逻辑复现比较、安装和公开下载复验。对完整未公开的冻结输入仅有哈希时，不能声称公众可无输入重建；本轮发布清单说明实际公开的输入及来源约束。

## 全领域来源范围合同

冻结输入逐个保留原始声明定位、完整来源主体、字段含义、角色范围和修改历史；适配器不通过名称末词、标题提及、品牌或兼容字段推断类型。8.1 万条范围不成立或证据不够的旧声明隔离待审；其中 13,799 条转换后的原生设计父声明仍全部待审，保留原来源而不冒充设计血缘。实际实施数量由正式候选的独立 SQL 验收报告给出。

冻结 v6 包含 12,896 条有完整主体与父类型范围证据的方向关系，210 条 Apple 官方商业产品线成员关系，以及 26 个来源目录、5,809 个保留自身 UID 的目录成员。来源目录不是新普通类别或世界设计系列：NVIDIA 兼容设备目录含完整多 GPU 系统，Canon/Intel 目录也不能自动当设计父链。`browse_domain(...)["source_directories"]` 返回目录及关系类型；`source_groups` 的组织分类与来源目录明确区分。255 个自身 family 范围不够的替代类型连接全部撤回，不能借另一祖先分支绕行。

构建安全入口要求 `structure_protected_paths.json` 固定生产库和封存来源检查点的绝对位置与 SHA-256；候选必须是独立 inode，生产库路径、硬链接或伪造 CLI baseline 均拒绝。`python -O` 和 `PYTHONOPTIMIZE` 不能用于构建或验收。外部独立构建回执绑定唯一 build ID、全部阶段、代码/输入清单及哈希；复现检查逐个比较实际表库存，只排除 SQLite 明确标识的 FTS 重复内容和有记录的运行时阶段数据。

`build_complete.json` 后仍需 `accept_structure_candidate.py local` 完整检查；公开下载安装证据必须包含真实下载 URL、文件 SHA、实际安装 SDK 和完整公共查询/导出复验报告。局部通过仅允许上传明确标记的预发布候选，不允许推荐稳定版本。

交付工具的独立小库拒绝回归见 [发布凭据检查](structure_current_delivery_guard_validation.json)、[保护路径和缓存检查](structure_current_build_safety_validation.json)及[完整复现比较检查](structure_compare_reproductions_fix_validation.json)。这些是工具回归，不能替代正式大库验收或真实公网下载。公开下载回执区分真实 HTTP(S) 网络传输、断点续传及缓存恢复；缓存、`file://` 和仅解压本地分片均不能声称本轮重新公开下载。安装 SDK 检查必须绑定同一个下载文件路径、文件状态和整库 SHA。

猫犬的细层门槛同时包含固定 VBO 2026-04-15 的通用 `Cat breed` / `Dog breed` 概念及宿主 `Felis catus` / `Canis lupus familiaris`（species/subspecies）。宿主科学身份与 WordNet 表示分开保留，不通过身份合并修正统计。在同一 1.10.1 基线和 SDK 上，原审阅门槛把 36 个猫品种对因共享宿主或通用品种概念误算为细层；修正后 Pets 16 细层、650 粗层，Dogs 717/6423 不变。这是纯规则更正，不能算新增知识；原门槛及全部 666/7140 类别对比较保留，见 [独立门槛比较](structure_native_breed_floor_comparison.json)。正式新数据的结果仍需本轮候选构建后独立验收。

## 追加范围与兼容修正

另完整核验 479 个 ABO 文具、清洁、卫浴和露营来源记录：203 个配置通过，276 个按来源语言、附件或目录范围等具体原因保留待审。追加四个真实入口分别使用写具/订书机/文件夹、清洁用具、水龙头/喷头/马桶座、帐篷/睡袋的已有 WordNet 原生类型。共复用九个真实入口根，不创建伪中间分类。全批实际构建和公开验收完成前，这些数量仅代表冻结输入及适配器验证结果。

`en_US` 与 `en-US` 等大小写、连字符/下划线等价语言标签在查询中兼容，原始语言字段及名称保持不变；不同区域与文字体系仍区分。领域成员按照实际类型路径计算：310 个照明配置同时属于家具来源范围，不强制分配唯一领域。名称全量验证包含原始名称、规范化别名及两种语言标签写法。

CUB 全部 200 个作者标签新增固定来源版本范围审查。其中 12 个历史拆分或现代合并相关标签只修订标签映射，旧 15 个待审标签全部保留。新增 12 条更宽的有依据原生范围对应，旧更窄对应保留为 REVIEW；源科学实体、分类边及身份桥不据此自动失效。新增待审不算数据丢失，也不算已确认现代物种。

`configuration_types` 是显式的新配置路径策略，允许经过审核的 `CONFIGURATION_TYPE_OF`。旧 `configuration` 策略保持原含义。类型路径可以独立于证据不足的型号分支存在；它不确认型号身份，也不宣称构成设计血缘。新策略的实际收益与数据修改收益在固定 755 标签、56,917 类别对下分别统计。

完整领域回归核对每个固定样本的原领域根路径。即使该对象仍可到统一根，原领域路径中的错误来源声明被撤回也可能合理移除其旧领域成员资格。验收必须对应到完整旧原始行、来源、关系、实际状态和处置台账；另一个不相关撤回记录不能证明此变化。初次验收的 208 项成员变化全部已有这种具体证据，失败记录和修正后的独立证据分别保留。

## 汽车作者范围与世界配置

完整 196 个作者类别的原始元数据、UID 和命名范围独立保留。原先特定 EPA 燃油配置、名称投影、VIN 实例或目录样本无法证明整个作者类别范围等价的映射，逐项保留历史并转为 `ANNOTATION_SCOPE_REVIEW`；现实实体及其已有合法关系继续存在。新作者来源使用 `stanford-cars-2013` / `2013` 命名空间和版本，通过 `DEPICTS_TYPE` 对应有明确依据的 motor_vehicle 范围，不新增世界车型、代际或配置。

旧 `source_native` 统计保持原三个数据集（402 标签、30,001 对）；新 `source_native_rank_floors` 加入 Cars 作者范围，共四个数据集（598 标签、49,111 对）。世界对象比较仍为固定 755 标签、56,917 对。Cars 原生投影只有粗层共同类型，不宣称存在细设计距离。

Cars 新策略中的 `coarse_lca_roles=['CLASS']` 明确将普通类型共同祖先列为粗层；旧策略不包含该选项。经过审定的型号、系列或配置共同祖先仍可提供细分辨率，身份或关系未确认不能仅凭角色字符串放行。

科学身份范围另审查 12 组、17 条实际桥；仅撤回一条已证明不等价的桥：OTT 旧 Carduelis carduelis 范围明确包含 caniceps 亚种，而固定 AviList 把它列为独立物种。原始 OTT 文件及父边已复核，保留原生分类；现代三个表示与旧 OTT 范围分开。其余 16 条桥没有得到范围不等价的充分证据，继续保留并列具体证据缺口，标签范围疑点不代替身份审定。

Aircraft 也采用显式普通类型粗门槛：airliner 或 FAA 发动机/机体类型共同祖先可以提供合法类型关系，不能当作细设计家族。作者 family/variant 的有据原生关系保持独立。此前 28 个对以 airliner 为共同祖先的细层判断将按新规则改为粗层；这是分辨率更正，不是新增知识或身份修复。
