# Ontology Platform v0.3 需求文档

## 版本定位

`v0.3` 的核心目标是让 Ontology Platform 从“人工维护本体和知识图谱的平台”演进为
“可被 Agent 通过统一 Skill 驱动的对话式本体与知识图谱构建平台”。

平台应交付一个可安装的 `ontology-builder` Skill。外部 Agent 使用该 Skill 与用户持续对话，
收集领域信息或接收用户文档，向平台提交本体、类、属性、关系类型、实体和关系的候选提案。
平台负责保存证据、执行确定性校验、支持人工审核，并在满足发布门槛后生成不可变的本体版本。

`v0.3` 不改变既有平台边界：平台不管理生产 Agent 的生命周期、部署或通用工作流编排。
Skill 负责 Agent 侧的对话和步骤编排，平台通过 HTTP API 和语义化 MCP 工具提供受控能力。
`ontology-builder` 必须能够独立安装到外部 Agent 宿主，不依赖平台内置聊天页面运行。

批准、豁免和发布的权威执行方必须是平台治理服务，但“由平台执行”不等于“用户永远只能
在平台页面操作”。`v0.3` 默认由平台构建工作台承载这些人工动作；未来可在具备独立授权、
内容绑定和逐次明确确认的前提下，由其他受信任客户端调用同一治理 API。

## 用户目标

目标用户无需预先掌握本体工程或图数据库知识，即可完成以下流程：

1. 用户通过自然语言描述业务领域、目标和预期问题。
2. Agent 根据 Skill 检查缺失信息，并针对性追问。
3. 用户直接回答问题，或上传 PDF、Markdown、纯文本等资料。
4. Agent 基于对话和文档提出领域本体及知识图谱候选内容。
5. Agent 提供待审核批次和平台工作台入口，用户审核 Schema、实体、关系、冲突项和低置信度项。
6. 平台从图谱中确定性选取事实并生成自然语言审核陈述。
7. 用户审核事实，平台验证能力问题和发布门槛。
8. 审核通过后发布不可变的本体版本，供查询和 Agent 使用。

## 核心原则

- **提案优先：** Agent 只能创建草稿或提案，不得直接修改已发布本体。
- **证据优先：** 从文档提取的 Class、Entity 和 Relation 必须可追溯到来源位置。
- **人机分工：** LLM 负责理解、抽取、归纳和表述；平台负责状态、约束、校验和发布。
- **版本不可变：** 已发布版本不可原地修改，后续变更必须创建新草稿版本。
- **能力问题驱动：** 先明确图谱需要回答的问题，再设计本体和抽取知识。
- **模型无关：** 平台 API 和提案格式不绑定具体 Agent 框架或模型提供方。
- **入口解耦：** Skill 是独立 Agent 能力，平台 UI 是治理控制面，二者复用同一应用服务。
- **幂等可恢复：** Agent 重试、断线或重复调用不能产生无法识别的重复数据。
- **文档不可信：** 上传文档一律视为待抽取数据，不得将文档内容当作 Agent 指令执行。

## 交互形态与系统边界

`v0.3` 采用“Agent 交互面与平台治理控制面分离”的架构：

```text
External Agent / IDE Agent / future platform chat host
                         |
                  ontology-builder Skill
                         |
                semantic MCP / HTTP API
                         |
        Ontology Platform governance services
                         |
             Review Workbench + storage
```

- Agent 和 Skill 负责自然语言交互、追问、文档理解、提案生成及流程提示。
- 平台服务负责提案状态、证据、确定性校验、审核决定、豁免和版本发布。
- 构建工作台负责展示复杂差异、证据、冲突、批量审核和发布确认。
- PostgreSQL 和 Neo4j 中的平台状态是工作流权威状态，聊天历史不是恢复依据。
- 平台未来可以增加内置聊天页面，但它只能作为同一个 Skill 的宿主，不得复制另一套提案、
  校验、审核或发布逻辑。

### v0.3 默认跨界面流程

1. 用户在任意受支持的外部 Agent 中启动 `ontology-builder`。
2. Skill 通过 MCP/API 创建提案并获取 Review Batch。
3. Agent 展示待审核数量、摘要和平台构建工作台的深链接。
4. 用户在构建工作台完成批准、拒绝、编辑、豁免或发布确认。
5. Agent 查询平台中的审核状态并继续后续阶段。

