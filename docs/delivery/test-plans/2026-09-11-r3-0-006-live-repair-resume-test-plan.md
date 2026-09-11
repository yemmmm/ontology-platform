# R3.0-006 live repair/resume — 共享测试计划

- 日期：2026-09-11
- 状态：实现完成，独立功能复验 Round 2 PASS；未启动真实 semantic modeling
- 设计：`docs/delivery/designs/2026-09-11-r3-0-006-live-repair-resume-design.md`

## 1. 测试边界与证据

验证第一层 live recovery 的 Runner/Transport/Host 边界，不替代 R3.0-006 的真实语义、
授权、SQL 或 RDF 验收。测试使用隔离临时 run，必须保留失败前后 run root、thread id、
candidate/CQ/approval、intent/receipt、issue evidence 和 cleanup evidence，不增加 semantic
start。真实链路至少有一个实际 loopback HTTP 或 AF_UNIX socket 故障，经过生产 Runner 外层
输入/issue dispatch 边界；patch/mock Agent 成功不能计为 E2E PASS。

## 2. 机械合同用例

| ID | 场景 | 通过条件 |
| --- | --- | --- |
| R1 | 已知 no-write 接口返回 typed error → `report_issue` → Coordinator pause | 只进入 `WAITING_REPAIR`；进程、原 thread、候选/审批/回复槽保留；无 cleanup/start-ledger 事件 |
| R2 | 当前 FIFO/outer 输入缺字段、类型或 stale issue | 输出 `outer-input-rejected`（含稳定 code、retryable、绑定信息）；下一条有效消息仍可驱动同一 run；内部 invariant 仍按 fatal 边界处理 |
| R3 | Host Skill 将一句话映射为当前 issue 的简短 `repair_completed` | Runner 不做关键词识别；run/reporter/epoch 精确绑定；`external_service` 与两个既有 component 合法；known no-write 只需 Host 核实 component，resolution/digest/verification 字段按合同可选；旧五字段仍兼容 |
| R4 | unknown mutation + 简短 repair resolution | 拒绝 resolution/resume；staged gate 和 `_staged_gate_killed` 保持 closed；没有重复 apply、候选/CQ/审批重建或 cleanup |
| R5 | unknown intent 或写后无响应 | 一句话 resolution、通知、健康结果均不能解锁；issue 保持 waiting、staged gate 保持 closed、intent/receipt 证据保留。本增量无真实 unlock seam；未来 adjudication API 另列后续，不伪称已支持 |
| R6 | unsupported component、死进程或 frozen runtime | `repair_rebind_required` 为 typed 可观察拒绝；unsupported 在 persist 前不烧 resolution/epoch；跨进程恢复不宣称成功 |
| R7 | Coordinator 发 resume 时 reporter 仍 busy | 返回 `resume_waiting_reporter`，resolution 保留可用；reporter idle 后同一 thread 新 turn 恢复；不进入永久 `rebind_required` |
| R8 | 原操作恢复 | 使用原 request/plan/idempotency key 重试并取得确定结果；新 turn、同 run、原 candidate identity；没有第二 semantic start 或重复成功写 |
| R9 | 正常 CQ/用户/上游交接等待 | 只记录等待，不 terminal/blocked/cleanup；局部故障只暂停责任角色，其他已有交接不丢失 |
| R10 | 提示/Skill 合同 | Protocol 使用 `platform_repair`/`runtime_recovery` issue category；runbook 描述 typed rejection、同 start resume 与 unknown-readback 门；无 `platform-contract` 伪 category |

R2/R3 补充：新简短修复通知必须带正确 run_id，跨 run 同名 issue/reporter/epoch 仍拒绝且
不持久化；旧完整五字段或 guidance 省略 run_id 仍按原 FIFO 绑定兼容，显式错 run_id 必须拒绝。
R4/R5 补充：旧五字段传 reconciled/receipt_readback_reconciled/confirmed_no_write 字符串
也不能解除 unknown；Agent 报 no-write 但持久 intent unknown/mismatch 同样拒绝。显式 abort
保留既有受控收尾，不能被 unknown 守卫永远阻止。
R7 补充：覆盖 Broker 先设 resume_sent 后 Reporter busy 的实际顺序，保持 pending 和未派发
control，idle 后仅一次 Runtime dispatch；不能只修改测试 fixture 让 Ledger 一直处于
resolution_ready。

