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

### Round 1（2026-08-18，deterministic 独立测试）

- Stable state：commit `5d34286`（main HEAD），工作树 clean；测试者为独立 requirement_tester，未参与
  实现与 spot-check。零真实模型调用、零 run root 创建、零真实账本写入（账本用例全部在
  `tempfile.TemporaryDirectory`）；未读取/记录任何 `auth.json`/token 内容。
- 范围：计划 §3 Round 1——实现审查 + A–E 全矩阵（含 A6/A7 回归）+ 全量回归。Round 2（真实 Luna
  run）未启动。
- 实现审查结论：`5d34286` 仅触及设计 §9 冻结表面（formal_runs/start_ledger/contracts/acceptance 单行
  泵扩展/三个新资产/新测试/test_model_routing.py 断言更新）；零 `backend/`/`frontend/` 改动
  （`git diff 5d34286 --stat -- backend/ frontend/` 为空）。三个资产对
  `git show 5d34286~1:modeling_team/...` 的 r2-3-005 对应文件 diff 仅含设计允许的重绑定
  （profile：profile_id/formal_contract/acceptance_standard 三行；task：task_id/objective 自引用句
  "For formal R2.3-008 (reusing the R2.3-005 slice contract),"/standard role_source 路径；standard：
  schema_version/requirement_ref 两行）。task objective 6411 字符逐句 diff 仅该自引用句差异，无任何
  route/terminal/quality-gate 措辞（"fallback"/"terminal" 命中均来自 005 基线原文）。`acceptance.py`
  泵集合为 `defer_output_pump` 唯一写点（acceptance.py:4179-4187），下游 codex.py:725/2558 仅消费
  spec 字段；`contracts.py` 封闭集单点消费（contracts.py:429）。
- 矩阵结果（方法：开发者套件 884 passed/1 skipped/286 subtests 全绿之外，另做独立探针）：
  - A1/A3/A4/A5：开发者套件 `test_r23008_luna_route_contract.py` 覆盖并通过；实现审查确认
    `formal_run_contract_for` 精确对匹配 + authoritative path/参数绑定沿用通用逻辑。
  - A2：008↔005 双向、008 profile+003 task 经 CLI 实测 exit 2 "unknown or cross-wired formal run
    contract"。**但见缺陷 R1-D1（High）：008 身份与非 formal 对端（如 `base-capability-smoke` /
    `new-scope-business-slice` / `base-three-agent.yaml`）的错配未被既有 cross-wire 守卫字面集合拒绝，
    validate exit 0 静默降级为非 formal 配置——同形 005/003 错配均 exit 2。**
  - A6：独立探针（`load_profile(strict=True)`）——008 profile 携 300s 通过；未注册 ID 携同参数被拒
    （"candidate progress timeout is restricted to the formal Profile"）；同未注册 ID 删参数后可加载
    （证明门是参数而非 ID 本身）。
  - A7：开发者测试经真实 `RunnerAcceptanceCarrier.start_child` + child factory 断言 spec
    `defer_output_pump=True`（008/005/003）与非 formal 不含该键；实现审查确认唯一写点。
  - B1/B2/B4/B5/B6：独立探针（fresh temp dir、真实 `StartLedger`）——resolver 精确配置（filename/cap
    3/increment 3/flags）；3 个 reserve→semantic_start 后第 4 个 start 以 "semantic-start budget is
    exhausted" 拒绝；terminal failure 后 `authorize_budget(3)` 扩容后第 4 个 start 成功；
    `initial_authorization` 对 R2.3-008 抛 `TeamConfigurationError`；篡改账本记录重放被拒。
  - C1/C2/C3/C5：开发者套件覆盖并通过；C4 由本测试独立 diff 证实（见实现审查）。
  - D1/D2/D3/D4：CLI 实测省略 `--model-profile` 时合同默认 `openai-luna-medium`，六角色
    `openai-codex/gpt-5.6-luna` requested/effective `medium/medium` `auth_mode=chatgpt-subscription`；
    显式 `--model-profile deepseek-v4-flash-max` exit 0 投影 `deepseek-direct`；preflight 顺序由
    runner.py:446-455 代码审查确认在 reservation/run root 之前。
  - E1/E4：`formal_runs.py` diff 仅新增（005/003 合同字段字节不变）；`openai-luna-medium.yaml` 与 closed
    catalog 不在 `5d34286` 触及文件中；R2.3-006/007 既有套件在 884 绿内。
  - E2：`.r2-3-002/003/005-start-ledger.jsonl` 测试前后 sha256 逐字节一致（002:
    `bef7e8be…f632`、003: `af64172…0dcc`、005: `328d10d…9ae2`）；`workspaces/modeling-runs/` 无任何
    `.r2-3-008-start-ledger.*`。
  - E3：`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest
    modeling_team/tests/ -q` → **884 passed, 1 skipped, 286 subtests passed（44.97s）**；
    `compileall modeling_team/` OK；`ruff check modeling_team/ --config backend/pyproject.toml` → All
    checks passed；`git diff --check`/`git diff --cached --check` 干净。
  - E5：`git diff 5d34286 --stat -- backend/ frontend/` 为空（重启门未触发）；被动 health
    `127.0.0.1:8001/api/health`=200、`127.0.0.1:5173/`=200。
