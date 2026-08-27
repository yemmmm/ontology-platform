# R3.0-003 纯语义 Ontology 与关系型 Schema 映射 — 功能设计

- 日期：2026-08-26
- 状态：plan review: **PASS**（第六轮窄幅复审通过，四条非阻塞小注已应用：先例模板名更正
  为 `entity-literal-facts`（`entity-detail` 是无占位符模板，勿作样式参照）、§6 补 MCP
  读面增量、候选载荷枚举显式列入 measure、测试计划完成门补 S3b）。修订历史：
  第一轮 H-1 读模型列投影透传、H-2 DSN/URL 拒绝门、缺省 `resource_types` 语义澄清；
  第二轮 H-A DSN 门改为字段作用域（豁免受 G1 形状 + G2/G6 存在性约束的 IRI 引用/定位
  字段，含 update/delete `*_iri` 与 `filters[].field` 两形态）、H-B `detail_fields` 并入
  授权扫描接线（引用无权资源整行隐藏）；第四轮三项 High——H-1 JSON 字面量内嵌 IRI 绕过
  授权（statements/export/context 面；修订：`semantic_access` 层新增通用 JSON 引用抽取
  helper，接入全部四个过滤点）、H-2 精确 IRI anchor 无法承载口径字段（修订：anchor
  降级为定位+分类面，四类新 rdf:type 映射 `mapping`/`metric` kind）、H-3 测试 fixture
  与 G2/G3 矛盾（修订：fixture 补全属性声明、表名一致限定、join 列闭合）；另按裁决将
  TableMapping update/delete 致 JoinMapping 悬空纳入 G3（原 §4.5 记录边界）。第五轮两项
  High——H-1 `/statements` 面永不包含映射语句（该面硬编码 asserted_data 图，
  `semantic_read_model.py` L308-312；语句级承载面更正为 export + context
  related/neighborhood，§3.5.5 重写）、H-2 `filter_candidate` 现状不扫候选 `data` 载荷
  （修订：候选载荷合同——`data` 必须携带 mapped_class/mapped_relation/mapped_property/
  grain 引用字段，helper 递归扫全 `data`，§3.5.4/§3.7）；确认项——内嵌字面量钉死
  `json.dumps` 规范形态（附录 A，`_literal_term(dict)` 存 Python repr 会致 helper 静默
  失配）、`detail_variables` 枚举补 `mapped_relation`/`mapped_property`、fixture
  join_path 载荷用分解形态；第五轮窄幅复审 PASS 后被第六轮推翻。第六轮三项 High——
  H-1 指标缺聚合目标字段（修订：新增 `op:metricMeasure`（值聚合必填，G2）与可选
  `op:valueExpression` 计算说明，§3.2(d)/§3.3/G1/G2）、H-2 已知稳定 IRI 无法保证精确
  读取完整字段（列表模板受 `default_limit` 截断且无 offset、MCP 工具无 `entity` 参数；
  修订：新增 4 个精确 detail 模板复用既有 `{entity_iri}` 占位符机制 + `entity` 参数，
  MCP `get_semantic_read_model` 增可选 `entity_iri`，§3.5.1/A3/A6）、H-3 指标 raw
  `table.column` 引用契约不自洽（无存在性校验、与两段式 `tableName` 矛盾；修订：收敛为
  属性 IRI 唯一形态，物理列经 TableMapping 由 R3.0-005 解析，§3.2(d)/§3.3/G1/G2）。
  审查范围含：读模型装饰机制、授权过滤接线、MCP 枚举派生、无 migration 结论、legacy
  合同隔离、守恒测试覆盖。已实现（2026-08-27）：独立测试 Round 2 PASS——Round 1 发现两项缺陷均已修复：① 8 个新模板
  命名空间硬编码为 `semantic/op/`（编译器实际写 `semantic/vocab/`）致真实运行 0 行，修复为经
  `config.DEFAULT_SEMANTIC_BASE_IRI` 派生的 `OP_VOCAB_PREFIX`（`_op_body()`）并补真实 Oxigraph
  执行级回归；② 既有平台缺陷窄修复（记录在案）：graph-set export 对 scope 声明但未写入的图
  未捕获 404 → 500，修复为 `graph_exists` 门控、缺图按空集。实现偏差（均已独立复核为非缺陷）：
  G3 合并视图需先投影同批 deletes、update_metric 对 measure 必需型聚合 fail-closed、detail
  模板以主变量绑定 `{entity_iri}`、同批 create+update 同资源由既有 `conflicting_item_effects`
  阻断、G5 逐 item finding。已知既有平台缺陷（本需求未引入，建议另立修复项）：legacy
  `mapping-list`/`import-graph-mappings` 模板与 Stage-2 写入侧存在同类命名空间错位（legacy
  合同逐字不变边界内不修）；export `turtle` 格式对单图数据返回空载荷（Oxigraph dump 落
  default graph、turtle 序列化排除 default graph；A5 未单独强制 turtle，不阻断本需求））
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-003（§4 表行 P0，概要设计待细化）
- 概要设计基线：
  `docs/delivery/designs/2026-08-25-v3-0-remaining-requirements-outline-design.md` §2、§4
- 冻结依赖合同：
  `docs/delivery/designs/2026-08-23-r3-0-004-semantic-knowledge-authorization-design.md`
  （保护集与"与不存在不可区分"呈现合同，本设计逐字复用、不改其代码语义）
- 共享测试计划：
  `docs/delivery/test-plans/2026-08-26-r3-0-003-relational-schema-mapping-test-plan.md`
- 交付边界：交付**平台通用**的关系 Schema 映射与指标定义的表达、写入、确定性校验和读取能力，
  全部作为稳定 IRI 语义资源（可被既有保护集引用）；验收使用领域风味 fixture，产品代码零领域分支。
  不实现 NL2SQL / SQL 执行（R3.0-005）、保护集存储与授权（R3.0-004，已完成）、真实场景建模
  （R3.0-006）

## 1. 目标

1. 平台新增一类通用语义资源：**关系 Schema 映射**（概念→表、属性→列与稳定业务标识、
   关系→外键/join path、枚举/状态值业务含义）与**指标定义**，每条资源具有独立稳定 IRI、
   存入 Ontology 图（RDF），可被查询、导出、挂证据，并可被 Project 级保护集显式引用。
2. 平台协议 Agent 可以在 Build Session / Modeling Batch 的 dry-run/apply 中以**确定性命令**
   （create/update/delete）创作这些资源，与现有 canonical 写路径（编译为 quads、SHACL 校验、
   不可变 Modeling Item）完全同轨。
3. 确定性校验门（无 LLM）：必填谓词齐全、目标 IRI 在 scope 内存在、join path 步骤引用的列
   在同一 Ontology 内有属性→列映射、payload 结构性拒绝凭证/连接串/业务行实例。
4. 读取面通用化：新增图限定的读模型模板（对齐 R3.0-007 的 `{graph_iris}` 合同），
   结构化语义上下文查询（context:query）新增 `mapping`、`metric` 资源类型；不新增任何
   领域专属路由。
