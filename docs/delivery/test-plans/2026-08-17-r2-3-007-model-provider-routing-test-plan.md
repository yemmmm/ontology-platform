# R2.3-007 Modeling Team Responses Provider 路由共享测试计划

- 状态：executed / Round 1–3（原合同）与 Round 4–5（变更 A：Luna Codex 订阅认证）独立测试完成——A1–A5、A7
  PASS，Round 4 发现 D1 High 修复后 Round 5 复测 PASS；A6 真实 Luna probe 待用户单独授权。G1/G3 原始论与
  followup 见 §5
- Requirement：`docs/requirements/requirements-v2.3.md#r23-007-modeling-team-responses-provider-路由与逐角色模型配置`
- Design：`docs/delivery/designs/2026-08-17-r2-3-007-model-provider-routing-design.md`
- Delivery record：`docs/delivery/records/2026-08-17-r2-3-007-model-provider-routing-delivery-record.md`

## 1. 完成门

1. 一个具名 profile 完整、不可变地绑定六角色；`validate/baseline/run` 解析一致并冻结同一 digest。
2. DeepSeek Direct 和 OpenAI Direct 只经 Responses session 工作；没有 Chat Completions/Anthropic fallback。
3. 六角色可分别配置 provider/model/requested effort；effective effort 与 capability mapping 一致且有证据。
4. 所有配置、credential、startup、upstream 和 cleanup failure 均 fail closed、typed、无自动换模。
5. credential 仍为 Host-owned；Agent/env/evidence/log/run root 无 plaintext secret；多 session 完整清理。
6. 现有 formal workflow、权限、Acceptance、R2.3-006 Examiner 隔离和默认全 DeepSeek 行为无回归。
7. 计划评审无未处置 Critical/High；实施后独立测试 PASS，失败轮保留。

## 2. 测试矩阵

### A. Profile loader 与 capability

- A1 加载 `deepseek-v4-flash-max`，六角色均得到 DeepSeek requested/effective `max/max` 和稳定 source digest。
- A2 加载 `openai-luna-medium`，六角色均得到 Luna `medium/medium`。
- A3 mixed fixture 六角色使用不同 route/effort；DeepSeek `low/medium/high -> high`、`xhigh/max -> max`，OpenAI
  六档 identity mapping。
- A4 缺任一角色、额外角色/字段、空值、重复/漂移 ID、未知 provider、provider/model cross-wire、unsupported
  effort、DeepSeek `none`、绝对/遍历/symlink path 均在副作用前拒绝。
- A5 初始 load 后替换 profile bytes；post-external-preflight digest check 拒绝，不创建 ledger/run process。

### B. CLI 与 baseline

- B1 `validate`、`baseline`、`run` 都接受 `--model-profile`，同一输入输出同一 ID/digest/effective projection。
- B2 省略参数使用 formal contract default `deepseek-v4-flash-max`，现有 R2.3-003/005 operator command 不变。
- B3 CLI 只接受 ID，不接受 path/URL/env override；non-formal fixture 不被意外提升为 formal provider route。
- B4 baseline 包含六角色 safe binding，不含 endpoint、credential path/value/digest 或 provider free text。

### C. Responses session

- C1 fake upstream：每个 session 仅监听 loopback、仅接受 bounded JSON `POST /responses`，替换 attacker auth，
  转发固定 headers，正确 stream response 和 safe counters。
- C2 profile 只引用一个 provider 时只创建一个 listener；mixed profile 恰好创建两个；同 provider 多角色共享 session。
- C3 unknown path/method/content type、oversize/malformed body、TLS/URL/startup/upstream/status/stream 失败均得到稳定
  reason code。两个 Provider 的 fake upstream 分别返回非 2xx + unique sentinel；经真实 loopback session 后 client
  只能得到固定 local failure/空 body，App Server artifact、日志和 run root 的 sentinel 匹配数为零。另用 2xx
  partial stream + transport exception 证明已发送模型 chunk 保持透明，而 exception text 不进入 client/artifact；
  不要求缓冲或撤回已发送模型输出。
- C4 OpenAI 与 DeepSeek credentials 分别执行 `0600`/owner/no-follow/metadata revalidation；任一个缺失时所有 Agent
  尚未启动且不读取不需要的 provider credential。OpenAI fixture 使用固定
  `modeling-team-openai.env`/`OPENAI_API_KEY=...` 合同；ambient env 不作为 fallback。

### D. 逐角色 Codex 投影

- D1 捕获四个 persistent role 的真实生成 TOML 和 `thread/start`，逐一等于 frozen binding；不存在默认 provider
  或 model 覆盖。
- D2 分别启动 Source/Platform Examiner fixture，证明 lookup key 精确为 canonical `source-examiner` 和
  `platform-examiner` package ID，即使两者 `AgentPackage.role` 都是 `source-specialist`，fresh child 仍使用各自
  binding、session base URL 和 effective effort。
