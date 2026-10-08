# 实际公网安装复验

候选数据 `v1.10.1-repair-review` 已通过实际无认证公开下载。公开代码标签 `v1.10.1-repair-code.1` 固定提交 `b36616f66bec48a7e47f576739efe88df3b466f6`；SDK `1.10.1rc1`；默认视图 `unified`。

数据库 SHA-256：`62a9190f1330091d84b7259a7ef2865a6ee1d098d860159b6ebec30db5fd5391`。修订：`da98222833499cf1bb84ff2f64376e5a4fb0594786e04a29694d5bb86c4b7492`。解压字节数：68,495,904,768。

独立公开代码检出及新建环境完成安装，252 项单元测试通过；GitHub CI 的 Python 3.10 和 3.12 合同检查通过。下载器完成分块和数据库流式 SHA-256、字节数及修订核验，安装收据与公开清单一致。API 查询实际使用新环境中 pip 安装的 site-packages 包，其 20 个 SDK 文件与数据库冻结指纹一致；验证匹配的内嵌索引、95 个领域、四视图全部 755 个标签及 56,917 个不同类别对。完整 16 项只读回归通过，验收期间数据库及输入保持不变。

逐项通过状态、结果指纹与 CI 链接见 [公开复验 JSON](unified_external_validation.json)。数据发布页：[候选发布](https://github.com/yyh427/fineAtlas-V1/releases/tag/v1.10.1-repair-review)；清单：[unified_data.json](https://github.com/yyh427/fineAtlas-V1/releases/download/v1.10.1-repair-review/unified_data.json)。

路径准入表示相应视图的层次导航可用；训练奖励准入独立遵循明确类型策略、范围审定及信息性共同祖先。身份未确认的标签保留 REVIEW；根可达不代表精确身份确认。结构、来源保留与接口验收不证明全部原来源分类学、视觉指标或跨领域奖励已经科学校准，也不自动替换生产版本。
