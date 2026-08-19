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
| 7 | `e2ad607` | start5 turn 层出站超时：`_minimal_codex_process_env` 显式最小 env 不含 host 代理变量（`http(s)_proxy=127.0.0.1:1080`），Host 网络禁止直连 chatgpt.com，codex `ReqwestDefault` 直连 → sampling/analytics/models 全部超时 → `llm-inactivity-timeout`。首次消耗 1/3 semantic start | developer 离线复现（真实宿主 env pre/post-fix env 形状 + in-bwrap 可见性探针，零模型调用零 chatgpt.com 接触）；主代理独立复跑全量 905 绿 | Round 7 复测 PASS（15/15 探针 + 泄漏面 + loopback 安全）；start6 实证零超时 |
| 8 | 工作树（本轮提交） | start6 tool 执行层全阻断（defect 5）：codex 0.147.0 tool/shell 执行 spawn 伴生二进制 `codex-code-mode-host`，namespace 只挂 `codex` → 每 tool call ENOENT，四角色 Blocked，runner 协调死锁挂起 4h（SIGINT 终止）。第二次消耗 semantic start（2/3）。另发现 SIGINT cleanup 不记 terminal_failure 的账本闭合缺口（已以 Delivery-Agent recovery 窄脚本闭合）。修复 = `_codex_companion_binary()`（resolved codex bin 目录解析伴生二进制，symlink/非 regular/不可执行一律 None 降级）+ 两个挂载点（`namespace_command` persistent 分支、`_acceptance_namespace_command` child `--` 前）additive ro-bind `/agent/bin/codex-code-mode-host` + 5 回归测试 | start6 rollouts 逐角色 ENOENT 签名（6/7/5/1）；宿主 release bin 目录仅 codex + codex-code-mode-host 两文件；developer 真实 namespace × 真实 bwrap 离线复现（pre-fix rc=127 ENOENT / post-fix 在位可执行）；全量 910 passed/1 skipped/293 subtests、compileall/ruff/diff-check PASS；主代理独立复跑通过 | Round 8 复测 PASS（20/20 探针 + 降级形状 + 账本 recovery strict replay 只读复验） |

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

### 2026-08-18 — Round 3 start5：首次消耗 semantic start，turn 层出站超时 — main agent

- Evidence: run `r23008-luna-20260818-start5`（stable state `3a2289f`）——freeze→reservation 4s，
  **`semantic_start` 20:33:30Z（1/3 首耗）**。前四项修复全部在线生效：无 configWarning、models cache
  命中、六角色 thread/started（含 protocol，缺陷 3 修复实证）、`turn/started` span
  `model=gpt-5.6-luna`/`medium`（Luna 路由在真实 turn 生效）。随后四角色 sampling 请求全部
  `request timed out`（5/5 重试 + HTTP 回退再超时）、analytics/models GET 同超时 → coordinator
  `llm-inactivity-timeout` → `terminal_failure`（runtime/infrastructure）20:38:47Z。
- 根因（三层证据）：Host egress 强制走 `http://127.0.0.1:1080`（direct curl chatgpt.com 挂起、via
  proxy 0.58s 通）；`_minimal_codex_process_env`（codex.py:371）显式最小 env 不含 `http_proxy`/
  `https_proxy`/`no_proxy`；codex `ReqwestDefault` 无代理 env 即直连 → 全部 chatgpt.com 出站超时。
  Round 6 "残余 refresh timeout" 观察项同因归并。
- Cleanup：runner 完整（scope deleted-empty、Project/Ontology 删除 residual 全零、三 key revoked）；
  temp key `4ef586d3…` revoke 复验 401（误建重复 key 先行 revoke）。账本 11 事件，1/3 消耗 2 剩余。
- Action/decision: 定层 runtime/infrastructure，回 developer 窄修复 env 透传。
- Outcome/next step: developer 缺陷修复循环（第四轮）。

### 2026-08-18 — start5 缺陷窄修复与 Round 7 复测 PASS — requirement developer/tester/main agent

- Evidence: developer 修复——`_PROXY_ENV_KEYS`（http_proxy/https_proxy/no_proxy 双大小写共 6 键）在
  `_minimal_codex_process_env` 内条件转发（仅宿主实际设置且非空时；其余宿主变量不穿越；`no_proxy`
  随行保 loopback 直连）+ 5 个新测试；`test_r23005_b_runtime.py` 既有 exact-equality 断言以
  `patch.dict` 钉死 proxy 键使断言宿主无关。离线复现：真实宿主 env 下 pre-fix 代理被剥离（env 层
  复现缺陷面）/post-fix 精确转发；in-bwrap 探针证实变量 namespace 内可见、proxy 端口 TCP 可达
  （HTTP 400 应答），零 chatgpt.com 接触。全量 905 passed/1 skipped/293 subtests、compileall/ruff/
  diff-check 全绿；主代理逐行复核 diff 并独立复跑通过。
- Round 7 独立复测 PASS——实现审查（产品面恰一个条件转发循环，DEEPSEEK 分支与非 formal 路径逐字
  不变）+ 独立 env 探针 15/15（真实/无代理/空值三宿主形态 keyset 精确、泄漏面零穿越、两条调用点
  sentinel 验证）+ loopback 安全（reqwest/httpx 双大小写、no_proxy 覆盖 127.0.0.1/localhost/::1）+
  回归 905 绿 + 账本 hygiene（恰 11 事件）。附带结论：Round 6 残余 refresh timeout 观察项同因归因
  闭合，start6 证据阅读验证其消失。