- D3 Agent env 不含 `DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`LLM_API_KEY`；TOML 只有 loopback URL 和
  `wire_api="responses"`。
- D4 route 变化不改变任何角色的 MCP、filesystem、network、team transport、platform read/write 权限。

### E. Failure、无 fallback 与 cleanup

- E1 任一 credential/session startup 失败产生 `runtime/infrastructure` + 对应稳定 reason，零 Agent start。
- E2 mixed run 中一个 upstream 返回 4xx/5xx、断流或 timeout：latch 整个 run，停止新 turn；另一个 provider
  不接手失败角色，request count 证明 fallback 为零。
- E3 两个 session 的 stop/server_close/thread_join/socket close/key wipe 均被独立尝试；第一个 cleanup 抛错时第二个
  仍执行，aggregate report 准确。
- E4 cleanup 后 process/listener/socket/credential buffer/secret audit 全部零残留；cleanup failure 本身保持 typed
  terminal failure，不能覆盖早先 provider failure。

### F. Evidence

- F1 baseline、role start、child start、provider lifecycle、terminal report 的 profile ID/digest 与逐角色
  provider/model/requested/effective binding 可重算且一致。
- F2 secret sentinel、credential path、secret digest 和 fake provider-controlled error text 在 run root/stdout/stderr/
  evidence 中匹配数为零。
- F3 DeepSeek `low` 的证据必须同时显示 `requested=low/effective=high`；不得只写 low 或伪装模型原生支持。

### G. Bounded real Provider probes

- G1 OpenAI Luna：使用 production-equivalent loopback session 执行一个最小 Responses tool-call turn，确认 exact
  `gpt-5.6-luna`、selected effort、function call、terminal、safe usage/status 和 cleanup。
- G2 DeepSeek V4 Flash：先做无凭据 `/responses` route probe，再执行一个最小 `high` 和一个最小 `max` Responses
  tool-call/terminal probe；确认 exact model、stream/terminal、proxy 2xx 和 cleanup。若 route/schema 不成立，记为
  BLOCKED，不尝试 `/chat/completions`。
- G3 一个 mixed formal smoke 覆盖四个 persistent roles 及两个 fresh Examiner kind 的配置投影；限制为验证路由、
  tool contract、终态和 cleanup，不扩大为业务语义 A/B 或质量评测。

真实 probe 必须预先记录授权、attempt budget、目标 profile、允许的模型调用数和 cleanup owner；失败不自动追加重试。

### H. 回归

- H1 全 `modeling_team` deterministic suite、compile、lint 与 diff checks 通过。
- H2 R2.3-003/005 的 formal contract、StartLedger/baseline、candidate/Acceptance flow 保持；默认 profile 行为与当前
  DeepSeek tuple 相同。fresh run 的 contract/TeamRun/baseline/Runtime 不再读取旧 manifest，历史 run/ledger bytes
  保持不变，且 profile 切换不增加授权 start/retry。
- H3 R2.3-006 fresh Examiner、typed report、exactly-once revoke、invariance、secret audit 和 zero-residue tests 保持。
- H4 若改 Runtime，重启 `ontology-platform.service`，backend `127.0.0.1:8001` 与 frontend `5173` health 均通过。

## 3. 计划轮次

- Round 1：实现审查；A-F deterministic focused tests；完整 modeling_team 回归。
- Round 2：G1/G2 bounded direct-provider probes；发现问题回到 developer，不放宽 Responses-only 合同。
- Round 3：G3 mixed formal smoke、H2/H3/H4 回归、最终 secret/cleanup audit。
- 后续轮次只修复已确认 requirement defect；继续追加本文，不创建第二份测试计划。

## 4. 当前证据与未执行项

- 2026-08-17 无凭据 `POST https://api.deepseek.com/responses` 返回 HTTP 401，证明 route 当前存在但不证明 request
  schema、effort 或 tool semantics。
- 仓库既有真实 smoke 记录一次 DeepSeek Responses upstream 2xx、exact model、matching turn/completed 和零残留；
  它支持设计可行性，但不能替代本需求发布时的 G2。
- OpenAI 官方文档确认 Luna Responses/function calling 和六档 effort；尚未使用 OpenAI credential 或发起模型调用。
- 本计划尚未实施；没有启动 Agent、创建 ledger start、修改平台或消耗新的真实 Provider attempt。

## 5. 独立测试轮次

| Round | Stable state | Result | Defects / unexecuted | Evidence |
| --- | --- | --- | --- | --- |
| 0 | design-only draft | UNEXECUTED | implementation、A-H 均未开始 | 本文第 4 节 |
| 1 | `8ee7aa4` (worktree: only delivery-record edit pending) | PASS (Round-1 scope: gates 1-6; A-F + H1) | 无本需求 Critical/High/Medium 缺陷。G1 BLOCKED（OpenAI credential 文件不存在，且属 Round 2 授权范围）；G2/G3、H2 历史字节核对、H3/H4 留待后续轮次；完整 `run` CLI 执行留待 G3（参数传递已由单测覆盖）。发现 1 个 pre-existing Low：ambient `DEEPSEEK_API_KEY` 下 7 个 `test_fallback_file_rejects_*` 失败（父提交 `533f99e` 同样失败，非本需求引入） | 本节 Round 1 详情 |
| 2 | `8ee7aa4`（同 Round 1 稳定状态） | G2 PASS；G1 BLOCKED（credential 缺失，未发起任何 OpenAI 调用） | G2 三项探针全部通过：route 401、`high` 与 `max` 各一次最小 tool-call turn 均 2xx/stream/terminal/exact model/effort 回显，cleanup 零残留。真实模型调用消耗 2/3 上限；零重试；未触碰 ledger/平台/产品代码。剩余：G3 mixed formal smoke 与 H2/H3/H4 属 Round 3 | 本节 Round 2 详情 |
| 3 | `8ee7aa4`（同前稳定状态） | PASS（G3 按"确定性投影已覆盖 + 真实 mixed smoke BLOCKED"记录；H2/H3 全绿；H4 未触发且被动健康通过；最终 secret/cleanup 审计零发现） | G3 真实执行 BLOCKED：待 (a) 用户创建 OpenAI credential 文件、(b) formal run 的 attempt/start 预算单独授权；未以 DeepSeek-only 替代。H2 发现一处非缺陷观察：`workspaces/modeling-runs` 目录 mtime 2026-08-17T16:22（Round 1 确定性套件瞬时 create+delete），零保留文件被修改 | 本节 Round 3 详情 |

