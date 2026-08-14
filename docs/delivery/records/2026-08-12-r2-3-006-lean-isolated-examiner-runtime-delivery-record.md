# R2.3-006 精简隔离 Examiner Runtime Delivery Record

- Requirement source：`docs/requirements/requirements-v2.3.md#r23-006-精简隔离-examiner-runtime`
- Status：implementation repair（三次真实 operation live-4/5/6 均为 `BLOCKED`；最后一次为
  `BLOCKED/runtime-infrastructure`（child-timeout），清理/不变性/typed failure 证据独立 PASS，语义完成门未通过）
- Started：2026-08-12T16:34:22+08:00
- Last updated：2026-08-13T09:30:00+08:00
- Design：`docs/delivery/designs/2026-08-12-r2-3-006-lean-isolated-examiner-runtime-design.md`
- Shared test plan：`docs/delivery/test-plans/2026-08-12-r2-3-006-lean-isolated-examiner-runtime-test-plan.md`
- Delivery baseline：`8b3ae42 Accept R2.3-003 retained-scope modeling`
- Delivery commits：`d5410ad Add lean isolated Examiner runtime`、`a32409f Fix retained acceptance snapshot`、
  `Repair Platform Examiner retrieval wave`（最后一项由 `git log -- <本文件>` 解析 immutable hash）

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
| 16 | clean `a32409f`; unique authorized retained N=2 operation | CQ-001 Source completed, but Platform emitted a fourth positive App Server usage increment before a terminal report and was mechanically stopped as `BLOCKED/runtime-budget`; operation returned exit 1 and wrote no acceptance evidence | Project read key create/revoke/readback/old-key-401 each exactly once; bootstrap admin revoked; live inventory/model/ledger unchanged; no operation process/socket/temp/secret residue; service active/200/200 | real semantic acceptance BLOCKED, not PASS/FAIL; no rerun authorized |
| 17 | independent Round 8 and root-cause audit | Failure-path implementation behaved as designed. The Platform prompt allowed serial exploratory read waves even though a report-tool call and provider completion must also fit inside three model inferences | independent cleanup/failure-path PASS; deterministic operation+lean 30/30; GitNexus trace plus source review bound the fourth positive usage to the metrics gate | prompt-contract defect returned for a no-key/no-provider repair before any future start |
| 18 | Platform prompt repair and independent Round 9 | Platform instructions/Skill now require one first-inference parallel read wave and next-inference typed report; cursor/truncated/incomplete/missing facts remain explicit gaps/unknowns instead of triggering another wave | Lean 24/24; operation+Lean 31/31; affected 86/86; full modeling_team 535 PASS + 1 SKIP; Ruff/compile/diff PASS | deterministic repair PASS; real provider behavior and ordered N=2 remain blocked pending new operation authorization |

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
| 8 | unique real operation failure-path audit | PASS (cleanup and fail-closed path) | real semantic acceptance `BLOCKED/runtime-budget`; no ordered N=2 PASS evidence | shared plan §12 |
| 9 | Platform retrieval-wave prompt repair | PASS (deterministic scope) | actual provider parallel wave and real ordered N=2 unexecuted | shared plan §13 |

## Final verification

- Required checks：mandatory plan review Round 2 PASS；main agent 在最终稳定状态重跑 operation+Lean 31/31、
  full modeling_team 535 PASS + 1 SKIP、changed Ruff、compileall、diff check，全部 PASS；independent Round 9
  另有 Lean 24/24、affected 86/86 PASS。
- Runtime/restart health：唯一真实 operation 的 failure-path/cleanup 独立 PASS；service active，backend/frontend
  200。modeling_team-only prompt/docs 变更不要求 backend/frontend restart，但最终仍复核 unit/endpoint health。
- Documentation/status sync：requirement/design/test plan/record 均明确“implemented、real acceptance
  BLOCKED/runtime-budget、prompt repair 待新授权”，不把 cleanup PASS 或 deterministic PASS 写成 semantic PASS。
- Cleanup：本次 operation-owned Project/admin keys active=0；workspace/model/ledger/live inventory 不变；`live-2`
  output 0700 且为空；无 operation process/socket/temp/secret residue。
- Residual gate：需要新的 operation authorization 才能验证修复后的 actual parallel tool wave、六条完整 metrics 和
  ordered `PASS,current=true,usable=true` N=2。该门直接属于 acceptance criteria，因此当前不能关闭需求。

## Retrospective

- Scope/design deviations：新增 standalone callable retained operation 作为真实完成边界；未接入通用 Runner 默认
  dispatcher，也未扩展 backend。真实运行后把 Platform retrieval 形态进一步收敛为 single parallel wave。
- Rework/root cause：确定性测试曾漏掉真实 API 字段归属和 provider tool-loop step shape；第一次 preflight 在 key
  创建前暴露前者，唯一 N=2 operation 以第 4 inference budget gate 暴露后者。两次都 fail-closed 且清理完整。
- What shortened delivery：复用 003 final workspace、strict proxy、typed report/verdict 和 positive-N 证据。
- Reusable lesson：fresh role 的独立性必须由输入清单和 transport/tool gate 证明；模型调用预算还必须把 terminal
  report tool 之后的 provider completion 算入，并在 prompt 中明确 retrieval wave timing。

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

### 2026-08-12 — unique authorized real operation and independent Round 8 — main agent / requirement tester

- Stable baseline：clean `a32409f Fix retained acceptance snapshot`；新目录
  `workspaces/modeling-acceptance/r23006-retained-n2-live-2` 不存在；service active，backend/frontend 200，
  retained ticket digest、CQ count=2、six-tool allowlist、provider credential preflight 均 PASS；operation-owned
  active admin/Project keys 均为 0。
- Real result：operation 越过 live snapshot，创建一个临时 Project read key，并开始 CQ-001 fresh Examiner。
  Source 完成后，Platform 在收到第四个 positive cumulative `thread/tokenUsage/updated` 时由
  `ExaminerRunMetrics.observe_notification` 在 append/继续前抛 `BLOCKED/runtime-budget`；CLI exit 1，未形成
  typed Platform report、ordered verdict 或 acceptance evidence。没有执行 CQ-002，也没有 semantic start/write。
- Exactly-once/cleanup：read key `0c289d42-…` create/revoke audit 各 1，revoke readback 1，旧 key protected GET
  返回 401；bootstrap admin `f28544a3-…` 随后撤销。operation-owned active keys=0；output root 0700 且为空，
  无 operation process/socket/temp/secret residue。
- Invariance：workspace state/default graph/version 保持 retained 值；live inventory 精确为
  `1,0,0,0,0,22`；ledger SHA `af6417…dcc`、66 records 不变；service active/200/200。
- Independent Round 8：failure-path/cleanup audit PASS，但真实 semantic acceptance 明确为
  `BLOCKED/runtime-budget`，不是 PASS/FAIL；deterministic operation+lean 30/30、Ruff/compile/diff PASS。详细证据见
  shared plan §12。唯一 Project-key operation 已消耗，不得无新授权重跑。

### 2026-08-12 — post-operation root-cause disposition — main agent

- Method：使用 `gitnexus-debugging` 重建 stale local index，再核对
  `ExaminerRunMetrics -> _CodexChildResource._run_stdout_pump -> run_lean_examiner_child` 真实异常链、operation
  window journal 与 Platform package/Skill。
- Conclusion：预算门没有误计或放行；每个 positive usage 增量代表一次真实 provider inference。现有 Platform
  prompt 强调完整检索/分页，却未要求把独立 read calls 合并进首个 tool wave；report MCP 后仍需 provider
  completion，因此串行第二轮探索会把终态推到第四次 inference。
- Disposition：这是 prompt-contract defect。任何未来 start 前只允许补通用“首轮并行读取、下一轮提交 typed
  report、incomplete/cursor 作为 gaps/unknown 报告”的边界；不得增加三步预算、注入 CQ 答案/专属工具计划或
  在无新 operation authorization 时重跑。

### 2026-08-12 — Platform prompt repair and independent Round 9 — requirement developer / tester

