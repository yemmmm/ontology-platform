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

## R4.4-002 任务金额预算（Host入口）

金额预算是任务资源授权和近实时估价投影，不能替代本页的用量原件、账单核对、应用完整性
或独立语义验收。新授权必须由 Host／用户写入稳定 `budget_ref`、显式
`resource_authorization.mode=amount`、真实 `authorization_reference`、任务范围和冻结价表；
Delivery、生产 Agent、Consumer／Judge 只能读取获准投影，不能创建、追加、改价或借余额扩大
业务目标、模型绑定、写入权限或验收范围。历史 `authorize-budget --additional-starts`
继续是次数授权，不能把旧次数余额猜测转换成金额。

Host CLI提供以下入口；命令只读配置／预算文件或更新 Host-owned 预算，不启动模型：

```sh
python -m modeling_team task-budget create \
  --ref workspaces/delivery-sessions/<session>/cost-budget \
  --config workspaces/host-authorizations/task-budget.json
python -m modeling_team task-budget add \
  --ref workspaces/delivery-sessions/<session>/cost-budget \
  --config workspaces/host-authorizations/task-budget-add.json
python -m modeling_team task-budget show \
  --ref workspaces/delivery-sessions/<session>/cost-budget --audience host
```

`create`／`add` 的结构化配置须包含真实用户授权引用；价表和金额由 Host冻结并由预算核心
校验。`show --audience host`返回完整获准投影，`delivery`只返回流程所需的额度、计量和控制
状态。预算估价采用三类归一化 token 桶和 Decimal 累计，缺测／暂估／在途／范围外调用仍
单独标记；它不代表供应商账单，也不改变本页离线报告的 `PARTIAL`／`UNKNOWN` 边界。

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
| `batch_report` | 完整 batch-report.json 中 Consumer task 的线程绑定及 model_usage 数值快照；不投影题目、答案或评分正文 |
| `activity` | R4.3-036 的数值化 launch／bind／exit、LLM／工具起止及明确暂停／等待；独立于旧 numeric capture 事件合同 |

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

### Consumer 终态用量核对

Host收尾时在同一scope逐个列出原`batch-report.json`（`kind: batch_report`）及实际
绑定线程的最终保留rollout（`kind: rollout`），继续使用上方离线命令生成独立报告。
每个batch源可按各task的`model_usage.fresh_thread_id`提供多个binding；每个binding
仍须有实际线程归属证据、provider／非秘密key_ref、任务及角色，不能按目录或时间猜配。
batch源须完整JSON；不将分段JSON当完整报告。原语义报告、digest和裁决不修改。

工具按(task_ref, provider, key_ref, thread_id)关联已绑定响应／累计用量，输出
`consumer_snapshot_comparisons`和Markdown差异表；快照只作核对，不与同线程记录相加。
因此报告快照早于最后响应时，末段用量来自保留的真实记录。原生回执仍按既有response_id
去重／累计基线规则处理；不同来源的归属冲突、数值下降或原件不齐继续披露限制。

缺原生记录时，仅有`fresh_thread: true`及数值增量的快照可作为partial小计，重复副本不
重复累计；冲突字段为unknown。没有fresh基线或实际线程绑定则不计入任务。快照不作为
最终账单匹配值，`metrics_complete`也不能证明用量已到最终截点。TTFT及其他metrics
完整性保持原合同。此核对不调用模型、不阻塞建模、不等待账单，也不为统计重启运行。

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

<a id="dsh-usage"></a>

## R4.3-034：DSH数值原件与混合scope

Messages代理在原有转发路径保留逐请求`attempt_start`、`response_usage`及`attempt_end`，
每次实际请求一个独立request_id，失败／重试压缩也保留。生产为
`<run>/evidence/dsh-provider.jsonl`，Delivery为`<session>/native/dsh-provider.jsonl`，
Consumer／Judge为`<attempt>/acceptance-runtime/<instance>/evidence/dsh-provider.jsonl`。
新文件0600、父目录0700。只保存白名单身份、时刻、状态、字段presence和数值，
不保存正文、推理、凭据、Key摘要或自由错误文本；采集失败不阻断流、不重发请求。
每帧最多256 KiB，超限停止本请求的数值观察；1024项有界异步队列隔离采集写入，
队列满／写入失败只记计量缺口，原字节继续转发。收尾最多等待1秒刷新，不等待账单。

Host在允许模型输入前把真实原生session注册到该代理。生产绑定run／role／进程代次，
Delivery绑定业务session／role／代次，验收绑定run／batch／role／代次；batch_id不是
operation_id。task_ref、operation_id、round及provider账户／非秘密key_ref仍由scope中的
真实Host记录补齐，不从目录／时间推断。缺任何绑定须保留unknown／unallocated，不能
把DSH session塞进thread_id。恢复时注册同一原生session的新代次，旧请求保持原归属；
新session另列，不清空旧历史。注册或采集都不授予建模／验收权限。

