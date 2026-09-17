# R3.0-016 建模 Team 宿主交互接口 S1 — 交付设计

- 日期：2026-09-18
- 状态：需求已登记并按外部意见修订（2026-09-17）；本文为 **S1（查询与存活 run 交互闭环）**
  交付设计。未实现、未独立功能验收、未真实 L0；不授予代码实施、真实 semantic start
  或额外业务审批权限。
- 需求：[R3.0-016](../../requirements/requirements-v3.0.md#r30-016-建模-team-宿主交互接口)
  （运行语义继承 R3.0-006；CQ 访谈/审核/冻结继承 R3.0-011；验收目标继承 R3.0-012；
  检查点接续继承 R3.0-015）
- 测试：[共享测试计划](../test-plans/2026-09-18-r3-0-016-s1-host-interaction-interface-test-plan.md)
- 基线：2026-09-18 只读代码核对，见 §2 与附录 A。本文把当前代码当现状证据，
  不当目标定义依据。

## 1. 目标与非目标

目标（S1）：宿主从已知 `run_id` 出发，经可复用的本地操作层与宿主专用 MCP 工具完成
"查询待办 → 提交答复/修复通知/审核冻结/交接收口 → 核对处理结果"的闭环；常规操作不要求
调用方知道文件布局、FIFO 路径或拼装底层信封；自然语言理解、业务判断与授权决定留在宿主。

非目标（本轮明确排除）：

- **S2 全部动作**：`start_run`、`pause/resume/stop`、检查点动作（inspect/save/resume/
  settle_source_run 的封装）不做任何实现，也不留 S2 占位工具或空壳参数；现有 outer
  `pause/resume/stop/checkpoint` 原通道行为不变，只是不经 S1 工具暴露。
- 保留 CLI：`classify-failure`、`authorize-repair`、`authorize-budget`、`authorize-initial`
  （归因与授权台账登记）、`publish-handoff`（离线交接发布，≠ `cq_handoff_complete`）、
  `cq-acceptance`（独立验收执行器，产生报告）。运行手册须列明各自适用合同与调用时机。
- 不新增：HTTP 服务化、后台任务队列/通用调度、自动批准/自动修复/写门重开、跨机器访问、
  用户/RBAC、平台资源 API、心跳框架。
- 操作层不判断业务语义、不解读自然语言、不替用户生成答案或批准。

## 2. 当前代码事实与缺口（2026-09-18 核对）

| 现状落点 | 已有能力 | S1 缺口（本设计最小补齐） |
| --- | --- | --- |
| `modeling_team/outer_input.py::OuterInputFifo` | FIFO 帧化：0600 FIFO/0700 目录、keeper fd、64KiB 行上限、UTF-8、坏帧 `OuterInputFramingError` | 无（作为传输复用；操作层按同约束写线） |
| `__main__.py::_handle_foreground_message`（stdin/FIFO 共用准入） | `_KNOWN_OUTER_ACTIONS`、`_CQ_OUTER_ACTIONS` 分发；无副作用拒绝经 `outer-input-rejected`/`cq-input-rejected` **只打到宿主 stdout**，不落任何可查文件 | 类型化拒绝无处可查 → `get_request_result` 需最小持久回执（§5） |
| `runner.py::receive_outer` / `handle_cq_outer_input` | user/question/issue_resolution/recover_provider 与 cq_interview/cq_review/cq_freeze/cq_handoff_complete/cq_acceptance_complete 已有严格信封校验与类型化拒绝 | 请求级关联只有 `checkpoint` 携带 `request_id`；其余动作无 request_id、无回执 |
| 分种类证据（`_append_evidence`，`<run-root>/evidence/*.jsonl`，均带 `recorded_at`） | outer-question/outer-user/owner-answer-failure、issue-report/issue-control/issue-resolution、provider-wait、cq-review-request/cq-review-decision/cq-freeze/cq-handoff-complete/cq-acceptance-complete/cq-wait-windows、runtime-failure/terminal-classification/settled、staged-decisions/multi-slice-* 等（全集见附录 A） | 无统一快照/待办/增量事件读取入口；宿主今天要手读多文件 |
| `state.json`（`_state`，覆盖写） | 顶层生命周期记录 | 外层 `status` 只触发 drain+provider 等待，不是快照（runbook 已确认） |
| 存活证据 | `checkpoint_recovery.py::chain_writer_lock_report` 有锁/PID 证据，仅适用带恢复来源的续跑 run | fresh run 无身份绑定 → 只能 unknown，需可查询的宿主登记约定（§7.1） |
| MCP 先例 | `backend/app/mcp/server.py`（FastMCP，`mcp>=1.0` 在 backend venv）；`modeling_team/capability_mcp.py`（自研 stdio JSON-RPC）；宿主配置片段先例 `.claude/ontology-mcp.json` | 无宿主专用 MCP 工具面 |
| 运行根 | `workspaces/modeling-runs/<run_id>`（`runner.py` L884） | 需 run_id→run-root 的安全解析（§8） |

## 3. 总体架构

三层，全部同机、无新服务：

```text
宿主 Agent（Codex/Claude Code/操作人）
  └─ 宿主专用 MCP 工具（stdio）modeling_team/host_ops_mcp.py   # 仅固定 12 个工具
       └─ 本地操作层 modeling_team/host_ops.py                  # 纯 Python，无业务语义
            ├─ 读：run-root 文件（evidence/*.jsonl、state.json、任务/Profile 快照、检查点锁证据）
            ├─ 观察：/proc（仅当宿主登记了 PID）、FIFO 存在性（仅作事实，不作存活）
            └─ 写：control/outer-input.fifo 一条完整 NDJSON 行（既有 outer 动作信封）
                 + control/host-requests.jsonl 提交台账
Runner 进程（现有 CLI 启动，S1 不改启动方式）
  └─ 既有准入路径 + 新增最小回执（evidence/outer-input-receipts.jsonl，§5）
```

- `host_ops.py` 不 import Runner 运行时（不实例化 `TeamRunner`）；只允许复用纯合同函数
  （如 `competency_questions.batch_report_acceptance_verdict`、`content_digest`）与
  `outer_input` 的行上限常量。读工具不调用 drain、平台 API、模型或恢复逻辑。
- `host_ops_mcp.py` 用 backend venv 的 `mcp` 包（FastMCP）注册固定工具面；服务器名
  `modeling-team-host`。工具名沿用需求表：`get_run_status`、`get_run_events`、
  `get_pending_actions`、`answer_question`、`register_question`、`submit_cq_review`、
  `freeze_cq`、`complete_cq_handoff`、`complete_cq_acceptance`、`resolve_issue`、
  `recover_provider`、`get_request_result`。S2 名称不注册。
- 配置交付：仓库新增独立片段 `.claude/modeling-team-host-mcp.json`（仿现有
  `.claude/ontology-mcp.json`，`command` 指向 `backend/.venv/bin/python`，
  `args: ["-m", "modeling_team.host_ops_mcp"]`，`cwd` 为仓库根），运行手册给出
  Claude/Codex 两侧的手工接入步骤。**不自动修改任何全局宿主配置**；生产
  `backend/app/mcp/tools/` 与 `modeling_team/agent-packages` 角色工具目录零改动。

## 4. S1 动作合同

通用约定：所有动作第一个参数 `run_id`；变更类动作额外接受可选 `request_id`（§5）。
结果信封统一 `{ok, data|error}`；错误为 `{code, object?, reason, retryable, next_action}`
（§9）。"提交结果"均含 `status ∈ {submitted, accepted, rejected}` 与查询提示；`unknown`
只出现在 `get_request_result`。

| 动作 | 结构化输入 | 底层通道 | 返回要点（关键行为） | 主要复用错误码 |
| --- | --- | --- | --- | --- |
| `get_run_status` | `run_id` | 只读文件+/proc | §7.1 快照：记录状态、阶段、最后可核实活动、有效语义进展、第一阻塞、待办摘要、终态结论、存活观察、证据引用、观察时间、限制 | `run_not_found`、`run_id_invalid` |
| `get_run_events` | `run_id`、可选 `cursor`、`limit`（默认 200，上限 1000） | 只读 `evidence/*.jsonl` | 事件列表（带 source 与源内序）、`next_cursor`、`has_more`、`limitations`；不触发 drain/写入 | `cursor_run_mismatch`、`cursor_invalid` |
| `get_pending_actions` | `run_id` | 只读派生（§7.2） | 待办列表：稳定标识、类型、状态、内容或获准引用、版本绑定、可用动作与必填绑定；已消费问题不再显示；不可答问题给出原因（需注册走 `register_question`） | 同上；缺文件记 limitation 不报错 |
| `answer_question` | `run_id`、`channel: user\|cq_interview`、`text`（中文多行原样）、`question_delivery_id`（user 必填，来自待办）、`wait_for_draft?`（cq） | FIFO `user` / `cq_interview` | 提交结果；接受回执含消费/序号证据；普通问题与 CQ 访谈是两条不同通道，不互通 | `invalid_owner_answer`、`owner_answer_rejected`、`cq_selector_incompatible` |
| `register_question` | `run_id`、`delivery_id`（显式宿主 ID）、`text` | FIFO `question` | 提交结果；仅在既有通道要求宿主注册时使用；答复失败后不自动注册替代问题；formal run 的 Runner-owned 拒绝原样透传 | `invalid_outer_question` |
| `submit_cq_review` | `run_id`、decision（`review_id`、`question_id`、`decision`、`content_version`、`content_digest`、`revision`、`modified_question?`、`note?`，绑定取自待办） | FIFO `cq_review` | 提交结果；沿用直接通道与原审批条件 | `cq_review_stale`、`cq_selector_incompatible` |
| `freeze_cq` | `run_id` | FIFO `cq_freeze` | `freeze_id`、`snapshot_digest`、公开题 ID、隐藏题计数；审核与冻结是不同动作，未经审核的冻结维持原拒绝 | `cq_freeze_schema_mismatch` |
| `complete_cq_handoff` | `run_id`、`freeze_id`、`freeze_digest`、`delivery_binding?`（绑定默认取自待办） | FIFO `cq_handoff_complete` | 提交结果 + `acceptance_phase=acceptance_pending`、`acceptance_attempt_id`、`report_directory`；复用在途/未知写入检查；成功不报整轮完成 | `cq_review_stale`、`cq_freeze_schema_mismatch` |
| `complete_cq_acceptance` | `run_id`（可选 `acceptance_attempt_id` 消歧） | FIFO `cq_acceptance_complete` | 工具从保留报告文件计算 `report_digest` 并用 `batch_report_acceptance_verdict` 复算 `cq_verdict` 组信封；Runner 复读核验后返回实际收口状态；仅适用 live `cq_semantic`；报告由 CLI `cq-acceptance` 产生（保留） | `cq_acceptance_report_mismatch`、`cq_review_stale`、`cq_selector_incompatible` |
| `resolve_issue` | `run_id`、`issue_id`、`reporter_id`、`control_epoch`、`resolution_type`、`repair_component?`、`resolution_text`、其余 `IssueResolution` 可选字段 | FIFO `issue_resolution` | 提交结果；绑定取自待办的当前 issue；普通便签渠道不提供（不冒充修复通知） | `issue_resolution_rejected`、`unknown_mutation_requires_reconciliation`、`coordinator_waiting_provider` |
| `recover_provider` | `run_id`、`agent_id` 或 `role` 二选一、`wait_id?`、`text`（恢复说明） | FIFO `recover_provider` | 提交结果 + `agent_id/wait_id/dispatch_mode`；不自动换模型、不重建线程、不开新 run | `invalid_provider_recovery`、`provider_wait_not_pending`、`provider_recovery_failed` |
| `get_request_result` | `run_id`、`request_id` | 只读回执台账+提交台账+分种类证据 | `outcome ∈ {accepted, rejected, submitted, unknown}` + 证据引用 + 下一步查询方式；动作接受 ≠ 建模完成/语义开始 | `request_id_unknown`、`request_id_conflict`、`run_not_found` |

文本原样传递：`text` 字段不做换行/空白归一；FIFO 行仍受 64KiB 上限，超限在操作层
先拒绝（`fifo_line_too_large`，同传输层语义），不写半行。

## 5. 请求标识与回执（最小关联机制）

现状：FIFO 写成功 ≠ Runner 接受；类型化拒绝只上 stdout；按需求 §提交确认反馈 3
"已有通道缺少关联确认时补最小关联与回执，不新增通用任务队列或调度系统"。

1. **信封**：变更类工具接受可选 `request_id`（非空字符串，长度 ≤128）。操作层把
   `request_id` 作为 NDJSON 行的**唯一新增顶层键**写入；共享准入包装
   （`_handle_foreground_message` 解码后、任何校验/分发之前，CQ 分支与 `receive_outer`
   共用）将其 pop 掉，因此各动作既有的严格字段校验看到的信封与现行完全一致
   （schema-v2 `user` 拒绝额外字段、`cq_acceptance_complete` 精确集合匹配等均不受
   影响）。**不带 `request_id` 的旧行为逐字节不变**；带 `request_id` 的行仅多一个
   顶层键，且该键不会到达任何动作校验器。
2. **提交台账（宿主侧）**：FIFO 写成功后，操作层追加一行
   `<run-root>/control/host-requests.jsonl`（0600，host 私有 control 目录，与 FIFO 同属
   宿主控制面）：`{request_id, action, content_digest, submitted_at}`。
   `content_digest` 为剥离 `request_id` 后动作信封的 canonical JSON sha256。
3. **准入回执（Runner 侧，最小改动）**：前台准入路径（`_handle_foreground_message`
   及 CQ 分支共用包装）在校验 `request_id` 存在时：pop 后分发；按准入结果追加一行
   `evidence/outer-input-receipts.jsonl`（复用 `_append_evidence`）：
   `{request_id, action, outcome: accepted|rejected, code?, ack_type?, content_digest}`。
   拒绝（含未知 action、坏 JSON、CQ 拒绝、`RecoverableOuterInputError`）同样落回执；
   持久化/发送失败的现行 fatal 边界不变（此时无回执，查询结果为 unknown）。
   FIFO **帧**错误（`OuterInputLineTooLong`/`OuterInputInvalidUtf8`）发生在准入包装
   之前，不落回执——此时仅有宿主提交台账，`get_request_result` 按序落到
   submitted/unknown；与"传输超时/部分提交不推断零写入"的既有边界一致，不另造
   回执通道。
4. **`get_request_result` 判定**（按序）：
   - 回执 `accepted` → `accepted`，附分种类证据引用（如 `issue-resolution.jsonl`、
     `outer-user.jsonl`、`cq-acceptance-complete.jsonl`）与"接受≠推进"的对应状态/事件
     查询提示；
   - 回执 `rejected` → `rejected`，附 code 与修正建议（不报 accepted）；
   - 仅提交台账、run 仍可能存活（§7.1 观察非终态）→ `submitted`（保留最后已知
     submitted 事实，附观察时间与再查方式）；
   - 仅提交台账、run 已终态/准入通道消失且无回执 → `unknown`（不自动重发、不换新
     ID 绕过、不改报失败重试）；
   - 无台账 → `request_id_unknown`；台账与回执 `content_digest` 不一致属异常，报告
     `request_id_conflict` 并指向证据。
5. **重复与冲突**：提交前操作层查同一 run 的台账+回执——同 `request_id` 同
   `content_digest` 且已有终局回执 → 直接返回原结果（"已处理"+引用），**不再写 FIFO**；
   同 `request_id` 不同 `content_digest` → `request_id_conflict` 明确拒绝。Runner 侧
   现行幂等（问题消费、issue 状态机、`cq_acceptance_complete` 幂等确认）不改动，
   作为第二道防线。
6. **无通用队列**：回执与台账都是 append-only JSONL 事实记录，无调度、无重试、无跨
   run 语义；`request_id` 作用域限单 run（台账在 run 根内）。

## 6. 事件 cursor 语义（`get_run_events`）

- **来源发现**：每次调用枚举 `<run-root>/evidence/*.jsonl` 当前实际存在的文件为源；
  不维护固定清单，因此"后出现的事件源"自动从 offset 0 读到，不漏读。`state.json` 是
  覆盖写快照，不入事件流（由 `get_run_status` 负责）。
- **cursor**：opaque（base64 JSON `{"v":1,"run_id":...,"offsets":{"<source>": <byte_offset>}}`），
  携带各源独立字节偏移；单 cursor ≠ 单时间戳，不用近似时间当高水位。cursor 内
  `run_id` 与请求不符 → `cursor_run_mismatch`；解析失败/版本不识 → `cursor_invalid`
  （不静默从头重扫）。
- **续读与选页**（2026-09-18 按独立测试 I Round 2/3 发现修订——原"合并排序取前 limit"
  的选页在多源停驻时不收敛）：每源只从其 offset 读到 EOF 的**完整换行行**构成该源
  候选池。每页**选集**：为每个非空池的首个未交付行（停驻头；按停驻不变量恒为本页
  视角未交付）保留保底交付槽位——停驻源数超过 limit 时按 `(head byte_offset, source)`
  升序确定性轮转，任意 `limit≥1` 无饥饿；其余槽位按 `(recorded_at, source, 源内行号)`
  合并序从各池其余候选填充。**页内输出**仍按 `(recorded_at, source, 源内行号)` 排序
  （`recorded_at` 缺失排尾；输出标 `ordering: "recorded_at-approximate"`——跨源只保留
  来源与源内原顺序，不虚构严格因果）；选集决定交付哪些事件，页内排序合同不变。
- **投递保证与收敛性**：无遗漏——每个完整行（含坏行/超长行占位）至少投递一次；
  停驻窗口内 at-least-once（同一正常行可在后续页重投递），宿主以
  `(source, byte_offset)` 作为事件唯一标识去重；坏行/超长行占位恰投递一次。分页在
  有限页内收敛，`has_more=true` 的下一页必非空；较早时间戳的晚到追加行因写在文件尾、
  字节偏移只会前进，配合停驻头保底天然不漏。
- **半行**：末尾无换行的部分行留给下次（offset 不推进），不计损坏、不报完整，
  也不置位 `has_more`（无其它可交付行时）。
- **损坏行**：完整行解析 JSON 失败 → 输出显式占位
  `{source, line_no, corrupt: true, parse_error}`，offset 推过该行，`limitations` 标
  `complete:false`，不静默跳过后声称完整。
- **大小边界**：`limit` 界定事件数；单行超过事件字节上限（默认 256KiB）输出
  `{source, line_no, truncated: true, byte_length}` 占位并继续；不整包回传日志
  （`app-server-events.jsonl` 可能含完整工具参数，宿主自行遵守不注入生产角色的边界）。
- 首次调用无 cursor 从各源 offset 0 开始（可分页读历史）；`get_run_status` 附带一个
  当前末尾 `events_cursor`，供只要增量的宿主直接续读。

## 7. 状态与待办读取

### 7.1 `get_run_status` 快照与存活证据

字段组（无证据的一律 `unknown/unavailable`，不猜测）：

| 字段组 | 来源 |
| --- | --- |
| 身份 | `run_id`、run 根相对路径、Task/Profile 快照引用（`task.snapshot.yaml`、`profile.snapshot.yaml`）、模型绑定（Task/Profile/model profile 记录可得则给，否则 unknown）；平台关联 Project/Session 仅从 run 根记录（如 baseline/scope 快照）派生并标注来源，明确 `run_id ≠ session_id`；S1 读工具不调平台 API |
| 记录状态 | `state.json` 原文 `state` 与附加字段（cleanup 等） |
| 阶段 | 各阶段证据最新事件（staged-decisions、multi-slice-workflow/gate、competency-questions/cq-* 等） |
| 最后可核实活动 | 全部证据源最大 `recorded_at` + 源名（basis=`evidence-file`） |
| 有效语义进展 | `semantic-start.jsonl`、staged 决定/回执、终态分类等；与日志增长/进程活动分开表述，`RUNNING` 不算进展 |
| 第一阻塞 | `runtime-failure.jsonl`（第一失败层）、issue 状态（仅读 `issue-report.jsonl`+`issue-control.jsonl`+`issue-resolution.jsonl`+`state.json`，runbook 规则）、provider 等待；各自带来源；无则 null |
| 待办摘要 | §7.2 派生的计数+引用 |
| 终态结论 | `terminal-classification.jsonl`、`settled.jsonl`、`state.json` 终态字段；不存在不猜 |
| 存活观察 | 三分：(a) 记录状态=state.json；(b) 进程观察=有依据才报——续跑 run 用 `chain_writer_lock_report`；宿主可选写 `<run-root>/control/host-supervisor.json`（`{schema, pid, started_at, session_ref?}`，宿主写、Runner 不写），存在则查 `/proc/<pid>` 报 `pid_alive`+观察时间；二者皆无 → `unknown`，**不抹去已知等待/阶段/终态记录**；(c) `fifo_present` 作为独立事实返回，明确不作为存活或语义进展证据 |
| 元信息 | `observed_at`（整快照）、`evidence_refs`（相对路径+可读性）、`limitations`（文件暂缺/不完整/记录冲突/旧 run 缺新字段时逐条列出，可读部分照给，不把读失败包装成"无待办/已完成"） |

读取零副作用：不 drain、不模型调用、不恢复、不 cleanup、不平台写入、不要求迁移历史 run。

### 7.2 `get_pending_actions` 派生源

只读文件派生，不做内存推断；每项含稳定标识/类型/状态/内容或获准引用/版本绑定/可用
动作与必填绑定：

| 待办类型 | 派生源与规则 |
| --- | --- |
| 待答问题 | `outer-question.jsonl`（注册+展示事件）− `outer-user.jsonl`（已答绑定）− `owner-answer-failure.jsonl`（已烧毁）；可用动作 `answer_question(user)`；未展示/不可答给原因；需注册的显示 `register_question`。注意：注册与展示记录为**同形 4 字段且内容相同**，"已展示"只能由同一 `delivery_id` 出现两次（注册+展示）推断，不存在独立 `displayed` 事件字段；已答扣减依赖 `outer-user.jsonl` 的 delivery 绑定，仅对 schema-v2/staged run 可靠——legacy run 的 `outer-user.jsonl` 只记 `{"text"}` 无绑定，旧 run 已答问题无法可靠扣除，在 `limitations` 中标注，不据此误报可答 |
| CQ 访谈窗口 | 窗口开闭是 Runner 内存态（`CQWaitWindowTracker`），`cq-wait-windows.jsonl` 仅在 cleanup 时落一条 `closed-on-exit`，**运行期不存在，不得作为派生源**。派生改用：`cq-interview.jsonl` 最新记录的 `wait_window_open` 快照 + `cq-review-request.jsonl`/`cq-review-decision.jsonl` 的窗口阶段转换；可用动作 `answer_question(cq_interview)` |
| CQ 审核项 | `cq-review-request.jsonl` 当前 `review_id`/`content_digest`/`question_ids` 与审核快照引用（`competency-questions/reviews/`）；可用动作 `submit_cq_review`（带 question 绑定） |
| CQ 冻结待办 | 审核完成且未冻结（无 `cq-freeze.jsonl`）；可用动作 `freeze_cq` |
| issue 等待 | issue 三文件 + `state.json`；当前 issue 的 `issue_id/reporter_id/control_epoch` 与允许的 resolution；可用动作 `resolve_issue` |
| provider 等待 | `provider-wait.jsonl` 每 agent 最新 `observed` 起，**仅** `host-recovery`/`cleared` 收口（该文件不存在 recovery-failed 类事件，恢复失败落在 `issue-control.jsonl`）；`observed` 之后的其它事件（如 `issue-report-unavailable`、`issue-reported`、`coordinator-delivery-failed`）不关闭等待；`host-recovery` 之后的 `issue-settlement-skipped` 不重开等待；绑定 `agent_id/role/wait_id`；可用动作 `recover_provider`；标注 Runner 准入时仍实时复核 |
| CQ 交接/验收收口 | `cq-handoff-complete.jsonl`（`freeze_id/freeze_digest/acceptance_attempt_id/report_directory`）与 `cq-acceptance-complete.jsonl`、`state.json`：handoff 前给 `complete_cq_handoff` 绑定；`acceptance_pending` 给 `complete_cq_acceptance` 绑定与获准报告引用（报告存在性/digest 由工具在提交时计算，宿主不算摘要）；已收口显示结论 |

边界：CQ 私有内容只按既有获准面输出——审核快照引用与公开投影可给宿主/用户；
隐藏题只给计数/ID（沿用 `cq-frozen` ack 先例），隐藏答案/依据不在待办面出现。
检查点类待办属 S2，不派生。

## 8. 安全与隔离边界

- 工具面仅 12 个固定工具，参数结构化，无 shell/任意 Python 执行原语。
- `run_id` 走路径安全校验（非空、禁 `/`、`..`、长度 ≤128），解析后必须落在
  `repository_root()/workspaces/modeling-runs` 内；不接受任意 path 参数；返回的
  证据引用是相对路径引用，不构成读取原语。
- 宿主工具只经独立宿主配置暴露；不进入 `backend/app/mcp/tools/`、角色 agent-packages
  工具目录或任何生产/验收方配置。独立验收方沿用 `cq-acceptance` CLI 原合同，不获得
  本工具面（A07）。不向生产角色透传宿主环境/凭据；`host-requests.jsonl`、
  `host-supervisor.json` 是 host 私有 control 面，不进角色挂载。
- 操作层不判断业务语义、不自动批准、不重开写门；`unknown_mutation_requires_reconciliation`
  等拒绝原样透传；错误归因沿用四类与第一阻塞层，接口成功不推导建模质量。

## 9. 错误分类

- **透传优先**：Runner 的 `outer-input-rejected` 形（`code/retryable/detail/run_id/
  issue_id/...`）与 CQ 拒绝形（`object/phase/reason_code/retry`）原码原语义进操作层
  错误信封 `{code, object?, reason, retryable, next_action}`，不折叠为"执行失败"。
- **操作层新增码（仅传输/关联/读取层，最小集）**：`run_not_found`、`run_id_invalid`、
  `cursor_run_mismatch`、`cursor_invalid`、`outer_input_channel_unavailable`（无 FIFO/
  run 已终态/未启用 FIFO 的 run，返回限制说明）、`outer_input_write_timeout`、
  `fifo_line_too_large`、`request_id_conflict`、`request_id_unknown`、`request_id_invalid`
 （操作层收到的 request_id 形状非法，如空串/超长/非字符串）。
- **有界性**：FIFO 打开（O_WRONLY|O_NONBLOCK+poll，≤3s）、写（≤3s）、工具整体 ≤10s；
  通道消失立即类型化返回，不挂起、不占工具调用等终态。仅在已证明无副作用（未写线/
  未过准入）时承诺安全重试；写超时/部分提交不推断零写入。

## 10. 兼容与投放

- **既有 CLI 启动的 run**：S1 只附着，不改启动方式；带 `--enable-outer-input-fifo`
  的 run 全功能可用，未启用的 run 读工具可用、变更类工具返回
  `outer_input_channel_unavailable`。
- **旧消息/旧 run**：无 `request_id` 的消息行为不变、无回执（查询返回
  `request_id_unknown`+指引）；旧 run 无 cursor/台账/身份绑定 → 增量从当前文件状态
  起、存活 unknown，均可读部分照给（§7.1 limitations）。
- **服务重启**：本设计不改 `backend/`、`frontend/`，不需要重启
  `ontology-platform.service`；MCP 服务器是宿主侧 stdio 进程。若实现时引入任何
  backend 改动，按 AGENTS.md 重启规则执行。
- **运行手册**：`skills/modeling-dev-loop/references/team-runbook.md` 新增宿主工具节
  （配置片段接入、12 工具最小用法、保留 CLI 清单及适用合同、`request_id` 用法、
  存活登记约定）；不自动修改用户全局配置。

## 11. 验收标准映射（S1 覆盖 A01–A07、A11；A08–A10 为 S2 非目标）

| 编号 | 覆盖机制 | 主要测试组 |
| --- | --- | --- |
| A01 | §7.1 快照来源与零副作用约束；存活三分法 | A01 组 |
| A02 | §6 cursor/来源发现/半行/损坏/跨界拒绝 | A02 组 |
| A03 | `get_pending_actions`+`answer_question`(user/cq_interview)+`register_question`+`get_request_result` | A03 组 |
| A04 | `submit_cq_review`/`freeze_cq` 绑定透传与原通道 | A04 组 |
| A05 | `resolve_issue`/`recover_provider` 绑定透传；无"便签代修复"通道 | A05 组 |
| A06 | §5 回执/台账/重复/冲突/有界通道 | A06 组 |
| A07 | §3 配置隔离+§8 边界+§7.2 私有内容边界 | A07 组 |
| A11 | `complete_cq_handoff`/`complete_cq_acceptance`+待办绑定+CLI 报告保留 | A11 组 |
| A08–A10 | S2（start/生命周期/检查点），本轮非目标，不建桩 | — |

## 12. 实现落点与交付顺序

| 落点 | 必要修改 |
| --- | --- |
| 新 `modeling_team/host_ops.py` | 操作层：run 解析、状态快照、事件 cursor、待办派生、FIFO 有界写、提交台账、请求结果查询 |
| 新 `modeling_team/host_ops_mcp.py` | 固定 12 工具的 stdio MCP 服务器（backend venv 的 `mcp` 包） |
| `modeling_team/__main__.py`（共享准入包装：CQ 分支与 `receive_outer` 之前 pop `request_id` 并落回执）、`runner.py`（仅为回执追加提供 `_append_evidence` 的最小访问，如需 helper 则加一个窄方法） | 可选 `request_id` 剥离 + `outer-input-receipts.jsonl` 回执（§5；唯一 Runner 侧改动，窄且向后兼容） |
| 新 `.claude/modeling-team-host-mcp.json`、runbook 新节 | 配置片段与手册示例 |
| `modeling_team/tests/` | `test_host_ops.py`、`test_host_ops_mcp.py`、`test_outer_input_receipts.py`（共享计划用例） |

顺序：操作层读工具 → 回执机制+变更工具 → MCP 面+配置/手册 → I 层验收 → 真实 L0。
每步跑 Team 回归并按共享计划做基线失败清单对比；无 S2 内容混入。

## 附录 A：实现相关锚点（2026-09-18 基线）

- 准入：`__main__.py` `_KNOWN_OUTER_ACTIONS`(≈L161)、`_CQ_OUTER_ACTIONS`(≈L194)、
  `_handle_foreground_message`(≈L261)、`_handle_cq_outer_message`(≈L230)、
  `_foreground_event_loop`(≈L323；emit=stdout print，拒绝不落盘——回执缺口的直接证据)。
- Runner：`receive_outer`(L3860)、`_recover_provider_outer`(L4107)、
  `handle_cq_outer_input`(L7935)、`_handle_cq_handoff_complete`(L7461)、
  `_handle_cq_acceptance_complete`(L7741)、`_handle_cq_interview`(L6761)、
  `_handle_cq_review`(L6818)、`handle_cq_freeze`(L7284)、`_record_outer_question`(L8839)、
  `_release_owner_answer`(L8892)、`observe_foreground_output`(L8705)、
  `_append_evidence`(L11001)、`_state`(L9978)。
- 合同：`competency_questions.py` `CQ_ACCEPTANCE_COMPLETE_FIELDS`(L154)、
  `CQ_ACCEPTANCE_VERDICTS`(L170)、`validate_review_decision`(L447)、
  `batch_report_acceptance_verdict`；`interventions.py` `IssueResolution`(L241)、
  `RecoverableOuterInputError.as_dict`(L100)。
- 传输/存活：`outer_input.py::OuterInputFifo`(max_line_bytes 65536)；
  `checkpoint_recovery.py::chain_writer_lock_report`(L365)；run 根
  `workspaces/modeling-runs/<run_id>`(runner.py L884)。
- 事件源：`_append_evidence` 调用点全集（60 类，含 outer-question/outer-user/
  owner-answer-failure、issue-report/control/resolution/abort/pause、provider-wait、
  cq-interview/review-request/review-decision/freeze/handoff-complete/
  acceptance-complete/wait-windows/terminal-report/cleanup/exposure/public-projection、
  runtime-failure、terminal-classification、settled、semantic-start、staged-decisions、
  multi-slice-*、coordinator*、deliveries、start-ledger 等）+ `checkpoints.jsonl`
  （S2，不读本类）；宿主 journal：`control/host-requests.jsonl`、
  `control/host-supervisor.json`（新）。
