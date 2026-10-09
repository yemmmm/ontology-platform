# HTTP API

本文档描述当前运行时实际注册的 HTTP API。完整操作清单由 FastAPI `app.openapi()` 生成；业务
契约、边界和示例由人工维护。

## R4.0-027 模型状态绑定

当前读取、索引、分页与交接使用 Ontology 的非负整数 `model_revision`（包括 `0`）。
Batch 必须提交整数 `expected_model_revision`；旧 `expected_workspace_version` 字段与
字符串哈希不再有效。漂移仍返回 `workspace_revision_conflict`，详情包含
`current_model_revision`；重新读取后使用新的幂等键继续。Attempt 的
`workspace.expected_version/before_version/after_version` 保留现有回执结构，值均为编号。
模型写入已提交才推进编号，dry-run、失败未写入、索引重建和搜索配置变化不推进。
Embedding／投影配置仍单独校验；旧索引降级为词面召回，重建成功后恢复当前向量索引。
恢复未收敛时，现有写入围栏阻止将不确定 RDF 内容作为稳定模型读取；反馈指向待协调 Attempt。
迁移 `0035_ontology_model_revision` 保留原 Ontology 编号与历史哈希列，不翻译旧回执。
旧分页游标须从第一页重读；旧交接与未完成 Attempt 须重新读取并准备新的编号绑定。
检查点和冻结证据保留原样，不改写历史记录为新状态。

## 地址与认证

- `./scripts/start-local.sh` 与本地 systemd 服务：`http://127.0.0.1:8001/api`
- 手动运行 `uv run uvicorn app.main:app --reload`：默认 `http://127.0.0.1:8000/api`
- OpenAPI UI：对应 backend 地址的 `/docs`

只有三个 `/api/health*` endpoint 和 `POST /api/auth/login` 公开。其他 API、OpenAPI JSON 和 docs
要求 `Authorization: Bearer <API key>` 或有效 UI session。API key 只有创建响应展示一次明文，之后
只能查询 metadata 或幂等撤销。

- `read`：读取、export、Context Query 与 scoped SPARQL。
- `model`：包含 read，并允许建模、Build Session 与受治理 RDF 写入。
- `admin`：包含 model/read，并允许 Project、Ontology、API key 与全局治理操作。

Project-bound 主体只能访问其 Project；显式提交 foreign Project 返回 `403 forbidden_scope`，只提供
foreign opaque resource ID 时返回 404。UI session 写请求还要求可信 Origin、CSRF cookie 与
`X-CSRF-Token` 相等。

### R4.0-006 主体与角色授权

普通用户仅通过个人 Key 访问；管理员仍可登录。`users.is_org_admin`／停用状态由服务端检查，
普通用户（包括旧 session）不能登录或取得组织管理员权限。Key scope 和语义 Grant 分别判断。

Org Admin 用 `POST /api/users` 登记普通用户（`username`），`GET /api/users`／`/{user_id}`
读取，`PATCH /api/users/{user_id}` 修改 `username` 或 `disabled`；不接受密码、管理员标志或自助注册。
Org Admin 用 `POST /api/projects/{project_id}/members`（`user_id`）添加成员，
`DELETE .../members/{user_id}` 移除；Project Admin 只能读取本项目成员的最小身份。

本项目 Admin 可管理 `/api/projects/{project_id}/semantic-access-roles`：
GET／POST 及 `/{role_id}` 的 GET／PATCH／DELETE。创建字段为 `name`、`description`、`grants`，
以及可选的 `business_role_iri`＋`business_role_ontology_id`。名称项目内唯一，重复返回 409；
Grant 复用保护集的精确字符串规范（至多 64 个、单个至多 128 字符、非空可打印、去重），不按空白或
大小写自动归并。显式关联核对同项目已有 `semantic_definition.semantic_role=business_role`，
读回 `business_role_status` 为 `unassociated`／`valid`／`missing`／`invalid_definition`；
业务角色后续变更／缺失不改变权限，可由管理员修正关联。

`GET /api/projects/{project_id}/members/{user_id}/roles` 读取角色 id 集合；PUT 使用
`{"role_ids": ["role-id"]}` 原子替换（空列表移除全部角色）。跨项目或不存在的角色使整个请求
返回 422，原集合不变。read／model Key 不能调用上述管理接口；Project Admin 不读取全局用户。

`POST /api/api-keys` 必须提交 `user_id`、`name`、`project_id` 和 `scopes`；项目 Key 的用户
必须已经加入本项目，组织 admin Key 必须归属启用的组织管理员。明文仍仅创建时返回。
读回包含 `user_id`，不含 Grant。PATCH 仅可修改 `name`，不能转移用户／项目或提高 scope。
旧 `semantic_grants` 字段在创建／更新时均返回 422；旧 Key Grant 不迁移或参与授权。
仅既有服务端 bootstrap 登记路径允许无归属组织 admin 凭据，API 省略用户或使用 bootstrap 名称
均不能取得该例外。已有无归属普通 Key 需由管理员明确配置成员并重新发行，不自动猜测归属。
R4.0-007 已将 Team 的宿主临时 admin、Protocol model 和 Modeling read Key 显式绑定
到既有 operator-admin 所属用户。仅在本轮新建或宿主确认成功 fork 的新 Project 中加入
该用户成员；existing／普通 checkpoint 接续不修改成员权限，缺成员时返回可定位错误。
不创建用户或语义角色，不复制旧 Project 的权限。

每次 HTTP 请求／MCP 调用重新检查 Key、所属用户、项目成员和角色。有效 Grant 为角色并集；
同用户同项目的所有 Key 共用角色权限，各 Key scope／撤销独立。组织 Key 也先检查所属用户
启用且仍为组织管理员，再进入管理员绕过；用户管理员标志不能提升项目 read Key 的 scope。
正常无角色／空 Grant 仍可读普通资源；依赖故障／损坏角色配置返回可重试 `503 dependency_error`
（MCP 为同名错误），不当作正常空权限或永久撤销凭据。

管理提交后的新调用无需重启即可生效。有效 scope／Grant 变化使旧 Context cursor 返回
`context_cursor_mismatch`，从首页重查；等价有效权限不使分页失效，凭据失效先返回认证错误。
移出项目会同事务撤销该用户本项目 Key 并清空分配，重新加入不复活旧 Key；禁用／重启用用户
可失效／恢复仍合格的未撤销 Key。删角色清分配，删项目级联清成员与角色而保留全局用户。
checkpoint fork 保留保护集和业务定义，成员、Key、权限角色与分配不复制。

主体、分配及 Grant 仅存在控制面，不加入 RDF／模型导出／SPARQL／Consumer 语义响应。
受治理读取继续保持无权与不存在不可区分、分页前过滤和保护集 OR；权限角色不会授予外部数据
或业务执行权限，也不会自动检测说明／脚本中复制的敏感文本。

