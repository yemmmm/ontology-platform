# R2.3-009 Modeling Team 校验降级与 Agent 自修复 — 设计文档

- 日期：2026-08-19
- 状态：Design（planner 产出，待 review；未实现任何产品代码）
- 需求来源：`docs/requirements/requirements-v2.3.md` R2.3-009（用户 2026-08-19 确认的 6 条核心决策为权威合同）
- 失败证据：`docs/delivery/records/2026-08-18-r2-3-008-luna-fullstack-route-delivery-record.md` start11/12/13（defect 9/10/11，commits 4711240 / c0fdc14 / a9fac61 已做窄修复，本设计将其哲学一般化）

## 1. 目标 / 非目标

### 目标

1. 消灭"校验失败 → 终止运行"的代码路径：run 只能以 (a) Agent 自己的终态报告
   （completed/blocked）或 (b) 分层兜底超时结束。
2. 一切运行中校验失败——含 A 类平台写入完整性——以 typed、可读原因返还责任 Agent，
   供其重试或报告 blocked。
3. B 类候选通道协议检查降级为"记录 observed-issue 证据 + 生成 Agent 可读冲突"。
4. C 类检索证据警告扫描降级为 record-only；检索证据完整性由 Examiner 独立验收判断。
5. 致命仅保留：启动期配置校验（Agent 尚不存在，无反馈对象）与真正的内部不变量崩溃
   （代码 bug，非 Agent 行为）。
6. 问题记录是优化参考，不是运行限制。

### 非目标

- 不放松 backend/ 自身的 API 校验与原子性（本需求只改 modeling_team Runner 工具层
  对校验失败的处置）。
- 不改变最终语义验收独立性（Examiner 仍独立判断检索证据与模型质量）。
- 不移除证据记录——是"记录不阻塞"，不是"不看见"。
- 不引入新表/新服务/新框架；反馈通道全部复用既有机制（capability 错误载荷、
  typed conflict envelope、协作 issue ledger、redrive 文本）。

## 2. 现状失效路径（代码事实，2026-08-19 核对）

- 终止闩：`modeling_team/runner.py:3359` `_latch_formal_candidate_failure(classification,
  reason)` —— `mark_terminal_failure` + gate close + state
  `TERMINAL_FAILURE_PENDING_CLEANUP` + evidence `formal-candidate-terminal-failure` +
  ledger `record_terminal_failure`。调用点：3139/3162/3188/3202（receipt wakeup 四类）、
  3259（accepted-candidate-registration-rejected）、4012/4331（candidate-progress-timeout）、
  4072（candidate-envelope-invalid，defect 10 路径）、4117（reply-slot-reopen-rejected）、
  4197/4337（turn-binding-missing）、4334（redrive-exhausted）。
- 进程退出：`modeling_team/__main__.py:670-697` `except (OSError, ValueError, RuntimeError,
  TeamConfigurationError) → print("run failed: …"); return 2`。`_latch` 后 re-raise 即走此路径。
- 超时/重驱：`modeling_team/candidate_progress.py:842-858` `check_deadline` raise
  `FormalCandidateProgressTimeout`（默认 120s，`profiles/r2-3-008-modeling-team.yaml:27`
  置 300s）；redrive 仅一次（`candidate_progress.py:865-878`）。
- 一次性回复槽：`modeling_team/transport_mcp.py:436-440`（defect 11）；reopen 仅候选方向
  （`transport_mcp.py:558-587`）。
- 检索警告扫描：`modeling_team/protocol_retrieval_gate.py:449-498`
  `_validate_response_quality`（defect 9；`context_truncated`+cursor 已豁免）。
- 既有反馈通道（复用基础）：`modeling_team/capability_mcp.py:633-701` 已把 handler 异常转成
  `{ok: False, error: diagnostic}` structuredContent + `evidence/capability-calls.jsonl` 审计
  （-32001 保持 opaque 是刻意的，防 token 侧信道）；`acceptance.py:1768-1940` 检索 gate 错误
  已经以 `AcceptanceContractError(data={reason: "ordinary_retrieval_incomplete", detail})`
  形态经 MCP 返还 protocol Agent；issue pending 期间 deadline 检查被跳过
  （`runner.py:3388-3400`）——注意是跳过检查而非暂停时钟（见 §4 通道 3 的显式接线要求）。
