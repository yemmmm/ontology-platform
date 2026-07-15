# v1.0 Agent 语义层平台需求清单

## 文档信息

- 文档状态：规划中
- 当前实现基线：`07888f7`
- 实现分支：`agent-semantic-layer-platform`
- 目标用户：单组织、小团队、自托管
- 参考验收场景：Dify 使用指南和 API 文档本体
- 更新日期：2026-07-15

本文件是下一阶段的需求与状态账本。实现任何需求后，必须同步更新其“当前状态”、
验收证据和相关提交，避免需求文档再次变成与代码脱节的历史计划。

## 状态与优先级

状态：

- `已实现`：当前代码已经满足本需求的主要验收标准。
- `部分实现`：已有可复用基础，但目标闭环尚未成立。
- `进行中`：已进入实现，尚未通过全部验收。
- `未实现`：当前没有可交付能力。
- `阻塞`：存在明确外部阻塞，必须记录原因。
- `延后`：不进入当前版本。

优先级：

- `P0`：Dify 参考闭环成立前必须完成。
- `P1`：首个闭环之后显著提升可用性、可靠性或扩展性。
- `P2`：规模化和持续运行能力。
- `不在范围`：明确不由本体平台承担。

投入使用 `S / M / L / XL` 表示相对工程量；投入产出比综合用户价值、依赖解锁数量和
实现复杂度评估。

## 已确认的目标边界

1. 外部建模 Agent + Skill 负责理解资料、澄清需求、提取知识和做建模判断。
2. 平台负责资料与证据管理、确定性验证、语义存储、版本、审计、查询和治理。
3. 外部消费 Agent 负责对话、规划、生成最终答案，并自行调用目标系统 API/MCP。
4. 平台不代理 Dify 等目标系统的操作，不保存目标系统明文凭证。
5. 平台为 Agent 提供自然语言检索和 SPARQL 两级查询入口，返回结构化语义上下文，
   不生成最终自然语言答案。
6. 每个本体独立治理和演进，通过图集合、导入关系、语义映射或桥接本体组合查询。
7. 首版由外部建模 Agent 自行读取资料；平台只保存 Agent 随建模结果提交的文档名和原文片段，
   不接管完整文档采集、解析和版本管理。
8. Dify 只作为通用能力的参考实现，平台代码不得包含 Dify 专用分支。

## v1.0 端到端验收闭环

```text
Dify 指南 / API 文档 / OpenAPI 文档
  -> 外部建模 Agent 直接读取资料并提取知识
  -> Agent 提交本体变更以及对应的文档名和原文片段
  -> 平台保存轻量证据引用并建立建模结果关联
  -> 平台确定性校验、写入、记录版本与审计
  -> 外部消费 Agent 发送自然语言查询或 SPARQL
  -> 平台返回资源、事实、关系、操作、约束、证据和版本上下文
  -> Agent 在测试 Dify 环境自行调用 API/MCP
  -> 完成工作流创建、发布和日志查询
```

## 当前实现基线

| 能力 | 当前状态 | 代码证据与差距 |
| --- | --- | --- |
| Project / Ontology 基础 CRUD | 已实现 | `backend/app/api/ontologies.py`；创建本体后不会初始化语义图和图集合。 |
| 结构化 Brief 与能力问题 | 已实现 | `backend/app/api/interview.py`、`backend/app/mcp/tools/interview.py`。 |
| RDF Dataset 与 SPARQL | 已实现 | Oxigraph、`RdfStoreRepository`、REST/MCP 只读 SPARQL。 |
| 受治理语义编辑 | 已实现 | Turtle、TriG、JSON-LD、受限 SPARQL Update、编辑审计和图可编辑性。 |
| 业务友好建模命令 | 已实现 | Class、Property、RelationType、Entity、Relation、Mapping、Fact 更新/删除等命令编译器。 |
| Graph Registry / Graph Set | 已实现 | 成员角色、来源签名、图修订、派生结果指针、过期检测、历史和差异。 |
| SHACL、推理和确定性规则 | 部分实现 | 服务和测试齐全；真实 OWL runner 依赖外部命令，执行仍是同步路径。 |
| 事实证据绑定 | 部分实现 | Postgres `fact_evidence_bindings` 已支持文档名和原文片段；尚未形成项目级复用引用，也未覆盖模型结构。 |
| 轻量证据引用 | 部分实现 | 事实绑定已有可复用字段；缺少项目级 Evidence Reference 写入、查询以及建模批次关联。现有 Artifact/Chunk 读接口不再代表 v1 目标。 |
| 固定语义读模型 | 已实现 | Classes、Entities、Facts、Readiness、History、Delta、Entity Search 等读模型。 |
| 自然语言语义查询 | 部分实现 | 当前只是 label/comment/IRI 子串查询；没有通用结构化上下文接口。 |
| Search / Vector 投影 | 部分实现 | 文档构建器和任务模型已存在，但运行时使用 `FakeSearchWriter` / `FakeVectorWriter`，结果不会持久化。 |
| Agent 查询测试 | 部分实现 | 当前 `agent-test` 在平台内调用 LLM 生成答案，与目标边界不一致，且中文分词能力不足。 |
| Agent 构建接口 | 部分实现 | REST/MCP 已支持 Project 级 Build Session、Checkpoint、恢复、幂等终态和 Ontology Lease；R-004 带证据建模批次尚未接入。 |
| 本体组合 | 部分实现 | Graph Set 可组合多个图，Mapping 命令存在；缺少本体依赖、导入版本和桥接关系契约。 |
| 身份认证和项目隔离 | 未实现 | `ApiKeyModel` 是未使用的骨架；HTTP/MCP 路由没有认证依赖，SPARQL 可查询整个 Dataset。 |
| 操作语义模型 | 未实现 | 尚无通用 Operation、参数、前置条件、效果、风险和外部工具绑定查询契约。 |
| 异步任务执行 | 未实现 | 投影、推理和规则没有持久任务队列、重试与恢复机制。 |
| Dify 端到端验收 | 未实现 | 当前没有固定资料集、问题集、外部 Agent 执行器和指标报告。 |

## 总需求排序