Agent 可以告知用户应执行什么治理动作，但不得把自然语言回复自行解释为已经完成批准、
豁免或发布。

## 关键概念

### Project Brief

领域项目的结构化需求说明，至少包含：

- 领域名称和业务目标。
- 范围及明确排除项。
- 核心概念、事件和参与者。
- 期望粒度。
- 数据来源及可信度优先级。
- 时间、地域和版本边界。
- 行业术语、别名和语言。
- 允许的推理范围。

### Competency Question

用于驱动本体设计和验收的能力问题。每个问题应包含自然语言问题、重要度、状态、可选的
结构化查询定义，以及在当前草稿或已发布版本上的验证结果。

### Proposal

Agent 对正式知识的候选变更。`v0.3` 至少支持：

- `SchemaChangeProposal`
- `EntityProposal`
- `RelationProposal`
- `MergeProposal`
- `ConstraintProposal`

提案统一采用以下生命周期：

```text
proposed -> validating -> validated -> approved/rejected -> applied
```

校验失败的提案保持可编辑状态，不得进入正式草稿。`approved` 只代表人工同意；只有成功
应用到指定草稿版本后才进入 `applied`。

### Review Batch

供人工集中审核的一组 Proposal、Conflict 或 Fact Claim。Review Batch 必须绑定项目、本体版本、
审核类型和稳定标识，提供待审核、已批准、已拒绝及已修改数量，并可生成指向构建工作台准确
范围的深链接。批次状态至少包含 `pending`、`in_review` 和 `completed`。

### Evidence

提案的来源证据。至少包含文档、页码或分块、字符区间、原文片段、内容哈希和来源类型。
来自用户对话的内容也应作为一种证据来源保存。

### Fact Claim

从草稿知识图谱中选出的结构化审核事实。事实必须先由后端根据节点、属性、边或推理路径
确定性生成，再由 LLM 转述为自然语言。自然语言文本不得成为事实的唯一表示。

## 生命周期状态

本体构建工作流至少包含以下状态：

```text
gathering
  -> schema_draft
  -> schema_review
  -> graph_building
  -> graph_review
  -> validated
  -> published
  -> deprecated
```

- 状态前进必须通过服务层动作完成，不允许客户端直接改写状态字段。
- 任一审核阶段均可退回前序草稿阶段，并记录原因。
- `published` 版本不可修改。
- 从已发布版本继续编辑时，平台创建新的草稿版本并记录父版本。
- `deprecated` 版本仍可读取和审计，但不能再作为默认写入目标。

## 分阶段需求

以下阶段按依赖顺序实施。阶段一至阶段六均属于 `v0.3` 核心范围；每个阶段必须通过自身
验收后才能将后续阶段标记为完成。

## 阶段一：构建治理与版本底座

### 目标

建立草稿、提案、证据、审核和发布的统一数据边界。后续所有 Agent 写入必须建立在该底座上。

### 功能需求

- 激活 `OntologyVersion`，支持草稿版本、父版本和不可变发布快照。
- 新增 Project Brief、Competency Question、Proposal、Review Batch、Evidence、Review Decision、
  Validation Run 和 Publication Gate 数据模型。
- 每个 Proposal 必须绑定项目、本体、目标草稿版本、创建来源和幂等键。
- Schema、Entity 和 Relation 的批量提案必须支持原子应用；任一项失败时不得部分写入。
- 保存提案的创建时间、创建者类型、模型标识、提示词或 Skill 版本、审核结果和应用结果。
- 已发布版本上的写请求必须被拒绝。
- 支持从已发布版本创建后继草稿，保留版本谱系。
- 提供版本 Schema 差异及图谱数据统计差异。

### 验收标准

- 可以创建草稿、提交提案、校验、批准、应用并发布版本。
- 被拒绝或校验失败的提案不会修改 PostgreSQL 中的正式 Schema 或 Neo4j 图数据。
- 重复提交同一幂等键不会创建重复提案或重复图数据。
- 已发布版本无法通过 HTTP API、MCP 或仓储层被修改。
- 可以完整查询一次提案从创建到应用的操作记录和证据链。
- 后端测试覆盖状态转换、原子应用、幂等行为和发布版本不可变性。

## 阶段二：需求访谈与能力问题

### 目标

让 Agent 能够通过结构化访谈形成领域边界，并以能力问题约束本体设计。

