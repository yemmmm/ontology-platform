# R2.3-006 精简隔离 Examiner Runtime 共享测试计划

- 状态：reviewed / 待实施（plan review Round2 PASS）
- Requirement：`docs/requirements/requirements-v2.3.md#r23-006-精简隔离-examiner-runtime`
- Design：`docs/delivery/designs/2026-08-12-r2-3-006-lean-isolated-examiner-runtime-design.md`
- Delivery record：`docs/delivery/records/2026-08-12-r2-3-006-lean-isolated-examiner-runtime-delivery-record.md`

## 1. 完成门

1. Source/Platform/Acceptance 每题 fresh instances 无主线程 turns；Acceptance 无 source/raw platform/main/前题历史。
2. 三类 role packet 字段、digest、token breakdown 可重算；host packet 不超过约定范围。
3. Platform 直接调用 strict proxy；无主 Agent人工转发，无 plaintext key。
4. 横向协作、缺输入、未知 tool/path/body/scope 在发送/backend 前 fail closed。
5. 每个 Examiner 正常最多 3 model turns；记录 TTFT、wall、proxy time 和 token breakdown。
6. R2.3-003 N=2 只读语义回归 PASS；N=1/3/5 顺序机械 PASS；R2.3-005/default 不变。
7. key exactly-once revoke/post-revoke denial，model/ledger 不变，零 process/socket/secret residue。
8. 独立 tester PASS；失败轮保留；需求/设计/记录/运行文档和提交同步。

## 2. 测试矩阵

### A. Packet 与上下文隔离

- A1 Source packet 只含当前 CQ、批准 source、binding 和 schema；注入 main-history marker 后 child 不可见。
- A2 Platform packet 只含 CQ、P/O/G/workspace/model digest、proxy/schema；不含 source/历史 verdict。
- A3 每题 fresh Acceptance packet 只含 ticket/standard、当前题两份 report+digest、ordinal 和 verdict schema；
  thread identity 不复用且 CQ2 输入不含 CQ1 report/verdict。
- A4 实际 first-call context inventory 证明 inherited conversation turns=0；system/safety、host packet、source/
  response token 分开计量。

### B. 路由与失败

- B1 Source→Platform、Platform→Source、Examiner→main/其他 Agent 的协作请求 pre-send 拒绝且留下 receipt。
- B2 删除 CQ、P/O/G、schema、digest 任一字段，Agent 不追问而返回准确 typed BLOCKED。
- B3 每个 wrapper exact schema 对 unknown/extra/missing/wrong-type tool/path/body/scope 均在 forwarder 前拒绝，
  `McpReadForwarder/session/backend_calls=0`；source missing 和 proxy failure 分类准确。
- B4 malformed report/digest 不进入 Acceptance 语义裁决。

### C. Direct proxy 与数据质量

- C1 Platform 从 capability 直接调用 proxy，一次 tool result 同时得到 structured response/request digest/
  response digest；Host 无人工数据消息。
- C2 使用 CQ1/CQ2 只读请求证明现有 entities/facts 足够生成 current/usable reports。
- C3 若 3-turn 内缺事实，保留具体 missing relation/evidence；不得用业务专属 API 修复本轮。

### D. Turns、性能与 positive-N

- D1 真实 App Server 探针先冻结 token-usage 事件名/字段/粒度；每个 Source/Platform/Acceptance 正常 path
  observable inference steps<=3；第4步前中断并 typed `BLOCKED/runtime-budget`。
- D2 每个 Examiner 目标<=60s、上限<=90s；proxy HTTP 单独计时；provider outage 单独分类。
- D3 N=1/3/5 ordinal/previous/next/final/settlement 无固定题名或数量逻辑。
- D4 `ExaminerRunMetrics/v1` 可重算 fresh thread、canonical first_turn_input、turn/start、token-usage increments、
  first/total/cached/task/evidence/output/reasoning、TTFT/terminal/proxy time；metrics 缺失时性能验收 FAIL/BLOCKED。

### E. Real acceptance、回归与清理

- E1 R2.3-003 final workspace N=2 每题 fresh Source/Platform/Acceptance 全部 PASS/current/usable，未预填历史答案。
- E2 StartLedger/ontology/batch/session/lease/attempt 前后不变，无 semantic start。
- E3 exactly-one read key create/revoke，post-revoke 401/403，child 无 plaintext，零 scoped residue。
- E4 R2.3-005/default 和非 Examiner Agent 上下文/工具行为无变化。
- E5 repository-required suites、compile/lint/diff、service restart/health（若改 runtime/backend）通过。

## 3. 计划轮次

- Round 1：实现审查 + focused deterministic packet/transport/proxy tests。
- Round 2：独立 real N=2 只读验收、性能/token 证据、清理和隔离回归。
- 后续轮次只处理已确认 requirement defect，继续追加本文，不创建新测试计划。

## 4. 当前未执行

本文件当前只冻结未来验收范围；没有启动 Agent、创建 key、调用平台或消耗建模授权。

## 5. 独立测试 Round 1（2026-08-12，未提交工作区）

结论：`FAIL`。本轮只验证实现边界和 deterministic/production seam；没有创建平台 key、调用
R2.3-003 retained workspace、启动 semantic start、修改 ontology/ledger，故不能把本轮结果当作
真实 N=2 验收。

### 已执行命令与结果

1. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest modeling_team.tests.test_r23006_lean_runtime -v`：13/13 PASS。
2. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest discover -s modeling_team/tests -p 'test_*.py'`：517 tests，517 PASS（其中 1 SKIP），退出码 0。使用仓库 backend venv；系统 Python 的同一命令因 pydantic/pydantic-settings 环境漂移出现 4 个导入错误，不作为本轮结论。
3. `PYTHONPATH=backend:. backend/.venv/bin/python -m compileall -q modeling_team` 与 `git diff --check`：PASS。
4. 真实 `codex-cli 0.147.0` fresh app-server 探针（临时 `CODEX_HOME`，无 semantic start）：确认 `thread/started`、`turn/started`、`thread/tokenUsage/updated`、`turn/completed` 事件和 thread/turn 绑定；只做空工具/协议探针，未执行 Examiner provider 语义 turn。

### 独立失败证据

- **P0，production input unreadable / real E2E BLOCKED**：`modeling_team/runtimes/codex.py:2032-2037`
  将 `default_tools_enabled=false`；`_require_lean_examiner_mcp_servers`（约 `:4045`）对 Source/
  Acceptance 只允许 `examiner_report.submit_examiner_report`。`launch_lean_examiner_child` 的
  `first_turn_input`（`:1412-1421`）只有 packet digest 和“Read `/agent/home/input.json`”文字；
  Source/Acceptance 没有 file-read/exec MCP。独立 app-server `mcpServerStatus/list` fresh probe
  返回空 inventory，且无 provider credential 可执行真实 model turn，因此无法证明 child 能读取
  `input.json` 或 Source bytes。当前只能 `BLOCKED`，不能以 injected executor/packet test 代替。

- **P0，typed-output-only 违反**：`_CodexChildResource._run_stdout_pump`（
  `modeling_team/runtimes/codex.py:775-810`）在 private child notification 之后无条件调用 generic
  `adapter._notification`。独立脚本构造 acceptance-examiner `_Agent` 并发送
  `item/agentMessage/delta` + `item/completed`，观察到 `adapter._messages` 从 `[]` 变为一个
  `RuntimeMessage(agent_id='acceptance-examiner-1', text='typed answer', kind='text')`，
  `receive_messages()` 也返回该消息。child 虽未注册在 `adapter.agents`，仍泄露到共享消息路由，
  不符合只通过 private report sink 返回 typed terminal payload 的合同。

- **P0，report-before-completed race / premature wall metric**：独立 fake resource 复现真实资源的
  `terminal_event=False` 初值；在 50ms 将合法 typed report 放入 `submitted_reports`，在 200ms 才置
  `terminal_event=True`。`run_lean_examiner_child`（`codex.py:1460-1489`）首轮记录 report 后，
  后续轮次因 `if report is None` 不再检查 `terminal_event`，最终 1s 后抛出
  `BLOCKED/runtime-infrastructure` 并 destroy child。`ExaminerRunMetrics.record_terminal_report`
  （`acceptance_runtime.py:494-500`）把 `terminal_wall_ms` 冻结在 report callback（约 51ms），
  早于 completed（约 200ms）；本轮实测 `premature_wall=true`。另测 report 已存在且同时
  `resource.blocked=ExaminerRuntimeBlocked('runtime-budget')` 时，blocked 优先、report 未消费、child
  destroyed，说明该单一顺序分支 fail-closed；但上述 callback-before-completed race 仍是发布阻断。

### 未执行/阻塞范围

- R2.3-003 retained workspace 的 CQ-001/CQ-002 N=2、exactly-once key create/revoke、post-revoke
  denial、model/ledger invariant、真实 provider semantic turns：`BLOCKED`。当前 diff 只暴露
  `LeanExaminerRuntime`/`CodexRuntimeAdapter.run_lean_examiner_child` seam，`rg` 未找到把它接入
  retained operation ticket/key lifecycle 的 callable operation boundary；不伪造 key 或报告。
- N=1/3/5 deterministic positive-N、strict schema、packet/digest、R2.3-005 regression 由 focused
  13/13 与完整 517/1-skip 回归覆盖；这些 PASS 不抵消上述生产可用性 FAIL。

修复建议：需求开发 agent 先修复三个 P0（child 最小只读输入能力、private pump 禁止 generic message
route、report/turn-completion 原子终态与 terminal-wall 计时），再进行 Round 2 复测和真实 N=2 授权验收。

## 6. 独立测试 Round 2（2026-08-12，未提交工作区）

结论：`FAIL`。Round 1 的三个 P0 均已复测为 PASS；本轮仍发现两个生产完成门阻断，故不能
提升为 requirement PASS，也没有创建 key、调用 retained workspace、启动 semantic start 或修改
ontology/ledger。

### 已执行命令与结果

1. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest modeling_team.tests.test_r23006_lean_runtime -v`：20/20 PASS。
2. 受影响回归（lean runtime、stdout pump、R2.3-005 runtime/settlement/repeatability、DeepSeek Codex、runtime failure）：52/52 PASS。
3. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest discover -s modeling_team/tests -p 'test_*.py'`：524 PASS，1 SKIP，退出码 0。
4. `PYTHONPATH=backend:. backend/.venv/bin/python -m compileall -q modeling_team` 与 `git diff --check`：PASS。
5. `backend/.venv/bin/ruff check modeling_team`：2 个既有、未触及本 diff 的 baseline findings（`modeling_team/__main__.py:524` 未使用 `schema_version`；`modeling_team/runner.py:26` 未使用 `FORMAL_MODEL_MANIFEST_RELATIVE`），新变更文件无新增 Ruff finding；按本需求记录为 baseline，不把它们改成产品修复。

### Round 1 P0 复测

- **P0-1 inline input/source：PASS**。`launch_lean_examiner_child` 现在在
  `modeling_team/runtimes/codex.py:1398-1434` 构造完整 `PACKET_JSON`、UTF-8
  `SOURCE_TEXT_JSON` 和 packet digest；Source/Acceptance instructions 与 Skill 不再要求
  `/agent/home/input.json`。focused test `test_codex_first_turn_contains_current_immutable_packet` 和
  `test_examiner_prompts_require_inline_packet_without_filesystem_read` PASS；独立 seam 观察到
  approved source text、base64 bytes、digest 均进入 first turn。
- **P0-2 generic message leak：PASS**。`_CodexChildResource._run_stdout_pump`（
  `codex.py:810-833`）过滤 lean child `item/agentMessage/*`/agentMessage completion，不调用
  generic message accumulator；独立模拟 delta+completion 后 `_messages=[]`，仍转发 MCP/turn
  completed，`terminal_event=True`。
- **P0-3 report-before-completed：PASS**。`run_lean_examiner_child`（`codex.py:1520-1546`）在
  report 首次校验后持续等待 terminal latch；独立 callback 约 50ms、completed 约 150ms 的 race
  返回 typed report、destroy child，`terminal_wall_ms` 约 150ms 而非 callback 时间。report 与
  runtime-budget 同时存在时 blocked 先赢、report 未消费且 child destroyed。

### 新发现的生产阻断

- **P0，Source evidence locator 未绑定当前 approved manifest**：
  `_validate_report_sink_payload`（`modeling_team/acceptance_runtime.py:806-821`）仅检查
  relative path，不接收或校验当前 Source packet 的 approved path/digest。独立传入
  `{"location":"not-approved.md#x"}` 后返回合法 report。`LeanExaminerRuntime.run`（约
  `:695-710`）仅按 report digest 构造 Acceptance packet，不携带 approved manifest 到 report
  sink validator；`run_lean_examiner_child` 返回 raw mapping。恶意/错误 Source child 可因此提交
  未批准 location，破坏 source fidelity。

- **P0，Platform locator 未绑定当前 `ScopedReadProxy` receipt**：
  `_validate_report_sink_payload`（`acceptance_runtime.py:822-852`）仅检查字段/hex/path/page
  形状，不比对当前 proxy `receipt_snapshot` 的 `(tool, request_digest, response_digest,
  artifact_path, scope)`。独立真实 proxy call 产生 `tool=check_platform_health`, request
  digest=`4ee7...`, response digest=`39f...`, artifact
  `acceptance/round/platform-read/<child>/0.json`；随后提交完全伪造 tool/ref/digests/path 的
  locator，validator 仍接受。`ScopedReadProxy` 保存 receipts（约 `:1279-1413`），但
  `LeanExaminerRuntime`/`run_lean_examiner_child` 没有 receipt 参数或绑定校验。

- **P0，retained N=2/key operation boundary 仍不可调用**：`rg` 全仓仅显示
  `LeanExaminerRuntime` 定义和 focused tests，`Runner`/`acceptance.py` 没有调用新 lean runtime；
  `run_lean_examiner_child` 只接受 caller 提供的 plaintext `read_key`/forwarder，未接入
  R2.3-003 retained ticket、exactly-once key create/revoke、post-revoke denial 和 before/after
  model/ledger inventory。独立验证因此保持 BLOCKED，不能伪造 N=2 或用 injected executors 代替
  real Runner-owned operation。

### Round 2 范围结论

Round 1 三个运行时缺陷已 FIXED；focused/affected/full deterministic 回归通过。但上述三个
生产边界（Source locator、Platform receipt binding、real retained operation/key lifecycle）仍未
满足 R2.3-006 E1-E3，需求保持 `FAIL`。需求开发 agent 必须补齐 binding 与真实 Runner operation
入口后，才能进入下一轮独立真实验收；本轮不创建 key、不执行 N=2。

## 7. 独立测试 Round 3（2026-08-12，未提交工作区）

结论：`FAIL`。本轮只复核 evidence-binding：Source approved path/dedup/Host ID、Platform 当前
receipt 一一绑定与分页、Acceptance ID union/PASS nonempty；不创建 read key、不调用 retained
R2.3-003 workspace、不启动 semantic start、不修改 ontology/ledger，也不把 deterministic seam
证据冒充真实 provider-backed N=2。

### 已执行命令与结果

1. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest modeling_team.tests.test_r23006_lean_runtime -v`：
   23/23 PASS，退出码 0。
2. 受影响回归（`test_examiner_stdout_pump`、`test_start44_examiner_contract`、`test_r23005_b_runtime`、
   `test_r23005_c_settlement`、`test_deepseek_codex_runtime`、`test_runtime_failure_boundary`、
   `test_r23005_t6_repeatability`、`test_r23006_lean_runtime`）：55/55 PASS，退出码 0。
3. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest discover -s modeling_team/tests -p 'test_*.py'`：
   527 PASS、1 SKIP，退出码 0。
4. changed-file Ruff：
   `backend/.venv/bin/ruff check modeling_team/acceptance_runtime.py modeling_team/runtimes/codex.py modeling_team/report_sink_mcp.py modeling_team/tests/test_r23006_lean_runtime.py`：PASS。
   全目录 `backend/.venv/bin/ruff check modeling_team` 仍仅报告既有 baseline：
   `modeling_team/__main__.py:524` 未使用 `schema_version`，`modeling_team/runner.py:26` 未使用
   `FORMAL_MODEL_MANIFEST_RELATIVE`；本轮未修改。
5. `PYTHONPATH=backend:. backend/.venv/bin/python -m compileall -q modeling_team` 与 `git diff --check`：PASS。

### Evidence-binding 复核

- **Source：PASS（当前 deterministic Host binding）**。`_source_report_evidence_ids`
  (`modeling_team/acceptance_runtime.py:871-900`) 将 report location 的 path 限定到当前
  packet `approved_sources`，拒绝 `not-approved.md#x`；同一 path 的两条 report locator 和
  packet manifest 重复 path 均在 Host binding 前拒绝。通过的 locator 产生 Host-owned
  `source:<sha256(canonical(path,sha256))>` ID（实测
  `source:76a577d6da84586501faf0d6df51eb6bb0c0610e6cf0f4dbf0d5823952f832a6`），不会使用
  child 自报 ID。
- **Platform：PARTIAL / P0 FAIL**。单 receipt 单页 locator 和同一分页链（page 0
  `has_more=true, output_cursor=cursor-1` -> page 1 `input_cursor=cursor-1,
  sequence_complete=true`）均 PASS；伪造 digest/path、重复 ref_id、缺 receipt 均
  `BLOCKED/acceptance-evidence`。但同一 Platform child 调用两个不同 tool 时，真实 receipts
  为 ordinal 0、1，而两个独立单页 locator 均应合法地使用
  `page={ordinal:0,input_cursor:null,output_cursor:null,has_more:false,sequence_complete:true}`。
  独立脚本调用 `_validate_platform_report_receipts` (`acceptance_runtime.py:918-983`) 得到
  `BLOCKED/acceptance-evidence`（`evidence={"page_ordinal":0}`）：实现把全部 receipts
  强制解释为单一分页链，并要求第二个 locator 为 page ordinal 1/前页 cursor，而不是按
  tool/read stream 分组。该真实形态拒绝是 P0 production blocker，不能以单链测试替代。
- **Acceptance：PASS**。`_validate_acceptance_evidence_ids`
  (`acceptance_runtime.py:986-995`) 接受 Source Host ID 与当前已绑定 Platform ref_id 的
  union；`PASS` 空 evidence、未知 ID、重复 ID 均 `BLOCKED/acceptance-evidence`。focused
  runtime 也复核了 acceptance packet 只携带当前题两类 ID union。

### 未执行与结论

- retained R2.3-003 CQ-001/CQ-002 N=2、真实 Runner-owned provider boundary、exactly-once
  operation key create/revoke、post-revoke denial、model/ledger before/after invariant 和
  service-backed receipts：本轮按授权冻结不执行；不创建 key、不伪造真实 N=2。
- Source/Acceptance binding 证据与 deterministic 回归通过，但 Platform 独立多工具单页分页
  P0 仍失败，故 R2.3-006 继续 `FAIL`。需求开发 agent 必须按 read-tool/分页 stream 分组修复
  receipt/page binding 后，再由独立 tester 复测；不能只扩大单链 fixtures。

## 8. 独立测试 Round 4（2026-08-12，稳定未提交工作区）

结论：`PASS`（本轮窄范围：Platform receipt/page binding 修复及 Round2 Source/Acceptance
binding 回归）。本轮不创建 read key、不调用 retained R2.3-003 workspace、不启动 semantic start、
不修改 ontology/ledger；因此该窄范围 PASS 不替代 R2.3-006 完成门中的真实 provider-backed N=2、
exactly-once key lifecycle 与 before/after invariant。

### 已执行命令与结果

1. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest modeling_team.tests.test_r23006_lean_runtime -v`：
   23/23 PASS，退出码 0。
2. 受影响回归（`test_examiner_stdout_pump`、`test_start44_examiner_contract`、`test_r23005_b_runtime`、
   `test_r23005_c_settlement`、`test_deepseek_codex_runtime`、`test_runtime_failure_boundary`、
   `test_r23005_t6_repeatability`、`test_r23006_lean_runtime`）：55/55 PASS，退出码 0。
3. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest discover -s modeling_team/tests -p 'test_*.py'`：
   527 PASS、1 SKIP，退出码 0。
4. changed-file Ruff：
   `backend/.venv/bin/ruff check modeling_team/acceptance_runtime.py modeling_team/runtimes/codex.py modeling_team/report_sink_mcp.py modeling_team/tests/test_r23006_lean_runtime.py`：PASS。
   全目录 `backend/.venv/bin/ruff check modeling_team` 仍仅报告既有 baseline：
   `modeling_team/__main__.py:524` 未使用 `schema_version`，`modeling_team/runner.py:26` 未使用
   `FORMAL_MODEL_MANIFEST_RELATIVE`；本轮未修改。