| ID | 需求 | 优先级 | 当前状态 | 投入 | 投入产出比 | 主要依赖 |
| --- | --- | --- | --- | --- | --- | --- |
| R-001 | 新建本体时自动创建默认语义工作区 | P0 | 已实现 | M | 极高 | 无 |
| R-002 | 轻量证据引用与建模结果关联 | P0 | 已实现 | S | 极高 | R-001 |
| R-003 | 外部 Agent 构建会话与 MCP 协议 | P0 | 部分实现 | M | 极高 | R-001、R-002 |
| R-004 | 外部 Agent 建模批次的预检、幂等应用与失败恢复 | P0 | 部分实现 | M | 极高 | R-001、R-003 |
| R-005 | 统一知识来源与推导链 | P0 | 部分实现 | L | 高 | R-002、R-004 |
| R-006 | 面向 Agent 的结构化语义上下文查询 | P0 | 部分实现 | L | 极高 | R-001、R-005 |
| R-007 | 通用操作语义与外部工具绑定 | P0 | 未实现 | M | 极高 | R-004、R-006 |
| R-008 | API/MCP 认证、授权与项目隔离 | P0 | 未实现 | L | 高 | R-001 |
| R-009 | Agent Test 外部化与查询诊断重构 | P0 | 部分实现 | S | 极高 | R-006 |
| R-010 | Dify 通用能力端到端验收套件 | P0 | 未实现 | M | 极高 | R-002 至 R-009 |
| R-011 | 当前 API/MCP/配置文档对齐 | P0 | 部分实现 | S | 高 | 无 |
| R-101 | HTML、站点、数据库 Schema 等来源适配器 | P1 | 未实现 | L | 高 | R-002 |
| R-102 | 来源变更检测与知识增量更新 | P1 | 部分实现 | L | 高 | R-101、R-004、R-005 |
| R-103 | 持久化 Search/Vector 投影与混合召回 | P1 | 部分实现 | L | 高 | R-006 |
| R-104 | 模块化本体依赖、导入和桥接 | P1 | 部分实现 | L | 高 | R-001、R-006 |
| R-105 | 不可变发布版本与按版本查询 | P1 | 部分实现 | L | 高 | R-001、R-005 |
| R-106 | 投影、推理和规则的异步任务框架 | P1 | 未实现 | L | 中高 | R-103 |
| R-107 | 面向用户的构建证据与进度工作台 | P1 | 部分实现 | L | 中高 | R-002、R-003 |
| R-108 | 查询审计、质量评测与可观测性 | P1 | 部分实现 | M | 高 | R-006、R-010 |
| R-109 | 细粒度 RBAC、服务账号和密钥轮换 | P1 | 未实现 | L | 中 | R-008 |
| R-110 | 可部署的 OWL Reasoner 运行方案 | P1 | 部分实现 | M | 中 | R-106 |
| R-201 | 定时同步、Webhook 与连接器调度 | P2 | 未实现 | XL | 中 | R-101、R-102、R-106 |
| R-202 | 外部系统实例资源的通用同步框架 | P2 | 未实现 | XL | 中高 | R-007、R-201 |
| R-203 | 跨项目可复用本体注册表与依赖解析 | P2 | 未实现 | L | 中 | R-104、R-105 |
| R-204 | 分布式任务执行、限流和容量治理 | P2 | 未实现 | XL | 中 | R-106 |
| R-205 | 多组织 SaaS 租户、计费与配额 | P2 | 延后 | XL | 低 | R-109、R-204 |

## P0 详细需求

### R-001 新建本体时自动创建默认语义工作区

当前状态：`已实现`

#### 要解决的问题

当前“创建 Ontology”只保存本体的基础信息；图注册、Graph Set 和图成员需要再通过语义
管理接口手工创建。结果是新本体没有确定的可操作数据边界：用户或外部 Agent 不知道应向
哪个图写入模型和事实、查询应使用哪个 Graph Set，也可能需要在 Debug 页面手工填写图 IRI。

本需求将 Ontology 作为一个语义工作区的根对象：一次创建本体，就得到一套可立即开始资料
接入、建模、校验和查询的默认图结构。它不负责自动生成领域模型内容；领域知识仍由外部
Agent 提议、平台校验和保存。

#### 目标行为

创建 Ontology 时，平台应在同一初始化流程中自动、幂等地创建或补齐以下资源：

- 默认本体定义图：存放类、属性、关系和语义约束等本体结构。
- 默认实例数据图：存放实体、关系事实和其他断言数据。
- 必要的 Shape / Policy 图：分别承载校验规则和治理策略；即使初始为空，也必须有明确的
  图角色和生命周期。
- 上述图的注册记录、初始修订记录和直接编辑策略。其中本体定义图和实例数据图默认可由
  已授权的建模流程写入，治理类图遵守其专用策略。
- 一个 `scope_type=ontology`、`scope_id=<ontology_id>` 的默认活动 Graph Set，并以明确角色
  组合这些图，例如 `asserted_ontology`、`asserted_data`、`shapes`、`policy`。
- 平台可由 Ontology ID 直接解析的工作区描述：默认 Graph Set、各角色对应的 graph IRI、各图
  当前修订、可编辑状态和当前来源签名（source signature）。普通 Agent 上下文以 Ontology
  工作区状态为主，不要求调用方读取或回传 Graph Set ID 和 graph IRI；受控 Debug/高级接口
  可以返回这些内部细节。

初始化资源的 IRI 与标识必须由 Ontology ID 按稳定规则推导，而不是由前端、Debug 页面或
Agent 临时指定。例如，对同一个 Ontology 重复执行初始化时，始终定位到同一组默认资源。

#### 交互与恢复要求

- `POST /projects/{project_id}/ontologies` 成功返回后，该 Ontology 已具备默认语义工作区；
  调用方无需再创建 Graph Set 或填写图 IRI。
- 提供内部服务及受控 REST/MCP repair 入口，用于发现并补齐历史本体或中断初始化留下的
  缺失资源。repair 只能创建缺失项或修复不一致项，不能悄然覆盖已有图内容和修订。
- 初始化过程应以原子事务完成；若涉及无法与数据库同事务提交的资源，则必须记录可恢复的
  初始化状态，并让 repair 可安全地收敛到完整工作区。
- 后续 R-003 至 R-006 在平台内部均以该默认 Graph Set 为默认语义范围；其中 R-003/R-004
  的普通 Agent 构建协议以 Ontology 为外部工作目标，由平台解析默认 Graph Set，不要求调用方
  填写 Graph Set ID 或图 IRI。R-002 的 Evidence Reference 归属 Project，其建模结果关联仍须
  在平台内部校验目标 Ontology 和 Graph Set。高级语义查询是否允许显式选择其他 Graph Set，
  由相应需求单独定义，但不能因缺省作用域缺失而无法工作。

验收标准：

- 创建 Ontology 后，无需进入 Debug 页面手工填写图 IRI、注册图或创建 Graph Set，即可开始
  写入资料、提交建模变更和执行默认查询。
- 每个新本体恰有一个默认活动 Graph Set；其中图成员角色完整、唯一，并且都归属该 Ontology。
- 对同一 Ontology 重试初始化或调用 repair，不会创建重复图、注册记录、修订记录或 Graph Set，
  也不会改写已有图内容。
- 面向 Agent 的 `build-context` 返回 Ontology 工作区是否就绪、工作区修订、可编辑状态、来源
  签名和问题摘要，不要求 Agent 读取或回传 Graph Set ID 和 graph IRI；受控工作区详情接口
  仍可返回默认 Graph Set、图角色和 graph IRI，用于平台诊断与高级语义操作。
- 初始化失败必须整体回滚，或留下可识别的待修复状态；repair 后可安全恢复为完整工作区。
- 已存在的历史 Ontology 可批量或按需执行 repair，并获得与新建本体一致的默认工作区结构。

### R-002 轻量证据引用与建模结果关联

当前状态：`已实现`

