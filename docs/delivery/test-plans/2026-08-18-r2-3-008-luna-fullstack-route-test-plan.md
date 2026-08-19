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

### Round 3（2026-08-18，授权的真实 Luna formal run start1–start4）

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

### Round 5（续，2026-08-18，R5-D1 修复复测）

- Stable state：commit `aee472b`（main HEAD）"Seed models cache for Examiner child builtin route (R5-D1)"
  （前置 `136cc4a` 为 Round 5 文档提交）。测试者为独立 requirement_tester，未参与修复。零真实 run、
  零真实账本写入、零模型调用；未读取/记录任何真实 `auth.json`/token 内容（探针 host auth 为自造
  `{}` 字节；`process_factory` sentinel 保证零二进制 spawn）。
- 实现审查（PASS）：`git show aee472b --stat` 恰 2 文件——`modeling_team/runtimes/codex.py`（+20/−9）
  与 `modeling_team/tests/test_r23008_codex_models_cache_seed.py`（+105/−1，新增 3 tests）；零
  `backend/`/`frontend/` 改动。变更面：(1) `_seed_models_cache(self, agent, model)` 重构为
  `(self, home: Path, model)`，函数体除 `agent.home`→`home` 外逐字不变（语义零变化）；persistent
  调用点（codex.py:3557）适配为 `agent.home`；(2) child builtin 子分支（`_formal_codex_builtin_config_
  lines(child_model_override)` 之后）新增唯一一行种子调用。外测 credential child 分支、非 formal、
  deepseek 路径均未触碰；无建模语义/账本/acceptance 表面变化。`process_factory` 为既有构造器 seam
  （codex.py:1109-1115，本 commit 未新增）。
- 独立 child 路径探针（PASS，一次性脚本已删除；12/12 断言）：真实
  `_launch_acceptance_child_impl`（formal builtin luna 绑定走**真实** `openai-luna-medium` 投影，
  未 monkeypatch binding），`process_factory` sentinel 阻断于二进制 spawn：
  - builtin child：child home 落 `models_cache.json`——models 与 snapshot 逐字相等（etag 逐字）、
    `client_version` `0.147.0`、`fetched_at` 距 now <0.1s、slug 集含 `gpt-5.6-luna`、mode `0600`；
    child config.toml 投影 `openai`/`gpt-5.6-luna`。
  - external-credential 绑定（`deepseek-direct`）：child home 不落任何 cache，config 非 builtin
    `openai`。
- 回归（PASS）：全量 `env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest
  modeling_team/tests/ -q` → **897 passed, 1 skipped, 293 subtests passed（45.53s）**（较 Round 5 增 3
  tests 即修复新增）；`python -m compileall modeling_team/` OK；`ruff check modeling_team/ --config
  backend/pyproject.toml` All checks passed；`git diff --check`/`git diff --cached --check` 干净。
- 账本/证据 hygiene（PASS）：`.r2-3-008-start-ledger.jsonl` 仍恰 6 事件（3× `reservation` + 3×
  `presemantic_release`，零 `semantic_start`，预算 0/3 消耗、3/3 未动）；`.r2-3-002/003/005-start-
  ledger.jsonl` sha256 与 Round 1–5 记录逐字节一致（`bef7e8be…f632`/`af64172…0dcc`/`328d10d…9ae2`）；
  `git status --short workspaces/ backend/ frontend/` 为空。
- 缺陷：无新增；**R5-D1 FIXED**。
- 结论：**Round 5（续）PASS——R5-D1 关闭**。formal builtin 投影下 persistent role 与 fresh Examiner
  child 两类 agent home 均获种子覆盖，start3 缺陷的残余暴露面清除；全量回归与账本 hygiene 全绿。
  **测试角度 start4 障碍已全部清除**（剩余不确定性仅为 codex 0.147.0 server 侧未观测面，非本轮可测）。
  测试后删除全部临时探针与 `/tmp/r5d1probe`。

**start4（同日，Round 5 续 PASS 后）**：

- Stable state：commit `fd5e23d`（`aee472b` 修复 + Round 5 续文档）。freeze → reservation 20:04:31Z。
- 结果：**models-refresh 竞态修复实证生效 + RPC message 保留修复立即兑现诊断价值**——coordinator 与
  modeling 完整 `thread/start`（thread_id 在位）；protocol `thread/start` 失败但这次保留了完整 message：
  `app-server thread/start failed (rpc_error, code=-32603): error creating thread: Fatal error: Failed to
  initialize session: required MCP servers failed to initialize: ontology_platform: No such file or
  directory (os error 2)`。零模型 turn、账本 `reservation → presemantic_release`，**仍 0/3 消耗**。
- 诊断：protocol 角色专属 `ontology_platform` MCP（`protocol_mcp_launch.py`：command
  `/backend/.venv/bin/python`、cwd `/backend`、`required = true`）在 bwrap namespace 内 spawn 失败
  ENOENT。`namespace_command` 对 protocol 已 ro-bind `/backend/app`、`/backend/.venv` 与 resolved
  interpreter root；0.147.0 对 required MCP 的初始化失败由旧版的容忍/延迟变为 `thread/start` 即致命。
  Round 4/5 的离线复现使用通用 config（未含 protocol 专属 MCP 块），故该缺陷逃过复测——developer
  复现面缺口的教训记入本轮。start3 protocol 失败很可能同因（当时 message 被丢弃）。
- Cleanup：state `CLEANED`、owned Project/Ontology 删除（residual 全零）、admin key `ceb074e5…`
  revoke（复验 401）。账本 8 事件（4× reservation + 4× presemantic_release），零 `semantic_start`。
- 结论：runtime/infrastructure（0.147.0 将 required MCP 初始化失败升级为 thread/start 致命 + protocol
  MCP 在 namespace 内 ENOENT 待定位），按 §4 R8 回 developer：以**真实 protocol 角色 config**（含
  ontology_platform MCP 块）离线复现定位 ENOENT 并窄修复；复测通过后再决定下一 start（预算 3/3 未动）。

### Round 6（2026-08-18，start4 protocol MCP ENOENT 缺陷修复复测）

- Stable state：`de21109` 之上未提交工作树——`modeling_team/runtimes/codex.py` 修改（+70/−21）与新测试
  `modeling_team/tests/test_r23008_protocol_interpreter_namespace.py`（3 tests）；主代理已独立复跑全量
  900 绿。测试者为独立 requirement_tester，未参与修复；工作树保持未提交交主代理 review。零真实 run、
  零真实账本写入、零模型调用、零 codex/app-server 驱动（探针在 bwrap 内只 exec 探针 payload）；未读取/
  记录任何真实 `auth.json`/token（探针 host auth 为自造 `{}`，`protocol_key` 为自造 probe 值）；
  start4 run root 仅只读引用，零修改。
- 范围：start4 缺陷（protocol `ontology_platform` MCP 在 bwrap 内 `execve` ENOENT → 0.147.0 升级为
  `thread/start` 致命 -32603）修复的独立复测——实现审查 + 真实 protocol config × 真实 bwrap 行为探针
  （pre-fix 复现 / post-fix 恢复）+ 全量回归 + 账本 hygiene + 残余观察项评估。
