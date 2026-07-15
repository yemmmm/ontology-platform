# R-004 外部 Agent 建模批次详细设计

**Date:** 2026-07-15  
**Status:** Approved for implementation  
**Owner:** Agent  
**Requirement:** `docs/requirements-v1.0.md` R-004

## 1. 背景与交付范围

R-003 已提供 Project 级 Build Session、追加式 Checkpoint、Ontology Lease 和
`workspace_version` 校验，但普通 Agent 建模仍然只能调用单条 canonical write 或若干专用接口。
这些接口没有统一的批次身份、逐项诊断、依赖处理、跨存储恢复和跨 Session 历史。

R-004 增加一个 Ontology 级建模批次协议。首版交付同时覆盖：

- PostgreSQL 持久模型与 Alembic 迁移；
- Modeling Command Handler 注册、编译、校验、依赖分组、应用和恢复服务；
- 单一 REST/MCP 提交能力与批次、Session、Ontology 查询能力；
- Ontology Modeling Context；
- Evidence、能力问题、Rule Definition 和 canonical RDF write 的接入；
- Build Context 与现有只读 Debug 页的诊断摘要；
- API、MCP、架构、需求状态和测试文档同步。

Operation 不在首版建立领域模型，只预留 handler 注册点，由 R-007 后续接入。R-004 不新增
人工建模页面、任务队列、自动推理、规则执行或投影重建。

## 2. 核心原则

1. 当前 Modeling Context 和固定语义读模型是后续建模的事实基础，Batch 历史只解释变化。
2. Batch 内容不可变；每次 dry-run 或 apply 是独立且幂等的 Attempt。
3. apply 是受控技术写入，不是人工 approve；发布和显式治理决定仍由用户负责。
4. Agent 只指定 Ontology，不指定 Graph Set、graph IRI 或 shape graph。
5. 所有建立项标识在编译前确定性分配，dry-run、apply 和恢复使用同一个规范化计划。
6. 批次先整体编译和校验，再一次写入最终稳定子集；数组顺序不构成覆盖或执行语义。
7. RDF 与 PostgreSQL 不假装拥有分布式事务。平台先持久化计划和写入栅栏，再通过可验证、
   幂等的向前恢复收敛。

## 3. 对外协议

### 3.1 REST 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/build-sessions/{session_id}/modeling-batches` | 以 mode 提交或幂等恢复一个 Batch Attempt |
| `GET` | `/modeling-batches/{batch_id}` | 读取 Batch、Items、全部 Attempts、Findings 和恢复状态 |
| `GET` | `/build-sessions/{session_id}/modeling-batches` | 分页读取 Session 内批次 |
| `GET` | `/ontologies/{ontology_id}/modeling-batches` | 跨 Session 按状态和时间分页读取批次 |
| `GET` | `/ontologies/{ontology_id}/modeling-context` | 读取当前权威建模基础和查询入口 |
| `GET` | `/ontologies/{ontology_id}/semantic-read-models/{model_name}` | 解析默认工作区并读取固定语义模型 |

提交成功或完成确定性校验时返回 `200`；首次建立 Batch 和 Attempt 也不依赖 `201` 区分幂等性，
响应中的 `created_batch`、`created_attempt` 明确说明是否新建。无法进入批次处理的顶层错误使用
HTTP 状态和统一 `detail.code`；进入处理后的建模问题始终返回正常 Attempt 响应。

Batch 已成功或部分成功后，使用新 idempotency key 再次 apply 不建立新 Attempt，也不返回错误；
平台以 `created_attempt=false` 返回原终态 apply Attempt。只有 Batch 内容或既有 key 的请求语义
发生变化时才返回冲突。

两个列表端点统一接受不透明 `cursor`、`limit`（1-100）和可重复的 `status`；Ontology 列表还接受
ISO-8601 `created_from`/`created_to`。稳定排序为 `created_at DESC, id DESC`，下一页游标同时编码
这两个值，避免相同时间戳产生重复或漏项。

### 3.2 MCP 工具

MCP 与 REST 调用同一服务，不复制校验逻辑：