## 当前主要工作流

### Project、Ontology 与需求澄清

- Project/Ontology CRUD 与默认语义工作区：`/api/projects`、
  `/api/projects/{project_id}/ontologies`
- Project Brief、Interview Answer 与 Competency Question：
  `/api/projects/{project_id}/brief`、`/api/projects/{project_id}/interview-answers`、
  `/api/projects/{project_id}/competency-questions`
- 构建上下文：`GET /api/projects/{project_id}/build-context`

创建 Ontology 后，平台会初始化默认 RDF 图和 Graph Set。历史或不完整工作区可使用当前注册的
workspace repair 操作修复。

### 外部 Agent 建模

外部 Agent 使用 Build Session 和 Ontology Lease 管理恢复与并发，再通过 Modeling Batch 完成
`dry_run` 和 apply。平台保存建模结果、幂等状态、冲突和审计，不在 HTTP 层替 Agent 做领域判断。

同一多值关系槽（相同主体与谓词）可在一个 `apply_atomic` Batch 中删除旧对象的关系并新增
不同对象的关系，以原子切换引用。该豁免不适用于单值竞争写、同一确切 statement 的增删，
或通配／cascade 删除导致的冲突；这些真实冲突仍按既有校验拒绝。Batch 验证失败不修改旧状态，
跨 Batch／Ontology 的切换不具备整体原子性。

R1.1 分阶段工作流使用 Build Session 下的 Modeling Workflow Artifact 和 Modeling Execution Event：
Artifact 以 `artifact_key` 创建不可变线性版本，Event 以 `client_event_id` 幂等追加并获得 Session 内
稳定序号。问题事件使用 current-head compare-and-set 保存 `open/answered/skipped/uncertain/reopened`
状态；更正只能追加 superseding event。`GET .../modeling-workflow:export` 提供完整 JSON 或 Markdown
复盘记录，`GET /api/build-sessions/{session_id}` 只内联小型 `modeling_workflow_summary`。

v4 R4.0-012 阶段性停用 Evidence／完整 lineage。Agent 读取业务资料理解与核对语义，
候选、Batch 与 canonical command 不接受追溯专用字段，不要求登记引用或补齐追溯链。
写入回执、审计、授权、图版本和必要恢复继续由平台与宿主保存；独立语义验收仍核对获准资料。
专用证据与追溯入口已撤下，旧参数按现有参数验证错误拒绝；不提供历史只读兼容。

### 查询与验证

- 授权范围发现：`GET /api/semantic/scopes:discover`
- Context Query：`POST /api/semantic/context:query`
- scoped SPARQL：`POST /api/semantic/sparql:query`
- Ontology read model 以清单中的当前操作为准。SHACL、OWL 自动推理及其运行／结果读取入口按 R4.0-025 退役。

Context Query 返回结构化资源、事实、关系、操作、约束和真实完整性状态，不生成最终自然语言答案。
旧 Agent Test API 已移除；外部 Agent 负责组合结构化结果并生成最终答案。

R1.2-004 起 Context Query 支持一次提交一组同主题的相关表达式。请求体的标准字段是
`queries: list[string]`（1–8 项，每项 trim 后 1–2000 字符、合计 ≤ 8000 字符）；兼容字段
`query: string` 等价于 `queries: [query]` 的单元素列表，二者必须提供且只提供一个。服务对去重
后的规范化表达式只执行一次检索与一次 embedding 批处理；融合结果按证据层级、得分、表达式支持数
和 R1.2-003 既有 tie-breaker 排序，输入顺序不影响打分或排序。匹配结果与相关上下文使用独立预算
（`limit` 默认 20/最大 100；`context_limit` 默认 100/最大 1000）和独立的游标：`match_cursor`
继续下一页匹配，`context_cursor` 只在当前匹配页内继续上下文。请求同时只能携带其中一种 cursor，
且 cursor 必须与当前 principal、Project/Ontology 范围、原始 `queries`、过滤、深度、页大小以及
绑定的 `model_revision` 完全匹配；否则返回 `400 invalid_context_cursor`、
`400 context_cursor_mismatch` 或 `409 context_snapshot_changed`。响应新增 `query.queries`、
`query.normalized_queries`、`primary_matches[*].matched_queries`、`primary_matches[*].fusion`、
`related_context[*].root_paths`、`matches_page`、`context_page`，顶层 `truncated` 等于两页
`truncated` 的逻辑或。配置 `SEMANTIC_CONTEXT_QUERY_CURSOR_SIGNING_SECRET` 时 cursor 可跨进程
重启继续验证；未配置时后端使用进程私有随机完整性材料并经能力发现声明该限制。


R4.0-008 在同一入口增加可选 `semantic_roles`：非空字符串列表，trim、去重，按已声明的
`data.semantic_definition.semantic_role` 精确且区分大小写匹配，多值 OR；与资源／断言筛选取
AND，只筛主命中。null／缺省不筛选，未知角色返回正常空匹配，不推断未声明的角色。
主命中及关联资源投影已有 `semantic_definition`、`action_definition`、`parameter_definition`、
与 description；statement 保留 subject／predicate／object、类型、datatype、
language、图／Ontology 身份及方向。`root_paths` 仅表示根与距离，逐边路径需从实际 statement 还原。

`context_detail` 仅控制关联行：REST 默认 full，MCP 默认 compact；主命中保持 full。
R4.3 增加显式 `preview`，主命中完整且有 `neighbors`：每根引用同一全局周边页的
摘要，`preview_ref` 为当前 `related_context` 的零基下标；稳定 `(ontology_id,kind,id)` 保存于
对应摘要，跨页按该稳定身份累计，不能复用另一页的下标。preview 的 `root_paths.root_index`
引用当前 `primary_matches`，保留每根距离及 Ontology 身份。该注册表保存名称、
IRI、资源类型、已声明角色、最长160字业务含义原文摘录，以及关系/事实身份与读详情入口。
关系保留谓词、端点、相对根方向与距离；资源的 `relationships` 保存直接根边，邻居引用的
`relationships.index` 定位它。多跳不伪装成直接边，完整路径从实际 statement/续页读取。
`preview/details_omitted/truncated` 显式表示省略，原始 JSON literal 不带回完整定义；用
`detail_query` 的 IRI 查主命中取得完整内容。`context_page.returned` 只计唯一摘要，
neighbors 引用不再计额；每页预算全局共享，续页主命中定义不变、邻居为当前页，可按身份累计。
授权先于投影。短定义可能因关联引用增加体积，preview 不保证每次更小。

