# R2.3-009 Modeling Team 校验降级与 Agent 自修复 — 共享测试计划

- 日期：2026-08-19
- 状态：Plan（planner 产出，待 review）
- 需求：`docs/requirements/requirements-v2.3.md` R2.3-009
- 设计：`docs/delivery/design/2026-08-19-r2-3-009-gate-relaxation-design.md`
- 命令：`PYTHONPATH=backend:. backend/.venv/bin/python -m pytest modeling_team/tests -q`（仓库根执行）
- 已知环境项：`test_deepseek_codex_runtime.py` 7 例在 shell 带 `DEEPSEEK_API_KEY` 时失败，
  `env -u DEEPSEEK_API_KEY` 下 21/21 通过——与本需求无关，验证时统一以 `env -u` 运行。

## 轮次总览

| 轮 | 内容 | 执行者 |
|---|---|---|
| R1 | 静态守恒：kill-path 白名单 + C 类无 raise | developer 自测 / tester 复核 |
| R2 | C 类 record-only 行为（defect 9 一般化） | requirement_tester（独立） |
| R3 | B 类 observed-issue + typed conflict（defect 10/11 一般化） | requirement_tester |
| R4 | A 类 typed capability 反馈 + run 继续 | requirement_tester |
| R5 | 反馈可读性与路由（通道 1/2/3） | requirement_tester |
| R6 | 兜底分层 T1/T2/T3 + 参数 | requirement_tester |
| R7 | 账本与终态合同兼容 + 回归 | requirement_tester |
| R8 | 真实运行演练（需用户显式 start 授权） | 独立 Examiner |
| R9 | 收尾：全量绿 + 文档/状态同步 | requirement_tester |

## R1 静态守恒（meta-invariant）

1. **kill-path 白名单测试**：source 扫描 `modeling_team/runner.py`，断言
   `_latch_formal_candidate_failure(` 调用点行集合 ⊆ 白名单（由实现以声明式 registry
   定义：T3 fallback、I 类 internal-invariant、S 类 startup）。任何新增调用点使测试失败，
   强制开发者显式登记并说明类别。
2. **C 类无 raise**：断言 `protocol_retrieval_gate.py` `_validate_response_quality`
   代码中不存在 `raise`（AST 级或文本级扫描）。
3. **reason_code 前缀**：S 类站点带 `startup-config:`、I 类带 `internal-invariant:` 的
   smoke 断言（抽查代表性站点即可，不逐一枚举）。

## R2 C 类 record-only（defect 9 场景一般化）

前置：R1 通过。

1. 构造 terminal 页截断/低命中 retrieval observation，调用改造后的校验路径：
   - 断言无异常、无 handoff 阻断；
   - 断言 receipt/observation evidence 含 `warnings_observed` 记录（含原因码）。
2. 对照组：cursor 绑定/结构不变量破坏仍以 `ordinary_retrieval_incomplete` + detail
   返还 protocol Agent（既有行为不回退），run 不终止。
3. 回归：defect 9 既有回归测试保持通过。

## R3 B 类 observed-issue + conflict（defect 10/11 场景一般化）

1. 非 JSON / 非 candidate-shaped 初始投递：observed-issue evidence 记录（含原始文本）、
   冲突/nudge 不误杀；后续真候选注册成功（defect 10 回归保持）。
2. revision 非严格更新 / digest 复用：该投递仍被 revision 门拒绝（检查保留），但处置为
   observed-issue + typed conflict 给 modeling；progress 不进入终态；后续合格 revision 被接受。
3. 一次性回复槽被占用后的 standalone revision（defect 11 回归）+ 新增：reopen 拒绝
   （runner.py:4117 旧 latch 位）改为 typed 反馈，run 继续。
4. envelope-invalid（runner.py:4072 旧 latch 位）：typed conflict 投递给 modeling，
   evidence 先持久化后判定（断言 evidence 中存在原始投递文本，再存在判定事件）。

## R4 A 类 typed 反馈 + run 继续

1. **同步站点**（通道 1）：Agent 发起的 dry-run/apply 合同违约（`acceptance.py` `_error`
   路径）→ capability 载荷 `{ok: False, error: {code, detail, remediation}}` 随 tool call
   响应返还调用者；`validation-feedback` evidence 记录；run 继续。
