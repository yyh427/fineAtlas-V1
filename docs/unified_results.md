# FineAtlas 统一层次验收与训练使用

固定数据：`v1.10.0-unified-review`；代码：`v1.10.0-unified-code.1`；SDK `1.10.0rc1`；视图：`unified`；WordNet 3.1。

数据库修订：`650353a713dc5e379d75c3660c34f88e4ff9027c496f96284b30ee21e29f6dcd`

SHA-256：`c8db664711255202d51ed571d60df66fe5b4315e879c1d509a5dd935bb3ee019`

解压字节数：68,496,932,864。

本候选已实施全领域来源规则、统一查询与匹配索引；未达到所有保留来源记录均已核验接入。缺证据、身份粒度冲突和不适用奖励仍明确保留，因此不能无条件替换正式库。文本 SFT 保留原标签，RL 只使用适用标记为真的层次项，类别正确性奖励独立保留。

## 实际检查范围

| 项目 | 结果 |
|---|---|
| 实际领域入口与公开接口 | 91/91 |
| 原始标签 | 755 全保留；四视图逐项 path/state 核对 |
| 固定非基准样本 | 2230/2230 保留；2229 可达；退步 0 |
| 六数据集全部不同类别对 | 56,917 对，输出状态／原因／有效性掩码 |
| 悬空边 | 0 原节点丢失；全结构检查保留／准入悬空数均见结构 JSON |
| 分类与分角色导航循环 | 四视图独立全图检查，见验证 JSON |
| 未接入的有效角色来源记录 | 5608；保留逐 UID 原始父声明和证据边界 |
| 角色冲突身份组 | 287；不凭角色名强行拆分／合并 |

全部 91 领域的入口、原生根、WordNet synset、定义、接入关系、依据及根 UID 链在 [unified_domains.csv](unified_domains.csv)，每步源关系见 [unified_domains.json](unified_domains.json)。领域成员的完整冻结可达性 join 已检查；未定位源记录没有删掉或静默排除。语义抽查包含全部接入根和选定定义、跨来源规则、固定样本、来源字段及发现的反例，不宣称全部源边逐条独立认证。

## 标签与视图

| 视图 | 原存储身份声明 | 当前身份核验 | 根可达 | 路径／状态一致 | 任务准入 |
|---|---:|---:|---:|---:|---:|
| strict | 753 | 752 | 751 | 755/755 | 751 |
| taxonomy | 753 | 752 | 754 | 755/755 | 754 |
| unified | 753 | 732 | 754 | 755/755 | 754 |
| membership | 753 | 752 | 0 | 755/755 | 0 |

身份声明、当前核验、根可达和奖励有效是不同指标。755 标签覆盖来自原数据；本轮不把它计为新增成果。旧视图保留其历史核验口径，不能把旧声明 753 与统一视图的新严格核验数字当成同口径下降。CRJ-700 的原 UID 表示更宽系列，精确注释范围未确认，没有替换成宽系列冒充确认。

同一身份组的不同来源表示已检查公开路径和状态；逐视图数量与差异见 `unified_validation.json.identity_peer_checks`。

## 层次奖励

| 数据集 | 全部类别对 | 有效层次项 | 有效比例 | 不适用状态 |
|---|---:|---:|---:|---|
| cub200 | 19900 | 7770 | 39.05% | COARSE_COMMON_ANCESTOR_ONLY: 8340; ENDPOINT_NOT_APPLICABLE: 3790 |
| fgvc_aircraft | 4950 | 3028 | 61.17% | ENDPOINT_NOT_APPLICABLE: 1295; IDENTITY_LINEAGE_ROLE_CONFLICT: 415; COARSE_COMMON_ANCESTOR_ONLY: 212 |
| flowers102 | 5151 | 1077 | 20.91% | ENDPOINT_NOT_APPLICABLE: 3071; COARSE_COMMON_ANCESTOR_ONLY: 1003 |
| pets37 | 666 | 638 | 95.80% | COARSE_COMMON_ANCESTOR_ONLY: 28 |
| stanford_dogs | 7140 | 717 | 10.04% | COARSE_COMMON_ANCESTOR_ONLY: 6423 |
| stanford_cars | 19110 | 131 | 0.69% | COARSE_COMMON_ANCESTOR_ONLY: 15269; IDENTITY_LINEAGE_ROLE_CONFLICT: 3710 |