外部建模 Agent 自行访问并读取知识文档，从中提取本体结构、关系、实体和事实。平台不要求
Agent 先上传完整文档，也不负责下载、解析、分块或版本化外部文档。Agent 提交建模结果时，
只需同时提交支持该结果的文档名和原文片段，平台将其保存为项目级 `Evidence Reference`，
并与相应建模项建立可查询的证据关联。

每个 Evidence Reference 只包含 Agent 实际提供的证据内容：

- `document_name`：人和 Agent 可识别的文档名称。
- `excerpt`：直接摘录的文档片段，不允许只提交摘要或 Agent 推断。
- 平台生成的 ID、所属 Project、内容哈希、创建主体和创建时间。

Evidence Reference 归属 Project，不归属某个 Ontology。项目内任一本体都可以把模型结构、
实体、关系或事实关联到已有引用；产生关联不复制证据内容。平台保存引用不代表已经持有完整
文档，也不对片段是否真实存在于外部文档作独立背书。

#### 创建与关联协议

- Evidence Reference 可以通过独立 REST/MCP 调用预先创建，也可以在建模批次的具体建模项中
  以内联方式提交。批次内联是外部建模 Agent 的主要路径。
- 每个建模项可以通过 `evidence_reference_ids` 复用已有引用，也可以通过 `evidence` 内联提交
  一个或多个 `{document_name, excerpt}`。同一项可以混合使用两种方式。
- Evidence Association 必须关联到批次中的具体建模项及其最终写入结果，而不是只挂在整个
  批次上。一个建模项可关联多个 Evidence Reference，一个 Evidence Reference 也可支持项目内
  不同本体的多个建模项。
- 建模项必须有稳定的客户端项标识，平台据此返回逐项证据解析结果、校验错误和最终关联结果。
  Evidence Association 应进入相应资源的 lineage、编辑审计和版本上下文。
- 不单独创建“Ontology 使用某文档”的关系；Ontology 与证据之间的关系由具体建模项上的
  Evidence Association 得出。

#### 规范化与幂等

- `document_name` 和 `excerpt` 去除首尾空白；`excerpt` 的 CRLF/CR 换行统一为 LF。内部空白、
  大小写、标点和正文内容保持不变，平台不得做摘要、纠错或语义改写。
- 规范化后 `document_name` 和 `excerpt` 都必须非空。
- `excerpt_hash` 使用规范化片段的 UTF-8 字节计算 SHA-256。
- Evidence Reference 的幂等键为
  `(project_id, normalized_document_name, excerpt_hash)`。命中时返回已有 ID；同名但片段不同，
  或片段相同但文档名不同，均创建不同引用。
- 独立创建和批次内联创建必须使用同一套规范化与去重规则；建模批次的 idempotency key 还要
  保证网络重试不会重复创建 Evidence Association。

#### 事务与错误语义

- 默认原子批次中，Evidence Reference 创建、建模结果写入和 Evidence Association 创建属于
  同一应用事务。任一建模项或证据校验失败时全部不落库，不留下孤立引用或部分关联。
- dry-run 不创建 Evidence Reference 或 Evidence Association，但必须返回每个内联证据将复用
  的已有引用，或规范化后的待创建候选及其幂等键，以及全部证据校验结果。
- R-004 显式启用部分应用时，只为成功建模项创建或关联其 Evidence Reference；仅被失败项
  使用的内联证据不得单独落库。
- 空文档名、空片段和格式不合法返回逐项校验错误；引用不存在、跨项目引用或目标建模项不存在
  时拒绝建立关联。跨项目引用对调用方表现为资源不可用，不泄露其他 Project 的证据信息。
- 首版 Evidence Reference 不可修改。文档名或片段需要更正时创建新引用，并通过新的建模变更
  更新关联；已经进入历史审计的旧引用继续保留。

验收标准：

- REST 与 MCP 均支持创建、读取和列出项目级 Evidence Reference。
- 创建只要求 `document_name` 和非空 `excerpt`；不要求上传文件、来源 URI、页码、字符范围、
  解析状态或来源版本。
- 同一 Project 内规范化文档名和片段内容均相同时幂等复用已有引用；同名但片段不同则创建
  不同引用。
- 项目内所有 Ontology 均可关联已有 Evidence Reference，但必须校验 Project 归属，禁止
  跨项目引用。
- schema、entity、relation、fact、mapping、rule 和 operation 等建模项均可关联零个或多个
  Evidence Reference；没有证据时必须保留“无证据”状态，不能伪造引用。
- 查询建模结果时能够返回关联的文档名和完整片段；证据关联进入编辑审计和版本上下文。
- 已被建模结果或审计引用的 Evidence Reference 不得物理删除；首版可以不提供删除接口。
- 独立创建、批次内联、dry-run、原子失败、显式部分应用和相同请求重试均有服务级测试，证明
  不会产生重复引用、重复关联或失败项遗留数据。

实现证据：`2dbe342`、`61f56f6`；迁移 `0021_lightweight_evidence`；REST
`evidence-references` / `evidence-associations`、四个 MCP 工具、canonical write 与事实证据兼容
接入，以及 Overview 下的项目共享 Evidence 页面。

验证证据：`cd backend && uv run pytest`（474 passed）；`cd frontend && npm run build`；
`cd frontend && npx playwright test`；真实 PostgreSQL/Oxigraph 环境完成迁移、引用幂等、项目级
查询、默认 Ontology 工作区关联和临时数据清理验证。

### R-003 外部 Agent 构建会话与 MCP 协议

当前状态：`部分实现`（R-003 会话协议已落地，R-004 apply 接线未完成）

最后更新：2026-07-15

实现证据：`2cfbfc1`；迁移 `0022_build_sessions`；Project Build Context、Build Session、
Checkpoint、Ontology Lease 共十个 REST 能力和十个 MCP 工具；旧 `get_build_context` MCP 工具
保留为 deprecated 委托别名；`BuildSessionService.authorize_apply(...)` 已提供工作区版本 guard。
Debug 区域已增加只读 Project 级 Build Context 诊断页，直接展示 `platform_state` 与
`agent_state`，支持最近会话游标分页、按需读取 Session 详情、确定性诊断提示及原始 JSON；
页面不提供任何 Session、Checkpoint 或 Lease 修改操作。前端实现见
`frontend/src/pages/BuildContextDebugPage.tsx`，设计见
`docs/superpowers/specs/2026-07-15-r003-build-context-debug-design.md`。

验证证据：`cd backend && uv run pytest`（495 passed，1 skipped）；
`RUN_POSTGRES_CONCURRENCY_TESTS=1 uv run pytest tests/test_build_session_postgres.py`（1 passed，
两条真实 PostgreSQL 连接竞争同一 Ontology 时恰好一个成功）；`uv run alembic upgrade head` 后
当前版本为 `0022_build_sessions (head)`。
前端诊断页验证：`cd frontend && npm run build`；
`cd frontend && npx playwright test tests/build-context-debug.spec.ts`（4 passed）；
`cd frontend && npx playwright test`（30 passed）。

