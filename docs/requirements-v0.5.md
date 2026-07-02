# Ontology Platform v0.5 需求文档

## 版本定位

`v0.5` 的目标是把平台从“可表达结构化图谱事实”推进为“可按知识锚点治理业务知识、
规则和 Assertion 的平台”。

本版本重点解决四个问题：

1. 区分无法锚定、锚定到单实体、锚定到双实体关系、锚定到 Class 的不同知识形态。
2. 将核心业务知识统一落到结构化 Assertion，而不是散落在自由文本、属性或关系中。
3. 支持 Class-level 默认知识、继承、覆盖和召回合并。
4. 为业务规则接入平台提供 RuleDefinition、规则执行和派生 Assertion 的确定性路径。

`v0.5` 不把平台做成通用 RAG 系统、通用 BPM 引擎、通用复杂规则引擎或业务系统运行时。
外部 Agent 和 `ontology-builder` Skill 仍负责自然语言理解、候选规则提取和建模建议。
平台负责知识锚定、结构校验、证据绑定、审核、版本化、Assertion 生成、失效和发布治理。

## 核心原则

- **锚点优先：** 每条核心知识必须说明锚定对象：无锚点、Entity、Relation、Class 或 Rule。
- **Assertion 统一：** 进入核心平台的业务事实、规则结论和流程判断都应表达为可审核 Assertion。
- **弱知识隔离：** 无法锚定的零散知识可以进入向量召回层，但默认不参与发布、推理或业务判断。
- **Class 知识可继承：** Class-level 知识默认适用于实例，但 Entity-level 知识可以显式覆盖。
- **规则先治理后执行：** 自然语言规则必须先形成 Rule Proposal，经校验和审核后才能成为 RuleDefinition。
- **执行结果可追溯：** 规则执行只生成派生 Assertion，必须记录输入、规则版本、证据和推理路径。
- **确定性边界：** 平台内置规则能力只支持可解释、可回放、可测试的有限 DSL 和状态机逻辑。

## 关键概念

### Knowledge Anchor

知识锚点描述一条知识与平台对象的绑定方式。至少包含：

- `unanchored`：无法可靠绑定到当前任何节点的背景知识。
- `entity`：绑定到单个具体实体的知识。
- `relation`：绑定两个或多个实体之间关系的知识。
- `class`：绑定到 Class，默认适用于该 Class 的实例。
- `rule`：绑定到规则定义、规则条件、规则结论或规则执行结果。

### Assertion

Assertion 是平台核心知识断言层。当前实现可复用并扩展 `FactClaim` 模型。Assertion 至少包含：

- subject：断言主体，可以是 Entity、Relation、Class、Rule 或流程实例。
- predicate：断言谓词，如 `family_structure`、`FRIEND_OF`、`closes_at`、`HAS_STATUS`。
- value：断言值，可以是标量、对象或目标实体引用。
- anchor：知识锚点类型和目标 ID。
- evidence_ids：来源证据。
- generation_reason：产生原因，如 `direct_user_statement`、`rule:<rule_id>`。
- graph_path：输入实体、关系、属性、规则和推理路径。
- confidence、audit_status、review_decision、stale、stale_reason。

### RuleDefinition

RuleDefinition 是审核通过后的结构化业务规则。至少包含：

- rule_type：`classification`、`derived_relation`、`validation`、`workflow`。
- scope：适用 Class、RelationType、Entity 集合或流程模板。
- condition：受限 DSL 表达的条件。
- conclusion：规则满足时生成的 Assertion 模板。
- priority：冲突处理优先级。
- status：`draft`、`active`、`deprecated`。
- evidence_ids、created_from_proposal_id、version。

### Class Knowledge

Class Knowledge 是作用于某类对象的默认知识或政策，不是复制到每个实例的实体属性。

示例：

```text
TeachingBuilding closes_at 23:00
scope = default_for_instances
```

当查询某个具体教学楼时，平台应返回实体自身知识、所属 Class 知识、父类知识和适用规则。

## 新增能力需求

### 1. 知识锚定分类

平台需要为所有候选知识保存锚定类型，并在提案校验中检查锚点是否合理。

最低能力：

- 支持 `unanchored`、`entity`、`relation`、`class`、`rule` 五类锚点。
- Agent 提交知识提案时必须声明锚点类型和目标对象。
- 平台校验锚点目标是否存在、是否属于当前 Ontology、是否与知识类型兼容。
- 审核工作台展示锚点、证据和建议存储形态。

验收标准：

- “8 小时睡眠能保证上课状态”在无明确业务对象时进入 `unanchored` 背景知识候选。
- “小明是单亲家庭”被识别为 `entity` 锚点，目标为 `小明`。
- “小明和小华是好朋友”被识别为 `relation` 锚点。
- “教学楼统一 23:00 关门”被识别为 `class` 锚点，目标为 `TeachingBuilding`。

