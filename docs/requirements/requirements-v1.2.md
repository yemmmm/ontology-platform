# v1.2 消费 Agent 语义查询体验优化需求

## 文档信息

- 文档状态：问题范围已确认，待逐项细化与实现
- 基础版本：`docs/requirements/requirements-v1.0.md`
- 关联版本：`docs/requirements/requirements-v1.1.md`
- 总体目标：降低外部消费 Agent 查询和解释本体知识时对内部 ID、IRI、SPARQL 与平台实现细节的依赖
- 参考验收场景：查询 Dify 合成参考本体中的工作流结构、规则触发条件和推理分类
- 目标用户：通过 REST/MCP 消费平台语义知识的外部 Agent、Agent Skill 开发者和查询调试人员
- 更新日期：2026-07-20

## 背景

v1.0 的 R-006 已提供自然语言 Context Query 和受作用域约束的只读 SPARQL，能够返回当前本体的
结构化语义上下文；R-005、固定语义读模型、规则、推理和 lineage 也已经形成可复用基础。这些
能力使消费 Agent 在已知 Project、Ontology、资源名称、关系和属性 IRI 时，可以准确读取本体
事实。

实际使用仍表明“底层可以查到”不等于“消费 Agent 容易查到”。在 2026-07-18 的 Dify 合成参考
本体验收中，消费 Agent 需要回答以下两组问题：

1. 客服工单、发票对账和合同风险审查分别包含哪些输入、按执行顺序排列的节点和输出；
2. 合同风险审查执行成功后为什么仍需关注，触发规则使用了什么属性值和阈值，最终推理分类
   是什么。

本体中存在回答所需的工作流、输入、节点顺序、输出、运行属性、规则结果和 Class 继承关系，
但召回过程暴露了以下问题：

- 中文业务短语查询对应英文标签时返回 `no_match`，需要调用方先知道英文名称；
- MCP 查询要求 `project_id` 和 `ontology_id`，但消费 Agent 缺少可用的 Project/Ontology 发现入口；
- 回答一个工作流结构问题需要自行组合输入、输出、`hasNode`、`node_order` 和 `node_type`；
- Rules 读模型即使请求完整字段，也只返回规则摘要和当前定义 ID，不能读取条件、阈值和结果断言；
- 规则结果能够把运行分类为 `ResourceIntensiveWorkflowRun`，Class 层次能够继续蕴含
  `AttentionRequiredWorkflowRun`，但当前推理状态、结果图和有效分类的表达不够直观；
- 全量实体读取容易产生过大响应和截断，支持的读模型、`include` 值及继续读取方式不易发现。

为完成上述回答，消费 Agent 最终使用了精确 SPARQL，并以只读 Python 命令访问平台内部 ORM/
服务层来发现 Project/Ontology ID 和读取当前规则正文。数据没有被修改，也没有根据常识补全，
但这种绕行不应成为正常消费路径。v1.2 以消除这些绕行为主要目标。

## 与 v1.0、v1.1 的关系

1. v1.2 建立在 v1.0 的 R-005、R-006、R-008 和现有固定语义读模型、规则、推理能力之上，不
   重新定义平台与外部 Agent 的责任边界。
2. 平台继续只返回结构化语义上下文、查询诊断和可验证的推导信息，不调用通用 LLM 生成最终
   自然语言答案；外部消费 Agent 继续负责对话、规划和回答。
3. v1.1 优化“建模 Agent 如何形成高质量语义知识”，v1.2 优化“消费 Agent 如何发现、查询和
   理解已经进入平台的语义知识”。两者可以同步实施，互不作为前置依赖，也不以对方完成作为
   启动或验收条件。
4. v1.1 的建模实践可以向 v1.2 提供代表性本体和查询问题，v1.2 的消费验收也可以反向暴露模型
   中缺少名称、别名、描述或关系的问题；这种证据互用不构成版本依赖。
5. 本版本承接 R-006 首版之后的使用体验缺口，并覆盖 R-009、R-108 中与查询诊断和可观测性相关
   的部分目标；在具体需求进入实现时，再同步更新 v1.0 对应条目的状态，不因新建本文件自动
   将全部 Pending 需求恢复。
6. Dify 合成本体只作为首个可重复验收场景，平台实现不得加入 Dify 专用、客服专用、发票专用
   或合同专用分支。

