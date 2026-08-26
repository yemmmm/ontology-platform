# R3.0-007 读取模型图限定与 LIMIT 截断修复 — 共享测试计划

- 日期：2026-08-26
- 状态：Round 1 独立测试 PASS（2026-08-26），需求已收口
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-007
- 设计：
  `docs/delivery/designs/2026-08-26-r3-0-007-read-model-graph-scoping-design.md`
- 前置记录：R3.0-004 测试计划 Round 1 轮次记录 O-1（缺陷发现与 live 复现）
- 执行者：开发者先自测；`requirement_tester` 在稳定状态独立复核并把轮次追加到本文
- 测试位置：`backend/tests/test_semantic_read_model.py`（新增用例，已裁决）；
  `test_semantic_access_http.py`（HTTP 级既有回归确认不破坏）
- 时序约束（关键）：8001 后端以 `--reload` 运行，代码一改线上即热载。因此
  **R1 的修复前 API 假 404 证据必须在实现改动合入之前采集**，原始输出保存于
  `docs/delivery/evidence/2026-08-26-r3-0-007/`；独立测试轮以直查 :7878 回放
  未限定查询形态的方式独立复核机制，不依赖主 agent 的采集过程。

## 1. 测试边界

本计划只验收 R3.0-007：

1. 读模型 SPARQL 模板图限定修复（entity-detail 加 `VALUES ?graph { {graph_iris} }`）
   与 LIMIT 截断假 404 的消除。
2. 不验收 O-2（图集成员图未写入时 export/shape 500）——独立缺陷。
3. 不改响应合同、不动 R3.0-004 授权过滤；scope 内有标签实体 >500 的既有窗口
   截断不是缺陷（不在判定内）。
4. 不启动真实建模、不宣称 R3.0-002/003/005/006 或 v3.0 完成。

## 2. 稳定测试命令

```bash
cd backend && uv sync --extra dev          # 依赖未变时省略
cd backend && uv run pytest                # 全量回归（完成门必需）
```

真实运行轮（§8）：

```bash
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

失败时按 CLAUDE.md 用 `journalctl --user -u ontology-platform.service` 定位并记录。

## 3. Fixture 设计

pytest 级：复用 `test_semantic_read_model.py` 的 `FakeStore`/`FakeScopeResolver`
与 `test_semantic_read_model_stage2_execution.py` 的 `_seed_graph_set`/`_client`
模式；IRI 一律 fixture 专用命名空间（如 `https://r307.test/…`），不进产品代码。

live 级（真实 Oxigraph :7878，org-admin key 驱动，沿用 R3.0-004 L2 实践）：

1. **对照项目 P_decoy**（decoy）：经真实接口创建项目/本体/graph set，用
   `POST /api/semantic/edits` 向其 `asserted_data` 角色图写入 **≥600 个只带
   `rdfs:label` 的 fixture 实体**（`<https://r307.test/decoy/e{i}> rdfs:label
   "r307-decoy-{i}"`，i=0..599）。600 单图即超过 entity-detail 的
   `default_limit=500`，叠加共享存储既有 ~2177 个带标签实体，构成"跨 Project 合计
   远超 LIMIT"。
2. **目标项目 P_target**：同路径创建，其 `asserted_data` 图只写 **1 个目标实体**
   `<https://r307.test/target/T1> rdfs:label "r307-target"`。目标图为最后创建、
   单实体，即"窗口尾部"位置——无 VALUES 限定时 500 行窗口由其他图（600 decoy +
   既有存储）的实体填满，目标实体在窗口外的概率结构上占优。
3. 主体：既有 org-admin key——缺陷对任何主体成立，用 org-admin 排除授权因素。

## 4. 成功路径（S）

- **S1 编译限定**：服务级。scope 解析出 asserted_data 图（可加 include=
  full-working-view 的 reasoning/rule 图）后，`FakeStore.last_query` 满足：
  含 `VALUES ?graph { <data 图…> }`（逐 IRI 相等）；无未替换的 `{graph_iris}`；
  `LIMIT` 替换不变。对齐既有 `test_class_topology_executes_and_decorates_rows`
  的断言模式。