- 实现审查（PASS）：
  - 工作树 diff 恰 2 文件（`codex.py` + 新测试），`git status --short` 无其他；零 `backend/`/`frontend/`
    改动（重启门未触发）；`protocol_mcp_launch.py` 及建模语义/账本/acceptance 表面零改动；MCP 块
    `required=true` 语义未动。
  - 变更面：`namespace_command` protocol 分支的 inline interpreter 绑定（旧 21 行）替换为
    `_protocol_interpreter_mounts()`（codex.py:3677-3743）；`namespace_command` 其余部分（base mounts、
    其他角色、mechanics contract/retrieval/candidate gate/reasoner binds）逐字不变；唯一调用点在
    `agent.package.role == "protocol"` 分支。
  - 语义审查：helper 以 fully-resolved runtime root 起步，沿 `backend/.venv/bin/python` 符号链逐跳
    （visited 防环、≤8 跳），对每个**绝对** target 的 `<target>/..`.. 即解释器 prefix 绑定于其自身路径；
    相对 target 落在已绑 venv 内不额外绑；`--dir` 祖先点先于任何 subtree bind 发出（`preexisting`
    基础 bind 覆盖的祖先不重复建）；与旧代码相比新增的唯一有效 bind 是字面绝对 target prefix。
- 独立行为探针（PASS，一次性脚本已删除；13/13 断言）：真实 `_write_config`（formal R2.3-008 + 真实
  `openai-luna-medium` 投影）产出 protocol config，真实 `namespace_command`（protocol 分支、真实 bwrap
  二进制、真实 `/backend/.venv` 与 uv 解释器布局，零模型调用）：
  - config 面：`mcp_servers.ontology_platform` 精确为 `command="/backend/.venv/bin/python"`、
    `cwd="/backend"`、`args=["-m","app.mcp.server"]`、`required=true`；model trio `gpt-5.6-luna`/`openai`；
    protocol home 同步落种子 `models_cache.json`（mode 0600，Round 5 修复回归通过）。
  - 宿主事实：`backend/.venv/bin/python` 为绝对符号链（目标
    `…/uv/python/cpython-3.14-linux-x86_64-gnu/bin/python3.14`，未版本化目录本身又是符号链），
    与 fully-resolved 路径（cpython-3.14.3-…）不同——与 developer 根因诊断一致。
  - (a) pre-fix 形状（post-fix mounts 精确去掉未版本化 prefix 的 ro-bind 三元组）：namespace 内
    `/backend/.venv/bin/python` exec 失败 `rc=127 / not found`（ENOENT），字面 target 在 ns 内不存在
    （`test -e` 失败）——独立复现 start4 缺陷签名。
  - (b) post-fix：字面 target 在 ns 内存在；MCP spawn 命令原样 exec 成功（`PY_OK`）；于 MCP cwd
    `/backend` + config PYTHONPATH 下 `import app.mcp.server` 成功（`MCP_OK`）——`thread/start` 前
    required MCP spawn 的 ENOENT 面消除（spawn 等价链路闭合；完整 app-server 握手按 §4 归 start5）。
- 回归（PASS）：全量 `env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest
  modeling_team/tests/ -q` → **900 passed, 1 skipped, 293 subtests passed（44.84s）**（较 Round 5 续增 3
  tests 即修复新增）；`python -m compileall modeling_team/` OK；`ruff check modeling_team/ --config
  backend/pyproject.toml` All checks passed；`git diff --check`/`git diff --cached --check` 干净。
- 账本/证据 hygiene（PASS）：`.r2-3-008-start-ledger.jsonl` 恰 8 事件（4× `reservation` + 4×
  `presemantic_release`，零 `semantic_start`，预算 0/3 消耗、3/3 未动）；`.r2-3-002/003/005-start-
  ledger.jsonl` sha256 与 Round 1–5 记录逐字节一致（`bef7e8be…f632`/`af64172…0dcc`/`328d10d…9ae2`）；
  `git status --short workspaces/ backend/ frontend/` 为空；start4 run root 零修改（只读）。
- 复现覆盖教训核验（held）：本轮独立探针从**真实 protocol 角色 config**（含 ontology_platform MCP 块
  与真实符号链布局）驱动，修复前签名（ENOENT）与修复后恢复均在真实面闭合——Round 4/5 用通用 config
  逃过该面的缺口未再发生；developer 新测试亦以真实 repo root + 真实 venv 断言 bind 面（3 tests），非
  仅 mock。
- 残余观察项评估（developer 记录：protocol 握手期间仍有一条 tolerated
  `failed to refresh available models: timeout waiting for child process to exit`，非致命）：判定为
  **可接受残余，非覆盖缺口**——(1) 结果为 tolerated 回退且 `thread/start` 成功，说明种子 cache 命中
  生效于致命路径；(2) 该条说明 0.147.0 另有一条仍走 refresh 的 models 查询面（种子未覆盖全部查找
  路径），但其失败结局已被实证为容忍路径，不触及 §4 R1–R5 路由/终态完成门；(3) start5 证据阅读时
  应把该 ERROR 行与真致命失败区分（记录为观察项，不阻断）。若未来某 start 中该面致命化，按新缺陷
  单独定层处理。
- 缺陷：无新增；start4 protocol MCP ENOENT 缺陷判 **FIXED**（pre-fix 复现 + post-fix 恢复 + 根因
  符号链事实三方闭合）。
- 结论：**Round 6 PASS——start5 障碍清除**。窄修复面（protocol 分支 mount 构造唯一改动 + 3 回归
  测试）与根因完全对应；全量 900 绿、compile/lint/diff 全过、账本与历史证据零改动。测试角度建议
  主代理 review 后提交工作树、按 §4 冻结要素启动 start5（授权预算 3/3 未动、0/3 已消耗）。测试后
  删除全部临时探针与 `/tmp/r6probe`。

**start5（同日，Round 6 PASS 后）**：

- Stable state：commit `3a2289f`（缺陷 3 修复 + Round 6 文档）。freeze `2026-08-17T20:33:22Z` → reservation
  `20:33:26Z`（4s）→ **`semantic_start` `20:33:30Z`——本需求首次消耗 semantic start（1/3）**。四缺陷修复
  全部实证生效：六角色无 configWarning、models cache 命中（`using cached models for OnlineIfUncached`，
  cache 命中日志在位）、四 persistent 角色完整 `thread/started`（含 protocol——缺陷 3 修复在线生效）、
  各角色 `turn/started` 且 span 显示 `model=gpt-5.6-luna reasoning_effort=medium`——**Luna 路由投影在
  真实 turn 上生效**。
- 结果：**首个模型 turn 层失败（semantic 阶段）**——四角色 sampling 请求全部
  `stream disconnected … sampling_error=request timed out`（5/5 重试 + `falling back to HTTP` 后再超时），
  analytics POST 与 forced-online models GET 同样超时；coordinator `llm-inactivity-timeout`，
  `terminal_failure`（`runtime/infrastructure`，`complete_modeling_quality_result=false`）20:38:47Z。
  账本 11 事件（4 组 presemantic + reservation + semantic_start + terminal_failure），**1/3 消耗，2 剩余**。
