# 模型供应商错误恢复

归属：R3.0-006，2026-09-14 增量。适用于加载本次代码的存活 Team Runner；旧冻结
checkout 不会热更新，已退出的线程不能通过本入口重建。

限流、额度/余额不足、并发拒绝或服务中断在 SDK 放弃重试后进入 `waiting_provider`，
保留原线程及建模/写入证据。识别依据为 App Server 的已知 `codexErrorInfo` 和 HTTP
状态；未知错误、身份/协议损坏仍可能进入不可恢复错误，不承诺覆盖所有供应商私有编码。

## 判断与恢复

Coordinator 可用时，Runner 将等待报告为 `runtime_recovery` issue，由 Coordinator
通过现有 `issue_control` 判断暂停/恢复；外部修复结果通过绑定的 `issue_resolution`
提供。Coordinator 自身受阻或无法推进时，宿主使用下面的直达入口，无需等待其回答。
宿主把用户“额度已恢复，请继续”的消息转换为结构化控制，不由程序解析自然语言关键词。

向目标 run 的现有 FIFO/stdin 发送一行 JSON，先查询状态：

```json
{"action":"status"}
```

`provider-wait-status.waits` 列出 `agent_id`、`role`、`wait_id`、`epoch`、错误变体、
HTTP 状态、恢复失败次数及 `recovery_route`。确认额度重置、充值或外部故障解除后：

```json
{"action":"recover_provider","run_id":"实际 run ID","role":"modeling","wait_id":"状态中的 wait_id","text":"额度已恢复，请继续原任务。"}
```

`role` 与 `agent_id` 二选一；`run_id` 可省略，提供时须匹配当前 run；建议携带从状态
读取的 `wait_id` 绑定当前问题。`text` 为非空、最多 4000 字符。成功返回
`provider-recovery` / `dispatch_mode=start`，表示原线程已接受新 turn，不表示建模成功。
过期绑定、无待恢复问题或恢复再次失败返回本行的 `outer-input-rejected`，不会据此终止
Runner；再次受限仍保留等待，外部条件改变后再触发。不要循环发送恢复命令消耗额度。

## 边界

- 等待时间不计入相关无进展/run fallback 超时；显式 `{"action":"stop"}` 仍可清理。
- 已完成操作不自动重放；未知写入的关闭写门不因恢复解除，先核对 Batch/Attempt/receipt。
- 多角色分别恢复，不改模型、不追加 semantic start。
- Coordinator 真正死亡时，`coordinator-unavailable` 明确交给宿主控制存活角色；死亡
  Coordinator 不会重建，也不宣称完整 Team 已恢复。宿主负责后续协调和显式停止。
- 本地测试覆盖实际管道 App Server 替身、Runner、issue 控制和前台入口；不是实际模型
  供应商恢复或语义验收。全套结果：1697 passed、1 skipped、331 subtests passed。
