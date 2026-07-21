# R1.1-005 Claude Code 双主 Agent 建模交互评测 Harness Delivery Record

- Requirement source: `docs/requirements/requirements-v1.1.md` R1.1-005
- Status: in-progress (`fast-local` optimization extension)
- Started: 2026-07-20T22:38:22+08:00
- Last updated: 2026-07-21T18:26:41+08:00
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

## Fast-local optimization extension timeline

### 2026-07-21T17:13:47+08:00 — settled-scope audit and refinement — user and main agent

- Context: 真实本地双 session 运行仍要求操作者分别启动、输入首条 prompt，并让建模 Agent 临场
  寻找平台鉴权。当前 modeler 从进程启动到人工首条 prompt 约 3 分 29 秒，Hook 激活约 53 秒，
  随后至少 8 分 11 秒执行 37 次 Bash 且没有调用 ontology-platform MCP；项目已有
  `.claude/ontology-mcp.json`，但启动命令未加载它，反而加载了多个无关全局 MCP。
- Action/decision: 用户确认按双配置建议交付：保留原 `strict-eval` 作为 R1.1-005 正式硬门禁，
  新增不作为正式验收证据的 `fast-local` 本地迭代配置。fast-local 固定版本化场景和资料路径，
  自动创建新 Build Session、准备两个已绑定的 Claude session、启动两个终端并注入首条 prompt；
  modeler 只加载 ontology-platform MCP，simulated user 不加载 MCP。非建模环节以基本可用为准。
- Credential decision: 用户明确本地 API key 暂不要求进一步加固；允许从 gitignored、权限受控的
  本地文件或 `backend/.env` 读取，但任何拟提交文件、暂存 diff 和本次提交新增历史都不得包含
  API key 原文。设计和测试不得把 credential 写入文档、场景、命令示例或测试夹具。
- Existing worktree baseline: HEAD `e7c4dd4`;已有未提交修改为
  `.claude/agents/ontology-modeling-agent.md`、`.claude/agents/simulated-user.md` 和
  `.codex/hooks/modeling_harness.py`。这些改动属于本次启动简化探索，后续实现可以吸收或替代其
  具体机制，但不得丢失 activation parser 对命令尾随 shell token 的兼容修复。
- Boundary: 不修改 backend/API/schema/frontend，不新增平台 Agent Runtime，不降低 simulated
  decision provenance 或平台事实权威；strict-eval 的 nonce、Hook 回执、participant replacement、
  真实双 session 和 structured summary 合同保持不变。
- Evidence: `docs/requirements/requirements-v1.1.md` R1.1-005 与“需求变更与代码落点规则”；
  `.claude/modeling-harness.md`；`.claude/ontology-mcp.json`；当前 Harness metadata/events 和 Claude
  可见 tool-use 记录。
- Outcome/next step: 对预设 session ID、严格 MCP 隔离和 Build Session 自动创建做最小真实探针，
  再追加设计与共享测试计划并进入独立 plan review。

### 2026-07-21T17:18:00+08:00 — risk probes and extension contract freeze — main agent

- Probe 1, Build Session automation: 使用 gitignored 本地 credential 通过真实
  `POST /api/projects/{project_id}/build-sessions` 创建唯一 session
  `8abbc06c-733d-42db-8ae8-d99b9f9cddc6`，返回 201/active；随后按 revision 调用 cancel，返回
  200/cancelled。key 未输出。设计结果：launcher 可复用 REST，不需要 backend 改动。
- Probe 2, predetermined Claude session: 当前 Claude CLI 使用调用方 UUID 启动 `-p` session，
  最终 envelope 原样返回同一 session ID，约 10.4 秒完成且无需人工首条 prompt。一次让 LLM 自行
  执行严格 activation 的探针没有产生 Harness metadata，证明 fast-local 不能把预绑定继续交给
  prompt 自律；设计采用 launcher/Harness 确定性 `prepare-fast`，Hook 再核对实际 session ID。
- Probe 3, MCP isolation/authentication: 持久化 Claude strict-config 探针的 transcript 只引用
  `ontology-platform`，未引用已配置的全局 MCP；真实 Python MCP stdio client 从
  `.claude/ontology-mcp.json` 等价命令启动服务，列出 64 个工具并成功调用
  `get_project_build_context`。唯一 Claude probe transcript 已移入桌面回收站。
- Contract freeze: 复用 R1.1-005，不新增一级需求。设计和共享测试计划追加 fast-local profile；
  strict-eval 身份与正式硬门禁不变。现有三处未提交探索改动纳入 developer handoff，允许以更确定
  的 pre-binding 机制替代 Agent 自激活文本，同时必须保留 activation parser 修复。
