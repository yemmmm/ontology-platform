# R2.3-009 Modeling Team 校验降级与 Agent 自修复 — 共享测试计划

- 日期：2026-08-19
- 状态：Plan（planner 产出，待 review）
- 需求：`docs/requirements/requirements-v2.3.md` R2.3-009
- 设计：`docs/delivery/design/2026-08-19-r2-3-009-gate-relaxation-design.md`
- 命令：`PYTHONPATH=backend:. backend/.venv/bin/python -m pytest modeling_team/tests -q`（仓库根执行）
- 已知环境项：`test_deepseek_codex_runtime.py` 7 例在 shell 带 `DEEPSEEK_API_KEY` 时失败，
  `env -u DEEPSEEK_API_KEY` 下 21/21 通过——与本需求无关，验证时统一以 `env -u` 运行。

## 轮次总览

| 轮 | 内容 | 执行者 |
|---|---|---|
| R1 | 静态守恒：kill-path 白名单 + C 类无 raise | developer 自测 / tester 复核 |
| R2 | C 类 record-only 行为（defect 9 一般化） | requirement_tester（独立） |
| R3 | B 类 observed-issue + typed conflict（defect 10/11 一般化） | requirement_tester |
| R4 | A 类 typed capability 反馈 + run 继续 | requirement_tester |
| R5 | 反馈可读性与路由（通道 1/2/3） | requirement_tester |
| R6 | 兜底分层 T1/T2/T3 + 参数 | requirement_tester |
| R7 | 账本与终态合同兼容 + 回归 | requirement_tester |
| R8 | 真实运行演练（需用户显式 start 授权） | 独立 Examiner |
| R9 | 收尾：全量绿 + 文档/状态同步 | requirement_tester |

## R1 静态守恒（meta-invariant）

1. **kill-path 白名单测试**：source 扫描 `modeling_team/runner.py`，断言
   `_latch_formal_candidate_failure(` 调用点行集合 ⊆ 白名单（由实现以声明式 registry
   定义：T3 fallback、I 类 internal-invariant、S 类 startup）。任何新增调用点使测试失败，
   强制开发者显式登记并说明类别。
2. **C 类无 raise**：断言 `protocol_retrieval_gate.py` `_validate_response_quality`
   代码中不存在 `raise`（AST 级或文本级扫描）。
3. **reason_code 前缀**：S 类站点带 `startup-config:`、I 类带 `internal-invariant:` 的
   smoke 断言（抽查代表性站点即可，不逐一枚举）。

## R2 C 类 record-only（defect 9 场景一般化）

前置：R1 通过。

1. 构造 terminal 页截断/低命中 retrieval observation，调用改造后的校验路径：
   - 断言无异常、无 handoff 阻断；
   - 断言 receipt/observation evidence 含 `warnings_observed` 记录（含原因码）。
2. 对照组：cursor 绑定/结构不变量破坏仍以 `ordinary_retrieval_incomplete` + detail
   返还 protocol Agent（既有行为不回退），run 不终止。
3. 回归：defect 9 既有回归测试保持通过。

## R3 B 类 observed-issue + conflict（defect 10/11 场景一般化）

1. 非 JSON / 非 candidate-shaped 初始投递：observed-issue evidence 记录（含原始文本）、
   冲突/nudge 不误杀；后续真候选注册成功（defect 10 回归保持）。
2. revision 非严格更新 / digest 复用：该投递仍被 revision 门拒绝（检查保留），但处置为
   observed-issue + typed conflict 给 modeling；progress 不进入终态；后续合格 revision 被接受。
3. 一次性回复槽被占用后的 standalone revision（defect 11 回归）+ 新增：reopen 拒绝
   （runner.py:4117 旧 latch 位）改为 typed 反馈，run 继续。
4. envelope-invalid（runner.py:4072 旧 latch 位）：typed conflict 投递给 modeling，
   evidence 先持久化后判定（断言 evidence 中存在原始投递文本，再存在判定事件）。

## R4 A 类 typed 反馈 + run 继续

1. **同步站点**（通道 1）：Agent 发起的 dry-run/apply 合同违约（`acceptance.py` `_error`
   路径）→ capability 载荷 `{ok: False, error: {code, detail, remediation}}` 随 tool call
   响应返还调用者；`validation-feedback` evidence 记录；run 继续。
2. **异步站点**（通道 2，review 修订）：registration rejected 且归因候选 plan 缺陷
   （`ProtocolRetrievalGateError`）→ Runtime typed 反馈投递给 **modeling**；progress 自
   `complete` 经 post-complete 重开迁移回 `awaiting_revision`；modeling 严格更新 revision
   重新注册成功——**且注册侧联动生效**（重开时 `_accepted_candidate_identity` 已作废，
   再注册不触发 `acceptance.py:1777` mutation 守卫，非 R2.3-003 requirement 同样走通）。
   replacement revision/digest 违约 → 反馈投递给 **protocol**。未经重开迁移的 identity
   mutation 仍致命（I 类，断言一处）。
3. **I 类守恒**（review 修订）：turn-binding missing（4197/4337）、dispatch receipt
   turn_id/mode 结构失败、`candidate_platform_gate` 文件系统/状态守卫、accepted identity
   mutation——均保持致命 fail-fast（断言 terminal_failure 分类，不产生 Agent 反馈循环）。
   **反例**：4331（candidate-progress-timeout）/4334（redrive-exhausted）不在 I 类白名单
   ——它们归 T1/T2，仅 T3 latch（与 R6.1 一致，防守恒测试与 T1 语义互斥）。
4. 重试不设代码上限：A 类连败 2 次后第 3 次仍收到同构反馈，而非 kill。
5. 反例守恒：S 类启动失败仍致命（1 例）。

## R5 反馈可读性与路由

1. 通道 1：MCP structuredContent 与 text content 双路径均含 `code`；-32001 审计行记录
   真实 code+detail（capability-calls.jsonl）。
2. 通道 2 路由：候选工件缺陷 → modeling 收到 conflict；receipt/handoff 行为缺陷 →
   protocol 收到 conflict（两个注入场景分别断言接收方）。
3. 通道 3：同一 (class, code, agent) 反馈重复 `feedback_escalation_repeat` 次后 Runner
   自动开 issue；issue 开启时 `progress.pause()` / 解决时 `resume()` 接线生效
   （断言详见 R6.2）。

## R6 兜底分层

1. T1：无进展达到 `candidate_progress_timeout_seconds` → nudge 事件投递、run 未终止；
   redrive 至 `candidate_redrive_limit`。