5. 受保护映射/指标对无权主体的呈现逐字复用 R3.0-004 合同：精确请求与真不存在不可区分、
   宽范围无痕子集、SPARQL 通用 scope 错误——授权**判定逻辑与合同零改动**：新资源沿用
   `SemanticAccessView` 的 IRI 可见性判定；实现上新增一个通用 JSON 引用抽取 helper
   （`semantic_access` 层，第四轮 H-1）并接入既有过滤点（含 `detail_fields`，评审 H-B），
   比"一处接线"更多一层通用机制增强，但不新增任何授权决策规则（§3.7）。
6. 验收级消费冒烟：从授权语义上下文出发，消费方可**机械恢复**表/列/join/指标语义，足以解释
   SQL 的生成（本需求不生成 SQL）。

## 2. 非目标

1. 不实现 NL2SQL、SQL 生成或 SQL 执行适配器（R3.0-005）。
2. 不实现保护集存储、成员管理或主体授权（R3.0-004 已交付；本需求只产出**可被引用**的稳定
   资源 IRI）。
3. 不做真实工业售后场景建模（R3.0-006）；本需求验收全部使用 fixture。
4. 不做自动 Schema→语义生成（列名/样例分布不得自动变成业务规则，需求原文边界）。
5. 不做 Schema 演进/映射迁移策略、指标 DSL 或 SQL 模板表达（概要设计 §4.4 暂不细化项）。
6. 不改 legacy 目录映射两个既有概念（§3.1）；不迁移、不删除、不复用其词汇。
7. 不做跨 Project 任何能力；不做映射管理 UI；不做 join path 独立资源化（内嵌于映射资源，
   已冻结）；TableMapping update/delete 致既有 JoinMapping 悬空已纳入 G3 阻塞（第四轮
   裁决，§3.4），其余跨资源级联（如删除被映射引用的类/关系/属性）不做，见 §4.5 记录
   边界。

## 3. 功能合同

### 3.1 与既有两个 legacy "Mapping" 概念的边界（防混淆，先声明）

平台现存两个同名概念，均为**目录导入时代遗留**，与本需求的纯语义映射是不同对象，本设计
不触碰：

| 既有概念 | 位置 | 说明 |
| --- | --- | --- |
| `op:SemanticMapping`（RDF） | `compile_create_mapping`（`semantic_command_compiler.py` L1514）、读模板 `mapping-list` / `import-graph-mappings`（`semantic_sparql_templates.py` L418/L445）、命令 `create_mapping`/`update_mapping`/`delete_mapping`（`modeling_handlers.py` 白名单既有项） | 外部字段目录映射（externalField/targetType/joinKey/confidence/owner/sourceId/runId），面向 import run |
| `semantic_mappings`（PostgreSQL） | `SemanticMappingModel`（`repositories/models.py` L994）、`governed_mapping_lexical_candidates`（`semantic_retrieval.py` L1034） | Stage-3 遗留目录表，只读参与检索锚定 |

本需求新增词汇使用**独立类型名**（`op:TableMapping` / `op:JoinMapping` /
`op:EnumValueMeaning` / `op:MetricDefinition`）与独立命令名，二者合同（含既有
`mapping-list` 读模型响应）逐字不变。既有守卫
`modeling_handlers.validate_payload_shape` 对 `*mapping` 命令拒绝 `source_id`/`run_id`
字段（L374）——新命令命名以 `mapping` 结尾会被同一守卫覆盖，这是**有利的巧合**：结构上
杜绝把新映射误写进 import 图；新命令 payload 也不定义这两个字段名。

### 3.2 资源词汇（op: = `{semantic_base_iri}/vocab/`）

四类新资源，每条一个独立稳定 IRI（`ns.resource(kind, id)` → `{base}/{kind}/{id}`），
全部写入 Ontology 图 `graph/ontology/{ontology_id}`（与 class/relation type 同图，
TBox 层语义资源）：

**通用谓词（四类共用）**

| 谓词 | 值 | 说明 |
| --- | --- | --- |
| `rdf:type` | 各类型 IRI | 见下 |
| `op:id` | 字面量 | 平台资源 id（既有惯例） |
| `op:ontology` | IRI | 归属本体（既有惯例） |
| `rdfs:label` / `rdfs:comment` | 字面量 | 名称 / 描述（label 使 `entity-detail`/`resources/{iri}` 精确读取面天然覆盖新资源） |
| `op:schemaSource` | 字面量 | 所依据 Schema 版本/来源，create 必填；格式约束：**无 scheme 前缀**的路径/标签形态（如 `pg-ddl/2026-08-22/after_sales.sql`、`schema-dump-2026-08-22`）——含 `://`、scheme 前缀或 userinfo 形态的值被 DSN 拒绝门拒绝（§3.3，评审 H-A） |
| `op:semanticVersion` | 字面量 | 映射自身语义版本（建模团队维护），create 可选 |

**（a）概念→表映射 `op:TableMapping`**（IRI kind `table-mapping`）

| 谓词 | 值 |
| --- | --- |
| `op:mappedClass` | 概念类 IRI |
| `op:tableName` | 字面量，保守标识符（允许 `schema.table` 两段） |
| `op:columnMappings` | JSON 字面量：`[{"property_iri":…, "column":…, "role":"value"|"business_key"}]`；`role` 缺省 `value`；**至少一条 `business_key`**（稳定业务标识列，确定性校验门） |

**（b）关系→外键/join path 映射 `op:JoinMapping`**（IRI kind `join-mapping`）

| 谓词 | 值 |
| --- | --- |
| `op:mappedRelationType` | 关系类型 IRI（owl:ObjectProperty） |
| `op:joinDirection` | 字面量 `forward` / `reverse`（关系方向相对外键方向） |
| `op:joinPath` | JSON 字面量，**有序步骤数组**（多跳 = 多步）：`[{"from_table":…, "to_table":…, "from_columns":[…], "to_columns":[…]}]`；连接条件即每步的列等值配对（`from_columns[i] ↔ to_columns[i]`，两数组等长）；join path 内嵌，不单独成资源（已冻结决策） |

**（c）枚举/状态值业务含义 `op:EnumValueMeaning`**（IRI kind `enum-meaning`）

| 谓词 | 值 |
| --- | --- |
| `op:mappedProperty` | 属性 IRI |
| `op:enumValue` | 字面量（列中的原始值） |
| `op:businessMeaning` | 字面量（业务含义，人工确认口径） |

同一 Ontology 内 `(op:mappedProperty, op:enumValue)` 唯一（确定性去重门）。

**（d）指标定义 `op:MetricDefinition`**（IRI kind `metric`，新 canonical 资源 kind；当前后端
不存在任何 metric 资源类型，此为首个）