- Evidence: `docs/delivery/designs/2026-07-20-r1-1-005-claude-dual-agent-harness-design.md`；
  `docs/delivery/test-plans/2026-07-20-r1-1-005-claude-dual-agent-harness-test-plan.md`；真实探针命令
  输出保留在本次 agent session，未写入 credential 或原始 Claude transcript。
- Outcome/next step: 进入 mandatory plan review；PASS 前不实施产品代码。

### 2026-07-21T17:31:00+08:00 — fast-local plan review Round 1 — plan_reviewer and main agent

- Result: **REVISE**, 0 Critical and 3 High. Main agent accepts all three as requirement-relevant.
- High 1, accepted-high: existing `run_lock` is per run while `.sessions` registry is global, so two
  run IDs can claim one UUID and partial writes can leave metadata/registry disagreement. Plan now
  requires one root registry lock for all registry mutations, incomplete preparation marker,
  Hook rejection, preparation-ID-scoped cleanup/repair, cross-run concurrency and per-write fault
  injection tests.
- High 2, accepted-high: HTTP idempotence depends on reusing the same `client_session_id` and payload;
  a crash after 201 but before local persistence would orphan a Build Session. Plan now persists a
  credential-free launch intent before POST, reuses it on retry, and validates Project ownership plus
  active state for explicit recovery sessions. Crash-after-201, payload drift, foreign and terminal
  recovery tests are mandatory.
- High 3, accepted-high: installed Claude declares variadic `--mcp-config <configs...>` and can consume
  a following prompt as another path. Plan freezes single-token `--mcp-config=<path>`, all named
  options before the final prompt, exact argv assertions and a real prompt/session/MCP-source probe.
- Preserved finding: reviewer confirmed the existing dirty trailing-token activation parser fix is
  explicitly covered; `summary_policy=explicit` terminal split was sufficiently designed and was not
  a High finding.
- Evidence: plan_reviewer report against current requirement/design/test plan and source lines in
  `.codex/hooks/modeling_harness.py` plus `backend/app/services/build_sessions.py`.
- Outcome/next step: revised design and shared test plan return to plan_reviewer Round 2. No product
  implementation has started.

### 2026-07-21T17:36:00+08:00 — fast-local plan review Round 2 — plan_reviewer and main agent

- Result: **REVISE**, 0 Critical and 1 High; the three Round 1 mechanisms exist, but preparation
  commit ordering remained inconsistent.
- Finding, accepted-high: the plan set metadata ready before appending required activation events.
  An event failure could therefore trigger registry cleanup while metadata remained active,
  contradicting the fault-injection acceptance contract.
- Plan change: all state, registries and required bounded events are now pre-commit writes while
  metadata remains incomplete; the final `preparation_complete=true/status=active` metadata write is
  the last required durable write and sole commit marker. Retry deduplicates pre-commit events and
  repairs only incomplete preparation-owned registries.
- Outcome/next step: return corrected commit-point protocol to plan_reviewer Round 3.

### 2026-07-21T17:39:00+08:00 — fast-local plan review Round 3 — plan_reviewer and main agent

- Result: **PASS**, 0 Critical and 0 High.
- Evidence: required metadata/state/registries/events remain pre-commit; incomplete preparation is
  Hook-invisible; final ready metadata replacement is the sole and last commit marker. Tests separate
  pre-commit cleanup/retry from committed state and forbid registry rollback after commit.
- Disposition: all Round 1–2 High findings are closed. Registry concurrency, Build Session crash
  recovery, MCP argv parsing, credential diff gate, explicit summary, strict/legacy compatibility
  and trailing-token activation-parser preservation remain covered.
- Outcome/next step: plan gate passed; freeze developer handoff against the reviewed current files.

### 2026-07-21T17:54:45+08:00 — fast-local implementation DEVEL_READY — requirement_developer and main agent

- Implemented: 新增 `.codex/fast_local_launcher.py`，把场景校验、credential 读取、Build Session
  创建/恢复、耐崩溃 launch intent、Harness `prepare-fast`、active locator 和两个 Claude 终端命令
  收敛为一次启动；新增固定 Dify 场景、最小/空 MCP 配置、可提交配置模板和两个角色的
  fast-local 启动说明。
- Harness changes: 全局 session registry mutation 统一使用 root lock；fast preparation 采用
  incomplete metadata、state、registries、去重 events 的 pre-commit 协议，最后一次 ready metadata
  replacement 才是 commit marker；Hook 拒绝 incomplete preparation；fast-local 使用显式 summary，
  strict-eval 和 legacy 路径保持原合同。
