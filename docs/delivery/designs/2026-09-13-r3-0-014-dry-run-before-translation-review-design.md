# R3.0-014 物化计划先 dry-run 后翻译审阅 — 交付设计

- 日期：2026-09-13
- 状态（2026-09-14 同步）：`b849fcf` 已实现；D1/D2/D3/D4 设计历史保留，D4 PASS。独立机械结果尚未登记；auth014 有部分真实 L0 宿主记录，未独立复核，完整 L0/L1 未通过。详见 §8。
- 需求：[requirements-v3.0.md 的 R3.0-014](../../requirements/requirements-v3.0.md#r30-014-物化计划先-dry-run-后翻译审阅)
- 关联需求：R3.0-008B、R3.0-009、R3.0-011、R3.0-012；R3.0-013 仍独立登记。
- 共享测试计划：[R3.0-014 共享测试计划](../test-plans/2026-09-13-r3-0-014-dry-run-before-translation-review-test-plan.md)
- 历史统计：[近轮审阅与 dry-run 失败统计](../records/2026-09-13-modeling-review-failure-statistics.md)

## 1. 结论和范围

本需求把物化阶段固定为以下顺序：

```text
Coordinator 批准业务候选语义/拓扑/值表达
        ↓
Protocol 生成并提交物化计划
        ↓
真实平台 dry-run ──技术修正──→ 重新 dry-run（同一 run，可有多个 Attempt）
        ↓ 仅接受平台 Attempt=validated 的事实
Coordinator 审阅最终翻译计划
        ↓
同一候选/计划/内容的 apply_atomic
```

“物化”在这里是把已批准的语义候选翻译成平台 `Modeling Batch`，并在
`apply_atomic` 时写入正式语义资源；它不是把业务表的每一行复制成 RDF 个体。`dry_run` 只编译、
检查并保存 Batch/Attempt 的校验元数据，不应用正式模型资源。

首版只调整启用 `parameters.unified_semantic_graph: true` 的 009 staged Team 提交流程。普通
产品提交、未启用 staged Team 的路径、旧 008B schema 和 R2.3 行为保持原合同；不增加 Reviewer
Agent、平台业务 API、数据库表、文件化批次 API、动态审批框架或上下文压缩机制。首次翻译审阅仍由
Coordinator 承担，业务语义审批职责不移动。

## 2. 实现前入口与关键差距

本节及 §7 引用保留设计时点的代码事实和行号；当前已实现状态见 §8，不能将下列旧缺口
重新当作当前未实现证据。

当前代码已证明 Protocol 通过 Runner 私有能力转发到真实后端，但不能把现有 `ok=true` 当作
平台校验成功：

| 观察点 | 当前证据 | 对本需求的结论 |
| --- | --- | --- |
| staged 入口 | `modeling_team/runner.py:4371-4415` 的 `protocol_staged_submit_modeling_batch` 经 Runner admission；`modeling_team/runner.py:4417-4644` 先做候选/计划/审批检查，再调用 host forwarder | 接线点是现有 Runner capability，不新增 Protocol 直写入口 |
| 009 close 检查 | `runner.py:4492-4507` 两种 mode 都调用 plan/candidate/approval close；`staged_decisions.py:2185-2210` 允许空 translation 列表，但检查已有条目的字段、非空 digest 和 decision=approved | 保留空列表可 dry-run 的基线；解除 rejected/无关格式问题对 dry-run 的误阻断，保留候选/决定绑定 |
| 翻译批准缺口 | `unified_approval_issue`（`staged_decisions.py:2444-2484`）只闭合业务 decisions，不匹配当前 plan 的 translation；旧计划条目只要格式合法且 approved 也不会因此被拒 | apply 必须新增“当前 plan_ref + projection_digest + 当前审批人”的翻译门；不是删除一个现有的 apply 翻译门 |
| 后端真实结果 | `backend/app/services/modeling_batches.py:2964-3020` 返回 `batch_id`、`attempt_id`、`mode`、`attempt_status`、findings 和 workspace 等；`dry_run` 不进入 `_execute` | 成功证据必须绑定真实 Attempt 的 `attempt_status=validated`；`batch_id` 或 receipt 存在不够 |
| forwarder 判定 | `modeling_team/staged_batch_write_forwarder.py:300-325` 当前只要求回复有 `batch_id` | forwarder 要求并保留 Attempt 身份、mode、status；无可识别结果继续走 unknown 对账 |
| 当前 Runner 回执 | `runner.py:4603-4644` 只把 `batch_id`、intent/receipt ordinal 和 `response_digest` 返回为 `ok=true` | 顶层 `ok` 只能表示 capability 回执完成，不能表示 dry-run validated 或 apply 成功 |

顺序改变同时涉及角色工作约定和代码增量：现有角色先申请翻译批准，并不意味着代码已经验证了
这项批准。M1（空 translation 列表可 dry-run）只作基线回归；新增行为由 M2/M6/M7 的 apply
门、M28 的 rejected/无关 translation 不阻断 dry-run，以及真实 Attempt proof 联合证明。
不得以 M1 单项通过声称完成本需求，也不将所有旧计划条目描述成当前必然被拒。

因此，R3.0-014 的“成功 dry-run”定义为：后端返回的同一次 `dry_run` Attempt 可由其
`attempt_id`/`idempotency_key`/`batch_id` 定位，`attempt_status=validated`，且没有 blocking finding；
Runner 将该平台结果绑定到当前不可变计划内容后，才允许进入翻译审阅。`validation_failed`、缺失
Attempt、只收到 receipt 或无法排除 unknown 均不是成功证据。

## 3. 功能合同

### 3.1 dry-run 前保留的门

在 dry-run 之前仍必须满足：

- run、Project、授权 Ontology、Protocol 身份和范围正确；
- 当前候选 revision、Coordinator 业务决定、plan projection 和每个 command 的绑定可闭合；
- `plan_ref` 位于当前 run 的 published materialization-plan 目录，计划字段和 digest 正确；
- 涉及值语义/枚举/L3 的命令仍需有效 `materialization unlock`、对应结论和 trace。当前
  `validate_staged_submission`（`staged_decisions.py:1329-1510`）已有的 unlock/trace 门不因
  dry-run 而移除；
- CQ freeze、现有 staged write admission、无未对账 unknown intent 等既有安全条件仍有效。

不再让翻译审批记录参与 dry-run 放行判断，而非首次开放空审批的 dry-run。dry-run 不以
“尚未由 Coordinator 审阅翻译”作为拒绝理由，也不放宽业务
候选批准、授权、值语义解锁或写入不确定性门。

### 3.2 平台 Attempt 和持久化语义

一次 dry-run 的平台结果必须记录以下最小身份和校验事实（来源只能是 Runner 调用真实后端得到的
结果，不接受 Agent 自报）：

```text
batch_id, attempt_id, client_batch_id, idempotency_key,
mode=dry_run, attempt_status, content_hash,
workspace.before_version, response_digest
```

其中 `content_hash` 由现有后端 `_content(payload)` 产生；首版固定由 forwarder 使用既有
`get_modeling_batch(batch_id)` 读回 Batch 内容及对应 Attempt，不扩展 backend submit response。
它覆盖 `ontology_id` 和按 `client_item_id` 排序后的完整 ModelingItemInput（含
`command_kind`、`payload`、依赖、evidence、rationale、CQ IDs 及其默认值）。它不覆盖 mode、
plan_ref、projection、value traces、lease、idempotency key 或 workspace version。读回必须匹配
submit 返回的 batch/attempt、mode、请求 key 和当前 plan 的规范化 items；不得拿列表中的任意
validated Attempt 或 Protocol 自报摘要代替。读回失败走现有对账，不据此重新提交。

已有响应实际提供的 operation-plan/hash、`delta_hash` 和 findings 用于复核和诊断，不是必须
新造的 proof 字段；apply 不要求复用 dry-run 的
内部 audit id，但必须复用经 projection/content hash 证明的实际命令内容。

dry-run 会持久化 Batch、Attempt、findings、item results、target snapshot、normalized delta、
operation plan 及 hash，并提交数据库事务；它不会调用正式 `_execute`，所以不写 Modeling 资源，
也不创建 EvidenceReference/Association。失败 Attempt 和 Batch 元数据保留；dry-run 校验失败后，
非终态 Batch 可继续接收同内容的新 Attempt，但 apply 已将 Batch 置为 failed 的情况按 §3.4
恢复，不能笼统认为任何失败后同 Batch 都能重试 apply。因异常或超时无法确定结果时，
现有 intent unknown/kill-switch/对账流程继续生效；
“可能只写了元数据”也不能当作零写入。

### 3.3 计划、审批和阶段转换

1. Protocol 根据已批准候选生成 plan。当前 projection 是实际 batch item 的完整投影，含默认值；
   execution parameters 不进入 projection digest。
2. Runner 重新读取 plan，以实际待转发的 batch 逐字段重建 projection，并闭合候选 revision 与
   当前业务决定。该检查在 dry-run 和 apply 都执行。
   对 approvals 的读取须按用途分开：dry-run 只验证本次候选/业务 decisions 及既有值语义批准，
   不因 translation 列表为空、旧版本、rejected 或无关条目格式问题而拒绝；不得跳过业务决定
   校验来实现放行。整个文件不可读取/解析或业务决定本身不合法，仍返回可恢复的准确错误。
3. dry-run 返回后，Protocol 只修复平台可定位的技术错误并再次 dry-run。若修正触及业务含义、
   候选内容、拓扑、共性关系或值表达，交回责任 Agent，发布新候选/决定或受影响的确认；不得把
   平台错误自动解释为业务批准。
4. 仅当当前计划绑定的真实 Attempt 为 `validated`，Protocol 才请求翻译审阅。Coordinator 审阅
   最终 plan、相关候选/决定和 dry-run findings，检查语义忠实度、覆盖/漏项、额外内容和限定含义；
   纯字段、digest、依赖和权限检查由确定性工具完成。
5. apply 需要当前计划的 approved translation approval，且 approval 精确匹配
   `plan_ref` 和 `projection_digest`；同时必须有同一计划内容的成功 dry-run proof。缺少、过期、
   被拒或只做过形状校验的 translation approval 均拒绝。
   apply 从本 run 当前 approvals artifact 选取该计划的唯一有效决定（不是要求只有一个物理条目）。
   相同 plan_ref/digest、approved_by、decision 的等效记录按一个决定处理，不增加拒绝；
   reason 仅措辞不同不改变批准身份，保留到历史，不作为冲突。相同 plan_ref/digest 出现不同
   decision 或 approved_by 才返回可修复的审批冲突，不采用“找到任一 approved 即通过”。
   `approved_by` 必须等于 Runner
   已解析的本 run Coordinator role ID，并沿用现有 Coordinator-owned 写入/角色隔离边界；
   非当前审批人、外 run 记录或旧角色身份均不能释放 apply，不新增身份/审批服务。
   历史旧计划和 rejected 决定保留在既有历史证据中，不作为当前批准，也不阻断新计划的 dry-run。
   Coordinator 提示明确按 `(plan_ref, projection_digest)` 读—改—写当前
   `value-semantics/approvals/approvals.json`：同值重复批准为 no-op；改变决定则替换该键的当前
   条目，保留其他键，不把同一计划的历次决定追加成多个“当前”条目。
   旧决定的具体载体是 `evidence/deliveries.jsonl`：在既有审批回复内携带该键的 previous/current
   五字段决定（含 reason）及本次关联的 dry-run Attempt；无旧决定时 previous 为空。
   `evidence/app-server-events.jsonl` 保留实际写文件/发送消息的原生事件作为交叉证据，不假定它
   会自动生成 approvals 全文件版本历史。更新后回告失败只补发同一决定，不再次追加批准；
   未留到事件的历史不能声称完整。复用现有 Transport 和单一 Coordinator 写者，不新增事件表、
   审批版本框架或跨文件事务硬门。旧 schema 的只读解析仍保持原合同，新模式不把整份 translation 历史
   当作 dry-run 的审批前置。
6. apply 重新检查当前授权、workspace version、租约、候选/决定和 intent/receipt 完整性，并以
   `mode=apply_atomic`、新的 idempotency key 提交同一 Batch 内容。不得把 dry-run key 重用于
   apply；不得以改变 key 掩盖内容变化。

技术修正后的 Batch 身份规则必须明确：如果平台 `_content` 覆盖的任一内容改变，Protocol 在
发布新 plan 时显式生成新的 `client_batch_id`（例如使用 plan_id/revision 派生的稳定标识），
重新计算含该身份的 projection digest，并使用新的 dry-run/apply key。不能假设现有
`protocol_mechanics` 会随 plan revision 自动更换 ID。旧 Batch/Attempt/receipt 均保留，
在已有 plan 修订说明或 Team delivery 中记录旧/新 plan_ref、client_batch_id 和失败 Attempt 的
替代/重试关系，不新增关联数据库或要求新的通用 supersedes 框架。内容不变的同一次请求重放
沿用原 key；需要在新 workspace 重新校验时，非 failed Batch 的相同内容使用新的 dry-run key；
只有内容不变且 Batch 仍允许 apply，才可以在 dry-run 与 apply 间复用 client_batch_id。
终态 failed 的无副作用恢复是内容未变也须换 Batch 的例外，见 §3.4；M8 必须走通内容修正正例。

无语义内容变化但仅更新执行状态时，复用业务决定；计划内容或候选 revision 变化则需要新计划、
新 dry-run，翻译审批至少重审受影响计划。仅 workspace version 漂移时规则固定如下：

- Protocol 保持候选、plan_ref、plan revision、projection digest、client_batch_id 和命令不变，
  只刷新 expected_workspace_version 和 dry-run key，省略 lease_token 后重新 dry-run。
- 新 dry-run validated 后，Runner 按未改变的 plan/projection、仍有效的业务决定和当前审批人
  确定性复用现有翻译批准，并使用新 Attempt proof；不再让 Coordinator 判断一次“能否复用”。
  然后使用当前 lease 和新的 apply key 执行；旧 proof 不因批准复用而恢复有效。
- 若新 findings 要求改变引用/命令/候选/决定，或批准已被撤回，则不属于纯版本漂移，进入相应
  修正/重审路径。不得为了纯版本漂移顺手发布新 plan_ref；确实发布新计划则必须匹配新的批准。

dry-run 请求不携带 lease_token 并不证明期间没有其他租约持有者，也不能证明漂移是历史运行的
常态；本需求不跨 LLM 审阅持有额外长租约，使用现有版本检查处理这个可发生的情况。

### 3.4 回执、失败和恢复

首版固定在现有 Runner-owned `staged-decisions` host evidence 中追加平台 Attempt 绑定，
通过 intent/receipt ordinal 关联现有回执，不修改旧 receipt schema。这是本地证据增量，
不是新的平台 API；旧 008B/009 记录按原 schema 验证，绝不就地补写新证明。新记录至少保存
上节列出的 Attempt 身份、状态、content hash、workspace 版本和 response digest，以及
plan_ref/projection digest。该新增事件由 Runner 写入，Agent 不能通过计划或消息自报 proof。

状态语义固定如下：

| 层 | 含义 | 是否能推动下一阶段 |
| --- | --- | --- |
| capability `ok=true` | Runner 已接收并写下调用回执 | 不能单独推动任何阶段 |
| platform Attempt `validation_failed` | 后端校验已完成但计划不合法，正式模型未应用 | 可由 Protocol 修正后重试，不是语义审阅失败 |
| platform Attempt `validated` + proof | 当前计划在该 workspace 时点通过平台 dry-run | 才能请求翻译审阅 |
| translation approval approved | Coordinator 认可最终计划的语义翻译 | 与成功 proof 一起才允许 apply |
| apply failed + failed_without_side_effects | 平台已证明本次正式写入未发生或已完成无副作用对账 | 仅在对账闭合后走下述新 Batch 恢复，不当作 applied 或普通 dry-run 失败 |
| apply Attempt `applied`/可核对的终态 | 正式写入已由平台完成并可回读 | 才能报告已物化；仍需独立验收 |
| forwarder/平台 unknown | 结果可能已持久化但身份或终态不明 | 进入既有对账，禁止盲重试/继续写 |

平台拒绝、字段缺失、旧审批、plan drift、workspace drift 返回类型化可修复反馈；不会整 run 永久
死亡。unknown intent、receipt 不匹配、不可读 evidence 继续触发现有写门 kill-switch，直到平台
Batch/Attempt 与本地 intent/receipt 对账闭合。失败轮次、修订和旧证据保留，后续成功不能覆盖。

#### apply 无副作用失败的同 run 恢复

`ModelingBatchService.submit`（`backend/app/services/modeling_batches.py:359-400`）对原 key
重放返回已有终态；对 failed Batch 的新 key apply 返回 `batch_failed`。只换 key 或在原 Batch
上再次 dry-run 都不会将 Batch 重新开放。因此在本 run、同一 Build Session 内使用以下既有通路：

1. 先读回对应 apply Attempt，确认 `attempt_status=failed`、
   `recovery.state=failed_without_side_effects` 且 `recovery.safe_to_retry=true`，并沿现有对账确认
   fence/unknown intent 已解除。不以 `safe_to_retry=true` 单字段、异常文字或 Agent 自报证明
   零写入（recovering 状态也可能返回该布尔值）。仍未知/部分写入时不得换 ID 绕过写门。
2. 修复真实错误后发布新的 plan revision 和 client_batch_id，即使命令内容保持不变；使用新
   dry-run/apply key，绑定新 projection。记录前驱失败 Batch/Attempt/plan 的交接关联，保留原
   终态和回执。不得直接把旧计划的 proof 或批准迁移到新 plan_ref。
3. 新 Batch 重新 dry-run，通过后只审阅该替代计划的差异（命令未变时主要核对身份与重试绑定），
   写入新 plan/ref 对应的翻译批准，再 apply。未变的业务语义无需重新审批；新 Batch 不是
   fresh semantic start，不消耗新的启动轮次。

T0 复核结论：缺口是设计没有交接既有的恢复通路，不是已证明必须重构平台状态机。
`test_apply_failure_recovers_releases_the_fence_and_is_retryable`（后端测试 :1957-2024）已有
“同内容、新 Batch、同 session”正例。failed Batch 不再 apply 的限制不等于 run 永久死亡；
本需求不把这一实现限制提升成业务不变量，也不新增同 Batch 解锁接口或全局移除 failed 守卫。
复用现有终态/幂等/对账通路比本次顺带改所有产品路径的终态合同更小。若实际恢复仍被平台硬门
阻断，按 AGENTS.md 重新对第一阻塞层做 T0，不用新重试计数或更多审批补丁封死 run。

报告追加 `phase=apply` 的失败事件，但归因仍按真实根因使用既有四类：如确定性平台合同拒绝归
platform-contract、存储/网络故障归 runtime/infrastructure；不能仅凭 failed 状态判断模型质量，
也不新增第五种“apply 类”。原始 reason_code、无副作用证明和新旧 Batch 关联必须保留。

## 4. 最小可实施接线

只需要在现有接缝增量接线，具体实现和测试交由后续角色完成：

1. **Runner gate**：在 `runner.py` 的 staged submission close 顺序中区分 dry-run/apply；dry-run
   保留空 translation 的基线并解除已有 translation 记录的误阻断，保留业务 close 检查；apply 新增 current translation
   approval 与成功 dry-run proof。
2. **平台结果投影**：固定使用已有 `get_modeling_batch` 做受控读回，不新增后端响应字段；
   forwarder 要求 `attempt_id`、`mode`、`attempt_status`
   和 `batch_id` 可识别；保留完整 findings 和 workspace 版本。
3. **Runner-owned proof**：`staged-decisions` host evidence 由 Runner 写入
   Attempt proof，并在 apply 前按 plan_ref、projection digest、client batch、content hash、
   dry-run key/status 和 workspace 时点做确定性检查。Agent 不能写 proof，也不能用 response_digest
   猜出 status。
4. **Protocol/Coordinator 提示**：同步 Task/Profile/角色说明和提交入口，明确 Protocol 先真实
   dry-run、只修技术错误、成功后交 Coordinator 翻译审阅；加入纯版本漂移复用、无副作用 apply
   失败的新 Batch 恢复，以及审批按键读—改—写/既有交接留痕；不添加 Reviewer 角色。
5. **回归接线**：补 focused mechanical tests、旧模式 fixtures 和最小真实 platform dry-run/apply
   验收；沿用现有 cleanup、unknown reconciliation、hidden isolation 和独立 L0/L1 记录方式。

不新建通用快照、锁、审计、审批或批次框架；Runner 只复用既有 admission、intent/receipt、
Batch/Attempt 和对账能力。

## 5. 验收标准和边界

### 必须成立

- M1 证明空 translation 的既有 dry-run 行为不退化；增量必须另外证明 rejected/无关 translation
  不阻断 dry-run，以及缺少当前翻译批准的 apply 被新增门拒绝；不能只跑 M1 宣称改动成立。
- dry-run `validated` 与失败、unknown、仅 receipt/`ok=true` 明确区分；成功 proof 绑定当前
  plan projection、candidate/decision、platform Batch content hash 和 workspace 时点。
- 技术修正只审最终计划；业务语义变化回到责任 Agent；翻译错误可以由 Coordinator 退回；同一
  内容的 apply 使用新 key，内容变化遵守 Batch 不可变合同。
- workspace 漂移、旧 approval、伪造摘要、文件改写、schema/mode 混用和 unknown 写入均不能放行。
- 值语义 unlock、权限、CQ freeze、租约、candidate/decision binding 和 hidden isolation 不因
  顺序调整而放松。
- 旧 008B、普通产品路径、旧 009 历史记录和 R2.3 行为不被追溯改写。

### 不在本需求结论内

- dry-run 通过不代表业务语义正确、模型质量 PASS、CQ/SQL/检索验收 PASS；
- receipt 数、修订数、候选 rejected 数不直接等于失败轮数；历史失败以共享统计报告的分类和证据为准；
- 本轮不声称代码已修改、产品测试已通过、平台已重启或真实建模已启动。

## 6. 关键风险假设（最多三项）

1. 现有只读 `get_modeling_batch` 可受控读回 Batch `content_hash` 和指定 Attempt；源码已提供
   该数据，但后续仍须实际验证 forwarder 读回的授权范围和结果关联。
2. 后端 `attempt_status`、`attempt_id`、workspace 版本和 findings 是真实 Attempt 的权威结果；
   Runner 必须按这些字段判定，不能把 Protocol/forwarder 自报摘要当作成功。
3. 非 failed Batch 的 dry-run/apply 可复用不可变内容/client_batch_id，但必须使用不同的 key；
   纯版本漂移保持 plan 身份重校验，已证明无副作用的 failed Batch 按 §3.4 换新 Batch 恢复。

## 7. 源码与合同附录

- `modeling_team/runner.py:4417-4644`：现有唯一 staged submit 入口、计划/候选/审批 close、先写
  intent 后转发、按 `batch_id` 写 receipt。
- `modeling_team/staged_decisions.py:1329-1510`：unlock、value trace、L3 和 materialization
  前置门；该门在两种 mode 都保留。
- `modeling_team/staged_decisions.py:1589-1670`：canonical command digest、intent/receipt
  字段和 009 plan/projection bindings；当前 receipt 不含平台 Attempt status。
- `modeling_team/staged_decisions.py:2220-2418`：plan projection digest、实际 batch 重建和
  candidate close；execution parameters 不进 projection digest。
- `modeling_team/staged_decisions.py:2514-2635`：旧/009 schema dispatch、receipt-intent
  cross-check、unknown intent kill-switch。
- `modeling_team/staged_batch_write_forwarder.py:300-325`：当前只要求 `batch_id`，需补 Attempt
  结果完整性。
- `backend/app/services/modeling_batches.py:2964-3020`：平台 Attempt response 已含 status、
  findings、workspace 等；`dry_run` 只落元数据，不进入 `_execute`。
- `backend/app/services/modeling_batches.py:370-575`：Batch content hash、request hash、
  idempotency、workspace 和 lease 规则。
- `modeling_team/references/r3-0-009-unified-graph-contract.json`：009 的候选/决定/plan、
  translation approval、projection digest、唯一写者和旧 schema 隔离合同。

## 8. 2026-09-14 交付状态同步

`b849fcf` 已包含 Runner、staged forwarder、计划/审批/proof 合同与测试代码。当前共享计划
尚未登记独立机械执行轮；存在测试文件不能证明已执行或独立通过。原设计 D4 PASS 保留。

auth014 宿主账本记录 L0-1/2/3/4/6 的真实路径取证，L0-5 unknown 未触发、L1 未完成。
本轮没有逐项复核原事件，故仅记录部分真实 L0 的宿主报告，不宣布完整 L0 或语义质量 PASS。
[状态核对依据](../records/2026-09-14-r3-0-015-review-evidence.md#4-012014-状态核对依据)
保留来源与限制。本次仅同步文档，不运行测试、重启服务或追加 semantic start。
