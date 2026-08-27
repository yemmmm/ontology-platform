# R3.0-003 纯语义 Ontology 与关系型 Schema 映射 — 共享测试计划

- 日期：2026-08-26
- 状态：plan review: **PASS**（第六轮窄幅复审通过，非阻塞小注已应用：完成门枚举补
  S3b；F2"grain 非 IRI 项注入 DSN"用例经复核断言不受 H-3 收敛影响、保留原样）。修订历史：第一轮
  H-1 `detail_fields` 透传与既有模板逐字节回归、H-2 DSN/连接串拒绝用例、缺省
  `resource_types` 增量默认正例；第二轮 H-A DSN 门字段作用域豁免与 IRI 引用/定位字段
  向量闭合负向断言、H-B `detail_fields` 引用受保护 IRI 的整行隐藏用例（`PS_REF`
  fixture）；终审补 update/delete `*_iri` 豁免正例与 `filters[].field` 两形态用例；第四轮
  H-1 内嵌 JSON 引用受保护 IRI 在 statements/export/context 面的隐藏用例与阴性对照、
  H-2 anchor 降级为定位+分类面（S4/S5/S8 改写）、H-3 fixture 与 G2/G3 对齐重写（属性
  全声明、表名一致限定、join 列闭合）；另按裁决新增 G3 反向悬空阻断 B 用例。第五轮
  H-1 `/statements` 面不含映射语句（asserted_data 硬编码）——S5/F3 语句级断言重定位到
  export 面（`/statements` 改为负向断言）、H-2 候选 `data` 载荷引用字段的隐藏用例补强；
  确认项——S1 JSON 字面量断言锚定 `json.dumps` 规范形态、fixture join_path 载荷注明
  分解形态；第五轮窄幅复审 PASS 后被第六轮推翻。第六轮三项 High——H-1 指标缺聚合目标
  （修订：TBox 增 `repairDuration` 属性、`METRIC_MTTR` 增 measure/value_expression、
  B2/B4/S8 度量目标正反用例）、H-2 已知 IRI 无法保证精确读取（列表受 `default_limit`
  截断且无 offset、MCP 无 `entity` 参数；修订：新增 S3b——四个精确 detail 模板 +
  窗口外精确读取 + 缺 `entity` 400 + MCP `entity_iri` 等价；S5/S8/F3/§1 同步）、H-3
  指标 raw `table.column` 引用不自洽（修订：F2 指标引用字段收敛为唯一 IRI 形态，
  raw 形态 G1 拒绝用例，替代原"两形态"用例）。待实现后由开发者自测、
  `requirement_tester` 独立复核并追加轮次记录
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-003
- 设计：
  `docs/delivery/designs/2026-08-26-r3-0-003-relational-schema-mapping-design.md`
- 执行者：开发者先自测；`requirement_tester` 在稳定状态独立复核并把轮次追加到本文
- 测试位置：`backend/tests/`（pytest），命令 `cd backend && uv run pytest`
- 依赖基线：R3.0-004（授权合同）与 R3.0-007（读模型图限定）已完成且其测试计划全绿；
  本计划在其上叠加，不修改其用例

## 1. 测试边界

本计划只验收 R3.0-003：

1. 关系 Schema 映射与指标定义资源的表达、写入（12 个 canonical 命令）、确定性校验
   （G1–G7）、读取（8 个图限定读模型模板（列表 ×4 + 精确详情 ×4，第六轮 H-2）+
   context:query `mapping`/`metric` 类型 +
   精确 IRI/语句/导出通用面）、授权呈现（逐字复用 R3.0-004 合同）与消费冒烟（A6）。
2. 领域风味名称（表名、列名、指标名，如工单/备件相关命名）只出现在 fixture 与断言；
  产品代码零领域分支（grep 门 F6）。
3. 不验收 NL2SQL / SQL 执行（R3.0-005）、保护集存储与授权实现（R3.0-004 既有范围）、
  真实场景建模质量（R3.0-006）；不宣称 v3.0 完成。
4. 不把 §4.5 其余已记录边界（删除被映射引用的类/关系/属性的级联阻断——TableMapping↔
   JoinMapping 悬空已由 G3 反向闭合覆盖（B8）、列级 SPARQL 投影）判为 FAIL。

## 2. 稳定测试命令

从仓库根执行：

```bash
cd backend && uv sync --extra dev          # 依赖未变时省略
cd backend && uv run pytest                # 全量回归（完成门必需）
cd backend && uv run pytest tests/test_semantic_command_compiler_r3003.py \
    tests/test_modeling_batches_relational_mapping.py    # 本需求新增用例（聚焦）
```

本需求无 migration；`uv run alembic current` 应保持 `0032`（验证无新增 head）。

真实运行轮（§8）：

