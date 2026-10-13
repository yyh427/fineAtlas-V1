# FineAtlas 755类可搜索图修复交付报告

本轮原六域755类已通过节点、合法完整导航路径、领域入口展开、逐边实际展开、非自身锚点动态候选、原生答案资格和精确评价验收。世界身份语义核验仅部分完成：416条沿用有效确认，339条仍缺完整世界范围证据（333 REVIEW、5 BROADER、1 REVOKED_EXACT）。这不是全库语义认证，也不是图像识别召回结果。

## 版本与保护

- 接续提交：`f198381582283de8ab658d20dd55be6a90f725ed`，源修订`fb63d9dfbbeba5a9d59289d147e65310cc5003b47b0b23c33d18a83793c2fa7f`。
- 分支：`repair/native755-searchable-graph-20261013`；交付提交：`1cbc84aa57af48f00f3d5ae27b835ae1a8e8efe7`。
- SDK：`1.11.0rc1+native755.graph.20261013`；候选数据库：`/data/yaoyuhan/FineAtlas-Eval/v1/repair_755_graph_20261013_020857/artifacts/fineatlas.sqlite`。
- 候选修订：`563950e014f84b17401a39efc389672e9bb3032e4cc934cf43d0885168cf0002`；SHA256：`aed35e92c0f1e5fd8b46462af1ef93af6853159c9edd50cefa9f86942807f8fc`；76014833664字节。
- SQLite backup产生一致独立快照；未覆盖上轮交付、v1.10.1、原rc1、独立增量或历史V26文件。保护校验见preservation_and_increment_acceptance.json；未发布、切换默认或训练。
- unified视图，reviewed_paths准入，source_native目标，open模式，closed_dataset=null，层级奖励关闭；规则、代码和SDK逐文件哈希均封存在run_config/数据库元数据。

## 覆盖与口径

|域|原生类|节点|路径/入口展开|逐边展开|动态候选|原生精确|世界有效确认|仅粗连接|
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|cub200|200|200|200|200|200|200|173|4|
|fgvc_aircraft|100|100|100|100|100|100|0|0|
|flowers102|102|102|102|102|102|102|87|5|
|pets37|37|37|37|37|37|37|37|0|
|stanford_dogs|120|120|120|120|120|120|119|0|
|stanford_cars|196|196|196|196|196|196|0|0|

逐类后台使用来源ID定位被检类别，寻找有证据的非自身上层并全分页检查；这是结构验收，绝不将这些锚点作为当前图像的真实父节点输入模型。模型接口只接受本会话已发出的导航/答案句柄。开放模式的范围来自图，不来自755完整表或某数据集白名单。

## 四项结果

身份：有效世界状态416/333/5/1本轮没有提升。相对原rc1的495确认，79条减少来自Aircraft76、Flowers2、dingo1，均为上轮已有撤回，本轮保留；不把未确认当错误。裸VERIFIED但世界未确认118条（115 REVIEW、3 BROADER；仅精确该登记值，不包括VERIFIED_CATEGORY_MAPPING等别的登记类型）。逐类实际查询原资料并保存755份检查记录，未确认339条有缺证与后续核查路径。416确认的旧证据存在性、角色及分量一致性已核查；没有宣称对416条全部重新鉴定了作者所有图像范围。

粒度：755类均有来源单位声明；Flowers为异质作者类别，Dogs区分117品种标签、dingo来源标签、dhole/African hunting dog野生物种标签；Aircraft为作者视觉variant；Cars为组合标注。未知世界范围和粒度保持未知。反馈公开source/source_unit，原生和世界精确分别评价。精确等价、导航和层级适用分开，不把父类/宽范围计精确，不用最大层级惩罚替代NA。

重复：同一组755次原名查询、预算10/80，新discovery重复占位均0；任务非法答案槽均0；新discovery/答案空查询均0。原始旧搜索Cars175次空仍存在，仅用于比较。旧raw component重复槽571/844，新显示只对连接且角色/范围/粒度兼容的已确认分量聚合，再截断。名字相同但身份未确认的表示保留，不把“零已确认分量重复”写成“全库无同义重复”。查询详细原槽位、唯一分量和新表示数见fixed755_queries.json。

