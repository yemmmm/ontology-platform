# R2.3-007 Modeling Team Responses Provider 路由共享测试计划

- 状态：reviewed / 待实施（plan review Round 2 PASS）
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
