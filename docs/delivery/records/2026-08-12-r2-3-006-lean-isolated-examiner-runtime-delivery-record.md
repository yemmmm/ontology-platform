# R2.3-006 精简隔离 Examiner Runtime Delivery Record

- Requirement source：`docs/requirements/requirements-v2.3.md#r23-006-精简隔离-examiner-runtime`
- Status：implementation in progress（用户已授权，真实 App Server probe PASS）
- Started：2026-08-12T16:34:22+08:00
- Last updated：2026-08-12T22:04:00+08:00
- Design：`docs/delivery/designs/2026-08-12-r2-3-006-lean-isolated-examiner-runtime-design.md`
- Shared test plan：`docs/delivery/test-plans/2026-08-12-r2-3-006-lean-isolated-examiner-runtime-test-plan.md`
- Delivery baseline：`8b3ae42 Accept R2.3-003 retained-scope modeling`
- Delivery commit：`Define R2.3-006 lean Examiner runtime`（`git log -- <本文件>` 可解析 immutable hash）

## Confirmed contract

- Current behavior：R2.3-003 Acceptance-only 语义与 formal settlement PASS，但 Examiner 每次调用约 26k–33k
  input tokens，CQ1/CQ2 Platform 分别 17/13 model calls；Platform 请求曾通过主 Agent转发并补问完整 CQ、scope、
  envelope/digest。
- Target behavior：fresh zero-history Source/Platform、report-only Acceptance、direct strict proxy、无横向补问、
  missing input typed BLOCKED、正常每个 Examiner<=3 turns，并保留 token/latency/proxy 分解证据。
- In scope：formal semantic Acceptance 三类 Agent 的最小 role packet、transport/proxy capability、typed output、
  metrics、R2.3-003 read-only regression 和 R2.3-005/default isolation。
- Non-goals：backend/CQ 专属 API、全局 Codex 指令重写、所有 subagent runtime、跨机器/L3 productization、重新
  执行 003 建模。
- Acceptance summary：上下文和路由隔离、direct proxy、N-CQ、<=3 turns、性能报告、无写入、撤钥清理和独立
  tester PASS。
- Refinement：用户明确认可上述后续形态并要求形成新需求号；编号定为 R2.3-006。003 未使用授权随已关闭
  需求失效，不自动转移。

## Timeline

### 2026-08-12T16:34:22+08:00 — source/current-state audit — main agent

- Context：用户认定 R2.3-003 PASS，要求检查收尾并把已认可的 Examiner 后续形态形成新需求。
- Evidence：HEAD `8b3ae42`；工作树 clean；`ontology-platform.service` active；backend `/api/health` 200；frontend
  200；Acceptance operation root 无 Unix socket、无 live_host/process。
- Decision：003 无剩余强制收尾。保留 gitignored operation evidence；最后一次未使用授权不跨需求继承。
- Outcome：建立 R2.3-006，当前仅需求/设计，不启动 Agent 或实现代码。

### 2026-08-12T16:34:22+08:00 — risk probe and design consequence — main agent

- Probe：复核 R2.3-003 start20-2 session token/turn 时间线与 service access log。
- Result：Platform 每轮实际 input 约 26k–33k，cached prefix 约 25k–32k；CQ1/CQ2 Platform 为 17/13 model
  calls。read-model entities/facts 两次 HTTP 分别在相邻约 1 秒内 200。
- Consequence：优先修 role context、transport 和 direct proxy，不先改查询 API。查询清晰度只在精简后仍有
  具体 missing-fact 证据时另行评估。

### 2026-08-12T16:34:22+08:00 — requirement/design/test-plan draft — main agent

- Action：新增 R2.3-006 权威条目、current-minimal design 与单一 shared test plan；把 performance、隔离、失败
  行为、non-goals 和 future productization 分开。