```bash
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

失败时按 CLAUDE.md 用 `journalctl --user -u ontology-platform.service` 定位并记录确切阻塞点。

## 3. Fixture 设计（pytest，复用 conftest 服务级模式）

fixture 项目 P（本体 `O_m`，默认图集齐备），内容为一个小型关系语义模块（名称仅存于测试
数据）：

1. **TBox 基础（第四轮 H-3 重写：映射与 grain 引用的属性全部先在 TBox 声明——G2 合并
   视图判定的前提）**：类 `WorkOrder`、`SparePart`、`PartSupply`（中间表对应类）；关系类型
   `consumesPart`（domain WorkOrder → range SparePart）；属性——WorkOrder 上 `workOrderId`、
   `createdDate`、`statusCode`、`sparePartKey`（FK 引用）、`equipmentId`（grain 维度）、
   `repairDuration`（维修耗时数值——度量目标属性，第六轮 H-1）；
   SparePart 上 `sparePartId`；PartSupply 上 `partSupplyId`、`workOrderRef`、`sparePartRef`。
2. **映射资源**（经新命令或等价 Batch 写入；join 步骤的表名与 TableMapping `table_name`
   逐字一致（含 schema 限定），全部 join 列都在对应 TableMapping 的 `column_mappings`
   中——G3 闭合的前提。**载荷形态（第五轮确认）**：下文 join 步骤中的
   `表.列` 三段串（如 `service.work_orders.spare_part_id`）是文档速记；实际 `join_path`
   载荷用**分解形态**——`from_table`（≤2 段标识符）与裸列名数组（`from_columns`/
   `to_columns`，等长配对，与设计 §3.2 `op:joinPath` 步骤结构一致）
   分字段承载，与 §3.3 命令 payload 字段一致）：
   - TableMapping `TM_WO`：`mappedClass=WorkOrder`、`tableName=service.work_orders`、
     `columnMappings=[{property_iri: workOrderId, column: work_order_id, role: business_key},
     {property_iri: createdDate, column: created_at, role: value},
     {property_iri: statusCode, column: status_code, role: value},
     {property_iri: sparePartKey, column: spare_part_id, role: value},
     {property_iri: equipmentId, column: equipment_id, role: value}]`；
   - TableMapping `TM_SP`：`mappedClass=SparePart`、`tableName=service.spare_parts`、
     `columnMappings=[{property_iri: sparePartId, column: id, role: business_key}]`；
   - TableMapping `TM_PS`（中间表，多跳前提）：`mappedClass=PartSupply`、
     `tableName=service.part_supplies`、`columnMappings=[{property_iri: partSupplyId,
     column: id, role: business_key}, {property_iri: workOrderRef, column: work_order_id,
     role: value}, {property_iri: sparePartRef, column: spare_part_id, role: value}]`；
   - JoinMapping `JM_CONSUMES`：`relation_type_iri=consumesPart`、`joinDirection=forward`、
     `joinPath` 一步：`service.work_orders.spare_part_id ↔ service.spare_parts.id`
     （from/to 列均在 TM_WO/TM_SP 的 `column_mappings` 中）；
   - 多跳 JoinMapping `JM_MULTI`（B 组边界）：两步路径——步骤 1
     `service.work_orders.work_order_id → service.part_supplies.work_order_id`、步骤 2
     `service.part_supplies.spare_part_id → service.spare_parts.id`（相邻步骤表衔接，
     全部列均在 TM_WO/TM_PS/TM_SP 对应 `column_mappings` 中）；
   - EnumValueMeaning `EM_STATUS`：`property=statusCode`、`enumValue="R01"`、
     businessMeaning 文本；
   - MetricDefinition `METRIC_MTTR`（第六轮 H-1 增补度量目标）：grain=[`equipmentId`
     属性 IRI]、timeField=`createdDate` 属性 IRI、**measure=`repairDuration` 属性 IRI**
     （WorkOrder 上的已声明属性，见 §3.1 TBox 增补）、valueExpression="repairDuration =
     resolved_at − reported_at，单位小时"（可选计算说明文本）、filters=[{field:
     `statusCode` 属性 IRI, operator:"eq", value:"R01"}]、aggregation="avg"、
     nullValueRule/denominatorRule 显式文本（grain/time_field/measure/filters[].field
     全部用已声明属性 IRI 形态——第六轮 H-3 收敛后这是唯一合法形态，G2 可判定）。
3. **保护集与主体**（复用 R3.0-004 管理面创建）：`PS_R303`（`allowed_grants=["r303-visibility"]`）
   成员 = `METRIC_MTTR` IRI + `TM_WO` IRI（映射与指标各一，含 ontology_id 定位）；
   `PS_REF`（同 grants）成员 = **仅被引用的资源 IRI**——`WorkOrder` 类 IRI、
   `consumesPart` 关系类型 IRI、`equipmentId` 属性 IRI（grain 引用的属性；各用独立成员
   条目；映射/指标资源本身**不加保护**，专测内嵌引用泄露向量：读模型 `detail_fields`、
   statements/export 的 JSON 字面量、context 候选——评审 H-B + 第四轮 H-1）；keys：
   `KEY_GRANT`（read + `r303-visibility`）、`KEY_NOGRANT`（read + 空 grants）、
   `KEY_MODEL`（model，写命令用）、`KEY_ADMIN`（org-admin）、`KEY_P2`（对照项目 P2 read key，
   P2 含同构但无保护集内容）。
4. **证据**：一条 evidence reference 经 Item `evidence_reference_ids` 关联到 `TM_WO`
  （A8）。
5. 每用例后清理 fixture 项目/本体/key（互不串扰）。

通用断言工具（用例内定义，不新增仓库级脚本）：

- **逐字节等价（同目标对照，沿用 R3.0-004 基准）**：对同一请求目标，"无权主体响应"与
  "该目标在对照范围真不存在时响应"的 `status + content-type + 规范化 JSON` 三元组完全相等；
  豁免回显字段（404 detail 的请求 IRI、`original_queries` 等）须在用例注明。
- **无泄露子串检查**：无权主体响应不得含受保护映射/指标 IRI、其 label、tableName、
  join path 内容、`r303-visibility`、`protection_set` 字样。

## 4. 成功路径（S）

- **S1 命令写入全链路**：`KEY_MODEL` 经 Modeling Batch（dry-run → apply）提交
  create_class/property/relation_type 与 12 类新命令的合法组合（含同批
  先类后映射的依赖顺序）：dry-run 无阻塞 finding；apply 后 RDF 中出现 §3.2 全部谓词的
  正确四元组（逐谓词断言，内嵌 JSON 字面量为 `json.dumps(payload, ensure_ascii=False)`
  规范形态、逐字节锚定附录 A 钉死形态）；Item 状态/不可变记录与现有 RDF
  命令一致。
- **S2 update/delete 语义**：update 逐谓词替换（旧值删除、新值插入，未指定谓词不动）；
  delete 清除该主体全部语句；`*_id` 与 `*_iri` 两种定位均可。
- **S3 读模型模板**：列表 ×4 与精确详情 ×4（第六轮 H-2）共八个新模板经
  `GET /api/semantic/graph-sets/{id}/read-models/{model_name}` 按名消费；列表模板返回全部
  行与列；全部模板体含 `VALUES ?g { {graph_iris} }`；MCP `get_semantic_read_model`
  同名结果与 HTTP 结构等价。
- **S3b 精确详情模板（第六轮 H-2 新增）**：四个 detail 模板带 `entity=<稳定 IRI>` 返回该
  资源完整 `detail_fields`（与列表模板同行逐字段一致）；**窗口外可精确读取**：构造超过
  列表模板 `default_limit` 的同类资源数据（复用 B7 的批量构造模式）使目标资源落在列表
  窗口之外——列表模板不返回该行，detail 模板 + `entity` 仍取回全部字段；detail 模板缺
  `entity` 参数 → 400（占位符机制既有错误合同）；MCP `get_semantic_read_model` 带
  `entity_iri` 参数结果与 HTTP 结构等价。
- **S3a `detail_fields` 透传与既有合同回归（评审 H-1）**：新模板响应项的 `detail_fields`
  子对象含全部声明的谓词列（`table_name`/`column_mappings`/`join_path`/枚举与指标字段/
  `schema_source` 等，未绑定键省略）；白名单变量保持现行顶层形状。**逐字节回归门**：全部
  既有模板（逐一执行，重点 legacy `mapping-list`/`import-graph-mappings`——其投影变量
  今天被丢弃，修改后仍不得出现在响应中）的响应项与实现前逐字节一致（无
  `detail_fields` 键）。
- **S4 context:query 新类型（第四轮 H-2 改写）**：宽词（表名/枚举值/指标名/业务含义文本）
  命中 `mapping`/`metric` 类型候选；精确 IRI anchor 命中并**正确分类**为 `mapping`/
  `metric` kind（响应只携带定位与 rdf_types/label 证据，**不含口径字段**——anchor 是
  定位+分类面，字段由 S3/S3a/S3b 的 `detail_fields` 承载，设计 §3.5.4）；**显式传入旧六类型**
  （`resource_types=["concept",…,"operation"]`）的请求与实现前结构等价（回归）；**缺省**
  （不传 `resource_types`）的请求**包含** mapping/metric 候选（既有"缺省全选"语义下的
  记录在案增量默认行为，评审澄清，正例断言）；排序稳定（追加尾部不扰动既有类型次序）。
- **S5 精确 IRI 与通用面（第五轮 H-1 改写）**：`GET /api/semantic/resources/{mapping IRI}`
  能**定位**资源（响应为 label-only 形态，不含映射字段——该面定位不载字段，设计
  §3.5.3）；字段读取经列表与精确详情模板的 `detail_fields` 承载（已知 IRI 走 detail
  模板，S3b；anchor 亦不载口径字段，第四轮 H-2）；语句级承载面为 **export 面（ontology 图含映射/指标语句）与 context
  related/neighborhood 展开**；`/statements` 面（硬编码 asserted_data 图）**不含**映射
  语句——断言其为空/不混入映射语句（负向，设计 §3.5.5），不对其做映射语句正断言。
- **S6 授权主体可见**：`KEY_GRANT` 与 `KEY_ADMIN` 在 S3/S4/S5 各面看到受保护映射/指标
  完整内容。
- **S7 证据与版本**：`TM_WO` 关联的 evidence reference 在证据面可见；
  `op:schemaSource`/`op:semanticVersion` 字面量在各读取面原样返回。
- **S8 消费冒烟（A6，第四轮 H-2 改写、第六轮 H-1/H-2 增补）**：测试内仅凭授权读取面
  （口径字段由读模型模板的 `detail_fields` 承载——已持稳定 IRI 的资源一律走 detail
  模板 + `entity` 参数精确读取，不依赖列表窗口扫描，第六轮 H-2；context:query 宽词与
  anchor 仅用于**定位与分类**
  ——确认资源 kind 与 IRI，不承载字段；不直连数据库、不用内部 API、不用
  `resources/{iri}` 或 anchor 承载字段）机械组装：
  WorkOrder→表/业务标识列/属性列、consumesPart→方向/join 步骤/连接条件、
  `METRIC_MTTR`→**度量目标（`repairDuration`，avg 的对象）**/计算说明/粒度/时间字段/
  过滤/聚合/空值/分母规则；输出结构化"SQL 生成依据说明"（含"avg 什么"逐字段断言）并
  逐字段断言（不生成、不执行 SQL）。

## 5. 边界路径（B）

- **B1 多跳 join**：`JM_MULTI` 两步路径写入与读取；相邻步骤表不衔接（`to_table(i) ≠
  from_table(i+1)`）→ G3 `join_path_not_mapped` 阻塞 finding（dry-run 即拒）。
- **B2 悬空目标**：`mapped_class_iri` 指向不存在类 / `relation_type_iri` 不存在 /
  `property_iri` 不存在 / metric grain·time_field·**measure（第六轮 H-1）**·filters[].field
  属性 IRI 不存在 → G2 `invalid_resource_reference`；
  同批先建目标后建映射则通过（合并视图判定）。
- **B3 枚举含义**：同 `(property_iri, enum_value)` 重复（跨 Batch 与同 Batch 两种）→ G5
  `resource_already_exists`；不同属性同值合法。
- **B4 指标度量目标与规则（第六轮 H-1 增补）**：`aggregation ∈ {sum,avg,min,max,
  count_distinct}` 而 `measure_property_iri` 缺失 → G1 拒绝（avg 没有"平均什么"不可
  通过）；纯 `count` 省略 measure 合法；measure 给出但属性不存在 → G2（B2 覆盖）；
  `count_distinct` 的 measure 即去重目标（正例）；`value_expression` 可选、缺省合法、
  给出时为自由文本（DSN 门作用域）；缺 `null_value_rule` 或空串 → G1 拒绝；填入显式
  "未确认"文本合法通过（显式未知不是缺省）；`aggregation` 超出枚举 → G1 拒绝。
- **B5 业务标识列**：`column_mappings` 无 `business_key` → G4 拒绝；join path 引用未映射
  列 / 未映射表 → G3 拒绝。
- **B6 update/delete 目标**：update/delete 不存在的映射/指标 IRI → G6
  `resource_not_found`；create 撞已有 IRI → `resource_already_exists`。
- **B7 图限定与跨项目隔离**：构造第二项目超过模板 LIMIT 的映射数据，目标行在窗口尾部
  仍正确返回（R3.0-007 回归形态应用于新模板）；查询不混入其他 Project 行。
- **B8 G3 反向悬空阻断（第四轮裁决）**：update `TM_WO` 从 `column_mappings` 移除
  `spare_part_id`（被 `JM_CONSUMES` 引用）或修改 `table_name` → G3 `join_path_not_mapped`
  阻塞（既有 JoinMapping 来自 store 与来自同批两种来源各覆盖）；delete `TM_WO` 同理
  阻塞；update 仅**新增**列（不删被引用列）→ 允许通过。

## 6. 失败路径（F）

- **F1 非法 payload**：未知字段（白名单外，如 `password`、`rows`、`sample_data`）→
  `invalid_command_payload`（Unknown payload field）；必填缺失；类型错误；`table_name`/
  `column` 含连接串/URL/空白（标识符正则拒）；内嵌 JSON 键集合不符（封闭 schema 拒）。
- **F2 凭证与连接串扫描（评审 H-2 扩充、H-A 修订为字段作用域）**：
  - 既有门：payload 任意字符串值注入平台密钥形态/JWT/bearer token/凭证字段名
    （`scan_domain_payload`）→ `invalid_command_payload`；
  - **DSN/URL 拒绝门正例（非 IRI 字段）**：`postgresql://svc:Pass123@10.0.0.4:5432/after_sales`、
    `jdbc:postgresql://host/db`、`postgres://…`、`user:pass@db-host` 形态分别注入
    `description`、`schema_source`、`filters[].value`、grain 非 IRI 项、`enum_value`
    （自由字符串与内嵌 JSON 各覆盖）→ 全部 `invalid_command_payload` 拒绝，dry-run 全或无、
    apply 无部分写入，RDF/export 中无该字符串残留；
  - **IRI 引用/定位字段豁免（H-A，按字段表穷举）**：合法 `mapped_class_iri`/
    `relation_type_iri`/`column_mappings[].property_iri`（平台 `http://…` 资源 IRI，本身含
    `://`）**以及 update/delete 的 `*_iri` 定位字段**（`table_mapping_iri` 等，含 `://`）
    不被 DSN 门误杀、正常通过（正例，与 S1/S2 互证——S2 的 `*_iri` 定位路径依赖此豁免）；
  - **IRI 引用/定位字段中的 DSN 向量闭合（负向断言）**：把 DSN/带 userinfo 的
    `http://u:p@host/…` 字符串塞进 `mapped_class_iri` 等 create 侧 IRI 引用字段 → G2
    `invalid_resource_reference`（scope 内不存在该"资源"）拒绝；塞进 update/delete 的
    `*_iri` 定位字段 → G6 `resource_not_found` 拒绝；
  - **指标引用字段唯一 IRI 形态（第六轮 H-3 收敛，替代原"两形态"）**：grain 项/
    `time_field`/`measure_property_iri`/`filters[].field` 的属性 IRI 形态走 G1 IRI 形状 +
    G2 存在性校验（不存在的属性 → `invalid_resource_reference`；合法属性通过）；
    `"table.column"`（两段或 `schema.table.column` 三段）raw 形态一律 G1 拒绝——
    不存在无校验豁免位，物理列解析归属 R3.0-005 消费方经 TableMapping 完成；
  - 保守误杀方向 sanity（非 IRI 自由文本）：含 `://` 或 scheme 前缀的正常自由文本同样被拒
    （fail-closed 文档化行为；IRI 引用字段不适用此门，由 G1/G2 管辖）。
