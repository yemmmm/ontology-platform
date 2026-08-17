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

### Round 3（2026-08-18，授权的真实 Luna formal run start1/start2）

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