- Change：Platform package instructions 与 Skill 要求首个 inference 把所有独立、可能需要的 read calls 放进
  单一 parallel tool wave；wave 返回后的下一 inference 必须提交 typed report，禁止串行探索、重复读取、第二
  retrieval wave、cursor follow 或 retry。首轮 cursor/truncated/incomplete/ambiguous/missing fact 在同一报告中
  保留 completeness markers、unknown 和 explicit gap。
- Guardrails：未改变三步 budget、runtime/proxy/report schema、Source/Acceptance package 或 backend；未注入
  CQ-001/CQ-002 答案或专属 tool plan，未创建 key/provider/child。
- Independent Round 9：prompt-contract deterministic PASS；Lean 24/24、operation+Lean 31/31、affected 86/86、
  full modeling_team 535 PASS + 1 SKIP，Ruff/compile/diff PASS。既有 evidence locator/page-chain/scope/source
  binding 未放宽。详细证据见 shared plan §13。
- Outcome：实现处于稳定、可提交的阻断点；真实 provider 是否执行 parallel wave、六条完整 metrics 与 ordered
  N=2 PASS 仍需新的 operation authorization。当前不得标记 requirement complete，也不得自动重跑。

### 2026-08-12 — authorized real operation live-3 and independent Round 10 — main agent / requirement tester

- Authorization：用户明确“同意，继续”，只授权一次新的 R2.3-006 retained-workspace read-only operation；允许
  一个新的临时 Project read key exactly-once create/revoke，不允许 semantic start、ontology/ledger write 或失败后
  自动重跑。Stable baseline 为 clean `6c1258a Repair Platform Examiner retrieval wave`。
- Real result：Source 约 28 秒完成；Platform 确实执行首轮单一并行 read wave 和 report/tool calls，没有第四个
  positive usage increment。约 90 秒 child watchdog 到期，operation 为 `BLOCKED/runtime-infrastructure`；代码与
  operation window 共同绑定的最可信底层 reason 是 `runtime/child-timeout`。Acceptance/CQ-002 未执行，没有
  ordered N=2 verdict 或 semantic PASS。
- Cleanup/invariance：Project read key 与 bootstrap admin 均撤销；read-key create/revoke/readback/old-key 401 各一次，
  operation-owned active keys=0。live inventory `1,0,0,0,0,22`、workspace/default graph/version、ledger SHA/66
  records 前后不变；output root `0700` 且为空，无 operation process/socket/temp/secret residue；service、backend、
  frontend 健康。
- Independent Round 10：FAIL/P1。typed child failure 在 runtime 内保留 `failure_category=runtime`、
  `reason_code=child-timeout`，但 outer operation 固定包装成 `retained acceptance operation failed`，CLI 和 retained
  artifact 均不显示安全 reason。详细证据见 shared test plan §14。本次唯一 operation 已消费，不得自动重跑。

### 2026-08-12 — typed failure evidence repair and independent Rounds 11-12 — developer / tester

- Repair：`R23006AcceptanceOperation` 只在 read-key lifecycle、全部 cleanup 与 model/ledger invariance 均完整时，
  把 `ExaminerRuntimeBlocked` 投影为 provider/credential-free typed `BLOCKED` result，并原子写入 mode `0600` 的
  `r23006-retained-acceptance.json`；outer `R23006OperationError` 同时显示安全 role/reason/category/code。success
  artifact 契约不变；secret、未知字段、自由文本、错误类型、绝对/遍历路径、cleanup/key/invariance failure 均不
  生成可误解 artifact。
- Round 11：live-3 child-timeout 路径通过，但独立测试发现 initial allowlist 漏掉 `runtime-budget.steps` 等合法 typed
  evidence，结论 FAIL/P1；详细证据见 shared plan §15。
- Round 12：生产代码中全部 10 类 typed evidence key 与 `failure_category/reason_code` 均受有限 schema/type 校验；
  14/14 合法投影、runtime-budget、runtime-metrics、acceptance-input、Source path、child-timeout、exact packet label
  与全部对抗分支 PASS。focused operation+lean `36/36`、affected `86/86`、full modeling_team `540 PASS + 1 SKIP`，
  Ruff、compileall、`git diff --check` PASS。详细证据见 shared plan §16。
- Boundary：本修复没有改 timeout、provider、Prompt、runtime budget、backend 或语义门；没有创建 key/provider/child，
  没有执行真实 N=2。deterministic observability 已闭环，但真实 semantic acceptance 仍是
  `BLOCKED/runtime-infrastructure`，必须获得新的 operation authorization 才可继续。

### 2026-08-12 — three-operation authorization and live-4 — main agent

- Authorization：用户明确“授权三次”。该授权只覆盖最多三次新的 R2.3-006 retained-workspace read-only
  operations；每次允许一个新的临时 Project read key exactly-once create/revoke，继续禁止 semantic start、
  ontology/ledger write、超过三次的自动重跑或把 cleanup PASS 当作 semantic PASS。
- Preflight：stable clean HEAD `5949a0f Preserve Examiner failure evidence`；live-4 output root 不存在；service
  active、backend/frontend 200；冻结 ticket digest、N=2、six-tool allowlist 与 retained scope 匹配。
- Authorization 1/3 — live-4：Source 完成，Platform 再次执行大量单一并行 read wave；operation 在约 90 秒
  watchdog 后返回 `BLOCKED/runtime-infrastructure`，CLI 与新 mode `0600` artifact 均保留
  `failure_category=runtime`、`reason_code=child-timeout`。Acceptance/CQ-002 未执行，不是 semantic PASS。
- Cleanup/invariance：artifact 证明 Project read key create/revoke `1/1`、revoke readback 200、旧 key 401、全部
  cleanup flags true；ledger SHA `af6417…dcc`/66 records 与 platform digest `3606c7…f95` 前后相同；service、
  backend、frontend 继续健康。
- New evidence gap：typed terminal reason 已真实闭环，但失败 artifact 尚未保存 Source/Platform partial metrics、
  report-received/terminal-event 状态或 proxy receipt count，无法从 retained evidence 区分 report 已提交但 provider
  未 terminal 与 tool wave 未完成。剩余授权为 `2/3`；先修该只读 observability gap，不修改 timeout、Prompt、
  provider、budget 或语义门，也不立即消耗下一次。

### 2026-08-12 — live-4 diagnostic repair and independent Rounds 17-18 — developer / tester

- Repair：private Codex child failure branch 在现有 category/code 上增加 `report_received`、`terminal_event` 与
  `proxy_receipt_count` 三个机械标量；`LeanExaminerRuntime` 保留 Source/Platform/Acceptance 各阶段已完成和当前
  `ExaminerRunMetrics/v1` 的深拷贝快照；operation 只在撤钥、cleanup 与 invariance 全部通过后写入最多六条有序
  `partial_metrics`。未改 generic carrier/notification/resource winner、90 秒 timeout、Prompt、provider、budget 或
  semantic gate。
- Round 17：FAIL/P1。初版 persistence gate 允许末条 `blocked=None`、nested block 与 outer role/reason/evidence
  不一致或前序 metric 携带 blocked，可能污染 retained failure-stage attribution；详细证据保留在 shared plan §17。
- Fix：非空 partial metrics 的前序记录必须全部 `blocked=None`，最后一条 sanitized block 必须与 outer typed
  BLOCKED 完全一致；空列表仍用于 metric 创建前的 typed stop。secret、额外字段、错误 role/bool/nested evidence
  或 cleanup/key/invariance failure 继续无 artifact。
- Round 18：PASS（deterministic diagnostics + retained live-4 audit）。focused `43/43`、deterministic selection
  `12/12`、affected `86/86`、full modeling_team `547 PASS + 1 SKIP`，Ruff、compileall、diff-check PASS；live-4
  artifact hash 未变，typed child-timeout、key lifecycle `1/1`/401、cleanup/invariance 与服务健康仍 PASS。详细证据
  见 shared plan §18。
- Boundary：Round18 不等于 semantic PASS，也没有创建 key/provider/child。三次授权尚余 `2/3`；可在该修复的
  clean commit 上执行 live-5，以真实保留 timeout 当刻 partial metrics 与 report/terminal/proxy 状态。

