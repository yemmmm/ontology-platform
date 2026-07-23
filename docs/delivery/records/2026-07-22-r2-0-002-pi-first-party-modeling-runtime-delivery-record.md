# R2.0-002 Pi 第一方建模 Agent Runtime 正式集成 Delivery Record

- Requirement source: `docs/requirements/requirements-v2.0.md` R2.0-002
- Status: **暂不继续推进；检查点保留，原验收未完成**。phase 1 (`2c4a678`) + G1
  orchestrator (`8881d4d`) committed & independently tested PASS (Round 1/2/3). G2 real run advanced
  across 9 rounds through coordinator→business-organizer→commit-business→Work Unit modeling (4 units
  accepted); blocked on work-unit result→SMD submission (migration gap, needs accept-unit-result path).
  Unmet original gates: G2 completion (work-unit result chain + apply + verification), H Claude
  retirement, and final closure; these are not active follow-up work under R2.0-002.
- Started: 2026-07-22T16:30:00+08:00
- Last updated: 2026-07-23T15:24:39+08:00
- Design: `docs/delivery/designs/2026-07-22-r2-0-002-pi-first-party-modeling-runtime-design.md`
- Shared test plan: `docs/delivery/test-plans/2026-07-22-r2-0-002-pi-first-party-modeling-runtime-test-plan.md`
- Architecture decision: `docs/architecture/decisions/0007-first-party-modeling-runtime-boundary.md`
- Delivery baseline: `294e5eb`
- Phase 1 commit: `2c4a678` (Build Pi Local modeling runtime phase 1; 37 files; clean `main`)
- G1 commit: `8881d4d` (Pi modeling orchestrator + Round 2/3 PASS)
- G2 checkpoint commit: `11f60f2` (Advance Pi modeling G2 real run through Work Unit modeling)
- Phase 1 model decision: `deepseek/deepseek-v4-flash` (carried from R2.0-001; key staged in gitignored
  config; required for G; G2 apply additionally requires `SEMANTIC_PRODUCT_WRITE_MODE=rdf_primary`)
- Delivery commit: pending G2 completion + H + closure

## Confirmed contract

- Current behavior: 真实建模流程运行在 Claude Code/Codex 等外部 Runtime。可复用的建模方法、
  Shared Modeling Directory、Local/Formal Profile、确定性候选合并、独立评审、Modeling Batch 和
  检索验收已存在；Claude Code 仍承担项目 Agent/Skill 装载、主/子角色会话、Hook 事件、双会话
  mailbox、MCP 隔离和 Harness Summary。Pi 0.81.1 已通过 R2.0-001 最小能力验证，但尚未运行真实
  平台建模流程。
- Target behavior: 将当前已经验证有效的建模流程迁移为由 Pi 第一方 Runtime 执行，并以真实资料
  建模、流程可见性和建模质量迭代证明迁移有效；Semantic Platform Core 继续只负责确定性校验、
  Evidence、Batch、持久化和查询。
- In scope: Pi Local Runtime、Pi-only Workflow Package、主协调/业务整理/Work Unit 建模/独立评审
  角色、现有平台接口、用户澄清、结构化交接、局部恢复、最小事件流与阶段 Summary，以及固定
  真实语料的端到端建模质量验收；Pi PASS 后退役 Claude 建模入口。
- Non-goals: 当前不建设生产级安全、完整崩溃恢复、分布式调度、远程执行、通用监控/审计服务、
  管理 UI、跨机器协作、自动升级或其他不直接改善建模质量与真实模型正确性的产品化能力。
- Acceptance summary: Pi Local 从 Project、资料和目标开始，完成访谈、Brief/CQ、分片建模、独立
  评审、确定性 dry-run/apply 与应用后 CQ/检索/provenance 验证；使用固定真实语料通过全部现有质量
  门禁。只生成候选或 dry-run 成功不算完成；不要求 Claude 对照或二次优化运行。
- Refinement: 用户明确要求在 R2.0-001 验证结束后开始 R2.0-002 设计，把 Claude Code 中的流程迁移
  到 Pi Agent，并继续坚持“核心优化建模流程，其它无关特性当前阶段不需要”。

## Timeline

### 2026-07-22T16:30:00+08:00 — source and current-state audit — user and main agent

- Context: R2.0-001 已在权威需求中标记 `已验证，PASS`，R2.0-002 已满足启动前置条件，但正文仍只
  是待细化方向，尚未冻结默认入口、Runtime 边界、迁移范围和真实建模验收合同。
- Action/decision: 以现有 R1.1 建模方法和质量门禁作为迁移基线；把 Claude Code 专属启动、Hook、
  mailbox、MCP 隔离和 summarizer 视为待替换 Runtime 适配，不把平台确定性协议或参考本体业务概念
  搬入 Pi Runtime。当前先进行用户功能细化，不开始实现。
- Evidence: `docs/requirements/requirements-v2.0.md`; R2.0-001 delivery record and issue report;
  `.claude/modeling-harness.md`; `.claude/local-modeling.md`; `.codex/modeling_profiles.py`;
  `.codex/local_modeling_adapter.py`; `.codex/shared_modeling_directory.py`; clean git status at
  `d6f8255`.
- Outcome/next step: 先确认 Pi 成为默认建模入口后的 Claude Code 兼容边界；随后收敛实际角色流程、
  输入输出、失败行为和质量验收。

### 2026-07-22T16:30:00+08:00 — R2.0-001 integration constraints carried forward — main agent

- Context: R2.0-001 的最小探针可用于选定 002 的最小实现方向，但不能冒充真实流程验收。
- Action/decision: 正式设计必须固定 `@earendil-works/pi-coding-agent@0.81.1` 及 lock，满足 Node
  `>=22.19.0`，在启动时显式确认项目资源 trust/加载结果，并为 Runner 选择可明确回收的 RPC
  子进程或持久宿主边界；不把这些约束扩大为生产级部署设计。
- Evidence: `docs/delivery/reports/2026-07-22-r2-0-001-pi-validation-issues.md`; ignored local
  `backend/.local/pi-v2-001/package-lock.json` and integrated RPC probe.
- Outcome/next step: 在功能合同确认后，用最小风险探针验证最终选定的 Runtime 边界。

### 2026-07-22T16:37:48+08:00 — refinement decision 1 — user and main agent

- Context: R2.0-002 需要明确是一次面向日常建模质量实验的最小迁移，还是同时替换现有 Local、
  Formal、fast-local 和 strict-eval 全部路径；后者会把正式交付、审计和产品化兼容成本带入本期。
- Action/decision: 用户同意本期完整迁移 Local 日常建模流程，并让 Pi 成为默认建模实验入口；现有
  Claude Code 路径只保留为质量对照和临时回退，不作为新流程的默认入口；Formal/strict-eval 的
  完整迁移不属于 R2.0-002 完成门槛。
- Evidence: 用户在 R2.0-002 细化问题 1 中明确回复“同意”。
- Outcome/next step: 继续确认 Pi 内部角色拓扑与交接边界，确保迁移优化建模协作而不是机械复制
  Claude Code 配置。

### 2026-07-22T16:39:59+08:00 — refinement decision 2 — user and main agent

- Context: Claude Code 当前存在多个项目 Agent 定义；逐个复制这些 Runtime 配置会保留外部
  Runtime 偶然形成的拓扑，而不是冻结真正保护建模质量的角色隔离和交接语义。
- Action/decision: 用户同意按功能阶段重组为 Pi 原生协作：一个持续与用户交互的主协调 Agent；
  一个独立业务整理 Session；每个 Work Unit 使用新建模 Session，并只在范围独立时并行；一个不
  共享建模隐藏对话的独立评审 Session。角色间仅通过 Shared Modeling Directory 中的结构化产物
  和稳定定位符交接，不复制隐藏聊天上下文。
