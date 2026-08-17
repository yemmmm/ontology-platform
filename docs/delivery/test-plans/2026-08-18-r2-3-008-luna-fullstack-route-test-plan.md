# R2.3-008 Luna 全栈路由/终态验证共享测试计划

- 状态：reviewed / UNEXECUTED——plan review Round 2 PASS（2026-08-18），实施未开始；本计划覆盖
  deterministic 矩阵与一次有界真实运行轮
- Requirement：`docs/requirements/requirements-v2.3.md#r23-008-luna-全栈路由终态验证复用-r235-切片`
- Design：`docs/delivery/designs/2026-08-18-r2-3-008-luna-fullstack-route-design.md`
- Delivery record：待实施开始后创建
- 复用基线：R2.3-007 测试计划（Round 1–6，含 A6 真实 Luna probe）与 R2.3-005 formal 验收流程

## 1. 完成门

1. `R2_3_008_CONTRACT` 与新 profile/task/standard 作为精确 authoritative 对解析；省略 `--model-profile` 时
   六角色投影为 `openai-codex/gpt-5.6-luna/medium/medium`，三条命令（validate/baseline/run）解析一致。
2. R2.3-008 StartLedger 以 formal 政策镜像解析；3-start 初始预算、20 分钟 freeze 门、状态机、授权不可变性
   按现有规则行为；`initial_authorization` 对 R2.3-008 拒绝；R2.3-002/003/005 账本与合同零改动。
3. 全量 `modeling_team` deterministic suite、compile、lint、diff checks 通过。
4. 一次授权的真实 Luna formal run：路由/终态证据完整——六个 package（含两个 fresh Examiner child）经 Luna
   真实启动、Team Transport 通信、平台/MCP 工具调用、typed 终态报告、完整 cleanup 零残留；evidence 记录
   逐角色 route binding 与 `auth_mode=chatgpt-subscription`；质量证据产生并保留但不作为完成门。
5. 计划评审无未处置 Critical/High；独立测试轮次 append-only，失败轮保留。

## 2. Deterministic 测试矩阵

### A. Contract 解析与资产校验

- A1 `load_formal_run_configuration` 接受新 profile/task 对，返回 `R2_3_008_CONTRACT`；`formal_run_contract_for`
  按 `(r2-3-008-modeling-team, r2-3-008-formal-acceptance)` 精确命中。
- A2 cross-wire 拒绝：R2.3-008 profile 配 R2.3-005 task（及反向）得不到任何 formal contract（fail closed）。
- A3 authoritative path 与参数绑定：错误 profile/task 路径、`formal_contract`/`acceptance_standard` 参数漂移、
  缺失 standard/model-profile 文件、symlink 均在任何 run 副作用前拒绝。
- A4 `deletion_policy` 为 `None`；携带 deletion policy 的 R2.3-008 合同被 `validate_formal_run_contract_assets`
  拒绝（restriction 仍限 R2.3-003）。
- A5 `FORMAL_RUN_CONTRACTS` 仍包含字段字节不变的 `R2_3_005_CONTRACT`/`R2_3_003_CONTRACT`。
- A6（plan review Round 1 Critical-1 回归）`contracts.py` `_FORMAL_PROFILE_IDS` 含
  `r2-3-008-modeling-team`：新 profile 连同 `candidate_progress_timeout_seconds: 300` 通过
  `load_profile(strict=True)`/`load_formal_team_configuration`；未注册 ID（负例 fixture）携带该参数仍被拒绝。
- A7（plan review Round 1 High-2 回归）新 task 触发的 Examiner child resource spec 含
  `defer_output_pump: True`（`acceptance.py` formal_deferred_pump 集合含
  `r2-3-008-formal-acceptance`）；既有 005/003 task 行为与非 formal 即时泵形态不变。

### B. Ledger 配置与预算门（临时目录账本）

- B1 `resolve_ledger_config("R2.3-008")` 返回精确配置（filename `.r2-3-008-start-ledger.jsonl`/`.lock`、
  initial cap 3、increment 3、strict_sequence/allow_incomplete_modeling_quality_repair/
  allow_variable_authorization 全 True）；filename/cap/increment 覆盖不匹配时拒绝；未知 requirement ID 拒绝。
