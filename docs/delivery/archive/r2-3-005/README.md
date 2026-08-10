# R2.3-005 交付归档

R2.3-005 已于 2026-08-10 由 Start75 完成，并经 Independent Round 29 验收 PASS。本目录保存已被最终方案
取代、但仍具审计和复盘价值的历史计划与交接材料。不要把归档文件当作当前运行指令。

## 快速接手

- [成功建模流程与接手手册（HTML）](r2-3-005-successful-modeling-handover.html)
- 权威需求：[`docs/requirements/requirements-v2.3.md`](../../../requirements/requirements-v2.3.md)
- 最终设计：[`docs/delivery/designs/2026-08-03-r2-3-005-modeling-team-runner-acceptance-design.md`](../../designs/2026-08-03-r2-3-005-modeling-team-runner-acceptance-design.md)
- 最终实施计划：[`docs/delivery/implementation-plans/2026-08-09-r2-3-005-provider-transition-and-closure.md`](../../implementation-plans/2026-08-09-r2-3-005-provider-transition-and-closure.md)
- 共享测试计划：[`docs/delivery/test-plans/2026-08-03-r2-3-005-modeling-team-runner-acceptance-test-plan.md`](../../test-plans/2026-08-03-r2-3-005-modeling-team-runner-acceptance-test-plan.md)
- 交付记录：[`docs/delivery/records/2026-08-03-r2-3-005-producer-runner-formalization-delivery-record.md`](../../records/2026-08-03-r2-3-005-producer-runner-formalization-delivery-record.md)

## 归档内容

- `historical-plans/`：已完成或被后续修订取代的阶段性修复方案。它们解释失败原因与设计演进，不是当前
  source of truth。
- `handoffs/`：已过期的会话交接快照；最终状态以交付记录和 Round 29 为准。

## 保留与删除决定

- 保留所有失败轮次、设计取舍和测试历史，因为它们构成审计链与可复用故障知识。
- 未删除产品代码、正式 Task/Profile、模型清单、测试或 retained Start75 证据。
- 没有发现能在不损害审计性或回归覆盖的前提下安全删除的产品文件；因此本次以移动归档代替永久删除。
- 外部 provider credential 不属于仓库归档，任何文档都不得记录其值或摘要。
