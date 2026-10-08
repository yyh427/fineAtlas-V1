#!/usr/bin/env python3
"""Write a version-pinned human report from actual completed acceptance outputs."""
import argparse,json,pathlib
p=argparse.ArgumentParser(description=__doc__)
for name in ('docs','manifest','examples','unresolved','branches','output'):p.add_argument('--'+name,type=pathlib.Path,required=True)
a=p.parse_args();load=lambda path:json.loads(path.read_text());d=load(a.docs/'unified_validation.json');m=load(a.manifest);examples=load(a.examples);unresolved=load(a.unresolved);branches=load(a.branches)
assert d['retention']['pass'] and d['domains']=={'actual':91,'public_contract_passes':91}
assert sum(x['pairs'] for x in d['pairs'].values())==56917
assert all(x['database_revision']==m['database_revision'] for x in d['pairs'].values()),'Manifest and audit refer to different snapshots'
lines=['# FineAtlas 统一层次验收与训练使用',
 f"\n固定数据：`{m['release']}`；代码：`v1.10.0-unified-code.1`；SDK `{m['sdk_version']}`；视图：`unified`；WordNet 3.1。",
 f"\n数据库修订：`{m['database_revision']}`\n\nSHA-256：`{m['database']['sha256']}`\n\n解压字节数：{m['database']['bytes']:,}。",
 '\n本候选已实施全领域来源规则、统一查询与匹配索引；未达到所有保留来源记录均已核验接入。缺证据、身份粒度冲突和不适用奖励仍明确保留，因此不能无条件替换正式库。文本 SFT 保留原标签，RL 只使用适用标记为真的层次项，类别正确性奖励独立保留。',
 '\n## 实际检查范围\n',
 '| 项目 | 结果 |','|---|---|',
 f"| 实际领域入口与公开接口 | {d['domains']['public_contract_passes']}/{d['domains']['actual']} |",
 '| 原始标签 | 755 全保留；四视图逐项 path/state 核对 |',
 f"| 固定非基准样本 | {d['nonfocus']['preserved']}/{d['nonfocus']['count']} 保留；{d['nonfocus']['connected']} 可达；退步 {d['nonfocus']['regressions']} |",
 '| 六数据集全部不同类别对 | 56,917 对，输出状态／原因／有效性掩码 |',
 f"| 悬空边 | {d['retention']['original_nodes_missing']} 原节点丢失；全结构检查保留／准入悬空数均见结构 JSON |",
 '| 分类与分角色导航循环 | 四视图独立全图检查，见验证 JSON |',
 f"| 未接入的有效角色来源记录 | {d['unrooted_navigation_source_records']}；保留逐 UID 原始父声明和证据边界 |",
 f"| 角色冲突身份组 | {d['identity_role_conflict_groups']}；不凭角色名强行拆分／合并 |",
 '\n全部 91 领域的入口、原生根、WordNet synset、定义、接入关系、依据及根 UID 链在 [unified_domains.csv](unified_domains.csv)，每步源关系见 [unified_domains.json](unified_domains.json)。领域成员的完整冻结可达性 join 已检查；未定位源记录没有删掉或静默排除。语义抽查包含全部接入根和选定定义、跨来源规则、固定样本、来源字段及发现的反例，不宣称全部源边逐条独立认证。',
 '\n## 标签与视图\n','| 视图 | 原存储身份声明 | 当前身份核验 | 根可达 | 路径／状态一致 | 任务准入 |','|---|---:|---:|---:|---:|---:|']
for view,x in d['labels'].items():lines.append(f"| {view} | {x['stored_identity_claim_verified']} | {x['identity_verified']} | {x['root_reachable']} | {x['path_state_consistent']}/755 | {x['hierarchy_admitted']} |")
lines+=['\n身份声明、当前核验、根可达和奖励有效是不同指标。755 标签覆盖来自原数据；本轮不把它计为新增成果。旧视图保留其历史核验口径，不能把旧声明 753 与统一视图的新严格核验数字当成同口径下降。CRJ-700 的原 UID 表示更宽系列，精确注释范围未确认，没有替换成宽系列冒充确认。',
 '\n同一身份组的不同来源表示已检查公开路径和状态；逐视图数量与差异见 `unified_validation.json.identity_peer_checks`。',
 '\n## 层次奖励\n','| 数据集 | 全部类别对 | 有效层次项 | 有效比例 | 不适用状态 |','|---|---:|---:|---:|---|']