- 根因（主代理定位，三层证据闭合）：Host egress 必须经本地代理（`http_proxy/https_proxy =
  http://127.0.0.1:1080`；主代理实测 direct curl chatgpt.com 挂起 124s+、via proxy 0.58s 返回）。
  `_minimal_codex_process_env`（codex.py:371）构造显式最小 env（CODEX_HOME/HOME/PATH/TERM/LANG/LC_ALL，
  deepseek key 仅非 formal）**不含代理变量**；bwrap 共享网络命名空间、代理可达，但 codex `ReqwestDefault`
  出站策略在无代理 env 时直连 → chatgpt.com 全部出站请求网络层超时。同因解释 Round 6 记录的"残余
  refresh timeout 观察项"（forced-online GET 同样超时）与 analytics 失败——非独立缺陷。
- Cleanup：runner 完整 cleanup（scope `deleted-empty`、owned Project/Ontology 删除 residual 全零、
  project-scoped key 与 protocol key revoked、runner 自建 admin key 自 revoke）；主代理 temp key
  `4ef586d3…` revoke（复验 401；误建的重复 key `admin-2` 已先行 revoke）。state `TERMINAL_REPORT_COMPLETE`，
  run root 零残留完整保留。
- 结论：runtime/infrastructure（namespace 出站代理环境缺失），按 §4 R8 回 developer 窄修复
  （`_minimal_codex_process_env` 透传 host 代理变量），复测后决定 start6（预算 2/3 剩余）。

### Round 7（2026-08-18，start5 proxy egress 缺陷修复复测）

- Stable state：`93640b6` 之上未提交工作树——`modeling_team/runtimes/codex.py`（+21）、
  `modeling_team/tests/test_r23005_b_runtime.py`（+20/−1）、新 `modeling_team/tests/
  test_r23008_codex_proxy_env.py`（5 tests）；主代理已独立复跑 905 绿并 review diff。测试者为独立
  requirement_tester，未参与修复；工作树保持未提交交主代理 review。零真实 run、零真实账本写入、零模型
  调用、零 chatgpt.com/任何外网接触（探针纯 env 构造 + sentinel process_factory）；未读取/记录任何真实
  `auth.json`/token。
- 范围：start5 缺陷（`_minimal_codex_process_env` 剥离宿主 proxy 变量 → 本机仅能经
  `http://127.0.0.1:1080` 出网，四角色 sampling/analytics/models 请求全部网络层超时；消耗首个 semantic
  start 1/3）修复的独立复测——实现审查 + 独立 env 行为探针 + loopback 安全推理 + 全量回归 + 账本
  hygiene。
- 实现审查（PASS）：工作树 diff 恰 3 文件（helper 改动 + 两个测试），零 `backend/`/`frontend/`；产品面
  变更仅 `_PROXY_ENV_KEYS` 元组（http(s)_proxy/no_proxy 双大小写 6 键）+ `_minimal_codex_process_env`
  内一个条件转发循环（`if value:` 空值不转发、仅这 6 键、其余任何宿主变量不穿越）；DEEPSEEK
  api_key 分支与非 formal 路径逻辑逐字不变；两个真实调用点（`_start_process` codex.py:3973 与
  `_launch_acceptance_child_impl` codex.py:2449）本就流经同一 helper，无第二 env 构造面。
- 独立 env 行为探针（PASS，一次性脚本已删除；15/15 断言）：
  - (a) 真实宿主 env（本机实际设置 `http_proxy`/`https_proxy=http://127.0.0.1:1080`、
    `no_proxy=localhost,127.0.0.1,::1`）：post-fix 精确转发该三键、keyset 恰为 base 6 ∪ 已设 proxy 键；
    pre-fix 形状（去掉 proxy 键）下宿主已设的 proxy 被剥离——env 层复现 start5 缺陷根因面。
  - (b) 模拟无 proxy 宿主：keyset 精确等于 base 6（不发明任何默认值）。
  - (c) 空值宿主（`http_proxy=""`/`NO_PROXY=""`）：不转发、keyset 仍 base 6。
  - 泄漏面：宿主设置 `DEEPSEEK_API_KEY`/`OPENAI_API_KEY`/自造随机变量均不进入 env；formal 模式无
    DEEPSEEK 键；非 formal（api_key 参数）恰增 DEEPSEEK 一键。
  - 双大小写混合：恰转发"实际已设"的键（本探针实测 5 键形态），不增不漏。
  - 调用点级（sentinel process_factory）：persistent `_start_process`（formal coordinator，真实
    `_write_config` 后）与 Examiner-child `_launch_acceptance_child_impl` 两条路径捕获的 spawn env 均
    携带真实宿主 proxy 三键且无 DEEPSEEK 键。
- Loopback 安全推理（PASS，代码/逻辑级零网络）：转发的 `no_proxy=localhost,127.0.0.1,::1` 与 proxy
  变量同入 minimal env——`127.0.0.1:8001`（in-namespace `ontology_platform` MCP 的 httpx 目标，按
  host 匹配不受端口影响）、`localhost:5434`（DB）、`::1` 均命中排除表保持直连；reqwest（codex 出站）
  与 httpx（平台 MCP）均读双大小写 env。宿主实际 env 已含该排除表，与转发行为闭合。观察项（非缺陷）：
  若未来宿主只设 proxy 不设 `no_proxy`，reqwest 默认不豁免 loopback——本宿主不构成该形态，且宿主 env
  是唯一权威源。
- 回归（PASS）：全量 `env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest
  modeling_team/tests/ -q` → **905 passed, 1 skipped, 293 subtests passed（44.97s）**（较 Round 6 增 5
  tests 即新回归 + `test_r23005_b_runtime` 精确等值断言改为 host-independent 固定注入双大小写 proxy
  键）；`python -m compileall modeling_team/` OK；`ruff check …` All checks passed；
  `git diff --check`/`--cached --check` 干净。
- 账本/证据 hygiene（PASS）：`.r2-3-008-start-ledger.jsonl` 恰 11 事件——5× `reservation` + 4×
  `presemantic_release` + 1× `semantic_start` + 1× `terminal_failure`（start1–4 各
  reservation+presemantic_release；start5 reservation+semantic_start+terminal_failure），零额外事件，
  **semantic start 预算 1/3 已消耗、2/3 剩余**；`.r2-3-002/003/005-start-ledger.jsonl` sha256 与 Round
  1–6 记录逐字节一致（`bef7e8be…f632`/`af64172…0dcc`/`328d10d…9ae2`）；`git status --short
  workspaces/ backend/ frontend/` 为空。
- 缺陷：无新增；start5 proxy 剥离缺陷判 **FIXED**（env 层 pre/post 对照 + 双调用点 spawn env 捕获
  闭合；出网连通性本身不在本轮可测面——本机直连被墙、经 proxy 可达的宿主事实由主代理 start5 证据与
  修复前 5/5 重试超时记录反向印证）。Round 6 记录的"tolerated models-refresh timeout"残余观察项随之
  归因于同一 proxy 根因（该 refresh 走直连超时后被容忍），修复后预期消失——start6 证据阅读时验证。
- 结论：**Round 7 PASS——start6 障碍清除**。窄修复面（单 helper 6 键条件转发 + 测试）与根因对应，
  全量 905 绿、compile/lint/diff 全过、账本与历史证据零改动。测试角度建议主代理 review 后提交工作树、
  按 §4 冻结要素启动 start6（预算 2/3 剩余）。测试后删除全部临时探针与 `/tmp/r7probe`。