- `kind: dsh_capture`（`capture`也兼容）读取上述数值原件；同一scope可并列Codex来源。
- `kind: dsh_native`读取Host的`session.event` wire或原生session JSONL。wire内取实际
  sessionId；直接持久文件须在source上给实际`runtime_session_id`，由baseline证据绑定。
  按session＋seq去重，保留真实毫秒时间；只投影数字，不复制assistant正文／题目／答案。
- bindings新增`runtime: dsh`、`runtime_session_id`、可选`process_instance`，共享代理
  按实际session匹配。既有Codex thread映射为`(codex, thread_id)`，原口径不变。
- `usage_definition_ref`必须引用已经核对的provider／adapter字段定义。capture中的
  `adapter_definition_ref`只说明固定DSH源码映射，不是供应商账单验证。缺定义不派生
  总输入。当前定义标识为`usage_semantics: dsh-exclusive-input/v1`。

DSH原始桶U=`input_tokens`、R=`cache_read_input_tokens`、W=`cache_creation_input_tokens`。
统一input=U+R+W，cached=R，uncached=U+W，W仍单列。40／60／5应得105／60／45，
不能把缓存再加一遍。缺任一输入桶不派生input／uncached，显式0保留；Harness默认零
不能替代provider presence。message_start的output=0不作最终输出，必须有终结delta
及message_stop；中断数值只能作partial小计。reasoning（若实际提供）属于output子集。
逐响应保留原桶、presence、字段事件位置、定义、来源偏移及完整性，JSON／Markdown同源。

provider response_id优先去重。无ID仅在具有实际Host注册证据及唯一单次request_id时
使用该请求身份，provider request-id响应头另列，不能当response_id。副本合并定位，
同ID数值冲突字段unknown。原生attempt／message按同turn／step替换，retry-started后
另计；普通assistant与成功summary只核对provider主账，不能相加。缺provider原件时
原生小计仅为`partial_dsh_native`，不进入完整账单MATCHED。失败压缩即使无summary，
仍按代理compact标记计入主账和非加性的compaction_subset。

需要读取已冻结TokenUsageProjection时，可显式提供`kind: receipts`、
`source_mode: dsh_assistant_cumulative`、runtime/session、timestamp、usage_semantics及
`raw_usage`（实际`uncachedInputTokens`／`cacheReadTokens`／`cacheWriteTokens`／
`outputTokens`）。binding沿019提供统一口径baseline及连续段证据，缺基线不求delta；
只核对普通assistant子集，不替代含压缩的provider总量。无provider或逐事件记录才可
列partial累计替代小计；不与同session其他来源相加。

DSH价表须与回执的definition_ref一致。独立提供cache_write_tokens费率时，普通未缓存
收费基数减去W；只提供未缓存费率时按U+W计价，不再叠加W。缺定义／必要字段金额
unknown，不预置价格。请求完成及headers后速率只用实际回执与唯一响应绑定；没有
真实首输出时间则generation速率unknown，不能从可见推理字数换算token。

完整任务仍须列Host／辅助模型、失败、恢复、修模、Consumer末段及收尾原件；报告的
已知小计不等于清单闭合、全链DSH、等质净降耗或费用对账。真实所选链覆盖与对照使用
[034开发测试记录](../../docs/delivery/records/2026-10-18-r4-3-034-implementation-test-record.md)
的分阶段清单；没有真实L0／独立L1前不改变新任务标准默认。旧省略runtime=codex、
显式Codex及历史读取继续有效，旧run不热切、不盲重放，不因统计追加start或修模轮次。

<a id="team-close-statistics"></a>

## Team 关闭统计（R4.3-036）