### 功能需求

- 提供读取和更新 Project Brief 的 API/MCP 能力。
- 后端返回 Project Brief 缺失字段和待澄清项，供 Skill 决定下一轮问题。
- 支持创建、排序、编辑、批准和停用 Competency Question。
- 能力问题可标记为 `draft`、`approved`、`testable`、`passed` 或 `failed`。
- 保存用户回答与 Project Brief 字段、能力问题之间的来源关联。
- Skill 每轮最多提出少量高价值问题，已确认内容不得重复追问。
- 用户可跳过非必要问题；Skill 应明确跳过信息对生成质量的影响。

### 验收标准

- 仅通过对话可以形成可编辑的 Project Brief。
- Skill 能识别范围、核心对象、目标问题或粒度等关键缺失项并继续追问。
- 用户修改早期回答后，相关能力问题可以被标记为需要重新验证。
- 每个已批准能力问题均能追溯到用户回答或项目目标。
- 后端测试覆盖字段完整度计算和能力问题状态转换。

## 阶段三：本体 Schema 候选生成与审核

### 目标

根据 Project Brief、能力问题和证据提出 Class、Property、RelationType 和 Constraint，
经过校验和人工审核后应用到草稿版本。

### 功能需求

- 支持批量提交 Schema Change Proposal。
- 候选 Class 至少包含名称、描述、别名、父类和证据。
- 候选 Property 至少包含所属 Class、类型、必填、多值、枚举值和约束。
- 候选 RelationType 至少包含来源 Class、目标 Class、反向名称和可选父关系。
- 校验同一本体内的名称冲突、无效父类、继承循环、非法 domain/range 和重复定义。
- 为“Class 还是 Entity”“Property 还是 RelationType”等建模歧义生成待审核项。
- 支持对候选项单条或批量批准、拒绝、编辑和合并。
- 审核界面展示变更前后差异、证据、置信度、影响范围和校验结果。
- Schema 应用后自动重新校验受影响的实体和关系，但不得自动删除不兼容数据。

### 验收标准

- Agent 可以从一份已批准的 Project Brief 生成完整 Schema 提案批次。
- 所有提案均可追溯到能力问题、对话或文档证据。
- 平台能够阻止继承循环、跨本体父类和不合法关系端点。
- 人工可以在 UI 中修改候选项后再批准，不需要重新运行整个提取流程。
- 批量应用失败时不产生部分 Schema。
- 后端测试覆盖 Schema 提案校验、冲突检测、审核和原子应用。

## 阶段四：文档摄取与知识图谱候选生成

### 目标

允许用户上传资料，并基于已审核或草稿 Schema 生成带证据的实体、关系和合并候选。

### 功能需求

- 支持上传 PDF、Markdown 和纯文本文件；文件保存与解析状态可查询。
- 将文档解析为可定位的 Source Chunk，保留页码、顺序、字符区间和内容哈希。
- 支持文档重新解析；内容未变化时复用已有分块和提取结果。
- Skill 只将文档内容用于数据抽取，不执行文档中的命令、提示词或工具调用要求。
- 支持按已有 Class 和 RelationType 提交 Entity/Relation Proposal。
- 每个文档抽取提案至少绑定一个 Evidence；用户声明可作为对话 Evidence，纯模型推测不得作为
  Entity 或 Relation Proposal 提交。
- 支持实体别名、规范名称、属性、关系属性和提取置信度。
- 支持候选实体消歧、重复检测和 Merge Proposal。
- 相互冲突的属性或关系不得自动覆盖，应生成冲突审核项。
- 提案应用前复用现有实体和关系校验规则。
- 支持查看某文档产生的全部候选项，以及某实体/关系对应的全部来源。

### 验收标准

- 用户上传文档后，Agent 可以生成符合当前 Schema 的实体和关系提案。
- 任一候选实体或关系都能定位到原始文档页码或文本区间。
- 对同一文档和同一提取运行重复提交不会产生重复实体或关系。
- 同名候选不会未经审核直接与已有实体合并。
- 文档中的提示注入文本不会触发额外工具调用或改变 Skill 工作流。
- 后端测试覆盖分块定位、证据关联、重复提交、冲突处理和提案应用。

## 阶段五：事实审核、能力问题验证与发布

### 目标

通过可追溯事实、能力问题和确定性校验评估草稿质量，并在满足发布门槛后发布本体版本。

