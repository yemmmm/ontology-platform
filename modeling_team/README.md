# Modeling Team Host 工具

## 整轮用量与账单对账（Host离线）

R4.3-019提供 `python -m modeling_team.usage_report --scope <scope.json> --output-dir <新目录>`，
读取显式绑定原件，输出数值JSON及Markdown。覆盖Delivery、生产／验收、恢复／修模及
辅助模型缺口；响应去重、线程累计不重复相加，unknown不补零，任务与账单窗口分开。
使用方式、scope／价格／时间合同和最小采集位置见
[Host用量报告](references/model-usage-report.md)。工程测试不等于真实账单或语义质量验收；
报告不进入生产模型或独立盲测输入，不改变建模授权。
收尾将Consumer的`batch_report`快照和实际绑定线程的最终`rollout`一并列入scope，
输出独立终态用量差异；同线程不重复相加，缺原件保留partial，原语义报告不修改。

## R4.4-002：任务金额预算（Host-only）

对明确采用金额模式的新任务，Host／用户先用结构化配置和真实授权引用创建稳定预算，
再把同一个 `budget_ref` 绑定到 Delivery、生产、修模和独立验收。金额模式不套用默认三轮
或轮余额门；轮次和 semantic-start 仍记录作分析，金额只限制资源消耗，不扩大业务目标、
模型、写入或验收授权。Delivery／生产 Agent 只读预算投影，不能创建、追加或改价；历史
次数授权继续按 `authorize-budget --additional-starts` 处理。

```bash
python -m modeling_team task-budget create \
  --ref workspaces/delivery-sessions/<session-id>/cost-budget \
  --config workspaces/host-authorizations/task-budget.json
python -m modeling_team task-budget add \
  --ref workspaces/delivery-sessions/<session-id>/cost-budget \
  --config workspaces/host-authorizations/task-budget-add.json
python -m modeling_team task-budget show \
  --ref workspaces/delivery-sessions/<session-id>/cost-budget --audience host
```

`create`／`add` 只接收 Host 提供的 JSON/YAML 对象，并要求其中有真实
`authorization_reference`（也可用 `--authorization-reference` 显式传入）；`show` 是只读查询，
不会刷新计量、发送暂停消息或启动模型。`--budget-ref` 可由受信 Host 传给 `run` 或
`checkpoint resume`，由运行时复用同一预算；该参数不是模型可选择的权限来源。

创建配置示例（金额和单价仅为虚构示例，不是调用授权或供应商报价）：

```json
{
  "task_ref": "original-business-objective",
  "authorization_reference": "actual-user-authorization",
  "amount": "10",
  "currency": "CNY",
  "allowed_operations": ["read", "supervise", "production", "repair", "evaluation"],
  "prices": [{
    "provider": "openai-codex",
    "actual_model": "gpt-6.1-sol",
    "cached_input_per_million": "0.2",
    "uncached_input_per_million": "2",
    "output_per_million": "8"
  }]
}
```

在原 Delivery 配置中设置 `resource_authorization.mode: amount` 及同级 `budget_ref`；
后续 run／operation 继承该引用。价表须覆盖全部获准实际模型；`add` 配置使用明确的
`authorization_reference`、唯一 `authorization_id` 与 `delta_amount`。足额追加后仍需
`continue_authorized: true` 的明确继续授权；不足、缺数及其他暂停原因不会因此清除。

## R4.3-031：显式生产 DSH 运行时

生产入口可显式选择 `runtime: dsh`；默认及原 Codex Profile 保持。首条配置复用026的
三个角色与原 Task：

```bash
python -m modeling_team validate \
  --profile modeling_team/profiles/r4-3-026-minimal-installation-chain-dsh.yaml \
  --task modeling_team/tasks/r4-3-026-minimal-installation-chain.yaml \
  --model-profile dsh-deepseek-flash-low
```

此命令只核对配置，不发模型请求、不启动建模。实际 `run` 仍须有效的模型、轮次及运行
授权，并显式传入上述 Profile／Task／model-profile、获准 scope、run ID 和 freeze 时间。
运行时与 provider 分别选择；当前 DSH 仅接 `deepseek-official`／`deepseek-flash` 原生
low／high／max，配置不会更名旧模型、改 effort 或回退订阅。所提供的 low 配置不是调用授权。
Delivery 及独立验收可分别按下节选择；默认 Codex，034全链切换仍单独验证。

