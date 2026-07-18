# v1.0 Agent 语义层平台需求清单

## 文档信息

- 文档状态：v1 安全边界已收口，其余未完成项已按 v1.1 方向重新排序
- 当前实现基线：R-008 交付工作区（上一功能基线 `2a1653e`，接口以运行时 registry 核对）
- 实现分支：`agent-semantic-layer-platform`
- 目标用户：单组织、小团队、自托管
- 参考验收场景：Dify 使用指南和 API 文档本体
- 更新日期：2026-07-17

本文件是下一阶段的需求与状态账本。实现任何需求后，必须同步更新其“当前状态”、
验收证据和相关提交，避免需求文档再次变成与代码脱节的历史计划。

## 状态与优先级

状态：

- `已实现`：当前代码已经满足本需求的主要验收标准。
- `部分实现`：已有可复用基础，但目标闭环尚未成立。
- `进行中`：已进入实现，尚未通过全部验收。
- `未实现`：当前没有可交付能力。
- `阻塞`：存在明确外部阻塞，必须记录原因。
- `挂起（Pending）`：需求和已有实现基础保留，但不进入当前交付顺序，也不阻塞 v1 收口；
  仅在 v1.1 实践证明其为建模效果瓶颈或另行确认优先级后恢复。
- `已调整`：原需求不再按当前文档中的独立范围继续交付，后续目标或验证方式已转入其他版本。
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

## v1.1 目标确认后的 v1 收口决定

v1 已经基本建立外部 Agent 安全提交建模结果所需的平台底座。下一阶段的主要风险不再是继续
扩充平台功能，而是外部建模 Agent 能否把真实业务资料整理成有实际价值的本体和知识模型。
因此，v1 只继续完成已经进入开发的安全边界，其余未完成需求不再默认阻塞 v1 收口或 v1.1
启动。

| 分类 | 需求 | 处理决定 | 原因 |
| --- | --- | --- | --- |
| 完成 | R-008 | 保持 P0，状态改为已实现 | HTTP、MCP 与 UI 的基本认证、授权和项目隔离已经通过独立验收。 |
| 挂起 | R-009 | 降为 P1，保留已有实现，不继续投入 | 主要改善消费 Agent 的查询调试体验，不直接解决建模 Agent 的知识理解和建模判断问题。 |
| 调整 | R-010 | 取消独立 v1 P0 交付，目标并入 v1.1 | 原方案预设固定任务数量和硬指标；新的 v1.1 先以实际建模效果为粗粒度目标，再由实践决定验证方式。 |
| 挂起 | R-101 至 R-110 | 保留需求和已有基础，统一 Pending | 都属于来源自动化、查询、组合、发布、任务、工作台、可观测性或治理增强；是否有助于建模效果应由 v1.1 实践验证。 |
| 挂起或延后 | R-201 至 R-205 | R-201 至 R-204 Pending，R-205 继续延后 | 规模化、持续同步和 SaaS 能力不应先于建模 Agent 的业务价值验证。 |

Pending 不表示否定这些能力，也不要求回滚已经存在的代码；它只表示当前不为其继续安排独立
交付。若 v1.1 的真实建模过程明确暴露某项平台能力为主要瓶颈，可以把对应需求恢复并调整范围。

## 当前实现基线

| 能力 | 当前状态 | 代码证据与差距 |
| --- | --- | --- |
| Project / Ontology 基础 CRUD | 已实现 | `backend/app/api/ontologies.py`；创建本体时会初始化默认 RDF 图、Graph Registry 和 Ontology-scoped Graph Set，历史缺口可 repair。 |
| 结构化 Brief 与能力问题 | 已实现 | `backend/app/api/interview.py`、`backend/app/mcp/tools/interview.py`。 |
| RDF Dataset 与 SPARQL | 已实现 | Oxigraph、`RdfStoreRepository`、REST/MCP 只读 SPARQL。 |
| 受治理语义编辑 | 已实现 | Turtle、TriG、JSON-LD、受限 SPARQL Update、编辑审计和图可编辑性。 |
| 业务友好建模命令 | 已实现 | Class、Property、RelationType、Entity、Relation、Mapping、Fact 更新/删除等命令编译器。 |
| Graph Registry / Graph Set | 已实现 | 成员角色、来源签名、图修订、派生结果指针、过期检测、历史和差异。 |
| SHACL、推理和确定性规则 | 部分实现 | 服务和测试齐全；真实 OWL runner 依赖外部命令，执行仍是同步路径。 |
| 事实证据绑定 | 已实现 | Project 级 Evidence Reference、Modeling Item association 和 R-005 statement/derived lineage 已覆盖当前轻量证据闭环。 |
| 轻量证据引用 | 已实现 | 项目级 Evidence Reference、查询、规范化复用以及 Modeling Item 级 Association 已接入 REST/MCP 与 R-004 apply。 |
| 固定语义读模型 | 已实现 | Classes、Entities、Facts、Readiness、History、Delta、Entity Search 等读模型。 |
| 自然语言语义查询 | 已实现 | REST/MCP 已提供统一 Context Query，支持 Project 全局或一个至多个 Ontology 范围、结构化上下文、精简 lineage/Evidence 状态和 scoped SPARQL。 |
| Search / Vector 投影 | 部分实现 | 文档构建器和任务模型已存在，但运行时使用 `FakeSearchWriter` / `FakeVectorWriter`，结果不会持久化。 |
| Agent 查询测试 | 部分实现 / Pending | 当前 `agent-test` 在平台内调用 LLM 生成答案，与目标边界不一致，且中文分词能力不足；R-009 暂不继续投入。 |
| Agent 构建接口 | 已实现 | REST/MCP 已支持 Project 级 Build Session、Checkpoint、Ontology Lease，以及 R-004 带证据 Modeling Batch 的 dry-run、原子/部分 apply、查询和恢复。 |
| 本体组合 | 部分实现 | Graph Set 可组合多个图，Mapping 命令存在；缺少本体依赖、导入版本和桥接关系契约。 |
| 身份认证和项目隔离 | 已实现 | R-008 已交付 hashed API key、UI session、scope 授权、Project 归属校验、MCP 策略和安全事件。 |
| 操作语义模型 | 已实现 | Ontology 级 Operation 已接入 R-004 建模批次、受治理 RDF 编辑、R-005 lineage 与 R-006 Context Query；平台只返回通用工具绑定和凭证需求类型，不执行工具或保存凭证实例。 |
| 异步任务执行 | 未实现 | 投影、推理和规则没有持久任务队列、重试与恢复机制。 |
| Dify 端到端验收 | 已调整 | 当前没有固定资料集、问题集、外部 Agent 执行器和指标报告；原 R-010 独立量化套件不再作为 v1 P0，Dify 建模效果验证转入 v1.1。 |

## 总需求排序

| ID | 需求 | 优先级 | 当前状态 | 投入 | 投入产出比 | 主要依赖 |
| --- | --- | --- | --- | --- | --- | --- |
| R-001 | 新建本体时自动创建默认语义工作区 | P0 | 已实现 | M | 极高 | 无 |
| R-002 | 轻量证据引用与建模结果关联 | P0 | 已实现 | S | 极高 | R-001 |
| R-003 | 外部 Agent 构建会话与 MCP 协议 | P0 | 已实现 | M | 极高 | R-001、R-002 |
| R-004 | 外部 Agent 建模批次的预检、幂等应用与失败恢复 | P0 | 已实现 | M | 极高 | R-001、R-003 |
| R-005 | 统一知识来源与推导链 | P0 | 已实现 | L | 高 | R-002、R-004 |
| R-006 | 面向 Agent 的结构化语义上下文查询 | P0 | 已实现 | L | 极高 | R-001、R-005 |
| R-007 | 通用操作语义与外部工具绑定 | P0 | 已实现 | M | 极高 | R-004、R-005、R-006 |
| R-008 | API/MCP 认证、授权与项目隔离 | P0 | 已实现 | L | 高 | R-001 |
| R-009 | Agent Test 外部化与查询诊断重构 | P1 | 挂起（Pending） | S | 中 | R-006 |
| R-010 | Dify 通用能力端到端验收套件（原方案） | P0 | 已调整 | M | - | 目标并入 v1.1 |
| R-011 | 当前 API/MCP/配置文档对齐 | P0 | 已实现 | S | 高 | R-008 |
| R-101 | HTML、站点、数据库 Schema 等来源适配器 | P1 | 挂起（Pending） | L | 待 v1.1 验证 | R-002 |
| R-102 | 来源变更检测与知识增量更新 | P1 | 挂起（Pending） | L | 待 v1.1 验证 | R-101、R-004、R-005 |
| R-103 | 持久化 Search/Vector 投影与混合召回 | P1 | 挂起（Pending） | L | 待 v1.1 验证 | R-006 |
| R-104 | 模块化本体依赖、导入和桥接 | P1 | 挂起（Pending） | L | 待 v1.1 验证 | R-001、R-006 |
| R-105 | 不可变发布版本与按版本查询 | P1 | 挂起（Pending） | L | 待 v1.1 验证 | R-001、R-005 |
| R-106 | 投影、推理和规则的异步任务框架 | P1 | 挂起（Pending） | L | 待 v1.1 验证 | R-103 |
| R-107 | 面向用户的构建证据与进度工作台 | P1 | 挂起（Pending） | L | 待 v1.1 验证 | R-002、R-003 |
| R-108 | 查询审计、质量评测与可观测性 | P1 | 挂起（Pending） | M | 待 v1.1 验证 | R-006、v1.1 |
| R-109 | 细粒度 RBAC、服务账号和密钥轮换 | P1 | 挂起（Pending） | L | 待 v1.1 验证 | R-008 |
| R-110 | 可部署的 OWL Reasoner 运行方案 | P1 | 挂起（Pending） | M | 待 v1.1 验证 | R-106 |
| R-201 | 定时同步、Webhook 与连接器调度 | P2 | 挂起（Pending） | XL | 低 | R-101、R-102、R-106 |
| R-202 | 外部系统实例资源的通用同步框架 | P2 | 挂起（Pending） | XL | 低 | R-007、R-201 |
| R-203 | 跨项目可复用本体注册表与依赖解析 | P2 | 挂起（Pending） | L | 低 | R-104、R-105 |
| R-204 | 分布式任务执行、限流和容量治理 | P2 | 挂起（Pending） | XL | 低 | R-106 |
| R-205 | 多组织 SaaS 租户、计费与配额 | P2 | 延后 | XL | 低 | R-109、R-204 |

