# R2.0-001 Pi 建模 Agent 能力验证 Delivery Record

- Requirement source: `docs/requirements/requirements-v2.0.md` R2.0-001
- Status: in-progress
- Started: 2026-07-22T09:45:00+08:00
- Last updated: 2026-07-22T15:34:19+08:00
- Design: pending
- Shared test plan: pending
- Delivery baseline: `c581841`; existing R1.1-007 and backend worktree changes are unrelated and
  must be preserved
- Delivery commit: pending

## Confirmed contract

- Current behavior: 平台通过外部 Claude Code/Codex Runtime、Skill、Hook、Harness、共享建模目录和
  本地 Adapter 实验建模工作流；平台核心不托管 Agent Runtime。
- Target behavior: 用最简单的 repo-local 原型验证 Pi 能否搭建平台建模 Agent，并向外暴露足以
  优化后续建模流程的关键事件和一个代表性阶段 Summary。
- In scope: 固定 `earendil-works/pi` 候选；验证 Runtime、模型、Prompt/Skill、工具与结构化产物、
  双角色显式交接、SDK/RPC 用户澄清、最小流程监看和单阶段 Summary 六类能力。
- Non-goals: 不交付正式 Pi 集成，不运行真实资料建模或质量对照；安全、崩溃恢复、完整 Session
  持久化、精确性能、生产监控/审计、部署、分发和完整许可证方案均不作为 001 完成门槛。
- Acceptance summary: 一个固定版本的最小合成场景足以证明 Pi 可以装配建模 Agent、运行两个隔离
  角色、调用结构化工具、显式交接、提问暂停继续、输出产物、暴露关键流程状态，并在一个代表性
  阶段结束时生成 Summary；测试不追求生产级精度。
- Refinement: 用户已确认“集成 Pi”属于 v2.0，并要求把“验证 Pi 是否具备建模 Agent 各项能力”
  定义为 R2.0-001；用户进一步确认 001 仅作为可行性验证门禁，PASS 后再进入 R2.0-002 正式集成；
  候选对象固定为 `earendil-works/pi` 和 `@earendil-works/pi-coding-agent`；
  `extension_feasible` 只接受基于公开接口的薄扩展，不接受在外层重造 Pi 核心子系统；用户交互
  必须通过 SDK/RPC 暂停与恢复探针，不接受 TUI-only 证据；用户随后将合同收缩为建模效果优先的
  POC 能力门禁，明确只需验证 Pi 可搭建建模 Agent、具备最小流程监看和一次阶段 Summary，其他
  产品化能力延后。

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

### 2026-07-22T15:02:54+08:00 — settled-scope re-audit — main agent

- Context: 用户要求开始细化 V2-001；仓库中的 R2.0-001 已完成四项功能边界确认并标记为
  `已细化，待实现`，因此本轮先按 settled-scope audit 检查是否仍有会改变验证结论的实质歧义。
- Action/decision: 十二类能力、四级分类、探针范围、PASS/FAIL/BLOCKED 和 001/002 边界保持
  有效；发现唯一的前置 P0 缺口是验证对象尚未固定到具体 Pi upstream 仓库、包名和维护方。
- Evidence: `docs/requirements/requirements-v2.0.md` R2.0-001；本交付记录此前四项用户确认；
  `git log -- docs/requirements/requirements-v2.0.md` 显示需求基线提交 `3a13fbf`；当前工作区在审计前
  为 clean `main...origin/main`。
- Outcome/next step: 请用户确认候选 Pi 的唯一 upstream；确认后补入需求合同，再判断是否可以直接
  进入设计与共享测试计划。

### 2026-07-22T15:04:48+08:00 — refinement decision 5 — user and main agent

- Context: `Pi` 名称不能唯一标识验证对象；仓库迁移、旧包和同名工具会导致 API、许可证及能力
  证据不可复核。
- Action/decision: 用户同意将候选对象固定为 `https://github.com/earendil-works/pi`（原
  `badlogic/pi-mono`）和 `@earendil-works/pi-coding-agent`。具体 commit 和依赖锁在设计阶段按公开
  可取得与可重复运行原则确定，验证过程不无记录地跟随 `main`。
