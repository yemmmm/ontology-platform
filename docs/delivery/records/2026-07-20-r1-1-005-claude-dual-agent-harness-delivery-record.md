# R1.1-005 Claude Code 双主 Agent 建模交互评测 Harness Delivery Record

- Requirement source: `docs/requirements/requirements-v1.1.md` R1.1-005
- Status: completed
- Started: 2026-07-20T22:38:22+08:00
- Last updated: 2026-07-20T23:31:33+08:00
- Design: `docs/delivery/designs/2026-07-20-r1-1-005-claude-dual-agent-harness-design.md`
- Shared test plan: `docs/delivery/test-plans/2026-07-20-r1-1-005-claude-dual-agent-harness-test-plan.md`
- Delivery baseline: work started at `d2edd27`; concurrent unrelated `59b1554 Sync Claude repository
  guidelines` became HEAD before closure and is preserved as the final parent
- Delivery commit: this delivery's scoped commit (`Implement Claude dual-agent modeling harness`)

## Confirmed contract

- Current behavior: repo-local Harness 只把一个 Codex 主 session 绑定到一个 run；主 Agent 同时承担
  用户交互、建模编排和平台进度，不能观察两个独立主 Agent 的真实多轮问答与审批。
- Target behavior: `simulated-user` 和 `ontology-modeling-agent` 分别使用独立顶层 Claude Code
  session，并通过 repo-local mailbox 持续通信；建模主 Agent 再调用抽取、分析和评审 subagent。Harness 将两个
  主 session、消息、subagent、阶段和平台稳定 ID 关联到同一评测 run。
- In scope: Claude Code 项目级 Agent/Hook 配置、跨 session Harness 身份和事件模型、双 session
  激活/恢复、repo-local mailbox 与 Runtime 任务事件、建模角色说明、自动化测试、真实 CLI/Hook
  可行性验证及文档。
- Non-goals: 平台托管 Agent Runtime、通用编排引擎、前端页面、backend/API/schema 变更、生产人工
  审批替代、对 Agent 权限做完整安全沙箱加固。
- Acceptance summary: 两个独立 Claude session 可绑定同一 run；模拟用户与建模 Agent 的消息方向和
  审批可追踪；建模 Agent 能调用三类 subagent；平台 Execution Event 仍是阶段权威；原 Codex Harness
  与 42 项现有 handoff/Harness 回归不退化；独立测试 PASS。
- Refinement: 用户已确认“双主 Agent：用户模拟主 Agent ↔ 建模主 Agent；建模主 Agent → 抽取、
  分析 subagent”的方案并要求直接实现，且明确暂不重点考虑 Agent 权限问题。权限只保留不把模拟
  审批冒充真人审批、不改变平台权威边界等基本约束。

## Timeline

### 2026-07-20T22:38:22+08:00 — source and current-state audit — user and main agent

- Context: 用户纠正了单主 Agent 方案无法模拟真实用户与建模 Agent 互动，并确认采用两个独立主
  session 的 Agent Team 方案。
- Action/decision: 新增 R1.1-005，而不回写已经关闭且明确排除 Claude Runtime 适配器的 R1.1-002
  历史范围。复用 R1.1-002 的平台工作流和 R1.1-003 的可靠建模产物交接。
- Evidence: `docs/requirements/requirements-v1.1.md` R1.1-002；`.codex/hooks/modeling_harness.py`；
  `.codex/tests/test_modeling_harness.py`；本机 `claude --version` 为 `2.1.153`；现有 Harness/handoff
  自动化本轮审计前为 `42 tests OK`。
- Outcome/next step: 进行 Claude Agent Teams、嵌套 subagent、Hook/摘要子进程和跨 session 身份的
  最小风险探针，再冻结设计和共享测试计划。

### 2026-07-20T22:43:00+08:00 — risk probes and contract freeze — main agent

- Probe 1, summary isolation: 在父 Claude Code 环境中用 `CLAUDECODE=1 claude -p --bare
  --tools '' --no-session-persistence --output-format json` 成功启动独立无工具摘要 session 并返回
  `OK`。结论：Hook 可使用隔离的 Claude 摘要进程，但仍需严格 schema、环境裁剪、超时和游标失败
  关闭。
- Probe 2, installed runtime: 本机 Claude Code 2.1.153 在 `-p` 模式把带名字的 Agent 调用记录为
  `task_type=local_agent`，未形成独立 teammate session，且嵌套调用未完成。结论：不能把该行为
  宣称为双主 Agent。
- Probe 3, current upstream CLI: 临时运行 Claude Code 2.1.215，建模 Agent 成功调用 extraction
  worker 并返回 `EXTRACTOR_OK`；两级调用仍均明确记录为 `task_type=local_agent`。结论：嵌套
  subagent 可用；双主交互采用两个由操作者显式启动和激活的顶层 session，共享 run ID，不依赖
  非交互 Agent 调用隐式创建 teammate。
- Decision: 冻结 R1.1-005 合同。Harness 兼容原 Codex 单参与者模式，同时新增 Claude 双参与者
  模式；模拟审批只能是 `agent_reported` 且带 `simulated=true`；平台执行事件保持阶段权威。