## v1 核心详细需求

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

当前状态：`已实现`

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

R-004 apply 已调用 `authorize_apply(...)`，Modeling Batch、Attempt、Finding、Evidence
Association、fence/recovering 摘要已进入 Build Context 和 Session detail。R-008 此后已补齐
外部接入的认证授权边界，不改变 R-003 会话协议本身已完成。

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

本项只调整构建协议的外部边界。R-006 已明确由调用方选择 Project 全局或一个至多个
Ontology，并由平台解析内部 Graph Set；普通 Agent 不显式指定 Graph Set。

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

完成或取消 Session 前不得存在仍在 `applying` 或 `recovering` 的建模批次；此时终态请求返回
`in_flight_batch` 冲突，并保留 Session 与 Lease 供原 Attempt 收敛。完成不要求所有 Ontology
都达到发布就绪，因为一次 Session 可以只是局部更新；完成摘要必须说明本次实际完成的范围和
未解决事项。

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
  已进入 apply 的 Attempt 由写入栅栏保护到终态；乐观 revision 冲突不会覆盖较新的 Checkpoint
  或终态。
- Agent 可以在 R-004 建模批次中创建或复用项目级 Evidence Reference；平台不负责恢复 Agent
  外部文档的读取位置，也不创建 Session 级伪证据关系。
- 创建重试、Checkpoint 重试、租约重试、断线恢复、过期租约、旧 token、revision 冲突、失败
  批次后继续、执行中批次阻止 Session 完成或取消、完成释放租约和取消释放租约均有服务级测试。

### R-004 外部 Agent 建模批次的预检、幂等应用与失败恢复

当前状态：`已实现`

最后更新：2026-07-15

详细设计：`docs/superpowers/specs/2026-07-15-r004-modeling-batch-design.md`；独立验证使用
`docs/superpowers/plans/2026-07-15-r004-modeling-batch-test-plan.md`。跨 RDF/PostgreSQL 的不确定
写入采用事前持久化计划、Ontology Write Fence 和向前恢复，决策见
`docs/adr/0005-forward-recovery-for-modeling-batches.md`。

实现证据：迁移 `0023_modeling_batches`、`0024_modeling_result_cascade` 和
`0025_backfill_workspaces`；`ModelingBatchService`、
`ModelingCommandHandlerRegistry`、组合 workspace-version 服务；六个 REST 与六个 MCP 能力；
canonical writer fence/claim/向前恢复接线；Ontology 级 Rule/Definition 版本模型；Modeling Item
级 Evidence Association；Build Context 和只读 Debug 诊断。

验证证据：`uv run alembic upgrade head` 已升级真实 PostgreSQL 到
`0025_backfill_workspaces (head)`；`cd backend && uv run pytest`（542 passed，3 skipped）；
PostgreSQL 并发 Batch/Attempt、Lease 和 Evidence upsert 定向测试（3 passed）；前端
`npm run build`、R-004 定向 Playwright（8 passed）及全量 Playwright（34 passed）通过。

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
  聚合为 `applying` 或 `recovering`；成功后终止为 `applied` 或 `partially_applied`。只有当平台
  能证明原 apply 无法安全恢复时才终止为 `failed`；该 Batch 不得再次普通 apply，修正或人工
  处置后的内容必须使用新 Batch。
- 同一 Batch 同一时刻最多只能有一个非终态 apply Attempt。Batch 进入 `applied` 或
  `partially_applied` 后，任何新幂等键的重复 apply 也只返回已有应用结果，不再写入；Batch
  进入 `failed` 后新 apply 返回稳定冲突。部分成功中的失败或被阻断内容以及 failed Batch
  需要修正时，必须提交新 Modeling Batch。
- 存在 `validating`、`applying` 或 `recovering` Attempt 时，同一 Batch 不得启动另一个 apply，
  所属 Build Session 也不得完成。相同幂等请求必须返回或推动原 Attempt 收敛。

#### 客户端标识与平台标识

- `client_batch_id` 由 Agent 生成，在一个 Build Session 内唯一，用于标识一份不可变
  Modeling Batch 内容；不同 Session 可以安全复用相同值，不要求 Agent 维护全局编号。
- idempotency key 由 Agent 为每次提交生成，在一个 Build Session 内唯一，用于幂等定位
  一次 Batch Attempt；dry-run 切换到 apply 或主动发起新的校验尝试时使用新键。
- `client_item_id` 由 Agent 生成，只需在所属 Modeling Batch 内唯一，用于逐项结果、Finding、
  `item_ref`、成功依赖、证据和审计关联。
- `batch_id` 与 `attempt_id` 由平台生成且全局唯一，分别标识持久化 Batch 和 Attempt；它们是
  平台资源标识，不代替客户端幂等键。Class、Entity、Relation 等最终语义资源使用平台分配的
  全局稳定资源 ID 和 IRI。
- REST/MCP 响应必须同时回显相关客户端标识和平台标识，使 Agent 可以使用自己的上下文定位
  结果，也可以在恢复、审计和查询时使用平台资源 ID。

#### 跨存储写入与恢复

- apply 在开始任何语义或证据副作用前，必须先持久化 Attempt 的规范化请求哈希、
  目标 Graph Set 和图修订、来源签名、delta 及其哈希、最终成功项或组以及预期证据变更。
- Attempt 从 `validating` 进入 `applying` 时必须建立 Ontology 写入栅栏并记录已校验的 Lease
  revision。此后即使 Lease 自然到期，其他 Session 也不能在该 Attempt 终态前获取可应用的新
  写权限；原 Lease token 不能用于启动新 Attempt，但已开始的 Attempt 可以完成或进入恢复。
- `applying` 或 `recovering` 写入栅栏存在时，不允许释放或轮换对应 Lease，也不允许完成或取消
  所属 Build Session。Attempt 收敛到终态后平台释放栅栏；无法自动收敛时必须通过受控恢复或
  管理处置解除，不能仅等待 Lease TTL 后让并发写入穿透。
- RDF 与 PostgreSQL 写入结果无法立即确定时，Attempt 进入 `recovering` 而不是直接
  `failed`。平台根据已持久化的写入计划与实际图、审计、证据、修订和来源签名对比，
  安全重试未发生的写入或补齐已发生写入的剩余记录。
- Agent 使用相同 idempotency key 重试时，必须返回或推动原 Attempt 恢复，不创建
  新 Attempt，也不通过重新编译而生成不同资源标识、delta 或证据计划。
- Attempt 必须使用数据库中的短期执行 claim 串行化 apply 与恢复执行。进程崩溃或 claim 超时后，
  相同幂等请求可以在锁定原 Attempt 后接管并进入恢复；未超时 claim、并发重试或普通读请求
  不得并行重放副作用。执行 claim 超时不释放 Ontology 写入栅栏。
- 恢复过程不得通过无条件删除图内容猜测回滚。收敛完成后 Attempt 进入 `applied` 或
  `partially_applied`；只有当平台能证明无法恢复时才进入 `failed`，并保留稳定错误码、
  已观察状态和需要的人工处置提示。
- Build Context 和 Batch 读接口必须显示 `recovering` Attempt、最近恢复结果与是否可安全重试，
  不能让 Agent 通过 Checkpoint 把不确定写入标记为已完成。

#### 同步执行与容量边界

- R-004 首版同步执行命令编译、确定性校验和正式应用；在正常容量范围内，提交接口直接返回
  `validated`、`validation_failed`、`applied` 或 `partially_applied` 等本次 Attempt 最终结果。
- 平台必须提供可配置且有文档说明的单批 Modeling Item 数量、请求体字节数、内联 Evidence
  数量与片段长度上限。超限请求在开始编译和写入前以稳定请求级错误拒绝，并返回实际值与上限，
  不允许静默截断 Item、payload 或 Evidence。
- HTTP 连接中断或写入结果不确定时，已持久化 Attempt 不因客户端离线而创建重复操作；Agent 使用
  相同 idempotency key 重试或读取 Batch 状态。进入 `recovering` 后由恢复流程收敛并通过读接口
  暴露结果，不要求同步请求一直保持连接。
- R-004 不建设通用持久任务队列、调度器或 Worker 框架。投影、推理和规则等通用异步执行能力
  仍由 R-106 负责；后续若将大批次迁移到异步执行，必须复用相同 Batch、Attempt、幂等和状态语义。

#### 查询、恢复与后续建模基础

- R-004 首版提供单一 Batch 提交能力、按 `batch_id` 读取完整 Batch/Item/Attempt、按 Build Session
  分页列出 Batch，以及按 Ontology 跨 Session 分页列出 Batch。Ontology 查询必须支持状态和时间
  过滤，使后续 Agent 能读取其他 Session 的成功、失败与 recovering 历史。