- Evidence: 用户在 R2.0-002 细化问题 2 中明确回复“同意”；现有 R1.1-006/007 结构化 Work Unit、
  candidate hash 和独立 review 合同。
- Outcome/next step: 继续确认 Pi Local 的完整输入与结束边界，避免只迁移中间模型生成步骤。

### 2026-07-22T16:42:51+08:00 — refinement decision 3 — user and main agent

- Context: 如果 Pi 只接收预制 Brief/CQ 或只输出候选模型，就无法验证资料理解、业务澄清、模型
  应用和检索反馈组成的完整建模质量闭环，也不能替代当前 Local 日常建模入口。
- Action/decision: 用户同意 Pi Local 从现有 Project、资料定位符/语料、建模目标和可选约束开始，
  完成资料理解、用户访谈、Brief/CQ 确认、Coverage/Work Unit、分片建模、独立评审、dry-run/apply，
  并以应用后的 CQ、语义检索和 provenance 验证结束。输出包括已应用模型、Shared Modeling
  Directory 产物、各阶段 Summary、明确遗漏和最终质量结论；只生成候选或只通过 dry-run 不算
  完整成功。
- Evidence: 用户在 R2.0-002 细化问题 3 中明确回复“同意”。
- Outcome/next step: 继续确认用户确认点和自动 apply 边界。

### 2026-07-22T16:45:07+08:00 — refinement decision 4 — user and main agent

- Context: 逐 Batch 人工批准会中断日常建模迭代，但完全自动应用又可能把未确认的业务含义、删除
  或影响不明的变更写入平台。
- Action/decision: 用户同意只保留三类强制确认：Brief/CQ 形成业务承诺前确认；资料无法解决的
  业务歧义暂停询问；删除、不可逆修改或影响范围不明的变更在 apply 前确认。普通新增和影响明确
  的修改在独立评审 PASS、candidate hash 一致且 dry-run 无阻断 Finding 后自动 apply，不逐 Batch
  请求确认。
- Evidence: 用户在 R2.0-002 细化问题 4 中明确回复“同意”。
- Outcome/next step: 继续确认局部失败、平台 Finding 和未知 apply 结果的恢复行为。

### 2026-07-22T16:48:09+08:00 — refinement decision 5 — user and main agent

- Context: R2.0-002 不建设通用 Pi Session 恢复系统，但角色失败、平台 Finding 或未知 apply 结果
  不能迫使整个本体从头重做，也不能通过新建 Batch 或跳过门禁来猜测恢复。
- Action/decision: 用户同意采用基于稳定产物的局部恢复：角色失败时保留已完成产物，仅以相同输入
  重启对应角色或 Work Unit；平台校验/dry-run Finding 映射回受影响 Work Unit，修正后重新合并、
  独立评审和 dry-run；apply 超时或结果未知时先用原 `client_batch_id` 和幂等标识核对平台状态，
  禁止新建替代 Batch；用户澄清暂停当前 run，回答后从共享产物继续；已成功应用的 Batch 不自动
  回滚。不要求恢复完整聊天、隐藏推理或崩溃前 Pi 进程。
- Evidence: 用户在 R2.0-002 细化问题 5 中明确回复“同意”；现有 R1.1-006/007 Batch 和局部重跑
  合同。
- Outcome/next step: 继续确认真实建模质量对照和流程优化验收门槛。

### 2026-07-22T17:08:27+08:00 — refinement decision 6 — user and main agent

- Context: 主 Agent 提议把 Claude Code 质量对照、基于 Summary 定位真实瓶颈，以及调整流程后
  重跑受影响范围一并纳入 R2.0-002 完成门槛；这些会把首次正式迁移扩大为对照实验和二次优化
  迭代。
- Action/decision: 用户只接受固定代表性真实语料和既有质量门禁两项。R2.0-002 使用固定版本语料
  与验收问题完成 Pi 全链路，并通过 source fidelity、业务范围、独立评审、平台校验、CQ、检索和
  provenance 门禁；本期不要求与 Claude Code 结果对照，不要求通过 Summary 定位一个真实瓶颈，
  也不要求修改流程后再跑一次证明改善。
- Evidence: 用户明确回复“不同意。345不做”，即拒绝提案第 3、4、5 项。
- Outcome/next step: 继续确认流程监看事件和阶段 Summary 的最小粒度；这些产物用于理解本次真实
  运行，不扩大为本期对照或二次优化实验。

### 2026-07-22T17:10:48+08:00 — refinement decision 7 — user and main agent

- Context: R2.0-002 需要比 001 的单阶段能力探针更完整地暴露真实流程，但逐 Turn Summary、隐藏
  推理、完整 transcript 或监控服务都不是当前建模质量验收的必要条件。
- Action/decision: 用户同意事件流记录 run、角色/Session、阶段开始结束、模型与工具调用状态、
  澄清暂停/继续、产物定位符和失败原因；仅在业务整理、每个 Work Unit、独立评审/apply、最终
  验证结束时生成结构化 Summary。不做逐 Turn Summary，不保存隐藏推理或完整 transcript，不建设
  监控 UI 或服务端事件库。事件和 Summary 只用于看清本次真实运行，不附带本期对照或二次优化门禁。
- Evidence: 用户在 R2.0-002 细化问题 7 中明确回复“同意”。
- Outcome/next step: 确认 Pi Runtime 的进程边界和 repo-local 交付形态。

### 2026-07-22T17:23:54+08:00 — refinement decision 8 — user and main agent

- Context: R2.0-001 的 SDK 探针在 Session dispose 后仍不能自然退出；把 Pi 嵌入 backend 或建设
  常驻服务还会引入当前不需要的服务生命周期、部署和运维范围。
- Action/decision: 经主 Agent 用本地命令/子进程方式重新解释后，用户同意 R2.0-002 交付仓库内的
  本地启动命令：运行建模时启动 Pi 主协调 Agent，需要业务整理、Work Unit 建模或评审时临时启动
  对应 Pi Agent，任务完成后关闭；所有 Agent 通过现有平台 API/MCP 工作。不把 Pi 放进 backend，
  不接入 systemd，不建设常驻 Runtime 服务。
- Evidence: 用户在澄清后的 R2.0-002 细化问题 8 中明确回复“同意”；R2.0-001 P1 进程生命周期
  问题。
- Outcome/next step: 继续确认 Runtime-neutral Modeling Workflow Package 与 Pi 专属薄适配的边界。

### 2026-07-22T17:27:37+08:00 — refinement decision 9 — user and main agent

- Context: 主 Agent 提议让 Pi 和 Claude Code 回退路径共同读取一套 Runtime-neutral 建模规则，以
  避免双份规则漂移；这仍会把 Claude Code 兼容性作为后续规则变更时的维护约束。
- Action/decision: 用户不同意继续维护 Claude Code 方案。R2.0-002 将 Pi Agent Workflow Package
  作为唯一主动维护的建模规则和角色方法来源；不要求 Pi 规则保持 Claude Code Skill/Agent/Hook
  兼容，也不要求后续建模规则变更同步到 Claude Code 路径。
- Evidence: 用户明确说明“claude的方案不需要继续维护了，完全可以只维护pi agent的规则”。
- Outcome/next step: 需要确认旧 Claude Code 建模文件在 Pi 全链路验收后是删除，还是保留为冻结、
  不保证可用的历史参考；该决定将修正先前的临时回退边界。

### 2026-07-22T17:37:41+08:00 — refinement decision 10 — user and main agent

- Context: 只停止同步 Claude 规则但继续保留现行入口和文档，会让使用者误以为该路径仍受支持，
  并让过时测试成为 Pi 规则变化的隐性维护负担。
