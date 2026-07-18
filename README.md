# Ontology Platform

Ontology Platform 是供外部 Agent 构建、验证和查询领域本体的本地语义平台。外部 Agent 负责理解
资料与建模判断；平台负责确定性校验、RDF/Oxigraph 语义存储、PostgreSQL 工作流与审计状态、
Evidence Reference、可恢复建模批次、lineage 和结构化查询。

当前 v1 已实现 R-001 至 R-008。Agent Test 外部化（R-009）只部分实现，Dify 端到端验收
（R-010）尚未实现。部署仍应使用受控网络并妥善保管运营凭据。

## Repository Layout

```text
backend/app/api/          # FastAPI routes and schemas
backend/app/mcp/          # FastMCP server and current tools
backend/app/repositories/ # PostgreSQL and RDF/Oxigraph persistence
backend/app/services/     # validation, modeling, query, and lineage workflows
frontend/src/             # React/Vite operational UI
skills/ontology-builder/  # installable external-agent workflow
scripts/                  # local startup and documentation synchronization
docs/                     # requirements, contracts, architecture, and operations
```

## Local Startup

推荐的一键启动方式：

```bash
./scripts/start-local.sh
```

脚本通过 Docker Compose 启动 PostgreSQL 和 Oxigraph，执行 backend 依赖同步和迁移，构建 frontend，
然后启动 backend reload server 与 frontend preview：

| Service | One-command address |
| --- | --- |
| Backend API | `http://127.0.0.1:8001/api` |
| FastAPI docs | `http://127.0.0.1:8001/docs` |
| Frontend preview | `http://127.0.0.1:5173/` |
| PostgreSQL host port | `5434` |
| Oxigraph | `http://127.0.0.1:7878` |

安装仓库自带的 user systemd unit：

```bash
./scripts/install-user-service.sh
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
journalctl --user -u ontology-platform.service
```

手动启动时先创建 backend 配置并安装依赖：

```bash
cp .env.example backend/.env
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

未显式传 `--port` 的 uvicorn 默认使用 `8000`，因此手动 backend 地址为
`http://127.0.0.1:8000/api`。另一个终端可运行 frontend dev server 或 MCP：

```bash
cd frontend
npm install
npm run dev
```

```bash
cd backend
uv run python -m app.mcp.server
```

Vite dev server 的实际地址以命令输出为准；frontend 默认请求同源 `/api`，也可用
`VITE_API_BASE_URL` 覆盖。

## Authentication Boundary

除三个 health endpoint 与登录外，HTTP、OpenAPI 和交互文档都要求 API key 或 UI session。
首次启用前，迁移后在 `backend/` 中创建持久运营主体：

```bash
uv run python -m app.cli.bootstrap_auth --username admin
```

命令交互式读取密码，把 username、初始 password 和一次性 API key 写入 gitignored、权限 `0600` 的
`backend/.local/ontology-platform-bootstrap.json`；该文件是 UI 登录和 API 接入的唯一初始凭据交付，
读取后应转存到受控密码库。API key 通过
`Authorization: Bearer <key>` 使用；MCP 从 `ONTOLOGY_MCP_API_KEY` 读取进程身份，缺失或失效时
拒绝启动。浏览器使用 HttpOnly session cookie，并对写请求执行 CSRF token 与可信 Origin 校验。

## Environment Variables

backend 从进程工作目录的 `.env` 读取配置；仓库命令以 `backend/` 为工作目录，因此文件应为
`backend/.env`。