2. T2：T1 用尽 → 自动 issue 开启；**断言 `progress.pause()` 已接线**（issue 开启时
   elapsed 冻结、解决时 `resume()` 起新区间；issue pending 期间及解决后 T1 均不因
   pending 时段的墙钟时间触发——review 修订，防 T1↔T2 乒乓）。
3. T3：**run 级 active clock**（自 `runner.start()` 成功起算、覆盖无 formal acceptance
   的 run、按 issue ledger 开/闭时间戳排除 pending 时段）达到 `run_fallback_timeout_seconds`
   → latch collaboration/routing "run-fallback-timeout"；terminal_evidence 含
   {nudges_sent, issues_opened, last_responsible_agent, feedback_counts}。
4. 反馈投递不重置 T3 active clock（注入 2 次无效重试后断言 clock 不归零）。
5. profile 参数缺省值测试：三参数默认 3/3/5400s。

## R7 账本与终态合同兼容

1. Agent 自愈后终态报告（completed）走既有 settlement 路径，分类正确。
2. Agent 报告 blocked 的合法出口：settlement 记录 blocked、run 正常清理、无
   terminal_failure；cleanup 时补记 `terminal_settlement(outcome="agent_blocked")`。
3. T3 终局账本事件与 terminal_evidence 完整；classification 集合与
   `start_ledger.py:18/420` 一致（`_RETRYABLE` 不变）。
4. **预算退款（用户确认"自修复 run 不计预算"）**：agent_blocked 与 T3
   run-fallback-timeout 终局后可追加一次 `budget_refund`，`_start_cap` 回放 +1；退款
   不可变、每 run 至多一次、必须紧跟终局记录；agent_completed / I 类致命 / 其他失败
   分类不产生退款；strict-sequence replay 对含退款序列的重放校验通过。
5. 全量回归：`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m
   pytest modeling_team/tests -q` 通过数 ≥ 现状基线（938 passed / 1 skipped / 302 subtests，
   2026-08-19 plan review 实测）。

## R8 真实运行演练（独立验收；需用户显式授权 start 预算）

- 前置：R1–R7 全 PASS；用户授权后执行。
- 场景：注入类 defect 9/10/11 等价的自然触发条件（不修改产品代码，通过场景数据诱导：
  分页截断检索、barrier 期 prose、槽占用后重投），观察 Agent 自修闭环。
- 判定：run 以 Agent 终态报告或 T3 结束；全程无 validator kill；evidence 完整；
  Examiner 独立判定检索证据与模型质量（与产生证据的过程独立）。

## R9 收尾

1. 全量测试绿（命令同上）。
2. 文档同步：requirements-v2.3.md R2.3-009 状态、设计文档标注实现结果、delivery record。
3. 白名单守恒测试与分类说明入 `docs/reference/`（若实现产出声明式 registry）。
4. 遗留风险显式化（如 T1/T2/T3 参数需真实运行标定）。

## 完成门

- R1–R7 全 PASS + R8（若授权）完成判定；
- 守恒测试固化（防回潮）；
- 既有 defect 9/10/11 回归测试全部保持通过；
- 无测试文件/临时脚本遗留（清理规则）。

---

## 独立测试轮次记录（requirement_tester）

### 第 1 轮 — 2026-08-20（R1–R7 独立复核）

- 被测版本：`main` @ `9dfaec7`（实现区间 `8c78308..9dfaec7`，6 commits），worktree 干净（除本测试计划与需求文档的既有未提交修改）。
- 方法：先逐轮审读实现（runner.py / acceptance.py / candidate_progress.py / start_ledger.py / transport_mcp.py / protocol_retrieval_gate.py / contracts.py 的 diff 与现行代码），再以独立编写的临时测试文件
  `modeling_team/tests/test_r23009_independent_round1_tmp.py`（25 个用例，fake adapter / 单元级）执行验证；该文件按清理规则在轮次结束后删除，断言要点记录于此。
- 命令：`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest modeling_team/tests -q`（仓库根）。

#### R1 静态守恒 — PASS

- 独立 AST 扫描 `runner.py`：`_latch_formal_candidate_failure(` 共 8 个调用点，全部字面量参数；
  `classification:reason` 对与 `_FORMAL_FAILURE_LATCH_WHITELIST`（7 项，4756/4899 共用 `platform-contract:internal-invariant:turn-binding-missing`）双向精确相等，无未登记站点、无白名单残留项。
- 非 T3、非 runtime/infrastructure 的 5 个条目均带 `internal-invariant:` 前缀（runner.py:3417-3428、各调用点 3168/3192/3233/3291/4756/4899）。
- `protocol_retrieval_gate._validate_response_quality`（449-516）AST 与文本级均无 `raise`；返回 `warnings_observed` 列表。
- S 类站点不经 latch：启动失败走 `release_presemantic(..., "startup-config: startup failure before business delivery")`（runner.py:1633-1636），前缀存在；`contracts.py` 新参数校验仍抛 `TeamConfigurationError`（独立用例验证 `run_fallback_timeout_seconds: 0` 被拒）。

#### R2 C 类 record-only — PASS

- 独立用例：`result_status != matched` + `recall.completeness != complete` + `vector_index_missing` 警告同页出现时，
  `validate_ordinary_retrieval` 正常返回 receipt（链不阻断），`receipt["warnings_observed"]` 含三类警告字符串；
  且 `evidence/retrieval-quality-warnings.jsonl` 追加 `{event: warnings_observed, ...}`（acceptance.py:1957-1992）。
- 对照组：游标链结构违约（非 terminal cursor 链）仍以 `AcceptanceContractError(data={reason: "ordinary_retrieval_incomplete", code: "ordinary-retrieval-incomplete", detail})` typed 返还 protocol Agent，run 不终止。
- defect 9 既有回归（test_r23008_context_truncated_pagination.py 3 例）在全量中通过。

#### R3 B 类 observed-issue + typed conflict — PASS

- 非严格更新 revision（冲突后重发同 revision/digest 候选）：revision 门仍拒绝（progress 留在 `awaiting_revision`），
  但处置为 evidence + 反馈：`observed-issue`（code=revision-not-strictly-newer、responsible_agent=modeling、`original_text` 为原始投递字节）；
  `deliveries` evidence 中原始文本的序号先于判定事件（先持久化后判定，`_record_observed_issue` runner.py:3458-3476）；
  `candidate-conflict` 投递到达 modeling（notice 含 conflict_code/conflict_detail/remediation）；run 未 latch。
- 修复路径实证（defect 11 形态）：违约投递消耗了 conflict 的一次性回复槽后，合规 rev-2 只能 standalone 投递并被接受
  （identity 前进到 rev-2，无终态、无 latch）——standalone-revision 语义在独立用例中复现。