- **F3 未授权受保护映射读取（与不存在不可区分）**：`KEY_NOGRANT` 对 `TM_WO`/`METRIC_MTTR`：
  - 精确 IRI（resources/{iri}、context:query anchor）与同目标在 P2 对照范围真不存在的响应
    **逐字节等价**（豁免回显字段注明）；
  - 四个 detail 模板带 `entity=<受保护 IRI>`：响应与"该 IRI 在对照范围真不存在"的响应
    **逐字节等价**（空结果，无提示、无 total、无回显），第六轮 H-2 面扩展；
  - 四个新列表模板返回无痕授权子集：分页/limit/排序与对照结构等价、无 warning/total/
    cursor 泄露、受保护行连同其 `detail_fields` 整行消失、叠加无泄露子串检查；
  - **公共资源内嵌引用受保护 IRI（评审 H-B + 第四轮 H-1 扩展到全部读取面，`PS_REF`）**：
    `TM_WO` 本身未加保护，但其 `detail_fields.mapped_class` 与 `column_mappings` JSON
    字面量引用受保护的 `WorkOrder` 类 IRI → `KEY_NOGRANT` 的：
    - `table-mapping-list` 中**该行整行消失**（与行不存在逐字节等价；不得出现"行保留、
      `mapped_class` 字段被抠掉"的部分删值形态）；
    - **export 面（第五轮 H-1 更正：语句级承载面是 export，`/statements` 面硬编码
      asserted_data 图、本就无映射语句）**：export 中携带该 JSON 字面量的映射语句 quad
      丢弃——对象值经 `semantic_access` 通用 JSON 引用抽取 helper 命中无权 IRI
      （`_term_unauthorized` 整词精确匹配抓不到内嵌引用，第四轮 H-1 的泄露向量）；
      context related/neighborhood 展开中引用该 JSON 字面量的语句行隐藏（经
      `filter_candidate` 的递归 `data` 扫描覆盖 `data.object` 的内嵌 JSON，第五轮 H-2；
      本 fixture 中该子场景对 KEY_NOGRANT 近乎空转——语句主体作为根已先被候选隐藏，
      有效向量由列表面/export/宽词候选三处实断言覆盖）；
    - context:query（宽词与缺省 `resource_types`）中引用它的候选项隐藏；
    同构覆盖 join-mapping 行/语句引用受保护的 `consumesPart` 关系类型、metric 行/语句
    grain 引用受保护的 `equipmentId` 属性 IRI；`KEY_GRANT` 全部可见；
    **阴性对照（不误伤）**：未加保护的属性 IRI（如 `createdDate`）出现在公共映射 JSON
    中时，`KEY_NOGRANT` 各面该行/语句**保持可见**（helper 只精确匹配无权成员集合）；
    并叠加无泄露子串检查（受保护类/关系/属性 IRI 与其 label 不得出现在无权响应任何层级）；
  - SPARQL（scope 含无权成员）→ 409 `scope_not_ready` 通用错误；scope 干净本体正常；
  - export 面中受保护映射/指标语句及引用它的语句整体隐藏（s/p/o 任一命中；`/statements`
    面无映射语句，不做此断言——第五轮 H-1）；
  - 语义知识读取面无 403/`forbidden`。