剩余问题：R-004 的实际 apply 路径尚未调用 `authorize_apply(...)`，也尚未把建模批次、验证结果
和 Evidence Association 聚合进 Build Context。因此本项仍保持“部分实现”，不能标记为
“已实现”。R-008 认证授权仍是外部接入前的独立安全依赖。

技术设计：`docs/superpowers/specs/2026-07-14-r003-build-session-design.md`

#### 要解决的问题

实施前，`GET /projects/{project_id}/build-context` 只是 Project、Brief、Ontology 列表和能力问题的
聚合快照，不能区分一次具体的外部 Agent 工作过程，也没有检查点、恢复、并发保护和建模批次
关联。Agent 中断后仍依赖自己的聊天记录或本地文件判断做到哪里；两个 Agent 同时修改同一
Ontology 时，平台也不能在写入前明确发现冲突。

平台需要保存一次外部 Agent 构建或更新工作的服务器端进度，但 Agent 运行时仍在平台外部，
平台不调度或托管模型，不保存完整对话，也不替 Agent 决定下一步建模计划。

#### 作用域与核心概念

- `Build Context` 是 Project 级、由服务器生成的恢复视图。它让 Agent 看到整个 Project 的
  Brief、全部 Ontology、未解决事项、活动或最近 Build Session、已接受建模批次、失败和最近
  活动，而不是只返回某个 Ontology 的局部状态。
- `Build Session` 归属一个 Project，记录一段外部协调的连续工作过程。不同的已授权 Agent
  实例可以恢复同一 active Session；一个 Session 可以依次查看或更新 Project 内多个
  Ontology，创建 Session 不会自动锁定整个 Project。
- `Build Checkpoint` 是 Agent 上报的追加式进度记录，至少包含阶段、当前步骤、下一步、当前
  关注的 Ontology、阻塞项或失败原因。Checkpoint 表达 Agent 的工作意图，不能覆盖平台已经
  观察到的批次、验证、Evidence Association、修订和错误事实。
- `Ontology Lease` 是 Build Session 对某个 Ontology 的限时独占编辑权。读取 Build Context、
  查询 Ontology 和执行不落库的分析不需要租约；真正应用建模变更时必须持有有效租约。
- Graph Set 是平台内部的语义数据范围和审计信息。R-003 的外部 REST/MCP 协议以
  `project_id`、`build_session_id` 和 `ontology_id` 为主要标识，不要求 Agent 选择、创建或管理
  Graph Set。平台在内部解析默认工作空间，并把实际 Graph Set、图修订和来源签名记录到批次
  与审计中，以支持重放和问题诊断。

本项只调整构建协议的外部边界。R-006 是否继续要求调用方显式指定 Graph Set，应在细化
R-006 时单独决定，不能由 R-003 默默改变。

#### 平台事实与 Agent 检查点

Build Context 必须明确区分两类进度：

1. **平台观察状态**：由已持久化的 Project Brief、能力问题、Ontology、Evidence Reference、
   建模批次、验证结果、修订和审计确定性生成，Agent 不能通过 Checkpoint 改写。
2. **Agent 报告状态**：由最新 Build Checkpoint 表达，包括当前阶段、当前步骤、下一步、工作
   摘要、关注的 Ontology、阻塞项和失败说明。平台保存这些内容，但不把它们伪装成已经完成的
   平台事实。

因此，即使 Agent 上报“模型已完成”，只要平台没有对应成功批次和验证记录，Build Context
仍必须分别展示“Agent 报告已完成”和“平台尚未观察到完成证据”。

#### 生命周期

Build Session 首版只使用三个持久状态：

- `active`：工作尚未显式结束，可以继续追加 Checkpoint、获取 Ontology Lease 和关联建模批次。
- `completed`：调用方显式完成，记录完成摘要并释放全部租约；这是终态，不代表 Ontology 已
  发布或通过全部质量门槛。
- `cancelled`：调用方显式取消，必须记录原因并释放全部租约；这是终态。

`resume` 是恢复一个 `active` Session 的动作，不是单独状态。Agent 进程退出、网络断开或租约
过期都不会自动把 Session 改成 `failed`、`cancelled` 或 `completed`。失败属于 Checkpoint 或
具体建模批次的结果；外部 Agent 可以读取失败原因后在同一 active Session 中修正并继续。
已完成或已取消的 Session 不可重新打开，需要继续工作时创建新的 Session，并可记录前序
Session ID。

完成 Session 前不得存在仍在执行的建模批次。完成不要求所有 Ontology 都达到发布就绪，因为
一次 Session 可以只是局部更新；完成摘要必须说明本次实际完成的范围和未解决事项。

#### 检查点、恢复与乐观并发

- 每个 Checkpoint 有稳定的客户端 Checkpoint ID 和服务器序号；相同客户端 ID 重试时幂等
  返回原记录，不重复追加。
- Session 保存单调递增的 `revision`。追加 Checkpoint、完成或取消时，调用方提交
  `expected_revision`；版本不匹配返回冲突以及当前 revision，避免两个 Agent 静默覆盖进度。
- Checkpoint 采用追加式历史，不能修改或删除旧记录。Build Session 可缓存最新 Checkpoint
  以便读取，但历史仍是恢复和审计依据。
- 恢复响应至少返回 Session 状态与 revision、最新 Checkpoint、涉及的 Ontology、已接受及失败
  批次、相关 Evidence Reference、当前租约、最近活动时间和可继续读取的历史游标。
- Build Context 可以使用摘要和分页，不能因为响应大小而无提示地截断恢复所需记录；若详细
  Evidence 或批次内容通过独立 REST/MCP 读取，必须返回稳定 ID 和明确的继续读取入口。
- 平台不保存 Agent 在外部文档中的阅读光标、浏览器状态或本地文件路径。Agent 需要恢复资料
  阅读时，依赖自身能力重新定位；平台只保存已经提交的 Evidence Reference 文档名和原文片段。

#### Ontology Lease 与冲突语义

- 同一 Ontology 同一时刻最多有一个有效写租约；不同 Ontology 可以由不同 Build Session
  并行处理。一个 Session 可以持有多个 Ontology Lease，但单个建模批次只能作用于一个
  Ontology，不提供跨 Ontology 原子写入。
- 获取租约返回不透明 lease token、到期时间和租约 revision。租约只能由持有它的 Session
  续期或主动释放；token 只在请求和响应中使用，平台不得明文持久化。
- 对同一 Session 和 Ontology 重试获取租约必须幂等。若租约已被其他 Session 持有，返回冲突、
  到期时间和可安全公开的持有会话信息，不等待、不抢占。
- 租约到期后其他 Session 可以获取新租约；旧 token 随即失效。旧 Agent 后续提交写批次时
  必须被拒绝，不能因为它曾经持有租约而继续写入。
- 租约只解决编辑并发，不是身份权限。调用方还必须通过 R-008 的 Project/Ontology 授权校验。
- 除租约外，R-004 的 apply 还应校验 Agent 开始编辑时看到的 Ontology 工作空间修订或等价
  来源签名，防止租约释放后基于过期上下文提交变更。

