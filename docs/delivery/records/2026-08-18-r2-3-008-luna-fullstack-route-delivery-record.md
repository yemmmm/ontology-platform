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

### 2026-08-18 — 实施完成与独立测试 Round 1（R1-D1）— requirement developer/tester

- Evidence: implementation `5d34286`（9 文件：formal_runs/start_ledger/contracts/acceptance 四处身份面 + 三个镜像资产 + 新测试文件）；主代理逐文件 diff 复核镜像最小重绑定、全量 884 passed、validate CLI 六角色
  `openai-codex/gpt-5.6-luna/medium` + `auth_mode=chatgpt-subscription`。独立测试 Round 1：A–E 矩阵全 PASS +
  对抗抽查，但发现 R1-D1（High，矩阵外）——`__main__.py:503-513`、`runner.py:358-367`、`runner.py:1185-1192`
  三处 cross-wire 守卫字面集合未注册 008 身份，008 profile + 非正式 task 静默降级 exit 0（主代理复现确认），
  降级路径会在 R2.3-002 默认账本 reserve。
- Action/decision: R1-D1 accepted-high 回 developer 窄修复。
- Outcome/next step: 修复后 Round 2 复测。

### 2026-08-18 — R1-D1 修复与独立测试 Round 2 PASS — requirement developer/tester

- Evidence: 修复 `a785d1d`——`formal_runs.py` 从闭合注册表派生 `FORMAL_PROFILE_IDS`/`FORMAL_TASK_IDS`，
  三处守卫改用派生集合（未来注册合同自动参与，漂移类缺陷不可复发）+ 3 测试/7 subtests。主代理复核：复现
  命令 exit 2、全量 887 passed/1 skipped/293 subtests、compile/ruff/diff-check 全绿。Round 2 复测：三条守卫
  路径双向 fail closed、005/003 回归同形、E2 真实账本字节不变、被动健康 200/200。
- Action/decision: deterministic 侧关闭；进入 Round 3 真实 Luna formal run 授权冻结。
- Outcome/next step: 冻结授权后启动真实运行。

### 2026-08-18 — Round 3 真实 Luna formal run 授权冻结 — user/main agent

- **Authorization source**：用户 2026-08-17 "同意，授权一次"（Luna 正式运行）+ 2026-08-17/18 载体决策
  （新开正式需求 R2.3-008、复用 R2.3-005 切片、仅路由/终态验收、首批 3 semantic start）。
- **Budget**：R2.3-008 账本 3 个 semantic start（`_R2_3_008_INITIAL_START_CAP = 3` 编码，无开账事件）；每次
  失败按既有四层分类记 terminal 后才决定是否消耗下一 start；不追加新 budget 授权；不自动 fallback 到
  DeepSeek/API Key/另一 effort；run 中途不换 model profile。
- **Run identity**：`r23008-luna-20260818-start1`；profile
  `modeling_team/profiles/r2-3-008-modeling-team.yaml`（sha256 `24c3a6b6…`）；task
  `modeling_team/tasks/r2-3-008-formal-acceptance.yaml`（sha256 `7d3e6094…`）；standard
  `modeling_team/references/r2-3-008-acceptance-standard.json`（sha256 `c90e3cee…`）；model profile
  `openai-luna-medium`（sha256 `b6dee50e…`，省略 `--model-profile`，合同默认即真实操作路径）。
- **资产与环境冻结**：baseline `a785d1d`，工作树 clean（仅本文档追加）；Host `codex login status` =
  Logged in using ChatGPT；`auth.json` 元数据 0600/owner/3983B（内容未读取，全程仅元数据）。
- **调用面**：`env -u DEEPSEEK_API_KEY -u OPENAI_API_KEY ONTOLOGY_PLATFORM_ADMIN_API_KEY=<临时 admin key>
  PYTHONPATH=backend:. backend/.venv/bin/python -m modeling_team run --profile … --task … --run-id
  r23008-luna-20260818-start1 --scope <mode: create YAML> --base-url http://127.0.0.1:8001
  --freeze-started-at <UTC 时间戳>`；无 task overlay（fresh create run 不需要）；canonical gate 临时 admin
  key 运行结束即 revoke。