**start6（同日，Round 7 PASS 后）**：

- Stable state：commit `e2ad607`（proxy 修复 + Round 7 文档）。freeze → reservation 20:50:03Z →
  **`semantic_start` 20:50:07Z——第二次消耗 semantic start（2/3）**。
- 结果：**proxy 修复实证生效 + tool 执行层新缺陷（defect 5）**——四角色零
  `request timed out`/`stream disconnected`（Round 6/7 记录的"残余 refresh timeout 观察项"按
  Round 7 预判消失）、models GET 200 OK、`sse::responses` websocket 流事件持续、
  `turn/started` span `model=gpt-5.6-luna`；但 codex 0.147.0 每个 tool/shell call 需 spawn 伴生
  二进制 `codex-code-mode-host`，namespace 仅挂 `codex` → 全部 tool call 返回
  `failed to spawn code-mode host /agent/bin/codex-code-mode-host: No such file or directory
  (os error 2)`（rollouts 逐角色 6/7/5/1 命中），四角色 Blocked 终答，runner 无 watchdog 挂起
  ~4h，主代理 SIGINT 终止。
- Cleanup：SIGINT graceful cleanup 完整（state `CLEANED`、scope 删除零残留、runner key 自
  revoke、temp key revoke 复验 401）。**账本闭合缺口**：SIGINT 路径不写 terminal_failure，而
  `_reserve` 要求最新 semantic_start 闭合——主代理以窄恢复脚本（真实 `StartLedger` API、写前
  断言、镜像 start5 事件形状）追加恰一条 `terminal_failure`（runtime/infrastructure），strict
  replay 复验通过。账本 14 事件，2/3 消耗、1 剩余。
- 结论：runtime/infrastructure，按 §4 R8 回 developer 窄修复（`namespace_command` 挂载
  codex-code-mode-host；宿主 release bin 目录已核实仅 codex + codex-code-mode-host 两文件）；
  复测后 start7（最后 1 start）。

### Round 8（2026-08-18，start6 codex companion ENOENT 缺陷修复复测）

- Stable state：`874304a` 之上未提交工作树——`modeling_team/runtimes/codex.py`（+44，纯新增）与新测试
  `modeling_team/tests/test_r23008_codex_companion_mount.py`（5 tests）；主代理已独立复跑 910 绿并 review
  diff。测试者为独立 requirement_tester，未参与修复；工作树保持未提交交主代理 review。零真实 run、零
  真实账本写入、零模型调用、零 app-server/伴生二进制执行（探针在 bwrap 内仅 test -x/-e/head ELF
  magic）；未读取/记录任何 `auth.json`/token。
- 范围：start6 缺陷 5（codex 0.147.0 tool/shell 执行 spawn 伴生二进制 `codex-code-mode-host`
  （argv[0]-相对解析），namespace 只挂 `codex` → 每个 tool call
  `failed to spawn code-mode host … (os error 2)`，四角色 Blocked、runner 死锁 4h；2/3 消耗）修复的
  独立复测——实现审查 + 真实 namespace 构造 × 真实 bwrap 行为探针 + 降级形状 + 全量回归 + 账本
  hygiene（含 recovery 闭合复验）。
- 实现审查（PASS）：diff 恰 2 文件，零 `backend/`/`frontend/`；产品面纯新增——`_codex_companion_binary()`
  （解析 codex resolved 二进制同目录伴生文件；lstat 拒 symlink/非 regular，`os.access X_OK` 拒不可执行，
  失败一律 `None` 降级）+ 两个挂载点的纯附加 bind：`namespace_command` persistent 分支（splice 进
  `--chdir` 插入序列、codex bind 紧后）与 `_acceptance_namespace_command`（bwrap `--` 分隔符前）。
  companion 缺失时两个 namespace surface 与 pre-fix 逐字节同形（分支加空列表）；`use_bwrap=False`
  两条早退路径未触碰；MCP/语义/账本表面零改动。
- 独立行为探针（PASS，一次性脚本已删除；20/20 断言，真实 `namespace_command`（coordinator，真实
  codex/companion 宿主布局）+ 真实 `_acceptance_namespace_command`（child）× 真实 bwrap）：
  - 宿主事实：companion 于真实 codex resolved bin 目录（`~/.codex/packages/standalone/releases/
    0.147.0-x86_64-unknown-linux-musl/bin/`），regular+exec、非符号链——与 delivery record start6 条目
    一致。
  - persistent pre-fix 形状（post-fix mounts 精确移除 companion ro-bind 三元组）：ns 内 `test -e` 失败、
    exec rc=127 "not found"（ENOENT）——独立复现 start6 签名；post-fix：companion 在 ns 内存在且
    可执行（`test -x/-f`）、ELF magic `7f454c46`（execve 可装载）。
  - child 同构：pre-fix ns 内不存在、post-fix 存在可执行；两挂载点 bind 均在 `--` 分隔符前。
  - 降级形状：scratch bin 无 companion → helper `None`，persistent/child 两条 command 零 companion
    token、codex bind 与 exec payload（`--` 后首参 `/agent/bin/codex`）不变——与 pre-fix surface 逐字节
    同形；symlinked companion 与非可执行 companion 均被拒（`None`）。
- 回归（PASS）：全量 `env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest
  modeling_team/tests/ -q` → **910 passed, 1 skipped, 293 subtests passed（45.55s）**（较 Round 7 增 5
  tests 即修复新增）；`python -m compileall modeling_team/` OK；`ruff check …` All checks passed；
  `git diff --check`/`--cached --check` 干净。
- 账本/证据 hygiene（PASS）：`.r2-3-008-start-ledger.jsonl` **恰 14 事件**——6× `reservation` + 4×
  `presemantic_release` + 2× `semantic_start` + 2× `terminal_failure`（start1–4 各
  reservation+presemantic_release；start5/6 各 reservation+semantic_start+terminal_failure），与
  delivery record 全历史逐条对应；**以真实 `StartLedger`（`resolve_ledger_config("R2.3-008")`）对
  `_records()` 只读复验 `_validate_strict_replay` 接受**——Delivery-Agent recovery 追加的 start6
  `terminal_failure`（`classification=runtime/infrastructure`、
  `complete_modeling_quality_result=false`、`repair_baseline_hash=None`）闭合有效，start7 预算门解锁；
  **2/3 已消耗、1 剩余**；`.r2-3-002/003/005-start-ledger.jsonl` sha256 与 Round 1–7 记录逐字节一致
  （`bef7e8be…f632`/`af64172…0dcc`/`328d10d…9ae2`）；`git status --short workspaces/ backend/
  frontend/` 为空。
- 缺陷：无新增；start6 companion ENOENT 缺陷判 **FIXED**（pre-fix ns 内 ENOENT 复现 + post-fix
  companion 在 ns 内存在/可执行/ELF 装载 + 降级同形三方闭合；真实 tool spawn 行为按 §4 归 start7 在线
  验证）。
- 结论：**Round 8 PASS——start7 障碍清除**。纯附加窄修复面与根因完全对应，全量 910 绿、compile/lint/
  diff 全过、账本 recovery 闭合只读复验通过、历史证据零改动。测试角度建议主代理提交工作树后按 §4
  冻结要素启动 start7（**最后 1 个 semantic start，预算 1/3 剩余**）。测试后删除全部临时探针与
  `/tmp/r8probe`。