- `submit_modeling_batch`
- `get_modeling_batch`
- `list_session_modeling_batches`
- `list_ontology_modeling_batches`
- `get_modeling_context`
- `get_ontology_read_model`

只有 `submit_modeling_batch` 是写工具。MCP 返回与 REST 相同的字段名、状态和 Finding code。

### 3.3 提交请求

```json
{
  "client_batch_id": "customer-model-v1",
  "ontology_id": "ontology-uuid",
  "idempotency_key": "attempt-uuid",
  "mode": "apply_atomic",
  "expected_workspace_version": "opaque-signature",
  "lease_token": "only-present-for-apply",
  "items": [
    {
      "client_item_id": "customer-class",
      "command_kind": "create_class",
      "payload": {"name": "Customer"},
      "depends_on": [],
      "evidence_reference_ids": [],
      "evidence": [],
      "rationale": "Represents a purchasing party",
      "competency_question_ids": []
    }
  ]
}
```

规则如下：

- `mode` 只允许 `dry_run`、`apply_atomic`、`apply_partial`，默认 `apply_atomic`；
- 三种 mode 都要求 `expected_workspace_version`，使 dry-run 结果也明确绑定读取基线；
- `lease_token` 在 apply 必填，在 dry-run 必须省略；它不进入内容哈希、Attempt 请求哈希或审计；
- Batch 顶层不接受 `actor`、`graph_set_id`、graph IRI 或 shape graph 参数；
- Item payload 使用命令专属严格 schema，拒绝未知字段，并且不得包含 `ontology_id`、
  `graph_set_id`、`graph_iri`、`target_graph_iri`、`shape_graph_iris` 或 `actor`；
- `client_item_id` 在 Batch 内唯一，`depends_on` 去重后参与内容哈希；Items 先按
  `client_item_id` 规范排序再计算内容哈希，因此数组重排不形成另一份 Batch 内容。

### 3.4 结构化资源引用

普通标量 payload 字段可使用以下两个对象之一：

```json
{"resource_id": "existing-platform-resource-id"}
{"item_ref": {"client_item_id": "customer-class", "output": "resource_id"}}
```

`item_ref.output` 首版只允许 `resource_id` 或 `resource_iri`。Handler 的字段 schema 声明该字段
需要 ID 还是 IRI；平台解析后再交给 canonical compiler。引用自动建立成功依赖，不使用字符串
替换或 `@item:` 语法。

建立类命令在编译前输出主资源：

| 命令 | ID payload 字段 | 资源种类 |
|---|---|---|
| `create_class` | `class_id` | `class` |
| `create_property` | `property_id` | `property` |
| `create_relation_type` | `relation_type_id` | `relation-type` |
| `create_shape` | `shape_id` | `shape` |
| `create_entity` | `entity_id` | `entity` |
| `create_mapping` | `mapping_id` | `mapping` |
| `create_rule_definition` | `rule_id` | `rule`（另返回 current `definition_id`） |

未提供允许的显式 ID 时，使用 UUIDv5 由平台 `batch_id/ontology_id/client_item_id/command_kind`
生成；IRI 使用现有 SemanticNamespace 生成。Batch 行必须先持久化，再分配 Item 输出；不同
Session 即使复用全部客户端 ID，也会因全局 `batch_id` 不同而得到不同资源 ID。显式 ID 仍须
通过格式、归属和冲突校验。

### 3.5 响应结构

提交与读取使用同一个核心响应：

```json
{
  "batch_id": "...",
  "client_batch_id": "...",
  "batch_status": "open",
  "attempt_id": "...",
  "mode": "dry_run",
  "attempt_status": "validated",
  "created_batch": true,
  "created_attempt": true,
  "workspace": {
    "expected_version": "...",
    "before_version": "...",
    "after_version": null
  },
  "target": {
    "graph_set_id": "read-only-diagnostic-id",
    "source_signature_before": "...",
    "source_signature_after": null,
    "graphs": [
      {
        "role": "asserted_ontology",
        "graph_iri": "...",
        "revision_before": 3,
        "revision_after": null
      }
    ]
  },
  "items": [
    {
      "item_id": "...",
      "client_item_id": "customer-class",
      "status": "validated",
      "resource_outputs": {"resource_id": "...", "resource_iri": "..."},
      "atomic_group_id": "...",
      "finding_codes": ["missing_evidence"]
    }
  ],
  "groups": [],
  "findings": [],
  "normalized_delta": {},
  "delta_hash": "...",
  "evidence_candidates": [],
  "recovery": {"state": "not_required", "safe_to_retry": true},
  "created_at": "...",
  "completed_at": "..."
}
```

