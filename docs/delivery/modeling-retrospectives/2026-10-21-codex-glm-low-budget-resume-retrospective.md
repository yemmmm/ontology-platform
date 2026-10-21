# Codex GLM low 金额接续未取得完整验收的原因

结论：模型生产及交接已经完成，未成功的是完整自主交付及独立语义验收。
最终四题都在验收运行时被终止，没有有效答案报告或Judge裁决，不能归为模型质量失败。
直接终止原因已定位到预算控制与验收turn身份守卫冲突；交接延迟和高消耗另有旧观察队列、
恢复状态投影及过早冻结问题。单纯追加额度不能修复这些缺陷。

分析范围为`minimal-chain-20261021-codex-glm-3cny-012852-r1`的首次3元及追加3元同run接续，
不重算首批费用、不启动模型或重新验收。实际生产、Delivery和Consumer均为
Codex／glm-5.3-flash／low，初建1轮、fresh semantic-start 1次，无实质修模。
生产基线`5320e6d`；下述三个运行时责任文件与该基线无差异，没有把当前修复当作原进程已生效。
完整运行及用量边界见[原记录](../records/2026-10-21-codex-glm-low-3cny-modeling-test.md)。

## 关联需求与旧优化验证

| 需求／原优化 | 本轮证据与验证结论 |
| --- | --- |
| R4.4-002 | 金额追加、同账接续、准入关闭及暂停指令真实发生；部分验证，F8的验收安全接续出现明确反例，整体接续目标未通过。未审计原费用或认定暂估为账单。 |
| R4.3-030／022 | 有界观察与yield已使用，但恢复后继续逐条投递旧快照，Delivery已知27.112M／托管链35.362M；10M目标未通过，原优化保持待调整。 |
| R4.3-029 | Delivery发起技术定位，Host完成私有结果；最新结果未进入原生输入，仍需Host补位冻结／交接。自主职责闭环仍部分验证。 |
| R4.3-026 | revision2两批应用、治理读回及生产交接完成；完整公开1／隐藏3已冻结，L1仅runtime-incomplete，没有质量裁决，整体PARTIAL。历史其他组的独立PASS不撤销。 |

不新增“已确认优化”编号；新修复建议尚未实施，不能按本次分析关闭任何真实语义验收项。

## 1. 预算恢复后再次暂停，合法turn被验收指标守卫拒绝

**已定位，直接终止原因；实现责任属于platform-contract，原报告记录runtime/infrastructure。**

四个Consumer均已实际调用`query_semantic_context`，公开Consumer另完成两次
`get_entity_statement_context`。因此报告中的`executed_question_ids=[]`是没有完成可验收报告，
不是没有启动或完全没有读取。最终报告的阻塞证据均指向原turn_id，且没有答案或Judge裁决。

以公开线程为例（以下均UTC）：

1. 03:00:55首次turn开始，03:01:11—21完成三次治理读取。
2. 03:01:22预算epoch7暂停送达，03:01:30获得实际确认。
3. 03:05:54预算epoch8恢复，原thread内实际开始新turn；不是新Consumer线程。
4. 03:05:58预算epoch9再次暂停，03:06:04线程因runtime-metrics退出。

[EvaluationOwner](../../../modeling_team/evaluation_owner.py)在派发控制前用一个
`_pending_control_turn`布尔值允许下一次turn变化；若这次派发返回`steer`，又把它清为false
（297—310行）。恢复开启新turn后，若首条usage尚未到达就再次steer暂停，这次清除也会
抹掉前次恢复的许可。[ExaminerRunMetrics](../../../modeling_team/acceptance_runtime.py)
随后在1135—1146行把同线程合法新turn当作未授权变化。输出泵捕获此异常即终止子进程，
见[Codex输出泵](../../../modeling_team/runtimes/codex.py)的1108—1116行。

本次使用保留的真实thread／turn身份作**离线构造时序复现**：单次恢复接受新turn；
恢复后、首条usage之前模拟第二次steer清除许可，得到与原报告相同的
`ExaminerBlocked/v1`／`runtime-metrics`／原turn_id。未向真实线程发消息或消耗额度。
这是状态机缺陷复现，不冒称原始RPC全量回放；原始记录未保留每次dispatch mode，
真实start活动、控制回执、旧turn阻塞证据和源码路径共同支持上述因果。

`model_context_window=0`不是该阻塞的原因：缺字段已被归零；本次拒绝发生在字段归一化之前。
`metrics_complete=false`、`terminal_report=false`是未正常收口的结果，不能直接反推模型能力。

## 2. Delivery恢复后逐条消费旧观察，最新处理结果被积压

**已定位，交付延迟及输入放大原因；platform-contract，实现责任属于Delivery输入队列。**

恢复后原生会话收到35条`host_observation`，其原始packet预算epoch分布为
0／1／2／3分别20／8／2／5条，全部早于追加额度后的epoch4。
例如02:45:36投递的`d8106070b51e47f59dbbc8ba49d6e942`来自session journal第223行的旧快照；
02:51:09仍在投递第344行的旧packet。不是每次yield都对应新的当前阻塞。

Host在02:51提交的issue处理结果已进入journal第2568行的
`e0be8dc989d94890ab16e39a3725550b`决策packet，但原生会话没有收到该input_id。
本次原生会话截止与原用量报告一致，未使用后来更新替换历史证据。