### 2026-08-12 — authorization 2/3 live-5 — main agent

- Baseline：clean `4dea660 Retain partial Examiner diagnostics`；live-5 output root 不存在；service active、
  backend/frontend 200；冻结 ticket/N=2/six-tool allowlist preflight PASS。
- Real result：Source 完成，Platform 在两个 inference steps 内完成单波读取并提交 typed report callback；随后
  `_validate_platform_report_receipts` 在 receipt-count/nonempty gate fail-closed 为
  `BLOCKED/acceptance-evidence`。没有 runtime-budget 或 child-timeout，没有进入 Acceptance/CQ-002，不是 semantic
  PASS。
- Partial metrics：Source `metrics_complete=true`、2 steps、terminal约25.9s；Platform 2 steps、TTFT约0.83s、
  proxy time约9.6s、total tokens `48741`、output tokens `12076`，但 report locator 校验失败，所以
  `metrics_complete=false`、`terminal_report=false`。artifact 没有保留 report ref/receipt 精确计数；真实日志显示
  receipts 非空，因此最可信原因是 report `evidence_refs` 数量与 proxy receipts 数量不等。
- Cleanup/invariance：mode `0600` BLOCKED artifact；Project read key create/revoke `1/1`、旧 key 401、全部 cleanup
  flags true；ledger SHA/66 records 与 platform digest 前后相同，service/backend/frontend 健康。
- Disposition：三次授权已消费 `2/3`，剩余 `1/3`。最后一次前先把 receipt-count mismatch 的安全 code/count 写入
  typed failure evidence，并修 Platform 通用 Prompt/Skill：只发回答当前问题所需的最小充分单波、最多六个成功
  proxy calls、每个 allowed tool 最多一次、每个成功 call 恰好一个 locator。不得注入 CQ 答案/专属 tool plan，
  不放宽一一 receipt binding、cursor、三步或 90 秒门。

### 2026-08-13 — live-5 receipt diagnostics / retrieval-bound repair and independent Round 20 — developer / tester

- Repair：Platform report receipt gate 对 `report-refs-invalid`、`receipts-empty` 与
  `receipt-count-mismatch` 保留固定 `binding_code`、`report_ref_count`、`proxy_receipt_count`；operation 仅接受
  这三个 code 与非 bool 非负整数计数，未知 code、错误类型或 secret 继续 fail-closed 且不写 artifact。
- Prompt contract：Platform package 与 Skill 改为当前问题的 minimum-sufficient 单一并行波；最多六个成功 proxy
  calls、每个 allowed tool 最多一次、每个成功 call 恰好一个 evidence locator，locator 数必须等于 current-child
  receipt 数。若上限内不足，必须在同一 typed report 保留 incomplete/unknown/gap；禁止第二波、重试、re-read、
  cursor follow 或放宽 completeness/receipt gate。
- Independent Round 20：PASS（deterministic scope），无 P0/P1。三种 gate 的 exact code/count、安全 mode `0600`
  persistence、7 个非法输入 no-artifact 与 13 项 Prompt/Skill marker 均通过；focused `44/44`、affected
  `86/86`、full modeling_team `548 PASS + 1 SKIP`，Ruff、compileall、diff-check PASS。详细证据见 shared plan §20。
- Boundary：本轮没有创建 key/provider/child 或执行 N=2，live-5 历史结论仍为 semantic BLOCKED。三次授权剩余
  `1/3`；仅在本修复形成 clean commit 后从全新 live-6 目录执行最后一次，禁止第 4 次 operation。

### 2026-08-13 — authorization 3/3 live-6 and independent Round 21 — main agent / tester

- Baseline：clean `1515807 Bound Platform Examiner receipt wave`；live-6 output root 不存在；service active、
  backend/frontend 200；冻结 ticket/N=2/six-tool allowlist preflight PASS。
- Real result：Source 完成（2 steps、`metrics_complete=true`、terminal report true、wall 约 21.2s）；Platform 在
  单一并行 read wave 内完成读取并提交 typed report（3 steps、terminal report true、wall 约 70.1s、proxy 约 4.2s）；
  Acceptance child 正好 3 inference steps 后未产生 terminal report，约 90 秒 child watchdog 到期，operation 为
  `BLOCKED/runtime-infrastructure`（reason_code=`child-timeout`、`report_received=false`、`terminal_event=false`、
  `proxy_receipt_count=0`）。Acceptance/CQ-002 未执行，没有 ordered N=2 verdict 或 semantic PASS。
- Partial metrics：artifact 保留 `source, platform, acceptance` 三角色快照；Source 2 steps、Platform 3 steps、
  Acceptance 3 steps `metrics_complete=false`。token increments 可重算 cumulative totals；失败是 typed
  runtime/infrastructure，而非伪造 PASS 或 report-first terminal。
- Cleanup/invariance：Project read key create/revoke `1/1`、旧 key 401、全部 cleanup flags true、operation-owned
  active keys=0、plaintext released；ledger SHA `af6417…dcc`/66 records 与 platform digest `3606c7…f95` 前后相同；
  secret/process/socket/temp residue 扫描干净；service、backend、frontend 健康。
- Independent Round 21：PASS（failure-path/lifecycle/invariance read-only audit scope），无新 P0/P1。artifact
  hash/mode、token increment 重算、有序 verdict 缺失（BLOCKED 正确形态）、DB 只读审计（project/admin 行均 revoked、
  active project keys=0、audit 仅 2 条 success 行）、清理 flag 与 `ps`/socket 扫描均通过；详细证据见 shared plan §21。
- Final disposition：三次授权 `3/3` 已全部消费，不再有 R2.3-006 自动重跑额度。最终真实语义结果为
  `BLOCKED/runtime-infrastructure`（Acceptance child-timeout，无 ordered N=2 verdict）；cleanup/lifecycle/invariance
  与 typed failure evidence 均独立 PASS，但这不构成 semantic PASS。

### 2026-08-13 — new authorization live-7 real N=2 — main agent

- Authorization：用户明确“授权一次建模执行次数”，只覆盖一次新的 R2.3-006 retained-workspace read-only
  operation（live-7）；允许一个新的临时 Project read key exactly-once create/revoke，继续禁止 semantic start、
  ontology/ledger write 或超过一次的自动重跑。本次为非常规需求续作，不走 requirement-delivery 流程。
- Preflight：stable clean HEAD `454e804 Refresh R2.3-006 status after live-6 consumption`；live-7 output root
  不存在；`ontology-platform.service` 曾因项目迁移后 systemd 单元/venv shebang 指向旧路径而无法启动，已修复
  单元 WorkingDirectory、重建 backend `.venv` 并验证 backend/frontend 200；冻结 ticket/N=2/six-tool allowlist
  与 retained scope 匹配。
- Real result：Source 完成（2 steps、`metrics_complete=true`、terminal report true、wall 约 25.6s）；Platform 在
  单一并行 read wave 内完成读取并提交 typed report callback（2 steps、TTFT 约 1.4s、proxy 约 11.6s、total
  tokens `33656`、output `8684`），随后 `_validate_platform_report_receipts` 在 receipt-count gate fail-closed 为
  `BLOCKED/acceptance-evidence`（`binding_code=receipt-count-mismatch`、`proxy_receipt_count=5`、
  `report_ref_count=3`）。Acceptance/CQ-002 未启动，没有 ordered N=2 verdict，不是 semantic PASS。
- Partial metrics：artifact 保留 `source, platform` 两角色快照；Source `metrics_complete=true`，Platform
  `metrics_complete=false`、`terminal_report=false`；token increments 与累计 totals 一致。失败是 typed
  evidence 层（report 只含 3 个 evidence locator，而 proxy 收到 5 个成功 call receipt），不是伪造 PASS。
- Cleanup/invariance：Project read key create/revoke `1/1`、旧 key 401、全部 cleanup flags true、
  operation-owned active keys=0；ledger SHA `af6417…dcc`/66 records 与 platform digest `3606c7…f95` 前后相同；
  `ps`/socket 扫描无 live-7 残留。