## 3. 真实临时 HTTP/socket 故障链路

用临时 loopback HTTP/AF_UNIX server（独立进程或真实 socket，不 patch client）控制响应序列：

1. 第一次原操作返回 503/连接断开且明确 `confirmed_no_write`；通过实际 Runner/Transport
   boundary 产生 issue，观测 outer issue，发 pause，保存同一 run/thread/candidate。
2. Host 侧修复 server 后返回 200；Skill 生成绑定当前 issue 的结构化 resolution 并经实际
   foreground/FIFO 输入；Coordinator 发送 resume，记录同 thread、new turn。
3. 原操作成功，核对原请求 digest/plan/candidate、issue 状态 `resolved`、后续 progress、
   无 cleanup/新 start/重复候选。保存 server access log、Runner evidence、前后状态 JSONL。
4. 重复一条 malformed outer input 后再送有效 resolution，证明只拒绝 malformed line；不得用
   mock `send_message` 或仅调用 ledger API 代替 Runner 边界。

另做真实 socket “写后无响应”序列：intent 标记 unknown，用户一句话必须仍被拒绝；核对
issue 等待、写门关闭及 intent/receipt 证据保持不变。本增量没有可验证的 gate reopen 入口；
若未来引入正式 readback/adjudication API，另开需求与测试轮次，不能在本轮伪造应用成功。

## 4. 回归与完成门

- 聚焦现有 `test_r23005_issue_escalation.py`、`test_r23009_self_reported_issue_resume.py`、
  `test_r23009_resolution_reaches_modeling.py`、`test_r30008b_*`/`test_r30009_*` staged
  recovery 用例；新增断言仅覆盖已证实的 malformed/invalid outer input 边界。内部 persistence
  或 Runtime delivery 故障继续可观察，不能由输入异常捕获一概吞掉；保留内部不变量回归。
- 执行 `uv run --project backend python -m pytest modeling_team -q` 及变更相关 Ruff；文档/提示
  校验用 `git diff --check`、JSON/skill contract validator。代码变更按 AGENTS 要求不报告完成
  直到测试通过；本轮不得以机械 PASS 代替真实建模 PASS。
- 独立测试者在开发冻结后追加 Round，复核真实 HTTP/socket 故障链、同 thread/new turn、
  unknown gate 和 cleanup/授权守恒；任何失败保留原始证据并按 platform-contract、
  collaboration/routing 或 runtime/infrastructure 归层。
- 本轮不依赖任何正在运行的 auth007 或其他 live run；未改 backend/frontend，故不要求产品服务
  restart。
- 完成门：R1–R10、真实故障链和回归全绿；run 状态/证据显示原环境保留且只恢复原步骤；
  unknown 写入没有被一句话旁路；若本计划的真实 socket/HTTP 故障链未执行，结论为
  PARTIAL/BLOCKED。本增量功能通过也不能声称 R3.0-006 语义 E2E PASS。

## 5. 执行记录

### 基线与计划评审

- 基线提交：`5fd399450b585670ef337f9bb892fb2ea9cd4f11`；原有 AGENTS.md、CLAUDE.md 和
  `.codex/agents/` 改动不纳入本次交付。
- 修改前聚焦基线：`uv run --project backend python -m pytest
  modeling_team/tests/test_r23005_issue_escalation.py
  modeling_team/tests/test_r30009_submission_recovery_feedback.py
  modeling_team/tests/test_runner_r23005_owner_answer.py -q` → 55 passed、21 subtests，4.92 秒。
  这些既有测试通过不证明新增恢复合同已满足。
- 独立计划评审 Round 1 REVISE：busy 控制提前消耗、unknown 字符串解锁、malformed/stale
  outer 致命边界、新通知 run 绑定四项 High；设计和本计划均记录修订。
