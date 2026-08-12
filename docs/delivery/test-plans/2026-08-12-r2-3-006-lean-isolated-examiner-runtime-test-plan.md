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
