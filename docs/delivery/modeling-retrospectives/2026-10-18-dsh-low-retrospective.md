# 2026-10-18 DSH low 最小链建模复盘

结论：有宿主补位的最小链独立非盲回归通过；DSH Delivery自主完整交付和净降耗均未成立。
优先解决DSH原生事件仍进入决策唤醒、Delivery HTTP400缺少可定位原因、文件交接依赖宿主
手工转存三项。没有证据要求重做本轮已通过的业务模型，也不新增运行授权或验收门。

## 范围与原结果

- 会话`minimal-chain-20261018-dsh-low`，R4.3-026最小安装链，角色配置均为
  `deepseek-flash/low`；生产、CQ、Consumer、Judge实际DSH绑定可核对。
- 固定Harness `687f282e8625c6b8d11ff58211a90524be2e4317`。初始代码`231bef4`，
  启动窄修`63206b9`，队列反馈及提示修正`d9bb5a5`；后者进入第二轮。
- `r1/r2`在semantic-start前失败，不扣轮；`r3`首轮已应用但未形成正式生产交接，
  未执行独立语义验收；`r4`第二轮重新生产并完成验收。共2/3轮、2次fresh semantic-start；
  不是在首次验收REVISE后修模，剩余1轮在任务关闭时收回。
- 原授权13:34:32，首个真实start 13:49:17，14分45秒，符合20分钟边界；第二轮
  14:07:03，Runner接纳验收14:15:24，最终关闭14:18:08，授权至关闭43分36秒。
  全部为2026-10-18 UTC+8。有效语义／技术工时未可靠分类，保持unknown。
- 最终公开1/1、隐藏3/3，均`full_pass=true`，无未执行题、实际coverage gap或模型漂移，
  同源freeze与model binding一致。复盘核对两份报告字节SHA256与原收尾清单一致，
  逐题裁决元数据均pass；未重跑Consumer／Judge，不作为新的独立裁决。
- 报告明确`non-blind-regression`。不扩称盲测、大场景、L2或全自主交付。
  原Runner已CLEANED、登记的角色／owner进程退出，临时key撤销证据保留；模型和失败现场保留。

主要原件入口为[授权与轮次](../../../workspaces/minimal-chain-20261018-dsh-low/authorization.json)、
[报告核对](../../../workspaces/minimal-chain-20261018-dsh-low/final-report-verification.json)、
[进程与运行时](../../../workspaces/minimal-chain-20261018-dsh-low/final-process-runtime-verification.json)、
[临时key收尾](../../../workspaces/minimal-chain-20261018-dsh-low/final-key-verification.json)和
[原任务修复／终局记录](../records/2026-10-18-dsh-modeling-startup-repair.md)。
这些gitignored原件仅为宿主证据，不整体交给生产角色。

## 关联需求验证与旧优化

权威需求见[v4.3](../../requirements/requirements-v4.3.md)，本次结论同时追加在其末尾；
历史工程PASS与旧语义失败均保留，不由本轮全局覆盖。

| 需求 | 实际证据 | 本次验证结论／缺口 |
| --- | --- | --- |
| 031 | 两轮实际装载、直接提交、治理自查；r4正常终态与清理 | 部分验证；A4本次有界真实运行通过，消息终态修正实测成立；所有异常控制／恢复场景未覆盖 |
| 032 | Delivery实际Host工具调用；原session恢复后仍HTTP400，后半程Host接管 | 验证未通过：本轮A5自主完整交付未达到；保留工程证据，A4仅证明恢复进入原session，未证明恢复业务成功 |
| 033 | 两个独立验收组，四个Consumer及两个Judge，实际治理读取、完整分母、无漂移 | 部分验证；A6本次最小链独立非盲L1通过；早期反馈、checkpoint接续及其他异常场景未实测 |
| 034／019 | 已收集原Delivery／恢复、两轮生产及六验收session的数值 | 部分验证；034 A5本次有界application／L1成立，A4自主完整切换未完成；计量及费用仍partial，默认不切换 |
| 030／022 | v2已进入Delivery，但DSH原生事件未被识别为例行事件，102次自动观察输入 | 部分验证；本次DSH事件降噪未达到F2预期，同条件完整降耗A5未验证；不能称已降耗 |
| 024／025／023 | r4两Class＋一个relation_type，无业务行实例，原子应用到revision2 | 本轮表示／方向／未知的有界语义正证据保留；不关闭其他历史范围缺口 |
| 026／028／015 | 最小链四题通过；新建空模型，未触发已有模型增量或生产终态前公开反馈 | 026追加有界通过；028增量效果、015早期反馈未验证，不以未触发判失败 |
| 029／016 | Delivery提出Host action，宿主诊断／修复／CQ审核／接管 | 交接局部采用成立；整体自主交付及宿主成本转移未闭合 |

