# MCP 工具

本文档描述当前 FastMCP 进程实际注册的工具。完整清单来自 `mcp.list_tools()`，并通过现有
`app.api.mcp_catalog._enumerate_tools()` 补充 category 和源文件。

## 启动与配置

从 backend 目录启动 stdio MCP server：

```bash
cd /path/to/ontology-platform/backend
uv sync --extra dev
uv run python -m app.mcp.server
```

Codex 等客户端应把 MCP server 的工作目录设为仓库的 `backend` 目录，并运行上述 Python 模块。
进程读取 `backend/.env` 中当前 `Settings` 支持的数据库、Oxigraph、LLM、Embedding 和语义运行参数。

启动前必须在 `backend/.env` 设置 `ONTOLOGY_MCP_API_KEY`。进程在进入 stdio/SSE/streamable HTTP
event loop 前验证 hashed API key；缺少、无效或已撤销 key 时非零退出。每次 tool call 会再次检查
撤销状态、required scope 和 Project/Ontology 归属，payload 中的 actor 不能覆盖认证主体。
中央 policy registry 同时显式声明 scope、ownership mode 和是否写状态：一般 Project-bound
调用必须带可解析的本 Project 资源；只读 `discover_semantic_scopes` 是身份感知的 global-safe
发现入口，由运行时 principal 限制 Project，其他无资源全局工具为 org-only。`check_semantic_staleness` 会更新 derived
pointer 状态，因此按 `admin + org-only + mutates_state` 执行，而不是只读健康检查。

## 当前推荐流程

1. 新消费会话先用 `discover_semantic_scopes` 分页发现授权 Project/Ontology；已有明确范围的客户端
   可直接查询。建模会话再用 Project Build Context 恢复 Project 事实。
2. 列出当前 Modeling Workflow Artifact 版本、Execution Event timeline 和 question current heads，
   不依赖旧聊天或本地 ledger 恢复。
3. 通过 Brief、Interview Answer 和 Competency Question 澄清需求；先保存 Business Knowledge Pack
   与 Modeling Coverage Matrix，再进入建模。
4. 外部 Agent 自行读取资料理解和核对语义；三个子角色
   使用独立只读上下文，只有主 Agent 持有 MCP credential。
5. 主 Agent 保存模型草案，调用 `submit_modeling_batch` dry-run；独立 reviewer 读取原资料、产物和
   每个带 fingerprint 的 Finding，只有 PASS 才进入 apply。
6. 主 Agent 获取 lease 并 apply exact reviewed batch；不经过旧 Proposal/Review/Publish 队列。
7. 用 Context Query、scoped SPARQL、read model 和 validation 验证，保存 verification
   artifact/event、checkpoint，并完成或取消 Build Session。

v4 R4.0-012 停用 Evidence 与完整 lineage：专用工具与旧 provenance 别名不再注册，
候选及 Batch 不接受追溯字段，正常检索不查询追溯链，也不要求 Agent 留证或补证。
工具响应定位、写入回执、审批、CQ 和独立验收记录继续保留；无历史只读替代工具。
当前 Team 入口为 [v4 Task](../../modeling_team/tasks/r4-0-012-tracing-suspension.yaml)，
复用现有多切片与 CQ Profile；旧追溯 Task 仅保留历史定义，不作为当前运行入口。

平台返回结构化语义上下文，不生成最终自然语言答案，也不代替外部 Agent 调用目标系统。

`discover_semantic_scopes` 接受可选 `query`、`queryable`、`cursor` 和 `limit`，返回扁平、稳定排序
的 Project/Ontology 候选。Project-bound credential 无需在参数中重复 Project ID；工具仍在服务层
先按当前认证主体过滤授权目录。返回的 `query_scope` 可直接传给 `query_semantic_context` 或
`semantic_sparql_query`，但发现结果不是授权或版本锁。
Cursor 还绑定当前认证主体的授权 Project 边界。配置 `SECRET_KEY` 后可跨 MCP/backend 进程和重启
验证；未配置时使用每个进程私有的随机完整性材料，因此跨进程或重启后的 cursor 会返回
`invalid_cursor`，调用方应重新开始发现。