R4.3 索引/文档模板为 `semantic-retrieval-v2` / `semantic-retrieval-document-v2`，只把
已有 semantic/action/parameter 定义的合同字段增加到资源文档，返回原始定义及词面字段依据。
旧模板向量索引保持降级，须沿现有投影重建流程恢复。`query.ranking_version` 和
`match.ranking_version/rank_score/semantic_similarity` 声明排序版本、排序值及向量相似度；旧 `score/lexical_score` 不改作
业务相关性证明。默认 `exact-expression-max-v2` 修复局部词项误判整句精确，保留可用 max
融合；`evidence-rrf-v2` 是待公开题效果验证的可选方案，不默认启用。查询向量可短时复用，
每次请求仍检查授权/模型修订/索引/分页完整性；邻接复用只限当前请求。

compact 保留普通业务解释、身份和 statement 信息；R4.0-025 不再投影专用规则注解，也不维护专用脚本省略合同。
无效／多值现有普通注解给出可定位读取诊断并保留获准原始 statement。
平台不执行脚本、SQL 或外部 API，不自动判定业务兼容或说明／脚本一致。

`query.result_scope=authorized_query_scope` 固定声明查询边界。`context_limit`（允许 0）仅控制页
大小，内部展开另有 5000 个去重可见工作项预算；`context_page.expansion.status` 为
`complete`／`partial`／`not_requested`。depth 或 context_limit 为 0 时不请求展开；预算不足且
存在额外可见工作项时 partial，reason 为 `expansion_budget_reached`，同时发出
`context_expansion_incomplete`。已枚举项仍可分页，末页可能无 cursor 而保持 partial；缩小范围或
从返回的 IRI 继续。complete 只覆盖当前主命中页、scope、断言选择与 depth，不证明业务完整。
主命中窗口只计授权并符合筛选的去重候选，原始 RDF／向量块满后稳定补读；额外合格候选确实
超出窗口时 `recall.completeness=degraded`，warning 为 `candidate_window_incomplete`。

所有授权在计额、遍历和投影前应用，不返回隐藏资源占位、数量或授权缺口提示；缺关联不能推导
“无规则／允许执行”。cursor 格式现为 v2，旧临时 token 按 invalid 合同失效。context cursor
独立恢复原匹配页，响应继续提供该页后继的 match cursor；续页绑定角色筛选，并校验当前可见
候选／上下文摘要。保护成员变化影响可见结果时返回 snapshot_changed，隐藏集合变化不单独
失效。输出前复核已绑定 Ontology 的 workspace／source 版本，避免混读。

R4.0-010 的四类数据映射资源沿用同一个 read-model 入口：
`GET /api/semantic/ontologies/{ontology_id}/read-models/{model_name}` 支持
`table-mapping-list`／`table-mapping-detail`、`join-mapping-list`／`join-mapping-detail`、
`enum-meaning-list`／`enum-meaning-detail` 和 `metric-list`／`metric-detail`。
detail 行的 `detail_fields` 保留物理定位与已声明引用，并解码结构化注解：TableMapping 包含
`table_name`、`mapped_class` 或 `mapped_definition`、`column_mappings`、`schema_source`、
`semantic_version`、`mapping_definition`、`semantic_definition`；JoinMapping 包含
`mapped_relation`、`join_direction`、`join_path` 及相同两种注解；EnumValueMeaning 包含
`mapped_property`、可选的 `table_mapping` 与 `column` 作用域、`enum_value`、
`business_meaning`、`semantic_value` 及两种注解；MetricDefinition 保留既有粒度／时间／度量／
聚合字段及 `mapping_definition`、`semantic_definition`。`mapped_class` 与 `mapped_definition`
表达两种互斥的 TableMapping 目标形式；`mapping_definition` 的 `source_key`、Schema 版本、
粒度、身份、路径、基数、字段含义和指标 contexts 是说明与引用，不是连接配置或执行授权。
缺省字段表示未提供，JSON `null` 表示已知未知；平台不会从同名表或 Schema 猜补业务含义。
精确 REST 资源读取 `GET /api/semantic/resources/{resource_iri}?ontology_id=...` 也会按同一
合同尝试四种 `*-detail` 模板，并在 `properties` 返回这些字段；不存在或无权的 mapping／metric
资源仍返回同形 `404`。

Context Query 的精确 IRI 锚点也适用于这些 mapping／metric 资源。除实际 RDF 边外，固定结构化
映射字段中的获准 IRI 引用会在 `related_context` 返回方向性派生行，例如：

```json
{
  "origin": "derived_reference",
  "target_kind": "derived_reference",
  "id": "urn:ontology-platform:derived-reference:<stable-sha256>",
  "data": {
    "source_iri": "https://example.test/table-mapping/orders",
    "target_iri": "https://example.test/rules/status-code",
    "predicate": "http://ontology-platform.local/semantic/vocab/mappingDefinition",
    "field_path": "data.mapping_definition.field_meanings[0].conversion_rule_iri",
    "source_path": "data.mapping_definition.field_meanings[0].conversion_rule_iri",
    "derived_reference": true
  }
}
```

派生行的身份由 source IRI、predicate、field path 和 target IRI 稳定计算；它不伪装为已存 RDF
statement。完整值先经过主体访问过滤，再计算列表／计数／cursor；嵌套受限引用会使相关行不可见，
不会返回占位、专属计数或存在性提示。无权与不存在沿用同形空结果／404。无效 JSON 或多值注解
保留获准原始 statement，并附 `annotation_read_diagnostic` warning；scope、cursor 和读取依赖
故障继续使用既有可重试错误合同。平台只保存和读取映射，不连接外部数据库、不执行 SQL／转换，
数据库行列权限由外部系统负责。

跨 Ontology 的映射引用由拥有方 Ontology 的 `reference_ontology_ids` 显式声明。
通过 `PATCH /api/ontologies/{ontology_id}` 提交同一 Project 内获准的依赖 Ontology ID，例如：

```json
{"reference_ontology_ids": ["approved-dependency-ontology-id"]}
```

该列表用于写入引用校验，不自动扩大读取授权；读取仍只包含调用方选定且获准的 Ontology。
同一 Project 关系不会隐式开放其他模型。取消依赖前会在已有 Project／Ontology 锁和 fence 下
重验存量映射；会使引用悬空时返回 `mapping_reference_scope_in_use`，修订映射后可重试。

映射资源或其声明依赖的直接编辑必须进入已有 Modeling Batch 的 `dry_run`／`apply_atomic`、
Attempt、Project fence 和恢复回执；`POST /api/semantic/edits`、原始 TriG／N-Quads／JSON-LD
导入及其他 raw import 也沿用同一合同，不能用绕过 Batch 的写入闭合引用。没有合适 Batch 时返回
`mapping_batch_required`。如果依赖 Project 存在尚未收敛的写入，返回可重试的
`mapping_reference_write_fenced`；调用方应先读取／reconcile 原 Attempt 和 fence，再重试原目标，
不要把同一不确定写入伪装成新的独立结果。

`modeling-context` 返回非秘密的 `semantic_base_iri`，
Protocol 以该 namespace 构造当前平台引用，不从业务候选猜测 IRI。