- Outcome/next step: 进入独立计划评审，未 PASS 前不修改 Harness 产品实现。

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |
| 1 — FAIL | Critical: 两个任意顶层 session 不能用原生 `SendMessage`；High: checkpoint 可被无身份 CLI 绕过、真实运行门禁可被 blocker 替代、参与者替换语义缺失；另有摘要 envelope、Agent/Task alias 和失败 Hook 问题 | 全部接受。保持两个对等顶层 session，新增 Hook 授权的 repo-local mailbox；checkpoint 复用一次性操作回执；新增 participant epoch/显式替换；真实双 session 改为关闭硬门禁；冻结 Claude structured-output envelope 和失败事件 | 独立 `plan_reviewer` 对需求、设计、测试计划及当前 runner 的 Round 1 报告 | 需求、设计和测试计划已修订；必须 Round 2 PASS 后才开发 |
| 2 — PASS | Round 1 Critical/High 全部核销；Medium 建议唯一 `operation_id` 与说明 poll 本机保密边界；Low 提醒 TeammateIdle、Stop 与 prompt 描述 | 接受全部 Medium/Low：操作回执键改为 `(run_id, operation_id)` 并绑定完整 fingerprint/session/role/epoch；poll 明确只读且不提供本机恶意进程隔离；真实双 session 仍是关闭硬门禁 | 独立 `plan_reviewer` Round 2 报告 | 设计与测试计划已补强，允许进入开发 |

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |
| 1 | Baseline `d2edd27`; reviewed R1.1-005 design Round 2 PASS | Developer implemented Harness v2 dual participants/epoch/replacement, Hook-authorized mailbox and checkpoint mutations, Claude lifecycle events and structured-output summarizer while retaining legacy Codex; added Claude settings, five Agent definitions and runbook | Main-agent stable file-set digest `2eda250b4d375401cb7dcd22bcc61c3c03066a2cee94807ef872e8c4e5bd5ea4`; independent pre-handoff rerun `Ran 50 tests in 13.793s`, `OK` | `DEVEL_READY`; no backend/frontend or pre-existing semantic-context files touched; hand off to independent tester |
| 2 | Independent Round 1 real-runtime run `claude-e2e-5565db8920ea6e68` | Defect: Claude Code 2.1.215 rejects the checked-in Draft 2020-12 `$schema` URI passed verbatim through `--json-schema`; real summarizer cannot return `structured_output`. Diagnostic removal of `$schema` passes local validation | Dual top-level session IDs `6342fd79...` and `2d927f99...`, mailbox, simulated approval, ack and nested extractor all passed; summary command failed with `no schema with key or ref` | Return to developer for minimal Claude schema adapter and regression test; Round 1 remains FAIL. The earlier digest was captured while developer final edits were still arriving and is not reused as the repair baseline |
| 3 | Round 1 defect reproduction | Claude adapter now copies the shared schema and removes only top-level `$schema` for the Claude CLI; checked-in schema, all remaining constraints, local validation and legacy Luna input are unchanged; added byte-preservation/constraint regression | Main agent rerun `Ran 51 tests in 16.196s`, `OK`; stable file-set digest `80704b577cdf1a09a2ffd6e71cc114113731609c0e8add9c6fef147528d388f4` | `DEVEL_READY_REPAIR`; return exact stable state to independent tester Round 2 |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| 1 | Developer handoff plus real synthetic run `claude-e2e-5565db8920ea6e68` | **FAIL** | Blocking Claude structured-output schema compatibility defect; no finalization/publication. Dual session/mailbox/subagent hard path itself passed | Full immutable evidence appended to shared test plan Round 1; raw ignored run retained for repair comparison |
| 2 | Digest `80704b577cdf1a09a2ffd6e71cc114113731609c0e8add9c6fef147528d388f4` | **PASS** | No blocking defect. Low residual: real finalization needed two transient failed summary attempts before bounded retry succeeded | 51 tests, Ruff/format, JSON and diff checks PASS; Claude Code 2.1.215 adapter and full 22-event finalize/publish PASS; full evidence in shared test plan Round 2 |

## Final verification

- Required checks: final main-agent run `Ran 51 tests in 16.994s`, `OK`; Ruff check/format, three
  JSON parses, `git diff --check`, real Claude dual-session and structured-output finalization PASS.
  GitNexus final staged detection saw all 14 scoped files, zero indexed symbols/processes and
  reported low risk; because `.codex`/`.claude` symbols are absent from the index, this is recorded
  as limited graph coverage rather than proof of no impact
- Runtime/restart health: not required; no backend/frontend/runtime service file changed
- Documentation/status sync: requirement, design, test plan, Codex compatibility guide, Claude
  runbook and delivery record aligned
- Cleanup: unique synthetic run and retrospective moved to trash; no probe artifact remains
- Residual risks and follow-ups: system-installed Claude Code 2.1.153 is below the tested 2.1.215
  path; structured summary had two transient failures before retry succeeded; poll intentionally
  provides no confidentiality from a malicious local process

## Retrospective

- Scope or design deviations: 原生 `SendMessage` 只适用于同一 Agent Team，不能连接任意两个顶层
  session；计划评审后改用受控 repo-local mailbox，同时保留两个对等顶层 session 的目标。
- Rework and root causes: 独立测试 Round 1 发现 Claude 2.1.215 的 JSON Schema dialect 不接受顶层
  Draft 2020-12 `$schema`。修复只在 Claude CLI adapter 的副本中移除该声明，未削弱本地/legacy
  schema；Round 2 真实 finalize PASS。
- What shortened or delayed delivery: 提前探针确认 nested local agent 可用；强制计划评审避免实现
  不可用的跨 session `SendMessage`。真实 summary 硬门禁增加一轮返工，但阻止了 mock-only 假通过。
- Reusable lessons: 多 Runtime Harness 必须分别验证 transport、session identity、Hook payload 和
  structured-output dialect；同名“Agent”能力不代表相同 session 拓扑或 schema 支持。