- Round 2 变更面复审 PASS：无新增 Critical/High，无待裁决项；结论仅为计划可实施。
- 开发与独立测试记录继续追加在本节，不能覆盖基线或失败轮次。

### 主会话提示与 Skill 校验

- 已同步 Modeling、Protocol、Coordinator 的等待/修复提示及 modeling-dev-loop 操作说明；
  修复通知不触发关键词路由，也不新增 semantic start。
- `python3 /home/yangxiang/.codex/skills/.system/skill-creator/scripts/quick_validate.py
  skills/modeling-dev-loop` → `Skill is valid!`。
- Skill 与 runbook 的 22 个本地 Markdown 链接检查通过；`git diff --check` 通过。
  以上仅验证指令文件，不证明 Runtime 恢复或语义质量。

### 开发首轮与主会话冻结检查

- 开发者首轮报告 development-ready：聚焦回归 79 passed、25 subtests；staged 相关
  58 passed；Transport 16 passed、4 subtests；compileall、diff check 通过。
  Ruff 变更文件通过，runner 两个既有 F401 未纳入本次范围。完整套件与独立测试尚未执行。
- 主会话冻结检查 REVISE：R2 的非 formal `user` 缺 question ID、question/text 无副作用
  输入校验仍抛致命异常，未覆盖原始失败；另旧格式只按字段名齐全判断，空值可绕过新格式
  显式 run_id 要求。两项均为 accepted-high，已交开发者补回归与最窄修复。
- 用户明确授权 Claude Code 并行开发。其独占
  `modeling_team/tests/test_r30006_live_repair_socket.py`，负责编写实际本地 socket 故障链；
  原开发者继续维护运行代码和其他测试。Claude Code 的输出属于开发自测，不能作为独立验收。

### 开发补修轮

- 原开发者再次报告 development-ready：owner-answer 37 passed、28 subtests；
  issue/resolution/Transport 聚焦 79 passed、32 subtests；staged wiring 58 passed。
  compileall、diff check 和相关 Ruff 通过（仍保留两个原有 F401）。
- 已补回原始缺 question ID、未知 ID、错误 text、正式 question 错通道、问题歧义、FIFO
  拒绝后继续以及旧五字段 null/empty 旁路测试；内部绑定、持久化和 Runtime 异常继续保留。
  首轮两个 accepted-high 在开发自测中关闭，独立测试待核实。

### Claude Code socket 用例开发自测

- 新增 `modeling_team/tests/test_r30006_live_repair_socket.py`。首次失败来自 prepared-only
  fixture 未接 Broker；随后修正测试端的 gate 错误码、thread ID 和 pause 输出预期，移除
  CapturingAdapter 自带的无关 canned reply。未修改生产代码，也未降低写门断言。
- `uv run --project backend python -m pytest
  modeling_team/tests/test_r30006_live_repair_socket.py -q` → 2 passed，4.18 秒；开发者另报
  两次重复运行分别为 3.97、3.96 秒，均 2 passed。
- `uv run --project backend ruff check
  modeling_team/tests/test_r30006_live_repair_socket.py` → All checks passed。
- 实际使用本地 HTTP/AF_UNIX 服务、Runner capability、Broker 和共享 foreground handler；
  Runtime Adapter 与下游客户端为测试实现，未启动真实 App Server、canonical stdio child
  或产品服务，不属于真实语义 E2E。busy、ledger unknown 与显式 abort 由其他用例及独立
  测试覆盖，不能由本文件的两个成功推导。
- 两方均已停止写入。冻结清单：`workspaces/live-repair-20260911/development-freeze.json`，
  共 14 个运行代码/测试/提示/Skill 文件；基线提交仍为 `5fd399450b585670ef337f9bb892fb2ea9cd4f11`。

### 独立测试 Round 1（2026-09-11 17:05 +08:00）