- raise 规模：runner 227 / start_ledger 77 / transport_mcp 70 / protocol_retrieval_gate 56 /
  candidate_progress 42 / handoff 25 / formal_runs 14 / candidate_platform_gate 12 /
  protocol_retrieval_mcp 10 / capability_mcp 5。

## 3. 分类 taxonomy 与逐类处置

分界线：`runner.start()` 成功返回（Agent 进程已存在）之前为启动期；之后为运行期。

### S — 启动/配置校验（保留致命）

- 范围：`runner.py` prepare/preflight 区（256-1199：run 目录、ledger factory、profile
  digest、acceptance standard、baseline artifacts）、协调 kind 固定（1323）、角色可见性探测
  （1629）、model_routing/provider 凭据预检、`__main__.py` 启动参数。
- 处置：不变。Agent 不存在，无反馈对象；按既有 presemantic release / startup failure 路径
  记账。reason_code 统一加前缀 `startup-config:`（仅 evidence/诊断用途，不改行为）。

### A — Agent 行为·平台写入完整性（致命 → typed 反馈，run 继续）

- 范围（**仅 Agent 可控**的写入完整性行为；runtime/Runner 内部产生的结构性失败见 I 类）：
  - 同步站点（Agent 主动 tool call 触发，请求栈内可直接返回错误）：`acceptance.py`
    dry-run/apply stage 合同（`_error` 载荷路径，今天已经同步返还）、`protocol_retrieval_mcp.py`
    的 apply/handoff 请求路径、Agent 发起的 temp key 申请违约；
  - 异步站点（Runner drain/dispatch 循环观测到，无在途请求可挂载错误）：
    accepted-candidate registration rejected 中归因于候选工件的部分（见下方细分表）。
  - **排除到 I 类**（review High-3 修正）：dispatch receipt 结构性失败
    （`candidate_progress.py:807-825` bind_dispatch 的 turn_id/mode 校验、`runner.py:4197/4337`
    turn-binding-missing——由 runtime adapter 产生，Agent 无法修复）、
    `candidate_platform_gate.py` 的文件系统/状态守卫（symlink、目录、gate state——Runner 内部
    一致性）、accepted identity/artifact mutation（`acceptance.py:1777/1781/1914-1933`——
    内部不可变量违约）。这些保持 fail-fast 致命，防止 adapter 故障退化为 90 分钟空转。
- 处置：
  1. 不调用 `_latch_formal_candidate_failure`，不 re-raise 至 foreground loop；
  2. **同步站点用通道 1**（capability 错误载荷，随 tool call 响应返回）；**异步站点用通道
     2**（Runtime 直接投递 typed 反馈，复用 `candidate_receipt_registered_notice` 先例
     `runner.py:3152-3170`）。通道 1 是同步响应而非推送通道，不能承载异步站点（review High-1
     修正）；
  3. evidence 记 `validation-feedback` 事件（class=A, code, responsible_agent, delivery_id,
     retry_allowed=true）；
  4. 重试次数不设代码上限，仅受 §5 兜底分层约束。
- **registration-rejected（旧 `runner.py:3259` latch 位）责任细分表**（review High-2 修正；
  依据 `acceptance.py:1741-1940` 的 `_error` 站点枚举）：

  | 触发原因（`AcceptanceContractError` / `ProtocolRetrievalGateError`） | 归类 | 反馈对象 |
  |---|---|---|
  | `ProtocolRetrievalGateError`（consumer_query plan 缺陷，`acceptance.py:1791/1804`） | A | **modeling**（plan 是候选工件内容） |
  | replacement revision/digest 合同违约（`acceptance.py:1741-1760`） | A | protocol（receipt 写入行为） |
  | observed platform tool/arguments/artifact 违约（`acceptance.py:1872-1940` 中 Agent 请求内容不合法项） | A | 责任调用 Agent |
  | identity/semantic payload/artifact **mutation**（`acceptance.py:1777/1781/1914-1917`） | I | 致命（内部不可变量） |
  | snapshot/model-state 绑定类（`acceptance.py:1965-2072`） | I | 致命（Runner 内部状态） |

- **post-complete 重开迁移**（review High-2 修正；注册侧联动见下）：registration rejected
  时 progress 已处 `complete` 态（`candidate_progress.py:659-666`），而现有唯一重开路径
  post-receipt conflict 被 `allow_post_receipt_revision` 硬性限定
  `requirement_id == "R2.3-003"`（`runner.py:574-576`）。本设计将 R2.3-003 的 post-receipt
  reopen **泛化**：registration rejected（A 类分支）时 Runner 投递 typed conflict 并将
  state 迁回 `awaiting_revision`，modeling 的下一份严格更新 revision 走既有 revision 门
  注册。该迁移对所有 requirement 生效，删除 R2.3-003 硬编码判定。
