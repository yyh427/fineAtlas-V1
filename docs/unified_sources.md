# 统一候选的来源与分发范围

WordNet 固定为 3.1；数据库保存 synset、原定义、来源校验值和接入依据。原数据来源及许可仍适用于各自记录，接口代码的 MIT 许可不替代第三方数据许可。

本轮冻结来源附件包含 Wikidata CC0 JSON（原 revision ID、抓取批次 SHA 和声明保留）及 AviList Core Team 的 [AviList v2025b，10 June 2026](https://www.avilist.org/checklist/v2025b/) 检查表，后者遵循 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。完整附件清单和逐文件 SHA 见候选附件 `source_snapshot_manifest.json`。OpenTree 原生父级使用 OTT **3.7draft3**，不把目录名 ott3.7.3 当作版本依据；相关原始行、标识、来源 SHA 和放置标记保存在冻结规则中。

FAA 和 EPA 中间层只采用明确原生字段和目录定义。制造商、年份、国家等仍为目录或属性；没有字段不填猜测值。历史来源和原始数据不由本次归档替换。

McLaren 厂商手册、EASA 型号证书和 Transport Canada 页面仅保留核验事实、URL 和校验值；完整 PDF/HTML 不放入 Git 或公开来源附件。McLaren MP4-12C 的 sports car 判断是单独人工核验，CRJ-700 的标注范围仍未确认。它们不包装为来源范围更大的通用规则。