- reopen 拒绝（monkeypatch `reopen_formal_reply_slot` 抛 `RoutingError`）：`formal-reply-slot-reopen-rejected` observed-issue +
  `candidate-conflict` 投递给 **protocol**（责任方为回执行为方），run 继续。
- 注：字面同候选重发先触发 `revision-not-strictly-newer`（严格更新检查在前）；`revision-digest-reused` 经消息映射表单测覆盖（runner.py:3402-3408）。

#### R4 A 类 typed 反馈 + run 继续 — PASS

- 同步站点：`validate_modeling_receipt` 阶段非法 → `AcceptanceContractError.data = {code: modeling-receipt-stage-invalid, detail, remediation}`；
  通道 1 端到端：`RunnerCapabilityEndpoint.handle` 的 structuredContent 与 text content 双路径均含 code，`capability-calls.jsonl` 审计行 diagnostic 含真实 code（capability_mcp.py:676-701）。
- 异步路由表（`_classify_registration_rejection` runner.py:3600-3629）：`ordinary_retrieval_plan_invalid` → A/modeling；
  `replacement_revision_not_newer`/`replacement_digest_reused`/`replacement_payload_missing` → A/protocol；无 code 的 opaque（mutation/snapshot 类）→ None（I 类致命）。
- post-complete 重开 + 注册侧联动（非 R2.3-003 requirement，task=r2-3-005）：`_handle_registration_rejected` 后
  progress 迁回 `awaiting_revision`、`acceptance._accepted_candidate_identity` 作废（evidence `registration-rejected-reopened.acceptance_registration_invalidated=True`）、
  modeling 收到 typed conflict；随后 rev-2（严格更新、digest 不同）经**首次注册路径**注册成功，不触发 mutation 守卫。
- I 类守恒：未重开路径同 identity 换 payload → `accepted candidate semantic payload was mutated`（opaque、无 data → I 类处置）；turn-binding missing → latch `internal-invariant:turn-binding-missing` + `TERMINAL_FAILURE_PENDING_CLEANUP`。
- S 类反例：profile 参数校验启动期仍致命。
- 无代码重试上限：同一 A 类反馈连投 4 次，每次均产生第 4 次 typed 反馈（见 R5 用例），无 kill。

#### R5 反馈可读性与路由 — PASS

- 通道 2 路由两方向独立断言：候选工件缺陷 → modeling（R3/R4 用例）；回执行为缺陷（reopen 拒绝）→ protocol（R3 用例）。
- 通道 3：同一 (A, consumer-query-plan-invalid, modeling) 反馈第 3 次（默认 repeat=3）自动开 1 个 issue
  （evidence `issue-escalation.reason_code=repeated-validation-feedback`），第 4 次不再开；run 继续。
- pause/resume 接线（聚焦项 c，见下）：T2 issue 开启 → drain 处理 issue_report → `progress.paused=True`，
  pending 期间 `check_deadline()` 恒 False；经 `issue_control(pause)`（CAS `mark_issue_dispatch` 后 pause）与
  `issue_control(resume)`（resume dispatch 校验 mode=start、线程绑定稳定后 resume）后 `paused=False`，
  `pending.accepted_at == resume 时刻`（新区间），pending 时段（100→500s）对 `active_elapsed` 贡献为 0（独立用例数值断言）。

#### R6 兜底分层 — PASS

- T1：deadline miss 只 nudge（`_nudges_sent` 有界 ≤ `candidate_redrive_limit`，默认 3），多次超窗 drain 后无 latch。
- T2：redrive 用尽 → 自动开 1 个 cooperative issue（`_escalate_candidate_stall` 一次性守卫）。
- T3 run 级 active clock：无 formal candidate 的 run（`_candidate_progress=None`）同样被 T3 覆盖并 latch
  `collaboration/routing:run-fallback-timeout`；issue-pending 时段被扣除（独立用例：active=101s 断言）；
  反馈投递不重置 `_run_fallback_started`；`acceptance.is_settled=True` 后不再 latch；
  terminal_evidence/run-fallback-timeout evidence 含 {nudges_sent, issues_opened, last_responsible_agent, feedback_counts}。
- 参数缺省：3 / 3 / 5400s（runner 属性缺省 + `FormalCandidateProgress.redrive_limit` 缺省 + contracts 仅 formal profile 可配置并做范围校验）。

#### R7 账本与终态合同兼容 — PASS（含聚焦项 b，见下）

- `terminal_settlement(agent_blocked)` → `budget_refund` 一次、二次 False、不可变（settlement 后 `terminal_failure` 被拒 "immutable"）；
  新实例（strict replay）无需新授权即可 reserve+start 下一个 run（`_start_cap` 回放 +1）。
- T3 形状 terminal_failure（`{run_id, classification, mutation_state, reason}` 且 reason=run-fallback-timeout）→ 退款；
  `platform-contract` 分类、无 evidence 的 `collaboration/routing`、`agent_completed` settlement → 均不退款。
- 带 baseline_hash 的 legacy evidence strict replay 通过且不退款；非 strict 账本拒绝任何 terminal evidence（"terminal evidence requires strict sequence"）→ 永不退款，历史记账不变。
- classification 集合不变（`_RETRYABLE` start_ledger.py:18，terminal 校验 :427）。
- 全量回归（本人独立执行）：**970 passed / 1 skipped / 302 subtests passed**（46s），不低于计划基线 938/1/302，与开发方申报一致。

### 聚焦复核（主 agent 指定三项）

- **(a) acceptance 替换分支遮蔽 "identity was mutated" 守卫** — **非缺陷（设计符合），附一项清洁建议**。
  `register_accepted_candidate`（acceptance.py:1782-1785）泛化后，所有 differing-record 先入替换分支，
  原 1843-1844 的 `accepted candidate identity was mutated` 判定在 `== record` 路径内不可达（死代码）。
  可达性分析 + 独立用例证明无"未重开静默换 identity"路径：runner 仅在 observe_delivery 返回 "accepted" 时注册（runner.py:3281），
  differing record 必然来自 `awaiting_revision` 迁移（经 receipt_digest 绑定的 typed conflict 或 registration-rejection 重开），
  complete 态下的新候选投递被 observe_delivery 直接忽略（独立用例断言返回 None、identity 不变）；
  同 identity 换 payload 的 `semantic payload was mutated` 守卫仍存活且 opaque（I 类）。
  建议：后续迭代删除或注释 1843-1844 死分支，避免误导。
