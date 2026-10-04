# R4.0-015 建模过程中的早期公开业务问答反馈设计

## 1. 设计状态、依据与边界

本文是 [R4.0-015](../../requirements/requirements-v4.0.md#r40-015-建模过程中的早期公开业务问答反馈) 的详细设计，承接 R4.0-009 的独立验收入口、R4.0-013 的逐点诊断原则和 R4.0-014 的生产交接说明。本文只设计一条在生产交接前可执行的、范围受限的公开业务问答反馈路径；不改变隐藏验收、不新增问题治理平台、不启动真实建模或外部业务调用。

设计完成不等于实现、功能验收或真实语义 PASS。公开反馈的结论是生产侧诊断输入，不能提升最终验收判定；同一问题一旦用于生产修模，后续只记相应回归属性。

## 2. 当前问题与设计目标

现有 exact IRI／资源匹配能证明资源可找到，不能证明 Consumer 能用获准语义回答业务问题。若等到所有场景完成、生产交接后才第一次问答，模型表达、检索取得和作答理解的问题会集中到末端暴露。

本设计要做到：

- 在一条已经安全写入并能确定性读回的完整小业务链可消费时，尽早问一至少量获准公开题；
- 保留实际问题、公开投影、读取响应、Consumer 答案、覆盖／缺口和当前模型状态绑定，使反馈可复核；
- 按证据区分模型表达、检索／可发现性、Consumer 作答和原因未知，沿现有生产修正职责继续；
- 让公开题、隐藏题、生产修复和最终独立判题的边界保持可观察，不用早期成功制造完整 PASS。

## 3. 现有入口与实际调用链

当前 R4 CQ 验收的真实平台读取／作答链已经在 `modeling_team/__main__.py` 中实现，不能只按角色名称推断：

```text
_run_cq_acceptance
  -> _cq_execute_batch
  -> build_platform_batch_packet (modeling_team/acceptance_runtime.py)
  -> CodexRuntimeAdapter.run_v3_acceptance_child
  -> launch_v3_acceptance_child
  -> package platform-examiner + platform_read_proxy + examiner_report sink
  -> query_semantic_context (及当前 packet 授权的其他只读工具)
  -> submit_examiner_report / _CQ_PLATFORM_ROLE_INSTRUCTIONS
  -> per-question Platform Examiner reports + retained platform-read receipts
```

证据有三处：`_CQ_PLATFORM_ROLE_INSTRUCTIONS` 明确要求对每道冻结题生成 `answer` 并提交一次报告；实际 v3 角色资产是
`modeling_team/agent-packages/v3-acceptance-batch/platform-examiner.md`，它只允许通过
ticket-bound `platform_read_proxy` 做获准只读查询，并向 `examiner_report` sink 提交
`schema_version/batch_id/question_id/question_content_version/answer/evidence_refs/explicit_unknown/status/failure_layer/reason`；
`_cq_execute_batch` 在 child 返回后读取 `examiner_reports`、`_cq_collect_platform_read_responses` 和持久化的
platform-read artifact。当前 v3 的 `platform-examiner` 是一个 single-continuous-batch 的平台语义读取／作答角色；它不是最终
Judge 或业务裁判，也不接收答案点或参考答案。

早期公开反馈复用上述**平台 Examiner 阶段**作为真实语义读取与回答，不调用后续 Judge 阶段。它不把该角色名称扩展成新的通用 Consumer 或业务裁判：题意范围和后续模型／检索／作答问题由宿主依据公开题和实际报告交回既有 Coordinator／Modeling／Protocol 职责。

## 4. 复用的既有能力

| 能力 | 现有入口 | 本设计的使用方式 |
| --- | --- | --- |
| 公开题隔离 | `modeling_team/competency_questions.py` 的 `public_projection`、冻结／版本摘要 | 只从当前获批公开投影组装反馈输入；不读取隐藏题文本、答案或私有审核理由 |
| 语义读取／回答 | `__main__._cq_execute_batch` 的 `build_platform_batch_packet`、`CodexRuntimeAdapter.run_v3_acceptance_child`、ticket-bound `McpReadForwarder` | 以当前只读 scope 读取公开业务链，复用分页、partial、显式未知和 platform-read receipt；不把平台 Examiner 当最终裁判 |
| 作答报告 | `acceptance_runtime.py` 的 v3 Platform Examiner report contract、`report_sink_mcp.py::submit_examiner_report` | 复用现有 v3 per-question `answer/evidence_refs/explicit_unknown/status/failure_layer/reason` 报告和 retained response；不新增 report schema |
| 反馈修正 | 现有 Modeling／Coordinator／Protocol、CQ 审核、dry-run/apply | 将反馈当作可定位问题输入，修订仍按现有 review、版本、审批和写入流程 |
| 状态绑定 | 当前 run 的 scope、已核验 question identity／freeze digest、模型状态、read receipt 和安全写入证据 | 从生产 handoff 前已有运行材料取得绑定；在读取前后观察状态，状态变化后标记过期，不混用前后状态 |

最终 CQ Examiner／Judge 路径仍在生产交接、写入排空后独立只读取证；它们不参与被验收 run 的生产修复。早期反馈只复用平台 Examiner 的真实读取／回答阶段。

## 5. 方案与决策

### D015-1：触发条件是“可消费链就绪”，不是固定批次

宿主在发现一条业务问题所需的对象、动作、规则、流程或映射已经安全写入、确定性核对且没有 unknown write 后，选择一至少量能够覆盖该链完整含义的公开题。此时可从仍在生产中的现有 run scope、已核验的题目 identity／freeze digest、模型绑定和安全写入／读回证据取得交接前绑定；不要求 production handoff 已发布，也不要求消费正式 acceptance attempt。题目、问题链或批次数不固化为通用数量，也不把公开问答设为每批必做的机械硬门。

反馈不得在写入状态未闭合、只存在角色自述或只能 exact 匹配资源时宣称业务链就绪。授权不足、内容不完整或响应 partial 时照实结束并保留缺口，沿当前生产流程继续。

### D015-2：输入只使用公开投影，范围绑定当前状态

宿主的 feedback binding 记录包含公开题文本、题目内容版本／digest、当前公开投影 digest、获准读取 scope、模型状态／读回摘要、已核验的安全写入／identity 证据和必要的执行上下文；传给既有 v3 Platform Examiner packet 的字段仍只遵循当前 packet contract。binding 记录不包含隐藏题、隐藏答案、隐藏审核 note、最终 Judge 评分点或能从这些资料反推结论的私有诊断。

回答依据当前真实语义读取。宿主在首次读取前记录 scope、model binding、freeze／content digest 和安全写入读回状态，在反馈结束后再次观察同一状态；若期间模型状态、冻结内容、授权 scope 或安全写入状态发生变化，宿主将原结果标记为 superseded／不可用于当前状态，并在下一次安全读回后重新执行需要的公开问题；不得拼接两种状态的响应。

### D015-3：反馈是诊断，不是正式 PASS

报告保留问题、真实响应、Consumer 答案、覆盖情况、已知不足和证据限制。宿主可以依据公开题意和 R4.0-013 的逐点思路整理“模型表达／检索／作答／原因未知”的后续方向，但不能把它转化成正式隐藏 Judge verdict 或全局模型质量结论。

反馈发现问题时，通过既有 Coordinator／Modeling／Protocol 通道交回生产角色；涉及内容修订的部分走 CQ review、显式 `modify`／`supplement`、dry-run/apply 和确定性回读。生产角色不接收隐藏资料，宿主不直接替它决定业务语义。

### D015-4：沿用现有报告形状，避免第二套治理平台

实现优先复用现有 v3 Examiner per-question 报告和当前 run 的 host record，但把早期反馈输出放在独立的 run-owned、append-only feedback 目录／记录中；它不占用正式 acceptance attempt、不得写入正式 batch-report，也不触发生产到验收的 phase 切换。若现有记录无法同时绑定公开投影、模型状态、安全写入证据和 feedback 路由，只增加最小元数据，包含：`run_id`、`question_id`、内容／投影 digest、scope／model binding 摘要、前后状态观察、read receipt、反馈报告路径、状态、反馈摘要和后续路由。它不是新平台 Schema、问题数据库或自动评分器。

### D015-5：早期成功不改变盲测资格

公开反馈成功只证明该公开问题在该状态下可消费；隐藏题仍按正式独立验收执行。公开题或其答案用于修模后，后续成功只能作为公开回归／生产证据，不再作为隐藏盲测证据。原冻结材料和旧报告保持只读。

## 6. 运行顺序

1. 宿主在仍可继续生产的现有 run 记录标明目标小业务链、获批公开题和触发依据；从下述 `materialization_progress` 检查点的 manifest 与已核验 artifact 取得交接前绑定，记录无 unknown write。此步骤不要求发布 production handoff，不创建或消费正式 acceptance attempt。
2. 从当前冻结池生成公开投影，记录题目 identity／content version、公开 projection digest 和可见字段。若题目未冻结，先沿现有审核路径完成冻结；不把未批准题送入反馈。
3. 通过 `modeling_team/__main__.py` 的新薄宿主入口调用现有平台 Examiner 阶段：构造同一 `build_platform_batch_packet`（只含公开题、content version、scope 和 model binding），调用 `CodexRuntimeAdapter.run_v3_acceptance_child`、`McpReadForwarder`、现有 `platform_read_proxy` 和 `examiner_report` sink。保留实际 tool response、分页／完整性信息、显式未知和 v3 per-question report；不构造 `build_acceptance_judge_packet`，不启动 acceptance Judge，不发送答案点或隐藏诊断，不消费正式 attempt 或切换 phase。
4. 宿主读取 v3 报告的 `answer/evidence_refs/explicit_unknown/status/failure_layer/reason`，并检查结束时状态是否仍绑定开始时的 scope、identity、model binding 和安全写入证据；没有足够证据时使用“原因未确定”，不补造业务事实。状态发生变化时记录 superseded，不把前后输出拼接。
5. 将需修正事项交已有生产责任者。修订、审核、dry-run/apply、回读和受影响公开题复核沿既有流程；未修正问题不因流程继续而记为通过。
6. 后续正式生产交接时，在 handoff 摘要中列明公开反馈已执行／未执行、题目是否曝光、反馈状态和未闭合项；该 handoff 只作为后续正式验收的交接材料，不回填或消费早期反馈的独立输出。完成后交正式独立验收；不让最终 Judge 读取或修改该生产记录。

## 7. 实施触点

先以当前代码和 runbook 的现有入口验证是否已能完成上述顺序，再实施最小差异：

| 文件／入口 | 可能的最小变更 | 验证重点 |
| --- | --- | --- |
| `skills/modeling-dev-loop/references/team-runbook.md` | 说明触发条件、公开投影、状态绑定、报告和修正顺序 | 不变成固定题数或生产硬门 |
| `modeling_team/__main__.py::_run_public_feedback`（新增薄宿主入口） | 从显式 `checkpoint_id` 的已验证 manifest／artifacts 取得交接前绑定，强制选择已冻结的公开 `question_id`，复用 `_cq_execute_batch` 的平台 packet／forwarder／持久化片段，只执行 Platform Examiner 阶段 | 不要求 production handoff，不消费正式 acceptance attempt，不进入 `_cq_build_judge_evidence_bundle`、`build_acceptance_judge_packet`、Judge session 或 `complete_cq_acceptance` |
| `modeling_team/acceptance_runtime.py`、`modeling_team/runtimes/codex.py` | 复用 `build_platform_batch_packet`、`run_v3_acceptance_child`、`McpReadForwarder`、`response_persistence` 和现有 sink；只提取共享平台阶段 helper，不改 v3 packet／sink contract | 不新增 Consumer runtime、report schema、tool allowlist 或诊断查询 |
| `modeling_team/competency_questions.py`、`runner.py` | 仅修正真实的公开 projection／identity／版本绑定缺口 | 原冻结、旧报告和隐藏隔离不变 |

入口参数最小为 `--run-root`、`--checkpoint-id`、`--freeze-id`、一个或多个 `--question-id`、`--model-profile` 和 `--session-timeout`；入口使用下述已发布检查点，拒绝隐藏或未冻结 ID。`--model-handoff` 不是早期反馈前置参数；若后续正式 handoff 已存在，只能作为只读关联。输出写入独立的 run-owned early-feedback 目录／记录，并保留标准 v3 Platform Examiner per-question reports 及 platform-read artifacts；不创建或消费正式 attempt，不写正式 batch-report，不切换 production／acceptance phase，不新增报告格式或报告管理器。不得把 early feedback 的 per-question reports 拼成正式 CQ batch PASS。

不预先新增角色包、UI、调度器、快照系统、问题治理平台或固定重试。实现若只需上述 host wrapper 与共享平台阶段 helper，不改业务模型或后端服务。

### 7.1 交接前绑定的确定来源

当前实现入口限定于已启用 `modeling_checkpoints` 及对应 selector 的任务。宿主通过现有
`host_ops.save_checkpoint(run_id, kind="materialization_progress")` 向活动 Runner 提交保存，
按原回执／`inspect_checkpoints` 确认检查点实际发布；提交成功不等于包已就绪。
自动产生的同类当前检查点也可复用，不为反馈重复保存已满足条件的包。

输入显式绑定 `checkpoint_id` 和 `checkpoints/<id>/manifest.json` 的摘要。复用现有 checkpoint
读取和摘要校验，要求 `materialization_progress` 完整包；从 `platform_bindings.project_id`、
`ontology_ids` 取得真实授权身份，`platform_bindings.run_scope` 保留获准范围，
`model_profile_digest` 仅用于配置绑定，不冒充平台内容摘要。题目、冻结和公开投影由 manifest
所列 CQ artifacts 解析且核验摘要；staged intents／receipts 与 `write_positions` 来自
`Runner._collect_checkpoint_stage` 和 `_save_run_checkpoint_captured` 的既有 capture/drain。
不得从不存在的 run-contract scope 字段或名称猜身份，也不得读取私有 artifact 后将其发给角色。

该检查点是读取起点，不保证后续无写入。开始前按既有写尾／回执核对 checkpoint 之后的写入，
存在 unknown write 或无法确定安全读回时返回准确未完成原因；不重放写入。记录当前平台模型
观察值并在反馈后再次观察，结合写尾／回执判断变化；发生变化的反馈保留为 superseded，不能
用于当前状态。复用现有观察合同，不新建快照、锁或长期冻结机制，生产可继续。

selector 未启用、包缺失／不完整、摘要不符或 scope 未核实，均保留反馈未执行／不可用和原因，
不静默启用检查点、修改 Task、改正式 phase 或阻断整个生产目标。现有公开反馈入口的上述能力
条件在 runbook 明示；后续对不启用检查点任务的支持不随本期自动扩展。

## 8. 验收标准与独立审阅

| 编号 | 验收场景 | 通过标准 |
| --- | --- | --- |
| A1 | 一条安全写入并可消费的小链在生产仍可继续、正式 handoff／attempt 尚未发布时就绪 | 从现有 scope、已核验 identity 和安全写入／读回证据取得绑定；实际公开题、获准读取和业务回答均有独立反馈输出；生产继续，正式 attempt 和 phase 不变；不以资源匹配代替回答 |
| A2 | 反馈发现模型表达错误、检索未取到或答案误解 | 依据实际响应区分责任，沿现有修正／复核路径继续；不强归模型缺失 |
| A3 | 语义未知、授权受限、partial 或运行不完整 | 报告保留具体不足和状态；不编造事实、不声称业务通过 |
| A4 | 反馈与生产继续并行 | 隐藏资料不进入反馈；最终独立验收者不修复该生产 run；公开边界可审计 |
| A5 | 公开问题成功后进入正式验收 | 公开结果标为非盲诊断／回归，隐藏和未覆盖范围仍按正式路径执行 |

设计审阅应独立核对：触发是否晚于安全写入、是否泄露隐藏资料、是否混用模型状态、反馈是否误当 PASS、修正是否绕开既有审核／dry-run/apply、是否引入新的硬门。出现 Critical／High 时先修设计再审阅；设计审阅不运行模型、不修改冻结产物。

## 9. 结论边界与待实现证据

本文交付的是可评审的最小方案。实现阶段须证明当前入口能选择公开题、组装公开投影、保留真实响应和状态绑定；若已有路径满足要求，直接复用并只补文档。受控功能测试只能证明隔离、记录和生命周期；真实公开业务问答需另行授权并单独记录，不能用 mock、提示检查或最终隐藏通过替代。