本地使用设计冻结的 `/home/yangxiang/deepseek-harness` 提交
`687f282e8625c6b8d11ff58211a90524be2e4317` 及其实际已构建依赖、Node 和 bubblewrap。
缺少构建或必要原角色 MCP 时返回定位错误；不继承用户 DSH 全局配置。每角色只挂载自身
材料、必要库和原 socket，实际工具名与 schema 全集在装载时比对。`read_role_material`
按冻结 manifest ID 有界读取原文，不接受任意路径。真实 provider key 只在 Host Messages
代理内，角色仅取得本轮代理凭据；代理不记录请求体，不开放 Files API。

外部 `pause`／`resume` 直接控制原角色进程和 MCP 后代，不等待 Coordinator 的文字确认。
暂停关闭新派发及写入准入；已准入 application 的 Host 回执仍可保存，未知写入继续沿原
通道核对。暂停不承诺取消云端请求或停止计费。provider 恢复先记录提交，观察原生领取后
才记录生效；中断流不自动重放。进程意外退出后的 `restore_session` 是 Host 的显式原历史
恢复接点，须先核清写入；不发送新任务，也不静默创建空 session。

Host 私有 `evidence/dsh-*.jsonl` 保存实际构建、材料、工具 schema、模型绑定、SDK事件、
逐派发身份、控制、等待恢复及清理证据。`messageId`只证明入队，`turn/end`只证明活动
结束；业务报告及 application、治理读回、独立语义验收继续各自取证。DSH 原始用量与
压缩事件保留供034读取，本条不提供 Codex 等价的归一化用量结论。

工程测试与边界见[031开发测试记录](../docs/delivery/records/2026-10-18-r4-3-031-implementation-test-record.md)。

## R4.3-032：独立 Delivery DSH 会话

原 `delivery --config <yaml>`／`delivery --config <yaml> --resume` 的配置增加独立
`runtime: dsh`；省略为 `codex`，不从生产 Profile 推断。沿原模型绑定优先级，显式
delivery 角色优先，否则继承 coordinator；模型配置必须兼容所选运行时，不自动转换。
例如在已有获准 Delivery 配置中选择：

```yaml
runtime: dsh
model_profile: dsh-deepseek-flash-low
```

其余 session_id、authorization_reference、task/profile/scope、allowed_operations、轮次及
源材料授权继续使用原合同。DSH 不接受 Codex 的 service_tier、model_context_window、
model_auto_compact_token_limit 显式字段；省略时使用冻结 DSH composition 的实际配置，
不会套用 Codex 的544000／489600默认值。配置示例不授予真实模型／建模调用权限。

Delivery 独立进程只装载原 instructions、required skill 与获准 Host 工具，复用031固定
构建、bubblewrap 和 Host Messages 代理。工具 schema 全集实际比对，无 shell、编辑器、
任意读取或动态 subagent；双向桥接保留真实 session/callId 与完整 JSON。Host 输入
包装中的 host_dispatch_id 只关联派发，payload 保留原 v2 输入／用户文本与来源。
活跃输入进入底层 Agent.steer 的最近 step；技术 interrupt 调 cancel(keepInbox)，不
冒称官方 SDK 有这两种接口，也不承诺取消远端 provider 请求。

`native/dsh-*.jsonl` 保留构建、原始事件、工具回执和逐派发原文；session／conversation
账本另记 queued、claimed、settled。accepted_by_native 只表示接收，实际 turn/end、
业务效果和独立验收各自取证。yield 后自然结束活动，Host 继续约2秒观察；普通心跳
不启动推理。暂停按生产／验收 owner 的实际运行时控制，Delivery 保持在线；停止／
撤权先在 Host 关闭新业务准入，明确 stop 期间不启动新推理。

显式恢复只接原 DSH 持久 session，核对模型、构建、方法、工具、原生 inbox 及工具结果；
已入队输入不重送，丢失 RPC 回执可由持久原文的 dispatch ID 核对。未决工具／写入或
事件缺口返回可定位错误，保留原件，不创建空白替代 session。旧记录缺 runtime 按
Codex 读取，不能把旧 Codex session 热迁为 DSH。finish_delivery 仍保留 standby。

工程结果及真实运行边界见[032开发测试记录](../docs/delivery/records/2026-10-18-r4-3-032-implementation-test-record.md)。


## R4.3-033：独立验收 DSH 子任务