- Project `Build Context` 返回全部 Ontology 的当前工作区摘要、未解决问题以及最近 Batch 和 Session
  摘要；它用于选择工作目标和恢复过程，不返回整个大型语义模型。
- 新增 Ontology 级 `Modeling Context` 读能力，至少返回当前 `workspace_version`、默认工作区状态、
  资源类型计数和分页或语义查询入口、最近已应用 Batch 与 delta 摘要、当前校验/锁定/过期状态。
  REST 与 MCP 使用同一服务和响应语义。
- Agent 开始或继续建模时，必须以 Modeling Context 和当前固定语义读模型为权威基础；历史 Batch
  用于解释“为什么变成现在这样”，Build Checkpoint 只表达旧 Agent 报告的进度，二者都不能通过
  回放或摘要替代当前语义状态。
- Agent 从 Modeling Context 获取 `workspace_version` 并在 apply 中作为预期版本提交。其他 Session
  在此后改写工作区时，apply 返回版本冲突；Agent 必须刷新 Modeling Context 并基于新状态调整，
  不得仅依赖旧 Batch 或 Checkpoint 覆盖当前内容。
- 首版复用现有 Classes、Entities、Facts、History、Delta、Rules 等固定读模型提供详细分页读取；
  R-006 后续可以为同一当前状态补充结构化自然语言语义查询，但不得建立另一套建模基础事实。
- 前端只把 Batch、Attempt、Finding 和 Modeling Context 摘要接入现有只读 Debug 诊断页；R-004
  不新增人工创建或修改批次的业务页面，面向用户的完整构建工作台仍属于 R-107。

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
  由平台 `batch_id`、Ontology、`client_item_id` 和 `command_kind` 确定性生成，使同一
  Modeling Batch 的 dry-run、apply 和网络重试得到同一资源标识和规范化 delta，同时避免
  不同 Session 复用 `client_batch_id` 时生成相同的全局资源标识。
- Modeling Item 还可通过 `depends_on` 声明“当前项只能在指定项成功时应用”。
  `depends_on` 表达成功依赖，不表达严格的逐项执行顺序；平台还要从 `item_ref`
  和命令资源引用中推导隐式成功依赖。
- 平台必须先解析全部资源标识和引用，再针对整个候选状态编译与校验。
  资源之间的循环引用、自引用或领域关系成环不自动构成批次错误；是否违反继承、
  状态流转或其他语义规则，由对应命令和领域校验器判定。

#### 同一语义目标的合并与冲突

- 每个 Modeling Command Handler 必须声明规范化写入集合，使平台可以在正式写入前识别多个
  Item 是否修改同一资源、属性、关系、事实槽位或受控记录。合并和冲突判断不依赖 Items 的数组顺序。
- 修改同一资源的不同且兼容槽位可以合并；完全相同的规范化写入效果只执行一次，并为相关 Item
  返回 `duplicate_effect` warning，但仍分别保留其 Item 状态、理由、证据与审计关联。
- 对同一单值槽位写入不同值、同时更新与删除同一资源、或产生其他不可同时成立的效果时，相关
  Item 返回阻断 `conflicting_item_effects` Finding。R-004 不提供 last-write-wins 或数组末项覆盖规则。
- `apply_atomic` 中任何效果冲突都阻止整批写入；`apply_partial` 中冲突项及其原子依赖组失败或
  blocked，平台对剩余候选子集重新收敛校验后才允许写入。

#### Evidence、建模理由与能力问题

- 每个 Modeling Item 可以分别提供已有 `evidence_reference_ids`、内联 `evidence`、Agent
  `rationale` 和 `competency_question_ids`。三者都关联具体 Item，不提供 Batch 级默认值，
  也不自动从其他 Item 继承。
- Evidence 是外部资料中的文档名和原文片段，继续完整遵守 R-002 的规范化、Project 归属、
  幂等复用和 Evidence Association 规则。`rationale` 是 Agent 的建模解释，不是原文证据，
  不得被平台伪装为 Evidence Reference。
- 能力问题表示一个 Item 服务于哪些业务问题。平台必须验证引用存在、属于当前 Project，且
  没有与目标 Ontology 的显式适用范围冲突；它不替代命令本身的语义校验。
- Evidence、理由和能力问题均可为空。没有 Evidence 时保留无证据状态并返回 warning，允许
  应用；证据格式错误、不存在或跨 Project 时返回阻断 error。
- `dry_run` 只返回将复用或待创建的 Evidence 候选。apply 只为最终 `applied` Item 创建或关联
  Evidence Reference；`failed`、`blocked` 和 `not_applied` Item 的内联 Evidence 不得单独落库。
- 同一 Evidence Reference 支持多个 Modeling Item 时，每个 Item 分别建立 Evidence Association，
  不创建 Batch 级证据关系。查询、审计和 lineage 必须能区分 Evidence、Agent rationale 与
  competency question 三种来源上下文。

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

#### 派生状态与不可变审计

- 成功 apply 必须更新实际图修订和 Graph Set 来源签名，并把受影响的推理结果、Rule Result、
  Search/Vector 投影和其他派生指针标记为 stale；R-004 不在写入请求中同步执行推理、规则或投影重建。
- 推理、规则和投影重建继续使用各自受控执行能力，并在 R-106 接入通用异步任务框架。重建完成前，
  Modeling Context 和查询响应必须暴露 stale 警告，不能把旧派生结果伪装成当前结果。
- 终态 Batch、Attempt、Item 结果、Finding、规范化 delta、证据关联和恢复诊断均为不可变审计事实。
  R-004 不提供 Agent 删除或改写历史记录的接口；修正建模内容通过新 Batch 完成。
- actor 现由 R-008 认证主体强制覆盖，不能信任请求 payload 中自报身份。Lease token、凭证、
  密钥和其他秘密不得进入 Batch 内容哈希、delta、Finding、审计或 Build/Modeling Context。

验收标准：

- 一次批次可包含 schema、entity、relation、fact、mapping 和 rule 变更；Operation 在
  R-007 定义后通过相同 handler 机制接入。
- 单一 REST/MCP 提交能力支持 `dry_run`、`apply_atomic` 和 `apply_partial`，返回
  规范化 delta、SHACL/平台校验结果和逐项错误或状态。
- 同一不可变 Modeling Batch 可保留多次 dry-run 和 apply Attempt 的完整历史；成功应用后
  任何重试都不会重复写入，内容修正使用新 Batch 而不改写已有审计。
- 不可恢复的执行故障将 Attempt 与 Batch 收敛为 `failed`，不会把可能已有副作用的 Batch
  重新开放给普通 apply；`applying` 进程崩溃后可由相同幂等请求通过执行 claim 串行接管。
- 客户端 Batch、Attempt 和 Item 标识分别只要求在 Build Session、Build Session 和 Batch
  范围内唯一；平台 Batch、Attempt 与最终语义资源标识全局唯一，所有响应可双向关联。
- RDF 或 PostgreSQL 写入中断后，相同 Attempt 可根据事前持久化的 delta 和来源状态
  收敛到确定终态，不重复写入、不新建 Attempt，也不伪装成普通校验失败。
- apply 开始后的 Ontology 写入栅栏覆盖 Lease 到期窗口，直到 Attempt 收敛才允许其他 Session
  获得新写权限；并发写入不能利用 TTL 穿透正在执行或恢复的批次。
- 首版在明确容量上限内同步返回批次结果；超限输入在写入前确定性拒绝，恢复中的 Attempt 可通过
  同一幂等请求或读接口继续观察，且不依赖 R-106 的通用异步任务框架。
- Agent 可先读取 Project Build Context，再读取目标 Ontology 的 Modeling Context 和按需语义
  详情，以当前 `workspace_version` 为后续建模基础；Batch 可按 Session 或 Ontology 跨 Session 查询。
- Agent 只提供 Ontology 标识即可混合提交多种建模命令；平台确定性解析默认 Graph Set
  和目标图，请求不接受 Graph Set ID 或 graph IRI 覆盖。
- 每个 Modeling Item 只承载一个严格类型命令，并可以结构化引用已有资源或同批次
  建立项；循环引用可以通过预分配标识和候选状态整体校验安全处理。
- `apply_partial` 将循环成功依赖折叠为原子依赖组，不会因为存在环而直接拒绝，也不会
  部分写入一个未完整的循环组。
- 多个 Item 的兼容写入可确定性合并，重复效果只写一次，矛盾效果不会按数组顺序覆盖；partial
  模式只在移除冲突组并重新校验成功后应用剩余内容。
- 请求级错误、逐项或组错误、批次级候选状态错误使用稳定且可区分的协议；
  警告不阻断应用，Agent 无法通过通用开关跳过确定性校验。
- `apply_partial` 的最终成功子集在实际写入前再次通过全部跨项与 SHACL 校验，
  无法归因的批次级阻断问题不会产生猜测性部分写入。
- apply 使用 idempotency key；网络重试不得重复写入。
- 批次默认原子应用；需要部分应用时必须显式声明并返回逐项状态。
- 每项可独立关联 Evidence Reference、Agent 建模理由或能力问题；三者不相互替代，失败或
  未应用项不会遗留内联 Evidence，且不存在 Batch 级证据自动继承。
- 成功后更新图修订、来源签名、过期状态、不可变编辑审计和 Build Session 进度；推理、规则与
  投影只标记 stale，不在 R-004 apply 中同步重跑。

### R-005 统一知识来源与推导链

当前状态：`已实现`