5. `PYTHONPATH=backend:. backend/.venv/bin/python -m compileall -q modeling_team` 与 `git diff --check`：PASS。

### Platform receipt/page adversarial matrix

对当前 `_validate_platform_report_receipts` (`modeling_team/acceptance_runtime.py:918-983`)
使用独立 deterministic `ProxyCallReceipt` 序列和 `SimpleNamespace(proxy.receipt_snapshot=...)`
执行 9/9 预期结果：

| 形态 | 结果 |
| --- | --- |
| 不同 tool，各自单页 `page.ordinal=0, input_cursor=null, output_cursor=null, has_more=false, sequence_complete=true` | PASS |
| 同 tool，两条独立单页（均 ordinal 0） | PASS |
| 同 tool 连续多页（ordinal 0 -> 1，cursor 连续） | PASS |
| 跨 tool 假续页（tool B 使用 tool A cursor/ordinal 1） | `BLOCKED/acceptance-evidence` |
| report locator 重排 | `BLOCKED/acceptance-evidence` |
| 缺页（refs 数少于当前 receipts） | `BLOCKED/acceptance-evidence` |
| cursor drift | `BLOCKED/acceptance-evidence` |
| request/response/artifact 坐标伪造 | `BLOCKED/acceptance-evidence` |
| receipt ordinal/order 损坏 | `BLOCKED/acceptance-evidence` |

窄修现在按当前 receipt 的 ordinal 和 locator 坐标逐项绑定；只有 `page.ordinal>0` 才要求同一
tool、前页 `has_more=true`、前页 `output_cursor` 与当前 `input_cursor` 相等；独立 stream 的
ordinal 0 不会被误判为前一条 stream 的续页。

### Round2 Source/Acceptance binding 回归

独立脚本复测 10/10 预期结果：Source approved path + Host-generated ID PASS；unapproved path、
重复 locator path、重复 approved manifest binding 均拒绝；Platform 当前 receipt PASS、伪造
receipt 拒绝；Acceptance 当前 Source/Platform ID union PASS，PASS 空 evidence、未知 ID、重复
ID 均 `BLOCKED/acceptance-evidence`。对应 Host 绑定仍在
`_source_report_evidence_ids` (`acceptance_runtime.py:871-900`) 与
`_validate_acceptance_evidence_ids` (`acceptance_runtime.py:986-995`)。

### 范围结论

本轮 Platform 窄修和 Round2 evidence-binding defect 均 PASS，无新 P0/P1。真实 Runner-owned
provider boundary、retained N=2、operation key exactly-once create/revoke、post-revoke denial、
model/ledger invariant 与 service-backed receipt 仍按授权冻结未执行；需单独授权/可调用 seam 后
再进行真实验收，不能把本轮 deterministic PASS 宣称为完整需求 PASS。

## 9. 独立测试 Round 5（2026-08-12，稳定未提交工作区）

结论：`FAIL`。本轮审查新增 `modeling_team/r23006_acceptance_operation.py` 与其 focused
tests，并复核当前 `ontology_ids` pre-forward scope gate。Round 4 的 Platform receipt 窄修及
Round 2 Source/Acceptance binding 仍保持 deterministic PASS；新增 retained-operation/key
生命周期边界存在 P0，不能宣称完整 R2.3-006 PASS。本轮没有创建 key、启动 provider、调用 retained
workspace/N=2、启动 semantic start、修改 ontology/ledger 或运行真实模型。

### 已执行命令与结果

1. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest
   modeling_team.tests.test_r23006_acceptance_operation
   modeling_team.tests.test_r23006_lean_runtime -v`：27/27 PASS，退出码 0。
2. 受影响回归（operation、lean runtime、stdout pump、start44、runtime failure、R2.3-005 B/C/T6、
   DeepSeek Codex）：59/59 PASS，退出码 0。
3. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest discover -s modeling_team/tests
   -p 'test_*.py'`：531 PASS、1 SKIP，退出码 0；仅出现既有 ResourceWarning/RuntimeWarning，未出现
   test failure。
4. `backend/.venv/bin/ruff check modeling_team/r23006_acceptance_operation.py
   modeling_team/tests/test_r23006_acceptance_operation.py modeling_team/tests/test_r23006_lean_runtime.py
   modeling_team/acceptance_runtime.py modeling_team/report_sink_mcp.py modeling_team/runtimes/codex.py`：PASS。
5. `backend/.venv/bin/python -m compileall -q`（本轮 operation/runtime 变更文件）：PASS；`git diff --check`：PASS。
6. `PYTHONPATH=backend:. backend/.venv/bin/python -m modeling_team.r23006_acceptance_operation --help`：CLI
   callable/usage PASS；`prepare_r23006_operation(ROOT)`：retained ticket、标准、manifest、source bytes
   digest、CQ-001/CQ-002 packet preparation PASS。仅 prepare/help 属 deterministic evidence；未调用默认
   production host。

### Production operation / binding 审查

- **生产 seam 已存在但真实 E2E BLOCKED**。`_ProductionOperationHost.start`
  (`modeling_team/r23006_acceptance_operation.py:471-518`) 延迟导入 backend、创建临时 admin key、
  构造 formal `run` 并以空 roster 调用 `CodexRuntimeAdapter.start_roster(run, [])`；adapter 的
  formal 分支会启动 `DeepSeekProviderProxy`。`create_read_key`/`run_examiner`（`:555-589`）随后
  走 `PlatformApiReadKeyLifecycle`、exact-schema `McpReadForwarder` 和 `LeanExaminerRuntime`。
  该静态调用链满足“Runner-owned provider path”形态，但按本轮授权不得创建 admin/read key 或启动
  provider，且没有 real provider/key authorization，因此不能把 fake-host 27/27 当作真实 N=2。
  另外，仓库 `rg` 只找到该 operation 模块自身及其 tests，没有现有 `Runner`/CLI dispatcher 调用它；
  当前可执行边界是显式 `python -m modeling_team.r23006_acceptance_operation`，不是既有 Team
  Runner 的默认分发路径。若完成门要求接入既有 Runner，这仍是待补的 production integration gap；
  本轮未擅自扩大范围或伪造该接线。

- **P0，retained ticket request/snapshot binding 漏洞**：`prepare_r23006_operation` 只验证 ticket
  自身 digest、continuation、`scope`/limits、standard/manifest digest；platform packet 在
  `:217-220` 无条件注入当前 20 项 `PLATFORM_PROXY_READ_TOOLS`，完全不校验 retained ticket 的
  `request_allowlist`。冻结 ticket 实际只有 6 项（且含当前 inventory 不再提供的
  `get_entity_statement_context`），静态差集为 runtime 额外 15 项、ticket 缺失 1 项。它也不读取
  `before_inventory` 或 ticket `model_state`；生产 snapshot（`:520-553`）只做当前 API digest 和
  ledger **before** hash/count 检查，未将 retained before-inventory digest/count/state 与实际快照
  绑定，也未检查 ticket ledger `after_*` 字段。独立 monkeypatch（只改临时内存 Mapping 并重算其
  self-digest，不写仓库）把 `request_allowlist=[]`、`before_inventory` 改为任意路径/digest、或
  `model_state` 计数改为 999；三种输入均 `prepare_r23006_operation(ROOT)` **ACCEPTED**，证明
  retained self-digest 不是足够的 identity/scope binding。实现应拒绝 drift/不一致或使用外部冻结
  digest，并只向 child/forwarder 暴露 ticket-approved exact inventory。

- **P0，create side-effect 后异常未撤钥**：`R23006AcceptanceOperation.run` 在
  `:352-360` 仅于 `host.create_read_key()` 正常返回后设置 `key_created=True`，finally
  `:364-367` 才按该标志 revoke。临时 `PartialCreate` host 先递增外部 create side-effect 再抛异常，
  精确输出为 `R23006OperationError retained acceptance operation failed` 与
  `{'create_side_effects': 1, 'revoke_calls': 0, 'stopped': True}`。真实
  `PlatformApiReadKeyLifecycle.create` 同样在 API 已返回 `201 {id}` 但缺 plaintext 时抛
  `Platform read key creation receipt is incomplete`，记录为空且没有 revoke 请求；该边界可留下
  已创建的 Project key，违反 exactly-once/finally cleanup。

- **P0，revoke 成功后 readback/denial 失败会再次 POST revoke**：
  `PlatformApiReadKeyLifecycle.revoke` (`modeling_team/acceptance.py:6131-6190`) 只有完整
  readback+old-key denial 后才把 record 标为 revoked；`finally` 清理 forwarder，但 active record
  保留。随后 production `stop` 的 `revoke_all` (`:6195-6205`, operation `:609-620`) 会再次调用
  revoke。临时 API：首次 revoke POST 返回 `200 revoked_at`、status readback 返回 500；随后
  `revoke_all()`，观察到两个 `/api/api-keys/k1:revoke` POST，record 仍 `active`。这违反 key
  revoke exactly-once，并在部分失败时无法给出安全 cleanup 结论。

- **P1，operation metrics gate 不是完整 fail-closed schema**：`_validate_result`
  (`r23006_acceptance_operation.py:295-329`) 只检查 6 条记录、role/thread/非空字段和 wall 上限，
  不重算 `first_turn_input.digest`，不校验 digest 格式/对应 packet，不校验 token increment 项的
  字段/类型/非负性或累计关系，也接受负 `ttft_ms`/`terminal_wall_ms`。独立把 nominal result
  的 digest 改成 `x`、increment 改成 `{'garbage': -1}`、TTFT/wall 改成 -1、`total_tokens` 改为
  字符串，五种均被 `_validate_result` **ACCEPTED**。正常 Lean runtime 会产生较强的内部 metrics，
  但 operation completion gate 对 host result 仍未 fail closed，不能单独作为“metrics complete”
  的证据。

- **P1，evidence writer 对 host-supplied secret 不做防泄漏拒绝**：nominal FakeHost evidence
  仅含 sanitized lifecycle fields，`r23006-retained-acceptance.json` mode 0600 且无
  `plaintext_key`/`Authorization`，该路径 PASS。但临时 host 返回同样合法 lifecycle counts
  并附 `plaintext_key=SECRET-KEY`、`Authorization=Bearer SECRET-KEY`，`_write_evidence`
  (`r23006_acceptance_operation.py:412-431`) 原样写入文件，输出检测为
  `{'contains_plaintext': True, 'contains_plaintext_field': True, 'contains_auth': True}`。
  当前 `_ProductionOperationHost.key_evidence` 静态投影不含这些字段，因此这是默认 host 的
  deterministic hardening gap（P1），不是本轮已执行的真实 secret leak。