- **Freeze 纪律**：本条目冻结到 ledger reservation ≤ 20 分钟；同一时刻最多一个 active reservation；run root
  与证据完整保留。
- **Cleanup owner**：Delivery Agent（主代理）——revoke 临时 admin key、核对 run root 终态、零残留扫描、
  不读取/记录 `auth.json`/token 内容。
- **完成判定**：按测试计划 §4 R1–R8 由独立评审做出，本冻结不预判结果；run 结局（settled 或 retryable
  terminal failure）不影响路由/终态门判定。
- Outcome/next step: 立即启动 start1。

### 2026-08-18 — Round 3 start1 启动层失败（presemantic）— main agent

- Evidence: run `r23008-luna-20260818-start1` 于 reservation 后 ~45s 失败——CLI `run failed: app-server
  skills/list failed (rpc_error, code=-32603)` exit 2（coordinator `_initialize` 第三步 skills discovery，
  thread/start 之前，零模型调用）。账本仅两条事件：`reservation`（18:32:16Z）→ `presemantic_release`
  （reason "startup failure before business delivery"，18:32:16Z），**无 `semantic_start`——0/3 start 被消耗**
  （`start_ledger.py` 预算只计 semantic_start；presemantic release 后新 reservation 合法）。cleanup：scope
  `deleted-empty`（owned Project/Ontology 删除、residual 全零、protocol key revoked）、acceptance
  aborted/zero_child_residue、temp admin key `3040969b…` 已由主代理 revoke（复验 401）。
- 失败定层：**runtime/infrastructure**（App Server 启动协议层，发生在任何模型路由/业务交付之前；非
  modeling-quality、非 platform-contract、非路由解析——preflight/TOML 投影均已完成）。
- 根因调查（有界，4 个本地探针）：Host codex 二进制于 2026-08-18 01:58 (+0800) 被更换（0.147.0），
  start1 是升级后首次 formal app-server run；对照 2026-08-10/12 最后成功 formal run 的 home 布局
  （无 `.system` skills、有 `sessions/`），app-server 行为已变化。但以 bwrap + 真实 skill 树 + 真实
  auth staging + coordinator config/MCP 表的 4 档本地探针均无法复现 `skills/list` 失败——失败依赖真实
  运行上下文或为瞬态。
- 次级发现：`aggregate_secret_audit match_count=1`/`private_credentials_destroyed=false`。主代理以
  digest-only 复现审计证实 **Host ChatGPT 凭据不在 run root**（全部 auth 值 0 命中）；唯一命中为
  runtime 内部 token 在审计时点的瞬态 surface（当前保留产物 0 残留）。记账为 cleanup 观察项，不改变
  失败定层。
- Action/decision: 记录失败与定层；按冻结授权消耗下一 reservation（start2，预算仍 3/3 semantic start，
  presemantic 失败不消耗）。若 start2 在同一 RPC 同形失败，则判 0.147.0 app-server 与当前握手机械的
  确定性不兼容，回 developer 窄修复 handshake 层。
- Outcome/next step: 冻结 start2 授权要素并启动。

### 2026-08-18 — Round 3 start2 同形失败，判定确定性不兼容 — main agent

- Evidence: run `r23008-luna-20260818-start2`（stable state `533d896`）于 reservation（18:53:55Z）后 ~3.8s
  同形失败：`app-server skills/list failed (rpc_error, code=-32603)`，零模型调用。首次启动尝试曾被 clean
  baseline gate 拒绝（主代理 start1 文档未提交，setup 疏失，零 reservation 零账本写入）；提交 `533d896`
  后复跑即达本结果。账本仍仅 `reservation → presemantic_release`——**0/3 semantic start 消耗**。
  cleanup 完整：state `CLEANED`、owned Project/Ontology 删除（residual 全零）、acceptance
  aborted/zero_child_residue、runner 自建 admin key 自 revoke、主代理 temp key `ab6fbce9…` revoke 后复验
  401。