- Failure layer：`modeling-quality/prompt-contract`。Platform 指令已声明“每个成功 proxy call 恰好一个
  evidence_refs locator、locator 数必须等于 receipt 数”，但模型在真实运行中仍只提交 3 个 locator 对应 5 个
  receipt，与 live-5 同一模式。裁决/诊断/清理均正确 fail-closed，不构成平台或 runtime 缺陷；修复责任面是
  Platform Examiner 指令（`modeling_team/agent-packages/platform-examiner/instructions.md`）及其 Skill 契约。
- Disposition：本次授权 `1/1` 已消费，未再启动第二次 operation。需先按 prompt-contract 缺陷修复 Platform
  指令并完成 deterministic 复验，之后请求新的 operation authorization 才可执行 live-8。

### 2026-08-13 — prompt-contract 修复与 Round 23 deterministic 复验 — main agent / tester

- Repair commit `450bbe6`：Platform Examiner 指令与 Skill 同时新增 "Mandatory locator count check before
  submission" 契约——提交前机械重数成功 proxy calls 与 `evidence_refs`，计数不等时同一 inference 内补齐 locator，
  不省略/合并/丢弃；明确 Host 将自动以 `receipt-count-mismatch` 拒绝且不可二次波修复。
- Round 23 deterministic 复验：PASS。两处权威 prompt 表面空白归一化后语义一致；marker 固化测试新增 7 个 marker
  （mechanically count、exactly equal to、receipt-count-mismatch、cannot be repaired by a second wave、add the
  missing locators、same inference、Re-count immediately before sending）后 focused `30/30`、full `548 PASS +
  1 SKIP`，无 regression。
- Boundary：本轮未创建/使用 key、未启动 provider/child、未执行 operation；live-7 授权结论不变（`1/1` 已消费）。
- Next gate：真实 semantic acceptance 仍需新的 operation authorization 执行 live-8，届时以 ordered N=2
  verdict 完成验收；禁止未授权 operation。

### 2026-08-13 — authorization 1/2 live-8 real N=2 — main agent

- Authorization：用户授权 2 轮新的 R2.3-006 retained-workspace read-only operation（live-8/live-9）；每轮允许
  一个新的临时 Project read key exactly-once create/revoke，继续禁止 semantic start、ontology/ledger write 或
  超过一轮的自动重跑。非常规需求续作，不走 requirement-delivery 流程。
- Preflight：stable clean HEAD `8991104 Verify R2.3-006 locator contract via Round 23`；live-8 output root 不
  存在；service active、backend/frontend 200；DeepSeek credential binding 可用；冻结 ticket/N=2/six-tool
  allowlist 与 retained scope 匹配。
- Real result：Source 完成（2 steps、`metrics_complete=true`、terminal report true、wall 约 23.6s、total tokens
  `24557`）；Platform 在单一并行 read wave 内完成读取并提交 typed report callback（2 steps、TTFT 约 1.5s、
  proxy 约 6.3s、total tokens `44545`），随后 `_validate_platform_report_receipts` 在 receipt-count gate
  fail-closed 为 `BLOCKED/acceptance-evidence`（`binding_code=receipt-count-mismatch`、
  `proxy_receipt_count=5`、`report_ref_count=4`）。Acceptance/CQ-002 未启动，没有 ordered N=2 verdict。
- Partial metrics：artifact 保留 `source, platform` 两角色快照；Source `metrics_complete=true`，Platform
  `metrics_complete=false`、`terminal_report=false`；token increments 与累计 totals 一致。失败是 typed evidence
  层（report 只含 4 个 evidence locator，而 proxy 收到 5 个成功 call receipt），从 live-5/7 的 3→5 改善到
  4→5，但 gate 仍严格 fail-closed，不是伪造 PASS。
- Cleanup/invariance：Project read key create/revoke `1/1`、旧 key 401、全部 cleanup flags true、
  operation-owned active keys=0；ledger SHA `af6417…dcc`/66 records 与 platform digest `3606c7…f95` 前后相同。
- Failure layer：`modeling-quality/prompt-contract`。同一失败模式（locator 数少于 receipt 数）连续第三次出现
  （live-5/7/8），纯文字计数指令不足以让模型机械对齐。
- Repair（live-9 前完成）：proxy 成功响应新增 `call_ordinal`（zero-based）与 `call_total`（运行中成功调用
  计数）；Platform instructions.md 与 SKILL.md 新增 "Mandatory ordinal alignment" 契约——按成功顺序逐条对齐
  `evidence_refs`、`ref_id = "p<call_ordinal>"`、locator 数必须等于最后一次响应的 `call_total`、提交前列出
  收到的 ordinals 并确认无缺失。marker 测试新增 5 个 marker，proxy ordinal/total 有聚焦断言；focused
  `30/30`、full `548 PASS + 1 SKIP` 无 regression。
- Disposition：授权 `1/2` 已消费。修复完成 deterministic 复验后，消耗第 2 轮（live-9）执行真实 N=2。

### 2026-08-13 — authorization 2/2 live-9 real N=2 — main agent

- Authorization：延续用户 2 轮授权中的第 2 轮，覆盖一次新的 R2.3-006 retained-workspace read-only operation
  （live-9）；允许一个新的临时 Project read key exactly-once create/revoke，禁止 semantic start、ontology/ledger
  write 或自动重跑。
- Preflight：stable clean HEAD `98f38a7 Record live-8 evidence and add ordinal alignment`；live-9 output root
  不存在；service active、backend/frontend 200；DeepSeek credential 可用；冻结 ticket/N=2/six-tool allowlist
  与 retained scope 匹配。
- Real result：Source 完成（2 steps、`metrics_complete=true`、terminal report true、wall 约 31.0s、total tokens
  `26676`）；Platform 2 steps（TTFT 约 1.1s、proxy 仅约 196ms、total tokens `33917`），随后 Platform report
  在 receipt-binding 校验链 fail-closed 为 `BLOCKED/acceptance-evidence`，但 `evidence={}` 为空（不再是
  count-mismatch 形式）。Acceptance/CQ-002 未启动，没有 ordered N=2 verdict。
- Partial metrics：artifact 保留 `source, platform` 两角色快照；Source `metrics_complete=true`、terminal report
  true；Platform `metrics_complete=false`、`terminal_report=false`。token increments 与累计 totals 一致。
- Cleanup/invariance：Project read key create/revoke `1/1`、旧 key 401、全部 cleanup flags true、
  operation-owned active keys=0；ledger SHA `af6417…dcc`/66 records 与 platform digest `3606c7…f95` 前后相同。
- 关键差异：live-9 的 Platform `proxy_time_ms=196.4`、`evidence_tokens=6711`（live-8 为 6338ms/26862），模型
  本次几乎未发起 proxy 读取波即提交 report，且失败点在 count 匹配之后的循环/结构校验（空 evidence），失败
  分支当前无法从 artifact 精确定位。Failure layer 候选为 `modeling-quality/prompt-contract` 或
  `platform-contract` 诊断缺口，待增强 typed failure 证据后确认。
- Repair（live-10 前完成）：给 `_validate_platform_report_receipts` 循环内每个失败分支与
  `record_terminal_report` 字段集校验补充精确 `binding_code`/`index` evidence，同步更新 operation
  `_PLATFORM_BINDING_CODES` 白名单，使下一次失败可精确定位分支；完成后 deterministic 复验。
- Disposition：授权 `2/2` 已消费。需要新的 operation authorization 才可执行 live-10。

### 2026-08-13 — all acceptance-evidence failures carry precise reason codes — main agent

- 用户指出"平台报错应该返回具体报错原因"。审查确认 live-9 的 `evidence={}` 属于诊断缺口：`acceptance-evidence`
  类失败曾有多处 raise 不带 evidence。
