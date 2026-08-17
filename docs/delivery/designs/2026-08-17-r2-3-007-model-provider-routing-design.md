# R2.3-007 Modeling Team Responses Provider 路由设计

- 状态：implemented / 独立测试 PASS（implementation commit `8ee7aa4`；测试计划 Round 1–3 记录全部证据；
  G1 OpenAI live probe 与 G3 真实 mixed formal smoke 因 OpenAI credential 缺失记 BLOCKED，为已记录 followup）
- Requirement：`docs/requirements/requirements-v2.3.md#r23-007-modeling-team-responses-provider-路由与逐角色模型配置`
- Test plan：`docs/delivery/test-plans/2026-08-17-r2-3-007-model-provider-routing-test-plan.md`
- Delivery record：`docs/delivery/records/2026-08-17-r2-3-007-model-provider-routing-delivery-record.md`

## 1. 目标

让同一套 formal Modeling Team workflow 在 fresh run 启动前选择一个具名 Team Model Profile，并让
Coordinator、Modeling、Protocol、Acceptance、Source Examiner、Platform Examiner 六个角色分别使用 profile
中声明的 Responses Provider、模型和 reasoning effort。首期支持：

- `deepseek-direct/deepseek-v4-flash`；
- `openai-direct/gpt-5.6-luna`。

切换只影响模型执行路由，不改变角色职责、消息协议、平台权限、Acceptance 标准、StartLedger 或 Examiner
隔离合同。

## 2. 已冻结功能合同

1. 启动入口接受 `--model-profile <profile-id>`；未传时使用 formal run contract 的默认 profile，保证现有命令
   继续得到全 DeepSeek 配置。`validate`、`baseline` 和 `run` 使用同一选择结果。
2. profile 必须一次完整声明六个角色，不提供局部继承、运行时 patch 或环境变量覆盖。修改或新增一个 repository-
   owned profile 后，下一次 fresh run 即可选择；同一 run 中途不换模。
3. profile 统一接受 `none/low/medium/high/xhigh/max` requested effort；Provider capability 显式解析 effective
   effort，并在任何运行副作用前完成校验。
4. 选定 Provider 在 credential preflight、session startup 或运行中不可用时，整个 run fail closed，分类为 typed
   `runtime/infrastructure`；不 fallback、不重试到另一模型，也不改写 profile。
5. baseline、运行证据和终态报告记录逐角色 requested/effective route binding 和 profile digest；任何 secret、
   credential path/digest、原始 Provider 错误正文均不得进入 Agent、run root 或日志。

## 3. 非目标

- 不实现 Chat Completions、Anthropic Messages 或任意非 Responses wire adapter。
- 不接入当前仅提供非 Responses DeepSeek 路径的 OpenCode Go；未来只有验证了 Responses endpoint 后，才能新增
  closed Provider declaration。
- 不实现热切换、自动 fallback、负载均衡、价格/质量路由、A/B、远程动态 Provider 注册或管理 UI。
- 不把本组件扩展成通用插件框架，不改变 Semantic Platform Core 或 modeling workflow。

## 4. 外部能力与风险结论

### 4.1 OpenAI Luna