- **S2 修复后正确返回（live）**：org-admin 调
  `GET /api/semantic/resources/https%3A%2F%2Fr307.test%2Ftarget%2FT1?graph_set_id=<P_target gs>`
  → 200，`label="r307-target"`、`source_graph_iri=<目标 asserted_data 图>`、
  `graph_set_id`/`source_signature`/`assertion_kind`/`evidence_status`/
  `derived_state`/`warnings` 字段齐全（与合同一致）。
- **S3 限定查询直接复验（live）**：向 :7878 提交修复后形态
  `VALUES ?graph { <目标图> } GRAPH ?graph { ?entity rdfs:label ?label . }` →
  仅目标图实体（含 T1）；窗口内行数 ≤ scope 内带标签实体数，不含 decoy/其他
  项目 IRI。

## 5. 边界路径（B）

- **B1 无源图 fail-closed**：graph set 无 asserted_data/可用源图时，entity-detail
  返回空 items + `read_model_no_source_graphs` warning，且 `FakeStore.last_query
  is None`（不发查询）；对应 HTTP 面 `read_resource` → 404（合同不变）。复用
  `test_class_topology_without_source_graphs_…` 模式。设计 §3.3.1 的预期变更点。
- **B2 include 扩图**：`include=full-working-view` 时 VALUES 含
  reasoning/rule 结果图（扩展既有
  `test_full_working_view_includes_reasoning_and_rule_graphs`，从只断言
  `last_graph_iris` 加强为断言编译查询文本）。
- **B3 响应合同不变**：修复前后对同一存在的实体，200 响应字段集合与 404 detail
  文案逐字一致（对照实现前基线快照或字段级断言）；R3.0-004 的 B1 等价用例
  （Operator vs 同目标对照在 resources 面逐字节相等）保持成立——修复前两侧同为
  假 404，修复后两侧同为真 404，等价性不变。
- **B4 LIMIT 语义不变**：scope 内实体数 < limit 时全部返回；`limit` 参数与
  `default_limit=500` 的 min 逻辑、授权过滤 `_FILTERED_FETCH_LIMIT` 超额取回
  不变（服务级断言传给 FakeStore 的 `limit` 参数与查询文本中的 `LIMIT` 值；
  评审备注：`# bounded_limit=` 尾注由真实存储层在服务层之后追加，服务级
  FakeStore 中不存在，不作断言对象）。

## 6. 失败路径（F）

- **F1 模板守恒（审计门，已裁决加入）**：遍历 `list_templates()`，凡 body 含
  `SELECT` 的可执行模板必须含 `{graph_iris}`（防未来再引入无限定模板）；composer
  （graph-set-staleness、entity-shape、publication-readiness、
  graph-set-history-list、graph-set-delta、owl-consistency-summary）豁免。
- **F2 破坏性检查（负向）**：无授权保护集场景下修复不改变任何行内容——
  `FakeStore` 返回的行经 decorator 后与修复前逐字段一致（防止 VALUES 改变
  `?graph` 投影导致 `source_graph_iri`/`assertion_kind` 漂移）。

## 7. 回归（R）

- **R1 跨 Project 超 LIMIT 窗口尾部回归（live，本需求验收核心用例）**：
  1. 按 §3 构造 P_decoy（600 decoy 实体）与 P_target（1 目标实体）。
  2. **修复前取证**（必须在实现改动之前执行；8001 后端 `--reload` 热载决定了
     顺序）：
     a. 向 :7878 直接提交未限定形态
        `SELECT DISTINCT ?entity ?label ?graph WHERE { GRAPH ?graph { ?entity
        rdfs:label ?label . } } LIMIT 500`，记录：返回行数（预期恰好 500=窗口
        饱和）、覆盖的 distinct 图数、`https://r307.test/target/T1` 是否在窗口内
        （预期不在）。
     b. org-admin 调 `GET …/resources/<T1>?graph_set_id=<P_target gs>` →
        **404（假 404）**，记录响应体。
     c. 若引擎排序异常导致 T1 落入窗口（无 ORDER BY，无引擎级保证）：向 P_decoy
        追加一批 decoy 实体后重取 a/b；重试机制与实际窗口构成一并记录。
     原始输出保存到 `docs/delivery/evidence/2026-08-26-r3-0-007/prefix/`。
  3. **修复后**（合入 + pytest 全绿 + 服务重启 + 健康检查后）：同一 GET → 200
     （断言同 S2）；S3 限定查询复验通过。
  4. 证据以真实命令 + 响应摘要记入轮次记录（§10），不污染保留证据：fixture
     全部走平台创建/删除路径，直查 SPARQL 只读。独立测试轮复核：向 :7878 回放
     未限定旧查询形态独立确认窗口混杂机制（该回放与产品代码版本无关）。