- 缺陷：
  - **R1-D1（High，相邻 fail-closed 覆盖缺口；不在 A–E 字面矩阵内，未违反任一成文验收条）**：
    cross-wire 守卫的字面集合未注册 R2.3-008 身份——`modeling_team/__main__.py:503-513`、
    `modeling_team/runner.py:358-367`、`modeling_team/runner.py:1185-1192` 仅枚举 005/003 的
    profile/task ID。复现：`env -u DEEPSEEK_API_KEY -u OPENAI_API_KEY PYTHONPATH=backend:.
    backend/.venv/bin/python -m modeling_team validate --profile
    modeling_team/profiles/r2-3-008-modeling-team.yaml --task
    modeling_team/tasks/new-scope-business-slice.yaml` → exit 0（期望 exit 2 "unknown or cross-wired
    formal run contract"；对照：同命令换 r2-3-005 profile 为 exit 2；反向 008 task + `base-three-agent`
    profile 同样 exit 0）。后果有界：该降级路径不能选 model profile（runner.py:326-329 B3 门仍在）、
    不能触达 R2.3-008 账本；但按 runner.py:517-527，v2 非 formal run 会在 **R2.3-002 默认账本** reserve——
    Round 2 若 task 路径配错将静默启动非 formal DeepSeek 运行并消耗 R2.3-002 预算，而非如 005/003
    一样 fail closed。建议 Round 2 前由 developer 在三处集合加入 008 身份（窄修复）。
- 未执行项：计划 §4/R1–R8（Round 2 有界真实 Luna run）——按 §3 属下一轮且需用户确认执行时机，
  本轮未创建 run root、未写任何真实账本、未发起真实模型调用。D3 的 seam 注入两类失败 reason 由开发者
  测试覆盖（test_d3_subscription_preflight…），本轮以代码审查 + 真实默认路径 CLI 实测替代注入复跑。
- 结论：**Round 1 deterministic 矩阵 PASS**（A–E 全部通过、全量回归绿、账本/历史证据零改动）；1 个
  High 缺陷 R1-D1 在矩阵外的相邻守卫层，建议修复后再进 Round 2。测试后清理了全部临时探针文件与
  `__pycache__` 产物，工作树保持 clean。

### Round 2（2026-08-18，R1-D1 修复复测）

