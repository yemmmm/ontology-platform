# R-006 结构化语义上下文查询独立测试计划

## 1. 测试依据

- 需求：`docs/requirements/requirements-v1.0.md` R-006。
- 设计：`docs/delivery/designs/2026-07-16-r006-semantic-context-query-design.md`。
- 依赖：R-001 默认工作区、R-005 lineage、现有只读 SPARQL。

开发 Agent 和测试 Agent 必须复用本计划。测试 Agent 不重新定义目标；每轮结果追加到本文件的
“独立测试记录”，使用 `PASS`、`FIXED`、`STILL FAILING`、`REGRESSION` 或 `BLOCKED` 标记。

## 2. 独立测试职责

1. 先审查实现是否只有一套 Context Query 流程，没有按问题类型分派。
2. 核对 Project/Ontology 到内部图范围的解析和跨 Project 防泄漏。
3. 运行 service、REST、MCP、SPARQL、frontend 和全量 backend 测试。
4. 使用真实 PostgreSQL/Oxigraph 验证 lexical、邻域、lineage、stale 和 SPARQL dataset scope。
5. 检查 Context Query 响应绝不携带 Evidence 原文、rationale、Audit 或 Competency Question。
6. 发现问题时向主 Agent 报告严重程度、复现步骤、预期/实际和涉及文件，不得放宽需求。

## 3. 必测场景

### A. Scope

- Project 全局包含全部 ready Ontology，顺序稳定。
- Project 全局有一个 incomplete Ontology 时返回其他结果、`scope_status=partial` 和排除原因。
- 显式一个或多个 Ontology 全部 ready 时成功。
- 显式列表中任一 incomplete、不存在或不属于 Project 时整体失败，不返回部分知识。
- 重复/空 Ontology 列表、错误 scope mode、空 Project 被拒绝。
- 响应不暴露 Graph Set ID 或 graph IRI。

### B. 统一查询文本

- 关键词、业务短语、完整中文问题、完整英文问题走同一 service 方法。
- 中文“发布工作流需要哪些参数”能命中已有中文名称/别名/属性，不依赖空格。
- 英文和 `camelCase`、`snake_case`、路径/API 标识符正确切分。
- 中英文混合查询命中已有双语 label/alias；没有已建模别名时不自动翻译。
- 空白和超长 query 被拒绝；普通未命中 query 返回 `no_match`，不是 unsupported。
- 多个同名候选同时返回并带客观 ambiguity warning，不自动合并或裁决。

### C. Corpus 与过滤

- concept、instance、relation、fact、rule 都可直接命中；R-007 未实现时 operation 可为空。
- label、SKOS alias、description、IRI/API 标识、property label 和 literal fact value 分别可命中。
- resource type 和 assertion type 过滤只缩小结果，不切换另一套业务流程。
- 默认包含当前 asserted/current derived；历史 deleted/replaced 不出现。
- stale current derived 可见、降权且带 warning。
- Evidence excerpt、document name、rationale、Audit reason、Competency Question 文本即使包含查询词也
  不能产生普通 semantic match。

### D. 排序与邻域

- exact label > exact alias > partial label > identifier > description > fact value。
- 相同输入和 workspace versions 多次查询，item ID、分组、分数和顺序完全一致。
- 主要匹配与关联上下文分开；`depth=0` 无关联项，默认一层，`depth=2/3` distance 正确。
- 入边、出边、literal fact、predicate 定义和 SHACL 约束按范围展开。
- 名称相同但没有显式 RDF 关系的跨 Ontology 资源不会被建立关系。
- limit 和内部候选上限设置 `truncated=true`，不返回后续操作建议。

### E. Evidence、lineage 与客观状态

- asserted fact/resource 只返回 Evidence Reference ID 和 status。
- 无 Evidence 返回 missing；不能用 rationale 或 question 替代。
- derived item 返回 run/proof/lineage 状态，不直接继承上游 Evidence ID。
- lineage partial/missing 不删除召回 item，只增加状态和 warning。
- 序列化响应递归检查不得出现 `excerpt`、`document_name`、`rationale`、`edit_audit`、
  `competency_question` 内容字段。
- 平台不返回答案充分性、未建模知识推测或下一步查询建议。

### F. REST 与 MCP

- `POST /api/semantic/context:query` 与 `query_semantic_context` 对同一请求返回相同核心字段、排序、
  scope、warnings 和 no-match 语义。
