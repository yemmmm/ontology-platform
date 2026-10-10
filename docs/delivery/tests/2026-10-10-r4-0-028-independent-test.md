# R4.0-028 独立功能验收记录

结论：**PASS（确定性与受控 native subprocess 功能复验范围），0 Critical／0 High**。首轮三个接线／指标／阶段交接缺口已闭环。实际模型全 Team L0、真实平台 live-source S4 全链路和独立业务语义 L1 **未执行／未判 PASS**；完整运行验收仍为 PARTIAL。本记录保留所有失败轮次，不用后续通过覆盖历史。

## 授权与证据边界

- 依据 R4.0-028 权威需求、2026-10-10 Team standby 设计及 R4.2-008 消息协作衔接设计。
- 仅本文件可编辑，其余代码只读；不调用产品服务、真实语义建模或付费模型。
- 允许现有受控 native subprocess fixture 和确定性测试；这些证据不构成实际模型 L0 或业务语义 L1 PASS。

## 第 1 轮：未冻结快照

基线 HEAD：`4a8230c90397aaad05c84aae9e10bd7b2af57827`，相关实现存在并行未提交修改。结果仅对应测试时读取的工作区。

命令（工作目录 backend）：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_team_standby.py ../modeling_team/tests/test_r3011_acceptance_cli_flow.py -q
```

结果：**9 passed，3 failed，6.67 秒**。standby 的五个确定性测试全部通过；受控原生 CLI fixture 的三处清理断言失败：

- `test_tg41_two_v3_sessions_complete_the_batch_through_real_sockets`
- `test_tg46_post_read_drift_keeps_reports_and_fails_the_batch`
- `test_tg46_post_read_failure_is_runtime_incomplete_and_retained`

共同失败位置：`modeling_team/tests/test_r3011_acceptance_cli_flow.py:454`。报告允许 `forwarder_retained=true`，但下一行仍强制 `forwarder_still_active is False`，实际为 true；需按准确的保留／销毁证据区分断言，不代表模型语义失败。

### 已发送给主 agent 的待修复功能缺口

1. 当前 `__main__.py` 单个 Judge packet 路径未向 `run_v3_acceptance_child` 传入 `cooperative_owner`，分组路径已传入。单 Judge 无法绑定原 owner 并处理协作暂停确认。
2. `EvaluationOwner.poll` 发同线程新 turn 前未接入 `ExaminerRunMetrics` 的后续 turn 身份处理。无模型确定性探针先提交 `threadId=same-thread, turnId=turn-one` 的 tokenUsage，再提交同线程 `turnId=turn-resume`，实际抛出 `ExaminerRuntimeBlocked binding-rejected {'turn_id': 'turn-one'}`。暂停后继续／保留 Consumer 咨询会遇到这条原报告指标边界；应保留原任务与实际费用证据，不能把新 turn 当新验收批次或粗略关闭指标检查。
3. 阶段交接专项待核：当前同步 CQ 在 Consumer 返回后自行启动 Judge；owner 无 current 时向 retained Consumer 转达，`pending_pause` 暂未见阶段接线使用。需证明设计 A4 的“无在办对象准确披露，Delivery 等待明确继续再安排下一阶段”不会被自动阶段推进覆盖；不得以全局暂停硬门替代消息协作。

以上已通知主 agent，等待修复和冻结后复测。尚未证明 Consumer/Judge 的 native 暂停—等待 turn 结束—继续、全 Team 原线程咨询、S4 完整 live-source 接线／两批锁互斥及显式全对象 stop。

## 第 2 轮：既有 S4／验收边界回归（仍未冻结）

命令（工作目录 backend）：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r30015_acceptance.py ../modeling_team/tests/test_r3011_acceptance_runtime.py -q
```

结果：**63 passed，12.59 秒**。覆盖既有已退出 source 的 S4、原冻结/漂移/完整性门、受控 CLI 与 report/read proxy 边界，未发现该范围回归。该结果不证明新增 live-source owner 封口接线、Consumer/Judge 协作等待恢复或待命 stop；首轮功能缺口仍需修复后复测。

## 第 3 轮：修复后隔离复验（仍未冻结）

基线 HEAD 仍为 `4a8230c90397aaad05c84aae9e10bd7b2af57827`，工作区存在并行未提交实现。静态确认单 Judge 与分组 Judge 均传入原 `cooperative_owner`；`run_v3_acceptance_child` 在启动下一个角色前调用 `before_next_task`；同线程显式控制 turn 通过 `allow_control_turn` 延续原指标，不重新建批次。