- Stable state：commit `a785d1d`（main HEAD）"Register R2.3-008 identities in cross-wire guards"；工作树仅含
  本测试计划 Round 1 追加（主代理保留未提交）。修复面审查：`formal_runs.py` 从 closed
  `FORMAL_RUN_CONTRACTS` 派生导出 `FORMAL_PROFILE_IDS`/`FORMAL_TASK_IDS`（frozenset，自动覆盖未来注册
  合同）；三处守卫（`__main__.py:510-513`、`runner.py:361-363`（prepare）、`runner.py:1183-1186`
  （preview_baseline））全部改用派生集合，无 005/003 字面残留；零 `backend/`/`frontend/` 改动。
  零真实模型调用、零 run root、零真实账本写入（prepare 探针用 temp ledger root）。
- R1-D1 复测（FIXED）：
  - CLI validate（守卫 1）：Round 1 两个复现方向均由 exit 0 → **exit 2 "unknown or cross-wired formal
    run contract"**——008 profile + `new-scope-business-slice.yaml`（v2 非 formal task）、008 profile +
    `base-capability-smoke.yaml`、`base-three-agent.yaml` + 008 task；008↔005 双向、008 profile + 003
    task 保持 exit 2。
  - `TeamRunner.preview_baseline`（守卫 3，独立探针）：008 profile + 非 formal task 与 base profile +
    008 task 双向抛 `TeamConfigurationError`，不创建任何 run/ledger 状态。
  - `TeamRunner.prepare`（守卫 2，独立探针，temp ledger root）：008 profile + 非 formal task 在任何
    reservation/run root 副作用前抛 `TeamConfigurationError`；temp ledger root 剩余文件为空 `[]`。
  - 派生集合实测内容：profiles `{003, 005, 008}`、tasks `{003, 005, 008}`。
- 修复影响回归：
  - 注册表语义未变：005/003 有效对 validate exit 0；005 profile + 非 formal task 仍 exit 2（与修复前同形）。
  - 有效 008 对 validate exit 0，省略 `--model-profile` 合同默认 `openai-luna-medium`，六角色唯一投影
    `(openai-codex, gpt-5.6-luna, medium, medium, chatgpt-subscription)`。
  - E3：`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest
    modeling_team/tests/ -q` → **887 passed, 1 skipped, 293 subtests passed（44.62s）**（较 Round 1 增 3
    tests/7 subtests 即修复新增守卫测试）；`compileall modeling_team/` OK；`ruff check …` All checks
    passed；`git diff --check`/`git diff --cached --check` 干净。
  - E2：`.r2-3-002/003/005-start-ledger.jsonl` 本轮前后 sha256 与 Round 1 记录逐字节一致（
    `bef7e8be…/af64172…/328d10d…`）；`workspaces/modeling-runs/` 仍无任何 `.r2-3-008-start-ledger.*`。
  - E5：`git diff a785d1d --stat -- backend/ frontend/` 为空（重启门未触发）；被动 health
    `8001/api/health`=200、`5173/`=200。
- 缺陷：无新增；R1-D1 关闭。
- 未执行项：计划 §4/R1–R8（有界真实 Luna run）仍属下一轮且需用户对执行时机的明确确认（授权冻结 +
  3-start 预算纪律照 §4/§6）；本轮未创建 run root、未写真实账本、未发起真实模型调用。
- 结论：**Round 2 PASS——R1-D1 FIXED**（三守卫路径双向复测通过、修复影响回归绿、全量 deterministic
  套件与 compile/lint/diff 检查通过、真实账本与历史证据零改动）。测试后清理全部临时探针与
  `__pycache__`；工作树仅余本测试计划的 append 修改。

### Round 3（2026-08-18，授权的真实 Luna formal run start1/start2/start3）

- Stable state：commit `a785d1d`；资产 digest 按 delivery record Round 3 冻结条目；run identity
  `r23008-luna-20260818-start1`；freeze `2026-08-17T18:32:06Z` → reservation 18:32:16Z（10s，≤20min 门）。
