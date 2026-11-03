# Demo high 建模与 Agent 评价测试

日期：2026-11-03。状态：**本轮完成，最终独立语义验收 PASS 36/36**。实际模型 revision 5，145 个资源、193 条关系；whole_model 读取覆盖 complete=true，未读材料、未读资源、不完整模型范围均为 0。该结论限于构造 Demo 的冻结范围，不代表客户业务盲测、真实供应商能力、SQL 执行、L2 重复性或净降耗证明。

## 授权、来源与执行范围

用户要求：“请启动一轮demo项目建模测试，模型选用glm-5.3-flash high，开启agent评价功能”。本轮沿 `scripts/modeling` 从新隔离 Project/Ontology 冷启动，所有 10 个实际托管原生执行的 provider 请求均核对为 `glm-direct / glm-5.3-flash / high`。独立默认预算 3 CNY，生产、自查、过程评价、最终验收共用；外部 Host 不扣预算。

业务为完整 Demo v2：模型目录/可用性、凭证授权/整数调用单位两个关联切片及必要语义数据/接口映射。获准来源为 `examples/llm-access-lab/business.md`、`competency-questions.json`，以及前轮冻结的原始 scope、OpenAPI、SQLite DDL。business 与 public-cq 摘要和当前文件一致，其余固定来源逐项 SHA256 校验通过。生产仅获得五份公开来源，不接收旧模型、旧候选、私有题、运行观察或评分。

正式验收复用生产前已冻结的 36 题及独立运行观察；标准未按本轮模型修改。独立验收使用另一个只读原生上下文，不创建/继续/修复生产，不读取过程评分。归属 R5.0-001/003/004/006 和可选过程评价 R5.0-011，见[当前需求](../requirements/requirements-v5.0.md)、[v5 Host runbook](../../skills/modeling-dev-loop/references/v5-runbook.md)。

代码基线 `4df16bfdc2367584335c7ca9459b233be4b35f4e`，本轮无源码或默认提示修改，不需后端/前端回归或服务重启。Run：`demo-high-eval-20261103T044154Z-start1`；输入及账本：`workspaces/v5-runs/demo-high-eval-20261103T044154Z-inputs/`。

## 实际生产与独立验收

本轮一次 semantic start、一次初建轮。初建预先安排的三批内容：概念/属性及行为规则流程接口图；类型级关系与 Class 端点连接；数据表/连接映射。应用共推进至 revision 5（首批分为三个原子 Batch）；生产有 3 个建模原生上下文、3 个应用后自查上下文。候选分批、实际模型 revision、框架内部 round 与用户实质修模轮分开计数，本轮没有交付后另开新的语义修模任务。

首批应用至 revision 3：133 资源、150 关系；生产自查保留已计划的关系/映射待办。第二批 revision 4：138 资源、169 关系，五种关系类型及九条 Class 端点边读回。最后 revision 5：145 资源、193 关系，四个表映射与三个连接映射应用后逐项自查。来源不足之处继续明确未知：状态 INTEGER 编码、时间格式/时区、凭证散列算法、响应结构、拒绝/回放和调价事件来源等，不以缺数据推导零值。九条公开问数题仍为 draft 能力目标，不把其标准当新业务事实。

全量生产自查期间一次 `query_semantic_context` 超时，Agent 使用已有精确模型读取继续核查，未修改平台或替换原执行。生产实际到达 `handoff_ready` 后才启动独立 36 题验收。最终[公开验收回执](../../workspaces/v5-runs/demo-high-eval-20261103T044154Z-start1/evaluations/final-full-36/public-feedback.json)为 PASS 36/36，完整来源与实际资源读取核对均通过；生产自查与独立验收分别保留。

## Agent 过程评价

三类均开启并实际完成，沿已提交生产记录精确版本由 Host 显式提交，绑定 `process-evaluation/v2`。观察不阻断生产，报告未回传生产，不构成自动修模或正式验收的替代。

| 阶段 | 四维得分 | 程序满意度 | 解释与限制 |
| --- | --- | --- | --- |
| CQ | 3 / 4 / 4 / 4 | gaps | 公开九题偏问数统计，未单独覆盖冲突、回放例外、零额度创建等运营规则；low 优先级题集覆盖提示，不证明实际模型缺失 |
| 范围/切片方案 | 4 / 4 / 4 / 4 | satisfied | 认可整体范围和分阶段责任；报告承认部分 OpenAPI 展示截断并借助生产材料摘要交叉核对，不能据此主张独立全文核实 |
| 实际整合 | 4 / 4 / 4 / 4 | unverified | 未报告已证实业务缺口，但约 110 个资源的单体正文未逐一展开；保留读取限制，不按高分改为满意或全量 PASS |