- Evidence: 用户明确回复“同意”；Pi 官方仓库及 `packages/coding-agent/docs/sdk.md`。
- Outcome/next step: upstream 歧义已消除；继续确认 `extension_feasible` 的维护成本边界。

### 2026-07-22T15:06:41+08:00 — refinement decision 6 — user and main agent

- Context: 仅以“未修改 Pi 源码”判断 `extension_feasible` 会允许在平台侧维护一个事实上的第二套
  Runtime，从而掩盖选型失败和长期维护成本。
- Action/decision: 用户同意采用薄扩展标准。平台自有 Adapter、Extension 和 Workflow Package
  可以组合 Pi 公开接口；若必须在外层重新实现 Agent loop、Session 存储、事件模型或工具调度等
  核心子系统，则按具体缺口判为 `fork_required` 或 `unsupported`，不得 PASS。
- Evidence: 用户明确回复“同意”；`docs/requirements/requirements-v2.0.md` 能力分类。
- Outcome/next step: 维护成本边界已冻结；继续确认用户交互能力是否必须通过真实 SDK/RPC 探针。

### 2026-07-22T15:09:10+08:00 — refinement decision 7 — user and main agent

- Context: 仅证明连续对话或 TUI 输入不能证明后续第一方 Runtime 可以在无 UI 的 SDK/RPC 模式下
  承接业务访谈和子角色澄清。
- Action/decision: 用户同意把用户交互列为最低真实探针：Agent 发出结构化问题，当前 Run 进入
  外部协调器可判断的暂停状态，协调器提交回答，原 Session 恢复并完成任务；不得依赖 Pi TUI 或
  通过重建 Session 模拟恢复。
- Evidence: 用户明确回复“同意”；`docs/requirements/requirements-v2.0.md` 验证方式和验收标准。
- Outcome/next step: 暂停继续合同已冻结；继续确认凭证不泄漏是否需要合成 canary 动态探针。

### 2026-07-22T15:13:05+08:00 — refinement scope change — user and main agent

- Context: 主 Agent 提议用合成 canary 验证凭证不会泄漏；用户指出当前是 POC 前期，核心目的是
  优化建模效果，安全性及其他非核心产品化能力暂不考虑，后续设计也必须遵循这一优先级。
- Action/decision: 不加入凭证 canary 探针；重新打开已冻结合同，计划将安全、生产恢复、完整审计、
  部署治理等不直接保护建模效果的能力移出 R2.0-001 PASS 门槛，只保留运行建模质量实验和定位
  质量问题所需的最小 Runtime 能力。具体保留范围待下一项用户确认后写回权威需求。
- Evidence: 用户明确回复“POC 前期阶段，不考虑安全性。核心目的是优化建模效果，其它都可以先
  不管，后续设计也要遵循这个原则”。
- Outcome/next step: 确认 R2.0-001 是否仍只做机制探针，还是应包含一次真实资料的最小建模效果
  实验；该决定将确定需求是能力门禁还是质量 POC。

### 2026-07-22T15:16:32+08:00 — refinement decision 8 — user and main agent

- Context: 建模效果是 v2.0 的总优先级，但用户需要继续区分“Pi 是否可用于搭建建模 Agent”的
  前置能力验证与后续真实建模质量实验。
- Action/decision: R2.0-001 仍只做轻量能力可行性验证，不运行真实资料建模或质量对照。验证以
  最简单、足以说明问题的文档证据和小探针证明两点：Pi 可以用于搭建平台建模 Agent；平台能够
  监看建模流程。测试不追求高精度。安全、生产恢复、精确性能指标、部署治理和真实质量验收均
  延后到确有需要的后续需求。
- Evidence: 用户明确说明“001 仅验证 Pi 是否具备相应能力，怎么简单怎么来，测试不需要很精确，
  只要能说明 Pi 能用于搭建平台的建模 Agent，同时能具备流程监看能力即可”。
