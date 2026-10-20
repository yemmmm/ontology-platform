# OntoWeave MCP 工具

本文档描述当前 FastMCP 进程实际注册的工具。完整清单来自 `mcp.list_tools()`，并通过现有
`app.api.mcp_catalog._enumerate_tools()` 补充 category 和源文件。

## R4.4-001 Team 工作展台（独立本地工具）

这些工具由 Team Transport／Host 提供，不注册到业务平台 MCP。
生产端点绑定 run／Agent 身份，提供 `update_work_card(card)`、
`resolve_work_request(request_id,resolution,note,update_id)`、`get_work_board(...)`；
`send_team_message` 保留旧合同，增加可选 `work_request`（request／feedback）。
请求 UUID 和反馈／关闭 update UUID 在首次调用前生成，重试复用；同身份不同内容返回
`work_request_conflict`。同一请求供双方投影，反馈不自动满足依赖，resolved 不发送确认消息。
回执分别报告 record／message 状态；`runtime_accepted` 只表示 Adapter 接受，不表示对方完成。

Host MCP 新增只读 `get_team_work_board(run_id,agent_id?,request_id?,view?,from_time?,to_time?,
record_seq?,cursor?,source_ref?,limit=25,include_statistics=false)`。默认 current；history
返回获准变化；version 需要 agent_id 与准确的卡片 record_seq。时间须带时区，按半开
区间筛选历史。页先按权限过滤，返回各集合 total／returned／complete 及统一 continuation；
续读保持原选择并传 cursor。source_ref 绑定 path／byte_length／sha256／末序号，来源变化
报 source_changed。Delivery 由会话绑定流程投影，模型不能选择 viewer 权限。
请求内较长反馈及消息列表仅展示最近5条，完整数量、覆盖与原 history 定位一并返回。
单次卡片／跟踪摘要最多16000 UTF-8字节，超限可修正为摘要及原件引用；不限制目标条数。

本地用户／宿主也可运行以下只读命令（不调用 Provider）：

```sh
backend/.venv/bin/python -m modeling_team work-board --run-id RUN
backend/.venv/bin/python -m modeling_team work-board --run-id RUN --agent AGENT --history --with-statistics --json
backend/.venv/bin/python -m modeling_team work-board --run-id RUN --agent AGENT --record-seq 42
backend/.venv/bin/python -m modeling_team work-board --run-id RUN --history --archive-ref evidence/work-board-retrospectives/snapshot-FINGERPRINT/index.json
```

CLI 还支持 `--from`、`--to`、`--cursor`、`--source-ref`（返回的 JSON）及 `--limit`。
统计直接引用019／036已发布结果，按真实成员／会话列一次；历史时间过滤不改统计窗口，
不分摊每卡精确token，不返回隐藏成员的总量或占比。关闭发布后附属生成私有历史快照及
统计版本索引，查询旧索引不混入最新统计。归档失败不改变原关闭、清理或统计 ready。
卡片正文与 numeric 报告分文件保存；缺卡、坏行、旧run、未知送达与缺统计均显式披露。

## R4.0-001 反馈工具

`submit_semantic_feedback` 是与召回并列的 read + PROJECT_RESOURCE 工具：
feedback_id、query_request、reasons、description、可选 result_snapshot 和
snapshot_complete，调用同一关系持久化服务，与 REST 共用身份、归属、幂等及错误合同。
回执只表示 received；不启动建模、不修改本体，不依赖 Team 或 candidate 写门。
快照是私有客户端报告，授权检查不把其中标识作为资源存在性探测输入。