### Round 1 详情（2026-08-17，independent tester，stable state `8ee7aa4`）

实现审查（对 `git show 8ee7aa4`，18 files，全部在 `modeling_team/` 下，无 `backend/` 改动 → H4 未触发）：

- 封闭 catalog：`model_routing.py` `PROVIDER_CATALOG` 仅 `deepseek-direct`/`openai-direct`，固定 endpoint/TLS/allowlist/effort mapping/credential validator；profile schema 强制字段集 `{model_provider, model, model_reasoning_effort}`，无法声明 URL/header/credential location。
- DeepSeek effort map：`none` 不在 `effort_effective` → loader 拒绝（A4 参数化含 DeepSeek `none` case）；`low/medium/high→high`、`xhigh/max→max`，requested+effective 同时记录。OpenAI 六档 identity。
- 逐角色 examiner 键：`runtimes/codex.py` `_validated_formal_role_binding(package_id)` 按 canonical package ID 查询；实测两个 `agent-packages/{source,platform}-examiner/package.yaml` 的 `role` 均为 `source-specialist`，mixed fixture 下二者分别解析到 openai/deepseek binding（D2）。
- 单向迁移：全仓 grep 确认 `load_formal_model_manifest`/`model_manifest_path` 在 `model_manifest.py` 之外零引用；`FormalRunContract.default_model_profile_id`、`TeamRun.team_model_profile`、baseline `team_model_profile` 均已切换；旧 `model-manifests/` 仅剩历史资产。
- 非 2xx：`_SessionHandler` drain+drop upstream body，本地固定 502 空 body + `provider-upstream-failed`；2xx partial stream：已发送 chunk 保持透明，transport 异常只记固定 reason，异常字符串不外传；`_signal_failure`/`_on_provider_session_failure` 均为稳定 reason code 白名单，零 provider free text。
- Credential：OpenAI binding 复刻 DeepSeek 合同（0600/owner/非 symlink/max 4096B/精确赋值/可选单换行；prepare 只留 dev/ino/size/mtime；读取用 `O_NOFOLLOW` + fstat 复验）；无 ambient env fallback（测试在 setenv `OPENAI_API_KEY` 下仍按文件合同失败）。
- Agent env：formal TOML `shell_environment_policy.exclude = ["DEEPSEEK_API_KEY","OPENAI_API_KEY","LLM_API_KEY"]`；`thread/start.model` 精确等于 binding.model。
- Aggregate cleanup：`ProviderSessionManager.stop()` 逐 session 独立 stop/stop_snapshot/clear_secret，单失败不影响其他；runtime latch 首个 provider failure，后续 cleanup failure 不覆盖。

执行结果（全部在 `env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python` 下）：

- `pytest modeling_team/tests/test_model_routing.py -q` → **48 passed**（27 函数 + 参数化）。
- H1 全量 `pytest modeling_team/tests/ -q` → **849 passed, 1 skipped（既有 opt-in real Codex smoke）, 273 subtests passed, 0 failed**。
- `python -m compileall -q modeling_team/` → exit 0；`ruff check modeling_team/ --config backend/pyproject.toml` → All checks passed；`git diff --check 533f99e 8ee7aa4` → clean。
- B1–B4 CLI 直接探针：`validate --model-profile openai-luna-medium` exit 0，输出六角色 `gpt-5.6-luna medium/medium` + digest `d93f9305…`；省略参数 → `deepseek-v4-flash-max` 六角色 `max/max`；`--model-profile ../secrets|/tmp/profile.yaml|missing-profile` → exit 2 + 固定错误；`baseline --model-profile openai-luna-medium` → manifest `team_model_profile` digest 与 validate 完全一致，`formal_model_manifest` 键不存在，endpoint/credential 名/路径扫描零匹配；`run --help` 显示 `--model-profile`（run 的参数传递由单测 `test_run_subcommand_accepts_model_profile_and_passes_selection_to_prepare` 覆盖，完整执行留待 G3）。
- C3 第二 provider 探针（openai-direct session + fake loopback upstream 418 + unique sentinel）：client 得到 502 空 body、`failures == ["provider-upstream-failed"]`、sentinel 在 snapshot/stop_snapshot 中零匹配、`upstream_errors == 1`。URL/TLS 门：非 loopback `http://` 拒绝（TLS required）、`/chat/completions` 拒绝、带 userinfo URL 拒绝、loopback `http://` 接受（fake-upstream seam）、占用端口 bind 失败为 typed `ProviderSessionError`。
- A–F 覆盖核对：A1（`test_luna_max_model_manifest.py::test_default_profile_binds_all_six_roles_to_deepseek_max`）至 F3（`test_low_effort_evidence_records_requested_and_effective`）全部有确定性用例；E2 的 latch/无 fallback/映射不变由 `test_runtime_latches_first_provider_failure_and_cannot_be_overwritten` + 代码面无任何 fallback 路径共同证明（live mixed-run 断流行为留待 G2/G3）。F2 的 run-root 全量 sentinel 扫描由既有 start74 cleanup audit 回归覆盖，真实 run 的最终 audit 属 Round 3。