## 总体目标交互

```text
消费 Agent 使用项目名称、业务问题或当前会话范围
  -> 平台解析授权 Project / Ontology 候选并返回明确范围
  -> Context Query 定位主要语义资源并说明命中或未命中原因
  -> 面向任务的读模型聚合相关输入、关系、顺序、规则和有效类型
  -> 需要精确验证时，Agent 使用稳定 ID 继续查询 SPARQL、规则定义、Evidence 或 lineage
  -> 平台返回范围、版本、断言来源、推导状态、截断与继续读取信息
  -> 消费 Agent 基于可核查事实生成最终答案
```

消费 Agent 可以继续使用 SPARQL 处理高级问题，但普通业务问题不应要求 Agent 先读取平台代码、
查询内部数据库、猜测读模型名称或手工发现内部 predicate IRI。

## 总需求

| ID | 需求 | 优先级 | 当前状态 | 主要依赖 |
| --- | --- | --- | --- | --- |
| R1.2-001 | 消费 Agent 查询闭环与绕行消除 | P0 | 未实现 | v1.0 R-005、R-006、R-008 |
| R1.2-002 | Project 与 Ontology 的授权发现和范围解析 | P0 | 已实现 | R1.2-001、v1.0 R-008 |
| R1.2-003 | 多语言与语义候选召回及可解释回退 | P0 | 未实现 | R1.2-001、v1.0 R-006 |
| R1.2-004 | 面向任务的聚合语义读模型 | P0 | 未实现 | R1.2-001、v1.0 R-006 |
| R1.2-005 | 规则定义查询与触发解释 | P0 | 未实现 | R1.2-001、v1.0 R-005、R-006 |
| R1.2-006 | 有效语义分类与派生状态一致性 | P0 | 未实现 | R1.2-001、v1.0 R-005、R-006 |
| R1.2-007 | 紧凑响应、能力发现和可继续读取 | P1 | 未实现 | R1.2-001、v1.0 R-006、R-011 |

## R1.2-001 消费 Agent 查询闭环与绕行消除

当前状态：`未实现`

### 需求定位

本需求是 v1.2 的查询闭环和共同验收合同，不新增万能查询、消费编排或自然语言回答接口。
R1.2-002 至 R1.2-006 分别交付闭环所需的具体能力；闭环实际使用的接口同时落实 R1.2-007
要求的最小截断、续读和能力发现能力。只有这些能力组合后通过版本级验收，R1.2-001 才能标记
为已实现；不要求 R1.2-007 对平台全部接口完成 P1 泛化。

### 要解决的问题

当前消费 Agent 可以通过多次 Context Query、读模型和 SPARQL 组合得到准确答案，但完成常见
业务问题仍需要知道内部 ID、英文标签、关系 IRI、属性 IRI、受支持读模型名称和派生图结构。
当外部接口缺少某项信息时，Agent 还可能绕过 REST/MCP，直接访问数据库或后端服务层。

### 目标行为

建立一个只依赖受支持 REST/MCP 的完整消费路径。Agent 从授权业务范围和自然语言问题出发，
能够发现相关本体、定位资源、读取常见结构、解释规则与推导，并在需要时沿稳定 ID 继续精确
查询。平台应区分“本体没有该信息”“召回没有命中”“结果被过滤或截断”“派生结果未物化”和
“调用方需要进一步限定范围”，避免把接口限制误报成知识不存在。

- 查询必须使用调用方显式指定或会话显式配置的 Project/Ontology 范围。两者均不存在时返回
  `scope_required`、当前身份可访问的 Project 候选和后续发现入口；不得扫描全部可访问 Project，
  也不得因候选唯一而静默选中。
- 闭环只查询当前语义状态，并返回实际语义版本或 revision。lineage 可以追溯当前事实的来源和
  历史变化，但调用方选择历史或不可变发布版本不属于本需求。查询期间版本变化时必须要求重新
  读取或明确标记变化，不能把不同版本拼成一次一致结果。
- 各接口保留简单、领域相关的状态结构。本需求不定义跨接口统一诊断对象或公共字段；只有确实
  可以继续查询时，相关接口才返回必要续读参数。
- 平台返回可核查的结构化事实和调用状态；外部消费 Agent 负责组合调用并生成最终自然语言答案。