`list_semantic_feedback`（project_id、pending_only、limit、cursor）、
`get_semantic_feedback`（feedback_id）、`record_semantic_feedback_resolution`
（feedback_id、resolution）均为内部 admin + PROJECT_RESOURCE 工具；反馈 ID 解析到
记录的真实项目。它们不自动加入 Consumer／生产角色／Examiner／Judge 的工具目录。
resolution、分页及超限合同见 [REST 接口](api.md#r40-001-独立召回反馈)。
保存/处理操作数据不会绕开业务模型写门；即使模型写门关闭仍可保存反馈，但不取得模型
修正权。MCP 错误使用相同服务 code，例如 feedback_identity_conflict、
feedback_snapshot_too_large、feedback_verification_stale 与 dependency_error。

## R4.0-027 模型状态绑定

当前读取、索引、分页与交接使用 Ontology 的非负整数 `model_revision`（包括 `0`）。
Batch 必须提交整数 `expected_model_revision`；旧 `expected_workspace_version` 字段与
字符串哈希不再有效。漂移仍返回 `workspace_revision_conflict`，详情包含
`current_model_revision`；重新读取后使用新的幂等键继续。Attempt 的
`workspace.expected_version/before_version/after_version` 保留现有回执结构，值均为编号。
模型写入已提交才推进编号，dry-run、失败未写入、索引重建和搜索配置变化不推进。
Embedding／投影配置仍单独校验；旧索引降级为词面召回，重建成功后恢复当前向量索引。
恢复未收敛时，现有写入围栏阻止将不确定 RDF 内容作为稳定模型读取；反馈指向待协调 Attempt。
迁移 `0035_ontology_model_revision` 保留原 Ontology 编号与历史哈希列，不翻译旧回执。
旧分页游标须从第一页重读；旧交接与未完成 Attempt 须重新读取并准备新的编号绑定。
检查点和冻结证据保留原样，不改写历史记录为新状态。

## 启动与配置

MCP 服务展示名为 `OntoWeave`；现有客户端配置键 `ontology-platform`／`ontology_platform`
与工具名称保持不变。

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
5. 当前统一图路径由 Modeling 调用 `modeling_submit_model_changes`，提交完整候选引用及显式变更意图。
   程序转换、绑定真实 Session／lease／revision，并在单次 `apply_atomic` 内校验和原子写入。
6. 新模型 Batch 的 `dry_run` 已退役，不要求 Protocol 翻译审批或成功证明；历史读取保留。
   已确认成功后进行获准自然语言召回、实际 IRI 展开及必要完整定义自查，保留索引和完整性限制。
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
`model_revision` 完全匹配；否则返回 `invalid_context_cursor`、
`context_cursor_mismatch` 或 `context_snapshot_changed`。响应新增 `query.queries`、
`query.normalized_queries`、`primary_matches[*].matched_queries`、`primary_matches[*].fusion`、
`related_context[*].root_paths`、`matches_page`、`context_page`。配置
`SEMANTIC_CONTEXT_QUERY_CURSOR_SIGNING_SECRET` 时 cursor 可跨进程重启继续验证；未配置时使用进程
私有随机完整性材料，并经 `GET /api/mcp/tools` 的 `capabilities.semantic_context_query` 字段声明
该限制、cursor 种类、生命周期与各项默认/上限。

R4.3-017 为 `query_semantic_context` 增加 `expansion_strategy`（`adaptive` 或 `fixed`），缺省为
`adaptive`；`depth` 可省略，adaptive／fixed 的缺省上限分别为 3／1，显式 0–3 始终是上限。
精确 IRI 查询保持 fixed 深度 1 的读取合同，不调用自适应评分。能力目录公布 adaptive 选择配置、
策略相关深度和完整性边界；`complete` 只覆盖当前授权页的 selected subgraph 或 requested depth，
不证明业务完整。Context Query cursor 为 v5，context cursor 绑定服务端 opaque snapshot 与选择配置，
旧 v4 及更早版本 token 需要无 cursor 重新查询。

R4.3-018 增加 `context_order=relevance|graph_distance`，自然语言缺省 relevance，独立于
扩展策略；精确 IRI 的解析顺序为 graph_distance，不调用周边评分。对当前根页已取得、
获准且输出筛选合格的周边先合并去重，完整候选各评一次，再按分数降序（同分用原完整
稳定键）排序和分页；0 分也保留，不新增淘汰。完整业务值、条件、例外、未知及真实路径
用于评分，路径只解释当前候选的贡献；preview 不返回完整评分材料。
`related_context[*].relevance` 在 full／compact／preview 都保留 `relevance_score`、
`relevance_scale=[0,3]`、实际 `relevance_model`、`relevance_version=jev-evidence-relevance-v1`
与 `relevance_status=scored|unavailable|not_requested`。`context_page.ranking` 独立于主命中／探索，
声明 requested_order／effective_order、status=applied|degraded|not_requested、
version=related-context-relevance-v1、score_version／score_scale、model、reason、candidate_count／
scored_count、filtered_count（恒0）、elapsed_seconds 和 snapshot_reused；ranking_scope 为
current_match_page_bounded_context。applied 不证明业务完整或未探索内容更差。
每根页最多评分512个候选；超过上限仍返回完整原集合。主命中、探索、周边共享默认15秒
Jev额度，周边另受入口起30秒软截止；单问题／批次为30000／60000 UTF-8字节，不截条件。
评分关闭、超时、输入过大、无效结果、完整值读取故障或模型漂移时整集合沿旧序，全部
分数null／unavailable，带 context_ranking_degraded；空集合／不展开／显式旧序为not_requested。
两种扩展的 relevance（含降级）均冻结完整集合及排名；context续页不召回、扩图或评分。
排序与配置、根页、投影、主体、授权、源修订和索引绑定cursor v5；快照过期、淘汰、重启
或配置变化须无cursor首查。稳定签名不使进程内快照跨重启存活。新增可见／撤权按原409
context_snapshot_changed；纯隐藏变化不产生公开失效信号，核验依赖失败沿可重试错误。
评分故障不会绕过授权或源修订核验。snapshot_reused仅为重放可归一化的运行字段，
业务data内同名字段和实际分数／顺序仍须逐值比较。真实效果仍待独立同集对照及业务验收。

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

映射或声明依赖的写入仍必须走 Modeling Batch 的请求内校验／`apply_atomic`、Attempt、Project
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
| build_sessions | `get_entity_statement_context` | Read the complete incident statement set for one exact live entity IRI.  This is intentionally a generic read projection.  Omitting ``model_revision`` binds the authoritative current version, which the response and every opaque cursor carry; an explicit version must still equal the current version.  The opaque cursor binds Project/Ontology, exact entity IRI, model revision, and a snapshot digest; callers must consume every page through ``complete=true`` before using the response as delete-impact evidence.  | entity_iri, ontology_id | cursor, entity_iri, model_revision, ontology_id, page_size | `backend/app/mcp/tools/modeling_batches.py` |
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
| build_sessions | `submit_modeling_batch` | Idempotently apply one immutable Ontology Modeling Batch. | client_batch_id, expected_model_revision, idempotency_key, items, ontology_id, session_id | client_batch_id, expected_model_revision, idempotency_key, items, lease_token, mode, ontology_id, session_id | `backend/app/mcp/tools/modeling_batches.py` |
| semantic | `add_semantic_protection_set_members` | Batch-add resource IRIs to a protection set (idempotent). | members, protection_set_id | actor, members, protection_set_id | `backend/app/mcp/tools/protection_sets.py` |
| semantic | `compile_and_apply_canonical_command` | Compile and apply a structured product command through the Phase 7 canonical writer. | command_kind, ontology_id, payload | actor, command_kind, ontology_id, payload, reason | `backend/app/mcp/tools/semantic.py` |
| semantic | `create_semantic_migration_run` | Create a Phase 7 migration run in dry_run/shadow/dual_write_backfill/cutover/rollback mode. | mode, scope_type | batch_size, created_by, mode, scope_id, scope_type, target_ontology_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `create_semantic_protection_set` | Create a protection set (named resource IRIs + OR-semantics grants). | name, project_id | actor, allowed_grants, description, members, name, project_id | `backend/app/mcp/tools/protection_sets.py` |
| semantic | `cutover_semantic_migration_run` | Execute the guarded RDF-primary cutover for a Phase 7 migration run. | run_id | run_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `delete_semantic_protection_set` | Delete an empty protection set; non-empty sets are rejected. | protection_set_id | actor, protection_set_id | `backend/app/mcp/tools/protection_sets.py` |
| semantic | `discover_semantic_scopes` | Discover authorized Project/Ontology query scopes and readiness. | - | cursor, limit, query, queryable | `backend/app/mcp/tools/semantic.py` |
| semantic | `export_semantic_ontology` | Export an Ontology model as Turtle, TriG, or JSON-LD. | ontology_id | allow_stale_derived, format, include, ontology_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `get_semantic_feedback` | Internal admin: read one private submission and its append-only resolution history. | feedback_id | feedback_id | `backend/app/mcp/tools/semantic_feedback.py` |
| semantic | `get_semantic_governance_status` | Return a governance status summary: graph counts, editability, derived staleness. | - | - | `backend/app/mcp/tools/semantic.py` |
| semantic | `get_semantic_read_model` | Read a compact graph-derived business JSON read model for an Ontology. | model_name, ontology_id | allow_stale_derived, entity_iri, include, limit, model_name, ontology_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `inspect_semantic_projection_status` | Inspect projection freshness by Ontology and projection kind. | - | ontology_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `list_semantic_edit_audits` | List recent governed semantic edit audit records. | - | limit | `backend/app/mcp/tools/semantic.py` |
| semantic | `list_semantic_feedback` | Internal admin: list private feedback in one authorized Project, with bounded pages. | project_id | cursor, limit, pending_only, project_id | `backend/app/mcp/tools/semantic_feedback.py` |
| semantic | `list_semantic_protection_sets` | List the protection sets of one authorized Project. | project_id | project_id | `backend/app/mcp/tools/protection_sets.py` |
| semantic | `preflight_semantic_migration` | Run Phase 7 migration preflight for a scope. | scope_type | scope_id, scope_type, target_ontology_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `query_semantic_context` | Recall structured semantic context from one Project's current Ontologies. | project_id, scope_mode | assertion_types, context_cursor, context_detail, context_limit, context_order, depth, expansion_strategy, limit, match_cursor, ontology_ids, project_id, queries, query, resource_types, scope_mode, search_mode, semantic_roles | `backend/app/mcp/tools/semantic.py` |
| semantic | `record_semantic_feedback_resolution` | Internal admin: append a scoped diagnosis and verification reference; no model write.  A resolved conclusion requires current model revisions, actual readback references and an independent validation reference. References are reports, not semantic verdicts.  | feedback_id, resolution | feedback_id, resolution | `backend/app/mcp/tools/semantic_feedback.py` |
| semantic | `remove_semantic_protection_set_members` | Batch-remove resource IRIs from a protection set. | protection_set_id, resource_iris | actor, protection_set_id, resource_iris | `backend/app/mcp/tools/protection_sets.py` |
| semantic | `rollback_semantic_migration_run` | Roll back a Phase 7 cutover and restore legacy-primary mode. | run_id | run_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `run_next_semantic_migration_batch` | Execute the next pending batch of a Phase 7 migration run. | run_id | run_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `run_semantic_migration_parity_check` | Run parity checks for a Phase 7 migration run. | run_id | check_name, run_id | `backend/app/mcp/tools/semantic.py` |
| semantic | `semantic_sparql_query` | Run scoped read-only SPARQL against current Ontology semantic state. | project_id, query, scope_mode | ontology_ids, project_id, query, result_limit, scope_mode, timeout_seconds | `backend/app/mcp/tools/semantic.py` |
| semantic | `start_semantic_projection_job` | Request a projection rebuild job and (for non-dry-run modes) execute it. | ontology_id, projection_kind, projection_version | allow_stale_derived, include, mode, ontology_id, projection_kind, projection_version | `backend/app/mcp/tools/semantic.py` |
| semantic | `submit_semantic_edit` | Submit a governed RDF/SPARQL Update semantic edit with audit metadata. | content, format, ontology_id | actor, content, format, ontology_id, reason, warning_state | `backend/app/mcp/tools/semantic.py` |
| semantic | `submit_semantic_feedback` | Save a client observation (read scope); reuse the ID and body for unknown receipts.  This only saves feedback. It does not diagnose, start modeling or modify the model.  | description, feedback_id, query_request, reasons | description, feedback_id, query_request, reasons, result_snapshot, snapshot_complete | `backend/app/mcp/tools/semantic_feedback.py` |
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

上述宿主服务保留 S1 的 12 项及 S2 的 8 项原语义，另提供交付接线。
它们不进入平台 MCP inventory 或生产角色权限。Delivery 会话通过原生结构化工具调用
使用同一操作层；业务入口只输出显式发布的业务消息，不透传内部工具响应。R4.3-029
将 CQ 私有审核和新平台修复交由获准 Host；Delivery 只发起窄的私有请求、做技术对账，
不再启动新的 Delivery repair operation。

| 工具 | 输入／作用 | 完成依据与限制 |
| --- | --- | --- |
| `submit_instruction` | run ID、`user_supplement`／`delivery_guidance`、原文、来源／授权、request ID | 既有 FIFO 与 Runner 实际投递回执；不伪造问题绑定 |
| `start_evaluation` | run／freeze、cq-acceptance 或 public-feedback、交接／checkpoint、题集与模型配置 | 包装现有 CLI，记录调用与 PID；不提供 unexecuted-report |
| `get_evaluation_status` | operation ID | 进程状态及本次新报告的真实请求绑定；旧报告、错误绑定或未执行不算有效结果 |
| `start_repair` | Host 获准的 repair-task、executor／model／effort、授权及 issue | 底层 Host 接口保留供宿主复用；R4.3-029 不向 Delivery 暴露新修复启动，历史任务仍可收尾 |
| `get_repair_status` | operation ID | 读取既有任务退出、受控日志及结果证据；`effect_verified` 不因 exit 0 变为 true |
| `stop_delivery_operation` | operation ID、reason | 核对本次拥有的 PID／进程组后终止，保留日志／回执；不控制无关进程 |
| `read_platform_record` | batch／session／ontology_batches 的 ID 与精确 project／ontology scope | 既有只读读回；返回记录与读取次数，无 apply/delete |
| `reconcile_write_state` | 本次 run、project／ontology scope | 既有写者证据与 Batch／Attempt／资源／回执对账；不补做隐藏根因查询 |

R4.3-033 为 `start_evaluation` 和
`resume_from_checkpoint(mode="acceptance")` 增加可选 `runtime: codex | dsh`，省略为
`codex`，不从生产或 Delivery 推断；CLI 对应 `--runtime`，覆盖正式 CQ、公开早期反馈
及只读验收接续。DSH 须显式选择含实际验收角色的模型 Profile，例如
`dsh-acceptance-deepseek-flash-low`；缺角色或不兼容模型返回可修正错误，不读取真凭据或
启动模型任务。DSH 的 `service_tier=fast` 不受支持，unset/default 移除本子进程的
Codex fast 继承。operation 请求和新报告绑定 runtime；旧报告缺字段仅按 Codex 读取，
不能匹配 DSH 请求。Delivery 用 `evaluation_runtime`／`evaluation_model_profile` 固定所选
验收绑定，模型工具不能自行改选。权限、冻结、治理读回、完整分母和独立语义裁决保持原合同。

### R4.3-030 首批：按需决策与 v2 模型视图

Delivery 本地新增 `yield_delivery`，必填 `input_id`、`phase`、`waiting_for`、
`next_action`、`reason`、`active_decisions`；可附 `evidence_references`。
等待对象用当前 session 的 `run_id`、`operation_id`、`host_request_id` 或
`run_id`＋`request_id`，另附 `condition`。有效决定逐项带 `decision_id`、`text`、
`source_references` 与显式 `replaces` 列表。工具只向原 session journal 追加
`delivery_yield`，返回 `waiting_recorded`／`end_current_turn`；不写平台、不确认待送输入、
不结束原生线程。模型须随后自然结束 turn，实际 `turn/completed` 才是推理结束证据。
等待列表不限制监督范围；程序继续约2秒观察所有绑定对象，明确任务 deadline、授权期限
及运行中 operation 的既有 `started_at`＋`session_timeout` 产生一次到期状态变化。
无期限或正常心跳不臆造超时；期限不会自动续权或重发写入。

模型默认输入为 `delivery-decision-input/v2`：`core` 为当前目标／阶段、授权／控制、
起点／额度引用、首阻塞及必要结果绑定，`unresolved` 为所有未决紧凑身份／状态，
`changes` 保留实际变化正文。`mode=changes` 不重复不变快照／历史；
`mode=bootstrap` 提供必要当前正文、原用户消息／未决问题及最新 yield 接续记录。
首次启动不再附整份 config；明确选取的 `task_context` 保留 task/profile/scope、获准资料
与执行约束，未知余额不由 start limit 推算。

`task_context`也保留宿主实际配置的`delivery_objective`、`authorization_budget`、
`initial_run_id`与`freeze_started_at`，用于准确传入任务限制、启动身份及起点。
额度是配置时快照，不能当实时余额或读文件授权。完整`delivery_objective`在bootstrap／
恢复时传入；后续正文更新走`changes`，不变正文不重复注入，coverage注明
`unchanged_delivery_objective`，原snapshot仍可沿journal引用定位。

DSH正常排队回执、已接收地图以及公开输入的queued／claimed／settled记录保留原件，
不单独触发模型决策；pending、错误／unknown、损坏或不识别的形状继续可见。
原生`tool/result.message.isError=true`始终作为错误，元数据带`tool_error=true`，
即使正文碰巧为成功形状JSON，也不会按普通成功过滤。

`get_run_status`、`get_pending_actions`、`get_evaluation_status`、`get_request_result`
仅在 Delivery 模型边界返回 `delivery-tool-view/v1` 简明结果；原始结果先存入
`delivery_tool_result` journal，以 `evidence` 及字段省略 coverage 定位。底层 Host 公开
合同不变，内部 observe、权限／绑定检查和 finish 使用原始结果；模型不能通过参数
选择内部视图。未知／损坏／拒绝不补默认成功，compact view 不能用于权威消费判定。

完整原件与原 pending／原生送达回执保留。旧 v1 只读转换，历史分页偏移不混入 v2；
恢复 bootstrap 仅确认本身，不推进旧 pending 页或 conversation dispatch。
32,000-byte 展示上限内显式分页，长变化正文不替换成只有引用；原件补读沿
`read_delivery_artifact` 的原权限、selection 和16,384-byte上限，同 session 的原始
`conversation-events.jsonl`可按需读取。coverage 指投影／所选页，不表示全源或业务完成。
unknown 输入只重送事实，依赖状态的动作核对 `current_state` 指向的新绑定。

原件补读使用返回的`path`／`source_ref`／`selection`或`continuation`，不猜测路径。
bytes的`length`是精确区间而非页面大小；省略length可读捕获原件的剩余区间，
`max_bytes`才限制每页体积。动态observation的旧摘要不适合反复追读，优先使用
不可变session journal范围或当前状态窄查询，既有权限、摘要及完整性校验保持。
CQ验收状态的`report_binding.summary.blind_status`仅返回原报告资格字符串或null，
不展开私有exposure明细；question_visibility=hidden不自动表示盲评。

首批只实现 F1＋F2。2026-10-19追加回执直达与F3可选阶段线程：v2的
`request_results`直接列出本次新落定的accepted回执，`unresolved[].result`保留未决／
拒绝的实际结果和纠错动作；不要求模型再查同一回执。首次bootstrap不展开全部已结历史。

Host配置`phase_thread_boundaries: [production, acceptance]`显式选择边界，缺省为空。
Delivery在`yield_delivery`可附`thread_boundary={phase,run_id,request_ids}`，同时保存
完整有效决定及理由。production要求实际接受的cq_freeze与冻结通知instruction请求，
由Delivery确认已进入生产；acceptance要求cq_handoff_complete接受、所选独立验收
operation已启动。只有当前输入的交接、旧活动已结束、无在途／未知提交、待投递输入
或未知写入时切换；条件不全延后，不终止原run。新线程仍在原监督进程中，接收当前
bootstrap、原用户约束与yield决定，不重新启动生产或重置额度。原线程迟到完成不能
释放新线程忙状态；usage保留实际原生身份，关闭统计累计全部线程而进程存活只计一次。
F3默认关闭，F4连续动作另行分项实施；F5真实token对照与A6独立语义需另获运行授权。
工程检查不证明真实等待行为、token或费用下降。

已启用的自然阶段到达时，当前v2输入的`core.phase_thread_handoff`明确给出候选
`thread_boundary`及下一动作。acceptance绑定实际接受的handoff和已启动的验收；
production列出已接受的freeze及后续instruction候选，由Delivery选择真正的冻结通知
request_id加入交接，不能用不相关指令替代。Delivery在原yield保存有效决定和理由后
结束当前活动；候选提示本身不表示程序已经切换，原所有安全／消费检查继续适用。

Delivery本地调用`submit_instruction`未给request_id时，程序沿既有原生调用身份补齐
稳定ID；显式ID保持，同一原生调用恢复／重投复用ID及原FIFO幂等账本。使用实际返回
的receipt_tracking身份核对通知与交接，不把submitted当consumed。Host原始工具的
可选参数合同不变。历史账本缺身份时，未决项返回`request_identity_missing`、原件
范围及处理动作；不改写旧记录或把无法关联的消息认作已消费。此类记录阻塞边界时，
`core.phase_thread_handoff`返回`status=deferred`、绑定的blocker及下一步，不再提供
可执行thread_boundary；Delivery继续原线程，并按未决反馈定位，避免重复申请／重发。

共用事件投影按实际DSH工具调用身份关联原生结果，识别嵌套JSON／文本错误；同工具
同问题持续时不因native seq/time/callId变化反复送达。其他工具成功不清除该问题；
本工具恢复、错误改变、复发、未知内容及受保护业务／控制／写入绑定继续可见。
原生工具schema中的error参数声明不当作运行错误，原件和未知事件保持。
Host issue等待同时识别匹配issue/epoch及reporter线程身份的DSH recovery-effective
实际claimed/settled回执；recovery-submitted仍不证明恢复。已注册私有Host结果的
session相对source_ref.path可原样复制读取，仍校验实际权限、完整长度和不可变digest。

### R4.3-029 Delivery→Host 私有接单

Delivery默认观察继续保留当前授权、阶段、待办、首阻塞、未知写入和新增变化。
正常MCP starting／ready及remoteControl disabled事件只保留原件，不触发模型决策；
错误、异常状态及损坏事件继续送达。稳定已完成的Host结果用`completed_index`定位，
工作完成、报告有效且无未决控制的evaluation在standby时也可进入既有
`operation_history`；新结果／绑定变化仍先送达，原件可通过精确引用补读。

在Delivery本地调用`standby_run`（含`finish_delivery`内部收尾）或
`complete_cq_acceptance`时，省略request_id会由程序补齐并在结果中返回；
Delivery所有提交态附`receipt_tracking`，包含原request_id、`via=host_observation`及
yield等待指引，不再用`next_query`要求立即轮询。`get_request_result`仍可用于实际
回执缺口、未知结果对账和显式恢复；submitted本身不是消费证明。
同一原生工具调用重投保留关联身份，
显式传入request_id继续原样使用。独立Host工具的可选参数合同不变；
submitted只证明提交，实际消费与standby仍以Runner回执／状态为准。

`complete_cq_handoff`在生产角色尚未报告完成时返回可恢复的
`cq_production_pending`，保持生产写入开放，不改变授权或发布handoff。
CQ拒绝回执保留`detail`和`retry`；`get_request_result`及同request_id重查返回
`reason`、`retryable=true`与对应`next_action`。等待真实生产报告完成后，使用原
freeze绑定及**新request_id**重试，无须扩大授权、补`delivery_binding`或等run先terminal。
真正的scope授权错误继续使用`cq_batch_scope_unauthorized`；历史缺`detail/retry`的
回执保持原格式与通用重试提示，不改写旧证据。

同一live run的验收运行故障已留存最终报告后，可显式调用
`complete_cq_handoff(retry_of=<当前acceptance_attempt_id>, ...)`，沿原freeze与scope
分配新的只读验收attempt，不重启生产。普通重复handoff保持幂等；同一`retry_of`
的重复请求返回已分配的同一新attempt。使用返回的`model_handoff`启动验收，再用新
attempt完成回交，不猜文件路径或复用旧报告目录。原handoff及全部旧报告不可覆盖；
新handoff位于`acceptance-v3/handoffs/attempt-NNNN.json`，验收CLI及Host回交均核对
Runner实际发布的该原件。前次报告未落定、旧attempt绑定或unknown writes仍准确拒绝
并可纠正；当前只覆盖有最终报告的重验，不把缺报告的未知执行当成已结束。
原任务要求的最终公开／隐藏组均在新attempt下执行，旧通过保留为历史，不拼接成新的
完整PASS；模型本身、源资料、题池分母与评分不因此改变。

Delivery的`yield_delivery.thread_boundary`显式申请在后续普通yield中持续保留，省略
字段不会取消；显式`null`取消。原journal恢复该意图，新输入仍需最新yield确认有效
决定，空闲／控制／写入检查保持。创建失败需再次显式申请，普通等待不自动重试。

`request_host_action` 是 Delivery 本地工具，不属于 `host_ops_mcp` 或平台 MCP inventory。
它在当前 session 私有 `session-events.jsonl` 追加 `host_action_request`，只接受
`kind=cq_review|platform_repair`，绑定 `request_id`、当前 `run_id` 和 `bindings`，不执行审核、
修复或结果认证。CQ `bindings` 使用当前 pending 的 `review_id`、`content_version`、
`content_digest`、`question_ids`，可带 `phase`、`review_snapshot_ref`、`draft_ref`；正式 issue
平台修复使用真实 `issue_id`、`reporter_id`、`control_epoch`，尚未建 issue 的技术异常可用空
`bindings` 先交接，但不能据此调用正式 `resolve_issue`。平台诊断可带
`expected_behavior`、`actual_behavior`、`blocked_step`、`evidence_references[]`、`checked[]`、
`hypotheses[]`、`write_state`。同一 `request_id` 同内容幂等，内容冲突可恢复拒绝；请求回执
不表示 Host 已执行或成功。字段不包含 CQ 题目、答案、评分、凭据或完整对话。

Host 将结果原件保存在当前 session 的私有 `host-results/` 后，在仓库根目录运行：

```bash
python -m modeling_team.delivery_host_actions \
  --session-root <session-root> \
  --request-id <request-id> \
  --status completed|blocked|failed \
  --result-path <host-results/result-file>
```

CLI 只接受当前 session 私有目录内的结果原件，并在同一锁保护的 journal 追加
`host_action_result`（绑定原 request、`source=host_agent`、终态、结果摘要和限制）；结果正文不
复制进 journal。CQ 由 Host 读取私有快照并调用现有 `submit_cq_review`，Delivery 只核对回执／
digest 后执行 `freeze_cq`。平台修复由 Host 按 T0、最窄修复、测试及必要部署／重启后，直接用
正式 issue 绑定调用 `resolve_issue(resolution_type="repair_completed")`；Delivery 不调用旧的
新修复启动／验证路径。

`start_run`／`resume_from_checkpoint` 新增可选 `host_session_ref` 透传；它仅关联宿主记录，
不授予权限或证明 semantic start。Delivery 原生工具投影隐藏 `repository_root`、
`base_url` 和 `host_session_ref`，由部署宿主注入。

本地入口为 `python -m modeling_team delivery --config <yaml> [--resume]`。
R4.3-020的Delivery CLI默认`model_context_window: 544000`及
`model_auto_compact_token_limit: 489600`，可在同一YAML中显式覆盖为正整数。
当前GLM Delivery有效输入窗口为516,800（95%），是旧258,400的两倍；
仅作用于新Delivery原生进程，不修改生产／验收角色或已启动线程。
外部provider的显式窗口通过启动时精确模型catalog避免Codex未知模型272,000上限；
它记录本会话预算，不能视为所有模型均支持该容量。变更模型／预算仍须核对实际规格。
原生模型保留自身容量上限；直接复用DeliveryRuntime的测试代答者默认不设置窗口。
实际生效检查及真实效果边界见
[局部交付记录](../delivery/records/2026-10-14-modeling-cache-cost-requirements-registration.md#delivery窗口翻倍的后续授权与局部实现)。
Delivery 不再暴露 `verify_repair`，保留 `get_repair_verification_status` 观察历史操作；
底层 `delivery_verification` 仍供获准 Host 按需复用。R4.3-029 新平台修复由 Host 执行
相关检查、必要部署及正式 issue 恢复；这些入口不属于上述 stdio MCP 清单，不能代替语义验收。
部署、授权、业务输入和证据边界见 [实施记录](../delivery/records/2026-10-08-r4-0-023-delivery-agent.md)。

## v4.3 Team 引用与效率工具

这些工具属于隔离 Team／Host 合同，不进入业务平台 MCP inventory，不新增平台 REST API。

| 工具 | 调用者与输入 | 输出及边界 |
| --- | --- | --- |
| `modeling_submit_model_changes` | unified Modeling；modeling_id；request（schema_version、candidate_ref、显式 changes）或 request_ref 二选一；request_ref可附request_edits；可选 placement_ref | 完整请求可按获准不可变材料引用无损载入；静态拒绝提供correction引用、可选无损建议及实际字段合同，Agent显式小范围纠错后仍走同一编译／原子apply、成功去重及不确定对账；不裁决业务语义 |
| `modeling_inspect_associations` | unified Modeling；modeling_id、可选 focus_iris | 在本 run 实际获准 Ontology 集合完整治理分页读取，调用既有关联辅助；部分、权限或修订漂移保持局部结论，不开放任意 SPARQL |
| `modeling_finish_changes` | unified Modeling；modeling_id | 完成程序持有的 Build Session 并释放租约；不等同最终语义验收 |
| `protocol_execute_approved_plans` | 保留计划能力；有序 plan_refs、ontology lease_tokens、mode=apply_atomic | apply 请求内校验；新模型 dry-run 和翻译／dry proof 前置门已退役。当前统一图正常写入使用 Modeling 直接能力；历史计划仍可解释 |
| `protocol_check_plan_coverage` | unified Protocol；同轮 candidate_ref、plan_refs、明确不落地 dispositions | 候选与命令身份覆盖、applied 记录和缺口；不推断业务依赖或模型质量 |
| `protocol_inspect_associations` | unified Protocol；本轮已观察 semantic_sparql_query read_refs、final_read_ref、project／ontology scope | 保留多页原文按引用进入现有关联扫描，定位／摘要可核对，缺页 PARTIAL；任意路径或其他 run 引用不可读 |
| `examiner_report.read_frozen_evidence` | v2 引用 Judge；run_id、batch_id、freeze_digest、reference_id | 仅返回已绑定冻结业务原文；同文可复用及重读，记录实际读取回执；无仓库／DB／平台读取权限 |
| `record_efficiency_progress` | 原生 Delivery；追加 intervals、counts、题集冻结身份或已核对 completion | 仅作用于 Host 配置 efficiency_round 的私有本地记录，不能改变原始起点；计算墙钟与故障并集，不裁决语义／性能 PASS |

R4.3-028：`changes` 每项显式包含 `change_id`、`action`、`resource_kind`、`item_id`、
`target_ref`、`fields` 六字段。候选入口选择item并使用fields=null；fields-only定义使用
item_id=null，创建时target_ref=null。工具宣告已有合法枚举及语义字段；编译器仍负责
操作组合、引用和内容校验，可修正内层错误返回原字段诊断，不变成不透明的认证拒绝。
`semantic_definition`仅使用现有六类字段，不支持exclusions；业务排除条件保留在有依据
的语义说明中。后续关系端点复制实际回执的resource_bindings引用，不能按数组位置猜。

完整请求已有文件时，先通过 `write_handoff_output` 保存一次，再调用
`publish_handoff_material(recipient_id="runner", source_path=...)`，将返回的
`material_id` 放入 `request_ref={"material_id":"…"}`；目录材料另加 `path` 选择一个文件。
文件正文为完整 `r4-3-025-model-changes/v1` 对象，不含外层 `modeling_id/request` 包装。
`request` 和 `request_ref` 只提供一个，另一键省略；小修改仍可内联。`candidate_ref` 是正文
内部的候选引用，不能代替完整请求引用。Runner 沿原材料授权／摘要检查一次读取完整正文，
不重新生成或静默修正字段；引用与内联的相同内容共用原提交身份、成功去重和不确定写入对账。
材料缺失、变化、越权、成员未选及 JSON 非法返回 `/request_ref` 可重试未写入反馈；原业务
内容错误仍由同一 compiler 定位。发布材料不等于获得模型写入授权。

静态编译拒绝另返回 `correction`：`request_ref` 指向本次实际被拒的完整对象；
`suggested_edits` 只建议将内层已有控制键移到缺失外层，或删掉完全相同的内层重复键；
`field_contracts` 给出所选资源／操作的实际允许字段。冲突值、未知语义和不支持的业务字段
不由程序决定。Agent确认后可用该引用和非空 `request_edits` 提交显式 JSON Patch：
`add`／`replace` 带 `value`，`remove` 只需 `op/path`，`move` 带 `from/path`；路径从请求
正文根开始（如 `/changes/0/fields/item_id`），不是 `/request` 包装。原件不变，程序在
副本上原子执行补丁；任一补丁错误返回 `/request_edits/N`，不发平台写入。修正后的完整
内容继续原编译、授权／冻结、application和去重／未知写入对账。若再次被拒，新引用
对应本次已编辑的正文；不要沿旧引用丢失前次修改。建议不会自动执行，也不是修模授权。

028增量路径在写入前按显式获准Ontology集合进行业务表达检索，再按候选所属图及实际IRI
补读完整定义、RDF类型、有向关系和必要路径；无匹配、词面降级或截断不证明不存在。
旧资源可引用本run真实保留的读模型`/structuredContent/data/items/N`或Context Query
`/structuredContent/data/primary_matches/N`，artifact_ref取platform_ref.artifact_path。
程序在原scope／revision／当前full类型核对后，使用当前Settings原生命名空间及原resource
编码方法往返一致地恢复执行ID；外部IRI不猜ID，仍可用于支持IRI的字段。Agent不解码
IRI或读取旧run。新写入推进修订后，刷新受影响的旧读取；成功回执仍沿原合同复用。

`placement_ref={artifact_ref,path}`仅选择Host已确认并冻结的本run拓扑条目，由
`multi-slice-ontology-plan`通知及已有确认后的任务提示提供；不改变request版本或六字段
change，不在fields内填Ontology ID。一个请求选一个归属；与candidate／target真实归属
冲突、快照变化或当前plan绑定失效返回可修正`scope_binding_required`。归属和确认plan
身份参与原submission快照和去重；不允许换placement绕过原不确定写入。

跨图Mapping另沿所属图reference_ontology_ids合同；未就绪时需Coordinator确认具体
cross_slice_dependencies及Host已绑定mapping_reference_direction。029新任务省略该选项
时固定采用`from_slice_depends_on_to_slice`，显式反向只允许
`to_slice_depends_on_from_slice`。开门后新确认的依赖可在原run直接Mapping提交前准备，
仅合并受影响owner的引用且保留旧引用；缺确认或配置失败返回带原字段路径的
`mapping_reference_scope_required`，可修正后继续。普通relation_type不增加此Mapping门。


当前Modeling／Consumer读目录仅宣告合法资源类型及hybrid／lexical模式；省略筛选包含
概念定义，专用rule／rules读取已退役。内部slice ID不是默认业务检索词；从问题业务
用语开始、沿实际IRI按需读取。错误反馈保留字段及合法枚举说明，不影响原授权边界。

Judge 初始 packet 只传冻结资料清单和题目对应；完整获准副本保留 Host，PASS 需要实际读取
并引用相关原文。平台响应采用无损正文注册表并主动按实际输入体积分组，各组覆盖同一
冻结完整题集，报告分别披露业务资料和平台响应字节量。
Delivery 程序持续观察并保留 observation.json；无关日志／心跳增长不启动重复推理，
有意义变化可 steer 当前活跃 turn，用户控制仍优先。

详细记录格式见 [同轮计时方法](../../modeling_team/references/efficiency-round-record.md)，
合同与工程／真实验证边界见 [v4.3 设计](../delivery/designs/2026-10-09-v4-3-modeling-efficiency-design.md)。

R4.3-024／025 的当前直接建模请求、value 规则、资源引用和回执边界见
[可执行合同](../../modeling_team/references/r4-3-025-direct-modeling-contract.json)。
Modeling 的三个只读工具通过独立代理绑定 Project 及本 run 实际获准 Ontology 集合，
支持现行 adaptive／context_order 参数和多次问题／IRI 查询。后端持有分页、授权、修订
和索引校验；代理不把首次问题锁成整个 run 唯一查询。旧暂停 run 不自动切换或恢复。