for ds,x in d['pairs'].items():
 statuses=x['pair_statuses'];good=statuses.get('APPLICABLE',0);total=x['pairs'];lines.append(f"| {ds} | {total} | {good} | {100*good/total:.2f}% | "+'; '.join(f'{k}: {v}' for k,v in statuses.items() if k!='APPLICABLE')+' |')
lines+=['\n只共享 entity、鸟／汽车等策略禁止的过宽共同祖先时，不返回任意最大错误距离。身份步骤成本为零；分类／设计／配置各使用公开允许的有向边集合。DAG 返回全部最低共同祖先，以有信息量共同祖先的向上边数和取最小值；多个不可比较祖先不随意删除。训练策略还检查来源、标注粒度、身份和祖先角色冲突。目录、属性、监管关系不混入距离。适用仅是结构／语义筛查，不是奖励强度或识别准确率已获实验验证。',
 '\n完整对表为 [unified_pairs.jsonl.gz](unified_pairs.jsonl.gz)。逐标签四视图为 [unified_labels.csv](unified_labels.csv)。同保守规则的旧版对比为 [unified_same_policy_comparison.json](unified_same_policy_comparison.json)：v35/v36 缺少角色合同，显式为接口／模式不支持；不会把旧裸距离升级成有效奖励。',
 '\n## CUB 混合来源复现\n','CUB 标签路径不再因为 WordNet／原生分类表示而使用两套不相容判定：使用已核验身份和合法领域分类进入统一骨架，训练固定 AviList 来源策略。仍有旧拆分、属级／标注范围等未确认项，不能把 200 类根可达当成全部 19,900 对都适用。',
 '\n| 类别对 | 训练距离 | 状态 | 最低共同祖先 |','|---|---:|---|---|']
for e in load(a.docs/'unified_cub_examples.json'):
 t=e['training_pair'];anc='; '.join(v.get('label',v.get('uid','')) for v in t.get('lcas',[]));lines.append('| '+' / '.join(e['labels'])+f" | {t.get('distance')} | {t['status']} | {anc} |")
lines+=['\n5 个实例的源 UID、不同来源表示、完整公开路径／task_path、LCA 集合及奖励策略结果见 [unified_cub_examples.json](unified_cub_examples.json)。未定位学妹 H1 的实际树配置或日志；不能断言她使用了哪个旧版本。',
 '\n## 大分支与真实层次\n',
 '通用修复使用 FAA AC-CAT 定义补 3 个陆上／水上／两栖中间类，EPA 明确容积类别补 7 个汽油配置中间类，覆盖 84,252 条非评测来源关系。制造商不是型号家族；配置属性不提升为全部型号。另有原生分类投影、OTT 明确分类父级、主源定义型号／栽培单位、完整角色导航和核验犬种标识／父级规则。',
 'FAA 单发动机活塞固定翼原有 61,283 个型号身份仍完整可浏览；默认先显示 3 个真实细分类型和 64 个残余型号。汽油车原有 23,553 个配置身份仍保留，默认先显示 7 个真实类型和 632 个残余配置。完整直接来源关系保留，不用删除叶子降低出度。',
 '陆上子类仍有约 58,514 个型号；现有 FAA 字段不证明制造商设计家族，采用真实制造商目录／字段筛选和稳定分页。EPA 未定义的混合容积字段保留粗边。GeoNames 河流约 991,798 个实例宽度本身合理，按国家／行政字段浏览，不冒充新增分类层。',
 f"所有 {branches['touched_parent_identity_scopes']} 个受影响父身份范围的公开前后分角色／关系计数保存在发布附件 `all_touched_parent_scopes.jsonl.gz`。完整 UID 保留检查和完整分页集合检查分别通过。单页最多 1,000，默认 20；索引查询、跨页无重复／遗漏、查询计划和同条件耗时见 [unified_performance.json](unified_performance.json)。冷条件指新 SDK/SQLite 连接，OS 缓存未清空，不用不同返回规模制造性能提升。",
 '\n飞机与汽车各 5 个基准／非基准前后路径及字段定义、来源证据见发布附件 `aircraft_car_examples.json`；路径变长本身不计为改进。',
 '\n## 剩余证据阻塞\n',
 f"本轮完整枚举了 {unresolved['source_records']} 个未接入来源记录。逐 UID 的冻结审核、原始父关系、源边界链及独立核验尝试保存在 `unresolved_evidence.jsonl.gz`。例外没有删除或改成强挂根。"]