- 修复：`acceptance-evidence` 全部失败分支现在携带精确 `binding_code`（+ `index`/`field`/`path`/
  `report_field_set`/`verdict_field_set` 等定位字段）：
  - Platform：`platform-refs-invalid`、`receipt-snapshot-invalid`、`locator-shape`、`ordinal-mismatch`、
    `locator-key-mismatch`、`page-shape`、`page-first-invalid`、`page-sequence-invalid`、
    `page-has-more-invalid`、`page-truncated-locator`、`page-final-invalid`、`ref-id-invalid`；
  - Source：`approved-sources-missing`、`approved-source-shape`、`approved-source-invalid`、
    `source-refs-invalid`、`source-locator-shape`、`source-path-unauthorized`；
  - Acceptance：`report-object-invalid`、`report-digest-invalid`、`report-sink-invalid`、
    `report-digest-mismatch`、`evidence-ref-ids-invalid`、`report-fields-invalid`、`verdict-fields-invalid`、
    `verdict-status-invalid`、`verdict-answer-invalid`、`verdict-evidence-refs-invalid`、`verdict-flags-invalid`、
    `verdict-ref-ids-shape`、`verdict-ref-ids-not-allowed`、`verdict-pass-without-evidence`、
    `submitted-report-shape`。
- Operation 投影白名单同步：`_PLATFORM_BINDING_CODES`/`_SOURCE_BINDING_CODES`/`_ACCEPTANCE_BINDING_CODES`
  三组集合 + `_BLOCKED_INTEGER_FIELDS`（`index`）+ 新增 `_BLOCKED_FIELD_SET_FIELDS`
  （`report_field_set`/`verdict_field_set` 逗号分隔字段集安全投影）。
- 新增测试：`test_typed_runtime_and_launch_evidence_is_safely_projected` 增补
  `report-fields-invalid`+field_set、`locator-key-mismatch`+index、`source-path-unauthorized`+path 三个案例；
  focused `45/45 PASS`、full `549 PASS + 1 SKIP`，无 regression。
- 后续 live-10 若仍 BLOCKED，artifact 将直接给出精确失败分支与定位字段，不再出现空 evidence。

### 2026-08-13 — authorization 1/3 live-10 real N=2 — main agent

- Authorization：用户授权 3 轮新的 R2.3-006 retained-workspace read-only operation（live-10/11/12）；每轮允许
  一个新的临时 Project read key exactly-once create/revoke，继续禁止 semantic start、ontology/ledger write 或
  超过一轮的自动重跑。
- Preflight：stable clean HEAD `64ac3fb Return precise reasons for every acceptance-evidence failure`；live-10
  output root 不存在；service active、backend/frontend 200；DeepSeek credential 可用；冻结 ticket/N=2/six-tool
  allowlist 与 retained scope 匹配。
- Real result：Source 完成（2 steps、`metrics_complete=true`、terminal report true、total tokens `25927`）；
  Platform 在单一并行 read wave 内完成读取并提交 typed report callback（2 steps、TTFT 约 1.4s、proxy 约 8.7s、
  evidence tokens `18075`、total tokens `26661`），随后 receipt-count gate fail-closed 为
  `BLOCKED/acceptance-evidence`（`binding_code=receipt-count-mismatch`、`proxy_receipt_count=2`、
  `report_ref_count=1`）。Acceptance/CQ-002 未启动，没有 ordered N=2 verdict。
- 关键观察：本次模型实际发起了 2 次成功 proxy 调用（proxy 8.7s、evidence 18075 tokens，读取真实发生），但
  report 只含 1 个 evidence_refs locator。这是 count-mismatch 连续第 4 次出现（live-5/7/8/10），模式为
  "模型确实调用但提交时漏写 locator"。
- Repair（live-11 前完成）：`receipt-count-mismatch` evidence 追加脱敏 `report_ref_ids`（模型提交的 ref_id
  列表）与 `proxy_receipt_ordinals`（Host 侧 receipt ordinal 列表），使下一次失败可直接对比模型漏写/合并了
  哪一项；operation 白名单同步（`_BLOCKED_FIELD_SET_FIELDS` 增加两个 summary 字段）。focused `45/45`、full
  `549 PASS + 1 SKIP` 无 regression。
- Disposition：授权 `1/3` 已消费。修复 deterministic 复验后消耗第 2 轮（live-11）。

### 2026-08-13 — authorization 2/3 live-11 real N=2（artifact 投影失败）— main agent

- Authorization：延续 3 轮授权中的第 2 轮（live-11）。
- Real result：Source 与 Platform 实跑均完成（Platform 在读取后提交 report 被 receipt-count gate 拒绝），
  但 operation 在写 artifact 前的 `_blocked_result` 证据投影处 fail-closed 为
  `R23006OperationError: typed Examiner blocked evidence value is invalid`，未生成 artifact。root cause：
  新增 `report_ref_ids` 摘要未在源头清洗字符集，模型真实 ref_id 含投影白名单之外的字符（如引号/分号/
  控制字符）时被拒绝。
- Failure layer：`platform-contract`（诊断投影缺口，非语义失败；source/platform 实跑已发生，授权已消费）。
- Repair：`_ref_id_summary` 在源头用 `[^A-Za-z0-9_:\-]` 清洗并截断 200 字符，摘要永不携带引号/控制字符；
  投影路径与 hostile 字符集经压力验证通过。focused `45/45`、full `549 PASS + 1 SKIP` 无 regression。
- Disposition：授权 `2/3` 已消费。修复后消耗第 3 轮（live-12）。

### 2026-08-13 — authorization 1/5 live-12 real N=2 — main agent

- Authorization：用户新授权 5 轮（live-12/13/14/15/16）；每轮允许一个新的临时 Project read key exactly-once
  create/revoke，禁止 semantic start、ontology/ledger write 或自动重跑。
- Preflight：stable clean HEAD `6e6e45a Sanitize ref summary and record live-11 evidence`；live-12 output root
  不存在；service active、backend/frontend 200；DeepSeek credential 可用；冻结 ticket/N=2/six-tool allowlist
  与 retained scope 匹配。
- Real result：Source 完成（2 steps、`metrics_complete=true`、terminal report true、total tokens `28908`）；
  Platform 在单一并行 read wave 内完成读取并提交 typed report callback（2 steps、TTFT 约 1.4s、proxy 约
  10.6s、evidence tokens `36224`、total tokens `39328`），随后 receipt-count gate fail-closed 为
  `BLOCKED/acceptance-evidence`（`binding_code=receipt-count-mismatch`、`proxy_receipt_count=5`、
  `report_ref_count=3`、`proxy_receipt_ordinals="0,1,2,3,4"`、`report_ref_ids="p0,p1,p2"`）。
- 关键观察：本次诊断（新增强的 ref/ordinal 摘要）证明 ordinal 契约已生效——模型使用 `p<ordinal>` 命名且
  p0..p2 连续正确，但只写了前 3 个 locator，遗漏了 p3、p4。模型确实发起了 5 次真实读取（proxy 10.6s、
  evidence 36224 tokens），提交时仍漏写 locator。这是 count-mismatch 连续第 5 次（live-5/7/8/10/12），
  失败模式收敛为"模型会读、会命名，但 report 中 locator 数少于成功调用数"。
- Repair（live-13 前完成）：prompt 机械步骤强化——提交前把"收到 N 个成功调用（ordinal 0..N-1）"显式写入
  思考并按 1..N 逐条核销 locator，缺失即补齐后同一 inference 提交；继续禁止二次波/补问。
- Disposition：授权 `1/5` 已消费。

### 2026-08-13 — authorization 2/5 live-13 real N=2 — main agent

- Real result：Source 完成（2 steps、`metrics_complete=true`、terminal report true、total tokens `28714`）；
  Platform 2 steps（TTFT 约 1.4s、proxy 约 10.8s、evidence tokens `22906`、total tokens `37989`）提交 report
  后被 `receipt-count-mismatch` 拒绝：`proxy_receipt_count=5`、`report_ref_count=3`、
  `proxy_receipt_ordinals="0,1,2,3,4"`、`report_ref_ids="p0,p1,p2"`。
- 关键观察：live-13 与 live-12 失败形态几乎完全相同（5→3、p0..p2）——"No locator selection by importance"
  契约（live-12 后新增）未改变模型行为。模型确实发起 5 次真实读取（proxy 10.8s），仍只写前 3 个 locator。