Batch 详情额外返回不可变 Items 和按创建时间排序的全部 Attempts。列表只返回安全摘要，不返回
内联 Evidence 原文、完整 delta 或 graph IRI。普通 Agent 的 Modeling Context 也不暴露 Lease token。

逐项状态固定如下：dry-run 成功项为 `validated`，直接错误项为 `failed`，依赖错误项为 `blocked`；
atomic apply 校验失败时直接错误项为 `failed`，其余未写入项统一为 `not_applied`；partial apply
分别使用 `applied`、`failed` 和 `blocked`。Attempt 级 dry-run/atomic 校验失败均为
`validation_failed`，partial 存在失败但成功写入子集时为 `partially_applied`。

## 4. 命令 Handler

### 4.1 接口

`ModelingCommandHandler` 注册表以 `command_kind` 为键。每个 handler 提供：

- 严格 payload 校验；
- 建立项主资源描述与确定性 ID 注入；
- `resource_id` / `item_ref` 字段解析；
- 隐式依赖和规范化 write effects；
- `compile(...)`，产出 RDF delta 或 PostgreSQL operation plan；
- `validate(...)`，产出 Validation Findings；
- `apply_postgres(...)`，仅供非 RDF handler 在已规划事务中执行；
- `describe_outputs(...)`，供响应、Evidence 和审计关联。

Handler 不提交事务、不读取 Lease token、不决定 batch mode，也不吞掉异常文本。

### 4.2 首版注册范围

RDF handler 复用现有 canonical compiler：

- Class、Property、Relation Type：create/update/delete；
- Shape：create/update/delete；
- Entity：create/update/delete；
- Relation：create/delete；
- Fact：update/delete；
- Mapping：create/update/delete。

`review_assertion` 属于人工事实审计，`bind_fact_evidence`/`unbind_fact_evidence` 已由 R-002 的
Evidence Association 取代，均不注册进普通 R-004 Batch。

PostgreSQL handler 增加：

- `create_rule_definition`；
- `update_rule_definition`；
- `delete_rule_definition`。

R-004 将 Rule 区分为逻辑资源和版本记录：逻辑 Rule 有稳定 `rule_id`、Ontology、`rule_iri`、
`status` 和 current definition 指针；Rule Definition Version 有独立 `definition_id` 和由全部规范化
定义内容计算的 version。create 同时建立两者；任何 update 都建立新 Definition Version、将前一
版本标记 `superseded` 并原子切换 current 指针；delete 将逻辑 Rule 和当前版本标记 `inactive`。
旧版本及其 Attempt 审计始终保留，不物理删除。

### 4.3 目标图解析

服务首先通过 Ontology Workspace 取得唯一 active default Graph Set，再按 handler 声明解析角色：

- ontology schema 和默认 Mapping → `asserted_ontology`；
- Entity、Relation、Fact → `asserted_data`；
- Shape → `shapes`；
- Rule Definition → PostgreSQL，不接受 RDF 目标图。

现有 shape compiler 使用受管 shapes 子图时，handler 必须验证它属于该 Ontology 的 `shapes`
类别和允许前缀。Import Mapping 依赖 import-run 专用图，首版普通 Batch 不接受 `source_id/run_id`
覆盖；相关命令返回 `unsupported_batch_variant`。

## 5. 持久化模型