- **注册侧联动（review New-A 修正，与重开迁移必须成套实施）**：注册替换分支同样被 task
  硬编码限定（`acceptance.py:1750` `self.task_id == "r2-3-003-existing-scope-incremental"`），
  其他 requirement 下以新 identity 二次注册会触发 `acceptance.py:1777`
  `_error("accepted candidate identity was mutated")`——即重开后的修复 revision 会在最后
  一步撞上 I 类致命守卫，自修复闭环以 kill 收场（defect 11 形态复活）。因此重开迁移
  执行时 Runner 必须**显式作废当前 `_accepted_candidate_identity`**（连同
  `_accepted_candidate`/`_ordinary_retrieval_gate`），使注册侧按首次注册路径接受 strictly-newer
  revision；`acceptance.py:1735/1750` 的替换分支随 reopen 判定一并泛化。identity mutation
  守卫（1777/1781）对**未经重开迁移**的路径仍然致命（I 类不变）。

### B — Agent 行为·候选通道协议（致命/拒绝 → observed issue + Agent 可读冲突）

- 范围：
  - `candidate_progress.observe_delivery` 的语义违约：revision 非严格更新、digest 复用
    （`candidate_progress.py:600-604`；defect 10 修复后的非候选忽略语义保持不变）；
  - receipt/conflict envelope 校验（`validate_formal_receipt/conflict` 在投递观测路径上的
    调用点）；
  - transport 一次性回复槽拒绝（`transport_mcp.py:436-440`）与 reopen 拒绝
    （`runner.py:4117` 不再 latch）；
  - consumer_query plan 预校验（`protocol_retrieval_gate.py:327-358, 667`）——构造
    ProtocolRetrievalGate 失败时不再阻断，生成冲突说明返还 modeling；
  - `runner.py:4072` candidate-envelope-invalid latch 位。
- 处置：
  1. 检查保留（工具层拥有协议格式与解析，per CLAUDE.md），但违约时：evidence 记
     `observed-issue` 事件（含原始投递文本——修复 defect 10 发现的"raise 先于持久化导致
     证据丢失"问题：先落 deliveries/evidence，再判定）；
  2. 生成 Agent 可读 typed conflict（复用 conflict envelope 机制 / `_post_receipt_conflict_
     envelope` 先例），由 Runner 投递给责任 Agent；
  3. Agent 自行决定修复方式与时机；deadline 不因冲突本身重置（§5 管理）。
  - 注：transport `send` 参数拒绝（如 `recipient is not allowed by frozen Profile`）本就是
    同步工具错误，Agent 直接可见——归入 B 但处置已是返还，无需改动行为，只补 `code` 字段。

### C — 检索证据警告扫描（阻塞 → record-only）

- 范围：`protocol_retrieval_gate.py:449-498` `_validate_response_quality` 的全部警告扫描
  （含 terminal 页截断告警；cursor 绑定不变式除外，见下）。
- 处置：扫描结果写入 retrieval observation evidence 与 receipt 的 `warnings_observed` 字段，
  不 raise、不阻断 handoff。检索证据完整性由 Examiner 独立判断（需求目标 4）。
- 边界：结构性证据不变量（cursor 绑定、artifact digest/身份、frozen query tuple 漂移——
  `protocol_retrieval_gate.py:811-890`）保护的是证据的确定性可验证性而非"完整性判断"，
  保持为返还 protocol 的 A/B 类反馈（它们本就经 `validate_ordinary_retrieval → _error` 以
  `ordinary_retrieval_incomplete` + detail 返还，不 kill run——仅需确认无 latch 路径）。

### I — 内部不变量 / 代码 bug（保留致命）

- 范围：`Runner is not prepared/started`（1459/2893/4405/4660）、`invalid Team Transport
  event`（4663/4684）、frozen-input write 不前进（266）、receipt wakeup 中不可归因于 Agent
  的内部状态（3139/3162/3188/3202 中不属于 Agent 可修复的部分）、`start_ledger.py` 自身
  一致性防护、`formal_runs.py` 合同装配。
