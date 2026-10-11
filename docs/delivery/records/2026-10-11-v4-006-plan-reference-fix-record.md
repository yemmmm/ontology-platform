# ISSUE-V4-006 批准计划引用入口修复

2026-10-11。范围为用户授权定位和修复[待解决清单](../open-bugs.md)中仍开放的
ISSUE-V4-006；其余五项已有修复证据，不重复开发。依据
[R4.3-002／003](../../requirements/requirements-v4.3.md#r43-003-确定性产物按引用交给工具处理)
和 [R3.0-014](../../requirements/requirements-v3.0.md)。未启动或恢复语义建模，未改变额度，
未修改历史 workspace、证据、冻结角色输入或平台资源。

## 定位与边界

- start3 原始 `evidence/deliveries.jsonl` 的 `delivery-2` 要求只做新 dry-run、禁止 apply；
  `delivery-42` 审阅完整三份 r6 关系计划后同样要求只 dry-run，随后逐批单独授权 apply。
  Protocol 原生会话明确识别 `protocol_execute_approved_plans`，并因其连续 apply 行为
  与当前只验证授权不符而选择手工入口。上述是具体操作选择依据，不将其概括为模型质量差。
- 原 `capability_mcp.py` 的引用 Schema 只有计划／租约／trace 参数，Runner 默认连续
  dry-run/apply，无只验证模式；`_reference_plan` 还无条件前置翻译批准。所有 capability
  的 `tools/list` 描述均是笼统的角色描述，未说明引用与手工路径区别。
- Protocol 活动提示原第 314 行附近前置翻译审阅，后文又要求批准后按引用执行；
  R3.0-014 实际允许先 dry-run、再用 findings 审阅翻译。该冲突属于 prompt-contract。
- `approval_content_mismatch` 原始两次失败来自手工删减 item 字段，批准内容一致性守卫
  正确阻止了不符内容。保留该守卫，修复确定性传递入口，不放宽模型写入。
- 旧运行未保留完整 `tools/list` 返回。baseline 的静态角色列表不能冒充模型完整工具视图；
  隔离代码和角色对入口的识别支持 start3 诊断，当前真实 socket fixture 证明接线／Schema
  可调用，不将其外推为每一轮旧调用选择的唯一原因。

原件为本机保留材料：
[start3 deliveries](../../../workspaces/modeling-runs/r4009-20261010-delivery-glmflashhigh-start3/evidence/deliveries.jsonl)、
[Protocol native session](../../../workspaces/modeling-runs/r4009-20261010-delivery-glmflashhigh-start3/runtime/protocol/home/sessions/2026/10/10/rollout-2026-10-10T08-10-26-01a124dd-0353-7cb2-9f69-a8959ad2e74e.jsonl)、
[实际调用字段差异](../../../workspaces/v4-delivery-20261010/start3-r6-core-exact-invocation-diff.json)。
这些 gitignored 宿主原件不作为隔离生产角色输入，也不提交或改写。

## 最小修复

1. 同一 `protocol_execute_approved_plans` 增加可选 `mode`，默认 `apply_atomic` 保持旧行为。
   显式 `dry_run` 配合空 `lease_tokens` 精确转发保存的 projection，只验证不应用正式模型。
   候选／业务批准、当前版本、未知写入对账仍保留；翻译批准只在 apply 路径要求。
2. 只验证返回每份计划的实际 dry-run Attempt／findings，资源状态标为 `not_applied`，
   不当作语义读回或验收。后续获准 apply 可复用同计划同版本的成功证明；漂移仍重新验证。
3. 两角色明确只验证调用与正常批准列表连续执行；显式 HOLD／只读指令仍必须遵守。
   真实 `tools/list` 对引用／手工入口给出不同用途描述。同步权威需求与 MCP 文档。

调用范围检查：`TeamRunner.__init__` 将 handler 接至 `RunnerAcceptanceCarrier`；
其 `_dispatch_capability` 校验 Protocol 身份后调用 handler；`_reference_plan` 仅由该 handler
和计划覆盖检查调用，覆盖检查保留默认翻译批准要求。非统一任务的 capability 集合不变。
GitNexus 未收录两个目标方法，无法提供完整图影响分析；已用直接调用点和 diff 检查补足。
`detect_changes` 返回 low，但未覆盖 Runner 新方法，不将其当作完整图覆盖证明。

## 验证与关闭边界

新增真实本地 capability socket 回归先失败：缺少 `mode` Schema，验证调用被 `-32001` 拒绝。
修复后检查只验证无租约／无 apply、完整 items、证明复用、翻译批准对 dry-run 与 apply 的
不同边界；同时回归内容篡改、未知写入阻断、连续执行版本推进与已 apply 不重放。
平台下游为确定性 fixture，未产生真实语义建模或平台写入。

工程回归 **122 passed，7 subtests passed**（36.73 秒）。命令从 `backend/` 执行：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
  ../modeling_team/tests/test_v43_production_refs.py \
  ../modeling_team/tests/test_r30014_dry_run_before_translation.py \
  ../modeling_team/tests/test_r30009_plan_ref_capability_schema.py \
  ../modeling_team/tests/test_r30009_runner_wiring.py \
  ../modeling_team/tests/test_capability_tool_names.py \
  ../modeling_team/tests/test_capability_handoff_diagnostic.py \
  ../modeling_team/tests/test_staged_associate_evidence.py \
  ../modeling_team/tests/test_transport.py -q
```

`git diff --check` 通过，清单与新增记录的 30 个本地链接目标存在。

真实采用和资源读回仍须在下一次已获准正常运行观察，
本次不声明独立语义验收或运行效果 PASS。仅修改 modeling_team 和文档，不要求后端／前端
服务重启；旧冻结进程不会因磁盘修复自动更新。
