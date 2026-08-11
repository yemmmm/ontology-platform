# R2.3-003 Existing-scope 增量建模设计

- 状态：同步瘦身、Carrier、context fence 与 native translator bridge 均已实现并回归 PASS；新授权
  `user-20260812-r23003-post-translation-bridge-start1-3` 将 cap 扩至 20。start19 已完成 durable Phase A，
  但合并双目标删除在 dry-run 被 `conflicting_item_effects` 阻断；当前 cap/count/active=`20/18/0`，
  两个 unknown 未删除，剩余两次授权。Phase B 已改为两个有序单目标 delete-only Batch，后续 run 复用
  start19 的四个 Phase-A 实体并以 8-item continuation 完成删除、readback 与 N-CQ
- 权威需求：`docs/requirements/requirements-v2.3.md#R2.3-003-已有-projectontology-增量建模`
- 交付记录：
  `docs/delivery/records/2026-08-11-r2-3-003-existing-scope-incremental-modeling-delivery-record.md`
- Source bundle：
  `docs/evaluation-scenarios/ontology-modeling-team-r2-3-003/agent-input/manifest.json`
- 更新日期：2026-08-12

## 1. 目标

使用一个全新的正式四角色 Modeling Team，通过 `existing` 模式连接 R2.3-005 Start75 保留的非空
Project/Ontology，只依赖当前平台事实、非敏感 scope handoff 和批准 source bundle 完成一次真实增量
建模。增量结果同时：

1. 解析 Start75 已建模的两个 `ExplicitUnknown`，写入当前结论与新 Evidence 后原子硬删除这两个资源；
2. 新增一个 C evaluation -> B publishability decision -> A publication outcome 业务切片；
3. 保持 Start75 既有版本、输出、调用和发布关系正确且可查询；
4. 在同一最终 model state 上通过 validation、reasoning、governed retrieval 和 standard 声明的全部 N 条独立 CQ。

## 2. 非目标

- 不恢复 Start75 Agent Session、Prompt、旧 verdict 或本地运行目录；
- 除两个目标 `ExplicitUnknown` 及其级联关系外，不复制、删除、重建或覆盖 Start75 本体；
- 不把 Dify、Workflow、Decision、Publication 等业务概念加入平台生产域；
- 不建设通用多需求编排、长期 Project 生命周期、自动回滚、并发写入或 Pi Adapter；
- 不建模普通 numeric score 阈值、其他 diagnostic、人工 review 后续或更多案例；
- 不新增或借用未授权的 semantic start；2026-08-12 精确 `+3` 已由 start16–start18 耗尽，
  任何后续 live run 必须获得新授权。

## 3. 功能合同

### 3.1 基线与启动

正式输入绑定 Start75 Project `7fc146d8-c76f-417b-9314-854544f269fc`、Ontology
`fd762f52-2f5e-4bc0-902a-5583135ab64d` 和一个不可变、非敏感 handoff。任何 Agent 启动、账本 reserve、
Build Session/Lease 或平台写入前，Runner 必须：

1. 验证 clean checkout、Task/Profile/model manifest/source manifest digest；
2. 通过授权平台读取重新确认 Project/Ontology 归属、Ontology 状态、默认 Graph Set、workspace version、
   没有 active Build Session/Lease 或 in-flight Attempt；
3. 将 live workspace version 与 handoff 比较；不一致时零副作用失败，不自动改写 handoff；
4. 确认本需求专属 StartLedger 严格回放，不修改历史授权/终态；当前 59 条记录的
   cap/count/active 精确为 `17/17/0`，最后一次 `+3` 授权已由 start16–start18 耗尽。

### 3.2 Agent 输入边界

- Coordinator 只得到目标、roster、CQ/验收标准和非敏感 scope identity，不得到 raw business sources；
- Modeling 得到旧批准业务资料、两个新增 source 文档，以及一个独立、project-scoped、read-only、运行期
  临时 credential。其 ontology-platform allowlist 精确为 `get_modeling_context`、
  `get_ontology_read_model`、`query_semantic_context`：首个 candidate 前必须先调用
  `get_modeling_context(ontology_id=O)`，确认 Project/Ontology、ready workspace、workspace version 且无
  active recovery/issues，并使用其 query entries 按需读取 `classes`、`entities`、`facts`、`rules` 或业务相关语义
  邻域。Modeling 不读取完整历史 Batch 来重放状态，不接收平台写工具，不持有 Protocol/model/admin key，
  不创建 Build Session/Lease/Batch，也不执行 validation/reasoning mutation；
