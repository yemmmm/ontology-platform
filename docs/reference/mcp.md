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
4. 外部 Agent 自行读取资料，以 Evidence Reference 保存实际使用的文档名和原文片段；三个子角色
   使用独立只读上下文，只有主 Agent 持有 MCP credential。
5. 主 Agent 保存模型草案，调用 `submit_modeling_batch` dry-run；独立 reviewer 读取原资料、产物和
   每个带 fingerprint 的 Finding，只有 PASS 才进入 apply。
6. 主 Agent 获取 lease 并 apply exact reviewed batch；不经过旧 Proposal/Review/Publish 队列。
7. 用 Context Query、scoped SPARQL、read model、validation 和 lineage 验证，保存 verification
   artifact/event、checkpoint，并完成或取消 Build Session。

平台返回结构化语义上下文，不生成最终自然语言答案，也不代替外部 Agent 调用目标系统。

`discover_semantic_scopes` 接受可选 `query`、`queryable`、`cursor` 和 `limit`，返回扁平、稳定排序
的 Project/Ontology 候选。Project-bound credential 无需在参数中重复 Project ID；工具仍在服务层
先按当前认证主体过滤授权目录。返回的 `query_scope` 可直接传给 `query_semantic_context` 或
`semantic_sparql_query`，但发现结果不是授权或版本锁。
Cursor 还绑定当前认证主体的授权 Project 边界。配置 `SECRET_KEY` 后可跨 MCP/backend 进程和重启
验证；未配置时使用每个进程私有的随机完整性材料，因此跨进程或重启后的 cursor 会返回
`invalid_cursor`，调用方应重新开始发现。

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

<!-- BEGIN GENERATED MCP TOOL INVENTORY -->