能力发现：`GET /api/mcp/tools` 在响应的 `capabilities.semantic_context_query` 中返回当前部署
公开的 `queries`/`query`/`limit`/`context_limit`/`depth` 上下限、cursor 种类
（`match`、`context`）、cursor 生命周期（默认 600 秒），以及是否配置了稳定 cursor 签名密钥。
该字段是 R1.2-007 capability discovery 在 Context Query 合约上的唯一展示位置，未引入新路由。

消费 Agent 新会话可先调用范围发现。无筛选时它以稳定游标分页返回当前主体可访问的 Project 与
Ontology；`query` 仅匹配稳定 ID 或名称（trim + case-insensitive contains），`queryable` 仅筛选
Ontology。Project 项返回 `complete/partial/unavailable` 和排除清单，Ontology 项分别返回业务
`status`、技术 `queryable`、不可用原因、当前 `model_revision` 和简要派生警告。响应中的
`query_scope` 可直接用于 Context Query/scoped SPARQL；实际查询仍会重新校验授权、就绪性和版本。
Cursor 同时绑定筛选条件和当前授权 Project 边界，不能在 Project-bound 与组织管理员主体之间或
不同 Project 主体之间复用。配置 `SECRET_KEY` 时 cursor 可跨进程重启继续验证；未配置时后端使用
进程私有随机完整性材料，cursor 只能在生成它的进程生命周期内使用，重启或切换进程后应重新从
第一页发现。

## 错误和兼容性边界

- FastAPI 参数校验通常返回 `422`；业务冲突和不存在资源按各操作实现返回 `4xx`。
- 缺少/无效/revoked credential 返回 `401 invalid_authentication`；scope 或 Project 越权返回
  `403 forbidden_scope`；领域 payload 命中高可信真实秘密返回 `422 secret_in_payload`。
- 受治理语义编辑、Modeling Batch 和 Build Session 有各自的冲突、幂等及恢复语义；调用方应保留
  返回的 session、lease、batch 和 checkpoint 标识。
- Workflow Artifact/Event 写入要求 `model`，读取/export 要求 `read`；单 Artifact 版本上限 1 MiB、
  Event payload 上限 64 KiB、export 上限 8 MiB。版本过期、foreign 引用、问题 stale head 和幂等
  冲突分别返回稳定业务 code，命中 secret 时不会自动修改或回显内容。
- 当前仍注册的 deprecated 兼容操作会继续出现在下方清单中；未注册的旧 Version、Proposal、
  Catalog、Connector 和 Neo4j Entity 接口不是当前能力。
- R-010 的 Dify 端到端验收套件尚未实现，当前没有可引用的 Dify 基准通过率。

## 完整运行时操作清单

下方区块由脚本维护，不要手工编辑。接口变更后运行：

```bash
cd backend
uv run python ../scripts/sync-interface-docs.py --write
```

<!-- BEGIN GENERATED HTTP API INVENTORY -->