- Action/decision: start6 障碍清除。提交修复与文档后按 §4 冻结要素启动 start6（预算 1/3 已消耗、
  2/3 剩余）。
- Outcome/next step: start6 执行与判定。

### 2026-08-18 — Round 3 start6：proxy 修复实证生效，tool 执行层全阻断（defect 5）— main agent

- Evidence: run `r23008-luna-20260818-start6`（stable state `e2ad607`）——freeze→reservation
  20:50:03Z，**`semantic_start` 20:50:07Z（2/3 消耗）**。proxy 修复在线实证生效：四角色零
  `request timed out`/`stream disconnected`（logs_2.sqlite 全角色 0 命中）、models GET 200 OK、
  `codex_api::sse::responses` websocket 流事件持续到达、`turn/started` span `model=gpt-5.6-luna`
  ——Round 7 记录的"残余 refresh timeout 观察项"按预判消失。
- **新缺陷（defect 5）**：codex 0.147.0 tool/shell 执行需 spawn 伴生二进制 `codex-code-mode-host`，
  runtime namespace 只挂载 `codex` 于 `/agent/bin/codex`，伴生二进制缺失 → namespace 内每个 tool
  call 返回 `failed to spawn code-mode host /agent/bin/codex-code-mode-host: No such file or
  directory (os error 2)`（session rollouts 逐角色命中：coordinator 6 / modeling 7 / protocol 5 /
  acceptance 1）。四 persistent 角色均以 Blocked 终答，coordinator 协调死锁，runner 无 watchdog/
  profile run-timeout，挂起 ~4 小时。
- 处置：主代理 SIGINT 终止（00:51:10Z aborted.jsonl）→ graceful cleanup 完整（state `CLEANED`、
  scope 删除零残留、runner 自建 key 自 revoke）；temp admin key revoked 复验 401。宿主侧事实：
  伴生二进制存在于 `~/.codex/packages/standalone/releases/0.147.0-x86_64-unknown-linux-musl/bin/`
  （codex 258MB + codex-code-mode-host 49MB，仅此两个文件）。
- **账本修复（Delivery-Agent recovery）**：SIGINT 路径（CLI KeyboardInterrupt → `runner.cleanup`）
  只清理资源不记 terminal_failure，而 `_reserve`（start_ledger.py:732-735）要求最新
  `semantic_start` 闭合后才能 reserve 下一 start——start6 处于 unclosed 状态会阻塞 start7。主代理
  以窄脚本（job tmp `close-start6-terminal-failure.py`，真实 `StartLedger` API，写前断言末事件
  为 start6 `semantic_start`）追加恰一条 `terminal_failure`（`runtime/infrastructure`、
  `complete_modeling_quality_result=false`、`repair_baseline_hash=null`、无 terminal_evidence——
  逐字段镜像 start5 由 runner 写出的形状），strict replay 在写入时复验通过。账本现 14 事件：
  2/3 消耗、1 剩余。
- Action/decision: 定层 runtime/infrastructure，回 requirement_developer 窄修复
  `namespace_command`：将 `codex-code-mode-host` 与 codex 同目录挂载到 `/agent/bin/`（并审计
  0.147.0 release bin 目录是否还有其他伴生二进制——已核实仅两个文件）；离线以真实 bwrap 复现
  ENOENT → post-fix tool spawn 成功。
- Outcome/next step: developer 缺陷修复循环（第五轮）→ Round 8 复测 → start7（最后 1 个 start）。

### 2026-08-18 — start6 缺陷窄修复（第五轮）与 Round 8 复测 PASS — requirement developer/tester/main agent

- Evidence: developer 修复——`_codex_companion_binary()` 从 resolved codex binary 所在 release
  `bin/` 目录解析 `codex-code-mode-host`（lstat 拒符号链/非 regular 文件、`X_OK` 拒不可执行、
  失败一律 `None` 降级为 pre-fix 形状），在两个 codex 挂载点 additive 追加 ro-bind
  `/agent/bin/codex-code-mode-host`：persistent `namespace_command`（`--chdir` 插入块内）与
  `_acceptance_namespace_command`（child 同样执行 tools，bind 置于 bwrap `--` 前）+ 5 回归测试
  （四 persistent 角色与 child 的 bind 在位、缺伴生降级逐字同形、symlink/不可执行拒绑）。
  真实 namespace × 真实 bwrap 离线复现：pre-fix `exec /agent/bin/codex-code-mode-host` rc=127
  ENOENT（逐字对齐 start6 签名），post-fix 伴生二进制在 ns 内在位可执行。零模型调用、零
  app-server、零 run/账本写入。全量 910 passed/1 skipped/293 subtests、compileall/ruff/
  diff-check 全绿；主代理逐行复核 diff 并独立复跑通过。
- Round 8 独立复测 PASS——实现审查（diff 恰 2 文件、纯新增、`use_bwrap=False` 早退路径未触碰、
  companion 缺失时 surface 逐字节同形）+ 独立行为探针 20/20（真实构造 × 真实 bwrap：persistent
  pre-fix ENOENT 复现/post-fix 在位可执行且 ELF magic 正确；child 同构；降级形状零 companion
  token）+ 全量 910 绿 + 账本 hygiene（008 恰 14 事件，**recovery 追加的 start6
  terminal_failure 经真实 `StartLedger` 只读 strict replay 复验有效**，start7 预算门解锁；
  002/003/005 逐字节不变）。