- 结果：**启动层失败（presemantic）**——coordinator App Server `_initialize` 的 `skills/list` RPC 返回
  `-32603`，CLI exit 2，零模型调用、零 thread/start。账本 `reservation → presemantic_release`，无
  `semantic_start`，**0/3 semantic start 消耗**。scope cleanup `deleted-empty`、acceptance
  aborted/zero_child_residue、零 child 残留；temp admin key revoked（复验 401）。
- 定层与调查：`runtime/infrastructure`（详见 delivery record start1 条目）；Host codex 0.147.0 于运行前
  34 分钟被更换，4 档本地探针（bwrap/真实 skill 树/真实 auth staging/config+MCP 表）未能复现。
- 观察项：`aggregate_secret_audit match_count=1`（runtime 内部 token 瞬态命中；Host ChatGPT 凭据经
  digest-only 复现审计证实不在 run root）。
- 结论：R1–R8 判定不成立也不失败（run 未达业务交付，按 §4 R8 以 presemantic release 处置）；继续
  start2（同冻结授权，预算 3/3）。

**start2（同日）**：

- Stable state：commit `533d896`（start1 文档提交后工作树 clean）。首次启动尝试被 clean baseline gate 拒绝
  （"clean baseline gate rejected non-empty git status"）——主代理未提交的 start1 文档追加所致，preflight
  阶段拒绝、零 reservation、零账本写入（账本复核仍仅 start1 两条事件）；属 setup 疏失，非缺陷。
- 复跑：freeze `2026-08-17T18:53:5x Z` → reservation 18:53:55Z。**同形失败**——`app-server skills/list
  failed (rpc_error, code=-32603)`，reservation 后 ~3.8s，零模型调用、零 thread/start。账本
  `reservation → presemantic_release`，**仍 0/3 消耗**。evidence `app-server-events.jsonl` 与 start1 同形
  （configWarning / remoteControl/status/changed / skills/changed 三个通知）。
- Cleanup：state `CLEANED`、owned Project/Ontology 删除（residual 全零）、acceptance aborted/
  zero_child_residue、runner 自建 admin key 已自 revoke（revoked_at 18:53:58Z）、主代理 temp admin key
  `ab6fbce9…` 已 revoke（复验 401）。
- 结论：按 start1 条目预承诺的判定——**0.147.0 app-server 与当前 `_initialize` 握手机械确定性不兼容**
  （runtime/infrastructure），回 requirement_developer 窄修复 handshake 层；修复经 deterministic 复测后再
  决定 start3（预算仍 3/3）。

**start3（同日，Round 4 修复复测 PASS 后）**：

- Stable state：commit `ff39aa2`（`303d701` 修复 + Round 4 复测文档）。freeze → reservation 19:26:35Z。
- 结果：**握手修复实证生效，推进到第三角色后失败**——coordinator 与 modeling 均完成 `_initialize` →
  `thread/start`（获得 thread_id、shell snapshot、MCP service 初始化、并连接
  `wss://chatgpt.com/backend-api/codex/responses` websocket），零 configWarning；protocol 角色
  `thread/start` 返回 -32603（`app-server thread/start failed (rpc_error, code=-32603)`）。零模型
  turn、零 semantic start——账本 `reservation → presemantic_release`，**仍 0/3 消耗**。
- 诊断（run root `logs_2.sqlite` 逐角色比对）：三个角色的 `thread/start` 均触发 0.147.0 新增 online
  models refresh（`GET https://chatgpt.com/backend-api/codex/models`），coordinator/modeling 记录两条
  ERROR `failed to refresh available models: timeout waiting for child process to exit` 后**容忍**并继续
  session_init；protocol 在同一 GET 后直接以 -32603 失败（其 log 终止于该 GET，无容忍路径）。
- Cleanup：state `CLEANED`、acceptance aborted/zero_child_residue、三个角色 admin key 与主代理 temp key
  `8bc051a2…` 全部 revoke（复验 401）；R2.3-008 窗口六个 key 全部 non-active。
