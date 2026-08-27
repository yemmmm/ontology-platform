# R3.0-006 T0 机械增量独立验收记录

- 需求：`docs/requirements/requirements-v3.0.md` R3.0-006
- 共享测试计划：`docs/delivery/test-plans/2026-08-27-r3-0-006-real-modeling-e2e-acceptance-test-plan.md` §3 T0 表
- 交付设计：`docs/delivery/designs/2026-08-27-r3-0-006-real-modeling-e2e-acceptance-design.md` §3.1 M1～M3
- 被测实现：commit `0cfabf7` "Implement R3.0-006 M1-M3 mechanical increments"（main）
- 独立验收方：requirement_tester（不创建/不延续任何真实 run；本轮零实现代码改动）

## 测试范围与非目标

- 范围：仅 T0-1～T0-6（机械增量 M1～M3 的实现阶段验收）。
- 非目标：不启动真实 modeling run；不执行 Phase A～D（T1 及以后用例）；不修改实现代码；
  不验证 attempt 记录面（按设计属 T1-3，用户授权时建立）。

## 稳定命令（本轮实际执行）

```bash
uv run --project backend python -m pytest modeling_team/tests/test_r30006_mechanical_increments.py -q
uv run --project backend python -m pytest modeling_team/tests/test_r30002_runner_wiring.py modeling_team/tests/test_r30002_scenario_map.py -q
uv run --project backend python -m pytest modeling_team -q
uv run --project backend ruff check modeling_team
# 基线对照（临时 detached worktree，用后已删除）
git worktree add --detach /tmp/r30006-head1 7046260
uv run --project backend python -m pytest modeling_team/tests/test_deepseek_codex_runtime.py -q
```

## Round 1（2026-08-27，实现 commit 0cfabf7，工作区 clean）

### 逐用例结果