### Cleanup / invariance / ordering evidence

- FakeHost provider-failure 和 snapshot-drift tests 均 PASS：正常失败路径执行一次 revoke、调用
  `stop()`，snapshot drift 被拒绝；nominal evidence 写入后目录 0700、文件 0600。
- `_validate_result` 的 nominal ordered `PASS,current=true,usable=true`、6 条 metrics 的
  `source,platform,acceptance`×2 顺序和重复 thread 拒绝均通过 focused tests；上述 P1 说明只做
  presence gate 仍不足以证明 real metrics digest/cumulative usage。
- 当前 `ScopedReadProxy.handle` 在 forwarder/backend 前对 `ontology_ids != [approved ontology]`
  返回 `read-scope-denied`, `backend_calls=0`；exact-schema unknown/missing/wrong-type matrix
  由 27/27 focused tests 复核 PASS。独立三输入 repro 对 `query_semantic_context` 得到：
  `ontology_ids=['o']` 正常 forward（backend_calls=1），`['other']` 和 `['o','other']` 均
  `{'error':'read-scope-denied','backend_calls':0}`，forward callback 总调用 1 次。此 gate PASS
  不修复 operation 未绑定 ticket allowlist 的 P0。

### 未执行、真实与结论

- retained R2.3-003 CQ-001/CQ-002 real N=2、new operation authorization/key、provider-backed
  child turns、post-revoke HTTP 401/403、数据库 key readback、model/ledger API before/after 和
  zero process/socket residue：`BLOCKED` by explicit Round5 freeze/no-key/no-provider authorization。
  不使用 old verdict 或 fake-host output 代替 real evidence。
- deterministic focused/affected/full suites、schema/packet/receipt/metrics presence、CLI
  callable path 和 static provider wiring PASS；P0 ticket binding 与 exactly-once lifecycle gaps
  make overall Round5 `FAIL`. 需求开发 agent 必须先修复 P0 并提供稳定 handoff，再安排下一轮独立
  复测；不得以本轮 deterministic PASS 或 operation `--help` 宣称 R2.3-006 complete。

## 10. 独立测试 Round 6（2026-08-12，稳定未提交工作区）

结论：`PASS`（Round 5 已确认的 operation deterministic P0/P1 修复均通过复测）；本轮可以进入
唯一一次、经明确授权的 retained R2.3-003 只读 operation。这里的 `PASS` 只覆盖当前修复和
确定性边界，不把尚未执行的 provider-backed CQ-001/CQ-002 N=2 当作真实需求完成；真实运行仍须
单独保留 provider、key、model/ledger before/after、post-revoke 和清理证据。

本轮不创建 key、不启动 provider、不调用 retained workspace/N=2、不启动 semantic start、不修改
ontology/ledger，也没有修改产品代码。仅追加本轮测试记录。

### 已执行命令与结果

1. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest
   modeling_team.tests.test_r23006_acceptance_operation
   modeling_team.tests.test_r23006_lean_runtime -v`：`30/30 PASS`，退出码 0。
2. 受影响回归：
   `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest
   modeling_team.tests.test_r23006_acceptance_operation
   modeling_team.tests.test_r23006_lean_runtime
   modeling_team.tests.test_examiner_stdout_pump
   modeling_team.tests.test_start44_examiner_contract
   modeling_team.tests.test_runtime_failure_boundary
   modeling_team.tests.test_r23005_b_runtime
   modeling_team.tests.test_r23005_c_settlement
   modeling_team.tests.test_r23005_t6_repeatability
   modeling_team.tests.test_deepseek_codex_runtime -v`：`62/62 PASS`，退出码 0。
3. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest discover -s modeling_team/tests
   -p 'test_*.py'`：`534 PASS`、`1 SKIP`，退出码 0；仅有既有 ResourceWarning/RuntimeWarning。
4. changed-file Ruff：
   `backend/.venv/bin/ruff check modeling_team/r23006_acceptance_operation.py
   modeling_team/tests/test_r23006_acceptance_operation.py modeling_team/tests/test_r23006_lean_runtime.py
   modeling_team/acceptance_runtime.py modeling_team/report_sink_mcp.py modeling_team/runtimes/codex.py`：PASS。
   全目录 Ruff 的既有 baseline 仍为 `modeling_team/__main__.py:524 F841` 和
   `modeling_team/runner.py:26 F401`，本轮未修改。
5. `backend/.venv/bin/python -m compileall -q modeling_team/r23006_acceptance_operation.py
   modeling_team/tests/test_r23006_acceptance_operation.py modeling_team/tests/test_r23006_lean_runtime.py
   modeling_team/acceptance_runtime.py modeling_team/report_sink_mcp.py modeling_team/runtimes/codex.py
   && echo COMPILEALL_PASS`：PASS；`git diff --check && echo DIFF_CHECK_PASS`：PASS。

### Round 5 finding 复测与独立对抗证据

- **partial create side-effect / exactly-once cleanup：PASS。** `R23006AcceptanceOperation.run`
  在 `r23006_acceptance_operation.py:486-505` 于 create 尝试前设置 `key_create_attempted=True`；
  production host `:806-851` 以 `revoke_attempted` 保证一次进入撤钥。独立 production-host 形态
  fake inventory 中发现唯一新 read key 时，观察到一次 `GET /api/api-keys` 加一次
  `POST /api/api-keys/<id>:revoke`，`revoke_count=1`；inventory 为空时 fail-closed 为
  `partial read key creation could not prove zero residue`，不静默成功且不发第二个 POST；多候选
  仍拒绝为 ambiguous residue。focused `test_partial_key_create_side_effect_still_invokes_revoke_cleanup`
  及异常路径均验证 stop 仍执行。
- **revoke POST 成功但 readback/denial 失败不重复 POST：PASS。** 独立 fake lifecycle 令第一次
  `revoke()` 在 POST 后抛 readback 错误，随后调用 production host `stop()`；观测到 lifecycle
  revoke 仅 1 次、`revoke_attempted=True`，stop 不再调用 revoke。generic lifecycle 的历史
  best-effort 行为未作为本轮生产 host 结论。
- **retained ticket/allowlist/model-state binding：PASS。** `prepare_r23006_operation`
  (`:114-225`) 要求 pinned `EXPECTED_TICKET_DIGEST` 与重算 digest 相等，冻结 ticket 的六项
  `request_allowlist`（含 `get_entity_statement_context`）逐项校验 exact P/O/G scope，并把
  `prepared.allowed_tools` 传给 `forwarder_for` (`:780-786`)；ticket/source manifest、before
  inventory path+digest、model-state scope/count 与 ledger sha/count 均在 prepare 时拒绝 drift。
  当前 prepared allowlist 数量为 6，未向 child/forwarder 传全局 20 项工具集。
- **strict metrics：PASS。** `_validate_result` (`:322-443`) 现在拒绝 bool turn/step、非 finite
  TTFT/terminal wall/proxy time、错误 digest、负/错误类型 token increments、缺少精确七项
  token 字段以及 cumulative totals 不一致；要求六条 `source/platform/acceptance × 2` 独立
  thread、ordered terminal reports。focused malformed-metrics、cumulative mismatch、NaN/bool
  对抗均 fail-closed，并在 cleanup 后才返回错误。
- **secret evidence：PASS。** `_reject_secret_evidence` (`:446-469`) 在 `_write_evidence`
  前拒绝 plaintext/authorization/read/admin key/secret/socket 字段和 secret-like 值；host 返回
  secret 的对抗结果为 `R23006OperationError`，`r23006-retained-acceptance.json` 不存在。
  nominal evidence 仍为 0700 目录、0600 文件，且无 secret。
- **snapshot/invariance：PASS。** production `snapshot` (`:646-764`) 去除 build-context 的
  `generated_at` 后计算 platform digest，同时绑定 live ontology/session/lease/attempt/key/batch
  六项 counts 与 retained ledger sha/count；独立 fake snapshot 改 generated_at 保持 digest，改
  live count 则以 `retained live inventory drifted: <field>` 拒绝。operation 仅在 before/after
  snapshot 相等时继续写 evidence。
- **ontology scope gate：PASS。** `ScopedReadProxy.handle` (`acceptance_runtime.py:1490-1515`)
  在 `exact_schemas is not None` 时对 `query_semantic_context`/`semantic_sparql_query` 的
  `ontology_ids != [approved ontology]` 返回 `read-scope-denied` 且 `backend_calls=0`；合法
  单 ontology 请求才 forward。R2.3-005 generic proxy（无 exact schema）行为保持原路径。

### 生产形态与范围结论

静态调用链仍为 `_ProductionOperationHost.start -> CodexRuntimeAdapter.start_roster(run, []) ->
PlatformApiReadKeyLifecycle -> exact McpReadForwarder -> LeanExaminerRuntime`，显式 CLI
`python -m modeling_team.r23006_acceptance_operation --output-root ...` 可解析并显示 usage。
本轮没有把 CLI/fake host 输出冒充真实语义证据：provider credential、new operation authorization
和真实 read key 均按授权冻结未使用。因此 retained N=2 的六条 real metrics、typed PASS、HTTP
401/403、数据库 key readback、model/ledger before/after、process/socket/secret residue 仍记为
`BLOCKED/未执行`，但没有新增 P0/P1，且当前修复态可交给主 agent 发起唯一真实 operation。

## 11. 独立测试 Round 7（2026-08-12，HEAD `d5410ad9` + 唯一未提交 snapshot diff）

结论：`PASS`（仅 `_ProductionOperationHost.snapshot` 的 `workspace-context` /
`modeling-context` 字段归属窄修）。本轮未创建 key、未启动 provider、未执行 N=2，也未修改产品代码；
因此该窄范围 PASS 不替代真实 retained operation 的 provider、key lifecycle、typed verdict 和
before/after invariant 证据。

### 稳定状态与 API/schema 复核

