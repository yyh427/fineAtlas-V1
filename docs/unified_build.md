# 1.10.1 正式版的构建、验收与恢复

本地正式 `v1.10.1` 已构建并通过16阶段验收，SDK `1.10.1`，默认视图 `unified`，WordNet 3.1。精确代码标签、数据库修订与文件校验值分别见 [unified_code.json](../unified_code.json)、[unified_data.json](../unified_data.json)。两源独立提升及来源语义保留检查已通过；正式公网安装与GitHub main／Latest切换仍为PENDING。原1.6和所有候选继续保留。

普通用户按 [README 默认流程](../README.md) 安装和下载，不需要执行重建。迁移和旧版本回退见 [migration_v1.10.1.md](migration_v1.10.1.md)。

## 候选内容与正式提升

`v1.10.1-repair-review` 的修复图、完整本地验收和实际公网复验已经保留。正式版从受保护候选的独立副本提升，以正式SDK重新冻结代码/版本元数据和匹配的浏览索引，并为新文件生成独立SHA、修订及分发清单。正式提升已完成独立复现和全部16阶段本地回归；压缩roundtrip及真正公开安装复验按各自凭据确认，当前不宣称公网通过。不能只把候选清单中的版本名或candidate标记改掉。

当前正式附件的精确复现步骤见 [stable_promotion_recipe.md](stable_promotion_recipe.md)。两次提升分别使用此前独立构建的repair primary与repair reproduction；二者已经完成精确文件绑定、105个逻辑表和模式比较，原primary还有完整16阶段实际公网验收。不能从同一份primary复制两次就称为独立源复现。

提升保留原源语义图的历史namespace、`unified_source_graph_revision`、类型合同、策略、WordNet使用记录、源／身份记录及原构建阶段指纹；不重新运行来源迁移或重写其历史。正式SDK／版本元数据重新冻结，随后只重建并嵌入匹配的新浏览索引，两份正式输出再独立比较和验收。源输入、SDK或原配方存在超出许可范围的变化时，该提升脚本拒绝复用，需要完整源重建。

从v1.8.1全基线直接以stable版本执行full rebuild，可能产生不同的源图namespace、冻结元数据、父修订和最终revision；即使部分语义内容相同，也不能宣称得到当前正式附件的精确revision。精确复现必须使用上面的两源提升配方及其原输入／验收凭据。正式两源提升、匹配浏览索引重建及两份输出105张逻辑表／模式比较已通过；103张非浏览表的来源语义保留检查通过，允许的版本／SDK冻结元数据变化单独列明，浏览派生表另行核验。完整16阶段本地receipt于2026-10-09 02:42:52 UTC结束，全部实际exit0且语义PASS。正式公网安装与main／Latest发布状态仍为PENDING。

此过程不增加源范围、不重写来源UID、原生payload和任务标签，也不把CUB15／CRJ世界身份REVIEW、4180个无根UID／2976身份组、283角色冲突组或Cars135／19110可用类别对宣称解决。正式验收的精确结果与实际代码引用见 [unified_results.md](unified_results.md) 和对应验收快照。

## 基线与冻结输入

完整重放的直接源基线是 `v1.8.1-hierarchy-review`，SHA-256：

```
d65e74d50785fe54bbfd04a91a7e818a27b766e8b038b18cdce5b2f48c6f9929
```

基线图修订：

```
fd5dfb79f85e91050980fc245f2221af293bc19d05049d1e1bce3cbec52e37ca
```

这是重放1.10历史源规则的输入基线，不是普通用户的默认下载版本。基线公开清单保存在 [night_baseline_data.json](night_baseline_data.json)。冻结输入包含原1.10完整规则与独立修复队列，不需要现场下载网页、重新选择证据或从旧候选提取临时SQL。`baseline.json` 中原构建位置仅作为历史记录，CLI 的 `--baseline` 指定当前安装路径。

输入包括选定 WordNet 3.1 定义与真实上位边、全部领域接入规则、来源标识、角色分类、任务范围、原生字段和家具许可快照。来源决定保留 URL、版本或 revision、SHA 与证据范围；重新获取的网页不能自动替代冻结证据。家具配置以目录 listing 标识保存，不能解释成制造商型号。

## 历史源规则完整复建

下面是完整重放源规则的开发流程，保留用于源规则开发和变化后的重建；输出版本及冻结namespace取决于输入和实际构建历史。它不是当前正式附件的exact promotion recipe，不能据此承诺正式精确revision。复现当前正式附件应执行 [两源提升配方](stable_promotion_recipe.md)，不要将历史源重放输出直接冒充当前正式附件。