- **F4 scope 拒绝**：read/Consumer 主体调用写命令（Modeling Batch 提交新命令）→ 现行
  model scope 合同（`forbidden_scope`）不变。
- **F5 RDF store 不可用**：候选校验期 store 异常 → 既有通用依赖错误合同（fail-closed，
  不静默放行）。
- **F6 边界守恒（grep 门）**：产品代码（`backend/app/`，排除 tests）不得出现 fixture 名称
  （`work_orders`、`spare_parts`、`R01`、`r303-visibility`、`METRIC_MTTR` 等）、领域专属
  路由/分支；新读模型模板必须含 `{graph_iris}`（守恒测试遍历 `list_templates()`）；校验
  路径无 LLM 客户端调用（grep 无 llm/embedding 依赖于 `_validate_relational_mapping_commands`）。
- **F7 遗留合同不变**：legacy `create_mapping`/`update_mapping`/`delete_mapping` 命令行为、
  `mapping-list`/`import-graph-mappings` 模板响应、`governed_mapping_lexical_candidates`
  检索锚定逐字回归（对照实现前快照）；新命令不得写入 import 图。

## 7. 回归（R）

- **R1 全量回归**：`cd backend && uv run pytest` 全部通过；重点关注
  `test_semantic_command_compiler*.py`、`test_modeling_batches_*.py`、
  `test_semantic_read_model*.py`、`test_semantic_context_query*.py`、
  `test_semantic_access_*.py`、`test_semantic_api.py`、`test_mcp_*.py`、
  `test_naming_and_schemas.py`。