本轮名称查询完整复算的修订为a92c261d…。后续两次封存只改7行metadata；query/evaluation代码及所有语义/索引表未变化，因此通过query_acceptance_final_binding.json复核绑定并保留原测试修订，没有伪造重跑结果。新版范围排序、导航与反馈在最终修订另行验收。

领域结构：基线755有节点、上层关系与缓存路径，但原neighbors对直接上层逐类展开0/755（限定该旧接口/口径，不宣称所有旧浏览功能不可达）。本轮修复混合关系与完整来源结构，实际新增445个来源概念，单位计数{"source_make_scope": 49, "source_design_label_scope": 174, "author_year_attribute": 16, "author_body_attribute": 18, "source_manufacturer_scope": 30, "lexical_canid_type": 158}。检查567条分类断言（566活跃IS_A、1改REVIEW）和803条类型/属性断言：DEPICTS_TYPE354、HAS_ATTRIBUTE377、DESIGN_TYPE_OF70、DEPICTS_DESIGN1、SOURCE_TYPE_REFERENCE1。均是本轮断言口径，不是566个新的独立世界事实。119条Dogs规范父类型来源断言，57对此前缺直接同分量父连接，62条是现有连接的补来源。

Cars49 make范围、174 design-label前缀范围只代表作者标签谓词及其范围包含，不是174个已确认厂商车型或系列；18车身、16年份属性不用IS_A。196组合类别都通过motor vehicle→make→design-label→DEPICTS_TYPE进入图。世界车型/配置/市场范围196类仍未完整核实。Dogs158个原WordNet3.0义项（120叶义项和38上层）按官方@指针接入；37个Pets世界品种补猫/犬类型关系；根的跨版本引用由IS_A改为SOURCE_TYPE_REFERENCE，不虚增严格深度。Aircraft30制造商类型范围与70作者family依据逐图三字段一致性接入，不把variant和family/model等同。

仅粗连接9类：cub200:17 Cardinal；cub200:91 Mockingbird；cub200:101 White Pelican；cub200:130 Tree Sparrow；flowers102:27 prince of wales feathers；flowers102:45 bolero deep blue；flowers102:46 wallflower；flowers102:47 marigold；flowers102:92 bee balm。口径是直接合法类型父仅领域根/纲/目/科；属和有区分作用的来源范围不计粗根。Cars的来源前缀结构完整不意味着世界OEM结构完整，二者另列。

## 具体案例

