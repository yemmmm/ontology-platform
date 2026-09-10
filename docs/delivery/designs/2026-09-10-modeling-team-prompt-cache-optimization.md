# Modeling Team 提示前缀与读取复用优化

## 授权与范围

2026-09-10 用户在缓存命中分析后授权实施优化，并要求把边界清楚的机械工作交给 Claude Code。
本增量归属 [R3.0-002/006](../../requirements/requirements-v3.0.md) 的 Team 运行路径，
沿用 [R2.3-007](../../requirements/requirements-v2.3.md) 的模型路由与冻结合同。
主工作区起点为 `71542b5`；原有 `AGENTS.md`、`CLAUDE.md`、`.codex/agents/` 改动不属于本次。

## 证据与判断

读取 `workspaces/skill-role-20260910/runtime-checkout/workspaces/modeling-runs/` 下的
`r30006-20260910-auth004-start1/2/3` 保留日志，四个生产角色的 `token_usage_record`
按 `response_id` 去重后，与各线程累计输入/缓存计数一致。读取快照截至
2026-09-10 14:01:52 UTC，不包括后续验收角色或尚未记录的请求。

| start | 输入 tokens | 缓存 tokens | 缓存输入比例 |
|---|---:|---:|---:|
| 1 | 17,496,461 | 17,219,453 | 98.417% |
| 2 | 5,404,010 | 5,218,304 | 96.564% |
| 3 | 56,062,874 | 54,682,880 | 97.538% |

start3 的五次压缩请求自身产生 633,209 未命中输入 tokens，占该轮未命中的 45.9%。
Modeling 压缩后首次请求为 16,580 输入 / 2,304 缓存（13.90%），随后一轮恢复至 94.21%。
普通续轮缓存已经有效。Protocol 的 256 次 shell 返回不能全部归因于重复资料读取；
不少是工具调用故障诊断，近期 `2212738` 已修复工具名称提示，本增量不重复修改该问题。

