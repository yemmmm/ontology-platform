# v5 当前状态核对

日期：2026-10-30。范围：读取当前需求、提交、交付记录及本地原始证据；不启动、恢复或修改建模运行。
本报告保留初始盘点快照；后续实施、真实 GLM 验证与保留缺口见[逐轮推进记录](../delivery/test-docs/2026-10-30-v5-follow-up-validation.md)，不能用本快照替代最新交付状态。

## 结论

当前 HEAD 为 `c9f7171`（2026-10-30 02:06:37 +08:00，Complete v5 workspace workflows and default entry）。
选定的 v5 核心路径已功能收口，新任务默认入口已切换到 `scripts/modeling`，采用 LangGraph＋Codex harness；旧任务沿原版本及 `--legacy` 接续。
当前开放范围为已验证的 GLM／显式 Task 路径。工程功能闭环不等于完整业务语义验收、全规模验证或净降耗证明。

## 推进位置

| 阶段 | 当前结果 | 证据边界 |
| --- | --- | --- |
| P0 执行底座 | 已具备真实模型／工具、隔离、自然回合控制、持久接续及应用对账证据 | 提供商结算和完整计量仍 PARTIAL |
| P1 最小完整链 | 工作空间、项目记忆、直接 HITL、实际应用、治理自查及独立交接已接入 | 已验证公开小场景，不能泛化全业务质量 |
| P2 递归协作 | 动态工作树、依赖、独立等待、成员通信及父级整合已实现并真实运行 | 4×30 分页／重建为机械规模；跨单元数值合计未专门语义评价 |
| P3 增量与总览 | 来源版本、局部重入、成果复用、实际模型版本总览及按需刷新已接入 | 大项目效果、刷新粒度及摘要消费收益待评价 |
| P4 接续与入口 | 保存时数据分叉、新上下文接续、同标准重复运行和默认入口切换已发生 | 旧会话及旧 PASS 不热迁；无同条件旧栈成本对照 |

## 本次直接核对的证据

- `scripts/modeling` 默认调用 `ontoweave_modeling`，`--legacy` 显式调用旧 `modeling_team`。
- 最终回归日志实际记录 **173 passed、1 warning、232.21 秒**。收口记录另载最后更新身份断言 **1 passed**；本次没有重跑测试。
- 动态树和冷启动两个独立报告均 PASS，各 3 题、沿同一公开冻结标准；父级模型／记忆／总览报告 PASS、6 题；双本体报告 PASS、2 题。
- 七个收口运行的 `host/cleanup.json` 均有 `aggregate_keys_non_active=true`、`no_in_flight_attempts=true`；本机进程列表未发现 v5 start／resume 或模块执行进程。工程模型保留。
- 用量汇总实际记录 7 个运行、6 个 task_ref、120 个原生线程，已知输入 9,449,819、输出 312,604，合计 9,762,423 token。状态 PARTIAL：外部 Host 用量未知并按规则排除任务金额，平台评分用量未完整归集，提供商账单未提供。

证据目录为 `workspaces/v5-runs/`，最终日志为 `continuous-20261029-inputs/full-tests-final-173.log`，用量为 `continuous-20261029-inputs/usage/summary.json`。
七个运行目录为 `continuous-20261029-start1`、`dynamic-tree-20261029-start1`、`cold-repeat-20261030-start1`、`project-memory-20261030-first`、`project-memory-20261030-second`、`snapshot-fork-20261030-start1`、`multi-ontology-20261030-start1`。

## 剩余重点

1. 用更具代表性的业务材料验证方法采用、语义完整性、独立业务质量与重复性。
2. 减少格式纠正和累计上下文，分别评价模型直接消费、记忆保真及摘要辅助效果。
3. 取得同条件对照和完整费用依据后再判断净降耗；当前不报告节省比例。
4. R5.0-008 增强记忆研究、R5.0-009 Auto Ontology／Schema 输入方法专项仍待深化；基础接线不等于专项完成。

本轮因核心功能收口停止，没有观察到 GLM 429／五小时额度耗尽作为停止原因。
需求和计划保留了早期“P1—P4 待实施”状态，应按文首 2026-10-30 最新说明及最终收口段解释，不能将历史状态当作当前进度。

## 来源与验证范围

- [v5 权威需求](../requirements/requirements-v5.0.md)：范围和最新状态。
- [改造计划](../delivery/implementation-plans/2026-10-28-v5-langgraph-codex-migration-plan.md)：P0—P4 阶段及证据边界。
- [持续推进记录](../delivery/records/2026-10-29-v5-autonomous-progression.md)：失败、修复、自主决定和真实运行过程。
- [核心功能收口](../delivery/records/2026-10-30-v5-core-closure.md)：功能矩阵、停止依据和未验证范围。
- [Host runbook](../../skills/modeling-dev-loop/references/v5-runbook.md)、[v5 README](../../modeling_team/v5/README.md)：实际入口和操作合同。

本次没有改动运行代码、重启服务或产生模型调用。复用了未变代码的现存证据；本次检查不新增独立业务语义验收结论。