| 谓词 | 值 |
| --- | --- |
| `op:metricGrain` | JSON 字面量：粒度维度引用数组；**每项为属性 IRI**（G2 存在性校验；第六轮 H-3 收敛——不设 `"table.column"` raw 形态，物理列经 TableMapping 解析，归属 R3.0-005 消费方） |
| `op:metricTimeField` | 属性 IRI（G2 存在性校验；同上收敛） |
| `op:metricMeasure` | **聚合目标**属性 IRI（第六轮 H-1 新增）：`aggregation ∈ {sum, avg, min, max, count_distinct}` 时**必填**（`count_distinct` 的去重目标即此字段；纯 `count` 行数统计不要求、若给出仍按 G2 校验）；G2 存在性校验 |
| `op:valueExpression` | 字面量，可选：派生度量的最小化计算说明文本（如 `repairDuration = resolved_at − reported_at，单位小时`）——平台只存储不执行、不解析（R3.0-005 消费方解释）；作为自由文本落入 DSN/URL 拒绝门作用域（§3.3） |
| `op:metricFilters` | JSON 字面量：`[{"field":…, "operator":…, "value":…}]`；`field` 为**属性 IRI**（G2 存在性校验；第六轮 H-3 收敛，不设 raw 形态）；`operator` 为声明式 token 字符串（平台不理解其业务含义，不校验业务语义、不是 SQL 片段） |
| `op:metricAggregation` | 字面量，∈ `{sum, avg, count, count_distinct, min, max}`（平台中立枚举，未来可扩） |
| `op:nullValueRule` | 字面量，显式空值规则文本（必填，不得为空串——未确认含义必须写成显式文字，不得缺省） |
| `op:denominatorRule` | 字面量，显式分母规则文本（必填，同上） |

设计取舍：列清单、join path、过滤条件以**规范化 JSON 字面量**内嵌（先例：
`create_class` 的 `op:externalMapping` JSON 字面量）。换取：每个映射/指标仍是单主体、
单稳定 IRI 的资源（保护集按 IRI 引用即可生效），join path 不单独成资源，读取面一张
模板可整行取回，消费方机械解析。代价（列不可单独被 SPARQL 变量投影）记入 §4.6。

### 3.3 写入命令（canonical，12 个）

命名沿用平台 `create_/update_/delete_` 惯例；`update_*` 语义为逐谓词 delete+insert
（既有 mapping/operation 模式）；`delete_*` 删除该主体全部语句。

| 命令 | payload 字段（`*` 必填；`?` 可选） |
| --- | --- |
| `create_table_mapping` | `table_mapping_id?` `name*` `description?` `mapped_class_iri*` `table_name*` `column_mappings*` `schema_source*` `semantic_version?` |
| `update_table_mapping` | `table_mapping_id`｜`table_mapping_iri`（二选一*）`name?` `description?` `table_name?` `column_mappings?` `schema_source?` `semantic_version?` |
| `delete_table_mapping` | `table_mapping_id`｜`table_mapping_iri*` |
| `create_join_mapping` | `join_mapping_id?` `name*` `description?` `relation_type_iri*` `join_direction*`（`forward`/`reverse`）`join_path*` `schema_source*` `semantic_version?` |
| `update_join_mapping` / `delete_join_mapping` | 对应字段（同上模式） |
| `create_enum_meaning` | `enum_meaning_id?` `name*` `description?` `property_iri*` `enum_value*` `business_meaning*` `schema_source*` `semantic_version?` |
| `update_enum_meaning` / `delete_enum_meaning` | 对应字段 |
| `create_metric_definition` | `metric_id?` `name*` `description?` `grain*` `time_field*` `measure_property_iri`（`aggregation ∈ {sum,avg,min,max,count_distinct}` 时必填，`count` 可省）`value_expression?` `filters*`（可空数组）`aggregation*` `null_value_rule*` `denominator_rule*` `schema_source*` `semantic_version?` |
| `update_metric_definition` / `delete_metric_definition` | 对应字段 |

接入点（全部既有机械通路，无新协议面）：

1. `semantic_command_compiler.py`：12 个 `compile_*` + `_COMPILERS` 注册（共享 helper：JSON
   字面量规范化、标识符校验、引用解析）。
2. `modeling_handlers.py`：`RDF_COMMANDS`、`CREATE_RESOURCES`（create 命令的稳定 IRI 派生）、
   `ALLOWED_FIELDS` 逐命令白名单。
3. MCP：`MODELING_BATCH_COMMAND_KINDS` 由 registry 自动派生（`mcp/tools/modeling_batches.py`
   L28），平台协议 Agent 的 Modeling Batch 工具 schema **自动**获得新命令，无需新工具。
4. 命令经 Modeling Batch dry-run/apply 执行：编译 quads → 确定性校验（§3.4）→ SHACL 既有
   校验 → 不可变 Item 记录，与现有 RDF 命令完全同轨。

**结构性反凭证/反行实例/反连接串**（不依赖 LLM）：

- `ALLOWED_FIELDS` 白名单机械拒绝一切未定义字段（不存在 `password`/`connection_string`/
  `rows`/`sample_data` 等字段位）。
- `table_name`、`column` 等标识符字段必须匹配保守标识符正则
  （`^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)?$` 量级）——这约束标识符形状，但**不足以**拦截
  DSN/URL（评审 H-2：`name`/`description`/`schema_source`/`business_meaning`/
  `null_value_rule`/`denominator_rule` 与 `filters[].value`、grain 项都是自由字符串）。
- **DSN/URL 拒绝门（评审 H-2 新增、H-A 修订为字段作用域，确定性）**：12 个新命令的编译
  入口对 payload 内字符串值做 DSN/URL 检查，但**按字段作用域**而非全值全局——
  **豁免结构性 IRI 引用字段**（按 §3.3 字段表穷举）：`mapped_class_iri`、
  `relation_type_iri`、`property_iri`、`column_mappings[].property_iri`、grain/`time_field`/
  `measure_property_iri`/`filters[].field` 的属性 IRI 引用项（第六轮 H-3 收敛后这些字段
  **只有**属性 IRI 一种形态，不存在 raw 列引用豁免位），以及四个 update/delete 命令的
  `*_iri` 定位字段（`table_mapping_iri`/`join_mapping_iri`/`enum_meaning_iri`/`metric_iri`）。
  豁免条件统一写作"G1 形状校验 + G2/G6 scope 存在性校验"：create 侧引用字段由 G2 判定，
  update/delete 定位字段由 G6 判定（`resource_not_found`），二者存在性检查都封住 DSN 注入
  （DSN 字符串如 `postgresql://…` 不是 scope 内资源 IRI，过不了存在性校验）；而平台资源
  IRI 均为 `http://…` 形态（`semantic_base_iri`），全值全局的 `://` 规则会误杀全部合法
  IRI 引用（评审 H-A 指出第一版不可实现）。
  三条规则作用于**其余全部字符串值**：
  1. 含 `://` 子串（覆盖 `postgresql://`、`jdbc:postgresql://`、`http(s)://` 等一切
     scheme-bearing DSN/URL）；
  2. 匹配 scheme 前缀形态 `^[a-z][a-z0-9+.\-]*:`（如 `postgres:…`、`mysql:…`；
     `schema_source` 等字段因此必须用无冒号前缀形态，§3.2）；
  3. 匹配 userinfo 形态 `[A-Za-z0-9._%+-]+:[^@\s]+@[A-Za-z0-9.\-]+`（`user:pass@host`，
     凭证内嵌形态）。
  覆盖范围：自由文本字段（`name`/`description`/`business_meaning`/`null_value_rule`/
  `denominator_rule`/`schema_source`/`semantic_version`）、非 IRI 字面量字段
  （`enum_value`、`filters[].value`、表/列标识符），以及内嵌 JSON
  （`column_mappings`/`join_path`/`filters`/`grain`）中的**非 IRI** 字符串项
  （`column`、`from_table`、`operator` 等；其中的 `property_iri` 项按 IRI 引用豁免）。
  `filters[].field`、grain 项、`time_field`、`measure_property_iri` 的合法形态**唯一**：
  属性 IRI——统一走 G1 IRI 形状校验 + G2 存在性校验并豁免本门；`"table.column"` raw
  形态在第六轮 H-3 收敛中**移除**（非 IRI 字符串过不了 G1 IRI 形状校验，物理列解析归属
  R3.0-005 消费方经 TableMapping 完成），不存在无校验的豁免位。
  正则保守设计、**误杀优先于漏放**（fail-closed 方向）：非 IRI 自由文本中含 ASCII 冒号
  scheme 前缀的正常措辞会被拒绝，建模 Agent 须改写（如改用全角冒号或去冒号）；中文文本
  不受 scheme 正则影响。**残余风险评估（一句话）**：IRI 引用字段中伪装 userinfo 的
  `http://u:p@host/…` 无法通过 G2 存在性校验，非 IRI 字段中的 userinfo 形态被规则 3 捕获，
  向量闭合。需求原文"映射不得包含数据库密码、连接串"由此门与 G2 共同强制，不依赖
  `scan_domain_payload`（后者只覆盖平台 key/JWT/AWS/Bearer/凭证字段名，抓不到 DSN）。