[需求](../../docs/requirements/requirements-v4.3.md#r4-3-036)及
[设计](../../docs/delivery/designs/2026-10-19-r4-3-036-team-close-statistics-design.md)
在现有账本上增加数值活动来源和原 owner 收尾接线，不产生模型调用。

- run：`TeamRunner.cleanup` 在运行时／验收及资源收尾后发布 `run_close`；原清理回执、
  `get_run_status` 和 `get_request_result` 附 `close_statistics`，不改变请求 outcome。
- 独立 CQ：原 `EvaluationOwner` 关闭后发布 `operation_close`；公开反馈在自己的收尾
  分支发布同一视图。`get_evaluation_status` 返回 operation 自己的报告引用。
  公开反馈的 `--statistics-root` 仅指定数值报告目录，不创建或接入验收 owner。
- Delivery：`runtime.close()`、`native_runtime_closed` 及 provider flush 后，程序发布
  `task_close`，追加 `close_statistics_ready`（失败为 `close_statistics_unavailable`），
  更新原 session／conversation 状态。早期 stopped／standby 不是统计冻结点。

每个报告根的 `evidence/close-statistics.json` 是只读查询指针，包含
`schema_version: team-close-statistics/v1`、`view`、`closure_status`、`report_status`、
`coverage_status`、`cutoff_at`、`summary`、`report_ref`、`markdown_ref`、`scope_ref` 和
固定限制码。路径相对该根，不是模型可选择的任意路径；不注入生产或盲测材料。
`closed`、`ready` 和覆盖是否完整分别判断。无收尾指针的强杀／历史 run 返回
`unknown/unavailable`，不在状态查询里重新解析日志或编造关闭时间。

`statistics-members.jsonl` 记录实际 launch 实例及已注册原件，`statistics-links.jsonl`
只连接实际 run／operation／业务 session 账本绑定的根，`activity.jsonl` 只含数值事件。
三者均在 Host 私有 `evidence/close-statistics-capture/` 子目录，Codex 新数值 usage 也
放在这里，避开默认 run 进度事件流；`host/activity` 通知不重复写进 DSH wire。
无原生身份的启动失败保留唯一 process instance，
不会变成伪 Codex thread 或 DSH session。恢复原 session 的新进程另列；生命周期相加，
跨代次跨度和离线间隔另列；没有退出时刻证据就保持时长 unknown。

统计含逐成员表、角色／runtime／精确模型及 effort 分组、各字段覆盖、已知 token 份额
及分母、配对样本加权缓存率、实际请求／attempt、失败／取消／unfinished、根工具耗时
Top 5、压缩子集、明确暂停及清理状态。run 的 `members` 只包含本 run 及关联子任务；
`task_cutoff_members` 是同一任务截至 cutoff 的其他已绑定成员，含仍在线 Delivery。
两者不能混成 run 已退出人数。缺 Host／辅助来源仍披露 unknown。

时间口径：

| 字段 | 数值含义 |
| --- | --- |
| `llm_request_seconds` | 已观察上游 attempt 起止累计，包括失败／重试、传输、排队和流式传输 |
| `tool_execution_seconds` | 已观察根工具进入实际执行／委托边界到返回，排除调度前排队和按序提交结果等待 |
| `active_seconds` | 同一 Agent 的 LLM 与根工具区间并集；summary 是累计 Agent 小计 |
| `team_active_seconds` | 可比较成员区间的并集，不能用累计 Agent 时间替代 |
| `lifecycle_seconds` | launch 至确认 exit；未退出为 null，另返截至 cutoff 的 elapsed |
| `wall_clock_seconds` | run 的原 Host 启动记录至收尾，或任务首次已注册 launch 至 cutoff；basis 单列 |

Linux Node `process.hrtime.bigint()` 与 Python `monotonic_ns()` 以 boot 绑定的
`clock_ref` 比较；不混用进程相对时钟。不可比、倒退、冲突、截断与缺边界保留定位，
unfinished 下界不计入完成耗时。`other_or_uncovered_seconds` 不是推断的 idle／等待。
工具内 sleep／长轮询属于工具执行；活动时间不代表有效语义工时。

| 路径 | 可观察边界及限制 |
| --- | --- |
| DSH 生产、Delivery、Consumer、Judge | 共用固定 Harness `tools/execute` 观察器，记录 rootCallId／callId；prepare 拒绝单列，嵌套调用不重复加总；Messages 代理记录独立 attempt 及 usage |
| Codex Delivery | Host 动态 tool handler 的实际委托边界，原生 thread 累计 usage 及关闭前末段 |
| Codex 生产 | Host 动态工具、受控 Modeling read proxy 及 role capability 服务端 handler；其他原生工具边界保持 unknown |
| Codex Consumer／Judge | 独立实例生命周期、native usage、受控读取代理 handler；未代理的报告／原生工具边界保持 unknown |
| Codex 外部代理／订阅 | 已有 Responses 代理记录实际 attempt；共享源按实际 adapter session 过滤，不能分配到 Agent 的时间在 unallocated 中单列；订阅内部请求时间 unknown |

报告先在私有临时目录完成冻结来源副本、scope、JSON 和 Markdown，再原子发布目录／
指针。两份报告完整才 ready。相同来源快照重复关闭不重复累加；迟到数值生成新版本，
链接旧版，失败也不改旧文件。scope 保存字节长度、SHA256、绑定与配置摘要；
`sources/…` 相对该 scope 目录，沿本页原离线命令可复算。报告失败只返回固定
`close_statistics_generation_failed`，不替代原 stop／清理结果，也不启动任何 Agent。

无完整价表时金额 unknown。工程 fixture 的 PASS 不证明真实全链统计覆盖、独立 L1、
降耗或费用对账；真实 A9 须另有有效授权，见
[实现测试记录](../../docs/delivery/records/2026-10-19-r4-3-036-implementation-test-record.md)。