- **R2 R3.0-004 套件保持绿**：`test_semantic_access_authorization.py`、
  `test_semantic_access_http.py`、`test_semantic_access_mcp.py`、
  `test_semantic_protection_sets.py` 全部既有用例不回归（授权过滤代码零改动的行为证明）。
- **R3 R3.0-007 守恒**：全部可执行模板含 `{graph_iris}` 的守恒测试通过（新模板纳入遍历）；
  `entity-detail` 图限定行为不变。
- **R4 context:query 兼容**：**显式传入旧六类型**的既有请求响应结构等价；缺省请求包含
  mapping/metric 候选（S4 正例，记录在案的增量默认行为）；`api/schemas.py` 枚举与
  `RESOURCE_TYPE_ORDER` 一致性测试（`test_naming_and_schemas.py`）。
- **R5 MCP 面**：`MODELING_BATCH_COMMAND_KINDS` 自动含 12 个新命令；MCP Modeling Batch
  提交新命令 round-trip 成功；既有命令枚举不变。

## 8. 真实运行（L，独立于 pytest）

1. **L1 重启与健康**：`systemctl --user restart ontology-platform.service` 后 unit active；
   `curl --fail http://127.0.0.1:8001/api/health` 与 `curl --fail http://127.0.0.1:5173/`
   通过；`uv run alembic current` 仍为 `0032`（无新增 head，验证 §6 无 migration 结论）。
2. **L2 live 写入与读取**：以真实 model key 经 HTTP/MCP 创建 Build Session + Modeling
   Batch（dry-run → apply）写入 fixture 映射/指标；read key 依次验证八个读模型模板
   （列表 ×4 + detail ×4 带 `entity` 参数）、
   context:query（宽词 + anchor + resource_types）、resources/{iri} 返回内容；
   记录命令与响应摘要到轮次记录。
3. **L3 live 授权对照**：以 `KEY_NOGRANT` 重复 L2 的受保护目标请求，与"同目标在对照范围
   真不存在"的响应保存两份样本 diff 为空（精确面）；列表面无痕子集；SPARQL 409
   `scope_not_ready`；grant key 正常可见。
4. **L4 live 消费冒烟（A6 的 live 形态）**：仅用授权读取面驱动一次机械消费（内联一次性
   脚本，不新增仓库文件），产出"SQL 生成依据说明"样本存档到轮次记录（临时文件用后删除）。

## 9. 清理

1. 撤销并清理 L2/L3/L4 创建的全部 fixture key；恢复被覆盖的环境变量原值。
2. 删除 fixture 项目/本体/graph set（保护集随项目级联；先清空成员再删或随项目删除），
   确认 `scopes:discover` 不再列出 fixture 项目。
