# R5.0-011 独立工程测试

日期：2026-11-03。权威需求：`docs/requirements/requirements-v5.0.md#r5-0-011`。

范围：默认关闭与显式提交、CQ/切片无实际模型执行、整合实际正文证据、格式错误可恢复、自然停用、汇总保留终态。只修改本测试文档和 `modeling_team/v5/tests/test_process_evaluation_independent.py`；不修改产品实现。

非目标：不启动付费模型或生产建模，不将机械评分规则测试当成 A6/A7/A13 的独立语义校准，不证明净降耗或 A14 实际采用。

环境：v5 `.venv/bin/python`，仓库已有 PostgreSQL 配置；使用独立临时 schema 并由 fixture 清理。命令：

```sh
cd modeling_team/v5
ONTOWEAVE_TEST_POSTGRES_CONFIG=/home/yangxiang/ontology-platform/workspaces/v5-codex-p0/postgres-host.json .venv/bin/python -m pytest tests/test_process_evaluation_independent.py -q
```

| 用例 | 步骤 | 期望 |
| --- | --- | --- |
| I1 | CQ/slicing 原生只读 invocation，无已准备实际模型 | 不访问平台配置，允许只读材料评分 |
| I2 | 整合只返回修订、路径/标签、无实际资源正文 | 不得完成满意评价 |
| I3 | 原生返回 `dimensions=null` | 诊断记录 failed，可纠正，不能向生产冒泡异常 |
| I4 | producer 发布现有 TeamChannel 材料并显式提交 | 允许绑定该版本 |
| I5 | stop/失败汇总后晚到合法评价 | 新报告保留原生产终态 |
| I6 | 三类固定报告含源条件缺口或未知 | 缺口不判满意，未知不猜分；仅机械规则 |

通过标准：工程用例全部通过；未执行语义评分与真实采用明确 BLOCKED，不能升级整体需求 PASS。

## Round 1

工作区：2026-11-03 开发中，产品文件尚未提交；执行期间开发者有并行修复，结果需 Round 2 固定后确认。

实际命令：上述独立 pytest 命令。结果：**6 failed, 3 passed in 2.18s**。机械评分三类固定报告规则通过；不是实际评分有效性结论。

- I1 High FAIL（2 个参数用例）：CQ/slicing invocation 仍读取平台 read_config，`platform_scope_not_prepared` 使评分无法开始。违反 A5。
- I2 High FAIL：只提供带修订的 label 搜索结果，未返回 `semantic_definition` 或 `detail_fields` 实际正文，仍完成且满意。违反 A5 的实际表达证据合同。
- I3 High FAIL：`dimensions=null` 引发未捕获 `TypeError: 'NoneType' object is not iterable`，诊断错误未按 F9 登记为可纠正失败。
- I4 Medium FAIL：TeamChannel 发布 `team_material`，提交端当时 allowlist 不接受，`process_artifact_forbidden`。违反 F3 复用已有产物边界。
- I5 Medium FAIL：先形成失败终态汇总，晚到结果调用 `summary('progress')` 使最新汇总生产状态变为 progress。违反 F11 终态与晚到报告语义。

A6/A7/A13 实际评分校准和 A14 真实任务均 **BLOCKED/未执行**：本轮不具备付费评分及真实建模授权，也没有原生评分报告；机械规则不能替代该证据。

结论：**FAIL**，已向开发者报告，需修复后原用例复测。

## Round 2

工作区：开发者修复后的当前未提交实现。仍使用同一用例、同一 PostgreSQL 临时 schema 方案。I1 按新增公开参数 `materials_only=True` 调用，且已核对实际 ProcessEvaluation 为 CQ/slicing 传此参数。

实际命令：同 Round 1。结果：**9 passed in 3.03s**。Ruff 本测试文件格式及静态检查通过。

| 用例 | 本轮结论 | 证据 |
| --- | --- | --- |
| I1 CQ/slicing（2 例） | FIXED | 无准备模型仍只启用 read_material，不访问平台 read_config |
| I2 标签/修订不能替实际正文 | FIXED | 整合 label-only 原生记录不能完成满意结果 |
| I3 格式错误可恢复 | FIXED | dimensions=null 返回 failed 及具体 error |
| I4 既有交接材料 | FIXED | team_material 显式提交 queued |
| I5 晚到汇总终态 | FIXED | 新汇总保留 failed 及 production_complete=true |
| I6 三类机械缺口/未知（3 例） | PASS | 已知缺口=gaps，证据不足=unverified |

独立工程测试结论：**PASS（本测试范围）**。A6/A7/A13 的原生评分有效性校准及 A14 获准真实任务仍 **BLOCKED/未执行**；本文件未产生任何付费调用或真实 semantic start，不据此宣称完整需求验收或净降耗。

## Round 3

工作区：2026-11-03 最终工程回归中的稳定实现；核对新增短控制锁、报告字段验证、历史适用性及账本读取。仅修改本测试记录，不修改产品或测试代码。

原命令复跑：**9 passed in 3.95s**。I1— I6 均 PASS，无已测场景回归。

### I7 — High：停用与真实准入之间仍有窗口

只读检查后使用临时 schema 和本文件既有的无付费 `native` stub 做额外内存钩子实验；不修改产品文件。步骤：

1. 启用并提交 CQ 阶段。
2. 在 `ontoweave_modeling.execution.synchronize_budget` 的首次调用钩子中执行 `process.configure(False)`，模拟 Host 在预算同步期间停用。
3. 继续原 `ExecutionManager.run`，观察 `begin_activity` 后的 invoke 调用。

期望：停用早于原生准入，不能开始新评价；未开始记录应取消。

实际输出：

```text
{'switch_enabled': False, 'native_calls': ['native_started_after_disable'], 'result_state': 'completed'}
```

证据：`ProcessEvaluation._run` 在控制锁内仅把诊断记录改为 running，释放锁后才调用 manager.run；后者先同步预算，再执行 TaskControl.begin_activity。停用看到 running 时不取消，而原生准入没有复查评价开关。故该窗口不能解释为“原生回合已经开始后自然结束”。违反 F9／A9。

建议：将评价开关检查与原生 begin_activity 的短准入区间置于同一锁内，不在整段原生回合持锁，以保留运行中手动停用能力。

Round 3 总结：**FAIL（新增 I7 High）**；原 9 项 PASS。已报告主 agent。A13/A14 仍未授权、未执行。

## Round 4

工作区：I7 修复后的实现，`ExecutionManager.run` 在预算同步后以可选 admission_guard 短锁覆盖开关复核、begin_activity 与 dispatching 持久化；原生 invoke 不持该锁，既有执行对账保持原身份。

将 Round 3 同一稳定复现固化为 `test_disable_during_budget_sync_prevents_native_admission`，未修改产品代码。复跑全部独立用例：

```text
10 passed in 2.95s
```

- I7：**FIXED**。预算同步钩子中停用后，记录为 cancelled，原生调用次数为 0；TaskControl.active 为空，未产生新的 execution。
- I1— I6：**PASS**，无回归。
- Ruff 格式、静态检查：PASS。

本轮独立工程测试结论：**PASS（10 项范围）**。Round 3 的 High 已关闭；此结论不声称覆盖所有调度时序或真实评分有效性。A13 原生评分校准、A14 获准真实任务仍未授权、未执行，维持此前证据边界。
