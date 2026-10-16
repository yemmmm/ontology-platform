# 2026-10-16 E组最小安装链复盘与阶段耗时

上一轮为`r4326-20261016-glmhigh-e-start1`，全角色使用`glm-5.3-flash/high`，
Task／Profile为`r4-3-026-minimal-installation-chain`，代码`43e0b37`。
从宿主台账登记至结果核对为**44分28.697秒**；全部四题报告齐备为**40分31.363秒**。
原用户消息时间未取得，且准备早于台账登记，因此两者均为已观察窗口，真实指令起点的
端到端耗时未知。最小链四题独立非盲语义回归通过；自主交付及生命周期未通过，整体PARTIAL。
本复盘不修改运行、冻结、裁决或授权，不启动下一轮，也不替代独立验收。

## 阶段时间

以下均为2026-10-16新加坡时间（UTC+08）。按里程碑划分互不重叠的墙钟区间，
不是逐角色有效工时；区间内可能混合推理、读取、等待、审核及技术纠错。
秒数显示四舍五入，总量按原始微秒计算，逐行显示值之和可能相差1秒。

| 阶段 | 起止 | 耗时 | 结果及边界 |
| --- | --- | ---: | --- |
| 启动准备 | 13:39:11—13:40:18 | 1分06秒 | 台账登记→首次真实semantic start |
| 资料理解、拓扑协调及CQ审核冻结 | 13:40:18—13:52:16 | 11分59秒 | 完整冻结公开1题、隐藏3题；含宿主提醒与审核参数纠错 |
| 建模与应用 | 13:52:16—13:57:26 | 5分10秒 | 两概念和一关系完成；2批应用、1批校验失败未写入；首次应用13:55:44 |
| 治理读回、自查及关闭Build Session | 13:57:26—14:02:48 | 5分22秒 | 关联检查3资源／25语句，无未解析引用；查询超时及分页补位保留 |
| 生产交接、封口与验收启动准备 | 14:02:48—14:08:10 | 5分22秒 | Modeling于14:03:58交付，Coordinator于14:06:01完成；14:07:28封口并交接 |
| 隐藏三题Consumer／Judge | 14:08:10—14:11:42 | 3分32秒 | 三题并发消费，独立裁决3/3通过 |
| 隐藏验收回传、等待与公开补验纠偏 | 14:11:42—14:18:16 | 6分33秒 | 14:14:37隐藏验收闭合；其后仍等待、提前final、停止隐藏owner，提醒后启动公开题 |
| 公开一题Consumer／Judge | 14:18:16—14:19:43 | 1分27秒 | 独立裁决1/1通过，四题全部齐备 |
| 最终事实纠正与结果核对 | 14:19:43—14:23:40 | 3分57秒 | 纠正批次成功数、非盲性质及保留偏差；已有封口保持，进入只读待命 |
| 合计 | 13:39:11—14:23:40 | **44分29秒** | 已观察窗口；没有把后续待命时间计入建模 |

补充里程碑：登记后16分32.821秒首次应用，18分14.225秒完整模型应用；
从semantic start到完整应用17分08.110秒。独立Consumer首次完成一道有效答案为
14:10:12.905，距登记31分01.437秒；它不是完整独立PASS时点。
早期`public-feedback`未执行，不与最终公开独立验收混同。

隐藏三道题任务分别于14:08:11.573、14:08:11.574、14:08:11.576开始，
14:10:12.905、14:10:32.055、14:10:29.934结束；共同重叠**121.329秒**，
Consumer阶段跨度140.484秒。Consumer全部完成到整批报告完成还有70.392秒，
包含Judge、证据复核及汇总，不能称为纯Judge推理时间。公开Consumer耗时54.429秒，
全部报告窗口87.240秒。两批验收窗口合计299.327秒（约4分59秒）；
不能把两批之间393.143秒全部称为验收计算或全部可删除等待。
无同条件串行实测对照，不计算并发提速倍数。

## 关联需求及旧优化复核