3. 终止临时 MCP 进程；删除响应样本与临时驱动脚本（不提交）。
4. fixture 常量只保留于 `backend/tests/`；确认新增文件不含密钥、连接串、个人数据。

## 10. 判定规则与完成门

- **PASS**：S1–S8（含 S3a、S3b）、B1–B8、F1–F7、R1–R5、L1–L4 全部通过；设计 §7 验收标准
  A1–A10 全部有对应证据；R3.0-003 需求状态占位更新；无 migration 结论经 L1 验证。
- **FAIL**：任一校验门可被绕过（非法 payload/悬空目标/未闭合 join path、**TableMapping
  update/delete 致既有 JoinMapping 悬空未被 G3 阻塞（B8，第四轮裁决）**、DSN 或凭证
  字符串写入非 IRI 字段成功、IRI 引用字段中的 DSN 未被 G2 拒绝、合法 IRI 引用被 DSN 门
  误杀）；任何授权泄露（F3 等价破坏、子串泄露、**公共资源 `detail_fields`/内嵌 JSON
  引用受保护 IRI 而行/语句/quad/候选项未整体隐藏（H-B + 第四轮 H-1）或阴性对照被误伤**、
  403 出现在语义知识读取面）；新模板缺
  图限定；既有读模型模板响应逐字节回归破坏（S3a）；context:query 显式旧六类型合同回归；
  legacy mapping 合同漂移；全量 pytest 失败；真实运行门未过。
- **BLOCKED**：仅用于 PostgreSQL/Oxigraph/systemd 服务无法运行等本轮无法修复的外部条件；
  环境性警告只记录不判 BLOCKED。
- 完成后由主 agent 收口：更新 R3.0-003 状态、需求文档信息区链接、设计/测试计划状态行；
  R3.0-005/006 仍保持待实现/待验收；不得据本计划通过宣称 v3.0 完成。
- 独立测试不创建也不延续其评估的生产运行，不改动已保留证据（CLAUDE.md 独立验收规则）。

## 轮次记录

（开发者自测与独立测试轮次由执行者追加，不得改写历史轮次。）

### Round 1（独立测试，2026-08-27）

- 工作区：`/home/yangxiang/ontology-platform`，HEAD `de52099` + 未提交实现改动
  （`backend/app/services/` 9 文件、`backend/app/api/schemas.py`、
  `backend/app/mcp/tools/semantic.py`、`docs/reference/mcp.md` 再生成块、5 个扩展测试文件、
  2 个新测试文件）。运行时已重启且健康（backend `/api/health` 200，frontend 5173 200），
  测试针对该运行时。测试者未修改产品代码、未放宽验收标准、未 commit。

**结论：FAIL**（读模型面真实运行不通过，见缺陷 D1）。

#### 执行范围与结果

- 实现审查 vs 设计附录 A：完成。命令面（12 编译器）、G1-G7 校验、DSN 三规则门、JSON 字面量
  规范化、R3.0-004 授权复用（`_iter_reference_strings` 泛化接入 filter_items/statements/quads/
  candidate）、context:query 扩展（`mapping`/`metric` 类型 + anchor 分类）均与设计一致。
- A10 全量 pytest：`cd backend && uv run pytest` → **928 passed, 10 skipped**（43.76s）。
- L1：Alembic head `0032_semantic_protection_sets`，无新 migration（设计 §6 无 schema 变更）——通过。
- S 组（pytest + live）：S1/S2 建模批 dry-run/apply 真实运行通过（含 TBox + 4 类映射资源 +
  206 条 bulk 分 3 批）；**S3/S3a/S3b/S8（8 个新读模型模板 list/detail）真实运行全部返回
  0 行——FAIL（D1）**；S4 context:query（宽词、anchor IRI、类型过滤）live 通过；S5/S6/S7 随
  pytest 通过。
- B 组：B1-B7 随 pytest；B8（TableMapping rename/update/delete 致既有 JoinMapping 悬空被 G3
  阻塞）经一次性探针在真实服务上验证通过（store 侧与同批两侧）。
- F 组：F1-F5、F7 随 pytest；F2（grain DSN `postgresql://…`）实测在编译期以
  `invalid_command_payload` fail-closed（G1 IRI 形状门先于 G2 拒绝，向量闭合）；F6 grep 门
  通过（`backend/app` 无 fixture 名 `work_orders`/`spare_parts`/`R01`/`r303-visibility`/
  `METRIC_MTTR`，校验路径无 LLM 调用）。
- R 组：R1（`resources/{iri}`）live 200 且 label 正确；R2 legacy 读模型模板逐字节回归随
  pytest；**R5（export 面）BLOCKED**（见 D2）；R3/R4 随 pytest。
- L 组：L2 读检查中模板面 FAIL（D1）；L3 授权双 key 全部通过（受保护/不存在字节等价、
  无授权读取为子集、H-B 行整体隐藏、SPARQL 409 scope_not_ready、跨项目阴性对照）；L4 消费
  演示因 detail 模板空结果无法完成（下游于 D1）。
- A1-A10 对照：A1-A7、A9、A10 有证据；A3（读模型面）真实运行不满足（D1）；A8 export 面
  BLOCKED（D2）。

#### 缺陷（按严重度）