- 结论：runtime/infrastructure（0.147.0 models-refresh 子进程超时在并发第三角色上升级为致命 RPC 错误），
  按 §4 R8 回 developer 窄修复（含 runtime 错误信息 surfacing 缺口——CLI 只保留 code 丢失 message）；
  修复复测后决定是否继续（预算 3/3 未动）。

### Round 4（2026-08-18，start1/start2 同形失败缺陷修复复测）

- Stable state：commit `303d701`（main HEAD）"Fix builtin-provider config splice dropping [features] header"；
  工作树仅含主代理未提交的 delivery record 追加（docs only）。测试者为独立 requirement_tester，未参与
  修复与 developer 离线复现。零真实模型调用、零 run root 创建、零真实账本写入、零真实 run；未读取/记录
  任何真实 `auth.json`/token 内容（探针 host auth 全部为自造 `{}` 字节）。
- 范围：start1/start2 缺陷修复 `303d701` 的独立复测——实现审查 + 独立 config-shape 验证（真实
  `load_profile`/`load_task`/`load_team_model_profile` + 真实 `_write_config`/child impl）+ 真实 codex
  0.147.0 二进制 config 解析对照 + 全量回归 + 账本/证据 hygiene。
- 实现审查（PASS）：
  - `git show 303d701 --stat`：仅 `modeling_team/runtimes/codex.py`（+8/−2，其中代码变更仅
    codex.py:3530 一行拼接 `provider_lines[:3] + lines + provider_lines[3:]` + 注释扩展）与新测试
    `modeling_team/tests/test_r23008_codex_builtin_config.py`（3 tests）；零 `backend/`/`frontend/` 改动
    （`git diff 303d701 --stat -- backend/ frontend/` 为空）；零 semantics/ledger/acceptance 表面改动。
  - 外部会话路径（codex.py:3549，`lines` 已预置 model trio）的 `lines[3:]` 截断语义正确保留未动；
    Examiner child 路径（codex.py:2364）本就使用正确的非截断拼接 `provider_lines[:3] + config_lines +
    provider_lines[3:]`，从未受此缺陷影响（start1/start2 亦未到达 child 启动）。
- 独立 config-shape 验证（PASS，一次性探针，已删除）：真实加载 008 profile（strict）/task/model profile
  `openai-luna-medium`（sha256 `b6dee50e…`），驱动真实 `_write_config`（四个 persistent role）与真实
  `_launch_acceptance_child_impl`（source/platform 两类 fresh Examiner child，fake process/RPC surface，
  均完成完整 impl startup 含 thread/start），对全部六角色 config.toml 以 tomllib 断言——
  `sandbox_mode=="read-only"`、`web_search=="disabled"`、11 个 feature flag 恰好构成 `[features]` 表且
  全部为 false、零 flag 裸露顶层、model trio（`gpt-5.6-luna`/`openai`/`medium`）恰出现一次、
  `[shell_environment_policy]`（inherit="core"）在位、顶层键恰为封闭集
  {model, model_provider, model_reasoning_effort, sandbox_mode, web_search, features, mcp_servers,
  shell_environment_policy}、无自定义 `[model_providers]`；child 另含 examiner_report（platform 再含
  platform_read_proxy）且不含 team_transport。128 项断言全过、0 失败。
- pre-fix 失败签名交叉验证（PASS）：从 post-fix 真实 config 按旧拼接语义（去第 4–6 行：
  `sandbox_mode`/`web_search`/`[features]`）推导 pre-fix 形状——六角色推导形状均使 11 个 flag 裸露顶层、
  第 4 行为 `apps = false`；以真实 codex 0.147.0 二进制对照（`CODEX_HOME=<各自 home> codex login status`，
  零模型调用）：pre-fix home 报
  `Error loading configuration: …/config.toml:4:8: invalid type: boolean \`false\`, expected struct
  AppsConfigToml`——与 start1/start2 保留的 `skills/list` -32603 失败逐字同形；post-fix home 正常解析并
  走完命令（无任何 config 错误/警告）。修复与根因之间的因果链由独立证据闭合。