- **(b) `_validate_terminal_evidence` 的 T3 替代形状** — **通过，未发现缺陷**。
  替代形状精确匹配 `{run_id, classification=collaboration/routing, mutation_state=zero-mutation, reason=run-fallback-timeout}`；
  replay 中任何 terminal_evidence（非 None）仍过 `_validate_terminal_evidence`（start_ledger.py:714），
  非 fallback 又缺 baseline_hash 的形状因字段集不匹配被拒；含/不含 baseline_hash 的 strict replay 分别由
  `test_r7_legacy_baseline_evidence...` 与退款回放用例验证；非 strict 账本拒绝 evidence 且 `refund_budget` 恒 False（runner 侧 `_run_fallback_terminal_evidence` 对非 strict 返回 None，runner.py:3967-3978）。
- **(c) pause()/resume() 接线** — **通过，"已存在"的说法不成立但现状正确**。
  开发方称 `_handle_issue_events` 的 pause/resume "此前已存在"——实际本变更区间新增了三处调用：
  runner.py:4076（issue_report 且 Coordinator 投递成功后 pause）、:4200（`mark_issue_dispatch` CAS 成功后 pause）、
  :4220（resume dispatch 校验 mode=start、线程/候选绑定稳定后 resume）。顺序正确；pause 幂等（candidate_progress.py:387-394），
  多 issue 串行处理不会重复计时；issue-abort 路径不 resume（终态，无需恢复）。独立用例数值验证了 pending 时段排除。

### 缺陷清单

- 阻断级/严重级/中级：无。
- 低（清洁建议，不阻断验收）：acceptance.py:1843-1844 `identity was mutated` 死分支（见聚焦项 a）。

### 结论

- **R1–R7 全部 PASS**；独立全量 970/1/302 与开发方申报一致。
- R8（真实运行演练）未执行——未获用户 start 授权，按计划保留；R9 收尾归主 agent。
- 临时测试文件 `modeling_team/tests/test_r23009_independent_round1_tmp.py` 已在轮次结束后删除（清理规则）。

---

## R8 真实运行演练记录（2026-08-20，主 agent 执行；用户已授权三次 start）

预算授权：用户 2026-08-19 授权三次 start（R8 验证）。账本
`workspaces/modeling-runs/.r2-3-009-start-ledger.jsonl`；run 根目录
`workspaces/modeling-runs/<run-id>/`。

### start1（r23009-luna-20260820-start1）

- freeze 17:04:24Z，semantic_start 17:04:32；T3 兜底超时 terminal_failure
  （collaboration/routing，run-fallback-timeout）18:43:29，`budget_refund` 18:43:32。
- 语义层未到达验收；失败层为运行推进阻塞（未复现 defect 9/10/11 场景细节，见 run 根证据）。

### start2（r23009-luna-20260820-start2）

- freeze 18:47:34Z。**首次在 R2.3-009 活动运行上完成全部语义落地**：5 个 stage batch 全部
  apply_atomic 成功、SHACL validation conforms、reasoning consistent、3 条治理检索 query 全部
  matched、两个显式 unknown 保留。
- 自修闭环真实触发并通过：issue-1（apply_atomic `idempotency_conflict`）→ coordinator 暂停 →
  owner 经 FIFO 下发 guidance（mode-bound key：plan key 只服务 dry_run，apply 用 plan key +
  字面 `-apply` 后缀；lease 重取）→ 同 epoch/线程恢复 → 继续完成全部 5 stage 落地。
- 唯一失败层：验收 cq-001 轮 BLOCKED（runtime-infrastructure）——platform examiner 两次
  （首次 + 唯一一次同输入重试）耗尽 10 步推理上限（`runtime-budget`），source examiner 不受影响。
  无 Agent 终态 → T3 20:22:16 结算，`budget_refund` 20:22:20。
- 窄修复：`_PLATFORM_EXAMINER_MAX_INFERENCE_STEPS` 10→20 + 3 个回归测试
  （test_r23009_examiner_step_budget.py），commit `080f551`。

### start3（r23009-luna-20260820-start3）

- freeze 20:24:28Z（baseline 含 080f551）。两轮冻结基线 owner 答复经 FIFO 正常闭环：
  delivery-4（cross-release output meaning）与 delivery-7（B no-score behavior）均判定
  not-confirmed，以显式 unknown 保留进候选。
- 候选 `r23008-candidate-1`（digest 6a1fc934…）protocol 接受；5 stage 全部落地、session 完成。
- 新失败层（platform-contract）：ordinary-retrieval gate 在
  `bCurrentlyConsumesPublishedBehavior` 路径上观察到两条不同 frozen tuple
  （首次 limit/context_limit=1 与自修重跑 20）后 fail-closed（"changed its frozen query tuple"）。
  已观察记录不可移除 → Agent 侧结构性不可修复（违背 R2.3-009 自修目标）。
- issue-1（21:00:59，platform_repair）→ owner guidance 确认缺陷并指示保留证据、停止重试、
  以 blocked 收场；protocol `report_task_result` 被 Broker 拒绝（`missing_modeling_handoff`：
  terminal result requires terminal handoffs）→ Agent-blocked 终态同样被该关卡阻断，T3 是唯一结算。
- T3 22:02:33 结算（collaboration/routing），`budget_refund` 22:02:36。run 根
  TERMINAL_FAILURE_CLEANED；临时 admin key `r23009-start3-temp` 已撤销、key 文件已删除。
- 窄修复：frozen-tuple 冲突降级为 receipt warning（每条 tuple 组的链仍完整校验，
  最早完成链被绑定）+ 3 个回归测试，commit `57556ab`。

### R8 判定（截至 2026-08-20）

- **未通过（保持开放）**：三次 start 均未到达真实 cq-001 验收 verdict。两次 live 证据驱动的
  平台窄修复（080f551 examiner 步数预算；57556ab 检索 tuple 冲突）已合入并通过全量
  984 passed / 1 skipped / 302 subtests。
- 预算核算：3 次授权 start 全部以 T3 收场 → 3 条 `budget_refund`；净消耗 0。下一次 start
  需用户重新授权。
- 自修机制 live 证据（R8 判定项）：运行全程无 validator 直接 kill（终态均由 T3 兜底达成）；
  issue 暂停/恢复、FIFO owner 答复、evidence 完整性三次均成立。
