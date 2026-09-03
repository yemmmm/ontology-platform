# R3.0-008A 受控值 L1/L2/L3 表达合同与 `semanticValue` 映射链 — 功能设计

- 日期：2026-09-03
- 状态：设计冻结（计划评审 Round 1 两项 accepted-high 已修订：G7 扩展合并视图改
  ontology+data 双图装载与投影；`_RELATIONAL_DSN_EXEMPT_FIELDS` 增补 `semantic_value`），
  待复审、待实现、待独立验收
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-008A（含「2026-09-03 细化决策」小节，
  用户已确认三项决策与低影响保守口径）
- 冻结依赖合同：
  - `docs/delivery/designs/2026-08-26-r3-0-003-relational-schema-mapping-design.md`
    （映射资源词汇、命令面、G2/G3/G5/G6 校验门、读取面 `detail_fields` 承载面——本设计只在其上
    增量，不改任何已冻结合同）
  - `docs/delivery/designs/2026-08-23-r3-0-004-semantic-knowledge-authorization-design.md`
    （与不存在不可区分、无痕过滤合同——逐字复用、零改动）
  - `docs/delivery/designs/2026-08-27-r3-0-005-ontology-guided-sql-qa-design.md`
    （Consumer 消费链与 AuthorizedChain 机械推导形态、fixture 复用先例）
- 越界登记（本设计不实现）：R3.0-008B（分析结论 artifact 的时点门、真实场景联合验收）、
  R3.0-009（共性抽象）、R3.0-010（接口信息映射源——仅登记边界，映射源不限定数据库 Schema）
- 场景数据基线：`docs/evaluation-scenarios/industrial-service-v3/`（R3.0-001，
  安全装载器 `scripts/load-industrial-service-v3-postgres.sh`）
- 共享测试计划：
  `docs/delivery/test-plans/2026-09-03-r3-0-008a-controlled-value-semantic-chain-test-plan.md`
- 交付边界：后端产品代码一个**小而集中**的增量（命令编译 2 处、校验门 1 处、读取投影 2 处）
  + 新增 pytest 测试。无新映射资源类型、无新 API 路由、无新 MCP 工具、无 migration；
  fixture 为独立验收载体（真实建模运行归 R3.0-006/008B）。

## 1. 目标

1. **表达合同落地**：受控值按 L1/L2/L3 三种形态表达（表达方式选择，非成熟度等级）：
   L1 属性字面量直接经 `TableMapping` 使用（零新代码）；L2 既有 `EnumValueMeaning`
   （`businessMeaning` 字面量为权威含义，无 `semanticValue`）；L3 在 L2 之上增加可选
   `op:semanticValue` IRI 引用，指向同图内一等业务语义节点，该节点提供权威业务语义。
2. **确定性完整性校验（G7）**：dry-run/apply 对 `semanticValue` 只做**结构校验**——目标在
   合并视图存在、非映射资源类型、单值；删除被指向节点被悬挂保护拒绝（对称既有 G3 反向）。
   「可读取」不在建模校验执行，由读取侧保护集过滤承担。
3. **反向检索链闭合（零新查询接口）**：`semanticValue` 投影进既有召回结果（context:query
   映射候选 `data`、enum-meaning read-model `detail_fields`）；L3 节点经既有 `rdfs:label`
   词法召回为 resource 候选；Consumer 在同一响应内沿「L3 候选 ↔ 映射候选
   `semantic_value` ↔ `enumValue` ↔ `mappedProperty`/`TableMapping`」拼接闭环。
4. **授权无痕**：`semanticValue` 投影进候选 `data` / 行 `detail_fields` 后，自动纳入
   `SemanticAccessView` 的递归 IRI 扫描——指向未授权 L3 节点时候选/行整条隐藏，
   Consumer 稳定返回无法确认（与不存在不可区分）。
5. **防猜测物化的机械面**：建模命令面不提供任何"按列名/样例值自动创建
   `EnumValueMeaning` 或 L3 节点"的路径；未确认候选值在 RDF 中只能不存在
   （时点管理归 R3.0-008B，本需求只保证机械上不存在猜测产物）。

## 2. 非目标