- 内嵌 JSON（`column_mappings`/`join_path`/`filters`/`grain`）按**封闭 schema** 校验（键集合
  固定、类型固定），业务行实例（任意行数组）不符合形状即拒绝。
- 编译入口对整个 payload 复用 `scan_domain_payload`（`security/secrets.py`，平台既有密钥
  扫描器），命中即 `invalid_command_payload`——与 DSN 门互补：它覆盖平台密钥/JWT/Bearer/
  凭证字段名形态，DSN 门覆盖连接串/URL/userinfo 形态。

### 3.4 确定性校验门（dry-run/apply，全部阻塞级 finding）

| # | 门 | 判定 |
| --- | --- | --- |
| G1 | 必填谓词齐全、值形状合法 | 编译期 `InvalidCommandPayload` → `invalid_command_payload`。第六轮 H-1/H-3 增补：`aggregation ∈ {sum,avg,min,max,count_distinct}` 而 `measure_property_iri` 缺失 → 拒；grain 项/`time_field`/`measure_property_iri`/`filters[].field` 非 IRI 形态（含 `"table.column"` raw 形态）→ 拒（IRI 形状校验） |
| G2 | 目标 IRI 在 scope 内存在 | `mapped_class_iri` 是 scope 内类、`relation_type_iri` 是 scope 内关系类型、`property_iri` 是 scope 内属性、metric 的 grain 项/`time_field`/`measure_property_iri`/`filters[].field` 属性 IRI 引用同理（第六轮 H-1 把 measure 纳入）；判定在**合并视图**（当前图 + 本 Batch 已编译 inserts）上进行——同批先 `create_class` 后 `create_table_mapping` 必须通过。失败 → `invalid_resource_reference` |
| G3 | join path 列闭合（正向 + 反向） | **正向**（create/update JoinMapping）：每步 `from_table`/`to_table` 必须是同一 Ontology 内某 `op:TableMapping` 的 `op:tableName`（含同批新建），且该步每个 `from_columns`/`to_columns` 元素出现在对应 TableMapping 的 `columnMappings` 中；多跳相邻步骤 `to_table(i) == from_table(i+1)`；`from_columns`/`to_columns` 等长非空。**反向**（第四轮裁决，update/delete TableMapping）：若修改会使**既有** JoinMapping（store 已存在或同批）的 join path 悬空——删除 TableMapping、修改 `table_name`、或从 `column_mappings` 移除/改名被 join 引用的列——阻塞；纯新增列/新增 TableMapping 不阻塞。失败 → `join_path_not_mapped` |
| G4 | 业务标识列存在 | TableMapping 的 `column_mappings` 至少一条 `role=business_key`。失败 → `invalid_command_payload` |
| G5 | 枚举含义唯一 | 同 Ontology 内 `(property_iri, enum_value)` 不重复（含同批）。失败 → `resource_already_exists` |
| G6 | create 幂等冲突 / update/delete 目标存在 | create 撞已有 IRI → `resource_already_exists`；update/delete 目标不存在 → `resource_not_found`（对齐 operation 命令在 `_validate_candidate_delta` 的既有模式） |
| G7 | 反凭证/反行实例/反连接串（§3.3 五条，含**字段作用域** DSN/URL 拒绝门——豁免受 G1 形状 + G2/G6 存在性约束的 IRI 引用/定位字段（含 update/delete `*_iri`），其余全部字符串值含内嵌 JSON 非 IRI 字符串；IRI 引用/定位字段中的 DSN 由 G2/G6 封住；`filters[].field` 等指标引用字段第六轮 H-3 后唯一 IRI 形态、显式校验） | `invalid_command_payload` |

实现位置：`modeling_batches.py` 新增一个 `_validate_relational_mapping_commands` 阶段
（模式对齐既有 `_validate_candidate_delta` 的 operation 分支与 `_validate_rule_command`），
在合并视图上执行；编译器内完成纯 payload 形状部分。无任何 LLM 调用。

### 3.5 读取面（全部通用，零领域路由）

1. **新读模型模板 ×8 = 列表 ×4 + 精确详情 ×4**（`semantic_sparql_templates.py`）：
   列表——`table-mapping-list`、`join-mapping-list`、`enum-meaning-list`、`metric-list`；
   精确详情——`table-mapping-detail`、`join-mapping-detail`、`enum-meaning-detail`、
   `metric-detail`（第六轮 H-2 新增）。模板体**必须**含
   `VALUES ?g { {graph_iris} }`（R3.0-007 冻结教训；其守恒测试遍历 `list_templates()` 自动
   约束新模板）。`required_roles=("asserted_ontology",)`、`primary_iri_variable` 各自指向
   主体变量、投影全部谓词列。经既有
   `GET /api/semantic/graph-sets/{id}/read-models/{model_name}` 与 MCP
   `get_semantic_read_model` 按名消费——模板注册即暴露，无新路由。
   **为什么必须有精确详情模板（第六轮 H-2）**：列表模板受 `default_limit` 截断（
   `bounded_limit = min(limit or template.default_limit, template.default_limit)`，请求
   `limit ≤ 2000` 且无 offset 分页参数，`semantic_read_model.py` L200/L237；HTTP 路由
   `semantic.py` L1570-1580），资源落在列表窗口之外时，已持有稳定 IRI 的消费方**无法**经
   列表取回字段——S8/A6 不能建立在"扫描列表"上。精确详情模板复用既有机制：模板体含
   `{entity_iri}` 占位符 + `VALUES ?subject { <{entity_iri}> }`（`entity-literal-facts`
   先例——`semantic_sparql_templates.py` L361-402；注意 `entity-detail` 本体（L89-106）
   是无占位符的 label 扫描模板，勿作样式参照，第六轮小注更正），
   由既有 `entity` 查询参数驱动——
   `_compile_template_query`（`semantic_read_model.py` L295-312）在占位符存在而参数缺失时
   报错（400），替换为该 IRI 的精确匹配；无 `LIMIT` 窗口问题（单主体至多一行）、无新路由、
   无共享代码改动（占位符机制原样复用）。四个 detail 模板复用与列表模板相同的投影与
   `detail_variables` 声明、走相同装饰/授权路径。MCP 补齐：`get_semantic_read_model`
   （`mcp/tools/semantic.py` L562）现无 `entity` 参数，新增可选 `entity_iri: str | None =
   None` 透传 service（纯尾部默认参数，既有调用行为不变）。