Pre-existing 失败处置（developer 声明独立复核）：ambient `DEEPSEEK_API_KEY` 导出时 `test_deepseek_codex_runtime.py::test_fallback_file_rejects_*` 7 个用例在 `8ee7aa4` 与父提交 `533f99e`（临时 worktree 实测）失败完全一致，均为 "DID NOT RAISE CodexRuntimeError"——process key 优先于 fallback file 属既有 legacy 非 formal 行为，非本需求引入；unset 后全绿。处置：记录为 pre-existing 测试环境敏感问题，建议后续单独让开发 hermetic 化（monkeypatch.delenv），不构成本需求缺陷、不阻塞 Round 1。

Round-1 范围外（后续轮次执行）：G1（BLOCKED：`~/.config/ontology-platform/modeling-team-openai.env` 不存在，且真实调用需 Round 2 单独授权）、G2/G3、H2 历史 run/ledger 字节核对与 profile 切换不增 start/retry 的账面复核、H3、H4（未触发）。

### Round 2 详情（2026-08-17，independent tester，stable state `8ee7aa4`，授权：delivery record 冻结的 G2 预算 = 1 次 route probe + 1 次 `high` + 1 次 `max`，硬上限 3 次真实 Responses 请求，失败即 BLOCKED 不重试）

G1（OpenAI Luna）— **BLOCKED（credential 缺失，非产品缺陷）**：

- `stat ~/.config/ontology-platform/modeling-team-openai.env` → ENOENT（仅 stat，未读取、未创建）。
- 未发起任何 OpenAI 网络调用。解除条件：用户按设计 §6.2 创建该文件后补跑 G1（需再次授权）。

G2（DeepSeek V4 Flash）— **PASS**，三项全部首次通过、零重试：

- G2a route probe（无凭据、不经 session、无 Authorization）：`POST https://api.deepseek.com/responses` → **HTTP 401**（body "Authentication Fails"，content-type 未返回）。证明 route 当前存在（非 404/405），与设计 §4.2 预期一致；不消耗模型调用。
- G2b `high` / G2c `max`：使用**生产等价路径**——`preflight_deepseek_credential()`（默认 Host 文件，0600/owner 53B）+ `ProviderSessionManager({"deepseek-direct": binding})` + `ResponsesProviderSession` loopback（与 `CodexRuntimeAdapter` 同一代码路径，非定制 client）。客户端故意注入 `Authorization: attacker-injected-header`，session 照常替换为 Host key 并成功（200 证明 inbound auth replacement 生效）。每次运行恰好一个请求（single-shot 脚本，无重试逻辑）。
- 两次探针共同证据（`high` / `max`）：
  - upstream 经 loopback session 返回 **200**，`text/event-stream`，SSE 全生命周期事件序列 `response.created → in_progress → reasoning_text.delta* → (output_text.delta*) → function_call_arguments.delta → response.completed`（34/49 个增量 chunk，流式透明转发）；
  - **exact model 回显 `deepseek-v4-flash`**；terminal `status="completed"`；
  - **tool-call round trip**：output items 含 `function_call name="get_probe_value"`、`call_id` 存在、`arguments="{}"`（单次请求内完成 tool-call + terminal，未追加第二轮调用）；
  - **requested/effective effort**：请求 `reasoning.effort` 分别为 `high`/`max`，catalog 映射 `high→high`、`max→max`，响应 `reasoning` 回显 `{'effort': 'high'}` / `{'effort': 'max'}`；
  - **safe usage**：`high` input 352（cached 256）/output 43（reasoning 13）/total 395；`max` input 365/output 68（reasoning 24）/total 433；
  - **safe status counters**：`requests=1, upstream_errors=0, rejected=0, client_disconnects=0`；`on_failure` 回调为空（零 provider failure latch）；
  - **cleanup 零残留**：`stop()` 报告 `shutdown_ok/server_close_ok/thread_joined=True, thread_alive=False, socket_open=False, lifecycle_failure=False`；session key buffer stop 后 0 字节（全零）；manager sessions 清空、`listening=False`、无 `formal-provider-session-*` 残留线程；stop 后 `base_url_for` 为 typed refusal。
- 模型调用消耗：**2 / 3**（route probe 401 不计）。探针脚本用后即删；未创建 run root（`workspaces/modeling-runs` 零 r23007 条目）、无 ledger start、无平台写入、未修改任何产品/设计/需求/交付记录文件。

Round-2 范围外：G3 mixed formal smoke、H2（历史 run/ledger 字节与 start/retry 账面复核）、H3、最终 secret/cleanup audit——属 Round 3；G1 待 credential 就绪后另行授权补跑。

### Round 3 详情（2026-08-17，independent tester，stable state `8ee7aa4`，零真实 Provider 调用）

G3 — 拆分记录：

- **确定性逐角色投影（已覆盖）**：Round 1 D1/D2 证据——mixed fixture 下四个 persistent role 的真实生成 TOML（model/provider/effective effort/base_url/wire_api/env exclude）与 `thread/start.model` 逐一等于 frozen binding，无默认 provider/model 覆盖；Source/Platform Examiner 两个 fresh child kind 按 canonical package ID（`source-examiner`/`platform-examiner`）解析到各自 provider 的独立 session base URL 与 effective effort，尽管二者 `AgentPackage.role` 均为 `source-specialist`。
- **真实 mixed formal smoke：BLOCKED**，解除条件：(a) 用户按设计 §6.2 创建 `~/.config/ontology-platform/modeling-team-openai.env`（本轮再次 stat 确认仍不存在）；(b) 用户单独授权一次 formal run 的建模 attempt/start 预算（StartLedger 记账）。明确未以 DeepSeek-only run 替代（不满足 "mixed" 且会消耗预算），未创建任何 ledger start 或 run root。