- **R2 全量回归**：`cd backend && uv run pytest` 全绿（当前基线 875 passed /
  10 skipped 之上不新增失败）；重点关注 `test_semantic_read_model*.py`、
  `test_semantic_access_http.py`、`test_semantic_read_model_stage2_execution.py`、
  `test_scoped_sparql_query.py`、`test_semantic_api.py`。
- **R3 R3.0-004 用例不回归**：R3.0-004 测试计划 S1–S8/B1–B8/F1–F7/R1–R5 既有
  pytest 映射全部保持绿（授权过滤位置与合同不动）；其轮次记录 O-1 即本缺陷，
  修复后由主 agent 在该测试计划以**追加方式**记录 O-1 修复回指（不改写历史
  轮次）。

## 8. 真实运行（L，独立于 pytest）

1. **L1 重启与健康**：`systemctl --user restart ontology-platform.service` 后
   unit active；`curl --fail http://127.0.0.1:8001/api/health` 与
   `curl --fail http://127.0.0.1:5173/` 通过。
2. **L2 live 修复验证**：R1.3（同 S2/S3）。可加一条既有真实内容的 resources
   读取（修复前因窗口混杂而 404 的任一实体）作为平台自愈证据（可选加强）。

## 9. 清理

1. 删除 fixture 项目 P_decoy/P_target（平台删除路径，级联 graph set 与图）；
   确认 Oxigraph 中 `https://r307.test/` 命名空间无残留四元组（只读 SPARQL
   COUNT 复核）。
2. 未新建 API key（复用既有 org-admin），`backend/.env` 未被修改；无临时 MCP
   进程、无临时脚本残留。
3. 测试 fixture 常量只存在于 `backend/tests/`；产品代码无 `r307` 命名空间。

## 10. 判定规则与完成门

- **PASS**：S1–S3、B1–B4、F1–F2、R1–R3、L1–L2 全部通过；R1 的修复前假 404 与
  修复后 200 证据均已记录；设计 §4 审计表在案。
- **FAIL**：修复后仍出现跨 scope 图进入 entity-detail 窗口；修复改变了响应字段/
  错误码/排序；R3.0-004 任一既有用例回归；无源图场景发出查询（fail-closed 破坏）；
  全量 pytest 失败。
- **BLOCKED**：仅用于 Oxigraph/systemd 服务无法运行等外部条件。
- 完成后由主 agent 收口：更新 R3.0-007 状态、需求文档信息区链接、设计/测试计划
  状态行；在 R3.0-004 测试计划轮次记录以追加方式记录 O-1 修复回指。
  R3.0-002/003/005/006 状态不变。

## 轮次记录

（开发者自测与独立测试轮次由执行者追加，不得改写历史轮次。）

### Round 1（独立测试，2026-08-26）

- 执行者：requirement_tester（独立轮，不复用主 agent 采集过程）
- 被测状态：工作区未提交改动（main 分支），实现 diff 仅
  `backend/app/services/semantic_sparql_templates.py`（entity-detail 模板体 +1 行
  `VALUES ?graph { {graph_iris} }`，与设计 §3.2 逐字一致）和
  `backend/tests/test_semantic_read_model.py`（+6 用例 + FakeStore.last_limit）。
  服务已由主 agent 重启；本轮独立复核 health。
- 未修改：产品代码、fixture、`docs/delivery/evidence/`、服务状态。

#### 实现评审（对照设计）

- 模板改动与设计 §3.2 完全一致：投影变量 `?graph` 不变，仅新增 VALUES 行；
  服务层/API 层零改动（`git diff` 证实）。
- 6 个新 pytest 用例与 S1/B1/B2/B4/F1/F2 的计划断言逐项核对一致（见下表）；
  FakeStore 仅新增 `last_limit` 记录，不改变既有桩识别逻辑。

#### 用例结果