最后更新：2026-07-15

详细设计：`docs/superpowers/specs/2026-07-15-r005-unified-lineage-design.md`；独立验证使用
`docs/superpowers/plans/2026-07-15-r005-lineage-test-plan.md`。

#### 要解决的问题

现有平台已经分别保存 Evidence Reference、Fact Evidence Binding、Modeling Item、Edit Audit、
Reasoning/Rule Run 和 derived result graph，但这些记录没有形成统一的知识项级查询链。当前
`inspect_semantic_statement_provenance` 只按 subject IRI 查读模型，Evidence 为空、Run 和 Audit
多数为 `null`，不能回答一条具体事实或模型语句由什么产生、引用了什么、依赖哪些前提以及是否
已经被替换。

本需求以带 named graph 和 graph revision 的 Statement Occurrence（语句实例）作为 RDF 知识的
底层 lineage 单元，以 statement ID、资源 IRI 或 Rule IRI 作为业务查询入口。平台统一组合已有
Evidence、Modeling Item、Audit、Run 和 Rule Definition 记录，但保持以下概念独立：

- Evidence Reference：外部 Agent 实际提交的文档名与原文片段，不代表平台验证过完整文档。
- Agent rationale / Competency Question：建模上下文，不是 Evidence。
- Edit Audit：谁或什么在何时、因为什么原因执行了编辑，不是 Evidence。
- Derivation：产生派生语句的 Run、定义版本、输入快照和可用的前提链。

#### 首版交付范围

- 持久化 asserted、OWL inferred、CONSTRUCT、Rule 和 workflow 结果的 Statement Occurrence。
- 将 R-004 applied Modeling Item 和 canonical/direct edit Audit 绑定到其实际产生的语句。
- Platform DSL 在可解析 matched binding 时保存 exact premise chain；SPARQL CONSTRUCT 和当前
  OWL runner 至少返回 coarse Run/input snapshot，不能伪造证明。
- Rule Definition 虽存于 PostgreSQL，也可按 Rule IRI 查询 Modeling Item、Evidence、rationale、
  Competency Question、版本和 Audit。
- 新增 Ontology 级统一 REST/MCP 查询；普通调用方不填写 Graph Set ID 或 graph IRI。
- 默认查询当前结果；可选查询被删除、替换或非当前派生结果的历史 lineage。
- 迁移前无法还原来源的内容仍可查询，但必须返回 `partial` 和稳定 warning。
- 首版不新增 UI；R-006 消费结构化结果，R-107 再提供工作台展示。

#### 验收标准

- 查询任一当前 RDF 模型结构、事实、Rule Definition 或派生结果时，可获取结构化 lineage；
  REST 与 MCP 的状态和作用域一致。
- 带 Evidence 的 R-004 结果可追溯到具体 Modeling Item、Evidence Reference 和 Edit Audit；无
  Evidence 内容允许存在，但明确返回 `evidence_status=missing`。
- rationale、Competency Question、人工 reason 和 Evidence 分字段返回，任何一项都不能伪装成
  另一项。
- Platform DSL 派生结果返回 Rule Definition version、Rule Run 和 exact premise chain；前提缺少
  Evidence 时返回 `dependency_evidence_status=contains_missing`。
- SPARQL CONSTRUCT 和当前 OWL runner 至少返回 Run、引擎/定义版本和输入 revisions，并明确
  `proof_level=coarse`；派生结果不直接绑定伪造的原始文档 Evidence。
- 删除并重新插入相同 quad 产生不同 Statement Occurrence；默认只返回当前结果，历史查询返回
  旧 occurrence、失效 Audit 和生命周期。
- R-004 幂等重试与向前恢复不会重复创建 Statement Occurrence、Origin 或 premise link。
- 跨 Ontology/Project 查询不能泄漏 Evidence excerpt；深度和节点上限可确定性截断递归链。
- Alembic、全量 backend pytest、MCP registry、真实 PostgreSQL/Oxigraph 定向验收以及服务重启
  health 检查全部通过。

#### 实现与验证结果

- 已新增 Statement Occurrence、Origin 和 exact Premise 的 PostgreSQL 持久化及 Alembic `0026`；
  asserted 删除后重插会保留不同 occurrence，R-004 重试和恢复使用确定性标识去重。
- canonical/direct edit、R-004 Modeling Item、OWL reasoning、SPARQL CONSTRUCT、Platform DSL 和
  workflow rule 写入路径均接入统一 recorder；Rule group 会保留每个输出对应的全部 Rule Definition
  版本和 exact premise，不以后一条来源覆盖前一条。
- 已提供 Ontology 作用域 REST `GET /api/ontologies/{ontology_id}/lineage` 和 MCP
  `get_ontology_lineage`；旧 MCP provenance 工具保留兼容并明确标记 deprecated。
- 查询端严格区分 Evidence、rationale、Competency Question、Audit 和 Derivation；派生语句不直接
  绑定 Evidence，并对 asserted Fact Evidence 进行 Graph Set、graph role 和 Ontology 双重校验。
- 独立测试覆盖历史失效 Audit、restricted WHERE、Evidence 隔离、跨 Ontology 防泄漏、Rule group
  多来源和 exact premise；最终结果为专项 `6 passed`、定向 `111 passed, 2 skipped`、backend 全量
  `568 passed, 3 skipped`。
- Alembic current/head 均为 `0026_semantic_statement_lineage`。真实 PostgreSQL/Oxigraph 验收已验证
  R-004 幂等写入、REST/MCP 一致性、Platform DSL exact 推导链及重启后持久化；服务、backend、
  frontend、PostgreSQL 和 Oxigraph 均健康。

### R-006 面向 Agent 的结构化语义上下文查询

当前状态：`已实现`

最后更新：2026-07-16

详细设计：`docs/superpowers/specs/2026-07-16-r006-semantic-context-query-design.md`；独立验证使用
`docs/superpowers/plans/2026-07-16-r006-semantic-context-query-test-plan.md`。

实现证据：REST `POST /api/semantic/context:query` 与 MCP `query_semantic_context` 共用
`SemanticQueryScopeResolver` 和 `SemanticContextQueryService`；`ScopedSparqlQueryService`
为 REST `POST /api/semantic/sparql:query` 与 MCP `semantic_sparql_query` 提供相同的
Project/Ontology 范围、只读校验和结果边界。
首版不新增 Context Query 页面，现有 Semantic Import/Export Debug 仅完成 scoped SPARQL 兼容。

验证证据：独立测试 Round 2 为 `PASS`，backend 全量、frontend build、Playwright、真实
PostgreSQL/Oxigraph 以及服务重启健康检查均通过。

新增统一的自然语言语义查询接口，并保留现有 SPARQL 作为高级入口。平台返回上下文，
不调用 LLM 生成最终答案。

#### 查询范围

每次查询必须限定在一个 Project 内，并由调用方明确选择以下一种范围：

- **项目全局查询**：查询该 Project 下当前可查询的全部 Ontology，用于跨领域理解和发现
  分布在不同 Ontology 中的概念、事实、关系、规则及操作。
- **指定 Ontology 查询**：选择一个或多个 Ontology，聚焦查询与当前问题相关的语义范围。

普通 Agent 使用 Project 和 Ontology 作为业务范围，不读取或传入 Graph Set ID、graph IRI。
平台根据所选 Ontology 解析各自的当前默认语义工作区。查询范围不得跨 Project；范围中存在
不可访问、未就绪或过期的 Ontology 时，平台不能静默改为扫描其他数据。

项目全局查询中部分 Ontology 未就绪或暂不可查询时，可以返回其他 Ontology 的结果，但整个
响应必须标记为部分结果，并列出未纳入的 Ontology 及原因。调用方明确选择一个或多个 Ontology
时，所选范围必须完整可查询，否则拒绝整个请求，不能返回看似完整的部分结果。不属于当前
Project 或调用方无权访问的 Ontology 始终拒绝，不能作为普通缺失项忽略。

首版自然语言召回和 SPARQL 均只查询各 Ontology 的当前语义状态，并在响应中返回实际语义
版本。已删除或已替换内容继续通过历史或 lineage 查询读取；选择不可变发布版本查询属于
R-105，不纳入 R-006 首版。

#### 返回边界

平台返回围绕当前问题组织的**结构化语义上下文**，而不是仅返回关键词命中的资源列表。
上下文应区分：

- 与问题直接相关的主要匹配项；
- 支撑这些匹配项的事实、关系、规则、操作、参数和约束；
- 每项内容的来源、断言或推导状态、适用 Ontology 及版本状态；
- 平台可客观确认的证据缺失、来源或推导链不完整、范围异常、结果截断和过期警告。

平台不根据这些内容生成自然语言结论，也不把可能相关但尚未产生的推导伪装成现有事实。
平台不判断召回结果是否足以回答问题，也不推测尚未建模的知识。
跨多个 Ontology 查询时，每项结果必须保留所属 Ontology；R-006 不负责合并不同 Ontology 的
业务定义，也不负责判断或解决它们之间的业务冲突。

#### 查询表达

首版同时接受关键词、业务短语和完整自然语言问题。Agent 不需要学习平台专用的自然语言
查询语法。平台必须在结果中明确返回识别到的查询主题、关键术语和候选含义；当一个名称或
问题存在多个合理解释时，返回候选项和歧义警告，由 Agent 继续限定范围，不能静默选定其中
一个含义。

自然语言入口只用于通过统一召回流程定位和组织已有语义知识。平台不预先判断问题属于哪种
类型，也不为不同问题类型建立不同处理流程；除空查询或无效范围外，所有查询都进入同一召回
流程。没有召回到相关知识时返回空结果和未命中状态，不能将其解释为“不支持的问题”。

