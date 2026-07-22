# R2.0-001 Pi 建模 Agent 能力验证 Delivery Record

- Requirement source: `docs/requirements/requirements-v2.0.md` R2.0-001
- Status: in-progress
- Started: 2026-07-22T09:45:00+08:00
- Last updated: 2026-07-22T11:07:15+08:00
- Design: pending
- Shared test plan: pending
- Delivery baseline: `c581841`; existing R1.1-007 and backend worktree changes are unrelated and
  must be preserved
- Delivery commit: pending

## Confirmed contract

- Current behavior: 平台通过外部 Claude Code/Codex Runtime、Skill、Hook、Harness、共享建模目录和
  本地 Adapter 实验建模工作流；平台核心不托管 Agent Runtime。
- Target behavior: 将第一方、可替换的建模 Agent Runtime 纳入 v2.0 目标，并首先验证 Pi 是否具备
  承载当前建模 Agent 全链路能力的条件。
- In scope: v2.0 版本定位；R2.0-001 的 Pi 能力验证目标、边界、验证维度、产物和验收结论。
- Non-goals: R2.0-001 不交付生产级 Pi 集成，不切换默认建模 Runtime，不承诺平台正式托管或
  向外发布 Pi Agent；这些工作在验证 PASS 后由后续需求承接。
- Acceptance summary: R2.0-001 通过文档核验和最小隔离探针判断 Pi 的公开 SDK、Extension、事件、
  会话、工具、模型、多角色、监控、恢复、安全和分发机制能否承载 v1.1 建模 Agent 能力；不要求
  完成平台接入或真实端到端建模。
- Refinement: 用户已确认“集成 Pi”属于 v2.0，并要求把“验证 Pi 是否具备建模 Agent 各项能力”
  定义为 R2.0-001；用户进一步确认 001 仅作为可行性验证门禁，PASS 后再进入 R2.0-002 正式集成。

## Timeline

### 2026-07-22T09:45:00+08:00 — requirement seed and baseline audit — user and main agent

- Context: v1.1 已证明外部 Runtime 的 Skill、Hook、监控、调试和恢复能力会影响建模实验的可控性；
  用户决定把 Pi 第一方 Runtime 方向提升为 v2.0，而不是继续作为 v1.1 的局部适配优化。
- Action/decision: 规划新建 `requirements-v2.0.md`，以 R2.0-001 先验证 Pi 的建模 Agent 能力。
- Evidence: `docs/architecture/decisions/0001-platform-boundaries.md`；
  `docs/requirements/requirements-v1.1.md`；
  `docs/delivery/designs/2026-07-22-r1-1-007-local-formal-modeling-profiles-design.md`；
  current `git status --short`.
- Outcome/next step: 确认 R2.0-001 是仅做可行性验证，还是同时承诺正式集成与默认切换。

### 2026-07-22T10:02:00+08:00 — refinement decision 1 — user and main agent

- Context: 需要区分“验证 Pi 是否适合”与“承诺把 Pi 正式集成进平台”，避免验证尚未完成就锁定
  Runtime 和生产架构。
- Action/decision: R2.0-001 只负责可行性验证。可以创建 repo-local Pi 原型并进行真实建模实验，
  但不交付生产集成、不切换默认 Runtime；验证 PASS 后由 R2.0-002 承接正式集成。
- Evidence: 用户在本轮需求细化中明确回复“同意”。
- Outcome/next step: 确认能力验证必须达到真实端到端建模，还是允许以静态 API/SDK 探针为主要证据。

### 2026-07-22T11:00:54+08:00 — refinement decision 2 — user and main agent

- Context: 真实端到端建模需要先完成 Pi 工具、角色、平台协议和工作流适配，若放入 001 会把
  “判断是否可行”和“实施正式改造”混为同一需求。
- Action/decision: R2.0-001 不要求真实端到端建模运行。001 只核验 Pi 的基础能力和公开扩展机制；
  平台接入、建模流程改造、真实资料运行及质量验收由后续需求负责。