- `git rev-parse --show-toplevel` 为 `/home/yangxiang/projects/ontology-platform`；HEAD 为
  `d5410ad9ee5949a1469807ca2cef5e1eb41cae83`，`git diff --name-status` 仅列出
  `M modeling_team/r23006_acceptance_operation.py`。未提交 diff 只新增
  `GET /api/ontologies/{ontology_id}/modeling-context` snapshot 请求，并把 build-context
  的 `generated_at` 去重与 workspace-version 校验移到正确响应位置。
- API 代码与 backend contract tests 证明：`workspace-context` (`backend/app/api/ontologies.py:120-132`)
  的 `OntologyWorkspaceContextRead` 只有 `state/default_graph_set_id/members/issues` 等字段，
  不提供 `workspace_version`；`modeling-context` (`backend/app/api/modeling_batches.py:118-120`)
  由 `ModelingBatchService.get_modeling_context` (`backend/app/services/modeling_batches.py:539-614`)
  返回 `workspace.state` 与 `workspace.workspace_version`；`build-context`
  (`backend/app/api/build_sessions.py:46-59`) 是独立的 Project 查询并带分页参数。修复后的
  `snapshot` (`modeling_team/r23006_acceptance_operation.py:670-710`) 按该顺序读取六个路径，
  仅从 modeling-context 校验 workspace version/state，从 workspace-context 校验 state/graph set，
  并只剥离 build-context 的 `generated_at`。

### 已执行命令与结果

1. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest
   modeling_team.tests.test_r23006_acceptance_operation
   modeling_team.tests.test_r23006_lean_runtime -v`：`30/30 PASS`，退出码 0。
2. `PYTHONPATH=backend backend/.venv/bin/python -m pytest -q
   backend/tests/test_modeling_batches_api.py backend/tests/test_ontology_workspace.py
   backend/tests/test_build_session_api.py`：`21 passed`，退出码 0；仅 3 个已知 framework deprecation warnings。
3. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest modeling_team.tests.test_platform_scope -v`：
   `9/9 PASS`，退出码 0；其中 retained producer 使用 modeling-context version 的既有回归通过。
4. `backend/.venv/bin/ruff check modeling_team/r23006_acceptance_operation.py`：PASS。
5. `backend/.venv/bin/python -m compileall -q modeling_team/r23006_acceptance_operation.py &&
   git diff --check`：PASS。
6. 只读 fixture preparation：`prepare_r23006_operation(Path('.'))` 成功；ticket digest 为
   `6134dcf7…963190b0` 且与 pinned digest 相等，CQ 顺序为 `cq-001,cq-002`，allowlist 恰为 6 项
   （含 `get_entity_statement_context`），retained before counts 为 ontology=1、active
   session/lease/attempt/project-key=0、modeling batches=22，ledger record_count=66。

### Snapshot 对抗证据

- 独立 fake read-only production host 按真实 API 形状返回：workspace-context 不含 version，
  modeling-context 含 expected `state=ready` 与 retained `workspace_version`；两次 snapshot
  唯一改变 build-context `generated_at`，两次 `platform_digest` 均为
  `e2c5218856b0a3ec6a960e7dd2f8088f9fba75baf9bb42cb470dc1fd13f08bdf`，证明时间字段不造成漂移。
- 将 modeling-context 的 workspace version 改为 `wrong-version`，得到
  `R23006OperationError: retained modeling workspace version drifted`；将 live ontology count
  从 retained 1 改为 2，得到 `retained live inventory drifted: ontology_count_in_project`。
- 真实路径序列按 `project -> project/ontologies -> workspace-context -> modeling-context ->
  build-context?recent_session_limit=100&recent_session_cursor=0 -> modeling-batches?limit=100`
  发出，未调用任何写 API。fixture source/ticket/ledger 仅读，未改变 digest 或 record count。

### Service / real-vs-deterministic 范围

`ontology-platform.service` 当时为 active/running，`curl --fail http://127.0.0.1:8001/api/health`
返回 HTTP 200 `{"status":"ok"}`。未使用旧 key；未对受保护的 retained API 做 live admin GET（无本轮
operation authorization），所以 live API snapshot、真实 provider、new key create/revoke、post-revoke
401/403、N=2 typed metrics、model/ledger before-after 与 zero residue 仍为 `BLOCKED/未执行`。
API 路由形状由源码和 21 个 backend contract tests 覆盖，fixture preparation 与上述 snapshot
对抗共同证明当前窄修没有新的 P0/P1；可以交回主 agent 继续唯一真实 operation 前置流程。

## 12. 独立测试 Round 8（2026-08-12，唯一真实 operation failure-path audit，HEAD `a32409fe`）

结论：`PASS`（真实 operation 的失败路径、撤销清理、快照不变性与残留审计）。本轮只读审查
已结束的唯一 retained operation `workspaces/modeling-acceptance/r23006-retained-n2-live-2`，
未创建/使用 key、未启动 provider/child、未重跑或继续 N=2，也未修改产品代码。真实 semantic
acceptance 结论为 `BLOCKED/runtime-budget`，不是 semantic PASS/FAIL；该 operation 因预算阻断
没有生成 evidence file，故不能据此宣称 R2.3-006 完成。

### 真实 operation 与预算门证据

- 主代理执行的唯一 CLI 形态为
  `PYTHONPATH=backend:. backend/.venv/bin/python -m modeling_team.r23006_acceptance_operation
  --repository-root . --output-root workspaces/modeling-acceptance/r23006-retained-n2-live-2`，
  exit code `1`。真实 trace 在第一个 question 的 Platform child 通过
  `ExaminerRunMetrics.observe_notification` 接收前三个 positive cumulative `tokenUsage` event；
  第四个 inference step 到达前抛出 `ExaminerRuntimeBlocked: BLOCKED/runtime-budget`，child 被
  中止/销毁，operation finally 执行清理，未写 evidence file。
- `modeling_team/acceptance_runtime.py:415-487` 在第四个 positive step append 之前 fail-closed；
  R2.3-006 requirement/design D1 要求 `<=3` inference steps 且第 4 个必须返回
  `BLOCKED/runtime-budget`。`_CodexChildResource`/`CodexRuntimeAdapter` 保留 typed blocked
  cause 并销毁 child；没有发现预算 gate 绕过、错误 PASS 或继续调用 backend 的新缺陷。
- 该真实失败路径与 deterministic regression 一致，但没有把 deterministic fake seam 当作真实
  semantic evidence；无 typed terminal reports、六条完整 metrics 或 semantic verdict 属于本轮预期
  的 `BLOCKED/未执行`。

### exactly-once key lifecycle 与 post-revoke denial

只读数据库查询（`PYTHONPATH=backend:. backend/.venv/bin/python`、`Settings(_env_file=backend/.env)`、
仅 SELECT）显示 operation-owned read key `0c289d42-a052-447c-8f6f-136b13711bcd` 于
`11:58:43.994Z` 创建、`11:59:52.904Z` 撤销；bootstrap admin `f28544a3-...` 于
`11:58:43.840Z` 创建、`11:59:53.622Z` 撤销。对应 read-key audit 记录各一条
`api_key_created`/`api_key_revoked`，均 success。operation window journal 计数为：

| 检查 | 次数 | 证据 |
| --- | ---: | --- |
| create POST | 1 | `POST /api/api-keys` → 201 |
| revoke POST | 1 | `POST /api/api-keys/<read-key>:revoke` → 200 |
| post-revoke readback | 1 | `GET /api/api-keys/<read-key>` → 200（撤销记录） |
| old read-key protected request | 1 | project GET → 401 |
| post-revoke 403 | 0 | 未出现错误授权绕过 |

operation-owned read/admin key 的 active 数均为 `0`；数据库中另有 20 个历史 org-admin active
keys，均非本 operation 的 key，未将其误报为本轮残留。

### model / ledger / live inventory 不变性

- 只读 workspace/context 查询得到 `state=ready`、default graph set
  `277fd804-e485-5156-b7a7-ca6a1081f950`，retained workspace version
  `18e4912e2ab90f808d4b31ab01befc1c0bea3471426abfc1e915cf27869157c0`。
- live inventory 与 retained before snapshot 完全相等：`ontology_count_in_project=1`、
  `active_session_count=0`、`active_lease_count=0`、`active_attempt_count=0`、
  `active_project_key_count=0`、`modeling_batch_count=22`。
- `.r2-3-003-start-ledger.jsonl` SHA-256 为
  `af64172206eeef68c89dd1e5bdbde240d7e031e13914ae44ce69177d86080dcc`，记录数 `66`，与 retained
  ticket/before snapshot 一致；本轮没有写 API、模型、ledger 或 workspace。

### process/socket/output/secret residue 与服务健康

- `workspaces/modeling-acceptance/r23006-retained-n2-live-2` 权限为 `0700` 且为空；无 evidence
  file。operation window 内没有 `r23006-examiner-*`/`mt-ex-*` 临时目录、socket、匹配的存活
  process 或 output entry。当前 output secret scan 为空。
- 预先存在且早于 operation window 的 `/tmp/r23006-examiner-*`、`/tmp/r23006-codex-*` 测试/legacy
  artifacts 未归因于本 operation，未删除或改写。
- `systemctl --user ... status ontology-platform.service` 为 active/running；
  `curl --fail http://127.0.0.1:8001/api/health` 返回 200 `{"status":"ok"}`；
  `curl --fail http://127.0.0.1:5173/` 返回 frontend HTML。

### deterministic regressions 与未执行项

1. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest
   modeling_team.tests.test_r23006_acceptance_operation
   modeling_team.tests.test_r23006_lean_runtime -v`：`30/30 PASS`。
2. `backend/.venv/bin/ruff check modeling_team/r23006_acceptance_operation.py
   modeling_team/acceptance_runtime.py modeling_team/runtimes/codex.py
   modeling_team/tests/test_r23006_acceptance_operation.py
   modeling_team/tests/test_r23006_lean_runtime.py`：PASS。
3. `backend/.venv/bin/python -m compileall -q modeling_team/r23006_acceptance_operation.py
   modeling_team/acceptance_runtime.py modeling_team/runtimes/codex.py`：PASS。
4. `git diff --check`：PASS。

本轮没有重跑真实 N=2、没有新 operation authorization/key/provider/child，也没有继续失败 run；
因此真实六 metrics、typed PASS、semantic acceptance 和完整 evidence 仍是 `BLOCKED/未执行`。在
本轮审计范围内没有新增 P0/P1；failure layer 明确为 contract 要求的 runtime budget gate，
cleanup、exactly-once lifecycle、live/model/ledger invariants 与服务健康均通过。

## 13. 独立测试 Round 9（2026-08-12，Platform prompt-contract repair，HEAD `a32409fe`）

结论：`PASS`（本轮限定为 Platform Examiner prompt/skill contract 与 deterministic regression）。
当前稳定状态的 developer-owned implementation diff 仅包含对
`modeling_team/agent-packages/platform-examiner/instructions.md`、`skills/platform-examiner/SKILL.md`
及其 focused test 的窄修（delivery record/test-plan 由主代理维护），未改 runtime budget、proxy、report
schema、source/acceptance package 或 R2.3-005/default 路径；本轮未创建/使用 key、未启动
provider/child、未执行真实 N=2。因此真实 semantic acceptance、provider 的实际 parallel tool-call
wave、完整 metrics/typed PASS 仍为 `BLOCKED/未执行`。

### 修复合同审查与对抗结论

- 两个实际 child package asset 均要求：首个 inference 发出覆盖所有独立且可能需要 reads 的单一
  parallel assistant tool-call wave；wave 返回后下一 inference 立即提交唯一 typed report；禁止串行
  探索、按结果决定下一独立 read、重复/re-read、第二 retrieval wave、cursor follow、retry。
- 两个 asset 均要求首轮 cursor-bearing、paginated、truncated、incomplete、ambiguous 或 missing fact
  原样保留 completeness markers，并在同一 report 写明 unknown 与 explicit gap；不把 incomplete retrieval
  变成 definitive conclusion。原来的 `Follow every pagination cursor` 文案已移除。
- `git diff` 新增 prompt/skill 内容不含 CQ-001/CQ-002 答案、预置答案或工具计划，也没有改变 `<=3`
  inference gate；runtime 文件 `acceptance_runtime.py`、`runtimes/codex.py`、operation host 无 diff。
- source fidelity 未放宽：Platform asset 仍要求每个 successful proxy call 原样复制
  `request_digest`/`response_digest`/`artifact_path`，保持 ticket Project/Ontology/graph/model-state
  binding；Source asset 未改动。semantic report 顶层仍仅允许既定六字段，`coverage.complete` 与
  `gaps` 仍是显式字段。
- typed BLOCKED 边界无矛盾：现有 `_validate_report_sink_payload` 保持
  `answerability={answerable,insufficient-evidence,unavailable}`、显式 `coverage/gaps` 和 exact
  `evidence_refs`；平台 locator 的 unfinished cursor chain、missing terminal page、reorder/cross-tool
  continuation 仍由 `_validate_platform_report_receipts` fail-closed 为
  `BLOCKED/acceptance-evidence`，不会形成 PASS 证据。若首轮事实不完整，prompt 要求 report 保留 gap，
  不要求模型猜测或越过报告边界。
- 仍有明确残余风险但非本轮缺陷：parallel wave 是 provider/model 行为，focused test 只能证明实际
  注入的两份 asset 含 timing/parallel/gap contract，不能替代真实 App Server notification/turn trace；
  真实 operation 受本轮授权约束未执行，须在唯一后续 operation 中观察 actual first-wave call shape。

### 已执行命令与结果

1. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest
   modeling_team.tests.test_r23006_lean_runtime -v`：`24/24 PASS`，包含
   `test_platform_examiner_prompt_requires_parallel_wave_then_report`、receipt/page chain、scope、
   typed BLOCKED、budget 与 report timing tests。
2. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest
   modeling_team.tests.test_r23006_acceptance_operation
   modeling_team.tests.test_r23006_lean_runtime -v`：`31/31 PASS`。
3. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest
   modeling_team.tests.test_platform_scope modeling_team.tests.test_codex_isolation
   modeling_team.tests.test_examiner_stdout_pump modeling_team.tests.test_transport -v`：`86/86 PASS`。
4. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest discover -s modeling_team/tests
   -p 'test*.py'`：`535 tests OK`，`1 skipped`；输出中的 ResourceWarning/RuntimeWarning 为既有
   test subprocess/framework warnings，不构成 failure。
5. `backend/.venv/bin/ruff check modeling_team/agent-packages/platform-examiner/instructions.md
   skills/platform-examiner/SKILL.md modeling_team/tests/test_r23006_lean_runtime.py`：PASS。
6. `backend/.venv/bin/python -m compileall -q modeling_team/tests/test_r23006_lean_runtime.py`：PASS；
   `git diff --check`：PASS。
7. 只读 diff assertions：parallel wave、next-report、no cursor/retry/re-read、gap/unknown markers 均
   present；old serial cursor directive、CQ answer/tool-plan injection 均 absent。当前 `git status` 仅
   预期 delivery record/test-plan 与两份 Platform asset/focused test 修改；无 runtime product diff。

### 未执行与发布边界

本轮没有 real provider、new authorization/key、child、retained N=2 或 semantic start；故不能把本轮
`PASS` 当作 R2.3-006 real semantic acceptance。若主代理继续唯一真实 operation，应重点收集首次
Platform child 的 `turn/start`、一波内各 tool calls、下一 inference report、completeness/gap markers、
第 4 usage gate 与 cleanup/evidence；若实际 provider 仍串行第二波或以 incomplete page 产出 PASS，应
立即记录为新的 production finding，而不是用本轮 prompt marker PASS 覆盖。

## 14. 独立测试 Round 10（2026-08-12，真实 operation `live-3` failure-path audit，HEAD `6c1258a`）

结论：`FAIL`（发现一个 P1 failure-observability/performance release blocker；cleanup、授权生命周期、
model/ledger/live invariants 与残留审计 PASS）。真实 semantic acceptance 为
`BLOCKED/runtime-infrastructure`，最可信的底层 reason code 是 `runtime/child-timeout`，不是
`runtime-budget`；没有产生 ordered N=2 PASS 或 acceptance evidence。本轮只读审查已结束的唯一
`workspaces/modeling-acceptance/r23006-retained-n2-live-3`，未创建/使用 key、未启动 provider/child、
未重跑/继续 N=2、未修改产品代码或 delivery record。

### 真实 trace、parallel wave 与失败层

- 主代理提供的唯一真实 CLI 结果为 exit code `1`。第一题 Source 完成（约 28s）；随后 Platform
  child 实际发出大量并行 read wave，并出现 proxy/report tool calls；真实 trace 没有第四个 positive
  `tokenUsage` increment，因此没有触发 `BLOCKED/runtime-budget`。Acceptance 未启动，CQ-002 未执行。
- Platform child 在约 90s absolute watchdog deadline 停止。当前 `_CodexChildResource._start_watchdog`
  (`modeling_team/runtimes/codex.py:704-736`) 到 deadline 记录 sanitized `failure_category=runtime`,
  `reason_code=child-timeout` 并终止 process；`run_lean_examiner_child` (`:1519-1529`) 将它转换为
  `ExaminerRuntimeBlocked("runtime-infrastructure", role="platform", evidence={...})`。因此
  `runtime-infrastructure/child-timeout` 是最可信 failure layer/reason，而不是预算 gate 或 report
  schema rejection。
- Report/tool callback 的存在由真实 trace 可见，但 retained output 没有逐事件 ordering/terminal
  metrics；无法独立证明它是否早于 watchdog 或是否收到 `turn/completed`。实现当前先检查
  `resource.failure_evidence`，再读取 submitted report，并且只有 `report != None` 且
  `resource.terminal_event=True` 才返回 (`codex.py:1519-1554`)；因此 report 在 completed 前到达时不会
  被错误地当成 PASS，timeout 也不会被 report 覆盖，属于 fail-closed。
- `ExaminerRunMetrics.record_terminal_report` 仍只在真实 terminal event 后冻结 `terminal_wall_ms`
  (`acceptance_runtime.py:500-509`)；本轮没有证据表明 terminal wall 被 callback 提前冻结。

### P1 failure observability finding

- **P1：底层 sanitized reason 没有被 outer operation/CLI 结构化保留。** `run_lean_examiner_child`
  确实构造 `ExaminerRuntimeBlocked`，其 `as_dict()` 含 `failure_category=runtime` 与
  `reason_code=child-timeout`；但 `R23006AcceptanceOperation.run` (`r23006_acceptance_operation.py:518-521`)
  将非 `R23006OperationError` 包装成固定字符串 `retained acceptance operation failed`。真实 CLI
  exit 1/trace 未展示 reason_code，output 目录也没有 failure evidence file。独立 deterministic
  repro 的 outer error 为 `R23006OperationError("retained acceptance operation failed")`，cause
  仅显示 `BLOCKED/runtime-infrastructure`；只有直接访问 cause.as_dict() 才能看到 `child-timeout`。
- 这不是 P0：安全边界、typed fail-closed、撤钥、child cleanup 和 model/ledger invariants 均保持；但
  是 P1，因为运维/验收无法从一次失败直接区分 child timeout、child crash、output-close 或 provider
  failure，也无法保留可审计的 sanitized terminal failure reason。下一次真实 operation 前应由
  developer 仅修复 failure reason 的结构化传播（不放宽 retry/budget/semantic gate），并增加 CLI/失败
  evidence 的 deterministic assertion。

### 90s timeout 与单波 prompt 风险判断

- 本次 Platform 首轮单波行为满足 Round9 prompt contract：没有证据表明它串行追 cursor、重复读取或
  消费第四个 inference。故未发现新的 prompt-contract P0。
- 但是 child 在 90s watchdog hard ceiling 到达时仍未完成 terminal completion，触及“通常 <=60s、不得 >90s”
  的性能门，因此真实运行仍是 `BLOCKED`（不能把恰到 hard ceiling 的 timeout 当作性能 PASS）。现有 retained output 没有 first/total/cached/task/evidence token、
  per-call proxy time、tool-call count 或 turn event ordering；不能证明是“单波 prompt 造成首轮过大”，
  也不能排除 provider/tool forwarding latency。把 prompt marker PASS 当成性能 PASS 会是证据越界。
  该缺口与上面的 P1 observability 共同阻止 real acceptance closure。

### exactly-once cleanup、不变性与残留

- 只读 DB：read key `b0b95c61-7441-49cc-9011-233e384f6cf8` created
  `2026-08-12T13:59:49.803730Z`、revoked `14:01:48.062623Z`；bootstrap admin
  `94739d10-2a66-4dbf-bb59-4fcbde7396c6` created `13:59:49.599834Z`、revoked
  `14:01:49.025538Z`。operation-owned active project/admin keys 均为 `0`；read-key create/revoke
  audit 各一条且 outcome=success。
- service journal (local `21:59:49–22:01:48+08:00`) 计数：create POST `1`、revoke POST `1`、
  post-revoke readback `1`、旧 read key project GET `401` `1`、`403` `0`。没有第二次 revoke。
- live inventory 与 retained before 完全相等：ontology `1`、active session/lease/attempt/project key
  `0/0/0/0`、modeling batches `22`；workspace `ready`、default graph
  `277fd804-e485-5156-b7a7-ca6a1081f950`、version
  `18e4912e2ab90f808d4b31ab01befc1c0bea3471426abfc1e915cf27869157c0`；ledger SHA
  `af64172206eeef68c89dd1e5bdbde240d7e031e13914ae44ce69177d86080dcc`、66 records unchanged。
- `workspaces/modeling-acceptance/r23006-retained-n2-live-3` mode `0700`, empty, no evidence file。
  Current process/socket scan finds no matching live-3/r23006 Examiner child residue; the only matching
  `r23006-examiner-*` temp root predates this operation (18:30 local, before 21:59 operation window) and
  is not attributed to live-3. Service remained active/running; backend health 200 `{"status":"ok"}` and
  frontend returned HTML.

### Deterministic commands/results and unexecuted scope

1. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest
   modeling_team.tests.test_r23006_acceptance_operation
   modeling_team.tests.test_r23006_lean_runtime -v`：`31/31 PASS`。
2. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest
   modeling_team.tests.test_platform_scope modeling_team.tests.test_codex_isolation
   modeling_team.tests.test_examiner_stdout_pump modeling_team.tests.test_transport -q`：`86/86 PASS`；仅
   既有 ResourceWarning/RuntimeWarning 输出。
3. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest discover -s modeling_team/tests
   -p 'test*.py'`：`535 tests OK`, `1 skipped`。
4. `backend/.venv/bin/ruff check modeling_team/acceptance_runtime.py modeling_team/runtimes/codex.py
   modeling_team/r23006_acceptance_operation.py modeling_team/agent-packages/platform-examiner/instructions.md
   skills/platform-examiner/SKILL.md modeling_team/tests/test_r23006_lean_runtime.py`：PASS；compileall 与
   `git diff --check`：PASS。
5. Read-only deterministic failure repro confirmed direct cause preserves
   `ExaminerRuntimeBlocked.as_dict()={blocked_reason:runtime-infrastructure, role:platform,
   evidence:{failure_category:runtime,reason_code:child-timeout}}`, while outer operation message omits the
   evidence. No product files were changed by this repro.

本轮没有继续真实 operation、没有新 key/provider/child、没有 CQ-002/Acceptance execution、没有完整 six-role
metrics 或 ordered PASS evidence。建议先修复 P1 failure reason propagation/retained failure evidence，再由主
代理决定是否申请唯一下一次真实 operation；不要用本轮 cleanup PASS 或 deterministic PASS 宣称需求完成。

## 15. 独立测试 Round 11（2026-08-12，failure-observability typed BLOCKED 修复复核，HEAD `6c1258a`）

结论：`FAIL`。本轮确认 live-3 形态的 `runtime-infrastructure`/`runtime`/`child-timeout`
失败可以在完整 cleanup、撤钥和不变性证明后安全落盘；secret、cleanup、snapshot、撤钥/停止异常和
不完整 key lifecycle 均 fail-closed 且不生成误导 artifact，success evidence contract 未变。但发现一个
新的 P1 typed-BLOCKED observability regression：runtime-budget 以及若干 runtime-metrics/acceptance-input
的合法 typed evidence 字段被 operation 拒绝，导致没有 BLOCKED artifact，CLI 错误也丢失 role/reason/category/code。

### live-3-shaped BLOCKED、secret 和 lifecycle 对抗证据

- 只读 inline `FakeHost` repro 让 `run_examiner` 抛出：
  `ExaminerRuntimeBlocked("runtime-infrastructure", role="platform", evidence={"failure_category":"runtime", "reason_code":"child-timeout"})`。
  operation 外层错误精确为
  `Examiner blocked: role=platform reason=runtime-infrastructure category=runtime code=child-timeout`，
  不含 provider exception/plaintext。`r23006-retained-acceptance.json` mode 为 `0600`，输出目录只有
  最终文件、没有临时文件；top-level 和 `result` 均为 `status=BLOCKED`，`result.complete=False`，
  `role/platform`、`failure_category/runtime`、`reason_code/child-timeout` 全部存在；cleanup 六项均为
  `True`，invariance `equal=True`，create/revoke 均为 `1` 且 host stopped。写入发生在
  `r23006_acceptance_operation.py:568-617` 的 finally cleanup、snapshot、lifecycle gate 之后。
- secret-bearing typed evidence（`read_key: sk_read_secret`）被 `_reject_secret_evidence` 拒绝；外层
  错误不回显 secret，artifact 不存在，host 仍 create/revoke `1/1` 并停止。对应 focused test
  `test_secret_failure_evidence_is_rejected_and_not_written` 通过。
- cleanup children 不完整、snapshot drift、partial create/revoke exception、stop exception 和
  incomplete key lifecycle 均未产生 `r23006-retained-acceptance.json`；cleanup/lifecycle 错误优先于
  typed BLOCKED，避免写入可误解结果。`test_blocked_failure_does_not_write_artifact_when_cleanup_or_invariance_is_incomplete`、
  `test_partial_key_create_side_effect_still_invokes_revoke_cleanup`、`test_snapshot_drift_fails_after_cleanup`
  以及只读异常 host repro 均通过。
- `test_success_writes_non_secret_evidence_after_cleanup` 通过：success 仍为原有 operation schema/result，
  mode `0600`，cleanup/lifecycle/invariance gate 保持，未发现 secret 写入或成功契约回归。

### P1：其他合法 typed BLOCKED evidence 被错误拒绝

`r23006_acceptance_operation.py:473-504` 将 `_BLOCKED_EVIDENCE_FIELDS` 限定为只有
`failure_category`、`reason_code`。然而 runtime 真实产生的 typed evidence 还包括：

- `acceptance_runtime.py:476-478` 的 `runtime-budget`：`{"steps": 4}`；
- `acceptance_runtime.py:437-447`、`:468` 的 runtime-metrics：`thread_id`、`turn_id`、`field`；
- `acceptance_runtime.py:402`、`:284` 的 acceptance-input：`inherited_turns`、`host_packet_tokens`。

只读 inline repro（`runtime-budget`, role `platform`, evidence `{"steps":4}`）实际结果：

```text
outer_type=R23006OperationError
outer=typed Examiner blocked evidence fields are unsupported
artifact=False
lifecycle=1 1 True
```

同类 `runtime-metrics` (`field`/`thread_id`/`turn_id`) 和 `acceptance-input` (`inherited_turns`/
`host_packet_tokens`) 也复现相同结果；只有空 evidence 的 `acceptance-evidence` 和 category/code
形态能落盘。该行为违反 typed BLOCKED 的安全可观测性合同：失败已 cleanup，但既没有 BLOCKED retained
artifact，也没有包含 `role/reason/category/code` 的安全外层摘要，且误报为 unsupported schema。判定为
`P1`（不绕过安全边界、不产生 PASS 或 secret，但会隐藏真实 runtime-budget/metrics/input failure，阻止
运维和独立验收定位失败层）。应由 developer 以不放宽 secret rejection 的方式投影/允许这些非敏感 typed
字段，并为各 typed reason 增加 deterministic assertions；本轮不修改产品代码。

### 实际命令和结果

1. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest
   modeling_team.tests.test_r23006_acceptance_operation modeling_team.tests.test_r23006_lean_runtime -v`：
   `34/34 PASS`。
2. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest
   modeling_team.tests.test_platform_scope modeling_team.tests.test_codex_isolation
   modeling_team.tests.test_examiner_stdout_pump modeling_team.tests.test_transport -q`：`86/86 PASS`。
3. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest discover -s modeling_team/tests -p 'test*.py'`：
   `538 tests OK`, `1 skipped`。
4. `backend/.venv/bin/ruff check modeling_team/r23006_acceptance_operation.py
   modeling_team/acceptance_runtime.py modeling_team/runtimes/codex.py
   modeling_team/tests/test_r23006_acceptance_operation.py modeling_team/tests/test_r23006_lean_runtime.py`：
   `All checks passed`。
5. `backend/.venv/bin/python -m compileall -q modeling_team/r23006_acceptance_operation.py
   modeling_team/acceptance_runtime.py modeling_team/runtimes/codex.py
   modeling_team/tests/test_r23006_acceptance_operation.py modeling_team/tests/test_r23006_lean_runtime.py`：
   PASS。
6. `git diff --check`：PASS。

本轮未创建/使用 key，未启动 provider/child，未重跑真实 N=2；因此没有新增真实 semantic acceptance、
ordered PASS 或六-role metrics 证据。应先修复并复测上述 P1，再考虑唯一真实 operation。

## 16. 独立测试 Round 12（2026-08-12，typed BLOCKED evidence projection follow-up，HEAD `6c1258a`）

结论：`PASS`（仅 deterministic failure-observability scope；不等同于真实 N=2 semantic acceptance）。
本轮复测 Round11 P1 修复：所有当前生产 `ExaminerRuntimeBlocked` evidence key 均有严格、无 secret 的投影；
live-3-shaped child-timeout、runtime-budget、cleanup/lifecycle/invariance gate、secret rejection 和 success
contract 均通过。未创建/使用 key，未启动 provider/child，未执行真实 N=2。

### typed projection matrix 与生产覆盖

对 `modeling_team/acceptance_runtime.py`、`modeling_team/runtimes/codex.py` 中全部生产构造点做 AST/`rg`
交叉核对，得到 10 个 distinct evidence keys：

| key | 生产来源 | projection |
| --- | --- | --- |
| `field`, `thread_id`, `turn_id` | runtime metrics | safe code string |
| `steps`, `host_packet_tokens`, `inherited_turns` | budget/input gates | non-bool non-negative integer |
| `packet` | packet validator | only three exact labels, normalized to `source-examiner-packet`, `platform-examiner-packet`, `acceptance-examiner-packet` |
| `path` | source evidence locator | safe relative code/path; absolute and `..` rejected |
| `read_key`, `forwarder` | platform launch gate | bool only, renamed to `read_key_present`/`forwarder_callable` |

`failure_category`/`reason_code` are additionally accepted as safe code strings. Matrix 14/14 valid cases all wrote
BLOCKED evidence after gates; no provider text or credential bytes were retained.

### 必须路径和对抗结果

- `runtime-budget` with `evidence={"steps":4}` now writes mode `0600` atomic
  `r23006-retained-acceptance.json`: top-level/result `BLOCKED`, `complete=False`, role `platform`, blocked reason
  `runtime-budget`, category/code `None`/`unspecified` in outer message, projected `steps=4`; cleanup six fields
  true, invariance equal true, create/revoke exactly `1/1`, stopped true.
- live-3-shaped `failure_category=runtime, reason_code=child-timeout` still writes 0600 BLOCKED artifact and
  outer safe `role/reason/category/code` message; success evidence remains mode 0600 and unchanged schema.
- Unknown key, unknown packet label (`other-packet`), provider/free-text strings, secret-bearing values, absolute
  paths (`/etc/passwd`), parent traversal (`../secret`, `docs/../secret`), bool/negative/float/string integer,
  non-bool launch flags, wrong scalar type and packet list all reject before write; every case had no retained
  artifact. Secret rejection remains fail-closed and does not echo the supplied value.
- Cleanup children false, snapshot drift, revoke exception, stop exception and incomplete key lifecycle all remain
  no-artifact gates. Deterministic repros showed revoke/stop attempted once and cleanup completed/failed visibly;
  no misleading BLOCKED file was produced.

### 命令与计数

1. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest
   modeling_team.tests.test_r23006_acceptance_operation modeling_team.tests.test_r23006_lean_runtime -v`：`36/36 PASS`。
2. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest
   modeling_team.tests.test_platform_scope modeling_team.tests.test_codex_isolation
   modeling_team.tests.test_examiner_stdout_pump modeling_team.tests.test_transport -q`：`86/86 PASS`。
3. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest discover -s modeling_team/tests -p 'test*.py'`：
   `540 tests OK`, `1 skipped`。
4. `backend/.venv/bin/ruff check modeling_team/r23006_acceptance_operation.py
   modeling_team/acceptance_runtime.py modeling_team/runtimes/codex.py
   modeling_team/tests/test_r23006_acceptance_operation.py modeling_team/tests/test_r23006_lean_runtime.py`：
   `All checks passed`。
5. `backend/.venv/bin/python -m compileall -q modeling_team/r23006_acceptance_operation.py
   modeling_team/acceptance_runtime.py modeling_team/runtimes/codex.py
   modeling_team/tests/test_r23006_acceptance_operation.py modeling_team/tests/test_r23006_lean_runtime.py`：PASS。
6. `git diff --check`：PASS。

本轮 PASS 只证明 typed failure projection、artifact safety 和 deterministic lifecycle gates；真实 provider
并行 wave、完整六角色 metrics、ordered N=2 PASS、semantic acceptance 与 live retained operation 仍未执行，
不能据此关闭 R2.3-006 real acceptance。

## 17. 独立测试 Round 17（2026-08-12，live-4 diagnostics / partial-metrics binding，HEAD `5949a0f`）

结论：`FAIL`（`P1` persistence binding defect；以下失败证据来自本轮初始稳定 diff，随后 developer 已提交窄修，
该窄修不在本轮独立结论内，须由下一轮复测）。本轮未创建/使用 key，未启动 provider/child，未重跑或修改
live-4，也未执行真实 N=2。

### 通过项和 retained live-4 只读证据

- Codex failure-winner deterministic repro 通过：typed child failure 先于 report return，report callback 不被返回，
  `finally` destroy 必达；`report_received`、`terminal_event`、`proxy_receipt_count` 仅保留安全布尔/计数，
  不含 raw report/response/secret。
- Source/Platform/Acceptance 及第二个 CQ 的 failure prefix 矩阵通过：快照 role 前缀依次为 1/2/3/4/5/6，
  仅当前失败项为 BLOCKED；metric 深拷贝不可变；失败后成功 N=2 得到六条 metrics 且 `failure_metrics` 重置为空。
- 只读 live-4 artifact 未变（sha256 `1945db4d899e0df943f38b2343b547ab856cb4e318c208c7edbae6e57eef2676`），
  mode `0600`、output dir `0700`，typed `platform/runtime/child-timeout`，create/revoke `1/1`、post-revoke
  `401`、cleanup/invariance 全部通过，ledger 66 条/sha `af6417...` 不变，未推断其不存在的 `partial_metrics`。
  backend/frontend health 均 HTTP 200，未发现残留 process/socket/output/secret。

### P1 精确复现（初始稳定 diff）

对 `R23006AcceptanceOperation` 注入外层
`ExaminerRuntimeBlocked(role=platform, failure_category=runtime, reason_code=child-timeout)`，并提供合法
`ExaminerRunMetrics/v1` 快照，结果如下：

1. 末条失败 metric `blocked=None`（`metrics_complete=False`, `terminal_report=False`）仍写出 mode `0600`
   BLOCKED artifact；应 fail-closed，末条必须存在且与外层 sanitized BLOCKED 完全一致。
2. 末条 nested blocked 的 role=`source`、reason=`runtime-budget` 或 receipt count 与外层不一致仍写出 artifact；
   应拒绝 mismatch，避免把 platform failure 持久化为错误 role/reason。
3. 前序已完成 metric 携带 blocked 仍可写出 artifact；应要求所有前序 snapshot `blocked=None`。

因此该 artifact 能通过 cleanup/key/invariance gate，却可能误导失败阶段和当前故障归属，属于 `P1`；不产生
PASS 或 secret，但会污染 retained failure evidence。随后 developer 的窄修新增了上述三类 no-artifact assertions，
应由 Round 18 复测，不在本轮将其视为已验收。

### 命令与结果

1. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest modeling_team.tests.test_r23006_acceptance_operation modeling_team.tests.test_r23006_lean_runtime -q`：修复后 smoke `43/43 PASS`（仅记录修复后状态，非本轮 FAIL 的抵消证据）。
2. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest modeling_team.tests.test_platform_scope modeling_team.tests.test_codex_isolation modeling_team.tests.test_examiner_stdout_pump modeling_team.tests.test_transport -q`：`86/86 PASS`。
3. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest discover -s modeling_team/tests -p 'test*.py' -q`：`547 tests OK`, `1 skipped`。
4. changed-file Ruff、`compileall`、`git diff --check`：全部 PASS。

GitNexus 对未编辑的 private 方法名存在聚合命中噪声；本轮证据按精确的 `CodexRuntimeAdapter.run_lean_examiner_child`、
`_CodexChildResource` 和 operation validator/class seam 审查，不把聚合命中当作额外调用者或生产影响。剩余授权
`2/3`；本轮结论仅覆盖 deterministic diagnostics 与 live-4 failure audit，不代表 semantic N=2 acceptance。

## 18. 独立测试 Round 18（2026-08-12，partial-metrics binding 修复复测，HEAD `5949a0f`）

结论：`PASS`（deterministic diagnostics / retained live-4 failure audit scope）。未创建/使用 key，未启动
provider/child，未执行或修改真实 N=2/live-4；因此不代表 semantic N=2 PASS。

### §17 失败项复测

使用合法 `ExaminerRunMetrics/v1` rows 和外层
`platform/runtime/child-timeout` BLOCKED 对每个 case 独立运行 operation：

- 前序 non-empty row 的 `blocked != None`：拒绝，`partial Examiner metric blocked stage is invalid`，无 artifact。
- 末条 nested blocked role=`source`、reason=`runtime-budget`、receipt count 不同于 outer：均拒绝，
  `partial Examiner metric does not match outer block`，无 artifact。
- 末条 `blocked=None` 且 `metrics_complete=False`/`terminal_report=False`：同样拒绝，无 artifact。
- 合法 prefix 的末条 sanitized blocked 与 outer 完全相等：写出 2-row BLOCKED artifact，mode `0600`，
  final block equality 为 true。
- empty `partial_metrics=[]` 的 pre-stage typed block 仍允许写出 0600 BLOCKED artifact（rows=0），保持
  Source 尚未生成 metrics 时的合法失败路径。

### diagnostics、stage、immutability 和 lifecycle 回归

- Codex failure-winner/report race：failure 先赢，report 不返回，`destroy()` 必达；diagnostics 只含
  `report_received`、`terminal_event`、`proxy_receipt_count` 安全值，无 raw report/response/secret。
- Source/Platform/Acceptance × CQ ordinal 1/2 的 prefix 分别为 1/2/3/4/5/6；仅末条为 BLOCKED，前序
  metrics 完成且 `blocked=None`。返回的 `failure_metrics` 深拷贝不可变；同一 runtime 后续成功 N=2 返回
  六条 `source/platform/acceptance` metrics，并清空 `failure_metrics`。
- secret/unknown/wrong-type evidence、cleanup incomplete、snapshot drift、revoke/stop exception、
  incomplete key lifecycle 均继续 fail-closed 且不写 artifact；success artifact 契约不变。
- live-4 只读 artifact sha256 仍为
  `1945db4d899e0df943f38b2343b547ab856cb4e318c208c7edbae6e57eef2676`，0600/dir 0700，typed
  `platform/runtime/child-timeout`，create/revoke `1/1`、401 readback、cleanup/invariance 完整、ledger
  66 条不变，artifact 未新增 `partial_metrics`；backend/frontend health 仍 HTTP 200，未发现残留。

### 命令与结果

1. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest modeling_team.tests.test_r23006_acceptance_operation modeling_team.tests.test_r23006_lean_runtime -q`：`43/43 PASS`。
2. focused deterministic diagnostic/stage/lifecycle selection：`12/12 PASS`（7 lean/Codex + 5 operation）。
3. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest modeling_team.tests.test_platform_scope modeling_team.tests.test_codex_isolation modeling_team.tests.test_examiner_stdout_pump modeling_team.tests.test_transport -q`：`86/86 PASS`。
4. `PYTHONPATH=backend:. backend/.venv/bin/python -m unittest discover -s modeling_team/tests -p 'test*.py' -q`：`547 tests OK`, `1 skipped`。
5. changed-file Ruff、`compileall`、`git diff --check`：全部 PASS。

本轮无新 finding。该 deterministic scope 已允许在相同代码完成 clean commit 后消耗剩余授权 `2/3` 进行唯一
真实 operation；仍需把真实 semantic execution、ordered PASS、六 role metrics 和最终 retention 结果单独验收。