- Action/decision: 用户同意在 Pi 全链路独立验收 PASS 前暂时保留 Claude 建模路径；PASS 后在
  R2.0-002 内删除 Claude 专属建模 Agent、Hook、Harness、launcher 和现行使用文档。历史交付文档
  与 Git 历史保留；Shared Modeling Directory、平台 Adapter 等 Pi 仍需使用的非 Claude 组件继续
  保留。最终仓库只提供 Pi 作为日常建模入口，不承诺 Claude 回退路径可用。
- Evidence: 用户在 R2.0-002 细化问题 10 中明确回复“同意”。
- Outcome/next step: 明确 Formal/strict-eval 在 Claude 路径删除后的支持状态，然后冻结功能合同。

### 2026-07-22T19:58:50+08:00 — refinement decision 11 and contract freeze — user and main agent

- Context: Claude Formal/strict-eval 依赖本期计划删除且不再维护的 Claude Harness；R2.0-002 又明确
  只迁移 Pi Local，因此不能同时继续承诺旧 Formal 路径受支持。
- Action/decision: 用户同意 R2.0-002 完成后只支持 Pi Local；原 Claude Formal/strict-eval 随旧
  入口一起退役。如果未来确实需要完整交付记录或严格评测，再以独立后续需求设计 Pi Formal，不为
  保留旧能力扩大本期范围。结合此前十项确认，R2.0-002 功能合同冻结，可以进入风险探针、设计与
  共享测试计划。
- Evidence: 用户在 R2.0-002 细化问题 11 中明确回复“同意”；本记录 refinement decision 1-10。
- Outcome/next step: 验证 Pi RPC 子进程、现有 Local Adapter 的 Claude Harness 耦合，以及 Claude
  入口退役的实际影响面；随后写回权威需求并形成设计/test plan。

### 2026-07-22T20:00:51+08:00 — risk probes — main agent

- Context: 设计最可能被三项假设推翻：Pi RPC 子进程是否可由外部 Runner 明确回收；现有 Local
  平台写入是否能在删除 Claude Harness 后直接复用；退役 Claude 是否只是删除 `.claude` 文件。
- Action/decision: 复跑 R2.0-001 的无平台写入 RPC 澄清探针，`input` 请求、外部回答和通知均成功，
  Runner 显式终止子进程后命令以 0 退出、总耗时约 0.5 秒，因此采用本地 Runner + 可回收 RPC
  子进程。代码审计确认 `commit_business`、`dry_run_next`、`apply_next`、`verify` 和 `finish` 等关键
  Adapter 动作都消费 Claude Harness `recording_grant`，`recording_health` 还直接调用
  `.codex/hooks/modeling_harness.py`；Pi 不能原样复用该门禁，设计必须让 Adapter 成为 Pi Runner
  内部平台边界，并用 Pi 可见事件包裹调用，同时保留原 hash、review、idempotency 和验证保护。
  当前 Profile、Shared Directory、Adapter 的 2 + 16 + 21 项合同测试全部通过，证明可迁移的确定性
  核心基线稳定。引用审计还发现 v1.1 当前能力声明和旧 Skill 直接绑定 Claude/Harness，因此退役
  必须同步状态与现行文档，不能误删非建模 GitNexus Skill 或历史交付记录。
- Evidence: `timeout 30s node backend/.local/pi-v2-001/rpc-clarification-probe.mjs` PASS；
  `python3 -m unittest discover -s .codex/tests -p 'test_modeling_profiles.py'` 2 PASS；相同命令运行
  `test_shared_modeling_directory.py` 16 PASS、`test_local_modeling_adapter.py` 21 PASS；scoped `rg`
  对 Adapter coupling 与 active Claude references 的结果。
- Outcome/next step: 采用 repo-local Pi RPC Runner；迁移而不是重写 Shared Directory/Adapter 的
  确定性核心；移除 Claude receipt/summary/profile 外壳，并在 Pi PASS 后完成旧入口和现行文档退役。

### 2026-07-22T20:04:31+08:00 — requirement, design, and shared test plan authored — main agent

- Context: 用户合同和三个高风险假设已收敛，可以冻结 R2.0-002 的功能设计与验收范围。
- Action/decision: 将 R2.0-002 写入权威需求，状态更新为 `已细化，待实现`；设计采用
  `pi-modeling-agent/` repo-local RPC Runner、Pi-only Workflow Package、迁移后的 Shared Directory
  和内部 platform adapter、repo-local events/stage summaries、两阶段 Claude 退役；共享测试计划以
  自动合同、固定 Dify 真实运行和退役后最终独立回归为完成门禁。没有加入 Claude 对照、二次优化、
  backend Runtime、Formal、UI 或生产恢复。
- Evidence: `docs/requirements/requirements-v2.0.md` R2.0-002；本记录顶部列出的 design 和 shared
  test plan。
- Outcome/next step: 完成 scoped consistency/diff 检查，然后提交 mandatory plan review。

### 2026-07-22T20:06:47+08:00 — mandatory plan review handoff — main agent

- Context: requirement/design/test plan/ADR 已形成，`git diff --check` 和 scoped 状态/边界检索通过；
  当前工作区只有本需求的六份文档变更。
- Action/decision: 将 R2.0-002 权威需求、v1.0 全局边界、ADR 0001/0007、设计、共享测试计划、
  AGENTS 约束和真实仓库交给独立 `plan_reviewer`。要求只报告证据支持的 Critical/High，并重点核验
  Pi RPC、Adapter/Harness 耦合、两阶段 Claude 退役、平台权威边界、实现可行性和真实验收覆盖。
- Evidence: plan reviewer handoff for task `/root/r2_0_002_plan_review`; scoped `git diff --check`;
  source/design/test paths listed at the top of this record.
- Outcome/next step: 主 Agent 等待审查结论，逐项判定严重性；确认的 High 修改方案后必须复审。

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |
| 1 | `agent_end` 被误作角色最终完成条件，可能在自动重试、压缩重试或排队 follow-up 前提前接受产物并终止子进程 | accepted-high | Pi 0.81.1 `docs/rpc.md` 与 `docs/extensions.md` 明确只有 `agent_settled` 表示不再自动继续，且 `ctx.isIdle()`/pending queue 可核验空闲 | 改为 `agent_settled` + idle/no-pending + Runner 空队列；新增普通、重试、压缩和排队 continuation 测试 |
| 1 | Claude 退役遗漏 README、backend 文档契约测试和 docs-sync CI 的硬编码 ontology-builder 依赖 | accepted-high | `README.md`、`backend/tests/test_documentation_sync.py`、`.github/workflows/docs-sync.yml` 仍直接安装、读取或运行旧 Skill | 退役清单逐项迁移或删除旧合同；最终强制运行完整 backend suite 和 docs-sync check |
| 2 | Round 1 两个 accepted-high 复审 | closed; PASS | 同一 plan reviewer 核验修订后的需求、设计和共享测试计划；无新增 Critical/High、无待确认假设 | 方案可进入 implementation-ready handoff |

### 2026-07-22T20:14:33+08:00 — plan review round 1 revised — main agent

- Context: mandatory plan review 返回 `REVISE`，报告两个有直接源码/官方包文档证据的 High finding。
- Action/decision: 接受两个 finding。修正先前风险探针结论：显式关闭 RPC 子进程只能证明外层 Runner
  可以回收它，不能证明第一次 `agent_end` 已安全完成角色。设计现在以 `agent_settled`、Extension
  idle/no-pending 和 Runner 空队列共同作为一次性角色产物接受条件；持续 coordinator 还必须达到工作流
  终态。Claude 退役也显式纳入 README、backend 文档契约测试和 docs-sync workflow，并把完整 backend
  suite 与 docs-sync check 列为最终命令。
- Evidence: plan reviewer round 1；Pi 0.81.1 `docs/rpc.md` 的事件表与 `docs/extensions.md` 的
  `agent_start / agent_end / agent_settled`、`ctx.isIdle()` 合同；上述三个硬编码仓库文件。