- Protocol 得到平台 mechanics、当前 scope、Modeling 的完整增量 candidate 和必要只读/写工具；
- Acceptance 得到冻结 handoff 与验收标准；每条 CQ 的 Source/Platform Examiner 仍按 R2.3-005 的
  fresh、隔离、只读边界创建和回收；
- 任一角色都不得看到 Start75 Agent 对话、旧答案、旧 verdict 或 tester-only 内容。

Modeling Context 是当前状态的概览和详细查询入口，不替代固定 semantic read models。Modeling candidate
继续保持 platform-neutral，不携带 IRI、平台 credential、Batch ID 或 workspace internals；Runner 通过
role-scoped MCP call evidence 证明 Modeling 确实完成了要求的只读入口调用。Protocol 收到 candidate 后
独立调用 Modeling Context/read model，并在任何 Build Session/Lease/write 前确认 workspace version 未从
Modeling 的观察版本漂移；漂移时返回零 mutation conflict，要求 Modeling 基于新状态提交完整 revision。
Modeling read credential 在角色终态或 run cleanup 时撤销，plaintext secret 必须销毁并进入 aggregate
secret/residue audit。

上述“精确三工具”必须是机械边界，不依赖 Prompt、Codex `enabled_tools` 或 backend project ownership
单独保证。Runner 在 existing live preflight 成功后、Modeling 首轮前创建一个 formal R2.3-003-only
`ModelingReadContext`：

1. Runner-owned key lifecycle 使用 PlatformScope admin API 创建独立 project-scoped `read` key；持久状态只含
   key ID/digest、P/O、run ID、创建/revoke receipt，plaintext 仅在 Host process memory 中交给本地
   Modeling read proxy，不写入 Agent home、环境、prompt、artifact 或日志。不得复用 Protocol model key、
   Acceptance child key 或通用 admin key；
2. Runner-owned local proxy 只注册三个 MCP tool，并在转发 backend 前验证工具和参数：
   `get_modeling_context` 只接受 exact O；`get_ontology_read_model` 只接受 exact O 且 model_name 属于
   `classes|entities|facts|rules`；`query_semantic_context` 只接受 exact P、`scope_mode=ontologies`、
   `ontology_ids=[O]`，cursor continuation 仍绑定同一初始 scope。任何其他 tool、同 Project 的其他
   Ontology、history/delta、空/全 Project scope、写/validation/reasoning 调用都在 proxy 前置拒绝，不发送
   backend 请求；
3. 该 proxy 可抽取/复用现有 Acceptance read-key/forwarder 的通用 credential、MCP forwarding、revoke 与
   secret-audit mechanics，但必须有 Modeling 专属 exact-three-tool policy/state；不得直接套用 Acceptance
   `ScopedReadProxy` 的 validation/reasoning/ticket 假设；
4. Modeling completed/blocked、Runner abort 或正常 cleanup 均停止 proxy，revoke key、admin readback
   `revoked_at`，再用旧 plaintext 证明 401/403；最后清除 plaintext并把 socket/thread/process/secret scan
   汇入 aggregate cleanup。任何 revoke/readback/denial/secret cleanup 失败都使 run cleanup FAIL。

Runner 同时维护 requirement-private `ModelingContextGate`，初始为 closed。只有 Modeling 通过 proxy 成功
调用 exact-O `get_modeling_context`，且 Host 校验 response `ok=true`、P/O 一致、workspace ready、非空
workspace_version、resource counts 合法、无 issues/active recovery 后，才写一个 immutable receipt（run、P/O、
workspace version、canonical response digest、proxy call receipt digest）并转为 `context_observed`。Detailed
read calls 只能在该入口成功后执行。Modeling 通过 direct Team Transport 或 staged-candidate capability 向
Protocol 发布 candidate 时，Runner 必须在 broker publication 前验证该 gate；closed/error/wrong scope 时
拒绝且不生成 delivery。成功发布后把 context receipt digest 与 candidate delivery/digest 关联，不把机械
字段塞进 platform-neutral candidate。

