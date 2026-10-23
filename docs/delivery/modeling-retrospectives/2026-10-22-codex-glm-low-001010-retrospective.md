# 2026-10-22 最新最小链：质量通过，Delivery 降耗仍需调整

本轮整体走通，模型一轮完成且独立四题全部通过；流程仍有可自修复的格式和交接返工，
不能称全程无故障。当前最值得优化的是 Delivery 的等待输入与拓扑错误反馈，而非重做模型。
本次按 modeling-retrospective 核对保留证据，不启动运行、不修改模型或运行代码。

## 范围、身份及需求验证

- session：`minimal-chain-20261022-codex-glm-low-3cny-001010`；run 为同名前缀加 `-r1`。
- Task `r4-3-026-minimal-installation-chain`，Profile `unified-modeling`，唯一业务源为原 scenario.md。
- Codex／glm-5.3-flash／low；启动代码 `e4bcf47`，baseline
  `6fd49b9f654abb41b87cacc136fa6b2bea8aeaafd01b49aa1bf3a1155a206c53`。
  授权、实际角色配置与 baseline-manifest 相符，不用当前文件代替旧进程加载证据。
- 金额授权 3 元，同一 budget_ref；初建 1 轮、fresh semantic-start 1 次，无实质修模。
  技术纠错不额外计轮；旧任务停止是本轮启动前的另项用户指令，不作为本轮建模失败。

| 关联需求 | 本轮验证结论 | 仍有边界 |
| --- | --- | --- |
| R4.3-026／024／025 | 部分验证；当前通用方法最小链 A2 有界独立非盲 L1 通过 | 两批应用、实际治理读取、自查和四题裁决成立；复杂业务、其他变更类型及重复性未由本轮覆盖 |
| R4.3-029 | 部分验证；Host 私审、冻结、生产到验收回交及安全只读收尾实际完成 | 普通内容／警告持续进入决策、过早交接及终态描述不准仍有反例；不宣称全部自主职责条件通过 |
| R4.3-022／030 | 部分验证；F3 两次实际切换、观察合并及有界读取采用成立 | 完整任务 ≤10M 子目标验证未通过；F1/F2 的无必要往返及净效果仍待调整 |
| R4.3-019／R4.4-002 | 部分验证；12 个已知线程、三 Delivery 线程与金额监视有数值 | 缺失数值请求、未接线辅助调用、暂估和尾差未结；本轮未触发预算暂停／恢复 |

上述结论追加到相应权威需求，不撤销历史工程或其他轮次 PASS，不将未触发场景判失败。

## 质量与时间

两批 application 为两个 Class 和一条 relation_type，revision 0→2；最终关联检查 COMPLETE，
3 个资源、21 条 statement、0 issue。生产治理读回与独立 Consumer 读取相互区分。
公开 1/1、隐藏 3/3 均为有效 pass，无未执行题；两报告的冻结与模型绑定一致，
evidence recheck 为 3＋8 条，drift／unavailable 均空。独立执行为只读验收，Consumer／Judge
与生产线程分离。本复盘核对既有裁决，不担任新的最终验收者。

报告明确 `non-blind-regression`，不能改称新题盲测；不覆盖原小链、工业服务全场景或 L2/L3。
安全收尾为实际 `READ_ONLY_WAIT/read_only_wait/working/read-only`，写入凭据非活跃、
Session 终态，无 pending／unknown／in-flight write；原 Team／Consumer 按既有合同保留。

| 事件（新加坡时间，2026-10-22） | 时刻／窗口 |
| --- | --- |
| 授权记录 | 08:10:10.433 |
| 真实 semantic start | 08:10:50.300，授权记录后 39.87 秒 |
| 完整题池冻结 | 08:13:42.822 |
| 拓扑 gate 接受 | 08:16:22.973 |
| 两批应用回执 | 08:16:50.330／08:17:29.262 |
| 生产交接 | 08:21:00.025 |
| Runner 验收闭合 pass | 08:24:24.104，semantic start 后 13分33.80秒 |
| finish_delivery 返回安全只读等待 | 08:25:20.476，授权记录后 15分10.04秒 |
| 已有用量快照截止 | 08:26:18.711，授权记录后 16分08.28秒 |

这些是阶段墙钟，不是有效语义工时；语义／技术／等待互斥分类仍 unknown，不计算占比。
本次复盘和文档工时另属事后工作，不回填为原任务已实现的节省。

