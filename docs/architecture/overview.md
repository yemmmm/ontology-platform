# Architecture

## 目标边界

Ontology Platform 的目标是可复用的 Agent 语义层，而不是内置领域建模 Agent：

| Party | Responsibility | Current surface |
| --- | --- | --- |
| User | 提供业务目标、回答澄清问题、决定 Agent 是否继续下一批写入 | external Agent conversation / UI |
| External Agent + Skill | 读取资料、提取知识、做建模判断、组织批次、生成最终自然语言答案和调用外部系统 | MCP / HTTP |
| Platform | 保存工作流与语义事实，执行确定性校验、并发/幂等/恢复、证据关联、审计、lineage 和结构化查询 | FastAPI + FastMCP + PostgreSQL + RDF/Oxigraph |

当前 Modeling Batch 是直接受治理写入协议，不依赖旧 Proposal/Review/Publish 队列。人工确认是
Agent 的继续/停止条件，不是平台内 approve/publish 操作。

## 当前组件

```text
React/Vite UI ───────┐
                     ├──> FastAPI adapters ──┐
External HTTP client ┘                       │
                                             ├──> application services
External Agent ── stdio FastMCP adapters ────┘          │
                                                        ├──> PostgreSQL
                                                        └──> RDF Dataset / Oxigraph
```

- FastAPI：UI/脚本使用的 HTTP adapter，并暴露 runtime OpenAPI。
- FastMCP：外部 Agent 的 stdio tool adapter；工具复用相同 services。
- PostgreSQL：Project/Ontology 元数据、访谈、Evidence Reference、Build Session/lease、Modeling
  Batch、Modeling Workflow Artifact/Event、rule、审计和 lineage 辅助状态。
- RDF Dataset / Oxigraph：当前权威本体结构、实例事实、Graph Registry/Graph Set、shape/policy、
  Operation 与 statement。
- React/Vite：本地管理与诊断工作区，不是另一条持久化路径。

Neo4j 曾是早期自定义图实例路径，但 migrations `0017_drop_legacy_governance.py` 之后的当前注册
API/MCP 不再把 Neo4j Entity/Catalog/Proposal/Version 流程作为权威写入路径。历史文档或遗留模型
类不能覆盖当前 RDF/Oxigraph 运行时事实。

## 默认 Ontology 工作区（R-001）

创建 Ontology 会幂等初始化默认 `asserted_ontology`、`asserted_data`、`shapes`、`policy` 图及一个
Ontology-scoped 默认 Graph Set。普通 Agent 以 Project/Ontology 为范围；平台内部解析 Graph Set、
graph IRI、revision、editability 和 source signature。repair 入口只补齐或修复不一致资源，不覆盖
已有语义内容。

## Evidence（R-002）

外部 Agent 自行读取资料，只提交实际使用的 `document_name + excerpt`。平台创建可复用的 Project
级 Evidence Reference，并在 Modeling Item 上建立 association。当前不存在完整文件 ingestion、
chunk 或 Evidence Artifact 上传协议。

## Build Session 与 Modeling Batch（R-003/R-004）

```text
Project Build Context
  -> create/resume Build Session
  -> Ontology Modeling Context
  -> dry-run Modeling Batch
  -> acquire Ontology Lease
  -> apply_atomic / apply_partial
  -> checkpoint and complete/cancel Session
```

`ModelingBatchService` 通过 session、lease、workspace version、idempotency key、item dependency、
确定性 Finding 和 Ontology Write Fence 管理写入。

```text
Modeling Batch Service
  -> persist deterministic plan in PostgreSQL
  -> canonical RDF writer + rule/evidence/audit effects
  -> terminal Attempt or forward recovery under the same Attempt
```

PostgreSQL 与 RDF store 没有跨存储 ACID 事务承诺。平台先持久化计划、隔离并发，并对不确定 side
effect 向前收敛。Build Session 的恢复与 Modeling Batch apply 恢复是不同层次。

## 分阶段建模工作流（R1.1-002）

`ModelingWorkflowService` 在 Build Session 下保存两类确定性资源：

- Modeling Workflow Artifact：按 `artifact_key` 锁定 Session 行并建立不可变线性版本，保存规范
  content hash、角色/workflow/prompt 版本和 supersedes；