- 测试者：独立需求测试 agent；开发者和并行测试贡献者均已停止写入。
- 代码版本/冻结状态：HEAD `5fd399450b585670ef337f9bb892fb2ea9cd4f11`，冻结清单
  `workspaces/live-repair-20260911/development-freeze.json` 的 14/14 文件 SHA256 全部吻合，
  manifest SHA256 为 `30429fe97110c23a8d9bb88c0d4b49378078f3dbbeb0031a86535753027d8e89`。
- 总体结论：**FAIL（本增量）**。真实 HTTP/AF_UNIX 故障链、R1–R9 机械合同和独立边界
  探针通过；R10 提示合同回归失败，且按要求执行的完整 Team suite 仍为红灯。已知的 7 个
  DeepSeek fallback 失败来自未变更文件读取当前 shell 的 `DEEPSEEK_API_KEY`，清除该变量后
  7/7 通过，单独归为环境前置问题，不把它们误报为本增量实现缺陷。

#### Round 1 执行范围与结果

- R1 **PASS**：真实 loopback HTTP 503（明确 no-write）→ issue report/pause → 同 socket 修复
  后 200 → 同 run、同 thread、新 turn 恢复；候选、plan、审批、slot、原请求、receipt、
  cleanup/start 计数均守恒。证据与 server 访问日志由
  `modeling_team/tests/test_r30006_live_repair_socket.py` 断言，独立命令结果为 `2 passed`。
- R2 **PASS**：旧非 formal 缺 question ID、question/text 错类型、问题歧义、formal question
  错通道、FIFO/foreground malformed 输入均为可重试 typed rejection；拒绝后有效输入仍能
  继续同一 run。聚焦回归覆盖
  `test_nonformal_outer_input_shape_errors_are_recoverable_and_retryable`、
  `test_formal_outer_question_wrong_channel_is_recoverable` 和 FIFO/foreground 用例；
  `test_display_envelope_integrity_rejects_unknown_and_all_binding_drift` 保持 run/project/origin
  漂移为 fatal，拒绝后不消费显示/答案状态。
- R3 **PASS**：short `repair_completed` 支持 `external_service` 且 digest/verification 可省略；
  两个既有 repair component 与完整旧五字段兼容；null/空 pseudo-legacy 不绕过显式 run_id；
  null、整数、数组和跨 run 字符串 run_id 均返回 `issue_run_mismatch`，不持久化 resolution。
- R4 **PASS**：AF_UNIX 写后无响应将 intent 置为 `unknown` 并关闭 staged gate；short repair、
  guidance 和旧五字段 `reconciled`/类似字符串均不能恢复，issue 保持 waiting、无第二次提交。
  独立探针还验证 durable gate 在 Agent 伪报 `confirmed_no_write` 时仍返回
  `unknown_mutation_requires_reconciliation`。
- R5 **PASS**：socket case 观测到入口层 `staged_gate_closed`，持久 gate 仍保留正确的
  `staged_unreconciled_batch` 原因；intent/receipt 和现场不变，没有伪造 unlock。
- R6 **PASS（受控 Runtime 范围）**：unsupported component 在 persist 前返回
  `repair_rebind_required` 且不烧 resolution/epoch；受控 dead reporter 与 reused-turn 探针
  保持 fatal 并进入 `rebind_required`。未启动真实 App Server/canonical stdio child，故不把
  受控进程对象测试扩写成跨进程恢复证据。
- R7 **PASS**：busy reporter 先保留 `resume_sent`、resolution 和未派发 control；idle 后只
  进行一次 Runtime dispatch，状态变为 `resolved`，重复 drain 不重复发送。
- 内部错误边界 **PASS**：聚焦回归中的
  `test_internal_persistence_error_remains_fatal_after_outer_validation` 与
  `test_coordinator_delivery_failure_still_raises` 保持 persistence/Coordinator Runtime 错误
  fatal；modeling relay 的受控失败只追加 evidence，符合设计中已持久化 resolution 的边界。
- R8 **PASS（第一层）**：真实 HTTP case 以原 request/plan/candidate/idempotency 证据复测，
  新 turn 与原 thread 绑定，只有一个 receipt 和一次实际写。没有重新生成 CQ、审批或候选。