- 实测暴露的遗留缺陷（记录待 R9 处置）：
  1. T3 terminal evidence 强制 `mutation_state: "zero-mutation"`，语义已落地时标签失实
     （runner.py `_run_fallback_terminal_evidence` + start_ledger.py:966/976 形状校验）。
  2. handoff 被阻时 Broker 拒绝 `report_task_result`（terminal requires handoffs），
     剥夺了「Agent 报告 blocked」这一更快的终态路径。
  3. acceptance.py:1843-1844 死分支（R7 复核已记录）。
  4. T1/T2/T3 时长参数未经真实运行标定（start3 实测 T3 在暂停排除后精确于 5400 活跃秒触发）。

### 用户决策记录（2026-08-20，方向已确认、实施暂缓）

- **放开 Agent 间沟通与上报限制**（处置遗留缺陷 2 的方向）：除需要隔离的 Examiner
  （不得随意向外询问信息，保持验收独立性）外，其余 Agent（modeling / protocol /
  coordinator）应可随时互相沟通与上报状态；唯一保留的约束是**终态提交
  （report_task_result 的 completed/blocked）必须在对应任务已到达完成或确定无法完成之后**，
  不再以"验收 handoff 未完成"为由拒绝 blocked 上报。
- 实施时机：用户明确"暂时不做修改"，待本轮三个问题（start1 超时根因、examiner 步数上限
  设计目的、本条沟通放开方案）讨论清楚后一并修改。
- 关联证据：start1 的 `invalid-standalone-conflict-quarantined`（protocol 冲突投递被隔离，
  modeling 未收到）；start3 的 `missing_modeling_handoff`（blocked 上报被拒）。

### 用户决策补录（2026-08-20 第二轮讨论）

- **examiner 推理步数护栏统一为 30，不区分角色**（取代 source/acceptance=3、platform=20
  的分角色标定；仍是防失控资源护栏，不是质量关卡）。
- **终态前置条件由角色自己判定**：角色自行确定自己的任务是否已到达完成或确定无法完成，
  无需 coordinator 或 Runner 代为判定。
- **正式候选通道保持类型化**（候选/回执/冲突仍走带校验的通道）；只放开普通沟通与状态上报。
- 问题 3（coordinator 终态结算节奏）用户未理解，待重新解释后决定——实施继续暂缓。

### 用户决策定稿与实施记录（2026-08-20 第三轮）

- **问题 3（coordinator 终态结算节奏）确定为方案 B**：保留"三个角色全部上报后
  coordinator 才能结算"的既有节奏。由于 blocked 现在始终可上报，不再存在角色
  因平台侧闸门而卡死无法上报、进而拖死结算的路径，故该项无需代码改动。
- 四项放开决策已一并实施（本批提交）：
  1. examiner 推理步数护栏统一为 30（`_EXAMINER_MAX_INFERENCE_STEPS`，全部角色，
     含重试子进程）；
  2. `blocked` 终态为角色自我声明：不再要求上游 terminal handoff、pending reply、
     或 Runtime 侧守卫（如 protocol 检索证据完整性）；`completed` 仍保留全部前置
     条件（handoff/依赖/reply 槽/守卫）；
  3. 正式候选通道保持类型化，但 receipt 之后 protocol→modeling 的非完全类型化
     standalone 消息不再隔离消失，作为普通对端消息投递并记录
     `invalid-standalone-conflict-delivered-as-ordinary` 证据（start1 死角的窄修复）；
  4. 结算节奏 B：无代码改动（coordinator 依赖建模/协议/验收三角色 handoff 的
     既有语义即为目标节奏）。
- 验证：`modeling_team/tests` 全量 986 passed / 1 skipped / 302 subtests
  （`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest
  modeling_team/tests -q`）。

## R8 第二批真实运行记录（2026-08-20，用户再次授权三次 start：start4-6）

### start4（r23009-luna-20260820-start4）

- 走到哪：语义全程落地（5 阶段 receipts、validation/reasoning/retrieval、session complete）；
  issue-1（apply 原子模式幂等键冲突）经 FIFO guidance 关闭；coordinator 成功构建 cq-001
  ticket draft 一次。
- 卡死层：平台合同 + Agent 行为。coordinator 解析自身 MCP 响应的脚本 bug
  （读取 `structuredContent.data`，实际响应在 `content[0].text`）后重试同一 draft 请求，
  被平台「already built」拒绝且无恢复路径（平台合同缺陷）；随后 coordinator 未上报
  blocked、静默放弃直至 T3（Agent 行为缺陷，与遗留缺陷「无唤醒机制」同类）。
- T3 04:10:21（collaboration/routing，run-fallback-timeout）；`budget_refund` 04:10:24，
  净消耗 0；临时 admin key 已吊销。
- 窄修复：同参数 delivery-bound draft 请求幂等重放——返回已保留的同一张不可变草稿，
  不同 revision 仍按 stale 拒绝（`acceptance.py`
  `coordinator_ticket_draft_from_delivery` + 回归测试改写），
  commit `ec04750`；全量 986 passed / 1 skipped / 302 subtests。

### start5（r23009-luna-20260820-start5）

- 走到哪：语义全程落地；两轮 frozen-baseline owner 问题（unknown-c-score-rating-continuity、
  unknown-c-score-quality-score-vs-rating-continuity）按「未确认 → 保留显式 unknown」答复；
  issue-1（同 start4 幂等键）经 guidance 关闭；handoff 投递、两张 acceptance ticket 发布、
  cq-002 Examiner 对启动。
- 卡死层：平台合同 + Agent 行为（复合）。
  1. **round 顺序守卫**：coordinator 先发布了 cq-002 的 ticket（round 先创建），acceptance
     先启动 cq-001 的 Examiner 被平台 `prior_round_cleanup_required` 拒绝；经 issue-2
     guidance 指示按发布顺序先结算 cq-002 后恢复。
  2. **Examiner 报告合同**：两个 Examiner 的唯一一次提交均被拒——source examiner 以
     「证据不足」结论提交了空 `evidence_refs`（合同要求至少一个 locator）；platform
     examiner 以 `{}` 调用 `query_semantic_context` 被 `read-scope-denied` 拒绝后以零次
     成功调用提交空 `evidence_refs` 报告。子进程单回合设计下无第二次提交机会。
  3. **无唤醒机制（致死层）**：watchdog 于 04:52:55 记录 child-timeout 后，持久
     Acceptance 角色（04:43:34 结束回合「awaiting terminal reports」）没有任何唤醒路径，
     run 死锁直至 T3。
- T3（collaboration/routing，run-fallback-timeout）；`budget_refund` 随后入账，净消耗 0；
  临时 admin key 已吊销（key id 24c1739c-2c18-40d3-8d24-308ce5b28773）。