| 需求／优化 | 本次已有证据 | 验证边界及状态 |
| --- | --- | --- |
| R4.3-001／R4.0-021 | 起止、应用、冻结、消费、交接和收尾时间可追溯 | 部分验证；原用户时间、有效语义工时、故障关键路径并集未知；不是完整业务120分钟性能基线 |
| R4.3-024／025 | Modeling直接提交、两批实际应用、明确失败未写入后纠正、治理读回与关联检查、资源关闭 | 部分验证；本次概念／方向及未知表达通过独立语义回归；其他操作及净效率仍待证，保留旧失败和待实测状态 |
| R4.3-026 | 同一冻结、同一模型绑定，公开1/1和隐藏3/3；实际revision2，未造实例或安装事实 | 本次有界模型语义回归通过，整体部分验证；自主交付、原查询故障及完整成本未闭合，不替代原小链／完整业务 |
| R4.3-027 | 三题真实重叠121.329秒，乱序完成后完整三题裁决，公开单题也完成 | 部分验证；A1三题与不足三题、A2本次成功路径取得真实证据；更多题接续、单题失败／漂移反例、完整用量与同条件速度收益未验证 |
| R4.3-013／014／015及RETRO既有恢复项 | 有交接与原请求技术纠错；没有新的生产恢复或早期反馈 | 保持原状态，未触发的反例不能关闭；最终公开验收不算早期反馈 |
| R4.3-016／019／020／022 | 本次补充原件复核；仍发生多次宿主补位、遗漏完整验收与过早final | 保持待实测；完整成本／有效工时和自主交付未闭合；021继续暂缓 |

初建消耗1轮，fresh semantic-start为1；校验纠错和只读验收不另扣轮次。
该组原台账保留剩余2轮，本次复盘不新增启动或修模授权。
没有新增用户确认项，不关闭完整优化预期。

## 已识别问题与最窄定位

- **CQ审核推进及参数纠错（collaboration/routing、platform-contract）。**
  首份草稿13:41:07提交，13:48:17批准，跨度7分09秒；期间宿主提醒读取精确审核绑定，
  后续提交遗漏`review_id`被本地校验拒绝，补齐后成功。草稿到批准不是纯空闲时间。
  已定位实际动作及调用错误；为何此前重复观察与拓扑引导优先，不能仅凭摘要推断模型内部原因。
  最小建议是沿已有pending审核和真实绑定推进，无需新增审批机制。
- **关系提交使用不支持的字段（platform-contract）。** 原请求在`semantic_definition`
  中增加`exclusions`，回执`invalid_command_payload: semantic_definition contains
  unsupported fields`，定位到`items/0/payload`。没有部分写入，修正后原目标继续，
  最终业务含义与未知保留。13:56:25失败至13:57:26应用约61秒，不是新一轮实质修模。
  保留该反馈与纠错路径，当前证据不支持删除基础校验。
- **查询代理固定5秒超时（runtime/infrastructure，边界已定位）。**
  原始完成事件显示生产侧4次失败（累计20.021秒），隐藏Consumer侧另有2次失败
  （累计10.006秒）；原摘要仅记录生产4次，不能据此称验收所有查询均成功。
  同版本、实际挂载的`read_proxy_mcp.py`在`_proxy_call`使用`client.settimeout(5)`，
  与5001—5006ms失败吻合；独立阶段同工具另有成功调用及其他治理读取。
  代理截止位置已定位，内部查询为何超时及最小合适预算未证实，不归因于模型缺事实。
  最小下一诊断是对照原请求与服务端耗时，避免只提示缩小query；本复盘不调用服务重验或修代码。
  累计工具耗时含并行活动，不能直接从总墙钟扣除30.027秒或认定全部关键路径损失。
- **读回重复与材料可达性（collaboration/routing）。** Modeling反复加大facts读取量并
  搜索未挂载的Host回执路径；宿主14:01:20提醒现有小页／`next_cursor`合同后完成读回。
  已定位行为与可用通路，未证明该5分22秒全是浪费。优先使用已有分页及实际可见回执。
- **交接先于Coordinator完成（collaboration/routing）。** 14:05:53请求交接，
  Coordinator约14:06:01才完成；同版本`complete_cq_handoff`的pending-agent分支返回
  `cq_batch_scope_unauthorized`，真实原因是生产交付尚未settled。此处可重试，
  14:07:28成功，无永久死锁。保留必要交付依赖，建议准确表达pending角色，避免把正常等待
  误判业务scope越权；本次没有理由新增硬门。
- **遗漏公开验收、误解待命与过早final（collaboration/routing）。** 隐藏报告14:11:42
  完成、14:14:37回传，Delivery仍等待owner退出，14:16:47停止隐藏owner并发出未覆盖
  公开题的final；宿主提醒后14:18:16公开验收开始。公开启动先因传`question_ids=[]`
  被`evaluation_argument_invalid`拒绝，删除该不适用参数后原操作成功。
  已定位到Delivery实际动作；待命是既有生命周期合同，不是本次需新建的能力。
  优先修正完整分母／completed与standby区分／仅显式stop才停止的既有指导采用，
  不降低验收范围，也不以停止进程推进下一步。393.143秒含回传与纠偏，净可节省时间待证。
