# v5 当前建模流程与设计一致性核对

日期：2026-10-30。代码基线：`c9f7171`。核对方式：当前源码、权威需求、方法设计及现存真实运行工具事件；没有运行新模型、修改运行状态或新增独立验收。
本报告保留初始盘点快照；后续实施、真实 GLM 验证与保留缺口见[逐轮推进记录](../delivery/test-docs/2026-10-30-v5-follow-up-validation.md)，不能用本快照替代最新交付状态。

## 结论

执行主干与设计方向一致，已形成可运行的工程闭环；**完整方法一致性仍为 PARTIAL**。
“核心功能收口”不能解释成 S0—S9 所有方法要求、所有业务语义和规模情境均已完成验证。

已一致的主要边界包括：程序调度而无常驻 Delivery LLM、Agent 负责语义、直接 HITL、原生回合边界控制、Host 确定性应用、真实治理读回、原身份对账及独立只读评价。
主要差异是子级完整循环被收敛为提案、父级等待全部直接子级、工作空间正交状态及命题去向尚未稳定采用。跨单元数值组合等仍是语义证据缺口。

## 1. 当前实际流程

1. **准备与冻结（S0）**：`scripts/modeling` 默认进入 v5。Host 提供 Task、原材料包、模型 Profile、授权和独立冻结题集引用；prepare 固定材料摘要、方法提示和技术表示合同。原生生产上下文不获得隐藏题包。
2. **准备真实基线**：根单元 `prepare_scope` 创建或绑定获准资源，子单元读取 snapshot；工作状态和 checkpoint 保存引用。
3. **生产 Agent 分析（S1—S5）**：在同一类 `model` 回合中进行拆分、材料审阅、命题捕获、解释、身份对齐、候选组装及共享整合；程序不为每个活动新增固定审批或调用。
4. **按需协作与等待**：启用工作管理时 Agent 可动态委派多层子单元；各单元有自己的执行／checkpoint。子级返回固定版本提案，由直接父级整合。普通成员通信、任务卡和项目／任务记忆按 Task 能力开关提供。
5. **直接人工介入（Q）**：Agent 返回带原因和影响的问题；原生回合结束后保存问题并进入 LangGraph 持久等待。CLI reply/input 登记答复或主动补充；原运行接续时按单元、请求和版本消费。部分答复不自动关闭整题，无关兄弟可继续分析。
6. **根单元应用（S6）**：根级候选 proposed 后，程序核对当前模型基线，经 Host 编译、绑定并应用。失败或基线变化反馈给 model；结果未知先保留原 operation 身份对账，不换身份盲重放。
7. **根级真实自查（S7）**：应用成功或 no_change 进入独立生产自查回合，实际查询治理接口；revise 回 model，waiting_input 进 Q，ready 形成 handoff_ready。handoff 中 semantic_acceptance 仍是 unverified。
8. **Host 单独发起独立评价（S8）**：evaluate 使用独立材料包、只读配置和全新原生上下文；验证冻结题、材料、实际模型版本及读取。支持子范围／追加范围和待验记忆／摘要，但不允许其替代实际模型缺失的事实。评价不是生产图自动继续的节点。
9. **显式变化重入（S9）**：Host 用 source-revise 提交完整新材料包及影响候选；在停稳边界激活，受影响单元和祖先回到 model，保留未变成果。外部模型版本变化会在应用前／实际读取时暴露。当前没有自动监视所有外部来源的后台服务。
10. **持续记录与总览（C1／C2）**：Agent 按需维护语义记录和生产摘要；消费者／用户总览通过 overview-refresh 的新只读上下文从实际模型生成。overview-show 核对当前模型版本和访问，旧结果可标 needs_review；并非每次工具调用自动重生成总览。

实际 LangGraph 节点为 `prepare → model ↔ collaborate → apply → self_check → handoff`，另有 `wait_input`，自查可回 model。S0—S9 是方法活动而非必须同名的图节点，这种合并本身符合方法设计 §17。

## 2. 对照结果

