# R-007 通用操作语义与外部工具绑定共享测试计划

## 1. 测试依据与记录规则

- 需求：`docs/requirements-v1.0.md` R-007。
- 设计：`docs/superpowers/specs/2026-07-16-r007-operation-semantics-design.md`。
- 依赖：R-004 Modeling Batch、R-005 lineage、R-006 Context Query。

开发 Agent 与独立测试 Agent 必须复用本计划。测试 Agent 在第 8 节追加 Round，不覆盖此前结果，
并使用 `PASS | FAIL | BLOCKED`；修复后使用 `FIXED | STILL FAILING | REGRESSION`。

## 2. 审查重点

1. Operation 是否只有一个 Ontology-scoped RDF 当前态，没有 Postgres/RDF 双权威。
2. 写入是否只扩展 R-004，读取是否只扩展 R-006，没有 Operation 专用批次/查询路由。
3. direct RDF `validate=false` 是否仍执行 Operation invariant，秘密字段是否在写入前 fail closed。
4. Operation 是否复用 R-005 Statement Occurrence、Modeling Item、Evidence 和 Audit lineage。
5. Dify 是否只存在于测试数据，产品代码无 Dify 判断或字段。

## 3. 必测场景

### A. Domain codec 与校验

- 最小合法 Operation 和包含全部字段的 Operation 可 canonical encode/decode；JSON key/空白稳定。
- 缺 name、target Class、binding、idempotency 或 risk 被拒绝；inactive 的允许字段行为与设计一致。
- risk/idempotency/binding kind/value type/status/schema version 非法时返回稳定 code。
- 参数名、condition name、failure code、binding ID 重复被拒绝。
- default/enum/constraint 与 string/integer/number/boolean/object/array/iri 类型逐项验证。
- 集合数、字符串长度、JSON 深度和总字节达到边界可接受，超过边界写入前拒绝。
- 任意嵌套 secret-bearing key、credential ref ID、token/password/header value 被
  `operation_secret_forbidden` 拒绝，错误不得回显秘密值。
- create 不接受自定义 Operation IRI；ID 生成的规范 IRI 稳定。direct RDF 中重复 ID、非规范 IRI、
  update/delete 同时提供不匹配 ID/IRI 均在写入前拒绝。

### B. Modeling Batch

- `create_operation` dry-run 输出确定性 operation ID/IRI 和 normalized delta，不写 RDF/Postgres。
- secret-bearing Operation payload 在 Batch/Item 创建前以请求级错误拒绝；数据库中无 Batch、Attempt、
  Item、Finding、content hash 或 Audit，错误/日志不含 secret 值。编译期单元测试还要证明防御纵深。
- 同一 Batch dry-run/apply/retry 使用相同资源 ID、Item、Audit、Statement Occurrence，不重复写入。
- `item_ref` 可引用同批次 create_class；不存在、跨 Ontology 或非 Class 目标失败。
- update scalar patch 保留 omitted 字段；显式空集合清空；提供集合整体替换。
- delete 后当前图和 Context Query 不再返回 Operation；历史 Statement Occurrence/Audit 保留。
- 两个 Item 同槽相同值产生 duplicate warning；不同值产生 `conflicting_item_effects`。
- apply_atomic 有 Operation 错误时全批不写；apply_partial 只应用稳定安全子集并重跑候选校验。
- Operation 与 class/entity/rule 混合批次、Evidence/rationale/question 关联、lease/workspace version、
  recovery 和 stale 标记回归通过。
- REST `submit_modeling_batch` 与 MCP 对同一 Operation batch 返回一致核心结果。

### C. 受治理 RDF 编辑

- Turtle、JSON-LD 或 INSERT DATA 可创建合法 Operation；确定性 RDF update 可修改它。
- target Class 不存在、required cardinality 缺失、JSON schema 非法、秘密字段均在 RDF 改写前失败。
- `validate=false` 不能绕过任何 Operation invariant。
- 影响 Operation 且无法预先确定候选的 restricted WHERE 返回
  `operation_edit_not_deterministic`；图 hash/revision/Audit 不变。
