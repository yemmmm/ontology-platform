# HTTP API

本文档描述当前运行时实际注册的 HTTP API。完整操作清单由 FastAPI `app.openapi()` 生成；业务
契约、边界和示例由人工维护。

## 地址与认证

- `./scripts/start-local.sh` 与本地 systemd 服务：`http://127.0.0.1:8001/api`
- 手动运行 `uv run uvicorn app.main:app --reload`：默认 `http://127.0.0.1:8000/api`
- OpenAPI UI：对应 backend 地址的 `/docs`

只有三个 `/api/health*` endpoint 和 `POST /api/auth/login` 公开。其他 API、OpenAPI JSON 和 docs
要求 `Authorization: Bearer <API key>` 或有效 UI session。API key 只有创建响应展示一次明文，之后
只能查询 metadata 或幂等撤销。

- `read`：读取、export、Context Query 与 scoped SPARQL。
- `model`：包含 read，并允许建模、Evidence、Build Session 与受治理 RDF 写入。
- `admin`：包含 model/read，并允许 Project、Ontology、API key 与全局治理操作。

Project-bound 主体只能访问其 Project；显式提交 foreign Project 返回 `403 forbidden_scope`，只提供
foreign opaque resource ID 时返回 404。UI session 写请求还要求可信 Origin、CSRF cookie 与
`X-CSRF-Token` 相等。

## 当前主要工作流

### Project、Ontology 与需求澄清

- Project/Ontology CRUD 与默认语义工作区：`/api/projects`、
  `/api/projects/{project_id}/ontologies`
- Project Brief、Interview Answer 与 Competency Question：
  `/api/projects/{project_id}/brief`、`/api/projects/{project_id}/interview-answers`、
  `/api/projects/{project_id}/competency-questions`
- 构建上下文：`GET /api/projects/{project_id}/build-context`

创建 Ontology 后，平台会初始化默认 RDF 图和 Graph Set。历史或不完整工作区可使用当前注册的
workspace repair 操作修复。

### 外部 Agent 建模

外部 Agent 使用 Build Session 和 Ontology Lease 管理恢复与并发，再通过 Modeling Batch 完成
`dry_run` 和 apply。平台保存建模结果、幂等状态、冲突和审计，不在 HTTP 层替 Agent 做领域判断。

R1.1 分阶段工作流使用 Build Session 下的 Modeling Workflow Artifact 和 Modeling Execution Event：
Artifact 以 `artifact_key` 创建不可变线性版本，Event 以 `client_event_id` 幂等追加并获得 Session 内
稳定序号。问题事件使用 current-head compare-and-set 保存 `open/answered/skipped/uncertain/reopened`
状态；更正只能追加 superseding event。`GET .../modeling-workflow:export` 提供完整 JSON 或 Markdown
复盘记录，`GET /api/build-sessions/{session_id}` 只内联小型 `modeling_workflow_summary`。

证据采用轻量 Evidence Reference：外部 Agent 自行读取资料，只提交实际使用的
`document_name + excerpt`，再把引用关联到 Modeling Item。当前没有完整文档上传、解析或旧
Proposal/Review/Publish 队列。

### 查询与验证

- Context Query：`POST /api/semantic/context:query`
- scoped SPARQL：`POST /api/semantic/sparql:query`
- Ontology read model、lineage、statement provenance、SHACL validation、reasoning 和 rule
  execution 均以清单中的当前操作为准。

Context Query 返回结构化资源、事实、关系、操作、约束和精简 lineage，不生成最终自然语言答案。
现有 Agent Test 仍会在平台内调用兼容 OpenAI 的 LLM，且中文分词能力不足；这是 R-009 的已知
缺口，不应作为目标态查询入口。

## 错误和兼容性边界

- FastAPI 参数校验通常返回 `422`；业务冲突和不存在资源按各操作实现返回 `4xx`。
- 缺少/无效/revoked credential 返回 `401 invalid_authentication`；scope 或 Project 越权返回
  `403 forbidden_scope`；领域 payload 命中高可信真实秘密返回 `422 secret_in_payload`。
- 受治理语义编辑、Modeling Batch 和 Build Session 有各自的冲突、幂等及恢复语义；调用方应保留
  返回的 session、lease、batch 和 checkpoint 标识。
- Workflow Artifact/Event 写入要求 `model`，读取/export 要求 `read`；单 Artifact 版本上限 1 MiB、
  Event payload 上限 64 KiB、export 上限 8 MiB。版本过期、foreign 引用、问题 stale head 和幂等
  冲突分别返回稳定业务 code，命中 secret 时不会自动修改或回显内容。