- 回归（PASS）：`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest
  modeling_team/tests/ -q` → **890 passed, 1 skipped, 293 subtests passed（44.71s）**（较 Round 2 增 3
  tests 即新回归测试）；`compileall modeling_team/` OK；`ruff check modeling_team/ --config
  backend/pyproject.toml` All checks passed；`git diff --check`/`git diff --cached --check` 干净。
- 账本/证据 hygiene（PASS）：`.r2-3-002/003/005-start-ledger.jsonl` sha256 逐字节与 Round 1/2 记录一致
  （`bef7e8be…f632`/`af64172…0dcc`/`328d10d…9ae2`）；`.r2-3-008-start-ledger.jsonl` 恰 4 事件——start1 与
  start2 各一条 `reservation` + 一条 `presemantic_release`（与本计划 Round 3 及 delivery record 记录的
  post-start2 状态一致；本任务简报中"恰 2 事件"为 start2 前的旧快照），零 `semantic_start`，
  **semantic start 预算仍 0/3 消耗**；`git status --short workspaces/ backend/ frontend/` 为空，
  `workspaces/modeling-runs/` 零修改。
- 未执行项：真实 app-server `skills/list` 完整握手（bwrap namespace + `_initialize`）未由本轮独立重跑——
  该链接由 developer 真实路径离线复现（post-fix 完整 coordinator 启动、零 configWarning）覆盖，且本轮以
  真实 0.147.0 二进制对 pre/post-fix config 的解析对照独立闭合了因果链；完整握手证明按 §4 归 start3。
  运行时 `/tmp/r23008-formal-credential-*` 18 个目录为 developer 早前会话产物（02:26 时间戳，早于本轮），
  非本轮创建，未处置。
- 缺陷：无新增。start1/start2 同形 `skills/list` -32603 缺陷判 **FIXED**（独立 config-shape + 真实二进制
  解析双重证实）。
- 结论：**Round 4 PASS——修复清除 start3 障碍**。窄修复面（一行拼接 + 回归测试）与根因完全对应，
  deterministic/回归/账本 hygiene 全绿；建议主代理在提交当前 delivery record 追加（start2 clean baseline
  gate 教训：非 clean tree 会被 preflight 拒绝）并完成 §4 冻结要素后，即可消耗首个 semantic start 启动
  start3（授权预算 3/3 未动）。测试后删除全部临时探针与 `__pycache__`；工作树仅余本测试计划与主代理
  delivery record 的 docs 追加。

### Round 5（2026-08-18，start3 thread/start 缺陷修复复测）

- Stable state：commit `c85628a`（main HEAD）"Seed models cache for builtin route and retain RPC error
  messages"；工作树仅含主代理未提交的 delivery record 追加（docs only，非本测试处置）。测试者为独立
  requirement_tester，未参与修复与 developer 离线复现。零真实模型调用、零 run root 创建、零真实账本
  写入、零真实 run；未读取/记录任何真实 `auth.json`/token 内容（探针 host auth 为自造 `{}` 字节）。
- 范围：start3 第三角色 `thread/start` -32603 缺陷修复 `c85628a` 的独立复测——实现审查 + vendored
  snapshot 安全审查 + 独立行为探针（真实 `_write_config` 种子链 + RPC message 保留）+ 全量回归 +
  账本/证据 hygiene。