- 非 Operation direct edit 行为无回归。
- direct edit 成功后 revision、stale、Audit 和 Statement Occurrence 正确；无 Evidence 时状态客观。

### D. Context Query

- 中文“发布工作流需要哪些参数和前置条件”、英文完整问题、API path、MCP tool name 均在同一
  pipeline 命中 `kind=operation`。
- name、alias、description、IRI、target Class、参数、前置条件、效果、failure、binding 与
  credential reference type 分别可命中；未命中保持 `no_match`。
- `resource_types=["operation"]` 仅过滤，不切换服务；省略过滤时 Operation 与其他知识一起排序。
- public `data` 完整返回 operation-v1 结构，JSON literal 已解析，不暴露 graph/raw RDF。
- 使用参数名、binding ID 或 credential type 查询且不带 resource filter 时，不得同时出现 raw JSON
  `kind=fact`；`resource_types=["fact"]` 必须 no-match 或只返回真正业务事实，不能返回 Operation
  内部 predicate/object；neighborhood 同样不得展开内部 JSON statement。
- target Class 出现在一层 related context；`depth=0` 不展开，limit/truncated 稳定。
- inactive/deleted/历史 Operation 不参与当前查询；不同 Ontology 同名 Operation 不合并。
- Project 全局 partial、显式 Ontology all-or-nothing 和跨 Project 防泄漏沿用 R-006。
- Evidence 只返回 ID/status；lineage target 使用 resource IRI；无 Evidence 与 partial lineage 带警告。
- 重复查询在相同 workspace version 上 item ID、score、分组和顺序完全一致。

### E. 凭证和边界

- Modeling payload、RDF、Context response、Batch content/plan/finding、Audit、lineage 递归扫描不含
  夹具 secret 或 credential reference ID。
- 错误 message/details 不回显 secret；日志和 journal 中不出现夹具 secret。
- Operation 只返回 credential requirement type；无执行 URL body、auth header 或可用凭证。
- 产品代码 `rg -i 'dify' backend/app` 不得新增 R-007 专用分支；Dify 仅见于 docs/tests/fixtures。

### F. Regression 与 runtime

- 现有 R-004 create/update/delete commands、Rule handler、partial apply、recovery 测试通过。
- R-005 lineage 和 R-006 service/API/MCP/scoped SPARQL 测试通过。
- MCP registry/allowlist 不增加 Operation 专用 tool；`submit_modeling_batch` 和
  `query_semantic_context` 仍是入口。
- 全量 backend pytest 通过；所有新增/修改 Python 文件 Ruff/format 通过；`git diff --check` 通过。
- 真实 PostgreSQL/Oxigraph 完成 create -> update -> query -> lineage -> delete -> history 流程。
- service 重启后已创建 Operation 仍可查询且顺序稳定；backend/frontend health 正常。

## 4. 建议自动化命令

测试文件名可按实现调整，但覆盖必须等价：

```bash
cd backend
uv run pytest \
  tests/test_operation_semantics.py \
  tests/test_modeling_batches_service.py \
  tests/test_modeling_batches_api.py \
  tests/test_semantic_context_query.py \
  tests/test_semantic_context_query_api.py \
  tests/test_semantic_context_query_mcp.py \
  tests/test_lineage_service.py \
  tests/test_mcp_surface.py -q
uv run pytest
uv run ruff check <changed-python-files>
uv run ruff format --check <changed-python-files>

cd ..
git diff --check
```

R-007 计划不改 frontend，因此无需为它新增 UI 测试；若实际 diff 触及 `frontend/`，必须运行：

```bash
cd frontend
npm run build
npx playwright test
```

## 5. 真实运行态验收

使用唯一测试后缀创建一个 Project、Ontology、Build Session、Lease、target Class、Evidence 和通用
Operation。测试 Operation 可使用 Dify 名称，但所有路径必须走通用模型。