H2 — formal/回归（全绿，`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest … -q`）：

- 默认 profile = 原 DeepSeek tuple：`test_luna_max_model_manifest.py + test_r23003_incremental_contract.py + test_r23005_contracts.py` → **84 passed, 23 subtests**（含 `test_default_profile_binds_all_six_roles_to_deepseek_max` 与 formal contract gate）。
- StartLedger 授权不变量：`test_start_ledger_r63.py + test_r23005_ledger_isolation.py + test_r23005_budget_extension.py` → **30 passed, 22 subtests**。
- fresh run 不读旧 manifest：Round 1 全仓 grep（`load_formal_model_manifest`/`model_manifest_path` 定义模块外零引用）+ 上述套件内 gate 测试共同证明。
- 历史证据完整性：`workspaces/modeling-runs`（188 个 run root）无任何 r2-3-007/r23007 条目（4 个 "007" 命中均为 2026-07-22 的 `r11007-live-*`，属 R1.1 历史）；三个 StartLedger `.jsonl`（94/66/332 条）`grep -c r23007` 均为 0，最后条目时间 2026-08-06/08-10/08-12；`find . -newermt 2026-08-16` 仅命中目录自身 mtime `2026-08-17T16:22`（Round 1 确定性套件的瞬时 create+delete 所致），**零保留文件**在 2026-08-16 后被修改。

H3 — R2.3-006 回归：`test_r23006_acceptance_operation.py + test_r23006_lean_runtime.py + test_start44_examiner_contract.py + test_start74_cleanup_audit.py + test_examiner_stdout_pump.py + test_candidate_platform_gate.py + test_deepseek_provider_proxy.py` → **96 passed, 55 subtests**（fresh examiner、typed report、exactly-once revoke、invariance、secret audit、zero-residue 全保持）。

H4 — 条件重启门：`git show 8ee7aa4 --stat` 18 文件全部在 `modeling_team/` 下，`backend/` 命中数为 0 → 门未触发，未重启。被动健康检查：`curl --fail http://127.0.0.1:8001/api/health` → HTTP 200；`curl --fail http://127.0.0.1:5173/` → HTTP 200。

最终 secret/cleanup 审计（零发现）：

- 四份 scope 文档（requirement §R2.3-007、design、本计划、delivery record）与 `git show 8ee7aa4` diff：`sk-[a-z0-9]{16,}` 等 secret-shaped 模式零命中；全部 `*_API_KEY=` 出现均为设计占位符（`<non-whitespace-value>`、`OPENAI_API_KEY=...` 合同记法）或测试 sentinel；本轮已知的 ambient DeepSeek key 字符串在仓库文件中零出现。DeepSeek credential 文件值从未被读取进任何文档/脚本输出。
- 残留：`/tmp` 无 `mt-ex-*`、无 `r23007*` 探针文件（两轮探针脚本均已即用即删）；`ss -ltnp` 仅见既有服务（uvicorn 8001、knowledge-base 8083），Round 2 probe 端口（45007/56579）零残留 listener；无 probe 残留进程。
- 测试数据归属：Rounds 1–3 在仓库内唯一写入为本测试计划 §5 的三轮追加；无其他测试产物保留。

**总体建议**：close-with-followups——R2.3-007 实现按本计划可判定范围（A-F、H1-H4、G2）全部通过，无产品缺陷；followups：(1) G1 待 OpenAI credential 就绪后授权补跑；(2) G3 真实 mixed formal smoke 待 (a)(b) 双条件；(3) pre-existing Low：`test_deepseek_codex_runtime.py` 7 个 fallback 用例建议 hermetic 化（`monkeypatch.delenv`）。

## 6. 实施中变更 A 测试增量（2026-08-17，executed：Round 4 FAIL→D1 修复→Round 5 PASS；A6 待授权）

本节对应设计 §12，只追加新合同，不改写 Rounds 0–3 的历史结论。原 G1/G3 关于 OpenAI API credential 文件
缺失的 BLOCKED 证据仍有效，但不再是修订后测试的前置条件。

- A1：`openai-luna-medium` 和 mixed profile 解析为 `openai-codex`，六个 canonical package binding 与
  requested/effective effort 精确；catalog 不再包含 `openai-direct`。
- A2：Host ChatGPT file-backed login preflight 成功；缓存缺失/不安全和 API-key login 分别返回
  `codex-subscription-auth-unavailable`/`codex-subscription-auth-mode-mismatch`，且发生在 reservation/Agent
  start 前；相同缺失条件下 DeepSeek-only prepare/run 不触发 ChatGPT preflight。
- A3：OpenAI-only run 不读取 OpenAI credential 文件或 ambient `OPENAI_API_KEY`，不创建 OpenAI loopback
  session；DeepSeek 默认 path 不发生行为变化。
