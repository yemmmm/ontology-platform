# R3.0-007 读取模型图限定与 LIMIT 截断修复 — 功能设计

- 日期：2026-08-26
- 状态：已实现（2026-08-26）；plan_reviewer 评审 PASS；共享测试计划独立测试
  Round 1 PASS（同日）
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-007（轮次记录 O-1，
  R3.0-004 独立测试 Round 1 发现的前置平台缺陷，基线 `d7f21ca` 即存在）
- 共享测试计划：
  `docs/delivery/test-plans/2026-08-26-r3-0-007-read-model-graph-scoping-test-plan.md`
- 交付边界：只修复读模型 SPARQL 模板的图限定缺陷（`entity-detail` 模板加
  `VALUES ?graph { {graph_iris} }`）；不改任何响应合同；不做精确 IRI 绑定等增强；
  不处理图集成员图未写入时的 export/shape 500（轮次记录 O-2，独立缺陷）

## 1. 目标

1. `entity-detail` 读模型模板的查询体经 `{graph_iris}` 替换后限定在请求 scope 的
   命名图内，对齐 `statement-list` 现状；共享 Oxigraph 存储上不再扫描全部命名图。
2. 消除 LIMIT 截断假 404：目标实体不再因其他 Project 的实体占满 `LIMIT 500`
   窗口而返回 404（`GET /api/semantic/resources/{iri}`，任何主体含 org-admin）。
3. 查询代价随请求 scope 增长，而非随平台总数据量增长。
4. 完成并记录 `semantic_sparql_templates.py` 全部模板的逐个图限定审计（§4）。

## 2. 非目标

1. 不改任何读取面响应合同：字段、错误码（含 404 detail 文案）、排序全部不变。
2. 不影响 R3.0-004 授权过滤：`SemanticAccessView` 过滤仍在查询之后、分页/截断之前
   （`semantic_read_model.py` 的 `_FILTERED_FETCH_LIMIT` 超额取回逻辑不动）。
3. 不加精确 IRI 绑定（`{entity_iri}` VALUES）、ORDER BY、计数或其他增强——用户已
   明确选择仅图限定最小修复。scope 内有标签实体总数超过 500 时的窗口截断是既有
   bounded-read 行为，不在本需求内。
4. 不处理 O-2（图集成员图从未写入时 export/shape 500，缺图 404 被映射为
   `RdfStoreUnavailable`）——独立缺陷，另行登记。
5. 不修改 `rdf_store.query_read_model` 的注释协议（测试桩识别依赖它）。

## 3. 功能合同

### 3.1 缺陷机制（现状）

`entity-detail` 模板体（`semantic_sparql_templates.py` ~L98-104）：

```sparql
SELECT DISTINCT ?entity ?label ?graph WHERE {
  GRAPH ?graph { ?entity rdfs:label ?label . }
}
LIMIT {limit}
```

- 无 `{graph_iris}` 占位符 → `_compile_template_query`（`semantic_read_model.py`
  ~L289）无 VALUES 可注入；`GRAPH ?graph` 是自由变量，扫描存储上**全部**命名图
  （全部 Project 的数据）。
- `rdf_store.query_read_model`（`rdf_store.py` ~L386）仅把 graph_iris 写成查询尾部
  注释（`# bounded_limit=… graphs=…`，测试桩识别用），不构成存储层限定。
- `default_limit=500` 截断后由应用层按请求 IRI 后过滤（`api/semantic.py`
  `read_resource` ~L1674-1688）。目标实体落在窗口外 → 假 404。
- 真实存储已复现（2026-08-26 探测）：共享 Oxigraph（:7878，~69838 quads、1799 个
  命名图、2177 个带标签实体）上该查询形态返回 500 行、跨 201 个项目数据图。

唯一调用方为 `read_resource`（`GET /api/semantic/resources/{iri}`）；MCP 与前端
无直接调用（仓库 grep 核实）。

### 3.2 修复（最小）

模板体改为对齐 `statement-list` 的形态（服务层零改动，`_compile_template_query`
的现有替换即可注入）：