1. 不新增映射资源类型（含 `ReferenceValueMapping`）、不建通用数据源连接器或多源编码注册中心
   （需求原文；接口信息映射源归 R3.0-010，本需求零实现）。
2. 不新增查询接口、不新增 API 路由/MCP 工具/服务/表/migration；`semanticValue` 反向链完全
   由既有读取面的字段投影承载。
3. 不把全部数据库枚举提升为 L3，不要求已有 L1/L2 无业务依据升级；不实现 L2↔L3 的自动
   升降级判断（升降级由建模方显式 `update_enum_meaning` 执行）。
4. 不把业务行、客户清单、工单或设备实例复制进 RDF（验收继续证明）。
5. 不建设编排框架、`analyzed_not_materialized` artifact schema、版本治理、管理 UI、
   Agent 时点管理（归 R3.0-008B）；不做共性抽象（R3.0-009）。
6. 不在建模校验中执行「可读取」判定（读取侧保护集承担，细化决策 1）。

## 3. 功能合同

### 3.1 资源词汇与表达形态

沿用 R3.0-003 词汇（`op:` = `{semantic_base_iri}/vocab/`），仅新增一个谓词：

- **`op:semanticValue`**：`EnumValueMeaning` → 一等业务语义节点（IRI），可选、单值。

| 层级 | 正式表达 | SQL 映射行为 |
| --- | --- | --- |
| L1 | 属性字面量，无独立语义节点 | 属性 + `TableMapping` 定位列，直接使用确认后的字面量 |
| L2 | `EnumValueMeaning`（`mappedProperty`+`enumValue`+`businessMeaning`），无 `semanticValue` | 由 `businessMeaning` 取原始编码，属性映射定位列 |
| L3 | 普通一等业务节点（本平台载体为 `op:Entity`，如 `biz:PartShortage`）+ `EnumValueMeaning` 带 `semanticValue` 指向它，**两个 RDF 主体** | `EnumValueMeaning` 提供原始编码，被指向节点提供权威业务语义 |

约束（需求 §L1/L2/L3 合同逐条落实）：

1. 每个 `EnumValueMeaning` 至多一个 `semanticValue`（编译层强制单值，§3.2）；
2. 同一 L3 节点允许被多个 `EnumValueMeaning` 指向（不同确认编码 → 同一业务值）；
3. L3 的 `businessMeaning` 可保留为展示文字；分类、关系、规则、跨语言标签以被指向节点为准
   （消费方解释规则，平台不强制清洗）；
4. 普通节点与 `EnumValueMeaning` 是两个资源：不使用同一 RDF 主体的多 `rdf:type` 混用
   业务实体与映射记录（命令面上 IRI 按资源 kind 分段生成，结构上不可碰撞；可表达的混用
   形态——`semanticValue` 指向映射资源类型——由 G7 拒绝，§3.3）；
5. 沿用 R3.0-003 的 `(mappedProperty, enumValue)` 唯一性（G5）与 `schemaSource` 边界，
   本设计零改动。

### 3.2 命令面（canonical 编译层）

`create_enum_meaning` / `update_enum_meaning` 增加可选字段 `semantic_value`（IRI 字符串或
`null`），其余字段集合不变：

- **create**：`semantic_value` 缺省 = L2；提供 = L3。非字符串/列表形态 →
  `InvalidCommandPayload`（沿用 `_relational_iri_value` 形状校验，多值在编译层即拒绝）。
  编译产物追加 `(subject, op:semanticValue, <目标>)` 四元组；`metadata` 增
  `semantic_value_iri`（供校验门读取，先例：`mapped_property_iri`）。
- **update**：`_relational_update_delta` 的 `iri_fields` 增
  `{"semantic_value": f"{op}semanticValue"}`——per-predicate 先删后插；值为 `null`/`""`
  即**清除**（L3→L2 降级），提供新 IRI 即**替换/增加**（L2→L3 升级）。
- `ALLOWED_FIELDS`（`backend/app/services/modeling_handlers.py`）两处命令各增
  `semantic_value`；白名单外字段照旧拒绝（防猜测面：不存在任何自动填充路径）。