Protocol receipt 后只开放只读 binding/context 工具；Build Session、Lease、Batch 和所有 mutation 仍由
第二道 version gate 阻断。Protocol 必须先重新调用 exact-O `get_modeling_context`；Runner 校验其 P/O/state/
recovery 规则，并把 response workspace_version 与 candidate 关联的 ModelingContext receipt 做 exact equality。
相同则生成 Protocol revalidation receipt 并开放后续 stateful tools；不同则使 candidate receipt/platform gate
失效，构造绑定 original delivery、candidate/receipt/context digests、observed/live versions 的 typed
zero-mutation conflict，进入既有完整 revision 流程。revision 前 Modeling 必须重新成功读取 live context；
旧 context receipt、旧 candidate receipt、直接 send、capability publish 或 stateful tool replay 均拒绝。

一旦同一 Protocol 进程的 `submit_modeling_batch(mode=apply_atomic)` 响应确认
`attempt_status=applied`，backend fence 必须校验响应中的 `before_version/expected_version/after_version`
与当前 receipt 连续，然后将该 candidate 的 revalidation context 前进到 `after_version`。下一个
stateful call 仍对该前进版本做 live readback；任何外部版本跳变仍在回调前拒绝。当前 run-owned
Lease 及可通过 validation/reasoning/retrieval 后续修复的 derived stale 不得被误当作 ontology identity
drift；`recovering.active`、not-ready 或 issues 仍 fail closed。

### 3.3 增量 candidate 与写入

Modeling 发布的 candidate 必须是“本轮完整增量”，不是对 Start75 candidate 的完整重发，也不是对本轮
candidate 的 patch。它用平台中立的 `existing_entity_ref` 声明需要引用的 Start75 语义实体 ID 与预期
Class，不携带平台 IRI；其余只包含 R2.3-003 新增/更新的语义项、完整 citations、constraints、dependencies
和 required retrieval paths。

Protocol 在翻译前使用 ontology-scoped live read model 为每个 `existing_entity_ref` 生成 Host/Tool
确定性的 existing-binding receipt。receipt 绑定 candidate digest、Project/Ontology、workspace version、
semantic ID、实际 IRI、Class 和 read evidence；缺失、重复或不匹配时在零 mutation 下冲突。纯 translator
只接受 candidate 加这份冻结 receipt，已有关系端点使用 receipt IRI；R2.3-005 create candidate 不接受该
参数且维持原翻译字节。Protocol 随后按当前 workspace version 对每个依赖阶段执行
`dry_run -> apply_atomic`。不得从 Start75 文件或 candidate 文本猜测平台 ID。每次成功 apply 后使用
receipt 的 after-version 作为下一阶段 expected workspace version。

Protocol 必须通过 native MCP `translate_candidate_to_batches` 把 candidate、`requirement_id=R2.3-003`、
existing-binding receipt、完整 deletion-impact receipts 和 Phase-A readback 状态一次性交给底层 translator；
不得在 candidate-only 调用被拒后手工拼 Batch。readback=false 时工具可以返回 create stages，但必须以
`phase_a_readback_required` 阻断 delete-only；Protocol 按返回顺序完成 create stage 的 dry-run/apply 与
durable readback，刷新 workspace-bound receipts 后再以 readback=true 获取最终 delete-only Phase B。
R2.3-005/default 继续只接受 candidate，不获得上述扩展参数。

当前 `entity-list` 实际返回 full `id/iri/class_iri`，不得由 Protocol 拆 IRI 尾段猜 semantic ID/Class。平台
通用 read projection 必须为 canonical entity 同时返回明确的 `semantic_id`、`entity_iri`、
`class_semantic_id`、`class_iri`，并绑定 Ontology/workspace version；非 canonical/缺字段形状 fail closed。
Protocol existing-binding parser 只消费这份显式投影。确定性测试必须使用真实 backend response fixture，
不能继续只用合成的 `semantic_id/class` 对象证明 live binding。