2. **读模型列投影透传（`semantic_read_model.py` 增量机制，评审 H-1）**：现行
   `_decorate_row` / `_graph_display_fields`（`semantic_read_model.py` L338-408）只把固定
   变量白名单（semantic_id/parent/class/class_label/source/target/relation/range/type/
   evidence_status/subject/predicate/object 等，别名 L51-55）装饰进响应项，其余 SELECT
   变量被静默丢弃（先例：legacy `mapping-list` 投影的 `?external_field`/`?join_key` 等
   从未出现在读模型 HTTP 响应中）。因此仅新增模板**不足以**让映射字段出现在响应里。设计：
   `ReadModelTemplate` 增加可选 `detail_variables: tuple[str, ...] = ()` 声明；行装饰阶段把
   声明过的非白名单投影变量**增量透传**进响应项的稳定子对象 `detail_fields`（变量未绑定
   时省略键）；白名单变量的现行顶层形状与装饰路径**零改动**。默认 `detail_variables=()`
   使全部既有模板（含 legacy `mapping-list`）响应**逐字节不变**，并以回归测试钉死；八个
   新模板（列表 + 精确详情，成对共享列声明）各自声明其谓词列
   （`table_name`/`mapped_class`/`column_mappings`/`join_direction`/
   `mapped_relation`/`join_path`/`enum_value`/`mapped_property`/`business_meaning`/指标字段
   （grain/time_field/measure/filters/aggregation/value_expression 等）/`schema_source`/
   `semantic_version`——第五轮
   补全 `mapped_relation`（JoinMapping 引用关系类型）与 `mapped_property`（EnumValueMeaning
   引用属性）两列）。
   **授权接线（评审 H-B，必选）**：`filter_items` 现状只扫描响应项的**浅层字符串值**
   （`semantic_read_model.py` L66-81，`_term_unauthorized` 对 dict 返回 False），顶层白名单
   变量（class/source/target 等字符串 IRI）满足 R3.0-004"引用无权资源须整体隐藏"合同，但
   嵌套 `detail_fields` dict 对扫描不可见——公共映射行可在 `detail_fields.mapped_class`
   中泄露受保护类/关系/属性 IRI。设计：`semantic_access` 层新增**通用 JSON 引用抽取
   helper**（第四轮 H-1：JSON-parse 字符串值、递归抽取 IRI 形态叶子、与无权保护成员集合
   精确匹配），装饰/过滤时把 `detail_fields` 的值（字符串与内嵌 JSON 中的字符串递归
   展开）经该 helper 并入 `access_view` 的词条可见性判定
   （`any_unauthorized`/`is_member_visible`）——其值引用任一无权保护成员的行**整行隐藏**，
   与顶层变量同一合同；不改模板投影设计（composer 分支 L111-199 自组装响应项、绕过
   `_decorate_row`，八个新模板均为非 composer 模板，不受影响）。
3. **精确 IRI 读取（定位面，非字段面）**：新资源带 `rdfs:label`，既有 `entity-detail`
   模板 + `GET /api/semantic/resources/{iri}` 能按 IRI **定位**资源（R3.0-007 修复后该面
   图限定正确），但该面响应只回 label（`properties={}` 形态），**不携带映射字段**。字段
   承载面是列表与精确详情模板（§3.5.1/3.5.2 的 `detail_fields`，消费方持 IRI 时应走
   detail 模板，第六轮 H-2）；context:query 精确
   anchor（§3.5.4）同为定位+分类面，不载口径字段（第四轮 H-2）。
4. **结构化语义上下文查询**（`semantic_context_query.py`）：`RESOURCE_TYPE_ORDER` 追加
   `"mapping"`、`"metric"`（追加在尾部，不扰动既有 kind 排序）；候选源新增
   `_mapping_candidates`（label、`tableName`、`enumValue`、`businessMeaning` 的词法锚定，
   模式对齐 `_operation_candidates` 先例：图 scope 显式注入）与 `_metric_candidates`
   （label/comment）。**候选载荷合同（第五轮 H-2）**：映射/指标候选的 `data` 载荷**必须
   携带**其引用字段（`mapped_class`、`mapped_relation`、`mapped_property`、grain/time_field/
   measure 引用等，IRI 形态），使消费方可见引用拓扑；相应地 `filter_candidate` 的通用 JSON 引用
   抽取 helper **递归扫描候选整个 `data` 载荷**（现行实现只扫 `id`/`iri`/语句位/
   `mapping_evidence`，不够——候选 `data` 携带无权引用 IRI 时候选项必须整体隐藏，见
   §3.7）。`api/schemas.py` 的 `resource_types` Literal 同步扩枚举；MCP 参数本为通用
   `list[str]`，无需改。映射语句作为普通语句同样进入 related/neighborhood 展开
   （`op:mappedClass` 等是普通谓词，通用语句管线自动覆盖）。
   **精确 IRI anchor（定位+分类面，第四轮 H-2 降级）**：现行 `_anchor_candidate_from_rows`
   按资源 rdf:type 分类（如 Operation 取 local-name），未识别类型落入 "instance" 且只携带
   rdf_types/label 证据。设计：四类新 rdf:type（`op:TableMapping`/`op:JoinMapping`/
   `op:EnumValueMeaning`/`op:MetricDefinition`）映射为 kind `mapping`/`metric`（local-name
   判定对齐 Operation 先例），使精确 IRI anchor 能**定位**新资源并**正确分类**；anchor
   **不返回任何口径字段**（其数据结构只携带 rdf_types/label 证据，结构上装不下
   `detail_fields`），字段承载面是列表与精确详情模板（§3.5.2，第六轮 H-2）。anchor 对无权主体走既有
   `anchor_not_found` 同不存在合同（§3.7）。
   **默认语义（评审澄清，H-3）**：`resource_types` 缺省时选中**全部**类型
   （`semantic_context_query.py` L260 既有行为），因此缺省请求在本交付后**会**包含
   mapping/metric 候选——这是**有意**的增量默认行为（R3.0-005 消费链路受益），不是回归；
   显式传入旧六类型的请求保持与实现前结构等价。
5. **export（语句级读取面）与 statements 面边界（第五轮 H-1 更正）**：`/api/semantic/
   statements`（`statement-list` 模板）经 `_graph_iris_for_scope` **硬编码只读
   `asserted_data` 角色成员图**（`semantic_read_model.py:308-312`），而映射/指标语句写入
   ontology 图（`asserted_ontology` 角色）——**映射语句不出现在 `/statements` 面，对任何
   主体（含授权主体）都不出现**；本交付不扩大 `statement-list` 的图选择（那会改变既有面
   合同）。映射/指标的**语句级读取面**是：①graph-set **export**（双图覆盖，
   `semantic_graph_set_export.py` 用 `source_graph_iris` = asserted_ontology +
   asserted_data）；②context:query 的 related/neighborhood 语句项（scope 图集含 ontology
   图）。export 面接线：`filter_quads`（对象 JSON 字面量内嵌无权 IRI 经通用 helper 整
   quad 隐藏，第四轮 H-1）。