- **MCP 层零改动**：`submit_modeling_batch` 经 `MODELING_BATCH_COMMAND_KINDS` 注册表
  透传 `command_kind`+`payload`，无字段白名单；读取面工具（`query_semantic_context` /
  `get_semantic_read_model`）为整包 envelope 透传。字段自动可达，不新增工具。

### 3.3 dry-run/apply 完整性校验：G7（`semanticValue` 结构门）

落在 `_validate_relational_mapping_commands`（`backend/app/services/modeling_batches.py`
1051-1364）内，全部阻塞级 finding，无 LLM。判定口径 = 2026-09-03 细化决策 1（只做结构
校验）。

**G7 专用合并视图（计划评审 Round 1 修订）**：`EnumValueMeaning` 落在 ontology graph
（`_ontology_graph_iri`），而 L3 一等业务节点的命令面载体 `create_entity`/`delete_entity`
全部四元组落在 data graph（`_data_graph_iri`，semantic_command_compiler.py 1264/1413）。
既有 G2/G3/G5/G6 的合并视图**只装载 ontology graph**，同批投影也按目标图过滤（modeling_
batches.py 1084-1089、1103、1128）——在该视图下实体永不可见。因此 G7 使用**扩展合并视图**：
批次目标 Ontology 的 ontology graph **与** data graph 双图装载，删除/插入投影的图过滤
条件同步扩到两类目标图。G2/G3/G5/G6 继续只查 ontology graph，与 G7 互不牵动；该扩展是
「L3 节点存在性可见」的机械必要条件，不改变拓扑范围口径（data graph 属于同一目标
Ontology 的存储拓扑，跨 Project/Ontology 引用仍然不可见、仍然拒绝）。

1. **目标存在（G7-a）**：`create_enum_meaning`/`update_enum_meaning` 载荷 `semantic_value`
   非空时，目标 IRI 必须在 G7 扩展合并视图（双图 + 同批投影）中存在（存在 = 以其为
   subject 的任意三元组）。目标缺失与跨 Project/Ontology 拓扑机械上同一拒绝形态，复用
   `invalid_resource_reference`，`path=["payload","semantic_value"]`（拒绝形态与既有 G2
   对 `property_iri` 同类，但视图口径不同，见上文）。
2. **非映射资源类型（G7-b）**：目标不得带任何映射资源 `rdf:type`
   （`op:EnumValueMeaning`/`op:TableMapping`/`op:JoinMapping`/`op:MetricDefinition`）。
   该检查同时覆盖可表达的「同一 RDF 主体混用」形态（含 `semanticValue` 指向自身——主体
   即 `EnumValueMeaning`）。finding 同 `invalid_resource_reference`，message 指明
   "must reference a non-mapping first-class semantic node"。
3. **单值（G7-c）**：载荷非字符串形态由编译层拒绝（§3.2）；G7 扫描合并视图枚举主体时
   顺带断言每个 `EnumValueMeaning` 的 `semanticValue` 对象至多一个（捕获直写残留），
   违反 → `invalid_resource_reference`。
4. **悬挂保护（G7-d，对称 G3 反向）**：校验触发集合在既有 12 个关系映射命令之外增加
   `delete_entity`（L3 节点的命令面载体，落 data graph）；在 G7 扩展合并视图（已应用
   批次删除投影，删除投影对 data graph 同样生效）中扫描**全部** `EnumValueMeaning` 的
   `semanticValue`，目标不存在 → 新 finding code `semantic_value_dangling`，归属到批次内
   删除该主体的 `delete_entity` 项（无归属项时 batch 级，与 G3 归属规则对称）。效果：
   删除被指向 L3 节点被拒绝；同批「删 L3 + 建指向它的枚举」同样被拒绝（投影顺序决定
   目标不可见）。
5. **不校验「可读取」**：保护集成员/授权状态不进入建模校验；未授权目标的链路断开由
   读取侧承担（§3.5）。

G5/G6 及其余既有门零改动；`update_enum_meaning` 不变更 `mappedProperty`（白名单不变），
G2 对 `property_iri` 的既有 create-only 校验维持原样。

### 3.4 检索投影（读取面，两处最小增量）