Alembic `0023` 新增以下表，并新增 `semantic_rules` 作为 Ontology 级逻辑 Rule：`id`、
`ontology_id`、`rule_iri`、`status`、`current_definition_id` 和审计时间，唯一键
`(ontology_id, rule_iri)`。`semantic_rule_definitions` 增加可空 `semantic_rule_id`、版本状态及
全内容哈希；R-004 版本使用唯一键 `(semantic_rule_id, version)`。原 `(rule_iri, version)` 约束
只继续保护 `semantic_rule_id IS NULL` 的 legacy Rule Definition。旧 Rule 保持可读但不被 R-004
跨 Ontology 复用；R-004 handler 只更新明确属于目标 Ontology 的逻辑 Rule。

### 5.1 `modeling_batches`

- `id`：全局 UUID；
- `project_id`、`ontology_id`、`build_session_id`；
- `client_batch_id`、`content_hash`；
- `status`：`open|applying|recovering|applied|partially_applied|failed`；
- `created_at`、`updated_at`、`terminal_at`；
- 唯一键 `(build_session_id, client_batch_id)`。

### 5.2 `modeling_items`

- `id`、`batch_id`、`client_item_id`、`ordinal`；
- `command_kind`、规范化 `payload`、`depends_on`；
- `resource_outputs`；
- `evidence_reference_ids`、规范化内联 `evidence`；
- `rationale`、`competency_question_ids`；
- 唯一键 `(batch_id, client_item_id)`。

Items 只保存 Batch 内容，不保存某次 Attempt 的状态。

### 5.3 `modeling_batch_attempts`

- `id`、`batch_id`、`build_session_id`、`idempotency_key`、`request_hash`；
- `mode`、`status`、`expected_workspace_version`；
- `graph_set_id`、`lease_revision`、`workspace_version_before/after`；
- `normalized_delta`、`delta_hash`、`operation_plan`、`operation_plan_hash`；
- `findings`、`groups`、`recovery_state`、`recovery_detail`；
- `audit_id`、`started_at`、`completed_at`、`created_at`；
- `execution_claim_id`、`execution_claim_expires_at`、`execution_claim_heartbeat_at`；
- 唯一键 `(build_session_id, idempotency_key)`。

数据库使用 partial unique index 保证同一 Batch 最多一个 `validating|applying|recovering` 的 apply
Attempt；服务仍先锁 Batch 行并返回稳定 `in_flight_batch`，索引是最后一道并发保护。

request hash 包含 Batch 内容哈希、mode 和 expected version，不包含 Lease token。`operation_plan`
在任何副作用前固化最终 Item 集、预分配 ID、RDF delta、Rule 操作和 Evidence 计划。

### 5.4 `modeling_attempt_item_results`

- `id`、`attempt_id`、`modeling_item_id`、`client_item_id`；
- `status`：`validated|failed|not_applied|blocked|applied`；
- `atomic_group_id`、`resource_outputs`、`finding_codes`；
- `evidence_reference_ids`、`evidence_association_ids`；
- 唯一键 `(attempt_id, modeling_item_id)`。

### 5.5 `ontology_write_fences`

- `ontology_id` 主键；
- `attempt_id` 唯一、`build_session_id`、`lease_revision`；
- `acquired_at`。

Fence 只存在于 `applying`/`recovering` Attempt。所有 canonical graph write 和 R-004 Lease
获取、轮换、释放、Session 完成/取消都检查 fence。所属 Attempt 通过内部 `attempt_id` 重入；
其他写入返回 `ontology_write_fenced`。

`build_checkpoints.related_batch_id` 在本迁移中补充指向 `modeling_batches` 的
`ON DELETE SET NULL` 外键。

R-004 将原本只含 Graph Set source signature 的不透明 `workspace_version` 扩展为组合签名：
`sha256(graph_source_signature + ontology_rule_signature)`。`ontology_rule_signature` 由该 Ontology
所有逻辑 Rule 及其 current Definition 的稳定 ID、IRI、version、status、name、input/output、
安全策略和其他规范化建模字段确定性计算，不依赖数据库行顺序或更新时间。Agent 仍不能解析该值；
现有图变更通过 graph revisions 改变它，Rule-only 变更也会改变它。Build Context、Modeling Context
和 `authorize_apply(...)` 必须统一调用同一 version service，不能保留两套版本算法。