- Outcome/next step: 对修订后的需求、设计和共享测试计划执行 consistency check，然后交回同一
  plan reviewer 复审两个已接受 High finding。

### 2026-07-22T20:16:40+08:00 — mandatory plan review round 2 PASS — plan reviewer and main agent

- Context: Round 1 两个 accepted-high 已写回权威需求、设计和共享测试计划。
- Action/decision: 同一 plan reviewer 复审后给出 `PASS`：生命周期合同与 Pi 0.81.1 文档一致；
  Claude 退役已覆盖 README、backend 文档契约测试、docs-sync workflow 及相应最终命令。没有新的
  Critical/High，也没有需要用户确认的关键假设。ADR 0007、设计和测试计划据此标记已评审。
- Evidence: plan reviewer round 2 `PASS`；本记录 Review disposition；reviewed design/test plan。
- Outcome/next step: R2.0-002 保持 `已细化，待实现`。完成提交前文档检查和影响范围检查后提交本次
  requirement/design 包；实现与独立测试在后续 delivery cycle 按共享测试计划执行。

### 2026-07-22T20:18:00+08:00 — design package verification — main agent

- Context: mandatory plan review 已 PASS，本轮只交付 requirement/design package，不修改产品代码。
- Action/decision: 执行 whitespace、接口文档同步、现有文档契约测试和 GitNexus 变更范围检查。
- Evidence: `git diff --check` PASS；`cd backend && uv run python ../scripts/sync-interface-docs.py
  --check` PASS；`cd backend && uv run pytest tests/test_documentation_sync.py` 为 10 PASS、3 个既有
  deprecation warnings；GitNexus `detect_changes(scope=all)` 为 low risk、0 changed symbols、0
  affected processes。
- Outcome/next step: 设计包可以提交。真实 Pi workflow、完整 backend 测试、真实场景运行、Claude
  退役和独立测试仍属于后续实现周期，不能由本次文档验证代替。

### 2026-07-22T21:30:45+08:00 — phase 1 development handoff frozen — user and main agent

- Context: 用户确认分阶段推进，本次只做阶段 1；真实模型沿用 `deepseek/deepseek-v4-flash`（key 就绪，
  阶段 1 不需要）。设计、共享测试计划、ADR 0007 已评审 PASS，合同冻结。
- Action/decision: 冻结阶段 1 开发交接，baseline `294e5eb`（设计包已提交，工作区 clean）。
  - Phase 1 scope：新建 `pi-modeling-agent/`（`package.json`+`package-lock.json`、`README.md`、
    `src/{cli,runner,rpc-session,event-recorder,stage-summary}.mjs`、`extensions/modeling-tools.ts`、
    `workflow/{coordinator,business-organizer,work-unit-modeler,model-reviewer,stage-summarizer}.md` +
    `references/` + `schemas/`、`scenarios/dify-foundations-v1.json`、`lib/`、`tests/`）；迁移
    `.codex/shared_modeling_directory.py`(平移)、`.codex/modeling_handoff.py`、`.codex/modeling_profiles.py`
    到 `pi-modeling-agent/lib/`；把 `.codex/local_modeling_adapter.py` 迁移为内部 `lib/platform_adapter.py`，
    移除 Claude Harness receipt 耦合；`.codex/fast_local_launcher.py` 的启动逻辑替换为 Pi RPC Runner。
    覆盖共享测试计划 A–F 自动合同。
  - Constraints：Pi `@earendil-works/pi-coding-agent@0.81.1`（以 R2.0-001
    `backend/.local/pi-v2-001/package-lock.json` 为基线，不混 upstream commit，见 R2.0-001 P3）；Node
    `>=22.19.0`；RPC `--mode rpc --no-session --approve` + NDJSON；一次性角色完成条件为 `agent_settled`
    + Extension `ctx.isIdle()` + 无 pending + Runner 空队列，**不得**在 `agent_end` 提前接受产物或回收
    子进程（Pi 0.81.1 `docs/rpc.md`、`docs/extensions.md`；本记录 Review disposition round 1 已修正）；
    Runner 必须外部超时 + 显式 kill 回收子进程（R2.0-001 P1）；迁移而非重写确定性核心，保留 candidate
    hash、review 绑定、input fingerprint、capacity-aware Batch 规划、幂等、verify 合同；移除
    `recording_grant`/`recording_health`/`.codex/hooks/modeling_harness.py` 依赖，由 Runner 内部边界信任
    取代；不新增 backend schema、Pi Session/事件公开 API、systemd 单元、远程调度；domain 概念（Dify
    Workflow/Node 等）只出现在场景与测试断言，不进生产代码。
  - Out of phase 1：真实端到端建模运行（测试计划 G）、Claude 路径退役（H）、文档/status 退役同步（I 的
    退役部分）。`.claude`/`.codex` 现有 Claude 建模文件在本阶段保持冻结不动，仅作为回退。
- Evidence: 用户确认（分阶段 + `deepseek/deepseek-v4-flash`）；本记录 Review disposition round 2 PASS；
  Explore 基线报告（迁移源 + 退役目标清单）；`backend/.local/pi-v2-001/{rpc-clarification-probe,integrated-rpc-probe,full-probe}.mjs`。
- Outcome/next step: 交 `requirement_developer` 实现 phase 1，不 commit；完成后交
  `requirement_tester` 独立测试 Round 1（A–F）。G/H 在阶段 1 PASS 后单独启动。

### 2026-07-22T22:21:49+08:00 — phase 1 development-ready and main-agent diff audit — main agent

- Context: `requirement_developer` 返回 development-ready signal；按工作流第 7 步，主 agent 必须亲自核查 diff 与关键约束，不采信报告。
- Action/decision: 核查通过。git 仅 `pi-modeling-agent/`（43 tracked 文件，untracked）+ 本 delivery-record（M）；冻结路径（`.claude`/`.codex`/`skills`/`README.md`/`docs-sync.yml`/`test_documentation_sync.py`/designs/test-plans/architecture/requirements）相对 `294e5eb` 零改动。主 agent 复跑 `npm test` 29/29、`python3 -m unittest discover -s tests` 59/59、`git diff --check` clean。关键约束落实：`src/rpc-session.mjs` 三重完成门（`agent_settled` + Extension `modeling_idle` + 空 `queue_update`，顶部注释明确**不**在 `agent_end` 关 stdin；`gracefulShutdown` SIGTERM→SIGKILL→await exit→无孤儿）；`lib/` receipt/harness 残留 0（仅 `platform_adapter.py:8` 一句说明性注释）；`authorize_runner_write`/`_consume_runner_grant`/`runner_authorization_required` 门禁到位；`backend/app` 无 Pi Session/事件泄漏。真实 `pi@0.81.1` RPC smoke 被 Runner 干净回收（exit 0）。
- Evidence: 主 agent git status / npm test / python unittest / grep 约束核查输出；developer development-ready signal（29/29 + 59/59 + smoke）。
- Outcome/next step: 冻结稳定态（worktree at `294e5eb` + untracked `pi-modeling-agent/`，developer 已停止），交 `requirement_tester` 独立测试 Round 1（A–F）。已知低优先级项：`platform_adapter.py` 残留 7 处 >100 字符行（迁移原文件折行，最长 159，与 `.codex` 原文一致，未折行以保迁移忠实度）；`__pycache__` 已被 `.gitignore` 忽略；G/H/I 退役不在 phase 1。

### 2026-07-22T22:29:14+08:00 — phase 1 independent test Round 1 PASS and findings disposition — main agent