#### REST 与 MCP 协议

首版 REST 至少提供以下稳定能力；路径名称可在实现设计中调整，但语义不能合并丢失：

- `GET /projects/{project_id}/build-context`：读取 Project 级完整恢复上下文。
- `POST /projects/{project_id}/build-sessions`：幂等创建 Build Session。
- `GET /build-sessions/{session_id}`：读取一个 Session 的恢复详情。
- `POST /build-sessions/{session_id}:resume`：校验 Session 可恢复并记录最近活动。
- `POST /build-sessions/{session_id}/checkpoints`：幂等追加 Checkpoint。
- `POST /build-sessions/{session_id}:complete`：显式完成并释放租约。
- `POST /build-sessions/{session_id}:cancel`：显式取消并释放租约。
- 获取、续期和释放 Ontology Lease 的受控入口。

MCP 至少提供对应的 `get_project_build_context`、`create_build_session`、`get_build_session`、
`resume_build_session`、`save_build_checkpoint`、`complete_build_session`、
`cancel_build_session`、`acquire_ontology_lease`、`renew_ontology_lease` 和
`release_ontology_lease` 工具。MCP 响应与 REST 使用同一服务层和状态语义，不能维护一套不同的
会话逻辑。

所有修改型 REST/MCP 调用都必须支持稳定客户端请求 ID，使超时重试不会重复创建 Session、
Checkpoint 或终态操作。创建、恢复、Checkpoint、租约和终态操作都要更新服务器端
`last_activity_at`；普通读取是否计入最近活动必须固定为“不计入”，避免监控轮询伪造活跃状态。

#### 与 R-002、R-004 的衔接

- R-003 只管理会话、进度和编辑租约，不直接定义 schema、entity、relation、fact、mapping、
  rule 或 operation 的批量写入格式；该格式由 R-004 定义。
- R-004 的每个 apply 批次必须关联一个 active Build Session、一个 Ontology 和有效 Ontology
  Lease，并记录平台内部解析出的 Graph Set、目标图修订和来源签名。dry-run 可以关联 Session，
  但不要求写租约。
- 建模批次中的 Evidence Reference 创建、复用和 Evidence Association 仍遵守 R-002；Build
  Session 只通过批次和具体建模项关联证据，不创建“整个 Session 使用某文档”的替代关系。
- 成功批次、失败批次和确定性校验结果必须进入平台观察状态并更新 `last_activity_at`。平台不得
  自动编造 Agent 的下一步；Agent 可在读取批次结果后追加新的 Checkpoint。

验收标准：

- 可通过 REST 与 MCP 幂等创建、恢复、完成和取消 Project 级 Build Session；一个 Session
  可以记录多个 Ontology 的工作，但每个建模批次只作用于一个 Ontology。
- Project 级 Build Context 同时返回平台观察状态与 Agent 最新 Checkpoint，能够覆盖全部
  Ontology、活动或最近 Session、批次、失败、证据引用入口和最近活动，不依赖 Agent 本地文件
  才能恢复服务器端工作。
- Session 只使用 `active`、`completed`、`cancelled` 三种持久状态；断线和租约过期不会破坏
  active Session 的可恢复性，失败批次可在同一 Session 内修正后继续。
- 外部 Agent 只需使用 Project、Build Session 和 Ontology 标识完成普通构建流程，不需要填写
  Graph Set ID 或 graph IRI；平台内部审计仍可追溯到实际 Graph Set、图修订和来源签名。
- 同一 Ontology 的并发写入受租约保护；不同 Ontology 可并行。租约到期后旧 token 无法写入，
  乐观 revision 冲突不会覆盖较新的 Checkpoint 或终态。
- Agent 可以在 R-004 建模批次中创建或复用项目级 Evidence Reference；平台不负责恢复 Agent
  外部文档的读取位置，也不创建 Session 级伪证据关系。
- 创建重试、Checkpoint 重试、租约重试、断线恢复、过期租约、旧 token、revision 冲突、失败
  批次后继续、完成释放租约和取消释放租约均有服务级测试。

### R-004 外部 Agent 建模批次的预检、幂等应用与失败恢复

当前状态：`部分实现`

在现有直接 RDF 编辑和 canonical command 之上，增加适合外部建模 Agent 的
批量预检与应用协议。`Modeling Batch（建模批次）` 是一次只针对一个 Ontology 的
提交单元；`Modeling Item（建模项）` 是其中具有稳定客户端标识的最小建模变更。

#### 已确认的应用权限边界

- `apply` 是将通过确定性校验的 Modeling Batch 写入语义工作区的技术动作，
  不等同于人工 `approve`。
- 外部建模 Agent 可以直接调用 apply，不需要另一个人工 apply 步骤；但平台必须先校验
  active Build Session、目标 Ontology、有效 Ontology Lease、预期工作区版本与调用方权限。
- 任一会话、租约、版本、权限或确定性校验失败时，不得开始正式语义写入。
- 对于显式启用人工评审的独立治理流程，Agent 仍然只能提交提案并读取决定，不能
  代替用户 approve、reject、解决冲突或发布版本。R-004 的默认建模闭环不以该人工
  评审流程为前置条件。

#### 统一批次提交与执行模式

- REST 只提供一个“提交 Modeling Batch”能力，MCP 只提供一个对应工具；请求使用
  `mode` 选择 `dry_run`、`apply_atomic` 或 `apply_partial`，不为三种模式维护
  三套接口。
- `dry_run` 执行完整命令编译、证据预解析和确定性校验，返回规范化 delta、
  逐项结果与当前 `workspace_version`；它不要求 Ontology Lease，也不写入语义数据、
  Evidence Reference 或 Evidence Association。
- `apply_atomic` 是默认应用模式。任一 Modeling Item 校验失败时整批不写入；
  错误项返回 `failed`，其他未应用项返回 `not_applied`。
- `apply_partial` 只在调用方显式选择时启用。平台先预检全部项，再一次性写入与
  失败项无依赖的成功子集；校验失败项返回 `failed`，依赖失败项的项返回
  `blocked`，独立成功项返回 `applied`。
- 未单独调用 `dry_run` 不代表跳过预检；两种 apply 模式都必须在正式写入前重新
  执行同等强度的全部校验。
- 三种模式使用同一请求与响应结构。幂等键绑定包含 `mode` 的规范化请求；
  相同键与相同请求返回原结果，相同键与不同内容返回 `idempotency_conflict`。
  从 `dry_run` 切换到 apply 必须使用新的幂等键。

#### Modeling Batch 与 Batch Attempt

- Modeling Batch 表示一组不可变的建模内容，平台保存其规范化内容哈希。同一
  Build Session 中重用 `client_batch_id` 但改变命令、payload、依赖、证据、理由或能力问题时，
  返回 `batch_content_conflict`；修正后的建模内容必须使用新 `client_batch_id`。
- 每次 `dry_run`、`apply_atomic` 或 `apply_partial` 调用都建立或幂等复用一个
  `Batch Attempt（批次尝试）`。Attempt 记录自己的 mode、idempotency key、预期工作区版本、
  校验结果、规范化 delta、状态、时间和应用前后签名，但不复制或修改 Batch 内容。