```sparql
# template: entity-detail
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?entity ?label ?graph WHERE {
  VALUES ?graph { {graph_iris} }
  GRAPH ?graph { ?entity rdfs:label ?label . }
}
LIMIT {limit}
```

- 保持投影变量 `?graph` 不变（decorator 的 `source_graph_iri` 列、行形状不变）。
- 已在真实 Oxigraph 验证该形态正确执行且只返回限定图的实体（~26ms）。
- `_graph_iris_for_scope` 对 `entity-detail` 走默认分支（`scope.source_graph_iris`
  + 按 include 追加 reasoning/rule 结果图），与 `statement-list` 的
  asserted_data-only 分支不同——保持现状不改（include=full-working-view 时
  推理/规则结果图中的 label 仍可命中，行为只收紧到"scope 内"）。

### 3.3 边界行为（修复后，均为预期）

1. **无源图 fail-closed**：`semantic_read_model.py` ~L201 的既有守卫
   `if not graph_iris and "{graph_iris}" in template.body` 修复后开始覆盖
   entity-detail：scope 无可用图时返回空 items + `read_model_no_source_graphs`
   warning 信封（不再发出无 VALUES 的非法/全库扫描查询），`read_resource` 随之
   404。与 `statement-list`/`class-topology` 现行行为一致，方向收紧，是**预期
   行为变更**（修复前该场景会全库扫描）。既有测试
   `test_class_topology_without_source_graphs_returns_empty_without_invalid_sparql`
   即此模式。
2. 授权过滤位置不变：查询 → `access_view.filter_items` → `items[:bounded_limit]`。
   R3.0-004 的"与真不存在逐字节等价"合同在 resources 面不变（过滤后不在 items
   → 同一 404 路径）。
3. LIMIT 语义不变：`default_limit=500`、`bounded_limit = min(limit or default,
   default)`、授权过滤时的 `_FILTERED_FETCH_LIMIT=10000` 超额取回均不动。

## 4. 模板审计表（逐个，`semantic_sparql_templates.py`）

| 模板 | 可执行 | 图限定 | 结论 |
| --- | --- | --- | --- |
| ontology-schema-summary | 是 | `VALUES ?g { {graph_iris} }` | 合规 |
| class-detail | 是 | `VALUES ?g` | 合规 |
| **entity-detail** | 是 | **无（裸 `GRAPH ?graph`）** | **本需求修复对象（唯一）** |
| statement-list | 是 | `VALUES ?graph` | 合规（对齐基准） |
| class-topology | 是 | `VALUES ?g` | 合规 |
| property-list | 是 | `VALUES ?g` | 合规 |
| relation-type-list | 是 | `VALUES ?g` | 合规 |
| class-shape-generated | 是 | `VALUES ?g` | 合规 |
| class-shape-custom | 是 | `VALUES ?g` | 合规 |
| entity-list | 是 | 多处 `VALUES ?g/?ig/?class_graph/?lg/?og` | 合规 |
| entity-relations | 是 | 多处 `VALUES` | 合规 |
| entity-literal-facts | 是 | `VALUES ?g/?pg` | 合规 |
| mapping-list | 是 | `VALUES ?g` | 合规 |
| import-graph-mappings | 是 | `VALUES ?g` | 合规 |
| fact-audit-queue | 是（`_fetch_fact_rows` 编译执行） | `VALUES ?g` | 合规 |
| fact-audit-queue-with-types | 是（同上） | `VALUES ?g` | 合规 |
| entity-search | 是（composer 改写后执行） | 多处 `VALUES` | 合规 |
| graph-set-staleness | 否（composer，体为空） | — | 豁免 |
| entity-shape | 否（composer） | — | 豁免 |
| publication-readiness | 否（composer） | — | 豁免 |
| graph-set-history-list | 否（composer，PG） | — | 豁免 |
| graph-set-delta | 否（composer，`_role_triples` 单图直查） | — | 豁免 |
| owl-consistency-summary | 否（composer，PG） | — | 豁免 |