- Action/decision: start7 障碍清除。提交修复与文档后按 §4 冻结要素启动 start7（预算 2/3 已
  消耗、1/3 剩余——最后 1 个 start）。
- Outcome/next step: start7 执行与判定（真实 tool spawn 成功按 §4 归 start7 在线验证）。

### 2026-08-18 — Round 3 start7：全链修复实证生效，candidate 注册层类型合同失败（defect 6）— main agent

- Evidence: run `r23008-luna-20260818-start7`（stable state `e848999`）——freeze/reservation
  01:09:25Z → **`semantic_start` 01:09:29Z（3/3 消耗，首批预算耗尽）**。**前五轮修复全部在线实证
  生效**：零出站超时、六角色工具/transport 真实执行（deliveries 6、mcp-elicitations 9、
  capability-calls、coordinator 协调回合），完整 formal candidate 于 01:10:40Z 通过 candidate
  gate（`formal-candidate-progress.jsonl`：`candidate_revision: 1`、semantic/candidate digest
  齐备，含 C→B→A 切片 entities/relations/explicit unknowns/consumer query 与 evidence
  citations）。随后 runner.py:3161 `register_accepted_candidate` 以未类型化
  TeamConfigurationError `accepted candidate_revision must be a safe stable identifier` 终止
  整个运行（CLI exit 2）。
- 根因（defect 6，三层合同不一致）：(a) envelope 校验
  `candidate_progress._validate_revision`（candidate_progress.py:74）接受正整数**或**非空字符串；
  (b) modeling 角色指令的 R2.3-003 专属小节（instructions.md:209 起，line 227）明确要求整数
  JSON number（`initial 1 (not "1")`），而通用小节从未钉死类型、唯一示例
  `platform-neutral-candidate-authoring.json:62` 是字符串 `"neutral-example-1"`；(c) 对非 003
  task，`acceptance.py:1743` `_safe_id` 只接受小写字符串。Luna modeling 角色产出整数 `1`——
  envelope 放行、candidate gate 通过，直到 acceptance 注册层才拒绝并以未类型化错误杀死整个
  run（Agent 无 in-run 类型化纠正路径）。
- 定层：**platform-contract**——确定性机械层自身的稳定标识符类型合同在两个校验点不一致，且
  失败在 candidate 接受之后才 surfaced（正确行为应是 envelope 处类型化拒绝、Agent 可当轮
  纠正，或两个校验点合同一致）。非 modeling-quality（通用指令未约束类型、008 逐字镜像 005
  资产无类型规定）、非路由/运行时。
- Cleanup：state `CLEANED`、acceptance aborted/`zero_child_residue`、`admin_key_revoked` +
  `aggregate_keys_non_active`（全部 key non-active）、temp admin key revoke 复验 401。
  `secret_audit match_count=3`（`private_credentials_destroyed=false`）：与 start1 观察项同形；
  主代理 digest-only 扫描证实 run root 保留产物对 Host `auth.json` 全部值 **0 plaintext 命中**，
  命中面为已 revoke 的 runtime 内部瞬态 key 面（bounded），记账为 cleanup 观察项。
- 账本修复（Delivery-Agent recovery，同 start6 先例）：CLI 异常路径不写 terminal_failure，
  以窄脚本（真实 `StartLedger` API、写前断言）追加恰一条 `terminal_failure`
  （`platform-contract`、`complete_modeling_quality_result=false`），strict replay 复验通过。
  账本 17 事件：**3/3 消耗，首批预算耗尽**。
- Action/decision: 回 requirement_developer 窄修复 defect 6（统一 revision 类型合同：
  envelope/注册两校验点一致 + 通用指令钉死类型，R2.3-003 整数小节不动）；Round 9 复测。
  **start8 需要新的用户 budget 授权（首批 3 start 已耗尽），修复后向用户请求。**
- Outcome/next step: developer 缺陷修复循环（第六轮）→ Round 9 复测 → 用户授权决策。

### 2026-08-18 — start7 缺陷窄修复（第六轮）与 Round 9 复测 PASS — requirement developer/tester/main agent

- Evidence: developer 修复——(1) `candidate_progress.py` 新增 `_validate_task_revision`（安全串
  `[a-z][a-z0-9-]{1,127}`，与 `acceptance._safe_id` 逐字符同步）在 `_new_pending` latch pending
  之前应用：非 003 task 的整数/非安全 revision 于**首次 delivery** 即获类型化
  `FormalCandidateError`（含 pattern 与 R2.3-003 例外说明，in-run 可纠正），中性
  `validate_formal_candidate`/`_validate_revision` 不变（Protocol 侧无 task 上下文的使用不受
  影响）；(2) `runner.py` 以与相邻 `allow_post_receipt_revision` 相同的
  `requirement_id=="R2.3-003"` 信号接线 `integer_revisions`；(3) `_revision_is_newer` 补非数字
  字符串对严格字典序递增（数字串数值、int-int 不变）——安全串合同下 conflict→revision 流可
  行的必要扩展；(4) 指令面：modeling instructions 通用小节一句话钉死字符串格式（003 小节
  不动）+ `platform-neutral-candidate-authoring.json` 字段规格与 checklist 行。7 文件 +87/−15
  + 新测试（6 tests/9 subtests）；全量 916 passed/1 skipped/302 subtests、compileall/ruff/
  diff-check 全绿；主代理逐行复核 diff 并独立复跑通过。