- R9 **PASS（机械/提示回归）**：正常 CQ、owner-answer、upstream-candidate 和 handoff 等待
  仍由现有等待/交接合同处理；本轮没有真实 semantic start，未把文档或机械等待断言当作
  真实建模质量证据。
- R10 **FAIL**：`modeling_team/tests/test_r23005_complete_revision.py::test_c95_modeling_waits_for_bound_protocol_gates_and_coordinator_uses_exact_pause_shape`
  要求 Coordinator 提示保留 `retry that same pause once`，当前冻结
  `modeling_team/agent-packages/coordinator/instructions.md:82` 只有 `retry that same pause`。
  该句中的 `once` 是本增量 diff 删除的既有提示合同，聚焦回归为 `1 failed, 142 passed,
  28 subtests`；完整 suite 同一项也失败。

#### 缺陷记录

- **R1-001，严重度 Medium，归层 prompt-contract/平台流程回归**：
  - 复现：在冻结 checkout 执行完整命令
    `uv run --project backend python -m pytest modeling_team -q`，或聚焦命令包含
    `modeling_team/tests/test_r23005_complete_revision.py`；定位到 `test_c95...`。
  - 期望：Coordinator 在 pause 参数被拒绝时最多重试当前 pause 一次，再等待结构化修复通知，
    保留既有防循环合同。
  - 实际：当前提示删除 `once`，断言找不到该契约文本；完整 suite 结果为
    `8 failed, 1502 passed, 1 skipped, 328 subtests passed`。
  - 证据：`workspaces/live-repair-20260911/acceptance/round1-full-suite.log`、
    `workspaces/live-repair-20260911/acceptance/round1-command-results.log`，以及当前与基线的
    `git diff -- modeling_team/agent-packages/coordinator/instructions.md`。

- 完整 suite 另外 7 个失败均在未改的 `modeling_team/runtimes/codex.py` /
  `modeling_team/tests/test_deepseek_codex_runtime.py`，当前和基线 SHA256 相同；继承
  `DEEPSEEK_API_KEY` 时短路 fallback 文件校验，使用 `env -u DEEPSEEK_API_KEY` 的同一 7 个
  参数化用例为 `7 passed`。不建议需求开发者为本增量修复它们，但主会话不能把原始完整命令
  的红灯报告为 PASS。

#### 校验、证据与未执行范围

- `quick_validate.py skills/modeling-dev-loop` → `Skill is valid!`；22 个本地 Markdown link
  全部存在；`git diff --check` 通过。
- 本次变更相关 Ruff：除 `runner.py` 的两个已存在 F401（`CQ_ACCEPTANCE_MODE`、
  `coverage_gaps_from_projection`）外通过；对 baseline `runner.py` 的 stdin Ruff 复核同时
  重现这两个 F401 及其既有 `RuntimeDispatchReceipt` F821。未修改这些无关 lint。
- 独立探针与结果保留在
  `workspaces/live-repair-20260911/acceptance/r1_edge_probes.py` 及上述两份日志。
- 未执行且不属于本轮完成门：真实 semantic modeling start、真实 App Server/LLM、canonical
  stdio child、平台服务启动/重启、真实 PostgreSQL/RDF/SQL/授权、auth007 或其他 live run、
  R3.0-006 L1/L2/L3 语义验收；backend/frontend 未改，未做 restart/health。此次 bounded
  functional PASS 不能解释为真实语义 E2E PASS。

建议主会话让需求开发 agent 恢复 Coordinator 提示中的 `once` 后再复测；先优先重跑 R10、
聚焦回归和完整 Team suite，再保留本轮真实故障与 unknown gate 证据。下一轮必须继续使用本
测试方案并追加 Round 2，不能覆盖本记录。

### 主会话 Round 1 缺陷处置与二次冻结

- 接受 R1-001 Medium：仅恢复 Coordinator 提示中的 `retry that same pause once;`。
  该句是现有提示指导，并非平台代码中的不可恢复次数硬门，本次无需改变。
- 开发者报告 development-ready；隔离测试进程的 `DEEPSEEK_API_KEY` 后，
  `test_r23005_complete_revision.py` 为 8 passed，`git diff --check` 通过。