- A4：OpenAI-only runtime 接受 empty external-session map、不创建 manager；mixed manager 只含 DeepSeek。
  OpenAI 持久 role/两个 fresh Examiner 的实际 TOML 为内建 `model_provider="openai"` 且无 provider table/base
  URL/session lookup；DeepSeek role/Examiner 只获得 loopback route。active-run fixture 证明 private auth 仅在
  OpenAI Codex 初始化窗口存在并在任何模型选择的 ServerRequest/tool/MCP dispatch 前删除；无 cross-role
  credential projection，cleanup 后无 `auth.json`、listener、thread 或 secret residue。
- A5：safe baseline/evidence 记录 `provider=openai-codex` 和 `auth_mode=chatgpt-subscription`，不记录 token、
  account/workspace、auth cache path/digest 或 `codex login status` 原始输出。
- A6：在用户单独授权一次无业务 Provider probe 后，通过 Codex 订阅认证运行 Luna Responses
  tool-call/terminal smoke，核对 exact model、effort、typed failure、零 fallback 和零 secret/residue。
- A7：重跑原 A-F/H1-H4 受影响回归；保留 Rounds 0–3，不以本节结果改写原 implementation PASS。

实施与独立测试已完成（implementation `52dde1f` + 缺陷修复 `5791492`；Round 4/5 详情见本节末尾）。A6 待用户
单独授权后执行。

### Round 4 详情（2026-08-17，independent tester，stable state `52dde1f`，零真实模型调用）

稳定状态：implementation commit `52dde1f`（父提交 `022c8f5`），工作树仅剩 delivery record 的 pending 编辑（主代理
所有，本轮未触碰）。本轮为实施中变更 A（设计 §12）的独立测试轮，执行 A1–A5、A7 与真实 Host preflight 行为
检查；A6 需用户单独授权，记为范围外，未发起任何真实模型调用。

**总体结论：FAIL（High，单缺陷 D1）**——确定性合同面全部通过，但真实 Host（已 `Logged in using ChatGPT`）上
subscription preflight 误判为 `codex-subscription-auth-unavailable`，阻塞设计 §12.6 验收条件 1 的主路径。

实现审查（对 `git show 52dde1f`，8 文件全部在 `modeling_team/` 下，`backend/`/`frontend/` 命中 0 → H4 未触发）：

- catalog：`PROVIDER_CATALOG` 仅 `deepseek-direct`/`openai-codex`；`openai-codex` 的 `upstream_url`/`credential_env`
  为 `None`，`uses_external_credential=False`。全仓产品代码 grep `openai-direct`/`preflight_openai_credential`/
  `read_openai_credential`/`modeling-team-openai` 零命中；OpenAI API Key parser/binding/preflight 已整体删除。
- conditional pre-reservation preflight：`runner.py` 两个分支（fresh 与 R2.3-003 deferred）中
  `preflight_codex_subscription_auth()` 均先于 `preflight_profile_credentials()`（即 DeepSeek credential read）、
  ledger reservation、run-root 创建与 Agent start 执行；`profile_requires_codex_subscription_auth()` 为假时
  DeepSeek-only profile 零触发。
- CLI：`__main__.py` 无条件 post-prepare `preflight_host_auth` 调用已删除；`test_cli_does_not_probe_host_auth_after_prepare`
  事件序为 `runner-init, prepare, start, cleanup`。
- manager 边界：`_start_runtime` 仅对 `uses_external_credential_session` 过滤后的 provider 创建
  `ProviderSessionManager`；OpenAI-only 零 manager、`provider_sessions=None` 被接受；mixed manager 只含
  `deepseek-direct`，`ProviderSessionManager` 构造函数拒绝内建 route。
- TOML 投影：`_formal_codex_builtin_config_lines` 产出 `model_provider = "openai"`（`CODEX_TOML_PROVIDER_ID`），
  无 `[model_providers.*]` table、无 `base_url`、无 `env_key`、无 session lookup；持久角色与两个 fresh Examiner
  走同一分支（`uses_external_credential_session(provider_id)` 判定）。
- auth staging/barrier：formal `openai-codex` 角色/child 设 `credential_mode="file_auth"`、
  `auth_barrier_pending=True`、`auth_path=<home>/auth.json`，复用既有 staging/barrier；formal external-route 角色
  `auth_path=None` + `provider_proxy`——auth.json 不投影给 deepseek-direct 角色。
- evidence：`RoleModelBinding.as_dict` 仅追加固定 `auth_mode="chatgpt-subscription"`；runner 私有
  `codex_subscription_auth_mode` 只存固定 label；`runner.py:1033` 的 `"auth_mode": "0600"` 为既有 private_runtime
  文件权限合同键，与本修订无关。auth cache 内容零读取（`model_routing.py` 仅 lstat + `codex login status`
  模块内解析）。

执行结果（`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python`）：

- H1 全量 `pytest modeling_team/tests/ -q` → **859 passed, 1 skipped（既有 opt-in real Codex smoke）, 273 subtests
  passed, 0 failed**（43.66s），与开发自报一致。
- A7 回归：`test_r23003_incremental_contract.py + test_r23005_contracts.py + test_luna_max_model_manifest.py +
  test_r23006_acceptance_operation.py + test_r23006_lean_runtime.py + test_start44_examiner_contract.py +
  test_start74_cleanup_audit.py + test_deepseek_provider_proxy.py` → **166 passed, 78 subtests passed**。
- `compileall -q modeling_team/` → exit 0；`ruff check modeling_team/ --config backend/pyproject.toml` → All
  checks passed；`git diff --check 022c8f5 52dde1f` → clean。
- A1：`test_openai_profile_binds_all_six_roles_to_luna_medium`、`test_mixed_profile_routes_each_role_with_capability_effort`
  PASS（全量内）。
