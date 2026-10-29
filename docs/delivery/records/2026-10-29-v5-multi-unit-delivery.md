# v5 多工作单元交付与运行记录

日期：2026-10-29。范围与来源见[最小接入](../../research/2026-10-29-v5-multi-unit-minimal-integration.md)。
用户确认继续；当前为 **工程实现完成，真实闭环 PARTIAL，等待实际 HITL 答复**。
不关闭完整 P2、递归父级方法或业务语义验收。

## 当前实现

一个父级加显式直接子级；独立工作／执行／checkpoint 身份、可配置并发、局部等待、
输入自动归属、任务卡、共享记忆及固定版本成果交接已接线。父级读取精确材料引用后自行
组合含义，只由父级执行实际应用。程序不自动合并同名业务定义，也不把局部成功当成整体正确。

调度器监听仍在执行的 future 和新的单元输入，不等所有业务阶段结束才恢复已获答复的
单元；没有新输入时不重复启动模型。普通暂停与预算仍在自然原生回合边界生效。
snapshot-save 包含各子图 checkpoint；reply 自动按请求路由，input --unit-id 可指定目标。

## 工程验证

最终完整 v5：**132 passed，1 条既有第三方 warning，116.76 秒**。
日志 `workspaces/v5-runs/multi-unit-20261029-full-tests-final.log`。Ruff check／format 通过。
5 份相关 Markdown 的 65 个本地链接及代码围栏、暂存 diff 检查通过。GitNexus staged
detect_changes 返回 19 个文件、0 个已索引符号／流程、low；因索引缺口不作为完整影响证明。

核心用例使用真实 PostgreSQL／checkpointer，验证：

- A 持久等待，B 继续到 proposal_ready，父级不提前应用。
- B 仍在原生活动中，A 的新答复已被消费，避免整体 barrier。
- 换调度器／连接后 B 的原结果不重放，父级按材料引用消费两份实际候选并只应用一次。
- 旧的过严 HITL 校验失败后重解析原始回执，不再调用 Agent，旧回执字节不变。
- 子级身份、输入和 snapshot 中的独立等待点保留；生产与独立验收工具边界沿旧测试覆盖。

这些确定性 Actor 不证明真实模型语义，真实父级应用和独立评价仍待下述答复后验证。
没有另设独立工程验收角色；未修改 backend／frontend、依赖或共享部署配置，无需重启服务。

## 真实运行

任务 `v5-multi-unit-20261029`，run `v5-multi-unit-20261029-start1`；父级 integration，
子级 installation／verification，全部使用 `glm-direct / glm-5.3-flash / low`。
原文 SHA256 `91fe40946e46a2c2314d07f6b3c1a3c3ac1870a55a51533aab9b9d2a4aa3208f`。
公开题集 `v5-multi-unit-public-criterion-20261029`，1 题，SHA256
`0d1e8556e64f04c8bd0fe30190121423ef859add665b696ebed5da44adc5248a`。

首轮两个原生执行区间重叠。安装 Agent 已真实返回含 question／reason／impact 的问题，
因 issues 为空被旧校验拒收，产生 5 个原生回合；原始回执全部保留。按 T0 删除重复原因
要求后，复用最后一份原回执注册同一工作单元的实际请求，没有再开提问回合。

核验首回合反复调用未注册文件 URI 的 read_mcp_resource。宿主观察到至少 119 次相同
失败，核实没有模型 application，只针对已绑定只读 app-server PID 发 SIGTERM；进程
退出确认后记录显式 interrupted 回执，native_turn_completed=false、normal_pause=false。
原生事件未改写，不把这次技术中止记为自然停稳或模型质量失败。
归因为 collaboration/routing，修复只涉及 v5 工具投影，保留真实失败用量及账本身份。

原执行对账后，在同一 run 的 verification--model-00001 恢复；实际工具为 read_material、
write_memory、update_work_card，均成功。该单元在安装请求已持久等待的窗口内继续执行：
上游区间 `12:43:47.572149Z`—`12:44:23.579399Z`，最终 proposal_ready，发布固定版本材料。

当前 installation 为 waiting_input，verification 为 proposal_ready，父级 waiting_children；
active={}，无后台模型调用。快照 local-hitl-wait-sibling-ready 保留此状态和两个独立 checkpoint。
最新可见估算金额 0.16640276 元，剩余 0.83359724 元；包含失败及技术恢复，不当作正常任务成本收益。
价表为用户配置版本，非提供商最终账单。Host 用量 unknown，单列不扣任务金额。

## 尚待完成与接续

实际请求 `human-request-4aca378ca7957e53c61c8485`：安装活动的正式名称是什么？
已通过用户入口提出；尚未收到实际答复，不采用默认名或把工程建议冒充确认。
答复只影响安装活动；核验的有效成果已保留，无需重做。

收到实际答复后，通过原 CLI reply 绑定上述请求，resume 同一 run；核对安装消费答复和
共享记忆、父级读取两份子级材料／原文并整合、实际应用、治理读回及独立公开工程检查。
原运行、工作空间及金额账本继续使用，不新建 run 或预算清零。完成后再撤销本轮凭据。

路径为 `workspaces/v5-runs/multi-unit-20261029-start1/`、
`multi-unit-20261029-inputs/`、`multi-unit-20261029-budget/`。progress.json 保存当前等待
与接续指令。当前 scope 和读凭据保留供原 run 接续，尚未执行终态 cleanup；不能记为
资源已全部撤销、真实父级应用 PASS 或独立语义 PASS。