- MCP registry、tool source catalog 和 allowlist 精确匹配。
- API/MCP schema 拒绝内部 Graph Set/graph IRI 参数。
- timeout、invalid scope、scope not ready 的错误 code 稳定。

### G. Scoped SPARQL

- `SELECT`、`ASK`、`CONSTRUCT`、`DESCRIBE` 在 selected scope 正常返回标准格式。
- `INSERT`、`DELETE`、`LOAD`、`CLEAR`、`DROP` 等 Update 被查询入口拒绝。
- `SERVICE`、`FROM`、`FROM NAMED` 被拒绝；注释或字符串中的同名文本不误判。
- dataset 注入分别覆盖有/无 `WHERE`、prefix/base、注释、字符串、IRI、子查询和嵌套括号；安全位置
  不唯一、注入后无法解析或查询形式改变时必须 fail closed，原始查询不得执行。
- 无 `GRAPH` 查询只能读取允许 default dataset。
- `GRAPH ?g` 只枚举允许 named graphs。
- 显式 `GRAPH <other-project-graph>` 返回空且不泄漏内容。
- 多 Ontology default union 和跨图 join 必须同时读取所有允许图；不得依赖 Oxigraph 0.5.9 会折叠的
  重复 SPARQL Protocol dataset 参数。
- Project 全局 partial 与显式列表 all-or-nothing 规则和 Context Query 一致。
- scope、workspace versions、truncated、stale warnings 在 REST/MCP 中一致。
- `CONSTRUCT`/`DESCRIBE` 结果不写入 Dataset，查询前后图 hash/revision 不变。
- 调用方已有更大 `LIMIT` 时，`result_limit` 仍分别硬限制 SELECT binding 和
  CONSTRUCT/DESCRIBE triple；ASK 保持布尔结果，只有真实遗漏才标记 truncated。
- 实际发送给 RDF store 的顶层 LIMIT 不超过 `result_limit + 1`；注释、字符串、子查询 LIMIT 不被
  修改，最终查询仍通过 parser。图结果继续执行 triple 级后处理。
- REST/MCP 对 timeout/result limit 的非法边界使用同一共享校验；timeout 和 store unavailable
  分别保持 `query_timeout`、`query_unavailable`，不得映射成 `invalid_query`。

### H. 前端兼容

- Semantic Import/Export Debug 页从当前 workspace 传 Project/Ontology scope。
- Graph Set selector 仍可用于 export，SPARQL 不再把 Graph Set 作为 Agent scope。
- `npm run build` 通过；现有 Playwright smoke 无回归。
- R-006 不新增 Context Query 页面，不改造 Agent Test 页面。

### I. Round 1 回归

- 属性 label 和事实分处 asserted ontology/data 图时，fact 过滤仍能召回；不同 Ontology 共享
  predicate IRI 或 label 时不交叉错配，响应 item 保留事实图所属 Ontology。
- `limit=20`、`depth=0` 的 12 个直接命中返回 12 条且不截断；唯一命中填满 `limit=1` 但无额外
  eligible item 时不截断。直接匹配优先于关联上下文。
- Scoped SPARQL 包含持久 Graph Set 成员和当前派生指针，不包含非成员 `/custom` 或虚拟 generated
  SHACL 图；合并约束由 Context Query 验证。

## 4. 建议命令

开发 Agent 可调整新增测试文件名，但测试 Agent 必须覆盖同等范围：

```bash
cd backend
uv run pytest \
  tests/test_semantic_context_query.py \
  tests/test_semantic_context_query_api.py \
  tests/test_semantic_context_query_mcp.py \
  tests/test_scoped_sparql_query.py \
  tests/test_mcp_surface.py -q
uv run pytest

cd ../frontend
npm run build
npx playwright test
```

代码检查：

```bash
cd backend
uv run ruff check app tests
```

## 5. 真实运行时验收

1. 使用同一 Project 创建两个 ready Ontology，并创建另一个 Project 的隔离 Ontology。
2. 在两个同 Project Ontology 中写入中英文 label/alias、实例、literal fact、跨资源 relation、
   SHACL constraint、Rule 和 Evidence；另建一个无 Evidence fact。