### 验收标准

- 本文件的两个参考问题能够完全通过公开 REST/MCP 回答，不读取平台数据库、ORM、内部服务或
  源代码，不猜测内部 IRI。
- 每个答案都能说明实际 Project/Ontology 范围、语义版本、主要匹配、关联事实和断言来源。
- 未命中、歧义、部分结果、截断、派生过期或未物化由对应公开接口明确区分；仅在可继续查询时
  提供后续入口。正常成功响应不为满足本需求增加额外诊断层级。
- 闭环涉及的截断结果具有稳定续读方式，所需参数、字段和限制可通过公开能力发现，不要求
  R1.2-007 的全部 P1 泛化能力先完成。
- REST 与 MCP 对相同身份、范围和业务参数返回一致的核心事实、排序、语义版本、领域状态、权限
  和范围判断；HTTP 状态/响应包装与 MCP 工具错误或续读形式不要求逐字段相同。
- 最终 PASS 以固定事实断言和公开接口调用轨迹为准，不评价外部 Agent 的自然语言文案质量；可
  保留真实消费 Agent 演示作为易用性证据，但不能代替确定性验收。

## R1.2-002 Project 与 Ontology 的授权发现和范围解析

当前状态：`已实现`

实现结果（2026-07-19）：共享 `AuthorizedScopeDiscoveryService` 和
`OntologyQueryReadinessEvaluator` 已接入 REST `GET /api/semantic/scopes:discover`、MCP
`discover_semantic_scopes` 与现有 R-006 范围解析；授权过滤、稳定游标、metadata 筛选、
`complete/partial/unavailable`、archived/workspace readiness 和派生警告已有专项回归。共享
测试计划保留 Round 1 High 缺陷及修复，并在 Round 2 独立 PASS；完整回归、真实 REST/MCP、
Context/SPARQL 闭环、systemd 重启和清理均通过。

### 需求定位

本需求提供一个独立于 Context Query 和 scoped SPARQL 的授权范围发现能力。外部消费 Agent/Skill
在一次新消费会话的首轮固定调用该能力，先了解当前身份可访问的 Project/Ontology，再显式选择
范围并调用现有语义查询接口。该首轮顺序属于外部消费协议；服务端不记录“是否已经发现过”，
已经持有明确、有效范围的客户端仍可直接查询，每次请求继续重新执行授权和范围校验。

### 要解决的问题

Context Query 和 scoped SPARQL 需要明确 `project_id` 及范围模式；Ontology 范围还需要
`ontology_id`。当前消费 Agent 缺少只读发现能力，只知道项目或本体名称时无法建立合法请求，
容易转而读取内部数据库或复用可能过期的历史 ID。

### 目标行为

为已认证消费 Agent 提供受 R-008 约束的独立 REST/MCP 范围发现能力。无筛选时，通过稳定游标
分页返回当前身份有权访问的完整 Project/Ontology 目录；允许使用该发现能力自己的可选元数据
`query` 和 `queryable` 条件收窄结果，但不得把范围发现混入语义 Context Query，也不得搜索 RDF
Dataset 中的 Class、Entity、Relation、规则或业务事实。

发现结果只包含消费查询范围和就绪性信息，不包含 Build Session、建模批次、进度、阻塞项或未决
事项。每个 Project 至少返回稳定 ID、名称、描述和聚合查询状态；每个 Ontology 至少返回稳定 ID、
所属 Project、名称、描述、业务 `status`、技术 `queryable`、当前 `workspace_version`、不可用原因
和必要的派生状态警告。结果应直接给出构造 R-006 请求所需的 `project_id`、`scope_mode` 和
`ontology_ids`，不暴露或要求调用方读取内部 Graph Set。

#### 查询就绪性

- Project 聚合状态为 `complete`、`partial` 或 `unavailable`。全部 Ontology 可查询时为
  `complete`；至少一个可查询时为 `partial`，并列出被排除 Ontology 及原因；没有可查询
  Ontology 时为 `unavailable`。
- `partial` Project 可以执行 Project 范围查询，但只覆盖就绪 Ontology；显式选择未就绪
  Ontology 时返回 `scope_not_ready`，不得静默扩大或切换范围。