| Variable | Purpose | Current default/example |
| --- | --- | --- |
| `APP_ENV` | Runtime environment label | `development` |
| `SECRET_KEY` | Persistent UI session signing key | empty generates an ephemeral process key |
| `ONTOLOGY_BOOTSTRAP_ADMIN_USER` / `_PASSWORD` | Idempotent bootstrap admin login | both empty |
| `ONTOLOGY_BOOTSTRAP_ADMIN_API_KEY` | Optional fixed-format org-admin bootstrap key | empty |
| `ONTOLOGY_MCP_API_KEY` | Required API key for MCP process startup | empty |
| `ONTOLOGY_UI_ORIGINS` | Exact comma-separated UI origins allowed for session writes | local `5173` origins |
| `DATABASE_URL` | PostgreSQL SQLAlchemy URL | localhost port `5434` |
| `LLM_BASE_URL` | OpenAI-compatible endpoint used only by current Agent Test | `https://api.openai.com/v1` |
| `LLM_API_KEY` / `LLM_MODEL` | Optional current Agent Test credentials/model | empty |
| `LLM_TEMPERATURE` | Current Agent Test temperature | `0.2` |
| `EMBEDDING_BASE_URL` | Embedding-compatible endpoint | BigModel v4 endpoint |
| `EMBEDDING_API_KEY` / `EMBEDDING_MODEL` | Embedding credentials/model | empty / `embedding-3` |
| `EMBEDDING_DIMENSIONS` / `EMBEDDING_TIMEOUT_SECONDS` | Embedding vector size/timeout | `1024` / `45` |
| `OXIGRAPH_URL` | Canonical RDF store endpoint | `http://localhost:7878` |
| `SEMANTIC_BASE_IRI` | Generated semantic resource prefix | `http://ontology-platform.local/semantic/` |
| `SEMANTIC_GRAPH_IRI_PREFIX` | Platform-managed graph prefix | `http://ontology-platform.local/semantic/graph/` |
| `SEMANTIC_QUERY_TIMEOUT_SECONDS` | General SPARQL timeout | `10` |
| `COMPETENCY_QUESTION_SPARQL_TIMEOUT_SECONDS` | Competency-question SPARQL timeout | `5` |
| `SEMANTIC_QUERY_RESULT_LIMIT` | Semantic query result limit | `1000` |
| `SEMANTIC_SHACL_INFERENCE` | pySHACL inference mode | `none` |
| `SEMANTIC_REASONER_COMMAND` / `SEMANTIC_REASONER_TIMEOUT_SECONDS` | Optional reasoner command/timeout | empty / `60` |
| `SEMANTIC_GRAPH_VISIBILITY_LABELS` | JSON visibility-label mapping | `{}` |
| `BUILD_SESSION_LEASE_TTL_SECONDS` | Ontology lease TTL | `300` |
| `MODELING_BATCH_MAX_ITEMS` | Maximum items per batch | `100` |
| `MODELING_BATCH_MAX_REQUEST_BYTES` | Maximum serialized request size | `1048576` |
| `MODELING_BATCH_MAX_INLINE_EVIDENCE` | Maximum inline evidence entries | `100` |
| `MODELING_BATCH_MAX_EVIDENCE_EXCERPT_CHARS` | Maximum evidence excerpt length | `20000` |
| `MODELING_BATCH_RECOVERY_MAX_STEPS` | Recovery convergence limit | `3` |
| `MODELING_BATCH_EXECUTION_CLAIM_TTL_SECONDS` | Execution claim TTL | `300` |
| `SEMANTIC_CANONICAL_STORE` | Phase-7 canonical-store mode | `legacy` |
| `SEMANTIC_PRODUCT_WRITE_MODE` | Phase-7 product write mode | `legacy_only` |
| `SEMANTIC_READ_MODE` | Phase-7 read mode | `legacy` |
| `SEMANTIC_LEGACY_WRITE_BLOCKED` | Phase-7 legacy write fence | `false` |
| `SEMANTIC_MIGRATION_BATCH_SIZE` | Migration batch size | `200` |
| `SEMANTIC_MIGRATION_PARITY_REQUIRED` | Require migration parity | `true` |
| `SEMANTIC_MIGRATION_PHASE2_MAPPING_VERSION` | Migration mapping version | `phase2-v1` |
| `SEMANTIC_MIGRATION_DEFAULT_SCOPE` | Migration default scope | `ad_hoc` |

`start-local.sh` 还接受 shell 级覆盖：`POSTGRES_HOST/PORT/DB/USER`、`OXIGRAPH_HOST/PORT`、
`BACKEND_HOST/PORT` 和 `FRONTEND_HOST/PORT`。这些变量控制启动脚本，不会自动替换已有
`backend/.env` 的 `DATABASE_URL`。

## Install ontology-builder in Codex

仓库 Skill 已按当前 R-001 至 R-007 协议维护。用 symlink 安装可让仓库更新立即生效：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -sfn "$PWD/skills/ontology-builder" "${CODEX_HOME:-$HOME/.codex}/skills/ontology-builder"
```

按 [MCP 文档](docs/reference/mcp.md) 配置并重启 Codex 后调用 `$ontology-builder`。Skill 使用 Build
Context、Build Session、Evidence Reference、Modeling Batch、Context Query 和 lineage；不会调用已
删除的文件上传、Proposal/Review/Publish 或 Catalog/Connector 工具。

## Documentation synchronization

HTTP 与 MCP 完整清单来自运行时注册表：

```bash
cd backend
uv run python ../scripts/sync-interface-docs.py --write
uv run python ../scripts/sync-interface-docs.py --check
```

CI 会校验生成清单、关键文档现状和 ontology-builder 的 registry 依赖。

## Documentation

- [HTTP API](docs/reference/api.md)
- [MCP Tools](docs/reference/mcp.md)
- [UI](docs/guides/ui.md)
- [Architecture](docs/architecture/overview.md)
- [Platform Guide](docs/guides/platform-guide.md)
- [Glossary](docs/reference/glossary.md)
- [v1.0 requirements](docs/requirements/requirements-v1.0.md)