R1.2-004 起 `query_semantic_context` 支持一次提交一组同主题的相关表达式：标准参数为
`queries: list[string]`（1–8 项，每项 trim 后 1–2000 字符、合计 ≤ 8000 字符），兼容参数
`query: string` 等价于单元素列表，二者必须提供且只提供一个。服务对去重后的规范化表达式只解析一次
范围、执行一次 embedding 批处理，再按证据层级、得分、表达式支持数和 R1.2-003 既有 tie-breaker
融合排序；输入顺序不影响打分或排序。匹配与上下文使用独立预算（`limit` 默认 20/最大 100；
`context_limit` 默认 100/最大 1000）和独立 cursor：`match_cursor` 继续下一页匹配，
`context_cursor` 只在当前匹配页内继续上下文。请求同时只能携带其中一种 cursor，且 cursor 必须与
当前 principal、Project/Ontology 范围、原始 `queries`、过滤、深度、页大小及绑定的
`workspace_version`/source signature 完全匹配；否则返回 `invalid_context_cursor`、
`context_cursor_mismatch` 或 `context_snapshot_changed`。响应新增 `query.queries`、
`query.normalized_queries`、`primary_matches[*].matched_queries`、`primary_matches[*].fusion`、
`related_context[*].root_paths`、`matches_page`、`context_page`。配置
`SEMANTIC_CONTEXT_QUERY_CURSOR_SIGNING_SECRET` 时 cursor 可跨进程重启继续验证；未配置时使用进程
私有随机完整性材料，并经 `GET /api/mcp/tools` 的 `capabilities.semantic_context_query` 字段声明
该限制、cursor 种类、生命周期与各项默认/上限。

## 返回与错误边界

多数业务工具通过 MCP runtime 返回 `{"ok": true, "data": ...}` 或
`{"ok": false, "error": ..., "error_code": ...}`；具体输入和返回仍以运行时 tool schema 与实现
为准，不能假设所有工具共享额外字段。session、lease、建模批次冲突和幂等语义由对应工具返回。
Artifact/Event 工具复用同一 service、R-008 Project resolver 与秘密扫描；外部调用不能自报
`platform_observed` 或 actor。Artifact/Event 重试必须复用原 client ID 和完全相同 payload。

当前未注册的旧 governance、catalog、connector、entity、fact、Evidence Artifact 上传和
Proposal/Review 工具不是可调用能力。R-009 查询诊断仍处于 Pending；旧 Agent Test 平台内 LLM 路径已移除。

## 完整运行时工具清单

下方区块由脚本维护，不要手工编辑。registry 变更后运行：

```bash
cd backend
uv run python ../scripts/sync-interface-docs.py --write
```

`query_semantic_context` 的 R4.0-008 合同与 [Context Query REST 说明](api.md) 共用服务：
可选 `semantic_roles` 只筛已声明的主命中角色，MCP 关联行默认 compact、主命中 full。
检查 `query.result_scope`、`recall.completeness`、双分页和 `context_page.expansion`；末页或
complete 的有界展开均不证明业务完整。脚本投影省略由 `projection.omitted_fields` 声明，可沿
已获准 IRI 以 full 补读。context cursor 独立恢复原匹配页；角色筛选与当前可见集合参与绑定。
无权与不存在保持同形；平台不执行规则脚本、数据库查询或外部调用。

R4.0-010 的 `get_semantic_read_model` 使用与 REST 相同的八个 mapping／metric model name：
四类资源各有 list/detail。返回的 `detail_fields` 解码 `mapping_definition` 与
`semantic_definition`；TableMapping 同时报告 `mapped_class` 或 `mapped_definition`，
EnumValueMeaning 可报告 `table_mapping`＋`column` 作用域，JoinMapping／MetricDefinition
保留其路径、角色、粒度、指标 contexts 与来源／Schema 定位。缺省、`null`、unknown 和冲突
按存储值返回，MCP 不把 source_key 或 schema_version 当作数据库权限、连接能力或已验证事实。
`get_ontology_read_model` 也接受这八个精确 model name，并通过 `entity_iri` 读取单个 mapping／
metric 资源；不存在或无权资源沿用该读取面的空结果合同，REST resource endpoint 的 `404` 语义
保持不变。

以 mapping／metric IRI 调用 `query_semantic_context` 时，固定结构化字段引用还会生成
`related_context` 的 `origin=derived_reference` 行。其 `data` 包含 `source_iri`、`target_iri`、
`predicate`、`field_path`／`source_path` 和 `derived_reference: true`；`id` 由 source、predicate、
字段路径和 target 稳定计算，因此可安全去重和续 cursor。该行是 JSON 引用的方向性投影，不是
新存储的 RDF statement。完整值先做语义访问过滤，受限嵌套引用在过滤后的计数和 cursor 中均不
出现。平台只读取映射说明与已声明引用，不执行 SQL、转换或外部数据库访问；数据库数据权限仍
由外部系统负责。