## 6. 状态机和事务边界

### 6.1 Attempt 状态

```text
validating ──ok dry-run────────────▶ validated
     │
     ├──deterministic error────────▶ validation_failed
     │
     └──ok apply──▶ applying ──────▶ applied / partially_applied
                         │
                         └──uncertain cross-store result──▶ recovering
                                                              │
                                                              ├──converged──▶ applied / partially_applied
                                                              └──proven unsafe──▶ failed ──▶ Batch failed
```

顶层请求错误不会建立 Attempt。进入 `validating` 后发生的普通命令或候选状态问题只能结束为
`validation_failed`。`failed` 只用于平台能证明无法自动恢复的执行故障。

Build Session complete/cancel 在存在 `validating|applying|recovering` apply Attempt 时返回
`in_flight_batch`。Lease 的 acquire/rotate/release 只在 fence 已建立后被强制阻止；如果 Lease 在
纯 validating 阶段失效，本次 apply 必须在建立 plan/fence 前返回 Lease 错误。

### 6.2 apply 两阶段

1. PostgreSQL 事务 A：锁定 Session、Lease、Batch 和 Ontology fence 槽位；重新校验
   workspace version；编译完整候选；保存 plan/delta/Findings/最终成功子集；建立 fence；将
   Attempt 置为 `applying` 并取得首个 execution claim；提交。
2. 执行阶段：按 plan 应用 union RDF delta；在 PostgreSQL 事务 B 中以预分配 ID 写入 Rule、
   Evidence、Evidence Association、单一 Batch audit、图修订、stale pointers、Item results 和
   Attempt 终态；重新计算并持久化 Graph Set source signature、更新 Build Session activity；最后
   释放 fence 并提交。Rule-only 变更也必须将目标 Graph Set 的 rule-result 及其下游投影 pointer
   标记 stale，但不运行 Rule。

RDF Item 合并成一个 union delta，只调用一次 canonical writer；完全重复 quad 去重。一个 Attempt
使用一个预分配 `audit_id`，Item results 和 Evidence Association 通过该 audit 与各自 Item 关联。
canonical writer 增加可选 `audit_id`、`fence_attempt_id` 和 `commit=False`，现有调用保持兼容。

### 6.3 恢复

如果 RDF 调用或事务 B 的结果不确定，平台在独立事务中将 Attempt 置为 `recovering`，保留 fence。
相同幂等 POST 请求可以触发一次有界恢复；GET 详情和 Debug 页面只观察状态，不产生恢复副作用：

1. 对比当前 workspace、预期 inserts、具体 deletes 和通配 delete 的可观察效果；
2. `not_applied`：在 fence 内重放同一 plan；
3. `applied`：不重写 RDF，只补齐缺失的 PostgreSQL 记录；
4. `partially_observed` 但未出现外部冲突：幂等重放 plan 使 RDF 收敛；
5. 出现计划外 revision、不可解释语句或不同 audit：保持 `recovering`，记录
   `recovery_requires_intervention`。只有平台能证明没有未归属或部分副作用、再次重放也不可能
   成功且释放 fence 安全时，才进入 `failed`；仍有不确定副作用时必须保持 `recovering` 等待受控处置。

恢复不重新编译、不分配新 ID、不删除整个图。每次恢复诊断追加到 `recovery_detail.history`，旧记录
不可修改。

进程在无法记录 `recovering` 前退出时，Attempt 会保持 `applying` 和 fence；相同幂等 POST 将它
按不确定结果处理并进入同一恢复算法。执行者每个阶段更新数据库 claim heartbeat；相同幂等
POST 先锁 Attempt，未超时 claim 只返回当前状态和 `retry_after`，超时后才以新 claim 串行接管。
claim TTL 必须大于底层 RDF 调用超时；即使旧执行者晚返回，预分配 ID、幂等 RDF delta 和
Attempt 行锁也只允许一个 PostgreSQL finalizer。新 dry-run 或新 apply Attempt 在 fence 存在时
均返回 `ontology_write_fenced`，避免针对尚未收敛的中间状态生成伪有效结果。