1. R-004 dry-run 和 apply 创建 Operation，验证 Evidence/Item/Audit/Statement Occurrence。
2. REST/MCP 分别查询中文名称、parameter、API identifier 和 credential type，核对核心响应一致。
3. update 替换参数/绑定并保留 omitted 字段；重试验证幂等，旧语句进入历史。
4. 用 direct RDF edit 修改描述；用 `validate=false` 提交 secret-bearing Operation 并确认写入前拒绝。
5. delete Operation，确认当前查询 no-match，lineage include-history 仍可解释创建/更新/删除。
6. 重启服务，在删除前或另一个保留 Operation 上重复最小查询，确认 Oxigraph 持久化。
7. 只清理由唯一后缀证明归属的 Project/RDF 图；无法证明归属的数据不删除并记录。

## 6. 重启与健康门槛

```bash
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

失败时：

```bash
journalctl --user -u ontology-platform.service --no-pager -n 200
```

## 7. 完成门槛

- 设计与需求的 scope/non-goals、R-004/R-005/R-006 集成和 secret invariant 均有自动化证据。
- 独立测试 Agent 在本文件追加 `PASS` Round；所有此前失败有修复/接受记录。
- 全量 backend、changed-file Ruff/format、diff check、真实 runtime、restart/health 全部通过。
- requirements、design、API、MCP、architecture、glossary 状态一致。
- 唯一测试数据清理完成或说明不能安全清理的具体原因。

## 8. 独立测试记录

测试 Agent 在此追加每轮结果，不覆盖前一轮。

### Round 1 - 2026-07-16 - FAIL

稳定基线：`b146983bbf23d8e8765bb8db0bb7f1e61679b9f3` 加 requirement_developer 的未提交
R-007 工作区；测试开始前开发写入已停止。

结论：`FAIL`。自动化、静态和重启健康门槛通过，但真实 PostgreSQL/Oxigraph
的首个 Operation 建模批次在 dry-run 和 apply 均返回 HTTP 500，无法进入
create -> update -> Context Query -> lineage -> delete -> include-history 主流程。

#### 已确认缺陷

- **High - 新 Ontology 的首个 Operation 批次因 asserted graph 尚未物理存在而返回
  500。** 使用唯一后缀 `r007-it-1784197087` 通过 REST 创建 Project、Ontology、
  Build Session 和 Lease，然后在一个批次中以 `item_ref` 同时 `create_class` 和
  `create_operation`。`dry_run` 与 `apply_atomic` 都返回 HTTP 500。journal 显示
  `ModelingBatchService._validate_candidate_delta()` 在 Operation 存在性检查中直接调用
  `rdf_store.get_graph()`，Oxigraph 对尚未存在的空 asserted graph 返回 404，未被
  按空图处理，最终抛出 `RdfStoreUnavailable: The graph <...> does not exists`。失败前
  Ontology Modeling Context 正常报告 `state=ready` 且图 revision 为 0；这是新建 Ontology
  的正常状态，且同批次创建目标 Class 是 R-007 的明确验收路径。代码证据：
  `backend/app/services/modeling_batches.py:796-804`。

#### 已执行命令与结果

- 定向回归：`cd backend && uv run pytest tests/test_operation_semantics.py
  tests/test_modeling_batches_service.py tests/test_modeling_batches_api.py
  tests/test_semantic_context_query.py tests/test_semantic_context_query_api.py
  tests/test_semantic_context_query_mcp.py tests/test_lineage_service.py tests/test_mcp_surface.py
  tests/test_semantic_service.py tests/test_r005_independent_acceptance.py -q`：`114 passed`。
- 全量后端：`cd backend && uv run pytest`：`645 passed, 3 skipped`；3 个 skip 为仓库已有
  PostgreSQL 标记用例，本轮另行使用真实 PostgreSQL/Oxigraph 执行运行态验收。
- 变更 Python 文件：`uv run ruff check ...`：通过；
  `uv run ruff format --check ...`：`10 files already formatted`；`git diff --check`：通过。
- 产品分支检查：`rg -n -i "dify" backend/app`：无匹配；MCP/API 只扩展现有
  `submit_modeling_batch` 和 `query_semantic_context` schema，无 Operation 专用工具或路由。
- 重启：`systemctl --user restart ontology-platform.service`；等待就绪后 unit 为 `active`，
  `GET http://127.0.0.1:8001/api/health` 返回 `200 {"status":"ok"}`，前端
  `http://127.0.0.1:5173/` 返回 `200`。