读取中的无效／多值注解会保留获准原始 statement，并在响应 warning 中返回
`annotation_read_diagnostic`；scope、cursor、RDF 依赖错误沿既有 `invalid_*`／snapshot 或
可重试依赖错误合同返回。修正范围或注解后可重新发起同一读取目标。

跨 Ontology 映射引用使用拥有方 Ontology 的 `reference_ontology_ids`。
Root／Protocol 通过现有 Ontology 更新接口声明同一 Project 内获准的依赖 ID；平台按这些模型
验证结构引用。读取通过 `ontology_id`／`ontology_ids` 指定且先授权，不隐式扩展依赖范围。
`get_ontology_workspace_context` 返回 Ontology 及模型状态，`get_semantic_read_model` 和
`export_semantic_ontology` 直接读取指定的模型；无需图集合或成员管理。

映射或声明依赖的写入仍必须走 Modeling Batch 的 `dry_run`／`apply_atomic`、Attempt、Project
fence 与恢复回执。MCP 的 `submit_semantic_edit`、canonical command 及 raw RDF import 遵循同一
边界；绕过 Batch 会返回 `mapping_batch_required`。依赖 Project 有未收敛写入时返回可恢复的
`mapping_reference_write_fenced`，客户端先读取／reconcile 原 Attempt 与 fence，再重试原目标。

bridge 成员／supersedes 修改若破坏存量引用，返回 `mapping_reference_scope_in_use`；先修订依赖映射
后可继续。引用校验范围不会自动扩大实际读取的 Graph Set／Ontology scope。

活动 Team Protocol facade（不属于下表的平台 MCP）公开 `build_unified_resource_binding_receipt`：
输入完整 governed `read_envelope`、candidate 和显式 Project／Ontology／workspace scope，输出实际
resource kind／id／IRI 与读证据绑定。`translate_candidate_to_batches` 使用该 receipt，并接受宿主
提供的 `semantic_base_iri`；该值来自注入的 modeling-context，不是 Modeling 候选字段。

R4.0-024 在同一 Team facade 增加只读 `inspect_model_associations`。Protocol 按挂载的
[检查合同](../../modeling_team/references/r4-0-024-model-check-contract.json)，使用现有
`semantic_sparql_query` 对获准 workspace 的 asserted 图执行固定四列 RDF 查询，分页至
`truncated=false`，最后以同一查询、`OFFSET 0`、`result_limit=1` 核对来源快照。Native 工具
消费未经改写的 `{request,response}` 页及最终读取、Project／Ontology／asserted graph scope、
注入的 `semantic_base_iri` 和可选增量 `focus_iris`，返回候选、未解析正式引用及可恢复的
覆盖／快照反馈。`coverage=complete` 只证明所提供读取完整且稳定，仍须核对完整获准成果
范围；`semantic_verdict` 始终为 `not_evaluated`。它不写资源、不授予生产完成或独立验收
PASS，Modeling 作业务处置，Protocol 经既有批准流程落实修复并复查。

<!-- BEGIN GENERATED MCP TOOL INVENTORY -->