优化台账031—034旧的“已确认待处理”是未同步的登记状态：四项均已有工程实现及测试。
本次追加最新状态，不新登记未经用户确认的优化，也不把新增建议直接视为实施授权。
021继续暂缓；此次没有建议重做压缩框架。

## 仍需解决的问题（按优先级）

### P1：DSH例行原生事件持续触发Delivery输入

**已定位，platform-contract，责任面030／032及Delivery输入投影。**
`delivery.py::_is_decision_event_noise`识别`app-server-events.jsonl`与
`provider-attempts.jsonl`，没有DSH对应分支；`host_ops.get_run_events`枚举所有证据JSONL。
因此DSH chunk／数值原件进入变化链，`_decision_event_metadata`又把嵌套frame压成原件引用，
并未提炼真正的活动结束、失败、未消费输入等状态。

原生Delivery session共保留102条`host_observation`输入，其中46条的事件引用出现项
全部来自DSH来源；这只是引用统计，不能将这46条全部认定为无业务价值。
已知Delivery输入27,375,070，占整批已知输入44,785,643的61.13%；输出38,937。
逐请求完整provider用量有92条，单次输入从25,726增长至785,788；离线报告另按自身
去重／替代规则给出93个已知计量单元，不能把计量单元当turn数。

**最小建议**：沿既有投影识别DSH例行stream／数值记录，保留原件，按真实状态变化唤醒；
失败、队列缺口、unknown、用户控制及必要完成事件仍需可见。不能整体屏蔽`dsh-*`。
先以现有事件／decision-input测试验证不漏异常，再在获准同条件最小链比较完整窗口
Delivery input及T_D、质量与宿主成本。可减少不必要往返／累计上下文，但无法据此估算降幅。

### P2：Delivery HTTP400原因被代理抹平，原session恢复无效

**部分定位，runtime/infrastructure首层；具体拒绝原因尚不明。**
`native/dsh-provider.jsonl`第281／284行分别记录05:53:16Z与05:54:22Z的400，
后者是同一原生session的显式恢复。`dsh-wire.jsonl`第943／981行均为INVALID_REQUEST，
有真实provider HTTP证据，不是工具参数本地校验失败。

`messages_provider_proxy.py::_MessagesHandler.do_POST`在status>=400时直接生成
`DeepSeek HTTP 400`，未读取并保留上游具体错误；Node通知进一步只传code／status。
所以当前原件不足以区分窗口、请求尺寸、历史结构或参数拒绝。原session恢复仍带同一
历史，不解决请求缺陷；也不能把400推成模型业务质量失败。
失败前输入已785,788，本机实际输出预留256,000，容量／压缩值得核对，
但没有被拒请求结构／上游原因，**不能断言上下文超限**。

**最小建议**：只在失败边界保留有界、脱敏、类型化的上游原因及请求结构／容量元数据，
对照原生恢复链定位；无需保存整份提示或敏感错误正文，不增加通用日志平台或盲目重试。
验证400首因可见且不泄露凭据、错误恢复仍受原授权；具体修复后再证明原路径可完成。

### P3：场景地图与动态公开CQ依赖宿主手工搬运

**已定位，platform-contract与prompt-contract，责任面031／032。**
DSH只提供冻结`role-materials`读取与`write_handoff_output`，没有原Coordinator动态文件
挂载的直接操作能力；原提示仍假定能维护Runner场景地图、读取动态公开投影。
`d9bb5a5`已明确使用handoff输出和Host公开消息，r4确实走通，但仍由外层逐次转存。
`round2-final-map-transfer.json`保留源／目标摘要，明确`semantic_edit=false`。

首轮`scope_binding_required`是未取得已确认范围／拓扑时的正确可恢复拒绝，不建议删门。
宿主原字节转存后原请求成功，说明缺口在原件到门的接线，不在重写业务模型。

**最小建议**：复用既有发布／Host工具链，在明确来源／目标下完成Coordinator原字节转存，
动态公开CQ及freeze事实沿现有输入准入到达，不依赖外层手工复制。不新建文件系统泛权工具，
不让Delivery代写语义。验证实际可读、摘要一致、公开边界、地图及时同步，且无需宿主代操作。
手工转存本轮有效且保留；是否程序化需用户确认实施，不能将其伪称零宿主成本。

