# R4.0-021 建模运行的最新状态摘要与分类耗时记录设计

## 1. 范围、基线与状态

- 权威范围：[R4.0-021](../../requirements/requirements-v4.0.md#r40-021-建模运行的最新状态摘要与分类耗时记录)。本设计提供接续导航所需的最新事实摘要，并规定时间分类、墙钟/累计/估算口径。
- 关联合同：[modeling-dev-loop Skill](../../../skills/modeling-dev-loop/SKILL.md)、[progress report](../../../skills/modeling-dev-loop/references/progress-report.md)、[R4.0-018～020 设计](2026-10-04-r4-0-018-acceptance-startup-handoff-design.md)。摘要不替代独立验收、handoff、写入完整性或语义质量判定。
- 当前状态：需求细化与设计；未实现、未新增监控服务、未对现有千行记录重写。现有 `modeling_team/host_ops.py:get_run_status` 已返回 identity、recorded state、latest stage、last activity、semantic progress、first blocker、pending summary、terminal conclusion、liveness、cursor、observed_at、evidence refs 和 limitations；该结构是最小复用基线。
- 现有记录缺口：status 输出已有大部分事实，但 session 级顶部摘要和分类耗时没有统一的进度报告栏目；过去记录中的阶段耗时只能按局部窗口估算。未知、重叠和局部估算必须保留，不能为了填表猜值。

本设计只补进度报告顶部摘要和现有记录中的轻量时间行；不创建管理 UI、监控平台、计时 Agent、每个工具调用强制打点或新的 scheduler。

## 2. 最新状态摘要合同

`get_run_status` 继续是 run 级只读事实入口。宿主读取其现有字段后，在 progress report 顶部维护一段当前摘要；这是一段可追溯的报告栏目，不是新的 status API 或平台 schema。每一项必须有来源或明确为 `unknown`。

以下只是 progress report 的栏目示意，不是新的 API/schema：

```json
{
  "latest_summary": {
    "as_of": "<UTC observed_at>",
    "run": {"run_id": "<run>", "checkpoint_id": "<current-or-null>", "source": "evidence/checkpoints.jsonl"},
    "process": {"recorded_state": "RUNNING", "observed": "alive|exited|unknown", "basis": "host_supervisor|chain_writer_lock|unknown"},
    "progress": {"stage": "<latest stage>", "semantic": "recorded facts", "verdicts": [{"scope": "public", "value": "PARTIAL", "source": "<report>"}]},
    "first_blocker": null,
    "remaining": {"pending_counts": {}, "next_action": "<current action or unknown>"},
    "authorization": {"reference": "<safe ref or null>", "starts_authorized": null, "starts_used": null, "starts_remaining": null, "source": "<ledger ref or unknown>"},
    "evidence_refs": ["state.json", "evidence/<file>.jsonl"],
    "limitations": []
  }
}
```

摘要中的 `RUNNING`、角色 terminal 或 process observation 都是独立事实。`process.observed=alive` 不能推出有效语义进展；`verdicts` 只能取现有完整报告/terminal evidence 的安全摘要，不能缩小分母或把 handoff/收口写成 PASS。授权余额无法从 run 根可靠取得时返回 null/unknown，并在 session 级 progress report 引用实际授权台账；绝不从 semantic-start 文件数量猜余额。

`checkpoint_id` 只引用当前可定位的已发布 checkpoint/handoff；没有唯一最新包、包已漂移或证据不可读时写 unknown，并保留限制。`remaining.next_action` 来自 pending action/阶段交接/进度记录，不能由摘要器发明业务动作。

## 3. 时间分类与记录格式

沿用现有事件和进度记录，在需要的阶段边界追加轻量时间行。分类使用稳定英文值并在报告显示中文：

| category | 含义 |
| --- | --- |
| `production_semantic_modeling` | 生产角色访谈、语义分析、候选建模和受控业务资料处理 |
| `independent_consumer_judge` | 独立 Consumer 检索/回答和 Judge 复核；public/hidden 可在 scope 中区分 |
| `waiting` | 等待业务回答、用户授权、外部接口、进程/资源状态或明确下一动作 |
| `repair_test` | 故障诊断、窄修复、开发测试和独立功能复测 |
| `review_docs` | 方案评审、记录审阅、设计/文档维护 |
| `startup_cleanup` | 启动准备、停止/清理、资源恢复和交接操作；与语义工作分开 |

建议的现有记录时间行如下，时间统一保存 UTC ISO-8601，并在报告声明显示时区；不新增平台 schema：

```json
{
  "session_ref": "<safe session reference>",
  "interval_id": "<stable id>",
  "category": "repair_test",
  "scope": "r4-0-021",
  "started_at": "<UTC>",
  "ended_at": "<UTC or null>",
  "duration_seconds": null,
  "basis": "observed|event-derived|estimate",
  "source_refs": ["<record or event>"],
  "overlaps": ["<interval id>"],
  "note": "<why exact separation is unavailable>"
}
```

`ended_at` 和 `duration_seconds` 不同时猜测；可由明确端点计算时才写 duration。墙钟总耗时是实际 session 窗口的经过时间或其可定位区间的 union，重叠区间不能重复相加。累计 Agent 工作时间另列 `cumulative_agent_seconds`，不与墙钟总量相加；分类可重叠时单独标出。只有局部窗口时写 `basis=estimate` 和覆盖范围，不外推到全 session，不伪造 CPU、token、计费或精确有效时间。

## 4. 决策表

| 决定 | 选择 | 原因与边界 |
| --- | --- | --- |
| D021-1 | 在 progress report 顶部维护可追溯当前摘要，复用既有 `get_run_status` 输出，不创建第二个状态 API | 现有 status 已聚合大部分字段；减少接续者同时拼读多份文件，且不改运行代码 |
| D021-2 | 摘要是事实索引，不是自动结论器 | 保留来源、时间、限制和 unknown；不能由 RUNNING、角色自报、handoff ready 或报告收口推出语义 PASS |
| D021-3 | 授权余额采用 session 台账输入，run 级不可得则 unknown | 额度是用户边界，不能由工具调用/semantic-start 计数猜测；不引入第二套计数器 |
| D021-4 | 时间以 append-only interval 记录，区分 wall-clock、overlap、cumulative 和 estimate | 适应已有长记录和并行 Agent；避免将进程存活时间误报为语义工作 |
| D021-5 | 六类分类够用；不足时允许合并并说明 | 直接服务本期改进判断，不建设过细的逐工具计时和管理 UI |
| D021-6 | 摘要维护在记录顶部，历史事件、报告、失败、清理证据只读保留 | 当前导航变新不意味着历史被改写；旧阶段明确时点和适用范围 |

## 5. 生成与交接流程

1. `get_run_status` 读取现有 evidence/state/pending/launch/checkpoint 记录，按证据时间选择最新可读项；每个字段保留 source/limitation。
2. 宿主在 progress report 顶部写当前摘要的核实时间、run/checkpoint、真实进程状态、语义成果、有效验收/待执行分母、首阻塞、剩余/下一动作、授权余额和证据链接。若摘要器与手工记录不一致，保留差异并以最新可核实事实修正顶部说明，不覆盖历史。
3. 发生生产交接、独立验收、窄修复、等待、审阅或清理时追加分类时间行；并行活动分别记录 interval/overlap。长时间无事件时不把整个进程窗口填成语义类。
4. 交接给下一观察者时提供摘要和原始路径/偏移；如果没有真正安排接手，写明未安排。新结果取代旧阶段状态时追加新时点和范围，旧报告仍保留。

## 6. 实施文件归属

| 文件 | 计划工作 |
| --- | --- |
| `modeling_team/host_ops.py`、`host_ops_mcp.py` | 作为现有只读事实来源复用；本条不改运行代码或增加 status 工具 |
| `skills/modeling-dev-loop/SKILL.md` | 在观察、交接、每轮结束和耗时报告处引用摘要及分类口径；保持语义优先和 20 分钟启动规则 |
| `skills/modeling-dev-loop/references/progress-report.md` | 增加顶部摘要模板、时间分类表、墙钟/累计/估算说明和交接责任字段 |
| `skills/modeling-dev-loop/references/team-runbook.md` | 将现有 `get_run_status`/events/pending/checkpoint 引用组织为快速接续步骤；不要求全面预检 |
| `docs/delivery/records/` 当前交付记录 | 以链接和时点补充本轮摘要；不批量改写历史记录或旧 verdict |

所有新增报告栏目必须是安全白名单，不能带隐藏题面、答案或凭据；status 现有字段保持原语义。

## 7. 分层验证计划

共享用例见[测试计划](../test-plans/2026-10-04-r4-0-018-021-operations-coordination-test-plan.md)。核心场景：

| 场景 | 预期 |
| --- | --- |
| A1 长记录多次阶段收口后接续 | 顶部摘要指向最新 run/checkpoint/状态/成果/阻塞/下一动作/授权，旧记录仍可读 |
| A2 新结果替代旧状态或资源重新准备 | 新旧时点和适用范围清楚，旧报告/清理证据不被覆盖 |
| A3 语义与修复/审阅并行 | 墙钟 union 不重复计算；累计 Agent 时间和重叠分类单列 |
| A4 只能取得进程窗口或局部估算 | 标记 unknown/estimate 和来源，不外推有效语义时间 |
| A5 用记录提出流程改进 | 生产语义、独立消费、等待、修复、审阅、启动清理分开，且不新增监控/预检框架 |

机械结构/链接检查、开发测试和独立功能验收只能证明摘要与计时合同。真实运行中的语义进展和独立验收仍按原 L0/L1 证据门执行；报表完整不等于模型 PASS。

## 8. 设计完成边界

本设计不宣称 R4.0-021 已实现，也不对当前记录的估算精度作新结论。实现后若授权、证据或端点缺失，应保留 unknown/PARTIAL，并报告实际可证明的墙钟、局部估算和语义工作时间。