- Outcome：等待 mandatory plan review；未实现、未测试 runtime、未修改 live state。

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |
| 1 | Exact proxy 不可由当前 silent schema filtering 满足 | accepted-high | `acceptance_runtime.py` 当前过滤 schema properties 后继续 call | 规定 per-tool exact args、forward 前拒绝、backend_calls=0 |
| 1 | Persistent Acceptance 保留前题上下文 | accepted-high | 现有 package/Runner 明确 persistent session | 改为每题 fresh Acceptance，Host 机械聚合 ordered verdict |
| 1 | 无 context/token/TTFT/step 可执行证据 | accepted-high | Codex runtime 当前只保留 first_turn_input/turn id，无 tokenUsage metrics gate | 增加真实 App Server probe、ExaminerRunMetrics/v1 和第4 step前中断 |
| 2 | Round1 三项闭环，无新 Critical/High | accepted-pass | reviewer 复核 requirement/design/test plan | plan frozen；implementation probe 保留为完成门 |

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |
| 0 | `8b3ae42` + docs draft | No implementation requested | docs review pending | pending |
| 1 | review Round1 | Three design blockers confirmed; no code defect cycle | docs revised | re-review pending |
| 2 | reviewed docs | No implementation yet | plan review PASS | development-ready |
| 3 | `6d0063b` clean worktree | User authorized implementation; real App Server token-usage probe PASS | Codex CLI 0.147.0 emitted bound usage before completion | developer handoff pending |
| 4 | implementation diff, no commit | Lean role packets/runtime, exact proxy schemas, App Server metrics observer, report-only Acceptance package and focused regressions implemented | focused 13/13; affected R2.3-005/runtime 74/74; compile/diff checks PASS | development-ready; independent test pending |
| 5 | independent test Round 1 | Three production P0 defects: unreadable child packet/source, generic message-route leak, report-before-completed race/premature wall metric | focused 13/13; full modeling_team 517 PASS + 1 SKIP; adversarial production-seam repros FAIL | returned to developer |
| 6 | P0 defect fix, no commit | Inline immutable packet plus UTF-8 source text replaced the unusable file-read instruction; lean agent-message delta/completion no longer enters generic messages; report validation now waits for provider terminal notification and terminal timing | focused 20/20; affected runtime/R2.3-005 74/74; full modeling_team 523 PASS + 1 SKIP; Ruff/compile/diff checks PASS | development-ready; independent Round 2 pending |
| 7 | independent test Round 2 | Round 1 defects fixed; Source locator still accepted non-approved paths, Platform locator accepted coordinates not present in current proxy receipts, and no retained N=2/key operation boundary existed | focused 20/20; affected 52/52; full modeling_team 524 PASS + 1 SKIP; direct adversarial locator submissions FAIL | evidence binding returned to developer; operation boundary pending |
| 8 | evidence-binding defect fix, no commit | Source locators now bind approved manifest paths to Host-derived IDs; Platform locators bind one-to-one to current child receipts and page metadata; Acceptance refs are restricted to the current reports' ID union | focused 23/23; affected 74/74; full modeling_team 526 PASS + 1 SKIP; changed Ruff/compile/diff checks PASS | development-ready; independent Round 3 pending |
| 9 | independent test Round 3 | Source and Acceptance binding passed; Platform validator incorrectly treated all calls in one child as one page chain, rejecting two tools that each returned an independent single page | focused 23/23; affected 55/55; full modeling_team 527 PASS + 1 SKIP; direct multi-tool locator repro FAIL | narrow page-sequence fix returned to developer; real N=2/key operation remains pending |
| 10 | Platform page-sequence fix and independent Round 4 | Receipt/report order remains one-to-one; ordinal 0 starts a new sequence, while ordinal >0 requires same-tool cursor continuity. Independent multi-tool, repeated-tool and adversarial sequence checks passed | focused 23/23; affected 55/55; full modeling_team 527 PASS + 1 SKIP; 9/9 Platform and 10/10 Source/Acceptance adversarial checks PASS | evidence binding closed; callable retained N=2/key operation is the only remaining completion gate |
| 11 | callable operation and independent Round 5 | Added a standalone retained-workspace N=2 operation seam and deterministic cleanup tests. Independent review found incomplete retained ticket/inventory binding, partial-create cleanup, repeated revoke after post-side-effect proof failure, permissive metrics, and secret-bearing injected evidence | operation/lean 27/27; affected 59/59; full modeling_team 531 PASS + 1 SKIP; production adversarial seams FAIL | returned to main for narrow operation-boundary repair; no key/provider/N=2 executed |
| 12 | Round 5 defect repair, no live operation | Operation now binds the immutable ticket digest, its six-tool request allowlist, before inventory/model state, live counts and ledger; create attempts reconcile residue, one revoke attempt is never replayed, metrics are strict, and secret-bearing evidence is rejected before persistence | operation/lean 30/30; affected runtime/R2.3-005 104/104; Ruff/compile/diff checks PASS | independent Round 6 pending |
| 13 | independent Round 6 and in-round closure | Production forwarder was narrowed from the global inventory to the retained six tools; bool/NaN/inconsistent token metrics were rejected; empty partial-create inventory became an explicit cleanup failure and cleanup errors take precedence | focused 30/30; affected 62/62; full modeling_team 534 PASS + 1 SKIP; changed Ruff/compile/diff checks PASS | deterministic operation boundary PASS; authorized real retained N=2 operation may start |
| 14 | `d5410ad` clean implementation commit; first real operation preflight | The authorized production operation started the provider/bootstrap-admin boundary, then failed closed before Project read-key creation because `workspace-context` does not expose `workspace_version`; finally cleanup revoked the bootstrap admin key and stopped the provider | no Examiner thread or Project key created; active `r23006-retained-admin`=0, active Project keys=0, output root contains no evidence file; service active/200/200 | authorization was not consumed; field ownership defect returned for narrow repair |
| 15 | `d5410ad` + snapshot-only diff; independent Round 7 | Snapshot now reads `modeling-context` and validates its nested workspace version while retaining workspace state/default graph checks on `workspace-context`; build-context index and volatile `generated_at` exclusion remain correct | operation+lean 30/30; backend context API 21 PASS; platform scope 9/9; Ruff/compile/diff PASS; direct read-only live service values match retained state/version | snapshot repair independently PASS; ready for a fresh-output real operation |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| 0 | docs draft | UNEXECUTED | requirement implementation not started | shared plan §4 |
| 1 | initial implementation | FAIL | packet readability, generic message leak, report/completion race | shared plan §5 |
| 2 | runtime P0 fixes | FAIL | Source/Platform evidence binding and callable retained operation missing | shared plan §6 |
| 3 | evidence-binding fixes | FAIL | independent Platform calls were forced into one page sequence; retained operation unexecuted | shared plan §7 |
| 4 | page-sequence fix | PASS (narrow scope) | retained real N=2/key operation deliberately unexecuted | shared plan §8 |
| 5 | callable operation first implementation | FAIL | partial key lifecycle, retained ticket/inventory, metrics and secret evidence gates | shared plan §9 |
| 6 | callable operation defect closure | PASS (deterministic scope) | real provider/key/N=2 still unexecuted | shared plan §10 |
| 7 | production snapshot field-ownership repair | PASS (narrow scope) | real provider/key/N=2 still unexecuted | shared plan §11 |

