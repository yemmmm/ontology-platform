# Ontology Platform v0.4 需求文档

## 版本定位

`v0.4` 的目标是把平台从“本体 Schema + 图实例管理”推进为“领域语义、实体事实、
外部数据目录和 Agent 写入/查询入口”统一的平台。

本版本重点解决三个问题：

1. 避免把数据库 Schema 直接照搬为 Ontology。
2. 让图谱能够表达自然语言中的结构化知识事实。
3. 让外部系统中的数据可被语义定位、授权访问和受控查询。

`v0.4` 不要求把所有业务数据迁入 Neo4j，也不把平台做成通用数据库代理、通用 ETL、
文档知识库、大模型服务或内置智能体系统。

所有智能判断均由外部 Agent 结合 `ontology-builder` Skill 完成。平台只提供确定性的
状态管理、数据模型、校验、版本控制、提案流转、图写入、图查询、目录查询和受控连接器能力。

## 核心原则

- **能力问题驱动：** 先定义平台要回答的问题，再设计 Class、Property 和 RelationType。
- **语义与存储分离：** Ontology 描述领域含义；Mapping、Catalog 和 Connector 处理数据位置。
- **Schema 稳定，事实动态：** Class-level schema 表达稳定领域模式；Entity-level graph 表达具体事实。
- **关系是一等公民：** 有独立语义、可遍历、可解释的连接应建为 Relation，而不是属性字段。
- **图谱不是垃圾桶：** 能结构化不代表必须入图；入图取决于查询价值、联动价值和维护能力。
- **治理前置：** 敏感字段、外部查询和身份合并必须经过平台策略，不允许 Agent 直接绕过。

## 建模边界

### Ontology 与数据库 Schema

Ontology 关注领域中稳定的概念、身份、关系和推理路径。数据库 Schema 关注字段、表、
索引、事务和存储效率。

平台需要提供数据结构和校验规则，使外部 Agent 在建模流程中能够明确区分：

- 领域概念：如 `Student`、`Course`、`Assessment`、`Dormitory`。
- 领域关系：如 `ENROLLED_IN`、`HAS_RESULT`、`APPLIES_TO`。
- 具体事实：如“李四高等数学期中成绩 42 分”“寝室 23:00 门禁”。
- 外部字段：如 `student_table.student_no`、`student_pii.id_card_number`。
- 治理元数据：如敏感级别、访问策略、审批要求、数据负责人。

禁止默认“一张表一个 Class、一列一个 Property、一条外键一个 Relation”。表结构只能作为
候选来源，不能作为本体结构的权威。

### Class-level Relation 与 Entity-level Relation

平台需要支持两类关系：

1. **Class-level RelationType**：定义在 Ontology Schema 中，表达稳定领域模式。
2. **Entity-level Relation**：定义在实体图谱中，表达两个具体实体之间的事实或特例。

例如：

```text
CourseOffering --CONFLICTS_WITH--> CourseOffering
```

表示课程安排之间存在“可能冲突”的稳定关系，属于 Class-level RelationType。

```text
2026春-高数周三1-2节 --CONFLICTS_WITH--> 2026春-物理周三1-2节
```

表示两个具体课程安排冲突，属于 Entity-level Relation，不应自动反推为两个 Class
之间存在 schema 关系。

## 新增能力需求

### 1. 建模方法论与能力问题

外部 Agent 和 `ontology-builder` Skill 需要在建模阶段执行以下判断；平台负责保存这些
判断产生的提案、校验结构约束并记录审核结果：

- 这个概念是否有稳定身份和生命周期？
- 更换数据库表名后，该概念是否仍然成立？
- 用户是否会用自然语言直接提到它？
- 它是否参与图遍历、解释、推理或模式发现？
- 它是领域事实，还是数据源字段、运维字段、治理字段？

验收标准：

- Project Brief 支持记录领域范围、排除项、关键身份规则和能力问题。
- Schema 候选提案中能标注候选项来源于“领域概念”还是“数据源结构”。
- Agent 在生成 schema 前必须先提出或复用能力问题。

### 2. Semantic Mapping

平台需要新增独立的语义映射层，连接 Ontology 与外部系统。

最低能力：

- Class / Property / RelationType 到外部系统资源和字段的映射。
- Entity 到外部系统 ID 的映射，如 `student_number`、一卡通编号、第三方系统 ID。
- 映射字段包括数据源、资源名、字段名、join key、有效期、置信度和负责人。
- 映射可以独立版本化，不要求修改已发布 Ontology。

验收标准：

- 外部表名变更后，仅更新 Mapping/Catalog，本体版本保持不变。
- 用户询问“李四高等数学期中成绩”时，平台能从实体映射定位外部成绩字段。

### 3. Data Catalog 与 external_fields

平台需要承担数据目录角色，保存“数据在哪里、怎么查、谁能查”，而不是复制所有数据。

最低能力：

- 登记数据源、资源、字段、负责人、权威级别、可用状态和说明。
- 字段级声明敏感等级、访问策略、脱敏规则、审批说明和审计要求。
- 支持 `external_fields` 描述图中不存储但可被平台路由的字段。

验收标准：

- 身份证号等 PII 不进入图谱实体属性。
- 当用户查询受限字段时，平台能返回拒绝原因、审批要求或在授权后代理查询。

### 4. Connector 与代理查询

Agent 不直接访问外部数据库。Platform 根据 Mapping 和 Catalog 做受控代理查询。

最低能力：

