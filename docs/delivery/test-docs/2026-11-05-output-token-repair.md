# v5 输出 token 修复与有界验证

日期：2026-11-05。归属：R5.0-012、R5.0-002，沿 R4.3-019/030 保留完整计量与净效果边界。
用户同意实施此前 [harness 评估的 A—D](../../research/2026-11-05-harness-differences-and-output-repair-options.md)，
授权真实建模到必要验证点后停止，可使用检查点。不要求本轮完成整个 Demo 或 36 题独立验收。

## 结果与验证范围

本轮目标是减少阶段无关指令、候选正文重抄和格式纠错。使用相同完整 Demo 的五份公开生产材料，
全部托管角色保持 Codex / glm-direct / glm-5.3-flash / high、并发 2；未降模型、effort 或截断输出。
私有 36 题仅保留原评价配置及身份，本轮未读取题目/答案，也未运行 L1。
当前有直接降幅证据的是完整来源分析阶段：输出 **27,199 → 13,384，减少 50.79%**。
正常阶段复用、提案提交及整任务净效果分别按下文证据记录，不将单阶段数值推广到全任务。

## 最小实现

| 批次 | 变化 | 兼容与证据边界 |
| --- | --- | --- |
| A | prepare 冻结 intake/propose/self_check 提示；intake/self_check 移除候选表示语法，保留源忠实、条件/例外/否定和未知 | propose 保留完整表达语法；旧冻结包沿原 instructions |
| B | submit_role_artifact 暂存原作者正文，原候选纯校验在本 turn 返回反馈；最终只交精确引用和小信封 | 暂存不应用本体，不裁决语义；回执绑定作者/执行/代次/阶段/basis，独立验收不变 |
| C | 未变来源版本允许同 actor 的正常阶段复用已完成读取及匹配的原生上下文 | 新 CQ/scope/model/业务答复须重新判断；旧正文不自动适用；损坏证明/线程绑定回退新读/新上下文 |
| D | 提案只保留一份署名正文，交接发布原结果、变更 ID、冲突、依赖等索引，正文仍可实际展开 | 读索引不代表读正文；intake、候选自足业务字段、原属主治理检查和独立验收保留 |

生成规范与容错解析分开：prompt 和工具参数展示统一图 v2 的根字段、业务 item 字段及完整变更外形；
执行仍保留宽松 decoder + 原 canonical validator 的聚合错误。此前宽松 decoder 被直接当作生成 schema，
真实 Modeler 返回仅 items/name/definition 的 55 项候选，造成格式返工；Host 未替其翻译或补写业务语义。

新包重新判断原件适用性后，可用 submit_role_artifact(artifact_ref=自己的原件) 避免重抄；
没有有效提交回执不能仅靠 retained_ref 进入新包。旧冻结包保留同基线的引用纠错兼容路径。
纯候选校验所需的三个 Python 文件窄挂载到隔离环境，不挂整仓库、旧 Runner 或私有目录。

真实运行另暴露三处合同阻塞，沿 T0 做窄修：共享声明允许实际 Coordinator actor；
相同 CQ 业务正文但不同精确材料的通知拥有不同身份；当前 WorkPlan 明确给出的公开 CQ 材料可由已注册
生产成员读取。后两项保留私有/其他材料权限和实际完整消费证明；未增加角色、审批或硬顺序。

GLM 小信封 outputSchema 探针虽 HTTP 200，却返回无真实读取的占位 JSON，因此生产不强制该选项。
其失败调用照实计费；不能以工具支持声明或 HTTP 成功代替实际兼容采用。

## 工程验证轮次

日志位于本机 gitignored 的 workspaces/v5-runs/demo-output-high-20261105-inputs/。

- 阶段提示、工具暂存与新流转均先以反例复现；开发中修正误放 feature flag 和测试 fixture 的适配/时序。
- 首次完整 v5：437 passed / 3 failed，1018.94 秒。真实问题为 CQ 材料通知身份冲突与裸非推理工具探针
  误取专业 JSON；已分别修复。受影响 89 项随后通过，552.44 秒。
- 最新合同/Team 25 项通过，66.56 秒；补充 canonical schema 展示和缺 receipt 负测先 RED 2 项。
- 修复后 output-contracts **14 项通过**。一并运行的旧纠错夹具另有 4 失败：缺 completed/thread_id 证明，
  或误认为新业务基线会删除未变来源的已读事实；保留正文失效检查后修正夹具，5 项通过，13.43 秒。
- 最终阶段提示/旧包兼容 2 项通过，0.47 秒；新包拒绝缺回执引用与旧包保持兼容的对照 2 项通过，7.65 秒。最终完整 v5 结果：**447 passed**，1042.22 秒（17m22）；1 条已有 Pydantic lifespan 注解 warning，无失败。
- Ruff 与 git diff --check 通过；最终独立代码复核：0 Critical / 0 High；复核者未另跑测试或模型。

GitNexus 的 freeze_team/CodexInvocation 未被索引，风险为 UNKNOWN；提交前 detect_changes 识别 18 个变更文件、0 个符号，不能据其 low 标签声称图覆盖。
采用直接调用检查：TaskBinding.prepare/for_unit → freeze_team；role_work → ExecutionManager →
CodexInvocation → CodexAgent/material_tools；独立 acceptance、平台编译/原子 apply 未改。
本轮只改 modeling_team/v5 和文档，无 backend/frontend 修改，无需服务重启。

## 真实测试与耗时

