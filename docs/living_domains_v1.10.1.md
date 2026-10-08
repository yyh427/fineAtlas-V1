# 1.10.1 生活领域入口与家具元数据试接

本批冻结输入包含 **4 个新增浏览入口、9 个已有 WordNet 3.1 根，以及 4 条 ABO 来源商品配置**。主候选 `v1.10.1-repair-review` 已完成构建，并于 2026-10-08 20:58 UTC 通过本页范围的只读前后对比。完整回归、独立复建一致性和公开安装仍须以各自验收报告为准；局部检查不等于发布验收通过。

## 四个浏览入口

入口复用已导入的真实 synset，沿保留的来源关系组织浏览。没有重复创建这些分类，没有把入口名称当作概念身份，也没有为目录增加人工 `IS_A`。WordNet 原定义和许可保留在数据库及 [WordNet 许可](WORDNET_LICENSE.txt) 中。

| 入口 | WordNet 3.1 根 UID | 来源定义的含义 |
|---|---|---|
| `kitchen_and_tableware` | `wordnet31:03626258-n` — kitchen utensil | 用于准备食物的器具 |
| 同上 | `wordnet31:04389081-n` — tableware | 在餐桌使用的器皿、餐具和玻璃器具 |
| `lighting` | `wordnet31:03641539-n` — lamp | 人工可见光源 |
| 同上 | `wordnet31:03641940-n` — lamp | 支承一个或多个电灯泡的家具器具 |
| 同上 | `wordnet31:03672706-n` — lighting fixture | 提供人工照明的固定装置 |
| `bags_and_luggage` | `wordnet31:02772753-n` — backpack | 以背部或肩部背带携带的包 |
| 同上 | `wordnet31:02777157-n` — handbag | 携带钱、小件个人物品或配件的包 |
| 同上 | `wordnet31:02777635-n` — luggage | 旅行时携带物品的箱包 |
| `toys` | `wordnet31:03971038-n` — plaything | 设计用于玩耍的人工物品 |

两个 `lamp` 词义各保留自己的 UID；手袋、背包和行李使用各自真实词义。原 `dishes` 的菜肴范围继续保留。`toys` 按 plaything 的来源范围组织，不能仅凭名称中的 “model” 判定任意模型为玩具。

冻结 WordNet 来源范围中，各入口的去重 synset 并集分别为 **155、43、24、51**，包括根。这些是已有 WordNet 来源概念数，允许与其他领域重叠；不是新增节点数，也不是最终候选的全部领域成员数。

已有细类可以通过明确入口找到，例如：

| 领域 | 实际来源细类示例 |
|---|---|
| 厨具餐具 | cooking utensil `wordnet31:03106637-n`；grater `wordnet31:03459829-n`；cutlery `wordnet31:03158041-n`；glassware `wordnet31:03443988-n` |
| 照明 | floor lamp `wordnet31:03371905-n`；table lamp `wordnet31:04387620-n`；chandelier `wordnet31:03008889-n` |
| 背包箱包 | kitbag `wordnet31:03625002-n`；clutch bag `wordnet31:03059403-n`；hand luggage `wordnet31:03492616-n` |
| 玩具 | doll `wordnet31:03223838-n`；dollhouse `wordnet31:03224065-n`；Frisbee `wordnet31:03402783-n` |

这些入口组织 WordNet 原有类型路径，其范围不等同于厂商在售商品目录。此次主要改善已有分类的发现与浏览，不据此宣称新增了大量型号。

成员统计区分两个口径：来源 UID 数保留各来源的独立记录，身份组数按已接受身份关系去重。按角色统计时，同一个身份组可能同时含不同角色的来源记录，不能把各角色的身份组数相加作为全域概念数。领域也允许合法重叠。深度表示从任一领域根出发的最短合法导航距离，不是全局根距离，也不是所有路径中的最大层数。

主候选中实际可浏览的成员如下，每格为 **来源 UID 数／该角色内身份组数**：

| 入口 | CLASS | MODEL_FAMILY | MODEL | CONFIGURATION | INSTANCE | DATASET_CATEGORY | CLASS 最短深度范围 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `kitchen_and_tableware` | 186／184 | 4／3 | 11／7 | 0／0 | 4／4 | 0／0 | 0–4 |
| `lighting` | 58／58 | 0／0 | 0／0 | 0／0 | 0／0 | 1／1 | 0–4 |
| `bags_and_luggage` | 32／32 | 0／0 | 0／0 | 0／0 | 0／0 | 0／0 | 0–3 |
| `toys` | 67／67 | 4／3 | 6／5 | 25／25 | 0／0 | 2／2 | 0–3 |

这些成员来自此前已保留的来源记录，新增的是四个明确的浏览入口。原 91 个规范域的名称、ID、入口 UID、根范围及 588 条旧兼容别名完整行均保持不变；主候选共有 95 个规范域、610 条别名。9 个新入口根都有合法统一根路径；上述 155、43、24、51 个 WordNet 来源 UID 全部在相应域中，原标签和原生数据未变。

## ABO 家具小批次