- `draft`、`active` Ontology 在默认语义工作空间完整时均可查询；`archived` Ontology 仍可发现，
  但返回 `queryable=false`、原因 `ontology_archived`，并从 Project 范围查询中排除。
- 任意业务状态下，默认语义工作空间缺失或损坏均返回 `queryable=false`、原因
  `workspace_not_ready`。业务 `status` 与技术 `queryable` 必须分开返回。
- Reasoning/Rule 结果缺失、过期或未物化只返回简要警告，不使仍可读取权威工作空间的 Ontology
  变为不可查询；完整派生诊断由具体查询接口和 R1.2-006 负责。
- Project 不新增聚合 `scope_version`；各 Ontology 返回已有 `workspace_version`，后续语义查询
  重新解析当前范围并返回实际使用的版本。

#### 元数据筛选、候选和分页

- 稳定 ID 精确匹配；Project/Ontology 名称使用去除首尾空白、忽略大小写的包含匹配。首版不搜索
  描述，不做拼写纠正、翻译、同义词、向量或模糊匹配，这些能力不替代 R1.2-003。
- Project 与 Ontology 同时命中时均保留，并返回资源类型和 `matched_on`；重名候选全部返回，
  不按候选数量或相似度静默选中。
- 无 `query` 时分页返回完整授权目录；命中 Project 时返回该 Project 及其全部授权 Ontology；
  只命中 Ontology 时返回必要的父 Project 元数据和命中的 Ontology 候选。
- `queryable` 过滤作用于 Ontology；过滤后没有匹配 Ontology 的 Project 不保留。显式筛选不可查询
  项时返回不可用原因；无匹配是成功空集合，不是接口错误。
- 分页使用稳定排序和游标，返回 `has_more`、后续游标和每页 `generated_at`。首版不建立目录快照
  或目录 revision；分页期间目录变化时不保证所有页面来自同一时刻，调用方选定范围后的实际查询
  必须重新校验授权、状态和 Ontology `workspace_version`，失败时重新执行范围发现。

#### 授权与失败关闭

- 发现结果只能包含当前身份有权访问的 Project/Ontology，不返回无权资源、遮蔽占位符或相关数量。
- 未认证保持 `401 invalid_authentication`；显式访问无权 Project 保持 R-008 的
  `403 forbidden_scope`。对不能安全暴露归属的 Ontology，统一按 `404 scope_not_found` 处理，
  不要求调用方区分“资源不存在”和“存在但无权”，避免资源枚举。
- 允许会话或客户端配置显式固定默认 Project/Ontology，但平台不得在没有可验证范围的情况下
  默认扫描整个 Dataset，也不得因为授权候选唯一而替调用方静默选中。

### 明确不在范围

- 不查询本体内部语义资源，不提供多语言或语义候选召回。
- 不返回 Build Context、建模进度或未决工作。
- 不选择历史/不可变发布版本，不新增 Project 聚合语义版本或目录快照。
- 不强制服务端保存首轮发现调用状态，不替外部 Agent 选择范围或生成最终答案。

### 验收标准

- 新消费会话能够先通过独立公开 REST/MCP 分页读取完整授权目录，再显式选择 Project/Ontology
  调用 R-006；服务端不要求已持有有效 ID 的客户端证明执行过首轮发现。
- 只知道 Project 或 Ontology 名称的 Agent 能通过确定性元数据筛选获得后续查询所需稳定 ID；
  重名返回全部授权候选，无匹配返回成功空集合，不静默选定。
- 发现结果区分 Ontology 业务状态、工作空间就绪性、派生警告和 Project 的
  `complete`/`partial`/`unavailable` 状态；`partial` Project 和明确未就绪 Ontology 的后续行为
  符合本需求约定。
- 发现结果可直接构造 Context Query 和 scoped SPARQL 的 `project_id`、`scope_mode`、
  `ontology_ids`，包含各 Ontology 实际 `workspace_version`，且不需要读取内部 Graph Set。
- 分页具有稳定游标和明确续读信息；目录在分页期间变化时，后续查询会重新校验范围，不把发现时
  的状态当成授权或版本锁。
- REST 与 MCP 对相同身份、筛选和分页条件返回一致的授权候选、排序、状态、版本和不可用原因。
- 未认证、显式 Project 越权和不透明 Ontology 查找保持 R-008 的失败关闭与防枚举语义；无权资源
  不出现在候选、数量或错误详情中。