两个旧 `ExplicitUnknown` 必须硬删除，不建 tombstone、resolution wrapper 或历史 unknown 实体。candidate
使用 `existing_entity_ref` 绑定其 live IRI，并用显式 `delete_existing_entity` 只声明冻结 target semantic
ID/Class 和 `delete_mode=full_live_impact`。Modeling 不声明 IRI、triple 或完整边集合。Protocol 在翻译前
通过 ontology-scoped live read 枚举全部关联三元组并生成 tool-owned canonical impact receipt/digest；用户
对目标实体的硬删除决定即授权删除 receipt 中全部 incident triples。Class/IRI/workspace 漂移、读取不完整、
分页链异常或 receipt 不匹配时零 mutation 冲突。纯 translator 只在 receipt 证明完整影响后生成
`delete_entity`。写入采用单调两阶段，不声称跨 RDF/PostgreSQL 原子：Phase A 的
不可变 Batch 只写解析结论、新 Evidence/lineage 和业务切片，完成 apply/readback 后形成 durable
resolution boundary；Phase B 再以两个按冻结目标顺序排列、各含一个目标的 delete-only Batch 删除两个
目标。Phase B 前重新绑定 workspace version
并重读完整影响集合。最终 readback 必须证明两个 semantic ID 不存在、已声明级联边消失、非目标 Start75
资源仍存在，且新结论直接引用批准 source。两阶段未全部完成时不得冻结 Acceptance model state。

若 Phase A 失败，旧 unknown 仍在并按普通写后对账处理。若 Phase B 的 RDF delete 后出现 SQL/receipt
失败，Runner/Protocol 不假定回滚：先 live readback。目标仍在则同一 Team 使用新 Batch 重试；目标均已
不存在则把 desired semantic state 视为已达到，只恢复/完成机械 Batch、Evidence association 或 lineage
记录，禁止重建 unknown。目标只删一部分或 workspace/readback 不完整时停止新 start，保留状态待人工
对账。测试必须注入 RDF apply 后、SQL commit 前失败并覆盖这三种 readback 分支。

现有通用 recovery 把 delete-only delta 中“仍有任一 delete match”都判为 `not_applied`，不能区分完全未删
和部分删除。实现必须让 Phase B recovery observation 消费 frozen impact receipt 的 before statement set：
目标仍在且 before 集合全部仍在、无新增 incident triple时为 `not_applied`；目标不存在且集合全部消失时为
`applied`；严格子集、目标/边混合、出现新 incident triple、snapshot/workspace drift 或读取不完整时为
`partial_or_drifted`。`_resume_attempt` 只对第一态重试、第二态跳过 RDF并完成机械恢复，第三态禁止 retry/
新 start。该逻辑应作为 receipt-bound 通用 delete-only recovery，不按两个 unknown ID 硬编码。

删除影响不能依赖当前最多 1000 条、无 per-entity completeness 的 `statement-list`。平台增加通用、精确 IRI
作用域的 entity-statement projection：输入 Project/Ontology、exact entity IRI、workspace version、page size
和 opaque cursor；输出 canonical-byte-sorted 的全部 subject/object statements、page digest、snapshot digest、
`next_cursor` 与显式 `complete`。cursor 必须绑定 scope/entity/workspace/snapshot；任何 drift、truncation、页
缺失/重复或未到 `complete=true` 都禁止生成 delete command。该能力是通用语义读取，不包含 Dify/unknown
业务分支。测试使用超过单页和超过 1000 条的实体关系证明完整分页；不能以“刚好未触顶”推定完整。

existing binding 或 deletion-impact read 在首个 candidate receipt 后发现 mismatch 时，Protocol 通过 typed
conflict capability 使当前 receipt 失效、关闭 platform gate，并把 progress 从 `complete` 原子转到
`awaiting_revision`；conflict 必须绑定原 delivery、candidate/receipt digest、workspace version、零 mutation
声明和精确原因。Modeling 只可用 `reply_to=<conflict delivery>` 交付一个完整 revision；Runner 校验同一
Protocol/Modeling identity、revision 单调、旧 digest 不复用后，允许新 typed receipt 替换旧 receipt并重新
开放 gate。任何旧 receipt、foreign/stale delivery、并行 revision 或 mutation 后 binding revision 均拒绝。

