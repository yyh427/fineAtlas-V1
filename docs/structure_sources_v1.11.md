# 1.11 新审阅来源和分发范围

沿用 [来源合同](unified_sources.md) 及 [数据来源](../DATA_SOURCES.md)。来源 UID、版本、出处、原始声明与审核历史分别保留；代码许可不替代各来源数据许可。

- ABO：[官方目录](https://amazon-berkeley-objects.s3.us-east-1.amazonaws.com/index.html)、[仅商品元数据归档](https://amazon-berkeley-objects.s3.us-east-1.amazonaws.com/archives/abo-listings.tar)，归档 SHA `b7f7ceacb328fa5ab6e143b88e1f948443a877cfc95b67ff09c8ebabd50644e3`。Amazon.com，CC BY 4.0；原署名与许可保留。新增记录只作来源配置，新增类型对应及字段索引是本轮修改。没有图像、旋转图或 3D 数据下载。
- WordNet：3.1 固定快照和原许可。WFO、OTT、AviList 沿用实际冻结版本。科学名称核对只提供级别候选；不同 UID 未经范围审定不折叠。
- CUB/Flowers：[CUB 原作者技术报告](https://authors.library.caltech.edu/records/cvm3y-5hh21/files/CUB_200_2011.pdf?download=1)、[后续分类研究作者的范围说明](https://github.com/cvjena/semantic-embeddings/blob/master/CUB-Hierarchy/README.md)、[Oxford 作者类别](https://www.robots.ox.ac.uk/~vgg/data/flowers/102/categories.html)。保留作者标签和范围证据；不采用多数物种替换或人为等深分类。论文/网页原文仅本地审核，不公开打包全文。
- Aircraft：FGVC-Aircraft 2013b 作者原生 variant/family/manufacturer 标注，FAA 登记与原厂资料分开。作者分组有独立来源 UID，不声称已确认商业对象身份。无图像下载或实验。
- Cars：EPA/vPIC/原厂的具体来源字段或设计定义用于范围审定；名称或制造商匹配不能证明身份。21 世纪年款目录没有自动构成代际/chassis 交叉表，缺证据项保留。
- VBO：已有 2026-04-15 本地本体快照，SHA `ed9c758eefc0439df3e3f46d1b014a72a2878bef89628f3e92e2befe253ac08d`，保留 Monarch 署名和 CC BY 4.0。FCI 官方标准号码、组和 section 的派生事实作为版本化组织目录；不公开原始标准 PDF、图像或网页全文，不用于进化或视觉距离。

每一修复输入包含实际来源 URL、快照哈希和范围理由。直接下载遇到的 403/404 等错误保留；官方网页可读取的事实与本地归档成功证据分开记录。可公开的派生事实和冻结输入由 release 附件清单列明，私人原始网页、论文、凭据和数据库不进入普通 Git 提交。