1. **context:query 映射候选**：`_mapping_candidates`
   （`backend/app/services/semantic_context_query.py` 1304-1400）SPARQL 增
   `OPTIONAL { ?mapping op:semanticValue ?semanticValue . }` 并投影；命中后写入候选
   `data["semantic_value"]`（非空时）。词法权重不变（`business_meaning` 既有 450 权重
   已覆盖词面召回；`semantic_value` 是精确 IRI 拼接键，不是词法匹配面）。
2. **enum-meaning read-model**：`enum-meaning-list` / `enum-meaning-detail` 模板
   （`backend/app/services/semantic_sparql_templates.py` 807-880）各增
   `?semantic_value` SELECT 变量 + `OPTIONAL`，并加入 `detail_variables`（行装饰器
   `detail_fields` 透传，R3.0-003 冻结承载面）。
3. L3 节点本身经既有 `semantic-context-candidates` 模板（同文件 1011 起）的任意 subject
   `rdfs:label` 匹配为 resource 候选——已覆盖，零改动。
4. 不新增反向查询接口：不提供 "按 L3 IRI 查枚举" 的专用端点；反向链由 Consumer 在同一
   context:query 响应内拼接（§3.6）。

### 3.5 授权与无法确认（零新代码，复用 R3.0-004 合同）

`semanticValue` 投影进候选 `data` 与行 `detail_fields` 后，自动落入既有递归 IRI 扫描：

- context:query：`SemanticAccessView.filter_candidate` 递归扫描候选 `data` 全部值
  （`backend/app/services/semantic_access.py` 160-205）——`semantic_value` 引用未授权
  成员 → 该映射候选整条隐藏；
- read-model：`filter_items` 在分页/计数/排序前按行值（含 `detail_fields` 嵌套）过滤
  （`backend/app/services/semantic_read_model.py` 258-260 附近）——enum-meaning 行整条隐藏；
- L3 节点本体是保护集成员时其 resource 候选同样隐藏（既有行为）。

链路效果：未授权主体看不到 L3 候选，也看不到带该 `semantic_value` 的映射候选/行——
与"从未建模"不可区分；Consumer 终态为无法确认（§3.6 合同 6），无泄露、无原因区分。

### 3.6 Consumer 反向链（消费方合同，测试侧承载）

Consumer（机械链形态沿用 R3.0-005 `AuthorizedChain` 先例，
`backend/tests/test_r3005_authorized_sql_chain.py` 636-848）在同一响应内执行：

1. 自然语言术语（如「缺料」）→ context:query → resource 候选（L3 节点，经 `rdfs:label`
   召回）与 mapping 候选（`EnumValueMeaning`，经 `business_meaning`/label 词面召回）；
2. 取 `mapping 候选 data.semantic_value == L3 候选 iri` 关联 → 读 `enum_value`（原始编码）
   与 `mapped_property`；
3. `mapped_property` → `table-mapping-list` 的 `column_mappings` 属性索引 → 表/列
   （多表时按 JoinMapping 机械拼 join）→ 生成可解释 SQL（标识符全部有授权出处）；
4. 任一环节缺失（`semanticValue` 缺失/被清除、枚举缺失、列映射缺失、无权、歧义）→
   **无法确认**终态：不区分未建模/不存在/无权，不回退原始 Schema 猜测编码或物理列
   （需求合同 6；措辞合同沿用 R3.0-005 设计 §4.2）。

平台不为该拼接新增任何字段以外的东西；`businessMeaning` 与被指向节点标签同时可见时，
以 L3 节点为权威（消费方解释，平台不清洗）。

### 3.7 测试数据复用（零新场景内容）

复用 R3.0-001 `industrial_service_v3` 真实表列（`work_orders.status`、
`work_order_delay_events.cause_code`（受控值 `PART_SHORTAGE` 等）、
`spare_parts.currency`）与 R3.0-003/005 fixture 形态（类/属性/TableMapping/JoinMapping/
EnumValueMeaning、保护集与多 key）；fixture 经 `KEY_MODEL` + Modeling Batch
（dry-run → apply）seeding 走真实产品写路径，seeding 批次 ID 登记为基线
（R3.0-005 §3.7 先例）。SQL 执行复用 R3.0-005 适配器（可选、DSN 门控）。

## 4. 错误与边界

### 4.1 校验失败（dry-run/apply）

