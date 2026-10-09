# v1.10.1 默认使用、升级与回退

正式 `v1.10.1`、SDK `1.10.1` 和默认 `unified` 已完成本地两源独立提升与16阶段验收。正式公网安装和GitHub main／Latest切换仍为PENDING；此页给出待发布的正式默认流程和可复现旧版本的路径。旧环境和旧数据目录继续保留。

## 新用户

按 [README 默认安装](../README.md) 普通 clone，不指定分支；创建虚拟环境、`pip install .`，随后 `download_single.py --output-dir ./data`。不传 `--manifest` 时只选择正式默认清单，不自动选择旧 1.6 或候选。`fineatlas --data-dir ./data stats` 不传视图参数，正式库默认 `unified`。

`check_installation.py --data-dir ./data` 和 `verify_unified_install.py --database ./data/fineatlas.sqlite --output ./verification` 默认使用当前正式清单与验收快照。检查依赖实际安装的 SDK，而不是临时从 checkout/src 导入接口。

## 已有 1.6 数据的用户

保留原代码环境与数据目录。将正式版安装在独立 checkout／虚拟环境，并下载到新目录；下载器会拒绝覆盖版本或哈希不同的旧库。

```bash
git clone https://github.com/yyh427/fineAtlas-V1.git fineatlas-v1.10.1
cd fineatlas-v1.10.1
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install .
python3 scripts/download_single.py --output-dir ../fineatlas-v1.10.1-data
fineatlas --data-dir ../fineatlas-v1.10.1-data stats
python3 scripts/check_installation.py --data-dir ../fineatlas-v1.10.1-data
python3 scripts/verify_unified_install.py \
  --database ../fineatlas-v1.10.1-data/fineatlas.sqlite \
  --output ../fineatlas-v1.10.1-verification
```

如设置了 `FINEATLAS_DATA_DIR`，升级后将其指向选定版本目录，或继续显式传 `--data-dir`。候选 `v1.10.1-repair-review` 与正式 `v1.10.1` 采用不同清单、代码冻结与数据库校验；不能因为图内容相近而混用。

## strict 兼容查询与完整旧版本复现

1.10.1 默认 `unified` 有意纳入选定 WordNet 3.1 骨架、合法原生分类及分角色导航。旧脚本若只需要当前库的严格分类关系，可以明确指定：

```bash
fineatlas --data-dir ../fineatlas-v1.10.1-data --relation-view strict stats
```

```python
from fineatlas import FineAtlas

with FineAtlas("../fineatlas-v1.10.1-data/fineatlas.sqlite", relation_view="strict") as atlas:
    print(atlas.stats())
```

新库 `strict` 使用当前已验证角色和关系合同，部分错误旧断言已经纠正，结果可能与旧库不同。需要完整复现 1.6，固定旧代码和旧数据：

```bash
git clone --branch v1.6.0 https://github.com/yyh427/fineAtlas-V1.git fineatlas-v1.6.0
cd fineatlas-v1.6.0
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install .
python3 scripts/download_single.py --manifest single_download.json \
  --output-dir ../fineatlas-v1.6.0-data
fineatlas --data-dir ../fineatlas-v1.6.0-data stats
python3 scripts/check_installation.py --data-dir ../fineatlas-v1.6.0-data
```

这里的 `single_download.json` 来自固定 `v1.6.0` checkout。[1.6 固定清单](https://github.com/yyh427/fineAtlas-V1/blob/v1.6.0/single_download.json)和旧 [Release](https://github.com/yyh427/fineAtlas-V1/releases/tag/v1.6.0)保留；正式代码目录另有 [legacy_single_download_v1.6.0.json](../legacy_single_download_v1.6.0.json)，可用于只下载旧数据。

回退时激活旧 checkout 的 `.venv`，把 `--data-dir` 指向保留的旧目录。再使用正式版时激活其独立环境和数据目录。不需要删除任一数据库，也不需要覆盖候选附件。

## 训练端迁移

根可达、精确身份与奖励掩码分开判断。1.10 修复内容仍保留 CUB15 个范围 REVIEW、CRJ-700 世界精确身份 REVIEW、Cars135／19110 对可用层次项，以及4180 个无根导航来源 UID／2976 个身份组／283 个角色冲突组。不可用端点或类别对保留 `applicable=false`、`distance=null`，训练跳过该层次项并继续保留类别正确性奖励。

不要把 `strict` 的历史方向距离、统一根可达率或厂商目录分组直接用作已校准的视觉类别错误代价。完整接口及关系策略见 [public_api.md](public_api.md)，正式结果与限制见 [unified_results.md](unified_results.md)。