[DeepSeek 缓存说明](https://api-docs.deepseek.com/guides/kv_cache/)要求复用已落盘的完整前缀单元，
共同前缀可能在前两次不同请求后才被识别。
[Responses 兼容合同](https://api-docs.deepseek.com/guides/responses_api/)明确不支持
`prompt_cache_key`、`prompt_cache_retention`、`previous_response_id`；不增加这些参数。

## 最小改动

1. 只调整 `TeamRunner._task_text()` 的 schema-v2 分支：角色/协作说明在前，未经改写的
   `task.objective` 在独立的末尾 `Task objective` 段出现一次。角色专属来源列表、scope、
   generation、候选/票据绑定、验收隔离和所有原有约束完整保留。schema-v1 文本逐字不变。
   目标是同角色、同配置而目标不同的任务保留更长的相同前缀；不声称跨不同工具集或不同
   角色必然共享缓存。
2. 在 v2 生产角色现有来源读取说明处明确：首次仍完整读取所有获准来源；同一线程后续
   不因收到新消息而重新输出未变化的全文，优先复用已读内容与准确定位；内容缺失、过期、
   变化、截断或压缩丢失时按需重新读取。此约定不豁免实时状态刷新、写前校验、完整引用，
   不扩大角色可见范围，也不允许跨 run 继承。Acceptance 保留独立的禁读来源说明。
3. 不改 provider、Codex 二进制、自动压缩阈值、线程生命周期、工具库存、平台读缓存、
   协作/写入/授权合同；不新增缓存服务、预热流量或新的平台硬门。

GitNexus 已修复本地 FTS 索引并重新构建。`_task_text` upstream 影响为 LOW：
直接调用者 `TeamRunner.start`、`run_no_semantic_start_smoke`，间接入口 CLI `main`。

## 验证与交接

- Claude Code 仅拥有 `modeling_team/runner.py` 及新增的提示合同回归测试文件；主 Agent
  负责本记录、需求同步、独立检查、总体回归和提交。双方不得覆盖其他并发改动。
- 先证明新测试在原代码上失败，再完成最小修复。验证 v2 各返回分支的目标仅出现一次且位于
  末尾；在仅替换目标时静态前缀完全相同；覆盖生产四角色、Acceptance 特殊分支和 v1 原文。
- 运行已有来源隔离、scope、formal 协作、CQ 路由和完整 Modeling Team 测试。
- 若执行真实 provider 对照，仅使用无业务源、无工具、无平台写入的合成请求，通过既有
  凭据读取/Responses 路径观测 usage；多轮并交错控制冷启动，保留输入、缓存、输出及延迟。
  不运行 semantic modeling start，不消耗或扩张其他会话的建模额度。
- 本次没有 backend/frontend、服务配置或依赖改动，无需重启在用服务。新提示在后续 fresh
  Team 启动时生效。文本/机械检查及合成 provider 探针均不能替代完整真实建模质量验收。

## 执行记录

- 2026-09-10：范围冻结，开始 Claude Code 机械交付；验证结果待补。
- Claude Code 已完成 `_task_text` 改动及 26 项新增回归；开发侧先观测
  `24 failed, 2 passed`，修复后 `26 passed`，相关既有测试合计 256 passed。
  交接记录：`workspaces/cache-optimization-20260910/claude-result.md`。
- 主 Agent 集成复核收窄两处提示：删除可能扩大首次读取时序的“before acting on any
  teammate request”；明确获准 teammate handoff 仍可复用，禁止的是其他角色私有来源、
  其他 run 会话和隐藏材料。避免将正常跨角色交付误判为越权来源。
- 首次全量测试 `7 failed, 1452 passed, 1 skipped, 321 subtests passed`。七项均为
  `test_deepseek_codex_runtime.py` 的 fallback 凭据文件测试，宿主已设置的
  `DEEPSEEK_API_KEY` 优先于测试文件，导致预期文件错误未触发；与提示改动无关。
  不修改凭据逻辑或测试预期，只在测试子进程清除该变量，最终命令如下：

  ```bash
  env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest modeling_team/tests -q
  ```

  结果：**1459 passed, 1 skipped, 321 subtests passed，65.41 秒**。
  日志：`workspaces/cache-optimization-20260910/modeling-team-tests-clean-env.log`。
- 主 Agent 独立比较原始提交函数与最终函数，在普通 v2、formal、v3 CQ 三种配置、
  五个角色、有/无 scope 共 30 种组合中，移除新增读取段及目标位置变化后原指令全部逐字一致。
  新测试 Ruff、文档链接与 `git diff --check` 通过；原有 AGENTS/CLAUDE 改动摘要未变。

## 最终前缀与真实 Provider 证据

同一 v3 Task/Profile 中仅替换目标首字符的五个合成变体，其任务文本公共 UTF-8 前缀如下；
这些字节数不包括 App Server 的角色指令、Skills 或工具库存，也不作为 token 数估计：

| 角色 | 原任务文本公共前缀 | 最终任务文本公共前缀 |
|---|---:|---:|
| Coordinator | 0 | 4,539 |
| Modeling | 0 | 3,604 |
| Protocol | 0 | 6,697 |
| CQ | 0 | 2,376 |
| Acceptance | 0 | 2,626 |

真实 DeepSeek 对照使用原/最终 Protocol 任务文本、五个不同的合成目标、每组固定但组间不同的
实验标记，以免两组互相复用缓存。两个组交错发送；相同 `deepseek-flash` / `max`，通过
既有 `ProviderSessionManager` 的 Responses 代理调用；无工具、无业务源内容、无平台调用。
不包含 App Server 的额外前缀，所以仅验证这次文本布局差异。

第一轮每组五次，输出上限 64，全部被限额截断；输入 usage 有效但不能作为完整响应证明。
原始结果完整保留于 `workspaces/cache-optimization-20260910/provider-probe.json`。
最终措辞冻结后重新执行每组五次，将输出上限设为 512；最终输入结果如下：

| 指标 | 修改前 | 最终修改后 |
|---|---:|---:|
| 五次总输入 tokens | 6,492 | 7,152 |
| 五次缓存输入 tokens | 0 | 5,120 |
| 五次未命中输入 tokens | 6,492 | 2,032 |
| 含首轮的缓存输入占比 | 0% | 71.588% |
| 第 2–5 次缓存输入占比 | 0% | 89.479% |
| 五次总输出 tokens（含 reasoning） | 522 | 1,848 |
| 响应总耗时中位数 | 1,139.05 ms | 2,039.10 ms |
| completed / incomplete | 5 / 0 | 4 / 1 |

输入未命中减少 **68.7%**，即使新增复用提示使输入稍增，输入缓存仍有明确收益。
输出推理长度不同且最后一个 after 响应达到限额，不能把该结果称为总成本或总延迟改善；
本次合成对照实际观察到更多输出及更高响应耗时。未进行完整建模对照，因此读取提示是否
减少重读/compact、实际 Team 成本、吞吐和语义质量仍须另行真实运行证明。

两轮总计 20 次有界 provider 请求，**零 semantic modeling starts**；代理清理成功，
监听 socket 和线程均关闭，凭据未写入请求文件、日志或提交内容。
最终可复核工件（本地 gitignored 目录保留）：

- [最终请求及逐次 usage](../../../workspaces/cache-optimization-20260910/provider-final/provider-probe.json)
- [最终统计摘要](../../../workspaces/cache-optimization-20260910/provider-final/summary.json)
- [文本前缀比较](../../../workspaces/cache-optimization-20260910/prefix-comparison.json)
- [原指令等价比较](../../../workspaces/cache-optimization-20260910/instruction-equivalence-final.json)

本增量机械交付已通过，输入缓存专项效果已观测；完整真实建模收益与质量未验收。
后续 fresh Team 必须使用包含此变更的 checkout；既有隔离 runtime checkout 不会被本次改动热更新。
