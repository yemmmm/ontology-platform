# R2.3-007 Modeling Team Responses Provider 路由交付记录

- Requirement source: `docs/requirements/requirements-v2.3.md#r23-007-modeling-team-responses-provider-路由与逐角色模型配置`
- Status: design-complete（reviewed；implementation pending）
- Started: 2026-08-17T14:25:49+08:00
- Last updated: 2026-08-17T15:03:12+08:00
- Design: `docs/delivery/designs/2026-08-17-r2-3-007-model-provider-routing-design.md`
- Shared test plan: `docs/delivery/test-plans/2026-08-17-r2-3-007-model-provider-routing-test-plan.md`
- Delivery baseline: `6a0331e Close R2.3-006 with full N=2 live-124 PASS`；初始工作树 clean
- Delivery commit: subject `Design Modeling Team provider routing`；本记录随同一提交交付，使用
  `git log -- docs/delivery/records/2026-08-17-r2-3-007-model-provider-routing-delivery-record.md` 解析 immutable hash

## Confirmed contract

- Current behavior: formal manifest 与 Runtime 把六个 package 锁定为
  `deepseek-v4-flash/deepseek/max`，Runner/Runtime 只持有一个 DeepSeek credential/proxy。
- Target behavior: 增加 Responses-only Model Routing/Provider Session 层；首期支持 DeepSeek Direct
  `deepseek-v4-flash` 与 OpenAI Direct `gpt-5.6-luna`，六角色分别配置模型和 reasoning effort。
- In scope: run 前 model profile 选择与摘要冻结、逐角色 capability 校验、按实际 Provider 建立 Host-owned
  session、逐角色有效配置证据、多 Provider cleanup。
- Non-goals: 非 Responses 协议、OpenCode Go Chat Completions bridge、运行中热切换、fallback/负载均衡/成本
  路由、质量 A/B、动态插件系统、UI、Semantic Platform Core 或角色语义变更。
- Acceptance summary: 两个 Responses Provider 的配置/运行/工具调用/终态、六角色独立绑定、requested/effective
  effort、secret isolation、typed failure、cleanup 和现有 Team/R2.3-006 回归均须形成独立证据。
- Refinement: 用户确认新增 Provider 层、DeepSeek V4 Flash、OpenAI Luna、逐角色 effort，并进一步确认当前设计
  不考虑非 Responses 接口。用户选择 Provider 不可用时 fail closed、不自动 fallback，并选择具名 Team Model
  Profile 作为 fresh run 的快速切换入口；reasoning effort 使用统一档位和 Provider 显式映射。

## Timeline

### 2026-08-17T14:25:49+08:00 — source/current-state audit — main agent

- Context: 用户要求完成多 Provider 与逐角色 reasoning 配置设计，并把范围收缩为 Responses-only。
- Evidence: HEAD `6a0331e`；初始工作树 clean；`modeling_team/model_manifest.py` 固定
  `FORMAL_MODEL_TUPLE`；`runner.py`/`runtimes/codex.py` 分别持有单一 DeepSeek credential binding/proxy。
- Action/decision: 建立 R2.3-007 Draft；复用现有 manifest、Provider proxy 安全边界、Team Runtime 和
  R2.3-006 Examiner 合同，不重建 Team workflow。
- Outcome/next step: 按 requirement-delivery 一次确认一个关键功能决策；先确认 Provider 故障是否允许 fallback。

### 2026-08-17T14:32:18+08:00 — fail-closed decision — user/main agent

- Context: Provider 在 preflight、启动或运行中可能不可用。
- Evidence: 用户选择方案 A。
- Action/decision: 当前 run 以 typed `runtime/infrastructure` failure 终止；禁止自动 fallback 或隐式换模。
- Outcome/next step: 配置和运行证据保持可复现；继续确认快速切换的配置入口。

### 2026-08-17T14:37:11+08:00 — named profile decision — user/main agent

- Context: 快速切换需要在可复用性与最小配置结构之间选择。
- Evidence: 用户选择方案 A。
- Action/decision: 使用具名 Team Model Profile，完整保存六角色的 provider/model/reasoning effort；fresh run
  通过 profile ID 选择并冻结配置。
- Outcome/next step: 不要求逐次编辑六份 package manifest；继续确认 reasoning effort 的跨 Provider 语义。

### 2026-08-17T14:39:12+08:00 — unified effort decision — user/main agent

- Context: OpenAI Luna 与 DeepSeek V4 Flash 支持的原生 reasoning effort 集合不同。
- Evidence: 用户选择方案 A。
- Action/decision: profile 统一使用 `none/low/medium/high/xhigh/max`；Provider capability 显式转换并同时记录
  requested/effective effort，未声明映射时 preflight 拒绝。
- Outcome/next step: 功能细化完成；进入外部能力与现有 Runtime 边界探针。

### 2026-08-17T14:43:15+08:00 — risk probes and design draft — main agent

