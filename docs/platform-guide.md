# 平台使用介绍与后续特性规划

## 平台定位

Ontology Platform 是一个面向领域本体和知识图谱建设的本地 MVP 平台。它把领域 Schema、
图谱事实、证据、审核、版本发布、外部数据目录和 Agent 接口放在同一套工作流中管理。

平台当前不尝试替代数据库、ETL 系统、文档知识库或大模型服务。它的核心职责是：

- 保存项目、Ontology、Class、Property、RelationType 等领域模型。
- 在写入实体和关系前执行确定性校验。
- 用 PostgreSQL 保存元数据，用 Neo4j 保存图谱实例。
- 通过 Review Workbench 让人工审核 Agent 提交的建模和图谱候选。
- 通过版本机制保证已发布 Ontology 不被原地修改。
- 通过 Catalog、Semantic Mapping 和 Connector 描述外部数据在哪里、如何受控查询。
- 通过 HTTP API 和 MCP 工具为 UI、脚本和外部 Agent 提供统一入口。

## 本地启动

推荐使用一键脚本启动本地环境：

```bash
./scripts/start-local.sh
```

脚本会检查 PostgreSQL 和 Neo4j，安装或同步后端依赖，执行 Alembic 迁移，构建前端产物，
并启动后端 API 与前端预览服务。

手动启动时，可按以下顺序运行：

```bash
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

常用入口：

- 后端 API：`http://localhost:8000/api`
- FastAPI 文档：`http://localhost:8000/docs`
- 前端开发服务：Vite 输出的本地地址
- MCP 服务：`cd backend && uv run python -m app.mcp.server`

## 推荐使用流程

### 1. 创建项目和 Ontology

进入前端后，先在 Projects 区域创建项目，再在项目下创建 Ontology。项目是业务域容器，
Ontology 是该项目中的领域模型。

适合放入 Project Brief 的内容包括：

- 业务范围和排除范围。
- 关键实体的身份规则。
- 用户希望平台回答的能力问题。
- 重要数据源、证据来源和治理要求。

### 2. 定义能力问题

在 Competency Questions 页面维护平台需要回答的问题，例如：

- 某个学生是否选了某门课？
- 某门课有哪些成绩构成？
- 某个政策适用于哪些对象？
- 当前版本是否能解释某个事实来源？

能力问题用于约束建模方向，避免把数据库表结构直接复制成本体结构。

### 3. 上传和追踪证据

Sources 页面用于上传源文档、查看解析状态、检查文本块和追踪由证据生成的提案。
证据会被关联到 Schema、实体、关系和事实候选，供后续审核使用。

### 4. 构建 Schema

Schema 层由 Class、Property 和 RelationType 组成：

- Class 表示稳定领域概念，如 `Student`、`Course`、`Assessment`。
- Property 表示 Class 的结构化属性，如 `status`、`start_date`。
- RelationType 表示可遍历、可解释的领域关系，如 `ENROLLED_IN`、`APPLIES_TO`。

可以在 Classes 页面手动编辑，也可以让外部 Agent 通过 MCP 提交 schema proposal。
Agent 只提交候选，最终是否采纳由人工在 Schema Review 页面决定。

### 5. 审核并应用提案

Review Workbench 是治理边界。Schema Review 和 Graph Review 支持按 item 审核候选项：

- approve：接受候选。
- reject：拒绝候选。
- edit：人工编辑候选后再审核。
- merge：合并重复或相近候选。
- waive：在允许的场景下豁免阻塞项。

提案需要先通过平台的确定性校验，再由人工批准，最后应用到正式草稿版本。
Agent 不能通过自然语言对话直接批准、拒绝、发布或合并数据。

### 6. 写入实体和关系

Graph Manager 用于维护实体和实体间关系。实体写入会校验：

- 所属 Ontology 和 Class 是否存在。
- 必填属性是否齐全。
- 属性类型、枚举值和未知属性是否合法。
- 关系的 source 和 target 是否符合 RelationType 定义。
- 实体级关系是否符合 relation scope 策略。