- 实现审查（PASS）：
  - `git show c85628a --stat`：恰 4 文件——`modeling_team/references/codex-models-cache-0.147.0.json`
    （新增 593 行）、`modeling_team/runtimes/codex.py`（+78/−7）、新测试
    `test_r23008_codex_models_cache_seed.py`（3 tests）、`test_runtime_failure_boundary.py`（改 1 增 1）；
    `git diff c85628a --stat -- backend/ frontend/` 为空（重启门未触发）；零 modeling 语义/账本/
    acceptance 表面改动（种子调用点在 `_write_config` builtin 分支内，错误对象仅新增 sanitized
    `server_message` 字段与 str 追加）。
  - 种子调用点唯一（codex.py:3553），位于 `formal and not uses_external_credential_session(binding.
    provider_id)` 的 builtin 分支（`_formal_codex_builtin_config_lines` 拼接之后）；外测 provider 分支与
    非 formal 路径不触发。`_seed_models_cache` 逐项防御：非 dict snapshot/非 list models/无 slug 集/
    slug 不命中 → 静默 return（保持 legacy 行为）；`OSError`/`JSONDecodeError` → 静默 return；
    `fetched_at` 以 `datetime.now(timezone.utc)` 置启动时刻；`models_cache.json` 写入后 `chmod 0600`。
  - RPC message 保留：`_sanitize_rpc_message` 仅空白折叠 + 240 字符截断（空串归 `None`）；
    `_rpc_error_from_value`（`_rpc` 真实异常路径，codex.py:4216/4264）在既有 `message` 必须为 `str` 的
    门后传入 sanitized message；malformed 分支（message 非 str）`server_message=None` 且 str 不含
    message；`data` 字段仍完全不进入错误对象。
- Vendored snapshot 安全审查（PASS）：`codex-models-cache-0.147.0.json`（173,963 字节）可解析 JSON；
  顶层键恰 `{client_version, etag, fetched_at, models}`，`client_version` 精确 `"0.147.0"`；7 个 model
  条目，`gpt-5.6-luna` 在列且 `supported_reasoning_levels` 含 `medium`（default_reasoning_level 亦为
  `medium`）。secret 扫描：键名路径命中 key-like 模式者仅 `model_messages.token_budget.*` 指令模板
  （纯提示词文本）；≥32 字符长字符串全部为 instructions_template/policy 模板（熵 4.3–4.6，自然语言）；
  唯一 etag `W/"fc34272d86d82eed47b4011efcecf30f"` 属正常 HTTP etag 形态；`auth.json`/`Bearer `/`access_
  token`/`refresh_token`/`api_key` 零命中；`sk-` 命中经上下文核对全部为 "task-specific" 子串。判定为
  官方 endpoint 模型目录元数据，无凭据/令牌。
- 独立行为探针（PASS，一次性脚本已删除；23/23 断言）：真实 `load_profile` 链 + `CodexRuntimeAdapter`
  + `openai-luna-medium` 投影驱动真实 `_write_config`：
  - (a) builtin binding（coordinator）：`models_cache.json` 落于 agent home，`models` 与 snapshot 逐字
    相等（etag 逐字保留），`client_version` `0.147.0`，`fetched_at` 距 now <0.1s，slug 集含
    `gpt-5.6-luna`，mode `0600`；config.toml 仍为 `openai`/`gpt-5.6-luna`（Round 4 拼接修复未被扰动）。
  - (b) 稍后启动的第二个 home（modeling）`fetched_at` 严格晚于前者（启动时刻戳逐次刷新）、models 仍
    逐字、mode `0600`。
  - (c) slug 不在 snapshot（`gpt-not-in-snapshot`）：不落任何 cache 文件。
  - (d) 隔离 repo root 下 snapshot 损坏（`{not json`）与不可读（mode 000）两种形态：`_write_config` 均
    不抛异常、不落 cache、config.toml 正常写出（安全降级为 legacy 行为）。
  - (4) RPC message 保留：`_rpc_error_from_value("thread/start", {code:-32603, message 含 \n/\t/多空格,
    data 含伪 secret})` → `server_message` 精确为折叠后文本、str 含 `code=-32603` 与 message、伪 secret
    不在 str/repr；500 字符 message 截断为恰 240；message 非 str → `malformed_rpc_error` 且
    `server_message=None`；`turn/steer` 分类（`no_active_turn_to_steer`）不受影响且 message 同步保留；
    直接构造格式 `app-server thread/start failed (rpc_error, code=-32603): boom` 与 runtime 自身调用点
    一致。