首版重点保证中文、英文以及中英文混合的 API 或业务标识。查询同时匹配已有名称、别名和
业务描述，但平台不负责自动翻译。跨语言命中必须有本体中已记录的对应名称或别名作为依据；
其他语言可以参与普通文本匹配，但首版不承诺专门的语言理解质量。

#### 首版验收场景

首版使用以下场景验证同一召回流程能够返回不同类型的相关知识：

- **查找与定义**：定位概念、实例或资源，并返回其定义和基本语义信息；
- **事实与约束**：查询资源的事实、状态、参数要求和适用约束；
- **关系与邻域**：查询资源之间的直接关系，以及受限深度内与问题相关的上下游语义；
- **来源与状态**：查询内容的来源、证据、断言或推导状态、完整性和过期状态。

R-007 提供 Operation 语义后，R-006 使用同一上下文响应支持操作、参数、前置条件和效果查询，
不建立单独的操作查询入口。复杂统计、任意比较或假设问题同样进入统一召回流程；R-006 可以
返回相关的已有知识，但不负责计算最终答案或在查询时产生新的推导。

#### 上下文展开

默认结果包含主要匹配项、与其直接相关的事实，以及一层关系邻域。Agent 可以明确请求在受限
深度内继续展开，但平台不得无界遍历或因项目全局查询而返回整个语义模型。达到深度或数量
限制时，响应必须说明结果已被截断。

#### 显式过滤

资源类型、断言类型、关系深度和结果数量均为 Agent 可选的显式过滤条件。平台不得根据问题
文本自动切换资源类型或断言类型，也不得为不同过滤组合建立不同的业务查询流程。

未指定资源或断言类型时，统一召回当前的概念、实例、关系、事实、规则及已有 Operation，
包括当前原始断言和当前推导结果。已删除或已被替换的历史内容默认不参与召回；当前仍被引用
但已经过期的推导结果可以返回，但必须携带过期状态。历史内容继续通过相应的历史或 lineage
查询能力按需读取。

#### 召回内容边界

统一召回使用已经进入语义模型的名称、别名、业务描述、稳定标识、关系名称及其关联资源、
事实属性和值，以及规则、Operation、参数和约束的名称与描述。

Evidence Reference 原文、Agent 建模理由、Edit Audit 备注和 Competency Question 不作为普通
语义知识参与召回。它们保持各自的治理含义，并通过 Evidence Reference ID 或 lineage 按需
查询，不能因文本相关而被当成已经确认的语义事实。

#### 结果组织与排序

结构化结果分为两层：**主要匹配**包含与查询文本直接相关的资源或事实；**关联上下文**包含
围绕主要匹配展开的一层事实、关系、约束、规则和操作。两层中的每项内容都必须标明自身类型、
所属 Ontology 和召回原因，不能以无法区分直接命中与邻域扩展的单一列表返回，也不建立复杂的
递归嵌套响应。

结果按与当前问题的相关程度组织：直接匹配的资源优先，其直接事实和关系次之，更外围的关联
内容靠后；在相关程度相当时，当前有效内容优先于已过期内容。缺少证据、来源不完整或仅有
粗粒度推导链的内容仍可返回，但必须保留对应状态和警告，不能因状态较弱而静默隐藏。

主要结果必须携带可供 Agent 理解的召回原因。相同请求在相同语义版本上必须得到稳定、可重放
的排序，不能因非业务因素随机变化。

#### 证据返回边界

结构化语义上下文默认只返回关联的 Evidence Reference ID 和证据状态，不直接返回证据原文。
Agent 需要核查时，再使用 Evidence Reference ID 读取已授权的证据详情。没有关联证据时必须
明确返回缺失状态，不能生成替代性说明。

对于推导结果，响应返回其推导状态和可继续追溯的 lineage 标识，不把上游 Evidence Reference
伪装成该推导结果的直接证据。完整来源与推导过程继续由 R-005 的统一 lineage 查询提供。

#### SPARQL 高级查询

Agent 可以自行生成只读 SPARQL，作为自然语言统一召回之外的精确查询入口。SPARQL 与自然
语言查询使用同一 Project/Ontology 范围模型：调用方明确选择项目全局或一个至多个 Ontology，
平台将其解析为当前逻辑查询范围；普通 Agent 不传入 Graph Set ID 或 graph IRI。

SPARQL 返回标准查询结果，以及实际查询范围、各 Ontology 语义版本、截断和过期状态，不再次
加工为结构化语义上下文或自然语言答案。R-006 定义此功能契约并执行当前 Project/Ontology
图范围；身份认证和细粒度授权属于 R-008，Agent 构造 SPARQL 和跨范围查询的端到端验收属于
R-010。

建议接口：

- REST：`POST /api/semantic/context:query`
- MCP：`query_semantic_context`

R-006 首版不新增面向普通用户的业务查询页面。R-009 将现有 Agent Test 页面改为 Context Query
调试页，并调用 R-006 的同一查询能力展示识别结果、召回过程、排序原因和警告；调试页不得
建立另一套查询语义或生成最终答案。

结构化响应至少包含：

- 主要匹配项，以及与问题相关的概念、实例、关系、事实、规则和操作。
- 参数/约束、Evidence Reference ID、断言类型、证据或来源缺失状态。
- 所属 Ontology、语义版本、来源签名、派生运行版本和过期警告。
- 命中资源的稳定标识，供 Agent 按需执行后续查询；平台不返回下一步操作建议。

验收标准：

- 首版至少支持中文、英文及其混合业务标识的 lexical 检索、别名和关系邻域扩展，不依赖
  自动翻译建立跨语言命中。
- 关键词、业务短语和完整问题均可作为输入；响应返回识别到的主题、关键术语及歧义候选。
- 查找与定义、事实与约束、关系与邻域、来源与状态四类场景均通过同一召回流程验证。
- 查询必须明确选择项目全局或一个至多个授权 Ontology，不允许默认扫描整个 Dataset；平台
  在内部解析对应的默认 Graph Set。
- 项目全局查询允许带明确排除清单的部分结果；显式 Ontology 列表必须完整成功或整体拒绝。
- Agent 生成的只读 SPARQL 使用相同的 Project/Ontology 范围模型，并返回标准查询结果及范围、
  版本、截断和过期状态。
- 自然语言召回和 SPARQL 首版只查询当前语义状态，不接受历史或发布版本选择。
- 结果可限制资源类型、断言类型、深度和数量。
- 未指定类型过滤时召回全部当前知识类型；历史内容默认排除，过期的当前推导结果明确标记。
- Evidence Reference 原文、Agent rationale、Edit Audit 和 Competency Question 不作为普通
  语义知识参与召回。
- 默认返回直接事实和一层关系邻域；扩大范围必须显式请求，截断结果必须带有明确提示。
- 同一请求和同一语义版本产生可重放的排序结果。
- 结果明确区分主要匹配和一层关联上下文，不使用无法区分命中来源的单一平铺列表。
- 主要结果返回召回原因；缺少证据或来源不完整的相关内容仍可见并带有明确状态。
- 证据、来源、推导链、查询范围或结果完整性存在客观缺失时返回对应状态和警告，而不是
  推测未建模知识或编造答案。
- REST 与 MCP 对相同范围和查询使用同一服务与响应语义。

### R-007 通用操作语义与外部工具绑定

当前状态：`已实现`

最后更新：2026-07-16

详细设计：`docs/superpowers/specs/2026-07-16-r007-operation-semantics-design.md`；独立验证使用
`docs/superpowers/plans/2026-07-16-r007-operation-semantics-test-plan.md`，Round 2 `PASS`。

#### 要解决的问题

R-001 至 R-006 已经形成默认语义工作区、证据、可恢复建模批次、统一 lineage 和结构化上下文
查询链，但当前模型只能描述资源、事实、关系和规则，不能稳定表达外部系统提供的可调用能力。
消费 Agent 因而无法从同一语义上下文中获得“发布工作流是什么操作、作用于哪类资源、需要哪些
参数、有什么前置条件和风险、应映射到哪个 API/MCP tool”等结构化事实。

本需求只让平台表达和检索外部能力，不让平台代理执行操作。外部消费 Agent 继续负责规划、取得
目标系统凭证并调用目标 API/MCP；平台不得保存凭证实例或明文秘密。

#### 作用域与权威状态

- Operation 归属一个 Ontology，当前权威状态存于其默认工作区的 `asserted_ontology` 图；目标资源
  类型使用稳定 Class IRI。Project 全局或多 Ontology 组合继续由 R-006 的范围模型处理。
- Operation 至少包含稳定 ID/IRI、名称、别名、语义描述、目标资源类型、参数、前置条件、效果、
  可能失败、幂等性、风险等级、外部工具绑定、凭证需求类型和状态。
- Operation IRI 由平台按 Ontology 内稳定 `operation_id` 确定性生成；创建时不接受自定义 IRI。
  update/delete 可用 ID 或其规范 IRI 定位，两者同时出现时必须指向同一资源。
- 参数包含名称、描述、必填性、值类型、枚举、默认值和有界校验约束。前置条件与效果首版是供
  Agent 消费的结构化声明，不建设表达式执行器，也不在平台内判断某次操作是否可执行。
- 外部工具绑定支持通用 `http_api` 与 `mcp_tool`，记录外部系统标识、operation/tool 标识、接口版本、
  文档来源和文档版本；不得出现 Dify 专用字段、表、路由或服务分支。
