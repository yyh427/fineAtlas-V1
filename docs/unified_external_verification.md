# 正式 v1.10.1 外部安装与默认流程复验

**状态：ACTUAL_DEFAULT_MAIN_PUBLIC_INSTALL_VERIFIED，九步默认公网流程及完整16阶段回归全部PASS。** 正式数据为 `v1.10.1`、SDK `1.10.1`、默认视图 `unified`。[正式Release](https://github.com/yyh427/fineAtlas-V1/releases/tag/v1.10.1)已实际公开（ID407453681、draft=false、prerelease=false、Latest=true），main已切换为正式默认版。正式两源独立提升、匹配浏览索引重建、16阶段本地验收、105张逻辑表／模式比较、103张非浏览表的来源语义保留检查及本地283项测试均通过。实际已安装SDK API和完整16阶段公网回归均通过，回归于2026-10-09 04:27:32 UTC结束；旧修复候选的公网PASS不能替代此次正式复验。

正式数据库的SHA-256、字节数、revision和分片以 [unified_data.json](../unified_data.json)为准；真实SDK固定commit／标签以 [unified_code.json](../unified_code.json)为准。固定tag `v1.10.1` 指向`9d72814b68066654569f09a085ba27f9a73630b0`；[PR #7](https://github.com/yyh427/fineAtlas-V1/pull/7)已合入main，merge commit为`d3c892f89ea0321b866700286a578023ab3c7fa6`。实际公网ordinary clone使用此main合并提交`d3c892f89ea0321b866700286a578023ab3c7fa6`，与固定C3代码tag提交分别记录。普通clone不指定分支、下载不传`--manifest`、stats不覆盖默认视图，全新venv实际pip安装SDK；九个实际步骤均PASS，包含完整16阶段公网回归。该凭据不代表后续仅含文档／证明JSON的提交重新下载或重跑全量验收。本页不把旧候选的校验值或测试数量当作正式结果。

## 默认用户流程

此次实际默认安装测试从普通无分支clone开始，用全新环境 `pip install .`，无 `--manifest` 下载、无视图参数 `fineatlas stats`，已实际得到正式1.10.1／unified。`check_installation.py` 和 `verify_unified_install.py` 不要求显式输入默认清单或验收快照，实际API来自新环境的已安装site-packages SDK。

完整可执行命令见 [README](../README.md)，旧1.6下载与代码／环境回退见 [migration_v1.10.1.md](migration_v1.10.1.md)。下载器对旧版本和候选要求显式选择清单，保留旧目录而不覆盖。

## 已取得的真实凭据

| 检查 | 当前状态 | 实际结果 |
|---|---|---|
| 正式代码、版本与GitHub CI | PASS | C3标签／分支及[main CI 37879689603](https://github.com/yyh427/fineAtlas-V1/actions/runs/37879689603)均通过Python3.10／3.12；普通main全新安装283项测试通过，耗时121.711秒 |
| 远端附件和旧版本保留 | PASS | 六个数据库分片与八份发布清单／报告附件SHA／字节数核验通过，旧发布与标签保留；实际公网验收证明另见下方JSON |
| 正式数据库分片与完整文件 | PASS | 六分片无认证默认下载及完整数据库SHA通过；04:12 UTC整库完成，68,495,904,768字节与正式清单一致 |
| 安装收据与代码指纹 | PASS | 普通main clone、全新venv、pip安装、283项测试及数据安装收据核验通过；实际SDK来自fresh venv site-packages，20个冻结SDK文件通过 |
| 默认视图与索引 | PASS | 无视图参数stats和check_installation通过；SDK1.10.1、默认unified、revision1325af…及匹配浏览索引正确 |
| 全部95域、755标签四视图和56917对 | PASS | 正式实际已安装SDK API逐项对照通过；9个既有WordNet接入点与ABO4范围保留 |
| 完整只读回归 | 本地及公网16阶段PASS | 公网16阶段全部实际exit0且语义PASS，结束于2026-10-09 04:27:32 UTC；九步默认公网流程实际全PASS |
| GitHub main／Latest与普通clone | PASS | Release为正式Latest，PR7已合main；普通无分支clone和全新安装通过；旧1.6及候选保留 |

正式实际结果及CI链接由 [公开复验JSON](unified_external_validation.json)记录；该JSON必须明确绑定正式版本和文件，不因旧报告all_pass=true而认定此次正式安装通过。

## 证据边界

身份确认、根可达、路径准入和训练奖励适用性分别检查。保留CUB15个annotation-scope REVIEW、CRJ-700世界精确身份REVIEW、Cars135／19110可用层次对、4180个无根导航UID／2976身份组及283个角色冲突组。不可用层次项保留mask和null距离，类别正确性奖励独立保留。

runner的范围外说明继续包括全部旧来源关系／身份的独立科学语义认证、全部注释范围解决和视觉奖励校准；这两项未由发布或安装检查完成。live公网下载／重安装是独立发布流程，不宣称16阶段runner自行做了下载。结构、来源保留和API通过不证明识别准确率提高或跨领域奖励已经校准。