- **把三份回执误报成三批应用（platform-contract；Delivery也未复核Attempt）。**
  原readiness的`applied_batches`确含失败批；同版本`_cq_production_readiness`
  直接投影所有submission receipts，未按Attempt状态筛选。
  原`staged-decisions`与平台回执明确为2个applied、1个validation_failed。
  当前摘要字段语义与实际状态不符已定位，不能仅将误报归因Agent；最终文本已纠正，
  程序未修。最小建议是在现有投影中区分已应用和明确失败，保留原回执与独立读取，
  不新增验证器或改变模型。原readiness、裁决及运行文件不回写。

最值得先推进的是现有Delivery完整验收／待命规则的实际采用与回执摘要准确性；
查询代理作为独立窄问题继续定位。建议未实施，未新增需求或承诺节省分钟数。
生产语义、基础设施、审核和文档的有效工时均unknown，无法判断有效语义是否过半；
本次未扩展平台或harness，不用未知余时推导浪费。

## 原件与检查

- [宿主授权及时间边界](../../../workspaces/minimal-chain-20261016-glmhigh-e/authorization.json)、
  [宿主结果](../../../workspaces/minimal-chain-20261016-glmhigh-e/result.json)、
  [技术补位](../../../workspaces/minimal-chain-20261016-glmhigh-e/host-supplements.jsonl)。
- run目录`workspaces/modeling-runs/r4326-20261016-glmhigh-e-start1/`下的
  `evidence/semantic-start.jsonl`、`cq-review-request.jsonl`、`cq-review-decision.jsonl`、
  `cq-freeze.jsonl`、`staged-decisions.jsonl`、`capability-calls.jsonl`、
  `terminal-result-handoff.jsonl`、`coordinator.jsonl`、`cq-handoff-complete.jsonl`、
  `cq-acceptance-complete.jsonl`和`app-server-events.jsonl`。
- [隐藏原报告](../../../workspaces/modeling-runs/r4326-20261016-glmhigh-e-start1/acceptance-v3/reports/cq-batch-0001/attempt-0001/batch-report.json)
  SHA256 `b8027de697eac2bd5c028c06d33479751187c75679e688d19071e9b7cf790e52`；
  [公开原报告](../../../workspaces/modeling-runs/r4326-20261016-glmhigh-e-start1/acceptance-v3/public-regression/cq-batch-0001/attempt-0001/batch-report.json)
  SHA256 `4c7d4c65110d55d92993b34d13a62185f420eb1f38c4be51fc547ddddca1cdb7`。
  两者同freeze／model binding，4个独立verdict均pass，无未执行题，14份保留响应重放
  stable，无drift／unavailable；本次核对这些已有证据，不重新执行验收。
- 阶段验收时间取原报告`sessions.timing`，并发取同目录`question-tasks/*.json`；
  不取文件mtime或owner退出时间。原报告标记均为`non-blind-regression`。
- 当前`runner.py`、`read_proxy_mcp.py`哈希与baseline相同；实际Modeling挂载bridge
  也一致，因此上述源码定位适用于原进程。仅做聚焦源码／事件核对，没有声称图谱影响覆盖。
- 本次只更新复盘、需求验证说明和既有台账；检查链接、阶段计算、报告哈希与diff。
  未改业务代码或技能，无需后端／前端测试、服务重启。原运行和裁决保持只读。

## 同日整体调优分析追加

用户要求继续分析性能，后续逐调用核对见[调优分析](2026-10-16-glmhigh-e-performance-tuning-analysis.md)。
补充两个计数边界：2个applied和1个validation_failed是durable Batch口径；实际
`modeling_submit_model_changes`调用6次，另3次在编译／输入阶段拒绝。除已列6次
语义查询超时外，隐藏Consumer还有1次SPARQL约5秒超时。
四Consumer的17次语义查询为14次参数拒绝、2次超时、1次正常返回；旧代理默认及实际
提示的`rule`类型已与当前后端冲突。四题最终语义回归通过依旧保留，但不证明正常
语义检索路径可用或无故障；阶段时间未变化。原事件、报告及授权不回写。