- 凭证需求只记录 `reference_type`、名称、描述和是否必需，例如 `api_key`、`oauth2` 或
  `mcp_server_auth`。Operation payload、RDF、Context Query、Batch/Audit/lineage 均不得接收或返回
  credential reference ID、token、secret、password、header value 等凭证实例或明文值。

#### 写入、校验与历史

- R-004 的同一 Modeling Batch 增加 `create_operation`、`update_operation` 和
  `delete_operation` handler；不新增 Operation 专用批次、事务或恢复接口。
- `create_operation` 可与同批次创建的目标 Class 通过结构化 `item_ref` 关联；Operation 继续遵守
  R-004 的 dry-run、确定性 ID、幂等、冲突、partial apply、Evidence 和恢复语义。
- `update_operation` 为 patch：省略字段保持原值，显式提供的参数、条件、效果、失败、绑定或凭证
  需求集合整体替换；空集合表示清空。删除后不参与当前查询，历史由 R-005 lineage/Audit 查询。
- 受治理 RDF 编辑也可创建或更新 Operation，但必须使用同一受控词汇、完整性和秘密字段校验；
  `validate=false` 只能跳过 SHACL，不能跳过 Operation 平台不变量。无法在写入前确定候选结果的
  Operation `DELETE/INSERT WHERE` 必须 fail closed，调用方可改用确定性 RDF delta 或 Modeling Batch。
- 名称、目标资源类型、至少一个工具绑定、幂等性和风险等级为活动 Operation 的必填字段；参数名和
  binding ID 在 Operation 内唯一，枚举/默认值/约束必须与参数值类型一致。
- R-004 Modeling Item、Evidence Reference、rationale、Competency Question、Edit Audit 和每条 RDF
  语句继续通过 R-005 的既有模型追溯，不建立 Operation 专用证据或历史表。
- R-004 在创建 Batch/Item 记录前递归扫描 Operation payload 的 secret-bearing key；命中时以稳定的
  请求级错误拒绝整个提交，不创建 Batch、Attempt、Item、Finding 或 Audit，也不回显字段值。

#### 查询契约

- R-006 的 `POST /api/semantic/context:query` 与 `query_semantic_context` 在同一候选、排序、范围、
  Evidence/lineage 装饰和截断流程中返回 `kind=operation`，不新增 Operation 专用查询入口。
- Operation 的名称、别名、描述、目标资源类型、参数名称/描述、前置条件、效果、失败和工具绑定
  标识均可参与普通 lexical 召回；结果 `data` 返回完整结构化 Operation 当前态。
- Operation 内部 JSON predicate 和 raw literal 不得进入 R-006 的普通 fact/relation 候选或邻域；
  它们只由 `kind=operation` 的受控 serializer 返回。即使显式只查询 `resource_types=["fact"]`，也
  不能借普通事实响应读取 Operation raw JSON。
- Operation 与目标 Class 的语义关系可进入同一一层关联上下文。查询只返回凭证需求类型，永不
  返回凭证实例、秘密或供 Agent 直接使用的认证 header/value。
- 相同范围、查询和语义版本产生稳定结果；未命中返回 R-006 的 `no_match`，不建立操作意图路由。

#### 明确不在首版范围

- 代理执行外部 API/MCP、网络连通性检查、重试、补偿、审批或操作日志采集。
- 凭证保管、凭证引用实例、服务身份和授权；API/MCP 接入安全仍属于 R-008。
- 外部系统真实资源实例同步；该能力属于 R-202。
- 可执行前置条件/效果 DSL、自动工作流规划、UI 编辑器或普通用户操作目录页面。
- Dify 专用模型、代码分支或内置操作包；Dify 只作为 R-010 的测试夹具。

验收标准：

- Modeling Batch 的 create/update/delete Operation 在 `dry_run`、`apply_atomic`、`apply_partial`、
  幂等重试和恢复路径中与现有命令一致，并能关联 Item 级 Evidence 和 lineage。
- 受治理 RDF 编辑可用同一词汇创建/更新合法 Operation；缺少必填字段、目标 Class 不存在、集合键
  冲突、类型/默认值/约束不一致或包含秘密字段时，在改写 RDF 前返回稳定错误。
- 上下文查询可把“发布工作流需要哪些参数和前置条件”解析到 Operation、目标资源 Class、参数、
  前置条件、效果、可能失败、幂等性、风险、通用 API/MCP 绑定及凭证需求类型。
- REST 与 MCP 对同一请求返回相同的 Operation 核心字段、顺序、范围、Evidence/lineage 状态和警告；
  Operation 仍遵守 R-006 的 Project/Ontology 隔离、当前态和有界响应。
- payload、RDF 当前态、Context Query、Batch、Finding、Audit 和 lineage 中不出现测试凭证明文、
  credential reference ID 或 secret-bearing 字段；`validate=false` 不能绕过该不变量。
- 删除或替换的 Operation 当前态不再召回，R-005 仍可查询其历史语句和来源。
- Dify 操作只作为通用模型测试数据，不产生任何 Dify 专用后端分支、API、表或查询流程。

#### 实现与验证结果

- 已新增共享 Operation vocabulary/codec/invariant，使用 `operation-v1` 受控 RDF 当前态、规范 JSON
  literal 和由 `operation_id` 确定性生成的 IRI；没有新增 Postgres Operation 双存储或 migration。
- R-004 已注册 `create_operation`、`update_operation`、`delete_operation`，复用 dry-run、原子/部分
  apply、幂等、Evidence、recovery、revision、stale 与 R-005 Statement Occurrence/Origin 记录。
- Operation secret-bearing key 在 Batch/Item 持久化前拒绝；canonical/direct RDF 即使
  `validate=false` 也执行同一 invariant，无法安全预判的 Operation WHERE 写入 fail closed。
- R-006 在同一 Context Query pipeline 返回结构化 `kind=operation` 和目标 Class context；内部
  Operation JSON predicate 已从普通 resource/fact/relation/neighborhood 投影排除，REST/MCP 一致。
- plan review Round 1 的三项 High 均修订后在 Round 2 `PASS`；独立测试 Round 1 发现的新 Ontology
  缺少物理 named graph 时 HTTP 500，修复后 Round 2 在真实 PostgreSQL/Oxigraph 完成
  create/update/query/lineage/direct edit/restart/delete/include-history、安全、scope 与清理闭环。
- 独立最终验证为 R-007 定向 `115 passed`、全量 backend `646 passed, 3 skipped`，changed-file
  Ruff/format 和 `git diff --check` 通过；临时运行模式已撤销，服务恢复原 `legacy_only` 配置后
  backend/frontend 均为 200。首版未修改 frontend，按共享测试计划不执行 UI suite。

R-007 交付时，R-008 身份认证/授权和 R-010 外部 Agent 端到端验收仍是独立 P0 需求；此后
R-008 已完成，R-010 的目标已转入 v1.1。

### R-008 API/MCP 认证、授权与项目隔离

当前状态：`已实现`

验收标准：

- HTTP 和 MCP 使用哈希存储的 API key 或等价服务身份；健康检查可保持公开。
- 首版 scope 至少包含 `read`、`model`、`admin`，并绑定 Project。
- Project、Ontology、Graph Set、Evidence 和查询范围必须进行归属校验。
- SPARQL 必须限制到授权图范围，不能通过 `GRAPH ?g` 绕过项目隔离。
- 编辑审计中的 actor 来自认证主体，不能完全信任请求体自报值。
- 禁止把外部系统明文密钥写入本体、日志或审计 delta。

#### 要解决的问题

`ApiKeyModel` 与 `api_keys` 表已存在但完全没有被引用，HTTP 与 MCP 路由没有任何
认证依赖。所有 SPARQL/Context Query 的项目隔离目前信任请求体中的 `project_id`，
没有认证绑定。编辑审计的 `actor` 直接来自请求体（如
`backend/app/api/semantic.py` 中 `request.actor`），即由客户端自报。Operation
payload 已有 `reject_operation_secrets` 防护，但本体内容、日志和审计 delta 未覆盖。

本需求在单组织、小团队、自托管的 v1 边界内，引入 API key 认证、UI session 认证、
scope 授权、Project 归属校验、SPARQL 范围强约束、actor 强制覆盖和统一密钥扫描，
使外部 Agent、消费方和 UI 都能在受控范围内读写。

#### v1 身份与认证契约

- **API key 绑定粒度**：每张 key 绑定一个 Project，scope 在 `{read, model, admin}`
  中选一个或多个。`admin` scope 的 key 可不绑 Project（全组织 admin key），可访问
  任意 Project。只有全组织 admin 能创建、列出和删除 Project，以及创建或撤销全组织
  admin key。Project-bound admin 只能管理所绑定 Project 内的 Ontology 和 API key；不能
  查看其他 Project、创建其他 Project，或创建未绑定 Project 的 key。UI bootstrap admin
  视为全组织 admin。
- **明文格式**：`sk_<scope>_<base62(32)>`，例如 `sk_admin_xxxxxxxx...`。明文仅在
  创建时返回一次，服务端只存 `sha256(plaintext)` 哈希；key 本身是高熵随机串，不需要
  慢哈希。复用现有 `api_keys.key_hash` 列。
- **API key 生命周期**：key 创建后 Project 和 scope 不可修改，明文不可再次读取；查询
  只返回名称、Project、scope、创建时间和撤销状态。撤销操作幂等且不可恢复，不提供单独
  的硬删除接口；需要不同权限时创建新 key。删除 Project 前先撤销其全部 key，安全事件
  记录不随 Project 删除。