- 真实运行态：REST 创建独立 Project/Ontology/Build Session/Lease 成功；Modeling
  Context 返回 `state=ready` 和 workspace version。首个包含 Class + Operation 的
  `dry_run` 和 `apply_atomic` 均返回 500，对应 journal 堆栈如上。异常回滚后
  Session/Ontology batch 列表为空，workspace version 未变。

#### 未执行与剩余风险

根据独立测试交接“确认 FAIL 后记录本轮并停止，不修改产品代码”的要求，
本轮未继续执行 update/query/REST-MCP 一致性/lineage/delete/include-history/重启持久化、
真实运行态 secret 零记录、raw JSON fact/unfiltered/neighborhood、direct RDF
`validate=false`/restricted WHERE 以及 Project/Ontology scope 验收。这些有自动化证据的
子集，但不能替代修复后的真实依赖复验。

#### 清理

唯一测试 Project `r007-it-1784197087` 通过 REST DELETE 返回 204；随后 Project
和 Ontology GET 均返回 404。失败请求已回滚，Batch 列表为空，未写入 RDF 当前态。
本轮未修改任何产品代码或验收范围。

### Round 2 - 2026-07-16 - PASS

稳定基线：Round 1 后 requirement_developer 报告修复完成的未提交 R-007 工作区；
测试开始前开发写入已停止。本轮只追加本记录，未修改产品代码或验收范围。

结论：`PASS`。Round 1 High 缺陷已修复；新 Ontology 的首个同批 Class + Operation
dry-run/apply、完整生命周期、REST/MCP、真实 PostgreSQL/Oxigraph、安全、scope、重启、
全量回归和清理门槛全部通过，未发现新的 Critical/High/Medium 验收缺陷。

#### Round 1 缺陷复验

- 使用唯一后缀 `r007-r2-1784197623` 创建全新 Project、Ontology、Build Session
  和 Lease。Ontology 处于 `state=ready`、asserted graph revision 0 且 Oxigraph 尚无
  该物理 named graph。
- 一个 Batch 中以 `item_ref` 同时 `create_class` 和 `create_operation`：
  `dry_run` 返回 HTTP 200 / `validated`，无 Finding；`apply_atomic` 返回 HTTP 200 /
  `applied`，两个 Item 均为 `applied` 且均生成 Evidence Reference ID。不再发生
  `RdfStoreUnavailable`，Round 1 High 标记为 `FIXED`。
- 当地 service 原始配置未设置 `SEMANTIC_PRODUCT_WRITE_MODE`，因此使用仓库默认
  `legacy_only`。真实写入验收期间使用
  `systemctl --user set-environment SEMANTIC_PRODUCT_WRITE_MODE=rdf_primary` 后重启 service；
  测试结束后已执行 `systemctl --user unset-environment SEMANTIC_PRODUCT_WRITE_MODE`
  并再次重启，恢复原始未设置/`legacy_only` 运行状态。

#### 功能、一致性与 lineage

- 创建后的 Context Query 可分别通过中文完整问句、`workflow_id`、
  `POST /workflows/{workflow_id}/publish` 和 `api_key` 命中同一
  `kind=operation`，完整返回 parameter、precondition、effect、failure、idempotency、
  risk、通用 binding 和 credential requirement type。
- REST 与真实 MCP `query_semantic_context` 对同一 `workflow_id` 请求的 primary 核心
  ID/kind/Ontology/label/data/match/Evidence/lineage 投影在排序后逐字节相同。
  MCP registry 仍只使用 `submit_modeling_batch` 和 `query_semantic_context`；55 个工具中
  无名称含 `operation` 的专用工具。
- `update_operation` 将 parameter 整体替换为 `release_note`、binding 替换为通用
  `mcp_tool`、risk 改为 `high`；省略的 name、description、precondition、effect 和
  credential requirement 均保留。完全相同请求重试返回同一 Batch/Attempt，
  `created_batch=false` 且 `created_attempt=false`。
- 确定性 direct RDF delete/insert data 成功修改 description，返回 Audit ID、graph revision 3
  和 `SHACL validation skipped by request`；随后 Context Query 返回新 description。