- 定层：**runtime/infrastructure（确定性）**——两次真实运行在同一 RPC（`_initialize` 第三步 `skills/list`）
  同形失败，而 4 档本地探针（含 bwrap + 真实 skill 树 + 真实 auth staging + coordinator config/MCP 表）均
  通过，说明不兼容点在真实 `_write_config`/`_initialize` 代码路径与 0.147.0 的组合，而非环境要素单独项。
- Action/decision: 按预承诺判定 0.147.0 app-server 与当前握手机械确定性不兼容；回 requirement_developer
  窄修复 handshake 层（定位真实路径下 `skills/list` -32603 根因，最小修复 + deterministic 回归测试）。
  修复经独立复测后再决定 start3（预算 3/3 未动）。
- Outcome/next step: developer 缺陷修复循环。

### 2026-08-18 — start1/start2 缺陷根因定位与窄修复 — requirement developer/main agent

- Evidence: developer 以真实代码路径离线复现（真实 profile/task/model-profile 加载 + 真实 `_write_config`
  + bwrap namespace + 真实 `_initialize`，零模型调用）：捕获 `skills/list` 错误
  `failed to reload config: /agent/home/config.toml:4:8: invalid type: boolean false, expected struct
  AppsConfigToml` 与 start1/start2 保留的 `configWarning`（"Invalid configuration; using defaults."，
  range 4:8-4:12 即顶层 `apps = false`）完全对应。根因：`_write_config` formal `openai-codex`
  builtin-provider 分支（R2.3-007 引入）从外部会话路径复制了 `lines[3:]` 截断，但该分支 `lines` 未预置
  model trio，截断丢弃 `sandbox_mode`/`web_search`/`[features]` 表头，11 个 feature flag 裸露为顶层键；
  旧版 CLI 容忍未知顶层键故存活至 0.147.0 升级。这也解释了 4 档本地探针全部通过（探针手写 config 含正确
  `[features]` 表头）。
- Action/decision: 接受修复 `303d701`——一行拼接修正（codex.py:3530）+ 注释 + 回归测试
  `test_r23008_codex_builtin_config.py`（3 tests，对 pre-fix 验证失败、post-fix 通过；钉死
  `sandbox_mode`/`web_search` 保留、11 flags 全部在 `[features]` 内、顶层键封闭面）。主代理逐行复核 diff
  并确认外部会话路径的 `lines[3:]`（trio 已预置）不受影响。全量 890 passed/1 skipped/293 subtests、
  compileall/ruff/diff-check 全绿；零 `backend/`/`frontend/` 改动。
- Outcome/next step: requirement_tester Round 4 独立复测；通过后再决定 start3（预算 3/3）。

### 2026-08-18 — Round 4 独立复测 PASS 与 start3 — requirement tester/main agent

- Evidence: Round 4 独立复测 PASS——实现审查确认 `303d701` 仅一行拼接修正 + 注释 + 新测试；独立
  config-shape 探针（真实加载链、六角色、128 断言）全过；pre-fix 签名用真实 codex 0.147.0 二进制
  `codex login status` 对照闭合因果链（pre-fix home 逐字复现 `config.toml:4:8 … expected struct
  AppsConfigToml`，post-fix 正常）；全量 890 passed；账本 hygiene 通过（tester 更正：008 账本为 4 事件，
  start1+start2 各 reservation/presemantic_release，零 `semantic_start`）。
- Action/decision: 修复双重证实，清除 start3 障碍。提交 `ff39aa2` 后按冻结授权启动 start3（同
  §4 要素，temp key `8bc051a2…`）。附带清理：主代理删除 `/tmp/r23008-formal-credential-*`（18 个，含
  `deepseek.env` 凭据残留）与 156 个空 `mt-*` broker 目录（developer/tester 观察项移交处置）。
- Outcome/next step: start3 执行与判定（见下一条）。

### 2026-08-18 — Round 3 start3：握手修复生效，第三角色 thread/start 失败 — main agent

