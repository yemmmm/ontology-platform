# 2026-10-19 Delivery阶段交接与只读重验修复

用户在[跨轮复盘](../modeling-retrospectives/2026-10-19-delivery-multirun-cost-review.md)
及Codex／DSH差异分析后授权“请你按照你的判断进行相应修复”。基线0083d36。
本次沿R4.3-030 F3／022／029／032及R3.0-012的唯一验收attempt合同修复有原件反例的
接续缺口，并更新实际加载提示。未授权新的建模或实质修模；本次未启动模型、继续旧run、
重新验收或改动旧冻结／报告，不消耗任何剩余建模轮次。

## 根因、最小修复与责任面

| 原问题 | 修复与边界 |
| --- | --- |
| 长turn中的普通yield覆盖显式thread_boundary，空闲时无申请可用 | Delivery保留独立pending_thread_handoff；普通yield更新最新有效决定而保留交接意图。显式null取消，原journal可恢复。切换仍要求最新输入的yield、全部待送输入落定、原生活动空闲、原授权控制与写入检查；未扩大可选边界或重启生产 |
| native新线程创建失败后可能因后续普通等待再次尝试 | 开始创建即消费本次显式申请；失败／不确定后需新显式申请，普通yield不自动热重试，原尝试证据和旧线程保留 |
| complete_cq_handoff始终返回旧handoff，CLI又不能覆盖旧报告，验收TIMEOUT导致fresh重做 | 为原工具增加可选retry_of=<当前acceptance_attempt_id>。有前次最终报告后，Runner在同run／freeze／scope、原只读门内登记新attempt和独立handoff；不重新生产，不再次保存生产handoff检查点。普通重复保持幂等，同retry_of重投返回已分配的同一attempt |
| 新attempt被旧completed摘要或固定原handoff路径挡住 | Host待办按当前attempt判断；Host回交与CLI共同识别原固定发布路径或Runner固定的attempt发布路径，并核对真实原件。旧handoff和所有旧报告保持不可覆盖；不接受任意调用方文件充当已发布handoff |
| 同一冻结／终态催办反复追加输入，队列无法排空；旧技术反馈重放 | 实际minimal-chain Coordinator提示保留原delivery身份及真实确认，停止相同内容反复换ID催办；Delivery提示在已排队时等待真实消费或新可操作缺口。新的业务／控制／真实错误和必要存活干预仍可发送；已接受的新地图回执优先于过期纠错。该项仅修prompt-contract，实际Agent行为仍待实测 |

F3保持原任务／起点／轮次、最新约束和有效决定；新旧原生线程计量合同继续适用。
retry_of不改变源材料、题集或评分，也不选择性拼接前次通过结果；原任务要求的最终
公开／隐藏组均使用新attempt绑定执行。缺前次最终报告时准确返回可恢复反馈，当前
不声称解决“进程已退出且完全缺报告”的其他未知执行场景。旧CLI失败／PARTIAL仍保留。

按T0复核，旧报告不可覆盖、实际未消费输入、未知写入和当前控制保护均有真实必要。
新增的是原模型上可恢复的新只读验收attempt，不删除这些保护；普通等待覆盖交接意图
不保护业务不变量，应消除该耦合。平台不按次数永久杀run、不替Agent判断业务语义。
没有修改DSH普通Team消息的next-turn语义、Provider协议或扩大工具权限。

## 调用与影响检查

F3调用面为yield_delivery→pending意图／最新yield→监督循环
maybe_switch_phase_thread→原native new_thread，恢复来自原session journal。
验收调用面为Host MCP→原FIFO→Runner handoff→CLI发布原件核验→独立报告→Host／Runner
摘要回交；checkpoint验收仍使用原handoff与原输入／输出隔离路径。