`cq-acceptance`、`public-feedback` 及 `checkpoint resume --mode acceptance` 可显式传
`--runtime dsh --model-profile dsh-acceptance-deepseek-flash-low`；省略 runtime 保持 Codex。
Host `start_evaluation`／`resume_from_checkpoint(mode="acceptance")` 对应可选字段为
`runtime`。Delivery 配置通过 `evaluation_runtime: dsh` 与
`evaluation_model_profile: dsh-acceptance-deepseek-flash-low` 单独绑定，与 Delivery 和生产
runtime 无关。Profile 只声明 Consumer 的 `platform-examiner` 和 Judge 的 `acceptance`，
不继承031生产三角色模型。公开早期反馈只要求 Consumer binding，不调用 Judge。
DSH 显式 `service_tier=fast` 返回可修正错误；unset/default 不继承 Codex fast 环境。

每题 Consumer、每组 Judge 各有私有进程、原生 session、只读输入与工具清单；沿原
三题并发、后置 Judge、完整分母、真实治理响应重验和冻结原文读取。DSH 报告由原 sink
接纳，格式错误可在同 session 纠正；入队、活动结束或进程退出都不是报告。
报告完成的 Consumer 可由原 owner 保留只读咨询，原报告入口关闭；暂停实际冻结当前及
保留进程和后代，继续使用原 session。新题及晚绑定成员受同一 owner 准入控制。

`<attempt-root>/acceptance-runtime/<process-instance>/` 保留 Host 私有构建、工具、模型、
材料摘要、原始事件、接纳报告摘要与原生 session 历史。读响应仍沿原 attempt 路径留存，
本地 `p0` 仅在本题解析。收尾仅清理本次进程、shim、socket和随机代理凭据；真实 key
不进入子进程。缺失用量保持 unknown，034另做归一化与整任务对账。
原 session 存活时可暂停／继续及只读追问；进程失效不自动恢复或重放未知请求。
既有只读接续创建独立的新 attempt，保留源输入与失败原件，不启动生产。

上述配置不授予真实模型调用权限。工程及本机确定性测试不等于真实 L0 或独立 L1，
详见[033开发测试记录](../docs/delivery/records/2026-10-18-r4-3-033-implementation-test-record.md)。

## R4.3-034：DSH整任务计量与切换边界

生产、Delivery、Consumer和Judge的Messages代理已接入Host私有numeric-only采集；
[离线报告](references/model-usage-report.md#dsh-usage)支持DSH／Codex
混合scope、互斥输入桶、真实session、原生核对、压缩子集及缓存写入计价。

另行获准026全链验证时，在新的现有Delivery配置中同时显式选择以下字段（其余业务
授权／scope／资料／session字段沿原合同；示例不是调用授权）：

```yaml
runtime: dsh
profile: modeling_team/profiles/r4-3-026-minimal-installation-chain-dsh.yaml
task: modeling_team/tasks/r4-3-026-minimal-installation-chain.yaml
model_profile: dsh-deepseek-flash-low
evaluation_runtime: dsh
evaluation_model_profile: dsh-acceptance-deepseek-flash-low
```

沿原`python -m modeling_team delivery --config <获准配置>`启动；公开反馈、完整验收和
只读acceptance接续均沿显式evaluation选择。缺精确角色模型返回配置错误，不补模型。
工程测试不改变标准新任务默认；真实L0／独立L1通过后才提交默认切换。必须核对实际
进程／session和全部必经角色，Delivery或验收仍Codex则mixed；外层Host残余另列成本。
[开发测试记录](../docs/delivery/records/2026-10-18-r4-3-034-implementation-test-record.md)
分别跟踪工程、真实运行、独立质量、切换、净效果和账单，不互作证明。

### Recoverable issue control feedback

A foreground/FIFO `issue_resolution` with a complete issue binding received while
the issue is still `reported` returns `issue_pause_pending`, `retryable=true`,
`issue_state=reported`, and the bound Coordinator `issue_control(action=pause)`
next action. The existing `outer-input-receipts.jsonl` records the same code,
detail and retry guidance. No resolution or runtime delivery occurs before the
pause; resend after its actual dispatch. Other malformed/not-ready inputs retain
their existing rejection contract. The flat MCP control adapter ignores its
schema-declared `reason` on `pause` only; unknown fields, resolution fields,
bindings/epoch/identity, and persisted resume/abort validation stay strict.
