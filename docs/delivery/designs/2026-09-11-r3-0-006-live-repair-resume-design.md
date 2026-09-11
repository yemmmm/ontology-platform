# R3.0-006 live repair/resume — 最小交付设计

- 日期：2026-09-11
- 状态：实现已完成；计划评审 Round 2 PASS，独立功能复验 Round 2 PASS（限定本增量）
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-006；必要恢复边界复用
  `docs/requirements/requirements-v2.3.md` R2.3-009
- 相关实现：`modeling_team/interventions.py`、`runner.py`、`__main__.py`、
  `runtimes/codex.py`、`skills/modeling-dev-loop/`

## 1. 目标与非目标

当 Modeling/Protocol/Coordinator 遇到外部接口或可修正输入问题时，保留当前 live
run、Agent 进程、原 Codex thread、候选/CQ/审批/提交 intent/receipt 和证据；用户修复
外部依赖后，由宿主 Skill 把“一句话继续”绑定到当前唯一 issue，Coordinator 恢复责任
角色，原失败操作在同一 run 中复测。该恢复不新增 semantic start、授权、准备或清理。

本增量不实现跨进程/跨 run 恢复、死 App Server 重绑、自动重试框架、后台队列、管理 UI、
自然语言生产路由或新的语义裁判；真实模型质量、SQL 和授权验收仍按 R3.0-006 独立验收。

## 2. 修改前基线与守恒边界

- `RecoverableIssueLedger` 已有 one-active-issue、CAS epoch、`reported → pause →
  waiting_* → resolution_ready → resume → resolved`，并绑定 run/reporter/thread/candidate。
- Runner 已有 issue-pending active-time 排除（`_track_issue_pending`、
  `_check_run_fallback_timeout`）、普通 delivery requeue、pending 时 cleanup 延迟，须复用。
- 当前 `_handle_foreground_message` 对已进入 `receive_outer` 的 `TeamConfigurationError`
  仍按 fatal 处理；当前 `repair_completed` 强制五个修复字段；unsupported component 或
  reporter busy 可能在 resolution 已保存后进入 `rebind_required`。
- `staged_unreconciled_batch` 只关闭 staged write gate；`_staged_gate_killed` 无解锁路径。
  这保护未知写入，不能用外部通知直接清除。

## 3. 功能合同

### 3.1 可恢复接口/输入错误

1. 已确认无写入的 read、health、context、候选读取或提交前校验错误，由责任 Agent
   `report_issue(category=platform_repair|protocol_guidance, mutation_state=confirmed_no_write,
   failing_operation=..., requested_action=...)`；外层字段/当前 issue 绑定错误由 Runner
   返回带 `code`, `retryable=true`, `issue_id` 的 typed rejection，只拒绝这一条输入。
2. Runner 只捕获明确的 recoverable outer rejection；内部不变量、thread/candidate/run
   绑定漂移、不可恢复进程死亡仍保持 fail-closed，并保留现场。禁止 blanket catch。
3. 正常 CQ 审核、用户访谈、上游候选和局部交接等待不创建 terminal/cleanup；若确有路由
   故障，只暂停责任角色并保留其他角色、delivery/reply slot 和既有产物。

### 3.2 用户一句话与恢复

1. `modeling-dev-loop` 宿主 Skill 读取当前唯一 active issue，将“接口已经修复完成，请
   继续”转换为严格的 `issue_resolution` envelope（issue/reporter/epoch/run 绑定）；
   Runner 不解析关键词、不新增自由文本 NLP 路由。多 issue、无 active issue 或绑定不明
   时返回 typed rejection，环境仍保留。
   新简短修复格式必须显式携带 `run_id`；宿主的新消息也应携带该字段，Runner 在持久化前
   校验与当前 live run 相等。旧五字段/guidance 格式可省略 run_id，继续使用原有的目标
   FIFO/run 绑定；显式提供时一律校验。兼容入口不声称具备省略 run_id 时的跨 run 防错投能力。
2. `repair_completed` 保留旧五字段完整形态（`repair_component`、`before_digest`、
   `after_digest`、`verification_reference`、`mutation_reconciliation`）的兼容性，同时允许
   Host 发送简短 `resolution_text`。`repair_component` 必须由 Host 按当前 issue 核实，
   支持新增 `external_service`，既有 `shared_backend_service` 与 `shared_backend_data`
   保持有效；`before_digest/after_digest` 可省略。对已确认 `confirmed_no_write` 的 issue，
   Host 核实 component 即足以启动原步骤复测，额外 verification/reconciliation 字段可选，
   不强制先做健康 probe。只有 `mutation_state=unknown` 才要求既有只读核对和真实
   reconciliation；通知或文字声明不能解锁写入。
3. unsupported repair component 在 resolution 持久化前做可恢复 typed rejection，保留 issue
   waiting，不消耗 resolution、不改变 issue epoch、不 cleanup，也不进入永久 `rebind_required`。
   死进程、frozen Runner/Transport/Skill 或 thread 已退出仍不能在本增量内重绑，保留证据并由
   宿主按现有规则决定终止或另开 fresh start。
4. Coordinator 仅在责任 reporter 已结束暂停 turn 后发送 bound `resume`；reporter 仍 busy
   时返回/记录 `resume_waiting_reporter`，保留 pending issue、原 resolution 和未派发 control，
   下一次 drain 可重试（允许保留 `resume_sent` 以防重复接收控制），
   不转 `rebind_required`、不重复持久化 resolution。成功恢复必须是同一 thread 的新 turn。