## Final verification

- Required checks：pending plan review；当前只需 docs diff/check。
- Runtime/restart health：baseline active/200/200；无 runtime code change。
- Documentation/status sync：requirements/design/test plan/record 已起草，待 review 后冻结。
- Cleanup：无新 runtime/live artifact。
- Residual risks and follow-ups：能否机械移除 inherited history/collaboration tools 需实施阶段以真实 context inventory
  证明；不能只依赖 `fork_turns=none` 声明。

## Retrospective

- Scope/design deviations：none yet。
- Rework/root cause：R2.3-003 的两分钟级延迟主要来自大 cached prefix、多轮消息和人工转发，而非 backend。
- What shortened delivery：复用 003 final workspace、strict proxy、typed report/verdict 和 positive-N 证据。
- Reusable lesson：fresh role 的独立性必须由输入清单和 transport/tool gate 证明，不能只靠 Agent 名称或 prompt。

### 2026-08-12T16:49:00+08:00 — mandatory plan review Round 1 — plan reviewer

- Result：REVISE；3 High，主 Agent全部认定 `accepted-high`。
- Findings：现有 proxy 会 silent-filter unknown args；persistent Acceptance thread 与当前题隔离矛盾；runtime 无
  tokenUsage/context inventory/TTFT/step budget 的机械证据。