模块内自由函数 `semantic_context_candidates_query` /
`semantic_context_neighborhood_query` 已显式注入图 scope（`_iri_values` /
`_graph_scope_values`），不在缺陷范围。服务内联查询
（`_list_asserted_fact_ids`、`_role_triples`）均带 `VALUES ?g` / 单图直查，合规。

**审计结论：`entity-detail` 是唯一缺图限定的可执行模板。**

## 5. 错误与失败行为

- 不新增错误码、不新增 warning（`read_model_no_source_graphs` 为既有 code，只是
  开始覆盖 entity-detail）。
- 图集不存在 / scope 解析失败 / 未知 IRI 404 等现行错误路径逐字不变。
- 无源图场景从"全库扫描后按 LIMIT 截断"变为 fail-closed 空信封（§3.3.1）。

## 6. 发布影响

- 单模板体字符串修改，无 schema/migration/依赖/配置变更；服务层与 API 层零改动。
- 运行时注意：本地 `ontology-platform.service` 的 8001 后端以 `--reload` 运行，
  模板文件保存后运行中服务即热载，因此**修复前 live 取证必须先于代码改动完成**
  （见共享测试计划 §7 R1）。
- 按 CLAUDE.md：实现后 `cd backend && uv run pytest` 全绿 →
  `systemctl --user restart ontology-platform.service` → 健康检查
  （`/api/health`、`:5173/`）→ live 验证 `GET /api/semantic/resources/{iri}`。
- 对其他读面零影响（审计表 §4）；对 R3.0-004 已验收行为零影响（过滤位置不动）。

## 7. 验收标准（详见共享测试计划）

| ID | 标准 |
| --- | --- |
| A1 | entity-detail 编译后查询含 `VALUES ?graph { <scope 图…> }` 且无未替换的 `{graph_iris}`（服务级 pytest） |
| A2 | 跨 Project 合计超过 LIMIT 的实体数据、目标实体在窗口尾部的回归用例：修复前假 404、修复后正确返回（真实 Oxigraph live） |
| A3 | 无源图 → `read_model_no_source_graphs` 空信封、不发出查询（fail-closed 边界用例） |
| A4 | 响应合同不变：200 字段集合、404 detail 文案、排序与修复前一致（对照断言） |
| A5 | R3.0-004 测试计划全部既有用例保持绿；`cd backend && uv run pytest` 全量通过 |
| A6 | §4 审计表落盘；可执行模板必须含 `{graph_iris}` 的守恒测试在位（已裁决加入，保护稳定平台合同） |

## 8. 假设（错误则需重设计）

1. `entity-detail` 的唯一产品调用方是 `read_resource`（已 grep 核实）；若存在
   依赖"跨 scope 扫描 label"行为的隐藏调用方，修复会改变其结果集。
2. Oxigraph 对 `VALUES ?graph {…} GRAPH ?graph {…}`（?graph 同时为投影变量）的
   求值正确且行形状不变（真实存储已探针验证 ~26ms）。
3. live 修复前证据依赖"窗口被非目标实体填满"（600 个 decoy + 既有 ~2177 实体 vs
   LIMIT 500）；SPARQL 无 ORDER BY 时窗口构成无引擎级保证，pre-fix 步骤按
   "窗口饱和 + 目标不在窗口内"取证并在异常排序时按计划重试（机制确定性），
   post-fix 断言则完全确定。

## 附录 A 技术要点（非主线）

- 改动文件：仅 `backend/app/services/semantic_sparql_templates.py`（entity-detail
  模板体两行：新增 `VALUES ?graph { {graph_iris} }`）。
- 新增测试：`backend/tests/test_semantic_read_model.py`（已裁决放此文件，
  `test_semantic_read_model_stage2_execution.py` 保持不动）——编译查询 VALUES
  断言、no_source_graphs 边界、full-working-view 的 VALUES 含派生图断言；守恒
  测试：遍历 `list_templates()`，凡 body 含 `SELECT` 的模板必须含 `{graph_iris}`。
- 测试桩兼容：`FakeStore`/`AccessStore` 均按查询文本 marker 识别模板，不做
  SPARQL 解析，新增 VALUES 不影响。
