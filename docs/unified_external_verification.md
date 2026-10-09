# 正式 v1.10.1 外部安装与默认流程复验

**状态：PENDING。** 正式版目标为数据 `v1.10.1`、SDK `1.10.1` 和默认视图 `unified`。正式两源独立提升、匹配浏览索引重建和16阶段本地验收已通过，105张逻辑表／模式比较、103张非浏览表的来源语义保留检查及本地283项单元测试通过。这里的PENDING专指正式公网安装、正式代码CI及GitHub默认main／Latest切换，不能用本地PASS替代。旧修复候选的公网PASS记录继续保留，但不能替代此正式版的实际复验。

正式数据库的SHA-256、字节数、revision和分片以 [unified_data.json](../unified_data.json)为准；真实SDK固定commit／标签以 [unified_code.json](../unified_code.json)为准。本页在取得正式独立凭据后更新，不引用旧候选校验值或写死其单元测试数量。

## 默认用户流程

目标验收从普通无分支clone开始，用全新环境 `pip install .`，无 `--manifest` 下载、无视图参数 `fineatlas stats`，默认应得到正式1.10.1／unified。`check_installation.py` 和 `verify_unified_install.py` 不要求显式输入默认清单或验收快照，实际API应来自新环境的已安装site-packages SDK。

完整可执行命令见 [README](../README.md)，旧1.6下载与代码／环境回退见 [migration_v1.10.1.md](migration_v1.10.1.md)。下载器对旧版本和候选要求显式选择清单，保留旧目录而不覆盖。

## 通过前必须取得的真实凭据

| 检查 | 当前状态 | 完成标准 |
|---|---|---|
| 正式代码、版本与GitHub CI | PENDING | 精确commit、SDK1.10.1、实际CI矩阵和实际测试数量绑定 |
| 正式数据库分片与完整文件 | PENDING | 无认证实际下载，分片及流式整库SHA／字节数／revision与正式清单一致 |
| 安装收据与代码指纹 | PENDING | 新环境实际pip包、冻结SDK文件、正式清单与数据库收据一致 |
| 默认视图与索引 | 本地PASS；公网PENDING | 默认unified，图／内嵌浏览索引同revision；stats不额外指定视图 |
| 全部95域、755标签四视图和56917对 | 本地PASS；公网PENDING | 对照正式验收快照；既有9个WordNet接入点与ABO4范围保持 |
| 完整只读回归 | 本地16阶段PASS；公网PENDING | 所有正式计划阶段实际exit0与语义PASS，保留各阶段命令与结果 |
| GitHub main／Latest与普通clone | PENDING | 实际远端默认代码与正式Release一致，旧1.6及候选仍可独立访问 |

正式实际结果及CI链接由 [公开复验JSON](unified_external_validation.json)记录；该JSON必须明确绑定正式版本和文件，不因旧报告all_pass=true而认定此次正式安装通过。

## 证据边界

身份确认、根可达、路径准入和训练奖励适用性分别检查。保留CUB15个annotation-scope REVIEW、CRJ-700世界精确身份REVIEW、Cars135／19110可用层次对、4180个无根导航UID／2976身份组及283个角色冲突组。不可用层次项保留mask和null距离，类别正确性奖励独立保留。

runner的范围外说明继续包括全部旧来源关系／身份的独立科学语义认证、全部注释范围解决和视觉奖励校准；这两项未由发布或安装检查完成。live公网下载／重安装是独立发布流程，不宣称16阶段runner自行做了下载。结构、来源保留和API通过不证明识别准确率提高或跨领域奖励已经校准。