整合评价冻结 revision 5；部分生产记录仍为应用前时点，报告明确区分计划记录与实际治理正文。正式独立验收之后另外完成了 whole_model 读证，不回填或改写过程评价的未验证状态。

实际整合第一次准入失败：一份已结束 provider attempt 先于匹配的 native 用量被账本观察，触发 `metering_error`，并非资金耗尽或模型质量错误。后续真实用量使 coverage 恢复 complete、unknown=0、issues=[]。Host 通过既有 `continue_authorized(clear_reasons=[metering_error])` 的当前输入恢复校验，沿原 3 元授权、同一 run、同一冻结绑定重试；未补零、删除历史、增加额度或创建新 semantic start。失败执行未发生原生模型调用；成功重试、原暂停、恢复和原始事件均保留。没有修补或放宽计量守卫；首次阻塞属于平台计量合同/采集时序，局部恢复不证明所有并发时序已修复。

最终过程[JSON/Markdown 汇总](../../workspaces/v5-runs/demo-high-eval-20261103T044154Z-start1/process-evaluations/summary-0008.md)显示三个阶段均 observed；其 Formal acceptance 保留 separate，正式结果沿上方独立回执核对。三份有效评分不能证明评价改善生产质量或净降耗；本轮没有对照或评分反馈后的生产干预。

## 时间、token 与金额

准备记录起点 2026-11-03 04:41:54.144 UTC；首个真实 semantic start 04:42:05.477 UTC；最后原生回合结束 06:35:27.540 UTC，执行时间窗 **6802.063 秒（1小时53分22秒）**。资源清理完成 06:36:45.866 UTC，准备至资源收尾墙钟 **6891.722 秒（1小时54分52秒）**。新加坡时间分别为 12:41:54、12:42:05、14:35:27、14:36:45。

下表按每个不同 native thread 最后累计计数统计，不叠加累计样本；输入含缓存，不再加一次缓存数。失败准入无 native thread，不计为零用量模型执行。分类区间包含工具及提供商等待，并行区间不能相加当全任务墙钟或纯语义劳动。

| 用途 | 原生执行数 | 输入 token | 输出 token | 冻结价表估算 CNY | 原生区间并集秒 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 生产建模 | 3 | 3,654,066 | 188,887 | 1.36662776 | 3692.714 |
| 生产自查 | 3 | 5,033,328 | 69,534 | 0.84981408 | 1530.475 |
| Agent 过程评价 | 3 | 3,500,493 | 54,088 | 0.48356628 | 882.459 |
| 最终独立验收 | 1 | 3,529,547 | 55,152 | 0.454219 | 1416.718 |

输入合计 **15,717,434**（其中缓存 **14,320,256**），输出 **367,661**，输入加输出 **16,085,095 token**。10/10 托管原生用量已知，最终账本 unknown=0、provisional=0、pending_settlement=0、inflight=0。

最终估算 **3.15422712 CNY**，超出 3 CNY 的 **0.15422712 CNY** 为已准入验收原生回合的自然尾差；达到预算条件后关闭新活动准入，在途回合按合同自然结束，未追加预算或启动新的纠错/修模。使用原冻结价表 user-20261020，不是供应商最终账单。生产建模/自查成本合计 2.21644184 CNY；三类过程评价 0.48356628 CNY；正式验收 0.454219 CNY。

外部 Host、平台内部未接线辅助调用及纯有效劳动时间 unknown，Host 用量单列且不扣预算；全任务计量仍为 PARTIAL。不能用缓存比例或本轮与历史运行的 token 差异主张净降耗或模型能力排名。原生用量与分类时间原件见 `observed-usage-summary.json`，账本见 `budget-final.json`。

## 资源收尾与证据

Project `9fedb021-06df-4ee3-91e4-667dd3cf9a8a`，Ontology `169ae452-021f-48b6-8dc6-37d56d98442e`。含实际平台数据的 final-full-36-pass 快照 `274e842d72704456aa41ba902c062264` 已保存，41 个工作空间对象，model_read_error=null。stop effective、control.mode=stopped、active 为空；cleanup 确认 sessions_terminal、no_in_flight_attempts、aggregate_keys_non_active。清理路径同时逐个撤销 modeling/acceptance read key，再收口协议与临时管理员凭据，未撤销共享 GLM 凭据。实际模型 written-retained，旧模型与失败原件保留。

所有本轮原件位于前述 inputs/run：task.json、host-record.json、stage-*.json、submit-*.json、process-*.log、metering-before-recovery.json、metering-recovery.json、evaluate-final-full-36.log、observed-usage-summary.json、final-category-costs.json、snapshot-final.json、stop-final.json、cleanup-final.json、status-final.json、budget-final.json。私有题和具体评分理由不提交到版本库。