- cub200/91 Mockingbird：`caltech-cub200-2011:category:91`；世界REVIEW。birds [DOMAIN_ENTRY_ROOT] → bird [IS_A] → Passeriformes [IS_A] → Mimidae [DEPICTS_TYPE] → Mockingbird。
- fgvc_aircraft/38 BAE 146-200：`fgvc-aircraft-2013b:variant:bae 146-200`；世界REVOKED_EXACT。aircraft [DOMAIN_ENTRY_ROOT] → aircraft [DESIGN_TYPE_OF] → BAE 146 [FGVC family] [SERIES_MEMBER_OF] → BAE 146-200。
- flowers102/92 bee balm：`oxford-flowers102:category:92`；世界REVIEW。plants [DOMAIN_ENTRY_ROOT] → Plantae [IS_A] → Pteridobiotina [IS_A] → Angiosperms [IS_A] → Lamiales [IS_A] → Lamiaceae [DEPICTS_TYPE] → bee balm。
- flowers102/74 rose：`oxford-flowers102:category:74`；世界CONFIRMED。plants [DOMAIN_ENTRY_ROOT] → Plantae [IS_A] → Pteridobiotina [IS_A] → Angiosperms [IS_A] → Rosales [IS_A] → Rosaceae [IS_A] → Rosa [DEPICTS_TYPE] → rose。
- flowers102/56 bishop of llandaff：`oxford-flowers102:category:56`；世界CONFIRMED。plants [DOMAIN_ENTRY_ROOT] → Plantae [IS_A] → Pteridobiotina [IS_A] → Angiosperms [IS_A] → Asterales [IS_A] → Asteraceae [IS_A] → Asteroideae [IS_A] → Coreopsideae [IS_A] → Dahlia [TAXONOMIC_PARENT] → Dahlia ʽBishop of Llandaff’ [DEPICTS_TYPE] → bishop of llandaff。
- stanford_cars/38 BMW Z4 Convertible 2012：`stanford-cars-2013:class:38`；世界REVIEW。cars and road motor vehicles [DOMAIN_ENTRY_ROOT] → motor_vehicle [IS_A] → BMW vehicles [source make scope] [IS_A] → BMW Z4 [source design-label scope] [DEPICTS_TYPE] → BMW Z4 Convertible 2012。
- stanford_dogs/1 Chihuahua：`stanford_dogs:2011:label:1`；世界CONFIRMED。animals [DOMAIN_ENTRY_ROOT] → animal [IS_A] → chordate [IS_A] → vertebrate [IS_A] → mammal [IS_A] → placental [IS_A] → carnivore [IS_A] → canine [SOURCE_TYPE_REFERENCE] → canine [WordNet3.0 sense] [IS_A] → dog [WordNet3.0 sense] [IS_A] → toy dog [WordNet3.0 sense] [IS_A] → Chihuahua [WordNet3.0 sense] [DEPICTS_TYPE] → Chihuahua。
- stanford_dogs/118 dingo：`stanford_dogs:2011:label:118`；世界BROADER。animals [DOMAIN_ENTRY_ROOT] → animal [IS_A] → chordate [IS_A] → vertebrate [IS_A] → mammal [IS_A] → placental [IS_A] → carnivore [IS_A] → canine [SOURCE_TYPE_REFERENCE] → canine [WordNet3.0 sense] [IS_A] → wild dog [WordNet3.0 sense] [IS_A] → dingo [WordNet3.0 sense] [DEPICTS_TYPE] → dingo。
- stanford_dogs/119 dhole：`stanford_dogs:2011:label:119`；世界CONFIRMED。animals [DOMAIN_ENTRY_ROOT] → animal [IS_A] → chordate [IS_A] → vertebrate [IS_A] → mammal [IS_A] → placental [IS_A] → carnivore [IS_A] → canine [SOURCE_TYPE_REFERENCE] → canine [WordNet3.0 sense] [IS_A] → wild dog [WordNet3.0 sense] [IS_A] → dhole [WordNet3.0 sense] [DEPICTS_TYPE] → dhole。
- stanford_dogs/120 African hunting dog：`stanford_dogs:2011:label:120`；世界CONFIRMED。animals [DOMAIN_ENTRY_ROOT] → animal [IS_A] → chordate [IS_A] → vertebrate [IS_A] → mammal [IS_A] → placental [IS_A] → carnivore [IS_A] → canine [SOURCE_TYPE_REFERENCE] → canine [WordNet3.0 sense] [IS_A] → wild dog [WordNet3.0 sense] [IS_A] → African hunting dog [WordNet3.0 sense] [DEPICTS_TYPE] → African hunting dog。

BMW38另有DEPICTS_DESIGN→vpic-model:452:1725，来自NHTSA型号与2012 BMW官方资料，不能等同具体EPA配置；bee balm92依据NC State的Monarda/Melissa共享Lamiaceae增加上界，未选择具体种；Mockingbird91保持原作者范围待审，不能从Mimus或同名推断Northern Mockingbird；Bishop保留cultivar/TAXONOMIC_PARENT；rose74的当前确认目标是属级wfo:wfo-4000033476 Rosa，不能强制过滤为species。同名Rosa的其他未确认来源表示不自动计作该精确身份。European pipit及Chihuahua等别名/截断回归在既有测试及个案报告复核，不能按名称合并来源节点。White Pelican额外检查Cornell和BirdLife的两种白鹈鹕资料，记录了同属事实，但没有作者完整范围证明，未据此确认具体种或写未经充分证明的上层。

## 固定层级项与验收