| 项目 | 结论 | 依据及边界 |
| --- | --- | --- |
| Agent／程序职责与无常驻 Delivery | 一致 | 语义解释归 Agent，路由／应用／对账归程序；无需 Delivery 转交人工问答。 |
| Q、自然暂停及原身份接续 | 已接通，按原证据范围成立 | 工作流等待与原生 interrupt 分离；单元输入、应用回执和控制身份分别保存。 |
| S6、S7、S8 的权威分离 | 一致 | 工作笔记不能写 application／acceptance 状态；实际应用、治理读回、独立报告各有来源。 |
| S1—S5 自由合并与递归拆分 | 机制一致，实际采用未全证实 | 工具允许动态树与原文下钻；不是程序逐步语义裁判。 |
| 子单元 S1—S7 完整局部循环 | 与原方法存在收敛差异 | 子级只能提出候选，不能进入实际 apply／写后 self_check；写入和完整写后自查集中在根级。 |
| 只等待受影响部分、安全部分先应用 | 当前比设计更严格 | 父级自动依赖全部直接子级，且存在全部直接子级未 ready 时 proposed 转 waiting_children 的门。 |
| 正交状态、材料覆盖、命题去向 | 工具存在，采用仍 PARTIAL | 真实记录以正文为主，states 未稳定填写；没有证据证明每项命题均有明确交付去向。 |
| S9 与 C2 变化维护 | 已有最小路径，非全面自动维护 | 依赖显式输入、来源／模型版本和已登记依赖；未登记依赖不可能由该机制自动识别。 |
| 跨单元数值组合、临界规则、大规模语义 | 未充分验证 | 收口记录明确数值合计未专项评价、4×30 仅机械规模；公开小题不能覆盖 A1—A23。 |

## 3. 具体差异与证据

### D1：子级只产提案，完整应用／自查集中根级

原方法 §5.3 明确子级内部运行 S1—S7，返回实际模型引用、应用及验证范围；§17 递归使用相同流程。
当前 `flow.py:386` 在子级 proposed/no_change 时直接保存 proposal_ready 并返回，绕过 apply 和 self_check；`execution.py:291` 明示 Only the root applies，子级提示也写明 changes 可为空。

这是[多单元交付记录](../delivery/records/2026-10-29-v5-multi-unit-delivery.md)已明确记录的最小实现选择，不是本次新发现的未知写入风险；但该记录没有证明它在大业务下等价满足原方法的局部闭环与有界父级责任。子级可主动读模型，但程序不要求、也不组织逐子级的写后自查。独立子范围评价可由 Host 另行发起，不等于生产子级已有完整闭环。

### D2：父级自动等待全部直接子级

方法 §17.7 明确“不要求整个项目全部完成”“只等待受影响变更，其他安全工作继续”。
当前 `multi_unit.py:109` 把所有 direct_units 加入父级依赖，只有各自当前代次 proposal_ready 才调度父级；`flow.py:333` 另把存在未完成直接子级的 proposed 改成 waiting_children。

因此，A 已完成、B 等人工输入时，A 可保留提案，其他兄弟可继续工作，但根级通常不能先应用 A 的安全独立变更。这是分析并行已经具备、分组应用仍有整层汇合的差别。声明某项真实业务依赖当然可以排序；问题在于代码默认将全部直接子级都作为依赖。

### D3：工作空间存在，但正交状态和完整去向没有稳定落到实际记录

R5.0-002 F3 要求区分材料审阅、认知、表达、应用、工作、验收与适用性；R5.0-003 F2 及方法 §11.2 要求每项有业务意义命题的可追踪去向。
工具提供 `kind`、`body`、`source_refs`、`depends_on`、`states`。`semantic_workspace.py:70` 接受空 states，默认只保存 applicability=current；这是允许 Agent 合理省略的存储行为，本身不能证明语义缺漏或建议新增硬拒绝。

本次扫描真实 `executions/*/agent/events.jsonl` 中生产／自查的 write_semantic_record 回执，排除 evaluation／overview，只统计明确 status=recorded 的成功回执：

| run | 成功记录回执数 | 未传 states | 未传 depends_on |
| --- | ---: | ---: | ---: |
| project-memory-20261030-first | 9 | 9 | 6 |
| snapshot-fork-20261030-start1 | 12 | 12 | 10 |
| multi-ontology-20261030-start1 | 12 | 12 | 10 |

共 33 次成功写入均未传 states；这是调用／版本回执计数，不是 33 个不同对象。正文保留了部分“已审阅／未应用／未知”等信息，不能断言完全没有状态记录；但结构化正交状态实际只见默认适用性，不能据此宣称完整状态维护已采用。缺少 depends_on 并非每条都错误，例如原始命题可直接依赖来源；只有已登记的记录依赖才会触发精确依赖刷新。