- 同一 Batch 可以有多个 dry-run Attempt，以记录它在不同 `workspace_version` 上的校验结果；
  旧结果必须保留所依据的版本，不得伪装成对当前工作区仍然有效。
- Attempt 状态使用 `validating`、`validated`、`validation_failed`、`applying`、
  `recovering`、`applied`、`partially_applied` 和 `failed`。`failed` 只表示无法恢复的执行故障，
  普通建模校验失败必须使用 `validation_failed`。
- Batch 在只有 dry-run 或校验失败时保持 `open`；存在正在执行或恢复的 apply Attempt 时
  聚合为 `applying` 或 `recovering`；成功后终止为 `applied` 或 `partially_applied`。
- 同一 Batch 同一时刻最多只能有一个非终态 apply Attempt。Batch 终止后，任何新幂等键的
  重复 apply 也只返回已有应用结果，不再写入；`partially_applied` 中失败或被阻断的内容
  需要修正时，必须提交新 Modeling Batch。
- 存在 `validating`、`applying` 或 `recovering` Attempt 时，同一 Batch 不得启动另一个 apply，
  所属 Build Session 也不得完成。相同幂等请求必须返回或推动原 Attempt 收敛。

#### 跨存储写入与恢复

- apply 在开始任何语义或证据副作用前，必须先持久化 Attempt 的规范化请求哈希、
  目标 Graph Set 和图修订、来源签名、delta 及其哈希、最终成功项或组以及预期证据变更。
- RDF 与 PostgreSQL 写入结果无法立即确定时，Attempt 进入 `recovering` 而不是直接
  `failed`。平台根据已持久化的写入计划与实际图、审计、证据、修订和来源签名对比，
  安全重试未发生的写入或补齐已发生写入的剩余记录。
- Agent 使用相同 idempotency key 重试时，必须返回或推动原 Attempt 恢复，不创建
  新 Attempt，也不通过重新编译而生成不同资源标识、delta 或证据计划。
- 恢复过程不得通过无条件删除图内容猜测回滚。收敛完成后 Attempt 进入 `applied` 或
  `partially_applied`；只有当平台能证明无法恢复时才进入 `failed`，并保留稳定错误码、
  已观察状态和需要的人工处置提示。
- Build Context 和 Batch 读接口必须显示 `recovering` Attempt、最近恢复结果与是否可安全重试，
  不能让 Agent 通过 Checkpoint 把不确定写入标记为已完成。

#### 命令承载范围

- R-004 建立可扩展的 Modeling Command Handler 注册机制。现有 canonical compiler 作为
  RDF delta 类命令的 handler；批次协议不假设每种建模命令都只修改 RDF。
- R-004 首版接入已定义的 schema、entity、relation、fact、mapping 命令，并为已存在的
  Rule 定义提供建立、更新和删除 handler。
- R-007 先定义 Operation 的领域模型、存储和查询契约，再将 Operation handler 注册到
  同一批次协议；接入时不得新增一套 Operation 专用批次接口。

#### Ontology 作用域与目标图解析

- 普通 R-004 批次只在顶层指定一个 `ontology_id`。调用方不得传入或覆盖
  `graph_set_id`、`target_graph_iri` 或 `shape_graph_iris`，Modeling Item payload 也不再
  重复接受 `ontology_id`。
- 平台必须根据 `ontology_id` 解析该 Ontology 的默认活动 Graph Set，再根据
  `command_kind` 将 Class、Property、RelationType 和 Mapping 定位到
  `asserted_ontology`，将 Entity、Relation 和 Fact 定位到 `asserted_data`，将
  Shape/Constraint 定位到 `shapes`。Rule Definition 按其 handler 的受控存储契约处理，
  不由 Agent 为它指定 asserted RDF 目标图。
- 命令编译和应用前必须验证默认 Graph Set 完整且归属目标 Ontology，解析出的
  Named Graph 由平台管理、允许直接编辑且未锁定。任一检查失败都不得改写到
  其他图作为降级路径。
- 响应和审计必须返回平台内部解析的 Graph Set、目标图角色、图 IRI、应用前后修订
  与来源签名；这些是只读的诊断和追溯信息，不是请求输入。
- 显式图选择仍可以存在于高级直接 RDF 编辑、Graph Set 管理或管理员 Debug 能力中，
  但不属于 R-004 的普通 Agent 批次协议。

#### Modeling Item 契约与批次内引用

- 每个 Modeling Batch 必须有一个由调用方提供的稳定 `client_batch_id`，用于标识
  同一组建模内容；它可在 `dry_run` 和后续 apply 之间保持不变，但不代替每次
  请求的 idempotency key。修改批次命令、payload 或关联资料后必须使用新的
  `client_batch_id`。
- 每个 Modeling Item 只包含一个 `command_kind` 及其严格类型的 `payload`，并提供
  在当前批次内唯一的 `client_item_id`。未知字段、未注册命令和与命令 schema
  不匹配的 payload 必须作为逐项校验错误返回。
- Modeling Item 可使用结构化 `resource_id` 引用已有资源，或使用结构化
  `item_ref` 引用同批次其他建立项的输出。不使用 `@item:...` 等嵌入普通字符串的
  隐式引用语法。
- 平台在编译前为建立项预分配资源标识。未显式给出受允许资源标识时，标识必须
  由 Ontology、`client_batch_id`、`client_item_id` 和 `command_kind` 确定性生成，使同一
  建模内容的 dry-run、apply 和网络重试得到同一资源标识和规范化 delta。
- Modeling Item 还可通过 `depends_on` 声明“当前项只能在指定项成功时应用”。
  `depends_on` 表达成功依赖，不表达严格的逐项执行顺序；平台还要从 `item_ref`
  和命令资源引用中推导隐式成功依赖。
- 平台必须先解析全部资源标识和引用，再针对整个候选状态编译与校验。
  资源之间的循环引用、自引用或领域关系成环不自动构成批次错误；是否违反继承、
  状态流转或其他语义规则，由对应命令和领域校验器判定。

#### 原子依赖组与部分应用

- 平台将通过显式或隐式成功依赖互相成环的 Modeling Item 识别为一个
  `Atomic Dependency Group（原子依赖组）`。循环本身是合法的，组内项不按先后顺序单独写入。
- `apply_partial` 中，一个原子依赖组只能全部应用或全部不应用。组内任一项发生
  阻断错误时，该项返回 `failed`，同组其他本身可通过的项返回 `blocked`，依赖该组的
  后续项或组也返回 `blocked`。
- 循环组全部校验通过时应作为一个整体应用；与该组无依赖的其他组仍可在
  `apply_partial` 中独立应用。平台可以将强连通分量折叠为无环组图，以稳定地计算
  失败传播与返回顺序。
- `apply_atomic` 仍以整个 Modeling Batch 为唯一原子单元；原子依赖组只用于诊断和
  逐项状态归因，不改变“任一项失败则整批不写入”的语义。