- **HTTP 认证**：所有非公开路由要求 `Authorization: Bearer <plaintext_key>`，服务端
  按 sha256 反查 `api_keys`。命中 `revoked_at IS NOT NULL` → 401。
- **MCP 认证**：MCP server 进程启动时读 `ONTOLOGY_MCP_API_KEY` 环境变量，整个进程
  内所有 tool call 都认证为该 key 对应的主体。环境变量未设置 → MCP server 拒绝启动，
  不允许默认未认证运行。
- **UI 认证**：前端走 session cookie + login。新增 `POST /api/auth/login`（用户名/
  密码）、`POST /api/auth/logout`、`GET /api/auth/me`。session 使用 `SECRET_KEY`
  签名的 cookie，7 天过期，无服务端 session 表。session 写请求使用 CSRF token 和显式可信
  UI origin allowlist；不能用代理改写后的 Host 与浏览器 Origin 直接比较。
- **Bootstrap**：启动时读 `ONTOLOGY_BOOTSTRAP_ADMIN_USER` / `_PASSWORD`，若 `users`
  表中不存在该用户则创建（密码哈希存储）。可选 `ONTOLOGY_BOOTSTRAP_ADMIN_API_KEY`
  在 `api_keys` 表中幂等创建一张全组织 admin key。环境变量未设置仅打 warning 日志，
  不阻断启动，便于本地与 CI 拉起。
- **本地与测试旁路**：v1 **不提供** `AUTH_DISABLED` 类全局开关。测试通过 fixture
  在 setup 中创建 admin key 并在 client headers 中携带。本地开发同样依赖 bootstrap
  admin 凭据。安全 hard cut 首次重启前必须创建并保留一组非测试运营主体；唯一后缀测试
  user/key 可以清理，但不能因此让部署回到仅 health 可用的无身份状态。
- **用户管理范围**：v1 仅一个 bootstrap admin，不提供用户 CRUD 路由、不提供用户列表
  UI。多人共用同一管理员账号；多用户管理、服务账号、key 轮换 UI 推迟到 R-109。

#### v1 授权与项目隔离契约

- **Scope 到操作的映射**：
  - `read` = 所有 GET、`sparql:query`、`context:query`、export、list、get、Evidence
    查询。
  - `model` = `read` + 本体编辑：`/api/semantic/edits`（TTL/TriG/JSON-LD、受限 SPARQL
    Update）、`/api/modeling-batches/*/apply`、build session、evidence association、
    graph set 成员变更、operation 语义写入。
  - `admin` = `model` + 跨本体管理：Project CRUD、Ontology CRUD、API key CRUD、
    `migrations`、`canonical-mode` 切换、`derived-results:gc`。
- **跨 Project 冲突**：Project-bound key（绑 P1）调用请求体中 `project_id=P2` 的
  端点 → 返回 `403 forbidden_scope` 并写入审计日志。全组织 admin key
  （`project_id=null`）遵循请求体 `project_id`。
- **公开路由**：仅 `/api/health`、`/api/health/postgres`、`/api/health/dependencies` 和
  完成登录所必需的 `POST /api/auth/login` 保持公开。其他所有路由必须认证。
- **管理类路由限制**：API key CRUD、Project CRUD、Ontology CRUD 仅 `admin` scope
  可调。全组织 admin 可管理全部 Project 和 key；Project-bound admin 只能管理自身
  Project 的 Ontology 和同 Project key，不能调用 Project 集合创建/删除或全组织 key 能力。
- **Rule Definition 归属**：新建 Rule Definition 必须绑定 Ontology，并通过
  `SemanticRuleModel` 解析到 Project；list/get/update/delete 按该归属过滤。历史
  `semantic_rule_id=null` 的 legacy definition 仅全组织 admin 可见。执行规则时，Rule Definition
  与目标 Graph Set 必须属于同一 Ontology/Project，不能把 P1 规则用于 P2 图集合。
- **SPARQL 范围**：保留现有 `scoped_sparql_query.inject_dataset_clauses` 的服务端注入
  语义（`FROM` + `FROM NAMED`），客户端 `FROM` / `FROM NAMED` / `SERVICE` 已被拒绝。
  `GRAPH ?g` 在 SPARQL 语义下只能枚举 `FROM NAMED` 注入的图，因此无法绕过项目隔离。
  v1 必须在小规模 probe 中验证 Oxigraph 实际行为符合该语义。

#### v1 审计与密钥防护契约

- **Audit actor 强制覆盖**：所有写操作记录的 `actor` 强制设为认证主体：
  - API key 请求 → `key:<key_name>`
  - UI session 请求 → `user:<username>`

  请求体中的 `actor` 字段被忽略。若客户端填了与认证主体不一致的 `actor`，请求仍然
  以认证主体写入，并在审计中记一条 warning（具体 warning 字段或新增列由设计阶段定）。
- **最小安全事件审计**：新增只追加的持久安全事件，仅记录登录成功/失败、无效或已撤销
  key、跨 Project/scope 越权、API key 创建/撤销和请求体伪造 actor。普通成功读取不记录，
  事件不得保存请求 payload、cookie、密钥或命中的秘密原文；全量查询审计、导出和保留策略
  仍属于 R-108/R-109。
- **统一密钥扫描**：所有文本写入路径走同一扫描器，仅在命中高可信真实秘密值时拒绝，
  返回 HTTP 422 + `secret_in_payload`，且错误和日志不得包含命中原文：
  - 允许 `secret` / `token` / `password` / `apiKey` / `credential` 等凭证术语、字段名、
    凭证需求类型和明确脱敏的占位符。
  - 拒绝平台自身完整 `sk_<scope>_<base62(32)>` key、完整 JWT、AWS access key、非占位
    Bearer token 等高可信值；结构化 credential 字段仅在值非空且不是脱敏占位符时拒绝。
  - 覆盖路径：`/api/semantic/edits`（TTL/TriG/JSON-LD、SPARQL Update）、
    `/api/modeling-batches/*/apply`、`/api/evidence`（excerpt）、operation 语义写入
    （沿用 `reject_operation_secrets`）。
- **日志脱敏**：服务端日志按 key 名拒绝记录：`Authorization`、`api_key`、`password`、
  `api-key`、`cookie`。结构化日志在序列化前过滤这些字段。

#### v1 明确不在范围

下列能力推迟到 R-109 或之后，v1 不实现：

- 用户与服务账号区分、多用户管理 UI。
- API key 轮换、撤销 UI（撤销机制本身已通过 `revoked_at` 字段存在，但没有管理界面）。
- 按 Ontology 或 Graph Set 的细粒度角色。
- 审计导出与敏感字段策略。
- 多组织、SaaS、计费与配额（R-205，延后）。
- 多因素认证。

#### 关键假设与验证

下列假设在设计阶段必须用最小实验或代码核对验证：

1. **Oxigraph 严格执行 `FROM NAMED` 限定 `GRAPH ?g` 范围**。当前
   `scoped_sparql_query.py` 注入 `FROM g FROM NAMED g`，理论上 `GRAPH ?g` 只能枚举
   注入的命名图，但需要最小规模 probe 验证 Oxigraph 行为，防止项目隔离被绕过。
2. **FastMCP 启动时拒绝运行的机制**。`backend/app/mcp/server.py` 当前是无副作用的
   `FastMCP()` 实例化，需要在 `mcp.run()` 前加 `ONTOLOGY_MCP_API_KEY` 校验，并确认
   FastMCP 没有"延迟初始化"导致校验被绕过。
3. **现有 audit 表结构**。`actor` 字段是 TEXT，硬覆盖写入没有问题；但"客户端填了
   不一致值时记 warning"需要找到合适的 warning 字段或新增列，由设计阶段确定。

#### 实现与验收证据（2026-07-17）

- migration `0027_r008_auth` 增加用户与只追加安全事件模型；API key 仅保存哈希，明文只在
  创建时返回，支持不可恢复的幂等撤销。
- HTTP、UI session 与 MCP 统一解析认证主体；55 个 MCP tool 均登记 scope、ownership 和
  mutation 策略，Project-bound 主体不能访问或改变其他 Project 资源。
- Rule Definition 新建时绑定 Ontology，Graph Set、Evidence、Build Session、Modeling Batch、
  RDF dataset 和查询范围均执行 Project 归属校验；未知归属 fail closed。
- 统一秘密扫描、认证 actor 覆盖、CSRF/Origin 校验和最小安全事件审计已接入；前端提供登录、
  登出、401 回登录和 session gate。
- 独立测试 Round 3 为 `PASS`：R-008 定向 `32 passed`，后端全量 `689 passed, 3 skipped`，
  前端 Playwright `33 passed, 3 skipped`，构建、迁移、Ruff/format、真实 Oxigraph、MCP、重启和
  数据清理门槛均通过；前两轮发现的两个 High 已修复并回归。
- 本地部署已配置固定 session secret，并创建 gitignored、目录 `0700`/文件 `0600` 的持久运营
  管理员凭据；最终重启后 UI 登录、`/api/auth/me` 和受保护业务端点均返回 200，匿名业务访问
  返回 401。凭据明文未进入 Git、日志或本文档。

### R-009 Agent Test 外部化与查询诊断重构

当前状态：`挂起（Pending）`

范围调整说明：本需求主要改善消费 Agent 的查询调试和结果展示，不直接提升建模 Agent 对外部
业务知识的理解与建模判断。已有 Context Query 和页面基础保留，但本需求不再阻塞 v1 收口，
也不作为 v1.1 的默认前置；只有 v1.1 实践证明查询诊断是建模效果的主要瓶颈时才恢复。