只共享 entity、鸟／汽车等策略禁止的过宽共同祖先时，不返回任意最大错误距离。身份步骤成本为零；分类／设计／配置各使用公开允许的有向边集合。DAG 返回全部最低共同祖先，以有信息量共同祖先的向上边数和取最小值；多个不可比较祖先不随意删除。训练策略还检查来源、标注粒度、身份和祖先角色冲突。目录、属性、监管关系不混入距离。适用仅是结构／语义筛查，不是奖励强度或识别准确率已获实验验证。

完整对表为 [unified_pairs.jsonl.gz](unified_pairs.jsonl.gz)。逐标签四视图为 [unified_labels.csv](unified_labels.csv)。同保守规则的旧版对比为 [unified_same_policy_comparison.json](unified_same_policy_comparison.json)：v35/v36 缺少角色合同，显式为接口／模式不支持；不会把旧裸距离升级成有效奖励。

## CUB 混合来源复现

CUB 标签路径不再因为 WordNet／原生分类表示而使用两套不相容判定：使用已核验身份和合法领域分类进入统一骨架，训练固定 AviList 来源策略。仍有旧拆分、属级／标注范围等未确认项，不能把 200 类根可达当成全部 19,900 对都适用。

| 类别对 | 训练距离 | 状态 | 最低共同祖先 |
|---|---:|---|---|
| Black footed Albatross / Laysan Albatross | 2 | APPLICABLE | Phoebastria |
| Brown Pelican / White Pelican | None | ENDPOINT_NOT_APPLICABLE |  |
| Sooty Albatross / Black footed Albatross | 4 | APPLICABLE | Diomedeidae |
| Laysan Albatross / Sooty Albatross | 4 | APPLICABLE | Diomedeidae |
| Tropical Kingbird / Gray Kingbird | 2 | APPLICABLE | Tyrannus |

5 个实例的源 UID、不同来源表示、完整公开路径／task_path、LCA 集合及奖励策略结果见 [unified_cub_examples.json](unified_cub_examples.json)。未定位学妹 H1 的实际树配置或日志；不能断言她使用了哪个旧版本。

## 大分支与真实层次

通用修复使用 FAA AC-CAT 定义补 3 个陆上／水上／两栖中间类，EPA 明确容积类别补 7 个汽油配置中间类，覆盖 84,252 条非评测来源关系。制造商不是型号家族；配置属性不提升为全部型号。另有原生分类投影、OTT 明确分类父级、主源定义型号／栽培单位、完整角色导航和核验犬种标识／父级规则。
FAA 单发动机活塞固定翼原有 61,283 个型号身份仍完整可浏览；默认先显示 3 个真实细分类型和 64 个残余型号。汽油车原有 23,553 个配置身份仍保留，默认先显示 7 个真实类型和 632 个残余配置。完整直接来源关系保留，不用删除叶子降低出度。
陆上子类仍有约 58,514 个型号；现有 FAA 字段不证明制造商设计家族，采用真实制造商目录／字段筛选和稳定分页。EPA 未定义的混合容积字段保留粗边。GeoNames 河流约 991,798 个实例宽度本身合理，按国家／行政字段浏览，不冒充新增分类层。
所有 10625 个受影响父身份范围的公开前后分角色／关系计数保存在发布附件 `all_touched_parent_scopes.jsonl.gz`。完整 UID 保留检查和完整分页集合检查分别通过。单页最多 1,000，默认 20；索引查询、跨页无重复／遗漏、查询计划和同条件耗时见 [unified_performance.json](unified_performance.json)。冷条件指新 SDK/SQLite 连接，OS 缓存未清空，不用不同返回规模制造性能提升。

飞机与汽车各 5 个基准／非基准前后路径及字段定义、来源证据见发布附件 `aircraft_car_examples.json`；路径变长本身不计为改进。

## 剩余证据阻塞

本轮完整枚举了 5608 个未接入来源记录。逐 UID 的冻结审核、原始父关系、源边界链及独立核验尝试保存在 `unresolved_evidence.jsonl.gz`。例外没有删除或改成强挂根。