命令（工作目录 backend）：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_team_standby.py -q
```

结果：**12 passed，0.32 秒**。包含真实 FIFO 阶段交接暂停／显式 resume（没有 current／retained 角色时不创建下一角色）、原指标允许一个显式控制 turn 且拒绝无授权额外 turn、existing scope 的 active Session／Lease／Attempt 和畸形清单拒绝封口、S4 新报告目录绑定和原 handoff 漂移拒绝。该 FIFO 用例使用确定性线程及临时目录，不是实际模型 Agent 等待行为证据。

另运行隔离 Python 探针，直接调用实际 `source_safe_for_acceptance` 与文件锁函数，以临时 source、实际存活的本测试 PID、mock Host 回执及确定性平台 readback 验证：

- 有效 fresh standby 请求、当前 owner、实际 owned key 撤回读回与模型修订绑定通过。
- stale 请求、owner 不匹配、unknown write、in-flight write、未撤回 key、模型 revision 漂移和 handoff 摘要漂移，七种变化均拒绝。
- 同一源第二个 acceptance lock 冲突；前一任务释放 acceptance lock 后，在原 production lock 和 owner 仍保留时下一批可再次取得 acceptance lock。

以上共十项直接断言通过，未访问产品服务或调用模型。此探针证明窄函数与锁合同；不能替代原 source native FIFO → Host → S4 完整集成或真实平台读回验收。等待主 agent 全量回归完成后再执行共享 `/tmp/r3011-acceptance-*` 集合的原生 CLI fixture，避免并发清理互扰。

## 第 4 轮：受控原生 Consumer／Judge 独立复验

主 agent 确认其首轮全 Team 回归已结束、无其他共享 native fixture 正在运行后执行。命令（工作目录 backend）：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r3011_acceptance_cli_flow.py -q
```

结果：**9 passed，16.20 秒**。首轮三个回归断言已全部通过。新增 Consumer／Judge 两个参数化用例各使用原生 CLI subprocess、受控 App Server 和真实 socket／FIFO：

- 原当前角色收到暂停并确认 `effective`，保存相同 thread／PID；等待超过 2.5 秒，而原有效处理时限为 2 秒，等待期间无任务完成和报告封口。
- 显式 resume 后同线程完成所有剩余问题；原题分母、Consumer 回答及 Judge 裁决完整，未报告 batch-incomplete。
- Consumer 真正完成后 report sink 封口并保留原会话；只读咨询后原 batch-report 字节完全不变，Consumer 仍实际存活。
- 明确 stop 后原 owner 为 stopped，retained 列表清空，受管子进程实际退出、private_root 实际清理，没有本轮未知残留。

该用例使用受控 App Server 产生报告，不调用付费模型，不证明实际模型能遵循等待／恢复指示或业务语义正确。全 Team Profile 原生角色协作及完整 live-source S4 端到端不由此用例代证。

## 当前结论与可复用基线

对 owning requirement／设计、实际调用路径和以上独立测试，未发现当前证据充分的 Critical／High。单 Judge owner、同线程续 turn 指标、Consumer-before-Judge 的无当前对象阶段暂停三项首轮缺口均闭环。只读咨询不重开写 admission，实际 owned write key 撤回、Build Session／Lease／Attempt 终态检查、S4 新报告来源／漂移与两个用途文件锁均有确定性证据。

最终读取 HEAD：`4a8230c90397aaad05c84aae9e10bd7b2af57827`；实现仍为并行未提交工作区。下表为第 3／4 轮后读取的 SHA-256，后续提交／冻结仅在这些相关内容未变化时可复用证据；父 agent 的全量回归结果属于另行证据，不计为本记录独立测试。

| 文件（仓库相对路径） | SHA-256 |
| --- | --- |
| `modeling_team/evaluation_owner.py` | `75be81ac0c16cee064880ad583343510cb68622b67aab9be3e0a7d517d99f6a5` |
| `modeling_team/__main__.py` | `5fed05693d639f8a4a1bff3e9857557deb7ccc441987f2f98a8b2cce04b9c5ad` |
| `modeling_team/acceptance_runtime.py` | `887a9ef30a9a08b8edcf862765c664d33e53e00ddcbcf62ca46ad8567eceb1bd` |
| `modeling_team/runtimes/codex.py` | `6bf042949116b87657009cc7629a001538450f0ba604e87f99f8fc2a95c77a4f` |
| `modeling_team/platform_scope.py` | `1e55e4359b27891213ca9412223014f09dcb4718a0ec6ddbf42b858e54d81851` |
| `modeling_team/checkpoint_recovery.py` | `9dfcdad9f76bc929d9af1933ef5128460448c165d38b8acd728e5688e0d271c7` |
| `modeling_team/runner.py` | `0e71f2efae20d91b3deecf23dc99c73baf3330bfc3c2cffce066035fb6e19a43` |
| `modeling_team/tests/test_team_standby.py` | `ac393d21eb677bfcce147788ca6d7accf62e9326e3bc16c79a3c24ac4ae4147d` |
| `modeling_team/tests/test_r3011_acceptance_cli_flow.py` | `6e78895736db4157df602fbf3b48657898caf8e0da614465e8590ecb6fd573f4` |

未验证边界：实际模型全 Team 原上下文可用／无输入无推理、真实平台封口读回与 live source FIFO → Host → S4 全链路、真实同源连续两批与权限绝对到期、完整 Delivery 最后退出的多对象部分失败，以及独立业务语义 L1。未启动产品服务、真实语义建模或付费推理，没有编辑实现或创建提交。
