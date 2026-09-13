# 最近六轮建模的审阅与物化失败统计

- 日期：2026-09-13；只读取证快照约 20:30（UTC+08）。
- 关联需求：[R3.0-014](../../requirements/requirements-v3.0.md#r30-014-物化计划先-dry-run-后翻译审阅)。
- 本记录是历史描述统计，不是新流程效果实验，也不是模型质量验收。

## 1. 结论与口径

最近六轮中，**语义候选审阅未观察到明确退回；物化翻译审阅通常为 0 次退回，
少数运行出现 1 次；真正的平台 dry-run 校验失败为每轮 0–4 次，中位数 3 次**
（后两项仅取进入物化阶段的五轮）。技术返工不能统一称为“Agent 审阅失败”。

| 运行 | 语义候选明确退回 | 物化翻译明确退回 | 平台 dry-run validation_failed | 提交入口错误返回 |
| --- | ---: | ---: | ---: | ---: |
| auth010-start1（09-12） | 0 | 1 | 2 | 8 |
| auth010-start2（09-12） | 0 | 1 | 3 | 4 |
| auth010-start3（09-13） | 0 | 未到达 | 未到达 | 未到达 |
| auth010-start4（09-13） | 0 | 0 | 3 | 2 |
| auth011-start1 | 0，另有 1 次覆盖补充 | 0 | 0 | 2 |
| auth012-start1 | 0 | 0 | 4 | 3 |

- 语义候选明确退回：6 轮共 0 次；不是“语义正确率 100%”。审批可能遗漏问题，
  运行可能提前终止，最终独立语义验收是另一件事。
- 物化翻译明确退回：5 轮共 2 次，均值 0.4，中位数 0，范围 0–1。
- 平台 dry-run 失败：5 轮共 12 次，均值 2.4，中位数 3，范围 0–4。
- 提交入口错误：共 19 次，包括 Runner 前置拒绝及转发后错误，**不全是平台校验失败**。
  auth010-start1 的 8 次含 6 次 Runner 前置拒绝、1 次平台批量上限拒绝及
  1 次转发后内容冲突/结果不确定；不能把后者当作安全的零写入校验失败。

“一次退回”按一份明确审阅反馈计，不按涉及的条目数、消息拆分数计。
“一次平台失败”按原生平台结果中的唯一 `attempt_id`、`mode=dry_run`、
`attempt_status=validation_failed` 计；重复查询不重复累计。47 个报错条目不是 47 轮失败。
提交入口错误按原生 completed 工具调用计，与具有正常回执的失败 Attempt 分栏。
没有进入某阶段标为“未到达”，不纳入该阶段均值。没有发现退回记录写 0，不从版本号倒推失败数。

语义统计范围是 Modeling 候选的业务语义审阅；不混入 CQ 草稿评审、L2 结论的
confirmed/rejected/deferred 裁决、共享抽象取舍、工具参数错误或最终消费者验收。
这些裁决中的 `rejected` 不自动表示此前提交过一个失败的完整候选。

## 2. 样本与可复查路径

以下均是仓库根目录下的保留 workspace，相对根目录记为 A1/A2/A3/A4/B1/C1。
这些原始证据是 gitignored 运行产物，本记录不搬运隐藏 CQ、源业务数据或凭据。

| 标记 | 运行根目录 |
| --- | --- |
| A1 | `workspaces/model-compare-20260912/runtime-checkout-auth010-1/workspaces/modeling-runs/r30006-20260912-auth010-start1` |
| A2 | `workspaces/model-compare-20260912/runtime-checkout-auth010-1/workspaces/modeling-runs/r30006-20260912-auth010-start2` |
| A3 | `workspaces/model-compare-20260912/runtime-checkout-auth010-3/workspaces/modeling-runs/r30006-20260913-auth010-start3` |
| A4 | `workspaces/model-compare-20260912/runtime-checkout-auth010-4/workspaces/modeling-runs/r30006-20260913-auth010-start4` |
| B1 | `workspaces/auth011-20260913/runtime-checkout-auth011/workspaces/modeling-runs/r30006-20260913-auth011-start1` |
| C1 | `workspaces/auth012-20260913/runtime-checkout-auth012-1/workspaces/modeling-runs/r30006-20260913-auth012-start1` |

排除两个不同性质的样本：

- `runtime-checkout-auth010-2/.../r30006-20260913-auth010-start2`：提前停止的重复启动，
  没有候选/物化计划；与表中 09-12 的 start2 不是同一运行。
- `runtime-checkout-auth012-1/.../r30006-20260913-auth012-start2`：取证时仍在运行，
  开始时间为 2026-09-13 19:31:35（UTC+08），不混入已停止运行的统计。

A1/A2 的本地 runtime state 曾停留在等待态，以对应 host terminal record 的停止/重启事实为准；
A3 未进入物化；A4/B1/C1 已清理。停止、清理不代表建模成功。

## 3. Agent 审阅退回的具体证据

审阅 `evidence/deliveries.jsonl` 的候选交接、Coordinator 回复，并核对
`stage3-neutral-graph/` 候选/计划及 `value-semantics/approvals/approvals.json`。
最终 approvals 可覆盖历史状态，因此不单独用最终文件反推失败次数。

| 证据 | 观察 | 计数 |
| --- | --- | --- |
| A1 `evidence/deliveries.jsonl` 第 44 行，delivery-44 | Coordinator 明确拒绝 translation r2：118 个 command payload 删除了 r1 字段，需要恢复完整转发投影 | 物化退回 1 |
| A2 同文件第 37 行，delivery-37 | Coordinator 明确不批准 Shape r1：`depends_on` 引用了别的批次的条目，而非本批次 client_item_id | 物化退回 1 |
| B1 同文件第 12、16、19 行 | r1 先获批准；公开 CQ 投影从 0008 更新到 0025 后要求 coverage delta，继而批准 r2 | 覆盖补充 1；不算已提交候选被明确判错退回 |
| A3/A4/C1 的候选与审阅消息 | 未发现明确语义候选退回；A4/C1 的计划修订来自提交或平台反馈，不能按 r2/r3 数量算 Agent 拒绝 | 按表列 0/未到达 |

A1/A2 的两次 Agent 拒绝都涉及可由确定性合同检查发现的技术问题，
不是 Agent 对业务语义作出的否决。此事实支持将技术反馈前置，但并不证明
只要换序就能省下全部交互、或独立 Reviewer 已经能降低上下文消耗。

## 4. 平台失败 Attempt 清单

下表行号均指相应运行的 `evidence/app-server-events.jsonl`，选取包含原生平台结果的
`item/completed` MCP 调用。部分结果在 `list_ontology_modeling_batches` 的摘要内，
其状态足以计数；未拿到 findings 全量时不猜具体根因。

| 运行 | 唯一失败 attempt_id | 原生结果行 | 结果/阻塞代码 |
| --- | --- | ---: | --- |
| A1 | `682ae44e-96e1-4147-85dc-c1676db5a1c8` | 141365 | validation_failed；invalid_command_payload |
| A1 | `cd7de40a-a8d3-49b1-95ff-8ad99f914edc` | 152221 | validation_failed；列表摘要，详细 enum 问题见 host terminal record |
| A2 | `6acbf5ed-37ba-4d23-b768-94f42abaaf6c` | 71099 | validation_failed；invalid_command_payload |
| A2 | `e623a67a-9f47-4ee7-9b73-6d76f6910656` | 72902 | validation_failed；列表摘要，delivery-34 记录 r3 失败 |
| A2 | `0c8a3d8c-ddf0-46eb-84e4-7a3326561e99` | 77128 | validation_failed；invalid_command_payload |
| A4 | `e2e73cb3-c3d8-4758-a97b-3432ca0ca331` | 326505 | validation_failed；invalid_resource_reference |
| A4 | `3b975bc0-0665-4140-a013-140e1aae8492` | 576816 | validation_failed；invalid_command_payload |
| A4 | `902c9636-64f8-4d51-9bfe-dfe476647338` | 598797 | validation_failed；invalid_dependency |
| C1 | `d9e4df97-3d15-4862-bd97-5036aed5bb7a` | 112319 | enum r1，47 个 blocking findings；invalid_command_payload |
| C1 | `a55b9772-c915-4c61-b969-1b02873ad8b1` | 116125 | enum r2，47 个 blocking findings；invalid_command_payload |
| C1 | `6f723a3b-ec70-4e46-9f64-91011902e17d` | 120197 | enum r3，47 个 blocking findings；invalid_command_payload |
| C1 | `f87da3f7-2c65-4a37-ad17-9acecde096dd` | 121057 | enum r4，47 个 blocking findings；invalid_resource_reference |

C1 的 enum r5 后续 validated 并 applied；这是一组计划经历 **4 轮平台失败**，
并非 4 轮 Agent 拒绝或 188 轮失败。

## 5. 提交入口错误和计数交叉检查

| 运行 | completed 原生 staged submit 调用 | 正常回执 dry_run / apply_atomic | 错误返回 |
| --- | ---: | --- | ---: |
| A1 | 12 | 3 / 1 | 8 |
| A2 | 31 | 15 / 12 | 4 |
| A3 | 0 | 0 / 0 | 0 |
| A4 | 33 | 17 / 14 | 2 |
| B1 | 17 | 8 / 7 | 2 |
| C1 | 19 | 10 / 6 | 3 |

这里的 apply 数是正常回执数量，**不是从 `ok=true` 推导成功应用数量**。
尤其不能用 `dry_run 回执数 − apply 回执数` 推导失败数：B1 最后一个 dry-run
没有后续 apply，也不意味着校验失败。A4 的一份历史汇总曾把被拒绝的 apply 转发
也算进成功数量，本记录以原生 completed 结果及 receipt 文件为计数依据。

错误证据行（同上原生事件文件）：

- A1：101632 `staged_l3_unapproved`；114719 `staged_batch_forward_failed`
  （batch_limit_exceeded）；125955 `approval_content_mismatch`；129629、162885
  `staged_submit_schema_mismatch`；160742、163321 `staged_trace_mismatch`；
  167779 `staged_batch_forward_unknown`（batch_content_conflict）。
- A2：68546 `approval_content_mismatch`；85593、96543、96624
  `staged_submit_schema_mismatch`，后两次是 apply 请求。
- A4：597162 dry-run、630634 apply，均 `approval_content_mismatch`。
- B1：96908、97860，均 dry-run `approval_content_mismatch`。
- C1：93042 `approval_content_mismatch`；94558、115694
  `staged_submit_schema_mismatch`，均 dry-run。

复查方法：流式读取 JSONL，仅取 `method=item/completed` 且
`params.item.type=mcpToolCall`；工具名匹配 staged submit 时按调用 ID 去重，
平台 readback 结果递归提取 Attempt 并按 `attempt_id` 去重。
解析优先 `result.structuredContent`，没有时解析 `result.content[].text` JSON。
与 `value-semantics/submission-receipts/receipt-*.json`、deliveries 和 host terminal
record 交叉核对；不从 Agent 的推测性消息认定平台根因。

主代理第二次去重复查结果：112 条 completed staged submit 对应 112 个唯一调用 ID；
六轮唯一 validation_failed Attempt 数依次为 2、3、0、3、0、4，与上表一致。

## 6. 对 R3.0-014 的启示与限制

先把 schema、字段、引用、依赖等技术错误交给平台反馈，再请 Agent 审阅最终翻译，
有机会减少对同一业务候选的机械重复审批；但不能省掉源忠实度、业务边界和翻译完整性审阅。
候选、命令、决定绑定变化仍须使相关 dry-run/审批失效，不能以“已经审过”绕过同内容约束。

六轮使用的提示、配置和终止原因不完全相同，且含中途停止样本；这些数字只是当前样本的
观察值，不是未来每轮失败次数预测。尚未测量换序后的 token、耗时或审阅质量变化；
R3.0-014 后续应在获授权的真实运行中记录这些数据，本次不启动实验。