- No retained source parent assertion at boundary: 56
- parent appears in a prepositional complement: 8
- Re-evaluated with conservative nominal-head and endpoint-sense contract: 1
- parent occurs inside a clause rather than the nominal head: 20
- Endpoint retained as source-only; classification is not admitted: 25
- Retained source assertion reaches a rooted parent but its role/view contract is not admitted: 881
- Global native sense ambiguity and strict nominal head review: 36
- Source assertion not admitted: 3
- Native model-field endpoint differs: 1
- No independently corroborated compatible parent: 1714
- Native unranked infraspecific group is not a species/class endpoint; independent typed placement required: 157
- GBIF synonym or doubtful concept; not strict subtype proof: 69
- Registry parent lacks unique independent native connection: 7
- Registry placement is uncertain, unassessed or unaccepted: 6
- Professional source itself flags name-parent conflict: 29
- Independent source retains same-rank conflict: 1
- Alignment is not a classification edge: 435
- MISSING_UNAMBIGUOUS_SPECIES_BINOMEN: 1
- UNSUPPORTED_OR_MISSING_RANK_SCOPE: 65
- UNSUPPORTED_OR_MISSING_CHILD_RANK: 49
- ENCODED_SPECIES_SCOPE_DOES_NOT_MATCH_PARENT: 1
- NO_DIRECT_DEFINITIONAL_CATEGORY_ANCHOR: 1
- Legacy P31 refinement lacks strict subtype proof; retained for independent review: 2042

实例包括当前缺少明确设计／栽培单位的 Buick Marquette、原生 Centramoebida→Longamoebia 的独立父级范围未确认，以及 Xanthomonas 旧分类与当前主源父级身份不一致。缺少相容的当前标识／范围／独立父级证据时，不把保留的源声明自动提升为已核验统一分类。宽分支缺失可核验家族字段、CRJ-700 缺数据集作者粒度对照、CUB 旧注释拆分及混合身份粒度也是明确限制。来源 JSON 缺字段不能由名称猜测补齐。

个例：McLaren MP4-12C sports car 采用厂商手册；游戏主机→显示器和扬声器→连接件两条错误边按独立主源定义隔离，已有合法替代路径保留。三个 FDA 监管类别角色和一条错误设计边单独记录。通用同 QID 主源角色修复 23 个表示；13 个已有家族与通用 model 单位冲突保持待审。完整原 UID、payload、原始关系端点及标签历史均保留。

末轮还核验并接入 7 个非基准食物概念：当前主源的未限定 food 上位声明与独立范围复核一致，使用原生分类关系，不伪造更细的菜系或配方层。补充来源快照及实际 revision 在发布附件 `late_primary_food_sources.json`。Callender-Hamilton bridge 的命名桥／桥型范围、M-11 Shtorm 的完整系统／弹体范围仍冲突，两个记录保持 UNKNOWN 并保存证据，不靠修改角色名称制造通过。

## 获取和最小复现

```bash
git clone --branch v1.10.0-unified-code.1 https://github.com/yyh427/fineAtlas-V1.git
cd fineAtlas-V1
python3 -m pip install -e .
python3 scripts/download_single.py --manifest unified_data.json --output-dir /path/to/fineatlas-1.10
python3 - <<'PYCODE'
from fineatlas import FineAtlas
with FineAtlas("/path/to/fineatlas-1.10/fineatlas.sqlite", relation_view="unified") as tree:
    print(tree.task_path("cub200", "1"))
    a=tree.target("cub200", "1")["target_uid"]
    b=tree.target("cub200", "2")["target_uid"]
    print(tree.lca(a,b,policy="classification"))
    print(tree.distance(a,b,policy="classification"))
    print(tree.relation_reward_index("cub200").query("1", "2"))
    tree.export_training("cub200", "/path/to/cub-text-training")
PYCODE
```

新目录安装，关闭旧 SDK／SQLite 连接；验证完整 SHA、数据库修订、默认视图和匹配索引。不套用旧 1.9 overlay，不共享旧游标／进程缓存。完整重建、检查和恢复命令见 [unified_build.md](unified_build.md)。候选分块／冻结输入／来源快照沿用同名 GitHub prerelease 分发，原生产库、旧候选、原始来源和用户未提交文件保留。

公开下载后干净代码／进程的复验结果另存同一 release 附件 `external_validation.json`，记录实际代码 commit、模块来源、完整下载 SHA、默认视图、91 入口及 755／56,917 查询比对；只有该附件记录的真实完成项可称已外部分发复验。未运行图像识别、视觉训练或推理，不宣称识别准确率提高。

发布下载复验发现并修复核验器的成功分页 schema 假设：成功页不强制含 `status`，但必须有合法分页字段、正确视图／修订及有界结果。原始失败日志保留；代码固定到 `v1.10.0-unified-code.1`，数据 SHA 与冻结 SDK 字节保持不变。