**start7（同日，Round 8 PASS 后）**：

- Stable state：commit `e848999`（defect 5 修复 + Round 8 文档）。freeze/reservation 01:09:25Z →
  **`semantic_start` 01:09:29Z——第三次消耗 semantic start（3/3，首批预算耗尽）**。
- 结果：**全链修复实证生效 + candidate 注册层类型合同失败（defect 6）**——零出站超时，六角色
  工具/transport 真实执行（defect 5 companion 修复在线实证：deliveries 6、elicitations 9、
  capability calls），完整 formal candidate（整数 `candidate_revision: 1`）通过 candidate gate
  后在 `register_accepted_candidate`（acceptance.py:1743 `_safe_id`，非 003 task 仅接受小写字符串）
  以未类型化错误终止整个 run。根因为三层 revision 类型合同不一致（envelope 校验接受正整数或
  字符串 / modeling 指令 R2.3-003 小节要求整数而通用小节无类型约束、示例为字符串 / 注册层仅
  字符串）。定层 platform-contract。
- Cleanup：state `CLEANED`、acceptance aborted/zero_child_residue、全部 key non-active、temp
  key revoke 复验 401；`secret_audit match_count=3` 经 digest-only 扫描证实保留产物 0 个 Host
  凭据 plaintext 命中（同 start1 观察项形态）。账本经 Delivery-Agent recovery 闭合
  terminal_failure（platform-contract），strict replay 复验通过；17 事件，3/3 消耗。
- 结论：按 §4 R8 回 developer 窄修复（统一 revision 类型合同）；**start8 需新用户 budget 授权**
  （首批 3 start 已耗尽），修复复测后向用户请求。

### Round 9（2026-08-18，start7 candidate_revision 类型合同缺陷修复复测）

- 测试对象：defect 6（platform-contract）修复 — 三方 candidate_revision 类型合同统一
  （delivery gate / runner / acceptance registration）。工作区 `4e546e6` 未提交树
  （7 个修改文件 + 新增 `modeling_team/tests/test_r23008_revision_type_contract.py`），
  全部位于 `modeling_team/`；`acceptance.py` 未被修改。
- 实现审查：`candidate_progress.py` 新增 `_SAFE_REVISION_RE = re.compile(r"[a-z][a-z0-9-]{1,127}")`
  与 `_validate_task_revision`；`_new_pending` 在 latch `self.pending` 之前调用（拒绝时零状态残留）；
  `integer_revisions: bool = False` 构造参数由 `runner.py` 以
  `requirement_id == "R2.3-003"` 门控传入（与相邻 `allow_post_receipt_revision` 同信号）；
  `_revision_is_newer` 扩展为字符串字典序严格递增（纯数字字符串数值比较）；003 整数语义保留。
  经 grep+直接导入验证 `_SAFE_REVISION_RE.pattern` 与 `acceptance._safe_id`
  （`re.fullmatch(r"[a-z][a-z0-9-]{1,127}", value)`, acceptance.py:359）逐字符一致。
- 行为探针（独立脚本，非开发者测试复用；零真实运行/账本/模型调用）：
  - (a) 非 003 门整数 revision（`1`）首次交付即抛 typed `FormalCandidateError`，
    消息含 `[a-z][a-z0-9-]{1,127}` 与 `R2.3-003`；`progress.pending is None`、identity 未设。
  - (b) 安全字符串 `rev-1` 通过 gate（`identity.candidate_revision == "rev-1"`）并端到端通过真实
    `RunnerAcceptanceCarrier.register_accepted_candidate`（临时目录，已清理）；registration 仍拒绝
    整数（`safe stable identifier`，AcceptanceContractError）— 上游未被放宽。
  - (c) `integer_revisions=True` 接受整数 `1`（003 路径）；同一开关下安全字符串仍被 envelope 容忍（超集不回归）。
  - (d) `_revision_is_newer`：字符串字典序严格递增（`rev-1`→`rev-2` True、`rev-2`→`rev-10`
    False 即定义的字典序规则）；纯数字字符串数值比较（`9`→`10` True、`10`→`9` False）；
    int-int 不变（1→2 True、2→2 False）；相等/不增拒绝；bool 与 str/int 混型一律 False。
  - (e) 不安全值全部 typed 拒绝：`Rev-1`、`rev 1`、`""`、`"1"`、`rev_1`、单字符、129 字符、
    128 字符（上界排他）、非 ASCII、`None`、`[]`、`{}`、`0`、`-1`、`1.5`、`True`；
    边界 2 与 128 字符接受。36/36 断言通过（其中 regex 同步断言经直接 pattern 比较二次确认）。
- 错误路径验证：`runner.py:3978-3982` drain 的 `except FormalCandidateError` 捕获点为 `4e546e6`
  既有代码（与其他 malformed envelope 完全同路径）；行为探针经 minimal stub 调用真实
  `TeamRunner._latch_formal_candidate_failure("modeling-quality", "candidate-envelope-invalid")`，
  确认状态 `TERMINAL_FAILURE_PENDING_CLEANUP` + evidence `formal-candidate-terminal-failure`
  （classification/reason_code/cleanup_required）+ `record_terminal_failure` 幂竭（首 latch 生效）。
  失败由 start7 的注册期无类型 run-kill 前移到首次交付的 typed 分类路径。
- 回归：`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. ... -m pytest modeling_team/tests/ -q`
  → **916 passed / 1 skipped / 302 subtests passed**（45.63s，与 R8 基线一致）；
  `compileall -q modeling_team/` OK；`ruff check modeling_team/ --config backend/pyproject.toml`
  OK；`git diff --check` / `--cached --check` 干净。
- 账本/证据卫生：`.r2-3-008-start-ledger.jsonl` 恰 17 事件
  （7 reservation + 4 presemantic_release + 3 semantic_start + 3 terminal_failure，3/3 消耗）；
  `.r2-3-002/003/005-start-ledger.jsonl` sha256 与冻结值逐一相等；`workspaces/ backend/ frontend/`
  零修改；本轮探针临时文件（/tmp/r9probe）已删除。
- 结论：defect 6 修复 **PASS**，无新缺陷。R2.3-008 到达"合同统一后可重新进入真实建模"状态；
  **start8 需新用户 budget 授权**（首批 3 start 已耗尽）。建议 coordinator 提交本修复后向用户请求授权。

**start8（同日，用户追加授权 3 start 后）**：

- Stable state：commit `a383e03`（budget_authorization `r2-3-008-budget-20260818-2`）。freeze/reservation
  07:25:39Z → **`semantic_start` 07:25:43Z（4/6 消耗）**。
- 结果：**全栈路由健康 + 未回答 outer question 环形等待死锁**——六轮修复全部在线实证（四角色
  thread/started、零出站超时、companion 在位、真实 Luna turn）；semantic_start 后 15s modeling 经
  Team Transport 发出 grounded clarification question（切片源材料留白的 B/C 无分数行为点），
  coordinator 转述 outer 后四角色环形等待，deliveries 停在 5、零 candidate，挂起 ~3h，主代理
  SIGINT 终止。runner 的 outer-input FIFO（`--enable-outer-input-fifo`，为 background Host 设计）
  为 opt-in 且未启用；runner 对 pending outer question 无 timeout——headless run 中问题永远无法
  被回答。