### 2. Unanchored Knowledge 与向量召回

无法与当前图谱对象可靠关联的零散知识可以进入扩展召回层，但不能自动成为核心事实。

最低能力：

- 保存原文、来源、摘要、embedding、标签、可信度和适用说明。
- 支持相似度召回，并在响应中标记为 `background_recall`。
- 支持后续人工或 Agent 将背景知识提升为 Entity、Class、Relation 或 Rule 知识。
- 不参与发布门槛、规则执行、流程判断或确定性问答。

验收标准：

- 查询相关主题时可以召回“8 小时睡眠能保证上课状态”。
- 平台响应必须区分该内容是背景召回，不是已审核图谱事实。
- 背景知识升级为规则或事实时，必须重新走 Proposal、Evidence、Review 和 Assertion 流程。

### 3. Entity Assertion

绑定到单个实体的知识应存储为 Entity-scoped Assertion，而不是仅作为自由文本备注。

最低能力：

- 支持将实体知识表达为 `subject / predicate / value`。
- 支持敏感级别、访问策略、证据和审核状态。
- 支持 Entity 属性与 Entity Assertion 的映射关系：稳定结构化字段可落属性，动态或敏感事实优先落 Assertion。
- Entity 删除、合并或属性变更时，相关 Assertion 必须标记 stale 或迁移。

验收标准：

- “小明是单亲家庭”生成 `subject=小明`、`predicate=family_structure`、`value=single_parent` 的 Assertion。
- 如果该知识被标记为敏感，未授权查询不能直接返回明文。
- 修改小明身份或合并实体后，相关 Assertion 不得静默丢失。

### 4. Relation Assertion 与实体级关系

两个实体之间的知识应优先表达为 Relation，并可同时生成 Relation-scoped Assertion 供审核。

最低能力：

- 支持实体级 RelationType，如 `FRIEND_OF`、`RELATED_TO`、`DEPENDS_ON`、`OVERRIDES`。
- Relation 支持 `symmetric`、`transitive`、`valid_from`、`valid_to`、`confidence`、`status`。
- Relation 创建后可生成对应 Assertion，进入 Fact Audit。
- Relation 事实不会自动提升为 Class-level RelationType。

验收标准：

- “小明和小华是好朋友”创建 `小明 --FRIEND_OF--> 小华`，并生成可审核 Assertion。
- 如果 `FRIEND_OF` 标记为对称关系，查询小华的朋友时可以返回小明。
- 若关系过期或被拒绝，相关 Assertion 必须更新状态或标记 stale。

### 5. Class Knowledge、继承与覆盖

Class-level 知识应作为默认政策、默认事实或默认约束作用于实例，而不是复制为每个实例的属性。

最低能力：

- 支持 Class-scoped Assertion。
- 支持 `scope=default_for_instances`。
- 支持 Class 层级继承：子类默认继承父类知识。
- 支持 Entity-level override，并记录覆盖原因、证据和有效期。
- 支持召回时合并 Entity、Class、父类和 override 知识。

验收标准：

- “教学楼统一 23:00 关门”存为 `TeachingBuilding closes_at 23:00` 的 Class Assertion。
- 查询“1 号教学楼几点关门”时，如果无实体覆盖，返回 Class 默认知识。
- 如果“实验教学楼 22:30 关门”，查询实验教学楼时返回实体覆盖，并说明覆盖了 Class 默认值。

### 6. 规则从自然语言到 RuleDefinition

业务规则必须通过外部 Agent/Skill 解析为结构化 Rule Proposal，再由平台校验和审核。

最低能力：

- Agent 从自然语言提取作用对象、条件、结论、证据和适用范围。
- 平台支持 `rule` proposal type 或扩展现有 `constraint` proposal。
- 平台校验规则引用的 Class、Property、RelationType、枚举值和目标 Assertion 模板。
- 审核通过后存储为 RuleDefinition。

示例：

```json
{
  "rule_type": "classification",
  "scope": {"class": "Student"},
  "condition": {">": [{"property": "average_score"}, 90]},
  "conclusion": {
    "assert": {
      "predicate": "student_status",
      "value": "excellent"
    }
  }
}
```

验收标准：

- “平均成绩大于 90 分的同学认定为优秀学生”可转为 Rule Proposal。
- 若 `average_score` 不是 number，平台拒绝规则。
- 若 `student_status` 不允许 `excellent`，平台拒绝规则或要求补充 schema 变更。

### 7. 规则执行与派生 Assertion

平台需要提供轻量规则执行服务，基于当前图谱快照和 RuleDefinition 生成派生 Assertion。