- Context: `requirement_tester` 独立测试 Round 1（A–F）完成，自行重跑全部套件并 review 实现源码，不采信 developer 数字。
- Action/decision: Round 1 **PASS**（phase 1 A–F）。tester 证据：`npm test` 29/29、`python3 -m unittest` 59/59、`git diff --check` clean、冻结路径与 `backend/app` 相对 `294e5eb` 零改动、receipt/Harness grep 0、backend Pi 泄漏 grep 0、tracked 无真实密钥。关键合同独立复核：A 节 `isCompleteEligible()` 三重门 + `RESET_EVENTS`（含 `agent_end`）清空 settled/idle，普通 `agent_end` 无 `agent_settled` 直接 reject，normal/auto-retry/compaction/queued 四情形只在三重信号齐备后完成，超时只杀 victim 无孤儿；D 节三库 byte-identical、`platform_adapter` 清理版（1278→1209 行）、5 个受保护写均 `_consume_runner_grant` 且授权缺失时不触达平台写。
- 主 agent 对 tester 2 条发现的判定：
  - **Medium（`lib/modeling_handoff.py` 死代码，含 Codex CLI supervisor + `skills/ontology-builder/references/modeler-handoff.schema.json` 硬编码）**：**接受为已知项，降级到 H 阶段处理，不阻塞 phase 1**。理由：tester 判定"非 phase-1 阻断""无调用方、未违 ADR/需求边界"；其 schema/supervisor 路径与 `skills/ontology-builder` 去留强耦合，而 skills 去留是 H（退役）的决定，在退役上下文一次处理（删除模块或剥离 Codex supervisor）更准确，避免现在改 H 又改。README Layout 行与交接文字需随最终 disposition 同步。
  - **Low（`platform_adapter.py` ~7 行 >100 字符）**：**已记录，迁移忠实度保留，不阻塞**。Ruff 100 列顺从在关闭阶段或 H 一并 ruff format。
- Evidence: tester Round 1 报告（test-plan `### Round 1`、delivery-record `Independent test rounds` 表）；主 agent 此前 diff audit。
- Outcome/next step: **phase 1（A–F 自动合同）独立测试 PASS，达阶段完成门禁**。按用户"分阶段"策略，暂停并向用户汇报；确认进入 G（真实端到端运行，需 deepseek key + 真实模型调用 + 场景真实资料路径）的准备工作后再启动。Medium/Low 已知项随 H 处理。

### 2026-07-22T23:37:01+08:00 — phase 1 checkpoint committed — main agent

- Context: phase 1（A–F）独立测试 PASS；用户确认"先提交 phase 1，再进 G"。
- Action/decision: 提交 phase 1 checkpoint `2c4a678`（37 文件，11694 insertions）：`pi-modeling-agent/` 全包 + delivery-record + 共享测试计划 Round 1。提交前核查：staged 37 文件；密钥扫描 2 hits 均为 `tests/entry-validation.test.mjs` deliberate test fixtures（`sk-secretvalue123456` / `sk-test1234567890abcdef`，验证 CLI 拒含密钥 scenario）；`.pi/agent` / `node_modules` / `workspaces` / `__pycache__` 均被 `.gitignore` 未进 commit；冻结路径与 `backend/app` 零改动。新 baseline `2c4a678`。
- Evidence: `git commit` → `2c4a678`；post-commit `git status` clean。
- Outcome/next step: phase 1 checkpoint 固化，进入 G（真实端到端建模运行）准备：deepseek key 配置、场景真实资料路径修正（指向 `docs/evaluation-corpora/dify-foundations/snapshots/dify-foundations-2026-07-18-5396c1a/`）、fresh ownership-proven 目标 Project。G 需真实模型调用（成本/时间）与用户在 Brief/CQ/apply 确认点交互。

### 2026-07-23T01:36:41+08:00 — G preparation findings and G1 handoff — main agent

- Context: phase 1 committed (`2c4a678`)；用户确认"主 agent 驱动真实运行"+"创建 fresh 隔离 Project"。驱动 G 前审阅 phase 1 代码确认真实运行入口。
- Action/decision: **范围发现**——phase 1 交付 `ModelingRun` 引擎原语（A–F fake Pi 独立 PASS），但 `src/cli.mjs main()` 只校验+输出 `{"status":"prepared"}` 就 return，**未调用 ModelingRun、未连通端到端真实运行**；无全流程编排器（execute/orchestrate）。phase 1 测试直接 `new ModelingRun()` + fake Pi 驱动单原语，绕过 CLI。这不是 phase 1 缺陷（A–F 范围=引擎原语+fake 测试，真实运行是 G），但意味着 **G 不能直接跑已有 CLI，须先实现端到端真实运行编排器**。另确认：deepseek key 有效（`d['deepseek']['key']`，余额 ¥48.24 CNY，`deepseek-v4-flash` 可用，复用 R2.0-001 `.pi/agent/`）。
- G 拆为两步：**G1（developer）** 实现端到端编排器（连通 cli→ModelingRun 全流程：访谈→Brief/CQ→业务整理→Work Unit 建模→候选合并→评审→authorize+dry-run/apply→验收；真实 Pi 启动；澄清路由可注入 handler；阶段 Summary；局部重跑）+ 环境配置（场景真实资料路径、`.pi/agent` deepseek）+ 编排测试（fake Pi，不调真实模型）；**G2（主 agent）** 创建 fresh Project、写 local.config、驱动真实运行（真实模型）、监看/转达澄清、验收 CQ/检索/provenance。
- Evidence: `src/cli.mjs:186-194`（main 仅 prepared）；`src/runner.mjs`（ModelingRun 原语无 execute）；`grep ModelingRun src/cli.mjs` 空；tests 直接 `driveRole`；deepseek balance API `is_available:true total_balance:48.24`。
- Outcome/next step: 交 `requirement_developer` 实现 G1（不 commit、不调真实模型）；G1 development-ready 后冻结稳定态交 G2（主 agent 驱动真实运行）。

### 2026-07-23T02:16:30+08:00 — G1 implemented, Round 2 PASS with defects, repair round launched — main agent

- Context: G1 developer 返回 development-ready（`orchestrator.mjs` 连通 `cli main`、真实 pi args、clarify/confirm 接缝、3 编排测试、真实 pi smoke exit 0 无孤儿；npm 32/32、python 59/59、冻结路径/backend 零改动、`.pi/agent` deepseek 就绪、无密钥泄漏）；主 agent diff audit 通过。`requirement_tester` Round 2 独立测试 **PASS（G1 自动化门禁）**，独立 probe 发现 4 个被 fake 掩盖的缺陷。
- Action/decision: 主 agent 逐条判定 tester 缺陷：**#1 accepted 必修**（`orchestrator.mjs:669` `_reviewerPrompt` 双引号输出字面 `${ontologyId}`，一行修复）；**#2 accepted 必修**（`_reviewOntology:441-471` REVISE/BLOCKED 只 re-merge 不重生成 Work Unit，3 轮后 throw；设计 Failure and recovery 要求 regenerate；G2 真实 reviewer 大概率 REVISE → 硬阻塞）；**#3 accepted 应修**（`_planAndApply:493-495` dry-run Finding 硬抛不映射 Work Unit；设计要求 map 回 Work Unit 重生成/合并/评审/dry-run）；**#4 accepted 一并修**（`_modelOntology:382,456` 缺 candidate-hash 一致性校验，adapter grant 后盾在，纵深防御）；**#5 low 记录不阻塞**（Summary per-ontology 而非设计字面 per-work-unit，schema 有效，G2 真实运行评估）。
- Evidence: tester Round 2 报告（test-plan `### Round 2`、delivery-record `Independent test rounds` 表）；独立 probe 确认 #1/#2/#3；主 agent G1 diff audit（cli 连通 orchestrator、agent_settled 门、.pi/agent gitignored、secret 0）。
- Outcome/next step: 启动修复轮（`requirement_developer` 修 #1-#4 + 加回归测试覆盖 REVISE 重生成/Finding 映射，fake）；修复后交 `requirement_tester` Round 3 重测，再进 G2（主 agent 创建 fresh Project + 驱动真实 deepseek 运行 + 验收）。