```bash
python3 -m pip install -e '.[build]'
python3 scripts/download_single.py --manifest docs/night_baseline_data.json \
  --output-dir /path/to/baseline
python3 scripts/rebuild_unified_repair.py \
  --baseline /path/to/baseline/fineatlas.sqlite \
  --inputs /path/to/frozen-inputs \
  --database /path/to/new-candidate.sqlite \
  --reports /path/to/new-build-reports \
  --browse-staging /path/to/new-browse-staging.sqlite
```

CLI 拒绝覆盖已有候选或 staging。它校验基线大小、修订和完整 SHA，创建非硬链接独立副本并复验，然后重放完整源规则、重算四个视图、冻结元数据、构建匹配的浏览 staging 并嵌入索引。所有 CLI 路径在切换子进程工作目录前固定。大型 SQLite 临时文件写入新候选目录下的 `tmp`。

源重放先落实规范角色，再应用依赖这些角色的最终导航关系。通用类型纠正使用稳定来源定位与内容 SHA；明确的通用类别证据不能被只凭 `rank=model` 的产品解析覆盖。生活入口采用增量注册，保留已有规范入口的 ID、范围及兼容别名，不从较旧原始声明重新展开其范围。

`rebuild_status.json` 记录每阶段命令、时间与结果，`rebuild_complete.json` 仅表示构建完成；独立验收通过后才可发布。图、元数据、浏览索引必须保持同一精确修订。冻结后变更源规则或 SDK 查询语义，需重新构建匹配图与索引。

## 独立复建与验收

精确正式复现先按 [提升配方](stable_promotion_recipe.md)分别提升已比较验收的repair primary与repair reproduction，再比较两份stable输出。源规则开发的历史full replay则在另一套不存在的输出路径再次重建后比较；这是另一条开发验证路径。比较命令为：

```bash
python3 scripts/compare_reproductions.py \
  --database /path/to/new-candidate.sqlite \
  --reproduction /path/to/independent-candidate.sqlite \
  --output /path/to/logical-comparison.json
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

比较器双向核对表清单、表结构以及全部语义记录；仅运行阶段时间和浏览构建时间不作为语义值比较。两份数据库保存各自完整 SHA，不要求物理文件哈希相等。

`run_unified_repair_acceptance.py --help` 给出完整验收所需路径：源保留基线、旧浏览基线、生产合同基线、固定非重点样本及冻结修复输入分别提供。验收包括完整入口、755 标签四视图、全部 56,917 类别对、源保留、所有连通分量无环、浏览合同及路径证据、实际 CLI 和公共接口，以及新生活领域的完整分页。

验收 receipt 绑定候选精确文件 SHA、图修订、版本及每阶段实际命令和语义结果。`report_unified_results.py` 仅编译通过且与当前文件一致的 receipt；进程退出 0、旧报告或抽样结果不能替代完整验收。

原始 UID、payload、来源关系与标签历史分别检查。经逐条证据核验的错误角色／设计关系纠正单列原声明、决定和合法替代路径；缺证据项继续保留待审。合法导航、严格分类、身份确认及层次奖励适用性分别报告，不用统一根可达率代替后面三项。

浏览性能使用相同来源、角色、粗边条件和返回数量。冷条件是新 SDK/SQLite 连接，OS 页缓存未清空；重复查询另报。

## 发布与恢复

压缩后完整roundtrip与SHA检查通过，才上传分块附件。历史候选保持独立prerelease；正式1.10.1经授权发布后采用新的正式Release、匹配代码与默认清单，并将默认main／Latest指向正式版。切换前必须完成分支和代码CI、源内容保留与正式promotion验收；切换后普通无分支clone、无manifest下载、默认stats和已安装SDK检查都要实际复验。旧1.6和候选附件、标签和数据不删除、不覆盖。

公开复验真正重新下载附件，使用固定可执行代码在全新环境中核对完整SHA、修订、全部入口、标签、类别对、分页及导出。报告中的16阶段runner不自行做live下载；发布/下载器/全新安装步骤有独立凭据。全部旧源关系和身份的独立科学语义认证，以及全部注释范围和视觉奖励校准，仍是明确范围外说明，不能随正式版本号自动声明完成。

失败阶段的日志与 checkpoint 保留。只有源重放已完成且冻结输入／代码未改变时，才能用 `build_unified_candidate.py --graphs-only` 恢复派生缓存阶段。重新应用来源决定可能追加历史台账，因此完整独立复建优先从受保护基线新副本开始。