3. 运行单 Ontology、多 Ontology、Project 全局、中文、英文、混合标识、未命中和 limit 查询。
4. 核对 Evidence 只有 ID，lineage/stale/partial 状态真实且无原文泄漏。
5. 运行 SELECT/ASK/CONSTRUCT/DESCRIBE，并用多图 default union、跨图 join、`GRAPH ?g`、显式其他
   Project graph 验证 fail-closed dataset 注入和 scope 不能绕过。
6. 通过 MCP 重复 Context Query 和 SPARQL，核对 REST/MCP 一致。
7. 重启服务后重复最小查询，确认结果和排序持久稳定。

运行时完成条件：

```bash
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

失败时检查：

```bash
journalctl --user -u ontology-platform.service --no-pager -n 200
```

## 6. 完成门槛

- 设计中的统一流程、范围、响应、证据和只读 SPARQL 边界全部有自动化测试。
- 全量 backend pytest、frontend build 和 Playwright 无失败。
- 真实 PostgreSQL/Oxigraph 证明 Context Query 和 SPARQL 均无法跨 Project 读取。
- Context Query 响应无 Evidence 原文或治理上下文泄漏。
- service 重启后 backend/frontend 健康，REST/MCP 查询可用。
- 若外部依赖阻塞，记录精确命令、错误和已完成的更窄验证，不以 mock 结果替代真实范围验收。

## 7. 独立测试记录

测试 Agent 在此追加每轮结果，不覆盖前一轮。

### Round 1 - 2026-07-16 - FAIL

#### 自动化结果

- `PASS` 定向后端：38 passed。
- `PASS` 全量后端：604 passed, 3 skipped。
- `PASS` 本次变更 Python 文件 Ruff：All checks passed。
- `PASS` 前端构建：`tsc -b && vite build` 完成。
- `PASS` Playwright：34 passed。
- 仓库全量 Ruff 仍有 60 个既有问题；本轮新增和修改文件不在失败清单中。

#### 真实运行态结果

- `PASS` 服务重启后 systemd unit active，`/api/health` 返回 `{"status":"ok"}`，前端返回 200。
- `PASS` 真实 PostgreSQL/Oxigraph：多 Ontology default union、`GRAPH ?g`、跨图 join、其他
  Project 的显式 GRAPH 为空；`SELECT`、`ASK`、`CONSTRUCT`、`DESCRIBE` 均可执行且未写入数据。
- `PASS` Update、`SERVICE`、调用方 `FROM` 被拒绝；Project 全局 partial、显式 Ontology 列表
  all-or-nothing 和跨 Project 404 均符合要求。
- `PASS` 5105 条无关数据之前/之后的目标仍可召回；中文概念、custom SHACL constraint、Rule、
  literal、stale derived、lineage warning 和 Evidence ID-only 投影通过。
- `PASS` Evidence excerpt、文档名和 binding 原文未进入 Context 响应；真实 REST/MCP 核心结果、
  scope、排序和 warnings 一致；仅使用 Evidence excerpt 中的独有文本查询返回 `no_match`。

#### 缺陷

- `FAIL - HIGH` 属性标签跨 Ontology/Data 图时无法召回使用该属性的事实。真实数据中属性 label
  位于 `asserted_ontology`、事实位于 `asserted_data`；使用该 label 且
  `resource_types=["fact"]` 查询返回 `no_match`。候选模板在同一个 `GRAPH ?graph` 中同时匹配事实
  和 `?predicate rdfs:label`，与默认工作区的分图方式不兼容。涉及
  `backend/app/services/semantic_sparql_templates.py:687`。
- `FAIL - MEDIUM` `limit=20`、`depth=0` 且存在 12 个直接命中时只返回 10 个并标记截断。
  `primary_budget = min(limit, 10)` 是未在需求或设计中声明的隐藏上限，也会使直接匹配在关联上下文
  之前被丢弃。同一处截断判断还会在唯一结果恰好等于 `limit=1` 时错误标记
  `truncated=true`。涉及 `backend/app/services/semantic_context_query.py:115` 和 `:137`。
- `FAIL - HIGH` scoped SPARQL 的 `result_limit` 可被调用方已有 `LIMIT` 绕过，且图结果不做服务端
  截断。真实请求 `CONSTRUCT ... LIMIT 100` 配合 `result_limit=1` 返回 100 triples，
  `truncated=false`。这同时违反结果边界并允许大图响应。涉及
  `backend/app/services/scoped_sparql_query.py:68` 和
  `backend/app/repositories/rdf_store.py:421`。
- `FAIL - MEDIUM` SPARQL timeout 的 HTTP 状态为 504，但稳定错误 code 被错误映射为
  `invalid_query`；`RdfStoreUnavailable` 同样被映射为 `invalid_query`。直接调用异常映射可稳定得到
  `SparqlQueryTimeout -> {"code":"invalid_query"}`，不符合设计中的 `query_timeout`，也会误导 Agent
  将可重试运行故障当成请求语法错误。涉及 `backend/app/api/semantic.py:337`。
- `FAIL - MEDIUM` MCP 绕过 REST Pydantic 后，scoped SPARQL service 不校验运行参数。真实 MCP 调用
  `result_limit=0`、`result_limit=-1` 或 `timeout_seconds=0` 均返回 `ok=true`，而 REST 会拒绝同一
  输入，违反 REST/MCP 同一服务语义。涉及 `backend/app/services/scoped_sparql_query.py:63`。

#### 残余风险

- custom SHACL 当前通过 `shapes/{ontology_id}/custom` 读取并投影到 Context，但 scoped SPARQL 的
  resolved dataset 只包含 Graph Set 的 `shapes` 成员；需在修复复测时明确验证高级查询是否按产品
  契约需要直接看到 custom/generated shape 子图。
- 当前真实验收数据由测试 Project 隔离，但未自动清理；不会进入其他 Project 查询范围。

### Round 2 - 2026-07-16 - PASS

#### 自动化结果

- `FIXED` Round 1 五项缺陷及 exact-fill、执行前顶层 LIMIT clamp 的新增回归全部通过。
- `PASS` 定向后端：65 passed。
- `PASS` 全量后端：631 passed, 3 skipped, 57 warnings。
- `PASS` 本次变更 Python 文件 Ruff；`git diff --check` 通过。
- `PASS` 前端构建；Playwright 34 passed。

#### 真实运行态结果

- `FIXED` 同一 Ontology 的属性 label 位于 ontology 图、事实位于 data 图时，
  `resource_types=["fact"]` 能召回正确事实；相同 property IRI 不跨 Ontology 错配。
- `FIXED` 超过 10 个直接匹配时使用完整响应预算；12 个预期直接匹配全部可见，唯一精确匹配配合
  `limit=1` 返回 `truncated=false`。
- `FIXED` `CONSTRUCT ... LIMIT 100` 配合 `result_limit=1` 在执行前被改为 `LIMIT 2` 探测，响应
  只含 1 triple 且 `truncated=true`；不再把超大 caller LIMIT 交给 store。
- `FIXED` REST runtime error code 为 `query_timeout` / `query_unavailable`；MCP 的
  `result_limit=0/-1`、`timeout_seconds=0` 均以 `invalid_query` 拒绝。
- `PASS` 多 Ontology default union、跨图 join、其他 Project 图为空、typed/language literal、
  Evidence 文本不参与召回、Context Evidence ID-only、REST/MCP 核心响应一致。
- `PASS` custom SHACL 约束继续通过 Context Query Shape Endpoint 投影；raw scoped SPARQL 对
  非 Graph Set member 的 `/custom` 子图返回空。该边界已同步到设计、API、MCP 和架构文档，与本轮
  批准的功能范围一致，解除 Round 1 对 shape dataset 的残余风险。
- `PASS` `ontology-platform.service` active，backend health 为 `{"status":"ok"}`，frontend 200。

#### 残余风险

- 仓库全量 Ruff 仍有 60 个既有问题；本次触及文件全绿，不作为 R-006 阻塞项。
- pytest 的 57 个 warning 为既有依赖弃用/插件提示；未出现 R-006 测试失败。
- 真实验收 Project 保留在本地数据库中且彼此隔离，未自动清理；不影响其他 Project 的查询范围。

### 验收后清理 - 2026-07-16

- 已精确删除唯一测试后缀 `14bf85cb6c` 对应的隔离 Project、Ontology、默认 Graph Set、RDF 图及
  本轮明确创建的关联测试数据，未触碰其他 Project 或无法明确归属的数据。
- 清理后 `ontology-platform.service` 为 active，backend health 返回 `{"status":"ok"}`，
  frontend 返回 HTTP 200。