- **自 A 类移入**（review High-3 修正）：dispatch receipt 结构性失败
  （`candidate_progress.py:807-825`、`runner.py:4197/4337`）、
  `candidate_platform_gate.py` 文件系统/状态守卫、accepted identity/semantic
  payload/artifact mutation（`acceptance.py:1777/1781/1914-1917`，经重开迁移作废后的
  重新注册除外——见 §3.A 注册侧联动）、model-state
  snapshot 绑定类（`acceptance.py:1965-2072`）。这些由 runtime adapter 或 Runner 内部状态
  产生，任何 Agent 行为都无法修复；保持 fail-fast（否则 adapter 故障会空转到 T3 兜底，
  账本终态从 platform-contract 退化为 collaboration/routing）。
- **不属于 I 类**（review New-B 修正）：`runner.py:4331`（candidate-progress-timeout）与
  `runner.py:4334`（redrive-exhausted）来自 deadline/redrive 机制本身，归 §5 兜底分层——
  T1 nudge / T2 自动 issue，最终仅 T3 latch。I 类致命集合不含这两个站点。
- 处置：保留 raise 与 `terminal_failure("runtime/infrastructure")`；reason_code 加前缀
  `internal-invariant:`，与 Agent 行为失败在账本证据上明确区分（修复归 developer，不耗
  Agent 侧修复预算）。

### H — Host/outer 动作校验（运行中，维持拒绝不维持 kill——无行为变更，显式归类防误改）

- 范围：outer input envelope / owner answer / issue resolution envelope（`runner.py:
  2893-3998`）、`start_ledger.py` 的 Host-API 守卫。
- 处置：维持 raise 给 Host 调用方（拒绝单条 outer 动作；run 继续）。本类不产生 run-kill。

### 处置汇总表

| 类 | 例证站点 | 旧处置 | 新处置 |
|---|---|---|---|
| S | runner.py 256-1199 | 启动失败 | 不变（+`startup-config:` 前缀） |
| A（同步） | acceptance.py dry-run/apply 合同、protocol_retrieval_mcp apply 请求路径 | 同步错误载荷（现状） | 保持通道 1，error 升级为 `{code, detail, remediation}` |
| A（异步） | runner.py 3259（细分表中 A 行） | latch → kill | 通道 2 Runtime 投递 typed 反馈 + post-complete 重开（§3.A）+ run 继续 |
| B | candidate_progress.py 600-604、transport_mcp.py 436-440、runner.py 4072/4117 | raise/latch → kill 或槽死锁 | observed-issue evidence + typed conflict + Agent 自修 |
| C | protocol_retrieval_gate.py 449-498（含 `result_status != "matched"` 与 recall incomplete 警告：未命中检索也可建 receipt，完整性由 Examiner 独立判定——需求目标 4） | raise（阻塞 handoff） | record-only（`warnings_observed`），Examiner 判定 |
| I | runner.py 1459/4663、4197/4337、candidate_platform_gate.py FS/状态守卫、acceptance.py mutation/snapshot 类、start_ledger.py | raise → kill | 不变（+`internal-invariant:` 前缀） |
| —（非 I） | runner.py 4331（timeout）/4334（redrive-exhausted） | latch → kill | T1 nudge / T2 自动 issue（§5），仅 T3 latch |
| H | runner.py 2893-3998 | raise 给 Host | 不变（非 kill 路径，显式归类） |

## 4. 反馈通道设计（全部复用既有机制）

三个通道，按"谁必须行动"选择；不新建传输。

### 通道 1：capability 错误载荷（同步，仅 Agent 主动 tool call 触发的 A/B 检查）

- 载体：既有 `capability_mcp.py` `{ok: False, error: …}` structuredContent + 审计
  （`evidence/capability-calls.jsonl`）。-32001 opaque 语义保持。
- 扩展：`error` 从纯文本升级为 `{code, detail, remediation?}`（code 即 reason_code；
  remediation 一句话，可选）。MCP 客户端会剥 error.data，故 code 必须出现在
  structuredContent 与 text content 双路径（现状已如此，保持）。
- 路由：自动到调用者 Agent，无需规则。
- **边界（review High-1）**：本通道是同步 tool-call 响应，不是推送通道。Runner drain/
  dispatch 循环中的异步失败（registration rejected、observed B 类违约）一律走通道 2。

### 通道 2：typed 反馈/conflict 投递（异步，Runner 观测到的 A/B 类）

- 载体：复用 formal candidate conflict envelope 与 `runner/candidate-gate` 直接 Runtime
  投递先例（`candidate_receipt_registered_notice`，runner.py:3152-3170）。异步 A 类
  （registration rejected）同样经此通道投递。
