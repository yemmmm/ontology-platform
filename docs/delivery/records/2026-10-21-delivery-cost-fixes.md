# Delivery 高消耗问题修复与验证

2026-10-21，用户在停止运行及完成[原件分析](../modeling-retrospectives/2026-10-21-codex-delivery-cost-analysis.md)
后要求“修复发现的问题”。本次按 R4.3-030／022、既有 F3 请求身份合同及 R4.4-002
修复已定位的五处 Delivery 缺口，不扩展通用编排或预算机制。

## 修复结果

| 问题 | 最小修复 | 保留的约束与证据 |
| --- | --- | --- |
| 同一 `delivery-deferred` 重排持续产生决策 | 按 run 内的 delivery_id／recipient_id 和实际完整内容识别问题状态，只忽略 recorded_at；相同状态跨恢复不重复唤醒 | 新消息、错误内容、控制绑定变化及实际送达后再次失败仍可见；原始重排证据不删除 |
| 分页补读退回含 snapshot／fingerprint 的原始 packet | 超长视图保存为当前 session 私有不可变投影；read_remaining 从已返回页末续读，read_original 读取同一完整投影 | 原 journal 的精确 evidence 引用继续保留，业务正文完整；不因补读自动确认输入或跳过送达 |
| `resolve_issue` 缺省 request_id 阻断阶段切换 | 沿既有 call_identity 生成稳定身份；同一原生工具重放保留身份，显式 ID 不变 | 不修改旧 null 账本，不伪造历史消费；未知写入、缺失身份及阶段实际回执检查保留 |
| 已正式拒绝的请求仍为 pending，继续等待恢复回执 | accepted／rejected 均进入已结算集合，变化与恢复输入显式返回拒绝及纠正信息；对已拒绝 ID 的等待返回可恢复的准确反馈 | unknown／冲突／无身份仍未决；阶段候选与实际切换只接受 accepted，拒绝不表示成功执行 |
| 预算控制确认错误落入 conversation 异常，参数失败难定位 | 对本轮无 conversation 的金额控制分支返回 budget_control_stale、当前 epoch／可用控制身份；格式错误指出字段及期待类型 | effective 仍需实际证据，证据引用为字符串；只能确认 Delivery owner，不替其他成员证明暂停，不追加金额或扩大授权 |

历史分页输入现在直接附当前预算控制及 run 状态摘要，防止旧页遮蔽新授权／只读状态。
Delivery 实际加载的 instructions 与 skill 同步说明分页续读、拒绝终态、恢复 selector、
缺省身份及预算确认反馈；未把提示补充当作程序缺陷的替代修复。

## 防御复核与影响范围

- 重排保障消息最终送达有必要，但相同等待不需要反复推理；只折叠决策状态，不改投递。
- 已知拒绝不属于在途或未知写入；允许处理反馈并继续原目标，不永久终止 run。
  接受结果才可满足冻结／handoff 的边界，写入与独立验收保护不降级。
- 缺身份检查保护真实回执关联，继续保留；修复调用边界的遗漏，不放行历史缺身份记录。
- 金额暂停保护授权，继续保留；仅改善当前控制与输入形状的可操作反馈，不承诺迟到计量
  无尾差，不改变预算账本算法。

变更限于 `modeling_team/delivery.py`、两个 Delivery 提示面和相关测试。
直接检查覆盖观察／事件去重、请求投影、yield 等待、阶段切换、原件读取及预算确认；
Codex、DSH 和金额控制关联用例一并回归。GitNexus 对两个目标方法返回
`Target not found`／UNKNOWN，未获得图覆盖；采用实际调用点检查与 Team 回归补足，
不把旧索引的空结果报告为零风险。提交前 detect_changes 识别 10 个暂存文件，但映射
0 个符号／流程；其 low 标签不作为完整影响分析结论。

## 验证

新增 15 个工程回归用例，覆盖首次／重复／状态变化、跨 session 恢复、原生调用重放、
实际 FIFO 回执与模拟 runtime 阶段切换、分页正文完整性及跨 session 读取拒绝。
旧投影用例同步纠正“拒绝仍应 pending”的错误期待，保留完整拒绝正文及 unknown 断言。

- 定向与关联回归：**294 passed／2 skipped，78.06s**。
- 完整 Team 回归：**3728 passed／12 skipped／318 subtests passed，617.53s**，
  359 条 warning（含 Python 3.14 多线程 fork 的 DeprecationWarning），无失败。
- Ruff、`git diff --check` 及 Delivery skill 格式检查通过。

原运行 `deliveries.jsonl` 只读经过同一 `_decision_events`：9,585 条延后投影为 9 条，
16 条实际 delivery 全部保留；源文件前后 SHA256 均为
`4d67ef3c201a7e7e473f41ae0fcd6ff390605bb08d1218672cfd8f13506a6182`。
该计数只证明原事件上的确定性折叠，不推算模型调用数或真实节省比例。

命令均从 `backend/` 执行，使用 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run --no-sync pytest`。
关联回归包含 cost_regressions、decision_input、token_reduction、request_identity、
phase_threads、wakeups、r44002_budget_integration、delivery_runtime 及 dsh_delivery；
完整回归范围为 `../modeling_team/tests`。原始输出保存在本机
[本轮 Host 目录](../../../workspaces/minimal-chain-20261020-codex-glm-3cny-171156/)
的 `delivery-cost-fix-verification.log`、`delivery-cost-fix-team-regression.log` 与
`delivery-cost-fix-original-event-projection.json`。

未改 backend／frontend 服务代码，不需重启应用服务。本次没有付费模型调用、生产
semantic-start、修模或独立验收；已停止的原 run／Delivery／验收未恢复。
工程回归只证明这些合同缺口已修，**不证明实际 token 降幅、全任务 10M 达标、预算全员
暂停／尾差闭合、真实 native 线程切换或独立语义 PASS**。这些仍按后续有效授权实测。