#### 校验层级与 Validation Finding

- 无法进入批次处理的请求级问题使用 HTTP 错误表达，包括认证或授权失败、
  Session/Ontology 不可用、Lease 无效、workspace version 或幂等冲突以及顶层请求
  schema 错误。这类问题不得伪装成某个 Modeling Item 失败。
- 顶层请求合法后，命令 payload、资源引用、证据、领域约束和候选图校验问题必须
  通过正常 Modeling Batch 响应一次性返回，不能在第一个错误处中止而强迫 Agent
  反复提交才发现其他问题。
- 每个确定性校验结果统一表达为 `Validation Finding`，至少包含稳定 `code`、
  `severity`、`scope`、受影响的 `client_item_ids`、请求字段 `path`、可读 `message`、
  结构化 `details`、`blocking` 和 `retryable`。`scope` 只使用 `batch`、`group`
  或 `item`，Agent 不需要解析服务器异常文本。
- `severity=error` 是阻断问题，`severity=warning` 允许应用但必须进入响应和审计，
  `severity=info` 只提供规范化或诊断信息。首版中 `blocking` 必须与 severity 固定映射，
  不允许 handler 返回非阻断 error 或阻断 warning。
- 没有证据或建模理由可以返回 warning/info 并保留对应无证据状态；证据格式错误、
  引用不存在或跨 Project 则是 error。R-004 不提供通用 `force`、`validate=false` 或
  `ignore_warnings` 参数绕过确定性校验；未来需要风险确认时必须使用具体政策的
  专用 acknowledgement。
- 单项都可编译但合并候选状态冲突、违反 SHACL 或其他跨项约束时，Finding
  必须尽可能归因到具体 Item 或原子依赖组。无法安全归因的阻断 Finding 必须使用
  `scope=batch`，两种 apply 模式都不得在无法确定安全子集时猜测应用。

#### `apply_partial` 候选子集收敛

- 平台必须先编译和校验完整候选状态，移除包含阻断 Finding 的原子依赖组后，
  重新构造剩余候选状态并重跑跨项与 SHACL 校验。
- 如果移除失败组后产生新的阻断问题，平台继续移除新失败组并重跑校验，直到
  成功子集稳定或不再存在可应用项。每轮移除顺序和最终子集必须确定性可重放。
- 只有最终稳定子集才能一次性应用，其 Evidence Reference、Evidence Association、审计、
  图修订和过期状态与实际成功项保持一致。

验收标准：

- 一次批次可包含 schema、entity、relation、fact、mapping 和 rule 变更；Operation 在
  R-007 定义后通过相同 handler 机制接入。
- 单一 REST/MCP 提交能力支持 `dry_run`、`apply_atomic` 和 `apply_partial`，返回
  规范化 delta、SHACL/平台校验结果和逐项错误或状态。
- 同一不可变 Modeling Batch 可保留多次 dry-run 和 apply Attempt 的完整历史；成功应用后
  任何重试都不会重复写入，内容修正使用新 Batch 而不改写已有审计。
- RDF 或 PostgreSQL 写入中断后，相同 Attempt 可根据事前持久化的 delta 和来源状态
  收敛到确定终态，不重复写入、不新建 Attempt，也不伪装成普通校验失败。
- Agent 只提供 Ontology 标识即可混合提交多种建模命令；平台确定性解析默认 Graph Set
  和目标图，请求不接受 Graph Set ID 或 graph IRI 覆盖。
- 每个 Modeling Item 只承载一个严格类型命令，并可以结构化引用已有资源或同批次
  建立项；循环引用可以通过预分配标识和候选状态整体校验安全处理。
- `apply_partial` 将循环成功依赖折叠为原子依赖组，不会因为存在环而直接拒绝，也不会
  部分写入一个未完整的循环组。
- 请求级错误、逐项或组错误、批次级候选状态错误使用稳定且可区分的协议；
  警告不阻断应用，Agent 无法通过通用开关跳过确定性校验。
- `apply_partial` 的最终成功子集在实际写入前再次通过全部跨项与 SHACL 校验，
  无法归因的批次级阻断问题不会产生猜测性部分写入。
- apply 使用 idempotency key；网络重试不得重复写入。
- 批次默认原子应用；需要部分应用时必须显式声明并返回逐项状态。
- 每项可关联 Evidence Reference、建模理由或能力问题。
- 成功后更新图修订、来源签名、过期状态、编辑审计和 Build Session 进度。

### R-005 统一知识来源与推导链

当前状态：`部分实现`

统一不同知识类型的来源表示：

- 提取事实：文档名和原文片段组成的 Evidence Reference。
- 模型结构：Evidence Reference 或 Agent 建模理由/能力问题。
- 推理结果：Reasoning/Rule Run、规则版本和前提事实。
- 人工编辑：认证主体、时间和修改原因。

验收标准：

- 查询任一结构、事实或派生结果时，都可获取其 lineage。
- 缺少证据的内容允许存在，但必须明确标记，不能伪装为有证据事实。
- 派生结果不得绑定伪造的原始文档证据，应返回规则和前提链。

### R-006 面向 Agent 的结构化语义上下文查询

当前状态：`部分实现`

新增统一的自然语言语义查询接口，并保留现有 SPARQL 作为高级入口。平台返回上下文，
不调用 LLM 生成最终答案。

建议接口：

- REST：`POST /api/semantic/context:query`
- MCP：`query_semantic_context`

结构化响应至少包含：

- 命中的概念、实例、关系、事实和操作。
- 参数/约束、来源证据、断言类型、可信或缺失状态。
- Graph Set、图修订、来源签名、派生运行版本和过期警告。
- 可供 Agent 继续构造 SPARQL 的 IRI 与推荐查询提示。

验收标准：

- 首版至少支持多语言 lexical 检索、别名和关系邻域扩展。
- 查询必须指定一个或多个授权 Graph Set，不允许默认扫描整个 Dataset。
- 结果可限制资源类型、断言类型、深度和数量。
- 同一请求和同一语义版本产生可重放的排序结果。
- 信息不足时返回缺失项和警告，而不是编造答案。

### R-007 通用操作语义与外部工具绑定

当前状态：`未实现`

平台需要通用表达“某个外部系统能做什么”，但不执行该操作。至少覆盖：

- Operation 名称、语义描述和目标资源类型。
- 输入参数、必填性、类型、枚举、默认值和校验约束。
- 前置条件、执行效果、可能失败、幂等性和风险等级。
- 外部 API/MCP operation 标识、文档来源和版本。
- 凭证引用类型；不得在 RDF 或查询结果中保存/返回明文凭证。

验收标准：

- 通过通用命令或 RDF 编辑可创建和更新 Operation。
- 上下文查询可把“发布工作流”解析到操作、目标资源、参数和前置条件。
- Dify 操作只是测试数据，不产生任何 Dify 专用后端分支。

### R-008 API/MCP 认证、授权与项目隔离

当前状态：`未实现`

验收标准：