### 3.6 Schema 版本/来源与证据

- 版本/来源：§3.2 通用谓词 `op:schemaSource`（create 必填）与 `op:semanticVersion`（可选）
  ——满足需求"语义版本与所依据 Schema 版本/来源的关联"。
- 证据绑定：Modeling Batch Item 的 `evidence_reference_ids` / inline `evidence` 是
  **命令无关**的通用机制（`_validate_evidence_and_questions` 已对任意命令校验并关联
  EvidenceReference）。映射/指标 Item 携带证据即被既有机制解析、持久化并在证据面可见，
  **零新机制**。

### 3.7 授权与呈现（逐字复用 R3.0-004 冻结合同）

新资源 IRI 可直接加入 Project 级保护集（悬空 IRI 亦合法，先保护后创建推荐）。无权主体的
呈现由既有 IRI 通用过滤保证——授权**判定逻辑、公式、合同、错误路径零改动**；实现上新增
一个 `semantic_access` 层的**通用 JSON 引用抽取 helper**（第四轮 H-1：JSON-parse 字符串
值、递归抽取 IRI 形态叶子、与无权集合精确匹配）并接入既有四个过滤点——`filter_items`
（含 `detail_fields` 值，评审 H-B）、`filter_statement_rows`、`filter_quads`、
`filter_candidate`（context:query 融合前）。这是通用机制增强而非新增授权决策规则：

- 精确请求：`resources/{iri}` 走 entity-detail → `access_view.filter_items` → 同一 404 路径，
  与真不存在逐字节一致（R3.0-004 §5.1 同目标对照基准）。该面是定位面（响应只回 label，
  §3.5.3）；字段承载面（新列表模板 `detail_fields` 无痕消失）与定位面（context:query
  anchor `anchor_not_found` 同不存在合同，定位+分类不载字段，第四轮 H-2）的授权等价
  断言都在测试计划 F3。
- 新列表模板：`SemanticReadModelService` 既有 `access_view.filter_items`（行过滤在
  limit/截断前，`_FILTERED_FETCH_LIMIT` 超额取回）——受保护映射行无痕消失；且**行本身
  公开但 `detail_fields` 引用了无权保护成员 IRI（如受保护类/关系/属性）时，该行按同一
  合同整行隐藏**（§3.5.2 接线，评审 H-B），不从 `detail_fields` 部分删值。
- context:query：候选过滤在融合/分页/cursor 前（`filter_candidate`，同经通用 helper——
  **递归扫描候选整个 `data` 载荷**：候选自身 IRI、语句位、内嵌 JSON 引用、以及 `data`
  中的引用字段（`mapped_class` 等）任一命中无权成员即整候选隐藏，第五轮 H-2）；精确 IRI
  anchor 走 `anchor_not_found` 同不存在合同。
- export（语句级读取面，第五轮 H-1 更正——`/statements` 面只读 asserted_data 图、不含
  映射语句，见 §3.5.5）：`filter_quads`（s/p/o 任一命中即隐藏——受保护映射作为 object
  被引用的语句整体隐藏；**对象 JSON 字面量内嵌无权 IRI 经通用 helper 同样隐藏**——公共
  映射语句不得因内嵌引用泄露受保护类/关系/属性，第四轮 H-1）。`filter_statement_rows`
  的 helper 接入保留（防御性，asserted_data 图行不含映射语句，不构成行为变化）。
- SPARQL：scope 与无权保护成员交集非空 → 既有通用 `scope_not_ready` 整体错误。

## 4. 错误与边界

### 4.1 校验失败（dry-run/apply）

§3.4 各门产生阻塞级 finding，Batch 进入 `validation_failed`，apply 拒绝；finding 归因到
具体 `client_item_id`（`path` 指向违规字段）。错误码全部为上述既有风格码，不新增 4xx 语义。

### 4.2 受保护映射/指标（R3.0-004 合同，逐字复用）

无权主体在任何读取面**不得**通过结果、warning、cursor、total、计数、排序或错误细节感知
受保护映射/指标/枚举含义的存在；语义知识读取面不出现 403/`forbidden`；跨 Project 仍按
`forbidden_scope` 项目边界合同。本需求验收在 R3.0-004 既有用例全绿的前提下，为新资源类型
补齐同基准等价断言（见测试计划 B 组）。

### 4.3 多跳 join 与方向

join path 是有序步骤数组，≥1 步、支持多跳；方向由 `op:joinDirection` 相对关系方向声明。
消费方按步骤顺序机械拼接；相邻步骤表不衔接（G3）在写入期拒绝，不留到读取期。

### 4.4 悬空目标与空值/分母

- 引用的类/关系/属性 IRI 不在 scope（G2）→ 阻塞；不允许"先应用后补"。
- 指标空值/分母规则是**必填显式文本**：未确认的口径必须以文字写明（如"分母口径未与业务
  确认，暂按全部工单计"），不得以缺省值静默通过——对应"未确认的业务含义必须保持显式未知"。

### 4.5 已记录边界（不修，不判 FAIL）

- **其余跨资源引用完整性**（TableMapping↔JoinMapping 的悬空已由 G3 反向闭合覆盖，第四轮
  裁决）：删除或改名被映射引用的类/关系类型/属性不做级联阻断——G2 只在写入映射命令时
  校验存在性，本体侧 TBox 变更不回溯阻断（产品化方向见 §8）。
- 列/连接条件内嵌 JSON 字面量：SPARQL 不能对单列做变量级投影/过滤；需要列级查询时消费方
  解析 JSON（消费冒烟证明可行）。列级独立资源化属未来产品化。
- 遗留 `mapping-list` / `import-graph-mappings` 模板与 `create_mapping` 命令保持原样。

### 4.6 平台/参考本体边界

表名、列名、指标名、join 步骤全部是**本体数据**；平台不解释其业务含义（operator token、
分母规则文本原样存取）。领域风味名称只允许出现在 fixture 与断言（CLAUDE.md 边界规则）。

## 5. 对 R3.0-002 建模流程与 R3.0-005 消费链路的衔接

- **R3.0-002（上游）**：多切片建模流程中的平台协议 Agent 在同一 Build Session / Modeling
  Batch 内把批准的映射/指标候选转为 `create_*` 命令（与 class/relation 命令混排、同批
  dry-run/apply）；切片场景地图中的"保护 IRI 建议"可直接指向新资源 IRI（保护集操作独立于
  Batch，先保护后创建推荐，R3.0-002 §3.4 合同不变）。R3.0-002 的三角色边界、机械增量验收
  不受影响——本需求只是为其白名单增加命令族。