- B2 reservation → semantic_start 正常消耗；第 4 个 start 被预算耗尽拒绝；同一时刻第二个 active reservation
  被拒绝。
- B3 未 terminal-failure 的 start 之后新 reservation 被拒绝（首个完整结果即终局语义）。
- B4 terminal_failure 必须分类最新 semantic start；此后 `authorize_budget`（`--requirement-id R2.3-008`）以
  唯一 `authorization_id`/`reference` 扩展预算，重放/变异被拒绝；扩展发生在 terminal failure 之前被拒绝。
- B5 `initial_authorization`（`authorize-initial`）对 R2.3-008 抛 `TeamConfigurationError`。
- B6 篡改账本（乱序、伪造授权、重复 run_id）被 strict replay 拒绝。

### C. Task 与验收标准校验

- C1 `validate` 对新对通过，输出 profile digest 与六角色 `openai-codex/gpt-5.6-luna` requested/effective
  `medium/medium` 投影。
- C2 新 standard JSON 经 `_acceptance_ticket_policy` 解析：恰好 2 个 CQ（`cq-001`/`cq-002`）、
  `unknown_policy=preserve-explicit-unknown`、`requirement_ref` 指向 R2.3-008、digest 冻结。
- C3 standard 漂移拒绝：1 个或 3 个 CQ、CQ ID 重复或偏离 `cq-001`/`cq-002`（与 runner 注入的
  "two terminal Examiner reports / final cq-002"文本一致性要求）、未知/缺失字段、错误 unknown_policy。
- C4 task objective 与 `r2-3-005-formal-acceptance.yaml` 逐字 diff 仅含 §5.3 允许的差异（requirement 自引用
  改写）；role_sources/protocol_tools/expected_terminal_evidence/semantic_start_evidence 一致，acceptance 角色
  的 standard role_source 指向新路径。
- C5 `baseline` 冻结与 `validate` 相同的 profile/task/standard/model-profile digest。

### D. 默认 model profile 投影

- D1 省略 `--model-profile` 时 `run` 的合同默认解析为 `openai-luna-medium`（不落回 DeepSeek 默认）。
- D2 baseline `team_model_profile` 块包含六角色 binding、profile path/sha256，不含 endpoint、credential
  path/value/digest 或 provider free text。
- D3 profile 引用 `openai-codex` 时，reservation 前执行 Host ChatGPT/file-cache preflight（注入 seam 验证
  `chatgpt-subscription`/两种失败 reason）；preflight 失败不创建 run root 或账本写入。
- D4 显式 `--model-profile` 覆盖路径不变；三条命令使用同一解析分支。

### E. 回归（R2.3-005/R2.3-003 及既有机械不受影响）

- E1 R2.3-005/R2.3-003 合同解析、authoritative 资产校验、deletion policy 行为与 HEAD 一致。
- E2 实仓 `workspaces/modeling-runs/` 下 `.r2-3-002/003/005-start-ledger.jsonl` 在全部测试前后 sha256 不变；
  历史 run root 零修改。
- E3 全量 `modeling_team` deterministic suite（`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:.
  backend/.venv/bin/python -m pytest modeling_team/tests/ -q`）、`python -m compileall modeling_team/`、
  `ruff check modeling_team/ --config backend/pyproject.toml`、`git diff --check` 通过。
- E4 R2.3-006 Examiner 隔离与 R2.3-007 路由/订阅认证既有套件无回归；`openai-luna-medium.yaml` 与 closed
  catalog 字节不变。
- E5 零 `backend/`/`frontend/` 改动，重启门未触发；被动 health 抽查 `127.0.0.1:8001/api/health` 与 `5173/`
   HTTP 200。

## 3. 计划轮次

- Round 1（deterministic）：实现审查 + A–E 全矩阵（含 A6/A7 身份注册回归）+ 全量回归；发现问题回 developer
  窄修复。
- Round 2（bounded real run）：§4 授权的真实 Luna formal run 本身；真实运行前必须完成 Round 1 并获得用户
  对执行的明确确认（3-start 首批授权已随需求确认，执行时机仍须冻结）。
- 后续轮次只修复已确认 requirement defect；继续追加本文，不创建第二份测试计划。