- 定层：**runtime/infrastructure**（问题为 contract-permitted，失败在 headless 运行缺少应答通道 +
  无超时，start6 无-watchdog 同族）。
- Cleanup：state `CLEANED`、scope `deleted-empty`、residual 全零、全部 key non-active；temp key
  revoke 复验 401；digest-only 扫描 761 保留文件对 host auth 值 0 plaintext 命中。账本经
  Delivery-Agent recovery 闭合 terminal_failure（runtime/infrastructure），strict replay 复验通过；
  21 事件，4/6 消耗。
- 结论：无代码缺陷；start9 追加 `--enable-outer-input-fifo`，outer question 出现时呈报用户
  （owner）决策，不代答业务语义。授权余量 2 start 内继续。

**start9（2026-08-18/19，FIFO outer-input 首次启用）**：

- Stable state：commit `92ecf79`。freeze 10:31:13Z → **`semantic_start`（5/6 消耗，1 剩余）**；
  启动命令追加 `--enable-outer-input-fifo`。
- 结果：**FIFO outer 应答闭环实证 + protocol receipt 二次构建死锁（defect 7）**——两个 outer
  question（B 消费 C 版本→用户确认 Version 2/quality_rating；B 无分数行为→按 005 基线 owner answer
  原文回传 preserve-explicit-unknown）均经 FIFO 送达并成为 candidate 证据；完整 formal candidate
  `r23008-candidate-1` 过 gate。protocol 手写回复 delivery-11 被 formal 验证拒绝 → redrive；protocol
  capability 构建 typed receipt 成功后 5s 二次调用被幂等拒绝（"typed candidate response was already
  built"），可行动诊断被 opaque -32001 遮蔽 → protocol 升级 issue-1 并弃置已持有 receipt；
  guidance 恢复后 redrive turn 已结束 → `candidate-redrive-exhausted` typed terminal failure
  （collaboration/routing，runner 自写账本）。
- Cleanup：state `CLEANED`、scope `deleted-empty`、residual 全零、key 全 non-active；temp key
  revoke 复验 401；digest-only 扫描 782 文件 0 plaintext 命中。账本 24 事件，5/6 消耗。
- 结论：FIFO 机制闭环（start8 死锁面解除）；defect 7 回 developer 窄修复（重复 receipt 构建的
  幂等/结构化诊断面），Round 10 复测后决定最后 1 个 start。

### Round 10（2026-08-19，start9 defect 7 receipt 二次构建 opaque 拒绝窄修复复测）

- 测试对象：defect 7（collaboration/routing，含 platform-contract 窄缺口）修复 — 同一
  still-answerable candidate 的重复 `protocol_build_candidate_receipt` 请求由 opaque 拒绝改为
  字节相同幂等 replay。工作区 `32c9b0f` 未提交树，仅 `modeling_team/runner.py`（+38/−6）+
  新增 `modeling_team/tests/test_r23008_receipt_idempotency.py`（5 tests）。
- 实现审查：`_active_protocol_candidate` 新增 keyword-only `idempotent_receipt=False`；
  "already built" 拒绝仅对非 replay 生效，且位于既有 conflict/terminal/foreign/paused/state
  检查之后（replay 旁路不能绕过任何前置防御）。`_build_protocol_candidate_receipt` 先读
  replay 标记，replay 时 canonical digest 与已注册 digest 比对，不匹配即抛
  "typed candidate receipt replay is not byte-stable"——该检查在两处状态写入之前（fail-closed，
  零状态突变）。replay 结果标记 `idempotent_replay: True`；startup guidance 增补 replay 语义
  （原样重发 receipt_json、勿据此升级 issue）。
- 新测试评估（5/5 通过，0.10s）：经真实 `RunnerAcceptanceCarrier` capability token 调用真实
  runner builder；test 2 精确复现 start9 序列（build → quarantined 后 pending.state=redrive_sent →
  重复调用 → replay）；test 3/4/5 分别守住 post-conflict、post-terminal、R2.3-003 整数
  revision replay + post-receipt conflict 后拒绝。
- 独立行为探针（15/15 通过，挂真实 R2.3-008 formal contract，非开发者 harness 复用）：
  - (1) 首建无 `idempotent_replay` 标记；redrive 后重复调用 replay 标记为 True、receipt_json
    逐字节相同（len=234）、registry 状态/digest 完好；
  - (2) 篡改已注册 digest → typed "not byte-stable" 拒绝，且 digest/registry 零突变（fail-closed
    时序确认）；(7) digest 注册缺失（del）同样 fail-closed 而非静默重建；
  - (3) foreign/stale delivery_id 在 replay 路径仍拒绝；(4) paused（经 `pause()`）拒绝；
    (5) terminal progress 拒绝；
  - (6) receipt→conflict 单次构建保留，duplicate conflict 与 conflict 后 receipt 均
    "already built" 拒绝——transport 单次接受语义未变。
- 回归：full suite `env -u DEEPSEEK_API_KEY -u OPENAI_API_KEY PYTHONPATH=backend:. ... pytest
  modeling_team/tests/ -q` → **921 passed / 1 skipped / 302 subtests**（与 main agent 复跑一致；
  R9 基线 916 + 新 5）；`compileall -q` OK；`ruff check` OK；`git diff --check` 干净。
- R2.3-003 无回归：003 integer-revision replay 保真（receipt.candidate_revision == 1 字节相同）、
  post-receipt conflict 路径仍可用、其后 receipt 再拒绝；既有 003 conflict 流测试全部在 921 内通过。
- 账本/证据卫生：`.r2-3-008-start-ledger.jsonl` 24 事件
  （9 reservation + 4 presemantic_release + 5 semantic_start + 5 terminal_failure +
  1 budget_authorization；**5/6 消耗，剩 1 start**）——与 start9 记录一致，本轮未触碰；
  002/003/005 sha256 与冻结值一致；`workspaces/ backend/ frontend/` 零修改；
  /tmp/r10probe 探针文件已删除。
- 结论：defect 7 修复 **PASS**，无新缺陷、无回归。修复可提交；消耗最后 1 个 start（start10）
  前 main agent 自行决策（余量 1，无需新授权），按实验规则该 start 应在修复后尽快用于真实建模。

### Round 11 前置记录（2026-08-19，start10 终态：defect 7 修复 live 验证通过，defect 8 击穿）

- start10（6/6 授权 start，freeze 00:06:00Z，FIFO 启用）live 证据：FIFO 外问闭环两次携带转发
  （delivery-4 → C Version 2/quality_rating；delivery-6 → explicit unknown
  unknown-b-no-score-behavior）；完整候选 r23008-candidate-1（29 items）经 formal 验证；
  **defect 7 修复 live 生效**（protocol 重复 `protocol_build_candidate_receipt` → ok=true 幂等
  replay，capability-calls.jsonl 00:08:29/00:08:33 两行）。