条件业务逻辑必须作为本体语义表达，而不是 Runner/Protocol 的硬编码分支。Modeling 可以选择通用语义
Rule、Condition/Decision/Outcome 对象或等价结构；验收只要求来源忠实、条件边界明确、可查询、可验证，
不预设 Class/predicate/IRI 答案。

### 3.4 写后失败

existing scope 不提供自动回滚。失败处理以第一次平台 mutation 为边界：

- mutation 前的 runtime/routing/platform 失败可以清理本轮资源，并在剩余授权内 fresh retry；
- 任一 apply 后应优先在同一存活 Team run 中读取当前状态、形成完整修订 candidate 和新 Batch 修复；
- apply 后若 Team terminal、mutation state unknown 或无法 readback 对账，停止新 start，保留 Project/
  Ontology、fence/attempt/session 证据并请求人工处理；
- 后续 start 只有在当前 model state 已通过正式 readback/validation 对账、形成新的明确 handoff 后才可
  继续。不得把原 Start75 workspace version 继续当作基线，也不得删除整个 Project 来恢复。

### 3.5 验收

Protocol 在最终写入后完成完整 readback、validation conforms、reasoning consistent 和 candidate 声明的
governed retrieval paths。Coordinator 只在 Modeling-ready 与 Protocol-silent 都成立后按 versioned
acceptance standard 冻结 N 张 CQ ticket。N 为任意正整数；Carrier 从 standard 派生 ordered question IDs，
严格串行启动，每题 fresh Source/Platform Examiner，上一题 current/usable PASS 且 child cleanup 后才推进。
任一题失败停止推进；任一新 write 使当前 epoch 全部 verdict 失效。settlement 要求同一最终 model state 上
恰好覆盖 standard 的完整有序 CQ 集合、全部 current/usable PASS 且无 active child。当前 003 standard 仍是
`base-continuity -> no-score-policy-and-case` 两题；通用载体必须用 1/3/5 题测试证明数量无硬编码，同时保持
R2.3-005 两题字节/顺序/settlement 行为兼容。

Runner 投影到 ticket/prompt 的机械元数据包含 `question_ordinal`、`question_count`、`previous_question_id`、
`next_question_id` 和 `is_final_question`；Acceptance/Coordinator 只据这些 Runner-owned 字段推进或终止，
不得从 ID 命名或 `cq-002` 推断 final。requirement-owned prompts 说明通用 N-CQ 流程，003/005 standard
仍拥有问题正文与来源绑定。

acceptance standard 的 `unknown_policy` 同时支持既有字符串
`preserve-explicit-unknown`（005 字节兼容）和 003 的结构化策略：
`mode=resolve-and-delete-targets`、精确 target semantic IDs、`preserve_non_targets=true`。Runner 校验 target
集合与 formal 003 contract 完全一致并投影到每张 ticket；Acceptance 的 `explicit_unknowns` check 对 003
解释为“目标 IDs 不存在且新结论/Evidence 完整，所有非目标 unknown 保持”，对 005 继续采用原 preserve
语义。任意 target 漏删、非目标 unknown 被删或 policy/task 交叉绑定均 fail closed。

003 formal contract、scope handoff 与 acceptance standard 同时冻结唯一删除集合：
`unknown-cross-release-output-meaning`、`unknown-b-no-score-behavior`，两者 expected Class 均为
`ExplicitUnknown`。candidate 只能重复声明该集合，不能决定删除目标；Runner/Protocol 比较 formal
contract、handoff、standard、candidate 四方完全一致后，才允许 live identity/impact read。实际 IRI 不写入
静态资产，只能来自 canonical live projection。任何错 ID、错 Class、少/多 target 或跨资产漂移均在
credential/Build Session/mutation 前 fail closed。