GitNexus未收录maybe_switch_phase_thread、_handle_cq_handoff_complete及Host
complete_cq_handoff，结果UNKNOWN／target not found，使用上述实际调用点检查。
_cq_consume_production_handoff上游分析LOW：直接_run_cq_acceptance，另涉及CLI
main与checkpoint只读验收入口。detect_changes返回low，但部分符号／文档位置映射
明显受旧索引影响；结合实际diff和调用点检查，不据此声称完整图覆盖。

## 验证

- 第一批交接回归先3 failed／13 passed，分别复现新输入后等待覆盖、恢复后丢失和
  缺显式取消；修复后16 passed。另补创建失败后普通等待不重试，随下述相关集通过。
- 只读重验专项先4 failed，入口均拒绝显式retry_of；修复后4 passed。随后补真实
  Host MCP→FIFO参数传递，及新attempt的公开／隐藏目录隔离。
- 最终首批相关集：**256 passed，20.21秒**。覆盖阶段交接、旧调优反例、只读重验、
  CQ交接／完成、Host操作／MCP及CLI报告不可覆盖。测试仅用throwaway run、文件系统、
  本地FIFO及既有运行时fixture，不调用外部模型或原业务项目。
- 全量Team回归：**3468 passed、12 skipped、318 subtests passed，582.34秒，退出0**。
  运行环境Python3.14.3；日志保留359条warnings（含多线程fork弃用提示），没有测试失败。
  随后的最后兼容检查发现新可选参数占用了MCP包装函数旧request_id的位置，补原位置
  调用反例先失败后修，将retry_of放到原参数之后。最终MCP／重验／阶段交接专项
  **43 passed，2.90秒**；全量中不受该签名顺序变化影响的其他结果复用，不重复相加。
  其余运行代码与全量输入一致；最终专项覆盖本次最后代码变化。
- 其余变更Python文件Ruff通过。runner.py存在与HEAD完全一致的7项既有诊断：
  F401在134／154／166／176，F811在150，F841在2338／4531；本次未新增诊断，
  未为修复这些无关历史问题扩大diff。Delivery skill validator、相关Markdown链接／
  围栏、数值JSON和git diff格式检查通过。

相关命令：

```sh
cd backend
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_delivery_phase_threads.py ../modeling_team/tests/test_delivery_tuning_regressions.py ../modeling_team/tests/test_cq_reacceptance.py ../modeling_team/tests/test_r3012_handoff.py ../modeling_team/tests/test_r3012_completion.py ../modeling_team/tests/test_host_ops.py ../modeling_team/tests/test_host_ops_mcp.py ../modeling_team/tests/test_r3012_partial_judging.py -q --tb=short
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q --tb=short
```

全量日志保存在gitignored
`workspaces/delivery-runtime-parity-20261019-repair/team-tests.log`。
最后兼容专项见同目录`final-mcp-tests.log`。
未改backend／frontend代码，无产品服务重启要求。原DSH进程／冻结提示不会因源文件
修改自动重载；本次不以旧进程证明新版本采用。工程通过不证明实际切换、Agent停止
重复催办、独立业务语义或真实净token下降。

## 后续真实采用核对

- OPT-20261019-DSH-03：实际显式交接后收到新输入及普通yield，仍在安全空闲时切换；
  最新约束、未决项、所有线程与冷启动成本完整归属；显式取消、未知写入继续受控。
- OPT-20261019-DSH-05：相同冻结／终态催办不再反复创建新delivery，过期反馈不
  覆盖新accepted回执，实际必要消息和输入完整性仍保持。
- OPT-20261019-DSH-07：同run失败验收已留最终报告时，显式新attempt完整执行原
  要求的公开／隐藏组，原模型／写门不重开、旧报告不改；无故障样本记未触发。

以上为用户本次已授权修复项，均保持**已实现待实测**；新07是原R3.0-012／029／032
接续缺口的调优子项，不是另建产品机制。030整体仍部分实现／部分验证，F4未实施、
021暂停；费用、完整净收益与重复性不因本次工程修复关闭。