- Round 9 独立复测 PASS——实现审查（regex 与 `_safe_id` 逐字符一致、latch 前拒绝零状态残留、
  `register_accepted_candidate` 本体未动未放宽、003 整数路径保留）+ 独立行为探针 36/36（整数
  typed 首拒零 pending、`rev-1` 端到端通过 registration、003 开关接受整数、`_revision_is_newer`
  全序规则含 `rev-2`→`rev-10` False 定义行为、16 类不安全值 typed 拒绝与 2/128 边界接受）+
  错误路径（drain 捕获点与既有 envelope-invalid 同路径、latch 幂竭）+ 全量 916 绿 + 账本
  hygiene（008 恰 17 事件、002/003/005 逐字节不变）。
- Action/decision: defect 6 闭合。修复与文档提交后，**start8 需新的用户 budget 授权（首批
  3 start 已耗尽），向用户请求**。
- Outcome/next step: 用户授权决策 → （授权则）start8 真实 Luna formal run 与 §4 R1–R8 判定。

### 2026-08-18 — 用户决定：暂停，不追加 budget — user/main agent

- Context: defect 6 修复提交 `622bf48`（Round 9 PASS）后，主代理就 start8 budget 授权询问
  用户（首批 3 start 已耗尽：start5 proxy 超时 / start6 companion 缺失 / start7 revision 类型
  合同，全部修复并复测 PASS）。
- Action/decision: **用户选择"不再授权，暂停"**。R2.3-008 保持 in-progress：六个缺陷修复与
  三轮真实运行证据完整保留；start7 已实证全栈 Luna 路由（六角色工具/transport 执行、完整
  formal candidate 产出与 gate 接受），仅 candidate 注册层类型合同失败（已修复未在线验证）。
  不启动 start8，不做任何进一步真实运行/账本写入。
- Outcome/next step: 迭代暂停。恢复条件：用户明确追加 budget 授权（账本
  `authorize_budget`，增量 3）后，在修复后基线上启动 start8 并按测试计划 §4 R1–R8 完成路由/
  终态判定。

### 2026-08-18 — 用户追加授权 3 个 start 与 start8 冻结 — user/main agent

- **Authorization source**：用户 2026-08-18 消息"继续授权三次"（在暂停决定之后追加）。账本事件
  `budget_authorization`（additional_starts=3，authorization_id
  `r2-3-008-budget-20260818-2`，reference 记录用户原话），strict replay 复验通过。预算现为
  3/3 剩余（累计 6 授权）。
- **Run identity**：`r23008-luna-20260818-start8`；profile/task/standard/model profile 资产与
  sha256 与 start1 冻结条目一致（未变）；稳定基线 `622bf48`（defect 6 修复 + Round 9 文档），
  工作树 clean。
- **边界与纪律**：与 §4/首轮冻结相同——fresh create scope、temp admin key 运行结束即 revoke、
  不读取/记录 `auth.json` 内容、零 API-key 路径、run 中途不换 profile、freeze→reservation
  ≤20min、run root 与证据完整保留、Cleanup owner 为主代理。
- **本 start 特有观察项**：defect 6 修复（revision 字符串合同）的在线验证——首次 delivery 若
  revision 非安全字符串应获类型化 in-run 纠正而非 run 终止；正常路径为完整 formal candidate
  注册成功并进入 Examiner 验收与终态。
- Outcome/next step: 立即启动 start8。

### 2026-08-18 — Round 3 start8：全栈健康，未回答 outer question 环形等待死锁 — main agent

- Evidence: run `r23008-luna-20260818-start8`（stable state `a383e03`）——freeze/reservation 07:25:39Z →
  **`semantic_start` 07:25:43Z（4/6 消耗）**。前六轮修复全部在线实证生效：四 persistent 角色完整
  `thread/started`（thread_id 在位）、零出站超时（models GET 200、websocket 流事件持续）、
  companion 挂载在位、各角色完成一个真实 Luna turn（`turn/started` span `gpt-5.6-luna`/`medium`）。
  **semantic_start 后 15 秒**，modeling 经 Team Transport 向 coordinator 发出 grounded clarification
  question（delivery-4，07:25:58Z，`evidence/outer-question.jsonl`）："When C completes without a numeric
  score and returns a diagnostic code, what does B do—block publication, continue, retry, or mark for
  review?"——即业务切片源材料中留白的 B/C 行为点（R2.3-003 冻结 ExplicitUnknown
  `unknown-b-no-score-behavior` 的同一切片在 008 standard `preserve-explicit-unknown` 政策下的再现）。
  coordinator 将问题转述给 outer 用户后进入 "Awaiting the user's clarification"；protocol 等待
  Modeling 的 candidate 交付；acceptance 等待 Runner acceptance_start；modeling 等待 coordinator
  回答——**四角色环形等待**，deliveries 停在 5，零 candidate，挂起 ~3h 后主代理 SIGINT 终止。
