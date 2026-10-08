# 统一候选的构建、验收与恢复

候选：`v1.10.0-unified-review`，SDK `1.10.0rc1`，默认视图 `unified`，WordNet 3.1。准确图修订与完整产物校验值以 `unified_data.json` 为准。所有公开附件通过项目既有 GitHub prerelease 分块 SQLite 分发机制提供；生产版本不替换。

## 基线与冻结输入

直接基线是 `v1.8.1-hierarchy-review`，不是旧正式版 v1.6，也不是仅增加浏览索引的 v1.9。基线清单为 `docs/night_baseline_data.json`，SHA-256：

```
d65e74d50785fe54bbfd04a91a7e818a27b766e8b038b18cdce5b2f48c6f9929
```

基线图修订：

```
fd5dfb79f85e91050980fc245f2221af293bc19d05049d1e1bce3cbec52e37ca
```

下载基线与本候选发布中的冻结输入到独立目录。输入归档中的 `baseline.json` 保留原始构建位置作为历史记录；外部重建通过 `--baseline` 指定实际的已校验安装路径，不修改冻结文件。

输入保留全部领域接入表、选定 WordNet 节点／超类边、全来源标识关联、原生字段分类规则、角色导航、原生分类投影、定义明确的来源单位及例外／待审清单。新来源快照保留 revision ID、URL、许可和 SHA；重新获取的新网页不能默认为本次冻结证据。

## 重放与索引

```bash
python3 -m pip install -e '.[build]'
python3 scripts/download_single.py --manifest docs/night_baseline_data.json \
  --output-dir /path/to/baseline-1.8.1
# 独立候选，不能硬链接到生产库或基线
cp --reflink=auto /path/to/baseline-1.8.1/fineatlas.sqlite /path/to/candidate.sqlite
sha256sum /path/to/candidate.sqlite
# 校验值必须等于上方基线 SHA，然后才应用冻结输入
python3 scripts/build_unified_candidate.py \
  --baseline /path/to/baseline-1.8.1/fineatlas.sqlite \
  --database /path/to/candidate.sqlite --inputs /path/to/unified-inputs \
  --reports /path/to/build-reports
python3 scripts/finalize_unified_metadata.py \
  --database /path/to/candidate.sqlite --inputs /path/to/unified-inputs \
  --output /path/to/frozen-metadata.json
python3 scripts/stage_browse_indexes.py \
  --source /path/to/candidate.sqlite --output /path/to/browse-staging.sqlite \
  --reports /path/to/browse-build --release v1.10.0-unified-review
```

从 `frozen-metadata.json` 读取精确的 `revision`，再应用派生索引：

```bash
python3 scripts/apply_browse_indexes.py \
  --database /path/to/candidate.sqlite --staging /path/to/browse-staging.sqlite \
  --source-revision <frozen-metadata-revision> --output /path/to/browse-application.json
```

索引源修订不匹配即拒绝应用。v1.9 外部浏览索引不能套用本次已改变源图的数据库。重建仍使用同一 SQLite/Migration 数据模型，临时 RAM 缓存只用于降低无意义的整表改写；提交后保存完整派生缓存。

## 必要检查

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 scripts/audit_unified_candidate.py \
  --database /path/to/candidate.sqlite \
  --baseline /path/to/baseline-1.8.1/fineatlas.sqlite \
  --samples /path/to/frozen-nonfocus-samples.json --output /path/to/acceptance
python3 scripts/audit_unified_browsing.py --database /path/to/candidate.sqlite \
  --baseline /path/to/verified-v1.9/fineatlas.sqlite --output /path/to/browse-checks
python3 scripts/audit_browse_contracts.py --baseline /path/to/candidate.sqlite \
  --staging /path/to/browse-staging.sqlite --output /path/to/contracts.json
python3 scripts/audit_browse_cycles.py --staging /path/to/browse-staging.sqlite \
  --output /path/to/cycles.json
python3 scripts/audit_browse_witnesses.py --baseline /path/to/candidate.sqlite \
  --staging /path/to/browse-staging.sqlite --output /path/to/witnesses.json
python3 scripts/audit_browse_cli.py --database /path/to/candidate.sqlite \
  --output /path/to/cli-reproduction
```

候选检查器支持按 `--phase domains/labels/structure/preservation/nonfocus` 重跑。标签阶段保留 755 个标签，输出六个数据集全部 56,917 个不同类别对的有效性与原因。源记录保留检查比较完整 UID、原始 payload、原始关系端点和标签历史，不仅比较数量。已核验的监管记录错误设计边纠正单列证据与替代路径，不包装成节点删除或合法关系丢失。

浏览性能使用相同 20 条返回规模、同一来源筛选与是否包含粗边的条件。冷条件仅指新 SDK/SQLite 连接，OS 页缓存没有清空；重复查询另报。完整分页枚举只出现在验收程序，常规接口使用索引和有界页。

## 检查点

本地执行按源输入、图构建、元数据冻结、浏览 staging、索引应用及每个验收阶段分别保存日志与 JSON 检查点。图构建失败时数据库保持未就绪，不能称为正式可用。

源重放已完成且输入未改变时，可用 `--graphs-only` 从同一独立候选重新构建缓存。变更输入后应检查源规则重放的幂等性；外部完整重建优先从已校验基线的独立副本重放。冻结后若修复源图或 SDK 查询语义，重新冻结修订并重建匹配的索引，不能继续使用旧游标／缓存。

发布前压缩 roundtrip 与完整 SHA 校验后上传分块；最后从公开附件重新下载，在干净进程中使用已推送代码加载，核验默认视图、修订、真实查询与回归结果。源图可达性、来源语义抽查、奖励适用性、发布一致性分别报告。

最终源输入还包含同 QID 的主源角色纠正。发现这一类明确错误时，先运行 `prepare_unified_same_qid_roles.py` 生成预览，核对其主源范围后将规则加入 `unified_root_contracts.jsonl`。本轮 23 个决定均已冻结。增量恢复可以使用 `build_unified_candidate.py --scope-reconciliation-only`，它会重放该队列、重新生成完整型号／配置导航并重建全部视图，随后必须重新冻结元数据和生成匹配索引。完整基线重放已包括此队列，不需要另建不兼容格式。