### 2026-07-23T08:25:29+08:00 — G1 Round 3 PASS, committed; G2 first real run failed (read-tool root cause); G2 repair launched — main agent

- Context: G1 修复轮后 Round 3 独立重测 PASS（#1-#4 独立 probe 确认修复，A-F + G1 合同保持，无新缺陷）；G1 编排器 checkpoint 提交 `8881d4d`。G2 真实 deepseek 运行首次启动（主 agent 驱动，fresh Project `52542fa4-5161-4d7e-9c81-cf62a9c95d7c`，deepseek-v4-flash ¥48.19）。
- Action/decision: **G2 失败（exit 1）**。根因：coordinator introduce 成功 settled，但 business-organizer 阶段 `pi exited (code 143 / SIGTERM) before role settlement`（约 9 分钟后）。诊断：`realPiRoleArgs`（orchestrator.mjs:44）用 `--no-builtin-tools`，`ROLE_TOOLS`（runner.mjs:18）无 `read`，但 `_organizerPrompt`（orchestrator.mjs:737）要求 role "Read only these source locators: <资料文件路径>"——**role 被要求读资料文件却没有 read 工具**，模型无法读、行为异常导致 pi exit 143。`pi --help` 确认 `--tools` allowlist 适用于 built-in（read/grep/find）+ extension 工具，故修复方向：给需读资料的 role 在 `--tools` 加 `read`（保留 `--no-builtin-tools` 关闭 bash/edit/write 等危险内置）。另：pi stderr 未记录到 events（recordableClass 不含 stderr），修复轮一并加 stderr 捕获便于后续诊断。
- Evidence: G2 `events.jsonl`（seq 1-10 coordinator introduce settled，seq 11 failure code 143，roles 仅 coordinator，无 business-organizer role_start）；`pi --help`（`--tools` 适用 built-in + extension，内置 read/grep/find）。
- Outcome/next step: 启动 G2 修复轮（`requirement_developer`：ROLE_TOOLS 给 business-organizer/work-unit-modeler/model-reviewer 加 read（+grep）；realRoleLauncher `--tools` 含 read；更新 fake 测试 tools 断言；加 stderr 捕获到 events；真实 pi probe 验证 role 能读资料不 exit 143；npm test 不破坏）。修复后主 agent 重跑 G2。

### 2026-07-23T08:51:34+08:00 — G2 read 修复后二次失败，真根因 queueEmpty（Pi 不发 queue_update），queueEmpty 修复轮 — main agent

- Context: read 工具修复（probe 证明 business-organizer 能读资料）后重跑 G2，**仍失败**（exit 1），与首次相同：coordinator introduce settled → `pi exited (code 143)`，roles 仅 coordinator（business-organizer 未启动），stderr 空。
- Action/decision: 深入诊断 reveal **真根因**（前次 read 误判）：`recordableClass` 含 `queue_update`（会记录 events），但 G2 events **无 queue_update** → 真实 Pi 0.81.1 **不发 queue_update**；`rpc-session.mjs:61` `queueEmpty` 初始 false，**只**由 queue_update（line 217）set → 永远 false；`isCompleteEligible()`（line 130）要求 `queueEmpty` → 永远不满足 → `awaitSettlement` 卡（agent_settled 记录了但 TERMINAL_IDLE/STAGE_END 未记录，证明 driveRole 卡在 awaitSettlement）→ pi idle ~8:48 后 exit 143。fake-pi 模拟 queue_update 故测试通过。两次失败根因相同（coordinator introduce awaitSettlement 卡），read 修复虽有效但非失败根因（business-organizer 未启动到 read 阶段）。
- 修复判定：Pi `agent_settled` 是"队列空 + 无 auto-continue"权威信号（plan review round 1 修正依据），故 agent_settled 时 set `queueEmpty=true`（双信号 settled+idle 仍强，不削弱三重门合同；保留 queue_update 处理若 Pi 未来发）。交 `requirement_developer` 修 + 真实 probe 验证（coordinator introduce 完整 settle 不卡 + 进入 business-organizer）。
- Evidence: G2 events.jsonl（无 queue_update，settled 后无 TERMINAL_IDLE/STAGE_END）；`event-recorder.mjs:90` recordableClass 含 queue_update；`rpc-session.mjs:61,130,217`（queueEmpty 初始 false / isCompleteEligible 要求 / 只 queue_update set）；ts delta settled→failure 8:48。
- Outcome/next step: G2 queueEmpty 修复轮；修复后主 agent 第三次重跑 G2。

### 2026-07-23T09:14:09+08:00 — G2 第三次重跑过 coordinator 关，business-organizer 产物路径/文件名不一致，修复轮 — main agent

- Context: queueEmpty+extensionIdle 修复后第三次重跑 G2，**coordinator introduce 完整 settle**（terminal_idle+stage_end 记录，修复生效），business-organizer 启动并运行到 settle，但 `acceptArtifact` 拒 `artifacts/brief.json`（reason: missing）→ failure。
- Action/decision: 双根因：①**路径不一致**——`realRoleLauncher` env 只设 `PI_CODING_AGENT_DIR` 未设 `PI_MODELING_RUN_DIR`，modeling-tools.ts `runDir` 默认 `cwd/workspaces/modeling-runs/current`，business-organizer 写到 `current/artifacts/`，orchestrator 从 `g2-run-<ts>/artifacts/` 读；②**文件名双后缀**——prompt 让 role 用 name=`brief.json`，Extension `write_modeling_artifact` 写 `${name}.json` → `brief.json.json`，acceptArtifact 读 `brief.json`。证据：`workspaces/modeling-runs/current/artifacts/{brief,coverage,questions}.json.json` 实际存在。修复：`realRoleLauncher` 接受 workDir 并 env 加 `PI_MODELING_RUN_DIR=workDir`（cli.runRealModeling / g2-drive 构造时传 workDir）；modeling-tools.ts `write_modeling_artifact` 不重复 `.json` 后缀（name 已含则不加）。
- Evidence: current/artifacts/brief.json.json 等存在（已清理）；`orchestrator.mjs:66 realRoleLauncher` env 无 PI_MODELING_RUN_DIR；`extensions/modeling-tools.ts:24 runDir` 默认 current、`:68 file=${name}.json`；G2 events artifact_rejected reason=missing locator=brief.json。
- Outcome/next step: G2 路径/文件名修复轮；修复后主 agent 第四次重跑 G2（应进入 confirm → commit_business → Work Unit 建模）。

### 2026-07-23T09:27:31+08:00 — G2 第四次重跑过 business-organizer settle，产物 schema 不符，business-organizer 合同修复轮 — main agent

- Context: 路径/文件名修复后第四次重跑 G2，coordinator + business-organizer 都完整 settle，产物写出（brief/coverage/questions.json 路径+文件名正确），但 `acceptArtifact` 拒 brief.json（reason missing_key:fields）。
- Action/decision: **G1 编排器 business-organizer 合同缺口**：`_organizerPrompt` 只说"Produce brief.json"未指定 schema，business-organizer（deepseek）自由产出 `{domain, scenario_goal, source_documents, core_entities, key_relationships}`，但 orchestrator `acceptArtifact requiredKeys` 期望 `{fields, confirmed_fields}`（brief）/`{competency_questions, coverage_items, work_units}`（coverage），且 `_commitBusiness`/`_initializeDirectory`/`shared_modeling_directory.initialize_run` 消费的平台合同又是另一套（brief 文本/competency_questions/coverage_items/work_units/sources）。fake 测试用恰好符合 requiredKeys 的 fixture 绕过了 schema 明确化。深层修复：统一 business-organizer 产物 schema 跨 acceptArtifact/_commitBusiness/_initializeDirectory，匹配 shared_modeling_directory 平台合同，并在 prompt 明确。
- Evidence: G2 events artifact_rejected reason=missing_key:fields；实际 brief.json keys 与期望不符；`orchestrator.mjs:267 requiredKeys fields/confirmed_fields`、`:270 competency_questions/coverage_items/work_units`；`shared_modeling_directory.py:259 brief=_bounded_text`、`:275-277 competency_questions/coverage_items/work_units`。
- Outcome/next step: G2 business-organizer 合同修复轮（统一 schema + prompt 明确）；修复后主 agent 第五次重跑 G2。

