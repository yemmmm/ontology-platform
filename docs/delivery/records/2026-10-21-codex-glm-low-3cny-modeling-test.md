# Codex GLM low：3元最小链建模测试

以下首批3元结论保留原统计时点；后续追加3元并恢复同一run的结果见文末“追加3元接续”。

本轮结论为 **PARTIAL**。实际完成两批原子应用，模型 revision2，已保留受治理读回；
完整题池冻结、生产交接和独立公开／隐藏验收尚未完成。金额门已关闭，原 run 和模型保留。
本记录不将预算暂停、HTTP402或流程缺陷归因为模型质量失败，也不宣称自主交付通过。

用户原话：“启动一轮建模测试，使用codex glm-5.3-flash low，授权3元额度”。
沿 R4.3-026 当前通用 Task/Profile、唯一 scenario.md 和新 project/scope，生产、Delivery、
CQ及拟启动的独立验收均选择 Codex／glm-5.3-flash／low，service tier为default。
采用 R4.4-002 金额模式；总授权始终3元，无追加金额。初建1轮、fresh semantic-start
1次，无实质语义修模，不套默认三轮资源门。外层Host不计入该金额预算。

运行身份及证据：

- Host目录／session：`minimal-chain-20261021-codex-glm-3cny-012852`。
- run：`minimal-chain-20261021-codex-glm-3cny-012852-r1`。
- 启动代码：`5320e6dfa030e823b5bcad4ad9133bbc0f66bca1`。
- project：`6e9b9695-25e7-4601-b020-e2a40738b95c`；ontology：
  `b49c9195-4220-4be6-9cd7-e21ce7c1b107`。
- 金额授权、配置、预算、原始回执与只读核查保存在
  [Host目录](../../../workspaces/minimal-chain-20261021-codex-glm-3cny-012852/)。

## 实际成果和流程缺口

semantic-start为2026-10-21 **01:29:22.884990 UTC**（09:29:22新加坡时间），
距本次Host授权登记约30秒。初始Task/model-profile配置校验通过，实际生成的Delivery及
三个生产角色配置均核实为glm-direct／glm-5.3-flash／low，不以加载配置代替语义通过。

Host于01:31:07完成全景题私有审核，明确`selected_scope_complete=false`，剩余阶段为
切片草案及审核。Delivery仍于01:31:47发布只含全景公开题的`cq-batch-0001`，隐藏题为0。
这是prompt-contract／阶段推进缺陷；权威Delivery Skill原已有“单次审核完成不等于整池完成”
要求，本次没有用新增平台硬门修补它。

周期卡片与实际阶段不一致后，Host核对正式回执，沿原`cq_interview`提交窄流程纠正，取得
accepted回执；没有补充业务定义或泄露隐藏题给生产。切片三题正式审核于01:37:16提交，
Host结果声明整池已审，但截至收口，仍只有旧全景冻结，没有新的完整冻结。因此已审题目
不能冒充已完整冻结的公开1／隐藏3验收池。本次需要Host流程补位，自主交付不成立。

平台实际应用：

| 完成时间 UTC | 内容 | 结果 |
| --- | --- | --- |
| 01:37:25.190582 | 两个概念Class | applied |
| 01:38:46.001241 | 安装资产→现场的安装位置relation_type | applied |

两批application回执、实际数据库两批`applied`及model revision2一致，没有未结算Batch。
受治理上下文原件已返回两个概念和安装关系；其中关联扩展出现`scoring_unavailable`／
`timeout`降级，不能称检索完整或独立语义PASS。卡片更新滞后，曾不足以显示实际成功写入；
最终结论以上述原件和实际资源核对为准。
Consumer／Judge尚未启动，生产交接、完整关联自查与独立全分母验收均未完成。
L0 Runtime为PARTIAL，L1独立验收为NOT_RUN；未验证L2／L3或实际阶段换线程降耗。

## 金额暂停与现场