| Tag | Method | Path | Summary |
| --- | --- | --- | --- |
| authentication | `GET` | `/api/api-keys` | List Api Keys |
| authentication | `GET` | `/api/api-keys/{key_id}` | Get Api Key |
| authentication | `GET` | `/api/auth/me` | Me |
| authentication | `POST` | `/api/api-keys` | Create Key |
| authentication | `POST` | `/api/api-keys/{key_id}:revoke` | Revoke Api Key |
| authentication | `POST` | `/api/auth/login` | Login |
| authentication | `POST` | `/api/auth/logout` | Logout |
| authentication | `PATCH` | `/api/api-keys/{key_id}` | Update Api Key |
| build sessions | `GET` | `/api/build-sessions/{session_id}` | Get Build Session |
| build sessions | `GET` | `/api/projects/{project_id}/build-context` | Get Project Build Context |
| build sessions | `POST` | `/api/build-sessions/{session_id}/checkpoints` | Save Build Checkpoint |
| build sessions | `POST` | `/api/build-sessions/{session_id}/ontology-leases/{ontology_id}:acquire` | Acquire Ontology Lease |
| build sessions | `POST` | `/api/build-sessions/{session_id}/ontology-leases/{ontology_id}:release` | Release Ontology Lease |
| build sessions | `POST` | `/api/build-sessions/{session_id}/ontology-leases/{ontology_id}:renew` | Renew Ontology Lease |
| build sessions | `POST` | `/api/build-sessions/{session_id}:cancel` | Cancel Build Session |
| build sessions | `POST` | `/api/build-sessions/{session_id}:complete` | Complete Build Session |
| build sessions | `POST` | `/api/build-sessions/{session_id}:resume` | Resume Build Session |
| build sessions | `POST` | `/api/projects/{project_id}/build-sessions` | Create Build Session |
| checkpoint-data | `POST` | `/api/checkpoint-data/capture` | Capture Data |
| checkpoint-data | `POST` | `/api/checkpoint-data/fork` | Fork Data |
| mcp-catalog | `GET` | `/api/mcp/tools` | List Mcp Tools |
| modeling batches | `GET` | `/api/build-sessions/{session_id}/modeling-batches` | List Session Modeling Batches |
| modeling batches | `GET` | `/api/modeling-batches/{batch_id}` | Get Modeling Batch |
| modeling batches | `GET` | `/api/ontologies/{ontology_id}/modeling-batches` | List Ontology Modeling Batches |
| modeling batches | `GET` | `/api/ontologies/{ontology_id}/modeling-context` | Get Modeling Context |
| modeling batches | `GET` | `/api/ontologies/{ontology_id}/semantic-read-models/{model_name}` | Get Ontology Read Model |
| modeling batches | `POST` | `/api/build-sessions/{session_id}/modeling-batches` | Submit Modeling Batch |
| modeling workbench | `GET` | `/api/projects/{project_id}/workbench` | Workbench |
| modeling workbench | `GET` | `/api/projects/{project_id}/workbench/runs/{team_run_id}` | Workbench Run |
| modeling workbench | `GET` | `/api/projects/{project_id}/workbench/runs/{team_run_id}/competency-questions` | Workbench Competency Questions |
| modeling workflow | `GET` | `/api/build-sessions/{session_id}/modeling-execution-events` | List Modeling Execution Events |
| modeling workflow | `GET` | `/api/build-sessions/{session_id}/modeling-workflow-artifacts` | List Modeling Workflow Artifacts |
| modeling workflow | `GET` | `/api/build-sessions/{session_id}/modeling-workflow:export` | Export Modeling Workflow Record |
| modeling workflow | `GET` | `/api/modeling-execution-events/{execution_event_id}` | Get Modeling Execution Event |
| modeling workflow | `GET` | `/api/modeling-workflow-artifacts/{workflow_artifact_id}` | Get Modeling Workflow Artifact |
| modeling workflow | `POST` | `/api/build-sessions/{session_id}/modeling-execution-events` | Record Modeling Execution Event |
| modeling workflow | `POST` | `/api/build-sessions/{session_id}/modeling-workflow-artifacts` | Create Modeling Workflow Artifact |
| ontologies | `GET` | `/api/ontologies/{ontology_id}` | Get Ontology |
| ontologies | `GET` | `/api/ontologies/{ontology_id}/workspace-context` | Get Ontology Workspace Context |
| ontologies | `GET` | `/api/projects` | List Projects |
| ontologies | `GET` | `/api/projects/{project_id}` | Get Project |
| ontologies | `GET` | `/api/projects/{project_id}/ontologies` | List Ontologies |
| ontologies | `POST` | `/api/ontologies/{ontology_id}/workspace/repair` | Repair Ontology Workspace |
| ontologies | `POST` | `/api/projects` | Create Project |
| ontologies | `POST` | `/api/projects/{project_id}/ontologies` | Create Ontology |
| ontologies | `POST` | `/api/projects/{project_id}/ontology-workspaces/repair` | Repair Project Ontology Workspaces |
| ontologies | `PATCH` | `/api/ontologies/{ontology_id}` | Update Ontology |
| ontologies | `PATCH` | `/api/projects/{project_id}` | Update Project |
| ontologies | `DELETE` | `/api/ontologies/{ontology_id}` | Delete Ontology |
| ontologies | `DELETE` | `/api/projects/{project_id}` | Delete Project |
| project interview | `GET` | `/api/ontologies/{ontology_id}/build-overview` | Get Build Overview |
| project interview | `GET` | `/api/projects/{project_id}/brief` | Get Project Brief |
| project interview | `GET` | `/api/projects/{project_id}/competency-questions` | List Competency Questions |
| project interview | `POST` | `/api/competency-questions/{question_id}/status` | Set Competency Question Status |
| project interview | `POST` | `/api/competency-questions/{question_id}/validate` | Validate Competency Question |
| project interview | `POST` | `/api/projects/{project_id}/competency-questions` | Create Competency Question |
| project interview | `POST` | `/api/projects/{project_id}/interview-answers` | Create Interview Answer |
| project interview | `PATCH` | `/api/competency-questions/{question_id}` | Update Competency Question |
| project interview | `PATCH` | `/api/projects/{project_id}/brief` | Update Project Brief |
| semantic | `GET` | `/api/semantic/canonical-mode` | Get Canonical Mode |
| semantic | `GET` | `/api/semantic/edits/audits` | List Semantic Edit Audits |
| semantic | `GET` | `/api/semantic/export` | Export Dataset |
| semantic | `GET` | `/api/semantic/migrations` | List Migration Runs |
| semantic | `GET` | `/api/semantic/migrations/{run_id}` | Get Migration Run |
| semantic | `GET` | `/api/semantic/ontologies/{ontology_id}/export` | Export Ontology |
| semantic | `GET` | `/api/semantic/ontologies/{ontology_id}/read-models/{model_name}` | Read Model |
| semantic | `GET` | `/api/semantic/projection-jobs` | List Projection Jobs |
| semantic | `GET` | `/api/semantic/projection-jobs/{job_id}` | Get Projection Job |
| semantic | `GET` | `/api/semantic/projections/status` | Projection Status |
| semantic | `GET` | `/api/semantic/resources/{resource_iri}` | Read Resource |
| semantic | `GET` | `/api/semantic/scopes:discover` | Discover Semantic Scopes |
| semantic | `GET` | `/api/semantic/statements` | List Statements |
| semantic | `GET` | `/api/semantic/status` | Get Governance Status |
| semantic | `POST` | `/api/semantic/canonical-writes:compile-and-apply` | Compile And Apply Product Command |
| semantic | `POST` | `/api/semantic/context:query` | Query Semantic Context |
| semantic | `POST` | `/api/semantic/datasets:load` | Load Dataset |
| semantic | `POST` | `/api/semantic/derived-results:gc` | Run Derived Results Gc |
| semantic | `POST` | `/api/semantic/edits` | Create Semantic Edit |
| semantic | `POST` | `/api/semantic/migrations` | Create Migration Run |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:cutover` | Cutover Migration Run |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:parity-check` | Run Migration Parity Check |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:rerun-failed-batches` | Rerun Failed Migration Batches |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:rollback` | Rollback Migration Run |
| semantic | `POST` | `/api/semantic/migrations/{run_id}:run-next-batch` | Run Next Migration Batch |
| semantic | `POST` | `/api/semantic/migrations:preflight` | Preflight Migration |
| semantic | `POST` | `/api/semantic/ontologies/{ontology_id}/projection-jobs` | Create Projection Job For Set |
| semantic | `POST` | `/api/semantic/ontologies/{ontology_id}/retrieval:rebuild` | Rebuild Ontology Retrieval |
| semantic | `POST` | `/api/semantic/projection-jobs/{job_id}:run` | Run Projection Job |
| semantic | `POST` | `/api/semantic/projections:reconcile` | Reconcile Projections |
| semantic | `POST` | `/api/semantic/sparql:query` | Query Sparql |
| semantic-protection-sets | `GET` | `/api/projects/{project_id}/protection-sets` | List Protection Sets |
| semantic-protection-sets | `GET` | `/api/protection-sets/{protection_set_id}` | Get Protection Set |
| semantic-protection-sets | `POST` | `/api/projects/{project_id}/protection-sets` | Create Protection Set |
| semantic-protection-sets | `POST` | `/api/protection-sets/{protection_set_id}/members` | Add Protection Set Members |
| semantic-protection-sets | `PATCH` | `/api/protection-sets/{protection_set_id}` | Update Protection Set |
| semantic-protection-sets | `DELETE` | `/api/protection-sets/{protection_set_id}` | Delete Protection Set |
| semantic-protection-sets | `DELETE` | `/api/protection-sets/{protection_set_id}/members` | Remove Protection Set Members |
| subject semantic access | `GET` | `/api/projects/{project_id}/members` | List Members |
| subject semantic access | `GET` | `/api/projects/{project_id}/members/{user_id}/roles` | Get Member Roles |
| subject semantic access | `GET` | `/api/projects/{project_id}/semantic-access-roles` | List Roles |
| subject semantic access | `GET` | `/api/projects/{project_id}/semantic-access-roles/{role_id}` | Get Role |
| subject semantic access | `GET` | `/api/users` | List Users |
| subject semantic access | `GET` | `/api/users/{user_id}` | Get User |
| subject semantic access | `POST` | `/api/projects/{project_id}/members` | Add Member |
| subject semantic access | `POST` | `/api/projects/{project_id}/semantic-access-roles` | Create Role |
| subject semantic access | `POST` | `/api/users` | Create User |
| subject semantic access | `PUT` | `/api/projects/{project_id}/members/{user_id}/roles` | Put Member Roles |
| subject semantic access | `PATCH` | `/api/projects/{project_id}/semantic-access-roles/{role_id}` | Update Role |
| subject semantic access | `PATCH` | `/api/users/{user_id}` | Update User |
| subject semantic access | `DELETE` | `/api/projects/{project_id}/members/{user_id}` | Delete Member |
| subject semantic access | `DELETE` | `/api/projects/{project_id}/semantic-access-roles/{role_id}` | Delete Role |
| untagged | `GET` | `/api/health` | Health |
| untagged | `GET` | `/api/health/dependencies` | Dependency Health |
| untagged | `GET` | `/api/health/postgres` | Postgres Health |