### 2026-07-23T10:36:09+08:00 — G2 第五次过 commit_business PATCH brief，CQ POST 400（ontology 不存在），系统性平台合同对齐发现 — main agent

- Context: R1+R2 修复后第五次重跑 G2，首次跑到 commit_business：coordinator+business-organizer 真实 grounding settle → 3 产物 accepted → confirm_business（1 ontology, 3 work_units, 3 CQs, 10 brief fields）→ adapter start（build_session 创建）+ authorize → commit_business PATCH brief **200 ✅** + GET CQ 200 ✅ + **POST CQ 400**。
- Action/decision: 平台日志定位 POST /competency-questions 400。根因：`interview.py create_question` 验证 `ontology_id` 属于 project，但 Project `52542fa4` fresh 无 ontology（`GET /ontologies` = []）；adapter start 只创建 build_session 不创建 ontology；`.codex` 原版也无 create_ontology（原版假设 ontology 已存在）。且平台 `OntologyCreate` schema 无 client id（平台生成 ontology_id），而编排器用 scenario-slug `ont-dify-foundations-v1` 作 ontology_id——ontology 创建 + id 来源合同不匹配。
- **根本发现（重要）**：G2 defect loop 已 6 轮修复（read/queueEmpty/extensionIdle/路径/文件名/schema/SMD 布局/cwd grounding），每轮一个**真实平台合同/schema 不匹配点**。这暴露 G1 编排器 + 迁移 adapter 与**真实平台合同系统性未对齐**：phase-1/G1 的 fake-Pi + mock-adapter + mock-平台测试让编排器在非真实环境 PASS（Round 1/2/3），但真实平台合同依赖链（ontology 创建/id、CQ-on-ontology 依赖、build_session、brief、coverage/work_unit schema、apply、verify）从未被真实平台验证。G2 真实运行逐个暴露这些 fake/mock 盲区。
- 策略调整：停止"逐轮 defect loop（一次真实运行发现一个合同点）"，改为让 developer **系统性用真实平台逐 action 对齐 adapter**（start/commit_business/dry_run_next/apply_next/verify/finish + ontology 创建/id 绑定 + CQ/coverage/work_unit schema），一次性发现+修复所有真实合同不匹配，再回到 G2 完整真实运行。这减少 defect loop 轮次（每轮真实运行 10–30 分钟 + 深度平台合同诊断，逐轮效率低）。
- Evidence: 平台日志 `POST /competency-questions 400`；`interview.py:288-290 ontology must belong to project`；`GET /projects/{id}/ontologies = []`；`OntologyCreate` 无 id 字段；adapter start 只创建 build_session。
- Outcome/next step: 启动系统性真实平台合同对齐修复轮（developer 逐 action 真实平台验证 + 对齐）；完成后回到 G2 真实运行验收。

### 2026-07-23T11:38:16+08:00 — G2 第六次过 start/ontology 创建，commit-business POST status 422（CQ source_brief_fields 空），系统性产物 schema 补全 — main agent

- Context: 系统性平台合同对齐（ontology 创建/id 绑定 + apply 合同）+ 设 `SEMANTIC_PRODUCT_WRITE_MODE=rdf_primary` 重启后，第六次重跑 G2：coordinator+business-organizer settle → confirm（1 ontology, 5 work_units, 5 CQs）→ start（build_session + **ontology 创建成功**）→ commit-business PATCH brief 200 + POST CQ **201 Created**（系统性对齐生效）→ POST /status **422**。
- Action/decision: 平台 `set_question_status` 要求 approved CQ 必须有 `source_answer_ids` 或 `source_brief_fields`，但 coverage CQ 无 `source_brief_fields`（business-organizer 没产）→ `_question_payload` source_brief_fields=[] → 422。又是 business-organizer 产物 schema 链一个字段缺失。为避免逐轮，启动 developer **系统性补全 business-organizer + work-unit-modeler 产物的所有平台要求字段**（CQ source_brief_fields/importance/query_definition、coverage_items/work_units 字段、modeling item Evidence/command_kind payload），一次性对齐 _organizerPrompt/_workUnitPrompt + 消费点 + 平台合同，写进 prompt 并真实 deepseek probe 验证。
- Evidence: 平台日志 POST /status 422；`interview.py set_question_status`（approved 需 source）；coverage CQ 无 source_brief_fields；`_question_payload` source_brief_fields=[]。
- Outcome/next step: 系统性产物 schema 补全修复轮；完成后主 agent 第七次重跑 G2。

### 2026-07-23T13:57:45+08:00 — G2 checkpoint: 9 real-run rounds advanced to Work Unit modeling, paused on work-unit result→SMD migration gap — main agent + user