- A2（确定性部分）：`test_subscription_preflight_*` 5 项、`test_runner_subscription_preflight_precedes_credentials_and_reservation`、
  `test_runner_subscription_preflight_failure_fails_closed_before_reservation`、
  `test_runner_deepseek_only_profile_never_triggers_subscription_preflight` PASS。
- A3：`test_codex_route_reads_no_openai_credential_or_ambient_key`、`test_deepseek_default_credential_path_is_unchanged`、
  `test_openai_only_runtime_needs_no_provider_sessions_or_bindings` PASS。
- A4：`test_persistent_role_projection_equals_frozen_mixed_bindings`、`test_examiner_children_route_by_canonical_package_id`、
  `test_openai_role_staged_auth_exists_only_through_first_turn_barrier`、`test_openai_role_staged_auth_is_removed_by_cleanup`
  PASS。
- A5：`test_baseline_projects_safe_profile_binding_without_provider_text`、
  `test_codex_role_evidence_records_provider_model_effort_and_safe_auth_mode` PASS。

**真实 Host preflight 行为检查（A2 行为面）— FAIL（缺陷 D1）**：

- 只读验证 `codex_auth_cache_path()` lstat：存在、非 symlink、mode 0600、uid 1000——metadata 合同满足。
- `preflight_codex_subscription_auth()`（真实 Host）→ raise `CodexSubscriptionAuthError
  reason=codex-subscription-auth-unavailable`。该调用只运行 `codex login status`，未读 token、未发模型调用。
- 诊断：Host `codex-cli 0.147.0` 的 `codex login status` 返回 **rc=0、stdout 0 字节、stderr 24 字节
  `Logged in using ChatGPT`**（关键词经 grep 确认，账户信息未记录）。而 `model_routing.py
  _run_codex_login_status` 只返回 `completed.stdout`，丢弃 stderr，导致 `_codex_login_mode_conclusion(0, "")`
  落入"无法判定登录方式"分支。
- 影响：设计 §12.6 验收条件 1（Host 已 ChatGPT 登录时选择 `openai-luna-medium` 应可启动）被阻塞；当前真实
  Host 上 Luna profile 的 prepare 阶段即 fail closed，未来授权的 A6 probe 也会被同一层阻塞。
- 单测未拦截的原因：全部新测试通过 `login_status` 注入 seam 伪造 stdout 输出，从未对真实 CLI 的流走向执行。
- 严重程度：High（fail-closed 方向安全：不泄密、不误入 API 计费路径；但完全阻断本修订的主路径并误报健康
  Host 登录为 unavailable）。
- 建议修复（供开发参考）：`_run_codex_login_status` 合并捕获 stderr（如 `stderr=subprocess.STDOUT` 或拼接
  `completed.stderr`），保持输出仍只留在模块内固定模式解析；并补一条模拟"消息在 stderr"形态的用例。

对抗探针（临时脚本即用即删）：

- P1 伪造 API-key 登录 stdout → `codex-subscription-auth-mode-mismatch`；P4 非零 rc → unavailable；P5 symlink
  cache / P6 0644 cache / P9 缺失 cache / P10 缺失 home → `codex-subscription-auth-unavailable`（P9/P10 同时证明
  cache 预检失败时 `codex login status` 不会被调用）；P7 合法 0600 cache + ChatGPT 登录 → `chatgpt-subscription`；
  P8 ambient `OPENAI_API_KEY=sk-probe-ambient-injected` 注入下 preflight 照常通过且从不读取该 env。
- P3 观察（Low，非缺陷）：stdout 同时含 "api key" 与 "ChatGPT" 时 chatgpt 分支优先；真实 CLI 输出为固定短句，
  当前不构成误判面，但 D1 修复若拼接 stdout+stderr 应保持关键词判定顺序并考虑 API-key 优先。
- secret/cleanup 审计：`git show 52dde1f` 中 `sk-` 形态命中均为测试 sentinel 且带不泄漏断言；产品代码
  `OPENAI_API_KEY` 仅出现在 `shell_environment_policy.exclude`；`model_routing.py` 对 auth cache 零内容读取；
  本轮零 run root、零 ledger start、零平台写入；本轮探针临时文件全部删除。观察项：`/tmp/mt-ex-cc049fe4e8a712af6beff79b`
  （含 report.sock，mtime 2026-08-17 19:53:36）为本轮开始前开发验证运行遗留的 examiner 残留，非本轮产物，
  未代为删除；`/tmp/r23003-pre-send-probe`、`/tmp/r23006_app_server_probe.py` 为 Rounds 0–3 时期既有文件。

缺陷清单：

- **D1（High）**：`modeling_team/model_routing.py::_run_codex_login_status` 只捕获 `codex login status` 的 stdout，
  而当前 Host codex-cli 0.147.0 将 `Logged in using ChatGPT` 写到 stderr；真实 Host 已 ChatGPT 登录仍被判定
  `codex-subscription-auth-unavailable`。复现：Host 上 `PYTHONPATH=backend:. backend/.venv/bin/python -c
  "from modeling_team.model_routing import preflight_codex_subscription_auth; preflight_codex_subscription_auth()"` →
  抛 `CodexSubscriptionAuthError`（对照：`codex login status 2>&1 >/dev/null` 输出 `Logged in using ChatGPT`，rc=0）。
  期望：返回 `chatgpt-subscription`。证据见上文本节。