- Evidence: run `r23008-luna-20260818-start3`（stable state `ff39aa2`）——**握手修复实证生效**：零
  configWarning，coordinator 与 modeling 完整启动（thread_id、shell snapshot、MCP 初始化、连接
  `wss://chatgpt.com/backend-api/codex/responses` websocket）；protocol 角色 `thread/start` 返回
  -32603，CLI exit 2。账本 `reservation`（19:26:35Z）→ `presemantic_release`，**仍 0/3 semantic
  start 消耗**。run root `logs_2.sqlite` 逐角色比对：三角色 `thread/start` 均触发 0.147.0 online
  models refresh（`GET chatgpt.com/backend-api/codex/models`）；coordinator/modeling 各记两条 ERROR
  `failed to refresh available models: timeout waiting for child process to exit` 后容忍继续；
  protocol 的 log 终止于同一 GET，其 -32603 无 message 保留（runtime 只保留 code，丢 message—— diagnosability 缺口）。
- 失败定层：**runtime/infrastructure**——0.147.0 models-refresh 子进程超时（`timeout waiting for
  child process to exit`，疑似 bwrap PID namespace 下子进程退出等待问题）在并发启动的第三角色上升级为
  致命 RPC 错误；非 modeling-quality、非平台合同、非路由解析（两角色已实证订阅路由连通）。
- Cleanup：state `CLEANED`、acceptance aborted/zero_child_residue；R2.3-008 窗口六个 API key（主代理
  三个 temp + runner 三个自建）全部 revoked（temp key 复验 401）。
- Action/decision: 回 requirement_developer 窄修复：(1) 诊断 models-refresh 子进程超时与第三角色致命化
  条件；(2) 修复候选——预置 models cache/禁用 online refresh 的 config 面、或 thread/start 对该失败的
  容忍/重试；(3) 附带修 runtime RPC 错误 message surfacing（保留 code 同时保留 message）。修复经独立
  复测后再决定下一 start（预算 3/3 未动）。
- Outcome/next step: developer 缺陷修复循环（第二轮）。

### 2026-08-18 — start3 缺陷根因定位与窄修复（第二轮）— requirement developer/main agent

- Evidence: developer 逐角色日志取证确认——三角色 `thread/start` 均因 agent home 无 `models_cache.json`
  触发 0.147.0 online models refresh；refresh 慢路径（`timeout waiting for child process to exit`，
  models manager 内部子进程在 bwrap PID namespace 下 reap 超时）在**同一次运行内**于 coordinator/modeling
  被容忍（回退 bundled catalog、继续 session_init）、在 protocol 成为致命 `-32603`——同一错误两种结局，
  判 server 侧传播竞态，"第三角色"非确定性属性。原始 -32603 message 在保留证据中不可恢复（runtime 丢弃
  message）。离线快网下慢路径不可复现（refresh ~1s 成功），故修复选择绕过而非复现。
- Action/decision: 接受修复 `c85628a`——(1) `_seed_models_cache` 在 formal builtin 分支为每个 agent home
  预置版本匹配、secret-free 的 vendored models snapshot
  （`modeling_team/references/codex-models-cache-0.147.0.json`，官方 endpoint 元数据，含 `gpt-5.6-luna`），
  `fetched_at` 置为启动时刻使 `online_if_uncached` 缓存命中、online refresh 完全不运行；slug 不在 snapshot
  或文件损坏时静默保持 legacy 行为，codex 自身在版本不匹配时回退自身 refresh（安全降级）。否决
  `features.remote_models=false`（改变 `gpt-5.6-luna` 元数据解析面）与 thread/start 重试（重入同一竞态）。
  (2) diagnosability 修复：`CodexRuntimeRPCError` 保留 sanitize 后（空白折叠、240 字符上限）的 JSON-RPC
  `message`；`data` 仍丢弃。离线三角色 bwrap 复现：seeded homes 三角色 `thread/start` 全过且 seeded
  cache 逐字未动（缓存命中直接证明，零 refresh）；全量 894 passed/1 skipped/293 subtests、
  compileall/ruff/diff-check 全绿；零 `backend/`/`frontend/` 改动。主代理复核 diff 与 vendored snapshot
  结构（纯模型目录元数据）并独立复跑全量套件通过。
- Outcome/next step: requirement_tester Round 5 独立复测；通过后启动 start4（预算 3/3 未动；0/3 已消耗）。