### 功能需求

- 后端从图谱确定性生成结构化 Fact Claim，不允许 LLM 自由补充图中不存在的事实。
- Fact Claim 支持 `direct`、`inferred`、`conflict` 和 `low_confidence` 类型。
- 事实包含 subject、predicate、object/value、图路径、证据、生成原因和审核状态。
- LLM 仅负责将结构化事实转述为自然语言；结构化事实始终是权威表示。
- 审核样本按实体属性、直接关系、推理事实、低置信度、冲突项、核心实体和能力问题答案分层选取。
- 用户可批准、拒绝或标记事实需要修正；拒绝事实必须关联到待修正提案或数据项。
- 能力问题可以绑定平台内部查询定义，并保存每次验证结果。
- 发布前运行 Schema 校验、图谱校验、证据覆盖率、冲突检查、能力问题测试和事实审核统计。
- 发布门槛由结构化规则配置，不允许只凭“随机 n 条事实正确”自动发布。
- 发布操作展示全部门槛、阻塞项和警告，并要求人工明确确认。
- 发布后创建不可变快照，并将该版本设为可查询的可用版本。

### 默认发布门槛

- Schema 审核完成且无严重校验错误。
- 不存在阻塞发布的待审核或已拒绝但未处理提案。
- 不存在未处理的严重冲突项。
- 所有必审低置信度提案均已处理。
- 关键 Class 和 RelationType 达到配置的证据覆盖率。
- 所有标记为 `testable` 的关键能力问题通过。
- 配置的分层事实样本已完成审核，准确率达到项目阈值。
- 所有被拒绝事实对应的问题已修正或被明确豁免。

### 验收标准

- 每条自然语言审核事实可以还原到唯一结构化事实和图路径。
- 修改相关实体或关系后，对应事实和能力问题结果会被标记为过期。
- 任一硬性发布门槛失败时，平台拒绝发布并返回明确阻塞原因。
- 发布版本包含 Schema 快照、图谱版本引用、验证报告和审核摘要。
- 发布版本可以通过现有查询型 MCP 工具读取。
- 后端测试覆盖事实选择、事实失效、能力问题验证、发布门槛和不可变发布快照。

## 阶段六：统一 `ontology-builder` Skill 交付

### 目标

交付一个可安装、可评测、可恢复的 Agent Skill，将上述平台能力组织成完整对话式构建流程。

### Skill 组成

- `SKILL.md`：触发条件、工作流、停止条件、安全边界和人工审批要求。
- `references/`：建模准则、访谈字段、提案格式、审核规则和常见歧义处理。
- `scripts/`：平台连接检查、文档上传、批量提案提交和状态轮询等确定性操作。
- `evals/`：至少覆盖纯对话、对话加文档、冲突文档、重复调用和提示注入场景。

Skill 对外作为一个统一能力发布，内部至少实现以下子工作流：

```text
project-intake
competency-question
ontology-discovery
document-ingestion
entity-relation-extraction
entity-resolution
ontology-validation
fact-audit
ontology-publication
```

### 行为要求

- 首次调用先读取当前构建上下文，不得假设项目为空。
- 优先复用已确认信息，只针对阻塞当前阶段的缺失项追问。
- 所有模型输出必须转换为平台定义的结构化提案后再提交。
- Schema 未达到最低可用条件前，不得大规模生成实体和关系。
- Skill 必须先调用校验能力，再提示用户进入审核或发布。
- Skill 不得代表用户批准提案、豁免错误或确认发布。
- Skill 应为待审核批次提供数量、摘要和平台构建工作台深链接，并等待平台状态发生变化。
- 中断后能够根据平台状态继续，不依赖完整聊天历史恢复。
- 平台不可用、提案校验失败或证据不足时，Skill 应说明具体阻塞项。

### 验收标准

- Skill 可按仓库文档安装到至少一个受支持的 Agent 宿主。
- 在一个全新项目中，仅通过对话即可完成 Project Brief、能力问题和 Schema 草稿。
- 加入至少一份文档后，可以生成带证据的实体和关系提案。
- Agent 中断并重新启动后，可以从当前项目阶段继续工作。
- Skill 可在外部 Agent 中完成端到端编排，不依赖平台内置聊天页面。
- Skill 不会直接调用数据库、执行原始 Cypher 或绕过 Proposal 服务。
- 评测用例可以稳定验证追问、提案、校验、审核等待和发布准备流程。