| 用例 | 结论 | 证据 |
| --- | --- | --- |
| S1 编译限定 | PASS | `test_entity_detail_compiles_with_graph_scoping_values`：断言编译查询含 `VALUES ?graph { <data 图> }`、无未替换 `{graph_iris}`、`LIMIT 500` 不变（diff 逐行核对 + 单独运行 6 passed） |
| S2 修复后正确返回（live） | PASS | org-admin GET `…/resources/https%3A%2F%2Fr307.test%2Ftarget%2FT1?graph_set_id=38e73116-…` → HTTP 200，`label="r307-target"`，`source_graph_iri=http://ontology-platform.local/semantic/graph/data/r307-target`，10 字段齐全（见下） |
| S3 限定查询直接复验（live） | PASS | S3a：向 :7878 `/query` 提交修复后形态限定目标图 → 恰 1 行（T1 + 目标图），无 decoy/其他图；S3b：回放旧未限定形态 → 500 行、跨 201 个 distinct 图、T1 不在窗口、无任何 `https://r307.test/` 实体在窗口——窗口混杂机制在原始存储中独立确认（机制证据，非产品失败） |
| B1 无源图 fail-closed | PASS | `test_entity_detail_without_source_graphs_returns_empty_without_query`：空 items + `read_model_no_source_graphs` warning + `last_query is None` |
| B2 include 扩图 | PASS | `test_entity_detail_full_working_view_compiles_derived_graphs_into_values`：编译查询 VALUES 逐 IRI 含 data+reasoning+rule 三图 |
| B3 响应合同不变 | PASS | live 200 字段集合 = `SemanticResourceRead`（schemas.py L1133）10 字段逐一对应（iri/label/graph_set_id/source_signature/assertion_kind/evidence_status/source_graph_iri/properties/derived_state/warnings）；404 detail `Resource not found: <iri>` 与 `api/semantic.py` L1688（本轮无 diff）及修复前 `prefix/api-false-404.txt` 逐字一致 |
| B4 LIMIT 语义不变 | PASS | `test_entity_detail_limit_semantics_bound_by_default_limit`：default 500 / limit=100 / limit=9999→500 三分支（last_limit + LIMIT 文本） |
| F1 模板守恒 | PASS | `test_every_executable_template_binds_graph_iris`：`list_templates()` 中 body 含 SELECT 者必含 `{graph_iris}`，violation 列表为空 |
| F2 行形状不变 | PASS | `test_entity_detail_values_addition_preserves_decorated_row_shape`：`source_graph_iri`/`assertion_kind="asserted"`/`evidence_status="not_applicable"` 不漂移 |
| R1 跨 Project 超 LIMIT 窗口尾部回归 | PASS | 修复前证据（主 agent 采集，本轮只读复核）：`prefix/unscoped-window.json` 500 行/201 图、T1 不在窗口；`prefix/api-false-404.txt` 同一 GET → 404。修复后本轮独立重放：同 GET → 200（S2 证据） |
| R2 全量回归 | PASS | `cd backend && uv run pytest -q` → **881 passed / 10 skipped**（基线 875/10 + 新增 6，无新失败） |
| R3 R3.0-004 用例不回归 | PASS | 单独运行 6 个重点文件 `test_semantic_read_model.py`、`test_semantic_access_http.py`、`test_semantic_access_authorization.py`、`test_semantic_read_model_stage2_execution.py`、`test_scoped_sparql_query.py`、`test_semantic_api.py` → 131 passed（含全量 881 内） |
| L1 重启与健康 | PASS（独立复核） | `systemctl --user is-active` → active；`curl -sf http://127.0.0.1:8001/api/health` → `{"status":"ok"}`；`curl -sf http://127.0.0.1:5173/` → 200（重启动作由主 agent 完成，本轮未重启） |
| L2 live 修复验证 | PASS | 同 S2/S3 证据 |

#### 跨 scope 隔离（S3 附带 API 级）

- decoy 实体 `https://r307.test/decoy/e0` + **target** graph set → 404（`Resource not found: …decoy/e0`）
- T1 + **decoy** graph set → 404（`Resource not found: …target/T1`）
- 对照：decoy/e0 + decoy graph set → 200，`source_graph_iri=…data/r307-decoy`

#### 关键命令与输出（摘录）