| # | 结果 | 证据 |
| --- | --- | --- |
| T0-1 | PASS | 新测试文件 28 passed / 16 subtests passed，其中 `LedgerBudgetGateTests::test_multi_slice_run_skips_the_start_ledger_entirely` 断言 `runner._ledger is None`、ledger root 不存在、全目录无 `.r2-3-002-start-ledger.jsonl`。代码核对 `runner.py`：`multi_slice_budget_exempt = multi_slice_workflow and not formal_acceptance` 使 v2 分支跳过 `resolve_ledger_config`。记录面（轮次/run-id/授权消耗）按设计在 T1-3 用户授权时建立，T0 阶段无对象可核，属既定时机而非阻塞。 |
| T0-2 | PASS | `test_ordinary_v2_task_still_reserves_through_the_ledger`（ledger 文件恰 1 个、含 `reservation` 记录）与 `test_ordinary_v2_task_keeps_the_reservation_gate`（第二 prepare 报 "start reservation is active"）通过；全量 suite 中 R2.3-002/003/005/008/009 相关测试全部通过（1111 passed）。注意：实现者声称"R3.0-002 既有 multi-slice ledger 预留断言改写为无预留"——经 grep HEAD~1 的 `test_r30002_runner_wiring.py`，**原先并不存在 multi-slice ledger 预留断言**，实际改写的是 gate 生命周期预期（legacy 无 plan 决策现按 `topology_missing_ontology_plan` 关闭，已在测试注释登记为 R3.0-006 修订）。属报告措辞不准，非功能缺陷。 |
| T0-3 | PASS | `test_three_role_multi_slice_run_starts_with_role_derived_dependencies`：三角色 profile `start()` 成功，`terminal_dependencies == {"protocol": {"modeling"}, "coordinator": {"modeling", "protocol"}}`，semantic-start 与 runtime-visibility-probe 证据落盘（ledger-less v2 run）。`test_four_role_formal_roster_dependency_graph_is_unchanged`：formal 四角色图仍为 `{"protocol": {"modeling"}, "coordinator": {"modeling", "protocol", "acceptance"}}`，与改动前硬编码值逐字节一致（diff 核对）。 |
| T0-4 | PASS | `InclusiveProfileContractTests` 5 用例通过：额外角色（`examiner`/`source-specialist`，agent_id ≠ role）加载并启动且不进 terminal 依赖；缺核心角色 fail-closed（"exactly one Coordinator, Modeling, and Protocol"）；核心角色 `agent_id == role` 恒等仍强制（改名 modeling 被拒）；缺核心边被拒；formal profile cross-wire 被拒。`contracts.py` diff 核对四处放宽与设计枚举一致：registry（仅拒 `_FORMAL_PROFILE_IDS` cross-wire）、角色集子集（`MULTI_SLICE_ROLE_VALUES <= role_set` + 去重）、恒等仅限核心角色、边集包含（`required_edges <= edges`）。formal 分支 diff 为零改动（byte-identical 成立）。 |
| T0-5a | PASS（附 Low 备注） | `OntologyPlanContractTests` + `GatePlanApplicationTests::test_gate_rejects_a_plan_with_dangling_slice_against_the_map` 通过：非 single 选择缺 plan → `topology_missing_ontology_plan`；single 选择带 plan → `topology_schema_mismatch`；结构规则 7 变体（单条目/重名/字段漂移/空名/空切片/切片重叠/切片未覆盖）均 `topology_invalid_ontology_plan`；dangling 仅在传入 map slice 清单时报 `topology_dangling_slice`；"map 缺失 + 含 plan 决策" 走 `map_unparsable`（更新后的 wiring 测试断言，符合评审 Round 3 提示的挂点顺序）。**Low 备注**：设计/测试计划的"既有无 `ontology_plan` 的 artifact 校验行为字节不变"与"其他选项时必填"两条对**非 single 选择的存量 artifact** 互相矛盾——实现取必填规则（fail-closed，正确取向），存量 `domain_ontology_split` 无 plan fixture 现在会被拒（已在测试中登记为声明修订）。已核 `docs/delivery/evidence/` 无任何已落档 topology-decision artifact（grep 零命中），故无冻结资产实际受影响。建议下次文档触碰时把守恒措辞收窄为"single_ontology 选择的存量 artifact"。 |
| T0-5b | PASS | `test_gate_open_applies_the_plan_and_delivers_all_ontology_ids`：门放行后 plan 应用恰一次、`ontology-plan-applied`/`ontology-plan-delivered` 事件落证、向 protocol 投递 `RuntimeDelivery(kind="multi-slice-ontology-plan", sender="runner/multi-slice-gate", expects_reply=False)`，notice `schema_version=r3-0-006-multi-slice-ontology-plan/v1` 含全部 `ontology_ids`；`protocol_context` 刷新为 `ontology_ids="ontology-1,ontology-2"`。`PlatformScopeOntologyPlanTests`：`apply_ontology_plan` 幂等（重复应用/新 scope 复用同名 Ontology 均零新建）、首条目 = scope 预建（只建 plan[1:]）、结构非法拒绝；单 Ontology `read_protocol_context` 形状不变（无 `ontology_ids` 键）。apply 失败为 evidence-only `runtime/infrastructure`、run 不终止（`test_plan_apply_failure_is_evidence_only_and_never_kills_the_run`）。task YAML 措辞同步在 commit diff 中（frozen scope 只含首个 Ontology、以 build-context 为准）。**Info 备注**：plan[0] 按位置绑定 scope 预建 Ontology，无名称一致性检查（设计即定义位置恒等，非缺陷；真实 run 中由协调 Agent 自律）。 |
| T0-5c | PASS | `MultiOntologyTerminalAggregateTests` 6 用例通过：多 Ontology 成功 run 达 `retained-pending-acceptance`（per-Ontology `workspace_versions`/`completed_session_ids`，无单值 `workspace_version` 键）；foreign/未覆盖 involved → `blocked`；同 Ontology 重复 completed session → `failed-written-retained`；`_has_writes` 覆盖全部计划内 Ontology（OR 聚合，任一有写即为 written）；retained-handoff 按 Ontology 集合记录且不完整多 Ontology 证据被拒（3 个 subTest 变异均抛 `TeamConfigurationError`，文件不落盘）。`_completed_terminal_statuses` 按 profile 实际角色集推导、四角色缺省保留（`test_retained_completion_status_is_derived_from_the_actual_role_set`）。单 Ontology/formal 清理分支代码 diff 为零改动（else 分支与旧代码一致）。 |
| T0-6 | PASS（附环境备注） | 全量 `uv run --project backend python -m pytest modeling_team -q`：**7 failed, 1111 passed, 1 skipped, 318 subtests passed**。7 个失败全部在 `test_deepseek_codex_runtime.py`（fallback 文件 chmod 0o640/0o604 与畸形赋值拒收用例 DID NOT RAISE——沙箱进程不受文件 mode 限制的环境性失败）；已在 HEAD~1（`7046260`）临时 detached worktree 中复跑该文件，同为 7 failed，且 `0cfabf7` 未触碰任何 deepseek/codex 相关文件（`git diff --name-only` 核对），确认为本仓已知环境基线、与本增量无关。ruff：10 findings 全部先前已存在（`runner.py:4819` F821 在 HEAD~1 第 4676 行即有；其余 9 个在被未触碰的 r23008/r23009 测试文件；改动文件零新增）。commit `0cfabf7` 已在 main 落档。 |

### 结论

- **总体：PASS**。T0-1～T0-6 全部通过；无阻塞缺陷；无需实现修复后复测。
- 发现（均不阻塞，不要求本轮修复）：
  1. **Low（文档措辞）**：测试计划 T0-5a/设计 §3.1 M3 的"存量无 `ontology_plan` artifact 字节不变"守恒措辞与"非 single 选择必填"规则对非 single 存量 artifact 互斥；实现取向正确，无冻结资产受影响；建议收窄措辞。
  2. **Low（实现者报告准确性）**："R3.0-002 multi-slice ledger 预留断言改写"不成立——原无该断言；实际改写为 gate 生命周期预期（已登记）。
  3. **Low（docstring 与机制不符）**：`modeling_team/runner.py:3661` docstring 称 apply 失败后 "the next cycle can retry"，但门旗标在 `runner.py:3638` 先于 apply 置位，后续 gate cycle 在 `runner.py:3550` 早退，run 内不会重试；仅 resume/新 run 会经幂等 `apply_ontology_plan` 重试。影响有限（channel (b) build-context 为权威通道、失败已落 `runtime/infrastructure` 证据），建议修 docstring 或把 apply 挪到旗标置位前。
  4. **Info**：plan[0] 位置绑定无名称核对（设计即如此定义）。
- 后续：T1 及以后用例等待用户显式授权真实 modeling start 后由 Delivery Agent 执行；attempt 记录面届时按 T1-3 核对。

## 清理

- 临时 detached worktree `/tmp/r30006-head1` 与 `/tmp/r30006-check` 比对文件已删除（`git worktree list` 复核）。
- `workspaces/modeling-runs/` 无 `r30006-*` 残留目录（测试自带 rmtree 清理，ls 复核）。
- 本轮未创建任何真实 run workspace。