- HTTP 和 MCP 使用哈希存储的 API key 或等价服务身份；健康检查可保持公开。
- 首版 scope 至少包含 `read`、`model`、`admin`，并绑定 Project。
- Project、Ontology、Graph Set、Evidence 和查询范围必须进行归属校验。
- SPARQL 必须限制到授权图范围，不能通过 `GRAPH ?g` 绕过项目隔离。
- 编辑审计中的 actor 来自认证主体，不能完全信任请求体自报值。
- 禁止把外部系统明文密钥写入本体、日志或审计 delta。

### R-009 Agent Test 外部化与查询诊断重构

当前状态：`部分实现`

现有 `agent-test` 由平台调用 LLM 生成最终答案，不符合目标边界。将其改为“查询诊断”能力：

- 展示结构化上下文、检索步骤、排序原因、版本和警告。
- 不在平台核心调用聊天模型。
- 外部 Agent 的答案和工具调用结果可作为独立评测记录回传，但不是平台生成。

验收标准：

- 未配置 LLM API key 时平台核心功能不降级。
- 移除英文空格分词依赖，至少正确处理中文和 API 标识符。
- 前端 Agent Test 页面改为 Context Query 调试页。

### R-010 Dify 通用能力端到端验收套件

当前状态：`未实现`

固定一份可版本化的 Dify 文档/OpenAPI 测试资料和不少于 20 个任务，覆盖：

- 产品概念和资源识别。
- 工作流创建所需结构、参数和约束。
- 发布相关前置条件和操作识别。
- 日志查询与失败排查相关知识。
- 自然语言召回、Agent 构造 SPARQL 和跨图组合查询。
- 文档版本变化后的增量更新。

首版建议指标：

- 关键测试知识证据覆盖率不低于 90%。
- Context Query `Recall@5` 不低于 80%。
- 操作及参数约束识别正确率不低于 90%。
- 测试 Dify 环境中的端到端任务成功率不低于 80%。
- 所有失败均能定位到检索、建模、验证、Agent 规划或目标系统调用阶段。

### R-011 当前 API/MCP/配置文档对齐

当前状态：`部分实现`

当前 README 和部分 API/MCP 文档仍描述已删除的旧接口与尚未实际生效的认证配置。

验收标准：

- README 环境变量、认证说明、端口和启动命令与当前代码一致。
- `docs/api.md`、`docs/mcp.md` 只列出真实注册的接口，并说明缺失能力。
- MCP 文档或生成物以运行时 registry 为准，避免维护第二份失真的手工清单。
- CI 校验文档中的关键 endpoint/tool 名称是否仍存在。

## P1 需求说明

### R-101 来源适配器

当轻量证据引用不足以支持自动更新时，再增加完整文档存储以及 HTML 站点、数据库元数据、
OpenAPI URL、Git 仓库路径等来源适配器。适配器只负责采集、解析、规范化、指纹和版本，
不做本体判断，也不改变 R-002 允许 Agent 直接提交文档片段的能力。

### R-102 来源变更与增量更新

在 R-101 建立完整来源快照后，比较来源版本和内容片段哈希，生成新增、修改、删除集合；
结合 R-005 lineage 标记受影响知识，并让外部 Agent 只重建受影响范围。不得把“重新采集”
退化为清空整个本体。

### R-103 持久化混合召回

替换 Fake Search/Vector writer，建立真实持久化索引、Embedding 生成、索引版本和查询服务。
支持 lexical + vector + 图邻域融合，并把来源签名、可见性和过期状态纳入过滤与排序。

### R-104 模块化本体组合

为本体模块声明依赖、版本约束、导入图、语义映射和桥接关系。Graph Set 应能够解析一个
模块集合并报告缺失、冲突或不兼容依赖，而不是只保存人工填写的图 IRI 列表。

### R-105 不可变发布版本

在现有图修订、Graph Set supersedes/history/delta 基础上形成清晰的不可变 release。查询可
选择当前工作集或指定 release，响应必须携带 release/version 标识，且可回滚到旧版本。

### R-106 异步任务框架

投影、推理、规则和大批次写入使用持久任务记录，支持租约、超时、重试、取消、
进度、幂等和服务重启恢复。首版不要求分布式 worker，但接口不能绑定同步 HTTP 生命周期。

### R-107 构建工作台

在现有 Brief、Questions、Modeling 和 Debug 页面之间补齐 Evidence Reference、Build Session、
建模批次和 Agent 最近活动视图。完整来源、解析状态和增量影响仅在 R-101/R-102 实现后加入。
页面展示业务术语，不要求普通用户填写 RDF 图 IRI。

### R-108 查询与质量可观测性

记录查询主体、授权范围、查询类型、Graph Set/source signature、耗时、命中、警告和评测结果；
敏感查询文本支持脱敏。提供 Dify 基准的趋势报告和失败归因。

### R-109 细粒度身份治理

在 R-008 基础上增加用户/服务账号区分、key 轮换和撤销、按 Ontology/Graph Set 的角色、审计
导出和敏感字段策略。单组织版本不实现租户计费。

### R-110 OWL Reasoner 部署

把当前外部 command runner 变成可安装、可健康检查、可报告引擎版本的标准运行方案，并覆盖
超时、资源限制和失败恢复。若 Dify 基准不需要复杂 OWL 推理，本项不得阻塞 P0。

## P2 与明确不在范围

P2 聚焦持续同步和规模化，不应提前阻塞参考闭环：

- R-201：定时同步、Webhook、连接器调度与采集凭证引用。
- R-202：将外部系统真实资源和状态按通用 Source Adapter 同步为实例知识。
- R-203：跨项目可复用本体注册表、依赖解析和兼容性策略。
- R-204：分布式 worker、队列隔离、限流、容量和成本治理。
- R-205：多组织 SaaS、计费和配额明确延后。

以下能力明确不由本体平台承担：

- 托管通用 Agent 对话、规划或大模型运行时。
- 代理执行 Dify 等目标系统的 API/MCP 操作。
- 在平台核心中加入 Dify 专用业务分支。
- 保存外部系统明文凭证。

## 推荐实施顺序

```text
第一批：R-001 -> R-002 -> R-003 -> R-004
第二批：R-005 -> R-006 -> R-007 -> R-009
安全线：R-008 与第一、第二批并行，但必须在外部 Agent 联调前完成
验收线：R-011 立即执行；R-010 在 R-002 完成后建立夹具，随各批次持续扩充
增强线：R-102 -> R-103 -> R-104/R-105 -> R-106/R-107/R-108
```

第一批先让外部 Agent 真正“有证据可留存、有进度可恢复、有变更可安全提交”；第二批让消费
Agent 真正“有结构化上下文可用”；安全线保证这些接口可以被外部 Agent 实际接入；Dify
验收线从一开始持续证明平台没有偏离最终价值。

## 状态更新模板

完成或推进某项需求时，在对应小节追加：

```text
当前状态：进行中 | 已实现 | 阻塞
最后更新：YYYY-MM-DD
实现证据：commit / API / MCP / UI / migration
验证证据：pytest / build / playwright / live acceptance
剩余问题：若无则写“无”
```