<!-- END GENERATED HTTP API INVENTORY -->

### R4.0-002 共同业务语义说明

`create/update_class`、`create/update_property`、`create/update_relation_type` 与
`create/update_entity` 的 Modeling Batch payload 支持可选 `semantic_definition`：

```json
{
  "semantic_role": "business_role",
  "business_meaning": "负责审核业务内容",
  "applicability": "售后场景",
  "unknowns": ["审核时限待确认"],
  "not_applicable": ["制造审批"],
  "conflicting_meanings": ["两种审核时限口径待确认"]
}
```

三个文本字段为非空字符串，三个集合字段为非空字符串数组；字段可省略，未知字段及错误类型
返回可修正的合同错误。更新时省略表示保持，`null` 清除整份声明，对象替换整份声明。
RDF 使用资源本身的 `op:semanticDefinition` JSON 字面量；这不会改变正式 Class、平台
resource kind 或权限。角色是已确认业务含义的开放字符串，不按视角推导，也不授予权限。

既有 `class-detail`、`entity-detail`、`ontology-schema-summary`、`property-list`、
`relation-type-list`、`entity-list` 读模型在 `detail_fields.semantic_definition` 返回声明，
对应投影版本为 `semantic-read-v2`。精确 `GET /api/semantic/resources/{resource_iri}` 在
`properties.semantic_definition` 返回声明，并支持上述实体、Class 与 Property 资源。
所有路径保留既有 scope 与 access_view；隐藏资源与不存在资源均返回同形 404／空结果。

局部职责或关系用独立的普通语义节点表达，节点说明本地含义并通过通用关系明确连接上下文、
共享定义、关系定义及两端；从既有关系／statement 读取取得这些引用。节点中的未知、冲突和
不适用保持独立；未返回声明或关系不足以推断不存在约束。业务行继续留在外部系统。

中立候选在 `semantic.semantic_definition` 表达上述声明，unified graph 候选使用可选的
item 字段 `semantic_definition`，Protocol 将已批准内容原样转入 payload。Class 可省略，
`semantic.classes` 是中立 Class ID 列表；普通分组使用关系。候选关系端点可用
`{"definition_ref": "candidate-item-id"}` 引用本候选中的 Class／predicate／entity，
Protocol 绑定平台身份，Modeling 不猜测平台 IRI；已存在资源继续遵循原 receipt 绑定合同。
详见 [当前候选合同](../../modeling_team/references/platform-neutral-candidate-authoring.json)。
本增量不引入 Evidence／lineage、自动同义合并或跨 Project 共享。

### R4.0-003 可复用 Action 与业务参数

Action 和业务参数复用普通 Entity 的稳定身份及 `semantic_definition`，不新增资源类型、
表或路由。Action 声明 `semantic_role: "behavior"`，名称、含义和范围随定义保存；人工或
尚无外部能力的动作合法，无需正式 Class、工具绑定、风险、幂等性或凭证说明。
`create_entity`／`update_entity` 的 Batch 和 canonical payload 新增两个可选注释：

```json
{
  "action_definition": {"input_status": "defined", "output_status": "none"},
  "parameter_definition": {
    "direction": "output",
    "value_kind": "object_reference",
    "cardinality": "single",
    "required": null,
    "occurrence_condition": "成功完成时",
    "result_kind": "updated_input"
  }
}
```

上例展示字段合同；实际 Action 和每个参数分别存于自己的 Entity 上，通过普通关系连接，
不会把它们合并成一个身份。每份注释是非空对象，所有字段可省略；省略表示没有提供说明，
不推导默认值。更新省略整份注释表示保持，`null` 清除整份，对象替换整份。
不支持的字段、值或资源类型返回可修正的 payload 错误。

| 注释字段 | 接受值及含义 |
| --- | --- |
| Action `input_status`／`output_status` | `defined`：已定义并通过关系连接参数；`none`：明确无业务输入／返回值；`unknown`：尚未确认。未声明输出与明确无输出不同 |
| 参数 `direction` | `input`／`output`／`unknown` |
| 参数 `value_kind` | `object_reference`／`value`／`unknown`；对象、属性或共享定义的具体引用在图关系中 |
| 参数 `value_type` | 已确认的非空值类型字符串或 `null`（未知），不从名称猜测 |
| 参数 `required` | 布尔值或 `null`（未知）；结果出现条件也可用 `occurrence_condition` 说明 |
| 参数 `cardinality` | `single`／`collection`／`unknown` |
| 参数 `occurrence_condition`／`unit`／`missing_meaning` | 非空已确认说明或 `null`（未知） |
| 参数 `enum_values` | JSON 标量数组；`[]` 明确没有声明枚举限制，`null` 未确认；省略为没有说明 |
| 参数 `result_kind` | `updated_input`／`new_object`／`computed_value`／`unknown`；更新输入时用普通关系引用具体输入参数 |

已确认参数至少说明名称、业务含义、方向、对象引用或值类型、必填性或结果出现条件以及
单值／集合含义；未确认部分显式保留未知。两个同类输入也保持不同参数身份，身份本身不
证明两个运行时对象不同。本合同不保存实际参数值、业务行或流程调用变量。

条件、效果、局部职责和能力关联使用普通语义节点，分别保留自然语言含义、适用范围、未知
及已知冲突。普通关系将节点连接到动作、适用对象／Class、参数、属性、共享规则或角色。
正式子类适用可由 Class 层次辨明；共同条件和局部追加条件同时保留，明确例外不自动覆盖。
效果的范围说明成功、失败或部分结果条件；定义写入不产生已发生的业务事实或权限。

能力关联节点说明对应含义及范围，并通过普通关系指向独立 Operation。允许零或多个能力，
同一能力可被多个动作引用；不自动推断等价、顺序、完整实现或版本兼容。组合步骤的缺口、
未确认对应和冲突随关联读回。更改关联不改写 Action；真正改变参数、条件或效果时须修改
业务定义。Operation 原有活动工具绑定、正式目标 Class 等校验继续生效。