- 更新与 direct edit 后 `include_history=true` lineage 有17条 active、4条 invalidated
  Statement Occurrence，直接编辑语句包含正确 Edit Audit。
- 重启 service 后，两个 Ontology 中的 Operation 仍可查；重启前后 Project 查询和
  直接编辑 Operation 查询的标准化响应逐字节相同，ID/Ontology 顺序不变。
- `delete_operation` 返回 HTTP 200 / `applied`，显式 Ontology 当前 Context Query
  返回 `no_match`。`include_history=false` lineage 返回 404；
  `include_history=true` 返回 HTTP 200 / `complete`，21条语句全部为
  `invalidated`，保留 Modeling Item 与 Edit Audit origins。

#### 安全、投影与 scope

- 包含唯一假 secret 的 Operation Modeling payload 返回 HTTP 422 /
  `operation_secret_forbidden`。请求前后全局 Batch/Attempt/Item/Audit 计数完全不变，
  该 `client_batch_id` 的 Batch 数为 0，响应和对应 journal 中假 secret 命中数为 0。
- Turtle direct RDF 在 Operation subject 上加入 secret-bearing predicate，即使
  `validate=false` 仍返回 `operation_secret_forbidden`；workspace version 和 Audit 数未变，
  错误与 journal 不含假 secret。
- Operation restricted `DELETE/INSERT WHERE` 返回
  `operation_edit_not_deterministic`；workspace version 和 Audit 数未变。
- 未过滤 `workflow_id` 查询的 primary 只有 concept 与结构化 Operation，一层
  related context 只有目标 Class，无 Operation 内部 predicate/raw JSON。
  `resource_types=["fact"]` 返回 `no_match`、空 primary 和空 related context。
- 同一 Project 的两个 Ontology 中建立同名 Operation：Project scope 稳定返回两条且
  不合并，各自显式 Ontology scope 只返回一条。另一 Project 中建立带唯一
  marker 的同名 Operation；第一个 Project 响应 marker 命中数为 0，将跨 Project
  Ontology ID 显式放入第一个 Project scope 返回 HTTP 404 / `scope_not_found`。
- `rg -n -i '\bdify\b' backend/app` 无匹配；Dify 只是本轮通用 Operation
  runtime 数据，产品代码无 Dify 分支。

#### 自动化、静态和运行健康

- 定向命令：`cd backend && uv run pytest tests/test_operation_semantics.py
  tests/test_modeling_batches_service.py tests/test_modeling_batches_api.py
  tests/test_semantic_context_query.py tests/test_semantic_context_query_api.py
  tests/test_semantic_context_query_mcp.py tests/test_lineage_service.py tests/test_mcp_surface.py
  tests/test_semantic_service.py tests/test_r005_independent_acceptance.py -q`：`115 passed`。
- 全量命令：`cd backend && uv run pytest`：`646 passed, 3 skipped`。3 个 skip 为仓库已有
  PostgreSQL 标记用例；本轮已另行在真实 PostgreSQL/Oxigraph 执行完整验收。
- `uv run ruff check` 对12个变更 Python 文件通过；
  `uv run ruff format --check` 返回 `12 files already formatted`；`git diff --check` 通过。
- R-007 未变更 frontend，按计划不执行 UI suite。在 `rdf_primary` 持久化重启和
  恢复原始配置后的最终重启两次，service 均为 `active`、backend
  `/api/health` 均返回 `200 {"status":"ok"}`，frontend 均返回 HTTP 200。

#### 清理与剩余风险

- 测试使用2个唯一 Project、3个唯一 Ontology。按 Ontology ID 枚举 ontology/data/
  shapes/shapes-custom/policy 共15个唯一 graph；清理前3个含数据，执行
  `DROP SILENT GRAPH` 后15个 `graph_exists` 均为 false。两个 Project REST DELETE 均返回
  204，随后两个 Project 和三个 Ontology GET 均返回 404。
- 临时 systemd manager 环境变量已删除，最终 service 在原始配置下健康。
- 剩余风险：无与 R-007 验收冲突的已知风险。需主 Agent 在关闭阶段将
  requirements/design/API/MCP/architecture/glossary 最终状态同步并提交；该关闭动作不改变
  本轮独立验收 `PASS`。