- 根因（非确定性层缺陷，设计机制存在但未启用）：runner 有完整的 outer-question 机制（记录
  `outer-question.jsonl`、前台 display 绑定、`receive_outer` 消费）与配套 **outer-input FIFO**
  （`__main__.py:357` `--enable-outer-input-fifo`，为 background Host 设计的 NDJSON 应答通道），
  但 FIFO 为 opt-in 且本次 run 命令沿袭 start1–start7 模板未启用；runner 对 pending 未回答的
  outer question 无 timeout/watchdog（与 start6 死锁同族缺口）。headless run 中该问题永远无法被
  回答 → 永久等待。
- 定层：**runtime/infrastructure**——deterministic 层与六角色路由全部健康；问题本身是
  contract-permitted 行为（outer-question 机制即为它设计），失败在于 headless 运行缺少应答通道
  且无超时，属运行面/操作面缺口（start6 先例：无 watchdog 挂起同判）。
- Cleanup：SIGINT graceful cleanup 完整（state `CLEANED`、scope `deleted-empty`、owned
  Project/Ontology 删除 residual 全零、acceptance aborted/zero_child_residue、全部 runner key
  non-active）；temp admin key `r23008-admin-key-8`（id `1e033f10…`）revoke 复验 401。run audit
  `secret_audit match_count=3`/`private_credentials_destroyed=false`：主代理 digest-only 扫描
  （5 个 host auth 值 in-memory 比对、不打印）证实 run root 761 个保留文件 **0 plaintext 命中**，
  与 start1/start7 观察项同形（runtime 内部瞬态 key 面）。
- 账本修复（Delivery-Agent recovery，同 start6/start7 先例）：SIGINT 路径不写 terminal_failure，
  以窄脚本（真实 `StartLedger` API、写前断言）追加恰一条 `terminal_failure`
  （`runtime/infrastructure`、`complete_modeling_quality_result=false`），strict replay 复验通过。
  账本 21 事件：**4/6 消耗（start5–8），2 剩余**（`r2-3-008-budget-20260818-2` 授权内）。
- Action/decision: start9 启动命令追加 `--enable-outer-input-fifo`——该 flag 即为此场景设计
  （background Host 经 FIFO 发送 grounded owner answer）；outer question 出现时由 Delivery Agent
  呈报用户（owner）决策，不由 Delivery Agent 代答业务语义。无代码缺陷需要修复循环。
- Outcome/next step: start9（授权余量内，无需新授权）。

### 2026-08-18/19 — Round 3 start9：FIFO outer 应答闭环实证 + protocol receipt 二次构建死锁（defect 7）— main agent/user

- Evidence: run `r23008-luna-20260818-start9`（stable state `92ecf79`）——freeze 10:31:13Z → reservation →
  **`semantic_start`（5/6 消耗，最后 1 剩余）**。启动命令追加 `--enable-outer-input-fifo`，
  `control/outer-input.fifo` 应答通道在位。
- **FIFO outer 应答机制闭环实证**：modeling 提出 2 个 grounded outer question——(1) B 消费 C 的哪个
  版本（delivery-3/6）：用户经 AskUserQuestion 确认 **Version 2 / quality_rating**（与 R2.3-005 已接受
  候选 `b-current-output → quality-rating-field` 一致）→ `owner-answer-delivery-1` 送达；(2) B 无分数
  行为（delivery-8）：按 R2.3-005 已接受基线 owner answer 2 原文回传（不推断，preserve explicit
  unknown）→ `owner-answer-delivery-2` 送达。modeling 随即交付**完整 formal candidate**
  （`r23008-candidate-1`，defect 6 字符串 revision 合同在线生效），两项 owner answer 被引用为证据、
  `unknown-b-no-score-behavior` 按 preserve-explicit-unknown 建模。start8 的死锁面（未回答 outer
  question）被设计机制正确解除。
- **新缺陷（defect 7）**：protocol 先以手写回复（delivery-11）应答 candidate，被 formal 验证拒绝
  （invalid-response，quarantined、reply slot reopened、redrive 发出）；protocol 经 capability 构建
  typed receipt **成功**（23:43:32Z，capability-calls.jsonl ok=true），5 秒后**再次调用**
  `protocol_build_candidate_receipt` 被 runner 幂等拒绝（"typed candidate response was already
  built"）——该可行动诊断被 capability 层故意 opaque 的 `-32001` 遮蔽（capability_mcp.py:580 注释
  自认"Agent 须据以行动的诊断应走结构化 success path"）；protocol 将其解读为 platform barrier 未授权，
  升级 cooperative issue-1（runtime_recovery、zero-mutation）并结束 turn，**未交付已持有的 receipt**。
  主代理以 `issue_resolution` guidance 恢复运行（23:50:27Z），但 redrive turn 已随升级结束——runner
  判 `candidate-redrive-exhausted`，**typed terminal failure（collaboration/routing）**，本条为 runner
  自写（无需 recovery 脚本）。
- Cleanup：state `CLEANED`、scope `deleted-empty`、residual 全零、acceptance aborted/
  zero_child_residue、全部 key non-active；temp admin key `r23008-admin-key-9`（id `d4d2eb06…`）
  revoke 复验 401；digest-only 扫描 782 保留文件对 host auth 值 **0 plaintext 命中**。账本 24 事件：
  **5/6 消耗，1 剩余**。
