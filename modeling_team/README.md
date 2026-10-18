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
Delivery 可按下节独立选择；独立验收仍沿既有 Codex 路径，033／034不属于031交付。

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
