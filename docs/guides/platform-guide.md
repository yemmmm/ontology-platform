# 平台使用指南

## 当前定位

Ontology Platform 是面向外部 Agent 的本地语义平台。外部 Agent + ontology-builder Skill 负责读取
资料、澄清需求、提取知识和做领域建模判断；平台负责：

- Project、Ontology 和默认语义工作区；
- Brief、Interview Answer、Competency Question；
- Project 级 Build Session、Checkpoint 与 Ontology Lease；
- 轻量 Evidence Reference 和建模结果关联；
- Modeling Batch 的 dry-run、原子/部分 apply、幂等、冲突与恢复；
- 版本化 Modeling Workflow Artifact、追加式 Execution Event 与 JSON/Markdown 执行记录导出；
- RDF/Oxigraph 语义状态、PostgreSQL 工作流/审计状态与统一 lineage；
- SHACL、推理、规则、Context Query、scoped SPARQL 和固定读模型。
- 面向消费 Agent 的授权 Project/Ontology 范围发现与查询就绪状态。

平台不替外部 Agent 生成领域判断或最终自然语言答案，也不保存外部系统明文凭证或代执行外部
Operation。R-008 已提供 HTTP/MCP/UI 认证、scope 授权和 Project 隔离；R-009 Agent Test 重构只部分
实现，R-010 Dify 验收未实现。

## 本地启动

推荐使用：

```bash
./scripts/start-local.sh
```

脚本启动 PostgreSQL 与 Oxigraph，执行 migration，构建 frontend，并运行：

- backend：`http://127.0.0.1:8001/api`
- FastAPI docs：`http://127.0.0.1:8001/docs`
- frontend preview：`http://127.0.0.1:5173/`
- PostgreSQL host port：`5434`
- Oxigraph：`http://127.0.0.1:7878`

手动启动 backend 时，uvicorn 未指定端口则使用 `8000`：