- **D1（CRITICAL）读模型面运行时不返回数据**：`backend/app/services/semantic_sparql_templates.py`
  8 个新模板（table-mapping/join-mapping/enum-meaning/metric 的 list+detail，约 L642-936）
  硬编码 `PREFIX op: <http://ontology-platform.local/semantic/op/>`，而编译器写入的命名空间是
  `{semantic_base_iri}/vocab/`（默认 `http://ontology-platform.local/semantic/vocab/`，
  `SemanticNamespace.vocab`，config.py `semantic_base_iri`）。复现（真实服务 127.0.0.1:8001，
  grant/model key，fixture：create_class wo + create_property dur + create_table_mapping tm1
  apply 成功后）：
  - `GET /api/semantic/graph-sets/{gs}/read-models/table-mapping-list` → 200 `items: []`；
    同 fixture 下 detail（`entity=…/table-mapping/tm1`）、join/enum/metric list/detail 全部
    0 项；
  - `POST /api/semantic/sparql:query`（org-admin）同图 `?s a op:TableMapping`：
    `PREFIX op: <…/semantic/vocab/>` → 1 行；`PREFIX op: <…/semantic/op/>` → 0 行；
  - `GET /api/semantic/resources/{…/table-mapping/tm1}` → 200（数据确实在图内），
    `POST /api/semantic/context:query`（query=IRI）→ `primary_matches[0].kind == "mapping"`
    （anchor 分类正常）。
  pytest 未拦截原因：新增测试的 FakeStore/SeededRdfStore 桩不解析 SPARQL，模板文本从未在
  真实 Oxigraph 上执行。影响：S3/S3a/S3b/S8、A3、L2 模板面、L4。修复面窄：8 处 `PREFIX op:`
  一行修正（或改为动态 `namespace_from_settings`）。注：同文件 L433/L461 两处 legacy 模板
  同样硬编码 `semantic/op/`，是否受影响需开发侧一并核对（本轮未单独验证 legacy 模板行数
  是否非零）。
- **D2（MAJOR，既有平台缺陷，非本需求引入）export 面 500**：`GET
  /api/semantic/graph-sets/{gs}/export?format=trig|n-quads|json-ld` → 500。journalctl 定位：
  `semantic_graph_set_export.py:98 _load_dataset → rdf_store.get_graph(data graph)` 对
  `…/graph/data/{oid}` 的 Oxigraph GET 返回 404（空 data graph 不存在）→ 未捕获 → 500。
  该文件在本变更集内未修改；仅含 class 的 fixture 同样 500（与 R3.0-003 资源无关）。
  影响：R5/A8 export 面无法验收 → BLOCKED；L3 export 双 key 等价检查在 500/500 上平凡
  成立，不具证据力。处置建议由主 agent 决定（另行立项或顺带修复）。

#### 观察与裁定（非缺陷）

- 开发者报告的 5 项偏差逐项复核：合并视图先投影 deletes 再 inserts、update_metric 对
  `aggregation` 变更 fail-closed、detail 模板主变量绑定 entity IRI、同批 create+update 由既有
  `conflicting_item_effects` 阻断、G5 逐 item finding——均与设计/测试计划判定的 fail-closed、
  等价性或既有门一致，**不构成缺陷**。
- `update_join_mapping`/`update_enum_meaning` ALLOWED_FIELDS 不含 `relation_type_iri`/
  `property_iri` 与 update_table_mapping 不含 `mapped_class_iri` 模式一致，设计"同上模式"如此
  解读合理，仅记录不改判。
- 首轮驱动脚本误读 anchor 响应键（应为 `primary_matches[0].kind`，无 `anchor` 顶层键），
  已用修正后的探针重验：anchor 分类通过。
- `create_metric_definition` 的 `time_field*`、`filters*`（可空数组）必填：设计 §3.3 明确，
  实测缺省拒绝为 `invalid_command_payload`，符合 G1，非缺陷。

#### 未执行/受阻用例

- R5/A8（export 面）：BLOCKED（D2）。
- L4（SQL 生成依据说明消费演示）：BLOCKED（D1 下游；detail 模板 0 行使演示无法取样）。

#### 清理确认

- 临时驱动 `/tmp/r3003_live.py` 与全部一次性探针脚本（heredoc，未落盘）已删除；
  fixture 项目（probe-*、r3003-live-*）全部删除（复查 leftover 为空），key 随项目级联撤销；
  未新增仓库内临时文件；6 个用户既有变更文件未触碰。

#### 复测建议

优先修复 D1（8 处 `PREFIX op:` 命名空间修正 + 在真实 Oxigraph 上补一条模板执行级回归，
防止桩测试再次漏过），D2 由主 agent 决定处置；随后按本计划执行 Round 2，重点复测
S3/S3a/S3b/S8、L2 模板面、L4 及 R5（若 D2 解除）。

### Round 2（独立复测，2026-08-27）

- 工作区：`/home/yangxiang/ontology-platform`，HEAD `de52099` + 未提交实现与 D1/D2 修复改动；
  运行时已重启并加载修复后代码（`/api/health` 200、frontend 200）。测试者未修改产品代码、
  未放宽验收标准、未 commit、未触碰用户既有变更文件。

**结论：PASS（R3.0-003 验收口径）；另记录 1 项与本需求无关的既有平台缺陷 D3（export
turtle 空载荷），处置由主 agent 决定。**

#### 修复复核（实现面）

- **D1 FIXED**：`semantic_sparql_templates.py` 新增 `OP_VOCAB_PREFIX`（由
  `config.py` 新常量 `DEFAULT_SEMANTIC_BASE_IRI` 拼出，值与原默认逐字相同，无行为变化）与
  `_op_body()`；8 个 R3.0-003 模板经 `{op_prefix}` 解析为 `…/semantic/vocab/`。新增门控回归
  `test_r3003_table_mapping_list_reads_compiler_vocabulary_on_real_store`
  （`RUN_OXIGRAPH_SPARQL_RUNNER_TESTS=1`）先编译再在真实 Oxigraph 上执行模板并断言 IRI 与
  `detail_fields`——经审查该测试确实执行 SPARQL（非桩），本轮实跑 1 passed。
- **D2 FIXED**：`semantic_graph_set_export.py::_load_dataset` 以 `graph_exists` 门控缺失图
  （`RdfStoreError` 时回退到 `get_graph` 上抛真实错误，fail-closed 保持）；新增
  `test_export_treats_missing_graph_as_empty`（7 passed 全文件）。