lines.append('')
for reason,count in unresolved.get('source_boundary_reasons',{}).items():lines.append(f'- {reason}: {count}')
lines+=['\n实例包括当前缺少明确设计／栽培单位的 Buick Marquette、原生 Centramoebida→Longamoebia 的独立父级范围未确认，以及 Xanthomonas 旧分类与当前主源父级身份不一致。缺少相容的当前标识／范围／独立父级证据时，不把保留的源声明自动提升为已核验统一分类。宽分支缺失可核验家族字段、CRJ-700 缺数据集作者粒度对照、CUB 旧注释拆分及混合身份粒度也是明确限制。来源 JSON 缺字段不能由名称猜测补齐。',
 '\n个例：McLaren MP4-12C sports car 采用厂商手册；游戏主机→显示器和扬声器→连接件两条错误边按独立主源定义隔离，已有合法替代路径保留。三个 FDA 监管类别角色和一条错误设计边单独记录。通用同 QID 主源角色修复 23 个表示；13 个已有家族与通用 model 单位冲突保持待审。完整原 UID、payload、原始关系端点及标签历史均保留。',
 '\n末轮还核验并接入 7 个非基准食物概念：当前主源的未限定 food 上位声明与独立范围复核一致，使用原生分类关系，不伪造更细的菜系或配方层。补充来源快照及实际 revision 在发布附件 `late_primary_food_sources.json`。Callender-Hamilton bridge 的命名桥／桥型范围、M-11 Shtorm 的完整系统／弹体范围仍冲突，两个记录保持 UNKNOWN 并保存证据，不靠修改角色名称制造通过。',
 '\n## 获取和最小复现\n',
 '```bash\ngit clone --branch v1.10.0-unified-code.1 https://github.com/yyh427/fineAtlas-V1.git\ncd fineAtlas-V1\npython3 -m pip install -e .\npython3 scripts/download_single.py --manifest unified_data.json --output-dir /path/to/fineatlas-1.10\npython3 - <<\'PYCODE\'\nfrom fineatlas import FineAtlas\nwith FineAtlas("/path/to/fineatlas-1.10/fineatlas.sqlite", relation_view="unified") as tree:\n    print(tree.task_path("cub200", "1"))\n    a=tree.target("cub200", "1")["target_uid"]\n    b=tree.target("cub200", "2")["target_uid"]\n    print(tree.lca(a,b,policy="classification"))\n    print(tree.distance(a,b,policy="classification"))\n    print(tree.relation_reward_index("cub200").query("1", "2"))\n    tree.export_training("cub200", "/path/to/cub-text-training")\nPYCODE\n```',
 '\n新目录安装，关闭旧 SDK／SQLite 连接；验证完整 SHA、数据库修订、默认视图和匹配索引。不套用旧 1.9 overlay，不共享旧游标／进程缓存。完整重建、检查和恢复命令见 [unified_build.md](unified_build.md)。候选分块／冻结输入／来源快照沿用同名 GitHub prerelease 分发，原生产库、旧候选、原始来源和用户未提交文件保留。',
 '\n公开下载后干净代码／进程的复验结果另存同一 release 附件 `external_validation.json`，记录实际代码 commit、模块来源、完整下载 SHA、默认视图、91 入口及 755／56,917 查询比对；只有该附件记录的真实完成项可称已外部分发复验。未运行图像识别、视觉训练或推理，不宣称识别准确率提高。']
a.output.write_text('\n'.join(lines)+'\n');print(a.output)
