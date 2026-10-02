# R4.0-010 数据映射视角与外部数据库关联设计

- 日期：2026-10-02。
- 状态：独立方案复审 Round 2 PASS（0 Critical／0 High）；后续用户授权按设计开发和测试，
  功能已实现，开发侧 A1—A9 功能验证 PASS，见[测试记录](../tests/2026-10-02-r4-0-010-relational-data-mapping-test-record.md)。
  独立功能／A10 真实语义验收未执行，整体 PARTIAL。
- 权威范围及决策主表：[R4.0-010](../../requirements/requirements-v4.0.md#r40-010-数据映射视角与外部数据库关联)。
- 代码基线：`9aa73d1`；开始时工作树干净。定向核对编译、Batch 映射校验、候选翻译、
  审批投影、映射／指标读取及跨视角上下文，未运行产品或数据库。
- 设计阶段授权：完成需求细化、设计，随后独立 Agent 审阅并修订至方案 PASS。
  后续另授权开发和测试，使用隔离平台数据库 fixture；不含外部业务数据库查询、外部执行或真实建模。
  D1—D10 无待用户决策项。
- 继承：[R3.0-003](../../requirements/requirements-v3.0.md#r30-003-纯语义-ontology-与关系型-schema-映射)、
  [既有映射设计](2026-08-26-r3-0-003-relational-schema-mapping-design.md)、
  [术语](../../reference/glossary.md)。历史设计的 Evidence 要求以当前 012 停用边界为准。

## 1. 目标与最小方案

工单表一行一张工单，维修明细表一行一个维修项目。一张工单对应三条明细时，连接后的三行
仍不能当作三张工单；数据库主键也未必是用户使用的工单编号。模型需要让 Consumer 知道
每行代表什么、如何识别统计对象、通过哪条路径连接以及何时必须去重或预聚合。

复用 TableMapping、JoinMapping、EnumValueMeaning、MetricDefinition 的稳定 IRI、
现有 CRUD 和 Ontology RDF 图。新增 `mapping_definition` 结构化注解、补充必要的明确
资源引用，并把 `semantic_definition` 扩展到这四种资源。无需新表、新资源体系、业务路由、
连接器框架或前端页面。数据库行不进入 RDF，平台保存和读取映射，不执行查询／转换。

只用自由文本无法确定多源同名表／自关联角色；另建映射体系则重复既有写入、授权和读面。
扩展现有四种资源能够解决当前登记的粒度、身份、基数和编码冲突，采用 D1—D6。
具体业务基数、单位换算及标识对应仍由资料／访谈确认，本文不把示例内容声明为真实业务事实。

## 2. 实际基线与差异

| 入口 | 已有能力 | 本条缺口与复用方式 |
| --- | --- | --- |
| [编译器](../../../backend/app/services/semantic_command_compiler.py) | 四种资源 CRUD，`schema_source`／`semantic_version`，JSON 字面量 | TableMapping 强制 Class、每列属性和至少一个 business_key；join 只有表名／列数组；需补明确信息且避免伪造语义 |
| [字段白名单](../../../backend/app/services/modeling_handlers.py) | 既有 12 个映射命令；semantic_definition 仅支持 class／property／entity／relation_type | 扩展四种映射 create／update 的注解与引用字段；delete 不接收注解 |
| [Batch](../../../backend/app/services/modeling_batches.py) | G2 引用、G3 路径闭合、G5 编码唯一性、G6 存在性、G7 参考值引用；原子应用与恢复 | G2／G3 只看目标 Ontology；G3 按 table_name 建字典，G5 按 property＋code 去重；补获准拓扑引用、来源／角色作用域及更新后的完整性 |
| [Protocol](../../../modeling_team/protocol_mechanics.py) | `translate_candidate_to_batches` 与 definition_ref；实体既有绑定 | 尚无四类 mapping 的中性候选翻译，不能声称后端命令已有就能真实建模；增量须进入活动翻译与绑定 |
| [统一审批](../../../modeling_team/staged_decisions.py) | 完整候选、摘要、拓扑决定、身份和审批投影 | 统一候选 item_kind 及身份读回需要识别既有四类映射，覆盖全部注解与引用，不能变成普通 entity 副本 |
| [读取模板](../../../backend/app/services/semantic_sparql_templates.py)、[read model](../../../backend/app/services/semantic_read_model.py) | 四类列表／精确模板及 detail_fields | 新字段需投影、JSON 解码；类名与资源身份不变；映射不依赖只读 asserted_data 的 statements 面 |
| [Context Query](../../../backend/app/services/semantic_context_query.py) | mapping／metric 生产器、通用注解 hydration、008 授权后展开与完整性 | 新注解进 full／compact，嵌套引用也成为有方向的显式关联，不能只把 JSON 原样放回而无法展开 |
| [访问过滤](../../../backend/app/services/semantic_access.py) | 递归扫描 JSON 字符串／对象里的 IRI，过滤读模型、候选、statement 和导出 | 复用扫描；验证新增字段全程进入过滤，并按现有合同隐藏引用受限对象的结果 |
| [外部 SQL 工具](../../../scripts/r3-0-005/sql_exec_adapter.py) | 执行获准单条 SQL，返回 rows／数据库错误；单 PostgreSQL 连接 | 沿用，不修改，不增加数据权限、策略改写或跨源执行；连接配置由外部宿主保管 |

上述为代码事实和缺口定位，不是本轮功能验证。004／006／007／008／012 已有实现和各自
验证状态不替代本条验收；009 映射段仍待真实运行授权，011 仍待细化。

## 3. 资源与注解合同

### 3.1 共同规则

- 每个映射资源可携带 `semantic_definition`：semantic_role=data_mapping、business_meaning、
  applicability、unknowns、not_applicable、conflicting_meanings，语法复用 002。
- `mapping_definition` 按主体已有 rdf:type 使用下列封闭字段；保存为
  `op:mappingDefinition` 的规范 JSON 字面量，沿用现有 JSON 序列化和授权扫描。
  不新建通用注解注册器。资源身份取编译回执 metadata 的实际主体，避免 metric／enum_meaning
  等命令名和 IRI 路径不一致导致注解写到另一主体。
- 注解缺省表示未提供，字段 `null` 表示明确未知，空数组表示明确没有已声明成员；业务“不适用”
  和冲突由 semantic_definition 表达。写入结构完整与 Consumer 足够回答是不同结论。
- update 的字段缺省保留，非空对象替换该注解，`null` 清除整个注解；嵌套字段不做隐式 merge。
  字段形状错误定位到具体项，修改／清除后的合并视图仍须保持现有引用完整性。
- 本文 JSON 仅为拟定合同示意，当前工具尚未支持；其中 IRI 是读回后的示意，Modeling 使用
  中性定义引用，不能复制示例去猜平台 IRI。

### 3.2 TableMapping：表行、对象和字段

保留原 `table_name`、`column_mappings`、`schema_source`、`semantic_version`。
新增 `mapped_definition_iri`（`op:mappedDefinition`），引用共享普通业务定义或正式 Class。
原 `mapped_class_iri`／`op:mappedClass` 保持原 Class 合同；create 两种字段恰好一个，不能
同填。update 不通过换目标偷改同身份的业务含义；确需改变目标定义时按 007 创建新映射并重审引用。

column_mappings 保留 column、property_iri、role=value／business_key 的旧形态；新增形态
允许 property_iri 缺省（只声明物理列），role 默认为 value。只有有属性引用、且业务意义已
确认的成员才能声明 business_key。物理列不自动创建属性。至少一个 business_key 的旧硬门
改为可表达未知业务键；空 column_mappings 仍为无效输入，未知业务键不能暗示所有行属于同一对象。

| mapping_definition 字段 | 类型与含义 |
| --- | --- |
| source_key | 非空字符串；Project 内稳定、非秘密来源键，不含 Schema 版本或 DSN |
| schema_version | 字符串／null；确认的 Schema 版本；schema_source 继续记录原 Schema 资料定位 |
| row_grain | 字符串／null；一行代表什么；对象、事件、快照等由业务解释，不固定业务类别枚举 |
| record_key_columns | 列名数组／null；区分行的完整复合键，数组一起构成一个键，不默认等同对象身份 |
| object_key_columns | 列名数组／null；识别该用途下业务对象的键，配合 applicability；可与记录键不同 |
| identifiers | 对象数组；每项为 columns、kind、property_iri、scope、correspondence；kind 为 technical／business／external／unknown，其余未确认部分为 null；描述其他编号和对应条件 |
| field_meanings | 对象数组；每项为 column、source_meaning、source_unit、target_unit、time_semantics、null_meaning、conversion_rule_iri；column 非空，其余字符串／null，规则为 IRI／null |
| row_scope | 字符串／null；该映射所覆盖的记录条件、快照／当前态范围，不是平台 SQL 过滤程序 |

source_key 在新表映射注解中必填；其余未知允许 null／未提供并披露缺口。identifiers[].columns
为非空列数组；property_iri 如存在指向共享属性定义，scope 区分租户／组织／时间等业务唯一性
范围，correspondence 说明对应条件，不能保存实例编号。所有列须在 column_mappings 出现。
field_meanings 中的转换规则引用 005 的普通业务规则，不是平台可执行 Rule。
time_semantics 说明时间代表的业务事件、时区和窗口边界；复杂含义可引用现有规则而不引入 DSL。

同一来源表允许多个适用范围明确的映射；消费者通过映射 IRI 区分，不能由 `(source_key, table_name)`
自动合并。一个对象由多表表示时各表引用共享定义，关系／字段和范围解释各自职责；没有通用主表假设。

### 3.3 JoinMapping：路径与角色

保留 relation_type_iri、join_direction=forward／reverse、schema_source、semantic_version。
每条 join_path 必须整体采用以下一种形态，不能混用：

- 旧形态：from_table、to_table、from_columns、to_columns；只在映射所属来源与目标 Ontology
  下能唯一解析两端表映射时允许。重复表名不按字典覆盖；返回可修正歧义，要求明确引用。
- 新形态：from_mapping_iri、to_mapping_iri、from_role、to_role、from_columns、to_columns。
  mapping IRI 引用 TableMapping，role 为路径内非空用途键；相邻步骤的前一 to_mapping＋to_role
  等于后一 from_mapping＋from_role。自关联允许同一 mapping 的不同 role；列数组按位置等值配对。

| mapping_definition 字段 | 类型与含义 |
| --- | --- |
| step_semantics | 数组；每项对应 join_path 索引，含 step_index、join_type、cardinality、additional_condition、condition_rule_iri |
| relationship_meaning | 字符串／null；这些连接为何代表已引用的业务关系，与 join_direction 一起解释方向 |
| duplicate_risk | 字符串／null；关联后哪些对象／值可能重复及使用注意事项 |
| execution_prerequisite | 字符串／null；跨源或复杂连接所需外部条件；不是连接配置或可执行能力声明 |

step_index 为有效、唯一的从 0 开始索引；join_type=inner／left／right／full／unknown，
cardinality=one_to_one／one_to_many／many_to_one／many_to_many／unknown，均按路径 from→to。
additional_condition 表达已确认的非等值／范围／编码连接条件，可选引用共享条件规则。
无 step_semantics 成员表示该步条件未分析，不默认 inner 或一对一。非等值／复杂条件须
Consumer 理解已确认说明／规则；此处不提供可自动编译 SQL 的谓词语言。

不强制所有基数已知；平台检查数组、引用及邻接，不扫描业务行证明一对多。路径顺序是连接
顺序，role 只代表该路径中的用途，不新增业务类别、实际对象或平台执行变量。

### 3.4 EnumValueMeaning：字段作用域

沿用 property_iri、enum_value、business_meaning、semantic_value（可选 L3 引用）。
新增 `table_mapping_iri`（`op:tableMapping`）和 `column`（`op:columnName`），两者同时给出
或同时缺省；给出时列须在所指表映射中映射到 property_iri。

- 新作用域唯一键为 `(table_mapping_iri, column, property_iri, enum_value)`；同一属性同编码在
  不同字段可以并存，不能静默覆盖同作用域的不同含义。
- 未给作用域的旧资源继续在旧组按 `(property_iri, enum_value)` 检查，不阻断不同作用域的新资源。
  读取中旧组不作为所有来源的默认值；只有当前来源可唯一闭合、且不存在明确作用域歧义时使用。
- 新／旧资源相互矛盾或多个映射上下文可用但未选择时，Consumer 保留冲突并报告无法确认。
  不按代码命中排序自动选择；不能在多源场景自动把旧映射迁移为某一个字段。
- mapping_definition 此类型只支持可选 conversion_rule_iri，用于已确认的编码转换规则。
  API 编码仍由 011 定义；数据库和 API 可以指向同一 semantic_value，不要求编码一致。

编码为受控参考值，不是具体业务行。L1 普通值不强建节点；L2 使用 business_meaning，
L3 延续 semantic_value 的稳定定义和可见性合同。

### 3.5 MetricDefinition：业务口径与物理上下文

继续用现有 grain、time_field、measure_property_iri、filters、aggregation、value_expression、
null_value_rule、denominator_rule 表达指标业务口径，不在映射注解复制一份公式。
mapping_definition 只有 `contexts` 数组，各项如下：

| 字段 | 含义 |
| --- | --- |
| context_key | 该指标内唯一、稳定非空键；外部 Consumer 根据问题范围选择，不按数组顺序选 |
| applicability | 字符串／null；此物理实现适用范围，不能覆盖业务定义 |
| base_mapping_iri | TableMapping IRI；统计出发点 |
| base_role | 非空角色键；与所选路径中的表用途一致；零条路径时仍明确用途 |
| join_mapping_iris | JoinMapping IRI 数组；所选路径；空数组明确无需 join，集合不代表执行顺序 |
| property_bindings | 数组；每项 property_iri、table_mapping_iri、role、column，把度量／时间／过滤／分组属性绑定到具体表角色列 |
| counted_identity | 数组／null；每项 table_mapping_iri、role、columns；整体代表一个统计对象的复合身份，null 为未知 |
| duplicate_handling | 字符串／null；明确不重复、按对象复合键去重或在明细先聚合的业务理由／约定 |
| conversion_rule_iris | IRI 数组；共享转换规则，空数组表示未声明转换，不能据此推断一定不需要 |

所有 role 要在 base 或所选路径出现，列闭合到所指 TableMapping；绑定属性必须与该列的
property_iri 对应。一个上下文内同一属性若有多个候选物理位置，保留冲突并让 Consumer
澄清用途，平台不自动优选。上下文关键键和引用已提供时必须结构合法；缺少业务判断允许未知。
既有 time_field 必填合同不在本条移除，缺真实时间依据时不得为凑合格编造字段。

工单数量可在无明细连接的基表按工单身份计数；确需按明细条件筛选时，明确先筛选后按同一
工单身份计数。工时总和则按明细度量汇总，不能对工时值做 DISTINCT 把相同数值的两条明细合并。
这些是示例的确认逻辑，不能写进平台默认规则。多个 contexts 不声明跨源汇总／互斥／完备性，
需要合并时保留明确业务条件或未知，不将数据源结果直接相加。

## 4. 候选、翻译与写入流程

```mermaid
flowchart LR
  A[获准资料与访谈] --> B[共享定义及映射候选]
  B --> C[Coordinator 语义与拓扑审批]
  C --> D[Protocol 引用绑定与确定性翻译]
  D --> E[现有 Batch dry-run / apply_atomic]
  E --> F[获准资源与 Context Query 读回]
  F --> G[Consumer 解释 / 独立映射验收]
```

1. Modeling 在已选的两种活动候选表达中使用 table_mapping／join_mapping／enum_meaning／
   metric_definition 四种中性 item_kind，物理字段和语义注解采用第 3 节含义；不提交 Batch、
   ontology_id、工具命令、平台 IRI、回执或凭证。映射 item_id 是候选语义身份。
2. 当前候选引用继续使用 `{definition_ref: item_id}`，统一候选沿用其批准的中性端点引用。
   既有引用只接受当前活动 R4 流程的受治理读取绑定，不能借用仅 R2.3-003 可用的 existing_entity_ref
   合同。需要扩展现有绑定的资源种类识别，不能直接假定 mapping 是 entity。
3. Coordinator 沿用场景地图／拓扑决策、共享定义 owner 和完整候选审批。新的 item_kind、
   mapping_definition、semantic_definition、作用域引用均进入现有内容摘要和批准投影。
   有未知可批准已确认的局部内容，不把批准变成业务事实。
4. Protocol 确定性翻译到既有四类 create 命令，依次解决业务定义／属性／规则引用、TableMapping、
   JoinMapping／EnumValueMeaning、MetricDefinition；普通业务关系指向映射时须在映射创建后
   处理。在既有按依赖形成计划的逻辑内补这几种资源，不新增 Team 阶段／运行框架。
5. 稳定身份由批准映射语义键与现有 namespace／回执唯一绑定，既有映射更新不改其 IRI；
   名称、Schema 版本及 slice 不直接生成新身份。新增 mapping 引用位置全部递归转换，
   不允许 JSON 内残留未解析 definition_ref 或假 IRI。
6. 对每个具体 Batch 使用当前 workspace_version、现有 lease、dry-run／apply 与回执。
   同批先按最终 deletes／inserts 投影再校验；跨 Batch 只使用已物化且已读回的引用，不能把
   将来 Batch 的资源当作当前存在。预检查后当前代码会 commit 再 _execute，因此版本／lease
   不是跨图完整性保证；实写前按 §5.2 重新锁定和校验。技术依赖顺序不要求所有视角分析完。
7. 读回校对实际主体、全部业务／映射注解、物理字段和引用；四类资源用原专属精确模板和
   Context Query，不以 asserted_data 的 `/statements` 可读性证明 Ontology 图的映射完整。

已有候选版本字段不因追加这些可选形态一律重命名；封闭校验器、authoring reference、活动
角色 Skill／Task 组装须同步。旧合法候选及非映射任务保持原行为，不追改已冻结历史包。
若当前候选未具备新形态，返回具体翻译冲突，不能把映射悄悄丢弃后报告完成。

## 5. 确定性校验、失败与权限

### 5.1 校验范围

只校验可观察输入和引用，不调用外部数据库。扩展原 G2／G3／G5／G7 的最窄实际缺口：

- 写目标仍为 Batch 所属 Ontology；读取引用图限定在当前 Project 已批准的拓扑依赖内，包含
  所引用普通定义的数据图、属性／映射的 Ontology 图及同批最终 delta。跨 Project 禁止；
  同 Project 也不等于全库允许。复用现有拓扑决策／Graph Set 解析，不由平台选择 Ontology 数量。
- 新 mapped_definition 检查是已存在共享定义／Class，非映射／治理资源；旧 mapped_class 仍
  检查 Class。属性引用检查已有属性，rule 引用检查 005 业务规则；不从 rdf:type 自动判定业务正确。
- 列、复合键、作用域、step 索引、两端配对、路径邻接、表角色及指标绑定均按第 3 节闭合。
  技术列可以没有属性引用，但不能被假定为业务属性／business_key。
- 新旧 join 都不得把两个候选同名表覆盖成一个。旧形态还没有稳定 source_key 时仅在原来源
  定位唯一才可用；无法唯一定位返回 `ambiguous_mapping_reference`，切换新明确引用即可继续。
- scoped 编码采用新唯一性；unscoped 采用旧组唯一性。不能因不同字段代码相同拒绝所有新资源。
- update／delete 检查最终态的引用完整性，不仅改动 item 自身。跨 Ontology 表／规则／共享定义
  被删除时，检查同 Project 内已有显式反向依赖，不能因当前 Batch 不含 mapping 命令就跳过。
  只保护声明的引用，已知业务兼容影响通过 007 重审，不构建自动兼容裁判。

拟定错误反馈复用现有 code／item_ids／path／severity 合同：格式错误、invalid_resource_reference、
join_path_not_mapped、ambiguous_mapping_reference、resource_already_exists。增加的编码／
映射作用域错误须定位具体 column／step／context。未知业务键、基数、单位等不生成永久拒绝；
Consumer 未具备必要上下文则如实无法确认。修正后重做相同目标的 dry-run，不人为增加 fresh start。
不确定写入仍按原 Batch／Attempt／回执恢复要求先确认状态。

跨 Ontology 的反向依赖检查与现有共享定义删除路径需在实施时接线；这是明确实现缺口，不把
目前 G2／G3 的本 Ontology 校验描述成已经覆盖全拓扑。未声明的业务影响不由平台猜测。

### 5.2 最终写入临界区（H010-01 修订）

初审反例：A 图的新增 JoinMapping 校验时 B 的列还在；B 的删列校验时 A 的 join 还没写。
当前两者只锁各自 Ontology，且预检查后 commit，不能保证最终无悬空。仅在两边各补一次
独立重读仍有同一窗口。采用共同串行边界，复用已有 ProjectModel 行和 Batch／Attempt，不建
锁表、advisory lock、跨图原子写或新的恢复协议。代价是同 Project 的相关写入短暂串行，
符合当前本机有界建模规模；读取不需要因此锁整个 Project。

1. 固定顺序为 Project 行（多 Project 时按 ID）→既有图所有者 Ontology 行（按 ID）→
   Attempt／fence。所有可能影响映射的 Batch submit、canonical 及直接编辑入口，均在原来
   首次 FOR UPDATE 之前取得所属 Project 行锁，不可先锁自己 Ontology 再争夺 Project。
   由目标图登记解析 Project，不信任 payload 伪造归属；目标范围／授权合同保持原样。
2. submit 的检查与 dry-run 仍用于准确反馈。其持久化 Attempt 后的 commit 可释放预检查锁；
   `_execute` 在实际写之前重新按同一顺序取得 Project／所有者锁，重新读获准拓扑图和
   同 Project 的既有反向依赖，按最终 delta 重跑 §5.1。这项检查不受 validate_shacl=false
   绕过；原工作区／lease 判断继续生效，不以预读结果替代最终检查。
3. canonical `apply_compiled_command`／`validate_compiled_command` 接入同一个映射完整性
   检查；合并 modeling_batch 无 item command_kind 时检查实际 delta，错误映射回原
   item／field。其 `commit=False` 必须把锁保留至外层 RDF 结果、图 revision、回执及
   `_finalize_success` 的 SQL 提交；在这个区间禁止先 commit／rollback 再继续 RDF 写。
   受锁保护的另一变更重新读取已提交状态后得到引用不存在或已有引用阻止删改，不能双双放行。
4. 会创建／修改映射资源、删改被声明依赖资源或清空对应业务／映射图的直接 canonical／
   `SemanticService.apply_edit`，使用已有 Batch／Attempt 的写入、fence 和恢复路径。
   无该执行上下文时，在任何副作用前返回可操作错误，要求通过既有批次工具提交；不能
   因调用 legacy／raw RDF 绕过完整性校验。无法投影为确定性 delta 的原始编辑同样反馈改用
   确定性命令，不在本条开发通用 SPARQL 编译器／导入框架。与映射无关的编辑保持原合同，
   但其改变共享定义／表字段后不能被误判为无关。生命周期清图／删除也先查已声明依赖；
   只收窄涉及模型完整性的删除，不扩成资源治理重设计。
5. 持 Project 锁期间检查现有未决 fence：非本 Attempt 的未决写入不得被视为稳定引用状态，
   返回可重试冲突并在尚未写入时按 `_fail_attempt_without_side_effects` 释放本次 fence。
   已写／可能写的失败保留原 fence，不清理资源或猜测成功。使用已有状态读取／reconcile
   确认之后再继续；不因并发等待或可重试冲突永久终结 semantic run。
6. `_resume_attempt`／reconcile 的 RDF重试与元数据收敛也取得相同 Project 锁；只允许本
   Attempt 穿过自己的 fence。rdf_already_applied 时按已记录 after／revision 证据确认已写结果，
   不能将重跑候选插入作为恢复。其他未决写入先安全收敛再重试，不新增自动 fresh start。

在实际实现中只抽出必要的确定性映射检查供 Batch 和 canonical 共用；Project 行锁直接复用
SQLAlchemy／已有模型，不引入泛化锁服务。原 `_execute` 确定性 pre-write 拒绝已支持无副作用
失败及释放自己的 fence，复用这一路径。旧锁顺序与 checkpoint 的所有者锁需要定向核对，
不能把新增 Project 锁放在已经持有 Ontology 锁的内层。

A7 增加可重复的交错提交检查：两个不同 Ontology 的 apply 都先取得各自预检查结果，随后
并发“新增引用／删除被引列”；最终仅允许保持引用完整性的一方应用，另一方准确拒绝并可
修订继续。再覆盖 direct-edit 无 Attempt 时拒绝绕过、校验后中间 commit 反例和未决 fence／
恢复持锁；这些是后续功能测试，不在本轮执行。

### 5.3 读取、展开与授权

- 列表／detail 模板、精确 resource 读取、导出和 mapping／metric producer 均投影新注解及
  明确引用；JSON 用既有规范格式，detail_fields.mapping_definition 为对象。
- mappedDefinition、tableMapping 等 IRI 谓词天然是明确边；mapping_definition／join_path 的
  每个结构化引用按固定字段含义提供关联端点。复用 008 的 statement/resource 身份与展开流程，
  对 JSON 引用以主体 IRI＋谓词＋字段路径＋目标 IRI 形成稳定的派生关联标识，并保留字段路径；
  不把它伪装为已存独立业务 triple，不为发现字段名建业务分支。
- full 保留全部获准字段；compact 保留资源身份、业务含义／未知及可获准补读的明确引用，
  裁剪、预算和 cursor 复用 008。不因找到了 mapping 就将其语义完整性标为 complete。
- 所有嵌套引用和 source 定位进入原语义访问过滤；被隐藏结果不得产生专属提示、数量、cursor
  或存在性信号。公开自由文本不复制受限定义正文；保护集责任仍由管理面承担，不新增 NLP 防泄漏。
- source_key 和 Schema 版本不表示数据权限、连接可用或映射经验证。受限语义不可见时不退回
  原始 Schema 猜测；数据库数据访问由外部系统授权。
- 不增加 Evidence／lineage 字段或后台追溯采集，必要写入、版本和恢复记录保持既有合同。

## 6. Schema 变化与验证分段

source_key 稳定，schema_version 和 schema_source 说明映射依据。字段更名／编码调整先确认
是否保持业务含义：保持则重审后更新现有映射及依赖；改变业务含义则创建新定义／映射并明确
引用迁移。技术版本相同不证明含义一致；版本变化也不自动认为所有业务定义失效。
沿用 007 的当前定义＋重审，不加映射版本固定、自动 Schema diff、同步任务或迁移框架。

功能验收 A1—A9 用隔离 fixture：至少包含两源同名表、一个复合键／桥接路径、一个自关联、
一个同属性同代码不同字段含义、工单三条明细、两个相同工时值、单位／时间边界及受限嵌套引用。
断言输出和实际干预后的自修复路径，不仅检查 JSON 字段存在。真实依赖功能检查在后续开发授权
执行，不把 mock／计划摘要当作应用正确。

A10 归 [009 映射段](2026-10-02-r4-0-009-multiview-semantic-acceptance-design.md)：
先冻结获准业务资料、Schema、代表数据和问题范围；Consumer 从获准语义取得数据源、身份、
关联／度量／转换口径再生成 SQL；独立验收方比对代表行和实际数值。业务数据由外部工具处理，
数值结果与现有验收记录留在宿主测试材料，不作为 RDF 行实例或 Modeling 追溯包。
未知跨源执行条件不以单源 SQL 结果代替验证；源资料／授权不足则保留原因和未验证范围。
本轮不读真实业务数据、不调用 SQL、不开始 semantic modeling start。

## 7. 实施交接与检查边界

| 计划触点 | 必要增量 | 验收 |
| --- | --- | --- |
| semantic_command_compiler.py／modeling_handlers.py | mapped_definition、scoped enum、referenced join、mapping_definition／semantic_definition；准确主体、增改删语义 | A1—A7 |
| modeling_batches.py／semantic_canonical_write.py／semantic.py 及相关删图入口 | 共用确定性映射检查；Project→Ontology 锁顺序、最终重校验、既有 Attempt／fence 的拒绝／恢复边界；拓扑、列／角色闭合、编码唯一性和反向引用 | A2—A7 |
| protocol_mechanics.py／staged_decisions.py／活动 Protocol MCP 与 Team Runner | 两种候选映射语义、身份绑定、审批摘要／投影、依赖翻译、回执及读回识别；归档 p2a driver 不作为活动执行入口 | A7、A9 |
| 活动 authoring／modeling reference、Skill、Task 组装 | 同步中性字段与未知处理，不向 Modeling 暴露平台 IRI 或追溯职责；选定 009 映射段时组装 | A1、A9；A10 后续授权 |
| semantic_sparql_templates.py／semantic_read_model.py／semantic_context_query.py | 新投影／解码、两种 mapped 目标、明确引用展开、full／compact／cursor；专属读与 Context Query 一致 | A1、A4—A9 |
| semantic_access.py（仅发现覆盖缺口时） | 保证新载荷／派生关联端点进入现有嵌套引用过滤，不新增权限模型 | A8 |
| [REST 文档](../../reference/api.md)／[MCP 文档](../../reference/mcp.md) | 同步具体命令字段、受治理读回、错误、未知及不执行数据库边界 | A9 |

生产代码保持通用；上述工单／维修名称只在例子及 fixture。无需数据库 migration 或服务配置
变化；若实际代码事实与此前提冲突，只核对窄依赖并记录，不扩成数据源产品化。
未来开发按仓库要求补行为测试，后端 `uv run pytest` 全量通过后重启并验证服务；改活跃 Team
合同需运行相关合同及 Skill 校验；不改前端时不强加前端测试。本轮文档检查无需服务重启。
本轮不声称 GitNexus 图影响覆盖；仅文档变更、定向源码读取，后续实现再按 AGENTS 做必要影响分析。

## 8. 文档自查与独立方案审阅

首次及初审修订后的自查检查需求 F1—F7、D1—D10、A1—A10 与设计对应，96 个本地
链接／锚点、Markdown 围栏／表格／空白、条款编号及 git diff --check 均通过。
复审后仅回填状态与记录，最终检查再次核对相同项目；不代表实现或真实语义正确性。

用户已明确授权独立方案审阅及修订至 PASS。审阅 Agent 仅只读检查方案与代码事实，报告
Critical／High 和关键未确认假设，不修改文件、不执行测试、不调用数据库、不启动建模。
审阅 Agent：`/root/r4010_plan_review`，初审基线为 `9aa73d1` 上的这两份文档。

| 轮次 | 独立结论 | 发现与修订 |
| --- | --- | --- |
| Round 1 | REVISE，0 Critical／1 High；无待用户确认关键假设 | H010-01：跨 Ontology 引用预检查与 RDF 实写之间存在并发窗口。§4.6、§5.2 和实施触点补 Project 行锁顺序、最终正反向重校验、direct-edit／Attempt／fence／恢复边界；需求 F6、D7、A7 同步修订 |
| Round 2 | PASS，0 Critical／0 High；无待确认关键假设 | 同一独立 Agent 确认 H010-01 在方案层 FIXED，最终锁／重校验、直接编辑及恢复边界与 F6／A7 同步；未发现新增阻断 |

两轮均于 2026-10-02 完成。复审后只回填本节与需求状态，没有追加业务设计变动。
方案 PASS 仅证明可交接实施，不代表代码已修复、并发测试通过或真实映射语义验收 PASS。
