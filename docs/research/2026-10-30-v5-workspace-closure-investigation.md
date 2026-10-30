# v5 默认工作空间闭合缺口调查

日期：2026-10-30。起点提交：`572bd7b`。范围：R5.0-002 F2／F3／F5／F6、R5.0-003 F6 与后续计划 T01；当前代码和真实运行分别验证，不修改历史失败。

## 已复现的问题

前轮 `local-rework-20261030-start1` 的实际模型修复至 revision 3，独立模型／局部修模检查 4/4，但最终工作空间存在：正文说 B 已正确表达、无需修改，`expression` 仍为 `partial`；旧错误／待修覆盖仍作为当前适用记录；根级覆盖仍绑定旧模型版本。来源为 `workspaces/v5-runs/local-rework-20261030-inputs/workspace-final-summary.log` 及原记录导出。该问题属于工作空间方法采用缺口，不能从模型 4/4 推出记录已闭合。

## 当前实现的具体缺口

1. `search_semantic_records` 的导航结果只给 ID、版本、正文预览和 freshness，不给原始 states／model_basis。当前／历史适用性和正文／状态不一致难以在有界导航中直接识别。
2. `get_modeling_context` 给当前单元的 task 记录及项目 summary 导航，没有当前单元在 project 范围的记录导航。
3. 根级自查及原单元 `check-unit` 提示未直接附上已有工作空间导航。方法虽要求重读、更新相同 ID，真实 GLM 仍可能新建完成笔记并留下旧记录。只增加一般性的“记得更新”指导，前轮已证明不足。

4. 前轮实际记录还存在 author 与 unit_id 不一致：B 署名的故障覆盖被标为 root，A 的自查覆盖被标为概念 ID。按 unit_id 精确查找会漏掉自己的署名记录。导航需同时考虑记录分配与作者归属，普通精确搜索不能悄悄改变含义。

来源：`modeling_team/v5/src/ontoweave_modeling/semantic_workspace.py` 的 search/context，`flow.py` 的 _self_check，`unit_checks.py`。GitNexus 尚未索引这些 v5 符号，impact 为 UNKNOWN；以具体调用点、差异和相关回归核对影响，不宣称图谱覆盖。

## 本轮最小修正

导航附上已有 states、model_basis，加入当前单元在同一获准项目的有界 project 记录；根级和局部自查拿到相同导航。实际 Host snapshot 更新可观察模型版本，freshness 仍按已有机制给出版本候选，由 GLM 按原材料与实际读取判断是否刷新、保留缺口或明确取代旧记录。

不自动填 complete，不推断业务依赖，不新增语义完成硬拒绝。本单元导航包含分配记录及署名记录，后续页可通过现有搜索工具的 include_authored=true 保持同一过滤条件；普通搜索默认不变。每页仍有原来的上限和 next_offset；不加载全项目记录正文或完整聊天。已知未表达与真实未知继续区分。程序只让现有证据容易找到，语义闭合结果必须由真实采用及独立评价证明。

## 验证安排与边界

- 导航和两种自查提示的相关开发检查已开展；原始缺失字段用例先失败。程序不得因提供导航而自动改变原 states。
- 新任务 `v5-workspace-closure-20261030`，稳定 3 元账本，`glm-direct/glm-5.3-flash/low`。复用前轮两个 Class 的获准公开工程材料，在首次建模前冻结六项标准；不给生产者具体旧记录 ID，也不由 Host 手改状态。
- 首次建模、自查、显式受控 B 错误、原单元发现与修订、最终记录和真实模型分别保留。评价者仅拿冻结来源、阶段产物和只读治理能力，不创建或修复生产。
- 具体运行、独立报告、成本、失败层和是否仍有缺口，继续追加到[统一验证记录](../delivery/test-docs/2026-10-30-v5-follow-up-validation.md)。该有界工程场景不是完整业务盲测、任意递归规模或净降耗证明。

## 依据

- [v5 权威需求](../requirements/requirements-v5.0.md#r5-0-002)
- [后续计划与 T01](../delivery/implementation-plans/2026-10-30-v5-next-tasks.md#t01稳定维护状态材料覆盖与命题去向)
- [方法设计](../delivery/designs/2026-10-26-ontoweave-modeling-methodology-design.md)
- [高影响风险复核](2026-10-30-v5-high-impact-risk-assessment.md)


## 本轮结果

新任务原始六项标准由独立只读 GLM 得到 **6/6 PASS**，目标模型 revision 3；当前 A／B／根级记录沿稳定身份更新，旧修模项明确取代，未由 Host 逐条闭合。最终完整开发回归 **199 passed**。期间一次上游流断开，窄修错误层丢失；计量缺失通过既有 Host 暂估／恢复 API 接续，同一 3 元账本估算 **0.51603408**，含 **0.182942** 暂估，不当作最终账单。

详见[逐轮记录 D5](../delivery/test-docs/2026-10-30-v5-follow-up-validation.md)。本次实际相关记录均为 task 范围，project_local 的归属与导航由开发用例验证；父级自主选择、真实共享项目记录及跨 run 记忆、低频例外／未分配父级范围、完整业务语义及净降耗仍未覆盖。该结果解除当前两 Class 场景中已复现的默认收口缺口，不宣称任意业务都能自动完整维护。