| Category | Tool | Description | Required parameters | All parameters | Source |
| --- | --- | --- | --- | --- | --- |
| system | `check_platform_health` | Verify API and PostgreSQL are reachable without direct DB credentials. | - | - | `backend/app/mcp/tools/system.py` |
| interview | `get_build_context` | Deprecated alias for get_project_build_context; use the new tool. | project_id | project_id | `backend/app/mcp/tools/interview.py` |
| interview | `get_ontology_workspace_context` | Read Ontology model state, revision, and editability. | ontology_id | ontology_id | `backend/app/mcp/tools/interview.py` |
| interview | `get_project_brief` | Read Project Brief completeness and up to three high-value clarification items. | project_id | project_id | `backend/app/mcp/tools/interview.py` |
| interview | `list_competency_questions` | List ordered competency questions and their validation states. | project_id | include_inactive, project_id | `backend/app/mcp/tools/interview.py` |
| interview | `propose_competency_questions` | Create ordered draft competency questions; this does not approve them. | project_id, questions | project_id, questions | `backend/app/mcp/tools/interview.py` |
| interview | `repair_ontology_workspace` | Idempotently inspect or repair an Ontology's default semantic workspace. | ontology_id | dry_run, ontology_id | `backend/app/mcp/tools/interview.py` |
| interview | `save_interview_answer` | Save a user answer so Project Brief fields and questions can cite it. | answer, project_id | actor_id, answer, project_id, source_type | `backend/app/mcp/tools/interview.py` |
| interview | `update_project_brief` | Update and confirm interview fields with saved-answer source links. | project_id, update | project_id, update | `backend/app/mcp/tools/interview.py` |
| interview | `validate_competency_question` | Run the bound query definition and record pass/fail result. | question_id | question_id | `backend/app/mcp/tools/interview.py` |
| build_sessions | `acquire_ontology_lease` | Acquire or rotate this Build Session's exclusive Ontology write lease. | client_request_id, expected_session_revision, ontology_id, session_id | client_request_id, expected_session_revision, ontology_id, rotate_token, session_id | `backend/app/mcp/tools/build_sessions.py` |
| build_sessions | `cancel_build_session` | Idempotently cancel a Build Session and release all its leases. | client_request_id, expected_revision, reason, session_id | client_request_id, expected_revision, reason, session_id | `backend/app/mcp/tools/build_sessions.py` |
| build_sessions | `complete_build_session` | Idempotently complete a Build Session and release all its leases. | client_request_id, expected_revision, session_id, summary | client_request_id, expected_revision, session_id, summary, unresolved_items | `backend/app/mcp/tools/build_sessions.py` |
| build_sessions | `create_build_session` | Idempotently create a Project-scoped external Agent Build Session. | client_session_id, project_id | client_session_id, initial_checkpoint, previous_session_id, project_id | `backend/app/mcp/tools/build_sessions.py` |
| build_sessions | `create_modeling_workflow_artifact` | Create one immutable, idempotent workflow artifact version. | artifact_key, artifact_type, client_version_id, content, content_format, created_by_role, session_id, workflow_name, workflow_version | artifact_key, artifact_type, client_version_id, content, content_format, created_by_role, ontology_id, role_prompt_version, session_id, supersedes_workflow_artifact_id, workflow_name, workflow_version | `backend/app/mcp/tools/modeling_workflow.py` |
| build_sessions | `export_modeling_workflow_record` | Export the complete execution record as structured JSON or Markdown. | session_id | format, session_id | `backend/app/mcp/tools/modeling_workflow.py` |
| build_sessions | `get_build_session` | Read one Build Session's checkpoints, leases, and recovery context. | session_id | checkpoint_cursor, checkpoint_limit, session_id | `backend/app/mcp/tools/build_sessions.py` |
| build_sessions | `get_entity_statement_context` | Read the complete incident statement set for one exact live entity IRI.  This is intentionally a generic read projection.  Omitting ``workspace_version`` binds the authoritative current version, which the response and every opaque cursor carry; an explicit version must still equal the current version.  The opaque cursor binds Project/Ontology, exact entity IRI, workspace version, and a snapshot digest; callers must consume every page through ``complete=true`` before using the response as delete-impact evidence.  | entity_iri, ontology_id | cursor, entity_iri, ontology_id, page_size, workspace_version | `backend/app/mcp/tools/modeling_batches.py` |
| build_sessions | `get_modeling_batch` | Read immutable Items, Attempts, Findings, and recovery history. | batch_id | batch_id | `backend/app/mcp/tools/modeling_batches.py` |
| build_sessions | `get_modeling_context` | Read the authoritative current state from which further modeling starts. | ontology_id | ontology_id | `backend/app/mcp/tools/modeling_batches.py` |
| build_sessions | `get_modeling_execution_event` | Read one immutable Modeling Execution Event. | execution_event_id | execution_event_id | `backend/app/mcp/tools/modeling_workflow.py` |
| build_sessions | `get_modeling_workflow_artifact` | Read one immutable workflow artifact version. | workflow_artifact_id | workflow_artifact_id | `backend/app/mcp/tools/modeling_workflow.py` |
| build_sessions | `get_ontology_read_model` | Resolve the default workspace and read a fixed Ontology semantic model. | model_name, ontology_id | allow_stale_derived, class_iri, entity_iri, field_set, include, kind, limit, model_name, ontology_id, q | `backend/app/mcp/tools/modeling_batches.py` |
| build_sessions | `get_project_build_context` | Read Project-wide platform facts and recoverable Agent session state. | project_id | project_id, recent_session_cursor, recent_session_limit | `backend/app/mcp/tools/build_sessions.py` |
| build_sessions | `list_modeling_execution_events` | List a stable sequence page from a Build Session's execution timeline. | session_id | cursor, event_type, limit, phase, session_id | `backend/app/mcp/tools/modeling_workflow.py` |
| build_sessions | `list_modeling_workflow_artifacts` | List stable pages of workflow artifact versions for a Build Session. | session_id | artifact_key, artifact_type, current_only, cursor, limit, ontology_id, session_id | `backend/app/mcp/tools/modeling_workflow.py` |
| build_sessions | `list_ontology_modeling_batches` | List Modeling Batches across Sessions for an Ontology. | ontology_id | created_from, created_to, cursor, limit, ontology_id, status | `backend/app/mcp/tools/modeling_batches.py` |
| build_sessions | `list_session_modeling_batches` | List Modeling Batches created in one Build Session. | session_id | cursor, limit, session_id, status | `backend/app/mcp/tools/modeling_batches.py` |
| build_sessions | `record_modeling_execution_event` | Append one idempotent event to a Build Session's execution record. | actor_role, client_event_id, event_type, phase, report_source, session_id, status, summary, workflow_name, workflow_version | actor_role, agent_model, agent_runtime, answer_reason, answer_text, blockers, client_event_id, cost_summary, decisions, duration_ms, event_type, expected_question_head_event_id, input_workflow_artifact_ids, interview_answer_id, next_step, occurred_at, ontology_id, output_workflow_artifact_ids, phase, quality_issues, question_id, question_state, question_text, reasoning_effort, rejected_alternatives, related_resources, report_source, role_prompt_version, session_id, status, summary, supersedes_execution_event_id, token_usage, unresolved_items, workflow_name, workflow_version | `backend/app/mcp/tools/modeling_workflow.py` |
| build_sessions | `release_ontology_lease` | Idempotently release this Build Session's Ontology write lease. | client_request_id, expected_lease_revision, lease_token, ontology_id, session_id | client_request_id, expected_lease_revision, lease_token, ontology_id, session_id | `backend/app/mcp/tools/build_sessions.py` |
| build_sessions | `renew_ontology_lease` | Renew a valid Ontology lease using its opaque token. | client_request_id, expected_lease_revision, lease_token, ontology_id, session_id | client_request_id, expected_lease_revision, lease_token, ontology_id, session_id | `backend/app/mcp/tools/build_sessions.py` |
| build_sessions | `resume_build_session` | Resume an active Build Session without changing its revision. | client_request_id, expected_revision, session_id | client_request_id, expected_revision, session_id | `backend/app/mcp/tools/build_sessions.py` |
| build_sessions | `save_build_checkpoint` | Idempotently append an Agent-reported Build Checkpoint. | client_checkpoint_id, current_step, expected_revision, phase, session_id | blockers, client_checkpoint_id, current_step, expected_revision, failure, next_step, ontology_id, phase, related_batch_id, session_id, summary | `backend/app/mcp/tools/build_sessions.py` |
| build_sessions | `submit_modeling_batch` | Dry-run or idempotently apply one immutable Ontology Modeling Batch. | client_batch_id, expected_workspace_version, idempotency_key, items, ontology_id, session_id | client_batch_id, expected_workspace_version, idempotency_key, items, lease_token, mode, ontology_id, session_id | `backend/app/mcp/tools/modeling_batches.py` |
| semantic | `add_semantic_protection_set_members` | Batch-add resource IRIs to a protection set (idempotent). | members, protection_set_id | actor, members, protection_set_id | `backend/app/mcp/tools/protection_sets.py` |
| semantic | `compile_and_apply_canonical_command` | Compile and apply a structured product command through the Phase 7 canonical writer. | command_kind, ontology_id, payload | actor, command_kind, ontology_id, payload, reason | `backend/app/mcp/tools/semantic.py` |
| semantic | `create_semantic_migration_run` | Create a Phase 7 migration run in dry_run/shadow/dual_write_backfill/cutover/rollback mode. | mode, scope_type | batch_size, created_by, mode, scope_id, scope_type, target_ontology_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `create_semantic_protection_set` | Create a protection set (named resource IRIs + OR-semantics grants). | name, project_id | actor, allowed_grants, description, members, name, project_id | `backend/app/mcp/tools/protection_sets.py` |
| semantic | `cutover_semantic_migration_run` | Execute the guarded RDF-primary cutover for a Phase 7 migration run. | run_id | run_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `delete_semantic_protection_set` | Delete an empty protection set; non-empty sets are rejected. | protection_set_id | actor, protection_set_id | `backend/app/mcp/tools/protection_sets.py` |
| semantic | `discover_semantic_scopes` | Discover authorized Project/Ontology query scopes and readiness. | - | cursor, limit, query, queryable | `backend/app/mcp/tools/semantic.py` |
| semantic | `export_semantic_ontology` | Export an Ontology model as Turtle, TriG, or JSON-LD. | ontology_id | allow_stale_derived, format, include, ontology_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `get_semantic_governance_status` | Return a governance status summary: graph counts, editability, derived staleness. | - | - | `backend/app/mcp/tools/semantic.py` |
| semantic | `get_semantic_read_model` | Read a compact graph-derived business JSON read model for an Ontology. | model_name, ontology_id | allow_stale_derived, entity_iri, include, limit, model_name, ontology_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `inspect_semantic_projection_status` | Inspect projection freshness by Ontology and projection kind. | - | ontology_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `list_semantic_edit_audits` | List recent governed semantic edit audit records. | - | limit | `backend/app/mcp/tools/semantic.py` |
| semantic | `list_semantic_protection_sets` | List the protection sets of one authorized Project. | project_id | project_id | `backend/app/mcp/tools/protection_sets.py` |
| semantic | `preflight_semantic_migration` | Run Phase 7 migration preflight for a scope. | scope_type | scope_id, scope_type, target_ontology_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `query_semantic_context` | Recall structured semantic context from one Project's current Ontologies. | project_id, scope_mode | assertion_types, context_cursor, context_detail, context_limit, depth, limit, match_cursor, ontology_ids, project_id, queries, query, resource_types, scope_mode, search_mode, semantic_roles | `backend/app/mcp/tools/semantic.py` |
| semantic | `remove_semantic_protection_set_members` | Batch-remove resource IRIs from a protection set. | protection_set_id, resource_iris | actor, protection_set_id, resource_iris | `backend/app/mcp/tools/protection_sets.py` |
| semantic | `rollback_semantic_migration_run` | Roll back a Phase 7 cutover and restore legacy-primary mode. | run_id | run_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `run_next_semantic_migration_batch` | Execute the next pending batch of a Phase 7 migration run. | run_id | run_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `run_semantic_migration_parity_check` | Run parity checks for a Phase 7 migration run. | run_id | check_name, run_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `semantic_sparql_query` | Run scoped read-only SPARQL against current Ontology semantic state. | project_id, query, scope_mode | ontology_ids, project_id, query, result_limit, scope_mode, timeout_seconds | `backend/app/mcp/tools/semantic.py` |
| semantic | `start_semantic_projection_job` | Request a projection rebuild job and (for non-dry-run modes) execute it. | ontology_id, projection_kind, projection_version | allow_stale_derived, include, mode, ontology_id, projection_kind, projection_version | `backend/app/mcp/tools/semantic.py` |
| semantic | `submit_semantic_edit` | Submit a governed RDF/SPARQL Update semantic edit with audit metadata. | content, format, ontology_id | actor, content, format, ontology_id, reason, warning_state | `backend/app/mcp/tools/semantic.py` |
| semantic | `update_semantic_protection_set` | Update a protection set name, description, or allowed_grants. | protection_set_id | actor, allowed_grants, description, name, protection_set_id | `backend/app/mcp/tools/protection_sets.py` |