- 定层：**collaboration/routing**（runner 自分类）；根因面含一个可修的 platform-contract 窄缺口——
  同一 candidate 的重复 receipt 构建请求（可由 runner 保留状态确定性重建、字节相同）被 opaque 拒绝
  且无结构化诊断/幂等再取路径，导致 Agent 弃置已构建 receipt 并烧掉整个 run。
- Action/decision: 回 requirement_developer 窄修复 defect 7（receipt 构建 capability 对重复请求的
  幂等/结构化诊断面；不改变 transport 单次接受语义）；Round 10 复测后决定是否消耗最后 1 个 start。
- Outcome/next step: developer 缺陷修复循环（第七轮）。

## 2026-08-19 — defect 7 窄修复（receipt 二次构建幂等 replay）+ Round 10 独立复测 PASS

- **修复（developer 第七轮，主代理复核后提交）**：`modeling_team/runner.py`（+38/−6）——
  `_active_protocol_candidate` 新增 keyword-only `idempotent_receipt=False`，"already built"
  拒绝仅对非 replay 生效且位于全部既有防御（conflict/terminal/foreign/stale/paused/state）
  之后；`_build_protocol_candidate_receipt` 对 still-answerable candidate 的重复请求走同一
  确定性重建路径，canonical digest 与注册 digest 比对（不匹配即 fail-closed
  "typed candidate receipt replay is not byte-stable"，检查先于任何状态写入），replay 结果标记
  `idempotent_replay: True`；protocol startup guidance 增补 replay 语义（原样重发 receipt_json、
  勿据此升级 issue）。新增 `modeling_team/tests/test_r23008_receipt_idempotency.py`（5 tests，
  含 start9 精确序列 redrive_sent replay、post-conflict/post-terminal 拒绝、R2.3-003 整数
  revision 回归）。transport 单次接受语义、capability 层 opaque `-32001`、R2.3-003
  post-receipt conflict 路径均未改动。
- **验证**：main agent 与 tester 独立各跑 full suite → **921 passed / 1 skipped / 302 subtests**
  （R9 基线 916 + 新 5）；compileall / ruff / `git diff --check` 干净；backend/frontend 零改动。
- **Round 10 独立复测（requirement_tester，同 test plan append-only）**：实现审查 + 5/5 新测试
  + 15/15 独立行为探针（真实 R2.3-008 formal contract，含篡改 digest fail-closed、digest 注册
  缺失 fail-closed、foreign/stale/paused/terminal 拒绝、receipt→conflict 单次构建保留）→
  **PASS，无新缺陷、无回归**；账本 24 事件未触碰（5/6 消耗，剩 1 start）。
- **Decision**：修复随本轮提交；按 Priority L0 立即消耗最后 1 个授权 start（start10）执行
  R2.3-008 §4 R1–R8 路由/终态验证（`--enable-outer-input-fifo`，同一冻结纪律；R1 的
  Examiner children 尚无 live 验证记录）。

## 2026-08-19 — start10（第 6/6 个授权 start）：defect 7 修复 live 生效，新 defect 8（untyped crash）终止

- **Run**：`r23008-luna-20260819-start10`，freeze `2026-08-19T00:06:00Z`，`--enable-outer-input-fifo`，
  账本 reservation 00:06:04 / semantic_start 00:06:10。工作树基线 commit `ddb4c3e`（defect 7 修复
  + Round 10 PASS 已提交）。
- **FIFO 外问闭环再次 live 生效**：两个外问均按冻结基线即时携带转发——delivery-4（B↔C 版本选择）
  → “B 消费 C Version 2（quality_rating），latest published 绑定”（用户 start9 决定）；delivery-6
  （B 无分数行为）→ “断言 explicit unknown `unknown-b-no-score-behavior`，不得发明行为”（005 基线
  owner answer 2）。owner-answer 两条均带 owner_answer_id/release_id 入册。
- **完整候选 delivery-8（r23008-candidate-1）**：29 items（含 currentlyConsumesOutput
  workflow-b→quality-rating-field、unknown-b-no-score-behavior、consumer_query×2），语义与 005
  基线一致；formal-candidate-progress 记 `candidate`/awaiting_receipt。
- **defect 7 修复 live 验证**：protocol 00:08:29 首次 `protocol_build_candidate_receipt` ok=true，
  00:08:33 **重复调用同一 capability → ok=true 幂等 replay**（start9 的致死序列原样存活，
  capability-calls.jsonl 两行 ok=true）。
- **新缺陷（defect 8，platform-contract）**：protocol 交付 receipt 后，acceptance
  `register_accepted_candidate` → `ProtocolRetrievalGate._extract_plan` 抛
  "consumer_query required_path has no candidate binding:
  workflow-b--currentlyConsumesOutput-->quality-rating-field"——Luna modeling agent 将
  consumer_query `required_paths` 写成完整路径表达式串（`subject--predicate-->object`），而平台契约
  （及 005 已验收基线）要求**裸谓词局部名**（`_extract_plan` 的 `_local_name(path) != path` 检查
  对不含 `#`/`/`/`:` 的路径表达式串不拦截，落入 declarations 键（谓词局部名）缺失 → 该错误在
  receipt 已交付后以 **untyped 异常击穿整run**（exit 2），无 quarantine、无 revision/redrive、
  无 typed 终态分类。触发面为 modeling 质量偏差，失败层为平台契约：非法候选必须以 typed、可修订
  的 invalid-response 呈现，不能在 receipt 交付后以未分类异常烧掉整个 run。