- **legacy 两模板边界复核**：`mapping-list`（L433）与 `import-graph-mappings`（L461）仍硬
  编码 `semantic/op/`，而 Stage-2 编译器写入 `{base}/vocab/`（`semantic_command_compiler.py`
  L1557 `op = str(ns.vocab)`）——**两者在真实存储上确实同样错位**，但属既有问题、不在本
  变更集（A9 只要求逐字回归，模板文本未动）。开发者"按边界不修"的结论成立；建议另立
  修复项。

#### 复测结果（FAIL/BLOCKED 用例 → 受影响回归 → 全量/运行时门）

- **S3/S3a/S3b/S8 与 L2 模板面（Round 1 FAIL）→ 全部 PASS**（真实服务，grant key，
  fixture：3 类 + 关系类型 + 11 属性 + 3 TableMapping + 2 跳 JoinMapping + EnumMeaning +
  MetricDefinition，apply_atomic applied）：
  - `table-mapping-list` 200，3 行；TM_WO `detail_fields` 完整（table_name
    `service.work_orders`、mapped_class、5 列 column_mappings JSON 字面量含 business_key
    role、schema_source、semantic_version）；
  - `table-mapping-detail`（`entity` 参数）200 单行；`join-mapping-list/detail` join_path
    两步（work_orders→work_parts→spare_parts）；`enum-meaning-list/detail`
    enum_value R01/business_meaning；`metric-list/detail` aggregation avg/measure/grain/
    time_field/filters；
  - S3b：`limit=1` 窗口仍生效（1 行）。
- **L4 消费演示（Round 1 BLOCKED）→ PASS**：仅用授权读取面机械重建"SQL 生成依据说明"：
  表 `service.work_orders`（5 列含 business_key 标注）、枚举 R01=已完成工单、连接
  forward `consumes-part` 两跳路径、指标口径 avg(repair-duration) grain equipment-id
  time created-date filter status-code='R01'，产出 SELECT…JOIN…WHERE…GROUP BY 样本（见本
  轮存档输出，临时脚本已删除）。
- **R5/A8 export 面（Round 1 BLOCKED）→ PASS（trig/json-ld）**：grant key 导出 200 且
  含 TM_WO/JM/EM/MT 语句（trig 10259 字节、json-ld 14610 字节）；nogrant 导出隐藏受保护
  TM_SP/MT、保留公共 TM_WO（H-B 整体隐藏 + grant 超集成立）。HTTP export 路由仅接受
  `trig|json-ld|turtle`（`n-quads` 400 属路由合同，非缺陷）。**turtle 200 但载荷为空 →
  缺陷 D3（见下）**。
- **L3 授权回归**：模板面 nogrant 隐藏 TM_SP 保留 TM_WO/TM_PS、metric-list 空、受保护
  detail 与真不存在 detail 逐字节相等（200 空集）；`resources/{iri}` 404 形状与 R3.0-004
  已验收合同一致（detail 为 `Resource not found: {请求 IRI}`，受保护与真不存在同形；本轮
  驱动对"不同 IRI 逐字节相等"的更强断言失败属驱动口径过严，已核对已验收测试
  `test_resource_route_returns_not_found_for_protected_member` 断言形状相同，非缺陷）。
- **A10 全量**：`cd backend && uv run pytest` → **929 passed, 11 skipped**（44s；较 Round 1
  +1 passed 为新 export 测试，+1 skipped 为未设门控环境变量的真实存储回归）。
- **L1**：`alembic current` 仍 `0032_semantic_protection_sets`（无新 migration）；backend/
  frontend 健康。
- Round 1 通过项（S1/S2/S4-S7、B、F、R1-R4、L3 其余）未受修复影响（修复仅触及模板前缀、
  export 缺图门控与 config 常量抽取），由全量 pytest 与本轮授权/模板回归覆盖。

#### 缺陷与观察

- **D3（MODERATE，既有平台缺陷，非本需求引入；由 D2 解封后暴露）**：graph-set export
  `turtle` 真实存储上返回 200 空载荷。根因：Oxigraph 单图 dump 为无 GRAPH 块的 trig，
  rdflib `Dataset.parse` 将其落入 default graph，而 `_serialize` turtle 分支排除
  `urn:x-rdflib:default` → 合并图为空（trig/json-ld 不受影响）。单元测试桩内容带 GRAPH
  块故通过。复现：任意含本体图的项目 `GET /api/semantic/graph-sets/{gs}/export?format=turtle`
  → 200，正文仅 1 字节；`format=trig` 同项目 402+ 字节含语句。turtle 分支在本变更集中未
  修改（属既有代码）。窄修复建议：按图 IRI 定向 parse 进命名图，或 turtle 合并时纳入
  default graph。设计 §7 A5 未单独强制 turtle，R3.0-003 验收以语句承载与隐藏为准（trig/
  json-ld 已证），故不判本需求 FAIL。
- 观察：`semantic_base_iri` 若经环境覆盖为非默认值，模板前缀仍取默认常量（代码注释已声明
  该限制，静态模板无法读 Settings）；本地实验用默认值，仅记录为残余限制。

#### 未执行用例

- 无 BLOCKED 项。turtle 格式的"含映射语句"断言 FAIL（D3，已定性为既有缺陷）。

#### 清理确认

- 一次性驱动 `/tmp/r3003_r2_live.py` 与诊断探针均已删除；fixture 项目（r3r2-live/r2diag/
  r2exp）与 key 全部删除（复查 leftover 为空）；未新增仓库文件。

#### 复测建议

R3.0-003 可收口（PASS）。建议主 agent：① 将 legacy `semantic/op/` 模板错位与 D3 turtle 空
载荷作为平台既有缺陷另立修复项（均非本需求回归）；② 若需 turtle 可用，修复后补一条真实
存储级 export turtle 内容断言。