- Context: 设计依赖 Luna/DeepSeek 的 Responses、effort、tool call 能力，以及当前 Runtime proxy/cleanup 边界。
- Evidence: OpenAI 官方 Luna/Model guidance 确认 Responses、function calling 和六档 effort；DeepSeek 官方公开页
  仅列 Chat Completions/Anthropic，但无凭据 `POST /responses` 当前返回 HTTP 401，仓库既有真实 smoke 记录一次
  exact V4 Flash Responses upstream 2xx、terminal 和零残留。当前 proxy 是透明 `/responses` forwarder，不做协议转换。
- Action/decision: OpenAI 六档 identity mapping；DeepSeek `low/medium/high -> high`、`xhigh/max -> max`，`none`
  在 Responses-only 首期拒绝。DeepSeek route 标记为行为实证但非公开合同，发布前 live probe 失败则 BLOCKED，
  禁止 Chat Completions fallback。设计采用 closed catalog、具名 profile、run-owned session map 和 aggregate cleanup。
- Outcome/next step: 已写一份设计与一份共享测试计划，进入 mandatory plan review。

### 2026-08-17T14:59:06+08:00 — plan review Round 1 disposition — plan reviewer/main agent

- Context: reviewer 对 requirement/design/test plan 与真实 Runtime/Runner/credential/proxy 路径做 Critical/High
  核对；用户再次要求避免低概率防御与过度设计。
- Evidence: 结论 `REVISE`，保留三个代码可证 High：OpenAI credential 最小合同缺失；新 profile 替换旧 manifest
  的 fresh-run 权威迁移不明确（含 Examiner role/package ID 碰撞）；现有 proxy 会把非 2xx Provider body 原样返回。
- Action/decision: 三项均记为 `accepted-high`。设计补充固定 OpenAI `0600` 文件/assignment/O_NOFOLLOW binding，
  不做 registry/轮换/env fallback；明确 TeamModelProfile 一次性成为 fresh-run 唯一来源、旧 manifest 仅作历史资产、
  canonical package ID lookup；非 2xx/stream failure 丢弃 upstream body，只返回固定 local failure。测试计划增加
  对应 fixture/sentinel/迁移回归。pre-run failure 只返回 typed result，不伪造 run evidence。
- Outcome/next step: `git diff --check` PASS；把修订后的设计/测试计划送回同一 reviewer 做 Round 2。

### 2026-08-17T15:03:12+08:00 — plan review Round 2 — plan reviewer/main agent

- Context: reviewer 复核 Round 1 三项 accepted-high 的修订，不扩展到低概率防御或未来通用框架。
- Evidence: 结论 `PASS`。固定 OpenAI credential 合同、fresh-run 单向 profile 迁移/canonical package ID、非 2xx
  body drop 与 2xx partial stream 边界均闭环；未发现新的 Critical/High。
- Action/decision: 设计和共享测试计划标记 reviewed；需求状态更新为 `Design-reviewed`。当前不实施产品代码，
  不运行真实 Provider G1/G2/G3，也不宣称功能可用。
- Outcome/next step: 完成文档检查并提交设计；后续实施必须复用本设计、测试计划和交付记录。

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |
| 1 | `REVISE`：OpenAI credential contract 缺失 | accepted-high | 当前仅有 DeepSeek binding/Runner path | 增加固定 OpenAI 文件合同和 C4/G1 |
| 1 | `REVISE`：新 profile 的 authoritative transition 与 Examiner key 不明确 | accepted-high | 旧 manifest/tuple/single proxy 是 fresh-run hard gate；两个 Examiner role 同名 | 明确一次性迁移、package ID lookup、H2/D2 |
| 1 | `REVISE`：非 2xx Provider body 可直通 Agent | accepted-high | 现有 `_ProxyHandler` 对 status>=400 仍 stream body | 明确 drain/drop + fixed local failure + sentinel test |
| 2 | 上述三项修订复核 | PASS | reviewer 重读 current filesystem；无新 Critical/High | 设计可实施 |

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |
| 0 | `6a0331e` + requirement/design/test-plan/record draft | Design only；未修改产品代码 | `git diff --check` PASS | plan review pending |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| 0 | requirement draft | UNEXECUTED | design/test plan/implementation 均未开始 | pending |

## Final verification

- Required checks: `git diff --check` PASS；四个 scope 文档 secret-shaped scan 无真实 credential（仅设计占位符）
- Runtime/restart health: 本阶段只改文档，未改 Runtime；不执行重启或 health probe
- Documentation/status sync: requirement、reviewed design、reviewed shared test plan 与本记录已同步
- Cleanup: 未启动模型、Provider、平台写入或 semantic start
- Residual risks and follow-ups: OpenCode Go 非 Responses 路径明确排除；DeepSeek Responses route 未出现在当前
  官方 endpoint 文档，必须以发布前 bounded live probe 为完成门

## Retrospective

- Scope or design deviations: 无；用户确认的 Responses-only、fail-closed、named profile、统一 effort 均保留
- Rework and root causes: Round 1 暴露三个现有代码边界未写实；按最小可实施合同补齐后 Round 2 PASS
- What shortened or delayed delivery: 复用现有六角色 manifest 和已验证 Provider proxy/cleanup 边界
- Reusable lessons: Provider、model、role binding 与 wire protocol 必须分离命名；同名模型经不同 Provider 提供时
  必须保留不同 route identity