### 2026-08-18 — Round 5 复测 PASS + R5-D1 窄修复 — requirement tester/developer/main agent

- Evidence: Round 5 独立复测 PASS（`c85628a`）——实现审查 4 文件精确、vendored snapshot secret-scan 干净
  （`client_version` 精确 0.147.0、`gpt-5.6-luna`/`medium` 在位）、独立行为探针 23/23（种子/freshness/
  未知 slug/损坏文件/0600/config 不扰动）、RPC message 保留契约（240 截断、data 丢弃）、全量 894 绿、
  账本 hygiene 通过。附 **R5-D1（High，覆盖缺口）**：`_seed_models_cache` 仅覆盖 persistent role 路径，
  fresh Examiner child 的 builtin 分支不种子 child 独立 home，而 child 同样 `thread/start` 且发生在
  `semantic_start` 之后——命中致命竞态将实际消耗 1/3 预算。
- Action/decision: 按测试建议先修复再 start。developer 窄修复 `aee472b`：`_seed_models_cache(home, model)`
  参数化为 home 路径，child builtin 分支补种子调用（external-credential/non-formal/deepseek 路径不动）
  + 3 个 child 路径回归测试（真实 `_launch_acceptance_child_impl`，sentinel 于 process_factory，零二进制
  零模型调用）。全量 897 passed/1 skipped/293 subtests、compileall/ruff/diff-check 全绿；主代理复核 diff
  并独立复跑通过。
- Outcome/next step: Round 5 续轮（delta 复测）；通过后启动 start4。

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
| 1 | `5d34286` | 按冻结范围实现 §9 全部表面 + 新测试文件（A–E 矩阵）；一处既有断言按设计更新（合同默认逐需求映射） | 全量 884 passed/1 skipped/286 subtests；compileall/ruff/diff-check PASS；validate CLI 六角色 luna 投影 | development-ready；Round 1 发现 R1-D1 |
| 2 | `a785d1d` | R1-D1 窄修复：`formal_runs.py` 从闭合注册表派生 `FORMAL_PROFILE_IDS`/`FORMAL_TASK_IDS`，三处 cross-wire 守卫改用派生集合 + 3 测试/7 subtests | 全量 887 passed/1 skipped/293 subtests；复现命令双向 exit 2；compileall/ruff/diff-check PASS | Round 2 复测 PASS |
| 3 | `303d701` | start1/start2 同形 `skills/list` -32603 根因修复：`_write_config` builtin-provider 分支错误 `lines[3:]` 截断（该分支未预置 model trio），丢弃 `sandbox_mode`/`web_search`/`[features]` 表头致 11 个 feature flag 裸露为顶层键，codex 0.147.0 在 `skills/list` config reload 时按 typed table 拒绝。修复为 `provider_lines[:3] + lines + provider_lines[3:]`（一行）+ 新回归测试 `test_r23008_codex_builtin_config.py`（3 tests，验证对 pre-fix 失败） | developer 真实路径离线复现（真实 `_write_config` + bwrap + `_initialize`，零模型调用）：pre-fix 复现精确 `-32603`/`configWarning`，post-fix 完整 coordinator 启动通过、零 configWarning；全量 890 passed/1 skipped/293 subtests；compileall/ruff/diff-check PASS | Round 4 复测 PASS；start3 实证握手修复生效 |
| 4 | `c85628a` | start3 protocol `thread/start` -32603 根因修复：0.147.0 online models refresh 慢路径在 bwrap 下 server 侧竞态（同错误容忍/致命两种结局）。修复 = `_seed_models_cache` 预置 vendored 版本匹配 models snapshot（`references/codex-models-cache-0.147.0.json`）使 `online_if_uncached` 缓存命中零 refresh + `CodexRuntimeRPCError` 保留 sanitize 后 JSON-RPC message（data 仍丢弃）+ 新回归测试 | developer 离线三角色 bwrap 复现：seeded homes 三角色 `thread/start` 全过、seeded cache 逐字未动（缓存命中直接证明）；全量 894 passed/1 skipped/293 subtests；compileall/ruff/diff-check PASS | Round 5 复测 PASS（附 R5-D1） |
| 5 | `aee472b` | R5-D1 窄修复：`_seed_models_cache(home, model)` 参数化，child builtin 分支补种子调用（child 的 `thread/start` 发生在 `semantic_start` 后，命中竞态会实际消耗预算）+ 3 个 child 路径回归测试 | 全量 897 passed/1 skipped/293 subtests；compileall/ruff/diff-check PASS；主代理独立复跑通过 | Round 5 续 PASS；start4 实证 models refresh 不再运行 |