2. **异步站点**（通道 2，review 修订）：registration rejected 且归因候选 plan 缺陷
   （`ProtocolRetrievalGateError`）→ Runtime typed 反馈投递给 **modeling**；progress 自
   `complete` 经 post-complete 重开迁移回 `awaiting_revision`；modeling 严格更新 revision
   重新注册成功——**且注册侧联动生效**（重开时 `_accepted_candidate_identity` 已作废，
   再注册不触发 `acceptance.py:1777` mutation 守卫，非 R2.3-003 requirement 同样走通）。
   replacement revision/digest 违约 → 反馈投递给 **protocol**。未经重开迁移的 identity
   mutation 仍致命（I 类，断言一处）。
3. **I 类守恒**（review 修订）：turn-binding missing（4197/4337）、dispatch receipt
   turn_id/mode 结构失败、`candidate_platform_gate` 文件系统/状态守卫、accepted identity
   mutation——均保持致命 fail-fast（断言 terminal_failure 分类，不产生 Agent 反馈循环）。
   **反例**：4331（candidate-progress-timeout）/4334（redrive-exhausted）不在 I 类白名单
   ——它们归 T1/T2，仅 T3 latch（与 R6.1 一致，防守恒测试与 T1 语义互斥）。
4. 重试不设代码上限：A 类连败 2 次后第 3 次仍收到同构反馈，而非 kill。
5. 反例守恒：S 类启动失败仍致命（1 例）。

## R5 反馈可读性与路由

1. 通道 1：MCP structuredContent 与 text content 双路径均含 `code`；-32001 审计行记录
   真实 code+detail（capability-calls.jsonl）。
2. 通道 2 路由：候选工件缺陷 → modeling 收到 conflict；receipt/handoff 行为缺陷 →
   protocol 收到 conflict（两个注入场景分别断言接收方）。
3. 通道 3：同一 (class, code, agent) 反馈重复 `feedback_escalation_repeat` 次后 Runner
   自动开 issue；issue 开启时 `progress.pause()` / 解决时 `resume()` 接线生效
   （断言详见 R6.2）。

## R6 兜底分层

1. T1：无进展达到 `candidate_progress_timeout_seconds` → nudge 事件投递、run 未终止；
   redrive 至 `candidate_redrive_limit`。
2. T2：T1 用尽 → 自动 issue 开启；**断言 `progress.pause()` 已接线**（issue 开启时
   elapsed 冻结、解决时 `resume()` 起新区间；issue pending 期间及解决后 T1 均不因
   pending 时段的墙钟时间触发——review 修订，防 T1↔T2 乒乓）。
3. T3：**run 级 active clock**（自 `runner.start()` 成功起算、覆盖无 formal acceptance
   的 run、按 issue ledger 开/闭时间戳排除 pending 时段）达到 `run_fallback_timeout_seconds`
   → latch collaboration/routing "run-fallback-timeout"；terminal_evidence 含
   {nudges_sent, issues_opened, last_responsible_agent, feedback_counts}。
4. 反馈投递不重置 T3 active clock（注入 2 次无效重试后断言 clock 不归零）。
5. profile 参数缺省值测试：三参数默认 3/3/5400s。

## R7 账本与终态合同兼容

1. Agent 自愈后终态报告（completed）走既有 settlement 路径，分类正确。
2. Agent 报告 blocked 的合法出口：settlement 记录 blocked、run 正常清理、无
   terminal_failure。
3. T3 终局账本事件与 terminal_evidence 完整；classification 集合与
   `start_ledger.py:18/420` 一致（`_RETRYABLE` 不变）。
4. 全量回归：`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m
   pytest modeling_team/tests -q` 通过数 ≥ 现状基线（938 passed / 1 skipped / 302 subtests，
   2026-08-19 plan review 实测）。

## R8 真实运行演练（独立验收；需用户显式授权 start 预算）

- 前置：R1–R7 全 PASS；用户授权后执行。
- 场景：注入类 defect 9/10/11 等价的自然触发条件（不修改产品代码，通过场景数据诱导：
  分页截断检索、barrier 期 prose、槽占用后重投），观察 Agent 自修闭环。
- 判定：run 以 Agent 终态报告或 T3 结束；全程无 validator kill；evidence 完整；
  Examiner 独立判定检索证据与模型质量（与产生证据的过程独立）。

## R9 收尾

1. 全量测试绿（命令同上）。
2. 文档同步：requirements-v2.3.md R2.3-009 状态、设计文档标注实现结果、delivery record。
3. 白名单守恒测试与分类说明入 `docs/reference/`（若实现产出声明式 registry）。
4. 遗留风险显式化（如 T1/T2/T3 参数需真实运行标定）。

## 完成门

- R1–R7 全 PASS + R8（若授权）完成判定；
- 守恒测试固化（防回潮）；
- 既有 defect 9/10/11 回归测试全部保持通过；
- 无测试文件/临时脚本遗留（清理规则）。