## R1.2-003 多语言与语义候选召回及可解释回退

当前状态：`未实现`

### 需求定位

本需求在调用方已经通过 R1.2-002 建立明确授权范围后，为 R-006 Context Query 及同一共享检索
模块上的 Entity/Class 搜索增加多语言混合召回。Project/Ontology 目录继续使用 R1.2-002 已确认的
稳定 ID 和名称确定性匹配，不在本需求中改为模糊、翻译或向量发现。

本需求交付 v1.0 R-103“持久化混合召回”中消费 Agent 当前必需的子集：真实持久化索引、Embedding
生成、词面与向量融合、版本/范围/过期过滤和可解释降级。R-103 的全平台泛化状态不因本需求进入
设计而自动改变。

### 要解决的问题

查询“客服工单”“发票对账”“合同风险审查”时，当前 Context Query 对本体中的对应英文工作流
返回 `no_match`。调用方只有先知道英文标签，才能进入后续结构查询。这使自然语言入口在跨语言
业务问题上产生假阴性，也无法判断问题是知识缺失还是词面没有对齐。

### 目标行为

在 R-006 的确定性范围和结果边界内建立默认混合召回。每次查询同时执行现有确定性词面匹配和
受相同 Ontology、当前工作空间版本及授权约束的向量召回，再用稳定规则融合候选。向量索引是由
当前 RDF Dataset 和活动 Rule 元数据生成的可重建投影，不是新的语义事实源。

#### 召回范围与索引内容

- 共享模块覆盖 Class、Entity、Relation/Property、Rule 和 Operation。Context Query、现有 Entity
  搜索和 Class 搜索默认使用 `hybrid`，同时保留显式 `lexical` 诊断模式。
- 索引文本只包含带语言信息的 `label`、`altLabel`、描述、IRI 本地名、类型名称，以及显式指向
  该资源的 Mapping 术语。不得索引任意业务事实值、Evidence 原文、审计内容、秘密或用户查询
  文本。
- 本体已有 label、altLabel 或 Mapping 时，结果返回具体谓词、值和语言等依据；标识符拆分支持
  NFKC、casefold、CamelCase、下划线、连字符和稳定 IRI 本地名。
- 只有语义相似性时标记为 `semantic_candidate`，返回模型/投影版本下的相似度和候选等级，不
  创建 altLabel、Mapping、关系或事实，也不伪装成已确认等价。
- 首版使用 PostgreSQL + pgvector 持久化 Ontology 内部检索投影，不引入独立向量数据库或 rerank
  模型。更换模型、维度、文档模板、阈值或融合规则必须创建新的检索投影版本并重新验收。

#### 排序、歧义与返回合同

- 精确 label、altLabel、Mapping 和稳定标识符命中属于显式依据，优先于仅相似候选；其他词面与
  向量分数使用版本化规则融合。最终 tie-breaker 保持 Ontology 顺序、资源类型、规范化 label 和
  稳定 ID，结果可重放。
- v1 `semantic-retrieval-v1` 在当前 `embedding-3`、1024 维文档合同下使用 cosine 最低候选阈值
  `0.45` 和歧义分差 `0.03`。这些值只能随新的投影版本变更，不能运行时静默漂移。
- 没有显式唯一依据且多个候选处于歧义分差内时返回全部候选，保留 Ontology、稳定 ID、语义类型、
  匹配方法和各自得分，由消费 Agent 或用户确认。
- 保留 R-006 `result_status=matched|no_match` 兼容性；新增召回摘要区分
  `exact|candidate|ambiguous|no_match` 及 `complete|degraded`，每个 item 的 match 信息区分词面
  分数、向量相似度、候选等级和依据。

#### 版本、同步与降级

- 每条索引记录和 manifest 绑定 Ontology、工作空间版本、source signature、Embedding 配置哈希和
  投影版本；Rule 资源还绑定由活动 Rule 和当前 Definition 可索引内容生成的 rule-set signature。
  查询只读取与本次实际范围和签名完全一致且 `current` 的索引，禁止使用旧索引冒充当前结果或
  跨授权 Ontology 召回。