最低能力：

- 支持 `classification`：属性条件满足时生成分类或状态 Assertion。
- 支持 `derived_relation`：满足图模式时生成派生关系 Assertion。
- 支持 `validation`：条件违反时生成 `constraint_violation` Assertion。
- 执行结果必须记录 rule_id、rule_version、输入实体、输入属性、graph_path 和 evidence_ids。
- 规则执行不得直接改已发布图谱；派生结果先进入 Assertion 审核。

验收标准：

- 学生平均分为 93 时，规则生成“该学生是优秀学生”的 `derived` Assertion。
- 学生平均分改为 88 后，原派生 Assertion 被标记 stale。
- 规则版本变更后，受影响的派生 Assertion 需要重新计算。

### 8. 工作流规则与流程状态

审批顺序类知识应表达为流程模板、步骤和状态约束，而不是普通自由文本。

最低能力：

- 支持 `WorkflowTemplate`、`WorkflowStep`、`WorkflowInstance` 的最小模型，或以 RuleDefinition +
  Assertion 形式表达同等结构。
- 步骤包含 role、order、entry_condition、exit_condition、status。
- 支持判断当前实例是否允许进入下一步，并生成 workflow Assertion。
- 支持流程定义版本化，不要求实现完整派单、通知、超时和会签能力。

验收标准：

- “某文件审批流程先是辅导员，然后是专业负责人”可表达为两个有序步骤。
- 文件未完成辅导员审批时，平台能生成“不允许进入专业负责人审批”的 validation Assertion。
- 文件完成辅导员审批后，平台能判断下一步为专业负责人。

### 9. 召回合并策略

平台需要为实体查询和问答提供统一知识合并逻辑。

最低能力：

查询某个实体时，返回以下来源并标注来源类型：

1. Entity 自身属性。
2. Entity-scoped Assertion。
3. 直接 Relation 和 Relation Assertion。
4. Class-scoped Assertion。
5. 父类继承知识。
6. Entity-level override。
7. RuleDefinition 产生的派生 Assertion。
8. Unanchored Knowledge 的背景召回。

验收标准：

- 查询“1 号教学楼”时能同时返回实体属性、Class 默认关门时间和相关背景材料。
- 如果 Entity override 与 Class 默认值冲突，优先返回 Entity override，并展示被覆盖的 Class 知识。
- 背景召回必须单独标注，不得与已审核 Assertion 混为同一可信级别。

### 10. 失效、冲突与发布门槛

规则、Class 知识和 Assertion 都必须参与治理状态管理。

最低能力：

- Entity、Relation、Class、RuleDefinition 或证据变更后，相关 Assertion 标记 stale。
- 支持同一主体和谓词的冲突检测。
- 支持 override 关系解释冲突，不把合法覆盖误判为错误。
- 发布前要求核心 Assertion、规则派生 Assertion 和冲突项完成审核。

验收标准：

- “教学楼 23:00 关门”和“实验教学楼 22:30 关门”不会被简单判为冲突，而是识别为 override。
- 两条同优先级规则对同一学生生成不同状态时，平台生成冲突项并阻塞发布。
- 存在 pending 或 stale 的核心 Assertion 时，发布 readiness 返回明确 blocker。

## 最小验收场景

1. 用户输入“平均成绩大于 90 分的同学认定为优秀学生”。
2. Agent/Skill 生成 Rule Proposal，平台校验 `Student.average_score` 和结论字段。
3. 审核通过后，平台保存 RuleDefinition。
4. 平台执行规则，为平均分 93 的学生生成 `derived` Assertion。
5. 用户审核该 Assertion 后，发布 readiness 通过相关规则门槛。
6. 用户输入“教学楼统一 23:00 关门”，平台保存 Class Assertion。
7. 查询具体教学楼时，平台返回实体知识、Class 默认知识和来源证据。
8. 用户输入“实验教学楼 22:30 关门”，平台保存 Entity override。
9. 查询实验教学楼时，平台返回 22:30，并说明覆盖了教学楼默认 23:00。
10. 用户输入“8 小时睡眠能保证上课状态”，平台作为背景知识召回保存，不进入核心发布事实。

## 暂不纳入 v0.5

- 通用复杂规则引擎、任意代码执行规则或完整 OWL DL 推理。
- 通用 BPM、派单、通知、超时、会签、组织权限和流程运行平台。
- 把所有非结构化材料建设成完整 RAG 产品。
- 无审核地把向量召回内容提升为正式业务事实。
- 自动决定复杂业务规则的最终语义；外部 Agent 只能提出候选，平台和人工审核决定是否入库。
- 完整主数据管理、数据质量平台或生产业务系统替代能力。
