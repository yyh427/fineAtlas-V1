# FineAtlas

当前默认开发版本为 **1.11.0rc1+native755.graph.20261013**。原六域755类全部保留，并通过节点、合法导航路径、实际展开、动态候选、答案资格和原生精确评价验收。

模型导航默认展示名称、别名和可选句柄，使用者可以直接搜索、展开和选择答案。详细来源、身份与路径信息另存为诊断记录。

当前数据以独立预发布标签 `v1.11.0rc1-native755-graph.20261013` 提供。稳定Release仍为 [v1.10.1](https://github.com/yyh427/fineAtlas-V1/releases/tag/v1.10.1)，旧版安装与回退说明见 [稳定版使用说明](docs/stable_v1.10.1_usage.md)。新版已完成结构和接口验收，尚未进行图像模型自主导航或识别实验。

## 安装与下载

需要Python3.10+、zstd，以及至少95GB可用磁盘。为新版使用独立数据目录。

```bash
git clone https://github.com/yyh427/fineAtlas-V1.git
cd fineAtlas-V1
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install .
python3 scripts/download_native755.py --output-dir ./data-native755
python3 scripts/configure_native755.py \
  --database ./data-native755/fineatlas.sqlite \
  --output ./run_config.json
```

服务器已有本轮验收数据库时，可以直接用其准确路径运行配置命令，无需再次下载。数据库SHA-256为 `aed35e92c0f1e5fd8b46462af1ef93af6853159c9edd50cefa9f86942807f8fc`，大小76,014,833,664字节。代码、SDK和数据均进行绑定检查。

## 搜索与导航

`requests.jsonl` 中填写模型自己的文本查询或选择的导航句柄：

```json
{"session_id":"demo","request_id":"entry","action":"entries"}
{"session_id":"demo","request_id":"search","action":"query","query":"BMW","limit":20}
```

```bash
python3 scripts/navigate.py \
  --run-config ./run_config.json \
  --requests ./requests.jsonl \
  --output ./model_feedback.jsonl
```

输出包含名称、别名、答案或导航句柄，以及分页和范围预算诊断。模型从本会话返回的句柄中选择，下一次请求可使用 `expand` 展开一步，或使用 `scope` 获取动态范围内的答案候选。跨进程继续会话时重新提供此前请求，以恢复已发出的句柄。

```json
{"session_id":"demo","request_id":"next","action":"scope","anchor_handles":["上一条返回的句柄"],"limit":20}
```

开放模式没有默认755类白名单，也不输入当前图像真实类别或真实父节点。大范围触及预算时明确报告不完整，不能把分页结束误认为全范围覆盖。

Python中使用同样的简洁展示：

```python
from fineatlas.experiment import FineAtlasExperimentTool
from fineatlas.model_display import simple_feedback

with FineAtlasExperimentTool('run_config.json') as tool:
    result = tool.query('BMW', limit=20)
    print(simple_feedback(result))
    allowed = tool.allowed_choices(result)
```

## 验收与版本范围

- CUB200、Aircraft100、Flowers102、Pets37、Dogs120、Cars196：755/755类通过可搜索图结构及原生评价验收。
- 本轮沿用416个已确认世界映射；333待审、5宽范围、1旧精确映射撤销。这些状态不删除原生类别，也不自动升级为世界身份监督。
- 9类已有粗连接，仍需细粒度来源证据。图像识别效果尚未测量。
- 默认推荐的新导航入口为 `scripts/navigate.py` 和动态范围接口。旧直接浏览缓存保留历史修订，不能用旧IS_A浏览结果代替新版755类混合路径验收。
- SDK核心代码和数据库固定在验收提交 `1cbc84aa57af48f00f3d5ae27b835ae1a8e8efe7`；本次发布增加展示模块和部署脚本，未修改已封存核心或数据库。请使用普通安装，避免editable安装触发核心提交校验。

逐类路径、来源证据和剩余问题见 [完整验收报告](docs/native755_delivery/FINAL_REPORT.md)、[755类验收表](docs/native755_delivery/755类可搜索图逐项验收.csv)和[发布说明](docs/native755_publication.md)。详细诊断可以添加 `--diagnostics-output audit.jsonl`；`--detailed` 显示完整接口反馈，历史接口继续保留。

## 回退

保留旧数据目录，在独立环境使用v1.10.1标签及其数据：

```bash
git clone --branch v1.10.1 --single-branch https://github.com/yyh427/fineAtlas-V1.git fineAtlas-stable
```

旧代码、SDK、配置和数据库作为一组使用。新版下载拒绝覆盖不同校验值的已有数据库。