- **defect 8（platform-contract，待修复）**：protocol 交付 receipt 后
  `ProtocolRetrievalGate._extract_plan` 因 modeling 将 consumer_query `required_paths` 写成
  路径表达式串（契约与 005 基线为裸谓词局部名）抛错，以 untyped 异常击穿整 run（exit 2），
  无 quarantine/revision/typed 终态。修复后需 Round 11 独立复测：a) 非法 required_paths 走
  typed invalid-response/revision 路径而非 crash；b) 合法裸局部名候选（005 基线格式）retrieval
  gate 全链路不受影响；c) 921+ 回归全绿。
- 账本 27 事件（6/6 消耗），start10 已以 platform-contract 关闭；卫生全零（key revoke+401，
  796 文件 0 命中）。**start11 需用户新授权。**

### Round 11（2026-08-19，start10 defect 8 非法 consumer_query 检索计划 untyped 崩溃窄修复复测）

- 测试对象：defect 8（platform-contract）修复 — start10 中 Modeling 将 `required_paths` 写成
  全路径表达式（`workflow-b--currentlyConsumesOutput-->quality-rating-field`），检索门禁仅在
  accepted-candidate registration 时（Protocol 已交付 receipt 后）拒绝，且
  `ProtocolRetrievalGateError` 以未分类 `run failed:` 退出烧掉整个 run。工作区 `c6df8f1`
  未提交树，仅 `modeling_team/runner.py`（+66/−7）+ 新增
  `modeling_team/tests/test_r23008_retrieval_plan_gate.py`（5 tests）。
- 实现审查：(1) `_build_protocol_candidate_receipt` 在出任何 receipt 前运行与注册时**完全相同**的
  `ProtocolRetrievalGate` 构造（同构造器、同参数——runner.py:2333 与 acceptance.py:1763/1785/1798
  逐参比对一致，candidate 为 `_active_protocol_candidate` 的 deepcopy 等价注册时 detach）；
  拒绝时标记 `receipt_rejected` 并抛 `AcceptanceContractError(data={reason:
  consumer_query_plan_invalid, detail, action})`。(2) conflict 前置集合扩为
  `{"receipt","receipt_rejected"}`，仅放开计划拒绝后的 revision 循环。(3) 
  `_observe_formal_candidate_delivery` 对 `register_accepted_candidate` 加
  `except AcceptanceContractError` → latch `platform-contract/
  accepted-candidate-registration-rejected` + typed `TeamConfigurationError`（防 start10
  手工 receipt 绕过路径）。(4) capability 层既有机制（capability_mcp.py:672-708）：带 Mapping
  `data` 的异常走 success-path `structuredContent {ok:False, error:{...}}`（-32001 仍保留给
  token/schema/dispatch 类失败）——本次修复直接复用，未改 capability 层。
- 新测试评估（5/5 通过，0.11s）：经真实 carrier capability + 真实 capability endpoint
  `tools/call handle()`；test 1 覆盖 path-expression 计划 → 结构化诊断 + 仅 `receipt_rejected`
  标记；test 2 验证 JSON-RPC 层 `{ok:False, error:{reason}}` 且无 error key；test 3/4/5 分别覆盖
  拒绝后 conflict 可用、合法 bare-local-name 全链路（含 defect-7 replay）、start10 手工 receipt
  绕过 → typed TeamConfigurationError + AcceptanceContractError cause + terminal latch。
- 独立行为探针（21/21 通过，挂真实 R2.3-008 formal contract，非开发者 harness 复用）：
  - (1) 非法计划 → `AcceptanceContractError`，data 三字段齐全；`_protocol_candidate_responses`
    恰为 `{delivery-1: receipt_rejected}`、**digest 注册表为空**（未发出任何 receipt）、progress
    未 latch；
  - (2) capability endpoint：无 JSON-RPC error key，`structuredContent {ok:False,
    error:{reason: consumer_query_plan_invalid}}` 直达 Agent（结构化 success path，非 -32001）；
  - (3) 标记不被滥用：计划拒绝后 typed conflict 可用（revision 循环开放），但 duplicate
    conflict / conflict 后 receipt 均 "already built" 拒绝；
  - (4) `receipt_rejected` 标记下 foreign/stale、paused、terminal 仍全部拒绝（marker 无旁路）；
  - (5) 重复 receipt 调用确定性重拒（两次异常与 data 完全相同），永不发出 accepted receipt；
  - (6) 合法 bare-local-name（005 基线形状）在 008 合同下全链路不变：build → register accepted →
    defect-7 replay 字节相同；
  - (7) start10 绕过路径：手工 exact receipt bytes → typed `accepted candidate registration
    failed: ...`（cause 为 AcceptanceContractError）、progress `terminal_failure_latched`、
    `evidence/formal-candidate-terminal-failure.jsonl` 落盘且含
    `"classification": "platform-contract"` 与 `accepted-candidate-registration-rejected`——
    不再是未分类退出。
- 回归：full suite → **926 passed / 1 skipped / 302 subtests**（与 main agent 复跑一致；R10 基线
  921 + 新 5）；`compileall -q` OK；`ruff check` OK；`git diff --check` 干净。`_extract_plan`
  bare-local-name 合同、transport 单次接受、003 专属路径均未改（既有测试全数通过）。
- 账本/证据卫生：`.r2-3-008-start-ledger.jsonl` 27 事件
  （10 reservation + 4 presemantic_release + 6 semantic_start + 6 terminal_failure +
  1 budget_authorization；**6/6 消耗，budget 再次耗尽**）——与 start10 记录一致，本轮未触碰；
  002/003/005 sha256 与冻结值一致；`workspaces/ backend/ frontend/` 零修改；
  /tmp 探针文件（含失败轮次泄漏目录）已全部删除。
- 结论：defect 8 修复 **PASS**，无新缺陷、无回归。修复可提交；**下一 start（start11）需新的用户
  budget 授权**（第二批 6 start 已耗尽）。

### Round 12（2026-08-19，start10 defect 8 配套预防指引轻量复核）

- 测试对象：defect 8 防复发指引（Modeling 可读 surface 固定 consumer_query 计划格式）。工作区
  `3abb692` 未提交树：`modeling_team/agent-packages/modeling/instructions.md`（+7）、
  `modeling_team/references/platform-neutral-candidate-authoring.json`（+6）、新增
  `modeling_team/tests/test_r23008_consumer_query_plan_guidance.py`（2 tests，surface 断言）。
  轻量轮：未重跑深检探针，仅复核指引一致性/中性/放置 + 回归。
- 指引与检索门禁契约一致性：`_extract_plan`（protocol_retrieval_gate.py:298-380）的有效契约是
  每个 `required_paths` 元素须等于同候选内已声明 predicate item 的局部名且解析到连通候选
  binding（`_local_name` 仅取 `#/:"` 分隔的末段；路径表达式/IRI 因不匹配任何声明谓词局部名被
  "no relation/fact predicate"/"no candidate binding" 拒绝）。新指引"exactly equal to the
  declared predicate local name of a predicate item in the same candidate；never a full path
  expression such as subject--predicate-->object, never an IRI"与该有效契约一致；"rejected
  before the candidate receipt is built"对应 R11 已验证的 receipt 前预检；"exactly one complete
  revised candidate"对应 conflict/revision 循环语义。示例 `currentlyConsumesOutput` 与 005 基线
  已接受候选（r23005 continuation exact-candidate）实际使用的谓词局部名一致。