- Evidence: 用户明确说明端到端运行涉及改造，应留给后续需求。
- Outcome/next step: 确认能力判定是否接受“通过 Pi 公开 SDK/Extension 可以实现”，还是只接受 Pi
  原生已内置的能力。

### 2026-07-22T11:01:53+08:00 — refinement decision 3 — user and main agent

- Context: Pi 有意保持核心精简，部分建模 Runtime 能力需要使用公开 SDK 或 Extension 构建；若只
  接受原生内置能力，会把“可安全扩展”错误判为“不支持”。
- Action/decision: 每项能力按 `native`、`extension_feasible`、`fork_required`、`unsupported` 四级
  分类。所有必需能力均为前两级时 R2.0-001 才能 PASS；任何必需能力需要 fork Pi 核心或当前无法
  实现时，不得给出无条件 PASS。
- Evidence: 用户明确回复“同意”。
- Outcome/next step: 确认是否以 v1.1 已定义的完整建模工作流与当前外部 Runtime 适配问题作为
  R2.0-001 必需能力清单的来源。

### 2026-07-22T11:03:54+08:00 — refinement decision 4 and contract freeze — user and main agent

- Context: 能力验证需要一个完整、非任意删减的基线，同时不能把后续平台集成和真实建模改造提前
  塞入可行性验证。
- Action/decision: 以 v1.1 已确认建模工作流为完整能力来源，覆盖主 Agent/多角色、Prompt/Skill/
  上下文、结构化产物、工具控制、Session 恢复、事件监控和调试、模型切换、用户交互、安全、
  Runtime 嵌入与平台扩展条件。001 只执行官方资料核验和最小隔离探针。
- Evidence: 用户明确回复“同意”。
- Outcome/next step: 功能合同冻结；创建 `requirements-v2.0.md` 并同步已确认术语。

### 2026-07-22T11:03:54+08:00 — requirement document authored — main agent

- Context: 四项关键边界均已由用户确认，足以形成 R2.0 版本定位和 R2.0-001 的完整功能合同。
- Action/decision: 新建 v2.0 需求文档，定义四级能力分类、十二类必需能力、最小探针、验证产物、
  PASS/FAIL/BLOCKED、非目标和后续 R2.0-002 门禁；向术语表增加三层架构术语。
- Evidence: `docs/requirements/requirements-v2.0.md`；`docs/reference/glossary.md`。
- Outcome/next step: 校对需求内部一致性和工作区范围；本轮不进入设计、实现或 Pi 安装。

### 2026-07-22T11:07:15+08:00 — requirement-document verification — main agent

- Context: 需求正文需要证明 001 与后续正式集成的边界一致，并且不能夹带现有 R1.1-007 工作区
  改动。
- Action/decision: 校对 v2.0 总表、R2.0-001 十二类能力、四级分类、验证方式、非目标和验收标准；
  保持 R2.0-002 仅为 PASS 后的待细化方向。
- Evidence: `git diff --check -- docs/requirements/requirements-v2.0.md docs/reference/glossary.md
  docs/delivery/records/2026-07-22-r2-0-001-pi-modeling-agent-capability-validation-delivery-record.md`；
  scoped `git diff` and `rg` consistency review.
- Outcome/next step: requirement refinement is complete; R2.0-001 remains unimplemented and awaits
  a separate design/test/implementation delivery cycle.

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |

## Final verification

- Required checks: scoped Markdown diff check PASS; requirement status and detailed section agree.
- Runtime/restart health: not applicable to requirement-document refinement.
- Documentation/status sync: v2.0 requirement source created and glossary terminology synchronized.
- Cleanup: no runtime data created.
- Residual risks and follow-ups: Pi capability claims remain to be proven by R2.0-001; R2.0-002 cannot
  start before PASS.

## Retrospective

- Scope or design deviations: pending.
- Rework and root causes: pending.
- What shortened or delayed delivery: pending.
- Reusable lessons: pending.