## API 与 MCP 能力

### Agent 可用的语义化 MCP 工具

`v0.3` 应在现有查询工具之外提供以下受控能力，最终命名可在实现时统一：

- `get_build_context`
- `get_project_brief`
- `update_project_brief`
- `list_competency_questions`
- `propose_competency_questions`
- `list_evidence_artifacts`
- `get_evidence_artifact_status`
- `propose_schema_changes`
- `propose_entities`
- `propose_relations`
- `propose_entity_merges`
- `validate_draft`
- `list_review_items`
- `get_review_batch`
- `get_review_workspace_link`
- `get_publication_readiness`

所有写工具必须写入 Proposal 或草稿治理模型，并复用 HTTP 服务层校验。不得暴露原始 SQL、
Cypher 或绕过服务层的通用 CRUD。

### 人工专属动作

以下动作必须由平台治理服务执行并记录。`v0.3` 默认只通过受认证的 HTTP API 和平台构建
工作台提供，不作为 Agent 可自主调用的 MCP 工具：

- 批准或拒绝提案。
- 豁免校验错误或发布门槛。
- 批准实体合并。
- 发布或废弃本体版本。

“人工专属”表示 Agent 无权自主决定，并不表示这些动作永久绑定某个页面。未来如需在聊天或
其他受信任客户端中执行，必须至少满足：

- 平台生成一次性确认单或确认令牌。
- 确认内容绑定具体 Proposal、豁免项或待发布版本的内容哈希。
- 客户端向用户展示完整影响摘要，并获得逐次明确确认。
- 平台验证调用者身份、权限、令牌有效期和内容未发生变化。
- 平台记录确认人、客户端、时间、Skill 版本和最终结果。

未满足上述条件时，用户在聊天中的“同意”“都批准”等自然语言回复不能直接触发治理动作。

## 前端需求

`v0.3` 应新增“构建工作台”，至少包含：

- 当前阶段、完成度、阻塞项和下一步建议。
- Project Brief 编辑器。
- Competency Question 列表及验证状态。
- Evidence Artifact 上传、解析状态和分块预览。
- Schema Proposal 差异审核。
- Entity、Relation、Merge 和 Conflict Proposal 批量审核。
- 原文证据定位和多来源对比。
- Fact Claim 分层审核页面。
- 发布门槛、验证报告和版本发布确认页。
- 可复制或打开的审核批次深链接，允许 Agent 将用户导航到准确的项目、版本和待审核范围。

审核界面必须允许用户修改候选内容后批准，且清楚区分：

- Class 与 Entity。
- Property 与 RelationType。
- 原文直接事实与推理事实。
- 新建实体与合并已有实体。
- 错误、警告和可人工豁免项。

## 数据存储职责

### PostgreSQL

继续作为以下数据的权威来源：

- Project Brief 和 Competency Question。
- 本体 Schema、约束和不可变版本快照。
- Evidence Artifact 元数据、Source Chunk 和 Evidence。
- Extraction Run、Proposal、Review Batch、Review Decision 和 Validation Run。
- Fact Claim 审核记录和 Publication Gate 结果。

### Neo4j

继续作为以下数据的权威来源：

- 草稿或已发布版本关联的实体节点。
- 实体之间的类型化关系。
- 图遍历和事实路径查询。

图节点和关系至少需要保存或可解析得到：

- `ontology_version_id`
- `source_ids`
- `evidence_ids`
- `confidence`
- `extraction_run_id`
- `review_status`

证据正文、审核记录和模型运行详情不在 Neo4j 重复保存，只保存引用。

## 本体表达能力演进

`v0.3` 继续使用当前轻量自定义 Schema 作为内部主模型，不要求将 RDF/OWL/SHACL 改为主存储模型。
为支持跨领域构建，Schema 至少应补充或预留：

- 稳定 URI 和 namespace。
- 多语言 label 和 description。
- Relation domain/range。
- inverse、symmetric、transitive 等关系特征。
- 唯一性、基数和跨实体约束。
- 时间有效区间和带属性关系。
- RDF/OWL/SHACL 导出映射。

`v0.3` P1 可提供 RDF/OWL/SHACL 导出，但完整描述逻辑推理不作为发布阻塞项。

## 非功能要求

### 可追溯性