## 已确认优化：实际采用与待调整项

- 原 OPT-20261019-DSH-03／030 F3：production、acceptance 两次真实 `switched`，
  共三线程计量成立；保持整体待调整，不从局部采用推导完整净降耗关闭。
- 原 OPT-20261019-DSH-05／025：unsupported unknowns 字段被拒后，Modeling 实际采用
  已有 `request_ref＋request_edits`，仅删除 fields 层冗余键后应用成功；原语义 unknowns
  留在 semantic_definition。该纠错子路径有效，首次正确提交和整体稳定性仍待调整。
- 10-21 CQ 顺序纠正：全景审核提交后约 42.64 秒完成 Host 处理；切片审核提交后约
  11.16 秒完成处理；全景批准到切片起草约 38.26 秒。局部顺序改善有证据，地图／拓扑
  仍有格式等待，不据此关闭全部准备效率预期。
- 022／030 已有观察合并：15 条合并记录、38 条 accepted dispatch，实际采用成立；
  但累计 85 个决策包、40 次 yield 调用（36 次成功登记）仍未解决等待期间的大量往返。
- 013／029 的引用交接仍有一次材料通道拒绝；014 恢复、028 既有模型增量、预算暂停
  本轮未触发，维持原状态。015 的阶段反馈不以最终四题验收替代。

## 用量、金额与相邻轮比较

已有冻结快照统计输入 11,107,509、输出 55,593，已知托管链 **11,163,102 token**；
缓存和推理是子集不重复相加。Delivery **7,245,302（64.90%）**，Coordinator 1,338,153，
Modeling 1,266,487，CQ 199,890，验收角色合计 1,113,270。
已知下界已超过 10M，故该量化子目标明确未通过，不只是缺证据。

预算快照估算 **1.93386172 元**，其中数值定价 1.07208772、暂估 0.861774（44.56%），
剩余估算 1.06613828；control_status=open，pause_epoch=0。不是供应商账单或最终结清。
计量截止 08:25:27.527，仍显示两个在途单元和未知尾差；总体覆盖 PARTIAL。
外部 Host 仅单列、不扣金额；其他获准辅助调用缺测继续保留，不当作零。

紧邻的凌晨 max 轮（15 元授权）同为通用方法最小链、初建一轮、独立四题通过。
本轮 start→Runner pass 13分34秒，前轮约 23分18秒；本轮托管已知 token 比前轮
9,323,415 高 **19.73%**，Delivery 比前轮 5,351,297 高 **35.39%**。
effort、代码（e4bcf47／72d4514）、故障和统计截止不同；只能说明本次更快且已知 token
更高，不能认定 low 导致增耗，亦不能仅凭预算较少宣称更省钱。

## 逐项定位及最小建议