<!-- END GENERATED MCP TOOL INVENTORY -->

## 宿主 Team 启动配置（R4.0-019）

独立 `modeling-team-host` stdio 服务的 [host_ops_mcp](../../modeling_team/host_ops_mcp.py)
不属于上表平台 MCP，也不挂载给生产角色。现有 `start_run` 和 `resume_from_checkpoint`
新增可选 `service_tier: str = "unset"`：`unset` 保留 child 继承环境，`fast` 在本次 child
环境副本设置 `MODELING_TEAM_CODEX_SERVICE_TIER=fast`，`default` 表示明确 normal/off，
仅从该副本移除此变量。宿主环境、其他存活进程和旧线程配置不变；非法值沿既有
`launch_arguments_invalid` 返回可重试错误，未启动 child。

请求保存在现有 `.host-launches/<new-run-id>.json` 的 `service_tier` 字段，不保存完整环境
或凭据；此字段仅证明启动传递请求，实际配置须核对角色隔离 TOML。未传值记录为 `unset`，
不能把继承导致的实际 fast 冒充用户明确请求。`start_run` 继续显式 `model_profile`；
`resume_from_checkpoint(mode="acceptance")` 可覆盖该 profile，production resume 仍使用
source profile，不支持覆盖。production/acceptance 计数仍分别按原合同为 1/0。