```bash
# R2 全量
cd backend && uv run pytest -q
# → 881 passed, 10 skipped, 226 warnings in 41.90s

# R3 重点文件
uv run pytest tests/test_semantic_read_model.py tests/test_semantic_access_http.py \
  tests/test_semantic_access_authorization.py tests/test_semantic_read_model_stage2_execution.py \
  tests/test_scoped_sparql_query.py tests/test_semantic_api.py -q
# → 131 passed

# S2（org-admin key 来自 backend/.env）
curl -s -w "\nHTTP %{http_code}\n" -H "Authorization: Bearer $KEY" \
  "http://127.0.0.1:8001/api/semantic/resources/https%3A%2F%2Fr307.test%2Ftarget%2FT1?graph_set_id=38e73116-f393-4952-9e5d-4b398934f437"
# → HTTP 200 {"iri":"https://r307.test/target/T1","label":"r307-target","graph_set_id":"38e73116-…",
#   "source_signature":"625fa998d57d47bb7dc1fbb1820582c2","assertion_kind":"asserted",
#   "evidence_status":"not_applicable","source_graph_iri":"http://ontology-platform.local/semantic/graph/data/r307-target",
#   "properties":{},"derived_state":{…},"warnings":[]}

# S3a 修复后形态（:7878 /query）
curl -s -X POST -H "Content-Type: application/sparql-query" --data \
  "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> SELECT DISTINCT ?entity ?label ?graph \
   WHERE { VALUES ?graph { <http://ontology-platform.local/semantic/graph/data/r307-target> } \
   GRAPH ?graph { ?entity rdfs:label ?label . } } LIMIT 500" http://localhost:7878/query
# → 恰 1 行：entity=https://r307.test/target/T1, label="r307-target", graph=目标图

# S3b 旧未限定形态回放（:7878 /query，只读）
# → rows=500, distinct graphs=201, T1 in window=False, r307.test 实体 in window=0（窗口全部由其他
#   Project 的图占据，跨项目窗口混杂机制独立确认；与 prefix/unscoped-window.json 500/201/T1-absent 一致）
```

#### 偏差

- 无计划外用例；未执行任何清理（fixture 保留给主 agent 在 PASS 后统一清理，见 §9）。
- S3b 回放需补 `PREFIX rdfs:` 声明（模板内本有，curl 单行提交时首轮遗漏后已修正，不影响结论）。

#### 残余风险

1. 模板仍无 ORDER BY，窗口构成无引擎级保证（设计 §8.3 已声明）；修复后断言
   （scope=单实体目标图）完全确定，风险仅在 scope 内带标签实体 >500 的既有 bounded-read 截断。
2. 本轮观测到的 500 行窗口全部来自其他 Project 既有数据、decoy 600 实体也未进窗口——
   机制证据（跨项目混杂）成立且与修复前取证一致，但"decoy 占用窗口"这一具体构成未复现，属窗口
   构成随机性，不影响判定。
3. 工作区另有多份与 R3.0-007 无关的未提交文档改动（v3-0 场景准备类文档），不属本轮验收范围，
   收口提交时建议主 agent 注意分离。

#### 结论

**Round 1 PASS**。S1–S3、B1–B4、F1–F2、R1–R3、L1–L2 全部通过；缺陷已消除
（同请求修复前 404 → 修复后 200），响应合同与 R3.0-004 授权回归全绿。无缺陷登记。

### 收口记录（主 agent，2026-08-26）

- Round 1 PASS 后按 §9 清理：
  1. fixture 三元组经平台路径 `POST /api/semantic/edits`（DELETE DATA，sparql-update）
     删除（decoy 600 + target 1）；只读 SPARQL 复核 `https://r307.test/` 残留 = 0。
  2. graph set 无平台删除 API（semantic API 仅支持成员更新），故对两行
     `r3.0-007-prefill` 标识的 fixture 记录（semantic_graph_sets /
     semantic_graph_set_members / semantic_graph_registry 共 6 行）按唯一标识直连
     PostgreSQL 删除，复核 remaining = 0。此为 §9 计划偏差，理由：平台当前无对应
     删除接口，行有唯一归属标识。
  3. 语义编辑审计行（create/cleanup 共 4 条 audit）保留为 fixture 生命周期历史证据。
  4. 未新建 API key；`backend/.env` 未修改；无临时脚本残留。
- 需求状态已同步：requirements-v3.0.md R3.0-007 → 已完成（2026-08-26）；
  设计/测试计划状态行更新；R3.0-004 测试计划追加 O-1 修复回指。
- 服务重启与健康验证见 Round 1 L1（重启于实现后由主 agent 执行）。