| 6 | 工作树（本轮提交） | start4 protocol `ontology_platform` MCP ENOENT 根因修复：`backend/.venv/bin/python` 为 uv 绝对符号链（未版本化目标目录再符号链到版本化目录），protocol namespace 仅绑 fully-resolved 前缀，字面绝对目标在 bwrap 内悬空 → 0.147.0 required MCP spawn `execve` ENOENT 升级 `thread/start` 致命。修复 = `_protocol_interpreter_mounts()` 沿符号链绑定每个绝对目标解释器前缀于其自身路径（祖先 `--dir` 先行、基础树不重建、fully-resolved 绑定保留）+ 3 回归测试 | developer 真实 protocol config × 真实 bwrap 复现：pre-fix 逐字复现 start4 签名（`execvp … No such file or directory` + `-32603` 消息），post-fix `THREAD_START_OK` 四 MCP 全初始化；全量 900 passed/1 skipped/293 subtests；compileall/ruff/diff-check PASS；主代理独立复跑通过 | Round 6 复测 PASS（pre-fix 复现 + post-fix 恢复 + 宿主符号链事实三方闭合） |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| 0 | design-reviewed | UNEXECUTED | implementation 未开始 | 测试计划 §5 |
| 1 | `5d34286` | PASS（A–E 矩阵）+ High R1-D1（矩阵外） | cross-wire 守卫字面集合未注册 008 身份，非正式配对静默降级；Round 3 真实 run 未执行（授权门） | 测试计划 §5 Round 1 |
| 2 | `a785d1d` | PASS | R1-D1 FIXED（三守卫路径双向 fail closed）；无回归；真实 run 留待 Round 3 授权冻结后 | 测试计划 §5 Round 2 |

## Final verification

- 待实施与独立测试完成后填写。

### 2026-08-18 — Round 3 start4：MCP 初始化致命化，protocol ontology_platform ENOENT — main agent

- Evidence: run `r23008-luna-20260818-start4`（stable state `fd5e23d`）——models-cache 种子修复实证生效
  （coordinator/modeling 完整 `thread/start`，无 refresh 竞态面）；RPC message 保留修复立即兑现：
  protocol `thread/start` 失败本次保留完整 message——`error creating thread: Fatal error: Failed to
  initialize session: required MCP servers failed to initialize: ontology_platform: No such file or
  directory (os error 2)`。账本 `reservation`（20:04:31Z）→ `presemantic_release`，**仍 0/3 消耗**。
- 诊断：protocol 专属 `ontology_platform` MCP（`protocol_mcp_launch.py`：`/backend/.venv/bin/python`
  -m app.mcp.server、cwd `/backend`、`required=true`）在 bwrap namespace 内 spawn ENOENT。
  `namespace_command` 已对 protocol ro-bind `/backend/app`、`/backend/.venv` 与 resolved interpreter
  root；0.147.0 将 required MCP 初始化失败升级为 `thread/start` 即致命（旧版容忍/延迟）。Round 4/5
  离线复现用通用 config 未含 protocol 专属 MCP 块，故逃过复测——复现面缺口教训记录。start3 protocol
  失败大概率同因（当时 message 被丢弃，被 models refresh 错误归因为竞态——cache 种子修复仍是正确
  独立缺陷，其在线面已被 start4 coordinator/modeling 通过所实证）。
- Cleanup：state `CLEANED`、owned Project/Ontology 删除（residual 全零）、temp key `ceb074e5…` revoke
  （复验 401）。账本 8 事件，零 `semantic_start`。