- Outcome/next step: 确认“流程监看”的最低可见事件集合；随后将十二类全门禁合同收缩为 POC
  最小能力合同。

### 2026-07-22T15:21:53+08:00 — refinement decision 9 — user and main agent

- Context: 流程监看的目的不是生产审计，而是看清每一步并优化 Prompt、Skill、角色协作和返工
  路径；仅有开始/结束事件不能解释步骤做了什么和为什么需要调整。
- Action/decision: 用户同意最小事件可见性包含角色/Session、流程阶段、模型调用状态、工具调用
  及结果状态、提问/暂停/恢复、最终产物位置或失败原因；同时要求具备类似 Claude Code Harness
  的 Summary 能力，为每个有意义的流程步骤生成概要。Summary 至少应概括角色、步骤目标、简明
  动作、输入/输出或产物引用、可见问题与决定、结果、未解决项和下一步，用于流程优化；不要求
  隐藏推理或完整 transcript。
- Evidence: 用户明确回复同意最小监看集合，并补充“每个步骤的概要是需要的”；
  `docs/delivery/designs/2026-07-20-r1-1-005-claude-dual-agent-harness-design.md` 的 Summary 合同。
- Outcome/next step: 确认 POC Summary 的生成隔离要求；随后冻结最小能力合同并重写权威需求。

### 2026-07-22T15:26:44+08:00 — refinement decision 10 — user and main agent

- Context: 主 Agent 提议每个步骤结束时启动短生命周期 Pi Summary Session；该方案超过 001
  说明“Pi 具备阶段概要能力”所需的最小验证范围。
- Action/decision: R2.0-001 只选择一个代表性阶段，在阶段结束时证明 Pi 能根据该阶段可见事件生成
  一份结构化 Summary。Summary 使用同一 Session、临时 Session 或扩展工具不作为功能合同，按
  最小实现决定；不要求逐步骤持续生成、生产级隔离、重试或持久化。
- Evidence: 用户明确说明“只需要验证某阶段结束时具备 summary 的能力即可”。
- Outcome/next step: 汇总并确认收缩后的最小能力与探针集合，然后重写权威需求。

### 2026-07-22T15:33:10+08:00 — refinement decision 11 and contract freeze — user and main agent

- Context: 主 Agent 汇总六类当前最小能力和明确非目标，避免旧十二类生产 Runtime 能力继续成为
  POC 完成门槛。
- Action/decision: 用户同意按最小合同重写 R2.0-001。权威需求现只要求 Runtime/模型、Prompt/
  Skill、结构化工具与产物、双角色显式交接、SDK/RPC 用户澄清、最小流程监看和一个代表性阶段
  Summary；使用一个合成场景和宽松探针验证。安全、恢复、精确性能、生产监控/审计、部署、分发、
  完整许可证方案及真实建模质量实验均明确延后。
- Evidence: 用户明确回复“同意”；`docs/requirements/requirements-v2.0.md` R2.0-001 当前最小能力
  合同、验证方式、非目标和验收标准。
- Outcome/next step: 功能合同重新冻结；下一阶段应编写最小设计和共享测试计划，不得重新引入已
  延后的产品化门槛。

### 2026-07-22T15:34:19+08:00 — refined-contract verification — main agent

- Context: 收缩后的需求需要确认总表状态、当前最小能力、验证方式、非目标和验收标准一致，且
  没有影响产品代码或既有执行流程。
- Action/decision: 完成 scoped 内容检索、Markdown diff 检查和 GitNexus 变更检测；仅两份需求交付
  文档发生变化，无代码符号和执行流程受影响，风险为 low。
- Evidence: `git diff --check` PASS；针对“六类”“代表性阶段 Summary”“不验证凭证隔离”和“真实
  业务资料”的 `rg` 一致性检查 PASS；GitNexus `detect_changes(scope=all)` 返回 changed files 2、
  changed symbols 0、affected processes 0、risk low。
- Outcome/next step: R2.0-001 功能细化完成，可以提交冻结合同；设计与测试计划留待下一阶段。

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