- **R3.0-005（下游）**：Consumer Agent 从授权语义上下文（口径字段承载面是列表与精确详情
  读模型模板的 `detail_fields`——已知稳定 IRI 时走 detail 模板，不依赖列表窗口，第六轮
  H-2；指标还含 `measure` 聚合目标与可选 `value_expression` 计算说明，第六轮 H-1；
  context:query 的 mapping/metric 类型、精确 anchor 与
  `resources/{iri}` 均为定位+分类面，不载字段，§3.5.3/§3.5.4）机械取得：概念的表与业务标识列、属性列、关系的方向与
  join 步骤、指标的度量目标/粒度/时间字段/过滤/聚合/空值与分母规则——这正是"生成可解释 SQL 并说明
  所用业务口径"所需的全部语义输入。本需求不生成 SQL；语义不足时 Consumer 返回无法确认的
  合同由 R3.0-005 自行实现。
- **R3.0-006（验收）**：真实建模产生的映射/指标即本词汇的实例；RDF 不存业务行实例由
  §3.3 结构性反行实例门与既有扫描器共同保证。

## 6. 发布影响

- **无数据库 migration**（已核实）：新资源只写入 RDF（Ontology 图）；Modeling Item 的
  `command_kind`/payload 是自由 JSON 列；新命令、模板、context 类型全部是代码级注册。
  PostgreSQL 零新表、零新列。
- 改动集中在 `backend/app/services/`（compiler、handlers、templates、
  **`semantic_read_model.py` 的 `detail_variables` 增量透传（§3.5.2）**、context query、
  modeling batch 校验）、`backend/app/api/schemas.py` 一个 Literal 枚举，以及
  `backend/app/mcp/tools/semantic.py` 的 `get_semantic_read_model` 增可选 `entity_iri`
  参数（第六轮 H-2，尾部默认透传，纯增量）；前端无必需改动。
- 按 CLAUDE.md：`cd backend && uv run pytest` 全绿 → `systemctl --user restart
  ontology-platform.service` → `/api/health` 与 `:5173/` 健康检查 → live 冒烟
  （真实 Batch apply + 授权双 key 读取，见测试计划 L 组）。
- 回滚：无存储格式变更，revert 代码即回滚；已写入的映射资源成为普通 RDF 语句，读取面回到
  未知模板 404（既有合同），无破坏性残留。

## 7. 验收标准（详见共享测试计划）

| ID | 标准 |
| --- | --- |
| A1 | 12 个命令在 Modeling Batch dry-run/apply 中确定性执行：编译 quads 正确、同批依赖（先类后映射）通过、Item 状态与不可变记录与现有 RDF 命令一致 |
| A2 | G1–G7 校验门各有正反用例（G3 含正向 join 闭合与反向 TableMapping update/delete 悬空阻断，第四轮裁决）；全部为确定性校验，代码中无 LLM 调用（grep 门） |
| A3 | 8 个新读模型模板（列表 ×4 + 精确详情 ×4，第六轮 H-2）全部含 `VALUES ?g { {graph_iris} }`（守恒测试自动覆盖）；**已知稳定 IRI 的资源即使落在列表默认窗口之外，也能经 detail 模板 + `entity` 参数取回全部 `detail_fields`**；跨 Project 数据不混入（R3.0-007 回归形态）；新模板经 `detail_fields` 透传返回全部谓词列，且**全部既有模板响应逐字节不变**（含 legacy `mapping-list`，回归门）；detail 模板缺 `entity` 参数 → 400 |
| A4 | context:query 支持 `mapping`/`metric` 资源类型：宽词与精确 IRI 命中；精确 anchor 正确**分类**为 `mapping`/`metric` kind 且**不返回口径字段**（定位+分类面，第四轮 H-2；字段由 A3 的 `detail_fields` 承载）；排序稳定；显式传入旧六类型的请求与实现前结构等价（回归）；缺省（不传 `resource_types`）请求按既有"全类型"语义**包含** mapping/metric 候选（记录在案的增量默认行为，评审澄清） |
| A5 | 授权：受保护映射/指标/枚举含义对无权主体在精确 IRI、列表模板（含 `detail_fields` 无痕消失，及**公共行的 `detail_fields` 引用受保护类/关系/属性 IRI 时整行隐藏**，评审 H-B）、context:query、export、SPARQL 各面与真不存在不可区分（同目标对照逐字节等价）；`/statements` 面对任何主体均无映射语句（asserted_data 硬编码，§3.5.5），只做负向断言、不做不可区分正断言；R3.0-004 测试计划既有用例全绿 |
| A6 | 消费冒烟：仅凭授权读取面（口径字段由读模型模板 `detail_fields` 承载——已知 IRI 走精确 detail 模板（第六轮 H-2），context:query 宽词/anchor 仅用于定位与分类；无直连数据库），消费方机械恢复概念→表/列/业务标识、关系→方向/join 步骤、指标度量目标/粒度/时间字段/过滤/聚合/计算说明等全部口径字段，并组装出足以解释 SQL 生成依据的结构化说明 |
| A7 | 结构性反凭证/反行实例/反连接串：字段白名单外键、标识符正则、封闭 JSON schema、`scan_domain_payload`、字段作用域 DSN/URL 拒绝门（`://`、scheme 前缀、`user:pass@host`，作用于自由文本/非 IRI 字面量/内嵌 JSON 非 IRI 字符串）各有拒绝用例；IRI 引用/定位字段（含 update/delete `*_iri` 与 `filters[].field` IRI 形态）中的 DSN 由 G2/G6 存在性拒绝（负向断言，向量闭合）；合法 IRI 引用（create 侧与 update/delete 定位）不被 DSN 门误杀 |
| A8 | 证据绑定：映射/指标 Item 携带 `evidence_reference_ids` 经既有机制关联并可在证据面读取 |
| A9 | 遗留合同不变：`create_mapping` 命令族、`mapping-list`/`import-graph-mappings` 模板、PG `semantic_mappings` 检索锚定行为逐字回归 |
| A10 | `cd backend && uv run pytest` 全量通过；服务重启 + 健康检查 + live 冒烟通过 |

## 8. 当前最小实现范围 vs 未来产品化

**当前最小实现范围**（本交付完成门）：

- §3.2 四类资源词汇与 §3.3 十二个命令；
- §3.4 七个确定性校验门；§3.3 反凭证四条；
- §3.5 八个图限定读模板（列表 ×4 + 精确详情 ×4，第六轮 H-2）+ context:query 两个新
  资源类型 + `api/schemas.py` 枚举扩展；
- §3.6 版本/来源谓词与既有证据机制复用；
- 配套 pytest 与 live 冒烟（测试计划）。

**未来产品化**（明确不在本完成门，不得静默晋升）：

- 删除/更新被映射引用的类/关系/属性时的级联阻断（TableMapping↔JoinMapping 悬空已由 G3
  当前覆盖）、悬空映射 lint 与告警；
- join path / 列级独立资源化与列级 SPARQL 投影；
- 指标 DSL、SQL 模板表达、指标版本谱系与血缘展开；
- Schema 演进/映射迁移、自动 Schema→语义辅助生成；
- 数据源注册、连接治理（本需求结构上禁止连接信息进入本体，未来若需要属平台控制面，另行
  需求与架构决策）；
- 映射管理 UI、跨 Project 映射复用。

## 9. 假设（错误则需重设计）