- 窄修复（T3 后、start6 前实施）：
  1. **examiner-terminal 唤醒**（commit `e695a11`）：carrier 在报告入账/基础设施失败
     记录时排队 terminal 事件，Host drain 循环向 Acceptance 投递一条机械通知
     （round/kind/outcome/digest，无业务语义）；issue pending 时事件保留待恢复后投递；
     Acceptance 已结算或无事件时不投递。
  2. **Examiner 指令补强**（同 commit）：source/platform examiner instructions 明确
     「报告的 `evidence_refs` 不得为空；证据不足/不可用结论仍须引用实际检视位置；
     平台 Examiner 零成功调用不得直接判 unavailable，须先按检索规则重发正确查询」。
  - 新增回归测试 `test_r23009_examiner_terminal_wake.py`（5 项）；全量 991 passed /
    1 skipped / 302 subtests。
- 遗留（记录待处置）：平台 Examiner「全部调用失败」仍无合法报告形状（指令层要求至少
  一次成功调用是缓解，非合同解）；round 发布顺序守卫依赖 coordinator 按 question 顺序
  发布 ticket（Agent 行为，未改平台）。

### start6（r23009-luna-20260820-start6）

- 走到哪：本批最深——第一版候选（r23008-candidate-1）收据被接受并于 06:08 **已应用到
  平台**（revision-1 mutation 生效）；两个 frozen-baseline owner 问题按「未确认 → 保留
  显式 unknown」答复；issue-1（protocol 抄错 Project ID 尾部）／issue-2（apply 幂等键）
  经 FIFO guidance 关闭；issue-3：受治理检索发现已接受候选**不含任何 consumer_query
  检索计划项**，经 guidance 由 Modeling 补发修订候选 r23008-candidate-2（delivery-13）。
- 卡死层：**平台合同**（issue-4，本轮致死层）。收据被接受后（progress state complete），
  唯一能重开修订的载体是「带类型字段的冲突包」（original_delivery_id/receipt_digest/
  workspace_version/mutation_state），而 `protocol_build_candidate_conflict` 只在
  R2.3-003 分支构造该形状——R2.3-009 生成六字段简装冲突，被通道按 complete-state 规则
  丢弃（standalone 与 reply-to 两种投递形态均不可达）。对 delivery-13 的 receipt/conflict
  能力调用均以 `typed candidate delivery_id is foreign or stale` 拒绝（通道仍绑定
  delivery-10）。Agent 行为正确：发现缺陷、上报、按指引补发修订，均无可指摘。
- 收尾：owner 经 issue-4 guidance 裁定平台合同缺口、指示各角色 blocked 收尾；
  protocol/modeling 报告 blocked；**acceptance 被终端守卫禁止报告 blocked**
  （仅 completed 可终止，见 runner `_terminal_report_guard`），「全员终态」不可达，
  唯自动出路为 T3。owner 随后以 FIFO `stop` 结束运行（07:1x），清理完成。
- 预算：`semantic_start` 06:01:52 已消耗；owner-stop 路径因 `terminal_results` 需全员
  报告才赋值，结算/退款未自动入账。经用户决定（2026-08-20）：**记为消耗**，本批三次
  授权净消耗 1。临时 admin key 已吊销（key id 77893bea-2414-4abc-9c61-a6d49a4fc62e）。
- 窄修复（本轮后实施）：commit `02d1241`——R2.3-008/009 下，候选完全不含 consumer_query
  项时，收据阶段即以结构化 `consumer_query_plan_invalid` 诊断拒绝（与 start10 非法
  required_paths 同路径），使已验证的「冲突→修订」循环发生在任何平台 mutation 之前；
  R2.3-005 的 planless 候选合同保持不变。新增回归测试 1 项，全量 992 passed / 1 skipped /
  302 subtests。
- 遗留（记录待处置）：
  1. **收据接受后的修订通道**：R2.3-009 无合法 post-receipt revision 载体（003 类型包
     语义为 pre-mutation zero-mutation，不适用于已应用 revision-1 的新建 scope 场景），
     需要一次正式合同设计，不能窄修。
  2. **acceptance 无法报告 blocked**：不可修复 run 只能靠 T3（90 分钟活跃时间）退出，
     本批三轮均因此拉长收尾；owner-stop 可提前结束但结算/退款不自动入账（本次按用户
     决定记为消耗）。
  3. revision-1 已应用且无 revision-2；scope 清理证据见 run root cleanup 记录。

## R9 第三批授权实跑记录（starts 7-9，2026-08-20）

T0 规则（AGENTS.md `40c4ac4`）落地后，用户授权三次新启动。本批前置代码：
`019baec`（R2.3-008/009 允许六字段简装 post-receipt 冲突重开修订；acceptance/coordinator
可自报 blocked）。

### start7（r23009-luna-20260820-start7）
- 走到：候选 delivery-11 / receipt delivery-12 / 交接 delivery-13、14；5 批 dry+apply 全部落库
  （apply key 由 Agent 自行推导 `-apply` 后缀，花了一轮 issue 指导）。
- 死因：**运行基础设施**——runner 在「交接已建、首轮未开」时序下运行结算就绪检查，
  `rounds[0]` 空列表索引崩溃，整 run teardown。ledger：terminal_failure
  (runtime/infrastructure)，按规则不退款。
- 窄修复：`820b362`——`_settlement_prerequisites_ready` 空轮次返回 False + 回归测试。
- 过程缺陷（自记）：start8 未先落 key 约定的持久修复，导致同类 issue 复发。

### start8（r23009-luna-20260820-start8）
- 走到：模型 5 阶段全部落库（live version 81959f4d…）；验收交接 delivery-9/10；cq-001
  验收轮启动，source Examiner 正常报告；**平台 Examiner 子进程两次整 600s child-timeout**
  （09:06:27、09:16:40），verdict BLOCKED(runtime-infrastructure)；运行空转至 T3
  （10:08）terminal_failure (collaboration/routing, run-fallback-timeout) → 自动退款。
- 子进程超时根因当时证据不足：child-session 随清理销毁，仅存摘要。
- 本轮后窄修复：`130ea66`——translate 工具直接输出 dry/apply 双 key + `-vN` 重试规则
  （key_convention 字段 + 协议说明书同步），start9 验证不再复发。