- 白名单数据源和预定义查询模板。
- 参数化查询，不开放任意 SQL。
- 查询前执行访问策略检查。
- 查询结果包含来源、查询时间、授权结果和审计信息。

验收标准：

- 未授权敏感查询被拒绝。
- 授权查询可返回匹配结果并记录审计信息。
- Agent 只能通过 MCP/API 请求平台查询，不能获得外部数据库凭据。

### 5. 知识事实入图

平台需要支持外部 Agent 将自然语言中的结构化知识事实写入为实体、属性和关系。

示例：

```text
寝室十一点门禁
```

应表达为：

```text
(:Dormitory {name: "学生寝室"})
(:AccessPolicy {name: "寝室门禁规定", cutoff_time: "23:00"})
(:AccessPolicy)-[:APPLIES_TO]->(:Dormitory)
```

而不是简单写成：

```text
(:Dormitory {access_time: "23:00"})
```

最低能力：

- 支持政策、校历、考试周、假期、设施建设等事实类实体。
- 支持有效期、适用范围、状态和例外说明。
- 支持事实动态变更，不要求修改 Ontology Schema。

验收标准：

- “16 周是考试周，不用上课”可表达为考试周和停课规则。
- “寝室 23:00 门禁”可表达为门禁规则作用于寝室。
- “2 号图书馆明年建成”可表达为设施建设项目及预计完成时间。

### 6. 入图判断标准

对弱关联知识，外部 Agent 不应无条件写入图谱。入图判断至少包含三个问题：

1. 用户或 Agent 是否会查询它？
2. 它是否影响现有实体的状态、行为、解释或推理？
3. 平台是否有能力维护它的时效性？

满足两个以上，Agent 可以提交入图提案；否则建议保留在文档、外部系统或未来主题图谱中。
平台只负责校验提案结构、关系约束和版本状态，不负责语义取舍。

示例：

```text
端午节学校放假三天
```

如果平台要回答“今天是否上课”“图书馆是否开放”“为什么课程暂停”，则应进入校历图谱：

```text
(:Holiday)-[:APPLIES_TO]->(:School)
(:Holiday)-[:SUSPENDS]->(:RegularClass)
```

如果当前平台只管理学生、课程和成绩，且不涉及校历或排课，则暂不入图。

### 7. Entity-level Relation

平台需要开放实体级关系，但必须与 Class-level RelationType 区分。

最低能力：

- Entity Relation 支持 `scope=instance`。
- RelationType 支持声明 `schema_allowed`、`entity_only` 或 `both`。
- 支持关系元信息，如 `symmetric`、`transitive`、`status`、`valid_from`、`valid_to`。
- Entity-level Relation 不自动写入 Ontology Schema，不自动反推 Class 关系。

建议首批内置通用实体级关系：

- `CONFLICTS_WITH`
- `RELATED_TO`
- `DEPENDS_ON`
- `OVERRIDES`
- `REPLACES`
- `BLOCKS`
- `DUPLICATES`
- `SAME_AS`
- `PART_OF`

验收标准：

- 可以表达 `entity1 --CONFLICTS_WITH--> entity2`。
- 该关系不会污染两个实体所属 Class 的 schema。
- 只有当同类实体关系反复出现并经过人工确认时，才可提升为 Class-level RelationType。

### 8. 实体解析与映射发现

平台需要支持对未建模的跨系统标识符关系做确定性数据分析，但不能自动确认为 `same_as`。
是否构成领域上的同一实体，由外部 Agent 形成候选解释并交由人工审核。

最低能力：

- 对两个外部系统的标识符集合做覆盖率、一对一、一对多、多对一等确定性统计。
- 将统计结果返回给 Agent；候选映射或 Merge Proposal 由 Agent/Skill 提交。
- 人工确认后才能写入身份映射或 `SAME_AS`。

验收标准：

- 用户询问“学生编号和学号是否一一对应”时，平台能先检查现有图关系。
- 若无关系，平台可在授权后比较两个外部系统值集合并返回统计结果，由 Agent 生成候选结论。

## 最小验收场景

1. 用户通过能力问题定义一个校园领域项目。
2. Agent/Skill 生成 `Student`、`Course`、`Assessment`、`AssessmentResult`、`Dormitory`、
   `AccessPolicy`、`Holiday` 等候选概念并提交平台，而不是复制数据库表名。
3. Agent/Skill 提交成绩、身份证号等字段到外部教务系统的映射；平台保存和校验映射，
   身份证号不进入图谱。
4. 用户询问学生成绩时，平台通过 Mapping、Catalog 和 Connector 查询外部系统。
5. 用户询问“寝室几点门禁”时，平台通过实体图谱返回门禁规则。
6. 用户询问“端午节是否上课”时，如果项目包含校历能力，平台通过假期事实解释停课。
7. 用户创建 `entity1 --CONFLICTS_WITH--> entity2`，该关系作为实体级事实保存，不改变 schema。
8. 发布后的 Ontology Schema 不可原地修改；事实、映射和目录按各自治理规则演进。

## 暂不纳入 v0.4

- 任意数据源的通用 SQL 代理。
- 无人工审核的实体自动合并或 `same_as` 写入。
- 完整主数据管理平台和通用 ETL 平台。
- 将所有外部业务数据同步到 Neo4j。
- 完整 RBAC 和组织租户体系。
- 复杂文档 RAG、全文问答和向量检索平台。
- 自动从弱关联文本中无限制抽取所有“知识”入图。