固定56917同域异类无序对=CUB19900、Aircraft4950、Flowers5151、Pets666、Dogs7140、Cars19110；分子是旧评价规则在选定view/准入/目标范围下返回APPLICABLE的对数，非边数量/树覆盖率。原requirement/source_scope逐行保留于固定56917对复算对照.csv。Dogs reviewed_paths/world由716/7140到2427/7140；其余4594粗共同祖先、119端点不适用。Cars world为0/19110（端点未确认），source_native为0/19110（仅旧层级项认为粗共同祖先）；Cars新的typed来源路径已成立，不能由0说无关系。历史135/19110和717/7140属于旧版本/旧判定，不能混用。准确率实验不启用层级奖励。

1173项非GPU回归通过；修复相关1370断言、1007身份分量及1193上行分量检查通过，无新增非法角色、自环/相关闭包循环；不认证全库继承语义。所有本轮操作幂等重放零改动，真实inverse writes在事务中回退到fb63、移除445新节点并保留755/增量计数后ROLLBACK，候选保留最终修订。SDK wheel独立环境验证绑定和实际CLI/工具反馈。

15组通用文本→公开句柄→动态范围/展开/分页/约束回归通过（14组完整范围，Lamiaceae一组触及20000节点预算，明确保留不完整诊断，原生候选在首屏；不称该范围全覆盖）；全部同名类型替代表示可按来源辨别，不把来源field当世界等价。目标source_native只优先排序范围内原生答案，其余合法世界对象仍保留；混合遍历先检查类型引用，再检查分类子节点；所有边类型/来源保留，超预算明确诊断。不是视觉识别实验，不能声称模型自主锚点命中或识别召回改善。

## 独立增量

接续上轮已协调增量，13登记项、111937集成对象原文及哈希、15274原生记录（755核心+14519扩展）逐行摘要不变；7 UID存在性、角色/可见性/原生答案合同复核通过。13672扩展训练ID可用、847仍阻塞（NABirds555、VegFru292），644世界映射隔离保留。增量旧包依赖v1.10.1不能直接覆盖rc1；本轮保留上轮已协调结果，不扩展任务，不混入755分母。

## 使用、回退与剩余工作

使用匹配wheel安装在独立环境；运行配置位于artifacts/run_config.json。模型接口为FineAtlasExperimentTool.entries/query/scope与scripts/experiment_scope755.py；scope输入仅已发出句柄、视图、目标粒度，输出实际范围、名字索引、路径、候选资格和约束。CLI也经同一expand_scope返回DOMAIN_ENTRY_ROOT导航入口，再展开真实类型。原生类ID查询/evaluate_exact属于后台，不能送到模型。具体命令见USAGE_AND_ROLLBACK.md。

回退优先选择上轮独立库与其SDK/config（从未覆盖）；若需逆向候选，先对候选再建一致工作快照，在无读者/训练使用时按journal逆序逐包rollback，禁止乱序。事务验证已覆盖所有本轮包并保留上轮增量。不要用含旧SDK的config读取新候选。

已完成：755真实图接入、源范围结构、接口/单位资格/安全聚合/分页、源码提交、快照、必要回归和交付。部分完成：世界精确身份核验和各域世界细粒度结构；339世界映射与9粗连接的逐条缺证在问题CSV，Cars196需要OEM/市场/配置完整范围，Aircraft100需要作者visual variant所覆盖真实型号交叉表，CUB27需要历史物种/亚种与作者图像范围，Flowers15含宽映射需类别属种/栽培品种范围，Dogs dingo需范围与分类处理。未开始：图像模型自主导航/识别实验、训练和正式发布（本轮不执行）。没有工程未验收项冒充完成。

可进入小规模原生755准确率/导航试验；不能把339条未确认作为世界身份监督，不能将本报告当视觉提升证据。建议先做少量跨域图像端到端锚点/分页/原生精确验证，再按批量作者范围资料解决Aircraft/Cars，随后补CUB/Flowers个例与粗结构。保留层级奖励关闭。后续按检查点续跑，新增证据充分才发新操作包；不恢复已撤销确认。完成本轮后停止，等待用户确认下一阶段。