- 路由规则（唯一判定维度：缺陷载体的所有者）：
  - 候选工件本身缺陷（envelope/revision/digest/plan 预校验）→ **modeling**；
  - 响应/回执/handoff 行为缺陷（receipt/conflict envelope 违约、apply/handoff A 类）→
    **protocol**。
- 冲突文本必须 typed（code + detail），且不再依赖一次性回复槽语义（defect 11 教训：
  修复路径不得要求 Agent 先消费某个恰好已被占用的槽）。standalone-revision 接受
  （a9fac61）保持。

### 通道 3：协作 issue 升级（重复失败 / 跨角色）

- 载体：既有 issue ledger 与 `report_issue`（transport_mcp.py:215/1202）。
- 触发：同一 (class, code, responsible_agent) 反馈重复 N 次（profile 参数
  `feedback_escalation_repeat`，默认 3）仍无进展 → Runner 自动开 issue（等同现在 Host
  guidance 的自动化版本）。
- **deadline 暂停需显式接线（review High-4 修正）**：现状 issue pending 只是让
  `_check_formal_candidate_progress` / `_maybe_redrive_formal_candidate` 跳过检查
  （runner.py:3388-3400），**时钟并未暂停**——`FormalCandidateProgress.pause()/resume()`
  （candidate_progress.py:384-403）在全仓库没有调用点，issue pending 的整段墙钟时间仍计入
  `active_elapsed`。本设计在 issue 开启时调用 `progress.pause()`、解决时调用
  `progress.resume()`，使 owner 指引循环真正免于 deadline 压力（否则 issue 解决瞬间 T1
  立即触发，T1↔T2 乒乓）。

### 证据规范

- `validation-feedback`（A 类）：{class, code, responsible_agent, delivery_id, tool,
  detail, retry_allowed}。
- `observed-issue`（B 类）：{class, code, responsible_agent, original_delivery_id,
  original_text}——先持久化后判定，修复 defect 10 暴露的"致命文本未留存"问题。
- 两者仅进 run evidence JSONL，不进 StartLedger 事件流，不触发预算扣减（目标 6：
  记录是优化参考不是运行限制）。

## 5. 兜底超时设计（分层）

| 层 | 触发 | 动作 | 参数 |
|---|---|---|---|
| T1 nudge | candidate 通道无进展达到 `candidate_progress_timeout_seconds`（现 300s，语义从 kill 改为 nudge） | 向责任 Agent 投递催办/redrive 文本（复用 `redrive_text`） | redrive 次上限 1 → profile `candidate_redrive_limit`（默认 3） |
| T2 escalation | T1 额度用尽仍无进展 | Runner 自动开协作 issue（暂停 deadline，进入 owner 指引循环；等价现行 guidance 流程） | `feedback_escalation_repeat` 默认 3 |
| T3 hard fallback | active-clock 超过 `run_fallback_timeout_seconds` | `_latch_formal_candidate_failure("collaboration/routing", "run-fallback-timeout")` → 既有确定性清理 + 账本自闭合路径 | profile 新参数，默认 5400s（90 min）；**run 级 active clock（新记账，review High-4）**：自 `runner.start()` 成功起算，覆盖含"无 formal acceptance 候选"在内的整个 run；排除 issue pending 时段（依据 issue ledger 开/闭时间戳累加，独立于候选级 `active_elapsed` 实现——候选级 pause 机制在 `pending is None` 时是 no-op，覆盖不了 T3） |

- 保留致命的基础设施故障：LLM inactivity / runtime adapter failure
  （`_consume_runtime_failures` → `terminal_failure("runtime/infrastructure")`，
  runner.py:1438/1605）不属于校验，不在降级范围。
- 每次向责任 Agent 成功投递反馈/冲突/nudge 时，T3 的 active clock 不重置（防 Agent 用
  无效重试无限续命），但 T1/T2 正常循环进行。

## 6. 与 StartLedger / 终态分类合同的交互

- classification 集合不变：`_RETRYABLE = {runtime/infrastructure, platform-contract,
  collaboration/routing}` + `modeling-quality`（start_ledger.py:18, 420）。无需迁移。