- 回归（PASS）：`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest
  modeling_team/tests/ -q` → **894 passed, 1 skipped, 293 subtests passed（44.03s）**（较 Round 4 增 4
  tests 即修复新增）；`python -m compileall modeling_team/` OK；`ruff check modeling_team/ --config
  backend/pyproject.toml` All checks passed；`git diff --check`/`git diff --cached --check` 干净。
- 账本/证据 hygiene（PASS）：`.r2-3-002/003/005-start-ledger.jsonl` sha256 与 Round 1/2/4 记录逐字节一致
  （`bef7e8be…f632`/`af64172…0dcc`/`328d10d…9ae2`）；`.r2-3-008-start-ledger.jsonl` 恰 6 事件——start1/2/3
  各一条 `reservation` + 一条 `presemantic_release`，零 `semantic_start`，**semantic start 预算 0/3
  消耗（3/3 未动）**；`git status --short workspaces/ backend/ frontend/` 为空，`workspaces/
  modeling-runs/` 零修改。
- 缺陷：
  - **R5-D1（High，修复覆盖缺口——Examiner child home 未种子）**：`_seed_models_cache` 仅在
    `_write_config`（persistent role 路径，codex.py:3553）被调用；fresh Examiner child 的 builtin 分支
    （`_launch_acceptance_child_impl`，codex.py:2370-2374 使用同一
    `_formal_codex_builtin_config_lines(child_model_override)`）**不种子** child 的独立 fresh home，而
    child 同样执行 `thread/start`（codex.py:2524，fresh home 无 `models_cache.json` → 同一 online
    refresh 路径）。复现依据（代码级）：grep 确认 `_seed_models_cache` 调用点唯一。期望：所有 formal
    builtin-provider agent home（含两类 fresh Examiner child）种子；实际：仅 persistent role 种子。
    后果：start3 的致命竞态在 child 启动面仍存在——若在 acceptance 阶段（`semantic_start` 已消耗后）
    child `thread/start` 命中致命分支，将烧掉 1/3 semantic start（start3 三 persistent 角色即 1/3 命中
    致命分支）。缓解因素：child 的 refresh 行为为代码级推断（start3 未达 child 启动，无 live 证据），
    且 developer 离线复现只覆盖三个 persistent 角色。建议：start4 前由 developer 在 child builtin 分支
    补一行 `self._seed_models_cache(...)`（等价窄修复），或主代理明确接受该残余风险后再启动。
- 未执行项：真实 bwrap 多角色 `thread/start` 复现（developer 离线已做；本轮以真实 `_write_config`
  种子链 + 代码级唯一调用点审查独立闭合"cache 必然落盘"链路，但 cache 命中→refresh 跳过一段沿用的
  是 codex 0.147.0 `online_if_uncached` 行为结论，非本轮 live 复测）；真实 run 属 start4（主代理决策）。
- 结论：**Round 5 PASS（修复本体 FIXED）**——种子行为、安全降级、snapshot 安全、RPC diagnosability、
  全量回归与账本 hygiene 全绿，persistent-role 路径的 start3 缺陷判定修复。但 **R5-D1（High）指出
  Examiner child 路径未获同等种子覆盖**；是否以一行窄修复补齐 child 分支后再启动 start4，由主代理
  决策（授权预算 3/3 未动、0/3 已消耗）。测试后删除全部临时探针与 `/tmp/r5probe`；工作树仅余本测试
  计划与主代理 delivery record 的 docs 追加。