- 所有 Agent 生成内容可追溯到用户回答、文档证据、模型和 Skill 版本。
- 所有审核和发布决定可查询。
- 图谱变更可以定位到对应 Proposal。

### 可恢复性

- 长文档解析和提取采用可查询状态的任务模型。
- 任务失败可重试，不重复创建已成功的提案。
- Skill 不依赖聊天上下文作为唯一工作状态。

### 可测试性

- 任何 `backend/` 行为变更都必须新增或更新测试。
- 后端完成前必须运行 `cd backend && uv run pytest`。
- Skill 必须提供固定输入和结构化断言的评测用例。
- UI 变更必须运行 `cd frontend && npm run build` 并记录人工浏览器检查。

### 性能基线

- Project Brief、提案列表和发布准备度查询应支持日常交互式使用。
- 文档解析和批量提取允许异步执行，但必须持续报告状态和失败原因。
- 提案列表必须分页，不允许一次加载整个大型图谱的全部候选项。

## 端到端版本验收场景

选择一个此前未预置的业务领域完成以下演示：

1. 创建空项目并启动 `ontology-builder` Skill。
2. 用户通过多轮对话描述目标，Agent 生成 Project Brief 和至少 5 个能力问题。
3. 用户上传至少一份文档。
4. Agent 提交 Class、Property 和 RelationType 提案。
5. Agent 返回 Schema Review Batch 摘要和深链接，用户在构建工作台审核并应用 Schema。
6. Agent 提交带证据的 Entity、Relation 和必要的 Merge Proposal。
7. Agent 查询审核结果；用户通过对应 Review Batch 完成图谱候选审核。
8. 平台生成分层 Fact Claim，用户完成事实审核。
9. 平台执行能力问题和发布门槛验证。
10. 用户明确发布版本 `v1`。
11. 外部 Agent 通过现有 MCP 查询工具检索发布图谱并回答能力问题。
12. 继续修改时，平台创建 `v2` 草稿且 `v1` 保持不可变。

该场景中任一正式知识都必须能追溯到用户声明、文档证据或明确标记的推理路径。

## 建议质量指标

- Schema 提案人工批准率。
- Entity/Relation 提案人工批准率。
- 证据覆盖率。
- 重复实体率和实体合并准确率。
- 严重约束违规数。
- 能力问题通过率。
- 分层事实审核准确率。
- 从空项目到首个可发布版本的人工交互轮数和耗时。
- Skill 中断恢复成功率。

这些指标用于评估和迭代，不应以单一 LLM 置信度替代人工审核或确定性校验。

## P1 能力

- RDF、OWL 和 SHACL 导出。
- 基于现有公共本体的术语对齐和复用建议。
- 可配置的轻量规则推理和推理事实解释。
- 文档增量更新及受影响提案分析。
- 项目级自定义发布门槛模板。
- 不同模型或抽取策略的质量对比。
- 使用同一个 `ontology-builder` Skill 的平台内置聊天宿主。
- 基于一次性确认令牌的受控聊天批准流程。

## 暂不纳入 v0.3

- Agent 自主批准或自主发布本体。
- 平台托管生产 Agent 生命周期或多 Agent 调度。
- 将平台内置聊天页面作为 `ontology-builder` 的唯一或必须交付入口。
- RDF/OWL 作为内部唯一主存储模型。
- 完整 OWL DL 推理和通用复杂规则引擎。
- 自动训练或微调领域大模型。
- 任意网站爬取、扫描件 OCR 和音视频知识抽取。
- 已发布版本之间的全自动图数据迁移。
- 完整用户系统、RBAC、组织租户和生产级密钥管理。
- 无人工参与的持续文档同步和本体自动演进。

## 实施依赖与顺序

必须优先完成阶段一的版本、提案、证据和审核底座，再开放任何 Agent 写入能力。推荐顺序为：

1. 数据模型、迁移、版本状态机和 Proposal 服务。
2. Project Brief、Competency Question 和构建上下文。
3. Schema 提案、校验和审核 UI。
4. 文档摄取、Evidence 和图谱提案。
5. Fact Claim、能力问题验证和发布门槛。
6. 统一 Skill、评测用例和端到端验收。

阶段实现过程中应保持 API handler、MCP tool、service 和 repository 分层。HTTP API 与 MCP
必须复用相同的应用服务，避免出现两套校验或状态转换逻辑。