```bash
cp .env.example backend/.env
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

frontend dev server 与 MCP 分别运行：

```bash
cd frontend && npm install && npm run dev
cd backend && uv run python -m app.mcp.server
```

frontend 默认请求同源 `/api`；手动跨源运行时可设置 `VITE_API_BASE_URL`。完整配置以
[README](../README.md) 和 [`.env.example`](../.env.example) 为准。

## 安全边界

三个 health endpoint 与登录公开，其他 HTTP 路由使用 hashed API key 或 UI session。`read`、
`model`、`admin` scope 按包含关系授权，Project-bound 主体只能解析和访问自身 Project 的资源；全组织
admin 才能管理 Project 与未绑定 key。MCP 必须配置 `ONTOLOGY_MCP_API_KEY`，每次 tool call 会重新
检查 key 是否已撤销。写入 actor 来自认证主体，payload 自报 actor 只用于伪造检测。领域 payload
命中高可信真实秘密时在持久化前拒绝。

迁移后首次 hard cut 前运行 `cd backend && uv run python -m app.cli.bootstrap_auth --username admin`，
并安全保管生成的 gitignored `0600` credentials 文件。文件一次性包含 username、UI 初始 password
和组织管理员 API key；读取后应转存到受控密码库，不能提交到 Git 或复制到日志。

## 推荐的外部 Agent 构建流程

### 1. 恢复 Project 事实

先读取 Project Build Context，检查 Brief、问题、本体工作区、活动 session、fence/recovery 和最近
批次。`.ontology-build.md` 可保存外部 Agent 的本地进度，但平台状态始终是事实来源。

### 2. 澄清需求

围绕业务目标、范围、关键对象、身份规则、关系、Operation、约束和能力问题更新 Project Brief、
Interview Answer 与 Competency Question。不要要求业务用户理解 Graph Set、graph IRI 等内部概念。

### 3. 创建或恢复 Build Session

需要写入时创建或恢复一个 Project 级 Build Session。Session 负责项目工作流恢复；真正应用某个
Ontology 的批次前，还要获取该 Ontology 的 lease。Session 和 lease 解决恢复与编辑并发，不等同于
R-008 的身份授权。

### 4. 保存轻量证据

外部 Agent 直接读取资料，只把实际支持某项建模决定的 `document_name + excerpt` 创建为 Project
级 Evidence Reference。平台按规范化内容复用引用，并在 Modeling Item 上记录 association。

当前没有完整文档上传、解析、chunk 状态或 Evidence Artifact 工作流。

用于 v1.1 Dify 场景的仓库本地验收资料位于
`docs/evaluation-corpora/dify-foundations/`。它固定官方文档 commit、逐文件来源与 SHA-256，并提供
离线校验、重建、版本差异和主题定位工具。外部角色应在一个 Build Session 中使用同一 snapshot
ID，并把 snapshot ID、manifest hash、实际文件路径/hash 写入 Business Knowledge Pack；发现官方
更新时先报告新鲜度差异，不能静默混用正文。该资料集只是可复现业务输入，不是平台上传能力，也
不直接等于 Evidence Reference；建模项仍要保存实际使用的精确原文摘录。

### 5. 先形成版本化业务交接

外部主 Agent 先全局扫描资料，让独立业务整理角色生成 Business Knowledge Pack 和 Modeling Coverage
Matrix；两者分别保存为不可变 Modeling Workflow Artifact。向用户确认业务摘要、高优先级能力问题
和阻塞歧义后，再启动独立建模角色。每轮最多提出三个阻塞问题；问题的 open/answered/skipped/
uncertain/reopened current head 与显式决定保存为 Execution Event，恢复后不重复已回答或跳过的问题。

业务整理角色不设计 Class/Property/RelationType/Batch；建模角色无平台 credential，不获取 lease 或
apply；独立 reviewer 必须看到原资料清单/关键证据、Pack/Matrix、模型草案和 dry-run Findings。

### 6. 提交、评审并应用 Modeling Batch

获取 Ontology Modeling Context，以其 `workspace_version` 为预期版本组织命令：

1. `dry_run` 查看规范化 delta、Finding、item 依赖与资源标识；dry-run 不需要 lease。
2. 获取有效 lease 后，用新的稳定 idempotency key 执行 `apply_atomic`。
3. 只有调用方明确接受部分成功时才使用 `apply_partial`。
4. 网络中断后用原 idempotency key 重试或查询原 batch，不创建新 batch 猜测结果。
5. 遇到 stale workspace、lease/fence 冲突或 recovering 时停止写入，重新读取上下文并按返回状态恢复。

dry-run 后保存 review report。只有业务、语义、覆盖、证据、平台与独立评审六个门禁全部通过，主
Agent 才能获取 lease 并 apply exact reviewed batch。Finding 以 Attempt ID + `finding_fingerprint`
引用；相同 code/path 不能代替唯一身份。REVISE/BLOCKED 必须追加返工/阻塞事件并保留失败轮次。

Modeling Batch 是当前写入协议，不经过旧 Proposal/Review/Publish 队列。人工确认只决定 Agent 是否
继续提交下一批，不能伪装成平台 approve/publish 调用。

### 7. 查询、验证与导出

新消费会话先调用 REST `GET /api/semantic/scopes:discover` 或 MCP
`discover_semantic_scopes`，分页读取当前身份的授权目录并显式选择 Project/Ontology。不要因为候选
唯一而静默选择，也不要把发现时的 `workspace_version` 当成锁；后续查询会重新校验当前状态。

用 Ontology read model、Context Query、scoped SPARQL、SHACL validation、reasoning/rule 结果和
lineage 验证建模结果。普通 Agent 使用 Project/Ontology 范围，不需要读取或回传 Graph Set ID 和
graph IRI。完成后保存 checkpoint 并 complete/cancel Build Session。
同时保存 verification report 和事件，并可导出 JSON 或 Markdown 执行记录供另一个已授权 Agent
恢复。平台 validation 通过不能单独代表业务质量通过。

Context Query 返回结构化语义上下文，不生成最终答案。现有 Agent Test 页面仍会在平台内调用 LLM，
且中文分词能力不足，只是 R-009 完成前的 legacy 调试入口。

## 当前 UI 工作区

当前主导航按 Overview、Modeling、Debug、Settings 分组：

- Overview：Project Brief、Structured Requirements、Evidence Reference；
- Modeling：Classes、Entities、Rules、Facts；
- Debug：governance/runtime diagnostics、Build Context、Agent Test、Recall、MCP Tools、Graph Sets；
- Settings：编辑锁与平台依赖健康。

部分历史页面组件仍保留在代码中并重定向到当前工作区，它们不代表旧 Version、Proposal、Catalog、
Connector 或 Publication HTTP/MCP 协议仍然存在。

## HTTP 与 MCP

HTTP 完整 operation 清单见 [api.md](api.md)，MCP 完整工具清单见 [mcp.md](mcp.md)。两个清单都
从当前运行时 registry 生成，不应根据旧文档猜测 endpoint 或工具名。

常用 MCP 流程由以下能力组成：

- health、Project/Build Context、Ontology workspace；
- Brief、Interview Answer、Competency Question；
- Build Session、Checkpoint、Ontology Lease；
- Evidence Reference；
- Modeling Context、Modeling Batch、read model；
- Modeling Workflow Artifact/Event、question current state 和执行记录 export；
- Context Query、scoped SPARQL、lineage 和语义验证。
- 授权范围发现 `discover_semantic_scopes`。

当前不存在受支持的完整文件上传、Proposal/Review/Publish、Catalog/Connector、Neo4j Entity/Fact
MCP 流程。

## 存储与一致性

- PostgreSQL：Project/Ontology 元数据、访谈状态、Evidence Reference、Build Session、lease、
  Modeling Batch、Modeling Workflow Artifact/Event、rule、审计与 lineage 辅助状态。
- RDF Dataset / Oxigraph：当前本体结构、实例事实、Graph Registry/Graph Set、shape/policy 与语义
  statement。
- Search/Vector writer 当前仍为 fake/in-memory 边界，不是持久召回索引。

Modeling Batch 跨 PostgreSQL 与 RDF 存储不宣称单事务原子性。平台先保存确定性计划，使用 write
fence 隔离并发，并在原 attempt 下向前恢复不确定结果。

## 当前缺口

- R-009：Agent Test 尚未重构为纯 Context Query 诊断，仍有平台内 LLM 和中文分词缺口。
- R-010：v1.1 已交付固定 Dify 官方文档资料快照，但任务集、外部 Agent 执行器、指标报告以及
  R1.1-003 后的完整 Dify 集成重跑仍未闭环。
- P1：持久 Search/Vector、模块依赖、不可变 release、异步任务、完整构建工作台等仍未闭环。

需求目标与最新状态以 [requirements-v1.0.md](requirements-v1.0.md) 为准。