candidate 的删除声明不携带 impact triples 或 digest；Protocol/tool 是完整 live impact 的唯一作者，receipt
绑定 target/scope/workspace/page-chain/snapshot/statement digest/candidate digest。translator 只消费 frozen
candidate 加 tool receipt。这样 deterministic identity、分页、解析和完整性保持在工具层，Modeling 只负责
“删除哪个已冻结业务资源”的语义意图。

最终查询仍返回目标 unknown semantic ID、旧 rationale 或其关系时为 modeling-quality FAIL；不存在结果
只有在新结论、Evidence 和业务链均完整可检索时才算正确删除。

## 4. 当前最小实现

### 4.0 同步瘦身边界

本轮不是重构 Modeling Team，而是删除已实际干扰 003 的三类重复机制：

- **单一 Prompt 合同**：Task objective 持有业务目标/候选约束；各 role package 持有角色协议；Runner
  `_task_text` 必须原样投影 objective 一次并只追加运行期机械事实，不再自行复制 003 目标 ID、item schema、
  业务切片或历史 delivery 文案。005 继续从其 standard/objective 获得当前两题及终止顺序。
- **行为验证替代字节冻结**：只删除 `FROZEN_GLOBAL_SURFACES` 及对应整文件 SHA 测试；保留 baseline、
  source/staged asset、candidate、receipt、evidence 等所有内容 digest gate，并补足 003/005 prompt projection、
  candidate progress、MCP allowlist、N-CQ、cleanup 等精确回归。
- **最终 cleanup 事实**：Codex formal cleanup 在私密 artifact unlink、child/role stop、proxy stop 后执行唯一
  最终 runtime audit；pre-cleanup 结果只作诊断，不进入最终 `private_credentials_destroyed`。Runner 在此后
  完成 Modeling-read/Protocol/admin key revoke、status readback 与旧 key 401/403，再组合唯一 run-level verdict。
  PASS 同时要求 scan complete/error=0/matches=0、无 Runner 已登记的 active process/socket/child/resource、proxy stopped、全部
  key 非 active 且 revoke/readback 成功、无 cleanup error；任一 revoke 失败必须 FAIL。

不拆分 Runner/Acceptance/Codex 大类，不新增策略框架，不改变 Ledger、平台 API、delete recovery、N-CQ
或 005 行为。后续新瘦身项必须有当前真实失败或重复验证证据，并先更新本设计和共享测试计划。

start13 只可在独立证据确认 scope before/after 一致、candidate/receipt 状态、零 stateful call、全部 key revoke、
最终 secret/process/socket scan 与安全生成残留清理后收口。Main 只删除明确的 staged bridge/零字节 socket
占位等生成文件，不删除 session/delivery/evidence；写入 canonical `terminal-reconciliation.jsonl` 后，必须以
StartLedger API append 带完整 terminal evidence 的 retryable failure。本轮不扩展 Ledger 状态机；该证据是
start13 的 Main-owned reconciliation 交付前置，不推广为所有历史/005 terminal failure 的新机械字段。

### 4.1 复用基线

原样复用 R2.3-005 的四角色生命周期、Team Transport、candidate receipt、分阶段 Batch、governed retrieval、
Acceptance Carrier/Examiner、settlement、DeepSeek proxy/credential 和 aggregate cleanup。R2.3-003 只增加
需求特有的身份、existing scope、source/CQ 和账本政策，不重写这些已验收能力。

### 4.2 必需实现差异

1. 新增 R2.3-003 Task、四角色 Profile、model manifest、当前两 CQ acceptance standard、existing scope
   handoff/config；
2. 扩展 candidate authoring/receipt/translator，加入仅 R2.3-003 可用的 `existing_entity_ref`、
   `delete_existing_entity` 与 read-model binding/deletion-impact receipt；translator 对普通 existing ref
   不发 command，只绑定 live IRI，对经过完整影响核对的删除项发 `delete_entity`。005 的 create-only
   translator 输入/输出保持不变；
   native MCP wrapper 精确透传 003 的 binding/impact/readback 参数，禁止 Protocol 手工 fallback；translator
   生成 Phase A semantic batches 与独立 Phase B delete-only batch，且删除永远排在 durable Phase A
   readback 之后；