- Context: G2 真实运行 defect loop 持续。系统性产物 schema 补全 developer 因 API 错误提前终止（部分完成）；主 agent 自补 CQ source_brief_fields（`_businessManifest` 默认 confirmed_fields）+ stage-summarizer artifact name（prompt 明确 `summary-<stage>`）+ summary array 字段类型指引。
- Action/decision: G2 第七/八/九次重跑持续推进：commit-business POST status approved 过（CQ source_brief_fields）→ stage-summarizer 产物 accepted（name 修复）→ summary validate 过（array 字段类型）→ **Work Unit modeler 全部跑了**（wu-1/2/3/4 启动+settle+artifact_accepted，真实 deepseek 建模 4 Work Unit）。第九次阻塞在 `shared_modeling_directory.py merge`：`unit wu-1 is not ready`。**根因：迁移设计缺口**——原版 `.codex` 经 Claude Harness 提交 work-unit result 到 SMD，迁移版移除 Harness 但 orchestrator `_driveWorkUnit` 只 acceptArtifact 返回，未写入 SMD `units/<id>/result.json`（modeling_items/terms/input_fingerprint）+ 设 status.state=ready；SMD CLI 无 `accept-unit-result` 命令。实质修复（SMD 加提交命令 + orchestrator 提交 + artifact→result schema + status 转换），且 apply/验收可能还有合同点。
- 用户决策：**仅 commit + 暂停 G2**（会话上下文已极大，当前会话完成 G2→H→关闭不现实）。
- Evidence: G2 events.jsonl（roles 含 work-unit-modeler:wu-1..4 artifact_accepted；merge 失败 unit not ready）；units/wu-1/status.json state=pending + 无 result.json；SMD CLI 命令无 accept-unit-result；`.codex` 原版经 Harness。
- Outcome/next step: **G2 暂停 checkpoint**。commit 当前 G2 大量修复（read/queueEmpty/extensionIdle/路径/文件名/business schema/SMD 布局/cwd grounding/系统性平台合同对齐/CQ source_brief_fields/stage-summary name+array + Work Unit 建模推进）。还原 `SEMANTIC_PRODUCT_WRITE_MODE` 至默认（legacy_only）。后续会话继续 G2：①work-unit result→SMD 提交链（SMD accept-unit-result + orchestrator + artifact→result schema）；②apply；③CQ/检索/provenance 验收；然后 H Claude 退役 + 关闭。G2 fresh Project `52542fa4-5161-4d7e-9c81-cf62a9c95d7c`（已提交 ontology/brief/CQ，无 apply）保留供后续。

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |
| 1 | `294e5eb` + untracked `pi-modeling-agent/` (43 files) + modified delivery-record; developer stopped, worktree stable | Phase 1: built `pi-modeling-agent` package; migrated deterministic libraries out of Claude Harness coupling; built Pi RPC Runner + Workflow Package + events/summaries; automated contract tests A–F | developer: `npm ci` (133 pkgs), `npm test` 29/29, `python3 -m unittest` 59/59, `git diff --check` clean, real `pi@0.81.1` RPC smoke 回收 exit 0; main-agent diff audit PASS (`agent_settled` 三重门 / receipt 残留 0 / runner-auth / 无 Pi 泄漏 backend / 冻结路径未动) | developer-ready; independent test Round 1 PASS (A–F); Medium `modeling_handoff` dead-code + Low >100-col lines deferred to H, non-blocking |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| 1 (phase 1, A–F) | HEAD `294e5eb` + untracked `pi-modeling-agent/` (43 files) + modified delivery-record; developer stopped | PASS | Medium: `lib/modeling_handoff.py` dead-codes Codex CLI launcher + `skills/ontology-builder` schema path (breaks at H unless stripped/removed). Low: ~7 >100-char lines in `platform_adapter.py` (migration-fidelity, main-agent-noted). Unexecuted: G real run, H Claude retirement, I retirement cleanup — out of phase 1 | `npm test` 29/29; `python3 -m unittest discover -s pi-modeling-agent/tests` 59/59; `git diff --check` clean; frozen-path + `backend/app` diff empty vs `294e5eb`; receipt/harness grep 0; backend Pi-leakage grep 0; full details in shared test plan `### Round 1` |
| 2 (G1 orchestrator, section G subset) | HEAD `2c4a678` + uncommitted G1 worktree changes only under `pi-modeling-agent/` (`scenarios/dify-foundations-v1.json`, `src/{cli,runner}.mjs`, `tests/fixtures/fake-pi.mjs` modified; new `src/orchestrator.mjs`, `tests/fixtures/fake-adapter.mjs`, `tests/g-orchestration.test.mjs`, `tests/smoke-real-pi.mjs`); developer stopped, not committed | PASS (G1 automated gate) | Medium: `_reviewerPrompt` literal `${ontologyId}` (double-quote not template, `orchestrator.mjs:669`). Medium/High-G2: REVISE/BLOCKED re-merges but does NOT regenerate Work Units (`orchestrator.mjs:441-471`, probe-confirmed `wuLaunches==1`+throw after 3 rounds); masked by fake. Medium: dry-run Finding hard-throws instead of mapping to Work Units (`orchestrator.mjs:493-495`, never waives). Low: no early candidate-hash mismatch check (adapter backstop); per-ontology Summary collapses design's per-Work-Unit + review/apply points. Unexecuted: G2 real model/platform/CQ/provenance, H retirement, I retirement cleanup; `smoke-real-pi.mjs` manual (needs gitignored `.pi/agent`) | `npm test` 32/32; `python3 -m unittest discover -s pi-modeling-agent/tests` 59/59; `git diff --check` clean; frozen-path + `backend/app` diff empty vs `2c4a678`; secret/receipt/backend-leakage grep 0; scenario locators exist + business-input-only; independent probes confirm 3 masked gaps; full details in shared test plan `### Round 2` |
| 3 (G1 orchestrator repair retest) | HEAD `2c4a678` + uncommitted G1+repair worktree changes only under `pi-modeling-agent/`; repair round touched ONLY G1 untracked files (`src/orchestrator.mjs`, `tests/g-orchestration.test.mjs`, `tests/fixtures/fake-adapter.mjs`; pre-repair G1 tracked mods `scenarios/dify-foundations-v1.json`, `src/{cli,runner}.mjs`, `tests/fixtures/fake-pi.mjs` unchanged by repair); developer stopped, not committed | PASS (#1-#4 fixed, no regression) | None. Round 2 #1 (`_reviewerPrompt` now backtick template), #2 (REVISE/BLOCKED -> `_regenerateAffected` re-fires `_driveWorkUnit`, bounded by `MAX_REVIEW_ROUNDS(3)`, never applies), #3 (dry-run Finding surfaced to stabilization loop -> regenerate/merge/review/re-dry-run, never waived), #4 (`_reviewOnce` ok only on PASS+matching hash; mismatch -> `candidate_hash_mismatch` regeneration) all independently confirmed. Race-fix triple-gate (`agent_settled`+idle+empty, `RESET_EVENTS` incl `agent_end`), one-shot authorize, business-confirm gate, dispose-no-orphan intact. Residual (non-blocking, G2): #5 Summary granularity; finding locator fidelity + BLOCKED-as-recoverable semantics depend on real reviewer; `_verificationDoc` placeholder; CLI confirm/clarify left throwing for G2 host wiring. Unexecuted: G2 real run, H retirement, I retirement cleanup; `smoke-real-pi.mjs` manual | `npm test` 37/37; `python3 -m unittest discover -s pi-modeling-agent/tests` 59/59; tester's own `/tmp/r3-probe.mjs` 12/12 (deliberately different targets: REVISE/Finding on the OTHER unit, transitive-dep expansion, REVISE+wrong-hash combo); `git diff --check` clean; frozen-path + `backend/app` + `docs/delivery/designs` diff empty vs `2c4a678`; secret/receipt/backend-leakage grep 0; full details in shared test plan `### Round 3` |

## Design-phase verification

- Required checks: mandatory plan review PASS; `git diff --check`, interface-doc sync, focused
  documentation contract tests, and GitNexus change detection PASS.
- Runtime/restart health: not applicable during requirement refinement.
- Documentation/status sync: requirement, ADR, design, test plan, and record aligned; implementation
  status deliberately remains pending.
- Cleanup: no runtime data created by R2.0-002 refinement.
- Residual risks and follow-ups: implementation must prove the reviewed lifecycle, project trust,
  fixed-version installation, real modeling quality, and post-Claude-retirement regression; none is
  claimed complete by this design delivery.

## Retrospective

- Scope or design deviations: pending.
- Rework and root causes: pending.
- What shortened or delayed delivery: pending.
- Reusable lessons: pending.

### 2026-07-23T15:24:39+08:00 — R2.0-002 暂停推进，R2.0-003 记录重构背景 — main agent + user

- Context: 对 R2.0-002 原需求、设计、共享测试计划、真实 G2 运行和当前提交重新审计。现有
  `11f60f2` 已保留 Pi Runtime 基础与真实运行至 Work Unit 的检查点，但 merge、独立 review、
  dry-run/apply、应用后 CQ/检索/provenance、Claude 退役和最终独立 PASS 均未完成。同时现有
  流程的目标与质量门禁逐渐把业务文档建模收敛为知识图谱构建，不能代表新的 Ontology 建模目标。
- Action/decision: 用户确认 R2.0-002 标记为“暂不继续推进”，保留代码、测试、设计、真实运行
  证据和 Project 检查点，不把它标记为已实现，不继续原 G2 链路，也不退役 Claude。新增
  R2.0-003“本体建模流程重构”，本次只记录背景、方向和待细化问题；明确不以“双轨建模”命名或
  预设最终方案。
- Evidence: `docs/requirements/requirements-v2.0.md` R2.0-002/R2.0-003；本记录 G2 checkpoint；
  shared test plan Round 1-3 及未执行门禁；commit `11f60f2`。
- Outcome/next step: 当前无实施中 v2.0 需求。后续从 R2.0-003 的功能细化开始，再决定 R2.0-002
  未完成链路和既有 Workflow Package 的复用、调整或替换范围。
