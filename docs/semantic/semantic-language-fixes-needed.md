# 标准语义语言重构 — 集成测试发现的中高等缺陷清单

## 背景

本文档基于按 `docs/semantic/semantic-language-integration-test-plan.md` 进行的集成验证。验证通过冷启动本地栈（Postgres + Neo4j + Oxigraph via Docker Compose，FastAPI 后端 `:8001`，前端 preview `:5173`），对运行中的服务实测场景 1、3、4、5、8、10，并跑了 61 个聚焦语义 pytest、116 个扩展语义 pytest 以及 14 个 Playwright spec。

**整体结论：FAIL。** 在干净部署和真实 Oxigraph 路径上有 2 个严重缺陷必须修复，1 个中等缺陷建议修复。

## 严重缺陷（必须修复，阻塞上线）

### #1 Alembic 迁移 revision ID 超过 `varchar(32)` 上限

- **现象**：在干净数据库上执行 `./scripts/start-local.sh` 时，Alembic 在从 `0014_semantic_rule_tables` 升级到 `0015_semantic_projection_manifests` 时报错：
  ```
  psycopg.errors.StringDataRightTruncation: value too long for type character varying(32)
  [SQL: UPDATE alembic_version SET version_num='0015_semantic_projection_manifests' WHERE ...]
  ```
- **根因**：Alembic 默认 `alembic_version.version_num` 列为 `varchar(32)`，而重构新增 revision ID 长度超标：
  - `0015_semantic_projection_manifests` — 34 字符 ❌
  - `0016_semantic_migration_tables` — 30 字符 ✅
  - 历史命名最长的 `0011_semantic_runtime_metadata` / `0013_semantic_graph_governance` 都是 30 字符，刚好卡在边界。
- **影响**：Acceptance Gate 1（"本地数据库下后端语义 API 测试通过"）从干净 checkout 上达不到；任何新部署 / 新 CI 环境会在首次迁移挂掉。
- **位置**：
  - `backend/migrations/versions/0015_semantic_projection_manifests.py:11-12`
  - `backend/migrations/versions/0016_semantic_migration_tables.py:11-12`（依赖 `0015`，必须连改）
- **建议修复（任选其一）**：
  1. **首选**：把 `0015_semantic_projection_manifests` 改名为 ≤32 字符的 revision（如 `0015_semantic_proj_manifests`，并同步改 `0016` 的 `down_revision`）。
  2. 在 `0011_semantic_runtime_metadata` 之前或之后插入一个早期迁移，把 `alembic_version.version_num` 扩为 `varchar(128)`，并更新项目的 `alembic` 模板（`backend/migrations/env.py`）。
- **验证方式**：
  ```bash
  docker compose down -v   # 清掉所有 volume
  docker compose up -d
  cd backend && uv run alembic upgrade head   # 应直接成功
  ```

### #2 SPARQL CONSTRUCT 规则在真 Oxigraph 下执行失败（`\nLIMIT` 缺陷）

- **现象**：通过 `POST /api/semantic/graph-sets/{graph_set_id}/rule-runs` 跑任意不带 `LIMIT` 的 `sparql_construct` 规则模板，规则运行返回：
  ```
  status=failed
  error="error at 3:7: expected one of OFFSET, VALUES"
  ```
- **复现**：把规则模板生成的等价查询直接打到 `/api/semantic/sparql:query` 同样报错；把 `\n` 换成空格同样的查询就成功并返回期望的派生三元组。
- **根因**：在 `LIMIT` 注入逻辑里用了换行符而非空格，Oxigraph 的 SPARQL 解析器拒绝 `}\nLIMIT N`：
  - `backend/app/repositories/rdf_store.py:409-412`
    ```python
    def _query_with_limit(query: str, limit: int) -> str:
        if " limit " in f" {query.lower()} ":
            return query
        return f"{query.rstrip()}\nLIMIT {limit}"   # ← \n 让 Oxigraph 报错
    ```
  - `backend/app/services/semantic_construct.py:62-64` 同样模式：
    ```python
    if " limit " not in f" {query.lower()} ":
        query = f"{query.rstrip()}\nLIMIT {statement_limit}"
    ```
- **影响**：任何用户 CONSTRUCT 模板（除非自己写了 `LIMIT`）都会跑挂 → Acceptance Gate 3（"图集校验、推理、规则派生、派生指针 reconcile、GC 串到一条场景中测试"）的规则派生这条腿在真 Oxigraph 下失败。pytest 没抓到是因为大多数规则测试走内存版 `RdfStoreRepository` 替身，不接真 Oxigraph。
- **建议修复**：
  1. 把两处 `f"{query.rstrip()}\nLIMIT {limit}"` 改成 `f"{query.rstrip()} LIMIT {limit}"`（空格替代换行）。
  2. 在 `backend/tests/` 中加一个 live-Oxigraph 集成测试：起真 Oxigraph 容器 → 装载一个小数据集 → 跑一个不带 `LIMIT` 的 CONSTRUCT 规则 → 断言 `status=succeeded` 且生成的语句正确。