- Verification: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .codex/tests -q`
  为 63 tests PASS；Ruff check/format、JSON parse、`git diff --check` 和本地 key 原文扫描均 PASS；
  fake HTTP + 真实 Harness subprocess 的 no-launch 集成 PASS。
- Safe live behavior: 对真实本地配置运行 `--no-launch` 时，在任何 POST 前识别出当前 strict
  active locator 仍为 non-terminal 并按设计拒绝；没有覆盖 locator、创建 Build Session 或启动终端。
- Stable handoff: implementation digest
  `d8ae11b817d24566101f679ca15c56b53c3155f49015bc9e734c13686e1e342b`；测试代理必须基于此状态
  独立验证，且不得覆盖当前 strict run。
- Outcome/next step: developer status `DEVEL_READY`; enter independent test Round 3.

### 2026-07-21T18:07:44+08:00 — fast-local independent test Round 3 — requirement_tester

- Result: **TEST_FAIL** on stable digest
  `d8ae11b817d24566101f679ca15c56b53c3155f49015bc9e734c13686e1e342b`.
- High: 真实 Claude Code 2.1.74 使用 launcher-shaped argv 时，modeler 未获得
  ontology-platform MCP，modeler 与 simulated user 都继承了额外 user/plugin MCP；因此
  `--strict-mcp-config` 本身不足以兑现 modeler-only/empty MCP 隔离合同。
- Medium: `repo_path()` 在调用者执行 file-or-directory 判断之前先要求 `is_file()`，导致存在的
  snapshot 目录被误报不存在；默认 `manifest.json` 文件路径未触发此问题。
- Passed evidence: 63 tests、Ruff、JSON/diff、真实唯一 Build Session create/cancel、直接 MCP
  64-tools/query、active locator 保护和实际 key 原文扫描均 PASS；当前 strict run 未修改。
- Cleanup: 三个唯一 Claude probe transcript/session-env 已精确移入桌面回收站；真实 probe Build
  Session 已取消。原始插件诊断意外包含无关本机 secret，因此未写入仓库或交付记录。
- Outcome/next step: return both accepted findings to requirement_developer; freeze a new digest and
  require independent Round 4. Round 3 remains append-only evidence.

### 2026-07-21T18:19:20+08:00 — Round 3 repair DEVEL_READY — requirement_developer and main agent

- High repair: 两个 Claude argv 增加单 token `--setting-sources=project`，并在任何 launch intent、
  health/API POST、Harness 或 locator 写入前执行 captured MCP inventory compatibility probe。
  modeler 必须恰好得到 ontology-platform，simulated user 必须没有 MCP；原始 stdout/stderr 永不
  输出或持久化，无法证明隔离时只返回有界升级/strict-eval 诊断。
- Current-runtime evidence: 本机 Claude Code 2.1.74 仍无法从 CLI-supplied config 看到
  ontology-platform，因此真实 launcher 在平台 mutation 前 exit 2，并明确要求升级至已验证的
  2.1.215+；active locator hash 未变化，没有 launch intent、Build Session 或 GUI 进程。
- Medium repair: `repo_path()` 现在显式区分 `file`、`directory` 与 `any`；scenario/config/env
  仍要求 regular file，corpus 接受仓库内文件或目录，repo 外路径继续拒绝。
- Verification: 全套 66 tests、Ruff check/format、JSON、diff、实际 key 原文扫描和 runtime health
  均 PASS；两个唯一 probe transcripts 已精确移入桌面回收站；无 backend/frontend 改动或 restart。
- Stable handoff: 统一使用列出顺序的标准 `sha256sum FILES... | sha256sum`，10-file developer
  surface digest 为 `c839e5fc0a36ccb426e6b15fe6425aa150ecea4e9f58af1b769012ce44a06db1`。
  先前报告的 `0c04...` 使用自定义 filename/NUL/content 聚合，文件本身未变化，后续不再使用。
- Outcome/next step: enter independent Round 4 against the standard digest.

### 2026-07-21T18:26:41+08:00 — fast-local independent test Round 4 — requirement_tester

- Result: **TEST_FAIL** on matching digest
  `c839e5fc0a36ccb426e6b15fe6425aa150ecea4e9f58af1b769012ce44a06db1`.
- Closed from Round 3: 真实 Claude 2.1.74 在 0.67 秒内 bounded fail-closed；mock-bypass locator 后
  证明 `prepare_intent=0`、HTTP=0，locator/intents 均不变。默认 manifest、真实 snapshot 目录、
  file corpus 均通过，错误目录类型与 repo 外路径按合同拒绝。
- New High: MCP inventory 接受逻辑在整行做 server-name 子串匹配，且没有要求目标行状态为
  Connected；`ontology-platform-shadow`、其他 server 的 command/path 含目标词、目标 server
  Failed to connect 三种伪清单都被误接受，不能作为 exact isolation proof。
- Other evidence: 66 tests、Ruff、JSON/diff、直接 MCP 和 actual-key scan PASS；当前 strict locator
  未改；tester 只追加共享 test plan。
- Outcome/next step: repair exact parsed server identity plus connected-state validation, then run
  independent Round 5. Round 4 remains append-only evidence.