- 中性未破坏：test_r23005_candidate_authoring.py 的禁词扫描（dify/workflow/quality_score/
  quality_rating/expected_answer/project_id/... + `[a-z]->[a-z]` 路径 regex）作用于整个
  reference JSON 文本——新增文案通过（中性示例 `neutralAssociation`，通用
  `subject--predicate-->object` 形式，无场景词）。instructions.md 不在禁词扫描范围（与 defect-6
  先例一致：真实示例进 instructions，中性名进 reference）。该测试含于 928 内通过。
- 放置核对：新增段位于 instructions.md 通用 envelope 约束区（第 ~98-104 行，紧接 defect-6
  revision 合同段之后、任何 item 材料化段之前）；R2.3-003 段自第 220 行始，未被触碰，
  003 候选作者流程无影响。
- 回归：full suite → **928 passed / 1 skipped / 302 subtests**（与 main agent 复跑一致；R11 基线
  926 + 新 2）；`compileall -q` OK；`ruff check` OK；`git diff --check` 干净。
- 账本/证据卫生：`.r2-3-008-start-ledger.jsonl` 28 事件——较 R11 多 1 条 `budget_authorization`
  （`r2-3-008-budget-20260819-3`，+3 starts，用户 2026-08-19 消息授权；semantic_start 仍 6，
  新批次 0 消耗）。该写入为本轮之前 coordinator/Delivery-Agent 所为，非本轮触碰；
  002/003/005 sha256 与冻结值一致；`workspaces/ backend/ frontend/` 零修改；本轮无探针临时文件。
- 结论：预防指引 **PASS**，无缺陷。指引 + R11 门禁 + 结构化诊断构成 defect 8 的完整防线；
  修复与指引可一并提交。新授权 3 start 可用于 start11（建议携带本轮指引生效后的 agent 包）。

### Round 13（start11 live 期间，主代理直接验证——预防指引扩展：shape min_count）

- 触发：start11 issue-3/issue-4 实证——已接受候选 `r23008-candidate-3` 的 shape 路径
  `path-workflow-role` 无 `min_count`，其 `negative_probe`（期望 `rejected`）被平台正确
  `validated`；接受后不可变，运行内不可修复（post-receipt revision 仅 R2.3-003，runner.py:575）。
  与 start10 同构的预防面真空：modeling 可读面从未写明该契约，且中性 reference 示例本身
  复刻了同一不一致。
- 变更面：`modeling_team/agent-packages/modeling/instructions.md`（+8 行 envelope 约束区、
  003 段外）；`modeling_team/references/platform-neutral-candidate-authoring.json`
  （`shape_path_min_count` 规格 + closure_checklist 一行 + 示例路径补 `"min_count": 1`，
  +7/-1）；`test_r23008_consumer_query_plan_guidance.py` 扩为 4 tests（新增 instructions 断言、
  reference 规格断言、"示例 shape 探针路径必须带 min_count"结构断言）。
- 契约一致性核对：`min_count` 语义与 `modeling-batch-item-contract.json:247`（integer、
  optional、compiler 强制 integer）一致；"无 min_count 即无 presence 约束"与平台实测
  （batch `a3164b98…` applied shape + 探针 dry_run validated）一致；探针期望 rejected 需
  min_count 与 005 已接受基线（全部路径 min_count:1）一致。
- 中性未破坏：reference 增量仅中性词；禁词扫描（grep dify|workflow-|quality_rating|
  quality_score|luna）仅命中 instructions.md 既有的 "business" 单词与
  `currentlyConsumesOutput`（R12 已有先例）。
- 回归：目标模块 13/13；full suite **930 passed / 1 skipped / 302 subtests**。7 个
  `test_deepseek_codex_runtime.py` 失败为环境性预存（本 shell `DEEPSEEK_API_KEY=1` 命中，
  resolver 优先 env，fallback 拒绝路径不触发；`git stash` 后 HEAD 同样 7 failed，证实与本轮
  无关；live run 命令一贯 `env -u DEEPSEEK_API_KEY`，不受影响）。
- 结论：**PASS**。预防指引随本轮提交，供 start12+（如启动）携带。

### Round 14（start11 live 期间，主代理直接验证——defect 9：context_truncated 分页误判）

- 触发：start11 issue-6——lexical 链首页 `context_truncated` + 有效 `next_context_cursor`，
  续页至非截断 terminal 页，gate 仍报 `ordinary_retrieval_incomplete`（"blocking warning:
  context_truncated"）两次。
- 修复面：`modeling_team/protocol_retrieval_gate.py` `_validate_response_quality`——
  `context_truncated` 且该页 `context_page.next_context_cursor` 非空时按分页信号跳过；无
  cursor 的 terminal 页命中原 token 检查仍阻塞；`matches_truncated`、hybrid evidence/lineage
  保守契约、cursor 绑定不变式、terminal-page 截断检查全部不变。
- 平台侧证据核对：`semantic_context_query.py` 中 warning 与 `context_page.truncated`/
  `next_context_cursor` 同源同条件（`len(related_raw) > context_limit`），跳过条件与平台语义
  一致；fail-closed（terminal 页带告警仍拒）。
- 测试：`test_r23008_context_truncated_pagination.py` 3/3（含 start11 精确序列：首页
  warning+cursor → 终页无 warning，receipt 注册成功且 artifact_paths=2）；现有
  `test_protocol_retrieval_gate.py` 22/22 无回归；full suite **925 passed / 1 skipped /
  302 subtests**（R13 基线 922+3；仍 7 个与代码无关的 `DEEPSEEK_API_KEY` 环境性失败）；
  compileall OK；ruff OK。
- 结论：**PASS**。修复随本轮提交；live start11 进程不可热载，按 typed terminal failure 收尾
  后由 start12 携带。

### Round 15（start12 终局后，主代理直接验证——defect 10：候选通道非 JSON 中途消息）

- 触发：start12 于 ~3 分钟 typed 失败 `formal candidate delivery is not canonical JSON`；
  modeling rollout line 43 复原致命投递为散文状态消息（等待 owner 澄清答复期间回应
  protocol 启动屏障催交），`observe_delivery` 将其判为初始候选投递后解码失败 run-kill，
  且先于持久化（deliveries.jsonl 仅 6 条）。
- 修复面：`modeling_team/candidate_progress.py` `observe_delivery`——初始/revision 槽位上
  非 JSON/非 dict 文本与"合法 JSON 但非候选形状"同判 `return None`（忽略）；启动屏障/
  redrive 持续催交、conflict 槽保持开放、dispatch deadline 仍约束。revision 非严格更新、
  digest 复用、Runtime attribution 非法等真语义违约 run-kill 语义不变。
  runner.py 侧 `candidate-envelope-invalid` latch 保留（仍覆盖其余 FormalCandidateError
  来源）。
- 测试：`test_r23008_nonjson_candidate_interim_messages.py` 3/3（start12 精确 prose；
  conflict 槽 prose 不消耗且正式 revision 仍接受；裸 JSON 字符串/数字同判）；现有
  candidate_progress 相关测试无回归；full suite **928 passed / 1 skipped / 302
  subtests**（`env -u DEEPSEEK_API_KEY` 下 `test_deepseek_codex_runtime.py` 21/21 全过，
  证实 7 失败纯环境性）。
- 结论：**PASS**。修复随本轮提交，start13 携带。