### P4：工具输出JSON错误被套成额度／余额／停机恢复

**已定位，runtime/infrastructure及prompt-contract，责任面031和Runner错误展示。**
首轮`dsh-wire.jsonl`第160行真实失败为
`DeepSeek Messages stream: tool input is invalid JSON / MALFORMED_RESPONSE`，
发生在首次提交工具参数尚未构造成功时；无该次写入证据。
`issue-report.jsonl`第1行却提示external quota/balance/outage recovery needed。
DSH Adapter把provider错误都进入wait，Runner `_report_provider_wait_issue`统一套该文案；
底层流／序列化问题的根因不能定位到供应商内部，但误导性恢复文案已定位。

**最小建议**：保留原错误类型及安全定位，不把所有错误描述为额度故障；对明确未派发
工具的坏JSON返回同目标可纠正反馈，在途／未知写入仍先核对。先用现有fixture验证，
不要为一个坏JSON新增永久终止门、自动生产重启或无界重试。原轮Host恢复后继续成功，
并不证明这一分类问题已修。

### P5：整任务成本与自主效果证据仍有缺口

**已定位的证据缺口，责任面019／034；不是模型质量缺陷。**
[原离线报告](../../../workspaces/minimal-chain-20261018-dsh-low/usage-report/report.md)
已知输入44,785,643、缓存43,560,960、未缓存1,224,683、输出279,556，缓存率97.27%。
Host监督／修复／审核／收尾及外部scoring数字缺失，部分失败／中断请求用量缺字段，
scope截止06:17:37Z，早于最终关闭06:18:08Z；usage／attribution／timing均partial，账单未提供。
更高缓存率不足以判净降耗；前一轮Codex DeepSeek为high、本轮low且含失败重启与接管，
不能作同条件纯运行时对照。

**最小建议**：先沿现有scope补可取得的Host／辅助／末段数值，取不到就保留unknown；
修好自主链后再做原四题同配置有界对照。分别判断Delivery input／T_D、全任务成本、
墙钟、人工介入及费用；不以新监控平台或账单等待阻挡安全建模。

## 已修复、正常等待与尚不能归责项

| 现象／证据 | 定位与本轮结果 | 后续边界 |
| --- | --- | --- |
| r1/r2缺Coordinator socket、部分初始化cleanup KeyError | 63206b9按实际角色装载并容忍未初始化成员；r3/r4实际启动及清理 | 启动窄修已生效，不重复立项或增加启动全审计 |
| r3终态报Protocol检索不完整，Modeling记录至少5次重试 | bool终态guard被Broker套成Protocol旧报错；实际上是未消费DSH消息；d9bb5a5改为runtime_input_pending并补自然结束活动说明 | r4 Coordinator 06:10:44Z收到准确反馈，结束活动消费终态handoff，06:10:49Z报告被接纳；修正实测成立，保留unknown输入保护 |
| r3 Coordinator先报blocked，之后dsh-dispatch-closed | 终态已锁定后仍需新派发，无法正式handoff；不属于业务模型不合格 | r4没有重演；未证明终态错误后的同run恢复，不能宣称所有恢复完成 |
| issue-2 resolution三次被拒 | resolution早于05:51:47Z实际pause；末次原工具提交后可结算，Host原诊断记录保留 | 正常顺序约束，不能从reject次数推导schema缺陷或删除必要控制 |
| vector_index_missing／derived_state_stale | r4交付原件披露；空模型发现使用词法／混合与权威读模型；写入成功与读回／四题验收成立 | 非本轮业务阻塞；向量不可用根因和派生状态时效未定位，不建议全面修复。涉及已有模型语义发现时，最小下一步核对原响应对应索引／revision，而非将no_match当不存在 |

上述平台警告只限制相关能力结论；本复盘未重建索引、重启服务或新执行模型读取。
未查到足以归因向量警告的生产源码字面分支，不能从交付摘要补造根因。

## 下一步与记录边界

建议先完成P1降噪和P2错误可定位性，再补P3现有交接接线；P4窄修可独立进行。
P5使用现有计量继续补证，不先建设新框架。后续获准运行首先核对无外层代操作时
DSH Delivery能否推进完整四题及stop；工程、最小链L1、全自主、降耗和费用分别报告。
当前授权已关闭，本次只读分析原件并更新复盘／需求验证／台账，未实施建议、未启动
或恢复任何模型／验收，没有新增优化确认项。