冻结自定义单价为缓存输入／未缓存输入／输出每百万token **0.02／1／4元**。
01:38:53首次累计估算3.15326216元触发预算暂停；迟到原生数值使估算降至2.71262108元。
Host沿原授权执行一次`continue_authorized`，金额仍3元、同run同目标；没有增加预算或start。
01:42:12再次触发暂停，随后生产及Delivery原生回合出现HTTP402／失败终止，未再授权新的消耗动作。

收口快照：已定价数值估算 **0.81117928元**，暂估 **2.265782元**，合计
**3.07696128元**，余额 **-0.07696128元**。暂估不是确定上界，全部数值不是供应商账单。
Host及未接线检索评分成本未从3元预算扣除。

金额admission已关闭；状态仍`PAUSE_PENDING`，Delivery逻辑owner有effective回执，
其余执行方多为instruction_delivered，不能写成全员有效暂停。原生最新活动显示生产及
Delivery回合均已结束；投影仍列2项inflight，保留该观察差异，不手工改写控制状态。
原Runner／角色进程、项目、模型和临时凭据按现有暂停现场保留，未获显式stop，未宣称清理。
恢复消耗需要新金额授权，并沿同一budget_ref接续，不清零历史。

## 用量与检查边界

截至 **2026-10-21 09:48:09 +08:00** 的离线原件统计如下，输入含缓存，输出含已归入的推理。

| 角色 | 输入 | 输出 | 输入＋输出 |
| --- | ---: | ---: | ---: |
| Delivery | 4,908,779 | 15,213 | 4,923,992 |
| Coordinator | 2,755,252 | 11,205 | 2,766,457 |
| Modeling | 1,863,710 | 8,776 | 1,872,486 |
| CQ | 274,613 | 3,172 | 277,785 |
| 托管链已知小计 | 9,802,354 | 38,366 | 9,840,720 |
| 外层Codex Host | 8,808,245 | 25,123 | 8,833,368 |
| 全任务已知小计 | 18,610,599 | 63,489 | 18,674,088 |

Consumer／Judge未调用；检索评分用量未知，截止点之后的Host整理未纳入，不编造全任务完整总数。
外层Host原生请求模型为gpt-6.1-sol，与用户为建模团队选定的GLM配置分开统计。
完整任务10M目标本轮未达到；高缓存率不改变该结论。原件、冻结字节范围和限制见
[离线报告](../../../workspaces/minimal-chain-20261021-codex-glm-3cny-012852/usage-report/report.md)。
有效语义、等待和Host处理时间未完整归集，不能给出有效语义占比；未扩展平台或harness。

本轮执行配置校验、真实启动、正常私有CQ审核、原run流程纠正、实际application和资源只读核对，
以及现有usage_report离线统计。未修改应用或Team源码，无须服务重启或后端／前端回归。
原有dirty文档和其他未跟踪文件保持。后续需先恢复完整题池及原生产流程，再进行独立验收；
本记录本身不追加金额、不授权新运行，也不修补或覆盖历史冻结和失败原件。

## 追加3元接续

用户原话：“再授权3元额度，恢复刚才暂停运行，上一轮授权已消耗额度本轮不细究”。
Host于2026-10-21 02:41 UTC沿原budget_ref追加3元、累计授权6元，保留旧账，不重新核算
首批消耗。沿同一run、原三个生产线程、原模型和glm-5.3-flash／low继续，未创建新的
production semantic-start或实质修模轮；累计仍为初建1轮、fresh start1次。

本次结果仍为 **PARTIAL；独立L1验收BLOCKED（runtime/infrastructure）**，不判模型质量失败。

- 原Modeling完成治理读回、完整关联扫描和build session收口；原Coordinator接受最终生产
  报告并同步场景地图／自查记录。实际模型保持revision2，两批均applied，未重放成功写入。
- 恢复provider wait已在原Runner内存账本处理issue-1，但Host文件待办仍显示旧issue_wait。
  Delivery重复提交resolve_issue被前台以invalid_outer_input拒绝，并等待已完成的Host结果。
  Host最初把拒绝归为短格式字段问题不准确；完整格式也被拒绝后，核对到前台在解析前检查
  issue状态，实际恢复路径已结清问题。该纠正及全部失败回执均保留，没有改旧事件或伪造修复。