来源为 [Amazon Berkeley Objects](https://amazon-berkeley-objects.s3.us-east-1.amazonaws.com/index.html)。试接复用 [metadata shard 0](https://amazon-berkeley-objects.s3.us-east-1.amazonaws.com/listings/metadata/listings_0.json.gz) 的前 200 条冻结记录，不下载图像或三维资产。该样本有顺序偏差，不能推断全源家具覆盖。

审定 4 条来源配置，原始多语言名称、列表值字段、商品类型、目录路径、型号字段、配置属性和资产标识均保留：

| 来源身份 `(domain_name, item_id)` | 商品范围 | 角色及类型连接 |
|---|---|---|
| `amazon.com`, `B072ZLCB3M` | Rivet Bristol 边桌，Walnut | `CONFIGURATION` → table `wordnet31:04386330-n` |
| `amazon.com`, `B07TMH6289` | AmazonBasics 儿童／少年躺椅，Light Blue | `CONFIGURATION` → chair `wordnet31:03005231-n` |
| `amazon.com`, `B075X4QMW7` | Rivet Eva 组合沙发，87 英寸，Navy | `CONFIGURATION` → sofa `wordnet31:04263630-n` |
| `amazon.com`, `B07F2X8K62` | Ravenna Home Radford 扶手椅，28.15 英寸 | `CONFIGURATION` → chair `wordnet31:03005231-n` |

连接关系是 `CONFIGURATION_TYPE_OF`。身份仅由来源的 `(domain_name, item_id)` 确定；商品 listing 没有被提升为全球制造商 `MODEL`、`MODEL_FAMILY` 或有序列号的实物 `INSTANCE`。品牌、同名和 `model_number` 不用于自动建立跨市场身份桥。

同样本另有 3 条家具候选未导入：

| 来源记录 | 原因 |
|---|---|
| `amazon.co.uk`, `B07CTPR73M` | `product_type=SOFA`，实际标题是布料色样 Swatch |
| `amazon.de`, `B075NR8HWJ` | 商品标题 Dofsan 与 `model_name=Homesick` 的范围需要进一步审定 |
| `amazon.com`, `B07B4SCB6T` | 多语言名称中的 Queen／King 和尺寸存在配置范围冲突 |

因此本批输入数为 4 个入口、4 条配置；新增全球型号、系列和物理实例的数量均为 0。排除记录保留在小样本及来源审查中。

主候选已确认这 4 个来源 UID 在旧 1.10 库中不存在；四条均保留完整原生字段及来源证明，以 `CONFIGURATION` 角色和 `CONFIGURATION_TYPE_OF` 连接进入 `furniture` 域，并具有合法根路径。家具域配置从 **38 条来源 UID／38 个身份组增加到 42／42**；其 CLASS（1342／1339）、MODEL（27／26）、MODEL_FAMILY（2／2）、INSTANCE（3／3）及 DATASET_CATEGORY（6／6）数量保持不变。此处核验的是目录配置身份，未确证全球产品身份。

## 许可、署名与版本定位

ABO 官方 [README](https://amazon-berkeley-objects.s3.us-east-1.amazonaws.com/README.md) 和 [完整许可](https://amazon-berkeley-objects.s3.us-east-1.amazonaws.com/LICENSE-CC-BY-4.0.txt) 指定 **CC BY 4.0**。版权归 **Amazon.com**。数据集建设者署名为：**Matthieu Guillaumin、Thomas Dideriksen、Kenan Deng、Himanshu Arora、Jasmine Collins、Jitendra Malik**。

本次改动说明：选择有界元数据子集，增加经过审定的来源配置角色和 WordNet 类型连接；原生字段不改写。来源 URI、许可 URI、版权和指定署名保留在冻结输入、数据库 provenance／`source_catalogs` 及 `ABO_ATTRIBUTION.txt` 中。接口代码的 MIT 许可不替代来源许可。

| 冻结文件 | SHA-256 |
|---|---|
| 实际 200 条 metadata 样本 | `e34761896d8c32b82eb36b7380b8f2b7c5f0b522fb275a83d714a878651cf746` |
| 官方 README | `3f42e33f6636704b5670b6a198b0403b2f885cebe459d9620f84e7323a61bc71` |
| 官方 CC BY 4.0 许可文件 | `419896aea50c15d6e40c5b4baf4bd346f78223b9a354c7357ad00262afdc08ec` |

版本依据是实际冻结样本的校验值，不给静态来源编造语义版本。原厂商 HTML、第三方 PDF、图片和三维文件不作为本批发布资产。

## 候选验收

聚焦验收必须验证原 91 个规范域及全部旧别名、9 个新增根、163 条接入规则对应关系、上述四个完整 WordNet 来源范围、公开 CLASS 分页和 4 条配置的角色、原记录及合法根路径。新增入口采用追加 ID，保留既有规范范围及原始域声明。

本页实测数量绑定主候选 revision `da98222833499cf1bb84ff2f64376e5a4fb0594786e04a29694d5bb86c4b7492`。局部只读对比已通过；公开 CLASS 完整分页、全部接入规则、完整四视图及公开安装由候选验收分别检查。

验收通过后，使用 `FineAtlas` 的 `domain()` 和 `domain_page()` 浏览这些入口。聚焦验收不能代替完整四视图检查、缓存与版本一致性、非重点回归、独立复建及公开下载复验。

```python
from fineatlas import FineAtlas

with FineAtlas("fineatlas.sqlite", relation_view="unified") as atlas:
    entry = atlas.domain("kitchen_and_tableware")
    page = atlas.domain_page("kitchen_and_tableware", node_kind="CLASS", limit=20)
    # page["next_cursor"] 配合 page["has_more"] 用于继续分页。
    furniture_configs = atlas.domain_page("furniture", node_kind="CONFIGURATION", limit=20)
```

配置页还包括原有来源配置；页面数量不等于本次 ABO 新增量。