- Modeling Execution Event：按 `client_event_id` 幂等追加、分配 Session 内 sequence，保存显式动作、
  决定、问题状态、Artifact 和平台资源引用、结构化质量问题及可用的 Runtime 指标。

问题状态在同一 Session 行锁内按 current-head CAS 转换，并发回答只有一个可成为 head。Artifact/
Event 追加只更新 `last_activity_at`，不增加 Build Session revision，因此不会让无关 checkpoint/lease
CAS 失效。Event 对 Modeling Batch Finding 使用 Attempt ID + 持久 `finding_fingerprint` 精确引用；
平台验证 Project/Session 归属但不判断 Pack、Coverage Matrix、review 或 verification 的业务结论。

REST 与 MCP adapter 复用同一 service、认证 actor、R-008 Project ownership resolver 和高可信秘密
扫描。JSON/Markdown export 可重建版本与时间线，但平台事实仍以 Modeling Batch、Validation、
Evidence、Audit、lineage 和当前 RDF 模型为准，Event 不形成第二真相。

## Lineage 与查询（R-005/R-006、R1.2-002）

R-005 把 statement occurrence、Evidence Reference、Modeling Item、Audit、revision、derived premise
和 stale 状态连成统一来源/推导链。R1.2-002 与 R-006 提供三级读入口：

- Scope Discovery：先按认证主体过滤 PostgreSQL Project/Ontology 目录，再执行确定性 metadata
  筛选、查询就绪评估和稳定 keyset 分页，不读取 RDF 业务事实；
- Context Query：解析 Project/一个或多个 Ontology 的当前默认工作区，执行有界检索、关系扩展、
  constraint 与精简 lineage projection，返回结构化资源、事实、关系和 Operation；
- scoped SPARQL：只接受 read-only query，由服务端注入经过验证的数据集范围并限制结果。

外部 Agent 负责把结构化上下文转成最终答案。旧 Agent Test 内部 LLM 路径已移除；
R-009 如恢复交付，只提供纯 Context Query 调试和诊断。

Scope Discovery 与 `SemanticQueryScopeResolver` 复用同一 Ontology readiness 评估。archived 和默认
工作区损坏项保持可发现但不可查询；Project 范围可排除部分不可用 Ontology，但全不可用范围失败
关闭。目录 cursor 不创建快照或授权锁，Context/SPARQL 每次重新校验当前 Project 归属、生命周期、
工作区和 `workspace_version`。

## Operation（R-007）

Operation 是默认 `asserted_ontology` 图中的 RDF 资源，通过普通 Modeling Batch 命令创建/更新/
删除，并复用 R-005 lineage 与 R-006 查询。平台只描述外部能力的 tool binding、输入输出、约束和
凭证需求类型；执行、凭证实例、重试和补偿留给外部 Agent/系统。Operation 与其他领域写路径均受
R-008 高可信秘密扫描保护。

## 派生状态与迁移

SHACL validation、reasoning、rule、projection 和 migration 使用当前 semantic services 与 Graph
Set source signature。Search/Vector writer 目前仍是假实现，真实持久索引属于 R-103；reasoner 可
通过可选外部 command 运行，标准部署治理属于 R-110。

## 安全与未完成边界

- R-008 已实现：HTTP/UI/MCP 使用统一认证主体、scope 授权与 Project 访问控制。
- R-009 挂起：旧 Agent Test 已移除，纯查询诊断尚未实现。
- R-010 已调整：Dify 建模效果验收已转入 v1.1，固定资料快照已交付，集成重跑尚未闭环。
- `ApiKeyModel` 只保存 SHA-256 key hash；`UserModel` 保存 Argon2id password hash，
  `SecurityAuditEventModel` 保存最小只追加安全事件。HTTP/MCP adapter 将 credential 解析为统一
  `AuthPrincipal`，服务写入使用 principal actor，并在访问 RDF/Postgres 资源前校验 Project 归属。
- raw Cypher 不属于当前接口；SPARQL Update 只允许受治理编辑路径中的受限形式。

## 接口文档同步边界（R-011）

HTTP operation 的唯一清单来源是 FastAPI `app.openapi()`；MCP tool 的唯一清单来源是
`mcp.list_tools()`。`scripts/sync-interface-docs.py` 只更新 `docs/reference/api.md` 与 `docs/reference/mcp.md` 的 marker
区块，人工说明不由生成器覆盖，CI 使用只读 `--check` 防止 registry 与文档漂移。