## 4. 有界真实运行轮（授权的 Luna formal run）

真实 run 前在 delivery record 冻结授权，模板与要素如下（沿用 A6/start75 授权冻结纪律）：

- **Authorization source**：用户 2026-08-17/18 对 R2.3-008 首批 3 个 semantic start 的确认（requirement
  §已确认目标第 4 条）。
- **Budget**：R2.3-008 账本 3 个 semantic start；每次失败按既有四层分类记 terminal 后才可决定是否消耗下一
  start；不追加新 budget 授权；不自动 fallback 到 DeepSeek/API Key/另一 effort。
- **Run identity**：`r23008-luna-<date>-start<N>`；task `modeling_team/tasks/r2-3-008-formal-acceptance.yaml`；
  profile `modeling_team/profiles/r2-3-008-modeling-team.yaml`；model profile `openai-luna-medium`（省略
  `--model-profile`，验证合同默认路径即真实操作路径）。`run` 完整调用还需 `--run-id <identity>`、
  `--scope <内容为 mode: create 的 YAML 文件>`、`--freeze-started-at <UTC 时间戳>`（v2 task 必填）、
  `--base-url http://127.0.0.1:8001`，环境侧 `ONTOLOGY_PLATFORM_ADMIN_API_KEY` 仅覆盖 canonical gate 窗口。
- **边界**：fresh scope（mode=create，平台自建 Project/Ontology）；canonical gate 临时 admin key 运行结束即
  revoke；不读取/记录 `auth.json`/token 内容（仅元数据）；全程零 API-key 路径；run 中途不换 profile。
- **Freeze 纪律**：资产 digest 冻结后 20 分钟内完成 reservation；同一时刻最多一个 active reservation；每个
  start 的 run root 与证据完整保留。
- **Cleanup owner**：Delivery Agent（主代理）——revoke 临时 admin key、核对 run root 终态、零残留扫描。

**Run 后证据检查（路由/终态完成门，R1–R8）**：

- R1 六个 package 的启动证据：四个 persistent role + 两类 fresh Examiner child（canonical package ID
  `source-examiner`/`platform-examiner`）逐角色 exact binding `openai-codex/gpt-5.6-luna/medium` 与
  `auth_mode=chatgpt-subscription`。
- R2 Team Transport 通信证据（delivery/coordination/report 事件）与平台/MCP 工具调用 receipts（build
  session/batch、dry-run/apply、validation/reasoning、governed retrieval、Examiner capability）。
- R3 typed 终态报告：child `terminal_report_digest`、persistent role `report_task_result`、run 状态机终态
  （settled 或 typed terminal failure 及分类）。
- R4 完整 cleanup：aggregate/per-role audit scan complete、zero match、zero error、zero child residue；
  listener/thread/socket 零残留；auth staging barrier 在首个 turn 后、任何 ServerRequest/tool/MCP dispatch 前
  移除；run root/日志/evidence 零 token/账户信息（secret-shaped 扫描零命中）。
- R5 账本：`.r2-3-008-start-ledger.jsonl` 只含实际消耗 start 的 reservation/semantic_start（+ 失败时
  terminal_failure）；`.r2-3-002/003/005` 账本字节不变。
- R6 质量证据已产生并保留（CQ verdict、candidate/validation/reasoning/retrieval receipts）——记录其内容但
  不以 usable PASS 与否判定本需求完成。
- R7 完成判定：R1–R5（及 R4 的 secret 审计）全部成立即 R2.3-008 路由/终态门 PASS；run 结局 settled 或
  retryable terminal failure 均不影响该判定；判定由未创建/未延续该 run 的独立评审做出且不改动脉据。
- R8 失败处置：任一 R1–R5 不成立时，按四层分类记 terminal、保留失败层证据、修复最窄层后再决定是否消耗
  下一 start；预算未耗尽即达成完成门时，剩余 start 不执行（R2.3-005 Start76–77 先例）。

## 5. 独立测试轮次

### Round 0（2026-08-18，UNEXECUTED）

- 状态：设计与实施未开始；无 Agent 启动、无 ledger start、无平台写入、无真实模型调用。
- 本节及后续轮次 append-only；每轮记录 stable state、范围、结果、缺陷/未执行项与证据指针。