中立候选在 `semantic.action_definition`／`semantic.parameter_definition` 表达注释；
unified 候选接纳同名可选 item 字段，由 Protocol 将获准内容原样映射到 Entity 命令。
新增中立 `operation` item：`semantic.operation_id` 是独立能力身份，`target_class` 指定
候选内的正式 Class，其余字段沿用 Operation v1。Protocol 翻译为 `create_operation`，
在 Class／Property 后、关联前写入；`definition_ref` 可引用该 Operation 的 item ID。
既有资源继续使用其原有获准读取／receipt 绑定，不能伪造新身份代替绑定。

RDF 在各 Entity 上保存 `op:actionDefinition`／`op:parameterDefinition` JSON 字面量。
`entity-list`／`entity-detail` 在 `detail_fields`、精确资源读取在 `properties` 返回对应对象。
引用保留为普通 RDF 关系；通过 `/api/semantic/statements`（`statement-list`）读取涉及
Class／Operation 的关系，不要求两端是 NamedIndividual。Class 层次从 `class-topology`
等既有入口读取；Operation 自身说明保持在既有受治理能力检索路径中。
`entity-relations` 的两端仍限于 NamedIndividual。

所有读取沿用已有 access_view：隐藏参数、规则或 Operation 的关系引用在计数、排序、
分页前过滤，精确隐藏与不存在响应同形。未返回获准关系不能推断没有约束或实现；IRI
过滤不自动保护复制到可见正文中的敏感文本。本增量不增加 Evidence／lineage、条件判定、
能力选择、外部调用或流程编排。详细中立表达见[候选合同](../../modeling_team/references/platform-neutral-candidate-authoring.json)。

### R4.0-025 校验、推理与专用规则合同退役

SHACL Shape CRUD／指导、SHACL 验证、OWL 自动一致性／分类／蕴含及其运行列表、
详情、结果状态读取已退役。直接 REST `/api/semantic/validation-runs`、`reasoning-runs`、
旧图集合的对应运行入口、`shapes/classes/*` 与 `derived-results:reconcile` 为 404；
对应 MCP 工具不再注册或出现在授权目录中。`create_shape`／`update_shape`／`delete_shape`
不在 Batch／canonical 命令集合中。Shape 专用图不能通过原始编辑或 dataset 导入进行维护。
通用 RDF 的 `owl`／`rule`／`shape` 词汇本身仍可用，不按名称删除普通知识。

普通规则使用已有 `semantic_definition.semantic_role: "rule"`、业务说明和普通关系保存
已确认条件、阈值、计算口径、适用范围、例外、冲突和未知。仍可用
`resource_types: ["instance"]`、`semantic_roles: ["rule"]` 及 statements／relations 受治理读取；
缺少专用注解或未返回关系不表示没有业务约束。源脚本可作为普通说明材料，不要求语言、
版本、执行环境、程序化输入输出或求值合同。`rule_definition` 不再作为可选写入／投影字段，
提交该字段返回可定位、可修复的 payload 错误；不会静默丢弃内容。

Context Query 的 `assertion_types` 仅支持 `asserted`；`asserted-plus-reasoning`、
`asserted-plus-rules` 和 fact-audit 的 `inferred`／`rule_derived` 不再支持。
`full-working-view` 不消费历史推理结果，专用 Shape 不进入业务检索范围。
普通显式分类、子类和关系照常保存读取，不产生未表达的推导事实。

写入不再带 SHACL 开关或 Shape 图参数。必要字段、类型格式、批次引用、授权、
图版本、原子 dry-run/apply、实际读回与未知写入恢复继续有效。Protocol 当前交接合同为
`r2-3-005-acceptance-stage-handoff/v2`，只绑定 dry-run、apply、readback 三个真实阶段；
不伪造 validation／reasoning 回执。关联完整性生产自查沿用 R4.0-024 的普通图扫描。

历史运行表、结果图、规则注解、共享图登记、版本和检查点数据保留，支持历史证据与资源恢复；
不进行批量迁移或删除，不重新计算历史 PASS／PARTIAL／REVISE。旧执行器退役仍有效，
没有替代规则执行器、SHACL 替代能力或推理兼容模式。

## v4.1 项目建模工作台只读投影

`GET /api/projects/{project_id}/workbench` 和
`GET /api/projects/{project_id}/workbench/runs/{team_run_id}` 为组织管理员或对应项目管理员
提供 Team/宿主产物的只读投影。普通 read/model Key 不可读取；跨项目访问沿用现有
`forbidden_scope` 合同。响应设置 `Cache-Control: no-store`，不创建/继续 run、不运行模型、不写产物。
Team run ID 与平台 Session、旧数据库 Run ID 相互独立。

`GET /api/projects/{project_id}/workbench/runs/{team_run_id}/competency-questions`
为 v4.2 概览提供管理员专用当前 CQ 视图，沿用上述项目管理员授权、no-store 和 run 绑定检查。
封套沿用 run 详情，artifacts 仅包含 competency_questions、reports、host；仅一个当前题集，
全景／切片统一展示。优先匹配 host 冻结绑定，无绑定时选择唯一最新完整冻结文件；摘要损坏、
歧义、枚举超过上限时 current_questions_available=false，不回退旧题。没有冻结文件时仅返回
公开投影供前端选择唯一最新记录。隐藏题仅提供 question_id、question、visibility、content_version，
不提供参考答案、答案点、私有回答或诊断。原 workbench run 投影继续不读取冻结隐藏题。
报告从现有运行目录中的正式 acceptance-v3/reports 读取，包含无 state.json 的只读验收
运行；跨运行报告必须核实同项目／本体、同 batch_id／snapshot_digest、前后模型绑定及
在线模型一致，公开回归报告不参与。acceptance_reports_complete 表示报告枚举未截断。
报告绑定同一 batch_id／snapshot_digest，沿用实时模型适用性核实；question_verdicts 仅含
获准当前题的 question_id／verdict，包含隐藏题用于逐题标记。verdicts 保留公开裁决，
hidden_summary 保留隐藏汇总。question_ids 包含该报告覆盖的当前题目（已执行、未执行
或已有裁决）；denominator 为该报告覆盖题数。进度按每题最新正式报告的裁决统一计数，
分母为当前完整题集，不区分公开／隐藏、不重复计数；最新报告覆盖却无裁决时不复用旧结果。
不加入建模角色工具；普通 read／model Key 不可访问，管理员视图不改变生产侧盲测隔离。

列表封套：`schema_version=v4.1-workbench/v1`、`project_id`、`observed_at`、`current_run_id`、
`runs[]`、`completeness {complete,limit}`、`limitations[]`。run 摘要包含 `run_id`、记录的 `state`、
`source_updated_at`、`platform_binding {project_id,ontology_ids}`。只有唯一明确非终态 run 时
提供 `current_run_id`；记录状态不是进程存活证明。枚举上限 1000；有界结果不保证全部历史。

