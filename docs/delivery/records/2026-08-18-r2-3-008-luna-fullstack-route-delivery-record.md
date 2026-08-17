# R2.3-008 Luna 全栈路由/终态验证交付记录

- Requirement source: `docs/requirements/requirements-v2.3.md#r23-008-luna-全栈路由终态验证复用-r235-切片`
- Status: in-progress（Design-reviewed；implementation 未开始）
- Started: 2026-08-18 (planning started 2026-08-17)
- Last updated: 2026-08-18
- Design: `docs/delivery/designs/2026-08-18-r2-3-008-luna-fullstack-route-design.md`
- Shared test plan: `docs/delivery/test-plans/2026-08-18-r2-3-008-luna-fullstack-route-test-plan.md`
- Delivery baseline: `8a33c07 Draft R2.3-008 Luna full-stack route verification requirement`；design commit
  `8a53e27`；plan-review 修订 commit `a0f1a06`
- 复用基线：R2.3-007（provider routing + Luna Codex 订阅认证，含 A6 真实 Luna probe PASS）与 R2.3-005
  formal 建模/验收流程

## Confirmed contract

- Current behavior: R2.3-007 已交付具名 model profile 快速切换与 Luna 订阅认证，A6 probe 实证单 turn 订阅
  路由；但完整 formal 六角色 Luna 运行从未发生——R2.3-005 账本封闭、R2.3-003/002 账本不适用、非正式任务
  不能选择 model profile。
- Target behavior: 新建 formal run contract `R2.3-008`（mode=create，fresh Project/Ontology），逐字复用
  `r2-3-005` 六角色语义与业务切片源材料；默认 model profile `openai-luna-medium`；一次真实六角色运行实证
  全栈 Luna 路由与终态；专属 StartLedger 首批 3 start。
- In scope: `formal_runs.py` 新合同、`start_ledger.py` 新配置、`contracts.py` profile ID 封闭集注册、
  `acceptance.py` 延迟泵 task_id 集合扩展、三个新资产文件（profile/task/standard YAML+JSON）、focused
  deterministic tests、一次授权的真实 Luna formal run。
- Non-goals: 不做 Luna/DeepSeek 质量 A/B；不修改 R2.3-007 已交付代码；不实现运行内"路由级 acceptance 模式"
  （完成门在需求层，由独立评审做出）；不改 runner/acceptance 语义、六角色合同、StartLedger 治理规则；零
  `backend/`/`frontend/` 改动。
- Acceptance summary: 路由/终态级——六 package 真实 Luna 启动（逐角色 exact binding +
  `auth_mode=chatgpt-subscription`）、Team Transport、平台/MCP 工具调用、typed 终态报告、完整 cleanup 零
  残留、账本只记实际消耗 start；质量证据产生并保留但非完成门（测试计划 §4 R1–R8）。
- Refinement: 用户确认载体系新正式需求 R2.3-008、任务复用 R2.3-005 切片、验收仅路由/终态级、首批授权 3
  start（2026-08-17/18 AskUserQuestion）。

## Timeline

### 2026-08-17/18 — 载体决策与需求 Draft — user/main agent

- Context: Luna 正式运行两次启动尝试均被治理门拒绝（R2.3-005 账本封闭、非正式任务不能选 model profile），
  零消耗。
- Evidence: R2.3-007 delivery record `start76 预约被账本拒绝` 条目；ledger/runner 代码核实。
- Action/decision: 用户选择新开正式需求 R2.3-008 作为 Luna formal 运行载体，并确认三项功能决策（复用
  R2.3-005 切片 / 仅路由终态验收 / 3 start）。需求 Draft 提交为 `8a33c07`。
- Outcome/next step: 委托 planner 产出设计与共享测试计划。

### 2026-08-18 — planner 设计与测试计划 — planner

- Evidence: 设计 `2026-08-18-r2-3-008-luna-fullstack-route-design.md`（双层完成门机制、3-start initial cap
  编码、三个新资产、最小实现面）与测试计划 `2026-08-18-r2-3-008-luna-fullstack-route-test-plan.md`
  （deterministic A–E 矩阵 + 有界真实运行轮 R1–R8）。commit `8a53e27`。
- Action/decision: 主代理复核通过；关键决策——首批 3-start 授权以 `initial_start_cap=3` 配置常量编码
  （对齐 R2.3-005 先例，strict 账本无法以 budget_authorization 开账）；运行内保持 R2.3-005 全强度质量流程，
  路由/终态完成门在需求层由独立评审做出。
- Outcome/next step: 进入 mandatory plan review。

### 2026-08-18 — plan review Round 1 REVISE — plan reviewer/main agent