- **Cleanup/卫生**：crash 路径确定性清理完整——state `CLEANED`、scope `deleted-empty`、residual
  全零、acceptance aborted/zero_child_residue、全部 key non-active；temp admin key
  `r23008-start10-temp`（id `c7d4e64f…`）revoke 200 / 复验 401；digest-only 扫描 796 保留文件
  **0 plaintext 命中**。账本 guarded recovery 关闭（platform-contract，27 事件：
  **6/6 消耗，授权 start 全部用尽**）。
- 定层：**platform-contract**（untyped crash on malformed candidate retrieval plan）；
  Action/next step：defect 8 回 requirement_developer 窄修复（candidate 消费查询 plan 非法的
  typed/可修订处理；不得改动 retrieval gate 的 bare-local-name 契约本身）；Round 11 复测。
  **任何 start11 需用户新授权**（6/6 已耗尽）。

## 2026-08-19 — defect 8 窄修复（retrieval plan 预检 + typed 防御）+ Round 11 独立复测 PASS

- **修复（developer 第八轮，主代理复核后提交）**：`modeling_team/runner.py`（+66/−7）——
  (1) `_build_protocol_candidate_receipt` 在构建任何 receipt 前，以与注册时完全相同的构造参数运行
  `ProtocolRetrievalGate` 预检；非法 consumer_query plan 不再发 receipt，而是记
  `receipt_rejected` 标记并抛携带 `data={reason:"consumer_query_plan_invalid",detail,action}`
  的 `AcceptanceContractError`，经 capability 既有 success-path 机制直达 Agent 为
  `{ok:False,error:{...}}` 结构化诊断（非 -32001）；Protocol 按指引走 typed conflict →
  Modeling 完整修订 `required_paths` 为裸局部名 → 新候选重验。(2)
  `_active_protocol_candidate` 的 conflict 前置集合扩为 `{"receipt","receipt_rejected"}`，
  仅放开该修订回路；其余拒绝全部不变。(3) `_observe_formal_candidate_delivery` 对
  `register_accepted_candidate` 包 `AcceptanceContractError` →
  `_latch_formal_candidate_failure("platform-contract","accepted-candidate-registration-rejected")`
  + typed `TeamConfigurationError`——start10 的未分类 exit-2 路径（含手工 exact receipt 绕过）
  不可能再现。新增 `modeling_team/tests/test_r23008_retrieval_plan_gate.py`（5 tests）。
  `_extract_plan` bare-local-name 契约、transport 单次接受、defect-7 replay、003 路径零改动。
- **验证**：main agent 与 tester 独立各跑 full suite → **926 passed / 1 skipped / 302 subtests**
  （R10 基线 921 + 新 5）；compileall / ruff / `git diff --check` 干净；backend/frontend 零改动。
- **Round 11 独立复测（requirement_tester，同 test plan append-only）**：实现审查 + 5/5 新测试
  + 独立探针（capability endpoint 直达 shape、标记不闭合 revision 循环、`receipt_rejected`
  下全部防御仍在、gate 预检先于 digest 注册 fail-closed、latched 终态证据落盘）→
  **PASS，无新缺陷、无回归**；账本 27 事件未触碰。
- **Decision**：修复随本轮提交。**第二批 6 start 已全部消耗——start11 需用户新授权**；
  未获授权前不开跑，替代路径为以 R1（Luna 下 Examiner children 无 live 验证）为显式残留
  关闭本需求。

## 2026-08-19 — 预防指引（required_paths 裸局部名契约下沉到 modeling 可读面）+ Round 12 PASS + 第三批预算授权

- **用户决策**：授权 3 个新 start（ledger `budget_authorization` `r2-3-008-budget-20260819-3`，
  28 事件），并明确要求"避免已经发现的错误在下次进行建模时依然犯错"。
- **预防面真空**：modeling agent 可读的全部 surface（instructions / 中性 authoring reference /
  task yaml）此前无一处写明 consumer_query `required_paths` 的裸谓词局部名契约——start10 的
  路径表达式串是凭空猜测。defect 8 修复提供恢复路径，本轮补预防。
- **修复（developer 第九轮，主代理复核后提交）**：
  `modeling_team/agent-packages/modeling/instructions.md`（+7，envelope 约束区、003 段之外）+
  `modeling_team/references/platform-neutral-candidate-authoring.json`（+6，
  `consumer_query_required_paths` 规格用中性示例 `neutralAssociation` + closure_checklist 一行，
  该文件未被 content-pin、增量容忍机制有 defect-6 先例）+ 新测试
  `test_r23008_consumer_query_plan_guidance.py`（2 tests）。
- **验证**：main agent 与 tester 独立各跑 full suite → **928 passed / 1 skipped / 302 subtests**
  （R11 基线 926 + 新 2）；compileall / ruff / `git diff --check` 干净。
- **Round 12（轻量）独立复测 PASS**：指引与 `_extract_plan` 契约逐点一致（含
  `currentlyConsumesOutput` 与 005 基线实际局部名一致）；reference JSON scenario-neutrality
  禁词扫描通过；003 段未触碰。
- **Decision**：随本轮提交后立即执行 start11（第三批第 1 个 start），携带生效后的 agent 包，
  冻结纪律 + `--enable-outer-input-fifo` + watchdog。

