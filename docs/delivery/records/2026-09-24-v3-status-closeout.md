# v3.0 阶段状态收口（2026-09-24）

本记录同步 2026-09-14 后已经发生、但尚未进入 v3.0 需求状态的运行与验收结果。
仅核对现有测试计划、宿主台账及保留 run 的只读状态；不重跑建模、不补造独立验收。
需求归属见 [v3.0 需求](../../requirements/requirements-v3.0.md)。

## 已核实的后续证据

| 范围 | 现有证据 | 可确认的结论与边界 |
| --- | --- | --- |
| R3.0-015 S4 | [共享测试计划的 Judge 真实复测与独立只读复核](../test-plans/2026-09-14-r3-0-015-modeling-checkpoint-recovery-test-plan.md#judge-窄修复与真实复测2026-09-16)；本机保留 `workspaces/checkpoint-minimal-20260916/host-ledger.json` | 人工最小场景的验收续跑获得一题非盲回归 PASS，独立只读复核判有界 S4/L0 PASS。该题已公开，不是完整场景隐藏题 L1。 |
| R3.0-015 S1/S2 | 本机 `workspaces/modeling-run-ledger.md` 的 auth-r3-0-023 批次；`workspaces/auth-r3-0-023-20260919/authorization.json`；执行 checkout 中两 run 的 `state.json`、`evidence/semantic-start.jsonl`、`evidence/checkpoints.jsonl` | start1 发布 `scenario_mapped-0001`、`cq_frozen-0001`；resume1 于 2026-09-20 00:43 +08 跨进程从后者接续，产出拓扑决定、候选和审批锚点。两 run 当前均 `CLEANED`，2/2 次 fresh starts 消耗，原证据保留；本批判据只覆盖恢复后真实推进，未执行完整 CQ/SQL 验收。 |
| R3.0-016 S2 | 本机 `workspaces/modeling-run-ledger.md` auth-r3-0-022 start3 与收尾段；[S2 独立测试计划](../test-plans/2026-09-18-r3-0-016-s2-start-lifecycle-checkpoint-test-plan.md) | 环境补齐后 start3 取得真实 semantic-start，用户于 2026-09-18 裁决本需求算作验收；后续 `stop_run` 收尾为 `CLEANED`，授权 1/1 消耗，保留原运行证据。不能把此前暂停态写成当前仍活跃。 |
| R3.0-017 | [独立功能验收与 F-SEAL-004 独立复核](../test-plans/2026-09-18-r3-0-017-checkpoint-data-fork-test-plan.md) | 功能验收与补充证据闭环；其交付范围没有真实 LLM 建模或独立语义验收。 |

auth-r3-0-023 的 run 根位于本机执行 checkout
`workspaces/auth-r3-0-023-20260919/runtime-checkout-auth023-1/workspaces/modeling-runs/`。
本次直接读取两份 `state.json`，均为 `CLEANED`；start1 的检查点事件含
`scenario_mapped-0001`、`cq_frozen-0001`，resume1 的 `resume-prepared` 绑定
`cq_frozen-0001`，计数为 `semantic_starts: 1`。这些 workspace 文件被 Git 忽略，
本表保留可核对的本机证据路径与结论，但不将宿主陈述当作独立语义验收。

## 仍未闭合

- v3.0 的完整工业售后场景仍缺 [版本完成定义](../../requirements/requirements-v3.0.md#6-版本完成定义)
  要求的独立运行证据：R3.0-006 真实建模与端到端问数、R3.0-008B 值语义联合验收、
  R3.0-009/011 的完整真实语义及批次验收。R3.0-012 的局部一题证据不替代其完整目标。
- R3.0-014 已实现，独立机械 Round 1 专用测试 12 项、Team 2016 项、后端 80 项通过；
  M4、M8、M9、M15、M26、M27、M30、M31 缺完整专项链路证据，结论为 `PARTIAL / REVISE`。
  [共享测试计划 §7.7](../test-plans/2026-09-13-r3-0-014-dry-run-before-translation-review-test-plan.md#77-2026-09-24-独立机械测试-round-1)
  保留命令、结果和缺口。auth014 宿主台账称 L0-1/2/3/4/6 取证；L0-5 unknown 未触发，
  L1 未完成。此次没有独立复核原运行证据。
- R3.0-013 仅登记待细化；R3.0-015 S3 按设计延后；R3.0-009 三项 Low 已登记但
  不阻断既有机械验收。这些事项按各自范围排期，不并成 v4 启动前置。

本轮没有新的 semantic start、平台写入、原始运行证据修改或产品代码修改。