1. **读模型行级授权过滤（含 H-B 接线与 H-1 通用 JSON 引用抽取）对新模板及语句面生效**：
   `SemanticReadModelService` 对非 composer 模板统一走 `access_view.filter_items`（超额
   取回后先过滤再截断），`detail_fields` 值经通用 helper 并入词条可见性扫描后，嵌套引用
   与顶层变量满足同一整行隐藏合同；且同一 helper 在 `filter_statement_rows`/
   `filter_quads`/`filter_candidate` 上行为一致（JSON-parse + IRI 叶子精确匹配，不误伤
   未受保护的 IRI）。若某新模板因投影形状需要 composer 式执行（自组装响应项、绕过
   `_decorate_row`），其过滤注入点不同，A5 的模板面断言需重新设计。
2. **`detail_variables` 透传可按模板选入且与白名单装饰路径隔离**（评审 H-1 已证实现状：
   白名单装饰在 `_decorate_row`/`_graph_display_fields`，其余变量被丢弃；`resources/{iri}`
   面只回 label）。若装饰路径与 composer 模板共享到无法按模板选入、或白名单行为被迫
   全局改变，透传机制需重新设计（既有模板逐字节回归门是硬约束）。
3. **缺省 `resource_types` 的增量默认变更是被接受的合同变更**（评审澄清确认）：缺省
   （不传）请求将包含 mapping/metric 候选（`semantic_context_query.py` L260 缺省全选的
   既有语义）；只有显式传入旧六类型的请求承诺与实现前结构等价。若后续被判定为破坏性
   默认变更（需要缺省排除新类型），候选源需改为显式 opt-in，机制重设计。

（次要、已核实不构成重设计风险：MCP 命令枚举自动派生自 registry；Modeling Item
`command_kind` 为自由字符串列；`*mapping` 命令名的 `source_id`/`run_id` 守卫对新命令无害
且有利。）

## 附录 A 技术要点（文件级，非主线）

| 文件 | 改动 |
| --- | --- |
| `backend/app/services/semantic_command_compiler.py` | 新增 `compile_create/update/delete_{table_mapping,join_mapping,enum_meaning,metric_definition}` 共 12 个 + 共享 helper（标识符正则、引用项渲染、`scan_domain_payload` 入口调用）；`_COMPILERS` 注册。**内嵌字面量规范化钉死（第五轮确认）**：新命令的 JSON 载荷（`column_mappings`/`join_path`/`filters` 等）一律以 `json.dumps(payload, ensure_ascii=False)` 的规范字符串形态落 RDF，**禁止复用 `_literal_term(dict)`**——现状该路径存 Python repr（`semantic_command_compiler.py` L96-104、L372-382，legacy `op:externalMapping` 先例即 repr 形态），repr 不是合法 JSON，授权层 JSON 引用抽取 helper 会静默失配，内嵌引用 IRI 将绕过可见性过滤 |
| `backend/app/services/modeling_handlers.py` | `RDF_COMMANDS` +12；`CREATE_RESOURCES` +4（`table-mapping`/`join-mapping`/`enum-meaning`/`metric` 的稳定 IRI 派生）；`ALLOWED_FIELDS` +12 条目 |
| `backend/app/services/modeling_batches.py` | 新增 `_validate_relational_mapping_commands`（G2/G3/G5/G6 的合并视图判定，G3 含 TableMapping update/delete 对既有 JoinMapping 的反向悬空检查（store 或同批）；模式对齐 `_validate_candidate_delta` 的 operation 分支），挂入既有校验序列 |
| `backend/app/services/semantic_sparql_templates.py` | +8 模板：列表 ×4——`table-mapping-list`、`join-mapping-list`、`enum-meaning-list`、`metric-list`；精确详情 ×4（第六轮 H-2）——`table-mapping-detail`、`join-mapping-detail`、`enum-meaning-detail`、`metric-detail`（含 `{entity_iri}` 占位符 + `VALUES ?subject { <{entity_iri}> }`，复用 `entity-literal-facts` 机制）；均含 `VALUES ?g { {graph_iris} }`，`required_roles=("asserted_ontology",)`，各自声明 `detail_variables` |
| `backend/app/services/semantic_read_model.py` | `ReadModelTemplate` 增可选 `detail_variables: tuple[str, ...] = ()`（frozen dataclass 尾部默认值字段，纯增量）；行装饰阶段（`_decorate_row`/`_graph_display_fields` 路径）把声明的非白名单投影变量增量透传进响应项 `detail_fields` 子对象（未绑定省略键）；白名单装饰路径与既有模板默认行为零改动（逐字节回归门）；**授权接线（评审 H-B）**：过滤时把 `detail_fields` 值（含内嵌 JSON 字符串递归展开）经 `semantic_access` 通用 JSON 引用抽取 helper（第四轮 H-1）并入词条可见性判定，引用无权保护成员 IRI 的行整行隐藏；composer 分支（L111-199）不动 |
| `backend/app/services/semantic_access.py` | 新增**通用 JSON 引用抽取 helper**（第四轮 H-1：JSON-parse 字符串值、递归抽取 IRI 形态叶子、与无权保护成员集合精确匹配），接入 `filter_items`/`filter_statement_rows`/`filter_quads`/`filter_candidate` 四个既有过滤点；`filter_candidate` 的扫描范围按第五轮 H-2 从 `id`/`iri`/语句位/`mapping_evidence` 扩为**递归扫描候选整个 `data` 载荷**（候选 `data` 携带无权引用 IRI 时候选整体隐藏）；授权判定逻辑、公式与合同零改动 |
| `backend/app/services/semantic_context_query.py` | `RESOURCE_TYPE_ORDER` 追加 `"mapping","metric"`；`_mapping_candidates`/`_metric_candidates`（对齐 `_operation_candidates`：图 scope 注入、精确 label 优先、access filter 在融合前；候选 `data` 载荷必须携带 `mapped_class`/`mapped_relation`/`mapped_property`/grain/time_field 等 IRI 形态引用字段，第五轮 H-2）；**anchor 分类扩展（第四轮 H-2）**：`_anchor_candidate_from_rows` 对四类新 rdf:type（`op:TableMapping`/`op:JoinMapping`/`op:EnumValueMeaning`/`op:MetricDefinition`）映射 kind `mapping`/`metric`（local-name 判定对齐 Operation 先例），anchor 保持定位+分类面、不携带口径字段 |
| `backend/app/api/schemas.py` | `SemanticContextQueryRequest.resource_types` Literal +2 值 |
| 测试（`backend/tests/`） | 新增 `test_semantic_command_compiler_r3003.py`（编译与 G1/G4/G7）、`test_modeling_batches_relational_mapping.py`（Batch 集成与 G2/G3/G5/G6、同批依赖）；扩展 `test_semantic_read_model.py`（新模板 + 图限定守恒）、`test_semantic_context_query.py`（新资源类型）、`test_semantic_access_http.py`（A5 等价断言）、`test_naming_and_schemas.py`（schema 枚举一致性） |

无 migration、无新服务文件、无前端必需改动；MCP 写命令面零代码（枚举自动派生）；MCP 读面
仅一处增量——`get_semantic_read_model` 加可选 `entity_iri` 参数（第六轮 H-2，透传既有
service 参数）。