直接 Team CLI 不新增 `--service-tier` 旗标，沿已有 per-command env 路径处理；详细命令、
角色 model/requested/effective effort、实际 config 白名单及 unsupported/unverified 边界见
[Session 配置运行参考](../../skills/modeling-dev-loop/references/team-runbook.md#session-配置传递与核对r40-019)。

`resume_from_checkpoint` 另有可选 `write_tail_run_id: str | null`（R3.0-015 双源生产接续，
仅 `mode="production"`）：当检查点包来自 `source_run_id`、但包保存之后存在一个已死继任
run 写过写尾时，该参数显式命名写尾 run（对应 CLI `--write-tail-run-id`）。包来源与摘要
不变；写尾 run 必须位于源 run 恢复链上且其 origin 绑定的 checkpoint 与所选包一致，并按
同一写者证据结算，否则返回 `write_tail_unrelated`/`write_tail_checkpoint_binding`/
`source_active`/`write_unreconciled` 等类型化拒绝。acceptance 模式或非法 run id 在启动前
即拒绝（`launch_arguments_invalid`）；未传时单源行为不变。

## 独立 Delivery Host 工具（R4.0-023）

上述宿主服务保留 S1 的 12 项及 S2 的 8 项原语义，另提供以下 8 项交付接线。
它们不进入平台 MCP inventory 或生产角色权限。Delivery 会话通过原生结构化工具调用
使用同一操作层；业务入口只输出显式发布的业务消息，不透传内部工具响应。

| 工具 | 输入／作用 | 完成依据与限制 |
| --- | --- | --- |
| `submit_instruction` | run ID、`user_supplement`／`delivery_guidance`、原文、来源／授权、request ID | 既有 FIFO 与 Runner 实际投递回执；不伪造问题绑定 |
| `start_evaluation` | run／freeze、cq-acceptance 或 public-feedback、交接／checkpoint、题集与模型配置 | 包装现有 CLI，记录调用与 PID；不提供 unexecuted-report |
| `get_evaluation_status` | operation ID | 进程状态及本次新报告的真实请求绑定；旧报告、错误绑定或未执行不算有效结果 |
| `start_repair` | repair-task 文件、指定 executor／model／effort、授权及 issue | 文件 stdin 与 typed argv；修复 workspace 隔离，启动不等于生效 |
| `get_repair_status` | operation ID | 退出、受控日志及结果证据，`effect_verified` 不因 exit 0 变为 true |
| `stop_delivery_operation` | operation ID、reason | 核对本次拥有的 PID／进程组后终止，保留日志／回执；不控制无关进程 |
| `read_platform_record` | batch／session／ontology_batches 的 ID 与精确 project／ontology scope | 既有只读读回；返回记录与读取次数，无 apply/delete |
| `reconcile_write_state` | 本次 run、project／ontology scope | 既有写者证据与 Batch／Attempt／资源／回执对账；不补做隐藏根因查询 |

`start_run`／`resume_from_checkpoint` 新增可选 `host_session_ref` 透传；它仅关联宿主记录，
不授予权限或证明 semantic start。Delivery 原生工具投影隐藏 `repository_root`、
`base_url` 和 `host_session_ref`，由部署宿主注入。

本地入口为 `python -m modeling_team delivery --config <yaml> [--resume]`。
独立原生会话另有宿主专用 `verify_repair`／`get_repair_verification_status`，按绑定修复
运行固定 repo 检查与明确授权的本地服务部署。它们不属于上述 stdio MCP 的 28 项清单，
不开放通用 shell；实际命令、退出码、健康与目标摘要保存在交付私有回执中，不能代替语义验收。
部署、授权、业务输入和证据边界见 [实施记录](../delivery/records/2026-10-08-r4-0-023-delivery-agent.md)。
