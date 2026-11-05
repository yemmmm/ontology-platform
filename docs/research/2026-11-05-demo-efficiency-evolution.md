# 完整 Demo 建模效率阶段

日期：2026-11-05。状态：执行中，尚未形成效率或语义结论。

本轮用户要求先提交并推送工作区，然后以 project-evolution 推进项目；短期目标为 Demo 半小时内完成，总预算15元。初始工作区7个文档已提交797cfe0并推送origin/main。

权威依据：[R5.0-007](../requirements/requirements-v5.0.md#r5-0-007)、R5.0-012及[R4.3-030](../requirements/requirements-v4.3.md#r4-3-030)。沿完整Demo v2两业务切片、原始来源、公开draft CQ和36项冻结标准，不使用最小链替代Demo。

运行配置：新隔离run `demo-efficiency-20261105-start1`；首轮沿最近Demo的GLM-5.3-flash/high，后继采用仓库默认low作配置对照；role-team/v1，并发2。可选过程评价关闭，优先完整生产和最终独立验收。与此前开启过程评价的试验有配置差异，不能直接作单因素降耗归因。

本轮唯一15 CNY账本及详细阶段约定见[运行输入](../../workspaces/v5-runs/demo-efficiency-20261105-inputs/stage.md)。生产、独立验收、失败和修复沿同预算累计，外部Host单列。旧run及原预算不恢复。

完成标准：实际应用及治理读回自查，独立36项验收，完整闭环墙钟不超过30分钟。生产、验收、技术修复、等待时间分列。一次通过不证明L2稳定性，未执行独立验收前不宣称质量通过。

验证范围：初始文档本地链接、凭据模式检查及git diff格式检查通过；未改应用代码，无需服务重启。运行进展及最终用量待补。

## 首轮结果与窄修复

首轮high从14:03:59 UTC开始，超过30分钟仍未应用，效率目标REVISE，L1未执行。14:37左右请求自然边界暂停，后已停稳，保留候选与失败原件。未以空模型判断语义质量。

`demo-efficiency-20261105-low-start2`沿同task_ref、同15元账本及相同完整来源/36题标准创建独立模型范围。改变effort，不能称为同配置工程净降耗。首份候选约8分钟交付，完整结果待验收。

真实失败：CQ将published handoff引用作为最终artifact_ref，得到role_artifact_reuse_forbidden；原反馈优先描述submit_role_artifact，但CQ没有该工具。最小改变仅按实际工具能力返回可执行反馈，并在权威CQ提示中明确首次完整正文、引用复用及消息ID/材料ID区别。没有放宽来源、身份、实际消费或候选接纳校验。已向原CQ投递署名technical-host指导，不把现场指导当作新冻结包自动采用。

开发验证：新增真实WorkUnitFlow/PostgreSQL回归先复现失败；修后test_output_contracts.py与test_role_team_flow.py共18 passed、1既有warning（96.94秒），Ruff检查/格式和git diff --check通过。仅修改modeling_team，无应用服务重启。GitNexus未找到当前model符号，detect_changes返回0符号；按直接调用点及差异/测试核对，不宣称图谱覆盖。

诊断证据：并行CQ可在provisional scope启动，范围安装后按新basis重评；本轮确有新增问题/未知，不能全部判为无效重复。业务消息在最终信封接纳前也能触发其他角色重评。保留现有协作语义，不为本次效率目标引入事务消息或新编排框架。

## 15:29 UTC 阶段更新

- high已停稳，托管已知输入4,124,560、输出222,009（合计4,346,569，缓存含在输入，推理含在输出），无原生用量缺项；模型未应用，快照与失败保留。cleanup撤销全部临时钥匙并删除空scope，不能称可直接resume其已删除scope。
- low同样超过半小时，阶段效率REVISE，L0/L1尚未闭环。已完成来源、公开CQ、候选整合尝试；apply均返回not_written。失败从选择字段、候选正文语法到材料消费信封分层记录，未当作模型质量结论。
- 正在完成现有submit_role_artifact的静态请求预检，以及复用既有编译合同的候选value/semantic_definition工具指导。不执行新dry-run或平台调用，不放宽应用门；既有direct compiler 38项、受影响v5 34项及新增4项通过，完整v5回归进行中。
- 回归暴露新增pure compiler导入缺少sandbox挂载，low Modeler00019已native_turn_failed且无在途。归因为本次工程修改的runtime/infrastructure缺口，待补齐明确文件并通过真实MCP加载后同run恢复；不能把此失败判为模型质量问题，也不能把普通单元通过当隔离通过。
- 当前累计计价约2.82240544 CNY，余额约12.17759456 CNY。外部Host token unknown且不计任务金额。技术指导首次错误署名technical-host被原合同当业务答复纳入basis，原件保留；后继已使用约定host-technical，不改写历史。

## 工程修复验证（15:43 UTC）

静态请求预检复用direct_modeling原校验，允许v5候选待Host填candidate_ref；原compile默认严格要求不变。submit_role_artifact可在同一回合返回model_changes_invalid。工具指导复用现有fields/semantic_definition合同，宽松最终decoder仍保留聚合反馈。仅显式挂载pure compiler及两个必需合同JSON，不暴露整仓库或隐藏材料。

- 初始全v5回归：450 passed、2 failed、1既有warning，978.40秒；两个失败均为新增导入缺失造成的真实隔离加载失败，原件full-v5-regression.log保留。
- 补齐挂载后，原参数化test_candidate_validator_is_available_in_real_isolated_tool_process[False/True]均PASS，2 passed/4.71秒，见运行目录isolated-validator-final.log。
- test_codex_agent.py：5 passed/4.91秒。新增静态预检/指导测试4 passed，既有direct compiler测试38 passed，相关输出/团队回归见同轮执行证据。没有把450+2拼称一次全套PASS；受影响原失败已复测。
- Modeler新回合已实际启动，错误从数百项字段问题收敛至8处引用并完成新交付，Coordinator整合中；未取得应用/独立验收成功证据。原失败、修复与等待均计入本任务墙钟。

授权收到时间采用宿主分钟级估计；精确效率计时使用原生semantic start记录，不拿prepare或新线程时间重置旧失败。

## 2026-11-06 接续（16:22 UTC／00:22 Asia/Singapore）

low原子apply实际completed，无错误，revision1／55项绑定。CQ治理复核及原属主unit check完成；第一次整体自查曾ready，但后续全范围实际核对发现回放条件、凭证状态影响、调用步骤、额度边界、接口响应字段等语义缺口，生产ready不能作为最终接受。原Modeler已在原run开始实际修模，按建模轮次另记一次；此前格式/参数/材料消费纠错不重复计轮，semantic-start原生记录数不代替业务轮次。

应用后的no_change交付还曾缺贡献artifact，已沿原责任补齐最小无写入贡献并在权威Modeler提示明确，实际运行已接纳，不重放旧create。新引用需整体重新接纳，旧创建贡献不代替新no_change。当前无独立L1结论，效率REVISE；累计托管计价约5.04017612 CNY，剩余约9.95982388 CNY。修模、自查与独立评价继续沿同15元预算，不启动新账本。

## 16:52 UTC 更新

原Modeler在原scope采用fields-only更新：先6个update/0 create补充真实语义缺口，再1个update/0 create补充其治理检查指出的遗漏未知项；实际应用完成，未重放旧创建。原属主检查两次明确给出revise但返回Markdown清单而非JSON，原件保留。已在unit_checks动态提示及权威modeler-self-check明确单个JSON信封、格式重试保留判断/证据；20项unit check回归通过（51.28秒），实际后继检查已将revise交回原Modeler并取得上述1项更新。原检查与修模不是独立L1验收。

Coordinator首次仅重开单元未传具体7项发现，Modeler错误返回no_change；后继具体工作请求促成6项更新。权威Coordinator提示补充发送精确来源/实际表达/自查引用并核对后继贡献，不把单纯reopen视为交接完成。当前仍为原任务生产闭环，累计托管估算6.26715600 CNY，剩余8.73284400 CNY。

预算中内部辅助调用尚有unwired_auxiliary=unknown，外部Host token同为unknown且排除任务金额；不能将托管账本估算或缓存率当作完整全任务成本或净降耗证据。

## 17:52 UTC 更新

修复后冷启动demo-efficiency-20261106-low-start3于2026-11-05T16:58:59.624259Z实际开始，原完整材料、low、36题及同15元预算。实际scope-plan已采用Modeler正式提案依赖cq-public，CQ无反向依赖；但先遇CQ Q8/Q9同时列入复用/修订、changes.schema_version错误、Coordinator shared_refs漏填及正文编译错误，超过30分钟仍未完成应用，效率REVISE。没有用缩小范围或旧模型替代冷启动。

CQ分类拒绝现补充重复/缺失/多余的确切ID反馈，保留原唯一身份与完整分类校验；真实失败包确定重复仅Q8/Q9，定向验证仍拒绝原错误，既有角色流程2 passed/58.86秒。

本轮工具指导还发现工程回归：将底层operation字段并集用作封闭candidate.value白名单遗漏合法relation.value.predicate。已改成开放的生成指导、显式predicate与各类型关键字段/端点说明，保留实际候选/编译校验。新增合法property谓词+关系的同一正例通过真实compile_model_changes和guidance JSON Schema，5项通过；扩展角色测试113 passed/464.88秒。不能将该指导缺陷归为模型质量问题。

旧run收口并非预算/锁故障：Coordinator收到proposal_ready的no_change结果，却将“尚未纳入current contribution_refs”误判为Modeler仍pending，并因无新队列消息等待。保留精确贡献与材料消费门，通过技术工作提示解锁；权威Coordinator提示补充生命周期active与工作ready、待整合与未完成的区别，不新增平台硬门。

运行控制已交单一trial_runtime_owner，父Host仅做只读核对和工程修复；其独占两个在途run的CLI控制，继续沿原授权到真实handoff与原生独立评价。当前L1尚未执行，已知托管估算约8.35/15 CNY；Host与未接线辅助用量边界保持。