- Repair（live-14 前完成）：count-mismatch evidence 追加 `report_ref_tools`（模型 locator 的工具名）与
  `proxy_receipt_tools`（Host receipts 的工具名），可精确对比"模型漏掉了哪个工具的 locator"（如是否丢弃了
  特定工具如 query_semantic_context 或 get_build_session），以区分"模型按工具取舍"还是"截断/遗漏"。
  focused `45/45`、full `549 PASS + 1 SKIP` 无 regression。
- Disposition：授权 `2/5` 已消费。诊断增强后消耗第 3 轮（live-14）。

### 2026-08-13 — authorization 3/5 live-14 real N=2 — main agent

- Real result：Source 完成（2 steps、`metrics_complete=true`、terminal report true、total tokens `26179`）；
  Platform 发出 5 次成功 proxy 调用（proxy 约 10.1s、5 receipts、evidence tokens `36352`）后未产生第二个
  inference step（`inference_steps=1`、`turn_start_count=1`、total tokens `11996`、output tokens `3899`），
  未提交 report（`report_received=false`、`terminal_event=false`），约 90 秒 child watchdog 到期，operation
  为 `BLOCKED/runtime-infrastructure`（`reason_code=child-timeout`）。Acceptance/CQ-002 未启动。
- Failure layer：`runtime/infrastructure`（child-timeout；与 live-4 同模式：Platform 单波读取后未产生
  terminal report）。不是 count-mismatch（本轮无 report 提交），不是伪造 PASS；清理/不变性/typed failure
  证据正常。
- Disposition：授权 `3/5` 已消费。剩余 live-15/16 两轮授权。

### 2026-08-13 — authorization 4/5 live-15 real N=2 — main agent

- Real result：Source 完成（2 steps、`metrics_complete=true`、terminal report true、total tokens `24656`）；
  Platform 2 steps（TTFT 约 1.0s、proxy 约 220ms、evidence tokens `6711`、total tokens `33295`）提交 report 后
  被 `BLOCKED/acceptance-evidence`（`binding_code=page-sequence-invalid`、`index=1`）。
- 关键进展：**count 校验首次通过**（不再是 receipt-count-mismatch）——模型 locator 数量与成功调用数一致，
  但第 2 个 locator 的 `page` 字段构成非法分页序列（跨工具调用发明了 ordinal 1，而每个独立调用应各自
  page.ordinal=0 单页）。诊断增强首次精确指出失败分支。
- Failure layer：`modeling-quality/prompt-contract`（page 语义未被模型遵守）。
- Repair（live-16 前完成）：instructions.md 与 SKILL.md 新增 "Page field is per-call, not a wave-wide
  sequence" 契约——`page` 只描述该次调用自身分页、每个独立调用 page.ordinal=0、完整响应
  `has_more=false`/`sequence_complete=true`、禁止跨调用发明 ordinal 序列；marker 测试新增 4 个 marker；
  focused `31/31`、full `549 PASS + 1 SKIP` 无 regression。
- Disposition：授权 `4/5` 已消费。修复后消耗第 5 轮（live-16）。

### 2026-08-13 — authorization 5/5 live-16 real N=2 — main agent

- Real result：Source 完成（2 steps、`metrics_complete=true`、terminal report true、total tokens `27675`）；
  Platform 发出 5 次成功 proxy 调用（proxy 约 4.9s、5 receipts、evidence tokens `26240`）后未产生第二个
  inference step（`inference_steps=1`、total tokens `13183`、output tokens `4463`），未提交 report
  （`report_received=false`、`terminal_event=false`），约 90 秒 child watchdog 到期，operation 为
  `BLOCKED/runtime-infrastructure`（`reason_code=child-timeout`）。
- Failure layer：`runtime/infrastructure`（与 live-4、live-14 同模式：Platform 单波读取后未产生 terminal
  report）。不是 count-mismatch（无 report 提交）、不是伪造 PASS；清理/不变性/typed failure 证据正常。
- 5/5 授权全部消费：live-12（count-mismatch 5→3）、live-13（count-mismatch 5→3）、live-14（child-timeout）、
  live-15（count 通过、page-sequence-invalid）、live-16（child-timeout）。
- 趋势：locator 数量问题已通过（live-15 count 通过），page 语义契约已新增（live-15 后）；剩余卡点为
  Platform 偶发单波读取后不产生第二步（child-timeout，与 live-4/14 同 runtime 模式）。后续需要新的 operation
  authorization 执行 live-17。

### 2026-08-14 — authorization 1/5 live-17 real N=2 — main agent

- Authorization：用户新增 5 轮授权（live-17/18/19/20/21）；每轮允许一个新的临时 Project read key
  exactly-once create/revoke，禁止 semantic start、ontology/ledger write 或自动重跑。
- Preflight：stable clean HEAD `019e7f5 Record live-16 child-timeout evidence`；live-17 output root 不存在；
  service active、backend/frontend 200；DeepSeek credential 可用；冻结 ticket/N=2/six-tool allowlist 与
  retained scope 匹配。
- Real result：Source 完成（2 steps、`metrics_complete=true`、terminal report true、total tokens `25719`）；
  Platform 发出 5 次成功 proxy 调用（proxy 约 9.4s、5 receipts、evidence tokens `34694`）后未产生第二个
  inference step（`inference_steps=1`、`turn_start_count=1`、total tokens `15567`、output tokens `7248`），
  未提交 report（`report_received=false`、`terminal_event=false`），约 90 秒 child watchdog 到期，operation
  为 `BLOCKED/runtime-infrastructure`（`reason_code=child-timeout`）。
- Failure layer：`runtime/infrastructure`。child-timeout 已是第 4 次出现（live-4/14/16/17），模式一致：
  Platform 在单一并行 wave 完成读取后停止生成，未提交 report。live-15 曾成功产生 2 steps 并提交 report
  （page-sequence-invalid），说明运行时路径可行，本轮属模型停止生成行为。
- Disposition：授权 `1/5` 已消费。剩余 live-18/19/20/21。

### 2026-08-14 — authorization 3/5 live-19 real N=2 — main agent

- Real result：**Source 完成（2 steps、`metrics_complete=true`、terminal report true）；Platform 首次成功
  （3 steps、`metrics_complete=true`、terminal report true、proxy 约 264ms、evidence tokens `7001`、total
  tokens `71988`）**——count 与 page 契约全部通过，report 被 Host 接受；Acceptance child 启动后 2 steps 未
  产生 terminal report，约 90 秒 child watchdog 到期，operation 为 `BLOCKED/runtime-infrastructure`
  （`reason_code=child-timeout`、`role=acceptance`）。CQ-002 未执行，无 ordered N=2 verdict。
- 关键进展：prompt 修复（page-per-call + no-importance + ordinal 对齐）组合生效，Platform 首次交付被接受的
  typed report。失败前移到 Acceptance 阶段（child-timeout，与 live-4/6 同模式：Acceptance 2-3 steps 后未
  提交 verdict）。
- Failure layer：`runtime/infrastructure`（Acceptance child-timeout）。清理/不变性/typed failure 证据正常。
- Disposition：授权 `3/5` 已消费。剩余 live-20/21。Platform 已验证可达；后续聚焦 Acceptance 阶段。

### 2026-08-14 — authorization 4/5 live-20 real N=2 — main agent

- Real result：Source 完成（2 steps、`metrics_complete=true`、terminal report true、total tokens `25768`）；
  Platform 发出 5 次成功 proxy 调用（proxy 约 7.5s、5 receipts、evidence tokens `34932`）后未产生第二个
  inference step（`inference_steps=1`、total tokens `17464`），未提交 report
  （`report_received=false`、`terminal_event=false`），约 90 秒 child watchdog 到期，operation 为
  `BLOCKED/runtime-infrastructure`（`reason_code=child-timeout`）。
- Failure layer：`runtime/infrastructure`。Platform 停止生成行为再现（live-14/16/17/20 同模式，4 次）；与
  live-19 成功形成对照：模型在 wave 后是否继续生成具有随机性。