### start9（r23009-luna-20260820-start9）
- 走到：三轮业务澄清（版本绑定→latest published Version 2、无分数行为→显式 unknown、
  版本连续性→显式 unknown）；候选一次通过；**5 批 dry+apply 零 key 冲突**（130ea66 生效）；
  validation/reasoning 通过；受治理检索两度被 bounded execution 截断（issue-1/issue-2，
  3 页/链 × ~75s/页 > ~600s 窗口），经实测定位为「翻页尺寸 limit=20 导致链长」而非平台
  故障，guidance 指示 limit=60 单页终止（实测 40/45/46 行单页 10s）；receipt 注册、
  交接 delivery、cq-001 启动；source Examiner 报告；**平台 Examiner 又两次整 600s
  child-timeout**（11:24:16、11:34:30）→ verdict BLOCKED → 空转至 T3（12:07）
  terminal_failure (collaboration/routing) → 自动退款。
- 平台 Examiner 600s 根因（跨 start8/9 四次复现，平台端点全程健康）：每步大上下文页 +
  模型回合 ~30-75s，20 步合法工作量 > 600s 墙；非挂死。
- 本轮后窄修复：`282ab8f`——examiner ticket 模板 timeout 600→1800s（注释含证据）。
- 预算：本批三次授权（7-9）全部消耗；start7 不退款、start8/9 自动退款；临时 admin key
  均已吊销（start8: 733518c7…；start9: 3024f77c…），/tmp 目录已清理。

### 本批逐轮对比
| 轮次 | 走到哪 | 死因 |
|---|---|---|
| start7 | 5 批全部落库、交接完成 | 运行基础设施（runner 空轮次索引崩溃） |
| start8 | 模型落库+交接+cq-001 验收轮 | 运行基础设施（平台 Examiner 600s 超时×2，空转至 T3） |
| start9 | 落库零冲突+检索 receipt+交接+cq-001 验收轮 | 运行基础设施（平台 Examiner 600s 超时×2 复现，空转至 T3） |

### start10（r23009-luna-20260821-start10，本批第 4 次授权第 1 轮）
- 走到：候选交接后协调者子串探测 ALL_TOOLS 即放弃，未开验收轮。
- 死因：**协作路由**——codex 0.148 把超过 64 字符的 MCP 工具名重命名
  （`<截断名>_<sha1>`）；`coordinator_build_acceptance_ticket_draft(_from_delivery)`
  模型可见名 80/94 字符被重命名，start9 能碰巧调用、start10 探测失败即放弃；
  空转至 T3 terminal_failure (collaboration/routing, run-fallback-timeout) → 自动退款。
- 本轮后窄修复：`ee06e78`——两个操作改名 `coordinator_ticket_draft(_from_delivery)`
  （48/62 字符）+ 契约测试 `test_capability_tool_names.py` 锁定全部操作 ≤64 字符。
- 临时 admin key 已吊销。

### start11（r23009-luna-20260821-start11，本批第 4 次授权第 2 轮）
- 走到：**历次最深**——业务澄清、候选 receipt、stage 交接、coordinator 两次
  ticket 草稿+发布（ee06e78 改名生效）、cq-001 验收轮启动；source Examiner 报告正常；
  平台 Examiner attempt-0 整 600s child-timeout，attempt-1 同输入重试 43s 完成回合但
  两次 `submit_examiner_report` 均被 bare `report-rejected` 拒绝（真实原因被通用
  except 吞掉）；acceptance 按 attempt 预算规则提交 BLOCKED verdict（02:36:35 持久成功）；
  随后 `acceptance_get_verdict` 误报 "invalidated by model-state drift" 拒读、
  `acceptance_verdict_route` 因 text 非规范 JSON 被拒（Agent 侧合同违规，prompt 已写明
  要求 canonical JSON）；issue-1 上报，owner guidance 裁定平台缺陷、blocked 关闭；
  四角色 terminal report 全部受理（02:39:4x），但 acceptance 载体未 settle、runner 无法
  进入结算播报，空转至 5400s run-fallback-timeout（02:57）terminal_failure
  (collaboration/routing) → 自动退款；zero-mutation。
- 死因分层：**平台合同**（verdict 可读性缺陷为主）+ Agent 侧路由 text 违规（次要）。
- 平台 Examiner 600s 复现一次（`282ab8f` 的 1800s 模板修复为何未覆盖 attempt-0 待
  start12 观察；attempt-1 43s 完成说明不是必然超时）。
- 本轮后窄修复：`9d2b2c3`——(1) `get_verdict`/`coordinator_get_verdict` 只在轮次真实
  `state_invalidated` 时拒读（`verdict_usable` 不再被误当漂移信号，BLOCKED/FAIL
  verdict 持久即可读）；(2) ReportSink 通用异常分支保留验证器异常类型+消息，不再输出
  bare `report-rejected`。回归测试：BLOCKED verdict 双读+漂移后仍拒读、sink detail 保留。
- 临时 admin key `r23009-batch4-start11-admin`（2cd63bea-b2ad…）已吊销。

### start12（r23009-luna-20260821-start12，本批第 4 次授权第 3 轮）
- 走到：模型阶段正常推进，modeling 就版本冲突（Version 1 `quality_score` vs
  latest Version 2 `quality_rating`）通过 `ready_for_acceptance` 协调频道发出澄清
  （coordination-1）；协调者接收、复述问题后结束回合，**未通过正式频道登记 owner
  question**（03:10:27 后全线静默）；空转至 5400s run-fallback-timeout（04:40:01）
  terminal_failure (collaboration/routing, zero-mutation) → 自动退款。
- 死因分层：**协作路由**——协调者把协调频道澄清当聊天处理，未走正式提问通道；
  且「切片指派→首个候选」窗口内无任何进度 owner：FIFO `user` 动作需要已登记的
  外层提问、issue 通道无活跃 issue、候选进度通道未开——start10 与 start12 均死在
  该空窗，唯一兜底是 5400s 全程超时，整轮只为一次可被一条询问救回的停滞烧掉。
- Agent 自身行为：modeling 正确发起澄清；协调者违规（收到的澄清必须登记为正式
  owner question 或直接作答，不得搁置）。
- 本轮后窄修复：`6c811e1`——runner 新增协作空转询问：当正式运行中无角色回合、
  无任何通知输出达 `idle_inquiry_seconds`（默认 300s），且无候选/验收子进程/协作
  issue 在途时，向协调者发送一条有界（默认 2 次）`idle-inquiry` delivery 并落
  evidence；复用现有 `last_output_monotonic` 活动时钟与 0.1s drain 循环，无新增
  外部脚本。测试 `test_cooperative_idle_inquiry.py`（5 例）+ 全量 1007 通过。
- 临时 admin key `r23009-batch4-start12-admin` 已吊销。