G7 全部阻塞级：`invalid_resource_reference`（目标缺失/跨拓扑/映射资源类型/多值）与
`semantic_value_dangling`（悬挂）。编译层载荷形态错误 → 既有
`candidate_validation_failed` 形态。apply 与 dry-run 同门（既有合同）。

### 4.2 已记录边界（不修，不判 FAIL）

- `delete_class`/`delete_property` 不在悬挂门触发集合内（L3 载体是 `op:Entity`；类/属性
  不是值节点载体）。若未来允许其他主体形态，扩展触发集合即可。
- 同一 RDF 主体多 `rdf:type` 混用在命令面上结构不可表达（IRI 按 kind 分段）；G7-b 拒绝
  其可表达等价形态（引用级混用）。
- `businessMeaning` 与 L3 标签并存且措辞不一致时平台不仲裁（权威以 L3 为准是消费方规则）。
- 读取侧「可读取」与语义歧义判定不在建模校验（细化决策 1）；Consumer 歧义终态归消费方。
- 接口信息作为映射源（R3.0-010）：本设计的 G7 与链路以数据库 Schema 为载体；
  `schemaSource` 字段不限定取值，不为接口源做任何专门分支。

### 4.3 平台/参考本体边界

L1/L2/L3、`缺料`/`PART_SHORTAGE` 等领域名称只出现在 fixture、问句与断言；产品代码改动
是通用谓词投影与结构校验，无领域分支（grep 门见测试计划 F4）。

## 5. 发布影响

- 无 migration（`alembic current` 保持 `0032`）；无新表/路由/服务/MCP 工具。
- 产品代码改动集中于 5 个文件（附录 A）；完成后按 CLAUDE.md 执行全量 pytest 与服务
  重启验证（`ontology-platform.service`，backend 8001 / frontend 5173 健康检查）。
- 回滚：revert 产品代码增量 + 删除新增测试文件；已 apply 的 fixture RDF 由测试清理
  （测试计划 §9）负责，谓词本身无存储 schema 依赖。

## 6. 验收标准（详见共享测试计划）

| ID | 标准 |
| --- | --- |
| A1 | L1/L2/L3 各至少一个 fixture 示例；L3 证明普通业务节点与 `EnumValueMeaning` 同时存在且职责分离（不同 RDF 主体） |
| A2 | 两个不同 `EnumValueMeaning` 指向同一 L3 节点：检索不产生两个"同义业务节点"，数据库过滤分别取得各自原始编码 |
| A3 | 代表问题「查询因为缺料而延期的订单」fixture 闭环：召回 L3 → `semanticValue` 反向映射 → `enumValue` → `mappedProperty`/`TableMapping` 定位列 → 可解释 SQL；断链任一环节稳定返回无法确认 |
| A4 | dry-run/apply 拒绝：目标缺失、跨拓扑、映射资源类型（含同主体混用可表达形态）、多值 `semanticValue`、删除被指向 L3 节点（悬挂）；未确认候选值不产生猜测 `EnumValueMeaning` 或正式 L3 节点 |
| A5 | 授权回归：`semanticValue` 指向未授权 L3 时候选/行无痕隐藏、Consumer 无法确认；R3.0-004/R3.0-005 既有用例全绿 |
| A6 | RDF 未复制客户、设备、工单等业务行（既有断言不回归 + 显式断言） |
| A7 | `update_enum_meaning` 增加/清除 `semanticValue`（L2↔L3 升降级）往返成立 |
| A8 | `cd backend && uv run pytest` 全量通过；零 migration；MCP 零新增工具 |

## 7. 当前最小实现范围 vs 未来产品化

**当前最小**：§3.2 命令面 + §3.3 G7 + §3.4 两处投影 + 测试计划全套（fixture 复用
`industrial_service_v3`）。
**未来产品化（不得静默晋升）**：接口信息映射源（R3.0-010）、`analyzed_not_materialized`
artifact schema 与时点门（R3.0-008B）、多源编码冲突模型、`semanticValue` 反向专用查询
接口、值域治理 UI、自动 L2↔L3 升降级建议。

## 8. 假设（错误则需重设计）

