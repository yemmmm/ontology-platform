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