[Delivery恢复](../../../modeling_team/delivery.py)保留所有未确认输入；bootstrap后
`_model_observation`继续取`_pending_decisions[0]`（3404—3406行），没有将最新恢复状态
已涵盖的历史观察合并。旧状态在恢复后逐条驱动推理，最新Host结果排在队尾。

本次恢复后39次`yield_delivery`，其中37次成功登记、2次因等待已拒绝请求获得准确反馈。
累计Delivery输入＋输出27,112,360，占托管链已知35,361,622的76.67%；Host只展示、不计金额成本。
这些数字支持输入放大及目标未达，不证明39次全部可删除，也不量化保证能节省多少费用。

## 3. Provider恢复已结清issue，Host投影仍把它列为待解决

**已定位，额外技术返工原因；platform-contract，实现责任属于恢复证据与状态投影。**

[Runner._settle_provider_wait_issue](../../../modeling_team/runner.py)直接推进原issue ledger、
保存resolution并`mark_dispatch`，避免重复启动恢复turn，但没有写出Host投影识别的终态
`issue-control`事件。[Host待办派生](../../../modeling_team/host_ops.py)依据持久报告和终态
control事件判定，因而继续显示旧issue_wait。

Delivery两次resolve_issue以及Host一次完整格式重试均被拒绝；
[前台准入](../../../modeling_team/__main__.py)在解析前先检查实际ledger状态，已结清issue
不处于waiting_owner／waiting_repair，统一返回`invalid_outer_input`，没有说明“已经结清”。
Host最初猜测缺少字段不准确，完整格式仍拒绝后已纠正；这段误诊也增加了返工。

原Runner随后真实接受完整冻结与生产交接，readiness确认无未结／未知写入，进一步证实
旧待办不代表活跃写入阻塞。已保留失败回执，没有回写旧事件或重放两批成功应用。

## 4. 全景审核被过早当作整池完成

**已定位，prompt-contract／阶段决策缺陷；不是最终四线程退出的直接原因。**

01:31的Host结果明确`selected_scope_complete=false`、仍有切片阶段，Delivery仍冻结
公开1／隐藏0的batch-0001。实际原生Delivery指令已经包含“单次review完成不代表整池完成”
及完整冻结的要求，不能归为缺少这项能力或未提供规则。
切片审核完成后仍未自主更新冻结；最终Host补位发布batch-0002，公开1／隐藏3，旧冻结保留。
本项已技术补位但自主采用未通过；后续应结合第2项修正当前状态消费，不堆叠同义长提示。

## 5. 检索存在真实评分超时降级

**部分定位到评分边界，独立于上述终止机制。**

生产平台响应`evidence/platform-responses/e6c7d325…-be998942….json`记录
`context_page.ranking.reason=timeout`及关联扩展`scoring_unavailable`，同时已有部分评分结果。
不能宣称所有检索完整，也不能用它解释四个Consumer相同turn守卫错误。
未调用新的评分服务；服务内部耗时原因及对必答点的实际影响尚未获得决定性证据，
须在运行时接续修复后沿原冻结题集独立重验，保留降级／分页信息后再定位质量影响。

## 最小纠正顺序与T0复核

1. **先修验收合法接续。** 同一已绑定thread中的合法控制turn不应终止验收。
   T0：防止混线程／伪造证据的真实不变量仍需保护；单纯turn变化本可恢复；删除或降级
   此重复硬门后，原thread隔离、单一owner、累计用量、预算准入、冻结／报告绑定仍保护实际结果。
   优先收窄或降级此拒绝，不通过增加次数限制或放宽语义评分解决。
2. **再修恢复输入积压与issue收敛。** 最新恢复状态先交付，已涵盖的旧观察合并而原件及
   正式动作回执保留；provider恢复结果应让Host投影识别实际结清，已结清请求返回准确反馈。
   不把旧issue再解决一遍，不增加第二套流程守卫。
3. **沿完整原题池重验。** 先用有界离线控制时序、恢复队列与投影合同验证修复；实际重验
   沿原revision2／完整freeze及公开1＋隐藏3，不重建模型、不减少题目、不改评分。
   新的模型调用仍需金额授权，本次分析不恢复预算，也未实施以上建议。

本次只读核对原件、检查源码及执行无模型的构造时序诊断，并更新分析／验证记录。
GitNexus返回的类位置与当前源码不一致且缺少控制方法，未据此声称完整图覆盖；
使用实际源码、调用点和启动基线diff确认责任面。没有修改平台源码、重启服务或执行真实重验。

原始证据导航：同run `acceptance-v3/public-regression/cq-batch-0002/attempt-0001/batch-report.json`、
`acceptance-v3/reports/cq-batch-0002/attempt-0001/batch-report.json`；
`.delivery-ops/*host-add3-independent-*.owner/evidence/agent-statistics/*/evidence/close-statistics-capture/`
的activity／usage；原预算events第2938—2983、3100—3153行；原Delivery journal与native rollout。
这些原件留在既有本机私有目录，报告不包含隐藏题正文、答案或评分细节。

后续用户授权“修复已定位问题”，上述控制turn、观察积压、恢复投影和阶段反馈的窄修
已实施，验证范围见[工程修复记录](../records/2026-10-21-modeling-resume-repair.md)。
此进展不改写本报告原始诊断时点、旧进程身份或L1未完成结论；评分服务内部原因仍未确定。