- Decision：不扩展 backend。修订为 per-tool exact pre-forward schema、每题 fresh Acceptance、Runner-owned
  `ExaminerRunMetrics/v1`、真实 App Server tokenUsage probe 和第4 inference step前 fail-closed 中断。
- Outcome：需求/设计/测试计划已修订，返回同一 reviewer Round2。

### 2026-08-12T16:52:00+08:00 — mandatory plan review Round 2 — plan reviewer

- Result：PASS；Round1 三项 High 全部闭环，无新 evidence-backed Critical/High。
- Evidence：exact pre-forward schema、每题 fresh Acceptance、`ExaminerRunMetrics/v1`/真实 tokenUsage probe/step
  budget 已进入 requirement/design/shared plan。
- Residual implementation gates：实施时冻结 tokenUsage 事件实际粒度、task/evidence token 可重算算法和
  inference-step 计数定义；这些是已计划 probe/metrics 门，不是当前设计 blocker。
- Outcome：R2.3-006 development-ready，等待用户后续授权实施；本轮不启动 Agent runtime、不创建 read key、
  不消费 semantic modeling authorization。

### 2026-08-12T17:34:01+08:00 — implementation authorization and risk probe — main agent

- Authorization：用户以“继续”解除 delivery record 中“待用户后续授权实施”门；只授权按 reviewed R2.3-006
  实施，不授权 semantic modeling start，也不转移已关闭 R2.3-003 的剩余授权。
- Baseline：`6d0063b Define R2.3-006 lean Examiner runtime`，初始 worktree clean，`origin/main` 同步。
- Probe：使用真实 `codex-cli 0.147.0 app-server --stdio` 启动 ephemeral fresh thread，单轮输入要求只回复
  `DONE`，无平台 key、ontology、ledger 或 semantic start。
- Evidence：App Server 依次发出 `thread/started`、`turn/started`、`thread/tokenUsage/updated`、
  `turn/completed`；usage notification 精确绑定 `threadId`/`turnId`，包含 `last`、累计 `total`、
  `inputTokens`、`cachedInputTokens`、`cacheWriteInputTokens`、`outputTokens`、
  `reasoningOutputTokens`、`totalTokens` 和 `modelContextWindow`。本次一个 turn 只收到一个 usage event，位于
  completion 前约 4ms；实现须支持同 turn 多次累计事件并按相邻累计值求增量。
- Outcome：冻结实际 method 为 `thread/tokenUsage/updated`；metrics 不再依赖 session 账单估算，可以进入
  developer handoff。GitNexus 索引损坏已通过删除并完整重建本仓库代码索引恢复，未改业务源码。

### 2026-08-12T17:35:44+08:00 — frozen development handoff — main agent

- Stable state：HEAD `6d0063b`；唯一 diff 为本 delivery record 的授权/probe 追加记录，developer 不得编辑本文件。
- Reviewed inputs：R2.3-006 requirement、Development-ready design、reviewed shared test plan；plan review Round2
  PASS，Round1 三项 High 已接受并闭环。
- Impact：`RunnerAcceptanceCarrier` HIGH（19 direct/42 total），`_CodexChildResource` CRITICAL
  （30 direct/44 total），通用 `_notification` HIGH（21 direct，覆盖现有 Runtime 流）；实现须避免更改通用
  notification 语义，优先使用 Examiner-private 增量边界。
- Required checks：每个待改 symbol 编辑前 GitNexus upstream impact；focused R2.3-006 tests；受影响
  R2.3-003/R2.3-005/default regressions；`python3 -m compileall modeling_team`；稳定点执行完整
  `python3 -m unittest discover -s modeling_team/tests -p 'test_*.py'`，并报告精确结果。
- Outcome：handoff 给 requirement developer；不授权 commit、delivery record 编辑、backend/API 扩展或 semantic
  start。

### 2026-08-12T18:17:18+08:00 — development-ready handoff — requirement developer

- Change：新增 fresh Source/Platform/Acceptance role packet、`ExaminerRunMetrics/v1`、ordered positive-N
  Host runtime、strict exact-schema proxy 和 report-only Acceptance package/skill；Codex 仅在 private child pump/
  launch 边界接入，未改通用 `_notification` 语义。