- **验证方式**：
  ```bash
  # 后端启动后
  curl -s -X POST http://127.0.0.1:8001/api/semantic/sparql:query \
    -H "Content-Type: application/json" \
    -d '{"query":"CONSTRUCT { ?s ?p ?o } WHERE { GRAPH <...> { ?s ?p ?o } }"}'
  # 应返回 200 + turtle，而非 400
  ```

## 中等缺陷（强烈建议修复，提升契约质量）

### #3 畸形 RDF 触发未捕获解析异常，返回 HTTP 500

- **现象**：向 `POST /api/semantic/edits` 提交非法 Turtle（如 `"GARBAGE not valid turtle"`）返回 **HTTP 500 Internal Server Error**，而非干净的 4xx。
- **根因**：`rdflib` 在解析失败时抛 `rdflib.plugins.parsers.notation3.BadSyntax`（继承自 `rdflib.parser.ParseError`），但 `app/api/semantic.py` 的 edits 端点异常处理器只捕获 `(SemanticServiceError, RdfStoreError)`：
  ```python
  # backend/app/api/semantic.py:353-374
  @router.post("/edits", response_model=SemanticEditResponse)
  def create_semantic_edit(...):
      try:
          result = _service(...).apply_edit(...)
          return SemanticEditResponse(**result)
      except (SemanticServiceError, RdfStoreError) as exc:
          raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
  ```
  服务层 `_prepare_edit → _parse_graph → graph.parse(...)` 直接把 `rdflib` 异常透传出来。
- **影响**：失败矩阵中"不修改 Oxigraph / 不修改图版本号"是满足的（事务回滚），但对外契约泄露了未处理异常类，违反 REST 契约，前端 / agent 拿不到结构化错误。同样的缺口也存在于其他消费 RDF 的端点（`/datasets:load` 等）。
- **位置**：
  - `backend/app/api/semantic.py:373-374`（以及类似的 `/datasets:load` 异常处理）
  - 服务层 `backend/app/services/semantic.py:580` 附近的 `_parse_graph`，建议在服务层把 `rdflib.parser.ParseError` 包装成 `SemanticServiceError(status_code=400)`。
- **建议修复**：
  1. 在服务层 `_parse_graph` / `_prepare_edit` 中捕获 `rdflib.parser.ParseError`，重新抛为带 `status_code=400` 的 `SemanticServiceError`，附带行号 / 解析细节。
  2. 或者把 API 端点的异常处理器扩展为也捕获 `rdflib.parser.ParseError`。
- **验证方式**：
  ```bash
  curl -i -X POST http://127.0.0.1:8001/api/semantic/edits \
    -H "Content-Type: application/json" \
    -d '{"format":"turtle","content":"GARBAGE","target_graph_iri":"...","evidence_status":"evidence_bound","warning_state":{}}'
  # 期望 HTTP 400 + { "detail": "RDF parse error: ..." }
  ```

## 次要观察（不阻塞，仅供参考）

下列并非缺陷，仅为集成测试覆盖建议：

- **Playwright spec 走 mock**：`frontend/tests/semantic-governance.spec.ts` 用 `page.route` 拦截 `**/api/**`，所以只覆盖了 UI 接线，未覆盖 live-contract。Acceptance Gate 7 满足，但建议补 1-2 个真后端契约 smoke（如加载 → 编辑 → 校验 → 导出的小 e2e）。
- **`PATCH /api/semantic/rule-definitions/{rule_id}` 不更新 `body`**：响应里 body 字段保持原值。如果是有意为之（规则定义不可变，需新建版本），建议在 OpenAPI summary 里说明；如果应该可改，需修服务层。
- **`/api/semantic/canonical-writes:compile-and-apply` 要求 `ontology_id`**：没有完整 legacy 数据模型（project / ontology / version）时无法完整跑通。建议提供一份官方 fixture 或更友好的错误提示。
- **`SEMANTIC_REASONER_COMMAND` 默认空**：测试计划允许 fake runner，生产部署文档应明确给出 HermiT / Openllet 的安装和命令模板。

## 上线前 Checklist

- [ ] 修复 #1（迁移 revision 命名 / alembic_version 列宽） — 在干净 volume 上跑通 `alembic upgrade head`。
- [ ] 修复 #2（`\nLIMIT` → ` LIMIT`） — 跑通 live-Oxigraph CONSTRUCT 规则端到端集成测试。
- [ ] 修复 #3（畸形 RDF → 400） — 给所有消费 RDF 的端点补 `rdflib.parser.ParseError` 处理。
- [ ] 补 live-Oxigraph 集成测试覆盖规则派生路径（参考 Acceptance Gate 2、3）。
- [ ] 重跑本测试计划场景 1–10，确认所有 acceptance gate 满足。