3. 把散落的 R2.3-005 formal Task/Profile 判断收口为两个明确注册的 formal run contract；R2.3-005 继续只
   接受其精确 create 合同，R2.3-003 只接受其精确 existing 合同，未知组合 fail closed；
4. 为 R2.3-003 增加独立 StartLedger namespace 与 `initial_authorization` 事件：固定初始 cap 0，空账本
   只接受一次绑定用户授权 ID/reference、精确 `additional_starts=4` 的初始授权；该事件不要求 prior
   terminal failure，后续 budget extension 仍要求正常前置。replay、locking、重复 ID/reference、事件顺序
   和 reserve 都 fail closed；不得读取、修改或消费 R2.3-005 的 Start75–77 账本；
5. 增加 nonempty-existing PlatformScope 路径：不调用 `_empty_context`，而是读取完整 workspace/history，
   只拒绝 active Session/Lease、in-flight Attempt/fence、身份或 handoff 漂移；cleanup 比较本轮 before/after
   workspace、确认本轮 Session/Lease terminal 并撤销 key，永不删除 P/O，也不因历史 batch/session 报错；
6. existing preflight credential 必须绑定 exact P/O/handoff/default Graph Set/workspace version，检查发生在
   initial authorization 之后、reservation/run root/Agent/Build Session 副作用之前；
7. Task/source staging 使用本需求的增量 candidate、两份新资料和当前两条 CQ；把 Acceptance Carrier、
   Runner task text、round advance、revalidation 与 settlement 参数化为 standard-owned N-CQ，保持 005
   当前两题顺序与行为兼容；
8. 同步修改所有 authoritative surfaces：003 Task/objective、Modeling/Protocol/Acceptance/Coordinator
   package prompts、acceptance standard loader/normalizer、ticket projection、Runner task text、Carrier
   frozen IDs/advance/revalidation/settlement；删除所有 preserve-old-unknown、exactly-two、固定 CQ ID 和
   final-CQ2 指令。005 的问题正文仍由原 standard 提供；
   同时扩展 standard/policy validator，支持 003 deletion-aware unknown policy 并保持 005 preserve policy；
   在 `FormalRunContract`、003 handoff、acceptance standard 冻结精确 target IDs/Class，candidate 无权选择；
9. 增加通用 canonical entity identity projection 与完整分页 entity-statement projection，并把
   `get_entity_statement_context` 纳入 formal Protocol allowlist/task tool；不增加 Dify 专属 API、schema、
   read model 或硬编码查询；
10. 扩展 typed candidate progress，支持 mutation 前 accepted-receipt -> live-binding conflict -> full
    revision -> replacement receipt；用 start5 的真实失败顺序做回归，并保持 005 初稿/conflict revision 路径。
11. 扩展 ModelingBatch delete-only recovery observation/resume branch，基于 impact receipt 区分
    `not_applied/applied/partial_or_drifted`，partial/drifted 永不自动重试。
12. 把 Modeling package 从 `platform:none` 调整为 requirement-gated read-only surface；Runner/Adapter 仅在
    formal R2.3-003 为 Modeling 创建独立 project-scoped `read` key并注册三工具 ontology-platform MCP，
    对 Coordinator/Acceptance/005/default 不扩大权限。增加 Modeling-first `get_modeling_context` 调用门、
    read-model 参数/scope 约束、Protocol workspace revalidation、call evidence、key revoke/secret cleanup；
    复用已有 MCP tools/service，不新增业务专用 API。
13. 新增 Runner-owned `ModelingContextGate` 与 Modeling read proxy：gate 覆盖 direct Team Transport 和
    staged-candidate capability 两条发布路径；proxy 在 backend 前执行 exact tool/P/O/model/scope allowlist。
    Candidate receipt 关联 Modeling context receipt；Protocol 只读 revalidation receipt 匹配后才开放 Session/
    Lease/write，drift 复用 post-receipt standalone typed conflict/revision，不新增第三套 revision 协议。

