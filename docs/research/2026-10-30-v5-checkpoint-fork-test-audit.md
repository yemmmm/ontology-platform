# v5 检查点恢复与 fork 测试核查

日期：2026-10-30；当前代码基线 `397c41d`。本次是已有证据与当前实现核查，没有重新启动 GLM、恢复 run、执行 fork、修改运行代码或重启服务。

## 结论

**做过自动测试，也做过真实平台／GLM 接续验证；但不能概括为当前版本任意检查点恢复和 fork 后所有增量写入均已通过。** 原 run 的持久接续、写后 checkpoint 缺口恢复、保存时平台数据 fork 和新上下文接续分别有证据。命名快照任意原地回滚不属于当前已实现路径，真正无终态执行及未知 fork 结果的完整对账接续仍有缺口。

## 已有测试与原件

| 能力 | 已核对证据 | 证明范围 |
| --- | --- | --- |
| 快照保存／读取／比较 | `test_snapshots.py`：冻结正文和版本不随后续写改变；保留 LangGraph checkpoint_id；忙碌保存；不依赖当前源文件的离线读取 | 观察快照，不等于平台数据备份或原地回滚 |
| 原 run 暂停后换进程接续 | [记忆／快照交付](../delivery/records/2026-10-29-v5-memory-snapshot-delivery.md)：decision-before-review 在 model revision 0／下一步 collaborate 保存；新 CLI 接续，没有重放 model-00000；最终只应用一次 | 正常持久接续；本次后继真实任务也多次在原 run 恢复 |
| 模型写成功、流程 checkpoint 保存前失败 | [原始证明](../../workspaces/v5-runs/project-memory-20261030-inputs/checkpoint-gap-reuse-proof.json)：actual_host_result completed，operation_id=apply-00001；正常 CLI 恢复后 handoff_ready，intent_count=1、receipt_count=1、model revision 3→4 | 该窄真实故障窗口下原操作复用，不重复成功写入；不是任意断电窗口保证 |
| 保存时数据 fork／新上下文接续 | [fork 回执](../../workspaces/v5-runs/project-memory-20261030-inputs/fork-create.json)、[pending 原件](../../workspaces/v5-runs/snapshot-fork-20261030-start1/fork-pending.json)：snapshot=a3dd920aed0f4a61b378219480c626a7，源 revision 3，目标 Project=c72e9fd7-9106-4608-8e33-c2544fac96a6，单 Ontology=a8919dc8-8385-5778-8d68-5c4e8afb9be4；导入 7 条认知／记忆记录，源归档，临时管理员密钥撤销 | 真实 SQL／RDF 平台分叉，非只复制快照 JSON；新原生上下文读取复核后 no_change |
| 分叉后独立验证 | [原报告](../../workspaces/v5-runs/snapshot-fork-20261030-start1/evaluations/fork-business-continuation/private-report.json)、[公开结果](../../workspaces/v5-runs/project-memory-20261030-inputs/evaluate-fork.log)：目标 revision 3，模型含义／编号条件／记忆保真公开三题 3/3 PASS | 有界工程参考；不能当任意业务、所有故障或旧 PASS 自动继承的证明 |
| fork 重复／未知结果保护 | `test_snapshot_fork.py` 两用例：显式 archive-source；同请求只 fork 一次；保留 task_ref／预算，隔离 workspace／控制；导入记录 needs_review；不导入 execution／handoff；未知响应保留预分配目标，第二次调用不再 fork | 数据复制平台为模拟，数据库仓储为实际 PostgreSQL；没有真实未知 COMMIT 后完整恢复到完成的证据 |

相关测试包含在已保存的最新 v5 完整回归 **214 passed、1 条既有 warning** 中，日志为 `local-owner-closure-20261030-inputs/regression-final-with-evidence-provenance.log`。其后修改仅为独立评价的 human-inputs 来源列表，相关模块 17 passed；snapshot／fork 逻辑未改。本次不重复运行已有测试。

## “恢复”须区分的三条路径

1. `resume`：接续原 run 的持久业务记录和 LangGraph 流程，并复用已确认结果／原操作。
2. `snapshot-show/diff`：读／比较命名观察快照；当前 CLI 没有“选任意命名快照并把原项目整体原地回滚”的入口。
3. `snapshot-fork --archive-source`：需要 include-platform 快照，从保存时数据创建新项目／本体和新原生上下文。复用的现有平台合同会归档整个源项目的 Ontology；不是无副作用的实验克隆。执行／在途控制／旧验收不复制为新目标的通过结论。

依据：[R5.0-001 F10／004／007](../requirements/requirements-v5.0.md)、[fork 复用边界](2026-10-30-v5-snapshot-fork-reuse.md)、[持续推进中的真实恢复／分叉记录](../delivery/records/2026-10-29-v5-autonomous-progression.md)。

## 当前版本新增的覆盖风险：fork 后复用已有资源写入

真实 fork／后继增量更新的证据早于 `38ef611` 的原生身份适配修正。最新全回归的 fork 平台替身不能替代该修正后真实 fork→复用既有类→创建关系的复验。

当前源码组合暴露明确的集成风险：

- [snapshot_fork.py](../../modeling_team/v5/src/ontoweave_modeling/snapshot_fork.py)导入语义／记忆记录，不将 fork 回执的 identity_mapping 装配为新 run 的 `applied-bindings.json`。
- [worker.py read_binding](../../modeling_team/v5/host/worker.py)对真实 governed id=IRI 投影，只有当前 run 的 applied-bindings 才补原生 resource_id；不会从 IRI 猜 UUID。
- 已有 `test_governed_iri_is_not_used_as_native_relation_endpoint(with_receipt=False)` 明确证明无该绑定时 resource_id=None，复用类作为关系端点的编译返回 `binding_identity_missing`。

因此，**当前最新版本 fork 后复用已有资源的增量写入不能标 PASS**。以上为当前静态组合与既有合同用例指向的风险，本次没有新开真实 fork 复现，也不把它夸大为数据复制或只读接续已经失败。下一步须沿同一真实授权／预算，用最小 fork 后关系写入验证确切 ID 映射，必要时最窄补齐映射交接；不能让 Agent 猜 ID 或重复建类绕过。

此外，[后续清单 T03.1](../delivery/implementation-plans/2026-10-30-v5-next-tasks.md)仍保留“原生已启动但没有 result／turn-completed”的完整对账恢复待验。安全不盲重启已有用例，完整恢复到完成不能由此推导。
