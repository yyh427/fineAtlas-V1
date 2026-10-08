# 公开候选下载与干净进程复验

本文件记录实际完成的公开下载和调用，不复用开发库。

- 数据标签：`v1.10.0-unified-review`；代码标签：`v1.10.0-unified-code.1`；实际检出代码：`ca46e6c45a2cc17f59ea4ab9f57c4d83f6cf3cd1`。
- 完整数据库 SHA-256：`c8db664711255202d51ed571d60df66fe5b4315e879c1d509a5dd935bb3ee019`；图修订：`650353a713dc5e379d75c3660c34f88e4ff9027c496f96284b30ee21e29f6dcd`。
- 从公开 `unified_data.json` 和全部公开分块安装到新目录；安装器退出 0，逐块与解压流完整 SHA／字节数均匹配。
- 干净虚拟环境与独立代码检出，逐个核对 20 个冻结 SDK 源文件；默认 `unified`，内嵌浏览索引修订一致。
- 全部 91 领域入口公开根路径／成员页通过；755 标签在四视图下与发布验收表一致；全部 56,917 类别对状态／距离有效性与发布记录一致。
- 14 条真实 CLI 通过，飞机 61,283 型号和汽车 23,553 配置的完整分页无重复／遗漏；使用相同规模比较性能。
- 从公开冻结输入归档读取固定非基准样本：2,230 全保留，2,229 可达，退步 0。
- 实际导出六个数据集的标签与训练类别对，逐数据集统计／修订／视图与发布表完全一致；无效层次项保留原因和空距离。

详细记录：[unified_external_validation.json](unified_external_validation.json)。发布附件 `external-reproduction-reports.tar.gz` 包含调用命令、结果、训练导出、分页和性能；本地检查点保留实际安装路径与日志。原始全图保留、循环和源合同检查已在同 SHA 的冻结候选上完成，不额外重复扫描整库。

该复验确认分发、代码、索引、默认配置和查询一致，仍不代表所有来源关系已经独立认证。5,608 个未接入来源记录、287 个角色冲突身份组及标注粒度限制继续有效；候选不具备无条件替换正式库的条件。未运行图像识别或视觉模型。

```bash
git clone --branch v1.10.0-unified-code.1 https://github.com/yyh427/fineAtlas-V1.git
cd fineAtlas-V1
python3 -m pip install -e .
python3 scripts/download_single.py --manifest unified_data.json --output-dir data-v1.10
python3 scripts/verify_unified_install.py --database data-v1.10/fineatlas.sqlite \
  --manifest unified_data.json --expected-validation docs/unified_validation.json \
  --output install-audit
```

不可直接使用其他分支／PyPI 版本、旧数据库、旧外部索引或旧游标来复现此结果。标签保持绑定上述代码 commit；后续报告提交不改变已测试的 SDK 字节或数据。

实际公开加载也发现了核验器对成功分页的错误假设；修正版 5 项协议回归和独立公开代码的 120 项测试均通过。首次失败及额外隔离调用的同目录导入失败日志保留；它们不被删除或标为通过。最终复验使用上述新代码标签，数据库和 20 个冻结 SDK 文件均未改变。