- D2（Low，观察）：`_codex_login_mode_conclusion` 关键词判定顺序在双关键词输出下偏 chatgpt；建议随 D1 修复一并
  处理，非独立阻塞项。

范围外：A6（真实 Luna probe）待用户单独授权；D1 修复并复测通过前，A6 即使授权也会在 prepare 层被阻塞。
建议主代理让需求开发 agent 修复 D1（`_run_codex_login_status` 捕获 stderr）后发起下一轮复测（复测重点：真实
Host preflight 返回 `chatgpt-subscription`、既有 859 套件保持全绿、新增 stderr 形态用例）。

### Round 5 详情（2026-08-17，independent tester，stable state `5791492`，零真实模型调用）

稳定状态：`5791492 Fix subscription preflight stderr capture`（在 `52dde1f` 之上），工作树仅剩 delivery record 与
本测试计划的 pending 编辑（非产品代码）。本轮复测 Round 4 缺陷 D1/D2 的修复及修复引入缺陷（开发曾误将
`capture_output=True` 与 `stderr=` 组合导致真实 Host `ValueError`，主代理已改 PIPE 形式并验证）后的最终形态。

**总体结论：PASS（Round-5 范围：D1/D2 修复验证 + A1/A3/A4/A5 抽查回归；A6 仍范围外）**

实现审查（对 `git show 5791492`，2 文件均不在 `backend/`/`frontend/` → H4 未触发）：

- `_run_codex_login_status` 改为 `stdout=subprocess.PIPE, stderr=subprocess.STDOUT`（合法组合，stderr 合并进返回
  流），`text=True/timeout=30/check=False` 与 env 注入保持不变；docstring 明确 codex-cli 0.147.0 的 stderr 形态。
- `_codex_login_mode_conclusion`（D2）：API-key 提示判定移到 ChatGPT 判定之前，歧义输出 fail 向
  mode-mismatch；三个分支 reason/message 均为固定常量。
- 新增测试 `test_subscription_preflight_reads_login_mode_written_to_stderr`（monkeypatch `subprocess.run`，断言
  `stderr == subprocess.STDOUT` 且 stderr-only 形态解析成功）与
  `test_subscription_preflight_api_key_hint_wins_over_chatgpt_text`。二者均 monkeypatch `subprocess.run`，无法捕获
  参数组合层面的 `ValueError`——该覆盖缺口由本轮 R5-2 真实调用路径探针补验（见下）。

真实 Host 行为验证（只运行 `codex login status`，不读 token、零模型调用；临时探针脚本即用即删）：

- R5-1 无注入全生产路径：`preflight_codex_subscription_auth()` → **`chatgpt-subscription`**（Round 4 D1 复现命令
  同路径，现返回期望值）。
- R5-2 无 monkeypatch 真实调用路径：`_run_codex_login_status(~/.codex)` 直接执行 → `rc=0`、合并输出 24 字节、
  含 `chatgpt`、不含 `api key`——证明真实 `subprocess.run` 调用的参数组合合法（若 `capture_output` 与 `stderr=`
  误组合会在此抛 `ValueError`），且 stderr 文本已并入解析流。
- R5-3 判定面：`_codex_login_mode_conclusion(0, "Logged in using an API key\n")` → mode-mismatch；歧义
  `"auth via API key (not ChatGPT)"` → mode-mismatch（D2 修复后 API-key 优先）；非零 rc → unavailable。

回归结果（`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python`）：

- H1 全量 `pytest modeling_team/tests/ -q` → **861 passed, 1 skipped（既有 opt-in）, 273 subtests passed, 0 failed**
  （43.52s），与预期一致（859 + 2 新测试）。
- `test_model_routing.py` 单文件 → **60 passed**；`compileall -q modeling_team/` exit 0；
  `ruff check modeling_team/ --config backend/pyproject.toml` All checks passed；
  `git diff --check 52dde1f 5791492` clean。
- A3/A4/A5 抽查（含 cross-role auth 隔离与 cleanup 零残留）：
  `test_openai_only_runtime_needs_no_provider_sessions_or_bindings`、
  `test_codex_route_reads_no_openai_credential_or_ambient_key`、
  `test_persistent_role_projection_equals_frozen_mixed_bindings`、
  `test_openai_role_staged_auth_exists_only_through_first_turn_barrier`、
  `test_openai_role_staged_auth_is_removed_by_cleanup`、
  `test_codex_role_evidence_records_provider_model_effort_and_safe_auth_mode`、
  `test_start74_cleanup_audit.py`、`test_luna_max_model_manifest.py` → **36 passed**，无回归。
- secret 审计：`git show 5791492` 无 secret 形态命中；本轮零 run root、零 ledger start、零平台写入、零临时文件
  残留。

缺陷状态：D1 **FIXED**（真实 Host 返回 `chatgpt-subscription`）；D2 **FIXED**（API-key 提示优先，歧义 fail 向
mode-mismatch）；修复引入的 `capture_output` 组合缺陷已由 PIPE 形式消除并经 R5-2 真实路径验证。本轮无新缺陷。

遗留观察（非缺陷）：两个新测试依赖 monkeypatch `subprocess.run`，参数组合合法性只有真实调用路径可证；建议后续
在开发侧为 `_run_codex_login_status` 补一条不 mock 的参数冒烟（或接受由本轮 R5-2 一次性人工验证覆盖）。

范围外：A6（真实 Luna probe）仍待用户单独授权；D1 已修复，授权后 A6 不再被 prepare 层阻塞。