现有 `agent-test` 由平台调用 LLM 生成最终答案，不符合目标边界。将其改为“查询诊断”能力：

- 展示结构化上下文、检索步骤、排序原因、版本和警告。
- 不在平台核心调用聊天模型。
- 外部 Agent 的答案和工具调用结果可作为独立评测记录回传，但不是平台生成。

验收标准：

- 未配置 LLM API key 时平台核心功能不降级。
- 移除英文空格分词依赖，至少正确处理中文和 API 标识符。
- 前端 Agent Test 页面改为 Context Query 调试页。

### R-010 Dify 通用能力端到端验收套件

当前状态：`已调整`

原需求计划预先建立固定 Dify 资料集、不少于 20 个任务以及证据覆盖率、Recall、操作识别率和
端到端成功率等硬指标。该方案能够验证完整链路，但在尚未充分理解建模 Agent 的主要能力问题
之前，容易把工作重心提前转向评测基础设施和指标达成，而不是直接改善实际建模效果。

因此，本需求不再作为独立 v1 P0 继续交付，也不再以原定任务数量和百分比阈值作为当前版本
门槛。Dify 继续作为代表性业务资料和深入试用场景，但具体建模过程、优化方法和验证方式统一
由 `docs/requirements-v1.1.md` 中的 R1.1-001 承接。后续若实践证明需要固定数据集、自动执行器
或量化指标，可以作为 R1.1-001 的实施方案建设，而不是恢复原需求的全部预设范围。

### R-011 当前 API/MCP/配置文档对齐

当前状态：`已实现`

当前 README 和 API/MCP 文档以运行时注册表与真实认证态为准；历史旧接口或未生效配置说明仅保留在历史交付记录中。

验收标准：

- README 环境变量、认证说明、端口和启动命令与当前代码一致。
- `docs/api.md`、`docs/mcp.md` 只列出真实注册的接口，并说明缺失能力。
- MCP 文档或生成物以运行时 registry 为准，避免维护第二份失真的手工清单。
- CI 校验文档中的关键 endpoint/tool 名称是否仍存在。

实施证据（2026-07-17）：

- `scripts/sync-interface-docs.py` 从 FastAPI OpenAPI 和 FastMCP runtime registry 生成 HTTP/MCP
  marker 区块，提供默认只读 `--check` 与显式 `--write`。
- README、`.env.example`、AGENTS、API/MCP、平台指南、UI 与架构文档已按当前 8001/5173/5434/7878
  启动方式、PostgreSQL + RDF/Oxigraph 存储和真实项目隔离/鉴权态同步。
- `skills/ontology-builder` 已迁移到 Build Session、Evidence Reference、Modeling Batch、Context
  Query 与 lineage；失效的完整文件上传和旧 Proposal/Catalog helper 已移除。
- `.github/workflows/docs-sync.yml` 与 `backend/tests/test_documentation_sync.py` 校验 inventory、配置
  真实性、Skill 结构/eval 和 MCP registry 依赖。
- R-011 的最初交付基于“R-008 尚未实现”进行文档定稿；R-008 后续上线后已进入刷新动作，需保证
  文档与公开/受保护端点鉴权边界一致：仅 `health`、`/api/auth/login`、`/api/auth/logout`、`/api/auth/register`、OpenAPI/docs
  保持公开，其它业务接口与 MCP tool 均按现网 scope/项目隔离与 401 失败策略执行。

验证证据（2026-07-17）：

- plan review Round 3 `PASS`；独立测试 Round 1 的 R-009 状态矛盾为 `FAIL`，修复并增加总表/详细
  条目一致性回归后，Round 2 `PASS`。
- 文档聚焦测试 `10 passed`；全量 backend `656 passed, 3 skipped`；frontend build 与 Playwright
  `34 passed`；Ruff、format、Bash、YAML、JSON、diff、Skill validator/eval/registry 检查通过。
- 隔离新上下文 ontology-builder forward test `PASS`；重启前后 live registry 与生成清单均为
  HTTP `115`、MCP `55`，服务、PostgreSQL/Oxigraph 依赖和 frontend 健康。
- R-011 首轮交付前保留“无认证访问业务接口返回 200”的历史证据；在 R-008 完成后，当前
  运行态回归要求改为无凭证访问受保护业务接口返回 401，并与 docs-sync 门禁保持一致。

## P1 需求说明

本节需求当前统一为 `挂起（Pending）`。已有部分实现和代码基础继续保留，但不再按原顺序主动
建设；恢复任一需求时，应记录它在 v1.1 实际建模过程中暴露的具体问题和预期作用。

### R-101 来源适配器

当前状态：`挂起（Pending）`

当轻量证据引用不足以支持自动更新时，再增加完整文档存储以及 HTML 站点、数据库元数据、
OpenAPI URL、Git 仓库路径等来源适配器。适配器只负责采集、解析、规范化、指纹和版本，
不做本体判断，也不改变 R-002 允许 Agent 直接提交文档片段的能力。

### R-102 来源变更与增量更新

当前状态：`挂起（Pending）`

在 R-101 建立完整来源快照后，比较来源版本和内容片段哈希，生成新增、修改、删除集合；
结合 R-005 lineage 标记受影响知识，并让外部 Agent 只重建受影响范围。不得把“重新采集”
退化为清空整个本体。

### R-103 持久化混合召回

当前状态：`挂起（Pending）`

替换 Fake Search/Vector writer，建立真实持久化索引、Embedding 生成、索引版本和查询服务。
支持 lexical + vector + 图邻域融合，并把来源签名、可见性和过期状态纳入过滤与排序。

### R-104 模块化本体组合

当前状态：`挂起（Pending）`

为本体模块声明依赖、版本约束、导入图、语义映射和桥接关系。Graph Set 应能够解析一个
模块集合并报告缺失、冲突或不兼容依赖，而不是只保存人工填写的图 IRI 列表。

### R-105 不可变发布版本

当前状态：`挂起（Pending）`

在现有图修订、Graph Set supersedes/history/delta 基础上形成清晰的不可变 release。查询可
选择当前工作集或指定 release，响应必须携带 release/version 标识，且可回滚到旧版本。

### R-106 异步任务框架

当前状态：`挂起（Pending）`

投影、推理、规则和大批次写入使用持久任务记录，支持租约、超时、重试、取消、
进度、幂等和服务重启恢复。首版不要求分布式 worker，但接口不能绑定同步 HTTP 生命周期。

### R-107 构建工作台

当前状态：`挂起（Pending）`

在现有 Brief、Questions、Modeling 和 Debug 页面之间补齐 Evidence Reference、Build Session、
建模批次和 Agent 最近活动视图。完整来源、解析状态和增量影响仅在 R-101/R-102 实现后加入。
页面展示业务术语，不要求普通用户填写 RDF 图 IRI。

### R-108 查询与质量可观测性

当前状态：`挂起（Pending）`

记录查询主体、授权范围、查询类型、Graph Set/source signature、耗时、命中、警告和评测结果；
敏感查询文本支持脱敏。提供 Dify 基准的趋势报告和失败归因。

### R-109 细粒度身份治理

当前状态：`挂起（Pending）`

在 R-008 基础上增加用户/服务账号区分、key 轮换和撤销、按 Ontology/Graph Set 的角色、审计
导出和敏感字段策略。单组织版本不实现租户计费。

### R-110 OWL Reasoner 部署

当前状态：`挂起（Pending）`

把当前外部 command runner 变成可安装、可健康检查、可报告引擎版本的标准运行方案，并覆盖
超时、资源限制和失败恢复。若 Dify 基准不需要复杂 OWL 推理，本项不得阻塞 P0。

## P2 与明确不在范围

P2 聚焦持续同步和规模化，不应提前阻塞建模效果验证。R-201 至 R-204 当前均为
`挂起（Pending）`，R-205 继续 `延后`：

- R-201（Pending）：定时同步、Webhook、连接器调度与采集凭证引用。
- R-202（Pending）：将外部系统真实资源和状态按通用 Source Adapter 同步为实例知识。
- R-203（Pending）：跨项目可复用本体注册表、依赖解析和兼容性策略。
- R-204（Pending）：分布式 worker、队列隔离、限流、容量和成本治理。
- R-205（延后）：多组织 SaaS、计费和配额。

以下能力明确不由本体平台承担：

- 托管通用 Agent 对话、规划或大模型运行时。
- 代理执行 Dify 等目标系统的 API/MCP 操作。
- 在平台核心中加入 Dify 专用业务分支。
- 保存外部系统明文凭证。

## 推荐实施顺序

```text
已完成底座：R-001 -> R-002 -> R-003 -> R-004 -> R-005 -> R-006 -> R-007 -> R-008 -> R-011
v1 安全收口：R-008 已完成
下一版本：以 R1.1-001 为总体效果目标，实施 R1.1-002 分阶段、可追溯的建模工作流
范围调整：R-010 原方案并入 v1.1
Pending：R-009、R-101 至 R-110、R-201 至 R-204
延后：R-205
```

当前不再按照原增强线继续堆叠平台能力。R-008 完成后，优先通过 Dify 等实际资料观察并改善
建模 Agent 的表现；只有某项 Pending 能力被实际证明是主要瓶颈时，才恢复对应需求。

## 状态更新模板

完成或推进某项需求时，在对应小节追加：

```text
当前状态：进行中 | 已实现 | 挂起（Pending） | 已调整 | 阻塞
最后更新：YYYY-MM-DD
实现证据：commit / API / MCP / UI / migration
验证证据：pytest / build / playwright / live acceptance
剩余问题：若无则写“无”
```