## 7. 编译、依赖和部分应用

### 7.1 校验顺序

1. 顶层 schema、容量、Session/Ontology、幂等和 workspace version；
2. apply 的 Lease 与 fence；
3. Item ID、命令 schema、禁止字段、Evidence 和能力问题归属；
4. 确定性资源 ID、结构化引用和隐式依赖；
5. Tarjan SCC 生成 Atomic Dependency Groups；
6. handler 领域校验、资源存在性和 write effects；
7. 重复/冲突 effects；
8. union candidate SHACL 和平台跨项校验；
9. partial 模式移除失败组、传播 blocked 并重复 7-8，直到固定点；
10. 保存最终规范化 plan。

服务收集全部可独立发现的 Findings，不在第一个 Item 错误处停止。

### 7.2 write effects

每个 effect 至少包含 `resource_key`、`slot_key`、`operation`、`cardinality`、规范化
`value_hash`、通配 `match_pattern` 和 `cascade_footprint`。Handler 必须声明单值/集合槽位，并把
Entity/Class 等删除可能影响的入边、出边、属性或从属资源纳入 footprint，不能只比较显式 inserts。

- 同资源不同 slot：兼容；
- 相同 effect：只执行一次并返回 `duplicate_effect` warning；
- 同一单值 slot 不同值、delete 与 update/create 同资源：返回
  `conflicting_item_effects`；
- 不以 Items 顺序决定胜者。

### 7.3 partial 固定点

SCC 被折叠为 group DAG。含直接 error 的 group 失败；所有依赖它的 group blocked。对剩余 groups
重新生成 union candidate。能够通过 SHACL focus node 或 effect 归因的错误继续移除对应 group；
无法安全归因的 batch error 阻止整个 partial apply。最终成功 groups 作为一个写入单元提交。

## 8. Evidence、理由和能力问题

- dry-run 调用 `resolve_candidates(..., persist=False)`，只返回 existing ID 或待创建摘要；
- apply 只为最终 `applied` Item 调用 `persist=True`；
- operation plan 为内联 Evidence 保存规范化 project evidence key，并为待建 Evidence Reference
  与 Association 预分配确定性 ID；如果同一 project evidence key 已由其他流程建立，则使用既有
  Reference ID。事务 B 使用唯一内容键 `INSERT ... ON CONFLICT DO NOTHING` 后重新 SELECT，
  Association ID 由 Attempt/Item/实际 Reference key 确定，恢复时不重新随机分配；
- Evidence Association 使用 `target_type=modeling_item`、`target_id=modeling_item.id`，并记录
  `client_item_id`、`edit_audit_id` 和 Graph Set；这样一个 Item 的多个输出仍有唯一证据归属；
- 已有 Evidence Reference、能力问题和 Ontology 必须属于 Batch Project；
- rationale 原样保存在 immutable Item 中，但永不转换为 Evidence；
- 无 Evidence 返回 `missing_evidence` warning，无 rationale 返回 `missing_rationale` info。

## 9. Modeling Context

`GET /ontologies/{ontology_id}/modeling-context` 返回：

- Project/Ontology 安全摘要；
- 当前 `workspace_version`、workspace state 和 editable；
- `resource_counts`：classes、properties、relation_types、shapes、entities、relations、facts、
  mappings、rule_definitions；
- `derived_state`：current/stale pointer 数量和 stale warning；
- active Lease 是否存在、是否被 fence（不返回 token、Graph Set ID 或 graph IRI）；
- 最近全部状态的 Batch 摘要和 `recent_batches_next_cursor`，可继续分页读取完整历史；
- 固定详情入口：Classes、Entities、Facts、Rules、History、Delta 和 Batch history。