“formal run contract” 只是两个已知需求的确定性身份/资产/作用域策略映射，不是动态插件系统、后台调度器
或通用 orchestration framework。

## 5. Future productization

- 任意需求声明式注册、动态 source、跨 Project 调度；
- existing-scope 自动 snapshot/rollback、跨 run crash recovery、长期 mutation journal；
- Project 生命周期 UI、并发 team 协调、通用 semantic migration；
- 自动把其他旧 unknown 转成通用时间版本知识状态。

以上均不属于 R2.3-003 完成门。

## 6. 风险核验结果

1. 平台字段级 `update_entity` 只触碰 payload 中给出的 predicate；existing relation 可引用绝对 IRI 追加；
   rule apply 会推进 workspace version。对应 4 个后端测试于 2026-08-11 PASS。
2. 当前正式 Runner 是 R2.3-005/create-only，Task/Profile/manifest/preflight/ledger 多处精确绑定；因此仅新增
   YAML 不可运行，必须实现第 4.2 节的窄扩展。
3. 当前 `PlatformScope._existing()` 会调用 `_empty_context()` 并拒绝任意历史 batch/session，不能用于
   Start75；必须实现第 4.2(5) 的 nonempty-existing 路径。
4. 当前本机数据库仍存在 Start75 Project/Ontology，历史 Build Session completed、Lease released；但正式
   API 因没有当前 read credential 返回 401，所以 live workspace drift 必须留到授权 preflight，不可用 retained
   文件代替。
5. 当前 Protocol translator 只生成 `create_*` 且要求 relation endpoint 在本轮 candidate 声明；必须实现
   existing binding receipt，不能重发旧资源或猜 IRI。
6. 当前 StartLedger 不允许 zero cap 的首次授权；必须实现一次性 `initial_authorization`，不能复用 005
   retry budget 事件。
7. GitNexus index 落后 HEAD 1 commit；按仓库入口刷新时因 invalid UTF-8 在 `LOWER` 阶段失败。旧索引只
   用于定位，设计结论以当前源码和测试为准。
8. 当前 typed progress 在 receipt accepted 后进入 `complete`，只接受初稿或 `awaiting_revision` 的 conflict
   reply；start5 因而把 corrected `delivery-7` 判为 foreign/stale。硬删除实现前必须先加入第 3.3 节的
   pre-mutation replacement lifecycle。
9. 当前 backend entity-list 返回 full `id/iri/class_iri`，Protocol binding parser 却期待合成
   `semantic_id/class`；现有单测不代表 live contract。必须由平台显式投影 neutral IDs。
10. 当前 statement-list 默认/最大结果受限且没有 entity-scoped complete cursor；wildcard `delete_entity`
    会删除所有 subject/object triples。没有完整分页证据时不能安全启用删除。
11. 既有 `get_modeling_context` 已由 R-004 实现并同时提供 REST/MCP，真实 Start8 返回 workspace identity、
    资源计数、stale/lease/recovery、recent batches 和 fixed read-model query entries；三个目标工具在 backend
    policy 中均为 Project-owned `read`、`mutates_state=False`。缺口仅是 Modeling runtime 当前
    `platform:none` 且没有 role-private live state，不能只改 prompt，必须实现 credential/tool wiring 与
    cleanup，同时保持 Protocol-only writer。

## 7. 完成标准

- 权威需求、source bundle、设计、共享测试计划和交付记录一致；
- plan review 无未处理 Critical/High；
- deterministic tests 覆盖两个 formal contract 隔离、003 ledger、existing preflight、source visibility、
  delta candidate、安全硬删除、N-CQ（至少 1/3/5）和写后失败；完整 repository-required suite PASS；
- start19 已完成 append-only 终态对账，当前三次授权剩余两次；提交本轮确定性修复并通过 current-context/
  health gate 后可继续。后续 R2.3-003 Team run 须复用 durable Phase A，完成两个单目标 Phase-B 删除与
  独立验收，首次完整 PASS 后停止；
- Runtime/credential/Build Session/Lease/child/proxy 清理为零残留，Project/Ontology 保留；
- 需求状态、设计结果、测试轮次、runtime health、cleanup 和 commit 全部同步。