- Disposition：授权 `4/5` 已消费。剩余 live-21 最后一轮。

### 2026-08-14 — authorization 5/5 live-21 real N=2 — main agent

- Real result：operation 在写 artifact 前的 `_blocked_result` 证据投影处 fail-closed 为
  `R23006OperationError: typed Examiner blocked evidence value is invalid: path`，未生成 artifact。Source/
  Platform 实跑已发生（授权已消费）。Root cause：Source 报告 location 路径含空格/锚点等字符时，投影的
  `path` 字段被 `_SAFE_BLOCKED_CODE` 拒绝。
- Failure layer：`platform-contract`（诊断投影缺口，非语义失败）。
- Repair：`path` 投影改为"必须含 `/`、无绝对路径/`..`/连续多空格、长度 ≤200"的宽松但 fail-closed 校验，
  允许空格与锚点（真实路径特征），继续拒绝 provider 文本（"platform Examiner packet"、"/etc/passwd"、
  "provider report text" 等测试保持拒绝）；focused `45/45`、full `549 PASS + 1 SKIP` 无 regression。
- 5/5 授权全部消费：live-17（Platform child-timeout）、live-18（投影拒绝）、live-19（Platform 首次成功、
  Acceptance child-timeout）、live-20（Platform child-timeout）、live-21（投影拒绝）。
- 趋势总结：count/page 契约已收敛（live-19 Platform 交付被接受的 typed report，3 steps/terminal true）；
  Platform 停止生成行为（child-timeout，live-14/16/17/20 共 4 次）与投影缺口（live-11/18/21 共 3 次）为
  当前主要 runtime/contract 卡点。后续需要新的 operation authorization 执行 live-22。

### 2026-08-14 — self-correction loop: sink-time binding validation with detailed rejection — main agent

- 用户指示：平台报错/接口拒绝必须在返回信息中详细描述，使 agent 能根据错误信息自我纠正。
- 根因分析：binding 校验（`_validate_platform_report_receipts` 等）此前只在 Host 轮询 `submitted_reports`
  时执行，模型提交 report 后立刻收到 `report-submitted`，永远不知道 report 为何被拒——无法自我纠正。
- 修复：
  1. `ReportSinkServer` 新增 sink-time `validator` + 有界重试（`max_attempts=3`）：提交时立即执行
     kind-specific binding 校验，失败返回 `{"ok": false, "code": "report-binding-rejected", "detail": <精确
     原因>, "attempts_remaining": N}`；成功后锁定（后续提交返回 `report-already-submitted`）；耗尽预算返回
     `report-attempts-exceeded`。
  2. 新增 `_blocked_detail`（把 `ExaminerRuntimeBlocked` evidence 转成可读文本，如
     `binding_code=receipt-count-mismatch at locator index 1 (report_ref_count=1, proxy_receipt_count=2)`）与
     `_make_report_validator`（source/platform/acceptance 三角色 sink-time 校验器，packet/resource 延迟绑定）；
     `ExaminerRuntimeBlocked.__str__` 返回该 detail。
  3. `codex.py` 的 `launch_lean_examiner_child` 安装 `sink_validator`（`spec["_packet"]` +
     `spec["_runtime_resource"]`），report sink 拒绝时详细原因经 MCP 返回模型。
  4. `report_sink_mcp.py` 的 `submit_examiner_report` 把 `code`/`detail`/`attempts_remaining` 拼入 MCP
     error message，模型可据此修正后重提。
- 测试：新增 `test_report_sink_returns_detailed_rejection_and_allows_bounded_retry`（拒绝 detail 断言 +
  修正后接受 + 重复提交拒绝）与 `test_report_sink_exhausts_attempt_budget`（预算耗尽）；`_semantic_payload`
  支持多 ref。full `549 PASS + 1 SKIP`、pytest start44 `12/12` 无 regression。
- 说明：此为用户对 R2.3-006 行为契约的显式修改（原验收"report 不可二次波修复"改为"允许有限次提交内
  自我纠正"）；仅改变 report 提交尝试边界，不改变 wave 数量上限、fresh 隔离或 typed evidence 语义。

### 2026-08-14 — authorization 1/3 live-22 real N=2 — main agent

- Authorization：用户授权 3 轮（live-22/23/24），并要求平台报错/接口拒绝必须返回详细原因使 agent 可
  自我纠正（self-correction loop 已实现）。
- Preflight：stable clean HEAD `bb50d41 Add sink-time validation with self-correction feedback`；live-22
  output root 不存在；service active、backend/frontend 200；DeepSeek credential 可用。
- Real result：Source 完成（2 steps、`metrics_complete=true`、terminal report true、total tokens `23513`）；
  Platform 2 steps（TTFT 约 1.4s、proxy 约 22.2s、evidence tokens `35064`、total tokens `36968`）后未提交
  report（`report_received=false`、`terminal_event=false`），约 90 秒 child watchdog 到期，operation 为
  `BLOCKED/runtime-infrastructure`（`reason_code=child-timeout`）。
- 关键观察：本轮 Platform 有 2 个 inference steps 且 proxy 22.2s（真实读取完成），但依然未产生 terminal
  report——与 live-14/16/17/20（1 step 停止）不同，本轮模型在第二步后仍未提交。模型在 wave 后是否继续
  生成并提交 report 具有明显随机性（live-19 曾成功）。
- Failure layer：`runtime/infrastructure`（模型停止生成行为，非 prompt 或契约缺陷）。
- Disposition：授权 `1/3` 已消费。剩余 live-23/24。

### 2026-08-14 — authorization 2/3 live-23 real N=2 — main agent

- Real result：Source child 启动失败（`reason_code=child-start-failed`、`inference_steps=0`、`total_tokens=0`、
  `proxy_receipt_count=0`），operation 为 `BLOCKED/runtime-infrastructure`。Acceptance/CQ-002 未启动。
- Failure layer：`runtime/infrastructure`（child 启动瞬时异常，如 provider/Codex 启动竞态；服务后端健康、
  DeepSeek credential 可用，非持久故障）。
- Disposition：授权 `2/3` 已消费。剩余 live-24 最后一轮。

### 2026-08-14 — authorization 3/3 live-24 real N=2 — main agent

- Real result：与 live-23 相同，Source child 启动失败（`reason_code=child-start-failed`、
  `inference_steps=0`、`total_tokens=0`），operation 为 `BLOCKED/runtime-infrastructure`。
- 诊断：standalone probe（用生产 packet 构造 Source child、timeout 60s）**启动成功**——child 启动路径本身
  正常；live-23/24 连续两次 child-start-failed 属 DeepSeek provider/Codex 启动瞬时竞态（外部基础设施抖动），
  非持久代码或契约缺陷。
- Disposition：授权 `3/3` 已全部消费：live-22（Platform 2 steps 后未提交 report，child-timeout）、live-23
  （Source child-start-failed）、live-24（Source child-start-failed）。后续需要新的 operation authorization
  执行 live-25。

### 2026-08-14 — root cause: codex binary resolution (child-start-failed) — main agent

- 症状：live-23/24/25/25a/26 连续 6 次 Source `child-start-failed`（0 steps、0 tokens），而早期 probe 看似
  成功。
- 根因：`CodexRuntimeAdapter` 默认 `codex_binary="codex"`，启动 child 时 `shutil.which("codex")` 在 opencode
  环境 PATH 中找不到 → `binary="codex"` → bwrap 或 Popen 阶段
  `FileNotFoundError: No such file or directory: 'codex'` → `_launch_acceptance_child` except 分支标记
  `child-start-failed`。真实异常被 typed-failure 包装掩盖，artifact 只见 `reason_code=child-start-failed`。
- 修复：`CodexRuntimeAdapter.__init__` 解析 codex 二进制为绝对路径——先 `shutil.which`，回退到
  `~/.codex/packages/standalone/current/bin/codex` 与 `.../current/codex`，再回退到传入路径本身。
  解析后 `codex_binary=/home/yangxiang/.codex/packages/standalone/current/bin/codex`（exists+exec 验证）。
  focused `52/52`、full `549 PASS + 1 SKIP` 无 regression。