5. resume 后责任 Agent 使用原请求/候选/plan/idempotency key 复测失败步骤；不得重新生成
   CQ、审批或候选。收到确定回执后才推进后续阶段；原始失败与恢复证据均 append-only。
   保留线程不代表 Session/lease 永不过期；责任角色按已有平台合同处理已失效的运行凭据，
   不更改获批语义或以“保留环境”绕过实际授权/版本检查。

### 3.3 未知写入硬边界

`mutation_state=unknown`、apply 超时/断连或 intent/receipt 不一致时，一句话 resolution
不得 resume 写入，staged gate 必须保持 closed，issue 保持 waiting 并保留原 intent/receipt
证据。本增量没有可验证的 unknown-write 解锁入口：不得把通知、文字、健康结果或假定的
adjudication 当成已闭合的只读核对/真实 reconciliation，也不新增 reconcile 服务、同 key
自动 retry 或 gate reopen。若未来需要正式 adjudication API，另列后续需求与测试；当前仅
提供安全拒绝和可观察等待。

## 4. 主会话/提示同步

- 主会话状态记录复用现有 run handoff：run/thread、active issue、候选/CQ/审批/intent/
  receipt、mutation state、当前 gate、已消耗授权和下一动作；修复通知不增加授权额度。
- `skills/modeling-dev-loop` runbook 改为一句可执行恢复说明：typed outer rejection 只修正当前
  消息，确认真实 loaded checkout/挂载后在同一 start 修复并复测原步骤，同时保留原产物与授权
  边界；外层 `resume` 不是跨进程恢复，并删除“缺字段必 fatal”旧规则。
- `modeling_team/agent-packages/protocol/instructions.md` 将 issue category 的
  `platform-contract` 修正为 `platform_repair`；`platform-contract` 只保留为宿主失败归因。
  明确 staged unknown 只能保留等待并关闭写门，不接受一句话解锁；未来 adjudication 若需新
  API 另行交付。

## 5. 影响设计的假设与缺口

1. 当前 live Runner、Coordinator 和责任 Agent 进程在用户修复期间继续存活；否则本增量只
   保留证据，不能声称恢复。
2. Host Skill 能从既有 issue 事实核实 repair component，并在已知 no-write 情况下启动原步
   骤复测；无法证明 no-write 时必须落入 unknown 分支，不以文字补证。
3. 当前没有可验证的 unknown-write gate reopen seam；未知写入保持 BLOCKED。完整
   adjudication/readback 恢复若需新 API，记录为后续，不扩大本次范围。

上述代码与提示边界已实现，独立测试结果追加在同一共享测试计划中。跨进程恢复和未知写入
解锁仍不支持；机械同线程 issue 恢复不能作为真实建模或语义 E2E PASS。

## 6. 技术落点与计划评审

- 明确区分可修正输入异常与 `TeamConfigurationError` 的内部失败；前者只由已核实的
  envelope/问题选择/epoch 校验在无副作用处抛出，foreground 只捕获前者。持久化和实际
  Runtime delivery 的异常不并入该类型，不以异常消息字符串做分类。
- `resume_sent` 在 Broker 控制入队时已设置；busy 检查发生在 Runtime dispatch 前。本次
  需提供局部、绑定同 issue/epoch 的 defer/再派发处理：未 send 时保留原 resolution 并等待
  reporter idle，下一 drain 再派发一次；不得已送出后回滚或重送。无队列框架或跨进程重绑。
- 对本次不支持重开的 unknown mutation，Ledger 在持久化 resolution 前拒绝所有非 abort
  resolution，包括旧五字段带 `reconciled` 等字符串；staged durable unknown/mismatch 也必须
  独立阻止恢复，不能依赖 Agent 报告的 mutation_state。显式 abort 仍可走既有受控收尾。
- 新格式显式 run_id 在外层接入点验证；后续复用既有不可变 IssueResolution 与 Ledger
  run/issue/epoch 比较，不在每层重复实现同一检查。

计划评审 Round 1：REVISE。H1 busy 状态消耗、H2 字符串 reconciliation 旁路、H3 输入错误
fatal 均接受，以上明确实现落点和负向测试；H4 跨 run 错投接受新格式显式 run_id，旧格式
保留既有 FIFO 绑定兼容，不扩大为破坏旧调用方的全量迁移。
Round 2 变更面复审 PASS：四项 High 已在设计与共享测试计划闭合，无待裁决项；该结论仅为
计划评审，不是实现、接口故障恢复或真实语义验收 PASS。

## 7. 实现与验证结果

已交付可恢复外层输入拒绝、简短且绑定当前 run 的修复通知、busy reporter 延后派发、
unknown 写入保持关闭，以及三个角色提示与宿主 Skill/runbook 同步。用户一句话由宿主
绑定为现有结构化消息，不增加关键词解析器或新的恢复框架。

- 主会话完整回归：`env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest
  modeling_team -q` → 1510 passed、1 skipped、328 subtests passed，95.05 秒，exit 0。
  只隔离测试进程继承的环境变量，未修改实际 provider 配置。
- 独立 Round 1 已通过实际本地 HTTP/AF_UNIX 故障链和受控 Runtime 边界；唯一提示回归
  R1-001 已恢复原措辞，Round 2 独立目标复验 8 passed，限定本增量的功能结论 PASS，见
  [共享测试计划](../test-plans/2026-09-11-r3-0-006-live-repair-resume-test-plan.md)。
- 无 backend/frontend 修改，无产品服务重启，无真实 semantic start；已有 live Runner 不会
  热加载本次代码或冻结提示。上述结果不证明真实 App Server/LLM、语义建模、检索或 SQL 验收。
