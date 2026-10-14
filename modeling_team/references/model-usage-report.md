# Host 整轮模型用量报告（R4.3-019）

权威范围：[需求](../../docs/requirements/requirements-v4.3.md#r4-3-019)、
[设计](../../docs/delivery/designs/2026-10-14-r4-3-019-model-usage-reconciliation-design.md)。
工具离线读取显式原件，不调用模型、不读取凭据、不改变 run 或授权。报告和 scope
保存在 gitignored Host 私有目录，不作为生产角色或独立盲测输入。

```sh
python -m modeling_team.usage_report \
  --scope workspaces/usage-audit/scope.json \
  --output-dir workspaces/usage-audit/report-1
```

输出目录必须尚不存在。生成 `report.json` 与同一归一化结果渲染的 `report.md`；
文件权限0600、目录0700。相同 scope 与冻结字节可重复得到完全相同的两份报告。
输入变动时另选目录；原件和旧报告不会被覆盖。

## 最小 scope

路径相对 scope 文件目录解析，`path` 必须在声明的 `root` 内。工具不递归扫描目录；
逐个列出获准原件。`evidence_ref` 指实际绑定证据，目录名或时间相近不能替代绑定。
下面演示一个显式规范回执输入；真实任务需补齐实际发生的所有层和原件，不能复制
示例的完整性声明。

```json
{
  "schema_version": "model-usage-scope/v1",
  "task_ref": "task-A",
  "code_revision": "actual-commit",
  "config_refs": ["actual-profile-reference"],
  "inventory_complete": false,
  "task_window": {
    "start": "2026-10-14T00:00:00+00:00",
    "end": "2026-10-15T00:00:00+00:00",
    "timezone": "UTC",
    "start_source": "authorization-record",
    "end_source": "observation-cutoff",
    "complete_independent_pass": false
  },
  "sources": [{
    "id": "delivery-receipts", "root": ".", "path": "receipts.jsonl",
    "kind": "receipts", "byte_offset": 0, "byte_length": 1024
  }],
  "bindings": [{
    "source_id": "delivery-receipts", "evidence_ref": "session.json#native_thread_id",
    "task_ref": "task-A", "session_id": "delivery-A", "run_id": "run-A",
    "operation_id": "operation-A", "round": 1,
    "thread_id": "real-thread-id", "role": "delivery", "phase": "supervision",
    "provider": "provider-A", "account_ref": "account-A", "key_ref": "modeling-key-A",
    "requested_model": "exact-requested-model",
    "requested_effort": "high", "effective_effort": "high",
    "usage_definition_ref": "provider-input-includes-cache-output-includes-reasoning"
  }],
  "layer_coverage": [
    {"role": "delivery", "status": "partial", "evidence_ref": "session.json"},
    {"role": "consumer", "status": "not_invoked", "evidence_ref": "operation-log"},
    {"role": "scoring", "status": "unknown", "evidence_ref": "reranker-invoked"}
  ]
}
```

`byte_length` 应为实际冻结前缀长度；省略时本次读取的字节自动冻结并记录长度／SHA256。
范围截断或从半行开始会披露定位，完整安全行继续计算。保留跨来源的真实字节偏移，
不使用重新编号的行号。为稳定复算，应把第一次实际读取长度写入下一次 scope。
`key_ref` 仅为非秘密别名，不使用 Key、摘要、片段或凭据路径；别名不能证明账单筛选。
`actual_model` 只能由实际返回或执行证据提供，不能直接把 requested_model 复制为实际模型。

## 支持的原件与绑定

| kind | 可读内容 |
| --- | --- |
| `rollout` | Codex JSONL `session_meta`、`turn_context`、`token_usage_record`、`compacted.compaction_response_id`、累计 `event_msg/token_count` |
| `app_server` | JSONL `thread/tokenUsage/updated` 的 thread/turn 与 total |
| `capture` | 本次 Delivery `thread_usage` 及代理 `attempt_start`／`attempt_end` 白名单记录 |
| `receipts` | 显式规范化逐响应或线程累计 JSONL，结构见下方 |
| `timing` | 真实唯一绑定的请求／头后／首输出／turn 时间回执 |
| `metrics` | 当前仅披露不能直接当逐响应 usage／provider TTFT 的缺口，不转换 Examiner ttft_ms |

未知 kind、坏行、缺文件及结构错误保留安全小计与限制，不补零。复制响应按
(provider,key_ref,response_id)合并来源。缺response_id时仅接受带
`unique_request_evidence_ref` 的真实request_id；其他情况保留 ambiguous，不能安全求和。
同身份字段数值冲突置该字段 unknown，其他一致字段仍保留，不任取一个值。

binding 可以使用 `response_ids` 或半开 `window` 切分共享线程；
`shared_thread: true` 且没有切片证据时，该用量单列 unallocated。
多个匹配 binding 不猜一个；复制来源归属 task 冲突也转 unallocated。
恢复保持真实thread身份，新的目录不产生新费用。未绑定源会显示缺口。

规范 `receipts` 每行的局部结构为：

```json
{"source_mode":"response","response_id":"real-response-id","thread_id":"real-thread-id","turn_id":"real-turn-id","timestamp":"2026-10-14T01:00:00Z","actual_model":"returned-model","status":"completed","usage":{"input_tokens":100,"cached_input_tokens":60,"output_tokens":20,"reasoning_output_tokens":5}}
```

也接受原数值 camelCase 字段，以及 `cache_write_input_tokens`。input包含cached，
reasoning_output是output子集；未知字段为null，估算字节／context窗口不进入usage。
`usage_definition_ref` 说明实际provider定义；账单要求与导入值定义一致。
请求开始或结算时间口径可附 `request_started_at`／`settled_at`，必须同时有真实唯一
`billing_time_evidence_ref`；否则不能把完成时间当开始或结算时间。

## 累计、压缩与未知

线程累计行使用 `source_mode: thread_cumulative`、thread_id、timestamp及usage。
默认只展示 `observed_thread_totals`，不与响应相加。只有binding中的
`cumulative_segment` 提供以下证据，才核算连续段增量：

```json
{
  "id": "continuous-segment-1", "evidence_ref": "actual-start-end-snapshots",
  "start": "2026-10-14T00:00:00Z", "end": "2026-10-14T02:00:00Z",
  "baseline": {"input_tokens":1000,"cached_input_tokens":600,"output_tokens":200,"reasoning_output_tokens":40},
  "includes_response_ids": ["real-response-id"]
}
```

只有确实fresh且有零基线证据时用 `fresh_zero_baseline: true`。继承、缺基线、下降或
不同来源累计序列不齐保持unknown。相同窗口、配置与包含关系被证明时取累计总量，
响应只作明细，残差标 `unitemized_residual`；未证明的重叠不相加。重叠累计段不会双算。
仅真实compaction_response_id绑定的用量进入 `compaction_subset`，作为总量子集。

`usage_status`、`attribution_status`、`timing_status`、`billing_status` 分开。
`inventory_complete` 只应在清单确实闭合时设置；缺调用、角色、辅助模型或字段仍披露
partial／unknown。not_invoked需要证据，已发生但无usage的attempt不能解释为零费用。
缓存命中率只用input/cached均已知的样本，并列样本输入覆盖；不能外推完整任务。

## 显式价格与双视图对账

`price_versions` 为数组。每项必须有provider、model、version、source_ref、verified_at、
币种、unit_tokens、半开start/end、definition_ref、`billing_mode: api`及rates。
rates显式指定已确认的计费类别，例如cached_input_tokens、uncached_input_tokens、
output_tokens；缓存写入／推理的计费定义也由真实价表决定，工具不套用其他provider公式。
金额用Decimal。订阅、缺价、跨价格段无法切片或缺必要token时金额unknown。
可选rounding_quantum仅支持十进制精度，须显式声明rounding_mode
（ROUND_HALF_UP、ROUND_HALF_EVEN、ROUND_DOWN、ROUND_UP），按每成本单元舍入。
不提供舍入时保留精确值，不使用隐含容差或汇率。

可选 `billing_scope` 独立于任务窗口，包含provider/account_ref/key_ref/model、
start/end（半开）、timezone、time_basis（usage_completion／request_start／settlement）、
definition_ref、source_ref、key_binding_evidence_ref、inventory_complete及vendor_usage。
目标任务、已证other_task、unallocated分别列出。未提供其他源时保留
outside_inventory_unknown；不猜客户端或扣费原因。

比较输出为vendor−local_matched，允许正负。范围或字段缺口只有raw_difference，
不能偶然相等就MATCHED。token_status与归属状态分开；金额也单独比较。
金额提供vendor_amount／currency；只有amount_rule_ref说明税／折扣／舍入规则，且
price_version_refs与实际估价版本一致时才判断金额MATCHED/MISMATCH，否则保留PARTIAL。
缺响应、供应商时区或细分时整体仍PARTIAL。attempt元数据不证明已收费或账单差额原因；
`attempt_usage_binding_evidence_ref` 只能引用已逐项核对所有attempt的真实证据。

## 吞吐与采集边界

`timing` 行包含provider/key_ref、response_id（turn另有thread_id/turn_id）、kind、
start/end、start_source/end_source、binding_evidence_ref、status及可比较clock_ref。
kind为request_completion、after_headers、generation、agent_turn。generation的start
必须是真实首输出，不能用首网络字节、工具输出或Examiner ttft_ms代替。

相同响应的冲突计时不任选。缺计时样本计入unknown；无唯一绑定不能从时间相近拼接。
成功、失败、中止和状态不明分开。报告给出Σoutput/Σduration、同一时钟的区间并集速率、
可算输出及完整性足够时的输出覆盖。output已含推理，不再相加或声称可见文本速度。
turn速率包含工具与等待，线程累计不能切turn就不算。墙钟为授权开始至完整独立PASS
及收尾，未PASS只报cutoff已耗时，不因修模重置。

Delivery将thread/tokenUsage数值保存到native/usage-events.jsonl，不进入模型通知。
实际operation/role通过usage_context传入；没有上下文不根据类名猜角色。
Delivery代理记录native/provider-attempts.jsonl；生产run记录evidence/provider-attempts.jsonl；
无run的独立evaluation记录workspaces/usage-receipts/<adapter-session>/evidence/。
共享代理没有可证明的role/thread时留null。每次上游attempt在发送前留start，结束留固定
状态／HTTP数值／end；异常退出留下unfinished。没有response唯一绑定，不与rollout
拼API吞吐。采集缺失或异常只记录固定usage_capture_incomplete，不能改变重试、字节转发、
工具权限、run状态或验收。新工具不关闭历史8,717,117差额，真实账单仍需另行获准验证。