实体和关系保存在 Neo4j 中，并复制必要的 Class 和 RelationType 元数据，便于查询和展示。

### 7. 搜索和解释图谱

Search 页面用于检索实体。后端支持 text、vector 和 hybrid 模式；启用 embedding 后，
实体名称、别名和属性会参与向量检索。

实体详情和 explain 接口可返回：

- 实体本身。
- 所属 Class schema。
- 直接关系。
- 附近相关实体。
- 用于 Agent 回答问题的上下文。

### 8. 执行事实审核

Fact Audit 页面用于对图谱中生成或推断出的 Fact Claim 做分层审核。平台支持生成事实声明、
抽样、标记 stale 状态，并记录 approve、reject、needs correction 等审核结果。

这个阶段用于降低错误事实进入发布版本的风险。

### 9. 发布版本

Publication 页面会检查发布前 gate，包括 Schema 校验、证据覆盖、能力问题状态、事实审核等。
通过 gate 并显式确认后，平台会发布不可变版本快照。

发布后的版本不能原地修改。后续变更应从已发布版本创建 successor draft。

### 10. 管理外部数据目录和连接器

Catalog 页面用于登记外部数据系统并建立语义映射：

- Data Source：外部系统，如数据库、API、文件存储。
- Data Resource：系统中的表、端点或文件。
- External Field：字段、敏感级别、访问策略、脱敏规则和审计要求。
- Semantic Mapping：把 Class、Property、RelationType 或 Entity 映射到外部字段。
- Connector Template：白名单查询模板，限定可查询字段和参数。

Connector 查询不会暴露数据库凭据，也不开放任意 SQL。平台会执行策略检查，返回授权状态、
拒绝原因、来源、查询时间和审计信息。

## 当前主要页面

- Overview：查看工作流阶段、当前版本、阻塞项和下一步。
- Brief：维护项目范围、身份规则和建模意图。
- Questions：维护能力问题和验证状态。
- Sources：上传和检查证据文档。
- Schema Review：审核 Schema 候选。
- Classes：维护 Class、Property 和 RelationType。
- Graph Review：审核实体、关系、合并和冲突候选。
- Entities：维护图谱实体和关系。
- Facts：执行事实声明审核。
- Publication：检查发布条件并发布版本。
- Versions：查看版本谱系、快照和 diff。
- Catalog：维护外部数据目录、映射和连接器。
- Search：测试实体检索。
- Agent Test：测试面向问题的 Agent 调用。
- MCP Tools：查看 Agent 可用工具。
- Evidence：追踪证据来源。
- Settings：查看运行时健康状态。

## Agent 和 MCP 用法

平台提供 MCP 工具，供外部 Agent 在不接触数据库凭据的情况下读取和提交候选数据。

常见 Agent 流程：

1. 调用 `check_platform_health` 确认平台依赖可用。
2. 调用 `get_build_context` 读取项目、Ontology、Brief 和问题状态。
3. 调用 `search_entities`、`get_entity`、`find_related_entities` 获取图谱上下文。
4. 调用 `propose_schema_changes`、`propose_entities` 或 `propose_relations` 提交候选。
5. 调用 `validate_proposal` 检查候选是否满足平台规则。
6. 调用 `list_review_items` 获取审核批次和前端 deep link。
7. 等待用户在 Review Workbench 中做治理决策。

MCP 明确不提供以下能力：

- 人工审核决策。
- 发布版本。
- 冲突最终裁决。
- 敏感外部数据的绕行访问。
- 任意 SQL 或原始 Cypher 执行。

## HTTP API 用法

HTTP API 是 UI 和脚本的主要入口。基础地址为：

```text
http://localhost:8000/api
```

常用资源包括：

