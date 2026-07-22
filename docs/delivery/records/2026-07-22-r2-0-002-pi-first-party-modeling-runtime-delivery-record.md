# R2.0-002 Pi 第一方建模 Agent Runtime 正式集成 Delivery Record

- Requirement source: `docs/requirements/requirements-v2.0.md` R2.0-002
- Status: in-progress
- Started: 2026-07-22T16:30:00+08:00
- Last updated: 2026-07-22T20:16:40+08:00
- Design: `docs/delivery/designs/2026-07-22-r2-0-002-pi-first-party-modeling-runtime-design.md`
- Shared test plan: `docs/delivery/test-plans/2026-07-22-r2-0-002-pi-first-party-modeling-runtime-test-plan.md`
- Delivery baseline: `d6f8255`; clean `main...origin/main`
- Design package commit: this commit
- Delivery commit: pending implementation

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

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |

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