所有本轮生产探针共用 **一个独立 3 CNY 金额预算** v5-demo-output-high-20261105；未追加。
旧 demo-role-high-20261105-start1 及其已耗尽预算保持暂停，不迁移旧材料/方法或继承验收结论。

主任务 demo-output-high-20261105-start1：授权记录 07:18:25Z；驱动 07:26:59Z 启动。
首次原生 turn 07:27:16Z（8 分 51 秒）返回占位结果，不能称成功来源分析；随后 CQ/Coordinator 有真实读取。
首段 07:26:59—07:42:57；第一次恢复 07:52:34—08:16:23，保留原始失败正文和所有消耗。
第二次恢复 08:46:52Z 后验证完整 canonical 工具提交，到首个成功候选暂存请求暂停，自然结束原生 turn。
08:55:39Z 成功暂存后请求暂停，08:56:57Z 原生自然收口，恢复段共 **10 分 05 秒**。
原作者提交统一图 v2 的 **45 项 candidate / 45 条 changes**，正文 32,681 字符；
最终信封 **3,274 字符**、artifact=null、引用与接纳正文完全一致，状态 proposal_ready。
本次提交无工具错误；沿原线程复用确切来源读取事实，补读当前公开 CQ，两页完整返回。
D 的索引/单独正文已实际发布，接收方消费只做了工程验证，未在本轮继续推进。
主检查点 candidate-staged-output-repair-verified / 1b2c3f5ae92a4fc7b347cd7bf0340a51，
包含平台状态，读取无错误。模型 revision 0，未 apply。两个 run 均 mode=paused、status=settled、active={}。

来源分析单阶段探针 demo-output-high-20261105-intake-only：08:14:46—08:20:25Z，
**5 分 39 秒**（含 prepare/接纳），只派 Modeler，不重复 Coordinator/CQ。
结果 source_intake / proposal_ready，issues=[]；26 条命题、13 条未知，正文经工具暂存、小信封被正式接纳。
五份原材料均实际完整读取：scope 279/279、business 1546/1546、API 13424/13424、schema 1036/1036、
公开 CQ 5020/5020 字符；SHA 与原批准 manifest 一致。完整读取不等于命题语义已独立验收。

| 来源分析 | 旧完整 Demo/high | 新相同生产材料/high |
| --- | ---: | ---: |
| 输入 | 409,896 | 125,458 |
| 输出（含推理） | 27,199 | 13,384 |
| 其中推理输出 | 14,656 | 9,564 |
| 其余输出 | 12,543 | 3,820 |
| 输入 + 输出 | 437,095 | 138,842 |

来源阶段输出降 50.79%，总 token 降 68.24%；未做独立同质量判定，也不是整任务净收益。
新 5m39 含 prepare，旧约 448 秒为原生窗口，边界不同，不计算精确耗时降幅。
检查点 intake-output-reduction-verified / 411b3e4d5d70463e911a8feb30d66d94，包含平台状态，读取无错误。

## 完整本轮用量及停止状态

从本次建模授权记录到最后原生收口共 **1 小时 38 分 32 秒**，包含准备、失败、Host 修复/测试暂停和
并行探针；并非纯模型生成耗时。58 个已完成 provider 请求的区间并集 **52 分 49.76 秒**。
剩余时间主要是技术修复和验证暂停，未称 Agent 整段持续生成；本轮不是同完成度耗时对照实验。
费用估算 **1.49521556 / 3 CNY**，11 个原生执行均有用量，未知/暂估/在途/待结算均为 0。

| 全部新 run 的角色 | 输入 | 输出（含推理） | 输入 + 输出 |
| --- | ---: | ---: | ---: |
| Modeling（含来源单阶段探针） | 1,518,349 | 106,250 | 1,624,599 |
| Competency Question | 1,363,781 | 70,428 | 1,434,209 |
| Coordinator | 305,507 | 34,504 | 340,011 |
| 合计 | **3,187,637** | **211,182** | **3,398,819** |

输出中 reasoning 119,794，其余 91,388；缓存输入 2,588,928 已包含在输入。失败与全部恢复均未剔除。
累计终点与逐执行 baseline 差分交叉核对一致。逐执行、材料 SHA、完整覆盖、检查点及最终状态见
[脱敏统计证据](../evidence/2026-11-05-output-token-repair.json)。

复核中补修了无 receipt 的旧引用回退。另一项建议是拒绝新包的有效 inline 正文，经 T0 与实际
basis/source/canonical/generation 检查核对后未加拒绝：当前执行的新正文已有真实作者/执行绑定，
旧正文引用才额外需要 receipt；强制拒绝只会新增一次可避免的纠错 turn。复核者已独立撤回该 High，
代码/README 明确保留兼容，正常路径继续工具/小信封。

计量原件为各 execution 的 usage.jsonl、native-usage-baseline.json 和 provider-usage.jsonl；
每次 continuation 按真实 baseline 取增量，再以每个 thread 的最新累计值交叉核对。
失败、占位、纠错、两个 probe 均包含；reasoning 已包含在 output，不重复相加。外部 Host 原始用量未知，
按用户既有规则单列且不计入金额预算；不将未知记作零。阶段重叠和技术修复暂停不归因于模型吞吐。

本轮限于工程修复及有界采用/输出证据，不宣称 R5.0-012 整体 L0、独立 L1 36 题或 L2 通过。
没有同完成度模型与独立质量证据时，不宣称完整任务净提速、净降耗或语义质量等价。