### 第 4 批逐轮对比
| 轮次 | 走到哪 | 死因 |
|---|---|---|
| start10 | 候选交接完成 | 协作路由（codex 64 字符工具名重命名，协调者探测失败即放弃，空转至 T3） |
| start11 | 历次最深：cq-001 验收轮、BLOCKED verdict 持久、四角色终报 | 平台合同（verdict 误报漂移拒读致无法结算）+ Agent 路由 text 违规 |
| start12 | 模型推进至版本冲突澄清 | 协作路由（协调者未登记正式提问；指派→首候选窗口无进度 owner，静默 90 分钟至 T3） |

### start13（r23009-luna-20260821-start13，第 5 批授权第 1 轮）
- 走到：业务澄清（owner 作答生效）、候选推进、协议校验循环、交接、cq-001 验收轮
  启动；source Examiner 正常；平台 Examiner 回合完成但 3 次
  `submit_examiner_report` 均收到无 detail、无 attempts 计账的 bare
  `report-rejected`，子进程无报告终局；issue-1 上报，owner guidance 裁定平台缺陷、
  按终报关闭；随后 acceptance BLOCKED verdict 提交也被同类 bare 拒绝（issue-2，
  owner 裁定走终报通道关闭）；四角色终报受理后空转至 5400s run-fallback-timeout
  terminal_failure → 自动退款；zero-mutation。
- 死因分层：**平台合同**——ReportSink 的 submit 回调（Host 侧 handle 查找、信封
  校验、receipt 绑定、持久化）抛出的异常逃逸到 `_serve` 最外层通用 except，被回答
  为 bare `report-rejected`，真实原因（scoped proxy receipt scope binding drifted
  家族）既不给子进程纠错线索、也不进 attempts 计账。start11 的 9d2b2c3 只修了验证器
  异常分支，submit 回调分支是同一缺陷族的孪生路径。
- Agent 自身行为：Examiner 报告 payload 形状有效、digest 64-hex（旁证排除转写
  错误）；其余角色均正确。
- 本轮后窄修复：`ea9ea16`——`_serve` 的 submit 分支独立 try/except，把回调异常
  以 `report-submit-rejected` + `type: message` detail + attempts_remaining 回给子
  进程并计入 `_rejections`。回归测试
  `test_report_sink_preserves_submit_callback_rejection_detail`；全量 1008 通过。
- 运行期操作：issue-1 首次 FIFO 投递因缺尾随换行被拒（`invalid_outer_input`），
  补换行重发成功。
- 临时 admin key `r23009-batch5-start13-admin` 已吊销。

### start14（r23009-luna-20260821-start14，第 5 批授权第 2 轮）
- 走到：建模角色开工、发出业务澄清问题；owner（操作方）在启动后未盯提问窗口，
  问题始终无人作答；空闲询问机制按上限向协调者发 2 次 `idle-inquiry`（行为正确，
  协调者不得编造业务答案）；Agent 保留未知项继续有限工作；空转至 5400s
  run-fallback-timeout terminal_failure → 自动退款。
- 死因分层：**协作路由**（owner 侧回答缺位，操作层过失，非 Agent、非平台缺陷）。
- Agent 自身行为：全部正确。
- 本轮后窄修复：无代码修复；操作修复为「启动后立即盯提问窗口」（start15 生效，
  开场提问 2 分钟内作答）。另发现 FIFO 半行缓冲陷阱：未带尾随换行的 JSON 会滞留
  缓冲并与下一条拼接成非法行，两条消息同时静默丢失（start15 首条回答即中招，
  补发成功）；已写入会话记忆与下轮操作规程。
- 临时 admin key `r23009-batch5-start14-admin` 已吊销。

### start15（r23009-luna-20260821-start15，第 5 批授权第 3 轮）
- 走到：**历次最深**——开场提问 2 分钟内 owner 作答（owner-answer-delivery-1 生效，
  `outer-user.jsonl` 落档）；建模推进至候选通过协议校验（delivery-7/8，receipt
  屏障前）；翻译环节发现建模质量问题：候选把 no-score 未知项编码为未声明实体引用
  `unknown-no-score`（unbound_relation_object，zero-mutation 正确拒绝）；issue-1
  上报，owner guidance 裁定改为契约显式未知机制表达并要求完整修订重驱动；此后
  protocol（"等建模修订候选"）与 modeling（"owner 回答确认未知项、无需修订，等
  protocol 放行"）对峙，协调者未仲裁、idle-inquiry 预算（2 次）已在等待 owner
  回答阶段耗尽；11:02Z 起全线静默至 5400s run-fallback-timeout（12:19:20Z）
  terminal_failure → 自动退款。
- 死因分层：**协作路由**——issue 裁定只送达 reporter（protocol），建模角色未收到
  裁定文本、按 owner 回答字面理解为"无需修订"；protocol 在终局消息里表达对修订
  候选的期待而未向 modeling 发 RuntimeDelivery；协调者 resume 后不再跟进。层内
  三因叠加：裁定分发面窄、角色间无请求传递、仲裁缺位。
- 平台侧新证据：`ea9ea16` 的 sink detail 修复在本轮装载的代码中未再出现 bare
  `report-rejected`（本轮未进入验收轮，未触发该路径，属无反例而非验证）。
- Agent 自身行为：modeling 把未知项编码为未声明实体是**建模质量**缺陷（issue-1
  根因，owner 已裁定修复路径）；死锁阶段的角色行为是理解分歧+路由缺失，非违规
  罢工。
- 运行期操作：FIFO 半行拼接陷阱实测确认（start15 首条 owner 回答丢失即为该机制，
  补发成功）；`status` 探测确认缓冲清洁后重发策略有效。
- 本轮后窄修复：无代码修复（死因为协作路由，候选修复方向见下）；临时 admin key
  `r23009-batch5-start15-admin`（d661ea1b-1863…）已吊销。

### 第 5 批逐轮对比
| 轮次 | 走到哪 | 死因 |
|---|---|---|
| start13 | 候选+交接+cq-001 验收轮，平台 Examiner 3 次报告被 bare 拒绝 | 平台合同（ReportSink submit 回调异常逃逸为无 detail 拒绝，ea9ea16 修复） |
| start14 | 建模开工、提问后等待 owner 回答 | 协作路由（owner 侧未盯提问窗口，回答缺位至超时；操作层过失） |
| start15 | 历次最深：owner 作答生效、候选过协议校验、翻译拒绝未声明实体、issue 裁定下达 | 协作路由（裁定只达 reporter、protocol/modeling 对峙、协调者不仲裁、idle 预算已尽） |

第 5 批候选窄修复方向（供下批授权前评估，未实施）：issue 裁定 resume 时同步向
候选 owner 角色（modeling）投递裁定摘要 delivery；idle-inquiry 预算在 owner 回答
落地后重置。