run 详情封套：`schema_version=v4.1-workbench-run/v1`，在上述身份/范围/时点外，包含
`artifacts {competency_questions,scenario_map,candidates,materialization,public_feedback,reports,host,handoff}`。
每组是 Artifact 数组；Artifact 包括 `artifact_id`、`kind`、`availability`（available/missing/error）、
`schema_version`、`version`、`source {path,updated_at,sha256}`、`observed_at`、
`scope {project_id,run_id,ontology_ids}`、`limitations[]`、`data`。产物按明确 schema 投影，
不提供任意路径、原始 JSON、私有题集、隐藏回答/诊断、运行日志或凭据。固定文件组枚举上限 500；
无法读取、schema 异常及源文件缺少分别记录。文件及其父目录的符号链接不读取。

固定事实根为源码定位的 `workspaces/modeling-runs`，不依赖服务 cwd。项目关联只接受
`state.platform_binding`、历史 `state.cleanup.scope` 和 `acceptance-v3/production-handoff.json`
的 `scope_binding`；无绑定、身份/范围冲突的 run 不挂到项目，不能从目录名猜测项目。
新 Runner 的 state 绑定仅来自已 prepare 的 PlatformScope 实际项目/Ontology 身份；成功扩展
Ontology plan 后同步原 state 的绑定并保留状态和额外字段，历史产物不改写。

- CQ 仅公开投影的题干、批准必答点、未知、范围、题版本和公开审核绑定；Brief CQ 不等于冻结题集。
- 地图保留切片/视角原状态和 note、candidate refs、共享维护者/引用、依赖、跨切片覆盖、显式未知和调整。
  未登记视角保持未登记；modeled 不提升为已应用或验收通过。
- 候选保留 revision/item、业务含义、未物化 value、脚本注解、映射表达及 neutral definition refs。
  物化投影读取 plan/intents/receipts/approvals 和 Runner 实际 Attempt proofs；apply 模式或普通回执
  本身不证明已应用。原报告/文件版本保留，不合并历史 PASS。
- 正式报告和 `public-regression` 作为不同 kind 保留原 verdict、公开 note/回答、批准必答点、完整分母、
  scope 计数和隐藏获准聚合。原合同没有结构化逐点 verdict 时标 `structured_point_verdicts=not_recorded`，
  不解析自由文本造裁决。`blind_status` 原标签保留；已曝光 ID 仅显示精确绑定的公开 ID。
  公开内容必须匹配报告/反馈的 freeze digest、batch 及题版本；旧公开题 ID 不解封另 freeze 的隐藏内容。
- 报告 `applicability` 与原 verdict 分离：`verified_current` 需要最新真实 freeze 记录、报告摘要、
  model binding 摘要、项目/范围、报告前后模型状态及当前只读 workspace 状态相符；漂移、摘要冲突或
  在线资源删除为 `stale`，缺少绑定/观察证据为 `binding_unknown`。不进行重新评分或真实业务执行。
  `report_digest_scope=complete_record|batch_report_core|mismatch` 明确摘要覆盖范围；现有 CLI 在
  核心报告摘要生成后追加 `sessions` 和 `full_pass`，`batch_report_core` 按该生产者前像验证，
  并记录 `sessions_and_full_pass_outside_report_digest`。`full_pass_verification=recorded_only_not_rescored`
  表示展示原报告最终值；摘要匹配与当前绑定核实均不产生新的 PASS 或独立语义验收结论。
- host 读取实际基线角色配置、存在的隔离 runtime config、固定启动记录、生命周期/交接/第一阻塞事件
  及独立验收 continuation 的已记录时间；请求值、冻结值、观察配置文件和未核实热切换分别表达。
  无绑定余额记录或结构化有效分类计时则保留未知，不从 start 事件数量或进程存活时间推算。

## 通用资源列表及外部能力定义阅读

`GET /api/semantic/ontologies/{ontology_id}/read-models/{model_name}`，使用
`model_name=resource-list`、`field_set=full` 和 `limit=500`，
组合既有实体/分类/属性/关系/映射/指标及 Operation 受治理投影。先在每个真实资源族服务端授权，
再按 IRI 合并和分页；同 IRI 保留同一共享身份、实体完整可见分类和语义注解。无正式 Class 的实体
可阅读。`paging` 的 complete/has_more/truncated 只针对授权且有界的可见集合，不证明业务知识完整。
此入口不从名称或类型推断七视角；业务角色来自真实 `semantic_definition.semantic_role`。

`operation-list`/`operation-detail` 读取 ontology 图中的 Operation 定义、参数、前提、效果、失败、
幂等性、全部精确 tool bindings 和凭据需求类别，沿用既有 Operation schema/秘密检测和语义授权；
不选择首个 binding，不执行外部能力。`GET /api/semantic/resources/{resource_iri}?ontology_id=...`
也支持 Operation 精确下钻，与列表使用相同授权范围。

## v4.2 通用资源关系图谱读取

沿用 `GET /api/semantic/ontologies/{ontology_id}/read-models/{model_name}`，
`model_name=resource-relations`、`include=asserted`，关系请求上限为 1000。
此模板与旧 `entity-relations` 分开：端点使用同一 Ontology 的 `resource-list` 获准
资源窗口（最多 500），支持 Class／属性／关系类型、无 Class 实体、Operation、映射及
指标之间的真实 IRI 三元组，不要求两端为 NamedIndividual。

返回既有 SemanticReadModelEnvelope；items 包含稳定三元组 id、source、target、relation
（predicate IRI）、可选 label、ontology_id、assertion_kind。同一三元组跨图只返回
一个稳定身份及一处真实图位置；不从自由文本或名称推断额外边，字面量不是节点。

2026-10-08 投影升级为 `semantic-resource-relations-v2`：`edge_kind=rdf_relation` 表示
真实 IRI 三元组，`edge_kind=structured_reference` 表示已有结构字段中的明确资源引用。
后者另含 `field_path`，label 为该字段路径，relation 仍为原结构字段谓词，
ontology_id 表示原字面量的读取 Ontology。稳定 id 纳入字段路径，避免同一资源在不同位置的引用被合并。
只读取既有映射／语义定义字段中的 `definition_ref`、`*_iri`、`*_iris`；
definition_ref 按同一获准 resource-list 窗口内唯一的 semantic_id 解析，精确 IRI
也必须落在该窗口内。兼容旧中性 mapping_payload 的 JSON 或安全字典字面量读取，
不执行代码、不按名称猜测、不写入额外 RDF 关系。源、目标、谓词和引用授权仍先于计数／分页。
端点窗口在实际 RDF 查询前限定；受限 predicate 在查询端排除，可选 label 经过原有嵌套
引用授权检查，不能公开的标签省略而保留已获准关系，客户端可用 predicate IRI 显示。

`model_revision` 与该 Ontology 资源读取范围保持一致。`paging.complete` 必须同时满足
端点窗口、关系窗口和底层读取完整；部分结果及相关 warnings 不能被解释为全项目没有
其他模型内容。本接口只读，不增加图写入、推理、业务执行或 Evidence／lineage 功能。
