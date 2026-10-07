# 来源关系浏览与大分支优化

接口版本：`1.9.0rc1`。这是候选功能，最终验证和产物状态以本轮结果报告为准。

## 明确区分四种组织

普通类型使用所选视图允许的分类关系；家族、型号和配置使用原有的
`NATIVE_DESIGN_PARENT`、`SERIES_MEMBER_OF`、`CONFIGURATION_OF` 等真实关系。
制造商、来源目录、年份和原生属性用于目录分组及筛选，不成为 `IS_A` 父节点。
命名实例保留实例角色和 `INSTANCE_OF`。

本轮不以名称前缀推断系列，不按固定数量分桶，不删除节点或原始连接。
对于已有两条真实关系构成的更细路径，浏览可以优先显示该路径；
没有可信中间类型的分支仍保留大分支，明确作为待补语义依据的问题。
因此，分页改善与中间语义层改善需要分别验收。

## 公共接口

```python
from fineatlas import FineAtlas

with FineAtlas('/path/to/new-candidate.sqlite', relation_view='strict') as atlas:
    print(atlas.browse_summary('aircraft'))
    # 默认只展开直接普通类型，单页最多 1000 个身份组。
    page = atlas.browse_children_page('aircraft', limit=20)
    # 在具体类型下分别查看系列、型号、配置及实例。
    models = atlas.browse_children_page(
        'hierarchy-type:aircraft-4-engine-1', node_kind='MODEL', limit=20)
    groups = atlas.browse_groups(
        'hierarchy-type:aircraft-4-engine-1', group_by='manufacturer')
    for group in groups['items']:
        assert group['is_a'] is False
    selected = atlas.browse_children_page(
        'hierarchy-type:aircraft-4-engine-1', node_kind='MODEL',
        filters={'manufacturer': groups['items'][0]['value']}) if groups['items'] else None
    print(atlas.locate('Cessna', domain='aircraft'))
    if models['items']:
        uid = models['items'][0]['uid']
        print(atlas.browse_location(uid, domain='aircraft'))
        print(atlas.source_members_page(uid))
        print(atlas.path_result(uid))        # 原来的最短路径和距离
        print(atlas.browse_path_result(uid)) # 优先有来源见证的细分路径
```

`browse_children_page` 使用身份组件的确定顺序和数据库键集分页。
`next_cursor` 绑定数据库修订、视图、根、父节点、角色、关系、筛选条件及粗连接开关；
跨条件或跨版本使用会报明确参数错误。每个结果包含原始端点 UID、关系、来源、
证据和来源连接数量。身份组的各来源表示通过 `source_members_page` 保留。

`include_coarse=True` 显示完整原始直接连接；默认仅隐藏有允许关系组合和真实
替代路径支持的粗连接。监管关系不会因为物理类型路径存在而被隐藏。
`browse_path_result` 明确返回 `shortest_distance`、`distance`、`path_is_shortest`
和 `selection`，显示路径变长不会被当作最短距离改善。
原 `path_result`、`connection_status` 和任务准入保持同一视图的既有规则。

领域名称、已有别名及 `fineatlas-domain:<name>` 解析到相同原生根。
领域浏览和检索使用相同成员范围。未知节点、未知领域、未准入、缺索引、
过期索引及自定义根外节点返回结构化状态。有效父节点没有所选角色时返回 `EMPTY`。

目录字段只来自已有原生字段：FAA 的 `MFR`、`MODEL`、结构及动力代码；
EPA 的 `make`、`model`、`baseModel`、`year` 和 `VClass`；已有目录、系列字段；
实例已有国家和行政区字段。缺失属性不生成替代值，仍可不加筛选浏览。
同名不同 UID 不合并；制造商目录不能当作真实型号家族。

## 构建、恢复与回滚

源库须为冻结的 `FINEATLAS_SINGLE_DB_V1`。构建只新增派生浏览表和版本元数据，
不修改节点、身份组、原始关系、标签和来源记录。磁盘空间与内存须先核验。
大型库可以用 RAM 暂存索引，然后一次写入独立候选；暂存文件不能单独作为完整库打开。
内存不足时可使用独立候选上的可恢复磁盘构建脚本。

```bash
export TMPDIR=/path/to/work/tmp
export SQLITE_TMPDIR="$TMPDIR"
mkdir -p "$TMPDIR"
python3 scripts/stage_browse_indexes.py --source /path/to/frozen-baseline.sqlite \
  --output /path/to/work/browse-staging.sqlite --reports /path/to/work/build-reports
# 为候选选择新文件，禁止覆盖正式库或旧候选。
cp --reflink=auto --sparse=always /path/to/frozen-baseline.sqlite /path/to/work/candidate.sqlite
python3 scripts/apply_browse_indexes.py --database /path/to/work/candidate.sqlite \
  --baseline /path/to/frozen-baseline.sqlite --staging /path/to/work/browse-staging.sqlite \
  --output /path/to/work/application.json
python3 -m unittest discover -s tests -v
python3 scripts/audit_usability.py --database /path/to/work/candidate.sqlite \
  --output /path/to/work/public-regression
python3 scripts/audit_browse_preservation.py --baseline /path/to/frozen-baseline.sqlite \
  --database /path/to/work/candidate.sqlite --output /path/to/work/preservation
python3 scripts/audit_browsing.py --baseline /path/to/frozen-baseline.sqlite \
  --database /path/to/work/candidate.sqlite --fixed-samples /path/to/fixed_nonfocus_samples.json \
  --output /path/to/work/browse-regression
```

完整身份集合保留同时检查源表逐行相等、身份分区相等，以及每条默认隐藏连接均能
展开为仍然可浏览的来源路径。固定大分支还逐页对比完整直接身份集合。
性能对比使用相同返回规模和缓存条件；首次连接查询不等同于清空操作系统缓存。
不运行图像识别、训练或推理，不由此宣称视觉识别准确率提升。

回滚只需使用原候选或正式库；在新候选中也可设 `include_coarse=True`
并使用原 `path_result`。原始图没有删除操作。

## 仍存在的限制

FAA 原生制造商/型号目录不自动提供可信型号家族；大分支的目录化浏览不能替代
缺失的普通中间类型。已有字段以外的属性不承诺可筛选。CRJ-700 的历史来源精确
身份存在冲突，保留未确认状态，不用宽泛系列替代具体型号。
755 标签的既有覆盖不是本轮新增成果；身份确认、根可达、关系合法和任务可用
必须分别报告。原 v26 的审计口径与当前多视图准入不同，不能直接相减作为改善量。