- 当前仍注册的 deprecated 兼容操作会继续出现在下方清单中；未注册的旧 Version、Proposal、
  Catalog、Connector 和 Neo4j Entity 接口不是当前能力。
- R-010 的 Dify 端到端验收套件尚未实现，当前没有可引用的 Dify 基准通过率。

## 完整运行时操作清单

下方区块由脚本维护，不要手工编辑。接口变更后运行：

```bash
cd backend
uv run python ../scripts/sync-interface-docs.py --write
```

<!-- BEGIN GENERATED HTTP API INVENTORY -->

| Tag | Method | Path | Summary |
| --- | --- | --- | --- |
| agent-test | `POST` | `/api/agent-test/run` | Run Agent Test |
| authentication | `GET` | `/api/api-keys` | List Api Keys |
| authentication | `GET` | `/api/api-keys/{key_id}` | Get Api Key |
| authentication | `GET` | `/api/auth/me` | Me |
| authentication | `POST` | `/api/api-keys` | Create Key |
| authentication | `POST` | `/api/api-keys/{key_id}:revoke` | Revoke Api Key |
| authentication | `POST` | `/api/auth/login` | Login |
| authentication | `POST` | `/api/auth/logout` | Logout |
| build sessions | `GET` | `/api/build-sessions/{session_id}` | Get Build Session |
| build sessions | `GET` | `/api/projects/{project_id}/build-context` | Get Project Build Context |
| build sessions | `POST` | `/api/build-sessions/{session_id}/checkpoints` | Save Build Checkpoint |
| build sessions | `POST` | `/api/build-sessions/{session_id}/ontology-leases/{ontology_id}:acquire` | Acquire Ontology Lease |
| build sessions | `POST` | `/api/build-sessions/{session_id}/ontology-leases/{ontology_id}:release` | Release Ontology Lease |
| build sessions | `POST` | `/api/build-sessions/{session_id}/ontology-leases/{ontology_id}:renew` | Renew Ontology Lease |
| build sessions | `POST` | `/api/build-sessions/{session_id}:cancel` | Cancel Build Session |
| build sessions | `POST` | `/api/build-sessions/{session_id}:complete` | Complete Build Session |
| build sessions | `POST` | `/api/build-sessions/{session_id}:resume` | Resume Build Session |
| build sessions | `POST` | `/api/projects/{project_id}/build-sessions` | Create Build Session |
| evidence | `GET` | `/api/chunks/{chunk_id}` | Get Evidence Chunk |
| evidence | `GET` | `/api/evidence-artifacts/{artifact_id}` | Get Evidence Artifact |
| evidence | `GET` | `/api/evidence-artifacts/{artifact_id}/chunks` | List Evidence Artifact Chunks |
| evidence | `GET` | `/api/projects/{project_id}/evidence-artifacts` | List Project Evidence Artifacts |
| evidence-references | `GET` | `/api/evidence-references/{reference_id}` | Get Evidence Reference |
| evidence-references | `GET` | `/api/evidence-references/{reference_id}/associations` | List Evidence Associations |
| evidence-references | `GET` | `/api/projects/{project_id}/evidence-associations` | List Target Evidence Associations |
| evidence-references | `GET` | `/api/projects/{project_id}/evidence-references` | List Evidence References |
| evidence-references | `POST` | `/api/projects/{project_id}/evidence-associations` | Create Evidence Associations |
| evidence-references | `POST` | `/api/projects/{project_id}/evidence-associations:batch` | Apply Evidence Association Batch |
| evidence-references | `POST` | `/api/projects/{project_id}/evidence-references` | Create Evidence Reference |
| evidence-references | `POST` | `/api/projects/{project_id}/evidence-references:resolve` | Resolve Evidence References |
| mcp-catalog | `GET` | `/api/mcp/tools` | List Mcp Tools |
| modeling batches | `GET` | `/api/build-sessions/{session_id}/modeling-batches` | List Session Modeling Batches |
| modeling batches | `GET` | `/api/modeling-batches/{batch_id}` | Get Modeling Batch |
| modeling batches | `GET` | `/api/ontologies/{ontology_id}/modeling-batches` | List Ontology Modeling Batches |
| modeling batches | `GET` | `/api/ontologies/{ontology_id}/modeling-context` | Get Modeling Context |
| modeling batches | `GET` | `/api/ontologies/{ontology_id}/semantic-read-models/{model_name}` | Get Ontology Read Model |
| modeling batches | `POST` | `/api/build-sessions/{session_id}/modeling-batches` | Submit Modeling Batch |
| modeling workflow | `GET` | `/api/build-sessions/{session_id}/modeling-execution-events` | List Modeling Execution Events |
| modeling workflow | `GET` | `/api/build-sessions/{session_id}/modeling-workflow-artifacts` | List Modeling Workflow Artifacts |
| modeling workflow | `GET` | `/api/build-sessions/{session_id}/modeling-workflow:export` | Export Modeling Workflow Record |
| modeling workflow | `GET` | `/api/modeling-execution-events/{execution_event_id}` | Get Modeling Execution Event |
| modeling workflow | `GET` | `/api/modeling-workflow-artifacts/{workflow_artifact_id}` | Get Modeling Workflow Artifact |
| modeling workflow | `POST` | `/api/build-sessions/{session_id}/modeling-execution-events` | Record Modeling Execution Event |
| modeling workflow | `POST` | `/api/build-sessions/{session_id}/modeling-workflow-artifacts` | Create Modeling Workflow Artifact |
| ontologies | `GET` | `/api/ontologies/{ontology_id}` | Get Ontology |
| ontologies | `GET` | `/api/ontologies/{ontology_id}/lineage` | Get Ontology Lineage |
| ontologies | `GET` | `/api/ontologies/{ontology_id}/workspace-context` | Get Ontology Workspace Context |
| ontologies | `GET` | `/api/projects` | List Projects |
| ontologies | `GET` | `/api/projects/{project_id}` | Get Project |
| ontologies | `GET` | `/api/projects/{project_id}/ontologies` | List Ontologies |
| ontologies | `POST` | `/api/ontologies/{ontology_id}/workspace/repair` | Repair Ontology Workspace |
| ontologies | `POST` | `/api/projects` | Create Project |
| ontologies | `POST` | `/api/projects/{project_id}/ontologies` | Create Ontology |
| ontologies | `POST` | `/api/projects/{project_id}/ontology-workspaces/repair` | Repair Project Ontology Workspaces |
| ontologies | `PATCH` | `/api/ontologies/{ontology_id}` | Update Ontology |
| ontologies | `PATCH` | `/api/projects/{project_id}` | Update Project |
| ontologies | `DELETE` | `/api/ontologies/{ontology_id}` | Delete Ontology |
| ontologies | `DELETE` | `/api/projects/{project_id}` | Delete Project |
| project interview | `GET` | `/api/ontologies/{ontology_id}/build-overview` | Get Build Overview |
| project interview | `GET` | `/api/projects/{project_id}/brief` | Get Project Brief |
| project interview | `GET` | `/api/projects/{project_id}/competency-questions` | List Competency Questions |
| project interview | `POST` | `/api/competency-questions/{question_id}/status` | Set Competency Question Status |
| project interview | `POST` | `/api/competency-questions/{question_id}/validate` | Validate Competency Question |
| project interview | `POST` | `/api/projects/{project_id}/competency-questions` | Create Competency Question |
| project interview | `POST` | `/api/projects/{project_id}/interview-answers` | Create Interview Answer |
| project interview | `PATCH` | `/api/competency-questions/{question_id}` | Update Competency Question |
| project interview | `PATCH` | `/api/projects/{project_id}/brief` | Update Project Brief |
| semantic | `GET` | `/api/semantic/canonical-mode` | Get Canonical Mode |
| semantic | `GET` | `/api/semantic/edits/audits` | List Semantic Edit Audits |
| semantic | `GET` | `/api/semantic/export` | Export Dataset |
| semantic | `GET` | `/api/semantic/graph-sets` | List Graph Sets |
| semantic | `GET` | `/api/semantic/graph-sets/{graph_set_id}` | Get Graph Set |
| semantic | `GET` | `/api/semantic/graph-sets/{graph_set_id}/export` | Export Graph Set |
| semantic | `GET` | `/api/semantic/graph-sets/{graph_set_id}/missing-evidence-facts` | List Missing Evidence Facts |
| semantic | `GET` | `/api/semantic/graph-sets/{graph_set_id}/read-models/{model_name}` | Read Model |
| semantic | `GET` | `/api/semantic/graph-sets/{graph_set_id}/shapes/classes/{class_iri}` | Read Class Shape Guidance |
| semantic | `GET` | `/api/semantic/graphs` | List Graph Registry |
| semantic | `GET` | `/api/semantic/graphs/{graph_iri}` | Get Graph Registry |
| semantic | `GET` | `/api/semantic/migrations` | List Migration Runs |
| semantic | `GET` | `/api/semantic/migrations/{run_id}` | Get Migration Run |
| semantic | `GET` | `/api/semantic/projection-jobs` | List Projection Jobs |
| semantic | `GET` | `/api/semantic/projection-jobs/{job_id}` | Get Projection Job |
| semantic | `GET` | `/api/semantic/projections/status` | Projection Status |
| semantic | `GET` | `/api/semantic/reasoning-runs` | List Reasoning Runs |
| semantic | `GET` | `/api/semantic/reasoning-runs/{run_id}` | Get Reasoning Run |
| semantic | `GET` | `/api/semantic/resources/{resource_iri}` | Read Resource |
| semantic | `GET` | `/api/semantic/rule-definitions` | List Rule Definitions |
| semantic | `GET` | `/api/semantic/rule-definitions/{rule_id}` | Get Rule Definition |
| semantic | `GET` | `/api/semantic/rule-runs` | List Rule Runs |
| semantic | `GET` | `/api/semantic/rule-runs/{run_id}` | Get Rule Run |
| semantic | `GET` | `/api/semantic/statements` | List Statements |
| semantic | `GET` | `/api/semantic/status` | Get Governance Status |
| semantic | `GET` | `/api/semantic/validation-runs` | List Validation Runs |
| semantic | `GET` | `/api/semantic/validation-runs/{run_id}` | Get Validation Run |
| semantic | `POST` | `/api/semantic/canonical-writes:compile-and-apply` | Compile And Apply Product Command |
| semantic | `POST` | `/api/semantic/context:query` | Query Semantic Context |
| semantic | `POST` | `/api/semantic/datasets:load` | Load Dataset |
| semantic | `POST` | `/api/semantic/derived-results:gc` | Run Derived Results Gc |
| semantic | `POST` | `/api/semantic/derived-results:reconcile` | Reconcile Derived Results |
| semantic | `POST` | `/api/semantic/edits` | Create Semantic Edit |
| semantic | `POST` | `/api/semantic/graph-sets` | Create Graph Set |
| semantic | `POST` | `/api/semantic/graph-sets/{graph_set_id}/construct-runs` | Create Graph Set Construct Run |
| semantic | `POST` | `/api/semantic/graph-sets/{graph_set_id}/fact-evidence` | Create Fact Evidence |
| semantic | `POST` | `/api/semantic/graph-sets/{graph_set_id}/projection-jobs` | Create Projection Job For Set |
| semantic | `POST` | `/api/semantic/graph-sets/{graph_set_id}/reasoning-runs` | Create Graph Set Reasoning Run |
| semantic | `POST` | `/api/semantic/graph-sets/{graph_set_id}/rule-runs` | Create Graph Set Rule Run |
| semantic | `POST` | `/api/semantic/graph-sets/{graph_set_id}/validation-runs` | Create Graph Set Validation Run |
| semantic | `POST` | `/api/semantic/graphs` | Register Graph |
| semantic | `POST` | `/api/semantic/migrations` | Create Migration Run |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:cutover` | Cutover Migration Run |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:parity-check` | Run Migration Parity Check |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:rerun-failed-batches` | Rerun Failed Migration Batches |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:rollback` | Rollback Migration Run |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:run-next-batch` | Run Next Migration Batch |
| semantic | `POST` | `/api/semantic/migrations:preflight` | Preflight Migration |
| semantic | `POST` | `/api/semantic/projection-jobs/{job_id}:run` | Run Projection Job |
| semantic | `POST` | `/api/semantic/projections:reconcile` | Reconcile Projections |
| semantic | `POST` | `/api/semantic/reasoning-runs` | Create Reasoning Run |
| semantic | `POST` | `/api/semantic/rule-definitions` | Create Rule Definition |
| semantic | `POST` | `/api/semantic/sparql:query` | Query Sparql |
| semantic | `POST` | `/api/semantic/validation-runs` | Create Validation Run |
| semantic | `PUT` | `/api/semantic/graph-sets/{graph_set_id}/members` | Update Graph Set Members |
| semantic | `PATCH` | `/api/semantic/graphs/{graph_iri}/editability` | Update Graph Editability |
| semantic | `PATCH` | `/api/semantic/rule-definitions/{rule_id}` | Update Rule Definition |
| semantic | `DELETE` | `/api/semantic/graph-sets/{graph_set_id}/fact-evidence/{binding_id}` | Delete Fact Evidence |
| semantic | `DELETE` | `/api/semantic/rule-definitions/{rule_id}` | Delete Rule Definition |
| untagged | `GET` | `/api/health` | Health |
| untagged | `GET` | `/api/health/dependencies` | Dependency Health |
| untagged | `GET` | `/api/health/postgres` | Postgres Health |

<!-- END GENERATED HTTP API INVENTORY -->
