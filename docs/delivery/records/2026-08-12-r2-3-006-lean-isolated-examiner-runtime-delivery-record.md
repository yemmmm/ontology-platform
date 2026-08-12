# R2.3-006 精简隔离 Examiner Runtime Delivery Record

- Requirement source：`docs/requirements/requirements-v2.3.md#r23-006-精简隔离-examiner-runtime`
- Status：development-ready（需求/设计已通过 Round2 review，未实施）
- Started：2026-08-12T16:34:22+08:00
- Last updated：2026-08-12T16:52:00+08:00
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

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| 0 | docs draft | UNEXECUTED | requirement implementation not started | shared plan §4 |

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