- Action/decision: 定层 runtime/infrastructure，回 requirement_developer：以**真实 protocol 角色
  config**（含 ontology_platform MCP 块与 protocol namespace binds）离线复现 ENOENT 并窄修复。
- Outcome/next step: developer 缺陷修复循环（第三轮）。

### 2026-08-18 — start4 缺陷根因定位与窄修复（第三轮）— requirement developer/main agent

- Evidence: developer 以**真实 protocol 角色 config**（schema v2：`ontology_platform` + protocol_mechanics
  + runner_capability + team_transport 块，luna builtin 绑定 + 种子 cache）驱动真实 `_write_config` 与
  真实 `namespace_command` protocol 分支（真实 bwrap、零模型调用）离线复现。根因：`backend/.venv/bin/
  python` 是 uv 管理的**绝对符号链**（目标 `~/.local/share/uv/python/cpython-3.14-…/bin/python3.14`，
  未版本化目录本身又符号链到 `cpython-3.14.3-…`）；旧代码只绑 fully-resolved 解释器前缀，`--ro-bind`
  保留 venv 内符号链原样，字面绝对目标路径在 namespace 内悬空；codex 0.147.0 以 `execve` 启动 required
  `ontology_platform` MCP → ENOENT → `thread/start` 致命。pre-fix 复现捕获 `bwrap: execvp
  /backend/.venv/bin/python: No such file or directory` 与 start4 保留消息逐字一致的 -32603；post-fix
  同一复现达 `THREAD_START_OK`，四 MCP 全初始化（probe API-key row 用后删除，核验 0 残留）。
- Action/decision: 接受修复——protocol 分支 inline 绑定替换为 `_protocol_interpreter_mounts()`：沿解释器
  符号链（防环、≤8 跳）对每个**绝对**目标的 runtime 前缀按自身路径 ro-bind，祖先 `--dir` 挂载点先于任何
  子树 bind，基础树（/usr 等）不重建，fully-resolved 前缀绑定保留（pyvenv.cfg/sysconfig），venv 内相对
  目标不加绑。`required=true`、MCP config 形状、建模语义零改动；仅 protocol 分支变化。否决改
  `protocol_mcp_launch.py` command 指向 resolved 路径（改冻结 launch 合同）与向 /backend 拷贝/符号链
  launcher（面更宽）。+3 回归测试（真实 repo 符号链布局）。主代理逐行复核 diff 并独立复跑全量
  900 passed/1 skipped/293 subtests、compileall/ruff/diff-check 全绿；零 `backend/`/`frontend/` 改动。
- 残余观察项（记录不阻断）：post-fix 复现 stderr 仍有一条 tolerated `failed to refresh available
  models: timeout waiting for child process to exit`（0.147.0 另一条种子未覆盖的 refresh 查询面），
  实证容忍回退、`thread/start` 成功，不触及路由/终态完成门；start5 证据阅读时与真致命失败区分。
- Outcome/next step: requirement_tester Round 6 独立复测。

### 2026-08-18 — Round 6 独立复测 PASS — requirement tester/main agent

- Evidence: Round 6 PASS——实现审查（diff 恰 2 文件、零 backend/frontend、protocol 分支唯一改动、其余
  mounts 逐字不变）+ 独立行为探针 13/13（真实 protocol config × 真实 bwrap：(a) 精确移除未版本化
  prefix bind 后 exec rc=127 ENOENT、字面 target 不存在——独立复现 start4 签名；(b) post-fix 字面
  target 在 ns 内存在、MCP spawn 命令 exec 成功、MCP cwd `/backend` 下 `import app.mcp.server` 成功）
  + 宿主符号链事实与根因三方闭合 + 全量 900 绿 + 账本 hygiene（008 恰 8 事件零 `semantic_start`、
  002/003/005 逐字节不变）。复现覆盖教训核验 held：本轮探针自始用真实 protocol 角色 config。
  残余观察项判定为可接受残余非覆盖缺口（容忍结局已实证，不触及 §4 R1–R5）。
- Action/decision: start5 障碍清除。提交修复与文档后按 §4 冻结要素启动 start5（预算 3/3、0/3 消耗）。
- Outcome/next step: start5 执行与判定。