| Category | Tool | Description | Required parameters | All parameters | Source |
| --- | --- | --- | --- | --- | --- |
| system | `check_platform_health` | Verify API and PostgreSQL are reachable without direct DB credentials. | - | - | `backend/app/mcp/tools/system.py` |
| interview | `get_build_context` | Deprecated alias for get_project_build_context; use the new tool. | project_id | project_id | `backend/app/mcp/tools/interview.py` |
| interview | `get_ontology_workspace_context` | Read the default Graph Set, graph roles, revisions, and editability. | ontology_id | ontology_id | `backend/app/mcp/tools/interview.py` |
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
| semantic | `associate_evidence_reference` | Create or reuse references and associate them with one concrete modeling result. | ontology_id, project_id, target_id, target_type | actor, client_item_id, edit_audit_id, evidence, evidence_reference_ids, graph_set_id, ontology_id, project_id, target_id, target_type | `backend/app/mcp/tools/evidence.py` |
| semantic | `check_semantic_staleness` | Reconcile derived-result staleness and return current/stale counts. | - | - | `backend/app/mcp/tools/semantic.py` |
| semantic | `compile_and_apply_canonical_command` | Compile and apply a structured product command through the Phase 7 canonical writer. | command_kind, graph_set_id, payload | actor, command_kind, graph_set_id, payload, reason, shape_graph_iris | `backend/app/mcp/tools/semantic.py` |
| semantic | `create_evidence_reference` | Create or idempotently reuse a project evidence reference. | document_name, excerpt, project_id | actor, document_name, excerpt, project_id | `backend/app/mcp/tools/evidence.py` |
| semantic | `create_semantic_migration_run` | Create a Phase 7 migration run in dry_run/shadow/dual_write_backfill/cutover/rollback mode. | mode, scope_type | batch_size, created_by, mode, scope_id, scope_type, target_graph_set_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `cutover_semantic_migration_run` | Execute the guarded RDF-primary cutover for a Phase 7 migration run. | run_id | run_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `describe_semantic_graph_set` | Return graph-set membership, source signature, and current derived pointers. | graph_set_id | graph_set_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `discover_semantic_scopes` | Discover authorized Project/Ontology query scopes and readiness. | - | cursor, limit, query, queryable | `backend/app/mcp/tools/semantic.py` |
| semantic | `export_semantic_graph_set` | Export a graph set as Turtle, TriG, or JSON-LD. | graph_set_id | allow_stale_derived, format, graph_set_id, include | `backend/app/mcp/tools/semantic.py` |
| semantic | `get_evidence_reference` | Read one evidence reference and its modeling-result associations. | reference_id | reference_id | `backend/app/mcp/tools/evidence.py` |
| semantic | `get_ontology_lineage` | Read bounded statement, resource, or Rule Definition lineage for an Ontology. | ontology_id, target_id, target_type | include_history, limit, max_depth, ontology_id, target_id, target_type | `backend/app/mcp/tools/semantic.py` |
| semantic | `get_semantic_governance_status` | Return a governance status summary: graph counts, editability, derived staleness. | - | - | `backend/app/mcp/tools/semantic.py` |
| semantic | `get_semantic_read_model` | Read a compact graph-derived business JSON read model for a graph set. | graph_set_id, model_name | allow_stale_derived, graph_set_id, include, limit, model_name | `backend/app/mcp/tools/semantic.py` |
| semantic | `inspect_semantic_projection_status` | Inspect projection freshness by graph set and projection kind. | - | graph_set_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `inspect_semantic_statement_provenance` | Deprecated compatibility wrapper; use get_ontology_lineage. | graph_set_id, statement_iri | graph_set_id, include, statement_iri | `backend/app/mcp/tools/semantic.py` |
| semantic | `list_evidence_references` | List project evidence references without loading complete source documents. | project_id | limit, offset, project_id, search | `backend/app/mcp/tools/evidence.py` |
| semantic | `list_semantic_derived_pointers` | List derived-result pointers for reasoning/rule results. | - | graph_set_id, result_kind, status | `backend/app/mcp/tools/semantic.py` |
| semantic | `list_semantic_edit_audits` | List recent governed semantic edit audit records. | - | limit | `backend/app/mcp/tools/semantic.py` |
| semantic | `preflight_semantic_migration` | Run Phase 7 migration preflight for a scope. | scope_type | scope_id, scope_type, target_graph_set_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `query_semantic_context` | Recall structured semantic context from one Project's current Ontologies. | project_id, query, scope_mode | assertion_types, depth, limit, ontology_ids, project_id, query, resource_types, scope_mode, search_mode | `backend/app/mcp/tools/semantic.py` |
| semantic | `rollback_semantic_migration_run` | Roll back a Phase 7 cutover and restore legacy-primary mode. | run_id | run_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `run_next_semantic_migration_batch` | Execute the next pending batch of a Phase 7 migration run. | run_id | run_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `run_semantic_migration_parity_check` | Run parity checks for a Phase 7 migration run. | run_id | check_name, run_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `run_semantic_reasoning` | Run OWL reasoning over a graph set and persist the result graph. | graph_set_id | engine_version, graph_set_id, persist_result_graph, shape_version, tasks | `backend/app/mcp/tools/semantic.py` |
| semantic | `run_semantic_rule` | Run a single rule, a named group, or all rules for a graph set. | graph_set_id | actor, engine_version, graph_set_id, promote_pointer, rule_definition_id, rule_definition_ids, rule_iri | `backend/app/mcp/tools/semantic.py` |
| semantic | `run_semantic_validation` | Run SHACL validation over a graph set, persisting the report graph and run metadata. | graph_set_id | actor, graph_set_id, persist_report_graph, reasoning_result_graph_iri, shape_graph_iris, shape_version, validation_scope | `backend/app/mcp/tools/semantic.py` |
| semantic | `semantic_sparql_query` | Run scoped read-only SPARQL against current Ontology semantic state. | project_id, query, scope_mode | ontology_ids, project_id, query, result_limit, scope_mode, timeout_seconds | `backend/app/mcp/tools/semantic.py` |
| semantic | `start_semantic_projection_job` | Request a projection rebuild job and (for non-dry-run modes) execute it. | graph_set_id, projection_kind, projection_version | allow_stale_derived, graph_set_id, include, mode, projection_kind, projection_version | `backend/app/mcp/tools/semantic.py` |
| semantic | `submit_semantic_edit` | Submit a governed RDF/SPARQL Update semantic edit with audit metadata. | content, format | actor, content, format, reason, shape_graph_iris, target_graph_iri, validate, warning_state | `backend/app/mcp/tools/semantic.py` |
| semantic | `submit_semantic_rule_definition` | Create or reuse an immediately executable platform rule definition. | body, language, name, ontology_id, rule_iri | body, created_by, input_roles, language, name, ontology_id, output_kind, priority, requires_review, rule_iri, uses_inferred_facts | `backend/app/mcp/tools/semantic.py` |

<!-- END GENERATED MCP TOOL INVENTORY -->