- 主会话核对 14 个冻结文件，仅上述提示措辞改变，其余 13 个 SHA256 保持不变。
  已更新同一冻结清单；Round 2 在测试子进程移除该环境变量后执行完整 Team suite，
  不修改实际环境配置或 DeepSeek 实现、测试。

### 独立测试 Round 2（2026-09-11 17:19–17:21 +08:00）

- 测试者：独立需求测试 agent；开发已冻结，未修改产品代码、测试代码或运行配置。
- 代码版本/冻结状态：HEAD `5fd399450b585670ef337f9bb892fb2ea9cd4f11`；冻结 manifest
  `workspaces/live-repair-20260911/development-freeze.json` SHA256 为
  `63d4548a879513cb013b9da4e621f59080aeda8d2211a02e026edde05beedd8f`，14/14 文件哈希匹配。
  工作区既有 AGENTS/CLAUDE、需求、实现、测试和 Skill 改动均保留，未覆盖其他 agent 变更。
- 独立 R10 复验命令：
  `env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest
  modeling_team/tests/test_r23005_complete_revision.py -q` → **8 passed in 0.12s**。
  目标断言 `test_c95_modeling_waits_for_bound_protocol_gates_and_coordinator_uses_exact_pause_shape`
  通过，确认 `retry that same pause once;` 已恢复；R1-001 **FIXED**。
- 完整 Team suite 命令由主会话实际执行一次，独立测试者引用该结果（测试子进程仅通过
  `env -u DEEPSEEK_API_KEY` 清除继承变量，未修改环境配置）：
  `env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest modeling_team -q`
  → **1510 passed, 1 skipped, 328 subtests passed**，退出码 0（约 95 秒）。
  完整 suite 包含本次变更相关的 R10、socket、issue/resume、staged recovery 和既有回归；原始
  输出保留在 `workspaces/live-repair-20260911/acceptance/round2-full-suite.log`。
- Round 2 结论：**PASS（bounded functional，仅第一层 live Runner/同 Agent thread 保存产物与
  恢复合同）**。Round 1 已独立取得的真实 HTTP/AF_UNIX 故障链、R1–R9、unknown/abort/busy/
  legacy 边界证据继续有效，本轮未重复启动真实 socket probe；本轮补足 R10 修复复验和完整
  suite 绿灯，无新增缺陷。
- 本轮未执行且仍明确不在范围：真实 semantic modeling start、真实 LLM/App Server/canonical
  stdio child、冷恢复/跨进程重绑、未知写入解锁、真实 PostgreSQL/RDF/SQL/授权验收、平台服务
  restart/health。Runtime Adapter 是受控测试实现；本轮 PASS 不能解释为真实 R3.0-006 语义或
  SQL E2E PASS，也不授予新的 semantic start。
- 缺陷状态：R1-001（Medium，Coordinator prompt contract）FIXED；无 STILL FAILING、
  REGRESSION 或 BLOCKED 项。建议主会话按 bounded functional PASS 收口，并保持真实语义验收
  与本机械/隔离证据分开。

### 主会话交付收口

- 接受 Round 2 的 bounded functional PASS：R1-001 已由独立测试者复验关闭，完整 suite
  由主会话执行并以进程 exit 0 核实。修正 Round 2 初稿中完整 suite 的执行者归属，
  不把主会话执行结果标为独立测试执行；Round 1 的独立失败和边界证据保持原样。
- 需求、设计、三个角色提示、宿主 Skill/runbook 与本测试记录已同步；不改变整个
  R3.0-006 的真实语义验收状态。没有启动或清理已有 live run，没有额外 semantic start。
- GitNexus staged `detect_changes` 为 LOW，17 个文件，65 个索引 touched symbols；索引
  未返回 affected flows，其动态调用覆盖有限，不能据此声称没有实际调用影响。暂存仅含
  本增量 17 个文件，既有 AGENTS.md、CLAUDE.md 和 `.codex/agents/` 保留且不纳入提交。