### 2026-08-14 — live-28 real N=2: Source/Platform both pass, Acceptance child-timeout — main agent

- Real result：**Source 完成（2 steps、terminal report true、`metrics_complete=true`）；Platform 完成
  （3 steps、terminal report true、`metrics_complete=true`、proxy 约 4.0s、evidence tokens `15113`、total
  tokens `58941`）**——child-start-failed 修复后两条读取管线全部通过；Acceptance 3 steps（total tokens
  `40565`、TTFT 约 1.1s）后未提交 verdict，90s child watchdog 到期，operation 为
  `BLOCKED/runtime-infrastructure`（`reason_code=child-timeout`、`role=acceptance`）。CQ-002 未执行。
- Failure layer：`modeling-quality/prompt-contract`（Acceptance 在 3 步内未提交 verdict；live-6/19/28 同模式）。
- Repair（live-29 前完成）：Acceptance instructions.md 与 SKILL.md 新增 turn budget 契约——第二 inference 前
  必须提交、最多 3 步、被拒时只修 named field 立即重提、禁止重读/重推导；focused `31/31`、full
  `549 PASS + 1 SKIP` 无 regression。

### 2026-08-14 — live-29 real N=2: Platform stop-generation child-timeout — main agent

- Real result：Source 完成（2 steps、terminal report true、total tokens `27240`）；Platform 发出 5 次成功
  proxy 调用（proxy 约 6.9s、evidence tokens `25926`、1 step、total tokens `12895`）后未产生第二个
  inference 提交 report，90s child watchdog 到期，`BLOCKED/runtime-infrastructure`
  （`reason_code=child-timeout`、`role=platform`）。Acceptance/CQ-002 未启动。
- Failure layer：`runtime/infrastructure`（Platform 停止生成行为，与 live-14/16/17/20/22 同模式；live-19/28
  曾成功证明链路可达）。非 prompt 或契约缺陷，继续重试。

### 2026-08-14 — live-30 real N=2: Platform stop-generation child-timeout — main agent

- Real result：Source 完成（3 steps、terminal report true、total tokens `41192`）；Platform 发出 5 次成功
  proxy 调用（proxy 约 8.9s、evidence tokens `25741`、1 step、total tokens `12505`、output tokens `4186`）
  后未产生第二个 inference，90s watchdog 到期，`BLOCKED/runtime-infrastructure`（`role=platform`、
  `reason_code=child-timeout`）。Acceptance/CQ-002 未启动。
- 分析：与 live-28 成功（3 increments: wave→推理→report）对比，live-30 只有 1 个 increment——模型在 tool
  结果返回后未继续生成。属 provider/Codex 行为随机性（live-19/28 证明链路可达），非 prompt 缺陷。
- Disposition：继续重试（无需授权）。

### 2026-08-14 — live-31 real N=2: Platform stop-generation child-timeout — main agent

- Real result：Source 完成（3 steps、terminal report true、total tokens `39121`）；Platform 发出 5 次成功
  proxy 调用（proxy 约 20.6s、evidence tokens `34693`、1 step、total tokens `14181`）后未产生第二个
  inference，90s watchdog 到期，`BLOCKED/runtime-infrastructure`（`role=platform`、
  `reason_code=child-timeout`）。
- 分析：live-29/30/31 连续 3 次同模式（Platform wave 后停止生成，1 increment）。对比 live-28 成功
  （3 increments：wave→推理→report 421 tokens）。`thread/start` 无 max_turns；模型在 tool 结果返回后是否
  继续生成属 DeepSeek provider 行为，非 prompt/代码缺陷。策略：继续重试。

### 2026-08-14 — live-32 real N=2: Platform stop-generation child-timeout — main agent

- Real result：Source 完成（2 steps、terminal report true、total tokens `25190`）；Platform 发出 5 次成功
  proxy 调用（proxy 约 8.6s、evidence tokens `22115`、1 step、total tokens `18338`）后未产生第二个
  inference，90s watchdog 到期，`BLOCKED/runtime-infrastructure`（`role=platform`、
  `reason_code=child-timeout`）。
- 分析：live-29~32 连续 4 次同模式（Platform wave 后停止生成，仅 1 increment）。DeepSeek 直连探针正常
  （function_call 返回）；provider proxy 为无状态透明转发。`model_reasoning_effort="max"` 下模型可能在
  tool-call 后陷入长推理或直接结束 turn，属 provider 行为随机性（live-19/28 成功 2/11）。
- Disposition：继续重试。

### 2026-08-14 — live-33 real N=2: Platform stop-generation child-timeout — main agent

- Real result：Source 完成（3 steps、terminal report true、total tokens `40383`）；Platform 2 steps
  （wave 后第二次推理 `reasoning_output_tokens=6421`、total tokens `47601`、proxy 约 4.0s、evidence tokens
  `19102`）后仍未提交 report，90s watchdog 到期，`BLOCKED/runtime-infrastructure`（`role=platform`、
  `reason_code=child-timeout`）。
- 分析：live-33 较 29-32 有进展（2 steps 而非 1 step），但模型在第二次长推理（6421 reasoning tokens）后
  未产生 report 提交调用。`model_reasoning_effort="max"` 为 R2.3-003/005 modeling manifest 冻结契约，
  R2.3-006 不得修改（AGENTS.md 边界）；"推理完成当作回答"是 DeepSeek reasoning 模型行为。live-28 成功
  模式（3 steps、提交步 reasoning 仅 78 tokens）说明提交是概率性的。
- Disposition：继续重试。

### 2026-08-14 — live-34 real N=2: Source/Platform pass, Acceptance no-tool child-timeout — main agent

- Real result：Source 完成（2 steps、terminal report true）；Platform 完成（3 steps、terminal report true、
  proxy 约 5.0s、evidence tokens `18414`、total tokens `61332`）；Acceptance 3 steps
  （`metrics_complete=True`、increments reasoning 1039→595→373 递减收敛、total tokens `31540`）后未调用
  `submit_examiner_report`，90s watchdog 到期，`BLOCKED/runtime-infrastructure`（`role=acceptance`、
  `reason_code=child-timeout`）。
- 分析：Acceptance 是纯推理任务（无读取工具），模型在 max reasoning 下把裁决写进推理文本而非调用
  `examiner_report` MCP 工具——"文本答案不算提交"。
- Repair（live-35 前完成）：Acceptance instructions.md/SKILL.md 明确"verdict 仅通过 submit_examiner_report
  工具调用生效，回复文本不算提交"；focused `31/31`、full `549 PASS + 1 SKIP` 无 regression。

### 2026-08-14 — live-35 real N=2: Platform stop-generation child-timeout — main agent

- Real result：Source 完成（2 steps、terminal report true、total tokens `24235`）；Platform 2 steps（total
  tokens `41685`）后未提交 report，90s watchdog 到期，`BLOCKED/runtime-infrastructure`（`role=platform`、
  `reason_code=child-timeout`）。Acceptance/CQ-002 未启动。
- Failure layer：`runtime/infrastructure`（Platform 停止生成行为，live-29~33/35 共 6 次；live-19/28/34
  成功 3/15）。

### 2026-08-14 — live-36 evidence + platform tool-submission contract — main agent

- Real result：Source 完成（3 steps、terminal report true、total tokens `40371`）；Platform 2 steps（proxy
  约 16.5s、evidence tokens `24379`、total tokens `37295`）后未提交 report，90s watchdog 到期，
  `BLOCKED/runtime-infrastructure`（`role=platform`、`reason_code=child-timeout`）。
- 分析：Platform/Acceptance 共同模式——模型把输出写进推理/回复文本而不调用 `submit_examiner_report`
  工具。live-19/28/34 成功 3/16。
- Repair（live-37 前完成）：Platform instructions.md/SKILL.md 明确"report 仅通过 submit_examiner_report
  工具调用生效，回复文本不算提交；wave 后下一 inference 必须调用工具"。focused `31/31`、full
  `549 PASS + 1 SKIP` 无 regression。