## 2026-08-19 — start11 live：issue-3/issue-4（shape min_count 内部不一致）+ Round 13 预防指引

- **start11 进展（live）**：首个在 Luna 下被接受的 formal candidate（`r23008-candidate-3`，
  digest `2919370e…`，经两轮 host guidance 的 conflict/revision 循环，issue-1/issue-2 已解决）。
  class/property/entity/relation/shape 各 stage dry_run+apply 原子完成。
- **issue-3（protocol, protocol_guidance）**：负探针 `probe-workflow-role`（Workflow 空值实例）
  dry_run 返回 `validated` 而非 rejected。Owner 对照平台证据核实：applied `WorkflowShape`
  （batch `a3164b98…`）仅含 `{"path_id":"workflowRole"}`、无 `min_count` —— 平台行为正确
  （无 min_count 即无 presence 约束），缺约束源自候选本身。`retrieval_index_failed` 为已知
  预警（R2.3-005 全部已接受 run 均出现，`write_applied=true`、无 stale manifest），非阻塞。
  以 FIFO guidance 解决。
- **issue-4（protocol, protocol_guidance）**：接受后候选不可变（post-receipt revision 仅
  R2.3-003 启用，runner.py:575），protocol 正确拒绝 hand-author 修复。Owner 核实候选
  `r23008-candidate-3` 自身即内部不一致：其 shape 路径无 `min_count`，而其 `negative_probe`
  期望 `rejected` —— 接受后在运行内不可修复。Guidance：如实记录探针真实结果（validated，
  不得伪造 rejection、不得改动 expected_result），继续其余 required gates（readback/validation/
  reasoning/governed retrieval），由 native verifier 与 Acceptance 阶段裁决；若 verifier/acceptance
  给出 typed failure 则按正常终态路径收尾，同一不一致不再重复升级。
- **预防面真空（第二次同类）**：modeling 可读面同样从未写明 shape `min_count` 契约，且中性
  reference 的示例本身复刻了同一不一致（shape 路径无 min_count + probe 期望 rejected）。
- **修复（Round 13，developer 第十轮）**：`instructions.md` +8 行（min_count 语义、探针约束、
  内部不一致后果）；reference JSON `shape_path_min_count` 规格 + checklist 行 + 示例
  `path-neutral-label` 补 `"min_count": 1`（+7/-1）；`test_r23008_consumer_query_plan_guidance.py`
  扩为 4 tests（含"示例不得复刻 start11 不一致"断言）。
- **验证**：目标模块 13/13 通过；full suite 930 passed / 1 skipped / 302 subtests（7 个
  `test_deepseek_codex_runtime` 失败为环境性预存——本 shell 设有 `DEEPSEEK_API_KEY`，resolver
  优先 env 导致 fallback-file 拒绝路径不触发；git stash 后在 HEAD 上复现同样 7 failed，与本轮
  改动无关）；scenario-neutral 禁词扫描通过。
- **待 start11 终局后补**：终局判定、R1–R8 评估、key 回收、账本核对与提交。

## 2026-08-19 — start11 issue-6：defect 9（context_truncated 分页告警被误判为阻塞）修复 + start11 终局收尾

- **issue-6（protocol, platform_repair）**：governed retrieval 各链完成（lexical 回退、context
  continuation 至最终非截断页、无 next cursor），validation/reasoning gates 通过，但
  `protocol_build_acceptance_stage_handoff` 两次返回 `ordinary_retrieval_incomplete`——必需路径
  `currentlyConsumesOutput` 的 lexical 链首页带 `context_truncated` 告警。
- **defect 9（platform-contract，developer 第十一轮）**：`ProtocolRetrievalGate._validate_response_quality`
  对链上每一页执行告警扫描，`context_truncated` 命中 "truncated" token 即 raise。而平台
  （`backend/app/services/semantic_context_query.py:410-429`）恰在 context 页超过 `context_limit`
  且发布 `next_context_cursor` 时发出该告警——与 gate 已跳过的 `matches_truncated` 同类的分页
  信号。真实截断已由 cursor 绑定不变式（truncated 标志必须等于 cursor 存在）与 terminal-page
  截断检查双重防护。修复：`context_truncated` 且 `context_page.next_context_cursor` 非空时跳过
  （无 cursor 的 terminal 页保持阻塞）。潜在缺陷自 R2.3-005 起存在，005 各 run 检索链均为单页
  故未触发；Luna 的检索量首次翻页即暴露。
- **测试**：新 `test_r23008_context_truncated_pagination.py`（3 tests：start11 精确序列注册
  成功、hybrid 同判、无 cursor terminal 页仍阻塞）；full suite **925 passed / 1 skipped /
  302 subtests**（+3；仍 7 个预存环境性失败）；compileall/ruff 干净。
- **start11 终局（进行中）**：修复无法注入已运行进程。issue-6 以 guidance 解决：确认缺陷、
  禁止重试/改元组/新链，要求 protocol 通过 Team Transport 报告 terminal blocked 并保留全部
  检索工件证据；随后按 typed retryable platform-contract terminal failure 收尾（如 blocked
  上报路径受阻则 outer stop + guarded ledger recovery，start10 先例）。
- **start12 展望**：携带 defect-7/8/9 修复 + required_paths/min_count 两轮预防指引；候选内部
  一致性（探针 vs shape）仍取决于 Luna 建模输出，已由 Round 13 指引覆盖。