- v1 在授权 Ontology、版本、签名和资源类型过滤后执行 pgvector exact cosine scan，不使用可能因
  ANN post-filter 产生漏召回的 HNSW/IVFFlat。查询超时只能标记 degraded，不能产生完整 no-match；
  近似索引需以后续投影版本和 exact parity 验收另行引入。
- 影响当前语义资源的写入提交后，同一请求同步重建受影响 Ontology 索引并等待结果。RDF/Rule
  权威事实优先提交；Embedding 或 pgvector 失败不能伪造跨存储回滚，写响应必须说明
  `write_applied` 与 `index_failed/stale`，并允许幂等重建。
- 新索引全部写完且再次确认工作空间版本未变化后才能原子提升为 `current`。并发变化、构建失败或
  返回维度/数量非法时不得提升；旧分区可以保留用于恢复，但不能参与当前查询。
- Rule create/PATCH/DELETE 必须在同一 PostgreSQL 事务中修改 Rule 和将受影响检索 manifest 标记
  stale，提交后才同步重建。即使进程在提交后、重建前退出，查询时的 rule-set signature 校验也
  必须拒绝旧 Rule 文档。
- 索引缺失、未回填、过期、配置不匹配或 provider 不可用时，查询继续返回可用词面结果，并在
  Ontology 粒度返回降级状态。若词面也无命中，仍使用 `result_status=no_match`，但召回摘要必须
  表明结果不完整，不能把降级误报为已完整证明知识不存在。
- 数据库迁移只建立扩展和表结构，不在迁移或服务启动时调用外部模型。既有 Ontology 通过显式、
  可重试的 backfill 建立首个 current 索引；完成前按上述规则降级。

### 明确不在范围

- 不改变 R1.2-002 Project/Ontology 目录发现和授权失败语义。
- 不把向量相似度写回本体或生成翻译、别名、Mapping、关系、事实和最终自然语言答案。
- 不索引任意事实/Evidence/审计文本，不记录查询正文，不在首版提供 rerank 模型。
- 不新增独立万能语义搜索接口；REST、MCP 和现有 read model 复用同一服务。

### 验收标准

- 三个中文业务名称能够召回对应英文工作流候选，并明确说明跨语言命中依据或候选性质。
- 中英文混合名称、API 标识符、下划线/连字符及常见命名变体具有稳定、可重放的匹配结果。
- 相似但不同的工作流不会被静默合并；歧义候选保留各自 Ontology、稳定 ID 和匹配原因。
- 本体确实没有相关知识时仍返回未命中，不由平台生成不存在的资源、关系或事实。
- 检索索引缺失、未构建或过期时明确降级到可用路径，并返回降级状态。
- Context Query、Entity 和 Class 搜索对相同范围、查询和类型过滤使用同一候选依据、阈值和稳定
  排序；REST/MCP 的核心候选、版本、歧义及降级判断一致。
- 查询和索引构建始终先施加授权 Ontology、当前工作空间版本和资源类型过滤；无权资源不出现在
  候选、数量、相似度或索引状态中。
- 语义写入后索引成功时返回同一工作空间版本的 current 结果；索引失败时事实保持可读，响应明确
  写入已应用及索引失败，重建成功前只走可用降级路径。

## R1.2-004 面向任务的聚合语义读模型

当前状态：`未实现`

### 要解决的问题

工作流定义已经通过关系和属性完整建模，但消费 Agent 为回答“输入、按顺序排列的节点和输出”
仍需自行发现 `hasInput`、`hasNode`、`node_order`、`node_type` 和 `hasOutput`，再执行多次 SPARQL
并在客户端组装。类似问题还可能涉及 Operation 参数、状态路径、运行事件和依赖拓扑。

### 目标行为

在通用语义事实之上提供面向高频任务的聚合读模型，首个模型为 `workflow-detail` 或等价能力，
至少返回：

- WorkflowDefinition 的稳定 ID、名称、来源和所属 Ontology；
- 输入名称、类型、默认值，以及本体实际存在的其他约束；
- 节点名称、类型和显式顺序；有分支、循环、并行或依赖关系时保留真实拓扑，不能强行线性化；
- 输出 key 及本体实际存在的类型或约束；
- 形成聚合结果所依据的 relation/property 稳定标识和版本。

聚合读模型是当前本体事实的结构化投影，不建立第二份业务真相；本体中缺失的 required、类型、
顺序或其他字段必须明确为空或缺失，不能使用默认常识补全。

