# v5 对 v4 多 Agent 协同设计的集成核对

日期：2026-11-03。源码基线：`b3511cc`。结论：**v5 已承接并实现 v4 的主要协同责任，编排和职责载体做了重构；不是原样运行旧 TeamRunner，也没有证据宣布全部协同场景已全面验收。刚完成的 Demo 没有使用多建模子 Agent，不能把其 36/36 PASS 作为多 Agent 分工协作的证明。**

## 权威设计与当前实现

[R5.0-001/002/003 和相邻合同映射](../requirements/requirements-v5.0.md)明确承接 v4 场景地图、共享协调、应用读回、工作卡、事件和预算，同时明确替换 Delivery 的机械推进和用户转交职责。[R4.0-007](../requirements/requirements-v4.0.md)本身已区分视角、切片、Ontology、Agent，不要求一视角一 Agent；不应把 v4 描述为强制固定数量角色。

| v4 的协同责任 | v5 的承接方式 | 当前源码/合同 |
| --- | --- | --- |
| Coordinator 组织范围、共享定义和整体协调 | 根/父工作单元保留未分配范围，整合直接子级及本层约束；业务权威记录迁到语义工作空间，地图为派生视图 | `work_plan.py` 的 `delegate/reopen/tree`；`flow.py` 的父级整合和 `_review_children` |
| Agent 分工、依赖与局部等待 | 动态递归工作树；子级可继续委派，各有身份和 PostgreSQL checkpoint；按依赖推进，无关单元可并发，局部等待/重入保留兄弟成果 | `multi_unit.py:MultiUnitFlow.advance`，实际使用 ThreadPoolExecutor 和 unit_concurrency；`work_plan.py` |
| 成员对话、工作卡和成果交接 | TeamChannel 提供消息、署名请求、版本化材料和卡片；原生 turn 结束后处理队列；收到/读到/满足依赖不混同 | `team.py`；README 的通信合同 |
| 共享定义维护、冲突和影响重审 | semantic_record 的内容版本、depends_on、独立状态及显式未知；重开受影响单元和祖先；语义等价与影响由 Agent 判断，不由调度器自动裁决 | `semantic_workspace.py`、`work_plan.py`、`revisions.py` |
| 模型应用、实际读回和独立验收 | 复用 v4.3 已有确定性应用及治理读取；根级整合，Host 执行；独立冻结/只读验收继续隔离 | `flow.py`、`host/worker.py`、`acceptance.py`；R5.0-004/006 |
| Delivery 推进、观察与人工转交 | LangGraph/程序负责确定性路由、等待、恢复和预算；HITL 请求直接关联用户与原单元，不再强制常驻 Delivery LLM 中转 | R5.0-001 F6/F9、`human_input.py`、`control.py` |

上述不是只有工具文件：`cli.py` 在 work_management/work_units 任务中选择 MultiUnitFlow，执行指令在有用时允许 delegate_work；正式 README 提供工作树、通信和局部重入入口。工作树路径支持并发；兼容的 collaboration.peers 消息路径则按消息串行，不把“能发消息”当作所有协作均并发。

## 已有验证及边界

[多单元交付记录](../delivery/records/2026-10-29-v5-multi-unit-delivery.md)记录了局部 HITL 等待、兄弟单元继续、父级分批应用及读回的真实工程闭环。

[2026-10-30 验证记录 D7](../delivery/test-docs/2026-10-30-v5-follow-up-validation.md)另外记录三层责任、原单元实际检查返回 revise、原身份及祖先重入、未变兄弟复用，并在修复后的实际 revision 8 获有界独立 6/6 PASS。历史误归属、被拒的自报 PASS、Host 技术重入和提示补充均保留；这不是任意递归/规模、完整客户业务盲测、无干预冷启动 L2 或净降耗验收。

本次只读取上述历史记录，未重跑这些实验。源码存在/已接线、历史有界实测和全功能完成是三个不同结论；当前不能宣称 v4 所有协同细节逐项完整迁移及全部泛化场景通过。

## 刚完成 Demo 的实际采用

[本轮 Demo 记录](2026-11-03-demo-high-agent-evaluation.md)和本次只读查询的工作空间一致：

- `work_management=true`，允许按需委派，但最终工作树 `units={}`、`root_generation=0`。
- `unit_concurrency=1`，没有产生建模子工作单元。
- 3 个生产建模执行和 3 个自查执行属于同一个根工作单元的分阶段执行；另外有独立过程评价和最终验收上下文。
- 因而属于“单根建模＋独立评价/验收”。多个 LLM 上下文不等于多个建模子 Agent 分工协作；业务有两个切片也不自动要求两名 Agent。
- 36/36 PASS 支持该冻结 Demo 范围的独立模型语义结论，未覆盖本次真实多建模 Agent 的委派、共享定义协商或父子整合质量。

## 核对方式

阅读当前权威需求、README、CLI 路由及上述源码；只读 PostgreSQL 中本轮 work_plan 和冻结 binding，核对已有交付记录。GitNexus list_repos 显示索引落后当前 HEAD 598 个提交，协作符号查询未获得 v5 有效流程；因此使用当前源码/调用点核对，没有宣称图谱流程覆盖，也未为这一局部问题重建索引。本次没有模型调用、产品代码变更、服务重启或新独立验收，仅做文档链接与格式检查。