- Host沿既有入口补位冻结完整题池：02:55:29 UTC，`cq-batch-0002`，公开1／隐藏3，
  原`cq-batch-0001`不覆盖。02:56:45生产交接获得真实accepted回执：ready=true、
  pending_writes=false、unknown_writes=[]、write_phase=read-only，实际校验不受旧待办误导。
- 独立公开／隐藏验收沿同一预算启动，Consumer共4个原生线程，仍为Codex／GLM low。
  两份报告均保留原完整分母，4题均runtime-incomplete，executed_question_ids为空，
  首阻塞为`BLOCKED/runtime-metrics`，没有可供Judge裁决的答案，Judge未启动。
  验收前后无model drift；不得把无裁决的机械fail写成4题模型质量失败。
- 完整报告已通过原`complete_cq_acceptance`交回源Runner并获得accepted；源run的
  standby请求也获accepted。四个失败Consumer自行销毁并停止转发器，两次实际验收及一次
  启动前拒绝所创建的三个只读临时key均确认revoked。原生产run、Delivery和CLI owner
  保留只读／待命，未授权stop，未宣称全部进程停止或全员预算暂停确认完成。

两个失败报告分别保存在
[公开报告](../../../workspaces/modeling-runs/minimal-chain-20261021-codex-glm-3cny-012852-r1/acceptance-v3/public-regression/cq-batch-0002/attempt-0001/batch-report.json)和
[隐藏报告](../../../workspaces/modeling-runs/minimal-chain-20261021-codex-glm-3cny-012852-r1/acceptance-v3/reports/cq-batch-0002/attempt-0001/batch-report.json)。
运行原件见Host目录的`budget-add3-result.json`、`add3-host-complete-freeze.json`、
`add3-host-complete-handoff.json`、`add3-acceptance-closure.json`、`add3-standby-result.json`
及`add3-final-resource-check.json`。

累计6元预算多次因暂估触及阈值而暂停，迟到结算恢复余额后沿本次明确继续授权恢复同一任务，
没有追加第三笔金额。最终只读快照累计估算 **7.75812984元**、余额 **-1.75812984元**，
包含暂估及尾差，不是供应商账单。预算入口已关闭，pause_pending仍保留实际确认边界。
本次按用户要求不追查首批金额，不把迟到数值、暂估变化或新增授权当作清零历史的理由。

截至2026-10-21 **11:17:16 +08:00** 的累计已知token如下。包含失败Consumer和全部
生产／Delivery线程；Host只展示、不计入任务金额成本。中间修改统计策略的开发turn已从
本任务Host窗口剔除，原首次建模和本次恢复turn按真实累计基线归属。

| 角色 | 输入 | 输出 | 输入＋输出 |
| --- | ---: | ---: | ---: |
| Delivery | 27,068,860 | 43,500 | 27,112,360 |
| Coordinator | 4,271,924 | 17,340 | 4,289,264 |
| Modeling | 3,394,729 | 14,456 | 3,409,185 |
| CQ | 431,470 | 3,713 | 435,183 |
| Consumer／platform-examiner | 114,539 | 1,091 | 115,630 |
| 托管链已知小计 | 35,281,522 | 80,100 | 35,361,622 |
| 外部Host（仅展示） | 28,661,398 | 87,213 | 28,748,611 |

Judge未调用；失败传输缺数及检索评分成本仍有覆盖限制。完整任务10M目标未达到，
有效语义／等待／宿主处理时间未完整归集，不编造比例；未扩展平台或harness。
独立报告与原生用量快照对照、去重、绑定和原件长度见
[接续用量报告](../../../workspaces/minimal-chain-20261021-codex-glm-3cny-012852/usage-report-add3/report.md)。

本次只执行获准接续、必要Host流程补位、只读核查及资源收尾，没有修改平台或Team源码，
不需应用重启或重跑开发测试。尚待解决验收runtime-metrics阻塞，再沿同一模型／完整冻结
题池进行独立重验；下一次模型调用仍需新的金额授权，不由本记录自动启动。