### 验收标准

- 一个公开调用返回三个参考工作流各自的输入、节点和输出，节点按显式 `node_order` 稳定排序。
- 对线性工作流返回可直接消费的顺序；对非线性工作流返回节点和边，不制造不存在的总顺序。
- `ticket_text`、`customer_tier`、`invoice_document`、`vendor_id`、`contract_text`、`jurisdiction`
  及三个输出 key 与本体当前事实一致。
- 本体未提供 required 或输出类型时，响应明确标记缺失，消费 Agent 无需通过异常响应推断。
- 聚合结果可以沿稳定 ID 继续查询原始语义事实、Evidence 和 lineage。

## R1.2-005 规则定义查询与触发解释

当前状态：`未实现`

### 要解决的问题

Rules 读模型当前返回规则名称、状态、版本和当前定义 ID，但不返回活动规则正文。消费 Agent
可以看到“Resource-intensive synthetic workflow runs”存在，却无法通过公开 MCP 确认触发属性、
比较符号、阈值和结果断言，只能读取内部规则定义服务。

### 目标行为

提供 Ontology 作用域内的规则详情和针对具体资源的触发解释：

- 返回当前活动定义、语言、版本、输入角色、规范化条件、阈值、结果断言、优先级和解释文本；
- 对具体资源区分“满足”“不满足”“缺少属性”“规则未运行”和“结果已过期”；
- 返回参与匹配的实际属性值、比较操作、阈值、绑定和产生的 statement/lineage 标识；
- 规则使用 Class、RelationType 或 Property 时，同时返回可读名称和稳定 IRI；
- 不暴露内部执行细节、秘密或不适合消费 Agent 的隐藏推理。

### 验收标准

- 公开 REST/MCP 能读取活动规则 `Resource-intensive synthetic workflow runs` 的当前定义。
- 对合同审查运行返回 `total_tokens=128000`、比较条件 `>= 50000` 和直接结果类型
  `ResourceIntensiveWorkflowRun`。
- 解释明确指出 `status=succeeded` 不属于该规则条件，因此执行成功不阻止资源关注规则触发。
- 阈值边界至少验证 `49999` 不触发、`50000` 触发，整数比较语义稳定。
- 规则未执行、定义已替换、结果过期和 lineage 不完整具有明确状态，不能展示为当前已触发。

## R1.2-006 有效语义分类与派生状态一致性

当前状态：`未实现`

### 要解决的问题

合同运行在数据图中断言为 `WorkflowRun`，在规则结果图中派生为
`ResourceIntensiveWorkflowRun`；Ontology 又声明该 Class 是 `AttentionRequiredWorkflowRun`
的子类。当前消费路径需要自行查询多个图并应用 Class 层次，且可能遇到 reasoning pointer 标记
为 current、对应结果图却没有物化最终父类断言的情况。

### 目标行为

平台为资源提供统一的有效分类视图，分别列出：

- 原始断言类型；
- 规则直接产生的类型；
- Reasoner 已物化的类型；
- 根据当前 Ontology 可蕴含但尚未物化的类型。

每个类型必须携带来源图、Run/Rule Definition、语义版本、current/stale 状态和可用 lineage。
平台不得把“可蕴含但未物化”伪装成已经写入 reasoning-result 图的事实，也不得因结果未物化而
让消费 Agent 误认为 Class 继承不存在。

派生状态必须区分任务执行成功、pointer 当前、输入签名匹配、结果图存在和预期物化完成等状态；
任何一项异常都应返回可诊断原因。

### 验收标准

- 合同运行返回原始类型 `WorkflowRun`、规则直接类型 `ResourceIntensiveWorkflowRun`，以及通过
  `rdfs:subClassOf` 可蕴含的最终分类 `AttentionRequiredWorkflowRun`。
- 响应明确区分规则结果与最终语义蕴含，并标识 `AttentionRequiredWorkflowRun` 是否已物化。
- `current` 不再掩盖空结果图、输入签名不匹配、pointer 过期或物化不完整。
- 相同类型由多个规则或推理路径产生时保留各自来源，不丢失可追溯性，也不无依据重复展示。
- Context Query、固定读模型和 scoped SPARQL 对同一派生状态的描述不互相矛盾。

## R1.2-007 紧凑响应、能力发现和可继续读取