OpenAI 官方模型页确认 `gpt-5.6-luna` 支持 Responses、function calling 和 reasoning；官方模型指南列出
`none/low/medium/high/xhigh/max` 六档。因此 `openai-direct/gpt-5.6-luna` 使用 identity mapping：requested
effort 等于 effective effort。来源：[GPT-5.6 Luna model](https://developers.openai.com/api/docs/models/gpt-5.6-luna)、
[Model guidance](https://developers.openai.com/api/docs/guides/latest-model)。

### 4.2 DeepSeek V4 Flash

DeepSeek 当前公开模型与 Thinking Mode 文档列出 V4 Flash、tool calls 以及原生 `high/max`；兼容规则为
`low/medium -> high`、`xhigh -> max`。但公开 endpoint 页面只列 Chat Completions/Anthropic，没有公开声明
Responses。来源：[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)、
[Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing)。

本仓库现有生产路径固定转发 `https://api.deepseek.com/responses`；历史真实 formal smoke 留有一次 upstream 2xx、
完整 turn 和清理证据。本次无凭据探针也得到 `/responses` HTTP 401，而不是 route-not-found。因此首期可保留
`deepseek-direct`，但把它定义为“行为实证的 Responses-compatible route”，而不是宣称 DeepSeek 官方公开合同。
实施发布前必须用现有最小 live probe 重验 model identity、tool call、stream/terminal 和 `high/max`；任何失败都
BLOCKED，禁止改走 `/chat/completions`。

DeepSeek 首期 effort capability 为：

| Requested | Effective | 结果 |
| --- | --- | --- |
| `none` | — | preflight 拒绝；Responses route 的 non-thinking body 尚无已验证合同 |
| `low` | `high` | 接受并同时记录 requested/effective |
| `medium` | `high` | 接受并同时记录 requested/effective |
| `high` | `high` | 接受 |
| `xhigh` | `max` | 接受并同时记录 requested/effective |
| `max` | `max` | 接受 |

## 5. 配置模型

### 5.1 Team Model Profile

新增 repository-owned `modeling_team/model-profiles/`。CLI 只接收受限 profile ID，并解析固定目录下同名 YAML；
拒绝绝对路径、`..`、symlink、重复 ID、未知字段、缺失角色和未知 route/model。建议 schema：

```yaml
schema_version: 1
model_profile_id: mixed-luna-deepseek
roles:
  coordinator:
    model_provider: openai-direct
    model: gpt-5.6-luna
    model_reasoning_effort: medium
  modeling:
    model_provider: deepseek-direct
    model: deepseek-v4-flash
    model_reasoning_effort: max
  protocol: {model_provider: openai-direct, model: gpt-5.6-luna, model_reasoning_effort: high}
  acceptance: {model_provider: openai-direct, model: gpt-5.6-luna, model_reasoning_effort: high}
  source-examiner: {model_provider: deepseek-direct, model: deepseek-v4-flash, model_reasoning_effort: low}
  platform-examiner: {model_provider: deepseek-direct, model: deepseek-v4-flash, model_reasoning_effort: max}
```

首期交付两个可直接选择的 profile：`deepseek-v4-flash-max` 和 `openai-luna-medium`。逐角色混配由同一 schema
直接支持，测试使用一个 mixed fixture 证明；不额外引入 profile inheritance。

加载结果是 immutable `TeamModelProfile`：保存 ID、repo-relative path、source SHA-256，以及六个
`RoleModelBinding(requested_provider, model, requested_effort, effective_effort)`。原始 YAML 在 prepare 的初始
baseline 与外部 preflight 后各读一次；digest 或解析结果漂移即在 reservation/Agent start 前失败。

### 5.2 Closed Provider Catalog

新增最小 closed catalog，不提供 plugin discovery：

| Provider ID | Model allowlist | Wire | Upstream | Credential assignment |
| --- | --- | --- | --- | --- |
| `deepseek-direct` | `deepseek-v4-flash` | Responses | `https://api.deepseek.com/responses` | `DEEPSEEK_API_KEY` |
| `openai-direct` | `gpt-5.6-luna` | Responses | `https://api.openai.com/v1/responses` | `OPENAI_API_KEY` |

catalog declaration 固定 endpoint、TLS 要求、模型 allowlist、effort mapping 和 credential validator。profile 不得
声明 URL、header 或 credential location，避免把模型选择变成任意网络出口。

### 5.3 Fresh-run 权威迁移

这是一次清晰替换，不实现新旧双栈：实施后 `TeamModelProfile` 是所有 fresh formal run 的唯一模型配置源。
`FormalRunContract.model_manifest_path` 改为 `default_model_profile_id`；`TeamRun.model_manifest` 改为
`team_model_profile`；baseline 的 `formal_model_manifest` 改为 `team_model_profile`；Runtime 和全部 current tests
同步切换。旧 `modeling_team/model-manifests/*.yaml` 不再被任何 fresh-run loader、baseline 或 Runtime 读取，仅作为
历史交付资产保留，不增加兼容 reader。

现有已完成 run root、ledger record 和历史证据保持原字节、不回写也不重新解释。新 profile digest 自然产生新的
fresh-run baseline hash；StartLedger 仍按现有授权/attempt 规则处理，不因模型切换获得额外 start 或 retry。

## 6. Runtime 边界

```text
CLI / TeamRunner.prepare
        |
        v
TeamModelProfileLoader ---> ProviderCatalog capability validation
        |                         |
        | frozen role bindings    | referenced provider IDs
        v                         v
TeamRun ----------------> ProviderSessionManager (Host-owned)
                               | one loopback session/provider
                 +-------------+-------------+
                 v                           v
       deepseek-direct session       openai-direct session
                 | POST /responses           | POST /responses
                 v                           v
        DeepSeek Responses route          OpenAI Responses

Codex role process -> only its selected loopback session; no provider key
```

### 6.1 Provider Session

把现有 DeepSeek loopback proxy 收敛成一个参数化的 `ResponsesProviderSession`，保留已有安全行为：只监听
`127.0.0.1:0`、只接受 bounded `POST /responses`、替换 inbound Authorization、固定 TLS upstream、只转发安全
response headers、Provider 正文不落日志、mutable key buffer 在 teardown 覆写。

成功的 2xx response 保持透明 streaming。任何非 2xx 必须消费并丢弃 upstream body，向本地 Codex client 返回
空 body 与固定本地失败状态；2xx stream 在成功终态前断开时，已经透明发送的模型输出不回收也不重新分类，只把
后续 transport failure 记为固定 `provider-upstream-failed`，不得转发异常字符串。这是当前零 Provider error
free-text 合同所需的单一边界；不缓冲完整 2xx response，也不做内容分类、脱敏规则引擎或响应改写框架。

`ProviderSessionManager` 只为 profile 实际引用的 provider 建一个 session；相同 provider 的多个角色共享该
session，不为每个角色复制 secret/listener。它暴露 `base_url_for(provider_id)` 和 safe lifecycle snapshots。
这是一层 run-owned 路由，不进入 Agent 业务协议。

### 6.2 Credential binding

保留当前 Host-owned、owner-private `0600`、no-follow、metadata revalidation 合同。首期只定义两个具体文件：

- DeepSeek：现有 `~/.config/ontology-platform/modeling-team-deepseek.env`，内容精确为
  `DEEPSEEK_API_KEY=<non-whitespace-value>` 加可选单个结尾换行；
- OpenAI：新增 `~/.config/ontology-platform/modeling-team-openai.env`，内容精确为
  `OPENAI_API_KEY=<non-whitespace-value>` 加可选单个结尾换行。

两者都必须是当前用户拥有的 regular file、mode `0600`、不是 symlink、最大 4096 bytes；prepare 先返回只含
device/inode/size/mtime 的 non-secret binding，session startup 用 `O_NOFOLLOW` 重开并核对 metadata 后才读取 mutable
bytes。`TeamRunner` 保留现有 `deepseek_credential_path`，新增一个具体 `openai_credential_path` 构造参数；不增加
credential registry、轮换服务或 ambient environment fallback。`ProviderSessionManager` 只接收 profile 实际引用
Provider 的 binding。

prepare 必须对 profile 引用的全部 provider 完成 preflight；R2.3-003 继续先完成 retained-scope preflight，再读取
任何 DeepSeek/OpenAI credential，然后重读 profile/baseline，最后才 reservation。凭据 preflight 失败在 run root
尚不存在时返回 machine-readable `runtime/infrastructure` + `provider-credential-unavailable`；它没有伪造的 run
evidence。session startup/运行期失败在已有 run evidence 中记录。

Agent process environment 同时排除 `DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`LLM_API_KEY`；Agent TOML 仅收到
selected loopback base URL、`wire_api = "responses"`、model 与 effective effort。

### 6.3 逐角色投影

现有 `FormalModelManifest.override_for(package_id)` 调用点改为查询 frozen
`TeamModelProfile.binding_for(package_id)`。这里的键始终是 canonical package ID，不是 `AgentPackage.role`；后者会
让当前都声明为 `source-specialist` 的 Source/Platform Examiner 发生碰撞：

- 四个 persistent roles 在各自 Codex home 生成对应 model/provider/effective effort；
- Source/Platform Examiner 每次 fresh child 都使用其各自固定 binding；
- `model_provider` TOML table 名使用稳定的 runtime-local ID，并指向该 binding 的 session；
- `thread/start.model` 必须与 binding.model 精确一致，不允许 Host/Codex 默认值覆盖。

Provider route 不授予额外 MCP、filesystem、network 或 team transport 权限。

## 7. CLI 与默认行为

`validate`、`baseline`、`run` 增加同名可选参数：

```bash
python -m modeling_team validate ... --model-profile openai-luna-medium
python -m modeling_team run ... --model-profile mixed-luna-deepseek
```

formal run contract 只保存 `default_model_profile_id`，不再把某个 requirement/task 锁死到唯一模型 tuple。省略参数
时选择 `deepseek-v4-flash-max`，保持当前 operational default。`validate` 输出 profile ID、digest 和逐角色 safe
requested/effective projection；`baseline` 与 `run` 复用同一 loader，不允许三条路径出现不同解析逻辑。

## 8. Evidence 与错误

baseline 中用 `team_model_profile` 替代当前单一 manifest binding：

```json
{
  "profile_id": "mixed-luna-deepseek",
  "path": "modeling_team/model-profiles/mixed-luna-deepseek.yaml",
  "sha256": "...",
  "roles": {
    "source-examiner": {
      "model_provider": "deepseek-direct",
      "model": "deepseek-v4-flash",
      "requested_effort": "low",
      "effective_effort": "high"
    }
  }
}
```

运行 evidence 还需包含逐 provider 的 safe request/status/lifecycle counts，以及每个 role/thread 的 exact binding。
以下错误均使用稳定 reason code，不拼接 provider free text：

- `model-profile-invalid`：schema、角色、route/model/effort 或 digest 不合法；
- `provider-credential-unavailable`：任一所需 credential 不满足 Host 合同；
- `provider-session-start-failed`：listener/upstream session 无法建立；
- `provider-upstream-failed`：网络、非成功 HTTP、stream 或 terminal 失败；
- `provider-session-cleanup-failed`：任一 listener/thread/socket/secret 未完成清理。

profile invalid 是 configuration failure。credential preflight 与 session startup 是 Agent start 前的 typed
`runtime/infrastructure` failure；前者通过 CLI/Runner result 返回且不创建伪 evidence，后者写入已创建 run 的
evidence。运行中 Provider 失败立即 latch 整个 run 的 `runtime/infrastructure`，停止新 turn 并进入 aggregate
cleanup。所有 referenced session 都独立尝试 stop/wipe；一个失败不能跳过其他 session 的清理。

## 9. 最小实现面

- 新增 `modeling_team/model_routing.py`：profile loader、closed catalog、capability/effective binding，以及具体
  OpenAI credential parser/binding；复用当前 DeepSeek 文件规则，不建立 credential plugin framework。
- 将 `deepseek_provider_proxy.py` 的通用 Responses forwarding/lifecycle 提取为 provider-neutral session；保留薄的
  DeepSeek compatibility exports 仅在迁移测试需要时使用，不新增协议 adapter hierarchy。
- `formal_runs.py`：formal contract 保存 default model profile ID；fresh-run 路径原子移除旧 manifest hard gate。
- `runner.py`：接收 profile ID、双读冻结、逐 provider credential binding、baseline projection。
- `runtimes/codex.py`：session map、逐角色投影、aggregate failure/cleanup/evidence。
- `__main__.py`：三条命令统一 `--model-profile`。
- 新增两个 profile YAML；更新 focused tests 和现有 formal regression。

不修改 Team package instructions、transport、capability MCP、platform operation 或 Acceptance schema。

## 10. 验收条件

1. 省略 profile 参数仍得到六角色 `deepseek-direct/deepseek-v4-flash/max`。
2. 选择 OpenAI profile 后六角色使用 `openai-direct/gpt-5.6-luna/medium`；选择 mixed fixture 后每个角色严格匹配
   自己的 binding，且 DeepSeek requested/effective 映射准确。
3. profile/schema/capability/digest 错误在 run root、ledger reservation、platform/model call 和 Agent process 前
   fail closed。
4. 两个 direct provider 各通过 Responses tool-call/terminal live smoke；DeepSeek 若不再支持 `/responses` 则需求
   BLOCKED，不改用非 Responses endpoint。
5. 任一 Provider 故障不触发 fallback；其他 session 仍完成 aggregate cleanup。
6. Agent/证据/日志零 plaintext secret，所有 listener/process/socket/key buffer 零残留。
7. R2.3-003、R2.3-005、R2.3-006 的角色、权限、Acceptance、invariance 与 cleanup 回归不变。
8. fresh run 不再读取旧 model manifest；两个 Examiner 按 `source-examiner`/`platform-examiner` package ID 得到
   各自 binding；历史 run/ledger evidence 不被迁移或改写。

## 11. 演进路径

若 OpenCode Go 后续为 `deepseek-v4-flash` 提供并验证 Responses endpoint，可在另一个小需求中增加一个 closed
Provider declaration、credential binding 和 live probe；同名模型仍以不同 provider ID 保持 route identity。若它
继续只有 Chat Completions，则必须另立协议适配需求，本设计不预留转换器。

## 12. 实施中变更 A：Luna 改用 Codex ChatGPT 订阅认证（2026-08-17）

### 12.1 变更状态与效力

本节是原设计进入实施并以 `8ee7aa4` 落地后的追加修订，不改写前述历史设计。经用户确认，Modeling Team 切换
到 Luna 时应复用宿主机现有的 Codex ChatGPT 登录和订阅访问能力，不应要求 OpenAI Platform API Key 或产生
独立 API 计费。凡本节与 §1、§5.2、§6、§8、§9、§10 中 `openai-direct`、`OPENAI_API_KEY` 或 OpenAI loopback
session 的描述冲突，以本节为准。

`8ee7aa4` 仍是原设计的已验证实现基线，但在本修订完成开发和独立测试前，不得把现有
`openai-direct/gpt-5.6-luna` 路径表述为“可使用 Codex Plus 套餐额度”。原 G1/G3 的“缺 OpenAI credential
文件”BLOCKED 结论保留为历史事实；该 credential 文件不再是修订后 G1/G3 的解除条件。

OpenAI 官方认证合同区分两种本地 Codex 登录：ChatGPT 登录用于 subscription access，API Key 用于
usage-based access；API Key 使用标准 API 定价而不是 ChatGPT 套餐额度。Codex 会缓存并复用登录，file storage
时缓存位于 `CODEX_HOME/auth.json`。来源：[Codex Authentication](https://learn.chatgpt.com/docs/auth)。

### 12.2 修订后的最小 Provider 合同

closed catalog 调整为：

| Provider ID | Model allowlist | Wire/runtime route | Host authentication |
| --- | --- | --- | --- |
| `deepseek-direct` | `deepseek-v4-flash` | 现有 loopback Responses session | 固定 DeepSeek credential 文件 |
| `openai-codex` | `gpt-5.6-luna` | Codex 内建 OpenAI Responses route | 已缓存的 ChatGPT subscription login |

`openai-codex` 取代 fresh-run catalog、`openai-luna-medium` profile 和 mixed profile 中的
`openai-direct`；不保留 alias 或双栈。Provider/model/effort 仍由六个 canonical package ID 独立配置，OpenAI
effort identity mapping 不变。认证方式是 catalog-owned route 属性，不增加到每个 role 的可编辑字段，避免同一
OpenAI route 被误配成 API Key 计费。

本次只支持当前已验证环境所使用的 file-backed Codex 登录缓存，不增加 keyring adapter、OAuth broker、token
service 或远程登录流程。若套餐或 workspace 不允许使用 Luna，按 Provider 不可用失败，不自动切换 API Key、
模型或 Provider。

### 12.3 Host 认证与隔离 Runtime

`TeamRunner.prepare` 先解析 profile 并完成 R2.3-003 retained-scope gate；仅当 frozen profile 引用
`openai-codex` 时，才在任何 DeepSeek credential read、ledger reservation、run-root 创建和 Agent start 前对
`CODEX_HOME/auth.json` 复用现有 owner-private、regular-file、non-symlink 元数据预检，并确认 `codex login
status` 的认证方式是 ChatGPT。完成全部 referenced-provider preflight 后重读 profile/baseline，再进入 reservation。
CLI/Adapter 不得在 `prepare` 返回后无条件追加 Host auth preflight；DeepSeek-only profile 在 Host 未登录 ChatGPT
时仍可准备和运行。只记录安全的 `auth_mode=chatgpt-subscription`；不得记录 token、账户标识、缓存正文、路径或
digest。以下情况 fail closed：

- 登录缓存缺失或不满足现有 private staging 合同：`codex-subscription-auth-unavailable`；
- 当前 Codex 使用 API Key 登录而不是 ChatGPT 登录：`codex-subscription-auth-mode-mismatch`。

只有绑定 `openai-codex` 的持久角色或 fresh Examiner 才把同一份 Host 登录缓存按现有 private
`auth.json` staging/auth-barrier 生命周期投影到各自隔离 `CODEX_HOME`，供 Codex App Server 初始化；操作者只需
在 Host 执行一次 `codex login`，不为每个 Team Agent 单独登录。这里明确修订原“Agent 进程零 plaintext
secret”合同：订阅认证要求 OpenAI-bound Codex App Server 在启动 barrier 内短暂读取 owner-private
`auth.json`，但 token/缓存不得进入模型消息、Agent 指令、工具/MCP、日志、evidence 或非绑定角色；文件必须在
首个 turn 接受后、任何模型选择的 ServerRequest/tool/MCP dispatch 前删除。测试必须直接观察该 active-run
barrier，不只检查最终 cleanup。该必要且有界的例外不扩展为通用 secret 注入。

绑定 `deepseek-direct` 的角色继续只使用 loopback Provider session，不接收 `auth.json`。mixed profile 因此
允许两种 Host-owned 认证边界并存，但任一角色只获得自己的 route 所需认证。

OpenAI 不再进入 `ProviderSessionManager`，也不读取、解析或注入
`~/.config/ontology-platform/modeling-team-openai.env`/`OPENAI_API_KEY`。`ProviderSessionManager` 只管理 profile
实际引用的外部 credential-backed route（当前仅 `deepseek-direct`）。若 external binding map 为空，OpenAI-only
run 不创建 manager，Runtime 接受 `provider_sessions=None`；mixed run 的 manager 只含 `deepseek-direct`。
持久角色和 fresh Examiner 使用同一分支：`deepseek-direct` 才调用 `base_url_for` 并生成自定义 Provider table；
`openai-codex` 直接生成 `model_provider = "openai"`，不调用 session lookup，不声明自定义 `base_url`、
`env_key`、Provider table 或 OpenAI loopback listener。profile/evidence 中仍保留 route identity
`openai-codex`，只有 Codex TOML 投影使用内建 ID `openai`。

### 12.4 Profile、证据与失败语义

profile 的用户界面不变：仍通过 `--model-profile` 快速切换，六角色仍分别配置 model/provider/requested
effort。`openai-luna-medium` 的 provider binding 改为 `openai-codex`；profile digest 随内容变化，既有 run、
ledger 和历史证据不回写。

baseline 与运行 evidence 对 OpenAI role 记录 `provider=openai-codex`、exact model、requested/effective effort
和安全的 `auth_mode=chatgpt-subscription`。DeepSeek evidence 继续记录 loopback session 的安全计数。任何
ChatGPT token、`auth.json` 内容、账户/workspace 标识或认证命令原始输出都不进入 run root、Agent 消息或日志。

OpenAI 登录预检失败沿用 `runtime/infrastructure` 分类；运行期 entitlement、限额、网络或 terminal 失败统一
落入既有 `provider-upstream-failed`，只保留稳定 reason code，不持久化 Provider free text。不 fallback 到
API Key、DeepSeek 或另一 effort。

### 12.5 最小实现调整

- `model_routing.py`：用 `openai-codex` 替换 `openai-direct` catalog entry；移除 OpenAI API Key
  parser/binding/preflight，保留 DeepSeek credential/session 代码。
- `runner.py`：在 retained-scope 之后、reservation/run-root 之前，只对 referenced route 执行 preflight；仅
  external credential route 创建 binding，`openai-codex` 执行 Host ChatGPT/file-cache preflight。删除 CLI 的
  unconditional post-prepare Host auth check。
- `runtimes/codex.py`：允许 empty/optional external session manager；OpenAI-only 不启动 manager，mixed manager
  只含 DeepSeek。持久角色和 fresh Examiner 都把 `openai-codex` 映射为内建 `openai` TOML，把
  `deepseek-direct` 映射为 loopback table；复用已有 staging、auth barrier、secret audit 与 cleanup，不新增认证
  框架。
- profiles/tests：把 OpenAI binding 改成 `openai-codex`，删除 OpenAI credential-file fixtures，增加订阅认证
  和 mixed role 隔离测试。
- CLI 参数、Team package、transport、MCP capability、StartLedger、Acceptance、Responses-only 合同均不变。

### 12.6 修订验收条件

1. Host 已 `Logged in using ChatGPT` 且 file-backed cache 合法时，选择 `openai-luna-medium` 不读取
   `OPENAI_API_KEY` 或 OpenAI credential 文件，六角色无需分别登录即可启动 Luna。
2. Host 未登录、缓存不合法或登录方式为 API Key 时，在 reservation/Agent start 前以对应稳定 reason fail
   closed，且不尝试 API 计费路径；同一条件不得影响 DeepSeek-only profile。
3. mixed profile 中 `openai-codex` role 只获得 private Codex auth，`deepseek-direct` role 只获得 loopback
   provider config；OpenAI-only 不创建 session manager；持久角色和两个 Examiner 的实际 TOML/session lookup 均
   按 canonical package ID 精确绑定。
4. Luna 最小 Responses tool-call/terminal smoke 返回 exact `gpt-5.6-luna`，evidence 记录 subscription auth mode
   且零 token/账户信息；该 smoke 证明本地 Codex 订阅路径可用，不宣称套餐无限额度。
5. DeepSeek 默认行为、逐角色 effort、无 fallback、历史证据不变、secret audit、cleanup 及 R2.3-003/005/006
   回归继续通过。
6. active-run barrier 证明 `auth.json` 只在 OpenAI-bound Codex 初始化窗口存在，并在任何模型选择的
   ServerRequest/tool/MCP dispatch 前删除；模型消息、其他角色、日志/evidence 与最终产物零 ChatGPT token。

### 12.7 非目标

- 不同时支持 `openai-codex` 和 OpenAI API Key 两种首期 route；未来确有 API 计费需求时另增明确 Provider ID。
- 不实现套餐余量查询、自动账号切换、额度预测或 API/订阅自动 fallback。
- 不改变 OpenCode Go 的后续接入边界，也不增加非 Responses adapter。