为避免普通 Agent 被迫读取内部 Graph Set ID，R-004 同时提供只读
`GET /ontologies/{ontology_id}/semantic-read-models/{model_name}` 和 MCP
`get_ontology_read_model`；服务端解析 default Graph Set 后委托现有 read-model service。
`model_name` 首版允许 `classes|entities|facts|history|delta|rules`，分页参数与现有模型一致。
Modeling Context 的 `query_entries` 返回这些可直接调用的具体 URL 和 MCP 工具参数模板。
其中 `delta` 由服务端自动选择同一 Ontology scope 中最近的非默认 Graph Set 作为历史基线，
与当前 default workspace 比较；没有历史基线时返回空差异和 `no_prior_graph_set` warning，调用方
不提供 Graph Set ID。

计数通过当前 RDF/Rule 读模型计算，不通过回放 Batch 推导。Build Context 的
`platform_state.modeling_batches` 和 Session detail 改为真实批次摘要。

## 10. 授权接缝与 R-008 边界

REST 和 MCP adapter 都向服务传入不可由 payload 构造的 `ModelingAuthorizationContext`，包含内部
actor、Project read/write 决定和调用表面。R-004 不读取请求中的 `actor`。R-008 完成后，该 context
由认证主体和 Project scope 生成，并在建立 Batch 前拒绝未授权调用。

当前仓库尚未实现 R-008，因此首版只能把 actor 记录为 `system:unattributed`，并明确标记这些接口
为本机/受信内部开发能力，不宣称已满足生产外部访问授权。该限制不改变 Session、Lease、版本和
确定性校验，但部署到不受信网络前必须先完成 R-008。

## 11. 容量和配置

新增配置及默认值：

```text
MODELING_BATCH_MAX_ITEMS=100
MODELING_BATCH_MAX_REQUEST_BYTES=1048576
MODELING_BATCH_MAX_INLINE_EVIDENCE=100
MODELING_BATCH_MAX_EVIDENCE_EXCERPT_CHARS=20000
MODELING_BATCH_RECOVERY_MAX_STEPS=3
MODELING_BATCH_EXECUTION_CLAIM_TTL_SECONDS=300
```

REST 使用实际请求 body 字节数，MCP 使用规范化 JSON UTF-8 字节数。所有超限错误返回稳定 code、
`actual` 和 `limit`，且发生在命令编译或副作用之前。

## 12. 前端诊断

现有 Build Context Debug 页保持 Project-scoped 和只读：

- Workspace 卡片可以展开加载 Modeling Context；
- 展示 workspace version、resource counts、derived stale 状态、fence 状态和近期 Batch；
- Modeling Batch 摘要可加载详情，展示 mode、Attempt 状态、逐项状态和 Finding，不提供 apply、
  retry、删除或编辑按钮；
- raw JSON 继续递归过滤 Lease token、凭证、Graph Set ID 和 graph IRI；
- 页面未选择 Ontology 时仍可通过 Project Build Context 使用。

## 13. 错误码

请求级至少包括：`request_too_large`、`batch_limit_exceeded`、`inline_evidence_limit_exceeded`、
`build_session_not_found`、`build_session_not_active`、`ontology_not_found`、
`workspace_revision_conflict`、`ontology_lease_conflict`、`lease_expired`、
`ontology_write_fenced`、`batch_content_conflict`、`idempotency_conflict`、
`batch_failed`、`in_flight_batch`。

Finding code 至少包括：`unsupported_command_kind`、`invalid_command_payload`、
`forbidden_target_override`、`invalid_resource_reference`、`unresolved_item_ref`、
`invalid_dependency`、`evidence_not_found`、`evidence_project_mismatch`、
`competency_question_not_found`、`competency_question_scope_mismatch`、`missing_evidence`、
`missing_rationale`、`duplicate_effect`、`conflicting_item_effects`、`shacl_violation`、
`candidate_validation_failed` 和 `dependency_failed`。

## 14. 交付验收

实现完成必须同时满足 `docs/requirements-v1.0.md` R-004 验收标准和配套测试计划。设计允许内部
类名和文件拆分根据代码规模调整，但不得改变：单一提交接口、三种 mode、不可变 Batch/Attempt、
结构化引用、SCC partial 语义、写入栅栏、事前 plan、向前恢复、当前 Modeling Context 权威性、
只读 Debug 边界以及 REST/MCP 同服务。