| 现象与原件 | 原因、影响及定位把握 | 最小调整／验证 |
| --- | --- | --- |
| 85 决策包中 29 个仅 events 变化；yield 40 次 | 已定位当前事件投影仍对 warning/configWarning 和部分原生工具完成通知推进事件链；源码 `_is_decision_event_noise`／`_decision_events`。原始启动警告 35 条，选择后按 source+offset 去重仍有 warning 18、configWarning 9 条；这不是 27 次独立唤醒，不能等额折算节省 | 优先沿022／030按实际等待条件核对唤醒价值；不变警告去重、完整原件保留、真实错误／授权／写入异常继续送达。保持四题、回执、必要催办，验证实际往返和全链 token；不将29包全部判无用 |
| 拓扑 08:12:43／08:12:55 两次 schema mismatch，08:16:22 才开门 | 已定位 Agent 先带不适用 ontology_plan，去掉后仍漏 decided_by；Runner `_check_multi_slice_topology_gate` 调用校验器后只传 reason_code，丢失已有 issue.detail；候选状态路径在两角色内不可读。冻结→开门约2分40秒是窗口，非全部可删耗时。首阻塞为 platform-contract，Agent格式错误与 prompt-contract纠正未可靠采用同时保留 | 先按T0复核 decided_by／固定比较格式是否需要阻断当前安全写入；若保留，必须给具体字段和实际可读定位，不再让Agent猜同一粗码。授权、真实归属及原子应用保持；以原失败形状的窄回放验证，不新建守卫 |
| 6次模型提交，仅2次应用 | 两次原生JSON解析失败、一次scope_binding_required、一次unsupported_change_field；非语义修模，未写入时可自修复。小补丁纠错已成功，工具没有业务内容错误的反证 | 保留 request_ref/edits；较大正文优先沿已有可发布JSON引用，减少重复内联转录；不新增重试次数门。验证首提正确性及失败后同轮恢复；完整质量保持 |
| 两次过早 complete_cq_handoff，随后两次等待已拒请求 | 已定位：未等真实生产终态变化就交接；提交回执只代表submitted，拒绝已在Runner产生；yield给出精确 delivery_wait_already_rejected 后，Delivery改为等待角色并用新ID，第三次成功。首层 collaboration/routing，无永久死锁 | 沿029权威决策步骤先核对真实settlement再交接；拒绝结束当前请求，等待依赖后新ID。不新增平台编排门，不删除保护未完成生产／未知写入的原硬门；验证同类路径不重复无效交接 |
| Coordinator 首次终态 report 被 material_forbidden 拒绝 | 已定位其引用来自Modeling发布给Coordinator的材料，不是自己向Runner发布的材料；随后自建短报告并发布，28秒内成功。权限拒绝正确，013原能力已有 | 使用本角色真实发布回执；或无材料时沿合同内联，不跨错通道转发材料ID。不新增中转层；验证真实收件方可读 |
| 自查query降级及扩展不完整 | 已定位到评分服务边界：ranking.reason=timeout，expansion.stop_reasons=scoring_unavailable，18.63秒查询窗口；独立四题后续读取／裁决通过，不能推导模型缺事实。供应商内部原因无证据 | 当前保留精确治理读回与警告；再次发生时用现有评分请求／服务日志定位。不为单次超时增加全局预检、延长所有timeout或强制重复全量查询 |
| 最终文字称“进入standby／无超授权调用” | raw状态实际read_only_wait，standby请求被接受只证明按合同安全保留；费用仍有暂估／在途，不能证明全部调用已结。已定位为报告措辞过强，不是资源安全反证 | 沿真实状态和估算范围描述；无需强制改状态、停团队、热加载或新增生命周期机制 |

首条 yield 还缺实际 run/request 绑定、一次等待已完成 Host 审核；均收到精确可恢复反馈后
自行纠正，归入同一等待采用问题，不另建优化编号。启动警告中的模型metadata fallback
仅为警告，实际窗口仍有配置证据；ignored default_tools_enabled 来自 Codex 生产／验收线程配置。
没有工具越权证据，不由此宣告隔离失效；其去重可沿现有输入路径处理，不扩成安全整改。

优先顺序：**等待输入及无效交接 → 拓扑反馈／T0收窄 → 首提与引用交接采用**。
前两项已有重复证据且直接作用于最大开销；不承诺具体节省分钟或比例。
评分偶发超时和费用暂估保留为有界待证，不建设额外harness。后续验证复用原合同、
完整题集和获准运行，若漏错误／降质量则恢复该局部输入路径；未经新授权不开展真实验证。

## 原件定位与本次交付边界

宿主目录：`workspaces/minimal-chain-20261022-codex-glm-low-3cny-001010/`：
`authorization.json`、`result-summary.json`、`usage-snapshot-002618/report.json`、
`final-budget-snapshot.json`。运行目录为 `workspaces/modeling-runs/<run_id>/`，
Delivery目录为 `workspaces/delivery-sessions/<session_id>/`。

- 应用／时序：evidence 下 semantic-start、staged-decisions、cq-freeze、multi-slice-gate、
  cq-handoff-complete、cq-acceptance-complete、outer-input-receipts、team-lifecycle JSONL。
- 行为／错误：runtime 各生产角色原生 rollout、Delivery native/sessions 的三线程 rollout、
  session-events.jsonl；源码 runner.py、scenario_map.py、delivery.py 为对应责任面。
- 两份原 batch-report 分别在 acceptance-v3/public-regression 与 reports 下
  `cq-batch-0001/attempt-0001/`；实际文件 SHA256 为
  `8e96ee3c3212dae1cace48ac1743646b1a850370756a3279b8b84ddb44f3d43c`／
  `e2fe87e3a7c02f98649a70c751eba128e6554bc5041da746e16344bbe0f471a8`，已对照绑定核验。

只更新本报告、关联需求验证追加及已有优化台账；无新确认优化编号、代码、模型调用、
预算或生产写入。本次只作diff／链接／数值与合同检查，不运行工程测试、重启服务或代替独立验收。