- Context: reviewer 对照真实代码核验设计关键假设。
- Evidence: 结论 `REVISE`——(Critical) `contracts.py` `_FORMAL_PROFILE_IDS` 封闭集未含新 profile，带
  `candidate_progress_timeout_seconds: 300` 的新 profile 在 strict 加载即被拒（reviewer 实测）；(High)
  `acceptance.py` `formal_deferred_pump` 按 task_id 字面集合判定，新 task 不在集合内会失去 start73
  report/watchdog 竞态保护；(Minor) 设计 §12 未列真实 run 完整命令面。其余关键假设（合同匹配、账本门、
  双层门机制、v2 task freeze 参数、create scope、测试覆盖闭合）核验通过。
- Action/decision: 三项均接受。Critical → `_FORMAL_PROFILE_IDS` 注册新 profile ID（否决删参数方案：会静默
  把 candidate timeout 降为 120s 默认，偏离复用基线）；High → 延迟泵集合加入新 task_id（否决书面接受风险：
  核心验收证据押在该路径）；Minor → 命令面补全。修订提交为 `a0f1a06`。
- Outcome/next step: 送回同一 reviewer 复核。

### 2026-08-18 — plan review Round 2 PASS 与开发移交冻结 — plan reviewer/main agent

- Evidence: reviewer 核对 `a0f1a06` diff 与代码：Critical/High 均关闭（封闭集仅 `contracts.py:429` 一处消费
  点，无其他校验语义变化；延迟泵集合扩展不触及终态/报告语义，005/003 行为不变）；无新 Critical/High。
  一处措辞级不精确（`--base-url` 实为可选带默认值）不构成阻塞。
- Action/decision: 接受 PASS。设计/测试计划标记 reviewed；需求状态更新为 `Design-reviewed`。冻结开发范围
  为设计 §9 全部表面：
  1. `modeling_team/formal_runs.py`：`R2_3_008_CONTRACT` + `FORMAL_RUN_CONTRACTS` 注册 + `__all__` 导出；
  2. `modeling_team/start_ledger.py`：R2.3-008 常量（initial cap 3 / additional 3）、`_LEDGER_CONFIGS` 条目、
     导出 requirement ID；
  3. `modeling_team/contracts.py`：`_FORMAL_PROFILE_IDS` 加入 `r2-3-008-modeling-team`；
  4. `modeling_team/acceptance.py`：`formal_deferred_pump` task_id 集合加入 `r2-3-008-formal-acceptance`
     （仅此单行）；
  5. 新增 `modeling_team/profiles/r2-3-008-modeling-team.yaml`、
     `modeling_team/tasks/r2-3-008-formal-acceptance.yaml`、
     `modeling_team/references/r2-3-008-acceptance-standard.json`（逐字镜像 + 最小重绑定，精确内容见设计
     §5.2/§5.3）；
  6. focused deterministic tests（测试计划 §2 A–E 矩阵，含 A6/A7 身份注册回归）。
  验证命令：`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest
  modeling_team/tests/ -q`、`python -m compileall modeling_team/`、
  `ruff check modeling_team/ --config backend/pyproject.toml`、`git diff --check`。
  开发不改 `backend/`/`frontend/`（重启门不触发）；不运行真实 Luna formal run（留待独立测试 Round 2 且须
  用户确认执行时机）；全程不读取/记录 `auth.json`/token 内容。
- Outcome/next step: `requirement_developer` 按冻结范围实施；完成后按稳定状态进入独立测试。

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |
| 1 | Critical：`_FORMAL_PROFILE_IDS` 封闭集未含新 profile，strict 加载即拒 | accepted-critical | `contracts.py:64-66`/`426-432`；reviewer 实测 REJECTED | 设计 §5.2 增注册要求；§9 纳入 contracts.py；测试计划 A6 |
| 1 | High：`formal_deferred_pump` task_id 字面集合不含新 task，Examiner 失去 start73 竞态保护 | accepted-high | `acceptance.py:4179-4186`；`test_start73_report_watchdog_race.py:358` | 设计 §5.3 增注册要求；§9 收窄非目标；测试计划 A7 |
| 1 | Minor：设计 §12 未列真实 run 完整命令面 | accepted-minor | `__main__.py:341-348`、`runner.py:415-416`、`preflight.py:53-70` | 设计 §12 与测试计划 §4 补全 |
| 2 | 上述三项修订复核 | PASS | reviewer 核对 `a0f1a06`；封闭集单点消费、泵扩展无语义变化 | 设计可实施 |

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |
| 0 | `8a33c07` + design `8a53e27` + revision `a0f1a06` | 设计/测试计划/需求 only；未修改产品代码 | `git diff --check` PASS；plan review Round 2 PASS | development handoff frozen |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| 0 | design-reviewed | UNEXECUTED | implementation 未开始 | 测试计划 §5 |

## Final verification

- 待实施与独立测试完成后填写。
