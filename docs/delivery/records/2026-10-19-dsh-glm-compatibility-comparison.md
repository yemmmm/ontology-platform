# 2026-10-19 DSH GLM 兼容与 Codex 同场景对比

用户要求在 DSH 中以 `glm-5.3-flash low` 执行一组任务，与最近 Codex 建模对比；
发现原隔离适配仅支持 DeepSeek 后，用户明确授权“补齐 GLM 兼容后运行”。
本次沿 R4.3-031／032／033／034 扩展精确 provider 接线，不改变建模业务含义或验收合同。

## 最小兼容范围

- 新增独立 `glm-messages` 目录路由，仅接受本次获准的 `glm-5.3-flash / low`；
  原 `glm-direct` Responses 路由及 Codex 默认保留。无自动回退、模型重命名或档位降级。
- 固定上游 `https://open.bigmodel.cn/api/anthropic/v1/messages`，复用宿主持钥、
  TLS、流式原字节转发、失败分类、凭据销毁及数值用量记录。官方兼容地址依据
  [智谱 Claude Code 文档](https://docs.bigmodel.cn/cn/coding-plan/tool/claude)。
- 复用固定 DSH Messages codec，单独注册 GLM provider；冻结本地 composition 摘要与
  实际有效绑定。原 DeepSeek 插件、工具集合／schema、资料隔离、控制与独立验收保持。
- Delivery、生产及独立 Consumer/Judge 全部显式 DSH／GLM。GLM credential 复用平台已有
  私有文件，只给隔离角色临时代理 token；没有复制 DSH 网页保存的另一份密钥。
  真实上游小请求 HTTP 200、响应模型精确，low 原样发送；不由响应推断供应商内部推理预算。
- 已核对用户 DSH 网页 provider `zai-coding-cn` 及默认 `glm-5.3-flash`，本地模型目录列出
  `glm-5.3`／`glm-5.3-flash`／`glm-5.3-highspeed`／`glm-4.6v`，前三者支持 low。
  网页既有 pi-ai 配置不注入隔离 Team，不修改 DSH 全局设置或密钥。

GitNexus 未收录新符号，impact 返回 UNKNOWN／target not found；本次采用直接调用点检查，
不声称图覆盖。受影响入口为 Delivery、生产 roster、验收 child 及生产凭据恢复。
未修改 backend/frontend，无产品服务重启。保留工作区此前无关未提交变更。

## 对比合同与原件

基线 `minimal-chain-20261019-token-opt-c-r1`；本组
`minimal-chain-20261019-dsh-glm-low-r1`，使用同一最小安装链源与 Task、同语义 Profile 的
DSH 版本、新项目新 scope。独立验收保持原公开1题／隐藏3题完整分母；本人工场景为
非盲回归，生产不接收私有答案或旧模型。Host 仅按既有职责逐点私审 CQ，不代写模型。

工程准备耗时与真实 semantic-start 至完整独立验收墙钟分开。对比全部绑定角色用量，
缓存是输入子集，推理是输出子集，缺失值及账单保持 unknown。不同协议、运行时及窗口
是实际差异，单次样本不做因果或完整费用结论。新增兼容成本单列，不隐藏到运行收益。

私有原件：`workspaces/minimal-chain-20261019-dsh-glm-low/`；保留授权、工程各轮日志、
上游探测摘要、Codex 基线数值、配置和真实运行证据。默认按一次任务的三轮上限管理，
fresh-start 与实质修模分开；成功后不为耗尽额度追加建模。当前任务未另发用户 stop，
正常完成按原合同保留只读 standby。

## 验证进度

新覆盖先红；GLM profile／原生 Delivery／生产隔离三项通过；当前 Consumer/Judge 两路
共20项通过。初轮曾发现验收 child 的 provider 检查依赖生产 run 属性，已收窄为传入
当前真实 binding；原失败日志保留。目录新增路由的原封闭集合断言已更新。
全量 Team 回归及真实运行结果随后追加；工程通过不代替真实 L0 或独立语义 L1。

当前最终专项验证：`test_dsh_glm`＋`test_messages_provider_proxy`共21通过；
`test_dsh_acceptance`两provider共20通过；`test_model_routing`77通过。
广泛Team套件按本次有界目标中止于612通过／2跳过／62项子测试，明确不是全量PASS；
另外生产／Delivery控制的相关回归保留完整日志，不与有交叉的轮次相加。
未运行backend/frontend套件，因为本次没有修改其代码。

## 真实结果与最终对比

**结论：本最小链独立非盲L1为4/4 PASS；DSH本轮更慢、记录输入更多，未证明降耗或费用下降。**
同一scenario和Task，除runtime／profile_id外Team Profile逐项相同；两轮冻结四题的题目、
必答点、未知、证据引用、可见性及内容版本规范化后完全相同。新旧代码差异仅本次兼容。

| 指标 | 最近Codex C组 | 本次DSH GLM low | 本次变化 |
| --- | ---: | ---: | ---: |
| 初建轮次／fresh starts | 1／1 | 1／1 | 无实质修模 |
| 独立非盲回归 | 公开1/1＋隐藏3/3 | 公开1/1＋隐藏3/3 | 同完整四题 |
| semantic-start至完整验收回交 | 10.86分钟 | 14.19分钟 | +30.60% |
| Delivery原生记录输入token | 6,919,702 | 21,418,062 | +209.52%（3.10倍） |
| 全链原生记录输入token | 9,930,615 | 24,586,921 | +147.59%（2.48倍） |
| 全链记录未缓存输入token | 430,007 | 787,881 | +83.23% |
| 全链记录输出token | 38,057 | 62,959 | +65.43% |

全链包含Delivery、Coordinator、Modeling、CQ、四个独立Consumer和两个独立Judge，
缓存／推理不重复相加。完整逐角色数值、原件摘要、截止点、模型身份及限制见
[数值证据](../evidence/2026-10-19-dsh-glm-low-comparison.json)。DSH原生190个数值响应，
与190个Provider响应计数对应，无重复事件冲突。输入按原生totalTokens-outputTokens
记录，未缓存／缓存读取也单列。**这不是完整供应商账单对账**：GLM把input/cache-read放在
流尾message_delta，原DeepSeek严格采集器将该位置标无效；固定DSH原生translator实际读取
流尾并保留数值。cache-write／reasoning字段缺失仍unknown，不填零、不伪称原代理完整。
本次没有为修补计量或提升对比结果再开模型任务；R4.3-019／034计量完整性仍PARTIAL。

当前外层Host为gpt-6.1-sol，与原C组glm-5.3-flash low Host不同。数值截止点已另外披露
兼容准备输入9,050,507、监督／对比输入16,352,288，总输入25,402,795、未缓存449,451；
当前响应、后续记录及最终答复尾部未计入。不能把Host或一次性开发成本隐藏到运行收益，
也不能把模型／Host／协议／窗口／故障路径不同的单样本差额归因于DSH本身。

### 实际阶段与阻塞处理

- 01:07:58.459970Z发生semantic-start，初建1轮；01:11:14.630050Z冻结完整四题。
- 两批application于01:11:21、01:11:35成功，revision0→1→2；治理读回、association
  和资源封口完成。没有apply重放、不确定写入或新的实质修模。
- CQ四次错误handoff资料读取最终自行纠正；没有Host手工搬运地图或代写业务模型。
- Modeling在真实新公开投影仍排队时三次终态拒绝，随后issue-1。Host重放连续seq0..190，
  核清九条输入全部settled、空inbox、无gap/conflict。T0复核保留保护实际未消费输入的守卫，
  没有删除校验或修平台代码。Coordinator误以为队友报告无需bound pause；Host技术补位
  使其经现有delivery_guidance完成pause，宿主guidance接受后原session恢复，随后终态接受。
  原Host consult在非只读阶段被正确拒绝，记录该操作入口错误，不掩盖为平台缺陷。
- issue_resolution于01:17:31.058973Z被接受，01:17:47.984549Z实际recovery-effective；
  01:18:24.417750Z正式production handoff接受，无pending／unknown写入。
- 公开及隐藏独立验收均为runtime=dsh、glm-messages／glm-5.3-flash／low；实际有效绑定
  及隔离工具有原件。两报告同freeze和model binding，未执行题、模型漂移、证据重验漂移为空。
- 01:22:09.673977Z接受complete_cq_acceptance（cq_verdict=pass）；
  01:22:44.416115Z接受standby。原模型、Team、Delivery及验收owner保留只读待命。
  此后未追加建模；1/3已用、2轮未用，不恢复旧关闭组的任何额度。

Host介入包含正常两次CQ私审及额外技术排队／issue握手补位，因此不称DSH完全自主交付PASS。
Delivery将这次无代码的技术guidance描述为“宿主平台修复”不准确，以Host原件为准。
原状态派生仍列历史issue_wait／cq_acceptance_closure；以实际accepted验收及standby回执
区分当前完成事实和历史首次阻塞，未改原事件去伪造干净终态。

为防止再次误读既有issue合同，收口时仅补充minimal-chain-coordinator权威提示：队友的issue
同样必须先bound pause，即使语义写入已经完成。配置validate通过；这是instruction-only纠正，
未重载本run冻结提示，未以本次结果声称新提示效果通过，也未启动新semantic start。
计量和重复唤醒后续优化没有在本任务扩展实现。

最终工程相关长回归为149通过、1项旧封闭目录断言失败；只修正新增路由对应断言后，
该模块77项全部通过（源码未再改），与前述21／20专项有交叉，不相加冒充一次全量。
最终相关链接、JSON、配置validate及git diff格式检查通过；没有backend/frontend变更或重启。
