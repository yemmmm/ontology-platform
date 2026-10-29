# v5 多工作单元交付与运行记录

日期：2026-10-29。范围与来源见[最小接入](../../research/2026-10-29-v5-multi-unit-minimal-integration.md)。
用户确认继续；当前授权最小链已完成，独立公开工程检查 **1/1 PASS**。此前因 HITL
等待而为 PARTIAL；用户随后授权宿主构造测试答复，已在原 run 完成父级应用与读回。
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

上述为初次实现检查。测试代答接续中补齐写入会话生命周期后，最新完整回归为
**133 passed，1 条既有 warning，130.97 秒**；针对性 Host 检查 **9 passed，4.56 秒**。
日志为 `multi-unit-20261029-completion-tests-final.log`、`multi-unit-20261029-session-restore-tests.log`。
最新 5 份 Markdown 的 66 个本地链接及围栏、最终 Ruff／暂存 diff 检查通过；本次 staged
detect_changes 为 7 个文件、0 已索引符号／流程、low，仍受前述索引缺口限制。

核心用例使用真实 PostgreSQL／checkpointer，验证：

- A 持久等待，B 继续到 proposal_ready，父级不提前应用。
- B 仍在原生活动中，A 的新答复已被消费，避免整体 barrier。
- 换调度器／连接后 B 的原结果不重放，父级按材料引用消费两份实际候选并只应用一次。
- 旧的过严 HITL 校验失败后重解析原始回执，不再调用 Agent，旧回执字节不变。
- 子级身份、输入和 snapshot 中的独立等待点保留；生产与独立验收工具边界沿旧测试覆盖。

确定性 Actor 不证明真实模型语义；本次另有下述实际应用／治理读回和公开小场景独立检查。
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

答复前 installation 为 waiting_input，verification 为 proposal_ready，父级 waiting_children；
active={}，无后台模型调用。快照 local-hitl-wait-sibling-ready 保留此状态和两个独立 checkpoint。
该时点估算金额 0.16640276 元，剩余 0.83359724 元；包含失败及技术恢复，不当作正常任务成本收益。
价表为用户配置版本，非提供商最终账单。Host 用量 unknown，单列不扣任务金额。

## 人工等待与测试代答接续

实际请求 `human-request-4aca378ca7957e53c61c8485`：安装活动的正式名称是什么？
此前通过用户入口提出并等待；随后用户明确“测试阶段不需要我亲自介入，你构造回答回复即可”。
据此构造“演示安装作业”，以 host-test-answerer 署名，通过原 CLI reply 关联原请求；
答复正文明确是用户授权下的测试构造，并非用户亲自作出的业务确认。授权、原文和答复
保存在 test-answer-authorization.json／test-answer-installation.txt，未修改冻结业务材料或题集。
答复只影响安装活动；核验有效成果保留，无需重做。

通过上述答复 resume 同一 run；安装实际消费答复、解决原请求，并 search/read 核验共享
记忆。父级实际 read_material 原文及 read_handoff_material 两份完整子级结果后整合。
原运行、工作空间及金额账本未更换，没有新建 semantic start 或预算清零。

路径为 `workspaces/v5-runs/multi-unit-20261029-start1/`、
`multi-unit-20261029-inputs/`、`multi-unit-20261029-budget/`。progress.json 保存当前等待
与接续指令。当前已 written-retained 收口，四个本轮凭据经后端只读核实均已撤销，
active={}；模型、记忆、任务卡、快照和原始失败证据均保留。

## 父级闭环、修复与证据边界

- 父级 apply-00000／00001 使用 fields-only change_id 作为 definition_ref，编译器明确
  返回 not_written。核对 R4.3 当前合同后，只修 v5 提示中 item/change 的歧义；原输入队列
  收到署名 host_tool_contract 澄清，不增加业务事实，也不扩展前向引用能力。
- apply-00002 成功建立三个 Class，模型 revision 1。真实自查发现还缺显式关系，返回
  revise，保持既定范围继续分批构造；不是重复初建或新实质修模。
- apply-00003／00004 因此前已应用 Session 的租约仍存在而 not_written。v5 Host 现于
  后续提交前恢复原快照中的生命周期身份、刷新 Session revision 并调用既有关闭接口。
  历史明确 not_written 不再阻止最终收口；未知写入和不完整应用仍须对账。
- 第一版关闭补丁曾重建空执行器，产生 closed=true、session_id=null 的无效关闭证明。
  原回执另存 `session-completion-before-context-restore.json`，修后真实恢复并关闭
  c4244024-e9d3-4138-b4b5-98c40c0b2f60、617ab191-5f95-4d39-bef7-835ccea8088f，非伪造空回执。
  本轮第二次写入发生在旧租约到期后，故其成功本身不证明提前释放效果；先关闭再提交的
  顺序由回归覆盖，修后真实关闭了两个 Session，其中第二个在租约尚未到期时关闭。
- apply-00005 成功补齐三条 relation_type，模型 revision 2。两次实际应用分别建立概念与
  关系；四次明确未写入的尝试保留。后续治理自查 ready，未重放已有概念写入。
- 父级普通状态通知曾重新唤醒两个子级，包含重复／歧义结果后的纠正。这些额外调用全部
  计入统计；后续再打磨通知与工作阶段，不据此宣称高效协作。真实答复到达时兄弟单元已
  完成；“兄弟仍忙时立即消费答复”在本批为确定性回归证据，不冒称真实同时接续。
- multi-unit-check-001 使用独立只读原生上下文，实际读原文、测试答复与模型，取得公开
  冻结工程判据 1/1 PASS。只覆盖该小材料，不外推完整 P2 或生产业务语义验收。

最终三个 Class 为演示设备、演示安装作业、演示核验作业；三条关系定义表达作用对象、
核验安装结果及“核验通过才可完成”的业务条件，未声明为平台强制执行规则。
最终快照 multi-unit-evaluated 的 model_read_error=null；初始快照仍保留 model revision 0，
完成快照为 revision 2，三个独立工作 checkpoint 与对象差异可查看。

Project `4dda3ff6-33e0-4d70-b606-16b8b3da6577`，Ontology
`281a3d19-b6af-45f0-b29d-9f6240cae816`。完整总结在 runtime-summary.json，生命周期证明
在 session-lifecycle-verification.json，凭据核实在 owned-key-verification.json。

共 1 semantic start、1 初建轮次；21 次原生执行：安装 8、核验 4、父级建模 6、自查 2、
独立评价 1。215 个上游请求均与账本匹配。输入 2639088（缓存 2354176）、输出 34316，
总计 2673404 token；按冻结用户价表计价 0.46925952 元，加暂估 0.034284 元，
charged_estimate 为 0.50354352 元，余额 0.49645648 元。包括全部失败／恢复及额外交互，
提供商结算覆盖仍 PARTIAL，外部 Host 用量 unknown、单列不扣任务金额，不推导净降耗。
首个上游请求 12:33:13.184319Z，最后请求结束 13:26:12.026528Z，凭据收口至
13:27:32.919995Z。墙钟包含人工等待、技术修复和基础设施往返，非纯语义时间；有效分类计时 unknown。