1. **拓扑口径 = 批次目标 Ontology 双图合并视图**（计划评审 Round 1 修订）：G7 的
   「同一获准 Project/Ontology 拓扑范围内」按「ontology graph + data graph 双图 + 同批
   投影」机械执行；跨 Ontology 引用（同 Project graph set 内）一律拒绝。若需求方裁定
   跨 Ontology 引用应放行或需按 graph set 校验，G7-a 的存在性判定需重设计。
2. **L3 节点的命令面载体是 `op:Entity`，落 data graph**：一等业务节点经 `create_entity`
   建成（data graph），悬挂门触发集合只需含 `delete_entity`；G7 视图必须双图装载才能
   看到它（§3.3）。若 008B/R3.0-009 引入其他值节点主体形态（新资源类型或允许类/属性
   充当值节点），触发集合、G7-b 的类型判定与视图图集合需扩展。fixture 图集须含
   `asserted_data` 角色成员图（`semantic_read_scope.py` `_SOURCE_ROLES` 已支持；
   默认图集组合路径在开发轮由 S3 用例端到端证明）。
3. **保护集递归扫描覆盖新增投影**：候选 `data` 值与行 `detail_fields` 均被
   `SemanticAccessView` 递归 IRI 扫描（`semantic_access.py` `filter_candidate` /
   `filter_items` 路径，计划评审已核实无键白名单），故授权过滤零新代码自动生效。

## 附录 A 技术要点（文件级，非主线）

| 文件 | 改动 |
| --- | --- |
| `backend/app/services/semantic_command_compiler.py` | `compile_create_enum_meaning`（约 2552-2598）：可选 `semantic_value`（`_relational_iri_value` 形状校验，非字符串/列表即 `InvalidCommandPayload`）；quads 追加 `op:semanticValue`；metadata 增 `semantic_value_iri`。`compile_update_enum_meaning`（2601-2637）：`_relational_update_delta` 的 `iri_fields` 增 `{"semantic_value": f"{op}semanticValue"}`（null/"" = 清除，2302-2309 既有 iri 分支）。**`_RELATIONAL_DSN_EXEMPT_FIELDS`（1995-2009）增 `"semantic_value"`**（计划评审 Round 1 补：IRI 必含 `://`，不豁免则编译入口被 DSN 门误拒） |
| `backend/app/services/modeling_handlers.py` | `ALLOWED_FIELDS` 的 `create_enum_meaning`（约 301）与 `update_enum_meaning`（约 309）各增 `"semantic_value"` |
| `backend/app/services/modeling_batches.py` | `_validate_relational_mapping_commands`（1051-1364）增 G7-a/b/c（枚举项载荷 `semantic_value` 对合并视图结构校验）与 G7-d（触发集合增 `delete_entity`，扫描合并视图全部 `EnumValueMeaning` 的 `semanticValue` 悬挂，按 G3 归属规则定位到删除项；新 code `semantic_value_dangling`）。**G7 用扩展合并视图（§3.3）：装载批次目标 Ontology 的 ontology graph + data graph 双图，删除/插入投影的图过滤条件同步扩到两类目标图；G2/G3/G5/G6 的查询仍限 ontology graph** |
| `backend/app/services/semantic_context_query.py` | `_mapping_candidates`（1304-1400）：SELECT 增 `?semanticValue` + `OPTIONAL`，`data` 投影键 `semantic_value`（与 `mapped_property` 等同型的非空透传） |
| `backend/app/services/semantic_sparql_templates.py` | `enum-meaning-list` / `enum-meaning-detail`（807-880）：SELECT 增 `?semantic_value` + `OPTIONAL`，`detail_variables` 增 `"semantic_value"` |
| `backend/app/mcp/` | 零改动（命令载荷经注册表透传；读取面整包 envelope 透传） |
| `backend/tests/test_r3008a_semantic_value_integrity.py` | 新增：G7 全部拒绝路径 + create/update 往返 + 未确认编码零猜测物化（服务级，先例 `test_modeling_batches_relational_mapping.py`） |
| `backend/tests/test_r3008a_controlled_value_chain.py` | 新增：L1/L2/L3 fixture seeding + context:query/read-model 投影 + 双指向同 L3 + 代表问题闭环（含断链矩阵）+ 授权无痕 + RDF 未复制业务行（先例 `test_r3005_authorized_sql_chain.py`） |