当前状态：`未实现`

### 要解决的问题

全量 Entities 读模型会混合工作流定义、节点、运行、事件、日志、输入和输出，响应容易过大并被
截断；不支持的 `include` 或读模型名称主要通过试错发现。消费 Agent 难以提前选择最小字段集，
也难以从截断结果稳定继续读取。

### 目标行为

所有面向消费 Agent 的查询能力提供机器可发现的参数、支持值、字段集和限制。大结果集支持稳定
游标分页、服务端过滤、紧凑投影和可继续读取链接或参数；响应必须区分服务端完整结果、客户端
展示截断和工具传输截断。

当请求不支持的 `model_name`、`include`、`field_set` 或 `scope_mode` 时，错误响应返回允许值和
对应能力发现入口，避免 Agent 猜测下一次调用。接口清单继续以 R-011 的运行时 registry 为准，
不维护失真的第二份手工列表。

### 验收标准

- Agent 能在调用前查询受支持读模型、字段集、`include`、scope mode、默认限制和最大限制。
- Entities、Rules 和新增聚合读模型支持最小字段投影、类型/标签过滤和稳定游标分页。
- 截断响应返回 `truncated`、截断层级、已返回数量、继续游标和建议的收窄参数。
- 不支持 `include=relations` 或错误 scope mode 等请求直接返回允许值，不要求读取源码纠错。
- 相同语义版本、过滤和游标产生稳定、无重复、无静默遗漏的分页结果。

## 共同非目标

- 不在平台核心中调用通用 LLM 生成最终自然语言答案。
- 不让平台替代消费 Agent 执行 Dify 或其他目标系统的 API/MCP。
- 不因检索相似度自动创建别名、Mapping、Class、关系、事实或规则。
- 不把某个 Dify 合成参考实例硬编码为产品查询接口。
- 不要求所有业务问题都由固定聚合读模型覆盖；任意高级查询继续由 scoped SPARQL 承担。
- 不在本版本自动恢复 v1.0 全部 Pending 查询、搜索、向量、工作台或 Reasoner 部署需求。

## 版本级验收

v1.2 至少使用当前 Dify 合成参考本体重复执行以下验收，不依赖实现 Agent 的本地历史上下文：

1. 使用中文问题查找客服工单、发票对账、合同风险审查，并返回每个工作流的输入、真实节点顺序、
   节点类型和输出；本体未提供的 required 或输出类型保持缺失。
2. 查询合同风险审查执行成功但仍需关注的原因，返回 `status=succeeded`、
   `total_tokens=128000`、规则阈值 `>=50000`、直接分类 `ResourceIntensiveWorkflowRun` 和最终
   可蕴含分类 `AttentionRequiredWorkflowRun`，并说明最终类型是否已物化。
3. 从只知道 Project/Ontology 名称开始完成上述查询，全程只使用受支持 REST/MCP；不得调用内部
   Python、直接数据库、后端 ORM/Service 或读取源码来补足产品接口。
4. 对每一步保留范围、语义版本、召回原因、断言来源、规则/推理状态、截断和继续读取信息，能够
   复核答案没有猜测本体中不存在的信息。
5. 使用至少一个无匹配问题、一个跨语言歧义问题、一个截断结果和一个过期/未物化派生状态验证
   失败与边界行为。
6. REST 与 MCP 使用相同服务语义通过定向测试，并完成仓库要求的 backend、MCP registry、真实
   PostgreSQL/Oxigraph、服务重启和健康检查；若后续增加 UI，再执行对应 frontend build 与
   Playwright 验收。

## 实施顺序建议

R1.2-001 是版本闭环和共同验收要求，不作为其他条目的串行代码前置。R1.2-002 至 R1.2-006 可以
在共享响应语义确定后并行设计和实施；R1.2-007 应伴随各接口落地，而不是在功能完成后补做。

v1.1 与 v1.2 可以由不同工作流同步推进。若两者同时修改 MCP registry、Ontology read model、
执行记录或测试夹具，应按共享接口和测试数据协调合并，但不能把代码冲突误写为需求依赖。

每个具体需求进入实现前，应补充对应设计、共享测试计划和交付记录，并按
`docs/requirements/requirements-v1.0.md` 的状态口径同步更新本文件状态、实现证据和相关提交。