- Focused verification：`python3 -m unittest modeling_team.tests.test_r23006_lean_runtime -v`
  13/13 PASS；受影响 `test_examiner_stdout_pump`、`test_r23005_b_runtime`、`test_r23005_contracts`、
  `test_r23005_c_settlement` 合计 74/74 PASS；`py_compile`、`compileall -q modeling_team`、
  `git diff --check` PASS。
- Full discover：仓库根目录执行时 518 tests，514 PASS、1 SKIP、4 import errors；四项均为既有
  backend `app` 模块未加入 `PYTHONPATH` 的 collection 环境问题，无 R2.3-006 assertion failure。独立测试
  必须以正确 backend path 重跑完整套件，不把本结果记为最终 PASS。
- Remaining gate：未运行真实 provider-backed Examiner 或 retained-workspace N=2；交给独立 tester，
  不创建 semantic start、不更改 ontology/ledger。

### 2026-08-12T18:25:31+08:00 — independent test Round 1 — requirement tester

- Result：FAIL；详细证据已追加到同一 shared test plan 第 5 节。
- Passing evidence：focused 13/13；使用 `PYTHONPATH=backend:. backend/.venv/bin/python` 执行完整
  modeling_team 套件 517 PASS、1 SKIP；compileall/diff check PASS。
- P0-1：Source/Acceptance 关闭 default tools 后只有 report MCP，首轮只给 packet digest 和
  “读 input.json”指令，没有可证明的 packet/source 读取能力；真实 E2E BLOCKED。
- P0-2：private child pump 仍调用通用 `_notification`，`item/agentMessage` 被写入共享
  `adapter._messages`，违反 typed-output-only/禁止 main route。
- P0-3：report 先于 `turn/completed` 到达时，Host 只在首次报告分支检查 terminal flag，
  后续即使 completed 也会超时为 `BLOCKED/runtime-infrastructure`；`terminal_wall_ms` 也在
  report callback 时过早冻结。
- Decision：三项作为同一 defect cycle 返回 requirement developer；修复后由同一 tester Round 2
  复测。本轮未创建 key、未读 retained workspace、未启动 semantic start、未改 ontology/ledger。

### 2026-08-12 — first authorized production-operation preflight — main agent

- Baseline：clean commit `d5410ad Add lean isolated Examiner runtime`；service active，backend/frontend 200。
- Result：operation 在首次 retained snapshot fail-closed：`workspace-context` 不包含被冻结校验使用的
  `workspace_version`。失败发生在 Project read key 创建和任何 Examiner thread 之前；没有 semantic write、
  modeling start 或 evidence publication。
- Cleanup evidence：active `r23006-retained-admin`=0，retained Project active key=0，provider 已停止，首次输出目录
  不含文件；backend/frontend 继续 200。由于 exactly-one Project key 尚未创建，本次 preflight 不消耗真实
  read-key/N=2 授权。
- Disposition：确认是 operation snapshot 对真实 API 字段归属的实现缺陷；只修该边界，不改变 backend API、
  ticket、scope、provider、proxy 或 Examiner semantics。

### 2026-08-12 — snapshot repair and independent Round 7 — main agent / requirement tester

- Repair：`workspace-context` 继续校验 retained state/default graph；新增只读 `modeling-context`，从其 nested
  workspace 校验 state/version；`build-context.generated_at` 的 volatile-field 排除同步到新路径索引。
- Main verification：operation focused 7/7，Ruff、py_compile、diff check PASS；直接只读 service 检查确认
  workspace-context 无 version，modeling-context version 与 retained `18e491…157c0` 相等；active bootstrap/
  Project keys 均为 0，service active/200/200。
- Independent Round 7：PASS；operation+lean 30/30、backend context API 21 PASS、platform scope 9/9、
  Ruff/compile/diff PASS；wrong modeling version 与 live-count drift 均 fail-closed，`generated_at` 变化不改变
  digest。详细证据见 shared plan §11。
- Outcome：修复稳定，可先形成干净提交，再从全新输出目录执行唯一授权真实 retained N=2 operation。