- 旧 latch 终止的运行，新行为分三种终局：
  1. **Agent 自愈 → Agent 终态报告**：正常 settlement（completed/blocked 既有语义与
     `TERMINAL_REPORT_COMPLETE` 路径不变）。blocked 报告成为"校验失败但 Agent 判定无法
     修复"的合法出口——这正是合同第 1 条的意图。
  2. **T3 hard fallback**：`terminal_failure("collaboration/routing", False,
     terminal_evidence={reason: "run-fallback-timeout", nudges_sent, issues_opened,
     last_responsible_agent, feedback_counts})`。
  3. **S/I 类**：与现状相同（presemantic release / `runtime/infrastructure`），reason_code
     前缀 `startup-config:` / `internal-invariant:` 供事后归因。
- `terminal_failure classification is immutable`（start_ledger.py:442-443）与 budget 消耗
  逻辑不变；预期效果是 terminal_failure 事件总数显著下降（多数 run 走 Agent 终态报告）。
- `_latch_formal_candidate_failure` 保留但调用点白名单化（见验收标准 2）。

## 7. 测试迁移（约 60 处 raise 断言；18 个文件共约 110 处 pytest.raises）

原则：**tests may assert `raises` only for (a) 纯校验器、(b) S 类启动配置、(c) I 类内部
不变量 helper；run 级测试必须断言"反馈工件 + run 继续"。**

- 不变（约一半）：
  - 纯校验器单测：`validate_formal_candidate/receipt/conflict`、`ProtocolRetrievalGate`
    构造/receipt 构建（`test_protocol_retrieval_gate.py` 的 `AcceptanceContractError`
    断言——`_error` 载荷机制保留）、transport `send` 参数拒绝、acceptance 合同单测。
  - S 类：`test_model_routing.py` 凭据预检、profile/manifest 校验
    （`test_luna_max_model_manifest.py`）。
- 改写（run-kill 语义断言）：
  - `test_r23005_candidate_progress.py` timeout latch 系列（533-671）：改断言
    "T1 nudge 事件 + 未终止 + 后续合法候选仍被接受"；`timeout_latched` 语义仅剩 T3。
  - `test_r23003_revision_contract.py` / `test_r23003_incremental_contract.py` 中
    revision/digest 违约 kill 断言：改断言 observed-issue evidence + conflict 生成 +
    revision 门（严格更新、digest 不同）本身仍拒绝该投递（检查保留，处置变）。
  - runner 级 latch 断言（如 4072/4117 对应测试）：改断言反馈投递与 progress 开放。
- 新增守恒测试（meta-invariant，防回潮）：source 扫描断言 `_latch_formal_candidate_failure`
  调用点仅存在于白名单模块行集合（fallback-timeout / internal-invariant / startup），
  以及 `protocol_retrieval_gate._validate_response_quality` 无 raise 分支（I/C 边界固化）。
- defect 9/10/11 既有回归测试（3+5+5）保持通过，作为一般化的最小锚点。

## 8. 实施顺序（供后续实现需求引用；本设计不改产品代码）

1. C 类 record-only（最小、独立、直接对应 defect 9 哲学）。
2. B 类：observe/transport 拒绝点 → evidence + conflict（含"先持久化后判定"）。
3. A 类异步站点改通道 2 反馈（registration-rejected 细分表 + post-complete 重开迁移与
   注册侧联动成套实施）；A 类同步站点升级 error 载荷结构。turn-binding/platform-gate FS
   守卫/mutation 已归 I 类保持致命，不在本步改动。
4. 兜底分层 T1/T2/T3 + profile 参数。
5. 白名单守恒测试 + 既有测试改写。
每步独立可交付、全绿后进入下一步（遵守 L0：进入真实建模早、修复最窄失败层）。

## 9. 验收标准

1. `env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest
   modeling_team/tests -q` 全绿，总数不低于现状
   （938 passed / 1 skipped / 302 subtests，2026-08-19 plan review 实测基线）。
2. kill-path 白名单化成立：`_latch_formal_candidate_failure` 调用点仅剩 T3 fallback、
   I 类、S 类；守恒测试固化。
3. 注入式演练（fake adapter 单测）：defect 9/10/11 三场景在旧 kill 点现在分别产生
   (a) record-only 警告 + handoff 继续、(b) observed-issue + 后续真候选注册、
   (c) conflict 后 revision 可达——run 均不终止。
4. A/B 类反馈对责任 Agent 可读：capability 载荷含 code+detail；conflict 投递到达
   正确角色（路由规则 §4）。
5. 真实运行验收按配套测试计划 rounds 执行（需用户显式 start 授权）。
6. 账本兼容：classification 集合不变；fallback-timeout 终局产生完整
   terminal_evidence；Agent 终态报告路径行为不回退。