- `/projects`：项目管理。
- `/projects/{project_id}/ontologies`：Ontology 管理。
- `/ontologies/{ontology_id}/classes`：Class 管理。
- `/classes/{class_id}/properties`：Property 管理。
- `/ontologies/{ontology_id}/relation-types`：RelationType 管理。
- `/ontologies/{ontology_id}/entities`：实体管理。
- `/ontologies/{ontology_id}/relations`：关系管理。
- `/proposals`：提案提交和治理流程。
- `/versions/{version_id}/publish`：版本发布。
- `/projects/{project_id}/data-sources`：外部数据源目录。
- `/projects/{project_id}/semantic-mappings`：语义映射。
- `/projects/{project_id}/connector-templates`：受控连接器模板。
- `/health/dependencies`：PostgreSQL 和 Neo4j 健康检查。

需要写入或治理操作时，按 README 中的约定携带 `Authorization: Bearer <ADMIN_TOKEN>`。

## 建模建议

建模时优先从能力问题和领域语言出发，而不是从表结构出发。

适合进入 Ontology 的内容：

- 用户会自然提到的稳定概念。
- 有独立身份和生命周期的对象。
- 会参与遍历、解释、推理或审核的关系。
- 会长期影响问答和业务判断的事实类型。

不建议直接进入 Ontology 的内容：

- 纯存储字段、索引、同步状态或运维字段。
- 只在一个外部系统内有意义的技术列名。
- 没有查询价值、无法维护时效性的零散事实。
- 敏感字段原文，如身份证号、密钥、隐私数据。

敏感或外部系统字段应优先放入 Catalog 和 External Field，再通过 Semantic Mapping 与
Ontology 关联。

## 后续可能新增的特性

### 更完整的权限和多租户

当前平台更偏本地 MVP。后续可以加入用户账号、组织、角色、权限、审计视图和更细粒度的
发布审批流程。

### 更强的版本和变更管理

后续可以增强版本 diff、迁移计划、向后兼容性检查、变更影响分析和跨版本查询能力。

### 更完整的 Catalog 和 Connector

当前连接器以白名单模板和本地确定性结果为核心。后续可以接入真实外部数据库、API 网关、
凭据托管、审批流、查询配额、缓存、脱敏策略和字段级审计报表。

### 身份解析和主数据能力

当前 identity resolution 只做确定性统计，不自动写入 `SAME_AS`。后续可以加入候选匹配、
置信度解释、人工确认队列、映射版本和实体合并回滚。

### 图谱推理与规则引擎

后续可以引入可配置规则、路径推理、约束检查、派生事实和冲突检测，但仍应保持可解释、
可审核和可回放。

### RDF/OWL/SHACL 兼容

平台当前使用自定义轻量模型。后续可以增加 RDF/OWL/SHACL 导入导出或兼容层，但不一定要把
它们作为内部主模型。

### 更强的 Agent 工作流

后续可以增强 `ontology-builder` Skill 的访谈、候选生成、证据引用、建模解释和失败恢复能力。
平台仍应保持治理边界：Agent 负责提出候选和解释理由，用户负责最终决策。

### 更丰富的前端工作台

可能新增的 UI 能力包括图谱可视化增强、批量编辑、审计仪表盘、Catalog 血缘视图、发布报告、
外部查询记录、权限配置和面向业务用户的只读探索视图。

### 数据质量和可观测性

后续可以加入重复实体检测、孤立节点提示、Schema 覆盖率、证据覆盖率、事实新鲜度、
embedding 回填状态、后台任务队列和系统运行指标。

## 当前边界

使用平台时需要注意以下边界：

- 已发布版本不可原地修改。
- Agent 提交的是候选，不是治理决策。
- 平台不开放原始 Cypher、任意 SQL 或外部系统凭据。
- 敏感字段应通过 Catalog 策略管理，不应直接写入图谱属性。
- 图谱事实需要考虑查询价值、维护能力和证据来源。
- 当前 MVP 仍以本地开发和验证为主，生产级认证、授权和运维能力需要后续补齐。

