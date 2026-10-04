# R4.0-018 生产交接与同源检查点验收的启动衔接设计

## 1. 范围、基线与状态

- 权威范围：[R4.0-018](../../requirements/requirements-v4.0.md#r40-018-生产交接与同源检查点验收的启动衔接)。本设计只细化该条目已确认的生产交接、停止、退出、同源续跑和只读验收边界。
- 关联合同：[modeling-dev-loop Skill](../../../skills/modeling-dev-loop/SKILL.md)、[Team runbook](../../../skills/modeling-dev-loop/references/team-runbook.md#同源-checkpoint-只读验收启动)、[R3.0-015 S4 设计](2026-09-14-r3-0-015-modeling-checkpoint-recovery-design.md)。R4.0-017 负责运行内部故障，R4.0-016 负责范围与题集选择。
- 当前状态：需求细化与设计；未实施、未运行本条新验证、未取得真实语义质量结论。现有代码和 runbook 证据只说明可复用入口，不证明操作员在所有运行中已经按顺序执行。
- 本轮基线：现有 `host_ops` 已提供 `get_run_status`、`stop_run`、`inspect_checkpoints`、`resume_from_checkpoint` 和受管 launch/exit 记录；`__main__._run_checkpoint_resume_acceptance` 已在源检查点上做只读核对、共享 root lock 和输入/输出分离。上一运行的 `source_active` 失败保留在 [执行记录](../records/2026-10-04-v4-semantic-acceptance-attempt-record.md#start5-独立验收启动边界1757-08)，不能由后续串行成功覆盖。

本设计不新增 scheduler、全局并发规则、状态平台、停止替代接口或语义裁判。若实施后的合同测试发现现有入口已经充分满足某项行为，只补说明与验证，不为“看起来更完整”增加代码。

## 2. 要解决的运行问题

角色 terminal 只表示角色不再工作，production handoff ready 只表示交接包和写入状态满足其合同，受管进程退出才表示该进程不再持有 writer/恢复资源。三者必须分别读取。当前同源 checkpoint resume 还共享 root-run 进程锁，因此公开和隐藏验收 continuation 不能并发启动；这是当前恢复实现的局部约束，不是所有项目的全局串行政策。

目标顺序如下：

```text
角色结果收齐
  -> handoff ready / pending_writes=false / unknown_writes=[]
  -> 通过既有 stop 通道停止 production writer
  -> 读取 launch/exit 和 get_run_status，确认进程退出
  -> 只读复核完整 production_handoff checkpoint
  -> 启动一批 acceptance continuation
  -> 确认该 continuation 进程退出
  -> 按获准顺序启动下一批
```

其中任一步发现 unknown write、未退出 writer、checkpoint 漂移或 `source_active`，保留首个阻塞及原始记录，使用现有可恢复路径处理；不得删除锁、伪改 `state.json`、盲目重放未知写入或用成功退出推导模型质量。

## 3. 现状核对与最小设计

| 位置 | 已有能力或事实 | 本条增量 |
| --- | --- | --- |
| `modeling_team/host_ops.py:get_run_status` | 返回 recorded state、stage、last activity、semantic progress、first blocker、pending、terminal conclusion、liveness、cursor 和 evidence refs | 继续作为顺序核对的事实入口；若实现阶段需要增加字段，只增加可从现有记录定位的状态，不改变旧字段语义 |
| `modeling_team/host_ops.py:stop_run`、`get_request_result` | 通过受管 FIFO 提交和观察 stop，stop 不等于写入结算 | runbook 明确先核对 handoff readiness，再 stop；记录 stop request/receipt/exit 证据 |
| `modeling_team/host_ops.py:inspect_checkpoints`、`resume_from_checkpoint` | checkpoint id 显式、源 run 只读、root lock、source-active 类型化拒绝、acceptance 记账 0 次 | 在操作顺序中固定“退出后 inspect/resume”，不重建已有恢复合同 |
| `modeling_team/__main__.py:_run_checkpoint_resume_acceptance` | 复用 handoff/freeze、输出新 run、保留源报告，完整 PASS 可只核验收口 | 验证 A4 的顺序和证据引用；不改源 run 或把旧 partial 拼成新 PASS |
| `skills/modeling-dev-loop/references/team-runbook.md` 同源段落、S4 段落 | 已写同源串行和 0 次 acceptance 规则 | 补成可执行 checklist：三态分别核对、stop/exit 门、继续/等待原因和下一动作 |
| 交付记录/进度报告 | 能保留失败和额度，但容易把“交接 ready”写成“验收可启动” | 使用同一 run/event/launch 引用记录 `blocked_at`、`next_action`、执行题数和有效裁决数 |

## 4. 决策表

| 决定 | 选择 | 原因与边界 |
| --- | --- | --- |
| D018-1 | 角色 terminal、handoff ready、managed process exited 三项独立字段/事实 | 直接保护写入完整性和资源生命周期；任何一项不能替代另一项。缺字段写 unknown，不凭空升级。 |
| D018-2 | acceptance 前必须走原 stop 通道并确认退出 | 复用已有控制通道和 reaper/launch record，避免启动后才用 `source_active` 探测未就绪状态；stop 失败继续保留源证据。 |
| D018-3 | 只对同一 root run 的同源 continuation 保持互斥 | root lock 是现有恢复合同的一部分；不新增跨项目或独立来源的全局并发禁令，也不固定 public 优先。 |
| D018-4 | `source_active`、`write_unreconciled`、漂移等是可定位启动阻塞 | 启动拒绝不消耗 acceptance 的 semantic start，不是模型质量失败；后续恢复必须使用同一明确 checkpoint/原始证据。 |
| D018-5 | 计数分开保存 | start/continuation attempt、实际执行题数、有效 Judge 裁决数和 PASS/PARTIAL 不能互相代替；acceptance continuation 的 `semantic_starts=0` 沿 S4 合同。 |
| D018-6 | 继续条件来自当前获准任务，不由本需求排序 | 让宿主可在公开先行、隐藏先行或单批验收之间按授权选择，避免流程偏好变成业务或额度硬门。 |

## 5. 运行时行为与反馈

### 5.1 启动前

宿主从当前 run 的 `get_run_status`、增量 `get_run_events`、`get_pending_actions` 和 handoff 记录取得 `freeze_id`、`freeze_digest`、`delivery_binding`（如有）。只接受当前 run 的最新事实：

- 角色结果已收齐，但仍有待处理 issue、pending write 或 unknown write：保留第一阻塞，继续可独立的只读核对，不提交验收启动。
- handoff `ready=true`、写入已排空、`unknown_writes=[]`，但 `liveness` 仍显示 writer/managed process 活跃：提交既有 `stop_run`，等待并读取 request receipt、launch record 和 exit evidence。
- 短时间无日志不等于退出；在既有有界观察窗口内仍未知时，报告“进程状态待核实”，不启动或重放。

### 5.2 停止后与 acceptance 接续

确认进程已退出、源 checkpoint/冻结池/交接包摘要仍一致后，调用既有 acceptance continuation 入口。新输出 run 写入 `recovery/origin.json`、新 attempt/report 和宿主收尾记录；源 run、handoff、freeze 和历史报告保持只读。完整可用 PASS 只做核验和收口，重新执行时仍使用完整冻结分母。

当前 continuation 退出后，才允许同一 root 的下一批启动。若冲突返回 `source_active`，记录“未执行题数”和原拒绝；不得将零题当成语义失败，也不得把后续 PASS 回填到该失败记录。

### 5.3 失败与交接

错误对象至少保留 `code/object_ref/phase/retryable/reason/next_action` 及原事件/请求引用。`write_unreconciled` 沿既有 Batch/Attempt/receipt 对账；不通过 stop 或新 run 清除不确定性。若宿主在当前会话结束时仍不能继续，交接必须写真实的源 run、进程观察、检查点、下一动作和责任人/下一观察者，不声称有后台监控。

## 6. 实施文件归属

| 文件 | 计划工作 |
| --- | --- |
| `skills/modeling-dev-loop/SKILL.md` | 把三态核对、stop/exit 顺序、0 次 acceptance 和独立计数写入宿主操作说明；不改授权或 semantic quality 完成门 |
| `skills/modeling-dev-loop/references/team-runbook.md` | 扩展“同源 checkpoint 只读验收启动” checklist，并链接 R4.0-018；保留现有 S2/S4 命令和错误码 |
| `skills/modeling-dev-loop/references/progress-report.md` | 规定 stage/handoff/exit/acceptance 的分段报告字段和下一动作 |
| `modeling_team/host_ops.py`, `host_ops_mcp.py`, `__main__.py` | 先复用现有接口。只有确定性测试证明某项顺序/状态不能被现有返回值观察时，才补最小只读字段或错误映射；禁止新增 scheduler/force-stop/并发管理器 |
| `modeling_team/tests/test_host_ops_s2.py`、相关 checkpoint/lifecycle 测试 | 覆盖顺序、类型化拒绝、源文件只读、root lock 和计数证据 |

实现时文件若无真实缺口则不修改。任何新增状态必须有现有事件或文件来源，不能让宿主猜测进程状态。

## 7. 分层验证计划

详见[共享测试计划](../test-plans/2026-10-04-r4-0-018-021-operations-coordination-test-plan.md)。本条的确定性用例包括：

| 用例 | 证明内容 |
| --- | --- |
| A1 | terminal/handoff ready 但 writer 活跃时，宿主不会直接启动 acceptance；stop 后确认退出再继续 |
| A2 | 同源 public/hidden continuation 按当前获准顺序串行；前一进程未退出得到可恢复 `source_active` |
| A3 | unknown write、未退出、checkpoint 漂移分别保留首阻塞和原件，不删锁、伪改 state 或重放 |
| A4 | 从完整 handoff 接续产生正确新输出、0 次 semantic start、完整题集/有效裁决计数；源 run 原样保留 |

机械检查、开发测试和独立功能测试可以证明合同行为；只有获准的真实运行才可证明真实进程/平台语义 E2E，不能用 A1-A4 的 fixture 冒充 L0/L1 或 CQ PASS。

## 8. 设计完成边界

本设计不宣称 R4.0-018 已实现或通过真实验收。后续开发完成后应分别报告：设计审阅、开发测试、独立功能验收、真实 runtime/semantic evidence。任一层缺失均保留 PARTIAL，并保留原 `source_active` 失败证据。