较早动态树运行绑定 semantic_workspace=false；冷启动绑定为 true，其写入调用仅 proposition、summary 两类。不能把所有运行拼接成一次完整方法采用验收。最新双本体运行有 material_review/proposition/coverage/summary，仍没有稳定的完整命题去向与独立正交状态证据。

程序的 source_read_missing 只核对提案引用材料是否在本回合实际读取、摘要是否一致；实际 read_material 返回字符范围和分页。它不能证明所有范围均读完或命题捕获没有遗漏。该语义结论仍应由 Agent 记录和独立材料覆盖核对承担，不应通过新增平台语义硬门替代。

### D4：配置启用、Host 驱动与尚未验证的范围

- semantic_workspace/shared_memory/work_management 由 Task 显式启用，包装入口不会自动全部开启；runbook 建议新任务启用。默认 v5 入口不意味着任意合法 Task 自动具有完整工作空间方法。
- 来源变化、总览刷新、独立评价和停止后接续当前为显式 Host／CLI 操作，符合首版结构化入口边界，不是全自动常驻业务服务。
- 应用格式失败目前返回 model 回合并附原候选和执行反馈，未单独提供轻量 S6 格式修正路径；能恢复，但是否产生不必要的重新推理仍需量化。
- A19 数值跨单元合计、A20 全量命题去向、A21 大量单元共同澄清的适用范围，以及 A22 数值／时间边界，不因公开动态树 3/3 或父级 6/6 自动完成。当前收口记录已明确部分边界，不应再扩大 PASS。

## 4. 建议的最小后续

1. 优先检查并改善 Agent 对材料审阅、命题去向和独立状态的实际维护，用已有记录工具及独立评价验证；不新增逐步骤审批或语义硬拒绝。
2. 明确子级提案／根级写入是当前实施边界；若继续沿此路径，验证父级有界责任和子范围实际读回，避免将原方法子级完整闭环标为已全实现。
3. 用明确安全的局部变更场景判断是否需要解除“全部直接子级”汇合，仍保留真实依赖、授权和原子应用；无需先扩成多写者架构。
4. 复用已有范围及方法 A19—A22 做代表性语义核对，区分工程机制、实际采用及业务结论；当前没有据本次检查启动新建模或增加运行授权。

## 5. 来源与检查限制

- [v5 需求](../requirements/requirements-v5.0.md)：R5.0-001—007，重点 002 F3、003 F1—F6、004、006。
- [方法设计](../delivery/designs/2026-10-26-ontoweave-modeling-methodology-design.md)：§5.3、§11、§17、A1—A23。
- [架构设计](../delivery/designs/2026-10-28-v5-p1-1-architecture-design.md)、[实施计划](../delivery/implementation-plans/2026-10-28-v5-langgraph-codex-migration-plan.md)：阶段与模块边界。
- [最终收口](../delivery/records/2026-10-30-v5-core-closure.md)、[持续运行记录](../delivery/records/2026-10-29-v5-autonomous-progression.md)：已声明证据及限制。
- [生产提示](../../modeling_team/v5/instructions/modeling.md)、[流程](../../modeling_team/v5/src/ontoweave_modeling/flow.py)、[调度](../../modeling_team/v5/src/ontoweave_modeling/multi_unit.py)、[CLI](../../modeling_team/v5/src/ontoweave_modeling/cli.py)、[语义工作空间](../../modeling_team/v5/src/ontoweave_modeling/semantic_workspace.py)、[执行工具接线](../../modeling_team/v5/src/ontoweave_modeling/execution.py)、[变化](../../modeling_team/v5/src/ontoweave_modeling/revisions.py)、[总览](../../modeling_team/v5/src/ontoweave_modeling/overviews.py)。

GitNexus 查询未返回当前 v5 调度／工作空间符号，结果主要落在旧平台模块；本次依据直接源码和调用点，不宣称图覆盖。未生成或刷新仓库 wiki。没有重跑后端／前端／v5 测试；没有改运行代码、重启服务、修复或恢复任何被验收 run。本文件是技术核对，不是新的独立业务语义验收或完整设计审阅 PASS。
