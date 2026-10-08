# 统一候选的构建、验收与恢复

本分支对应 `v1.10.1-repair-review`，SDK `1.10.1rc1`，默认视图 `unified`，WordNet 3.1。精确代码标签、数据库修订与文件校验值分别见 `unified_code.json`、`unified_data.json`。候选使用 GitHub prerelease 附件分发，旧生产数据库与候选继续保留。

## 基线与冻结输入

完整重放的直接源基线是 `v1.8.1-hierarchy-review`，SHA-256：

```
d65e74d50785fe54bbfd04a91a7e818a27b766e8b038b18cdce5b2f48c6f9929
```

基线图修订：

```
fd5dfb79f85e91050980fc245f2221af293bc19d05049d1e1bce3cbec52e37ca
```

这是复建 1.10 源规则的输入基线；交付和使用的版本是新的 1.10 修复候选。基线公开清单保存在 `docs/night_baseline_data.json`。冻结输入包含原 1.10 完整规则与本次独立修复队列，不需要现场下载网页、重新选择证据或从旧候选提取临时 SQL。`baseline.json` 中原构建位置仅作为历史记录，CLI 的 `--baseline` 指定当前安装路径。

输入包括选定 WordNet 3.1 定义与真实上位边、全部领域接入规则、来源标识、角色分类、任务范围、原生字段和家具许可快照。来源决定保留 URL、版本或 revision、SHA 与证据范围；重新获取的网页不能自动替代冻结证据。家具配置以目录 listing 标识保存，不能解释成制造商型号。

## 完整复建

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

在另一套不存在的输出路径再次执行完整复建，然后比较：

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

压缩后完整 roundtrip 与 SHA 检查通过，才上传分块附件；新候选使用独立分支、PR 和 prerelease，不合并主分支或替换生产版。公开复验重新下载附件、固定代码标签并在干净进程中核对修订、全部入口、标签、类别对、分页及导出。

失败阶段的日志与 checkpoint 保留。只有源重放已完成且冻结输入／代码未改变时，才能用 `build_unified_candidate.py --graphs-only` 恢复派生缓存阶段。重新应用来源决定可能追加历史台账，因此完整独立复建优先从受保护基线新副本开始。
