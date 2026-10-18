# DSH low 第二次任务：终态空闲询问窄修

授权：用户授权 DSH / deepseek-flash / low 建模三轮、结束后关闭；首轮运行故障后，
明确选择“授权最窄修复并继续”，保留剩余两轮。归属
[R4.3-031](../../requirements/requirements-v4.3.md#r4-3-031) 的运行存活／停止边界，
沿既有 [modeling-dev-loop](../../../skills/modeling-dev-loop/SKILL.md) 恢复原业务目标。

## 原始失败与窄修

Session `minimal-chain-20261018-dsh-low-b`，首轮
`run-20261018-minimal-chain-b1` 于 11:38:25Z 真正开始，消耗 1/3 轮。
当前业务仍为 R4.3-026 的两个概念和一条安装位置关系。两批 apply_atomic 到 revision2，
实际治理读回、关联检查和 modeling_finish_changes 已完成；Modeling 与 Coordinator
的终态回执分别于 11:44:14Z、11:44:23Z 接受。原 Runner 随后以
`dsh-dispatch-closed` 失败并 CLEANED，正式交接和独立验收未执行。
模型按 failed-written-retained 保留；原日志、冻结池和失败现场没有改写。

Runner 的 `_check_cooperative_idle` 在生产角色已经提交终态、CQ 仍等待 Host 交接时，
仍会向 Coordinator 派发 idle-inquiry。DSH 在接受终态后关闭新输入；该派发异常逃出
drain 导致清理。DSH 没有 Codex 的 last_output_monotonic 接口，这条路径在全员空闲且
启动基线超过300秒时即可触发。没有将生产终态等同最终语义完成。

T0：询问已终结角色不保护源忠实度、范围、模型正确性、授权、application 或写入完整性，
无需保留该派发。最小变更仅在 Coordinator 已存在真实 transport result 时跳过空闲询问；
普通活动 Coordinator 的既有询问、写入对账、独立验收及资源收尾继续适用。
不放开 DSH 终态输入、不伪造交接、不重放已应用 Batch，也不增加恢复机制。

两个参数化回归（completed／blocked）先在旧代码失败，均证明终态 Coordinator
仍收到错误询问；另九个既有询问用例通过。修正仅4行生产代码及该行为回归。
仅改 modeling_team，不涉及 backend／frontend 产品代码，无需产品服务重启；
新 Runner 才加载修复。

GitNexus impact 对 `_check_cooperative_idle` 返回 Target not found / UNKNOWN。
实际定向核对唯一生产调用点 drain、transport results 和 DSH send_message 终态拒绝；
不声称图覆盖。测试日志及后续真实运行原件保存在
gitignored `workspaces/minimal-chain-20261018-dsh-low-b/`。

## 验证与任务接续

定向空闲询问及实际固定 DSH runtime/events 回归 **30 passed，73.53秒**。
命令在 backend 目录：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
  ../modeling_team/tests/test_cooperative_idle_inquiry.py \
  ../modeling_team/tests/test_dsh_runtime.py ../modeling_team/tests/test_dsh_events.py -q
```

Team 全量 **3317 passed、12 skipped、318 subtests passed**，492.37秒，退出0；
359项既有依赖／fork弃用告警保留，不将跳过项当真实环境覆盖。原件为本轮
`repair/team.log`、`repair/team.xml`；定向检查及源码摘要为
`repair/targeted-verification.json`。工程检查、真实运行和独立语义验收
分别记录，不将本修复当作语义 PASS。

第二轮 `run-20261018-minimal-chain-b2` 于11:51:15Z真正开始，已用2/3、剩余1；
加载的Runner含本次修复，代码尚待本轮完整检查后提交，原baseline摘要不事后改写。
原首轮不再写入；不因技术修复追加次数。

原DSH Delivery于11:51:56Z因`CONTEXT_WINDOW_EXCEEDED`／HTTP400退出。
新诊断记录给出`context_window_exceeded`，请求259条消息、2502856字节，
`max_tokens=256000`；前一成功请求记录input5848／cache_read775680。
保留原native会话及supervision_interrupted，不通过截断历史或新线程冒充原会话恢复。
外层Host沿既有工具推进同一b2，不产生第三次semantic start，不改角色模型或业务内容。
Delivery完整自主交付未通过。其finally撤回了原Runner继承的bootstrap key；
Host仅恢复该同一key以继续获准live run，并记录必须最终撤回。

## 最终结果与关闭

第二轮使用本次修复，生产两个原子批次到revision2；完成治理读回、关联自查、资源关闭，
Modeling及Coordinator均真实terminal_report_accepted。超过原空闲询问窗口后Runner仍存活，
Host原complete_cq_handoff接收成功：ready=true、pending_writes=false、unknown_writes=[]、
write_phase=read-only，正式进入acceptance_pending。场景地图、拓扑和运行期公开CQ/freeze
沿035自动接线，Host没有手工复制或代写语义产物；两次实际私有CQ审核与宿主技术接续披露。

显式runtime=dsh、dsh-acceptance-deepseek-flash-low，先公开组，再隐藏组三题，
每题Consumer和两组Judge为独立只读会话。原报告均full_pass=true：**公开1/1、隐藏3/3**，
无未执行题、model_state_drift或证据重验漂移，两组model_binding_digest相同。
报告标为non-blind-regression；结论只适用于本人工最小链，不外推大业务、盲测或L2。
原complete_cq_acceptance按隐藏报告绑定被源Runner接受；模型、冻结池、报告和首轮失败保留。

用户要求的关闭已执行：源stop回执accepted/stopped，两run均CLEANED、PID退出、FIFO移除；
两验收owner lifecycle=stopped且active/retained成员均空，原DSH Delivery亦已退出。
收尾只读核对16个登记PID均不在/proc，DSH cleanup complete且无residual；
12把登记临时key数据库读回均revoked，其中本次关闭补撤3把（恢复的原bootstrap及两个验收读key）。
验收operation的外层status字段仍保留running旧值，不能仅靠它判存活；
本次关闭结论依据owner停止、成员空和全部登记PID实际退出。

**实际用2/3轮，fresh semantic starts=2；无额外实质修模轮，未用1轮已撤回。**
沿原DeliverySession.apply_user_control撤回后续production/evaluation/repair准入；
未启动新的原生推理，也未把原supervision_interrupted改写为自主finish_delivery成功。
这次是**有宿主补位的有界独立语义PASS**，DSH Delivery完整自主交付仍未通过。
窄修复提交`e463cd3`；既有其他工作区修改未纳入提交。

完整原件位于gitignored `workspaces/minimal-chain-20261018-dsh-low-b/`：
authorization.json、final-report-verification.json、acceptance-completion.json、
final-lifecycle-verification.json、final-process-verification.json、final-key-verification.json
及final-delivery-permission-closure.json。原生数值收集沿019既有usage_report生成器，
见usage-scope.json、usage-report/report.json和report.md，包含两轮、失败Delivery及六个验收会话。
Host/scoring/部分失败用量及账单缺口保留unknown，不声称全任务成本完整或真实净降耗。
有效语义／技术／等待时间未可靠拆分，保留unknown；原始阶段UTC墙钟不冒充有效工作时间。
